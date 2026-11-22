# Comprehensive Practice: Reproducing `null`, Overload, `intern`, and String-Number Concatenation Pitfalls

## 1. Goal and how to study

This practice asks you to **predict the output before running**, then verify on Java 17+ to recognize four common pitfall groups:

1. **`null`**: a null reference can be concatenated into the text `"null"`, throw `NullPointerException`, or make an overload call ambiguous.
2. **Overload**: Java selects the method based on the **compile-time type of the expression**, not by inspecting the object's runtime class to pick a new overload.
3. **String pool and `intern()`**: `==` checks **same object reference**, whereas `equals()` checks **same content**. Literals and constant expressions follow different sharing rules than runtime-created strings.
4. **Concatenation with numbers and `char`**: `+` is both numeric addition and string concatenation; evaluation order and parentheses change the result.

Each section includes code, expected predictions, explanations, and safe idioms. Do not run lines marked **compile error** together with runnable code, as they illustrate invalid cases. For examples that throw runtime exceptions, wrap calls in `try/catch` if you want subsequent statements to keep executing.

## 2. The `null` pitfall: string concatenation is not like calling a method

`String` is a **reference type**. A `String` variable can hold a `null` reference, meaning it **points to no `String` object**. This differs from an empty string `""`.

~~~java
String missing = null;
String empty = "";

System.out.println(missing == null); // true
System.out.println(empty == null);   // false
System.out.println(empty.isEmpty()); // true
~~~

### 2.1. Concatenating with `null` produces the text `"null"`

In a string concatenation context, a `null` reference is converted into the text `"null"`:

~~~java
String value = null;

System.out.println("id=" + value); // id=null
System.out.println(value + "!");   // null!
~~~

This **does not mean** the `value` variable holds a four-character string object `n-u-l-l`. It is still a `null` reference; concatenation merely builds a new string value for display.

If you do not want the text `null` printed to the UI, handle missing data intentionally:

~~~java
String label = value == null ? "(none)" : value;
System.out.println("id=" + label); // id=(none)
~~~

This is safe when the business convention is replacing `null` with an explicit placeholder. If `null` is invalid data that must be rejected, detect and report an error at the appropriate boundary instead of silently substituting it.

### 2.2. Calling a method on `null` throws `NullPointerException`

~~~java
String value = null;

// value.length();           // NullPointerException at runtime
// value.concat("!");        // NullPointerException at runtime
// value.equals("ready");    // NullPointerException at runtime
~~~

Conversely, calling a method on a real object can safely compare against a `null` reference:

~~~java
String value = null;

System.out.println("ready".equals(value)); // false
System.out.println(java.util.Objects.equals(value, "ready")); // false
System.out.println(java.util.Objects.equals(null, null)); // true
~~~

Therefore, with a string constant and a nullable variable, `"ready".equals(value)` is usually safe and readable. When both sides may be `null`, `Objects.equals(a, b)` provides null-safe content comparison.

Distinguish the semantics clearly: `Objects.equals(null, null)` returns `true` because **both references are `null`**, not because two string objects exist with equal content.

### 2.3. `String.valueOf(null)` has an overload trap

`String.valueOf` has several overloads, including:

~~~java
String.valueOf(Object obj)
String.valueOf(char[] data)
~~~

Two calls that look nearly identical behave differently:

~~~java
System.out.println(String.valueOf((Object) null)); // null

try {
    String.valueOf((char[]) null);
} catch (NullPointerException ex) {
    System.out.println("char[] null => NPE");
}
~~~

When passing `(Object) null`, `valueOf(Object)` returns the string `"null"`. When passing `(char[]) null`, the char-array overload attempts to access the array and throws `NullPointerException`.

An even more interesting trap:

~~~java
// String.valueOf(null);
~~~

This line **compiles**, yet Java selects `valueOf(char[])`, because `char[]` is a subtype of `Object` and is the more specific overload among the applicable candidates. The result is a **`NullPointerException` at runtime**.

When you want a `null` reference converted into `"null"`, write explicitly:

~~~java
String text = String.valueOf((Object) null);
~~~

Or if you want a fallback value:

~~~java
String text = java.util.Objects.toString(null, "(empty)");
// (empty)
~~~

Practical takeaway: **do not guess from the method name alone**. Check which overload is chosen based on argument types.

