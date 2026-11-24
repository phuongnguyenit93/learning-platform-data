# Masking or Hashing Sensitive Identifiers in Spring Framework Application Events

## 1. Goals and Design Principles

Spring Framework Application Events allow components within an application to communicate via a publish/subscribe model. However, when publishing events about customers, accounts, users, orders, devices, or login sessions, identifying data can **travel beyond its original scope**: multiple listeners read the payload, write logs, attach attributes to traces, emit metrics, spawn async tasks, or forward the event to an outbox/message broker.

A common mistake is thinking that internal events only run inside the JVM and can therefore freely carry emails, phone numbers, customer IDs, session IDs, addresses, tokens, or entire entities. In practice, events can be printed via `toString()`, retained in queues, serialized at integration boundaries, or exposed in error reports.

This lesson focuses specifically on **masking, removing, or hashing sensitive identifiers** in the context of Spring Application Events:

- Identifying direct and indirect identifiers, as well as the channels that can leak data.
- Choosing between **omitting**, **redacting/masking**, **keyed HMAC pseudonymization**, **random opaque IDs**, and **encryption**.
- Understanding why plain SHA-256 hashing of predictable emails/phone numbers/IDs is usually **insufficient protection**.
- Designing events to carry only minimal business data and purpose-appropriate references.
- Writing Java 17+ with `Mac(HmacSHA256)` and Spring `@EventListener`, including runnable Gradle code, safe output, and JUnit 5 tests.
- Managing keys, tenant/domain separation, key rotation, retention, logging/metrics/tracing, and leak-prevention testing.
- Avoiding confusing **pseudonymization** with **anonymization**, or using hashed tokens as proof of authorization.

**Priority principle:** If a listener does not need an identity, **do not put the identity into the event**. If occurrences must be linked without exposing the raw identifier, use an appropriate pseudonymization mechanism and govern keys properly. "Already hashed" does not automatically make data anonymous or safe to publish.

## 2. Where Do Spring Application Events Travel?

Typical path:

~~~text
Controller / Domain Service
            |
            | raw data used in business logic
            v
ApplicationEventPublisher.publishEvent(event)
            |
            v
ApplicationEventMulticaster
            |
            +--> AuditListener ----------> log / SIEM
            |
            +--> NotificationListener ---> email / HTTP
            |
            +--> AnalyticsListener ------> metrics / tracing
            |
            +--> AsyncListener ----------> executor queue
            |
            +--> IntegrationListener ----> outbox / broker
~~~

`ApplicationEventPublisher.publishEvent(Object)` allows publishing POJOs/records without necessarily subclassing `ApplicationEvent`. Spring supports `@EventListener` to receive events by type. With the default multicaster, regular listeners run synchronously on the publisher thread; with `@Async` or an executor, the event may live longer in a task queue.

**Spring does not automatically redact, encrypt, or hash event fields.** Any bean eligible to receive that event type can read the payload passed to it by reference. An event being dispatched in-process does not mean the payload is scoped to each listener's business permissions.

In code:

~~~java
// Design to review: raw email and entity are shared broadly.
publisher.publishEvent(new CustomerUpdated(customerEmail, customerEntity));
~~~

If a listener logs `event.toString()`, a record directly holding an email can automatically print that email into logs. If `customerEntity` holds an object graph or sensitive tokens, the event holds references to them too.

**Protect at payload design time first**, then continue restricting data at output sinks. Performing redaction only inside a log appender does not stop other listeners from reading the data off the event.

## 3. Direct Identifiers, Indirect Identifiers, and Linkability

Not every ID is harmless. A value can become sensitive when combined with other data.

| Data Category | Synthetic Example | Risk |
| --- | --- | --- |
| Direct identifier | Email, phone, full name, document number | Can directly identify an individual |
| Internal ID | `customerId`, `accountId`, `patientId` | Lookup or linkage to personal records |
| Session identifier | Session ID, refresh token, API token | Can act as a credential if disclosed |
| Device identifier | Device ID, advertising ID | Tracking activity by device |
| Indirect identifier | IP, address, timestamp, location, attribute combinations | Can re-identify when joined with other data |
| Business ID | Order/payment/document ID | Can link to sensitive data and should not be logged publicly |
| Correlation ID | Request ID, trace ID, event ID | Usually does not directly identify a person, yet can link actions or cause high-cardinality metrics |

An email turned into a stable HMAC string can still let a system track "the same person" across multiple events. That is a **pseudonymous identifier**, not automatically fully anonymized data.

A random `UUID.randomUUID()` contains no email, yet if a database maps that UUID to a user and logs record many actions under the same UUID, linkability still exists. The protection level depends on **lookup capability, retention duration, who has access, and processing purpose**.

For sensitive data, determine upfront:

1. Who is the producer and which listeners will receive it?
2. Who needs the original identity; who only needs status/counts?
3. Does the event leave the process or get stored durably?
4. Do events for the same subject need to be joined?
5. What access level do owners of logs, metrics, traces, or DLQs have?
6. How long must the data be retained and how are deletion requests handled?

## 4. Choosing the Right Measure: Omit, Mask, Hash, Tokenize, or Encrypt

Techniques serve different goals. No single `hash()` function satisfies every security requirement.

