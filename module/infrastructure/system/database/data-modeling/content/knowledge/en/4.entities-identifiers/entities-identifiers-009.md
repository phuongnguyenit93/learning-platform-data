# Distinguishing Duplicate Records from Two Entities with Identical Attributes

## 1. Why Must Duplicate Records Be Distinguished from Different Entities?

During data collection and integration, a system can encounter two situations that look very similar on the surface:

- Two records describe **the same real-world entity** yet were created or imported into the system multiple times.
- Two records share some or even many identical attributes, yet actually describe **two different entities**.

For example, two customers sharing the name "Nguyễn Minh Anh" and birthdate 12/04/1995 are not necessarily the same person. Conversely, one customer may appear as "Nguyễn Minh Anh" in the sales system and "Minh Anh Nguyen" in the customer support system, yet still be the same person.

Confusing these two situations causes two kinds of errors:

- **False positive (erroneous merge):** two different entities are treated as one. Their data can get mixed, access rights misassigned, or transactions attributed to the wrong person.
- **False negative (missed duplicate):** multiple records for the same entity stay separate. Reports may count one customer multiple times, send duplicate notifications, or produce inconsistent profiles.

Therefore, the data model must separate the concepts of **record**, **entity**, and **identity**. A record is how the system stores a set of data; an entity is the object or thing that data describes; identity is the basis for knowing whether records refer to the same entity.

## 2. Distinguishing Identical Attribute Values from Identical Identity

### 2.1. Attribute Equality Does Not Imply the Same Entity

Suppose the system stores two profiles:

| Attribute | Profile A | Profile B |
|---|---|---|
| Full name | Trần Minh An | Trần Minh An |
| Date of birth | 10/08/1990 | 10/08/1990 |
| City | Đà Nẵng | Đà Nẵng |
| Email | an.one@example.test | an.two@example.test |
| Profile code | C-1001 | C-2048 |

Both profiles share the same name, date of birth, and city, yet have different emails and profile codes. That is not enough to conclude they are two different people, because one person can use multiple emails. Nor is it enough to conclude they are the same person. More evidence and understanding of how the system issues codes are required.

An attribute describes one facet of an entity. Multiple entities can share the same value on that facet. Personal names, dates of birth, common product names, building addresses, or area codes are not necessarily unique.

### 2.2. Attribute Differences Do Not Imply Different Entities Either

An entity can change over time. Customers move houses, change phone numbers, change full names, or update emails. If two records differ in address, you cannot automatically conclude they are two different customers.

Distinguish among:

- **Stable attributes:** rarely change and can assist identification, such as an identifier issued by an authoritative agency or system within a defined scope.
- **Volatile attributes:** can change over time, such as address, phone number, email, status.
- **Shareable attributes:** multiple entities can hold the same value, such as full name, date of birth, city, or product name.
- **Contextual attributes:** unique only within a scope, such as employee ID within a company or room number within a building.

To determine whether two records share an entity, examine the meaning, stability, scope, and provenance of each attribute.

## 3. What Is a Duplicate Record?

A duplicate record occurs when multiple rows or documents describe the same entity or event under business rules, even though they may differ in representation or certain attributes.

Common causes:

- A user creates a profile multiple times after failing to find the old profile.
- A request is retried after a timeout without idempotency on the creation operation.
- Data is imported from multiple files or multiple source systems.
- A system re-syncs data without recognizing an already existing record.
- The same person is recorded with different spellings of name, address, or phone number.
- Identification rules changed without consolidating historical data.

For example, the same customer may be recorded as two profiles:

| customer_id | full_name | email | source |
|---|---|---|---|
| 501 | Nguyen Thi Mai | mai@example.test | Web |
| 892 | Mai Nguyen | MAI@example.test | CRM |

If email normalization is case-insensitive and evidence confirms both profiles belong to the same customer, these may be duplicate records. However, do not merge solely on matching email if the system permits shared addresses or if emails are unverified.

Duplicate records do not have to match byte for byte. One record may lack a phone number while the other has a new address; one source may use Vietnamese diacritics while another strips diacritics. Recognizing duplicates requires understanding both data and business context.

## 4. Two Different Entities with Identical Attributes

Two different entities can share many descriptive attributes. This is especially common when the chosen attributes lack uniqueness.

Examples:

- Two people sharing full name, date of birth, and city.
- Two products sharing a commercial name yet from different manufacturers or versions.
- Two rooms sharing code "A101" yet located in two different buildings.
- Two businesses sharing a display name yet having different registration numbers.
- Two transactions with the same amount and close timestamps yet executed by two different accounts.

To prevent erroneous merges, define identification scope. For example, room codes are unique only within a building:

```sql
UNIQUE (building_id, room_code)
```

Two `A101` rooms in two different buildings are two valid entities. Placing `UNIQUE(room_code)` alone causes the database to reject valid data. Without an appropriate constraint, the system may link the wrong room when querying solely by local code.