## 3. Overload traps: Java decides at compile time

A class can have multiple methods with the same name but different parameter lists:

~~~java
static String classify(Object value) {
    return "Object";
}

static String classify(String value) {
    return "String";
}
~~~

When called:

~~~java
System.out.println(classify("Java")); // String
System.out.println(classify(null));   // String
System.out.println(classify((Object) null)); // Object
~~~

Explanation:

- The string `"Java"` has type `String`, so the `String` overload is the most specific match.
- The `null` literal is convertible to any reference type; `String` is more specific than `Object`, so the `String` overload is selected.
- `(Object) null` has **compile-time expression type `Object`**, so the `Object` overload is selected.

`classify` above is a `static` method in an illustrative example. Even for instance overloads, Java still determines the **method signature** from compile-time types; *overriding* is a separate mechanism that dispatches based on the actual object type at runtime.

### 3.1. Two overloads with no more-specific type: compile error

~~~java
static String inspect(String value) {
    return "String";
}

static String inspect(Integer value) {
    return "Integer";
}

// System.out.println(inspect(null)); // COMPILE ERROR: ambiguous
~~~

`String` and `Integer` are not subtypes of one another. The `null` literal applies to both, so the compiler cannot choose a better overload. Fix by stating your intent explicitly:

~~~java
System.out.println(inspect((String) null));  // String
System.out.println(inspect((Integer) null)); // Integer
~~~

Casting here **only guides overload resolution**; it creates no new object and does not turn `null` into string content. If the real method dereferences the parameter without a null check, it can still throw an exception.

### 3.2. Why does `System.out.println(null)` cause ambiguity?

`PrintStream` has overloads including:

~~~java
println(String x)
println(char[] x)
println(Object x)
~~~

The call:

~~~java
// System.out.println(null); // COMPILE ERROR: ambiguous
~~~

Both `String` and `char[]` are more specific than `Object`, yet neither is more specific than the other. The compiler cannot choose.

The following calls have unambiguous meaning:

~~~java
System.out.println((String) null); // null
System.out.println((Object) null); // null
~~~

Meanwhile:

~~~java
// System.out.println((char[]) null); // NullPointerException at runtime
~~~

The difference is that the char-array overload expects to read **the elements of the array**, rather than simply converting an object reference to text.

### 3.3. `StringBuilder.append(null)` has a similar trap

`StringBuilder` has multiple overloads for `String`, `CharSequence`, `Object`, and `char[]`, among other types.

~~~java
// new StringBuilder().append(null); // COMPILE ERROR: ambiguous
~~~

An uncast `null` call can match reference overloads that cannot be ordered by "most specific". Specify the desired type and behavior explicitly:

~~~java
System.out.println(new StringBuilder().append((String) null));
// null

System.out.println(new StringBuilder().append((Object) null));
// null
~~~

Passing a null array to `append(char[])` throws `NullPointerException` at runtime. This clearly illustrates the rule: **a compile-time ambiguous overload error and a runtime exception from passing `null` to a chosen method are two distinct kinds of errors**.

## 4. String pool, `intern()`, and two kinds of equality

In Java:

- `a == b`, when `a` and `b` are object references, checks whether they hold **the same reference**.
- `a.equals(b)` on two non-null strings checks **equal string content**.
- `String` is immutable; two distinct objects can easily hold identical content.

### 4.1. Literals and `new String()`

~~~java
String a = "java";
String b = "java";
String c = new String("java");

System.out.println(a == b);      // true
System.out.println(a == c);      // false
System.out.println(a.equals(c)); // true
~~~

`"java"` literals in the same Java environment are interned/shared per language rules, so `a` and `b` point to the same pooled string object. `new String("java")` explicitly allocates a new `String` object; `c` has the same content but not the same reference as `a`.

Use `equals()` when checking status codes, usernames, product names, menu choices, or values read from APIs/files/databases:

~~~java
if ("ACTIVE".equals(status)) {
    // Handle when status content equals "ACTIVE".
}
~~~

Do not use `status == "ACTIVE"` to compare business values because the outcome can depend on whether the object happened to be shared.

### 4.2. `intern()` returns the canonical reference in the string pool

~~~java
String literal = "java";
String created = new String("java");

