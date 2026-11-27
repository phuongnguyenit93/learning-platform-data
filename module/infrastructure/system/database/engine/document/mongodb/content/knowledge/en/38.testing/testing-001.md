# Splitting Unit, Integration, and End-to-End Tests for MongoDB Applications

## 1. Why Does a MongoDB Project Need Multiple Testing Layers?

Suppose a home rental system uses **Spring Boot, Spring Data MongoDB, and a MongoDB replica set**. A tenant submits a house-viewing request; the backend creates a booking, saves it to a collection, allows the host to confirm it, and returns the status over a REST API.

One day, a new deployment surfaces the following bugs:

- The service re-confirms a booking that was already cancelled.
- The Java property **tenantId** was renamed to the BSON field **tenant_id**, but an old query still uses the wrong field name.
- A unique index was not created in the staging environment, allowing a request to be written twice.
- The HTTP controller returns **200 OK** instead of **201 Created**.
- The API allows a user belonging to tenant A to read a booking belonging to tenant B.
- The booking creation flow works on the developer's machine but fails when connecting to real MongoDB due to a BSON type or transaction issue.

There is **no single test type** that is fast, completely isolated, and proves all of the above at once.

We need to separate responsibilities:

~~~text
                     User / client
                         |
                   HTTP REST API
                         |
                    Controller
                         |
                   BookingService
                         |
                  BookingRepository
                         |
                Spring Data mapping
                         |
                  MongoDB driver
                         |
                      MongoDB

UNIT TEST:
  Business rules in BookingService, mocked repository

INTEGRATION TEST:
  Repository + mapper + driver + real MongoDB

END-TO-END TEST:
  Client sends HTTP -> Controller -> Service -> Repository
    -> real MongoDB -> HTTP response
~~~

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **unit testing**, **integration testing**, and **end-to-end (E2E) testing** by the **boundaries of the system actually executed**.
2. Decide which layer should verify a requirement to **avoid unnecessary duplication and slowness**.
3. Use **JUnit 5 + Mockito** to test a MongoDB service without needing a database.
4. Use **@DataMongoTest + Testcontainers** to verify Spring Data mapping, repository queries, and actual BSON.
5. Use **@WebMvcTest/MockMvc** within its proper scope — without confusing a controller slice test with full E2E.
6. Use **@SpringBootTest(webEnvironment = RANDOM_PORT)** and an HTTP client to test an API flow against real MongoDB.
7. Test MongoDB-specific behaviors: **_id, @Field, embedded documents, unique indexes, optimistic locking, transactions, write concern, TTL, and Change Streams**.
8. Create reproducible fixtures that are independent across tests and do not affect production data.
9. Design negative tests for validation, tenant isolation, concurrency, and database failures.
10. Build a CI strategy, choose test counts at each layer, manage flaky tests, and record appropriate evidence.

> **Scope:** This lesson belongs to **Database Engine Document MongoDB → Testing**. Examples use **Java 17+, Spring Boot 3.4+ compatible with Spring Data MongoDB, JUnit Jupiter, Mockito, and Testcontainers**. Some annotations/versions may change according to the BOM and newer releases; check the corresponding API before use. No tests or Gradle runs were executed while writing this documentation. All example data/collections are solely for a **MongoDB test container or isolated lab database**, never production.

## 2. How Do the Three Testing Layers Differ?

### 2.1. Unit Test

A **unit test** verifies a small unit of logic, usually a class or a group of functions, with external dependencies replaced by test doubles when needed.

Example:

> “When a booking is already CANCELLED, a confirm call must be rejected and repository.save must not be executed.”

No MongoDB server is needed to verify this business rule.

~~~text
JUnit -> BookingService -> Mockito BookingRepository
                      |
                  No MongoDB
~~~

Characteristics:

- Fast execution, minimal environment dependencies.
- Failures are usually easy to isolate.
- Suitable for testing state transitions, validation, pure Java mapping, and pricing calculations.
- Does not prove that MongoDB queries are correct or that BSON is stored with the expected schema.

### 2.2. Integration Test

An **integration test** verifies the collaboration between real components, for example:

> “When BookingRepository saves a BookingDocument, tenantId must be written as tenant_id, guest.fullName as guest.full_name, and the findByIdAndTenantId query must return the right booking.”

To prove this, **Spring Data mapper + MongoDB driver + a real MongoDB server** are required.

~~~text
JUnit -> MongoRepository -> MappingMongoConverter
       -> MongoDB Java Driver -> Testcontainers MongoDB
~~~

Characteristics:

- Slower than unit tests; usually requires a Docker runtime or managed test database.
- Verifies BSON, indexes, queries, server constraints, and data access scenarios.
- Does not by itself prove that HTTP routing, JSON serialization, or the frontend work.

### 2.3. End-to-End Test

**End-to-end** tests a business flow traversing all required components from a defined starting point to a defined ending point.

Example:

> “A client sends POST /api/bookings and gets 201 Created, then GET with the same tenant returns the booking, while GET with a different tenant returns no data.”

~~~text
HTTP client
     |
     v
Spring Boot HTTP server (real port)
     |
     v
Controller -> Service -> Repository -> real MongoDB
     |
     v
HTTP status + response JSON + persisted state
~~~

Without a real browser, this can be a **service-level E2E**. It fully proves the service flow, yet **does not yet prove the UI, ingress, SSO, or all external systems**. You must clearly state the **start/end boundaries** when calling a test E2E.

### 2.4. Comparison Table

| Criterion | Unit | Integration | End-to-end |
| --- | --- | --- | --- |
| Subject | Isolated logic | Boundaries between components | User/business flow |
| Real MongoDB | Not needed | Usually yes | Yes if the flow depends on DB |
| Real HTTP server | No | Optional | Usually yes for service E2E |
| Fake dependencies | Often uses Mockito | Limited to the exact boundary | Minimized; external systems may still be stubbed with control |
| Speed | Fast | Medium | Slower |
| Fault isolation | High | Medium | Lower across many components |
| Catches wrong BSON @Field | Unreliable if only mocked | Yes | Can detect indirectly |
| Catches wrong HTTP status | No if only testing service | No if only testing repository | Yes |
| Catches business rule bugs | Yes | Possibly | Possibly |
| Flakiness risk | Usually low | Depends on DB environment | Higher across multiple services |

**Classify by what actually ran**, not by method names like testIntegration() or directory names.

## 3. Not Every Test Fits Strictly Into Those Three Labels

In practice, other terms also appear:

- **Component test:** tests a component with some real dependencies and some mocked/stubbed ones.
- **Slice test:** Spring Boot loads only part of the application context, such as **@WebMvcTest** or **@DataMongoTest**.
- **Contract test:** verifies the request/response/schema contract between two services.
- **System test:** tests a larger integrated system, potentially spanning multiple services.
- **Smoke test:** a few basic journeys after deployment.
- **Performance/load test:** measures throughput/latency under load.
- **Resilience/failover test:** verifies behavior under infrastructure faults.

A **@WebMvcTest** using MockMvc and a mocked BookingService is a **controller slice/component test**, not full E2E, even though it uses HTTP methods and JSON.

A **@DataMongoTest** running against real MongoDB is a **persistence integration test**, even though it never calls a REST controller.

### 3.1. The Test Pyramid Is a Guideline, Not a Percentage Law

~~~text
                   /\
                  /  \
                 / E2E\        Few, selective critical journeys
                /------\
               /  Integ \      Data and service boundaries
              /----------\
             /    Unit    \    Many small, fast logic cases
            /______________\
~~~

We generally want **many fast unit tests**, **well-placed integration tests**, and **fewer but high-value E2E tests**.

There is no mandatory 70/20/10 ratio for every project. A service that is mostly persistence mapping may need more integration tests; an I/O-light business engine may need mostly unit tests.

### 3.2. When to Place a Check at a Lower Layer?

Pragmatic rule:

> If a bug can be reliably proven at a lower layer, do not repeat the same ten data combinations in E2E.

Example for booking validation:

- Unit test 12 cases of title/tenant/request input.
- Integration test 2 cases requiring real MongoDB.
- E2E test 1–2 representative journeys to prove wiring and HTTP contract.

However, never push a test down to a mock layer if **the behavior to be proven belongs to the database**.

## 4. Split by Question, Not by Class Name

A business requirement should be broken down into independent conditions.

| Question to answer | Appropriate layer | Reason |
| --- | --- | --- |
| Can a CANCELLED booking be confirmed? | Unit | Pure Java state transition |
| Are required tenantId/ID checked? | Unit | Service validation |
| Does the service pass the right object to repository.save? | Unit | Interaction with dependency |
| Does Java tenantId map to BSON tenant_id properly? | Integration | Requires MappingMongoConverter |
| Does a repository query on a nested field return right data? | Integration | Requires server query semantics |
| Does MongoDB reject an actual duplicate key? | Integration | Server-enforced constraint |
| Does a transaction roll back when the second write fails? | Integration | Requires replica set and transaction |
| Does REST POST return 201 and proper JSON? | Controller slice or E2E | Slice to check controller; E2E to confirm full flow |
| Does an HTTP request create the expected document in MongoDB? | E2E | Cross-layer verification |
| Does another tenant receive 404/403 per policy? | Unit + E2E | Policy logic and API enforcement |
| Does 500 req/s still meet p99? | Performance | Not a goal of unit tests |
| Does the driver reconnect on secondary stepdown? | Resilience integration/system | Requires valid real/simulated topology |

