# Boolean Literals in Java 17+

## 1. What is a boolean literal?

A **boolean literal** is a true or false value written directly in Java source code. Java has only **two boolean literals**:

- `true`: logical true value.
- `false`: logical false value.

Both have the primitive type **`boolean`**. They must be written **strictly in lowercase**. `True`, `FALSE`, or `TRUE` are not boolean literals.

~~~java
boolean available = true;
boolean soldOut = false;
~~~

In the snippet above, `boolean` is a type keyword; `available` and `soldOut` are identifiers; `true` and `false` are **literals**, not keywords or variable names.

Specifically, `true` and `false` cannot be used as identifier names:

~~~java
// int true = 1;  // Compile error: true cannot be a variable name
// int false = 0; // Compile error
~~~

**Do not confuse literals with character strings:** `"true"` and `"false"` have type `String`, not `boolean`.

## 2. The boolean type has only two values

A variable of primitive type `boolean` can only hold `true` or `false`, or an expression that evaluates to `boolean`:

~~~java
boolean connected = true;
boolean ready = connected;
boolean adult = 20 >= 18;
boolean eligible = connected && adult;
~~~

The following declarations are **invalid**:

~~~java
// boolean a = 1;       // int does not automatically convert to boolean
// boolean b = 0;       // int does not automatically convert to boolean
// boolean c = "true";  // String does not automatically convert to boolean
// boolean d = null;    // null cannot be assigned to primitive boolean
~~~

Unlike some other languages, Java **has no rule that treats 0 as false and non-zero numbers as true**. Therefore:

~~~java
// if (1) { } // Does not compile: if condition must have type boolean
if (true) {
    System.out.println("Nhanh dung");
}
~~~

The `if (true)` snippet prints `Nhanh dung`; `if (false)` has a valid body, but does not execute its body at runtime.

## 3. Boolean literals and boolean expressions

Literals provide values directly, whereas expressions can **compute** a boolean value from other operands.

| Expression | Type | Result | Reason |
|---|---|---|---|
| `true` | `boolean` | `true` | Literal |
| `false` | `boolean` | `false` | Literal |
| `5 > 3` | `boolean` | `true` | Numeric comparison |
| `10 == 7` | `boolean` | `false` | Two different values |
| `!false` | `boolean` | `true` | Negation |
| `true && false` | `boolean` | `false` | AND operation |
| `true \|\| false` | `boolean` | `true` | OR operation |
| `true ^ true` | `boolean` | `false` | XOR: two identical values |

Variables can also hold the result of an expression:

~~~java
int score = 75;
boolean passed = score >= 50;
boolean excellent = score >= 90;

System.out.println(passed);    // true
System.out.println(excellent); // false
~~~

Not every `boolean` value needs to be written as a literal: a comparison, a method like `String.isBlank()`, or a method call you write can also produce a `boolean`.

## 4. Logical operations on booleans

The three most frequently used operators:

- `!` (NOT) flips `true` to `false` and vice versa.
- `&&` (AND) returns `true` only if **both sides** are `true`.
- `||` (OR) returns `true` if **at least one side** is `true`.

| `a` | `b` | `!a` | `a && b` | `a \|\| b` | `a ^ b` |
|---|---|---|---|---|---|
| false | false | true | false | false | false |
| false | true | true | false | true | true |
| true | false | false | false | true | true |
| true | true | false | true | true | false |

`^` is the **XOR** operation on two booleans: true when **the two operands differ**.

When combining multiple conditions, use parentheses to express intent clearly:

~~~java
boolean authenticated = true;
boolean active = true;
boolean blocked = false;

boolean canEnter = authenticated && active && !blocked;
System.out.println(canEnter); // true
~~~

Avoid overly long expressions that are hard to verify. Naming intermediate variables keeps the logic closer to requirements and easier to read.

## 5. `&&` and `||` are short-circuiting

