# Canonical Constructors and Compact Constructors in Java 17

In Java 17, a **record** is a way to declare a data type primarily used to represent a fixed group of values. When creating a record instance, Java needs to receive values for the **record components** declared in the header. The constructor accepting that exact set of components is called the **canonical constructor**.

Java supports two ways to write a canonical constructor: the **full form (normal/explicit canonical constructor)** and the **short form (compact constructor)**. Additionally, if you do not write a canonical constructor yourself, the compiler **automatically generates** one.

Understanding these three cases helps you validate data, normalize inputs, and keep a record in a valid state without writing repetitive assignments.

> **Version:** Records have been an official feature since Java 16 (JEP 395), so all syntax in this lesson works on **Java 17** without `--enable-preview`. This lesson focuses on rules that remain applicable in modern Java, without legacy preview syntax.

## 1. How Do Record Components Define the Initialization Contract?

Consider the declaration:

~~~java
record Point(int x, int y) {
}
~~~

The elements `int x` and `int y` in the header are called **record components**. For the declaration above, Java generates the corresponding core members:

- Two state-holding fields: `private final int x` and `private final int y`.
- Two accessors: `x()` and `y()`.
- Appropriate `equals(Object)`, `hashCode()`, and `toString()` methods.
- A canonical constructor with parameters `(int x, int y)` to initialize both components.

You can write:

~~~java
Point p = new Point(3, 7);

System.out.println(p.x()); // 3
System.out.println(p.y()); // 7
System.out.println(p);     // Point[x=3, y=7]
~~~

A record **does not** automatically generate a no-arg constructor `Point()`, because both `x` and `y` must be initialized according to the header's contract.

From the outside, `new Point(3, 7)` looks like calling a traditional constructor. The difference is that **the record header predefines the shape of the canonical constructor**: the name, type, and order of each component.

### Three Common Cases

| Case | What do you write? | Who assigns values to the component fields? | When to use |
|---|---|---|---|
| **Implicit canonical constructor** | Only write the record header, do not declare a canonical constructor | Compiler generates the constructor and assignments | Data needs no extra validation or normalization |
| **Explicit canonical constructor, full form** | Write a constructor whose parameter list matches the header | **You manually assign** all component fields | Need direct control over initialization or assignment logic |
| **Compact constructor** | Write the record name and constructor body, **with no parameter list** | Compiler assigns fields after the constructor body succeeds | Need to validate/normalize parameters while keeping code concise and less error-prone |

**Very common pitfall:** *A compact constructor is also a way of declaring the canonical constructor.* It is not a constructor with a different parameter set.

## 2. Implicit Canonical Constructor: No Need to Write Manually

The simplest example:

~~~java
record Size(int width, int height) {
}
~~~

If no explicit canonical constructor is present, the compiler generates a constructor with an equivalent job:

~~~java
// Illustrating the meaning of the compiler-generated constructor:
Size(int width, int height) {
    this.width = width;
    this.height = height;
}
~~~

In this example, `Size` has package-private access, so the generated constructor has the same access level. If the record is `public`, the implicit constructor is also `public`.

When no data validation is needed, this is the most concise option:

~~~java
Size size = new Size(1920, 1080);
System.out.println(size.width());  // 1920
System.out.println(size.height()); // 1080
~~~

Note: the compiler does not infer that dimensions must be positive. `new Size(-1, 0)` is still valid under the declaration above. To enforce business invariants, you need to write a canonical constructor to check them.

## 3. Explicit Canonical Constructor, Full Form

This is a constructor that explicitly states a **parameter list** matching the record header in **count, names, types, and order** of components.

~~~java
record Rectangle(int width, int height) {

    public Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException(
                    "Width and height must be greater than 0");
        }

        this.width = width;
        this.height = height;
    }
}
~~~

Here, the constructor accepts the exact `int width, int height` as in the header and does two things:

1. Validates the data before initialization.
2. **Manually assigns** the fields `this.width` and `this.height`.

