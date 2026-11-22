# Where Execution Resumes After Exception Handling in Java

An important question when reading a program that uses `try`/`catch` is: **after an exception is caught, which statement does Java run next?** Java **does not automatically return to the statement that threw the exception**, nor does it **continue with the remaining statements of the interrupted `try` block**. If a matching `catch` handles the exception and completes normally, the execution flow goes through the necessary cleanup (if any) and then resumes at **the next valid statement after the `try`/`catch`/`finally` construct** in the current scope.

However, the actual resume point also depends on where the `catch` is placed, which methods have been popped off the call stack, `finally`, `return`, `break`, `continue`, new exceptions during handling, and whether the exception is caught at all. This lesson builds the rules to determine **the next execution path** rather than memorizing a single example.

## 1. Fundamental rule: a `try` block that threw an exception does not continue running

Given the structure:

```java
try {
    statementA();
    statementB(); // Throws exception
    statementC();
} catch (SomeException e) {
    handle(e);
}
statementD();
```

This is an **illustrative code skeleton**; the methods and the `SomeException` type are not defined and it does not run standalone. Assuming `statementB()` throws the exact type caught by `catch` and `handle(e)` completes normally, the execution order is:

1. `statementA()` executes.
2. `statementB()` starts and throws an exception; that call **does not complete normally**.
3. Java skips `statementC()` in the same `try` block.
4. Java executes the matching `catch` body, here `handle(e)`.
5. When `catch` completes normally, Java executes `statementD()`, which lies **after the entire `try/catch` construct**.

Java does not "jump back" to `statementB()` to retry, does not automatically run `statementC()`, and does not resume a method that exited abruptly. A retry only happens when the program code **actively** writes loop logic or calls the method again.

If **no exception occurs**, statements A, B, and C run in order; the `catch` body does not run, and only then does D run. If the exception **has no matching `catch`**, it continues propagating to the caller; D may not run at all.

## 2. First example: resuming after `catch`

Save the following code as `CatchResumeDemo.java`. This is a complete program running on Java 17+:

```java
public class CatchResumeDemo {
    public static void main(String[] args) {
        System.out.println("1. Trước try");

        try {
            System.out.println("2. Đầu try");
            int number = Integer.parseInt("abc");
            System.out.println("3. Number = " + number);
        } catch (NumberFormatException e) {
            System.out.println("4. Đang xử lý NumberFormatException");
        }

        System.out.println("5. Sau try/catch");
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CatchResumeDemo.java
java CatchResumeDemo
```

**Exact stdout** when the console uses UTF-8:

```text
1. Trước try
2. Đầu try
4. Đang xử lý NumberFormatException
5. Sau try/catch
```

Reason line 3 is absent: `Integer.parseInt("abc")` throws `NumberFormatException`, so the rest of the assignment statement and the following `println` statement **do not run**. The `catch` is selected based on the exception type. After handling finishes, statement 5 outside the `try/catch` construct is executed.

Do not confuse "the exception was caught" with "the failing statement succeeded." The exception still occurred; the program simply took a different handling path and can continue doing appropriate work.

## 3. Rules for finding `catch`: where it is caught determines where it resumes

When an exception is thrown, the JVM searches for a matching handler according to the language structure:

- First, it checks the `catch` clauses attached to the `try` enclosing the throw point, in declaration order. One matching `catch` is selected; the remaining `catch` clauses of the same `try` do not run.
- If there is no suitable handler at the current level, the exception continues propagating out of the scope containing `try` and up to the calling method. Methods that exit abruptly do not resume at the statement immediately following the failing call.
- If a `catch` is found at a higher level and that `catch` block completes normally, execution can resume **after the `try/catch` construct at that level**.
- Related `finally` blocks and resource-closing operations are still evaluated as scopes are exited; they can produce additional exceptions or alter how completion occurs.

