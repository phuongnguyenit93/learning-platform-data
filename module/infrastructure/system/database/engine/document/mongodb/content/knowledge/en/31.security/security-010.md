# Query, Index, and Feature Limitations with Field Encryption in MongoDB

An application may need to store highly sensitive data such as **national IDs, account numbers, salaries, addresses, customer profiles, or contract contents** in MongoDB. Disk encryption alone protects data at the storage layer, yet the database process still handles readable values once decrypted on the server. Many systems enforce a stricter requirement: **sensitive values must be encrypted by the application before ever reaching MongoDB**.

MongoDB offers two main approaches for in-use field encryption:

- **Client-Side Field Level Encryption (CSFLE)**, using *deterministic* or *randomized* encryption.
- **Queryable Encryption (QE)**, supporting declared query types on encrypted data without revealing plaintext to the server.

However, **encryption changes what you can query**. Once a field is ciphertext, you can no longer assume keyword search, range comparisons, sorting, averaging, unique indexes, or shard keys work as they do on plaintext fields. Exact capabilities depend on encryption mode, MongoDB version, driver, key setup, and the query types enabled from the start.

This lesson explains those limitations in detail, how to design schemas around them, and how to avoid common mistakes when deploying field encryption in MongoDB.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **TLS, encryption at rest, CSFLE, and Queryable Encryption**.
2. Explain why the server stores **BinData ciphertext** and cannot directly interpret plaintext semantics.
3. Distinguish **deterministic** and **randomized** CSFLE.
4. Identify which query types **Queryable Encryption** supports by version and **`queryType`**.
5. Explain why **B-tree/unique/text/vector/TTL indexes** cannot be applied arbitrarily to encrypted fields.
6. Recognize limitations around **aggregations, sort, group, lookup, update, upsert, null, arrays, collations, sharding, views, and time series**.
7. Design schemas combining **plain routing/filter fields** with **encrypted secret fields** without violating privacy requirements.
8. Construct queries through an **encryption-configured MongoDB driver** rather than sending plaintext from an unconfigured client.
9. Plan **key management, metadata/index overhead, migrations, monitoring, backups, and testing**.

**Version scope:** MongoDB continues evolving Queryable Encryption. Older versions may support only equality, or equality + range; prefix/suffix/substring appeared in preview on MongoDB 8.2 and reached **GA in MongoDB 9.0** in September 2026. Every example must be verified against your deployment's **server version, driver version, Automatic Encryption Shared Library, and FCV**. Never assume newer MongoDB syntax or features work on a 6.x or 7.x cluster.

## 2. Which Layers Encrypt Data?

### 2.1. TLS Protects Data in Transit

TLS encrypts traffic between endpoints:

~~~text
Application  ===== TLS connection =====>  MongoDB
~~~

When configured and verified properly, it protects against eavesdropping and tampering on the wire. Yet **TLS does not keep plaintext secret from the server** once the server receives and decrypts traffic at the endpoint.

### 2.2. Encryption at Rest Protects Stored Data

Storage-level encryption protects files, snapshots, and disks against unauthorized physical or storage access. Still, an authorized MongoDB process continues processing **plaintext values** of regular fields once read and decrypted from storage.

### 2.3. Client-Side Field Encryption Protects Values Before Transmission

~~~text
Application
  |
  |  plaintext: "ID-123456789"
  v
MongoDB Driver + encryption configuration + keys
  |
  |  ciphertext: BinData(...)
  v
MongoDB Server
  |
  |  Stores ciphertext and related metadata
  v
Database files, replication, backups
~~~

On read:

~~~text
MongoDB Server -> ciphertext BinData(...)
                          |
                          v
             Authorized Driver + keys
                          |
                          v
               plaintext in application
~~~

A client lacking the decryption keys and configuration sees only ciphertext, even if it has read privileges on the MongoDB collection.

**Conclusion:** relying solely on TLS, encryption at rest, or field encryption does not replace the remaining layers. Combine authentication, authorization, key management, and log/backup protection.

### 2.4. Threat Model

Client-side encryption reduces plaintext exposure when an attacker obtains data from the server, disks, or database backups **without holding the decryption keys**.

It **does not automatically protect** when:

- The application host holding the keys is compromised.
- A process with decryption rights intentionally exports plaintext.
- An API returns sensitive data to unauthorized users.
- The secret manager or KMS credentials leak.
- The application writes plaintext into logs, traces, caches, or exports.
- Queries on public fields leak private facts via metadata.

Thus, encrypting a field does not eliminate leakage risks across **every component of the system**.

## 3. Three Encryption Modes to Distinguish

### 3.1. Deterministic CSFLE

Given the same key, type, and input value, deterministic encryption produces a **consistent ciphertext** per the algorithm.

~~~text
"acct-123" --encrypt K--> Ciphertext A
"acct-123" --encrypt K--> Ciphertext A
"acct-999" --encrypt K--> Ciphertext B
~~~

Key advantage: the driver can encrypt **literal values in equality queries** into matching ciphertexts, and the database compares ciphertexts against stored records.

**Security trade-off:** identical values yield identical ciphertexts. On low-cardinality fields (e.g., gender, three-label statuses, credit tiers), an observer can run **frequency analysis** on ciphertexts to infer distributions. Never treat deterministic encryption as a safe default for every secret field.

### 3.2. Randomized CSFLE

With the same value and key, each encryption produces a different ciphertext:

~~~text
"acct-123" --encrypt K--> Ciphertext R1
"acct-123" --encrypt K--> Ciphertext R2
"acct-123" --encrypt K--> Ciphertext R3
~~~

This hides duplicate ciphertexts far better than deterministic encryption, but MongoDB **cannot use direct ciphertext equality** to match records sharing the same plaintext.

Randomized CSFLE fits fields that only need **storage and post-decryption display**; the app queries by another field and fetches the encrypted field to decrypt on the client.

### 3.3. Queryable Encryption (QE)

QE enables **declared query types on encrypted fields** without producing identical deterministic ciphertexts for equal plaintexts.

~~~text
Application + QE-enabled Driver
       |    encrypt value and query payload
       v
MongoDB:
  ciphertext encrypted fields
  internal encrypted query metadata/tags
       |
       v
  query engine finds matching candidates
       |
       v
Driver decrypts result for authorized caller
~~~

QE produces randomized ciphertexts even for identical plaintexts and relies on **encrypted indexes/metadata** built for the configured `queryType`.

Do not view QE as merely renamed deterministic CSFLE. Query capabilities, indexing, metadata collections, write costs, collection creation, and limitations all differ.

### 3.4. High-Level Comparison Table

| Property | Deterministic CSFLE | Randomized CSFLE | Queryable Encryption |
|---|---|---|---|
| Same plaintext yields same ciphertext? | Yes under identical encryption params | No by design | No by design |
| Equality on encrypted field | Yes when driver/query properly configured | No | Yes if `queryType` supports equality or range |
| Range on encrypted field | Does not preserve plaintext ordering | No | Yes when `queryType: range` enabled on supported version |
| Prefix/suffix/substring | No | No | Per supported version and string `queryType` |
| Encrypt field without querying it | Yes | Yes | Yes via `queryType: none` |
| Standard index on ciphertext | Can serve deterministic equality under matching conditions | Carries no plaintext semantics | Never create B-tree index on encrypted field in place of encrypted index |
| Plaintext uniqueness via standard index | Not universally guaranteed; evaluate carefully | No | Not guaranteed for encrypted fields |
| Server sees plaintext? | No, if routed through proper encryption | No, if properly configured | No, if properly configured |
| Specialized query metadata cost | Lower than QE, still verify index impact | Usually no field queries | QE maintains metadata collections/tags with dedicated management cost |

## 4. Why Does Encryption Affect Queries?

A normal query:

~~~javascript
db.employees.find({ salary: { $gt: 50000 } });
~~~

requires MongoDB to compare **numeric values** and return documents where `salary` exceeds 50000.

When `salary` is encrypted with CSFLE, the server only holds something like:

~~~javascript
{
  salary: BinData(/* encrypted payload */)
}
~~~

MongoDB cannot tell which ciphertexts correspond to salaries above 50000 by comparing **byte ordering** against the ciphertext of 50000. Ciphertext ordering bears no relation to plaintext ordering.

An encrypted field also ceases to behave like a plain String for operations such as:

~~~javascript
{ email: /@example\.com$/ }
{ salary: { $gte: 50000 } }
{ name: { $regex: "^Nguyen" } }
{ $expr: { $add: ["$salary", 500] } }
~~~

These work **only when an encryption feature explicitly supports that query type**; never assume every plaintext query works identically.

### 4.1. “Runs Without Error” Can Still Return Wrong Results

Especially with **explicit/manual encryption**, the server may apply BSON operators directly to `BinData` ciphertexts. For example, `$gt` between two ciphertexts may execute server-side without throwing an error, yet the result **does not compare plaintext salaries**.

Drivers with **automatic encryption** block many unsupported operations. Never bypass those guards by manually encrypting a literal and sending a range comparison straight to the server.

### 4.2. Querying Unencrypted Fields Remains Useful

A document may store:

~~~javascript
{
  tenantId: "TENANT-A",
  recordId: "REC-1001",
  status: "ACTIVE",
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  identity: {
    nationalId: BinData(/* encrypted */)
  },
  salary: BinData(/* encrypted */)
}
~~~

The application can filter by **tenantId**, **recordId**, **status**, and **createdAt** when those fields remain unencrypted and indexed; then the authorized driver decrypts **nationalId** and **salary**.

However, leaving `status` or `createdAt` plaintext **exposes that metadata** to anyone reading the server. That is an approved **threat-model decision**, not a harmless trick to dodge encryption.

## 5. Query Limitations with Deterministic CSFLE

In automatic CSFLE mode, the driver analyzes queries, encrypts supported literals, and decrypts results. For **deterministically encrypted** fields, MongoDB documentation lists supported comparison operators including:

- **$eq**, **$ne**.
- **$in**, **$nin**.
- Logical combinations **$and**, **$or**, **$not**, **$nor** within supported conditions.
- **$exists** checks field presence without comparing plaintext content.

Do not infer from this list that **all BSON types** or deeply nested structures are supported. Automatic CSFLE restricts arrays/objects, booleans, decimals/doubles in deterministic comparisons, and comparisons with `null` or regexes.

### 5.1. Equality Using a CSFLE-Configured Driver

Suppose the app has a **customers** collection and a **MongoClient configured with automatic CSFLE** encrypting **identity.taxId** deterministically.

Query logic:

~~~javascript
// Executed by a client configured with auto encryption.
const result = await encryptedCollection.findOne({
  "identity.taxId": "TAX-000123"
});
~~~

The driver encrypts the literal **TAX-000123** before sending the query, the server matches ciphertexts, and the authorized driver decrypts the returned field.

**Do not expect this query to return results from an unconfigured `mongosh` session**, because the server does not encrypt plaintext query literals on its own.

### 5.2. $in with Multiple Values

~~~javascript
// Illustrates a query from a configured automatic CSFLE client only.
await encryptedCollection.find({
  "identity.taxId": {
    $in: ["TAX-000123", "TAX-000987"]
  }
}).toArray();
~~~

Plaintext values in the list must match the driver's configured schema/algorithm. Mismatched types, mixing `null`, or querying a randomized field will fail to match as expected.

### 5.3. $exists Is Not Value Matching

~~~javascript
await encryptedCollection.find({
  "identity.taxId": { $exists: true }
}).toArray();
~~~

The server checks field presence without knowing plaintext. However, **`$exists: true`** cannot distinguish `"TAX-000123"` from `"TAX-000987"`.

### 5.4. Never Use $gt or $sort on Deterministic Salary

~~~javascript
// DOES NOT express valid plaintext comparison under deterministic CSFLE:
await encryptedCollection.find({
  salary: { $gt: 50000 }
}).toArray();
~~~

~~~javascript
// No guarantee of sorting by plaintext salary:
await encryptedCollection.find()
  .sort({ salary: -1 })
  .toArray();
~~~

If server-side range queries on encrypted salaries are required, evaluate **Queryable Encryption `queryType: range`** and its constraints—or redesign so salary range queries are unnecessary.

### 5.5. $regex and Collations

~~~javascript
// Not supported by deterministic CSFLE as a plaintext regexp:
await encryptedCollection.find({
  "identity.taxId": /^TAX-00/
}).toArray();
~~~

Enabling a **case-insensitive collation** also does not cause the server to decrypt ciphertexts for string comparison. When case/accent-insensitive equality is required under CSFLE, the app can **normalize inputs before encrypting** under an approved business contract.

For example, normalizing emails consistently can help lookups, **yet never assume you can lowercase every email or user identifier** without altering identity semantics. Define exact business normalization rules first.

### 5.6. Why Is Deterministic Encryption Unsuitable for Low-Cardinality Fields?

Example encrypted field:

~~~text
employmentStatus:
  ACTIVE  -> 95%
  LEAVE   ->  4%
  ENDED   ->  1%
~~~

Because deterministic ciphertexts repeat for equal values, anyone observing ciphertext counts sees three buckets matching those ratios and can infer the largest bucket is `ACTIVE` using external knowledge.

Evaluate **cardinality**, frequency-analysis exposure, and real field sensitivity—never assume equality convenience outweighs privacy requirements.

## 6. Query Limitations with Randomized CSFLE

With randomized encryption, equal plaintexts produce different ciphertexts. Therefore **direct equality queries on the encrypted field are impossible via normal queries**.

### 6.1. Example Field That Does Not Need Querying

Document:

~~~javascript
{
  _id: "EMP-1001",
  tenantId: "TENANT-A",
  publicEmployeeCode: "E-1001",
  medicalNote: BinData(/* randomized CSFLE ciphertext */)
}
~~~

Application read:

~~~javascript
// Query on unencrypted fields:
const employee = await encryptedCollection.findOne({
  tenantId: "TENANT-A",
  publicEmployeeCode: "E-1001"
});

// If the driver has permissions and keys, medicalNote is decrypted.
~~~

