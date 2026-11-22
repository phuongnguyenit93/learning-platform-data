# Java 21 and Finalized Pattern Matching

## 1. What Does “Finalized” Mean?

**Java 21 is a major milestone for pattern matching in Java:** two features exited *preview* status and became standard features—**record patterns (JEP 440)** and **pattern matching for `switch` (JEP 441)**. Together with **pattern matching for `instanceof`** (standard since Java 16), **records** (standard since Java 16), and **sealed classes/interfaces** (standard since Java 17), Java 21 lets you model data and classify many kinds of objects with a consistent syntax.

Conceptual example:

```java
sealed interface Request permits Parcel, Cancellation {}
record Parcel(String code, int weight) implements Request {}
record Cancellation(String reason) implements Request {}
```

Starting in Java 21, you can use patterns in `switch`:

```java
static String label(Request request) {
    return switch (request) {
        case Parcel(String code, int weight) when weight >= 10 ->
                "Hàng nặng: " + code;
        case Parcel(String code, int weight) ->
                "Hàng thường: " + code;
        case Cancellation(String reason) ->
                "Hủy: " + reason;
        case Cancellation ignored ->
                "Hủy thiếu lý do";
        case null -> "Chưa có yêu cầu";
    };
}
```

The snippets above are **declarative illustrations** that can be placed in the same type context; Section 9 provides a complete program. Note that `Cancellation(String reason)` does not match when the `reason` component is `null`, so the trailing `Cancellation ignored` case serves as a fallback.

When saying **“pattern matching is finalized in Java 21”**, you need to understand this accurately:

- Specifically, **record patterns** and **pattern matching for `switch`** have been standardized and can be used in production code on JDK 21 **without `--enable-preview`**.
- That **does not mean every future pattern-matching idea is already present in Java 21**. For example, **unnamed patterns and variables** using `_` are only a *preview* feature in Java 21 (JEP 443), not part of the default standard syntax.
- “Standard” also does not guarantee that code is always business-correct, always `null`-free, or automatically faster than older idioms. The compiler checks type and flow rules; business logic still requires design and testing.

## 2. Compatibility Timeline

| Java Version | Key Milestone | Meaning for Developers |
| --- | --- | --- |
| Java 14–15 | Pattern matching for `instanceof` in preview | Can be tried when preview is enabled; should not be mistaken for standard syntax in those versions. |
| **Java 16** | `instanceof` type patterns finalized (JEP 394); records finalized (JEP 395) | Write `obj instanceof String text` and define `record` without preview. |
| **Java 17** | Sealed classes/interfaces finalized (JEP 409); pattern matching for `switch` enters preview (JEP 406) | Can model closed hierarchies; `switch` pattern matching must not yet be treated as a standard feature. |
| Java 19–20 | Record patterns tested via preview (JEP 405, JEP 432); pattern matching for `switch` continues in preview | Syntax and several rules were still being refined before the final release. |
| **Java 21** | **Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) finalized** | Use type/record patterns in `switch`, `when` guards, and nested deconstruction with standard syntax, without preview. |
| Java 21 | Unnamed patterns and variables remain in preview (JEP 443) | Do not write `_` as an unnamed pattern when only standard Java 21 features are allowed. |

**Important note:** `record`, `sealed`, and type patterns in `instanceof` are not synonymous with “record patterns” in `switch`. They are distinct evolutionary steps; when checking compatibility, you must examine **each syntactic construct actually used**, not merely whether the project has records.

For example:

```java
// Java 16+:
if (obj instanceof String text) {
    System.out.println(text.length());
}

// Java 21+ (standard):
if (obj instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

The second snippet requires `Point` to be a record with two `int` components. Java 17 does not understand the record pattern `Point(int x, int y)` under its standard language version, even though Java 17 already supports record declarations.

## 3. Type Patterns in instanceof: A Stable Foundation

Before pattern matching for `instanceof` became a standard feature:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.toUpperCase());
}
```

