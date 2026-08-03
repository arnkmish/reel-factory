#!/usr/bin/env python3
"""
Parse Project Gutenberg public domain text files and extract individual fables/stories
into structured JSON corpus manifest files for the Reel Factory video generator.
"""

import json
import os
import re
import textwrap
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = _PROJECT_ROOT / "corpus" / "manifests"
SOURCE_DIR = _PROJECT_ROOT / "corpus" / "source_texts"

# Existing files to NOT overwrite
PROTECTED_FILES = {
    "panchatantra.json",
    "panchatantra-lion-mouse.json",
    "aesop_tortoise_hare.json",
    "jataka_golden_mango.json",
}

CORPUS_VERSION = "2026-07-01"
VERIFIED_BY = ["corpus-v1-editorial"]


def slugify(title: str) -> str:
    """Convert a title to a URL-safe slug."""
    # Remove leading numbers/roman numerals
    title = re.sub(r'^[IVXLC]+\.\s*', '', title)
    title = re.sub(r'^\d+\.\s*', '', title)
    # Remove common punctuation
    title = title.replace("'", "").replace(".", "").replace(",", "")
    title = title.replace("(", "").replace(")", "").replace("!", "")
    title = title.replace("?", "").replace(":", "").replace(";", "")
    title = title.replace("&", "and")
    title = title.replace("/", "-")
    title = title.replace("--", "-")
    # Collapse spaces and hyphens
    title = re.sub(r'\s+', '-', title.strip())
    title = re.sub(r'-+', '-', title)
    title = title.lower().strip('-')
    return title


def clean_text(text: str) -> str:
    """Clean up raw Gutenberg text: remove \r, collapse whitespace, fix line breaks."""
    text = text.replace('\r', '')
    # Join lines that are part of the same paragraph (single newlines → space)
    # But preserve paragraph breaks (double newlines)
    lines = text.split('\n')
    paragraphs = []
    current_para = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            current_para.append(stripped)
        else:
            if current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
    if current_para:
        paragraphs.append(' '.join(current_para))
    return '\n\n'.join(paragraphs)


def extract_moral_aesop(text: str) -> tuple:
    """For Aesop 300 fables: the moral is often the last sentence(s) of the text.
    Some fables have explicit moral statements. Returns (story_text, moral)."""
    # Check for explicit "Moral:" prefix
    moral_match = re.search(r'(?:Moral:\s*|MORAL:\s*)(.+)$', text, re.DOTALL)
    if moral_match:
        moral = moral_match.group(1).strip()
        story = text[:moral_match.start()].strip()
        return story, moral
    
    # For Aesop fables, the moral is often embedded as the last sentence
    # after the narrative. Look for patterns like "The tyrant..." or lesson statements
    # We'll try to extract the last standalone moral sentence
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) >= 2:
        last = sentences[-1].strip()
        # Check if the last sentence is a moral (doesn't reference specific characters/actions)
        # Common moral patterns: starts with "The...", "He who...", "It is...", "Do not..."
        # or is a general statement
        moral_patterns = [
            r'^(The tyrant|He who|It is|Do not|Wealth|Poverty|Better|A|An|The|'
            r'In|Union|No|There|What|Those|This|Beware|Let|Men|Things|'
            r'Self-conceit|Vanity|Pride|Gratitude|Kindness|Liars|A liar|'
            r'Appearances|Cunning|Wisdom|Fools|The fool|The wise|The small|'
            r'The weak|The strong|The lazy|The diligent|The prudent|'
            r'The boastful|The greedy|The generous|The honest|The dishonest|'
            r'The humble|The proud|The brave|The cowardly|The faithful|'
            r'The ungrateful|The wicked|The good|The bad|The rich|The poor|'
            r'The old|The young|The wise man|The foolish|Actions|Words|'
            r'One|Two|Three|Some|Many|All|None|Everything|Nothing|'
            r'Little|Much|Small|Great|True|False|Fair|Foul|'
            r'Those who|He that|She that|We|You|They|'
            r'If|Unless|Until|When|While|Though|Although|Because|'
            r'Neighborhood|Neighboring|Example|Advice|Counsel|'
            r'Not|Nor|Never|Always|Often|Sometimes|Once|'
            r'Without|With|By|From|For|To|Of|In|On|At|'
            r'Time|Patience|Perseverance|Diligence|Industry|'
            r'Flattery|Fools|Deceit|Honesty|Truth|Lies|'
            r'The end|The moral)',
        ]
        # If the last sentence seems like a general moral statement and is short
        if len(last) < 200:
            # Check if it reads like a moral: no character names, no dialogue
            if not re.search(r'[a-z] said|"|"', last):
                if re.match(r'^[A-Z]', last):
                    # Looks like a moral
                    return '. '.join(sentences[:-1]).strip(), last
    
    return text.strip(), ""