**medicalNote** is protected with randomized CSFLE because workflows never search by note contents.

### 6.2. Queries That Fail Intent

~~~javascript
// Plaintext equality is not supported on a randomized encrypted field:
await encryptedCollection.findOne({
  medicalNote: "penicillin allergy"
});
~~~

~~~javascript
// Regex is also meaningless on ciphertext:
await encryptedCollection.find({
  medicalNote: /penicillin/i
}).toArray();
~~~

If a new requirement demands keyword search over notes, simply adding an index cannot restore searchability. Revisit the **threat model, encryption type, QE capabilities, and auxiliary metadata architecture**.

### 6.3. Never Use a Unique Index to Enforce Plaintext Uniqueness

If two documents share:

~~~text
medicalNote plaintext = "same value"
~~~

randomized encryption outputs two distinct ciphertexts. A unique index on the ciphertext treats them as **two different values** and allows both documents to be inserted.

Plaintext uniqueness must be enforced via a separate mechanism rather than relying on unique indexes over randomized ciphertexts.

### 6.4. You Do Not Need to Encrypt Every Field

A design can keep **`identity.primaryKey`** as an uninformative random key for document lookup while encrypting rarely queried fields with randomized encryption.

The key rule is ensuring **the lookup key genuinely reveals no restricted information**, with proper uniqueness and access control. Avoid taking a secret ID and merely renaming the field to `publicLookupKey`.

## 7. Queryable Encryption: `queryType` Defines the Limits

In QE, field settings inside **`encryptedFields`** specify both encryption and permitted query types.

### 7.1. Encrypt Without Querying: `queryType: none`

Example **`encryptedFields` schema fragment**:

~~~javascript
{
  path: "medicalNotes",
  bsonType: "string"
  // No queries declared -> non-queryable by default.
}
~~~

The field is encrypted without an encrypted-query index for plaintext lookups. The app queries by other metadata and the driver decrypts on read.

### 7.2. Equality `queryType`

~~~javascript
{
  path: "identity.taxId",
  bsonType: "string",
  queries: {
    queryType: "equality"
  }
}
~~~

Designed for **exact matching**. With a valid driver/QE setup:

~~~javascript
await encryptedCollection.findOne({
  "identity.taxId": "TAX-000123"
});
~~~

The server processes the query via QE without seeing plaintext `taxId`. This does not turn the field into full-text search or enable arbitrary string operators.

### 7.3. Range `queryType`

On MongoDB versions supporting range QE (GA from MongoDB 8.0), numeric or `Date` fields can declare:

~~~javascript
{
  path: "salary",
  bsonType: "int",
  queries: {
    queryType: "range",
    min: 0,
    max: 1000000
  }
}
~~~

Query example:

~~~javascript
await encryptedCollection.find({
  salary: {
    $gte: 50000,
    $lt: 100000
  }
}).toArray();
~~~

**`min`**, **`max`**, and parameters like **`sparsity`, `trimFactor`, and `precision`** impact metadata storage, performance, and queryable bounds; exact configuration depends on version and `bsonType`. This is an illustrative fragment, not a full collection and KMS setup.

### 7.4. String `queryType`: Prefix, Suffix, Substring

In versions supporting **QE string queries**, you can enable:

- **prefix**: values starting with a prefix.
- **suffix**: values ending with a suffix.
- **substring**: values containing a substring.

Business examples:

~~~text
prefix("INV-2026-")
suffix("-00418")
substring("PAY")
~~~

These are not arbitrary regexes on ciphertext. They use QE's **dedicated query types and expressions**, with constraints:

- Apply only to **BSON String** per feature rules.
- Include parameters for **`caseSensitive`**, **`diacriticSensitive`**, and query string length.
- **Prefix and suffix** can be configured together on one field in supported versions.
- **Substring** cannot be freely combined with other `queryType`s on the same field.
- Length caps, **string** algorithms, and compatibility differ between **8.2 preview** and **9.0 GA**.

**Version history:** MongoDB 8.2 introduced a public preview of string queries with preview query types/algorithms; MongoDB 9.0 promoted the new prefix/suffix/substring types to GA. Never copy 8.2 preview configs straight into 9.0 without reading migration docs; preview **`prefixPreview`/`suffixPreview`/`substringPreview`** using the preview **`text`** algorithm were deprecated/removed in 9.0 per documentation.

### 7.5. Do Not Arbitrarily Combine Multiple `queryType`s

Never assume one field can enable every query mode:

~~~text
salary:
  equality + range + prefix + substring
~~~

In QE, **`queryType` is strictly constrained**. Numeric/Date fields pick equality or range; a range-configured field supports equality through the range engine, but you cannot arbitrarily declare both types simultaneously in the schema.

For String queries, prefix/suffix have specific combination rules and substring has strict exclusions. Changing queryable-field settings typically requires **collection/index migration and rebuild**, not editing a JSON object on a running `MongoClient`.

### 7.6. Supported Does Not Mean Plaintext Performance

A supported range query still processes encrypted query metadata and can incur:

- More metadata entries than equality.
- Higher insert/update and cleanup overhead.
- Latency sensitive to selectivity and range tuning.
- Storage growth driven by `sparsity`/`trimFactor`/`precision`.

Substring support likewise does not deliver the same performance/cost profile as a standard text index on unencrypted data.

## 8. Query Capability Matrix on Encrypted Fields

This table summarizes **plaintext-equivalent capabilities**; always verify exact version/driver, `queryType`, and BSON type limits.

| Query Operation | Deterministic CSFLE | Randomized CSFLE | QE Equality | QE Range | QE String Query |
|---|---|---|---|---|---|
| Filter by unencrypted `_id`/`tenantId` | Yes | Yes | Yes | Yes | Yes |
| Read field and decrypt with key | Yes | Yes | Yes | Yes | Yes |
| `$exists` on encrypted field | Yes per rules | Yes per rules | Yes per rules | Yes per rules | Depends on rules |
| `$eq` literal plaintext | Conditionally yes | No | Yes | Yes via range semantics | Depends on string operator |
| `$in` / `$nin` literal | Conditionally yes | No | Yes | Yes within supported scope | Depends on support |
| `$gt` / `$gte` / `$lt` / `$lte` | Not on plaintext | No | No | Yes | Not as numeric range |
| Arbitrary regex | No | No | No | No | No; use dedicated QE string ops |
| Prefix/suffix/substring | No | No | No | No | Yes with matching `queryType` and version |
| `$sort` on encrypted plaintext | No | No | No | Not directly permitted | Not directly permitted |
| `$sum`/`$avg` on encrypted numbers | No | No | No | Not directly permitted | Not applicable |
| Exact uniqueness via `unique(ciphertext)` | Evaluate limits and leakage | Does not guarantee plaintext | Not guaranteed | Not guaranteed | Not guaranteed |
| Full-text / Atlas Search on plaintext | Not directly | Not directly | Not directly | Not directly | Only defined string query features, not general search |

**How to read this:** “Yes” does not mean every syntactic variant works—for example, comparisons with **`null`**, **arrays**, or another encrypted field may be rejected even when the operator is listed. “No” means the operation cannot run **with plaintext semantics on the server**; it does not stop an authorized app from reading/decrypting a small bounded set and computing client-side when security and latency allow.

## 9. Standard Indexes Change Meaning When Fields Are Encrypted

On unencrypted documents:

~~~javascript
db.customers.createIndex({ email: 1 });
~~~

a B-tree index lets MongoDB locate **plaintext email values**. When encrypted, the server only sees ciphertext. Any index created on ciphertext (where permitted) organizes **ciphertext bytes**, without enabling arbitrary plaintext email operations.

### 9.1. Deterministic CSFLE and Equality Indexes

With consistent deterministic encryption using the same key and scheme, a standard index on the ciphertext field can support **exact equality lookups** under matching server/driver conditions:

~~~javascript
// Consider only when the field uses deterministic CSFLE.
db.customers.createIndex({
  "identity.taxId": 1
});
~~~

When queried through a properly configured automatic CSFLE driver:

~~~javascript
await encryptedCollection.findOne({
  "identity.taxId": "TAX-000123"
});
~~~

the server locates the matching driver-generated ciphertext. However:

- It does not make **range** queries valid.
- It does not make **regex/collation** queries valid.
- It does not hide duplicate ciphertexts across documents.
- It does not make queries under a different encryption key match.
- You must verify MongoDB's index/field type rules.

Do not index deterministic low-cardinality fields if your threat model forbids frequency leakage.

### 9.2. Randomized CSFLE and Indexes

Because identical plaintexts yield distinct ciphertexts:

~~~text
plaintext email: user@example.com
   -> Ciphertext 1
   -> Ciphertext 2
   -> Ciphertext 3
~~~

a standard B-tree index on a randomized ciphertext field **cannot perform plaintext equality lookups**.

Even if `createIndex` succeeds, “having an index” provides no way to reproduce each document's unique ciphertext at query time.

### 9.3. QE: Never Create a B-Tree Index on an Encrypted Field for Speed

MongoDB documentation warns **against creating indexes directly on QE encrypted fields** for queries; it degrades performance, as Queryable Encryption uses dedicated metadata/query indexes.

Avoid:

~~~javascript
// Not a recommended index strategy for a QE field.
db.secureRecords.createIndex({
  "identity.taxId": 1
});
~~~

Instead, in supported MongoDB workflows:

- Create the QE collection with the right **`encryptedFields` schema**.
- Let the server/driver manage encrypted query metadata.
- Where recommended by documentation, an index on **`__safeContent__`** supports query execution—never create a B-tree index pretending the field is plaintext.

Example index pattern mentioned in documentation:

~~~javascript
// Follow only per QE and exact server version documentation.
db.secureRecords.createIndex({
  __safeContent__: 1
});
~~~

**`__safeContent__`** is an internal Queryable Encryption mechanism, not a business field for apps to read, write, or alter. Never treat that index as a substitute for declaring **`queries`/`queryType`**.

### 9.4. Indexing Unencrypted Metadata

A design can index:

~~~javascript
db.secureRecords.createIndex({
  tenantId: 1,
  createdAt: -1
});
~~~

when `tenantId`/`createdAt` are allowed unencrypted. This index supports:

~~~javascript
db.secureRecords.find({
  tenantId: "TENANT-A",
  createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
}).sort({ createdAt: -1 });
~~~

This queries and indexes **plaintext metadata**, not encrypted salary, taxId, or confidential notes. Queries on QE collections must still obey driver/version command limits.

### 9.5. Indexing Auxiliary Search Tokens

Some systems store a separate **search token** for lookups, e.g.:

~~~javascript
{
  tenantId: "TENANT-A",
  opaqueLookupToken: BinData(/* designed lookup token */),
  secretValue: BinData(/* encrypted field */)
}
~~~

If used, tokens must rely on keyed cryptography (such as **HMAC**) or a reviewed secure design; **never use plain SHA-256 of guessable values claiming it is secure**.

Risks:

- Frequency leakage.
- Dictionary/brute-force attacks on small domains.
- Token collisions or normalization mismatches.
- Key lifecycle, rotation, and cross-tenant scoping.
- Inference via metadata/index/query patterns.

A shadow/blind index is an **additional cryptographic design**, not a trivial, universally better replacement for QE.

## 10. Unique Indexes: You Cannot Infer Plaintext Uniqueness

On a plaintext field:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
);
~~~

MongoDB enforces uniqueness on stored field/index keys.

When `email` uses **randomized encryption** or **Queryable Encryption**:

~~~text
user@example.com -> Ciphertext A
user@example.com -> Ciphertext B
~~~

the server sees A and B as distinct values. A unique index on ciphertext **cannot enforce the business rule “one email belongs to one account”**.

### 10.1. QE Always Requires Business-Layer Uniqueness Design

MongoDB docs explicitly state unique indexes containing encrypted fields in QE **do not enforce plaintext uniqueness**. Never create:

~~~javascript
// Do not rely on this to enforce plaintext email uniqueness in QE.
db.customers.createIndex(
  { tenantId: 1, encryptedEmail: 1 },
  { unique: true }
);
~~~

assuming the business constraint is enforced.

### 10.2. Deterministic CSFLE Compares Ciphertexts, Not Universal Scenarios

Deterministic encryption with the **same key, type, normalization, and algorithm** produces repeatable ciphertexts for equal plaintexts, enabling ciphertext equality/uniqueness in narrow designs.

Yet you must evaluate:

- Are multiple keys or key versions in use?
- Can normalization or BSON types drift?
- Can any client write outside the encryption schema?
- How do sharding and cross-shard unique index rules interact?
- Is frequency leakage acceptable?
- Is normalized uniqueness required across a tenant?

Never claim a deterministic ciphertext unique index **always** preserves identity invariants across all topologies and migrations.

### 10.3. Separating Uniqueness Keys from Confidential Fields

One pattern uses a **non-secret business reference**:

~~~javascript
{
  _id: "CUSTOMER-1001",
  tenantId: "TENANT-A",
  externalCustomerRef: "CREF-1001",
  encryptedEmail: BinData(/* QE */)
}
~~~

A unique index works cleanly on `externalCustomerRef` within the target scope if the rule is “unique customer reference”.

If the actual rule is **unique plaintext email**, `externalCustomerRef` **cannot substitute** for it. You need an atomic, properly authorized registry/dedup design or a reviewed cryptographic lookup key—never an unprotected “query-then-insert”.

### 10.4. Check-Before-Insert Races

Scenario:

~~~text
Request A: find(email) -> not found
Request B: find(email) -> not found
Request A: insert(email)
Request B: insert(email)
~~~

Without an atomic uniqueness primitive, both A and B succeed.

Encryption does not eliminate race conditions; **uniqueness** and **confidentiality** must be solved together by design.

## 11. Sharding and Encrypted Fields

Shard keys let `mongos` route reads and writes based on key values. When a field is encrypted, ciphertexts cannot inherently preserve properties needed by shard keys and query routers.

### 11.1. Never Use a QE Encrypted Field as a Shard Key

