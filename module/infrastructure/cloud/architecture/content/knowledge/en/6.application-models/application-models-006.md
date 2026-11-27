# Hexagonal Architecture and Isolating Platform Dependencies

## 1. The problem: business logic tightly coupled to frameworks and cloud

When building a cloud application, a team typically chooses an HTTP framework, database engine, message broker, storage service, authentication tooling, and deployment method. These choices are necessary for the application to run, but **business rules should not depend directly on platform-specific details**.

Imagine a booking confirmation feature with logic like this: receive an HTTP request, read data via an ORM, check availability, write a record to the database, and send an event using a cloud SDK. If everything lives inside one controller or a service packed with framework annotations, swapping the ORM, switching from REST to a queue consumer, or testing business rules becomes difficult. Every technology change risks forcing edits to the booking rules themselves.

**Hexagonal Architecture** (also called **Ports and Adapters**) solves this by placing business logic at the center and letting communication, persistence, and infrastructure mechanisms plug in through **contracts defined by the application**. This is an application architecture model in the CLOUD_ARCHITECTURE module that separates deciding *what the system must do* from *how it communicates with the outside world*.

After this lesson, you will be able to:

- Clearly explain **domain, application use case, port, adapter, composition root**, and source-code dependency direction.
- Distinguish **driving adapters** and **driven adapters**, **inbound ports** and **outbound ports**.
- Design a Java example whose business logic is independent of HTTP, ORM, and cloud SDKs.
- Test the core using in-memory fakes while recognizing scenarios that require real integration testing.
- Apply the model to weigh trade-offs across **reliability, security, scalability, cost, and operations** using Well-Architected thinking.

### Genuine simplification

A small application does not necessarily need every directory, interface, and adapter for every operation. Hexagonal Architecture is **a way to manage dependency directions and boundaries**, not a mandate to create many layers or microservices. Its value comes from more independent changes, easier testing, and the ability to swap infrastructure with controlled impact.

## 2. Overall diagram: core inside, adapters outside

The six sides of the hexagon are merely a **metaphor illustrating multiple connection ports**; the number of ports or adapters is not limited to six.

~~~mermaid
flowchart LR
    Web["HTTP REST / Web UI"] -->|"calls"| In["Inbound port: CreateBooking"]
    Job["CLI / Scheduler / Message consumer"] -->|"calls"| In
    subgraph Hex["Application core (hexagon)"]
        In --> Use["Application use case"]
        Use --> Domain["Domain model / business rules"]
        Use --> OutDB["Outbound port: BookingStore"]
        Use --> OutPay["Outbound port: PaymentGateway"]
    end
    OutDB -->|"implements"| DB["Adapter: JDBC / JPA / managed database"]
    OutPay -->|"implements"| Pay["Adapter: HTTP client / cloud SDK"]
~~~

Note: arrows in the diagram depict **runtime call flow**, so the application can invoke a storage port implemented by an adapter. **Source-code dependency direction** is a separate matter: outer adapters depend on contracts in the core; the core **does not import** frameworks, SDKs, or outer adapter classes.

### 2.1. Components

| Component | Responsibility | Example |
| --- | --- | --- |
| **Domain** | Business rules, concepts, and invariants independent of infrastructure | Booking, Room, valid date range rules |
| **Application use case** | Orchestrates a business task, controls flow, and invokes ports | `CreateBookingService` |
| **Inbound port** (*primary port*) | Contract of tasks external callers may ask the system to execute | `CreateBooking.execute(command)` |
| **Driving adapter** (*primary adapter*) | Receives external signals, transforms input, and invokes an inbound port | REST controller, CLI, message consumer |
| **Outbound port** (*secondary port*) | Contract the core needs from the outside to complete a task | `BookingStore`, `PaymentGateway`, `ObjectStorage` |
| **Driven adapter** (*secondary adapter*) | Realizes an outbound port with concrete technology | PostgreSQL adapter, Kafka publisher, S3 adapter |
| **Composition root** | Wires concrete implementations together at startup | Spring Configuration or manual wiring |

The terms *primary/secondary* do not indicate which component is more important; they describe **which side initiates the interaction**. An HTTP adapter drives calls into a use case, whereas a database adapter is driven by the use case through a port.

### 2.2. Dependency inversion: the core rule

~~~mermaid
flowchart TB
    A["Adapters: REST, Kafka, CLI, JDBC, cloud SDK"] --> P["Application: use cases + ports"]
    P --> D["Domain: business rules"]
~~~

In Java, this is the key mechanism: an interface describing a business need such as `BookingStore.insertIfNoOverlap` is defined in application/core; the PostgreSQL adapter lives in infrastructure and **implements** that interface. `CreateBookingService` receives a `BookingStore` via its constructor. Thus the core knows **what capability it needs**, without knowing about SQL drivers, connection pools, Spring Data, REST endpoints, or cloud regions.

Dependency rules to uphold when organizing modules/repositories:

1. **Domain** does not import application, adapters, frameworks, or cloud SDKs.
2. **Application** depends only on domain, ports, and truly appropriate standard language APIs.
3. **Adapters** may depend on application/domain to convert data and implement ports.
4. **Composition root** knows both interfaces and implementations to wire them at runtime.

Runtime call flow may go **from core out to adapters**, yet this **creates no source-code dependency from core to adapters**. Distinguishing those two kinds of arrows is the key to understanding hexagonal architecture.

## 3. Where to place boundaries?

### 3.1. Domain: what is always true?

