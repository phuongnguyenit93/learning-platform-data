# `Objects.requireNonNull` and Precondition Validation in Java

In Java, **precondition validation** means verifying the required conditions of a call **before using the data or performing side effects**. For example, an order creation method might require the order ID to be non-`null` and non-empty, the quantity to be positive, and the system state to allow writes. Checking early causes errors to surface at the **API boundary**, rather than waiting for an internal statement to throw a confusing exception after data has already been partially modified.

In the Java Core – Exception module, under the **Runtime Exceptions** group, `java.util.Objects.requireNonNull` is the foundational API for requiring that a **reference must not be `null`**. It either returns the input reference itself or throws `NullPointerException` right at the check site. However, **`requireNonNull` only checks for null**; it does not replace checks for empty strings, negative values, invalid states, size limits, data integrity, or access permissions.

~~~java
static String normalizeName(String name) {
    Objects.requireNonNull(name, "name must not be null");
    if (name.isBlank()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    return name.trim();
}
~~~

This is a valid Java method snippet when `import java.util.Objects;` is present. It intentionally distinguishes between **null** and **blank**: both are invalid, but they reflect two different conditions. The rest of this article explains the API, exception type selection, validation timing, differences between eager and lazy fallbacks, limitations of null checks, and a standalone Java 17+ program.

## 1. Why is precondition validation important?

Suppose a service receives a request:

~~~java
void sendReceipt(String email, int quantity) {
    inventory.decrease(quantity);
    emailClient.send(email, "Receipt");
}
~~~

This is a **non-standalone illustrative snippet**, assuming `inventory` and `emailClient` exist. If `email == null` or `quantity <= 0`, the application may have already decreased inventory before discovering that the request is invalid. At that point, merely catching a `NullPointerException` **does not roll back** the inventory change.

A better structure:

~~~java
void sendReceipt(String email, int quantity) {
    Objects.requireNonNull(email, "email");
    if (email.isBlank()) {
        throw new IllegalArgumentException("email is blank");
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    inventory.decrease(quantity);
    emailClient.send(email, "Receipt");
}
~~~

Cheap, pure checks are placed before side effects. This helps detect invalid data before causing state changes.

**However, validation does not replace transactions.** Even when inputs are valid, updating inventory might succeed and then sending the email might fail. When consistency is needed, the application must also design appropriate transactions, outbox patterns, idempotency, or error-handling policies. "Precondition checking" only addresses **knowable preconditions**, not guaranteeing that every subsequent operation will succeed.

## 2. How does `Objects.requireNonNull` work?

`Objects` is a utility class in the `java.util` package. Three commonly used overloads:

~~~java
public static <T> T requireNonNull(T obj)

public static <T> T requireNonNull(T obj, String message)

public static <T> T requireNonNull(
        T obj, java.util.function.Supplier<String> messageSupplier)
~~~

These are **illustrative API signatures**, not a custom-defined class. All three overloads share the following behavior:

1. If `obj != null`, return **the reference `obj` itself**.
2. If `obj == null`, throw `NullPointerException`.
3. The message form adds information to identify which parameter was invalid.
4. The `Supplier<String>` form allows constructing the message **lazily** when null is detected.

A simple example:

~~~java
String value = "Java";
String checked = Objects.requireNonNull(value);

System.out.println(checked == value);
// true
~~~

`requireNonNull` does not copy the object, does not make the variable immutable, does not trim whitespace, and does not change the data type. The return value is commonly used to assign directly to a field or pass to the next API.

If null is passed:

~~~java
Object missing = null;
Objects.requireNonNull(missing);
// Throws NullPointerException.
~~~

This is a snippet that intentionally throws an exception at runtime. Do not rely on the message of the no-message overload in tests; the message of a new `NullPointerException` may be `null`.

### Why does it return the input value?

Returning the value keeps code concise in constructors:

~~~java
final class ConnectionConfig {
    private final String host;

    ConnectionConfig(String host) {
        this.host = Objects.requireNonNull(host, "host");
    }
}
~~~

This is a valid Java class when `Objects` is imported. If the caller passes null, the constructor fails before completing, rather than creating an object with an invalid `host` field.

Note that a non-null `host` **does not prove** that the host string is properly formatted, exists in DNS, or is reachable. Those conditions require separate validation.

## 3. Choosing `NullPointerException`, `IllegalArgumentException`, or `IllegalStateException`?

All three classes are unchecked exceptions, but they communicate different meanings.

| Condition | Typically appropriate type | Example |
| --- | --- | --- |
| A required API reference is `null` | `NullPointerException` | `Objects.requireNonNull(orderId, "orderId")` |
| Argument value is non-null but outside valid domain | `IllegalArgumentException` | `quantity <= 0` |
| Object/system is in a state that disallows the operation | `IllegalStateException` | Calling `send()` before connecting |
| Index is out of bounds for a collection | `IndexOutOfBoundsException` | `Objects.checkIndex(index, size)` |
| Value not found as an expected outcome | `Optional`/result may be used | Looking up a non-existent ID |

These are **common design conventions**, not an absolute formula for every public API. Some libraries treat `null` as an invalid argument and intentionally throw `IllegalArgumentException`. What matters is a **consistent, clear contract**.

### Null condition

~~~java
Objects.requireNonNull(customerId, "customerId");
~~~

This form clearly expresses "required non-null reference". If it fails, `getMessage()` of the exception created by the string-message overload is `"customerId"`.

### Value condition

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException(
            "quantity must be greater than zero");
}
~~~

`quantity` is a primitive `int` and cannot be null; `requireNonNull` plays no role in this check.

### State condition

~~~java
if (!connected) {
    throw new IllegalStateException("connection is not ready");
}
~~~

Here the send request itself may be completely valid, but **the receiver's state** does not allow proceeding.

### Do not catch `NullPointerException` to guess which parameter is null

Do not replace proactive validation with:

~~~java
try {
    return user.getProfile().getName();
} catch (NullPointerException e) {
    return "unknown";
}
~~~

This is a counterexample snippet. `NullPointerException` could come from `user`, `getProfile()`, or logic inside some method; catching broadly and falling back can hide an important programming bug. If a nullable reference chain is a valid state, handle **each nullable boundary according to the contract**, rather than swallowing every NPE.

## 4. Two ways to write messages for `requireNonNull`

**Fixed message:**

~~~java
Objects.requireNonNull(request, "request must not be null");
~~~

The message is readable and has no complex string-building cost. For most parameters, this is a good default choice.

**Dynamic message:**

~~~java
Objects.requireNonNull(request,
        () -> "request is required in phase " + phase);
~~~

Here `request` and `phase` are variables available in scope. The lambda is a `Supplier<String>`; it only builds the string when `request == null`.

### When is the Supplier invoked?

~~~java
String value = "present";
int[] calls = {0};

Objects.requireNonNull(value, () -> {
    calls[0]++;
    return "computed diagnostic";
});

System.out.println(calls[0]); // 0
~~~

If the object is non-null, the supplier **does not need to be invoked**. With null:

~~~java
String value = null;
int[] calls = {0};

try {
    Objects.requireNonNull(value, () -> {
        calls[0]++;
        return "computed diagnostic";
    });
} catch (NullPointerException e) {
    System.out.println(e.getMessage()); // computed diagnostic
}
System.out.println(calls[0]); // 1
~~~

These are two standalone illustrative snippets; the main program at the end of the article will verify the same principle.

### A lazy supplier does not mean it is safe to produce side effects

The message supplier should only compute **diagnostic information**. Avoid putting data updates, network calls, or side-effecting logging inside it:

~~~java
Objects.requireNonNull(value, () -> {
    chargeCreditCard(); // Avoid: side effect inside message.
    return "value is missing";
});
~~~

This is a counterexample with a hypothetical `chargeCreditCard()` method. When null, Java runs the supplier to obtain the message, leading to an unintended business operation **while constructing the exception**.

An overly complex message supplier can also throw another exception, masking the NPE that `requireNonNull` was supposed to report. Keep messages short, non-throwing, and free of sensitive data.

### Watch out for overloads when passing null as the message

Do not write ambiguously:

~~~java
Objects.requireNonNull(value, null);
~~~

This form **does not compile** because there are two two-argument overloads accepting `String` and `Supplier<String>`, and the `null` literal matches both without a more specific type.

If you truly want to select the `String` message overload with a null value, you can cast:

~~~java
Objects.requireNonNull(value, (String) null);
~~~

In normal code, however, pass a useful message without needing to cast null.

## 5. `Objects.requireNonNullElse`: choosing a fallback value

Since Java 9, `Objects` has added:

~~~java
public static <T> T requireNonNullElse(
        T obj, T defaultObj)
~~~

If `obj != null`, return `obj`; if `obj == null`, return `defaultObj`, **but the selected value must not be null**.

~~~java
String name = Objects.requireNonNullElse(
        null, "anonymous");

System.out.println(name); // anonymous
~~~

If both the primary value and the fallback are null:

~~~java
Objects.requireNonNullElse(null, null);
// NullPointerException.
~~~

This snippet intentionally triggers a runtime error.

### How it differs from `requireNonNull` in purpose

| Method | When input is non-null | When input is null |
| --- | --- | --- |
| `requireNonNull(obj)` | Returns `obj` | Throws `NullPointerException` |
| `requireNonNull(obj, message)` | Returns `obj` | Throws NPE with message |
| `requireNonNullElse(obj, fallback)` | Returns `obj` | Returns non-null fallback, or throws NPE |

`requireNonNullElse` is only appropriate if **the fallback is a valid value according to the contract**. If a missing input is an error, do not use a default string to mask it.

### Java evaluates arguments before calling the method

An important point:

~~~java
String result = Objects.requireNonNullElse(
        "primary", createExpensiveDefault());
~~~

Even though `"primary"` is non-null, Java still **evaluates the argument expression** `createExpensiveDefault()` before calling `requireNonNullElse`. It may be expensive or have side effects.

This is an **illustrative code snippet**, assuming `createExpensiveDefault()` returns a `String`. If creating the fallback is resource-intensive, consider `requireNonNullElseGet`.

## 6. `Objects.requireNonNullElseGet`: lazily created fallback

Java 9+ provides:

~~~java
public static <T> T requireNonNullElseGet(
        T obj,
        java.util.function.Supplier<? extends T> supplier)
~~~

If `obj != null`, return `obj` without calling the fallback supplier. If `obj == null`, Java obtains the fallback from the supplier and requires **the selected result to be non-null**.

~~~java
String a = Objects.requireNonNullElseGet(
        "ready", () -> expensiveDefault());

String b = Objects.requireNonNullElseGet(
        null, () -> expensiveDefault());
~~~

This is an illustrative snippet assuming `expensiveDefault()` is already defined.

- Case `a`: the supplier is not called.
- Case `b`: the supplier is called to create the fallback value.

### Valid input but the supplier returns null?

~~~java
Objects.requireNonNullElseGet(
        null, () -> null);
// NullPointerException.
~~~

This form does not allow a null fallback. If an API genuinely allows returning null, do not use `requireNonNullElseGet` as a way to silently legitimize that.

### When to use `Else` vs `ElseGet`?

Use `requireNonNullElse` if the fallback is already available or extremely cheap:

~~~java
String label = Objects.requireNonNullElse(rawLabel, "(none)");
~~~

Use `requireNonNullElseGet` if the fallback needs to construct an object, read configuration, or perform significant computation:

~~~java
Settings settings = Objects.requireNonNullElseGet(
        suppliedSettings,
        () -> Settings.defaults());
~~~

This is an illustrative snippet with a hypothetical `Settings` class. Creating fallback data should be a safe operation, and the contract should clearly state when it is computed.

**Do not confuse with `Optional.orElse`/`orElseGet`:** both pairs express the idea of eager/lazy fallback, but `Objects.requireNonNullElse(Get)` operates on **nullable references**, whereas `Optional` represents presence/absence of a value via a different API type.

## 7. Choosing an overload for helpful messages

A good message should describe **the parameter name and the condition**:

~~~java
Objects.requireNonNull(orderId, "orderId must not be null");
~~~

Less helpful:

~~~java
Objects.requireNonNull(orderId, "Error");
~~~

In larger systems, you can include non-sensitive context:

~~~java
Objects.requireNonNull(payload,
        () -> "payload is required for operation " + operation);
~~~

However, avoid:

- Passwords, tokens, secrets, raw cookies, payment card details.
- Entire requests/bodies containing sensitive data.
- Using messages as **stable machine-readable error codes**.
- Relying on file names/line numbers in `printStackTrace()` to determine business conditions.

If automated branching is needed, use a structured error code or an appropriate exception type. Messages are for human readers and may change over time.

## 8. Organizing validation in priority order

For a multi-field request, decide on a **meaningful check order**.

Example:

~~~java
static void validate(
        String orderId,
        String email,
        int quantity,
        boolean systemReady) {

    Objects.requireNonNull(orderId, "orderId");
    Objects.requireNonNull(email, "email");

    if (orderId.isBlank()) {
        throw new IllegalArgumentException("orderId is blank");
    }
    if (email.isBlank()) {
        throw new IllegalArgumentException("email is blank");
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive");
    }
    if (!systemReady) {
        throw new IllegalStateException("system is not ready");
    }
}
~~~

This method can be placed in a Java class with `Objects` imported.

- Required references are checked for null before calling `isBlank()`.
- Value domains are verified next.
- State conditions are checked before causing side effects.
- The method completes normally only when all preconditions are satisfied.

If multiple errors exist simultaneously, **fail fast** means the method throws at **the first invalid condition** in code order. It does not produce a list of all errors. For input forms, you may want a validator that collects all errors and returns a structured result instead of throwing on the first failure.

### Do not mask the first error with a second error

Poor code:

~~~java
static void process(String code) {
    if (code.isBlank()) { // NPE when code is null.
        throw new IllegalArgumentException("blank");
    }
}
~~~

Better approach:

~~~java
static void process(String code) {
    Objects.requireNonNull(code, "code");
    if (code.isBlank()) {
        throw new IllegalArgumentException("code is blank");
    }
}
~~~

This sequence establishes a clear contract: null is an intentional NPE, blank is an IAE.

## 9. Input validation does not imply an immutable object

After `requireNonNull(value)` succeeds, you know **the reference at the time of the check** is non-null. That does not prove:

- The object is not modified by another thread.
- The contents of a list do not contain null.
- The object's fields are all valid.
- The data has appropriate access permissions or security properties.
- The object always remains in a usable state.
- Subsequent I/O operations will not fail.

Example:

~~~java
List<String> names = Objects.requireNonNull(
        suppliedNames, "suppliedNames");
~~~

This is an illustrative snippet with `List` and variable `suppliedNames`. It only verifies that **the list reference is non-null**. Inside, there can still be null elements:

~~~java
List<String> names =
        new java.util.ArrayList<>();
names.add(null);

Objects.requireNonNull(names);     // Succeeds.
Objects.requireNonNull(names.get(0)); // Throws NPE.
~~~

If the contract requires every element to be non-null, validate elements individually or use an immutable/copy API with explicit rules.

### Null checks in constructors and defensive copying

With a mutable collection:

~~~java
final class NameGroup {
    private final java.util.List<String> names;

    NameGroup(java.util.List<String> names) {
        this.names = java.util.List.copyOf(
                Objects.requireNonNull(names, "names"));
    }
}
~~~

`List.copyOf` creates an unmodifiable list and **rejects null elements** according to the API contract. It prevents retaining a reference to a mutable list that the caller might continue modifying, though it still does not check rules such as empty strings or duplicate names.

This is a valid class if `Objects` is imported. Do not assume every copy operation or every collection API has the same null policy; read the specific contract.

## 10. `requireNonNull` in constructors, records, and setters

### Constructor

~~~java
final class Customer {
    private final String id;

    Customer(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }
}
~~~

If `id == null`, no `Customer` object is successfully created to hand back to the caller.

### Record compact constructor in Java 17

~~~java
record Product(String sku, int count) {
    Product {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku is blank");
        }
        if (count < 0) {
            throw new IllegalArgumentException("count is negative");
        }
    }
}
~~~