After using a type pattern:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

The new syntax combines the type test and binding a variable of type `String`. When `value` is not a `String` or is `null`, the pattern does not match and the `if` body does not execute.

**The compiler manages scope by flow (flow scoping):**

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.length());
}
```

The right-hand side of `&&` is only evaluated when the left-hand side is true, so `text` is definitely bound. Conversely:

```java
// DOES NOT COMPILE: the right-hand side of || runs when the pattern on the left is false.
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

In a **guard clause** whose non-matching branch exits early, the pattern variable can be used in the remainder of the block:

```java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Cần String");
    }
    return text;
}
```

You cannot use a pattern variable in the `else` branch of a positive test, on paths where the pattern might be false, or outside the scope where the compiler has proven a match. This is an important mechanism that remains unchanged when patterns are brought into `switch` and record patterns.

## 4. Record Patterns: Type-Checked Data Deconstruction

A record declares its component structure:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

In Java 21, you can use a record pattern directly:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

And use a **nested record pattern**:

```java
if (value instanceof Segment(
        Point(int x1, int y1),
        Point(int x2, int y2))) {
    System.out.println(x2 - x1);
}
```

In principle, the compiler matches the pattern against the record structure: the number of components and the pattern type at each position must match. The variables `x1`, `y1`, `x2`, and `y2` are only in scope where the nested pattern has matched.

You can use `var` for **component type inference**:

```java
if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Here `x` and `y` have type `int` according to the record declaration, not an unknown `Object`.

### Record patterns and null

Three cases must be distinguished:

1. **The selector is `null`:** it does not match a record pattern such as `Point(int x, int y)`.
2. **A nested record is `null`:** `Segment(Point(...), Point(...))` does not match when `start` or `end` is `null`.
3. **A component bound with `var` is null:** for reference components, `var` can receive `null`; you must check it yourself before calling methods on the variable.

Example:

```java
record Note(String message) {}

static String noteText(Object input) {
    if (input instanceof Note(var message)
            && message != null
            && !message.isBlank()) {
        return message;
    }
    return "Thiếu thông điệp";
}
```

Using `var message` allows the null-component case to be handled with an explicit condition. If you use `Note(String message)`, the nested type pattern `String message` does not match a null component; do not confuse these two behaviors.

### Record patterns do not construct data

A record pattern **reads components through the record's accessors** to match the pattern; it does not create a new record and does not perform constructor validation on behalf of the application. Custom accessors can be expensive or throw exceptions; if an accessor throws an exception during record pattern matching, you should understand Java 21's `MatchException` mechanism. Do not infer from the shorter syntax that a pattern has zero cost or cannot fail.

## 5. Pattern Matching for switch: case, when, and Results

Java 21 allows using **type patterns** and **record patterns** in `case`:

```java
static String classify(Object input) {
    return switch (input) {
        case Integer number when number > 0 ->
                "Số dương: " + number;
        case Integer number ->
                "Số nguyên không dương: " + number;
        case String text when !text.isBlank() ->
                "Chuỗi: " + text;
        case String ignored ->
                "Chuỗi trống";
        case null ->
                "Không có dữ liệu";
        default ->
                "Loại khác";
    };
}
```

This is a complete Java 21 method when placed inside a class. Key points to remember:

- `switch` evaluates branches **in order**; the first branch whose pattern and guard both match is selected.
- The `when` guard is evaluated **after the pattern matches**; therefore `number` or `text` already has a definite type inside the guard.
- If the guard returns `false`, Java continues evaluating subsequent branches.
- An unguarded branch such as `case Integer number` must be **placed after** guarded branches of the same type; otherwise it can make the later branch **dominated**.
- `->` is switch rule syntax, with no fall-through mechanism like the old colon label groups.
- `return switch (...) { ... };` is a **switch expression** and must yield a value or end with `throw` on every path.

### Using blocks and yield when multiple statements are needed

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> {
            String normalized = text.strip();
            yield normalized.isEmpty()
                    ? "Chuỗi rỗng"
                    : "Nội dung: " + normalized;
        }
        case null -> "Không có chuỗi";
        default -> "Không phải chuỗi";
    };
}
```