| Technique | Mechanism | Use When | Limitations |
| --- | --- | --- | --- |
| **Data minimization** | Exclude identifiers from events | Handlers need no identity | Less information for correlation |
| **Redaction** | Replace with `[REDACTED]` or drop entirely | Only knowing the event occurred matters, not identity | Cannot track the same subject |
| **Masking** | Show only allowed portion, e.g., `***@example.test` | Authorized readers need a partial view | Remaining portion may still identify |
| **Plain SHA-256** | Keyless deterministic hash | Integrity checks on high-entropy data with fitting goals | Predictable inputs are vulnerable to dictionary/enumeration |
| **HMAC-SHA256** | Secret-keyed hash | Scoped stable reference needed without emitting raw ID | Anyone with the key and candidate list can compute tokens; tokens remain linkable |
| **Random opaque ID** | Random token + protected mapping | Consumer needs authorized lookup of real identity | Must manage mapping/lifecycle/retention |
| **Encryption** | Keyed reversible encryption | Authorized consumer must recover original data | Key, nonce, access control, and protocol complexity |
| **Aggregation** | Send only totals/statistics | Analytics need no per-user events | Loss of detail; must evaluate small-group inference risk |

**Selection rule:** No linkage needed → omit or redact; linkage needed without reversal → scoped keyed HMAC; real identity lookup needed → random opaque reference with restricted mapping; data must be sent for legitimate recipient decryption → authenticated encryption with proper key management.

Do not use partial masking like `a***@domain.com` unless the system genuinely needs to display part of the address. On small datasets, the exposed characters may suffice to guess the subject.

## 5. Why Is SHA-256(email) Not Secure Enough?

A common flawed design:

~~~java
String exposedRef = sha256(email);
publisher.publishEvent(new CustomerChanged(exposedRef));
~~~

This is **illustrative code**, not a complete method/class. The flaw is not that SHA-256 is "broken" in the general preimage sense. The flaw is that many identifiers have a **small, structured, or predictable value space**.

An attacker holding the hashed email can compute SHA-256 over a list of candidate emails and compare results. For phone numbers, postal codes, sequential IDs, or a known set of user IDs, enumeration cost can be very low.

~~~text
SHA256("user1@example.test") -> hash A
SHA256("user2@example.test") -> hash B

Anyone with a candidate list can compute the exact same hash.
No "secret salt" needs to be known because there is no key here.
~~~

Variants must also be understood properly:

- **Per-record salt**: reduces precomputed rainbow tables and direct cross-record linkage, yet if the salt is stored alongside the hash an attacker can still test candidates against that salt; it does not turn predictable data into a secret.
- **A fixed public salt**: still allows recomputing all candidates and should not be treated as a key.
- **A secret pepper/key**: moves the design toward keyed hashing like HMAC, requiring real key management.
- **Truncating SHA-256**: merely discards bits from the digest without stopping candidate guessing, while increasing collision probability.

**Specifically:** Passwords, access tokens, OTPs, or session secrets should never appear in events. **Password storage** requires dedicated password-hashing/KDF algorithms (Argon2id, scrypt, bcrypt depending on the system), never plain SHA-256 or a demo HMAC event identifier.

## 6. HMAC-SHA256: Stable Pseudonyms with Clear Boundaries

HMAC uses a **secret key** and a message:

~~~text
digest = HMAC-SHA256(secretKey, canonicalInput)
ref    = formatVersion + Base64UrlNoPadding(digest)
~~~

Given the same key and input, HMAC returns the same digest. Someone who only sees the digest without the key cannot easily generate tokens for a guessed email list, provided the key stays secret and has sufficient entropy. However, anyone with the key or access to the token-generating service can recompute candidates, and identical digests still link multiple events together.

HMAC is **pseudonymization**, not guaranteed absolute anonymization. Nor is it **authorization**: a request sending a valid `subjectRef` does not mean the caller is allowed to read the corresponding profile.

### 6.1. Scoping by Tenant and Purpose

Do not use solely:

~~~text
HMAC(key, customerEmail)
~~~

across every feature, because the same email yields the same token across multiple modules, enabling cross-data linkage.

Better design:

~~~text
HMAC(
  key,
  lengthPrefix("spring-event/customer-preference/v1")
  || lengthPrefix(tenantId)
  || lengthPrefix(canonicalCustomerIdentifier)
)
~~~

Key points:

- **Purpose/domain separation**: a token used for customer preference events will not collide with a token used for billing audits, even with the same identifier and key.
- **Tenant separation**: an identifier in tenant A yields a different token in tenant B (with negligible collision probability).
- **Length-prefix encoding**: avoids ambiguity when concatenating strings, such as `("a","bc")` vs `("ab","c")`.
- **Version**: documents the canonicalization/encoding/algorithm contract so changes remain controlled.

### 6.2. Canonicalization Must Be Consistent

Strings `"Alice@example.test"` and `"alice@example.test"` may be treated as equal or distinct depending on the authoritative identity system. Do not arbitrarily lowercase all emails, Unicode-normalize, or strip characters unless the identity store uses the exact same rules. "Safe normalization" must follow the **business identity contract**, not a convenient ad-hoc hash helper.

Once the domain service has canonicalized the input, the pseudonymizer should preserve a consistent byte representation such as UTF-8. Do not let `Locale.getDefault()` or the OS timezone enter the ID-transformation path.

## 7. What Should the Event Payload Look Like?

For a listener that needs to know "a customer preference just changed" without needing the real email:

~~~java
public record CustomerPreferenceChanged(
        String subjectRef,
        String changeKind,
        Instant occurredAt) {}
~~~

This is a **minimal** event, not a `CustomerEntity` carrying email, phone number, address, session, and permissions.

Compare:

~~~java
// Risk: record.toString() may print the email.
public record UnsafeEvent(
        String email,
        String phone,
        Object customerEntity) {}

// Better approach when consumers only need correlation:
public record SafeEvent(
        String subjectRef,
        String changeKind) {}
~~~

If a consumer **truly needs the real customer ID** to query a database, one-way HMAC **cannot reverse itself** back to the original ID. There are three common patterns:

1. **Keep the ID inside the trust boundary if the recipient needs it to execute business work.** Use an internal event restricted to authorized subscribers/trust boundaries; do not serialize/log the raw ID to weaker channels.
2. **Use a random opaque ID + access-controlled mapping table.** Authorized listeners look up the reference to obtain the real ID; monitoring systems lack access to the mapping table.
3. **Use an intentional pseudonym index/lookup** if the data layer supports querying by precomputed token with proper key/rotation governance; never assume arbitrary `findById` repositories accept HMAC tokens.

For email senders, sometimes the task needs the real address. Do not replace the email with a hash in the event and then try to invent a nonexistent "unhash" function; instead, store a delivery job with a valid reference in protected storage and let an authorized worker dereference the data.

### 7.1. Publish POJOs Instead of Wrapping Raw Data in Source

Spring supports `ApplicationEvent` subclasses carrying `source`. If you choose that style, **`source` can also retain sensitive information**.

~~~java
// Consider carefully: source retains the raw CustomerEntity.
public class CustomerUpdatedEvent extends ApplicationEvent {
    public CustomerUpdatedEvent(CustomerEntity customer) {
        super(customer);
    }
}
~~~

This is illustrative without the `CustomerEntity` class. Do not sanitize custom fields while forgetting that `getSource()` still returns the raw entity. For many use cases, a record/POJO holding only permitted fields reduces data exposure surface.

## 8. Runnable Java 17+ Example with Spring and HMAC-SHA256

This example uses **Spring Framework 6.2.15**, `@EventListener`, and JDK crypto APIs. It publishes an event containing an **HMAC reference**, event type, and timestamp, **without the raw email**.

Key design notes:

- **To run immediately as a demo:** the application generates a random HMAC key when the Spring context initializes.
- **In production:** the key must come from an appropriate secret manager/keystore with sufficient entropy, stay consistent across restarts and instances when matching tokens are needed, and have a key ID and rotation process.
- **Never log** the key, raw identifiers, or full digests.
- Each hash allocates a new `Mac` because `Mac` must not be assumed thread-safe for sharing across listener threads.

### 8.1. Directory Structure

~~~text
sensitive-id-event-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── SensitiveIdentifierEventDemo.java
    └── test/
        └── java/
            └── demo/
                └── SensitiveIdentifierEventDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'sensitive-id-event-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.SensitiveIdentifierEventDemo'
}

test {
    useJUnitPlatform()
}
~~~

No external crypto library is needed because Java 17 provides `HmacSHA256` out of the box. When using Spring Boot, let Boot dependency management keep Spring versions aligned across the system.

### 8.2. Complete Java File

Create **`src/main/java/demo/SensitiveIdentifierEventDemo.java`**:

~~~java
package demo;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SensitiveIdentifierEventDemo {

    // Event contains no email, customer entity, or authentication token.
    public record CustomerPreferenceChanged(
            String subjectRef,
            String changeKind,
            Instant occurredAt) {}

    public static final class Pseudonymizer {
        private static final byte[] PURPOSE =
                "spring-event/customer-preference/v1"
                        .getBytes(StandardCharsets.UTF_8);

        private final SecretKey key;

        public Pseudonymizer(SecretKey key) {
            this.key = Objects.requireNonNull(key);
        }

        public String subjectRef(String tenant, String rawCustomerId) {
            if (tenant == null || tenant.isBlank()
                    || rawCustomerId == null || rawCustomerId.isBlank()) {
                // Do not echo sensitive input in exceptions.
                throw new IllegalArgumentException(
                        "Identifiers must be nonblank");
            }

            byte[] tenantBytes = tenant.getBytes(StandardCharsets.UTF_8);
            byte[] idBytes =
                    rawCustomerId.getBytes(StandardCharsets.UTF_8);

            // Length-prefix to avoid ambiguity when concatenating strings.
            ByteBuffer input = ByteBuffer.allocate(
                    3 * Integer.BYTES
                    + PURPOSE.length + tenantBytes.length + idBytes.length);

            input.putInt(PURPOSE.length).put(PURPOSE);
            input.putInt(tenantBytes.length).put(tenantBytes);
            input.putInt(idBytes.length).put(idBytes);

            try {
                // Do not share mutable Mac instances across threads.
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(key);
                byte[] digest = mac.doFinal(input.array());

                return "h1_" + Base64.getUrlEncoder()
                        .withoutPadding().encodeToString(digest);
            } catch (GeneralSecurityException ex) {
                throw new IllegalStateException(
                        "Unable to create reference", ex);
            }
        }
    }

    public static final class ChangePublisher {
        private final ApplicationEventPublisher events;
        private final Pseudonymizer pseudonymizer;

        public ChangePublisher(
                ApplicationEventPublisher events,
                Pseudonymizer pseudonymizer) {
            this.events = events;
            this.pseudonymizer = pseudonymizer;
        }

        public void preferenceChanged(String tenant, String rawCustomerId) {
            String ref = pseudonymizer.subjectRef(
                    tenant, rawCustomerId);

            events.publishEvent(new CustomerPreferenceChanged(
                    ref,
                    "PREFERENCE_UPDATED",
                    Instant.now()));
        }
    }

    // Demo prints only non-sensitive information; do not log record.toString().
    public static final class AuditListener {
        private final AtomicInteger count = new AtomicInteger();
        private final AtomicReference<CustomerPreferenceChanged> last =
                new AtomicReference<>();

        @EventListener
        public void handle(CustomerPreferenceChanged event) {
            last.set(event);
            count.incrementAndGet();

            System.out.println("listener.event=customer_preference_changed");
            System.out.println("listener.identity=hidden");
        }

        public int count() {
            return count.get();
        }

        public CustomerPreferenceChanged last() {
            return last.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public SecretKey demoHmacKey()
                throws GeneralSecurityException {
            // Demo only: a new key is generated each time a Spring context is created.
            KeyGenerator generator =
                    KeyGenerator.getInstance("HmacSHA256");
            generator.init(256);
            return generator.generateKey();
        }

        @Bean
        public Pseudonymizer pseudonymizer(SecretKey demoHmacKey) {
            return new Pseudonymizer(demoHmacKey);
        }

        @Bean
        public ChangePublisher changePublisher(
                ApplicationEventPublisher events,
                Pseudonymizer pseudonymizer) {
            return new ChangePublisher(events, pseudonymizer);
        }

        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Pseudonymizer pseudonymizer =
                    context.getBean(Pseudonymizer.class);
            ChangePublisher publisher =
                    context.getBean(ChangePublisher.class);
            AuditListener listener =
                    context.getBean(AuditListener.class);

            // Simulated data, not a real email.
            String rawId = "user-42@example.test";
            String tenant = "tenant-demo";

            String first = pseudonymizer.subjectRef(tenant, rawId);
            String repeat = pseudonymizer.subjectRef(tenant, rawId);
            String otherTenant =
                    pseudonymizer.subjectRef("tenant-other", rawId);

            publisher.preferenceChanged(tenant, rawId);

            System.out.println(
                    "sameInputSameReference=" + first.equals(repeat));
            System.out.println(
                    "differentTenantDifferentReference="
                    + !first.equals(otherTenant));
            System.out.println(
                    "eventContainsRawId="
                    + listener.last().toString().contains(rawId));
            System.out.println(
                    "listenerCount=" + listener.count());
        }
    }
}
~~~

### 8.3. Running the Demo

In the project directory, using JDK 17+ and Gradle:

~~~bash
gradle -q run
~~~

If Gradle Wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

Lines **printed by the demo code** in order under normal conditions:

~~~text
listener.event=customer_preference_changed
listener.identity=hidden
sameInputSameReference=true
differentTenantDifferentReference=true
eventContainsRawId=false
listenerCount=1
~~~

Digest values are not printed because they remain linkable identifiers. The difference between tenant A and B tokens relies on HMAC properties; collision probability for HMAC-SHA256 in this use case is extremely small, though that is not a claim that the algorithm is mathematically collision-impossible.

Log line ordering comes from the default `SimpleApplicationEventMulticaster` invoking listeners synchronously: the two listener lines appear before the lines printed by `main` after `publishEvent`. If switched to async, wait for callback completion before reading `listener.last()`.

### 8.4. Why Does the Example Not Expose the Raw ID in the Event?

- Record `CustomerPreferenceChanged` contains only `subjectRef`, `changeKind`, and `occurredAt`.
- `ChangePublisher` receives the raw identifier via method argument to compute the token, yet **never** puts it into the event object.
- `Pseudonymizer` encodes purpose, tenant, and raw ID in UTF-8 with length prefixes and computes HMAC-SHA256.
- `AuditListener` prints only two fixed strings containing neither IDs nor tokens.
- `Mac` is created fresh per calculation; no mutable internal state is shared across threads.
- `SecretKey` is generated randomly and **never printed**; the demo key itself is not persisted across startups.

**Important limitation:** `eventContainsRawId=false` only proves the demo record does not contain that raw ID string. It does not prove the entire runtime, all dependency logs, or memory dumps lack raw data. In reality, the raw ID still exists temporarily in service arguments and JVM strings; production security requires designing the full data lifecycle, access controls, and sinks.

## 9. JUnit 5: Checking Determinism, Scope, Spring Wiring, and Invalid Inputs

