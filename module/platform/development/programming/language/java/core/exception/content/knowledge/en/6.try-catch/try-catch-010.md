# Rules for Catching a Checked Exception That the `try` Block Cannot Throw in Java

> **Topic:** Java Core → Exception → Try and catch. Java does not allow arbitrarily declaring a `catch` for a **specific checked exception** if compile-time analysis shows that the corresponding `try` block cannot throw a compatible checked exception. This is a rule about **compile-time program validity**, distinct from the question of "whether the exception actually occurs during a given run." The rule has an important exception for `catch (Exception)` and supertypes of `Exception`, typically `catch (Throwable)`.

## 1. Core Answer

Consider an example inside a Java method:

```java
try {
    int value = Integer.parseInt("123");
    System.out.println(value);
} catch (java.io.IOException e) {
    System.out.println("Lỗi I/O");
}
```

The snippet above **does not compile**. `Integer.parseInt(String)` does not declare throwing a checked `IOException`; `System.out.println` does not declare a checked `IOException` either. `Integer.parseInt` can throw an unchecked `NumberFormatException`, but that exception does not belong to the `IOException` hierarchy.

The compiler may report something similar to:

```text
exception IOException is never thrown in body of corresponding try statement
```

The exact message depends on the compiler/JDK; do not treat this as program stdout.

If you want to catch number-parsing errors, use the appropriate handler:

```java
try {
    int value = Integer.parseInt("abc");
    System.out.println(value);
} catch (NumberFormatException e) {
    System.out.println("Giá trị nhập không phải số nguyên");
}
```

The corrected snippet compiles; in the `"abc"` case, the `NumberFormatException` branch is selected.

**Practical rule:** for a specific checked exception such as `IOException`, `SQLException`, `ParseException`, `InterruptedException`, or a custom subclass of `Exception`, the compiler requires the `try` block to be capable of throwing a checked exception that the handler can catch, except for the special language exception described in Section 4.

## 2. What Is a Checked Exception?

Every object thrown in Java belongs to the `java.lang.Throwable` hierarchy. There are two major branches:

```text
java.lang.Throwable
├── java.lang.Error
│   └── AssertionError
└── java.lang.Exception
    ├── java.io.IOException
    │   ├── java.io.FileNotFoundException
    │   └── java.io.EOFException
    ├── java.text.ParseException
    ├── java.lang.InterruptedException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        │   └── java.lang.NumberFormatException
        └── java.lang.NullPointerException
```

The categories are distinguished as follows:

- **Unchecked exceptions:** `RuntimeException` and its subclasses, `Error` and its subclasses. Code can throw them without declaring `throws`; the compiler does not force the caller to catch or declare them.
- **Checked exceptions:** other subclasses of `Throwable` outside the `RuntimeException` and `Error` branches. For example, `IOException`, `Exception`, `Throwable`, and a class directly extending `Throwable`. When they can escape, the catch-or-declare rule applies.
- **`Exception` is not synonymous with checked:** `NumberFormatException` is an `Exception`, yet it is still unchecked because it inherits from `RuntimeException`.

It is necessary to distinguish **two** checks:

1. When a method can let a checked exception escape, the caller must generally **`catch` or declare `throws`** appropriately.
2. When a `catch` declares a specific checked type, the compiler also checks whether the `try` block is **capable of throwing a compatible checked exception**.

This article focuses on the second check while explaining commonly misunderstood cases.

## 3. What Exactly Does the Compiler Check?

According to the `try`/`catch` rules in the Java Language Specification (JLS 14.20), for a checked type `E` that a handler can catch, the program may fail to compile if the `try` block cannot throw a checked exception with a compatible type relationship to `E`. There is a **special exception** when `E` is `Exception` or a **superclass of `Exception`**.

In practical terms:

