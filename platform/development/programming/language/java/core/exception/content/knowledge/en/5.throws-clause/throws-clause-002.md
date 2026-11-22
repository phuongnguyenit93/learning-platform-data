# Declaring One or Multiple Exception Types with the `throws` Clause in Java

## 1. Learning Objectives

A method can complete normally or terminate with an exception. In Java, the `throws` clause of a method or constructor tells readers and the compiler which **exception types** a call can propagate outward, especially *checked exceptions*.

After this lesson, you will be able to:

- Write the `throws` syntax correctly with **one** or **multiple** exception types, separated by commas.
- Distinguish the `throws` declaration clause from the `throw` statement.
- Understand how the compiler checks checked exceptions and how callers handle them with `try/catch` or propagate them with `throws`.
- Choose specific exception types or an appropriate supertype, avoiding overly broad declarations.
- Apply `throws` in methods, constructors, interface implementation methods, and overridden methods.
- Distinguish a `throws` list from `multi-catch` syntax, and recognize common compile-time errors.

The examples use Java 17+; many examples are standalone programs that can be run with `javac` and `java`.

## 2. What Is `throws` Used For?

In a method declaration, `throws` appears **after the parameter list and before the method body**:

```java
public String load() throws java.io.IOException {
    // Method body.
    return "data";
}
```

This is a method snippet. It declares that the method is **allowed to propagate** `IOException` outward. It does not mean every call will actually throw an exception. Not throwing an error inside the body of the example above is still valid.

General syntax:

```text
[modifiers] ReturnType methodName(parameters)
        throws ExceptionType1, ExceptionType2, ... {
    // statements
}
```

In the syntax above, `ExceptionType1` and `ExceptionType2` are type names, not objects. Each type must be a subclass of `Throwable` or a type variable with a compatible bound. In practice, subclasses of `Exception` are commonly used; Java still allows declaring unchecked types such as `IllegalArgumentException`.

Example declaring **one type**:

```java
void readFile() throws java.io.IOException {
    // Read a file; an API call inside may throw IOException.
}
```

Example declaring **multiple types**:

```java
void process() throws java.io.IOException, java.text.ParseException {
    // May fail while reading data or parsing content.
}
```

The two snippets above are **illustrative methods**, not standalone `main` programs. They show how to place types after `throws`, separated by **commas**. You can wrap lines between types for readability; line breaks do not change the meaning of the declaration.

### A `throws` List Is Not a List of Exceptions Guaranteed to Occur

- `throws IOException`: the method may allow an exception compatible with `IOException` to propagate out.
- `throws IOException, ParseException`: the method may propagate an exception from the I/O group or the parsing group (or exceptions matching those types) along **different execution paths**.
- A normal throw propagates **one `Throwable` object** at a time; a `throws` list does not require the method to throw all listed types.
- There is no required priority order among types in `throws`; changing the order of class names does not change the compiler's exception-checking rules.
- There is no requirement to list every possible `RuntimeException` or `Error` that might occur.

## 3. Distinguishing `throw` and `throws`

These serve two different roles: `throws IOException, ParseException` **lists two error types that can escape** in the signature, whereas `throw new ParseException("invalid", 0);` **throws a specific object** when the execution branch reaches that statement. `throws` does not create objects, log anything, or catch errors.

A key point of this lesson is the **listing syntax**: after `throws`, use a **comma** (`throws IOException, ParseException`); the `|` symbol is only used in multi-catch (`catch (IOException | ParseException ex)`). The caller must handle checked exceptions that can escape under the contract, even if most runs succeed. A deeper comparison between the throwing action and the declaration contract is practiced separately in the `throw` vs. `throws` lesson.

## 4. Why Must Checked Exceptions Be Caught or Declared?

Relevant hierarchy:

```text
Throwable
├── Error                         (unchecked)
│   └── ...
└── Exception
    ├── IOException               (checked)
    │   └── FileNotFoundException (checked)
    ├── ParseException            (checked)
    └── RuntimeException          (unchecked)
        ├── IllegalArgumentException
        └── NullPointerException
```

