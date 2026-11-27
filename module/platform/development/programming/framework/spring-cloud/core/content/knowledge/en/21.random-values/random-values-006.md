# Usage Limits for Instance IDs, Security Keys, and Persistent Identifiers

## 1. Random Values Do Not Solve Every Kind of Identifier

Spring Boot provides `RandomValuePropertySource` to inject random values into configuration. Placeholders such as `${random.uuid}`, `${random.int}`, or `${random.value}` are useful when an application needs a temporary value at startup, such as a run ID, test data, or a default value used in development environments.

However, the following three needs have different requirements:

- **Instance ID:** identifies a single run or an instance registered in a service registry. The ID may change when the instance is recreated, yet it must distinguish concurrently existing instances.
- **Security key:** protects data or authenticates a transaction. Keys require a secure random source, sufficient entropy, and dedicated storage, access control, backup, and rotation lifecycles.
- **Persistent identifier:** identifies the same record or entity across multiple restarts, deployments, and data migrations. The value must be generated once and persisted.

Using a single random placeholder for all three purposes easily causes failures: the registry treats a restarted process as a new instance, old ciphertext cannot be decrypted after the key changes, or a record receives a different ID every time the application starts.

This lesson belongs to the **Random Values** chapter of the **SPRING_CLOUD_CORE** module. The module focuses on Spring Cloud Commons, Spring Cloud Context, externalized configuration, Spring Boot compatibility, refresh scope, discovery, service registries, service communication, and how to test/operate common abstractions.

After this lesson, learners will be able to:

- Read and bound the usage of Spring Boot's `random.*` placeholders.
- Explain why a startup random value is not a persistent identifier.
- Choose an instance ID suited to the lifecycle of a process, container, or Pod.
- Distinguish random IDs from tokens/keys that must resist guessing.
- Generate key material using a CSPRNG and manage it via a secret manager or KMS.
- Design data IDs with practical uniqueness and durable storage.
- Evaluate collision, entropy, restarts, scale-out, rotation, and recovery.
- Write tests for ID stability or rotation according to actual requirements.

## 2. Spring Boot's RandomValuePropertySource

### 2.1. Supported Placeholders

Spring Boot registers `RandomValuePropertySource` in `Environment`. Current documentation describes the main values:

| Placeholder | Result |
| --- | --- |
| `${random.value}` | A random string/bytes value per the implementation |
| `${random.int}` | A random integer |
| `${random.long}` | A random 64-bit integer |
| `${random.uuid}` | A random UUID |
| `${random.int(10)}` | Integer from 0 to 10, excluding 10 |
| `${random.int[1024,65536]}` | Integer from 1024 to 65535 |
| `${random.long[1000,9000]}` | Long integer from 1000 to 8999 |

The range syntax has the form `OPEN min,max CLOSE`. The opening and closing characters can be parentheses or square brackets; the upper bound is always **exclusive**. If only one bound is passed, Spring Boot uses 0 as the lower bound and that value as the upper bound.

YAML configuration example:

```yaml
app:
  diagnostics:
    boot-id: "${random.uuid}"
    sample-bucket: "${random.int[0,100]}"
    temporary-value: "${random.value}"
```

Equivalent in properties:

```properties
app.diagnostics.boot-id=${random.uuid}
app.diagnostics.sample-bucket=${random.int[0,100]}
app.diagnostics.temporary-value=${random.value}
```

In YAML, wrap placeholders containing brackets or special characters in quotes so the parser handles them as scalars. With `random.int[0,100]`, possible values are 0 through 99.

### 2.2. Values Are Generated When the Property Is Read

`RandomValuePropertySource` is a property source that generates values when queried. It is not a data store capable of remembering generated values across subsequent runs.

Therefore:

- A value bound to a configuration bean at startup typically stays in that bean until the bean is recreated or configuration is rebound.
- When the process restarts and the property is resolved again, the random value may differ.
- Do not assume two resolutions of the same `${random.uuid}` expression in two different places will receive the same UUID.
- Do not use a random value as a default that must stay stable across restarts unless it has been persisted in a durable location.

If multiple components must share the same value, establish a clear owning source and pass that value via a bean/configuration, or persist it in a store with an appropriate lifecycle. Do not let each component independently resolve a random placeholder and expect them to match.