- `catch (IOException e)` requires the `try` block to have a path that can throw a related checked type (such as `IOException`, a subtype like `FileNotFoundException`, or a broad declared type like `Exception` that could hold an `IOException`).
- `catch (ParseException e)` is invalid if the `try` block only calls methods that do not declare a compatible checked type and does not throw such a type itself.
- `catch (RuntimeException e)` is valid even if the `try` block has no line that "obviously" throws an unchecked exception.
- `catch (Exception e)` is valid even when the `try` block does not declare throwing any checked exception.
- `catch (Throwable t)` is also valid in the same situation, though catching that broadly is usually inappropriate at the business logic layer.

**This is not an analysis that proves an exception will definitely occur at runtime.** The compiler relies primarily on the exception types that expressions, calls, resources, and language constructs **can throw** according to their static contracts, together with specific flow-analysis rules. A method declaring `throws IOException` might always return normally in its current implementation, yet the caller can still validly write `catch (IOException)`.

### 3.1. Compilation Prediction Table

Evaluate each `try`/`catch` pair independently:

| Code in `try` | Handler | Result | Reason |
| --- | --- | --- | --- |
| `System.out.println("Hi");` | `catch (IOException e)` | **Compile error** | No compatible checked `IOException` from the `try` block. |
| `Integer.parseInt("abc");` | `catch (NumberFormatException e)` | Valid | `NumberFormatException` is unchecked; it can be caught. |
| `System.out.println("Hi");` | `catch (RuntimeException e)` | Valid | Unchecked exceptions are not restricted by the specific checked catch rule. |
| `System.out.println("Hi");` | `catch (Exception e)` | Valid | `Exception` is a case specially permitted by the JLS. |
| `System.out.println("Hi");` | `catch (Throwable t)` | Valid | `Throwable` is a superclass of `Exception`. |
| `readFromFile();` with `throws IOException` | `catch (IOException e)` | Valid | The callee method signature declares a path that can throw `IOException`. |
| `readFromFile();` with `throws IOException` | `catch (FileNotFoundException e)` | Valid if remaining handlers/declarations cover the checked exceptions | `FileNotFoundException` is a subtype that may fall under the declared `IOException`. |
| `readFromFile();` with `throws IOException` | `catch (SQLException e)` | Error if no other `SQLException` source exists | Two different checked branches, incompatible. |

In the case where a handler only catches the `FileNotFoundException` subtype from a method declaring `throws IOException`, the compiler still requires the code to handle the **remaining `IOException` possibilities** via a subsequent handler or `throws IOException` on the enclosing method. The fact that a handler can validly exist does not by itself mean all checked exceptions have been handled.

## 4. Why `catch (Exception)` and `catch (Throwable)` Usually Do Not Trigger a "never thrown" Error

This is an important exception to remember accurately:

```java
try {
    System.out.println("Hello");
} catch (Exception e) {
    System.out.println("Có Exception");
}
```

This snippet **compiles validly**, even though `println` does not declare throwing a checked `Exception`. `catch (Exception)` covers `RuntimeException` as well; more importantly, the JLS has a direct exception for `Exception` and its superclasses in the "checked exception not thrown" check. `catch (Throwable)` also falls under this exception.

Compare that with:

```java
try {
    System.out.println("Hello");
} catch (java.io.IOException e) {
    System.out.println("Có IOException");
}
```

This is **invalid**, because `IOException` is a specific checked subtype and the `try` block cannot throw a compatible checked exception.

Do not deduce that because `Exception` is checked, `catch (Exception)` must be forbidden. This is a **defined exception in the compilation rules**, not a compiler bug. Likewise, the validity of `catch (Throwable)` does **not** mean it is a safe handler for a program: it can also catch `Error`, which business code should not swallow.

### 4.1. Syntactic Validity Does Not Mean the Handler Will Run

```java
try {
    System.out.println("OK");
} catch (Exception e) {
    System.out.println("Không mong đợi");
}
```

For the example above alone, normal stdout is:

```text
OK
```

The handler does not run because no `Exception` is thrown during that run. Java allows declaring this handler, but it does not manufacture an error to trigger it.