If you only write “test BookingRepository” without a specific question, it is hard to know whether the test should use Mockito or Testcontainers.

## 5. Running Example Model Throughout the Lesson

### 5.1. Business Flow

We design a simple **Booking API**:

1. A user requests to create a booking for a listing.
2. The booking is saved with status **REQUESTED**.
3. An authorized user in the tenant calls confirm, transitioning the status to **CONFIRMED**.
4. A **CANCELLED** booking cannot be confirmed.
5. Every read/modify operation must be scoped by **tenantId**.

This is a small model to clarify test boundaries. A real system also needs authentication, actor-level permissions, listing ownership, availability, idempotency, auditing, and concurrency controls.

### 5.2. BSON Contract

Collection **booking_requests_411**:

~~~javascript
{
  _id: "bk-411-example",
  tenant_id: "tenant-001",
  listing_id: "listing-100",
  guest: {
    full_name: "Lan"
  },
  status: "REQUESTED",
  created_at: ISODate("2026-01-15T09:00:00Z"),
  _class: "com.example.mongo411.domain.BookingDocument"
}
~~~

**_class** may be added by default by Spring Data; the exact format depends on the converter/type mapper. Tests should not rely on a single class name if the application intentionally uses aliases or disables type metadata.

### 5.3. Lesson Boundaries

~~~text
HTTP client
   |
BookingController
   |
BookingService
   |             Clock
BookingRepository (Spring Data)
   |
MongoDB
~~~

**Clock** is injected so unit tests can control time. **BookingRepository** is mocked in unit tests and real with Testcontainers in integration and E2E tests.

### 5.4. Package Conventions

~~~text
src/main/java/com/example/mongo411/
  Mongo411Application.java
  domain/
    BookingStatus.java
    GuestInfo.java
    BookingDocument.java
  repository/
    BookingRepository.java
  service/
    BookingService.java
  web/
    BookingController.java
    CreateBookingRequest.java
    BookingResponse.java
    BookingErrorHandler.java

src/test/java/com/example/mongo411/
  service/BookingServiceUnitTest.java
  repository/BookingRepositoryIntegrationTest.java
  web/BookingControllerSliceTest.java
  BookingHttpE2ETest.java
~~~

Each Java snippet has its own file name; if you create a lab project yourself, place the right package/imports and dependencies. This lesson does not create those Java files on the user's machine.

## 6. Minimal Configuration for the Lab Project

### 6.1. Dependencies

With Maven and appropriate Spring Boot dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>mongodb</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Artifact names illustrate **Testcontainers 1.x**. Newer major versions may change module coordinates; use a **compatible BOM** and check the documentation for the chosen version. In Spring Boot 3.4+/Spring Framework 6.2+, the controller slice example below uses **@MockitoBean**.

### 6.2. Which Layers Need Docker/Testcontainers?

- **Unit tests with Mockito:** no Docker/MongoDB required.
- **@WebMvcTest controller slice:** no MongoDB required if the service is mocked.
- **@DataMongoTest with MongoDBContainer:** requires a compatible container runtime.
- **@SpringBootTest E2E with MongoDBContainer:** requires a test container database and a real HTTP server.

If CI cannot run Docker, that is a test infrastructure issue; do not replace every integration test with mocks and still claim that real MongoDB has been verified.

### 6.3. Spring Boot Application

File **Mongo411Application.java**:

~~~java
package com.example.mongo411;

