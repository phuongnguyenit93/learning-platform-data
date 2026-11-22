# Distinguishing `true`, `false`, and `null` from Keywords in Java

## 1. Key point: literals are not keywords

In Java 17, **`true`** and **`false`** are the two *boolean literals* (direct constant values of type `boolean`); **`null`** is the *null literal* (a special value representing no reference to an object).

They are easily mistaken for keywords because their spellings are reserved by the language and **cannot be used as identifier names**. However, according to Java's lexical classification, all three are **literals, not keywords**.

| Sequence in source | Classification | Type/meaning | Usable as a variable name? |
|---|---|---|---|
| `true` | Boolean literal | `boolean` true value | No |
| `false` | Boolean literal | `boolean` false value | No |
| `null` | Null literal | Null value, convertible to an appropriate reference type | No |
| `boolean` | Keyword | Primitive boolean type name | No |
| `if`, `else` | Keywords | Control flow constructs | No |
| `class`, `return` | Keywords | Class declaration / returning a result | No |
| `Boolean` | Class name in `java.lang` | Wrapper object for boolean | Can be used to reference the class; **not a keyword** |

**Remember:** Do not say "`true` is a keyword of the `boolean` type." The accurate statement is "`true` is a **boolean literal**; `boolean` is a **keyword** used to write the primitive type name."

## 2. Boolean literals: `true` and `false`

Declaring and assigning values:

~~~java
boolean loggedIn = true;
boolean suspended = false;

if (loggedIn && !suspended) {
    System.out.println("ALLOW");
} else {
    System.out.println("DENY");
}
~~~

The output is `ALLOW`. In this snippet:

- `boolean` is a keyword for the data type.
- `true` and `false` are literals, not variable names.
- `loggedIn` and `suspended` are two programmer-chosen identifiers.
- `if` and `else` are keywords, while the expression `loggedIn && !suspended` produces a `boolean` value.

**Java does not treat integers as booleans.** The following snippets have syntax/type errors:

~~~java
// boolean ready = 1;    // Invalid: int does not implicitly convert to boolean
// if (1) { }            // Invalid: if requires a boolean condition
// boolean done = "true"; // Invalid: String is not boolean
~~~

If you receive the string `"true"` from input, it is still a **`String`**, not a boolean literal in source code. You can convert it with an appropriate API, such as `Boolean.parseBoolean("true")`.

### Case sensitivity

Java is case-sensitive:

- Exact lowercase `true` and `false` are literals.
- `True`, `False`, `TRUE`, and `FALSE` **are not automatically literals**. They can be identifiers if validly declared, or cause an undeclared-name error.
- `Boolean.TRUE` and `Boolean.FALSE` are **fields of the `Boolean` class**, not the literal syntax `true` and `false` themselves.

Example:

~~~java
boolean ready = true;
boolean approved = Boolean.TRUE;  // Unboxing from Boolean to boolean
// boolean wrong = True;         // Error if there is no variable/field named True
~~~

In Java applications, use `true`/`false` directly when you need a `boolean` value; use `Boolean` when an object type is required by an API contract.

## 3. `null`: no reference, not the string "null"

`null` can be assigned to variables of an appropriate **reference type**:

~~~java
String name = null;
Integer score = null;
int[] numbers = null;
Object object = null;
~~~

A reference variable holding `null` means it **references no object** at that moment. This does not mean an object is deleted immediately, nor is it a special `String` object.

Compare:

~~~java
String missing = null;
String text = "null";

System.out.println(missing == null); // true
System.out.println(text == null);    // false
System.out.println("null".equals(text));    // true
System.out.println("null".equals(missing)); // false
~~~

`"null"` is a four-character string, completely different from the **null literal**.

**You cannot assign `null` to primitive types** such as `int` and `boolean`:

~~~java
// int count = null;         // Compile-time error
// boolean enabled = null;   // Compile-time error
~~~

A `Boolean` variable can accept `null` because `Boolean` is a wrapper class (a reference type); a `boolean` variable only has two values: `true` or `false`.