### 4.2. Do Not Confuse with a Handler Shadowed by a Supertype

The following snippet is **still invalid**, even though `catch (Exception)` is a special case:

```java
try {
    System.out.println("Hello");
} catch (Exception e) {
    System.out.println("Exception");
} catch (RuntimeException e) {
    System.out.println("RuntimeException");
}
```

The trailing `RuntimeException` handler is already covered by `Exception`, so the compiler reports that the handler is unreachable. **Two separate rules** coexist:

- The rule: "can the `try` block throw the checked exception that the `catch` accepts?"
- The rule: "is this handler completely covered by an earlier handler?"

Even though it is exempt from the first rule, `catch (Exception)` can still make subsequent handlers unreachable.

## 5. Java 17 Program: Valid Handlers Even Without Checked Exceptions

Create the file `LegalCatchWithoutCheckedDemo.java`:

```java
public class LegalCatchWithoutCheckedDemo {
    static void inspect(boolean bad) {
        try {
            int value = bad
                    ? Integer.parseInt("không-phải-số")
                    : Integer.parseInt("20");
            System.out.println("Giá trị: " + value);
        } catch (NumberFormatException e) {
            System.out.println("Lỗi parse: "
                    + e.getClass().getSimpleName());
        } catch (Exception e) {
            System.out.println("Exception khác: "
                    + e.getClass().getSimpleName());
        } finally {
            System.out.println("Hoàn tất lượt kiểm tra");
        }
    }

    public static void main(String[] args) {
        inspect(false);
        inspect(true);
    }
}
```

Compile and run commands:

```bash
javac -encoding UTF-8 LegalCatchWithoutCheckedDemo.java
java LegalCatchWithoutCheckedDemo
```

Exact stdout:

```text
Giá trị: 20
Hoàn tất lượt kiểm tra
Lỗi parse: NumberFormatException
Hoàn tất lượt kiểm tra
```

Why are both `catch` blocks valid?

1. `NumberFormatException` belongs to the unchecked `RuntimeException` branch.
2. `catch (Exception)` is allowed even though the `try` block has no declared checked exception.
3. The narrower `NumberFormatException` handler is placed before the broader `Exception` handler to avoid an unreachable handler error.
4. `finally` normally executes after each run, even when an exception is caught. In this example it prints one line after both cases.

The program has no checked exceptions on the parsing path; there is no need for `throws IOException` or an artificial `catch IOException`.

## 6. Invalid Case: Catching `IOException` When `try` Only Processes In-Memory Data

The following example is a program that **intentionally does not compile**; save it as `InvalidCheckedCatchDemo.java` only if you want to observe the compiler diagnostic:

```java
import java.io.IOException;

public class InvalidCheckedCatchDemo {
    public static void main(String[] args) {
        try {
            int number = Integer.parseInt("123");
            System.out.println(number);
        } catch (IOException e) {
            System.out.println("I/O thất bại");
        }
    }
}
```

Run the check command:

```bash
javac -encoding UTF-8 InvalidCheckedCatchDemo.java
```

**Expected result:** `javac` does not produce a valid program because `IOException` is never thrown from the corresponding `try` block. The `Integer.parseInt` path can throw `NumberFormatException` (unchecked), not a checked `IOException`. You should not predict stdout, because the program does not compile.

### 6.1. Fix According to the Error That Can Actually Occur

If the goal is to handle unparseable input, fix the handler:

```java
catch (NumberFormatException e) {
    System.out.println("Không thể chuyển thành số");
}
```

This is a **replacement handler snippet**, not standalone outside `try`. If you want to read data from a file, actually use a reading API that can throw `IOException` (and consider try-with-resources) rather than adding an unrelated checked handler.

### 6.2. Do Not Fix by Writing `throws IOException` on the Method Containing `try`

Merely adding:

```java
public static void main(String[] args) throws java.io.IOException {
    // The try block only parses a number.
}
```

