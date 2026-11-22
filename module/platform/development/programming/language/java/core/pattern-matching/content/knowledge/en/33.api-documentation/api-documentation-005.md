# Documenting Record Components in Java: Javadoc, Contracts, and Clear APIs (Java 21)

## 1. Why Do Record Components Need Dedicated Documentation?

A record represents a set of **state-defining values** through the component list in its header:

```java
public record Point(int x, int y) {}
```

Java provides a canonical constructor, `x()`/`y()` accessors, and `equals`, `hashCode`, and `toString` methods based on the components. However, simply looking at the names `x` and `y` does not tell you the coordinate system, unit of measurement, valid range, nullability, or the meaning of a data change.

For a public API, **a component is not just a field for holding data**. It simultaneously affects:

- The parameters and order of the canonical constructor;
- The accessor with the same name as the component;
- The shape of record patterns in Java 21;
- The default generated `equals`/`hashCode` and `toString` representation;
- The schema exposed by some serialization, reflection, or mapping libraries;
- Compatibility when adding, removing, renaming, or changing the type of a component.

Therefore, a record's documentation needs to answer **"what does this value mean, who can create it, read it, and what are they allowed to assume?"** rather than merely repeating the Java names and types.

An under-documented example:

```java
public record Price(long amount, String currency) {}
```

Is `amount` in dollars, cents, or minor currency units? Are negative numbers accepted? Can `currency` be `null`? Is ISO 4217 required? Is `"usd"` normalized to `"USD"`? API users cannot infer those details from the signature.

**Lesson objectives:** write Javadoc in the right place using `@param` for record components; clearly state meaning, units, invariants, nullability, normalization, and ownership; document compact constructors, custom accessors, generic components, and record patterns; and use the `javadoc` tool to detect errors and inspect the generated HTML.

This lesson belongs to the **API and Documentation** section of Java Core Pattern Matching. `record` has been a standard feature since **Java 16** (JEP 395), while record patterns and pattern matching for `switch` became official in **Java 21** (JEP 440, JEP 441). The full program uses **JDK 21+**; generating Javadoc documentation also applies to records that do not use pattern matching.

## 2. Core Syntax: `@param` on the Record's Javadoc

For records, the standard and **standard doclet**-supported approach is to place Javadoc **immediately before the `record` declaration**, then use `@param` with **the exact name of each component**:

```java
/**
 * A coordinate on a plane measured in meters.
 *
 * @param x abscissa, measured in meters; must be non-negative
 * @param y ordinate, measured in meters; must be non-negative
 */
public record Point(int x, int y) {
    public Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException(
                "Coordinates must be non-negative");
        }
    }
}
```

In this example:

- The opening description explains the **overall meaning of the record**.
- `@param x` explains the `x` component, without needing to create a separate field Javadoc.
- `@param y` explains the `y` component.
- The compact constructor enforces the **non-negative** promise.

`@param` appears in the Javadoc of the **type declaration**, but for records, the standard doclet uses it to display component information. This is the core convention to remember. Do not write `@return` directly on a `record`'s Javadoc: `@return` is for methods, not types.

**Exact naming is required:** for `record Point(int x, int y)`, writing `@param length` instead of `@param x` references the wrong target and may trigger a doclint warning. When renaming a component, you must update the corresponding `@param`.

### A Record Only Needs to Describe Its Contract, Not Be Verbose

A concise yet useful example:

```java
/**
 * Customer identifier normalized for value-based comparison.
 *
 * @param value non-null/non-blank customer identifier, stripped of leading
 *              and trailing whitespace on construction; case is preserved
 */
public record CustomerId(String value) {
    public CustomerId {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Blank customerId");
        }
    }
}
```

Here the actual behavior matches the documentation: `strip()`, not `toUpperCase()`. If the business decides identifiers are case-insensitive, both the implementation and the contract must be updated; you cannot just change the description text.

### Do Not Write Regular Comments Thinking They Are Javadoc

```java
// Currency code.
public record Currency(String code) {}
```

A `//` comment may help someone reading the source, but **it is not Javadoc** processed as an API documentation comment. Use `/** ... */` before the record declaration when you want to generate official documentation pages.

## 3. Properties to State for Each Component

Good Javadoc does not necessarily need every single item, but it must clarify **the contracts that users cannot infer from the type**.