### Type of the `null` expression

According to the Java specification, the null literal has a special **null type** (which has no type name to declare directly). A null value can convert to reference types, yet not every Java expression can infer a type from `null` alone:

~~~java
String label = null;   // Valid
Object value = null;   // Valid
// var unknown = null; // Invalid: var cannot infer an appropriate type
~~~

Do not confuse **the type of the null literal** with a class named `Null`: Java has no standard class named `Null` representing a "null object".

## 4. Null checks and avoiding NullPointerException

A common null check is:

~~~java
String userName = null;
boolean hasName = userName != null && !userName.isBlank();
System.out.println(hasName); // false
~~~

`&&` has **short-circuiting**: if `userName != null` is `false`, the JVM does not evaluate `!userName.isBlank()`. As a result, no method is invoked through a null reference.

Conversely:

~~~java
// String userName = null;
// System.out.println(userName.length()); // Throws NullPointerException
~~~

The snippet above is **valid at compile time** but throws `NullPointerException` when executed. This is a runtime error, not proof that `null` is a keyword.

Safer string content comparison with a literal:

~~~java
String state = null;
System.out.println("ACTIVE".equals(state)); // false
~~~

In cases comparing two potentially null objects, `java.util.Objects.equals(a, b)` can be appropriate. It returns `true` when both are null, or when two non-null values are considered equal according to `equals`.

**Trap:** `instanceof` with a null value yields `false`:

~~~java
String s = null;
System.out.println(s instanceof String); // false
~~~

A variable declared as type `String` can still hold null; `instanceof` does not conclude that a null value is an instance of `String`.

## 5. When a Boolean wrapper holds null: careful with unboxing

Java has two easily confused types:

| Type | Nature | Values it can hold |
|---|---|---|
| `boolean` | Primitive type | `true`, `false` |
| `Boolean` | Reference type (wrapper) | `Boolean` object or `null` |

Example:

~~~java
Boolean answer = null;
// if (answer) { } // Type-valid, but causes NullPointerException on unboxing
~~~

An `if` condition can accept a `Boolean` thanks to **auto-unboxing**, yet if the reference is `null`, converting to `boolean` triggers a `NullPointerException`.

Two expressions with different meanings:

~~~java
Boolean answer = null;

boolean definitelyTrue = Boolean.TRUE.equals(answer); // false
boolean hasValue = answer != null;                    // false
~~~

The first is only true if the wrapper holds the value true; the second only checks **whether a value is present**, regardless of whether that value is true or false.

If business logic has three states ("true, false, unknown"), `Boolean` allows representing all three, though how null is handled must be clearly defined. Do not arbitrarily treat null as false: in many situations, "unknown" is completely different from "false".

## 6. Runnable Java 17 demo: observing all three literals

Create a file **`LiteralDemo.java`**:

~~~java
public final class LiteralDemo {
    private LiteralDemo() {}

    static class Defaults {
        boolean ready; // Defaults to false
        String note;   // Defaults to null
    }

    public static void main(String[] args) {
        boolean enabled = true;
        boolean blocked = false;
        String name = null;
        String word = "null";
        Boolean optional = null;

        System.out.println("enabled = " + enabled);
        System.out.println("blocked = " + blocked);
        System.out.println("name == null: " + (name == null));
        System.out.println("\"null\" == null: " + (word == null));
        System.out.println("word equals null text: " + "null".equals(word));
        System.out.println("name is nonblank: "
                + (name != null && !name.isBlank()));
        System.out.println("Boolean.TRUE.equals(optional): "
                + Boolean.TRUE.equals(optional));
        System.out.println("optional == null: " + (optional == null));
        System.out.println("parseBoolean(TRUE): "
                + Boolean.parseBoolean("TRUE"));
        System.out.println("parseBoolean(yes): "
                + Boolean.parseBoolean("yes"));
        System.out.println("null instanceof String: "
                + (name instanceof String));

        Defaults defaults = new Defaults();
        System.out.println("default ready: " + defaults.ready);
        System.out.println("default note is null: "
                + (defaults.note == null));

        if (enabled && !blocked) {
            System.out.println("decision: ALLOW");
        }
    }
}
~~~

