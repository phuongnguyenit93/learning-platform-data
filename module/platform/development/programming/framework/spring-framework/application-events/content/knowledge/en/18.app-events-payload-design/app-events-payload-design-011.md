# Sensitive Data in Events: Designing Safe Payloads with Spring Framework

## 1. Why Are Event Payloads a Data-Leak Surface?

In Spring Framework, `ApplicationEventPublisher.publishEvent(event)` forwards an event object to the listener dispatch mechanism (`ApplicationEventMulticaster`). One event can be received by many `@EventListener` or `ApplicationListener` beans; listeners may log, emit metrics, spawn background tasks, persist to an outbox, or forward to a message broker.

Therefore, **an event payload must be designed as data shared across all receiving components**, not merely as an internal argument to the calling method. Putting passwords, tokens, emails, ID numbers, or financial details into events creates extra copies and unnecessary access paths.

Example of **what not to do**:

```java
// Snippet illustrating an unsafe design.
record CustomerUpdated(
        String customerId,
        String email,
        String password,
        String accessToken,
        String fullAddress) {}
```

A listener only needs to know "contact information changed", yet receives passwords and access tokens as well. If someone accidentally calls `log.info("event={}", event)`, Java record's default `toString()` can also dump the entire contents into logs. Once the event is serialized to JSON, sensitive data spreads further into brokers, dead-letter queues, APM tools, and replica stores.

**Core principle:** an event should carry only the **minimal information consumers genuinely need**, matching each consumer's purpose and access permissions. Without a concrete need, never include sensitive data in events.

## 2. Classifying Data Before Building Events

Not all data is equally sensitive. Classify by **harm if leaked**, intended purpose, linkability to identify a person, and system protection policies.

| Category | Examples | Default Handling in Event Design |
| --- | --- | --- |
| Authentication secrets | Passwords, OTPs, refresh/access tokens, API keys, private keys | **Exclude from payloads**; do not log; do not replay via events |
| Personal identifying data | Email, phone number, address, government ID, date of birth | Avoid attaching; use a minimal reference if authorized consumers can look it up |
| Financial/health data | Account numbers, card details, lab results, treatment details | Include only with strict business justification and controls; do not broadcast widely by default |
| User-supplied data | Message text, notes, filenames, free-form text | Treat as untrusted; may contain PII, secrets, or log-injection payloads |
| Linkable identifiers | Customer ID, order ID, tenant ID, IP, device ID | Do not assume "harmless"; bound scope, lookup permissions, and retention |
| Business metadata | Change type, status, aggregate version, event ID | Keep minimal; even the event name itself can sometimes reveal sensitive facts |

For example, the name `SensitiveDiagnosisConfirmed` already reveals health information purely from the **event type**, even if the payload carries only an ID. In sensitive domains, review event names, routing keys, topic names, metric tags, and log messages alike.

A random UUID instead of an email reduces direct exposure, yet **pseudonymization is not anonymization**. If someone with access can use that ID to look up an identity, the ID can still constitute personal data requiring protection.

## 3. Consumer-Driven Design: Who Actually Needs Each Field?

Before declaring an event record, evaluate every field against a needs table:

| Candidate Field | Which Consumer Needs It? | Can It Be Replaced? | Decision |
| --- | --- | --- | --- |
| `eventId` | Audit, retries, deduplication | Usually no | Safe to keep; contains no direct sensitive info |
| `customerRef` | Authorized handler needing customer lookup | Opaque ID | Keep only if consumers truly need it; enforce access control |
| `changedFields` | Audit or state sync | Enum instead of old/new values | Keep at an appropriate level of granularity |
| `newEmail` | Perhaps only one confirmation-email service needs it | Controlled lookup by ID / dedicated flow | Exclude from broadly broadcast events by default |
| `oldEmail` | Rarely needed by ordinary listeners | Do not pass, or use a dedicated audit flow | Exclude from general events |
| `password` / `accessToken` | Should never be broadcast event data | Separate auth/secret mechanism | Remove completely |
| `occurredAt` | Business timeline, audit | Timestamp | Keep while considering linkability |
| `schemaVersion` | Out-of-process consumers | Version number | Safe to keep |

The resulting example is a minimal event:

```java
record ProfileChanged(
        String eventId,
        String customerRef,
        Set<ChangedField> changedFields) {}
```