`catch` branches match by type relationship. A `catch (RuntimeException e)` can catch `NumberFormatException` because it is an indirect subclass. A `catch (IOException e)` does not catch `NumberFormatException`. When both specific and general branches exist in the same `try`, place the specific branch first to avoid unreachable `catch` code.

Visualizing the normal flow with a matching handler:

```text
Statement before try
        │
        ▼
      try
        │
        ├─ No exception thrown ────────────┐
        │                                  │
        └─ Exception thrown                │
                 │                         │
                 ▼                         │
          compatible catch                 │
                 │                         │
                 └───────────┐             │
                             ▼             │
                  finally (if any) ◀───────┘
                             │
                             ▼
                  After the entire try/catch/finally
```

This diagram describes the **normal completion path** of the handler. If `catch`/`finally` throws an exception, or contains `return`/`break`/`continue`, the execution target is determined by the rules of those cases.

## 4. Exception from a callee method: the caller does not automatically retry the call

This is a very commonly misunderstood situation. When a callee method throws an exception, the calling method can catch it if the call is inside an appropriate `try`. However, the callee method has already exited abruptly; Java **does not reopen the old stack frame** to continue right after the `throw` statement.

Save the file `CallStackResumeDemo.java`:

```java
public class CallStackResumeDemo {
    static void parseAtLowerLevel() {
        System.out.println("B. Bắt đầu trong phương thức con");
        Integer.parseInt("not-a-number");
        System.out.println("C. Cuối phương thức con");
    }

    static void invokeWithoutHandling() {
        System.out.println("A. Trước khi gọi con");
        parseAtLowerLevel();
        System.out.println("D. Sau khi gọi con");
    }

    public static void main(String[] args) {
        System.out.println("0. Trong main");
        try {
            invokeWithoutHandling();
            System.out.println("E. Sau lời gọi trong try");
        } catch (NumberFormatException e) {
            System.out.println("F. Bắt tại main");
        }
        System.out.println("G. Tiếp tục tại main");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CallStackResumeDemo.java
java CallStackResumeDemo
```

**Exact stdout:**

```text
0. Trong main
A. Trước khi gọi con
B. Bắt đầu trong phương thức con
F. Bắt tại main
G. Tiếp tục tại main
```

Lines C, D, and E do not appear. `parseAtLowerLevel` and `invokeWithoutHandling` terminated abruptly because they did not catch the exception themselves; only in `main` is there a matching handler. After the handler in `main`, statement G runs, **not** D or E.

If you want `invokeWithoutHandling` to continue after a known error, you must **place `try/catch` inside that method itself** around the operation that may fail, or change the callee method's contract to return an appropriate result.

## 5. Catching inside vs. outside the call: two different outcomes

For the same exception, where the handler is placed changes which statements still execute.

### Case A: the callee method catches the error, then returns normally

```java
static int parseOrDefault(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return 0;
    }
}
```

This is an **illustrative method**, with no `main`. With `text = "abc"`, `catch` executes and `return 0` makes the method return normally. The caller can run the statement right after `parseOrDefault("abc")` because the call completed normally (with value `0`). However, keep in mind: using `0` as a fallback value is only valid if the contract clearly specifies it; if `0` is also valid data, consider a result type that distinguishes success from failure.

### Case B: the callee method lets the error escape; the caller catches it

```java
static int parseStrict(String text) {
    return Integer.parseInt(text);
}

static void run() {
    try {
        int value = parseStrict("abc");
        System.out.println("Giá trị: " + value);
    } catch (NumberFormatException e) {
        System.out.println("Giá trị nhập sai");
    }
    System.out.println("Tiếp tục run");
}
```

These are **illustrative methods** placed in a class; there is no `main`. The statement printing `Giá trị:` is skipped because the call to `parseStrict` did not return normally. The statement `Tiếp tục run` is after the `try/catch` construct, so it runs if the handler completes normally.

