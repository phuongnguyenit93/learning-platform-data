# Recording Open Questions, Decisions to Confirm, and Acceptance Criteria

## Lesson Objectives

After this lesson, you will be able to turn ambiguities in business requirements into trackable questions with accountable owners and deadlines; record design decisions along with their rationale and consequences; and write acceptance criteria specific enough to verify whether the data model meets needs.

In data analysis, this documentation prevents turning assumptions into facts, keeps critical choices from living only in verbal discussions, and builds traceability from requirements to models, implementation, and testing.

## 1. Why Record Ambiguities?

Business requirements often begin with statements like:

- Customers can place orders.
- An order contains multiple products.
- The system stores payment history.
- Users can update their contact information.

These statements suggest scope yet fall short for data design. They do not clarify whether customers need accounts, whether an order can ship in multiple deliveries, how failed payments are recorded, or how long contact history must be retained.

If an analyst fills in missing answers unilaterally, the model accumulates unconfirmed assumptions. When the business discovers discrepancies later, the team may have to change relationships, keys, record lifecycles, historical data, or even integrated APIs.

Therefore, every ambiguity must be logged as a trackable item. A good entry shows:

- what is unclear;
- why the answer affects the model or workflow;
- who holds authority to confirm;
- when the answer is needed;
- current status and available evidence;
- which decisions or model elements depend on the answer.

Logging questions does not slow down analysis. It lets the team see which parts can proceed and which parts depend on confirmation.

## 2. Distinguishing Questions, Assumptions, and Decisions

These three types of information are often conflated, yet carry distinct meanings.

| Type | Meaning | How to Handle |
|---|---|---|
| Open question | Insufficient information to conclude | Assign confirmer, deadline, and log impact |
| Assumption | Temporarily treating something as true so analysis can continue | Record rationale, risk, and verification conditions |
| Decision | Choice approved by an authorized party | Record choice, rationale, decision maker, and consequences |

For example: the requirement states "customers can place orders." The team does not yet know whether buyers need an account. That is a **question**. To sketch the model, the team temporarily assumes customers can buy without logging in. That is an **assumption**. After the product owner confirms guest checkout is allowed, the team records that linking an order to an account is optional. That is a **decision**.

Never log an assumption as an approved decision. Without confirmation from an authorized party, the status must reflect that fact.

### 2.1. When Is an Item a Question?

Create a question whenever at least one of these signs appears:

- Requirements use vague words like "fast," "customer," "history," "processed."
- Two stakeholders interpret the same term differently.
- It is unclear whether a relationship is mandatory or optional.
- It is unclear whether an attribute can mutate or must stay immutable over time.
- It is unclear which source is authoritative when data conflicts.
- Multiple design options yield different costs, risks, or behaviors.
- Exception, cancellation, refund, deletion, or archival rules are undescribed.

### 2.2. When Should an Assumption Be Recorded?

Assumptions are helpful when the team must keep moving before an answer arrives. Each assumption should have:

- an identifier;
- the assumed statement;
- rationale for temporary adoption;
- confidence level;
- impact if the assumption proves wrong;
- owner who must confirm;
- when it must be rechecked.

Example: "Tentatively assume product codes are issued by the catalog system and never reused after a product is discontinued." This assumption impacts keys, historical references, and partner data imports.

If an assumption carries high risk, do not use it to lock down hard-to-reverse design choices. Keep that part of the design in a proposed state or build an option that remains changeable later.

### 2.3. When Does Something Become a Decision?

A decision is marked confirmed only when approved by an authorized person or role. The record must state the scope in which the decision applies and its effective date.

Decisions can be revisited when business rules, scale, legal regulations, or workloads change. Revising a decision should create a new version or record linked to the prior decision; never silently overwrite history so readers cannot tell why the model changed.

## 3. How to Write an Actionable Open Question

A good question must be specific, neutral, and aimed at an answer that impacts design.

Instead of writing "Need to clarify customer," split it into focused questions:

- Are buyers required to have a login account?
- Can an organization have multiple people placing orders on its behalf?
- Can one person link multiple accounts?
- Does an order need to keep recipient details independent of the customer profile?

Each question should focus on one issue. If a sentence packs multiple points that could receive different answers, split it into separate entries.

