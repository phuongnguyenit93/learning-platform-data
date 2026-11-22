# Combining Record Patterns with Type Patterns in Java 21

In Java, a **type pattern** checks the type and binds a name to **the entire object**, while a **record pattern** checks a record and **deconstructs its components**. When combining these two kinds of patterns, we can both recognize the structure of the data and choose whether to keep an object whole or further deconstruct each component as needed.

This lesson uses **Java 21 or later**. Pattern matching for `instanceof` has been stable since Java 16 (JEP 394); record patterns (JEP 440) and pattern matching for `switch` (JEP 441) became official in Java 21. The Java 21 examples in this lesson do not require `--enable-preview`.

## 1. Distinguishing the two patterns before combining them

Suppose we have the following record:

```java
record Point(int x, int y) {}
```

Given an `Object input` variable holding `new Point(2, 3)`, compare:

```java
// Type pattern: captures the entire Point object.
if (input instanceof Point p) {
    System.out.println(p.x() + p.y()); // 5
}

// Record pattern: directly deconstructs the two components.
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

- `Point p` is a **type pattern**: it checks whether `input` is a `Point` and binds the entire object to `p`. To read its components, use the accessors `p.x()` and `p.y()`.
- `Point(int x, int y)` is a **record pattern**: it checks the `Point` object and then applies two component patterns, `int x` and `int y`, immediately giving you the two variables `x` and `y`.
- `int x` and `int y` are **type patterns in component positions** of the record pattern. Therefore, even a simple record pattern can already include type patterns.
- There is no “destructuring assignment” such as `(x, y) = point` in Java 21; deconstruction syntax here is used in pattern matching contexts such as `instanceof` and `case`.

Both approaches **read** the existing record. They do not invoke the constructor to create a new record and do not mutate the record's components.

## 2. A data model that requires combining multiple patterns

Consider an outer record containing multiple data types:

```java
record Point(int x, int y) {}
record Owner(String name) {}
record Envelope(String id, Object payload, Owner owner) {}
```

`Envelope` consists of:

| Component | Declared type | Meaning |
| --- | --- | --- |
| `id` | `String` | Identifier of the data envelope |
| `payload` | `Object` | Content that may be a `Point`, a `String`, or another type |
| `owner` | `Owner` | Owner information, which is itself a record |

Because `payload` has the declared type `Object`, it is not known in advance whether the content is actually a `Point` or a `String`. The goal of combining patterns is to **check the type at the exact position** and only extract variables that have been verified.

## 3. Using type patterns directly inside a record pattern

The first example only deconstructs the outer record, while keeping the matched objects intact for `payload` and `owner`:

```java
Object candidate = new Envelope(
        "E1", new Point(2, 3), new Owner("Lan"));

if (candidate instanceof Envelope(String id, Point p, Owner owner)) {
    System.out.println(id);        // E1
    System.out.println(p.x());     // 2
    System.out.println(owner.name()); // Lan
}
```

Reading the expression `Envelope(String id, Point p, Owner owner)` from the outside in:

1. `Envelope(...)` is a **record pattern**. `candidate` must be a non-`null` `Envelope`.
2. `String id` is a **component type pattern** for the first component (declared as `String`). It declares the variable `id`.
3. `Point p` is a **component type pattern** placed on the `payload` component (declared as `Object`). It only matches when the content is actually a `Point` object; the variable `p` holds **the entire `Point` object**.
4. `Owner owner` is a **component type pattern** for the third component (declared as `Owner`); the variable `owner` holds the `Owner` record so `owner.name()` can be called.

If `payload` holds a `String`, the pattern in step 3 does not match and the entire `instanceof` check returns `false`. No manual cast from `Object` to `Point` is needed.

Here Java still deconstructs `Envelope`, but we intentionally **do not further deconstruct** the `Point` and `Owner` objects. This approach is suitable when you need to call accessors or pass the whole object to another method.

## 4. Nesting record patterns alongside type patterns

If you need the coordinates and the owner's name directly, replace `Point p` and `Owner owner` with nested record patterns:

```java
Object candidate = new Envelope(
        "E1", new Point(2, 3), new Owner("Lan"));

