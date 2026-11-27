# Client-Side Field Level Encryption and Queryable Encryption in MongoDB

## 1. Why Are Disk Encryption and TLS Still Not Enough?

A customer profile management app stores documents like:

```javascript
{
  _id: ObjectId("66a000000000000000000335"),
  tenantId: "ORG-A",
  fullName: "Customer A",
  email: "person@example.test",
  nationalId: "ID-00991",
  incomeVnd: NumberLong("24000000"),
  internalNote: "Sensitive note"
}
```

The application must let authorized staff **look up the right customer by identifier** and occasionally filter by income bracket, while database infrastructure admins or anyone stealing backups **must not be able to read sensitive fields in plaintext**.

Two common protection layers:

- **TLS / in transit:** encrypts the network channel between the application and MongoDB.
- **Encryption at rest:** protects data on disks/snapshots within the scope of the deployed mechanism.

Both layers are essential, yet data can still be **decrypted on the MongoDB server** to execute queries. Anyone with database read privileges on the collection can view plaintext values if you rely solely on those layers.

**Client-Side Field Level Encryption (CSFLE)** and **Queryable Encryption (QE)** belong to **in-use encryption**: fields are encrypted **on the client/driver before being sent** to MongoDB. The server stores ciphertext, while only authorized clients holding the valid keys decrypt when reading.

This lesson belongs to the **Security** chapter of the **Database Engine Document MongoDB** module, focusing on how both technologies protect data, query capabilities, key setup, limitations, and safe deployment.

After this lesson, you will be able to:

1. Distinguish TLS, encryption at rest, CSFLE, and Queryable Encryption.
2. Explain **deterministic** and **randomized** CSFLE, including frequency-analysis risks.
3. Explain why QE can still query randomly encrypted ciphertexts, at the cost of extra metadata and overhead.
4. Distinguish **CMK**, **DEK**, **Key Vault**, and KMS; understand that losing keys can mean losing data.
5. Choose the right query types—**equality, range, prefix, suffix, substring**—per MongoDB version and BSON type.
6. Design encrypted schemas/`encryptedFields`; avoid creating ordinary indexes on QE fields expecting them to support encrypted queries.
7. Understand limitations around unique indexes, TTL, sharding, migrations, updates, aggregations, and collations.
8. Build explicit CSFLE and automatic QE experiments in Node.js **on a lab cluster**, using simulated keys strictly for learning.
9. Plan authorization, rotation/backups, monitoring, incident response, and verification that plaintext never leaks.

## 2. Client-Side Encryption Architecture

### 2.1. Write Flow

```text
         Application / MongoDB Driver
                    |
           plaintext in memory
                    |
              select field
                    |
       DEK + encryption library
                    |
           ciphertext (BinData)
                    |
               TLS network
                    |
                    v
               MongoDB Server
                    |
             store ciphertext
                    |
             Disk / Replicas
```

The MongoDB server still sees collection names, field names, some metadata, and unencrypted fields. It **does not hold plaintext CMKs/DEKs** to decrypt properly protected fields.

### 2.2. Read Flow

```text
            MongoDB Server
                   |
          return ciphertext
                   |
                   v
             MongoDB Driver
                   |
        fetch protected DEK
        and unwrap via right KMS
                   |
                decrypt
                   |
                   v
        plaintext in application
```

Only clients configured and authorized to reach the **right key vault/KMS** can decrypt. Once decrypted in application memory, however, data can still leak via logs, crash dumps, API responses, or a compromised service.

### 2.3. Protection Boundaries and Threat Model

These two technologies primarily defend when an attacker:

- Obtains only a copy of the database or backup.
- Has database read access to ciphertext without key access.
- Observes network traffic without holding client keys.
- Holds broad server DBA rights without the application's decryption keys.

They **do not automatically protect** against:

- Hijacked clients that hold decryption rights.
- Malware running inside the same process as the driver accessing plaintext/CMK.
- APIs mistakenly returning sensitive fields to unauthorized users.
- Compromised KMS credentials or CMKs.
- Side-channel analysis of query logs and snapshots in certain threat models.
- Unencrypted fields, field names, document sizes, or remaining access patterns.

In particular, **QE does not guarantee security against an attacker with persistent access to the environment or both snapshots and query transcripts/logs**; always check the official threat model, especially for range queries. Never promise “absolute zero-knowledge under all circumstances”.

## 3. Comparing CSFLE and Queryable Encryption

### 3.1. CSFLE: Two Encryption Modes

CSFLE supports:

- **Deterministic:** for the same DEK, BSON type, and plaintext, encryption produces identical output. This enables certain **equality queries** on encrypted fields.
- **Randomized:** identical plaintexts produce different ciphertexts each time. This reduces duplicate/frequency observation risks, **but does not support direct equality queries** on that field's value.

### 3.2. Queryable Encryption: Randomized Encryption That Remains Queryable

QE uses **randomized** encryption paired with protected auxiliary metadata to support searches over encrypted fields without MongoDB ever decrypting the field's plaintext.

Supported query types by version include:

- **Equality**: equality/inequality and set membership operators as supported.
- **Range**: greater-than/less-than conditions on supported BSON types.
- **Prefix/suffix/substring** on strings in versions supporting those features.
- **None**: encrypts the field while **disallowing** queries on its value.

QE does not make every MongoDB operator work on ciphertexts. Clear limits apply to BSON types, commands, updates, and aggregations.

### 3.3. Decision Matrix

| Criterion | CSFLE Deterministic | CSFLE Randomized | Queryable Encryption |
| --- | --- | --- | --- |
| Encrypted on client | Yes | Yes | Yes |
| Same plaintext → same ciphertext | Yes | No | No (randomized mechanism) |
| Equality query | Yes with proper config/driver | No | Yes if field configured for `equality` or compatible type |
| Range query | Not a standard CSFLE capability | No | Yes in supported versions |
| Prefix/suffix/substring | No | No | Yes in MongoDB 9.0 GA with compatible driver/library |
| Frequency leakage from identical ciphertexts | Risky, especially low-cardinality | Greatly reduced | Does not expose equality via raw ciphertext; other threat-model considerations apply |
| Management structure | Encryption schema/DEKs | Encryption schema/DEKs | `encryptedFields`, key vault, ESC/ECOC, `__safeContent__` |
| Metadata/search overhead | Depends on field count | Depends on field count | Higher writes/storage and query cost |
| Use case | High-cardinality IDs/emails needing exact match | Notes or payloads read only by document ID | Sensitive fields requiring equality/range/partial-string search |

**Selection guidance:** start from **query requirements**. Fields displayed only after fetching a document by `_id` rarely need queryable indexes. If you still must query encrypted data, evaluate QE rather than weakening security by using deterministic encryption on a low-cardinality field.

## 4. Versions and Feature Support

This topic is **heavily version-dependent**:

| Capability | Key Milestone |
| --- | --- |
| CSFLE | Available since MongoDB Server 4.2 under supported conditions |
| QE equality | Introduced and GA in the MongoDB 7.0 line, with preview/prior capabilities earlier |
| QE range | MongoDB Server 8.0 and later |
| QE prefix/suffix/substring on strings | **MongoDB Server 9.0 and later** for GA; requires compatible driver/library |
| Prefix/suffix/substring public preview | Available in 8.2/8.3; **not directly compatible with 9.0 GA** per migration notes |
| Automatic encryption | Depends on driver version, **MongoDB Atlas/Enterprise**, and Automatic Encryption Shared Library |
| Explicit encryption/decryption | Usable in broader environments when driver and server support it; check exact limits |

In September 2026, MongoDB announced **GA** for QE prefix, suffix, and substring queries. Crucially, if running the **public preview** on 8.2/8.3, **do not upgrade assuming existing ciphertexts/indexes work directly in 9.0**; consult official migration documentation.

Never judge support solely from `mongosh --version`. Verify **server, FCV, driver, cryptographic shared library, topology, edition/plan, and KMS configuration**.

### 4.1. MongoDB Community and Automatic Encryption

MongoDB's Quick Start docs distinguish: **automatic encryption** targets compatible Atlas/Enterprise environments; MongoDB Community does not support the same **automatic** path in official examples, though certain **explicit encryption** capabilities work depending on server/driver. Never run automatic QE code on standalone Community and conclude “QE is broken”.

### 4.2. Replica Sets and Sharded Clusters

QE supports **replica sets and sharded clusters** in compatible versions; current docs note **standalone** and **secondary reads** are not supported in QE contexts. With sharding, additional rules govern shard keys, indexes, and encrypted metadata structures.