### 2.3. A Random Placeholder Is Not a Storage Contract

Example:

```yaml
app:
  encryption:
    key: "${random.value}"
```

The application may start with a new value on the next run. If this value was used to encrypt data and not persisted, the application can lose the ability to decrypt data created in the previous run.

Similarly:

```yaml
app:
  customer:
    id: "${random.uuid}"
```

This is merely a configuration value resolved within the application lifecycle. It does not create a customer record, does not write an ID to the database, and does not guarantee the customer keeps the same ID across restarts.

Clearly decide whether a value's lifecycle belongs to **a configuration resolution**, **a process run**, **an instance lifecycle**, or **a data lifecycle**. These lifecycles are not the same.

## 3. Using Random Values for Instance IDs

### 3.1. Service ID and Instance ID Are Two Different Concepts

In service discovery, distinguish:

| Concept | Meaning | Example |
| --- | --- | --- |
| Service ID | Logical name of the service | `inventory-service` |
| Instance ID | Identifier of a registered instance | `inventory-service:pod-7f9c` |
| Network address | Address to connect to the instance | `10.0.4.12:8080` |
| Process ID | OS PID of the process on a host | `18432` |
| Deployment identity | Identifier issued by the deployment platform | Pod UID, task ID, or VM ID |

Multiple instances share the same service ID, yet require distinct instance IDs so the registry can distinguish registrations. Spring Cloud Commons provides the `ServiceRegistry` and `Registration` abstractions; how instance IDs are generated and interpreted depends on the registry provider such as Eureka, Consul, or Zookeeper.

### 3.2. When Is a Random UUID Appropriate?

A random UUID can be appropriate for **a single instance run** when all of the following hold:

- Each startup is treated as a fresh registration.
- Concurrently running instances need distinct IDs.
- The registry supports updating, deregistering, or expiring old registrations.
- The system does not need to keep the same instance ID across restarts.
- The ID is not used as a service identifier or business data identifier.

Example configuring an application ID:

```yaml
spring:
  application:
    name: inventory-service

app:
  instance:
    id: "${INSTANCE_ID:${random.uuid}}"
```

Here, the deployment platform can provide `INSTANCE_ID`. When that variable is not supplied, Spring Boot resolves a random UUID as a fallback. The `app.instance.id` property is application-defined configuration; Spring Cloud Commons does not automatically use this property for every registry. The application must map it into the configuration or `Registration` of the provider in use.

### 3.3. When Should Platform-Issued Identifiers Be Used?

In container/orchestrator environments, the platform usually provides an identifier better suited to the instance lifecycle:

- Kubernetes Pod UID or a combination of namespace and Pod UID.
- ECS task ARN or task ID.
- Cloud-provider-assigned VM/instance ID.
- Host identity combined with port when the deployment model guarantees uniqueness of that pair.
- Deployment ordinal when an application runs stateful replicas with stable identities.