The domain holds concepts, **invariants**, rules, and states with business meaning. For example, check-out date must be after check-in date; a confirmed booking must belong to a real room unit; the same room unit cannot have two overlapping confirmed bookings.

Distinguish rules checkable on a single object from rules requiring coordination across multiple records. A **valid date range** can be checked directly inside a `Booking` object; **no two overlapping bookings** requires an atomic write mechanism and cannot be guaranteed by a pre-save check alone.

### 3.2. Application: what workflow executes?

A use case decides the execution order of a task: validate business-meaningful inputs, construct domain objects, invoke persistence ports, interpret results, and return output. The use case does not need to know whether it was invoked by REST or a message consumer.

Place transaction rules, action-level authorization, and idempotency policies in the appropriate layer. For example, the permission rule "whether this user is allowed to book for that account" is an application requirement to enforce; JWT verification details can live in the HTTP adapter. Authorization checks must not vanish simply because another input adapter does not use HTTP.

### 3.3. Adapter: communicating with concrete technology

An adapter translates an inbound/outbound contract into a platform's dialect:

- An HTTP controller turns JSON and headers into a command, mapping outcomes or errors to status codes.
- A JDBC/JPA adapter translates business entities to tables, transactions, SQL, and driver exceptions.
- An object storage SDK adapter translates document-save requests into bucket names, keys, retries, encryption, and provider APIs.
- A message consumer turns events into commands, verifies sender identity if required, and handles ack/nack, retries, and dead-letter policies.

Adapters may contain **technical** logic (SQL pagination, callback signature verification, backoff, serialization), but shared **business** rules should not be scattered across individual adapters.

## 4. Choosing ports in business language

A port is not a mirror of an SDK. An interface named `S3ClientWrapper.putObject` taking S3 types directly as parameters still couples the core to a vendor under a thin wrapper.

Instead of creating an "all-purpose" port with dozens of arbitrary methods, express the capability the use case needs:

| Application Need | Meaningful Port | Details That Belong in the Adapter |
| --- | --- | --- |
| Persist booking if no conflict | `BookingStore.insertIfNoOverlap(booking)` | SQL, locks, transactions, unique/exclusion constraints |
| Fetch payment status | `PaymentGateway.checkStatus(paymentId)` | Endpoint, API key, HTTP timeout, response mapping |
| Archive generated invoice | `InvoiceArchive.save(document)` | Bucket/container, region, multipart upload, SDK |
| Look up exchange rate for pricing | `ExchangeRateProvider.currentRate(pair)` | API vendor, caching, authentication |
| Enqueue notification request | `NotificationRequests.enqueue(message)` | Queue topic, serializer, retries, DLQ |

**A port must describe semantics**, not just method signatures: for example, whether saving a booking returns success or conflict, whether atomicity is required, response deadlines, and which errors the application can handle. Identical Java interfaces do not guarantee identical adapter behavior if semantic contracts are ignored.

For trivial needs, do not create a dedicated port just to wrap every operation. Add a port when it establishes a valuable boundary: separating business rules from technology, aiding testing, or enabling swapping implementations where change is genuinely likely.

## 5. Example: designing a room booking feature in Java

Suppose an application serves room renters. A user picks a room and date range; the system must confirm a booking **only if no overlapping confirmed booking exists**. We will build a small vertical slice to illustrate dependency direction, rather than attempting to model an entire hotel system.

**Minimum requirements for the example:**

- Check-out date is after check-in date; `roomId` is non-blank.
- For the same `roomId`, two half-open date intervals **[checkIn, checkOut)** must not overlap. CheckOut on the 12th and the next booking's CheckIn on the 12th are adjacent, not overlapping.
- Booking persistence success or rejection must be **atomic** under two concurrent requests.
- REST and database are adapters; the use case can run in a unit test with no server or cloud.

The example uses Java 17+ for `record` syntax. Code blocks specify relative paths; each block is a separate Java file in the project.

### 5.1. Directory layout

~~~text
booking/
  domain/
    Booking.java
  application/
    port/in/
      CreateBooking.java
      CreateBookingCommand.java
    port/out/
      BookingStore.java
    service/
      CreateBookingService.java
      RoomUnavailableException.java
  adapters/
    in/http/
      BookingHttpController.java
    out/jdbc/
      PostgresBookingStore.java
  bootstrap/
    BookingConfiguration.java
~~~

Paths are a reference layout. You can use Java modules, Maven modules, or packages depending on team size; what must be preserved is the **actual dependency direction**, not the number of folders.

### 5.2. Domain with zero framework imports

File **domain/Booking.java**:

~~~java
package example.booking.domain;

import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public record Booking(
        UUID id,
        String roomId,
        LocalDate checkIn,
        LocalDate checkOut) {

    public Booking {
        Objects.requireNonNull(id, "id");
        if (roomId == null || roomId.isBlank()) {
            throw new IllegalArgumentException("roomId is required");
        }
        Objects.requireNonNull(checkIn, "checkIn");
        Objects.requireNonNull(checkOut, "checkOut");
        if (!checkOut.isAfter(checkIn)) {
            throw new IllegalArgumentException("checkOut must be after checkIn");
        }
    }
}
~~~

The `Booking` object uses only standard Java APIs; it knows nothing of PostgreSQL, JDBC, HTTP, Spring, or any cloud provider. Validating in the domain ensures every entry point into the system enforces the same date invariant.

### 5.3. Inbound port and command

File **application/port/in/CreateBookingCommand.java**:

~~~java
package example.booking.application.port.in;

import java.time.LocalDate;

