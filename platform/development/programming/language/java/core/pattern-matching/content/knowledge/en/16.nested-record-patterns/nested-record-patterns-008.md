# Reading Nested Record Patterns from Outside In (Java 21+)

## 1. Main Idea

A **nested record pattern** helps check and deconstruct a structure consisting of multiple `record` types nested inside one another. When reading an expression with multiple nested pairs of parentheses, **start from the outermost record, identify each component in declaration order, and then drill down into any component that has a subsequent record pattern**. Finally, the leaf variables receive values to be used in the `if` or `case` body.

General example:

```java
Outer(var first, Inner(var second, Leaf(var third, var fourth)))
```

Read aloud: "The value must be an `Outer`; assign the first component to `first`; the second component must be an `Inner`; assign the first component of `Inner` to `second`; the remaining component must be a `Leaf`; assign the two components of `Leaf` to `third` and `fourth`."

**Version requirement:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have both been standard features since **Java 21**. The examples use JDK 21+ and do not require `--enable-preview`. Although `record` has existed since Java 16, Java 17 does not support nested record pattern syntax as a standard feature.

After this lesson, learners will be able to correctly read the type and order of each component, explain why a level fails to match, place `when` after deconstruction, and choose an appropriate nesting depth instead of deconstructing everything.

## 2. Read the Data Structure Before Reading the Pattern

Consider four records:

```java
record Point(int x, int y) {}
record Address(String city, Point point) {}
record Person(String name, Address address) {}
record Parcel(String code, Person receiver) {}
```

A `Parcel` contains a `Person`; that person contains an `Address`; the address contains a `Point`. The type tree can be represented as follows:

```text
Parcel
├── code: String
└── receiver: Person
    ├── name: String
    └── address: Address
        ├── city: String
        └── point: Point
            ├── x: int
            └── y: int
```

Each pair of parentheses in a record pattern represents **the list of patterns for the components of that exact record**. New variable names in the pattern do not determine position; the positions must match the record declaration. For example:

```java
Parcel(var code, Person(var name, Address(var city, Point(var x, var y))))
```

Reading from outside in:

| Level | Pattern part | What needs to be verified | Bound variables |
| --- | --- | --- | --- |
| 1 | `Parcel(..., ...)` | Input is a non-null `Parcel` | None yet, before deconstructing components |
| 1 → leaf | `var code` | First component of `Parcel` is `code` | `code` of type `String` |
| 2 | `Person(..., ...)` | `Parcel.receiver()` is a non-null `Person` | Variables of `Person` will be evaluated |
| 2 → leaf | `var name` | First component of `Person` is `name` | `name` of type `String` |
| 3 | `Address(..., ...)` | `Person.address()` is a non-null `Address` | Variables of `Address` will be evaluated |
| 3 → leaf | `var city` | First component of `Address` is `city` | `city` of type `String` |
| 4 | `Point(..., ...)` | `Address.point()` is a non-null `Point` | Variables of `Point` will be evaluated |
| 4 → leaf | `var x, var y` | Two `int` components of `Point` | `x` and `y` of type `int` |

**Quick reading tip:** whenever you encounter `Type(`, step into a new record; when you encounter `var name` or a leaf pattern, stop drilling down at that component; when you encounter `)`, step back out to the parent record. Commas separate components **within the same record**, not across levels.

This is a mental model for explaining structure and matching conditions, not a guarantee that the JVM creates intermediate objects or executes line by line like a sequential program. A record pattern does not create copies; it checks types and reads components using existing accessors.

## 3. Tracing with a Concrete Object

Suppose we have:

```java
Parcel parcel = new Parcel(
    "PK-21",
    new Person(
        "An",
        new Address("Hà Nội", new Point(3, 4))
    )
);
```

Check:

```java
if (parcel instanceof Parcel(
        var code,
        Person(var name,
            Address(var city, Point(var x, var y))))) {
    System.out.println(code + " | " + name + " | " + city
        + " | " + x + " | " + y);
}
```

This is an **illustrative snippet using the records just declared**, not a standalone runnable file. Output printed if placed in an appropriate program:

```text
PK-21 | An | Hà Nội | 3 | 4
```

Let's trace the structure, following the exact order of the component branches:

1. **Outermost:** the `parcel` object is a `Parcel`. The first component `code` receives `"PK-21"`.
2. **Into receiver:** the second component must match `Person(...)`. This is a check on the value of `parcel.receiver()`; if it is `null`, matching fails here.
3. **Into Person:** `name` receives `"An"`. The `address` component must match `Address(...)`.
4. **Into Address:** `city` receives `"Hà Nội"`. The `point` component must match `Point(...)`.
5. **Into Point:** `x` receives `3`, `y` receives `4`; there are no deeper nested record patterns.
6. **Back out:** if **all** subpatterns match, the entire `Parcel(...)` matches; the variables `code`, `name`, `city`, `x`, `y` can be used in the `if` body.

If the `Point(...)` level does not match, the **entire** nested pattern does not match. The program does not "partially deconstruct and then run the `if` body"; the variables are only in scope in the branch where the entire pattern succeeds.

## 4. Complete Java 21 Example: Reading Deep and Falling Back to Shallower Levels

Create the file **`NestedReadingDemo.java`**:

```java
public class NestedReadingDemo {
    record Point(int x, int y) {}
    record Address(String city, Point point) {}
    record Person(String name, Address address) {}
    record Parcel(String code, Person receiver) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "Giá trị null";

            // Read deep down to Point, then use a guard to check the name.
            case Parcel(
                    var code,
                    Person(var name,
                        Address(var city, Point(var x, var y))))
                    when name != null && code != null ->
                code + ": " + name + " ở " + city
                    + ", điểm (" + x + ", " + y + ")";

            // Point does not exist: stop at Address and receive point.
            case Parcel(
                    var code,
                    Person(var name, Address(var city, var point)))
                    when point == null ->
                code + ": thiếu tọa độ";

            // Address does not exist: stop at Person and receive address.
            case Parcel(
                    var code,
                    Person(var name, var address))
                    when address == null ->
                code + ": thiếu địa chỉ";

            // Person does not exist: stop at Parcel and receive receiver.
            case Parcel(var code, var receiver)
                    when receiver == null ->
                code + ": thiếu người nhận";

            // Structure is Parcel, but did not satisfy the conditions of the branches above.
            case Parcel(var code, var receiver) ->
                code + ": dữ liệu chưa hợp lệ";

            default -> "Không phải bưu kiện";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Parcel(
            "PK-21",
            new Person("An", new Address("Hà Nội", new Point(3, 4))))));

        System.out.println(describe(new Parcel(
            "PK-22",
            new Person("Bình", new Address("Huế", null)))));

        System.out.println(describe(new Parcel(
            "PK-23", new Person("Chi", null))));

        System.out.println(describe(new Parcel("PK-24", null)));

        System.out.println(describe(new Parcel(
            "PK-25",
            new Person(null, new Address("Đà Nẵng", new Point(5, 6))))));

        System.out.println(describe("abc"));
        System.out.println(describe(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 NestedReadingDemo.java
java NestedReadingDemo
```

Expected output:

```text
PK-21: An ở Hà Nội, điểm (3, 4)
PK-22: thiếu tọa độ
PK-23: thiếu địa chỉ
PK-24: thiếu người nhận
PK-25: dữ liệu chưa hợp lệ
Không phải bưu kiện
Giá trị null
```

**Why is the corresponding branch selected?**

- **PK-21:** every record from `Parcel` down to `Point` exists; `code` and `name` are non-null, so both the nested pattern and `when` succeed.
- **PK-22:** `Address.point()` is `null`, so the nested `Point(var x, var y)` fails. The second branch only requires `Address` to be present; `var point` receives `null` and the `point == null` guard is true.
- **PK-23:** `Person.address()` is `null`, so the first and second branches (both requiring `Address(...)`) do not match. The third branch deconstructs down to `Person` and receives `address == null`.
- **PK-24:** `Parcel.receiver()` is `null`, so branches containing `Person(...)` do not match. `var receiver` in the fourth branch receives null and the guard is true.
- **PK-25:** the nested record pattern **still matches structurally** because `var name` directly on a `String` component can receive null. The guard `name != null` is `false`; the subsequent guards checking for missing point/address/receiver are also false, so the final `Parcel(var code, var receiver)` branch runs.
- `"abc"` is not a `Parcel`, so it enters `default`; the `null` selector is handled by `case null`.

The highlight of this example is that **the reading depth can vary according to the purpose of each branch**: one branch goes all the way to `Point`, another stops at `Address`, and another only examines `Parcel`. All of them are still based on the same record declarations.

## 5. Distinguishing a Deep-Matching Pattern from a Variable Receiving the Whole Component

The following two syntaxes are **not equivalent in matching conditions**:

```java
// Checks that point is a non-null Point, then deconstructs x and y.
Parcel(var code, Person(var name,
    Address(var city, Point(var x, var y))))

// Does not require point to be a non-null Point;
// the variable point receives the entire Address.point() component.
Parcel(var code, Person(var name,
    Address(var city, var point)))
```

