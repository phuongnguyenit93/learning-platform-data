# Variable Scope in `try` and `catch` Parameters in Java

A Java exception-handling snippet can **fail to compile even when the exception is caught completely correctly**, simply because a variable was declared in a scope that is no longer active, or because the compiler cannot prove the variable was assigned a value before use. To write clean and safe `try/catch` blocks, you need to distinguish three issues:

1. **Scope (name visibility)**: from where to where can a variable be referred to by name?
2. **Lifetime (data/object lifespan)**: when exiting a block, is the referenced object necessarily destroyed?
3. **Definite assignment**: at a point where a local variable is read, can the compiler prove the variable has received a value on every execution path that can reach that point?

`try`, `catch`, and `finally` are blocks with their own curly braces. **A local variable declared inside a `try` body is not visible in the `catch` or `finally` body**. Conversely, a local variable declared before `try` in the same enclosing scope can be used inside the sub-blocks, provided it is validly assigned. **A `catch (SomeException e)` parameter is only in scope within its corresponding `catch` body**, not in `try`, other handlers, or statements after the construct.

This lesson focuses on variable scope around `try/catch` in Java 17+, explaining both compile-time errors and how to design code so that exception handling does not lose data or mask failure signals.

## 1. Scope Map of `try`, `catch`, `finally`

Consider the following skeleton code. This illustrates scope rules; the methods named `work`, `recover`, and `cleanup` are not defined, so this snippet is not a standalone program:

```java
String shared = "trước try";       // Enclosing scope

try {
    int onlyInTry = 10;          // Only belongs to the try block
    work(shared, onlyInTry);
} catch (IllegalStateException problem) {
    recover(shared, problem);    // shared and problem are visible here
    // onlyInTry: NOT visible
} finally {
    cleanup(shared);             // shared is visible here
    // onlyInTry and problem: NOT visible
}

System.out.println(shared);      // shared is still visible
// onlyInTry and problem: NOT visible
```

| Variable | Where is it declared? | In `try` | In `catch` | In `finally` | After the construct |
| --- | --- | --- | --- | --- | --- |
| `shared` | Before `try`, in the enclosing block | Yes | Yes | Yes | Yes, until the end of the enclosing scope |
| `onlyInTry` | Inside the `try` body | Yes, from declaration to the end of its scope | No | No | No |
| `problem` | `catch` parameter | No | Yes, inside that handler's body | No | No |
| Variable declared in `catch` | Inside the `catch` body | No | Only that handler itself | No | No |
| Variable declared in `finally` | Inside the `finally` body | No | No | Yes, inside `finally` | No |

**Be careful how you read the table:** "Yes" refers to *variable name visibility (scope)*; it does not assert that the variable has been validly initialized or assigned. A local variable may be visible in a block yet still be rejected by the compiler when used because it is not **definitely assigned**.

`catch` branches of the same `try` have their own separate scopes, so the same parameter name can be used across multiple handlers:

```java
try {
    operation();
} catch (java.io.IOException e) {
    System.out.println("I/O: " + e.getMessage());
} catch (IllegalArgumentException e) {
    System.out.println("Input: " + e.getMessage());
}
```

This is an **illustrative skeleton**, assuming `operation()` is a method that can throw `IOException` and `IllegalArgumentException`. Two parameters both named `e` are valid because they belong to **two separate `catch` blocks** that do not execute simultaneously.

## 2. A Variable Declared in `try` Does Not Appear in `catch`

A very common mistake is declaring a return value inside `try` and then wanting to print that value in `catch` or immediately after `try/catch`.

Example that **intentionally does not compile**:

```java
try {
    int quantity = Integer.parseInt("12");
    System.out.println(quantity);
} catch (NumberFormatException e) {
    System.out.println(quantity); // Error: cannot find symbol quantity
}
System.out.println(quantity);     // Error: cannot find symbol quantity
```

The name `quantity` belongs to the `try` block's scope. When the compiler analyzes the `catch` handler and the statement outside, **there is no local variable named `quantity` visible in either location**. Scope errors are checked at compile time, even if you believe that when `parseInt` succeeds, the variable has definitely been created.

How to fix this depends on your actual needs:

- If `quantity` is only needed for processing along the success path, **keep all of its usage inside `try`**; do not pull the variable outside unnecessarily.
- If the result is needed for both the success path and the exception-handling path, **declare the variable in the enclosing block** and ensure every valid path assigns a value before reading it.
- If an operation can fail and no valid numeric value exists, you can use **`OptionalInt`, a stateful result type**, or return early from the method; do not force a fallback number to pass as valid data.