public record CreateBookingCommand(
        String roomId,
        LocalDate checkIn,
        LocalDate checkOut) {
}
~~~

File **application/port/in/CreateBooking.java**:

~~~java
package example.booking.application.port.in;

import java.util.UUID;

public interface CreateBooking {
    UUID execute(CreateBookingCommand command);
}
~~~

The use case accepts a plain Java command, not `HttpServletRequest`, `ResponseEntity`, or a web-coupled DTO. The inbound port is a contract callable by a REST controller, a CLI, or an event-driven adapter.

### 5.4. Outbound port and atomic contract

File **application/port/out/BookingStore.java**:

~~~java
package example.booking.application.port.out;

import example.booking.domain.Booking;

public interface BookingStore {
    /**
     * Atomically inserts a confirmed booking if no confirmed
     * booking for the same room overlaps [checkIn, checkOut).
     * Returns false on a booking conflict.
     * Other infrastructure failures must not be reported as conflicts.
     */
    boolean insertIfNoOverlap(Booking booking);
}
~~~

Notice the word **atomically**. If the port merely had `checkAvailable()` followed by `save()`, the use case would be vulnerable to race conditions: two requests both read "available" and both save. The port contract requires the adapter to provide write-time protection, such as an appropriate database constraint or verified transaction/locking.

### 5.5. Use case depending only on ports

File **application/service/RoomUnavailableException.java**:

~~~java
package example.booking.application.service;

public final class RoomUnavailableException extends RuntimeException {
    public RoomUnavailableException() {
        super("Room is not available for the requested dates");
    }
}
~~~

File **application/service/CreateBookingService.java**:

~~~java
package example.booking.application.service;

import example.booking.application.port.in.CreateBooking;
import example.booking.application.port.in.CreateBookingCommand;
import example.booking.application.port.out.BookingStore;
import example.booking.domain.Booking;
import java.util.Objects;
import java.util.UUID;

public final class CreateBookingService implements CreateBooking {
    private final BookingStore store;

    public CreateBookingService(BookingStore store) {
        this.store = Objects.requireNonNull(store);
    }

    @Override
    public UUID execute(CreateBookingCommand command) {
        Objects.requireNonNull(command);
        Booking booking = new Booking(
                UUID.randomUUID(),
                command.roomId(),
                command.checkIn(),
                command.checkOut());

        if (!store.insertIfNoOverlap(booking)) {
            throw new RoomUnavailableException();
        }
        return booking.id();
    }
}
~~~

The use case imports neither JDBC nor Spring. If REST is replaced by a message consumer next week, `CreateBookingService` **needs no modification**. If the team switches Postgres for another store, the core does not need to change **as long as the new adapter upholds the same atomic contract**.

This example focuses on a single business scenario. Production requires adding principal authentication, authorization, booking states, idempotency for retried requests, pricing policies, and hold expiration per approved requirements.

## 6. Driving adapter: accepts HTTP without holding business logic

Suppose the application uses Spring Web at the outer layer. The REST controller translates HTTP input into `CreateBookingCommand` and maps output to a response; it **never checks room availability directly or executes SQL**.

File **adapters/in/http/BookingHttpController.java**:

~~~java
package example.booking.adapters.in.http;

import example.booking.application.port.in.CreateBooking;
import example.booking.application.port.in.CreateBookingCommand;
import example.booking.application.service.RoomUnavailableException;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/bookings")
public final class BookingHttpController {
    private final CreateBooking createBooking;

    public BookingHttpController(CreateBooking createBooking) {
        this.createBooking = createBooking;
    }

    @PostMapping
    public ResponseEntity<CreatedBookingResponse> create(
            @RequestBody CreateBookingRequest request) {
        UUID id = createBooking.execute(new CreateBookingCommand(
                request.roomId(),
                request.checkIn(),
                request.checkOut()));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CreatedBookingResponse(id));
    }

    @ExceptionHandler(RoomUnavailableException.class)
    public ResponseEntity<String> conflict(RoomUnavailableException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body("Room is not available");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid booking request");
    }

    public record CreateBookingRequest(
            String roomId, LocalDate checkIn, LocalDate checkOut) {}

    public record CreatedBookingResponse(UUID bookingId) {}
}
~~~

Annotations like `@RestController`, `@PostMapping`, `@RequestBody`, and the `ResponseEntity` type appear only inside the adapter. Replacing HTTP with gRPC or CLI only requires writing another inbound adapter calling the same `CreateBooking`; business policies are not duplicated.

The snippet illustrates basic mapping. In production, you must handle malformed JSON, unparseable dates, consistent error formats, safe logging, authentication/authorization, rate limiting, and exception mapping per the API contract. Transport-level errors can be handled using shared framework mechanisms without pushing them into the domain.

### When multiple input channels exist

A scheduled job can invoke the use case to process bookings normalized from a file; a message consumer can also invoke the use case upon receiving a valid request from a partner system. Those adapters are responsible for **data conversion and delivery semantics**. If a broker delivers duplicates, the consumer must apply an appropriate idempotency policy; never assume a plain Java use case automatically knows a message was processed before.

## 7. Driven adapter: PostgreSQL enforces anti-double-booking

### 7.1. Schema enforcing the outbound port's contract