if (candidate instanceof
        Envelope(String id, Point(int x, int y), Owner(String name))) {
    System.out.println(id + ": (" + x + "," + y + "), owner=" + name);
    // E1: (2,3), owner=Lan
}
```

Structure:

```text
Envelope(
    String id,               // Type pattern for the id component
    Point(int x, int y),     // Record pattern for payload
    Owner(String name)       // Record pattern for owner
)
```

- `Envelope(...)` is the outer record pattern.
- `String id` is a type pattern directly inside `Envelope`.
- `Point(int x, int y)` is a nested record pattern for `payload`; inside it are two type patterns `int x` and `int y`.
- `Owner(String name)` is a nested record pattern for `owner`; inside it is the type pattern `String name`.
- The variables `id`, `x`, `y`, and `name` can only be used in places where the compiler knows **the entire pattern has matched successfully**.

Matching follows the record declaration structure, **not variable names**. `Point(int a, int b)` still deconstructs component `x` into `a` and component `y` into `b`.

### Some matching results

| Data | Nested pattern above | Reason |
| --- | --- | --- |
| `Envelope("E1", new Point(2,3), new Owner("Lan"))` | Matches | Correct three components and nested structures |
| `Envelope("E2", "hello", new Owner("Minh"))` | Does not match | `payload` is not a `Point` |
| `Envelope("E3", new Point(9,9), null)` | Does not match | The record pattern `Owner(...)` does not accept `null` |
| `Envelope("E4", new Point(0,0), new Owner(null))` | Matches | `Owner` exists; the component type pattern `String name` can accept `null` |
| `null` | Does not match | The outer record pattern `Envelope(...)` does not accept `null` |

Details about `null` in component type patterns are analyzed in section 7.

## 5. Combining a record pattern with different kinds of type patterns

For the `payload` field declared as `Object`, we can place the type pattern `String text` instead of the nested record pattern `Point(...)`:

```java
Object candidate = new Envelope(
        "E2", "hello", new Owner("Minh"));

if (candidate instanceof Envelope(
        String id, String text, Owner(var ownerName))) {
    System.out.println(id + " text=" + text + ", owner=" + ownerName);
    // E2 text=hello, owner=Minh
}
```

In this example:

- `String id` matches the `id` component declared as `String`.
- `String text` is placed on the `payload` component declared as `Object`. It **checks the type at runtime** and only accepts a payload that is a non-`null` `String`.
- `Owner(var ownerName)` is a record pattern nested inside `Envelope`. `var ownerName` infers the component type of `name` as `String`.

`var` in a record pattern is **static** type inference based on the record declaration. It is not a dynamically typed variable. If you write `Envelope(var id, var payload, var owner)`, the inferred types are `String`, `Object`, and `Owner` respectively, and there is no constraint that `payload` is actually a `Point` or a `String`.

### Keep the nested record or deconstruct it further?

The two versions below check the same case where `payload` is a `Point`, but differ in the data used in the matching branch:

```java
// Keep the entire Point and read via accessor.
if (candidate instanceof Envelope(var id, Point p, var owner)) {
    System.out.println(p.x());
}

// Deconstruct Point to get the two int variables directly.
if (candidate instanceof Envelope(var id, Point(var x, var y), var owner)) {
    System.out.println(x);
}
```

Use `Point p` when you need to pass `p` to another method; use `Point(var x, var y)` when you need each component directly. Both only match when `payload` is actually a non-`null` `Point`.

## 6. Combining chained matches with &&

Not every combination has to live inside **one** nested record pattern. We can deconstruct the outer record first and then check a component with another type pattern using `&&`:

```java
if (candidate instanceof Envelope(var id, var payload, var owner)
        && payload instanceof Point p) {
    System.out.println(id + " has point x=" + p.x());
}
```

The left-hand side checks that `candidate` is an `Envelope` and declares the variable `payload` (with static type `Object`). The right-hand side checks whether `payload` is a `Point` and binds the entire object to `p`. Because the `&&` operator evaluates from left to right and only evaluates the right-hand side when the left-hand side is true, `payload` is already in scope when reaching `payload instanceof Point p`.

This expression serves a filtering purpose similar to:

```java
if (candidate instanceof Envelope(var id, Point p, var owner)) {
    System.out.println(id + " has point x=" + p.x());
}
```

For simple structures, the nested record pattern version is shorter; for multiple independent checks or when `payload` needs to be used in multiple ways, the `&&` version can be more convenient.

**Scope note:** if you use `||` or try to read a pattern variable where the matching branch is not guaranteed, the code may fail to compile. Do not rely on identical variable names to assume they always exist outside the condition.

## 7. Important difference when encountering null

An easy-to-confuse rule is: **a record pattern does not match a `null` record object**, whereas **a type pattern in a record component position can match `null` if it is an unconditional pattern for the declared type of that component**.

Given `record Envelope(String id, Object payload, Owner owner)`, consider:

```java
Object candidate = new Envelope(null, null, new Owner(null));
```

The following expressions evaluate to:

```java
candidate instanceof Envelope(String id, var payload, var owner)
// true: String id is unconditional for the declared String component;
//       the variables id and payload can receive null.

candidate instanceof Envelope(var id, String text, var owner)
// false: String text requires the Object payload to actually be a non-null String.