This is a valid record declaration in an appropriate Java 17 class/file. The compact constructor can validate components before record construction completes.

Advantage: any `new Product(...)` call using this constructor is validated at the boundary. However, a record does not automatically verify all business rules just because it generates accessors and is shallowly immutable.

### Setter

~~~java
void setDisplayName(String value) {
    this.displayName = Objects.requireNonNull(
            value, "displayName");
}
~~~

This is an illustrative snippet inside a mutable class. Checking before assignment prevents introducing an invalid null state into the object.

## 11. Why you should not try to "call `requireNonNull` on everything"

Not every null reference is an error:

- A `middleName` field may be optional.
- A lookup function may return `null` under a legacy contract.
- A dependency may be created from a default when not provided.
- An input attribute may represent "no value".

If `null` is valid, give it a clear meaning or use an appropriate API such as `Optional` for optional return types. **Do not throw NPE just to appear defensive.**

Example of an optional attribute:

~~~java
static String visibleLabel(String label) {
    return Objects.requireNonNullElse(label, "(unnamed)");
}
~~~

Contrast with a required value:

~~~java
static String requiredLabel(String label) {
    return Objects.requireNonNull(label, "label");
}
~~~

Both are valid; choose according to the method's contract.

Do not force `Optional` into every field, every parameter, or every collection element as a rigid pattern. `Optional` is especially useful for return APIs that may have no value, but nullability design should be consistent with the context.