With PostgreSQL, an **exclusion constraint** can prevent two `CONFIRMED` bookings from having overlapping date ranges for the same `roomId`. Example:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE bookings (
    id          uuid PRIMARY KEY,
    room_id     text NOT NULL,
    check_in    date NOT NULL,
    check_out   date NOT NULL,
    status      text NOT NULL
                CHECK (status IN ('CONFIRMED', 'CANCELLED')),
    CHECK (check_out > check_in),
    CONSTRAINT no_overlapping_confirmed_bookings
      EXCLUDE USING gist (
        room_id WITH =,
        daterange(check_in, check_out, '[)') WITH &&
      )
      WHERE (status = 'CONFIRMED')
);
~~~

This constraint is specific to PostgreSQL and applies only to **confirmed bookings** in this table. Manage schemas with controlled migrations; DBAs/operations teams must evaluate PostgreSQL version, extensions, indexing, existing data, and performance under real load.

Because the DB enforces conflict checking right inside the write operation, two concurrent transactions cannot both commit `CONFIRMED` rows violating the exclusion constraint. This differs from doing an unprotected `SELECT` to check availability followed by `INSERT`.

### 7.2. JDBC adapter implementing the outbound port

File **adapters/out/jdbc/PostgresBookingStore.java**:

~~~java
package example.booking.adapters.out.jdbc;

import example.booking.application.port.out.BookingStore;
import example.booking.domain.Booking;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class PostgresBookingStore implements BookingStore {
    private final DataSource dataSource;

    public PostgresBookingStore(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public boolean insertIfNoOverlap(Booking booking) {
        String sql = """
            INSERT INTO bookings
                (id, room_id, check_in, check_out, status)
            VALUES (?, ?, ?, ?, 'CONFIRMED')
            """;
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(sql)) {
            statement.setObject(1, booking.id());
            statement.setString(2, booking.roomId());
            statement.setObject(3, booking.checkIn());
            statement.setObject(4, booking.checkOut());
            statement.executeUpdate();
            return true;
        } catch (SQLException ex) {
            // PostgreSQL SQLSTATE 23P01: exclusion_violation
            if ("23P01".equals(ex.getSQLState())) {
                return false;
            }
            throw new IllegalStateException("Cannot persist booking", ex);
        }
    }
}
~~~

Only SQLSTATE **23P01** is interpreted as a booking conflict in this illustrative adapter. Timeouts, connection exhaustion, network errors, schema mismatches, or permission errors must surface as infrastructure failures; **never turn every `SQLException` into "room unavailable."** For more complex transactional scenarios, control commit/rollback and explicit transaction boundaries.

Important semantic notes:

- The SQL example uses the half-open date interval `[checkIn, checkOut)`, avoiding false conflicts on check-out day.
- **Do not assume equivalence across adapters**: switching from PostgreSQL to a key-value database does not mean a simple key-based conditional write will detect overlapping date ranges. The new adapter needs a different atomic strategy, such as per-day keys, transactions, or another tested mechanism.
- A new booking request may be resent after a client loses the response. Generating a fresh UUID per request in the example **does not prevent duplicates across retries**. Production needs an idempotency key bound to the actor and request payload, with outcomes safely persisted and retrieved.
- If payments and event emissions are involved, a successful `INSERT` **does not automatically update external systems atomically**; see the consistency and outbox section below.

### 7.3. Composition root wiring at startup

File **bootstrap/BookingConfiguration.java**:

~~~java
package example.booking.bootstrap;

import example.booking.application.port.in.CreateBooking;
import example.booking.application.port.out.BookingStore;
import example.booking.application.service.CreateBookingService;
import example.booking.adapters.out.jdbc.PostgresBookingStore;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BookingConfiguration {
    @Bean
    BookingStore bookingStore(DataSource dataSource) {
        return new PostgresBookingStore(dataSource);
    }

    @Bean
    CreateBooking createBooking(BookingStore bookingStore) {
        return new CreateBookingService(bookingStore);
    }
}
~~~

The bootstrap layer knows both the core and adapters, so it is permitted to depend on both. The use case needs no annotations to be instantiated; the framework is used at the edge to wire components together. In small applications, **manual constructor wiring** can also serve as a sensible composition root.

## 8. Testing across different boundaries

A major benefit of hexagonal architecture is that use cases **can run without starting a web server, database, or cloud SDK**. However, never conclude from unit tests alone that every real-world adapter contract works properly.

### 8.1. Unit testing the use case with a fake adapter

JUnit 5 example:

~~~java
package example.booking.application.service;

import example.booking.application.port.in.CreateBookingCommand;
import example.booking.application.port.out.BookingStore;
import example.booking.domain.Booking;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CreateBookingServiceTest {
    @Test
    void refusesOverlappingDateRanges() {
        List<Booking> saved = new ArrayList<>();
        BookingStore fakeStore = candidate -> {
            boolean conflict = saved.stream().anyMatch(existing ->
                existing.roomId().equals(candidate.roomId())
                && existing.checkIn().isBefore(candidate.checkOut())
                && candidate.checkIn().isBefore(existing.checkOut())
            );
            if (conflict) return false;
            saved.add(candidate);
            return true;
        };
        var useCase = new CreateBookingService(fakeStore);
        var start = LocalDate.of(2027, 3, 10);
        var end = LocalDate.of(2027, 3, 12);

        useCase.execute(new CreateBookingCommand("R-101", start, end));

        assertThrows(RoomUnavailableException.class,
            () -> useCase.execute(new CreateBookingCommand(
                "R-101", start.plusDays(1), end.plusDays(1))));
        assertEquals(1, saved.size());
    }
}
~~~

The test requires no database and focuses on **use-case behavior** when the port reports a conflict. The fake here runs sequentially and **does not prove concurrency safety**. That verification belongs to integration tests against the real adapter and database.

### 8.2. Contract-based testing map