System.out.println(created == literal);          // false
System.out.println(created.intern() == literal); // true
System.out.println(created.equals(literal));     // true
~~~

`intern()` returns a canonical reference for that content from the *string pool*. If the pool already contains a string with equal content, `intern()` returns that existing string's reference; otherwise, canonical reference management follows JVM rules.

Do not overuse `intern()` as a "trick to speed up every comparison." Putting many distinct strings into the pool can increase memory pressure and management overhead; effectiveness depends on value repetition, lifetime, and application requirements. `equals()` remains the proper API for content comparison even when one or both strings are interned.

### 4.3. Constant folding vs runtime concatenation

Distinguish constant expressions from expressions involving variables:

~~~java
String literal = "java";
String folded = "ja" + "va";

String part = "ja";
String runtime = part + "va";

System.out.println(literal == folded);  // true
System.out.println(literal == runtime); // false
System.out.println(literal.equals(runtime)); // true
~~~

`"ja" + "va"` is a **constant expression**, so the compiler can fold it into the `"java"` literal and use the interned reference. `part + "va"` is runtime concatenation; the resulting object has identical content but does not automatically become a pooled reference merely because its content matches a literal.

If `part` is an eligible **compile-time constant variable**:

~~~java
final String part = "ja";
String value = part + "va";
System.out.println(value == "java"); // true
~~~

Because `part` is a `final String` initialized with a constant expression, this concatenation is also a compile-time constant. Do not generalize that **every `final` variable creates a constant expression**: if its value comes from a method call or runtime input, it does not become a compile-time constant simply from the `final` keyword.

**Practical rule:** predict `==` to understand pooling mechanics; in application code, use `equals()` or `Objects.equals()` to compare values.

## 5. The `+` operator with numbers: left-to-right order decides the result

The `+` operator plays two roles:

- When both operands are eligible for numeric addition, Java performs **numeric addition** per numeric promotion rules.
- When either operand is a `String`, Java performs **string concatenation**, converting the other operand into a text representation.

Additive/concatenation operators share the same precedence and associate **left to right**. Parentheses alter grouping:

~~~java
System.out.println(1 + 2 + "3");   // 33
System.out.println("1" + 2 + 3);   // 123
System.out.println("1" + (2 + 3)); // 15
System.out.println((1 + 2) + "3"); // 33
~~~

Step-by-step explanation:

1. `1 + 2 + "3"`: `1 + 2` is numeric addition yielding `3`; then `3 + "3"` produces `"33"`.
2. `"1" + 2 + 3`: starts with a `String`, so `"1" + 2` becomes `"12"`; then `"12" + 3` becomes `"123"`.
3. `"1" + (2 + 3)`: the parenthesized expression yields `5` first, then concatenates into `"15"`.
4. `(1 + 2) + "3"` produces the same `"33"` content as the first example because the two numbers are added first.

With numeric variables:

~~~java
int price = 10;
int fee = 5;

System.out.println("Total: " + price + fee);   // Total: 105
System.out.println("Total: " + (price + fee)); // Total: 15
~~~

Parentheses clarify the intended addition. This is a program correctness bug, not a performance issue.

### 5.1. `char` plus a number: usually gives a numeric code, not the next letter

`char` is an unsigned 16-bit integer type. In numeric addition with `int`, `char` is promoted for arithmetic:

~~~java
System.out.println('A' + 1);     // 66
System.out.println("A" + 1);     // A1
System.out.println("char=" + 'A' + 1); // char=A1
~~~

`'A' + 1` does not print `B`: the expression has type `int` and value `65 + 1 = 66`. If you genuinely want the next character within an appropriate range:

~~~java
char next = (char) ('A' + 1);
System.out.println(next); // B
~~~

This is merely arithmetic on UTF-16 values and **is not** a general algorithm for incrementing "visible Unicode characters."

### 5.2. Concatenating with `null` and numbers together

~~~java
String missing = null;

System.out.println("x=" + missing + 1);  // x=null1
System.out.println("x=" + (1 + 2));      // x=3
System.out.println((Object) null + "3"); // null3
~~~

Use explicit parentheses and null-substitution rules. For example, `"x=" + (missing == null ? 0 : Integer.parseInt(missing)) + 1` still concatenates `1` after starting with a `String`; to compute the sum, wrap the entire addition: `"x=" + ((missing == null ? 0 : Integer.parseInt(missing)) + 1)`.

