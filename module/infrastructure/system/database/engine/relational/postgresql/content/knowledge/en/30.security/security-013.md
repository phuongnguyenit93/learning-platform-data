# Encryption, Data Masking, and Per-Layer Protection Limits in PostgreSQL

## 1. Scenario: Encrypted Data Still Leaks

A system stores customer details in PostgreSQL:

```text
customer_id | full_name | email                | phone
------------+-----------+----------------------+--------------
101         | An        | an@example.invalid   | 0900000001
102         | Binh      | binh@example.invalid | 0900000002
```

The operations team turns on **disk encryption**, configures **TLS** for application connections, and creates a view displaying masked emails as `a***@example.invalid` for support staff. They conclude: "Personal data is now protected."

Yet any of the following gaps can still expose data:

- The application account holds direct `SELECT email FROM customers` privileges, bypassing the masking view.
- A DBA or operating system administrator on the PostgreSQL host can read plaintext once the OS decrypts the disk layer.
- The application logs emails, phone numbers, or decryption keys.
- Backups, file exports, caches, analytics stores, or search replicas do not enforce the same controls.
- A `SECURITY DEFINER` API returns unmasked rows to an inappropriate role.
- Encryption keys live inside the same database, same backups, and same privilege boundary as the ciphertext.
- The "masking" layer only transforms display strings while callers can still filter, sort, or infer raw values via other queries.

That is why data protection must be designed in **multiple layers, each addressing a distinct threat class**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **encryption**, **hashing**, **masking**, **tokenization**, **anonymization**, and **access control**.
2. Threat-model PostgreSQL data across transit, storage media, database internals, applications, replicas/copies, and human operators.
3. Understand TLS accurately, including server identity verification and the boundaries of encryption in transit.
4. Explain the protection scope of disk/volume encryption, backup encryption, and other at-rest controls.
5. Use `pgcrypto` conceptually to encrypt/decrypt fields while explaining why DB-side encryption does not hide plaintext from the database server itself.
6. Understand application-layer encryption, envelope encryption, KMS/HSM, key rotation, and key-usage separation.
7. Contrast probabilistic encryption with deterministic encryption; analyze probing/frequency-leakage risks and build controlled "blind indexes".
8. Mask sensitive fields using SQL views, column-level grants, and display functions.
9. Distinguish masking from RLS, explaining how each solves a separate access dimension.
10. Identify leaks across logs, `RETURNING`, `COPY`, backups, WAL, replication, planner statistics, search indexes, and BI exports.
11. Build a layered lab and run tests verifying exactly which role sees what data.
12. Choose the right defense layer for each threat without equating "encrypted" with "secure".

---

## 2. Classify Data Before Choosing Controls

Not every piece of data needs the same protection policy.

| Category | Examples | Exposure Impact | Defensive Direction |
|---|---|---|---|
| Public | Published product names | Low, mostly accuracy concerns | Integrity, availability, backups |
| Internal | Discount rates, delivery schedules | Business secret leakage | Roles, row/column grants, TLS, encryption |
| Personal data (PII) | Email, phone number, address | Privacy breach | Minimization, masking, encryption, access control |
| Highly sensitive data | National IDs, bank accounts | Fraud, legal/regulatory liability | Field encryption, key separation, audit, retention |
| User passwords | Login passwords | Account takeover | Dedicated **password hashing**, never plaintext |
| System credentials | API keys, refresh tokens | Unauthorized lateral access | Secret managers, scoped rights, rotation, log hygiene |
| Encryption keys | DEKs/KEKs, private keys | Complete loss of ciphertext secrecy | KMS/HSM, strictly separated from data |

### 2.1. Identify Usage Patterns First

The same email address may need to support:

- Sending notifications.
- User login.
- Exact-match lookups.
- Masked display for customer support.
- Domain-level customer analytics.
- Data subject exports under privacy regulations.

No single cryptographic scheme simultaneously enables every workflow with maximum secrecy. Decide **which fields are decrypted, by whom, and when**.

### 2.2. Data Minimization Often Beats Encrypting Everything

If business logic does not need a full national ID number, **do not store it**. If only the last four digits are required, consider storing strictly those four digits per governing policy and regulations.

Data you never collect cannot leak from your database.

## 3. Essential Terms to Distinguish

| Term | Meaning | Recoverable Original Value? | Primary Protection |
|---|---|---|---|
| **Encryption** | Uses a key to turn plaintext into ciphertext | Yes, with key and authorization | Confidentiality against parties lacking the key |
| **Hashing** | Transforms data into a one-way digest | Not decryptable; guessable/brute-forceable if low entropy | Comparisons, integrity, or verification components |
| **Password hashing** | Salted hashing with tuned work cost | Not decryptable | Protects stored passwords against offline cracking |
| **Masking** | Replaces or hides parts of data at display or export time | Original often still exists elsewhere | Limits visual exposure to specific viewers |
| **Tokenization** | Replaces sensitive values with mapped tokens via a token vault | Yes, if authorized to detokenize | Limits sprawl of original sensitive values |
| **Pseudonymization** | Replaces direct identifiers with linkable pseudonyms | Re-linkable with mapping | Reduces direct exposure; not full anonymization |
| **Anonymization** | Removes reasonable re-identification ability under a threat model | Designed to prevent re-identification | Privacy preservation; requires re-identification review |
| **Authorization** | Governs who may perform what actions | Not directly applicable | Prevents unauthorized access |

### 3.1. Masking Is Not Encryption

```text
Original:   an@example.invalid
Masked:     a***@example.invalid
Encrypted:  <unreadable bytea or ciphertext>
```

A masked string still reveals the first character and email domain, and guarantees nothing about whether plaintext remains in base tables, logs, or memory.

### 3.2. Hashing Is Not Encryption

```sql
SELECT encode(digest('an@example.invalid', 'sha256'), 'hex');
```

With `pgcrypto`, this returns a digest. There is no "decrypt SHA-256". However, emails have low entropy and can easily be matched against candidate email lists—so **plain SHA-256 hashing never makes emails safely anonymous**.

### 3.3. Access Control Is Not Encryption

A role holding `SELECT` needs no key to read plaintext columns. Meanwhile, ciphertext in the DB hides field contents from roles lacking keys, yet those roles can still inspect or manipulate metadata allowed by SQL privileges.

### 3.4. Confidentiality Differs From Integrity and Availability

- **Confidentiality:** unauthorized parties cannot read data.
- **Integrity:** unauthorized tampering is prevented or detected.
- **Availability:** data and services remain accessible when needed.

Encryption primarily addresses confidentiality; many cipher modes require explicit integrity authentication separately. Nor does encryption replace backups, constraints, or ransomware resilience.

## 4. Build a Threat Model Before Picking Encryption Layers

A solid threat model answers:

1. Which assets need protection?
2. Who are potential adversaries: end users, app roles, DBAs, infra admins, cloud providers, disk thieves, backup thieves?
3. Which layers could an attacker compromise: network, SQL session, VM, OS, disk snapshots, KMS, application tier, or logs?
4. Where do keys live, who can invoke them, and where does decryption occur?
5. Where do copies live: base tables, WAL, backups, replicas, caches, exports, queues, metrics?
6. Is the goal hiding plaintext completely or restricting UI visibility?
7. Do protected fields require search, filtering, joins, or analytics?
8. What are recovery and key rotation procedures after key compromise?

### 4.1. Condensed Threat-Model Matrix

| Threat / Adversary | TLS | Disk Encryption | DB-Side Field Encryption | App-Side Field Encryption | Masked View / RLS |
|---|---|---|---|---|---|
| Network eavesdropping between app and DB | Protects when properly verified | No | Partial for some payloads | Protects encrypted payloads | No |
| Physical theft of powered-off disk | No | Yes with proper setup/keys | Yes for encrypted fields | Yes | No |
| Access to plaintext PostgreSQL dump | No | Does not protect exported dumps | Hides ciphertext fields if keys separated | Hides ciphertext fields if keys separated | No |
| SQL role limited to masked view | Indirect | No | Depends on decrypt rights | App holds plaintext; DB holds ciphertext | Effective at SQL boundary |
| SQL injection in app role holding full SELECT | No | No | No if role can decrypt/read keys | Limits plaintext inside DB | No if role can read base table |
| DBA/superuser with host access | No | No | Can observe plaintext/keys during DB decryption | Lacks app keys, though metadata/backups still visible | Generally bypasses SQL masking/RLS |
| Compromised app authorized for KMS | No | No | No guarantee | Can decrypt via app KMS rights | No guarantee |
| Logs leaking plaintext | No | No | No | No if app logs plaintext | No if logged outside view |

**Read this matrix as typical coverage scope, not a security certification.** Real effectiveness depends on configuration, privileges, key custody, data flows, and adversary capabilities.

## 5. Defense in Depth: Multiple Layers, Each With Limits

A layered architecture might combine:

```text
User
   |
   | HTTPS + authentication + API authorization
   v
Application
   |
   | TLS to PostgreSQL
   |      +-- Optionally encrypt fields with app key beforehand
   v
PostgreSQL
   |
   | SQL roles / GRANT / RLS / views / auditing
   |      +-- Optionally pgcrypto where appropriate
   v
Data files + WAL + replicas
   |
   | Volume/disk encryption, infrastructure keys
   v
Backups / snapshots / exports
   |
   | Backup encryption and separate storage ACLs
   v
Recovery storage
```

Alongside:

```text
KMS / HSM / secret manager
   |
   +-- manages key policies
   +-- authorizes encrypt/decrypt by identity
   +-- rotation / disablement / audit trails
```

Never translate "we have 5 layers" into "no leak paths exist". If one application account holds full row-read privileges and permission to decrypt every field, a SQL injection exploiting that account bypasses multiple layers simultaneously.

## 6. Encryption in Transit: TLS

When applications talk to PostgreSQL over a network, TLS helps:

- Protect credentials, SQL statements, bound values, and results from eavesdropping.
- Protect stream integrity per the TLS protocol.
- Authenticate the database server when clients properly validate certificates and hostnames.

### 6.1. A Stronger Connection String

Example with libpq/psql:

```text
host=db.example.invalid
port=5432
dbname=appdb
user=app_reader
sslmode=verify-full
sslrootcert=/path/to/trusted-root-ca.crt
```

This is a **configuration pattern**, not a live server and containing no passwords.

### 6.2. sslmode Levels Are Not Equivalent

