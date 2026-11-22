# Designing for Dependency Substitution in Tests (Java OOP)

## 1. Why Is a Class Hard to Test?

Suppose CheckoutService processes payments. If it constructs an HTTP client internally, connects to a payment provider, sends email, and reads the system clock, every unit-test run may require network access, real credentials, or the machine's current time. Such tests are slow, difficult to reproduce, and potentially side-effectful.

The solution is to design **a test seam for replacing dependencies**: CheckoutService knows only the **contracts** it needs, while concrete collaborators are supplied externally. Production wiring provides real adapters; tests supply doubles with controlled behavior.

In Java, the usual technique is **constructor Dependency Injection (DI)** combined with the **Dependency Inversion Principle (DIP)**. Interfaces express capabilities, and constructors allow implementation selection when objects are created. Spring or another DI framework is not required.

### Boundaries to Isolate

| Dependency | Production Runtime | Unit Test | Reason for Substitution |
| --- | --- | --- | --- |
| Payment gateway | Adapter invokes external API | Stub returns planned success/failure/errors | Avoid real service calls; control scenarios |
| Notification sender | SMTP or email service | Spy records send requests | Verify interactions; avoid real email |
| Clock | Clock.systemUTC() | Clock.fixed(...) | Deterministic time, exact assertions |
| Data repository | JDBC/ORM | In-memory fake when appropriate | Isolate business rules and run quickly |

Distinguish **the dependency contract** from **its implementation**. CheckoutService needs to know that PaymentGateway can charge, not whether it uses REST, gRPC, or a test fake.

~~~mermaid
flowchart LR
    T["JUnit test"] --> S["CheckoutService"]
    W["Ứng dụng chạy thật"] --> S
    S --> G["PaymentGateway"]
    S --> R["ReceiptSender"]
    S --> C["Clock"]
    G -. "khi chạy thật" .-> GA["Adapter API thanh toán"]
    G -. "trong test" .-> GS["StubGateway"]
    R -. "trong test" .-> RS["RecordingSender"]
    C -. "trong test" .-> FC["Clock.fixed"]
~~~

## 2. Example Design: Checkout Service

Business contract chosen for this lesson:
1. Order IDs must be non-null and not whitespace-only; VND amounts must be greater than 0.
2. Invalid data throws IllegalArgumentException **before** invoking any dependencies.
3. When the gateway returns true, send one notification; when false, send none.
4. The result contains the approval status and the time obtained from the injected Clock.
5. If the payment gateway throws an exception, propagate it without sending a notification.

This example teaches testing techniques. Real payment systems also require idempotency, transactions, retries, and reliable notifications to avoid an approved charge followed by a lost receipt.

Build a **Java 17 + Maven + JUnit 5** project with this structure:

~~~text
replaceable-dependencies/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── PaymentGateway.java
    │   ├── ReceiptSender.java
    │   └── CheckoutService.java
    └── test/java/vn/example/
        └── CheckoutServiceTest.java
~~~

### 2.1. Maven: pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>replaceable-dependencies</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 2.2. Define the Contracts (Ports)

**src/main/java/vn/example/PaymentGateway.java**

~~~java
package vn.example;

/** Giao tiếp tối thiểu mà nghiệp vụ checkout cần. */
public interface PaymentGateway {
    /**
     * @return true nếu được chấp nhận; false nếu bị từ chối.
     * @throws RuntimeException khi dịch vụ phụ thuộc gặp sự cố.
     */
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/vn/example/ReceiptSender.java**

~~~java
package vn.example;

/** Gửi thông báo cho đơn hàng đã được chấp nhận. */
public interface ReceiptSender {
    void send(String orderId);
}
~~~

Place interfaces near **the needs of their consumers**, rather than importing third-party SDKs directly into business classes. Real adapters can implement PaymentGateway/ReceiptSender in the infrastructure layer.

### 2.3. Inject Dependencies Through the Constructor

**src/main/java/vn/example/CheckoutService.java**

~~~java
package vn.example;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class CheckoutService {
    private final PaymentGateway gateway;
    private final ReceiptSender sender;
    private final Clock clock;

    public CheckoutService(
            PaymentGateway gateway,
            ReceiptSender sender,
            Clock clock) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.sender = Objects.requireNonNull(sender, "sender");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Result checkout(String orderId, long amountVnd) {
        // Xác thực trước khi tạo bất kỳ tác dụng phụ nào.
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }

        boolean accepted = gateway.charge(orderId, amountVnd);

        if (accepted) {
            sender.send(orderId);
        }

        return new Result(accepted, clock.instant());
    }

