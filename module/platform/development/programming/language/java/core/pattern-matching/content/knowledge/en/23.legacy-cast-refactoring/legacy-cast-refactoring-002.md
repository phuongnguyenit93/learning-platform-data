# Refactoring a Single Type-Check Branch: From `instanceof` + Cast to Pattern Matching

## 1. Goal of the Refactoring

In Java before *pattern matching for `instanceof`*, a type-check branch typically had two consecutive operations:

1. Check whether the value belongs to the target type using `instanceof`.
2. If true, manually cast the same value to that type in order to call methods or use its data.

Example:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Since **Java 16** (JEP 394), these two steps can be combined into a single **type pattern**:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`String text` inside `instanceof` both specifies the type to check and declares the **pattern variable** `text`. When the condition matches, `text` has static type `String` and references the exact same object that was checked. Java **does not create a new `String` object** and does not mutate the object's contents.

In this lesson, the scope is **refactoring a single type-check branch** in an existing program: removing the redundant cast while preserving the `if`/`else` control-flow paths and the processed values. This is a small but common technique when upgrading legacy Java code. **Java 17** already supports type patterns in `instanceof`; with Java 21, you can also consider record patterns when the input data is a record.

## 2. Before/After Example: One Branch, Same Behavior

### Before refactoring: check then cast

```java
static void handleLegacy(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println("text=" + text.strip().toUpperCase());
    } else {
        System.out.println("unsupported");
    }
}
```

The `if` branch only runs when `value` is a `String`, so the cast `(String) value` inside that branch is safe. However, repeating the type name `String` and the expression `value` makes the code more verbose than necessary.

### After refactoring: type pattern directly in `instanceof`

```java
static void handleModern(Object value) {
    if (value instanceof String text) {
        System.out.println("text=" + text.strip().toUpperCase());
    } else {
        System.out.println("unsupported");
    }
}
```

Both methods share the same intent: process `String` and route all remaining values into the `else` branch. `text` is only used in the branch where the compiler has proven that matching succeeded.

**Complete program:** save as `SingleBranchRefactor.java`:

```java
import java.util.Locale;

public class SingleBranchRefactor {
    static void legacy(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            System.out.println("old:" +
                    text.strip().toUpperCase(Locale.ROOT));
        } else {
            System.out.println("old:skip");
        }
    }

    static void modern(Object value) {
        if (value instanceof String text) {
            System.out.println("new:" +
                    text.strip().toUpperCase(Locale.ROOT));
        } else {
            System.out.println("new:skip");
        }
    }

    public static void main(String[] args) {
        Object[] cases = {" java ", 42, null};

        for (Object value : cases) {
            legacy(value);
            modern(value);
        }
    }
}
```

Compile and run with JDK 21:

```bash
javac --release 21 SingleBranchRefactor.java
java SingleBranchRefactor
```

Output:

```text
old:JAVA
new:JAVA
old:skip
new:skip
old:skip
new:skip
```

The prefixes `old:` and `new:` are used to distinguish the output of the two methods; the processed content is equivalent. For `42` and `null`, both enter the `else` branch.

## 3. Safe Refactoring Process for a Single Branch

A small refactoring should follow clear steps:

1. **Identify the existing check.** For example, `if (input instanceof Customer)`.
2. **Identify the corresponding cast inside the matching branch.** For example, `Customer customer = (Customer) input;`.
3. **Move the variable name into the type pattern.** Change it to `if (input instanceof Customer customer)`.
4. **Remove only the replaced cast and variable declaration.** Keep the existing processing logic, `else` branch, return statements, and exception handling intact.
5. **Compile and test the execution paths.** At minimum, test one value of the matching type, one value of a non-matching type, and `null` if the reference can be `null`.

Mechanical transformation example:

```java
// Before
if (candidate instanceof Number) {
    Number number = (Number) candidate;
    System.out.println(number.intValue());
}

// After
if (candidate instanceof Number number) {
    System.out.println(number.intValue());
}
```

There is no need to change `Number` to `Integer` just because the current sample data happens to be an `Integer`. Doing so **narrows the set of accepted types**: `Number` also has subtypes such as `Long`, `Double`, and `BigDecimal`. When the goal is purely refactoring, **keep the original type from the existing condition**.