This is a simplified diagram of representative classes. An exception is **checked** when its type does not belong to the `RuntimeException` or `Error` branch of `Throwable`.

Basic rule: if a method/constructor body **can produce a checked exception** that is not handled locally, the `throws` declaration of the method/constructor must list that type or a suitable **supertype**.

The caller has two options:

1. **Catch and handle** it with `try/catch` when recovery is possible at that point.
2. **Continue declaring** it with `throws` to pass the responsibility for handling it up to the next caller.

Unchecked exceptions can be caught and can be declared, but the compiler **does not require** declaring or catching them.

For exception checking, a call to a method declared with `throws IOException` is treated as potentially throwing a checked exception of that type, even if a specific run never produces an error. Therefore, caller code must satisfy the contract based on the **signature visible at compile time**.

## 5. Declaring One Type: A Complete Runnable Program

Create the file **`SingleThrowsDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;

public class SingleThrowsDemo {
    static String firstLine(Reader source) throws IOException {
        try (BufferedReader reader = new BufferedReader(source)) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        String result = firstLine(new StringReader("alpha\nbeta"));
        System.out.println(result);
    }
}
```

Compile and run commands:

```bash
javac SingleThrowsDemo.java
java SingleThrowsDemo
```

Exact `stdout`:

```text
alpha
```

Explanation:

- `BufferedReader.readLine()` declares that it can throw `IOException`. Even though the source is a `StringReader` and the test case runs successfully, `firstLine` still must handle or declare the possibility of the checked exception from the API method it calls.
- `firstLine(...) throws IOException` chooses to **propagate the responsibility** of handling it to the caller.
- `main(...) throws IOException` continues the declaration, so the example compiles validly. If a checked exception actually escapes `main`, the program has no handler in this example code.
- `try-with-resources` closes `BufferedReader` and the wrapped source after use, even if reading fails; an error from `close()` is also subject to the corresponding exception-checking contract.

If you want to handle the error instead of propagating it:

```java
try {
    String line = firstLine(source);
    System.out.println(line);
} catch (java.io.IOException failure) {
    System.err.println("Cannot read data: " + failure.getMessage());
}
```

This is only an **illustrative snippet**, assuming the variable `source` is already validly declared and the `firstLine` method is available. `catch` should perform a useful action: returning a failure result, recording context, recovering, or rethrowing the cause, depending on the application.

## 6. Declaring Multiple Types: A Method with Different Error Paths

When processing has multiple failure possibilities that need to be distinguished, a `throws` list preserves specific information for the caller.

Create the file **`MultipleThrowsDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.text.ParseException;

public class MultipleThrowsDemo {
    static int readScore(Reader source)
            throws IOException, ParseException {
        try (BufferedReader reader = new BufferedReader(source)) {
            String line = reader.readLine();

            if (line == null) {
                throw new ParseException("missing score", 0);
            }

            try {
                return Integer.parseInt(line);
            } catch (NumberFormatException failure) {
                ParseException parsed =
                        new ParseException("invalid score", 0);
                parsed.initCause(failure);
                throw parsed;
            }
        }
    }

    public static void main(String[] args) {
        try {
            int score = readScore(new StringReader("85"));
            System.out.println("valid=" + score);
        } catch (IOException | ParseException failure) {
            System.out.println("unexpected="
                    + failure.getClass().getSimpleName());
        }

        try {
            readScore(new StringReader("bad"));
        } catch (IOException | ParseException failure) {
            System.out.println("invalid="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac MultipleThrowsDemo.java
java MultipleThrowsDemo
```

Exact `stdout`:

```text
valid=85
invalid=ParseException
```

**Why are two checked exception types needed?**

- `reader.readLine()` and closing the reader can report `IOException`.
- An empty line or one containing non-numeric data is intentionally converted by this method into a `ParseException`; when conversion fails, the original `NumberFormatException` is preserved in `getCause()`.
- Both `IOException` and `ParseException` can escape `readScore`, so `throws IOException, ParseException` is declared in full.
- `main` uses `catch (IOException | ParseException failure)` to catch both types in the same handler. This is **multi-catch**; the `|` symbol is only valid in an appropriate `catch`, **not** in a `throws` list.

