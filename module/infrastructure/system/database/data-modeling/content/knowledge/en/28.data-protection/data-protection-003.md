# Separating Identifying Information from Business Data When Appropriate

## Learning Objectives

After this lesson, you will be able to:

- Identify **direct identifying information**, **information linkable for re-identification**, and business data that can still constitute personal data in a given context.
- Decide **when to separate** identifying data from orders, transactions, events, and analytical warehouses, and when separation can break semantics or introduce unnecessary complexity.
- Design an **identity storage zone** and a **business data zone** using reference keys, least-privilege access, service contracts, and controlled re-identification workflows.
- Distinguish **physical separation**, **logical separation**, **pseudonymization**, **anonymization**, **tokenization**, **encryption**, and **hashing**, without promising protection levels a solution does not actually achieve.
- Write PostgreSQL schemas with tenant boundaries, foreign keys, locked shipping address records, and role-based read access; design APIs that avoid exposing PII unnecessarily.
- Handle flows for **order confirmation, delivery, support, analytics, reconciliation, data deletion/restriction, recovery, and schema changes**.
- Assess residual risks such as linkage via persistent identifiers, rare attribute combinations, copies in logs/CDC, backups, and test environments.

This lesson belongs to the **Data Protection** chapter of **DATABASE_DATA_MODELING**. The module's goal is to translate business requirements into models with clear entities, relationships, constraints, keys, indexes, and physical schemas, while choosing appropriate relational, document, graph, or analytical structures. Data protection is part of modeling: **placing the right data within the right access boundary** is often just as important as writing a fast query.

> This lesson covers **technical design and data governance workflows**, not conclusions about legal obligations in a specific jurisdiction. Protection requirements, lawful processing bases, retention limits, and data subject rights must be determined according to the policies and regulations applicable to the actual system.

## 1. The Problem: One Order Table Holding Too Much

An e-commerce application currently stores:

~~~text
orders
  order_id
  customer_id
  customer_name
  customer_email
  customer_phone
  shipping_address
  product_id
  product_name_at_confirmation
  unit_price_at_confirmation
  quantity
  total_amount
  currency
  confirmed_at
  status
~~~

Operations needs **order_id, status, timestamps, and monetary amounts** to measure workload. Analytics needs **order lines, quantities, amounts, and timestamps** to measure revenue. The logistics service needs **the address and phone number for the specific parcel being delivered**. Only certain customer support tasks need to look up **email** or contact the recipient.

If every department has `SELECT` access on this table, every operational query can also access personal contact details and residential addresses. When the table is replicated to search indexes, analytical warehouses, or logs, the footprint of identifying information expands further.

The goal of data separation is not "hiding columns to make a table prettier," but rather:

1. **Reducing the number of systems and people that need to hold identifying data.**
2. **Allowing business workflows to operate with technical identifiers that do not directly state who the person is.**
3. **Establishing control points** when a task has a legitimate reason to link an ID back to a person.
4. **Limiting blast radius** if a read model, report, or application account is compromised.
5. **Managing the lifecycle** of identifying information independently from transactional records retained under contractual obligations.

A typical target design looks like:

~~~text
              Customer registration / verification
                        |
                        v
             [Identity Data Zone]
               subject_ref -> name/email/phone
                        |
                   subject_ref
                        |
                        v
              [Order Business Zone]
            order_ref, subject_ref, status,
            locked price, order lines, timestamp
                        |
             +----------+------------+
             |                       |
             v                       v
     [Sales Aggregation]      [Delivery Service]
     no email/phone needed    fetches locked address
     usually does not need    via dedicated permission/
     subject_ref              contract
~~~

**subject_ref** is a system-issued pseudonymous linkage key. The fact that it contains no name or email **does not make the data anonymous**: the organization can still link back to the real person through the mapping table or auxiliary data.

## 2. Classifying Identifiers: Not Only Email and Phone Number

### 2.1. Direct and Indirect Identifiers

| Group | Examples | Risk / interpretation |
| --- | --- | --- |
| **Direct identifiers** | Full name with address, personal email, phone number, government ID | Can directly recognize or contact a person |
| **Persistent technical identifiers** | customerId, subject_ref, deviceId, account ID | Can link multiple behaviors of the same person, even without a name |
| **Linkable attributes / quasi-identifiers** | Date of birth, very small region, exact transaction timestamps, location, occupation | Combined with external sources, can identify a specific person |
| **Transactional data** | Orders, delivery routes, purchase history, spend level | Can constitute personal data when tied to a subject |
| **Contextually sensitive data** | Support notes, location history, risk assessment scores | Can cause harm if leaked, even without a name |
| **Authentication secrets** | Password hashes, session tokens, API keys | Require separate control; never co-locate "for convenient JOINs" |

For example, an analytical table drops names and emails yet retains a fixed **subject_ref**, exact purchase timestamps, and store IDs. If a viewer can join to the customer system or knows about a rare transaction, the data can still re-identify a person.

Therefore, classify based on **linkability in the real operating environment**, not merely by checking whether a **full_name** column exists.

### 2.2. Identifiability Changes by Recipient

- The Order team may need **subject_ref** to identify which customer owns an order.
- The Fraud team may need behavior across multiple orders without necessarily needing display names.
- The Dashboard service may only need **date × status × currency** and order counts.
- A third party receiving a small dataset might combine it with public information; lacking names does not guarantee safety.
- A database administrator with elevated privileges can read both business and mapping tables if they live in the same system without effective privilege separation.

**Rule:** identify who can access supplementary information and for what purpose before concluding a dataset is "non-identifying."

## 3. When Should You Separate, and When Should You Not Do It Mechanically?

Separation fits well when **a dataset is read broadly** while only a narrow set of use cases needs identifying information.

| Scenario | Typically appropriate design direction | Why |
| --- | --- | --- |
| Daily total orders dashboard | Use only facts/aggregates without emails or addresses | No need to identify individuals |
| Behavior-based risk scoring | Use subject_ref and approved features; look up identity via a separate workflow when needed | Reduces PII volume in analytics pipelines |
| Listing 20 recent orders for a signed-in customer | Order API returns orders for the authenticated subject, possibly without email | Read authorization and caller identity are handled at the boundary |
| Sending delivery notifications | Notification service may need phone/email via token or contact service | Only one consumer needs the contact channel |
| Printing shipping labels | Recipient/address snapshot per parcel with logistics permissions | Real data is needed to fulfill the task |
| Storing locked unit prices on invoices/orders | Keep a **business snapshot** at transaction time | Never destroy evidentiary records just because data can tie to a person |
| Customer support queries in a very small shop | Separate logically via views/roles first; weigh the cost of separate systems | Avoid complexity exceeding benefits |
| Truly aggregated data unlinkable to individuals in context | No need to keep personal links if unnecessary | Minimizes re-identification potential |

**Do not** separate under a slogan like "every name and address must vanish from every transaction" when the business must know **the accepted shipping address at order confirmation**, or when record-keeping obligations apply. Instead, place the **delivery snapshot** in a restricted-access zone with appropriate retention and correction rules.