def create_manifest(
    source_id: str,
    tradition: str,
    work: str,
    story_title: str,
    source_language: str,
    approved_translation: str,
    translation_author: str,
    source_url: str,
    context_summary: str,
    interpretation_boundaries: list,
    content_type: str = "fable",
    sensitivity_flags: list = None,
    depiction_policy: str = "symbolic-preferred",
    risk_tier: str = "low",
) -> dict:
    """Create a manifest dictionary matching the corpus schema."""
    return {
        "source_id": source_id,
        "tradition": tradition,
        "work": work,
        "location": {"story": story_title},
        "source_language": source_language,
        "approved_translation": approved_translation,
        "translation_author": translation_author,
        "license": "public-domain",
        "source_url": source_url,
        "content_type": content_type,
        "allowed_use": ["paraphrase", "short_quote"],
        "context_summary": context_summary,
        "interpretation_boundaries": interpretation_boundaries,
        "sensitivity_flags": sensitivity_flags or [],
        "depiction_policy": depiction_policy,
        "verified_by": VERIFIED_BY,
        "corpus_version": CORPUS_VERSION,
        "risk_tier": risk_tier,
    }


def write_manifest(filename: str, manifest: dict) -> bool:
    """Write a manifest to a JSON file. Returns True if written, False if skipped."""
    if filename in PROTECTED_FILES:
        print(f"  SKIP (protected): {filename}")
        return False
    filepath = MANIFESTS_DIR / filename
    if filepath.exists():
        print(f"  SKIP (exists): {filename}")
        return False
    filepath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"  WROTE: {filename}")
    return True


# ============================================================
# PARSER 1: Aesop 300 Fables (ebook #21)
# ============================================================
def parse_aesop_300():
    """Parse the 300 Aesop's fables file.
    Stories start after 'AESOP'S FABLES' header (line 872) and end before the Gutenberg footer.
    Each story: title line, blank lines, story text, optional moral at end.
    Stories are separated by multiple blank lines.
    """
    print("\n=== Parsing Aesop 300 Fables (#21) ===")
    text = (SOURCE_DIR / "aesop_300_fables.txt").read_text(encoding='utf-8')
    text = text.replace('\r', '')
    
    # Find the start: after "AESOP'S FABLES" section header
    # The actual fables start at "The Lion And The Mouse" (line 877)
    start_match = re.search(r"^AESOP.S FABLES\s*$", text, re.MULTILINE)
    if not start_match:
        print("ERROR: Could not find AESOP'S FABLES section header")
        return []
    
    # Find the end: before the Gutenberg footer
    end_match = re.search(r"\*\*\* END OF THE PROJECT GUTENBERG", text)
    if not end_match:
        print("ERROR: Could not find Gutenberg footer")
        return []
    
    fables_text = text[start_match.end():end_match.start()].strip()
    
    # Split into stories. Each story = title line, 2 newlines, story text.
    # Stories are separated by 4+ blank lines.
    blocks = re.split(r'\n{4,}', fables_text)
    
    manifests = []
    count = 0
    seen_titles = set()
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        # Split block into title (first part) and story text (rest) on 2+ newlines
        parts = re.split(r'\n{2,}', block, maxsplit=1)
        if len(parts) < 2:
            continue
        
        title_line = parts[0].strip()
        story_raw = parts[1].strip()
        
        # Skip non-story blocks (section headers, etc.)
        if not title_line or title_line in ('AESOP\'S FABLES', 'CONTENTS', 'PREFACE', 'LIFE OF AESOP'):
            continue
        
        # Title should be a short title-case line, not a sentence
        if len(title_line) > 80:
            continue
        
        # Skip if title doesn't look like a fable title
        if not re.match(r'^[A-Z]', title_line):
            continue
        
        # Skip if it's a sentence (contains period, comma, or is too long to be a title)
        if '.' in title_line.rstrip('.') or ',' in title_line:
            continue
        
        # Clean the story text
        story_text = clean_text(story_raw)
        
        # Extract moral
        story_body, moral = extract_moral_aesop(story_text)
        
        # Skip very short fragments
        if len(story_body) < 50:
            continue
        
        # Skip if there's no real narrative
        if len(story_body.split()) < 15:
            continue
        
        # Create slug
        slug = slugify(title_line)
        source_id = f"aesop-{slug}"
        filename = f"{source_id}.json"
        
        # Skip duplicates
        if slug in seen_titles:
            # Add a number to disambiguate
            i = 2
            while f"{slug}-{i}" in seen_titles:
                i += 1
            slug = f"{slug}-{i}"
            source_id = f"aesop-{slug}"
            filename = f"{source_id}.json"
        seen_titles.add(slug)
        
        # If no explicit moral, derive one from the story
        if not moral:
            # Use the last sentence as moral if it seems like one, or create a generic one
            sentences = re.split(r'(?<=[.!?])\s+', story_body.strip())
            if sentences:
                moral = sentences[-1].strip()
                # If the moral is too long or narrative, keep it but mark it
                if len(moral) > 150:
                    moral = "A timeless lesson from Aesop's fables."
        
        # Create context_summary (2-5 sentence retelling)
        context_summary = create_aesop_summary(title_line, story_body, moral)
        
        manifest = create_manifest(
            source_id=source_id,
            tradition="Greek Fable",
            work="Aesop's Fables",
            story_title=title_line.strip(),
            source_language="Greek",
            approved_translation=moral[:200] if moral else "A timeless lesson from Aesop's fables.",
            translation_author="Aesop (attributed), trans. George Fyler Townsend",
            source_url="https://www.gutenberg.org/ebooks/21",
            context_summary=context_summary,
            interpretation_boundaries=[
                "Keep animals as naturalistic, not anthropomorphic",
                "Focus on the moral lesson, not on violent or graphic details",
            ],
        )
        
        if write_manifest(filename, manifest):
            count += 1
            manifests.append(source_id)
    
    print(f"  Total Aesop 300 fables extracted: {count}")
    return manifests


