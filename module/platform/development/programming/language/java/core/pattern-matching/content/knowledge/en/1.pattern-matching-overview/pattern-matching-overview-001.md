# What problem does pattern matching solve in Java?

## 1. Where does the problem come from?

In Java, a variable has a **compile-time declared type**, but the object that the variable references may belong to a more specific type at runtime. For example, a parameter of type `Object` can receive a `String`, an `Integer`, or another object. When needing to handle each type separately, developers often have to:

1. Check whether the object belongs to the type to be handled using `instanceof`.
2. Explicitly cast to access members of that type.
3. Create a new variable, and only then use the data.

The two operations of checking and casting usually refer to **the same object and the same type**, so the old style repeats information. With data structures that have multiple variants, conditional branches also easily become long, hard to read, and prone to variable mix-ups. **Pattern matching** allows expressing both the matching condition and the extraction of needed data simultaneously, helping the compiler verify types and variable scope.

The short idea: instead of asking `is this object a String?` and then casting manually, we write `if this object is a String, call it s to use in the matching branch`.

## 2. Before and after: a runnable example with Java 17

File `PatternMatchingBasics.java`:

```java
public class PatternMatchingBasics {
    static String traditional(Object value) {
        if (value instanceof String) {
            String s = (String) value;
            return "Chuỗi dài " + s.length();
        }
        if (value instanceof Integer) {
            Integer n = (Integer) value;
            return "Số nhân đôi " + (n * 2);
        }
        return "Kiểu khác";
    }

    static String modern(Object value) {
        if (value instanceof String s) {
            return "Chuỗi dài " + s.length();
        }
        if (value instanceof Integer n) {
            return "Số nhân đôi " + (n * 2);
        }
        return "Kiểu khác";
    }

    public static void main(String[] args) {
        System.out.println(traditional("Java"));
        System.out.println(modern("Java"));
        System.out.println(modern(21));
        System.out.println(modern(null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac PatternMatchingBasics.java
java PatternMatchingBasics
```

Output:

```text
Chuỗi dài 4
Chuỗi dài 4
Số nhân đôi 42
Kiểu khác
```

In `value instanceof String s`, **`String` is the pattern type**, and **`s` is the pattern variable**. If the check succeeds, `s` already has the type `String` so `length()` can be called directly. If it does not match, that branch does not run. Both methods return the same result, but the `modern` version eliminates the casts and duplicate declarations.

It is important to distinguish: `instanceof String s` does not turn an arbitrary object into a `String` and does not change the actual runtime type of `value`. It only names a reference of the appropriate type **when the condition matches**.

## 3. What does pattern matching actually improve?

| Problem in traditional code | Pattern matching support | Limitations to remember |
| --- | --- | --- |
| Checking `instanceof` and then casting the same type | Combines type check and variable declaration into a single expression | Does not turn an object of the wrong type into the right type |
| Many temporary variables, many repetitive casts | Reduces boilerplate code, makes handling branches clearer | Does not automatically eliminate every `if` or `switch` |
| Using variables after a check is prone to scope errors | The compiler analyzes where the pattern is definitely matched | Pattern variables are not available on every branch |
| Handling multiple object types via long `if/else if` chains | `switch` with type patterns (Java 21) expresses cases directly | Must consider case ordering, exhaustiveness, and `null` |
| Extracting record fields requires manual accessor calls | Record patterns (Java 21) extract components directly in the pattern | Applies only to the corresponding record; cannot arbitrarily destructure every class |

The main benefits are **shorter code where repetition exists**, **clearer intent**, and **better static checking**. This is an improvement in expressiveness and type safety; there is no guarantee that the program will run faster in all cases.

## 4. A pattern variable only exists where it definitely matches

Java uses control-flow analysis to determine whether a pattern variable is definitely assigned (commonly called *flow scoping*). The following example is a valid method in Java 17:

```java
static void printNonBlank(Object value) {
    if (value instanceof String s && !s.isBlank()) {
        System.out.println(s.trim());
    }
}
```

The right-hand side of `&&` is only evaluated when `value instanceof String s` is true, so `s` is valid to use there and inside the `if` body. Conversely, `s` cannot be arbitrarily used on the right-hand side of `||`: that side can execute when the pattern **does not match**. Similarly, after a regular `if` that can take either branch, it cannot be assumed that `s` still exists.