Here `ChangedField.EMAIL` means **the email changed**, without carrying the old or new email value. If a specific consumer is authorized to use the new value, it must fetch it via an access-controlled service or a dedicated risk-assessed channel.

Watch out for **fan-out bloat**: an event consumed by 20 listeners should not carry extra sensitive data just because one listener wants it. Split off a narrowly scoped dedicated event, or emit a generic reference event and provide an authorized lookup operation for permitted consumers.

## 4. Trust Boundaries in the Event Dispatch Flow

```text
Domain / Application service
    |
    | Mutate source data in protected store
    v
Create minimal event
    |  eventId, customerRef, changedFields
    |  NO email/password/token
    v
ApplicationEventPublisher
    |
    +-- Audit listener: log only event type + safe field names
    |
    +-- Cache listener: handle only identifiers within allowed scope
    |
    +-- Async worker: may run on another thread; does not by default
    |                 inherit publisher's permissions or context
    |
    +-- If there is a bridge/outbox/broker:
           serialize -> topic/queue -> DLQ -> replay -> backups
           every copy may retain payloads longer than expected
```

Within the same Spring application context, `@EventListener` has no built-in "field-level authorization" per payload. Any listener matching the **event type** receives the entire object. Never use "modules are in the same app" as an excuse to put secrets into event objects.

Specifically, `ApplicationEventPublisher.publishEvent(Object)` can wrap POJOs/records in `PayloadApplicationEvent` during dispatch. By default, standard events run synchronously; yet `publishEvent` is fundamentally a **handoff** to the multicaster—it does not guarantee every listener finishes, and execution can be asynchronous depending on configuration.

Thread switches also affect `SecurityContextHolder`, MDC, transactions, and `ThreadLocal` values. Never assume "the publisher was authorized" implies another worker or listener holds the same permissions.

## 5. Standalone Java 17 + Spring Framework 6.2 Example

Goal: illustrate a service persisting a new email while publishing an event **containing no email**, so listeners see only what kind of field changed. The example uses no real database or real authorization; it demonstrates payload structure and in-process handling rather than a complete security system.

### Structure

```text
safe-domain-events/
├── pom.xml
└── src/main/java/demo/SensitiveEventDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>safe-domain-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SensitiveEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/SensitiveEventDemo.java`:

```java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SensitiveEventDemo {

    public enum ChangedField {
        EMAIL
    }

    // Event contains ONLY minimal fields; no email or secrets.
    public record ProfileChanged(
            String eventId,
            String customerRef,
            Set<ChangedField> changedFields) {

        public ProfileChanged {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(customerRef);
            changedFields = Set.copyOf(
                    Objects.requireNonNull(changedFields));
        }

        // Guardrail in case someone accidentally logs the whole object.
        // This is NOT a protection mechanism for JSON serialization.
        @Override
        public String toString() {
            return "ProfileChanged{changedFields=" + changedFields + "}";
        }
    }

    // Sensitive data belongs in the source data store, not in the event.
    public record Customer(String reference, String email) {
        @Override
        public String toString() {
            return "Customer{REDACTED}";
        }
    }

    public static class CustomerRepository {
        private final Map<String, Customer> rows = new HashMap<>();

        public CustomerRepository() {
            rows.put("customer-42",
                    new Customer("customer-42", "before@example.invalid"));
        }

        public Customer get(String reference) {
            Customer customer = rows.get(reference);
            if (customer == null) {
                throw new IllegalArgumentException("Unknown customer");
            }
            return customer;
        }

        public void save(Customer customer) {
            rows.put(customer.reference(), customer);
            System.out.println("repository: saved customer");
        }
    }

    public static class CustomerService {
        private final CustomerRepository repository;
        private final ApplicationEventPublisher publisher;

        public CustomerService(CustomerRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void changeEmail(String customerRef, String newEmail) {
            Objects.requireNonNull(newEmail);
            // This is only a minimal input check for the demo,
            // not a production-grade email validator.
            if (!newEmail.contains("@")) {
                throw new IllegalArgumentException("Invalid email");
            }

            Customer old = repository.get(customerRef);
            repository.save(new Customer(old.reference(), newEmail));

            ProfileChanged event = new ProfileChanged(
                    UUID.randomUUID().toString(),
                    old.reference(),
                    Set.of(ChangedField.EMAIL));

            publisher.publishEvent(event);
            System.out.println("publisher: handoff complete");
        }
    }

    public static class AuditListener {
        @EventListener
        public void onProfileChanged(ProfileChanged event) {
            // Do not log Customer/email, linkable IDs, or the event object.
            System.out.println("listener: PROFILE_CHANGED fields="
                    + event.changedFields());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        CustomerRepository customerRepository() {
            return new CustomerRepository();
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }

        @Bean
        CustomerService customerService(
                CustomerRepository repository,
                ApplicationEventPublisher publisher) {
            return new CustomerService(repository, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            CustomerService service =
                    context.getBean(CustomerService.class);
            CustomerRepository repository =
                    context.getBean(CustomerRepository.class);

            System.out.println("before: email stored in repository");
            service.changeEmail(
                    "customer-42", "replacement@example.invalid");
            System.out.println("after: email updated="
                    + "replacement@example.invalid".equals(
                            repository.get("customer-42").email()));
        }
    }
}
```

