# Representing Command Payloads with Records: A Java 21+ Case Study

## 1. Context: What Data Does a Business Request Carry?

Suppose a shopping cart management application receives the following requests:

- **Create cart** with a `cartId`.
- **Add products** with a cart ID and a list of product lines (`sku`, `quantity`).
- **Checkout** a cart by ID.
- **Cancel cart** with a reason.

These requests are **commands**: they express an intent to be processed, rather than asserting that an action has already occurred. A command can be rejected due to invalid data, missing permissions, a non-existent cart, or a disallowed state.

In real-world systems, a command message also carries metadata such as a request ID, actor/correlation ID, timestamp, or schema version. We need to distinguish:

- **Command payload:** the business data describing *what to do and on which target*, for example `AddProducts("C-1", [Line("SACH",2)])`.
- **Command envelope:** the outer wrapper containing metadata and the payload, for example `Envelope(requestId, actorId, payload)`.
- **Domain state/aggregate:** the state of the shopping cart being processed; it is not the payload.
- **Event:** a message asserting what **has happened** after successful processing, for example `ProductsAdded`; an event is not synonymous with a command.

**Lesson objective:** use **Java records** to create payloads that are statically typed, hold stable data after creation, validate their structure, and are easy to dispatch with pattern matching. This lesson uses Java **21+** to combine records, sealed interfaces, record patterns, and `switch`; records themselves have been a standard feature since Java 16.

## 2. Why Are Records a Good Fit for Command Payloads?

A payload needs to represent a known set of data. Minimal example:

~~~java
record AddOneProduct(String cartId, String sku, int quantity) {}

AddOneProduct payload = new AddOneProduct("C-1", "SACH", 2);
System.out.println(payload.cartId());  // C-1
System.out.println(payload.sku());     // SACH
System.out.println(payload.quantity());// 2
~~~

A Java record automatically provides components according to the record class contract:

1. **Components** in the header, for example `String cartId`, `int quantity`.
2. **A canonical constructor** to initialize all components (which can be customized for data validation).
3. **Accessors** such as `cartId()`, `quantity()`, rather than default JavaBeans getters like `getCartId()`.
4. `equals()` and `hashCode()` based on component values; `toString()` for convenient diagnostics.
5. Fields holding component data are `private final`. A record is `final` and cannot have subclasses.

**Benefits as a payload:** data must be passed explicitly at creation time; there is no need for an object with many setters and intermediate states missing fields; handlers receive a stable structure and can easily match against it with patterns.

**Avoid over-interpreting:** a record **does not automatically guarantee** that all values are valid, does not automatically authenticate permissions, does not automatically serialize to JSON with any arbitrary library, and does not automatically become *deeply immutable* when it holds references to mutable objects.

## 3. Payload and Envelope: Separating Business Data from Transport Metadata

A clear way to define the types:

~~~java
sealed interface Payload permits CreateCart, AddProducts, Checkout, CancelCart {}

record CreateCart(String cartId) implements Payload {}

record Line(String sku, int quantity) {}

record AddProducts(String cartId, List<Line> lines) implements Payload {}

record Checkout(String cartId) implements Payload {}

record CancelCart(String cartId, String reason) implements Payload {}

record Envelope(String requestId, String actorId, Payload payload) {}
~~~

The snippets above illustrate **data shapes** (requiring `import java.util.List`) without validation yet. The complete program in Section 9 will implement everything in a single top-level class.

Why not put `requestId` and `actorId` into every payload?

- `AddProducts` only needs the cart identifier and the line items: this is the data belonging to the business request itself.
- `requestId` is typically metadata used for correlation/tracing, and sometimes as the basis for an idempotency policy.
- `actorId` describes the performer, usually obtained from a **trusted authentication context**; you should not trust an actor string self-reported by the client in JSON.
- Metadata such as timestamp, tenant, trace ID, and version can change with the transport environment without changing the meaning of the payload.

Separating the envelope allows handlers to receive common information in one place:

~~~java
static String logLabel(Envelope message) {
    return message.requestId() + " / " +
           message.payload().getClass().getSimpleName();
}
~~~

This is an illustrative snippet that depends on the `Envelope` definition above; it is not a standalone program.

**There is no single standard forcing every system to use an envelope.** If an application is small or commands only exist internally within the same process, standalone payload records may suffice. Separating an envelope is useful when there are APIs, queues, tracing, auditing, or multiple command types sharing metadata.

## 4. Designing a Closed Payload Hierarchy with `sealed interface`

~~~java
sealed interface Payload
        permits CreateCart, AddProducts, Checkout, CancelCart {}
~~~

Each command payload type is a separate record:

~~~java
record CreateCart(String cartId) implements Payload {}
record Checkout(String cartId) implements Payload {}
record CancelCart(String cartId, String reason) implements Payload {}
~~~