| Aspect | Question to answer | Example description |
| --- | --- | --- |
| Domain meaning | What does the component represent? | `customerId` is the identifier in the sales system |
| Unit of measurement | What unit is this number measured in? | `minorUnits` is the smallest unit of the currency |
| Valid range | Can it be negative, zero, or out of bounds? | `quantity >= 1` |
| Nullability | Is `null` allowed and what does it mean? | `address` is required; `notes` may be null meaning not entered |
| Normalization | Does the constructor transform the input? | `currency` is stripped via `strip()` and uppercased using `Locale.ROOT` |
| Immutability | Does the component hold a mutable reference? | `lines` is an unmodifiable copy |
| Collection structure | Can the list be empty or contain null elements? | `lines` is non-empty, elements are non-null |
| Equality/ordering | Does order or scale matter? | `List.equals` is order-sensitive; `BigDecimal.equals` is scale-sensitive |
| Versioning and compatibility | How does the API change if a component is added? | May break constructor, accessors, and record patterns |
| Security | Does it contain sensitive information? | Do not log tokens or rely on `toString()` to mask data |

**Do not fabricate promises.** `record` only guarantees that the component's backing field is structurally final; it does **not** create deep immutability. If a component is `List<MutableItem>` and only uses `List.copyOf`, the elements can still be mutated through another reference. Javadoc should not claim "the entire object graph is immutable" unless there is real protection in place.

### Units Are Part of the Contract, Not a Minor Detail

Compare:

```java
/** @param amount monetary amount */
record Money(long amount) {}
```

with:

```java
/**
 * Non-negative monetary amount in the currency's smallest unit.
 *
 * @param minorUnits number of minor units, must be 0 or greater
 * @param currency three-letter currency code uppercased on construction
 */
record Money(long minorUnits, String currency) {}
```

The second snippet prevents confusion between 1,000 major units and 1,000 minor units. However, a three-letter regex **is not enough to validate ISO 4217**; if the implementation only checks `[A-Z]{3}`, the documentation must accurately state "three-letter" rather than claiming all values are valid ISO currency codes.

## 4. Stating Nullability Explicitly: Contract, Not Just Annotations

Java allows passing `null` to a reference-typed record component if the constructor does not forbid it:

```java
record RawContact(String email, String phone) {}

RawContact input = new RawContact(null, null); // Syntactically valid.
```

If the domain requires `email`, the documentation should state **must not be null** and the constructor should validate it:

```java
/**
 * Validated contact information.
 *
 * @param email required email address, non-null and non-blank
 * @param phone optional phone number; null means not provided
 */
record Contact(String email, String phone) {
    Contact {
        email = java.util.Objects.requireNonNull(email, "email").strip();
        if (email.isEmpty()) {
            throw new IllegalArgumentException("Blank email");
        }
    }
}
```

Distinguish between:

- **Component type:** `String` by itself does not indicate non-null.
- **Javadoc contract:** the description communicates expectations and business meaning.
- **Constructor validation:** enforces the expectation upon object creation.
- **Annotations:** `@Nullable`/`@NonNull` from libraries can help tooling analysis, but Java has no universal non-null annotation with runtime enforcement across all applications.

When a component is nullable, state **what null means**. "May be null" without semantics often forces callers to guess. If missing data has multiple distinct business states, consider an enum, sealed variants, or a result type instead of a single ambiguous `null`.

### Record Patterns Do Not Automatically Eliminate Null Components

```java
if (value instanceof RawContact(var email, var phone)) {
    // email and phone have type String, but can still be null.
}
```

`var email` binds the component value, including `null`. With a nested record pattern:

```java
record Customer(RawContact contact) {}

if (value instanceof Customer(RawContact(var email, var phone))) {
    // Only matches if Customer.contact is non-null and is a RawContact.
}
```

If `contact == null`, the nested pattern `RawContact(...)` does not match and the `if` body does not execute. However, if `contact` is non-null and `email == null`, the pattern still matches; `email` can be null. Therefore, component documentation is crucial for code using record patterns: **the static type of a pattern variable is not a guarantee that its value is non-null**.

## 5. Documenting Validation and Normalization in Canonical Constructors

Javadoc `@param` on a record describes **the components and overall contract**. If there is a compact canonical constructor or explicit constructor, document any significant object-creation behavior and thrown exceptions.

Example:

```java
/**
 * Product code normalized for value-based comparison.
 *
 * @param code normalized code, ASCII uppercase letters/digits/hyphens;
 *             must be 2 to 20 characters long
 */
public record ProductCode(String code) {

    /**
     * Normalizes the input code before storing state.
     *
     * @throws NullPointerException if code is null
     * @throws IllegalArgumentException if the normalized code has an invalid format
     */
    public ProductCode {
        code = java.util.Objects.requireNonNull(code, "code")
            .strip()
            .toUpperCase(java.util.Locale.ROOT);
        if (!code.matches("[A-Z0-9-]{2,20}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
```

**Remember tag placement:**

- `@param code` on the **record's** Javadoc describes the component.
- `@throws` belongs to the Javadoc **of the constructor or method** that may throw the exception.
- If documenting an **explicit canonical constructor with a parameter list**, `@param` in the constructor's Javadoc describes that constructor parameter. With a compact constructor, the parameter list is inferred from the record header; avoid repeating descriptions that conflict with `@param` on the type.
- Do not add `@throws` to the record type's Javadoc expecting the standard doclet to treat it as a constructor tag: `@throws` has method/constructor context.

### Compact Constructors Do Not Directly Assign Component Fields

In `public ProductCode { ... }`, the `code` parameter is normalized. When the constructor completes normally, the compiler assigns the final value of the parameter to the component field. Do not write `this.code = code` inside a compact constructor body. Normalization descriptions should reflect the **stored value**, not just the "initial input".

### Constructors May Accept Input Different from What the Accessor Returns

If you call:

```java
var product = new ProductCode(" ab-12 ");
System.out.println(product.code()); // AB-12
```

then API users have every right to expect the accessor to return the **normalized code**. Thus `@param code` should mention normalization; the Javadoc of an explicit accessor (if present) must also reflect the normalized result.

## 6. Generated Accessors and Explicitly Declared Accessors

A record has accessors with the same names as its components:

```java
record Range(int lower, int upper) {}
// Accessors: lower() and upper().
```

These are **not** JavaBean setters/getters named `getLower()`. Documentation readers need to know the accessor they will call is `lower()`, and its return value has the declared type.

**If the accessor is implicitly generated**, there is no need to manually write a method just to attach duplicate Javadoc. Focus on describing the component in the record's `@param` and inspect the HTML generated by `javadoc`.

When **explicitly declaring an accessor** because it has behavior worth explaining, write Javadoc on that method using `@return` in the proper context:

```java
/**
 * Place name normalized by stripping leading and trailing whitespace.
 *
 * @param name required name; will be normalized via strip()
 */
public record Place(String name) {
    public Place {
        name = java.util.Objects.requireNonNull(name, "name").strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("Blank place name");
        }
    }

    /**
     * Returns the normalized place name.
     *
     * @return non-null and non-blank name
     */
    public String name() {
        return name;
    }
}
```

A custom accessor must have the exact signature matching the component (here `public String name()`). Do not confuse a record component with a field that can be arbitrarily hidden or mutated via an accessor. The record specification expects accessors to consistently reflect components; especially when using record patterns, accessors are invoked for deconstruction.

**Performance note:** do not put heavy I/O or business side effects inside an accessor just to "compute on read", because `Record(var x)` can invoke the accessor. If an accessor throws an exception during record pattern matching, Java 21 specifies a `MatchException` wrapping the original cause. Public documentation and API design should treat accessors as reliable data-reading paths with dependable contracts.

## 7. Documenting Collection Components: Ownership and Shallow Immutability

A record with a `List<T>` component can easily be misunderstood. Consider:

```java
record UnsafeOrder(java.util.List<String> lines) {}
```

The `lines` field is final, but callers can:
- Mutate the input list after creating the record;
- Mutate the list obtained from `lines()` if the list is mutable;
- Cause the record's `equals`/`hashCode` to change when the list changes.

Therefore, define ownership in the documentation, then implement it properly:

```java
/**
 * Snapshot of SKU codes in the exact order received.
 *
 * @param items non-null, non-empty list with no null elements;
 *              copied into an unmodifiable list
 */
record SkuSnapshot(java.util.List<String> items) {
    SkuSnapshot {
        items = java.util.List.copyOf(
            java.util.Objects.requireNonNull(items, "items"));
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty items");
        }
    }
}
```

With immutable `String`, the copied list preserves a structurally stable snapshot and does not expose a mutable list through the default accessor.

**Do not describe `List.copyOf` as a deep copy.** If the component is `List<MutableAddress>`, the elements remain mutable even though the list itself does not allow adding or removing. Javadoc must state the actual level of protection and consider using immutable value objects for elements.

### Arrays and Equality

