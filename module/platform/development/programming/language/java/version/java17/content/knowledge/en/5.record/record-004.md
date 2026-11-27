# Validating and Normalizing Parameters in Record Constructors — Java 17

In Java 17, `record` is a way to declare a data type used to represent a fixed set of values. For example, `record User(String name, int age)` has two **record components**: `name` and `age`. Java automatically generates the corresponding `private final` fields, accessors `name()` and `age()`, along with `equals()`, `hashCode()`, and `toString()`.

However, **`final` does not mean input data is always valid**. The following code can still create nonsensical state if parameters are not validated:

```java
record User(String name, int age) {}

User a = new User(null, -5);
User b = new User("   ", 20);
```

For records carrying business constraints, the constructor is the appropriate place to **validate** and **normalize** parameters before storing them into components. That way, every public constructor call follows the exact same rules rather than relying on callers to sanitize data themselves.

This lesson focuses on **canonical constructor** and **compact canonical constructor** syntax, how to use these two forms to protect data invariants, how to handle collections, and common mistakes in Java 17.

## 1. How Does a Record's Canonical Constructor Work?

Consider a simple record:

```java
public record Student(String name, int age) {
}
```

The declaration above defines components in the order `String name`, `int age`. When you do not declare a canonical constructor yourself, Java provides a constructor matching the component list:

```java
new Student("Lan", 18);
```

You can think of the compiler-generated constructor as taking the `name` and `age` parameters and initializing the two final fields of the record. The record itself also automatically gets accessors:

```java
Student s = new Student("Lan", 18);

System.out.println(s.name()); // Lan
System.out.println(s.age());  // 18
```

If you want to reject blank names or negative ages, you **declare the canonical constructor yourself** to put those conditions into the initialization process.

In Java 17 there are two main ways to write it:

| Form | Syntax | How components are assigned |
| --- | --- | --- |
| **Compact canonical constructor** | `public Student { ... }` | The compiler automatically assigns component parameters to their corresponding fields **after the constructor body completes normally**. |
| **Explicit canonical constructor** | `public Student(String name, int age) { ... }` | The developer must manually assign all component fields, e.g., `this.name = ...`. |

For validating and normalizing values, the compact constructor is usually shorter and easier to read.

## 2. Validating Parameters with a Compact Constructor

A compact constructor has the same name as the record, **omits the parameter list**, and **has no parentheses `()`** after the name:

```java
public record Student(String name, int age) {

    public Student {
        if (name == null) {
            throw new IllegalArgumentException("name must not be null");
        }

        if (name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("age must be between 0 and 150");
        }
    }
}
```

Inside the compact constructor body, the variables `name` and `age` are parameters derived from the component list. Java automatically assigns them to the record's fields when the constructor body exits without throwing an exception.

Call example:

```java
Student valid = new Student("Mai", 21);
System.out.println(valid); // Student[name=Mai, age=21]

Student invalid = new Student("  ", 21);
// Throws IllegalArgumentException during name validation.
```

**Note:** The maximum age condition of `150` is merely an illustrative constraint. Real applications should define rules based on their own data domain.

### Using `Objects.requireNonNull` for Required Parameters

Instead of writing `if (value == null)` manually for each component, you can use `Objects.requireNonNull`:

```java
import java.util.Objects;

public record Student(String name, int age) {

    public Student {
        Objects.requireNonNull(name, "name must not be null");

        if (name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

`Objects.requireNonNull(name, "...")` throws `NullPointerException` with the specific message if `name == null`. If not `null`, the method returns the `name` reference itself. Both styles of null handling are valid; keep exception conventions consistent across your project.

## 3. Normalizing Parameters Before Java Assigns Fields

Validation aims to **reject** invalid values. Normalization aims to **transform** a valid input value into a consistent form.

For example, a user enters a course code with extra spaces and lowercase letters:

```text
"  java-017  "
```

The application wants to store that code as:

```text
"JAVA-017"
```

A compact constructor lets you **reassign component parameters** before the automatic field assignment occurs:

```java
import java.util.Locale;
import java.util.Objects;