| Test Layer | Target and Question | Example |
| --- | --- | --- |
| Domain unit test | Do business invariants always hold? | Reject `checkOut` before/equal `checkIn`; accept adjacent intervals |
| Application unit test | Does the use case interpret port outcomes properly? | Throw `RoomUnavailable` when store returns `false` |
| Adapter integration test | Do driver, SQL, constraints, and serialization match the contract? | Two concurrent `INSERT`s with overlapping dates: at most one commits |
| Contract test | Do alternative adapters enforce identical port semantics? | Same failure cases, date boundaries, and status codes on Postgres or alternate store |
| API test | Are HTTP mapping, authentication, and input errors right? | `201` on creation, `409` on conflict, `400` on invalid dates |
| End-to-end / resilience | How does the full chain handle network faults, timeouts, retries, outages? | Payment disconnect, duplicate event delivery, restart recovery |

In practice, run PostgreSQL in a test container or an isolated integration environment to verify constraints and transactions. Even when using emulators for managed queues/object storage, still run selected verification tests against the real service because emulators do not always match production semantics, limits, IAM, or error behavior.

### 8.3. Fakes and mocks must not mask contract bugs

A fake store might save bookings in a `List` and return `true`/`false`, but if the fake always succeeds while the real database experiences transaction conflicts, unit tests create false confidence. Clearly define **contract tests** for each outbound port; distinguish business errors, transient failures, and unrecoverable failures. For adapters with specific consistency or timing requirements, add load and real-fault scenario tests.

## 9. Isolating cloud dependencies with semantic ports

Ports are an effective mechanism for limiting how far cloud SDKs and APIs reach into the core. Suppose an application needs to store an invoice after generating a PDF. The use case cares about **saving, retrieving, and referencing the invoice**, not about AWS S3 buckets, Azure blob containers, or Google Cloud Storage libraries.

### 9.1. Designing a document storage port

A small example:

~~~java
package example.invoice.application.port.out;

public interface InvoiceArchive {
    StoredInvoice save(String invoiceId, byte[] pdfContent);

    record StoredInvoice(String reference, String checksum) {}
}
~~~

Corresponding adapters could be:

- **S3InvoiceArchive** using the AWS SDK, handling bucket, object key, metadata, and API errors itself.
- **GcsInvoiceArchive** using the Google Cloud Storage SDK, translating the same business contract.
- **LocalFileInvoiceArchive** using the filesystem for local development or an appropriate test environment.

The use case still calls `InvoiceArchive.save` and receives a contract-defined reference. If the core stores raw `s3://...` paths and upstream logic parses bucket/key in S3 syntax, isolation is purely cosmetic. Prefer an **opaque reference** or business identifier when the use case does not need to know storage representation.

**Note the example's limitation:** using `byte[]` may not suit very large invoices because the entire payload must load into memory. For large documents, design a port supporting streaming or multipart upload, and explicitly define mid-transfer errors, checksums, and access permissions. Never abstract behind an API that cannot meet real performance constraints.

### 9.2. Platform dependencies cannot be eliminated completely

Ports minimize the impact on business logic when swapping SDKs or backends, but cannot erase meaningful platform differences:

| Platform Difference | Consequence to Evaluate |
| --- | --- |
| Read/write consistency, locking models | Does it satisfy read-after-write, contention handling, and sensitive workflows? |
| Identity policies, IAM, and encryption keys | Who has access, auditing, and secret management; how are permissions migrated? |
| Size limits, throughput, rate limits | Are chunking, streaming, retries, throttling, or backpressure needed? |
| Event features, retention/deletion rules | Does the port need dedicated capabilities or must business flows change? |
| Geographic regions, compliance, egress fees | How does it affect data residency, latency, cost, and DR? |
| SLAs, timeouts, and failure behavior | Adapters must classify errors, retry, and measure SLOs against the real product |

If a feature exists on only one platform and is a core requirement, **do not pretend clouds are identical** by hiding everything under a generic interface. Document the capability, use a specialized port, or accept intentional vendor coupling in an ADR. The goal is **controlling and clarifying dependencies**, not promising effortless cloud migration.

### 9.3. Choosing just enough abstraction

A port is useful only when it expresses business intent independently of mechanism. If every call is a 1:1 pass-through into an SDK, interfaces add class count without reducing coupling. Conversely, if every adapter shares one bloated interface covering uploads, signed URLs, ACLs, cross-region replication, and streaming when the use case only needs to save an invoice, the design creates unnecessary complexity.

Prefer **small interfaces tailored to what a use case actually needs**, paired with error, result, and security contracts. It is not mandatory to wrap every single call or every cloud service in an interface.

## 10. Cloud deployment: source boundaries vs. operational boundaries

Hexagonal Architecture governs **application structure and dependencies**, not the number of processes, containers, VPCs, AZs, or regions. A modular monolith containing domain, application, and adapters can be packaged as one application and run on VMs, containers, PaaS, or serverless when constraints allow.

~~~mermaid
flowchart TB
    Internet["Web / Partner"] --> Gateway["HTTPS Load Balancer / API Gateway"]
    Gateway --> App["One or more application instances: Core + REST adapter + JDBC adapter"]
    App --> DB["Managed PostgreSQL"]
    App --> Storage["Cloud Object Storage"]
    App --> Broker["Managed Queue, if background jobs exist"]
    Broker --> Worker["Worker: Message adapter + shared relevant use cases"]
    App -.-> Telemetry["Centralized logs, metrics, traces"]
    Worker -.-> Telemetry
