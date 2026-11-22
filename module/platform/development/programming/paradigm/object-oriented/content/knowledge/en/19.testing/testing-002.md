# Testing Constructors and Invalid States in OOP

**Topic:** OOP → Testing → **Testing constructors and invalid states**  
**Example environment:** Java 17+, JUnit Jupiter 5 (and `junit-jupiter-params` for parameterized tests).

## 1. Why Test a Constructor That “Only Assigns Fields”?

Consider a class representing an invoice. For an invoice to be meaningful, it must guarantee:

- A **nonblank customer ID**.
- **At least one line item**.
- Every line item has a valid product ID, nonnegative unit price, and positive quantity.
- **Merchandise subtotal** is calculated without overflowing `long`.
- **Discount** is nonnegative and does not exceed the merchandise subtotal.
- After creation, the caller cannot mutate the original list and thereby change the constructed invoice.

If a constructor accepts everything without validation, it can create an object with `discountVnd > subtotalVnd`, no line items, or even a negative payable amount. The error may not surface when `new` runs, but later during database persistence, tax calculation, or refunds.

**A constructor is a boundary that protects an object's invariants.** When a constructor returns normally, callers may trust that the resulting object satisfies its published guarantees. Invalid data should cause the constructor to **reject object creation** through a clear error mechanism.

Not every constructor needs elaborate logic: a simple value object with two fields may require very little validation. But once a class declares invariants, **testing its constructor verifies that the contract holds from the moment the object exists**.

### Three Core Questions

1. **Valid case:** Are fields correct after creation? Are defaults and normalization applied correctly?
2. **Invalid case:** Which inputs must be rejected? What exception type applies? Can an incorrect observable state escape?
3. **After initialization:** Does the object remain valid if mutable input or a shared reference changes?

A test asserting that `new Invoice(...)` merely “does not throw” is insufficient when construction also calculates totals, normalizes values, or snapshots inputs.

## 2. Distinguishing Preconditions, Postconditions, and Invariants

| Concept | Question to Ask | Example |
| --- | --- | --- |
| **Precondition** | Is the input valid when invoking the constructor? | `quantity > 0`; `customerId` is not blank |
| **Postcondition** | After successful construction, is the object initialized correctly? | `total = subtotal - discount` |
| **Invariant** | What must always hold whenever the object is observable? | `0 <= discount <= subtotal`, `total >= 0` |
| **Ownership/aliasing** | Does the object own its data or share mutable references? | Mutating the caller's `ArrayList` does not change the invoice |
| **Failure contract** | How does construction respond to violations? | `IllegalArgumentException` for invalid values, `NullPointerException` for required null references (if the contract chooses this) |
| **Failure atomicity** | Can side effects remain when construction fails? | Do not send email or write external data merely because `new` was attempted |

Compare these three cases:

~~~text
Input hợp lệ:
  Invoice("CUS-01", [2 sách × 125000], discount=20000)
  → subtotal=250000, total=230000

Input không hợp lệ:
  Invoice("CUS-01", [2 sách × 125000], discount=300000)
  → ném IllegalArgumentException; không trả Invoice

Trạng thái bị phá sau tạo nếu thiết kế sai:
  Invoice giữ trực tiếp List mutable của caller
  → caller.clear() → hóa đơn trở thành rỗng
~~~

**“No object is returned” does not mean Java automatically rolls back every side effect** performed inside a constructor. If construction registers `this` with a listener, publishes an event, or writes to a DB before validation finishes, those effects may persist. Avoid such designs, and test side-effect boundaries when genuinely necessary.

## 3. Build a Test Matrix Before Writing Tests

A good matrix specifies **valid cases, boundaries, rejected inputs, and post-call outcomes**:

| Group | Input | Expected Outcome |
| --- | --- | --- |
| Normal | Valid ID and one or more valid items | Construction succeeds, preserving correct data |
| Normalization | ID `"  CUS-01  "` | `customerId()` returns `"CUS-01"` |
| Invalid ID | `null`, `""`, or whitespace only | `IllegalArgumentException` |
| Invalid list | `null` or empty list | Rejected by contract (e.g., `NullPointerException`, `IllegalArgumentException`) |
| Invalid element | List contains `null` | Rejected; no invoice created |
| Invalid line item | 0/negative quantity, negative price, blank SKU | Rejected by `LineItem` |
| Lower discount boundary | `discount = 0` | Valid |
| Upper discount boundary | `discount = subtotal` | Valid; final total = 0 |
| Discount beyond boundary | `discount = subtotal + 1` | `IllegalArgumentException` |
| Arithmetic overflow | `unitPrice × quantity` exceeds `long` | `ArithmeticException` |
| Aliasing | Modify source list after construction | Invoice does not change |
| Accessor protection | Call `invoice.lines().clear()` | `UnsupportedOperationException` |
| State after failure | Construction fails or an operation is rejected | No invalid object is returned; existing state still obeys the contract |

**Select exception types according to the contract**; all invalid inputs need not produce the same exception. For example, `Objects.requireNonNull(...)` throws `NullPointerException`, while negative quantity is typically reported with `IllegalArgumentException`.

## 4. Complete Java 17 Example: Constructor-Enforced Invariants

Create **ConstructorInvariantDemo.java**. This example uses a `record` for an immutable line item, an `Invoice` class whose constructor validates cross-field constraints, `Math.addExact/multiplyExact` to prevent silent overflow, and `List.copyOf` to separate the invoice from the caller's mutable list.

~~~java
import java.util.List;
import java.util.Objects;

public class ConstructorInvariantDemo {

    // Value object: không có setter; mỗi dòng được validate riêng.
    public record LineItem(
            String sku,
            long unitPriceVnd,
            int quantity) {

        public LineItem {
            sku = requiredText(sku, "sku");

            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                        "unitPriceVnd không được âm");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity phải dương");
            }
        }

        public long lineTotalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    public static final class Invoice {
        private final String customerId;
        private final List<LineItem> lines;
        private final long subtotalVnd;
        private final long discountVnd;
        private final long totalVnd;

        public Invoice(
                String customerId,
                List<LineItem> lines,
                long discountVnd) {

            // Xác thực và tính toán trên biến cục bộ trước khi gán field.
            String normalizedId = requiredText(
                    customerId, "customerId");

            Objects.requireNonNull(lines, "lines");
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "Hóa đơn cần ít nhất một dòng hàng");
            }

            // Tránh giữ tham chiếu tới ArrayList mutable của caller.
            // List.copyOf cũng từ chối phần tử null.
            List<LineItem> snapshot = List.copyOf(lines);

            long subtotal = 0;
            for (LineItem line : snapshot) {
                subtotal = Math.addExact(
                        subtotal, line.lineTotalVnd());
            }

            if (discountVnd < 0 || discountVnd > subtotal) {
                throw new IllegalArgumentException(
                        "Giảm giá phải nằm trong [0, subtotal]");
            }

            long total = Math.subtractExact(subtotal, discountVnd);

            // Chỉ thiết lập state sau khi toàn bộ điều kiện đã qua.
            this.customerId = normalizedId;
            this.lines = snapshot;
            this.subtotalVnd = subtotal;
            this.discountVnd = discountVnd;
            this.totalVnd = total;
        }

        public String customerId() {
            return customerId;
        }

        public List<LineItem> lines() {
            return lines;
        }

        public long subtotalVnd() {
            return subtotalVnd;
        }

        public long discountVnd() {
            return discountVnd;
        }

        public long totalVnd() {
            return totalVnd;
        }
    }

    private static String requiredText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " không được null/rỗng");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        var invoice = new Invoice(
                "  CUS-01  ",
                List.of(
                        new LineItem("BOOK-1", 125_000L, 2),
                        new LineItem("PEN-1", 35_000L, 1)
                ),
                20_000L
        );

        System.out.println(invoice.customerId());
        System.out.println(invoice.subtotalVnd());
        System.out.println(invoice.totalVnd());
        System.out.println(invoice.lines().size());
    }
}
~~~

Run:

~~~bash
javac ConstructorInvariantDemo.java
java ConstructorInvariantDemo
~~~

Output:

~~~text
CUS-01
285000
265000
2
~~~

### Why Validate Before Assigning Fields?

In `Invoice`, the customer ID is normalized, the list validated and copied, and the subtotal calculated before assigning the `final` fields. If an item is missing or a discount exceeds the subtotal, no `Invoice` is returned to the client.

