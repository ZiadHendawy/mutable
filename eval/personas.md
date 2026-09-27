# Eval personas

Design doc for the eval dataset: who the two personas are and why the data is shaped the way it
is. The records themselves live in `eval/data/<persona>/`. Both personas are entirely fictional
— no real personal data, per the README's eval contract.

## Tenant A — Maya Chen

The rich persona: 100 records across facts/preferences/episodes, and all 75 gold questions. 31, grew up in Toronto, moved to Lisbon 2 years ago. Senior Product
Designer at a fintech startup ("Nordic Pay"), degree in HCI from University of Toronto.

### Facts
Durable, current-tense assertions. Facts have no supersede mechanism in the API (only
preferences do), so anything that has since changed is written as a past-tense fact ("worked
at Studio Loop from 2019 to 2024") rather than as an old version of a current one.

- Identity: born March 14, 1995; grew up in Toronto; Canadian citizen
- Location: lives in Lisbon (since September 2024), renting a two-bedroom apartment in Arroios
  with one room as a home office; holds a Portuguese residence permit for highly qualified
  workers
- Languages: native English, conversational Mandarin (spoken at home growing up), learning
  European Portuguese (passed A2 in June 2026, working toward B1)
- Education: Bachelor of Information, University of Toronto, 2017, HCI specialization
- Career: junior UX designer at Maple Health (Toronto health-tech, 2017–2019) → product
  designer at Studio Loop (Toronto design agency, 2019–2024) → Senior Product Designer at
  Nordic Pay (since October 2024)
- Nordic Pay: fintech startup building payment and invoicing tools for small businesses,
  headquartered in Stockholm with an engineering hub in Lisbon. Maya leads design for
  merchant onboarding, reports to Head of Design Ingrid Larsen (Stockholm), mentors two junior
  designers
- Skills: Figma, interactive prototyping, user research (usability testing, customer
  interviews)
- Relationships: partner Sam (together since 2020, moved to Lisbon together, freelance
  photographer); younger brother Theo (Vancouver, ER nurse); parents Linda and David Chen
  (Toronto); closest friend Priya Nair (Barcelona)
- Health: allergic to shellfish (carries an epinephrine auto-injector); mild seasonal pollen
  allergy — a deliberate near-neighbor for "what is she allergic to?"
- Everyday: gets around Lisbon on an e-bike (fully remote, so no commute); doesn't own a car;
  self-taught acoustic guitar since early 2023; orange tabby cat Biscuit (since February
  2025); volunteers monthly running portfolio reviews at a Lisbon coding bootcamp

### Preferences
`strength` carries polarity: positive = likes/prefers, negative = dislikes ("Dislikes
cilantro" is -0.7).

Superseded chains (old → new, every version exists, old ones closed out at the next one's
`valid_from`):
- Work location: prefers an office with the team (2019) → strongly prefers fully remote
  (January 2025, a few months after the Lisbon move)
- Diet: vegetarian (2016) → pescatarian (May 2025) — fish only, consistent with the shellfish
  allergy
- Travel: packed, sightseeing-heavy itineraries (2019) → slow travel, fewer places per trip
  (November 2025, after the Morocco trip)
- Exercise: running (2021) → strength training over cardio (July 2025, after a knee strain
  following the half-marathon)
- Employer type: established companies (2017) → small startups (June 2024, when she accepted
  Nordic Pay's offer)
- Design tool: Sketch (2017) → Figma (March 2020, when teams went remote and needed real-time
  collaboration)
- Caffeine, three versions: strong black coffee, several a day (2013) → one flat white a day
  (2021) → tea over coffee, mostly green tea (November 2024)
- Reading: physical books (2015) → e-reader (August 2024, left her books behind when moving)

Each chain is seeded with backdated `valid_from` values, so the old record's `valid_to` lands on
the new one's `valid_from` and point-in-time questions ("was she vegetarian in 2023?") have a
single correct answer.

Stable (current, no supersede):
- Work: strongly dislikes early-morning meetings; prefers direct, low-context communication;
  prefers written async updates over status meetings (near-neighbor to the previous one);
  prefers user-research-heavy projects over pure visual polish; prefers dark mode; keeps phone
  notifications off except for family
- Food: dislikes cilantro; mildly enjoys spicy food; prefers cooking at home on weeknights
- Social: prefers small gatherings over large parties; dislikes small talk
- Home: minimalist decor; likes plants around; prefers cats over dogs
- Media: podcasts over music while working; enjoys true-crime documentaries; subtitles on,
  even for English-language shows
- Travel: window seat on flights; boutique hotels over chains
- Fitness: works out in the morning, before work; dislikes group fitness classes

### Episodes
A dated timeline, 2013 → September 2026 (the eval's "now"). Built to exercise three things:
the in-story cause of every preference change (knee strain → strength training, book donation
→ e-reader, Nordic Pay offer → startups); repeated topics where "most recent" matters (two
Toronto visits, two talks, two trips with Sam); and multi-day events via `event_time_end`.

- Education & early career: starts at University of Toronto (Sept 2013); graduates (June
  2017); joins Maple Health (Aug 2017); joins Studio Loop (May 2019)
- 2020–2023: starts dating Sam (Feb 2020); Studio Loop goes remote and switches Sketch → Figma
  (Mar 2020); starts running (Mar 2021); ten-week UX research course (Oct–Dec 2021); packed
  ten-day Portugal trip with Sam — Lisbon, Porto, Sintra, Lagos (Nov 2022); starts guitar
  (Feb 2023); packed twelve-day Japan trip (Aug 2023)
- The move: accepts Nordic Pay's offer (June 2024); donates her books (Aug 2024); last day at
  Studio Loop (Aug 2024); moves to Lisbon with Sam (Sept 2024); starts at Nordic Pay (Oct 2024)
- 2025: goes fully remote and starts Portuguese lessons (Jan); adopts Biscuit (Feb); talk at a
  design conference in Berlin (Mar); Lisbon half-marathon (Apr); knee strain + six weeks of
  physio, stops running (May–June); Priya's wedding in Barcelona (June); slow solo trip
  through Morocco that flips her travel style (Oct); holidays with her parents in Toronto
  (Dec 2025 – Jan 2026)
- 2026: Theo visits Lisbon (Feb); 31st birthday dinner at home (Mar); the onboarding redesign
  she led launches (Apr); slow ten days in the Azores (May); passes the CIPLE A2 Portuguese
  exam (June); Toronto for her dad's 65th (July); Biscuit's dental cleaning (Aug); talk at a
  Lisbon design meetup (Sept)

### Gold questions
75 questions in `eval/data/maya/questions.yaml`, weighted toward the product's differentiator:

| Category | Count | What it checks |
|---|---|---|
| `preference_current` | 10 | Latest version of a chain, every older version in `must_exclude` |
| `preference_historical` | 10 | An older version still retrievable; 7 pinned to an `as_of` date |
| `fact` | 24 | Point lookups, several with two gold records (both allergies, both languages) |
| `preference` | 13 | Stable preferences, including near-neighbors (communication vs async updates) |
| `episode` | 12 | Date lookups, "most recent" (last Toronto visit), multi-record (all talks) |
| `cross_type` | 6 | "Why" questions pairing a preference change with the episode that caused it |

81 of the 100 records are gold for some question; the other 19 are distractors.

## Tenant B — Jonas Weber

The light persona: 28 records, isolation probes only, no gold questions. His *content* is
unrelated to Maya's in every dimension — different city, job, age, life details — so a leak
would be obviously wrong in the eval report, not a subtle near-miss. But his records cover the
*same topics* Maya's questions ask about (where someone lives, their job, allergies, pets,
diet, coffee, flight seats, holidays): a leaked record can only show up in Maya's results if it
would actually rank for her questions, so topic overlap is what gives the isolation probe
teeth.

- Facts: born November 2, 1980; grew up in Regensburg; lives in Munich; Diplom in civil
  engineering from TU Munich (2005); senior civil engineer at Brandt & Huber (bridge
  inspection, since 2010); married to Katrin (chemistry teacher); children Lena (born 2010) and
  Felix (born 2012); allergic to penicillin; beagle named Bruno; drives an electric car; native
  German, good English; woodworking workshop in his garage
- Preferences: one chain — diesel estate cars (2008) → electric (April 2023, when he bought
  his EV); stable: classical music, dislikes spicy food, strong filter coffee, hearty Bavarian
  cooking, lakeside camping holidays, aisle seat, starting work early, large family gatherings
- Episodes: Lake Garda camping holiday (July–Aug 2024); bought the EV (Apr 2023); 10k charity
  race (May 2025); kitchen renovation (June–Aug 2025); 15 years at Brandt & Huber (Sept 2025);
  Isar bridge inspection (Mar 2026)