`record Bytes(byte[] data)` is even riskier: arrays are mutable and a record's default `equals`/`hashCode` uses reference equality for arrays, not byte-content comparison. If the domain requires content-based value semantics, you must defensively clone on input/output and override `equals`/`hashCode` accordingly, or choose a different wrapper. Javadoc cannot magically make an array immutable.

### Does Element Order Matter?

`List.equals` compares by order. If the domain treats two lists with the same elements in different orders as equivalent, use an appropriate model (such as a `Set` or normalizing the order) and state it clearly. You cannot simply write "unordered" in `@param` while keeping a `List` with order-sensitive equality and pretend the contract is enforced.

## 8. Documenting Generic Records, Enums, and Complex Component Types

Records support generics:

```java
/**
 * A processed paginated result.
 *
 * @param <T> element type of the result list
 * @param items list of elements, non-null; order is preserved
 * @param total total number of results, must be non-negative
 */
public record Page<T>(java.util.List<T> items, long total) {
    public Page {
        items = java.util.List.copyOf(
            java.util.Objects.requireNonNull(items, "items"));
        if (total < 0) {
            throw new IllegalArgumentException("Negative total");
        }
    }
}
```

Here **`@param <T>`** documents the type parameter while **`@param items`** documents the record component. They are two different things. Good Javadoc should document both if the name `T` is not self-explanatory.

For `Page<T>`:
- `List.copyOf` rejects null elements;
- It does not make elements of type `T` immutable;
- `total` is the total count of results, not necessarily the number of items on the page;
- If the invariant `items.size() <= total` is required, **enforce** it in the constructor before documenting it.

An enum component can convey much of its value domain on its own:

```java
enum State { CREATED, PAID, CANCELLED }
/** @param state order status, must be non-null */
record OrderStatus(State state) {}
```

However, Javadoc `@param state` **does not automatically prevent** `new OrderStatus(null)`. If the contract is non-null, there must be validation or a convention with an appropriate checking mechanism.

### Annotations and Other Tooling

An annotation on a record component can apply to `FIELD`, `METHOD`, `PARAMETER`, or `RECORD_COMPONENT` depending on its `@Target`; propagation to generated members follows specific rules. **Do not assume every annotation propagates everywhere**, or that a library `@NotNull` will always generate a runtime check. Verify your application's actual toolchain and keep Javadoc consistent with the constructor.

## 9. Record Patterns Make Component Documentation Even More Important

Java 21 allows:

```java
record GeoPoint(double latitude, double longitude) {}

if (value instanceof GeoPoint(var lat, var lon)) {
    System.out.println(lat + ", " + lon);
}
```

The components in the header determine the **extraction order**. If `latitude` and `longitude` both have type `double`, the compiler will not catch someone accidentally reading `lon` as latitude in other logic. Documentation must state:
- `latitude` is **latitude** in degrees, valid range -90 to 90 if enforced by the constructor;
- `longitude` is **longitude** in degrees, valid range -180 to 180 if enforced by the constructor;
- Reference system conventions if the domain depends on a coordinate system;
- Nullability if the component is a reference type, or special numeric domains such as `NaN`/`Infinity` if relevant.

Example adding validation:

```java
/**
 * A coordinate pair in geographic degrees.
 *
 * @param latitude latitude, finite number from -90 to 90 degrees
 * @param longitude longitude, finite number from -180 to 180 degrees
 */
record GeoPoint(double latitude, double longitude) {
    GeoPoint {
        if (!Double.isFinite(latitude) || latitude < -90 || latitude > 90
                || !Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid coordinates");
        }
    }
}
```

**Why mention `NaN`?** Both `<` and `>` comparisons with `NaN` return `false`. If you only write `latitude < -90 || latitude > 90`, `NaN` slips through. When documentation promises a "finite number", the implementation must check `Double.isFinite`.

### Components Extracted from Nested Records

```java
record Route(String id, GeoPoint start, GeoPoint finish) {}

if (value instanceof Route(
        var id,
        GeoPoint(var startLat, var startLon),
        GeoPoint(var endLat, var endLon))) {
    System.out.println(id);
}
```

The pattern requires `Route`, `start`, and `finish` to be non-null instances of their respective records. If the `start` component is nullable, the nested `GeoPoint(...)` does not match when it is null. Documentation for `Route.start`/`Route.finish` should clearly state those invariants; do not rely solely on nested patterns as a substitute for validation.