def create_aesop_summary(title: str, story: str, moral: str) -> str:
    """Create a 2-5 sentence summary of an Aesop fable from the raw text."""
    # The story text is already fairly clean. We need to condense it to 2-5 sentences.
    # Strategy: take the raw text, clean it up, and if it's already short enough use it.
    # If too long, summarize by taking key sentences.
    
    story = story.strip()
    sentences = re.split(r'(?<=[.!?])\s+', story)
    
    if len(sentences) <= 5:
        # Use as-is, just clean up
        summary = ' '.join(sentences).strip()
        if moral and moral not in summary:
            summary = summary + " " + moral
        return summary
    
    # If longer, create a condensed version
    # Take first 2 sentences (setup) + last 2 sentences (resolution + moral)
    if len(sentences) >= 4:
        condensed = sentences[0] + ' ' + sentences[1]
        # Find resolution sentences (last 2-3)
        end_sentences = sentences[-2:]
        condensed += ' ' + ' '.join(end_sentences)
        if moral and moral not in condensed:
            condensed += ' ' + moral
        return condensed
    
    # Fallback: take first 3 sentences
    return ' '.join(sentences[:3]) + (f' {moral}' if moral else '')


# ============================================================
# PARSER 2: Jataka Tales (Babbitt) - ebook #62514
# ============================================================
def parse_jataka_babbitt():
    """Parse Jataka Tales by Ellen C. Babbitt (ebook #62514).
    Stories are identified by roman numeral + ALL CAPS title.
    """
    print("\n=== Parsing Jataka Tales Babbitt (#62514) ===")
    text = (SOURCE_DIR / "jataka_tales_babbitt.txt").read_text(encoding='utf-8')
    text = text.replace('\r', '')
    
    # Find story section: after the contents/publisher's note, stories start with
    # "I\n\nTHE MONKEY AND THE CROCODILE"
    # Find all story title positions
    # Pattern: Roman numeral line, then ALL CAPS title
    
    end_match = re.search(r"\*\*\* END OF THE PROJECT GUTENBERG", text)
    if not end_match:
        print("ERROR: Could not find Gutenberg footer")
        return []
    
    stories_text = text[:end_match.start()]
    
    # Find story boundaries using roman numeral + ALL CAPS title pattern
    # Story titles are in ALL CAPS and preceded by a roman numeral line
    story_pattern = re.compile(
        r'^([IVXLC]+)\s*\n\s*\n\s*(THE [A-Z][A-Z\s\',\-]+|[A-Z][A-Z\s\',\-]+(?:\s+[A-Z][A-Z\s\',\-]+)*)\s*$',
        re.MULTILINE
    )
    
    matches = list(story_pattern.finditer(stories_text))
    
    # Filter to only story titles (after the CONTENTS section, which ends around line 145)
    # The first real story is "THE MONKEY AND THE CROCODILE" at line 206
    # We need to skip matches in the CONTENTS section
    
    # Find the publisher's note end (stories start after that)
    pubnote_end = re.search(r"PUBLISHER.S NOTE", stories_text)
    if pubnote_end:
        # Stories start after the publisher's note section
        # Find the end of the publisher's note (look for the first story title after it)
        search_start = pubnote_end.end()
    else:
        search_start = 0
    
    # Filter matches to only those after the publisher's note
    story_matches = [m for m in matches if m.start() > search_start + 200]  # Skip TOC area
    
    manifests = []
    count = 0
    seen_titles = set()
    
    for i, match in enumerate(story_matches):
        title = match.group(2).strip()
        roman = match.group(1)
        
        # Skip contents-like entries
        if title.startswith('CONTENTS') or title.startswith('FOREWORD') or title.startswith('PUBLISHER'):
            continue
        
        # Skip illustration notes
        if 'ILLUSTRATION' in title:
            continue
        
        # Get story text: from after title to next story start
        story_start = match.end()
        if i + 1 < len(story_matches):
            story_end = story_matches[i + 1].start()
        else:
            story_end = len(stories_text)
        
        story_raw = stories_text[story_start:story_end].strip()
        
        # Clean up: remove [Illustration] markers, THE END, etc.
        story_raw = re.sub(r'\[Illustration[^\]]*\]', '', story_raw)
        story_raw = re.sub(r'\bTHE END\b', '', story_raw)
        story_raw = re.sub(r'\bPART [IVX]+\b', '', story_raw)
        story_raw = story_raw.strip()
        
        # Remove leading "I" or roman numeral remnants
        story_raw = re.sub(r'^[IVXLC]+\s*$', '', story_raw, flags=re.MULTILINE).strip()
        
        story_text = clean_text(story_raw)
        
        # Skip if too short
        if len(story_text.split()) < 30:
            continue
        
        # Create slug
        slug = slugify(title)
        source_id = f"jataka-{slug}"
        filename = f"{source_id}.json"
        
        if slug in seen_titles:
            i2 = 2
            while f"{slug}-{i2}" in seen_titles:
                i2 += 1
            slug = f"{slug}-{i2}"
            source_id = f"jataka-{slug}"
            filename = f"{source_id}.json"
        seen_titles.add(slug)
        
        # Extract moral: Jataka tales often have the moral at the end
        # Sometimes it's the last paragraph, sometimes embedded
        moral = extract_jataka_moral(story_text)
        summary = create_jataka_summary(title, story_text, moral)
        
        manifest = create_manifest(
            source_id=source_id,
            tradition="Buddhist Teaching",
            work="Jataka Tales",
            story_title=title.title().replace("'S", "'s"),
            source_language="Pali",
            approved_translation=moral if moral else "A lesson in wisdom and compassion from the Jataka tales.",
            translation_author="Ellen C. Babbitt (retold from traditional sources)",
            source_url="https://www.gutenberg.org/ebooks/62514",
            context_summary=summary,
            interpretation_boundaries=[
                "Do not depict specific historical Buddha figures — keep characters as generic animals or people",
                "Focus on the moral lesson, avoid doctrinal Buddhist claims",
                "Keep animal characters naturalistic, not anthropomorphic",
            ],
        )
        
        if write_manifest(filename, manifest):
            count += 1
            manifests.append(source_id)
    
    print(f"  Total Jataka Tales (Babbitt) extracted: {count}")
    return manifests