Similarly, if the old branch has an `else`, do not remove or modify the `else` unless there is a new design requirement. A good refactoring can be reviewed by comparing the before and after code line by line.

## 4. Semantics That Must Be Preserved

For the same side-effect-free expression `value`, the same checked type `T`, and the same body, the snippets below perform the same type test and operate on the same object after the test succeeds:

```java
// Old approach
if (value instanceof CharSequence) {
    CharSequence seq = (CharSequence) value;
    consume(seq);
}

// New approach
if (value instanceof CharSequence seq) {
    consume(seq);
}
```

Here, `consume(seq)` is simply a **hypothetical method already available in context**; the two snippets are for comparing refactoring structure, not standalone programs.

Key points:

| Situation | `instanceof` + cast in branch | Type pattern |
| --- | --- | --- |
| Value is of the checked type | Branch executes, cast is valid | Branch executes, pattern variable is bound |
| Value is of a valid subtype | Branch executes | Branch executes |
| Value is not of the type | Condition is `false`, branch is skipped | Condition is `false`, branch is skipped |
| Value is `null` | `instanceof` is `false`, cast in branch is not executed | `instanceof` is `false`, variable is not bound |
| `else` branch exists | `else` runs if not matched | `else` runs if not matched |
| Object after check | References the original value | References the original value |

**Do not confuse `instanceof` with an unchecked direct cast.** If you write `String s = (String) value;` outside a guarding branch, a value of the wrong type can throw `ClassCastException`; refactoring with a type pattern does not introduce that behavior.

For `null`, `value instanceof String text` evaluates to `false` rather than throwing `NullPointerException`. This matches the behavior of `value instanceof String` before refactoring.

## 5. Pattern Variable Scope: *Flow Scoping*

Unlike a regular local variable declared at the top of a block, a pattern variable follows **flow scoping** (control-flow-dependent scope): it is only in scope at locations where the compiler can guarantee that matching succeeded.

Valid:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Invalid if you try to use the variable in `else` or immediately after `if` when the matching branch might have been skipped:

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    // Cannot use text here: the pattern did not match.
}

// Cannot use text here by default.
```

The variable `text` is not declared for every path like a variable pre-initialized to `null`. This is Java's type-safety and definite-assignment mechanism.

If an outer local variable named `text` already exists and causes a scope conflict, choose a different pattern variable name (such as `matchedText`) instead of arbitrarily renaming unrelated variables.

## 6. Combining Conditions with `&&`

A refactoring often encounters an additional business condition checked after the type test:

```java
// Old
if (value instanceof String) {
    String text = (String) value;
    if (!text.isBlank()) {
        System.out.println(text.trim());
    }
}
```

You can keep the two-level structure, or merge the conditions when the intent is simply to process non-blank strings:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

The right-hand side of `&&` is evaluated only when the pattern on the left-hand side has matched; therefore `text.isBlank()` is type-safe and will not fail due to `value == null`.

Complete program `CompoundConditionDemo.java`:

```java
public class CompoundConditionDemo {
    static void print(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            System.out.println("content=" + text.trim());
        } else {
            System.out.println("empty-or-other");
        }
    }

    public static void main(String[] args) {
        print(" hello ");
        print(" ");
        print(1);
        print(null);
    }
}
```

```bash
javac --release 21 CompoundConditionDemo.java
java CompoundConditionDemo
```

Output:

```text
content=hello
empty-or-other
empty-or-other
empty-or-other
```

**Be careful when merging branches:** if the old version had an `else` attached to the type-checking `if`, moving the business condition into `&&` can cause the `else` branch to execute even when the type matches but the business condition fails. The merge above is only valid when you have verified the desired behavior for every branch.

**`||` does not provide the same guarantee.** The expression `value instanceof String text || anotherCondition` can evaluate to `true` because of `anotherCondition` even if the pattern failed. Therefore, `text` cannot be used inside the `if` branch as if it were always bound. Never flip `&&` to `||` just to shorten code.

## 7. Guard Clause: Reducing Nesting While Keeping the Type Check

In a method that exits early when the data has the wrong type, you can turn the check branch into a *guard clause*. Before:

```java
static void handle(Object candidate) {
    if (candidate instanceof CharSequence) {
        CharSequence text = (CharSequence) candidate;
        System.out.println(text.length());
    } else {
        System.out.println("unsupported");
        return;
    }
}
```

After:

```java
static void handle(Object candidate) {
    if (!(candidate instanceof CharSequence text)) {
        System.out.println("unsupported");
        return;
    }

    System.out.println(text.length());
}
```

The new code negates the condition, but **the non-matching branch terminates with `return`**. Because of that, on the line after the guard, the compiler proves that `candidate instanceof CharSequence text` must have succeeded. If the non-matching branch does not terminate (execution can still fall through), the compiler will not allow `text` to be used that way.

Standalone program `GuardClauseDemo.java`:

```java
public class GuardClauseDemo {
    static void handle(Object candidate) {
        if (!(candidate instanceof CharSequence text)) {
            System.out.println("unsupported");
            return;
        }

        System.out.println("length=" + text.length());
    }