Do not use a standalone `mongod` demo to validate all QE behaviors.

## 5. Envelope Encryption: CMK, DEK, and Key Vault

### 5.1. Three Layers of Responsibility

```text
Customer-managed KMS
      |
      | holds Customer Master Key (CMK)
      |
      +--- unwrap / wrap ---> Data Encryption Key (DEK)
                                     |
                                     | encrypts field on client
                                     v
                           MongoDB encrypted fields
                                     |
                                     v
                          Ciphertext in documents

MongoDB Key Vault collection
      |
      +-- stores CMK-wrapped DEKs
      +-- key metadata / keyAltNames
```

- **CMK (Customer Master Key)**: root key controlled by the organization, housed in a remote key management service.
- **DEK (Data Encryption Key)**: key used to encrypt/decrypt data at the field level.
- **Key Vault collection**: MongoDB collection storing **encrypted/wrapped DEKs** and metadata—never plaintext CMKs.
- **KMS**: AWS KMS, Azure Key Vault, Google Cloud KMS, KMIP, or compatible provider per documentation.

Clients hold KMS permissions to unwrap DEKs and run encryption. MongoDB Server never owns plaintext DEKs.

### 5.2. The Key Vault Is Critical Data Requiring Backups

Example:

```javascript
{
  _id: UUID("00000000-0000-4000-8000-000000000335"),
  keyMaterial: BinData(0, "...wrapped DEK..."),
  masterKey: { provider: "aws", /* ... */ },
  keyAltNames: ["tenant-a-private-fields"],
  status: 0,
  creationDate: ISODate("2026-11-14T04:00:00Z")
}
```

This is illustrative only. **Never log plaintext `keyMaterial`**, never copy the Key Vault to public storage, and never use example UUIDs as real keys.

With `keyAltNames`, the Key Vault needs an appropriate **unique index** so one alias cannot point to two different DEKs. Separate key write/delete privileges from business collection CRUD privileges.

### 5.3. Losing Keys Can Mean Irrecoverable Data Loss

If the CMK needed to unwrap a DEK is lost, or the DEK needed to decrypt ciphertext is deleted, data can become **permanently unreadable** even with intact database backups.

Therefore backup and recovery must cover:

1. MongoDB data and metadata.
2. The Key Vault.
3. Ability to restore KMS/CMK access and key history.
4. Encrypted-field schemas and compatible driver versions.
5. Restore testing in an isolated, access-controlled environment.

**Never** run `deleteKey()` or destroy a CMK to “clean up old keys” until certain no ciphertext anywhere still depends on them.

### 5.4. Local KMS Is Strictly for Testing

MongoDB supports a **local key provider** using a 96-byte key, convenient for labs:

```javascript
import { randomBytes } from "node:crypto";

const localMasterKey = randomBytes(96);
const kmsProviders = {
  local: {
    key: localMasterKey
  }
};
```

This is an **ephemeral in-memory key** for learning, not a production design. When the process exits and `localMasterKey` is lost, any DEKs wrapped by it can never be decrypted. Never hardcode this key in source/git, logs, or shared docs.

Production must use a **remote KMS**, RBAC, auditing, separation of duties, and rotation/restore runbooks.

## 6. Deterministic CSFLE: Queryable, Yet Leaks Frequency

### 6.1. Identical Ciphertexts Are a Signal

Suppose a `countryCode` field has only two values:

```text
VN, VN, VN, VN, VN, US, VN, VN, US, VN
```

Deterministic encryption yields:

```text
VN -> CIPH_A
US -> CIPH_B

CIPH_A, CIPH_A, CIPH_A, CIPH_A, ...
```

Even without the DEK, an attacker sees **two value groups**, with one dominating. Knowing real-world distributions lets them infer values via **frequency analysis**.

Be especially cautious with:

- Statuses with 2–5 values;
- Countries, genders, or coarse income brackets;
- Booleans or verification flags;
- Any low-cardinality or heavily skewed field.

Never pick deterministic encryption merely because `find({field:value})` feels easier to write.

### 6.2. Deterministic Encryption Does Not Enforce Business Uniqueness

If emails must be unique, never assume “identical deterministic ciphertexts automatically prevent duplicates”. Uniqueness also depends on unique indexes, collations, normalization, sharding, and every client encrypting with identical rules, DEKs, and BSON types.

If clients use different keys or write plaintext directly, the same email can exist under multiple representations. Enforce business uniqueness with dedicated invariants, especially since QE uses randomized ciphertexts.

### 6.3. Fields That Should Never Use Deterministic Encryption

Fields never queried by value:

```javascript
{
  internalNote: "Private note",
  medicalHistory: { /* sensitive structured data */ },
  attachments: [ /* ... */ ]
}
```

are candidates for **randomized CSFLE** or QE `queryType: none`, depending on BSON types and storage needs.

CSFLE **does not support deterministic encryption of whole arrays or objects**, whereas randomized encryption can encrypt an entire array/object per schema rules. Once an entire object is encrypted as ciphertext, MongoDB cannot normally query subfields inside it.

## 7. Automatic vs. Explicit CSFLE

### 7.1. Automatic

With automatic CSFLE:

```text
Application:
    collection.insertOne({ passport: "A12345" })
                     |
                     v
    Driver + schemaMap + KMS
                     |
                 encrypt
                     |
                     v
MongoDB:
    { passport: BinData(encrypted subtype, ...) }
```

The application uses natural CRUD APIs; the driver reads encryption rules and encrypts matching fields.

A **client-controlled `schemaMap`** prevents a compromised server from altering remote schemas to downgrade client encryption. However, you must keep schemas aligned across all services writing to the collection.

### 7.2. Explicit

With explicit CSFLE, the application calls encryption directly:

```javascript
const ciphertext = await clientEncryption.encrypt(
  "ID-00991",
  {
    keyId: dataKeyId,
    algorithm:
      "AEAD_AES_256_CBC_HMAC_SHA_512-Deterministic"
  }
);

await db.collection("people").insertOne({
  tenantId: "ORG-A",
  nationalId: ciphertext
});
```

When reading:

```javascript
const raw = await db.collection("people").findOne({
  tenantId: "ORG-A"
});

const nationalId = await clientEncryption.decrypt(
  raw.nationalId
);
```

Its strength is explicit control over which fields get encrypted. Its weakness is **forgetting to encrypt on one write path** or **forgetting to decrypt on one read path**. Pair it with tests, code reviews, and server-side schema enforcement where possible.

### 7.3. Avoid Double Encryption

Never explicitly encrypt a field and then pass it through an automatic-encryption client configured to encrypt that same field without checking driver contracts—that can trigger errors or unintended double-processing.

Choose cleanly:

- **Automatic client:** application passes plaintext in memory; driver encrypts.
- **Explicit encryption:** application produces the encrypted BSON value and handles read/write paths directly.

When multiple services write to a collection, all writers must follow identical field, key, and encryption rules.

## 8. Hands-On Explicit CSFLE in Node.js

### 8.1. Environment Requirements

This lab uses a **test MongoDB deployment** supporting CSFLE, a compatible Node.js driver, and the encryption library. Use synthetic data only. Never run against real customer, financial, or personal records.

Install packages matching your driver version:

```bash
npm install mongodb mongodb-client-encryption
```

Installation and native libraries vary by OS, Node.js version, and driver; check compatibility docs for your version.

Supply a test MongoDB URI via `MONGODB_URI`. Never place connection strings containing passwords into source files or Git commits.

### 8.2. Complete Explicit Encryption Example

CommonJS code:

```javascript
const {
  MongoClient,
  ClientEncryption,
  ObjectId
} = require("mongodb");

const { randomBytes } = require("node:crypto");

async function main() {
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    throw new Error("MONGODB_URI is required");
  }

  const client = new MongoClient(uri);
  await client.connect();

  try {
    const db = client.db("mongo_encryption_row335_lab");
    const runId = new ObjectId().toHexString();

    // Create a dedicated namespace to avoid colliding with other data.
    const collectionName = "csfle_" + runId;
    const vaultName = "vault_" + runId;
    const collection = db.collection(collectionName);
    const vault = db.collection(vaultName);

    await vault.createIndex(
      { keyAltNames: 1 },
      { unique: true }
    );

    // Lab only: losing this key loses the ability to decrypt.
    const localMasterKey = randomBytes(96);

    const encryption = new ClientEncryption(client, {
      keyVaultNamespace: db.databaseName + "." + vaultName,
      kmsProviders: {
        local: { key: localMasterKey }
      }
    });

    const dataKeyId = await encryption.createDataKey(
      "local",
      { keyAltNames: ["row335-key-" + runId] }
    );

    const encryptCode = (value) =>
      encryption.encrypt(value, {
        keyId: dataKeyId,
        algorithm:
          "AEAD_AES_256_CBC_HMAC_SHA_512-Deterministic"
      });

    const encryptNote = (value) =>
      encryption.encrypt(value, {
        keyId: dataKeyId,
        algorithm:
          "AEAD_AES_256_CBC_HMAC_SHA_512-Random"
      });

    const value = "LAB-PRIVATE-ID-335";
    const encryptedCodeA = await encryptCode(value);
    const encryptedCodeB = await encryptCode(value);
    const encryptedNoteA = await encryptNote("Demo note");
    const encryptedNoteB = await encryptNote("Demo note");

    const fileId = new ObjectId();

    await collection.insertOne({
      _id: fileId,
      runId,
      publicLabel: "Lab customer",
      privateCode: encryptedCodeA,
      privateNote: encryptedNoteA
    });

    // Equality query: must encrypt the query value with the same rules.
    const hit = await collection.findOne({
      _id: fileId,
      privateCode: encryptedCodeB
    });

    if (!hit) {
      throw new Error("Cannot find encrypted document");
    }

    const decryptedCode = await encryption.decrypt(
      hit.privateCode
    );
    const decryptedNote = await encryption.decrypt(
      hit.privateNote
    );

    console.log({
      collectionName,
      runId,
      foundByDeterministicEquality: Boolean(hit),
      codeRoundTripCorrect: decryptedCode === value,
      noteRoundTripCorrect:
        decryptedNote === "Demo note",
      ciphertextIsBinary:
        hit.privateCode?._bsontype === "Binary"
    });

    // Never print real plaintext, ciphertext, or key material.
    // Cannot run equality queries on randomized privateNote.

    // Clean up only the record from this test run.
    const removed = await collection.deleteOne({
      _id: fileId,
      runId
    });
    console.log({ deleted: removed.deletedCount });

    // Lab collection/vault still remain. Only clean up via the lab
    // admin runbook after confirming DEKs/keys are no longer needed.
  } finally {
    await client.close();
  }
}

main().catch((error) => {
  console.error(error.name, error.message);
  process.exitCode = 1;
});
```

In this lab, `encryptedCodeA` and `encryptedCodeB` encrypt the same string with the same DEK, algorithm, and BSON type, making them usable for equality. Normally `encryptedNoteA`/`encryptedNoteB` yield distinct ciphertexts, yet both decrypt cleanly with the DEK.

**This is not a cryptographic audit.** Never treat comparing buffers in a small test as proof of algorithm strength; cryptographic properties come from specifications and drivers. Also never copy `localMasterKey` to logs. If records must be read by another process, manage keys securely—this lab intentionally uses an ephemeral key.

### 8.3. What Happens When a Client Lacks the Key?

A normal MongoDB client reading an encrypted field sees a **BSON Binary ciphertext**, not a plaintext string. Sending an unencrypted filter `privateCode: "LAB-PRIVATE-ID-335"` will fail to match the deterministic ciphertext.

Understand three distinct setups:

1. No encryption config: sees raw BSON ciphertext only.
2. Explicit encryption helper: app encrypts query filters and decrypts results itself.
3. Automatic encryption config: driver handles supported schemas and operations.

Never expect MongoDB Server to decrypt on the client's behalf.

## 9. How Does Queryable Encryption Work?

### 9.1. Key Difference from Deterministic Encryption

Deterministic CSFLE supports equality by producing identical ciphertexts for identical plaintexts. QE aims for **identical plaintexts producing distinct ciphertexts** while still allowing searches via **structured encrypted indexes** and dedicated query processing.

```text
Application searches nationalId = "ID-00991"
                    |
                    v
Driver + DEK + query analysis
                    |
    transforms query into tokens/structures
      supported by the QE protocol
                    |
                    v
MongoDB Server
   |
   +--- encrypted collection documents
   +--- encrypted state metadata (ESC)
   +--- encrypted compaction metadata (ECOC)
   +--- __safeContent__ in documents
                    |
             select candidates
                    |
                    v
       return encrypted documents
                    |
                    v
         Driver decrypts for app
```

Never conclude the server sees plaintext merely because it executes searches. Conversely, never promise the query structure leaks **zero** information under every threat model.

### 9.2. Metadata Collections and System Fields

For a collection `patients`, QE may create:

```text
patients
enxcol_.patients.esc
enxcol_.patients.ecoc
```

Definitions:

- **ESC (Encrypted State Collection)**: metadata supporting indexes/queries on encrypted data.
- **ECOC (Encrypted Compaction Collection)**: metadata supporting management/compaction.
- **`__safeContent__`**: QE-managed field inside encrypted documents used for query indexing.

**Never directly edit, delete, rename, backfill, or manually create `__safeContent__`/ESC/ECOC.** MongoDB docs warn this corrupts query results and undermines security.

### 9.3. Overhead Compared to Plain Collections

For a single equality-indexed field, one insert can trigger writes to the main collection **plus two metadata collections**. Indexing more fields multiplies overhead proportionally.

MongoDB documentation notes an encrypted collection may use roughly **2–3x storage** compared to an unencrypted collection in some scenarios; that is not a fixed constant for every workload.

Range and partial-string queries carry different setups and costs than equality. Always benchmark with **realistic data and value distributions**, not just 10 demo documents.

## 10. Defining a QE Encrypted Schema

### 10.1. `encryptedFields` and `fields`

Example:

```javascript
const encryptedFields = {
  fields: [
    {
      path: "nationalId",
      bsonType: "string",
      queries: {
        queryType: "equality"
      }
    },
    {
      path: "incomeVnd",
      bsonType: "long",
      queries: {
        queryType: "range",
        min: Long.fromNumber(0),
        max: Long.fromNumber(1000000000)
      }
    },
    {
      path: "internalNote",
      bsonType: "string"
      // No queries => encrypted, not queryable.
    }
  ]
};
```

This is a **design template**; executing it requires driver/BSON `Long`, key vault/KMS, permissions, and collection creation through QE workflows. A `keyId` can reference a valid DEK UUID, or `createEncryptedCollection()` can generate DEKs for fields omitting `keyId`.

### 10.2. Granting Queryability per Field

With:

```javascript
{
  path: "nationalId",
  bsonType: "string",
  queries: { queryType: "equality" }
}
```

a properly configured app can run:

```javascript
await encryptedCollection.findOne({
  nationalId: "ID-00991"
});
```

The driver detects the comparison on the encrypted field and rewrites it per the QE protocol.

If a field only declares:

```javascript
{
  path: "internalNote",
  bsonType: "string"
}
```

the driver encrypts/decrypts it, **but cannot run equality queries on its plaintext** through QE.

### 10.3. You Cannot Arbitrarily Enable Every Query Type on One Field

Per MongoDB 9.0 docs:

- Queryable fields use an appropriate equality/range configuration rather than “enabling everything” arbitrarily.
- Prefix and suffix can be combined on the same field when configuration constraints are met.
- Substring **cannot be combined** with prefix/suffix on the same field.
- Each query type supports only specific BSON types.
- Query types are fixed when creating the encrypted collection; **you cannot edit the type on an existing field** expecting existing indexes to convert automatically.

Changing query capabilities requires creating a new encrypted collection and migrating per official procedures.

### 10.4. Never Encrypt `_id` with QE

QE does not allow configuring `_id` as an encrypted field. Design stable technical document IDs rather than placing sensitive plaintext in `_id` unnecessarily.

If a business key (such as national ID) must remain secret, use a technical `_id`, a separate encrypted field, and a compatible uniqueness architecture rather than a plaintext national ID `_id`.

## 11. QE Equality: Which Fields Fit?

### 11.1. Identifier Lookup Example

`nationalId` as a string:

```javascript
{
  path: "nationalId",
  bsonType: "string",
  queries: {
    queryType: "equality"
  }
}
```

The application can look up:

```javascript
await collection.findOne({
  nationalId: "ID-00991"
});
```

using a properly configured QE client.

Supported equality comparisons in MongoDB 9.0 include `$eq`, `$ne`, `$in`, `$nin`, and logical combinations per the supported operations list. Not every plaintext operator works with QE.

