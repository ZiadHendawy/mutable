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
Superseded chains (old → new, both records exist, old one closed out):
- Used to prefer working from an office (valid from 2019) → now strongly prefers fully remote
  (from January 2025, a few months after the Lisbon move)
- Used to be vegetarian (valid from 2016) → now pescatarian (from May 2025) — fish only, still
  consistent with the shellfish allergy
- Used to prefer packed, sightseeing-heavy itineraries (valid from 2019) → now prefers slow
  travel, fewer places per trip (from November 2025, after the Morocco trip below)

Each chain is seeded with backdated `valid_from` values, so the old record's `valid_to` lands on
the new one's `valid_from` and point-in-time questions ("was she vegetarian in 2023?") have a
single correct answer.

Stable (current, no supersede):
- Strongly dislikes early-morning meetings
- Prefers direct, low-context communication over lengthy back-and-forth
- Prefers projects centered on user research over pure visual polish
- Mildly prefers small startups over large companies
- Prefers tea over coffee
- Dislikes cilantro
- Mildly enjoys spicy food
- Prefers small gatherings over large parties
- Dislikes small talk
- Prefers minimalist home decor
- Likes having plants around her living space
- Prefers podcasts over music while working
- Enjoys true-crime documentaries
- Prefers subtitles on, even for English-language shows
- Prefers a window seat on flights
- Prefers boutique hotels over chain hotels
- Prefers strength training over cardio
- Prefers working out in the morning
- Dislikes group fitness classes

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