Run in the `safe-domain-events` directory, requiring JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Output printed by the program itself (excluding auxiliary Maven messages):

```text
before: email stored in repository
repository: saved customer
listener: PROFILE_CHANGED fields=[EMAIL]
publisher: handoff complete
after: email updated=true
```

### Explanation and Limitations of the Example

1. `CustomerRepository` keeps the email in its own data structure (here a simulated `Map`). It does not print the email to stdout.
2. `CustomerService` updates the email first, then builds `ProfileChanged` with a random `eventId`, `customerRef`, and the `EMAIL` enum set. **No `oldEmail`/`newEmail`/`token`/`password` fields exist.**
3. Spring 6.2 dispatches the record via `publishEvent(Object)` to the matching `@EventListener` method. With the default synchronous multicaster, the `listener` line appears before `publisher: handoff complete`.
4. `toString()` is overridden to avoid leaking details if someone prints the record. Still, never log entire events and never rely on `toString()` to protect serialization: a JSON serializer can directly read `eventId` or `customerRef`.
5. `Set.copyOf(...)` creates an immutable set so consumers cannot mutate the payload via a mutable reference after event creation.
6. The string `replacement@example.invalid` is test data under the `.invalid` domain, not a real contact address. In real runs, process data under the application's data-protection regulations.
7. The repository in the example has **no transactions, encryption, or authorization**. This is an event payload design demo, not proof of comprehensive email data protection at rest.

**Important:** `customerRef` can still be indirect personal data if linked to customer profiles. A listener wishing to look up the profile must be authorized by user/service, tenant, and purpose; having an ID in an event does not automatically grant access rights.

## 6. Why Avoid Using Whole Entities as Payloads?

A common anti-pattern:

```java
// Snippet that should NOT be used for broadly broadcast events.
publisher.publishEvent(customerEntity);
```

`customerEntity` may contain emails, addresses, JPA relationships, payment details, lazy-loaded associations, or unclassified internal fields. When sending the whole object:

- Listeners receive excessive data and may accidentally use fields outside their scope.
- Auto-generated `toString()` (records, Lombok `@Data`, or manual code) can print sensitive fields.
- Mapping/serialization tools may traverse getters and unexpectedly expand the object graph.
- Mutable entities can change state after publication, causing async listeners to observe inconsistent values.
- Lazy loading and persistence contexts can fail outside transactions; "fixing" it by eager-loading every relation bloats the payload.
- If the entity lands in a broker/DLQ, sensitive data may outlive the originating database record.

**Alternative:** build a dedicated, immutable event record carrying only the needed business snapshot. If receiving the event suffices to look up data, carry only a controlled reference; never broadcast entire entities.

For events requiring a snapshot (such as payment amount for reconciliation), decide explicitly whether each field is truly required, which consumers may see it, and how long event data lives. Do not mechanically apply "ID-only" if consumers need **historical point-in-time values** that the current store may later overwrite.

## 7. Are Reference IDs Completely Safe?

No. Referencing merely reduces direct attribute duplication; it does not eliminate data-protection responsibilities.

Proper processing flow:

```text
ProfileChanged(eventId, customerRef, changedFields)
     |
     v
Consumer needing the data
     |
     +-- authenticate service / actor
     +-- verify tenant and legitimate purpose
     +-- check permissions on customerRef
     |
     v
RestrictedCustomerService.load(customerRef)
     |
     +-- return only required fields per policy
     +-- record access audit with safe metadata
     v
Process and delete temporary data per policy
```