Create **`src/test/java/demo/SensitiveIdentifierEventDemoTest.java`**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SensitiveIdentifierEventDemoTest {

    @Test
    void sameInputAndKeyProduceSameScopedReference() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SensitiveIdentifierEventDemo.Config.class)) {

            var pseudonymizer = context.getBean(
                    SensitiveIdentifierEventDemo.Pseudonymizer.class);

            String id = "user-42@example.test";
            String a = pseudonymizer.subjectRef("tenant-A", id);
            String again = pseudonymizer.subjectRef("tenant-A", id);
            String b = pseudonymizer.subjectRef("tenant-B", id);

            assertEquals(a, again);
            assertNotEquals(a, b);
            assertTrue(a.matches("h1_[A-Za-z0-9_-]{43}"));
            assertFalse(a.contains(id));
        }
    }

    @Test
    void springEventCarriesPseudonymInsteadOfRawId() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SensitiveIdentifierEventDemo.Config.class)) {

            var publisher = context.getBean(
                    SensitiveIdentifierEventDemo.ChangePublisher.class);
            var listener = context.getBean(
                    SensitiveIdentifierEventDemo.AuditListener.class);

            String raw = "another-user@example.test";
            publisher.preferenceChanged("tenant-A", raw);

            assertEquals(1, listener.count());
            var event = listener.last();
            assertEquals("PREFERENCE_UPDATED", event.changeKind());
            assertTrue(event.subjectRef().startsWith("h1_"));
            assertFalse(event.toString().contains(raw));
        }
    }

    @Test
    void emptyIdentifierIsRejectedWithoutEchoingInput() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SensitiveIdentifierEventDemo.Config.class)) {

            var pseudonymizer = context.getBean(
                    SensitiveIdentifierEventDemo.Pseudonymizer.class);

            var failure = assertThrows(
                    IllegalArgumentException.class,
                    () -> pseudonymizer.subjectRef("tenant-A", " "));

            assertEquals("Identifiers must be nonblank",
                    failure.getMessage());
        }
    }
}
~~~

Run:

~~~bash
gradle test
~~~

The tests verify three contracts:

1. **Deterministic within the same key/scope** and isolated tokens when switching tenants.
2. **Events flow through real Spring publisher/listener wiring**; no raw ID appears in the example record's payload.
3. **Fail closed on invalid input** and exceptions do not echo user data.

These test logic and wiring; they do **not** replace penetration testing, log audits, or verifying production key management. This lesson does not claim Gradle was executed here; results should be verified in an actual build environment.

## 10. Managing HMAC Keys in Production

The demo code uses `KeyGenerator` to create an in-memory 256-bit HMAC key so it runs standalone. If multiple instances A and B generate different keys, **the same customer ID will produce different references**, breaking correlation, deduplication, or lookups.

A production design requires:

### 10.1. Key Source

- Generate keys with sufficient entropy using a CSPRNG or key management system.
- Store and distribute via an appropriate **secret manager, KMS, HSM, or keystore**.
- Never hard-code keys in source code, test fixtures used in production, Docker images, committed `application.yml`, query parameters, or logs.
- Restrict service IAM permissions to only the required key; separate privileges for producers, consumers, operators, and observability.
- Never log full keys or Base64-encoded keys when debugging errors.

If receiving keys from injected environment variables, protect runtime configs, crash dumps, and diagnostic endpoints too. Production environments may choose KMS MAC operations so keys never leave the KMS, trading off network latency, quotas, and availability.

### 10.2. Key IDs and Versioning

A possible format:

~~~text
pseudonym token:
  hmac-v2.<keyId>.<base64url(digest)>

metadata:
  purpose = customer-preference
  tenant = isolated scope (not necessarily emitting raw tenant)
  algorithm = HmacSHA256
  keyId = key identifier, not a secret
~~~

This format is a **design example**, distinct from the simple `h1_` prefix in the demo. Do not mix key ID, algorithm version, and canonicalization version uncontrollably; when input encoding changes, consumers must know the version to interpret it.

### 10.3. Rotation

When changing keys, the same ID produces a new token:

~~~text
reference(K_old, tenant, customer) != reference(K_new, tenant, customer)
~~~

If the system stores old events or uses tokens to correlate across multiple days, plan for:

1. Attaching `keyId`/version to new tokens.
2. Retaining old keys within permitted scope and duration long enough to read/migrate valid data.
3. Using dual-read or mapping migration if old and new data must correlate.
4. Avoiding emitting two different IDs for the same business action without handling dedup/versioning.
5. Revoking old keys per retention and deletion policies once no longer needed.
6. Auditing where keys are used and the impact if a key is compromised.

Key rotation **does not** automatically erase tokens already written to logs/outboxes. Data lifecycle and retention must still be handled separately.

## 11. An HMAC Token Can Still Be Sensitive

A common misconception: "it's hashed, so log it freely." An HMAC token may hide the original email, yet still allows:

- Linking multiple actions by the same subject within the same scope/key.
- Joining against another system holding the mapping or knowing the input/key.
- Inferring activity from timing, frequency, event types, or accompanying attributes.
- Recovering the mapping if the key or token-generating service is compromised or allows unrestricted oracle queries.

Therefore:

- Only log tokens when there is a **clear correlation need**; prefer not logging them or logging only event type/status.
- Apply purpose/tenant isolation and bounded retention.
- Never use the token as proof-of-identity or an authorization credential.
- When authorizing, derive identity from the authenticated principal/trust boundary and check resource-level permissions; never trust a client-supplied `subjectRef`.
- Protect token-generation endpoints from abuse: authentication, rate limiting, auditing—never turn them into public dictionary oracles.
- Treat pseudonyms as **data that still requires protection** under applicable risk models/regulations, never assuming they are anonymous by default.

If the true requirement is **unlinkability across events**, deterministic HMAC is unsuitable. Use a fresh random event ID per occurrence and omit subject references; for analytics, consider aggregation/k-anonymity or more fitting privacy techniques depending on the use case.