For example, with Consul Discovery, a platform-provided ID can be mapped to the provider-specific property:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        instance-id: "${INSTANCE_ID:${HOSTNAME:${random.uuid}}}"
```

This is Consul-specific configuration. For Eureka or another provider, property names and semantics may differ. Read the provider documentation instead of assuming a single common instance ID property across all implementations.

If using `HOSTNAME` as a fallback, verify that hostnames are genuinely unique within the registry scope. Short hostnames can collide across different namespaces, clusters, or environments. Pod UIDs or task IDs usually reflect the instance lifecycle more clearly.

### 3.4. Risks When a Random ID Changes After Restart

Suppose an instance registers with ID `inventory-service:4f...`. After a restart, `${random.uuid}` generates a new ID. The registry may see the new registration while the old registration has not yet been removed or its lease has not yet expired.

Consequences may include:

- Two registrations pointing to the same address during the transition period.
- The old registration remaining until health checks or TTL remove it.
- Dashboards and logs having difficulty correlating an instance before and after restart.
- Deregistration needing to target the exact old registration.
- Consumers temporarily receiving a stale address if caches have not updated.

Therefore, coordinate the ID with the registration lifecycle: register when the instance is ready, deregister on shutdown when possible, configure appropriate leases/health checks, and monitor registry propagation. Do not use random IDs to mask incomplete registration management.

### 3.5. Do Not Use Instance IDs as Service IDs or Data Identifiers

A service ID must be stable so consumers can call the service by its logical name. If each process generates a random service ID, consumers cannot know which name to call and the registry fills up with fragmented logical services.

An instance ID only identifies a registration. It should not replace:

- `spring.application.name` or the service name.
- IDs of customers, orders, payments, or business resources.
- IDs of a cluster or tenant whose lifecycle outlives an instance.
- Secrets/tokens used to authenticate requests.

## 4. Do Not Use Random Placeholders as Long-Lived Security Keys

### 4.1. Why Random Values in Configuration Are Not Enough

Spring Boot documentation describes `RandomValuePropertySource` as a utility for injecting random values into configuration, such as secrets or test values. However, placeholders do not manage key lifecycles.

An encryption key must remain stable for as long as data protected by that key still needs to be read. If a new key is generated on every startup:

1. Process A generates key K1.
2. The application encrypts data using K1.
3. Process A terminates.
4. Process B starts and resolves key K2.
5. Old data still requires K1, yet the application now only has K2.

Without a safely stored copy of K1 and a key-version selection mechanism, old data may become undecryptable.

Even if a given Spring Boot version's implementation uses a secure random source, that still does not turn `RandomValuePropertySource` into a KMS, secret manager, or durable keystore.

### 4.2. Random Integers Lack Sufficient Key Space

Do not use expressions such as:

```yaml
security:
  api-key: "${random.int[0,1000000]}"
  encryption-key: "${random.long}"
```

An integer among one million values only provides roughly 20 bits of search space. A 64-bit integer also fails modern encryption key requirements by default, and numeric representations can strip leading bits or cause type conversion issues.

Keys must be generated according to the algorithm and size required by the protocol, using an appropriate CSPRNG source. Do not choose a length simply because a string looks long or hard to read.

### 4.3. Using SecureRandom to Generate Key Material

In Java, `java.security.SecureRandom` provides a cryptographically strong pseudo-random number generator. The following example illustrates generating a 256-bit AES key:

```java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyGeneration {

    private KeyGeneration() {
    }

    public static SecretKey newAes256Key()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, new SecureRandom());
        return generator.generateKey();
    }
}
```

This snippet illustrates generating key material. In production systems, provision keys through a key management process: store keys in KMS/HSM or a secret manager, assign versions/aliases, restrict identities allowed to use the key, and ensure backup/recovery.

Do not invoke key generation on every startup if the application needs to continue decrypting previously encrypted data. The application should retrieve the appropriate key version from the keystore according to its policy.

### 4.4. Generating Random Tokens Differs from Creating Encryption Keys

A bearer token or password reset token needs to be unguessable, though it does not necessarily have to be an AES key. Use a CSPRNG to generate enough random bytes and encode them in an appropriate representation:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class TokenGenerator {

    private static final SecureRandom RANDOM = new SecureRandom();

    private TokenGenerator() {
    }

    public static String newToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
```

A 32-byte token contains 256 bits of random data before Base64URL encoding. Tokens need expiration, purpose scoping, single-use semantics where appropriate, and secure storage. For bearer authentication tokens, the server can store only a hash of the token to reduce risk if the database is read.

Do not use UUIDs as security capabilities. UUIDs are primarily identifiers; RFC 9562 warns against assuming UUIDs are unguessable or treating possession of a UUID as proof of authorization. If possession of a string grants access to a sensitive action, generate a proper security token.

### 4.5. Do Not Seed with Time or Predictable Data

Avoid the following patterns for secrets:

```java
Random random = new Random(System.currentTimeMillis());
String token = Long.toHexString(random.nextLong());
```

Current time, PID, hostname, MAC address, or a counter do not provide sufficient entropy and can be guessed. Also do not call `SecureRandom.setSeed(System.currentTimeMillis())` to replace the entropy source. `SecureRandom` self-seeds via its provider; if a special policy is needed, configure and evaluate the provider according to your environment's security standards.

