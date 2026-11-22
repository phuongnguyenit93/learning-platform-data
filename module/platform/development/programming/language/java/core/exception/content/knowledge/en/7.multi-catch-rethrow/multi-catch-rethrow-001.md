# Multi-catch from Java 7 and the | Syntax in Java

> Java Core – Exception · Group: Multi-catch and rethrow · Focus: Java 7+ syntax, valid alternatives, catch parameter type, and usage in exception handling. Main examples run on Java 17+.

## 1. What is multi-catch used for?

An operation may encounter multiple types of errors that require the **same handling logic**. Before Java 7, the standard approach was to write multiple `catch` branches and duplicate code:

```java
try {
    loadData();
} catch (IOException ex) {
    System.out.println("Cannot process data: " + ex.getMessage());
} catch (NumberFormatException ex) {
    System.out.println("Cannot process data: " + ex.getMessage());
}
```

Starting in **Java 7**, multi-catch allows grouping exception types into **a single catch parameter**, separated by a vertical bar `|`:

```java
try {
    loadData();
} catch (IOException | NumberFormatException ex) {
    System.out.println("Cannot process data: " + ex.getMessage());
}
```

The two snippets above are **illustrative code**, assuming `java.io.IOException` is imported and `loadData()` is declared appropriately. They are not standalone programs.

**Meaning:** When the `try` body throws an exception object matching **any** of the listed types, Java executes only **one shared handler**. This syntax reduces code duplication, expresses that the errors share the same handling policy, and preserves the original exception object.

### Learning Outcomes

You will learn how to:

1. Read and write `catch (A | B ex)` using valid Java 7+ syntax.
2. Determine when two types can be combined and when the compiler forbids it due to a subtype relationship.
3. Distinguish multi-catch from multiple independent catch blocks, and understand the inferred parameter type and the implicitly `final` rule.
4. Catch both checked and unchecked exceptions in the same handler when they share the same policy.
5. Use `throw ex;` to propagate an exception and understand its connection to precise rethrow from Java 7.
6. Compile a Java 17 program and accurately compare the selected handler and stdout.

## 2. The | syntax in the catch parameter

Structure:

```java
try {
    operation();
} catch (FirstException | SecondException ex) {
    handle(ex);
}
```

This snippet illustrates the grammar; the type and method names are placeholders, not standalone compilable code.

| Component | Meaning |
| --- | --- |
| `try { ... }` | Execution block that may throw an exception |
| `FirstException` | First alternative |
| `|` | Separator between **exception types** in a union type |
| `SecondException` | Second alternative |
| `ex` | **A single parameter variable**, referencing the actual exception object |
| `{ handle(ex); }` | **A single handler block** shared across the alternatives |

The `|` symbol is not `||`. In multi-catch, it appears **between type names** and does not perform a boolean OR or bitwise OR when handling the object.

Example that is **valid regarding the relationship between alternatives**:

```java
catch (IOException | NumberFormatException | IllegalStateException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

None of these three types has a subtype relationship with another. When placed in a real program, it must still satisfy compiler checks for checked exceptions and handler ordering.

Conversely, here are examples with **intentionally invalid syntax**:

```java
// Wrong: do not use || or a comma to separate types:
catch (IOException || NumberFormatException ex) { }
catch (IOException, NumberFormatException ex) { }
```

In addition, the union type here is only for catch parameter declarations; there is no general variable syntax such as `IOException | NumberFormatException ex;`.

**Version milestone:** Multi-catch was introduced in Java SE 7 through the language enhancements of Project Coin (JSR 334). It requires no external libraries. If you must compile for Java 6 syntax, this feature does not exist; if you target Java 7 or later, the syntax is valid.

## 3. Subtype rule: parent and child classes cannot be combined

This is the most important constraint. According to [JLS 17 section 14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20), in a union with multiple alternatives, **no alternative may be a subtype of another alternative**.

Observe the inheritance tree:

```text
java.lang.Throwable
└── java.lang.Exception
    ├── java.io.IOException
    │   └── java.io.FileNotFoundException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        │   └── java.lang.NumberFormatException
        └── java.lang.IllegalStateException