Key point to remember: **"after `catch`" means after the `catch` belonging to the exact scope doing the handling**; there is no global resume point shared by all exceptions.

## 6. `finally` lies on the exit path of `try/catch`

A construct with `finally`:

```java
try {
    work();
} catch (SomeException e) {
    recover(e);
} finally {
    cleanup();
}
nextStep();
```

This is an illustrative skeleton that does not run standalone. When `work()` throws `SomeException` and `recover(e)` completes normally, the order is: **`work` up to the throw point → `catch` handles → `finally` cleans up → `nextStep`**.

If `work` does not throw an exception, the order is `work` completes → `finally` → `nextStep`. If the exception is not caught, `finally` still executes during normal exception propagation, but `nextStep` does not run in the scope being exited.

Complete example in `FinallyResumeDemo.java`:

```java
public class FinallyResumeDemo {
    static void execute(boolean fail) {
        System.out.println("Bắt đầu");
        try {
            System.out.println("Trong try");
            if (fail) {
                throw new IllegalArgumentException("Dữ liệu sai");
            }
            System.out.println("Try thành công");
        } catch (IllegalArgumentException e) {
            System.out.println("Trong catch: " + e.getMessage());
        } finally {
            System.out.println("Trong finally");
        }
        System.out.println("Sau try/catch/finally");
    }

    public static void main(String[] args) {
        execute(false);
        System.out.println("---");
        execute(true);
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 FinallyResumeDemo.java
java FinallyResumeDemo
```

**Exact stdout**:

```text
Bắt đầu
Trong try
Try thành công
Trong finally
Sau try/catch/finally
---
Bắt đầu
Trong try
Trong catch: Dữ liệu sai
Trong finally
Sau try/catch/finally
```

The example shows that `finally` sits on both the success path and the handled-exception path. Do not arbitrarily put `return` or throw a new exception in `finally`: they can override the previously determined completion.

**Limitation note:** `finally` is not an absolute guarantee in every environmental situation. Force-terminating the process, a severe JVM crash, or a `System.exit` call can prevent normal cleanup from running. For `AutoCloseable` resources, `try-with-resources` is usually the preferred choice.

## 7. `return` inside `try` or `catch`: execution does not continue after the construct

The normal path after `catch` only occurs when the `catch` block completes **normally**. If the `catch` block executes `return`, the method returns to the caller after executing any necessary `finally`, rather than running the statement after the construct.

File `ReturnFinallyDemo.java`:

```java
public class ReturnFinallyDemo {
    static int compute(boolean fail) {
        try {
            System.out.println("Try");
            if (fail) {
                throw new IllegalStateException("Không tính được");
            }
            return 10;
        } catch (IllegalStateException e) {
            System.out.println("Catch");
            return -1;
        } finally {
            System.out.println("Finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả A = " + compute(false));
        System.out.println("Kết quả B = " + compute(true));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 ReturnFinallyDemo.java
java ReturnFinallyDemo
```

**Exact stdout**:

```text
Try
Finally
Kết quả A = 10
Try
Catch
Finally
Kết quả B = -1
```

In call A, `return 10` in `try` causes `finally` to run before the caller receives `10`; `catch` does not run. In call B, `try` throws an exception, `catch` prints and then executes `return -1`, yet `finally` still runs before the caller receives the value.

Similarly, `throw` in `catch` causes the new exception to propagate upward instead of continuing with the statement after the construct. A `break` or `continue` statement inside a `try/catch` within a loop also transfers control to a different target, after running `finally` according to the rules.

**Warning:** `return` in `finally` can discard both a pending `return` value and a propagating exception; generally avoid writing it that way.

## 8. What if `catch` itself throws a new exception?

The `catch` branches of **the same `try`** are not a "try the next branch" chain when a handler runs into a problem. Once a `catch` has been selected, subsequent `catch` clauses in the same construct **do not catch exceptions thrown from that `catch` body**. The new exception must go to an enclosing `try` or an appropriate caller.