~~~

The diagram shows that **logical separation does not mandate separate deployments**. Core and adapters can run in the same process to avoid round trips and cost, while background workers run in separate processes when truly needed. Later, a use case can be deployed separately if clear load, ownership, or release-schedule requirements emerge.

When moving from VMs to containers or serverless, the core requires minimal changes if contracts stay intact; however, you must still evaluate cold starts, execution timeouts, database connections, concurrency limits, networking, IAM, and operations. **Ports do not make platform limits disappear.**

## 11. Reliability and consistency when multiple adapters participate

Decoupling dependencies does not automatically make a system consistent or reliable. Calls from a use case to a database, message broker, payment gateway, and object storage are typically **independent transactions**, with no easy global transaction spanning them all. Ports make those boundaries visible, yet the team must still design failure handling.

### 11.1. Why writing to a database and then publishing can lose events

Consider a booking confirmation and notification use case:

~~~text
1. Write booking CONFIRMED to database       -> commits successfully
2. Publish BookingConfirmed to queue         -> times out or process crashes
3. No notification event exists, even though the booking exists
~~~

Reversing the order to publish before writing to the database can emit an event for a booking whose transaction later fails. The hexagonal model does not guarantee atomicity across two separate resources.

### 11.2. Transactional outbox and at-least-once consumption

A common pattern when **events must not be lost after commit**:

~~~mermaid
sequenceDiagram
    participant A as Use case
    participant DB as Database
    participant R as Outbox relay
    participant Q as Queue
    participant C as Consumer
    A->>DB: Transaction: write booking + outbox event
    DB-->>A: Commit
    R->>DB: Read unpublished outbox rows
    R->>Q: Publish BookingConfirmed
    Q-->>R: Ack
    R->>DB: Mark delivered
    Q->>C: Deliver event
    C->>C: Idempotent handling
~~~

An outbox closes the gap between DB and broker by writing both the booking and the outbox row in **the same DB transaction**. However, the relay may publish successfully and crash before marking the row delivered; therefore, events **may be delivered more than once**. Consumers must handle them idempotently, such as recording processed `eventId`s or using idempotent update operations.

To keep port semantics clear, you can design an outbound port like `BookingCommitPort.confirmAndRecordEvent` with an atomicity requirement; the database adapter writes both booking and outbox in one transaction. Another option is managing transactions in an appropriate coordinating adapter. Never create two separate ports and assume a Spring transaction automatically covers an external queue.

### 11.3. Error classification and contract-driven retries

| Scenario | What the Core Needs to Know | What the Adapter Must Handle |
| --- | --- | --- |
| Room already has an overlapping booking | Business conflict; return rejection | Detect SQL constraint or equivalent atomic rule |
| Temporary database disconnect | Outcome may or may not have committed; apply proper retry policy | Classify timeout/connection errors, observability, avoid misreporting as conflict |
| Payment gateway timeout | Transaction state is **unknown**; reconciliation needed | Manage deadlines, idempotency keys, status queries when supported |
| Queue delivers same message twice | Must not produce duplicate side effects | Deduplication/idempotency, ack/nack, proper DLQ |
| Object storage unreachable | Use case enters error or deferred state per requirements | Bounded retries, alerts, security rules, and error codes |

**Blind retries can break correctness.** Do not retry every error, and never automatically repeat a payment without knowing whether the previous attempt was accepted. Error classification must reflect business behavior and vendor terms.

## 12. Allocating responsibility for security, observability, and performance

### 12.1. Security crosses multiple boundaries

Hexagonal architecture does not remove security responsibilities from the core. Distinguish:

- **Edge authentication**: HTTP adapter or gateway verifies JWT/session; message adapter checks producer identity via broker mechanisms.
- **Business authorization**: application decides which principal may perform an action on which resource. Another adapter calling the same use case must not accidentally bypass this check.
- **System permissions**: adapters receive least-privilege IAM roles, secrets, and network rules to access only their target resources.
- **Data protection**: adapters encrypt in transit, log safely, and handle sensitive payloads; domain/application define data classifications and business-meaningful access/retention rules.

In multi-tenant systems, a command typically needs an authenticated actor/tenant context from the edge. **Never trust an arbitrary client-supplied `tenantId`** unless it is bound to verified identity and access rights. You can define an `ActorContext` type in the application layer independent of framework JWT claim types.

### 12.2. Cross-layer observability without leaking SDKs

| Need | Sensible Implementation |
| --- | --- |
| Tracing a booking from REST to DB/broker | Propagate correlation/trace IDs through adapters; instrument edges and I/O points |
| Measuring error rates and latency | Metrics per use case and port; dashboards paired with SLIs/SLOs |
| Investigating infrastructure errors | Detailed driver/SDK logs inside adapters, categorized and linked to request IDs |
| Preventing sensitive data leaks | Redaction, strict log field control; never log tokens, passwords, or card numbers |
| Analyzing load | Measure actual latency and throughput per adapter; inspect pools, retries, caches, network hops |

Typically instrumentation relies on framework hooks or agents at adapters/edges. The core may emit business events or invoke a telemetry port **when genuinely justified**; avoid forcing domain models to import OpenTelemetry SDKs or cloud logging SDKs merely for technical logging.

### 12.3. Performance and cost of boundaries

An in-process Java interface call has vastly different overhead from a remote HTTP service call. **Hexagonal does not require every adapter to be a separate service**, so do not blame network latency on the pattern itself.