## 12. Safe Logging Design for Listeners

### 12.1. Avoid Stringifying Events

Avoid:

~~~java
@EventListener
public void on(CustomerPreferenceChanged event) {
    logger.info("Customer changed: {}", event);
}
~~~

This is illustrative code. Java records generate a `toString()` containing component names and values. If the event holds an email or HMAC reference, logs capture that value. If a new field is added later, logs automatically inherit it without review noticing.

Better:

~~~java
@EventListener
public void on(CustomerPreferenceChanged event) {
    logger.info("customer preference event processed; kind={}",
            event.changeKind());
}
~~~

Log only approved fields. If correlation is needed, pick an independent `eventId` and control linkability. Parameterized log templates do not automatically mask PII; **values passed in still need review**.

### 12.2. Exception Messages Can Leak Raw IDs

Avoid:

~~~java
throw new IllegalArgumentException(
        "Invalid customer " + rawCustomerId);
~~~

If the exception is logged, the raw ID travels inside the message. Use a finite error message/code:

~~~java
throw new IllegalArgumentException(
        "Invalid customer identifier");
~~~

For support investigations, use a correlation ID or error code and a controlled, restricted audit channel instead of echoing input data into public exceptions/routine logs.

### 12.3. Log Injection and User-Supplied Text

Even after masking identifiers, other text fields may contain newlines, control characters, or delimiters causing log forging. Use structured logging and encoders that escape properly, validate field lengths, and never concatenate raw user input into log templates. The OWASP Logging Cheat Sheet recommends excluding, masking, or restricting personal data, secrets, and session values in logs.

Log aggregation, file rotation, archives, and backups all need proper retention, RBAC, and transport protection; redaction in a log-viewer UI **does not** delete raw data already stored in the backend.

## 13. Metrics and Tracing: Avoiding High Cardinality and Context Leaks

A common mistake:

~~~java
registry.counter(
        "customer.event",
        "customer_ref", event.subjectRef()).increment();
~~~

Even with HMAC, each subject creates a distinct label value. With hundreds of thousands of users, time-series cardinality explodes and you have pushed a linkable identifier into the metrics system.

Metric tags should be **low-cardinality**:

~~~java
registry.counter(
        "customer.event",
        "type", "preference_changed",
        "outcome", "success").increment();
~~~

This illustrative snippet requires Micrometer `MeterRegistry` and a `registry` bean. `event type`, `outcome`, `handler`, and `error kind` from a finite set are far better suited than `customerId`, `email`, `eventId`, `traceId`, or digests.

### 13.1. Traces and Logs Have Their Own Policies

Trace span attributes/baggage may be exported to third parties; never put raw IDs or full HMAC tokens into attributes automatically. If per-user correlation is required, it must have a valid purpose, access controls, sampling, and retention. For async listeners, MDC/ThreadLocal context does not automatically propagate to executors; context propagation does not replace data sanitization policies.

Separate them cleanly:

- Metrics: aggregated counts, durations, outcomes.
- Logs: operational events with bounded fields.
- Traces: linking execution paths with permitted correlation IDs.
- Restricted audit store: sensitive data genuinely needed for auditing, with dedicated permissions and retention.

### 13.2. Do Not Put Secrets in Error Reporting

Sentry, APM agents, OpenTelemetry exporters, or crash reporters may automatically capture request parameters, exception messages, or object fields. Audit SDK configurations, filters, before-send hooks, and sample telemetry payloads, not just `logger.info` calls in source code.

## 14. Transactions, Async, Outbox, and Dead-Letter Queues

### 14.1. Transaction-Bound Events

With `@TransactionalEventListener(AFTER_COMMIT)`, execution may be deferred until after commit, yet the payload remains an object in the JVM. If the event carries a raw ID, it stays alive until the callback runs. HMAC does not change transaction timing and does not make side effects safe if the callback executes outside a transaction.

### 14.2. Async Queues

With an executor, tasks can hold events/payloads on the heap longer. If payloads hold sensitive data, reference counts and lifetime increase; if queues are dumped or crash reports capture objects, exposure risk grows. Keep only genuinely needed fields in events.

### 14.3. Outbox / Message Brokers

If an event is serialized to outbox JSON, Kafka, RabbitMQ, or HTTP, who can access the data differs from an in-process Spring event. A "trusted" internal event is not automatically a public integration contract.

Ensure:

- Internal events and integration DTOs are separated when trust boundaries differ.
- Sanitize and validate **before persisting/publishing** to broader channels.
- Schema versioning and data classification per field.
- Appropriate encryption at rest/in transit, ACLs, and retention.
- DLQs/retries do not retain data indefinitely or replicate sensitive data across many stores.
- Serialize opaque references only when consumers have an authorized retrieval/handling mechanism.

If zero event loss across crashes is required, transactional outbox or brokers are the delivery architecture; HMAC only addresses part of **confidentiality/correlation**, not delivery guarantees.

## 15. API Design and Authorization Models

A service may need the real customer ID to update the database, while an audit listener does not need to know it. A two-layer architecture can be used:

~~~text
Authenticated request
     |
     v
Authorized domain service
  |  (keep raw ID inside trusted zone)
  |
  +--> database update
  |
  +--> event adapter / safe DTO
         |
         +--> pseudonymize raw ID with approved scope/key
         |
         +--> publish CustomerPreferenceChanged(subjectRef, kind)
                  |
                  +--> metrics/audit listeners: no raw ID