**Do not try to fix it by creating another variable with the same name in `catch`** and expecting it to be the variable from `try`. Two declarations in two different scopes are **two different variables** and do not pass data between each other.

## 3. Complete Java 17 Example: Placing Variables in the Right Scope

File `TryVariableScopeDemo.java`:

```java
public class TryVariableScopeDemo {
    static void process(String input) {
        System.out.println("Input: " + input);
        try {
            int number = Integer.parseInt(input);
            System.out.println("Trong try: " + (number * 2));
        } catch (NumberFormatException e) {
            System.out.println("Trong catch: không phải số nguyên");
        }
        System.out.println("Sau try/catch");
    }

    public static void main(String[] args) {
        process("7");
        process("abc");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 TryVariableScopeDemo.java
java TryVariableScopeDemo
```

**Exact stdout** on a UTF-8 terminal:

```text
Input: 7
Trong try: 14
Sau try/catch
Input: abc
Trong catch: không phải số nguyên
Sau try/catch
```

In this example, `number` only needs to serve the successful parse path, so scoping it inside `try` is appropriate. When `"abc"` fails to convert, the exception is caught; there is no `number` value that needs to be used in the handler. The statement after the construct runs on both paths if the handler completes normally.

Notable point: **the scope of `number` does not expand after an exception is caught**. Whether an operation terminates abnormally or succeeds does not change the scope rules determined by the compiler from the source code structure.

## 4. A Variable in an Outer Block Can Be Used in Both `try` and `catch`

When both branches need to update a shared result, declare the variable before `try`:

```java
String label;

try {
    int quantity = Integer.parseInt(input);
    label = "Số lượng: " + quantity;
} catch (NumberFormatException e) {
    label = "Số lượng không hợp lệ";
}

System.out.println(label);
```

This is an **illustrative method skeleton**, assuming a `String` parameter `input` already exists. `label` is visible in both `try` and `catch` because it is declared in the enclosing block. Reading `label` after the construct can be valid because:

- If the parse call and assignment succeed, `label` is assigned in the `try` branch.
- If parsing throws `NumberFormatException` and the handler completes normally, `label` is assigned in `catch`.
- If another uncaught exception occurs, the method does not continue normally to `println`, so that path does not cause an unassigned variable to be read.

Java verifies these conditions using **definite assignment** rules, not merely by seeing an assignment somewhere in the code.

For easy verification, the following standalone program assigns the result in both branches. Save as `SharedResultDemo.java`:

```java
public class SharedResultDemo {
    static String describe(String text) {
        String result;
        try {
            int value = Integer.parseInt(text);
            result = "Hợp lệ: " + value;
        } catch (NumberFormatException e) {
            result = "Không hợp lệ";
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(describe("42"));
        System.out.println(describe("x"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 SharedResultDemo.java
java SharedResultDemo
```

Stdout:

```text
Hợp lệ: 42
Không hợp lệ
```

The variable `result` **does not need to be assigned a dummy initial value** because every path to `return result` has already assigned it. If the goal is to prevent the caller from mistaking failure for success, a result data type carrying status or returning directly from each branch can also be clearer.

## 5. Scope Differs from Definite Assignment

Two compiler errors look similar to beginners, but they have different causes:

- **Variable name out of scope**: the variable is declared inside `try` and then used in `catch`. The compiler cannot find the name at the usage site.
- **Variable might not have been assigned**: the variable is declared outside `try` and is visible in all branches, but the compiler cannot prove it has received a value before being read.

Example of the second case, **intentionally failing to compile**:

```java
int quantity;
try {
    quantity = Integer.parseInt(input);
} catch (NumberFormatException e) {
    System.out.println("Đầu vào sai");
}
System.out.println(quantity); // Variable quantity might not have been initialized
```

This is an illustrative skeleton with `input` from the enclosing scope. Because the handler can complete without assigning `quantity`, the final statement might read an uninitialized variable. The fact that `quantity` is in scope **does not make it definitely assigned**.

One fix depending on the requirement:

```java
int quantity;
try {
    quantity = Integer.parseInt(input);
} catch (NumberFormatException e) {
    throw new IllegalArgumentException("Số lượng phải là số nguyên", e);
}
System.out.println(quantity);
```

This is still an illustrative skeleton; the code after `catch` only executes when the conversion succeeds, because the handler throws a new exception instead of completing normally. Written this way, `quantity` is definitely assigned on every path that can reach the print statement. If the interface layer needs to handle input errors as an expected outcome, another approach is to return a validation status instead of converting it into a new exception.

Or assign in both branches with a specific meaning:

```java
int quantity;
try {
    quantity = Integer.parseInt(input);
} catch (NumberFormatException e) {
    quantity = 0; // Only valid if 0 is an allowed fallback by contract.
}
System.out.println(quantity);
```

