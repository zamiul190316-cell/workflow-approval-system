"""
ai_validator.py — AI Document Validation Module
Trust Bank PLC Workflow Approval System

Uses OCR + NLP keyword matching to validate that uploaded documents
are relevant to the request category/subject.

Dependencies (optional — falls back to basic matching if unavailable):
    pip install pytesseract Pillow PyPDF2 python-docx
"""
import os
import re
import logging
from difflib import SequenceMatcher

logger = logging.getLogger('workflow')

# ─── Category keyword map ─────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    'medical claim':          ['medical', 'health', 'hospital', 'doctor', 'prescription',
                               'treatment', 'diagnosis', 'patient', 'clinic', 'medicine',
                               'discharge', 'laboratory', 'xray', 'blood test'],
    'travel allowance':       ['travel', 'journey', 'ticket', 'flight', 'train', 'bus',
                               'hotel', 'accommodation', 'boarding', 'itinerary', 'visa',
                               'passport', 'transport'],
    'training request':       ['training', 'workshop', 'seminar', 'course', 'certification',
                               'program', 'learning', 'education', 'institute', 'academy'],
    'leave application':      ['leave', 'absence', 'vacation', 'sick', 'annual',
                               'emergency', 'casual', 'approval', 'hr'],
    'loan approval':          ['loan', 'credit', 'repayment', 'interest', 'collateral',
                               'borrower', 'lender', 'mortgage', 'finance', 'bank'],
    'procurement request':    ['purchase', 'vendor', 'quotation', 'invoice', 'supply',
                               'requisition', 'procurement', 'order', 'price', 'delivery'],
    'it procurement':         ['laptop', 'computer', 'server', 'network', 'hardware',
                               'software', 'device', 'equipment', 'it', 'technology',
                               'monitor', 'keyboard', 'router', 'switch'],
    'fund transfer':          ['transfer', 'amount', 'account', 'beneficiary', 'rtgs',
                               'neft', 'swift', 'bdt', 'taka', 'payment', 'remittance'],
    'recruitment':            ['vacancy', 'candidate', 'interview', 'resume', 'cv',
                               'appointment', 'hire', 'job', 'position', 'employment'],
    'asset purchase':         ['asset', 'furniture', 'vehicle', 'equipment', 'purchase',
                               'depreciation', 'fixed asset', 'acquisition'],
    'vendor payment':         ['vendor', 'invoice', 'payment', 'supplier', 'bill',
                               'service', 'contract', 'amount', 'receipt'],
    'account opening':        ['account', 'customer', 'kyc', 'nid', 'passport',
                               'signature', 'nominee', 'opening', 'form'],
    'credit limit increase':  ['credit', 'limit', 'increase', 'facility', 'exposure',
                               'cib', 'risk', 'collateral', 'liability'],
    'investment approval':    ['investment', 'return', 'portfolio', 'bond', 'treasury',
                               'security', 'yield', 'maturity', 'rate'],
}

# Suspicious / clearly wrong document signals
REJECTION_SIGNALS = [
    'pornographic', 'illegal', 'explicit', 'violence',
    'unrelated', 'personal photo', 'selfie',
]


# ─── Text Extraction ──────────────────────────────────────────────────────────

def extract_text_from_file(file_path: str) -> str:
    """Extract text from PDF, image, or Word document."""
    ext = os.path.splitext(file_path)[1].lower()
    text = ''

    try:
        if ext == '.pdf':
            text = _extract_pdf(file_path)
        elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'):
            text = _extract_image(file_path)
        elif ext in ('.doc', '.docx'):
            text = _extract_word(file_path)
        elif ext in ('.txt', '.csv'):
            with open(file_path, 'r', errors='ignore') as f:
                text = f.read()
        else:
            text = ''
    except Exception as exc:
        logger.warning('Text extraction failed for %s: %s', file_path, exc)
        text = ''

    return text.lower().strip()


def _extract_pdf(path: str) -> str:
    try:
        import PyPDF2
        text = []
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text.append(page.extract_text() or '')
        return ' '.join(text)
    except ImportError:
        logger.info('PyPDF2 not installed — skipping PDF text extraction')
        return ''