Once you declare the full explicit canonical constructor, the compiler **does not** add another implicit canonical constructor to assign fields for you. Because component fields are `final`, every normal execution path of the constructor must fully initialize them.

Call example:

~~~java
Rectangle ok = new Rectangle(8, 5);
System.out.println(ok); // Rectangle[width=8, height=5]

// Throws IllegalArgumentException per the rule we defined:
new Rectangle(-2, 5);
~~~

### 3.1. Cannot Change Parameter Names, Order, or Types of the Canonical Constructor

For `record Rectangle(int width, int height)`, the following constructor **is not** the corresponding canonical constructor:

~~~java
record Rectangle(int width, int height) {
    // This is a constructor with different parameters; it does not replace the canonical constructor.
    // If declared as an overload, this constructor must delegate via this(...).
    public Rectangle(int width) {
        this(width, width);
    }
}
~~~

`Rectangle(int width)` is an **overloaded constructor**: it takes only one parameter and delegates to the two-parameter canonical constructor. Because the canonical constructor is not explicitly declared in this example, Java still auto-generates `Rectangle(int width, int height)`.

You cannot "rename" the canonical parameters to `(int w, int h)` and expect the compiler to treat it as the same record signature. Canonical constructor rules are stricter than ordinary constructors: parameter names must match the record components.

### 3.2. Manually Assign All Components

Error example:

~~~java
// INVALID EXAMPLE: missing initialization of field y.
record Position(int x, int y) {
    public Position(int x, int y) {
        this.x = x;
        // this.y has not been assigned.
    }
}
~~~

The compiler reports an error because `y` is uninitialized. There is no automatic assignment at the end of a **full canonical constructor**.

When processing multiple components with longer logic, you can compute and validate first before assigning:

~~~java
import java.util.Objects;

record PersonName(String givenName, String familyName) {
    public PersonName(String givenName, String familyName) {
        Objects.requireNonNull(givenName, "givenName");
        Objects.requireNonNull(familyName, "familyName");

        String normalizedGiven = givenName.strip();
        String normalizedFamily = familyName.strip();

        if (normalizedGiven.isEmpty() || normalizedFamily.isEmpty()) {
            throw new IllegalArgumentException("Given name and family name must not be empty");
        }

        this.givenName = normalizedGiven;
        this.familyName = normalizedFamily;
    }
}
~~~

After successful initialization, the `givenName()` and `familyName()` accessors return the normalized values. Normalization is part of the **object creation contract**, without requiring callers to remember to preprocess inputs themselves.

## 4. Compact Constructor: Validate and Normalize, Java Assigns Fields

A compact constructor has a distinct syntax:

~~~java
record Percentage(int value) {

    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Percentage must be in the range 0..100");
        }
    }
}
~~~

Pay attention:

- Write `public Percentage { ... }`, **do not write** `Percentage(int value)`.
- The `value` parameter still **exists implicitly**, taken from the record header.
- You can read, validate, and **reassign the parameter variable** `value` inside the constructor body.
- If the constructor body finishes normally, the compiler automatically assigns the final value of `value` to the field `this.value`.

Semantically, the case above is equivalent to a full canonical constructor like:

~~~java
record Percentage(int value) {
    public Percentage(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Percentage must be in the range 0..100");
        }
        this.value = value;
    }
}
~~~

You use only **one of these two forms** for a single record; you cannot declare both canonical constructors at the same time.

### 4.1. Normalizing Parameters Right Inside a Compact Constructor

A very common use case is trimming whitespace and normalizing letter casing:

~~~java
import java.util.Locale;
import java.util.Objects;

record CourseCode(String value) {

    public CourseCode {
        Objects.requireNonNull(value, "value");

        value = value.strip().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2,5}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Course code must match format JAVA-017");
        }
    }
}
~~~

Calling it:

~~~java
CourseCode code = new CourseCode("  java-017  ");

System.out.println(code.value()); // JAVA-017
System.out.println(code);         // CourseCode[value=JAVA-017]
~~~

Initialization flow:

~~~text
new CourseCode("  java-017  ")
             |
             v
Parameter value = "  java-017  "
             |
             v
Execute compact constructor body:
  - null check
  - value = "JAVA-017"
  - format check
             |
             v
Constructor body finishes normally
             |
             v
Compiler assigns this.value = value
             |
             v
Completed record: CourseCode[value=JAVA-017]
~~~

The final assignment is the compiler's responsibility, keeping the code concise and preventing a forgotten field assignment when a record has many components.

### 4.2. Do Not Manually Assign Component Fields in a Compact Constructor

The following snippet is **invalid**:

~~~java
record Score(int value) {

    public Score {
        if (value < 0) {
            throw new IllegalArgumentException();
        }

        // ERROR: cannot assign directly to a component field
        // inside a compact constructor body.
        this.value = value;
    }
}
~~~

Correct way:

~~~java
record Score(int value) {

    public Score {
        if (value < 0) {
            throw new IllegalArgumentException("Score must not be negative");
        }
        // No need to assign this.value.
    }
}
~~~

When normalizing, **reassign the parameter**, such as `value = Math.max(0, value)` if automatically clamping negative scores truly matches business requirements. If negative input is an error, throwing an exception is usually clearer.

### 4.3. Compact Constructors Can Use Multiple Components

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "End date must not be before start date");
        }
    }
}
~~~

Java automatically assigns **both** `start` and `end` fields after the constructor body completes successfully. If validation throws an exception, no object is returned to the caller.

## 5. Comparing All Three Initialization Forms in One Program

Create the file **`RecordConstructorDemo.java`**:

~~~java
import java.util.Objects;

// 1. No constructor written: compiler generates canonical constructor.
record Point(int x, int y) {
}

// 2. Full canonical constructor: assign fields manually.
record FullName(String first, String last) {

    public FullName(String first, String last) {
        this.first = requireNonBlank(first, "first");
        this.last = requireNonBlank(last, "last");
    }

    private static String requireNonBlank(String value, String label) {
        Objects.requireNonNull(value, label);

        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }

        return normalized;
    }
}

// 3. Compact constructor: compiler assigns field after validation.
record Percentage(int value) {

    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Value must be within 0..100");
        }
    }
}

public class RecordConstructorDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 5);
        FullName name = new FullName("  An  ", "  Nguyen ");
        Percentage percentage = new Percentage(75);

        System.out.println(point);
        System.out.println(name);
        System.out.println(percentage);
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 RecordConstructorDemo.java
java RecordConstructorDemo
~~~

Output:

~~~text
Point[x=2, y=5]
FullName[first=An, last=Nguyen]
Percentage[value=75]
~~~

Lesson from the example: **all three records have a canonical constructor**, though only the last two declare an explicit constructor. The main difference lies in **where field assignment happens**.

## 6. Syntax and Accessibility Rules

### 6.1. Names and Components of the Canonical Constructor Must Match the Record Header

Given the declaration:

~~~java
record Coordinate(double latitude, double longitude) {
}
~~~

The full canonical constructor must accept exactly `double latitude, double longitude` in that order. A compact constructor omits the parameter list but still has the two corresponding implicit parameters.

A constructor accepting a different parameter set is an *overloaded* constructor and must obey the rule of delegating to the canonical constructor.

### 6.2. Access Modifier Must Match or Exceed the Record's Visibility

An explicit canonical constructor cannot have **narrower** access than its enclosing record.

For example, a `public` record must have a `public` explicit canonical constructor:

~~~java
// File CustomerId.java
public record CustomerId(long value) {

    public CustomerId {
        if (value <= 0) {
            throw new IllegalArgumentException("ID must be positive");
        }
    }
}
~~~

If you declare a package-private or `private` explicit canonical constructor for a `public record`, the compiler will reject it.

For a package-private record, the canonical constructor does not have to be `public`; however, examples in this lesson often write `public` to make accessibility intent clear. When no explicit canonical constructor is present, the compiler generates a constructor with the same accessibility as the record.