Do not use `0` or `-1` as arbitrary error codes if they can be valid values; in that case, represent success/failure explicitly.

### Why Is Java Strict?

Local variables in Java **do not have a default value** merely by being declared. Fields of an object have default values according to Java's initialization rules, whereas **local variables in a method must be assigned before being read**. This distinction helps the compiler prevent many bugs involving uninitialized data.

Even if you know for sure that data will always parse successfully in a test, the compiler still does not infer that the exception branch is impossible for all runtime inputs. Your code must satisfy the execution paths permitted by the language.

## 6. Scope of the `catch` Parameter

In:

```java
catch (NumberFormatException e) {
    System.out.println(e.getMessage());
}
```

`e` is the **`catch` clause parameter**, with declared type `NumberFormatException`. It is declared by the handler's parameter section and **is in scope within that handler's block**. It does not exist as a variable that can be referenced by name from the `try` body, from `finally`, from another handler, or in statements after the entire construct.

Example that **intentionally does not compile**:

```java
try {
    Integer.parseInt(input);
} catch (NumberFormatException e) {
    System.out.println(e.getClass().getSimpleName());
} finally {
    System.out.println(e.getMessage()); // No e in finally scope
}
System.out.println(e);                 // No e in outer scope
```

If you need to pass error information to code in an outer scope, you can declare a variable in the outer scope and assign the appropriate information, but you must consider whether storing the error complicates the contract. In most cases, handle the error directly inside the handler or let the exception propagate.

**The name `e` is not mandatory**; you can use `ex`, `cause`, `error`, etc., as long as you follow Java identifier rules and the variable name does not collide in overlapping scopes. Choosing a name that expresses its responsibility is more helpful than insisting on a single character.

## 7. The `catch` Parameter Is the Error Object, Not a Copy of the Object

When a handler receives `catch (SomeException e)`, the variable `e` holds a **reference** to the thrown exception object. Java passes references by value when passing parameters; the handler parameter itself is also just a local name. This matters for scope and rethrowing:

- `throw e;` throws **the exact same exception object** referenced by `e`.
- Renaming `e` does not change the runtime type of the object.
- If you use a single-type `catch` and reassign `e` to a different object (which can be legal in some contexts), a subsequent `throw e` will throw the new object the variable points to. That is no longer rethrowing the original error.
- The `catch` parameter goes out of scope when the handler finishes, but the exception object **is not necessarily reclaimed immediately**. It may still be referenced elsewhere, such as by a wrapper exception, a logging mechanism, or a caller that catches it again.

Save `CatchReferenceDemo.java`:

```java
public class CatchReferenceDemo {
    static IllegalArgumentException original;

    static void run() {
        original = new IllegalArgumentException("Lỗi dữ liệu");
        try {
            throw original;
        } catch (IllegalArgumentException e) {
            System.out.println("Trong catch: " + (e == original));
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IllegalArgumentException outer) {
            System.out.println("Trong main: " + (outer == original));
            System.out.println("Message: " + outer.getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CatchReferenceDemo.java
java CatchReferenceDemo
```

Stdout:

```text
Trong catch: true
Trong main: true
Message: Lỗi dữ liệu
```

The names `e` in the inner handler and `outer` in the outer handler are different, yet they can reference **the same instance**. Using the `original` field in this example is only for checking identity; you should not create global state holding the "latest exception" to communicate between threads in a real program.

## 8. Sibling `catch` Handlers Have Separate Scopes

Two handlers of the same `try` statement can use the same parameter name:

```java
try {
    potentiallyFails();
} catch (java.io.IOException e) {
    System.out.println("I/O: " + e.getMessage());
} catch (IllegalArgumentException e) {
    System.out.println("Input: " + e.getMessage());
}
```

This is an illustrative skeleton, assuming `potentiallyFails()` declares/permits the corresponding exception types. Java allows both `e` names because each name only exists within its own handler's scope.

However, **you cannot create another variable with the same name `e` inside the handler body** when it collides with the existing parameter:

```java
try {
    Integer.parseInt("x");
} catch (NumberFormatException e) {
    String e = "bad"; // Compile error: variable e is already defined in this scope
}
```

Replacing `String e` with `message` will be valid.

A similar misconception is thinking that the second `catch` can read a local variable declared in the first `catch`. It cannot, because the two handlers are two independent scopes.

## 9. Shadowing and Name Collisions with Enclosing Variables

Java allows a local variable or handler parameter to **shadow** a field with the same name in a closer scope; however, it does not allow arbitrarily declaring a new local variable with the same name as a local variable already in an enclosing active scope.

