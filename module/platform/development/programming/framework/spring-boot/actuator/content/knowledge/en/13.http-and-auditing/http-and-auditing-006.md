# Roles of AuditEvent and AuditEventRepository

## 1. From a business action to audit evidence

Suppose an operator changes another user's access permissions. When reviewing afterward, the question is not just "what status code did the API return?" but also:

- Who performed the action?
- What action occurred?
- At what time?
- Which target was affected and with what outcome?

An access log line containing `POST /permissions -> 200` can help locate the HTTP call, yet it does not fully describe the business meaning. We need a structured event, and then a place to receive and query those events.

In Spring Boot Actuator:

- **`AuditEvent` is the data describing an audit event.**
- **`AuditEventRepository` is the contract for adding and finding audit events.**

These two roles are separate. Creating an event object does not mean it has been stored; having a repository also does not mean the application automatically knows every action that needs auditing.

This lesson uses Spring Boot **3.3.x** APIs. Actuator's auditing mechanism supports security events and business events published by the application. [Spring Boot 3.3: Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

## 2. AuditEvent: describing what happened

### Four core components

| Component | Java data type | Role | Example |
| --- | --- | --- | --- |
| `timestamp` | `Instant` | When the event was recorded based on how the object was constructed | `2024-01-01T00:00:00Z` |
| `principal` | `String` | Name of the actor associated with the event | `operator-1` |
| `type` | `String` | Event type | `ROLE_GRANTED` |
| `data` | `Map<String, Object>` | Structured supplementary information | Target, granted role, outcome, correlation ID |

`principal` here is a **name string**, not the full `Authentication` object, credential list, or a new authentication mechanism.

`type` is also a string. Business event types need clear, stable conventions with distinct meanings. For example, `ROLE_CHANGE_REQUESTED` describes a change request; `ROLE_GRANTED` should indicate that granting the role reached the successful state the system wants to confirm. The two names should not be used interchangeably.

### Creating an event with an explicit timestamp

Illustrative Java snippet using Actuator classes:

```java
AuditEvent event = new AuditEvent(
        Instant.parse("2024-01-01T00:00:00Z"),
        "operator-1",
        "ROLE_GRANTED",
        Map.of(
                "target", "user-7",
                "role", "REPORT_READER",
                "outcome", "SUCCESS",
                "eventId", "audit-demo-001"));
```

This is a snippet creating an object, not a standalone program, and it performs no storage operation yet.

The constructor accepting a timestamp helps make experiments reproducible or represent an already-determined event time. Constructors without a timestamp use the time the event is created. Do not assume `timestamp` equals the time a database committed the transaction or the time an external system actually finished the work.

Supplementary data should explain the event, but should not become a copy of every application object. For a permission change, the role name and target identifier are usually more useful than stuffing an entire user profile into `data`.

### What does AuditEvent not guarantee on its own?

An object holding audit fields does not automatically:

- Verify that the recorder is genuinely the stated `principal`.
- Validate that the business action actually succeeded.
- Write to a database or export to a storage system.
- Generate a unique event identifier.
- Protect data against modification/deletion across its entire lifecycle.
- Emit an audit event for every API.

Therefore, obtaining the actor name from a trusted authentication context and emitting events at the right business point are the application's responsibility. Do not trust a client-supplied `actor` field and use it as-is as proof of who performed an action.

### Be careful with mutable data

In the Spring Boot 3.3.0 implementation verified in this lesson, `data` is wrapped as an unmodifiable map through `getData()`. This does not mean the entire source map and nested objects inside it were deep-copied.

If you retain a mutable source map, or place mutable entities/lists inside it, the contents seen later may differ from when the event was created.

Prefer simple values and a stable data snapshot. `Map.of(...)` in the example uses ready-made strings, which helps avoid accidentally mutating the map later. If using `Map.copyOf`, remember it is still not a deep copy of all nested objects.

## 3. AuditEventRepository: the contract for writing and finding

The central interface has two operations:

```java
void add(AuditEvent event);

List<AuditEvent> find(String principal, Instant after, String type);
```

This is the signature for understanding the API, not a complete repository class. The interface lives in package `org.springframework.boot.actuate.audit`.

### add accepts an event for the implementation to store per its contract

Example:

```java
repository.add(event);
```

`AuditEventRepository` hides storage details so the event producer does not need to know whether the backend is memory, a database, or a custom mechanism.

However, sharing the same `add` signature does not mean every implementation has the same data durability. An in-memory repository accepting an event differs from an implementation that has successfully written to durable storage under its guarantees.

The `void` return type is also not an automatic guarantee that the event was replicated, backed up, or delivered exactly once.

### find filters by three conditions

| Parameter | When non-null | When `null` |
| --- | --- | --- |
| `principal` | Filter by actor name | No restriction by actor |
| `after` | Select events after the given timestamp | No restriction by this timestamp |
| `type` | Filter by event type | No restriction by type |

Non-null conditions are combined together. Example:

```java
repository.find(
        "operator-1",
        Instant.parse("2024-01-01T00:00:00Z"),
        "ROLE_GRANTED");
```

This query searches for events matching the actor, matching the type, and occurring after the given timestamp, within the dataset held by the implementation. Parameter semantics are described in the [AuditEventRepository API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html); the corresponding signatures were verified directly against the 3.3.0 library used in the experiment.

With `InMemoryAuditEventRepository` verified below, `after` is a **strictly after** condition: an event with a timestamp equal to the boundary is excluded. Do not interpret it as `timestamp >= after`.

`null` for the principal parameter means "do not filter by actor", not "find only events of anonymous users".

### This is neither a CRUD interface nor an authorization filter

Do not call `save`, `findAll`, or Spring Data methods assuming they belong to `AuditEventRepository`. This standard interface defines only the two operations above; it does not provide pagination, updates, deletion, or querying by target ID inside `data` by default.

The `principal` parameter is a **data query criterion**, not authentication of the caller running the query. Someone permitted to call `find(null, null, null)` can receive all events still retained by the implementation. Read permissions and data boundaries must be enforced in the consuming layer.

You also should not rely on a universal sort order if the implementation contract does not specify one. When pagination or stable ordering is needed, design the API and store accordingly.

## 4. Two paths for delivering events into the repository

### Direct path

```text
Business code
    -> create AuditEvent
    -> call AuditEventRepository.add
    -> implementation receives/stores
```

This approach is straightforward: a business class or a dedicated audit service receives the repository via dependency injection and calls `add`.

Its advantage is a clear write path. In return, the caller needs a write-error handling policy, an explicit timing choice, and clarity on whether this write has any transactional coupling with the business operation.

### Application-event path

```text
Business code or security event bridge
    -> AuditApplicationEvent wrapping AuditEvent
    -> ApplicationEventPublisher
    -> AuditListener
    -> AuditEventRepository.add
```

`AuditApplicationEvent` is the event class used for Spring's event mechanism. It wraps `AuditEvent`, and the default `AuditListener` receives that event type and forwards the data to the repository.

Example of publishing an event in an application with suitable auditing infrastructure:

```java
publisher.publishEvent(new AuditApplicationEvent(event));
```

Do not assume `publisher.publishEvent(event)` where `event` is a bare `AuditEvent` will flow through the default listener. Spring may broadcast it as an application payload, but a listener accepting `AuditApplicationEvent` does not automatically handle arbitrary types.

