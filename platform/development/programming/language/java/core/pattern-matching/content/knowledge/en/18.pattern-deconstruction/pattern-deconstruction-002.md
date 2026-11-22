# Extracting multiple components instead of repeated accessor calls

## Objectives

When working with a `record` that has multiple components, especially a record containing other records, Java code often has to call multiple accessors such as `rect.origin().x()`, `rect.origin().y()`, and `rect.size().width()`. A **record pattern (deconstruction pattern)** lets you describe the structure to extract directly in the match and bind multiple components to variables at the same time.

After this lesson, you will know:
- Why repeated accessor chains make multi-level data processing code harder to read.
- How to use a `record pattern` to extract multiple components, including nested records.
- How to choose `if`/`instanceof` or `switch` to bring the extracted variables into the processing block.
- How to use `var` for type inference, and use `when` or `&&` to add conditions.
- Key distinctions to remember: record types, `null`, non-matching branches, `case` ordering, variable scope, and execution cost.

**Version:** Record patterns were standardized in **Java 21** (JEP 440). Starting from Java 21, pattern matching for `switch` (JEP 441) is also a standard feature. The examples use JDK 21 or later, without needing `--enable-preview`.

## 1. The problem: reading multiple components with accessors

Suppose we have three records describing a rectangle:

```java
record Point(int x, int y) {}
record Size(int width, int height) {}
record Rectangle(String id, Point origin, Size size) {}
```

To get the rectangle's ID, position, and dimensions, the traditional accessor approach is:

```java
// Assume rect, rect.origin(), and rect.size() are all non-null.
String id = rect.id();
int x = rect.origin().x();
int y = rect.origin().y();
int width = rect.size().width();
int height = rect.size().height();

System.out.println(id + " @ (" + x + ", " + y + ") - "
    + width + "x" + height);
```

This approach is **correct and appropriate** when only a few components are needed. However, when handling multiple levels, `rect.origin()` and `rect.size()` are repeated, making the data structure and branching conditions harder to follow.

One improvement in Java 17 is to store the intermediate records first:

```java
Point origin = rect.origin();
Size size = rect.size();

int x = origin.x();
int y = origin.y();
int width = size.width();
int height = size.height();
```

This reduces repeated accessor calls and is clear. Starting from Java 21, record patterns also allow **matching the entire shape and binding variables in a single pattern**, which is very useful when the code branches based on data.

## 2. Deconstruction: extracting multiple components in one pattern

With `Rectangle`, you can write:

```java
// Placed inside a method with an Object variable named value:
if (value instanceof Rectangle(
        String id,
        Point(int x, int y),
        Size(int width, int height))) {
    System.out.println(id + " @ (" + x + ", " + y + ") - "
        + width + "x" + height);
}
```

This pattern performs the following simultaneously:
1. Checks that `value` is a non-null `Rectangle`.
2. Binds the `id` component to the variable `id`.
3. Extracts the `origin` component and requires it to match `Point(int x, int y)`, thereby binding `x` and `y`.
4. Extracts the `size` component and requires it to match `Size(int width, int height)`, thereby binding `width` and `height`.
5. Executes the `if` body only when the entire structure matches.

That is a **nested record pattern**: the outer record pattern contains two inner record patterns. The code uses the bound values directly without calling `rect.origin().x()` or `rect.size().height()` inside the body.

Inside the record pattern, `String id`, `int x`, and `int width` are **type patterns** in component positions; `Point(...)` and `Size(...)` are nested **record patterns**. Thus, deconstruction combines type checking with structural extraction.

### Using var when types are already clear

If the compiler already knows the component types, you can write:

```java
if (value instanceof Rectangle(
        var id,
        Point(var x, var y),
        Size(var width, var height))) {
    // id: String; x/y/width/height: int
}
```

Here, `var` is a pattern with a **type inferred from the record component**, not a dynamic type. Use explicit type names when you want readers to clearly see type boundaries; use `var` when the nested structure is already expressive enough.

**What Java 21 does not support yet:** Record deconstruction must appear in a pattern-matching context such as `instanceof` or `switch`. Arbitrary destructuring assignment syntax like the following is **invalid**:

```java
// Intentionally invalid in Java 21:
var (x, y) = point;
```

When you only want to assign from a record whose type is already known for certain, calling accessors or creating intermediate variables remains completely reasonable.

## 3. Java 21 program: before and after using record patterns

Create the file **`DeconstructionComponentsDemo.java`**:

