# Naming classes, fields, and methods in Java OOP

**Goal:** Names should reveal **a class's role**, **the meaning and units of data**, **a method's behavior**, and **side effects and return contracts**. Good names make code readable, clarify responsibilities, and reduce API misuse. Naming is not a substitute for sound design, but it is an essential part of it.

## 1. Core principle: names must tell the truth

Consider this code:

~~~java
DataManager m = new DataManager();
m.process(x);
boolean flag = m.check();
~~~

A reader cannot tell what `DataManager` manages, whether `process()` creates or deletes data, what condition `check()` checks, or what `flag` means. Vague names force people to inspect method bodies and trace several classes to understand code.

A more descriptive version:

~~~java
OrderRepository orders = new InMemoryOrderRepository();
orders.insert(order);
boolean exists = orders.findById(order.orderId()).isPresent();
~~~

Here, the names show that the repository manages orders, `insert()` adds an order, and `findById()` looks up an ID with a possibly missing result. The contract still needs to say what happens with duplicate IDs, but the API is easier to understand.

**Five questions before finalizing a name:**

1. **Which business concept does it represent?** `Order`, `Cart`, `Payment`, or infrastructure such as `OrderRepository`?
2. **Does it convey the role rather than just the data type?** `remainingSeats` is more useful than `number`; `userIds` is more useful than `stringList`.
3. **Can callers predict the action?** `cancelReservation()` is clearer than `handle()`.
4. **Does it reflect conditions and results?** `findById()` suggests “might not exist”; `requireById()` may indicate “throw if missing” if that convention is documented.
5. **Will it stay accurate if implementation changes?** `OrderRepository` accommodates a switch from JDBC to API calls; `JdbcOrderDao` contains technology details and only fits when the class truly is a JDBC adapter.

Do not optimize names solely for brevity. A longer, precise name is often cheaper than repeated reader inference. Conversely, names that repeat information already in context make code cumbersome.

## 2. Standard Java naming conventions

| Element | Common convention | Example | Notes |
|---|---|---|---|
| Class | `UpperCamelCase`, usually a noun/noun phrase | `ShoppingCart`, `OrderRepository` | Describes the object or responsibility |
| Interface | `UpperCamelCase` | `PaymentGateway`, `Runnable` | Named for the **contract**; no mandatory `I` prefix |
| Record | `UpperCamelCase` | `Money`, `OrderLine` | Describes a value or data grouping |
| Enum type | `UpperCamelCase` | `OrderStatus` | Names a set of states or categories |
| Enum constant | `UPPER_SNAKE_CASE` | `PENDING_PAYMENT`, `PAID` | Usually fixed values |
| Method | `lowerCamelCase`, usually a verb/verb phrase | `addLine()`, `findById()` | Names the action or query |
| Field | `lowerCamelCase` | `orderId`, `remainingSeats` | Avoid Hungarian-style prefixes `strName`, `mName` |
| Parameter / local variable | `lowerCamelCase` | `orderId`, `customerEmail` | Short names can work in very clear contexts |
| Named constant | `UPPER_SNAKE_CASE` | `MAX_RETRY_ATTEMPTS` | Typically `static final` for truly immutable constants |
| Package | Lowercase, grouped by domain/feature | `com.example.orders` | Avoid camelCase or underscores in new package names |
| Generic type parameter | Usually one meaningful uppercase letter | `T`, `E`, `K`, `V`, `ID` | Longer, clear names can help complex generics |

These are widely used Java **conventions**, not compiler-enforced naming laws. Java is case-sensitive: `orderId` and `OrderId` are different identifiers.

**Distinguish `final` from constants:** `private final List<Order> orders` makes only the list **reference** unassignable; elements may still be added/removed. Do not automatically rename it `ORDERS` just because it has `final`. `private static final int MAX_ITEMS = 100;` is a typical `UPPER_SNAKE_CASE` constant. Likewise, `private static final List<String> CODES = new ArrayList<>()` has a fixed reference but mutable contents, so consider actual immutability before treating it as a constant.

