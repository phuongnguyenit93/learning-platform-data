# Auxiliary Constructors and Canonical Constructor Delegation Rules in Records (Java 17)

> **Topic:** Java 17  
> **Chapter:** Record  
> **Scope:** Features stable in Java 17. All examples are designed for `javac --release 17`, without needing preview features enabled.

## 1. The Problem to Solve

Suppose an application stores connection configuration consisting of a host name, port, and security mode:

```java
record Endpoint(String host, int port, boolean secure) { }
```

You can create an object by passing all three values:

```java
Endpoint endpoint = new Endpoint("api.example.com", 443, true);
```

However, if most HTTPS connections use port 443, callers might want shorter ways to invoke it:

```java
new Endpoint("api.example.com");      // Default HTTPS, port 443
new Endpoint("api.example.com", 8443); // HTTPS, specified port
new Endpoint();                       // Default local configuration
```

In Java 17, a `record` **is allowed to declare multiple constructors** just like a regular class, with one very important constraint: **every auxiliary (non-canonical) constructor must begin with a call to another constructor of the same record using `this(...)`**. The delegation chain must ultimately reach the **canonical constructor**, where the record components are initialized.

This lesson clarifies three forms to distinguish:

1. **The auto-generated canonical constructor** provided by Java if you do not declare one.
2. **An explicitly written canonical constructor**, either in full form or short form (*compact canonical constructor*).
3. **Auxiliary constructors (overloaded/non-canonical)**, which provide convenient creation forms but must delegate via `this(...)`.

## 2. What Is the Canonical Constructor?

Every record has a list of **record components** in its header:

```java
record Student(String name, int age) { }
```

With this header, the standard constructor has two parameters, **in the exact matching order and types**:

```java
Student(String name, int age)
```

This is called the **canonical constructor**. When not declared explicitly, the compiler provides a constructor that initializes the field corresponding to each component:

```java
Student student = new Student("Lan", 20);
System.out.println(student.name()); // Lan
System.out.println(student.age());  // 20
```

Each record has exactly **one canonical constructor** (either implicitly generated or explicitly declared). Java **does not automatically generate a no-arg constructor** for a record with components. For example, `new Student()` is invalid unless you write an auxiliary constructor `Student()`.

With `record Student(String name, int age)`, Java also provides:

- Two corresponding component fields: `private final String name` and `private final int age`.
- Accessors: `name()` and `age()`.
- `equals(Object)`, `hashCode()`, and `toString()` methods appropriate for the record.

**The canonical constructor is responsible for initializing all component fields**, not just partially initializing them. That is the reason every auxiliary constructor must route through it.

### 2.1. Three Forms of Canonical Constructor

**Form A — Let Java generate it automatically:**

```java
record Student(String name, int age) { }
```

Suitable when input data is already valid and needs no normalization.

**Form B — Write a full canonical constructor manually:**

```java
import java.util.Objects;

record Student(String name, int age) {
    Student(String name, int age) {
        this.name = Objects.requireNonNull(name, "name").strip();
        if (this.name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be >= 0");
        }
        this.age = age;
    }
}
```

In this form, you declare the full parameter list and **manually assign each component field** via `this.name = ...`, `this.age = ...`; the compiler requires every component field to be properly initialized. The full form is useful when you want explicit control over the assignments.

**Form C — Write a compact canonical constructor:**

```java
import java.util.Objects;

record Student(String name, int age) {
    Student {
        name = Objects.requireNonNull(name, "name").strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be >= 0");
        }
    }
}
```

In a **compact constructor**, the parameters are taken implicitly from the record header. Once the body completes normally, Java automatically assigns the parameter values (possibly normalized) to each component field in declaration order. Therefore:

```java
name = name.strip(); // Valid: reassigning the parameter in a compact constructor
```

but:

```java
// Invalid in a compact constructor:
// this.name = name.strip();
```