### 11.2. Never Confuse QE with a Unique Index

Two documents with identical `nationalId: "ID-00991"` get different ciphertexts under QE. **A unique index on an encrypted field's ciphertext does not enforce plaintext uniqueness.**

If a unique business key is required:

- Evaluate a separate **registry** holding normalized business keys or HMAC tokens with proper key management.
- Enforce uniqueness on an **indexable, properly partitioned** field/collection.
- Define tenant scope, canonicalization, and idempotency.
- Use transactions or atomic state machines to coordinate the registry with business documents.
- Restrict access to the registry, as lookup tokens/HMAC keys carry their own threat model.

Never store raw unsalted SHA-256 hashes of small-domain IDs as “secrets”; attackers can dictionary-attack them. Keyed HMACs with managed lifecycles and rotation offer stronger protection in lookup designs, subject to security review.

### 11.3. Nulls and Missing Fields

Current docs state QE does not support encrypting BSON `null`/`undefined`. Distinguish:

- **Omitted field**: document lacks the encrypted field, per schema/client rules.
- **`null` value**: cannot be encrypted as a string by default.
- **Empty string**: valid string type with distinct business meaning.
- **Wrong BSON type**: triggers encryption/validation errors.

When business logic needs an “unprovided” state, omit the field or track status in a separate field per policy. Never write `nationalId: null` into a strictly typed encrypted field expecting null equality queries to work.

## 12. QE Range: Numeric and Date Data

### 12.1. Capabilities from MongoDB 8.0 Onward

QE range queries support BSON types including:

- `date`.
- `int` / `long`.
- `double` / `decimal` under specific constraints.

Example querying records within an insurance amount range:

```javascript
{
  path: "premiumCents",
  bsonType: "long",
  queries: {
    queryType: "range",
    min: Long.fromNumber(0),
    max: Long.fromNumber(1000000000)
  }
}
```

Query:

```javascript
await encryptedCollection.find({
  premiumCents: {
    $gte: Long.fromNumber(20000000),
    $lt: Long.fromNumber(50000000)
  }
}).toArray();
```

Always use the **exact BSON type**. In Node.js, `Long.fromNumber()`/`Long.fromString()` avoids `int`/`double` mismatches; use safe conversion for values exceeding JS safe integers.

### 12.2. Bounds Impact Both Security and Performance

`min` and `max` define the **declared query domain**. MongoDB can reject queries outside bounds.

- Overly wide bounds inflate index/query costs.
- Overly narrow bounds block storing or querying legitimate future values.
- `double`/`decimal` require precision parameters per version.
- Range queries over sensitive data carry their own threat model; query transcripts can leak inferences in certain models.

Never pick `min`/`max` from this month's data alone without accounting for long-term growth.

### 12.3. Currency Types and Precision

For financial amounts, storing **smallest integer units** (cents/minor units within domain bounds) avoids floating-point bugs where feasible. When using `Decimal128`, verify:

- Which driver/server versions support encrypted range on `decimal`;
- Precision, `min`, and `max` settings;
- Serialization and comparison behavior;
- Guarantees that values stay within configured bounds.

Encryption never fixes bad data-type choices; a rounded-off amount before encryption stays wrong after decryption.

## 13. QE Prefix, Suffix, and Substring in MongoDB 9.0

### 13.1. GA Release and Matching Expressions

MongoDB 9.0 ships GA support for:

- **Prefix:** values starting with a string, using supported expressions like `$encStrStartsWith`.
- **Suffix:** values ending with a string, using `$encStrEndsWith`.
- **Substring:** substrings anywhere inside a value, using `$encStrContains`.
- **Normalized equality:** normalized matching via related configured expressions.

These are **QE queries on encrypted string fields**, **not MongoDB Search `$search`**. Do not infer text relevance scoring, stemming, fuzzy matching, or full-text indexing from substring support.

### 13.2. Length Limits Are Critical

For `substring` in 9.0:

- Indexed string fields have **`strMaxLength` between 2 and 50** per configuration.
- Queried substrings range from **2 to 6 characters** under `strMinQueryLength`/`strMaxQueryLength` limits.
- Arbitrary-length substring queries like plaintext regexes are not supported.
- These limits govern storage, write cost, queryability, and migration.

For prefix/suffix, query lengths must obey the query type and version bounds.

For example, bounded-length `nationalId` values can fit certain partial-match cases, whereas a multi-thousand-character `internalNote` **is not** a valid fit for 50-character-capped QE substring queries.

### 13.3. Case Sensitivity, Diacritics, and Vietnamese Text

String query types support `caseSensitive` and `diacriticSensitive` options per 9.0 documentation.

For instance, matching `"nguyen"` with `"Nguyễn"` requires:

1. Defining exact Unicode/case/diacritic equivalence rules.
2. Evaluating false-positive impact.
3. Configuring index and query options **before creating the collection**.
4. Testing against real Vietnamese strings and accented/unaccented identifiers.
5. Never expecting standard collations to automatically fix ciphertext comparisons.

**QE does not apply standard collations like a plaintext field**; the server cannot apply a general collation to ciphertext and yield expected results.

### 13.4. Public Preview 8.2/8.3 Differs from 9.0 GA

Per MongoDB 9.0 release notes, `prefixPreview`/`suffixPreview`/`substringPreview` from public previews are **not directly compatible** with the GA mechanism. If currently on 8.2/8.3:

- Do not swap driver/server binaries and run blindly without a plan.
- Check migration or new-collection creation procedures.
- Verify decrypt/read/write/query against the exact compatibility matrix.
- Keep rollback plans and key/metadata backups.

Never mix preview code snippets with current 9.0 libraries.

## 14. QE Limitations to Design Around

### 14.1. BSON Types

Overview per current documentation:

| Query Type | Typical Supported BSON Types |
| --- | --- |
| `equality` | Most common BSON types, **excluding** array/object/double/decimal |
| `range` | date, int, long, double, decimal |
| `prefix/suffix/substring` | string |
| `none` | Can encrypt whole arrays/objects, without querying inside them |
| Excluded from query types | null, undefined, MinKey, MaxKey |

Additional note: you cannot arbitrarily encrypt fields **inside array elements** and query them like ordinary subfields. Check whole-field encryption rules and type constraints if using arrays or objects.

### 14.2. CRUD and Operators

Queryable Encryption supports only a **subset** of commands and operators. Per current docs:

- `updateMany()` and `deleteMany()` are unsupported on QE collections per listed semantics.
- `bulkWrite` and `findAndModify` carry specific restrictions.
- Certain aggregation stages and expressions cannot operate on encrypted fields.
- `$regex` on encrypted fields does not work like plaintext string search.
- Queries comparing against `null` or disallowed types fail.
- `$text`, `$where`, and `$jsonSchema` face restrictions or rejection through QE automatic clients.
- Upserts have special behavior: **encrypted fields in the filter may not carry over into inserted documents**; construct inserted documents explicitly.

Read **Supported Operations for Queryable Encryption** for your exact server/driver before shipping to production—never stop after testing only `insert` and `findOne`.

### 14.3. Collections and Indexes

MongoDB docs state these QE constraints:

- **Applies only to newly created QE collections**; you cannot enable QE by editing a populated collection's schema expecting existing records to encrypt automatically.
- You cannot change an encrypted field's `queryType` on an existing collection.
- You cannot rename encrypted fields or collections via standard `$rename`/`renameCollection`.
- You cannot mix CSFLE and QE on the same collection.
- Special collection types such as **time-series, capped, and views** are unsupported in current cases.
- **TTL and unique indexes** carry strict limits; unique indexes on encrypted fields **do not enforce plaintext uniqueness**.
- Never create a standard B-tree index on a QE encrypted field expecting it to act as a queryable index.
- Never delete or manually create QE metadata collections.

Many deployments require verifying the `__safeContent__` index created by the driver/collection setup workflow.

### 14.4. Sharding, Read Preferences, and Transactions

For QE on a sharded cluster, evaluate:

- Topology/FCV and `mongos`/shard support.
- Whether encrypted fields are compatible with shard key needs.
- Differences between server-side uniqueness and encrypted field uniqueness.
- Restrictions on secondary reads and certain transaction/CRUD operators.
- Placement and backup of QE metadata collections.
- Impact of migrations or resharding on encryption metadata.

Never use a plaintext sensitive identifier as a shard key solely for targeted routing without weighing exposure risks. Likewise, never assume hashed/unique indexes on ciphertext deliver plaintext semantics.