public record Course(String code, String title, int durationMinutes) {

    public Course {
        code = Objects.requireNonNull(code, "code must not be null")
                      .strip()
                      .toUpperCase(Locale.ROOT);

        title = Objects.requireNonNull(title, "title must not be null")
                       .strip();

        if (!code.matches("[A-Z]{2,8}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "code must match JAVA-017 or AB-123"
            );
        }

        if (title.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }

        if (durationMinutes <= 0) {
            throw new IllegalArgumentException(
                    "durationMinutes must be greater than 0"
            );
        }
    }
}
```

Usage:

```java
Course course = new Course("  java-017  ", "  Learning Java 17  ", 90);

System.out.println(course.code());            // JAVA-017
System.out.println(course.title());           // Learning Java 17
System.out.println(course.durationMinutes()); // 90
```

Steps executed when calling `new Course(...)`:

```text
Input parameters
       |
       v
Null check
       |
       v
Normalize code/title
       |
       v
Validate format, values, business rules
       |
       +--- Error ---> Throw exception, do not create record
       |
       v
End of compact constructor body
       |
       v
Java assigns normalized parameters to component fields
       |
       v
Valid record created
```

### Why Use `Locale.ROOT` in Identifier Examples?

When the goal is a technical code whose uppercase rules are independent of the user's language, `toUpperCase(Locale.ROOT)` produces more consistent results than case conversion based on the environment's default locale.

However, **not every string should be uppercased or lowercased**. Display names, case-sensitive strings, secret tokens, and values with specific semantics must be handled according to exact business requirements. `strip()` should also only be used when leading/trailing whitespace carries no meaning.

### Correct Order: Check Null Before Processing Strings

**Wrong:**

```java
record Product(String name) {
    public Product {
        name = name.strip(); // May throw NullPointerException without a clear message.
    }
}
```

**Right:**

```java
import java.util.Objects;

record Product(String name) {
    public Product {
        name = Objects.requireNonNull(name, "name is required").strip();

        if (name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }
}
```

Here `Objects.requireNonNull(...)` both verifies the parameter and returns the string on which `strip()` is called.

## 4. Distinguishing `strip()`, `trim()`, and `isBlank()`

In Java 17 examples, three methods frequently appear:

| Method | Purpose | Key Point |
| --- | --- | --- |
| `strip()` | Removes leading and trailing whitespace according to Java's Unicode whitespace rules. | Generally better suited for modern text data than `trim()`. |
| `trim()` | Removes characters at both ends with code point `<= U+0020`. | Still works, but uses different removal criteria than `strip()`. |
| `isBlank()` | Checks whether a string is empty or contains only Java whitespace characters. | Distinguishes blank strings from strings with content. |

Example:

```java
String raw = "   Java 17   ";

System.out.println(raw.strip());          // Java 17
System.out.println("   ".isBlank());      // true
System.out.println("Java 17".isBlank());  // false
```

Two main choices when designing a constructor:

- **Normalize then validate:** `name = name.strip(); if (name.isBlank()) ...`. Suitable when the application is allowed to discard extra whitespace.
- **Validate while keeping the original value:** `if (name.isBlank()) ...`, without reassigning `name`. Suitable when whitespace in the string may be significant.

## 5. Validating Relationships Across Multiple Components

Not every validity condition applies to a single parameter in isolation. A record representing a date range must check the **relationship** between the start date and end date.

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        Objects.requireNonNull(start, "start must not be null");
        Objects.requireNonNull(end, "end must not be null");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end must not be before start"
            );
        }
    }

    public long inclusiveDays() {
        return java.time.temporal.ChronoUnit.DAYS.between(start, end) + 1;
    }
}
```

Calling the constructor:

```java
DateRange valid = new DateRange(
        LocalDate.of(2026, 1, 10),
        LocalDate.of(2026, 1, 12)
);
System.out.println(valid.inclusiveDays()); // 3

DateRange invalid = new DateRange(
        LocalDate.of(2026, 1, 12),
        LocalDate.of(2026, 1, 10)
);
// Throws IllegalArgumentException.
```

In this example, the date range **allows `start` to equal `end`**. If business rules require `end` to be strictly **after** `start`, change the condition to:

```java
if (!end.isAfter(start)) {
    throw new IllegalArgumentException("end must be after start");
}
```

Key point: cross-field checks in the constructor prevent the record from ever entering states like "end date before start date".

## 6. Do Not Directly Assign Component Fields in a Compact Constructor

A common mistake is declaring a compact constructor while also trying to assign to the record's final fields.

**Wrong:**

```java
record Tag(String value) {
    public Tag {
        value = value.strip();
        this.value = value; // Compile ERROR
    }
}
```

In a compact constructor, the compiler is responsible for field assignment. Manually assigning `this.value` here is invalid.

**Right:**

```java
import java.util.Objects;

record Tag(String value) {
    public Tag {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

The developer only modifies the **parameter** `value`; at the end of the constructor, Java automatically stores the final value into the corresponding field.

Additionally, you cannot declare both a **compact canonical constructor** and an **explicit canonical constructor** in the same record, because both represent the same canonical constructor.

## 7. When to Use an Explicit Canonical Constructor?

You can write out the full parameters and assign each field yourself:

```java
import java.util.Locale;
import java.util.Objects;

public record CourseCode(String value) {