import java.time.Clock;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Mongo411Application {

    public static void main(String[] args) {
        SpringApplication.run(
            Mongo411Application.class, args
        );
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Production uses system time, while unit tests can inject **Clock.fixed** to verify createdAt precisely.

## 7. Domain Model and Real Repository

### 7.1. BookingStatus

File **domain/BookingStatus.java**:

~~~java
package com.example.mongo411.domain;

public enum BookingStatus {
    REQUESTED,
    CONFIRMED,
    CANCELLED
}
~~~

### 7.2. GuestInfo as an Embedded Document

File **domain/GuestInfo.java**:

~~~java
package com.example.mongo411.domain;

import org.springframework.data.mongodb.core.mapping.Field;

public class GuestInfo {

    @Field("full_name")
    private String fullName;

    protected GuestInfo() {
    }

    public GuestInfo(String fullName) {
        this.fullName = fullName;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

An embedded object does not need its own collection.

### 7.3. BookingDocument

File **domain/BookingDocument.java**:

~~~java
package com.example.mongo411.domain;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "booking_requests_411")
public class BookingDocument {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("listing_id")
    private String listingId;

    @Field("guest")
    private GuestInfo guest;

    @Field("status")
    private BookingStatus status;

    @Field("created_at")
    private Instant createdAt;

    protected BookingDocument() {
    }

    public BookingDocument(
            String id,
            String tenantId,
            String listingId,
            GuestInfo guest,
            Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.listingId = listingId;
        this.guest = guest;
        this.status = BookingStatus.REQUESTED;
        this.createdAt = createdAt;
    }

    public void confirm() {
        if (status == BookingStatus.CANCELLED) {
            throw new IllegalStateException(
                "Cancelled booking cannot be confirmed"
            );
        }
        status = BookingStatus.CONFIRMED;
    }

    public void cancel() {
        status = BookingStatus.CANCELLED;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getListingId() {
        return listingId;
    }

    public GuestInfo getGuest() {
        return guest;
    }

    public BookingStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

IDs formatted like **"bk-411..."** in the example are Strings without a 24-hex-digit shape, avoiding ambiguity around **@Id String → BSON ObjectId** conversion. For IDs that look like ObjectIds, check how Spring Data MongoDB converts them or choose an appropriate **@MongoId(FieldType.STRING)** strategy.

### 7.4. BookingRepository

File **repository/BookingRepository.java**:

~~~java
package com.example.mongo411.repository;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;
import com.example.mongo411.domain.BookingDocument;

public interface BookingRepository
        extends MongoRepository<BookingDocument, String> {

    Optional<BookingDocument> findByIdAndTenantId(
        String id,
        String tenantId
    );
}
~~~

The derived query must use mapping to read MongoDB:

~~~javascript
{
  _id: "bk-411-example",
  tenant_id: "tenant-001"
}
~~~

This is what an **integration test** should prove. Mockito does not know whether MongoDB has a tenant_id field.

## 8. BookingService: Concentrating Business Rules

File **service/BookingService.java**:

~~~java
package com.example.mongo411.service;

import java.time.Clock;
import java.time.Instant;
import java.util.NoSuchElementException;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.BookingStatus;
import com.example.mongo411.domain.GuestInfo;
import com.example.mongo411.repository.BookingRepository;

@Service
public class BookingService {

    private final BookingRepository repository;
    private final Clock clock;

    public BookingService(
            BookingRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public BookingDocument createBooking(
            String tenantId,
            String listingId,
            String guestName) {
        requireText(tenantId, "tenantId");
        requireText(listingId, "listingId");
        requireText(guestName, "guestName");

        BookingDocument booking = new BookingDocument(
            "bk-411-" + UUID.randomUUID(),
            tenantId,
            listingId,
            new GuestInfo(guestName),
            Instant.now(clock)
        );

        return repository.save(booking);
    }

    public BookingDocument getBooking(
            String tenantId,
            String bookingId) {
        requireText(tenantId, "tenantId");
        requireText(bookingId, "bookingId");

        return repository
            .findByIdAndTenantId(bookingId, tenantId)
            .orElseThrow(() -> new NoSuchElementException(
                "Booking does not exist in tenant"
            ));
    }

    public BookingDocument confirmBooking(
            String tenantId,
            String bookingId) {
        BookingDocument booking =
            getBooking(tenantId, bookingId);

        if (booking.getStatus()
                == BookingStatus.CONFIRMED) {
            // Do not write again if already in the target state.
            return booking;
        }

        booking.confirm();
        return repository.save(booking);
    }

    private static void requireText(
            String value,
            String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                fieldName + " must not be blank"
            );
        }
    }
}
~~~

This service is **intentionally minimal for learning testing**:

- No real authentication integration.
- No verification that the listing is still available.
- No optimistic locking, so concurrent updates can cause lost updates.
- No idempotency key for creation.
- No audit log or multi-document transaction.

These limitations become additional testing and design requirements in later sections.

## 9. Unit Testing with JUnit 5 and Mockito

### 9.1. Why Mock the Repository?

Rules such as **a cancelled booking cannot be confirmed** do not depend on disk, network, BSON, indexes, or a replica set. A unit test can use a mock to immediately return a BookingDocument in the desired state.

The goal is:

~~~text
When: repository returns a CANCELLED booking
Then: confirmBooking throws IllegalStateException
And: repository.save is not called
~~~

### 9.2. Unit Test Example

File **service/BookingServiceUnitTest.java**:

~~~java
package com.example.mongo411.service;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.NoSuchElementException;
import java.util.Optional;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.BookingStatus;
import com.example.mongo411.domain.GuestInfo;
import com.example.mongo411.repository.BookingRepository;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class BookingServiceUnitTest {

    private static final Instant FIXED_TIME =
        Instant.parse("2026-01-15T09:00:00Z");

    @Mock
    BookingRepository repository;

    BookingService service;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(
            FIXED_TIME, ZoneOffset.UTC
        );
        service = new BookingService(
            repository, clock
        );
    }

    @Test
    void createBookingSavesRequestedState() {
        when(repository.save(any(BookingDocument.class)))
            .thenAnswer(call -> call.getArgument(0));

        BookingDocument result = service.createBooking(
            "tenant-001",
            "listing-100",
            "Lan"
        );

        assertNotNull(result.getId());
        assertTrue(result.getId().startsWith("bk-411-"));
        assertEquals(
            BookingStatus.REQUESTED, result.getStatus()
        );
        assertEquals(FIXED_TIME, result.getCreatedAt());
        assertEquals(
            "tenant-001", result.getTenantId()
        );
        assertEquals(
            "Lan", result.getGuest().getFullName()
        );
        verify(repository).save(result);
    }

    @Test
    void rejectsBlankTenantWithoutDatabaseCall() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.createBooking(
                " ", "listing-100", "Lan"
            )
        );

        verifyNoInteractions(repository);
    }

    @Test
    void confirmsRequestedBookingAndPersistsIt() {
        BookingDocument booking = booking("bk-411-1");

        when(repository.findByIdAndTenantId(
            "bk-411-1", "tenant-001"
        )).thenReturn(Optional.of(booking));
        when(repository.save(booking))
            .thenReturn(booking);

        BookingDocument result = service.confirmBooking(
            "tenant-001", "bk-411-1"
        );

        assertEquals(
            BookingStatus.CONFIRMED, result.getStatus()
        );
        verify(repository).save(booking);
    }

    @Test
    void cannotConfirmCancelledBooking() {
        BookingDocument booking = booking("bk-411-2");
        booking.cancel();

        when(repository.findByIdAndTenantId(
            "bk-411-2", "tenant-001"
        )).thenReturn(Optional.of(booking));

        assertThrows(
            IllegalStateException.class,
            () -> service.confirmBooking(
                "tenant-001", "bk-411-2"
            )
        );

        verify(repository, never()).save(any());
    }

    @Test
    void confirmedBookingIsIdempotentForConfirm() {
        BookingDocument booking = booking("bk-411-3");
        booking.confirm();

        when(repository.findByIdAndTenantId(
            "bk-411-3", "tenant-001"
        )).thenReturn(Optional.of(booking));

        BookingDocument result = service.confirmBooking(
            "tenant-001", "bk-411-3"
        );

        assertEquals(
            BookingStatus.CONFIRMED, result.getStatus()
        );
        verify(repository, never()).save(any());
    }

    @Test
    void missingOrOtherTenantBookingIsNotReturned() {
        when(repository.findByIdAndTenantId(
            "bk-411-4", "tenant-002"
        )).thenReturn(Optional.empty());

        assertThrows(
            NoSuchElementException.class,
            () -> service.getBooking(
                "tenant-002", "bk-411-4"
            )
        );

        verify(repository).findByIdAndTenantId(
            "bk-411-4", "tenant-002"
        );
    }

    private BookingDocument booking(String id) {
        return new BookingDocument(
            id,
            "tenant-001",
            "listing-100",
            new GuestInfo("Lan"),
            FIXED_TIME
        );
    }
}
~~~

### 9.3. What Do Unit Tests Actually Prove?

The tests above prove:

- Service validation runs before calling the repository.
- REQUESTED/CONFIRMED/CANCELLED states obey the rules.
- Clock can be fixed.
- The service passes **both bookingId and tenantId** to the repository.
- No save occurs when rules disallow it.

They **do not prove**:

- That findByIdAndTenantId translates into the right BSON query.
- That Mongod stores guest.full_name properly.
- That a unique index exists.
- That the API returns the right status code.
- That a real MongoDB instance is reachable.

### 9.4. Test Doubles Return What You Stub, Not What the Database Has

Example:

~~~java
when(repository.findByIdAndTenantId(
    "bk-411-1", "tenant-001"
)).thenReturn(Optional.of(booking));
~~~

Mockito returns the booking because we told it to; it **does not parse MongoDB field names**. If the derived query name is wrong or a field name changed, the unit test can still PASS.

### 9.5. Avoid Over-Reliance on verify

Not every unit test needs to verify the exact order of every call. If a test only passes because an internal method was called exactly three times, refactoring the implementation can break the test even when behavior is unchanged.

Prefer asserting on **observable behavior**, and use interaction assertions when **not writing / not calling a dependency** is itself part of the requirement.

## 10. Pure Java Tests Without Mockito

A domain method like:

~~~java
public void confirm() {
    if (status == BookingStatus.CANCELLED) {
        throw new IllegalStateException(
            "Cancelled booking cannot be confirmed"
        );
    }
    status = BookingStatus.CONFIRMED;
}
~~~

can be tested directly:

~~~java
@Test
void cancelledBookingCannotBeConfirmed() {
    BookingDocument booking = new BookingDocument(
        "bk-411-domain",
        "tenant-001",
        "listing-100",
        new GuestInfo("Lan"),
        Instant.parse("2026-01-15T09:00:00Z")
    );

    booking.cancel();

    assertThrows(
        IllegalStateException.class,
        booking::confirm
    );
    assertEquals(
        BookingStatus.CANCELLED,
        booking.getStatus()
    );
}
~~~

This is a unit test **without mocks**. Do not add Mockito just because a file ends with Test.

## 11. Real MongoDB Integration Tests with Testcontainers

### 11.1. Why Not Use a Mocked MongoTemplate?

A mocked MongoTemplate does not perform:

- BSON serialization/deserialization.
- **@Field("tenant_id")** mapping.
- Query execution and nested array semantics.
- MongoDB unique index enforcement.
- Real server transaction semantics.
- Driver/server wire protocol and errors.

A well-targeted integration test must use a **real MongoDB server**, even if it runs in an ephemeral container.

### 11.2. What Does Testcontainers Do?

**Testcontainers** spins up a MongoDB container suitable for integration tests, provides the connection URI, and cleans up the environment according to the test lifecycle.

Advantages:

- Independent of data on the developer's machine.
- Same image/version in CI when configured consistently.
- Can reproduce real MongoDB errors.
- Suitable for checking mapping, repositories, indexes, and data.

Notes:

- Requires a compatible container runtime.
- Image pulls can take time.
- Test datasets should be small yet cover edge cases.
- Image version should stay close to production; do not use an uncontrolled “latest” tag.
- A single-node container **does not prove HA/failover of a three-node replica set**.

### 11.3. @DataMongoTest

**@DataMongoTest** is a Spring Boot test slice focused on MongoDB persistence components, typically loading mapping, repositories, and MongoTemplate without loading all web/service layers of the system.

This is a good scope for:

> “Does this repository method really query the right BSON fields and return the expected Java object?”

### 11.4. Complete Integration Test

File **repository/BookingRepositoryIntegrationTest.java**:

~~~java
package com.example.mongo411.repository;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.GuestInfo;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class BookingRepositoryIntegrationTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired
    BookingRepository repository;

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void resetTestCollection() {
        // ONLY on this class's MongoDB test container.
        template
            .getCollection("booking_requests_411")
            .deleteMany(new Document());
    }

    @Test
    void savesMappedBsonFieldNamesAndNestedGuest() {
        BookingDocument booking = sample(
            "bk-411-it-1",
            "tenant-001"
        );
        repository.save(booking);

        Document bson = template
            .getCollection("booking_requests_411")
            .find(new Document("_id", "bk-411-it-1"))
            .first();

        assertNotNull(bson);
        assertEquals(
            "tenant-001", bson.getString("tenant_id")
        );
        assertFalse(bson.containsKey("tenantId"));

        Document guest = bson.get("guest", Document.class);
        assertNotNull(guest);
        assertEquals(
            "Lan", guest.getString("full_name")
        );
        assertEquals(
            "REQUESTED", bson.getString("status")
        );
        assertNotNull(bson.getDate("created_at"));
    }

    @Test
    void derivedQueryRequiresMatchingTenant() {
        repository.save(
            sample("bk-411-it-2", "tenant-001")
        );

        assertTrue(
            repository.findByIdAndTenantId(
                "bk-411-it-2", "tenant-001"
            ).isPresent()
        );
        assertTrue(
            repository.findByIdAndTenantId(
                "bk-411-it-2", "tenant-002"
            ).isEmpty()
        );
    }

    @Test
    void duplicateIdIsRejectedByRealMongoDb() {
        repository.insert(
            sample("bk-411-dup", "tenant-001")
        );

        assertThrows(
            DuplicateKeyException.class,
            () -> repository.insert(
                sample("bk-411-dup", "tenant-002")
            )
        );
    }

    private BookingDocument sample(
            String id,
            String tenantId) {
        return new BookingDocument(
            id,
            tenantId,
            "listing-100",
            new GuestInfo("Lan"),
            Instant.parse("2026-01-15T09:00:00Z")
        );
    }
}
~~~

### 11.5. What This Test Proves