## 12. `Objects.checkIndex` and related precondition checks

In addition to non-null reference checks, a method may require a **valid index or index range**. Java 17 provides these helpers:

~~~java
Objects.checkIndex(index, length);                 // 0 <= index < length
Objects.checkFromToIndex(from, to, length);        // 0 <= from <= to <= length
Objects.checkFromIndexSize(from, size, length);    // Range [from, from + size) lies within length
~~~

This is an illustrative snippet with variables and `import java.util.Objects`. The helpers return `index`/`from` when valid, and throw `IndexOutOfBoundsException` otherwise. The range helpers are designed to check safely even against integer overflow conditions, rather than arbitrarily adding `int` values.

Example of two different preconditions in the same API:

~~~java
Objects.requireNonNull(array, "array");
Objects.checkIndex(index, array.length);
int value = array[index];
~~~

A null reference causes `NullPointerException`; an invalid index causes a bounds error. Do not swallow both and return `0` as if reading succeeded. Conversely, accessing `array[index]` already performs bounds checking; calling `checkIndex` before **every** read is not mandatory. The article on `IndexOutOfBoundsException` analyzes `[from, to)` ranges, off-by-one errors, and helper selection in depth. Here the focus is **verifying preconditions before side effects**.

## 13. `Objects.requireNonNull` and helpful NullPointerExceptions