Java does not require the constructor to assign `final` fields in the exact sequence shown, but **calculating and validating with local variables before publishing the object** makes invariants easier to inspect and reduces the risk of leaking `this` during initialization. Avoid calling overridable virtual methods, registering listeners, or passing `this` to another thread from a constructor.

For mutable data structures, `List.copyOf` creates a list that cannot be modified through the returned reference and is detached from the caller's original mutable `ArrayList`. This is a **shallow copy of the elements**: if a `LineItem` contains a mutable object, a caller holding another reference to that element may still modify it. Here, `LineItem` uses `String`, `long`, and `int`, so the example has no mutable-element problem.

### Why Not Use Setters to Complete Construction?

The following approach allows invalid intermediate states:

~~~java
// Chỉ minh họa anti-pattern: không có validation tại ranh giới tạo.
Invoice invoice = new Invoice();
invoice.setCustomerId("CUS-01");
invoice.setDiscountVnd(500_000L);
// Ở đây chưa chắc tồn tại dòng hàng nào!
~~~

The complete example's `Invoice` **has no no-argument constructor or setters**; clients receive an object only after providing all required valid data. UI form objects and framework-managed entities may have different lifecycles, but their **incomplete** states should then be distinguished from **valid domain** states, not treated as equivalent.

## 5. JUnit 5: Testing Valid Paths and Boundary Values

Create **ConstructorInvariantDemoTest.java** (in the same package as the class above). The tests use JUnit Jupiter and the `junit-jupiter-params` module.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class ConstructorInvariantDemoTest {

    private static ConstructorInvariantDemo.LineItem item(
            long price, int quantity) {
        return new ConstructorInvariantDemo.LineItem(
                "BOOK-1", price, quantity);
    }

    private static ConstructorInvariantDemo.Invoice invoice(
            String customerId, List<ConstructorInvariantDemo.LineItem> lines,
            long discount) {
        return new ConstructorInvariantDemo.Invoice(
                customerId, lines, discount);
    }

    @Test
    void validInvoiceComputesTotalsAndNormalizesId() {
        var result = invoice(
                "  CUS-01 ",
                List.of(item(125_000L, 2), item(35_000L, 1)),
                20_000L);

        assertAll(
                () -> assertEquals("CUS-01", result.customerId()),
                () -> assertEquals(285_000L, result.subtotalVnd()),
                () -> assertEquals(20_000L, result.discountVnd()),
                () -> assertEquals(265_000L, result.totalVnd()),
                () -> assertEquals(2, result.lines().size())
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   ", "\t"})
    void invalidCustomerIdIsRejected(String invalidId) {
        assertThrows(IllegalArgumentException.class, () ->
                invoice(invalidId, List.of(item(100L, 1)), 0L));
    }

    @Test
    void emptyAndNullLinesAreRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                invoice("CUS", List.of(), 0L));

        assertThrows(NullPointerException.class, () ->
                invoice("CUS", null, 0L));
    }

    @Test
    void nullElementIsRejected() {
        var source =
                new ArrayList<ConstructorInvariantDemo.LineItem>();
        source.add(item(10L, 1));
        source.add(null);

        assertThrows(NullPointerException.class, () ->
                invoice("CUS", source, 0L));
    }

    @Test
    void discountBoundariesAreClear() {
        var goods = List.of(item(100L, 2)); // subtotal = 200

        assertEquals(200L,
                invoice("CUS", goods, 0L).totalVnd());
        assertEquals(0L,
                invoice("CUS", goods, 200L).totalVnd());

        assertThrows(IllegalArgumentException.class, () ->
                invoice("CUS", goods, -1L));
        assertThrows(IllegalArgumentException.class, () ->
                invoice("CUS", goods, 201L));
    }

    @Test
    void invalidLineItemIsRejectedAtConstruction() {
        assertThrows(IllegalArgumentException.class, () ->
                item(-1L, 1));
        assertThrows(IllegalArgumentException.class, () ->
                item(100L, 0));
        assertThrows(IllegalArgumentException.class, () ->
                new ConstructorInvariantDemo.LineItem(
                        "  ", 100L, 1));
    }

    @Test
    void overflowIsRejectedInsteadOfWrapping() {
        assertThrows(ArithmeticException.class, () ->
                invoice("CUS", List.of(
                        item(Long.MAX_VALUE, 2)), 0L));

        assertThrows(ArithmeticException.class, () ->
                invoice("CUS", List.of(
                        item(Long.MAX_VALUE, 1),
                        item(1L, 1)), 0L));
    }

    @Test
    void sourceListMutationCannotChangeInvoice() {
        var source =
                new ArrayList<ConstructorInvariantDemo.LineItem>();
        source.add(item(100L, 1));
        var result = invoice("CUS", source, 0L);

        source.clear();
        assertEquals(1, result.lines().size());
        assertEquals(100L, result.totalVnd());

        assertThrows(UnsupportedOperationException.class, () ->
                result.lines().add(item(1L, 1)));
    }
}
~~~