Risks to consider:

- **IDOR/BOLA:** a consumer or API using `customerRef` without verifying tenant/subject authorization can read someone else's data.
- **Linkability:** a stable ID appearing across topics/logs enables correlating activities of the same subject.
- **Replay:** an old event may be replayed after a consumer's permissions were revoked; re-lookups must evaluate permissions *at processing time*.
- **Snapshot vs. current state:** if a consumer looks up minutes later, the email may have changed again; lookup results may not reflect the state at event time.
- **Enumeration:** sequential IDs make guessing objects easier; opaque IDs are only a mitigation layer, not a substitute for access control.

When historical and sensitive snapshots are required, you may need a dedicated tightly permissioned event channel, encrypted payloads, or snapshots stored in a protected vault with limited-access references. Design according to purpose and retention; never stuff excessive data into a shared event merely to save one lookup.

## 8. Logging, Tracing, and Observability Easily Leak Payloads

Leaks do not come solely from business listeners. Payloads can enter:

- `INFO`/`DEBUG` logs printing events, parameters, or exception messages.
- Structured logging when loggers reflect fields off records/POJOs.
- MDC, trace baggage, span attributes, metric labels, and APM systems.
- Dead-letter queues, retry topics, failure reports, and error dashboards.
- HTTP access logs, webhook payload dumps, and message serializer debug logs.
- Test snapshots, CI failure logs, JVM heap dumps, and support data exports.

Examples of what not to do:

```java
// If the payload contains PII, this line creates a leak risk.
log.info("Received event {}", event);

// Potentially even more dangerous: turning email into a metric label,
// both leaking data and exploding cardinality.
counter.tag("email", customer.getEmail());
```

A better design logs a vetted **allowlist** of fields:

```java
// Illustrative snippet, requires a real logger in the application.
log.info("eventType=PROFILE_CHANGED changedFields={}",
        event.changedFields());
```

Note that `changedFields` itself can disclose details in sensitive domains. For medical or financial events, you might log only a neutral classified code.

### Masking, Redaction, and `toString()`

- **Not collecting** data into events is better than collecting it and masking afterward.
- When partial logging is unavoidable, use an **allowlist** rather than serializing whole objects and trying regex replacements.
- Custom `toString()` reduces basic log leaks, yet **does not stop JSON/XML/Protobuf serializers** from reading properties.
- Partial masking (e.g., showing 2 characters of an email) can still allow identification. Evaluate whether logging remaining fragments is truly needed.
- Escape/sanitize CR, LF, and delimiters from untrusted content before logging to reduce log-injection risk.
- Never accidentally log request bodies or exceptions containing secrets inside a listener merely while debugging failures.

The OWASP Logging Cheat Sheet recommends excluding, masking, sanitizing, hashing, or encrypting sensitive data depending on context, alongside restricting log access and retention lifecycles. See the references at the end.

## 9. Hashing, HMAC, Tokenization, and Encryption Serve Different Roles

**Hashing is usually insufficient to "anonymize" an email or phone number.** Fields with predictable value spaces are vulnerable to dictionary attacks under plain `SHA-256(email)`. Never broadcast hashed emails to every topic treating them as public data.

Distinguish clearly:

| Technique | Effect | Limitations |
| --- | --- | --- |
| Removing the field | Creates no copy of the data inside the event | Consumers may need a separate lookup flow |
| Tokenization / opaque reference | Replaces the value with a token or ID, resolved via a vault/service | Still must protect tokens, mappings, authorization, and retention |
| HMAC with managed secret key | Produces controlled reference codes from inputs | Keys must be protected/rotated; outputs remain linkable |
| Encryption in transit (TLS) | Protects data over the wire | Authorized consumers still see plaintext; does not protect logs post-decryption |
| Encryption at rest | Reduces risk of reading stored data/replicas | Does not replace authorization or key management |
| Field-level encryption | Encrypts specific sensitive fields in the payload | Requires key management and authorized decrypting consumers; does not fix overly broad broadcasting |

