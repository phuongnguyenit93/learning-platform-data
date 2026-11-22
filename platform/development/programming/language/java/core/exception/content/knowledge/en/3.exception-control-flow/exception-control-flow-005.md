# Finding the Nearest Matching `catch` Block in Java

When an exception is thrown, Java needs to decide **which `catch` block will receive that exception object**. The core rule: Java searches for **the nearest matching handler along the active execution flow**, based on the runtime type of the exception and the `try/catch` scopes enclosing the throw site. If there is no matching `catch` at the current point, the exception continues propagating outward through method calls; along the way, `finally` blocks must execute according to Java's rules.

This lesson focuses on the process of finding a matching `catch` and the resulting control flow changes. It is part of **Java Core – Exception / Control Flow**.

## 1. What is a "matching `catch`"?

A `catch` clause has the form:

~~~java
catch (SomeException e) {
    // Handle the exception.
}
~~~

A `catch` matches when **the propagating exception object has a type assignable to the `catch` parameter type**. In other words, the object's type can be the exact type in the `catch` or a subclass of that type.

For example, consider the following hierarchy:

~~~text
Throwable
└── Exception
    └── RuntimeException
        └── IllegalArgumentException
            └── NumberFormatException
~~~

Since `NumberFormatException` is a subclass of `IllegalArgumentException`, the exception `new NumberFormatException("sai")` can be caught by:

~~~java
catch (NumberFormatException e) { ... }
catch (IllegalArgumentException e) { ... }
catch (RuntimeException e) { ... }
catch (Exception e) { ... }
catch (Throwable e) { ... }
~~~

The lines above are **individual illustrative options**, not five `catch` blocks placed consecutively in that order within the same `try`. In real code, `catch` blocks must be ordered validly so that later branches are not shadowed by earlier ones.

Two conditions must be distinguished:

- **Compatible type:** `catch (IllegalArgumentException e)` receives a `NumberFormatException`, whereas `catch (NullPointerException e)` does not receive a `NumberFormatException` because there is no corresponding inheritance relationship.
- **On the propagation path:** The `catch` must belong to a handling region enclosing the throw operation in the **active call chain**. A `catch` located in another method that is not on the current call path has no chance to receive the error.

Matching checks **the type of the propagating exception object**; the message in `getMessage()` does not determine which `catch` runs. Nor does the declared type of a reference variable replace the object's runtime type when determining a matching `catch`.

## 2. In what order does Java search for a `catch`?

Consider an exception thrown in an executing method. You can trace the process in the following steps:

1. **Start at the throw point.** When `throw` is executed (or an API throws an exception), normal code after that point in the currently running branch does not continue immediately.
2. **Check the nearest enclosing `try` region.** Java inspects the `catch` clauses attached to the `try` enclosing the throw point, in declaration order from top to bottom. The first clause with a matching type is selected.
3. **If no clause matches, propagate to an outer scope.** Other enclosing `try` regions in the same method or in caller methods may have a matching `catch`.
4. **Execute associated `finally` blocks while exiting scopes.** Normal `finally` blocks run even when a `catch` is found at an outer level; a `finally` block itself can also throw a new exception and change the outcome.
5. **When a matching `catch` is found, transfer control into that block.** If the handler completes normally, the program continues after the corresponding `try/catch/finally` construct.
6. **If no matching handler exists along the call path**, the exception exits the outermost method of the executing thread; the thread/runtime uncaught exception handling mechanism takes over.

The concept of "nearest" means **nearest among the handling regions enclosing the execution path** whose type can receive the exception. It does **not** mean the `catch` on the smallest line number, the method with the closest name, or "whichever `catch` appears at the top of the file".

A `catch` whose type does not match cannot "temporarily intercept" and convert the exception to that type. If the exception does not match, Java continues searching outward.

### Handler search flow diagram

~~~text
A statement throws exception E
         |
         v
Is there a matching catch in the nearest try region?
         | Yes
         +------> Enter the first matching catch
         |
         | No
         v
Exit the current scope (execute associated finally)
         |
         v
Is there an active enclosing try region?
         | Yes
         +------> Search for a matching catch in the enclosing region
         |
         | No
         v
Exception exits the method / returns to caller
         |
         v
Repeat across active callers
         |
         v
No matching handler left -> uncaught exception
~~~

The diagram illustrates the mental model for tracing the flow; in the Java language, completing `finally` blocks, closing resources, and handling newly thrown errors follow more detailed rules presented later.

