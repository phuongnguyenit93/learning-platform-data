# Casting Again After Matching: A Common Pitfall in Java Pattern Matching

## 1. The Problem: Having a Pattern Variable Yet Casting Again

When writing Java out of old habit, a type check with `instanceof` is often followed by a cast. However, **pattern matching** can simultaneously **check the type** and **bind the matched value** to a variable of the appropriate type. In that case, casting again to the exact same type that was just matched is usually a **redundant cast** that provides no additional guarantee.

```java
Object value = "Java";

if (value instanceof String text) {
    String again = (String) value; // Redundant cast: we already have the String variable text.
    System.out.println(text.toUpperCase());
}
```

With the `text` variable, the compiler already knows its static type is `String`. The cast `(String) value` in the example above usually still compiles; it is not necessarily a syntax error. However, it makes the code harder to read, introduces an extra variable name, and can lead to a more serious bug if the developer **re-evaluates a source expression with side effects** instead of using the matched variable.

Distinguish accurately:

- `value instanceof String`: traditional type check; **does not** create a pattern variable. If `value` is declared as `Object`, a cast may be needed when calling `String` APIs.
- `value instanceof String text`: **type pattern**; checks the type and creates the variable `text` already typed as `String` within the valid control-flow scope.
- `value instanceof Location(var name, Point(var x, var y))`: **record pattern**; checks and deconstructs components of nested `record`s.

Type patterns in `instanceof` have been stable since **Java 16** (JEP 394). Record patterns and pattern matching for `switch` have been stable since **Java 21** (JEP 440, 441). The complete program in this article requires **JDK 21+**, without `--enable-preview`.

## 2. Before and After Refactoring: Same Logic, No Redundant Cast

### Old approach: check `instanceof` then cast

```java
static String legacy(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        if (!text.isBlank()) {
            return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
        }
    }
    return "other";
}
```

Here, `value instanceof String` only returns a `boolean`. The code calling `String.isBlank()` and `String.trim()` requires an object with static type `String`, so casting after the check was the reasonable way to write this in older Java.

### New approach: use the matched variable directly

```java
static String modern(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
    }
    return "other";
}
```

`text` is declared right in the type pattern. The right-hand side of `&&` only executes when the left-hand side matches, so `text.isBlank()` is called when the variable already holds a valid value.

With `" java "`, `"   "`, `42`, and `null`, both versions produce `text:JAVA`, `other`, `other`, and `other`, respectively. The program in Section 6 includes an actual comparison check, throwing an `AssertionError` if the old and new results differ.

The main benefits are **fewer repetitive casts, fewer intermediate variables, and directly expressing the type guarantee that the compiler has already verified**. Do not assume that removing a cast always makes the program run faster: the JIT can optimize equivalent operations; benchmark if performance is truly a requirement.

## 3. Casting the Same Matched Value Usually Does Not Change the Value

```java
if (value instanceof String text) {
    String again = (String) value;
    System.out.println(again == text); // true if value is still the same reference.
}
```

In a scenario where the source is the same unchanged reference, casting to `String` **does not create a new String** and does not transform its content. It merely expresses a type requirement already satisfied by the type pattern. The flaw is not just an extra line: if other parts of the code start using `again` instead of `text`, the intent of the match step becomes harder to follow.

Do not confuse a cast with **mapping** or **data conversion**. `new Dto(text)` creates a target object; `text.toUpperCase()` creates a string via an API; `(String) value` only casts the reference and does not perform those conversions.

## 4. Flow Scoping: Knowing When a Pattern Variable Can Be Used

Java applies **flow scoping**: a pattern variable is in scope wherever every execution path reaching that point guarantees the pattern has matched.

### Inside the true `if` branch

```java
static void show(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Valid.
    } else {
        System.out.println("not a String");
        // Cannot use text here.
    }
}
```

In `else`, the pattern may not have matched. Casting `(String) value` there does not fix the issue; it can throw `ClassCastException` or fail to handle `null` properly.

### Short-circuit `&&` and the `||` trap

**Valid:**

```java
if (value instanceof String text && text.startsWith("J")) {
    System.out.println(text);
}
```

**Invalid:**

```java
// Wrong: the right-hand side of || can run when the pattern on the left did NOT match.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("found");
}
```