Tests are named after **behavior**, not internal field names. For example, `discountBoundariesAreClear` immediately communicates the rule “0 and subtotal are valid; values outside this range are rejected,” unlike a generic name such as `testConstructor3`.

### Why Each Test Type Matters

- **Happy path:** verify outputs and normalization, not merely “does not throw.”
- **Null/empty/blank:** distinguish null references, empty strings, and whitespace-only strings.
- **Boundary:** test the exact edges `0`, `subtotal`, `-1`, and `subtotal + 1`; mistakes involving `<`/`<=` are easy to make.
- **Nested invalid input:** an `Invoice` is valid only when its `LineItem` instances are valid. Validation at each level forms a chain of contracts.
- **Overflow:** `Math.multiplyExact` or `Math.addExact` explicitly handles a guarantee that ordinary `long` arithmetic does not provide.
- **Aliasing:** prove the object does not change when callers modify the source list.
- **Accessor:** prove the returned reference cannot let callers break invariants by manipulating the list.

**Note:** The example's unit tests require only JUnit Jupiter. JUnit is not included in the JDK by default, so add it as a test dependency. Demo and test files may share a package; if they use different packages, visibility/imports must be adjusted.

## 6. Testing Invalid States *After* Successful Construction

Constructors are not the only concern: an initially valid object can later be corrupted through a method. For mutable objects, update operations must also preserve invariants.

For example, a wallet/limit-management class may be created with a valid balance, but an operation that deducts more than the available amount must be rejected **without changing the balance**:

~~~java
public final class Wallet {
    private long balanceVnd;

    public Wallet(long initialBalanceVnd) {
        if (initialBalanceVnd < 0) {
            throw new IllegalArgumentException(
                    "Số dư ban đầu không được âm");
        }
        this.balanceVnd = initialBalanceVnd;
    }

    public long balanceVnd() {
        return balanceVnd;
    }

    public void debit(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException(
                    "Số tiền phải dương");
        }
        if (amountVnd > balanceVnd) {
            throw new IllegalStateException(
                    "Không đủ số dư");
        }

        balanceVnd = Math.subtractExact(balanceVnd, amountVnd);
    }
}
~~~

This is a separate class, saved as **Wallet.java** if run independently. To illustrate testing:

~~~java
@Test
void failedDebitMustPreserveValidState() {
    Wallet wallet = new Wallet(100L);

    assertThrows(IllegalStateException.class, () ->
            wallet.debit(101L));

    assertEquals(100L, wallet.balanceVnd());
}

@Test
void constructorRejectsNegativeInitialBalance() {
    assertThrows(IllegalArgumentException.class, () ->
            new Wallet(-1L));
}
~~~

The two tests above are methods in a JUnit test class with `import static org.junit.jupiter.api.Assertions.*;` and `import org.junit.jupiter.api.Test;`.

**Meaning:** Instead of forcing a valid `Wallet` into a negative state through reflection and then testing a different method, test **the public usage path capable of producing the error**. If invariants are protected correctly, no public API can create a negative balance.

The Wallet example is not thread-safe; concurrent operations may race on `balanceVnd`. Real-money systems also need appropriate transactions, idempotency, and authorization. A passing constructor test does not establish that the object's entire lifecycle is safe under concurrency.

## 7. Do Not Test by Arbitrarily Breaking Invariants

Sometimes we want to “create an invalid object and pass it to a service” to see how the service responds. But if the constructor rejects invalid objects, that is **correct design**.

An example to avoid in ordinary business unit tests:

~~~java
// Không nên dùng reflection chỉ để vượt constructor:
// Field f = Invoice.class.getDeclaredField("discountVnd");
// f.setAccessible(true);
// f.setLong(invoice, -99L);
~~~

That approach ties the test to private structure and violates the invariant that the class promises to protect. Renaming the field during refactoring can break the test even though public behavior is unchanged.

**Instead, introduce failures at the right boundary:**

- If a user submits invalid JSON, test **request validation/deserialization**.
- If the database contains invalid legacy data, test **persistence mapping/migration** or a state-recovery adapter.
- If a service depends on a collaborator that may fail, use a fake or mock that returns errors according to the dependency contract.
- If testing recovery from old snapshots, use **a controlled internal test fixture API** rather than exposing public setters on domain objects.

The key is **testing where an error can actually arise**, instead of manufacturing a state the API forbids.

## 8. Multistep Constructors: Ensure Failures Leave No Side Effects

A dangerous constructor may perform work beyond initializing state:

~~~java
// Anti-pattern minh họa: side effect trước khi validate xong.
class BadRegistration {
    BadRegistration(EventBus bus, String email) {
        bus.publish("RegistrationStarted");
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email sai");
        }
    }
}
~~~

With an invalid email, the caller never receives a valid `BadRegistration`, **but the event may already have been published**. A listener may have persisted data, sent email, or created an incorrect business log.

A clearer design:

1. Constructors/factories create **valid** value objects with minimal side effects.
2. An application service coordinates transactions, persistence, and events/outbox according to the requirements.
3. If any step fails, define separate handling, rollback, or compensation.
4. Test side effects through fakes to verify invalid input **does not invoke collaborators**.

Example service that creates a registration request:

~~~java
record RegistrationRequest(String email) {
    RegistrationRequest {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email sai");
        }
        email = email.trim();
    }
}

interface RegistrationGateway {
    void submit(RegistrationRequest request);
}

final class RegistrationService {
    private final RegistrationGateway gateway;

    RegistrationService(RegistrationGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    void register(String email) {
        RegistrationRequest request = new RegistrationRequest(email);
        gateway.submit(request);
    }
}
~~~

Now `RegistrationRequest` rejects invalid input before `submit()` executes. Tests can use a fake to count gateway calls and verify invalid input produces no side effects. The implementation still needs gateway-error handling and contract-based retries; validation alone does not create cross-network transactions.

## 9. A Fake for Verifying “No Dependency Call on Invalid Input”

The types above can share a package. An illustrative JUnit test:

~~~java
@Test
void invalidRegistrationDoesNotCallGateway() {
    class RecordingGateway implements RegistrationGateway {
        int calls;

        @Override
        public void submit(RegistrationRequest request) {
            calls++;
        }
    }

    RecordingGateway fake = new RecordingGateway();
    RegistrationService service = new RegistrationService(fake);

    assertThrows(IllegalArgumentException.class, () ->
            service.register("  "));

    assertEquals(0, fake.calls);
}
~~~

This snippet belongs inside a test class with the corresponding JUnit imports. It verifies **external behavior** (no request sent for invalid input), not a private field merely because that field exists.

## 10. Records, Builders, and Inheritance: Beyond Ordinary Constructors

### 10.1. Compact Record Constructors

Java `record` generates a canonical constructor automatically; validation can be added through a **compact constructor**:

~~~java
record Age(int years) {
    Age {
        if (years < 0 || years > 150) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
    }
}
~~~

Tests should accept `0` and `150`, while rejecting `-1` and `151`. Records **do not validate automatically** without explicit validation code. They are also only **shallowly immutable**: components holding a mutable `List` or array can expose mutable observable state without defensive handling.

### 10.2. A Builder Must Not Bypass Product Invariants

~~~java
Invoice invoice = Invoice.builder()
        .customerId("CUS-01")
        .addLine(...)
        .discountVnd(200_000L)
        .build();
~~~

This is a **hypothetical Builder API illustration**, not an API currently present in `ConstructorInvariantDemo.Invoice`. When a Builder creates an object, `discount <= subtotal` must still be enforced in `build()` or by the Product constructor/factory. Test missing fields, defaults, and invalid combinations; individual valid setters do not imply a valid Builder result.

### 10.3. Inheritance and Overridable Method Calls

Calling an overridable method from a constructor may run the subclass implementation **before the subclass's own fields are fully initialized**:

~~~java
class Base {
    Base() {
        initialize(); // Nguy cơ dispatch tới override.
    }