    public record Result(boolean accepted, Instant checkedAt) {}
}
~~~

All three fields are final: each object's dependencies are fixed when constructed. Objects.requireNonNull reports wiring errors early rather than waiting until checkout is actually called. Clock is an existing Java abstraction; there is no need to invent TimeProvider solely to replace Instant.now().

The key: CheckoutService **does not construct adapters with new**, select environments inside business logic, or instantiate Clock.systemUTC() itself. The **composition root** supplies these dependencies. Production wiring might provide a real PaymentGateway, ReceiptSender, and Clock.systemUTC(); tests can inject the doubles below.

## 3. Writing Unit Tests Without Network or Real Email

We use two test doubles:
- **StubGateway**: returns predetermined results (true/false/exceptions) and records arguments and call counts.
- **RecordingSender**: a minimal spy recording order IDs for requested sends.
- **Clock.fixed(...)**: replaces the system clock with a fixed instant.

**src/test/java/vn/example/CheckoutServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    private static final Instant FIXED_TIME =
            Instant.parse("2026-01-02T03:04:05Z");

    private final StubGateway gateway = new StubGateway();
    private final RecordingSender sender = new RecordingSender();
    private final Clock clock = Clock.fixed(FIXED_TIME, ZoneOffset.UTC);

    private CheckoutService service() {
        return new CheckoutService(gateway, sender, clock);
    }

    @Test
    void successChargesOnceAndSendsOneReceipt() {
        gateway.approved = true;

        CheckoutService.Result result =
                service().checkout("ORD-001", 150_000);

        assertTrue(result.accepted());
        assertEquals(FIXED_TIME, result.checkedAt());
        assertEquals(1, gateway.calls);
        assertEquals("ORD-001", gateway.lastOrderId);
        assertEquals(150_000, gateway.lastAmount);
        assertEquals(List.of("ORD-001"), sender.sentOrderIds);
    }

    @Test
    void declinedPaymentDoesNotSendReceipt() {
        gateway.approved = false;

        CheckoutService.Result result =
                service().checkout("ORD-002", 80_000);

        assertFalse(result.accepted());
        assertEquals(FIXED_TIME, result.checkedAt());
        assertEquals(1, gateway.calls);
        assertTrue(sender.sentOrderIds.isEmpty());
    }

    @Test
    void invalidInputNeverCallsDependencies() {
        CheckoutService checkout = service();

        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout(null, 100));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout("  ", 100));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout("ORD-003", 0));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout("ORD-003", -10));

        assertEquals(0, gateway.calls);
        assertTrue(sender.sentOrderIds.isEmpty());
    }

    @Test
    void gatewayFailurePropagatesWithoutSending() {
        IllegalStateException failure =
                new IllegalStateException("Gateway unavailable");
        gateway.failure = failure;

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                () -> service().checkout("ORD-004", 200_000));

        assertSame(failure, actual);
        assertEquals(1, gateway.calls);
        assertTrue(sender.sentOrderIds.isEmpty());
    }

    @Test
    void constructorRejectsMissingDependencies() {
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(null, sender, clock));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(gateway, null, clock));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(gateway, sender, null));
    }

    // Stub có khả năng ghi lại tương tác: dùng trong phạm vi test.
    private static final class StubGateway implements PaymentGateway {
        boolean approved = true;
        RuntimeException failure;
        int calls;
        String lastOrderId;
        long lastAmount;

        @Override
        public boolean charge(String orderId, long amountVnd) {
            calls++;
            lastOrderId = orderId;
            lastAmount = amountVnd;

            if (failure != null) {
                throw failure;
            }
            return approved;
        }
    }

    // Spy ghi nhận tác dụng phụ thay vì gửi email.
    private static final class RecordingSender implements ReceiptSender {
        final List<String> sentOrderIds = new ArrayList<>();

        @Override
        public void send(String orderId) {
            sentOrderIds.add(orderId);
        }
    }
}
~~~