```java
public class DeconstructionComponentsDemo {
    record Point(int x, int y) {}

    record Size(int width, int height) {}

    record Rectangle(String id, Point origin, Size size) {}

    // Approach 1: read components using accessors.
    // Precondition: rect, origin, and size are non-null.
    static String usingAccessors(Rectangle rect) {
        int x = rect.origin().x();
        int y = rect.origin().y();
        int width = rect.size().width();
        int height = rect.size().height();

        return rect.id() + " origin=(" + x + "," + y
            + ") size=" + width + "x" + height;
    }

    // Approach 2: classify and extract using a nested record pattern.
    static String usingPatterns(Object value) {
        return switch (value) {
            case Rectangle(
                    String id,
                    Point(int x, int y),
                    Size(int width, int height))
                    when width > 0 && height > 0 ->
                id + " origin=(" + x + "," + y
                    + ") size=" + width + "x" + height;

            case Rectangle(var id, var origin, var size) ->
                "invalid rectangle";

            case null -> "null input";

            default -> "unsupported type";
        };
    }

    public static void main(String[] args) {
        Rectangle valid = new Rectangle(
            "R-1", new Point(2, 3), new Size(4, 5));

        System.out.println(usingAccessors(valid));
        System.out.println(usingPatterns(valid));

        System.out.println(usingPatterns(
            new Rectangle("R-2", null, new Size(4, 5))));
        System.out.println(usingPatterns(
            new Rectangle("R-3", new Point(2, 3), new Size(0, 5))));
        System.out.println(usingPatterns(null));
        System.out.println(usingPatterns("other"));
    }
}
```

Save the file with the exact name and compile/run with JDK 21 or later:

```bash
javac --release 21 DeconstructionComponentsDemo.java
java DeconstructionComponentsDemo
```

Output:

```text
R-1 origin=(2,3) size=4x5
R-1 origin=(2,3) size=4x5
invalid rectangle
invalid rectangle
null input
unsupported type
```

**Reading the results:**

| Case | How it is handled | Result |
| --- | --- | --- |
| `R-1` with `Point(2,3)` and `Size(4,5)` | Both accessor and pattern read all 4 numbers; guard is true | Two identical info lines |
| `R-2` with `origin == null` | Nested `Point(...)` does not match; `case Rectangle(var ...)` handles it | `invalid rectangle` |
| `R-3` with `width == 0` | Nested pattern matches, but `when width > 0` is false | `invalid rectangle` |
| Input value `null` | `case null` | `null input` |
| String `"other"` | `default` because it is not a `Rectangle` | `unsupported type` |

The `usingAccessors` method illustrates direct data access when **preconditions are already guaranteed**. The `usingPatterns` method simultaneously checks structure and classifies input; the two methods do not necessarily replace each other in every situation. In the valid case, they build the same result string.

## 4. Adding conditions after deconstruction

A record pattern describes **type and shape**; business conditions such as positive width/height should be written outside the pattern.

**With instanceof**, append `&&` after the pattern:

```java
if (value instanceof Rectangle(
        var id, Point(var x, var y), Size(var width, var height))
        && width > 0 && height > 0) {
    // value is a Rectangle with valid origin/size,
    // and both width and height are positive.
}
```

If the structure does not match, Java will not evaluate the subsequent parts of the `&&` chain and will not attempt to use unbound variables.

**With switch**, place the `when` guard immediately after the `case` pattern:

```java
// Excerpt from a switch expression:
case Rectangle(
        var id, Point(var x, var y), Size(var width, var height))
        when width > 0 && height > 0 ->
    id + ": " + width + "x" + height;
```

`when` is evaluated only after the pattern matches. When the guard returns `false`, Java continues searching for another matching `case` branch. In the program in section 3, the `Rectangle(var id, var origin, var size)` branch acts as a fallback.

**Do not confuse:** Starting from Java 21, pattern matching for `switch` uses the `when` syntax; do not write `case ... && condition` as in the older syntax of some preview versions.

## 5. Null, variable scope, and case ordering

### 5.1. Deconstruction does not automatically replace all null checks

- `null instanceof Rectangle(...)` is `false`.
- If `Rectangle` is not `null` but `origin == null`, the nested pattern `Point(...)` does not match and the branch containing it is skipped.
- If `size == null`, the nested pattern `Size(...)` also does not match.
- `case Rectangle(var id, var origin, var size)` can still match a `Rectangle` whose **reference components** such as `origin` or `size` are `null`. A `var` pattern at a component position does not require the reference value to be non-null.
- A `switch` selector that is `null` must be handled explicitly with `case null` if specific behavior is needed; `default` alone generally does not replace null handling.

