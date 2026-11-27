# Cross-Checking Server Features, Drivers, Encryption Libraries, and Editions

In a **Spring Data MongoDB** application, the requirement to "encrypt data" becomes an actionable design only once you clarify **at which layer encryption occurs**, **what MongoDB Server supports**, **which edition is running**, **whether the Java driver has the matching capability**, **which encryption libraries are packaged**, and **where keys are managed**.

A cluster using TLS and encrypted disks can still return plaintext data to any account with read permissions. Conversely, an application using **Client-Side Field Level Encryption (CSFLE)** can keep sensitive fields as ciphertext on the server, yet still requires TLS, authorization, key management, and backup procedures. This lesson shows how to cross-check those layers before choosing a configuration for **MongoTemplate**, repositories, or **ReactiveMongoTemplate**.

> Scope: MongoDB Community Server, MongoDB Enterprise Advanced, and MongoDB Atlas; synchronous or reactive Java drivers used by Spring Data MongoDB. Documentation reference point: **November 2026**. Feature eligibility must always be re-verified against your exact versions, topology, FCV, software packaging, and compatibility documentation at deployment time.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish encryption **in transit**, **at rest**, and **client-side before data is sent**.
2. Read compatibility matrices across **server version × edition × topology × driver × encryption library × query type**.
3. Distinguish **explicit encryption** from **automatic encryption**, including **automatic decryption** without automatic encryption.
4. Understand the distinct roles of **mongodb-crypt**, **libmongocrypt**, **crypt_shared**, **mongocryptd**, **DEK**, **CMK**, and **KMS**.
5. Make evidence-based decisions for encrypted-field query requirements and plan tests from Spring Data MongoDB.

## 2. Viewing Through Protection Layers

| Layer | Who Performs It? | Where Is Data Protected? | Does It Hide Data From MongoDB Server? |
| --- | --- | --- | --- |
| **TLS** | Driver and MongoDB endpoint | Over the network in transit | **No**. The server decrypts TLS to process queries. |
| **Encryption at rest** | Atlas storage mechanism, Enterprise, or OS/disk infrastructure | Data files, volumes, and backups within configured scope | **No**. A running server still reads data to process operations. |
| **CSFLE** | Client/driver and encryption library | Selected fields encrypted before leaving the application | **Yes**, for configured fields when keys are kept out of the server's hands. |
| **Queryable Encryption (QE)** | Client/driver; server processes queries over encrypted data via supported mechanism | Sensitive fields stay encrypted while supporting certain query types | **Yes**, when properly configured; query capabilities depend on version and QE limits. |

~~~mermaid
flowchart LR
    A["Spring Data MongoDB<br/>MongoTemplate / Repository"] --> B["Java MongoDB Driver"]
    B --> C{"Client-side encryption?"}
    C -- "CSFLE or QE" --> D["mongodb-crypt / libmongocrypt<br/>DEK + KMS + query analysis if needed"]
    C -- "No" --> E["TLS"]
    D --> E
    E --> F["MongoDB Server<br/>Community / Enterprise / Atlas"]
    F --> G["Storage layer<br/>Encryption at rest"]
~~~

**Isolate the threat to address:**

- Prevent sniffing between the application and MongoDB: configure **TLS** and certificate verification.
- Prevent unauthorized reading of stolen storage media: **encryption at rest**, key policies, and backups.
- Restrict DBAs or services with database read access from viewing confidential fields: **client-side encryption** with keys protected separately from DB admin accounts.
- Need to search encrypted fields: select **deterministic CSFLE** or **Queryable Encryption** appropriately; never assume an ordinary MongoDB query will work.

## 3. Capability Matrix by Edition and Mechanism

In the table below, **Conditional** means you must also verify version, topology, driver, configuration, and component access permissions. This is a directional guide, **not a replacement for the official compatibility matrix**.