### 3.1. Run the Tests

Install JDK 17 and Maven, open a terminal in the directory containing pom.xml, then run:

~~~bash
mvn test
~~~

The code contains **5 @Test methods**; with correct compilation and execution, Maven reports 5 tests, 0 failures, and 0 errors. All scenarios run in memory without actual HTTP requests or email.

By default, JUnit Jupiter creates a fresh test-class instance for each @Test method. StubGateway and RecordingSender are therefore reinitialized for each case; no ordering dependency exists.

### 3.2. What the Tests Actually Establish

| Test | Behavior to Protect | Example Defect Detected |
| --- | --- | --- |
| successChargesOnceAndSendsOneReceipt | Correct charge parameters; receipt only after approval; correct timestamp | Duplicate charges, wrong amount, missing receipt |
| declinedPaymentDoesNotSendReceipt | No notification when the gateway declines | Sends email regardless of outcome |
| invalidInputNeverCallsDependencies | Validate before any side effects | Calls API with blank ID or negative amount |
| gatewayFailurePropagatesWithoutSending | Do not send after a charge failure | Swallows exception and reports successful notification |
| constructorRejectsMissingDependencies | Required collaborators must exist | Constructs an object without a required dependency |

Do not use reflection to read CheckoutService's private fields in tests. These assertions observe public outcomes and interactions recorded by doubles, without prescribing a particular internal algorithm.

## 4. Identifying Test Double Types

| Type | Purpose | Example |
| --- | --- | --- |
| Dummy | Supplied to satisfy a signature but not used in that test | Empty sender when validating input |
| Stub | Supplies fixed/configurable values or outcomes | StubGateway.approved = false |
| Fake | Simple but functional implementation, often storing data in memory | InMemoryUserRepository |
| Spy | Records calls for later verification | RecordingSender.sentOrderIds |
| Mock | Object with specified and verified interaction expectations, often library-generated | Mockito mock(PaymentGateway.class) and verify(...) |

A test double can serve more than one role. StubGateway both supplies predetermined results and records call counts. Avoid forcing every double into a fixed label; choose tools that clearly express the contract under test.

**Mocks are not synonymous with unit tests.** The example uses hand-written fakes/spies, which suffice for simple interactions without Mockito. For many methods or complex interactions, a mocking library can reduce boilerplate, but verifying every internal call makes tests brittle under legitimate refactoring.

## 5. Dependency Substitution Points in OOP Design

### Constructor Injection (Preferred for Required Dependencies)

~~~java
// Ví dụ mẫu về cú pháp; các interface tương ứng phải được khai báo.
final class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }
}
~~~

Benefits: required dependencies are explicit; incomplete objects are harder to create; real and fake implementations are easy to supply; immutable collaborators fit naturally. Constructor injection works well for dependencies shared throughout an object's lifecycle.

### Method Injection (Useful for Per-Call Dependencies)

~~~java
import java.time.Clock;

final class DeadlinePolicy {
    boolean expired(java.time.Instant deadline, Clock clock) {
        return clock.instant().isAfter(deadline);
    }
}
~~~

A small policy can receive Clock as a parameter because time is an input to the operation. Avoid passing a long list of dependencies through every method when they truly belong to the class lifecycle; constructor injection is then clearer.

### Adapter / Ports and Adapters

In hexagonal architecture, PaymentGateway is a **port** required by the business; both the real HTTP client and a test stub are **adapters** satisfying that port. Source-code dependencies point toward the abstraction; the appropriate adapter is wired at runtime.