**API principle:** Record patterns are consumers of existing contracts. They do not fix contracts and do not "protect" components that the constructor failed to validate.

## 10. Standalone Java 21 Example: Records, Javadoc, and Pattern Matching

The program below demonstrates how to write Javadoc for:
- Record components with `@param` directly on the record declaration;
- Compact constructors documenting normalization and exceptions;
- Defensively copied collection components;
- Explicit accessors with `@return`;
- A computation method with its own Javadoc;
- Pattern matching for `switch` using the exact component order.

Create the file **`RecordComponentDocumentationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

/**
 * Demonstrates API contracts for record components.
 *
 * @since 1.0
 */
public class RecordComponentDocumentationDemo {

    /**
     * Normalized product code; used to identify a product type.
     *
     * @param value normalized product code, consisting of 2-20
     *              ASCII A-Z, 0-9, or hyphen characters; non-null
     */
    public record ProductCode(String value) {

        /**
         * Normalizes and validates the product code before storing.
         *
         * @throws NullPointerException if value is null
         * @throws IllegalArgumentException if the code has an invalid format
         */
        public ProductCode {
            value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
            if (!value.matches("[A-Z0-9-]{2,20}")) {
                throw new IllegalArgumentException(
                    "Invalid product code");
            }
        }
    }

    /**
     * An order line item with a positive product quantity.
     *
     * @param code required product code, non-null
     * @param quantity number of product units, must be greater than 0
     */
    public record LineItem(ProductCode code, int quantity) {

        /**
         * Validates the code and quantity.
         *
         * @throws NullPointerException if code is null
         * @throws IllegalArgumentException if quantity is not positive
         */
        public LineItem {
            Objects.requireNonNull(code, "code");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "Quantity must be positive");
            }
        }
    }

    /**
     * Snapshot of an order's line items at creation time.
     *
     * @param id order identifier after stripping leading/trailing whitespace,
     *           required non-null and non-blank
     * @param lines non-null, non-empty list with no null elements;
     *              copied into an unmodifiable list preserving order
     */
    public record OrderSnapshot(String id, List<LineItem> lines) {

        /**
         * Normalizes id and copies the input list.
         *
         * @throws NullPointerException if id or lines is null,
         *                              or lines contains a null element
         * @throws IllegalArgumentException if id is blank or
         *                                  the list is empty
         */
        public OrderSnapshot {
            id = Objects.requireNonNull(id, "id").strip();
            if (id.isEmpty()) {
                throw new IllegalArgumentException("Blank order id");
            }
            lines = List.copyOf(
                Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Empty lines");
            }
        }

        /**
         * Computes the total product quantity across all line items.
         *
         * @return sum of quantity across all lines; always positive
         * @throws ArithmeticException if the sum overflows int range
         */
        public int totalUnits() {
            int total = 0;
            for (LineItem item : lines) {
                total = Math.addExact(total, item.quantity());
            }
            return total;
        }
    }

    /**
     * City name with leading and trailing whitespace stripped.
     *
     * @param name non-null/non-blank name after normalization
     */
    public record City(String name) {

        /**
         * Normalizes the city name on creation.
         *
         * @throws NullPointerException if name is null
         * @throws IllegalArgumentException if name is blank
         */
        public City {
            name = Objects.requireNonNull(name, "name").strip();
            if (name.isEmpty()) {
                throw new IllegalArgumentException("Blank city");
            }
        }

        /**
         * Returns the normalized city name.
         *
         * @return non-null, non-blank name
         */
        public String name() {
            return name;
        }
    }

    /**
     * Interprets a value using Java 21 record patterns.
     *
     * @param value value to classify, may be null
     * @return short description for the received data type
     */
    public static String describe(Object value) {
        return switch (value) {
            case null -> "null";

            case OrderSnapshot(var id, var lines)
                    when lines.size() > 1 ->
                id + ": " + lines.size() + " dòng";

            case OrderSnapshot(var id, var lines) ->
                id + ": 1 dòng";

            case City(var name) ->
                "Thành phố: " + name;

            default -> "khác";
        };
    }

    /**
     * Runs API demonstration scenarios.
     *
     * @param args command-line arguments, unused
     */
    public static void main(String[] args) {
        List<LineItem> source = new ArrayList<>();
        source.add(new LineItem(new ProductCode(" pen "), 2));

        OrderSnapshot first = new OrderSnapshot(" OD-01 ", source);
        source.add(new LineItem(new ProductCode("BOOK"), 4));

        System.out.println("Mã: "
            + first.lines().get(0).code().value());
        System.out.println("Số dòng: " + first.lines().size());
        System.out.println("Tổng món: " + first.totalUnits());
        System.out.println(describe(first));

        OrderSnapshot second = new OrderSnapshot(
            "OD-02",
            List.of(
                new LineItem(new ProductCode("pen"), 1),
                new LineItem(new ProductCode("book"), 3)));

        System.out.println(describe(second));
        System.out.println(describe(new City(" Huế ")));

        try {
            first.lines().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Danh sách không thể sửa");
        }

        try {
            new ProductCode(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Mã rỗng bị từ chối");
        }

        System.out.println(describe(null));
        System.out.println(describe(123));
    }
}
```