def _extract_image(path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(path)
        return pytesseract.image_to_string(img)
    except ImportError:
        logger.info('pytesseract/Pillow not installed — skipping OCR')
        return ''
    except Exception as exc:
        logger.warning('OCR failed: %s', exc)
        return ''


def _extract_word(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return ' '.join(p.text for p in doc.paragraphs)
    except ImportError:
        logger.info('python-docx not installed — skipping Word extraction')
        return ''


# ─── Validation Logic ─────────────────────────────────────────────────────────

def validate_document(file_path: str, category: str, subject: str) -> dict:
    """
    Validate an uploaded document against the approval category and subject.

    Returns:
        {
            'valid': True/False,
            'confidence': 0-100 (int),
            'matched_keywords': [...],
            'message': 'Human readable result',
            'details': '...',
        }
    """
    category_lower = category.lower()
    subject_lower = subject.lower()

    # Extract text from document
    doc_text = extract_text_from_file(file_path)

    # If no text could be extracted, do a soft pass (cannot verify)
    if not doc_text:
        return {
            'valid': True,
            'confidence': 40,
            'matched_keywords': [],
            'message': '⚠️ Document accepted (text could not be extracted for AI analysis).',
            'details': 'File type may not support text extraction. Manual review recommended.',
        }

    # Check rejection signals
    for signal in REJECTION_SIGNALS:
        if signal in doc_text:
            return {
                'valid': False,
                'confidence': 95,
                'matched_keywords': [signal],
                'message': '❌ Inappropriate document detected.',
                'details': f'Document contains flagged content: "{signal}". Please upload the correct document.',
            }

    # Find best matching category keywords
    keywords = _get_keywords(category_lower)
    subject_keywords = _tokenize(subject_lower)
    all_keywords = list(set(keywords + subject_keywords))

    matched = [kw for kw in all_keywords if kw in doc_text]
    match_ratio = len(matched) / max(len(all_keywords), 1)
    confidence = min(int(match_ratio * 100) + _fuzzy_bonus(doc_text, subject_lower), 100)

    if confidence >= 50:
        return {
            'valid': True,
            'confidence': confidence,
            'matched_keywords': matched[:10],
            'message': f'✅ Document appears relevant to the request ({confidence}% match).',
            'details': f'Matched keywords: {", ".join(matched[:8]) or "N/A"}',
        }
    elif confidence >= 25:
        return {
            'valid': True,
            'confidence': confidence,
            'matched_keywords': matched[:10],
            'message': f'⚠️ Document partially matches ({confidence}%). Accepted with low confidence.',
            'details': 'Manual review recommended. Matched: ' + ', '.join(matched[:6] or ['(none)']),
        }
    else:
        return {
            'valid': False,
            'confidence': confidence,
            'matched_keywords': matched,
            'message': f'❌ Document does not appear relevant to "{category}" ({confidence}% match).',
            'details': (
                'The uploaded document does not match the expected content for this request type. '
                'Please upload the correct supporting document.'
            ),
        }


def _get_keywords(category_lower: str) -> list:
    """Find keyword list for the given category string."""
    for cat_key, keywords in CATEGORY_KEYWORDS.items():
        if cat_key in category_lower or _similarity(cat_key, category_lower) > 0.6:
            return keywords
    # fallback: return generic finance/banking keywords
    return ['bank', 'trust', 'approval', 'request', 'document', 'form', 'letter', 'certificate']


def _tokenize(text: str) -> list:
    """Split subject into meaningful tokens (≥4 chars)."""
    return [w for w in re.findall(r'\b[a-z]{4,}\b', text.lower()) if w not in _STOPWORDS]


def _fuzzy_bonus(doc_text: str, subject: str) -> int:
    """Extra confidence if document text is similar to the subject."""
    ratio = SequenceMatcher(None, doc_text[:500], subject).ratio()
    return int(ratio * 20)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


_STOPWORDS = {
    'the','and','for','this','that','with','from','have','will','been',
    'your','their','they','what','when','where','which','while','should',
    'request','approval','attach','please','document','form','bank',
}


# ─── Quick API ────────────────────────────────────────────────────────────────

def quick_validate(uploaded_file, category: str, subject: str) -> dict:
    """
    Convenience wrapper: saves Django InMemoryUploadedFile to a temp path,
    runs validate_document(), cleans up.
    """
    import tempfile, shutil
    ext = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name
    try:
        result = validate_document(tmp_path, category, subject)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    return result