## 6. `StringBuilder.append()` also distinguishes data types

`StringBuilder` has many overloads; output can vary depending on the expression passed in:

~~~java
StringBuilder a = new StringBuilder();
a.append('A').append(1);
System.out.println(a); // A1

StringBuilder b = new StringBuilder();
b.append('A' + 1);
System.out.println(b); // 66
~~~

In case `a`, `append(char)` outputs the letter `A` and `append(int)` appends the digit `1`. In case `b`, the addition `'A' + 1` executes **before `append` is called**, producing the integer `66`, so the `append(int)` overload prints `66`.

Use two separate calls when appending a character and a number, and explicit addition when computing a sum:

~~~java
String message = new StringBuilder()
        .append("Result: ")
        .append(1 + 2)
        .toString();
// Result: 3
~~~

For a few fixed parts, `"Result: " + (1 + 2)` is even shorter. Do not replace `+` with `StringBuilder` merely to dodge operator-precedence pitfalls: both require expressing intent accurately.

## 7. Complete runnable Java 17+ program

Create the file **`StringPitfallsDemo.java`**:

~~~java
import java.util.Objects;

public class StringPitfallsDemo {
    static String classify(Object value) {
        return "Object";
    }

    static String classify(String value) {
        return "String";
    }

    static String inspect(String value) {
        return "String";
    }

    static String inspect(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        String missing = null;
        System.out.println("plus null: " + ("id=" + missing));
        System.out.println("safe equals: " + "ok".equals(missing));
        System.out.println("both null: " + Objects.equals(null, null));

        System.out.println(
                "valueOf(Object): " + String.valueOf((Object) null));

        try {
            String.valueOf((char[]) null);
        } catch (NullPointerException ex) {
            System.out.println("valueOf(char[]): NPE");
        }

        System.out.println("overload(null): " + classify(null));
        System.out.println(
                "overload((Object)null): " + classify((Object) null));
        System.out.println(
                "inspect((String)null): " + inspect((String) null));

        // Do not uncomment: these are ambiguous overload compile errors.
        // inspect(null);
        // System.out.println(null);
        // new StringBuilder().append(null);

        String literal = "java";
        String created = new String("java");
        System.out.println("literal == new: " + (literal == created));
        System.out.println(
                "literal equals new: " + literal.equals(created));
        System.out.println(
                "intern identity: " + (literal == created.intern()));

        String folded = "ja" + "va";
        String part = "ja";
        String runtime = part + "va";
        System.out.println("folded identity: " + (literal == folded));
        System.out.println("runtime identity: " + (literal == runtime));
        System.out.println(
                "runtime equality: " + literal.equals(runtime));

        System.out.println("numeric first: " + (1 + 2 + "3"));
        System.out.println("string first: " + ("1" + 2 + 3));
        System.out.println("grouped: " + ("1" + (2 + 3)));
        System.out.println("char plus int: " + ('A' + 1));
        System.out.println("char then string: " + ("A" + 1));

        StringBuilder builder = new StringBuilder();
        builder.append('A').append(1);
        System.out.println("builder: " + builder);
    }
}
~~~

Compile and run:

~~~bash
javac StringPitfallsDemo.java
java StringPitfallsDemo
~~~

Output:

~~~text
plus null: id=null
safe equals: false
both null: true
valueOf(Object): null
valueOf(char[]): NPE
overload(null): String
overload((Object)null): Object
inspect((String)null): String
literal == new: false
literal equals new: true
intern identity: true
folded identity: true
runtime identity: false
runtime equality: true
numeric first: 33
string first: 123
grouped: 15
char plus int: 66
char then string: A1
builder: A1
~~~

### Why are these the results?

- `missing` is a null reference, concatenated into the text `null`; yet `"ok".equals(missing)` remains `false` without invoking a method on `null`.
- `Objects.equals(null, null)` compares two `null` values and returns `true`.
- `String.valueOf((Object) null)` produces `"null"`, whereas `String.valueOf((char[]) null)` throws `NullPointerException` via the array overload.
- `classify(null)` selects the `String` overload as more specific than `Object`; casting `(Object) null` shifts selection to the `Object` overload.
- `inspect(null)` is commented out because `String` and `Integer` have no specificity relation; adding a cast chooses the desired overload.
- Literals, constant concatenation expressions, and `intern()` refer to the same pool reference; `new String(...)` and runtime concatenation create distinct objects in this example, though `equals()` compares content as `true` for all of them.
- The `+` expressions produce `33`, `123`, and `15` according to addition/concatenation grouping.
- `'A' + 1` yields the number `66`; `"A" + 1` yields `"A1"`; `append('A').append(1)` also yields `A1`.