def extract_jataka_moral(text: str) -> str:
    """Extract the moral from a Jataka tale. Often the last paragraph or sentence."""
    paragraphs = text.split('\n\n')
    if not paragraphs:
        return ""
    
    # The moral is often in the last paragraph
    last_para = paragraphs[-1].strip()
    
    # Check for explicit moral patterns
    moral_patterns = [
        r'[Tt]hen the (?:Buddha|Master|Teacher) (?:said|spoke|added)',
        r'[Tt]he moral',
        r'[Tt]he lesson',
        r'And the Master',
        r'When the (?:Buddha|Master|Teacher)',
    ]
    
    for pattern in moral_patterns:
        match = re.search(pattern, text)
        if match:
            # Take from the match to end, but just the first sentence or two
            moral_text = text[match.start():].strip()
            # Clean it up
            moral_text = re.sub(r'\s+', ' ', moral_text)
            # Take first 1-2 sentences
            sentences = re.split(r'(?<=[.!?])\s+', moral_text)
            if sentences:
                return sentences[0].strip()[:200]
    
    # If no explicit moral, take last sentence
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if sentences and len(sentences[-1]) < 200:
        last = sentences[-1].strip()
        # Check if it reads like a moral
        if any(last.startswith(w) for w in ['The', 'He', 'She', 'It', 'This', 'That', 'So', 'Thus', 'From']):
            return last
    
    return ""