### 6.3. Restrictions on Canonical Constructors

Whether written in full or compact form, a canonical constructor:

- Cannot declare its own type parameters (cannot be a generic constructor).
- Cannot declare a `throws` clause.
- Cannot call another constructor via an explicit `this(...)` or `super(...)` invocation in its body.
- Must maintain proper initialization of all record components.

Specifically, a **compact constructor** also has these rules:

- Has no parameter list in its declaration.
- Does not allow direct assignment to fields corresponding to record components.
- Cannot use a `return` statement to exit the constructor body.

If validation needs to report a checked exception, design a different error representation suited to your API, such as converting to a meaningful unchecked exception when data is invalid. Do not write `throws IOException` on a canonical constructor.

### 6.4. Cannot Add Instance Fields Manually to a Record

A record ties its official state to the component list in the header. Therefore, declaring extra instance fields like the following is invalid:

~~~java
record Rectangle(int width, int height) {
    // Invalid: records do not allow declaring extra instance fields.
    // private final int area;
}
~~~

If you want to compute the area, use a method:

~~~java
record Rectangle(int width, int height) {

    public Rectangle {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException();
        }
    }

    public long area() {
        return (long) width * height;
    }
}
~~~

A record can still declare **static fields**, static methods, and instance methods, provided they follow language rules.

## 7. Overloaded Constructors Must Delegate to the Canonical Constructor

Records still support overloaded constructors to offer convenient ways of creating objects. However, **every non-canonical constructor must begin with a `this(...)` call** forwarding to another constructor of the same record, eventually reaching the canonical constructor.

For example, a date range can be created from two dates or from a single day.

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {

    // Compact canonical constructor:
    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException("Invalid date range");
        }
    }

    // Overloaded constructor: delegates to the canonical constructor.
    public DateRange(LocalDate singleDay) {
        this(singleDay, singleDay);
    }
}
~~~

Call example:

~~~java
LocalDate today = LocalDate.of(2026, 11, 15);

DateRange oneDay = new DateRange(today);
DateRange severalDays = new DateRange(today, today.plusDays(7));

System.out.println(oneDay.start());      // 2026-11-15
System.out.println(severalDays.end());   // 2026-11-22
~~~

Both creation paths go through the compact canonical constructor, so both get null and date-order validation.

The following snippet is invalid:

~~~java
record NumberBox(int value) {
    // Invalid overloaded constructor: does not call this(...) first.
    public NumberBox(String text) {
        // int parsed = Integer.parseInt(text);
        // this(parsed);
    }
}
~~~

How to fix it:

~~~java
record NumberBox(int value) {
    public NumberBox(String text) {
        this(Integer.parseInt(text));
    }
}
~~~

If you need to transform data before invoking the constructor, you can call a static helper method inside the argument expression of `this(...)`.

In many cases, a **static factory method** with a descriptive name like `of(...)`, `fromText(...)`, or `fromCelsius(...)` makes the API easier to read than creating too many overloaded constructors.

## 8. Choosing Full Canonical vs. Compact in Real Projects

Both forms can validate and normalize. Which one to choose depends on how much detailed control you need over the initialization process.

| Need | Recommended Choice | Example |
|---|---|---|
| No validation needed, data is just a group of values | Implicit constructor | `record Point(int x, int y) {}` |
| Range, null, or cross-component checks | Compact constructor | `start` must not be after `end` |
| Trimming whitespace or normalizing input representation while keeping components | Compact constructor | `code = code.strip().toUpperCase(Locale.ROOT)` |
| Wanting explicit component assignments after computation or individual initialization steps | Full canonical | `this.first = normalize(first)` |
| Supporting additional creation signatures | Overloaded constructor delegating to canonical | `new DateRange(singleDay)` |
| Expressing semantics of multiple creation methods | Static factory method | `DateRange.oneDay(date)` |

**Practical recommendation:** When you only need to validate or normalize parameters, a compact constructor is usually easier to maintain because you do not repeat field assignments. Use the full canonical form when the component assignments themselves need to be shown and controlled explicitly.