Spring Boot documents both using the repository directly and publishing `AuditApplicationEvent` for business events. [Boot 3.3 Custom Auditing Guide](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html#actuator.auditing.custom).

### Publishing an event differs from durable storage

`ApplicationContext`'s event mechanism is an in-application communication path, not automatically a durable messaging system. With the default event multicaster, listeners are invoked synchronously on the publishing thread; if the multicaster is replaced or switched to asynchronous execution, error handling and completion timing must be re-evaluated. [Spring Framework: Application events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).

Do not both call `repository.add(event)` and publish the wrapper for the same event through that listener, unless two write paths are intentionally handled. Otherwise, one action can produce two records. The repository interface provides no automatic deduplication by `eventId`.

## 5. First experiment: creating, storing, finding, and buffer limits

### Test project

Both programs in this lesson are Java programs with `main` and do not open an HTTP server. They use Spring Boot 3.3.0 and the corresponding Spring Framework so results are reproducible with Java 17 or later.

Create `pom.xml` in a separate test directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>audit-roles-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
    </dependencies>
</project>
```

Save the first program at `src/main/java/AuditRepositoryDemo.java`:

```java
import java.time.Instant;
import java.util.Map;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;

public class AuditRepositoryDemo {
    private static final Instant BASE = Instant.parse("2024-01-01T00:00:00Z");

    public static void main(String[] args) {
        AuditEventRepository repository = new InMemoryAuditEventRepository(3);
        AuditEvent first = event(0, "operator-1", "LIMIT_CHANGED");

        System.out.println("before.add=" + repository.find(null, null, null).size());
        repository.add(first);
        System.out.println("after.add=" + repository.find(null, null, null).size());
        System.out.println("first.type=" + first.getType());
        System.out.println("first.target=" + first.getData().get("target"));

        repository.add(event(1, "user-2", "AUTHENTICATION_FAILURE"));
        repository.add(event(2, "operator-1", "LIMIT_CHANGED"));

        System.out.println("all=" + repository.find(null, null, null).size());
        System.out.println("operator.limitChanges="
                + repository.find("operator-1", null, "LIMIT_CHANGED").size());
        System.out.println("after.t1="
                + repository.find(null, BASE.plusSeconds(1), null).size());
        System.out.println("after.t2.strict="
                + repository.find("operator-1", BASE.plusSeconds(2), "LIMIT_CHANGED").size());

        repository.add(event(3, "operator-1", "LIMIT_CHANGED"));
        System.out.println("after.overflow=" + repository.find(null, null, null).size());
        boolean oldestRetained = repository.find(null, null, null).stream()
                .anyMatch(item -> item.getTimestamp().equals(BASE));
        System.out.println("oldest.retained=" + oldestRetained);
        System.out.println("fresh.repository="
                + new InMemoryAuditEventRepository(3).find(null, null, null).size());
    }

    private static AuditEvent event(long seconds, String actor, String type) {
        return new AuditEvent(BASE.plusSeconds(seconds), actor, type,
                Map.of("target", "account-42", "eventId", "audit-" + seconds));
    }
}
```

Compile and gather dependencies with Maven:

```bash
mvn -q compile dependency:copy-dependencies
```

Run on Windows PowerShell:

```powershell
java -cp 'target/classes;target/dependency/*' AuditRepositoryDemo
```

On Linux/macOS:

```bash
java -cp 'target/classes:target/dependency/*' AuditRepositoryDemo
```

Dependencies must be downloadable if not already cached. All identifiers and actions in the example are synthetic data; no real limit changes occur.

Exact stdout:

```text
before.add=0
after.add=1
first.type=LIMIT_CHANGED
first.target=account-42
all=3
operator.limitChanges=2
after.t1=1
after.t2.strict=0
after.overflow=3
oldest.retained=false
fresh.repository=0
```

### What the example proves

1. After creating `first`, the repository still has no records: `before.add=0`.
2. Calling `add` places the event into the active store: `after.add=1`.
3. The event retains descriptive data such as action type and target.
4. Combining actor and event-type filters finds two `LIMIT_CHANGED` events.
5. Filtering after `t1` matches only the event at `t2`.
6. The event at exact `t2` is not selected by the "after `t2`" condition.
7. Adding a fourth event to a three-slot buffer evicts the oldest event.
8. Creating a new repository produces an empty in-memory store.

Do not treat `fresh.repository=0` as a test of a durable store restarting. It merely illustrates that state belongs to the in-memory repository object, not automatically to a shared external store.

## 6. Second experiment: what do the wrapper and listener do?

Save the next program at `src/main/java/AuditPublicationDemo.java` in the same test project:

```java
import java.time.Instant;
import java.util.Map;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.boot.actuate.audit.listener.AuditListener;
import org.springframework.context.support.GenericApplicationContext;

public class AuditPublicationDemo {
    public static void main(String[] args) {
        var repository = new InMemoryAuditEventRepository(10);

        try (var context = new GenericApplicationContext()) {
            context.addApplicationListener(new AuditListener(repository));
            context.refresh();

            AuditEvent wrapped = new AuditEvent(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    "operator-1", "ROLE_GRANTED",
                    Map.of("target", "user-7", "role", "REPORT_READER"));
            context.publishEvent(new AuditApplicationEvent(wrapped));
            System.out.println("after.wrapper="
                    + repository.find(null, null, null).size());

            AuditEvent plain = new AuditEvent(
                    Instant.parse("2024-01-01T00:00:01Z"),
                    "operator-1", "ROLE_REVOKED",
                    Map.of("target", "user-7", "role", "REPORT_READER"));
            context.publishEvent(plain);
            System.out.println("after.plain="
                    + repository.find(null, null, null).size());

            repository.add(plain);
            System.out.println("after.direct="
                    + repository.find(null, null, null).size());
        }
    }
}
```

Recompile after adding the file. On Windows PowerShell:

```powershell
mvn -q compile dependency:copy-dependencies
java -cp 'target/classes;target/dependency/*' AuditPublicationDemo
```

On Linux/macOS, change the classpath separator to `:`.

Exact stdout:

```text
after.wrapper=1
after.plain=1
after.direct=2
```

How to read it:

- `after.wrapper=1`: the listener received `AuditApplicationEvent` and added the event to the repository.
- `after.plain=1`: publishing a bare `AuditEvent` does not cause the registered listener to match the wrong type; the record count does not increase.
- `after.direct=2`: calling the repository directly still stores the second event.

The program intentionally creates a `GenericApplicationContext` and registers `AuditListener` to show the mechanism clearly. It does not run Spring Boot's auto-configuration and does not simulate an actual login.

In a Boot application with proper auditing auto-configuration, do not register an identical listener just because the example calls `addApplicationListener`: check existing beans to avoid two listeners both writing the same event.

The example also does not claim every bare `AuditEvent` published will always be ignored in every application. If an application defines its own listener for that type, behavior depends on that listener. The takeaway here is that **only the matching wrapper type matches the default listener being demonstrated**.

## 7. Wiring the repository into a Spring Boot application

A development configuration can declare the bean:

```java
package example.audit;

import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditStorageConfiguration {

    @Bean
    AuditEventRepository auditEventRepository() {
        return new InMemoryAuditEventRepository(200);
    }
}
```

This is a configuration snippet added to an application, not a file to add to the `main` project of the two experiments.

The repository bean provides the event sink for the corresponding auditing infrastructure. When Spring Security and auditing are configured appropriately, events such as authentication success/failure or access denied can be converted into audit events.

That does not mean every HTTP 401/403 automatically produces the same audit record. You must check the rejection point, authentication/authorization mechanism, and actual event-publishing path.

Business actions such as granting report access, exporting data, or confirming a change still must be emitted by the application with accurate semantics. Infrastructure does not automatically know which business event a method or URL corresponds to.

### Repository and endpoint have different roles

If the `auditevents` endpoint is enabled and exposed, the endpoint provides read access to events from the repository. It does not replace creating or storing events.

Endpoint read permissions must be controlled separately. An event having `principal=operator-1` does not mean only that user can see it; that is data inside the event, not an access-control rule.

In multi-tenant/multi-customer systems, data boundaries also must be designed explicitly. Do not use a client-supplied filter parameter as an authorization mechanism.

## 8. Choosing an implementation by retention responsibility

### In-memory repository

`InMemoryAuditEventRepository` is convenient for learning, verifying event flows, and diagnostics during development. It retains a capacity-bounded set inside the process.

Consequences:

- Restarting loses process state.
- Each instance has its own store.
- Exceeding capacity causes older events to disappear.
- A record-count limit does not equal a byte limit or day count.
- There is no built-in durable, tamper-evident history across the entire system.

Spring recommends a different repository solution based on production requirements rather than relying on the in-memory implementation in production. Do not judge audit completeness solely by whether the endpoint currently returns a few records.

### Custom repositories need an operational contract

If implemented with a database or centralized store, clarify:

| Responsibility | Question to resolve |
| --- | --- |
| Writing data | When is an `add` call considered successfully accepted? |
| Durability | Does data survive when the application/instance terminates? |
| Write failures | Should the business action proceed, fail, or route to a recovery mechanism? |
| Deduplication | If the same event is resent, which key identifies it? |
| Querying | How are filters, ordering, result limits, and data scope supported? |
| Lifecycle | Who may read, how long is data retained, and by what process is it deleted? |
| Integrity | Who can modify/delete; is tamper detection needed? |

The `AuditEventRepository` interface is an extension point for swapping the implementation, not a complete design covering all the requirements above.

Timestamps are not unique keys. Multiple events can share the same timestamp; `after` alone is insufficient as an exact-once cursor across arbitrary data stores. If forwarding or syncing with a resume cursor is required, design appropriate identifiers and ordering.

## 9. Business timing and audit data must match

Suppose an application writes `ROLE_GRANTED` before the role-change transaction commits, and then the transaction rolls back. An independent repository may still hold an event describing a change that never actually succeeded.

Conversely, if writing only after the business work finishes and the process crashes before writing the audit record, an event can be lost. `AuditEvent` and `AuditEventRepository` alone do not close this gap.

You must distinguish "requested", "attempted", "succeeded", and "failed" events, then choose appropriate transaction binding or store-and-forward mechanisms. Spring has listeners bound to transaction phases, though choosing that mechanism is a separate design; the default auditing listener does not automatically carry every `AFTER_COMMIT` guarantee a business flow requires. [Spring Framework: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Also do not record a "success" purely based on HTTP 200. An API may reply that a request was accepted while asynchronous work has not finished yet.

## 10. Keeping audit data useful and controlled

A good event helps answer questions without retaining excess sensitive data:

- Choose clear target IDs, action names, and outcomes.
- Use correlation IDs to look up details when needed instead of copying the whole request.
- Do not store passwords, bearer tokens, session cookies, or full authentication objects.
- Keep only genuinely needed before/after values; apply dedicated rules for sensitive fields.
- Bound the size and shape of `data`, avoiding holding entire mutable entity graphs.
- Distinguish the actor performing the action from the affected target.
- Do not treat calling `toString()` and writing to console as a complete audit store.

Do not confuse Actuator auditing with storage-layer auto-population features like `createdBy`, `createdDate` in Spring Data auditing. One describes events; the other typically attaches metadata to data records. They can complement each other but do not replace each other.

## 11. Self-check practice

1. You create `new AuditEvent(...)` without calling the repository or publishing the wrapper. Does the repository automatically receive the event?
2. In a permission-grant event, which field is the performing actor and which is the affected target?
3. Does `find(null, null, null)` mean finding only anonymous events?
4. Why was an event whose timestamp equaled the `after` boundary excluded in the experiment?
5. Why did publishing a bare `AuditEvent` not increase the record count in the second program?
6. If a repository retains only three events, does an empty query result prove an event never happened?
7. If events must survive restarts and avoid duplicate writes on retries, which responsibilities are not met by an in-memory repository?

Comparison: creating an object does not store it; principal and target play different roles; `null` in filters means unrestricted. The repository returns data according to what the implementation retains, while the meaning, timing, and reliability of audit evidence require a consistently designed create–write–read pipeline.
