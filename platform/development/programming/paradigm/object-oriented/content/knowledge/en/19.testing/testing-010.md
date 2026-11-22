# Testing Interactions Among Multiple Objects in Java OOP

## 1. Why Test Collaboration?

An object-oriented method rarely performs everything itself. It receives requests, invokes collaborators, processes their results, and decides the next steps. In a sales application, a checkout service may coordinate:

1. **Inventory** to reserve stock.
2. **PaymentGateway** to charge payments.
3. **ReceiptSender** to send receipts.

Each class can pass independent tests while the overall workflow is still wrong: a receipt is sent before payment, money is charged without stock, inventory is not released after payment rejection, or a charge is attempted twice. These are **object-interaction defects**.

**Interaction testing** verifies that objects invoke collaborators under the right conditions, with correct parameters and necessary call counts and ordering. **State-based testing** checks resulting data and state. These approaches complement each other; counting calls alone is not a substitute for verifying business outcomes.

After this lesson, you can:
- Identify object boundaries that need testing.
- Write tests for success, rejection, and failure paths.
- Use Mockito verify, never, verifyNoInteractions, and InOrder.
- Write collaboration tests with real in-memory objects.
- Distinguish ordering required by business rules from mere implementation details.

## 2. Define the Business Contract First

We implement CheckoutService. Each order has an ID, SKU, quantity, and positive VND amount. Rules:

| Scenario | Required Calls | Outcome |
| --- | --- | --- |
| Insufficient stock | inventory.reserve returns false; **do not** invoke payment or sender | OUT_OF_STOCK |
| Reservation and payment succeed | reserve → charge → send, each exactly once | PAID |
| Gateway declines payment | reserve → charge → release; no receipt | DECLINED |
| Gateway throws RuntimeException | reserve → charge → release; no receipt; propagate error | Exception |
| Null order | Do not call any collaborator | NullPointerException |
| Receipt sending fails after a charge | Propagate exception; do not charge again or release automatically | Exception (requires safe resend mechanism in real systems) |

The crucial conditions are **do not charge when reservation fails** and **do not send a receipt until payment is confirmed successful**.

Sequence overview:

~~~mermaid
sequenceDiagram
    actor Client
    participant C as CheckoutService
    participant I as Inventory
    participant P as PaymentGateway
    participant R as ReceiptSender
    Client->>C: checkout(order)
    C->>I: reserve(sku, quantity)
    alt Hết hàng
        I-->>C: false
        C-->>Client: OUT_OF_STOCK
    else Đã giữ hàng
        I-->>C: true
        C->>P: charge(orderId, amountVnd)
        alt Thanh toán bị từ chối
            P-->>C: false
            C->>I: release(sku, quantity)
            C-->>Client: DECLINED
        else Thanh toán thành công
            P-->>C: true
            C->>R: send(orderId)
            C-->>Client: PAID
        end
    end
~~~

The diagram shows the normal path. Test exceptional paths separately because each dependency can fail differently.

## 3. Java 17 + Maven + JUnit 5 + Mockito Project

The project uses Java 17 for records, JUnit Jupiter for tests, and Mockito for verifying calls. Spring is not required.

~~~text
oop-collaboration-tests/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── Inventory.java
    │   ├── PaymentGateway.java
    │   ├── ReceiptSender.java
    │   └── CheckoutService.java
    └── test/java/vn/example/
        ├── CheckoutServiceTest.java
        └── CheckoutCollaborationTest.java
~~~

### 3.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>oop-collaboration-tests</artifactId>
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
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-junit-jupiter</artifactId>
            <version>5.14.2</version>
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

### 3.2. Three Collaborator Interfaces

**src/main/java/vn/example/Inventory.java**

~~~java
package vn.example;

public interface Inventory {
    /** true nếu giữ đủ số lượng; false nếu không thể giữ. */
    boolean reserve(String sku, int quantity);