## 3. Standalone Java 17+ example: searching for `catch` across multiple levels

Create the file **`CatchSearchDemo.java`** with the following full content:

~~~java
public class CatchSearchDemo {
    public static void main(String[] args) {
        System.out.println("1) Tim catch qua cac phuong thuc");
        try {
            first();
        } catch (IllegalArgumentException e) {
            System.out.println("main catch: " + e.getMessage());
        } finally {
            System.out.println("main finally");
        }

        System.out.println("2) Catch phu hop trong try gan nhat");
        try {
            try {
                throw new NumberFormatException("abc");
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "inner catch: " + e.getClass().getSimpleName());
            } finally {
                System.out.println("inner finally");
            }
        } catch (IllegalArgumentException e) {
            System.out.println("outer catch");
        }

        System.out.println("3) Catch va nem lai");
        try {
            try {
                throw new IllegalStateException("chua san sang");
            } catch (IllegalStateException e) {
                System.out.println("inner catch: " + e.getMessage());
                throw e;
            } finally {
                System.out.println("inner finally");
            }
        } catch (RuntimeException e) {
            System.out.println(
                    "outer catch: " + e.getClass().getSimpleName());
        }

        System.out.println("4) Catch cu the dung truoc catch cha");
        try {
            Integer.parseInt("7x");
        } catch (NumberFormatException e) {
            System.out.println("specific catch");
        } catch (IllegalArgumentException e) {
            System.out.println("general catch");
        }
    }

    static void first() {
        try {
            middle();
        } catch (NullPointerException e) {
            System.out.println("first null catch");
        } finally {
            System.out.println("first finally");
        }
    }

    static void middle() {
        try {
            leaf();
        } catch (IllegalStateException e) {
            System.out.println("middle state catch");
        } finally {
            System.out.println("middle finally");
        }
    }

    static void leaf() {
        throw new NumberFormatException("bad-number");
    }
}
~~~

Run with Java 17 or newer:

~~~bash
javac CatchSearchDemo.java
java CatchSearchDemo
~~~

Exact output:

~~~text
1) Tim catch qua cac phuong thuc
middle finally
first finally
main catch: bad-number
main finally
2) Catch phu hop trong try gan nhat
inner catch: NumberFormatException
inner finally
3) Catch va nem lai
inner catch: chua san sang
inner finally
outer catch: IllegalStateException
4) Catch cu the dung truoc catch cha
specific catch
~~~

### Walkthrough of scenario 1: propagating across methods

Call flow:

~~~text
main()
  └── first()
        └── middle()
              └── leaf()
                    └── throw NumberFormatException
~~~

Step by step:

1. `leaf()` throws the object `NumberFormatException("bad-number")`.
2. `middle()` has `catch (IllegalStateException e)`. The propagating exception **is not** an `IllegalStateException` or a subclass of it, so this branch is not entered. `middle finally` is printed.
3. `first()` has `catch (NullPointerException e)`. The type is incompatible, so the `catch` branch does not run. `first finally` is printed.
4. `main()` has `catch (IllegalArgumentException e)`. Since `NumberFormatException extends IllegalArgumentException`, this is the **first matching handler along the propagation path**. The program prints `main catch: bad-number`.
5. `main`'s `finally` runs and prints `main finally`. This `try/catch/finally` construct finishes normally, and the program moves to part 2.

Notable point: the two inner `finally` blocks run **before** the `catch` in `main` catches the exception. The lines `first null catch` and `middle state catch` are **not** printed because their types do not match the exception.

The process of unwinding calls due to a propagating exception is commonly called **stack unwinding**. Normal calls remaining on the call stack are unwound one by one until a matching handler is reached, running cleanup blocks along the way according to Java's rules.

### Walkthrough of scenario 2: preferring the nearer `try` region

`NumberFormatException` is thrown in the inner `try`. That region has `catch (IllegalArgumentException e)`, which is sufficient to receive it due to the inheritance relationship. Java enters `inner catch` and continues to run `inner finally`. The exception has been handled and **does not automatically propagate to `outer catch`**.

"Nearest" here is expressed by the **nesting** relationship between the two `try` regions. Once a matching `catch` branch exists in the inner region, the outer region does not run merely because it also has a compatible type.

### Walkthrough of scenario 3: catching and rethrowing

The `inner catch` block receives `IllegalStateException` and then executes `throw e;`. This is **a rethrow** of the caught exception object. Next, `inner finally` runs, and then `catch (RuntimeException e)` in the outer region receives the exception because `IllegalStateException extends RuntimeException`.