**Do not** create a remote identity service solely to look like "microservices": if every checkout request must make multiple cross-network calls without failure strategies, availability can suffer. The degree of separation should match the risk, system scale, operational capability, and transactional requirements.

### 3.1. Field-Level Decision Questions

Before placing a field in a business table, ask:

1. Is it **data needed for business decisions**, **contact information**, **transactional evidence**, or an **aggregated value**?
2. Does a reader of this table **need to know who the subject is** to perform the task?
3. Should the field **stay fixed as of transaction time** or **follow the current profile**?
4. If the link to identity is removed or separated, can **business invariants** still be verified?
5. If this table alone leaks, to what extent could outsiders link it with other sources?
6. Does separation introduce **cross-database transactions, latency, reconciliation overhead, or outages when the identity service is unavailable**?
7. Does the field fall under special **retention, deletion/redaction, audit, and export** rules?

Answering at the **field and use-case** level is usually far more accurate than a blanket command to "move all PII to another database."

## 4. Reference Model: Identity, Business, Delivery, and Analytics

A balanced design for e-commerce:

~~~text
commerce.customer_subjects
  (tenant_id, subject_ref)          -- persistent technical identifier

pii.customer_contacts
  (tenant_id, subject_ref)          -- current name, email, phone

commerce.orders
  (tenant_id, order_ref)
  subject_ref                       -- nullable per approved unlink policy
  order_state, confirmed_at, amount, currency

commerce.order_lines
  (tenant_id, order_ref, line_no)
  product_ref, quantity,
  unit_price_at_confirmation

pii.order_delivery_snapshots
  (tenant_id, order_ref)
  recipient_name, phone, address_at_confirmation

analytics.daily_order_metrics
  (business_date, currency, status)
  order_count, confirmed_amount
~~~

### 4.1. Why Separate Identity, Business Customer, and Recipient?

- **Customer/subject** is the business entity performing transactions. It can exist under a stable code without storing email.
- **Contact** is a **current** contact method that can be updated, verified, revoked, or deleted per policy.
- **Recipient** is the person receiving a parcel/order, who may **differ from the buyer**. Blindly joining to the customer's current contact to print labels can ship to the wrong address or leak data.
- **Order snapshot** holds the confirmed delivery address or per-shipment address version, requiring dedicated operational access and retention lifecycle.
- **Analytics** generally does not need recipient names. If customer-cohort analysis is needed, explicitly decide whether a stable pseudonym is truly necessary or whether safer aggregation suffices.

Separating identity from business data **does not mean deleting all join keys**, but rather keeping **only the minimal reference keys** and controlling identity resolution.

### 4.2. Two Types of Relationships Must Be Modeled Explicitly

| Relationship | Nature | How it updates |
| --- | --- | --- |
| **subject_ref → current contact** | Contact profile can change over time | Updated from the Customer/Identity source |
| **order_ref → locked delivery snapshot** | Fulfillment fact at confirmation time | Keep snapshot; use traceable revisions/adjustments when permitted |
| **order_ref → subject_ref** | Connects buyer and business record | Unlink only under approved policy without destroying audit trails |
| **fact → analytics aggregate** | Derived data serving metrics | Refresh/reconcile by grain and timestamp |
| **subject_ref → real identity** | Re-identification capability | Accessed only under controlled permissions and purpose |

If a single **address** column is used everywhere without distinguishing **current vs at_confirmation**, a "keep data in sync" job might rewrite delivery history. That is a modeling bug, not just a security bug.

## 5. PostgreSQL: Logical Separation Schema with Clear Keys and Relationships

This example uses **two schemas within the same PostgreSQL instance**: **commerce** for business operations and **pii** for identifying data. This organizes permissions and design cleanly, **but does not create a complete physical security boundary**; database owners, superusers, shared backups, and misconfigurations can still reach both zones.

The following SQL is an **illustrative model**, not a complete production security configuration. UUIDs are generated by the application tier from an appropriate random source or via a controlled ID issuer.

### 5.1. Technical Identifier Without Exposing Name/Address

~~~sql
CREATE SCHEMA commerce;
CREATE SCHEMA pii;

CREATE TABLE commerce.customer_subjects (
    tenant_id BIGINT NOT NULL,
    subject_ref UUID NOT NULL,
    subject_state TEXT NOT NULL
        CHECK (subject_state IN ('ACTIVE', 'RESTRICTED', 'CLOSED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, subject_ref)
);
~~~

**subject_ref** is a persistent random identifier generated and managed under contract. Never embed email/phone into IDs, and avoid meaningful codes such as birth date + region code. Depending on risk, you can issue **different codes per audience or purpose** to limit cross-system linkage.

Even when identity cannot be read directly from a UUID, anyone able to view multiple orders sharing a `subject_ref` can still infer a person's behavior. **Pseudonymized data must still be controlled according to personal-data risk**.

### 5.2. Current Identity Table Restricted to Authorized Parties

~~~sql
CREATE TABLE pii.customer_contacts (
    tenant_id BIGINT NOT NULL,
    subject_ref UUID NOT NULL,
    legal_name TEXT,
    email TEXT,
    phone_e164 TEXT,
    contact_updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, subject_ref),
    FOREIGN KEY (tenant_id, subject_ref)
        REFERENCES commerce.customer_subjects(tenant_id, subject_ref)
        ON DELETE RESTRICT
);
~~~

This table holds **current contacts**, not transactional record history. If regulations require keeping contact change history, design dedicated versioning/retention and access controls; never write unbounded PII logs.

In this example, email and phone are `TEXT` for structural clarity. Real systems need validation/normalization, verification mechanisms, search policies, and potentially **application-level encryption**. Never claim that placing two fields in the **pii** schema encrypts them automatically.

**PRIMARY KEY (tenant_id, subject_ref)** prevents two current contacts for the same subject in a single-contact model. If a user can have multiple emails, phones, or recipients, change the grain to one contact method/record with its own key. Never stuff multiple values into one comma-separated `TEXT` field.

### 5.3. Business Tables Without Names/Emails by Default

~~~sql
CREATE TABLE commerce.orders (
    tenant_id BIGINT NOT NULL,
    order_ref UUID NOT NULL,
    subject_ref UUID,
    order_state TEXT NOT NULL
        CHECK (order_state IN (
            'CONFIRMED', 'PROCESSING', 'SHIPPED',
            'DELIVERED', 'CANCELLED'
        )),
    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmed_amount NUMERIC(18, 2) NOT NULL
        CHECK (confirmed_amount >= 0),
    currency CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, order_ref),
    FOREIGN KEY (tenant_id, subject_ref)
        REFERENCES commerce.customer_subjects(tenant_id, subject_ref)
        ON DELETE RESTRICT
);