- **MongoRepository.save()** executes a write via the driver.
- **@Field** properly stores **tenant_id**.
- Embedded guest contains **full_name**.
- A BSON Date is stored for created_at.
- Derived query **findByIdAndTenantId** works against a real database.
- MongoDB enforces **_id** uniqueness when inserting two documents with the same ID.

### 11.6. Why Use insert in the Duplicate Test?

**save** has different semantics from **insert**. If you save a document with an existing _id, the repository can perform an appropriate replace/upsert; that is **not** a good test for duplicate-key on insert.

To prove MongoDB rejects two inserts with the same _id, explicitly use **insert**.

### 11.7. Note on MongoDBContainer

In the illustrated Testcontainers MongoDB module versions, **getReplicaSetUrl()** returns a URI suitable for the single-node replica-set container provisioned by Testcontainers for testing.

Do not conclude:

~~~text
MongoDBContainer has replicaSetUrl
  => three-node election, network partition,
     and cross-region latency have been tested.
~~~

Those HA/failover scenarios require dedicated topology/chaos tests.

### 11.8. Never Use a Production Database in @DataMongoTest

A line like:

~~~java
template.getCollection(
    "booking_requests_411"
).deleteMany(new Document());
~~~

is acceptable **only because this is an isolated MongoDB container created by the test**.

If the URI is accidentally misconfigured to point to production, this line can wipe real data. When organizing deployments:

- Maintain a test profile without production secrets.
- Limit CI credentials to test databases only.
- Use network policies to block test runners from reaching production wherever possible.
- Fail fast if the URI does not belong to a test deployment.
- Do not run destructive cleanup without verifying the environment.

## 12. Testing Unique Indexes and Server Constraints

### 12.1. An Index Annotation Is Not an Actual Index

If a model adds:

~~~java
@Indexed(unique = true)
private String externalRequestId;
~~~

you cannot simply assert the annotation exists and conclude the server will reject duplicates. Auto-index creation depends on configuration and conditions, and data migrations can cause index builds to fail.

An **integration test** should verify that the index is actually created and enforced.

### 12.2. Creating a Unique Index on an Isolated Test Collection

Illustrative example in an isolated MongoDB container:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

MongoCollection<Document> keys =
    template.getCollection("request_keys_411");

keys.deleteMany(new Document());
keys.createIndex(
    new Document("tenant_id", 1)
        .append("request_key", 1),
    new IndexOptions().unique(true)
);

keys.insertOne(
    new Document("_id", "key-411-a")
        .append("tenant_id", "tenant-001")
        .append("request_key", "req-001")
);

assertThrows(
    MongoWriteException.class,
    () -> keys.insertOne(
        new Document("_id", "key-411-b")
            .append("tenant_id", "tenant-001")
            .append("request_key", "req-001")
    )
);
~~~

This tests **server enforcement of a compound unique index**. The same request_key across different tenants may be allowed depending on the index pattern.

### 12.3. Both Positive and Negative Tests Are Needed

- Positive: two different tenants can use the same request_key if the contract allows it.
- Negative: the same tenant cannot insert a duplicate request_key.
- Migration: if duplicates already exist before index creation, creating the index can fail.

Not all unique indexes belong on runtime entities; production typically uses controlled migrations.

## 13. Mapping and BSON Types Require Integration Coverage

### 13.1. Java String ID and ObjectId

When using **@Id String**, Spring Data may apply ObjectId conversion for strings with a matching shape. A unit test with a mocked repository cannot see this BSON type issue.

Integration tests should cover:

- Business String IDs containing hyphens.
- 24-character hex IDs if the system uses them.
- Queries via Repository and raw MongoDB Document.
- Verifying whether the actual **_id** is a BSON String or ObjectId.

If policy requires pure Strings, consider **@MongoId(FieldType.STRING)** and verify readback.

### 13.2. BigDecimal and Decimal128

For monetary amounts:

~~~java
@Field(
    value = "amount",
    targetType = FieldType.DECIMAL128
)
private BigDecimal amount;
~~~

Integration tests must confirm the actual BSON type is **decimal**, not String or Double, and that the value/scale is restored accurately.

### 13.3. Nested Arrays

Given:

~~~javascript
{
  rooms: [
    { type: "bedroom", area_sqm: 10 },
    { type: "kitchen", area_sqm: 30 }
  ]
}
~~~

Two conditions:

~~~javascript
{
  "rooms.type": "bedroom",
  "rooms.area_sqm": { $gte: 20 }
}
~~~

can match **different elements** in the array. If the business rule requires the same room to satisfy both, **$elemMatch** must be used.

A unit test checking only that a query string was built is not enough to prove this semantics. Seed a **counterexample document** in an integration test.

### 13.4. Null and Missing Fields

Older documents might lack the guest field. Integration tests should check:

- guest absent.
- guest: null.
- guest.full_name: null.
- guest.full_name: "".
- guest.full_name containing a valid string.

MongoDB **{ field: null }** can match both null and missing according to query semantics. Business logic must know when to use **$exists, $type**, and validation.

### 13.5. Mapping _class

A converter test can assert fields and nested objects without **hardcoding a full class name** if the project plans to adopt type aliases. If using polymorphism, include corresponding tests proving subclasses read back properly even when _class/type metadata changes.

## 14. Controller Slice Tests with @WebMvcTest

### 14.1. When to Use @WebMvcTest?

If you only need to verify:

- Route **POST /api/bookings** maps properly.
- Request JSON body deserializes.
- Headers are read.
- HTTP status is 201.
- Response DTO contains the expected fields.
- Controller translates exceptions to HTTP statuses.

then **@WebMvcTest** can be fast and sufficient. It does not need MongoDB running.

### 14.2. Request/Response DTOs

File **web/CreateBookingRequest.java**:

~~~java
package com.example.mongo411.web;

public record CreateBookingRequest(
    String listingId,
    String guestName
) {}
~~~

File **web/BookingResponse.java**:

~~~java
package com.example.mongo411.web;

import com.example.mongo411.domain.BookingDocument;

public record BookingResponse(
    String id,
    String listingId,
    String status,
    String createdAt
) {

    public static BookingResponse from(
            BookingDocument booking) {
        return new BookingResponse(
            booking.getId(),
            booking.getListingId(),
            booking.getStatus().name(),
            booking.getCreatedAt().toString()
        );
    }
}
~~~

### 14.3. Lab Controller

File **web/BookingController.java**:

~~~java
package com.example.mongo411.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.service.BookingService;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final BookingService service;

    public BookingController(BookingService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookingResponse> create(
            @RequestHeader("X-Lab-Tenant") String tenant,
            @RequestBody CreateBookingRequest request) {
        BookingDocument saved = service.createBooking(
            tenant,
            request.listingId(),
            request.guestName()
        );
        return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(BookingResponse.from(saved));
    }

    @GetMapping("/{id}")
    public BookingResponse get(
            @RequestHeader("X-Lab-Tenant") String tenant,
            @PathVariable String id) {
        return BookingResponse.from(
            service.getBooking(tenant, id)
        );
    }

    @PatchMapping("/{id}/confirm")
    public BookingResponse confirm(
            @RequestHeader("X-Lab-Tenant") String tenant,
            @PathVariable String id) {
        return BookingResponse.from(
            service.confirmBooking(tenant, id)
        );
    }
}
~~~

**Security warning:** The **X-Lab-Tenant** header is solely a simulated identity mechanism for learning. In production, tenantId must be derived from a **server-verified authenticated principal/session/token**. Never allow users to swap a header themselves and treat them as another tenant.

### 14.4. Translating Exceptions to Status Codes

File **web/BookingErrorHandler.java**:

~~~java
package com.example.mongo411.web;

import java.util.NoSuchElementException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
public class BookingErrorHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> badRequest(
            IllegalArgumentException error) {
        return ResponseEntity
            .badRequest()
            .body(error.getMessage());
    }

    @ExceptionHandler(NoSuchElementException.class)
    ResponseEntity<String> notFound(
            NoSuchElementException error) {
        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body("Booking not found");
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<String> conflict(
            IllegalStateException error) {
        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(error.getMessage());
    }
}
~~~

### 14.5. @WebMvcTest and @MockitoBean

File **web/BookingControllerSliceTest.java**:

~~~java
package com.example.mongo411.web;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

import java.time.Instant;

import com.example.mongo411.domain.BookingDocument;
import com.example.mongo411.domain.GuestInfo;
import com.example.mongo411.service.BookingService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(BookingController.class)
class BookingControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    BookingService service;

    @Test
    void postCreatesBookingAndReturns201() throws Exception {
        BookingDocument saved = new BookingDocument(
            "bk-411-mvc",
            "tenant-001",
            "listing-100",
            new GuestInfo("Lan"),
            Instant.parse("2026-01-15T09:00:00Z")
        );

        when(service.createBooking(
            "tenant-001", "listing-100", "Lan"
        )).thenReturn(saved);

        mvc.perform(
            post("/api/bookings")
                .header("X-Lab-Tenant", "tenant-001")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"listingId\":\"listing-100\","
                    + "\"guestName\":\"Lan\"}"
                )
        )
        .andExpect(status().isCreated())
        .andExpect(
            jsonPath("$.id").value("bk-411-mvc")
        )
        .andExpect(
            jsonPath("$.status").value("REQUESTED")
        );
    }
}
~~~