Complete example in `CatchThrowsDemo.java`:

```java
public class CatchThrowsDemo {
    public static void main(String[] args) {
        try {
            try {
                throw new NumberFormatException("chuỗi sai");
            } catch (NumberFormatException e) {
                System.out.println("Catch bên trong");
                throw new IllegalStateException("Xử lý bị lỗi", e);
            } catch (IllegalStateException e) {
                System.out.println("Catch thứ hai ở bên trong");
            } finally {
                System.out.println("Finally bên trong");
            }
        } catch (IllegalStateException e) {
            System.out.println("Catch bên ngoài: " + e.getMessage());
        }
        System.out.println("Tiếp tục bên ngoài");
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CatchThrowsDemo.java
java CatchThrowsDemo
```

**Exact stdout**:

```text
Catch bên trong
Finally bên trong
Catch bên ngoài: Xử lý bị lỗi
Tiếp tục bên ngoài
```

Reason: `NumberFormatException` is caught by the first handler, which then throws `IllegalStateException`. The **sibling** `catch (IllegalStateException e)` branch is not tried. The inner construct's `finally` runs before the exception continues to the outer handler. When the outer handler completes normally, the final statement of `main` runs.

Use a constructor accepting `cause` to preserve the original cause (`NumberFormatException`). During diagnostics, `e.getCause()` in the outer handler lets you trace back to the root error.

## 9. What if `finally` throws an exception or alters control flow?

`finally` can change the outcome already determined in `try` or `catch`. For example, an original exception is propagating, but `finally` throws a different exception: the new exception can **replace** the original exception as the directly observed outcome of the entire construct.

Consider the illustrative snippet:

```java
try {
    throw new IllegalArgumentException("Lỗi chính");
} finally {
    throw new IllegalStateException("Lỗi trong cleanup");
}
```

If placed in a valid Java context, the exception exiting is `IllegalStateException` from `finally`. With this pattern, the primary error can be masked. Therefore, do not deliberately `throw` or `return` in `finally` just to "make sure something is handled"; prefer clean cleanup code, preserve the cause, and use `try-with-resources` when appropriate.

Similarly, if `finally` has a `return`, a pending return value from `try`/`catch` can be replaced. Java permits some of these forms, but they make control flow hard to reason about and are commonly flagged by code quality rules.

`finally` may fail to complete normally due to an exception from a cleanup operation. In that case, the next statement after the construct **does not run automatically**, unless an enclosing level catches the new exception and resumes at that level's position.

## 10. `try-with-resources`: closing resources before entering `catch` outside the resource block

In `try-with-resources`, Java closes the `AutoCloseable` resources that were successfully initialized when leaving the `try` block. If there are multiple resources, they are closed in **reverse order of their declaration**. Resources are closed **before** any `catch` or `finally` attached to that `try-with-resources` statement executes.

File `ResourceResumeDemo.java`:

```java
public class ResourceResumeDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Thao tác thất bại");
        } catch (IllegalArgumentException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally");
        }
        System.out.println("Sau try-with-resources");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 ResourceResumeDemo.java
java ResourceResumeDemo
```

**Exact stdout**:

```text
Mở A
Mở B
Trong try
Đóng B
Đóng A
Catch: Thao tác thất bại
Finally
Sau try-with-resources
```

The order is significant: the exception in the `try` body prevents code from continuing there; before reaching `catch`, both resources are closed in the order B then A. After `catch` comes `finally`, and only then the final line.

When `close()` also throws an exception while another exception from the `try` body is propagating, the exception from closing **is typically attached as a suppressed exception**, while the primary exception from the `try` body is preserved. This differs from writing a `finally` that throws a new error and can mask the original error.

Minimal example checking suppressed exceptions:

```java
public class SuppressedDemo {
    static class FailingClose implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (FailingClose resource = new FailingClose()) {
            throw new IllegalArgumentException("Thao tác lỗi");
        } catch (IllegalArgumentException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Suppressed: " + e.getSuppressed().length);
            System.out.println("Phụ: " + e.getSuppressed()[0].getMessage());
        }
        System.out.println("Tiếp tục sau catch");
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 SuppressedDemo.java
java SuppressedDemo
```

**Exact stdout**:

```text
Chính: Thao tác lỗi
Suppressed: 1
Phụ: Không đóng được
Tiếp tục sau catch
```

This snippet shows that `catch` sees the primary exception from the `try` body, and the exception during closing is stored in `getSuppressed()`. If only `close()` fails while the `try` body throws no exception, the exception from `close()` can become the primary exception and be caught by a matching handler.

## 11. Is `catch` inside or outside the loop?

Loops make the resume point easy to misread. Compare the two structures:

**`try/catch` inside the loop:**

```java
for (String value : inputs) {
    try {
        process(value);
    } catch (NumberFormatException e) {
        System.out.println("Bỏ qua input sai");
    }
}
```

**`try/catch` enclosing the entire loop:**

```java
try {
    for (String value : inputs) {
        process(value);
    }
} catch (NumberFormatException e) {
    System.out.println("Dừng vòng lặp vì input sai");
}
```

Both snippets are **illustrative code skeletons**, assuming `inputs` and `process` exist. With the handler inside, the current iteration can finish and the loop moves on to the next element. With the handler outside, when an iteration throws an exception and exits to the outer `catch`, **the entire loop has already been exited**; Java does not automatically return to the next element.

Complete example in `LoopCatchDemo.java`:

```java
public class LoopCatchDemo {
    static void insideLoop(String[] values) {
        for (String value : values) {
            try {
                System.out.println("Trong: " + Integer.parseInt(value));
            } catch (NumberFormatException e) {
                System.out.println("Trong: bỏ qua " + value);
            }
        }
        System.out.println("Trong: kết thúc vòng lặp");
    }

    static void outsideLoop(String[] values) {
        try {
            for (String value : values) {
                System.out.println("Ngoài: " + Integer.parseInt(value));
            }
        } catch (NumberFormatException e) {
            System.out.println("Ngoài: bắt lỗi và rời vòng lặp");
        }
        System.out.println("Ngoài: sau try/catch");
    }

    public static void main(String[] args) {
        String[] values = {"1", "sai", "3"};
        insideLoop(values);
        System.out.println("---");
        outsideLoop(values);
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 LoopCatchDemo.java
java LoopCatchDemo
```

**Exact stdout**:

```text
Trong: 1
Trong: bỏ qua sai
Trong: 3
Trong: kết thúc vòng lặp
---
Ngoài: 1
Ngoài: bắt lỗi và rời vòng lặp
Ngoài: sau try/catch
```

With `insideLoop`, the iteration for `"sai"` has a handler within that very iteration; after `catch`, the loop proceeds to `"3"`. With `outsideLoop`, the error at `"sai"` causes Java to exit the loop to the outer `catch`; `"3"` is no longer processed.

This rule does not mean `catch` always means "skip invalid input." If intermediate state has already changed or side effects occurred, continuing the loop may be unsafe. Handling policies must be designed around contracts and state.

## 12. `break`, `continue`, and `return` change the control target

Inside `try` or `catch` blocks placed within a loop:

- `continue` transfers control to the next step of the corresponding loop (or specified loop label), after executing any necessary `finally`. It does not simply jump to the statement after the `try/catch` block of the current iteration.
- `break` exits the corresponding loop or `switch` block (or labeled construct) after executing any necessary `finally`. The target is the statement after the loop/`switch`, not the start of the next iteration.
- `return` exits the method after executing any necessary `finally`. The caller only resumes after the call when the method completes normally by returning; if an exception continues propagating outward, the caller may have to catch it.
- `throw` creates/throws an exception and begins searching for a matching handler; statements after `throw` on the same path do not execute.