| Capability | Community Server | Self-Managed Enterprise Advanced | MongoDB Atlas |
| --- | --- | --- | --- |
| TLS between driver and server | Yes, when TLS is configured | Yes, when TLS is configured | Yes, connects per Atlas policies |
| File encryption via **native encrypted WiredTiger storage engine** | Not a native Community feature; can encrypt at OS/volume layer | Yes, on WiredTiger when properly configured | Default encryption at rest; encryption layers and CMK depend on product/tier |
| **CSFLE explicit encryption** | Conditional; compatible servers from 4.2 | Conditional; compatible servers from 4.2 | Conditional |
| **CSFLE automatic encryption** | **No** per edition licensing matrix | Conditional | Conditional |
| **CSFLE automatic decryption** for encrypted data | Conditional, with matching client and keys | Conditional | Conditional |
| **QE explicit encryption** | Conditional, on QE-supported servers and topologies | Conditional | Conditional |
| **QE automatic encryption** | **No** per edition licensing matrix | Conditional | Conditional |
| **QE automatic decryption** for encrypted data | Conditional, with client config and keys | Conditional | Conditional |
| MongoDB Server FIPS mode | Not available by default as an Enterprise feature | Verify Enterprise distribution and configuration | Confirm by service, tier, and compliance requirements |

**Three common misconceptions:**

1. **Having TLS does not mean having CSFLE/QE.** TLS protects the wire; the server still processes plaintext for fields not encrypted on the client.
2. **Community supporting explicit encryption does not mean it supports automatic encryption.** Community apps can explicitly call encrypt/decrypt APIs, or use corresponding automatic decryption, but query analysis and automatic encryption carry edition restrictions.
3. **Atlas having default encryption at rest does not mean the application has enabled QE.** Field encryption must be designed separately; customer-managed key options also depend on product/tier.

**Example scenario:** a team runs Community Server 8.x on a replica set, with a QE-capable Java driver and **mongodb-crypt**. They can evaluate **QE explicit encryption**; they **cannot** conclude "QE automatic encryption works" merely from upgrading the server and adding the JAR. Even on Enterprise/Atlas, query analysis components and KMS must still be configured.

## 4. Server Version, Topology, and Query Capabilities

Search capability on encrypted fields is not decided by the driver alone. The server must understand the metadata layout and encrypted query shape in use.

| Need | Mechanism | Compatibility Milestones to Check | Key Notes |
| --- | --- | --- | --- |
| Encrypt field and read only after decryption | Randomized/explicit CSFLE | CSFLE available from MongoDB Server 4.2 with supporting driver | Cannot search by plaintext value on randomized encrypted fields. |
| Exact-match lookup by value | Deterministic CSFLE | Server and driver supporting CSFLE | Ciphertexts for equal values can repeat, leaking frequency patterns. |
| Exact lookup with randomized ciphertext | QE equality | **MongoDB 7.0+ GA** and compatible driver/QE runtime | QE 6.x public preview is not directly compatible with 7.0 GA format. |
| Range search on encrypted field | QE range | **MongoDB 8.0+**, driver, and crypto library supporting the query type | Requires configuring matching data type, value bounds, parameters, and encrypted indexes. |
| Prefix, suffix, substring search | QE prefix/suffix/substring | **MongoDB 9.0+ GA** and driver/library supporting the new APIs | 8.2–8.x preview versions have different APIs/formats; do not upgrade by arbitrarily renaming options. |

**Topology:** QE requires a **replica set** or **sharded cluster**; **standalone** is not supported. Beyond the binary version, verify **featureCompatibilityVersion (FCV)** and specific feature requirements. Having a sufficiently high binary version is only part of the check.

**Query notes:** operators, aggregation stages, updates, sharding, secondary reads, collection renaming, and indexing for QE fields carry specific restrictions. Never infer that because QE supports range queries, any `MongoTemplate.query(...)`, aggregation, or `MongoRepository` method with arbitrary operators is supported. Test exact query shapes and consult **Supported Operations** and **Limitations** for your target server version.

Example choices for a customer management application:

| Field | Need | Option to Evaluate |
| --- | --- | --- |
| **customer.notes** | Store and display, no content search | Randomized CSFLE or unindexed QE; decrypt on client |
| **customer.email** | Exact email lookup | QE equality; or deterministic CSFLE after evaluating frequency leakage |
| **customer.salary** | Salary range filter | QE range on a compatible stack; deterministic CSFLE does not support range queries |
| **customer.name** | Name prefix search | QE string query on MongoDB 9.0+ with supporting driver/library; verify string constraints |

Low-cardinality fields such as **ACTIVE/INACTIVE** status should not default to deterministic encryption, because observers can deduce value distributions from ciphertext frequencies.

## 5. Drivers and Encryption Libraries: Who Does What?

In a Spring Data MongoDB project, clearly distinguish these components:

| Component | Role | Pre-Run Checks |
| --- | --- | --- |
| **Spring Data MongoDB** | Document mapping, repositories, `MongoTemplate`/`ReactiveMongoTemplate`, and DB access config | Current Spring Data/Spring Boot version and managed driver version |
| **mongodb-driver-sync** or **mongodb-driver-reactivestreams** | Connections, BSON, MongoDB commands, encryption config APIs on `MongoClient` | Actual version in dependency tree; algorithm/QE support |
| **org.mongodb:mongodb-crypt** | Java artifact added to use in-use encryption | JAR present at runtime and version aligned with Java driver |
| **libmongocrypt** | Core cryptographic library used by the driver/integration layer | Native binary compatible with OS/CPU, build, and version |
| **crypt_shared** / **Automatic Encryption Shared Library** | Analyzes and rewrites queries for automatic encryption; recommended option | Edition/entitlement, shared library file, path, and runtime compatibility |
| **mongocryptd** | Legacy query analysis daemon in older automatic CSFLE setups | May be needed on legacy systems; **deprecated since MongoDB 9.0**, prefer `crypt_shared` |
| **KMS** and **Key Vault** | Manage master keys and data encryption keys | Access permissions, KMS connectivity, lifecycle/backups, and vault authorization |

**Do not equate `libmongocrypt` with `crypt_shared`.** The core library performs cryptography; the query-analysis component handles detecting and rewriting queries for automatic encryption. **`mongocryptd` does not store keys and does not directly encrypt data**. Adding the driver or JAR does not automatically bundle, license, or configure all other components.

Java driver artifacts are typically managed via a **Bill of Materials (BOM)** or Spring Boot dependency management. Do not mix the latest `mongodb-crypt` version with an older Java driver without checking compatibility. When packaging Docker deployment artifacts, verify the **runtime image** as well: a native library present on a dev laptop may be missing in a container or target the wrong CPU architecture.

Example Maven dependency for in-use encryption when the project uses compatible dependency management:

~~~xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-crypt</artifactId>
</dependency>
~~~

Avoid pinning an independent version if it conflicts with the driver version managed by Spring. For reactive Java, confirm encryption features are supported by the **reactive driver version** in use; synchronous Java examples do not guarantee identical APIs exist across all reactive releases.

## 6. Keys, Vaults, and KMS Services

Even when edition and driver support encryption, jobs still fail if the application cannot obtain keys:

- **Data Encryption Key (DEK):** used to encrypt individual data fields. Protected DEKs are stored in the **Key Vault** collection.
- **Customer Master Key (CMK):** protects DEKs; typically hosted in AWS KMS, Azure Key Vault, Google Cloud KMS, KMIP, or another supported option.
- **Key Vault collection:** dedicated MongoDB collection storing key documents; **not** a place to store plaintext CMKs.
- **KMS credentials and network permissions:** the application must authenticate, call KMS, and read relevant DEKs. MongoDB authentication and KMS authentication are separate concerns.

~~~mermaid
sequenceDiagram
    participant App as "Spring Application"
    participant Driver as "MongoDB Driver + Crypto"
    participant KMS as "KMS / Master Key"
    participant Vault as "MongoDB Key Vault"
    participant DB as "MongoDB Collection"
    App->>Driver: "Save document with sensitive field"
    Driver->>Vault: "Read protected DEK"
    Driver->>KMS: "Request unwrap DEK per permissions"
    KMS-->>Driver: "Return valid key material"
    Driver->>Driver: "Encrypt field on client"
    Driver->>DB: "Send BSON containing ciphertext over TLS"
    DB-->>Driver: "Read ciphertext"
    Driver->>Driver: "Decrypt on key-authorized client"
    Driver-->>App: "Decrypted value"