Conversely, if `inner catch` completes normally without rethrowing, `outer catch` will not run. Catching an exception **does not mean** every outer level receives it; only exceptions that continue propagating trigger further handler searches.

### Walkthrough of scenario 4: order of `catch` clauses in the same `try`

`Integer.parseInt("7x")` throws `NumberFormatException`. Within the same `try` construct, `catch (NumberFormatException e)` appears before `catch (IllegalArgumentException e)`, so the specific branch is selected and only `specific catch` is printed.

Java checks `catch` clauses **in order of appearance**, stopping at the first matching clause. You should place specialized types before general types.

## 4. Type relationships and the order of `catch` clauses

The following two snippets are **not equivalent**:

Correct — subclass before superclass:

~~~java
try {
    Integer.parseInt("khong-phai-so");
} catch (NumberFormatException e) {
    System.out.println("Sai dinh dang so");
} catch (IllegalArgumentException e) {
    System.out.println("Tham so khong hop le");
}
~~~

Incorrect — the compiler rejects it because the later branch can never receive an exception not already caught by the earlier branch:

~~~java
try {
    Integer.parseInt("khong-phai-so");
} catch (IllegalArgumentException e) {
    System.out.println("Loi tham so");
} catch (NumberFormatException e) {
    System.out.println("Loi dinh dang so");
}
~~~

These are **two illustrative snippets**, not standalone programs. In the incorrect snippet, `catch (NumberFormatException e)` causes a compile error because every `NumberFormatException` already matches `IllegalArgumentException` above it.

| Runtime exception object | `catch (NumberFormatException)` | `catch (IllegalArgumentException)` | `catch (IOException)` |
| --- | --- | --- | --- |
| `new NumberFormatException()` | Matches | Matches | No |
| `new IllegalArgumentException()` | No | Matches | No |
| `new IOException()` | No | No | Matches |

The table only evaluates **type-matching capability per branch**; the outcome of the whole construct also depends on `catch` ordering and which `try` regions are actually active.

### `catch (Exception)` and `catch (Throwable)`

- `catch (Exception e)` receives exceptions under the `Exception` branch, including `RuntimeException` and many checked exceptions, but does **not** receive `Error`.
- `catch (Throwable t)` can receive both `Exception` and `Error`. Catching too broadly can swallow serious errors or hide design flaws. It should only be used at boundaries with an explicit error-handling policy.
- `catch (RuntimeException e)` receives subclasses of `RuntimeException`, not other checked exceptions under `Exception` such as `IOException`.
- Being *checked/unchecked* does not change the `catch` search rules **at runtime**: the compiler uses the checked classification to require catching or declaring; once an exception is thrown, Java searches for a handler based on runtime type and scope.

## 5. The nearest `catch` does not have to be in the same method

Consider the call chain:

~~~java
static void controller() {
    try {
        service();
    } catch (IllegalArgumentException e) {
        System.out.println("Du lieu khong hop le");
    }
}

static void service() {
    repository();
}

static void repository() {
    throw new IllegalArgumentException("id sai");
}
~~~

This is a **three-method illustrative snippet**. When `controller()` is actively calling `service()` and then `repository()`, an exception thrown from `repository()` can be caught by `controller()`. The fact that the intermediate methods do not declare `throws IllegalArgumentException` does not prevent propagation because this exception is unchecked.

However, a `catch` in `controller()` **cannot** receive an exception from a call to `repository()` belonging to a completely different call chain. Java does not scan the entire codebase to pick any handler that looks suitable.

If `service()` has already caught and finished handling the exception, `controller()` will not receive that same exception either, unless `service()` rethrows it or throws a new exception.

### Does `throws` locate a handler?

No. The declaration:

~~~java
static void readFile(java.nio.file.Path path)
        throws java.io.IOException {
    java.nio.file.Files.readString(path);
}
~~~

states that a checked exception may escape the method and the caller must satisfy the compiler's rules. It **does not select** a handler or change runtime type matching. The actual handler is still determined by active `try/catch` constructs.

## 6. Do sibling `catch` or `finally` blocks catch newly thrown errors?

An easily confused detail: **the `catch` clauses of a `try` only handle exceptions thrown from the corresponding `try` body**, including calls made inside it. Once execution is **already inside a `catch` block**, a new exception thrown in that handler **does not go back to check sibling `catch` clauses** of the same `try`.