    void initialize() {}
}

class Child extends Base {
    private String name = "ready";

    @Override
    void initialize() {
        // Ở thời điểm Base() gọi, name chưa được gán "ready".
        System.out.println(name); // null
    }
}
~~~

Therefore, avoid relying on subclass overrides to complete constructor invariants. Tests of a subclass can catch this bug, but **a better design** keeps initialization inside constructors/factories without virtual dispatch and performs subtype-dependent steps after the object is fully initialized.

Do not register `this` with a callback or thread inside a constructor: other code may observe the object too early, before its fields are safely initialized.

## 11. Testing Invalid Combinations of State

Individual fields can be valid while **their combination** is invalid. Consider an appointment:

- `start` and `end` must not be null;
- `end` must be after `start`;
- for `REMOTE`, a meeting link is required;
- for `ONSITE`, a physical location is required.

A small matrix:

| Mode | Meeting Link | Location | Result |
| --- | --- | --- | --- |
| REMOTE | Yes | No | Valid |
| REMOTE | No | No | Invalid: missing link |
| ONSITE | No | Yes | Valid |
| ONSITE | No | No | Invalid: missing location |
| Either | Yes | Yes | Contract-dependent: are extra details allowed? |
| Either | End before start | Either | Invalid |

**Testing fields in isolation will not reveal every cross-field violation.** This is a good place to identify equivalence classes and use parameterized or table-driven tests to reduce duplication while covering important combinations.

However, do not attempt the full Cartesian product of 20 fields without a risk-based reason. Prioritize combinations affecting real invariants; use property-based testing for large value domains when suitable tools are available.

## 12. Testing Errors as Part of a Contract, Not Exact Wording

Example:

~~~java
IllegalArgumentException failure =
        assertThrows(IllegalArgumentException.class,
                () -> new ConstructorInvariantDemo.LineItem(
                        "SKU", -1L, 1));
~~~

You may assert `failure.getMessage()` if the message is **an agreed public contract**, but do not freeze all internal wording merely to add assertions. Changing language, adding context, or improving phrasing is usually not a domain failure.

If a caller must distinguish “discount exceeds subtotal” from “customer ID is missing,” expose an **error code**, result type, or semantically specific exception. Do not make callers parse message strings to decide what to do.

### `assertThrows` and `assertDoesNotThrow`

- `assertThrows(Expected.class, executable)` accepts the expected exception class **or a subclass**. If a contract requires the **exact type**, use `assertThrowsExactly` in a supporting JUnit 5 version.
- `assertDoesNotThrow` is useful for showing boundary values are valid, but generally also **verify the properties** of the constructed object instead of merely asserting no exception.
- `assertAll` groups related assertions about one object so its postconditions are clear; do not use it to conceal failed construction.

Example:

~~~java
var invoice = assertDoesNotThrow(() ->
        new ConstructorInvariantDemo.Invoice(
                "CUS",
                List.of(new ConstructorInvariantDemo.LineItem(
                        "BOOK", 100L, 1)),
                100L));

assertEquals(0L, invoice.totalVnd());
~~~

## 13. Immutable Objects and Invalid States Under Concurrent Load

An object whose fields are `private final`, whose components are immutable, and which does not escape its constructor is generally safer to share across threads. But **`final` does not make every referenced object immutable**, nor does it replace synchronization design for mutable state.

The earlier `Wallet` example is not thread-safe. Two threads may each observe a balance of 100 and attempt to subtract 80, leading to lost updates or unexpected outcomes depending on interleaving. Constructor tests do not exercise that behavior.

Database-backed entities also need **transactions/locking/versioning** to prevent simultaneous requests from overwriting each other. A class with valid in-memory invariants can still behave incorrectly when a persistence mapper bypasses its constructor or a database contains old-version data.

Separate testing responsibilities:

| Boundary | What to Verify |
| --- | --- |
| Constructor/record/builder | Valid input yields a valid object; invalid input is rejected |
| Public mutator | Invalid actions preserve invariants; successful updates satisfy postconditions |
| Serialization/deserialization | JSON input is validated/restored according to the contract |
| Persistence mapper/ORM | Stored and reloaded data preserve invariants; invalid legacy data is handled |
| Application service | Failures do not trigger unintended external side effects; authorization and state are correct |
| Concurrency/transaction boundary | Concurrent commands preserve constraints in the actual source of truth |

Do not rerun expensive integration tests for every small condition already unit-tested; equally, do not claim system-wide safety from one constructor unit test.

## 14. Common Mistakes in Constructor Tests

| Mistake | Problem | Better Approach |
| --- | --- | --- |
| Only checking `assertNotNull(new Object(...))` | Does not establish values, invariants, or failure behavior | Assert meaningful postconditions |
| Testing only the happy path | Misses boundary and invalid values | Test valid, invalid, and boundary cases |
| Expecting every null to throw an arbitrarily chosen exception | Does not reflect the actual contract | Specify the null policy and assert it |
| Using reflection to construct invalid objects | Couples tests to private internals | Test public constructors/mutators and external input boundaries |
| Using `assertThrows(Exception.class, ...)` | Too broad; an incorrect exception still passes | Assert the expected exception type |
| Asserting exact wording of every message | Brittle tests when wording changes | Assert messages only when contractually required |
| Assuming `final List` means immutable | Callers may still change list contents | Defensive copying and aliasing tests |
| Not checking `total` near discount limits | Off-by-one errors can slip through | Test `0`, `subtotal`, `subtotal+1` |
| Unnecessary I/O inside constructors | Side effects are hard to roll back after validation fails | Validate first; coordinate I/O in a service |
| Testing setters individually but not combinations | Individually valid fields may be invalid together | Test cross-field invariants |
| Testing only one thread for a shared mutable object | Misses races and lost updates | Concurrency tests and protection at the correct boundary when needed |

## 15. Constructor Review Checklist

Use this checklist before finalizing tests:

- [ ] Are required parameters checked for null/blank/range violations?
- [ ] Have **exact boundaries** been tested (0, 1, max, max+1)?
- [ ] Are there **cross-field rules** that must be verified together?
- [ ] Are overflow or precision-loss cases handled?
- [ ] After success, are fields normalized and derived values correct?
- [ ] Are collections and mutable references copied or protected appropriately?
- [ ] Can any caller mutate the object in ways that bypass validation?
- [ ] Does construction call overridable code, publish `this`, or create side effects too early?
- [ ] Are exception/result types meaningful to API consumers?
- [ ] Can an ORM, serializer, or framework construct the object through a different path?
- [ ] For mutable objects, do rejected operations preserve valid state?

This checklist does not replace domain reasoning: the strongest tests derive from real invariants, not a generic template.

## 16. Exercise: Creating Valid Appointments

Design a Java `Appointment` class with these fields:

- `appointmentId`: must not be blank.
- `start` and `end`: `LocalDateTime`, non-null, and `end.isAfter(start)`.
- `channel`: an enum, either `ONLINE` or `OFFLINE`.
- `meetingLink`: required for `ONLINE`.
- `location`: required for `OFFLINE`.
- `participants`: a list of participant IDs with at least one entry, no null/blank entries, and no duplicate IDs after normalization.
- After construction, the object is used as immutable configuration.

**Exercise requirements:**

1. Design a constructor (or static factory) that cannot produce invalid states.
2. Draw a table of valid/invalid combinations of `channel`, `meetingLink`, and `location`.
3. Write JUnit 5 parameterized tests for null/blank IDs, boundary `start/end` values, and missing fields for each `channel`.
4. Test empty `participants`, null entries, blank entries, and duplicates after trimming.
5. Verify that editing the source list after creation does not change the object and that accessors do not expose a mutable internal list.
6. If the app receives JSON data, explain which boundary validation occurs before invoking the domain constructor.
7. If an appointment has `reschedule(newStart, newEnd)`, should it return a new immutable object or mutate state in a controlled way? Prove invalid input leaves no corrupted state.

**Acceptance criteria:** every construction path protects invariants; tests assert both valid results and invalid-input rejection behavior; failing parameters/combinations never expose invalid objects; external mutable data cannot corrupt created objects.

---

**Remember:** Constructors do more than “copy data into fields” when objects have business invariants. Constructor testing verifies the promise that **a successfully created object is already valid**; invalid-state testing proves construction and mutation paths **cannot silently violate that promise**.