    public CourseCode(String value) {
        String normalized = Objects.requireNonNull(value, "value")
                                   .strip()
                                   .toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{2,8}-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid course code");
        }

        this.value = normalized;
    }
}
```

This is an **explicit canonical constructor**: the parameter list must match the record's components. Every component field must be properly assigned inside this constructor.

An equivalent, more concise version can be written with a compact constructor:

```java
import java.util.Locale;
import java.util.Objects;

public record CourseCode(String value) {

    public CourseCode {
        value = Objects.requireNonNull(value, "value")
                       .strip()
                       .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2,8}-[0-9]{3}")) {
            throw new IllegalArgumentException("Invalid course code");
        }
    }
}
```

The two versions above should be placed in **two separate files or two separate trials**, as they declare the same `CourseCode` record.

A compact constructor is ideal for validation/normalization. An explicit canonical constructor is useful if you need direct control over field assignments, even though the code is longer.

### Note on Visibility

An explicitly declared canonical constructor must have visibility at least as broad as the record. For example, for `public record CourseCode(...)`, write `public CourseCode { ... }` or `public CourseCode(...) { ... }`. Writing a non-`public` constructor for a `public record` will cause a compilation access error.

## 8. Additional Constructors Must Also Go Through the Canonical Constructor

A record can declare constructors other than the canonical constructor for convenience. However, an additional constructor must **delegate to another constructor of the same record via a `this(...)` call at the start of its body**; the delegation chain must eventually reach the canonical constructor.

```java
import java.util.Objects;

public record Product(String code, int quantity) {

    public Product {
        code = Objects.requireNonNull(code, "code").strip();

        if (code.isBlank()) {
            throw new IllegalArgumentException("code must not be blank");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }

    public Product(String code) {
        this(code, 1); // Delegates to the canonical constructor.
    }
}
```

Both creation forms are validated:

```java
Product p1 = new Product("  A-01  ", 2);
Product p2 = new Product("  B-02  ");

System.out.println(p1); // Product[code=A-01, quantity=2]
System.out.println(p2); // Product[code=B-02, quantity=1]
```

**Wrong — additional constructor tries to assign component fields directly:**

```java
record Product(String code, int quantity) {