The right-hand side of `||` executes when the left-hand side is `false`; at that point `text` cannot be used. Do not replace it with `((String) value).isEmpty()` because `value` might not be a `String` at that point.

### Guard clauses and variables used after `if`

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) return -1;
    return text.length();
}
```

The negated branch terminates the method, so the last line can only execute after `value instanceof String text` succeeds. `text` is valid on the last line. If the negated branch only logged a message and let the method continue, this guarantee would no longer hold.

**Conclusion:** Do not cast again to "bring a variable out of scope." Structure conditions and control paths with `if`, guard clauses, `&&`, or `switch` so the compiler can prove the match.

## 5. Pattern Matching in `switch` and Record Patterns

### Type patterns in `switch`

```java
static String typeLabel(Object value) {
    return switch (value) {
        case String text -> "S:" + text;
        case Integer number -> "I:" + number;
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Each case declares a variable of the right type. There is no need for `(String) value` in `case String text` or `(Integer) value` in `case Integer number`. Variables from another case cannot be used arbitrarily when that case did not match.

**`null`:** `value instanceof String text` is `false` if `value == null`. With `switch`, handling `null` must be intentional; `case null` in the example addresses this case. Without an appropriate `null`-handling branch, switching on a null reference can throw `NullPointerException`.

### Record patterns with nested components

```java
record Point(int x, int y) {}
record Location(String name, Point point) {}
```

If you want to keep the object intact:

```java
if (value instanceof Location location) {
    Point point = location.point();
    if (point != null) {
        System.out.println(location.name() + ": " + point.x());
    }
}
```

`location` is already a `Location`. Writing `((Location) value).point()` is a redundant cast. When the goal is only to extract components, use a nested record pattern:

```java
if (value instanceof Location(var name, Point(var x, var y))) {
    System.out.println(name + ": " + x + "," + y);
}
```

`name` has type `String`, and `x` and `y` have type `int` according to the record declaration. There is no need to cast the source object again or cast from `Object` to obtain these values. If the `point` component is `null`, the nested pattern `Point(...)` does not match and the entire `instanceof` expression returns `false`.

**Be careful:** `Location(var name, var point)` can still bind `point = null`; `var` by itself does not mean "this component is non-null." A record pattern does not create a deep copy, does not automatically create a new DTO, and does not automatically validate business rules. Component deconstruction follows the **declaration order of the record**, so do not reorder variables by guesswork.

## 6. Complete Compilable and Runnable Example

Create the file **`CastAfterMatchDemo.java`**:

```java
public class CastAfterMatchDemo {
    record Point(int x, int y) {}
    record Location(String name, Point point) {}

    static String legacy(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            if (!text.isBlank()) {
                return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
            }
        }
        return "other";
    }

    static String modern(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "text:" + text.trim().toUpperCase(java.util.Locale.ROOT);
        }
        return "other";
    }

    static boolean repeatedCastSame(Object value) {
        if (value instanceof String text) {
            String again = (String) value;
            return again == text;
        }
        return false;
    }

    static String coordinates(Object value) {
        if (value instanceof Location(var name, Point(var x, var y))) {
            return name + "@(" + x + "," + y + ")";
        }
        return "no-location";
    }

    static int lengthOrMinusOne(Object value) {
        if (!(value instanceof String text)) return -1;
        return text.length();
    }

    static String typeLabel(Object value) {
        return switch (value) {
            case String text -> "S:" + text;
            case Integer number -> "I:" + number;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static void check(Object value) {
        String left = legacy(value);
        String right = modern(value);
        if (!left.equals(right)) {
            throw new AssertionError(left + " != " + right);
        }
        System.out.println(right);
    }

    public static void main(String[] args) {
        check(" java ");
        check("   ");
        check(42);
        check(null);
        System.out.println("same-ref:" + repeatedCastSame("hi"));
        System.out.println(coordinates(new Location("HCM", new Point(2, 3))));
        System.out.println(coordinates(new Location("HCM", null)));
        System.out.println(lengthOrMinusOne("abc"));
        System.out.println(lengthOrMinusOne(5));
        System.out.println(typeLabel("ok"));
        System.out.println(typeLabel(7));
        System.out.println(typeLabel(null));
    }
}
```

Run with JDK 21 or later:

```bash
javac --release 21 CastAfterMatchDemo.java
java CastAfterMatchDemo
```

**Exact stdout:**

```text
text:JAVA
other
other
other
same-ref:true
HCM@(2,3)
no-location
3
-1
S:ok
I:7
NULL
```

Tested on JDK 24 with Java 21 syntax and confirmed to produce the exact **12 lines** above. The `check` method compares the legacy result with the refactored result; it not only prints the output but also throws an `AssertionError` if they differ.

| Test case | Behavior |
| --- | --- |
| `" java "` | Both methods return `text:JAVA` |
| Blank string, `Integer`, `null` | All return `other` |
| Re-casting after matching the same stable value | `same-ref:true`, no new reference created |
| `Location("HCM", Point(2,3))` | Nested pattern extracts coordinates, returns `HCM@(2,3)` |
| `Location("HCM", null)` | Sub-pattern does not match, returns `no-location` |
| Guard clause receiving `"abc"` and `5` | Returns `3` and `-1` |
| Switch with `"ok"`, `7`, `null` | Returns `S:ok`, `I:7`, `NULL` |

## 7. A More Serious Bug: Re-reading the Matched Expression

A bug that easily appears when migrating old code to pattern matching is **calling an expression with side effects again** and then casting the new value:

```java
// Wrong: two calls to removeFirst() consume two different elements.
if (queue.removeFirst() instanceof String text) {
    String again = (String) queue.removeFirst();
    System.out.println(again);
}
```

The pattern checked **the value returned by the first `removeFirst()` call**, not every subsequent result of the method. The second call might return an `Integer` or the queue might already be empty; this cast can throw `ClassCastException` (or an exception from the retrieval operation).

**Correct if you want to use the element just matched:**

```java
if (queue.removeFirst() instanceof String text) {
    System.out.println(text);
}
```

The standalone test snippet below can be placed in a method or run in JShell:

```java
var queue = new java.util.ArrayDeque<Object>();
queue.add("first");
queue.add(99);

if (queue.removeFirst() instanceof String text) {
    try {
        String again = (String) queue.removeFirst();
        System.out.println(again);
    } catch (ClassCastException ex) {
        System.out.println("first=" + text
                + ", second-cast=ClassCastException");
    }
}
```

Output from the print statement in the snippet above:

```text
first=first, second-cast=ClassCastException
```

Verified this scenario with JDK 24: `text` still holds `"first"`, while the second read retrieves `Integer(99)`, causing the cast to fail.

**Key rule:** Use the **pattern variable** to process the exact value that was checked, especially when the source is an iterator, queue, stream-like API, data query, randomized API, or accessor with side effects. Do not replace a "redundant cast" with "casting a new result" and assume the logic is unchanged.

## 8. When Does a Cast Have a Purpose and Should Not Be Removed Arbitrarily?

### 8.1. Pattern variable is not used yet

```java
if (value instanceof String) {
    String text = (String) value;
}
```

Here there is only a traditional type check; if you have not switched to the `String text` syntax yet, the cast serves to turn `Object` into `String` inside the checked branch.

### 8.2. A narrower type than the matched type is needed

```java
if (value instanceof CharSequence chars) {
    System.out.println(chars.length());
    if (chars instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
```

`chars` has type `CharSequence`, which is not guaranteed to be a `String`. It could be a `StringBuilder`. The second type pattern performs a legitimate additional check instead of blindly casting to `String`.

### 8.3. Intentionally changing the static type for overload resolution

```java
static void handle(Object value) {
    System.out.println("Object");
}

static void handle(CharSequence value) {
    System.out.println("CharSequence");
}

// Inside a method that has Object input:
if (input instanceof String text) {
    handle(text);          // Selects handle(CharSequence).
    handle((Object) text); // Selects handle(Object).
}
```

The two overloaded methods and the `if` block above are **illustrative snippets that must be placed inside an appropriate class/method**, not a standalone compilable file. The cast `(Object) text` intentionally changes the static type of the expression to select an overload; it is different from casting `(String) input` when you already have `String text`.

### 8.4. Data conversion rather than reference casting

`new ResponseDto(text)`, `Integer.parseInt(text)`, or a formatter method is **mapping or conversion**. They may be necessary after matching, but they are not re-casting to the same type. Name the conversion responsibility clearly, and avoid using a cast as a validation mechanism that does not actually validate business data.

## 9. Generic Types and Non-existent "Type Guarantees"

Because of **type erasure**, `instanceof` does not by itself prove that every element in a `List` is a `String`. With a variable `Object value`, the following syntax cannot be used to check a generic type argument:

```java
// Invalid in an Object context: List<String> is not reifiable.
if (value instanceof java.util.List<String> strings) {
    System.out.println(strings.size());
}
```

The right approach is to check the container with a wildcard and check each element:

```java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

These are illustrative snippets inside a method with a `value` variable. Casting `List<?>` to `List<String>` adds no real runtime check on the elements; an unchecked cast can also hide data errors until the elements are used later.

## 10. Common Mistakes and How to Fix Them

| Mistake | Risk | Fix |
| --- | --- | --- |
| `if (x instanceof String s) { String t=(String)x; }` | Unnecessary extra variable and repeated cast | Use `s` directly |
| `case String s -> ((String)x).length()` | Ignores the already-typed pattern variable | Use `s.length()` |
| Matched `Location(...)` then cast `x` again to call accessors | Verbose code, defeats the purpose of deconstruction | Use component patterns or keep `Location location` if the whole object is needed |
| Putting `s` on the right-hand side of `||` after a type pattern | No match guarantee | Use `&&` if the condition needs the pattern variable |
| Using the pattern variable in `else` | Not guaranteed to be assigned | Only use it in the matched branch or after a valid guard clause |
| Calling `removeFirst()` or `next()` twice in order to cast | Uses two different values, causing side effects | Use the pattern variable from the first call |
| Assuming `instanceof` on `null` throws an error | Incorrect semantics | `null instanceof T t` returns `false` |
| Omitting null handling in a pattern switch | A null switch selector can throw an exception | Use `case null` or a separate guard |
| Casting `CharSequence` to `String` without checking | Possible `ClassCastException` | Use an additional `instanceof String text` |
| Casting a generic list to bypass validation | Does not actually prove element types | Use `List<?>` and check elements |

## 11. Practice Exercises

**Exercise A — remove the cast:** Rewrite the following method using one type pattern and one `&&` condition:

```java
static int score(Object source) {
    if (source instanceof String) {
        String text = (String) source;
        if (!text.isBlank()) return text.length();
    }
    return 0;
}
```

Answer:

```java
static int score(Object source) {
    if (source instanceof String text && !text.isBlank()) {
        return text.length();
    }
    return 0;
}
```

Cases to test: `" Java "` gives `6` (because `trim` is not called), `"   "` gives `0`, `123` gives `0`, `null` gives `0`.

**Exercise B — nested record:** Given `record Coordinate(int x, int y) {}` and `record Checkpoint(String code, Coordinate point) {}`. Write a match condition to print the code and the sum of the coordinates, without casting.

```java
// Inside a method that has Object input.
if (input instanceof Checkpoint(var code, Coordinate(var x, var y))) {
    System.out.println(code + ":" + (x + y));
}
```

If `point == null`, the nested record pattern does not match and the branch does not execute; no cast is needed and this match does not cause a `NullPointerException`.

**Exercise C — side effect:** Identify the bug in the snippet:

```java
if (iterator.next() instanceof String text) {
    String again = (String) iterator.next();
    use(again);
}
```

Answer: not only is there a redundant cast, but `iterator.next()` is called **twice**, which may retrieve a different element or exhaust the iterator. If the goal is to process the element just matched, use `use(text);`. This is illustrative code, assuming `iterator` and `use` already exist in context.

## 12. Refactoring Checklist

1. **Is there already a type/record pattern variable?** If so, use it before writing a cast to the same type.
2. **Does the scope guarantee a match?** Check `if` branches, `&&`, guard clauses, `switch`, and paths that can fail.
3. **Is the source stable?** Do not re-evaluate an expression with side effects to fetch a new value and cast it.
4. **Does the cast have another purpose?** Distinguish a redundant same-type cast from checking a narrower subtype, overload selection, or an actual conversion.
5. **Are there `null`s, nullable record components, or generic types?** Patterns do not replace validation; do not assume runtime information that Java does not check.
6. **Have you tested both old and new behavior?** Include matching-type values, wrong-type values, `null`, boundary data, and side-effect bugs.

**Remember:** Once a pattern matches, the pattern variable is the type-checked value. Write code against that variable; do not cast again out of old habit, and especially do not re-evaluate an expression with side effects assuming the result is still the matched object.

Official documentation:

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