**does not make the inner `catch (IOException)` valid**. `throws` on the outer method only declares exceptions that can **escape the method**; it does not make the statements inside `try` suddenly capable of throwing `IOException`.

Conversely, changing **the signature of a callee method actually invoked inside `try`** can change the checked-catch check because the `try` block now contains a call declaring the corresponding checked type.

## 7. A Call with `throws` Makes `catch` Valid Even When a Run Has No Error

Create `DeclaredThrowsCatchDemo.java`:

```java
import java.io.IOException;

public class DeclaredThrowsCatchDemo {
    static String readConfig(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("Không có cấu hình");
        }
        return "ready";
    }

    public static void main(String[] args) {
        for (boolean fail : new boolean[] {false, true}) {
            try {
                System.out.println("Cấu hình: " + readConfig(fail));
            } catch (IOException e) {
                System.out.println("Lỗi đọc: " + e.getMessage());
            }
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 DeclaredThrowsCatchDemo.java
java DeclaredThrowsCatchDemo
```

Stdout:

```text
Cấu hình: ready
Lỗi đọc: Không có cấu hình
```

- `readConfig` declares `throws IOException`.
- On the `false` iteration, there is no exception: Java does not require a handler to actually execute to be considered valid.
- On the `true` iteration, `IOException` is actually thrown: the corresponding handler runs.
- Whether `try` can throw a checked exception is evaluated from the `readConfig(fail)` call and the method's signature, not from whether the programmer "knows in advance" which branch a given run will take.

### 7.1. An Implementation That Does Not Actually Throw Still Declares `throws`

A method can be written as:

```java
static String cachedValue() throws java.io.IOException {
    return "cached";
}
```

A direct caller can catch `IOException` around the `cachedValue()` call, even though the current body only returns a string. The caller's compiler relies on the **method's declared contract**. In production code, keep signatures reflective of actual failure possibilities or interface contracts and avoid needlessly declaring broad checked exceptions; however, language validity does not depend on whether a particular run actually throws.

## 8. Inheritance Relationships: `try` Can Throw a Supertype or Subtype

The checked type in `throws` does not have to be **the exact same** name as in `catch`.

A valid and meaningful example:

```java
static void load() throws java.io.IOException {
    throw new java.io.FileNotFoundException("Thiếu file");
}
```

The caller can use:

```java
try {
    load();
} catch (java.io.FileNotFoundException e) {
    System.out.println("Chọn tệp khác");
} catch (java.io.IOException e) {
    System.out.println("I/O khác");
}
```

The snippets above illustrate a method and call site; they need to be placed in an appropriate class/method context. Although `load()` declares `throws IOException`, it can in fact throw `FileNotFoundException` — a subclass. Placing the subtype handler before the supertype handler is valid. The remaining `IOException` handler handles any other `IOException` that may arise under the contract.

### 8.1. Catching a Subtype of a Broadly Declared Checked Type

Suppose `read() throws IOException`; you can write `catch (EOFException)` before `catch (IOException)` even though the signature only says `IOException`. Reason: an `EOFException` object is also an `IOException`, so that checked path **is not excluded by the supertype declaration**.

Similarly, if `operation() throws Exception`, the `try` block may be considered capable of throwing `IOException` or `ParseException` at the type level, but **the caller must still handle the remaining `Exception`**. You cannot write handlers for just two subtypes and treat `throws Exception` as fully handled.

### 8.2. Catching an Unrelated Checked Type Fails

If the `try` block only calls `read() throws IOException`, then `catch (java.sql.SQLException e)` is invalid when there is no other source of checked `SQLException` in the `try` block. Sharing `Exception` as a common ancestor is not enough: `IOException` and `SQLException` are two separate branches, so throwing an `IOException` does not create a possibility of throwing `SQLException`.

**Tip:** read the ancestor chain of the exception type. A `catch (Parent)` handler catches `Child` if `Child extends Parent`. Conversely, when a method **declares a supertype** in `throws`, the compiler can allow a subtype handler because an object of the subtype still satisfies the declared supertype.