    public Product(String code) {
        this.code = code; // ERROR: this constructor must delegate via this(...)
        this.quantity = 1;
    }
}
```

A static factory method should also call the canonical constructor (directly or through an additional constructor), rather than trying to create a record and then mutate components:

```java
record Point(int x, int y) {
    public static Point origin() {
        return new Point(0, 0);
    }
}
```

## 9. For Collections, Make Defensive Copies

A record's component fields are `final`, meaning field references cannot be reassigned after initialization. However, if a component points to a **mutable object**, the object's contents can still be modified from outside.

### Example with Risk of Data Mutation

```java
import java.util.List;

record Playlist(String name, List<String> songs) {
}

var songs = new java.util.ArrayList<String>();
songs.add("A");
Playlist playlist = new Playlist("Favorites", songs);

songs.add("B");
System.out.println(playlist.songs()); // [A, B]
```

Even though `Playlist` is a record, the internal list changes along with the caller's `songs` variable.

### Normalizing Collections with `List.copyOf`

```java
import java.util.List;
import java.util.Objects;

public record Playlist(String name, List<String> songs) {

    public Playlist {
        name = Objects.requireNonNull(name, "name").strip();

        if (name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        songs = List.copyOf(Objects.requireNonNull(songs, "songs"));

        if (songs.isEmpty()) {
            throw new IllegalArgumentException("Playlist needs at least one song");
        }
    }
}
```

Usage:

```java
import java.util.ArrayList;
import java.util.List;

var original = new ArrayList<String>(List.of("A"));
Playlist playlist = new Playlist("  Favorites  ", original);

original.add("B");

System.out.println(playlist.name());  // Favorites
System.out.println(playlist.songs()); // [A]
```

`List.copyOf(...)` creates (or reuses) an unmodifiable list, preserves element order, and **does not allow `null` elements**. By reassigning the `songs` parameter in the compact constructor, the record field receives the proper list.

**Limitation to know:** `List.copyOf` only copies at the collection level; it **does not deep-copy** elements that are mutable objects. For data requiring deep immutability, use immutable elements or copy each object according to its own rules.

### When a Component Is an Array

Java arrays are mutable even when the reference is stored in a `final` field. If a record must have an array component, you typically have to copy on **input** and on **output**:

```java
import java.util.Objects;

public record Bytes(byte[] data) {

    public Bytes {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

This protects the internally stored array from direct mutation. However, a record with an array component has another consideration: auto-generated `equals()`/`hashCode()` for arrays use reference comparison semantics, **not element-by-element content comparison**. If content comparison is needed, design a dedicated wrapper type with appropriate `equals()`/`hashCode()` or choose another immutable data structure instead of expecting the record to handle it automatically.

## 10. Choosing Exception Types and Normalization Policies

Constructors establish a record's **invariants**. Validation choices should be consistent with business rules and clear to callers.

| Situation | Common Approach | Reason |
| --- | --- | --- |
| Required reference parameter is `null` | `Objects.requireNonNull(value, "value")` | Throws `NullPointerException` with a message identifying the exact component. |
| Negative number, empty string, invalid range | `throw new IllegalArgumentException("...")` | Indicates the supplied argument violates constructor preconditions. |
| Meaningless outer whitespace on name/code | `strip()` then check `isBlank()` | Stores a consistent representation rather than redundant variants. |
| Locale-independent technical identifier | `toUpperCase(Locale.ROOT)` or `toLowerCase(Locale.ROOT)` | Avoids dependence on default locale when normalizing technical codes. |
| Collection needing protection from modification | `List.copyOf`/`Set.copyOf`/`Map.copyOf` where appropriate | Creates an unmodifiable collection; still consider element mutability. |
| Missing input with a business default | Additional constructor calling `this(...)` or factory method | Every initialization path goes through the canonical constructor. |

Do not "normalize" by silently turning every invalid input into a default value. For example, silently converting `quantity = -10` to `0` can hide input bugs. Unless business requirements explicitly specify that transformation, throw an exception.

### Money Example: Avoiding Arbitrary Rounding

`BigDecimal` is commonly used for decimal values requiring precision. Only round or change scale if the data contract allows it. The example below requires a non-negative value representable exactly with two decimal places, so it uses `RoundingMode.UNNECESSARY` to reject values needing rounding:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record Money(BigDecimal amount) {

    public Money {
        amount = Objects.requireNonNull(amount, "amount");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }

        try {
            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "amount can have at most 2 decimal places",
                    ex
            );
        }
    }
}
```

`new Money(new BigDecimal("12.5"))` is stored with `amount()` as `12.50`; `new Money(new BigDecimal("12.345"))` is rejected. The two-decimal-place rule is just a **domain example**, not a universal default for every metric, exchange rate, or currency.

## 11. Complete Example: Record with Normalized Data and Clear Invariants

Suppose a system receives orders with an ID, quantity, and tag list. Requirements:

- `orderId` is required, trimmed of leading/trailing whitespace, and uppercased using a neutral locale.
- `quantity` is greater than 0.
- `tags` is non-`null`, contains no `null` elements, and cannot be mutated by the caller after record creation.
- Every constructor must enforce these conditions.

File `Order.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public record Order(String orderId, int quantity, List<String> tags) {

    public Order {
        orderId = Objects.requireNonNull(orderId, "orderId")
                         .strip()
                         .toUpperCase(Locale.ROOT);

        if (orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be greater than 0");
        }

        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }

    public Order(String orderId, int quantity) {
        this(orderId, quantity, List.of());
    }
}
```

File `Main.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        var editableTags = new ArrayList<>(List.of("priority"));

