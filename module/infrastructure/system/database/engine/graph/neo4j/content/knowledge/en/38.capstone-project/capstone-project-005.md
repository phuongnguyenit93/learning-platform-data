# Integrating Java or Spring Boot with Transactions and Error Handling

A production-ready Neo4j application needs more than Cypher queries returning right answers in Neo4j Browser. When users send HTTP requests, the system must **authenticate, authorize, manage transactions, prevent half-written state, handle concurrent requests, retry appropriate errors, and return reconcilable results**. This bridges graph data modeling with building an operable Java backend.

This lesson belongs to the **Capstone Project** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses Neo4j to model connected data as a **property graph**, query nodes, relationships, and paths with Cypher, apply indexes/constraints, ingest data, integrate Java Driver and Spring Data Neo4j, and follow operational principles. This capstone brings those pieces together into a **Spring Boot + Neo4j Java Driver** application with explicit transactions and error handling. Near the end, it also covers replacing the data-access layer with Spring Data Neo4j (SDN).

**Problem statement:** build an event seat-booking API. An attendee requests a number of seats; the system must verify remaining capacity, deduct seats, and create the booking record and its relationships **within a single Neo4j transaction**. If a client retries after a timeout, the system must not deduct seats twice. If multiple users compete for the last seats, total confirmed seats must never exceed capacity.

After completing this lesson, you will have:

1. A property graph model and Cypher schema with business keys, indexes, and constraints.
2. A `POST /api/v1/bookings` API and a lookup query using the idempotency key.
3. A Java service using `Driver`, `Session`, `executeWrite`, and parameterized Cypher queries.
4. A locking/serialization strategy for seat inventory updates under concurrency.
5. An error policy covering invalid input, missing entities, insufficient seats, duplicate requests, connection drops, and unknown commit outcomes.
6. A test matrix, acceptance criteria, baseline observability metrics, and a deployment/rollback plan.

> **Scope:** code snippets illustrate compatible Java 17+, Spring Boot, Spring Data Neo4j, and Neo4j Java Driver patterns. Configuration syntax, driver APIs, and test dependencies should be checked against your exact versions. This lesson presents self-contained architecture and sample code for building the capstone; it does not claim to ship a pre-built project or a running Neo4j server.

## 1. Business Requirements and Acceptance Criteria

Suppose an organization hosts multiple events. Each event has a total capacity and remaining available seats. Authenticated users can book 1 to 5 seats per request.

| ID | Requirement | Verification criteria |
| --- | --- | --- |
| R01 | Only authenticated users can book. | Missing/invalid principal is rejected before touching the database. |
| R02 | No cross-tenant reads or writes. | Tenant is verified from security context; all nodes in a transaction share the same tenant. |
| R03 | Available seats never go negative. | Even under concurrent requests, `availableSeats >= 0` holds after all committed transactions. |
| R04 | Never deduct seats if booking fails. | If creating Booking/relationships fails, seat updates roll back completely. |
| R05 | One idempotency key represents one request. | Replaying the same key + payload returns the same booking; same key + different payload is rejected. |
| R06 | Business keys never duplicate. | Constraints prevent two Bookings from sharing a key within a tenant. |
| R07 | Network errors never cause duplicate bookings. | Client reuses the same key; server reconciles previously committed state when needed. |
| R08 | Only open events can be booked. | Non-`OPEN` events are rejected without deducting seats. |
| R09 | Responses never leak internal details. | Never expose stack traces, raw Cypher, passwords, or unnecessary properties. |
| R10 | Observable and recoverable. | Logs/metrics record request IDs, error codes, latency; backup and restart tested in isolation. |

These are minimum requirements. Cancellations, seat refunds, payments, and waitlists are **outside the primary write flow**; they can be added as extensions with dedicated transactions and idempotency rules.

## 2. Choosing the Property Graph Model

A suitable model:

~~~text
(:CapAttendee {tenantId, attendeeId, displayName})
             |
             | [:CAP_HAS_BOOKING]
             v
(:CapBooking {
  tenantId, bookingId, requestKey,
  attendeeId, eventId, seats, remainingAfter,
  status, createdAt
})
             |
             | [:CAP_FOR_EVENT]
             v
(:CapEvent {
  tenantId, eventId, title,
  capacity, availableSeats, status, lockVersion
})
~~~

Why model **Booking as a node** instead of just a relationship from Attendee to Event?

- A booking has its own lifecycle, status, request key, seat count, and timestamp.
- A uniqueness constraint on `(tenantId, requestKey)` is needed to enforce idempotent requests.
- One person can book multiple times for the same event if allowed by business rules; each booking gets its own identity.
- It is easy to attach auditing, cancellation, payment state, or outbox records later.

Relationships follow a **fixed direction**: `(Attendee)-[:CAP_HAS_BOOKING]->(Booking)-[:CAP_FOR_EVENT]->(Event)`. Never create reversed edges and rely on undirected traversals to “compensate.”

### 2.1. Data Invariants

Define invariants clearly before writing Java:

| ID | Invariant | Primary protection |
| --- | --- | --- |
| I1 | `0 <= availableSeats <= capacity`. | Atomic transaction updating the Event with seat checks and write lock. |
| I2 | Every Booking links to exactly one valid Attendee and Event. | Cypher creates links in the same transaction; invariant verification tests. |
| I3 | Booking and both endpoints share `tenantId`. | Queries scope every node by tenant from security context. |
| I4 | `(tenantId, bookingId)` is unique. | Neo4j uniqueness constraint. |
| I5 | `(tenantId, requestKey)` is unique. | Neo4j uniqueness constraint + payload verification on replay. |
| I6 | A `CONFIRMED` Booking exists only if seats were deducted. | Atomic Neo4j transaction. |
| I7 | Retrying with the same key creates no extra Booking. | Pre-read, post-lock re-read, constraint, and collision reconciliation. |

**Note:** standard composite uniqueness constraints enforce uniqueness **when values are present**; they do not automatically require all properties to exist. Enforce presence via API/Java validation or edition-appropriate node-key/existence constraints.

## 3. Application Architecture and Transaction Boundaries

~~~text
Web/Mobile Client
   |
   | POST /api/v1/bookings
   | Idempotency-Key: <request-key>
   v
Spring Security / Authn
   |
   v
BookingController
   |
   +--> TenantScope: tenant from verified principal
   |
   +--> BookingService
           |
           | Neo4j Driver executeWrite(...)
           v
       Neo4j transaction
         1. Look up existing requestKey
         2. Acquire write lock on Event
         3. Re-check requestKey
         4. Verify Attendee, Event, and available seats
         5. Deduct seats + create Booking + create two relationships
         6. COMMIT or ROLLBACK atomically
           |
           v
      BookingReceipt (DTO)
~~~

The boundary is **one Neo4j transaction** for every graph mutation involved. Never split `SET availableSeats` and `CREATE Booking` into two independent autocommit `session.run(...)` calls.

Component responsibilities in the capstone:

| Component | Responsibility | Must never do |
| --- | --- | --- |
| Spring Security | Authenticate user; provide trusted principal/claims. | Never trust a client-supplied tenant header as authorization proof. |
| Controller | Validate JSON/headers and select HTTP status codes. | Never build Cypher by concatenating user strings. |
| TenantScope | Verify user permission for the tenant. | Never fall back to a default tenant when principal is null. |
| BookingService | Coordinate idempotency, transaction, and domain errors. | Never send emails or broker messages inside a retryable callback. |
| Neo4j Driver | Manage sessions, transactions, routing, and transient retries. | Never infer domain seat/tenant invariants on its own. |
| Neo4j | Store graph, enforce transactions/constraints, and hold write locks. | Never protect HTTP endpoints from unauthorized users on its own. |

## 4. Environment Setup and Dependencies

Minimum capstone environment:

- A JDK supported by your chosen Spring Boot version (e.g., Java 17+ on compatible lines).
- A **test** Neo4j instance with privileges to create `Cap*` schema and data.
- Spring Boot with Web, Validation, Security, and Spring Data Neo4j starter (which autoconfigures `Driver`).
- An HTTP client, Neo4j Browser/Cypher Shell, and JUnit testing framework.
- Optional: Testcontainers Neo4j for automated integration tests.

Example **Gradle Kotlin DSL** dependencies, assuming the Spring Boot plugin and compatible dependency management/BOM:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:neo4j")
}
~~~

Never guess “latest” versions or mix incompatible Boot/SDN/Java Driver majors. Pin versions through an approved BOM/lockfile and verify compatibility with your Neo4j server.

### 4.1. Connecting Without Hardcoded Credentials

Example `application.yml`:

~~~yaml
spring:
  neo4j:
    uri: ${NEO4J_URI}
    authentication:
      username: ${NEO4J_USERNAME}
      password: ${NEO4J_PASSWORD}