~~~

The flow above is illustrative, not a fixed per-call network sequence for every driver. Drivers may cache information according to library policy. Never hardcode CMKs/DEKs, never log plaintext or key material, and plan key rotation and recovery. **Key loss can render ciphertext undecryptable**, even when MongoDB data remains intact.

## 7. Cross-Checking Real Configuration Before Writing Code

A valid verification pass records **server version, edition/deployment, topology, FCV, driver version, crypto dependency, query analysis component, KMS, and query requirements**. Never treat a single `db.version()` line as complete proof.

### Step 1 — Verify Server and Topology

Run in **mongosh** using an appropriately privileged account:

~~~javascript
db.version();

db.adminCommand({ buildInfo: 1 });

db.adminCommand({ hello: 1 });

// May require higher privileges; managed environments may restrict.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

How to interpret the output:

- **buildInfo.version:** server binary version, input to the matrix.
- **buildInfo.modules** and deployment info: a clue for checking edition; on Atlas, confirm cluster type/tier from Atlas management controls rather than guessing from the version string.
- **hello.setName**, host list, or topology info: distinguishes replica set from standalone; if connected through **mongos**, confirms a sharded cluster.
- **featureCompatibilityVersion:** checks server feature compatibility state. If the command lacks permissions, mark it **unverified** and ask administrators instead of guessing.

To verify TLS from the client, inspect the connection string and driver SSL settings; verify valid certificates in real environments. Never disable hostname verification or allow untrusted certificates just to "make it work." On Atlas, use TLS settings per service documentation.

### Step 2 — Record Java-Side Versions

Inspect the dependency tree of the exact artifact to be deployed (Maven or Gradle) and record at least:

~~~text
Spring Boot:                 <version>
Spring Data MongoDB:         <version>
mongodb-driver-sync/reactive:<version>
mongodb-crypt:               <version>
libmongocrypt/native:        <version/OS/architecture>
crypt_shared:                <version/path if used>
MongoDB Server + FCV:        <version + FCV>
Edition / Deployment:        <Community | Enterprise | Atlas + tier>
Topology:                    <standalone | replica set | sharded>
KMS provider:                <provider + access info, do not log secrets>
Feature / Query:             <CSFLE/QE + explicit/automatic + query type>
~~~

Every **version** and minimum prerequisite must be checked against the compatibility matrix of your exact driver and encryption feature; versions in older guides may not match modern runtimes.

### Step 3 — Choose the Encryption Mode

| Application Condition | Deployment Direction |
| --- | --- |
| Community and wants explicit per-field encryption | Evaluate **explicit CSFLE** or **explicit QE** depending on server/topology/queries; application handles encrypting on write and encrypting search values via the right APIs. |
| Enterprise/Atlas and wants automatic encryption | Evaluate **automatic CSFLE** or **automatic QE**, configure **AutoEncryptionSettings**, query analysis component, and rules/schemas for the chosen feature. |
| Has ciphertext to read without auto-encrypting writes | Evaluate **automatic decryption** with appropriate bypass settings; check APIs by feature and driver version. |
| Only needs disk/backup encryption | Configure **at-rest encryption** at the infrastructure layer or native engine for your edition; do not call it field encryption. |

**Automatic CSFLE** and **automatic QE** use separate metadata/rules. Do not substitute CSFLE's `schemaMap` for QE's `encryptedFieldsMap`. With QE, create collections and encrypted-fields metadata through the official workflow; you cannot simply add an annotation to an existing collection and expect queries to be encrypted.

## 8. Example Java Driver Configuration for `MongoTemplate` Integration

