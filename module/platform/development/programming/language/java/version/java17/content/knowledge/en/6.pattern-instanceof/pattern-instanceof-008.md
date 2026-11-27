# Reassigning Pattern Variables and Scope Limits in Java 17

**Topic:** Java 17 → Pattern instanceof  
**Focus:** Whether a pattern variable can be reassigned; where the variable name is visible after an `instanceof` check; how scope changes across `if`, `else`, `!`, `&&`, `||`, the ternary operator, and early-exit branches.

**Pattern matching for `instanceof` has been a standard feature since Java 16**, so it works directly in Java 17 without `--enable-preview`. In the standard release, variables declared via a type pattern **are no longer implicitly `final`**. However, they still follow special scoping rules based on **control flow** (*flow scoping*).

This article covers only **type patterns with `instanceof` in Java 17**. It does not use pattern matching for `switch` because that syntax was still in *preview* in Java 17; nor does it use pattern forms added in later Java versions.

## 1. What Is a Pattern Variable?

Before pattern matching, a type-check-and-cast operation was typically written as:

~~~java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

With Java 17, you can combine the type check and variable declaration:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

In the expression `value instanceof String text`:

- `value` is the expression being checked.
- `String` is the type to match against.
- `text` is the **pattern variable**, initialized when the object matches the type.
- Wherever `text` is in valid scope, code can directly use `String` methods without manual casting.

When `value` is `null`, `instanceof String text` evaluates to `false`, creating no execution path where `text` is assigned a value.

Variable `text` does not become a member of `value`, is not a global variable, and does not exist in every branch of the method. It is a **local variable introduced by the pattern**.

## 2. Can a Pattern Variable Be Reassigned?

**Yes.** In Java 17, a pattern variable declared by `instanceof` is **not implicitly `final`**. As long as the right-hand expression is compatible with the variable's type, you can assign another value to the variable within its valid scope.

Example:

~~~java
Object value = "  Hello Java  ";

if (value instanceof String text) {
    System.out.println(text); // Has leading/trailing whitespace.

    text = text.strip();       // Valid in Java 17.

    System.out.println(text); // Hello Java
}
~~~

Variable `text` initially references the checked string. After `text = text.strip()`, it references the normalized string. **Reassigning `text` does not automatically reassign `value`.**

### 2.1. Limits when reassigning

A pattern variable has the **static type** written in the pattern. Therefore:

~~~java
Object item = "A";

if (item instanceof String text) {
    text = "B";                   // Valid: String -> String.
    text = text.toLowerCase();    // Valid: returns String.

    // text = 123;                // Wrong: int cannot be assigned to String.
    // text = new Object();       // Wrong: Object cannot be assigned to String.
}
~~~

Java still enforces normal assignment type rules. You cannot use reassignment to "turn" a `String` pattern into an `Integer` pattern.

**`null` can be assigned** to a reference-typed pattern variable, unless constrained otherwise by the program or static analysis tools:

~~~java
Object value = "Hello";

if (value instanceof String text) {
    text = null;  // Syntactically and type-wise valid in Java.

    // text.length();  // Compiles, but throws NullPointerException if executed.
}
~~~

This shows that the initial check verifies the object **at match time**, rather than guaranteeing the variable remains non-`null` or still refers to the original object after subsequent assignments. Do not assign `null` to a pattern variable merely to test a logic branch; the example above illustrates the feature's boundaries.

### 2.2. Reassigning a pattern variable vs. mutating the object

Distinguish between:

| Operation | What changes | Does it change the original checked variable? |
| --- | --- | --- |
| `text = text.strip()` | Reference value of pattern variable `text`. | Not automatically. |
| `builder.append("!")` with pattern `StringBuilder builder` | State of the referenced **object**. | The original variable can observe the change because both point to the object. |
| `value = anotherObject` | Reference value of `value`. | Yes, this directly assigns to the original variable. |

Example of mutating an object:

~~~java
Object value = new StringBuilder("Java");

if (value instanceof StringBuilder builder) {
    builder.append(" 17");
    System.out.println(builder); // Java 17
}

System.out.println(value);       // Java 17
~~~

`append` mutates the contents of the `StringBuilder` rather than assigning a new reference to `builder`. Both `value` and `builder` reference the same object inside that branch.

### 2.3. Why do many older sources say pattern variables are `final`?

Earlier preview releases before the feature was finalized had different rules. When **JEP 394** finalized pattern matching for `instanceof` in Java 16, the "pattern variables are implicitly `final`" restriction was removed for better consistency with ordinary local variables. Thus, when learning **Java 17**, the explanation that "pattern variables cannot be reassigned" is outdated information.

