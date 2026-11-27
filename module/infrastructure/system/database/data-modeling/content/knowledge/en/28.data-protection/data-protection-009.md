# Modeling Consent State, Processing Purpose, and Validity Periods

## 1. Why Is a Boolean Consent Column Insufficient?

In the **DATABASE_DATA_MODELING** module, the challenge of turning business requirements into a data model requires answering questions about entities, relationships, constraints, keys, indexes, and historical data. In the **Data Protection** chapter, a common requirement is storing a data subject's consent for specific processing activities.

Suppose an e-commerce platform has customer **501**. The business wants to carry out these activities:

- Send product promotional emails.
- Send promotional push notifications via the app.
- Personalize product recommendations based on browsing history.
- Send operational notifications about orders.
- Share a defined set of information with a partner for a specific purpose.

If the customer table only contains:

~~~sql
marketing_consent boolean
~~~

then when the value is `TRUE`, the system cannot answer on its own:

1. To **which purpose** did the customer consent: email, push, personalization, or all of them?
2. Consent for **which processing entity or brand scope**?
3. Consent starting from **which timestamp**, and does it **expire**?
4. Which **notice content and policy version** did the customer view?
5. Who or which channel captured the choice; is there proof of an affirmative action?
6. When did the customer withdraw consent?
7. Was a campaign executed on March 10 based on the state known on that day?
8. When a withdrawal arrives late because a device was offline, how should prior decisions be explained?

A Boolean can serve as a **current projection** for fast reads, but it cannot replace a full consent model with scope, evidence, and history.

**Core problem:** explicitly represent **subject**, **processing purpose**, **scope**, **choice state**, **effective period**, **recorded time**, and **evidence**. From there, the system must determine which activities are permitted under applicable policy while preserving explainability and auditability.

This lesson does not assume every data processing activity relies on consent: depending on context and applicable regulations, an activity may rely on **another lawful basis**. The consent model should be used **only when consent is the required or relevant basis**, rather than replacing the entire data-processing policy framework.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish consent state from overall processing authorization and from data access actions.
2. Design a choice around **subject – purpose – scope – notice version – time**.
3. Define **GRANTED, DENIED, WITHDRAWN, EXPIRED, UNKNOWN** and state transition semantics.
4. Use half-open validity intervals **[from, to)** to store the active choice at each point in time.
5. Distinguish **valid time**, **accepted/recorded time**, and historical knowledge reconstruction.
6. Design evidence tables, decision logs, and current projections in PostgreSQL.
7. Set non-overlapping constraints and handle concurrent writes, retries, and consent withdrawal.
8. Build as-of queries and pre-processing validation workflows.
9. Integrate data protection across distributed, document, graph, and analytical models when needed.

## 2. "Consent" Is Not an Immutable Attribute of a Customer

A customer may consent to promotional emails while declining push notifications. They may agree to personalized recommendations for Brand A but not Brand B. Today they consent; next month they withdraw.

Therefore, **consent should not be modeled as a permanent attribute of the Customer entity**.

A consent choice requires context:

~~~text
Consent choice =
    Subject
  + Purpose
  + Processing scope
  + Choice / decision
  + Effective time
  + Evidence and notice version
~~~

Example:

~~~text
Subject:        Customer 501
Purpose:        MARKETING_EMAIL
Scope:          Brand A / account email address
Choice:         GRANTED
Effective from: 2026-02-01 09:00 UTC
Evidence:       Web form, notice v3, request R-100
~~~

Another choice for the same customer:

~~~text
Subject:        Customer 501
Purpose:        PERSONALIZATION
Scope:          Brand A / product browsing behavior
Choice:         DENIED
Effective from: 2026-02-01 09:00 UTC
~~~

There is no conflict between the two rows because they apply to **different purposes**.

### 2.1. Core Entities

| Entity | Role |
|---|---|
| **DataSubject** | The data subject or a controlled identifier used by the system |
| **ProcessingPurpose** | A processing purpose governed by code, description, and version |
| **ConsentScope** | Choice scope: controller, brand, channel, data categories, related activities |
| **ConsentNotice** | The text presented when requesting the choice; a verifiable stored copy or reference |
| **ConsentDecision** | A recorded choice action: grant, deny, withdraw, re-grant |
| **ConsentStateHistory** | Projection of effective state over time intervals |
| **ProcessingPolicy** | Rules determining whether an activity is permitted, including the appropriate processing basis |
| **ProcessingRecord** | Evidence that a processing activity occurred or was blocked, when auditing is required |

These entities can be separate tables, or partially reside inside a policy service. Separating responsibilities prevents confusing **consent evidence** with **current state** or **processing authorization outcomes**.

## 3. Distinguishing Processing Purpose from Channel and Data Category

**Processing purpose** answers the question: **"Why is the data being used?"**

Examples:

- **MARKETING_EMAIL:** sending marketing content via email.
- **MARKETING_PUSH:** sending promotional notifications via the mobile app.
- **PERSONALIZED_RECOMMENDATION:** personalizing suggestions based on behavior.
- **PARTNER_OFFER_SHARING:** sharing scoped data so a partner can send offers.
- **ORDER_FULFILLMENT:** processing orders and deliveries under a defined processing basis.

Technical names must be paired with **clear business descriptions**, not just an opaque code.

**Channel** answers "via what medium?": email, push, SMS, web.

**Data category** answers "which data is used?": purchase history, browsing events, contact address.

**Controller / recipient scope** answers "who is processing or receiving the data under the agreed scope?".

These three axes may relate to one another, yet they are not identical. One marketing purpose may use multiple channels, and each channel may require a separate choice under policy. Do not design a column **purpose = email** when "email" can mean both a contact data type and a delivery channel.

### 3.1. The Purpose Catalog Must Be Governed

| Attribute | Example | Design requirement |
|---|---|---|
| purpose_code | MARKETING_EMAIL | Stable, well-defined code |
| display_name | Receive promotional emails | Clear to the data subject |
| purpose_description | Send promotional content... | Matches the published disclosure |
| processing_activity | SEND_MARKETING_CAMPAIGN | Links to actual processing operations |
| data_categories | EMAIL_ADDRESS, PURCHASE_SEGMENT | Only the data categories actually used |
| controller_scope | BRAND_A | Applicable organizational scope |
| policy_version | POLICY-2026-02 | Effective rule version |

A **material change** in purpose should not silently alter the description of the same `purpose_code` and treat all prior choices as valid for the new purpose. A new `purpose_code`, new notice, and re-consent flow may be required under applicable policy.

### 3.2. Do Not Bundle Everything into One Checkbox

Example UI pattern:

~~~text
[ ] I agree to receive marketing emails.
[ ] I agree to receive promotional push notifications via the app.
[ ] I agree to allow personalized recommendations from browsing behavior.
~~~

Three separate choices reflect state and scope far better than a single **"I agree to all terms"** checkbox. Specific UI design and consent validity conditions must also satisfy applicable legal rules; this lesson focuses on **how the data model accurately preserves the choices collected**.

## 4. Boundary Between Consent and Data Processing Authorization

A system may have:

~~~text
ConsentState(subject, purpose) = GRANTED
~~~