        Order order = new Order("  ab-123  ", 2, editableTags);
        editableTags.add("changed-after-create");

        System.out.println(order.orderId());
        System.out.println(order.quantity());
        System.out.println(order.tags());

        Order simple = new Order("  cd-456  ", 1);
        System.out.println(simple);
    }
}
```

Compile for Java 17:

```bash
mkdir out
javac --release 17 -encoding UTF-8 -d out Order.java Main.java
java -cp out Main
```

Expected output:

```text
AB-123
2
[priority]
Order[orderId=CD-456, quantity=1, tags=[]]
```

In this example, `editableTags` is mutated after `Order` is created, yet the copy inside the record remains unchanged. The additional constructor `Order(String orderId, int quantity)` also uses the canonical constructor, so no initialization path bypasses validation.

## 12. Common Mistakes When Writing Record Constructors

### Mistake A: Normalizing a Temporary Variable but Forgetting to Reassign the Parameter

**Behaviorally wrong, even though it compiles:**

```java
record Username(String value) {
    public Username {
        String normalized = value.strip();
        // value still holds the original value.
    }
}
```

**Right:**

```java
import java.util.Objects;

record Username(String value) {
    public Username {
        value = Objects.requireNonNull(value, "value").strip();
    }
}
```

In a compact constructor, the implicit assignment at the end of the body uses the **final value of the `value` parameter**. If you only normalize into a local variable `normalized` without reassigning the parameter, the record stores the original input.

### Mistake B: Calling an Accessor to Check Values Before the Compact Constructor Finishes

Do not treat the `name()` accessor as the way to read the normalized value inside a compact constructor body. **Check the `name` parameter directly**:

```java
record User(String name) {
    public User {
        name = name.strip();

        if (name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }
}
```

In a compact constructor, record fields are only implicitly assigned **after** the constructor body, so normalization and validation logic must operate on the parameters.

### Mistake C: Believing Records Are Deeply Immutable Automatically

```java
import java.util.List;

record Notes(List<StringBuilder> entries) {
    public Notes {
        entries = List.copyOf(entries);
    }
}
```

`List.copyOf` prevents adding/removing elements through the accessor, but each `StringBuilder` inside the list can still be mutated. If fixed contents are desired, convert to a list of immutable values such as `List<String>` after copying the data, or define an appropriate immutable type.

### Mistake D: Using Default Values to Mask Invalid Input

```java
record Quantity(int value) {
    public Quantity {
        if (value < 0) {
            value = 0; // May hide bugs if business rules forbid negatives.
        }
    }
}
```

If negative quantities are invalid input, report an error:

```java
record Quantity(int value) {
    public Quantity {
        if (value < 0) {
            throw new IllegalArgumentException("value must not be negative");
        }
    }
}
```

Only use a default value when input requirements explicitly specify its meaning.

### Mistake E: Expecting an Accessor to Normalize Data at Record Creation

**Do not** merely modify the accessor and assume data was normalized at initialization:

```java
record Username(String value) {
    @Override
    public String value() {
        return value.strip();
    }
}
```

In this example, the internal field can still hold whitespace, while the auto-generated `equals()`, `hashCode()`, and `toString()` operate on **the internally stored state**. This easily causes discrepancies between what the accessor returns and the record's internal representation.

**Right:** normalize in the canonical constructor:

```java
import java.util.Objects;

record Username(String value) {
    public Username {
        value = Objects.requireNonNull(value, "value").strip();
    }
}
```

Now the accessor, `equals()`, `hashCode()`, and `toString()` all rely on the normalized value stored in the record.

## 13. Practice Exercises

### Exercise 1: Normalizing Display Names

Define:

```java
record DisplayName(String value) {
}
```

Requirement: `value` must not be `null`; after stripping leading and trailing whitespace, the string must not be blank. Do not force uppercase or lowercase. Write a compact constructor and test:

```java
new DisplayName("  Minh  "); // expected value(): "Minh"
new DisplayName("   ");      // Throws exception
new DisplayName(null);       // Throws exception
```

### Exercise 2: Validating Numeric Ranges

Create `record IntRange(int min, int max)`. Require `min <= max`. Test:

```java
new IntRange(3, 8); // Valid
new IntRange(5, 5); // Valid
new IntRange(9, 2); // Throws IllegalArgumentException
```

Then add constructor `IntRange(int max)` calling `this(0, max)`, ensuring the rule still applies.

### Exercise 3: Copying Collections

Create `record Tags(List<String> values)`. Use `List.copyOf` in the compact constructor, then:

1. Create an `ArrayList<String>` and pass it to `Tags`.
2. Add an element to the original `ArrayList` after creating the record.
3. Observe that `tags.values()` still retains the original list.
4. Try mutating directly via `tags.values().add(...)`; the list is protected against mutation.

### Exercise 4: Comparing Both Canonical Constructor Forms

Write the same normalization problem `record Code(String value)` in two ways **in two separate code versions**:

- Compact constructor: reassign the `value` parameter.
- Explicit canonical constructor: manually assign the `this.value` field.

Observe how the differences in syntax and field-assignment responsibility affect the conciseness of each approach.

## 14. Takeaways When Designing Record Constructors

| What to Do | How to Do It in Java 17 |
| --- | --- |
| Check for null | `Objects.requireNonNull(...)` or explicit condition. |
| Validate numeric bounds, length, format | `if (...) throw new IllegalArgumentException(...)`. |
| Normalize a component | In a compact constructor, **reassign the component parameter** before the constructor body ends. |
| Assign component fields manually | Only in an **explicit canonical constructor**, ensuring all fields are initialized. |
| Protect collections | Defensively copy using `List.copyOf`/`Set.copyOf`/`Map.copyOf` when appropriate; consider element immutability. |
| Add convenience constructors | Call `this(...)` to pass through the canonical constructor. |
| Avoid divergence between state and accessor | Put validation and normalization in the canonical constructor rather than transforming only on access. |
| Verify correctness | Instantiate records with both valid and invalid data; observe stored values and exceptions. |

**Core principle:** a record should be created in a **valid state normalized according to business rules**. In Java 17, compact canonical constructors make this clear: validate inputs, reassign any parameters requiring normalization, and let the compiler finish storing them into the component fields.