The example is deterministic: `StringReader("85")` provides valid data, while `StringReader("bad")` produces `ParseException` as described. It does not depend on files, network, or machine permissions.

### When You Need to Handle Two Types in Two Different Ways

Illustrative snippet using the methods declared above:

```java
try {
    int score = readScore(source);
    saveScore(score);
} catch (ParseException failure) {
    reportInvalidInput(failure);
} catch (IOException failure) {
    reportReadFailure(failure);
}
```

This is an **illustrative snippet**, not a standalone runnable program: `source`, `saveScore`, `reportInvalidInput`, and `reportReadFailure` need to be declared. When recovery actions differ, separate `catch` blocks are often easier to read than multi-catch.

## 7. Which Error Paths Should Declared Exception Types Cover?

Suppose a method can throw `FileNotFoundException`, which is a subclass of `IOException`. Both of the following signatures can satisfy exception checking:

```java
void loadA() throws java.io.FileNotFoundException {
    // ...
}

void loadB() throws java.io.IOException {
    // ...
}
```

These two snippets are **illustrative signatures**. Declaring a supertype covers the subtype exception, but it also widens the contract for the caller. Specifically:

- `throws FileNotFoundException`: the caller knows the declared checked error type is relatively narrow.
- `throws IOException`: the caller must prepare for a broader range of I/O-related errors.
- `throws Exception` or `throws Throwable`: legal in appropriate cases, but usually too broad for application APIs because it reduces clarity and forces callers to handle a wide type.
- Declaring both `throws FileNotFoundException, IOException` can be valid, but it is **redundant** with respect to checked-exception capability because `IOException` already covers `FileNotFoundException`.
- You do not need to add `RuntimeException` to the list just to make the program compile.

**Design rule:** prefer listing checked exception types that are independently meaningful to the caller; use a supertype when the API genuinely intends to allow that family of subclasses. Do not add error types just "in case" without justification.

### A Declaration List Does Not Mean a Handling Mechanism

`throws` does not automatically create retries, fallbacks, logging, or rollbacks. When a checked exception occurs, if the method body does not catch it, execution completes abruptly and the error propagates to the caller. If there is no compatible handler in the call chain, it can reach the thread's uncaught exception handler.

Also do not assume that a declared exception type is guaranteed to appear on every call. The declaration is only a contract about the **possibility** of occurrence.

## 8. `throws` in Constructors

A constructor also lists **one or more checked exception types**, separated by commas, when initialization must read or validate data. Example declaring a constructor that handles both I/O and format errors:

```java
// Placed in class Config, with java.io.Reader provided by the caller.
Config(java.io.Reader source)
        throws java.io.IOException, java.text.ParseException {
    int first = source.read();
    if (first != '{') {
        throw new java.text.ParseException("expected '{'", 0);
    }
}
```

This is an **illustrative constructor snippet**, not a standalone Java file. `source.read()` can throw `IOException`; the format check can throw `ParseException`. Any place calling `new Config(reader)` must catch or declare **both** checked exception types. A constructor has no return type, and `throws` is placed after the parameter list and before the body. If a constructor throws, the `new` call does not return a successfully initialized object; the calling method cannot treat the failure as a valid result.

For complex constructors, manage resources and cleanup properly; this example does not close `Reader` because ownership of the input source remains with the caller.

## 9. `throws` and Method Overriding (`override`)

If an interface declares **multiple checked exception types**, an implementation can declare a narrower set, and must not add broader or incompatible checked types. Example:

```java
// Two illustrative declarations, to be placed in appropriate Java files.
interface DocumentSource {
    String load() throws java.io.IOException, java.text.ParseException;
}

class ParsedSource implements DocumentSource {
    @Override
    public String load() throws java.text.ParseException {
        return "valid"; // This implementation does not produce I/O errors.
    }
}
```