**Note:** In Java, static imports for MockMvcRequestBuilders/MockMvcResultMatchers must form **a valid Java statement** (in the snippet they are wrapped across lines after the dot for readability; the Java compiler allows that whitespace). Depending on component scanning configuration, ensure **BookingErrorHandler** is included in the MVC slice when testing error mappings.

### 14.6. Proving the Real Scope

The test above:

- Uses Spring MVC mapping/JSON infrastructure.
- Runs the real controller.
- Uses a Mockito mock for BookingService.
- **Does not call** MongoDB.
- Does not prove repository and persistence wiring.

This is a **slice test**; do not report “booking workflow E2E verified” based solely on this test.

### 14.7. @AutoConfigureMockMvc with @SpringBootTest

An application can use:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiIntegrationTest {
    @Autowired MockMvc mvc;
}
~~~

With the full context and real MongoDB, the test exercises controller/service/repository, yet **MockMvc does not open a real TCP HTTP server**. That is a **full-context HTTP-layer integration test**, not synonymous with real-port E2E. Choose the name and objective clearly.

## 15. Service-Level E2E with Real HTTP and Real MongoDB

### 15.1. Objective

An E2E scenario should prove end-to-end behavior:

~~~text
POST /api/bookings
   |
   v
201 + booking ID
   |
   v
GET /api/bookings/{id}
   |
   v
200 + REQUESTED
   |
   v
PATCH /api/bookings/{id}/confirm
   |
   v
200 + CONFIRMED
   |
   v
MongoDB stores status CONFIRMED
~~~

Along with a negative path:

~~~text
GET with a different tenant
   |
   v
404 (does not disclose booking)
~~~

This is **service-level E2E with a simulated tenant header**, not yet a security E2E test with real authentication.

### 15.2. @SpringBootTest RANDOM_PORT

Choose:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
~~~

Spring Boot starts an embedded HTTP server on a random port. **TestRestTemplate** sends requests via an HTTP client to the real server, rather than merely invoking the controller as a Java method.

### 15.3. Complete E2E Test

File **BookingHttpE2ETest.java**:

~~~java
package com.example.mongo411;

import static org.junit.jupiter.api.Assertions.*;

import com.example.mongo411.web.BookingResponse;
import com.example.mongo411.web.CreateBookingRequest;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.http.*;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Testcontainers
class BookingHttpE2ETest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired
    TestRestTemplate http;

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void clean() {
        template
            .getCollection("booking_requests_411")
            .deleteMany(new Document());
    }

    @Test
    void createReadConfirmAndIsolateTenant() {
        HttpHeaders ownerHeaders = new HttpHeaders();
        ownerHeaders.set("X-Lab-Tenant", "tenant-001");

        HttpEntity<CreateBookingRequest> createRequest =
            new HttpEntity<>(
                new CreateBookingRequest(
                    "listing-100", "Lan"
                ),
                ownerHeaders
            );

        ResponseEntity<BookingResponse> created =
            http.exchange(
                "/api/bookings",
                HttpMethod.POST,
                createRequest,
                BookingResponse.class
            );

        assertEquals(
            HttpStatus.CREATED,
            created.getStatusCode()
        );
        assertNotNull(created.getBody());
        assertEquals(
            "REQUESTED",
            created.getBody().status()
        );

        String bookingId = created.getBody().id();
        assertNotNull(bookingId);

        ResponseEntity<BookingResponse> fetched =
            http.exchange(
                "/api/bookings/" + bookingId,
                HttpMethod.GET,
                new HttpEntity<>(null, ownerHeaders),
                BookingResponse.class
            );

        assertEquals(
            HttpStatus.OK,
            fetched.getStatusCode()
        );
        assertEquals(
            bookingId, fetched.getBody().id()
        );

        ResponseEntity<BookingResponse> confirmed =
            http.exchange(
                "/api/bookings/" + bookingId + "/confirm",
                HttpMethod.PATCH,
                new HttpEntity<>(null, ownerHeaders),
                BookingResponse.class
            );

        assertEquals(
            HttpStatus.OK,
            confirmed.getStatusCode()
        );
        assertEquals(
            "CONFIRMED",
            confirmed.getBody().status()
        );

        Document saved = template
            .getCollection("booking_requests_411")
            .find(new Document("_id", bookingId))
            .first();

        assertNotNull(saved);
        assertEquals(
            "CONFIRMED", saved.getString("status")
        );
        assertEquals(
            "tenant-001", saved.getString("tenant_id")
        );

        HttpHeaders otherTenant = new HttpHeaders();
        otherTenant.set("X-Lab-Tenant", "tenant-002");

        ResponseEntity<String> denied =
            http.exchange(
                "/api/bookings/" + bookingId,
                HttpMethod.GET,
                new HttpEntity<>(null, otherTenant),
                String.class
            );

        assertEquals(
            HttpStatus.NOT_FOUND,
            denied.getStatusCode()
        );
    }
}
~~~

### 15.4. Why Can E2E Catch Bugs That Unit Tests Miss?

A mistake like:

~~~java
@GetMapping("/api/booking/{id}")
~~~

instead of:

~~~java
@GetMapping("/api/bookings/{id}")
~~~

can cause E2E to return **404**, even while all BookingService unit tests PASS.

A URI configuration bug, bean wiring issue, or response serializer defect may also only appear when running the real application.

### 15.5. Limitations of the Example E2E Test

This is **not production-wide E2E** because:

- The tenant header is not verified by JWT/SSO.
- There is no ingress/load balancer/API gateway.
- Only one MongoDB test container is used, insufficient to test three-node failover.
- There are no external email, payment, message broker, or search index integrations.
- It does not test browser UI.
- It does not test real concurrent requests.

When reporting results, state accurately: **“service-level HTTP-to-MongoDB E2E”**.

## 16. Distinguishing E2E, Contract, UI, and Smoke Tests

### 16.1. Service-Level E2E

Real HTTP → Spring Boot → real MongoDB. Example in section 15.

### 16.2. Product-Level E2E

A complete user journey:

~~~text
Browser
  -> Login/Identity Provider
  -> Frontend
  -> API Gateway
  -> Booking Service
  -> MongoDB
  -> Notification Service
  -> Email/SMS sandbox
  -> User receives confirmation
~~~

This test takes more time and is more prone to flakiness; pick only critical journeys and use test accounts/sandboxes.

### 16.3. Contract Test

For example, the Booking API commits to returning:

~~~json
{
  "id": "bk-411-example",
  "listingId": "listing-100",
  "status": "REQUESTED",
  "createdAt": "2026-01-15T09:00:00Z"
}
~~~

A contract test can check field names, schema, HTTP status, error shape, and backward compatibility. It does not by itself prove MongoDB saved the right state, unless the test is designed with a real persistence flow.

### 16.4. Post-Deploy Smoke Test

A few read-only operations or isolated sandbox data:

- Health/readiness endpoint works.
- Database connection is ready.
- A safe query returns expected data.
- If permitted, a create/read/delete on a test tenant with reliable cleanup.

Never run destructive smoke tests against real customer datasets.

## 17. Testing MongoDB Transactions

### 17.1. What Can a Unit Test Prove?

Suppose the service updates the booking status and inserts an audit event in the same transaction. A unit test can prove that **when the secondary repository throws an exception, the service does not proceed with subsequent business steps** under mock logic.

However, a unit test **cannot prove the server rolls back two writes** as a real MongoDB transaction.

### 17.2. Integration Test for Commit/Rollback

A transaction integration test needs:

- A MongoDB deployment supporting transactions, typically a replica set or sharded cluster.
- A configured Spring transaction manager.
- Operations actually running within the same session/transaction.
- Assertions verifying no partial writes remain after an error.
- Awareness of write concern/read concern and session semantics.

Scenario:

~~~text
BEGIN TRANSACTION
  update booking -> CONFIRMED
  insert audit event
  force exception before commit
ROLLBACK

Assert after transaction:
  booking is still REQUESTED
  audit event does not exist
~~~

### 17.3. @Transactional Is Not Proof

Simply seeing:

~~~java
@Transactional
public void confirmAndAudit(...) {
    // ...
}
~~~

does not prove the transaction actually works. Without a MongoTransactionManager, or with broken self-invocation/proxy setup, behavior may differ from expectations.

Transaction tests must run against a **real database** and verify persisted state after both success and failure.

### 17.4. Testcontainers Single-Node Replica Set

The MongoDB container configured by the Testcontainers module supports replica-set connections for testing in appropriate versions, allowing verification of certain transaction semantics.

**Do not** treat a commit/rollback test on a single-node replica set as proof that the application handles:

- Primary stepdown.
- Network partition.
- Multi-shard distributed transactions.
- Majority timeout.
- Multi-member replica-set recovery.

Those scenarios belong in dedicated integration/system resilience tests.

## 18. Testing Concurrency and Optimistic Locking

### 18.1. Why Is Single-Threaded Testing Not Enough?

Two concurrent requests:

~~~text
Request A reads booking REQUESTED
Request B reads booking REQUESTED
A transitions to CONFIRMED, saves
B transitions to CANCELLED, saves
~~~

If the service uses **read-modify-save** of the entire document without a version check, a **lost update** can occur.