In Queryable Encryption, shard keys **cannot be encrypted fields**. QE internal metadata collections also have restrictions preventing arbitrary sharding.

Inappropriate example:

~~~javascript
// Never use a QE-encrypted taxId as a shard key.
sh.shardCollection(
  "secure_db.customers",
  { "identity.taxId": 1 }
);
~~~

Instead, pick a shard key from policy-approved unencrypted fields with good cardinality and query alignment, such as `tenantId` or an opaque tenant routing key.

### 11.2. CSFLE Encrypted Shard Keys Also Carry Hazards

For CSFLE, MongoDB warns that using encrypted fields in shard keys or encrypting an existing shard key can cause **incorrect or unpredictable sharding behavior**. Never assume deterministic ciphertext solves all shard-routing rules.

Keep shard keys **unencrypted**, deliberately chosen, and free of sensitive data exposure.

### 11.3. Illustrative Design

~~~javascript
{
  tenantId: "TENANT-A",            // Permitted routing metadata
  recordId: "REC-1001",           // Non-sensitive ID
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  identity: {
    taxId: BinData(/* QE encrypted */)
  },
  salary: BinData(/* QE encrypted */)
}
~~~

Candidate shard key:

~~~javascript
{ tenantId: 1, recordId: 1 }
~~~

Evaluate cardinality, hotspots, query targeting, unique indexes, and privacy. Never turn a secret identifier into a plaintext shard key just for throughput.

### 11.4. QE Topology and Transactions

Queryable Encryption supports **replica sets and sharded clusters** under deployment rules; **standalone** deployments are generally unsupported for full QE. Secondary reads and transactions on sharded clusters carry extra constraints; earlier docs noted transactions on sharded QE required `readConcern: "snapshot"`.

Always check your version's compatibility matrix: never assume “MongoDB supports transactions” means every combination of **QE + sharding + read preference + transaction** works identically to plaintext collections.

## 12. Sorting on Encrypted Fields

Example employee list:

~~~javascript
db.employees.find({
  tenantId: "TENANT-A"
}).sort({
  salary: -1
});
~~~

If `salary` uses QE range encryption, you can **filter by range** per the supported `queryType`. That **does not mean** MongoDB can or is permitted to sort results by plaintext salary.

Finding “`salary` in `[50000, 100000)`” and returning “`salary` descending” are **two different problems**.

### 12.1. Sorting Ciphertext Is Not Sorting Plaintext

Never treat byte ordering of encrypted `BinData` as ordering of salaries, scores, or dates.

~~~text
Plaintext salary:  30000, 50000, 90000
Ciphertext order:  no reliable ordering relation to original numbers
~~~

### 12.2. Sorting by Unencrypted Metadata

If policy permits:

~~~javascript
db.employees.find({
  tenantId: "TENANT-A"
}).sort({
  createdAt: -1
}).limit(20);
~~~

In QE, sorting on unencrypted fields can appear in supported aggregation stages or normal queries, yet **exact driver and pipeline requirements** must still be checked. Never infer that an encrypted `salary` can be sorted just because `$sort` is listed.

### 12.3. Sorting After Client-Side Decryption

Another option:

1. Filter candidates by tenant, status, and authorization.
2. Read a **strictly bounded** result set.
3. Decrypt values in the authorized client.
4. Sort locally by salary.

Risks:

- Must read larger result sets.
- Only produces a **globally accurate** sort if all candidates were fetched; sorting one page to return top-10 is inaccurate across the whole corpus.
- Exposes plaintext in app memory/logs if poorly handled.
- Does not scale to millions of documents.

Never treat client-side sorting as a way to “restore every MongoDB feature” at the expense of SLAs and security.

## 13. Aggregations and Computations on Encrypted Fields

Unencrypted Number/String/Date fields work with standard aggregation operators. When encrypted client-side, MongoDB sees ciphertext and **does not decrypt values to compute aggregates**.

### 13.1. Do Not Sum or Average Encrypted Salaries

~~~javascript
// Not a valid plaintext salary calculation in CSFLE/QE:
db.employees.aggregate([
  {
    $group: {
      _id: "$departmentId",
      avgSalary: { $avg: "$salary" },
      totalSalary: { $sum: "$salary" }
    }
  }
]);
~~~

When `salary` is encrypted, the server lacks plaintext Numbers for `$avg`/`$sum`. Some pipelines/drivers error out; under explicit encryption, operating on `BinData` can yield unexpected results. **Never treat the absence of an error as proof of a valid calculation.**

Alternatives:

- Compute on an **authorized client** over a bounded decrypted set.
- Maintain **non-sensitive or policy-approved aggregate tables**.
- Use reviewed specialized secure computation/cryptographic tools if large-scale privacy-preserving analytics are truly needed.

Never add a plaintext `salaryTotal` field to the same document if policy forbids exposing that value.

### 13.2. $group on Encrypted Fields

Deterministic CSFLE can support some cases of **`$group` on a deterministically encrypted field**, subject to stage/expression limits and frequency leakage. This **does not mean** accumulators operate on plaintext.

Distinction:

~~~text
Group deterministically encrypted salary:
  Can group identical ciphertexts under supported configurations.

Average deterministically encrypted salary:
  Cannot compute plaintext averages from BinData alone.
~~~

For QE, automatic encryption docs list **`$group` on unencrypted fields** as supported, not arbitrary grouping on encrypted fields.

### 13.3. $project Can Return Fields, Not Perform Arbitrary Math

A pipeline projecting fields for the driver to decrypt can be supported:

~~~javascript
db.employees.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      employeeCode: 1,
      departmentId: 1,
      salary: 1
    }
  }
]);
~~~

Whereas:

~~~javascript
{
  $project: {
    salaryAfterRaise: { $multiply: ["$salary", 1.05] }
  }
}
~~~

cannot compute on plaintext salary when the server only holds ciphertext.

### 13.4. Supported Stages Do Not Mean All Expressions Are Supported

MongoDB's QE automatic encryption docs list supported stages such as:

- **`$match`**, **`$project`**, **`$addFields`** within defined scopes.
- **`$sort`**, **`$limit`**, **`$skip`** with permitted fields and syntax.
- **`$group`** on unencrypted fields.
- **`$lookup`/`$graphLookup`** with dedicated restrictions.

Inside every stage, expressions touching encrypted fields must still be on the **allowlist**.

A pipeline using a valid `$project` stage will still fail if it applies **`$toLower`** or **`$concat`** to an encrypted String. Never assume all aggregation expressions are allowed.

### 13.5. $lookup and Join Keys

Typical example:

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerRef",
      foreignField: "customerRef",
      as: "customer"
    }
  }
]);
~~~

If **`customerRef`** is encrypted, never assume the join compares plaintext properly. In QE automatic encryption versions, docs restrict using **encrypted fields as `localField`/`foreignField`** and impose special rules on multiple encrypted collections, encrypted arrays, and subpipelines.

**Simpler alternative:** use a **non-sensitive opaque `customerRef`** for joins while encrypting sensitive fields such as `nationalId`, `email`, or `salary` separately.

### 13.6. $out and $merge

Queryable Encryption automatic encryption does not freely support aggregation stages **writing to another collection**, such as **`$out`** and **`$merge`**. Never run a pipeline from an encrypted collection assuming `$merge` re-encrypts each field properly in the destination collection.

For ETL or data movement:

1. Define decryption permission boundaries.
2. Select target collections and matching encryption schemas.
3. Write through an appropriately configured encryption client/migration tool.
4. Verify no unapproved window stores plaintext.

### 13.7. $text, Regex, MongoDB Search, and Vector Search

Avoid:

~~~javascript
// Does not search plaintext of encrypted Strings:
db.customers.find({
  $text: { $search: "Nguyen" }
});
~~~

QE **is incompatible with MongoDB Atlas Search** over encrypted fields per documented limits; CSFLE likewise provides no full-text or n-gram search on ciphertext.

Under automatic encryption clients, **`$text`** may be rejected by the driver even when targeting another field, depending on the supported operators set.

**Vector Search** must also not be treated as semantic search directly over client-encrypted fields. Vector embeddings and search indexes are separate pipelines; generating embeddings from plaintext and storing them searchable can leak sensitive information and must be evaluated as sensitive derived data.

### 13.8. Why You Must Test Against the Right Collection and Client

An aggregation that runs on a plaintext collection may be restricted or rejected when run **through a `MongoClient` with automatic encryption enabled**, because the encryption library enforces supported stages and commands.

Never use results from an unencrypted debug client to claim the QE production service will behave identically.

## 14. Updates, Replacements, and Upserts with Encrypted Fields

Field encryption affects not only queries, but updates too.

### 14.1. $set and $unset

Queryable Encryption automatic encryption supports update operators such as:

- **`$set`**
- **`$unset`**

on encrypted fields under valid conditions. Logical example:

~~~javascript
// QE-configured client; salary is defined as encrypted.
await encryptedCollection.updateOne(
  {
    tenantId: "TENANT-A",
    recordId: "REC-1001"
  },
  {
    $set: {
      salary: 85000
    }
  }
);
~~~

The driver encrypts the new `salary` per schema; the server never receives plaintext for that field in the QE flow.

### 14.2. Never Use $inc on Encrypted Salary

~~~javascript
// Does not increment plaintext encrypted salary:
await encryptedCollection.updateOne(
  { recordId: "REC-1001" },
  { $inc: { salary: 5000 } }
);
~~~

**`$inc`** requires the server to read an existing number and add to it. With `BinData` ciphertext, the server has no plaintext number. Alternative:

1. Read the document through an authorized decrypting client.
2. Verify authorization and business rules.
3. Compute the new salary in the application.
4. Write back using **`$set`** via the encrypted client.
5. Enforce **concurrency control** to prevent lost updates.

Never run unversioned read-modify-write under high concurrency.

### 14.3. Optimistic Concurrency Example

~~~javascript
// Assumes the record was read and decrypted earlier.
const originalVersion = 7;
const updatedSalary = 85000;