In a `switch expression`, a case block requires `yield` to supply the value for the expression. Do not confuse `yield` with `break` or `return`; each keyword has its own control-flow rules.

### Guards when the pattern does not match

If the selector is a `Double` and the case being tested is `case Integer number when number > 0`, the `Integer` pattern does not match, so the guard `number > 0` is not evaluated. If the selector is `Integer(-2)`, the pattern matches but the guard is false, so the subsequent unguarded `Integer` case is selected.

The difference between **pattern mismatch** and **guard false** is very important in unit tests, because both cause a case to be skipped but can lead to different branches.

## 6. Sealed Interfaces and Exhaustiveness: The Benefit of Closed Types

A `sealed interface` lets the compiler know which **direct subtypes are permitted**:

```java
sealed interface Outcome permits Accepted, Refused, Waiting {}
record Accepted(String id) implements Outcome {}
record Refused(String reason) implements Outcome {}
record Waiting(int seconds) implements Outcome {}
```

In Java 21:

```java
static String status(Outcome outcome) {
    return switch (outcome) {
        case Accepted(String id) -> "Đã nhận: " + id;
        case Refused(String reason) -> "Từ chối: " + reason;
        case Refused refused -> "Từ chối không có lý do";
        case Waiting(int seconds) -> "Chờ: " + seconds;
        case null -> "Chưa có trạng thái";
    };
}
```

The `switch expression` can be verified by the compiler as **exhaustive**: every non-null `Outcome` object must belong to one of the permitted subtypes `Accepted`, `Refused`, or `Waiting` (records are all final), and `case null` handles a null selector separately. **No `default` is needed**.

If a new subtype, such as `TimedOut`, is added to the `permits` list, `switch` statements/expressions relying on the old set of types may require adding a case upon recompilation. This is a major advantage for catching unhandled policies.

**However, note one detail:** `Accepted(String id)` does not match if `id == null`, and the code above **has no fallback `case Accepted accepted`**. Thus, the illustrative `status` snippet is incomplete for an `Accepted` with a `null` component. To be accurate and exhaustive, you should use one of two approaches:

```java
// Approach 1: var for a potentially null component.
case Accepted(var id) -> "Đã nhận: " + id;

// Approach 2: add a catch-all subtype case after the specific pattern.
case Accepted(String id) -> "Đã nhận: " + id;
case Accepted accepted -> "Đã nhận nhưng thiếu id";
```

The snippets above are **illustrative branches for fixing the code**, not a program putting both options into the same `switch`. The `Refused` case already has the fallback `Refused refused` branch. When writing a `switch` over a sealed hierarchy, exhaustiveness is based on types and Java's language rules; if a component type pattern might fail to match due to null, ensure that data is handled according to the business contract.

**Technical note:** In Java 21, the compiler's recognition of a record pattern as covering the record type has specific rules regarding pattern *unconditionality*; you should not treat having a record pattern with a reference type pattern as automatic proof that components are never null. When you need to express a null policy explicitly in the domain, use `var`, a broader type-pattern branch, or validation in the constructor.

### Do not mask missing cases with default

For a closed domain, this snippet:

```java
// Less safe for detecting new subtypes:
return switch (outcome) {
    case Accepted accepted -> "OK";
    default -> "OTHER";
};
```

easily hides the fact that `Refused` and `Waiting` need their own rules. `default` can make sense for open inputs like `Object` or a plugin interface, but in a closed domain it weakens one of the key benefits of exhaustiveness.

**Do not equate null with default:** with pattern matching for `switch`, `null` has its own rules; if you want to handle a null selector, use `case null` or check beforehand. Do not expect `default` to automatically turn null into an ordinary result.