## 15. Hands-On Automatic Queryable Encryption in Node.js

### 15.1. Strict Prerequisites Before Running

This example requires:

- A **MongoDB Atlas or Enterprise test deployment** supporting automatic QE.
- A compatible replica set or sharded cluster.
- Compatible Node.js MongoDB driver + `mongodb-client-encryption`.
- **Automatic Encryption Shared Library (`crypt_shared`)** matching version and platform.
- Permissions to create namespaces, the Key Vault, and metadata collections.
- A local KMS key **for lab use only**—never production.
- A fresh collection name per run without overwriting existing collections.

If prerequisites are missing, **do not run** and manually hack collections to “force QE to work”. Study the schema and docs first, then run on a properly provisioned lab.

### 15.2. Sample Code with an Equality Field

Set `MONGODB_URI` and `CRYPT_SHARED_LIB_PATH` for your test environment. Sequence:

1. Connect a test admin client.
2. Create the Key Vault with a unique index on aliases.
3. Instantiate `ClientEncryption`.
4. Create the QE collection via `createEncryptedCollection()` to generate DEKs and metadata.
5. Create an encrypted `MongoClient` with `encryptedFieldsMap`, KMS options, and `crypt_shared`.
6. Insert/query plaintext on the client; ciphertext is stored on the server.

```javascript
const {
  MongoClient,
  ClientEncryption,
  ObjectId
} = require("mongodb");

const { randomBytes } = require("node:crypto");

async function runQueryableEncryptionLab() {
  const uri = process.env.MONGODB_URI;
  const cryptSharedLibPath =
    process.env.CRYPT_SHARED_LIB_PATH;

  if (!uri || !cryptSharedLibPath) {
    throw new Error(
      "Need MONGODB_URI and CRYPT_SHARED_LIB_PATH"
    );
  }

  const admin = new MongoClient(uri);
  await admin.connect();

  let encryptedClient;

  try {
    const dbName = "mongo_encryption_row335_lab";
    const runId = new ObjectId().toHexString();
    const collectionName = "qe_" + runId;
    const keyVaultCollection = "vault_qe_" + runId;
    const keyVaultNamespace =
      dbName + "." + keyVaultCollection;
    const namespace = dbName + "." + collectionName;

    const db = admin.db(dbName);
    const vault = db.collection(keyVaultCollection);

    await vault.createIndex(
      { keyAltNames: 1 },
      { unique: true }
    );

    const kmsProviders = {
      local: {
        key: randomBytes(96)
      }
    };

    const clientEncryption = new ClientEncryption(admin, {
      keyVaultNamespace,
      kmsProviders
    });

    const requestedEncryptedFields = {
      fields: [
        {
          path: "privateCode",
          bsonType: "string",
          queries: { queryType: "equality" }
        },
        {
          path: "privateNote",
          bsonType: "string"
          // encrypt, but not queryable
        }
      ]
    };

    // Helper properly creates DEKs and metadata collections.
    const created =
      await clientEncryption.createEncryptedCollection(
        db,
        collectionName,
        {
          provider: "local",
          createCollectionOptions: {
            encryptedFields: requestedEncryptedFields
          }
        }
      );

    // created.encryptedFields includes generated keyIds.
    const finalEncryptedFields = created.encryptedFields;

    encryptedClient = new MongoClient(uri, {
      autoEncryption: {
        keyVaultNamespace,
        kmsProviders,
        encryptedFieldsMap: {
          [namespace]: finalEncryptedFields
        },
        extraOptions: {
          cryptSharedLibPath
        }
      }
    });

    await encryptedClient.connect();

    const encryptedCollection = encryptedClient
      .db(dbName)
      .collection(collectionName);

    const id = new ObjectId();

    await encryptedCollection.insertOne({
      _id: id,
      runId,
      publicLabel: "Sample QE record",
      privateCode: "DEMO-SECRET-335",
      privateNote: "Read only after lookup by _id"
    });

    // Automatic QE: driver transforms the equality filter.
    const hit = await encryptedCollection.findOne({
      privateCode: "DEMO-SECRET-335"
    });

    if (!hit || !hit._id.equals(id)) {
      throw new Error("QE equality lookup failed");
    }

    // Plain client without KMS sees Binary ciphertext.
    const raw = await admin
      .db(dbName)
      .collection(collectionName)
      .findOne({ _id: id });

    console.log({
      namespace,
      foundByEncryptedEquality: true,
      decryptedCodeMatches:
        hit.privateCode === "DEMO-SECRET-335",
      rawCodeIsBinary:
        raw.privateCode?._bsontype === "Binary",
      rawNoteIsBinary:
        raw.privateNote?._bsontype === "Binary"
    });

    // Never log sensitive content, local key, or DEK.
    // Do not drop encrypted collections/metadata inside the demo.
  } finally {
    if (encryptedClient) {
      await encryptedClient.close();
    }
    await admin.close();
  }
}

runQueryableEncryptionLab().catch((error) => {
  console.error(error.name, error.message);
  process.exitCode = 1;
});
```

**Demo scope limit:** the script does not automatically delete encrypted metadata collections and Key Vaults afterward. Creating new lab collections consumes storage; admins should clean up the **exact namespace and related metadata** using a QE-compatible driver once confirmed DEKs are no longer needed. Never run `dropDatabase()`/`drop()` arbitrarily on shared databases.

### 15.3. Key Mechanics Explained

- `requestedEncryptedFields` is the **intended schema** declared by the app.
- `createEncryptedCollection()` creates the collection properly, generates `keyId`s when omitted, and initializes metadata/indexes.
- `encryptedFieldsMap` ensures the encrypted client enforces the chosen schema rather than trusting unverified remote schemas.
- `kmsProviders.local` is lab-only, with no CMK backup.
- `cryptSharedLibPath` points to the valid cryptographic/query-analysis binary library.
- `insertOne()` accepts plaintext **on the client**, while the server receives ciphertext.
- `findOne({privateCode: ...})` works solely via client-side QE query rewriting; an unconfigured client cannot query plaintext.
- A raw MongoDB client sees ciphertext and cannot decrypt it.
- Never create ordinary B-tree indexes on `privateCode` trying to “speed up QE”; QE uses its own metadata/index mechanism.

### 15.4. Troubleshooting Collection Creation Errors

Common causes:

- Incompatible server/driver/`crypt_shared` versions.
- Running standalone or Community without automatic QE.
- Missing permissions to create Key Vaults, collections, or indexes.
- Insufficient KMS permissions to create or unwrap DEKs.
- Colliding collection/metadata names from an earlier run.
- Invalid `encryptedFields` schema or BSON types.
- Network/firewall blocking KMS calls.
- Collection already exists or was created outside the QE workflow.
- Key Vault missing unique index on `keyAltNames`.

Inspect the **error code/message**, namespace, and permissions. Never manually edit ESC/ECOC or `__safeContent__` to bypass errors.

## 16. Protecting Schemas and Access Permissions

### 16.1. Why Enforce Schemas on the Client?

A client relying purely on server-supplied schemas is exposed if an attacker alters server-side config or the app connects to the wrong deployment. Therefore, keep `schemaMap`/`encryptedFieldsMap` **in versioned, controlled application configuration** where appropriate.

Version configs and test them:

```text
encryptionConfigVersion: enc-v3
collection: people_secure_v3
encryptedFields:
  - nationalId: equality, string
  - incomeCents: range, long
  - internalNote: none, string
```

Never let two writer services target the same namespace with one encrypting `nationalId` while the other writes plaintext. If legacy records exist, migrate and block plaintext writes via server/driver controls.

### 16.2. Encryption Does Not Replace RBAC/Authorization

A client holding a DEK can still read plaintext fields. You still need:

- Authenticated users.
- Authorization by tenant, document, and purpose.
- Decryption roles restricted per service.
- Separation of ingestion writers, read services, key admins, and DB admins.
- Audits for KMS decrypt/unwrap, key edits, and data access.
- Redaction of ciphertext/decrypted values in logs, exceptions, and traces.
- Avoiding placing plaintext in `metadata` fields or `_id` outside your threat model.

Encryption restricts **who can read plaintext from the database**, not **who is allowed to call an API**.

### 16.3. KMS IAM and Networking

Applications need KMS access to unwrap DEKs. Production policies should:

- Use short-lived/managed identities rather than hardcoded credentials.
- Scope decrypt/rewrap permissions per environment/collection/tenant.
- Separate sandbox and production CMKs.
- Strictly restrict who can disable/delete CMKs.
- Monitor KMS failures and throttling.
- Define handling for KMS unavailability or expired credentials.
- Plan restore and rotation early.

Never assume KMS is only called once at startup: new clients, cold caches, key refreshes, or failovers all need to unwrap keys.

## 17. Key Rotation: More Than Swapping an Environment Variable

### 17.1. CMK Rotation Differs from DEK Rotation

**CMK rotation / rewrap:**

- Rotates the wrapping key in KMS per supported procedures.
- DEKs can be **rewrapped** under the new CMK without re-encrypting all plaintext data.
- In Node.js, `rewrapManyDataKey()` provides this via compatible driver APIs.

**DEK rotation / re-encrypt:**

- Replacing the actual DEK encrypting fields requires reading old ciphertexts, decrypting with the old key, and re-encrypting with a new DEK via a controlled migration/validation process.
- QE maintains query metadata tied to the encrypted collection/keys; you cannot arbitrarily swap `keyId` in an old schema expecting all records and query tokens to update automatically.

Never treat changing a CMK ARN or deleting an old DEK as a “completed rotation”.

### 17.2. Conceptual Rewrap Runbook

```text
Inventory: CMKs, DEKs, collections, keyAltNames
                    |
       Create/authorize new CMK
                    |
          Rewrap DEKs as supported
                    |
         Validate decrypt with clients
                    |
         Keep old CMK during retention
                    |
         Backup + restore test
                    |
      Retire old material only if safe
```

Documentation notes `rewrapManyDataKey()` swaps the CMK wrapping layer **without changing the DEK value**. An old CMK may still be needed by unrewrapped DEKs, snapshots, or archived backups.

### 17.3. Rotation and Data Erasure

Destroying CMKs/DEKs for “cryptographic erasure” requires strict review:

- Losing keys can make legitimate data unreadable.
- Data may already have been decrypted/copied to caches or logs.
- Older backups may need historical keys.
- Legal rules may require retention.
- Downstream systems may hold plaintext copies.

Never bulk-destroy keys as casual routine housekeeping.

## 18. Backup, Restore, and Migration

### 18.1. Backups Must Include Every Dependent Component

For CSFLE:

- Business collection ciphertexts.
- Key Vault containing wrapped DEKs.
- Active CMK access via KMS.
- Schema configs and driver versions.

For QE additionally:

- Main encrypted collection.
- Associated ESC and ECOC metadata collections.
- Server/driver-managed `__safeContent__`.
- `encryptedFields` definition/metadata.
- KMS/Key Vault and driver compatibility.

Restoring only the main collection without QE metadata collections causes **encrypted queries to return wrong results**, even when ciphertexts remain intact.

### 18.2. Never Enable QE by Editing an Existing Schema

Common mistake:

```text
Existing collection:
  1,000,000 plaintext documents

Developer:
  add encryptedFieldsMap to client

Expectation:
  old 1,000,000 docs become encrypted automatically
```

This **does not happen**. If new clients encrypt subsequent writes, the collection mixes plaintext and ciphertext. QE encrypted queries will not match legacy plaintext records.

Controlled migration plan:

1. Design the encrypted schema and query requirements.
2. Create a **new QE collection** using the proper driver/helper.
3. Define retention, uniqueness, and permissions.
4. Read source records through a controlled path.
5. Validate and normalize exact BSON types.
6. Write documents/batches into the new collection via an encryption-enabled client.
7. Monitor progress, errors, counts, and authorized samples.
8. Coordinate concurrent writes during migration (controlled quiesce/dual-write/outbox).
9. Cut over reads/writes via feature flags/cutover plan.
10. Preserve rollback and retain old keys/metadata until verified.

**Never** treat this as a simple `updateMany({$set:{...}})`: QE imposes limits on multi-document updates, schema changes, and metadata.

### 18.3. Never Migrate QE by Copying Raw Ciphertext

Copying `BinData` ciphertexts from one encrypted collection to another without creating/rebuilding matching metadata leaves **the target collection's queryable index missing required state**.

Migrations must follow MongoDB-supported workflows—typically **decrypting on an authorized client and re-encrypting into the new collection** under the target schema/keys. Protect plaintext in memory throughout; never write plaintext to staging files or logs.

### 18.4. Never Change Type/queryType In-Place

In QE, a field's query type is fixed at collection creation. Moving from `equality` to `range` or adding partial-match requires **planning a migration**, not editing a config object and restarting clients.

## 19. Metadata Compaction and QE Overhead

### 19.1. Why Do ESC/ECOC Grow Over Time?

QE tracks metadata to support querying encrypted fields. Writes grow those metadata collections. Simple illustration:

```text
main collection:
   1 document with 2 queryable encrypted fields

QE metadata:
   additional entries/writes in ESC and ECOC
```

Every insert or update on encrypted fields costs more than a plain MongoDB insert. More queryable fields multiply the cost.

### 19.2. Compaction Is a Conditional Admin Operation

MongoDB provides **structured metadata compaction/cleanup** to bound ESC/ECOC size via dedicated procedures, subject to version, privilege, encrypted-client, and performance constraints.

Never run:

```javascript
// DANGEROUS: corrupts QE metadata.
db.getCollection("enxcol_.people.esc").deleteMany({});
db.getCollection("enxcol_.people.ecoc").drop();
```

Instead:

- Monitor ESC/ECOC sizes.
- Consult `compactStructuredEncryptionData` docs and QE admin procedures for your exact version.
- Schedule outside peak traffic when impactful.
- Back up and validate before and after.
- Ensure KMS access and an encryption-configured connection.
- Never run compaction commands without understanding version semantics.

### 19.3. Compaction Also Has Security Trade-Offs

MongoDB docs note that under certain threat models, compaction can reveal statistical information about field/value combinations occurring between compaction runs. Schedule compaction weighing **storage/performance goals against your threat model**, rather than running it on an overly aggressive cron.

### 19.4. Tuning Parameters

QE tuning parameters include:

- `contention`: trades write throughput on repeated values against `find` performance.
- Range `min`/`max`/`precision`: governs bounds and overhead.
- `sparsity`/`trimFactor`: advanced parameters per query type and version.
- `strMaxLength`/`strMinQueryLength`/`strMaxQueryLength` for partial strings.

Never copy tuning numbers from an old blog post to production without measuring. These parameters affect both security and performance, create distinct schemas/indexes, and often cannot be changed once data exists.

## 20. Performance, Scalability, and Monitoring

### 20.1. Baseline Before Enabling Encryption

Measure on a representative workload:

| Metric | Why It Matters |
| --- | --- |
| p50/p95/p99 insert latency | Captures key-access and QE metadata write overhead |
| p50/p95/p99 equality/range query latency | Identifies expensive query shapes |
| Query throughput/QPS | Verifies post-encryption capacity |
| Client CPU | Crypto and query analysis are not free |
| MongoDB CPU/disk/network | Encrypted payloads and metadata increase load |
| KMS request rate/latency | Exposes cold key-cache and network impacts |
| Key unwrap failures | Surfaces KMS permission/availability faults |
| ESC/ECOC size growth | Signals compaction/sizing needs |
| Write conflicts/timeouts | Reveals contention on low-cardinality fields |
| Memory/driver pools | Tracks service connection/cache/CPU growth |
| Backup/restore duration | Accounts for extra metadata, keys, and larger data |

Never claim “QE is X% slower” without benchmarking your exact corpus, query mix, and topology.

### 20.2. Note Redacted Query Diagnostics

MongoDB QE **redacts/omits** certain details from query logs, the profiler, and diagnostic commands to prevent leakage. Therefore:

- Some queries do not appear in the profiler as in plain MongoDB.
- `collStats`, `currentOp`, and related outputs may omit or redact fields.
- Operations teams need **application-level APM metrics** by operation, query class, tenant tier, and index version—without logging raw plaintext.
- Never try disabling redaction or logging plaintext queries just to make debugging easier.

### 20.3. Safe Trace Example

Illustrative record:

```json
{
  "traceId": "tr-335",
  "collection": "people_secure",
  "operation": "encrypted-equality-lookup",
  "queryClass": "national-id-exact",
  "success": true,
  "latencyMs": 85,
  "kmsLatencyMs": 12,
  "keyAliasClass": "tenant-level"
}
```

Never log national IDs, encrypted payloads, raw query tokens, key material, full encrypted schemas containing secrets, or KMS credentials. Even ciphertexts and query transcripts can be sensitive under certain threat models.