### Abbreviations and terminology

Prefer readable names such as `HttpClient`, `customerId`, `paymentUrl`, and `parseJson()`. Familiar abbreviations such as `URL`, `HTTP`, `DTO`, and `ID` are fine, but follow **a consistent project convention**, especially in public APIs. Existing Java libraries include types named `URL` and `URI`; do not arbitrarily rename library APIs.

For example, `getURL()` and `getUrl()` may produce different property names under JavaBeans introspection due to decapitalization rules. When renaming code used by reflection, serialization, or binding, verify actual behavior rather than merely changing letter case.

## 3. Naming classes: prioritize concepts and responsibilities

### Domain-model classes

Nouns such as `Invoice`, `ShoppingCart`, `OrderLine`, and `BankAccount` usually clarify which entity or value an object represents. Its methods enforce the concept's invariants.

~~~java
final class ShoppingCart {
    // Danh sách và hành vi thuộc cùng khái niệm giỏ hàng.
}

record OrderLine(String sku, int quantity) {}
~~~

If `Cart` already lives in package `com.example.checkout.cart`, there is no need to call it `CheckoutShoppingCartDataModel`. Be specific enough to avoid confusion with another `Cart` in context, but avoid redundant prefixes.

### Classes that provide behaviors

Some responsibilities are not “entities” but collaborators:

| Vague name | Suggested name | Clarified responsibility |
|---|---|---|
| `OrderManager` | `OrderRepository` | Store and query orders |
| `PaymentHelper` | `PaymentGateway` | Communicate with payment systems |
| `ThingProcessor` | `InvoiceCalculator` | Calculate invoice amounts |
| `ReportUtil` | `CsvReportExporter` | Export reports as CSV |
| `DataHandler` | `InventoryReservationService` | Reserve inventory under business rules |
| `EmailStuff` | `ReceiptSender` | Send receipts |

Suffixes such as `Service`, `Manager`, `Handler`, and `Processor` are not forbidden; they are weak only when they **fail to explain what the service does**. `CheckoutService` may be a good name for a clearly defined checkout use case. Do not force every class to become `SomethingService`.

**Interfaces:** name them by capability/contract, such as `TaxPolicy`, `ShippingGateway`, and `OrderRepository`. Implementation names should convey useful differences: `JdbcOrderRepository`, `InMemoryOrderRepository`, and `StripePaymentGateway`. Avoid reflexive `IOrderRepository`/`OrderRepositoryImpl` naming when it adds no information; follow any established project convention consistently.

**Exceptions:** a meaningful name such as `InsufficientBalanceException` or `OrderNotFoundException` tells callers what went wrong; avoid `MyException` or `CustomException` when a public API can be more specific.

**Classes with `Dto`/`Request`/`Response` suffixes:** appropriate at HTTP/integration boundaries when they transport data. Do not unknowingly treat a DTO as a domain entity; `CreateOrderRequest` need not enforce the same invariants as `Order`.

## 4. Naming fields: meaning, quantity, units, and state

A field name should communicate **what the stored data represents**:

~~~java
// Khó đọc vì thiếu ý nghĩa:
private long value;
private int t;
private boolean flag;
private List<String> data;

// Cụ thể hơn trong ngữ cảnh ví dụ:
private long balanceCents;
private int retryCount;
private boolean emailVerified;
private List<String> permittedCountryCodes;
~~~

### Collections and plurals

- One element: `order`, `customer`, `selectedProduct`.
- Multiple elements: `orders`, `customerIds`, `selectedProducts`.
- A lookup collection: `ordersById` for a `Map<String, Order>`; the name describes **the key** used.
- `pendingOrders` describes a filter, while `orders` merely describes the element type.

Avoid embedding technical collection types in every field name, such as `arrayListOfOrders`; switching `ArrayList` to `LinkedList`/`List` would make the name inaccurate. Prefer an appropriate abstraction: `List<Order> pendingOrders`.

### Units and value ranges