With **JDK 17 or newer**, open a terminal in the file's directory.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 LiteralDemo.java
java -cp . LiteralDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\LiteralDemo.java
java -cp . LiteralDemo
~~~

Expected output:

~~~text
enabled = true
blocked = false
name == null: true
"null" == null: false
word equals null text: true
name is nonblank: false
Boolean.TRUE.equals(optional): false
optional == null: true
parseBoolean(TRUE): true
parseBoolean(yes): false
null instanceof String: false
default ready: false
default note is null: true
decision: ALLOW
~~~

Further explanation on `Boolean.parseBoolean(String)`: the result is `true` only when the input string represents `"true"` (case-insensitive). Other strings such as `"yes"`, `"1"`, and even null return `false`, **without throwing an input error**. Therefore, if business logic must reject invalid input, you need to validate allowed strings rather than merely calling `parseBoolean`.

### Default values do not apply to every variable

In `Defaults`, the field `boolean ready` defaults to `false`, while the reference field `String note` defaults to `null`. This is Java's **field initialization** rule.

**Local variables** inside a method cannot be arbitrarily read before being definitely assigned:

~~~java
// Inside a method:
// boolean flag;
// System.out.println(flag); // Compile error: local variable is not initialized
~~~

Do not deduce that because a boolean field defaults to false, every local boolean variable is also pre-assigned false.

## 7. Invalid expressions and how to read their errors

The **intentionally invalid** examples below should not be placed in the main runnable file:

~~~java
// boolean a = True;       // Name True is not declared (if no such identifier exists)
// int x = null;           // null cannot convert to int
// boolean ok = null;      // null cannot convert to primitive boolean
// var item = null;        // Cannot infer type from null alone
// int true = 1;           // true is a boolean literal, not a variable name
// String null = "x";      // null literal is not a variable name
// int class = 1;          // class is a keyword
~~~

| Error | Phase | Nature |
|---|---|---|
| Using `true` as a variable name | Compile | Literals cannot serve as identifiers |
| Using `class` as a variable name | Compile | Keywords cannot serve as identifiers |
| Assigning `null` to `int` | Compile | Null does not convert to primitives |
| `var x = null` | Compile | Cannot infer an appropriate type |
| Calling `name.length()` when name is null | Runtime | `NullPointerException` |
| Auto-unboxing a null `Boolean` | Runtime | `NullPointerException` |
| Passing `"yes"` to `parseBoolean` | Runs per API | Returns false; needs validation if invalid data should be reported |

The compiler does not automatically determine the business meaning of `null`. With real APIs, ask whether null means "no data", "not yet entered", or "error", then choose an appropriate data model and validation.

## 8. Do not confuse booleans with conditions and three-state values

`true`/`false` are **values**; `if`/`while` are **control-flow keywords**, while the part inside parentheses must produce a valid boolean expression.

~~~java
boolean paid = true;
if (paid) {
    System.out.println("Da thanh toan");
}
~~~

Here:

- `paid` is an identifier, and `true` is a literal assigned to the variable.
- `if` is a keyword; `paid` is a boolean condition.
- `"Da thanh toan"` is a string literal used for printing, not a boolean value.

Java has no **third primitive boolean value** representing null. When you need an "unknown" state alongside true/false, you can use an explicit model such as an enum:

~~~java
enum ApprovalState {
    APPROVED, REJECTED, UNKNOWN
}
~~~

An enum avoids guessing what `null` means; however, it is only worth using when the domain truly has three states and processing flows need to distinguish them.

## 9. Edge cases worth remembering

**1. `null == null` is true.** Both sides are the null literal, so reference comparison applies and yields `true`. However, this does not turn null into an object on which methods can be invoked.

**2. `"false"` differs from `false`.** The string `"false"` is a `String`, while `false` is a `boolean`. You cannot write `boolean valid = "false";` and expect Java to cast it automatically.

