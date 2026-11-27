# Key Vault, Data Encryption Keys, and KMS Providers

## 1. Three Components in the MongoDB Data Encryption Problem

When building a **Spring Data MongoDB** application, developers typically use **MongoTemplate** or **MongoRepository** to persist documents. For sensitive fields such as identification numbers, payment details, or personal data, you need to define **who can see plaintext**, **where encryption keys live**, and **how the application retrieves keys**. MongoDB provides **client-side encryption** (Client-Side Field Level Encryption, CSFLE; and Queryable Encryption in supported cases), allowing you to choose fields to encrypt before they leave the application.

Three core concepts:

| Concept | Role | Where Is It Actually Stored? |
| --- | --- | --- |
| **Key vault** | Collection storing metadata and the **encrypted** form of Data Encryption Keys (DEKs); helps clients locate needed keys. | An application-designated MongoDB collection, e.g., **encryption.__keyVault**. |
| **Data Encryption Key (DEK)** | Symmetric key used to encrypt/decrypt sensitive data values. | In wrapped/encrypted form inside the key vault; plaintext key material is handled only temporarily on the client when needed. |
| **KMS provider** | How the client accesses the **master key / KEK** to wrap or unwrap DEKs. | Can be a key management service like AWS KMS, Azure Key Vault, Google Cloud KMS, KMIP, or a local key during development. |

**A KMS provider is not the DEK itself.** The master key is managed via the KMS; the DEK encrypts document values; the key vault holds metadata and wrapped DEKs. This is **envelope encryption**.

### Learning Objectives

After this lesson, you will be able to:

1. Diagram the encryption/decryption flow across a Spring application, key vault, and KMS provider.
2. Identify the important fields of a key vault document.
3. Create and use DEKs via the MongoDB Java Driver inside a Spring application.
4. Choose a local KMS for learning and an external KMS for deployment environments.
5. Plan access permissions, backups, rotation, failure recovery, and integration with MongoTemplate/repositories.

## 2. Distinguishing Encryption Layers

Before configuring a key vault, know what kind of protection it solves.

| Protection Layer | What Does It Protect? | Are Key Vault and DEK Involved? |
| --- | --- | --- |
| **TLS in transit** | Data moving between client and MongoDB against network eavesdropping/tampering. | Not directly; TLS protects the transport channel. |
| **Encryption at rest** | Data files, devices, or backups while stored on the storage system. | Not directly via the client-side mechanism; managed separately by the server or storage platform. |
| **Client-Side Field Level Encryption (CSFLE)** | Selected field values encrypted at the client before being sent to MongoDB. | Yes: uses DEKs and a key vault; decryption requires access to the DEK and KMS. |
| **Queryable Encryption (QE)** | Client-side encryption supporting certain query types on encrypted data per supported features/versions. | Yes: also requires a key vault, DEKs, and KMS; query configuration, metadata, and deployment prerequisites have additional rules. |

**Example:** TLS does not prevent a database administrator with read permissions from viewing stored plaintext field values; encryption at rest does not mean values are encrypted individually at the document layer. With client-side encryption, only properly configured fields and access paths are protected. Unencrypted fields, collection names, metadata, and access patterns may still leak partial information.

## 3. How Does Envelope Encryption Happen?

Suppose the application stores the **citizenId** field of **customers** documents.

~~~mermaid
flowchart TB
    App["Spring Data MongoDB / Java Driver<br/>client-side"]
    Vault[("MongoDB Key Vault<br/>encryption.__keyVault<br/>Wrapped DEK")]
    KMS["KMS provider<br/>access to master key / KEK"]
    Data[("MongoDB customers<br/>encrypted field BSON BinData subtype 6")]

    App -->|"1. Look up metadata and wrapped DEK"| Vault
    Vault -->|"2. Return wrapped DEK"| App
    App <-->|"3. Send wrap / unwrap DEK request"| KMS
    App -->|"4. Encrypt field then write ciphertext"| Data
    Data -->|"5. Read ciphertext; decrypt on client"| App
~~~

### When Creating a DEK