`timeout = 500` does not say whether 500 is milliseconds, seconds, or minutes. Two approaches are:

~~~java
long timeoutMillis = 500L;        // Nếu API thật sự lưu con số millis
java.time.Duration timeout =
        java.time.Duration.ofMillis(500); // Tốt khi API hỗ trợ Duration
~~~

Likewise, `balanceCents` is more precise than `balance` for an integer number of cents; `discountRate` (ratio 0–1) and `discountPercent` (0–100) **are not interchangeable** without an agreed convention. Real monetary values may require `Money(amount, currency)`, `BigDecimal`, and rounding rules, not just a renamed field.

### Boolean variables: use readable affirmative predicates

| Unclear | Suggested | Use case |
|---|---|---|
| `flag` | `emailVerified` | State field |
| Boolean `status` | `paymentCompleted` | A specific binary state |
| `notInvalid` | `valid` | Avoid double negation |
| `check()` | `hasAvailableSeats()` | Condition query |
| `testUser()` | `canAccessResource()` | Permission-checking method |
| `enabledOrNot` | `isEnabled()` | Boolean getter under API conventions |

Read it in a statement:

~~~java
if (account.isLocked()) {
    throw new IllegalStateException("Account is locked");
}

if (cart.hasItems() && payment.canBeCaptured()) {
    // Thực hiện bước tiếp theo.
}
~~~

Note that `isEnabled()` is a conventional JavaBeans name for Boolean methods; `record Settings(boolean enabled)` generates `enabled()`. Do not rename all record accessors to `getEnabled()` just to match JavaBeans; consider actual framework and API requirements.

## 5. Naming methods: express actions and contracts

Action methods should use **verbs or verb phrases**; query methods may use attribute names or clear predicates. A name should indicate not only “what happens” but also help callers anticipate state changes, I/O, failures, and absent results.

| Weak method | Clearer method | Benefit |
|---|---|---|
| `process(order)` | `placeOrder(order)` | Identifies the use case |
| `handle(orderId)` | `cancelOrder(orderId)` | Identifies the effect |
| `calculate(x)` | `calculateShippingFee(destination)` | Identifies the value being computed |
| `update(x)` | `changeDeliveryAddress(address)` | Identifies the field/invariant modified |
| `check(orderId)` | `existsById(orderId)` | Makes the return value easier to understand |
| `get(id)` | `findById(id)` | Indicates lookup by ID |
| `doPayment()` | `capturePayment()` | Distinguishes authorization from capture |
| `run()` | `generateMonthlyStatement()` | Makes the business outcome clear |

### Useful prefixes, not rigid rules

- `getName()` / `name()`: reads a property; follow JavaBeans rules when a framework requires them.
- `isLocked()`, `hasItems()`, `canSubmit()`: Boolean queries.
- `findById()`: suitable when **not found** is an expected outcome, such as returning `Optional<T>`.
- `requireById()` or `loadRequiredById()`: may indicate a **throw-if-missing** convention, which must be documented. Java does not mandate one global error policy for `get` or `find`.
- `calculateTotal()` / `subtotalAmount()`: computations not intended to have side effects.
- `createOrder()`, `placeOrder()`, `cancelOrder()`: actions that change state.
- `save()`, `insert()`, `update()`: document the difference between new writes, updates, upserts, duplicate-key handling, and transactions; a name alone does not ensure correct behavior.
- `sendEmail()`, `enqueueEmail()`, `scheduleEmail()`: distinguish initiating delivery, enqueuing, and scheduling. If code only publishes a message, `enqueue`/`publish` is more accurate than claiming successful delivery.
- `validate()` may throw or return a list of errors; if both semantics exist, distinguish them by names/contracts such as `isValid()` and `validateOrThrow()`.

**Do not hide side effects behind getter names:** a `getBalance()` that calls a remote payment API, changes state, or takes several seconds can surprise callers. If remote access is required, `fetchBalance()` with documented timing, errors, and caching may be clearer.

### Avoid Boolean flags that control separate workflows