When you only need validation and data normalization, the **compact canonical constructor** is usually the most concise and readable choice.

| Form | Declares parameter list? | Who assigns component fields? | When to use? |
|---|---|---|---|
| Implicitly generated | No constructor written | Compiler | Input data needs no processing |
| Full canonical | Yes, matches components by name, type, order | Developer | Want direct control over the assignment process |
| Compact canonical | No, uses implicit parameters from header | Compiler, after the body | Validate, normalize, and keep code concise |

**You cannot declare both a full canonical and a compact canonical constructor** in the same record: both are the canonical constructor with the same signature, so the compiler reports a duplicate error.

## 3. Auxiliary Constructors and the `this(...)` Rule

An auxiliary constructor is a constructor with a **parameter list different from the canonical constructor's signature**. It lets you create records with default values, input conversions, or convenient call forms.

```java
record Point(int x, int y) {
    Point(int x) {
        this(x, 0);
    }
}
```

Here:

- `Point(int x, int y)` is the canonical constructor implicitly generated by Java.
- `Point(int x)` is an auxiliary constructor.
- `this(x, 0)` calls the canonical constructor, passing `0` as the default `y` value.

Usage:

```java
Point point = new Point(5);
System.out.println(point); // Point[x=5, y=0]
```

### 3.1. Mandatory Rule in Java 17

**In Java 17, the body of every non-canonical constructor must begin with a call to another constructor of the same record:**

```java
this(...);
```

`this(...)` is an *alternate constructor invocation*. You may call the canonical constructor directly **or** another auxiliary constructor, as long as the entire chain eventually reaches the canonical constructor.

**You cannot** use `super(...)` instead of `this(...)`. Records inherit `java.lang.Record` via language rules; you cannot manually control component field initialization by calling `super(...)` in an auxiliary constructor.

**You cannot** place other statements before `this(...)` in an auxiliary constructor in Java 17. Newer Java versions may have different constructor rules; this lesson adheres strictly to the stable semantics of **JDK 17**.

Valid example:

```java
record Box(int width, int height) {
    Box(int side) {
        this(side, side);
    }
}
```

Invalid example:

```java
record Box(int width, int height) {
    // INVALID: auxiliary constructor does not begin with this(...).
    Box(int side) {
        int normalized = Math.max(0, side);
        this(normalized, normalized);
    }
}
```

You cannot move `this(...)` after the normalization step. Instead, place validation/normalization in the canonical constructor or express it as an expression right inside the `this(...)` call.

### 3.2. Can Chain Through Multiple Auxiliary Constructors

```java
record Ticket(String code, int priority) {
    Ticket() {
        this("NEW");
    }

    Ticket(String code) {
        this(code, 0);
    }

    Ticket {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Invalid ticket code");
        }
        if (priority < 0) {
            throw new IllegalArgumentException("Priority must be >= 0");
        }
    }
}
```

Execution flow of `new Ticket()`:

```text
new Ticket()
   |
   v
Ticket()                [auxiliary constructor]
   | this("NEW")
   v
Ticket(String code)     [auxiliary constructor]
   | this(code, 0)
   v
Ticket(String, int)     [compact canonical constructor]
   | validates code, priority
   | Java assigns component fields
   v
Ticket[code=NEW, priority=0]
```

This chain is called **constructor chaining**. The compiler forbids a `this(...)` chain from cycling back to the starting constructor and forming a loop.

### 3.3. Auxiliary Constructors Can Contain Code After `this(...)`

The requirement is that **the first statement must be `this(...)`**; Java does not require that call to be the last statement:

```java
record Counter(int initial) {
    Counter() {
        this(0);
        System.out.println("Created default Counter");
    }
}
```

When statements after `this(...)` run, the canonical constructor has already finished initializing and validating the record. You can perform other valid operations, but **you cannot reassign the `final` fields of the record**. For data objects, minimize side effects in constructors and keep validity rules centralized in the canonical constructor.

