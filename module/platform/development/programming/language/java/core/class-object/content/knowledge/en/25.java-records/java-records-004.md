# Canonical Constructor and Compact Canonical Constructor in Java Records (Java 17+)

A `record` declares **a data type with fixed record components**. For example, `record Point(int x, int y) {}` declares two components `x` and `y`. Java provides the corresponding private final fields, accessors `x()` and `y()`, and generates the `equals`, `hashCode`, and `toString` behaviors based on the record components if you do not declare them yourself. The core focus of this lesson is **the constructor that initializes all component fields**.

A **canonical constructor** accepts the exact parameters corresponding to **all record components, in the exact order, with the exact names and types**. If not declared, the compiler provides a default canonical constructor. You can declare it explicitly with the full parameter list and assign the fields yourself.

A **compact canonical constructor** is a shorthand form: you only write the record name and a block `Point { ... }`, **without writing a parameter list**. You can still validate and normalize the parameters; after the block completes normally, the compiler **automatically assigns each component field from its corresponding parameter**. Therefore, in a compact constructor, you **must not manually assign** `this.x = ...`.

This lesson belongs to **Java core – class-object**, group **Record**, topic **Canonical Constructor and Compact Canonical Constructor**. The examples use Java **17 or higher** and do not require preview features. Each complete program includes a file name, run command, and reliable stdout; intentionally invalid lines are marked separately.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify the canonical constructor from the record header without confusing it with an overloaded constructor.
2. Recognize the implicitly generated canonical constructor when a record does not declare one explicitly.
3. Write an **explicit canonical constructor** with the exact parameter names/types/order and assign all fields.
4. Write a **compact constructor** for validation, data normalization, and preserving *invariants*.
5. Explain accurately **when the compiler assigns component fields** in a compact constructor.
6. Know why a compact constructor **must not directly assign** component fields.
7. Handle `null`, value ranges, trim/canonicalization, and exceptions when data is invalid.
8. Write non-canonical constructors by **delegating to another constructor of the same record via `this(...)`**.
9. Understand the access modifier appropriate for a record's accessibility.
10. Distinguish final component fields from **deep immutability** of the object to which a component reference points.
11. Test record accessors, equality, and the effects of normalization.
12. Choose a readable constructor form and avoid duplicate initialization logic.

## 2. The Record Header Determines the Component List

Consider the declaration:

~~~java
record Point(int x, int y) {
}
~~~

This is a complete **package-private top-level record**. The record header `(int x, int y)` declares two components in the exact order `x`, `y`. When no constructor is written by you, the compiler generates a canonical constructor equivalent in behavior to accepting `x` and `y` and assigning the two corresponding private final fields.

You can use:

~~~java
Point point = new Point(3, 4);
int first = point.x();
int second = point.y();
~~~

This is a valid snippet inside a method in the same package; the accessors are `x()` and `y()`, **not automatically** `getX()` or `getY()`. There are no default setters.

An important point: **a record is not just a shorthand for a hand-written class**. A record has a structural contract for its components, canonical constructor, and transparent data behavior. However, if a component is a reference to a mutable object, the record does not automatically make that object immutable.

## 3. Complete Program 1 — Implicit Canonical Constructor

Create the file **`ImplicitCanonicalDemo.java`**:

~~~java
record Point(int x, int y) {
}