**Short-circuit evaluation** means Java skips the right-hand side when the left-hand side is already enough to decide the result:

- `false && something()`: does not call `something()` because the result is guaranteed to be `false`.
- `true || something()`: does not call `something()` because the result is guaranteed to be `true`.

One benefit is safely checking before accessing a potentially null value:

~~~java
String name = null;
boolean hasName = name != null && !name.isBlank();
System.out.println(hasName); // false, does not throw an error
~~~

Once `name != null` is `false`, Java **does not evaluate** `name.isBlank()`.

On two boolean operands, `&` and `|` also perform AND/OR, but **evaluate both sides** without short-circuiting. Therefore, replacing `&&` with `&` in the null example above can cause a `NullPointerException`.

### Seeing the right-hand side skipped for yourself

~~~java
static boolean trace(String message, boolean result) {
    System.out.println(message);
    return result;
}

// Inside a method:
boolean first = false && trace("RIGHT_1", true);
boolean second = true || trace("RIGHT_2", false);
System.out.println(first);  // false
System.out.println(second); // true
~~~

The two strings `RIGHT_1` and `RIGHT_2` **are not printed** because the `trace` calls on the right-hand side never take place. This matters when the right-hand side is a resource-intensive method call or has side effects.

**Recommendation:** do not rely on side effects from the right-hand side of `&&`/`||` when the logic requires them to **always run**. Extract mandatory actions into separate statements.

## 6. Runnable Java 17 example

Create the file **`BooleanLiteralDemo.java`** with all of the following content:

~~~java
public final class BooleanLiteralDemo {
    private BooleanLiteralDemo() {}

    static final class Settings {
        boolean enabled; // Primitive field has default value false
    }

    static boolean canAccess(
            boolean loggedIn, boolean verified, boolean blocked) {
        return loggedIn && verified && !blocked;
    }

    static boolean hasVisibleText(String text) {
        return text != null && !text.isBlank();
    }

    static boolean trace(String label, boolean value) {
        System.out.println("evaluated: " + label);
        return value;
    }

    public static void main(String[] args) {
        boolean enabled = true;
        boolean paused = false;

        System.out.println("literal true: " + enabled);
        System.out.println("literal false: " + paused);
        System.out.println("negation: " + !enabled);
        System.out.println("comparison: " + (5 > 3));
        System.out.println("allow: " + canAccess(true, true, false));
        System.out.println("blocked: " + canAccess(true, true, true));

        System.out.println("null valid: " + hasVisibleText(null));
        System.out.println("blank valid: " + hasVisibleText("   "));
        System.out.println("name valid: " + hasVisibleText("Lan"));

        boolean skippedAnd = false && trace("AND right", true);
        boolean skippedOr = true || trace("OR right", false);
        System.out.println("short AND: " + skippedAnd);
        System.out.println("short OR: " + skippedOr);

        System.out.println("parse TRUE: "
                + Boolean.parseBoolean("TRUE"));
        System.out.println("parse yes: "
                + Boolean.parseBoolean("yes"));
        System.out.println("default field: " + new Settings().enabled);
    }
}
~~~

Compile and run with **JDK 17 or newer**, from the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 BooleanLiteralDemo.java
java -cp . BooleanLiteralDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\BooleanLiteralDemo.java
java -cp . BooleanLiteralDemo
~~~

**Expected output:**

~~~text
literal true: true
literal false: false
negation: false
comparison: true
allow: true
blocked: false
null valid: false
blank valid: false
name valid: true
short AND: false
short OR: true
parse TRUE: true
parse yes: false
default field: false
~~~

Notice: **there are no `evaluated:` lines** because both `trace` calls sit on the right-hand side skipped by short-circuiting. The result of `hasVisibleText(null)` is also safe thanks to `&&`.

The output above is the expected result for learners to run and verify themselves. No Maven, Gradle, or external libraries are needed.