## 4. Complete Practical Example: Creating Configurations with Multiple Call Forms

Create `ConstructorDemo.java`:

```java
import java.util.Locale;
import java.util.Objects;

public class ConstructorDemo {

    public record Endpoint(String host, int port, boolean secure) {

        // Compact canonical constructor: used by ALL Endpoint creation paths.
        public Endpoint {
            host = Objects.requireNonNull(host, "host")
                    .strip()
                    .toLowerCase(Locale.ROOT);

            if (host.isBlank()) {
                throw new IllegalArgumentException("host must not be blank");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException(
                        "port must be in range 1..65535");
            }
        }

        // Host only: defaults to HTTPS on port 443.
        public Endpoint(String host) {
            this(host, 443, true);
        }

        // Host and port, TLS enabled by default.
        public Endpoint(String host, int port) {
            this(host, port, true);
        }

        // Used for local practice.
        public Endpoint() {
            this("localhost", 8080, false);
        }

        public String url() {
            return (secure ? "https://" : "http://")
                    + host + ":" + port;
        }
    }

    public static void main(String[] args) {
        Endpoint first = new Endpoint("  EXAMPLE.COM  ");
        Endpoint second = new Endpoint();
        Endpoint third = new Endpoint("API.LOCAL", 8443, true);

        System.out.println(first);
        System.out.println(second.url());
        System.out.println(third.url());
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 ConstructorDemo.java
java ConstructorDemo
```

Output:

```text
Endpoint[host=example.com, port=443, secure=true]
http://localhost:8080
https://api.local:8443
```

What to observe:

1. `new Endpoint("  EXAMPLE.COM  ")` selects the **one-parameter** auxiliary constructor.
2. That constructor calls `this(host, 443, true)`, forwarding to the **compact canonical constructor**.
3. The canonical constructor trims whitespace, lowercases `host` using `Locale.ROOT`, and validates the port.
4. Java assigns the normalized parameters to the component fields. The output shows host as `example.com`.
5. The two-parameter, three-parameter, and no-arg calls all pass through the exact same validation logic.

Try creating invalid values:

```java
new ConstructorDemo.Endpoint(" ", 443, true);
new ConstructorDemo.Endpoint("api.example.com", 70000, true);
```

Both throw `IllegalArgumentException` from the canonical constructor. That is the main benefit of **centralizing invariants in one place** instead of duplicating checks across every auxiliary constructor.

> **Note:** Lowercasing a hostname fits DNS names, but you should not automatically apply the same normalization to every business string. Normalize values according to the specific requirements of your data domain.

## 5. Comparing Full and Compact Canonical Constructors with Overloads

Both designs below achieve the same goal: auxiliary constructors use `this(...)` and the canonical constructor enforces invariants.

### 5.1. Full Canonical: Assigning Fields Manually

In `InventoryItem.java`:

```java
import java.util.Objects;

public record InventoryItem(String sku, int quantity) {

    // Full canonical constructor.
    public InventoryItem(String sku, int quantity) {
        String normalized = Objects.requireNonNull(sku, "sku").strip();
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be >= 0");
        }

        this.sku = normalized;
        this.quantity = quantity;
    }

    public InventoryItem(String sku) {
        this(sku, 0);
    }
}
```

When writing the full canonical constructor yourself, its parameters must have the **exact names, types, and order** of the record header (`sku` then `quantity`). Inside this constructor, you must initialize the component fields directly; none may be omitted.

### 5.2. Compact Canonical: Java Assigns Fields After the Body

Equivalent version in `InventoryItem.java`:

```java
import java.util.Objects;

public record InventoryItem(String sku, int quantity) {

    public InventoryItem {
        sku = Objects.requireNonNull(sku, "sku").strip();
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be >= 0");
        }
    }

    public InventoryItem(String sku) {
        this(sku, 0);
    }
}
```

Here, **do not write** `this.sku = sku` or `this.quantity = quantity` in the compact constructor; Java handles that automatically.