Spring Data MongoDB executes operations via `MongoClient`. Automatic encryption settings usually attach to `MongoClientSettings`; `MongoTemplate` or repositories use that client for I/O. The example below highlights the exact wiring points to check for **automatic CSFLE** on Enterprise/Atlas.

~~~java
import com.mongodb.AutoEncryptionSettings;
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.Map;
import org.bson.BsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class MongoCsfleClientFactory {

    // Configuration skeleton only: maps and paths must be supplied from
    // secret management and the application's actual schema.
    public static MongoClient create(
            String connectionString,
            Map<String, Map<String, Object>> kmsProviders,
            Map<String, BsonDocument> csfleSchemaMap,
            String cryptSharedLibraryFile) {

        AutoEncryptionSettings encryption = AutoEncryptionSettings.builder()
            .keyVaultNamespace("keyvault.datakeys")
            .kmsProviders(kmsProviders)
            .schemaMap(csfleSchemaMap)
            .extraOptions(Map.of(
                "cryptSharedLibPath", cryptSharedLibraryFile,
                "cryptSharedLibRequired", true
            ))
            .build();

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(connectionString))
            .autoEncryptionSettings(encryption)
            .build();

        return MongoClients.create(settings);
    }

    public static MongoTemplate createTemplate(MongoClient client) {
        return new MongoTemplate(client, "appdb");
    }
}
~~~

**How to read this example properly:**

- **kmsProviders** holds valid KMS configuration, never hardcoded secrets in source code. **csfleSchemaMap** must contain the full namespace key (e.g., `appdb.customers`) and a valid CSFLE schema for fields requiring encryption. If the map is empty and the server also lacks an appropriate encryption schema, the client will not automatically encrypt target fields.
- **cryptSharedLibraryFile** must point to the actual library **file** for your OS/CPU, not a directory. **cryptSharedLibRequired=true** ensures an explicit error if the required library fails to load.
- This is an **integration skeleton**, not a complete production template: you still need DEK/CMK provisioning, Key Vault/KMS permissions, TLS, accurate schema config, client lifecycle management, and DB ciphertext verification.
- In Spring Boot, register the right **`MongoClient` bean** so `MongoTemplate`/repositories use the configured client; creating a separate `MongoClient` without auto-encryption for a write task leaves that write unencrypted.
- For **Queryable Encryption**, use QE's encrypted-fields configuration and collection-creation workflow (such as `encryptedFieldsMap`), rather than copying the CSFLE schema above.
- For **explicit encryption**, use the driver's `ClientEncryption` API and store ciphertext in the matching BSON type; ordinary `MongoTemplate.save` calls do not infer which fields to encrypt without an automatic mechanism.

Client-side encryption can affect `Criteria` queries, projections, aggregations, indexes, and mapping of sensitive fields. A derived repository method name does not automatically prove queries on ciphertext are supported. Test exact query shapes through the actual bean and driver version going to production.

## 9. Decision Table From Requirements to Configuration

Suppose a project team must store customers' **email**, **national ID**, **internal notes**, and **income**. Key questions to ask:

1. **Who must not see the data?** Only someone stealing a disk, or also administrators with DB query access?
2. **Which fields need querying and with which operators?** Equality, range, prefix, aggregation?
3. **What is the server?** Community, Enterprise Advanced, or Atlas; version, topology, FCV?
4. **Can application code be modified to encrypt per operation?** If not, do automatic encryption's edition and query-analysis requirements fit?
5. **Do the driver and crypto library support that encryption mode and query type?** Have the build artifact and container image been verified?
6. **Who holds the keys?** Where is the KMS, who may decrypt, and how is access recovered if lost?

| Context | Preliminary Choice | Deciding Conditions |
| --- | --- | --- |
| Community, must hide data from DB admins, read fields only after fetching document | **Explicit randomized CSFLE** | Driver + `mongodb-crypt`, DEK/KMS, encrypt and decrypt in application |
| Community, needs exact email lookup | **Deterministic CSFLE** or **explicit QE equality** | Weigh deterministic frequency leakage; QE needs compatible version/topology and APIs |
| Enterprise/Atlas, avoid modifying every write call | **Automatic CSFLE/QE** | Edition, query analysis component, schema/metadata, driver, KMS, real tests |
| Needs income range filtering on ciphertext | **QE range** | Server 8.0+ with supporting driver/library and proper encrypted collection |
| Needs substring search inside encrypted names | **QE string** | Server 9.0+ GA with supporting driver/library; check limits and overhead |
| Only needs volume or backup protection | **Encryption at rest** | Verify edition/infrastructure layer; does not hide data from DBA queries |

