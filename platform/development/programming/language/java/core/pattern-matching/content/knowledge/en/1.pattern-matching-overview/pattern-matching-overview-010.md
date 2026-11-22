# Pattern Matching Learning Roadmap in Java

## 1. What Problem Does It Solve?

In Java, many pieces of code must check an object's type before extracting its data for processing. Previously, developers often used `instanceof`, manual casting, `if/else` chains, or `switch` statements that only checked constants. **Pattern matching** lets you directly express "does a value match a pattern; if it matches, which variables should be extracted?". As a result, type-based control flow becomes clearer and repetitive casts are reduced.

For example, `if (value instanceof String text)` both checks whether `value` is a `String` and declares the variable `text` already typed as `String` for the matching branch. With Java 21, you can also use type patterns in `switch` and deconstruct `record` components using **record patterns**.

This article is a **learning map**: what order to learn in, what you must know at each stage, what exercises to practice, and what criteria to use to know you are ready to move on. The subsequent in-depth articles will fully explain each mechanism.

**Destination:** You can read, write, and test code using `instanceof` patterns, pattern matching for `switch`, and record patterns, and know when to combine them with `record`/`sealed`. You must also recognize variable scope, shadowed branches, `null` cases, and version compatibility limits.

## 2. Choosing a JDK and Prerequisite Knowledge

| Learning Milestone | Java Version | Status |
| --- | --- | --- |
| Type pattern in `instanceof` | Java 16 and later | Standard feature since Java 16; usable on Java 17 |
| `record` (data type) | Java 16 and later | Standard feature; foundation for learning record patterns |
| `sealed` class/interface | Java 17 and later | Standard feature; useful for `switch` covering all subtypes |
| Type pattern, guard, and `case null` in `switch` | Java 21 and later | Pattern matching for `switch` is standard since Java 21 |
| Record patterns and nested record patterns | Java 21 and later | Standard since Java 21 |

You should use **JDK 21 or later** when following the full roadmap. If your project is on Java 17, learn and apply the `instanceof` part first; **do not copy Java 21 `switch` pattern/record pattern syntax into code compiled with `--release 17`**. Java 21 can run all the stable examples below without `--enable-preview`. Some pattern matching enhancements in other Java versions may still be in preview; check the documentation for your exact JDK version and treat them as extensions, not prerequisites to complete this roadmap.

Before starting, you should understand: reference types and polymorphism; `Object`, inheritance, and interfaces; `instanceof` and casting; `if/else` and `&&`/`||`; `switch` expressions; and the meaning of `null`. Then learn the basics of `record` and `sealed` constructs. You do not need to learn reflection or regular expressions first: pattern matching here is **not** regex and does not automatically inspect arbitrary object structures.

Check your environment:

```bash
java -version
javac -version
```

Both commands must point to the JDK appropriate for the part you are about to learn. When compiling with a newer JDK for a target version, use `javac --release 17` or `javac --release 21` to proactively verify compatibility.

## 3. Learning Order from Basics to Application

| Stage | Focus | Practice Exercise and Completion Sign |
| --- | --- | --- |
| 0. Identifying the problem | Comparing type check + manual cast with pattern matching; reviewing `switch` expressions and `null` | Point out redundant casts in code and explain why type checking is needed |
| 1. Type pattern in `instanceof` | `instanceof String text`; matching condition; variable bound when the pattern matches | Write a method taking `Object`, handling `String` and `Integer` without manual casting |
| 2. Control-flow variable scope | Flow scoping; `&&`; negation + early return; uncertain branches | Explain why a pattern variable is or is not in scope on each line |
| 3. Pattern matching in `switch` | `case String s`, `case null`, `when`, `default`, case ordering, dominance | Convert a type-classifying `if/else` chain into a valid `switch` on Java 21 |
| 4. Record patterns | Deconstructing `record` components, nested patterns, and differences from accessor calls | Extract coordinates or nested data without declaring manual temporary variables |
| 5. Sealed + exhaustiveness checking | Permitted subtype set, exhaustiveness, guarded branches, and remaining branches | Write a `switch` expression for a closed type model without an arbitrary `default` |
| 6. Design and testing | Choosing the right construct, handling `null`, edge cases, reading compiler errors | Complete the synthesis exercise, test valid/error branches, and explain design choices |