**Advantages:**

- The compiler knows the permitted set of subtypes, making it easy to check whether a switch expression handles all cases.
- Each record has components directly relevant to a single intent; there is no need for a "MegaCommand" consisting of a `type` and a bunch of nullable fields.
- Handler-calling code can accept a common `Payload`, while concrete structures remain type-safe.
- When adding an `ApplyCoupon` subtype, exhaustive switches over `Payload` can be flagged by the compiler to be updated.

**Design limitation:** a sealed interface intentionally **closes** the list of subtypes; it is not suitable for a plugin API that allows external parties to create arbitrary subtypes without a clear extension strategy.

Command names should use verbs expressing intent: `CreateCart`, `AddProducts`, `Checkout`, `CancelCart`; corresponding events should use past-tense names such as `CartCreated`, `ProductsAdded`, `CartCheckedOut`. The two message types have different roles even though both can use records.

## 5. Protecting Payload Data with a Compact Canonical Constructor

Records allow validating and normalizing parameters right at creation time:

~~~java
static String requireText(String text, String name) {
    if (text == null || text.isBlank())
        throw new IllegalArgumentException(name + " không được trống");
    return text.strip();
}

record CreateCart(String cartId) implements Payload {
    public CreateCart {
        cartId = requireText(cartId, "cartId");
    }
}

record Line(String sku, int quantity) {
    public Line {
        sku = requireText(sku, "sku");
        if (quantity <= 0)
            throw new IllegalArgumentException("quantity phải > 0");
    }
}
~~~

These are excerpts to explain constructors; if placed outside a class, the `Payload` type and `requireText` method must be available in the appropriate scope.

In a **compact constructor**:

1. The names `cartId`, `sku`, `quantity` are parameters corresponding to the record components.
2. We can validate and reassign parameters before they are stored into the record fields.
3. After the compact constructor body, Java automatically initializes the component fields from the corresponding parameters.
4. You do not need to—and must not arbitrarily—manually assign `this.cartId = ...` in the style of a full canonical constructor inside a compact constructor.

Data errors should be caught **at payload creation time** when they are invariants true for every payload: IDs must not be blank, quantities must be positive, and product lists to add must not be empty.

**Do not turn the compact constructor into an application handler.** Whether a cart exists, has already checked out, has enough inventory, or whether the actor is permitted depends on external state: these must be handled in the business/application layer.

## 6. Records with Collections: Defensive Copying Is a Practical Requirement

A record with a reference component does not automatically guarantee that the referenced object's contents are immutable. Unsafe example:

~~~java
record UnsafeAddProducts(String cartId, List<Line> lines) {}

List<Line> source = new ArrayList<>();
source.add(new Line("SACH", 2));
UnsafeAddProducts command = new UnsafeAddProducts("C-1", source);
source.add(new Line("BUT", 4));

// command.lines() now sees "BUT" as well.
~~~

If payload data is mutated between enqueueing and processing, the system may execute **something different from the original request**. This makes logging/auditing, retries, and unit testing difficult.

For `List`, you should perform a defensive copy in the constructor:

~~~java
record AddProducts(String cartId, List<Line> lines) implements Payload {
    public AddProducts {
        cartId = requireText(cartId, "cartId");
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
        if (lines.isEmpty())
            throw new IllegalArgumentException("lines không được rỗng");
    }
}
~~~

`List.copyOf` creates a list that cannot be modified through the `List` API, isolated from structural updates to the input list. It rejects a `null` list and null elements. This **is a shallow copy**: if the elements inside are still mutable, element state can still change. In the example, the `Line` element is a record containing only `String` and `int`, so the structure is suitable for a stable payload.

Similarly, if a payload contains an array, `Map`, `Set`, or nested mutable object, you must evaluate how to copy it and how accessors return data. A `final` field only fixes the **reference**, not the entire object graph.

## 7. Distinguishing Payload Validation from Business Validation

This is an important review boundary.

| Condition | Where to check? | Why? |
| --- | --- | --- |
| `cartId` is a non-blank string | Compact constructor/value object | Always needs to be true for every payload of this type |
| `sku` is non-blank; `quantity > 0` | `Line` constructor | Does not require a database to determine |
| `lines` has at least one element and no nulls | `AddProducts` constructor | Protects message structure |
| Whether the cart exists | Handler/repository | Requires persisted state |
| Whether the actor has permission for the cart | Authentication/authorization + handler | Requires trusted identity and business permissions |
| Whether the cart is in `DRAFT` | Domain/application handler | Depends on current state |
| Whether the cart has items before checkout | Domain/application handler | Depends on aggregate |
| Whether the request is a duplicate | Application/infrastructure, persistence | Requires durable request/idempotency state |