## 7. Differences Between Java 17 and Java 21 in a Project

If a project is running on JDK 17 and only uses standard features, the following constructs can be used:

```java
record Request(String id) {}
sealed interface Response permits Success, Failure {}
record Success(String value) implements Response {}
record Failure(String error) implements Response {}

static String requestId(Object value) {
    if (value instanceof Request request) {
        return request.id();
    }
    return "Không phải Request";
}
```

This is an illustrative code example using **records + sealed types + `instanceof` type patterns**. No `switch` pattern matching is required.

If you migrate the project to Java 21, you can move explicit type-classification logic to `switch`, reducing `if/else if` chains and taking advantage of exhaustiveness checking for closed subtypes:

```java
static String responseText(Response response) {
    return switch (response) {
        case Success(String value) ->
                "Thành công: " + value;
        case Success success ->
                "Thành công thiếu giá trị";
        case Failure(String error) ->
                "Thất bại: " + error;
        case Failure failure ->
                "Thất bại thiếu lý do";
        case null ->
                "Không có kết quả";
    };
}
```

When used on JDK 17, the Java 21 `responseText` example above will **not compile under the standard Java 17 language**. You cannot simply switch the runtime to 21 while keeping the compiler configured at `--release 17` and expect record patterns and `when` to be accepted.

**Upgrade to Java 21 only when it fits your system:** check your toolchain, CI, production environment, frameworks, libraries, build plugins, IDE, JVM distribution, and upgrade policy. Finalized pattern features do not force every Java 17 application to be rewritten immediately; refactoring should demonstrate clearer code and tests proving behavior is preserved.

## 8. Common Syntax Mistakes When Migrating from Preview to Java 21

### 8.1. Old-style `&&` guards in case labels

Some older preview documentation used a different guarded-pattern syntax than the finalized syntax. In Java 21, write guards using **`when`**:

```java
// Java 21:
case String text when !text.isBlank() -> "Có chữ";

// Old preview syntax, do not use as a standard Java 21 case:
// case String text && !text.isBlank() -> "Có chữ";
```

The code in the fence illustrates case labels; it is not a standalone Java method. With `instanceof`, `&&` **remains completely valid** for chaining conditions:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

Therefore, do not mistakenly change all `&&` to `when`: `when` is guard syntax in a `switch` `case`, whereas `&&` is the boolean operator.

### 8.2. Confusing record patterns with constructors

`case Parcel(String code, Address(String city), int weight)` **does not create a new `Parcel`**. It is a pattern that tests an existing `Parcel` object and extracts component data via accessors. The constructor `new Parcel(...)` is for creating data; a record pattern is for matching/deconstructing data.

### 8.3. Placing a general case before a specific case

```java
// DOES NOT COMPILE: case String is dominated by the preceding case Object.
// return switch (value) {
//     case Object anything -> "Một object";
//     case String text -> "Chuỗi: " + text;
//     case null -> "null";
// };
```

`case Object anything` is a general pattern for non-null objects, so the subsequent `case String text` is dominated. Place specific/guarded branches before broader ones.

### 8.4. Not accounting for null components

`record Note(String content)` can still be created with `content == null` if the constructor does not forbid it. `Note(String text)` has a nested `String` type pattern, which does not match when `content` is null. `Note(var text)` can bind a null content. When you need to call `text.length()`, check `text != null` first.

### 8.5. Assuming `_` is always available as an unnamed pattern

In Java 21, the ability to use `_` as an unnamed variable/pattern belongs to **preview JEP 443**. If production code requires using only standard features, use a meaningful variable name (such as `ignored`) or another structure instead of assuming `case Parcel(_, _, _)` is default Java 21 syntax.

### 8.6. Skipping tests because the compiler checks exhaustiveness

The compiler checks types, dominance, and exhaustiveness according to the language rules; it does not know constraints like “weight must be positive”, “code must not be blank”, or “city must be supported”. You must test true/false guards, fallback branches, null, boundary data, and new types if the domain changes.