~~~

Environment variables must be injected by a secret manager or deployment config; never commit passwords to Git or print them to logs. Use `neo4j+s://` or Bolt/TLS with verified certificates in real deployments; never disable TLS verification in production to bypass connection errors.

Spring Data Neo4j starter autoconfigures an `org.neo4j.driver.Driver` bean in compatible Boot setups; the code below **injects that Driver** rather than creating ad-hoc extra pools.

### 4.2. Suggested Project Structure

~~~text
src/main/java/.../
  BookingApplication.java
  api/
    BookingController.java
    BookingInput.java
    BookingReceipt.java
    ApiErrorHandler.java
  security/
    TenantScope.java
    SecurityConfiguration.java
  booking/
    BookingService.java
    BookingProblem.java
  monitoring/
    RequestCorrelationFilter.java

src/main/resources/
  application.yml
  migrations/            (Cypher schema scripts)

src/test/java/.../
  BookingIntegrationTest.java
  BookingConcurrencyTest.java
  BookingSecurityTest.java
~~~

This is a **reference layout for the learner's own project repository**, not files pre-created outside this lesson.

## 5. Neo4j Schema: Create Constraints Before Opening the API

Run in a **learning/test** database. Constraint names are prefixed to avoid colliding with other systems:

~~~cypher
CREATE CONSTRAINT cap_attendee_key IF NOT EXISTS
FOR (a:CapAttendee)
REQUIRE (a.tenantId, a.attendeeId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT cap_event_key IF NOT EXISTS
FOR (e:CapEvent)
REQUIRE (e.tenantId, e.eventId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT cap_booking_key IF NOT EXISTS
FOR (b:CapBooking)
REQUIRE (b.tenantId, b.bookingId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT cap_booking_request_key IF NOT EXISTS
FOR (b:CapBooking)
REQUIRE (b.tenantId, b.requestKey) IS UNIQUE;
~~~

The two constraints on Booking serve distinct purposes: `bookingId` identifies the persisted result; `requestKey` identifies an **authorized client intent** for safe retry reconciliation.

Verify:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'cap_'
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Creating a constraint over existing data with duplicate keys fails. Never delete duplicate nodes blindly; reconcile the records and resolve duplicates per business rules. Uniqueness constraints create backing lookup indexes; never `DROP INDEX` on a constraint's backing index during “index cleanup.”

### 5.1. Sample Fixture Data

~~~cypher
MERGE (a:CapAttendee {
  tenantId: 'tenant-demo',
  attendeeId: 'A01'
})
ON CREATE SET a.displayName = 'Sample Attendee 01';
~~~

~~~cypher
MERGE (e:CapEvent {
  tenantId: 'tenant-demo',
  eventId: 'E01'
})
ON CREATE SET
  e.title = 'Neo4j Workshop',
  e.capacity = 3,
  e.availableSeats = 3,
  e.status = 'OPEN',
  e.lockVersion = 0;
~~~

`ON CREATE SET` intentionally initializes seat inventory only when the event is first created. Re-running the fixture will not reset `availableSeats` or overwrite active bookings.

Create a second attendee for concurrency testing:

~~~cypher
MERGE (a:CapAttendee {
  tenantId: 'tenant-demo',
  attendeeId: 'A02'
})
ON CREATE SET a.displayName = 'Sample Attendee 02';
~~~

**Never use production data for practice** and never reset capacity/seats on a live ticketing event by re-running a seed script.

## 6. HTTP Contract: Request, Response, and Errors

### 6.1. Creating a Booking

~~~http
POST /api/v1/bookings HTTP/1.1
Content-Type: application/json
Authorization: Bearer <valid-token>
Idempotency-Key: req-demo-001

{
  "attendeeId": "A01",
  "eventId": "E01",
  "seats": 2
}
~~~

Illustrative initial response:

~~~json
{
  "bookingId": "b2db6cc2-4f75-45b3-b7bb-1ed9ca2f67b5",
  "status": "CONFIRMED",
  "seats": 2,
  "remainingAfter": 1,
  "replayed": false
}
~~~

Resending the same `Idempotency-Key` and payload returns the **same `bookingId`/`seats`/`remainingAfter`** with `replayed: true`. Remaining seats on the event may later drop due to other bookings, but `remainingAfter` on this receipt reflects the **snapshot when this booking committed**, not live inventory.

### 6.2. Error Status Table

| Case | Suggested HTTP | Application error code |
| --- | --- | --- |
| Invalid JSON/headers, seats outside 1..5 | 400 | `INVALID_REQUEST` |
| Unauthenticated | 401 | `UNAUTHENTICATED` |
| User not permitted to book in tenant | 403 | `FORBIDDEN` |
| Event/Attendee absent in allowed scope | 404 | `ENTITY_NOT_FOUND` |
| Event closed or insufficient seats | 409 | `EVENT_UNAVAILABLE` / `NO_SEATS` |
| Existing request key with different payload | 409 | `IDEMPOTENCY_KEY_REUSED` |
| Driver temporarily unreachable / retry budget spent | 503 | `TEMPORARY_UNAVAILABLE` |
| Uncertain whether transaction committed | 503 or pending lookup status | `OUTCOME_UNKNOWN` |
| Unexpected implementation/schema error | 500 | `INTERNAL_ERROR` |

Never return raw Neo4j `ClientException` messages, stack traces, or Cypher strings to HTTP clients. Classify errors like constraint collisions **by context** rather than blindly mapping every database error to HTTP 409.

## 7. Java DTOs and Tenant Validation

Java 17+ with Bean Validation. Place these two records in **two separate files**, `BookingInput.java` and `BookingReceipt.java` (in the same API package), even though they are shown together here:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record BookingInput(
    @NotBlank String attendeeId,
    @NotBlank String eventId,
    @Min(1) @Max(5) int seats
) {}
~~~

~~~java
public record BookingReceipt(
    String bookingId,
    String status,
    int seats,
    int remainingAfter,
    boolean replayed
) {}
~~~

If your Spring Boot/Validation version uses a different package namespace, adjust imports accordingly. `BookingInput` accepts only client-controllable fields—**never `tenantId` or `availableSeats` in the request body**.

Tenant resolution contract:

~~~java
import java.security.Principal;

public interface TenantScope {
    // Verify principal, check tenant access, and return trusted tenant ID.
    // If unverifiable: reject; never return a default tenant.
    String requireTenant(Principal principal);
}
~~~

**Tenant-level** permission does not automatically mean a user can book for **every attendee** in that tenant. Add an object-level authorization contract:

~~~java
import java.security.Principal;

public interface BookingAccess {
    // Reject if the principal is not authorized to book for this attendee.
    void requireBookPermission(
        Principal principal, String tenantId, String attendeeId);
}
~~~

In a real product, implement `TenantScope` and `BookingAccess` from Spring Security authentication/JWT claims after **verifying signature, issuer, audience, expiry, and permissions**, plus user–attendee ownership if required. A self-supplied `X-Tenant-Id` header never suffices to grant access. The sample API is security-complete only after these auth implementations are built and tested.

## 8. Domain Exceptions and Outcome Semantics

Separate business exceptions from technical faults:

~~~java
import org.springframework.http.HttpStatus;

public final class BookingProblem extends RuntimeException {
    private final HttpStatus status;
    private final String code;

    public BookingProblem(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus status() { return status; }
    public String code() { return code; }
}
~~~

`BookingProblem` captures **deterministic business failures**: missing event, insufficient seats, or mismatched replay payload. These are never reasons for the driver to auto-retry the transaction; repeating identical inputs just repeats the error.

Conversely, connection drops can happen **before, during, or after COMMIT**. When the app receives no response from the server, it **cannot assume the transaction rolled back**. It must reconcile state using the request key.

## 9. Controlled Write Transactions with Neo4j Java Driver

This is the core of the capstone. The sample uses Neo4j Java Driver `executeWrite` (managed transaction) and **two separate queries** so the Event node acquires a write lock before reading seat inventory.

Flow:

1. Check if a Booking already exists for `tenantId + requestKey`; if found, verify payload equality and return it.
2. Acquire a write lock on the Event by updating `lockVersion` on that exact node.
3. **Re-check** `requestKey` after acquiring the lock: another request with the same key may have committed while this one waited.
4. Read Event/Attendee state **under the write lock**; reject if seats are insufficient.
5. Within the same transaction, deduct seats, create the Booking, and create both relationships.
6. If any exception occurs before commit, roll back everything. On commit, return the receipt.

### 9.1. Why Lock Before Reading Seat Counts?

Here is the dangerous concurrent pattern:

~~~text
Event.availableSeats = 1

Request A reads availableSeats = 1
Request B reads availableSeats = 1
A decides 1 seat is available
B decides 1 seat is available
A and B both write back to the same node asynchronously
=> Risk of lost updates or overselling seats
~~~

Simply wrapping queries in a transaction **is not enough** if decisions read stale values before blocking competing writers. Here, before reading to decide, the transaction **writes to the Event node**, causing Neo4j to acquire a write lock on it. Competing transactions targeting the same Event serialize at the lock point, so the subsequent seat read runs while holding write ownership.

This code uses neither APOC lock procedures nor `MERGE` as a substitute for transactions. In complex flows locking **multiple Events**, enforce a consistent lock ordering to avoid deadlocks and test under load.

### 9.2. Looking Up a Receipt by Request Key

~~~java
private static final String FIND_BY_REQUEST = """
    MATCH (b:CapBooking {
      tenantId: $tenantId,
      requestKey: $requestKey
    })
    RETURN b.bookingId AS bookingId,
           b.attendeeId AS attendeeId,
           b.eventId AS eventId,
           b.seats AS seats,
           b.remainingAfter AS remainingAfter,
           b.status AS status
    """;
~~~

Request keys should be unpredictable/high-entropy strings generated by the client, length-bounded, and free of passwords/PII. Each key represents one **specific intent within one tenant**; avoid logging raw header keys into shared log aggregators.

### 9.3. Sample Service: Booking and Reconciliation

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionContext;
import org.neo4j.driver.exceptions.ClientException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public final class BookingService {
    private static final String DATABASE = "neo4j";

    private static final String FIND_BY_REQUEST = """
        MATCH (b:CapBooking {
          tenantId: $tenantId,
          requestKey: $requestKey
        })
        RETURN b.bookingId AS bookingId,
               b.attendeeId AS attendeeId,
               b.eventId AS eventId,
               b.seats AS seats,
               b.remainingAfter AS remainingAfter,
               b.status AS status
        """;

    private final Driver driver;

    public BookingService(Driver driver) {
        this.driver = driver;
    }

    public BookingReceipt reserve(
            String tenantId, String requestKey, BookingInput input) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new BookingProblem(HttpStatus.FORBIDDEN,
                "FORBIDDEN", "Tenant not verified");
        }
        if (requestKey == null || requestKey.isBlank()
                || requestKey.length() > 128) {
            throw new BookingProblem(HttpStatus.BAD_REQUEST,
                "INVALID_REQUEST", "Invalid Idempotency-Key");
        }
        if (input == null || input.eventId() == null
                || input.eventId().isBlank()
                || input.attendeeId() == null
                || input.attendeeId().isBlank()
                || input.seats() < 1 || input.seats() > 5) {
            throw new BookingProblem(HttpStatus.BAD_REQUEST,
                "INVALID_REQUEST", "Invalid payload");
        }

        // Generated outside callback: no external side effect on retries.
        String bookingId = UUID.randomUUID().toString();
        try (Session session = driver.session(
                SessionConfig.forDatabase(DATABASE))) {
            return session.executeWrite(tx ->
                doReserve(tx, tenantId, requestKey, input, bookingId));
        } catch (ClientException ex) {
            // Reconcile ONLY UNIQUE constraint collisions;
            // never swallow unrelated Cypher/schema errors.
            if (!"Neo.ClientError.Schema.ConstraintValidationFailed"
                    .equals(ex.code())) {
                throw ex;
            }
            BookingReceipt found = lookupAfterCollision(
                tenantId, requestKey, input);
            if (found != null) return found;
            throw ex;  // Other collision; do not assume replay.
        }
    }

    private BookingReceipt doReserve(
            TransactionContext tx, String tenantId, String requestKey,
            BookingInput input, String bookingId) {
        Map<String, Object> ids = Map.of(
            "tenantId", tenantId,
            "requestKey", requestKey,
            "eventId", input.eventId(),
            "attendeeId", input.attendeeId()
        );

        // 1. Fast path: did this request commit earlier?
        List<Record> prior = tx.run(FIND_BY_REQUEST, ids).list();
        if (!prior.isEmpty()) {
            return asReceipt(prior.get(0), input, true);
        }

        // 2. Separate write statement acquiring a write lock on Event.
        List<Record> locked = tx.run("""
            MATCH (e:CapEvent {
              tenantId: $tenantId,
              eventId: $eventId
            })
            SET e.lockVersion = coalesce(e.lockVersion, 0) + 1
            RETURN e.eventId AS eventId
            """, ids).list();
        if (locked.isEmpty()) {
            throw new BookingProblem(HttpStatus.NOT_FOUND,
                "ENTITY_NOT_FOUND", "Event not found");
        }

        // 3. Re-read requestKey once serialized on Event.
        prior = tx.run(FIND_BY_REQUEST, ids).list();
        if (!prior.isEmpty()) {
            return asReceipt(prior.get(0), input, true);
        }

        // 4. Read seats and verify Attendee under the write lock.
        List<Record> inventory = tx.run("""
            MATCH (e:CapEvent {
              tenantId: $tenantId,
              eventId: $eventId
            })
            MATCH (a:CapAttendee {
              tenantId: $tenantId,
              attendeeId: $attendeeId
            })
            RETURN e.availableSeats AS availableSeats,
                   e.capacity AS capacity,
                   e.status AS eventStatus
            """, ids).list();
        if (inventory.isEmpty()) {
            throw new BookingProblem(HttpStatus.NOT_FOUND,
                "ENTITY_NOT_FOUND", "Attendee not found");
        }

        Record state = inventory.get(0);
        if (state.get("eventStatus").isNull() ||
                !"OPEN".equals(state.get("eventStatus").asString())) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "EVENT_UNAVAILABLE", "Event is not open");
        }
        if (state.get("availableSeats").isNull()
                || state.get("capacity").isNull()) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "INVALID_INVENTORY", "Seat inventory uninitialized");
        }
        int available = state.get("availableSeats").asInt();
        int capacity = state.get("capacity").asInt();
        if (available < 0 || capacity < 0 || available > capacity) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "INVALID_INVENTORY", "Invalid seat inventory data");
        }
        if (available < input.seats()) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "NO_SEATS", "Not enough seats available");
        }
        int remaining = available - input.seats();

        // 5. Create node/edges and deduct seats in the SAME transaction.
        Map<String, Object> params = new HashMap<>(ids);
        params.put("seats", input.seats());
        params.put("bookingId", bookingId);
        params.put("remainingAfter", remaining);

        Record saved = tx.run("""
            MATCH (a:CapAttendee {
              tenantId: $tenantId,
              attendeeId: $attendeeId
            })
            MATCH (e:CapEvent {
              tenantId: $tenantId,
              eventId: $eventId
            })
            SET e.availableSeats = $remainingAfter
            CREATE (b:CapBooking {
              tenantId: $tenantId,
              bookingId: $bookingId,
              requestKey: $requestKey,
              attendeeId: $attendeeId,
              eventId: $eventId,
              seats: $seats,
              remainingAfter: $remainingAfter,
              status: 'CONFIRMED',
              createdAt: datetime()
            })
            CREATE (a)-[:CAP_HAS_BOOKING]->(b)
            CREATE (b)-[:CAP_FOR_EVENT]->(e)
            RETURN b.bookingId AS bookingId,
                   b.status AS status,
                   b.seats AS seats,
                   b.remainingAfter AS remainingAfter
            """, params).single();

        return new BookingReceipt(
            saved.get("bookingId").asString(),
            saved.get("status").asString(),
            saved.get("seats").asInt(),
            saved.get("remainingAfter").asInt(),
            false
        );
    }

    private BookingReceipt lookupAfterCollision(
            String tenantId, String requestKey, BookingInput input) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(DATABASE))) {
            // Read via WRITE routing in clusters to avoid replica lag
            // right after another transaction wins the unique constraint.
            // This callback is read-only and has no side effects.
            return session.executeWrite(tx -> {
                List<Record> rows = tx.run(
                    FIND_BY_REQUEST,
                    Map.of("tenantId", tenantId, "requestKey", requestKey)
                ).list();
                return rows.isEmpty() ? null :
                    asReceipt(rows.get(0), input, true);
            });
        }
    }

    private static BookingReceipt asReceipt(
            Record row, BookingInput input, boolean replayed) {
        boolean samePayload =
            row.get("attendeeId").asString().equals(input.attendeeId())
            && row.get("eventId").asString().equals(input.eventId())
            && row.get("seats").asInt() == input.seats();
        if (!samePayload) {
            throw new BookingProblem(HttpStatus.CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                "Key already bound to a different payload");
        }
        return new BookingReceipt(
            row.get("bookingId").asString(),
            row.get("status").asString(),
            row.get("seats").asInt(),
            row.get("remainingAfter").asInt(),
            replayed
        );
    }
}
~~~