Another valid case is **checking for failure and returning early**:

```java
static int lengthOfString(Object value) {
    if (!(value instanceof String s)) {
        return 0;
    }
    return s.length();
}
```

After the `if`, every remaining path that continues has already matched `String s`, so `s` can be used. This is safer than casting manually without checking. Even so, pattern matching does not replace understanding control flow: if `return` is replaced with an operation that does not terminate the branch, you cannot assume the variable is assigned.

### The null case

With `instanceof` type patterns, `null instanceof String s` is `false`. Therefore `modern(null)` in the first example returns `"Kiểu khác"` and does not cause a `NullPointerException`. However, do not generalize that every pattern-matching `switch` also handles `null` automatically; that follows a different rule, see the next section.

## 5. From multiple ifs to pattern matching in switch in Java 21

When an expression needs to examine multiple cases, Java 21 allows **type patterns in `switch`** and provides the `when` syntax to add a guard condition (*guard*). For records, **record patterns** also help deconstruct data components when matching. Both pattern matching for switch (JEP 441) and record patterns (JEP 440) are standard features since **Java 21**.

Standalone example, file `PatternSwitchDemo.java` (requires JDK 21 or later):

```java
public class PatternSwitchDemo {
    record Point(int x, int y) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "Giá trị null";
            case Point(int x, int y) when x == 0 && y == 0 -> "Gốc tọa độ";
            case Point(int x, int y) -> "Điểm (" + x + ", " + y + ")";
            case String s when s.isBlank() -> "Chuỗi trắng";
            case String s -> "Chuỗi: " + s;
            case Integer n -> "Số: " + n;
            default -> "Kiểu khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(" "));
        System.out.println(describe(7));
        System.out.println(describe(null));
    }
}
```

Run commands:

```bash
javac PatternSwitchDemo.java
java PatternSwitchDemo
```

Output:

```text
Gốc tọa độ
Điểm (2, 3)
Chuỗi trắng
Số: 7
Giá trị null
```

Here:

- `case Point(int x, int y)` matches a `Point` and extracts the components `x`, `y`. There is no need to call `point.x()` and `point.y()` separately.
- `when x == 0 && y == 0` only accepts the `Point` at the origin. When the guard is false, `switch` continues checking the next `Point` case.
- `case String s when s.isBlank()` must appear before `case String s`, because an unguarded `String` case covers all non-null strings.
- `case null` handles null input intentionally. With a pattern `switch` on a reference type, if there is no branch accepting null, a null input normally throws a `NullPointerException`, even when `default` is present.
- `default` is the fallback for the remaining types of the `Object` parameter.

**Version boundary:** `instanceof` type patterns have been a standard feature since Java 16, so they work in Java 17. Pattern `switch` and record patterns are standard features since Java 21. Do not copy the `switch` example above into a Java 17 project and expect it to compile with standard commands; Java 17–20 had *preview* versions with changing rules/syntax. The example above uses the stable Java 21 syntax.

## 6. Combining with sealed types: checking exhaustiveness

When a data model has a **closed set of variants** using a `sealed interface` or `sealed class`, the compiler can verify that a `switch` expression handles all permitted subtypes. This is another advantage over `if/else` chains: missing a variant can be caught right at compile time.

Standalone example, file `SealedSwitchDemo.java` (JDK 21+):

```java
public class SealedSwitchDemo {
    sealed interface Outcome permits Success, Failure {}
    record Success(String value) implements Outcome {}
    record Failure(String reason) implements Outcome {}

    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Success(String value) -> "OK: " + value;
            case Failure(String reason) -> "Lỗi: " + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("đã lưu")));
        System.out.println(describe(new Failure("timeout")));
    }
}
```

```bash
javac SealedSwitchDemo.java
java SealedSwitchDemo
```

```text
OK: đã lưu
Lỗi: timeout
```

`default` is not needed here because `Outcome` only permits two implementing types, `Success` and `Failure`, and both are handled. If a new permitted subtype is added later, the compiler can require updating the `switch` accordingly. This is a very practical maintainability benefit for state models, processing outcomes, or events with a well-defined set of variants.