candidate instanceof Envelope(var id, var payload, Owner(String name))
// true: Owner is non-null and the component String name can receive null.
```

The three expressions above are illustrative examples, not standalone Java statements placed inside a complete method. The results are also verified in the full runnable program in section 9.

If the nested record `owner` is `null`, the pattern `Owner(String name)` or `Owner(var name)` **does not match**. If `owner` exists but `owner.name() == null`, the type pattern `String name` inside `Owner(...)` can match the `null` component because it is unconditional for the declared type `String`.

Clearly distinguish the **outer level**:

```java
Object candidate = null;

if (candidate instanceof Envelope(var id, var payload, var owner)) {
    // Does not run: candidate is null.
}
```

And remember that a **top-level type pattern** in `instanceof` also does not match `null`; for example, `candidate instanceof String s` returns `false` when `candidate == null`. The ability of a component type pattern to accept `null` is a specific rule when the pattern is applied to a record component.

Do not call `name.length()` or `id.length()` immediately just because a record pattern matched: a variable of a reference type can hold `null`. Check with `== null` or enforce constraints in the record constructor when required by business logic.

## 8. Combining multiple patterns in switch

Java 21 `switch` allows classifying payload forms directly in `case` labels. When there are narrow branches and a broad branch, place the specific branches first:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "input=null";
        case Envelope(String id, Point(int x, int y), Owner(String name)) ->
                id + " point=(" + x + "," + y + "), owner=" + name;
        case Envelope(String id, String text, Owner(var name)) when !text.isBlank() ->
                id + " text=" + text + ", owner=" + name;
        case Envelope(var id, var payload, var owner) -> "Other envelope: " + id;
        default -> "Not an envelope";
    };
}
```

- **Point** branch: the `Envelope` record pattern combines the type pattern `String id` with two nested record patterns `Point` and `Owner`; it only matches when all records being deconstructed are non-null.
- **String** branch: `String text` checks the runtime type of `payload`. `when !text.isBlank()` is only evaluated after every pattern in the case has matched, so calling `text.isBlank()` is safe here.
- **Remaining Envelope** branch: `var` on each component accepts any component value, including `null`. This branch handles payloads of other types or nested structures that do not qualify for the two preceding branches.
- `case null` handles **a `null` selector `value`**; it does not handle every `null` component inside the record.
- `default` handles objects that are not an `Envelope`.

**Ordering and dominance:** `case Envelope(var id, var payload, var owner)` is a broad case that matches every non-`null` `Envelope`. If placed before `case Envelope(String id, Point(...), Owner(...))`, the specific case after it would be *dominated* and Java would reject compilation. When a guard condition is meaningful, place the case with `when` before the corresponding general case.

In a `switch` with a potentially `null` selector, do not assume `default` handles `null`: explicitly specify `case null` if you need custom behavior; otherwise, a `null` selector may throw a `NullPointerException`.

## 9. Complete program running on Java 21+

Save the following code as **`PatternCompositionDemo.java`**:

```java
public class PatternCompositionDemo {
    record Point(int x, int y) {}
    record Owner(String name) {}
    record Envelope(String id, Object payload, Owner owner) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "input=null";
            case Envelope(String id, Point(int x, int y), Owner(String name)) ->
                    id + " point=(" + x + "," + y + "), owner=" + name;
            case Envelope(String id, String text, Owner(var name)) when !text.isBlank() ->
                    id + " text=" + text + ", owner=" + name;
            case Envelope(var id, var payload, var owner) -> "Other envelope: " + id;
            default -> "Not an envelope";
        };
    }

    static String inspectPayload(Object value) {
        if (value instanceof Envelope(var id, var payload, var owner)
                && payload instanceof Point p) {
            return id + " has point x=" + p.x();
        }
        return "not point";
    }

    public static void main(String[] args) {
        Object a = new Envelope("E1", new Point(2, 3), new Owner("Lan"));
        Object b = new Envelope("E2", "hello", new Owner("Minh"));
        Object c = new Envelope("E3", new Point(9, 9), null);
        Object d = new Envelope(null, null, new Owner(null));
        Object e = "test";
        for (Object v : new Object[]{a, b, c, d, e, null}) {
            System.out.println(describe(v));
        }
        System.out.println(inspectPayload(a));
        System.out.println(inspectPayload(b));
        System.out.println("null id type: "
                + (d instanceof Envelope(String id, var payload, var owner)));
        System.out.println("null payload String: "
                + (d instanceof Envelope(var id, String text, var owner)));
        System.out.println("null owner record: "
                + (c instanceof Envelope(var id, var payload, Owner(var name))));
        Object f = new Envelope("E4", new Point(0, 0), new Owner(null));
        System.out.println("null name type: "
                + (f instanceof Envelope(String id, Point(var x, var y), Owner(String name))));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 PatternCompositionDemo.java
java PatternCompositionDemo
```