The same `AddProducts("C-1", ...)` can be structurally valid yet **invalid to execute** if cart `C-1` has already been checked out. This is not a flaw in Java records.

You need to distinguish **validation failure** from **business rule failure** in API error handling: the two kinds of errors may map to different response codes, logs, and retry policies.

## 8. Dispatching Payloads with Record Patterns in `switch`

Java 21 allows handlers to dispatch by **record type** and deconstruct components directly:

~~~java
static String describe(Payload payload) {
    return switch (payload) {
        case CreateCart(var cartId) ->
            "Tạo giỏ " + cartId;

        case AddProducts(var cartId, var lines) ->
            "Thêm " + lines.size() + " dòng vào " + cartId;

        case Checkout(var cartId) ->
            "Thanh toán " + cartId;

        case CancelCart(var cartId, var reason) ->
            "Hủy " + cartId + ": " + reason;
    };
}
~~~

- `case AddProducts(var cartId, var lines)` uses the exact **component declaration order**, not matching by variable name.
- `var` infers types from the record components; in `AddProducts`, `lines` has static type `List<Line>`.
- Inside a record case, the compiler already knows the concrete subtype, so no manual cast is needed.
- With `sealed interface Payload` and all four subtypes handled, the switch expression is **exhaustive**; no `default` is needed. This helps catch newly added subtypes that have not yet been handled.

**Regarding null:** `switch (payload)` with a null selector throws `NullPointerException` if `case null` is missing; `default` does not automatically catch null either. In the hands-on program below, `Envelope` forbids null payloads via `Objects.requireNonNull(payload, "payload")`, so the handler has a clear precondition. When receiving external data, you must still ensure constructors/validation are actually invoked.

Pattern matching only decides **which branch to enter**. It does not automatically guarantee the payload is authorized to update state; that remains the handler's responsibility.

## 9. Complete Java 21+ Example: Payload, Envelope, Handler, and Cart State

Save as **`CommandPayloadRecordDemo.java`**:

~~~java
import java.util.*;

public class CommandPayloadRecordDemo {
    sealed interface Payload
            permits CreateCart, AddProducts, Checkout, CancelCart {}

    static String requireText(String text, String name) {
        if (text == null || text.isBlank())
            throw new IllegalArgumentException(
                    name + " không được trống");
        return text.strip();
    }

    record CreateCart(String cartId) implements Payload {
        public CreateCart {
            cartId = requireText(cartId, "cartId");
        }
    }

    record Line(String sku, int quantity) {
        public Line {
            sku = requireText(sku, "sku");
            if (quantity <= 0)
                throw new IllegalArgumentException(
                        "quantity phải > 0");
        }
    }

