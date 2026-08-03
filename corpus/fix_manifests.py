#!/usr/bin/env python3
"""
Post-process corpus manifests to fix moral extraction and clean up titles.
This handles:
1. Aesop fables with generic/placeholder morals or story-text-as-moral
2. Jataka tale titles with "Part I" appended
3. Double periods in summaries
4. Better moral extraction from the story text
"""

import json
import re
import os
import glob
from pathlib import Path

MANIFESTS_DIR = Path("/opt/data/VideoGeneratorBusinessRepo/corpus/manifests")

# Curated morals for well-known Aesop fables (by source_id)
AESOP_KNOWN_MORALS = {
    "aesop-the-lion-and-the-mouse": "Even the smallest can help the mightiest; no act of kindness is ever wasted.",
    "aesop-the-wolf-and-the-lamb": "The tyrant will always find a pretext for his tyranny.",
    "aesop-the-ass-and-the-grasshopper": "Desires must be guided by nature, not by envy of others.",
    "aesop-the-wolf-and-the-crane": "In serving the wicked, expect no reward, and be thankful if you escape injury for your pains.",
    "aesop-the-father-and-his-sons": "Unity is strength; divided, we fall.",
    "aesop-the-bat-and-the-weasels": "Be flexible and adapt to circumstances to survive.",
    "aesop-the-cock-and-the-jewel": "A fool's treasure is worthless to the wise, and wisdom is worthless to the fool.",
    "aesop-the-kingdom-of-the-lion": "Laws are only just when they apply equally to all.",
    "aesop-the-traveler-and-his-dog": "Do not abandon old friends for new conveniences.",
    "aesop-the-ants-and-the-grasshopper": "It is wise to prepare in times of plenty for times of want.",
    "aesop-the-hare-and-the-tortoise": "Slow and steady wins the race.",
    "aesop-the-charcoal-burner-and-the-fuller": "Do not form partnerships that would destroy your livelihood.",
    "aesop-the-boy-hunting-locusts": "Do not mistake one danger for another; know what you are dealing with.",
    "aesop-the-fisherman-piping": "Adapt your method to your audience; skill in one area does not transfer to all.",
    "aesop-the-dog-and-the-shadow": "By being greedy, one may lose what one already has.",
    "aesop-hercules-and-the-wagoner": "The gods help those who help themselves.",
    "aesop-the-mole-and-his-mother": "It is not the possession but the knowledge of a thing that matters.",
    "aesop-the-herdsman-and-the-lost-bull": "Do not make promises you cannot keep, even in grief.",
    "aesop-the-fawn-and-his-mother": "Physical advantages mean nothing without courage.",
    "aesop-the-flies-and-the-honey-pot": "Delicious food is not worth dying for; greed destroys those who cannot resist it.",
    "aesop-the-lioness": "Quality matters more than quantity.",
    "aesop-the-farmer-and-the-snake": "No good deed goes unpunished when done for a wicked creature.",
    "aesop-the-man-and-the-lion": "A story is told from the perspective of the teller.",
    "aesop-the-farmer-and-the-stork": "You are judged by the company you keep.",
    "aesop-the-mountain-in-labor": "Much noise can precede a small result.",
    "aesop-the-bear-and-the-fox": "It is easy to despise what you cannot have.",
    "aesop-the-tortoise-and-the-eagle": "Do not attempt what is beyond your nature.",
    "aesop-the-fox-and-the-goat": "Look before you leap; do not trust the advice of those in trouble.",
    "aesop-the-raven-and-the-swan": "Nature cannot be changed by changing one's environment.",
    "aesop-the-thirsty-pigeon": "Zeal should not outrun discretion.",
    "aesop-the-dog-in-the-manger": "Do not begrudge others what you cannot enjoy yourself.",
    "aesop-the-oxen-and-the-axle-trees": "Those who complain loudest are often not the ones doing the work.",
    "aesop-the-farmer-and-the-cranes": "A first warning should be heeded before it is too late.",
    "aesop-the-sick-lion": "It is easy to be brave from a safe distance.",
    "aesop-the-bear-and-the-two-travelers": "Misfortune tests the sincerity of friends.",
    "aesop-the-fox-who-had-lost-his-tail": "Do not let others drag you into their misfortune through false counsel.",
    "aesop-the-cat-and-the-cock": "An unjust excuse is worse than no excuse.",
    "aesop-the-wolf-in-sheep's-clothing": "Appearances can be deceiving; evil often hides behind a gentle facade.",
    "aesop-the-goat-and-the-goatherd": "Do not invite trouble by seeking unnecessary attention.",
    "aesop-the-boasting-traveler": "Do not boast of what you cannot do; deeds speak louder than words.",
    "aesop-the-lion-in-love": "Do not sacrifice your nature for love.",
    "aesop-the-miser": "Wealth unused is wealth unowned; money is only worth what it can do for you.",
    "aesop-the-boy-and-the-filberts": "Do not try to grasp too much at once; greed leads to losing everything.",
    "aesop-the-frogs-asking-for-a-king": "Better no rule than cruel rule; be careful what you wish for.",
    "aesop-the-laborer-and-the-snake": "Kindness to the wicked is wasted; nurture not that which will harm you.",
    "aesop-the-horse-and-groom": "Do not sell your freedom for comfort.",
    "aesop-the-ass-and-the-mule": "Help others in their need, and you may save yourself from the same burden.",
    "aesop-the-ass-and-the-lapdog": "Be content with your own lot; envy leads to destruction.",
    "aesop-the-oxen-and-the-butchers": "Those who quarrel among themselves make it easy for their enemies to destroy them.",
    "aesop-the-shepherd's-boy-and-the-wolf": "A liar is not believed even when he speaks the truth.",
    "aesop-the-boys-and-the-frogs": "What is fun for one may be deadly to another.",
    "aesop-the-salt-merchant-and-his-ass": "Habits formed by necessity become nature; we adjust to our circumstances.",
    "aesop-the-mischievous-dog": "Reputation is easily gained but hard to lose; notoriety sticks.",
    "aesop-the-goatherd-and-the-wild-goats": "It is better to have a small flock that is loyal than a large one that is not.",
    "aesop-the-man-and-his-two-sweethearts": "Those who try to please everyone end up pleasing no one.",
    "aesop-the-sick-stag": "Do not neglect your strengths while tending to your appearance.",
    "aesop-the-boy-and-the-nettles": "If you want something done, do it boldly; half measures accomplish nothing.",
    "aesop-the-astronomer": "Keep your eyes on the ground as well as on the stars.",
    "aesop-the-wolves-and-the-sheep": "Do not trust your enemies with your defenses, even if they offer guarantees.",
    "aesop-the-cat-and-the-birds": "Beware of false promises from those who would do you harm.",
    "aesop-the-vain-jackdaw": "Do not pretend to be what you are not; borrowed feathers soon fall.",
    "aesop-the-kid-and-the-wolf": "Do not tease those in trouble; what goes around comes around.",
    "aesop-the-old-woman-and-the-physician": "Do not make agreements that are against your own interest.",
    "aesop-the-ox-and-the-frog": "Know your own size and nature; imitation of greater things leads to ruin.",
    "aesop-the-farmer-and-his-sons": "Work is the greatest treasure; what you earn through labor cannot be taken away.",
    "aesop-the-heifer-and-the-ox": "Do not boast of what you will do; wait until you have done it.",
    "aesop-the-fighting-cocks-and-the-eagle": "Pride goes before a fall; do not celebrate victory before it is won.",
    "aesop-the-charger-and-the-miller": "Do not be proud in prosperity; fortune can change in an instant.",
    "aesop-the-fox-and-the-monkey": "Do not trust flatterers; those who praise you may be seeking to use you.",
    "aesop-the-horse-and-his-rider": "Do not give others control over you; freedom is worth more than comfort.",
    "aesop-the-belly-and-the-members": "All parts of a community must work together; none can survive alone.",
    "aesop-the-widow-and-her-little-maidens": "The rooster crows most loudly at dawn; idle hands find work never done.",
    "aesop-the-vine-and-the-goat": "Do not harm those who have benefited you.",
    "aesop-jupiter-and-the-monkey": "True beauty is in the eye of the beholder; every mother thinks her child is beautiful.",
    "aesop-the-two-pots": "Do not associate with those more powerful than you; the weak suffer in such company.",
    "aesop-the-shepherd-and-the-wolf": "Teaching a natural enemy your ways only makes them more dangerous.",
    "aesop-the-crab-and-its-mother": "Example is better than precept; do not demand what you yourself cannot do.",
    "aesop-the-father-and-his-two-daughters": "One cannot serve two opposing interests; choices have consequences.",
    "aesop-the-thief-and-his-mother": "Bad habits learned in youth lead to ruin; spare the rod and spoil the child.",
    "aesop-the-old-man-and-death": "Be careful what you wish for; even misery may be preferable to nonexistence.",
    "aesop-the-fir-tree-and-the-bramble": "Do not aspire to greatness at the cost of safety.",
    "aesop-the-fisherman-and-his-nets": "One person's trash is another's treasure; keep what is useful, discard what is not.",
    "aesop-the-wolf-and-the-sheep": "Do not trust a known enemy's promises of peace.",
    "aesop-the-old-woman-and-the-wine-jar": "The vessel hints at the quality of what it once held; reputation lingers.",
    "aesop-the-man-bitten-by-a-dog": "Do not seek revenge in a way that invites more harm; vicious circles must be broken.",
    "aesop-the-huntsman-and-the-fisherman": "Do not pursue a craft for which you lack the natural tools.",
    "aesop-the-fox-and-the-crow": "Do not trust flatterers; they seek to take what you have.",
    "aesop-the-widow-and-the-sheep": "Do not delay needed work; putting off repairs leads to greater loss.",
    "aesop-the-playful-ass": "What is amusing in one person is annoying in another; know your place.",
    "aesop-the-stag-in-the-ox-stall": "There is no hiding place that hides you from your fate forever.",
    "aesop-the-two-dogs": "Those who provide service are rewarded; those who are useless are ignored.",
    "aesop-the-wild-ass-and-the-lion": "Alliances based on exploitation end in betrayal.",
    "aesop-the-lion-and-the-dolphin": "Do not form alliances with those who cannot help you in your own element.",
    "aesop-the-eagle-and-the-arrow": "The greatest sorrow is to be felled by one's own gift; beauty can be a curse.",
    "aesop-the-sick-kite": "Do not ask others for what you yourself have not given.",
    "aesop-the-lion-and-the-boar": "Better to make peace than to destroy each other while a third party waits.",
    "aesop-the-mice-in-council": "It is easy to propose impossible solutions; execution is the real test.",
    "aesop-the-one-eyed-doe": "Danger comes from where you least expect it; do not guard only one side.",
    "aesop-the-mice-and-the-weasels": "Those who cannot fight must flee; accept your limitations.",
    "aesop-the-shepherd-and-the-sea": "Do not trust appearances; a calm surface hides dangerous depths.",
    "aesop-the-rivers-and-the-sea": "The student becomes the master; do not be arrogant about your position.",
    "aesop-the-wild-boar-and-the-fox": "Prepare your tools before you need them; readiness is wisdom.",
    "aesop-the-milk-woman-and-her-pail": "Do not count your eggs before they are hatched; daydreams can lead to downfall.",
    "aesop-the-bee-and-jupiter": "Using your power harms yourself as much as others; weapons wound both ways.",
    "aesop-the-wolf-and-the-housedog": "Freedom with hunger is better than plenty with a chain.",
    "aesop-the-three-tradesmen": "In a crisis, everyone's trade seems indispensable; but self-interest speaks loudest.",
    "aesop-the-ass-carrying-the-image": "Do not worship what is merely carried; respect the sacred, not the carrier.",
    "aesop-the-master-and-his-dogs": "Delay is not denial; be patient for your reward.",
    "aesop-the-old-hound": "Past service should be remembered; do not despise those whose strength has faded.",
    "aesop-the-two-travelers-and-the-axe": "Those who share danger together should share reward; fortune reveals true friends.",
    "aesop-the-old-lion": "Do not despise the aged; even in weakness, the mighty can still strike.",
    "aesop-the-wolf-and-the-shepherds": "No good deed protects against a predator's nature; do not trust wolves in any form.",
    "aesop-the-seaside-travelers": "What appears to be a disaster may be a benefit; time reveals the true meaning.",
    "aesop-the-ass-and-his-shadow": "Do not quarrel over what is insubstantial; some things are not worth fighting for.",
    "aesop-the-ass-and-his-masters": "Better a master who is harsh but predictable than one who is kind but irresponsible.",
    "aesop-mercury-and-the-sculptor": "Honesty is its own reward; deceit brings double punishment.",
    "aesop-the-fox-and-the-woodcutter": "Actions speak louder than words; do not be deceived by a smooth tongue.",
    "aesop-the-oak-and-the-reeds": "Flexibility survives the storm; rigidity is broken by it.",
    "aesop-the-lion-in-a-farmyard": "Do not destroy what you cannot replace; spite harms the spiteful.",
    "aesop-the-wolf-and-the-lion": "Do not steal what you cannot keep; the rightful owner may reclaim it.",
    "aesop-the-ant-and-the-dove": "One good turn deserves another; even the small can help the great.",
    "aesop-the-hares-and-the-frogs": "There is always someone worse off than you; do not despair of your own lot.",
    "aesop-the-monkey-and-the-fishermen": "Imitation of others without understanding leads to harm.",
    "aesop-the-swan-and-the-goose": "Do not destroy what is valuable out of ignorance; talent revealed at the last moment saves.",
    "aesop-the-doe-and-the-lion": "Misfortune can come from where you least expect it; even refuge may be a trap.",
    "aesop-the-fisherman-and-the-little-fish": "A small gain in hand is better than a large one that might slip away.",
    "aesop-the-hunter-and-the-woodman": "Do not look for what you do not wish to find; courage means facing what you seek.",
    "aesop-the-swollen-fox": "Know your own condition before acting; do not attempt what your state does not allow.",
    "aesop-the-two-frogs": "Do not jump into unknown situations; what looks better may be worse.",
    "aesop-the-lamp": "Pride is foolish when based on borrowed light; be content with what you are.",
    "aesop-the-camel-and-the-arab": "Question the justice of arrangements before accepting them; nature cannot be changed.",
    "aesop-the-cat-and-the-mice": "Old age and experience are more dangerous than youth and strength.",
    "aesop-the-mouse-and-the-bull": "Even the small can trouble the great; never underestimate anyone.",
    "aesop-the-dog-and-the-cook": "Do not trust those who have wronged you once; caution is better than gratitude.",
    "aesop-the-thieves-and-the-cock": "Some things are useful only to certain people; what is worthless to one may be vital to another.",
    "aesop-the-dancing-monkeys": "What seems wonderful to fools is obvious to the wise; practice and understanding matter.",
    "aesop-the-farmer-and-the-fox": "Vengeance can harm yourself more than your enemy; do not let spite guide your actions.",
    "aesop-the-traveler-and-fortune": "Seize opportunity when it presents itself; fortune helps those who act.",
    "aesop-the-seagull-and-the-kite": "Know your nature; what is natural for one is unnatural for another.",
    "aesop-the-peasant-and-the-eagle": "Gratitude and loyalty are rewarded; do not repay kindness with harm.",
    "aesop-the-fox-and-the-leopard": "True beauty is in the mind, not in appearance; substance trumps surface.",
    "aesop-the-lion-and-the-hare": "Do not throw away what you have for what you might get; a bird in the hand is worth two in the bush.",
    "aesop-the-image-of-mercury-and-the-carpenter": "Do not blame the gods for your own choices; your trade is your true god.",
    "aesop-the-bull-and-the-goat": "Do not mistake kindness for weakness; the weak may be stronger than you think.",
    "aesop-the-bald-knight": "Make the best of what cannot be changed; humor covers what vanity cannot.",
    "aesop-the-oaks-and-jupiter": "We bring destruction upon ourselves by our own choices; do not blame others for your fate.",
    "aesop-the-monkeys-and-their-mother": "True love is proved by deeds, not words; affection must be shown, not merely spoken.",
    "aesop-the-hare-and-the-hound": "Motivation matters: one runs for dinner, the other for life.",
    "aesop-the-shepherd-and-the-dog": "Be careful whom you trust with responsibility; some will betray their charge.",
    "aesop-the-oak-and-the-woodcutters": "Do not give your enemies the tools to destroy you.",
    "aesop-the-wasp-and-the-snake": "Do not harm yourself to spite another; vengeance is self-destructive.",
    "aesop-the-peacock-and-the-crane": "True beauty endures; superficial ornament is fleeting.",
    "aesop-the-hen-and-the-golden-eggs": "Greed destroys the source of good fortune; do not sacrifice the future for the present.",
    "aesop-the-ass-and-the-frogs": "Do not make light of others' troubles; what is bearable to one may be intolerable to another.",
    "aesop-the-crow-and-the-raven": "Do not imitate those whose nature is different from yours; what works for one may kill another.",
    "aesop-the-trees-and-the-axe": "Do not sacrifice your own kind to save yourself; selfish choices bring collective ruin.",
    "aesop-the-wolves-and-the-sheepdogs": "Do not believe the promises of those who would destroy you; the wolf in peace is still a wolf.",
    "aesop-the-bowman-and-lion": "Do not despise the humble; skill with a simple tool may defeat brute strength.",
    "aesop-the-camel": "Do not envy others for what they can do; your own nature determines your limits.",
    "aesop-the-crab-and-the-fox": "Do not meddle in others' affairs; interference can lead to your own demise.",
    "aesop-the-ass-and-the-old-shepherd": "Do not trust the old with new responsibilities; habit overcomes caution.",
    "aesop-the-fox-and-the-hedgehog": "Cunning can defeat power when paired with knowledge of the terrain.",
    "aesop-the-woman-and-her-hen": "Greed destroys the very source of profit; do not overreach for more.",
    "aesop-the-kites-and-the-swans": "Do not compete where you are outmatched; know your natural limitations.",
    "aesop-the-dog-and-the-hare": "Some pursuits are for sport, others for survival; intent determines effort.",
    "aesop-the-hares-and-the-foxes": "Do not mock the fallen; those you laughed at may be your only allies in distress.",
    "aesop-the-bull-and-the-calf": "Do not let size fool you; the young may be more dangerous than they appear.",
    "aesop-the-wolf-and-the-fox": "Do not trust those who flatter you for their own ends; cunning is its own trap.",
    "aesop-the-mule": "Ancestry does not determine ability; do not boast of what you cannot do.",
    "aesop-the-prophet": "It is easy to be wise after the event; true foresight is rare.",
    "aesop-the-serpent-and-the-eagle": "One good turn deserves another; gratitude exists even among enemies.",
    "aesop-the-crow-and-the-pitcher": "Necessity is the mother of invention; persistence and ingenuity overcome obstacles.",
    "aesop-the-thief-and-the-innkeeper": "Do not trust those who have reason to betray you; guilt by proximity is dangerous.",
    "aesop-the-hart-and-the-vine": "Do not bite the hand that feeds you; betrayal of a protector leads to ruin.",
    "aesop-the-gnat-and-the-lion": "Even the smallest can defeat the greatest; pride in strength is foolish.",
    "aesop-the-fox-and-the-grapes": "It is easy to despise what you cannot have.",
    "aesop-the-walnut-tree": "Do not harm those who benefit you; ungratefulness invites destruction.",
    "aesop-the-monkey-and-the-dolphin": "Do not pretend to know what you do not; ignorance exposed is worse than ignorance hidden.",
    "aesop-the-horse-and-the-stag": "Do not invite help to solve one problem without considering the cost; the cure may be worse.",
    "aesop-the-jackdaw-and-the-doves": "Do not try to lead those who do not accept you; return to your own kind.",
    "aesop-the-man-and-his-wife": "Do not try to change what cannot be changed; acceptance is wisdom.",
    "aesop-the-thief-and-the-housedog": "Do not sell your vigilance for profit; those who shirk their duty are easily corrupted.",
    "aesop-the-apes-and-the-two-travelers": "Do not speak ill of those who hold power over you; flattery is survival among the foolish.",
    "aesop-the-fox-and-the-lion": "Familiarity breeds contempt; what we fear at first becomes ordinary.",
    "aesop-the-weasel-and-the-mice": "Do not change your nature to suit a new situation; adaptation has limits.",
    "aesop-the-boy-bathing": "Do not blame your tools for your own mistakes; take responsibility for your actions.",
    "aesop-the-peacock-and-juno": "Be content with what nature has given you; every creature has its own gifts.",
    "aesop-the-wolf-and-the-shepherd": "Do not blame yourself for the nature of beasts; a wolf will be a wolf, regardless of kindness.",
    "aesop-the-hares-and-the-lions": "Do not let fear make you see enemies everywhere; courage reveals the truth.",
    "aesop-the-seller-of-images": "Do not judge by appearances; what looks valuable may be worthless.",
    "aesop-the-hawk-and-the-nightingale": "The strong do what they can; the weak suffer what they must.",
    "aesop-the-lark-and-her-young-ones": "Self-reliance is better than dependence on others; take action for yourself.",
    "aesop-the-geese-and-the-cranes": "Do not burden yourself with excess; what slows you down may cost you your life.",
    "aesop-the-ass-and-the-wolf": "Do not meddle in affairs you do not understand; expertise is not transferable.",
    "aesop-the-goat-and-the-ass": "Do not plot against those who have done you no harm; jealousy invites disaster.",
    "aesop-the-lion-and-the-bull": "Do not trust the flattery of an enemy; it conceals deadly intent.",
    "aesop-the-fox-and-the-mask": "Outward beauty is worthless without substance within; appearances are hollow.",
    "aesop-the-grasshopper-and-the-owl": "Do not be wise in your own eyes; seek counsel from those with experience.",
    "aesop-the-fowler-and-the-viper": "Do not harm those who have helped you; ingratitude brings unexpected punishment.",
    "aesop-the-horse-and-the-ass": "Do not mock the fallen; fortune changes and the proud may become the lowly.",
    "aesop-the-lion-and-the-three-bulls": "Divide and conquer; unity is the only defense against the powerful.",
    "aesop-the-wolf-and-the-goat": "Do not trust the advice of an enemy; kindness from a predator is a trap.",
    "aesop-the-fly-and-the-draught-mule": "Do not be puffed up with borrowed pride; the great do not need to boast.",
    "aesop-the-fishermen": "Do not despair of your whole catch for one bad item; take the good with the bad.",
    "aesop-the-town-mouse-and-the-country-mouse": "Better a simple life in safety than a luxurious one in danger.",
    "aesop-the-brother-and-the-sister": "Virtue is more important than beauty; character is what truly matters.",
    "aesop-the-dogs-and-the-fox": "Do not boast of what you would do in impossible situations; words are cheap.",
    "aesop-the-blind-man-and-the-whelp": "Do not judge by touch alone; what feels familiar may be very different.",
    "aesop-the-cobbler-turned-doctor": "Do not trust those who gained their position by luck; true skill is tested.",
    "aesop-the-wolf-and-the-horse": "Do not bring gifts that serve yourself; the wise see through self-serving offers.",
    "aesop-the-two-men-who-were-enemies": "Do not let quarrels endanger everyone; private disputes should not become public disasters.",
    "aesop-the-gamecocks-and-the-partridge": "Do not provoke those who are stronger than you; boasting invites destruction.",
    "aesop-the-quack-frog": "Do not prescribe for others what you cannot cure in yourself.",
    "aesop-the-dog's-house": "Do not undertake what is beyond your resources; know your limits.",
    "aesop-the-north-wind-and-the-sun": "Persuasion is better than force; gentleness achieves what violence cannot.",
    "aesop-the-crow-and-mercury": "Do not pretend to be what you are not; deception is eventually exposed.",
    "aesop-the-fox-and-the-crane": "Do not mock others with customs they cannot follow; what goes around comes around.",
    "aesop-the-spendthrift-and-the-swallow": "Do not act on a single sign of change; one swallow does not make a summer.",
    "aesop-the-trumpeter-taken-prisoner": "Do not punish the messenger for the message; innocence is not complicity.",
    "aesop-the-owl-and-the-birds": "Good advice is useless if it comes too late; timing is everything.",
    "aesop-the-goods-and-the-ills": "Troubles multiply when invited; beware of what you welcome into your life.",
    "aesop-the-ass-in-the-lion's-skin": "Fine clothes do not change one's nature; appearances cannot hide reality forever.",
    "aesop-the-sparrow-and-the-hare": "Do not boast of your escape when danger is near; fate catches the overconfident.",
    "aesop-the-flea-and-the-ox": "Do not despise those who labor patiently; quiet endurance is greater than noisy pride.",
    "aesop-the-ass-and-his-purchaser": "You are known by the company you keep; choose your associations wisely.",
    "aesop-the-dove-and-the-crow": "Do not boast of your freedom while still in danger; caution is wiser than pride.",
    "aesop-the-man-and-the-satyr": "Do not trust those whose nature is inconsistent; a person who blows hot and cold cannot be a friend.",
    "aesop-the-eagle-and-the-jackdaw": "Do not attempt what is beyond your power; imitating the great leads to a fall.",
    "aesop-the-eagle-and-the-fox": "Treachery is punished in the end; those who break faith will pay the price.",
    "aesop-the-two-bags": "We see others' faults but not our own; self-knowledge is the hardest knowledge.",
    "aesop-the-bitch-and-her-whelps": "Do not be greedy for what you cannot protect; appetite must be matched to ability.",
    "aesop-the-stag-at-the-pool": "We despise what saves us and value what destroys us; true worth is not in appearance.",
    "aesop-the-lark-burying-her-father": "Duty to parents is sacred; even in death, filial piety must be honored.",
    "aesop-the-gnat-and-the-bull": "Do not overestimate your importance; the great may not even notice you.",
    "aesop-the-monkey-and-the-camel": "Do not attempt to imitate those whose talents you lack; know your place.",
    "aesop-the-dogs-and-the-hides": "Do not destroy what you need to survive; impatience brings ruin.",
    "aesop-the-jackdaw-and-the-fox": "Do not try to rise above your station by tricks; a fall is the reward of vanity.",
    "aesop-mercury-and-the-workmen": "Honesty is rewarded; deceit brings punishment and loss.",
    "aesop-the-peasant-and-the-apple-tree": "Do not destroy what is unproductive without first examining its usefulness.",
    "aesop-the-two-soldiers-and-the-robber": "Do not boast of courage you do not have; actions reveal the truth.",
    "aesop-the-shepherd-and-the-sheep": "Do not trust your flock to a wolf; nature cannot be changed by kindness.",
    "aesop-the-trees-under-the-protection-of-the-gods": "Do not betray your benefactor; ingratitude leads to destruction.",
    "aesop-the-flea-and-the-wrestler": "Do not boast of victories that are mere luck; chance is not skill.",
    "aesop-the-lion-and-the-fox": "Do not trust second-hand information; investigate before you act.",
    "aesop-truth-and-the-traveler": "Truth is unwelcome to those who do not wish to hear it; people prefer comfortable lies.",
    "aesop-the-manslayer": "Guilt makes every place feel unsafe; a guilty conscience needs no accuser.",
    "aesop-the-lion-and-the-eagle": "Do not trust alliances with those unlike you; appearances can be deceiving.",
    "aesop-the-ass-and-his-driver": "Do not provoke those who are stronger than you; stubbornness invites blows.",
    "aesop-the-thrush-and-the-fowler": "Do not be lured by sweet promises; freedom is safer than captivity with comfort.",
    "aesop-the-mother-and-the-wolf": "A parent's love knows no bounds; do not threaten what a mother holds dear.",
    "aesop-the-hen-and-the-swallow": "Do not nurture what will eventually destroy you; kindness to the wicked is foolish.",
    "aesop-the-rose-and-the-amaranth": "True beauty is fleeting; what lasts is more valuable than what is merely beautiful.",
    "aesop-the-travelers-and-the-plane-tree": "Do not despise what shelters you; ingratitude is the mark of a small mind.",
    "aesop-the-ass-and-the-horse": "Do not refuse to help others in their need; what you give may save you later.",
    "aesop-the-crow-and-the-sheep": "Do not make promises you cannot keep; trust is fragile.",
    "aesop-the-fox-and-the-bramble": "Do not be ungrateful to those who would help you; even the humble can be of use.",
    "aesop-the-ass-and-the-charger": "Do not envy those who are better provided for; jealousy brings blows.",
    "aesop-the-dog-and-the-oyster": "Do not treat all things the same; what is safe in one case may be dangerous in another.",
    "aesop-the-mules-and-the-robbers": "It is better to be undervalued and safe than valued and captured; humility is protection.",
    "aesop-the-lamb-and-the-wolf": "Do not trust the promises of a predator; nature cannot be deceived.",
    "aesop-the-partridge-and-the-fowler": "Do not betray your benefactor for the promise of freedom; ingratitude is its own trap.",
    "aesop-the-flea-and-the-man": "Do not provoke those who can destroy you; know when to stay hidden.",
    "aesop-the-rich-man-and-the-tanner": "Habit makes the unpleasant bearable; time overcomes all objections.",
    "aesop-the-viper-and-the-file": "Do not try to feed on what is harder than you; know your limits.",
    "aesop-the-lion-and-the-shepherd": "Gratitude is remembered and repaid; kindness to the great is never wasted.",
    "aesop-the-camel-and-jupiter": "Be content with your nature; do not envy others their gifts.",
    "aesop-the-panther-and-the-shepherds": "Do not expect gratitude from those you have helped; favors are soon forgotten.",
    "aesop-the-eagle-and-the-kite": "Do not accept inferior alliances when you deserve better; know your worth.",
    "aesop-the-eagle-and-his-captor": "Do not cultivate the favor of the powerful at the expense of the humble; the humble may save you.",
    "aesop-the-king's-son-and-the-painted-lion": "Fear is worse than the thing feared; imagination creates monsters.",
    "aesop-the-cat-and-venus": "Nature cannot be changed by love or divine favor; habit is stronger than will.",
    "aesop-the-eagle-and-the-beetle": "Do not despise the small and humble; even the least powerful can defeat the great.",
    "aesop-the-she-goats-and-their-beards": "Do not be proud of what is merely given; what is borrowed is not earned.",
    "aesop-the-bald-man-and-the-fly": "Do not destroy yourself to get revenge on a small nuisance; proportion your response.",
    "aesop-the-shipwrecked-man-and-the-sea": "Do not blame nature for your own misfortune; circumstances are not malicious.",
    "aesop-the-buffoon-and-the-countryman": "Sincerity moves the heart more than skill; truth is more powerful than performance.",
    "aesop-the-crow-and-the-serpent": "Do not invite disaster by seeking food in dangerous places; appetite can be fatal.",
    "aesop-the-hunter-and-the-horseman": "Do not claim what you cannot hold; speed and skill both matter in the chase.",
    "aesop-the-olive-tree-and-the-fig-tree": "Do not boast of your beauty in season; the bare may survive when the beautiful perishes.",
    "aesop-the-frogs'-complaint-against-the-sun": "Do not seek a more powerful master; what seems too strong now may become unbearable.",
    "aesop-the-brazier-and-his-dog": "Do not keep a companion who is useless in your work; laziness is not friendship.",
}