For example:

~~~java
try {
    throw new IllegalArgumentException("loi dau");
} catch (IllegalArgumentException e) {
    throw new IllegalStateException("loi trong catch", e);
} catch (IllegalStateException e) {
    System.out.println("Khong bat loi moi o day");
}
~~~

This is an **illustrative snippet**, not a standalone program. The initial `IllegalArgumentException` is caught by the first branch. The new `IllegalStateException` thrown **inside the first `catch` branch** exits to an enclosing handling region, if one exists. The `catch (IllegalStateException e)` branch is a sibling branch, so it **does not** receive that new exception.

If you want to catch errors thrown while handling an exception, structure an enclosing `try/catch` or a new `try/catch` inside the handler block when genuinely needed.

Similarly, a new exception thrown inside a `finally` block is not handled by the `catch` clauses attached to that `try` as if it came from the `try` body. It propagates to a suitable enclosing region.

## 7. The role of `finally` when searching for a handler

An exception may pass through multiple `finally` blocks before being caught. Normally, `finally` runs when leaving a `try/catch` region whether exiting via normal completion, `return`, or an exception. This explains the print order in scenarios 1 and 3.

Simple example:

~~~java
try {
    try {
        throw new IllegalArgumentException("sai");
    } finally {
        System.out.println("don dep ben trong");
    }
} catch (IllegalArgumentException e) {
    System.out.println("bat o ngoai");
}
~~~

Output:

~~~text
don dep ben trong
bat o ngoai
~~~

This is an **illustrative snippet** that can be placed in `main` to run. The inner block has no `catch`, yet `finally` runs before the exception is caught outside.

**Important warning:** If `finally` itself executes `throw` with a new exception, or executes `return` while an earlier exception is propagating, the outcome can change: the original exception may no longer be the one that exits. Therefore, avoid `return` in `finally` and avoid letting cleanup logic mask the primary error.

When using **try-with-resources**, resources are closed automatically when exiting the `try`. Exceptions thrown during closing can be recorded as *suppressed exceptions* when the `try` body has already thrown a primary error; handler lookup for the primary error still follows type and scope rules. This is a different mechanism from manually throwing a new error in `finally`.

## 8. When no matching `catch` is found

If Java has traversed every handling scope in the call chain without finding a matching handler, the exception becomes an **uncaught exception** for that execution thread. Typically, the runtime displays the exception type, message, and stack trace through the thread's default handler; specific behavior can be customized by a framework or `Thread.UncaughtExceptionHandler`.

Do not interpret "uncaught" as meaning **the entire JVM must terminate immediately** in every case: a background thread may terminate while other threads keep running; a framework may manage errors at task boundaries. In a simple single-threaded program running in `main`, an unhandled exception usually causes `main` to terminate abnormally.

Standalone illustrative example if placed in `main`:

~~~java
throw new IllegalArgumentException("du lieu sai");
~~~

Without an enclosing `catch`, the runtime reports the exception with a stack trace. No normal code runs after the `throw` statement in that same control flow.

### Distinguishing three outcomes after a throw

| Scenario | Behavior |
| --- | --- |
| A matching `catch` catches it and finishes normally | The exception stops propagating; execution continues normally after the construct |
| A matching `catch` catches it and then runs `throw e` or throws a new error | Handler search continues in outer scopes for the thrown exception |
| No matching `catch` is found | The exception exits the current call path and is handled as an uncaught error at the thread/runtime boundary |

## 9. How to trace an error using a stack trace

When you see a stack trace, start from the **throw point** and the **call chain** to find which constructs actually enclose the thrown exception. For instance, an error thrown in `leaf()` passes through `middle()` and `first()` to `main()`. Useful steps:

1. Identify the actual **exception type** in the first line, e.g., `NumberFormatException`.
2. Locate where the error occurred in the frames and confirm how the caller methods invoke each other.
3. Inspect the `try/catch` regions that actually enclose the corresponding calls, starting from the nearest region.
4. Compare the type of each `catch` according to inheritance, and check the order of clauses within the same `try`.
5. Check `finally` blocks, resource closing, or rethrowing `catch` blocks to explain execution order and possible exception replacement.
6. If you see `Caused by`, distinguish the **outer wrapper exception** from the **root cause**. A handler receives the exception being thrown at that level; Java does not automatically inspect `getCause()` to choose a `catch`.