~~~java
// Mơ hồ: true có nghĩa gì? Khó nhớ khi đọc lời gọi.
processOrder(order, true);

// Rõ ý định hơn nếu là hai thao tác khác nhau:
orderService.submitOrder(order);
orderService.previewOrder(order);
~~~

If the difference is merely a valid configuration setting within one operation, a named enum may work:

~~~java
enum DeliveryPriority { STANDARD, EXPRESS }

shippingService.scheduleShipment(order, DeliveryPriority.EXPRESS);
~~~

Not every Boolean parameter requires splitting a method: split when the flag selects independent behaviors that the generic name conceals.

## 6. Complete example: from generic names to a readable OOP API

Scenario: a user adds products to a cart, views a subtotal, and places an order. Legacy code often has vague names such as:

~~~java
// Mã Java hợp lệ nhưng tên không nói rõ trách nhiệm.
class Manager {
    private java.util.List<String> data = new java.util.ArrayList<>();
    private boolean flag;

    void add(String x) { data.add(x); }
    java.math.BigDecimal calc() { return java.math.BigDecimal.ZERO; }
    void process(String x) { flag = (x != null); }
}
~~~

Readers cannot tell whether `data` represents a cart or saved orders, what `flag` means, what `calc()` calculates, or whether `process()` persists anything.

### Revised names and responsibility boundaries

~~~mermaid
classDiagram
    class ShoppingCart {
        -List~CartLine~ lines
        +addProduct(String, int, BigDecimal)
        +hasItems() boolean
        +snapshot() CartSnapshot
    }
    class CartLine {
        <<record>>
        +sku
        +quantity
        +unitPrice
        +lineTotal()
    }
    class CheckoutService {
        -OrderRepository orders
        +placeOrder(String, ShoppingCart) Order
    }
    class OrderRepository {
        <<interface>>
        +insert(Order)
        +findById(String) Optional
    }
    class InMemoryOrderRepository
    ShoppingCart *-- CartLine
    CheckoutService --> ShoppingCart : đọc snapshot
    CheckoutService --> OrderRepository : lưu đơn
    InMemoryOrderRepository ..|> OrderRepository
~~~

- `ShoppingCart` is a noun representing a business object; `addProduct()` communicates an action, `hasItems()` a condition, and `snapshot()` that callers receive **a snapshot of data**.
- `CartLine` represents a line item with `quantity` and `unitPrice`; `lineTotal()` clearly means the total for that line.
- `CheckoutService.placeOrder()` names the use-case goal and main effect; `OrderRepository.insert()` denotes a new-write operation.
- `InMemoryOrderRepository` explains the implementation; consumers of the interface need not know it uses a `ConcurrentHashMap`.

**Complete code in `NamingDemo.java`, runnable with Java 17+:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

record CartLine(String sku, int quantity, BigDecimal unitPrice) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid cart line");
        }
    }

    BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

// Snapshot bất biến tại thời điểm đặt đơn.
record CartSnapshot(List<CartLine> lines, BigDecimal subtotalAmount) {
    CartSnapshot {
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(subtotalAmount, "subtotalAmount");
        lines = List.copyOf(lines);
    }
}

final class ShoppingCart {
    private final List<CartLine> lines = new ArrayList<>();

    void addProduct(String sku, int quantity, BigDecimal unitPrice) {
        lines.add(new CartLine(sku, quantity, unitPrice));
    }

    boolean hasItems() {
        return !lines.isEmpty();
    }

    CartSnapshot snapshot() {
        List<CartLine> copiedLines = List.copyOf(lines);
        BigDecimal subtotalAmount = copiedLines.stream()
                .map(CartLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new CartSnapshot(copiedLines, subtotalAmount);
    }
}

record Order(String orderId, List<CartLine> lines, BigDecimal subtotalAmount) {
    Order {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(subtotalAmount, "subtotalAmount");
        if (orderId.isBlank() || lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid order");
        }
        lines = List.copyOf(lines);
    }
}

interface OrderRepository {
    void insert(Order order);              // Trùng mã thì báo lỗi
    Optional<Order> findById(String orderId); // Không thấy -> Optional.empty()
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> ordersById =
            new ConcurrentHashMap<>();