## 7. Boolean literals differ from String and the Boolean wrapper

These three expressions have different meanings:

~~~java
boolean primitive = true;
String text = "true";
Boolean wrapper = Boolean.TRUE;
~~~

| Value | Type | Meaning |
|---|---|---|
| `true` | `boolean` | Boolean literal |
| `"true"` | `String` | Four-character string |
| `Boolean.TRUE` | `Boolean` | Constant field holding a wrapper object |
| `Boolean.parseBoolean("true")` | `boolean` | String conversion result |

For string inputs, you can use `Boolean.parseBoolean(text)`. You need to understand the API's contract clearly:

~~~java
System.out.println(Boolean.parseBoolean("true"));  // true
System.out.println(Boolean.parseBoolean("TRUE"));  // true
System.out.println(Boolean.parseBoolean("false")); // false
System.out.println(Boolean.parseBoolean("yes"));   // false
System.out.println(Boolean.parseBoolean(null));    // false
~~~

`parseBoolean` only returns `true` if the string represents `"true"` under a case-insensitive comparison. It **does not report an error** on other strings, returning `false` instead. If an application requires users to enter strictly `true` or `false`, you must validate input **before or outside** the `parseBoolean` call.

The wrapper class `Boolean` is a **reference type**, so a `Boolean` variable can hold `null`; primitive `boolean` cannot:

~~~java
Boolean optional = null;
// boolean invalid = null; // Does not compile
~~~

If you use `if (optional)`, Java attempts to **unbox** `Boolean` to `boolean`; when `optional` is `null`, this statement throws a `NullPointerException`. If you only want to check whether the value is true, you can use:

~~~java
Boolean optional = null;
boolean on = Boolean.TRUE.equals(optional); // false
~~~

Do not treat `null` as a "third boolean literal": the primitive `boolean` type only has `true` and `false`.

## 8. Default values and local variables

A primitive `boolean` **field** is default-initialized by Java to `false` when an object is created (or during class preparation for a static field).

~~~java
class Flags {
    boolean active;
}

Flags flags = new Flags();
System.out.println(flags.active); // false
~~~

However, a **local variable inside a method** must be definitely assigned before being read:

~~~java
// Inside a method:
// boolean ready;
// System.out.println(ready); // Compile error: might not have been initialized
~~~

Therefore, you must distinguish:

- The literal `false` is a value written in source code.
- A field's default value `false` is a Java initialization rule.
- A local `boolean` variable does not automatically allow reading a "default false" when unassigned.

## 9. Common mistakes when using boolean literals

| Code or behavior | Issue | Correct syntax |
|---|---|---|
| `boolean ready = True;` | `True` is not a literal; may cause undeclared name error | `boolean ready = true;` |
| `boolean ready = 1;` | Java does not treat `1` as true | Use `true` or a condition producing boolean |
| `if (1) { }` | Condition does not have type boolean | `if (count > 0) { }` |
| `boolean ready = "false";` | A string is not a boolean literal | Convert/validate input |
| `boolean ready = null;` | Primitive does not accept null | Use appropriate true/false |
| `if (flag = true)` | **Compiles**, but is an assignment, making the condition true | `if (flag)` when checking the value |
| `if (flag == true)` | Usually redundant | `if (flag)` |
| `if (flag == false)` | Can be replaced with a more readable form | `if (!flag)` |
| `Boolean.parseBoolean("yes")` returns false | The API does not treat "yes" as true | Validate if only true/false are accepted |
| `Boolean b = null; if (b)` | NPE during unboxing | Handle null intentionally |

### Dangerous bug: assignment in a condition

~~~java
boolean approved = false;
if (approved = true) {
    System.out.println("APPROVED");
}
System.out.println(approved); // true
~~~

This snippet is **valid** because the assignment expression `approved = true` has the boolean value `true`; however, it **modifies the variable** and can break business logic.