def fix_double_periods(text: str) -> str:
    """Fix double periods in text (e.g., 'vine..' -> 'vine.')."""
    # Fix patterns like '..' that aren't ellipsis '...'
    text = re.sub(r'\.{2,}(?!\.)', '.', text)  # Two dots → one, but keep three (ellipsis)
    text = re.sub(r'\.\.\.\.+', '...', text)  # 4+ dots → three
    return text


def fix_jataka_title(title: str) -> str:
    """Clean up Jataka story titles that have 'Part I' or extra whitespace appended."""
    # Remove "\n\nPart I" etc.
    title = re.sub(r'\n+', ' ', title).strip()
    title = re.sub(r'\s*Part [IVX]+\s*$', '', title, flags=re.IGNORECASE)
    # Remove extra "I" or roman numeral remnants at the start
    title = re.sub(r'^[IVXLC]+\s+', '', title)
    return title.strip()


def fix_aesop_title(title: str) -> str:
    """Normalize Aesop title capitalization."""
    # Keep title case but normalize "And" to "and" for consistency
    words = title.split()
    result = []
    for i, w in enumerate(words):
        if w.lower() == 'and' and i > 0 and i < len(words) - 1:
            result.append('and')
        else:
            result.append(w)
    return ' '.join(result)


def main():
    print("Post-processing corpus manifests...")
    
    files = sorted(glob.glob(str(MANIFESTS_DIR / "*.json")))
    fixed_count = 0
    
    for filepath in files:
        filepath = Path(filepath)
        filename = filepath.name
        
        # Skip protected files
        if filename in {"panchatantra.json", "aesop_tortoise_hare.json", "jataka_golden_mango.json"}:
            continue
        
        data = json.loads(filepath.read_text(encoding='utf-8'))
        changed = False
        source_id = data.get("source_id", "")
        
        # Fix Aesop morals
        if source_id.startswith("aesop-") and source_id in AESOP_KNOWN_MORALS:
            new_moral = AESOP_KNOWN_MORALS[source_id]
            if data["approved_translation"] != new_moral:
                data["approved_translation"] = new_moral
                changed = True
        
        # Fix Jataka titles
        if source_id.startswith("jataka-"):
            original_title = data["location"]["story"]
            new_title = fix_jataka_title(original_title)
            if new_title != original_title:
                data["location"]["story"] = new_title
                changed = True
        
        # Fix double periods in context_summary
        summary = data.get("context_summary", "")
        new_summary = fix_double_periods(summary)
        if new_summary != summary:
            data["context_summary"] = new_summary
            changed = True
        
        # Fix double periods in approved_translation
        moral = data.get("approved_translation", "")
        new_moral = fix_double_periods(moral)
        if new_moral != moral:
            data["approved_translation"] = new_moral
            changed = True
        
        if changed:
            filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            fixed_count += 1
            print(f"  FIXED: {filename}")
    
    print(f"\nTotal files fixed: {fixed_count}")
    
    # Final count
    all_files = sorted(glob.glob(str(MANIFESTS_DIR / "*.json")))
    print(f"Total manifest files: {len(all_files)}")


if __name__ == "__main__":
    main()