## 8. Prediction and self-check exercises

Write down your predictions for **value**, **result type**, and whether an error happens at **compile time** or **runtime** before reading the answers.

### Exercise 1: `null` and `equals`

~~~java
String x = null;
System.out.println("x=" + x);
System.out.println("go".equals(x));
System.out.println(x == null);
~~~

**Answer:** `x=null`, `false`, `true` respectively. `"go".equals(x)` invokes on a non-null literal, while `== null` checks the reference.

### Exercise 2: `null` and overloads

~~~java
// A
String.valueOf((Object) null);

// B
String.valueOf((char[]) null);

// C
String.valueOf(null);
~~~

**Answer:** A returns `"null"`; B throws `NullPointerException`; C **compiles yet also throws `NullPointerException`** because it chooses the `char[]` overload. This is an easy place to confuse `valueOf(Object)` and `valueOf(char[])`.

### Exercise 3: ambiguous overloads

~~~java
static void f(String x) {}
static void f(Integer x) {}

// f(null);
~~~

**Answer:** `f(null)` fails to compile because both overloads apply and neither is more specific. `f((String) null)` and `f((Integer) null)` are valid for overload resolution.

### Exercise 4: comparing `String`s

~~~java
String x = "ab";
String y = "a" + "b";
String p = "a";
String z = p + "b";

System.out.println(x == y);
System.out.println(x == z);
System.out.println(x.equals(z));
~~~

**Answer:** `true`, `false`, `true`. `y` is a constant expression; `z` is created by runtime concatenation.

### Exercise 5: numeric addition or string concatenation?

~~~java
System.out.println(10 + 5 + " USD");
System.out.println("USD " + 10 + 5);
System.out.println("USD " + (10 + 5));
~~~

**Answer:** `15 USD`, `USD 105`, `USD 15`. Parentheses determine whether the two numbers are added first or converted to strings sequentially.

### Exercise 6: `char` and `StringBuilder`

~~~java
System.out.println('0' + 1);

StringBuilder sb = new StringBuilder();
sb.append('0').append(1);
System.out.println(sb);
~~~

**Answer:** `49` and `01`. `'0'` has numeric code `48`; `'0' + 1` is numeric addition. Two `append` calls sequentially append a character and a digit.

### Exercise 7: two different error kinds

~~~java
// System.out.println(null);     // A
// System.out.println((char[]) null); // B
~~~

**Answer:** A does not compile due to ambiguity between `String` and `char[]` overloads. B explicitly chooses the `char[]` overload but throws `NullPointerException` at runtime. Casting handles **overload selection**; it does not make passing `null` valid.

### Exercise 8: `final` and constant expressions

~~~java
final String a = "ja";
String x = a + "va";
String y = "java";
System.out.println(x == y);
~~~

**Answer:** `true`. `a` is a compile-time constant variable of type `String`, initialized with a constant expression; concatenating with `"va"` is also a constant expression. This rule does not apply to `final` variables whose values are only known at runtime.

## 9. Distinguishing compile-time errors, runtime errors, and logic errors

| Case | Outcome | Cause |
|---|---|---|
| `String.valueOf(null)` | `NullPointerException` at runtime | Selects `char[]` overload, more specific than `Object` |
| `String.valueOf((Object) null)` | String `"null"` | Selects `Object` overload |
| `System.out.println(null)` | Compile error | `String` and `char[]` overloads are ambiguous |
| `new StringBuilder().append(null)` | Compile error | Reference overloads have no unique most-specific choice |
| `missing.length()` when `missing == null` | `NullPointerException` | Calling a method on a `null` reference |
| `new String("java") == "java"` | `false` | Two distinct objects |
| `new String("java").equals("java")` | `true` | Equal content |
| `"Total: " + 10 + 5` | `"Total: 105"` | Left-to-right string concatenation |
| `"Total: " + (10 + 5)` | `"Total: 15"` | Numeric addition inside parentheses first |
| `'A' + 1` | `int` `66` | Numeric addition and numeric promotion |

