# The Roles of `instanceof`, `switch`, and `record` in Java Pattern Matching

## 1. The Big Picture: Identifying, Branching, and Extracting Data

In Java, **pattern matching** is a way to check whether a value conforms to an expected shape/data type, while simultaneously declaring a variable to use the matched data. As a result, programs avoid repeating a manual type check followed by a type cast.

Suppose a method accepts an `Object`: the actual value might be a `String`, an `Integer`, a domain object, or `null`. To handle it, we typically need to answer three questions:

1. **What type is this object?** `instanceof` with a type pattern helps check a single possibility and obtain a typed variable.
2. **When there are multiple possibilities, which branch should be chosen?** `switch` with patterns helps express a multi-branch classification clearly and with compiler verification.
3. **What structure does the data have, and what components does it contain?** `record` declares a data-carrying type; a **record pattern** (Java 21+) allows matching and directly deconstructing the components of a `record`.

An important distinction: **a `record` itself is not pattern matching**. It is a way to define a data class. The syntax `Point(int x, int y)` in an `instanceof` or `case` context is what constitutes a *record pattern*.

| Tool | Primary Role | Stable Version |
| --- | --- | --- |
| `obj instanceof T value` | Checks a type pattern and creates a variable of type `T` | Java 16 |
| `record Point(int x, int y) {}` | Defines a data type whose components are exposed via accessors | Java 16 |
| `switch` expression with constant labels | Selects a result based on `int`, `String`, `enum`, etc. | Java 14 |
| `switch` with `case T value` and `when` | Matches multiple types/conditions in order | Java 21 |
| `Point(int x, int y)` as a record pattern | Checks `Point` and extracts its components | Java 21 |
| `sealed` interface/class | Restricts allowed subtypes, helping `switch` cover all cases | Java 17 |

In Java 17, `instanceof` patterns and `record` are already available for regular use; pattern matching for `switch` was still in *preview*, so it cannot be used as stable Java 17 syntax. The type-based `switch` and record pattern examples below require **JDK 21 or later**.

## 2. `instanceof`: Identifying a Single Type and Eliminating Redundant Casts

### Before and After Type Patterns

The traditional approach checks the type first, then casts inside the confirmed branch:

```java
static int length(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return text.length();
    }
    return 0;
}
```

With a type pattern, `text` is assigned only when `input` is actually a `String`:

```java
static int length(Object input) {
    if (input instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Here, `String text` is both a **type check** and a **variable bound to the matched value**. The type of `text` is already known to the compiler, so no cast is needed. When `input == null`, `instanceof String text` returns `false`.

### Variable Scope Depends on Control Flow

Java only allows using a pattern variable where the compiler can prove that the match succeeded. Because `&&` evaluates the right-hand side only when the left-hand side is true, this is valid:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Conversely, the following expression **does not compile**, because on the right-hand side of `||`, `text` might not have been assigned:

```java
// INVALID:
// if (input instanceof String text || text.isBlank()) { ... }
```

An early-exit branch can also keep the variable in scope afterward:

```java
static String normalized(Object input) {
    if (!(input instanceof String text)) {
        return "Không phải chuỗi";
    }
    return text.strip();
}
```

Practical rule: use `instanceof` when you only need to handle **one specific type**, or when a short condition is more natural than multiple `switch` branches.

## 3. `record`: Modeling Data to Make Matching Clear

A `record` is a kind of class used to represent data with a fixed structure, such as coordinates:

```java
record Point(int x, int y) {}
```

The declaration above automatically generates the corresponding constructor, the `x()` and `y()` accessors, as well as `equals()`, `hashCode()`, and `toString()`. Component fields are `private final`; a `Point` object has no generated setters. Access is done via `point.x()`, not `point.getX()`.

A `record` lets the reader immediately see what components a value consists of. However, it **does not guarantee deep immutability**: if a component holds a mutable `List`, the contents of the list can still be modified. Nor does a `record` automatically forbid `null`; validation can be added in the constructor when the domain requires it.

```java
record User(String name, int age) {
    User {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be non-negative");
        }
    }
}
```

This is a *compact constructor*: Java assigns the component parameters to the record's fields after the constructor body runs. A record is still a class (implicitly `final`, extending `java.lang.Record`); it can implement interfaces, but cannot extend an arbitrary class.

### Complete Example for Java 17

The file **`Instanceof17Demo.java`** combines `record` and type patterns; no preview features are needed at all:

```java
public class Instanceof17Demo {
    record Point(int x, int y) {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Text: " + text.strip();
        }
        if (value instanceof Point point) {
            return "Point: " + point.x() + "," + point.y();
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe("  Hello  "));
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac Instanceof17Demo.java
java Instanceof17Demo
```

Output:

```text
Text: Hello
Point: 2,3
Other
```

Here, `record Point` defines the **shape of the data**; `instanceof Point point` only confirms the type and grants access through `point.x()` and `point.y()`. It does **not** directly extract the two components into `x` and `y` variables—that is the role of record patterns in Java 21.

## 4. `switch`: Choosing Among Multiple Patterns

### How Do Traditional `switch` and Pattern `switch` Differ?

A traditional `switch` selects a branch based on a **constant value** (such as `case "DONE"` or `case 1`). This style of `switch` expression was already stable before Java 17:

```java
static String label(String status) {
    return switch (status) {
        case "NEW" -> "Mới";
        case "DONE" -> "Hoàn tất";
        default -> "Khác";
    };
}
```

Starting in Java 21, `switch` can also select a branch based on the **type and condition** of a value:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case Integer n -> "Số nguyên: " + n;
        case String text when text.isBlank() -> "Chuỗi trống";
        case String text -> "Chuỗi: " + text;
        default -> "Kiểu khác";
    };
}
```

`case String text` checks the type and creates the variable `text`. `when text.isBlank()` is an additional condition (*guard*), evaluated only after the pattern matches. The guarded `String` branch must appear before the general `String` branch.

### Ordering, Exhaustiveness, and `null`

- **Order matters.** If `case CharSequence chars` appears before `case String text`, the `String` branch is shadowed (*dominated*) because every `String` is a `CharSequence`; Java reports a compile-time error. Place specific cases before broader ones.
- **Exhaustiveness.** A `switch` expression must cover every possible case. When switching on `Object`, `default` is typically required. With a `sealed` type hierarchy, the compiler can verify that all valid subtypes are listed, so `default` is not needed.
- **`null` must be considered explicitly.** Ordinary type patterns do not match `null`; if a `switch` encounters `null` without `case null`, it may throw a `NullPointerException`. A regular `default` does not substitute for handling `null`.
- **Pattern variables are scoped to their corresponding branch.** A variable from `case Integer n` does not exist in the `case String text` branch or after the `switch`.

Use `switch` when multiple input types map to distinct actions, especially when you want the compiler to warn about missing cases.

## 5. Record Patterns: Type Checking and Data Extraction Directly in the Pattern (Java 21+)

The type pattern `Point point` only binds a name to the **entire** object. The record pattern `Point(int x, int y)` goes one step further: it checks that the object is a `Point`, then matches each component in turn to bring `x` and `y` into scope.

The following snippet is placed inside a Java 21 class that declares `record Point(int x, int y) {}`:

```java
Object candidate = new Point(2, 3);

if (candidate instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

Record patterns can also be nested when the data model contains other records:

```java
record Address(String city) {}
record Person(String name, Address address) {}

// Assume the record declarations are in the same class scope as the usage snippet:
Object value = new Person("An", new Address("Hà Nội"));
if (value instanceof Person(String name, Address(String city))) {
    System.out.println(name + " ở " + city);
}
```

When run in the stated context, the printed line is `An ở Hà Nội`. The snippets in this section are **syntax illustrations**, not standalone Java files; a complete runnable example appears right below.

A record pattern is a tool for **checked deconstruction**: it does not mutate the original object, call setters, or create a copy. If a nested record structure contains a `null` value, a sub-pattern requiring a specific object type may fail to match; therefore, you should design data invariants or handle `null` appropriately.

## 6. Combining `sealed`, `record`, and `switch` for Multi-Variant Data

Each tool handles one part of the model:

- `sealed interface Event` defines the **set of allowed variants**.
- `record Moved` and `record Stopped` define the **data for each variant**.
- `switch` with patterns selects the **corresponding handling logic**; the record pattern extracts coordinates directly from `Moved`.
- `when` distinguishes special cases within the same variant.

Create the file **`PatternSwitch21Demo.java`**:

```java
public class PatternSwitch21Demo {
    sealed interface Event permits Moved, Stopped {}