### 18.2. @Version

Spring Data MongoDB supports optimistic locking:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

With supported mapping/operations, the version field helps detect updates on an entity that was modified since it was read.

### 18.3. Splitting Tests

- **Unit:** when the repository throws OptimisticLockingFailureException, the service reacts/retries according to policy.
- **Integration:** two copies with the same version are read; copy A saves successfully, and copy B's save must be rejected by optimistic locking.
- **E2E:** two concurrent HTTP requests do not result in an invalid state, if required by the system.

Do not conclude “the service is concurrency-safe” just because @Version appears in source code.

### 18.4. Do Not Abuse sleep

A concurrency test with:

~~~java
Thread.sleep(1000);
~~~

does not guarantee two operations hit the exact race window. Use **CountDownLatch, CyclicBarrier, or CompletableFuture coordination** to synchronize start times; verify outcomes with deadlines and final persisted data.

### 18.5. If Retrying, Test Idempotency

A timeout does not always mean MongoDB failed to write. A client may receive a timeout after the write already committed. If the API automatically retries create booking with a new ID, it risks duplicating bookings.

Test with integration/E2E:

- Send the same **idempotency key** twice.
- The server uses a unique constraint and reconciliation.
- Only one booking is created.
- The retry response conforms to specified semantics.

Unit tests can verify exception-handling logic for duplicate keys, while server unique enforcement still requires integration testing.

## 19. Choosing the Right Layer for MongoDB-Specific Behaviors

### 19.1. TTL Index

MongoDB TTL cleanup is an **asynchronous** background operation; it does not happen at the exact millisecond a document expires.

A test containing:

~~~java
Thread.sleep(200);
assertFalse(repository.existsById(id));
~~~

can flake or make false assumptions. Instead:

- Unit test the logic that computes expiry timestamps.
- Integration test that the index definition actually has the right **expireAfterSeconds**.
- If TTL deletion itself must be tested, use **eventually/polling with an adequate timeout**, never demanding instant deletion.
- Do not use a TTL test to measure exact per-document deletion timing.

### 19.2. Change Streams

Change Streams require a suitable MongoDB deployment, typically a replica set or sharded cluster.

Split:

- Unit: event-type handling and consumer idempotency.
- Integration: open a real change stream, perform insert/update, read events, verify resume tokens.
- E2E: an event from MongoDB flows through the consumer and produces an observable business side effect.

Do not mock every event and claim you tested the correctness of resumeAfter, oplog retention, or permissions.

### 19.3. Unique Indexes

Unit: the application handles duplicate-key exceptions properly.

Integration: the server actually has the unique index and rejects duplicate data.

E2E: the API returns **409 Conflict** or the agreed response contract on duplicate requests.

### 19.4. JSON Schema Validation

Unit: check DTO/Bean Validation.

Integration: create the MongoDB collection validator in the test database and attempt to insert invalid BSON; verify the server rejects it.

E2E: the API returns an appropriate input error and leaves no invalid document behind.

**Bean Validation** and **MongoDB server schema validation** are two distinct layers.

### 19.5. Read/Write Concerns

Unit tests can confirm the service selects the right policy/configuration when passed through an abstraction.

Integration tests need a real database to verify basic behavior/timeouts.

Resilience/system tests are required to evaluate majority writes, lag, read preferences, and election/failover under a representative topology.

### 19.6. Aggregation

Unit tests are suitable for business transformations after results are fetched.

Integration tests must verify:

- $match/$group/$lookup semantics.
- Empty results and null/missing fields.
- Numeric BSON types.
- Array pipelines.
- Collation, sorting, and pagination.

If aggregation output writes to another collection via $merge/$out, tests must assert side effects and clean up.

### 19.7. Indexes and Query Performance

Integration tests can verify index existence and explain plans in an appropriate environment. However, a test with 50 documents does not prove an index is optimal in production with 50 million documents.

Latency p95/p99, throughput, and saturation require **load/performance tests** on a sufficiently representative dataset and topology.

## 20. Test Fixtures: Small but Purposeful Data

### 20.1. Simple Fixture

~~~java
static BookingDocument booking(
        String id,
        String tenantId) {
    return new BookingDocument(
        id,
        tenantId,
        "listing-100",
        new GuestInfo("Lan"),
        Instant.parse("2026-01-15T09:00:00Z")
    );
}
~~~

A good fixture:

- Has valid defaults.
- Allows overriding fields the test needs to vary.
- Never uses real production data.
- Makes the scenario clear from its name.
- Creates no side effects outside the test's scope.

### 20.2. Plant Counterexample Data

To test tenant isolation, include at least:

~~~text
booking-A: tenant-001
booking-B: tenant-002
~~~

If a test only contains tenant-001 documents, a query missing the tenant filter can still PASS without exposing the risk.

To test array $elemMatch, seed a document with two elements **each satisfying a different condition**, to catch queries that erroneously match across separate elements.

### 20.3. Fix Time

Avoid:

~~~java
assertEquals(
    Instant.now(),
    booking.getCreatedAt()
);
~~~

Two calls to now can differ by milliseconds/nanoseconds. Use **Clock.fixed** in unit tests, or assert a reasonable time window in real integration tests.

### 20.4. Bounded Random IDs

Random UUIDs help avoid collisions, but a test asserting a specific ID should:

- Inject an ID generator, or
- Only assert shape/prefix, or
- Supply a deterministic ID via a fixture.

Do not rely on random ordering or wall-clock timestamps to determine PASS/FAIL.

### 20.5. Never Share One Mutable Dataset Across All Tests

If Test A creates a booking and Test B implicitly depends on that booking, results depend on execution order. Running in parallel or reordering tests will cause flakes.

Each test should create its own required data in an isolated environment, or adhere to a clear fixture/reset contract.

## 21. Managing the MongoDB Test Database Lifecycle

### 21.1. Testcontainers Lifecycle

~~~text
Start container
      |
Create MongoDB test connection
      |
Prepare fixture per test
      |
Run assertions
      |
Cleanup test data / container stops
~~~

To reduce runtime, containers can be shared across tests under an appropriate strategy, though sharing increases the burden of preventing data leakage and test interference.

### 21.2. @BeforeEach Cleanup

On a **completely isolated** container, deleting documents from the test collection before each case is straightforward:

~~~java
@BeforeEach
void clean() {
    template.getCollection(
        "booking_requests_411"
    ).deleteMany(new Document());
}
~~~

This is **not** a safe pattern if tests connect to production or a shared staging environment. Guardrails must ensure the URI truly targets a test environment.

### 21.3. Per-Run Database Names

For parallel CI runs, a dedicated database can be used per job/run:

~~~text
mongo_test_411_run_123
mongo_test_411_run_124
~~~

Or separate containers with independent data filesystems. Choose based on cost and isolation guarantees.

### 21.4. Impact of @DirtiesContext

**@DirtiesContext** instructs the Spring test framework to recreate the application context under specified conditions, which can be very expensive. Do not use it as a default database cleanup command. If the context/beans do not change, resetting test data at the appropriate scope is usually much more efficient.

### 21.5. Parallel Execution

Two tests sharing a database and both calling:

~~~java
deleteMany(new Document());
~~~

can wipe each other's data when running in parallel. Choose one of:

- Separate containers/databases/collections per test.
- Controlled test serialization.
- Unique fixture keys without global cleanup.

Do not simply increase CI worker counts while forgetting data isolation.

## 22. Negative Tests Matter More Than Just the Happy Path

A strong test suite does not only ask “does creating a booking succeed?”.

### 22.1. Validation

- Missing tenantId.
- Blank listingId.
- Blank guestName.
- Invalid JSON.
- Oversized fields.
- Unknown enum status.

### 22.2. Authorization

- Tenant A reads tenant B's booking.
- Tenant A confirms tenant B's booking.
- Unauthenticated user.
- Read-only user attempting to write.

In the lab model, the tenant header is purely illustrative; in a real application, authentication/authorization must be tested at the formal security layer.

### 22.3. Data Integrity

- Duplicate idempotency key.
- Duplicate _id.
- Invalid BSON type.
- Missing required fields when a validator exists.
- Currency/Decimal128 conversion.
- Timestamp timezone/precision.

### 22.4. State Transitions

- REQUESTED → CONFIRMED.
- CONFIRMED → CONFIRMED (idempotent or conflict per contract).
- CANCELLED → CONFIRMED rejected.
- Missing booking → 404.
- Conflicting concurrent updates.

### 22.5. Reliability

- MongoDB temporarily unavailable.
- Driver server selection timeout.
- Connection pool exhaustion.
- Retryable write error.
- Transaction conflict.
- Primary stepdown (only on an appropriate test topology).

Do not use a mock throwing an arbitrary RuntimeException and treat it as testing exact MongoDB error labels/retry semantics.

## 23. Failure Injection: Picking the Right Layer

### 23.1. In Unit Tests

Mock the repository to throw:

~~~java
when(repository.save(any()))
    .thenThrow(
        new IllegalStateException("Simulated persistence failure")
    );
~~~

This tests service/logging/exception-translation behavior per policy. It **does not accurately reproduce a MongoDB driver exception** if the faked exception type does not match.

### 23.2. In Integration Tests