If an event must carry sensitive data in a specialized flow, explicitly define who encrypts, who decrypts, permission bounds, retention limits, key rotation, and deletion/revocation mechanisms. Never invent custom cryptographic algorithms. Encryption does not make an out-of-scope payload legitimate.

## 10. In-Process Events Differ from Message Brokers / Outboxes

### In-Process `ApplicationEvent`

Spring `@EventListener` runs within the same JVM, yet the number of listeners can grow module by module. Simply adding a listener for that type expands who observes the payload. There is no default field-level ACL in the multicaster.

### When Events Go Through a Broker

If a bridge forwards events to Kafka/RabbitMQ or external systems, data can reside in:

- Topics/queues and replicas.
- Lagging consumer groups, retry topics, and dead-letter topics.
- Backups, analytics pipelines, tracing, and operational dumps.
- Schema registries or sample payloads pasted into team documentation.
- Long-term event archives or data-lake pipelines.

Specifically, secrets kept in events do not vanish when the source database deletes them. Define **retention across all copies**, per-topic/consumer permissions, encryption, schema policies, staging handling, and deletion workflows per applicable requirements.

### Transactional Outbox

When durable publication must accompany an aggregate update transaction, write an outbox row and relay it:

```text
BEGIN DB TRANSACTION
    update customer_profile ...
    insert into outbox(event_id, type, customer_ref, changed_fields)
COMMIT

relay (after commit)
    -> read outbox
    -> publish message
    -> retry/mark delivered
```

An outbox solves **surviving crashes** better than in-memory publishing, yet creates a **longer-lived copy**. Therefore outbox schema design must also apply data minimization, field encryption if needed, retention, access controls, and data-deletion policies. Relays can duplicate emissions if they publish before updating status; consumers should be idempotent based on event ID.