| libpq Mode | General Security Semantics |
|---|---|
| `disable` | No TLS used |
| `prefer` | Tries TLS but may fall back silently |
| `require` | Demands TLS channel, though not always full hostname verification |
| `verify-ca` | Verifies certificate chain against trusted CA |
| `verify-full` | Verifies both certificate chain and hostname against connection rules |

**Prefer `verify-full`** when trusted certificate infrastructure is available. Never assume `require` provides complete server identity validation; exact behavior depends on client trust stores and parameters.

### 6.3. PostgreSQL Server Configuration

Enable TLS on the server with appropriate certificate and key files:

```conf
# Sample postgresql.conf snippet (not complete TLS setup):
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
```

In `pg_hba.conf`, enforce `hostssl` rules to allow TCP connections strictly over TLS for specified roles and CIDR blocks:

```conf
# Illustrative pattern; adjust IP ranges and auth methods per environment:
hostssl appdb app_reader 10.20.0.0/16 scram-sha-256
```

Always review rule ordering, network topology, authentication methods, and private key file permissions carefully.

### 6.4. Inspecting the Active Connection

Query current backend TLS status:

```sql
SELECT
    ssl,
    version,
    cipher,
    bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

If `ssl=true`, this backend connection uses TLS. However, that **does not prove the client verified the server's hostname**; verify client-side `sslmode` independently.

### 6.5. Where Does TLS Protection Stop?

TLS does not protect:

- Data once decrypted and returned to the application.
- Credentials written into application logs.
- Data residing in server/app RAM outside the TLS channel.
- Unencrypted disks, backups, or file exports.
- Abusive queries sent by an authenticated, compromised role.

Never cite TLS as an excuse to skip encryption or access control in remaining layers.

## 7. Encryption at Rest: Disks, Volumes, and Storage

At-rest encryption typically operates across one or more layers:

- Full-disk encryption.
- Volume/block-device encryption.
- Encrypted cloud disks and snapshots.
- Encrypted backup object storage.
- Product-specific database encryption mechanisms depending on vendor/distribution.

### 7.1. What Threat Does It Mitigate Well?

Suppose an attacker steals **physical disks removed from a server without the encryption key**. Properly configured disk encryption stops them from reading PostgreSQL files directly.

### 7.2. What Threats Does It Not Mitigate?

While the system is running and the filesystem is unlocked:

- PostgreSQL reads data pages normally.
- Authorized SQL roles can read plaintext from any column not encrypted at a higher layer.
- Anyone controlling the host OS or database engine can inspect unlocked storage within their privileges.

It is **storage encryption**, not per-query SQL authorization.

### 7.3. Should You Claim PostgreSQL Always Has Built-In TDE?

No. Database/storage encryption capabilities vary by **PostgreSQL version, distribution, managed cloud service, extensions, and infrastructure tooling**. Always verify the exact deployment architecture, key custody, WAL/temp-file coverage, backups, and replication.

### 7.4. Which Files Need Coverage?

PostgreSQL maintains multiple physical artifacts:

```text
Base table/index files
WAL segments
Temporary files / spill files
Physical backups / snapshots
Archived WAL
Replication copies
Filesystem copies and crash dumps
```

Do not encrypt only `base/` while forgetting WAL or backups. Plaintext values inserted once can persist across multiple files per storage and operational lifecycles.

## 8. Backup Encryption Differs From Disk Encryption

Suppose production volumes are encrypted, yet a nightly job executes:

```text
pg_dump -> backup.sql -> upload to bucket
```

`backup.sql` contains **plaintext** emails and phone numbers. Production disk encryption never automatically encrypts off-host logical dump files.

### 8.1. Dedicated Backup Controls

- Encrypt backup archives and storage objects.
- Separate backup decryption keys from routine DB readers.
- Tighten IAM and storage ACLs.
- Enforce retention and lifecycle policies.
- Control where backups can be replicated or downloaded.
- Audit backup access and downloads.
- Drill restore verification periodically.
- Enforce purge workflows for expired copies.

### 8.2. Backup Encryption Still Has Boundaries

Anyone authorized to **access both the decryption key and the backup file** can recover the data. Separate key custody, storage download rights, and restore execution according to operational duties.

### 8.3. Do Not Overlook Logical Exports

Beyond `pg_dump`, watch out for:

- `COPY TO`.
- CSV exports.
- BI dashboards.
- Emailed reports.
- ETL pipelines.
- Search indexes.
- Data warehouses.
- Developer database clones.

Every copy creates a **new trust boundary**.

## 9. Field/Column-Level Encryption

Suppose only `national_identifier` needs stricter secrecy than other attributes.

A schema might store:

```text
customer_id       bigint
display_name      text
identifier_cipher bytea
key_version       text
```

Benefits:

- Anyone stealing data files or holding only `SELECT` on ciphertext cannot read the identifier without keys.
- Sensitive columns receive stronger protection than public ones.
- Decryption key permissions can be scoped to fewer services.

Limitations:

- You cannot run `ILIKE` or B-tree equality directly over properly randomized ciphertext.
- Key lifecycle and rotation add complexity.
- Plaintext still emerges upon decryption and can enter logs or app memory.
- Metadata such as `customer_id`, ciphertext length, and access patterns can still leak information.
- Decrypted values reside in RAM and require careful lifetime handling.

### 9.1. Field Encryption Does Not Replace Column Privileges

A role lacking the decryption key can still read raw ciphertext if granted `SELECT`. Whether that metadata exposure is acceptable depends on your threat model—configure table and column grants appropriately.

### 9.2. Field Encryption Does Not Prevent Deleting or Overwriting Ciphertext

Use authenticated encryption for integrity alongside DB constraints. Any role with `UPDATE` can still overwrite or wipe ciphertext; authentication detects tampering, not loss of availability.

## 10. pgcrypto: Encryption Inside PostgreSQL

PostgreSQL offers the `pgcrypto` extension featuring:

- `pgp_sym_encrypt` / `pgp_sym_decrypt`: OpenPGP symmetric passphrase encryption.
- `pgp_pub_encrypt` / `pgp_pub_decrypt`: asymmetric key-pair encryption.
- `digest` / `hmac`: cryptographic digests and keyed MACs.
- `crypt` / `gen_salt`: password hashing algorithms supported by the extension.
- Low-level ciphers: require deep knowledge of modes, IVs/nonces, and authentication—never roll custom protocols casually.

### 10.1. Enabling the Extension

In a learning database where permitted and supported:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

Installation privileges and supported algorithms vary across PostgreSQL versions, OpenSSL builds, and security policies.

### 10.2. Where Does pgcrypto Execute?

When sending:

```sql
SELECT pgp_sym_encrypt(p_plaintext, p_passphrase);
```

both plaintext and passphrase are **sent to PostgreSQL** and processed **inside the database server**.

Thus `pgcrypto` fits many DB-side field-encryption needs, yet **cannot satisfy a requirement that "the database server must never see plaintext"**.

### 10.3. Never Hard-Code Keys Inside SQL Strings

Avoid production code like:

```sql
-- UNSAFE example for production:
SELECT pgp_sym_encrypt(
    'identifier-sensitive',
    'HARDCODED-SECRET-KEY'
);
```

SQL text lands in client command histories, server logs, traces, audit trails, and repositories. Later lab snippets use **explicit dummy values** strictly to illustrate mechanics and highlight this pitfall.

## 11. Lab: Illustrative Schema for Masking and Encryption

**All sample data below is completely synthetic and represents no real individuals.** Run only in a practice database.

```sql
CREATE SCHEMA IF NOT EXISTS sec390;

CREATE TABLE sec390.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    full_name text NOT NULL,
    email text NOT NULL,
    phone text,
    national_identifier text,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO sec390.customers(
    tenant_id,
    full_name,
    email,
    phone,
    national_identifier
)
VALUES
    (7, 'An', 'an@example.invalid', '000-000-0001', 'FAKE-ID-001'),
    (7, 'Binh', 'binh@example.invalid', '000-000-0002', 'FAKE-ID-002'),
    (8, 'Chi', 'chi@example.invalid', '000-000-0003', 'FAKE-ID-003');