### 3.1. Fields of a Question Log

A **question log** is a list of unresolved questions. Useful fields typically include:

| Field | Content |
|---|---|
| ID | Stable identifier such as `Q-001` |
| Question | Issue to confirm, phrased clearly |
| Context | Requirement, discussion, or scenario prompting the question |
| Impact | Entities, attributes, relationships, rules, or flows affected |
| Priority | Impact severity while unanswered |
| Confirmer | Role or individual with decision authority |
| Due date | When the answer is needed |
| Status | Open, In review, Answered, Deferred, or Rejected |
| Answer / evidence | Confirmed content and reference source |
| Links | Related decision ID, requirement ID, or model element |

A specialized tool is not strictly required. A table in project documentation works fine, provided someone updates it, change history exists, and links connect to decisions.

### 3.2. Example Question Log for a Sales System

The rows below are illustrative examples; unconfirmed answers must not be treated as policies of a real system.

| ID | Open Question | Data Impact | Priority | Confirmer | Example Status |
|---|---|---|---|---|---|
| Q-001 | Can buyers place orders without an account? | Order–Customer/Account link, optionality of account | High | Product owner | Open |
| Q-002 | Can one order be delivered in multiple shipments? | Order–Shipment relationship and delivery lifecycle | High | Warehouse ops | Open |
| Q-003 | Is unit price locked at order creation or payment confirmation? | Price snapshot attributes and effective timing | High | Sales / Accounting | In review |
| Q-004 | Does an order allow partial payments or multiple payment attempts? | Order–Payment relationship, amounts, and statuses | High | Accounting | Open |
| Q-005 | Must old addresses remain retrievable after a customer updates them? | History storage, valid time, and retention | Medium | Customer data owner | Open |

The "impact" column is vital. It helps the confirmer understand why an answer matters and helps engineers know what is blocked waiting on it.

### 3.3. Prioritizing Questions by Risk

Not every question needs immediate resolution. Prioritize based on:

- **Impact severity:** If answered differently, how much does the model change?
- **Likelihood:** How often does this scenario occur?
- **Cost of late change:** Will it require data migration, API changes, or integration rework?
- **Dependency count:** How many other decisions are waiting on this answer?
- **Schedule:** Does it block a design, development, or acceptance milestone?

Questions touching identity, cardinality, history, access control, and lifecycles usually carry high late-change costs. Questions about UI display labels may carry less impact depending on the system.

Use consistent priority levels, such as Critical/High/Medium/Low, and define what each level means within the team. Never slap on priority labels just to create artificial urgency.

## 4. Recording Decisions to Confirm

Once a question is answered, the team must document the choice and its consequences. In data design, decisions typically affect:

- entity boundaries;
- identifiers and keys;
- cardinality and optionality;
- base attributes, derived attributes, and snapshot data;
- how state and history are stored;
- authoritative data sources;
- synchronization and conflict handling;
- storage models or query patterns.

### 4.1. Contents of a Decision Record

A **decision record** should contain the following sections:

1. **ID and title:** Unique code and brief summary of the choice.
2. **Context:** Requirement, issue, or question leading to the decision.
3. **Status:** Proposed, Approved, Rejected, Superseded, or Deferred.
4. **Options:** Choices considered, including keeping the status quo.
5. **Choice:** Selected or proposed option.
6. **Rationale:** Business rules, data, workload, and supporting evidence.
7. **Consequences:** Effects on the model, applications, operations, legacy data, and integrations.
8. **Approver and date:** Who confirmed it and when.
9. **Re-evaluation conditions:** Events or thresholds triggering a review.
10. **Links:** Related question IDs, requirement IDs, model elements, and acceptance criteria.

Recording rejected options and why they failed prevents future readers from re-litigating the exact same debate without context.

### 4.2. Example Decision Record

**D-001 — Separate Login Account from Buyer Profile**

- **Context:** Q-001 asks whether customers can place orders without logging in.
- **Example status:** Proposed, awaiting product owner approval.
- **Option A:** Require every buyer to have an Account.
- **Option B:** Buyer/Customer is a business concept; linking an Account is optional.
- **Proposed choice:** Option B.
- **Rationale:** Supports guest checkout; login identity and purchasing roles have distinct lifecycles.
- **Consequences:** Orders can store buyer contact info directly and reference an Account when present; do not use account ID as the sole identifier for all buyers.
- **Needs confirmation:** Product owner confirms guest checkout policy and profile merge rules when a buyer registers later.
- **Revisit when:** The store switches to a members-only model or customer identification rules change.