Example of `continue` and `finally` in `ContinueFinallyDemo.java`:

```java
public class ContinueFinallyDemo {
    public static void main(String[] args) {
        for (int i = 1; i <= 3; i++) {
            try {
                System.out.println("Try " + i);
                if (i == 2) {
                    continue;
                }
                System.out.println("Giữa " + i);
            } finally {
                System.out.println("Finally " + i);
            }
            System.out.println("Cuối lượt " + i);
        }
        System.out.println("Sau vòng lặp");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 ContinueFinallyDemo.java
java ContinueFinallyDemo
```

**Exact stdout**:

```text
Try 1
Giữa 1
Finally 1
Cuối lượt 1
Try 2
Finally 2
Try 3
Giữa 3
Finally 3
Cuối lượt 3
Sau vòng lặp
```

When `i == 2`, `continue` inside `try` skips `Giữa 2` and `Cuối lượt 2`, yet **`Finally 2` is still printed** before moving to the iteration with `i == 3`. This example has no exceptions, because the goal is to understand how `finally` interacts with different forms of control flow.

## 13. Nested `try`: catching at the nearest matching level

Nested `try` blocks can cause an exception to be handled right in the inner block or propagate to the outer one. If the inner level catches and handles it normally, statements after the inner construct **inside the outer block** can continue. If there is no matching handler inside, Java leaves the rest of the outer `try` to look for an outer `catch`.

Program `NestedTryDemo.java`:

```java
public class NestedTryDemo {
    static void handledInside() {
        try {
            System.out.println("A1");
            try {
                throw new IllegalArgumentException("Lỗi A");
            } catch (IllegalArgumentException e) {
                System.out.println("A2: catch trong");
            }
            System.out.println("A3: tiếp trong try ngoài");
        } catch (RuntimeException e) {
            System.out.println("A4: catch ngoài");
        }
        System.out.println("A5: sau toàn bộ");
    }

    static void handledOutside() {
        try {
            System.out.println("B1");
            try {
                throw new IllegalStateException("Lỗi B");
            } catch (NumberFormatException e) {
                System.out.println("B2: catch trong");
            }
            System.out.println("B3: sau try trong");
        } catch (IllegalStateException e) {
            System.out.println("B4: catch ngoài");
        }
        System.out.println("B5: sau toàn bộ");
    }

    public static void main(String[] args) {
        handledInside();
        System.out.println("---");
        handledOutside();
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 NestedTryDemo.java
java NestedTryDemo
```

**Exact stdout**:

```text
A1
A2: catch trong
A3: tiếp trong try ngoài
A5: sau toàn bộ
---
B1
B4: catch ngoài
B5: sau toàn bộ
```

In case A, the inner handler catches `IllegalArgumentException`, so the outer block remains on the normal execution path and runs A3. In case B, the inner handler only catches `NumberFormatException`, which does not match `IllegalStateException`; thus B2 and B3 do not run, and the exception goes to the outer handler B4.

A noteworthy detail: when a `catch` completes normally, statements after its construct run **if** they are not governed by another control-flow action. For instance, A3 runs because the inner catch succeeded, whereas B3 does not run because the `try` containing B3 was exited abruptly.

## 14. When there is no matching handler, where does execution "resume"?

If an exception is not caught in the current method, it continues propagating up to the caller. When no matching handler remains on the call chain, the executing thread can terminate abruptly. In a simple console application, an exception escaping `main` typically results in printing a stack trace to **stderr** and an error exit status for the program.

In a server application, a framework might catch the exception at the request boundary, return an error response, and continue processing other requests. In a multithreaded application, an uncaught exception can terminate the current thread without necessarily stopping all other threads. Therefore, there is no rule saying "throwing an exception definitely stops the entire JVM."