On JVMs supporting helpful NPE messages, a null dereference error may include a message describing the failed expression. This is a **debugging aid**, not a stable business contract for parsing `getMessage()`.

~~~java
String name = null;
Objects.requireNonNull(name, "name must not be null");
~~~

This illustrative snippet requires `import java.util.Objects`. `requireNonNull` proactively reports the constraint right at the input boundary, with an application-chosen message; whereas a helpful NPE is automatically generated by certain runtime operations. Both may be `NullPointerException`, but they answer two different questions: **was an API precondition violated**, or **where did code dereference null**.

## 14. Avoiding side effects before validation and Java evaluation order

An important execution detail: **arguments to a method call are evaluated before the method begins running**.

Consider:

~~~java
save(
        Objects.requireNonNull(orderId, "orderId"),
        calculateAndChargeFee());
~~~

Even though the first argument is checked by `requireNonNull` before evaluating the second argument under the **left-to-right argument evaluation** rule, you should still avoid structuring complex calls like this when side effects are significant or multiple inputs need validation. Placing validation in separate statements makes the code easier to read and control.

~~~java
Objects.requireNonNull(orderId, "orderId");
validateFeePolicy();

int fee = calculateFee();
save(orderId, fee);
~~~

This is an illustrative snippet with hypothetical functions. If `calculateFee()` has side effects, run it only after the necessary checks.