const result = await encryptedCollection.updateOne(
  {
    tenantId: "TENANT-A",
    recordId: "REC-1001",
    version: originalVersion
  },
  {
    $set: {
      salary: updatedSalary,
      version: originalVersion + 1
    }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Version conflict: reload and retry");
}
~~~

In this design, **`version` is unencrypted metadata** permitted by the threat model. The server checks `version` atomically during `updateOne`. The app must retry safely without applying raises twice; never treat this snippet as an entire payroll transaction.

### 14.4. Do Not Run Arbitrary updateMany in QE

Queryable Encryption restricts **multi-document updates/deletes**. MongoDB documentation notes operations such as **`updateMany`** and bulk writes with multiple update/delete statements are unsupported under documented QE rules.

Avoid:

~~~javascript
// Do not use as a production QE migration:
await encryptedCollection.updateMany(
  { tenantId: "TENANT-A" },
  { $set: { salary: 90000 } }
);
~~~

Instead, use a **controlled migration worker**: iterate via a supported client, update individual documents under valid conditions, checkpoint, handle retries/idempotency, and monitor write amplification.

### 14.5. Upsert with an Encrypted Filter

A common pitfall: in QE upserts, encrypted fields inside the **query filter** may **not automatically populate into the newly inserted document** as some expect.

Example:

~~~javascript
// Risk of assuming encrypted filter field is auto-copied into inserted doc.
await encryptedCollection.updateOne(
  {
    "identity.taxId": "TAX-000123"
  },
  {
    $set: { status: "ACTIVE" }
  },
  { upsert: true }
);
~~~

Never assume the created document contains **`identity.taxId`** matching the schema. Explicitly supply inserted fields, test upsert behavior on your version, and never treat upsert as a uniqueness substitute when schemas/indexes do not enforce it.

### 14.6. Replacement Updates

Replacement-style updates are supported under specific conditions. Ensure:

- The driver holds a compatible encryption config.
- The replacement includes all schema-required fields.
- `tenantId`, shard keys, and retained fields are not dropped.
- Unencrypted clients cannot accidentally overwrite with plaintext.

`replaceOne` replaces the entire business document, so be extra cautious against dropping fields or breaking encryption metadata.

### 14.7. $rename Operations

In CSFLE, some **`$rename`** cases work if source and target carry matching encryption metadata. In QE, encrypted field names are bound to the schema and cannot be freely renamed.

Never write:

~~~javascript
// Do not use arbitrarily on a QE encrypted field:
db.secureRecords.updateOne(
  { recordId: "REC-1001" },
  { $rename: { "identity.taxId": "taxReference" } }
);
~~~

expecting encrypted query configs to translate automatically. Moving an encrypted field typically requires a **decrypt/re-encrypt schema migration**.

## 15. Nulls, Missing Fields, and Restricted BSON Types

Once encrypted, do not assume **`null`** behaves as it does on plaintext fields.

### 15.1. Null Is Not the Same as an Omitted Field

In regular collections:

~~~javascript
{ name: null }
{ /* no name field */ }
~~~

Running:

~~~javascript
db.people.find({ name: null });
~~~

has specific MongoDB behavior matching both `null` and missing fields. However, in automatic CSFLE/QE, supported-operator docs state **comparing an encrypted field to `null`** may be rejected even when `$eq` is supported for other values.

Avoid:

~~~javascript
// Do not treat this as a valid encrypted null comparison.
await encryptedCollection.find({
  secretField: { $eq: null }
}).toArray();
~~~

### 15.2. Optional Field Pattern

One clean pattern:

~~~javascript
{
  tenantId: "TENANT-A",
  recordId: "REC-1001",
  hasMedicalNote: true,     // permitted metadata if policy allows
  medicalNote: BinData(/* encrypted */)
}
~~~

For a record without `medicalNote`:

~~~javascript
{
  tenantId: "TENANT-A",
  recordId: "REC-1002",
  hasMedicalNote: false
}
~~~

The app uses **`$exists`** or an approved boolean metadata flag to query presence rather than forcing `null` encryption.

**Trade-off:** `hasMedicalNote` reveals that a note exists. That itself can be sensitive, so verify whether exposing field presence is permitted.

### 15.3. QE BSON Types by `queryType`

MongoDB QE documentation restricts valid BSON types per `queryType`:

| Query Type | Typical Data Types |
|---|---|
| `equality` | Most BSON scalar types, excluding restricted types like arrays, objects, and double/decimal with equality indexes |
| `range` | **`date`, `int`, `long`, `double`, `decimal`** per version |
| `prefix`/`suffix`/`substring` | **`string`** per applicable feature |
| `none` | Can support additional types like arrays/objects without querying inside them |

A **`double`/`decimal`** field needing equality comparison may require a **`range` index** per QE docs rather than an equality `queryType` like String.

Never swap **`bsonType: "int"`** for **`"long"`** or **`"double"`** across clients when schemas/indexes expect one exact type.

### 15.4. BSON Values That Cannot Be Freely Encrypted

Values like **`MinKey`, `MaxKey`, `null`, `undefined`** carry restrictions because encryption does not conceal type tags fully; QE often forbids encrypting them.

Avoid storing:

~~~javascript
{
  salary: undefined,
  encryptedString: null
}
~~~

expecting automatic encryption clients to encrypt everything cleanly.

For required fields, validate **before calling the encrypted client**; for optional fields, enforce explicit **omission**.

### 15.5. Integers vs. Floating-Point

A value like:

~~~javascript
salary: 50000
~~~

can serialize into different BSON numeric types depending on driver and builder. If the QE schema declares **`bsonType: "int"`**, never let another code path write a **`double`** into that field.

In Java, distinguish **`Integer`, `Long`, `Double`, `Decimal128`**; in JavaScript/Python watch serializers and use **`Int32`/`Long`** wrappers where needed. Match types to domain bounds and enforce consistency across ingestion and queries.

### 15.6. $in vs. Encrypted Array Values

Two distinct cases:

~~~javascript
// Query a scalar encrypted field against a list of scalar values.
{ "identity.taxId": { $in: ["TAX-1", "TAX-2"] } }
~~~

versus:

~~~javascript
// Encrypted field holding an array itself.
{ tags: ["A", "B"] }
~~~

The first works under supported `queryType`s/drivers. The second faces strict limits: an **encrypted array** does not support `$elemMatch`, `$all`, or element-level queries as plaintext arrays do.

## 16. Arrays, Objects, and Nested Fields

### 16.1. Deterministic CSFLE Cannot Arbitrarily Encrypt Whole Objects/Arrays

Example:

~~~javascript
{
  address: {
    line1: "A Street",
    city: "HCM",
    postalCode: "700000"
  },
  phones: ["+84-...", "+84-..."]
}
~~~

Deterministic CSFLE restricts encrypting **whole objects or arrays**; CSFLE docs state whole-object/array encryption is supported only with randomized encryption in that mode.

If you need queries on `postalCode`, encrypt the **scalar `postalCode`** deterministically or via QE as required, verifying supported paths and schemas. Never assume MongoDB can still query `address.postalCode` once the entire `address` object is randomized-encrypted.

### 16.2. Nested Fields Inside Arrays of Documents

Example:

~~~javascript
{
  contacts: [
    { type: "HOME", phone: "+84-..." },
    { type: "WORK", phone: "+84-..." }
  ]
}
~~~

Automatic CSFLE restricts encrypting fields **inside arrays of documents**. Queryable Encryption also restricts encrypted fields inside arrays; encrypting the whole array with `queryType: none` **does not allow querying elements inside**.

If equality lookups by phone number are needed, consider:

- Extracting a separate **`contacts`** collection where each contact is a document with an encryptable/queryable scalar field.
- Using an auxiliary lookup field matching your threat model.
- Adjusting query requirements if phones only display after looking up `userId`.

### 16.3. No “Magic” Multikey Index for Encrypted Arrays

Multikey indexes power array queries on plaintext MongoDB. On an encrypted array, the server sees only a single ciphertext payload—there are no plaintext elements to index individually.

Never assume creating an index on **`contacts.phone`** makes elements inside a randomized-encrypted `contacts` array searchable.

### 16.4. Document Design Driven by Query Needs

Two models:

~~~text
Model A
  userId = plaintext opaque ID
  contacts = randomized encrypted array
  Query: fetch by userId only, then decrypt all contacts

Model B
  userId = plaintext opaque ID
  separate contact documents
  encryptedPhone = QE equality
  Query: look up phone in contact collection
~~~

Model A excels when `contacts` are always opened after `userId` is known. Model B fits phone-lookup requirements at the cost of more documents, encrypted index overhead, and synchronization. Neither model wins every workload.

## 17. Collations, Case-Insensitivity, and Normalization

Plaintext String fields can use collations or regexes for case- or accent-insensitive comparisons.

Once encrypted:

- **Deterministic CSFLE** encrypts the exact canonical bytes supplied; MongoDB collations do not operate on plaintext.
- **QE** offers case/diacritic sensitivity parameters for String queries in supported versions, which still differs from full arbitrary MongoDB collations on plaintext.

### 17.1. Email Example

~~~text
Alice@example.com
alice@example.com
ALICE@EXAMPLE.COM
~~~

Never assume these three strings represent either the same account or distinct accounts without checking. Canonicalization rules belong to system business standards.

With deterministic CSFLE equality and canonical search, the application must produce the **exact same canonical form before encrypting both stored documents and queries**.

### 17.2. Never Expect Collations to Interpret Ciphertext

~~~javascript
db.customers.find({
  encryptedName: "Nguyen"
}).collation({
  locale: "vi",
  strength: 2
});
~~~

The server will not decrypt `encryptedName` to compare it under the collation. CSFLE/QE docs warn collations do not behave as expected on ciphertext.

### 17.3. QE Case/Diacritic Query Types

Newer QE String modes allow configuring case and diacritic sensitivity. Conceptual example:

~~~text
queryType: prefix
caseSensitive: false
diacriticSensitive: false
~~~

This is an **encrypted query schema choice** locked in up front, not something toggled per `find()` call.

Fully understand String query costs and limits (token lengths, text normalization, version constraints) before enabling.

## 18. Incompatible Features or Separate Handling

Certain MongoDB features cannot be freely combined with client-encrypted fields or QE collections:

| Feature | Consideration |
|---|---|
| MongoDB Search / Atlas Search | Cannot full-text search plaintext hidden in ciphertext; QE compatibility limits apply |
| Vector Search | Cannot read semantics inside encrypted fields; derived embeddings carry their own exposure risk |
| Time series collections | Field-level encryption/QE have incompatibilities with time series collections |
| Capped collections | QE has restrictions on capped collections |
| Views | Queries via views touching encrypted fields can fail or return wrong results |
| Change streams | Restrictions on database/cluster watch scope and decryption; payloads are not automatically plaintext |
| TTL indexes | QE collections restrict TTL indexes per version documentation |
| Unique indexes | Never guarantee plaintext uniqueness for randomized/QE encrypted fields |
| Sharded collections | Can support QE topology, but shard keys cannot be encrypted fields |
| `$lookup`, `$graphLookup` | Joins on encrypted fields face strict limitations |
| Transactions | Extra constraints on topology, read concern, drivers, and operations |
| Schema validation | Never arbitrarily inject `encrypt` keywords or disable validation in QE; follow `encryptedFields` schema |
| Aggregation `$merge`/`$out` | Unsupported under automatic QE as arbitrary plaintext pipelines |

This is a **directional reference**, not an absolute ban on every feature in every version. Unencrypted fields inside a QE collection can also behave differently from encrypted fields; always check the compatibility and supported-operations matrices.

### 18.1. Time Series + CSFLE

MongoDB time series collections carry documented restrictions, including **lack of support for Client-Side Field Level Encryption** under the described model.

If sensor readings hold secret attributes, consider:

- Storing sensitive attributes encrypted in a **separate standard collection**.
- Storing less sensitive time series metrics in the time series collection where policy allows.
- Maintaining a separate registry mapping opaque `sensorId`s to real identities.

Never assume CSFLE can simply be bolted onto an existing time series collection via a driver option.

### 18.2. QE Collections: Creation, Migration, and Renaming

In many QE versions, collections **must be created with `encryptedFields` from inception**. There is no “flip encryption on an existing collection” switch that automatically encrypts old documents and rebuilds indexes.

Additional constraints include:

- Cannot arbitrarily rename encrypted collections.
- Cannot change a field's `queryType` once defined.
- Cannot convert a CSFLE collection to QE with a single `collMod`.
- Specific rules govern `$jsonSchema`, `validationAction`, and `validationLevel`.
- Metadata collections must be created and managed via supported workflows.

Thus encryption schema changes are **architectural decisions requiring migrations**, not minor connection-string tweaks.

### 18.3. QE on Older Versions

Older clusters may lack:

- QE range GA.
- QE String prefix/suffix/substring GA.
- Newer `precision`/`trimFactor`/`sparsity` options.
- Certain `$lookup` behaviors across multiple encrypted collections.

Never build a product around a feature in current docs if your running server lacks that version.

### 18.4. Automatic vs. Explicit Encryption

**Automatic encryption**:

~~~text
App sends plaintext literal via configured driver
              |
              v
Driver checks encryption schema and supported operations
              |
              v
Encrypt query/write payload and send to server
~~~

**Explicit encryption**:

~~~text
App manually calls encrypt()/decrypt()
              |
              v
App manages encrypted values and query payload
              |
              v
Server sees ciphertext, may operate as BinData
~~~

Explicit encryption does not make unsupported operators valid. It also increases the risk of **queries running silently with wrong semantics** if the app forgets the server compares ciphertext rather than plaintext.

## 19. Designing a Secure Schema for a Real Workload

Suppose an HR system needs to:

- Look up employees by **`employeeCode`**.
- Filter by **`tenantId`**, **`departmentId`**, **`employmentStatus`**, and **`createdAt`** ranges.
- Look up exact **`taxId`** when authorized.
- Filter employees with `salary` in a numeric range, **without needing server-side salary sorting or averaging**.
- Read **`medicalNote`** only after locating an employee via other metadata.

A candidate document design:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "TENANT-A",
  employeeCode: "E-1001",
  departmentId: "FINANCE",
  employmentStatus: "ACTIVE",
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  identity: {
    taxId: BinData(/* QE equality */)
  },
  salary: BinData(/* QE range */),
  medicalNote: BinData(/* encrypted, queryType none */)
}
~~~

### 19.1. Field and Purpose Map

| Field | Planned Handling | Supported Queries | Notes |
|---|---|---|---|
| `_id` | Unencrypted per QE schema | Exact record lookup | Never use `_id` as a QE encrypted field |
| `tenantId` | Permitted opaque metadata | Tenant filter | Enforce authorization independently |
| `employeeCode` | Opaque public business ID | Exact + scoped unique | Never embed secret IDs |
| `departmentId` | Plaintext per threat model | Equality/group | Can reveal department |
| `employmentStatus` | Plaintext per threat model | Equality | Can reveal employment state |
| `createdAt` | Plaintext per threat model | Range/sort | Can reveal hiring activity |
| `identity.taxId` | QE equality | Exact lookup | Never use as shard key |
| `salary` | QE range | Numerical range | Cannot sort/sum/avg directly |
| `medicalNote` | QE `none` or randomized CSFLE | No content search | Decrypt only after reading right record |

This is an **illustrative design**. If organizational policy forbids exposing `departmentId` or `employmentStatus`, encrypt or isolate those fields and accept the corresponding query constraints.

### 19.2. Indexes for Unencrypted Metadata

For fields permitted in plaintext:

~~~javascript
db.employees.createIndex({
  tenantId: 1,
  employeeCode: 1
});

db.employees.createIndex({
  tenantId: 1,
  departmentId: 1,
  createdAt: -1
});
~~~

These indexes serve **metadata routing/filtering/sorting** without decrypting `salary` on the server.

With Queryable Encryption, indexes for encrypted fields are managed by the **`encryptedFields` schema/metadata mechanism**; never add B-tree indexes on `salary`/`taxId` trying to run plaintext queries.

### 19.3. Query Pattern by Public ID

~~~javascript
const employee = await encryptedCollection.findOne({
  tenantId: authenticatedTenantId,
  employeeCode: "E-1001"
});
~~~

Through an authorized encryption client, **`salary`/`taxId`/`medicalNote`** in the result are decrypted for the application.

Yet just because the driver can decrypt them **does not mean every end user may see all three fields**. The application layer must enforce authorization and return role-scoped **projection/response DTOs**.

### 19.4. Querying `taxId` Equality

~~~javascript
const employee = await encryptedCollection.findOne({
  tenantId: authenticatedTenantId,
  "identity.taxId": "TAX-000123"
});
~~~

Prerequisites:

- `taxId` configured with **QE equality**.
- Client holds matching `encryptedFields` schema, keys, and support library.
- Query value matches exact BSON type (String).
- `tenantId` comes from verified authentication, never trusted client input.

### 19.5. Querying `salary` Range

~~~javascript
const employees = await encryptedCollection.find({
  tenantId: authenticatedTenantId,
  salary: {
    $gte: 60000,
    $lt: 100000
  }
}).toArray();
~~~

Prerequisites:

- `salary` encrypted with **QE range**.
- Schema range `min`/`max`, numeric BSON type, and options align.
- Driver and cluster support the corresponding range query.

Never tack on `.sort({ salary: -1 })` or `$avg: "$salary"` assuming it remains valid.

### 19.6. Scale-Bounded Client-Side Aggregation

With only 20 employees in a department and policy approval, the app can:

1. Filter `tenantId` + `departmentId` server-side.
2. Read the 20 records decrypted by the driver.
3. Compute aggregates inside the authorized app.
4. Return controlled aggregate results.

With **20 million employees**, reading everything client-side fails on memory, network, latency, and plaintext exposure. Re-evaluate the threat model or build an **approved aggregate store** with clear disclosure policies.

### 19.7. Never Turn Metadata into a Secret-Leakage Channel