public class ImplicitCanonicalDemo {
    public static void main(String[] args) {
        Point first = new Point(3, 4);
        Point second = new Point(3, 4);
        Point third = new Point(3, 5);

        System.out.println("x=" + first.x());
        System.out.println("y=" + first.y());
        System.out.println("point=" + first);
        System.out.println("equal=" + first.equals(second));
        System.out.println("different=" + first.equals(third));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ImplicitCanonicalDemo.java
java ImplicitCanonicalDemo
~~~

**Stdout:**

~~~text
x=3
y=4
point=Point[x=3, y=4]
equal=true
different=false
~~~

There is no need to write the `Point(int x, int y)` constructor yourself. With the declaration above, the canonical constructor provided by the compiler sets both fields. `equals` compares the values of the components according to record rules; two Points with the same x/y are considered equal.

The type name `Point` in the same file is package-private, while `ImplicitCanonicalDemo` is a public class matching the file name. Having two top-level declarations like this is completely valid.

## 4. What Exactly Is a Canonical Constructor?

Given:

~~~java
record Customer(String id, int points, boolean active) {
}
~~~

the canonical constructor has a corresponding formal parameter list:

~~~java
Customer(String id, int points, boolean active)
~~~

**All components must match** in **order, name, and type**. It is not enough for a constructor to simply "have the same number of parameters". You cannot arbitrarily change `String id` to `String customerId` in an explicit canonical constructor declaration.

| Header component | Canonical formal parameter |
| --- | --- |
| `String id` | `String id` |
| `int points` | `int points` |
| `boolean active` | `boolean active` |

A constructor with a different signature, such as `Customer(String id)`, is a **non-canonical constructor**; it must perform an appropriate constructor invocation to another constructor of the same record, so that initialization goes through the canonical constructor.

Java does not allow a record to declare additional **custom instance fields** beyond the fields corresponding to its components; a record can have static fields, instance/static methods, and appropriate nested types. Therefore, the canonical constructor is the ideal central point for establishing the invariant of the record's state.

## 5. Explicit Canonical Constructor — You Assign the Fields Yourself

If you need to validate data and want to write the assignment logic explicitly:

~~~java
record Coordinate(int row, int column) {
    Coordinate(int row, int column) {
        if (row < 0 || column < 0) {
            throw new IllegalArgumentException("negative");
        }

        this.row = row;
        this.column = column;
    }
}
~~~

This is a **valid record**. The lines `this.row = row` and `this.column = column` are the responsibility of the **explicit canonical constructor**. Because record component fields are final, each field must be validly assigned before the constructor completes normally.

If you forget `this.column = column`, Java will detect that the field has not been initialized on the constructor's completion path; the program will not compile.

If the data is invalid, throwing `IllegalArgumentException` in the constructor is a suitable choice for many value objects. Other exception types can also be used depending on the API contract, but you should not construct an object in an invalid state and only handle it when it is used.

## 6. Complete Program 2 — Explicit Canonical Constructor

Create the file **`ExplicitCanonicalDemo.java`**:

~~~java
record Coordinate(int row, int column) {
    Coordinate(int row, int column) {
        if (row < 0 || column < 0) {
            throw new IllegalArgumentException(
                    "coordinates must be non-negative");
        }
        this.row = row;
        this.column = column;
    }
}

public class ExplicitCanonicalDemo {
    public static void main(String[] args) {
        Coordinate a = new Coordinate(2, 5);
        System.out.println("coordinate=" + a);
        System.out.println("row=" + a.row());

        try {
            new Coordinate(-1, 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Command:

~~~bash
javac -encoding UTF-8 ExplicitCanonicalDemo.java
java ExplicitCanonicalDemo
~~~

**Stdout:**

~~~text
coordinate=Coordinate[row=2, column=5]
row=2
invalid=coordinates must be non-negative
~~~

Because the constructor assigns `this.row` and `this.column` itself, omitting an assignment can cause compilation to fail. In return, you explicitly control when and what values are assigned, which is useful when the constructor needs to transform data using complex logic.

## 7. Compact Canonical Constructor — Shorthand Syntax

Still with two components, you can write:

~~~java
record Coordinate(int row, int column) {
    Coordinate {
        if (row < 0 || column < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}
~~~

This is a **valid record**. `Coordinate { ... }` is a **compact canonical constructor**, written without `(int row, int column)`.

The compiler provides the parameters `row` and `column` corresponding to the header. They are used directly in the body for validation or normalization. After the body completes normally, the compiler performs the corresponding assignments:

~~~java
// Mental model, not code written inside the compact constructor:
// this.row = row;
// this.column = column;
~~~

This is only a **behavioral description**. Do not copy `this.field = parameter` lines into the body of a compact constructor: that violates the rules of the language. Both constructor forms have **the same responsibility of initializing state**, but the place where field assignments appear is different.

## 8. Complete Program 3 — Compact Constructor to Validate an Invariant

Create the file **`CompactRangeDemo.java`**:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException(
                    "start must not exceed end");
        }
    }

    int length() {
        return end - start;
    }
}

public class CompactRangeDemo {
    public static void main(String[] args) {
        Range first = new Range(2, 7);
        Range zero = new Range(5, 5);

        System.out.println("range=" + first);
        System.out.println("length=" + first.length());
        System.out.println("zero=" + zero.length());

        try {
            new Range(8, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CompactRangeDemo.java
java CompactRangeDemo
~~~

**Stdout:**

~~~text
range=Range[start=2, end=7]
length=5
zero=0
invalid=start must not exceed end
~~~

The compact constructor only checks the relationship between the two parameters. There are no `this.start` and `this.end` assignment statements, because the compiler handles them after the body completes.

The `length()` method is an additionally defined method, not an accessor of a record component named length. If the interval followed an inclusive rule, the calculation might be `end - start + 1`; this lesson uses the simple distance `end - start` to avoid business-logic ambiguity.

## 9. Initialization Order: What Happens Before and After the Compact Body?

For a compact constructor:

1. The arguments of `new RecordType(...)` are evaluated according to Java rules.
2. A new record object is created and the construction process is executed.
3. The parameters corresponding to the record components already have values for the constructor body to use.
4. The code in the compact constructor runs: validation, normalization, or exceptions.
5. **If the body completes normally**, the component fields are assigned from their corresponding parameters as specified by the language.
6. Construction completes; the caller receives a valid object reference.

If the code in step 4 throws an exception, the object **is not returned as a successful result** of `new`. There is no process of "creating a record with invalid fields and fixing them later".

**Warning:** inside a compact constructor, do not read the state of `this`'s component fields in place of the identically named parameters before they are assigned. Check `start`, `end`, `name`, etc. directly. Calling instance methods may expose an incompletely initialized `this` externally or observe an unintended state.

## 10. Why Is `this.component = ...` Invalid in a Compact Constructor?

This is an **intentionally non-compiling snippet**:

~~~java
record BadPoint(int x, int y) {
    BadPoint {
        this.x = x; // Error: assigning a component field in a compact constructor.
        this.y = y; // Same error.
    }
}
~~~

In a compact constructor, the compiler reserves the initialization of component fields for the step **after the body**. Manually assigning fields is not only redundant, it is **prohibited**.

Do not try to fix it by removing `this.` and writing `x = x;`: that statement merely assigns a parameter to itself, performs no normalization, and makes the code harder to read.

If you want to assign fields manually, use an **explicit canonical constructor** with the full formal parameter list. If you want to validate/adjust parameter values and let the compiler assign them automatically, use a **compact constructor**.

## 11. Compact Constructors Can Normalize Parameters

The `name` and `email` parameters of a compact constructor are not treated as `final` simply because the component fields are final. You can **reassign the parameter itself**, and the compiler then uses **the new value** to initialize the field.

~~~java
record Username(String value) {
    Username {
        if (value == null) {
            throw new IllegalArgumentException("missing name");
        }
        value = value.strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank name");
        }
    }
}
~~~

This is a valid declaration. A call `new Username("  An  ")` creates an object whose `value()` is `"An"`.

Modifying **a parameter** in the compact body is completely different from mutating a component field after construction. The component field is still assigned once during record creation and cannot be changed afterward.

**Design note:** normalization must fit the domain. Do not automatically `trim`, lowercase, uppercase, strip diacritics, or normalize Unicode for all kinds of data, because those transformations may discard meaningful information.

## 12. Complete Program 4 — Canonicalizing String Data

Create the file **`CompactNormalizationDemo.java`**:

~~~java
import java.util.Locale;

record LoginName(String value) {
    LoginName {
        if (value == null) {
            throw new IllegalArgumentException("missing");
        }
        value = value.strip().toLowerCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank");
        }
    }
}

public class CompactNormalizationDemo {
    public static void main(String[] args) {
        LoginName first = new LoginName("  AN  ");
        LoginName second = new LoginName("an");

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
        System.out.println("same value="
                + first.equals(second));

        try {
            new LoginName("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CompactNormalizationDemo.java
java CompactNormalizationDemo
~~~

**Stdout:**

~~~text
first=an
second=an
same value=true
invalid=blank
~~~

The two calls have different initial arguments, but the compact constructor normalizes both to the same `value="an"`, so the record-generated `equals` considers them equal.

`Locale.ROOT` is chosen to avoid letting the machine's default locale alter lowercasing results for special cases. A real login policy still needs to clearly define Unicode normalization, allowed characters, and database uniqueness; this example only illustrates normalization in the constructor.

## 13. Equivalence in Invariants: Explicit and Compact

With the same idea of enforcing a non-null string with leading/trailing whitespace removed:

**Explicit canonical constructor:**

~~~java
record TagExplicit(String text) {
    TagExplicit(String text) {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        this.text = text.strip();
    }
}
~~~

**Compact canonical constructor:**

~~~java
record TagCompact(String text) {
    TagCompact {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        text = text.strip();
    }
}
~~~

These are **two valid record declarations**. Both constructor forms can establish the invariant that `text` is non-null and stripped. The differences are:

| Task | Explicit canonical | Compact canonical |
| --- | --- | --- |
| Writing the parameter list | Yes, matching the header | No |
| Accessing input in the body | Via the `text` parameter | Via the implicit `text` parameter |
| Initializing `this.text` manually | Must do so | Must not do so |
| Can normalize | Yes | Yes, by reassigning the parameter |
| Forgetting field assignment causes an error | May cause a compile-time error | Compiler assigns automatically |
| Suitable use case | Needs complex assignment control | Concise validation/normalization |

**Having the same invariant does not mean creating the same type:** `TagExplicit` and `TagCompact` are two different record types. Comparing `new TagExplicit("A")` with `new TagCompact("A")` using `equals` does not produce equality across two record types.

## 14. Complete Program 5 — Comparing the Two Constructor Forms

Create the file **`ConstructorFormsDemo.java`**:

~~~java
record ExplicitTag(String text) {
    ExplicitTag(String text) {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        this.text = text.strip();
    }
}

record CompactTag(String text) {
    CompactTag {
        if (text == null) {
            throw new IllegalArgumentException("missing");
        }
        text = text.strip();
    }
}

public class ConstructorFormsDemo {
    public static void main(String[] args) {
        ExplicitTag a = new ExplicitTag("  java ");
        CompactTag b = new CompactTag("  java ");

        System.out.println("explicit=" + a.text());
        System.out.println("compact=" + b.text());
        System.out.println("same content="
                + a.text().equals(b.text()));
        System.out.println("different records="
                + a.equals(b));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstructorFormsDemo.java
java ConstructorFormsDemo
~~~

**Stdout:**

~~~text
explicit=java
compact=java
same content=true
different records=false
~~~

Both implementations set the text field to `"java"` after normalization. However, `a.equals(b)` is false because the two objects are instances of **two different record types**, even though their contents are identical strings.

## 15. `Objects.requireNonNull` and Error Messages

For reference components, a record **does not automatically forbid null**. If you need a non-null invariant, you must explicitly enforce the condition in the constructor:

~~~java
import java.util.Objects;

record ProductCode(String code) {
    ProductCode {
        Objects.requireNonNull(code, "code");
    }
}
~~~

This is a valid declaration. `new ProductCode(null)` throws a `NullPointerException` with the message `"code"`. You can also use `IllegalArgumentException` if it fits your API policy; what matters is **consistency and documentation**.

Differences:

- `Objects.requireNonNull`: rejects null values, does not handle blank strings.
- `String.isBlank()`: checks Unicode whitespace according to `Character.isWhitespace` when the String is non-null.
- `String.strip()`: removes leading/trailing whitespace according to Java rules, without automatically validating length or format.
- `List.copyOf(...)`: creates an unmodifiable list from a collection, but rejects null elements and does not deep-copy object elements.
- Validating with a regex or parser: suitable when the domain defines an exact format.

Treat validation as **the public contract of a value object**, not merely a constructor syntax trick.

## 16. Complete Program 6 — Null, Blank, and Numeric Range

Create the file **`RecordValidationDemo.java`**:

~~~java
import java.util.Objects;

record AccountInput(String owner, int age) {
    AccountInput {
        Objects.requireNonNull(owner, "owner");
        owner = owner.strip();

        if (owner.isEmpty()) {
            throw new IllegalArgumentException("blank owner");
        }
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("invalid age");
        }
    }
}

public class RecordValidationDemo {
    public static void main(String[] args) {
        AccountInput accepted =
                new AccountInput("  An  ", 20);

        System.out.println("accepted=" + accepted);

        try {
            new AccountInput(null, 20);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getMessage());
        }

        try {
            new AccountInput("   ", 20);
        } catch (IllegalArgumentException ex) {
            System.out.println("blank=" + ex.getMessage());
        }

        try {
            new AccountInput("An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("age=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 RecordValidationDemo.java
java RecordValidationDemo
~~~

**Stdout:**

~~~text
accepted=AccountInput[owner=An, age=20]
null=owner
blank=blank owner
age=invalid age
~~~

The compact constructor guarantees that after construction, every valid AccountInput has a non-null/non-empty owner after stripping and an age within the specified range. `toString()` is generated by the record from the component fields after normalization.

Not every program should use an age limit of 150; that is an example of a **specific policy** and needs to be adjusted for the domain.

## 17. Canonical Constructors Cannot Declare a `throws` Clause

This is an important difference between a record constructor and a regular class constructor. According to JLS 17, **a record's canonical constructor cannot have a `throws` clause**. Therefore, the following snippet is **intentionally non-compiling**:

~~~java
record InvalidRecord(String raw) {
    InvalidRecord(String raw) throws java.io.IOException {
        this.raw = raw;
    }
}
~~~

A **compact constructor** also does not declare parameters or a `throws` clause:

~~~java
// INTENTIONALLY NON-COMPILING:
record InvalidCompact(String raw) {
    InvalidCompact throws java.io.IOException {
    }
}
~~~

You can still throw **unchecked exceptions** such as `IllegalArgumentException` or `NullPointerException` when validation fails. If validation depends on I/O that causes a checked exception, consider a named **factory method** that can declare `throws`, and then return a record once the data has been validated.

Avoid performing complex I/O directly inside the constructor of a record meant only to represent value data. If you need to load a file or query a service, separate that activity from construction.

## 18. Access Rules for the Canonical Constructor

When a record has a specific accessibility, the canonical constructor must have access **no more restrictive than** the record's access. For example, a public record needs a public canonical constructor if you declare an explicit/compact canonical constructor yourself.

~~~java
public record PublicPoint(int x, int y) {
    public PublicPoint {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}
~~~

This is **valid content of the file `PublicPoint.java`**, used as an illustrative snippet. For a public record, the `public` modifier is placed before the compact constructor.

The corresponding explicit form:

~~~java
public record PublicPoint(int x, int y) {
    public PublicPoint(int x, int y) {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("negative");
        }
        this.x = x;
        this.y = y;
    }
}
~~~

This is **an alternative version**; do not combine it with the compact version in the same file, as that would create two duplicate canonical constructors.

For a package-private record, the canonical constructor can be package-private as in the previous demos. **Do not narrow the access level** of a public record's canonical constructor just because you want the object to be created through a factory; the record contract has specific constraints on the canonical constructor.

## 19. Cannot Have Two Different Canonical Constructors for the Same Record

This is an **intentionally non-compiling snippet**:

~~~java
record BadPair(int left, int right) {
    BadPair {
        if (left > right) {
            throw new IllegalArgumentException("wrong order");
        }
    }

    BadPair(int left, int right) {
        this.left = left;
        this.right = right;
    }
}
~~~

Both parts above declare **the same canonical constructor**, one in compact form and one in explicit form. The compiler does not allow them to coexist.

You must **choose one**:

- Compact when you only need to validate or normalize parameters, letting the compiler assign fields automatically.
- Explicit when you need direct control over field assignments and conformance to strict definite assignment rules.

Do not call that an "overload" because both constructors have the same canonical signature; an overload must have **a different parameter list**.

## 20. Non-Canonical Constructor: Must Delegate Using `this(...)`

A record can have overloaded constructors to support convenient ways of instantiation, but **every non-canonical constructor must begin with an explicit constructor invocation to another constructor of the same record** according to Java 17 rules.

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("invalid range");
        }
    }

    Range(int end) {
        this(0, end);
    }
}
~~~

This is a valid record:

- `Range(int start, int end)` is the compact canonical constructor declared via `Range { ... }`.
- `Range(int end)` is a non-canonical overload.
- `this(0, end)` appears at the start of the overload, passing data into the canonical constructor.
- Validation in the canonical constructor still runs for every successful instantiation.

You **cannot** use a non-canonical constructor to bypass validation by setting fields manually. Records are designed to centralize component initialization through the canonical constructor.

## 21. Complete Program 7 — Overload Calling the Canonical Constructor

Create the file **`DelegatingRecordConstructorDemo.java`**:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("invalid range");
        }
    }

    Range(int end) {
        this(0, end);
    }

    int size() {
        return end - start;
    }
}

public class DelegatingRecordConstructorDemo {
    public static void main(String[] args) {
        Range shortForm = new Range(5);
        Range fullForm = new Range(2, 8);

        System.out.println("short=" + shortForm);
        System.out.println("full=" + fullForm);
        System.out.println("size=" + fullForm.size());

        try {
            new Range(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 DelegatingRecordConstructorDemo.java
java DelegatingRecordConstructorDemo
~~~

**Stdout:**

~~~text
short=Range[start=0, end=5]
full=Range[start=2, end=8]
size=6
invalid=invalid range
~~~

The call `new Range(-1)` goes through the `Range(int end)` overload and then into the canonical constructor with `start=0,end=-1`, where the invariant `start <= end` is violated and an exception is thrown.

An important advantage of delegation: **all object creation paths share a single validation point**.

## 22. Common Mistakes with Overloads

**Intentionally non-compiling:** a non-canonical constructor that does not call `this(...)` first:

~~~java
record BadOverload(int value) {
    BadOverload() {
        System.out.println("initializing");
        this(0);
    }
}
~~~

In Java 17, an explicit constructor invocation such as `this(0)` must be **the first statement** of the corresponding constructor body. You cannot add logging or validation statements before it in an overload.

Another overload is **intentionally non-compiling** if it attempts to assign a component field:

~~~java
record BadOverload(int value) {
    BadOverload() {
        this.value = 0;
    }
}
~~~

A non-canonical constructor cannot build a "separate path" to assign component fields directly; instead, it must delegate via `this(...)` according to record rules. To provide a default value, write `this(0)`.

**Design tip:** compute simple default expressions directly in the arguments of `this(...)` or move heavy logic to a static helper/factory. Never create an infinite `this(...)` constructor delegation cycle.

## 23. Null Checks and Defensive Copies for Collection Components

A record has final fields, but if a component is a `List<String>`, the list itself can be mutable. For example:

~~~java
record Team(String name, java.util.List<String> members) {
}
~~~

If the caller creates `new Team("A", mutableList)` and then modifies mutableList, the record will **observe the change** because the component reference points to the same object. `final` locks the reference field; it does not make the list immutable.

A compact constructor can create a **defensive snapshot**:

~~~java
record Team(String name, java.util.List<String> members) {
    Team {
        java.util.Objects.requireNonNull(name, "name");
        java.util.Objects.requireNonNull(members, "members");
        members = java.util.List.copyOf(members);
    }
}
~~~

This is a valid record. After the body, the `members` field is assigned **the copied list** rather than the list reference passed by the caller. `List.copyOf` returns an unmodifiable list and rejects null elements, but **does not deep-copy mutable elements inside**.

If the component list contains immutable `String` elements, this pattern is very suitable for a structural snapshot. If it contains mutable objects, you must also consider element ownership/deep copying.

## 24. Complete Program 8 — Compact Constructor Capturing a List Snapshot

Create the file **`DefensiveCopyRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Team(String name, List<String> members) {
    Team {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(
                Objects.requireNonNull(members, "members"));
    }
}

public class DefensiveCopyRecordDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Team team = new Team("Core", source);
        source.add("Binh");

        System.out.println("source=" + source);
        System.out.println("team=" + team.members());

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("mutation="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 DefensiveCopyRecordDemo.java
java DefensiveCopyRecordDemo
~~~

**Stdout:**

~~~text
source=[An, Binh]
team=[An]
mutation=UnsupportedOperationException
~~~

The record constructor creates a structural snapshot with one element An. The caller modifying source afterward does not change `team.members()`. The compiler-provided accessor returns an unmodifiable list, so `add` throws UnsupportedOperationException.

**Do not infer that every record is always deeply immutable**. This result comes from **the defensive copy in the compact constructor**, not just from the record declaration.

## 25. Array Components: Must Be Handled Both at Initialization and in the Accessor

For `byte[]`, `int[]`, and `String[]`, copying in the constructor only protects against the caller modifying **the source array**. The default record accessor still returns **the same array field reference**; the caller can modify the array inside the record after creation.

A complete defensive copy policy for an array typically requires:

1. Cloning the input in the compact constructor: `data = data.clone();`.
2. Overriding the `data()` accessor to return `data.clone()`.
3. If you want **value equality** based on array contents, designing an appropriate `equals`/`hashCode`; record-generated implementations do not automatically deep-compare array elements.

Do not treat `Arrays.equals` and record-generated `equals` as equivalent. For array components, record-generated `equals` uses equality based on the corresponding component object value, and arrays do not override `Object.equals` to compare contents.

For a data model that primarily holds a collection, a `List` snapshot can be simpler than an array if the API does not require an array for performance/interop.

## 26. Complete Program 9 — Compact Constructor Receiving an Array

To clearly observe **the compact constructor normalizing a parameter before Java assigns the component field**, create the file **`CompactArrayConstructorDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

record Samples(int[] values) {
    Samples {
        values = Objects.requireNonNull(values, "values").clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}

public class CompactArrayConstructorDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};
        Samples saved = new Samples(source);

        source[0] = 9;
        int[] returned = saved.values();
        returned[1] = 8;

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("returned=" + Arrays.toString(returned));
        System.out.println("saved=" + Arrays.toString(saved.values()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CompactArrayConstructorDemo.java
java CompactArrayConstructorDemo
~~~

Stdout:

~~~text
source=[9, 2]
returned=[1, 8]
saved=[1, 2]
~~~

In the compact constructor, `values` is **the parameter** that is replaced with a copy before the implicit assignment to the final component field. Having the getter return a clone is an explicitly declared **accessor method**, separate from the constructor; if you only copy on input, the default getter can still expose the array.

This example focuses on **constructor timing and initialization**, without using `equals` to avoid mixing two different contracts. How to design value equality for an array component is covered in the dedicated lesson on `equals/hashCode/toString`.

## 27. Generic Records Still Use a Canonical Constructor Based on Components

A record can declare a type parameter:

~~~java
record Pair<T>(T first, T second) {
    Pair {
        java.util.Objects.requireNonNull(first, "first");
        java.util.Objects.requireNonNull(second, "second");
    }
}
~~~

This is a valid record. The compact constructor does **not** repeat `<T>` or the `(T first, T second)` list; the parameters are inferred from the header.

Inside a method, you can write:

~~~java
Pair<String> pair = new Pair<>("A", "B");
~~~

This is a valid snippet. The generic type parameter `T` is part of the record declaration, not a separate type parameter of the canonical constructor.

If you write an explicit canonical constructor, you must preserve the types corresponding to the header (`T first`, `T second`), without creating an independent generic method/constructor that alters the canonical signature.

## 28. Complete Program 10 — Generic Record with a Compact Constructor

Create the file **`GenericRecordConstructorDemo.java`**:

~~~java
import java.util.Objects;

record Pair<T>(T first, T second) {
    Pair {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");
    }

    Pair<T> swapped() {
        return new Pair<>(second, first);
    }
}

public class GenericRecordConstructorDemo {
    public static void main(String[] args) {
        Pair<String> pair = new Pair<>("A", "B");
        Pair<String> swapped = pair.swapped();

        System.out.println("pair=" + pair);
        System.out.println("swapped=" + swapped);
        System.out.println("same=" + pair.equals(swapped));

        try {
            new Pair<>("A", null);
        } catch (NullPointerException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericRecordConstructorDemo.java
java GenericRecordConstructorDemo
~~~

**Stdout:**

~~~text
pair=Pair[first=A, second=B]
swapped=Pair[first=B, second=A]
same=false
invalid=second
~~~

`swapped()` does not modify the current record: it creates **a new Pair** and runs the canonical constructor again, so the non-null invariant is preserved. This is how data changes are expressed in value-object style.

## 29. Declaring a Record Does Not Mean Automatic Validation

Given:

~~~java
record Percentage(int value) {
}
~~~

the compiler still accepts `new Percentage(-10)` and `new Percentage(1000)`. Because `int` has no additional domain constraints, the record header by itself does **not** know the 0–100 range.

Adding a compact constructor:

~~~java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "outside 0..100");
        }
    }
}
~~~

makes the policy part of the **invariant**: every normal call through the canonical constructor must satisfy the value range.

You must distinguish between **"defining the data structure"** and **"determining what data is considered valid"**. The compact form reduces boilerplate, but deciding the constraints still belongs to domain design.

## 30. Complete Program 11 — Constructor Checking Bounds

Create the file **`PercentageRecordDemo.java`**:

~~~java
record Percentage(int value) {
    Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "outside 0..100");
        }
    }

    boolean isComplete() {
        return value == 100;
    }
}

public class PercentageRecordDemo {
    public static void main(String[] args) {
        Percentage half = new Percentage(50);
        Percentage full = new Percentage(100);

        System.out.println("half=" + half);
        System.out.println("half complete=" + half.isComplete());
        System.out.println("full complete=" + full.isComplete());

        try {
            new Percentage(101);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 PercentageRecordDemo.java
java PercentageRecordDemo
~~~

**Stdout:**

~~~text
half=Percentage[value=50]
half complete=false
full complete=true
invalid=outside 0..100
~~~

The record has an additional `isComplete()` method as a function computed from the immutable component. There is no need for a new `complete` field updated separately — thus state is not duplicated.

## 31. Writing an Explicit Canonical Constructor for Complex Normalization

A compact constructor is sufficient for most short validation/normalization tasks. However, an explicit canonical constructor is sometimes easier to structure if values are computed across multiple steps and you want to assign the field exactly once at the end.

For example:

~~~java
record Rectangle(int width, int height) {
    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("non-positive");
        }

        int normalizedWidth = width;
        int normalizedHeight = height;
        this.width = normalizedWidth;
        this.height = normalizedHeight;
    }
}
~~~

This is a valid record, though in this example the `normalizedWidth` and `normalizedHeight` variables provide no benefit; a compact constructor would be shorter and clearer.

Only choose the explicit form when controlling assignments directly genuinely improves readability. **Do not use the explicit form to bypass validation or leave record fields uninitialized** — the compiler still enforces the rules of final fields and the canonical constructor.

## 32. Rules to Remember for an Explicit Canonical Constructor

An explicit canonical constructor of a record must satisfy important requirements:

- The formal parameter list **matches the record components** in name, type, and order.
- It cannot declare its own type parameters for the canonical constructor.
- It cannot declare a `throws` clause.
- It cannot use an explicit constructor invocation `this(...)` or `super(...)` in the canonical constructor.
- It cannot redeclare instance fields corresponding to components to replace the generated fields.
- Component fields are final; you must perform valid and complete assignments when the constructor completes normally.
- The access of the canonical constructor must be at least as accessible as the record.
- If there is a canonical constructor declared by you, the compiler **does not provide** a second default canonical constructor.

The compact form differs from the explicit form in that it has no formal parameter list and does not write assignments to component fields.

These constraints ensure that record construction has a predictable structure, preventing an object with half of its components uninitialized from being published externally.

## 33. Rules to Remember for a Compact Canonical Constructor

For a compact constructor:

- Write `RecordName { statements }`, **without parentheses**.
- Formal parameters corresponding to the record components are provided implicitly.
- Use parameter names such as `name`, `amount`, `items` to validate or normalize.
- Parameters can be reassigned (`name = name.strip()`) if appropriate.
- **Do not directly assign** `this.name`, `this.amount`, etc.
- No `throws` clause and no separate type parameters can be declared.
- Do not place an explicit constructor invocation `this(...)` or `super(...)` in the body.
- Do not write a `return` statement to exit a compact constructor.
- After the body completes normally, the compiler automatically assigns all component fields.
- If the body throws an unchecked exception, construction fails.
- The access of the canonical constructor must follow the record's access.

Most records that need validation or defensive copying should use the **compact form** because it avoids boilerplate and reduces the chance of forgetting to assign a field.

## 34. Do Not Overuse Validation When the Constructor Needs to Be Reused

A record constructor needs to create a valid object. It should not take on responsibilities such as:

- Directly calling an HTTP API or database to load external references.
- Logging sensitive passwords/tokens and then throwing an exception.
- Creating a thread and publishing `this` while component fields have not finished being assigned.
- Performing non-rollbackable side effects before validation completes.
- Implicitly altering business data according to rules the caller is unaware of.
- Performing operations with blocking/unbounded cost just to "create a value".

When creating data requires I/O, use a factory/service to handle I/O and return a validated record. Constructors should be fast, deterministic, and easy to unit-test whenever possible.

In a compact constructor, the fact that fields are assigned **after the body** further underscores why `this` should not be published from an initializer/constructor. Do not call instance callbacks during the normalization step.

## 35. Record Components with Mutable Objects Require Care Regarding Equality

Generated record `equals` and `hashCode` are based on component values according to the record contract. If a component is a mutable object, there are two risks:

1. A mutable object changing after construction can alter the results observed through accessors or equality/hashCode.
2. For types such as arrays, equality by default object identity **is not equivalent to deep element equality**.

Therefore:

- For `String`, `Integer`, and immutable value objects, the canonical constructor is usually simple.
- For `List<String>`, you can create a `List.copyOf` snapshot.
- For `Map<K,V>`, you can consider `Map.copyOf`, while keeping the null policy and mutable values in mind.
- For `int[]`, clone on input/output if you want to prevent mutation, and define equality separately.
- For mutable domain objects, the constructor may need a deep defensive copy or a different representation.

You should not treat `record` as synonymous with **a deeply immutable aggregate**. Java only guarantees the structural constraints of record fields itself, while the immutability of the object graph is up to your design.

## 36. Constructors Are Invoked When Created Through Different Paths

In Java 17, record construction does not only occur with a `new SomeRecord(...)` expression. Some frameworks, reflection APIs, or record serialization may also rely on the canonical constructor according to their own contracts.

For the serialization mechanism supported by Java for serializable records, the canonical constructor plays a role in restoring the record. That makes constructor validation even more important, though it does not turn validation into a substitute for trust-boundary checks at the application layer.

In business code, you should test that every data creation path you expose **does not bypass invariants**. Do not rely on setters to "fix a record after creation"; record components do not have compiler-provided setters.

## 37. Complete Program 12 — Introspecting Record Components

Create the file **`RecordConstructorReflectionDemo.java`**:

~~~java
import java.lang.reflect.RecordComponent;

record Key(String namespace, String value) {
    Key {
        if (namespace == null || value == null) {
            throw new IllegalArgumentException("missing");
        }
    }
}

public class RecordConstructorReflectionDemo {
    public static void main(String[] args) {
        Class<Key> type = Key.class;

        System.out.println("isRecord=" + type.isRecord());

        for (RecordComponent component :
                type.getRecordComponents()) {
            System.out.println(component.getName() + ":"
                    + component.getType().getSimpleName());
        }

        Key key = new Key("orders", "A1");
        System.out.println("key=" + key);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 RecordConstructorReflectionDemo.java
java RecordConstructorReflectionDemo
~~~

**Stdout:**

~~~text
isRecord=true
namespace:String
value:String
key=Key[namespace=orders, value=A1]
~~~

`getRecordComponents()` returns metadata in the order of the components as declared in the record header. The canonical constructor is bound to that exact order and those types. Reflection is used here to illustrate **the structure of a record**, not to mutate final fields.

## 38. Code-Reading Exercise: Distinguishing Two Constructors

Consider the example:

~~~java
record Interval(int from, int to) {
    Interval {
        if (from > to) {
            throw new IllegalArgumentException("wrong order");
        }
    }

    Interval(int to) {
        this(0, to);
    }
}
~~~

This is a valid record.

Answer on your own before reading the answers:

- Which constructor is canonical?
- Which constructor is an overload/non-canonical?
- What does the line `this(0, to)` call?
- In the compact constructor, when are `this.from` and `this.to` assigned?
- Does `new Interval(-1)` create an object or throw an exception?
- Why cannot the overload place a `System.out.println(...)` statement before `this(0, to)` under Java 17?

**Answer:** `Interval { ... }` is the compact canonical constructor; `Interval(int to)` is a non-canonical overload. `this(0,to)` delegates to the canonical constructor (signature `Interval(int from,int to)`). The compiler assigns the component fields after the compact body succeeds. `new Interval(-1)` throws IllegalArgumentException because 0 is greater than -1. In Java 17, the explicit constructor invocation `this(...)` in an overload must be at the beginning of the constructor body.

## 39. Comparison Table for Choosing a Constructor Form

| Requirement | No constructor declared | Explicit canonical | Compact canonical |
| --- | --- | --- | --- |
| Only need to assign the components as-is | Best | Unnecessarily verbose | Unnecessary |
| Check for negative/null values | Insufficient | Yes | Yes, usually most concise |
| Normalize String before assignment | Insufficient | Yes | Yes, modify the parameter |
| Defensive copy `List` | Insufficient | Yes | Yes, modify the parameter |
| Manually control field assignments | Compiler does by default | Allowed | **Not allowed** |
| Forgetting to assign a component | Handled by compiler | May cause compile error | Handled by compiler |
| One-parameter constructor overload | Need to add overload | Overload calls canonical | Overload calls canonical |
| Transparent record contract | Yes | Yes if written properly | Yes if written properly |
| Need to call I/O / checked exceptions | Should extract a factory | Cannot declare `throws` on canonical | Cannot declare `throws` on canonical |

The compact form is not a "no-argument constructor". It is **a canonical constructor with implicit parameters** matching the record header. This is a common misconception worth avoiding when first learning.

## 40. Common Compile-Time Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Explicit canonical renames a parameter | Name does not match record header | Keep exact component names |
| Explicit canonical misses a `this.field` assignment | Final field not definitely assigned | Assign all fields, or use compact |
| Compact constructor assigns `this.field` | Component fields are assigned by the compiler after the body | Modify the parameter, not the field |
| Declaring both compact and explicit canonical | Two duplicate canonical constructors | Choose one |
| Writing `RecordName()` thinking it is compact | That is a 0-parameter overload | Compact must be written `RecordName { ... }` |
| Overload without `this(...)` | Non-canonical must delegate | Call another constructor of the same record |
| Placing statements before `this(...)` in an overload | Java 17 requires invocation to be first | Move logic to a helper/arguments |
| Adding `throws IOException` to canonical | Prohibited by JLS | Factory/service handles checked exception |
| Public record, private canonical constructor | Access narrower than record | Use public canonical |
| Using `return;` in compact | Return statement is not allowed | End block normally/throw |
| Forgetting to validate `null` | Record reference component can be null | `Objects.requireNonNull` |
| Thinking final field makes `List` immutable | Only the reference field is final | `List.copyOf` |
| Cloning input array but accessor returns original array | Caller can still mutate internal array | Override accessor to return a clone |
| Thinking array contents deep-equal automatically | Array equals uses identity | Design equality or another representation |
| Thinking constructor accepts new values after record creation | Fields have no setters; record values do not mutate that way | Create a new record |
| Putting many side effects in compact | Prone to partial initialization/confusing errors | Named factory, early validation |
| Treating an overloaded constructor as canonical | Differs from header signature | Delegate to canonical |
| Reassigning compact parameter thinking it updates field immediately | Field is assigned after body | Use parameter to validate, normalize |

## 41. Process for Explaining a Record Constructor

When reading a Java 17 record snippet, analyze:

1. Which components are in the **record header**, and what are their types/names/order?
2. **Is a constructor declared?** If not, there is an implicit canonical constructor.
3. If you see `RecordName { ... }`, it is a **compact canonical constructor**.
4. If you see `RecordName(T1 a, T2 b)`, compare it with the header to tell whether it is an explicit canonical constructor or a non-canonical overload.
5. If explicit canonical, check that all component fields are assigned on every normal completion path.
6. If compact, check validation/normalization on **parameters**, with no `this.component` assignment.
7. If non-canonical, check the initial `this(...)` statement and the final path to the canonical constructor.
8. Check access and forbidden `throws` on the canonical constructor.
9. Check whether null, range, and cross-field invariants are enforced when creating the object.
10. If a component holds a mutable object, check defensive copying and the accessor.
11. Only afterward evaluate `toString`, `equals`, `hashCode`, and output.
12. If there is an exception, determine which objects were actually successfully created and which side effects occurred.

Determine validity **at compile time** before predicting stdout; an example missing a field assignment or attempting to assign a field in a compact constructor has no runtime output.

## 42. Practice Exercises

**Question 1.** Given `record Point(int x,int y) {}`, which constructor does Java provide?

**Question 2.** Is `Point(int a,int b)` an explicit canonical constructor of Point, even though it has the same two int types?

**Question 3.** Is `Point { if(x<0) throw ...; }` a no-argument constructor?

**Question 4.** In an explicit canonical constructor, who must assign `this.x` and `this.y`?

**Question 5.** In a compact constructor, who assigns those fields, and when?

**Question 6.** Is it allowed to write `this.x = x` in a compact constructor?

**Question 7.** Is it allowed to write `x = Math.abs(x)` in a compact constructor to normalize the parameter?

**Question 8.** Why can `new Username(" An ")` produce a `value()` of `"An"` even though the component field is final?

**Question 9.** Can a record have both compact and explicit canonical constructors at the same time?

**Question 10.** What should a `Point()` constructor write if it wants to provide defaults `(0,0)`?

**Question 11.** In Java 17, can you write `System.out.println("start"); this(0,0);` inside a non-canonical constructor?

**Question 12.** Can a compact canonical constructor declare `throws IOException`?

**Question 13.** If a public record declares a private explicit canonical constructor, what happens?

**Question 14.** Does a record header automatically forbid `null` for a String component?

**Question 15.** What is the effect of `List.copyOf` in a compact constructor? Does it deep-copy mutable elements?

**Question 16.** Why is cloning the input array in the constructor not enough to prevent the caller from mutating the record state?

**Question 17.** Do two record instances whose array components have the same contents but are different array objects have generated equals return true?

**Question 18.** Can a generic record `Pair<T>` declare a compact constructor `Pair { ... }`?

**Question 19.** Can an overloaded constructor assign component fields directly instead of calling `this(...)`?

**Question 20.** When normalization turns two different inputs into the same components, what result does generated equals return if the record type is the same?

**Question 21.** If code inside a compact constructor throws IllegalArgumentException, does the caller receive a completed record object?

**Question 22.** How do `name()` and `getName()` differ for a record component `name`?

**Question 23.** Why should you not call a callback using `this` from a compact constructor before the fields are assigned?

**Question 24.** If validation needs to read a file or call a service that throws a checked exception, where should that logic be placed?

### Answers with Explanations

1. A canonical `Point(int x,int y)` is generated by the compiler if no replacement constructor is declared.
2. No; canonical parameter names must match the header (`x`, `y`).
3. No; the compact constructor has all parameters matching the header **implicitly**.
4. The explicit canonical constructor's code must assign all fields upon normal completion.
5. The compiler assigns them automatically after the compact body finishes normally.
6. No, assignments to record component fields are prohibited in the compact form.
7. Yes, you can modify the parameter `x` itself if the normalization fits the invariant.
8. The constructor updates the parameter before the compiler assigns the final field.
9. No; there can only be one canonical constructor for the same signature.
10. `Point() { this(0, 0); }` is a valid non-canonical overload.
11. No; in Java 17, the `this(...)` invocation must come first.
12. No; a canonical constructor does not allow a `throws` clause.
13. Compilation error because the access is narrower than the record's.
14. No; it must be validated according to the domain.
15. It snapshots an unmodifiable list structure, and does not deep-copy mutable elements.
16. The default accessor returns the array field reference; a defensive copy is needed when returning it.
17. No, generated equals does not deep-compare array contents.
18. Yes; the parameters and type variable belong to the header.
19. No; a non-canonical constructor must delegate through a constructor of the record.
20. If they are of the same type and their components are equal, record-generated equals returns true.
21. No; creation fails and the exception propagates to the caller.
22. The default accessor is `name()`; Java does not generate `getName()` by default.
23. Because component fields may not have been completely initialized yet, exposing the object or allowing invalid state to be read.
24. In a service/factory with an explicit I/O/throws contract, then create the record once the data is available.

## 43. Practice Checklist

- [ ] Identified the canonical parameter list directly from the record header.
- [ ] Chosen implicit, explicit, or compact based on actual needs.
- [ ] If explicit, formal parameter names/types/order match the components.
- [ ] If explicit, all component fields are validly assigned when the constructor completes.
- [ ] If compact, the body contains no direct assignment to `this.component`.
- [ ] If compact, parameters are normalized before the compiler's implicit assignment.
- [ ] No two canonical constructors exist for a single record.
- [ ] All overloaded non-canonical constructors call `this(...)` according to Java 17 rules.
- [ ] No `throws` clause on the canonical constructor.
- [ ] The accessibility of the canonical constructor is not narrower than the record.
- [ ] `null`, blank, and invalid range inputs are handled according to policy.
- [ ] Invariants involving multiple components are checked in the constructor.
- [ ] Mutable reference components have an appropriate snapshot/copy policy.
- [ ] For array components, a defensive accessor and equality/hashCode have been considered.
- [ ] No callbacks are called that leak `this` before the object is fully constructed.
- [ ] No heavy I/O or hard-to-rollback side effects are placed in the constructor.
- [ ] Verified that `componentName()` accessors and generated `toString`/`equals` behave as expected.
- [ ] Compiled each demo with Java 17+ and matched stdout.
- [ ] Intentionally invalid examples are clearly distinguished from runnable programs.

## 44. Official Java 17 Documentation

- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): the record concept and implicit members.
- [JLS 17 §8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): components, types, and declaration order.
- [JLS 17 §8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): explicit canonical, compact canonical, restrictions, and overloads.
- [JLS 17 §8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): component fields, accessors, and `equals`/`hashCode`/`toString`.
- [JLS 17 §8.8.7 — Constructor Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7): explicit constructor invocation and body rules.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): assignment constraints for final fields.
- [Java SE 17 API — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): record base class and value equality.
- [Java SE 17 API — Class.isRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isRecord()): runtime record type check.
- [Java SE 17 API — Class.getRecordComponents](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getRecordComponents()): record components metadata.
- [Java SE 17 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): null validation.
- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot, null policy.
- [Java SE 17 API — Arrays.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#equals(int[],int[])): comparing array contents when needed.
- [JEP 395 — Records (Final)](https://openjdk.org/jeps/395): design motivation, canonical constructors, and record immutability.

## 45. Summary

The **canonical constructor** of a record is always tied to **all record components**, in the exact order, names, and types. When no validation or normalization is needed, letting the compiler generate the constructor is the clearest approach.

When an invariant is needed, you have two choices:

- **Explicit canonical:** write `RecordName(T1 a, T2 b)`, validate the data, and then **manually assign** `this.a` and `this.b`.
- **Compact canonical:** write `RecordName { ... }`, validate or modify the **implicit parameters**, and then **let the compiler automatically assign** the component fields after the body completes normally.

Use **compact** for simple validation, canonicalization, and defensive copying; use **explicit** when manually controlling field assignments genuinely makes the code clearer. For overloaded constructors with different signatures, you must delegate via `this(...)` according to Java 17 rules so that all ways of creating an object go through shared validation.

Finally, **final record fields do not mean a deeply immutable object graph**. If components are lists/arrays/mutable types, you must decide on defensive copying, accessors, and equality based on the data contract. A good record is a value object with a clear structure, reliable invariants, and a constructor that fulfills a single responsibility: **creating a valid state**.