A clearer counterexample:

~~~java
save(
        calculateAndChargeFee(),
        Objects.requireNonNull(orderId, "orderId"));
~~~

Java evaluates arguments **from left to right**: `calculateAndChargeFee()` can run before `requireNonNull(orderId)` detects null. Never place validation after irreversible operations.

**Do not interpret "fail fast" as "all validation automatically runs before every expression".** Statement placement and actual evaluation order still determine when an error is detected.

## 15. Validate at boundaries, not infinitely in every internal layer

In a public API, checking non-null parameters makes the contract clear. However, each internal layer does not necessarily need to repeat the same check if invariants have already been established and preserved.

For example, if an immutable object has already had its non-null `id` verified by its constructor, internal methods reading `id` do not need to call `Objects.requireNonNull(id)` every time just to compensate for unmaintained invariants.

Conversely, at boundaries between the system and external data — HTTP, JSON, files, databases, user input, or plugins — re-validate because the data source is outside the module's control.

A practical strategy:

1. Validate **types/parsability** of data at the ingestion boundary.
2. Validate **nullability and value domains** right before constructing domain objects.
3. Create objects that enforce invariants via constructors or factories.
4. Pass valid objects across layers instead of a loose set of error-prone parameters.
5. Still handle I/O exceptions, concurrency, and state changes that may occur later.

Precondition validation **reduces input-related errors**, rather than replacing state checks at the time the actual operation executes.

## 16. Standalone Java 17+ program for verification

Create the file **`RequireNonNullDemo.java`**. The program produces deterministic output illustrating `requireNonNull`, lazy messages, fallbacks, preconditions, exception types, and index checks.

~~~java
import java.util.Objects;

public class RequireNonNullDemo {

    record Order(String id, int quantity) {}

    public static void main(String[] args) {
        System.out.println("== basic non-null ==");
        String original = "java";
        String checked = Objects.requireNonNull(original);
        System.out.println("sameReference=" + (original == checked));

        attempt("missing", () ->
                Objects.requireNonNull(null, "id is required"));

        System.out.println("== lazy message ==");
        int[] messageCalls = {0};
        Objects.requireNonNull("present", () -> {
            messageCalls[0]++;
            return "not present";
        });
        System.out.println("callsAfterPresent=" + messageCalls[0]);

        attempt("lazyMissing", () ->
                Objects.requireNonNull(null, () -> {
                    messageCalls[0]++;
                    return "computed message";
                }));
        System.out.println("callsAfterMissing=" + messageCalls[0]);

        System.out.println("== non-null fallback ==");
        System.out.println("elseValue="
                + Objects.requireNonNullElse(null, "guest"));
        System.out.println("elsePrimary="
                + Objects.requireNonNullElse("owner", "guest"));
        attempt("elseBothNull", () ->
                Objects.requireNonNullElse(null, null));

        System.out.println("== eager versus lazy ==");
        System.out.println("eagerResult="
                + Objects.requireNonNullElse(
                        "primary", makeFallback()));
        int[] fallbackCalls = {0};
        String lazyPrimary = Objects.requireNonNullElseGet(
                "primary", () -> {
                    fallbackCalls[0]++;
                    return "created";
                });
        System.out.println("lazyPrimary=" + lazyPrimary);
        System.out.println("fallbackCalls=" + fallbackCalls[0]);

        String lazyMissing = Objects.requireNonNullElseGet(
                null, () -> {
                    fallbackCalls[0]++;
                    return "created";
                });
        System.out.println("lazyMissing=" + lazyMissing);
        System.out.println("fallbackCalls=" + fallbackCalls[0]);
        attempt("lazyNullResult", () ->
                Objects.requireNonNullElseGet(null, () -> null));

        System.out.println("== domain validation ==");
        Order order = createOrder("O-1", 2, true);
        System.out.println("created=" + order.id()
                + ",quantity=" + order.quantity());

        attempt("nullId", () ->
                createOrder(null, 2, true));
        attempt("blankId", () ->
                createOrder("  ", 2, true));
        attempt("invalidQuantity", () ->
                createOrder("O-2", 0, true));
        attempt("systemNotReady", () ->
                createOrder("O-3", 2, false));

        System.out.println("== index validation ==");
        System.out.println("index=" + Objects.checkIndex(2, 3));
        System.out.println("fromTo="
                + Objects.checkFromToIndex(1, 3, 3));
        System.out.println("fromSize="
                + Objects.checkFromIndexSize(1, 2, 3));
        attempt("invalidIndex", () -> Objects.checkIndex(3, 3));
    }