    public static void main(String[] args) {
        handle("abc");
        handle(new StringBuilder("xy"));
        handle(null);
    }
}
```

```bash
javac --release 21 GuardClauseDemo.java
java GuardClauseDemo
```

Output:

```text
length=3
length=2
unsupported
```

`CharSequence` is an interface: both `String` and `StringBuilder` match it. Because the refactoring preserves the `CharSequence` type, it does not accidentally exclude `StringBuilder`.

**Only invert the condition after thoroughly checking control flow.** In a small single-branch refactoring, directly replacing `instanceof` + cast is usually the lowest-risk change; a guard clause is an additional improvement if it preserves the execution paths and side effects.

## 8. A Branch with `else`: Checking for Side-Effect Order Changes

With a plain variable `value`, the check and the cast in the old pattern already operated on the same value. However, some legacy code repeats an **expression with side effects**:

```java
// Problematic example: getNext() is called at two different times.
if (source.getNext() instanceof String) {
    String text = (String) source.getNext();
    use(text);
}
```

`source.getNext()` may return **two different values** across the two calls, or advance a cursor, write logs, or perform I/O. Changing it to:

```java
if (source.getNext() instanceof String text) {
    use(text);
}
```

causes `getNext()` to run only **once**. The new version may be more logically sound, but it is **not a strictly behavior-preserving refactoring** when repeated calls have side effects. You must evaluate how `getNext()` behaves before claiming equivalence.

When the old code already stored the value once, the safe approach is to keep the intermediate variable:

```java
Object candidate = source.getNext();