**When choosing between the two forms:**

- Compact fits most cases: null checks, range checks, string normalization, or defensive copies.
- Full form is useful if you want to show the processing order and individual field assignments explicitly.
- Both play the same **canonical** role; overloaded constructors call them with `this(...)` under the exact same rules.

## 6. Exact Rules on Signatures and Visibility

### 6.1. Which Constructor Counts as Canonical?

Consider the record:

```java
public record Coordinate(double latitude, double longitude) { }
```

The canonical signature has two `double` parameters in exact order:

```java
public Coordinate(double latitude, double longitude)
```

The following forms do not have the canonical signature:

```java
Coordinate(double latitude)             // Overload: fewer parameters
Coordinate(String coordinateText)        // Overload: different type
Coordinate()                             // Overload: no parameters
```

**Merely renaming parameters does not create a new overload.** If you try writing:

```java
record Coordinate(double latitude, double longitude) {
    // INVALID: two-double signature is still the canonical signature,
    // yet parameter names do not match record components.
    Coordinate(double x, double y) {
        this.latitude = x;
        this.longitude = y;
    }
}
```

Java will reject it because an explicitly declared canonical constructor's parameters must match the component names.

Similarly, swapping two components of **the same type** does not alter the overload signature and cannot be used to add a new constructor:

```java
record Range(int start, int end) {
    // INVALID: still signature (int, int), colliding with the canonical constructor.
    // Range(int end, int start) { ... }
}
```

When you need to express two semantic meanings for the same parameter types, use a **clearly named static factory method** rather than trying to overload by renaming variables:

```java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start must be <= end");
        }
    }

    static Range startingAtZero(int end) {
        return new Range(0, end);
    }
}
```

### 6.2. Visibility of the Canonical Constructor

In Java 17, an explicitly declared canonical constructor **cannot have narrower visibility than the record**:

| Record Visibility | Canonical Constructor Visibility |
|---|---|
| `public` | Must be `public` |
| `protected` (nested record allowed to have this visibility) | `protected` or `public` |
| Package-private | Package-private or `public` |
| `private` (nested record) | Can choose any valid visibility |

Example of a public record:

```java
public record User(String name) {
    // VALID: same visibility as the record.
    public User {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("invalid name");
        }
    }
}
```

Changing `public User` to `private User` inside a `public` record causes a compilation error.

**Auxiliary constructors can choose their own visibility** depending on purpose. For example, a `private` overload might only be used by static factory methods inside the record. The "not narrower than the record" rule above applies specifically to the **canonical constructor**.

### 6.3. Specific Constraints on Canonical Constructors

An explicitly declared full canonical constructor:

- Must have parameter names and types matching the record components.
- **Cannot be a generic constructor** (cannot declare its own type parameters).
- **Cannot have a `throws` clause**.
- **Cannot contain an explicit `this(...)` or `super(...)` constructor invocation**.
- In full form, must initialize component fields according to definite assignment rules.

For a compact canonical constructor, you also cannot write `return`, `this(...)`, `super(...)`, or directly assign to component fields.

**Distinction:** A *generic* record like `record Pair<T>(T value)` is completely valid; what is forbidden is a **canonical constructor declaring its own type parameters**, not a record having type parameters.

### 6.4. Auxiliary Constructors Can Declare `throws`

An auxiliary constructor can accept different input types and declare checked exceptions. Example file `DocumentText.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public record DocumentText(String content) {

    public DocumentText {
        Objects.requireNonNull(content, "content");
    }

    public DocumentText(Path path) throws IOException {
        this(Files.readString(path));
    }
}
```

Here `DocumentText(Path)` is an **auxiliary** constructor, so it may declare `throws IOException`. It must still **begin** with `this(...)`. Java evaluates `Files.readString(path)` before invoking the canonical constructor `DocumentText(String)`. If reading the file fails, the canonical constructor is not called.