    /** Hoàn lại đúng số lượng đã giữ. */
    void release(String sku, int quantity);
}
~~~

**src/main/java/vn/example/PaymentGateway.java**

~~~java
package vn.example;

public interface PaymentGateway {
    /** true: chấp nhận thanh toán; false: từ chối. */
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/vn/example/ReceiptSender.java**

~~~java
package vn.example;

public interface ReceiptSender {
    void send(String orderId);
}
~~~

These interfaces expose only the capabilities CheckoutService needs. The consumer does not care whether stock is stored in SQL or memory, the payment gateway uses HTTP or a fake, or the sender uses SMTP or a queue.

### 3.3. Real Orchestrating Class

**src/main/java/vn/example/CheckoutService.java**

~~~java
package vn.example;

import java.util.Objects;

public final class CheckoutService {
    private final Inventory inventory;
    private final PaymentGateway gateway;
    private final ReceiptSender sender;

    public CheckoutService(
            Inventory inventory,
            PaymentGateway gateway,
            ReceiptSender sender) {
        this.inventory = Objects.requireNonNull(inventory, "inventory");
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    public record Order(
            String orderId,
            String sku,
            int quantity,
            long amountVnd) {

        public Order {
            if (orderId == null || orderId.isBlank()
                    || sku == null || sku.isBlank()
                    || quantity <= 0 || amountVnd <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
        }
    }

    public enum Outcome {
        OUT_OF_STOCK, DECLINED, PAID
    }

    public Outcome checkout(Order order) {
        Objects.requireNonNull(order, "order");

        if (!inventory.reserve(order.sku(), order.quantity())) {
            return Outcome.OUT_OF_STOCK;
        }

        final boolean accepted;
        try {
            accepted = gateway.charge(
                    order.orderId(), order.amountVnd());
        } catch (RuntimeException failure) {
            inventory.release(order.sku(), order.quantity());
            throw failure;
        }

        if (!accepted) {
            inventory.release(order.sku(), order.quantity());
            return Outcome.DECLINED;
        }

        sender.send(order.orderId());
        return Outcome.PAID;
    }
}
~~~

Notable points:

- **CheckoutService is the real system under test**. Its three collaborators are constructor-injected.
- The Order object protects its own data invariants; tests cannot put a negative quantity into a valid Order.
- On insufficient stock, return immediately, so PaymentGateway and ReceiptSender must never be invoked.
- If the gateway declines, release occurs **after** charge. If the gateway throws RuntimeException, release also occurs before propagating the error.
- The try block surrounds only charge, so an exception from release is not caught again to trigger a second release.
- Sender failures after successful charging propagate; the service **does not** try to reverse the payment. This is an intentional simplification to clarify cross-system consistency.

**Real-world payment caveat:** a gateway network failure may leave uncertainty about whether funds were charged. The demo's rule of releasing inventory when the gateway throws is a simplified teaching assumption, not a safe production payment workflow. Real systems need idempotency keys, status reconciliation, compensation, and reliable coordination of order state.

## 4. Interaction Unit Tests with Mockito

Mockito creates collaborators whose responses can be controlled and calls recorded. Tests instantiate a **real CheckoutService**, never mock CheckoutService itself.

**src/test/java/vn/example/CheckoutServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {
    private static final CheckoutService.Order ORDER =
            new CheckoutService.Order("O-1", "SKU-1", 2, 100_000);

    @Mock Inventory inventory;
    @Mock PaymentGateway gateway;
    @Mock ReceiptSender sender;

    private CheckoutService service;

    @BeforeEach
    void setUp() {
        service = new CheckoutService(inventory, gateway, sender);
    }

    @Test
    void successCallsCollaboratorsInBusinessOrder() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(gateway.charge("O-1", 100_000)).thenReturn(true);

        CheckoutService.Outcome result = service.checkout(ORDER);

        assertEquals(CheckoutService.Outcome.PAID, result);
        InOrder calls = inOrder(inventory, gateway, sender);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(sender).send("O-1");
        calls.verifyNoMoreInteractions();
    }

    @Test
    void outOfStockStopsBeforePaymentAndReceipt() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(false);

        CheckoutService.Outcome result = service.checkout(ORDER);

        assertEquals(CheckoutService.Outcome.OUT_OF_STOCK, result);
        verify(inventory).reserve("SKU-1", 2);
        verifyNoMoreInteractions(inventory);
        verifyNoInteractions(gateway, sender);
    }