**Important correctness explanations:**

1. `SET e.lockVersion = ...` is a **real write** on the Event node executed in a dedicated query prior to reading `availableSeats`. It holds a write lock until the transaction ends, preventing concurrent bookings for the same Event from making decisions on stale counts.
2. Re-reading `requestKey` under the lock catches the case where an identical-key request committed while this transaction waited on the **same Event's** lock.
3. Two requests sharing a key yet targeting **different Events** do not contend on the same Event lock. The `(tenantId, requestKey)` uniqueness constraint still prevents committing two bookings with the same key; the collision is reconciled via lookup after the losing transaction rolls back.
4. Any exception thrown before commit (e.g., missing Attendee or `CREATE` constraint failure) **rolls back both `lockVersion` and seat updates**. `lockVersion` is an internal serialization mechanism here, not a business version exposed to clients.
5. `executeWrite` may retry the callback on transient errors. Therefore **never send emails, call external HTTP services, or publish broker messages inside the callback**.
6. `bookingId` is generated outside the callback so it stays stable across driver retries of one invocation; `requestKey` is the durable identity across separate HTTP attempts.
7. The snippet checks a **specific legacy Neo4j constraint error code**. Newer drivers/servers introduce GQLSTATUS codes or altered classifications; in production, test collision detection against your exact versions. **Never treat every `ClientException` as a replay.**
8. Payload equality checks only `attendeeId`, `eventId`, and `seats` because the current API contract has those three fields. When adding ticket tiers, prices, promo codes, or payment methods, expand payload comparison or canonical request hashing so keys cannot be reused with altered semantics.
9. If events are deleted, resized, or closed outside this service, enforce **consistent update protocols on the Event node**. A writer bypassing the locking protocol and invariants can break booking guarantees.