Meanwhile, the **canonical constructor** `DocumentText(String)` cannot declare `throws IOException`. If you need to report invalid data inside the canonical constructor, use an appropriate unchecked exception (such as `IllegalArgumentException`) or handle errors at the call boundary.

## 7. How to Normalize Parameters Before `this(...)` Properly in Java 17?

A very common mistake is wanting to compute an intermediate value before delegating to canonical:

```java
record Label(String text, String category) {
    Label(String text) {
        // INVALID: Java 17 does not allow this statement before this(...).
        String normalized = text.strip();
        this(normalized, "GENERAL");
    }
}
```

There are three valid approaches.

### Approach 1 — Normalize Directly in the Canonical Constructor (Usually Preferred)

```java
import java.util.Objects;

record Label(String text, String category) {
    Label {
        text = Objects.requireNonNull(text, "text").strip();
        category = Objects.requireNonNull(category, "category").strip();
        if (text.isBlank() || category.isBlank()) {
            throw new IllegalArgumentException("Fields must not be blank");
        }
    }

    Label(String text) {
        this(text, "GENERAL");
    }
}
```

Every path that creates a `Label` uses the same normalization logic; no caller can bypass the rule by calling the full constructor.

### Approach 2 — Call a Static Method in the Arguments of `this(...)`

```java
import java.util.Locale;
import java.util.Objects;

record Label(String text, String category) {
    Label(String text) {
        this(normalize(text), "GENERAL");
    }

    private static String normalize(String value) {
        return Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
    }
}
```

In Java 17, static methods not depending on the instance can be called while **evaluating argument expressions** for `this(...)`. If normalization is an invariant for all creation paths, put it in the canonical constructor rather than in only one overload.

### Approach 3 — Use Named Static Factory Methods

```java
record Distance(double meters) {
    Distance {
        if (!Double.isFinite(meters) || meters < 0) {
            throw new IllegalArgumentException("invalid meters");
        }
    }

    static Distance fromKilometers(double kilometers) {
        return new Distance(kilometers * 1000);
    }
}
```

Usage:

```java
Distance distance = Distance.fromKilometers(2.5);
System.out.println(distance.meters()); // 2500.0
```

Static factory methods are especially helpful when multiple creation paths take **the same parameter types** with different meanings. For example, do not try adding two `Distance(double)` constructors to distinguish "meters" and "kilometers": Java distinguishes overloads by signature, not by parameter names or business intent.

## 8. Auxiliary Constructors, Mutable Lists, and Record Immutability

Records have `final` component fields, but if a component points to a mutable list, external code can still mutate the list. For a record to represent a reliable snapshot, perform defensive copying **in the canonical constructor**.

```java
import java.util.List;
import java.util.Objects;

record Basket(List<String> productCodes) {

    Basket {
        productCodes = List.copyOf(
                Objects.requireNonNull(productCodes, "productCodes"));
    }

    Basket() {
        this(List.of());
    }

    Basket(String firstProductCode) {
        this(List.of(firstProductCode));
    }
}
```

Usage:

```java
import java.util.ArrayList;
import java.util.List;

class BasketDemo {
    public static void main(String[] args) {
        List<String> codes = new ArrayList<>();
        codes.add("P-1");

        Basket basket = new Basket(codes);
        codes.add("P-2");

        System.out.println(basket.productCodes()); // [P-1]
        System.out.println(new Basket());           // Basket[productCodes=[]]
        System.out.println(new Basket("P-3"));      // Basket[productCodes=[P-3]]
    }
}
```

Every auxiliary constructor delegates to the canonical constructor and passes through `List.copyOf(...)`, so no overload can accidentally skip copying. `List.copyOf` creates a structurally unmodifiable list and rejects `null` elements. If the list contains **mutable child objects**, a dedicated deep-immutability strategy is needed; `List.copyOf` does not automatically deep-copy elements.