    @Override
    public void insert(Order order) {
        Objects.requireNonNull(order, "order");
        Order previous = ordersById.putIfAbsent(order.orderId(), order);
        if (previous != null) {
            throw new IllegalStateException("Order already exists");
        }
    }

    @Override
    public Optional<Order> findById(String orderId) {
        return Optional.ofNullable(ordersById.get(orderId));
    }
}

final class CheckoutService {
    private final OrderRepository orders;

    CheckoutService(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders, "orders");
    }

    Order placeOrder(String orderId, ShoppingCart cart) {
        Objects.requireNonNull(cart, "cart");

        CartSnapshot cartSnapshot = cart.snapshot();
        if (cartSnapshot.lines().isEmpty()) {
            throw new IllegalArgumentException("Cannot place an empty cart");
        }

        Order order = new Order(orderId,
                cartSnapshot.lines(), cartSnapshot.subtotalAmount());

        orders.insert(order);
        return order;
    }
}

public class NamingDemo {
    public static void main(String[] args) {
        ShoppingCart cart = new ShoppingCart();
        cart.addProduct("JAVA-BOOK", 2, new BigDecimal("125000"));
        cart.addProduct("NOTEBOOK", 1, new BigDecimal("30000"));

        OrderRepository orders = new InMemoryOrderRepository();
        CheckoutService checkout = new CheckoutService(orders);

        Order placedOrder = checkout.placeOrder("ORD-42", cart);

        System.out.println(placedOrder.subtotalAmount()); // 280000
        System.out.println(orders.findById("ORD-42").isPresent()); // true
    }
}
~~~

~~~bash
javac NamingDemo.java
java NamingDemo
~~~

Expected output:

~~~text
280000
true
~~~

In this example:

1. `orderId` is **the order ID**, `sku` is **the product code**, `quantity` is **the quantity**, and `unitPrice` is **the unit price**. Avoid opaque names such as `str1`, `x`, or `val`.
2. `CartSnapshot` represents copied data at order-placement time. `snapshot()` uses the same copied list to compute the subtotal, preventing discrepancies between calculated totals and stored items.
3. `OrderRepository.insert()` matches the behavior of rejecting duplicate IDs through `putIfAbsent`, while `findById()` indicates the possibility of returning `Optional.empty()`.
4. `CheckoutService.placeOrder()` returns the saved `Order`, so the caller names its variable `placedOrder` rather than a generic `result`.
5. `BigDecimal` is used for monetary calculations instead of `double`. Real applications also need currency, rounding/scale policies, and taxation/discount rules.

This illustrates **naming and class boundaries**, not a complete order-management system: mutable `ShoppingCart` has no thread-safety guarantees for concurrent updates; its in-memory repository does not persist across runs; and duplicate-ID rules, transactions, and authentication need further design for production.

**Why do the names fit together?** A call to `checkout.placeOrder("ORD-42", cart)` makes the order-placement action clear; `orders.findById(...)` is a query; and `cart.snapshot()` creates stable data for a new order. Readers need not open every method body to understand the basic functionality.

## 7. Good names must align with APIs and consistency

A name that sounds “good” cannot compensate for a broken contract:

~~~java
// Sai về mặt ý nghĩa: tên nói truy vấn nhưng thực tế xóa dữ liệu.
Order findById(String id) {
    return deleteOrderAndReturnOldValue(id);
}
~~~

If a query has side effects, reconsider the design rather than just making the name more attractive. A name is **a promise** to its caller.

Within one class, avoid multiple names for the same meaning unless real differences exist:

~~~java
findOrder(id);
lookupOrder(id);
getOrder(id);
fetchOrder(id);
~~~

If the four methods truly have different behaviors, documentation should distinguish in-memory lookup, database lookup, HTTP fetching, and throwing on a missing item. If they are only legacy aliases, reduce the number so the API is easier to learn.