Real server constraints can be simulated via:

- Duplicate unique key.
- Different BSON type.
- Schema validator.
- Document size limit in controlled tests.
- Transaction rollback.
- Query maxTimeMS on an appropriate test workload.

Do not force the test server into indefinite hangs/locks without timeouts and cleanup.

### 23.3. In Resilience/System Tests

Scenarios such as:

- Primary stepdown.
- Loss of a replica member.
- Network delay/partition.
- Disk pressure.
- Sharded migration/failover.

require specialized infrastructure/experiments and guardrails. Never execute them in production solely to increase coverage.

### 23.4. Why Does Retry Logic Need an End-to-End Viewpoint?

A request can follow this sequence:

~~~text
Client sends create
MongoDB commits
Network timeout before response
Client retries
~~~

If creation lacks idempotency, the system can create two bookings. Unit tests verify retry policy, integration tests verify unique key/transaction behavior, and E2E tests verify that two HTTP requests with the same idempotency key yield the correct observable outcome.

## 24. Test Data Containing PII and Security

### 24.1. Do Not Arbitrarily Copy Real Data into CI

Production MongoDB may store names, phone numbers, financial details, and addresses. Dumping raw datasets into CI to “look like production” creates risks:

- Exposing PII/secrets.
- Developers lacking authorization to view that data.
- Unmanaged retention/backups of test databases.
- Logs containing real documents.

Prefer synthetic fixtures or data sanitized and approved per policy.

### 24.2. Test Credentials

A test database user should have permissions scoped strictly to the test deployment. Never place production root URIs in:

~~~text
application-test.yml
GitHub Actions secrets
developer laptops
CI debug logs
~~~

If a secret manager is used, manage test credentials under separate scopes and rotation policies.

### 24.3. Do Not Log Sensitive BSON in Full

When assertions fail, log only the fields needed for debugging and mask PII. Never print raw MongoDB URIs containing passwords or dump full booking documents into public CI artifacts.

## 25. CI Pipeline: Which Tests Run When?

### 25.1. Sample Pipeline

~~~text
Developer push / pull request
          |
          v
     Compile + static checks
          |
          v
        Unit tests
          |
          v
  Persistence integration tests
    (Testcontainers MongoDB)
          |
          v
   Controller/API contract tests
          |
          v
     Service-level E2E
          |
          v
      Build/deploy review
          |
          v
   Staging smoke/system E2E
~~~

Ordering may vary by execution time and cost. The goals are:

- Fail fast on pure logic errors.
- Gather evidence against real MongoDB before deploy.
- Run critical E2E tests at an appropriate frequency.
- Avoid turning every PR into an unnecessarily multi-hour test suite.

### 25.2. On Pull Requests

Typically:

- All unit tests.
- Key integration tests.
- Controller slices/contract tests.
- A few service-level E2E tests.

If too slow, optimize isolation, parallelism, fixture scope, and split pipelines sensibly; never blindly delete all integration tests just to cut runtime.

### 25.3. Nightly or Pre-Release

Can expand to include:

- Multiple supported MongoDB versions.
- Migration fixtures from older schemas.
- Larger datasets.
- Full E2E journeys.
- Replica-set failover tests.
- Load/performance smoke runs.
- Security scanning.

### 25.4. Post-Deploy

Smoke tests must use:

- Health/readiness checks.
- A dedicated test tenant if writes are required.
- Authorized accounts.
- Deadlines and cleanup.
- Alerts if production behavior deviates.

Never create real customer bookings in a smoke test.

## 26. Test Matrix by Environment

| Test type | Local developer | Pull request CI | Nightly/staging | Production |
| --- | --- | --- | --- | --- |
| Unit | Always | Always | Yes | No need to run on production |
| @WebMvcTest | Frequently | Frequently | Yes | No |
| @DataMongoTest + container | With Docker | Recommended | Yes | No |
| HTTP + MongoDB container E2E | With Docker | Critical paths | Full paths | No |
| Schema migration rehearsal | Optional | If schema changed | Recommended | Approved migrations only |
| Failover/resilience | Dedicated lab | Infrastructure-dependent | Recommended when suitable | Do not induce outages |
| Load/performance | Small scale | Smoke | Representative staging | Approved plans only |
| Post-deploy smoke | Not needed | No | Yes | Safe read-only/test-tenant |

The goal is not maximizing E2E count, but **covering the right risks at the layer capable of proving them**.

## 27. Evaluating Test Suite Quality

### 27.1. Code Coverage Does Not Equal Confidence

A service with 95% line coverage where every repository is mocked can still have wrong BSON field names in every single query.

Conversely, a small integration test verifying mapping and unique indexes can catch a severe deployment bug missed by dozens of mock tests.

### 27.2. Mutation Testing

Where feasible, use mutation testing at the unit layer to check whether tests detect when a condition flips from:

~~~text
if (status == CANCELLED)
~~~

to:

~~~text
if (status == CONFIRMED)
~~~

If tests still PASS, rule coverage may be weak. Mutation testing is a complementary technique, not a replacement for integration tests.

### 27.3. Flaky Tests

Common sources:

- Order-dependent tests.
- Shared mutable fixtures.
- Timing-based sleeps.
- Non-deterministic TTL/background jobs.
- MongoDB container not yet ready.
- Random ports, network, and external services.
- CI resource contention.
- Tests comparing Instant.now with exact equality.

Fix flakiness via root cause, isolation, explicit readiness, and bounded eventual assertions. Do not blindly retry tests 10 times and report PASS while masking bugs.

### 27.4. Test Ownership

Every failed test should indicate:

- Is the bug in business logic, mapping, database, or HTTP?
- Where are the logs/test evidence located?
- Who owns fixing it?
- Did test data leak into another case?

A huge suite whose failures are undiagnosable can slow a team down more than a small, well-designed suite.

## 28. Sample Test Plan for a New Feature

### 28.1. Requirement

> “A booking can be confirmed if it is still REQUESTED. A CANCELLED booking must be rejected. No tenant can access another tenant's booking.”

### 28.2. Unit Cases

1. REQUESTED → CONFIRMED.
2. CANCELLED → IllegalStateException.
3. CONFIRMED → idempotent (does not save again).
4. Missing booking → NoSuchElementException.
5. Blank tenant/ID → IllegalArgumentException.
6. Do not call repository.save when validation/state fails.

### 28.3. Integration Cases

1. Persists tenant_id/listing_id/guest.full_name properly.
2. findByIdAndTenantId returns the matching tenant and excludes other tenants.
3. Duplicate _id is rejected by the server.
4. Critical indexes/JSON schema verified if used in deployment.
5. Transaction/optimistic locking behavior if required by the feature.

### 28.4. Controller Slice Cases

1. POST returns 201 + JSON DTO.
2. Missing required header returns 400.
3. Invalid body returns error matching contract.
4. Service reports missing → 404.
5. Service reports conflict → 409.

### 28.5. E2E Cases

1. Create → Get → Confirm → Get, checking persisted state.
2. Cross-tenant GET returns no data.
3. One key negative business flow, such as confirming a cancelled booking returning 409.

### 28.6. Beyond the Three Layers

1. Load test if concurrency/throughput SLOs exist.
2. Failover test if HA is required.
3. Restore drill if RTO/RPO guarantees are required.
4. Security test for real principals/roles.

## 29. Common Mistakes

| Mistake | Problem | Fix |
| --- | --- | --- |
| Mocking MongoRepository and calling it an integration test | Does not actually test the database | @DataMongoTest + real MongoDB |
| Using @WebMvcTest and calling it full E2E | Service/DB are both mocked | Classify as controller slice |
| Having only E2E for every logic branch | Slow, hard to isolate failures | Split out many unit cases |
| Having only unit tests | Blind to mapping/index/server errors | Add persistence integration |
| Pointing integration tests at arbitrary developer localhost | Hard to reproduce, data-dependent | Isolated container |
| Tests connecting to a production URI | Risk of data loss | Fail-fast + network/secret separation |
| Clearing the entire collection before each test on a shared DB | Deletes other tests' data | Separate database/container |
| Tests depending on execution order | Flaky under parallel runs | Independent per-test fixtures |
| Using fixed Thread.sleep for TTL | TTL is asynchronous | Eventual assertion with timeout |
| Comparing Instant.now with exact equality | Nondeterministic | Clock.fixed |
| Using save to test duplicate _id | Save can replace | Use insert |
| Asserting @Indexed annotation is enough | Server may not have built the index | Verify the real index |
| Failing to seed tenant B | Misses missing tenant filter | Cross-tenant negative fixture |
| Testing only single-item arrays | Misses $elemMatch issue | Seed counterexample elements |
| Testing Java fields without inspecting raw BSON | Misses @Field alias/type | Raw Document assertions |
| Ignoring errors/timeouts in E2E | Happy path masks failure paths | Negative/resilience tests |
| Testing transactions on unsupported standalone | False conclusions | Replica set test environment |
| Testing single-node RS and claiming failover tested | No multi-member election | Multi-node resilience test |
| Asserting p99 across 10 requests | Statistically unreliable | Dedicated load test |
| Using production PII as fixtures | Violates privacy/security | Synthetic/anonymized data |
| Hardcoding MongoDB root secret in tests | Exposes high privileges | Least-privilege test credentials |
| Retrying failed tests indefinitely | Masks flakiness | Fix root cause |
| Looking only at line coverage | Coverage ignores integration quality | Mapping/constraints tests |
| Using @DirtiesContext to clean DB on every case | Slow suite and may still leave data | Scope-appropriate reset |
| Not pinning MongoDB/image versions | Undetected drift from production | Pin version/BOM |
| Not naming tests after behavior | Hard to diagnose failures | Given–When–Then and clear names |