### 8.1. Compact Constructors Are Well-Suited for Defensive Copies

Record components are `private final`, but **`final` only prevents reassigning the field reference**, not mutating the referenced object. If a component is a mutable collection, keeping the raw input reference can allow the record's observable state to change externally.

Example to avoid:

~~~java
import java.util.List;

record Team(List<String> members) {
    // Implicit constructor keeps the exact input List reference.
}
~~~

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(List.of("An", "Binh"));
Team team = new Team(names);

names.add("Chi");
System.out.println(team.members()); // [An, Binh, Chi]
~~~

If you want to store a list that cannot be modified through the `List` API, copy it in the constructor:

~~~java
import java.util.List;
import java.util.Objects;

record Team(List<String> members) {

    public Team {
        Objects.requireNonNull(members, "members");
        members = List.copyOf(members);
    }
}
~~~

Afterward, mutating the original list does not affect the list stored in the record; `team.members().add("Chi")` will throw `UnsupportedOperationException`.

**Limitation to remember:** `List.copyOf` creates an unmodifiable copy of the list structure, but **does not deep-copy element objects**. If elements are objects with mutable state, state observed through the collection can still change. With arrays, `final` fields are even less sufficient: consider copying arrays on input and when returning from accessors. Furthermore, generated `equals`/`hashCode` for records containing arrays apply array reference semantics, so collections are usually better suited when content-based equality is desired.

### 8.2. Canonical Constructors Centralize Invariants

An *invariant* is a condition that must hold true for every successfully created object. For example, `DateRange` requires `start <= end`. Placing checks in the canonical constructor provides two benefits:

1. Callers cannot bypass validation by picking another constructor, provided all overloaded constructors properly delegate to the canonical constructor.
2. Ordinary object creations using `new` enforce the same rules; calling code does not need to repeat validation at every call site.

This rule is especially valuable when a record represents a **value object** with clear validity constraints: currency codes, business IDs, date ranges, ratios, coordinates, etc.

## 9. Common Pitfalls

### 9.1. Confusing a Compact Constructor with a No-Arg Constructor

~~~java
record Price(int amount) {
    public Price {
        if (amount < 0) {
            throw new IllegalArgumentException();
        }
    }
}
~~~

`Price { ... }` **is not** a no-arg constructor. It still takes the `int amount` parameter from the record header:

~~~java
new Price(100); // Valid.
// new Price(); // Invalid unless a separate overload is declared.
~~~

### 9.2. Manually Assigning Fields in a Compact Constructor

~~~java
// Invalid in a compact constructor:
// this.amount = amount;
~~~

Validate or reassign the **parameter variable** `amount` instead. The compiler performs the field assignment after the compact body completes normally.

### 9.3. Forgetting to Assign a Component in the Full Canonical Form

~~~java
record Pair(int left, int right) {
    public Pair(int left, int right) {
        this.left = left;
        // Missing this.right = right;
    }
}
~~~

When using the full canonical form, you must assign all components. This is one reason compact constructors are helpful when the logic is purely validation.

### 9.4. Writing `throws` on a Canonical Constructor

~~~java
// Invalid example: canonical constructors cannot have a throws clause.
record Payload(String text) {
    // public Payload(String text) throws Exception {
    //     this.text = text;
    // }
}
~~~

If validation simply rejects invalid data, unchecked exceptions such as `IllegalArgumentException` or `NullPointerException` are usually appropriate. When an API needs recoverable error handling, consider a static factory method or a separate parsing method with an explicit error contract.

### 9.5. Expecting to Mutate Components with Setters After Creation

~~~java
record AccountId(long value) {
}
~~~

A record does not let you write a setter like `this.value = newValue` to change a component field after initialization. If a different value is needed, create a new record:

~~~java
AccountId first = new AccountId(10);
AccountId second = new AccountId(20);
~~~

If the problem requires objects with continuously changing state, a regular class may suit better than a record.