10. Under a race, a replay request might increment `lockVersion` while acquiring the lock before discovering the Booking already exists. It **never deducts extra seats**, yet it still performs a technical write. Under heavy replay traffic, consider a dedicated request-marker node for serialization and verify it with concurrency tests rather than routing every replay through Event locks.
11. In a Neo4j cluster, `executeRead` routed to a replica can lag behind a newly committed transaction unless bookmarks/causal consistency are used. Hence `lookupAfterCollision` uses `executeWrite` to run a **read on the write-routing path**. It performs no mutations; if you switch to replica reads, ensure causal consistency via bookmarks or a supported mechanism.

### 9.4. Two Events Sharing One Request Key

Race scenario:

~~~text
Request A: tenant T, key K, event E1
Request B: tenant T, key K, event E2

Both transactions can acquire locks on E1 and E2 independently.
Constraint (tenantId, requestKey) allows only one Booking(K).
The losing transaction rolls back its seat deduction.
Service reads Booking(K):
  - Same payload => replay succeeds
  - Different payload => 409 IDEMPOTENCY_KEY_REUSED
~~~

That is why **locking the Event alone is insufficient for request-key uniqueness**; you also need the uniqueness constraint and collision reconciliation.

### 9.5. Insufficient Seats and Rollback

If an Event has one seat left and a request asks for two:

~~~text
Transaction:
  LOCK Event (SET lockVersion = lockVersion + 1)
  READ availableSeats = 1
  CHECK seatsRequested = 2 => NO_SEATS
  THROW BookingProblem
  ROLLBACK (including lockVersion)
~~~

No Booking, no relationships, and `availableSeats` remains 1. Verify this behavior with read-back queries in integration tests.

## 10. Spring Boot Controller and HTTP Status Codes

~~~java
import java.security.Principal;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/bookings")
public final class BookingController {
    private final BookingService bookingService;
    private final TenantScope tenantScope;
    private final BookingAccess bookingAccess;

    public BookingController(
            BookingService bookingService, TenantScope tenantScope,
            BookingAccess bookingAccess) {
        this.bookingService = bookingService;
        this.tenantScope = tenantScope;
        this.bookingAccess = bookingAccess;
    }

    @PostMapping
    public ResponseEntity<BookingReceipt> create(
            Principal principal,
            @RequestHeader("Idempotency-Key") String requestKey,
            @Valid @RequestBody BookingInput input) {
        String tenantId = tenantScope.requireTenant(principal);
        bookingAccess.requireBookPermission(
            principal, tenantId, input.attendeeId());
        BookingReceipt result = bookingService.reserve(
            tenantId, requestKey, input);
        return ResponseEntity
            .status(result.replayed() ? HttpStatus.OK : HttpStatus.CREATED)
            .body(result);
    }
}
~~~

Response contract: **201 Created** for a newly created booking, **200 OK** for a valid replay; both return the same `bookingId`. You may add a `Location` header pointing to the resource if an authorized GET endpoint is provided.

The controller invokes both `TenantScope` and `BookingAccess`, never trusting `tenantId` from client-controlled JSON or headers. **Never ship a `TenantScope` stub returning `"tenant-demo"` for all users in a real product**; when running an unauthenticated local demo, mark it strictly for isolated testing and never expose the endpoint publicly.

## 11. Normalizing Exceptions into API Errors

In Spring Boot, use an advice handler so driver internals never leak:

~~~java
import org.neo4j.driver.exceptions.ServiceUnavailableException;
import org.neo4j.driver.exceptions.SessionExpiredException;
import org.neo4j.driver.exceptions.TransientException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record ApiError(String code, String message) {}

@RestControllerAdvice
public final class ApiErrorHandler {
    @ExceptionHandler(BookingProblem.class)
    public ResponseEntity<ApiError> business(BookingProblem ex) {
        return ResponseEntity.status(ex.status())
            .body(new ApiError(ex.code(), ex.getMessage()));
    }

    @ExceptionHandler({
        ServiceUnavailableException.class,
        SessionExpiredException.class,
        TransientException.class
    })
    public ResponseEntity<ApiError> temporary(RuntimeException ex) {
        // After a connection drop, whether COMMIT succeeded may be unknown.
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError("OUTCOME_UNKNOWN",
                "Please retry with the same Idempotency-Key"));
    }
}
~~~

This is a **partial exception-handler example**; add handlers for authentication/authorization, Bean Validation/JSON parse errors, constraint/schema errors, unexpected 500s, and correlation IDs per your framework version. Never return Neo4j `ex.getMessage()` directly to clients. In production, log technical causes to restricted-access logs with request IDs while excluding passwords, PII, and raw query parameters.

**Do not label `OUTCOME_UNKNOWN` for transient errors as meaning the transaction definitely committed.** It is a conservative status: the client **does not know** the outcome and must reconcile via the request key. When the service can prove a pre-commit failure rolled back, returning a more specific code is appropriate.

### 11.1. Retry Matrix

| Error category | Where does retry happen? | Rule |
| --- | --- | --- |
| Invalid input | Nowhere. | Fix payload. |
| Attendee/Event not found | Nowhere. | Verify permissions and IDs. |
| Insufficient seats, Event closed | No immediate retry. | Return 409; client decides next flow if state changes. |
| Idempotency key collision | Reconcile via lookup. | Same payload -> return receipt; different payload -> 409. |
| Transient deadlock / lock contention | Driver may retry `executeWrite`. | Bound retry time, monitor contention; callback must be retry-safe. |
| Connection drop / leader switch | Conditional driver/client retry. | Reuse the **same request key**; never mint a new business intent. |
| Syntax / permission / schema error | Never blind-retry. | Treat as code/config bug and fix root cause. |
| Lost response right at commit | Do not assume rollback. | Look up `requestKey`, or replay same key after reconnecting. |

Transient failures can exhaust the driver's retry budget; the API should return recognizable errors and protect the database using rate limiting, concurrency limits, and client backoff with jitter. Never allow unbounded client retries when the database is overloaded.

## 12. Status Lookup and Reconciling OUTCOME_UNKNOWN

Upon receiving `503 OUTCOME_UNKNOWN`, the client can:

1. Keep the exact same `Idempotency-Key` and payload.
2. Wait/backoff according to policy.
3. Re-submit the exact same request. The service either finds the committed Booking and returns its receipt, or executes the write if the earlier attempt rolled back.
4. If a dedicated lookup endpoint exists, query it to confirm status without issuing a new write.

A lookup query:

~~~cypher
MATCH (b:CapBooking {
  tenantId: $tenantId,
  requestKey: $requestKey
})
RETURN b.bookingId AS bookingId,
       b.attendeeId AS attendeeId,
       b.eventId AS eventId,
       b.seats AS seats,
       b.remainingAfter AS remainingAfter,
       b.status AS status;
~~~

**Authorization:** `$tenantId` must be server-verified, and users must not be able to guess another user's request key to read their bookings. Verify the caller has rights to the corresponding Attendee/Booking; sharing a tenant **may not suffice** when users within a tenant must be isolated.

### 12.1. Suggested GET Endpoint

~~~http
GET /api/v1/bookings/by-request-key/req-demo-001 HTTP/1.1
Authorization: Bearer <valid-token>
~~~