### Colliding with an enclosing local variable: compile error

```java
void demonstrate() {
    String e = "đã có";
    try {
        Integer.parseInt("x");
    } catch (NumberFormatException e) { // Invalid: e already exists in outer local scope
        System.out.println(e);
    }
}
```

This is an illustrative method that **intentionally does not compile**. The `catch` parameter collides with the local variable `e` in the still-active enclosing scope. Fix it by using a different name, such as `catch (NumberFormatException cause)`.

### Colliding with a field: can be valid

Complete example in `FieldShadowDemo.java`:

```java
public class FieldShadowDemo {
    private String error = "field";

    void demonstrate() {
        try {
            Integer.parseInt("invalid");
        } catch (NumberFormatException error) {
            System.out.println("Catch: " + error.getClass().getSimpleName());
            System.out.println("Field: " + this.error);
        }
    }

    public static void main(String[] args) {
        new FieldShadowDemo().demonstrate();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 FieldShadowDemo.java
java FieldShadowDemo
```

Stdout:

```text
Catch: NumberFormatException
Field: field
```

Inside the handler, the name `error` refers to the `catch` parameter. The object's `error` field still exists and can be accessed via `this.error`. This is **field shadowing**, which differs from redeclaring a local variable inside an active nested scope.

Design principle: name handler parameters clearly to avoid confusion with object state; do not rely on shadowing when unnecessary.

## 10. Single-Type `catch` and `final` / `effectively final`

A single-type `catch` parameter such as `catch (IOException e)` can normally be reassigned if it is not declared `final`. However, **reassigning a handler parameter is usually confusing**: it loses the original reference name, can break *precise rethrow* analysis, and makes error diagnosis harder.

Compare:

```java
catch (IllegalArgumentException e) {
    // e is not reassigned: effectively final.
    throw e;
}
```

with:

```java
catch (IllegalArgumentException e) {
    e = new IllegalArgumentException("Lỗi đã bị thay");
    throw e; // Throws the new object, no longer preserving the original error's identity.
}
```

These are **two separate illustrative handler snippets**, not meant to be placed back-to-back as a standalone program. The first handler's parameter is *effectively final* because there is no reassignment; in the second handler, `e` is no longer effectively final.

You can enforce immutability of the reference with the `final` keyword:

```java
catch (final IllegalArgumentException e) {
    System.out.println(e.getMessage());
    // e = new IllegalArgumentException(); // Invalid
}
```

Distinguish between **not reassigning a reference variable** and **an immutable object**. `final` or *effectively final* only restricts the variable `e` from pointing to another instance; methods on the exception object can still mutate mutable properties, such as `addSuppressed` or `setStackTrace`.

## 11. Multi-catch: One Parameter with Multiple Types and Implicitly `final`

Java supports multi-catch:

```java
try {
    readOrParse();
} catch (java.io.IOException | IllegalArgumentException e) {
    System.out.println(e.getClass().getSimpleName());
}
```

This is an illustrative skeleton; the `readOrParse()` method must be defined for the program to compile. Here there is **one parameter `e`**, but it can receive an exception belonging to either of the declared type alternatives. Java applies the general rules of an appropriate union/lub type to check method calls on `e`.

Key points to remember:

- The parameter in a multi-catch is **implicitly final**: you cannot reassign `e`.
- The types separated by `|` must not have a direct or indirect parent–child relationship where one type is a subtype of the other; for example, `IOException | Exception` is invalid.
- The scope of `e` is still only **the multi-catch handler body**.
- The parameter holds only one concrete exception object per handler execution, not two objects simultaneously.

Complete example in `MultiCatchScopeDemo.java`:

```java
import java.io.IOException;

public class MultiCatchScopeDemo {
    static void process(String input) throws IOException {
        if (input.equals("io")) {
            throw new IOException("Hỏng nguồn");
        }
        int value = Integer.parseInt(input);
        System.out.println("Số: " + value);
    }

    public static void main(String[] args) {
        for (String input : new String[] {"4", "io", "abc"}) {
            try {
                process(input);
            } catch (IOException | NumberFormatException e) {
                System.out.println("Bắt: " + e.getClass().getSimpleName());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 MultiCatchScopeDemo.java
java MultiCatchScopeDemo
```

Stdout:

```text
Số: 4
Bắt: IOException
Bắt: NumberFormatException
```

The scope of `e` ends after the handler. If you add `e = new IOException("Khác")` inside the multi-catch, the program is rejected at compile time because this parameter is implicitly `final`.

## 12. How Does Precise Rethrow Relate to Scope and Reassigning the `catch` Parameter?