A broken design adds:

~~~javascript
{
  salaryEncrypted: BinData(/* ... */),
  salaryPlaintextForSorting: 85000
}
~~~

`salaryEncrypted` protects nothing if anyone reading the server sees `salaryPlaintextForSorting`.

Derived fields like **`salaryBand`**, **`hasMedicalNote`**, or **`ageBucket`** also leak information. Assess **inference risk** from every derived field instead of assuming “it's not exact salary so it's harmless”.

## 20. Declaring an `encryptedFields` Schema for Queryable Encryption

To enable QE, the collection needs an **`encryptedFields` schema** specifying fields and query types—never just an `isEncrypted` boolean flag on documents.

### 20.1. Illustrative Schema Example

Fragment (omitting full KMS and `ClientEncryption` setup):

~~~javascript
const encryptedFields = {
  fields: [
    {
      path: "identity.taxId",
      bsonType: "string",
      queries: { queryType: "equality" }
    },
    {
      path: "salary",
      bsonType: "int",
      queries: {
        queryType: "range",
        min: 0,
        max: 1000000
      }
    },
    {
      path: "medicalNote",
      bsonType: "string"
    }
  ]
};
~~~

Depending on version and API:

- Specifying **`keyId`** per field may be optional or required.
- Some helpers auto-create **data encryption keys (DEKs)** if `keyId` is omitted.
- Range options impose rules on **`sparsity`, `trimFactor`, `precision`, `min`, and `max`**.
- Internal metadata fields and collections are provisioned via the QE setup workflow.

**Never run this fragment alone as a full collection-creation script** expecting encryption without configuring KMS, driver, key vault, and encryption helpers.

### 20.2. Follow the Right Workflow to Create Encrypted Collections

Workflow:

~~~text
1. Verify MongoDB deployment/edition/version supports QE
2. Configure KMS and key access permissions
3. Create or prepare Key Vault + DEKs
4. Define encryptedFields schema
5. Create encrypted collection using supported helper/API
6. Verify indexes and metadata collections
7. Configure MongoClient with proper autoEncryption/explicit mode
8. Only then insert/find via the driver
~~~

Never manually edit QE metadata collections via CRUD to “clean indexes”, as they are managed by the encrypted query engine.

### 20.3. Never Arbitrarily Apply `encryptedFieldsMap` to Existing Plaintext Collections

Suppose a collection holds:

~~~javascript
{ taxId: "TAX-000123" } // legacy plaintext data
~~~

Then you update client config so new writes encrypt `taxId`. Old documents remain plaintext while new ones store ciphertext. Queries through the encrypted client encrypt literals and **miss legacy records**, producing incomplete results.

Moreover, leaving legacy plaintext violates confidentiality policy.

Proper migration requires:

- Creating a new destination collection with the target schema.
- Reading source records in a protected environment.
- Encrypting and writing every document per procedure.
- Verifying counts, uniqueness, permissions, and values.
- Cutting over traffic safely.
- Handling legacy plaintext data, backups, caches, and exports per policy.

Never treat **swapping config and inserting new rows** as a migration.

### 20.4. `queryType` Cannot Be Changed on Existing Collections

A field starting as:

~~~javascript
{ path: "identity.taxId", queries: { queryType: "equality" } }
~~~

cannot later add prefix search simply by editing `MongoClient` config—old indexes lack the necessary tags. You must plan a **new schema/index and migration**.

### 20.5. QE Metadata and Query Indexing

Queryable Encryption maintains **two auxiliary metadata collections** for encrypted queries, commonly referred to as **ESC** and **ECOC** in technical docs, alongside the business collection.

Every write to a queryable field updates the corresponding **encrypted query metadata**. Range and string searches generate more tags/metadata entries than equality.

This explains why QE introduces noticeable overhead even when encrypting only a few fields.

## 21. Key Vault, Data Encryption Keys, and KMS

Field-encrypted systems rely on at least two key roles:

- **DEK – Data Encryption Key:** encrypts field data.
- **CMK – Customer Master Key** or KMS-managed key: protects/wraps DEKs.

Conceptual model:

~~~text
KMS / HSM / Key Management Service
            |
            v
         Master Key
            |
            v
  Wrap / unwrap Data Encryption Keys
            |
            v
   Key Vault metadata collection
            |
            v
    Authorized MongoDB driver
            |
            v
   Encrypt / decrypt field values
~~~

### 21.1. MongoDB Data Access Differs from Key Access

A user permitted to read a MongoDB collection without KMS/key access sees only **`BinData` ciphertext**.

Conversely, a service holding decryption keys that skips user authorization checks can leak all data through its API. Never equate “has decryption key” with “user is authorized to view fields”.

### 21.2. Never Hardcode Key Material

Never write:

~~~javascript
const localMasterKey = "base64-secret-master-key-in-repository";
~~~

in production source code or shared internal docs.

Lab examples may use a **local KMS provider** per MongoDB guides, while production requires secure remote key management, backups, auditing, and rotation.

### 21.3. Key Rotation Is Not Just Generating a New Key

In client-side encryption, rotation can involve:

- Rewrapping DEKs under a new master key.
- Re-encrypting field data with a new DEK or encryption config for stronger changes.
- Keeping old and new clients working smoothly during transition.
- Preserving decryption of historical records.
- Rebuilding or migrating encrypted indexes/metadata as required.

Depending on rotation type, rewrapping key metadata may **avoid re-encrypting all data**, whereas changing algorithms, `queryType`s, or key IDs requires broader migration. Never use one generic script for every rotation scenario.

### 21.4. Key Availability and System Availability

If KMS is temporarily unreachable, applications may:

- Fail to initialize auto-encryption clients.
- Fail to encrypt new writes.
- Fail to decrypt reads needing uncached keys.
- Return errors or spike latency due to retries.

Define fallbacks **that never downgrade protection**; never write temporary plaintext during a KMS outage. Fields mandated to be encrypted must **fail closed**.

## 22. Java MongoDB Sync Driver: Querying with an Encryption-Configured Client

In Java, business code interacts with **`MongoCollection<Document>`**, while encryption depends on how the **`MongoClient`** was constructed.

A client built with:

~~~java
MongoClient plain = MongoClients.create(uri);
~~~

**does not automatically become a QE/CSFLE encrypted client** just because the server holds ciphertext collections. Automatic encryption requires **`AutoEncryptionSettings`**, **`keyVaultNamespace`**, **`kmsProviders`**, schema maps or encrypted fields maps, supported drivers, and the cryptographic library per official docs.

The examples below deliberately accept a **`MongoCollection` already obtained from a properly configured encrypted client**. They illustrate query shapes and business guards, without assuming KMS/DEKs exist inside a standalone Java method.

### 22.1. Lookup by Encrypted Equality Field

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class SecureTaxIdLookup {
    private final MongoCollection<Document> collection;

    public SecureTaxIdLookup(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public Document findByTaxId(
            String trustedTenantId,
            String taxId) {

        if (trustedTenantId == null || taxId == null) {
            throw new IllegalArgumentException(
                    "tenantId and taxId must be provided");
        }

        return collection.find(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("identity.taxId", taxId)
                )
        ).first();
    }
}
~~~

The QE driver handles this query when **`identity.taxId`** is configured with `queryType: equality` in a supported environment. Deterministic CSFLE follows the same logic when using a CSFLE schema.

If `taxId` uses **randomized CSFLE** or **QE `queryType: none`**, plaintext lookups will not work.

### 22.2. Range Query with QE

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;

public final class EncryptedSalaryRangeQuery {
    private final MongoCollection<Document> collection;