The rule "can be reassigned" **does not mean** "should be reassigned frequently." For code that needs to stay readable or pass the variable into a lambda, a separate result variable is often preferable.

## 3. Flow Scoping: Scope Depends on Execution Paths

A regular local variable declared via `String text = ...` is scoped by block structure. A pattern variable differs in that **an execution path must prove the match succeeded** before the variable name can be used.

The Java Language Specification calls this mechanism **flow scoping**: the compiler determines the locations where the pattern variable is *definitely matched*.

Example:

~~~java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // Valid: true branch.
} else {
    System.out.println("Not a String");

    // System.out.println(text); // Wrong: text is not in scope here.
}

// System.out.println(text);     // Wrong: after if, text is not guaranteed to exist.
~~~

**Reason:** if the `instanceof` condition is `false`, the `else` branch runs while the `String text` pattern has never matched. After the `if` statement, execution may likewise have come through the `else` branch. The compiler disallows accessing `text` at those positions.

### Basic scope table

| Construct | Where the pattern variable can be used | Where it cannot be used by default |
| --- | --- | --- |
| `if (o instanceof String s)` | Inside the `true` branch. | The `else` branch, or after the entire `if` if both paths continue. |
| `if (o instanceof String s && condition(s))` | Right-hand side of `&&` and `true` branch. | The `else` branch or after a regular `if`. |
| `if (o instanceof String s \|\| otherCondition)` | Cannot use `s` in the `true` branch just because the overall expression is true. | Right-hand side of `\|\|` and the `true` branch of this expression. |
| `if (!(o instanceof String s))` | The `else` branch when the negated condition is false. | The `true` branch of the negated condition. |
| `if (!(o instanceof String s)) return/throw;` | Code continuing after the guard clause. | The guard branch before exiting. |
| `o instanceof String s ? s.trim() : "N/A"` | Second branch of the ternary operator (after `?`). | The branch after `:`. |

For complex expressions, trace all paths execution can take, rather than only looking at curly braces.

## 4. Combining with `&&`: Scope Extends to the Right-Hand Side

The `&&` operator in Java **short-circuits**: it evaluates the right-hand side only if the left-hand side is `true`. Therefore:

~~~java
Object input = "Java 17";

if (input instanceof String text && text.length() >= 5) {
    System.out.println(text.toUpperCase());
}
~~~

The right-hand side `text.length() >= 5` only runs when `input instanceof String text` is `true`. There `text` is assigned and has type `String`, so Java permits using the variable.

Conditions can be extended:

~~~java
if (input instanceof String text
        && !text.isBlank()
        && text.length() <= 100) {
    System.out.println(text.strip());
}
~~~

Inside the **`true` branch**, all three conditions hold. However, if any condition is `false`, you cannot deduce that the first match succeeded, so `text` cannot be used in `else` by default.

### Common mistake: reversing the condition order

~~~java
Object input = "Java 17";

// Wrong: text is not declared/matched on the left-hand side.
// if (text.length() > 0 && input instanceof String text) {
//     System.out.println(text);
// }
~~~

**Order matters:** the type check must precede expressions using the pattern variable.

## 5. Combining with `||`: When Is the Variable Not Guaranteed Assigned?

The `||` operator also short-circuits, but its right-hand side only runs when the left-hand side is **`false`**. Thus the following pattern is invalid:

~~~java
Object input = "Java 17";
boolean allowOtherTypes = true;

// Wrong: when the left-hand side is false, the right-hand side can still run
// even though input is not a String.
// if (input instanceof String text || allowOtherTypes) {
//     System.out.println(text.length());
// }
~~~

Even when **the entire condition is true**, that could be due to `allowOtherTypes`, not `input instanceof String text`. Variable `text` is not guaranteed assigned inside the `if` branch.

**Memory tip:**

- With `A && B`, to reach `B`, `A` **must be true**.
- With `A || B`, to reach `B`, `A` **must be false**.

Therefore, a pattern introduced when `instanceof` is `true` fits the right-hand side of `&&`; the pattern `o instanceof T t || ...` does not allow using `t` on the right-hand side as if the match were guaranteed.

### Using negation with `||` in a valid way

You can write a *guard clause* checking whether a value **is not a string or is a blank string**:

~~~java
static String requireText(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Need a non-blank string");
    }

    // Here the if condition was false: input is a String and not blank.
    return text.strip();
}
~~~