In particular, `try` does not create a handler by itself. A `try` block with only `finally` and no `catch` can clean up when an exception occurs, and then **the exception continues propagating**. To restore the path in the current scope, a matching handler or another valid control mechanism is required.

## 15. Quick-reference table: after situation X, which statement runs?

| Situation | Outcome of `try/catch` in the current scope | Next position |
| --- | --- | --- |
| `try` completes normally | `catch` does not run; `finally` runs if present | Statement after the entire construct |
| `try` throws exception and matching `catch` completes normally | Skip remainder of `try`, execute `catch`, run `finally` if present | Statement after the entire construct |
| `try` throws exception, no matching `catch` | Exit scope, run related cleanup/`finally` | Search for outer handler or in caller; remainder of exited scope does not run |
| `catch` throws a new exception | Skip remainder of `catch`, execute related `finally` | Handler of enclosing `try` or caller |
| `catch` executes `return` | Prepare return value, run `finally` if present | Caller receives value if no new interference occurs |
| `catch` executes `break` in a loop | Exit loop after necessary `finally` | Statement after the corresponding loop |
| `catch` executes `continue` in a loop | Advance iteration after necessary `finally` | Next update/condition check step of the corresponding loop |
| `finally` throws a new exception | Alters control outcome, may mask previous exception/return | Search for outer handler for the new exception |
| `try-with-resources` closes resources successfully then handler completes normally | Close resources before `catch` and `finally` | Statement after the entire construct |
| `try-with-resources` has primary error and close error | Close error may be attached as suppressed to primary error | Handler receives primary exception and can inspect suppressed ones |
| `catch` inside a callee returns normally | Callee completes normally | Statement immediately after the call in the caller |
| Handler exists only in a higher caller | Intermediate callers exit abruptly | Statement after the `try/catch` construct in the caller that actually catches the error |

The table lists common paths; `finally` can alter the outcome if it itself completes abruptly, and recovery must be designed to match program state.

## 16. Common misconceptions and how to fix them

**Misconception 1: "After `catch`, Java returns to the line that threw the error."**  
False. `catch` does not act as an automatic retry. The execution path where the error was thrown has already been skipped for that scope; to retry, you must write a loop or re-invoke the operation, paying attention to modified state and side effects.

**Misconception 2: "If the error is caught in `main`, the callee method resumes."**  
False. If an exception from a callee method has propagated outward, that method's stack frame has been popped and is not automatically restored. `main` resumes at the position after its own handler.

**Misconception 3: "The statement right after `throw` still runs if there is a `catch` below."**  
False. `throw` interrupts the normal path at that point. Code after `throw` in the same block without an alternative branch can even be unreachable code and cause a compilation error.

**Misconception 4: "`finally` only runs on error."**  
False. `finally` normally runs when leaving the construct whether `try` succeeds, throws an exception, executes `return`, or executes `continue`. Do not abuse `finally` by writing `return` that overrides the outcome.

**Misconception 5: "A `catch` can catch a new exception from a preceding sibling `catch`."**  
False. An exception thrown from a handler body requires an enclosing handler or caller; sibling handlers only serve exceptions originating from the corresponding `try` block.

**Misconception 6: "`try/catch` inside a loop and outside a loop process subsequent elements the same way."**  
False. A handler inside the loop can allow the next iteration; an enclosing handler means the loop has already been exited when the exception is caught.

**Misconception 7: "`try-with-resources` closes after `catch` finishes."**  
False for a `catch` attached directly to that `try-with-resources` statement: initialized resources are closed **before** that handler runs.

**Misconception 8: "Once inside `catch`, the program is definitely stable and continues."**  
False. `catch` can throw a new error, contain `return`, or break data invariants. Continuing is only safe when state and operation contracts have been properly restored.

**Misconception 9: "Catching `Exception` stops all Java errors right here."**  
False. `Error` does not belong to the `Exception` branch; moreover, `catch` itself can throw a new error. Each handler only catches objects matching its type from the attached `try` scope.