## 9. Try-with-resources: `close()` Is Also a Source of Checked Exceptions

A very easy case to overlook: even when **the `try` body itself does not read or throw a checked exception**, the **resource-closing** operation in try-with-resources can declare a checked exception. In that case, a checked handler is valid.

Create `ResourceCloseCatchDemo.java`:

```java
import java.io.IOException;

public class ResourceCloseCatchDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Đóng thất bại");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Đang thực hiện");
        } catch (IOException e) {
            System.out.println("Lỗi tài nguyên: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ResourceCloseCatchDemo.java
java ResourceCloseCatchDemo
```

Exact stdout:

```text
Đang thực hiện
Đang đóng
Lỗi tài nguyên: Đóng thất bại
```

Why is `catch (IOException)` valid even though the block body only contains `println`?

- `Resource` implements `AutoCloseable` and `close() throws IOException`.
- Try-with-resources invokes `close()` when leaving the block.
- `close()` can throw a checked `IOException`, so the construct as a whole has an error path matching the handler.
- The exception from `close()` is caught by the `catch` attached to that try-with-resources statement.

With multiple resources, Java closes them in reverse declaration order. If the block body already threw an exception and `close()` also throws, the closing error is normally recorded in `getSuppressed()` of the primary exception, rather than silently replacing the first exception.

### 9.1. Not Every `close()` Declares `IOException`

For example, `StringReader.close()` does not declare a checked `IOException`; creating a `StringReader` with a string and only calling `println` in the body will not make `catch (IOException)` valid just because the construct is try-with-resources.

What matters is the **actual type and `close()` method seen by the compiler**, along with the constructors/initializers and operations in the body. If a resource is declared using the broad type `AutoCloseable`, `close()` in that interface declares `throws Exception`; that can impose a broader checked obligation than using a concrete type with a narrower `close()` signature.

### 9.2. Errors from the Resource Initializer Are Also Considered

The resource initialization part inside `try ( ... )` can call constructors or methods that declare checked exceptions. Checked errors arising during **resource creation** also belong to the error paths that must be handled under the language rules, not only the statements inside the curly braces.

## 10. Multi-catch: Every Checked Alternative Must Still Have a Valid Reason

Multi-catch syntax:

```java
catch (java.io.IOException | IllegalArgumentException e) {
    System.out.println(e.getMessage());
}
```

This is an illustrative handler and must follow a `try` block. A multi-catch can combine multiple types that have no subtype inheritance relationship with one another when they are handled the same way.

However, adding an unchecked branch **does not validate** an impossible checked branch:

```java
// INTENTIONALLY INVALID IF TRY ONLY PARSES A NUMBER:
try {
    Integer.parseInt("123");
} catch (java.io.IOException | NumberFormatException e) {
    System.out.println("Có lỗi");
}
```

`NumberFormatException` is unchecked, which is fine. But `IOException` is checked and `try` cannot throw it, so the construct above is invalid.

How to fix it based on the real error sources:

- If you only parse numbers, remove `IOException` from the multi-catch.
- If `try` actually performs I/O with `throws IOException`, then the multi-catch can be valid provided the types have no subclass relationship and the handling logic is appropriate.

You **must not** combine `IOException | FileNotFoundException` in a single multi-catch, because `FileNotFoundException extends IOException`. That is a different rule from "checked exception never thrown," yet it also causes a compile-time error.

### 10.1. Java 17 Program with Two Types That Can Actually Occur

Create `MultiCatchCheckedDemo.java`:

```java
import java.io.IOException;

public class MultiCatchCheckedDemo {
    static void handle(String text) throws IOException {
        if (text == null) {
            throw new IOException("Thiếu nguồn");
        }
        System.out.println("Số: " + Integer.parseInt(text));
    }

    public static void main(String[] args) {
        for (String text : new String[] {"8", "abc", null}) {
            try {
                handle(text);
            } catch (IOException | NumberFormatException e) {
                System.out.println("Lỗi: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 MultiCatchCheckedDemo.java
java MultiCatchCheckedDemo
```