Note: searchable text encryption **does not mean** MongoDB's full search engine, regex, or full-text features work on ciphertext. Verify supported operators, performance, and query-pattern inference risks before selecting a solution.

## 10. Compatibility Testing: Proving by Behavior

In a staging environment close to production, assemble an **evidence table** before approving go-live:

| Test | How to Execute | Pass Criteria |
| --- | --- | --- |
| TLS connection | Use exact production `MongoClient` config with valid trust store | Connects with proper hostname verification; certificate checks not disabled |
| Edition and topology support | Record version, FCV, edition, topology and cross-check feature docs | All official prerequisites satisfied |
| Crypto library loads | Initialize encrypted `MongoClient` in the real runtime | No native library, `crypt_shared`, or ABI/architecture errors |
| KMS/DEK reachable | Create or read a test DEK against a dedicated key vault | Key unwraps under the application's authorized identity |
| No plaintext leaks on write | Write sample sensitive fields via encrypted client; read back with a **keyless client** | Protected fields stored as encrypted BSON/ciphertext, no plaintext visible |
| Authorized decryption | Read same document with an authorized client and an unauthorized client | Authorized client receives exact value; keyless client cannot decrypt |
| Query on ciphertext | Run exact **`Criteria`/query types** (equality, range, string if needed) | Returns expected results within feature limits |
| Unsupported query | Run a known-unsupported operator on an encrypted field | Rejected cleanly, never silently falling back to unsafe plaintext queries |
| Cross-runtime verification | Run the same suite on the target deployment image/build | No API/native library/format drift from test environment |
| KMS revocation and recovery | Test in an isolated environment, never on production | Observable error without leaking secrets; documented recovery works |

**Why is a second, keyless client needed?** If you test only through a client with automatic decryption enabled, read data always looks like plaintext as designed. That **does not prove data was stored as ciphertext**; the key-authorized client decrypted it for the app. Reading without auto-decryption and inspecting raw BSON confirms real encryption took place.

For **`@DataMongoTest`** and Testcontainers, separate mapping tests from encryption-compatibility tests. A standalone Community MongoDB Testcontainer can test CRUD and some explicit CSFLE operations, but is **insufficient** to verify QE (which requires replica set/sharding), edition-gated automatic encryption, or production-packaged native libraries. Do not mark the entire stack compatible just because repository unit tests are green.

Metrics to monitor during load tests: p95/p99 encrypt/decrypt latency, application CPU, KMS latency, ciphertext size, QE index/metadata overhead, memory footprint, and query-speed impact. With **`ReactiveMongoTemplate`**, also test backpressure, concurrency, retries, and asynchronous encryption paths; do not extrapolate performance from sync driver benchmarks.

## 11. Troubleshooting by Layer

| Symptom | What to Check | Resolution |
| --- | --- | --- |
| Connection fails with TLS handshake/certificate error | Trust store, hostname, CA, certificate expiry | Fix trust chain and certificates; do not disable TLS verification |
| Auto encryption does not run, or reports unsupported edition | Automatic encryption attempted on Community; missing query analysis | Verify edition, switch to explicit if appropriate, or move to a supported edition/tier |
| Native library load failed | Wrong path, OS/CPU, JAR/native version, file permissions | Verify runtime artifacts and driver compatibility matrix |
| `crypt_shared` not found | File missing, wrong path, insufficient permissions | Package library for the right edition; point `cryptSharedLibPath` to the file |
| KMS authentication/permission error | Expired credentials, wrong IAM/role, network failure, disabled master key | Verify permissions and connectivity to KMS safely |
| Reads return ciphertext without decrypting | Client lacks decryption config, KMS key, or Key Vault access | Inspect actual client used by `MongoTemplate`/repositories and key permissions |
| Range/prefix query errors | Server, FCV, driver, or crypto library lacks query type support | Re-check version matrix and field/collection format |
| Writes plaintext despite expecting ciphertext | Missing/wrong schema/metadata or written via another client | Check schema map, `encryptedFields`, namespace, and active beans |
| QE preview data fails to open with GA configuration | Cross-generation QE format difference | Plan decryption and data migration per version upgrade guide |