`ParsedSource.load()` omits `IOException` and keeps `ParseException`; this is a valid narrowing of the contract. Replacing it with `throws Exception` would be invalid because it widens the checked exception scope. However, when a call goes through a variable with static type `DocumentSource`, the compiler still enforces **both** checked exception types from the interface, regardless of which implementation might be chosen at runtime.

A specific feature of multi-type lists is that narrowing can drop **one error branch** or use a valid subtype of that branch. Not every override has to copy the interface's entire `throws` list verbatim.

## 10. The `throws` Clause in API Signatures

This clause can appear in:

- Regular methods, including `static` methods.
- `abstract` methods and interface method declarations.
- `default` methods of interfaces.
- Constructors, including `public`, `protected`, or package-private constructors.
- Generic methods; in advanced cases, the exception type can also be a **type variable** upper-bounded by `Throwable`.

Example contract declarations:

```java
interface Repository {
    byte[] read(String key) throws java.io.IOException;
}

abstract class Importer {
    abstract void importData() throws java.io.IOException,
            java.text.ParseException;
}
```

These are two valid type declarations to illustrate signatures; they do not contain `main`. These bodyless methods still use `throws` to announce checked-exception handling responsibilities to implementers and callers.

### `throws` Is Not Part of Overload Resolution

You cannot create two methods that differ only in their `throws` list:

```java
// Invalid if both are placed in the same class:
void execute() throws java.io.IOException { }
void execute() throws java.text.ParseException { }
```

This is an **intentionally invalid example**: Java does not treat two signatures as distinct overloads solely because their `throws` clauses differ. Differentiate methods by name or parameters when there are genuinely two different operations.

### `throws` Does Not Change the Return Type

A method `int parse() throws ParseException` still has return type `int` on the success path. If an error is thrown, no `int` value is returned to that call; control flow follows the exception mechanism. `throws` is not a union type or a `Result`-style wrapper.

## 11. `throws` and Lambda Expressions

A lambda body must also be compatible with the set of checked exceptions allowed by the **target functional method**.

Valid example using a custom interface:

```java
import java.io.IOException;

@FunctionalInterface
interface IoAction {
    void run() throws IOException;
}

public class LambdaThrowsDemo {
    public static void main(String[] args) throws IOException {
        IoAction action = () -> {
            System.out.println("action completed");
        };
        action.run();
    }
}
```

Save as **`LambdaThrowsDemo.java`** and run:

```bash
javac LambdaThrowsDemo.java
java LambdaThrowsDemo
```

`stdout`:

```text
action completed
```

If the lambda body actually throws `IOException`, it is valid with `IoAction` because the functional method allows `throws IOException`. However, a lambda assigned to `Runnable` cannot throw a checked `IOException` out of its body, because `Runnable.run()` does not declare any checked exceptions.

This explains why adding `throws IOException` to the **enclosing method** is not enough to allow a `Runnable` lambda to throw an incompatible checked exception: the checking rules for a lambda body depend on the functional type to which the lambda is assigned.

## 12. Common Syntax and Design Mistakes

| Incorrect Code / Misconception | Issue | Correct Approach |
| --- | --- | --- |
| `void f() throw IOException` | `throw` is not used for declarations | `void f() throws IOException` |
| `void f() throws new IOException()` | `throws` requires types, not objects | `void f() throws IOException` |
| `void f() throws IOException \| ParseException` | Misusing the `|` symbol from multi-catch | `void f() throws IOException, ParseException` |
| `throw IOException;` | `throw` requires an expression of type `Throwable` | `throw new IOException();` or rethrow a caught variable |
| Calling a `throws IOException` method without catching/declaring | Does not satisfy checked exception rules | Use `catch (IOException e)` or declare `throws IOException` |
| `throws Exception` for every error | Broadens the contract and forces generic handling | Prefer specific, meaningful checked types |
| Only adding `throws` and treating the error as handled | The exception can still propagate outward | Identify the application boundary responsible for handling it |
| Adding a broader checked exception when overriding (`override`) | Can violate the supertype method's contract | Keep, narrow, or omit checked exceptions |
| Assuming a `throws` list guarantees the error type will occur | A declaration only describes possibility | Check execution paths and actual causes |
| Thinking `throws` is required for every `RuntimeException` | Unchecked exceptions are not enforced by the compiler | Declaration is optional, though API documentation should still be clear |