Since Java 7, when a handler parameter is `final` or *effectively final*, the compiler can perform **precise rethrow** analysis: even if the parameter is declared with a broad type like `Exception`, the set of checked exceptions that can actually be rethrown via `throw e` is narrowed based on the `try` block.

Valid example in `PreciseRethrowScopeDemo.java`:

```java
import java.io.IOException;

public class PreciseRethrowScopeDemo {
    static void read() throws IOException {
        throw new IOException("Không đọc được");
    }

    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            System.out.println("Trong catch");
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Ở caller: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 PreciseRethrowScopeDemo.java
java PreciseRethrowScopeDemo
```

Stdout:

```text
Trong catch
Ở caller: Không đọc được
```

Even though it catches `catch (Exception e)`, the `relay` method only needs `throws IOException` in this example, because `e` is not reassigned and Java determines that the checked exception that can arise from the `try` body is `IOException`. Unchecked exceptions, if any, do not need to be declared.

If `e` is reassigned in the same handler, Java cannot apply the same type-narrowing rule. For instance, the following snippet **intentionally does not compile** with a signature having only `throws IOException`:

```java
static void relayBad() throws IOException {
    try {
        throw new IOException("Lỗi gốc");
    } catch (Exception e) {
        e = new IOException("Lỗi khác");
        throw e; // Checked against the broad Exception type.
    }
}
```

This example highlights that **the scope and reassignment status of a handler parameter affect checked-exception obligations at compile time**. Do not reassign the `catch` parameter when the goal is to propagate the original exception; declare a different variable if you genuinely need to represent a new error, and declare the appropriate contract.

## 13. `try-with-resources` Has Its Own Scope for Resources

In `try-with-resources`, a resource declared in the `try` header has scope inside the **`try` block body**; it is not in scope in the attached `catch` or `finally` handlers, nor in statements after the construct.

Example that **intentionally does not compile** if the commented lines are turned into code:

```java
try (java.io.StringReader reader = new java.io.StringReader("abc")) {
    System.out.println(reader.read());
} catch (java.io.IOException e) {
    // reader.read(); // No reader in catch scope.
}
// reader.read(); // No reader after try-with-resources.
```

`reader` is declared in the resource specification, initialized before entering the `try` body, and automatically closed by Java when leaving the resource scope. The handler's parameter `e` still lives only inside the `catch` body.

A standalone program showing scope and closing order, saved as `ResourceScopeDemo.java`:

```java
public class ResourceScopeDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở: " + name);
        }

        String read() {
            return "Dữ liệu từ " + name;
        }

        @Override
        public void close() {
            System.out.println("Đóng: " + name);
        }
    }

    public static void main(String[] args) {
        String result = "Chưa có dữ liệu";

        try (Resource resource = new Resource("A")) {
            result = resource.read();
            System.out.println("Trong try: " + result);
            throw new IllegalStateException("Lỗi sau khi đọc");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally");
        }

        System.out.println("Result ngoài: " + result);
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 ResourceScopeDemo.java
java ResourceScopeDemo
```

Stdout:

```text
Mở: A
Trong try: Dữ liệu từ A
Đóng: A
Catch: Lỗi sau khi đọc
Finally
Result ngoài: Dữ liệu từ A
```

On the success path of opening and reading the resource, `result` is assigned before the `throw` statement. However, the constructor or `read()` could still fail before the assignment and jump into `catch`; initializing `result` with a fallback value helps the program satisfy **definite assignment** rules. The `resource` is closed **before** the handler executes. The scope of `resource` does not extend to the handler, but `result` is declared in the outer block so it remains visible at the end.

**Scope and cleanup are two independent concepts:** a resource goes out of scope after `try`, while the timing of calling `close()` is specifically managed by `try-with-resources`. A closed object can still be referenced from elsewhere if a reference was retained; that does not mean it is still permitted to use the underlying resource.

## 14. `try-with-resources` Using a Previously Declared Variable (Java 9+)

Since Java 9, a resource specification can accept a variable already declared outside `try`, if that variable is `final` or *effectively final* and its type implements `AutoCloseable`. In that case, **the variable name's scope remains the scope where it was originally declared**.

Standalone Java 17 example, saved as `ExistingResourceDemo.java`:

```java
public class ExistingResourceDemo {
    static class Resource implements AutoCloseable {
        private boolean closed;

        String read() {
            if (closed) {
                throw new IllegalStateException("Đã đóng");
            }
            return "ok";
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("Đang đóng");
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            System.out.println(resource.read());
        }

        System.out.println("Có thể gọi tên resource: " + resource.isClosed());
    }
}
```

Run:

```bash
javac --release 17 ExistingResourceDemo.java
java ExistingResourceDemo
```

Stdout:

```text
ok
Đang đóng
Có thể gọi tên resource: true
```

The `resource` variable was declared before `try`, so the name remains in scope after the construct, even though the object has already been closed. The *effectively final* condition requires not reassigning `resource` after its initial assignment; if you write `resource = new Resource()` afterward, the compiler will reject using `resource` in this `try (resource)` form.

Since Java 9, passing an existing variable like this is valid syntax. For Java 7/8, the standard syntax is declaring the resource directly inside `try (...)`, or using a new resource variable declaration compatible with that language version.

## 15. `finally` Scope and Shared Variables

`finally` is a separate block. It does not have access to local variables declared inside `try` or to `catch` parameters, but it can access variables in the enclosing scope.

```java
int attempts = 0;

try {
    attempts++;
    execute();
} catch (RuntimeException e) {
    System.out.println("Lỗi: " + e.getMessage());
} finally {
    System.out.println("Số lần thử: " + attempts);
}
```

This is illustrative code; `execute()` is not defined. `attempts` is in the enclosing scope and has an initial value, so `finally` can read it. If instead you wrote `int attempts = 0;` **only inside `try`**, `finally` would not be allowed to refer to that variable by name.

If you only need resource cleanup, prefer `try-with-resources` with `AutoCloseable` objects. If using `finally` for other purposes, avoid `return` or throwing a new exception inside it, as that can overwrite the result or suppress a propagating exception.

You cannot infer that a variable visible in `finally` has a valid state: if state is only updated partway through `try` and an exception occurs before that point, `finally` must tolerate partially updated state.

## 16. `catch` Parameters and Lambdas: Variable Capture Rules

Java allows lambdas or anonymous classes to use local variables from an enclosing scope when the variable is `final` or *effectively final*. `catch` parameters follow this same mechanism. A handler can create a lambda using `e`, provided `e` is not reassigned when it is captured.

Complete example, saved as `CatchLambdaDemo.java`:

```java
public class CatchLambdaDemo {
    public static void main(String[] args) {
        Runnable report;

        try {
            Integer.parseInt("wrong");
            report = () -> System.out.println("Không có lỗi");
        } catch (NumberFormatException e) {
            report = () -> System.out.println(
                    "Lambda đọc: " + e.getClass().getSimpleName());
        }

        report.run();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 CatchLambdaDemo.java
java CatchLambdaDemo
```

Stdout:

```text
Lambda đọc: NumberFormatException
```

`report` is declared in the outer scope and assigned in the branches. A lambda created inside `catch` can capture parameter `e` when `e` is effectively final. **Ending the `catch` scope does not cause the exception object to be destroyed automatically**: the lambda can retain the reference it needs when executed later.

This is why you should be careful when retaining lambdas or callbacks long-term: an exception holds a stack trace, cause, and contextual data; capturing it may keep it in memory longer than desired or unintentionally expose details if passed across inappropriate layers.

If you reassign `e` in the handler while also trying to capture it, the compiler will report an error because the captured variable is no longer effectively final. A cleaner approach is to leave `e` intact and, if needed, capture a processed message string or error code.

## 17. Scope Is Not Always "Object Lifetime"

A common misconception: after leaving `catch`, because the name `e` is no longer in scope, the exception object must also disappear. Java does not work that way.

- **Lexical scope** of the name `e` ends at the closing brace of the handler.
- **Reference reachability** of the exception object depends on whether something else still holds a reference to it.
- The garbage collector (GC) can only reclaim objects that are no longer reachable according to JVM rules; there is no guaranteed exact reclamation time immediately upon exiting a block.
- If you rethrow the same object with `throw e`, the caller can catch that exact instance.
- If you wrap the exception with `new IllegalStateException("...", e)`, the wrapper holds `e` as its `cause`; the original exception can continue living as long as the wrapper does.
- If you capture `e` in a stored lambda, the object can remain reachable even after the handler has finished.

This is the difference between **where a variable name can be accessed** and **where data is still referenced**. Similarly, closing a resource does not mean immediately deleting the Java object holding the resource.

## 18. Scope and Exception Handling in Loops

Variables declared in a loop body or in the `try` of each iteration are scoped to the loop structure. A variable outside the loop can accumulate results.

Example `LoopScopeDemo.java`:

```java
public class LoopScopeDemo {
    public static void main(String[] args) {
        int validCount = 0;

        for (String text : new String[] {"2", "bad", "5"}) {
            try {
                int number = Integer.parseInt(text);
                System.out.println("Giá trị: " + number);
                validCount++;
            } catch (NumberFormatException e) {
                System.out.println("Bỏ qua: " + text);
            }
        }

        System.out.println("Hợp lệ: " + validCount);
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 LoopScopeDemo.java
java LoopScopeDemo
```