## 17. How to reason through a Java snippet with exceptions

When reading code, do not just look for the textually nearest `catch`. Mark the **structural scope** and **execution order**:

1. Identify the exact expression or statement that can throw an exception; list the statements that already ran before the throw point.
2. Identify the `try` enclosing the throw point; look for a handler with a matching type, checking from inner to outer constructs and up the call chain if needed.
3. Cross out statements in the remainder of the interrupted `try`, as well as statements right after the call in methods that exited abruptly.
4. Track cleanup steps during unwinding: `try-with-resources` closes resources, `finally` runs according to the rules.
5. Determine whether the handler completes **normally** or executes `return`, `break`, `continue`, `throw`, or throws a new error.
6. Only when the path of the entire construct completes normally should you mark the statement following `try/catch/finally` as the next execution position.
7. With loops, nested `try`, and caller/callee, determine exactly which constructs are still active after handling.
8. Check side effects prior to the error and whether true recovery is possible. Resuming execution is a control-flow behavior; it **does not guarantee** that data and state are valid.

## 18. Self-check exercises

**Question 1.** After `NumberFormatException` is caught by `catch` and the handler completes normally, does Java continue running the rest of `try` or the statement after the entire `try/catch`?  
**Answer:** The statement after the entire `try/catch`, after `finally` if present. The rest of `try` is skipped.

**Question 2.** `main` calls `A()`, `A()` calls `B()`; `B()` throws an exception, and only `main` has a handler. Does the statement after the `B()` call inside `A()` run?  
**Answer:** No. `A()` exited abruptly. `main` resumes after its matching handler if the handler completes normally.

**Question 3.** A `catch` catches an exception and then executes `return 5`; outside the construct there is still a `println("X")` statement in the same method. Is X printed?  
**Answer:** No, assuming no control-flow interference and that the statement simply sits after the construct. The method returns to the caller; any related `finally` still executes.

**Question 4.** In a loop processing three strings, the second string causes an error. `try/catch` is inside the loop body and the handler completes normally. Is the third string processed?  
**Answer:** Possibly yes, if the loop condition and structure still allow it. Conversely, if `try/catch` encloses the entire loop, the error exits the loop to the outer handler, so it does not automatically continue to the third element.

**Question 5.** When using `try (A a = ...; B b = ...)` and the `try` body throws an exception, what is the closing order of the resources?  
**Answer:** B then A, for the resources that were successfully initialized; closing takes place before the `catch`/`finally` attached directly to that statement.

**Question 6.** An inner `catch` throws a new exception. Can the next sibling `catch` at the same level catch it?  
**Answer:** No. The new exception propagates to an enclosing `try` or the caller, after completing related cleanup/`finally`.

**Question 7.** What happens if `finally` throws a different exception while an old exception is propagating out?  
**Answer:** The new exception from `finally` can replace the old exception as the outcome of the construct, masking the original error. This is one reason to avoid unintended `throw` statements in `finally`.

**Question 8.** If `try` completes normally and has a `finally`, does the statement after the construct run before or after `finally`?  
**Answer:** After `finally`, provided `finally` also completes normally.

## 19. Key takeaways

Where execution resumes after an exception is handled **depends on where it is caught**. If the handler completes normally, Java resumes **after the entire `try/catch/finally` construct containing that handler**, after related cleanup; the remaining statements of the interrupted `try` do not automatically resume. If an exception propagates from a callee up to a caller, the callee and any intermediate methods that exited abruptly do not automatically continue. `return`, `break`, `continue`, `throw`, new exceptions in the handler/`finally`, and `try-with-resources` can all alter the specific path.

To reason accurately, always track four elements: **throw point → matching handler → cleanup/`finally` → next control position**. Once all four are identified, you can explain precisely why a line ran, was skipped, or only ran at an outer calling level.