1. The client randomly generates DEK key material using the driver's cryptographic mechanism.
2. The client uses the declared KMS provider to encrypt (wrap) the DEK material with the master key.
3. The client stores the metadata document and **wrapped DEK** in the key vault, receiving a **key ID** for reference.
4. The application uses the key ID or **keyAltNames** to identify which DEK to use for each field.

### When Writing Encrypted Data

1. The driver reads DEK information from the key vault when needed; the wrapped DEK is unwrapped with the master key through the KMS provider.
2. On the client side, the encryption library uses the DEK to encrypt the field value.
3. MongoDB receives and stores the ciphertext. For client-side encrypted values, the encrypted BSON format typically has **binary subtype 6**.

### When Reading Encrypted Data

1. The application receives ciphertext from MongoDB.
2. The client identifies the required DEK from information embedded in the encrypted value.
3. The driver fetches the DEK from the key vault and asks the KMS to unwrap it if the matching key is not already in memory/cache.
4. The client decrypts and returns plaintext to code authorized to use that value.

The KMS may be called fewer times than the number of documents read or written because the driver can cache unwrapped DEKs. Do not assume **every read calls the KMS**, nor rely on caching to skip proper access design and KMS availability planning. MongoDB read permissions alone are insufficient for decryption without the keys and proper client configuration.

## 4. What Is a Key Vault and What Is Its Structure?

A key vault is an **ordinary MongoDB collection**, identified by a **database.collection** string in driver configuration. For example:

~~~text
Database:   encryption
Collection: __keyVault
Namespace:  encryption.__keyVault
~~~

This is an example namespace, not a mandatory name. The key vault can reside on the same cluster as application data or on a deployment matching your security policy; the driver must be configured with the right connection and permissions.

A key document conceptually looks like:

~~~javascript
{
  _id: UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
  keyAltNames: ["customers-citizen-id-v1"],
  keyMaterial: BinData(0, "<encrypted DEK>"),
  creationDate: ISODate("2026-10-01T00:00:00Z"),
  updateDate: ISODate("2026-10-01T00:00:00Z"),
  status: 0,
  masterKey: {
    provider: "aws",
    region: "ap-southeast-1",
    key: "arn:aws:kms:ap-southeast-1:123456789012:key/example-key-id"
  }
}
~~~

This is only a structural example for comprehension; exact details depend on the encryption mechanism and driver. Notable fields:

| Field | Meaning |
| --- | --- |
| **_id** | Unique ID of the DEK, usually represented as a BSON UUID. Can be embedded to identify the key when decrypting encrypted data. |
| **keyMaterial** | DEK material encrypted with the master key. Not the plaintext data key. |
| **masterKey** | Metadata identifying the KMS provider and associated master key, e.g., an AWS KMS key in a specific region. |
| **keyAltNames** | Business-meaningful aliases, e.g., **customers-citizen-id-v1**, used for easier key lookup. |
| **creationDate/updateDate** | Creation/update timestamps of key metadata, useful for auditing and operations. |
| **status** | Status of the key document as represented by the encryption mechanism. Do not manually edit this to "disable" a key. |

**The key vault is critical data that must be backed up.** If the key vault is lost, clients may be unable to recover DEKs for decryption, even if the data documents remain intact. If access to the master key in KMS is lost, wrapped DEKs may also become unusable.

### Why Is a Unique Index Needed on `keyAltNames`?

When multiple processes provision keys, an alias must uniquely identify one DEK. MongoDB recommends creating a **unique partial index** on **keyAltNames** to avoid multiple keys sharing the same alias in the key vault.

Run in **mongosh** after preparing the database and permissions:

~~~javascript
db.getSiblingDB("encryption")
  .getCollection("__keyVault")
  .createIndex(
    { keyAltNames: 1 },
    {
      unique: true,
      partialFilterExpression: { keyAltNames: { $exists: true } }
    }
  );
~~~

This index does not replace database access permissions. Nor does it mean **key ID** and **keyAltName** are the same: a DEK has one ID and can be assigned aliases per supported APIs. In business code, choose stable aliases and avoid generating a new DEK per request.

## 5. What Is a Data Encryption Key (DEK) Used For?