Therefore, deconstruction is beneficial when the data structure requires all nested records to be present: a specific branch runs only if they exist. However, bound components can still hold `null` if the sub-pattern allows it; check separately when business rules forbid null.

### 5.2. Variables exist only within the matched branch

`x`, `y`, `width`, and `height` in `if` are **pattern variables**. The compiler allows using them inside the `if` body and in the parts of the `&&` condition where the match is guaranteed to have succeeded. In `switch`, they can be used in the `when` guard and the corresponding `case` body.

Do not use those variables in other branches or outside the scope analyzed as matched. Give different names to the components; declaring two pattern variables with the same name in the same pattern is a compile-time error.

### 5.3. Place specific branches before broad branches

The following snippet is **intentionally invalid** when placed in the same `switch`:

```java
case Rectangle(var id, var origin, var size) -> "any rectangle";
case Rectangle(var id, Point(var x, var y),
               Size(var width, var height)) -> "detailed";
```

The first branch already covers all non-null `Rectangle` values, so the second branch can never be selected; Java reports a *dominated case* error. Place deeper and guarded branches first, and general branches later.

If you use a `switch` expression on a selector of type `Object`, you must ensure **exhaustiveness**, for example by having `default` to handle other types. `case null` is a separate option for handling null input.

## 6. Record patterns vs. accessors: choosing the right tool

| Situation | Approach to consider | Why |
| --- | --- | --- |
| Only one component is needed, e.g. `user.name()` | Call accessor | Simple, short, clear intent |
| Already have an object guaranteed to be valid and only need a few fields | Accessors or intermediate record variables | No need to create a branching context |
| Checking the type and extracting multiple components at once | `instanceof Record(...)` | Type check + data binding in one step |
| Multiple structures/variants to handle | `switch` with record patterns | Choice branches clearly describe data shapes |
| Deeply nested records | Nested record pattern with limited depth | Fewer accessor chains, expected structure is easy to see |
| Pattern is too long or business logic is complex | Extract a method; keep accessors if clearer | Avoids a hard-to-maintain branching expression |

**Do not assume record patterns are always faster.** Deconstruction still relies on the record's accessors; Java does not guarantee that replacing source code with patterns is a performance optimization. A record can also define custom accessors, so do not use calls with side effects to justify matching multiple times. If you need to evaluate performance, measure in the actual context.

**Deconstruction does not create a new record** and does not automatically deep-copy. Records have final components, but reference components can point to mutable objects. Extracting multiple variables also does not equate to taking an atomic snapshot in a multithreaded program.

**Record patterns apply to records, not arbitrary classes.** For regular POJOs, use type patterns and class methods. When you need to bind multiple fields from an ordinary object, Java 21 has no arbitrary deconstruction syntax like some other languages.

## 7. Process for refactoring from accessors to deconstruction

1. Identify the outermost record and the tree of components actually needed.
2. Read the existing accessor expressions, e.g. `rect.origin().x()`, `rect.origin().y()`, `rect.size().width()`.
3. Place the corresponding record pattern where `if`/`instanceof` or `switch` branching **already exists**; avoid creating patterns just to force all code into one style.
4. Name variables meaningfully such as `x`, `y`, `width`, `height`. You can use `var` when types are already clear from the record and component signatures.
5. Move value checks into `&&` or `when`; add fallback branches for missing nested records, invalid data, and null.
6. Re-run valid cases, missing-component cases, boundary values, and wrong-type inputs. Verify that error handling remains clear and semantics have not changed unintentionally.

### Practice exercise

Add `record Color(int red, int green, int blue) {}` and update the `Rectangle` definition to include a `Color color` component. Write a `switch` that extracts `id`, `x`, `y`, `width`, `height`, `red`, `green`, and `blue` simultaneously using a nested record pattern. Require in the guard that `width > 0`, `height > 0`, and each color channel is in the range 0..255; add a fallback case to handle a missing color component or invalid values.

This exercise highlights the benefit of deconstruction when **multiple related values** are needed and also clarifies why pattern depth must be controlled for readability.

## References

- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 440: https://openjdk.org/jeps/440
- OpenJDK JEP 441: https://openjdk.org/jeps/441