## 30. Practice Checklist

### 30.1. Before Writing Tests

- Identify the behavior to prove.
- Choose the lowest layer **capable of proving the real behavior**.
- Separate database-agnostic business rules from persistence adapters where sensible.
- Define BSON/API contracts.
- Identify positive/negative/edge data cases.

### 30.2. Unit

- Avoid Spring context unless needed.
- Mock I/O dependencies.
- Use deterministic Clock/ID generator when needed.
- Assert behavior and side effects / absence of side effects.
- Avoid coupling to unnecessary implementation details.

### 30.3. Integration

- Real MongoDB server, version close to production.
- Isolated test database.
- Assert raw BSON field names/types.
- Test index/unique/schema/query semantics.
- Test null/missing/nested arrays.
- Run transaction/concurrency tests on a supporting deployment.
- Safe cleanup and parallel execution.

### 30.4. E2E

- Clearly state start/end boundaries.
- Real HTTP server if the goal is network-level HTTP.
- Verify response status/body and persisted state.
- Include negative authorization paths.
- Stub external dependencies purposefully, without faking everything.
- Separate test data/credentials.
- Do not use E2E to measure p99 capacity without a load harness.

### 30.5. CI

- Unit tests run frequently and fast.
- Integration tests are never silently disabled.
- Critical E2E paths run before release.
- Artifacts record test environment/versions.
- Flakiness has an owner and root-cause resolution.
- Test credentials never appear in logs.

## 31. Hands-On Exercises

### Exercise 1 — Identify the Layer

A test calls BookingService.confirmBooking with a Mockito repository. Is this unit, integration, or E2E? What has it not verified?

### Exercise 2 — Real Persistence

A test starts a MongoDB Testcontainer, calls repository.save, and then reads the raw BSON Document. Classify it and explain why.

### Exercise 3 — Controller Slice

What type is @WebMvcTest + MockMvc + @MockitoBean BookingService? Why should it not be called full E2E?

### Exercise 4 — Real HTTP

A test uses @SpringBootTest(RANDOM_PORT), TestRestTemplate, and real MongoDB. Which boundaries does it verify?

### Exercise 5 — Test Pyramid

A feature has 20 business validation rules, one repository query, and two user journeys. How would you distribute the tests to be both fast and reliable?

### Exercise 6 — Business Rule

Write a unit test ensuring CANCELLED cannot transition to CONFIRMED and repository.save is not called.

### Exercise 7 — Fixed Time

Replace direct Instant.now() in the service with Clock injection. Write an assertion on createdAt at a fixed timestamp.

### Exercise 8 — Negative Validation

Test an empty tenantId in BookingService. Why is verifyNoInteractions(repository) a valuable assertion?

### Exercise 9 — Mockito Is Not Enough

Mock the repository to return the expected result for findByIdAndTenantId. Why does this test fail to detect whether real MongoDB stores the field name tenant_id?

### Exercise 10 — BSON Mapping

Write an integration test that saves a BookingDocument and asserts the raw Document contains tenant_id, listing_id, and guest.full_name.

### Exercise 11 — Duplicate _id

Why should you call repository.insert twice instead of save twice when testing MongoDB duplicate _id?

### Exercise 12 — Compound Unique Index

Design a unique index on tenant_id and request_key. Write a negative test colliding on both and a positive test with a different tenant_id.

### Exercise 13 — ObjectId Conversion

Explain the risk when a Java @Id String has a value resembling an ObjectId. What should the integration test assert in actual BSON?

### Exercise 14 — Decimal128

A domain uses BigDecimal for rent amounts. Write a test plan for Java → BSON Decimal128 → Java with fractional values.

### Exercise 15 — Array Semantics

Seed a document with a 10 m² bedroom and a 30 m² kitchen. Show how a dotted query can match both conditions across different elements, then fix it with $elemMatch.

### Exercise 16 — Null/Missing

Write cases for guest field missing, null, and guest.full_name empty. Why must all three not be treated as the same business state?

### Exercise 17 — API Contract

POST /api/bookings must return 201, id, status, and createdAt. Write a controller slice test with MockMvc.

### Exercise 18 — 404/409

Design tests for a non-existent booking and a cancelled booking. Specify the exception mapping and HTTP status codes.

### Exercise 19 — E2E Flow

Describe/write a Create → Get → Confirm → Get test and verify the final MongoDB status is CONFIRMED.

### Exercise 20 — Tenant Isolation

Create a booking for tenant-001; accessing it as tenant-002 must be denied or return no data. State which layer tests the policy and which layer tests full HTTP enforcement.

### Exercise 21 — Real Authentication

Why can't the X-Lab-Tenant header in the example serve as a production security mechanism? Design a test with a server-authenticated security principal.

### Exercise 22 — Transaction Rollback

A transaction updates a booking and inserts an audit entry, then throws an exception. Which test type and deployment are needed to confirm zero partial writes?

### Exercise 23 — @Version

Two copies with the same version are read; A saves first, B saves second. Design an optimistic locking integration test and its expected exception.

### Exercise 24 — TTL

Why does a TTL test using a 100 ms sleep often flake? Outline an approach for testing the index definition and asynchronous cleanup.

### Exercise 25 — Change Stream

Split tests for the event handler, real change-stream cursor, and the consumer → business side effect flow.

### Exercise 26 — Testcontainers

Analyze the benefits of pinning the MongoDB image version, generating the replica-set URI automatically, and not relying on a local MongoDB installation on a laptop.

### Exercise 27 — Test Data Isolation

Two tests running in parallel both wipe the entire collection. Propose ways to isolate databases/collections or coordinate test execution.

### Exercise 28 — @DirtiesContext

Why should @DirtiesContext not be used as the default solution for resetting MongoDB between every test?

### Exercise 29 — Production Protection

An integration test calls deleteMany({}) on a lab collection, yet the URI accidentally points to production. Design guardrails across CI/secrets/network/test runtime.

### Exercise 30 — Unknown Fields

Spring Data reads an older document containing a field absent from the Java class and saves it back. What kind of integration test can catch the risk of losing that field?

### Exercise 31 — Retry and Idempotency

A client times out after MongoDB has committed a create. Design unit/integration/E2E tests proving retries do not create duplicate bookings.

### Exercise 32 — Performance Is Not Unit

Why can't you conclude MongoDB meets 500 RPS at p99 200 ms from 10 unit tests and one @DataMongoTest over 20 documents?

### Exercise 33 — Resilience

You need to prove the driver recovers after a primary stepdown. Is a single-node MongoDBContainer sufficient? What topology and test controls are required?

### Exercise 34 — Test Quality

Line coverage reaches 95%, yet production fails because a unique index does not exist. What do you add to the test suite and release pipeline?

### Exercise 35 — CI

Propose a pipeline comprising compile, unit, integration, controller slice/contract, service E2E, staging smoke, and nightly resilience. What is each layer's goal?

### Exercise 36 — End-to-End Plan

For a booking system with 20 tenants, 5 million documents, requiring optimistic locking, idempotency keys, and an audit trail: draft a complete **unit/integration/E2E** test matrix plus out-of-band performance/recovery testing.

## 32. References

- Spring Boot Reference — [Testing](https://docs.spring.io/spring-boot/reference/testing/index.html).
- Spring Boot Reference — [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).
- Spring Boot Reference — [Test Slices](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-tests).
- Spring Data MongoDB — [Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB — [Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).
- Spring Data MongoDB — [Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking).
- JUnit Jupiter — [User Guide](https://junit.org/junit5/docs/current/user-guide/).
- Mockito — [Official site](https://site.mockito.org/).
- Testcontainers Java — [MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/).
- Testcontainers Java — [JUnit 5 Integration](https://java.testcontainers.org/test_framework_integration/junit_5/).
- MongoDB Manual — [Documents](https://www.mongodb.com/docs/manual/core/document/).
- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/).
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).

**Conclusion:** For MongoDB applications, split tests according to the **actual boundaries that need to be proven**: **unit tests** verify business rules quickly and in isolation with JUnit/Mockito; **integration tests** use real MongoDB to verify Spring Data mapping, BSON, queries, indexes, unique constraints, and transactions; **end-to-end tests** verify a journey from the HTTP client through Spring Boot to MongoDB and the returned state. **@WebMvcTest** is a controller slice, not full E2E; **mock repositories** do not prove database behavior; **Testcontainers single-node replica set** does not prove multi-node HA/failover. A trustworthy test suite requires **independent fixtures, deterministic clocks, negative scenarios, tenant isolation, schema evolution checks, test environment safeguards, and sensible CI**. The goal is not to write as many E2E tests as possible, but to **catch bugs at the appropriate layer with the lowest cost, while having sufficient evidence that MongoDB and the entire user flow work properly**.