A DEK is the key that encrypts **data values**. It is distinct from the KMS master key and distinct from the MongoDB connection password.

For example, a customer management system might use:

- **DEK A:** encrypts customers' `citizenId` field.
- **DEK B:** encrypts sensitive contact information.
- **DEK C:** encrypts data for a tenant group with separate isolation policies.

There is no mandatory rule to create exactly one DEK per document, per collection, or per tenant; the DEK partitioning strategy depends on isolation level, access permissions, and operational overhead. Using too few DEKs can widen the blast radius if a key is compromised; using too many DEKs can complicate lifecycle management and administration.

### Key ID vs. `keyAltName`

| Access By | Suitable When | What to Watch |
| --- | --- | --- |
| **Key ID** | A specific, stable, unambiguous key reference is needed. | Must store or resolve the exact key UUID. |
| **keyAltName** | You want readable alias-based configuration for each data group. | Must enforce alias uniqueness and manage change/revocation policies. |

Client-side encrypted ciphertext embeds the key identification needed for the driver to look up the decryption DEK. **Changing an alias does not re-encrypt ciphertext**; rotating to a new DEK so data actually uses a different key is a separate procedure.

## 6. KMS Providers and Master Keys

A **Key Management Service (KMS)** manages or provides access to the **key-encryption key (KEK/master key)**. Clients use this key to wrap/unwrap DEKs. KMS permissions can be separated from permissions to read/write documents and the key vault.

MongoDB supports common provider families depending on driver version and environment:

| Provider | Use Case | Deployment Conditions to Consider |
| --- | --- | --- |
| **local** | Learning, prototyping, and controlled test environments. | Supplies a **96-byte** master key client-side; you are responsible for key storage, distribution, and backup. |
| **AWS KMS** | Applications running on AWS with IAM/KMS permissions. | Requires configuring region, KMS key identifier, permissions, and connectivity to KMS. |
| **Azure Key Vault** | Applications with Azure infrastructure and identity. | Requires endpoint/key identifier, permissions, and appropriate identity provisioning. |
| **Google Cloud KMS** | Applications with Google Cloud infrastructure and identity. | Requires key resource/version details, permissions, and appropriate credentials. |
| **KMIP** | Enterprises using KMIP-compliant key management systems. | Requires KMIP server, TLS/certificates, and access policies. |

Three values are frequently confused:

1. **Provider name** (e.g., **aws**, **local**) tells the driver which KMS mechanism to select.
2. **Provider credentials** tell the driver how the client authenticates to call the KMS.
3. **Master key identifier** points to the specific master key managed by the provider to wrap DEKs.

For example: an application with a valid IAM role (credentials) must still specify the exact KMS key ARN (master key identifier) and hold permissions for the required operations. **Successfully declaring a provider does not mean a DEK has been created.**

### Is Local KMS Safe for Production?

The local provider requires the application to hold the master key material. This is useful for learning the workflow, but production generally favors a KMS with clear access control, auditing, and recovery policies. If `local` is used under special circumstances, you need an equivalent secret management mechanism for access control and backup. Never hardcode master keys in Java, YAML, Git, or logs.

## 7. Hands-On DEK Creation With Spring and the MongoDB Java Driver

This example uses **local KMS** to keep the steps clear and avoid external service account dependencies. Assume:

- MongoDB is running, the **encryption.__keyVault** collection can be created, and the connection account has appropriate permissions.
- The application has Spring Data MongoDB dependencies and MongoDB Java Driver components supporting CSFLE, including the required encryption library for your driver/OS.
- Two environment variables are set: **MONGODB_URI** and **LOCAL_KMS_KEY_BASE64**. The latter holds **96 random bytes** Base64-encoded; it is an application secret and must not be committed to the repository.
- The unique partial index on **keyAltNames** has been created as shown above.

### 7.1. Declaring `ClientEncryption` as a Spring Bean