## 9. Complete Runnable Java 21 Program

Create the file **`Java21PatternMatchingFinalDemo.java`**:

```java
import java.util.Locale;

public class Java21PatternMatchingFinalDemo {
    sealed interface Request permits Parcel, Cancellation, Delay {}

    record Address(String city) {}

    record Parcel(String code, Address destination, int weight)
            implements Request {}

    record Cancellation(String reason) implements Request {}

    record Delay(int minutes) implements Request {}

    static String inspect(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.strip().toUpperCase(Locale.ROOT);
        }
        return "Không phải chuỗi có nội dung";
    }

    static String describe(Request request) {
        return switch (request) {
            case Parcel(String code, Address(String city), int weight)
                    when weight >= 10 && "Hà Nội".equals(city) ->
                    "Hàng nặng " + code + " đến " + city;

            case Parcel(String code, Address(String city), int weight) ->
                    "Gửi " + code + " đến " + city;

            case Parcel ignored ->
                    "Thiếu cấu trúc địa chỉ";

            case Cancellation(String reason)
                    when !reason.isBlank() ->
                    "Đã hủy: " + reason;

            case Cancellation ignored ->
                    "Hủy thiếu lý do";

            case Delay(int minutes) when minutes > 0 ->
                    "Hoãn " + minutes + " phút";

            case Delay ignored ->
                    "Thời gian hoãn không hợp lệ";

            case null ->
                    "Không có yêu cầu";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect("  java  "));
        System.out.println(inspect(42));

        System.out.println(describe(
                new Parcel("P1", new Address("Hà Nội"), 12)));
        System.out.println(describe(
                new Parcel("P2", new Address("Đà Nẵng"), 5)));
        System.out.println(describe(
                new Parcel("P3", null, 2)));
        System.out.println(describe(
                new Parcel("P4", new Address(null), 2)));

        System.out.println(describe(new Cancellation("Hết hàng")));
        System.out.println(describe(new Cancellation(null)));
        System.out.println(describe(new Delay(3)));
        System.out.println(describe(new Delay(0)));
        System.out.println(describe(null));
    }
}
```

Compile with **JDK 21 or newer** and run:

```bash
javac -encoding UTF-8 Java21PatternMatchingFinalDemo.java
java Java21PatternMatchingFinalDemo
```

Expected output:

```text
JAVA
Không phải chuỗi có nội dung
Hàng nặng P1 đến Hà Nội
Gửi P2 đến Đà Nẵng
Thiếu cấu trúc địa chỉ
Thiếu cấu trúc địa chỉ
Đã hủy: Hết hàng
Hủy thiếu lý do
Hoãn 3 phút
Thời gian hoãn không hợp lệ
Không có yêu cầu
```

### Output Explanation

1. `inspect("  java  ")` matches the type pattern `String text`, passes `!text.isBlank()`, trims whitespace with `strip()`, and converts to `JAVA`.
2. `inspect(42)` receives an `Integer`, does not match `String`, and returns the fallback result.
3. `Parcel("P1", Address("Hà Nội"), 12)` matches the nested record pattern, and both the `weight >= 10` guard and city `Hà Nội` are true, so the heavy-parcel branch is selected.
4. `Parcel("P2", Address("Đà Nẵng"), 5)` matches the record pattern, but the first guard is false; the next `Parcel(...)` branch returns `Gửi P2 đến Đà Nẵng`.
5. `Parcel("P3", null, 2)` does not match the nested `Address(String city)` because `destination == null`, so `case Parcel ignored` is selected.
6. `Parcel("P4", Address(null), 2)` has an `Address`, but its `city == null` component causes the `String city` type pattern to fail to match; `case Parcel ignored` is also selected.
7. `Cancellation("Hết hàng")` matches the pattern and `!reason.isBlank()`; `Cancellation(null)` does not match the `String reason` type pattern, so it goes to `case Cancellation ignored`.
8. `Delay(3)` satisfies the `minutes > 0` guard; `Delay(0)` fails the guard and goes to `case Delay ignored`.
9. `null` is handled separately by `case null`.