This is a proposed decision, not yet an approved decision. In real project documentation, replace the status and choice fields with details confirmed by an authorized party.

### 4.3. Record Consequences, Not Just the Choice

A decision stating only "use UUID" or "pick document database" is not enough for others to understand.

For example, a decision to use UUIDs must clarify:

- Which service generates the UUID?
- Is ID generation required before writing to the database?
- Does the ID appear in public APIs?
- Must a separate human-readable business code be maintained?
- What ID format does the legacy system use, and how will migration map them?

Similarly, a decision to embed `items` inside a document must clarify size limits, update frequency, needs for querying individual line items independently, and how an order with very many items is handled.

### 4.4. Decisions Can Be Superseded

When context shifts, an older decision may be superseded. Record:

- which older decision the new decision replaces;
- why it changed;
- affected data and components;
- migration plan;
- effective start date;
- how data created under the old rules is handled.

Never delete old decisions from history. Decision history explains why data across two periods has different structures.

## 5. Writing Verifiable Acceptance Criteria

**Acceptance criteria** describe observable conditions verifying that a requirement or design output satisfies business needs.

Criteria must answer: "What must we observe to know this requirement is met?" They must never simply state "system works well," "data is valid," or "queries are fast."

Good criteria are typically:

- specific and unambiguous;
- observable or measurable;
- testable with concrete data and scenarios;
- linked to a requirement or decision;
- focused on expected outcomes without dictating unnecessary implementation details;
- inclusive of normal, boundary, and critical failure scenarios.

### 5.1. Distinguishing Acceptance Criteria from Implementation Details

Requirement: "Preserve the exact price of old orders when catalog prices change."

An acceptance criterion could be:

> When an order has been confirmed at 850,000 VND for a product, and later the catalog price changes to 900,000 VND, viewing the old order still displays a unit price of 850,000 VND and currency code VND.

This is observable, testable behavior. It does not mandate storing it in a column named `unit_price`, in a relational table, or inside a document. Those choices belong to modeling and implementation design.

Specific technical criteria may be needed when architectural or operational constraints exist, yet implementation choices should not be disguised as business criteria when users only care about outcomes.

### 5.2. Given–When–Then Format

Criteria can be structured as:

- **Given:** Initial context and preconditions.
- **When:** Action or event occurring.
- **Then:** Observable and verifiable outcome.

Example:

```gherkin
Feature: Preserve price at order placement time

Scenario: Catalog price changes after an order is confirmed
  Given product P-20 has price 850000 VND
  And the customer creates an order with quantity 2
  When the order is confirmed
  And the catalog price of P-20 changes to 900000 VND
  Then the old order still displays unit price 850000 VND
  And the line item total is still calculated using the locked price
  And the line item currency remains VND
```

This scenario makes sense only once the price-locking policy is confirmed. If it is not yet known whether price locks at order creation or payment confirmation, keep the question open rather than writing criteria as though a decision already exists.

## 6. Acceptance Criteria for Data Models

Data model acceptance criteria must cover semantics, structure, relationships, rules, and data usage—not merely whether the database creates tables successfully.

### 6.1. Identity and Uniqueness

Specify:

- what identifies each entity;
- within what scope the identifier is unique;
- whether codes can change or be reused;
- whether IDs must be reconciled across multiple systems;
- how duplicate data is detected and handled.

Example criterion: "When two customer-creation requests share the same external identifier within the same tenant, the system does not create two profiles; the outcome must reference the existing profile or return a conflict error per agreed rules."

### 6.2. Relationships, Cardinality, and Optionality

For each relationship, specify:

- one-to-one, one-to-many, or many-to-many;
- which side is mandatory;
- whether unlinked records can exist;
- how the other side behaves when one side is deleted or deactivated.

Example: "Every received Order must have exactly one purchasing party. Account may be absent for guest orders. Every OrderItem must belong to an active managed Order."

### 6.3. Attributes, Value Domains, and Units