Stdout:

```text
Số: 8
Lỗi: NumberFormatException
Lỗi: IOException
```

This is a valid multi-catch case: `handle` declares `throws IOException`, while `Integer.parseInt` inside can throw unchecked `NumberFormatException`. The two types have no parent-child relationship and share the same error-display strategy.

The exception variable of a multi-catch is **implicitly final**; it cannot be reassigned. When different handling logic is needed for the two types, separating them into two distinct handlers makes the contract clearer.

## 11. Nested `try`, Already-Handled `catch`, and `finally`

The question "which checked types can the `try` block throw?" must be asked within the **exact scope** to which the handler is attached.

### 11.1. Exception Already Caught in an Inner `try`

Illustrative snippet:

```java
try {
    try {
        throw new java.io.IOException("Đã có lỗi");
    } catch (java.io.IOException handled) {
        System.out.println("Đã xử lý ở trong");
    }
} catch (java.io.IOException e) {
    System.out.println("Bắt ở ngoài");
}
```

The snippet above **intentionally does not compile** because `IOException` was already handled inside, leaving no checked `IOException` path escaping the outer `try` body. The outer handler cannot receive `IOException` from this situation.

If the inner handler did `throw handled;` or the outer `try` block actually called another operation that could throw `IOException`, the evaluation would differ. The compiler checks whether the exception can **escape** the inner construct, rather than simply counting occurrences of `throw` at every level.

### 11.2. New Exception Thrown in a Sibling `catch`