Compile and run in the directory containing the file, using **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 RecordComponentDocumentationDemo.java
java RecordComponentDocumentationDemo
```

**Exact expected output:**

```text
Mã: PEN
Số dòng: 1
Tổng món: 2
OD-01: 1 dòng
OD-02: 2 dòng
Thành phố: Huế
Danh sách không thể sửa
Mã rỗng bị từ chối
null
khác
```

### Analyzing the Relationship Between Javadoc and Behavior

1. `ProductCode(" pen ")` produces `"PEN"`. `@param value` describes the stored format; the compact constructor normalizes with `strip` and `Locale.ROOT`, then checks the regex.
2. `LineItem.quantity` must be positive. The condition is enforced in the constructor, not just written in Javadoc.
3. `OrderSnapshot.lines` is an unmodifiable list. Adding an element to `source` after creation does not change `first.lines()`, so only one line remains and total units is 2.
4. `totalUnits()` uses `Math.addExact`: if the integer sum exceeds `int` range, it throws `ArithmeticException` just as the method documentation states, instead of silently overflowing.
5. `City.name()` is an explicit accessor with `@return` Javadoc, returning the name normalized by the constructor.
6. `describe` uses `OrderSnapshot(var id, var lines)`: component order in the pattern matches the header; the guarded branch precedes the general branch of the same type.
7. Explicit `case null` handles a null selector. Do not rely on `default` to catch null in a pattern-matching switch.

The objects in the example only carry illustrative data and do not yet represent a full order domain with transactions, persistence, pricing, or payment status.

## 11. Generating HTML Documentation with the `javadoc` Tool

With JDK 21 installed, use the same Java file from section 10:

```bash
javadoc -d api-doc -public -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all RecordComponentDocumentationDemo.java
```

This command:
- Reads documentation comments in the source;
- Generates HTML into the `api-doc` directory;
- Preserves UTF-8 encoding so Vietnamese diacritics are handled properly;
- Generates only the public API via `-public`;
- Enables Javadoc checks via `-Xdoclint:all` (e.g., missing tags, broken references, invalid HTML or Javadoc syntax).

**How to manually inspect after running:**

1. Open the HTML page for `RecordComponentDocumentationDemo` and view the public nested records section.
2. Open `ProductCode` and find the description for the `value` component; verify normalization against the constructor.
3. Open `LineItem` to check the `quantity > 0` contract and exceptions.
4. Open `OrderSnapshot` to read the `lines` description regarding null/ownership, and `totalUnits()` regarding overflow.
5. Open `City` to inspect the `name()` accessor with `@return`.
6. Check `javadoc` warnings rather than relying solely on the `javac` exit code.
7. Update or fix Javadoc and regenerate HTML to verify. Avoid editing generated HTML by hand when the source is the source of truth.

`javac` checks **Java syntax and types**, while `javadoc`/doclint helps verify many aspects of **API documentation**. No tool can completely prove that "input is always normalized" holds across all runtime branches without code and tests.

### Wrong `@param` Name and Missing Content

Example record:

```java
/**
 * A quantity.
 *
 * @param count number of elements
 */
