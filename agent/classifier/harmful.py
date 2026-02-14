"""
Harmful content detection: OpenAI (vision + moderation) or local keyword blocklist + OCR.
Categories: inappropriate, violence, self_harm, bullying_hate.
"""
import io
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PIL import Image

# Optional OCR
try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# Max size (longest side) for OCR/vision to reduce CPU and memory
MAX_IMAGE_SIZE_FOR_ANALYSIS = 800

# Default keyword blocklist (sample; extend via config classifier.keywords)
DEFAULT_KEYWORDS: Dict[str, List[str]] = {
    "inappropriate": ["porn", "xxx", "adult only", "nsfw", "nude", "naked"],
    "violence": ["kill yourself", "murder", "shoot them", "bomb", "terrorist"],
    "self_harm": ["suicide", "cut myself", "self harm", "end my life", "kill myself"],
    "bullying_hate": ["hate you", "kill yourself", "die", "ugly", "fat", "stupid", "hate speech", "racist"],
}


@dataclass
class HarmfulResult:
    flagged: bool
    categories: List[str] = field(default_factory=list)
    confidence: float = 0.0
    details: Optional[str] = None


class HarmfulContentClassifier:
    """OpenAI (moderation + optional vision) or local keyword blocklist + OCR."""

    def __init__(
        self,
        api_key: str = "",
        categories: Optional[List[str]] = None,
        confidence_threshold: float = 0.7,
        use_vision: bool = True,
        provider: str = "openai",
        keywords: Optional[Dict[str, List[str]]] = None,
    ):
        self.api_key = api_key
        self.categories = categories or [
            "inappropriate",
            "violence",
            "self_harm",
            "bullying_hate",
        ]
        self.threshold = confidence_threshold
        self.use_vision = use_vision
        self.provider = (provider or "openai").lower()
        self._keywords = {k.lower(): [w.lower() for w in v] for k, v in (keywords or DEFAULT_KEYWORDS).items()}
        self._cooldown_until: dict = {}  # category -> unix time

    def _resize_for_analysis(self, image: Image.Image, max_size: int = MAX_IMAGE_SIZE_FOR_ANALYSIS) -> Image.Image:
        """Resize image so longest side is max_size. Speeds up OCR and vision and reduces memory."""
        w, h = image.size
        if w <= max_size and h <= max_size:
            return image
        if w >= h:
            new_w = max_size
            new_h = int(h * max_size / w)
        else:
            new_h = max_size
            new_w = int(w * max_size / h)
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = getattr(Image, "LANCZOS", 1)
        return image.resize((new_w, new_h), resample)

    def check_image(self, image: Image.Image) -> HarmfulResult:
        """Run detection on image. Returns HarmfulResult."""
        small = self._resize_for_analysis(image)
        text = ""
        if HAS_OCR:
            try:
                text = pytesseract.image_to_string(small)
            except Exception:
                pass
        text = (text or "").strip()

        if self.provider == "keyword":
            return self._check_keywords(text)

        if not self.api_key:
            return HarmfulResult(flagged=False)

        # 1) Text moderation (OpenAI)
        if text:
            result = self._moderate_text(text)
            if result.flagged:
                return result

        # 2) Optional vision (OpenAI) – use resized image
        if self.use_vision:
            return self._check_vision(small)
        return HarmfulResult(flagged=False)

    def _check_keywords(self, text: str) -> HarmfulResult:
        """Local: match OCR text against keyword blocklist. No API."""
        if not text:
            return HarmfulResult(flagged=False)
        text_lower = text.lower()
        # Normalize whitespace for phrase matching
        text_norm = re.sub(r"\s+", " ", text_lower)
        flagged_cats: List[str] = []
        for cat in self.categories:
            words = self._keywords.get(cat, [])
            for phrase in words:
                if phrase in text_norm or phrase in text_lower:
                    if cat not in flagged_cats:
                        flagged_cats.append(cat)
                    break
        return HarmfulResult(
            flagged=len(flagged_cats) > 0,
            categories=flagged_cats,
            confidence=self.threshold if flagged_cats else 0.0,
            details=f"Keyword match: {', '.join(flagged_cats)}" if flagged_cats else None,
        )

    def _moderate_text(self, text: str) -> HarmfulResult:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            r = client.moderations.create(input=text)
            res = r.results[0]
            # Map API category names (with hyphen) to our names
            cat_map = [
                ("sexual", "inappropriate"),
                ("violence", "violence"),
                ("self-harm", "self_harm"),
                ("hate", "bullying_hate"),
                ("harassment", "bullying_hate"),
            ]
            flagged_cats = []
            cats = getattr(res, "categories", None)
            if cats is not None:
                for api_name, our_name in cat_map:
                    try:
                        flag = getattr(cats, api_name, None)
                        if flag is True or (hasattr(flag, "flagged") and getattr(flag, "flagged", False)):
                            if our_name not in flagged_cats:
                                flagged_cats.append(our_name)
                    except Exception:
                        pass
            scores = getattr(res, "category_scores", None)
            conf = 0.9 if flagged_cats else 0.0
            if scores is not None:
                for api_name, _ in cat_map:
                    try:
                        s = getattr(scores, api_name, None)
                        if s is not None and float(s) > conf:
                            conf = float(s)
                    except Exception:
                        pass
            return HarmfulResult(
                flagged=len(flagged_cats) > 0,
                categories=flagged_cats,
                confidence=conf,
                details=f"Text moderation: {', '.join(flagged_cats) or 'none'}",
            )
        except Exception as e:
            return HarmfulResult(flagged=False, details=str(e))

    def _check_vision(self, image: Image.Image) -> HarmfulResult:
        """Use OpenAI vision to describe and infer safety (no dedicated safety API for image)."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            buf.seek(0)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe this image in one short sentence. Then answer: does it show inappropriate/adult content, graphic violence, self-harm, or bullying/hate? Reply with ONLY: SAFE or one or more of: INAPPROPRIATE, VIOLENCE, SELF_HARM, BULLYING_HATE.",
                            },
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{__import__('base64').b64encode(buf.getvalue()).decode()}"}},
                        ],
                    }
                ],
                max_tokens=150,
            )
            content = (response.choices[0].message.content or "").strip().upper()
            if "SAFE" in content and "INAPPROPRIATE" not in content and "VIOLENCE" not in content and "SELF_HARM" not in content and "BULLYING" not in content:
                return HarmfulResult(flagged=False)
            cats = []
            if "INAPPROPRIATE" in content:
                cats.append("inappropriate")
            if "VIOLENCE" in content:
                cats.append("violence")
            if "SELF_HARM" in content:
                cats.append("self_harm")
            if "BULLYING" in content or "HATE" in content:
                cats.append("bullying_hate")
            return HarmfulResult(
                flagged=len(cats) > 0,
                categories=cats,
                confidence=self.threshold,
                details=content[:200],
            )
        except Exception as e:
            return HarmfulResult(flagged=False, details=str(e))

    def apply_cooldown(self, categories: List[str], cooldown_seconds: int) -> bool:
        """Return True if we should suppress alert due to cooldown."""
        now = time.time()
        for c in categories:
            if self._cooldown_until.get(c, 0) > now:
                return True
        for c in categories:
            self._cooldown_until[c] = now + cooldown_seconds
        return False