if (candidate instanceof String text) {
    use(text);
}
```

Both `source.getNext()`/`use(text)` examples in this section are **illustrative snippets within a class that already declares those members**, not standalone programs.

In addition, moving code between branches can alter method call timing, object state, logging, or exceptions. **Single-branch refactoring** should avoid relocating business logic unless there is a separate goal.

## 9. Limitations of Generic Type Patterns

Not every cast can be converted directly into an `instanceof` check with arbitrary type arguments. Java generics have **type erasure**: at runtime, many parameterized types such as `List<String>` cannot be checked directly.

The following example **does not compile** when `input` has type `Object`:

```java
if (input instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

The reason is that `List<String>` is not a type that can be fully checked by `instanceof` in that context. Instead, you can check `List<?>` and process elements as needed:

```java
if (input instanceof java.util.List<?> values) {
    System.out.println(values.size());
}
```

Complete example `GenericCheckDemo.java`:

```java
import java.util.List;

public class GenericCheckDemo {
    static void handle(Object input) {
        if (input instanceof List<?> values) {
            System.out.println("size=" + values.size());
        } else {
            System.out.println("not-list");
        }
    }

    public static void main(String[] args) {
        handle(List.of("a", "b"));
        handle("other");
    }
}
```

```bash
javac --release 21 GenericCheckDemo.java
java GenericCheckDemo
```

Output:

```text
size=2
not-list
```

The `List<?>` check **does not verify that each element is a `String`**. If the logic requires `String`, continue checking each element or design the API with accurate generic types. Do not add an unchecked cast to `List<String>` just to change the syntax.

## 10. When to Use a Record Pattern Instead of a Type Pattern?

If a branch checks the type of a record and then calls multiple accessors to extract components, Java 21 lets you consider a **record pattern**. This is a **broader** refactoring step than simply removing a cast: it changes how components are accessed and requires careful attention to how the record, `null`, and accessors behave.

Example:

```java
record Point(int x, int y) {}

static void print(Object input) {
    if (input instanceof Point(var x, var y)) {
        System.out.println(x + y);
    }
}
```

`Point(var x, var y)` both matches the record type `Point` and deconstructs its two components using the record's accessors. `x` and `y` are inferred as `int`. For `null` or a mismatched type, `instanceof` returns `false`.

Note: **type patterns for `instanceof` became standard in Java 16**, whereas **record patterns became standard in Java 21** (JEP 440). If you target Java 17 compatibility, use `input instanceof Point point` and call `point.x()`, `point.y()`; do not put record patterns into source code that needs to compile with `--release 17`.

Custom-defined record accessors can have side effects or throw exceptions; a record pattern is not merely replacing a cast with a new variable name. If you want to strictly preserve the behavior of a legacy branch, prefer the direct **type pattern** step first before considering deconstruction.

## 11. Cases Where You Should Not Refactor Mechanically

1. **Changing the checked type.** Turning `instanceof Number` into `instanceof Integer` changes which cases are accepted.
2. **Moving method calls.** If the source expression or code in the branch has side effects, changing its position can alter the result.
3. **Deleting the `else` path.** Handling for non-matching types is still part of the method's contract.
4. **Using the pattern variable out of scope.** A pattern variable is only in scope where matching is guaranteed to have succeeded.
5. **Merging `&&` into an `if` that has an `else` without reviewing the conditions.** A failing business condition can cause the `else` branch to run differently from the old version.
6. **Trying to use `List<String>` with `instanceof` on `Object`.** Type erasure prevents checking generic type arguments that way.
7. **Creating a variable name that collides with an existing local variable.** Choose a new, clear name that avoids scope collisions.
8. **Assuming a pattern creates a copy of the data.** The pattern variable references the matched object; a mutable object remains the same instance.
9. **Treating a syntax refactoring as a reason to change `null` or exception handling.** Preserve behavior first, and improve behavior in a separate change if needed.
10. **Converting an entire `if/else if` chain into a `switch` unnecessarily.** For a single type-check branch, `instanceof T t` is usually a small, easy-to-review change.

## 12. Testing Needed After Refactoring

A single-branch refactoring usually does not require complex tests if structural equivalence can be shown and existing checks pass. However, for critical business code, clear test cases are recommended:

| Input | Expected branch | Purpose |
| --- | --- | --- |
| Object of exact type `T` | `if` branch | Pattern variable has the right value |
| Object of a subtype of `T` | `if` branch | Condition was not narrowed |
| Object of wrong type | `else` branch or skip `if` | No mistaken cast |
| `null` | Non-matching branch | `instanceof` does not match `null` |
| Valid edge value, e.g., empty string | Type branch, then business condition | Secondary condition semantics unchanged |
| Source expression with side effects | Compare call counts before/after | Detect unintended changes |

In a code review, a concrete diff is often enough to understand the change:

```diff
-if (value instanceof Account) {
-    Account account = (Account) value;
+if (value instanceof Account account) {
     send(account);
 }
```

`Account` and `send(...)` here are **illustrative names** for a class and method in a real project. In this case, if `value` is the same side-effect-free expression and the rest of the branch is unchanged, the logic handling `Account` objects does not change.

## 13. Application Checklist

Before finalizing the refactoring, verify each item in order:

- Is the type after `instanceof` **identical** to the previously checked type?
- Was the cast variable replaced by a clear, properly scoped pattern variable?
- Are the branch processing logic, `else`, and any `return`/`throw` statements preserved?
- Do `null`, subtypes, and wrong-type inputs still take the exact same paths as before?
- Is any expression evaluated **fewer or more times than before**?
- If `&&`, `||`, or negation is used, does the compiler prove the variable is matched at every usage site?
- If the code runs on Java 17, have you avoided record patterns introduced in Java 21?

**Remember:** for a classic single type-check branch, the core transformation is **`if (x instanceof T) { T t = (T) x; ... }` → `if (x instanceof T t) { ... }`**. The power of pattern matching lies in letting the compiler bind the variable based on the type-check result, while the safety of the refactoring depends on preserving control-flow paths and source-expression behavior.

## References

- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394)
- [Oracle Java SE 21 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof-operator.html)
- [Java Language Specification 21 — §15.20.2 Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Java Language Specification 21 — §6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