    record AddProducts(String cartId, List<Line> lines)
            implements Payload {
        public AddProducts {
            cartId = requireText(cartId, "cartId");
            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty())
                throw new IllegalArgumentException(
                        "lines không được rỗng");
        }
    }

    record Checkout(String cartId) implements Payload {
        public Checkout {
            cartId = requireText(cartId, "cartId");
        }
    }

    record CancelCart(String cartId, String reason)
            implements Payload {
        public CancelCart {
            cartId = requireText(cartId, "cartId");
            reason = requireText(reason, "reason");
        }
    }

    record Envelope(String requestId, String actorId, Payload payload) {
        public Envelope {
            requestId = requireText(requestId, "requestId");
            actorId = requireText(actorId, "actorId");
            Objects.requireNonNull(payload, "payload");
        }
    }

    enum Status { DRAFT, CHECKED_OUT, CANCELLED }

    record Cart(String id, String ownerId,
                List<Line> lines, Status status) {
        public Cart {
            id = requireText(id, "id");
            ownerId = requireText(ownerId, "ownerId");
            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            Objects.requireNonNull(status, "status");
        }
    }

    static final class Handler {
        private final Map<String, Cart> carts = new HashMap<>();

        String apply(Envelope envelope) {
            Objects.requireNonNull(envelope, "envelope");

            String detail = switch (envelope.payload()) {
                case CreateCart(var id) -> {
                    if (carts.containsKey(id))
                        throw new IllegalStateException(
                                "Giỏ đã tồn tại: " + id);

                    carts.put(id, new Cart(
                            id, envelope.actorId(),
                            List.of(), Status.DRAFT));
                    yield "Tạo giỏ " + id;
                }

                case AddProducts(var id, var newLines) -> {
                    Cart cart = requireDraftOwner(
                            id, envelope.actorId());

                    List<Line> combined =
                            new ArrayList<>(cart.lines());
                    combined.addAll(newLines);
                    carts.put(id, new Cart(
                            id, cart.ownerId(),
                            combined, Status.DRAFT));

                    yield "Thêm " + newLines.size()
                            + " dòng vào " + id;
                }

                case Checkout(var id) -> {
                    Cart cart = requireDraftOwner(
                            id, envelope.actorId());
                    if (cart.lines().isEmpty())
                        throw new IllegalStateException("Giỏ rỗng");

                    carts.put(id, new Cart(
                            id, cart.ownerId(),
                            cart.lines(), Status.CHECKED_OUT));
                    yield "Thanh toán " + id;
                }

                case CancelCart(var id, var reason) -> {
                    Cart cart = requireDraftOwner(
                            id, envelope.actorId());
                    carts.put(id, new Cart(
                            id, cart.ownerId(),
                            cart.lines(), Status.CANCELLED));

                    yield "Hủy giỏ " + id + ": " + reason;
                }
            };

            return envelope.requestId() + ": " + detail;
        }

        private Cart requireDraftOwner(String id, String actorId) {
            Cart cart = carts.get(id);
            if (cart == null)
                throw new IllegalStateException(
                        "Không tìm thấy giỏ: " + id);
            if (!cart.ownerId().equals(actorId))
                throw new SecurityException("Không có quyền");
            if (cart.status() != Status.DRAFT)
                throw new IllegalStateException(
                        "Giỏ không ở DRAFT");
            return cart;
        }

        Cart find(String id) {
            return Objects.requireNonNull(carts.get(id), "cart");
        }
    }

    public static void main(String[] args) {
        Handler handler = new Handler();

        List<Line> mutable = new ArrayList<>();
        mutable.add(new Line("SACH", 2));
        AddProducts add = new AddProducts(" C-1 ", mutable);
        mutable.add(new Line("BUT", 4));

        System.out.println(
                "Dòng trong payload: " + add.lines().size());

        System.out.println(handler.apply(new Envelope(
                "R-1", "U-1", new CreateCart(" C-1 "))));
        System.out.println(handler.apply(new Envelope(
                "R-2", "U-1", add)));
        System.out.println(handler.apply(new Envelope(
                "R-3", "U-1", new Checkout("C-1"))));

        System.out.println(handler.find("C-1").status()
                + " / " + handler.find("C-1").lines().size());

        try {
            handler.apply(new Envelope("R-4", "U-1",
                    new AddProducts("C-1",
                            List.of(new Line("BUT", 1)))));
        } catch (IllegalStateException e) {
            System.out.println(
                    "Lỗi nghiệp vụ: " + e.getMessage());
        }

        try {
            new Line("SAI", 0);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "Lỗi dữ liệu: " + e.getMessage());
        }

        System.out.println(handler.apply(new Envelope(
                "R-5", "U-2", new CreateCart("C-2"))));

        try {
            handler.apply(new Envelope("R-6", "U-99",
                    new AddProducts("C-2",
                            List.of(new Line("SACH", 1)))));
        } catch (SecurityException e) {
            System.out.println(
                    "Lỗi quyền: " + e.getMessage());
        }

        System.out.println(handler.apply(new Envelope(
                "R-7", "U-2",
                new CancelCart("C-2", " Đổi ý "))));

        System.out.println(handler.find("C-2").status());
        System.out.println("Payload bằng nhau: "
                + add.equals(new AddProducts(
                        "C-1", List.of(new Line("SACH", 2)))));
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac --release 21 -encoding UTF-8 CommandPayloadRecordDemo.java
java CommandPayloadRecordDemo
~~~

Output:

~~~text
Dòng trong payload: 1
R-1: Tạo giỏ C-1
R-2: Thêm 1 dòng vào C-1
R-3: Thanh toán C-1
CHECKED_OUT / 1
Lỗi nghiệp vụ: Giỏ không ở DRAFT
Lỗi dữ liệu: quantity phải > 0
R-5: Tạo giỏ C-2
Lỗi quyền: Không có quyền
R-7: Hủy giỏ C-2: Đổi ý
CANCELLED
Payload bằng nhau: true
~~~

### 9.1. Why Are the 12 Lines of Output Meaningful?

- **`Dòng trong payload: 1`:** the source `ArrayList` had an element added after the payload was created, yet `AddProducts.lines` still has one line thanks to `List.copyOf`.
- **`R-1...R-3`:** three different request metadata values wrapping the corresponding payloads. `cartId` is `strip()`ped so `" C-1 "` and `"C-1"` share the same logical ID.
- **`CHECKED_OUT / 1`:** the handler updated the cart via an immutable state snapshot rather than mutating the old record directly.
- **`Lỗi nghiệp vụ`:** the `AddProducts` payload is valid, but cannot be applied to a cart that is already `CHECKED_OUT`.
- **`Lỗi dữ liệu`:** `Line("SAI", 0)` is rejected by the constructor **before** reaching the handler.
- **`Lỗi quyền`:** checking that the actor does not match the owner in the demo handler; this is only an illustration **assuming actorId came from a trusted source**.
- **`R-7...CANCELLED`:** the same envelope type works for the cancel-cart payload.
- **`Payload bằng nhau: true`:** the `AddProducts` record compares by components; two `Line`s with equal values and two lists with equal contents are equal.