    @Test
    void declinedPaymentReleasesInventoryWithoutReceipt() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(gateway.charge("O-1", 100_000)).thenReturn(false);

        CheckoutService.Outcome result = service.checkout(ORDER);

        assertEquals(CheckoutService.Outcome.DECLINED, result);
        InOrder calls = inOrder(inventory, gateway);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(inventory).release("SKU-1", 2);
        calls.verifyNoMoreInteractions();
        verifyNoInteractions(sender);
    }

    @Test
    void gatewayFailureReleasesInventoryAndPropagatesError() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        IllegalStateException failure =
                new IllegalStateException("Gateway unavailable");
        when(gateway.charge("O-1", 100_000)).thenThrow(failure);

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                () -> service.checkout(ORDER));

        assertSame(failure, actual);
        InOrder calls = inOrder(inventory, gateway);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(inventory).release("SKU-1", 2);
        calls.verifyNoMoreInteractions();
        verifyNoInteractions(sender);
    }

    @Test
    void receiptFailureIsNotTreatedAsPaymentFailure() {
        when(inventory.reserve("SKU-1", 2)).thenReturn(true);
        when(gateway.charge("O-1", 100_000)).thenReturn(true);
        doThrow(new IllegalStateException("Mail unavailable"))
                .when(sender).send("O-1");

        assertThrows(IllegalStateException.class,
                () -> service.checkout(ORDER));

        InOrder calls = inOrder(inventory, gateway, sender);
        calls.verify(inventory).reserve("SKU-1", 2);
        calls.verify(gateway).charge("O-1", 100_000);
        calls.verify(sender).send("O-1");
        calls.verifyNoMoreInteractions();
        verify(inventory, never()).release(anyString(), anyInt());
    }

    @Test
    void nullOrderDoesNotTouchCollaborators() {
        assertThrows(NullPointerException.class,
                () -> service.checkout(null));
        verifyNoInteractions(inventory, gateway, sender);
    }

    @Test
    void constructorRequiresAllCollaborators() {
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(null, gateway, sender));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(inventory, null, sender));
        assertThrows(NullPointerException.class,
                () -> new CheckoutService(inventory, gateway, null));

        verifyNoInteractions(inventory, gateway, sender);
    }
}
~~~

### Understanding Verification Calls

| Testing API | Meaning | When to Use |
| --- | --- | --- |
| when(...).thenReturn(...) | Configure mock response for a scenario | Stock available/unavailable; payment approved/declined |
| when(...).thenThrow(...) | Simulate collaborator exception | Payment provider failure |
| doThrow(...).when(sender).send(...) | Simulate an exception from a void method | Receipt notification failure |
| verify(mock).method(args) | By default, require exactly one matching call | Parameters passed to inventory and gateway |
| verify(mock, never()).method(...) | Verify a particular call never occurs | No release after a successful charge followed only by email failure |
| verifyNoInteractions(mock) | No interactions with a mock | Out-of-stock branch never touches gateway/sender |
| inOrder(a, b, c) | Verify order of required business calls | Reserve before charging, charge before sending |
| assertEquals / assertThrows | Verify public results and exceptions | Avoid tests containing only verify calls |

**Caution:** Mockito defaults unstubbed booleans to false. Thus the out-of-stock case could run when Inventory is accidentally left unstubbed, producing a misleading green test. Explicitly configure each branch's necessary responses as in the example.