The most important debugging skill is classifying properly:

- **Compile-time error:** the JVM has not run the program yet; adjust casts or signatures so the compiler knows which overload to invoke.
- **Runtime exception:** the code compiled, but a `null` reference was used illegally; check data and contracts.
- **Logic bug:** code runs without crashing yet yields wrong results, such as using `==` for content equality or forgetting parentheses when adding numbers.

Never use `try/catch` to "fix" an ambiguous overload error: that error occurs before the program can run.

## 10. Writing safe code in real projects

### 10.1. Compare content with `equals`

~~~java
boolean accepted = "OK".equals(status);
boolean same = java.util.Objects.equals(firstName, secondName);
~~~

This reduces `NullPointerException` risk from calling `equals` on a potentially `null` reference. To test reference identity for object-identity purposes, `==` remains appropriate; the issue is misusing it for string content comparison.

### 10.2. Handle `null` per business requirements

~~~java
String displayName = java.util.Objects.toString(userName, "(anonymous)");
~~~

If `null` represents missing data that needs a message, supply a meaningful fallback. If an input must never be `null`, validate at the boundary, e.g., using `Objects.requireNonNull` with a clear message.

### 10.3. Clarify overloads with types and names

When overloading could cause ambiguity with `null` literals, it is often better to design APIs with distinct method names for distinct behaviors if that improves clarity:

~~~java
static String fromText(String text) {
    return text == null ? "" : text;
}

static String fromNumber(Integer number) {
    return number == null ? "" : number.toString();
}
~~~

If overloads are kept, pass variables with clear static types or appropriate casts; do not add arbitrary casts merely to silence compiler warnings.

### 10.4. Use explicit parentheses for arithmetic

~~~java
int quantity = 2;
int unitPrice = 50;

String total = "Total: " + (quantity * unitPrice);
~~~

Even though `*` has higher precedence than `+`, parentheses help readers separate arithmetic from string concatenation. With mixed additions, parentheses determine correctness:

~~~java
String totalWithFee = "Total: " + (quantity * unitPrice + 10);
~~~

### 10.5. Understand `intern` without relying on it

There is no need to manually intern every string just to compare values:

~~~java
String source = new String("READY");
boolean sameContent = "READY".equals(source); // true
~~~

`equals` preserves exact semantics whether strings come from files, HTTP, databases, newly allocated objects, or the string pool. If memory optimization for many duplicate strings is required, measure and design specifically for it; never turn assumptions about pooled references into business logic.

## 11. Debugging checklist for surprising results

When encountering a Java `String` expression:

1. **Determine each expression's compile-time type.** With `null`, ask which overloads apply and which is most specific.
2. **Determine whether `null` is a data value or an absent reference.** `+` concatenation, `String.valueOf`, and method calls may behave differently.
3. **Ask whether you are comparing references or content.** `==` is reference identity; `equals` is content equality.
4. **Determine when the string was created.** Literals/constant expressions and runtime concatenation differ in interning rules.
5. **Add parentheses to make addition explicit.** A single `String` operand turns subsequent `+` into string concatenation.
6. **Read the compiler error before editing.** An ambiguous overload is a signature-selection error, completely different from `NullPointerException`.
7. **Run a minimal program with deterministic output.** Verify value, type, and error cases; do not infer solely from API names.
8. **Write tests guarding behavior.** `null` values, empty strings, literals/`new String`, compile-time constants, numbers, and `char` should each have test cases.

## 12. Key takeaways

All four pitfall groups share one root cause: **similar-looking syntax triggers different Java rules depending on types, context, and when values are created**.

- `null` in concatenation can become `"null"`; calling a method on `null` can throw `NullPointerException`.
- Overload resolution uses **compile-time argument types**; casting clarifies selection but does not fix `null` data.
- `intern()` and constant folding concern **shared objects**; to compare `String` content, use `equals()`.
- `+` performs both numeric addition and string concatenation; left-to-right order and parentheses decide the output.

The most effective way to learn is predicting **whether it compiles, what it prints if it runs, and why**, then checking against Java 17+ examples before applying these rules in larger programs.