When using remote adapters, account for **timeouts, retry budgets, connection pools, rate limits, serialization, payload sizes, and failure domains**. Turning an internal port into a microservice call usually changes error contracts and response times; never treat it as merely swapping an implementation class.

For instance, an object storage adapter can use streaming instead of `byte[]` for large documents. A query port needs pagination to avoid loading entire tables into RAM; pagination and consistency requirements must be defined by business behavior rather than merely wrapping a DB query method.

## 13. Comparing Hexagonal with Layered, Clean, Onion, and microservices

These concepts relate closely but are not synonymous:

| Model | Focus | Relationship to Hexagonal |
| --- | --- | --- |
| **Layered Architecture** | Splits into presentation, business, data access | Works very well if dependency direction is clear; breaks down when business logic depends on DAO/framework implementations |
| **Hexagonal / Ports and Adapters** | Isolates core using inbound/outbound contracts and adapters | Emphasizes keeping business logic independent of delivery channels, persistence, and platforms |
| **Onion Architecture** | Domain core at center, dependencies pointing inward | Shares the inward dependency rule, typically layered as domain/application/infrastructure |
| **Clean Architecture** | Entities, use cases, interface adapters, frameworks/drivers | Shares many principles, differing in terminology and boundary phrasing |
| **DDD** (*Domain-Driven Design*) | Business models, bounded contexts, ubiquitous language | Helps identify domain models and port boundaries; does not mandate every tactical pattern |
| **Microservices** | Independent deployment and operational units along business boundaries | Each microservice can use hexagonal; a monolith can use it too |

There is no need to debate whether a diagram is "pure hexagonal" or "pure clean." What matters is **where business rules live, which way dependencies point, and what must change when an external platform changes**.

### When is hexagonal architecture worth using?

It fits when an application has substantial business rules, multiple input channels, external integrations, expected DB or cloud provider changes, requirements to test use cases decoupled from infrastructure, or a need to curb framework coupling.

For a very simple CRUD endpoint that merely passes data through with no business policies and a short lifespan, heavy abstractions may not pay off. You can start with a minimal layout and extract ports when concrete dependencies or testing needs emerge. **Do not create interfaces for every class out of habit.**

## 14. Step-by-step migration from a framework-centric application

Suppose a legacy system has controllers directly calling ORM repositories, cloud SDKs, and performing business checks. A safe migration should proceed **one business slice at a time**:

1. **Pick a high-value use case**, such as creating a booking; map current call paths and error cases. Add tests covering core behavior before changing structure.
2. **Identify business rules** currently living in controllers, repositories, or stored procedures; clarify invariants and real transaction semantics.
3. **Create a command and inbound port** for the business action; keep the HTTP layer thin, doing only request/response translation.
4. **Extract rules into domain/application**. Define outbound ports based on the use case's actual needs rather than copying entire ORM interfaces.
5. **Wrap existing data access in an adapter**. Ensure the new adapter preserves the atomicity, error behavior, and transactions of the legacy code.
6. **Move configuration and wiring** to the composition root; verify the core no longer imports framework types.
7. **Measure and verify**: run unit tests on the use case, integration tests on adapters, API flow tests, load tests, and compare logs/metrics.
8. **Delete old call paths once confirmed** no consumers still depend on them; update diagrams, runbooks, permissions, and ADRs.

You do not need to convert the entire repository to the new structure in one go. During transition, adapters can call legacy repositories underneath; what matters is progressively removing dependencies from application logic onto concrete repositories.

### Example impact of change

| Change | If Business Logic Is Coupled to Tech | With Proper Ports/Adapters |
| --- | --- | --- |
| REST switches to gRPC | Processing rules must be duplicated in new endpoints | Write a gRPC driving adapter calling the inbound port |
| PostgreSQL driver / ORM changes | Domain services coupled to entities/annotations break | Replace JDBC/JPA adapter, keeping contracts and integration tests |
| S3 switches to another storage | Every use case touching buckets/keys and SDK must change | Swap `InvoiceArchive` adapter if the new backend meets the contract |
| Adding a scheduled job | Must reuse controllers or copy business code | Write a CLI/job adapter calling the use case |
| Changing authentication method | Business checks tied to JWT types must change | Map auth claims to `ActorContext` at the edge; keep business authorization intact |
| Changing booking strategy | Rules and persistence must be re-evaluated | Update domain/use cases and port contracts when semantics change |

The last row highlights an important limit: **Hexagonal isolates mechanism changes better than business-rule changes**. If the business switches from daily to hourly bookings or adds expiring holds, domain, ports, and data models will naturally need updates.

## 15. Trade-offs with Well-Architected thinking

Hexagonal Architecture is **not** an automatic certification that an application is reliable, secure, or cheap. It provides a structure that makes it easier for teams to test, evolve, and take ownership of those quality attributes.

| Pillar / Goal | Potential Benefits | What Must Still Be Done Proactively |
| --- | --- | --- |
| **Operational Excellence** | Core easily testable; adapters have clear owners; safer independent changes | CI/CD, logs/metrics/traces, runbooks, config governance, version management |
| **Security** | Separates business rules from IAM/encryption mechanics; fewer SDK imports in core | Enforce authorization in the right layer, least privilege, sensitive data controls, cross-adapter policy tests |
| **Reliability** | Port contracts clarify error/retry semantics; easy fault simulation in tests | Transactions, outbox/idempotency, backups, DR, drills, and SLOs |
| **Performance Efficiency** | Bottleneck adapters can be swapped; backends chosen by measurement | Preserve semantics, run real load tests, tune pools, timeouts, and caching |
| **Cost Optimization** | Lower migration cost when technologies change; faster test feedback | Weigh interface/adapter overhead against operational effort and cloud budget |
| **Sustainability** | Storage/compute backends can be swapped to trim wasted resources | Measure actual efficiency; avoid redundant layers and duplicate processing |