Another case: in `catch (FileNotFoundException | IOException e)`, the two alternatives are in the same inheritance hierarchy, so multi-catch is invalid due to the parent-child relationship. In a **`throws` list**, listing both types carries no useful distinction because `IOException` already covers `FileNotFoundException`. The syntax and rules of `throws` and `catch` should be evaluated separately.

## 13. How to Write Clear Exception Contracts

### 13.1. Choose Types That Accurately Describe the Error Source

For example, a function that reads data and decodes a format: `throws IOException, ParseException` helps callers distinguish data-access errors from content-parsing errors. If you only use `throws Exception`, callers lose the ability to know which specific types to catch without deeper inspection.

### 13.2. Preserve the Cause When Crossing Layers

If you need to convert `NumberFormatException` into a checked `ParseException`, store the original exception as the `cause`, as shown in `MultipleThrowsDemo`. The stack trace and root cause help with diagnosis when multiple API layers propagate exceptions.

### 13.3. Do Not Use `throws` as a Substitute for Input Validation

A `throws IllegalArgumentException` contract can be useful documentation, but you still must perform appropriate input validation where needed. Merely adding the type name to the signature does not generate validation checks.

### 13.4. Use `@throws` in JavaDoc

`@throws IOException` is a **documentation tag** explaining the error condition. It does not replace the `throws` clause in the method declaration when a checked exception must be declared. When building public APIs, use both an accurate signature and documentation explaining failure conditions.

Example signature with JavaDoc:

```java
/**
 * Reads configuration from the provided source.
 *
 * @param source data source
 * @return configuration content
 * @throws java.io.IOException if the read operation fails
 * @throws java.text.ParseException if the content is invalid
 */
String loadConfig(java.io.Reader source)
        throws java.io.IOException, java.text.ParseException {
    // Illustrative body simplified.
    return "";
}
```

This is an **illustrative method snippet** for API documentation and signatures. In real production code, the body must perform the promised work; do not use a stub in place of actual reading/parsing logic.

## 14. Self-Check Questions

1. **What is the syntax for one checked exception type?** Example: `void load() throws IOException`.
2. **How are two types separated?** By a comma: `throws IOException, ParseException`.
3. **Does `throws` actually throw an exception object?** No. A `throw` statement or an operation that fails at runtime performs the throw.
4. **Is a method declared with `throws IOException` valid if a run does not throw an error?** Yes.
5. **If you call an API with a checked exception and do not catch it, what must you do?** Propagate the allowed type by declaring it with `throws` or a compatible supertype.
6. **Is `throws IOException | ParseException` valid?** No. The `|` symbol is for multi-catch; `throws` uses commas.
7. **Is `RuntimeException` required to be declared in `throws`?** No. It is unchecked.
8. **Can a method implementing an interface with `throws IOException` omit `throws`?** Yes, if its body is valid and does not propagate disallowed checked exceptions.
9. **Can two methods be overloaded differing only by their `throws` clause?** No.
10. **Does `throws IOException, ParseException` mean both are thrown at the same time?** No. Each throw propagates a single exception object; the two types represent possibilities.

## 15. Official Documentation (Java 17)

- [Java Language Specification §8.4.6 — Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): syntax and rules for declaring exception types.
- [Java Language Specification §8.8.5 — Constructor Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.5): `throws` clause in constructors.
- [Java Language Specification §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception checking.
- [Java Language Specification §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exception constraints when overriding.
- [Java Language Specification §14.20 — The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `catch` and multi-catch.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [ParseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParseException.html): checked exception types used in the examples.

**Key takeaway:** After `throws` comes **one or more exception types**, separated by commas. This clause declares a contract so the compiler and callers can determine responsibilities for checked exceptions; it does not create, catch, or fix any error on its own.