### Should method names repeat the class name?

~~~java
// Lặp thừa ngữ cảnh:
cart.addCartProduct(product);
orderRepository.findOrderByOrderId(orderId);

// Tự nhiên hơn khi class đã cho biết bối cảnh:
cart.addProduct(product);
orderRepository.findById(orderId);
~~~

However, `OrderRepository.findByCustomerId()` contains meaningful `CustomerId` information because it distinguishes the query. Do not remove important information merely to shorten a name.

### Method names, exceptions, and null

If a method may not find data, choose and enforce **one consistent contract**:

~~~java
Optional<Order> findById(String orderId);  // Không tìm thấy -> empty()

Order requireById(String orderId);          // Không tìm thấy -> exception
~~~

This is **a deliberately designed API convention**, not a mandatory Java standard. `Optional` is useful for “present or absent” results; there is no need to wrap every variable or field in `Optional`. Explicitly document rejections and side effects of writes, especially for public APIs.

## 8. Naming parameters, local variables, and loop variables

Variable names should reflect **their scope of use**:

~~~java
// i là hợp lý khi chỉ là index của vòng lặp ngắn:
for (int i = 0; i < orderLines.size(); i++) {
    System.out.println(orderLines.get(i));
}

// Trong logic nghiệp vụ, hãy nói vai trò:
for (OrderLine orderLine : orderLines) {
    // ...
}
~~~

For transformed data, input and output names should describe their differences:

~~~java
String rawEmail = request.email();
String normalizedEmail = rawEmail.strip().toLowerCase(java.util.Locale.ROOT);
~~~

However, do not use `normalizedEmail` unless the business domain defines whether lowercasing an entire email address is valid; many systems lowercase only the domain portion, and email comparison policies must be consistent. This example demonstrates **naming data before and after transformation**, not a universal email-normalization rule.

A parameter named `timeoutMillis` is better than `time` when the API accepts only milliseconds; with a `Duration timeout` type, the type already conveys units, so `timeout` is sufficient.

Avoid ambiguous numerical names: what is `total` a total of, and does it include tax? In payments, `subtotalAmount`, `taxAmount`, `shippingFee`, and `grandTotalAmount` may all be distinct. Do not collapse them into `amount` when they appear together in a method.

## 9. JavaBeans, records, ORMs, and serialization

Naming affects more than readers. Some tools derive **property names**, bean identifiers, or column names from code.

### JavaBeans getters/setters

~~~java
public final class CustomerView {
    private String displayName;
    private boolean active;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Many JavaBeans frameworks infer property `displayName` from `getDisplayName()` and `active` from `isActive()`. Actual behavior still depends on library versions and annotations. Avoid casually changing public getter signatures used by reflection-based clients.

### Record accessors

~~~java
public record CustomerSummary(String customerId, boolean active) {}
~~~

Records generate `customerId()` and `active()` accessors automatically, not `getCustomerId()` or `isActive()`. Library consumers need to know the type is a record and which versions of their frameworks support records.

### Published API/ORM/JSON contracts

If a REST payload uses `customer_id` but the Java field is `customerId`, map them explicitly via annotations/mappers rather than making every Java name match JSON formatting:

~~~java
// Ví dụ khái niệm với Jackson:
record CustomerDto(
    @com.fasterxml.jackson.annotation.JsonProperty("customer_id")
    String customerId
) {}
~~~

Similarly, JPA may derive column names or use `@Column(name = "...")`; changing Java field names can affect mappings unless schema names are fixed explicitly. Spring may also derive default bean names from class names; renaming classes can affect wiring through `@Qualifier` or name-based injection.

**Important:** renaming a public API can break source compatibility, binary compatibility, reflection, JSON contracts, database mappings, Spring configuration, documentation, log parsing, and external scripts. Renaming a private field not accessed through reflection usually has a much smaller impact.

## 10. Renaming safely in an existing codebase

Suppose the old API method `createOrder()` should be renamed `placeOrder()`:

1. **Understand current behavior:** does it create an in-memory object, persist to a database, or perform an entire workflow? Rename only when the new name matches the semantics.
2. **Find usages and public boundaries:** compile-time callers, overloads, method references, reflection, serialization, plugin SPIs, Spring/ORM configuration, and scripts.
3. **Use your IDE's Rename Symbol feature:** update symbols and references, then inspect string-based usages that tools may miss.
4. **Support legacy API clients:** keep a compatibility wrapper marked deprecated during a migration period if needed.
5. **Build and test:** compile all relevant modules; test reflection/JSON/database mappings where applicable; review API docs, examples, logs, and metrics.
6. **Remove the old name:** only according to versioning policy and after checking that consumers have migrated.

Example public wrapper:

~~~java
public final class OrderApplicationService {
    public Order placeOrder(String orderId, ShoppingCart cart) {
        // Triển khai đúng use case ở đây.
        throw new UnsupportedOperationException("Illustrative body");
    }

