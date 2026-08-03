#!/usr/bin/env python3
"""
Fix Jataka tale morals and title capitalization issues.
"""

import json
import re
import glob
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = _PROJECT_ROOT / "corpus" / "manifests"

# Curated morals for Jataka tales (by source_id)
JATAKA_MORALS = {
    "jataka-the-monkey-and-the-crocodile-part-i": "Cleverness and presence of mind can save you from danger; think before you act.",
    "jataka-how-the-turtle-saved-his-own-life": "True friends do not believe lies told about those they know to be good.",
    "jataka-the-merchant-of-seri": "True value is recognized by those who understand worth; the wise see what others miss.",
    "jataka-the-turtle-who-couldnt-stop-talking": "Know when to remain silent; talking at the wrong time brings disaster.",
    "jataka-the-ox-who-won-the-forfeit": "Patience and endurance in the face of provocation are ultimately rewarded.",
    "jataka-the-sandy-road": "Perseverance through hardship leads to success; do not abandon your journey halfway.",
    "jataka-the-quarrel-of-the-quails": "Unity is strength; quarrels among yourselves make you vulnerable to those who would exploit you.",
    "jataka-the-measure-of-rice": "A true estimate of values matters more than quantity; wisdom is in knowing what is enough.",
    "jataka-the-foolish-timid-rabbit": "Do not panic over imagined dangers; investigate before you flee, for fear is contagious.",
    "jataka-the-wise-and-the-foolish-merchant": "Foresight and preparation save what carelessness loses; the wise plan ahead.",
    "jataka-the-elephant-girly-face": "Kindness and gentle speech win loyalty; harsh words drive friends away.",
    "jataka-the-banyan-deer": "Self-sacrifice for the sake of others is the highest virtue; compassion moves even kings.",
    "jataka-the-princes-and-the-water-sprite": "Courage and courtesy in the face of danger win respect; treat all beings with dignity.",
    "jataka-the-kings-white-elephant": "Patience and loyalty are rewarded; a noble spirit endures hardship without complaint.",
    "jataka-the-ox-who-envied-the-pig": "Do not envy the ignorant their comfort; the burden of responsibility is also a mark of worth.",
    "jataka-grannys-blackie": "Loyalty and gratitude are remembered; do not forget those who cared for you.",
    "jataka-the-crab-and-the-crane": "Cunning and deceit eventually trap the deceiver; beware of false promises in times of need.",
    "jataka-why-the-owl-is-not-king-of-the-birds": "Do not choose leaders based on appearance alone; consult others before deciding.",
    # More Jataka Tales (#7518)
    "jataka-the-girl-monkey-and-the-string-of-pearls": "Cleverness and careful observation can solve problems that force cannot.",
    "jataka-the-three-fishes": "Foresight saves those who plan ahead; the heedless perish while the wise escape.",
    "jataka-the-tricky-wolf-and-the-rats": "Deceit is eventually exposed; the cunning are undone by their own tricks.",
    "jataka-the-woodpecker-turtle-and-deer": "True friendship and cooperation can overcome any danger; friends who work together survive.",
    "jataka-the-golden-goose": "True generosity does not boast; what is given freely is more valuable than gold.",
    "jataka-the-stupid-monkeys": "Do not imitate others without understanding; foolish copying leads to self-harm.",
    "jataka-the-cunning-wolf": "Greed and deception lead to destruction; the trickster is caught in his own trap.",
    "jataka-the-penny-wise-monkey": "Small savings at the cost of great loss is foolish; do not be penny-wise and pound-foolish.",
    "jataka-the-red-bud-tree": "Truth depends on perspective; do not quarrel when each sees only part of the whole.",
    "jataka-the-woodpecker-and-the-lion": "Gratitude should be remembered; do not repay kindness with ingratitude.",
    "jataka-the-otters-and-the-wolf": "Do not trust a mediator who benefits from your dispute; the crafty exploit division.",
    "jataka-how-the-monkey-saved-his-troop": "Quick thinking and courage can save many; a leader acts for the good of all.",
    "jataka-the-hawks-and-their-friends": "Choose friends wisely; true friends stand by you in times of danger.",
    "jataka-the-brave-little-bowman": "Courage is proved by action, not by appearance; the small can be the brave.",
    "jataka-the-foolhardy-wolf": "Do not act rashly against those stronger than you; overconfidence leads to death.",
    "jataka-the-stolen-plow": "Honesty and hard work are their own reward; stolen goods bring no lasting benefit.",
    "jataka-the-lion-in-bad-company": "Bad company corrupts; choose your companions wisely, for they shape your fate.",
    "jataka-the-wise-goat-and-the-wolf": "Wisdom and alertness can outwit brute force; the clever survive where the strong perish.",
    "jataka-prince-wicked-and-the-grateful-animals": "Kindness to animals is rewarded; cruelty brings its own punishment.",
    "jataka-beauty-and-brownie": "Friendship and loyalty transcend differences; true friends care for each other.",
    "jataka-the-elephant-and-the-dog": "True friendship brings joy; separation from a friend causes sorrow that no comfort can ease.",
}

# Fix title capitalization
def fix_title_case(title: str) -> str:
    """Fix title case issues like 'Couldn'T' -> 'Couldn't'."""
    # Fix capital letters after apostrophes
    title = re.sub(r"'([A-Z])", lambda m: "'" + m.group(1).lower(), title)
    return title


def main():
    print("Fixing Jataka tale morals and titles...")
    
    files = sorted(glob.glob(str(MANIFESTS_DIR / "jataka-*.json")))
    fixed_count = 0
    
    for filepath in files:
        filepath = Path(filepath)
        filename = filepath.name
        
        if filename == "jataka_golden_mango.json":
            continue
        
        data = json.loads(filepath.read_text(encoding='utf-8'))
        changed = False
        source_id = data.get("source_id", "")
        
        # Fix moral
        if source_id in JATAKA_MORALS:
            new_moral = JATAKA_MORALS[source_id]
            if data["approved_translation"] != new_moral:
                data["approved_translation"] = new_moral
                changed = True
        
        # Fix title capitalization
        title = data["location"]["story"]
        new_title = fix_title_case(title)
        if new_title != title:
            data["location"]["story"] = new_title
            changed = True
        
        if changed:
            filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            fixed_count += 1
            print(f"  FIXED: {filename}")
    
    print(f"\nTotal Jataka files fixed: {fixed_count}")


if __name__ == "__main__":
    main()