### 20.4. Metadata Capacity

Queryable field counts and insert/update rates can grow ESC/ECOC rapidly. Avoid:

- Encrypting/indexing every field just because it feels “safer”;
- Using `range` on fields needing only `equality`;
- Using `substring` on long descriptions;
- Indexing low-cardinality fields with heavy write hotspots without tuning `contention`;
- Running bulk migrations at full throttle without sizing ESC/ECOC first.

## 21. Common Errors and Investigation

### 21.1. Cannot Decrypt a Field

Possible causes:

- Wrong KMS/CMK or expired credentials.
- Wrong Key Vault namespace.
- Required key ID was deleted.
- Key Vault was not restored alongside data.
- Driver/encryption library mismatch.
- Client uses a mismatched encryption schema.
- Ciphertext was altered or corrupted.
- Network path to KMS is blocked.

Never troubleshoot by printing CMKs/DEKs to logs or disabling encryption. Check error codes, namespaces/`keyId`s, KMS audits, and restore credentials.

### 21.2. QE Find Returns Empty Despite Matching Documents in MongoDB

Verify:

1. Was data inserted via the encrypted client or a raw client?
2. Was the QE collection created properly before inserting?
3. Does `encryptedFieldsMap` match the server definition?
4. Does the field's query type support the operator used?
5. Does the query input match the exact BSON type?
6. Is the encrypted field null or missing?
7. Did a tenant/status filter exclude the document?
8. Were ESC/ECOC/`__safeContent__` modified manually?
9. Are driver, `crypt_shared`, and FCV compatible?
10. Is replication lag or a migration cutover in progress?

Never blame the MongoDB query engine when unencrypted values fail to match ciphertexts.

### 21.3. “Duplicates” on Encrypted nationalId

Because QE produces randomized ciphertexts, a unique index on that field **does not enforce plaintext uniqueness**. Solve uniqueness via a business-key registry/contract before deploying.

### 21.4. Schema Errors Writing Encrypted Fields

Possible causes:

- Field holds an unencryptable BSON type.
- String/number type mismatches schema.
- Value falls outside range bounds.
- Disallowed `null`/`undefined`.
- Partial-string length exceeds configured limits.
- Collection's `encryptedFields` query type differs from client config.
- Unsupported update operator used.

Never patch ciphertext fields manually. Fix the data contract or migrate the collection per policy.

### 21.5. Changing Encrypted Schema Yields Wrong Results

MongoDB docs warn that changing `encryptedFieldsMap` on an existing collection creates **old plaintext docs mixed with new encrypted docs** and inconsistent queries. Fix by rolling back config or running a controlled migration—never add a temporary “unencrypted bypass” config just to query data out.

### 21.6. KMS Outage

When KMS is unavailable:

- Clients with cached DEKs may keep running within cache lifetimes.
- Newly started clients or uncached keys fail.
- Encrypt/decrypt error rates climb.
- Retries must use backoff to avoid a thundering herd against KMS.
- Never fall back to storing plaintext just to keep the app up.

Implement circuit breakers, observability, and safe degraded modes—such as keeping endpoints that do not touch encrypted fields operational.

## 22. Production Deployment Workflow

### 22.1. Classify Data First

Build a field map:

| Field | Sensitive? | Required Queries | Guidance |
| --- | --- | --- | --- |
| Technical `_id` | No PII | Lookup by ID | Keep plaintext, random ID |
| `tenantId` | May reveal org info | Authorization filters | Assess leakage; often plaintext with access control |
| `nationalId` | Highly sensitive | Exact lookup | QE equality or reviewed lookup architecture |
| `incomeCents` | Sensitive | Value ranges | QE range on compatible MongoDB |
| `internalNote` | Highly sensitive | No content search | Randomized CSFLE or QE `none` |
| `status` | Low cardinality | Frequent filtering | Avoid deterministic CSFLE by habit; analyze threat model |
| `updatedAt` | Operational metadata | Sort/time windows | Consider plaintext or QE range if strictly required |

Crucially, **leaving a field plaintext** when needed for querying/sorting is an intentional decision—not every field shares identical sensitivity.

### 22.2. Preflight

- Align on threat model and regulatory mandates.
- Choose CSFLE or QE per collection (never mix both on one collection).
- Lock down query types and BSON types per field.
- Verify version/FCV/driver/`crypt_shared`/edition compatibility.
- Select remote KMS, IAM, region, recovery, and key rotation.
- Design a dedicated Key Vault with strict permissions and unique alias index.
- Address business uniqueness invariants separately.
- Test compatibility across all read/write/update/upsert/bulk/aggregation APIs.
- Size storage/CPU/network/KMS capacity and backups.
- Design migrations if collections already hold data.

### 22.3. Staging

- Use synthetic/anonymized data with realistic distributions.
- Create the new encrypted collection via supported helpers/drivers.
- Measure equality/range/partial-match latency.
- Test missing fields, nulls, and wrong BSON types.
- Test expired KMS credentials, client restarts, and primary failovers.
- Test Key Vault restores and decryption via authorized clients.
- Run negative tests for raw clients and unauthorized tenants.
- Reconcile record counts and business keys pre/post-migration.
- Verify **zero plaintext** exists inside raw documents for encrypted fields.

### 22.4. Rollout

```text
Design fields + queries + KMS
             |
             v
Provision Key Vault + roles
             |
             v
Create new encrypted collection
             |
             v
Migrate / backfill carefully
             |
             v
Shadow reads + consistency checks
             |
             v
Canary traffic / feature flag
             |
             v
Monitor latency, correctness, KMS
             |
             v
Cutover
             |
             v
Retain old data/keys for rollback
             |
             v
Retire only after review
```

If a canary fails, rollback must revert **both `encryptedFields`/query template configs and data routing** compatibly. Simply renaming a collection is not enough.

### 22.5. Incident Response

If plaintext or secrets leak:

1. Isolate the leak path and lock down access scopes.
2. Identify affected data, keys, query logs, and services.
3. Block further use of compromised credentials.
4. Plan appropriate key rotation/migration without impulsively destroying keys and losing data.
5. Restore service with secure IAM and key material.
6. Reconcile data integrity and audit access.
7. Execute compliance/notification workflows if applicable.
8. Add tests and controls to prevent recurrence.

Never call `rewrapManyDataKey()` and declare safety if a **DEK, plaintext, or application process** was compromised. Rewrapping the CMK does not replace the DEK or erase stolen plaintext.

## 23. Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| “TLS hides data from DBAs” | TLS only protects transit; authorized DBAs can read plaintext without client-side encryption |
| “Encryption at rest equals CSFLE” | They are distinct complementary layers |
| “Deterministic CSFLE has no leakage” | Identical plaintexts yield identical ciphertexts, risking frequency analysis |
| “Randomized CSFLE still supports `find({secret:value})`” | No; randomized encrypted fields cannot be queried directly by value |
| “QE ciphertexts are randomized so they aren't queryable” | QE uses encrypted queryable indexes and a dedicated protocol |
| “QE supports every MongoDB operator” | Only a documented subset per query type/server/driver |
| “MongoDB 7.0 has QE range GA” | Range requires MongoDB 8.0 or later |
| “Prefix/suffix/substring was GA in 8.2” | 8.2/8.3 Public Preview differs from 9.0 GA |
| “QE substring is full-text search” | Bounded short strings only; does not replace Search relevance |
| “Unique indexes on QE fields prevent plaintext duplicates” | Randomized ciphertexts do not enforce plaintext uniqueness |
| “Just add `encryptedFieldsMap` to an existing collection” | Does not migrate existing documents |
| “Query types can be changed on a live collection” | Query types are fixed at creation; migration is required |
| “Use both QE and CSFLE on one collection for extra safety” | QE docs do not support mixing both on the same collection |
| “Drop ESC/ECOC to save disk space” | Breaks encrypted queries or corrupts data |
| “Metadata compaction is just `deleteMany`” | Must use dedicated QE commands |
| “DEKs are stored in plaintext in MongoDB” | The Key Vault stores CMK-wrapped DEKs |
| “Backing up data alone is enough” | Must back up Key Vault and preserve CMK recovery |
| “Rotating the CMK re-encrypts old records with new DEKs” | CMK rotation/rewrap differs from DEK re-encryption |
| “Fall back to plaintext temporarily if KMS is down” | Violates security requirements; fail safely instead |
| “Encryption replaces authorization” | Clients with keys still need tenant/document authorization |
| “QE logs/profiler match plain collections” | Diagnostics are partially redacted/omitted |
| “Every encrypted field should be indexed” | Queryable fields increase overhead and leakage trade-offs |
| “Encrypted field queries use standard collations” | QE restricts collations; string queries use dedicated options |
| “Local-key test setups work for production” | Production requires remote KMS and proper key governance |