    static String makeFallback() {
        System.out.println("fallbackFactoryCalled");
        return "backup";
    }

    static Order createOrder(
            String id, int quantity, boolean systemReady) {
        Objects.requireNonNull(id, "id");

        if (id.isBlank()) {
            throw new IllegalArgumentException("id is blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        if (!systemReady) {
            throw new IllegalStateException(
                    "system is not ready");
        }
        return new Order(id, quantity);
    }

    static void attempt(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + "=OK");
        } catch (RuntimeException e) {
            System.out.println(label + "="
                    + e.getClass().getSimpleName()
                    + ":" + e.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac RequireNonNullDemo.java
java RequireNonNullDemo
~~~

**Exact stdout (Java 17+):**

~~~text
== basic non-null ==
sameReference=true
missing=NullPointerException:id is required
== lazy message ==
callsAfterPresent=0
lazyMissing=NullPointerException:computed message
callsAfterMissing=1
== non-null fallback ==
elseValue=guest
elsePrimary=owner
elseBothNull=NullPointerException:defaultObj
== eager versus lazy ==
fallbackFactoryCalled
eagerResult=primary
lazyPrimary=primary
fallbackCalls=0
lazyMissing=created
fallbackCalls=1
lazyNullResult=NullPointerException:supplier.get()
== domain validation ==
created=O-1,quantity=2
nullId=NullPointerException:id
blankId=IllegalArgumentException:id is blank
invalidQuantity=IllegalArgumentException:quantity must be positive
systemNotReady=IllegalStateException:system is not ready
== index validation ==
index=2
fromTo=1
fromSize=1
invalidIndex=IndexOutOfBoundsException:Index 3 out of bounds for length 3
~~~

### Program explanation

**`basic non-null`:** `requireNonNull(original)` returns the exact reference, so `sameReference=true`. When `obj == null`, the message overload creates a `NullPointerException` with the supplied message.

**`lazy message`:** the first time, `"present"` is non-null, so the supplier does not run and the counter remains `0`. The second time, null causes the supplier to run once to build the message; `attempt` catches the NPE and prints its content.

**`non-null fallback`:** when obj is null, `requireNonNullElse` returns `"guest"`. When obj is non-null, it returns `"owner"`. When both are null, JDK 17 throws an NPE with message `defaultObj` per the standard implementation. Do not rely on this message detail as an application error-classification contract.

**`eager versus lazy`:** `makeFallback()` runs **before** `requireNonNullElse` even though primary is non-null, so it prints `fallbackFactoryCalled`. In contrast, the supplier of `requireNonNullElseGet` is not called when primary is non-null; when primary is null, the supplier is called once and returns `"created"`.

**`domain validation`:** `createOrder` distinguishes null id (NPE), blank id and non-positive quantity (IAE), and system not ready (ISE). Validation is performed before creating the `Order` record; the caller receives the specific error type.

**`index validation`:** `Objects.checkIndex` and the two range-checking methods return the valid start/index. When index equals length, the method throws `IndexOutOfBoundsException`.

### Stability of JDK messages

The program prints the messages of some exceptions generated by JDK 17 inside `Objects` helpers. Messages such as `defaultObj`, `supplier.get()`, or `Index 3 out of bounds for length 3` are **standard JDK 17 messages**, but **should not be used as an API contract** or conditional logic in a system. If you need tests portable across multiple JDKs, check the exception type and structured information controlled by the application itself; do not force tests to depend verbatim on JDK messages.

## 17. Null in generic APIs and type inference

`Objects.requireNonNull` has the generic signature `<T> T` to preserve the object's static type:

~~~java
String text = Objects.requireNonNull(
        suppliedText, "suppliedText");

java.util.List<String> names = Objects.requireNonNull(
        suppliedNames, "suppliedNames");
~~~

This is an illustrative snippet with corresponding input variables. Generics here **do not deeply inspect type arguments** or collection contents. They only inform the compiler that the return type is compatible with the type of `obj`.

For a method returning a generic object:

~~~java
static <T> T required(T value) {
    return Objects.requireNonNull(value, "value");
}
~~~

The method preserves type `T` and reports NPE if the object is null. It does not turn a nullable value into a compile-time proof of non-nullness across Java's entire type system (Java 17 does not have built-in type-level null-safety like some other languages).

Annotations such as `@NonNull` or `@Nullable` come from separate libraries and static analysis tools; they can improve check quality but do not replace the runtime behavior of `Objects.requireNonNull`.

## 18. Common misconceptions and mistakes

### 18.1. "`requireNonNull` fixes a null value with a default"

False. `requireNonNull` throws NPE on null. If the contract has a valid fallback, use `requireNonNullElse` or `requireNonNullElseGet`.

### 18.2. "`requireNonNull` proves a String is not empty"

False. `""` and `"   "` are both non-null. Check `isEmpty()` or `isBlank()` as required.

### 18.3. "Use `requireNonNull` for primitive integers"

Primitives `int`, `long`, and `boolean` cannot be null. Only when a wrapper such as `Integer` can be null does `requireNonNull` check that wrapper reference.

### 18.4. "`Objects.requireNonNullElse` never creates the fallback if the object is already present"

False if the fallback is passed as a **method call expression**. Java evaluates arguments before calling the method. Only `requireNonNullElseGet` defers **executing the supplier** until the fallback is needed.

### 18.5. "`requireNonNullElseGet` allows a null fallback"

False. When a fallback is needed, the value returned by the supplier must be non-null; otherwise the method throws NPE.

### 18.6. "The message supplier is always called"

False. With `requireNonNull(obj, Supplier<String>)`, the supplier is only used when `obj` is null. Keep message suppliers pure to avoid unexpected side effects.

### 18.7. "Wrapping everything in `catch (NullPointerException)` is defensive programming"

False. It can hide unexpected programming bugs inside many different calls. Proactively validate **parameters with non-null contracts** rather than swallowing every NPE.

### 18.8. "All non-null data is valid"

False. Negative numbers, malformed emails, out-of-range lengths, unready states, and security conditions still require verification.

### 18.9. "`IllegalArgumentException` and `IllegalStateException` are interchangeable"

Avoid treating them as interchangeable. IAE typically describes an invalid argument value; ISE typically describes a receiver state that disallows the operation.

### 18.10. "Precondition checks alone prevent all errors"

False. After validation, I/O errors, thread contention, data changes, timeouts, resource exhaustion, or side-effect failures can still occur. Transaction/lifecycle design is still needed.

### 18.11. "`requireNonNull(list)` checks every element"

False. It checks the list reference. If all elements must be non-null, validate elements or use an API with that contract such as `List.copyOf`.

### 18.12. "Having helpful NPEs means validation is unnecessary"

False. Helpful NPEs aid diagnostics but do not replace an explicit precondition contract. Auto-generated messages should not be parsed either.

### 18.13. "`Objects.checkIndex` throws NPE if index is out of bounds"

False. For integer indices, a range check failure throws `IndexOutOfBoundsException`, not a null-reference error.

### 18.14. "Catching an NPE means execution can safely continue in any state"

False. An unexpected NPE may indicate a broken invariant. If there is no accurate recovery plan, let the error propagate to an appropriate handler.

### 18.15. "Arguments are evaluated after the method begins"

False. Java evaluates argument expressions from left to right **before the method call**. Side effects in an earlier argument can still execute before validation in a later argument.

### 18.16. "Validation should report generic errors to hide parameter names"

Not necessarily. For internal logs and developer-facing APIs, parameter names are usually helpful. What needs to be hidden is sensitive data, not all diagnostic context.

### 18.17. "A nullable field is always a bug"

No. `null` can be a valid optional state by contract. The bug is **inconsistency** between nullability and usage.

### 18.18. "Fail fast is the only way to do form validation"

No. For interactive input APIs, returning multiple errors at once is sometimes better than throwing an exception on the very first error. Choose based on how the caller needs to present and recover from errors.

## 19. Checklist before processing a request

1. **Distinguish required from optional:** Which fields must not be null, and which may be absent?
2. **Check for null early:** Use `Objects.requireNonNull` if null violates the contract.
3. **Check value domains:** Empty/blank strings, negative numbers, lengths, value ranges, formats.
4. **Check state:** Is the receiver/system in a state that allows the operation?
5. **Choose clear error types:** NPE for required null; IAE for invalid argument value; ISE for invalid state; IOBE for indices.
6. **Place validation before side effects:** Avoid writing data or making network calls before discovering invalid input.
7. **Do not overuse fallbacks:** Fallback values must be business-valid; use lazy evaluation only when deferred computation is needed.
8. **Do not parse error messages:** Use exception types or structured error codes when machine logic is needed.
9. **Keep sensitive information out of messages:** Do not accidentally expose tokens or entire requests.
10. **Check contract depth:** A non-null reference does not prove internal data is valid.
11. **Handle concurrency and I/O separately:** Initial validation does not eliminate races or side-effect failures.
12. **Test at boundaries:** Null, blank, out-of-range values, invalid state, and the success branch.
13. **Maintain invariants after construction:** Constructors/factories should produce valid objects so internal code does not repeat checks endlessly.
14. **Define the public API clearly:** Callers should know when an exception is thrown and when a fallback result is returned.

## 20. Self-check questions

1. What does `Objects.requireNonNull` return when the object is non-null?
2. What exception type does it throw when the object is null?
3. Does `requireNonNull("x")` create a new `String`?
4. How do the two message-taking overloads differ?
5. Is the message supplier called if the object is non-null?
6. Why should side effects be avoided in a message supplier?
7. What is the message of `requireNonNull(null, "id")`?
8. Does `requireNonNull("", "name")` throw an error? Why or why not?
9. How does `String.isBlank()` differ from a null check?
10. When should `IllegalArgumentException` be used after `requireNonNull`?
11. When should `IllegalStateException` be used?
12. What does `requireNonNullElse(null, "guest")` return?
13. What does `requireNonNullElse(null, null)` do?
14. When passing a fallback-creating call to `requireNonNullElse`, when does it run?
15. Does `requireNonNullElseGet("present", supplier)` call the supplier?
16. Is `requireNonNullElseGet(null, () -> null)` valid?
17. Why can `requireNonNullElseGet` be beneficial when the fallback is expensive?
18. If a list reference is non-null, are all its elements guaranteed to be non-null?
19. Can a record compact constructor validate nullability and value domains?
20. What does `Objects.checkIndex(index, length)` return if valid?
21. What error does `checkIndex(length, length)` throw?
22. What does `Objects.checkFromToIndex(1, 3, 3)` return?
23. What is the risk of wrapping an entire operation in `catch (NullPointerException)`?
24. Do helpful NPEs replace a proactive validation contract?
25. If a null check is placed after a database update call, what can happen?
26. Can a primitive `int` be null?
27. If a nullable parameter is valid, should `requireNonNull` still always be called?
28. Why are both validation and transactions needed together?
29. When should a list of validation errors be returned instead of throwing the first exception?
30. Should tests check the exception type or the JDK-generated message text?

### Suggested answers

1. The exact object reference passed in.
2. `NullPointerException`.
3. No.
4. `String` takes an eager, pre-built message; `Supplier<String>` builds the message lazily when null.
5. No.
6. It could execute during exception construction and cause unexpected behavior or another error.
7. `"id"`.
8. No; an empty string is still a non-null object.
9. `isBlank` checks characters/whitespace; `requireNonNull` checks the reference.
10. When the object is non-null, but the argument value violates a precondition.
11. When the current state does not allow the operation.
12. `"guest"`.
13. Throws NPE.
14. The argument expression is evaluated before the method starts, even when the primary value is present.
15. No.
16. No; it throws NPE when the fallback result is null.
17. The supplier is only evaluated when the primary value is null.
18. No.
19. Yes.
20. Returns `index`.
21. `IndexOutOfBoundsException`.
22. `1`.
23. It can swallow programming bugs or hide the real failure location.
24. No.
25. Side effects may already have occurred before the invalid input is detected.
26. No.
27. No; follow the nullability contract.
28. Validation checks inputs upfront; transactions handle consistency when subsequent operations can still fail.
29. When the caller needs to display or fix multiple invalid fields in one pass.
30. Prefer checking the exception type and stable application data; do not parse JDK messages.

## 21. Summary

**`Objects.requireNonNull` verifies that a required reference is not `null` and reports `NullPointerException` right at the API boundary.** Returning the reference allows direct use in constructors/field assignments; the `Supplier<String>` overload builds the message only when needed. When a valid fallback exists, `requireNonNullElse` provides a replacement value, while `requireNonNullElseGet` creates the fallback lazily. Those tools **do not** replace checks for blank strings, numeric ranges, state, indices, or security. Validate knowable preconditions **before side effects**, distinguish NPE/IAE/ISE/IOBE semantically, and keep I/O, transaction, and concurrency handling independent from validation.