In this example, the subtypes `Parcel`, `Cancellation`, and `Delay` are directly permitted final records, so their corresponding unguarded cases allow the `switch expression` to handle every non-null `Request` value. No `default` is needed.

### Checking the Actual Version

In the terminal, you can check which JDK is active:

```bash
java -version
javac -version
```

If `javac` is version 17, this program using Java 21 record patterns and switch patterns cannot be compiled with standard Java 17 syntax. With JDK 21, you can verify the target language level:

```bash
javac --release 21 -encoding UTF-8 Java21PatternMatchingFinalDemo.java
```

The `--release 21` flag requires a compiler toolchain that supports release 21; it does **not** turn an older `javac` into a Java 21 compiler. In addition, an artifact compiled for Java 21 cannot run by default on a Java 17 runtime.

## 10. Type Inference, Generics, and Known Limitations

Record patterns are not limited to non-generic records. Java 21 can **infer type arguments of a generic record pattern** from the static type context when enough information is available:

```java
record Box<T>(T item) {}

static void printBox(Box<String> box) {
    if (box instanceof Box(var item)) {
        System.out.println(item.toUpperCase());
    }
}
```

This is an illustrative snippet placed in a class that has the `Box` record. The compiler infers the type of `item` from the component of `Box<String>`. You should not interpret `var` as disabling type checking.

However, **type erasure still exists**: testing a runtime object does not prove an arbitrary generic argument such as `T == String` solely by an erased type test. When the input has type `Object`, you can check the actual component with a nested pattern:

```java
static String readStringBox(Object input) {
    if (input instanceof Box(var item)
            && item instanceof String text) {
        return text;
    }
    return "Không phải Box chứa String";
}
```

This pattern checks that the actual component value is a `String` before using it. When working with generics, you must consider compile-time types, runtime types, unchecked casts, `null`, and record structure. Pattern matching does not eliminate the limitations of generics on the JVM.

## 11. Upgrading from Java 17 or Preview Versions

A controlled upgrade plan:

1. **Verify JDK/`javac` and `--release`/`sourceCompatibility`:** running on a Java 21 runtime does not mean all modules are compiling with source 21.
2. **Identify old preview syntax:** convert old-style guarded cases to Java 21 `when`, and review dominance, null, and exhaustiveness rules; do not copy preview code verbatim without recompiling.
3. **Preserve existing data contracts:** adding record patterns does not automatically validate null or negative values; keep validation at constructors/boundaries.
4. **Focus on places with repeated subtype classification:** use `switch` on sealed hierarchies where it clarifies branches, but do not replace every polymorphic method with `switch`.
5. **Check exception behavior:** refactoring from manual accessors to record patterns can affect exception wrapping; test custom accessors if any exist.
6. **Test boundary values and fallback cases:** `when` true/false, null selectors, null nested components, new subtypes, and case ordering.
7. **Compile and run in CI on the finalized toolchain:** verify your IDE, formatter, linter, test runner, plugins, container images, and deployment environment.
8. **Do not enable preview accidentally:** this lesson uses standard Java 21 features; `--enable-preview` should only be enabled when a project intentionally uses a preview JEP and accepts its compatibility policy.