Putting request keys in URL paths can expose them in proxy logs or browser history. If keys are treated as sensitive tokens, use `POST /api/v1/bookings/lookup` with a JSON body or rely solely on idempotent POST retries. In all cases, **a key never substitutes for authorization**.

### 12.2. Do Not Confuse Booking IDs with Idempotency Keys

- `bookingId` is server-generated and identifies the committed record.
- `requestKey` is client-generated and stays stable for **one booking intent**, usable even before `bookingId` is known.
- Whenever a user genuinely wants to reserve additional seats, they must generate a **new** request key; reusing an old key with a new seat count must return 409.

### 12.3. Key Retention Window

Purging Bookings or idempotency metadata too early allows an old replayed request to execute as brand new. Set retention based on real retry windows, data-deletion rules, and Booking lifecycles. If PII must be erased while preserving key protection, retain a minimal marker with an appropriate TTL and test deletion edge cases. **Never store request keys forever without privacy and storage policies.**

## 13. Running the Same Business Flow with Plain Java Driver

Spring Boot is optional for CLI tools or background workers. Neo4j Java Driver supports the flow directly:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public final class BookingCli {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");
        if (uri == null || username == null || password == null) {
            throw new IllegalStateException(
                "Missing connection settings in environment");
        }

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();

            BookingService bookingService = new BookingService(driver);
            BookingReceipt result = bookingService.reserve(
                "tenant-demo",
                "cli-local-request-001",
                new BookingInput("A01", "E01", 1));

            System.out.println("Booking ID: " + result.bookingId());
        }
    }
}
~~~

Hardcoding `tenant-demo` is **strictly for local CLI testing in an isolated environment**; multi-tenant workers must derive tenant and permissions from verified task/identity context. Never print passwords or credentialed URIs, never commit secrets to source code, and never call `verifyConnectivity()` per HTTP request.

**Driver lifecycle:** instantiate one shared Driver/pool for the application's lifetime and close it on shutdown; open a **separate Session per request/task** and never share one Session across threads. In clusters, configure proper routing/encryption URIs and pass the target database via `SessionConfig.forDatabase(...)` instead of relying on an implicit default.

### 13.1. Sync vs. Reactive Choice

The code above uses the **synchronous/blocking Java Driver**, suited for Spring MVC and small-to-medium workloads. If adopting Spring WebFlux / reactive driver, design from the start around reactive streams, transaction boundaries, and backpressure—never invoke these blocking methods on an event-loop thread.

Never mix `CompletableFuture`, blocking sessions, and reactive transactions haphazardly just to boost concurrency. Establish atomicity, error handling, and observability first before changing execution models.

## 14. Spring Data Neo4j and Neo4jClient Alternative

Spring Boot apps using the SDN starter can choose **Spring-managed transactions** instead of driver-managed transactions. In that model:

- `@Node`, `@Relationship`, and `@RelationshipProperties` entities fit standard CRUD and aggregate workflows.
- `Neo4jClient` works well for screen-tailored Cypher or targeted property/edge updates.
- A `@Transactional` service backed by a **properly configured Neo4j transaction manager** groups multiple repository/`Neo4jClient` calls into one transaction.
- Verify how SDN persists aggregates: calling `save()` on a partially hydrated entity may overwrite or prune relationships unexpectedly instead of “just updating one property.”

Simple read/write service example with `Neo4jClient`:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class EventAdminService {
    private final Neo4jClient client;

    public EventAdminService(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public String renameEvent(String tenantId, String eventId,
                              String title) {
        // Authorization/validation must run before invoking this method.
        return client.query("""
                MATCH (e:CapEvent {
                  tenantId: $tenantId,
                  eventId: $eventId
                })
                SET e.title = $title
                RETURN e.eventId AS id
                """)
            .bind(tenantId).to("tenantId")
            .bind(eventId).to("eventId")
            .bind(title).to("title")
            .fetchAs(String.class)
            .mappedBy((typeSystem, row) ->
                row.get("id").asString())
            .one()
            .orElseThrow(() -> new IllegalArgumentException(
                "Event does not exist"));
    }
}
~~~

This illustrates SDN's API/transaction path rather than replacing the full booking service. With `@Transactional`, configure the Neo4j transaction manager explicitly and test rollback on your Spring Boot version. If the app also uses an RDBMS, **name the exact transaction manager** on each service; a plain `@Transactional` never creates a distributed transaction across Neo4j and an RDBMS.

### 14.1. Two Transaction Management Styles — Pick One per Use Case

| Driver-managed | Spring-managed |
| --- | --- |
| `session.executeWrite(tx -> ...)` | `@Transactional` on service with Neo4j transaction manager |
| Driver manages transaction, callback, and transient retries. | Spring opens/commits/rolls back around the method per configuration. |
| Natural for plain Java and explicit Cypher flows. | Convenient when coordinating multiple repositories/Neo4jClient calls in Spring. |
| Does not automatically join an outer Spring `@Transactional`. | A raw Java Driver `Session` does not automatically join Spring's transaction. |
| Callback can retry, so avoid external side effects. | Spring does not make external API calls atomic with Neo4j. |

**Never wrap `executeWrite` inside `@Transactional` assuming the two merge into one transaction.** If migrating the booking flow to SDN, move all steps—“lock Event → read seats → create Booking/edges → deduct seats”—into **one Spring-managed transaction** via Spring-managed repositories/`Neo4jClient` and verify with integration tests.

### 14.2. Role of @Version

SDN supports optimistic locking on entities via `@Version` in suitable models. However:

- `@Version` guards updates to the **same entity** per framework semantics; it does not enforce invariants spanning multiple nodes and relationships automatically.
- Using optimistic concurrency for seat inventory requires managing conflict retries, avoiding stale overwrites, and resolving concurrent winners/losers on the Event.
- When running custom Cypher to update properties directly, never assume entity annotations automatically apply to that query.

This capstone chooses **an upfront write lock on Event** because it clearly demonstrates serialization and transaction boundaries; it is not the only option. You can build an optimistic-concurrency variant or conditional Cypher update with result checks, provided you prove it under concurrency tests.

## 15. Invariant Verification Queries After Every Test

### 15.1. Reconciling Seat Inventory and Confirmed Bookings

~~~cypher
MATCH (e:CapEvent {
  tenantId: $tenantId,
  eventId: $eventId
})
OPTIONAL MATCH
  (b:CapBooking {tenantId: $tenantId})
  -[:CAP_FOR_EVENT]->(e)
WITH e,
     sum(
       CASE
         WHEN b.status = 'CONFIRMED' THEN b.seats
         ELSE 0
       END
     ) AS bookedSeats
RETURN e.capacity AS capacity,
       e.availableSeats AS availableSeats,
       bookedSeats,
       e.availableSeats + bookedSeats = e.capacity
         AS capacityInvariant,
       e.availableSeats >= 0 AS nonNegative;
~~~

Starting from the 3-seat fixture:

| State | availableSeats | bookedSeats | capacityInvariant |
| --- | ---: | ---: | --- |
| Initial | 3 | 0 | true |
| A01 books 2 seats | 1 | 2 | true |
| Replay same key | 1 | 2 | true |
| A02 books 1 more seat | 0 | 3 | true |
| Next 1-seat request rejected | 0 | 3 | true |

This reconciliation query assumes no cancellation/refund workflow yet and no uncoordinated admin edits to `capacity`. When adding cancellations, update `bookedSeats` rules and transaction history accordingly. Never count Booking nodes instead of summing seats when a Booking can reserve multiple seats.

### 15.2. Verify Every Booking Links to Exactly One Attendee and Event

~~~cypher
MATCH (b:CapBooking {tenantId: $tenantId})
OPTIONAL MATCH
  (a:CapAttendee)-[:CAP_HAS_BOOKING]->(b)
WITH b, count(a) AS attendeeLinks,
        collect(DISTINCT a.tenantId) AS attendeeTenants
OPTIONAL MATCH
  (b)-[:CAP_FOR_EVENT]->(e:CapEvent)
WITH b, attendeeLinks, attendeeTenants,
     count(e) AS eventLinks,
     collect(DISTINCT e.tenantId) AS eventTenants
WHERE attendeeLinks <> 1
   OR eventLinks <> 1
   OR b.tenantId NOT IN attendeeTenants
   OR b.tenantId NOT IN eventTenants
RETURN b.bookingId AS bookingId,
       attendeeLinks, eventLinks,
       attendeeTenants, eventTenants
LIMIT 100;
~~~

Expected **0 rows**. This verifies structural cardinality. For complete integrity, also assert `b.attendeeId = a.attendeeId`, `b.eventId = e.eventId`, and absence of parallel edges. Booking node/relationship uniqueness alone does not enforce exactly two incident relationships.

### 15.3. Check for Duplicate Request Keys

~~~cypher
MATCH (b:CapBooking {tenantId: $tenantId})
WITH b.requestKey AS requestKey, count(b) AS total
WHERE total > 1
RETURN requestKey, total
ORDER BY total DESC;
~~~

With `cap_booking_request_key` active and valid keys always supplied, expect 0 rows. If any Booking has a null or missing `requestKey`, standard uniqueness constraints do not catch it; input validation and missing-data tests remain necessary.

## 16. Integration Testing Against a Real Neo4j Instance

**You cannot prove transaction/locking correctness by mocking `Driver`.** Unit tests help verify input validation and error mapping, whereas race conditions, unique constraints, rollbacks, and driver retries must run against a **real Neo4j instance in an isolated environment**.

Use Testcontainers to spin up a disposable Neo4j test instance. Illustrative setup:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class BookingIntegrationTest {
    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword("test-only-password");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username",
            () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
            () -> "test-only-password");
    }

    @Test
    void smokePlaceholder() {
        // Add schema migration/fixture and real assertions in tests below.
        // Never mark PASS just because the container starts.
    }
}
~~~