### 9.2. What the Demo Intentionally Does Not Implement

This is an **in-memory** simulation, not a production ordering system:

- No HTTP/JSON serializer, message broker, or real API.
- No token/session authentication for `actorId`: `Envelope.actorId` is passed directly from test code.
- No database, transactions, optimistic locking, or thread-safety guarantees under concurrent updates.
- No inventory checks, pricing, budgets, or full business processing rules.
- No duplicate `requestId` protection. `R-1` is only a correlation label in the demo, not an idempotency key enforced by the system.
- No domain events published or audit logs persisted. The string `"Thanh toán ..."` is only a **handler result**, not proof that a payment gateway settled funds.

Keep these limitations in mind when applying the ideas to a real environment.

## 10. Payload Is Not Synonymous with Domain Aggregate or Event

### 10.1. Payload Is a Request

~~~java
new Checkout("C-1")
~~~

This payload does not contain the entire cart's information, because it only needs the aggregate identifier to request checkout.

### 10.2. State Is the Current Truth of the Aggregate

~~~java
record Cart(String id, String ownerId,
            List<Line> lines, Status status) {}
~~~

In the demo, `Cart` is an immutable state snapshot. A production application may use a richer behavioral domain model entity/class, persistence mapping, or an event-sourced aggregate; do not choose a record for an entity just because it is concise.

### 10.3. Event Is What Has Happened

~~~java
record CartCheckedOut(String cartId, String actorId) {}
~~~

An event like the above should only be created/published **after** the handler has succeeded and fulfilled the appropriate transaction/outbox requirements. A failed `Checkout` command must not automatically turn into `CartCheckedOut`.

**Design rule:** commands are typically named with **imperative verbs**, while events are named to describe **outcomes that have occurred**. Two messages may share similar data in a few fields, yet differ in semantics, timing, retry behavior, and source of truth.

## 11. What Bugs Can an Overly Broad Payload Pattern Cause?

A common anti-pattern:

~~~java
// Illustrative anti-pattern: one type with too many unrelated fields.
record MegaCommand(
        String type,
        String cartId,
        String sku,
        Integer quantity,
        List<Line> lines,
        String reason,
        String requestId) {}
~~~

If `type == "CHECKOUT"`, many fields become null or ignored; if `type == "ADD"`, the `reason` field is meaningless. As new commands are added, the number of invalid combinations grows and string-based validation becomes hard to control.

Split into records per intent:

~~~java
sealed interface Payload permits CreateCart, AddProducts, Checkout, CancelCart {}
record CreateCart(String cartId) implements Payload {}
record Checkout(String cartId) implements Payload {}
record CancelCart(String cartId, String reason) implements Payload {}
record AddProducts(String cartId, List<Line> lines) implements Payload {}
~~~

The declarations above show the API shape without implementation details; see the validated code in Section 9.

**Trade-off:** each command type increases the number of classes/records to manage. This is worthwhile when business operations have different structures; for a small tool with a single operation, creating a sealed hierarchy is not strictly necessary.

## 12. From JSON/API to Record Payload: The Deserialization Boundary

An external request might have a JSON structure like this:

~~~json
{
  "requestId": "R-2",
  "type": "ADD_PRODUCTS",
  "payload": {
    "cartId": "C-1",
    "lines": [{ "sku": "SACH", "quantity": 2 }]
  }
}
~~~

This is only a **transport schema example**, not runnable Java code. When receiving it:

1. The parser/serializer reads the JSON and checks structure, numeric types, required fields, and maximum collection sizes.
2. An adapter maps the `type` field to the concrete payload subtype, for example `"ADD_PRODUCTS" -> AddProducts`.
3. `Line` and `AddProducts` are constructed via their canonical constructors so internal invariants are checked.
4. Authenticate the sender and set `actorId` from a **trusted context**; do not trust a self-declared `actorId` inside the payload.
5. Create `Envelope(requestId, trustedActorId, payload)` and pass it to the handler.
6. The handler checks permissions/business rules and updates state within the appropriate transaction.
7. Translate the result or exception into a clear response/error code without leaking sensitive internal details.

A simplified mapping function to illustrate the idea:

~~~java
// Java pseudocode: not a standalone function, depends on DTO/parser.
// Payload payload = switch (dto.type()) {
//     case "CREATE_CART" -> new CreateCart(dto.cartId());
//     case "ADD_PRODUCTS" -> new AddProducts(
//             dto.cartId(), mapValidatedLines(dto.lines()));
//     case "CHECKOUT" -> new Checkout(dto.cartId());
//     case "CANCEL_CART" -> new CancelCart(
//             dto.cartId(), dto.reason());
//     default -> throw new IllegalArgumentException("Unknown type");
// };
~~~