Consider:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    throw new java.io.IOException("Lỗi chuyển đổi", e);
} catch (java.io.IOException e) {
    System.out.println("Không bắt lỗi vừa ném từ catch bên trên");
}
```

The fragment above **intentionally does not compile** if those are the only error sources: the last `IOException` handler does not catch a new exception thrown inside another `catch` of the same `try`; at the same time, the enclosing method must handle or declare the checked `IOException` created by the first handler.

A new exception thrown inside a handler must be handled by a **new `try` or an outer scope**, or else declared to propagate. The `catch` clauses of the same `try` are alternative branches, not a sequential handler chain.

### 11.3. Exception Arising in `finally`

An exception thrown in the `finally` block of the same construct is not handled by the accompanying `catch` handlers as if it came from the `try` body. It can propagate to the caller or an outer handler.

Illustrative method example:

```java
static void cleanup() throws java.io.IOException {
    try {
        System.out.println("Làm việc");
    } finally {
        throw new java.io.IOException("Lỗi khi dọn dẹp");
    }
}
```

The method must declare `throws IOException`; you cannot add `catch (IOException)` to the sibling `try` handler chain to handle the exception produced by that `finally`. To handle it locally, use an appropriate nested `try` at the cleanup site or let the caller handle it per the contract.

**Do not confuse `finally` with try-with-resources:** with try-with-resources, checked errors from `close()` can be handled by the `catch` attached to that construct.

## 12. Why the Compiler Needs This Rule

A `catch (IOException)` after a `try` block that only computes integers usually expresses a wrong contract: the code in the `try` block does not interact with an I/O source according to static type information. The rule helps catch:

1. **Wrong exception type:** the author confused `NumberFormatException` with `IOException`.
2. **Stale refactoring:** an I/O call was replaced with in-memory computation, but the old handler remained.
3. **Misunderstanding `throws`:** the author thought adding `throws` to the enclosing method makes any `catch` valid.
4. **Scope confusion:** an exception arises in `catch` or `finally`, yet the author expected a sibling handler to receive it.
5. **Redundant checked types in multi-catch:** lumping in errors that have no source.

On the other hand, because the rule is based on **possibility according to static types** (not guaranteed outcomes on every run), the compiler can still allow a handler that never actually runs—for instance, a callee method declaring `throws IOException` whose implementation currently always succeeds. That is how signatures and API compatibility are preserved.

## 13. Distinguishing from Similar Compile Errors

| Error | Example Idea | Nature |
| --- | --- | --- |
| "exception X is never thrown in body of corresponding try" | `catch(IOException)` after pure number parsing | Specific checked handler has no compatible source. |
| "unreported exception X; must be caught or declared" | Calling `readLine()` without catching/declaring `IOException` | A checked exception can escape and has not been handled properly. |
| "exception X has already been caught" | `catch(Exception)` placed before `catch(IOException)` | Earlier handler shadows a later handler. |
| "Alternatives in a multi-catch statement cannot be related by subclassing" | `catch(IOException \| FileNotFoundException)` | Two types in the same multi-catch have a parent-child relationship. |
| "unreachable statement" | Normal statement right after an unconditional `throw` | Execution flow cannot reach that statement. |
| "incompatible types ... cannot be converted to Throwable" | `throw "error";` | Expression after `throw` is not a valid throwable type. |

When encountering an error, read the **key phrase** and check the type relationship between the error source in `try` and the handler; do not fix it by slapping `catch (Exception)` everywhere without knowing what needs to be handled.

## 14. Common Mistakes and How to Fix Them

### 14.1. "Any `catch` is valid because the JVM can encounter unexpected errors"

Not true for specific checked exceptions. A source can throw unchecked `RuntimeException` or `Error`, but that does not create a possibility of throwing `IOException` under the checked contract. `catch(IOException)` still needs a basis in the `try` block.

### 14.2. "`catch (Exception)` must be forbidden if `try` does not throw a checked exception"

Not true. `catch (Exception)` is specially permitted by the language; it can also handle unchecked `RuntimeException`. Similarly, `catch (Throwable)` still compiles, though it is usually too broad for the business layer.

### 14.3. "Writing `throws IOException` on the current method is enough to catch `IOException`"

No. `throws` describes checked exceptions **escaping the method**; it does not change the contents or throwing capability of an inner `try`. Read exactly which methods are called inside `try` and their signatures.

### 14.4. "If the code only creates `FileNotFoundException`, then `catch(IOException)` is forbidden because the names differ"

False. `FileNotFoundException extends IOException`; a supertype handler can catch a subtype. Compiler rules allow compatible type relationships rather than requiring identical names.

### 14.5. "If `try` calls a method that throws `IOException`, `catch(SQLException)` is also valid because both are checked"

False. The two branches are unrelated; no checked `SQLException` source is declared, so that specific handler is invalid in the stated context.

### 14.6. "Try-with-resources only considers statements inside the curly braces"

False. Both the resource initializer and `close()` can throw checked exceptions. `catch(IOException)` can be completely valid when the block body only prints a string, if the resource's `close()` declares `throws IOException`.

### 14.7. "If a checked exception appears in a nested `try`, the outer `catch` is always valid"

False. If the inner `catch` already handled it and did not rethrow, the corresponding checked exception cannot escape into the outer `try` block. You must trace the **actual structural propagation path**, not just search for the text `throw IOException` in the file.

### 14.8. "An exception thrown in `catch` will be caught by the next handler"

False. Sibling handlers are alternatives for exceptions escaping the **`try` body**. A new exception inside `catch` must be handled in another scope or declared to propagate.

### 14.9. "The compiler always proves whether a callee method can actually throw"

No. The compiler uses the callee method's signature and exception analysis rules. An implementation with `throws IOException` whose body only executes `return` is still enough to create a checked possibility for the caller. This is a compatibility mechanism when using libraries/interfaces.

### 14.10. "Fix compile errors by swallowing all exceptions"

You should not. Remove the unrelated `IOException` from the handler when the error source is number parsing, or place the handler at the layer that actually performs I/O. Catching and ignoring errors can mislead the caller into thinking the operation succeeded while state may have been partially modified.

## 15. Self-Check Exercises

### Exercise 1 — Valid or Invalid?

Evaluate the following `try/catch` snippets independently (placed inside an appropriate method).

**A.**

```java
try {
    System.out.println(10 / 2);
} catch (java.io.IOException e) {
    System.out.println("I/O");
}
```

**Answer:** invalid. The `try` block has no checked `IOException` source.

**B.**

```java
try {
    System.out.println(10 / 2);
} catch (Exception e) {
    System.out.println("Exception");
}
```

**Answer:** valid; `Exception` is a special exception to the rule.

**C.**

```java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException e) {
    System.out.println("Bad number");
}
```

**Answer:** valid; `NumberFormatException` is unchecked. When run, it prints `Bad number`.

**D.**

```java
try {
    Thread.sleep(1);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
```

**Answer:** valid; `Thread.sleep` declares checked `InterruptedException`. When catching interruption, restoring the interrupt flag may fit the task-cancellation policy; the example has no fixed stdout because it depends on thread interruption.

### Exercise 2 — Replace the Call and Observe the Compiler

Create a method `static String read() throws IOException`, then place a call to it inside a `try` with `catch(IOException)`. Afterward, replace the call with `return "OK"` or `println("OK")` inside the `try` block. Why does the checked handler become invalid? Removing the source capable of throwing the checked exception changes the contract within that scope.

### Exercise 3 — Supertype and Subtype

A method declares `throws IOException` and internally can throw `EOFException`. Write a `catch(EOFException)` handler before `catch(IOException)`. Explain why both are valid and why the second handler is still needed to handle other kinds of `IOException`.

### Exercise 4 — Resource Closing Error

Run `ResourceCloseCatchDemo`, then modify `Resource.close()` so it does not declare or throw `IOException` and only prints `"Đang đóng"`. Is there any checked `IOException` source left in `try`? If not, `catch(IOException)` becomes invalid. Fix the handler so the program compiles again while still closing the resource.

### Exercise 5 — Multi-catch

Why is `catch(IOException | NumberFormatException)` valid in `MultiCatchCheckedDemo` yet invalid when the `try` block only calls `Integer.parseInt(...)`? Explain two points separately: the checked `IOException` source and the unchecked `NumberFormatException`.

### Exercise 6 — Exception Handled Inside

Use the nested `try` from Section 11.1. Add `throw handled;` in the inner handler (and declare or handle it validly in the outer scope). Explain why rethrowing allows the outer `catch(IOException)` to receive the exception, instead of the inner handler completing normally.

## 16. Checklist Before Adding a Checked `catch`

- [ ] Do I know whether the exception to catch is checked or unchecked?
- [ ] Is there a call, `throw`, or resource in the **exact `try` block** that can throw a compatible checked exception?
- [ ] Have I considered the resource initializer and `close()` of try-with-resources?
- [ ] Have I checked the parent-child relationship between the type in `throws` and the `catch` type?
- [ ] Is the exception already completely handled by a nested `catch` before reaching this handler?
- [ ] Does the exception actually arise in a sibling `catch`/`finally`, outside the scope protected by this handler?
- [ ] Did I confuse an unchecked exception from a parser with a checked `IOException`?
- [ ] Am I aware of the special rule for `catch(Exception)` and `catch(Throwable)` while still choosing an appropriate catch scope?
- [ ] For multi-catch, does every checked alternative have a basis, and are the types non-overlapping?
- [ ] If I only need to report invalid input, have I chosen the right exception type instead of adding an unrelated checked handler?
- [ ] Are the handlers ordered from specific to general with no unreachable branches?
- [ ] Does the code still distinguish failure from success per contract without swallowing important errors?

**Takeaway:** the compiler does not allow catching a **specific checked exception** when the `try` block cannot throw a compatible checked exception, with the language exception for `Exception` and its supertypes. Examine the **exception sources by type signature and `try` scope** before deciding on a handler; avoid creating redundant `catch` blocks or replacing every error with an overly broad handler.