The architectural checkpoint is: **which cloud requirement does a decision satisfy, what contract does the port specify, can the adapter prove that contract, and what is the long-term operational cost?**

## 16. Common mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Treating the hexagon as a six-service diagram | Unjustified deployment splitting | Treat the hexagon as an application boundary metaphor; choose process count from requirements |
| Placing interfaces in infrastructure so core imports SDK DTOs | Dependency direction remains inverted | Move interfaces into application; use types fitting business language |
| Ports mirroring every ORM/cloud SDK method | Swapping APIs does not reduce coupling | Design around business operations and use-case semantics |
| Domain objects carrying web, ORM, or cloud annotations | Domain is hard to test and swap infrastructure | Use mappers in adapters; allow libraries in core only via conscious trade-off |
| Creating one interface and pass-through class per method | Extra boilerplate with no meaningful boundary | Prioritize ports at real change or testing boundaries |
| Putting all logic into adapters | REST and consumers enforce inconsistent rules | Move shared policies into domain/application |
| Two-step check availability then `INSERT` | Race conditions, duplicate bookings | Atomic write contracts and verified DB constraints/transactions |
| Treating mocks/fakes as proof of database compatibility | Misses concurrency, driver, and schema bugs | Contract and integration tests on real backends |
| Assuming a DB transaction makes a queue atomic too | Lost or duplicated events | Transactional outbox where appropriate and idempotent consumers |
| Swapping clouds just by swapping implementations | Misses IAM, consistency, limits, egress costs | Evaluate capabilities and SLAs; record exceptions/ADRs as needed |
| Leaking JWTs, HTTP statuses, or SDK exceptions into domain | Business logic cannot be reused across channels | Translate at adapters; keep application semantics independent |
| Pushing every concern through ports for "architectural purity" | Loses simple observability, adds ceremony | Instrument at edges; add ports only when meaningful |

## 17. Practice exercise

A Java e-commerce platform stores invoices in one cloud provider's object storage, processes payments via a partner API, and persists orders in PostgreSQL. Currently, `OrderController` calls all three SDKs directly while decrementing inventory and transitioning order status. The business wants to add a Kafka consumer to ingest partner orders and is considering switching invoice storage services.

Complete the following:

1. Draw **one hexagonal diagram** showing domain, application use cases, inbound/outbound ports, and HTTP, Kafka, PostgreSQL, payment, and invoice archive adapters.
2. Select **at least two business invariants** to protect in domain/application, and one invariant requiring an atomic database mechanism.
3. Design method signatures for `CreateOrder` (inbound), `OrderStore`, `PaymentGateway`, and `InvoiceArchive` (outbound) without using DTOs or SDK types.
4. Identify who is responsible for JSON/Kafka message mapping, payment callback verification, IAM role selection, timeouts/retries, and duplicate-event protection.
5. Write one unit test using a fake `OrderStore` and one integration test capable of catching an inventory/order race condition.
6. Compare **two options**: keeping the current controller and adding a Kafka branch, vs. extracting use cases/ports and writing a Kafka adapter. Evaluate cost of change, testing, reliability, and migration risks.
7. Write a **short ADR** on whether to introduce an `InvoiceArchive` port before switching object storage; specify the contract, assumptions, triggers to revisit, and evaluation metrics.

### Grading hints

A strong solution clearly shows **dependency arrows pointing inward to the core**, inbound ports callable from both HTTP and Kafka, outbound adapters implementing contracts with realistic semantics, and a core unaware of SDK details. The write-up must explain which operations need database atomicity, which can become asynchronous, and how to handle uncertain results from payment or queues.

A diagram full of boxes is not enough: explain *why* boundaries exist, who owns them, how they are tested, and their impact on Well-Architected pillars.

## 18. Checklist for evaluating a hexagonal design

Before accepting the design, verify:

- [ ] **Domain** expresses business rules and imports no frameworks, transports, or cloud SDKs.
- [ ] **Application use cases** have clear inputs/outputs, manage business flows, and depend only on necessary ports.
- [ ] **Inbound adapters** handle protocol conversion and input validation without duplicating business rules.
- [ ] **Outbound ports** specify semantics for transactions, consistency, errors, timeouts, and outcomes rather than mirroring vendor APIs.
- [ ] **Outbound adapters** implement contracts with concrete technology and proper error mapping.
- [ ] **Composition root** wires implementations and manages environment-specific configuration.
- [ ] **Concurrency/idempotency** is verified against real state stores; fake tests never substitute for integration tests.
- [ ] **Security** enforces identity, resource authorization, and cloud IAM; all adapters obey mandatory policies.
- [ ] **Operations** cover telemetry, safe logging, alerts, backups, and DR per approved requirements.
- [ ] **Every abstraction has a reason** tied to testing, technology change, or boundary enforcement; avoid redundant interfaces and mappers.
- [ ] **ADRs** record choices, trade-offs, and triggers to revisit when requirements or platforms change.

**Key takeaway:** Hexagonal Architecture keeps **business policies** stable amid changes in **communication mechanisms and infrastructure**. Its strength lies in port contracts designed around real semantics, dependencies pointing inward to the core, and independently testable adapters. On the cloud, combine this model with explicit requirements for consistency, security, performance, operations, and cost to build architectures that are flexible yet reliable.