~~~

If a notification listener needs an email to send mail, do not force it to "reverse a hash." Separate a durable delivery job in protected storage holding an **opaque reference** to the customer record, and let an authorized worker resolve that reference under business rules.

Authorization must happen **before domain actions** and **at every subsequent data retrieval**. An HMAC token is not a session token, access token, or authorization capability. If a token arrives from a client, verify tenant, access permissions, and underlying data state through a trusted system.

### 15.1. Do Not Rely on UI Masking as a Security Control

If the UI displays `u***@example.test` while backend events/logs still store the real email, the risk remains. Likewise, if the API response strips the email yet the message broker still carries `rawEmail`, the security policy is unmet. Classify and protect **every point where data crosses a trust boundary**.

### 15.2. Data Requiring Deletion or Expiration

A pseudonym does not allow deleting data by raw ID without a mapping or the ability to recompute the token using old keys. When deletion rights apply, the system must know which tokens and records relate to the subject; design retention, key lifecycles, and indexes upfront. Do not delete keys prematurely while backlog records still require processing, nor keep keys forever out of convenience.

## 16. Performance and Trade-Offs of HMAC

HMAC-SHA256 on short inputs usually has low computational cost, yet trade-offs remain:

- Creating a new `Mac` per call avoids sharing non-thread-safe state. Benchmark throughput if event rates are very high.
- HMAC with keys in a remote KMS incurs network latency, quotas, timeouts, and failure modes. Consider local KMS-protected key caching per policy if permitted.
- Data needs consistent normalization/encoding; transforming large or unusual strings can consume CPU/memory. Validate input size limits.
- Never feed an entire object graph into the hash input; pick only the canonical identifier, purpose, and tenant.
- Tokens are longer than numeric IDs, incurring index/storage overhead if persisted; size indexes/columns appropriately and evaluate collision risk before truncating.

In the demo, the HMAC-SHA256 digest is 32 bytes; unpadded Base64URL encodes it as **43 ASCII characters**, plus the `h1_` prefix for **46 characters total**. That is merely representation length, not proof that the data is safe for every purpose.

**Never truncate tokens to 6 or 8 characters** just to make logs pretty. Truncation increases collision risk, especially across millions of subjects. If you only need a log marker to investigate a specific request, use a randomly generated correlation ID rather than a poorly truncated subject digest.

## 17. Data-Safety Testing Beyond Unit Tests

The JUnit suite in section 9 confirms the demo event omits the raw ID. Production requires tests covering real exit paths:

| Test | What to Verify |
| --- | --- |
| Event schema | No raw email, phone, password, token, `CustomerEntity`, or request object fields |
| Stable pseudonym | Same key/scope/input yields the same token |
| Scope isolation | Different purpose/tenant produces different tokens by design |
| Key rotation | Valid records can still be read/migrated without losing required correlation |
| Log capture | Contains no raw ID/secret; never prints unauthorized full events/`toString()` |
| Exception paths | Error messages and stack traces undergo proper redaction |
| Metric labels | No user ID, raw ID, event ID, or high-cardinality digest |
| Tracing export | Spans/baggage emit no unauthorized data |
| Async events | Queues and error handlers do not inadvertently log payloads |
| Outbox/DLQ | Serialized JSON has no forbidden fields; proper retention and permissions |
| Key exposure | Not present in logs, metrics, source, public config, or build artifacts |
| Authorization | Possessing a token does not grant cross-tenant or unauthorized data access |
| Deletion/retention | Data and pseudonyms expire per actual policy |

### 17.1. Log Capture Tests Beat Grepping Source Code

Searching source for `logger.info(event)` is not enough. Libraries or exception handlers can format objects themselves. With Logback/SLF4J, attach a test appender to capture listener logs and assert they contain neither synthetic emails nor keys. For tracing, use an in-memory exporter/test harness; for outboxes, query the persisted JSON.

### 17.2. Testing Dictionary Attacks at Design Level

Never claim "SHA-256 tested safe" simply because the digest looks unreadable. State the threat model: an attacker without the key who can enumerate candidate identifiers. HMAC defends far better here provided the key stays uncompromised and the token-generation service is not an exploitable oracle.

### 17.3. Testing Mismatched Keys Across Instances

If two instances use different keys, the same email yields two different tokens. For systems requiring stable cross-instance correlation, integration tests must prove instances share the configured key version at the right time. The demo **intentionally** does not satisfy this because it generates a random key per context.

## 18. Common Mistakes and Misconceptions