However, **covering all types does not mean covering null**: calling `describe(null)` in this example can still throw a `NullPointerException`. Also note that a case with `when` only covers values that satisfy the guard; guarded branches alone are usually not enough to prove exhaustiveness.

## 7. When is pattern matching a reasonable choice?

Some practical scenarios:

- **Handling multi-type input at system boundaries:** code receiving `Object` from a generic API, utility, event handler, or adapter that must branch based on the actual type. Using `instanceof T t` helps avoid repetitive casts.
- **Outcomes with multiple variants:** with `sealed` and `record`, a `switch` can clearly describe each success/failure case and be checked for exhaustiveness.
- **Immutable record-shaped data structures:** record patterns help extract components (including nested patterns when types match), which is useful when working with DTOs, parsing results, geometry, or categorized data.
- **Filtering a case before using the value:** a type pattern combined with `&&` expresses both the type condition and the content condition, while the variable only exists in the safe branch.

For example, when handling `Object value`, `value instanceof String text && !text.isBlank()` is clearer than a sequence of type checking, casting, and then checking the string. But if all inputs already share a common type with an appropriate polymorphic method, calling that method is usually simpler than a large `switch` distinguishing each subclass.

## 8. What pattern matching does not solve

1. **Does not replace object-oriented design.** If you own the classes and each type already knows how to perform a behavior, polymorphism (interface/override) usually avoids having to check types everywhere. Pattern matching is very useful where *data classification* is needed, but it is not a reason to turn every business flow into a giant `switch`.
2. **Does not check element types of erased generics.** You cannot use the type pattern `instanceof java.util.List<String> strings` to verify that every element is a `String`. Due to *type erasure*, you can check `instanceof java.util.List<?> list`, and then check elements when needed.
3. **Not regex or text matching.** Patterns here express types/data structures in the Java language, not substring matching via regular expressions.
4. **Does not automatically validate business rules.** `case Point(int x, int y)` only extracts the record components; if coordinate bounds need validation, you must add appropriate conditions/validation.
5. **Does not guarantee higher performance.** The direct benefits are clarity and static checking; optimization depends on the compiler, runtime, and specific problem.

## 9. Common mistakes and how to avoid them

| Common mistake | Why / how to handle |
| --- | --- |
| Using a pattern variable in a branch where it might not have matched, such as the right-hand side of `||` | Use `&&` when you want to check additional conditions after matching; or separate logic with clear control flow |
| Assuming `instanceof` with null will match a reference type | `null` does not match a type pattern; handle null separately if needed |
| Placing `case CharSequence cs` before `case String s` in a Java 21 switch | The first case already covers all Strings, making the latter case *dominated* and invalid; place the more specific case first |
| Writing only `when`-guarded branches in a switch expression and forgetting other cases | A guard makes a case match only a subset; add an unguarded general case or `default` when exhaustiveness is required |
| Using Java 21 `when`/record pattern syntax in a project built with Java 17 | Check the JDK version, `--release`, and source language level; use `instanceof` type patterns when Java 17 compatibility is needed |
| Assuming a `List<?>` pattern verifies the type of every element | Check and handle each element if generic element type requirements exist |
| Using pattern matching everywhere instead of polymorphic methods | Keep behavior in the object types when the domain design allows; use patterns when the real goal is classifying/destructuring data |

## 10. How to decide whether to use it

When encountering a long piece of Java code due to type checking, ask yourself:

1. Are you repeatedly writing `instanceof` and casting the same object? If yes, `instanceof T variable` is usually a direct improvement, compatible with Java 17.
2. Are there multiple data variants and does the project use Java 21+? Consider pattern `switch`, especially when the input is `sealed` or `record`.
3. Do you need to extract record components? Record patterns help extract them clearly right at the check site.
4. Do you need to handle null, case ordering, guards, and new variants? Design all branches completely before replacing `if/else` with `switch`.
5. Can it be solved more simply with polymorphism? If yes, prefer a clean domain design.

**Conclusion:** Pattern matching eliminates the repetitive and error-prone boilerplate between **identifying a value** and **using that value under its known type/structure**. Start with `instanceof` type patterns in Java 17, then move to `switch` and record patterns in Java 21 when the problem has multiple variants or record-shaped data. The core value is readable code, fewer casts, safely scoped variables, and many missing-case bugs caught right at compile time.