CREATE TABLE commerce.order_lines (
    tenant_id BIGINT NOT NULL,
    order_ref UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_ref UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    PRIMARY KEY (tenant_id, order_ref, line_no),
    FOREIGN KEY (tenant_id, order_ref)
        REFERENCES commerce.orders(tenant_id, order_ref)
        ON DELETE CASCADE
);

CREATE INDEX ix_orders_by_subject_recent
    ON commerce.orders (
        tenant_id, subject_ref, confirmed_at DESC, order_ref DESC
    );
~~~

**Grain and invariants:**

- Each **orders** row is one order within one tenant.
- Each **order_lines** row is one confirmed order line, identified by **(tenant_id, order_ref, line_no)**.
- **confirmed_amount** is an order-grain monetary amount; do not `SUM` this field after joining multiple `order_lines` without aggregating at the right level.
- **unit_price_at_confirmation** is the locked price, not synchronized with current catalog prices.
- **subject_ref** in `orders` enables querying orders by subject while allowing **NULL** via an approved unlinking workflow if business and retention obligations allow. Never arbitrarily delete/null it to bypass audit obligations.
- Composite foreign keys preserve **tenant_id** across joins, reducing cross-tenant reference mistakes by design.
- **ON DELETE CASCADE** on `order_lines` only expresses structural dependency when an authoritative owner deletes an order. It is **not** an automatic policy to erase transaction records; order deletion must be governed by workflow and retention rules.

### 5.4. Locked Delivery Address in a Restricted Zone

~~~sql
CREATE TABLE pii.order_delivery_snapshots (
    tenant_id BIGINT NOT NULL,
    order_ref UUID NOT NULL,
    recipient_name TEXT NOT NULL,
    recipient_phone TEXT,
    address_line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    country_code CHAR(2) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_ref),
    FOREIGN KEY (tenant_id, order_ref)
        REFERENCES commerce.orders(tenant_id, order_ref)
        ON DELETE CASCADE
);
~~~

This table is a **transaction-event snapshot**, distinct from current **pii.customer_contacts**. Changing a default profile address must never overwrite **order_delivery_snapshots**. If an order supports multiple shipments, parcels, or post-confirmation address changes, the grain may become **(tenant_id, order_ref, delivery_revision)** or **shipment_ref**, rather than one row per order.

This example covers **physical orders requiring delivery**. For digital orders, a delivery record may not need to exist at all. Once full addresses are no longer needed for operations or records, apply policy-driven deletion/redaction rather than keeping them forever because "snapshots are immutable."

### 5.5. What Is Logical Separation vs. Real Control Assurance?

Placing tables in different schemas is purely **namespace and privilege organization**. If the same application account holds `SELECT` on both **commerce.orders** and **pii.customer_contacts**, it can still join the two zones. If a DBA can back up the entire database, backups contain both business and identifying data.

The model provides real protection only when paired with:

- Least-privilege **database roles and table/column grants**.
- **Service APIs** restricting re-identification, enforcing object- and purpose-level authorization.
- **No exporting of identifying data** into projections or analytical warehouses unless needed.
- **Key, backup, log, and test-environment management** aligned with real boundaries.
- **Testing and auditing** across all direct and indirect data access paths.

## 6. Business Queries Without Joining Names/Emails

For example, a dashboard needs total confirmed order value by Vietnam business date and currency, without knowing who the customers are:

~~~sql
SELECT
    (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS business_date,
    currency,
    COUNT(*) AS order_count,
    SUM(confirmed_amount) AS confirmed_order_value
FROM commerce.orders
WHERE order_state IN (
    'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'
)
  AND confirmed_at >= $1::TIMESTAMPTZ
  AND confirmed_at <  $2::TIMESTAMPTZ
GROUP BY
    (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
    currency
ORDER BY business_date, currency;
~~~

The query touches no **pii** tables and does not return **subject_ref**. The output represents **confirmed** order value, which **does not automatically equal collected revenue**; refunds, statuses, taxes, discounts, and recognition timing require their own definitions.

Never directly sum VND and USD. Even within one currency, `SUM` must run at **order grain**. Joining multiple order lines and then summing **confirmed_amount** multiplies order totals by line counts.

### 6.1. Personal Order List Pages Only Need Partial Data

A "my recent orders" API can fetch:

~~~sql
SELECT
    order_ref,
    order_state,
    confirmed_at,
    confirmed_amount,
    currency
FROM commerce.orders
WHERE tenant_id = $1
  AND subject_ref = $2::UUID
ORDER BY confirmed_at DESC, order_ref DESC
LIMIT 20;
~~~

Here:

- **$1** must come from the authenticated tenant context.
- **$2** is the `subject_ref` mapped by the Identity/Authorization service from the **current principal**, **not** taken directly from a client-supplied query parameter.
- The service returns only **order_ref, status, timestamp, and amount**, omitting `subject_ref` if the UI does not need it.
- If a customer holds multiple valid accounts or shares order visibility, ownership must be defined by business rules and authorization, not merely comparing a UUID.

**Never rely on UUID unpredictability** in place of authorization checks. Swapping IDs in a URL can still cause unauthorized access if the backend fails to verify tenant and owner.

### 6.2. When Re-Identification Is Needed, Invoke an Authorized Capability

For example, a support agent needs to send an email regarding a specific order. One flow could be:

~~~text
Support user -> Support Service
    |
    | Verify role, tenant, purpose, and order read access
    v
Order Service -> verify order_ref, status, subject_ref
    |
    | Request Contact Service: purpose=ORDER_SUPPORT
    | pass subject_ref over authenticated internal channel
    v
Contact Service
    | Check policy, write audit log
    | Return only email/phone needed for the task
    v
Support Service -> execute contact action, limit logging/caching
~~~

**Do not automatically return all Contact fields.** If the workflow only needs to send a notification, Contact Service can dispatch it directly rather than returning the email to Support Service—reducing the number of places seeing identifiers.

If Contact Service is unavailable, the application must define explicit behavior: controlled retries, task queuing, or reporting that contact is temporarily unavailable. **Never fall back to reading the `pii` table with a super-privileged account** as a default incident workaround.

## 7. Database Permissions: Separating Roles Without Schema Illusions

Suppose roles **commerce_reader** and **contact_reader** are provisioned through the organization's standard grant process. Illustrative grants:

~~~sql
-- Restrict default entry to the identity schema.
REVOKE ALL ON SCHEMA pii FROM PUBLIC;

-- Only granted accounts receive USAGE and SELECT.
GRANT USAGE ON SCHEMA commerce TO commerce_reader;
GRANT SELECT (
    tenant_id, order_ref, order_state,
    confirmed_at, confirmed_amount, currency
) ON commerce.orders TO commerce_reader;

GRANT USAGE ON SCHEMA pii TO contact_reader;
GRANT SELECT (
    tenant_id, subject_ref,
    legal_name, email, phone_e164
) ON pii.customer_contacts TO contact_reader;
~~~

In real systems, account for pre-existing grants, schema/table/column privileges, role inheritance, default privileges on new tables, object ownership, `SECURITY DEFINER` functions, row-level security, and migration accounts. **A schema-level REVOKE does not automatically revoke existing table grants**; thorough control requires auditing all privilege paths and view/function invocation rights.

Column-level `SELECT` grants also **do not enforce tenant isolation on their own**. If `commerce_reader` can execute arbitrary SQL and read every tenant in `orders`, that remains overly broad for a multi-tenant application.

### 7.1. Row-Level Security and Its Limits

PostgreSQL supports tenant-based RLS policies, for instance for a dedicated query role:

~~~sql
ALTER TABLE commerce.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE commerce.orders FORCE ROW LEVEL SECURITY;

CREATE POLICY commerce_orders_tenant_read
ON commerce.orders
FOR SELECT TO commerce_reader
USING (
    tenant_id =
      NULLIF(current_setting('app.tenant_id', true), '')::BIGINT
);
~~~

A trusted backend can set **app.tenant_id** inside a transaction after authenticating the principal and tenant, then query using the RLS-constrained role. **However, this is not a standalone barrier if clients can run arbitrary SQL or set GUCs**: a role allowed to `SET` arbitrary values can spoof tenants. Lock down entry points, prevent users from running ad-hoc SQL under that role, and apply stronger authorization models where risk warrants.

RLS also has bypasses/exceptions such as superusers, the **BYPASSRLS** attribute, owners in certain setups, and access via views/functions; **FORCE ROW LEVEL SECURITY** does not turn it into protection against every privileged account. Verify against your exact architecture and PostgreSQL version.

Even with accurate RLS, responses/APIs still need **object- and purpose-level authorization**. Permission to view an order does not automatically grant permission to view the recipient's phone number.

### 7.2. Separate Within the Same Database or Into a Separate Service?

| Separation level | Example | Benefits | Costs / limits |
| --- | --- | --- | --- |
| **Columns and allowlisted DTOs** | Omit email from Order API | Minimal change; reduces response exposure | Roles with table `SELECT` still see PII |
| **Separate tables/schemas in same DB** | `pii.customer_contacts` and `commerce.orders` | Clearer privileges and retention; retains FKs/transactions | DBAs, backups, and privilege config remain shared |
| **Separate database** | Contact DB and Order DB | Shrinks account/backup scope; independent access control | No native cross-DB FKs; complex sync and reconciliation |
| **Identity/vault service** | Controlled, audited contact lookup API | Centralizes re-identification gate; can act instead of returning PII | Latency, availability, operational and integration cost |
| **Encryption key / security domain separation** | App-layer encrypted contacts with isolated keys | Limits impact if only DB copy leaks | Complex key management; does not stop leaks at decryption points |

No single tier is a universal standard for every product. **Both physical and logical separation require access governance**, and splitting across many stores can increase unmanaged copies if integration flows are poorly designed.

## 8. Pseudonymization, Tokenization, Hashing, Encryption, and Anonymization

These terms are frequently conflated, leading to misjudged protection levels.

### 8.1. Pseudonymization: Replacing Identifiers While Linkability Remains

**Pseudonymization** replaces direct identifiers with another code, for example:

~~~text
Customer: subject_ref = "6d03...e2c" (random UUID)
Identity mapping: subject_ref -> email, name, phone
Order data:       subject_ref -> purchased orders
~~~

As long as the mapping exists, orders can be linked back to a person. Even if the mapping is deleted, detailed attributes and auxiliary sources can still allow inferring identity. **Never call pseudonymized data anonymous.**

Its primary benefit is **limiting who can identify**, not promising "nobody can re-identify."

### 8.2. Tokenization: Replacement Tokens and Mapping Vaults

A **random token** with no embedded meaning can map to the original value inside a vault:

~~~text
payment_contact_token: "tok_..." (not an email)
          |
          v
Token vault -> protected email or delivery channel
~~~

Tokens can **vary per consumer/purpose** to curb cross-linking. Design must specify:

- Who issues tokens and guarantees uniqueness?
- How long does a token remain stable?
- What can a token be used to retrieve?
- Who can detokenize, read data, or only trigger actions?
- Could a leaked token be abused as a bearer credential?
- When mappings are revoked, rotated, or deleted, how do consumers react?

Tokenization and pseudonymization overlap technically. What matters is not the label, but **reversibility/linkability, where mappings reside, and access controls**.

### 8.3. Identifier Hashing: Beware of Emails and Phone Numbers

A common flawed choice:

~~~text
customer_hash = SHA256(lowercase(email))
~~~

Emails and phone numbers have **predictable value spaces**. If a party can test an email list and compare hashes, values do not become anonymous. Reusing the same unkeyed hash across datasets also creates a **cross-system join key**.

When a **deterministic lookup index** without plaintext storage is genuinely required, consider **HMAC with a secret key and explicit normalization rules**, while noting:

- It remains linkable data; **not anonymization**.
- Keys must be managed and permissioned independently, with rotation strategies.
- Same input + same key yields the same output, enabling unwanted correlation.
- Changing email/phone normalization rules can cause mismatches.
- Anyone permitted to invoke HMAC as an oracle on arbitrary inputs can run dictionary attacks and abuse access.
- If fuzzy search is required, HMAC does not solve it naturally; search must be designed separately.

Password hashing is a different problem (requiring dedicated password hashing functions with per-password salts and tunable work factors); never copy an "email hash" pattern for passwords.

### 8.4. Encryption Protects Content While Undecrypted

**Encryption at rest** or **application-level encryption** can protect emails/addresses against certain unauthorized access paths. Choose vetted authenticated algorithms, manage nonces/IVs, keys, tenant context, and rotation using approved libraries/services; never invent custom cryptography.

Questions you must answer:

- **Where and by which role** is data decrypted?
- Are keys stored alongside ciphertext or backups?
- Do logs, traces, caches, or query results retain plaintext after decryption?
- Is object-level authorization enforced prior to decryption?
- When rotating keys, how is older data read or re-encrypted?
- When email search is required, what lookup mechanism is used and what query-pattern leakage risks exist?

**Encryption does not replace authorization.** A compromised service authorized to decrypt every record can still leak the entire dataset.

### 8.5. Anonymization Requires Re-Identification Risk Assessment

A dataset containing only **order counts by date and currency** may carry lower risk than per-customer data, yet **aggregation does not automatically guarantee anonymity**. Tiny groups, overly granular timestamps, or overlapping filters can still expose one person's behavior.

True **anonymization** requires evaluating processing methods, available auxiliary data, likely attackers, re-identification risk, and acceptable information loss. Techniques such as minimum group thresholds, time/geo coarsening, query restrictions, or formal statistical disclosure controls may be necessary. **Deleting `full_name` is insufficient** to call a dataset anonymous.

## 9. Write Paths: Separating Data While Preserving Transactional Correctness

### 9.1. Customer Registration in the Same Database

When creating a new customer, both zones can be written in **one PostgreSQL transaction**:

~~~sql
BEGIN;

INSERT INTO commerce.customer_subjects (
    tenant_id, subject_ref, subject_state
)
VALUES ($1, $2::UUID, 'ACTIVE');

INSERT INTO pii.customer_contacts (
    tenant_id, subject_ref, legal_name, email, phone_e164
)
VALUES ($1, $2::UUID, $3, $4, $5);

COMMIT;
~~~

This assumes the backend validated inputs, checked collection policies, generated **subject_ref** once from a controlled random source, and derived tenant from a trusted context. If step 2 fails, the transaction rolls back both subject and contact.

This is the advantage of **schema separation inside one database**: transactions and FKs still work. Moving **pii.customer_contacts** to a separate database removes shared transactions and FKs, requiring subject creation protocols, idempotency, retries, reconciliation, and handling of half-created states.

### 9.2. Order Confirmation: Historical Data Needs Its Own Boundary

Suppose a customer selects a shipping address at checkout. Upon confirmation, the system must lock in:

- The buyer's **subject_ref**, with verified ownership.
- A unique **order_ref** for the order.
- Prices/quantities/terms computed from an authoritative source.
- **The confirmed shipping address**, which may differ from the current default contact.
- Order status, timestamp, and transaction version.

Within one PostgreSQL database, the application can insert **commerce.orders**, **commerce.order_lines**, and **pii.order_delivery_snapshots** in the same transaction after validating prices, inventory, and identity. Never commit the order first and emit an unreliable "please create delivery snapshot" message; if shipping requires that data, a missing snapshot is a business defect.

**Never pull addresses from the current profile each time you print labels for past orders.** If a user updates their contact details the next day, the order's accepted shipping address may need to remain preserved, or be modified only through an audited delivery-address amendment flow.

**Never duplicate all PII fields directly onto `order_lines`.** Line-item grain does not need recipient phone/email; doing so multiplies PII occurrences by line count.

### 9.3. Multiple Databases: Beyond Consistency, Consider Safety

When Identity and Order live in separate databases, consider a flow like:

~~~text
1. Order DB commits order referencing subject_ref.
2. Identity Service confirms subject is active.
3. Delivery Service creates snapshot/routing.
~~~

This ordering risks **TOCTOU** or partial states: the subject is restricted between steps 1 and 2, service 3 transiently fails, or the buyer changes addresses. Define **which truth is locked at which step** and how recovery works.

A common pattern is **local transaction + outbox + workflow state**:

- Confirm the order only when core business preconditions pass.
- Record an identifier-bearing event in the same Order transaction.
- Authorized consumers receive the event and execute subsequent steps with idempotency keys.
- When downstream steps fail, the order enters an observable state supporting retries or compensation; never report "shipped" prematurely.
- Any message carrying PII must use restricted channel contracts or carry only reference tokens resolved under authorization.

Outbox solves **reliable intent emission**, not turning multiple databases and external services into an atomic transaction. **Duplicate delivery, out-of-order events, and missing consumers** must still be designed for.

## 10. APIs and Events: Publish Only Data Needed for the Purpose

An Order API for an operations dashboard does not need contact details:

~~~json
{
  "orderId": "7d3f8a52-0ff2-4bb6-8c89-79d2acf6d313",
  "status": "PROCESSING",
  "confirmedAt": "2026-11-22T01:00:00Z",
  "confirmedTotal": {
    "amount": "310000.00",
    "currency": "VND"
  }
}
~~~

This payload can still relate to a person via the order ID and Order query permissions, so object-level access must still be enforced. However, it **does not proactively broadcast emails/phones/addresses** to consumers that do not need them.

A status integration event:

~~~json
{
  "eventId": "bfaef6c2-26e8-4874-a28e-2c1fc01080e6",
  "eventType": "OrderProcessingStarted",
  "schemaVersion": 1,
  "orderId": "7d3f8a52-0ff2-4bb6-8c89-79d2acf6d313",
  "orderVersion": 4,
  "occurredAt": "2026-11-22T01:03:00Z"
}
~~~

**Do not include `customer_contacts` by default in every `OrderUpdated` event.** Event buses have many subscribers; one consumer needing to contact a customer does not grant every subscriber a right to see emails.

### 10.1. Dedicated Logistics Contract

The delivery service needs exact recipient information. You can design:

~~~text
POST /delivery-requests/{deliveryRef}/resolve-contact
Caller: authorized Logistics Service
Purpose: FULFILLMENT
Resource: specific assigned shipment/order
Response: permitted recipient name, contact number, delivery address

Requirements:
- authenticate service identity
- verify assignment to the specific shipment/order
- enforce usage and retention time limits
- write audit log without full plaintext PII
~~~

This is a **privilege and business contract**, not just a REST route. If delivery goes through an external partner, also bound fields and access duration under the integration agreement. Revoke tokens/access once the need ends.

### 10.2. Analytics Usually Needs Less Than Assumed

Example of exporting a fact at **confirmed order line** grain:

~~~text
fact_order_line_confirmed
  event_date
  product_ref
  currency
  quantity
  unit_price_at_confirmation
  discount_allocated
  net_line_amount
  channel_code
  source_order_ref       -- only if needed for verification, with restricted permissions
~~~

Do not blindly add **email, phone, shipping_address, or risk_score** to facts. If cohort analysis is needed, attach **event-time segments** derived under approved formulas and policies rather than copying full personal profiles.

If **subject_ref** is kept in the warehouse for unique customer counts or repeat behavior, explicitly document **purpose, permissions, retention, join restrictions**, and sequential linkage risks. A nameless identifier can still stitch together multi-year behavior, so pseudonymization never exempts data from controls.

## 11. Preventing Unmanaged PII Copies: CDC, Caches, Logs, Backups

Separating schemas while streaming **CDC of `pii.customer_contacts`** to a company-wide topic negates privilege separation. Similarly, if Order Service fetches a contact and dumps the full JSON response into debug logs, data resurfaces elsewhere.

### 11.1. Map of Where Data Can Appear

| Location | Risk | Controls to consider |
| --- | --- | --- |
| **Source database** | Overbroad read roles, wrong tenant, DBA access | Least-privilege roles, audit, backup/key controls |
| **CDC/outbox/event bus** | Full-row payloads with PII; unvetted new subscribers | Event allowlists, topic ACLs, retention, transport encryption |
| **Caches** | Keys/values holding contacts, excessive TTL, cross-tenant sharing | Scoped keys, TTL, invalidation, read authorization |
| **Application logs/APM/traces** | Logged request/response bodies, emails, addresses, auth tokens | Redaction and log tests; avoid logging raw payloads |
| **Search indexes** | Directly indexing names/phones/locations with broad search rights | Clear purpose, field-level access, source-driven deletion |
| **Analytical warehouses** | Stable subject IDs, rare groups, multi-dataset JOINs | Use-case pseudonyms, aggregates, conditional access |
| **Exports/reports** | CSVs downloaded and shared outside policy | Export permissions, tracking/audit, expiration |
| **Test/staging** | Copied production data with weaker controls | Synthetic/de-identified test data, narrow access |
| **Backups/archives** | Old snapshots retaining PII after primary deletion | Retention policies, keys, expiration and restore procedures |
| **DLQ/retry queues** | Failed payloads retained longer than primary events | Redaction, ACLs, TTL, purge mechanisms |

**Data separation means designing data paths, not just table diagrams.** When a field traverses six systems, all six must be inventoried under applicable policies.

### 11.2. Never Publish Full Rows as Integration Contracts

CDC is useful for technical synchronization, yet **raw rows of an identity table** are not a general integration contract. When consumers need to react to contact state changes, emit a PII-free event and let authorized callers query Contact Service for minimal fields at the right moment.

Example:

~~~text
CustomerContactChanged
  eventId
  subjectRef
  revision
  changedFieldCategories: ["PHONE"]
  occurredAt

Do NOT include full name, address, email, or old/new phone by default.
~~~

Even this event carries a persistent `subjectRef` and partial change metadata, so restrict subscribers and retention. If a consumer does not need to know which subject updated contact info, it should not receive events at this granularity.

## 12. Reconciliation: Physical Separation Must Not Break Correctness

When data spans tables or stores, reconcile **reference identifiers**, **delivery address completeness when required**, **late-arriving events**, and **stray PII copies**.

### 12.1. Checking Reference and Contact Coverage

With the same-database DDL, FKs protect **commerce.orders.subject_ref** pointing to **commerce.customer_subjects** whenever `subject_ref` is non-NULL. To find orders with a subject lacking a current contact, an authorized role can run a diagnostic query:

~~~sql
SELECT
    o.tenant_id,
    o.order_ref,
    o.subject_ref
FROM commerce.orders AS o
LEFT JOIN pii.customer_contacts AS c
    ON c.tenant_id = o.tenant_id
   AND c.subject_ref = o.subject_ref
WHERE o.subject_ref IS NOT NULL
  AND c.subject_ref IS NULL;
~~~

**Do not assume every returned row is an error.** A subject may be closed, verified in another system, have had its contact deleted on request, or belong to an account that does not collect contact info. Maintain a **coverage contract** defining which orders/states require a contact and what threshold is expected.

This query is a **privileged reconciliation job**, not for dashboards or general services. Consider outputting only **counts and error codes** instead of `order_ref`/`subject_ref` lists for unprivileged viewers.

### 12.2. Checking Required Delivery Snapshots

Suppose **every physical order in `SHIPPED` state** must have exactly one recipient snapshot in a single-parcel model:

~~~sql
SELECT
    o.tenant_id,
    o.order_ref
FROM commerce.orders AS o
LEFT JOIN pii.order_delivery_snapshots AS d
    ON d.tenant_id = o.tenant_id
   AND d.order_ref = o.order_ref
WHERE o.order_state = 'SHIPPED'
  AND d.order_ref IS NULL;
~~~

This **invariant depends on the assumed use case**—it does not apply to digital orders or completed orders whose addresses were validly purged. When enforcing retention, distinguish **in-transit orders needing data** from **historical orders no longer authorized to keep addresses**.

With multiple shipments, snapshot grain and keys must change; the `SELECT` above applies only to the one-snapshot-per-order model.

### 12.3. Reconciling Permissions and Data Exports

Beyond table consistency, verify:

- Role **commerce_reader** cannot `SELECT` any **pii** table via any grant path.
- Order list endpoints do not return **subject_ref** if excluded from the contract.
- Logs and API errors never contain **legal_name**, **email**, **phone**, or **address_line1**.
- Analytics exports do not accidentally pick up PII when source schemas add new columns.
- Every re-identification call logs **reason, actor identity, subject, timestamp, and outcome**.
- Restricted/deleted data never resurrects via rebuild jobs, event replays, or backup restores.
- Cross-store reconciliation uses matching **watermarks/versions**, rather than flagging valid replication lag as permanent drift.

These checks can be automated via contract tests, integration tests, audits, and operational metrics. **Matching row counts do not prove data is well protected**, and **omitting names does not prove business correctness**.

## 13. Data Lifecycle: Deletion, Restriction, Retention, and Recovery

When an individual requests account closure or processing restriction, the organization must determine **specific rights and obligations** before acting. You cannot assume every request ends in a blanket "DELETE everything," because transaction records, disputes, audits, or retention duties may still apply.

Illustrative lifecycle model:

~~~text
ACTIVE
   |
   | update/restriction request or purpose expired
   v
RESTRICTED
   |
   | verify scope of data to retain vs. eligible for deletion
   v
CONTACT_REMOVED_OR_REDACTED
   |
   | process unlinking, copies, caches, exports, events
   v
RECONCILED / CLOSED
~~~

This is **not a universal legal flowchart**. Every transition needs an established basis, approver, and contextual audit trail.

### 13.1. Can You Delete Contacts While Retaining Business Records?

**Yes, in certain scenarios when policy/regulations permit**, provided you clarify:

- Are order records still required for accounting, disputes, or other obligations?
- Is keeping **subject_ref** still required to prove accountability, or can it be unlinked?
- Is the locked shipping address still needed for carrier claims, or must it be purged after a set period?
- Are there indirect identifiers in free-text notes, rare SKUs, locations, or timestamps?
- Are copies sitting in search indexes, analytics, caches, logs, or backups?
- Do you need to prevent **recreating the contact from old data** during migrations/replays?

In the example DDL, **orders.subject_ref** is nullable. Once approved, a workflow can **unlink eligible orders** and then delete the contact within scope:

~~~sql
BEGIN;

-- Illustrates operations ONLY AFTER verifying permissions,
-- retention obligations, and eligible orders for the subject.
UPDATE commerce.orders
SET subject_ref = NULL
WHERE tenant_id = $1
  AND subject_ref = $2::UUID;

DELETE FROM pii.customer_contacts
WHERE tenant_id = $1
  AND subject_ref = $2::UUID;

-- Do NOT automatically delete customer_subjects or record history.
-- The application must verify affected row counts and related constraints.
COMMIT;
~~~

**Never run this snippet as a generic data-deletion solution.** It can break legitimate transaction lookup/reconciliation, and leaves **pii.order_delivery_snapshots**, logs, backups, and external stores untouched. Real workflows require per-data-class decisions, clear accountability, and awareness of business consequences. For downstream systems, issue acknowledged delete/redaction commands and guard against late-arriving events.

### 13.2. Never Recreate Identity After Deletion

A common pitfall: the primary system deleted a contact, yet a backfill job reads old events or backups and **re-inserts `pii.customer_contacts`**. Enforce **tombstone/restriction markers**, replay controls, and copy freshness rules so pipelines know which subjects or records must never be regenerated.

These markers are themselves subject-related metadata and must be governed with appropriate permissions, purpose, and retention. Never broadcast the entire list of deletion-requesting users to every consumer.

### 13.3. Backups and Real-World Retention

Deleting a row in an active database does not immediately edit every snapshot or backup. Design must account for **backup cycles, restore permissions, expiration timelines**, data resurrection from old backups, and re-applying deletion/restriction orders upon recovery.

One sound approach is maintaining a **protected deletion/restriction ledger**, re-enforcing controls after a restore before serving traffic, or applying approved key-management/retention solutions. Never claim encryption or deleting keys equals "complete erasure" if plaintext copies or decryption paths still exist.

## 14. Threat Model: Which Risks Does Separation Reduce, and What Remains?

| Scenario | How separation can help | What still requires protection |
| --- | --- | --- |
| Read-only dashboard account compromised | No email/phone/address in read tables | Avoid stable subject keys and overly small groups |
| Order Service read outside authorization | Direct identifying data sits in another zone | Roles, tenant authorization, ID access, logs |
| DB admin account compromised | Same-DB schema separation is **insufficient** | Separation of duties/keys, MFA, audit, least privilege |
| OLTP backup leaked | Physical/key separation can shrink PII in one backup | Audit backup vaults and real restore privileges |
| Event broker has unintended subscriber | Minimal events omit contacts | ACLs, retention, token/subjectRef linkability |
| Search index exposed publicly | Projection can omit PII | Search permissions, stale data, delete propagation |
| Employee abuses contact lookup | Centralized endpoint enables auditing | Purpose-based authorization, rate limits, anomaly detection |
| Analytics joined with external datasets | Reduced via aggregates and scoped tokens | Quasi-identifiers, rare cohorts, query controls |
| Old data restore/replay job | Metadata can block regeneration | Restore runbooks, tombstones, post-recovery reconciliation |

Key takeaway: **separation reduces blast radius**, it does not automatically prove full-system security. Threats must be evaluated by **who holds access, where data lives, what can be joined, and recovery paths**.

## 15. Migrating from a PII-Laden Table to a Separated Model

Suppose **legacy_orders** holds addresses, emails, names, and order data together. A risk-reducing migration plan:

1. **Inventory fields and consumers**: APIs, batch jobs, dashboards, exports, CDC, search, logs. Classify PII, technical IDs, snapshots, and copies.
2. **Define authoritative sources and grain**: current customer, confirmed order, delivery snapshot; check whether buyer and recipient can differ.
3. **Lock data policies**: purpose-based access, retention, classification, deletion/redaction rules, and auditing.
4. **Design linkage keys**: persistent `subject_ref` or scoped tokens, unique per tenant; protect re-identification paths.
5. **Provision new zones**: tables/schemas, roles, tenant tests, grants, and encryption if required.
6. **Backfill by authoritative milestone**: populate subjects/contacts from trusted sources; migrate historical addresses into delivery snapshots **without overwriting history with current addresses**.
7. **Catch up live changes during migration**: use checkpoints/outbox/controlled CDC; prevent legacy jobs from overwriting backwards or resurrecting restricted records.
8. **Shadow read and reconcile**: order counts, lines, totals, contact coverage, snapshots, permissions, and API outputs within permitted scope.
9. **Cut over consumers in cohorts**: dashboards read only business/aggregate tables; logistics calls dedicated contract; support uses contact lookup service.
10. **Revoke legacy permissions**: remove broad `SELECT` paths on legacy tables; drop old columns/tables only after zero dependencies remain and retention allows.
11. **Test incidents and recovery**: late events, Contact Service offline, deletion requests mid-backfill, backup restores, tenant mismatches.
12. **Monitor long-term**: re-identification audits, PII leak tests, lag/coverage, access rights, count of systems still holding contacts.

### 15.1. Do Not Use Dual-Write to Create Two Sources of Truth

If both `legacy_orders.email` and `pii.customer_contacts.email` are written temporarily, designate **one authoritative writer** while the other acts purely as a transitional projection. If both are edited independently without conflict resolution, one system may update to a new email while the other serves the old one.

After cutover, never keep bidirectional sync indefinitely "for compatibility." Set a retirement schedule for legacy writers/readers backed by evidence that all consumers migrated.

### 15.2. Weigh Feasibility by Workload and Consequences

A small system may not need a separate database. A massive system with independent teams may need a dedicated Contact Service and key vault. Base the decision on:

- **Number of consumers** genuinely needing re-identification.
- **Ratio of requests** needing contacts vs. business-only requests.
- **Latency/availability** impact of API-based contact lookups.
- **Current privilege footprint** and potential to reduce PII-exposed accounts.
- **Exposure risk** across databases, backups, logs, and partner systems.
- **Cost of sync, reconciliation, recovery, and deletion** across distributed stores.
- **Audit requirements, record history, and retention policies**.

Separation is only valuable when protected properties and operations are **expressed as verifiable criteria**, not because an architecture diagram looks modern.

## 16. Comparing Relational, Document, Graph, and Analytics Models

### 16.1. Relational Databases

Relational models excel at expressing **foreign keys, UNIQUE constraints, schema/table/column privileges, transactions, and reconciliation queries**. Splitting contacts into a separate table in the same DB is often the lowest-cost first step, though elevated privileges and JOIN paths still need control.

When splitting across multiple databases, cross-boundary FKs and transactions disappear. Define field-level authority and add appropriate consistency mechanisms.

### 16.2. Document Databases

A Customer document bundling **profile, account, addresses, and transaction history** reads conveniently, yet returning the whole document easily leaks PII. Keep **customerIdentity** separate from **order documents** containing only `subjectRef` and needed snapshots; enforce collection permissions and projection DTOs.

If you embed current contacts into many order documents, email updates cause huge fan-out even though historical orders do not need the new email. Distinguish **current contact** from **recipient at confirmation** before embedding.

### 16.3. Graph Databases

Graphs model relationships like **Customer–PLACED–Order–SHIPPED_TO–Address**. Even without returning names, traversing unique edges can infer individuals, locations, and behaviors.

Control **node/edge types, traversal purposes, query depth, subject-scoped permissions, and returned payload size**. Removing a `name` property from nodes is never enough to anonymize an entire graph.

### 16.4. Analytical/Columnar Models

A sales fact at **order-line** grain holds product/date/channel dimensions and monetary measures. If reports do not need customers, drop the **customer dimension key** or use appropriate groupings. If repeat behavior is needed, consider a purpose-specific token with restricted access.

Aggregation reduces identifiability, yet small cohorts or multi-dimensional combinations raise risk again. Control **grain, filterability, cardinality, and retention**, never assuming a warehouse is safe because it "only contains numbers."

## 17. Review Checklist Before Separating or Publishing Data

| Question | Expected evidence |
| --- | --- |
| Is the field needed for the business? | Specific use case and owner |
| Is it a direct or indirect identifier? | Classification in data-linkage context |
| Which point in time does it represent? | Current, at-confirmation, event time, effective time |
| Are buyer and recipient identical? | Real-world business grain/relationship |
| Is cross-domain linkage required? | Purpose and lifespan of `subjectRef`/token |
| Who is authorized to re-identify? | Roles, object authorization, purpose/audit |
| Logical or physical separation? | Threat model, permissions, backups, transaction cost |
| How are IDs/keys generated and rotated? | Stable, unique, non-PII-derivable identifiers |
| Where do copies live? | DB, CDC, logs, caches, indexes, DLQs, exports, backups |
| Can snapshots mutate with profile updates? | Versioning/amendment rules for transactions |
| Can data be deleted/redacted? | Distinct policies for contacts, orders, deliveries |
| Can rebuilds resurrect deleted data? | Tombstone/restriction and replay rules |
| Is it reconcilable? | FKs, coverage, counts, permissions, freshness |
| Do APIs leak `subjectRef` needlessly? | DTO allowlists and contract tests |
| Does the design disrupt checkout? | SLOs, retries, idempotency, failure modes |
| Is ownership assigned? | Owners for source, identity vault, business, analytics |

## 18. Case Study Exercises

### Exercise 1 — Sales Dashboard Still Carries Emails

A **fact_sales** table has one row per order line, and the pipeline copies **customer_email** onto every row "for convenient querying." The dashboard only displays total sales by date and currency.

**Question:** What is the risk? Which fields should be exposed, and is `subject_ref` needed?

### Exercise 2 — Is a UUID Anonymous Data?

A system replaces email with a **subject_ref UUID** across purchase history. A `subject_ref → email` mapping table remains in Identity Service; the team claims the dataset can be shared freely because emails are gone.

**Question:** Is the claim valid? Which re-identification paths still exist?

### Exercise 3 — Buyer Differs from Recipient

Customer A buys a gift for B and enters B's address. A label-printing job reads A's **pii.customer_contacts** instead of the order snapshot.

**Question:** Is this a privacy bug or a business modeling bug, and how do you fix it?

### Exercise 4 — Unkeyed Email Hashing

Analytics exports **SHA256(lowercase(email))** claiming nobody can tell who is in the dataset. Someone with a list of common emails can recompute hashes.

**Question:** Why is it easy to probe? Does HMAC solve every issue?

### Exercise 5 — Tenant Permissions Checked Only in the UI

Order Service fetches orders by **order_ref** without filtering by tenant/owner; a client swapping IDs in requests can read other users' orders. The team says "UUIDs are unguessable, so it's secure enough."

**Question:** What protection is missing? Write the conditions required in queries or the authorization layer.

### Exercise 6 — Database Split Causes Account Creation Failures

Order DB and Identity DB are separated. Creating a subject in Order succeeds, but writing Contact fails; the client retries multiple times. Some subjects lack contacts, and some duplicates appear.

**Question:** What consistency/idempotency decisions and recovery workflows are needed?

### Exercise 7 — Deleting Contacts While Retaining Records

A user requests account closure. The system must consider keeping orders for record-keeping over the applicable retention period; the current email may no longer be needed. The team wants to immediately **DELETE CASCADE** the customer, orders, and order lines.

**Question:** Why is this dangerous? How should items be classified and handled step by step?

### Exercise 8 — Data Resurrection After Recovery

Contact Service restricted/deleted a record per policy. A week later, the team restores an old backup and runs CDC replay, causing the record to reappear in the search index.

**Question:** What is missing in the lifecycle design? How do you verify no revoked data remains in copies?

### Exercise 9 — Logistics Service Reads All Contacts

A shipping service holds `SELECT` on **pii.customer_contacts** across all tenants. It only needs recipient phone numbers for parcels being delivered this week.

**Question:** Along which dimensions should access be restricted? Is an API returning raw phone numbers the only option?

### Exercise 10 — Rare Reports Can Re-Identify

A report drops names/emails yet allows filtering by **a tiny ward, exact minute, rare product category, and total amount**. Someone knowing when a transaction occurred can deduce the customer.

**Question:** Why is aggregation insufficient? List at least three mitigations.

### Suggested Answers

1. Email is duplicated across every fact row, expanding exposure and deletion cost. A daily/currency dashboard only needs **business_date, currency, order_count, amount** with clear definitions; **subject_ref** is normally **not needed**.
2. **Invalid.** UUIDs are pseudonymization; mappings still allow re-identification, and purchase behavior, timestamps, locations, and external datasets can also link back. Assess permissions, purpose, retention, and linkage risk.
3. Both: wrong business data source (**buyer ≠ recipient**), and it can leak addresses or ship to the wrong place. Use the **delivery snapshot for the specific order/shipment**, accessed under Logistics permissions.
4. Email spaces are guessable via list hashing and comparison; identical hashes enable cross-dataset joining. Secret-keyed HMAC resists unkeyed probing, yet still produces linkable IDs requiring key management, oracle access control, and rotation; **it is not anonymization**.
5. Missing **object-level**, tenant, and owner authorization. Queries must restrict by authenticated tenant and authorized **subject_ref** (or a verified access grant table); never trust client-supplied IDs as proof of authorization.
6. Define the **authoritative subject source**, registration idempotency keys, per-tenant uniqueness, and contact-creation flows with retry/compensation. Track incomplete states and reconcile; never create a new subject per retry. Never assume two databases share a transaction.
7. `DELETE CASCADE` can destroy required records and audit trails; classify **current contact, person–order links, delivery snapshots, orders, and lines**, evaluate obligations/retention, restrict/delete each category under approval, handle copies, and audit.
8. Missing **restriction/tombstone persistence across restore/replay**, source validation prior to applying CDC, and target reconciliation. Re-apply restriction/deletion orders post-restore before serving consumers, and audit indexes/caches/backups.
9. Restrict by **tenant, assigned shipment, purpose, time window**, role, and returned fields. Contact Service can **send messages directly** instead of returning phone numbers; if phone numbers are genuinely needed for delivery, return them only within authorized scope and log audits.
10. Combinations of quasi-identifiers can identify individuals even without names. Apply **time/region coarsening**, **suppress overly small groups**, **restrict filter dimensions and read privileges**, or apply appropriate statistical disclosure controls while evaluating real re-identification risk.

## 19. Key Takeaways

**Separating identifying information from business data when appropriate** means drawing clear boundaries between **who the real person is**, **what transactions they performed**, and **which consumers legitimately need to link the two**. Those boundaries must live across **schemas, privileges, APIs, events, logs, backups, retention, and recovery workflows**, not merely in table naming.

**Pseudonymization reduces direct identifiability but does not equal anonymization.** Persistent codes, purchase histories, locations, and timestamps can still identify indirectly. Effective protection requires minimizing who and what can re-identify, while assessing remaining combinable sources.

**Never sacrifice transactional truth for an illusion of "zero PII."** Locked shipping addresses, amounts, and transaction records have different lifecycles and purposes from current contact profiles. Govern them inside appropriate permission zones with explicit amendment and retention policies.

Before separating a field, ask: **"Who needs to know identity for which action, for how long, as of what point in time is this data true, what can it link with, and if permissions are revoked or systems are restored, does the separation still protect users?"** Answering with models, constraints, tests, and operational runbooks keeps data both useful and safely governed.