### 4.1. Entities and Records Do Not Have an Absolute One-to-One Relationship

One entity can have multiple records due to duplication or history. One record can also describe multiple entities if the model improperly collapses data—such as storing two contacts in one text field or storing multiple devices in the same row without individual identifiers.

Consequently, do not infer identity solely from row counts or column similarity. The model must clearly define the managed object, its lifecycle, and how a record represents that object.

## 5. Identifier Types and Their Roles

### 5.1. Internal Identifiers

An internal identifier (surrogate identifier) is system-assigned, such as `customer_id` or a UUID. It distinguishes records within a system and usually remains stable throughout a record's lifecycle.

Example:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(320)
);
```

If two profiles have different `customer_id` values, they are two distinct records in the table. However, this does not prove they are two distinct real-world people. They could be two duplicate records created independently.

This is crucial: a primary key guarantees record identification inside the database; it does not automatically prove the real-world identity of the described object.

### 5.2. Business Identifiers

A business identifier is a code governed by business processes or an authoritative system—such as a tax ID, employee code, contract number, or an organization's customer code.

When using one, determine:

- Who issues the code and how many issuers exist?
- Is the code unique system-wide or only within an organization/unit?
- Can the code change or be reused?
- Is the code verified or merely user-entered?
- Are normalization rules applied before comparison?

A code unique only within an organization must be paired with the organization identifier when checking:

```sql
UNIQUE (organization_id, employee_code)
```

### 5.3. Source System Identifiers

When integrating multiple systems, each source may hold its own code for the same customer. Never assume source codes are globally unique.

Source identifier mappings can be stored:

```sql
CREATE TABLE customer_source_id (
    source_system VARCHAR(50) NOT NULL,
    source_customer_id VARCHAR(100) NOT NULL,
    customer_id BIGINT NOT NULL,
    PRIMARY KEY (source_system, source_customer_id),
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
```

The composite key `(source_system, source_customer_id)` distinguishes identical codes issued by different systems. Multiple source codes can map to one canonical `customer_id` once verified to describe the same customer.

This structure preserves data provenance and supports tracing if an erroneous linkage is discovered.

## 6. Entity Resolution: Identifying Records of the Same Entity

Entity resolution is the process of determining which records describe the same entity, even when their data differs. This process is also called record linkage or deduplication depending on context.

It can be broken into steps:

1. Normalize attributes used for matching.
2. Find candidate pairs of potentially related records.
3. Score match likelihood based on multiple attributes and rules.
4. Decide whether to auto-merge, route for human review, or keep separate.
5. Store results, evidence, and change history for traceability.

### 6.1. Data Normalization

Normalization reduces non-semantic formatting differences. Examples:

| Original Value | Illustrative Normalized Value |
|---|---|
| ` MAI.NGUYEN@EXAMPLE.TEST ` | `mai.nguyen@example.test` |
| `Nguyễn  Thị Mai` | `Nguyễn Thị Mai` |
| `+84 912 345 678` | `+84912345678` |
| `12 Đường Lê Lợi` | Address string parsed and standardized per rules |

Not every field can be normalized simply by lowercasing or stripping diacritics. Personal names must retain original forms for display; phone numbers require country-code normalization; addresses require parsing administrative components; emails have comparison rules depending on system policy and semantics.

Store both original and normalized values whenever exact display or traceability is needed.

### 6.2. Exact Matching and Fuzzy Matching

**Exact matching** compares normalized values or verified identifiers. For example, an identical contract code from the same source system can be strong evidence.

**Fuzzy matching** compares near-similar values, such as typos in names, abbreviation differences, or address variants. Usable methods include:

- Edit distance to measure character insertions, deletions, or substitutions.
- Jaro-Winkler to compare name strings sharing prefixes.
- Token similarity to compare words in names or addresses.
- Date matching within an allowed tolerance window.
- Phone number or email matching post-normalization.

No single fuzzy matching algorithm fits every field. Personal names, addresses, product codes, and ID numbers carry different semantics. Matching thresholds must be evaluated on labeled real-world data.

### 6.3. Combining Multiple Attributes

Never decide to merge based solely on one common attribute. Combine name, date of birth, email, phone, address, and source identifiers weighted by field reliability.

Example criteria table:

| Attribute | Matching Evidence | Relative Confidence |
|---|---|---|
| Verified identifier within same scope | Exact match | Very strong |
| Verified email | Match after normalization | Strong, depending on sharing policy |
| Phone number | Match after normalization | Medium to strong, depending on reuse potential |
| Full name | Exact or fuzzy match | Weak to medium |
| Date of birth | Exact match | Supporting, though insufficient alone |
| Address | Partial or fuzzy match | Supporting, as it can be shared or change |

This table is a relative guide only. Confidence depends on data quality, issuing source, verification workflows, and business domain.

### 6.4. Scoring and Decision Thresholds

A matching system can compute a score from multiple signals:

```text
Match score
  = w1 × name_score
  + w2 × dob_score
  + w3 × email_score
  + w4 × phone_score
  + w5 × address_score
```

Where weights `w1...w5` reflect reliability and total weight can be normalized to 1. This is an illustrative model only; real systems require training or calibrating weights on verified record pairs.

Results can be partitioned into three zones:

| Score / Condition | Action |
|---|---|
| Very high with strong identifier evidence | Auto-merge per validated policy |
| Intermediate or conflicting signals | Route to authorized human review |
| Low | Keep two profiles separate |

Do not tune thresholds merely to shrink record counts. Erroneous merges can cause far worse damage than missed duplicates, especially in healthcare, financial, access-control, or personal data.

## 7. False Positives and False Negatives

### 7.1. False Positive: Merging Two Different Entities

For example, two people sharing a name and date of birth are merged into one customer. Consequences can include:

- One person's purchase history becomes visible to the other.
- Invoices, loyalty points, or liabilities get misattributed.
- Access permissions and notifications are sent to the wrong recipient.
- Editing or deleting one person's data affects the other person.

To reduce false positives:

- Prioritize identifiers with clear provenance and scope.
- Never use name or address as a unique key unless guaranteed by business rules.
- Inspect conflicting evidence, such as two distinct verified identifiers.
- Use conservative auto-merge thresholds.
- Escalate uncertain cases to authorized human reviewers.
- Record rationale and evidence for merge decisions.

### 7.2. False Negative: Missing Duplicate Records

For example, one person has two profiles because one holds an old email and the other holds a new email, plus different name spellings. The system fails to detect the match and keeps two separate customers.

To reduce false negatives:

- Normalize values prior to comparison.
- Combine multiple attributes instead of exact-matching a single field.
- Use source identifiers when available.
- Search candidate pairs within likely duplicate buckets.
- Allow users to report suspected duplicate profiles.
- Periodically review newly created records and historical data.

The goal is not erasing every difference across records, but making well-founded identity decisions.

## 8. Safe Workflow for Handling Duplicate Records

### 8.1. Define Merge Rules Before Consolidating

Before updating data, determine:

- The entity type being processed: customer, product, employee, location, or event.
- Attributes used for identification and their confidence levels.
- Identifier scope: global, tenant, organization, source, or temporal.
- Which attributes are mutable.
- Which cases qualify for auto-merge vs. require review.
- Which system is the authoritative source for each attribute.

The same rules do not necessarily apply across all entities. Two products with the same name may be two distinct SKUs; two transactions with the same amount are not the same transaction.

### 8.2. Selecting the Canonical Record and Merging Attributes

Once two records are confirmed to represent the same entity, choose a canonical identifier (`canonical ID`). Then decide attribute resolution:

- Keep values from the authoritative source.
- Prefer verified values.
- Retain change history when values carry temporal significance.
- Record provenance and update timestamps.
- Never overwrite good data with missing or lower-confidence values.

For instance, profile A has a verified email while profile B has a newly verified phone number. The canonical record can keep both attributes alongside their respective sources, rather than taking every field from a single profile.

### 8.3. Migrating Referencing Relationships

If two customer records are merged, orders, support tickets, transactions, and other relationships must continue referencing the canonical customer.

You can maintain an old-ID-to-canonical-ID redirect table:

```sql
CREATE TABLE entity_id_redirect (
    entity_type VARCHAR(50) NOT NULL,
    old_entity_id BIGINT NOT NULL,
    canonical_entity_id BIGINT NOT NULL,
    merged_at TIMESTAMP NOT NULL,
    reason VARCHAR(500),
    PRIMARY KEY (entity_type, old_entity_id)
);
```

This table helps resolve legacy references, trace decisions, and transition integrated systems gradually. Prevent cyclic mappings—such as A pointing to B and B pointing back to A—and ensure the final canonical ID exists and holds a valid status.

Foreign key updates must run inside controlled transactions or recoverable workflows to avoid broken links. For large datasets, batch processing with progress tracking may be needed.

### 8.4. Never Erase Provenance Trails

After merging, do not erase all traces of the old record if the business requires auditing or historical explanation. Retain:

- Old ID and canonical ID.
- Timestamp, actor, or process performing the merge.
- Reason and evidence.
- Before and after attribute values if needed.
- Source systems of individual attributes.
- How related relationships were handled.

An erroneous merge decision must support rollback or unmerging whenever policy and data structures allow.

## 9. Preventing Duplicate Records at Write Time

### 9.1. Unique Constraints Matching Verified Rules

If the business has a clear unique identifier, protect it with a database constraint. For example, customer code unique within a tenant:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_code VARCHAR(50) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_customer_tenant_code
        UNIQUE (tenant_id, customer_code)
);
```

This constraint stops two records from using the same code within one tenant. It does not block two customers sharing the same name, because name is not defined as unique.

Add unique constraints only when business rules genuinely demand them. Placing `UNIQUE(full_name, birth_date)` could reject two different people who happen to share a name and birthdate.

### 9.2. Idempotency for Retried Requests

One source of duplicate records is a client retrying a request after a timeout without knowing whether the prior attempt succeeded. An idempotency key lets the system recognize the same business request arriving multiple times.

For example, for a payment creation request:

```sql
CREATE TABLE payment_request (
    request_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    payment_id BIGINT,
    CONSTRAINT uq_payment_request
        UNIQUE (tenant_id, idempotency_key)
);
```

Upon receiving a request, the system checks the idempotency key within tenant scope. If the key already exists, return the recorded outcome or handle according to prior status rather than creating a new transaction. Persist both the outcome and processing status to prevent two concurrent requests from creating duplicate records.

Idempotency stops duplicate replays of the same request; it does not solve cases where two users submit two different requests for the same underlying entity. Those cases still require identifier rules and entity resolution.

### 9.3. Pre-Checks and Write-Time Constraints

Applications can search for similar profiles before creating a new one to warn users. However, pre-checks do not replace unique constraints because two concurrent requests can both pass the pre-check.

Combine:

- Pre-checks for user experience.
- Database constraints for definite uniqueness rules.
- Matching workflows for cases needing fuzzy matching.
- Review and merge workflows for cases lacking sufficient evidence.

## 10. Evaluating Identification Process Quality

Do not measure quality solely by the count of merged records. Evaluate quality using human-verified ground truth or benchmark datasets.

Common metrics:

- **Precision:** among pairs predicted as duplicates, how many are truly duplicates?
- **Recall:** among truly duplicate pairs, how many did the system find?
- **False positive rate:** rate of distinct-entity pairs mistakenly predicted as duplicates.
- **False negative rate:** rate of same-entity pairs missed.
- **Review rate:** fraction of pairs routed to human reviewers.
- **Unmerge rate:** fraction of merge decisions that had to be reversed due to error.

Precision and recall formulas:

```text
Precision = True Positives / (True Positives + False Positives)

Recall = True Positives / (True Positives + False Negatives)
```

For example, the system proposes 100 duplicate pairs, of which 95 are confirmed true. Precision is 95%. If there are 120 actual duplicate pairs in the test set, recall is 95/120, approximately 79.2%.

High precision limits erroneous merges; high recall catches more duplicate records. Suitable thresholds depend on business risk. For sensitive profiles or financial transactions, prioritize precision and manual review for ambiguous cases.

## 11. Common Mistakes

- Assuming two records with the same name are the same person or product.
- Assuming two records with different IDs are definitely different real-world entities.
- Assuming every differing attribute proves two entities are distinct, even when attributes can change.
- Using a non-unique field such as address, date of birth, or name as an identifying key.
- Merging profiles based solely on fuzzy matching scores without inspecting conflicting evidence.
- Failing to distinguish internal IDs, business IDs, and source-system IDs.
- Over-normalizing data, losing original information or collapsing distinct values into false matches.
- Merging records without updating foreign keys and dependent systems.
- Deleting old records without saving mappings, provenance, or history.
- Checking duplicates only in the application without enforcing uniqueness rules via constraints.
- Treating an idempotency key as if it solves every case where two separate requests create the same entity.
- Measuring quality by merged profile count rather than precision, recall, and the impact of erroneous decisions.

## 12. Checklist for Distinguishing and Handling Duplicate Records

Before concluding two records represent the same entity, confirm:

- [ ] Entity type and business meaning of each record have been defined.
- [ ] Record identifiers are distinguished from real-world entity identity.
- [ ] Scope of each identifier has been defined.
- [ ] Attributes are classified as stable, volatile, or shareable.
- [ ] Data is normalized per suitable rules while retaining raw values when needed.
- [ ] Multiple signals are combined rather than relying on one common attribute.
- [ ] Conflicting evidence and false-positive risks have been examined.
- [ ] Uncertain cases are routed to a review workflow.
- [ ] Canonical ID and attribute-merging rules have been chosen.
- [ ] Foreign keys and source systems are migrated in a controlled manner.
- [ ] Old ID mappings, provenance, rationale, and merge history are preserved.
- [ ] Constraints and idempotency keys are applied at the proper business scope.
- [ ] Matching quality is evaluated using precision, recall, and verified samples.

Distinguishing duplicate records from two entities with identical attributes is a problem of identity and business context, not merely string comparison or finding identical rows. When the model clearly records identifiers, scope, provenance, and decision history, the system can reduce duplicate data while protecting boundaries between genuinely distinct entities.