The stages have a dependency order: **type checking → variable scope → multi-pattern branching → data deconstruction → subtype coverage → application design**. Do not start with nested record patterns if you are still confused about when an `instanceof` pattern variable is in scope.

### Stage 0 — See the Problem Before Learning the Syntax

Read this old code snippet:

```java
Object value = "Java";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Here `instanceof` has already confirmed the type, yet the developer still has to cast it again. Guiding question: what would change if the compiler immediately provided a variable of the right type once the pattern matched? The answer leads to Stage 1; the exercise is to identify the steps **check → cast → use**.

### Stage 1 — Learn `instanceof` Type Patterns First

The same idea above can be written as:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

The variable `text` simply represents the object that matched the `String` pattern; this is not a data conversion from one type to another. When `value` is `null`, the type pattern in `instanceof` does not match and the `if` body does not execute.

Standalone practice exercise, runnable with Java 17:

```java
public class PatternMatchingBasics {
    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Văn bản: " + text;
        }
        if (value instanceof Integer number) {
            return "Số nguyên: " + number;
        }
        return "Giá trị khác";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(21));
        System.out.println(describe(null));
    }
}
```

Save as `PatternMatchingBasics.java`, then run:

```bash
javac -encoding UTF-8 --release 17 PatternMatchingBasics.java
java PatternMatchingBasics
```

Expected output:

```text
Văn bản: Java
Số nguyên: 21
Giá trị khác
```

**Self-check:** If you change `"Java"` to `""`, why does the method return `"Giá trị khác"`? Because the variable `text` is only used in the branch when both `instanceof` **and** the condition `!text.isBlank()` are satisfied.

### Stage 2 — Master Flow Scoping to Avoid Compilation Errors

The scope of a pattern variable depends on **the control flow proving that the pattern matched**; it does not simply depend on a pair of curly braces.

```java
if (value instanceof String text && text.length() > 3) {
    System.out.println(text);
}
```

On the right-hand side of `&&`, `text` is already confirmed because the left-hand side must be true for the right-hand side to be evaluated. Conversely, the snippet below is **wrong and does not compile**:

```java
// WRONG: text may not have been created when the left-hand side is false.
if (value instanceof String text || text.isEmpty()) {
    System.out.println(value);
}
```

Another form to know is a negated check followed by an early return:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length()); // After if, text is definitely matched.
```

This snippet illustrates **the body of a method returning `void`**, with `value` as an already-declared variable. Draw the two control-flow branches yourself and show why the line after `if` can only run when `value` matches `String`. Do not try to use a pattern variable when the compiler has not proved that the pattern matched.

### Stage 3 — Expand from One Pattern to Multi-Pattern `switch` (Java 21)

When you need to handle multiple different types of the same value, `switch` lets each `case` attach a pattern:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String s when s.isBlank() -> "Chuỗi trống";
        case String s -> "Chuỗi: " + s;
        case Integer n -> "Số: " + n;
        default -> "Kiểu khác";
    };
}
```

This is an **illustrative method snippet** placed inside a class, requiring Java 21 or later. `when` is an additional condition (**guard**): it is only evaluated after the type pattern matches. The guarded `String` branch is placed before the general `String` branch so that special data is handled properly.

Three rules you must understand:

1. **Ordering and dominance:** A general case that covers all values of a more specific case after it will make the later case unreachable, and the compiler will report an error. For example, placing `case Object o` before `case String s` is invalid.
2. **`null` must be handled explicitly if it can occur:** A pattern `switch` on a `null` reference without a `null`-handling branch will throw `NullPointerException` in normal cases; `default` does not automatically replace `case null`.
3. **A `switch` expression must cover all possible cases:** For type `Object`, which can take many kinds of values, the example above uses `default`. For a closed set of subtypes using `sealed`, the compiler can verify exhaustiveness without `default`.

Exercise: write a method that classifies inputs `null`, empty string, normal string, integer, and an arbitrary object; add test cases for each branch. Intentionally swap the order of the two `String` cases and observe the dominance error message.

### Stage 4 — Learn Record Patterns to Deconstruct Structured Data (Java 21)

A `record` describes fixed data components; a **record pattern** lets you test and extract those components right at the matching site.

```java
record Point(int x, int y) {}