~~~java
import com.mongodb.ClientEncryptionSettings;
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.vault.ClientEncryption;
import com.mongodb.client.vault.ClientEncryptions;
import java.util.Base64;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MongoEncryptionConfiguration {

    @Bean(destroyMethod = "close")
    ClientEncryption clientEncryption() {
        byte[] localMasterKey = Base64.getDecoder().decode(
            requiredEnv("LOCAL_KMS_KEY_BASE64")
        );
        if (localMasterKey.length != 96) {
            throw new IllegalArgumentException(
                "Local KMS master key must contain exactly 96 bytes"
            );
        }

        MongoClientSettings keyVaultClientSettings =
            MongoClientSettings.builder()
                .applyConnectionString(
                    new ConnectionString(requiredEnv("MONGODB_URI"))
                )
                .build();

        ClientEncryptionSettings encryptionSettings =
            ClientEncryptionSettings.builder()
                .keyVaultNamespace("encryption.__keyVault")
                .keyVaultMongoClientSettings(keyVaultClientSettings)
                .kmsProviders(
                    Map.of("local", Map.of("key", localMasterKey))
                )
                .build();

        return ClientEncryptions.create(encryptionSettings);
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

The **ClientEncryption** object manages DEK creation and explicit encryption/decryption operations. In this example, **keyVaultMongoClientSettings** specifies the connection settings for reading/writing the key vault. In real systems, the key vault connection may use separate credentials and a separate deployment.

If the native encryption library or matching configuration is missing, the driver may throw an error when invoking encryption operations. Install the crypto dependency/component matching the MongoDB Java Driver version in use.

### 7.2. Creating a Key and Encrypting/Decrypting a Value

~~~java
import com.mongodb.client.model.vault.DataKeyOptions;
import com.mongodb.client.model.vault.EncryptOptions;
import com.mongodb.client.vault.ClientEncryption;
import java.util.List;
import org.bson.BsonBinary;
import org.bson.BsonString;
import org.springframework.stereotype.Service;

@Service
class CustomerSensitiveDataService {

    private final ClientEncryption encryption;

    CustomerSensitiveDataService(ClientEncryption encryption) {
        this.encryption = encryption;
    }

    // Call only in a controlled key provisioning workflow.
    BsonBinary provisionCitizenIdKey() {
        return encryption.createDataKey(
            "local",
            new DataKeyOptions()
                .keyAltNames(List.of("customers-citizen-id-v1"))
        );
    }

    BsonBinary encryptCitizenId(BsonBinary dataKeyId, String plaintext) {
        return encryption.encrypt(
            new BsonString(plaintext),
            new EncryptOptions("AEAD_AES_256_CBC_HMAC_SHA_512-Random")
                .keyId(dataKeyId)
        );
    }

    String decryptCitizenId(BsonBinary ciphertext) {
        return encryption.decrypt(ciphertext).asString().getValue();
    }
}
~~~

**What the example shows:**

- **createDataKey("local", ...)** generates a DEK, wraps it using the local master key, writes the document to the key vault, and returns the key ID.
- **encrypt(...)** uses the specified DEK to encrypt the value; the result is an encrypted BSON binary, not a plain text string.
- **decrypt(...)** recovers plaintext when access to the key vault and matching KMS provider is available.
- The **Random** algorithm ensures encrypting the same plaintext multiple times can produce different ciphertexts; suitable when direct comparison searches on the encrypted value are not needed.

This is an example of **explicit encryption**: the code actively invokes **encrypt** and **decrypt**. The `ClientEncryption` bean above **does not automatically cause every `MongoTemplate`/`MongoRepository` to encrypt fields**. To store ciphertext from this example, design appropriate mapping/codecs to preserve the BSON encrypted binary; do not convert ciphertext into a string or accidentally write plaintext back.

**Do not call `provisionCitizenIdKey` per document or per request.** Creating a DEK is a controlled administrative action. On startup or in a job, the application should look up the provisioned key by alias/ID, handle the case where the key already exists, and reuse it for the designed data scope.

### 7.3. When Do `MongoTemplate` and Repositories Encrypt Automatically?

In **automatic encryption**, the **MongoClient actually used by Spring Data MongoDB** must be configured with **AutoEncryptionSettings** containing:

- **keyVaultNamespace** and required key vault access settings.
- **kmsProviders** and credentials/key identifiers.
- Schema or metadata specifying which fields to encrypt, algorithms, and corresponding DEKs.
- Driver encryption libraries/components matching the MongoDB mechanism and deployed version.

Conceptual partial driver configuration example:

~~~java
import com.mongodb.AutoEncryptionSettings;
import com.mongodb.MongoClientSettings;
import java.util.Map;

// kmsProviders and encryptedFieldsMap/schemaMap are built
// from actual deployment configuration, not an arbitrary empty map.
AutoEncryptionSettings autoEncryptionSettings =
    AutoEncryptionSettings.builder()
        .keyVaultNamespace("encryption.__keyVault")
        .kmsProviders(kmsProviders)
        .build();

MongoClientSettings appClientSettings = MongoClientSettings.builder()
    .applyConnectionString(connectionString)
    .autoEncryptionSettings(autoEncryptionSettings)
    .build();
~~~

This snippet illustrates where configuration goes, not a complete runnable setup: you must provide **kmsProviders**, **connectionString**, encrypted field descriptors, and the corresponding crypto components. The application must use the **MongoClient** created from `appClientSettings`; configuring a separate client does not affect the client created by Spring Data.

When automatic encryption is active and properly declared, `MongoTemplate`/repository operations on applicable fields can encrypt and decrypt per client settings. When using **Queryable Encryption**, follow the corresponding supported algorithms/query types and collection creation workflow; **do not** take the `Random` algorithm from the explicit CSFLE example and assume it supports queries on ciphertext.

## 8. Replacing the Local Provider With an External KMS

With an external KMS, configuration splits into two parts:

- **KMS provider credentials:** the application's permission to call the KMS service API, which should come from a managed identity mechanism (such as a role or workload identity) rather than hardcoded secrets.
- **Master key descriptor:** information identifying the master key to wrap DEKs, such as the region and ARN of an AWS KMS key.

Example descriptor *format* when creating a DEK on AWS; illustrative values must be replaced with configuration provided by your operations team:

~~~java
import com.mongodb.client.model.vault.DataKeyOptions;
import org.bson.BsonBinary;
import org.bson.BsonDocument;
import org.bson.BsonString;
import java.util.List;

// clientEncryption is configured with the "aws" provider and valid permissions.
BsonDocument masterKey = new BsonDocument()
    .append("region", new BsonString("ap-southeast-1"))
    .append("key", new BsonString(
        "arn:aws:kms:ap-southeast-1:123456789012:key/example-key-id"
    ));

BsonBinary dataKeyId = clientEncryption.createDataKey(
    "aws",
    new DataKeyOptions()
        .masterKey(masterKey)
        .keyAltNames(List.of("customers-citizen-id-v2"))
);
~~~

This pattern only illustrates **how to choose a master key when creating a DEK**, assuming you already have a `ClientEncryption` configured for AWS KMS. This code cannot be used standalone without provider credentials, permission policies, KMS connectivity, and a key vault. For Azure/GCP/KMIP, the descriptor format differs; follow documentation for your exact driver/KMS version.

### Permissions and Protection Scope

An application may have permission to read a business collection while lacking access to the key vault or KMS. Conversely, read access to the key vault does not grant decryption capability without permission to use the master key. This enables separation of duties across business applications, key-provisioning services, and administrative tasks.

Clearly define:

1. Which services are allowed to create new DEKs, read keys, and request KMS decryption.
2. Which services may only read encrypted documents without obtaining plaintext.
3. Who may edit aliases, alter key metadata, restore backups, and initiate rotations.
4. How credentials are managed across development, CI, and production environments.

Do not confuse **field encryption** with **system-wide access control**: MongoDB permissions, secret management, TLS, auditing, and application authorization remain essential.

## 9. Key Lifecycle Management: Provisioning, Usage, Rotation, and Recovery

### 9.1. DEK Provisioning

When deploying a new service, an administrative job can create DEKs once and record their IDs/aliases. You should:

- Name keys by business scope and versioning policy, e.g., **customer-identity-v1**.
- Create the unique index on `keyAltNames`.
- Ensure repeated key creation does not cause drift; if a valid key already exists, reuse it per defined procedure.
- Separate key-creation permissions from day-to-day document read/write permissions whenever possible.

### 9.2. Master Key Rotation vs. DEK Rotation

| Operation | What Changes | Must Document Data Be Re-Encrypted? |
| --- | --- | --- |
| **Rewrap DEK with another master key** | Changes the protection layer wrapping the DEK in the key vault, e.g., migrating to a new KMS key. | In principle **no**, if the DEK encrypting documents stays the same; verify version capabilities and APIs. |
| **Create new DEK and migrate data** | New or migrated data values will use a different DEK. | **Yes** for old data that needs to move to the new DEK: must decrypt and re-encrypt according to plan. |
| **Change keyAltName** | Changes alias/metadata referencing the key. | Does not make existing ciphertext use a new DEK. |
| **Disable/delete old master key or DEK** | Can cut off access to unwrap existing data. | Risk of **losing decryption capability**; perform only after verifying which data and backups still depend on that key. |

Some MongoDB Driver versions provide **rewrapManyDataKey** to rewrap DEKs under a new provider/master key. Availability, library requirements, and parameters vary by version; design testing and rollback procedures before running in operations.

**Crucial point:** decryption paths for previously written data may continue to depend on old DEKs long after the application switches to a new DEK. Never delete a key just because all new records use a different key.

### 9.3. Backup and Disaster Recovery

To recover client-side encrypted data, backing up only the business collection is insufficient. Ensure:

- Consistent backups of both the **data collection** and the **key vault**, plus the ability to restore key IDs/metadata.
- The master key remains accessible after recovery, including KMS permissions, region/endpoint, version, and associated service identity.
- Local secret management (if used) has its own backup and recovery process.
- Test restores in an isolated environment: read old ciphertext, unwrap DEKs, and verify decryption with a client of matching version/configuration.

### 9.4. Auditing and Key Lifetimes

Track key creation, alias changes, KMS permission changes, decryption failures, and rotation activities through appropriate audit systems. Never write **master keys**, **plaintext DEKs**, or **decrypted values** to logs. Key metadata may also reflect business information; expose only what is necessary.

## 10. Common Errors and How to Diagnose Them

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| DEK / key ID not found | Wrong key vault namespace, wrong deployment, key not created, or missing read permission. | Check `keyVaultNamespace`, key ID/alias, connection account, and backups. |
| KMS denies access or times out | Credentials, master key usage permissions, endpoint, TLS, or network path. | Verify service identity, policies, network routing, and KMS latency. |
| Key creation fails with duplicate `keyAltNames` | Multiple provisions of the same alias or concurrent jobs running. | Check unique index and make provisioning controlled/idempotent. |
| Read data remains ciphertext | Using a client not configured for decryption, or explicit encryption without calling `decrypt`. | Check the actual driver/client used by `MongoTemplate` and key vault/KMS configuration. |
| Cannot decrypt old data after rotation | Lost old master key/DEK, misconfigured provider change, or deleted key vault. | Restore corresponding permissions and keys; proceed with migration only when old data can be decrypted. |
| Query on encrypted field returns no results | Algorithm does not support query type, wrongly encrypted filter, or missing QE/CSFLE setup. | Identify encryption mode, algorithm, supported queries, and compare with metadata. |
| Application works on machine A but fails on machine B | Missing native crypt library, wrong environment variables, wrong KMS credentials, or different driver version. | Compare dependencies and deployment configuration; check each layer from key vault connection to KMS. |

### Ordered Diagnostic Procedure

1. **Confirm failure scope:** did DEK creation, ciphertext write, ciphertext read, or decryption fail?
2. **Check MongoDB:** is the application targeting the right cluster, database, and `keyVaultNamespace`?
3. **Check metadata:** does the key ID/alias exist, was it validly created, and is it readable? Do not print `keyMaterial` to logs.
4. **Check KMS:** is the provider right, does the master key exist, do credentials have permission, and is the network reachable?
5. **Check driver/Spring:** are encryption dependencies present, versions compatible, and is the right `MongoClient` with `AutoEncryptionSettings` or explicit logic being used?
6. **Test a single document in a controlled environment:** encrypt, store, read, and decrypt with an authorized client; retain safe status logs for analysis.

## 11. Design Scenarios in Spring Data MongoDB Applications

**Scenario A — Customer profile management application:** Collection **customers** has **name**, **citizenId**, and **createdAt**. Policy requires only one service to read `citizenId`. You can isolate permissions for this service, use a DEK for `citizenId`, and choose explicit or automatic encryption. Other services can still access unencrypted fields under their own permissions.

**Scenario B — Multi-tenant isolation requirements:** Each tenant or tenant group can be assigned a dedicated DEK per policy, combined with key vault/KMS access controls and a provisioning workflow. Measure the overhead of managing many DEKs, KMS calls, and cache behavior; do not assume "one DEK per tenant" is mandatory by default.

**Scenario C — Need to search customers by confidential ID:** If using the **Random** algorithm in the examples, you cannot assume plaintext equality queries will work. Evaluate an encryption feature supporting queries (e.g., Queryable Encryption with the right query type and supported version), along with information leakage and data constraints. Never switch to deterministic encryption solely to make a query work without assessing risk.

**Scenario D — Migrating from local KMS to a managed KMS:** Build the new provider configuration, prepare permissions, and plan rewrap/migration per driver version while preserving the ability to read old data. Test backups, rollback, and effects on client caches before decommissioning the local configuration.

## 12. Pre-Production Checklist

1. **Choose the right encryption layer:** identify fields to protect, restricted roles, and queries to support; distinguish CSFLE from Queryable Encryption.
2. **Design the key vault:** namespace, deployment target, unique partial index, backups, and read/write permissions.
3. **Choose DEK strategy:** which data groups share keys, alias naming, provisioning, ID tracking, and key lifetimes.
4. **Configure KMS:** master keys/KEKs, identities, permissions, networking, and monitoring; never store secrets in Git or logs.
5. **Wire Spring Data MongoDB:** distinguish explicit from automatic encryption; ensure `MongoTemplate`/repositories use the right `MongoClient` and codecs/mappings.
6. **Functional testing:** written data is ciphertext, authorized apps can decrypt, unauthorized apps cannot obtain plaintext.
7. **Operational testing:** KMS timeouts, key vault disconnects, rotation, backup restores, migrations, and reading historical data.
8. **Monitor performance:** client crypto latency, key vault/KMS access times, caching, throughput, and encrypted-field query costs.

### Self-Check Questions

**1. Why does having read access to the key vault not guarantee you can decrypt?** Because the key vault contains **wrapped DEKs**; the client also needs access to the corresponding master key from the KMS provider to unwrap the key.

**2. Why shouldn't you create a new DEK on every `repository.save()` call?** Doing so increases key count, management overhead, and rotation/recovery complexity. Normally DEKs are provisioned for a designed data scope and reused in a controlled manner.

**3. Does rewrapping a DEK mean all documents are re-encrypted?** No. Rewrapping changes the protection layer around the DEK; re-encrypting data with a new DEK is a separate operation.

**4. Once a `ClientEncryption` bean is created, does `MongoTemplate` automatically encrypt all fields?** No. Explicit encryption requires calling `encrypt`/`decrypt`; automatic encryption requires configuring `MongoClient`, encryption schemas/metadata, and driver crypto components.

**5. What happens if data backups are intact, but the KMS master key is lost?** You may be unable to unwrap DEKs in the key vault and lose the ability to decrypt the corresponding data. Backup design must include key recoverability.

## Conclusion

In Spring Data MongoDB, the **key vault**, **DEK**, and **KMS provider** form the trust chain of client-side encryption: **the key vault stores wrapped DEKs, the KMS protects master keys, and DEKs encrypt document values in the application**. Sound design requires choosing algorithms/features based on query needs, controlled key provisioning, separate permissions for data and keys, secure secret storage, and tested rotation and recovery procedures. `MongoTemplate` and repositories remain the data access layer, while how encryption occurs depends on MongoDB Java Driver configuration and your data protection policy.