The image tag and Testcontainers constructor above are illustrative; pick Neo4j images and dependencies **matching your actual stack**. A Docker/container runtime or container-enabled CI runner is required. Without Testcontainers, point tests at a dedicated integration-test database and ensure cleanup never affects unrelated data.

In tests, apply schema constraints before seeding fixtures and wait for constraints/indexes to come online if needed. Under parallel test execution, give each test an isolated fixture or serialized cleanup so **one test never wipes another running test's data**.

`@SpringBootTest` boots the application context; this scaffold requires beans for `TenantScope`, `BookingAccess`, security config, and migrations/fixtures before running as a real integration test. Never treat an empty `smokePlaceholder()` without assertions as proof of business correctness.

### 16.1. Testing Idempotency Against the Real Service

JUnit pseudocode (assuming `service` and fixture are initialized):

~~~java
@Test
void sameRequestKeyDoesNotConsumeSeatsTwice() {
    BookingInput input = new BookingInput("A01", "E01", 2);

    BookingReceipt first = service.reserve(
        "tenant-demo", "same-request-key", input);
    BookingReceipt second = service.reserve(
        "tenant-demo", "same-request-key", input);

    assertEquals(first.bookingId(), second.bookingId());
    assertFalse(first.replayed());
    assertTrue(second.replayed());
    assertEquals(1, readAvailableSeats("tenant-demo", "E01"));
    assertEquals(1, countBookingsByRequestKey(
        "tenant-demo", "same-request-key"));
}
~~~

`readAvailableSeats(...)` and `countBookingsByRequestKey(...)` are test helpers you implement with Cypher. Never mock these queries. Start the test with 3 available seats and no existing Booking for that request key.

### 16.2. Testing Rollback via Post-Update Failure Injection

Isolated test on the test database:

~~~java
@Test
void transactionRollsBackWhenCallbackThrows() {
    assertThrows(IllegalStateException.class, () -> {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (e:CapEvent {
                      tenantId: 'tenant-demo',
                      eventId: 'E01'
                    })
                    SET e.availableSeats = e.availableSeats - 1
                    RETURN e.eventId
                    """).consume();

                // Intentional failure before transaction commit.
                throw new IllegalStateException("INJECTED_FAILURE");
            });
        }
    });
    assertEquals(3, readAvailableSeats("tenant-demo", "E01"));
}
~~~

This demonstrates that mutations in the same transaction roll back when the callback throws. **It is not a production endpoint**—never expose fault injection in a live service. In the full service, add a test-only seam between steps to inject a failure and verify **zero orphaned Bookings or half-created relationships remain**.

### 16.3. Testing Concurrent Bookings

Create an Event with three seats, then launch **eight requests with distinct keys**, each requesting one seat. Expect three transactions to succeed and five to fail with insufficient seats, with `availableSeats` never dropping below `0`.

Test skeleton:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
CountDownLatch start = new CountDownLatch(1);
List<Future<BookingReceipt>> futures = new ArrayList<>();
try {
    for (int i = 0; i < 8; i++) {
        final int n = i;
        futures.add(pool.submit(() -> {
            start.await();
            return service.reserve(
                "tenant-demo",
                "parallel-" + n,
                new BookingInput("A01", "E01", 1));
        }));
    }
    start.countDown();

    int success = 0;
    int noSeats = 0;
    for (Future<BookingReceipt> future : futures) {
        try {
            if ("CONFIRMED".equals(future.get().status())) success++;
        } catch (ExecutionException ex) {
            if (ex.getCause() instanceof BookingProblem problem
                    && "NO_SEATS".equals(problem.code())) {
                noSeats++;
            } else {
                throw ex;
            }
        }
    }
    assertEquals(3, success);
    assertEquals(5, noSeats);
    assertEquals(0, readAvailableSeats("tenant-demo", "E01"));
} finally {
    pool.shutdownNow();
}
~~~

Standard JUnit/concurrency imports are omitted for brevity. Under higher concurrency or tight retry budgets, tests may hit timeouts or lock contention. When that happens, inspect **error types** and retry budgets rather than loosening assertions to “five arbitrary errors.” The paramount invariant is **never overselling and never leaving partial records**.

### 16.4. Testing Unknown Commit Outcomes

Reproducing a connection drop **right after commit and before response delivery** is hard in plain unit tests. In integration/chaos tests, use a programmable network proxy like Toxiproxy or a controlled fault-injection harness to sever responses at different phases.

Test sequence:

1. Send request K with payload P.
2. Cut the connection in the window causing **unknown outcome**; whether commit occurred is uncertain.
3. Restore connectivity and resend **the exact same K and P**.
4. Inspect the graph and verify **at most one Booking(K)** exists, and seats were deducted at most once if booking succeeded.
5. Send K with a different payload Q and assert 409 without mutating state.

Never disrupt a production Neo4j network to run this test. When outcome cannot be determined immediately, return `OUTCOME_UNKNOWN` and instruct the client to check or replay with the same key per policy.

## 17. Capstone Acceptance Test Matrix

| ID | Scenario | Mandatory outcome |
| --- | --- | --- |
| C01 | Event has 3 seats, book 2 seats. | HTTP 201, one CONFIRMED Booking, available=1, both edges correctly directed. |
| C02 | Resend same key/payload as C01. | HTTP 200, identical bookingId, seats not deducted twice. |
| C03 | Same key, different seat count. | HTTP 409 IDEMPOTENCY_KEY_REUSED, graph unchanged. |
| C04 | Same key, different Event. | 409; never two Bookings with the same key. |
| C05 | Event has 1 seat, request asks for 2. | 409 NO_SEATS, seats unchanged. |
| C06 | Event status is CLOSED. | 409, no Booking created. |
| C07 | Event missing in tenant. | 404, no Booking created. |
| C08 | Attendee missing in tenant. | 404 and lockVersion update rolls back. |
| C09 | `seats` = 0, -1, 6, or malformed JSON. | 400 before any Neo4j write. |
| C10 | Missing `Idempotency-Key`. | 400 with zero side effects. |
| C11 | Missing/invalid principal. | 401, no mutation executed. |
| C12 | Principal lacks permission for attendee. | 403, no mutation executed. |
| C13 | Another tenant's Event shares `eventId`. | Neither reads nor writes across tenants. |
| C14 | 8 concurrent requests compete for 3 seats. | At most 3 confirmed, available non-negative, sum equals capacity. |
| C15 | Two concurrent requests share key on same Event. | Exactly one Booking; second becomes replay or reconciles cleanly. |
| C16 | Two concurrent requests share key on different Events. | Constraint enforces single key; losing payload fails and rolls back. |
| C17 | Exception after seat update before commit. | ROLLBACK, no partial Booking or dangling edges. |
| C18 | Driver hits retryable transient error. | Zero external side effects in callback; final outcome accurate. |
| C19 | Response lost right at commit. | Replay with same key reconciles without double-deducting seats. |
| C20 | Request-key uniqueness constraint missing. | Migration gate blocks rollout because idempotency guard is missing. |
| C21 | Neo4j index/constraint not online. | Detected during startup/rollout rather than running silently broken. |
| C22 | Transaction commits, then server restarts. | Committed data survives recovery intact. |
| C23 | User guesses another user's bookingId/requestKey. | Read API enforces object-level authorization; zero leakage. |
| C24 | Internal Cypher/schema error. | Consistent HTTP 500; zero query text/PII leaked in response. |
| C25 | Telemetry/metrics collector drops data. | Alerts on missing telemetry; never treats missing data as zero errors. |
| C26 | Capacity altered erroneously by admin/other job. | Invariant check detects mismatch and halts further bad bookings. |

**Testing objective:** prove invariants hold after every case, not merely HTTP status codes. A request returning 409 that still deducted seats before failing is a **FAIL**.

## 18. Limits of Neo4j Transactions with External Systems

A CONFIRMED Booking often triggers emails, push notifications, or broker events. However, a Neo4j transaction **cannot commit atomically** across email servers or message brokers:

~~~text
Neo4j COMMIT succeeds
           |
           +--> Broker publish fails
           |
           '-- Email sent, yet HTTP response lost
~~~

Sending an email **inside** the `executeWrite` callback means driver retries could send duplicate emails even though only one Booking commits. Therefore:

- Never call external services inside transaction callbacks.
- Use the **outbox pattern**: write a `CapOutboxEvent` in the same Neo4j transaction as the Booking, then have a worker publish after commit.
- Workers use a unique `eventId`, claim/ack/idempotency tracking, and bounded retries.
- Subscribers must handle **at-least-once** delivery and deduplicate by event ID when infrastructure lacks end-to-end exactly-once delivery.

### 18.1. Sample Outbox Node

Extension to the Booking creation Cypher:

~~~cypher
CREATE (evt:CapOutboxEvent {
  tenantId: $tenantId,
  eventId: $outboxEventId,
  eventType: 'BOOKING_CONFIRMED',
  bookingId: $bookingId,
  status: 'PENDING',
  createdAt: datetime()
})
~~~

Insert this strictly **inside the exact same transaction creating the Booking** if outbox is implemented. Add a uniqueness constraint on `(tenantId, eventId)`, claim/retry policies, concurrent worker claiming, and post-publish retention. Never `CREATE CapOutboxEvent` in a separate HTTP call after the Booking committed and treat it as atomic.

**Privacy note:** outbox events should not embed full attendee PII. Store `bookingId`/`eventId` so authorized downstream services fetch needed fields. Never let workers log raw request bodies or credentials.

## 19. Monitoring Errors and Production Performance

Even a transactionally sound app can miss SLOs when thousands of requests hammer a single hot Event. Monitor **both business outcomes and infrastructure resources**:

| Metric | Meaning |
| --- | --- |
| `booking_requests_total` by outcome/code | Success rate, NO_SEATS, invalid, unknown, 5xx. |
| `booking_replayed_total` | Replay volume and idempotency effectiveness. |
| `booking_transaction_duration` p50/p95/p99 | Load and lock/commit wait time. |
| Transient/timeout/leader-change errors | Distinguishes Neo4j faults vs. routing/driver issues. |
| Bookings per Event over time | Detects hot Events/supernodes and lock contention. |
| Remaining seats and invariant status | Guards non-negativity and booked + available = capacity. |
| Neo4j active transactions, lock wait | Concurrency bottlenecks per server metric capabilities. |
| CPU, page cache, disk I/O, tx logs | Separates resource saturation from Cypher/code bugs. |
| Connection pool and retry counts | Detects long wait queues or undersized pools. |
| Backup age and restore drills | Ensures recoverability if schema/upgrades fail. |

Metric names in this table are **illustrative application-defined names**, not guaranteed built-in Prometheus/Neo4j names. Tag by error code and operation name, avoiding high-cardinality labels like raw `userId`, email, `bookingId`, or `requestKey`.

### 19.1. Correlation IDs

Each HTTP request should carry a trace/correlation ID issued by a trusted gateway or verified server-side. Structured logs should show:

~~~text
timestamp | requestId | operation=book | tenantRef=<redacted>
result=CONFIRMED | durationMs | replayed=false
~~~

Never log emails, sensitive user fields, raw query parameters, or tokens. When investigating a specific booking, store audit references in access-controlled storage rather than dumping full identities onto shared dashboards.

### 19.2. Contention on Very Hot Events

Locking on the Event node **intentionally serializes** `availableSeats` updates. That protects invariants yet reduces throughput when thousands of requests per second contend on one Event.

Mitigation options:

- Queue requests per Event in the application tier with bounded queues and fairness.
- Assign explicit seat/slot nodes with individual unique constraints, or partition inventory buckets when domain rules allow.
- Enforce API rate limits, concurrency caps, and timeouts to prevent overload collapse.
- Move to asynchronous booking with a `PENDING` status and status polling/webhooks—**never fake `CONFIRMED` before commit**.
- Trim unnecessary transaction work and extra index writes.

These patterns **change the transactional problem**, requiring fresh invariant and fairness verification. Never treat an un-synchronized seat cache as the final authority unless it updates atomically with Neo4j.

## 20. Tuning Cypher Without Sacrificing Correctness

### 20.1. Leveraging Business-Key Indexes

A booking starts with:

~~~cypher
EXPLAIN
MATCH (e:CapEvent {
  tenantId: $tenantId,
  eventId: $eventId
})
RETURN e.availableSeats AS availableSeats;
~~~

With `cap_event_key`, Neo4j maintains a backing index for the composite key lookup. On tiny fixtures, however, the planner may pick a cheaper scan. **Never judge performance just because an index exists**; inspect `EXPLAIN`/`PROFILE` on representative data and examine `Rows`, `DB Hits`, and p95 latency.

### 20.2. Never Run PROFILE Casually on Mutations

`PROFILE` executes the query. Hence:

~~~cypher
PROFILE
MATCH (e:CapEvent {tenantId: $tenantId, eventId: $eventId})
RETURN e.availableSeats;
~~~

is a safe read-only plan inspection, whereas `PROFILE` on `SET e.availableSeats = ...` **mutates data** when executed. Never run write profiling in production just to inspect DB Hits.

### 20.3. Never Split Transactions to Shave Latency

Atomicity violation:

~~~text
session.run("SET e.availableSeats = ...");  // autocommit
session.run("CREATE Booking ...");           // separate autocommit
~~~

If the second statement fails, seats were deducted with no Booking. Never trade correctness for a few milliseconds. To cut latency, measure:

- Query round-trips inside the transaction.
- Event lock contention, lock wait time, and commit latency.
- Index lookups for Event, Attendee, and Booking keys.
- Page cache hit ratio, disk I/O, and transaction log flushes.
- Unnecessary properties or relationships touched inside the write transaction.

After tuning, re-run the entire concurrency and idempotency test suite. A faster p50 means nothing if p99 degrades severely or overselling becomes possible.

## 21. Security and Multi-Tenant Boundaries

Every entry point must uphold these rules:

1. **Principal:** authenticate via Spring Security; never trust unverified claims.
2. **Tenant:** derive from identity/authorization; if a user accesses multiple tenants, verify rights to the requested tenant explicitly.
3. **Attendee:** verify the caller is authorized to book for that attendee even within the same tenant.
4. **Event:** anchor queries on `tenantId + eventId`; never look up solely by `eventId` when IDs can collide across tenants.
5. **Booking:** look up via `tenantId + requestKey/bookingId` and enforce object-level permissions before returning data.
6. **Schema:** tenant-scoped uniqueness; never let clients supply `tenantId` or `remainingAfter`.
7. **Secrets:** manage Neo4j credentials, JWT signing keys, and TLS certificates via a secrets manager.
8. **Network:** allow only approved apps/jobs to reach Neo4j directly; never expose Bolt publicly without necessity.
9. **Logs:** exclude tokens, passwords, raw request keys, and PII from traces/logs.
10. **Least privilege:** app accounts should lack role admin, database management, backup, or schema DDL privileges.

**Application-layer authorization does not replace database security if other direct connections exist.** Consider fine-grained access control where supported by your edition/version, or separate databases/accounts and network boundaries based on isolation needs.

### 21.1. Testing Cross-Tenant Isolation

Create an event sharing `eventId = E01` in another tenant in the fixture:

~~~cypher
MERGE (e:CapEvent {
  tenantId: 'tenant-other',
  eventId: 'E01'
})
ON CREATE SET
  e.title = 'Other Tenant Event',
  e.capacity = 1,
  e.availableSeats = 1,
  e.status = 'OPEN',
  e.lockVersion = 0;
~~~

Send a `tenant-demo` booking request for `E01`; only the `tenant-demo` Event is updated. Requests from `tenant-other` users must also fail to read `tenant-demo` Bookings or Attendees.

Never write a generic `MATCH (e:CapEvent {eventId:$id})` inside mutating services because it can match multiple nodes across tenants.

## 22. Safe Deployment and Recovery Plan

Passing JUnit tests alone does not make a service production-ready. Before opening the API:

| Step | Activity | Gate |
| --- | --- | --- |
| P1 | Verify Neo4j, Spring Boot, Driver, plugin, and edition versions. | Compatibility confirmed. |
| P2 | Backup and restore drill on representative data. | Recovery path meets RPO/RTO. |
| P3 | Apply schema migrations with authorized credentials. | Four constraints exist and are online. |
| P4 | Audit security, TLS, network, secrets, and attendee permissions. | Zero unauthorized access paths. |
| P5 | Seed/test data in staging environment. | Invariants hold, no duplicate request keys. |
| P6 | Run concurrent and retry load tests. | Zero overselling, p95/p99 within SLO. |
| P7 | Enable canary rollout and observability. | Error metrics, tracing, and app rollback ready. |
| P8 | Ramp traffic incrementally. | No abnormal spike in constraint/`OUTCOME_UNKNOWN` errors. |
| P9 | Post-deploy monitoring and regular backups. | On-call owner and incident schedule active. |

### 22.1. Application Rollback Does Not Roll Back Committed Data

If a new app version goes live, writes Bookings, and is rolled back to an older image, rolling back the binary **does not delete committed Bookings** and should not. Schema/index migrations might also be incompatible with older code. Before deploying, verify:

- Can the prior app version still run against the new schema?
- Are schema migrations backward-compatible (*expand/migrate/contract*)?
- If rollback requires restoring a backup, how are Bookings committed after the backup timestamp handled?
- How will already-published outbox events be reconciled?

Never restore a pre-deployment backup and silently wipe committed transactions without an explicit business decision and replay plan.

### 22.2. Incident Runbook for Seat Discrepancies

If `availableSeats < 0` or `bookedSeats + availableSeats != capacity` is detected:

1. Throttle or pause mutations on the affected Event per approved incident procedure.
2. Record the Event ID, timestamps, preserved transaction/request IDs, and latest backup point.
3. Audit permissions, alternative write paths, rollback/commit logs, and uniqueness constraints.
4. Reconcile CONFIRMED Bookings against seat counts—never adjust `availableSeats` blindly by guesswork.
5. Apply remediation based on the authoritative source of truth and business sign-off.
6. Run concurrency/idempotency regression tests and monitor closely after re-opening.

Never delete relationships or Bookings simply to “make counts match” without confirming whether users already received confirmation.

## 23. Capstone Handover Package

A capstone is graded on **verifiable proof**, not Java line count. Recommended deliverables:

| Artifact | Minimum contents |
| --- | --- |
| Architecture doc | Node/relationship diagram, tenant boundaries, rationale for Booking node. |
| Schema migration | Four constraints, online verification, schema rollback guide. |
| API contract | Request/response schemas, idempotency key, HTTP statuses, and error codes. |
| Java implementation | Controller, domain service, transactions, lookup/reconciliation, DTOs, auth contracts. |
| Configuration | Environment variables for Neo4j/TLS, Security config, test/prod profiles. |
| Tests | Validation, atomic rollback, concurrent booking, retries, unknown outcome, tenant isolation. |
| Evidence | Test execution logs, invariant query outputs, execution plans, p95/p99, sourced metric screenshots. |
| Operations | Backup/restore drills, deploy gates, alerts, Neo4j and inventory incident runbooks. |
| Known limits | No payment integration, no cancellations, hot-Event throughput limits, version constraints. |

This lesson does not generate these project files automatically; build them in your own capstone repository per your team's guidelines.

## 24. Capstone Grading Rubric

| Criterion group | Illustrative weight | Passing requirements |
| --- | ---: | --- |
| Graph modeling and constraints | 15% | Correct node/edge directions, unique keys, and tenant isolation. |
| Cypher and transactions | 25% | Atomic seats + Booking + edges; zero overselling under concurrency. |
| Idempotency and error handling | 20% | Accurate replay, 409 on mismatch, reconciliation path for unknown outcome. |
| Spring Boot / Java design | 15% | Clean layering, parameterized Cypher, proper Driver/session lifecycle. |
| Testing and evidence | 15% | Real DB tests for concurrency/rollback/security plus invariant reports. |
| Operations and security | 10% | Secrets/TLS/auth, logs/metrics, deploy gates, and backup/restore. |

This rubric is **illustrative**, not a rigid universal grading rule.

Certain defects act as **automatic failing conditions** regardless of other scores: overselling seats, partially committed transactions, cross-tenant data leaks, missing authentication/authorization, or duplicate Bookings on retries.

## 25. Extension Exercises

**Exercise 1 — Add a secure GET endpoint.** Implement reading a Booking by `bookingId`, enforcing tenant and Attendee authorization and returning only required fields. Verify other users in the same tenant cannot inspect someone else's Booking.

**Exercise 2 — Booking cancellation.** Design `POST /bookings/{id}/cancel` with its own idempotency key. Lock Event and Booking in a deterministic order, refunding seats **exactly once** when transitioning `CONFIRMED → CANCELLED`. Write a test for two concurrent cancel requests.

**Exercise 3 — Reservation TTL.** Replace instant `CONFIRMED` with a timed `HELD` seat hold. Design the expiration job, payment race handling, timezone consistency, and idempotency so seats neither stay locked forever nor get refunded twice.

**Exercise 4 — Outbox.** Write `CapOutboxEvent` in the same transaction, add a worker publishing `BOOKING_CONFIRMED`, and deduplicate on the subscriber. Simulate a “broker disconnect” right after booking commit; prove the event still delivers without creating a second booking.

**Exercise 5 — Optimistic concurrency.** Compare the current upfront write lock against a `@Version` / check-and-set variant. Measure throughput and lock waits on a hot Event while preserving every invariant.

**Exercise 6 — SDN transactions.** Rewrite the service using `Neo4jClient` and `@Transactional`; contrast Spring's transaction manager with Driver `executeWrite`, and prove rollback when relationship creation fails.

**Exercise 7 — Surviving unknown commit outcomes.** Use a network proxy in tests to sever connections at different points. Document guaranteed-rollback, guaranteed-commit, and unknown-outcome windows. Verify retrying with the same key never inflates booked seats.

**Exercise 8 — Finer multi-tenant authorization.** A user has access to two tenants yet cannot book for every Attendee. Design API and Cypher authorization checks blocking unauthorized proxy bookings and preventing leaks of sensitive booking counts.

**Exercise 9 — Hot Events and load shedding.** Simulate 100 concurrent requests competing for 10 seats. Measure p50/p95/p99, transient errors, and lock waits. Propose queuing, rate limiting, or transaction optimizations without breaking invariants.

**Exercise 10 — Historical state.** Add a `REFUNDED` status and update reconciliation to `capacity = available + held/confirmed seats`. Prove older reporting queries break if they sum all Bookings regardless of status.

**Exercise 11 — Upgrade and recovery.** Back up the test database, upgrade to a newer supported Neo4j version, restore into an isolated environment, and verify graph/constraints/transactions before accepting API writes.

**Exercise 12 — Audit trail.** Record `actorRef`, `requestId`, `action`, and `outcome` in an appropriate audit store without leaking PII or secrets. Distinguish committed successes from rejected attempts and timed-out unknown outcomes.

## 26. Capstone Completion Checklist

1. **Model:** Attendee → Booking → Event properly directed, tenant-scoped, with business keys.
2. **Schema:** four constraints created, online, and protected from accidental index drops.
3. **Security:** verified principal, tenant, and Attendee booking rights; client headers never trusted.
4. **Transactions:** seat deduction, Booking creation, and both relationships share one transaction.
5. **Concurrency:** seat reads occur under an Event write lock; tested with parallel writers and invalid data.
6. **Idempotency:** tenant-unique request keys; same payload returns original receipt; mismatched payload fails.
7. **Unknown outcome:** lost commit response is never assumed rolled back; client retries same key or queries authorized lookup.
8. **Retries:** callback safety respects `executeWrite` retries—zero external side effects inside callbacks.
9. **Error contract:** domain errors map to 400/404/409, connection drops to 503, unexpected faults to 500, without exposing stack traces or Cypher.
10. **Framework discipline:** uses either Java Driver managed transactions or Spring-managed transactions without assuming automatic merging.
11. **Real tests:** Neo4j integration tests cover rollback, races, constraint collisions, tenants, stale/missing data, and restarts.
12. **Reconciliation:** remaining seats stay non-negative; confirmed + available equals capacity per business rules.
13. **Observability:** correlation IDs, categorized errors, p95/p99 latency, lock contention, and missing-telemetry alerts exist.
14. **Resources:** documented plan for hot Events, overload shedding, connection pools, indexes, and transaction logs.
15. **Recovery:** backup/restore rehearsed; migration/rollout gates and rollback caveats evaluated.
16. **Handover:** docs, code, secret-free config, test reports, known limits, and operational owners ready.

**Conclusion:** A Java/Spring Boot application with Neo4j succeeds only when **business invariants survive failures and concurrency**, not merely when one happy-path HTTP request returns 201. Start from the graph schema and uniqueness constraints, build mutations with explicit write locks and atomic transactions, enforce idempotency keys for retries and unknown commits, validate tenant and object-level permissions, and prove everything with real integration tests and Cypher reconciliation. Only once those guarantees are verified is a property-graph API ready for reliable operation.
