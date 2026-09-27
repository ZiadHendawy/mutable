# Eval personas (milestone 3, task 1)

Reference for authoring the actual seed data in later tasks. Both personas are entirely
fictional — no real personal data, per the README's eval contract.

## Tenant A — Maya Chen

The rich persona: ~100 records across facts/preferences/episodes, ~75 gold questions get
authored against this one. 31, grew up in Toronto, moved to Lisbon 2 years ago. Senior Product
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
  European Portuguese (~A2)
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
- Moved Toronto → Lisbon, September 2024
- Started at Nordic Pay, October 2024
- Gave a talk at a design conference in Berlin, March 2025
- Adopted a cat, Biscuit, February 2025
- Friend's wedding in Barcelona, June 2025
- Completed a half-marathon in Lisbon, April 2025
- Trip to Morocco, October 2025 (multi-day — exercises `event_time_end`)
- Visited family in Toronto for the holidays, December 2025

## Tenant B — Jonas Weber

The light persona: ~20–30 records, isolation probes only, no gold questions needed. Deliberately
unrelated to Maya in every dimension — different city, job, age, life details — so that if
isolation ever broke, the leak would be obviously wrong in the eval report, not a subtle
near-miss.

- 45, lives in Munich, civil engineer, two teenage children
- Hobbies: woodworking, prefers classical music, dislikes spicy food
- Drives an electric car
- Renovated his kitchen (completed August 2025)
- Ran a local 10k charity race, May 2025