    record Moved(int x, int y) implements Event {}
    record Stopped() implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case null -> "No event";
            case Moved(int x, int y) when x == 0 && y == 0 -> "Origin";
            case Moved(int x, int y) -> "Moved(" + x + ", " + y + ")";
            case Stopped ignored -> "Stopped";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Moved(0, 0)));
        System.out.println(describe(new Moved(2, 3)));
        System.out.println(describe(new Stopped()));
        System.out.println(describe(null));
    }
}
```

Compile and run with JDK 21 or later, targeting Java 21:

```bash
javac --release 21 PatternSwitch21Demo.java
java PatternSwitch21Demo
```

Exact output:

```text
Origin
Moved(2, 3)
Stopped
No event
```

No `default` is needed because `Event` is `sealed` and the unguarded branches already cover both `Moved` and `Stopped`; `case null` handles `null` explicitly. If you later add a `record Paused() implements Event` variant and update `permits`, the compiler will report that the `switch` is not exhaustive when recompiling the handling code.

By contrast, a `switch` on `Object` cannot know all possible input types, so it usually requires a `default`. For a bounded domain relationship, the `sealed + record + switch` trio models a finite set of choices cleanly.

## 7. Which Tool Should You Choose for Each Problem?

| Scenario | Suitable Approach | Reason |
| --- | --- | --- |
| A single special branch when the input is a `String` | `if (obj instanceof String s)` | Concise, no manual cast required |
| Input has multiple types, each with different rules | `switch` with type patterns (Java 21+) | Branches and ordering are visible in one place |
| Need a small data type such as coordinates, time intervals, or calculation results | `record` | Clearly states components; auto-generates constructor/accessors/value methods |
| Need to extract multiple components of a record directly | Record pattern (Java 21+) | Avoids manually calling multiple accessors in conditions and branches |
| A closed set of domain variants, e.g., `Success`/`Failure` | `sealed` + subtypes + `switch` | Checks exhaustiveness when new variants are added |
| Project must run on Java 17 without preview enabled | `instanceof` pattern + `record` + `if/else` or constant `switch` | Does not depend on Java 21 syntax |

Not every `if/else` needs to be converted into a `switch`: if you are only checking one case, `instanceof` is clearer. Not every class should become a `record`: objects with their own identity, mutable state, or complex behavior usually need regular classes. And `record` does not have to be paired with pattern matching; many records are used normally via their accessors.

## 8. Common Pitfalls and Self-Check

1. **Confusing version milestones.** `record` and `instanceof T t` run stably on Java 17; `case T t`, `when`, and `Point(int x, int y)` as patterns in the examples require Java 21+. Projects should explicitly configure `--release` or the language level in the build tool/IDE.
2. **Assuming `record` deconstructs data by itself.** `record Point(int x, int y)` defines the type; `instanceof Point p` only creates the variable `p`; `instanceof Point(int x, int y)` is what creates the component variables.
3. **Using a pattern variable outside its guaranteed-match scope.** Carefully check `&&`, `||`, negation `!`, and early-exit branches; the compiler uses flow-sensitive analysis to verify this.
4. **Placing a general pattern before a specific pattern in `switch`.** For example, `CharSequence` dominates `String`. With `when`, a guarded branch should come before an unguarded branch of the same type.
5. **Forgetting `null`.** `instanceof` with `null` evaluates to `false`; pattern `switch` may need `case null`; record components can also be `null` if not validated.
6. **Equating `final` with deep immutability.** A record keeps the component reference fixed; the object that the reference points to may still be mutable. When immutable data is needed, use immutable component types or defensive copies.
7. **Misusing parameterized patterns that cannot be checked at runtime.** For example, `instanceof java.util.List<String> list` is invalid as a regular type check because generics are erased; you usually have to match `List<?> list` and check elements if needed.

### Practice Exercises

- On Java 17, add an `Integer` branch to `Instanceof17Demo.describe`. Test with `null`, a blank string, and `Point`; explain which branch is selected.
- On Java 21, add a `Paused` variant to `Event`, update `permits`, and observe the `switch` compile error before adding `case Paused p`.
- Try placing `case Moved(int x, int y)` before `case Moved(int x, int y) when x == 0 && y == 0` and explain why the guarded branch is dominated.

**Remember:** `instanceof` identifies **a single type**; `switch` organizes **multiple matching branches**; `record` describes **the shape of data**; and record patterns extract **the components** of that data. When used in the right place, they clarify control flow and reduce manual casting, though they do not replace careful data modeling and `null` handling.

## Official References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