**Interaction order is a design decision.** If operations are independent with no promised ordering, use ordinary verify rather than InOrder. Fix ordering only for steps where reordering would violate business rules.

## 5. Collaboration Tests with Real In-Memory Objects

Mocks can establish that CheckoutService **called** release, but cannot establish that stock was actually returned. To test state after a call sequence, combine real objects and in-memory implementations with explicit behavior.

**src/test/java/vn/example/CheckoutCollaborationTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CheckoutCollaborationTest {

    private static final CheckoutService.Order ORDER =
            new CheckoutService.Order("O-1", "SKU-1", 2, 100_000);

    @Test
    void successfulWorkflowUpdatesRealInMemoryState() {
        InMemoryInventory inventory = new InMemoryInventory();
        RecordingSender sender = new RecordingSender();

        // Hàm lambda này là implementation của PaymentGateway.
        PaymentGateway gateway = (orderId, amountVnd) -> true;
        CheckoutService service =
                new CheckoutService(inventory, gateway, sender);

        assertEquals(CheckoutService.Outcome.PAID,
                service.checkout(ORDER));
        assertEquals(3, inventory.available("SKU-1"));
        assertEquals(List.of("O-1"), sender.sent);
    }

    @Test
    void rejectedPaymentRestoresStockWithoutNotification() {
        InMemoryInventory inventory = new InMemoryInventory();
        RecordingSender sender = new RecordingSender();
        PaymentGateway gateway = (orderId, amountVnd) -> false;
        CheckoutService service =
                new CheckoutService(inventory, gateway, sender);

        assertEquals(CheckoutService.Outcome.DECLINED,
                service.checkout(ORDER));
        assertEquals(5, inventory.available("SKU-1"));
        assertTrue(sender.sent.isEmpty());
    }

    private static final class InMemoryInventory implements Inventory {
        private final Map<String, Integer> stock = new HashMap<>();

        InMemoryInventory() {
            stock.put("SKU-1", 5);
        }

        @Override
        public boolean reserve(String sku, int quantity) {
            int current = stock.getOrDefault(sku, 0);
            if (current < quantity) {
                return false;
            }
            stock.put(sku, current - quantity);
            return true;
        }

        @Override
        public void release(String sku, int quantity) {
            stock.merge(sku, quantity, Integer::sum);
        }

        int available(String sku) {
            return stock.getOrDefault(sku, 0);
        }
    }

    private static final class RecordingSender implements ReceiptSender {
        final List<String> sent = new ArrayList<>();

        @Override
        public void send(String orderId) {
            sent.add(orderId);
        }
    }
}
~~~

Here, InMemoryInventory is a stateful fake, while RecordingSender is a spy recording side effects. These two tests need no Mockito: inventory state and sent-record lists provide evidence of collaboration outcomes. They still do not connect to production inventory or payment systems, so they are not full infrastructure integration tests.

### 5.1. Run the Entire Lesson

In the directory containing pom.xml, use JDK 17 or a newer version compatible with Maven:

~~~bash
mvn test
~~~

The two test classes contain **9 @Test methods**: 7 mock-interaction tests and 2 in-memory collaboration tests. With the code entered as shown and appropriate Maven dependencies, expect 9 passes, with no failures/errors. Every test uses its own fixture to avoid order dependencies.

## 6. Distinguishing Test Levels

| Level | Real Components Executed | Dependencies Replaced | Main Guarantee |
| --- | --- | --- | --- |
| Unit + interaction test | CheckoutService | Mock Inventory, Gateway, Sender | Conditions, parameters, ordering, counts, and exceptions |
| Unit/collaboration test | CheckoutService, InMemoryInventory, RecordingSender | Gateway returns fixed result | In-memory state changes across objects |
| Integration test | JDBC/API adapters and test services | Only some external systems | Mapping, transactions, configuration, infrastructure contracts |
| End-to-end test | Application workflow close to reality | May use a sandbox to avoid real charges | End-to-end component coordination |