```

### 3.1. Two independent types: valid

```java
catch (IOException | NumberFormatException ex) {
    System.out.println(ex.getMessage());
}
```

An `IOException` is not a `NumberFormatException`, and vice versa. Whichever type the actual exception has, the variable `ex` references that exact object.

### 3.2. Parent and child: invalid

```java
// Wrong, only illustrates a compilation error:
catch (IOException | FileNotFoundException ex) {
    System.out.println(ex.getMessage());
}
```

`FileNotFoundException` is a subtype of `IOException`. The overlapping union causes the compiler to reject it. Reversing it to `FileNotFoundException | IOException` **is still wrong**, because the inheritance relationship has not changed.

Similarly:

```java
// Wrong: NumberFormatException extends IllegalArgumentException.
catch (NumberFormatException | IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
```

If a parent and child type **need the same handling**, simply catch the **parent type**:

```java
catch (IOException ex) {
    System.out.println("I/O failure");
}
```

If they require **different** handling, use two catch blocks ordered child before parent:

```java
try {
    readFile();
} catch (FileNotFoundException ex) {
    System.out.println("Missing file");
} catch (IOException ex) {
    System.out.println("Other I/O error");
}
```

The snippet above assumes `readFile()` can throw `IOException`, solely to illustrate catch ordering.

**Key comparison:** In **multi-catch**, two parent–child alternatives are forbidden **in any order**. In **separate catch blocks**, both can be declared if the **subclass comes before the superclass** so that the subclass handler is not shadowed.

## 4. At runtime, multi-catch catches a single exception object

Example:

```java
try {
    readThenParse();
} catch (IOException | NumberFormatException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

A single throw propagates **one Throwable instance**, without creating two instances. Java checks the handlers in order and finds the first matching catch; in a union, only **one alternative** needs to match the runtime type.

Suppose the method throws `FileNotFoundException`:

- `FileNotFoundException` is a subtype of `IOException`, so the `IOException` alternative catches it.
- The variable `ex` holds the original `FileNotFoundException` object.
- `ex.getClass().getSimpleName()` produces `FileNotFoundException`, not `IOException` or the name of the union.
- The handler block runs **once**, and the remaining sibling catch blocks of the same `try` do not run.
- If the handler block throws a new exception, sibling catch blocks do not automatically catch the new exception thrown inside that handler.

Multi-catch is not a way to collect multiple simultaneous errors. If a resource-closing error occurs while a primary exception is already thrown in `try-with-resources`, the mechanism can use `getSuppressed()` to preserve the secondary error; that is a different concept from the `|` syntax.

## 5. Complete Java 17 example and expected output

Save the code below as **`MultiCatchDemo.java`**. The example uses modern Java `switch ->` syntax, so it requires **Java 17+**; the multi-catch syntax itself has existed since Java 7.

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class MultiCatchDemo {
    private static void perform(String mode) throws IOException {
        switch (mode) {
            case "missing" -> throw new FileNotFoundException("config.txt");
            case "io" -> throw new IOException("read failed");
            case "number" -> Integer.parseInt("NaN");
            case "argument" -> throw new IllegalArgumentException("unsupported input");
            case "ok" -> System.out.println("work=ok");
            default -> throw new IllegalStateException("unexpected mode");
        }
    }

    private static void run(String mode) {
        System.out.println("== " + mode + " ==");
        try {
            perform(mode);
            System.out.println("try completed");
        } catch (IOException | NumberFormatException ex) {
            System.out.println("group=" + ex.getClass().getSimpleName());
        } catch (IllegalArgumentException ex) {
            System.out.println("argument=" + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }

    private static void rethrowFileError() throws IOException {
        try {
            throw new FileNotFoundException("log.txt");
        } catch (IOException | IllegalArgumentException ex) {
            System.out.println("inside=" + ex.getClass().getSimpleName());
            throw ex;
        }
    }

    public static void main(String[] args) {
        run("missing");
        run("io");
        run("number");
        run("argument");
        run("ok");

        System.out.println("== rethrow ==");
        try {
            rethrowFileError();
        } catch (IOException ex) {
            System.out.println("outside=" + ex.getClass().getSimpleName());
        }
    }
}
```

With a JDK supporting `--release 17`:

```bash
javac --release 17 -encoding UTF-8 MultiCatchDemo.java
java MultiCatchDemo
```

**Exact stdout** verified by compiling and running the program:

```text
== missing ==
group=FileNotFoundException
finally
after
== io ==
group=IOException
finally
after
== number ==
group=NumberFormatException
finally
after
== argument ==
argument=unsupported input
finally
after
== ok ==
work=ok
try completed
finally
after
== rethrow ==
inside=FileNotFoundException
outside=FileNotFoundException
```

### The missing case

`perform("missing")` throws `FileNotFoundException`. It is caught by the `IOException` alternative because it belongs to the `IOException` inheritance tree. The group handler prints `group=FileNotFoundException` according to the actual **runtime** type, then the `finally` block prints `finally`, and then `after` is printed.

### The io case

`perform("io")` throws an `IOException` object. It is caught directly by the first alternative, printing `group=IOException`. No other handler of the `try` statement runs.

### The number case

`Integer.parseInt("NaN")` throws `NumberFormatException` because the string is not a valid integer format. The second alternative catches this exception and runs the **same block** as `IOException`. This demonstrates that multi-catch can group **checked** and **unchecked exceptions** when the handling policy is the same.

### The argument case

`perform("argument")` throws a plain `IllegalArgumentException`. It is the **parent** type of `NumberFormatException`, but not every `IllegalArgumentException` is a `NumberFormatException`. The preceding union only catches `NumberFormatException`, so the error falls through to `catch (IllegalArgumentException)` afterward.

A catch for a superclass can catch a subclass instance, but **not the other way around**.

### The ok case

`perform("ok")` prints `work=ok` and completes normally; the `try` body continues and prints `try completed`. The catch blocks do not run. `finally` still runs, and then `after` is printed.

### The rethrow case

`rethrowFileError()` throws a `FileNotFoundException`, catches it in the `IOException | IllegalArgumentException` union, prints `inside=FileNotFoundException`, and then executes `throw ex;`. The caller in `main` receives the **same exception** via `catch (IOException)` and prints `outside=FileNotFoundException`.

`throw ex;` does not create a new exception when `ex` is a valid reference to the caught object.

## 6. Type of the ex parameter and the implicitly final rule

In a multi-catch:

```java
catch (IOException | NumberFormatException ex) {
    System.out.println(ex.getMessage());
    System.out.println(ex.getCause());
}
```

the parameter `ex` has **a single declared type** inferred by the compiler from the alternatives. According to the JLS, that type is the **least upper bound**: `lub(D1, D2, ...)`. It may be a supertype or a type with common bounds, rather than changing its static type on each run.

Therefore, **common** members of `Throwable` such as `getMessage()`, `getCause()`, `getSuppressed()`, `printStackTrace()`, and `getClass()` can all be used. A method that exists only on one subtype cannot be called directly on `ex` if the common declared type does not provide that method.

### Reassigning ex is not allowed

The exception variable of a multi-catch is **implicitly final**, so the following is rejected by the compiler:

```java
try {
    readThenParse();
} catch (IOException | NumberFormatException ex) {
    // Wrong if uncommented:
    // ex = new IOException("another failure");
}
```

Even without writing the `final` keyword, you cannot reassign `ex` to another exception or assign `null` to it.

For comparison: in a **uni-catch** such as `catch (IOException ex)`, the parameter is not implicitly final. It can be *effectively final* if it is not reassigned. Although single-catch syntax allows reassignment in some cases, doing so is generally discouraged because it makes tracking the original exception harder and can affect rethrow analysis.

**Do not confuse the two terms:** A multi-catch parameter is **implicitly final**; an unassigned uni-catch parameter can be **effectively final**. The JLS distinguishes the two cases, though both play a role in preserving exception types during rethrow.

## 7. Multi-catch and precise rethrow from Java 7

Alongside multi-catch, Java 7 improved how checked exceptions are checked when **rethrowing the `catch` parameter itself** via `throw ex;`. In the `MultiCatchDemo` program in section 5, `rethrowFileError()` catches `IOException | IllegalArgumentException` and rethrows `ex`. The caller can still distinguish the actual `FileNotFoundException` error, and the signature `throws IOException` is sufficient; there is no need to widen it to `throws Exception`.

These are two separate features: **multi-catch** groups error types that share a handler; **precise rethrow** allows the compiler to infer the set of checked exceptions that can escape from `try` when the `catch` variable is `final` or *effectively final*. A single `catch (Exception ex)` that does not reassign `ex` can also benefit from precise rethrow. If you modify the `ex` reference in a single-catch, that inference benefit may be lost.

At an introductory level, check three things: whether the actual exception is preserved when `throw ex` runs, whether the `throws` signature covers any checked exceptions that still escape, and whether the handler recovers or merely delegates responsibility to the caller. Exact exception-set analysis and the impact of reassignment will be covered in depth in the rethrow section.

## 8. Checked, unchecked, and catch blocks after a union

`IOException` is checked: the compiler requires catching or declaring it if it can be thrown. `NumberFormatException` is unchecked, so it does not need to be declared with `throws`, yet it is still allowed to be caught. Multi-catch does not turn checked exceptions into unchecked ones.

For a catch to be valid, in addition to the subtype condition, the compiler checks **whether a checked exception can actually be thrown in the try block** according to JLS rules. For example, if you only parse a numeric string and call no I/O APIs, having a catch for `IOException` will typically be reported as unreachable because that checked exception cannot be thrown.

### Subsequent catch blocks can be shadowed

Example that **intentionally does not compile**, assuming `readFile()` can throw `IOException`:

```java
try {
    readFile();
} catch (IOException | NumberFormatException ex) {
    System.out.println("group");
} catch (FileNotFoundException ex) {
    System.out.println("missing");
}
```

`FileNotFoundException` is already covered by the `IOException` alternative of the first catch. Therefore, the later catch can never receive an exception that the first catch did not already catch, causing the compiler to reject it. This is a **catch ordering** error; it is different from the error of **having subtype-related alternatives within the same union**.

A valid way to organize this if you want to distinguish a missing file from other I/O errors:

```java
try {
    readFile();
} catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println("known failure");
} catch (IOException ex) {
    System.out.println("other I/O failure");
}
```

The first two alternatives have no parent–child relationship, and the `IOException` catch afterward can still receive `IOException` instances other than `FileNotFoundException`.

## 9. When to use multi-catch vs. separate catch blocks

### Use multi-catch when the policy is the same

For example, a program reads configuration and then parses a number. If both an I/O error and a number format error mean "the configuration is unusable", both types can be translated into a single application-layer exception:

```java
try {
    loadConfiguration();
} catch (IOException | NumberFormatException ex) {
    throw new IllegalStateException("Invalid configuration", ex);
}
```

This is an illustrative snippet assuming `loadConfiguration()` exists. The `IllegalStateException(String, Throwable)` constructor preserves the original exception as the `cause` for diagnostics.

### Use separate catch blocks when recovery paths differ

```java
try {
    loadConfiguration();
} catch (IOException ex) {
    retryLater(ex);
} catch (NumberFormatException ex) {
    askUserToCorrectInput(ex);
}
```

This snippet merely illustrates business methods. An I/O error might be retried after checking conditions; a number format error requires fixing the input. Forcing both into a grouped catch would lose their domain meaning.

### Do not catch Exception or Throwable out of habit

`catch (Exception)` can catch unchecked logic bugs such as `NullPointerException`, making it easy for the application to continue in an invalid state. `catch (Throwable)` also includes `Error`, which is usually inappropriate to swallow and keep running. Catch at the level of specificity that the current layer can actually recover from.

Multi-catch helps eliminate duplicate code, but that is not a reason to ignore important differences in error handling.

## 10. Minimal program compatible with Java 7 syntax

The main example in section 5 uses modern `switch` to demonstrate multiple scenarios. To verify **specifically the Java 7 multi-catch feature**, you can use the following program with classic syntax.

Save as **`Java7MultiCatch.java`**:

```java
import java.io.IOException;

public class Java7MultiCatch {
    static void work(int kind) throws IOException {
        if (kind == 1) {
            throw new IOException("io");
        }
        throw new NumberFormatException("number");
    }

    public static void main(String[] args) {
        try {
            work(1);
        } catch (IOException | NumberFormatException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
```

If using an actual JDK 7:

```bash
javac Java7MultiCatch.java
java Java7MultiCatch
```

Stdout:

```text
IOException
```

If you replace `work(1)` with `work(2)`, the output becomes `NumberFormatException`. Both runs enter the same grouped catch while preserving the **runtime type**.

Do not assume every newer JDK compiler still supports `--release 7`; run `javac --help` to see which release levels your compiler supports. The Java 7 version runs directly on JDK 7 or a toolchain supporting release 7; the Java 17 example in section 5 was verified separately using `javac --release 17`.

## 11. Table of common syntax errors and rules

| Syntax | Verdict | Explanation |
| --- | --- | --- |
| `catch (IOException | NumberFormatException ex)` | Valid if `try` matches | Two types without subtype overlap |
| `catch (IOException|NumberFormatException ex)` | Valid | Spaces around the vertical bar are optional |
| `catch (IOException || NumberFormatException ex)` | Invalid | Misused boolean operator `||` |
| `catch (IOException, NumberFormatException ex)` | Invalid | Commas do not separate union types |
| `catch (IOException | FileNotFoundException ex)` | Invalid | Parent and child types overlap |
| `catch (IllegalArgumentException | NumberFormatException ex)` | Invalid | `NumberFormatException` is a subtype |
| `catch (IOException | IOException ex)` | Invalid | Duplicate alternative of the same type |
| `catch (IOException | NumberFormatException ex) { ex = null; }` | Invalid | Multi-catch parameter is implicitly final |
| `catch (IOException ex)` | Valid if `try` matches | Normal uni-catch |
| `catch (IOException | IllegalStateException ex)` | Valid if `try` matches | Checked and unchecked can be combined |

Snippets marked "Invalid" are for illustrating compilation errors; **do not put them into runnable programs**.

## 12. Multi-catch verification checklist

For a new piece of code, check in order:

1. **Identify the actual error set:** read the API `throws` signatures for checked exceptions; add unchecked exceptions that have business meaning.
2. **Map `extends` relationships:** especially check pairs like `FileNotFoundException/IOException`, `NumberFormatException/IllegalArgumentException`, and other subtypes.
3. **Group only errors with the same policy:** if recovery paths differ, use separate catch blocks.
4. **Place multi-catch in valid handler order:** subtypes must be handled before supertypes in consecutive catch blocks.
5. **Do not reassign `ex`:** it is implicitly final in multi-catch.
6. **Preserve the cause when wrapping:** e.g., `new IllegalStateException(message, ex)`.
7. **Test every alternative:** one case throwing the first alternative, one throwing the second, one with no error, and one matching only another catch.
8. **If rethrowing, check signatures and callers:** checked exceptions may need corresponding `throws`; avoid swallowing errors.
9. **Check exception types, do not hardcode system messages:** I/O messages can vary across environments and JDK versions.

### Exercise scenario

Suppose `read()` can throw `IOException`:

```java
try {
    read();
} catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println("A");
} catch (IOException ex) {
    System.out.println("B");
}
```

This is an illustrative snippet placed inside a method where `read()` is declared, not a standalone program.

| Exception from try | Output | Reason |
| --- | --- | --- |
| `FileNotFoundException` | `A` | Matches `FileNotFoundException` alternative |
| `NumberFormatException` | `A` | Matches `NumberFormatException` alternative |
| `IOException` other than `FileNotFoundException` | `B` | Does not match first union, matches `IOException` catch |
| No exception | Neither A nor B printed | Catch blocks do not run |

If you change the first union to `IOException | FileNotFoundException`, the compiler rejects it due to subtype overlap. If you move `catch (IOException)` before the union containing `FileNotFoundException`, the compiler rejects it because the grouped branch is shadowed for `FileNotFoundException`.

## 13. Common misconceptions to avoid

- **"The | symbol runs both handlers."** No: it is one parameter, one handler block, and one thrown exception object.
- **"Parent and child types are valid if you reverse their order in the same union."** No: subtypes are forbidden in a union in any order.
- **"Multi-catch only catches checked exceptions."** No: both checked and unchecked exceptions can be used.
- **"ex changes its static type per alternative at runtime."** No: the compiler determines one common declared type; the runtime object still retains its concrete type.
- **"You can reassign ex to another exception."** No: a multi-catch parameter is implicitly final.
- **"Catching NumberFormatException catches every IllegalArgumentException."** No: catching a subclass does not automatically catch all instances of its superclass.
- **"Multi-catch replaces throws."** No: checked exceptions are still analyzed at compile time.
- **"An exception thrown from the first catch will be caught by a sibling catch."** No: sibling catch blocks of the same `try` only handle exceptions from the `try` body.
- **"`throw ex` creates a new exception."** No: for a non-null `ex`, it rethrows the same object.
- **"Multi-catch and precise rethrow are the same feature."** No: they serve different purposes even though both appeared in Java 7.
- **"The more types you group, the better."** No: only group types that share the same handling policy.
- **"Catching an exception cleans up resources."** No: cleanup still requires constructs such as `try-with-resources` or an appropriate `finally`.

## 14. Self-check questions

**1.** Which Java version introduced multi-catch, and what is the separator between alternatives?

*Answer:* Java 7; a single vertical bar `|` between types.

**2.** Why does `IOException | FileNotFoundException` fail to compile?

*Answer:* Because `FileNotFoundException` is a subtype of `IOException`.

**3.** Is a thrown `FileNotFoundException` caught by `IOException | NumberFormatException`?

*Answer:* Yes, via the `IOException` alternative.

**4.** If `catch (IOException | NumberFormatException ex)` has already caught `NumberFormatException`, will a subsequent `catch (IllegalArgumentException)` run?

*Answer:* No. Only the first matching handler is executed.

**5.** Why does a direct `IllegalArgumentException` not enter the `IOException | NumberFormatException` group?

*Answer:* Because `NumberFormatException` is a subclass of `IllegalArgumentException`, so not every `IllegalArgumentException` instance is a `NumberFormatException`.

**6.** Can you reassign `ex` inside a multi-catch?

*Answer:* No, it is implicitly final.

**7.** Does `throw ex;` inside a grouped catch create a new `IOException` or automatically remove checked exception requirements?

*Answer:* No. It rethrows the existing object; the compiler still analyzes which checked exceptions can escape, and the caller must handle or declare them accordingly.

**8.** If `IOException` needs a retry while `NumberFormatException` needs to prompt the user to re-enter input, should you use multi-catch?

*Answer:* You should consider separating the two catch blocks because their recovery policies differ.

## 15. Official references

- [Java Language Specification 17 – §14.20 The try statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): multi-catch syntax, union alternatives, subtype constraints, parameter type, and implicitly final.
- [JLS 17 – §14.20.1 Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): first-matching-handler rule.
- [JLS 17 – §11.2.2 Exception Analysis of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.2): precise rethrow mechanism in exception analysis.
- [JLS 17 – §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): checked exception rules.
- [Oracle tutorial – Catching Multiple Exception Types](https://docs.oracle.com/javase/tutorial/essential/exceptions/catch.html): explanation of multi-catch and practical usage.
- [JSR 334 – Small Enhancements to the Java Programming Language](https://jcp.org/en/jsr/detail?id=334): language enhancement bundle in Java 7.

**Key takeaway:** The `catch (A | B ex)` syntax groups errors with the same handling logic into **one handler**. Alternatives must not have a subtype relationship with each other; `ex` is implicitly final; the order of other catch blocks still matters; and when rethrowing, checked exceptions are still verified by the compiler under Java's rethrow rules.