**Exact output:**

```text
E1 point=(2,3), owner=Lan
E2 text=hello, owner=Minh
Other envelope: E3
Other envelope: null
Not an envelope
input=null
E1 has point x=2
not point
null id type: true
null payload String: false
null owner record: false
null name type: true
```

Explanation in order:

1. `E1` contains a non-`null` `Point` and `Owner`, so it matches the nested record patterns branch, extracting `x=2`, `y=3`, and `name="Lan"`.
2. `E2` contains a non-blank `String` payload, so it matches the `String text` branch and the `!text.isBlank()` guard.
3. `E3` contains a `Point` but `owner == null`, so the `Owner(String name)` pattern fails; the broader `Envelope(var id, var payload, var owner)` case catches it.
4. `d` is an `Envelope` with `id == null` and `payload == null`; it still matches `Envelope(var ...)`, and string concatenation produces `Other envelope: null`.
5. The `String` object goes to `default`; the `null` selector goes to `case null`.
6. The `inspectPayload` method deconstructs `Envelope` using `var`, then uses the type pattern `Point p` to inspect `payload` separately. It succeeds for `E1` and fails for `E2`.
7. The last four lines test `null` at component positions: the type pattern `String id` applied to a component declared as `String` can accept `null`; `String text` applied to `Object` does not accept `null`; the record pattern `Owner(...)` does not accept a `null` record; however, the component type pattern `String name` inside `Owner` accepts a `null` name value.

The program was compiled with `javac --release 21` and executed to verify the output.

## 10. Common mistakes when combining patterns

1. **Equating type patterns with record patterns.** `Point p` keeps a whole `Point` object; `Point(int x, int y)` deconstructs the two components. Choose the intended behavior before writing.
2. **Placing a pattern at the wrong position in a record.** For `Envelope(String id, Object payload, Owner owner)`, the pattern in the second position checks `payload`, not `owner`. Variable names do not change the declaration order.
3. **Wrong number of component patterns.** `Envelope` has three components; the record pattern `Envelope(...)` must provide all three component patterns according to Java 21 syntax.
4. **Seeing `Object` and manually casting before matching.** Use `Point p` or `String text` to check `payload` before reading specialized data; avoid casts that could cause a `ClassCastException`.
5. **Assuming type patterns reject `null` in every position.** `String id` on a component declared as `String` can accept `null`, whereas `String text` on an `Object` component requires a non-`null` `String` value.
6. **Assuming a nested record pattern accepts a `null` nested record.** `Owner(String name)` does not match if `owner == null`; to preserve a potentially `null` value, use `var owner` and check it when needed.
7. **Using a pattern variable outside its guaranteed match scope.** Variable scope in `if`, `&&`, and `switch` depends on control flow; let the compiler verify where variables can be used.
8. **Putting a broad case before a specific case.** `Envelope(var id, var payload, var owner)` can dominate subsequent branches that check `Point` or `String`.
9. **Confusing a `var` variable with a dynamic object.** The type of `var` is inferred at compile time from the record; `var payload` has type `Object` and does not automatically become `Point` even if the runtime value is a `Point`.
10. **Confusing record patterns with object creation syntax.** `new Envelope(...)` creates a record; `Envelope(...)` inside `instanceof`/`case` is syntax for checking and deconstructing data.

## 11. Self-check

**Question 1.** Given `Object o = new Envelope("A", new Point(7, 8), new Owner("Ha"));`, does the pattern `Envelope(String id, Point p, Owner(String name))` match? What is the variable `p`?

*Answer:* Yes; `p` is **the entire `Point(7, 8)` record**, so you can call `p.x()` to get `7`. If you want coordinate variables directly, use `Point(int x, int y)`.

**Question 2.** Given `new Envelope("B", "abc", new Owner("Ha"))`, does the pattern `Envelope(var id, Point p, var owner)` match?

*Answer:* No. The component type pattern `Point p` is applied to a payload whose runtime type is `String`, so it does not match.

**Question 3.** In `Envelope(String id, Point(var x, var y), Owner(var name))`, what are the static types of `x`, `y`, and `name`?

*Answer:* `int`, `int`, and `String`. `var` takes its type from the component declarations of the `Point` and `Owner` records.

**Question 4.** Why must `case Envelope(var id, var payload, var owner)` come after the cases that classify `Point` and `String`?

*Answer:* It is a record pattern broad enough to match every non-`null` `Envelope`. If placed earlier, it dominates the specialized cases that follow.

**Official documentation:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).