yet that alone **is not enough** to conclude every processing activity is permitted. It must also check:

- Does it match the exact disclosed purpose?
- Is the data being used within the permitted and necessary scope?
- Do the executing actor and processing system have access rights?
- Have the validity period or conditions expired?
- Are there specific restrictions on the subject, data category, or representative?
- What processing policies and legal obligations currently apply?
- Is there any stop-processing, erasure, restriction, or objection request?

Conversely, **the absence of a GRANTED consent** does not prove that **every** processing activity is prohibited: an activity may be permitted on another processing basis, if genuinely compliant with law and policy. For instance, order status notifications should not automatically be conflated with promotional marketing emails.

Therefore, separate:

~~~text
ConsentEvidence     = what the subject chose and supporting proof
ProcessingPolicy    = lawful basis and processing conditions
AuthorizationResult = decision for a specific operation at time T
~~~

**Safety rule:** if an activity **requires consent** and the system finds no valid `GRANTED` proof for the exact purpose and scope, **do not execute that activity** until verified. This is **fail-closed behavior for consent-dependent processing paths**, not a legal conclusion for every data operation.

## 5. Choice States: Distinguishing Grant, Deny, and Withdraw

A single `TRUE/FALSE` state loses critical semantics.

| State or outcome | Meaning | Considered active consent? |
|---|---|---|
| **GRANTED** | Valid affirmative choice within scope and time | Yes, if all other conditions are met |
| **DENIED** | Subject actively declined a choice request | No |
| **WITHDRAWN** | Subject withdrew a previously granted choice | No, from the effective withdrawal timestamp |
| **EXPIRED** | A grant reached its published expiration rule | No, after expiration |
| **UNKNOWN / NO_RECORD** | No sufficiently reliable record or never asked | Must not be inferred as GRANTED |
| **INVALIDATED** | Proof determined invalid or voided by procedure | No, once invalidation takes effect |

It is not always necessary to store **EXPIRED** as a separate event if **valid_to** or **expires_at** is already on the grant. When queried after the deadline, **EXPIRED** can be inferred from the time interval.

Similarly, **UNKNOWN** represents the **system's state of knowledge**, not necessarily a refusal by the subject. If a choice was never requested, do not fabricate a **DENIED** event merely for query convenience.

### 5.1. A Simple State Machine

~~~mermaid
flowchart LR
    U["UNKNOWN"] -->|grant| G["GRANTED"]
    U -->|deny| D["DENIED"]
    G -->|withdraw| W["WITHDRAWN"]
    G -->|expire| E["EXPIRED"]
    D -->|new grant| G
    W -->|new grant| G
    E -->|new grant| G
~~~

This diagram describes only **choice semantics**, not the full workflow of proof verification, legal conditions, representative capacity, or authorization checks. An event such as **WITHDRAW** without a prior grant can be recorded as a withdrawal request action, but must never rewrite history to claim "previously granted" without proof.

### 5.2. Do Not Delete the GRANTED Record When the Subject Withdraws

If consent was `GRANTED` on Feb 1 and withdrawn on Mar 10, deleting the grant row or overwriting it to `FALSE` loses the answer to:

> "At the time the email was sent on March 5, what consent evidence did the system hold?"

Retain **choice history and evidence** under an appropriate retention policy while blocking further processing once the withdrawal takes effect. This is distinct from keeping all personal data indefinitely.

## 6. Effective Time Differs from System Knowledge Time

An action can carry several timestamps:

| Field | Meaning |
|---|---|
| **source_action_at** | When the client reports the subject clicked grant/withdraw |
| **received_at** | When the server received the request |
| **accepted_at** | When the authoritative system accepted the decision |
| **effective_at** | When the decision starts affecting the processing scope |
| **expires_at** | Under what condition the grant ceases to be valid |
| **recorded_at** | When the record entered the system or log |
| **known_period** | Interval during which the system treats a version of info as known |
| **processed_at** | When an operation relying on consent was executed |

Specifically, **source_action_at** from an offline device may not be fully trustworthy due to clock skew. Server-issued **accepted_at** is more reliable for operational investigations, though not necessarily the exact transaction **COMMIT** timestamp.

**effective_at** must follow clear rules: for example, a grant takes effect when the system accepts and verifies proof; a withdrawal applies from a time aligned with policy and response obligations. Never allow clients to supply an arbitrary past date to retroactively legitimize a grant that did not exist when processing occurred.

### 6.1. Three-Stage Example

Suppose customer 501 makes choices for **MARKETING_EMAIL** on Brand A:

~~~text
2026-02-01 09:00 UTC: GRANTED
2026-03-10 10:00 UTC: WITHDRAWN
2026-04-02 08:00 UTC: Re-GRANTED (new notice)

Validity timeline:

[2026-02-01 09:00, 2026-03-10 10:00) GRANTED
[2026-03-10 10:00, 2026-04-02 08:00) WITHDRAWN
[2026-04-02 08:00, +∞)               GRANTED
~~~

Questions:

- **Mar 5:** treated as `GRANTED` in this timeline.
- **Mar 10 at exactly 10:00:** no longer `GRANTED`; falls into the `WITHDRAWN` interval.
- **Mar 20:** `WITHDRAWN`.
- **Apr 5:** `GRANTED` again if valid evidence and conditions exist.

**A re-grant does not turn the withdrawn interval in March into a grant.** History must remain intact for explainability.

### 6.2. Half-Open Intervals `[from, to)`

Convention:

~~~text
A <= time < B

[2026-02-01 09:00, 2026-03-10 10:00) GRANTED
[2026-03-10 10:00, 2026-04-02 08:00) WITHDRAWN
~~~

The boundary **Mar 10 10:00** belongs exclusively to `WITHDRAWN`. Avoid using two inclusive boundaries or using `09:59:59.999` as an end boundary, since timestamp precision may vary.

## 7. Time Units: UTC, Timezones, and Expiration Rules

For processing executed at an absolute instant, use **timestamptz** in PostgreSQL and exchange timestamps with explicit offsets. A choice expiring on a **local calendar date** requires conversion rules:

- Does it expire at start of day or end of day?
- Whose timezone governs the date: the subject's, country's, or controller's?
- If the subject changes timezones, does the deadline shift?
- If a region observes daylight saving time, day length is not fixed.
- If the limit is "after 90 days," does it mean **90 × 24 hours** or **90 calendar days** in a specified timezone?

For example, a policy "expires at the start of May 1 in Vietnam time" corresponds to:

~~~text
valid_to = 2026-05-01 00:00:00+07
         = 2026-04-30 17:00:00 UTC
~~~

Do not blindly apply **DATE(timestamp_utc)** to derive local dates or set "infinity" when the published notice states a finite duration.

### 7.1. Decision Time Can Differ from Execution Time

A marketing campaign is scheduled at 08:00 but actually sent at 09:00. If the customer withdraws consent at 08:30, **checking at scheduling time** is insufficient for sending at 09:00.

You must define the **valid verification point** per activity: before enqueueing, immediately before sending, and when the consumer executes, depending on requirements. A decision cache needs TTL, invalidation, and timely propagation of withdrawal changes.

## 8. Choosing the Grain for Consent: What Does One Row Represent?