**There is no rule** that every JSON library automatically reconstructs sealed subtypes/record payloads without configuring polymorphic mapping or a discriminator. Depending on Jackson, JSON-B, or another framework, you must read the version's documentation and verify compatibility of constructors, field names, unknown properties, and validation.

### Boundary Validation Is More Than Record Constructors

A payload can be valid according to Java types yet still unsafe to process:

- Strings millions of characters long causing overload.
- Huge collections spiking time/memory usage.
- Malformed IDs or IDs containing unexpected characters.
- Requests spoofing another `actorId` if the boundary does not authenticate.
- Ignored unknown fields leading the client to believe a feature was applied.
- Integer overflow, extreme values, or negative numbers violating fine-grained rules.

Define max sizes, schema versions, required-field checks, and authorization at the **appropriate boundary**, rather than assuming records solve everything.

## 13. Idempotency: Record Equality and `requestId` Are Not Enough

Records generate `equals()` based on components, but **value equality does not mean exactly-once processing**. For example:

~~~java
AddProducts a = new AddProducts(
        "C-1", List.of(new Line("SACH", 2)));
AddProducts b = new AddProducts(
        "C-1", List.of(new Line("SACH", 2)));

System.out.println(a.equals(b)); // true
~~~

Two objects are equal by value, yet they may be **two distinct valid requests to add items**; you cannot default to ignoring the second one just because `equals() == true`.

Even when an envelope has `requestId`:

~~~java
record Envelope(String requestId, String actorId, Payload payload) {}
~~~

having this field does not by itself make the system idempotent. In production, if a client retries due to a timeout or a broker redelivers a message, you need policies such as:

- An idempotency key that remains stable across retries of the **same logical request**.
- A clear uniqueness scope, for example per tenant/actor/operation.
- Persisting the result or processed state alongside the appropriate transaction/unique constraint.
- Defining behavior when the same key is sent with a different payload.
- A strategy for handling concurrent duplicate requests.
- Retention period and response semantics when a duplicate is encountered.

The demo uses `requestId` to **label results** and has no mechanism to store/query keys, so it must **not** be treated as a demonstration of idempotency or exactly-once delivery.

## 14. Schema Evolution: Adding a Component Changes the Contract

Suppose initially:

~~~java
record CreateCart(String cartId) implements Payload {}
~~~

Later the business requires adding a currency:

~~~java
record CreateCart(String cartId, String currency) implements Payload {}
~~~

This is not just a display change; altering a record header can affect:

- The canonical constructor signature and call sites at compile time.
- Exposed record components and accessors.
- `equals()`, `hashCode()`, and `toString()`.
- The message's deserialization/serialization schema.
- Record patterns `case CreateCart(var cartId)` now **have the wrong component count** if not updated.
- Older messages still sitting in queues or stored for replay.

**Recommended strategies:**

1. Explicitly record the contract version in the API/message schema, rather than inferring it solely from the Java class name.
2. Provide an **adapter/migrator** that converts old messages to the current internal payload if backward compatibility is required.
3. Supply controlled defaults when allowed by the business; do not silently assign a currency or tenant that causes incorrect behavior.
4. Test round-trips with serializers and fixtures for both old and new versions.
5. When changing subtypes in a sealed hierarchy, review all exhaustive pattern switches.
6. Distinguish **in-process model evolution** from **wire/queue exchange schemas**; they do not share the same deployment lifecycle.

Do not simply add a component and assume the record is automatically backward compatible with all older clients/producers.

## 15. Pattern Matching on Payloads: Benefits and Limitations

### Benefits

- Each case is type-checked and deconstructs components cleanly.
- Reduces manual casts and chains of `if (type.equals(...))`.
- With a sealed hierarchy, the compiler helps detect unhandled subtypes.
- `when` can express simple branching conditions over matched data.
- Nested record patterns are convenient when payloads have clearly structured nested records.

### Things to Be Careful About

- A record pattern only matches the record structure; it **does not re-run the constructor** to validate.
- Guards can cause side effects if you call services/mutations inside `when`; keep guards simple and pure whenever possible.
- A nested pattern `case SomePayload(NestedRecord(...))` does not match when the component holding the nested record is null; provide a fallback/validation if null is valid data.
- `case null` handles a null selector, **not** null fields/components inside the record.
- Type erasure prevents generic type arguments from always being checked at runtime—for example, an `Object` cannot arbitrarily be checked as a parameterized `Box<String>`.
- Dispatching a core behavior with a switch over all implementations can sometimes increase coupling compared to polymorphism. Choose the structure that fits the responsibility, rather than applying patterns just for new syntax.
- Compiler errors about dominance, arity, and exhaustiveness are important signals to fix; adding `default` indiscriminately can mask new subtypes.