| Misconception / Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| "Internal events have no PII risk" | Listeners/logs/traces/async/outboxes widen exposure | Send minimal data; classify every sink |
| Hashing emails with SHA-256 is anonymization | Dictionary attacks work on predictable emails | Prefer omitting; if stable token needed, use keyed HMAC |
| Masking `a***@domain` is always safe | Can re-identify using remaining exposed characters | Mask only when the use case truly requires it |
| HMAC tokens are public data | They still link multiple events and can be mapped | Treat as pseudonymous; apply retention/ACLs |
| Hashed values can serve as access tokens | Hashes do not prove ownership/authorization | Check principal/tenant/resource permissions |
| Putting email in the event and masking only in logs | Other listeners still read the raw email | Sanitize at payload/trust boundary |
| Records hide sensitive content automatically | Record `toString` prints component values | Never log arbitrary objects; use allowlisted DTOs |
| Identifiers inside `ApplicationEvent.source` are harmless | `source` can be a rich entity | Never pass sensitive entities as `source` |
| HMAC does not need a secret manager | Key exposure lets attackers compute candidates | KMS/keystore, least privilege, rotation |
| Generating a random key on restart keeps tokens stable | Tokens change across restarts | Production uses stable, versioned keys |
| Reusing the same key/input across all modules | Enables cross-domain linkage | Separate scopes by purpose and tenant |
| Plain string concatenation `tenant+id` | Encoding ambiguity and logic collisions | Length prefixes / canonical encoding |
| HMAC can be unhashed back to the real ID | HMAC is not two-way encryption | Use restricted mapping/references if lookup is needed |
| Public salts replace HMAC keys | Attackers still test candidates with the known salt | Use secret-keyed HMAC when appropriate |
| Truncating digests to a few chars works at any scale | Collision risk rises with token count | Evaluate mathematically; keep sufficient digest length |
| Putting subject hashes in Micrometer tags is safe | High cardinality and linkability | Bounded tags; controlled correlation |
| Using `@Async` eliminates data risk | Queues hold payloads longer and error paths may log | Minimize fields; protect async pipelines |
| Tokens need no deletion since they are hashed | Retention and protection duties may still apply | Enforce lifecycle and deletion policies |
| Passing tests means production is safe | Tests may omit log exporters, KMS, or brokers | Conduct integration/security reviews across all exit paths |
| Using HMAC event tokens to hash passwords | Password storage is a different problem | Use a proper password KDF; never emit passwords |
| Same raw ID must always yield the same token everywhere | Increases cross-module linkability | Namespace by purpose and tenant |

## 19. Code Review Checklist and Self-Check Questions

**Checklist:**

- [ ] Identified which fields are direct/indirect identifiers.
- [ ] When listeners do not need identity, payloads omit identity.
- [ ] No raw emails/phones/tokens/passwords/sessions or sensitive entities are placed in events.
- [ ] Where stable references are required, HMAC uses high-entropy keys, explicit scopes, and versioning.
- [ ] Plain SHA-256 on predictable identifiers is never labeled anonymous.
- [ ] Canonicalization matches the authoritative identity system.
- [ ] Event `source` does not inadvertently hold raw entities/requests.
- [ ] Listeners never log raw `event.toString()` or exceptions containing raw inputs.
- [ ] Metrics/traces/logs/queues/outboxes/DLQs have been audited across trust boundaries.
- [ ] Pseudonymization is never used as authorization.
- [ ] Key ownership, IAM, rotation, key IDs, and retention policies exist.
- [ ] Consumers needing original IDs have a clear plan (mappings/restricted stores).
- [ ] Tests verify actual sinks, not merely `toString()` assertions.
- [ ] Reviews catch sensitive fields being added to event schemas.
- [ ] Deletion/retention/correlation handling during key rotation is defined.

**Question 1.** When a listener only counts how many times customers change preferences, should the email be included in the event?

**Answer:** No. Event type/counters suffice; do not even pseudonymize if no identifier is needed.

**Question 2.** Why does `SHA-256(email)` fail to protect well against an attacker holding a candidate email list?

**Answer:** The attacker computes the exact same hash for each candidate and compares; SHA-256 has no secret key.

**Question 3.** Does HMAC-SHA256 make data completely anonymous?

**Answer:** No. Tokens remain linkable and recomputable by anyone with the key/candidate source; protect them as pseudonymous data.

**Question 4.** A consumer wants to fetch a customer entity from the database, yet the event only carries an HMAC reference; can it simply call `findById(hash)`?

**Answer:** Only if the data layer was explicitly designed with a matching index/lookup. HMAC cannot be reversed; usually an opaque ID + mapping or a restricted workflow is needed.

**Question 5.** Why include tenant and purpose in the HMAC input?

**Answer:** To prevent the same identifier from producing identical tokens across tenants/modules, limiting cross-linkage.

**Question 6.** Is generating a random HMAC key on each application startup fine for a demo? Is it fine for production correlation?

**Answer:** Fine for a standalone demo; production needs stable, versioned, rotated keys so desired correlations are not lost.

**Question 7.** Should a full HMAC token be recorded as a `customer_ref` tag in Micrometer?

**Answer:** No. It takes too many distinct values, creating high cardinality and trackability; use bounded event-type/outcome tags.

**Question 8.** Once emails are masked in logs while the event still carries the raw email, is all risk resolved?

**Answer:** No. Listeners, memory, tracing, outboxes/brokers, and error paths can still expose it; sanitize the payload right at the boundary.

## 20. References

- Spring Framework 6.2 — Standard and Custom Events, POJO payloads, and `@EventListener`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `PayloadApplicationEvent` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Java SE 17 — `javax.crypto.Mac`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
- Java SE 17 — `javax.crypto.KeyGenerator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html
- Java SE 17 — `java.util.Base64`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html
- Java SE 17 — `java.nio.ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- OWASP — Logging Cheat Sheet, data to exclude/mask/hash and preventing log injection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Cryptographic Storage Cheat Sheet, key management principles: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet (password hashing is a distinct problem from HMAC event identity): https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