Grain of **ConsentDecision**:

> One accepted choice action (or recorded as invalid/denied depending on the flow) by one subject, for one specific purpose and scope, linked to a timestamp and evidence.

Grain of **ConsentStateHistory**:

> One contiguous effective state segment for the exact combination `(tenant, subject, purpose, scope)`.

These two data types have **different grains**. One withdrawal action may close a `GRANTED` state segment and open a `WITHDRAWN` segment. One UI request may update three purposes at once, creating **three separate decisions** sharing a request/correlation ID.

### 8.1. Business Key of a Choice Stream

A stream can be identified by:

~~~text
(tenant_id, subject_id, purpose_code, scope_key)
~~~

Where **scope_key** is a normalized, governed code, for example:

~~~text
BRAND_A:EMAIL
BRAND_A:PUSH
BRAND_A:PERSONALIZATION
BRAND_B:EMAIL
~~~

This is merely an illustration of scope codes; larger systems may split `controller_id`, `channel_code`, `data_category`, and `processing_activity` into more structured columns or reference tables.

Never let callers pass arbitrary strings and treat every case or whitespace variation as a new scope.

### 8.2. Why Separate Subject and Source Identity?

A subject may use web, mobile app, and CRM with three source IDs. If consent stores only each application's `user_id`, the system cannot reliably apply withdrawals for the same person across channels.

You can issue a controlled **canonical_subject_id** alongside a source-ID mapping table. However, account merges must be verified; never auto-merge two profiles just because email or name matches. For unauthenticated devices, choice scope may apply only to a **device/browser identifier**, and must not be attached by default to every potentially related account.

## 9. What Consent Evidence Should Be Stored?

A state table showing `GRANTED` does not sufficiently prove **what the subject saw and how they interacted**.

Information that may need to be retained:

- **notice_id / notice_version**: version of the presented content.
- **notice_content_ref**: reference to durably stored content.
- **content hash**: digest verifying content integrity, where applicable.
- **locale**: language of the content.
- **capture_channel**: web, mobile, call center, or paper form.
- **interaction_type**: active checkbox selection, authenticated account confirmation, documented workflow, etc.
- **actor/representative**: who acted and whether valid representation authority existed.
- **source_decision_key**: source-issued choice ID used to prevent retries.
- **accepted_at and effective_at**: distinguishing recording from effectiveness.
- **scope/purpose**: what the choice actually applies to.
- **evidence_ref**: reference to permitted retained proof.
- **policy/processing version**: which rule version the system used to interpret processing rights.

Do not store passwords, auth tokens, payment card data, full HTTP request bodies, or unnecessary personal data just to "prove consent."

**A hash does not replace the actual presented content.** Storing only a hash without recoverable content/version makes it hard to explain what the subject read. Nor should a single hash automatically be treated as tamper-proof if admin privileges, storage, and write paths are unprotected.

### 9.1. Notice History Must Be Immutable for Published Content

If notice `v3` was used to collect choices in February, never overwrite `v3`'s text with new April content under the same version.

Possible design:

~~~text
notice_id=N3
version=3
locale=vi-VN
purpose=MARKETING_EMAIL
content_ref=immutable://privacy/notice/N3/vi-VN
digest=...
published_at=...
~~~

When a meaningful change occurs, create a new version. Whether re-consent is required depends on whether the change exceeds the scope of prior choices under the defined legal policy.

## 10. ER Model: Decision Events, State, and Evidence