## 16. Test Matrix for Command Payloads

Tests should cover **three layers**:

### Layer A — Payload Constructor/Invariants

| Input | Expected |
| --- | --- |
| `CreateCart(null)` | Rejected with `IllegalArgumentException` |
| `CreateCart("   ")` | Rejected |
| `CreateCart(" C-1 ")` | Normalized to `"C-1"` |
| `Line("SACH", 0)` | Rejected for `quantity <= 0` |
| `AddProducts("C-1", List.of())` | Rejected for empty list |
| `AddProducts("C-1", null)` | Rejected for null reference |
| `AddProducts("C-1", listMutable)` then mutate list | Created payload does not change |
| `Envelope("R-1", "U-1", null)` | Rejected for null payload |

### Layer B — Handler/Domain Rules

| State and Request | Expected |
| --- | --- |
| Create new cart | `DRAFT` created successfully |
| Create existing cart ID | Duplicate ID rejected per policy |
| Add items to `DRAFT` cart by same owner | Succeeds |
| Checkout `DRAFT` cart that is empty | Rejected |
| Checkout cart with items | Transitions to `CHECKED_OUT` |
| Add items after checkout | Rejected due to state |
| Non-owner actor attempts to modify cart | Rejected for permission |
| Cancel `DRAFT` cart by owner | Transitions to `CANCELLED` |
| Cancel an already `CANCELLED` cart | Rejected or returns result per agreed policy |

### Layer C — API/Message Boundary

| Test | Purpose |
| --- | --- |
| Missing `type` or unknown `type` | Does not instantiate wrong subtype |
| JSON missing required field | Detects schema/validation error |
| Oversized collection | Enforces resource limits |
| Request with self-declared `actorId` differing from authenticated identity | Does not bypass authorization |
| Old-version message | Backward compatibility per policy |
| Resending same `requestId` | Verifies idempotency **if implemented by the system** |
| Two concurrent requests on one cart | Verifies transaction/concurrency handling |
| Serializer round-trip | Preserves subtype, fields, and Unicode data |

Do not just test "each `case` executes once". With `when`, test true/false guards, short-circuit paths of `&&`/`||`, null selectors, and null components. Coverage tools only help observe code paths; they do not prove all invariants.

## 17. Common Mistakes When Introducing Payload Records

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Payload and state entity are the same class/record | Confuses request with lifecycle state | Separate payload and aggregate |
| Payload holds `Repository`, `Connection`, or service | Infrastructure coupling, hard to serialize/test | Keep records as data; handlers hold dependencies |
| Accepting `actorId` from client and trusting it directly | Can modify other users' data | Obtain trusted principal from auth context |
| Checking `cartId` only in handler while allowing invalid records to be created freely | Messages lack stable invariants | Validate structure at creation time |
| Assuming `final` makes `List` deeply immutable | Payload can change after enqueueing | Defensive copy and immutable elements |
| Using one `MegaCommand` with countless nullable fields | Many invalid data combinations | Split records per intent |
| Assuming `requestId` equals idempotency | Duplicate deliveries can still run multiple times | Design durable deduplication |
| Thinking `record.equals` prevents duplicates | Two identical requests may both be valid | Separate value equality from business idempotency |
| Adding a component to a record without updating consumers | Constructors/patterns/schemas can break | Versioning, adapters, contract tests |
| Using `default` in a sealed switch for all new subtypes | Can mask unhandled new use cases | Leverage exhaustive switches |
| Using `case null` and assuming all components are non-null | NPE inside the case | Check component/constructor invariants |
| Treating `switch` as an authorization check | Cases only select types, not authenticate actors | Authorize in handler/domain |
| Handling all payloads with an unlocked map | Races, lost updates | Transactions/versioning/concurrency control |
| Logging raw payloads containing secrets | Data leakage | Redaction and logging policy |
| Using a record just for brevity when a mutable entity/ORM proxy is needed | Unsuitable for lifecycle/identity | Choose an appropriate domain class |

## 18. Code Review Checklist for Payload Records

A PR adding/modifying a command payload should be reviewed against this checklist:

- [ ] Payload class has an **intent-based name**, with minimal components yet sufficient business data.
- [ ] Transport/request metadata lives in an appropriate envelope/context, not unnecessarily mixed into the payload.
- [ ] Record constructors validate non-null, blank, ranges, collection sizes, and internal invariants.
- [ ] Mutable nested data is defensively copied; record elements have appropriate immutable semantics.
- [ ] Callers cannot mutate the payload after sending via an alias to a collection.
- [ ] Sealed hierarchy and pattern switches are exhaustive for the API scope.
- [ ] Record patterns match the exact **component order and count**, and guards have no unintended side effects.
- [ ] Null selectors and nullable components have an explicit policy.
- [ ] Handlers check existence, authorization, and state; DB-dependent business logic is not placed in constructors.
- [ ] Tests distinguish **data errors**, **permission errors**, and **state errors**.
- [ ] `requestId`/correlation ID is not advertised as idempotency if not implemented.
- [ ] JSON/schema versioning, backward compatibility, concurrency, and error mapping are considered if commands cross networks/queues.
- [ ] Sensitive information is not logged raw via `toString()`.
- [ ] Comprehensive tests cover both boundary + handler, not just a single `new Record(...)` example.

This checklist helps maintain a clear boundary between **command payloads as data** and **handlers as the place that executes intent**.

## 19. Exercises and Suggested Answers

**Exercise 1 — Payload design.** Add an `ApplyCoupon(cartId, couponCode)` request to the system. Which fields belong in the payload? If `requestId`/`actorId` are needed, where do they go? What changes are needed in the sealed hierarchy and handler?

**Exercise 2 — Defensive copy.** For `record Batch(List<Line> lines) {}`, write a compact constructor preventing the source list from being mutated after the record is created. Does `List.copyOf` protect against mutation if `Line` elements are mutable?

**Exercise 3 — Validation vs. domain rule.** Why should `quantity > 0` be checked when creating `Line`, while `cart.status() == DRAFT` should be checked in the handler? What problems arise if both are placed in the payload constructor?

**Exercise 4 — Idempotency.** A client sends two `AddProducts` requests with the same `cartId`/`lines` but **different `requestId`s**. Payload `equals()` may be `true`. Should the system automatically drop the second request? If the client retries with the same `requestId` after a timeout, what support does the system need?

**Exercise 5 — Versioning.** Add `currency` to `CreateCart`. What impacts on constructors, record patterns, serializers, and older consumers need to be considered?

**Exercise 6 — Permission.** A client sends `Envelope("R-10", "ADMIN", payload)`. Why is `actorId == "ADMIN"` in the record **not** proof of permission? Describe how to use an authenticated principal to build the envelope at the boundary.

**Hints:**

~~~java
// Exercise 1: sketch in the same hierarchy:
record ApplyCoupon(String cartId, String couponCode)
        implements Payload {
    public ApplyCoupon {
        cartId = requireText(cartId, "cartId");
        couponCode = requireText(couponCode, "couponCode");
    }
}

// Exercise 2:
record Batch(List<Line> lines) {
    public Batch {
        lines = List.copyOf(Objects.requireNonNull(lines));
    }
}
~~~

- Exercise 1: the payload contains `cartId` and `couponCode`; `requestId`/`actorId` are metadata suited for the envelope/context. Add `ApplyCoupon` to `permits` and add a dispatch branch; the handler must also check cart state and coupon validity according to business rules.
- Exercise 2: `List.copyOf` protects the **list structure** rather than deep-copying mutable elements. In the demo, `Line` is a simple record, so it is safer.
- Exercise 3: `quantity` is a standalone data invariant; state requires reading the current cart and can change over time, so payload constructors should not be forced to access repositories.
- Exercise 4: do not automatically deduplicate by payload equality; you need an idempotency key with defined semantics and durable storage of the result/processing state if required by the business.
- Exercise 5: constructor signatures, pattern arity, wire schemas, and backward compatibility all require updates/migration.
- Exercise 6: a client-supplied `actorId` can be spoofed. Authenticate the principal using a trusted source, then construct the envelope or pass the principal into the handler via server-side context.

## 20. Summary

Representing **command payloads with records** works well when:

1. **The payload is strictly the data of the business intent**, containing no services, transactions, or mutable entities.
2. **Constructors protect internal invariants**; `List.copyOf` and immutable element records help prevent unintended aliasing.
3. **The envelope separates metadata from the payload**; identity information must come from a trusted authentication source.
4. **A sealed hierarchy + record pattern switch** enables type-safe dispatch and leverages exhaustiveness in Java 21.
5. **The handler applies business rules to state**: checking permissions, state, resource existence, and transactions/concurrency.
6. **Both normal and failure cases are tested**, without conflating value equality, correlation IDs, and idempotency.
7. **Wire schemas are versioned intentionally**, especially when adding record components or new subtypes.

### References

- [JEP 395 — Records](https://openjdk.org/jeps/395): record class semantics, components/accessors/constructors, and value-oriented data.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): restricting the set of subtypes of an interface.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record deconstruction in pattern matching (Java 21).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch patterns, `case null`, and exhaustiveness (Java 21).
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Java SE 21 List.copyOf API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