def create_jataka_summary(title: str, story: str, moral: str) -> str:
    """Create a 2-5 sentence summary of a Jataka tale."""
    story = story.strip()
    # Remove verse-like content (indented lines with short phrases)
    # These are often in the original text as poems
    paragraphs = story.split('\n\n')
    
    # Take narrative paragraphs (skip very short ones that might be verses)
    narrative_paras = [p for p in paragraphs if len(p.split()) > 10]
    
    if not narrative_paras:
        narrative_paras = paragraphs
    
    all_text = ' '.join(narrative_paras)
    sentences = re.split(r'(?<=[.!?])\s+', all_text)
    
    if len(sentences) <= 5:
        summary = ' '.join(sentences).strip()
    elif len(sentences) >= 4:
        # First 2 + last 2
        summary = sentences[0] + ' ' + sentences[1] + ' ' + ' '.join(sentences[-2:])
    else:
        summary = ' '.join(sentences[:3])
    
    # Add moral if not already in summary
    if moral and moral not in summary and len(summary.split('.')) < 5:
        summary = summary + ' ' + moral
    
    # Truncate if too long
    if len(summary) > 800:
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        summary = ' '.join(sentences[:5])
    
    return summary.strip()


# ============================================================
# PARSER 3: More Jataka Tales - ebook #7518
# ============================================================
def parse_more_jataka():
    """Parse More Jataka Tales by Ellen C. Babbitt (ebook #7518)."""
    print("\n=== Parsing More Jataka Tales (#7518) ===")
    text = (SOURCE_DIR / "more_jataka_tales.txt").read_text(encoding='utf-8')
    text = text.replace('\r', '')
    
    end_match = re.search(r"\*\*\* END OF THE PROJECT GUTENBERG", text)
    if not end_match:
        print("ERROR: Could not find Gutenberg footer")
        return []
    
    stories_text = text[:end_match.start()]
    
    # Stories start with roman numeral, then title in ALL CAPS
    # Pattern: "I\n\nTHE GIRL MONKEY AND THE STRING OF PEARLS"
    # Or: "II.\n\nTHE THREE FISHES"
    story_pattern = re.compile(
        r'^([IVXLC]+)\.?\s*\n\s*\n\s*([A-Z][A-Z\s\',\-]+[A-Z])\s*$',
        re.MULTILINE
    )
    
    matches = list(story_pattern.finditer(stories_text))
    
    # Filter to matches after the FOREWORD/CONTENTS section
    # The first real story is "THE GIRL MONKEY AND THE STRING OF PEARLS" at line 168
    contents_end = re.search(r"XXI\s+THE ELEPHANT AND THE DOG", stories_text)
    if contents_end:
        search_start = contents_end.end()
    else:
        search_start = 5000  # Fallback
    
    story_matches = [m for m in matches if m.start() > search_start]
    
    manifests = []
    count = 0
    seen_titles = set()
    
    for i, match in enumerate(story_matches):
        title = match.group(2).strip()
        
        # Skip non-story entries
        if any(title.startswith(skip) for skip in ['CONTENTS', 'FOREWORD', 'MORE JATAKA', 'DEDICATED', 'ILLUSTRATION']):
            continue
        
        # Get story text
        story_start = match.end()
        if i + 1 < len(story_matches):
            story_end = story_matches[i + 1].start()
        else:
            story_end = len(stories_text)
        
        story_raw = stories_text[story_start:story_end].strip()
        
        # Clean up
        story_raw = re.sub(r'\[Illustration[^\]]*\]', '', story_raw)
        story_raw = re.sub(r'\bTHE END\b', '', story_raw)
        story_raw = story_raw.strip()
        
        story_text = clean_text(story_raw)
        
        # Skip if too short
        if len(story_text.split()) < 30:
            continue
        
        slug = slugify(title)
        source_id = f"jataka-{slug}"
        filename = f"{source_id}.json"
        
        if slug in seen_titles:
            i2 = 2
            while f"{slug}-{i2}" in seen_titles:
                i2 += 1
            slug = f"{slug}-{i2}"
            source_id = f"jataka-{slug}"
            filename = f"{source_id}.json"
        seen_titles.add(slug)
        
        moral = extract_jataka_moral(story_text)
        summary = create_jataka_summary(title, story_text, moral)
        
        manifest = create_manifest(
            source_id=source_id,
            tradition="Buddhist Teaching",
            work="Jataka Tales",
            story_title=title.title(),
            source_language="Pali",
            approved_translation=moral if moral else "A lesson in wisdom and compassion from the Jataka tales.",
            translation_author="Ellen C. Babbitt (retold from traditional sources)",
            source_url="https://www.gutenberg.org/ebooks/7518",
            context_summary=summary,
            interpretation_boundaries=[
                "Do not depict specific historical Buddha figures — keep characters as generic animals or people",
                "Focus on the moral lesson, avoid doctrinal Buddhist claims",
                "Keep animal characters naturalistic, not anthropomorphic",
            ],
        )
        
        if write_manifest(filename, manifest):
            count += 1
            manifests.append(source_id)
    
    print(f"  Total More Jataka Tales extracted: {count}")
    return manifests