Design point to remember: **data validation and protection rules belong in the canonical constructor**, while auxiliary constructors primarily supply defaults or adapt input formats.

## 9. Generic Records and Auxiliary Constructors

Records can declare type parameters, and overloaded constructors can use them normally:

```java
import java.util.Objects;

record Response<T>(T data, String source) {

    Response {
        Objects.requireNonNull(data, "data");
        Objects.requireNonNull(source, "source");
    }

    Response(T data) {
        this(data, "unknown");
    }
}
```

Usage:

```java
Response<String> text = new Response<>("Hello");
Response<Integer> number = new Response<>(42, "cache");

System.out.println(text);   // Response[data=Hello, source=unknown]
System.out.println(number); // Response[data=42, source=cache]
```

When a record has type parameter `T`, the corresponding canonical constructor is still `Response(T data, String source)` and `Response(T data)` is an overload. Java performs type checking at compile time; you do not rewrite constructors with a concrete type for each `T`.

One thing to watch out for: a record with constructors taking closely related reference types can cause **overload ambiguity**, especially when passing a `null` literal. For example:

```java
record Code(String value) {
    Code(Integer number) {
        this(String.valueOf(number));
    }
}

// new Code(null); // INVALID: ambiguous between Code(String) and Code(Integer)
```

Pass values with specific types, use an explicit cast when genuinely needed, or design a static factory method whose name describes the input such as `Code.fromNumber(123)`. Avoid overusing overloads if they make the API unpredictable.

## 10. Common Compile Errors

### 10.1. Not Calling `this(...)` in an Auxiliary Constructor

```java
record Person(String name, int age) {
    Person(String name) {
        // INVALID: cannot assign fields manually and stop here.
        // this.name = name;
        // this.age = 0;
    }
}
```

**Fix:**

```java
record Person(String name, int age) {
    Person(String name) {
        this(name, 0);
    }
}
```

### 10.2. Placing Statements Before `this(...)` in JDK 17

```java
record Point(int x, int y) {
    Point(int x) {
        // INVALID in Java 17:
        // System.out.println("Creating Point");
        // this(x, 0);
        this(x, 0);
    }
}
```

The `this(...)` statement must come first; if validation or transformation is needed before initialization, prefer the canonical constructor.

### 10.3. Duplicate Canonical and Compact Constructor Declarations

```java
record Name(String value) {
    // Cannot declare both canonical forms at the same time:
    //
    // Name(String value) {
    //     this.value = value;
    // }
    //
    // Name {
    //     value = value.strip();
    // }
}
```

Choose **one** of the two forms. Two canonical constructors cannot coexist.

### 10.4. Directly Assigning Component Fields in a Compact Constructor

```java
record Name(String value) {
    Name {
        // INVALID: this.value = value.strip();
        value = value.strip(); // VALID
    }
}
```

Java automatically assigns the normalized `value` parameter to `this.value` when the compact constructor finishes normally.

### 10.5. Cyclic Constructor Calls

```java
record Pair(int left, int right) {
    Pair(int only) {
        // INVALID if the no-arg overload delegates back here.
        // this();
        this(only, 0);
    }

    Pair() {
        this(0);
    }
}
```

The current version is valid because `Pair() → Pair(int) → Pair(int, int)`. Replacing `this(only, 0)` with `this()` in `Pair(int)` creates a cycle `Pair() ↔ Pair(int)` and is rejected at compile time.

### 10.6. Cannot Declare Arbitrary Instance Fields in a Record

```java
record Session(String id) {
    // INVALID: records do not allow extra instance fields.
    // private int retries;

    static final int MAX_RETRIES = 3; // VALID: static field
}
```

Constructor overloads do not turn a record into an ordinary mutable class. If data is record state, express it as a component. If a complex lifecycle or stateful object is needed, consider a regular class.

### 10.7. Do Not Use `return` or `this(...)` in a Compact Canonical Constructor

