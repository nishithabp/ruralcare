"""SMS templates in the app's four languages."""
TEMPLATES = {
    "urgent_asha": {
        "en": "Urgent: {name} reported {symptoms}. Please visit today.",
        "hi": "ज़रूरी: {name} ने {symptoms} बताया है। कृपया आज मिलने जाएँ।",
        "kn": "ತುರ್ತು: {name} ಅವರು {symptoms} ಎಂದು ತಿಳಿಸಿದ್ದಾರೆ. ದಯವಿಟ್ಟು ಇಂದೇ ಭೇಟಿ ನೀಡಿ.",
        "ta": "அவசரம்: {name} {symptoms} என தெரிவித்தார். இன்றே சென்று பார்க்கவும்.",
    },
    "expiry_patient": {
        "en": "{medicine} expires in {days} days. Please get a new strip.",
        "hi": "{medicine} {days} दिन में एक्सपायर हो रही है। कृपया नई पट्टी लें।",
        "kn": "{medicine} {days} ದಿನಗಳಲ್ಲಿ ಅವಧಿ ಮುಗಿಯುತ್ತದೆ. ದಯವಿಟ್ಟು ಹೊಸ ಸ್ಟ್ರಿಪ್ ಪಡೆಯಿರಿ.",
        "ta": "{medicine} {days} நாட்களில் காலாவதியாகும். புதிய அட்டையைப் பெறுங்கள்.",
    },
    "appointment": {
        "en": "Reminder: your doctor consultation is today.",
        "hi": "याद दिलाना: आज आपका डॉक्टर से परामर्श है।",
        "kn": "ನೆನಪಿಸುವಿಕೆ: ಇಂದು ನಿಮ್ಮ ವೈದ್ಯರ ಸಮಾಲೋಚನೆ ಇದೆ.",
        "ta": "நினைவூட்டல்: இன்று உங்கள் மருத்துவர் ஆலோசனை உள்ளது.",
    },
}


def render(key: str, lang: str, **params) -> str:
    t = TEMPLATES[key]
    return t.get(lang, t["en"]).format(**params)