Why is `text.isBlank()` on the right-hand side of `||` valid? To evaluate the right-hand side, `!(input instanceof String text)` must be `false`. From that it follows that the `String text` match **succeeded**.

This is an important case: **not every expression containing `||` is wrong**. Scope depends on which boolean outcome guarantees the match succeeded.

## 6. Negation `!` and Early-Exit Branches

Consider the expression:

~~~java
if (!(value instanceof String text)) {
    // value did NOT match String; text cannot be used here.
} else {
    // Negation is false => value matched String.
    System.out.println(text.length());
}
~~~

Negation `!` flips the `true` and `false` meanings of the condition. The `else` branch here is where `text` can be used.

### 6.1. Guard clauses let you use the variable after `if`

A practical, clear pattern in Java 17:

~~~java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }

    // All paths reaching here matched String.
    text = text.strip();
    return text;
}
~~~

The `if` branch **cannot complete normally** because it always throws an exception when entered. If execution reaches `text = text.strip()`, the match definitely succeeded. Hence `text` is in scope for the remainder of the block.

You can use `return` instead of `throw`:

~~~java
static int textLengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
~~~

Compare with a case that **does not exit early**:

~~~java
static void printIfText(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Not a string");
    }

    // Wrong if uncommented: the if branch can finish and continue.
    // System.out.println(text.length());
}
~~~

Merely negating the condition with `!`, **without `throw`/`return` or another construct guaranteeing exit**, is not enough to extend the variable's scope to subsequent code.

### 6.2. Control-flow diagram

~~~text
                    input instanceof String text?
                             /          \
                         true            false
                          |                |
                 text is assigned    text is not assigned
                          |                |
                 use text validly    cannot use text

  if (!(...)) throw ...;           // Failure branch is blocked.
  use text here                    // Only the matched path remains.
~~~

Java infers scope **from the paths that can reach a statement**, not from hoping the input will usually be a string.

## 7. The Ternary Operator `?:` and Variable Scope

A pattern variable can be used in the corresponding branch of a conditional expression:

~~~java
static String label(Object value) {
    return value instanceof String text
            ? text.strip()
            : "Not a string";
}
~~~

The branch after `?` is evaluated only when the match condition is `true`, so `text` can be used. The branch after `:` has no such guarantee:

~~~java
// Wrong: in the false branch, the pattern did not match.
// String label = value instanceof String text
//         ? "String"
//         : text.toUpperCase();
~~~

With a negated condition, the corresponding scope can lie in the branch after `:`:

~~~java
static String normalizedOrDefault(Object value) {
    return !(value instanceof String text)
            ? "N/A"
            : text.strip();
}
~~~

**Note:** the ternary operator does not automatically "export" the pattern variable into the scope of subsequent statements, because the expression itself can complete via different branches.

## 8. With `while` and `for`: Scope in the Condition and Loop Body

A pattern variable's scope can also include a loop body if the condition proves the match succeeded.

Example `while` loop:

~~~java
Object current = "Java";

while (current instanceof String text && !text.isEmpty()) {
    System.out.println(text);
    current = null; // Next check no longer matches String.
}

// Cannot use text here by default.
// System.out.println(text);
~~~

Each time the loop body runs, `current` must match `String`, so `text` is valid. After the loop, it cannot be inferred that the last check matched; hence `text` cannot be used afterward by default.

For basic `for` loops, the same principle applies:

~~~java
Object current = "data";

for (; current instanceof String text && !text.isBlank(); current = null) {
    System.out.println(text.toUpperCase());
}
~~~

Because of the `instanceof` condition in the middle clause, `text` can be used in the update section and loop body at positions Java confirms have definitely matched. The example only uses `current` in the update section for simple termination. Do not assume `text` is in scope in **all** parts of a `for` statement, especially the initialization section before the condition.

## 9. Variable Scope and Name Collisions

One benefit of *flow scoping* is that a pattern variable name can be reused across independent branches, provided **no two declarations with the same name share overlapping scopes**.

### 9.1. Reusing a name after the previous scope has ended

~~~java
static void printTwo(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println("A: " + text);
    }

    if (second instanceof String text) {
        System.out.println("B: " + text);
    }
}
~~~

The two declarations of `text` in separate `instanceof` expressions are valid in this structure, because the pattern variable of the first `if` branch is **not in scope** in the second `if` expression.

### 9.2. Cannot shadow a local variable currently in scope

~~~java
static void conflict(Object value) {
    String text = "already exists";

    // Wrong: local variable text is already in this scope.
    // if (value instanceof String text) {
    //     System.out.println(text);
    // }
}
~~~