Use the default `SecureRandom` for typical application needs or select a specific provider/algorithm per organizational policy. Do not pick an algorithm merely because its name sounds strong; verify provider support and platform requirements.

## 5. Persistent Identifiers Must Be Stored

### 5.1. Random UUIDs Can Serve as Primary Keys When Generated Once

UUIDv4 can be a good practical entity identifier when generated once at record creation time and stored in the database. Java provides:

```java
UUID id = UUID.randomUUID();
```

Entity example:

```java
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
class Order {

    @Id
    private UUID id = UUID.randomUUID();

    protected Order() {
    }

    UUID getId() {
        return id;
    }
}
```

The crucial point is that the UUID is assigned when creating a new entity and persisted with the record. When reading the record on a later run, the application retrieves the ID from the database; it does not regenerate the ID simply because the process started.

There must be a unique constraint or primary key constraint in the database. UUIDs make collision probability very low in practice, yet do not turn probability into an absolute mathematical guarantee. The database remains the place that enforces uniqueness for stored data.

### 5.2. Do Not Use Random Placeholders for Record IDs

The example below is unsuitable if the goal is to identify an order:

```yaml
app:
  order:
    id: "${random.uuid}"
```

This is a configuration value shared within a process/context, not an ID generated per order. Multiple orders could accidentally share that value; the next restart would resolve a different value.

Record IDs should be generated at the exact boundary of record creation:

- In the application/domain layer when creating an entity.
- In the database via an appropriate sequence/identity/default.
- In a dedicated ID service if a distributed architecture requires centralized coordination.
- Via a clearly chosen and tested distributed ID algorithm.

### 5.3. Choosing an ID Type by Requirements

| ID Type | Characteristics | When Appropriate |
| --- | --- | --- |
| Database sequence/identity | Sequential, requires database to issue ID | Data resides in one database or sequential numbers are required |
| UUIDv4 | Random, no cross-node coordination needed, high practical uniqueness | Distributed IDs without time-ordering requirements |
| UUIDv7 | Contains timestamp and random/counter bits, supports near time-based sorting | Need distributed IDs and locality/index ordering; exposing timestamp info is acceptable |
| Snowflake-like ID | Typically combines timestamp, node ID, and sequence | Systems needing ordered IDs and controlled worker/node identity |
| Platform-assigned ID | Tied to Pod/task/VM lifecycle | Identifying deployment instances |
| Stored-once random ID | Generated via CSPRNG and written to a data store | Entities needing opaque IDs that must remain durable |

RFC 9562 defines UUIDv4 and UUIDv7 along with UUID generation rules. UUIDv7 places a Unix milliseconds timestamp in the leading bits and uses remaining bits for entropy/counter depending on configuration. Time-ordered UUIDs can help index locality, though the timestamp also reveals the approximate creation time.

Java's `UUID.randomUUID()` creates a version 4 UUID. If the application needs UUIDv7, use an RFC 9562-compliant library or a platform-supported ID mechanism; do not manually assemble timestamp and random bits without verifying version/variant bits and standard rules.

### 5.4. Deterministic Identifiers from Stable Data

Some systems require the same input to always produce the same ID, such as mapping an external reference to an internal key. That is a deterministic identifier problem, not a random identifier problem.

You can use namespace/name-based UUIDs per appropriate standards or store a mapping table. Canonicalization, namespace, and algorithm must be chosen clearly; changing input normalization can produce different IDs. Name-based hashes/UUIDs are not authentication signatures and should not embed sensitive personal data in inferable values.

If input data has low entropy or is easy to guess, plain hashing does not hide it. Use a controlled mapping or a keyed construction when confidentiality must be protected.

## 6. Collisions and Uniqueness Limits

### 6.1. Birthday Bound

Given a space of `b` random bits and `n` generated values, when `n` is small relative to the space, the probability of at least one collision can be approximated as:

[
p \approx \frac{n(n-1)}{2^{b+1}}
]

The probability grows quadratically with the number of values. Therefore, reducing random bits or using a small numeric range can cause collisions much sooner than intuition suggests.

UUIDv4 has 128 bits in total, with version and variant bits reserved, leaving 122 random bits. Collision probability for UUIDv4 is very low for typical ID volumes, though not zero.