This also allows provider changes without rewriting checkout rules. Not every class needs its own interface, however: extracting an interface solely to mock a pure calculation with no I/O and no meaningful alternate provider usually makes the design more complex.

## 6. Designs That Make Tests Difficult and How to Improve Them

| Testability Problem | Consequence | Improvement |
| --- | --- | --- |
| Constructs HTTP client, repository, or SMTP client inside business code | Tests require real systems or hacks to replace objects | Inject port/interface through constructor |
| Calls Instant.now() / LocalDate.now() directly in business rules | Results vary with time | Inject Clock and call clock.instant() / LocalDate.now(clock) |
| Calls System.getenv() throughout business branches | Tests depend on machine configuration | Read configuration at the composition root; inject immutable values/config |
| Uses global singleton or static mutable state | Tests interfere with one another and parallel execution | Limit state to instances; define clear lifecycles/reset rules |
| One business method deeply invokes numerous external APIs | Failures are difficult to localize | Split responsibilities; isolate adapters and orchestration |
| Mocks every internal object | Tests depend on call order and implementation details | Verify observable outcomes; mock genuine boundaries |

Do not use interfaces to conceal a design problem. If testing one small method requires dozens of mocks, the class may have too many responsibilities (violating the Single Responsibility Principle).

## 7. Unit Tests Versus Integration Tests

The tests above establish CheckoutService's decisions **assuming dependencies honor their simulated contracts**. They do not prove that the real payment adapter formats requests correctly, email arrives, timeouts are handled, or the system recovers from outages.

Useful testing layers:

~~~mermaid
flowchart TD
    U["Unit test: CheckoutService + test doubles"] --> C["Quy tắc nghiệp vụ"]
    I["Integration test: adapter + dịch vụ test/database"] --> K["Giao thức, serialization, giao dịch"]
    E["End-to-end test: luồng ứng dụng thực"] --> H["Cấu hình và phối hợp toàn hệ thống"]
~~~

A real PaymentGateway needs integration/contract tests against the provider API, especially error codes, retries, and timeouts. Unit tests remain useful for fast, reproducible feedback on business branches. Do not infer real-adapter correctness from a fake.

## 8. Key Principles for Replacing Dependencies

1. **Control nondeterminism:** clocks, networks, randomness, files, and databases are good seam candidates when they affect tests. For randomness, inject a Random or a seeded generator if required by the contract.
2. **Control state:** every test uses clean doubles; avoid shared static mutable fixtures.
3. **Match fake behavior to the contract:** a fake that accepts more than the real API may make tests pass while production fails. Use integration tests for adapters and update fakes when contracts change.
4. **Test failure paths:** rejection, exceptions, missing data, and timeouts remain important even when the happy path passes.
5. **Do not fake the SUT itself:** to test CheckoutService, construct the real CheckoutService and replace external collaborators.
6. **Prefer business-significant assertions:** for example, do not send receipts after declined payments; do not verify every getter, setter, or internal call sequence by default.
7. **Separate application assembly from business logic:** the composition root chooses implementations, configuration, and lifecycles; services perform their own responsibilities.
8. **Do not require a DI framework:** creating new CheckoutService(fakeGateway, recordingSender, fixedClock) is already valid dependency injection.

## 9. Applied Exercises

**Exercise 1 — Persisting transactions.** Define TransactionRepository with save(...), injected through the constructor. Use RecordingRepository in tests to verify persistence occurs only when the gateway returns true. Specify what happens on persistence failures and test that behavior.

**Exercise 2 — Expiration time.** Add a checkout deadline. Use Clock.fixed(...) to test instants before, at, and after it; document which boundary is valid.

**Exercise 3 — Notification failure.** Make RecordingSender throw an exception. Observe that a payment may have succeeded despite checkout throwing. Propose persisting transaction state and publishing events or using a transactional outbox for safe resends, avoiding an additional charge.

**Self-assessment:** If you can construct a business class with controlled dependencies, exercise success/failure paths without real services, and still test real adapters separately, you have created a useful OOP test seam.