static String location(Object value) {
    if (value instanceof Point(int x, int y)) {
        return "(" + x + ", " + y + ")";
    }
    return "Không phải điểm";
}
```

The snippet above illustrates a `record` declaration and a method in the same class scope, requiring Java 21 or later. With `new Point(2, 5)`, the method returns `(2, 5)`. There is no need to do `Point p = (Point) value` and then call `p.x()` and `p.y()`.

Once you are comfortable with single-level patterns, move on to nested patterns:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}

// Inside a method, with variable Object value:
if (value instanceof Segment(Point(int x1, int y1), Point(int x2, int y2))) {
    System.out.println("Từ " + x1 + "," + y1 + " đến " + x2 + "," + y2);
}
```

This is **illustrative code to be placed inside an appropriate class/method**, not a complete program; if combined with the previous `Point` example, declare `Point` only once. Exercise: change the structure to `Order(Customer customer, Money amount)` (defining these types yourself), then deconstruct each component step by step; test `null` to see that type/record patterns do not match `null` by default.

Do not confuse record patterns with freely accessing any `private` field of an arbitrary class. This mechanism is based on **the component structure of a `record`** and Java's type rules.

### Stage 5 — Combine with `sealed` to Handle Closed Type Models

`sealed` restricts which direct subtypes are permitted to implement an interface or extend a class. When a `switch` covers all relevant subtypes, the compiler can prove **exhaustiveness**. This is why `sealed` is very useful for representing multiple cases of a data domain.

The following complete synthesis example uses Java 21, combining `record`, guards, `switch` expressions, and `case null`:

```java
public class PatternMatchingAdvanced {
    sealed interface Shape permits Circle, Rect {}

    record Circle(double radius) implements Shape {}
    record Rect(double width, double height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case null -> "Không có hình";
            case Circle(double r) when r <= 0 -> "Hình tròn không hợp lệ";
            case Circle(double r) -> "Hình tròn, bán kính=" + r;
            case Rect(double w, double h) when w <= 0 || h <= 0 ->
                    "Hình chữ nhật không hợp lệ";
            case Rect(double w, double h) ->
                    "Hình chữ nhật, kích thước=" + w + "x" + h;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(2)));
        System.out.println(describe(new Rect(3, 4)));
        System.out.println(describe(null));
    }
}
```

Save to `PatternMatchingAdvanced.java`:

```bash
javac -encoding UTF-8 --release 21 PatternMatchingAdvanced.java
java PatternMatchingAdvanced
```

Expected output:

```text
Hình tròn, bán kính=2.0
Hình chữ nhật, kích thước=3.0x4.0
Không có hình
```

Why is `default` not needed? Because `Shape` only permits `Circle` and `Rect`, the valid cases of each record have an **unguarded** branch to cover the remainder, and `null` is also handled. The two guards for invalid values are only priority branches; they are not sufficient on their own to cover the entire type. Try adding a `Triangle` subtype to `permits` without adding a `case`; the `switch` exhaustiveness error helps catch the missing handling.

In an open model, where subtypes can grow beyond control, `default` or another organization may be more appropriate. You should not turn every class hierarchy into `sealed` just to be able to write a `switch`.

### Stage 6 — Use Pattern Matching Intentionally

At this point, compare the options for the same problem:

| Situation | Consider Using |
| --- | --- |
| Only need to branch on one or two object types | `instanceof` pattern may be shorter and easier to read |
| Need to handle multiple data types of a single value | Pattern `switch`, paying attention to general cases and `null` |
| Data is already a `record` and components need to be extracted | Record pattern, including nested ones while still readable |
| Closed data domain with known variants | `sealed` combined with `switch` for exhaustiveness checking |
| Behavior belongs to the objects themselves and can be called via an interface | Consider **polymorphism**; you do not necessarily have to write a long `switch` everywhere |

Pattern matching is a way to express type checking and data deconstruction, not a replacement for object-oriented design principles. If the same type-based `switch` is repeated across multiple classes, ask yourself whether a polymorphic method would make responsibilities clearer. If a `record` structure is nested too deeply, naming intermediate variables or extracting helper methods may be easier to maintain.

## 4. Synthesis Exercises by Level

**Basic level (Java 17):** Write `format(Object input)` for `String`, `Integer`, `Double`, and other values, using `instanceof` patterns with no manual casting. Test `null`, blank strings, and negative numbers. Explain why the `instanceof` pattern does not match `null`.