With `record Address(String city, Point point)`, the variable `point` in the second pattern has inferred type `Point`; it can be null, because `var point` is an unconditional type pattern for that `Point`-typed component. The first pattern uses the **record pattern** `Point(...)`, which a null value does not match.

Similarly:

```java
Parcel(var code, Person(var name, var address))
Parcel(var code, var receiver)
```

The first line checks that `Person` is non-null and keeps `Address` intact in the `address` variable; the second line does not drill into `Person`, it simply keeps `receiver` intact.

If a component does not need to be deconstructed further, stop at `var` or an appropriate type pattern. There is no need to write patterns for every level just to obtain a variable at an upper level.

## 6. `null` Rules at Each Level

Reading a nested pattern from outside in is also a way to determine **where a null value will cause the pattern to fail**.

| Value | `Parcel(var code, var receiver)` | `Parcel(var code, Person(var name, var address))` | Pattern nested down to `Point(var x, var y)` |
| --- | --- | --- | --- |
| `new Parcel("A", null)` | Matches: `receiver == null` | Does not match: `Person(...)` requires non-null | Does not match |
| `new Parcel("B", new Person("An", null))` | Matches | Matches: `address == null` | Does not match: `Address(...)` requires non-null |
| `new Parcel("C", new Person("An", new Address("Huế", null)))` | Matches | Matches | Does not match: `Point(...)` requires non-null |
| `new Parcel("D", new Person(null, new Address("Huế", new Point(1, 2))))` | Matches | Matches: `name == null` | Matches structurally; another guard may reject it |
| `null` (the selector itself) | Does not match record pattern | Does not match | Does not match |

**Distinguish three rules:**

1. **A record pattern itself does not match null**, at any depth: `Person(...)` or `Point(...)` requires the value at that level to be an actual record instance.
2. **A type pattern directly on a record component can match null if it is unconditional for that component's type**. `var name` on `String name` and `var receiver` on `Person receiver` are examples; they bind null values as well. Do not mechanically apply the rule of a top-level `instanceof String s` to `var s` inside a record pattern.
3. **A null `switch` selector** must be handled separately. `case null` is the explicit way to express it; do not expect `default` to automatically substitute for a null branch in a pattern matching switch.

Record patterns check **structure**; they do not automatically enforce business invariants such as "name must not be empty" or "parcel code is required". To guarantee valid data from the start, validate in the record's constructor; to filter during processing, use a `when` guard.

## 7. `when` Runs After the Entire Nested Pattern Matches

With `switch`, you can filter with an additional condition:

```java
case Parcel(
        var code,
        Person(var name, Address(var city, Point(var x, var y))))
        when x >= 0 && y >= 0 ->
    "Điểm có hai tọa độ không âm";
```

The **conceptual** order is: input matches `Parcel` → components must match each nested pattern → variables `x`, `y` are bound → evaluate the `when` guard → execute the branch if the guard is true. If the guard is false, `switch` evaluates the next matching branch. A guard cannot "rescue" a level that already failed: if `Point` is null, the expression `x >= 0` is not evaluated with any assumed `x` value.

Pattern variables are only in scope where the compiler determines the pattern has matched, including `when` and the body of the successful branch. You cannot use `x` or `name` outside that scope.

**Order branches from specific to general.** The following pattern **intentionally does not compile** because the general branch shadows the specific branch:

```java
// Dominance error example, not a runnable program.
return switch (input) {
    case Parcel p -> "Mọi Parcel";
    case Parcel(var code, Person(var name, var address)) ->
        "Không tới được nhánh này";
    default -> "Khác";
};
```

`case Parcel p` already accepts every non-null `Parcel`; the subsequent branch is **dominated**. Swap the two branches, or put specific/`when` branches first and then use the general branch as a fallback.

## 8. Comparison with Manual Accessor Calls

Without nested patterns, the same condition usually has to be expressed using multiple checks and accessor calls:

```java
// Conceptual illustration; assumes input is in method scope.
if (input instanceof Parcel p
        && p.receiver() != null
        && p.receiver().address() != null
        && p.receiver().address().point() != null) {
    String code = p.code();
    String name = p.receiver().name();
    String city = p.receiver().address().city();
    int x = p.receiver().address().point().x();
    int y = p.receiver().address().point().y();
    // Use code, name, city, x, y...
}
```

The manual approach may be appropriate when using only one component, when needing step-by-step checks with separate error messages, or when handling null with complex policies. Meanwhile, a nested pattern concisely expresses **"does the input have the exact structure to deconstruct?"** and binds variables directly:

```java
if (input instanceof Parcel(
        var code,
        Person(var name, Address(var city, Point(var x, var y))))) {
    // Use code, name, city, x, y...
}
```

The two snippets are only equivalent **in their intent to check the non-null structure of nested records**, not a mechanical replacement for all logic: records can contain null components, custom accessors can have special behavior, and manual accessor calls can be repeated.

If a custom record accessor throws an exception, the matching process may terminate with a `MatchException` (wrapping the underlying cause). Therefore, records and accessors should be simple and stable, avoiding unexpected side effects.

## 9. Method for Reading and Debugging Very Deep Patterns

When encountering a long expression, apply the following sequence:

1. **Find the opening:** which record does the pattern start with? Can the input object have that type?
2. **Read the record declarations:** write out the components in the **order** of the record, without assigning arbitrary names. Each record pattern must have the exact number of components.
3. **Indent by parentheses:** each `Type(` creates a level. Match the first pattern to the first component, the second pattern to the second component.
4. **Mark the leaves:** `var v` or `Type v` receives the component into a variable; `OtherRecord(...)` forces drilling deeper and requires that record to be non-null.
5. **Identify the nearest failure point:** ask "which level is missing or has the wrong type?". If a nested record fails to match, the entire outer pattern fails and moves to another branch.
6. **Read the guard last:** only when all levels match is `when` evaluated. For `switch`, check branch ordering and dominance errors.
7. **Verify output with concrete data:** test a complete case, a case missing a record at each level, a case with a false guard, and a null selector.

Example reformatted for readability:

```java
Parcel(
    var code,
    Person(
        var name,
        Address(
            var city,
            Point(
                var x,
                var y
            )
        )
    )
)
```

Although spanning multiple lines, this is still **a single pattern**, not a constructor call `new Parcel(...)`, and the names `code`, `name`, `city`, `x`, `y` here are **variables declared by the pattern**, not arguments passed to a constructor.

## 10. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Writing `Parcel(Person(...), var code)` causes a compiler error | Component order does not match `record Parcel(String code, Person receiver)` | Read the record declaration first, and order `code` then `receiver` correctly. |
| Missing or extra subpattern | Each record pattern must have the exact number of declared components | Count components per pair of parentheses for each record. |
| Using `Point(...)` with a regular class | `Type(...)` is a record pattern, only for **record classes** | Use a type pattern for regular classes or change the data model when appropriate. |
| `Point(...)` does not match even though `Address` exists | `Address.point()` is null or the value has an incompatible type | Read down to the `Point` level and check the data; use a shallower branch if null handling is needed. |
| Thinking `var name` eliminates null | A type pattern directly on a component can be **null-matching** | Use a `name != null` guard or validate in the constructor. |
| Accessing `x` after `switch`/`if` | Pattern variables are only in scope where a match is guaranteed | Use them inside the branch body or return the result out. |
| Specialized branch is unreachable | A general branch is placed before it, causing dominance | Move the specific nested pattern/guard earlier. |
| `javac` does not recognize `record pattern` | Using a JDK below 21 or an older language level setting | Check `javac -version` and compile with `--release 21` on JDK 21+. |
| Wanting to ignore a component with `_` on standard Java 21 | Unnamed patterns are a preview feature in Java 21 | Use a named `var unused` or intentionally configure preview; this lesson uses only stable syntax. |

## 11. Self-Check Exercises

Given `Parcel(var code, Person(var name, Address(var city, Point(var x, var y))))`:

1. Explain why `new Parcel("A", null)` does not match even though the outermost object is still a `Parcel`. State the exact level that fails.
2. Write a pattern that accepts a `Parcel` with a non-null `receiver` but **does not require** `address` to be non-null. Suggested answer: `Parcel(var code, Person(var name, var address))`.
3. Add a `when x == y` branch to specifically match `Point` instances on the line `x = y` and place it in the correct order relative to the general branch.
4. Use the table in Section 6 to predict which branch is selected when `Address.point()` is null and when `Person.name()` is null; run the example to verify.
5. Change `Point(var x, var y)` to `var point` at the exact same position, explain what type the new variable has, and how deep the structure is still checked.

**Key takeaway:** read patterns **from outside in according to component declarations**; `Record(...)` requires that level to be a non-null record; `var` can hold a component as-is including null; every level must match before the guard runs; place specific branches before general branches.

## References

- [Oracle Java 21 — Record Patterns, Nested Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — `14.30, Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