To fix it, rename the pattern variable:

~~~java
static void noConflict(Object value) {
    String text = "already exists";
    if (value instanceof String parsedText) {
        System.out.println(parsedText);
    }
    System.out.println(text);
}
~~~

### 9.3. Do not declare the same pattern name on both sides of a compound condition

The following example is **invalid**:

~~~java
Object a = "A";
Object b = "B";

// Wrong: two patterns both declare name s in a combined expression.
// if ((a instanceof String s) && (b instanceof String s)) {
//     System.out.println(s);
// }
~~~

Use distinct names when you need both objects:

~~~java
if (a instanceof String first && b instanceof String second) {
    System.out.println(first + " - " + second);
}
~~~

The example works because `first` and `second` are differently named pattern variables, confirmed matched along the path to the `if` body.

## 10. Reassigning Pattern Variables and Lambdas: `effectively final`

Just because a pattern variable **can be reassigned** does not mean it can always be *captured* by a lambda. Java requires local variables used inside a lambda to be `final` or **effectively final**, meaning they are never reassigned after initialization under language rules.

Valid case:

~~~java
static Runnable printer(Object value) {
    if (value instanceof String text) {
        return () -> System.out.println(text);
    }
    return () -> System.out.println("Not a string");
}
~~~

Variable `text` is never reassigned, so it satisfies the effectively final requirement.

Conversely:

~~~java
static Runnable invalidPrinter(Object value) {
    if (value instanceof String text) {
        text = text.strip();

        // Wrong: text was reassigned, no longer effectively final.
        // return () -> System.out.println(text);
    }
    return () -> {};
}
~~~

Even though `text = text.strip()` itself is **valid**, that assignment disqualifies `text` from being captured by the lambda.

A clearer approach:

~~~java
static Runnable normalizedPrinter(Object value) {
    if (value instanceof String text) {
        String normalized = text.strip();
        return () -> System.out.println(normalized);
    }
    return () -> System.out.println("Not a string");
}
~~~

Variable `normalized` receives only one value and is not reassigned, so the lambda can use it. This also separates **the initially checked object** from **the transformed value**.

## 11. Complete Example: Scope, Guard Clauses, and Reassignment

Create the file **`PatternScopeDemo.java`** with the contents below. The program uses only stable Java SE 17 APIs without preview features:

~~~java
public class PatternScopeDemo {
    static String describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            // Pattern variables can be reassigned in Java 17.
            text = text.strip();
            return "String: " + text;
        }

        if (input instanceof Integer number) {
            return "Integer: " + number;
        }

        return "Unsupported or blank string";
    }

    static String requireText(Object input) {
        if (!(input instanceof String text)) {
            throw new IllegalArgumentException("Need a String value");
        }

        // Valid outside if because the non-matching path exited.
        String normalized = text.strip();
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("String must not be blank");
        }

        return normalized;
    }

    static String compactLabel(Object input) {
        return input instanceof String text
                ? text.toUpperCase()
                : "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java 17  "));
        System.out.println(describe(42));
        System.out.println(describe("  "));
        System.out.println(requireText("  ready  "));
        System.out.println(compactLabel("pattern"));
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 PatternScopeDemo.java
java PatternScopeDemo
~~~

Expected output:

~~~text
String: Java 17
Integer: 42
Unsupported or blank string
ready
PATTERN
~~~

Points to examine in the program:

1. In `describe`, `text` is only used after `input instanceof String text` succeeds; `&&` allows calling `text.isBlank()` directly in the condition.
2. Reassigning `text = text.strip()` is valid and only affects the pattern variable within that scope.
3. The `Integer number` branch uses an independent pattern variable, unrelated to `text` in the branch above.
4. In `requireText`, if the match fails, `throw` terminates the path. After `if`, `text` is definitely assigned and allowed to be used.
5. In `compactLabel`, the pattern variable only appears in the corresponding branch of the `?:` operator.