Stdout:

```text
Giá trị: 2
Bỏ qua: bad
Giá trị: 5
Hợp lệ: 2
```

`number` only exists inside the `try` block of each iteration; `e` only exists inside the handler of the corresponding failing iteration; `text` is declared in the enhanced `for` header and is visible in both `try` and `catch` inside the loop body; `validCount` is outside the loop so it can be used afterward.

If an exception is caught **outside the entire loop**, the loop is exited when the exception propagates to the outer handler; Java does not automatically return to the next element. Placing `try/catch` in the right position helps variables and handling scope reflect intent: handling errors per item or aborting the whole batch.

## 19. Clean Design Pattern: Return Data as a Result Instead of Sharing Variables Unsafely

Not every error-handling block should try to create a shared variable between `try` and `catch`. If data truly only exists on success, you can represent a **stateful result**.

Java 17 supports `record` and `sealed interface`, which are useful for this example. Save `ParseResultDemo.java`:

```java
public class ParseResultDemo {
    sealed interface ParseResult permits Success, Invalid {
    }

    record Success(int value) implements ParseResult {
    }

    record Invalid(String reason) implements ParseResult {
    }

    static ParseResult parse(String input) {
        try {
            int number = Integer.parseInt(input);
            return new Success(number);
        } catch (NumberFormatException e) {
            return new Invalid("Không phải số nguyên");
        }
    }

    static void describe(String input) {
        ParseResult result = parse(input);

        if (result instanceof Success success) {
            System.out.println("OK: " + success.value());
        } else if (result instanceof Invalid invalid) {
            System.out.println("Sai: " + invalid.reason());
        }
    }

    public static void main(String[] args) {
        describe("10");
        describe("x");
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 ParseResultDemo.java
java ParseResultDemo
```

Stdout:

```text
OK: 10
Sai: Không phải số nguyên
```

The `number` data stays in the `try` block of the `parse` method and is only moved into `Success` when parsing succeeds. The handler does not need to refer to `number` because no valid success value is created on the error path. Outside, `result` is a value always returned by contract; type checking determines which branch to use.

The pattern variables `success` and `invalid` also have scope governed by pattern matching's **flow scoping**, which is a separate Java 17 mechanism. It does not extend the scope of variables in `try` or `catch` parameters. The example chooses `if/else if` so the reader clearly sees that each value is only used after the appropriate type check.

## 20. Common Compile Errors and Fixes

| Message or Symptom | Common Cause | Fix |
| --- | --- | --- |
| `cannot find symbol: variable x` when reading from `catch` | `x` declared only inside `try` | Move declaration to outer scope if truly needed, or process `x` inside `try` |
| `variable x might not have been initialized` | `x` is in scope, but an execution path does not assign it | Assign on all normal paths, return/throw early, or model the result explicitly |
| `variable e is already defined` | Creating local variable `e` colliding with handler parameter or outer local | Rename to avoid overlapping scope |
| `multi-catch parameter e may not be assigned` | Reassigning `catch (A \| B e)` parameter | Do not reassign; create another variable if needed |
| `local variables referenced from a lambda expression must be final or effectively final` | Capturing a parameter/variable that was reassigned | Keep the parameter effectively final or capture another value |
| `unreported exception ... must be caught or declared to be thrown` | A checked exception (including via `throw e`) is not handled/declared | Catch appropriately or add `throws` per contract |
| Handler cannot see resource declared in `try (...)` | Resource specification scopes it only to the `try` body | Use data before leaving the block or declare an outer reference if truly needed |
| Need to use exception after handler, but name `e` is gone | `e` is only in handler scope | Handle inside handler, rethrow, or pass info outward via an appropriately typed value |

**Do not "fix" every scope error by turning variables into fields or `static`.** Doing so extends lifetime and shares state, which can cause contention in multithreading and make testing harder. Keep scope as small as practically needed.

## 21. Notes on Exceptions and Execution Paths When Analyzing Variables

The compiler analyzes variable scope **according to the lexical structure of the code**, while exceptions altering where execution continues is **control flow**. These two rule layers interact but cannot replace one another.

For example, if `try` calls a method that can throw an exception **before** an assignment statement, the `catch` branch can run when the outer variable has not yet received a value. If `catch` assigns a valid fallback, the variable becomes definitely assigned after the whole construct. If the handler ends with `return` or `throw`, Java knows there is no normal path going through that handler to the variable-reading statement.