## 24. Design and Practice Exercises

### Exercise A. Choosing the Right Mechanism

An app stores:

```javascript
{
  taxId: "...",
  countryCode: "VN",
  creditLimitCents: NumberLong("350000000"),
  privateMemo: "...",
  tenantId: "T1"
}
```

Requirements:

1. Exact lookup by `taxId`.
2. Range filtering on `creditLimitCents`.
3. Display `privateMemo` when opening a document; never search by it.
4. Strict tenant filtering and authorization.
5. Millions of records with some low-cardinality fields.

Select deterministic/randomized CSFLE or the appropriate QE query type for each field. Explain security/performance/uniqueness trade-offs and minimum MongoDB versions.

### Exercise B. Frequency Analysis

A `riskLevel` field only takes `LOW` and `HIGH`, with 95% of rows `LOW`.

- Why is deterministic CSFLE risky?
- Should you use randomized encryption if the app never queries by `riskLevel`?
- If filtering on it is required, how do you evaluate threat model and performance?
- Does QE eliminate all information leakage in every scenario?

### Exercise C. CMK, DEK, and Key Vault

Draw the diagram:

```text
Remote KMS -> CMK -> wrapped DEK in Key Vault
                          |
                          v
                   encrypted field
```

Explain the consequences of:

- Losing the CMK.
- Accidentally deleting the DEK.
- Backing up only the main collection without the Key Vault.
- Rotating the CMK without rewrapping older DEKs.
- A client holding KMS credentials yet lacking collection read access.

### Exercise D. Equality and Uniqueness

Two documents with identical plaintext `taxId` are written using QE equality:

- Must their ciphertexts match?
- Does a unique index on the encrypted field guarantee business uniqueness?
- How can a protected lookup registry/key be designed?
- Why is raw SHA-256 of a guessable ID risky?

### Exercise E. Query Types by Version

An engineering team runs MongoDB 7.0 and wants:

1. Equality on an encrypted string.
2. Range on encrypted income.
3. Substring queries on a 200-character encrypted string.

Identify what works immediately, what requires upgrading or redesigning, and why 9.0 QE substring imposes length caps.

### Exercise F. Migrating a Legacy Collection

`people` currently holds 1 million plaintext documents. A developer proposes adding `encryptedFieldsMap` and restarting the app.

- What happens to legacy documents?
- Why will encrypted equality queries miss documents?
- How would you design migration to `people_encrypted_v2`?
- Must `_id`, uniqueness, references, and backups be preserved?
- How do you prevent lost writes during cutover?

### Exercise G. Key Rotation

An organization rotates its CMK annually.

- Distinguish KMS rotation from `rewrapManyDataKey()`.
- After rewrapping, must all data be re-encrypted immediately?
- If an attacker steals a plaintext DEK, is rewrapping under a new CMK enough?
- Why retain decryption access for older snapshots/backups?
- Who should hold key-administration privileges?

### Exercise H. Metadata and Performance

A collection has 3 QE fields, inserts jump 10x after a marketing campaign, and ESC/ECOC grow rapidly.

- Why did write volume surge?
- Which metrics should you measure?
- When should you consider metadata compaction?
- Why must you never `drop()` ESC/ECOC?
- How do `contention` and range bounds affect behavior?

### Exercise I. Application Security Scenario

A service holds KMS decrypt rights and can read the entire collection. An API accepts `tenantId` from the query string and returns decrypted records.

- Does encryption automatically prevent cross-tenant data leaks?
- Where must authorization live?
- What must never be logged?
- Why separate ciphertext-read roles from decryption roles?

### Exercise J. Unsupported Queries

A developer tries running:

```javascript
await encryptedCollection.updateMany(
  { nationalId: { $regex: /^ID-/ } },
  { $set: { flag: true } }
);
```

- What is wrong regarding QE operators?
- What is wrong regarding multi-document updates?
- Why must you never edit ciphertexts manually?
- How would you redesign this safely with controlled authorization and throughput?

### Exercise K. QE Preview vs. GA

An environment uses QE `substringPreview` on MongoDB 8.3 and wants to upgrade to 9.0.

- Why is this not a fully backward-compatible minor upgrade?
- Which migration documentation must you read?
- When should you create a fresh encrypted collection?
- How should you test decryption, queries, KMS/drivers, and rollback?

### Exercise L. KMS Outage

Some pods keep querying via cache, while newly restarted pods fail decryption continuously.

- Why does that difference happen?
- Which metrics pinpoint KMS failures?
- Why is falling back to plaintext forbidden?
- How do you recover without logging key material or losing data?

## 25. Official Documentation and Applicability Notes

Encryption capabilities depend heavily on server version, driver version, cryptographic libraries, and KMS. Verify primary documentation before deploying:

- [Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/) — CSFLE introduction, automatic/explicit modes, and compatibility.
- [CSFLE Encryption Algorithms](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/encryption-algorithms/) — deterministic vs. randomized and frequency-analysis risks.
- [CSFLE Encryption Schemas](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/create-schema/) — declaring encryption rules.
- [Queryable Encryption Overview](https://www.mongodb.com/docs/manual/core/queryable-encryption/) — architecture and components.
- [Choosing an In-Use Encryption Approach](https://www.mongodb.com/docs/manual/core/queryable-encryption/about-qe-csfle/) — comparing CSFLE and QE.
- [Queryable Encryption Supported Operations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/supported-operations/) — exact operators, BSON types, CRUD, and aggregation support.
- [Queryable Encryption Limitations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/limitations/) — topology, unique/TTL, migration, diagnostic redaction, and threat model.
- [Queryable Encryption Schema](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-create-encryption-schema/) — `encryptedFields`, query types, bounds, and partial-match config.
- [Create Encrypted Collection](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-create-encrypted-collection/) — collection creation and insertion flow.
- [Query Encrypted Data](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-retrieve-encrypted-document/) — equality/range and newer version queries.
- [Encryption Keys and Key Vaults](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/keys-key-vaults/) — CMK, DEK, Key Vault, and rewrap.
- [Manage Encrypted Collections and Metadata](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/manage-collections/) — ESC, ECOC, `__safeContent__`, and compaction.
- [Queryable Encryption Quick Start](https://www.mongodb.com/docs/manual/core/queryable-encryption/quick-start/) — compatible lab setup and local-key warnings.
- [MongoDB 9.0 Compatibility](https://www.mongodb.com/docs/manual/release-notes/9.0-compatibility/) — migrating from 8.2/8.3 prefix/suffix/substring preview to GA.
- [Node.js Driver ClientEncryption API](https://mongodb.github.io/node-mongodb-native/) — verify signatures for `encrypt()`, `createDataKey()`, `createEncryptedCollection()`, and `rewrapManyDataKey()` for your driver version.

**Version note at time of writing:** MongoDB 9.0 includes GA QE prefix/suffix/substring support; these examples do not replace the version matrix for your specific deployment. In particular, verify edition policies and automatic encryption availability for your Atlas/Enterprise environment and driver.

## 26. Conclusion

**CSFLE** and **Queryable Encryption** encrypt sensitive fields **before data leaves the application**, complementing TLS, encryption at rest, authentication, and authorization. Deterministic CSFLE supports equality at the cost of duplicate/frequency pattern leakage; randomized CSFLE hides those patterns but cannot be queried by field value. QE pairs randomized ciphertexts with encrypted metadata/indexes to support conditional queries—including equality, range, and partial string matches in newer versions—in exchange for **storage overhead, write cost, key governance, and operation limits**.

Using these technologies effectively requires an end-to-end design: **threat model → field/BSON type/query type selection → remote KMS/CMK/DEK/Key Vault → proper encrypted collection creation → API authorization and uniqueness → migration/backup/rotation → monitoring and recovery**. Never treat encryption as a substitute for authorization; never manually edit ESC/ECOC/`__safeContent__`; never destroy keys while dependent data exists; and never assume every plaintext MongoDB operation works on ciphertext.

**Core takeaway:** client-side encryption truly protects data only when **keys, schemas, access controls, read–write flows, and recovery plans** are all designed cohesively.