    public EncryptedSalaryRangeQuery(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public List<Document> findBetween(
            String trustedTenantId,
            int minimumInclusive,
            int maximumExclusive) {

        if (minimumInclusive < 0
                || maximumExclusive <= minimumInclusive) {
            throw new IllegalArgumentException(
                    "Invalid salary range");
        }

        Bson filter = Filters.and(
                Filters.eq("tenantId", trustedTenantId),
                Filters.gte("salary", minimumInclusive),
                Filters.lt("salary", maximumExclusive)
        );

        return collection.find(filter)
                .limit(100)
                .into(new ArrayList<>());
    }
}
~~~

To run:

- Server and driver must support **QE range**.
- **`salary`** must declare `queryType: range`.
- BSON numeric types must match the schema (e.g., **`int`**).
- `100` is an **illustrative service response cap**, not a QE-enforced threshold.

Capping response size does not make queries free; still evaluate bulk exposure of sensitive rows and enforce tenant filtering.

### 22.3. Updating an Encrypted Field with $set

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class SecureSalaryUpdater {
    private final MongoCollection<Document> collection;

    public SecureSalaryUpdater(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public boolean setSalary(
            String trustedTenantId,
            String employeeCode,
            int newSalary) {

        if (newSalary < 0) {
            throw new IllegalArgumentException(
                    "Salary must be nonnegative");
        }

        UpdateResult result = collection.updateOne(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("employeeCode", employeeCode)
                ),
                Updates.set("salary", newSalary)
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

For QE field `salary`, the driver encrypts **`newSalary`** before sending the update per schema. Never replace **`Updates.set("salary", value)`** with **`Updates.inc("salary", delta)`** when `salary` is encrypted.

**Warning:** this illustrates the basic update call; real payroll systems need business authorization, auditing, optimistic concurrency, dual approval, and transaction policies.

### 22.4. Querying by Unencrypted Fields

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public final class MetadataEmployeeSearch {
    private final MongoCollection<Document> collection;

    public MetadataEmployeeSearch(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public List<Document> recentlyCreated(
            String tenantId,
            Date from) {

        return collection.find(
                Filters.and(
                        Filters.eq("tenantId", tenantId),
                        Filters.gte("createdAt", from)
                )
        )
                .sort(Sorts.descending("createdAt"))
                .limit(50)
                .into(new ArrayList<>());
    }
}
~~~

Here **`createdAt`** is intentionally unencrypted. MongoDB uses a structured B-tree index on `tenantId`/`createdAt`, and the authorized driver decrypts **returned encrypted fields**.

### 22.5. Never Return Raw Documents to Every User

A driver-decrypted `Document` may contain `salary`, `taxId`, or `medicalNote`. Never serialize the full `Document` into JSON responses if the caller is only allowed to view name and department.

Instead:

~~~text
MongoCollection<Document> returns decrypted data
             |
             v
Service applies field-level authorization
             |
             v
Safe response DTO with approved fields
             |
             v
HTTP response
~~~

The driver's ability to decrypt is a **process capability**, not proof the caller may view those fields.

## 23. Node.js: Boundary Between Encrypted Clients and Queries

In the MongoDB Node.js Driver, QE/CSFLE apps typically construct a **`MongoClient` with `autoEncryption` options** or use **`ClientEncryption`** for explicit encryption.

A Node.js query:

~~~javascript
const collection = encryptedClient
  .db("secure_db")
  .collection("employees");

const employee = await collection.findOne({
  tenantId: authenticatedTenantId,
  "identity.taxId": "TAX-000123"
});
~~~

performs encrypted equality only if:

- **`encryptedClient`** is a properly configured QE/CSFLE `MongoClient`.
- **`identity.taxId`** is declared queryable.
- Keys and the support library are available.
- The literal's BSON type matches the schema.
- The caller is authorized to search and decrypt results.

### 23.1. Conceptual Client Setup Flow

~~~text
Configuration:
  MONGODB_URI
  Key Vault namespace
  KMS provider(s) and credentials
  Encryption schema/map
  Crypt shared library / auto encryption support
  Driver version and server compatibility

             |
             v
   Create encryption-enabled MongoClient
             |
             v
   Use collections through that client
             |
             v
   Query with supported operators
~~~

If a process simply runs:

~~~javascript
const client = new MongoClient(process.env.MONGODB_URI);
~~~

without encryption options, **never assume QE is active** merely because the URI targets the right database.

### 23.2. Never Pass Pre-Encrypted Values Arbitrarily into an Automatic Client

Under automatic encryption, the driver expects **plaintext values** for schema-specified fields so it can encrypt them. Passing manually encrypted ciphertext into that same field on an automatic client can fail or trigger erroneous double encryption.

Under explicit encryption, the app manages payloads and query tokens itself. Choose and enforce one model deliberately—never mix them ad hoc across code paths.

### 23.3. Databases Accessed by Both Encrypted and Unencrypted Clients

A system with:

~~~text
Service A -> encryption-enabled driver
Service B -> ordinary driver
DBA tool  -> ordinary connection
~~~

must verify:

- Can Service B write to protected fields?
- Does the server enforce schemas blocking plaintext writes?
- Is the DBA tool restricted to reading ciphertext?
- Can an external tool leak plaintext into audit logs?

Without server-side schema enforcement, an unencrypted client can write plaintext into a field meant to be encrypted, breaking confidentiality and causing QE/CSFLE queries to miss records.

**Never treat “the main service uses an encrypted client” as proof the whole collection stays encrypted.**

## 24. Manual/Explicit Encryption: Use Cases and Risks

Explicit encryption lets the application explicitly:

~~~text
Plaintext value
    |
    v
ClientEncryption.encrypt(value, algorithm/queryType/options)
    |
    v
Encrypted payload
    |
    v
MongoDB insert/find
~~~

### 24.1. When to Consider Explicit Encryption?

- Integrating with custom encryption workflows.
- Choosing keys/encryption per operation within supported bounds.
- Managing ciphertexts intentionally in an existing app security layer.
- Deployment environments where automatic encryption is unsupported on the edition/version.

### 24.2. Never Invent Your Own Algorithms

Avoid:

~~~javascript
// Never use base64 or XOR as encryption!
const encrypted = Buffer.from(plaintext).toString("base64");
~~~

Base64 is trivial public encoding, **not cryptographic encryption**. Likewise, never invent “encryption” by salting and hashing with SHA-256 and treating it as queryable encryption.

Use MongoDB-provided algorithms/APIs with proper key lifecycles and configurations.

### 24.3. Comparing Ciphertexts with Unsupported Operators

With explicit CSFLE, the server sees `BinData` values and can run BSON comparisons—but those results do not match plaintext comparisons.

~~~text
Encrypted value A < encrypted value B
~~~

does not imply:

~~~text
Plaintext value A < Plaintext value B
~~~

If range queries are needed, use official QE `range`. If broader sorting or aggregation is needed, adjust requirements or architecture.

### 24.4. Never Use Explicit Encryption to Bypass Policy

An app using manual encryption must still:

- Encrypt the right fields on every insert path.
- Block unauthorized clients from bypassing encryption.
- Never alter QE metadata manually.
- Keep key IDs, algorithms, `bsonType`s, and `queryType`s consistent.
- Never log plaintext or inferable ciphertexts.
- Maintain re-encryption and restore policies.

## 25. Performance, Storage, and Cost of Queryable Encryption

Encrypted querying over secrets is not free. For Queryable Encryption, MongoDB manages metadata/tags and executes cryptographic query processing.

### 25.1. Sources of Overhead

~~~text
Plaintext document write
          |
          v
Encryption-enabled driver
          |
          v
Encrypted field ciphertext
          |
          +------------------+
          |                  |
          v                  v
 Business document   Encrypted query metadata
          |                  |
          v                  v
   Document write        Metadata/index work
          |                  |
          +---------+--------+
                    |
                    v
            Latency / storage / I/O
~~~

Account for:

- Encrypted payload size.
- Number of queryable encrypted fields.
- Metadata collections.
- Tags generated per field/`queryType`.
- Client-side encrypt/decrypt CPU time.
- KMS/key-cache and initialization costs.
- Write amplification from index/metadata updates.
- Query efficiency across low/high selectivity filters.

### 25.2. Equality Usually Uses Less Metadata Than Range/String

Conceptually:

~~~text
Equality:
  Exact match on encrypted value
  -> relatively compact metadata

Range:
  Multi-bound range search
  -> more structures/tags needed

Substring:
  Substrings across many positions
  -> metadata/tags can grow rapidly
~~~

Never multiply equality tag counts by a fixed factor to estimate range/string costs—overhead depends on **bounds, precision, query length, and QE tuning parameters**.

### 25.3. String Substring Can Generate Heavy Metadata

In QE String queries, tag counts scale with:

- Length of the encrypted field.
- Minimum/maximum substring query lengths.
- Configured string length limits.
- Prefix/suffix vs. substring indexing.

In MongoDB 9.0's GA release, substring search targets bounded short Strings (e.g., max field length 50 chars and query terms 2–6 chars per published bounds). **Never treat QE substring as full-text search over multi-thousand-character descriptions.**

Check exact version limits and estimate storage before enabling substring search across multiple fields.

### 25.4. Range: `min`/`max`/`precision`/`sparsity`/`trimFactor`

A `salary` field encrypted with range QE:

~~~javascript
{
  path: "salary",
  bsonType: "int",
  queries: {
    queryType: "range",
    min: 0,
    max: 1000000
  }
}
~~~

Related tuning parameters (version-dependent):

| Parameter | Role |
|---|---|
| `min`, `max` | Bounds the queryable value domain |
| `precision` | Decimal precision cap for `double`/`decimal` per rules |
| `sparsity` | Trades encrypted range metadata density against query/storage cost |
| `trimFactor` | Controls range index/tag construction and overhead |
| `contention` | Tunes concurrency behavior/cost on repeated values |

**Never pick random tuning numbers**; each carries constraints, side effects, and immutability rules. Benchmark realistic workloads against your server version's documentation.

### 25.5. Precision Is Not Business Rounding

In certain QE `double`/`decimal` range configs, `precision` affects **indexed/queried representations** and may truncate decimal digits rather than applying business rounding rules.

Example:

~~~text
Original stored encrypted value: 10.18
Index/query precision = 1
Relevant query representation: 10.1
~~~

Never base payroll, tax, or interest logic on false rounding assumptions. When exact decimals are required, choose `Decimal128` or integer minor units with matching range configuration.

### 25.6. Metadata Cleanup and Compaction

In QE, metadata collections grow under heavy inserts, updates, and deletes. Docs provide dedicated **encrypted data compaction/cleanup** procedures.

Never run:

~~~javascript
// Never modify QE metadata directly:
db.enxcol_.deleteMany({});
~~~

or rename internal namespaces outside supported tooling. Operations must:

- Monitor metadata storage growth.
- Run compaction/cleanup commands per version and runbook.
- Avoid colliding with large migrations without load testing.
- Account for query execution impacts during compaction.

### 25.7. Diagnosing Query Latency

If an encrypted equality query is slow:

1. Verify the query matches the configured `queryType` and schema.
2. Check whether tenant filters are applied.
3. Check query selectivity.
4. Verify metadata/index health.
5. Measure driver encrypt/decrypt latency.
6. Measure MongoDB query/network round-trip time.
7. Check write load and metadata growth.
8. Verify server and driver versions.

Never assume slowness is caused by a missing B-tree index on the encrypted field; adding one in QE can make performance worse.

## 26. Observability and Logging with Encrypted Fields

### 26.1. Logs May Be Redacted

To avoid leaking sensitive details, Queryable Encryption enforces **redaction** in query logs, the profiler, and diagnostic commands. Details normally visible for plaintext collections may be hidden or omitted.

While this protects privacy, it makes debugging solely from MongoDB slow-query logs harder.

### 26.2. Which Application Metrics Should You Record?

| Suggested Metric | Purpose |
|---|---|
| `encrypted_query_latency_p95` | Latency from the app's perspective |
| `query_type` | Equality/range/string/none workflow breakdown |
| `encrypted_write_latency_p95` | Write cost through encrypted clients |
| `decrypt_latency_p95` | Safe-instrumented decryption duration |
| `kms_errors` | KMS failures and timeouts |
| `encryption_schema_mismatch` | Client/schema/version mismatches |
| `unsupported_operator_errors` | Unsupported query attempts |
| `bson_type_mismatch` | Literal/query/field type mismatches |
| `metadata_storage_bytes` | QE metadata growth |
| `encrypted_collection_migration_progress` | Migration tracking |
| `plaintext_write_incidents` | Policy-violating plaintext write attempts |
| `unauthorized_decrypt_attempts` | Unauthorized access signals |

These are **suggested application metric names**, not built-in MongoDB metric keys.

### 26.3. Never Log Secret Values

Never log:

~~~text
taxId plaintext: TAX-000123
salary plaintext: 85000
decrypted full Document: ...
KMS secret / local master key / DEK material
~~~

Instead log safe metadata:

~~~text
requestId
tenantRef (permitted scope)
collection
queryType
operator family
model/schema version
latency
error code/category
key reference (never key material)
~~~

Even ciphertexts and tags can be sensitive under certain threat models; never dump full encrypted payloads into observability pipelines assuming “it's encrypted so it's harmless”.

### 26.4. Explain and the Profiler

Certain diagnostics are limited or redacted under QE. **Explain output on encrypted collections can differ or omit details** compared to plaintext queries.

When queries run slowly, rely on:

- Application/driver metrics.
- Permitted query-plan and index metadata.
- Cluster resource telemetry.
- QE profiler/log redaction documentation.
- Staging environments with synthetic data—never pipe production plaintext into debugging tools.

Never disable encryption in production just to make logging easier.

### 26.5. Monitoring Must Not Leak Data Permissions

A per-`tenantId` dashboard can itself leak sensitive facts. If a user may not view another tenant's headcount or transaction totals, aggregate dashboards also need authorization and access scoping.

Encrypting `salary` helps little if a public monitoring table exposes **`salaryBandCount` per tenant** against policy.

## 27. Migrating from Plaintext or CSFLE to QE

Suppose a legacy collection holds:

~~~javascript
{
  employeeCode: "E-1001",
  salary: 85000
}
~~~

and needs to migrate to:

~~~javascript
{
  employeeCode: "E-1001",
  salary: BinData(/* QE range */)
}
~~~

### 27.1. Prerequisites to Prepare

1. Identify **fields to encrypt** and each field's `queryType`.
2. Verify server version, edition, driver, and `crypt` support.
3. Inventory all read/write code paths, batch jobs, ETL, backups, and reports.
4. Provision KMS/DEKs and service permissions.
5. Design the target collection created with **`encryptedFields` schema**.
6. Size storage, tags, index metadata, and capacity.
7. Pick a downtime, dual-write, or cutover strategy.
8. Prepare verification checklists and rollback/restore plans.

### 27.2. General Flow

~~~text
Plaintext / old CSFLE collection
              |
              v
Authorized migration reader
              |
              v
Validate types + business invariants
              |
              v
Authorized QE-enabled writer
              |
              v
New QE collection + metadata
              |
              v
Compare counts / sample values / query results
              |
              v
Switch application traffic
              |
              v
Retire old collection and copies by policy
~~~

### 27.3. Never Edit `encryptedFieldsMap` at Runtime Expecting Auto-Migration

MongoDB docs warn that changing **`encryptedFieldsMap`** on a client while old plaintext rows remain causes mismatches: new queries encrypt literals and fail to match legacy rows.

Safer practice is a **versioned migration** writing and validating records into a target collection, never toggling one config variable.

### 27.4. Handling Live Traffic During Migration

If the app keeps writing to the old collection mid-migration, updates can be lost or duplicated. Strategies include:

- Pausing writes during a maintenance window.
- Carefully engineered and tested change capture/dual-write within supported features.
- Checkpointed migration with replay and reconciliation.

Remember **QE imposes limits on change streams and commands**, so never assume a generic CDC connector can decrypt and migrate every encrypted field out of the box.

### 27.5. Validate Against Business Invariants

Do not check only:

~~~text
Old count = 100000
New count = 100000
~~~

Also verify:

- Fields requiring encryption hold ciphertext, with zero plaintext remaining.
- Authorized decrypting clients receive exact original values.
- Unauthorized clients cannot view plaintext.
- Equality/range/string queries return expected matching sets (per feature).
- Business uniqueness constraints still hold.
- Tenant isolation remains intact.
- Indexes and metadata readiness meet targets.
- Reports/ETL have transitioned to the new design.

### 27.6. Handle Legacy Plaintext in Backups and Logs

Even after the new encrypted collection is live, the old collection and pre-migration backups still hold plaintext. Manage deletion, retention, and restores per corporate policy; never delete backups needed for recovery without approval.

## 28. Version Milestones and Differences

Key milestones when reading documentation:

| Feature Branch | What to Check |
|---|---|
| Deterministic/randomized CSFLE | Equality support and driver/algorithm limits |
| QE equality | Available from early QE versions; requires `encryptedFields` schema |
| QE range | Official GA from MongoDB 8.0; earlier versions differ in status/limits |
| QE prefix/suffix/substring | Public preview in MongoDB 8.2; GA in MongoDB 9.0 |
| QE String algorithms | New 9.0 configuration differs from older preview types |
| `$lookup` across multiple encrypted collections | Support and limits vary by version, notably from 8.1+ |
| Range tuning | `sparsity`/`trimFactor`/`precision` bounds can shift by release |
| Driver/`crypt_shared` library | Must match `queryType` support—not server version alone |
| MongoDB Atlas / Enterprise / Community | Automatic/explicit capabilities and deployment support differ |

### 28.1. Never Claim “MongoDB Can Never Search Substrings on Encrypted Fields”

That held true for traditional CSFLE and pre-string-search QE versions, **but is false as a permanent claim for MongoDB 9.0**.

Conversely, claiming “MongoDB has QE substring so any MongoDB collection supports regex on encrypted fields” is also false: it requires matching `queryType`/schema, String types, length caps, version, and driver.

### 28.2. Match Documentation Version to Syntax

If running 7.0, never copy-paste 9.0 examples blindly. When upgrading from 8.2 preview to 9.0, never retain preview `queryType`/algorithm names without checking compatibility guides.

In an Architecture Decision Record (ADR), document:

~~~text
MongoDB server version:
FCV:
MongoDB driver version:
Crypt shared library version:
QE/CSFLE mode:
QueryType per encrypted field:
KMS provider:
Key vault namespace:
Schema/index migration version:
~~~

An encrypted system's documentation should never say merely “uses MongoDB with field encryption” without recording compatibility details.

## 29. Common Errors and Scenarios

### 29.1. CSFLE Equality Query Returns 0 Despite Visible Ciphertext

**Symptom:** `findOne` by `taxId` returns nothing, yet querying by `_id` shows `taxId` contains `BinData`.

Possible causes:

- Query ran through a `MongoClient` **without CSFLE/QE configured**.
- Field uses randomized CSFLE or QE `queryType: none`.
- Query literal used a different BSON type or normalization than insertion.
- Documents were encrypted under a different key, schema, or version.
- Legacy documents remain plaintext after enabling encryption.

**Resolution:** verify encryption client, `encryptedFields`/schema, key ID, BSON type, and a sample record via an authorized client. Never debug by brute-forcing ciphertexts in production.

### 29.2. `$gt` on Salary Returns Wrong Results or Errors

**Cause:** the field uses deterministic/randomized CSFLE, yet the server is asked to compare numeric values on ciphertext.

**Resolution:** if server-side range queries are needed, adopt QE `range` on a supported version; for small datasets where policy permits, pre-filter by metadata and filter/sort decrypted records client-side.

### 29.3. Sorting Salary Gives Nonsensical Order

**Cause:** ciphertext does not preserve numeric order. Even QE `range` filtering does not enable sorting by plaintext salary.

**Resolution:** sort by an approved unencrypted field, or build bounded client-side reporting/computation.

### 29.4. Unique Index on Encrypted Email Fails to Block Duplicates

**Cause:** QE and randomized CSFLE output different ciphertexts for the same email, so the unique index sees distinct keys.

**Resolution:** implement a separate atomic registry/business uniqueness mechanism or reviewed cryptographic lookup token matching your threat model. Never rely on check-before-insert to prevent races.

### 29.5. Regex on Encrypted Name Is Rejected

**Cause:** CSFLE does not support plaintext regexes on ciphertext; QE equality/range do not support arbitrary regexes either.

**Resolution:** if prefix/suffix/substring matches the real need, check QE String queries on a supported version and evaluate their cost. For full-text search, redesign architecture—never silently store `name` plaintext just to index it.

### 29.6. Queryable Encryption Indexes Grow Unexpectedly Large

**Cause:** too many queryable encrypted fields, overly fine range precision, heavy substring metadata tags, or lack of cleanup/compaction.

**Resolution:** measure metadata storage and write amplification, tighten `queryType`/`precision`/`sparsity` per policy, and switch non-queried fields to `queryType: none`.

### 29.7. QE Collection Slows Down After Heavy Updates

**Possible causes:** metadata growth, frequent encrypted index updates, contention, poorly selective filters, or KMS/driver latency.

**Resolution:** instrument every stage, inspect encrypted metadata maintenance and query options. Never add B-tree indexes on encrypted fields out of habit to “fix slowness”.

### 29.8. Array of Objects Cannot Be Queried Normally

**Cause:** encrypted arrays or nested fields in arrays face strict limits; the server lacks plaintext elements for multikey indexing or `$elemMatch`.

**Resolution:** extract child documents under a supported model or revise query requirements. Never index a `BinData` field expecting plaintext element indexing.

### 29.9. Query Works in Service A, Fails in Service B

Possible causes:

- Different MongoDB driver or `crypt` library versions.
- One service uses an encryption-enabled client while the other uses a plain client.
- Divergent encryption schemas or key vault configs.
- Service B uses an unsupported operator.
- Query literals use different BSON types.

**Resolution:** compare configs, package versions, KMS permissions, and schema versions—not just SQL-like query shapes.

### 29.10. Client Fails to Decrypt After Rotation

**Cause:** service lacks the new key, wrong key vault/KMS config, DEK cannot unwrap, or a migration swapped keys inconsistently.

**Resolution:** verify key references/permissions, rotation version, and backup/restore steps; never log DEKs or master keys while debugging.

### 29.11. `$lookup` on Encrypted Key Fails to Match

**Cause:** joins on encrypted fields are restricted; ciphertexts across two collections do not join like plaintext.

**Resolution:** use a non-sensitive opaque reference as the join key, or follow exact version/driver-supported pipeline rules and limits.

### 29.12. Averaging Salary via Aggregation Returns Null or Wrong Value

**Cause:** the server sees `BinData` ciphertexts rather than plaintext Numbers.

**Resolution:** build an authorized client-side calculation or an approved aggregate store—never expose plaintext salaries in the collection.

### 29.13. Unencrypted Field Fails with `$text` Error

In some automatic encryption modes, the driver blocks operators like **`$text`, `$where`, `$jsonSchema`** even when targeting an unencrypted field.

**Resolution:** check the supported-operations list for an **encryption-configured `MongoClient`**; separate search services/collections if full-text search is required and cannot safely share the pipeline.

### 29.14. Cannot Switch `queryType` from Equality to Range

**Cause:** `encryptedFields` schemas and indexes are built for the declared `queryType` and carry immutability rules.

**Resolution:** run a versioned migration to a new collection/schema, backfill, and cut over. Never edit a local `encryptedFieldsMap` mid-flight expecting indexes to rebuild automatically.

### 29.15. Report Leaks Secret Data Despite Encrypted DB

**Cause:** an API or reporting service holding decryption rights exported plaintext into an unprotected cache, warehouse, or log.

**Resolution:** audit downstream data flows and enforce field-level authorization and retention everywhere. MongoDB encryption does not stop authorized decrypting apps from leaking data downstream.

### 29.16. KMS Error Causes Request Failures

**Cause:** failed key initialization, insufficient permissions, provider timeout, or cold key cache.

**Resolution:** bounded retries, health checks, and fail-closed behavior. Never fall back to writing plaintext “temporarily” for availability when policy requires field encryption.

## 30. Runbook for Checking a Query on an Encrypted Field

### Step 1 — Identify the Encryption Model

Record:

~~~text
Collection:
Field path:
Encryption: CSFLE deterministic / randomized / QE
QueryType:
BSON type:
Driver version:
Server version:
Key ID:
~~~

### Step 2 — Define the Desired Operation

Examples:

~~~text
exact match taxId
salary numeric range
sort by salary
calculate average salary
prefix name search
join by customer ID
~~~

Check against **supported operators/aggregation expressions**. If unsupported, never send the query hoping it works.

### Step 3 — Inspect Indexes and Schema

- Does deterministic CSFLE equality have an appropriate index?
- Did QE declare the right `queryType`?
- Were QE metadata collections/indexes created properly?
- Was a B-tree index accidentally added on a QE encrypted field?
- Are unencrypted metadata fields sufficient for routing/filtering/sorting?

### Step 4 — Inspect the Client

- Is the code actually using an encryption-enabled `MongoClient`?
- Do KMS, key vault, DEK, and config match?
- Were explicit and automatic encryption accidentally mixed?
- Does the query literal match the schema BSON type?

### Step 5 — Check Authorization

- Does tenant context come from authentication?
- Is the user permitted to search/decrypt this field?
- Is the API leaking plaintext into logs or caches?
- Is any ongoing migration fully synchronized?

### Step 6 — Measure Latency by Layer

~~~text
Authentication/authorization
            |
            v
Driver encryption/query analysis
            |
            v
Network + MongoDB query
            |
            v
Driver decryption
            |
            v
Response transformation
~~~

Measure latency across each stage rather than blaming missing indexes immediately.

### Step 7 — Classify and Resolve

Categories:

- **Unsupported query pattern** → change `queryType`/schema/architecture.
- **Wrong encryption client** → fix driver/KMS configuration.
- **Wrong BSON type** → fix serialization/validation.
- **Missing query index/metadata** → fix collection-creation workflow.
- **Metadata/index overhead** → tune per QE guidance.
- **Permission leak** → treat as a security incident.
- **Migration inconsistency** → reconcile and recover per runbook.

Any production encryption schema change or metadata cleanup requires authorization and formal approval.

## 31. Architectural Alternatives to Querying Encrypted Fields

### 31.1. Query by Opaque ID

~~~text
User provides customerCode
          |
          v
MongoDB exact match on opaque customerCode
          |
          v
Driver decrypts secret profile
~~~

Works well when callers already hold a non-sensitive public ID.

### 31.2. Query by Permitted Metadata

~~~text
tenantId + createdAt + status
          |
          v
Narrow bounded result set
          |
          v
Authorized client decrypts selected fields
~~~

Suitable only when policy permits that metadata and candidate sets stay small.

### 31.3. Separate Searchable Info from Secrets

A collection can hold:

~~~javascript
{
  docRef: "DOC-1001",
  publicTitle: "Process guide",
  encryptedContent: BinData(/* confidential */)
}
~~~

Search on **`publicTitle`** if genuinely safe to expose, then decrypt contents after authorization checks.

**Never derive `publicTitle` from a secret** without analyzing disclosure risk.

### 31.4. Dedicated Application-Side Computation

When a sensitive aggregate must be computed over a small dataset:

~~~text
Authorized batch
  -> query by approved nonsecret selectors
  -> decrypt records
  -> compute in protected runtime
  -> output approved aggregate only
~~~

Protect memory and logs, control exports, and ensure dataset size stays manageable.

### 31.5. Adjust Product Requirements

Sometimes the best answer is **not building arbitrary search over every sensitive field**. For example:

- No need to search every `medicalNote` for arbitrary words.
- No need to sort the whole company top-to-bottom by salary.
- No need for autocomplete across full bank account numbers.

Instead of breaking security guarantees in the database, redesign the UI/workflow to locate records via an opaque code and display authorized details.

## 32. Practice Exercises and Scenarios

These exercises primarily test **design analysis and limitation awareness**. Running live QE/CSFLE commands requires a properly configured MongoDB deployment, driver, and KMS; never run schema or encryption changes directly on collections holding real data.

### Exercise 1. Distinguishing Encryption Layers

A system enables TLS and encryption at rest yet stores `salary` as a normal number `85000`.

**Question:** Can MongoDB server run `$avg` on `salary`? Does that mean `salary` is client-side encrypted?

**Answer:** The server still sees plaintext `salary` at the database layer, so numeric aggregation works normally. However, `salary` is **not client-side field encrypted**; TLS and encryption at rest protect other layers.

### Exercise 2. Deterministic or Randomized?

An app needs:

~~~text
taxId: exact match lookup
medicalNote: read only after employeeCode is known
~~~

**Question:** Using CSFLE, which algorithm fits each field?

**Guidance:** `taxId` can use deterministic encryption for equality if leakage and limits are acceptable; `medicalNote` should use randomized encryption since plaintext search is unneeded. Evaluate cardinality, permissions, and key design before finalizing.

### Exercise 3. Frequency Analysis

A deterministically encrypted field takes three plaintext values distributed 90%, 9%, and 1%.

**Question:** Does encryption completely hide each value's frequency?

**Answer:** No. Equal plaintexts yield identical ciphertexts in deterministic CSFLE, exposing value group sizes and enabling inference.

### Exercise 4. Randomized Equality

Two documents have identical:

~~~text
medicalNote plaintext = "allergy"
~~~

with different ciphertexts. A developer indexes `medicalNote` and queries for `"allergy"`.

**Question:** Does that index locate both documents by plaintext?

**Answer:** No. Indexing randomized ciphertexts cannot enable plaintext equality lookups. Redesign query architecture or choose an encryption scheme supporting the query.

### Exercise 5. QE Equality

**`identity.taxId`** declares:

~~~javascript
{
  path: "identity.taxId",
  bsonType: "string",
  queries: {
    queryType: "equality"
  }
}
~~~

**Question:** With a QE client, can you look up `taxId` by equality? Can you run numeric range queries on it?

**Answer:** Equality works per schema and BSON type; that does not allow range queries on String `taxId`. Range operations require an appropriate field and `queryType`.

### Exercise 6. QE Range and Sorting

A collection encrypts **`salary`** with QE range. Product wants:

1. Filter salaries between 60000 and 100000.
2. Sort all results descending by `salary`.

**Question:** Are both operations guaranteed simultaneously?

**Answer:** Range filtering works on compatible versions/schemas. **Plaintext salary sorting is not automatically supported** simply because range filtering is enabled; choose another approach if sorting is required.

### Exercise 7. QE String Search by Version

A MongoDB 7.0 system needs suffix searches on encrypted account numbers. The team reads an article on MongoDB 9.0 QE String GA.

**Question:** Can they copy that syntax into 7.0?

**Answer:** No. Prefix/suffix/substring support varies by version: 8.2 introduced public preview; 9.0 brought GA. Plan a compatible upgrade or redesign rather than assuming 7.0 supports it.

### Exercise 8. `$regex` on Ciphertext

~~~javascript
db.records.find({
  encryptedName: /^Nguyen/
});
~~~

**Question:** Can regex match directly inside an encrypted field?

**Answer:** Not as a normal plaintext String regex. CSFLE does not support plaintext regexes on ciphertext. Newer QE requires a **matching String `queryType` and supported operators**, not arbitrary regexes.

### Exercise 9. Wrong Index on QE

A developer runs:

~~~javascript
db.records.createIndex({
  encryptedSalary: 1
});
~~~

on a QE `encryptedSalary` field because range queries feel slow.

**Question:** Is this recommended by documentation?

**Answer:** No. QE relies on dedicated encrypted query indexes/metadata. Adding standard indexes on encrypted fields can degrade performance. Check `encryptedFields` schema, `queryType`, metadata, and version-appropriate tuning.

### Exercise 10. `__safeContent__`

A team wants to edit **`__safeContent__`** directly to return more QE matches.

**Question:** Should they do this?

**Answer:** No. `__safeContent__` and related metadata belong to QE internals; never modify them directly. Tune and index using version-appropriate supported tools.

### Exercise 11. Plaintext Uniqueness on QE

Two customers have identical plaintext emails, yet distinct QE ciphertexts. A unique index is placed on `encryptedEmail`.

**Question:** Does that unique index prevent duplicate plaintext emails?

**Answer:** No. MongoDB compares encrypted index keys, not plaintext uniqueness invariants. Build a dedicated atomic business uniqueness or reviewed cryptographic lookup pattern.

### Exercise 12. Check-Before-Insert Race

Two concurrent requests both run `find(email)`, get nothing, and both insert.

**Question:** Can `find` before `insert` prevent races?

**Answer:** No. You need an atomic uniqueness primitive or concurrency-safe workflow while still protecting email confidentiality. Encryption alone does not fix races.

### Exercise 13. Secret Shard Key

A QE collection encrypts `taxId`. A DBA plans to choose **`taxId`** as the shard key to distribute documents.

**Question:** Is that valid?

**Answer:** No. QE encrypted fields cannot be shard keys. Pick an unencrypted, policy-approved opaque shard key aligned with queries and capacity.

### Exercise 14. `$avg` on Encrypted Salary

Query:

~~~javascript
db.employees.aggregate([
  {
    $group: {
      _id: "$departmentId",
      avgSalary: { $avg: "$salary" }
    }
  }
]);
~~~

**Question:** When `salary` is ciphertext, can MongoDB compute exact plaintext average salary?

**Answer:** Not via standard numeric aggregation. Use an authorized client-side calculation or an approved separate aggregate store.

### Exercise 15. `$inc` on a QE Field

~~~javascript
await encryptedCollection.updateOne(
  { employeeCode: "E-1001" },
  { $inc: { salary: 5000 } }
);
~~~

**Question:** Why does this not fit encrypted `salary`?

**Answer:** `$inc` requires the server to add to an existing Number. The server lacks plaintext `salary`; QE automatic encryption only supports specific update operators such as `$set`/`$unset` on encrypted fields. Read/decrypt, compute client-side, and write back with `$set` plus a version guard.

### Exercise 16. Null on an Encrypted Field

The application executes:

~~~javascript
await encryptedCollection.findOne({
  "identity.taxId": null
});
~~~

**Question:** Can you assume `null` comparisons work on encrypted queries?

**Answer:** No. Comparisons with `null` on encrypted fields may be rejected. Distinguish omitted fields, optional fields, and threat-model-approved metadata.

### Exercise 17. Array of Documents

~~~javascript
{
  contacts: [
    { type: "WORK", phone: "+84..." },
    { type: "HOME", phone: "+84..." }
  ]
}
~~~

**Question:** Can a collection with randomized encryption over `contacts` use a multikey index to search individual plaintext phones?

**Answer:** No. The server sees an encrypted array as ciphertext and cannot index individual elements. Extract child documents or adjust query design.

### Exercise 18. QE Upsert with Encrypted Filter

Code:

~~~javascript
await encryptedCollection.updateOne(
  { "identity.taxId": "TAX-1001" },
  { $set: { status: "ACTIVE" } },
  { upsert: true }
);
~~~

**Question:** Can you assume the newly inserted document includes `identity.taxId`?

**Answer:** No. QE limits encrypted fields in upsert filters; those fields may be omitted from inserted documents. Explicitly construct insert payloads/invariants and never treat upsert as a uniqueness substitute.

### Exercise 19. Sorting After Decrypting One Page

An app fetches the first 20 records by `createdAt`, decrypts `salary`, sorts those 20, and labels them “Top 20 highest-paid employees company-wide”.

**Question:** What is wrong?

**Answer:** Those 20 rows are a **subset by `createdAt`**, not the full population; sorting locally does not produce the global top salaries. Redesign the query, data flow, or product requirement.

### Exercise 20. Case-Insensitive Collation

`email` uses deterministic encryption. A developer adds `collation` `strength=2` assuming `"Alice@example.com"` and `"alice@example.com"` will match.

**Question:** Can you trust the result?

**Answer:** No. MongoDB collations do not apply plaintext string semantics to ciphertext. For canonical equality, the app must apply consistent business normalization before encrypting.

### Exercise 21. Client Without Keys

A DBA has read permissions on a MongoDB collection but lacks DEK/KMS access.

**Question:** Can the DBA read plaintext of client-encrypted fields directly from the server?

**Answer:** By design, the server stores ciphertext; without decryption capability the client does not see plaintext. Still, evaluate metadata exposure and inference risks—never drop RBAC because fields are encrypted.

### Exercise 22. Rapid QE Metadata Growth

A collection has three String `substring`-queryable fields; writes surge and metadata storage exceeds projections.

**Question:** What should you investigate?

**Guidance:** Check `substring` version limits, tag counts by length, field/query length configs, write volume, metadata compaction/cleanup, and whether all three fields truly require substring search.

### Exercise 23. Changing QE `queryType` Without Migration

`salary` started with QE `equality`/`none`. Product wants `range`, so the team edits only local `encryptedFieldsMap`.

**Question:** Why is that wrong?

**Answer:** `queryType` is part of the schema/index metadata and cannot mutate freely. Legacy data and indexes do not convert to range automatically. Run a versioned collection migration, backfill, and cutover.

### Exercise 24. Using `$lookup` with Encrypted Join Keys

`orders` and `customers` both encrypt `customerId`.

**Question:** Can you assume `$lookup` `localField`/`foreignField` on `customerId` works just like plaintext?

**Answer:** No. QE/CSFLE impose join limits on encrypted fields; versions differ on self-joins or multi-collection behavior. A simpler design uses a non-sensitive opaque reference where policy allows.

### Exercise 25. String Prefix Queries on Newer Versions

A MongoDB 9.0 app needs prefix searches `"CASE-2026-"` on encrypted case numbers. A developer uses a regex.

**Question:** What is required to use the new QE String capability?

**Guidance:** Configure `queryType: prefix` with the 9.0 string algorithm/schema, valid case/diacritic/length parameters, and compatible driver/`crypt` shared library. Use official QE expressions rather than regexes on ciphertext.

### Exercise 26. Full-Text Search on Health Notes

`medicalNote` holds multi-thousand-character prose. Users want to find documents matching any keyword or semantic phrase.

**Question:** Should you enable QE `substring` and treat it as full-text/semantic search?

**Answer:** No. QE `substring` on supported versions targets bounded short Strings, not full Atlas Search/Vector Search over long notes. Evaluate search architecture within privacy boundaries or revise requirements.

### Exercise 27. KMS Outage

The key provider loses connectivity; a service proposes temporarily writing plaintext `salary` to avoid downtime.

**Question:** Should you allow that?

**Answer:** No if policy requires field encryption. Fail closed, use bounded retries/queues, alert, and follow recovery plans—never silently downgrade protection.

### Exercise 28. Migration with Legacy Plaintext Data

A collection holds 1 million plaintext records. The team enables `encryptedFieldsMap` in the service and writes new records with QE.

**Question:** Why do searches and security fail?

**Answer:** Legacy records stay plaintext so encrypted queries miss them, and plaintext persists in the collection and backups. Run a proper migration creating the target collection, backfilling/re-encrypting, reconciling, and cutting over.

### Exercise 29. Designing an HR Profile System

Requirements:

~~~text
employeeCode: exact match and unique per tenant
departmentId: filter, group
createdAt: filter/sort
taxId: equality lookup, must stay hidden
salary: range filter, must stay hidden
medicalNote: read only after finding the person
~~~

**Task:** Build a field table answering:

1. Which fields stay plaintext per threat model?
2. Which fields use randomized CSFLE or QE `none`?
3. Which fields use QE `equality`?
4. Which fields use QE `range`?
5. Which standard indexes are permitted?
6. How do you guarantee unique `employeeCode` and tenant isolation?
7. Must salary-average reporting change?

**Suitable answer:** `tenantId`/`employeeCode`/`departmentId`/`createdAt` can remain metadata if policy allows, with standard indexes. `taxId` uses QE `equality`, `salary` uses QE `range`, and `medicalNote` uses `queryType: none` or randomized CSFLE depending on collection architecture. Never use `salary` ciphertext for sort/avg; enforce unique `employeeCode` on unencrypted fields per topology. Verify full authorization workflows and versions.

### Exercise 30. Choosing an Approach for a Customer Lookup API

The app needs to look up customers by:

- Exact `customerRef`.
- Exact encrypted `taxId`.
- Partial encrypted `phone` string.
- Multi-page free-form notes.

**Question:** Does one index type solve all four?

**Answer:** No. `customerRef` uses a standard exact index; `taxId` uses QE `equality` or deterministic CSFLE under valid conditions; partial String search on `phone` needs QE String queries on a supported version or a redesigned lookup; multi-page notes require separate search and security evaluation. Never treat one B-tree index or one encrypted `queryType` as universal.

### Exercise 31. Reviewing a Design Whose Metadata Leaks Secrets

Document:

~~~javascript
{
  salary: BinData(/* encrypted */),
  salaryForSort: 95000,
  salaryBand: "TOP_1_PERCENT"
}
~~~

**Question:** What goals do the auxiliary fields undermine?

**Guidance:** `salaryForSort` exposes `salary` directly; `salaryBand` leaks sensitive information by classification. Threat modeling must evaluate all metadata and derived fields, not only fields labeled encrypted.

### Exercise 32. Building a Compatibility Matrix

Suppose an organization runs MongoDB 8.0 in production and MongoDB 9.0 in the lab.

**Requirement:** Build a matrix for:

1. Deterministic CSFLE equality.
2. Randomized CSFLE query by value.
3. QE equality.
4. QE range.
5. QE prefix/suffix/substring.
6. QE plaintext unique constraint.
7. QE encrypted shard key.
8. QE aggregation sum/sort on salary.

**Guidance:** Mark Supported only with evidence from exact version/driver docs. Never mark 9.0 String features Supported for 8.0, and never mark unique/plaintext sort Supported just because range queries work.

## 33. Pre-Deployment Encrypted Field Checklist

### 33.1. Data Design

- [ ] Documented threat model and list of protected fields.
- [ ] Documented **mandatory queries** per field.
- [ ] Selected valid **deterministic/randomized CSFLE** or **QE `queryType`** per field.
- [ ] Verified BSON types, optional/`null` behavior, and nested/array limits.
- [ ] Evaluated whether plaintext metadata leaks sensitive facts.
- [ ] Chose an unencrypted shard key if sharding.
- [ ] Designed uniqueness without relying on QE ciphertext unique indexes.

### 33.2. Server, Driver, and Keys

- [ ] Server, FCV, driver, and `crypt` library support target features.
- [ ] Separate key vault, KMS credentials, and RBAC exist.
- [ ] Encryption schemas and `queryType`s are versioned.
- [ ] Server-side enforcement prevents accidental plaintext writes.
- [ ] Zero secrets/key material in repos, logs, or public docs.
- [ ] KMS outage handling and key rotation plans exist.

### 33.3. Indexes and Queries

- [ ] QE collections/indexes created via supported workflow.
- [ ] No B-tree indexes manually added on QE encrypted fields in place of encrypted indexes.
- [ ] Equality/range/string queries use only supported operators.
- [ ] No sort, sum, avg, regex, or full-text on ciphertext as plaintext.
- [ ] Updates/upserts/bulk writes conform to supported operations.
- [ ] Reporting and joins are designed around encrypted field limits.

### 33.4. Security and Operations

- [ ] API enforces field-level authorization before returning decrypted data.
- [ ] `tenantId` and permissions come from authentication, never unverified user input.
- [ ] Telemetry tracks encryption errors, KMS latency, metadata growth, and migrations.
- [ ] Logs and traces omit sensitive plaintext and keys.
- [ ] Backups and restores tested with proper decryption permissions.
- [ ] Migration plans cover legacy plaintext/CSFLE data and historical retention.
- [ ] Tested on synthetic data free of real secrets prior to rollout.

## 34. Version-Specific References

Limitations vary by MongoDB server and driver version. Always verify your exact release branch before applying examples in production. Official sources:

- [MongoDB — Choose an In-Use Encryption Approach](https://www.mongodb.com/docs/manual/core/queryable-encryption/about-qe-csfle/)
- [MongoDB — CSFLE Encryption Algorithms](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/encryption-algorithms/)
- [MongoDB — CSFLE Supported Operations](https://www.mongodb.com/docs/manual/core/csfle/reference/supported-operations/)
- [MongoDB — CSFLE Limitations](https://www.mongodb.com/docs/manual/core/csfle/reference/limitations/)
- [MongoDB — QE Supported Operations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/supported-operations/)
- [MongoDB — QE Limitations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/limitations/)
- [MongoDB — QE Create an Encryption Schema](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-create-encryption-schema/)
- [MongoDB — QE Encrypted Fields and Enabled Queries](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/encrypt-and-query/)
- [MongoDB — Estimate QE Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)
- [MongoDB — Queryable Encryption Explicit Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/manual-encryption/)
- [MongoDB — MongoDB 8.2 Release Notes](https://www.mongodb.com/docs/manual/release-notes/8.2/)
- [MongoDB — QE Prefix, Suffix, Substring GA Announcement (29/09/2026)](https://www.mongodb.com/products/updates/now-ga-queryable-encryption-prefix-suffix-and-substring-support/)

**/manual/** pages track the latest documentation release. If running an older server, open the matching version path (such as **/v8.0/** or **/v7.0/**) alongside your driver docs.

## 35. Summary

Client-side field encryption protects data before it reaches MongoDB, in exchange for **no longer assuming all plaintext query and indexing features still work**. Remember the distinctions:

~~~text
                 FIELD ENCRYPTION
                       |
          +------------+-------------+
          |                          |
         CSFLE                 QUERYABLE ENCRYPTION
          |                          |
    +-----+------+          +--------+---------+
    |            |          |        |         |
Deterministic Randomized  Equality  Range  String query
    |            |          |        |         |
  Exact       No direct    Exact    Range   Prefix / suffix /
 equality    value query  lookup   filters  substring by version
    |            |          |        |         |
    +------------+----------+--------+---------+
                       |
                       v
           INDEX, SCHEMA, KEYS, VERSION
                       |
                       v
            APP AUTHORIZATION + AUDIT
~~~

**Ten essential principles:**

1. **MongoDB sees only ciphertext** for properly client-encrypted fields; BSON comparisons or arithmetic on ciphertext do not reflect plaintext semantics.
2. **Deterministic CSFLE** supports equality while leaking duplicate-value patterns; **randomized** hides duplicates better but cannot be queried directly by value.
3. **Queryable Encryption** enables pre-declared query types—equality, range, and String prefix/suffix/substring on supported versions—without **making every operator valid**.
4. **Never add B-tree indexes onto QE encrypted fields** to replace QE indexes. Query metadata and **`__safeContent__`** must be managed through supported mechanisms.
5. **Unique indexes on randomized/QE ciphertext do not guarantee plaintext uniqueness**. Uniqueness requires a dedicated concurrency-safe business model.
6. **Encrypted shard keys, arrays, nulls, collations, sorting, aggregations, joins, updates/bulk, views, time series, and Search** all carry limitations that must be evaluated before locking a schema.
7. **Range queries do not mean plaintext sort/avg/sum**. Computations outside `queryType` require authorized app-layer processing or architectural redesign.
8. **Every query requires the right client, keys, BSON type, `queryType`, and version**. An ordinary MongoDB client cannot decrypt data merely by having the URI.
9. **Key management and authorization are separate responsibilities**: backend decryption rights do not equal per-user viewing rights, and derived metadata or logs can still leak data.
10. **Field encryption is an architectural and lifecycle commitment**. Migrations, key rotation, encrypted query indexes, compaction, backups, and version compatibility require runbooks, not a single config flag.

Strong solutions always begin by asking **“what must users genuinely query?”** and **“what metadata may the server see?”**. Only once those two questions are answered should you choose CSFLE or Queryable Encryption, pick `queryType`s, design indexes and keys, and verify required MongoDB features remain supported. The goal is not merely turning encryption on—it is **protecting data while reliably serving authorized business queries within clearly understood and verified boundaries**.