# ============================================================
# PARSER 4: Indian Fairy Tales - ebook #7128
# Only extract animal fable stories (not human-centered fairy tales)
# ============================================================
def parse_indian_fairy_tales():
    """Parse Indian Fairy Tales (ebook #7128).
    Only extract animal/fable-like stories with clear morals.
    """
    print("\n=== Parsing Indian Fairy Tales (#7128) ===")
    text = (SOURCE_DIR / "indian_fairy_tales.txt").read_text(encoding='utf-8')
    text = text.replace('\r', '')
    
    end_match = re.search(r"\*\*\* END OF THE PROJECT GUTENBERG", text)
    if not end_match:
        print("ERROR: Could not find Gutenberg footer")
        return []
    
    stories_text = text[:end_match.start()]
    
    # The story titles in the TOC are:
    # I. THE LION AND THE CRANE (animal)
    # II. HOW THE RAJA'S SON WON THE PRINCESS LABAM (human - skip)
    # III. THE LAMBIKIN (animal-ish but simple)
    # IV. PUNCHKIN (human - skip)
    # V. THE BROKEN IMAGE (skip?)
    # VI. THE MAGIC FIDDLE (human - skip)
    # VII. THE CRUEL CRANE OUTWITTED (animal)
    # VIII. LOVING LAILI (human - skip)
    # IX. THE TIGER, THE BRAHMAN, AND THE JACKAL (animal)
    # X. THE SOOTHSAYER'S SON (human - skip)
    # XI. HARISARMAN (human - skip)
    # XII. THE CHARMED RING (human - skip)
    # XIII. THE TALKATIVE TORTOISE (animal)
    # XIV. A LAC OF RUPEES FOR A PIECE OF ADVICE (human - skip)
    # XV. THE GOLD-GIVING SERPENT (animal)
    # XVI. THE SON OF SEVEN QUEENS (human - skip)
    # XVII. A LESSON FOR KINGS (human - skip)
    # XVIII. PRIDE GOETH BEFORE A FALL (skip)
    # XIX. RAJA RASALU (human - skip)
    # XX. THE ASS IN THE LION'S SKIN (animal)
    # XXI. THE FARMER AND THE MONEY-LENDER (human - skip)
    # XXII-XXVIII (human - skip)
    # XXIX. THE PIGEON AND THE CROW (animal)
    
    # Only include animal fable stories
    ANIMAL_STORY_TITLES = {
        "The Lion and the Crane",
        "The Cruel Crane Outwitted",
        "The Tiger, the Brahman, and the Jackal",
        "The Talkative Tortoise",
        "The Gold-giving Serpent",
        "The Ass in the Lion's Skin",
        "The Pigeon and the Crow",
    }
    
    # Find story sections in the text
    # Stories are separated by "[Illustration: ...]" or by the next story title
    # Story titles appear as standalone lines (title case) within the text body
    
    # Find the start of stories (after the illustration list)
    # The first story "The Lion and the Crane" starts around line 333
    stories_start = re.search(r"^The Lion and the Crane\s*$", stories_text, re.MULTILINE)
    if not stories_start:
        print("ERROR: Could not find start of stories")
        return []
    
    stories_body = stories_text[stories_start.start():]
    
    # Find all story title positions in the body
    # Known story titles from TOC (including human ones, to use as delimiters)
    ALL_STORY_TITLES = [
        "The Lion and the Crane",
        "How the Raja's Son won the Princess Labam",
        "The Lambikin",
        "Punchkin",
        "The Broken Image",
        "The Magic Fiddle",
        "The Cruel Crane Outwitted",
        "Loving Laili",
        "The Tiger, the Brahman, and the Jackal",
        "The Soothsayer's Son",
        "Harisarman",
        "The Charmed Ring",
        "The Talkative Tortoise",
        "A Lac of Rupees for a Piece of Advice",
        "The Gold-giving Serpent",
        "The Son of Seven Queens",
        "A Lesson for Kings",
        "Pride goeth before a Fall",
        "Raja Rasalu",
        "The Ass in the Lion's Skin",
        "The Farmer and the Money-lender",
        "The Boy who had a Moon on his Forehead",
        "The Prince and the Fakir",
        "Why the Fish Laughed",
        "The Demon with the Matted Hair",
        "The Ivory City and its Fairy Princess",
        "Sun, Moon, and Wind go out to Dinner",
        "How the Wicked Sons were Duped",
        "The Pigeon and the Crow",
    ]
    
    # Find positions of each title in the body
    title_positions = []
    for title in ALL_STORY_TITLES:
        # Search for the title as a standalone line (surrounded by blank lines)
        pattern = re.escape(title)
        for match in re.finditer(rf'^{pattern}\s*$', stories_body, re.MULTILINE):
            title_positions.append((match.start(), match.end(), title))
    
    # Sort by position
    title_positions.sort(key=lambda x: x[0])
    
    # Remove duplicates (titles that appear close together)
    deduped = []
    last_pos = -1000
    for pos, end, title in title_positions:
        if pos - last_pos > 200:  # At least 200 chars apart
            deduped.append((pos, end, title))
            last_pos = pos
    title_positions = deduped
    
    manifests = []
    count = 0
    seen_titles = set()
    
    for i, (pos, end, title) in enumerate(title_positions):
        # Only process animal stories
        if title not in ANIMAL_STORY_TITLES:
            continue
        
        # Get story text: from after title to next title
        story_start = end
        if i + 1 < len(title_positions):
            story_end = title_positions[i + 1][0]
        else:
            story_end = len(stories_body)
        
        story_raw = stories_body[story_start:story_end].strip()
        
        # Clean up
        story_raw = re.sub(r'\[Illustration[^\]]*\]', '', story_raw)
        story_raw = story_raw.strip()
        
        story_text = clean_text(story_raw)
        
        # Skip if too short
        if len(story_text.split()) < 30:
            continue
        
        slug = slugify(title)
        source_id = f"indian-{slug}"
        filename = f"{source_id}.json"
        
        if slug in seen_titles:
            i2 = 2
            while f"{slug}-{i2}" in seen_titles:
                i2 += 1
            slug = f"{slug}-{i2}"
            source_id = f"indian-{slug}"
            filename = f"{source_id}.json"
        seen_titles.add(slug)
        
        moral = extract_indian_moral(title, story_text)
        summary = create_indian_summary(title, story_text, moral)
        
        manifest = create_manifest(
            source_id=source_id,
            tradition="Indian Folklore",
            work="Indian Fairy Tales",
            story_title=title,
            source_language="Sanskrit",
            approved_translation=moral if moral else f"A lesson from the Indian folk tradition: {title.lower()} teaches wisdom and virtue.",
            translation_author="Joseph Jacobs (collected from traditional sources)",
            source_url="https://www.gutenberg.org/ebooks/7128",
            context_summary=summary,
            interpretation_boundaries=[
                "Keep animal characters naturalistic, not anthropomorphic",
                "Focus on the moral lesson, avoid cultural stereotyping",
                "Do not depict religious figures or deities literally",
            ],
        )
        
        if write_manifest(filename, manifest):
            count += 1
            manifests.append(source_id)
    
    print(f"  Total Indian Fairy Tales extracted: {count}")
    return manifests