    /** @deprecated Use {@link #placeOrder(String, ShoppingCart)}. */
    @Deprecated(since = "2.1", forRemoval = false)
    public Order createOrder(String orderId, ShoppingCart cart) {
        return placeOrder(orderId, cart);
    }
}
~~~

The wrapper only demonstrates **a migration strategy**; it is not used directly with `NamingDemo.java` (the complete example calls its coordinating class `CheckoutService`). While keeping the wrapper, `createOrder()` must honor its old contract if `placeOrder()` has equivalent semantics; a rename must not silently change behavior. If method names are used as protocol or serialized keys, they need separate migration handling.

## 11. Reviewing and testing name quality

Name quality is difficult to quantify automatically because it depends on business context. Review these questions:

| Review question | Good example | Warning sign |
|---|---|---|
| Does the class express a clear role? | `ReceiptSender` | `GeneralHelper` handles 6 unrelated tasks |
| Does a field express meaning and units? | `retryDelayMillis` | `delay` with unspecified units |
| Does a Boolean read like a question? | `hasOutstandingInvoices()` | `check()` |
| Does a method reveal effects? | `cancelSubscription()` | `processSubscription()` |
| Are possibly missing results clear? | `findById(): Optional<Order>` | `get()` silently returns null |
| Does a public name avoid unnecessary implementation details? | `OrderRepository` | `JdbcMysqlV2Util` in a domain API |
| Does a name match behavior? | `insert()` reports a duplicate key | `find()` deletes data |

Test names also document behavior. With JUnit Jupiter 5, choose names describing **scenarios and outcomes**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;

class NamingDemoTest {
    @Test
    void placingOrderStoresAnImmutableCartSnapshot() {
        OrderRepository repository = new InMemoryOrderRepository();
        CheckoutService checkout = new CheckoutService(repository);
        ShoppingCart cart = new ShoppingCart();
        cart.addProduct("BOOK", 2, new BigDecimal("100"));

        Order placedOrder = checkout.placeOrder("O-1", cart);
        cart.addProduct("PEN", 1, new BigDecimal("10"));

        assertEquals(1, placedOrder.lines().size());
        assertEquals(0, new BigDecimal("200")
                .compareTo(placedOrder.subtotalAmount()));
        assertEquals(placedOrder, repository.findById("O-1").orElseThrow());
    }

    @Test
    void insertingDuplicateOrderIdIsRejected() {
        OrderRepository repository = new InMemoryOrderRepository();
        CheckoutService checkout = new CheckoutService(repository);

        ShoppingCart cart = new ShoppingCart();
        cart.addProduct("BOOK", 1, BigDecimal.TEN);

        checkout.placeOrder("O-2", cart);

        assertThrows(IllegalStateException.class,
                () -> checkout.placeOrder("O-2", cart));
    }