## 12. Common Mistakes and Fixes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `s` in `else` of `if (o instanceof String s)`. | `else` runs when the match failed. | Read the original variable, handle the other case, or write a suitable negated branch. |
| Using `s` after an `if` whose non-matching branch still continues. | On the next line, `s` is not guaranteed assigned. | Use `s` inside the matching branch or write an early-exit guard clause. |
| `o instanceof String s \|\| s.isEmpty()`. | The right-hand side of `\|\|` is evaluated when the left-hand side is false. | Use `&&`, or intentional negation like `!(o instanceof String s) \|\| s.isEmpty()`. |
| Assigning `s = 123` when `s` is `String`. | Type-incompatible assignment. | Assign a value of a compatible type or create another variable. |
| Reassigning `s` and then capturing `s` in a lambda. | No longer effectively final. | Create a new variable that is not reassigned for lambda capture. |
| Declaring pattern `s` with the same name as a local variable still in scope. | Name collision; the pattern cannot shadow that local variable. | Rename the pattern or reorganize the code block. |
| Thinking `value instanceof String s` turns `value` into a `String` variable. | The pattern creates a **new** variable `s` without changing the declared type of `value`. | Use `s` when you need `String` methods. |
| Thinking pattern `s` is always non-`null` after any statement. | `s` can be reassigned, including to `null`. | Avoid arbitrary reassignment; use a clear normalized variable. |

### Another case to avoid: type checks already known at compile time

Java 17 does not allow an unconditional `instanceof` pattern check when the source expression's type is already a subtype of the target pattern type:

~~~java
String value = "Java";

// Wrong in Java 17: value already has type String.
// if (value instanceof String text) {
//     System.out.println(text);
// }

// Use value directly:
System.out.println(value.length());
~~~

In examples needing dynamic type checks, use a value with a broader static type, such as `Object`, a common interface, or an appropriate superclass. This is the current rule of the standard Java 17 release; do not copy old preview examples.

## 13. How to Choose: Reassign or Create a New Variable?

Suppose the pattern matched and you need to normalize the string:

**Approach 1 — reassign directly:**

~~~java
if (input instanceof String text) {
    text = text.strip();
    process(text);
}
~~~

Suitable if the scope is short, the original value is not needed, and `text` does not need to be used inside a lambda.

**Approach 2 — create a new result variable:**

~~~java
if (input instanceof String text) {
    String normalized = text.strip();
    process(normalized);
}
~~~

Suitable if you want to preserve the original reference, distinguish raw data from normalized data, or prepare the variable for use in a lambda. The second approach is generally easier for readers to follow when processing logic is long.

> Both snippets above assume a `process(String)` method exists in the application context. They are illustrative snippets, not standalone programs.

Do not stretch a condition chain just to keep a pattern variable usable at a distant location. For complex logic, extract a method with a clear name, expressing both the checked condition and avoiding scope conflicts.

## 14. Self-Practice on Scoping

Given an `Object input` variable holding an arbitrary value, predict where the name `text` can be used:

**Scenario A:**

~~~java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
~~~

**Answer:** `text` is valid on the right-hand side of `&&` and inside the `if` branch when the entire condition is true.

**Scenario B:**

~~~java
if (input instanceof String text || input == null) {
    // System.out.println(text); // Invalid.
}
~~~

**Answer:** `if` can run because `input == null`, so `text` is not guaranteed to be assigned.

**Scenario C:**

~~~java
if (!(input instanceof String text)) {
    return;
}
System.out.println(text);
~~~

**Answer:** `text` is valid on the last line when the snippet is inside a `void` method; the non-matching branch returned, so all remaining paths matched.

**Scenario D:**

~~~java
if (input instanceof String text) {
    text = text.toUpperCase();
    // Runnable action = () -> System.out.println(text);
}
~~~

**Answer:** the reassignment is valid; the commented lambda line is invalid because `text` is no longer effectively final.

**Scenario E:**

~~~java
if (input instanceof String text) {
    System.out.println(text);
}
if (input instanceof Integer number) {
    System.out.println(number);
}
~~~

**Answer:** both branches are valid. `text` and `number` belong to separate scopes tied to their respective matches. Neither variable automatically becomes usable everywhere after the two `if` statements.

## 15. Official References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): describes the standard feature and the change removing `implicitly final` for pattern variables.
- [Java SE 17 Language Changes — Oracle](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html): milestone finalizing pattern matching for `instanceof` in Java 16 and applicability when using Java 17.
- [Java Language Specification 17 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): foundation of variable scoping rules.
- [Java Language Specification 17 §6.3.1 — Scope for Pattern Variables in Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1): rules for `&&`, `||`, `!`, ternary operator, and `instanceof`.
- [Java Language Specification 17 §6.3.2 — Scope for Pattern Variables in Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.2): scoping rules for `if`, loops, and other statements.
- [Java Language Specification 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): rules for `final` and `effectively final`, relevant to lambda capture of local variables.

**Core principle:** In Java 17, a pattern variable **can be reassigned if type-compatible**, but is only **in scope where control flow proves the match succeeded**. When reading code, trace each `true`/`false` branch, especially before and after `&&`, `||`, and early-exit statements.