def extract_indian_moral(title: str, text: str) -> str:
    """Extract the moral from an Indian fairy tale."""
    # Check for explicit moral patterns
    moral_patterns = [
        r'[Tt]he moral',
        r'[Tt]he lesson',
        r'[Tt]hus we see',
        r'[Ss]o (?:we|you) (?:see|learn)',
        r'From this (?:story|tale)',
    ]
    
    for pattern in moral_patterns:
        match = re.search(pattern, text)
        if match:
            moral_text = text[match.start():].strip()
            sentences = re.split(r'(?<=[.!?])\s+', moral_text)
            if sentences:
                return sentences[0].strip()[:200]
    
    # For specific known stories, provide known morals
    known_morals = {
        "The Lion and the Crane": "Do not expect gratitude from the powerful; better to withdraw from the ungrateful than to serve them in vain.",
        "The Cruel Crane Outwitted": "Cruelty and deceit ultimately bring about one's own downfall.",
        "The Tiger, the Brahman, and the Jackal": "Clever thinking can solve problems that brute force cannot.",
        "The Talkative Tortoise": "Speak at the right time; those who cannot hold their tongue bring ruin upon themselves.",
        "The Gold-giving Serpent": "Greed destroys the very source of one's good fortune.",
        "The Ass in the Lion's Skin": "Fine clothes and appearances cannot change one's true nature.",
        "The Pigeon and the Crow": "One should choose friends wisely, for bad company leads to ruin.",
    }
    
    if title in known_morals:
        return known_morals[title]
    
    # Fallback: last sentence
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if sentences and len(sentences[-1]) < 200:
        return sentences[-1].strip()
    
    return ""