If you only want to check the current state, write `if (approved)`. When reviewing code, take care to distinguish the assignment operator `=` from the comparison operator `==`.

## 10. When should you use literals directly?

The two literals are useful when they clearly express intent:

~~~java
boolean featureEnabled = false; // Temporarily disable a feature
boolean hasPermission = true;   // Allow based on a verified condition
~~~

However, do not use `true` or `false` in place of mandatory checks:

~~~java
// Wrong for business logic without actual verification:
boolean authenticated = true;

// Better: result from a meaningful verification call
// boolean authenticated = verifyCredentials(user, password);
~~~

For methods returning a boolean, choose names that form a clear question:

~~~java
static boolean isAdult(int age) {
    return age >= 18;
}

static boolean isEven(int n) {
    return n % 2 == 0;
}
~~~

In `return age >= 18;`, there is no need to write the verbose form:

~~~java
// Unnecessary:
if (age >= 18) {
    return true;
} else {
    return false;
}
~~~

Returning the boolean expression directly is shorter and usually clearer. Still, if each branch has different business reasons or requires additional processing, `if/else` can remain appropriate.

## 11. Exercises with answers

### Exercise A — classify literals

Given `true`, `false`, `"true"`, `Boolean.TRUE`, `True`.

**Answer:** only `true` and `false` are boolean literals; `"true"` is a String literal; `Boolean.TRUE` is a field of the wrapper class; `True` is not a literal and is only valid if a corresponding identifier has been declared.

### Exercise B — predict expressions

~~~java
boolean a = true;
boolean b = false;
System.out.println(a && b);
System.out.println(a || b);
System.out.println(!a);
System.out.println(a ^ b);
~~~

**Answer:**

~~~text
false
true
false
true
~~~

### Exercise C — null-guard short-circuiting

~~~java
String value = null;
boolean ok = value != null && value.length() > 2;
System.out.println(ok);
~~~

**Answer:** prints `false`, does not throw `NullPointerException`, because the right-hand side of `&&` is not evaluated. If replaced with boolean `&`, the right-hand side is evaluated and the `length()` call throws an error.

### Exercise D — parseBoolean results

Predict `Boolean.parseBoolean("TRUE")`, `Boolean.parseBoolean("1")`, `Boolean.parseBoolean("false")`.

**Answer:** `true`, `false`, `false`, respectively. The API does not treat `1` as true by default.

### Exercise E — identify the logic bug

~~~java
boolean paid = false;
if (paid = true) {
    System.out.println("SHIP");
}
~~~

**Answer:** prints `SHIP` because the assignment sets `paid` to `true`. If you only want to ship when the variable was already true, fix it to `if (paid)` (and a real payment verification flow is needed).

## 12. Self-assessment checklist

- [ ] Know there are only two boolean literals in Java: `true` and `false`.
- [ ] Write them in lowercase and understand they are **not keywords**.
- [ ] Do not confuse `boolean`, `Boolean`, `"true"`, and the literal `true`.
- [ ] Understand that comparisons and logical operators produce expressions of type `boolean`.
- [ ] Use `!`, `&&`, `||`, `^` accurately.
- [ ] Explain why `&&`/`||` do not always evaluate their right-hand side.
- [ ] Know that `Boolean.parseBoolean` does not automatically report errors on unrecognized strings.
- [ ] Know that a boolean field defaults to false whereas a local variable must be assigned before reading.
- [ ] Avoid writing `if (flag = true)` when intending to test a value.
- [ ] Compile/run `BooleanLiteralDemo.java` on JDK 17+ and verify the results.

**Conclusion:** `true` and `false` are the two literals of type `boolean` used to represent true/false in Java code. The boolean type expresses conditions explicitly; Java does not automatically convert integers or strings into booleans. When using literals in expressions, you must understand logical operators, short-circuiting, and the difference between primitive `boolean` and the `Boolean` wrapper to avoid condition bugs and improper null handling.