~~~mermaid
erDiagram
    DATA_SUBJECT ||--o{ CONSENT_SCOPE : "has choice scopes"
    PROCESSING_PURPOSE ||--o{ CONSENT_SCOPE : "evaluated per purpose"
    CONSENT_SCOPE ||--o{ CONSENT_DECISION : "records actions"
    CONSENT_SCOPE ||--o{ CONSENT_STATE_HISTORY : "state versions"
    CONSENT_NOTICE ||--o{ CONSENT_DECISION : "referenced notice"
    CONSENT_DECISION ||--o{ CONSENT_STATE_HISTORY : "decision source"
    DATA_SUBJECT {
        bigint tenant_id PK
        uuid subject_id PK
    }
    PROCESSING_PURPOSE {
        text purpose_code PK
        text description
    }
    CONSENT_SCOPE {
        bigint tenant_id PK
        uuid subject_id PK
        text purpose_code PK
        text scope_key PK
        bigint revision
    }
    CONSENT_NOTICE {
        uuid notice_id PK
        text purpose_code
        text notice_version
        text locale
    }
    CONSENT_DECISION {
        uuid decision_id PK
        text action_code
        timestamptz effective_at
        timestamptz accepted_at
        text evidence_ref
    }
    CONSENT_STATE_HISTORY {
        bigint state_version_id PK
        text state_code
        tstzrange valid_period
        uuid source_decision_id
    }
~~~

The model uses a **decision log** as proof of actions, while **state history** is a representation optimized for as-of state queries. Both tables can be written in one transaction within the same database.

One project may choose event sourcing as the source of truth and build state history as a projection. Another may treat state history as the authoritative state store while emitting decision events for audit. Clearly state the **authoritative source** and reconciliation mechanism so the two tables never diverge independently.

## 11. PostgreSQL: Subject, Purpose, and Scope Tables

Examples use PostgreSQL **timestamptz** and **tstzrange**. The **btree_gist** extension is needed to support equality operators inside the GiST exclusion constraint shown later.

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE data_subject (
    tenant_id  bigint NOT NULL,
    subject_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, subject_id)
);

CREATE TABLE processing_purpose (
    purpose_code text PRIMARY KEY,
    display_name text NOT NULL,
    description text NOT NULL,

    CONSTRAINT ck_purpose_code_not_blank
        CHECK (length(btrim(purpose_code)) > 0)
);

CREATE TABLE consent_scope (
    tenant_id    bigint NOT NULL,
    subject_id   uuid NOT NULL,
    purpose_code text NOT NULL
                 REFERENCES processing_purpose(purpose_code),
    scope_key    text NOT NULL,
    revision     bigint NOT NULL DEFAULT 0
                 CHECK (revision >= 0),

    PRIMARY KEY (tenant_id, subject_id, purpose_code, scope_key),

    FOREIGN KEY (tenant_id, subject_id)
        REFERENCES data_subject(tenant_id, subject_id),

    CONSTRAINT ck_scope_key_not_blank
        CHECK (length(btrim(scope_key)) > 0)
);
~~~

**consent_scope** holds one stable row per subject–purpose–scope combination. Beyond acting as a foreign key target, it serves as the **transaction lock point** when updating multiple state versions: you can run `SELECT ... FOR UPDATE` on that exact scope row before closing/opening intervals.

Production systems must enforce tenant-scoped access control, govern the scope catalog, and integrate policy versions. This DDL is intentionally the core model, not a complete compliance platform.

### 11.1. Purpose Differs from Processing Basis

The **processing_purpose** table records the purpose. It does not assert that every purpose requires consent. Systems should have a separate **processing policy** specifying purpose, activity type, controller, data source, and lawful basis over time.

Do not create an immutable **consent_required boolean** column on `purpose_code` and treat it as a legal answer across every market, subject type, and time period if those conditions can change.

## 12. PostgreSQL: Storing Notices and Append-Only Decisions

### 12.1. Notice Records

~~~sql
CREATE TABLE consent_notice (
    notice_id      uuid PRIMARY KEY,
    purpose_code   text NOT NULL
                   REFERENCES processing_purpose(purpose_code),
    notice_version text NOT NULL,
    locale_code    text NOT NULL,
    content_ref    text NOT NULL,
    content_sha256 char(64) NOT NULL,
    published_at   timestamptz NOT NULL,

    UNIQUE (purpose_code, notice_version, locale_code)
);
~~~

**content_sha256** is the hash of the actual content, not a random string generated by the application. You must define the canonical format of hashed content and how the original copy is stored. Storing only a hash is insufficient if published content must be recovered.

### 12.2. Decision Log

~~~sql
CREATE TABLE consent_decision (
    decision_id     uuid PRIMARY KEY,
    tenant_id       bigint NOT NULL,
    subject_id      uuid NOT NULL,
    purpose_code    text NOT NULL,
    scope_key       text NOT NULL,

    action_code     text NOT NULL
                    CHECK (
                        action_code IN (
                            'GRANT', 'DENY', 'WITHDRAW'
                        )
                    ),

    effective_at    timestamptz NOT NULL,
    source_action_at timestamptz,
    accepted_at     timestamptz NOT NULL
                    DEFAULT statement_timestamp(),

    notice_id       uuid REFERENCES consent_notice(notice_id),
    capture_source  text NOT NULL,
    source_decision_key text NOT NULL,
    evidence_ref    text,

    FOREIGN KEY (
        tenant_id, subject_id, purpose_code, scope_key
    ) REFERENCES consent_scope (
        tenant_id, subject_id, purpose_code, scope_key
    ),

    UNIQUE (
        tenant_id, capture_source, source_decision_key
    ),

    CONSTRAINT ck_grant_has_evidence
        CHECK (
            action_code <> 'GRANT'
            OR (notice_id IS NOT NULL AND evidence_ref IS NOT NULL)
        )
);
~~~

In this model, **source_decision_key** must be a distinct ID for **each purpose/scope choice** issued by the capture source, not one shared ID for an entire form with three checkboxes. If a form submits multiple choices, use a shared **correlation_id** (which can be added) to group decisions, while keeping each decision uniquely identified for retry protection.

The `UNIQUE` constraint protects the namespace **tenant + capture_source + source_decision_key**. If the source ID is unique only under a different scope, adjust the key to match the source contract.

**notice_id** is required on `GRANT`, yet an FK alone does not prove the notice matched the purpose, locale, scope, and content actually shown. The write path must verify this; a composite foreign key or policy validator can be added if stronger database-level guarantees are required.

### 12.3. Do Not Alter History with Arbitrary UPDATEs

The decision log should be treated as **action evidence**. When a decision is found to be recorded erroneously or needs correction, write a **new decision/correction** linked to the prior decision rather than silently updating fields of the old record.

This does not mean audit data is kept forever regardless of erasure/restriction requests. Retention, minimization, and controlled rectification/deletion mechanisms under applicable regulations are still required.

## 13. PostgreSQL: Validity-Interval State Projection

~~~sql
CREATE TABLE consent_state_history (
    state_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tenant_id    bigint NOT NULL,
    subject_id   uuid NOT NULL,
    purpose_code text NOT NULL,
    scope_key    text NOT NULL,

    state_code   text NOT NULL
                 CHECK (
                     state_code IN (
                         'GRANTED', 'DENIED', 'WITHDRAWN'
                     )
                 ),

    valid_period tstzrange NOT NULL,
    source_decision_id uuid NOT NULL
                       REFERENCES consent_decision(decision_id),

    FOREIGN KEY (
        tenant_id, subject_id, purpose_code, scope_key
    ) REFERENCES consent_scope (
        tenant_id, subject_id, purpose_code, scope_key
    ),

    CONSTRAINT ck_consent_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_one_consent_state_per_instant
        EXCLUDE USING gist (
            tenant_id WITH =,
            subject_id WITH =,
            purpose_code WITH =,
            scope_key WITH =,
            valid_period WITH &&
        )
);
~~~

Grain of the table: **one active state across one continuous interval for one specific scope**.

The **EXCLUDE** constraint rejects two rows with the same tenant/subject/purpose/scope whose **valid_period** overlaps. It enforces the invariant "at time B, there is at most one state."

**The constraint does not guarantee a state always exists.** If no record exists yet, or there is a gap between two decisions, the query returns no rows. For consent-dependent processing, a missing state must be interpreted as **no valid grant**, never defaulted to `GRANTED`.

### 13.1. Expiration Lies on the Grant's End Boundary

If a grant expires at `T`:

~~~text
GRANTED: [t0, T)
After T: no longer GRANTED
~~~

You can close the grant at `T` **without INSERTing EXPIRED** if the system only needs to know whether a grant is active. If reporting an explicit `EXPIRED` status is needed for display or audit, derive it from the grant's termination reason or store an appropriate event/state. Never fabricate an event saying "subject actively withdrew" when the grant simply expired automatically.

### 13.2. Decision and State Must Match the Same Scope

A single-column FK to `decision_id` only ensures **the decision exists**, not that a state row references a decision with the matching **tenant, subject, purpose, and scope**. Write paths and data-quality tests must verify these fields match; you can upgrade to a composite foreign key if database-level enforcement is desired.

Never allow a `GRANTED` row for Brand A to mistakenly reference a decision granted for Brand B just because the decision UUID exists.

## 14. Sample Data: One Customer, One Purpose, Three Stages

Suppose:

~~~text
tenant_id    = 1
subject_id   = 501 (business label)
purpose_code = MARKETING_EMAIL
scope_key    = BRAND_A:EMAIL

2026-02-01 09:00 UTC: customer accepts notice v3
2026-03-10 10:00 UTC: customer withdraws
2026-04-02 08:00 UTC: customer grants again under notice v4
~~~

Projected timeline:

| From (UTC) | To (UTC, exclusive) | State | Basis |
|---|---|---|---|
| 2026-02-01 09:00 | 2026-03-10 10:00 | GRANTED | Decision D1, notice v3 |
| 2026-03-10 10:00 | 2026-04-02 08:00 | WITHDRAWN | Decision D2 |
| 2026-04-02 08:00 | Unbounded | GRANTED | Decision D3, notice v4 |

The table above uses subject `501` for readability, whereas the SQL DDL uses a system-assigned **subject_id uuid**. These are two illustrative representations, not verbatim `INSERT` statements.

### 14.1. Do Not Share Grants Across Purposes

If the same customer has:

~~~text
MARKETING_EMAIL: GRANTED
PERSONALIZATION:  DENIED
MARKETING_PUSH:   UNKNOWN
~~~

then marketing email queries can rely on `GRANTED` if all other conditions hold. However, promotional push and personalization **must not implicitly inherit that permission**.

If Brand B wants to send emails, `GRANTED` under **BRAND_A:EMAIL** does not transfer to **BRAND_B:EMAIL** unless the published scope and original choice genuinely included Brand B under verified rules.

### 14.2. Re-Granting Is a New Decision

D3 must not rewrite D1 into "continuous consent since Feb 1." The March `WITHDRAWN` interval is a critical part of history, because activities had to stop during that period.

## 15. As-Of Consent Queries at a Point in Time

In PostgreSQL, the **@>** operator tests whether a range contains a timestamp.

Example retrieving state on 2026-03-05:

~~~sql
SELECT
    state_code,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to,
    source_decision_id
FROM consent_state_history
WHERE tenant_id = :tenant_id
  AND subject_id = :subject_id
  AND purpose_code = 'MARKETING_EMAIL'
  AND scope_key = 'BRAND_A:EMAIL'
  AND valid_period @> TIMESTAMPTZ '2026-03-05 12:00:00+00';
~~~

Parameters **:tenant_id** and **:subject_id** are application-bound, not built-in PostgreSQL variables. Given the example timeline, the query returns **GRANTED**.

### 15.1. A Check Flag for Consent-Dependent Paths

~~~sql
SELECT COALESCE((
    SELECT state_code = 'GRANTED'
    FROM consent_state_history
    WHERE tenant_id = :tenant_id
      AND subject_id = :subject_id
      AND purpose_code = :purpose_code
      AND scope_key = :scope_key
      AND valid_period @> :operation_at
), FALSE) AS has_active_grant;
~~~

Because the exclusion constraint guarantees at most one matching row at any instant, the scalar subquery will not return multiple rows while the constraint is active. When no row matches, **COALESCE(..., FALSE)** returns `FALSE`.

**This is only one grant-check step.** Returning `TRUE` does not replace checks for actual purpose, processing basis, access permissions, data categories, notice conditions, and other restriction policies.

### 15.2. Expected Results

| Operation time | Active grant result |
|---|---|
| 2026-03-05 12:00 UTC | TRUE |
| 2026-03-10 09:59 UTC | TRUE |
| 2026-03-10 10:00 UTC | FALSE |
| 2026-03-20 12:00 UTC | FALSE |
| 2026-04-05 12:00 UTC | TRUE |
| Date before Feb 1 with no record | FALSE |

If a grant has an explicit expiration timestamp, the upper bound of the interval must reflect that exact deadline. Never keep returning `TRUE` merely because the last recorded action was `GRANTED`.

## 16. Transactional Updates: Grant, Withdraw, and Re-Grant Must Be Atomic

A new choice affects all of:

- Decision log (proof of action).
- State projection (effective permission).
- Possibly an outbox record to propagate changes to email, analytics, or data warehouse services.
- Scope revision for concurrency control.

If writing the decision succeeds and updating state fails without rollback or reconciliation, the two sources can contradict each other.

### 16.1. Protocol When Updating Only the Latest Version

Assuming only decisions with **effective_at strictly later than the start of the currently open interval**, with no future-dated decisions or retroactive corrections:

~~~text
BEGIN TRANSACTION

1. Find CONSENT_SCOPE for the exact tenant + subject + purpose + scope.
2. Lock the scope row with SELECT ... FOR UPDATE.
3. Validate request idempotency, permissions, and evidence.
4. Verify effective_at is valid and ordered relative to the open state.
5. INSERT the new CONSENT_DECISION.
6. Close valid_period of the previous state at effective_at.
7. INSERT the new CONSENT_STATE_HISTORY starting at effective_at.
8. Increment scope revision.
9. INSERT outbox event if change propagation is needed.
10. COMMIT.

If any step fails: ROLLBACK and do not confirm success.
~~~

Locking the stable scope row prevents two concurrent requests for the same subject/purpose/scope from splitting intervals based on stale state. The **Exclusion constraint** acts as an extra safeguard, blocking overlapping outcomes even if a code path bypasses update rules.

### 16.2. Do Not Close an Interval When `effective_at` Equals the Start Point

If the system already has `GRANTED` starting at 10:00 and a new `WITHDRAW` request also applies at exactly 10:00, setting **[10:00, 10:00)** produces an empty range and must be rejected. You must define **decision precedence at identical timestamps**, potentially collapsing the final state via business logic within the transaction while preserving both decision events.

Never add one microsecond to `effective_at` to work around the constraint, as doing so corrupts the business timestamp.

### 16.3. Retroactive or Future Decisions Are More Complex

If the current state has:

~~~text
GRANTED   [2026-02-01, 2026-05-01)
WITHDRAWN [2026-05-01, +∞)
~~~

and on April 10 a decision arrives effective March 15, you cannot simply "close the last row and open a new row." You must:

1. Locate the **segment containing the effective timestamp**.
2. Verify authority and retroactive handling rules.
3. Split the timeline at the required boundaries.
4. Preserve still-valid future decisions.
5. Verify no intervals overlap.
6. Record why effective history changed.
7. Assess impact on processing decisions already executed in the past.

Never backdate a grant merely to legitimize processing the system performed before proof existed.

### 16.4. Idempotency of a Choice

If the web app resends decision `D2` due to a timeout after commit, the system must recognize it as **the same choice** and return the prior result instead of creating another withdrawal that corrupts the timeline.

The `UNIQUE` key on `source_decision_key` in the decision table supports deduplication. However, if the same key is resent with a different purpose, scope, action, or evidence, return a **conflict**, rather than treating it as an identical retry.

## 17. Withdrawing Consent: Ending Future Permission While Retaining Historical Proof

Withdrawing consent is not flipping a `GRANTED` Boolean to `FALSE` and calling it done.

A complete workflow requires:

1. Letting subjects submit requests through supported channels.
2. Identifying the subject and appropriate representative authority.
3. Identifying the withdrawn **purpose and scope**.
4. Recording action, received, and accepted times; applying `effective_at` per policy.
5. Closing the active grant interval.
6. Writing the withdrawal decision with `request_id` and minimal evidence.
7. Updating projections/caches/segments used for new processing.
8. Propagating stop-processing events to relevant downstream systems.
9. Ensuring queued send/data-sharing jobs are re-checked.
10. Monitoring withdrawal propagation and exception handling.

### 17.1. Withdrawal Does Not Automatically Delete All Prior Records

Some data may have been validly processed before the withdrawal took effect; some records may need retention under independent obligations or for evidence, depending on law and policy. At the same time, processing purposes relying on the withdrawn consent **must not continue using the data based on the old grant**.

Therefore, separate:

~~~text
Consent withdrawn
  ≠ delete all historical evidence automatically
  ≠ continue future processing because data already exists
  ≠ instantly purge all backups regardless of obligations
~~~

Separate policies and enforcement checks are needed for retention, restriction, deletion/anonymization, and data subject rights.

### 17.2. Consent Rights Must Not Be Reused from Stale Caches

An email system fetched an eligible recipient list yesterday. This morning the customer withdrew consent. If a worker still sends based on yesterday's snapshot, the system fails to stop processing in time.

Solutions may include:

- **Final consent check** immediately before sending.
- Rapidly synchronized suppression lists.
- Cache invalidation or low TTL for consent caches.
- Idempotent `WITHDRAW` event handling.
- Monitoring propagation lag and pending queues.
- Failing closed if status cannot be verified for consent-required paths.

No single solution fits every SLA; choose and test based on the operation's risk.

## 18. Bitemporal: When Did It Take Effect vs. What Did the System Know?

Suppose a mobile app records a withdrawal at **10:00 on Mar 10**, while offline, and only syncs to the server at **12:00**.

There are two distinct questions:

1. **"Under the currently accepted decision, at what business time B did the withdrawal take effect?"**
2. **"At 11:00, did the server already know and have the ability to apply the withdrawal?"**

If the application later sets `valid_from = 10:00` to reflect the customer's request, the **valid time** timeline reports `WITHDRAWN` at 11:00. Yet that does not mean a consumer at 11:00 had received that information.

Explaining both axes requires:

- **valid_period**: the business interval during which the information is deemed effective.
- **known_period**: the interval during which the system accepted/stored that version as known.

### 18.1. Two-Time-Axis Example

~~~text
Before 12:00 the server recorded:
  GRANTED, valid [02/01, +∞), known [02/01, 03/10 12:00)

From 12:00 the server recorded:
  GRANTED,   valid [02/01, 03/10 10:00), known [03/10 12:00, +∞)
  WITHDRAWN, valid [03/10 10:00, +∞),    known [03/10 12:00, +∞)
~~~

This distinguishes two statements:

- At **K = 11:00**, the system believed the grant was active for **B = 11:00**.
- At **K = 13:00**, based on received information and effectiveness rules, the system can treat the withdrawal as applying to **B = 11:00**.

**Do not treat backdating valid time as an automatic conclusion about the lawfulness of an operation executed at 11:00.** That depends on rules governing effective withdrawal timing, when the system could reasonably know and act, response obligations, evidence, and applicable policy.

### 18.2. Bitemporal Constraints

If using a bitemporal projection table, each row carries both **valid_period** and **known_period**. A conceptual PostgreSQL constraint:

~~~sql
-- Illustrative CONSTRAINT excerpt;
-- must be placed inside a CREATE TABLE with all required columns.
EXCLUDE USING gist (
    tenant_id WITH =,
    subject_id WITH =,
    purpose_code WITH =,
    scope_key WITH =,
    valid_period WITH &&,
    known_period WITH &&
)
~~~

This prevents two states for the same scope from overlapping **simultaneously on both valid time and known time**. Two versions with overlapping `valid_period` but disjoint `known_period` are valid, because they reflect the system's knowledge in two different eras.

**Application-supplied known time is not necessarily exact commit time.** If proof of state at transaction commit is required, design appropriate cutoffs, recording, and commit ordering rather than just adding an `updated_at` column.

### 18.3. Does an Event Log Replace Bitemporal Modeling?

A complete, ordered decision event log allows replaying accepted states at each version. Yet replaying to answer "what did the system know at K?" requires mapping versions to authoritative timestamps, stable interpretation rules, and all corrections.

Bitemporal history is a **convenient projection for two-axis queries**, not a capability that magically appears just because data has an `event_id`.

## 19. Effective Attributes and Relationships Must Also Match the Point in Time

Consent may depend on:

- Which tenant the subject belongs to.
- Which brand or controller holds authority over that channel.
- Which email address is the verified contact endpoint.
- Which device was linked to which account.
- During which interval a representative held valid authority.

If the **subject – email address** relationship has history, consent to email an old address does not automatically apply to every new address. Policy may bind consent to **subject + purpose + channel**, or to a **specific contact address**; choose according to the published disclosure.

### 19.1. Avoid Joining Current Versions to Past Events

Suppose a customer changes email on May 1. A March campaign sent to the old address. You cannot JOIN March send logs with the current email table and report that the message was sent to the new address.

Processing records or finalized messages must preserve the **contact endpoint/identifier used** (stored safely and minimally) and timestamp, or an FK to the effective contact version.

### 19.2. Time-Bounded Representative Relationships

If representative X only held authority to decide on behalf of the subject during `[A, B)`, a grant executed by X at time C must verify **C ∈ [A, B)**. Never use current representative authority to validate historical decisions.

This is a **temporal join** between decisions and representative-relationship history, along with required proof of authority.

## 20. Distributed Systems: Synchronizing Withdrawals Across Services

An organization might have:

~~~mermaid
flowchart TD
    UI["Web/App: subject choice"] --> CS["Authoritative consent service"]
    CS --> DB["Decision log + State history"]
    CS --> OB["Transactional outbox"]
    OB --> MQ["Message broker / event stream"]
    MQ --> EM["Email marketing"]
    MQ --> RE["Recommendation service"]
    MQ --> DW["Analytics warehouse / activation"]
    CS --> AP["Processing authorization API"]
    AP --> EM
    AP --> RE
~~~

When consent changes, downstream consumers can receive an event:

~~~json
{
  "eventId": "evt-withdraw-501",
  "subjectId": "subject-501",
  "purposeCode": "MARKETING_EMAIL",
  "scopeKey": "BRAND_A:EMAIL",
  "decisionId": "D2",
  "action": "WITHDRAW",
  "effectiveAt": "2026-03-10T10:00:00Z",
  "revision": 12
}
~~~

This is a **semantic illustration payload**, not a JSON record with real DDL UUIDs. An event must keep a **fixed eventId across publisher retries**; consumers deduplicate and apply the appropriate version/revision.

### 20.1. Outbox Prevents Gaps Between DB and Broker

If the app commits history and then publishes to the broker directly, the database might commit while the broker misses the message. If it publishes before commit, consumers may receive changes not yet accepted.

A transactional outbox writes the state/decision record and outgoing message in the same database transaction, and a publisher relays it afterward. This reduces message loss risk, though it can **deliver duplicates**; consumers still need idempotency.

### 20.2. Do Not Confuse Emitted Events with Applied Withdrawals Everywhere

A `WITHDRAW` message accepted by the broker does not prove the email worker processed it and halted sending. Monitor:

- Revision processed at each consumer.
- Propagation latency.
- Pending or in-flight jobs.
- Count of blocked operations.
- Errors, retries, and out-of-sync data.

High-risk paths may require **synchronous checks at the point of execution** rather than relying solely on asynchronous events.

### 20.3. Replaying Events Does Not Mean Replaying Actions

When rebuilding a projection by replaying historical `GRANT/WITHDRAW` events, the system must not re-trigger **marketing emails** from old events. Separate **state-building consumers** from **side-effect-executing consumers**, and design idempotency and time-window checks.

## 21. Relational, Document, Graph, and Analytical Models

Different database choices must uphold the same semantic contract:

| Technology / model | Possible representation | Risks to control |
|---|---|---|
| **Relational** | ConsentScope, DecisionLog, StateHistory, Notice | FKs, EXCLUDE, transactions, versions, and as-of queries |
| **Document** | Consent decision documents, current projection | Concurrent updates, non-overlap, scope structure, retention |
| **Graph** | Subject → Purpose/Controller/Channel with effective edges | Point-in-time relationship queries; avoid inferring via current edges |
| **Event store** | GRANT/WITHDRAW decision stream, replay projection | Ordering, idempotency, schema evolution, snapshots |
| **Data warehouse/lakehouse** | Consent history and time-sliced activation datasets | Late data, check timing, stale segments, PII |
| **Cache/search index** | Current consent status or suppression projection | Sync lag, invalidation, fail-safe behavior |

### 21.1. Documents Do Not Automatically Enforce Interval Integrity

A collection with documents like:

~~~json
{
  "subjectId": "subject-501",
  "purpose": "MARKETING_EMAIL",
  "scope": "BRAND_A:EMAIL",
  "status": "GRANTED",
  "validFrom": "2026-02-01T09:00:00Z",
  "validTo": "2026-03-10T10:00:00Z"
}
~~~

A unique index on **(subject, purpose, validFrom)** does not prevent two intervals starting at different times from overlapping. You need transactions, stream locking, or validation appropriate to the chosen document database's guarantees.

### 21.2. Graphs Must Check All Related Edges

A subject may link to a brand and a conditional purpose. Querying "did the subject have a grant for Brand A at time T?" must check **the consent edge's timestamps**, and if necessary **the subject–brand/contact edge's timestamps**. Querying a current edge can mis-infer authorization for a historical event.

### 21.3. Warehouses Are Projections, Not Necessarily Authoritative Decision Sources

A warehouse used for campaign analytics may store consent status as of ingestion time. If data arrives late, yesterday's snapshot table may not reflect a newly effective withdrawal. Never use a marketing segment exported yesterday as the sole basis for sending today.

An authoritative consent service or policy engine should provide **execution-time verification rules** matching the defined SLA.

## 22. Indexing, Partitioning, Retention, and Privacy

### 22.1. Queries to Optimize

| Query pattern | Supporting structure |
|---|---|
| One subject + purpose + scope at T | Composite scope key + GiST range |
| All decisions for a subject | Index on tenant, subject, accepted_at |
| Decision by request ID | UNIQUE on tenant, capture_source, source_decision_key |
| Grants due to expire | Index on `upper(valid_period)` or appropriate deadline job |
| History by tenant and time | Controlled partitioning/archival |
| Auditing notice per decision | FK `notice_id` and immutable content storage |

Example audit index:

~~~sql
CREATE INDEX ix_consent_decision_subject_time
ON consent_decision (
    tenant_id, subject_id, accepted_at DESC
);
~~~

The state history GiST exclusion already creates an index supporting equality and overlap predicates by scope. Measure real queries before adding more indexes; some workloads may benefit from a separate B-tree for a current-state projection.

### 22.2. Do Not Time-Partition in a Way That Breaks Overlap Constraints

If `state_history` is split into monthly tables by `effective_at`, a `valid_period` interval can span multiple months. Two overlapping intervals sitting in different partitions will not be caught by a local `UNIQUE/EXCLUDE`.

PostgreSQL has constraints on cross-partition uniqueness/exclusion depending on layout and version. For consent, **state correctness comes first**: consider keeping the state history table with a centralized constraint, partitioning the decision log by `accepted_at`, or using a stream lock/registry point to validate the entire timeline before writing.

Never choose partitioning merely to `DROP` old data quickly if doing so allows `GRANTED` and `WITHDRAWN` states to be active simultaneously.

### 22.3. Retaining Proof Does Not Mean Retaining All PII Forever

The decision log must be able to prove how choices were collected and changed. Yet retention must have a **purpose, duration, read authorization, and deletion/anonymization mechanism per applicable requirements**.

Practices:

- Use a **pseudonymous subject_id** instead of copying emails/addresses directly.
- Separate the real-identity mapping table from the consent log.
- Restrict payloads via field allowlists.
- Protect notices, evidence, logs, and exports.
- Enforce role- and tenant-based access control.
- Define retention for evidence, state history, processing records, and backups.
- Track erasure, restriction, and legal requests independently from withdrawal.
- Do not auto-delete all proof upon withdrawal if proof obligations remain; equally, do not retain data beyond what is necessary.

**Append-only is a logical audit rule, not a license to store personal data indefinitely.**

## 23. Common Mistakes

| Practice | Why it is wrong or incomplete | How to improve |
|---|---|---|
| Single `marketing_consent` column | Unknown purpose, scope, time, notice | Consent per subject–purpose–scope |
| New choice overwrites old state | Loses ability to prove history | Decision log and state intervals |
| No distinction between DENIED and UNKNOWN | Misrecords subject's decision | Separate missing-proof state |
| Not recording notice version | Unknown what text was shown | Immutable notice version + reference |
| Assuming all consent lasts forever | Ignores expiry, corrections, withdrawal | Validity intervals and policies |
| Using `received_at` as `valid_from` everywhere | Wrong when effective time differs from receipt | Define each time axis separately |
| Using client timestamp to backdate grants | Can legitimize processing prior to proof | Verify authoritative effective timestamp |
| Treating missing rows as TRUE | Fail-open on consent-required paths | Unknown → no active grant |
| Applying email grant to push | Exceeds consented scope | Separate purpose/channel/scope |
| Caching grants all day without invalidation | Sends after withdrawal | Final check/suppression/version |
| Joining history by subject without purpose | Fan-out and wrong authorization inference | Full composite scope key |
| Allowing overlapping state versions | Ambiguous state at T | EXCLUDE/transactions and tests |
| Emitting event without updating projection | Downstream diverges from source | Outbox, versioning, reconciliation |
| Treating withdrawal as deleting all data | Ignores other obligations/evidence | Separate retention and rights workflows |
| Event replay re-sends emails | Unintended duplicate side effects | Separate projection replay from actions |
| Relying solely on a slow warehouse | Stale activation state | Check at point of execution |
| Multi-purpose request shares one decision key | Unique conflict or lost choices | Unique key per choice, shared correlation |

## 24. Testing State, Time, and Processing Authorization

A test suite must use **deterministic expected-outcome scenarios** rather than only checking that `INSERT` succeeds.

### 24.1. Sample Timeline Tests

| Scenario | Expected outcome |
|---|---|
| Grant `MARKETING_EMAIL` Brand A from Feb 1 | `GRANTED` on Mar 5 |
| Withdrawal at exact Mar 10 10:00 | No longer `GRANTED` at boundary |
| Query on Mar 20 | `WITHDRAWN` |
| Re-grant from Apr 2 08:00 | `GRANTED` on Apr 5 |
| Query before initial grant | No record / `UNKNOWN`, never infer `GRANTED` |
| Query `MARKETING_PUSH` | Cannot use `MARKETING_EMAIL` grant |
| Query same purpose for Brand B | Cannot use Brand A grant beyond confirmed scope |
| Expiry at May 1 | After May 1, no active grant |
| Two overlapping states for same scope | Rejected by database/validator |
| Two different scopes at the same time | Allowed if purpose and scope are valid |

### 24.2. Concurrency and Idempotency Tests

1. Two workers updating consent for the same scope concurrently do not produce two overlapping states.
2. A `GRANT` request that times out after commit and is retried does not create a second decision/version.
3. Same `source_decision_key` with different action or evidence raises a conflict.
4. Transaction writes decision successfully while projection write fails: both roll back together.
5. Missing scope row when two requests start simultaneously: creation path uses PK/unique with controlled retry.
6. Late-arriving data with past `effective_at` does not corrupt the timeline and does not retroactively legitimize past processing.
7. Two decisions with identical `effective_at` have clear ordering/precedence and leave no empty interval.
8. Bitemporal queries at `K` before and after `accepted_at` return different system knowledge when a correction occurs.

### 24.3. Execution and Propagation Tests

1. An email scheduled before withdrawal but sent after withdrawal must be re-checked per applicable policy.
2. Consumer receiving `WITHDRAW` twice neither drops nor resurrects a grant.
3. Consumer receiving out-of-order events uses revision or authoritative source rather than regressing current state.
4. When the consent service is unavailable, consent-required paths follow the approved **fail-safe policy**.
5. Replaying historical events does not re-trigger campaigns or data sharing.
6. Subject ID splits/merges verify scope and proof rather than blindly merging grants across subjects.
7. APIs enforce tenant and authorization checks: another tenant's service cannot fetch consent records.
8. Withdrawal events are auditable from request, decision, and outbox through downstream acknowledgment.

### 24.4. Data Quality and Evidence Tests

- `GRANT` without notice or evidence is rejected when required by contract.
- `notice_id` matches the actual purpose and version presented.
- No tokens/passwords or out-of-scope PII stored in evidence.
- Date/time values include offsets; business dates are never compared to UTC timestamps without rules.
- Any state record referencing a decision with mismatched tenant/purpose/scope is detected.
- Once retention expires, history APIs report data is no longer available under retention rather than inferring `GRANTED`.
- Reconcile current projection against decision-log replay within the retained window.

## 25. Lab Exercise: Managing Choices for an E-Commerce Platform

A platform has customer **C-501**, two brands **A** and **B**, and these purposes:

- `MARKETING_EMAIL`: receive promotional emails.
- `MARKETING_PUSH`: receive promotional push notifications.
- `PERSONALIZATION`: behavioral personalization.
- `ORDER_NOTICE`: order status notifications under a processing basis defined separately by policy.

Timeline of events:

~~~text
2026-02-01 09:00 UTC:
  Brand A, MARKETING_EMAIL: GRANTED, notice v3
  Brand A, MARKETING_PUSH: DENIED
  Brand A, PERSONALIZATION: GRANTED, notice v2

2026-03-10 10:00 UTC:
  Brand A, MARKETING_EMAIL: WITHDRAWN

2026-03-10 11:00 UTC:
  Email worker has 1 campaign queued for sending.

2026-04-02 08:00 UTC:
  Brand A, MARKETING_EMAIL: Re-GRANTED, notice v4

2026-04-05:
  Brand B wants to use C-501's email to send offers.
~~~

### 25.1. Design Tasks

1. Specify the grain of `ConsentDecision` and `ConsentStateHistory`.
2. Design purpose and scope codes by tenant/brand/channel.
3. Choose PK, FK, and UNIQUE keys for subject, notice, decision, and scope.
4. Draw the state transition diagram `GRANTED → WITHDRAWN → GRANTED` for Brand A email.
5. Write DDL for `valid_period` as **[from, to)** and the non-overlapping constraint.
6. Build timelines for Brand A email, Brand A push, and Brand A personalization without mixing them up.
7. Write as-of queries for Mar 5, Mar 20, and Apr 5.
8. Explain why Brand B does not automatically inherit Brand A's grant.
9. Explain why `ORDER_NOTICE` may require a separate policy instead of relying on marketing consent.
10. Propose handling for the email worker queued at 11:00, including a final pre-send check.
11. If the app captured withdrawal offline at 10:00 but the server received it at 12:00, describe valid time and known time; do not infer legal conclusions from backdating alone.
12. Describe the transaction writing decision, state, and outbox, plus concurrency control.
13. Design idempotency when the app retries the same withdrawal request three times.
14. State a strategy for storing notice v3/v4 evidence without keeping unnecessary sensitive data.
15. Design tests for expiry, missing records, overlaps, wrong scope, late events, and duplicate downstream processing.
16. Define retention for proof, state, raw events, and ability to answer historical queries.

### 25.2. Guided Solutions

- Brand A email has `GRANTED`, `WITHDRAWN`, `GRANTED` intervals matching the table in Section 14.
- Brand A push has its own `DENIED`; Brand A personalization has its own `GRANTED`.
- Brand B has no grant in the appropriate scope, so permission cannot be inferred from Brand A.
- Email sending workers must re-check consent before execution or use suppression/invalidation meeting the SLA.
- `ORDER_NOTICE` must not be conflated with marketing consent; processing basis policy is a separate layer.
- Bitemporal modeling or replay with knowledge timestamps explains processing that occurred before the server received an offline withdrawal.
- Retention must keep necessary proof within defined limits rather than retaining all PII indefinitely by default.

**Acceptance criteria:** a consent change never erases history; permissions never bleed across purposes/scopes; as-of queries handle boundaries accurately; committed actions have proof; withdrawals propagate and are re-verified at execution points; missing data is never treated as consent granted.

## 26. Design Review Checklist

- **Subject:** is there an authoritative `subject_id` and clear tenant scope?
- **Purpose:** does each purpose have a stable code, description, and change policy?
- **Scope:** are controller, brand, channel, data category, and recipient represented exactly as disclosed?
- **State:** are `GRANTED`, `DENIED`, `WITHDRAWN`, `EXPIRED`, and `UNKNOWN` cleanly distinguished?
- **Evidence:** can notice version, locale, actual content, interaction, and decision ID be audited?
- **Time:** do event/client time, accepted/recorded time, effective time, `expires_at`, and known time each have distinct semantics?
- **Boundaries:** do all validity intervals use `[from, to)` and avoid overlaps within the same scope?
- **Constraints:** are PK, FK, UNIQUE, EXCLUDE, and scope–decision consistency enforced?
- **Concurrent writes:** are there stable locks/revisions and atomic transactions to prevent lost updates?
- **Retries:** do repeated identical source decisions avoid creating duplicate decisions while conflicting payloads are detected?
- **Withdrawal:** does it halt future processing within consent-required scope, with re-checks at execution time?
- **Downstream:** are outbox, event IDs, consumer idempotency, propagation lag, and reconciliation monitored?
- **Retrospective queries:** does the system preserve what was known at `K` if historical decisions must be proven?
- **Processing basis:** is consent kept distinct from overall processing authorization, with separate policy evaluation?
- **Privacy:** are proof and logs minimized, access-controlled, retention/deletion-governed, and tamper-protected?
- **Multi-model:** when projecting from relational to document/graph/lakehouse, are scopes and temporal invariants preserved?
- **Testing:** have timestamp boundaries, expiry, missing records, scope mismatches, race conditions, offline delays, and stale caches been tested?

**Conclusion:** a trustworthy consent model is not a `TRUE/FALSE` column on a customer table. It is a **conditional, time-bounded relationship among subject, purpose, scope, decision, and evidence**. The decision table preserves action history; the validity-interval state table supports as-of queries; the policy engine determines whether a specific operation is allowed. Good design ensures **permissions are never over-generalized from a single choice**, **trails are never lost upon withdrawal**, and **late-arriving information never rewrites history falsely**. Only when clear keys, constraints, time semantics, and access controls work together can consent data evolve and be verified in a distributed system.
