# Do Not Put a Supertype and a Subtype in the Same Java Multi-Catch

In Java, a **multi-catch** clause allows multiple exception types to share a single handler block:

~~~java
try {
    performOperation();
} catch (IOException | SQLException ex) {
    handleFailure(ex);
}
~~~

This is an **illustrative snippet**; `performOperation()` and `handleFailure(...)` must be defined appropriately. The `|` between exception types means "catch one of the listed types." However, **you must not list both a supertype and one of its subtypes in the same multi-catch**:

~~~java
// INVALID: FileNotFoundException is a subclass of IOException.
catch (FileNotFoundException | IOException ex) {
    // ...
}
~~~

This is a **compile-time** error, not an error that only occurs at runtime. If you only need to handle the entire exception family in one way, **catch the single supertype**. If you need to distinguish how the specific type and the general type are handled, **use separate `catch` blocks with the subtype before the supertype**. If two types do not inherit from each other and share the same handling logic, **multi-catch is a valid choice**.

This lesson covers the rule, the rationale, how to determine inheritance relationships, how to fix common mistakes, the impact on rethrowing exceptions, and compiled/verified Java 17+ examples.

## 1. Recap: What is multi-catch used for?

Since Java 7, a `catch` clause can list multiple independent exception types using `|` when they share the same handler body:

~~~java
try {
    performOperation();
} catch (java.io.IOException | java.sql.SQLException ex) {
    System.err.println(ex.getMessage());
}
~~~

This is an illustrative snippet that requires `performOperation()` to declare the corresponding checked exceptions. A single exception triggers only **one** matching handler; the `|` operator does not create multiple variables or multiple handling passes. For this lesson, the focus is not on relearning the syntax, but on the **subtype relationship**: even though `A` and `B` both belong to `Exception`, `catch (A | B e)` is rejected when `A` inherits from `B` or vice versa.

## 2. Why can't a supertype and a subtype be combined?

Consider the familiar hierarchy:

~~~text
java.lang.Exception
└── java.io.IOException
    ├── java.io.FileNotFoundException
    ├── java.io.EOFException
    ├── java.nio.file.FileSystemException
    │   └── java.nio.file.AccessDeniedException
    └── ...
~~~

`FileNotFoundException` is a subclass of `IOException`, meaning:

~~~java
// A FileNotFoundException is also an IOException.
IOException error = new java.io.FileNotFoundException("thiếu tệp");
~~~

If a `catch` block already catches `IOException`, it **naturally catches** every `FileNotFoundException` (and all other subclasses of `IOException`) thrown from the protected `try` block. Therefore, the following code:

~~~java
// DOES NOT COMPILE.
catch (FileNotFoundException | IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

contains an alternative that is **redundant in terms of type coverage**. Java requires the alternatives in a multi-catch to be disjoint with respect to inheritance: no type may be a subclass of another. Reversing the order to `IOException | FileNotFoundException` is **still invalid**.

The rule applies to **both direct and indirect inheritance relationships**. For example, `AccessDeniedException` is an indirect subclass of `IOException` via `FileSystemException`, so `IOException | AccessDeniedException` is also invalid.

Therefore, checking validity is not just about seeing whether two names are identical; you must check the **subtype relationship in the `Throwable` hierarchy**.

## 3. A failing compilation example and how to read the `javac` message

The `InvalidMultiCatch.java` file below is intentionally written to demonstrate the error; **it cannot be compiled into a runnable program**:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

class InvalidMultiCatch {
    static void run() {
        try {
            throw new FileNotFoundException("missing");
        } catch (FileNotFoundException | IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 InvalidMultiCatch.java
~~~

A modern JDK `javac` reports an error containing lines such as:

~~~text
error: Alternatives in a multi-catch statement cannot be related by subclassing
Alternative FileNotFoundException is a subclass of alternative IOException
~~~

The caret position in the message typically points to an alternative in the `catch` list; the path, line number, and error formatting depend on the environment. The key point is: **one alternative is a subclass of another alternative in the same multi-catch**.

This is not an error caused by `try` throwing only one exception or by the `catch` blocks being in the wrong order. Even if `try` can genuinely throw both `IOException` and `FileNotFoundException`, the subtype is already covered by the supertype, so both cannot be written as peer alternatives in a multi-catch.

## 4. Fix 1: Catch a single supertype when sharing the same handling

If all errors in the `IOException` family require the same handling, write:

~~~java
import java.io.IOException;

// Illustrative snippet inside an appropriate method.
try {
    readData();
} catch (IOException ex) {
    System.err.println("Không đọc được dữ liệu: " + ex.getMessage());
}
~~~

`catch (IOException ex)` catches `FileNotFoundException`, `EOFException`, and every subclass of `IOException` thrown within the `try` block. There is no need to write:

~~~java
// Wrong:
catch (IOException | FileNotFoundException | EOFException ex) {
    // ...
}
~~~

The advantage of a single `catch (IOException)` is simplicity without repeating subtypes. On the other hand, it may **also catch other I/O exceptions** beyond the two you originally intended to handle, such as `AccessDeniedException`. If those types require different behavior, choose the separate-branch approach in the next section.

Do not automatically widen to `catch (Exception)` or `catch (Throwable)` just to fix a syntax error: a broader type can mask errors you did not intend to handle. Choose a supertype that is **narrow enough for the contract and intended recovery strategy**.

## 5. Fix 2: Use separate `catch` blocks when different handling is needed

If you want to handle `FileNotFoundException` separately and provide general handling for the remaining `IOException` types, use **two separate `catch` blocks**:

~~~java
try {
    readData();
} catch (FileNotFoundException ex) {
    System.err.println("Hãy kiểm tra đường dẫn tệp.");
} catch (IOException ex) {
    System.err.println("Lỗi I/O khác: " + ex.getMessage());
}
~~~

This is an **illustrative snippet**, requiring appropriate `import` statements and a `readData()` method. This approach is valid because Java checks `catch` blocks **in order**, from top to bottom. If the actual error is `FileNotFoundException`, it enters the first block; if it is another `IOException`, it reaches the second block.

**You must place the subtype before the supertype**. Writing them in reverse:

~~~java
// INVALID: the second block can never catch anything.
try {
    readData();
} catch (IOException ex) {
    System.err.println("I/O");
} catch (FileNotFoundException ex) {
    System.err.println("Thiếu tệp");
}
~~~

causes `catch (FileNotFoundException)` to be considered unreachable, because the preceding `catch (IOException)` already covers the subtype.

Important note: **the rules for multi-catch and multiple separate catch blocks differ in how they are fixed**:

- **Within the same multi-catch:** `catch (FileNotFoundException | IOException ex)` is **invalid in any order**.
- **In two separate `catch` blocks:** `catch (FileNotFoundException)` followed by `catch (IOException)` is **valid**, because the specific type is prioritized first.
- **Two separate `catch` blocks in reverse order:** `catch (IOException)` followed by `catch (FileNotFoundException)` is **invalid** because the specific branch is shadowed.

## 6. Complete Java 17+ example: handling subtype before supertype

Create the file `HierarchyCatchDemo.java`:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

public class HierarchyCatchDemo {
    static void load(boolean missing) throws IOException {
        if (missing) {
            throw new FileNotFoundException("thiếu tài liệu");
        }
        throw new IOException("lỗi đọc chung");
    }

    public static void main(String[] args) {
        for (boolean missing : new boolean[] {true, false}) {
            try {
                load(missing);
            } catch (FileNotFoundException ex) {
                System.out.println("Thiếu tệp: " + ex.getMessage());
            } catch (IOException ex) {
                System.out.println("I/O tổng quát: " + ex.getMessage());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 HierarchyCatchDemo.java
java HierarchyCatchDemo
~~~

Exact stdout:

~~~text
Thiếu tệp: thiếu tài liệu
I/O tổng quát: lỗi đọc chung
~~~

Analysis:

1. On the first iteration, `load(true)` throws `FileNotFoundException`. The specific branch catches the error, and the general branch does not run.
2. On the next iteration, `load(false)` throws an `IOException` object. The first branch does not match; the second branch handles it.
3. The two branches can use different messages and recovery strategies. If they are completely identical, both can be replaced with a single `catch (IOException)`.

Do not confuse `throws IOException` in `load`'s signature with the runtime type of the actual exception. The signature declares the error type that may be propagated; `catch` selects the branch based on the **actual object** at runtime.

## 7. Fix 3: Multi-catch sibling types that do not inherit from each other

Two types **sharing `IOException` as their parent** does not mean one is a subtype of the other. For instance, `FileNotFoundException` and `EOFException` are both subclasses of `IOException`, but **there is no direct or indirect inheritance relationship between those two types**. They can appear together in a multi-catch:

~~~java
catch (FileNotFoundException | EOFException ex) {
    System.err.println("Nhóm lỗi tệp đặc biệt: " + ex.getMessage());
}
~~~

You can add `catch (IOException ex)` **in a separate subsequent branch** to handle the remaining I/O errors. This structure fits when two specific types need a shared handling approach, while other I/O types need different handling.

Complete example `MultiCatchSiblingsDemo.java`:

~~~java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class MultiCatchSiblingsDemo {
    static void load(String mode) throws IOException {
        switch (mode) {
            case "missing" -> throw new FileNotFoundException("thiếu tệp");
            case "ended" -> throw new EOFException("hết dữ liệu");
            case "denied" -> throw new IOException("không có quyền");
            default -> System.out.println("Đọc thành công");
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[] {"missing", "ended", "denied", "ok"}) {
            try {
                load(mode);
            } catch (FileNotFoundException | EOFException ex) {
                System.out.println("Nhóm cụ thể: " + ex.getClass().getSimpleName()
                        + " - " + ex.getMessage());
            } catch (IOException ex) {
                System.out.println("I/O khác: " + ex.getMessage());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 MultiCatchSiblingsDemo.java
java MultiCatchSiblingsDemo
~~~

Exact stdout:

~~~text
Nhóm cụ thể: FileNotFoundException - thiếu tệp
Nhóm cụ thể: EOFException - hết dữ liệu
I/O khác: không có quyền
Đọc thành công
~~~

Why is this allowed?

- The two alternatives `FileNotFoundException` and `EOFException` have no supertype–subtype relationship with each other.
- `catch (IOException)` is a **separate subsequent branch**, not an `| IOException` alternative inside the preceding multi-catch branch.
- If `load` throws `FileNotFoundException` or `EOFException`, it enters the first multi-catch.
- If `load` throws an `IOException` that does not match either specific type, it is handled in the following `catch (IOException)` branch.
- For `"ok"`, `load` completes normally, so none of the `catch` blocks run.

The example uses expression-style arrows in a `switch` statement, compatible with Java 17. The errors in the program are intentionally thrown exceptions so that the demonstration output is deterministic; they do not depend on whether a real file exists.

## 8. Type pairs: valid or not?

| Alternatives in the same `catch (... | ... ex)` | Valid? | Explanation |
| --- | --- | --- |
| `IOException | SQLException` | Yes | Two exception classes that do not inherit from each other. |
| `FileNotFoundException | EOFException` | Yes | Same `IOException` branch, but two independent sub-branches. |
| `IllegalArgumentException | IllegalStateException` | Yes | Same `RuntimeException` branch, not subclasses of each other. |
| `IOException | RuntimeException` | Yes | Two types belonging to different branches of `Exception`. |
| `IOException | FileNotFoundException` | No | `FileNotFoundException` inherits from `IOException`. |
| `Exception | IOException` | No | `IOException` inherits from `Exception`. |
| `RuntimeException | IllegalArgumentException` | No | `IllegalArgumentException` inherits from `RuntimeException`. |
| `IllegalArgumentException | NumberFormatException` | No | `NumberFormatException` inherits from `IllegalArgumentException`. |
| `Throwable | Error` | No | `Error` inherits from `Throwable`. |
| `IOException | AccessDeniedException` | No | `AccessDeniedException` is an indirect subclass of `IOException`. |

A pair with **no subtype relationship** only satisfies the rule for multi-catch alternatives. The entire statement must still satisfy other rules, such as whether the `try` block can throw the caught checked exceptions, the order of branches in the larger structure, and type accessibility/imports.

Therefore, "Yes" (valid) in the table means **it does not violate the multi-catch inheritance rule**, not that every program containing this pair is guaranteed to compile.

## 9. `catch` only checks the runtime type, not the position in the `|` list

Some people write:

~~~java
catch (IllegalArgumentException | IllegalStateException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
~~~

and mistakenly think Java checks from left to right and preserves a priority order similar to separate `catch` blocks. In reality, **both alternatives lead to the exact same handler block**; there are not two different branches to choose between. The caught object still has its **actual runtime type**, such as `IllegalArgumentException` or `IllegalStateException`; `ex.getClass()` reveals that actual class.

Meanwhile:

~~~java
catch (IllegalArgumentException ex) {
    // Handle argument error.
} catch (IllegalStateException ex) {
    // Handle state error.
}
~~~

are two separate branches, each with its own handling logic. You should use multi-catch when you **genuinely want shared handling**; do not merge them just for brevity if different errors require different actions.

Similarly, **swapping the positions** of `FileNotFoundException | IOException` to `IOException | FileNotFoundException` does not fix the compiler error because the rule checks **type relationships**, not positional priority in the `|` list.

## 10. Variable type in multi-catch and things to watch out for

In a multi-catch branch such as:

~~~java
catch (FileNotFoundException | EOFException ex) {
    System.out.println(ex.getMessage());
}
~~~

the compiler infers a reference type that can be safely used based on the alternatives; in this example, common methods from `IOException`/`Throwable` such as `getMessage()` are all usable. The runtime type of the actual object remains unchanged.

However, you cannot directly call a method that only exists on **one of the alternatives** if the static type of `ex` does not guarantee that method exists. When you truly need type-specific behavior for each type, split them into separate `catch` blocks or perform proper type checks inside the handler block.

### The multi-catch parameter cannot be reassigned

The following code **does not compile**:

~~~java
// Example illustrating the error when reassigning a multi-catch parameter.
try {
    performOperation();
} catch (IOException | SQLException ex) {
    ex = new IOException("thay thế");
}
~~~

The multi-catch parameter `ex` is treated as effectively final by Java's rules. If you need to create a new exception to propagate outward, write `throw new ...` or store the new reference in **another variable**. You should not replace the original object reference and accidentally lose diagnostic information.

Variable reassignment is unrelated to the supertype–subtype rule, but it is a common mistake when converting multiple `catch` blocks into a multi-catch.

### You cannot use both a supertype and a subtype to "provide more methods"

If you want to call an API specific to `FileNotFoundException`, adding `IOException` to the `|` list does not help; it only causes a compile-time error. The right choice is to catch `FileNotFoundException` in a separate branch, or work with the supertype's common interface when appropriate.

## 11. `throw ex` inside multi-catch and checked exception checking

The statement `throw ex;` rethrows **the exact exception object** that was caught. Even when the alternatives in a multi-catch are valid, the compiler must still ensure that any checked exceptions that can be propagated are caught or declared.

Example:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Illustrative snippet inside a class.
static void process() throws IOException, SQLException {
    try {
        operation(); // May throw IOException or SQLException.
    } catch (IOException | SQLException ex) {
        System.err.println("Không hoàn thành");
        throw ex;
    }
}
~~~

This is an **illustrative snippet** that requires defining `operation()` with an appropriate signature. Java supports relatively precise rethrow analysis in certain cases, and in this example `throws IOException, SQLException` covers the checked exceptions that must be declared.

You must not change the example to `catch (IOException | FileNotFoundException ex)` just because both types can be thrown by `operation()`: the supertype–subtype relationship is still a multi-catch syntax/type error, regardless of whether you intend to rethrow.

Distinguish between:

- **`throw ex`**: rethrows the caught object without creating a new exception.
- **`throw new SomeException(..., ex)`**: creates a new exception, preserving `ex` as the cause when the constructor supports it.
- **`throws IOException, SQLException`**: declares checked exceptions that may escape from the method, using commas. The multi-catch rule prohibiting supertype–subtype pairs **is not a rule prohibiting all `throws` lists**.
- **`catch (A | B ex)`**: a list of alternatives in *one handler branch*, using `|` and prohibiting any supertype–subtype relationship between the alternatives.

If you only want to handle an `IOException` family and then rethrow, `catch (IOException ex) { throw ex; }` is sufficient; there is no need to list all subclasses.

## 12. Choosing between multi-catch and multiple separate `catch` blocks in practice

When deciding on an exception-catching structure, start from the **desired behavior**, not from the desire to cram multiple exception names onto one line.

### Case A: Handle all I/O exceptions the same way

~~~java
catch (IOException ex) {
    reportIoFailure(ex);
}
~~~

A single supertype is appropriate. This is the simplest option if all `IOException` types are handled uniformly.

### Case B: One type needs special handling, the rest share general handling

~~~java
catch (FileNotFoundException ex) {
    askForAnotherPath(ex);
} catch (IOException ex) {
    reportIoFailure(ex);
}
~~~

Two separate branches, subtype before supertype. This is the right structure when behavior differs and a general fallback branch is needed.

### Case C: Some sibling types share handling, others have a separate branch

~~~java
catch (FileNotFoundException | EOFException ex) {
    reportInputUnavailable(ex);
} catch (IOException ex) {
    reportOtherIoFailure(ex);
}
~~~

Multi-catch for types that do not inherit from each other; a separate supertype branch follows afterward. This groups specific failure conditions while still providing a fallback branch.

### Case D: Exception types from two independent families

~~~java
catch (IOException | SQLException ex) {
    reportExternalFailure(ex);
}
~~~

A single multi-catch branch can be used because the two types have no inheritance relationship. However, only combine them if they genuinely share the same handling; in some cases, database errors require a rollback whereas I/O errors require a different recovery strategy, in which case separate branches are clearer.

The method names `reportIoFailure`, `askForAnotherPath`, `reportInputUnavailable`, `reportOtherIoFailure`, and `reportExternalFailure` in the illustrative snippets must be defined before compiling; complete runnable programs have been provided in sections 6 and 7.

## 13. Common mistakes when writing or fixing multi-catch

| Mistake | Why is it wrong? | How to fix |
| --- | --- | --- |
| `catch (IOException | FileNotFoundException ex)` | The subtype is in the same multi-catch as the supertype. | Catch only `IOException`, or split into two `catch` blocks in the right order. |
| `catch (IllegalArgumentException | NumberFormatException ex)` | `NumberFormatException extends IllegalArgumentException`. | Catch `IllegalArgumentException` if handled uniformly, or catch the specific type in an earlier separate branch. |
| Swapping to `FileNotFoundException | IOException` to try to fix the error | The rule does not depend on the order of alternatives. | Change the structure, not just the permutation. |
| Putting `catch (IOException)` before `catch (FileNotFoundException)` | The second separate branch is shadowed by the supertype branch. | Move `FileNotFoundException` before `IOException`. |
| Using `catch (Exception | IOException ex)` | `IOException` is a subclass of `Exception`. | Choose the needed supertype, or split into branches with distinct behavior. |
| Thinking two types with the same parent class cannot be combined | All classes share a common ancestor; what is prohibited is two alternatives inheriting from **each other**. | `FileNotFoundException | EOFException` is valid regarding the subtype rule. |
| Using `||` or a comma between `catch` types | Invalid multi-catch syntax. | Use a single `|` between alternatives. |
| Merging errors that have different handling policies | A single block makes it hard to distinguish behavior and can obscure information. | Use separate `catch` blocks when needed. |
| Using an overly broad supertype just to make the code compile | It may catch additional errors outside the intended scope of handling. | Choose a supertype appropriate to the actual error scope. |
| Reassigning the multi-catch parameter `ex` | The multi-catch parameter is effectively final. | Use another variable or throw a new exception as intended. |
| Assuming the program will run just because the two types do not inherit from each other | Checked exceptions and other constraints are still checked. | Verify the entire `try` block, `catch` branches, `throws` clauses, and imports. |

A quick tip before writing a multi-catch: for **every pair of types placed on either side of `|`**, ask "Can A be assigned to a variable of type B, or can B be assigned to a variable of type A, due to inheritance?" If yes, that signals a subtype relationship, and they should not be placed in the same multi-catch branch.

## 14. Self-check exercises

**Exercise 1.** Why is `catch (IOException | FileNotFoundException ex)` invalid?

**Answer:** `FileNotFoundException` inherits from `IOException`. An object of type `FileNotFoundException` already matches `IOException`, so the two alternatives cannot be placed in the same multi-catch.

**Exercise 2.** Does changing the order to `catch (FileNotFoundException | IOException ex)` fix it?

**Answer:** No. The supertype–subtype relationship still exists regardless of order.

**Exercise 3.** If `FileNotFoundException` needs a specific message while other `IOException` types need a general message, what should you write?

**Answer:** Two separate branches: `catch (FileNotFoundException ex) { ... }` first, and `catch (IOException ex) { ... }` second.

**Exercise 4.** Does `catch (FileNotFoundException | EOFException ex)` violate this rule?

**Answer:** No. Both types are independent subclasses of `IOException`; neither is a subclass of the other. The program must still satisfy the remaining checks for checked exceptions.

**Exercise 5.** Is `catch (IllegalArgumentException | NumberFormatException ex)` valid?

**Answer:** No; `NumberFormatException` inherits from `IllegalArgumentException`.

**Exercise 6.** If you only want one handler for all `IOException` types, what should you do?

**Answer:** Use a single `catch (IOException ex)`. There is no need to list the subclasses.

**Exercise 7.** Can you have `catch (FileNotFoundException | EOFException ex)` followed by `catch (IOException ex)`?

**Answer:** Yes, provided the `try` block and other rules are satisfied. The supertype is in a **separate** subsequent branch, not in the same `|` list.

**Exercise 8.** Is `throws IOException, FileNotFoundException` prohibited by the multi-catch rule?

**Answer:** No. `throws` and `catch (A | B)` have different syntax and rules; however, declaring both a supertype and a subtype in `throws` is usually redundant in terms of error scope.

**Exercise 9.** Is `catch (Exception | RuntimeException ex)` valid?

**Answer:** No, because `RuntimeException` is a subclass of `Exception`.

**Exercise 10.** When does fixing an invalid multi-catch by splitting it into two separate `catch` blocks make more sense than removing the subtype?

**Answer:** When the specific error must be handled differently from general errors—for example, letting the user choose a new path when a file is missing while reporting a system error for other `IOException` types.

## References

- [Java Language Specification 17, §14.20 — The `try` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): `catch` syntax rules, multi-catch, validity of alternatives, and handling.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checking checked exceptions that may be thrown and caught.
- [Oracle Java Tutorials — Catching Multiple Exception Types and Rethrowing Exceptions](https://docs.oracle.com/javase/tutorial/essential/exceptions/multiple.html): multi-catch examples and why alternatives with a subtype relationship are disallowed (written for Java 7/8; the rule still applies in Java 17).
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html), and [EOFException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html): reference for inheritance relationships among I/O types.

**Key takeaway:** in **one** `catch (A | B ex)`, A and B must not have a supertype–subtype relationship. If you need to catch the entire branch uniformly, catch the **supertype**; if you need separate handling, write **separate `catch` blocks in subtype-before-supertype order**; if two types are independent and share the same logic, use **multi-catch**.