Another mistake is placing code that reads a result after a handler just because "there is always a result." If a call fails midway, **data produced before the error cannot be treated as a complete result**. Ensure consistency of side effects, return contracts, and program state, beyond merely satisfying the compiler.

Also do not confuse checked exceptions with variable scope: an `IOException` declared with `throws` is a **throwing contract** issue, whereas `cannot find symbol` for a variable inside `try` is a **name scope** issue. Adding `throws` does not expand variable scope.

## 22. Self-Check Exercises

**Q1.** Can a variable `x` declared inside `try` be referred to by name in the `catch` attached to that `try`?  
**Answer:** No. They are two different block bodies; `x` is only in scope within the `try` body.

**Q2.** A variable `result` is declared before `try` but only assigned when parsing succeeds. If `catch` only prints an error and completes normally, can `result` be read after the construct?  
**Answer:** Not necessarily. The compiler may report that it might not have been initialized because the handler path can still reach the read site. All paths must assign it, or the error branch must return/throw.

**Q3.** Can two different `catch` branches both use a parameter named `e`?  
**Answer:** Yes. The scopes of those parameters belong to two separate handlers.

**Q4.** Can you declare `String e` inside a handler that already has parameter `catch (IOException e)`?  
**Answer:** No. That is a declaration collision in a scope where `e` already exists.

**Q5.** Can a multi-catch parameter be reassigned?  
**Answer:** No. A multi-catch parameter is implicitly final.

**Q6.** Does `catch (Exception e) { throw e; }` always require declaring `throws Exception`?  
**Answer:** No. With a final/effectively final parameter, Java can use precise rethrow to determine a narrower set of checked exceptions from the `try` body.

**Q7.** Is a resource declared in `try (Resource r = ...)` visible in the `catch` directly attached to that construct?  
**Answer:** No. The resource specification restricts the scope of `r` to the `try` body.

**Q8.** With `Resource r = new Resource(); try (r) {...}` on Java 17, can `r` be referred to by name after `try`?  
**Answer:** Yes, because `r` was declared outside `try`. However, the resource has already been closed (or attempted to be closed) upon leaving the block.

**Q9.** Does the `final` keyword on a `catch` parameter make the exception object completely immutable?  
**Answer:** No. It forbids reassigning the parameter, but does not prevent valid methods from modifying the object's properties.

**Q10.** If a lambda created in `catch` holds a reference to `e` and runs after the handler, does that violate scope?  
**Answer:** No, if `e` was validly captured (final/effectively final). The lambda holds an object reference; `e` going out of scope in code outside the handler does not make the lambda lose its captured reference.

## 23. Checklist When Writing `try/catch`

Before finishing an exception-handling method, review:

1. **In what scope are variables declared?** Only move declarations outside `try` when branches genuinely need the same variable.
2. **Is a variable used in `catch`/`finally` that belongs only to `try`?** If so, restructure the data flow.
3. **Is an outer variable assigned on all normal paths?** Consider exceptions occurring before the assignment and whether the handler completes normally.
4. **Does the `catch` parameter collide with an outer local variable or a variable inside the handler?** Avoid scope collisions.
5. **Is the handler parameter reassigned?** Preserve the original exception when rethrowing and retain precise rethrow capability.
6. **Does multi-catch follow type and final rules?** Do not reassign the parameter, and do not combine two types with a parent–child relationship.
7. **Are resources used within valid scope?** Remember that resources declared in `try (...)` are not visible in `catch` and are auto-closed.
8. **Do lambdas capture variables validly?** Check final/effectively final and the risk of holding long-lived references.
9. **Is an incomplete result used after a failure path?** Ensure business state and meaning, not just compilability.
10. **Do examples and tests cover both success and error paths?** This is the best way to confirm scope/assignment branches are understood accurately.

## 24. Key Takeaways

**In Java, the `try` body, each `catch` body, and the `finally` body are separate variable scopes.** Variables declared in `try` cannot be accessed in `catch`; a `catch` parameter can only be accessed in its corresponding handler; variables declared before the construct can appear in the sub-blocks and afterward, provided they obey **definite assignment**.

With multi-catch, the handler parameter is implicitly `final`. With single-type catch, keeping the parameter *effectively final* is good practice to preserve identity and support **precise rethrow**. `try-with-resources` has its own resource scope rules; when using a previously declared variable (`try (resource)`, Java 9+), distinguish between name scope and the fact that the resource is already closed.

Keep variables in the **smallest meaningful scope**, assign them clearly on paths that can continue, and do not turn failures into fake success data just to resolve a scope error. That mindset helps `try/catch` code both compile cleanly and faithfully reflect the exception-handling flow.