Specify types, domains, precision, units, and optionality. Avoid criteria that merely say "correct data type."

Example: "Quantity on each line item is a positive integer; unit price is a non-negative decimal; monetary amounts are always paired with a supported currency code."

### 6.4. Invariants and Lifecycle

Specify which rules must always hold and which state transitions are allowed. Example:

- line items cannot have zero or negative quantities;
- a failed payment never automatically turns into a succeeded payment;
- a canceled order cannot transition to delivered without an approved restoration workflow;
- every shipment must reference its corresponding order.

State transition rules require pre-state, action, and post-state scenarios for testing.

### 6.5. History and Time

Identify which data is snapshot, which is current state, and which requires history.

Example criteria:

- Changing a customer's address does not alter the locked shipping address of past orders.
- When receiving a delayed partner event, the system retains both event occurrence time and receipt time.
- Authorized users can retrieve status change history within the permitted time window.

### 6.6. Queries and Workload

Criteria can describe critical queries using sample datasets and measurement conditions:

- Looking up an order by code returns exactly one order when the code is unique.
- Listing a customer's orders over a time range neither drops nor duplicates orders.
- Daily revenue reports do not double-count order-level totals when joined with multiple line items.
- Critical queries meet latency thresholds under agreed load and data scale.

If performance criteria exist, state environment, data scale, concurrency, percentile, and measurement method. Never write "fast" without a testable threshold.

## 7. Complete Example: From Question to Acceptance Criteria

Suppose the initial requirement is:

> Customers place orders, pay, and receive goods. The system must store history to support customer care and reporting.

### 7.1. Splitting into Questions

| ID | Question | Impact |
|---|---|---|
| Q-101 | Do buyers need to log in? | Buyer identity and relationship to Account |
| Q-102 | Can an order have multiple payment attempts? | Order–Payment model and transaction history |
| Q-103 | Can one order ship in multiple deliveries? | Order–Shipment model |
| Q-104 | How long must status history be kept and who can view it? | Storage, auditing, and access permissions |
| Q-105 | Do revenue reports use order placement time or payment time? | Metric definitions and timestamps in analytical models |

Questions Q-101 through Q-105 require confirmation from business owners. Logging them does not mean answers already exist.

### 7.2. Recording Decisions After Confirmation

Suppose the product owner and relevant teams confirm the following policies in an illustrative project:

| ID | Confirmed Decision | Model Implications |
|---|---|---|
| D-101 | Allow guest checkout; login account is optional | Account is not a mandatory identifier for every buyer |
| D-102 | Every payment attempt is recorded separately | One Order can link to many Payments |
| D-103 | One Order can split into multiple Shipments | Shipment has its own lifecycle |
| D-104 | Retain status history for support and audits per retention policy | Requires event/history source and access controls |
| D-105 | Reports separate booked revenue (order time) from collected revenue (payment time) | Separate metric definitions and timestamps required |

In a real project, each row must link to a decision record containing context, options, rationale, approver, effective date, and detailed consequences. The table above is only an illustrative summary.

### 7.3. Writing Acceptance Criteria

| ID | Criterion | How to Verify |
|---|---|---|
| AC-101 | Guest orders can still be created without an Account; required contact details are stored per policy | Create an order without logging in and read back buyer details |
| AC-102 | Each payment attempt has its own transaction ID, amount, currency, timestamp, and result | Submit one failed and one succeeded attempt; verify two records exist |
| AC-103 | One Order can link to multiple Shipments; each Shipment's status is tracked independently | Create two shipments for the same order and update them to different statuses |
| AC-104 | Status history is retrievable according to permitted roles and time range | Test history queries with authorized and unauthorized accounts |
| AC-105 | Reports separate metrics by order recording time and payment time | Use a test dataset where order placement and payment fall on different dates |

This example shows how decisions must turn into testable outcomes. If a decision produces no criteria, its consequences may not yet be understood or there is no way to prove the decision was implemented properly.

## 8. Linking Requirements, Questions, Decisions, and Model

Individual documents are only useful when links can be traced across them. **Traceability** helps answer:

- Why does this entity or attribute exist?
- Who requested this rule?
- Which decision made this relationship optional?
- Which criterion proves the model meets the requirement?
- If a requirement changes, which parts need review?

A simple traceability matrix can look like this:

| Requirement | Question | Decision | Acceptance Criteria | Model Element |
|---|---|---|---|---|
| R-01: Allow ordering | Q-101 | D-101 | AC-101 | Buyer, Account, Order |
| R-02: Store payment attempts | Q-102 | D-102 | AC-102 | Order, Payment |
| R-03: Support split deliveries | Q-103 | D-103 | AC-103 | Order, Shipment |
| R-04: Retrieve history | Q-104 | D-104 | AC-104 | OrderStatusHistory/Event |
| R-05: Time-based reporting | Q-105 | D-105 | AC-105 | FactOrder, FactPayment, or corresponding measures |

The matrix need not be a separate tool. IDs can live in documents, an issue tracker, or a requirements management system. What matters is keeping IDs stable and updating links when changes occur.

### 8.1. Checking Coverage

Before considering analysis complete, verify:

- Does every critical requirement have acceptance criteria?
- Does every question have a status, confirmer, and next step?
- Does every critical decision have context and consequences?
- Is every approved decision reflected in the model?
- Can every significant model element trace back to a requirement or rule?
- Does every acceptance criterion have a verification method and test data?

If a model element cannot trace back to any requirement, verify whether it is a technical rule, an operational need, or leftover over-design. If a requirement leads to no model element or behavior, confirm whether it was missed or is purely informational.

## 9. Managing Changes and Statuses

Requirements and decisions can change as the team uncovers new scenarios or as business policies evolve.

A simple management workflow:

1. Log the new requirement or change with an ID and source.
2. Break down into questions, assumptions, and impacts.
3. Assign questions to authorized owners and agree on due dates.
4. Write a decision record upon confirmation.
5. Update the model and related acceptance criteria.
6. Assess impacts on existing data, APIs, integrations, and reports.
7. Retest affected criteria and record results.

Agree on a clear set of statuses. For example:

- **Open:** No answer yet.
- **In review:** Awaiting review by an authorized party.
- **Answered:** Answered, though not yet necessarily approved as a decision.
- **Approved:** Accepted and approved.
- **Deferred:** Postponed until a defined milestone or condition.
- **Rejected:** Option or requirement declined.
- **Superseded:** Replaced by a newer record.

Statuses must reflect actual workflow progress. Never mark a question Answered merely because the engineering team picked an implementation on its own.

## 10. Common Mistakes

- **Leaving questions buried in meeting notes:** Weeks later nobody knows who must answer or whether a decision was finalized. Create IDs and assign owners.
- **Writing overly broad questions:** "How do customers work?" is hard to answer and hard to link to a model. Split into specific questions.
- **Turning assumptions into decisions:** Leads readers to think a policy was approved. Record statuses and confirmers.
- **Recording only the choice without rationale:** Future readers cannot judge whether the decision still fits when context changes.
- **Writing vague criteria:** "Data must be accurate" fails to specify which data, accurate against which source, and how to test it.
- **Tying criteria to table or column names too early:** Can lock down design before understanding desired behavior. Describe business outcomes first.
- **Skipping edge cases:** Testing only the happy path misses failed payments, missing data, late events, and concurrent updates.
- **Not updating links on changes:** Model, decisions, and criteria drift into contradiction if only one document is edited.
- **Not keeping decision history:** Readers cannot understand why older data differs from current rules.

## 11. Conclusion

Open questions help the team pinpoint what needs confirmation; assumptions allow analysis to move forward while clearly flagged as temporary; decisions capture approved choices with rationale and consequences. Acceptance criteria convert requirements into observable, verifiable conditions.

In data modeling, link these records to relevant entities, attributes, relationships, invariants, history, and queries. When requirements shift, those links tell you exactly which model parts and data need review.

## Self-Check

1. Distinguish an open question, an assumption, and a decision using an example from customer data.
2. Which parts of a data model are affected by a question on whether an order can ship in multiple deliveries?
3. Why must a decision record include rejected options as well as consequences of the chosen option?
4. Write a Given–When–Then criterion for a failed payment followed by a retry.
5. What additional details are needed for the criterion "queries must be fast" to become verifiable?
6. How do you trace backward from a model attribute to the requirement and person who confirmed it?
7. When a decision is superseded, what information must be retained to explain data created under the old rules?