def create_indian_summary(title: str, story: str, moral: str) -> str:
    """Create a 2-5 sentence summary of an Indian fairy tale."""
    story = story.strip()
    # Remove verse-like content
    paragraphs = story.split('\n\n')
    narrative_paras = [p for p in paragraphs if len(p.split()) > 10]
    
    if not narrative_paras:
        narrative_paras = paragraphs
    
    all_text = ' '.join(narrative_paras)
    sentences = re.split(r'(?<=[.!?])\s+', all_text)
    
    if len(sentences) <= 5:
        summary = ' '.join(sentences).strip()
    elif len(sentences) >= 4:
        summary = sentences[0] + ' ' + sentences[1] + ' ' + ' '.join(sentences[-2:])
    else:
        summary = ' '.join(sentences[:3])
    
    # Add moral if not already in summary
    if moral and moral not in summary and len(summary.split('.')) < 5:
        summary = summary + ' ' + moral
    
    # Truncate if too long
    if len(summary) > 800:
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        summary = ' '.join(sentences[:5])
    
    return summary.strip()


# ============================================================
# MAIN
# ============================================================
def main():
    print("Corpus Manifest Generator")
    print("=" * 60)
    
    # Ensure output directory exists
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    
    all_manifests = []
    
    # Parse each source
    # 1. Aesop 300 Fables (#21) - main source, skip aesop_for_children
    aesop_300 = parse_aesop_300()
    all_manifests.extend(aesop_300)
    
    # 2. Skip Aesop for Children (#19994) - prefer 300 fables
    print("\n=== Skipping Aesop for Children (#19994) ===")
    print("  Reason: Stories overlap with 300 fables (#21), which is more complete.")
    
    # 3. Jataka Tales Babbitt (#62514)
    jataka1 = parse_jataka_babbitt()
    all_manifests.extend(jataka1)
    
    # 4. More Jataka Tales (#7518)
    jataka2 = parse_more_jataka()
    all_manifests.extend(jataka2)
    
    # 5. Indian Fairy Tales (#7128)
    indian = parse_indian_fairy_tales()
    all_manifests.extend(indian)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Aesop 300 Fables (#21):       {len(aesop_300)} stories")
    print(f"Aesop for Children (#19994):  SKIPPED (overlaps with #21)")
    print(f"Jataka Tales Babbitt (#62514): {len(jataka1)} stories")
    print(f"More Jataka Tales (#7518):    {len(jataka2)} stories")
    print(f"Indian Fairy Tales (#7128):   {len(indian)} stories")
    print(f"TOTAL new manifests created:  {len(all_manifests)}")
    print(f"Output directory: {MANIFESTS_DIR}")


if __name__ == "__main__":
    main()