### `@TransactionalEventListener` Is Not a Data-Filtering Tool

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` ensures processing only occurs after transaction commit, yet **does not redact payloads**, grant authorization, or prevent consumers from logging secrets. Nor is it durable event persistence across crashes. Separate *when to process* from *what data may be shared*.

## 11. Minimal Payloads That Still Suffice for Business Needs

Not every event is ID-only. A consumer may need a historical snapshot for reconciliation, where looking up current state might return different data.

Consider three cases:

**A. Refreshing a profile cache.** The consumer only needs `customerRef` and `changedFields`, then fetches fresh data via an authorized API. The shared payload needs no email.

**B. Notifying "email changed".** One listener may need to send a confirmation to the new address. Instead of putting `newEmail` into the shared event, dispatch the notification through a dedicated minimal-privilege service, or a dedicated properly authorized and encrypted channel.

**C. Reconciling a payment.** A snapshot like amount, currency, or payment reference may be required for historical immutability. Even so, exclude card numbers, CVV, tokens, and superfluous identifiers; only authorized consumers receive appropriately classified data.

An event schema may include `eventId`, `occurredAt`, `aggregateVersion`, and `schemaVersion` to support replay/idempotency. Include only when needed; timestamps, IDs, and enums can also become linkable information when combined with other datasets.

**Rule:** if you cannot explain "which consumer needs this field and why a less sensitive representation will not work", do not add it to a shared payload.

## 12. Scenarios Where Security Bugs Arise

### 12.1. Putting Entire Request DTOs into Events

Request DTOs often hold authentication details or raw client inputs. Dropping the whole DTO into an event propagates fields never meant for listeners. Construct events from an explicit allowlist schema after business validation.

### 12.2. Using `@Data` / Records and Logging Whole Objects

Lombok-generated `toString()`, Java record default `toString()`, and structured loggers can print every field. Custom redaction methods act as a secondary guardrail, while the durable fix is keeping sensitive fields out of events altogether; verify with log policies and unit tests.

### 12.3. Using Emails or Government IDs as Event IDs

Identifiers can leak through routing keys, metrics, topic partitions, trace tags, or exceptions. Use an appropriate random/opaque ID and restrict mapping to authorized services; never treat opaque IDs as a replacement for authorization.

### 12.4. Consumer Reading Another User's Data via `customerRef`

Emitting an ID does not grant permission. Verify tenant, purpose, and authorization on every lookup. Never treat the fact that a listener runs in the same process as proof that access checks already passed.

### 12.5. Copying Sensitive Context onto Worker Threads

`@Async` or async multicasters switch threads. Never copy entire `ThreadLocal`s, HTTP headers, or security contexts to workers just "for convenience"; propagate only required, authorized context using safe mechanisms. When events are processed minutes later, current authentication and permissions may already have changed.

### 12.6. Replaying Old Events While Ignoring New Data Policies

A consumer replaying long-lived events can resurrect data that expired or was deleted under retention policies. Control retention and access across **brokers, DLQs, outboxes, backups, and consumer stores**; plan migrations, deletions, or tombstones per real technology and legal obligations.

### 12.7. Using PII as Metric Tags

Tags like `email`, `phone`, or `customerId` explode cardinality, waste resources, and expose data to dashboard viewers. Use low-cardinality labels such as neutral event types, outcomes, module names, or standardized error codes.

### 12.8. Believing Encryption Solves Every Risk

If every consumer holds the decryption key, the event is still over-broadcast. If payloads are logged before encryption or after decryption, TLS and encryption at rest cannot save them. Access control, minimization, monitoring, and incident-response processes remain mandatory.

## 13. Testing Safe Payloads

Beyond testing that events are delivered properly, test **what data must never be present**:

1. **Schema allowlist:** `ProfileChanged` has no `email()`, `password()`, or `accessToken()` accessors; consumers receive only allowed fields.
2. **Business outcome:** updating the email in the repository succeeds while listeners receive only minimal metadata.
3. **No log leaks:** inspect captured logs from publishers, listeners, errors, and serializers to confirm no test email addresses or dummy tokens appear.
4. **Actual JSON:** if using Jackson/Avro/Protobuf for a broker, serialize the event in tests and inspect the key list. `toString()` does not prove JSON safety.
5. **Indirect fields:** attempt using a customer ID from another tenant; lookup listeners/services must deny access when unauthorized.
6. **Async/replay:** receivers must not rely on the publisher's `SecurityContextHolder`; replays must enforce permissions and retention at processing time.
7. **DLQs and outboxes:** publish/consume failures must not push secrets into error messages, raw headers, or dead-letter bodies.
8. **Idempotency:** event IDs contain no PII, and consumers do not repeat side effects when receiving the same event again.
9. **Snapshots:** for workflows needing historical values, verify schemas store just enough and are protected per classification.
10. **Schema change review:** adding any new field must undergo consumer, logging, retention, access-control, and backward-compatibility review.

A quick code-review check is listing all event fields and answering four questions for each: **Who needs it? What for? Where will it be stored? For how long?** If you cannot answer, that field may be introducing unnecessary risk.

### Test Snippet Avoiding Common Mistakes

```java
// This is a testing idea, not a standalone JUnit class.
// Do not verify safety solely via profileChanged.toString().
String json = objectMapper.writeValueAsString(profileChanged);
assertFalse(json.contains("replacement@example.invalid"));
assertFalse(json.contains("accessToken"));
```

However, a test using `contains(...)` is a **supplementary guardrail**, not a replacement for schema structure checks, privacy classification, and authorization testing. Configure the actual production serializer and avoid printing sensitive JSON in assertion failure messages.

## 14. Implementation Checklist

- [ ] Identify consumers and purposes before locking down event types/schemas.
- [ ] Enforce a field allowlist; exclude credentials, tokens, passwords, and unnecessary data.
- [ ] Use immutable events; avoid mutable entities/DTOs and deep object graphs.
- [ ] Treat opaque IDs as linkable data; verify tenant and authorization at lookup time.
- [ ] Ensure loggers, tracers, metrics, exceptions, and DLQs never record prohibited fields.
- [ ] Separate publish/commit timing decisions from data-sharing decisions.
- [ ] With brokers/outboxes, define retention, encryption, consumer ACLs, deletion, and replay policies.
- [ ] Account for idempotency, historical data, schema versions, and consumer permission changes.
- [ ] Include tests for excluded fields, serialized output, logs, and cross-tenant access.
- [ ] Assess privacy/security impact whenever adding a new field or expanding consumers.

**Conclusion:** a well-designed event is not one packed with "everything anyone might find handy", but one with **clear semantics, minimal data, and controlled access and lifecycle**. In Spring Framework, multicasters and annotations handle event distribution; protecting sensitive data remains the responsibility of domain design, the application layer, and operational infrastructure.

## References

- [Spring Framework 6.2 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Application Events and `@EventListener`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — API Security Top 10: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