### 9.6. Forgetting That Post-Normalization Data Is What Gets Stored

Consider:

~~~java
record Label(String value) {
    public Label {
        value = value.strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("Label must not be empty");
        }
    }
}
~~~

If the input consists solely of whitespace, `strip()` produces an empty string and validation throws an error. If the input is `"  Java  "`, the stored value is `"Java"`. Validating on the normalized form usually makes more sense than checking only the raw input string.

Remember to check for null before calling `strip()` if the API can receive null.

## 10. Practice Exercises

### Exercise 1: Convert from Full Canonical to Compact

Given the code:

~~~java
record Age(int years) {

    public Age(int years) {
        if (years < 0 || years > 150) {
            throw new IllegalArgumentException("Invalid age");
        }
        this.years = years;
    }
}
~~~

Rewrite it using a compact constructor and explain why `this.years = years` can be removed.

**Suggested Answer:**

~~~java
record Age(int years) {

    public Age {
        if (years < 0 || years > 150) {
            throw new IllegalArgumentException("Invalid age");
        }
    }
}
~~~

The compiler automatically performs `this.years = years` after the compact constructor body finishes normally.

### Exercise 2: Normalize a Product Code

Create `record ProductCode(String value)` such that:

- Null is not accepted.
- Leading/trailing whitespace is removed.
- Letters are converted to uppercase using `Locale.ROOT`.
- The result must not be empty.

**Reference Solution:**

~~~java
import java.util.Locale;
import java.util.Objects;

record ProductCode(String value) {

    public ProductCode {
        Objects.requireNonNull(value, "value");
        value = value.strip().toUpperCase(Locale.ROOT);

        if (value.isEmpty()) {
            throw new IllegalArgumentException("Product code is empty");
        }
    }
}
~~~

### Exercise 3: Spot the Error in Constructor Declaration

Consider:

~~~java
record Interval(int start, int end) {

    public Interval {
        if (start > end) {
            throw new IllegalArgumentException("Invalid interval");
        }
        // this.start = start;
        // this.end = end;
    }
}
~~~

If you uncomment the two statements `this.start = start` and `this.end = end`, what happens?

**Answer:** The compiler reports an error because compact constructors do not allow direct assignment to record component fields. Keep them commented out or remove them completely.

### Exercise 4: Write a Valid Overloaded Constructor

Add constructor `Interval(int end)` to create an interval from `0` to `end` while sharing the same validation.

**Answer:**

~~~java
record Interval(int start, int end) {

    public Interval {
        if (start > end) {
            throw new IllegalArgumentException("Invalid interval");
        }
    }

    public Interval(int end) {
        this(0, end);
    }
}
~~~

`new Interval(5)` is valid, while `new Interval(-5)` will be rejected by the canonical constructor because `0 > -5`.

## 11. Concept Summary

Keep a simple mental model in mind:

~~~text
Record header defines components
          |
          v
  Canonical constructor
          |
          +-- Not declared    -> Compiler generates constructor and field assignments
          |
          +-- Full form       -> You declare parameters, validate, and assign fields manually
          |
          +-- Compact         -> You validate/normalize parameters,
                                 compiler assigns fields after body finishes

Overloaded constructors -> must delegate via this(...) to canonical constructor
~~~

When you see `public MyRecord { ... }`, recognize it as a **compact canonical constructor** receiving the components already listed in the header. When you see `public MyRecord(Type a, Type b) { ... }` matching the header, remember it is the **full canonical constructor**, where component fields must be assigned explicitly.

For **validating and normalizing data in Java 17**, the compact constructor is usually the shortest and easiest-to-maintain expression. The full canonical form remains useful when direct control over assignment details is needed.

## 12. References

- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): standard status of records and description of compact constructors.
- [Java Language Specification, Java SE 17 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): rules for records, components, members, and constructors.
- [Java Language Specification, Java SE 17 — `8.10.4 Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): specification of canonical, compact, and overloaded constructors.
- [Oracle Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): guide to records in Java 17.