For example, `catch (java.io.IOException e)` does **not** automatically catch a `RuntimeException` just because `runtimeException.getCause()` is an `IOException`. To handle based on the cause, the appropriate layer must explicitly inspect the cause or design the API to throw the right exception type.

Note: the frame order in a stack trace helps you understand the call chain; it does **not** show every `try/catch` or tell you whether a specific `catch` is in scope. To conclude with certainty, you must check the source code and actual control flow.

## 10. Common misconceptions

**Misconception 1 — "Java searches for the `catch` matching the exception name that is closest in the file."**

Java searches by **execution scope**, not global textual order. A `catch` branch in a method that has not been called is irrelevant.

**Misconception 2 — "The nearest `catch` of the exact same class always wins even if it is outside an inner `try`."**

If an inner `try` already has a superclass branch that can receive the exception, it handles it before the outer region. Java does not skip a nearer handler to look for a more specialized handler farther away.

**Misconception 3 — "All `catch` branches are tested and every matching branch runs."**

Within **one `try`**, only the first matching branch is selected. After that branch finishes normally, the remaining branches do not run.

**Misconception 4 — "Putting a superclass `catch` before a subclass `catch` is fine."**

If the superclass completely covers the subclass, the later subclass branch is unreachable; Java reports a compile error.

**Misconception 5 — "`finally` only runs when a `catch` receives the exception."**

A normal `finally` runs even when there is no matching `catch` and while an exception is propagating to an outer level. Abnormal process or VM termination can prevent this guarantee; do not rely on `finally` if the JVM is abruptly killed.

**Misconception 6 — "A subsequent `catch` in the same construct will receive an error thrown by an earlier `catch`."**

No. An error from `catch` handler code must find a handler in an enclosing scope or another `try`.

**Misconception 7 — "Only checked exceptions propagate across methods."**

Both checked and unchecked exceptions can propagate across multiple methods. Checked exceptions differ in the compile-time catch/declare requirement; runtime `catch` lookup still depends on type and scope.

**Misconception 8 — "Catching `Exception` catches everything that can be thrown."**

`Error` is a separate branch of `Throwable`, so it is not caught by `catch (Exception e)`. Avoid catching `Throwable` indiscriminately just to try continuing after a serious error.

## 11. Self-check exercises

**Question 1.** `NumberFormatException` is thrown inside a `try` that has `catch (IllegalArgumentException e)`. Does this `catch` match? Why?

**Question 2.** Method `a()` calls `b()`, and `b()` calls `c()`. `c()` throws `IllegalStateException`; `b()` only has `catch (NullPointerException e)`; `a()` has `catch (RuntimeException e)`. Which `catch` is selected?

**Question 3.** If both an inner `try` region and an outer `try` region have `catch (Exception e)`, and an exception is thrown in the inner region, which region receives it first?

**Question 4.** If an inner `catch` receives an exception and executes `throw e;`, what happens next? When can `finally` run?

**Question 5.** Why can't you place `catch (RuntimeException e)` before `catch (NumberFormatException e)` in the same `try` construct?

**Question 6.** A method throws `new IllegalStateException("x", new IOException("root"))`. If an outer `catch` only catches `IOException`, will it receive the propagating exception? Why?

**Question 7.** When there is no matching `catch` in `main`, must all other threads in the JVM stop immediately?

### Suggested answers

1. Yes, because `NumberFormatException` is a subclass of `IllegalArgumentException`.
2. `catch (RuntimeException e)` in `a()`; the branch in `b()` does not match the type.
3. The inner region receives it first if the exception is thrown in its `try` and that branch matches.
4. The exception continues propagating to the outer region; any associated `finally` normally runs upon exiting the block before the outer handler receives it.
5. Because the `RuntimeException` branch already catches every `NumberFormatException`, making the later branch unreachable.
6. No. The propagating object is `IllegalStateException`; `IOException` is only the cause stored in `cause`.
7. No. An uncaught exception affects that thread; process-wide consequences depend on the remaining threads and the task-management environment.

## 12. Key takeaway

When Java encounters an exception, ask **"which handling region encloses the throw point and has a `catch` that accepts that object's type?"**. Java prioritizes the nearest active region; within the same region, it prioritizes the first matching `catch` branch. If none matches, the exception propagates across call levels, executing associated cleanup along the way, until it meets a matching handler or becomes an uncaught exception. Understanding this propagation path helps you predict stdout, pinpoint the origin of errors, and choose where to handle exceptions without catching too broadly.