```java
record Quantity(int value) {
    Quantity {
        if (value < 0) {
            throw new IllegalArgumentException("value must be >= 0");
        }

        // INVALID:
        // return;
        // this(value);
    }
}
```

A compact constructor completes through the compiler's implicit initialization mechanism. To report invalid data, use an appropriate exception.

## 11. Organizing Constructors in Real APIs

For a public record serving multiple layers, recommended structure:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(String productId,
                        int quantity,
                        BigDecimal unitPrice) {

    // Protects data regardless of which constructor the caller picks.
    public OrderLine {
        productId = Objects.requireNonNull(
                productId, "productId").strip();
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (productId.isEmpty()) {
            throw new IllegalArgumentException("productId must not be empty");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be >= 0");
        }
    }

    // One product, default quantity 1.
    public OrderLine(String productId, BigDecimal unitPrice) {
        this(productId, 1, unitPrice);
    }

    // Used only when caller supplies unit price as a decimal string.
    public OrderLine(String productId, int quantity, String unitPrice) {
        this(productId, quantity, new BigDecimal(unitPrice));
    }

    public BigDecimal total() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Three corresponding ways to construct:

```java
OrderLine full = new OrderLine("P-1", 3, new BigDecimal("12.50"));
OrderLine defaultQuantity = new OrderLine("P-2", new BigDecimal("8.00"));
OrderLine parsedPrice = new OrderLine("P-3", 2, "7.25");

System.out.println(full.total());            // 37.50
System.out.println(defaultQuantity.total()); // 8.00
System.out.println(parsedPrice.total());     // 14.50
```

The constructor taking `String unitPrice` throws `NumberFormatException` if the string is not a valid decimal number; that matches how `BigDecimal(String)` parses. If the API needs a custom error message, replace it with a static factory method with explicit error handling or a static helper inside the `this(...)` expression.

### Design Principles to Avoid Long-Term Bugs

- Keep the overload list **small and meaningful**. Each constructor should offer a creation path callers can easily predict.
- Put shared invariants and normalization into the **canonical constructor**, avoiding duplicated checks across overloads.
- Have each auxiliary constructor call `this(...)` right at the start, favoring concise and readable arguments.
- Avoid overloads that differ only by same-typed parameters with easily confused meanings; use **named static factories** when needed.
- Control mutable data via defensive copying directly in the canonical constructor.
- Enforce visibility policy: an explicitly declared canonical constructor on a `public` record must be `public`.
- For serialization, JSON mapping, ORM, or frameworks, check how the library instantiates records and supports canonical constructors. Do not rely on a convenience constructor to enforce mandatory invariants: libraries may invoke the canonical constructor directly.

## 12. Practice Exercises

### Exercise 1 — Default Constructors

Write record `Page(int number, int size)` with:

1. A compact canonical constructor checking `number >= 1` and `1 <= size <= 100`.
2. Constructor `Page(int number)` defaulting `size = 20`.
3. Constructor `Page()` creating the first page with default size 20.
4. Run `new Page()`, `new Page(3)`, `new Page(2, 50)`; print each record.

**Suggested Solution:**

```java
record Page(int number, int size) {
    Page {
        if (number < 1) {
            throw new IllegalArgumentException("number must be >= 1");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("size must be within 1..100");
        }
    }

    Page(int number) {
        this(number, 20);
    }

    Page() {
        this(1);
    }
}
```

Note that the call chain of `new Page()` is `Page() → Page(int) → Page(int, int)`.

### Exercise 2 — Spot the Invalid Constructor

Given the code:

```java
record UserProfile(String username, int age) {
    UserProfile(String username) {
        username = username.trim();
        this(username, 18);
    }
}
```

**Question:** Why does this code fail to compile in Java 17? Fix it so every creation path validates that `username` is non-blank.

**Hint:** Move the normalization step into a compact canonical constructor; replace the overload body with `this(username, 18)` as the first statement.

**Solution:**

```java
record UserProfile(String username, int age) {
    UserProfile {
        username = java.util.Objects.requireNonNull(
                username, "username").strip();
        if (username.isBlank()) {
            throw new IllegalArgumentException("invalid username");
        }
        if (age < 0) {
            throw new IllegalArgumentException("invalid age");
        }
    }

    UserProfile(String username) {
        this(username, 18);
    }
}
```

### Exercise 3 — Distinguishing Overloads vs. Factories

You want to construct `Temperature(double celsius)` from Celsius and Fahrenheit. Writing two `Temperature(double)` constructors with different meanings is impossible because their signatures collide.

**Requirement:** keep the canonical constructor for Celsius and add a static factory `fromFahrenheit(double)`:

```java
record Temperature(double celsius) {
    Temperature {
        if (!Double.isFinite(celsius)) {
            throw new IllegalArgumentException("Temperature is not finite");
        }
    }

    static Temperature fromFahrenheit(double fahrenheit) {
        return new Temperature((fahrenheit - 32.0) * 5.0 / 9.0);
    }
}
```

Try `Temperature.fromFahrenheit(212)` and observe the Celsius value approximately `100.0`.

### Exercise 4 — Constructor Reading Data from a File

From the `DocumentText(String content)` example, add constructor `DocumentText(Path path) throws IOException` and explain:

- Why is this constructor allowed to declare `throws IOException`?
- Why is `this(Files.readString(path))` valid in Java 17?
- When `Files.readString` fails, does the canonical constructor run?

**Guidance:** It is an auxiliary constructor, `this(...)` is the first statement, and the argument is evaluated before the target constructor is invoked. If reading the file throws an exception, the invocation stops there.

## 13. Quick Summary

| Question | Java 17 Rule |
|---|---|
| How many canonical constructors does a record have? | Exactly one; implicitly generated, written in full, or written compact |
| Are constructors without all components allowed? | Yes; those are auxiliary constructors with signatures different from canonical |
| What must an auxiliary constructor do? | **Begin** with `this(...)` calling another constructor of the same record |
| Can `this(...)` chain across multiple overloads? | Yes, but the chain must end at canonical and must not form a cycle |
| Can statements appear before `this(...)`? | **No in Java 17** |
| Can `super(...)` be called in an overload? | No |
| Can a compact constructor assign `this.field`? | No; assign the component parameter, and Java assigns the field |
| Can both compact and full canonical be declared? | No; duplicate canonical constructor |
| Can a canonical constructor declare `throws` for checked exceptions? | Cannot declare a `throws` clause |
| Can an auxiliary constructor declare `throws`? | Yes, following normal constructor rules |
| Can an explicit canonical constructor on a `public record` be `private`? | No; the canonical constructor must be `public` |
| Where should validation live? | In the canonical constructor so all creation paths comply |

## 14. Official Java 17 Documentation

- [Java Language Specification 17 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record syntax and constraints.
- [JLS 17 — `8.10.4 Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical constructors, auxiliary constructors, and the requirement that auxiliary constructors **begin** with an alternate constructor invocation.
- [JLS 17 — `8.10.4.1 Normal Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.1): parameter names/types, `throws` restrictions, exclusion of `this(...)` and `super(...)`.
- [JLS 17 — `8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.2): parameter normalization and implicit field assignments.
- [JLS 17 — `8.8.7.1 Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)` and `super(...)`.
- [JEP 395 — Records](https://openjdk.org/jeps/395): records standardized in Java 16 and fully supported in Java 17.
- [dev.java — Using Records to Model Immutable Data](https://dev.java/learn/using-record-to-model-immutable-data/): examples and guides on canonical/compact constructors.

**Key takeaway:** Auxiliary constructors make records more convenient to instantiate, but do not replace the canonical constructor. In **Java 17**, every overload must start with `this(...)`; the canonical constructor completes initialization of all record components and is the right place to keep data invariants true.