```

Because this demo table stores plaintext, anyone with full table `SELECT` sees every sensitive column. We use it to study **masking and privileges**, not as a blueprint for production PII storage.

### 11.1. Separation of Field Responsibilities

- `customer_id`: surrogate technical key.
- `tenant_id`: organizational data boundary.
- `full_name`: conditionally displayed.
- `email`/`phone`: contact attributes.
- `national_identifier`: highly sensitive field requiring strict access limits.
- `created_at`: metadata potentially subject to retention policies.

### 11.2. Never Use Real PII in Encryption Labs

Dev and lab environments often share access or capture verbose logs. Always generate synthetic test fixtures rather than copying production PII "to test realistically".

## 12. Controlled pgp_sym_encrypt / pgp_sym_decrypt Example

Create a dedicated ciphertext table:

```sql
CREATE TABLE sec390.encrypted_notes (
    note_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES sec390.customers(customer_id),
    encrypted_note bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Pattern for drivers using bound parameters:

```sql
INSERT INTO sec390.encrypted_notes(
    customer_id,
    encrypted_note
)
VALUES (
    $1::bigint,
    pgp_sym_encrypt(
        $2::text,
        $3::text,
        'cipher-algo=aes256'
    )
)
RETURNING note_id;
```

Here:

- `$1` = `customer_id`.
- `$2` = synthetic note content.
- `$3` = passphrase fetched from a secret manager by an authorized application.
- `encrypted_note` stores ciphertext as `bytea`.

**Note:** `$1`/`$2`/`$3` illustrate application/driver-bound parameters, not statements you paste directly into `psql` without preparing parameters.

### 12.1. Inspecting Ciphertext Metadata

```sql
SELECT
    note_id,
    customer_id,
    octet_length(encrypted_note) AS encrypted_bytes,
    created_at
FROM sec390.encrypted_notes
ORDER BY note_id;
```

Even though ciphertext is not plaintext, avoid exposing raw ciphertext unnecessarily in every API.

### 12.2. Authorized Decryption With a Supplied Passphrase

```sql
SELECT
    pgp_sym_decrypt(
        encrypted_note,
        $1::text
    ) AS note_plaintext
FROM sec390.encrypted_notes
WHERE note_id = $2::bigint;
```

Execute strictly within authenticated, authorized app flows. Once decrypted, the output is **plaintext** and can reach app memory, telemetry, or API responses.

### 12.3. Wrong Keys Must Fail Cleanly

Decrypting with an invalid passphrase or key raises an error. Never catch decryption errors and include raw ciphertext or sensitive details in exception messages.

### 12.4. Do Not Confuse Passphrases With Robust Key Management

Hard-coding a static passphrase in config files, source repos, or a table beside ciphertext defeats protection. Sound designs address key lifecycle, access governance, backups, and rotation.

## 13. Direct Lab-Only Round-Trip Example

To observe one encrypt/decrypt round-trip directly without an app, use **strictly synthetic text** and a **throwaway dummy passphrase**:

```sql
-- LAB ONLY: literal passphrases risk entering command history and logs!
WITH encrypted AS (
    SELECT pgp_sym_encrypt(
        'TRAINING-ONLY-NOT-PII',
        'LAB-KEY-DO-NOT-REUSE',
        'cipher-algo=aes256'
    ) AS ciphertext
)
SELECT
    octet_length(ciphertext) AS ciphertext_bytes,
    pgp_sym_decrypt(
        ciphertext,
        'LAB-KEY-DO-NOT-REUSE'
    ) AS restored_text
FROM encrypted;
```

Expected `restored_text`:

```text
TRAINING-ONLY-NOT-PII
```

### 13.1. What This Example Does Not Prove

- It does not prove keys are managed securely.
- It does not guarantee secrets never hit logs.
- It does not protect data from database superusers.
- It does not make ciphertext searchable via `LIKE`.
- It does not represent production encryption-at-rest.

It solely demonstrates **one encrypt/decrypt round-trip** given a matching passphrase.

## 14. Who Does DB-Side Encryption Protect Against?

Suppose `identifier_cipher` is encrypted via `pgcrypto`.

| Actor | Knows Passphrase? | Reads Ciphertext? | Reads Plaintext? |
|---|---|---|---|
| Role holding only SELECT on ciphertext | No | Yes if GRANTed | Cannot decrypt without key |
| Service authorized to call decrypt with key | Yes | Yes | Yes |
| SQL injection in a session holding the key | Possibly | Yes | Possibly |
| DBA controlling host and observing decrypt calls | Can observe plaintext/keys arriving at server | Yes | High risk |
| Attacker holding ciphertext-only backup without key | No | Yes | Impractical given sound algorithm/key |

### 14.1. Key Separation Is Critical

A database backup containing both:

```text
encrypted_identifier bytea
encryption_key text
```

allows anyone obtaining the backup to decrypt everything.

Keep keys outside the database, backups, and shared permission scopes whenever your threat model requires it.

### 14.2. DB Encryption Does Not Block Other SQL Operations

Even if PII columns are encrypted, a role with `DELETE` can destroy rows, and one with `UPDATE` can corrupt ciphertext. Encryption never substitutes for `GRANT`, RLS, constraints, WAL archiving, and backups.

## 15. Application-Layer Encryption: PostgreSQL Receives Only Ciphertext

To prevent **the database server from ever seeing plaintext**, encrypt inside the application layer.

Flow:

```text
Plaintext (in authorized service)
       |
       v
App uses vetted crypto library + key from KMS
       |
       v
Ciphertext + nonce + auth tag + key version
       |
       | TLS
       v
PostgreSQL: stores bytea/metadata; never receives field plaintext
       |
       v
Authorized service reads ciphertext
       |
       v
App requests decryption authorization via KMS/keystore
       |
       v
Plaintext exists strictly in services requiring it
```

### 15.1. Prefer Authenticated Encryption

Normally choose an **AEAD (Authenticated Encryption with Associated Data)** standard such as AES-GCM or ChaCha20-Poly1305 via a vetted crypto library aligned with platform standards.

AEAD provides confidentiality plus integrity/authenticity verification under matching threat models, provided:

- Nonces/IVs are generated strictly per algorithm rules.
- Nonces are never reused under the same key when uniqueness is required.
- Associated Data (AAD)—such as immutable `tenant_id` or record context—is designed carefully.
- Key rotation and versioning metadata are maintained reliably.
- Custom cryptographic protocols are never built via SQL string operations.

### 15.2. Illustrative Storage Schema

```sql
CREATE TABLE sec390.secure_identifiers (
    customer_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    ciphertext bytea NOT NULL,
    nonce bytea NOT NULL,
    authentication_tag bytea NOT NULL,
    algorithm text NOT NULL,
    key_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

These columns form an **illustrative storage contract**, not custom AES-GCM implementation code; applications must rely on vetted libraries and validate formats strictly.

### 15.3. Protection Scope

Application-layer encryption keeps plaintext out of PostgreSQL for encrypted fields. Still:

- Services authorized to decrypt still handle plaintext.
- Full compromise of an authorized service exposes its KMS permissions.
- Metadata and lookup indexes can still reveal patterns.
- Application logs or caches recording plaintext undermine this benefit.
- DBAs can delete or corrupt ciphertext, affecting availability; AEAD detects tampering without guaranteeing availability.

## 16. Envelope Encryption and KMS

At scale, you should never rely on a single eternal hard-coded passphrase.

Common architecture:

```text
KMS-managed KEK (Key Encryption Key)
           |
           +-- protects / wraps DEK
                    |
                    v
           DEK (Data Encryption Key)
                    |
                    +-- encrypts data fields
                    |
                    v
              Ciphertext
```

Stored metadata often includes:

```text
record_id
ciphertext
nonce/tag
wrapped_dek
kek_key_id
key_version
algorithm
```

### 16.1. Why Separate KEK and DEK?

- Restricts access to the root master key / KEK.
- Simplifies key rotation workflows.
- Lets distinct datasets use isolated DEKs.
- Shrinks blast radius per key when segmented well.
- Provides auditable KMS/HSM decrypt trails.

### 16.2. KMS Does Not Secure Over-Privileged Apps Automatically

If one service role can invoke `Decrypt` on every DEK across all tenants, compromising that app role still causes mass exposure.

Enforce:

- Least privilege.
- Environment/tenant key segmentation matching risk profiles.
- Strict key policies and IAM identity context.
- Auditing of `Decrypt` API calls.
- Quotas and rate limits.
- Key revocation and incident playbooks.

### 16.3. Where Does Plaintext Exist?

Any service decrypting data holds plaintext in RAM. Manage memory lifetimes, crash dumps, debuggers/tracers, and API responses carefully. "Not storing keys in the DB" does not mean "plaintext exists nowhere".

## 17. Key Rotation Differs From Password Rotation

Different keys follow distinct rotation lifecycles:

| Key Type | Protects | Rotation Considerations |
|---|---|---|
| TLS private key/cert | Network transit | Certs, CA trust stores, client rollout |
| Volume encryption key | Block storage | Cloud provider support, snapshots, recoverability |
| Field DEK | Individual records/datasets | Data re-encryption and key versioning |
| KMS KEK | Protects wrapped DEKs | Rewrapping DEKs or versioned master keys |
| Application secret/token | Connections/APIs | Staged rollouts and active sessions |

### 17.1. Rotation Requires Versioning

If you store only `ciphertext` with no key version, decrypting records across multiple rotations becomes unmanageable.

Metadata typically records:

```text
key_version = "v3"
algorithm = "AES-256-GCM"
ciphertext = ...
```

These values illustrate structural conventions, not a mandatory universal format.

### 17.2. Rotating a KEK Does Not Always Require Re-Encrypting All Data

With proper envelope encryption, you can **rewrap DEKs** under a new KEK without re-encrypting every database row, depending on policy and threat model.

If a DEK itself is compromised or an algorithm changes, you must **re-encrypt records** under a fresh DEK.

### 17.3. Rotation and Backups

Older backups may still rely on prior keys for restoration. Never destroy keys until you have:

- Inventoried every dataset and backup relying on the key.
- Completed required migrations and re-encryption.
- Reviewed retention and compliance deletion rules.
- Tested restoring valid backups.

Conversely, keeping every key forever expands exposure. Balance recoverability against retention rules deliberately.

## 18. Password Hashing: No Decryption, No Masking

Login passwords **must never be stored using reversible encryption** just so they could be read back.

Standard practice uses **dedicated password hashing** featuring:

- A unique random salt per password.
- Tunable computational/memory cost factors.
- Modern algorithms such as Argon2id via vetted authentication libraries.
- Transparent rehashing when policies or parameters tighten.
- Application-layer rate limiting, MFA, and breached-credential screening.

### 18.1. Why Isn't SHA-256(password) Good Enough?

```sql
SELECT digest('my-password', 'sha256');
```

SHA-256 is a fast general-purpose hash easily brute-forced for weak passwords. Never treat `digest()` as secure password storage.

### 18.2. pgcrypto crypt() and gen_salt()

Educational DB-side example:

```sql
-- Dummy fixture; never embed real passwords in SQL literals.
SELECT crypt(
    'TRAINING-PASSWORD',
    gen_salt('bf', 10)
) AS stored_hash;
```

Legacy verification query:

```sql
SELECT
    crypt('candidate-password', stored_hash)
    = stored_hash AS password_matches
FROM some_login_table
WHERE account_id = $1;
```

The second query is a **template**, as `some_login_table` is not created in the lab.

### 18.3. Limits of bcrypt / Blowfish

Many bcrypt implementations truncate passwords (commonly at 72 bytes) and carry specific normalization quirks. New systems should generally favor Argon2id inside the authentication service per modern policy.

### 18.4. Avoid Passing Plaintext Passwords in SQL Literals

Hashing inside the DB server sends plaintext passwords to PostgreSQL. If that violates your threat model or logging policy, hash and verify inside the authentication service and persist only the hash.

## 19. Hashing Emails or Identifiers: Dictionary Attack Risks

An email address is not a high-entropy 256-bit secret. Seeing:

```text
SHA256("an@example.invalid")
```

lets an attacker hash candidate emails and match digests offline.

### 19.1. "Hashed" Does Not Mean Anonymous

Unsalted hashes over predictable domains fall quickly to dictionary attacks. Furthermore, deterministic digests let observers link the same person across tables and datasets.

### 19.2. Use Keyed HMAC for Controlled Equality Tokens

When an exact-match lookup token is required, a controlled option is **HMAC** with a separately managed secret key:

```sql
-- Structural example: $1 = normalized synthetic email,
-- $2 = secret supplied strictly by authorized service.
SELECT hmac(
    'email:v1:' || lower(trim($1::text)),
    $2::text,
    'sha256'
) AS lookup_token;
```

Never store the HMAC secret alongside the tokens if offline guessing resistance is required.

### 19.3. HMAC Is Not Encryption Either

HMAC supports exact equality tokens; you cannot recover the original email from an HMAC output. If you still need to email customers, keep a separate authorized ciphertext storage/decryption path.

### 19.4. Normalization Is a Contract

`lower(trim(email))` is a simplistic example; emails and domain identifiers have complex canonicalization rules. Never invent ad-hoc normalization that silently merges distinct identities and weakens security.

## 20. Searchable Encryption: Trade-Offs Between Queries and Leakage

Common storage designs compare as follows:

| Storage Approach | Exact Equality Filtering? | Leakage / Limitations |
|---|---|---|
| Plaintext | Yes | Readable by anyone with `SELECT` |
| Randomized encryption / AEAD | Not via direct ciphertext equality | Strongly hides equality, requiring decryption or secondary index |
| Deterministic encryption | Yes on matching ciphertext | Leaks duplicate values and frequency distributions |
| HMAC / blind index beside ciphertext | Yes via lookup token | Leaks equality, frequency, and access patterns |
| App decrypts and scans | Yes in app logic | High I/O, broad plaintext exposure, poor scalability |

### 20.1. Why Doesn't Randomized Encryption Support LIKE?

Encrypting the same email twice with distinct random nonces produces two completely different ciphertexts. Therefore:

```sql
WHERE email_ciphertext = :encrypted_candidate
```

will not match plaintext equivalents unless specialized schemes are used.

Likewise, `LIKE '%@example.com'` over binary `bytea` ciphertext cannot evaluate domain semantics.

### 20.2. Deterministic Encryption Leaks Equality

Anyone reading ciphertext sees when two rows share **identical plaintext**. Across low-entropy attributes, frequency distributions leak substantial information.

Never casually deploy homegrown deterministic encryption just to index ciphertext while ignoring leakage.

### 20.3. Blind Indexes Do Not Prevent All Inference

A deterministic HMAC token still reveals:

- Whether two customers share the same normalized identifier.
- Which values occur most frequently.
- How often a token is queried.

And if the service and HMAC key are compromised, offline guessing returns. Treat blind indexes as **explicitly accepted leakage**, not zero-leakage searchable encryption.

## 21. Schema Pattern for Ciphertext and Blind Indexes

Illustrative table layout (never build custom cryptography primitives):

```sql
CREATE TABLE sec390.encrypted_contacts (
    customer_id bigint PRIMARY KEY
        REFERENCES sec390.customers(customer_id),
    tenant_id integer NOT NULL,
    email_ciphertext bytea NOT NULL,
    email_nonce bytea NOT NULL,
    email_tag bytea NOT NULL,
    email_lookup_token bytea,
    key_version text NOT NULL
);

CREATE INDEX idx_sec390_email_lookup
ON sec390.encrypted_contacts(
    tenant_id,
    email_lookup_token
);
```

Application workflow:

1. Canonicalize email per contract.
2. Compute HMAC lookup token using an independent lookup key from KMS/keystore.
3. Encrypt email using AEAD under the authorized data key.
4. Persist ciphertext, nonce, tag, token, and key version atomically in one transaction.
5. On lookup, recompute the token, filtering by tenant and token.
6. Decrypt authorized matches and verify business predicates.

### 21.1. Why Include tenant_id in the Index?

It scopes queries and partitions lookup values per tenant. Remember that an index starting with `tenant_id` **does not enforce RLS**; application and DB authorization still apply.

### 21.2. Separate Lookup Keys From Encryption Keys

Never reuse the same key for both HMAC and AEAD. Key/domain separation avoids cross-protocol weaknesses.

### 21.3. Rotating Lookup Keys

Changing lookup keys invalidates existing tokens, requiring controlled recomputation, dual-write, and dual-read windows during migration. Never drop old tokens until new indexes and code paths are live.

## 22. Masking: Hiding Data at Presentation Time

A view can omit raw columns and expose only masked projections:

```sql
CREATE VIEW sec390.customer_support_view
WITH (security_barrier = true)
AS
SELECT
    c.customer_id,
    c.tenant_id,
    c.full_name,
    CASE
        WHEN position('@' IN c.email) > 0 THEN
            left(c.email, 1) || '***@'
            || split_part(c.email, '@', 2)
        ELSE '***'
    END AS email_masked,
    CASE
        WHEN c.phone IS NULL THEN NULL
        ELSE '***-' || right(c.phone, 4)
    END AS phone_masked
FROM sec390.customers AS c;
```

Query it:

```sql
SELECT
    customer_id,
    full_name,
    email_masked,
    phone_masked
FROM sec390.customer_support_view
ORDER BY customer_id;
```

Illustrative output:

| customer_id | full_name | email_masked | phone_masked |
|---:|---|---|---|
| 1 | An | a***@example.invalid | ***-0001 |
| 2 | Binh | b***@example.invalid | ***-0002 |
| 3 | Chi | c***@example.invalid | ***-0003 |

### 22.1. What Does Masking Achieve Here?

The view interface outputs only masked emails and phone numbers, and omits `national_identifier` entirely.

### 22.2. What Does Masking Not Solve?

`sec390.customers` still holds plaintext. Any role with direct `SELECT` on the base table reads everything.

### 22.3. Masked Values Can Still Be Identifying

First letters, email domains, and last four phone digits can still identify individuals when correlated with other fields. Match masking depth to your threat model.

### 22.4. security_barrier Does Not Enforce Tenant Policy

Setting `security_barrier` stops risky optimizer pushdowns when a view forms a security boundary, yet **does not check** which tenant the caller belongs to. Our demo view still shows both tenants 7 and 8 unless RLS or authorization filters them.

## 23. Masking Views Require Tight Base-Table Permissions

If you grant support:

```sql
GRANT SELECT ON sec390.customers TO support_role;
```

that role can bypass the view and query plaintext directly. Clean design requires:

- Granting zero direct base-table `SELECT` to roles restricted to masked views.
- Granting only schema `USAGE` and `SELECT` on the masked view.
- Auditing view ownership and permissions.
- Preventing untrusted roles from creating functions or views in trusted schemas.
- Auditing every other API accessing the base table.

### 23.1. Example Role Setup (Requires DBA / CREATEROLE)

```sql
-- Run only in a learning environment with appropriate admin privileges.
CREATE ROLE sec390_support NOLOGIN;

GRANT USAGE ON SCHEMA sec390
TO sec390_support;

GRANT SELECT ON sec390.customer_support_view
TO sec390_support;

REVOKE ALL ON sec390.customers
FROM PUBLIC;
```

Notice `sec390_support` receives zero grants on the base table. Unless it inherits rights through another role, the masked view is its sole query path.

### 23.2. REVOKE FROM PUBLIC Does Not Strip Owner Rights

The table owner retains ownership privileges. If the support role owns the table or inherits a role holding base-table `SELECT`, this setup fails.

**Always audit effective privileges** of the actual login account, including inherited memberships and `SET ROLE` paths.

### 23.3. View Owners and Base-Table Privileges

Under PostgreSQL's default view behavior, base-table access is checked against the **view owner**, not the caller. Thus a caller holding `SELECT` on the view can query view columns even without `SELECT` on the base table.

While convenient for column filtering, it places high responsibility on the view creator: inadvertently projecting raw PII inside a view exposes it immediately.

### 23.4. Verify Using the Actual Role

Test from a session assuming the support role's exact privileges rather than assuming revocations worked based on superuser checks.

## 24. Column-Level Privileges: Not Every Role Reads Every Column

PostgreSQL supports granting `SELECT` on specific columns:

```sql
-- Apply to practice role if it exists.
GRANT SELECT (
    customer_id,
    tenant_id,
    full_name
)
ON sec390.customers
TO sec390_support;
```

Assuming no broader table grant exists elsewhere, the role can query the granted columns while remaining blocked from `email`, `phone`, and `national_identifier`.

### 24.1. Permitted Query

```sql
SELECT customer_id, full_name
FROM sec390.customers;
```

Succeeds under the support role when properly granted.

### 24.2. Rejected Query

```sql
-- Under a role holding only the column grants above:
SELECT email
FROM sec390.customers;
```

Rejected with column/table `permission denied`, assuming no alternate role membership grants access.

### 24.3. Hiding Columns in the UI Is Not Column Security

If the DB login holds full-table `SELECT`, rendering only two columns in client code provides zero DB security. Any SQL injection or direct query can select unrendered columns.

### 24.4. Column Grants and Masked Views Complement Each Other

- Column privileges: **block SQL access** entirely to restricted columns.
- Masked views: **provide controlled redacted forms** of sensitive fields to authorized viewers.

Use either or both depending on requirements and privileges.

## 25. Role-Based Dynamic Masking Requires Care

Suppose requirements specify:

```text
Support staff:  a***@example.invalid
PII team:       an@example.invalid
```

Often two explicit views/endpoints with clean grants are clearer than complex role-conditional expressions:

```text
sec390.customer_support_view -> masked data
sec390.customer_private_view -> full data, strictly restricted grants
```

### 25.1. Why Two Views Are Often Easier to Audit

Clear separation:

- Support roles hold `SELECT` solely on the masked view.
- Authorized specialists hold access to the private view or audited reveal API.
- Each view carries independent audit and logging rules.
- Grants are trivial to inspect for accidental over-exposure.

### 25.2. If Using Conditional CASE Logic by Role

A view/function switching output via `current_user`, role memberships, or auth context must account for:

- `session_user` differing from `current_user` under `SET ROLE` or `SECURITY DEFINER`.
- Inherited memberships and `SET ROLE` privileges.
- Never trusting a client-mutable GUC as authorization proof.
- Anyone with base-table `SELECT` bypassing masking altogether.
- Query optimizations or UDF side channels creating inference vectors.

Never slap a naive `CASE` statement together, call it "dynamic masking", and assume all paths are secure.

## 26. security_invoker Views and Base-Table Permissions

Modern PostgreSQL provides the `security_invoker` view option, switching base-relation privilege and RLS checks to the calling role.

Syntax example (on supported versions):

```sql
CREATE VIEW sec390.customer_invoker_view
WITH (security_invoker = true)
AS
SELECT
    customer_id,
    full_name
FROM sec390.customers;
```

### 26.1. Do Not Confuse With Default Views

With `security_invoker`, the caller's own base-table privileges apply under PostgreSQL semantics. A role holding `SELECT` on the view alone fails unless it also holds rights on the underlying tables.

### 26.2. A Common Design Trap

To make a `security_invoker` view run, teams sometimes hastily issue:

```sql
GRANT SELECT ON sec390.customers TO support_role;
```

which defeats column masking if full plaintext base-table access was granted simultaneously.

Choose intentionally:

- Owner-based view + strictly masked projection.
- Invoker-based view + strict column-level privileges and RLS.
- Or a dedicated API design.

Always verify live behavior under the actual role, not just by reading DDL.

## 27. RLS: Column Masking Differs From Row Filtering

Masking answers: "**How much of this column may be displayed?**"

Row-Level Security answers: "**Which rows may this role read or modify?**"

Example:

```text
tenant_id 7 -> customers An, Binh
tenant_id 8 -> customer Chi
```

If tenant 7's role should only see tenant 7, masking Chi's email to `c***@example.invalid` **still leaks** that Chi exists under tenant 8. The entire row must be blocked.

### 27.1. Applying RLS to the Table

Illustrative policy once the role and table grants exist:

```sql
CREATE ROLE sec390_tenant7 NOLOGIN;

ALTER TABLE sec390.customers
ENABLE ROW LEVEL SECURITY;

CREATE POLICY sec390_tenant7_read
ON sec390.customers
FOR SELECT
TO sec390_tenant7
USING (tenant_id = 7);
```

This is a single-role example policy, not a generic multi-tenant framework. Real systems also require `INSERT`/`UPDATE`/`DELETE` policies and verified tenant binding.

### 27.2. RLS Does Not Mask Visible Columns

If tenant 7 holds table `SELECT` and the policy filters `tenant_id = 7`, that role still sees raw email, phone, and `national_identifier` across **all tenant 7 rows**.

RLS and column masking address **orthogonal dimensions**.

### 27.3. Owners, Superusers, and BYPASSRLS

RLS includes bypass exceptions for superusers, `BYPASSRLS` roles, and normal table owners (unless `FORCE ROW LEVEL SECURITY` is set).

Never test RLS as a superuser and assume applications behave identically.

### 27.4. A tenant_id GUC Is Not Verified Identity

Common pattern:

```sql
USING (tenant_id = current_setting('app.tenant_id')::integer)
```

If clients can issue `SET app.tenant_id = '8'`, this provides **zero authorization**. Ensure session context is bound securely to verified identity without client tampering.

### 27.5. Unexpected Interactions Between RLS and View Owners

Default views evaluate base-table permissions and RLS relative to the view owner. Thus even with RLS active on the base table, a view owned by a bypassing role can return rows the caller should never see.

Always trace the **exact execution path**: direct table, owner-based view, `security_invoker` view, `SECURITY DEFINER` routine, and role memberships.

## 28. SECURITY DEFINER Can Break Masking If Misused

In PostgreSQL:

- `SECURITY INVOKER` is the default for functions.
- `SECURITY DEFINER` executes with the function owner's privileges.

A `SECURITY DEFINER` function reading plaintext tables can inadvertently give callers broad unmasked reveal capabilities.

### 28.1. Flawed Reveal API Example

A routine such as:

```sql
-- DANGEROUS PATTERN IF EXECUTE IS GRANTED BROADLY:
CREATE FUNCTION sec390.reveal_identifier(p_customer_id bigint)
RETURNS text
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec390, pg_temp
AS $$
    SELECT c.national_identifier
    FROM sec390.customers AS c
    WHERE c.customer_id = p_customer_id;
$$;
```

If its owner can read all rows and `EXECUTE` is granted loosely, callers can reveal anyone's identifier by supplying arbitrary IDs.

### 28.2. Pinning search_path Is Not Enough

A safe `search_path` only prevents object shadowing. It **does not** replace:

- Verifying caller authorization for the requested customer.
- Tenant isolation.
- Rate limiting.
- Reveal auditing.
- Revoking `PUBLIC EXECUTE`.
- Application SQL injection hygiene.
- Secret/key protection.

### 28.3. Secure-by-Design Reveal Flows

When a reveal capability is genuinely needed:

1. Document business purpose and authorized roles.
2. Verify caller authorization against a trusted identity inside the boundary.
3. Never trust an arbitrary `tenant_id` input alone.
4. Pin `search_path` and qualify critical tables/functions.
5. Revoke `EXECUTE` from `PUBLIC` and grant strictly to authorized roles.
6. Audit reveal events per policy without logging plaintext values.
7. Separate decryption keys from the DB where required by the threat model.

## 29. Query-Time Redaction Differs From Modifying Stored Data

There are at least three meanings of "hiding/masking" data:

### 29.1. Query-Time Presentation Masking

```sql
SELECT left(email, 1) || '***'
FROM sec390.customers;
```

The base table keeps the full email; only the query projection is redacted.

### 29.2. Generating Sanitized Copies for Non-Production

An ETL job may export pseudonymized or redacted fixtures for staging/testing. Even then, evaluate **re-identification risk** from combined attributes like age, region, purchase timestamps, and order codes.

### 29.3. Overwriting or Deleting Source Sensitive Data

```sql
UPDATE sec390.customers
SET phone = NULL
WHERE customer_id = ...;
```

This alters live business records rather than masking views. MVCC versions, WAL segments, replicas, and backups can still hold prior values temporarily until vacuumed, archived out, or expired per retention policies.

Never promise "instant deletion from every copy" solely because an `UPDATE` committed.

## 30. Masked Views Can Still Be Reverse-Engineered

Suppose a view reveals only:

```text
a***@example.invalid
```

yet the same role can run:

```sql
SELECT count(*)
FROM sec390.customers
WHERE email = 'an@example.invalid';
```

A user can brute-force candidate emails until matching counts reveal the true plaintext without ever selecting `email` directly.

### 30.1. Evaluate Query Capabilities Too

Any role forbidden from reading plaintext should also lack privileges enabling `WHERE`, `ORDER BY`, or matching predicates that act as guessing oracles over secret columns.

### 30.2. Counts, Ordering, and Timing All Leak Information

Side-channel leakage occurs via:

- Row counts satisfying hidden predicates.
- Result ordering based on secret columns.
- Distinguishable error messages across values.
- Response timing variations.
- Probing record existence by ID.
- Facets and aggregates.
- Pagination offsets and cross-table joins.

### 30.3. security_barrier Helps, Without Being Magic

`security_barrier` views restrict certain unsafe predicate pushdowns, yet never eliminate timing/inference channels or replace column grants and RLS.

## 31. Logs Are Another "Data Copy" Requiring Protection

Many breaches originate not from core tables, but from logs:

```text
INFO sql="INSERT INTO customers(email) VALUES('an@example...')"
INFO request_body={"password":"..."}
DEBUG token=...
ERROR decrypt failed for plaintext=...
```

### 31.1. Places Sensitive Data Lands Unexpectedly

- Application request/response logs.
- ORM SQL debug logging.
- PostgreSQL statement logs.
- Error logs.
- Audit extensions.
- Query performance tracing.
- APM spans.
- Core/crash dumps.
- Job/ETL logs.
- CI/CD deployment logs.
- Terminal buffers and `psql` command history.

### 31.2. Parameterization Does Not Guarantee Log Exclusion

Binding parameters avoids SQL injection and separates values from SQL text, yet drivers, PostgreSQL logging settings (`log_parameter_max_length`, etc.), or observability agents may still capture bind parameters depending on configuration.

Configure redaction, logging scopes, retention, access controls, and verify logs in staging.

### 31.3. pg_stat_statements Is Not a Secret Vault

Query normalization tools scrub constants, yet should never be relied upon as an absolute guarantee across every telemetry pipeline. Keep keys and secrets out of identifiers, comments, and error strings.

### 31.4. Never Emit Keys via RAISE NOTICE

`RAISE NOTICE 'key: %', secret;` in PL/pgSQL sends secrets straight to server/client logs. Scrub debug output before anything reaches production.

## 32. WAL, Replication, and CDC Also Fall Within Your Scope

Whenever PostgreSQL persists mutations:

- WAL records changes required for crash recovery and replication.
- Physical replicas mirror database storage.
- Logical replication / CDC streams publish column values per publication config.
- Backups and snapshots capture point-in-time copies.

### 32.1. When Columns Hold Plaintext in PostgreSQL

Replicas and CDC streams carry sufficient information to reconstruct plaintext. Disk encryption on the primary host does not protect downstream replicas or analytics pipelines automatically.

### 32.2. When Columns Hold App-Encrypted Ciphertext

PostgreSQL and replicas observe ciphertext for those columns, yet still carry:

- Metadata.
- Search tokens / blind indexes.
- IDs and foreign-key relationships.
- Ciphertext lengths.
- Timestamps.
- Remaining plaintext attributes.

Never treat an entire CDC event stream as automatically harmless.

### 32.3. Replication / CDC Privileges Are High-Sensitivity

A replication slot can stream records across every tenant, bypassing typical API boundaries. Lock down replication credentials, publication column/row filters, network links, logs, and downstream consumer storage.

## 33. Indexes, Caches, Materialized Views, and Search Indexes

Sensitive data often gets duplicated inside or alongside the DB:

```sql
CREATE INDEX ... ON ... (email);
```

And across:

- Generated columns.
- Expression indexes.
- Materialized views.
- Cached API payloads.
- Search engines.
- Reporting tables.
- Message queues.
- Analytics warehouses.

### 33.1. Masking Views Do Not Protect Unmasked Copies

Adding `customer_support_view` while leaving a plaintext `customer_search` table readable by support still exposes raw emails.

### 33.2. Indexing Encrypted Fields Requires Purpose-Built Design

A standard B-tree index over properly randomized ciphertext cannot answer email queries. If exact lookup is required, adopt an explicit blind-index/token design aligned with your threat model rather than decrypting the whole table during scans.

### 33.3. Caches and TTLs

If a role's PII access is revoked, cached plaintext remains readable until invalidated or expired. Storage encryption never flushes application caches on permission changes.

## 34. Roles and Least Privilege in PostgreSQL

Clean designs separate responsibilities across roles:

```text
app_public       -> SELECT public data
app_support      -> SELECT masked views
app_private      -> restricted access to required fields
app_writer       -> INSERT/UPDATE via defined APIs
app_migration    -> controlled DDL execution
db_operator      -> database operations and backups
key_operator     -> KMS key administration
auditor          -> read-only audit metadata access
```

Separate **database operations**, **business data access**, and **key usage** wherever possible.

### 34.1. Never Grant SUPERUSER to Applications

Superuser privileges bypass nearly all PostgreSQL security layers. Compromising a superuser app account immediately nullifies RLS, views, and grants.

### 34.2. Never Make Support Roles Table Owners

Table owners retain DDL authority and bypass RLS by default unless `FORCE` is set. Roles needing only masked views must never own PII tables.

### 34.3. Govern Default Privileges

Migrations creating new tables, views, or functions can accidentally inherit overly broad grants or omit revocations. Enforce `ALTER DEFAULT PRIVILEGES` per owner/schema and automated grant checks in CI.

### 34.4. EXPLAIN Is Also an Observation Channel

Any role permitted to run arbitrary SQL and `EXPLAIN` can infer table cardinalities, plans, statistics, and timings. Ad-hoc SQL access carries much higher risk than fixed, scoped APIs.

## 35. Verify Effective Privileges—Never Guess From One GRANT

PostgreSQL provides built-in privilege inspection functions:

```sql
SELECT
    has_table_privilege(
        'sec390_support',
        'sec390.customers',
        'SELECT'
    ) AS can_select_entire_table,
    has_column_privilege(
        'sec390_support',
        'sec390.customers',
        'email',
        'SELECT'
    ) AS can_select_email_column,
    has_table_privilege(
        'sec390_support',
        'sec390.customer_support_view',
        'SELECT'
    ) AS can_select_masked_view;
```

### 35.1. Column Grants Do Not Grant Whole-Table SELECT

A role with column-level `SELECT` on a subset of columns can run valid queries referencing only those columns without holding full-table `SELECT`. Inspect both table-level and column-level privileges.

### 35.2. Test as the Real Effective Role With Synthetic Data

Open a session running as the application's actual effective role to verify:

- Base-table `SELECT` is rejected as expected.
- Masked view `SELECT` succeeds.
- Queries cannot filter on restricted columns.
- Other tenants' rows remain invisible.
- Privileged decryption functions cannot be invoked.
- Alternate schemas/tables provide no backdoors to the source data.

### 35.3. Checking SQL Grants Does Not Prove Encryption

A role failing `SELECT email` proves privilege denial, not that data files on disk are encrypted. Permissions and cryptography are independent layers.

## 36. Handling the "Support Can Only See the Last 4 Phone Digits" Requirement

Suppose policy states:

> Support may confirm the last four digits of a customer's phone number, but must never see the full number or national ID.

Recommended workflow:

1. Confirm why the last four digits are needed.
2. When feasible, store or return strictly those four digits for confirmation flows.
3. If the full number is still needed elsewhere, tightly restrict storage and decryption paths.
4. Expose views/endpoints returning solely the redacted suffix.
5. Grant zero `SELECT` access on raw `phone` or `national_identifier` to support.
6. Enforce RLS and tenant scoping along the same path.
7. Audit API logs and exports.
8. Test against inference/oracle queries.
9. Log reveal/access events per policy.
10. Review roles and grants periodically.

### 36.1. Example Test Query

```sql
SELECT
    customer_id,
    full_name,
    phone_masked
FROM sec390.customer_support_view
WHERE tenant_id = 7
ORDER BY customer_id;
```

In our lab, this returns two tenant 7 rows. Remember that filtering `tenant_id = 7` inside client SQL **is not authorization** if callers can change `7` to `8`. Production requires binding tenant scope to verified identity or RLS.

## 37. Dynamic Data Masking Is Not a Uniform Built-In Core Feature Across Every PostgreSQL Setup

Some commercial RDBMS products provide a built-in "dynamic masking policy" syntax. Never copy vendor-specific syntax expecting PostgreSQL to behave identically.

In PostgreSQL, common building blocks include:

- Views with `CASE`/string expressions.
- Column-level privileges.
- RLS.
- Narrowly granted APIs/functions.
- Specialized vetted extensions or tools (where approved and audited).
- Application-tier redaction.
- ETL pipelines producing sanitized datasets.

### 37.1. Never Treat Any Masking Extension as a Blindly Proven Boundary

Before adopting an extension, evaluate:

- Version support and active maintenance.
- Role and DDL mechanics.
- Superuser/owner interactions.
- Interactions with views, functions, `COPY`, and replication.
- Performance overhead.
- Backup and restore behavior.
- Logging and alternate query channels.

### 37.2. Test Data Masking Does Not Automatically Produce Anonymous Exports

Masking a few digits or swapping names in an export often leaves linkable identifiers intact. True anonymization claims require formal re-identification risk analysis under applicable standards.

## 38. Authenticated Encryption and Data Integrity

Confidentiality alone is insufficient. Tampered ciphertext can:

- Fail decryption cleanly or noisily.
- Produce corrupted plaintext under unauthenticated modes.
- Trigger downstream application bugs or padding-oracle leaks.

### 38.1. Favor AEAD in New Designs

Use a vetted AEAD library configuration rather than improvising:

```text
AES-CBC + homegrown checksum
```

without deep expertise in padding oracles, MACs, key separation, and authentication checks.

### 38.2. Exercise Caution With Low-Level pgcrypto Primitives

Raw low-level ciphers in `pgcrypto` have sharp edges and do not automatically deliver modern authenticated encryption guarantees merely by choosing AES.

For app-level authenticated encryption, rely on vetted cryptography libraries instead of assembling custom protocols in raw SQL.

### 38.3. Binding Context via AAD

Include immutable context such as `tenant_id`, record type, or stable record ID in AAD where supported, ensuring ciphertext cannot silently be swapped across tenants or tables. Avoid mutable attributes in AAD that would break decryption whenever fields update.

## 39. Key Rotation and Migrations Must Not Lose Data

Phased migration from plaintext to app-encrypted fields:

```text
Phase 1: add ciphertext / key_version columns
          |
Phase 2: deploy controlled dual-write application
          |
Phase 3: backfill ciphertext with new key
          |
Phase 4: reconcile counts, IDs, integrity, authorization
          |
Phase 5: switch read path to ciphertext
          |
Phase 6: stop writing plaintext
          |
Phase 7: monitor and resolve straggler records
          |
Phase 8: purge plaintext per retention;
         evaluate WAL/backups/exports
```

### 39.1. Do Not Drop Source Columns Immediately After Backfill

Some rows might still lack backfill, hit key-version errors, undergo retries, or still be read by older app instances during rollout.

### 39.2. Dual-Writes Require Consistency Control

Writing plaintext and ciphertext across two separate transactions risks drift. Keep dual-writes atomic in one DB transaction or reconcile reliably.

### 39.3. Legacy Copies Remain After Migration

WAL archives, older backups, replicas, logs, and caches still retain pre-migration plaintext until retention windows expire. Never claim `ALTER TABLE DROP COLUMN` immediately purges every historical trace.

## 40. Incident Response: When a Key or Backup Leaks

Prepare ahead of time:

- Inventory of all keys and key owners.
- Mapping between datasets and key versions.
- Ability to disable or revoke KMS permissions rapidly.
- Procedures to rotate DEKs and KEKs.
- Batch re-encryption pipelines.
- Audit logs scrubbed of plaintext.
- Inventory of backups and downstream destinations.
- Ability to scope exposure windows and impacted records.
- Notification plans aligned with legal/compliance rules.
- Restore verification drills using active keys.

### 40.1. Key Compromised Without Confirmed Data File Exposure

Assess actual KMS permissions held by the attacker, potential ciphertext access paths, key usage logs, and timeframes before declaring data safe or fully compromised.

### 40.2. Backup Compromised While Keys Stay Properly Separated

Field encryption protects encrypted columns when keys remain isolated. Still assess plaintext columns, metadata, and any deterministic/blind-index inference risks.

### 40.3. Application Compromised

App-layer encryption cannot stop an attacker inside an application authorized to decrypt records. Revoke credentials, KMS permissions, and tokens, patch the entry point, and analyze access logs alongside key rotation.

## 41. Performance and Operational Trade-Offs of Encryption and Masking

Every defense carries operational cost:

| Mechanism | Typical Cost |
|---|---|
| TLS | Handshake and crypto CPU, certificate lifecycle management |
| Disk encryption | Storage I/O overhead, volume key administration |
| Field-level `pgcrypto` | DB CPU for encrypt/decrypt, larger ciphertext storage |
| App AEAD | App CPU/RAM, added metadata columns, KMS call latency |
| Masking views | String expression cost, restricted optimizer pushdowns |
| RLS | Policy predicate evaluation, planner and index impacts |
| Blind indexes | Extra columns/indexes, key rotation effort, equality leakage |
| Per-op KMS calls | Network latency, cost, availability and rate-limit exposure |
| Audit / log redaction | Pipeline processing and storage overhead |

### 41.1. Never Benchmark Only a Tiny SELECT

Measure:

- Workload-realistic p50/p95/p99 latency.
- Decryption frequency per request.
- KMS DEK caching and validity windows.
- App and DB CPU/memory utilization.
- WAL and backup size growth.
- Execution plans under RLS and masking views.
- Behavior during KMS throttling or outages.
- Backfill and rekey throughput across millions of rows.

### 41.2. Encryption Is Not a Query Optimization

Encrypted columns resist conventional plaintext indexing. Decrypting inside `WHERE`:

```sql
-- Anti-pattern for large-scale search:
WHERE decrypt(ciphertext, key) = search_value
```

scans huge row counts, spikes CPU, and exposes keys/plaintext to the DB server. Use purposefully evaluated lookup tokens when searchable encryption is required.

### 41.3. Caching Keys Does Not Mean Caching Forever

Caching DEKs improves latency at the cost of holding keys in RAM longer if an instance is compromised. Tune TTLs, permissions, invalidation, and auditing carefully.

## 42. Decision Matrix: Which Layer Solves Which Requirement?

| Requirement | Typical Layer / Tool | Remaining Gap to Watch |
|---|---|---|
| Prevent DB wire sniffing | TLS + server hostname validation | Does not protect plaintext after decryption in app/DB |
| Protect stolen offline disks | Disk / volume encryption | Does not block DBAs or authorized SQL roles |
| Protect exported backups | Backup encryption + storage ACLs | Holders of both key and file can restore |
| Prevent DB from seeing field plaintext | App-layer AEAD | App and KMS holders still access plaintext |
| Restrict decryption to specific roles | KMS policies + app auth | Must guard against app/role compromise |
| Show support only masked emails | Masked views/APIs + tight grants | Must block all base-table access paths |
| Isolate tenants | RLS/permissions + verified identity | Does not mask PII within a tenant's own rows |
| Block reads of a specific column | Column-level privileges | Disk files still contain plaintext unless encrypted |
| Store login passwords | Argon2id / password hashing | Still requires rate limits and MFA |
| Exact lookup on encrypted emails | Controlled HMAC / blind index | Leaks equality and frequency |
| Purge expired data | Retention / deletion workflows | Backups, WAL, and replicas follow separate lifecycles |
| Detect anomalous access | Auditing and monitoring | Logs themselves must scrub PII and keys |
| Prevent SQL injection | Parameterized SQL + validation | Does not replace authorization |
| Prevent data loss | Backups, restore drills, HA | Encryption never guarantees availability |
| Enforce data validity | Constraints and validation | Does not provide secrecy |
| Protect keys | KMS/HSM, secret managers, least privilege | Key-usage auth and app compromise remain critical |

**No single security switch covers every row in this table.** Identify your exact adversaries before selecting controls.

## 43. Common Design Flaws

### 43.1. "TLS is enabled, so our backups are encrypted"

False. TLS protects network transit, not exported `pg_dump` files.

### 43.2. "Disk encryption prevents DBAs from reading PII"

False in most setups. Once volumes are unlocked at runtime, the database reads plaintext blocks normally.

### 43.3. "Using pgcrypto keeps plaintext away from PostgreSQL"

False. `pgcrypto` runs inside PostgreSQL, receiving both keys and plaintext on the server.

### 43.4. "SHA-256 is enough for passwords"

False. Passwords require dedicated salted, work-cost password hashing rather than fast hashes.

### 43.5. "Hashing emails guarantees full anonymization"

False. Emails belong to guessable domains vulnerable to dictionary attacks and cross-table linking.

### 43.6. "Deterministic encryption leaks nothing"

False. Equality and frequency leak directly, enabling statistical inference.

### 43.7. "We have a masking view, so direct base-table SELECT is fine"

False. Roles can simply query the base table and bypass the view.

### 43.8. "RLS hides all PII automatically"

False. RLS restricts rows; roles permitted to read PII columns still see raw values within authorized rows.

### 43.9. "RLS passed when tested as the owner/superuser, so the app works identically"

Owners and superusers have bypass rules. Always test under actual effective runtime roles.

### 43.10. "SECURITY DEFINER is safe because SET search_path is pinned"

False. It still requires authorization checks, tight `EXECUTE` grants, and output minimization.

### 43.11. "If a role can't SELECT a secret column, it can't infer it"

If permitted in `WHERE`, `ORDER BY`, counts, errors, or timing paths, callers can still infer hidden values.

### 43.12. "Storing the key in the same database table is fine"

False under any threat model where an adversary captures the database or backup.

### 43.13. "One shared key for all tenants is simple and sufficient"

Creates a massive blast radius. Segment keys and permissions according to risk.

### 43.14. "Delete old keys immediately after rotation"

Breaks restoring legacy backups or unread historical records. Verify inventories, re-encryption, and restores first.

### 43.15. "DROP COLUMN immediately erases plaintext everywhere"

False. WAL, backups, replicas, exports, and logs retain historical copies per lifecycle.

### 43.16. "Bound parameters never enter logs"

False as an absolute guarantee. Certain logging and APM tracing configs capture parameter values.

### 43.17. "Masking renders data anonymous"

False. Masked exports can often still be re-identified via quasi-identifier combinations.

### 43.18. "Encrypted fields support LIKE and ORDER BY normally"

Not under randomized encryption; search requires dedicated token/index designs.

### 43.19. "AEAD guarantees availability"

False. Adversaries can delete or corrupt rows even without decrypting them.

### 43.20. "Keys never leave KMS, so compromised apps cannot leak PII"

An app holding `Decrypt` permission receives plaintext upon decryption and can leak it if compromised.

### 43.21. "security_barrier views make every query safe"

No. They do not replace grants, RLS, authentication, or inference defenses.

### 43.22. "Only production databases hold PII"

Staging clones, backups, BI stores, support tools, and crash dumps often contain real PII unless sanitized.

### 43.23. "Using HMAC tokens stops all leakage"

Equality, frequency, membership, and query patterns remain observable; key exposure re-enables dictionary attacks.

### 43.24. "Once encrypted, auditing is unnecessary"

False. You must monitor decryption calls, plaintext access, backup downloads, and key policy edits.

## 44. Practice Exercises With Explanations

### Exercise 1. Network Sniffing Between App and PostgreSQL

**Prompt:** An attacker can observe packets between the app and DB. Which control protects the channel?

**Answer:** TLS with proper certificate and hostname verification—typically `sslmode=verify-full` in libpq alongside hardened server TLS config, paired with strong auth and network controls.

### Exercise 2. Running Server and Role With SELECT on Email

**Prompt:** Disk encryption is active. Can a SQL role still `SELECT` plaintext emails?

**Answer:** Yes, if the role holds SQL `SELECT` and the column stores plaintext. Disk encryption does not block authorized SQL queries.

### Exercise 3. SQL Backup Uploaded to a Storage Bucket

**Prompt:** Does production volume encryption protect an exported SQL dump?

**Answer:** Not automatically; apply separate backup encryption and storage access controls.

### Exercise 4. Where Does pgcrypto Decryption Run?

**Answer:** Inside the PostgreSQL server process, meaning the database server observes plaintext during decryption.

### Exercise 5. Keeping Identifier Plaintext Out of the DB Completely

**Answer:** Encrypt at the application layer using a vetted AEAD library prior to `INSERT`, sending only ciphertext and required metadata to PostgreSQL.

### Exercise 6. Should Plaintext DEKs Live Next to Ciphertext?

**Answer:** No, whenever your threat model requires DB backups not to yield plaintext. Use KMS/HSM or proper key separation.

### Exercise 7. KMS Key Exposed Through App Compromise

**Prompt:** An app can decrypt every customer record. Is data safe if the app is breached?

**Answer:** No; attackers inside the app inherit its KMS `Decrypt` rights. Enforce least privilege, segmentation, auditing, and incident response.

### Exercise 8. Masking Emails With a SQL Expression

```sql
SELECT
    left(email, 1) || '***@'
    || split_part(email, '@', 2) AS masked_email
FROM sec390.customers;
```

**Answer:** Changes only the query's output representation without altering stored table data.

### Exercise 9. Support Holds SELECT on Both Masked View and Base Table

**Answer:** Flawed design because the role can query `email` and `phone` straight from the base table, bypassing masking.

### Exercise 10. Restrict Support to Reading Only ID and Full Name

**Answer:**

```sql
GRANT SELECT(customer_id, full_name)
ON sec390.customers
TO sec390_support;
```

Also verify the role inherits no broader table grants via group memberships.

### Exercise 11. Does RLS Filtering tenant_id=7 Mask Emails for Tenant 7?

**Answer:** No; if the role can select `email`, it still reads raw emails for tenant 7 rows.

### Exercise 12. Does the Masked View Filter Out Tenant 8 Automatically?

**Answer:** No unless an RLS policy, `WHERE` clause, or tenant authorization check enforces it. Our lab masking view outputs both tenants 7 and 8.

### Exercise 13. Is `current_setting('app.tenant_id')` a Tamper-Proof Auth Token?

**Answer:** Not if clients can `SET` it freely. Bind session context strictly from verified identity components.

### Exercise 14. Why Must View Ownership Be Audited?

**Answer:** Default view base permissions and RLS evaluate relative to the view owner; an overly privileged owner can expose rows callers should never see.

### Exercise 15. Does a `security_invoker` View Always Improve Masking?

**Answer:** Not if it forces granting direct base-table `SELECT` to the caller, bypassing column masking. Design grants carefully.

### Exercise 16. SECURITY DEFINER Function Revealing Data by `customer_id`

**Answer:** Enforce caller/tenant authorization inside the boundary, restrict `EXECUTE`, pin `search_path`, and audit calls; an arbitrary `p_customer_id` input is never proof of authorization.

### Exercise 17. Is SHA-256 Password Hashing Sufficient?

**Answer:** No. Use Argon2id/salted high-cost password hashing alongside brute-force and MFA controls.

### Exercise 18. Does Hashing Emails With SHA-256 Anonymize Them?

**Answer:** No. Emails fall quickly to dictionary attacks and digests permit cross-dataset linking.

### Exercise 19. How Does HMAC Differ From Plain SHA-256?

**Answer:** HMAC incorporates a secret key so tokens cannot be computed or verified purely from public inputs; still requires key custody and leakage analysis.

### Exercise 20. Can an Email Be Decrypted From Its HMAC Token?

**Answer:** No. If you need the real email later, maintain a separate authorized encrypted store.

### Exercise 21. Does Randomized Encryption Produce Identical Ciphertext for Identical Plaintext?

**Answer:** With properly generated random nonces, no—which is why direct ciphertext equality lookups fail.

### Exercise 22. What Does Deterministic Encryption Leak?

**Answer:** Plaintext equality across records and value frequency distributions within that scope.

### Exercise 23. Does a Blind Index Prevent All Information Leakage?

**Answer:** No. Token equality, frequency, and query access patterns still leak.

### Exercise 24. Does `LIKE` Work Over Properly Encrypted Ciphertext?

**Answer:** Not with plaintext semantics; design dedicated lookup/search strategies.

### Exercise 25. Is Raw AES-CBC Without a MAC Sufficient?

**Answer:** Never assume unauthenticated modes ensure integrity or authenticity. Favor vetted AEAD schemes.

### Exercise 26. Why Store `key_version`?

**Answer:** To know which key and algorithm to use for decryption during rotations and historical restores.

### Exercise 27. Does Rotating a KEK Require Re-Encrypting Every Row?

**Answer:** Not always; envelope encryption allows rewrapping DEKs. Re-encryption is needed if a DEK leaked or policy/algorithms demand it.

### Exercise 28. Does `DROP COLUMN` After Migration Immediately Erase All Plaintext?

**Answer:** No; WAL, backups, replicas, exports, and logs retain old values until retention expires.

### Exercise 29. Is Logging a SQL Statement With a Literal Password Safe?

**Answer:** No; SQL history and logs expose credentials. Parameterize queries, scrub logs, and audit parameter-logging settings.

### Exercise 30. Why Are Backups Often Weaker Than Live Production DBs?

**Answer:** Backups may be plaintext exports, broadly accessible, replicated across buckets, and retained long-term even when live DB disks are encrypted.

### Exercise 31. Inspecting Active Connection TLS Status

```sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

**Answer:** Reports backend TLS usage, without verifying client-side hostname checking.

### Exercise 32. Showing Support Strictly the Last 4 Phone Digits

**Answer:** Expose an API/view returning `right(phone, 4)` with tenant scoping, revoke raw column access, block alternate table paths, and note residual re-identification risk across combined fields.

### Exercise 33. Filtering `WHERE email='known@example.invalid'` Without `SELECT`

**Answer:** Control whether the role may reference `email` in `WHERE` at all. If permitted, match counts act as an existence oracle; restrict column SQL capabilities strictly.

### Exercise 34. What If a Role Has `SUPERUSER`?

**Answer:** SQL permissions and RLS boundaries can be bypassed. Never assign superuser to applications; use app-side encryption and key separation if the threat model restricts DBAs.

### Exercise 35. Auditing Whether Support Can Read `email`

```sql
SELECT has_column_privilege(
    'sec390_support',
    'sec390.customers',
    'email',
    'SELECT'
);
```

**Answer:** Checks effective privilege; follow up with live role-based tests.

### Exercise 36. Does App-Encrypted Data Enter WAL as Plaintext?

**Answer:** When only ciphertext is sent for that field, WAL captures ciphertext and metadata; unencrypted sibling columns, logs, and downstream systems still need protection.

### Exercise 37. What Risks Arise During KMS Outages?

**Answer:** Services may fail to decrypt data, impacting availability; design bounded DEK caching, timeouts, and fail-safe policies rather than granting unlimited bypass access.

### Exercise 38. Should Keys Be Logged When Decryption Fails?

**Answer:** Never. Log error codes, correlation IDs, key versions, and non-sensitive metadata—never keys or plaintext.

### Exercise 39. Does Staging Data Need Masking or Synthetic Replacement?

**Answer:** Yes whenever staging holds PII. Prefer synthetic fixtures or policy-approved sanitized copies; never treat non-production environments as zero-risk.

### Exercise 40. Two Layers Needed for Tenant-Scoped Masked Support Access

**Answer:** Combine **row authorization** (RLS/permissions) and **column masking** (masked view/API or column grants), backed by verified identity and zero unmasked base-table backdoors.

## 45. PostgreSQL Data Protection Implementation Checklist

| Question | Verification Item |
|---|---|
| Classified data and usage requirements? | PII / secrets / public / internal |
| Eliminated unneeded collection? | Data minimization |
| Modeled realistic adversaries? | Network, disk, SQL role, DBA, app, backups |
| App-to-DB connections encrypted with TLS? | Client and server TLS config |
| Clients verify CA and server hostname? | `verify-full` where applicable |
| What does at-rest encryption cover? | Volumes, WAL, temp files, snapshots |
| Are backup exports encrypted independently? | Storage ACLs and separate KEKs |
| Do replicas, CDC, and warehouses have equal protection? | Downstream inventory |
| Which fields must stay hidden from DB plaintext? | App-layer encryption |
| Vetted AEAD algorithm used? | Proper nonce, tag, and AAD handling |
| Are keys strictly separated from DB and backups? | KMS/HSM and key isolation |
| Are decryption rights scoped per identity/tenant? | Least privilege |
| Key versioning and rotation plan ready? | Restore and rekey readiness |
| Need exact lookup on encrypted values? | Documented blind-index leakage |
| Passwords hashed properly? | Argon2id with unique salts and tuned cost |
| Using fast SHA-256 for passwords? | Never |
| Support sees only masked required fields? | Masked view/API |
| Support blocked from direct base-table `SELECT`? | No unnecessary base grants |
| Column grants audited under effective role? | `has_column_privilege` |
| Tenant boundaries enforced? | RLS and verified identity |
| Audited owner/`BYPASSRLS`/superuser effects? | No assumptions about RLS |
| Audited view owners and `security_invoker`? | Base-table access verification |
| Audited `SECURITY DEFINER` reveal routines? | `EXECUTE` ACLs and `search_path` |
| Checked query capabilities against oracle leaks? | `WHERE` / `COUNT` / `ORDER BY` |
| Logs and traces scrubbed? | Zero PII, keys, or bind secrets |
| Retention enforced across backups/clones/staging? | Lifecycle and purge plans |
| Audited decrypt/backup/export operations? | Monitoring and alerts |
| Incident response and key revocation ready? | Compromise playbooks |
| Tested under real low-privilege roles with fake data? | Not tested solely as superuser |
| Benchmarked CPU, latency, and KMS outage handling? | Performance and availability |
| Verified restoring backups with older rotated keys? | Rotation without data loss |
| Aligned with legal and retention policies? | Beyond SQL configuration alone |

## 46. Quick Reference Table

| Goal | Typical Control | Do Not Confuse With |
|---|---|---|
| Encrypt DB network traffic | TLS | Disk encryption |
| Protect stolen offline disks | Volume encryption | SQL authorization |
| Encrypt a column inside DB | `pgcrypto` (when DB trust permitted) | Hiding plaintext from DB server |
| Keep plaintext out of DB entirely | App-layer AEAD | Unscoped KMS access |
| Rotate managed keys cleanly | KMS/HSM / envelope encryption | Storing keys in a DB table |
| Show masked emails to support | Masked view / API | Full-disk encryption |
| Block `SELECT` on email column | Column-level privileges | Hiding columns in frontend UI |
| Isolate tenants across rows | RLS / verified authorization | Display `CASE` masking |
| Store login passwords | Argon2id / password hashing | Plain SHA-256 |
| Equality search on encrypted emails | Keyed HMAC / blind index | Leakage-free frequency hiding |
| Limit backup exposure | Backup encryption + ACLs | Database connection TLS |
| Prevent SQL injection | Bound parameters | Field masking |
| Prevent log leakage | Redaction and retention | "TLS is enough" |
| Prevent data loss | Backups, restore drills, HA | Encryption alone |
| Protect non-prod copies | Synthetic/sanitized data + access control | Merely renaming columns |
| Prove privilege boundaries | Testing under real effective roles | Testing as superuser |

## 47. Official Documentation and Further Study

**PostgreSQL:**

- [SSL Support](https://www.postgresql.org/docs/current/ssl-tcp.html) — server-side TLS configuration.
- [libpq SSL Support](https://www.postgresql.org/docs/current/libpq-ssl.html) — CA/hostname validation and `sslmode`.
- [pg_stat_ssl](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-SSL-VIEW) — backend TLS connection inspection.
- [pgcrypto](https://www.postgresql.org/docs/current/pgcrypto.html) — PGP encryption, hashing, HMAC, and key/data caveats.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — `GRANT`/`REVOKE` and column-level privileges.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS, owner/bypass rules, and policy behavior.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html) — `security_barrier`/`security_invoker` and view privileges.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — `SECURITY DEFINER`, ownership, and privileges.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html) — `search_path` and safe routine design.
- [Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html) — risks and controls for SQL/parameter logging.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup strategies and recovery limits.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — WAL archiving and point-in-time recovery.

**Beyond PostgreSQL:**

- Current documentation for your organization's cryptographic libraries and KMS/HSM platforms.
- OWASP Password Storage Cheat Sheet and Argon2id guidance.
- Governing legal, data classification, retention, and breach-notification policies.

Examples in this guide are instructional and use synthetic fixtures. Real deployments must verify PostgreSQL versions, extension permissions, cipher modes, key policies, TLS verification, grants/RLS, application handling, and backups. **Do not treat SQL snippets in this article as executed production outputs.**

## 48. Summary: Each Layer Protects One Slice of the System

Decision map:

```text
Sensitive data
    |
    +-- Truly necessary to store?
    |       -> If not, do not collect it
    |
    +-- In transit?
    |       -> TLS + server verification
    |
    +-- At rest on storage?
    |       -> Disk / backup encryption
    |
    +-- May the DB see plaintext?
    |       -> pgcrypto if allowed by threat model
    |       -> Otherwise app-layer encryption + KMS
    |
    +-- Who may decrypt?
    |       -> Key policies, least privilege, auditing
    |
    +-- Who may access which rows?
    |       -> Authentication, GRANT, RLS
    |
    +-- Who may see which columns?
    |       -> Column privileges, masked views/APIs
    |
    +-- Copied anywhere else?
    |       -> Logs, WAL, backups, replicas, CDC, BI, caches
    |
    +-- If keys or data leak?
            -> Rotation, incident response, recovery
```

### Core Principles to Remember

1. **Encryption does not replace access control.** TLS and volume encryption never stop a role holding `SELECT` from reading plaintext columns.
2. **Masking is not encryption.** Views present redacted strings while underlying plaintext often stays intact.
3. **RLS and column grants solve orthogonal problems.** RLS filters rows; masking and column grants constrain columns and display forms.
4. **DB-side `pgcrypto` differs from app-layer encryption.** `pgcrypto` handles keys and plaintext on the DB host; app-layer encryption keeps field plaintext off the DB server.
5. **Key separation governs real field-encryption strength.** If an attacker capturing ciphertext can also reach the key, secrecy collapses.
6. **Password storage requires dedicated password-hashing algorithms.** Never substitute fast SHA-256 or reversible encryption for passwords.
7. **Hashing or HMACing identifiers does not anonymize them by default.** Account for guessing, equality leakage, key custody, and dataset linkability.
8. **There is no zero-leakage searchable encryption for free.** Equality lookups inherently trade exact matching against frequency/pattern leakage.
9. **Every copy introduces a new risk perimeter.** WAL, backups, logs, search engines, BI tools, staging DBs, and caches all need governance.
10. **`SECURITY DEFINER`, view ownership, and RLS bypasses must be verified under real effective roles.** Never treat superuser runs as authorization proof.
11. **Key rotation and data deletion are multi-step workflows.** Never purge keys or plaintext before validating restores, replication lag, and retention schedules.
12. **Threat modeling comes before choosing tools.** Define adversaries, protected assets, and trust boundaries before picking `pgcrypto`, KMS, views, RLS, or disk encryption.

**One sentence to remember:** *TLS protects data in motion; disk/backup encryption protects offline storage copies; field encryption protects values when keys are absent; masking limits visual presentation; GRANT/RLS governs authorized access; and key management determines whether encryption actually keeps secrets.* Only when these layers work together under an explicit threat model and role-based verification is PostgreSQL data meaningfully protected.