### 6.2. Uniqueness Constraints Are Still Required

Do not substitute probability for data constraints. For IDs stored in a database:

- Define a primary key or unique constraint.
- Handle duplicate key errors as a possible case.
- If the algorithm permits, generate a new ID and retry with a bound on collisions.
- Emit metrics/logs for duplicate ID errors to detect generator bugs or replayed data.
- Never overwrite an existing record when an ID collides.

For IDs distributed across multiple databases or regions, clearly define the uniqueness scope: a table, a database, the entire system, or multiple organizations. If the cost of a collision is severe, add a coordination mechanism or central registry rather than relying solely on random bits.

### 6.3. Random Integers Collide Easily in Small Spaces

For example, `${random.int[0,100]}` only has 100 possibilities. When multiple instances start concurrently, duplicate values are normal. This can serve as a sampling bucket or a randomly chosen number, yet is unsuitable as an instance ID or primary key.

Do not use a random port in production as a unique identifier without binding a socket and publishing the actual bound port. If a temporary port is needed in tests, let the OS allocate a free port and read the bound port.

## 7. Designing by Lifecycle

### 7.1. Decision Matrix

| Need | Suitable Value | Storage / Owning Source | What to Avoid |
| --- | --- | --- | --- |
| Single-boot ID for log tracing | Random UUID | Log context or startup metadata | Using it as the service ID |
| Short-lived instance ID | Pod UID/task ID; UUID if fallback needed | Platform metadata or registry registration | Failing to deregister/expire old registrations |
| Service name | Stable configured name | `spring.application.name` or service catalog | Random service name on every boot |
| Encryption key | Key from CSPRNG/KMS | KMS, HSM, Vault, or secret manager | Regenerating with `${random.value}` on every restart |
| Bearer token/reset token | Sufficient-entropy token from SecureRandom | Client receives once; server stores hash/expiry | UUID or random integer as access credentials |
| Entity primary key | UUID/sequence/ID service | Database | Placeholder in application.yml |
| Cross-system linking ID | Persistent ID or stored mapping | Versioned database/catalog | Regenerating randomly on every sync |
| Test fixture | Seeded/controlled random value when reproducibility is needed | Test setup | Relying on unfixed randomness causing flaky tests |

### 7.2. Choosing Storage by Lifecycle

Ask how long the value must exist:

- **For a single configuration read:** a random placeholder may suffice.
- **Within one process:** bind to a bean or hold in application state.
- **For an instance lifecycle:** obtain the ID from the platform or registration provider.
- **Across restarts/deployments:** persist in a database, secret manager, or durable metadata.
- **Across multiple services/regions:** use an ID scheme and uniqueness constraints with clearly defined scope.

Do not store security keys in `application.yml` just to make them reusable. Store key material in a keystore, and grant the application permission to use the appropriate key/version via workload identity.

## 8. Testing and Operations

### 8.1. Testing Random Properties

Do not assert a specific hardcoded value for `${random.uuid}` or `${random.int}`. Instead, verify:

- The UUID parses cleanly and matches the expected format.
- The integer lies in the min-inclusive/max-exclusive range.
- The value binds to the expected property/type.
- The value can change between two context creations if the test verifies ephemeral behavior.
- Tests do not depend on random ordering across test cases.

Example testing a UUID:

```java
UUID bootId = UUID.fromString(environment.getRequiredProperty("app.diagnostics.boot-id"));
assertThat(bootId).isNotNull();
```

If deterministic testing is needed, inject a fixed ID via a test property source rather than trying to predict random outputs.

### 8.2. Testing Instance Registration

An integration test for a service registry should:

1. Start an instance with a stable service ID.
2. Verify the instance ID appears in the registration.
3. Start a second instance and verify IDs do not collide in the same registry.
4. Stop the first instance and verify deregistration/lease expiry.
5. Restart and verify ID semantics: preserved if using a stable platform identity, or changed if intentionally process-scoped.
6. Verify the registry stops returning the old endpoint after the expected propagation window.

Do not inspect only the `app.instance.id` property; verify that the provider actually uses that value when registering.

### 8.3. Testing the Key Lifecycle

For encryption keys:

- Encrypt a fixture using key version K1.
- Restart the application and verify it still retrieves K1 to decrypt the fixture.
- Create K2 following the rotation procedure.
- Verify new data uses K2 while old data remains readable during the transition period.
- Revoke K1 only after data/backups have been processed according to policy.
- Verify KMS/secret manager access permissions and audit logs.

Do not print key bytes, plaintext secrets, or bearer tokens into test logs. Use synthetic fixtures; never put production keys into unit tests.

### 8.4. Testing Persistent IDs

For entity IDs:

- Create an entity and save it to the database.
- Close the context or restart the process.
- Read the entity back and verify the ID has not changed.
- Attempt to insert a duplicate ID and verify the unique constraint rejects it.
- For distributed IDs, test imports/replays and data from multiple nodes.

## 9. Common Errors and Resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Instance ID changes after every restart | Using `${random.uuid}` as fallback or primary value | Decide between process-scoped or platform-scoped ID; use Pod/task/VM identity if stability is needed |
| Registry keeps stale instances | Missing deregistration or overly long lease/health timeout | Check shutdown hooks, registration lifecycle, and TTL |
| Multiple properties get different UUIDs | Each placeholder resolution can generate a new value | Create an ID-owning bean or pass the same resolved value |
| Old ciphertext fails to decrypt after restart | Encryption key regenerated on startup | Retrieve versioned keys from KMS/Vault and plan rotation |
| Random integers collide | Value space is too small | Use an ID scheme with sufficient space and a unique constraint |
| UUID used as an access token | Confusing an ID with a security capability | Generate bearer tokens via CSPRNG with expiry and single-use policy |
| Record IDs change on deploy | ID generated from runtime configuration instead of stored | Generate ID on entity creation and persist in the database |
| Flaky tests | Tests depend on random order or collision assumptions | Inject deterministic fixtures and assert invariants |
| Nodes share the same instance ID | Configuration value copied across replicas | Use per-pod/task/VM identity or a distributed generator |
| Key rotation breaks old data | Old key revoked before re-encrypting or preserving old key version reads | Use key versioning and test migration/restore |

## 10. Selection and Operational Checklist

Before shipping a random value to production, confirm:

1. Does this value identify a resolution, a process, an instance, or a data entity?
2. Must it remain unchanged across restarts or deployments?
3. Must it be unique across replicas, clusters, or regions?
4. Is the collision domain understood and acceptable?
5. If it is an instance ID, which property does the registry provider actually use?
6. Are deregistration, health checks, or lease expiry configured for old registrations?
7. If it is a key/token, is the source a CSPRNG with sufficient entropy?
8. Is the key stored in KMS/HSM/Vault/secret manager instead of regenerated on every startup?
9. Are key versioning, rotation, backup, and recovery in place?
10. If it is a data ID, is the value durably persisted with a unique constraint?
11. Is a UUID being used as a bearer token or security capability?
12. Do tests verify invariants instead of depending on specific random values?
13. Could logs accidentally print keys, tokens, or sensitive data?
14. Do provider docs and the runtime Spring Boot version match the actual configuration?

## 11. Official References

- [Spring Boot — Externalized Configuration, Configuring Random Values](https://docs.spring.io/spring-boot/reference/features/external-config.html): syntax for `random.value`, `random.int`, `random.long`, `random.uuid`, and range bounds.
- [RandomValuePropertySource API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html): generated value types and property source configuration.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `ServiceRegistry`, `Registration`, auto-registration, and discovery.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): service discovery configuration and provider-specific instance metadata.
- [Java SecureRandom Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html): cryptographically strong random number generator, seeding, and thread safety.
- [Java UUID Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/UUID.html): `UUID.randomUUID()` generating version 4 UUIDs via CSPRNG.
- [RFC 9562 — Universally Unique Identifiers](https://www.rfc-editor.org/rfc/rfc9562.html): UUIDv4, UUIDv7, collision resistance, unguessability, and limits on using UUIDs as security capabilities.

**Remember:** Spring Boot's random placeholders are convenient for temporary configuration values. Instance IDs must match the registration lifecycle; security keys require a CSPRNG and key management; data identifiers must be generated once, stored durably, and have uniqueness enforced by the database or a coordination mechanism.