Never write plaintext, raw DEKs, CMKs, password-bearing URIs, or sensitive user details into diagnostic logs. When investigating deeply, use synthetic test data and log command IDs, error types, driver versions, loaded libraries, and correlation IDs.

## 12. Technology Selection Approval Checklist

- [ ] Threat clearly stated: in transit, at rest, or server-privileged access.
- [ ] Confirmed **edition**, Atlas cluster tier if applicable, **server version**, **FCV**, and **topology**.
- [ ] Recorded versions of **Spring Data MongoDB**, sync/reactive Java driver, **mongodb-crypt**, native **libmongocrypt**, and **crypt_shared** if used.
- [ ] Confirmed feature choice: **CSFLE** vs. **QE**, **explicit** vs. **automatic**, and decryption approach.
- [ ] Cross-checked actual query types against officially supported versions and limits.
- [ ] Configured and tested **KMS**, **Key Vault**, DEK/CMK, access policies, rotation, and recovery.
- [ ] Verified documents are stored as ciphertext by raw reading from a non-decrypting client.
- [ ] Tested through the exact **`MongoClient`** used by `MongoTemplate`, repositories, or `ReactiveMongoTemplate`.
- [ ] Benchmarked performance and tested TLS, native library, KMS, and unsupported-query failures.
- [ ] Documented explicitly which capabilities are **unsupported**, untested, or require upgrades.

## 13. References to Re-Verify Versions

Consult documentation for your exact **deployment versions**, especially when upgrading MongoDB Server or the Java driver:

1. [MongoDB — In-Use Encryption (Java Sync Driver)](https://www.mongodb.com/docs/drivers/java/sync/current/security/encrypt-fields/): `mongodb-crypt` dependency, CSFLE, QE, and query capabilities.
2. [MongoDB — Compatibility: QE and CSFLE](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/compatibility/): version, edition, and driver; choosing the right encryption feature and Java driver.
3. [MongoDB — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/): architecture, limitations, and supported query types.
4. [MongoDB — Queryable Encryption Limitations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/limitations/): topology, collections, sharding, and unsupported operations.
5. [MongoDB — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): automatic/explicit encryption and key management.
6. [MongoDB — Install CSFLE Query Analysis Component](https://www.mongodb.com/docs/manual/core/csfle/reference/install-library/): `crypt_shared`, `mongocryptd`, and runtime prerequisites.
7. [MongoDB — Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/): Enterprise's native WiredTiger encrypted storage engine.
8. [MongoDB Atlas — Encryption at Rest Overview](https://www.mongodb.com/docs/atlas/security-encryption-at-rest-overview/): default encryption layers and customer-managed keys by product.
9. [MongoDB — TLS/SSL Transport Encryption](https://www.mongodb.com/docs/manual/core/security-transport-encryption/): authentication and transport encryption.
10. [MongoDB Java Driver — AutoEncryptionSettings.Builder](https://mongodb.github.io/mongo-java-driver/5.12/apidocs/driver-core/com/mongodb/AutoEncryptionSettings.Builder.html): `schemaMap`, `encryptedFieldsMap`, and `crypt_shared` path options.

**Key takeaway:** "MongoDB supports encryption" is not enough to make a design decision. Certify a feature as **ready for deployment** only after proving **the right protection layer + the right edition + the right server/FCV/topology + the right driver/library + the right key management + the right query types**, verified end-to-end through your Spring Data MongoDB application's real execution paths.