    @Test
    void addingLineWithInvalidQuantityIsRejected() {
        ShoppingCart cart = new ShoppingCart();

        assertThrows(IllegalArgumentException.class,
                () -> cart.addProduct("BOOK", 0, BigDecimal.ONE));
    }
}
~~~

`placingOrderStoresAnImmutableCartSnapshot` states the tested scenario; `insertingDuplicateOrderIdIsRejected` makes the error condition clear. This test requires JUnit Jupiter 5 configured in the project. Tests assert **actual behavior**, not just the presence of particular method names.

Regarding “immutable”: `Order.lines()` returns an unmodifiable list copy and `CartLine` is an immutable record with `String`, `int`, and `BigDecimal` components (all immutable). Thus the snapshot remains unchanged **in this example**. A list copy containing mutable elements does not automatically become a deep copy through `List.copyOf`, so `immutableSnapshot` would mislead without further precautions.

## 12. Common errors and fixes

| Error | Consequence | Resolution |
|---|---|---|
| Using `Manager`, `Helper`, or `Util` for unrelated tasks | Obscures class responsibility | Name the capability/domain; review cohesion |
| Using `data`, `temp`, or `flag` in broad scopes | Readers must trace many lines | Express role and state: `pendingOrders`, `paymentCaptured` |
| Hiding I/O or state changes in method names | Surprises callers with performance or failures | Choose accurate names or document the contract |
| Inconsistent abbreviations | Makes search and concept recognition harder | Maintain a shared terminology glossary and conventions |
| Unnecessary concrete type in a domain name | Becomes inaccurate after implementation changes | Name the meaning; let the type declaration provide details |
| Long names that repeat class/package context | Makes APIs cumbersome | Remove redundancy without losing meaning |
| Renaming public getters/DTOs without checking mappings | Breaks JSON, bean binding, or binary compatibility | Test boundaries and plan migration/versioning |
| Giving one behavior many synonymous names | API is hard to learn; aliases proliferate | Prefer one primary name with temporary deprecated wrappers if needed |
| Returning results that contradict names | Violates caller expectations | Align contracts, method names, and implementations |

## 13. Business-domain naming exercise

An enrollment application currently has this API:

~~~java
class ProcessManager {
    private int n;
    private boolean f;
    private java.util.List<String> values;

    void doWork(String x);
    boolean check(String x);
    void execute(String x, boolean flag);
    String get(String x);
}
~~~

**Business assumptions** to avoid guessing: the system manages seats in a classroom. `n` is the number of remaining seats; `f` indicates registration is closed; `values` stores enrolled student IDs. `doWork(studentId)` enrolls a student; `check(studentId)` checks enrollment; `execute(studentId, flag)` enrolls or cancels depending on the flag; `get(studentId)` returns a confirmation code if enrollment exists.

Complete the following:

1. Propose a class name for one responsibility, such as `ClassEnrollment` if it owns and protects enrollment records; avoid `Manager` unless needed.
2. Rename fields `remainingSeats`, `registrationClosed`, and `enrolledStudentIds`, or choose a data structure that prevents duplicate enrollment.
3. Implement intention-revealing methods `enrollStudent()`, `cancelEnrollment()`, `isEnrolled()`, and `findConfirmationCode()` (consider `Optional<String>` when missing data is normal); replace flag-driven behavior with two explicit operations.
4. Define invariants: no duplicate enrollments, no negative seat counts, no enrollment after registration closes, and cancellation must update the seat count.
5. Write behavior-oriented tests such as `enrollingStudentDecreasesAvailableSeats()`, `enrollingTwiceIsRejected()`, and `closedRegistrationRejectsEnrollment()`.
6. Verify that every name matches its actual behavior. If confirmation codes are created only after enrollment succeeds, `findConfirmationCode()` must not conceal an automatic new enrollment.

**Self-assessment:** Can someone unfamiliar with the code read a method call and predict its main effect? Will names remain accurate if lists become database tables? Does the API clearly separate queries from state-changing operations?

---

**Remember:** Naming well is **a design decision**. Classes reveal *what an object is or does*, fields reveal *data and units*, and methods reveal *behavior and contracts*. Names that reflect domain language, follow Java conventions, and accurately describe effects make code easier to read, test, and change.