**3. `Boolean.FALSE` is not null.** `Boolean.FALSE` is a wrapper object representing false; if a `Boolean` field is null, the missing-value state must be checked separately.

**4. `== null` is suitable for checking whether a reference exists.** However, do not use `==` by default to compare the **contents** of two non-null `String` objects; usually use `equals`.

**5. `null` can cause overload ambiguity.** If there are two overloads without a clear enough type relationship, such as `work(String)` and `work(Integer)`, calling `work(null)` may cause a compile error because both accept null yet neither is unambiguously better. You can cast `work((String) null)` if intended.

**6. Watch out for `switch` with null in Java 17.** A traditional switch expression/statement receiving a null reference selector typically throws `NullPointerException` upon evaluation. Do not assume null goes to the `default` branch; check for null beforehand or use techniques suited to the Java version and requirements.

**7. Null does not automatically mean "data permanently does not exist".** A variable currently holding null can be assigned another reference later if reassignment is allowed. Being null is a state of a **reference value**, not an immutable label on an object itself.

## 10. Short exercises with answers

### Exercise A — lexical classification

Classify the tokens `boolean`, `true`, `false`, `null`, `if`, and `Boolean`.

**Answer:** `boolean` and `if` are keywords; `true`/`false` are boolean literals; `null` is the null literal; `Boolean` is a wrapper class name in `java.lang` (not a keyword).

### Exercise B — valid or error?

~~~java
boolean x = false;
Boolean y = null;
String z = "null";
~~~

**Answer:** all three declarations are valid. `x` is primitive false, `y` is a null reference, and `z` is a non-null string containing the text `null`.

### Exercise C — predict the output

~~~java
String s = null;
System.out.println(s == null);
System.out.println("abc".equals(s));
System.out.println(s instanceof String);
~~~

**Answer:**

~~~text
true
false
false
~~~

There is no method call through `s`, so no `NullPointerException` occurs.

### Exercise D — choose how to avoid an unboxing error

~~~java
Boolean flag = null;
// if (flag) System.out.println("ON");
~~~

**Answer:** `if (flag)` will cause `NullPointerException` when Java auto-unboxes the null value. If the intent is to allow only true, write `if (Boolean.TRUE.equals(flag)) { ... }`. If null means "unconfirmed", handle it explicitly instead of silently treating it as false.

### Exercise E — API accepting user string input

An application only accepts `true` or `false` (case-insensitive). A user enters `yes`. Should `Boolean.parseBoolean("yes")` be used and treated as valid input?

**Answer:** No. `parseBoolean("yes")` returns false per the API; if the system requires **accepting only those two strings**, validate beforehand and reject `yes` with an appropriate message.

## 11. Self-check checklist

- [ ] Correctly state that `true`/`false` are **boolean literals** and `null` is the **null literal**; do not call them Java keywords.
- [ ] Distinguish the keyword `boolean` from the literals `true` and `false`.
- [ ] Understand that `Boolean` is a wrapper class, distinct from primitive `boolean`.
- [ ] Know that `null` is not the string `"null"` and cannot be assigned to `int`/`boolean`.
- [ ] Do not use the three literals `true`, `false`, `null` as variable names.
- [ ] Use `== null`, `!= null && ...`, and `"literal".equals(value)` for their intended purposes.
- [ ] Distinguish compile errors (invalid types) from runtime `NullPointerException`.
- [ ] Know that primitive boolean fields default to false and reference fields default to null, whereas local variables must be assigned before being read.
- [ ] Successfully run `LiteralDemo.java` with `javac`/`java` and verify the output.
- [ ] Do not treat a passing test run as proof that null carries the same meaning across all business domains.

**Conclusion:** **`true` and `false` are `boolean` literals; `null` is the null literal; none of the three are Java keywords**, even though they are reserved and cannot be used as identifiers. Keywords like `boolean`, `if`, and `class` form language structure; literals represent values. Understanding this classification helps you read code accurately, avoid type errors, and handle null deliberately.