Test-level terminology can vary across teams. More important than the label is documenting which components actually ran, which were simulated, and what the test did not establish.

Production systems also need tests for inventory adapters under concurrent updates, payments with timeouts, and notification systems with slow or duplicate queue delivery. Mockito alone cannot establish that real systems satisfy their contracts.

## 7. Common Multi-Object Testing Mistakes

### 7.1. Checking Calls but Not Results

~~~java
// Chưa đủ: chỉ biết charge đã được gọi.
verify(gateway).charge("O-1", 100_000);
~~~

Combine result assertions (PAID/DECLINED) with resulting state, such as inventory. Correct call parameters can still yield wrong outcomes if an orchestrator ignores return values.

### 7.2. Mocking the Object Under Test

Mocking CheckoutService and making checkout return PAID only verifies Mockito's configuration, not the business branch. Instantiate a real CheckoutService and substitute collaborators outside the boundary under test.

### 7.3. Verifying Every Internal Detail

Overly detailed tests can break after valid refactoring. For example, adding a logging step may cause a hardcoded list of calls to produce false alarms. Verify only interactions belonging to **business contracts** or those preventing dangerous effects such as duplicate charges.

### 7.4. Tests Depend on Shared Data

If a fake inventory is a singleton shared across tests, an earlier test's stock reduction affects later tests. Create a fresh fake per test; real-DB integration tests need suitable data isolation or rollback/cleanup.

### 7.5. Ambiguous Handling of Failures Across Objects

PaymentGateway throwing does not necessarily mean payment was declined: the gateway may have received the charge but lost its response. Do not infer business outcomes from technical exceptions without a defined contract. Real payment systems need reconciliation, idempotency keys, durable progress records, and safe retries.

Failure to send a receipt is also not a reason to charge again automatically. Transactional outbox or durable events may be needed for safe resend. Specify those decisions as contracts and test matching scenarios.

## 8. Designing for Testable Interactions

1. **Small role-specific interfaces:** Inventory, PaymentGateway, and ReceiptSender expose only operations needed by the workflow.
2. **Constructor injection:** receive collaborators from outside rather than constructing them internally or accessing global singletons.
3. **Separate orchestration from I/O:** CheckoutService chooses ordering while adapters handle external communication.
4. **Explicit outcome models:** the Outcome enum distinguishes success, out-of-stock, and payment-declined branches so tests do not infer outcomes from null.
5. **Distinguish false results from exceptions:** business rejection differs from technical failure; recovery policies may differ.
6. **Recognize side-effect boundaries:** charge, release, and send are sensitive interactions requiring careful tests because they change the outside world.
7. **Combine state and ordering tests:** collaboration is correct only when final results are correct too.
8. **Use fakes/mocks deliberately:** mocks verify interactions, fakes model state changes, and real adapters need separate integration tests.

## 9. Practice Exercises

**Exercise 1 — Catch ordering errors.** Deliberately move sender.send(...) before gateway.charge(...). Rerun tests and identify the failing cases. Restore the correct order and explain its business significance.

**Exercise 2 — Catch duplicate calls.** Deliberately invoke gateway.charge(...) twice on the successful path. Verify that InOrder/verifyNoMoreInteractions detects the extra call, then restore correct code.

**Exercise 3 — Add an out-of-stock collaboration test.** Add a test to CheckoutCollaborationTest for an order requesting 6 items when inventory contains only 5. Expect OUT_OF_STOCK, unchanged stock of 5, and no receipt.

**Exercise 4 — Add a durable event.** Simulate EventPublisher and extend the workflow to publish OrderPaid after successful payment. Specify ordering between persisted payment state and event publication; use mocks to verify order and a fake repository to check final state.

**Self-assessment criterion:** A good multi-object interaction test makes clear **who calls whom, when, with which data, and which side effects must occur or be prohibited**, while also proving observable user-facing results or business state.