**Intermediate level (Java 21):** Convert `format` into a `switch` expression. Distinguish blank strings using `when`, with `case null` and `default`. Intentionally place an overly general case above a specific one to observe the dominance error, then fix the order. Note which cases require `default`.

**Advanced level (Java 21):** Design a `sealed interface Payment permits Cash, Card, Transfer` where the variants are `record`s. Use record patterns to extract data, guards to validate positive amounts, and write a `switch` expression describing the transaction. Try adding a fourth payment type to see the effect of exhaustiveness; do not use real payment data and do not use this example to make real-world financial business decisions.

**Completion exercise:** For each exercise above, write a test case table including input, selected branch, and expected output; test negative/zero/positive boundaries (where applicable), `null`, unmatched types, and changes to the subtype set. Run with `--release` matching the target version. Evaluate whether the method remains clear after adding multiple cases.

## 5. Common Mistakes to Recognize Immediately

- **Using Java 21 syntax in a Java 17 project:** `switch` expressions existed before Java 21, but `case String s`, `when`, and record patterns as shown here require Java 21 or later to use as standard features.
- **Assuming a pattern variable is always in scope for the entire method:** Scope depends on paths that definitely make the pattern match; `||`, negation, and early returns must be analyzed separately.
- **Placing a general case before a specific case:** The later case may be dominated and fail to compile.
- **Assuming `default` includes `null`:** You need to understand the `null` rules of pattern `switch` and explicitly write `case null` when the input can be null.
- **Writing only guarded cases in a closed `switch`:** Guards can evaluate to false; an unguarded branch or valid catch-all is needed for the compiler to prove exhaustiveness.
- **Confusing record patterns with a mechanism to "unlock" any class:** Record patterns rely on record components; they are not reflection over private fields of arbitrary objects.
- **Overusing type-based branching:** For behavior tightly bound to object types, polymorphic design is sometimes easier to maintain than a series of duplicated `switch` statements.
- **Running examples with inconsistent configuration:** Check the `java`, `javac` versions and the `--release` flag; examples using standard Java 21 features do not need preview enabled.

## 6. Self-Assessment and Suggested Study Schedule

A reference study schedule that can be adjusted to your personal pace:

| Session | Content | Required Deliverable |
| --- | --- | --- |
| 1 | Foundations + `instanceof` patterns | `PatternMatchingBasics` program running properly |
| 2 | Flow scoping and intentional compilation errors | Ability to explain at least three control-flow paths of a pattern variable |
| 3 | `switch` patterns, guards, `null`, and dominance | Type classifier with clear tests for all cases |
| 4 | `record`, record patterns, nested patterns | An example deconstructing a record without manual casting |
| 5 | `sealed`, exhaustiveness, synthesis exercise | `PatternMatchingAdvanced` and a version with an added subtype |
| 6 | Refactoring and testing | Ability to decide when to use pattern matching vs. polymorphism |

**You are ready for more advanced study when you can answer on your own:**

1. How does pattern matching differ from traditional `instanceof` + casting?
2. Why is `text` valid on the right-hand side of `&&` in a condition, but not necessarily valid on the right-hand side of `||`?
3. When is a `case` dominated by an earlier case? How do guards affect branch selection?
4. How does a pattern `switch` handle `null`? Why is `default` not automatically equivalent to `case null`?
5. What information does a record pattern extract from a `record`, and what happens when the pattern does not match?
6. How does `sealed` help the compiler check `switch` exhaustiveness when the hierarchy changes?
7. Why would you choose `instanceof`, `switch`, record patterns, or polymorphism for a specific problem?

If you cannot explain any question yet, go back to the corresponding stage and modify an example yourself. You do not need to memorize every language rule before writing code: what matters is understanding **matching conditions, bound variables, safe scope, and missing cases**.

## 7. Official References for Further Learning

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): motivation, type patterns, and variable scope; standard since Java 16.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch, guards, null, dominance, and exhaustiveness; standard since Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstructing record components and nested patterns; standard since Java 21.
- [Oracle Java SE 21 Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): list of features and standard release versions.

Use documentation matching the **Java version your project actually compiles and runs on**. Extensions in newer JDK versions can be learned after you have mastered the standard features of Java 17/21.