You do not need to immediately convert every `if (x instanceof T) { ... }` to `switch`. With only one or two simple branches, `if` can be easier to read. The clearest advantages of `switch` appear with **closed subtype sets**, **multiple handling branches**, or **the need for compiler-checked exhaustiveness**.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong or Misleading | How to Fix |
| --- | --- | --- |
| Using record patterns in code targeting Java 17 | This feature became standard in Java 21. | Upgrade source/target/toolchain appropriately or use Java 17 type patterns. |
| Using `case Type t && condition` from old preview docs | Java 21 guard syntax uses `when`. | Change to `case Type t when condition -> ...`. |
| Using a pattern variable outside its flow scope | The compiler cannot prove the pattern matched. | Use it in the true branch, after an appropriate `&&`, or after an early-exit guard clause. |
| Placing `case Object obj` before `case String s` | The later branch is dominated. | Place specific cases first. |
| Assuming `default` always handles a null selector | Pattern `switch` handles null separately. | Use `case null` or an explicit null check. |
| Assuming nested record patterns accept any null component | Nested type patterns may not match null. | Use `var` with validation or a fallback subtype case. |
| Using `when` only for positive values with no remaining case | A false guard leaves that type unhandled. | Add an unguarded case for the same subtype or a catch-all branch. |
| Adding `default -> "OK"` to a sealed hierarchy | Can hide missing branches when the domain gains a new type. | List variants explicitly and let the compiler check exhaustiveness. |
| Using `_` as standard Java 21 syntax | Unnamed patterns/variables are only preview in Java 21. | Use named variables in code without preview enabled. |
| Thinking pattern matching is automatically faster than every call | Type checks, accessors, guards, and JVM optimizations still apply. | Measure actual performance and optimize when there is a bottleneck. |

## 13. Self-Check

Given:

```java
sealed interface Message permits Text, NumberMessage {}
record Text(String value) implements Message {}
record NumberMessage(int value) implements Message {}
```

**Question 1:** Why does the following snippet require Java 21 to be standard syntax?

```java
return switch (message) {
    case Text(String value) -> "Text: " + value;
    case Text text -> "Text thiếu dữ liệu";
    case NumberMessage(int value) -> "Number: " + value;
    case null -> "Không có message";
};
```

**Answer:** Because it uses **record patterns inside `case` of a pattern-matching `switch`**, two features that became standard in Java 21. Plain `record` and `sealed` declarations could already be written in older Java versions.

**Question 2:** If `new Text(null)` is passed into the `switch`, which branch matches?

**Answer:** `case Text(String value)` does not match because the nested `String` pattern does not match null; the subsequent `case Text text` branch handles it. Omitting this branch without another null policy can easily leave data with missing components unhandled as intended.

**Question 3:** If a new subtype `Image` is added to `permits Message` without updating the `switch`, what should be checked?

**Answer:** Upon recompilation, a `switch expression` without `default` can be reported as non-exhaustive if a case for the new subtype is missing. Meaningful handling should be added, rather than unconditionally adding `default` and losing the compiler signal.

**Question 4:** Should `--enable-preview` be used to run the main Java 21 example in this lesson?

**Answer:** No. Type patterns for `instanceof`, record patterns, and pattern matching for `switch` are already standard features in Java 21. Preview only applies to other JEPs that are not yet finalized in that release.

## 14. Background References

- **JEP 394 – Pattern Matching for `instanceof`:** https://openjdk.org/jeps/394
- **JEP 395 – Records:** https://openjdk.org/jeps/395
- **JEP 409 – Sealed Classes:** https://openjdk.org/jeps/409
- **JEP 440 – Record Patterns:** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for `switch`:** https://openjdk.org/jeps/441
- **JEP 443 – Unnamed Patterns and Variables (Preview in Java 21):** https://openjdk.org/jeps/443
- **Java Language Specification 21, Patterns (`14.30`):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **Java 21 Language Guide – Pattern Matching for `switch`:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html

**Conclusion:** Java 21 marks the stage where **record patterns** and **pattern matching for `switch`** become standard features. Combined with Java 16's type patterns, Java 16's records, and Java 17's sealed types, they form a powerful toolkit for representing and classifying data structures. To use them properly, you must understand **language versions, type/record patterns, flow scope, `when`, null, dominance, and exhaustiveness**; when upgrading a project, do not confuse standard features with preview features, and always verify logic with both the compiler and real tests.