record Quantity(int quantity) {}
```

`@param count` does not match the name `quantity`; a Javadoc tool that checks tag references may report an error or warning. The correct way:

```java
/** @param quantity number of elements */
record Quantity(int quantity) {}
```

Do not disable doclint entirely to hide issues if your goal is to publish high-quality documentation.

## 12. Common Javadoc Tags and Where to Use Them Correctly

| Tag | Where to place? | Example purpose |
| --- | --- | --- |
| `@param componentName` | `record`'s Javadoc | Describe a record component |
| `@param <T>` | Generic record's Javadoc | Describe a type parameter |
| `@param parameterName` | Constructor/method Javadoc | Describe an actual constructor/method parameter |
| `@return` | Method/accessor Javadoc | Explain the return value |
| `@throws` / `@exception` | Constructor or method Javadoc | Exception conditions; prefer `@throws` |
| `@since` | Relevant type or member | API version when it was introduced |
| `@see` | Type/member | Reference link to related API |
| `{@link ...}` | Appropriate Javadoc body | Clickable reference to a type/member |
| `{@code ...}` | Javadoc body | Display code/literals without HTML interpretation |
| `{@literal ...}` | Javadoc body | Display literals without code font |
| `{@inheritDoc}` | Method genuinely inheriting valid docs | Not used by default for record components |

**Distinguish `@param` on a type vs. on a method:** For a record, `@param` on the record declaration refers to its components. On a method, `@param` refers to method parameters. It is not a way to write Javadoc tags directly for a hidden field inside the record.

**Avoid `@return` on a record:** A record declaration has no return value; accessor methods do. Adding `@return` directly before a `record` declaration puts the tag in the wrong Javadoc context.

**Link to the right target:** To refer to an accessor, `{@link #name()}` inside `City`'s Javadoc can point to the accessor method; a record component in the header is not a method reference target using a plain field name.

## 13. Documentation and Backward Compatibility

A record carries a contract about its **component list**. Changing:

```java
public record Point(int x, int y) {}
```

to:

```java
public record Point(int x, int y, int z) {}
```

is not just adding one line of Javadoc. This change can affect:
- Canonical constructor calls: `new Point(1, 2)` no longer compiles without an overloaded constructor.
- Record patterns: `Point(var x, var y)` no longer matches the arity of the 3D record.
- Accessors, component descriptors, and reflection.
- Default `equals`, `hashCode`, and `toString` because the component set changed.
- Some external library schemas, serialization, or mappers.

**Documentation changes must go hand in hand with API review and tests.** Component names, order, and meaning are part of the public API design. For widely used APIs, you might introduce a new record like `Point3D`, an intentional compatibility constructor, or a new DTO version, instead of silently breaking existing callers.

If you **change the meaning** of a component without changing its signature, the risk is even harder to spot: `amount` changing from "cents" to "dollars" is still a `long` and `javac` will not report an error. Javadoc with clear units, specific names like `minorUnits`, and contract tests reduce such mistakes.

## 14. Review Checklist for Record Component Javadoc

| Question | Desired outcome |
| --- | --- |
| Is Javadoc placed immediately before the record declaration? | Uses `/** ... */`, not `//` |
| Does each component have a `@param` with the exact name? | None missing, no stale names after refactoring |
| Does the overall record description state domain meaning? | No meaningless filler like "holds data" |
| Do numeric values have units and valid ranges? | E.g., `minorUnits >= 0`, explicit unit |
| Do reference types have a null contract? | States required, optional, and meaning of null |
| Is normalization accurately documented? | `strip`, uppercase, rounding if actually performed |
| Do collections state ownership and null policy? | Copy, unmodifiable, ordering, null elements |
| Is deep immutability over-promised? | Distinguishes final references from mutable elements |
| Does the constructor enforce invariants? | Javadoc matches actual validation |
| Do custom accessors document behavior and `@return`? | Does not contradict stored state |
| Are exceptions documented in the right place? | `@throws` on constructor/method |
| Do record patterns use the exact component order? | Does not swap two components of the same type |
| Was `javadoc -Xdoclint:all` checked? | No ignored reference/tag warnings |
| Was the generated HTML inspected? | Content is readable and sufficient for API users |
| Were record changes reviewed for compatibility? | Constructors, patterns, equality, schemas |

### Quick-Read Rule

For a new record, a reviewer should be able to answer within one pass:
1. What is this value?
2. What does each component measure/represent?
3. How is a valid instance constructed?
4. What can be null or mutated?
5. What in the API depends on component order/count?

If these cannot be answered, strengthen the **contract in names/types/Javadoc/constructors**, rather than merely adding another generic paragraph.

## 15. Common Pitfalls

**Pitfall 1 — Missing component `@param`.** A record has two or three components but only a one-line Javadoc "record data". Users do not know the units or value ranges. Add `@param` with exact names.

**Pitfall 2 — Writing `@return` directly on the record.** That is a method tag, not for a type declaration. Place `@return` on an accessor/method when needed.

**Pitfall 3 — Documenting non-null while the constructor still allows null.** Javadoc does not generate runtime checks. Use `Objects.requireNonNull` or appropriate validation, and write tests.

**Pitfall 4 — Claiming "immutable" when holding a mutable list.** A final reference does not freeze child objects. State ownership and add defensive copies if that is an invariant.

**Pitfall 5 — Wrong unit documentation.** `amount=1000` can be mistaken for 1000 dollars instead of 1000 cents. Name it `minorUnits`/`cents` and document it accurately.

**Pitfall 6 — Normalization docs mismatch behavior.** Documenting "uppercased" when the constructor only calls `strip`, or vice versa. Test inputs requiring normalization and update code/docs together.

**Pitfall 7 — Using old `@param` names after refactoring.** The header changed from `value` to `code` but the doc tag still says `value`. Enable doclint and update immediately.

**Pitfall 8 — Generic type parameter left unexplained.** `Page<T>` has `@param items` but lacks `@param <T>` even though `T` has specific domain meaning.

**Pitfall 9 — Adding a record component and forgetting API consumers.** Constructors and record patterns change, `equals`/`hashCode` change; review compatibility and tests.

**Pitfall 10 — Custom accessor doing expensive work or silently throwing.** Pattern-matching code can call accessors. If unusual behavior exists, reconsider the design first; Javadoc cannot replace a consistent API.

**Pitfall 11 — Editing generated Javadoc HTML instead of source.** Regenerating overwrites changes. Edit source comments and re-run `javadoc`.

**Pitfall 12 — Mixing Javadoc with internal TODO comments.** Public documentation should describe the current contract, not contain placeholders or sensitive infrastructure details.

## 16. Practice Exercises

**Exercise 1 — Document a component.** Given `record Temperature(double celsius)`, write `@param celsius` including the unit °C and how `NaN`/`Infinity` are handled. If you want to forbid non-finite values, add `Double.isFinite(celsius)` in a compact constructor.

**Exercise 2 — Null contract.** Design `record Contact(String email, String phone)` so `email` is required while `phone` may be null. Write Javadoc distinguishing "absent" from "blank", and test whether the constructor rejects a null email.

**Exercise 3 — Generate HTML.** Run `javadoc -Xdoclint:all` on `RecordComponentDocumentationDemo.java`, open the `OrderSnapshot` page, and compare the `lines` description with `List.copyOf` behavior. Locate the documentation section for `totalUnits()`.

**Exercise 4 — Test a tag error.** Change `@param quantity` to `@param count` in `LineItem` without changing the header. Re-run Javadoc and observe the warning/how the broken reference is detected. Restore the correct tag.

**Exercise 5 — Record pattern.** Write `case GeoPoint(var lat, var lon)` on a validated `GeoPoint`. Explain why component documentation still needs to state the unit is degrees and `NaN` is disallowed.

**Exercise 6 — Collection ownership.** Create `record Tags(List<String> values)`, use `List.copyOf`, and write Javadoc promising a non-null, unmodifiable list with no null elements. If `String` is replaced with `MutableTag`, which promise must be revised?

**Exercise 7 — API evolution.** Add `discount` to `LineItem`. List affected consumers: constructor, record patterns, equality, documentation, and schema; propose a versioning strategy.

**Exercise 8 — Documentation vs. validation.** Find a `@param` stating "must be positive" where the constructor does not check it. Write a test exposing negative values and add validation in the right place. Conclude why Javadoc does not replace tests.

**Exercise 9 — Custom accessor.** Add an explicit accessor `public String name()` to a normalized record. Write an appropriate `@return`; explain why it must not arbitrarily return a value inconsistent with the stored component.

## 17. Summary

**Record components are part of the API contract, not an implementation detail to omit from documentation.** When writing Javadoc for records:

- Place the documentation comment **immediately before `record`**.
- Use **`@param componentName`** with exact names to describe each component, and **`@param <T>`** for generic record type parameters.
- Clearly state **meaning, units, value ranges, nullability, normalization, ownership, and immutability** when they matter.
- Document **`@throws`** on constructors/methods that enforce validation; use **`@return`** on accessors or methods, never `@return` on the record declaration.
- Ensure promises are **enforced** by constructors, defensive copies, and tests; Javadoc does not enforce invariants on its own.
- Treat record patterns as consumers of component order and types.
- Run **`javadoc -Xdoclint:all`**, inspect the HTML, and review backward compatibility whenever changing the header.

### References

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [Oracle Java 21 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Java SE 21 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
