# `InvocationTargetException` and the Actual Exception of the Invoked Method in Java

> **Topic:** Java Core → Exception → API Exceptions. When invoking a method using **Java Reflection**, `java.lang.reflect.Method.invoke(...)` does not propagate every exception thrown by the target method directly to the caller. If the invoked code (**target method**) completes abnormally by throwing a `Throwable`, the reflective call normally reports an **`InvocationTargetException`**. The actual exception is stored in the wrapper's `getCause()` or `getTargetException()`. Understanding these two layers helps diagnose root causes, preserve stack traces, design error handling, and avoid confusing Reflection issues with business logic errors inside the method.

## 1. Essence: one call, two exception layers

Consider a direct call:

```java
service.load();
```

If `load()` throws `IOException`, the calling code can receive `IOException` directly.

When calling via Reflection:

```java
java.lang.reflect.Method method =
        Service.class.getMethod("load");

method.invoke(service);
```

if **`load()` itself** throws `IOException`, the code calling `invoke` will see `InvocationTargetException` (a wrapper). To find the actual error:

```java
try {
    method.invoke(service);
} catch (java.lang.reflect.InvocationTargetException wrapper) {
    Throwable targetError = wrapper.getCause();
    System.out.println(targetError.getClass().getName());
}
```

The code snippets above are **illustrative**, assuming `Service`, `service`, and the checked exceptions from lookup/invoke are handled in an appropriate method.

Relationship diagram:

```text
Caller
  |
  | Method.invoke(target, args...)
  v
Reflection API
  |
  | Invokes actual method: Service.load()
  v
Service.load()
  |
  | throw new IOException("Không đọc được file")
  v
IOException  <----------------------------+
  |                                        |
  | Reflection wraps error when method throws
  v                                        |
InvocationTargetException                 |
  └── cause / targetException ------------+
  |
  v
Caller catches wrapper and traces original error
```

**Key point:** `InvocationTargetException` does not mean the method name is wrong, nor does it mean the target method threw an exception with that name. It is an **error representation layer** created by Reflection when the invoked code throws an exception.

## 2. Classifying `InvocationTargetException` in the `Throwable` hierarchy

Hierarchy:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.ReflectiveOperationException
        └── java.lang.reflect.InvocationTargetException
```

Therefore:

- `InvocationTargetException` is a **checked exception**; if calling `Method.invoke(...)`, Java code must normally **catch** or **declare `throws`** for it.
- It is a subtype of `ReflectiveOperationException` and `Exception`; it is **not** a `RuntimeException`.
- The underlying target error can be a checked `IOException`, an unchecked `IllegalArgumentException`, `NullPointerException`, a custom exception, or even an `Error`.
- The fact that the wrapper is checked **does not turn the target exception into a checked exception or vice versa**; the two objects have their own types, their own stack traces, and different meanings.
- The `Constructor.newInstance(...)` API can also produce this wrapper when the target constructor throws an exception.
- Do not assume that **every Reflection API** produces `InvocationTargetException`. Many operations such as field/method lookup, access checks, and class initialization have their own exception contracts.

### 2.1. `getCause()` and `getTargetException()`

Two commonly used methods:

```java
Throwable getCause()
Throwable getTargetException()
```

For an `InvocationTargetException` created by `Method.invoke` when the target actually throws an error, both return **the same wrapped original exception**. `getTargetException()` is the API specific to this class; `getCause()` follows the general **exception chaining** mechanism of `Throwable`, which is convenient for code that processes cause chains.

Example at the catch site:

```java
Throwable cause = wrapper.getCause();
Throwable target = wrapper.getTargetException();
boolean sameObject = cause == target;
```

`sameObject` will be `true` for a standard wrapper reflecting the same target failure.

**Do not confuse them:** `wrapper.getStackTrace()` describes the stack associated with the wrapper, whereas `wrapper.getCause().getStackTrace()` describes the stack of the exception that the target method threw.

### 2.2. Wrapper differs from its message

`getMessage()` on the wrapper is not a reliable way to retrieve the target's message. Read directly:

```java
Throwable target = wrapper.getCause();
String targetMessage =
        target == null ? null : target.getMessage();
```

Normally a wrapper created by Reflection will have a cause, but when writing utilities that accept `InvocationTargetException` objects constructed manually by other code, you should check for null before accessing the cause.

## 3. Three distinct failure categories to separate

When using Reflection, there are at least three groups of events:

| Group | Example | Observed exception type |
| --- | --- | --- |
| **Metadata lookup** | Method named `load` not found or wrong parameter list in `getMethod` | `NoSuchMethodException`, not an error from the method body |
| **Invalid Reflection call** | `invoke` with wrong receiver object, wrong argument count/types, or missing access permission | May be `IllegalArgumentException`, `NullPointerException`, `IllegalAccessException`, etc., from the reflective invocation API |
| **Target code throws Throwable** | Method body executes and throws `IOException`, `IllegalStateException`, etc. | `InvocationTargetException` wrapping the actual `Throwable` |

Other situations such as class initialization failures, linkage errors, or module environment issues require examining the contract of each call. Do not force every Reflection error into a single branch.

**Key distinction:** `Method.invoke(...)` itself throwing `IllegalArgumentException` when passed wrong arguments is usually **not** an `InvocationTargetException`. But if the **target method** itself throws `IllegalArgumentException`, you will normally receive **`InvocationTargetException` with `IllegalArgumentException` as its cause**.

### 3.1. Has the method body always executed when `InvocationTargetException` occurs?

When the wrapper indicates that the target threw, execution of the invoked code was triggered and terminated abnormally. However, do not assume all lines in the body ran: the method might throw right at the start, a constructor might throw before completing, or the target might call another method where the error originates. Additionally, class initialization related to the target has its own rules. To know for sure, inspect the stack trace of the **cause** and the control conditions.

## 4. Java 17 — Example 1: `Method.invoke` wrapping a checked `IOException`

Create **`ReflectiveMethodFailureDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectiveMethodFailureDemo {
    public static final class Service {
        public String load(String key) throws IOException {
            if ("bad".equals(key)) {
                throw new IOException("Không đọc được bad");
            }
            return "loaded:" + key;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Service service = new Service();
        Method method =
                Service.class.getMethod("load", String.class);

        Object goodResult = method.invoke(service, "good");
        System.out.println("Good: " + goodResult);

        try {
            method.invoke(service, "bad");
        } catch (InvocationTargetException wrapper) {
            Throwable target = wrapper.getTargetException();
            System.out.println("Wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Target: "
                    + target.getClass().getSimpleName());
            System.out.println("Message: " + target.getMessage());
            System.out.println("Same cause: "
                    + (wrapper.getCause() == target));
        }
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 ReflectiveMethodFailureDemo.java
java ReflectiveMethodFailureDemo
```

**Exact stdout:**

```text
Good: loaded:good
Wrapper: InvocationTargetException
Target: IOException
Message: Không đọc được bad
Same cause: true
```

Step-by-step explanation:

1. `Service.class.getMethod("load", String.class)` looks up a public method by name and **parameter types**; it does not execute the method yet.
2. `method.invoke(service, "good")` calls `load("good")`; the method returns a string, so `invoke` returns an `Object` containing that string.
3. `method.invoke(service, "bad")` enters the body of `load`; the body throws a checked `IOException`.
4. The Reflection caller does not receive `IOException` directly from `Method.invoke`; it receives `InvocationTargetException`.
5. `getTargetException()` and `getCause()` point to the same actual `IOException` object.
6. `main` declares `throws ReflectiveOperationException` to handle checked exceptions from the Reflection API that may still escape, while the `catch(InvocationTargetException)` branch explicitly interprets the target failure in the bad case.
7. If you call `service.load("bad")` directly, the compiler requires catching or declaring `IOException`; when calling via `Method.invoke`, the compiler knows about **`InvocationTargetException`**, and does not "read" `throws IOException` from the method described by the `Method` object.

**Do not call `method.invoke(service, "bad")` and write a standalone `catch(IOException)`** expecting an I/O error from the method body; Reflection's checked signature does not declare such a direct `IOException`.

## 5. Java Reflection does not automatically throw target errors directly

Common public signature (omitting annotations and details):

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException,
               IllegalArgumentException,
               InvocationTargetException
```

This is the signature of `java.lang.reflect.Method.invoke` at the API level you need to learn. `IllegalArgumentException` is unchecked, so even though it appears in the `throws` clause, the compiler does not require handling it.

Important points about the contract boundary:

- A `Method` may represent a method declared with `throws IOException`, `throws SQLException`, or no checked throws.
- However, **`Method.invoke` has its own signature**, which is not parameterized by the target's checked exception types.
- Java does not infer the target's checked exceptions when a method is looked up/selected dynamically via reflection.
- `InvocationTargetException` provides a unified wrapping layer so the API can report "the invoked code threw an error" regardless of what kind of method the target is.
- To handle a specific target type, you must **unwrap** it and apply a policy, or use a direct call if the method can be known at compile time.

### 5.1. The target's `throws` clause still matters

If the target declares `throws IOException`, direct Java calls are governed by that contract. When a call site uses reflection, the compiler applies the `Method.invoke` signature; that **does not turn unchecked into checked or eliminate the I/O error**. The I/O error is still inside the cause object, and the calling layer must decide how to report/recover.

A target can throw an unchecked exception even if its own signature does not declare `throws`, and Reflection still wraps that target exception.

## 6. Java 17 — Example 2: unchecked exception thrown by the **target method**

Create **`ReflectiveRuntimeFailureDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectiveRuntimeFailureDemo {
    public static final class Calculator {
        public int divide(int numerator, int denominator) {
            return numerator / denominator;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method divide = Calculator.class.getMethod(
                "divide", int.class, int.class);
        Calculator calculator = new Calculator();

        Object ok = divide.invoke(calculator, 12, 3);
        System.out.println("Result: " + ok);

        try {
            divide.invoke(calculator, 12, 0);
        } catch (InvocationTargetException wrapper) {
            Throwable actual = wrapper.getCause();
            System.out.println("Actual: "
                    + actual.getClass().getSimpleName());
            System.out.println("Message: " + actual.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ReflectiveRuntimeFailureDemo.java
java ReflectiveRuntimeFailureDemo
```

Stdout:

```text
Result: 4
Actual: ArithmeticException
Message: / by zero
```

**Why is there a wrapper if `ArithmeticException` is unchecked?**

`InvocationTargetException` is not only for wrapping **checked exceptions**. `Method.invoke` wraps the `Throwable` thrown by the target method. When division in `Calculator.divide` triggers `ArithmeticException`, Reflection still creates the wrapper so the caller can distinguish it from errors caused by the `invoke` API itself (such as passing invalid arguments).

A `catch(ArithmeticException)` placed directly around `divide.invoke(...)` **does not catch** the target exception in this example; the caller will see the wrapper. If the application wants to handle `ArithmeticException` specifically, it must unwrap and inspect `getCause()`.

### 6.1. Can a target throw an `Error`?

Yes. A target method can throw `AssertionError` or another `Error`. `Method.invoke` normally reports a target-thrown `Throwable` via `InvocationTargetException`. However, other runtime errors (such as class initialization errors) have their own contracts, so do not claim that "any `Error` occurring around Reflection is guaranteed to be wrapped".

Do not broadly catch `Error` just to "recover from all JVM errors". A specialized framework may need to release resources/log and then let the failure propagate per its contract; many `Error`s are not safe to treat as expected business errors.

## 7. `Constructor.newInstance` can also wrap target errors

Reflection does not only invoke methods; `java.lang.reflect.Constructor<T>.newInstance(Object... initargs)` allows creating an object using the described constructor. If the **constructor body** throws an exception, the API can report `InvocationTargetException`.

For example, a constructor rejecting a negative argument:

```java
public Account(int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("amount âm");
    }
    this.amount = amount;
}
```

If `new Account(-1)` is called directly, the caller receives `IllegalArgumentException`. If `constructor.newInstance(-1)` is used, the caller will normally receive **`InvocationTargetException`**, with `IllegalArgumentException` from the constructor as its cause.

### 7.1. Java 17 — Example 3: constructor exception

Create **`ReflectiveConstructorFailureDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ReflectiveConstructorFailureDemo {
    public static final class Account {
        private final int amount;

        public Account(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("amount âm");
            }
            this.amount = amount;
        }

        public int amount() {
            return amount;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<Account> constructor =
                Account.class.getConstructor(int.class);

        Account valid = constructor.newInstance(5);
        System.out.println("Created: " + valid.amount());

        try {
            constructor.newInstance(-1);
        } catch (InvocationTargetException wrapper) {
            Throwable target = wrapper.getCause();
            System.out.println("Wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Target: "
                    + target.getClass().getSimpleName());
            System.out.println("Message: " + target.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ReflectiveConstructorFailureDemo.java
java ReflectiveConstructorFailureDemo
```

Stdout:

```text
Created: 5
Wrapper: InvocationTargetException
Target: IllegalArgumentException
Message: amount âm
```

This is a **public** constructor, so `getConstructor(int.class)` finds it. The constructor does not complete in the `-1` case and the caller does not receive a valid `Account` object. The wrapper does not let the constructor continue or roll back side effects that occurred before throwing.

### 7.2. Do not confuse with `Class.getDeclaredConstructor`

- `getConstructor(...)` finds a matching **public** constructor.
- `getDeclaredConstructor(...)` can find a constructor **declared in the class**, including private ones; however, finding metadata does not mean permission to invoke it is granted.
- Java access permissions and module restrictions can cause the call to fail before the constructor body runs.
- When no matching constructor is found, `NoSuchMethodException` belongs to the lookup phase, not an error inside the constructor body.
- Accessing a private constructor with `setAccessible(true)`/`trySetAccessible` has security/encapsulation and module restrictions; do not use it to bypass unauthorized API contracts.

## 8. Java 17 — Example 4: Reflection errors that are **not** target exceptions

The goal of this example is to distinguish three situations:

1. The method name does not exist.
2. Wrong argument types are supplied to `invoke`.
3. Arguments are valid, and the method body throws an unchecked exception.

Create **`ReflectionVsTargetDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionVsTargetDemo {
    public static final class Operations {
        public void process(String value) {
            if ("boom".equals(value)) {
                throw new IllegalStateException("Lỗi từ method đích");
            }
            System.out.println("Processed: " + value);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Operations target = new Operations();

        try {
            Operations.class.getMethod("missing");
        } catch (NoSuchMethodException e) {
            System.out.println("Lookup: NoSuchMethodException");
        }

        Method method =
                Operations.class.getMethod("process", String.class);

        try {
            method.invoke(target, 123);
        } catch (IllegalArgumentException e) {
            System.out.println("Argument: IllegalArgumentException");
        }

        try {
            method.invoke(target, "boom");
        } catch (InvocationTargetException wrapper) {
            System.out.println("Invocation: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Target: "
                    + wrapper.getCause().getClass().getSimpleName());
        }

        method.invoke(target, "ok");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ReflectionVsTargetDemo.java
java ReflectionVsTargetDemo
```

Stdout:

```text
Lookup: NoSuchMethodException
Argument: IllegalArgumentException
Invocation: InvocationTargetException
Target: IllegalStateException
Processed: ok
```

Explanation:

- `getMethod("missing")` does not find the member; **no body is executed**, so it reports `NoSuchMethodException`.
- `method.invoke(target, 123)` passes an `Integer` for a `String` parameter; Reflection rejects the invalid argument with `IllegalArgumentException`.
- `method.invoke(target, "boom")` has a valid argument, the body executes and throws `IllegalStateException`; Reflection wraps it in `InvocationTargetException`.
- `method.invoke(target, "ok")` completes successfully and prints `Processed: ok`.

A simple but very important example: **the same word "ArgumentException" can appear at two different layers**. Check whether you caught the exception directly from the `invoke` API, or retrieved an exception via `wrapper.getCause()`.

### 8.1. When does `IllegalAccessException` occur?

If the caller is not permitted to invoke the member under Java's access rules, `Method.invoke` can throw a checked `IllegalAccessException`. This is a **method access permission** issue, not an exception thrown by the method body. Do not unwrap `IllegalAccessException` as if an `InvocationTargetException` were attached to it.

A successful lookup does not guarantee a successful invocation: metadata may be found via `getDeclaredMethod`, but that does not automatically grant permission to invoke a private member.

### 8.2. `NullPointerException` can come from two sources

If you invoke an **instance method** via `Method.invoke` and pass a `null` receiver, the API can throw `NullPointerException` because there is no target object. However, if the receiver is valid and **the target's body** throws `NullPointerException`, the caller will see an `InvocationTargetException` wrapper carrying `NullPointerException` as its cause.

Therefore, when inspecting logs, do not look only at the exception class name; you need to know the **layer where it originated**.

## 9. When does `Method.invoke` return a value, and what does it return?

For a method returning an object or a primitive, `Method.invoke` returns `Object`. If the original method returns a primitive such as `int`, Reflection **boxes** it into a wrapper object such as `Integer`. For a `void` method, the result of `invoke` is `null`.

When the target throws an exception, `invoke` **has no successful return value**; the exception (wrapper) alters the control flow.

### 9.1. Java 17 — Example 5: methods returning primitive, void, and static

Create **`ReflectiveReturnValuesDemo.java`**:

```java
import java.lang.reflect.Method;

public class ReflectiveReturnValuesDemo {
    public static final class Calculator {
        public int add(int a, int b) {
            return a + b;
        }

        public void ping() {
            System.out.println("Ping");
        }

        public static String version() {
            return "v1";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Calculator target = new Calculator();

        Method add = Calculator.class.getMethod(
                "add", int.class, int.class);
        Object sum = add.invoke(target, 2, 3);
        System.out.println("Sum: " + sum);
        System.out.println("Boxed: "
                + sum.getClass().getSimpleName());

        Method ping = Calculator.class.getMethod("ping");
        Object voidResult = ping.invoke(target);
        System.out.println("Void result null: "
                + (voidResult == null));

        Method version = Calculator.class.getMethod("version");
        Object staticResult = version.invoke(null);
        System.out.println("Static: " + staticResult);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ReflectiveReturnValuesDemo.java
java ReflectiveReturnValuesDemo
```

Stdout:

```text
Sum: 5
Boxed: Integer
Ping
Void result null: true
Static: v1
```

Lessons:

- `getMethod("add", int.class, int.class)` uses the **declared parameter types**, not the argument instance type `Integer.class`.
- The result of `int add(...)` is boxed into `Integer`.
- `void ping()` causes `invoke` to return `null`, which does not mean the body did not run.
- For `static version()`, you can pass a `null` receiver to `invoke`, because a static method does not use an instance receiver.
- For an instance method, the receiver must be compatible with the declaring class and access rules.

These belong to the **reflection invocation contract**, independent of distinguishing wrapper and target exceptions, yet helpful for pinpointing where an error can occur.

## 10. Choosing a handler for `InvocationTargetException` and its cause

At a layer using Reflection, a handler should answer:

1. **Did the reflective call fail during preparation?** For example, lookup/permission/argument errors.
2. **If the target threw, what is the actual type?** Read `wrapper.getCause()`.
3. **Can the current layer recover?** Should it skip the operation, return a structured failure, rethrow a specific checked exception, or translate it into a business exception?
4. **Does the cause object need to be preserved?** Avoid creating a new exception with only the message and dropping the original trace.
5. **If there were side effects before throwing**, evaluate the state; wrapping does not roll back.

An illustrative handler:

```java
try {
    method.invoke(target, argument);
} catch (InvocationTargetException wrapper) {
    Throwable cause = wrapper.getCause();
    if (cause instanceof java.io.IOException io) {
        reportIoFailure(io);
    } else if (cause instanceof RuntimeException re) {
        throw re;
    } else if (cause instanceof Error er) {
        throw er;
    } else {
        throw new IllegalStateException(
                "Method đích thất bại", cause);
    }
}
```

This is a **code snippet** that assumes `method`, `target`, `argument`, `reportIoFailure`, and other checked exceptions of `Method.invoke` are defined/handled. It expresses a sample policy, not the only strategy.

### 10.1. Why not catch `Exception` and blindly cast?

Avoid this:

```java
try {
    method.invoke(target);
} catch (Exception e) {
    throw (RuntimeException) e.getCause();
}
```

This is an **anti-pattern**. `e` could be `NoSuchMethodException` or `IllegalAccessException` with a `null` cause; the target could throw a checked `IOException` or an `Error`; an unsafe cast can trigger `ClassCastException`/`NullPointerException` and obscure the original cause.

If unwrapping is needed, **apply it only to `InvocationTargetException`**, then inspect the actual target `Throwable` type.

## 11. Java 17 — Example 6: rethrowing the real `IOException` and preserving the original object

Sometimes an abstraction knows the target method can throw `IOException` and wants its public API to keep the checked contract `throws IOException`, rather than turning the error into a generic runtime wrapper.

Create **`RethrowTargetIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class RethrowTargetIOExceptionDemo {
    public static final class Source {
        public void fetch() throws IOException {
            throw new IOException("Kết nối bị ngắt");
        }
    }

    static void runReflectively()
            throws IOException, ReflectiveOperationException {
        Method method = Source.class.getMethod("fetch");
        try {
            method.invoke(new Source());
        } catch (InvocationTargetException wrapper) {
            Throwable target = wrapper.getCause();

            if (target instanceof IOException io) {
                throw io;
            }
            if (target instanceof RuntimeException re) {
                throw re;
            }
            if (target instanceof Error error) {
                throw error;
            }
            throw new IllegalStateException(
                    "Checked exception không mong đợi", target);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        try {
            runReflectively();
        } catch (IOException e) {
            System.out.println("Caught: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Top frame: "
                    + e.getStackTrace()[0].getMethodName());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 RethrowTargetIOExceptionDemo.java
java RethrowTargetIOExceptionDemo
```

Stdout when running this program directly on JDK 17:

```text
Caught: IOException
Message: Kết nối bị ngắt
Top frame: fetch
```

Explanation:

- `runReflectively` catches the checked wrapper thrown by `Method.invoke`.
- When the cause is `IOException`, the code **rethrows the exact cause object**, without creating a copy.
- `main` receives `IOException` according to the checked contract of `runReflectively`.
- Because the same cause object is reused, the stack trace still has the top frame at the location where `IOException` was created in `fetch()`, rather than being replaced by the unwrap site.
- `getStackTrace()[0]` is used here in an example with a normal controlled stack. In general-purpose `Throwable`-handling code, the stack array may be empty or customized; do not assume a frame always exists.
- For checked `Throwable`s outside the allowed set, the example chooses an `IllegalStateException` wrapper with a cause. A real API must design this policy clearly according to its domain, without silently hiding failures as success.

### 11.1. Should a public API declare `throws InvocationTargetException`?

Not necessarily if the Reflection layer already catches and interprets the wrapper. A library may choose to **hide Reflection details** from its external API, exposing only business exceptions or appropriate checked exceptions. If the caller is genuinely responsible for managing Reflection, exposing `ReflectiveOperationException` can also be appropriate.

The design principle is not to force every application layer to know about `InvocationTargetException` merely because a lower implementation layer uses Reflection.

## 12. Be careful with `Throwable` whose cause is an `Error`

A target can throw an `Error`, such as `AssertionError`. When unwrapping:

```java
Throwable cause = wrapper.getCause();
if (cause instanceof Error error) {
    throw error;
}
```

is syntactically valid. However, do not actively catch `Error` broadly and try to "fix" all state. For many `Error`s, the environment or invariants may no longer be trustworthy enough to continue.

If a framework must log and propagate the error to the caller, remember to distinguish failures that occurred **inside the target** from runtime errors that occurred before the target was invoked. Choose a dedicated policy for fatal or unrecoverable errors rather than relying on a single generic handler.

## 13. The `cause` chain: the Reflection wrapper may only be the outermost layer

Suppose the target method already wrapped an I/O error:

```java
public void process() {
    try {
        readConfiguration();
    } catch (IOException e) {
        throw new IllegalStateException(
                "Cấu hình không khả dụng", e);
    }
}
```

This is an illustrative method, assuming `readConfiguration()` is defined appropriately. When invoked via reflection and the target throws `IllegalStateException`, the chain looks like:

```text
InvocationTargetException       ← created by Method.invoke
  └── cause: IllegalStateException("Cấu hình không khả dụng")
        └── cause: IOException("Lỗi đọc cấu hình")
```

A single call to `wrapper.getCause()` only returns the **direct cause**, `IllegalStateException`, not immediately the deepest `IOException`. To inspect the root cause, you can follow each `getCause()` link. However, do not always skip intermediate layers: they may carry important business meaning and useful messages.

### 13.1. Java 17 — Example 7: two explicit cause layers

Create **`ReflectionCauseChainDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionCauseChainDemo {
    public static final class Workflow {
        public void execute() {
            IOException source =
                    new IOException("Đọc dữ liệu lỗi");
            throw new IllegalStateException(
                    "Không hoàn tất workflow", source);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method method =
                Workflow.class.getMethod("execute");

        try {
            method.invoke(new Workflow());
        } catch (InvocationTargetException wrapper) {
            Throwable directCause = wrapper.getCause();
            Throwable rootCause = directCause.getCause();

            System.out.println("Wrapper: "
                    + wrapper.getClass().getSimpleName());
            System.out.println("Direct cause: "
                    + directCause.getClass().getSimpleName());
            System.out.println("Root cause: "
                    + rootCause.getClass().getSimpleName());
            System.out.println("Root message: "
                    + rootCause.getMessage());
            System.out.println("Suppressed on wrapper: "
                    + wrapper.getSuppressed().length);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ReflectionCauseChainDemo.java
java ReflectionCauseChainDemo
```

Stdout:

```text
Wrapper: InvocationTargetException
Direct cause: IllegalStateException
Root cause: IOException
Root message: Đọc dữ liệu lỗi
Suppressed on wrapper: 0
```

Key takeaways:

- The wrapper created by Reflection sits outside an `IllegalStateException` created by application code.
- `IllegalStateException` in turn has `IOException` as its cause.
- `getSuppressed()` is a separate mechanism from `cause`; this example adds no suppressed errors, so the count is 0.
- If the target uses try-with-resources and encounters an error in `close()`, suppressed exceptions may reside on the **target exception** or a deeper `Throwable` in the cause chain, not automatically on the Reflection wrapper.
- Therefore, a logger that only records `wrapper.getMessage()` can lose a lot of information. Log the **full `Throwable`**, or traverse the relationship chain when structured handling is needed.

## 14. Stack traces of the wrapper and the target method

Normally the two `Throwable` objects have two stack traces:

- `InvocationTargetException`: created at the reflective call layer; its trace typically starts in Reflection/JDK classes.
- Target exception: created or thrown in the actual method; its trace typically leads to the line in the target code and its internal callers.

Example log-style output:

```text
java.lang.reflect.InvocationTargetException
    at ... Method.invoke(...)
    at ... ReflectiveCaller.main(...)
Caused by: java.io.IOException: Không đọc được bad
    at ... Service.load(...)
    ... N more
```

This is a **stack trace sketch**, not fixed stderr output. Internal Reflection class names, line numbers, truncated frames, and ordering can vary across JDK versions, execution modes, and loggers.

**For debugging:** usually read from `InvocationTargetException` down to the **`Caused by:`** section. Below that are the type and trace of the actual error created/propagated by the target. Do not stop at the `Method.invoke` line and conclude there is a bug in Java Reflection.

### 14.1. How does `getTargetException()` store the stack?

It returns the **original `Throwable` object** held by the wrapper, without creating a new exception on each call. Read `target.getStackTrace()` to inspect frames associated with the target. Guard against empty trace arrays in general-purpose tools, and do not treat source line numbers as a stable machine contract.

### 14.2. Should you replace the trace with `fillInStackTrace()`?

Usually **no**. When unwrapping and rethrowing the target exception, keeping the original trace helps reveal the original source of the error. Calling `fillInStackTrace()` overwrites the recorded location information, which can make diagnostics lose track of the original target failure. If you need to add context, using a new wrapper with a `cause` or logging context is more appropriate.

## 15. What if the target body itself throws `InvocationTargetException`?

Because it is a public checked exception class, a target method in Java **can also explicitly throw an `InvocationTargetException`**. When calling that method via `Method.invoke`, Reflection wraps the target's `Throwable` in **another wrapper**; thus two layers of the same type can appear:

```text
InvocationTargetException  ← outer wrapper created by Method.invoke
  └── cause: InvocationTargetException ← object thrown by target
        └── cause: IOException
```

This is rarely needed in normal code, but it is useful for understanding why a utility that "continuously unwraps all `InvocationTargetException`s" can erase API layer boundaries. Decide whether you want to strip **the wrapper created by the current `invoke` step** or walk to the deepest cause exception under a different policy.

There is no general rule requiring "a Reflection call to have only one `Throwable` in the chain". Each layer can create its own wrapper.

## 16. `Method.invoke` with `static`, instance, access, and signature

To distinguish wrapper vs. target errors accurately, you need to know several Reflection invocation rules:

| Operation | What must be right | Possible error |
| --- | --- | --- |
| `getMethod(name, parameterTypes)` | Matching public member exists | `NoSuchMethodException` |
| `getDeclaredMethod(...)` | Directly declared member exists | `NoSuchMethodException` |
| `invoke(receiver, args...)` on instance method | Non-null receiver compatible with declaring class | `NullPointerException` or `IllegalArgumentException` from API |
| `invoke(null, args...)` on static method | `null` receiver is accepted | Method body can still produce wrapper on failure |
| Passing arguments | Count/types compatible with signature, accounting for valid boxing/widening | `IllegalArgumentException` from Reflection |
| Calling restricted-access member | Access permitted by Java/module rules | `IllegalAccessException` or encapsulation issue |
| Target body executes and throws | Target code raises `Throwable` | `InvocationTargetException` with cause |

**Varargs note:** the Java signature `Object... args` of `Method.invoke` follows varargs rules at **Reflection's own call site**, which is distinct from a target method's varargs parameter. For a method taking a single array parameter, you may need to cast `(Object) array` to pass one array object instead of having the compiler expand it as varargs for `invoke`. This is an argument-passing issue, not a way to fix target errors.

### 16.1. Returned metadata does not guarantee the target will be invoked

Method lookup can succeed while `invoke` is rejected due to access. With generic bridge methods, inherited methods, visibility, or module encapsulation, you sometimes need to understand the actual resolved method and context class loader. Do not attribute every pre-target failure to a target exception.

## 17. `Class.newInstance()` and why to avoid it

The old `Class.newInstance()` API has been **deprecated** since Java 9. One confusing aspect is that its handling of constructor exceptions differs from the consistent wrapping mechanism of `Constructor.newInstance(...)`, and it can propagate checked constructor exceptions in ways that bypass compile-time type checking unexpectedly.

In modern Java 17 code, prefer:

```java
Constructor<MyType> constructor =
        MyType.class.getDeclaredConstructor();

MyType instance = constructor.newInstance();
```

This is an **illustrative snippet**; it requires importing `Constructor`, an appropriate `MyType` class, and handling checked reflection exceptions. If the constructor throws an error, `Constructor.newInstance` reports `InvocationTargetException`; the caller can unwrap `getCause()`.

Do not write guides recommending `Class.newInstance()` as the standard API when clearer constructor reflection exists.

## 18. `MethodHandles` has a different mechanism from `Method.invoke`

Reflection's `Method.invoke` and the `java.lang.invoke.MethodHandle` API have different forms, type checking, and exception contracts. When invoking a method handle via `invokeExact`/`invoke`/`invokeWithArguments`, an exception thrown by the target **can propagate directly** according to the method-handle invocation contract, without necessarily being wrapped into `InvocationTargetException` like `Method.invoke`.

Do not assume:

> "Whenever a method is invoked dynamically, there will be an `InvocationTargetException`."

That only holds for specific APIs that define such a wrapping mechanism, notably `Method.invoke` and `Constructor.newInstance`.

### 18.1. Java 17 — Example 8: `MethodHandle` letting `IOException` pass through directly

Create **`MethodHandleVsReflectionDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class MethodHandleVsReflectionDemo {
    public static void fail() throws IOException {
        throw new IOException("Lỗi gốc");
    }

    public static void main(String[] args) throws Throwable {
        Method method =
                MethodHandleVsReflectionDemo.class.getMethod("fail");

        try {
            method.invoke(null);
        } catch (InvocationTargetException e) {
            System.out.println("Reflection: "
                    + e.getClass().getSimpleName());
            System.out.println("Reflection cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        MethodHandle handle = MethodHandles.lookup()
                .findStatic(MethodHandleVsReflectionDemo.class,
                        "fail", MethodType.methodType(void.class));

        try {
            handle.invokeWithArguments();
        } catch (IOException e) {
            System.out.println("MethodHandle: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 MethodHandleVsReflectionDemo.java
java MethodHandleVsReflectionDemo
```

Stdout:

```text
Reflection: InvocationTargetException
Reflection cause: IOException
MethodHandle: IOException
Message: Lỗi gốc
```

**Explanation:** the same static method `fail()` throws `IOException`. `Method.invoke(null)` wraps the target error in `InvocationTargetException`, whereas `MethodHandle.invokeWithArguments()` in this example lets `IOException` reach the handler directly. This is an **API contract** comparison, not proof that method handles are always faster or can replace reflection in all cases.

Declaring `throws Throwable` on `main` is only to illustrate the full checked `Throwable` contract that the method handle API can expose; in a production API, choose an appropriate boundary, exception types, and policy.

## 19. Dynamic proxy: `UndeclaredThrowableException` may occur instead of this wrapper

`java.lang.reflect.Proxy` uses `InvocationHandler.invoke(...)`, which has its own contract. When the handler throws a **checked `Throwable` not among the types permitted by the interface method**, the proxy call can throw `java.lang.reflect.UndeclaredThrowableException` (unchecked), preserving the original error via `getUndeclaredThrowable()`/`getCause()`.

This is **different** from `InvocationTargetException` created by `Method.invoke` when a target method throws an error.

Illustrative example:

```text
Proxy interface method: void run()      (does not throw IOException)
InvocationHandler: throw new IOException("network")
Caller of proxy: UndeclaredThrowableException
    └── cause: IOException
```

Do not confuse the two classes just because both are in `java.lang.reflect` and both relate to "dynamic invocation".

### 19.1. When an `InvocationHandler` itself uses `Method.invoke`

If the handler receives a `Method method` and calls `method.invoke(realTarget, args)`, it can receive `InvocationTargetException` from Reflection. If the handler **rethrows the checked wrapper as-is** when the proxy interface method does not declare that type, the proxy may wrap it again into `UndeclaredThrowableException`. Thus the chain can become:

```text
UndeclaredThrowableException
  └── cause: InvocationTargetException
        └── cause: IOException
```

A well-designed handler needs a policy to **unwrap the Reflection wrapper appropriately** and decide how to map the error to the proxy interface's contract. Do not turn all target failures into an unrelated wrapper that the caller cannot understand.

### 19.2. Do not apply Reflection unwrap logic to every proxy error

A proxy can throw errors from the proxy itself or from the handler directly. If there is no actual `InvocationTargetException` in the chain, do not force a cast. Check each API, then read the cause if needed.

## 20. Java 17 — Example 9: `UndeclaredThrowableException` in a proxy

Create **`ProxyUndeclaredExceptionDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

public class ProxyUndeclaredExceptionDemo {
    public interface Task {
        void run();
    }

    public static void main(String[] args) {
        Task task = (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] {Task.class},
                (proxy, method, values) -> {
                    throw new IOException("I/O trong handler");
                });

        try {
            task.run();
        } catch (UndeclaredThrowableException e) {
            System.out.println("Proxy wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Undeclared: "
                    + e.getUndeclaredThrowable()
                            .getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ProxyUndeclaredExceptionDemo.java
java ProxyUndeclaredExceptionDemo
```

Stdout:

```text
Proxy wrapper: UndeclaredThrowableException
Undeclared: IOException
Cause message: I/O trong handler
```

**Meaning:** `Task.run()` has no checked `throws`, yet the handler throws a checked `IOException`. The proxy must report the error using an unchecked wrapper consistent with the interface method's contract. This is not `Method.invoke`; there is no `InvocationTargetException` in this example.

When designing a real proxy, separate errors from the business implementation, errors from the handler, and Reflection errors from any Reflection calls the handler may use.

## 21. Misconceptions to fix immediately

| Misconception | Reality |
| --- | --- |
| "`InvocationTargetException` is the business error itself." | It is usually a wrapper created by Reflection; the target error is in `getCause()`. |
| "Only checked exceptions from the target get wrapped." | The target can throw an unchecked exception or `Error`, and `Method.invoke` still uses the wrapper for target-thrown `Throwable`s. |
| "`getTargetException()` returns a message string." | It returns a `Throwable` object. |
| "`getCause()` and `getTargetException()` are always different." | In a standard Reflection wrapper, they point to the same target throwable. |
| "`method.invoke` throws `IOException` directly because the original method `throws IOException`." | The Reflection caller sees checked `InvocationTargetException`; unwrap it to get `IOException`. |
| "`IllegalArgumentException` around `invoke` is always from the target." | Wrong arguments can make the `invoke` API itself throw `IllegalArgumentException` directly. |
| "If a method is not found, you must unwrap the target." | `NoSuchMethodException` occurs during lookup; no target invocation happened yet. |
| "`IllegalAccessException` is an exception from the body." | It is usually a Reflection access-check failure. |
| "If the wrapper exists, the entire method body finished running." | The target threw and terminated abnormally; the body may have stopped very early. |
| "If the target body throws `NullPointerException`, `catch (NullPointerException)` around `invoke` will catch it." | Normally the caller sees `InvocationTargetException` wrapping the NPE. |
| "The wrapper's stack trace is enough to find the original line of code." | You need to inspect `Caused by`/the target's stack. |
| "`wrapper.getMessage()` always matches the original error message." | You must read the message from the actual cause. |
| "You can catch `Exception` and cast `cause` to `RuntimeException`." | It could be null, the wrong type, checked, or an `Error`; you must classify safely. |
| "The wrapper automatically rolls back side effects." | Exception chaining only preserves information; it does not undo state. |
| "`Constructor.newInstance` does not use `InvocationTargetException`." | A target constructor throwing an error can be wrapped. |
| "`Class.newInstance()` is the modern choice." | That old API is deprecated; prefer constructor reflection. |
| "`MethodHandle` also always wraps the target in `InvocationTargetException`." | `MethodHandle` invocation has a different contract and can pass the target `Throwable` directly. |
| "Proxy and Reflection always use the same wrapper." | Dynamic proxy can use `UndeclaredThrowableException`. |
| "Logging just the wrapper class name is enough to know the root cause." | Log the full `Throwable`/cause chain and safe contextual information. |

## 22. How to debug in a framework using Reflection

Many frameworks invoke application methods indirectly: test runners, plugin systems, dependency injection, command dispatchers, runtime annotation processors, or dynamic callback registries. When `InvocationTargetException` appears in logs:

1. **Read the cause structure:** what type and message does `wrapper.getCause()` have?
2. **Inspect the cause's stack trace** to locate the position in the target method's code.
3. Identify the invoked method/constructor, the receiver, and the argument count/types.
4. If `NoSuchMethodException`/`IllegalAccessException` occurs outside the wrapper, fix the lookup/access permissions rather than debugging the body.
5. If the target threw a checked exception (e.g., `IOException`), ask which layer has the retry/fallback policy or should report failure.
6. If the target threw an unchecked exception, check inputs, invariants, and state before the throw.
7. If there are multiple wrappers, traverse the chain purposefully rather than mechanically calling `cause.getCause()`.
8. If the target uses resources, inspect `getSuppressed()` on the target `Throwable` and relevant causes when cleanup errors occur.
9. Assess side effects before failure: did the operation already write data, make network calls, or mutate a cache?
10. Place logging/monitoring at the appropriate boundary, without printing raw stacks/causes to public clients.

### 22.1. Example of meaningful logging

Instead of just:

```text
ERROR InvocationTargetException
```

a more useful report might record:

```text
Operation: Service.load
Wrapper: InvocationTargetException
Cause type: IOException
Cause message: Không đọc được bad
Correlation ID: REQ-42
```

This is an **illustrative format**, not a specific logger API. With a real logger, it is better to pass the `Throwable` object itself as the error argument to preserve stack/cause/suppressed information, while logging context according to your data policy.

## 23. Preserving stack and cause across layer boundaries

An adapter may want to translate a target error into a business exception:

```java
try {
    method.invoke(target);
} catch (InvocationTargetException wrapper) {
    throw new ServiceOperationException(
            "Không hoàn tất thao tác", wrapper.getCause());
}
```

This is a **code snippet** assuming `ServiceOperationException` has a constructor accepting a cause and that other checked Reflection exceptions are handled.

You have two options with different meanings:

- **Keep the target cause itself as the cause of the business wrapper:** convenient for callers to classify the root cause and reduces Reflection layers in the cause chain if outer layers do not need Reflection details.
- **Keep `InvocationTargetException` as the cause:** useful when you need to show that the Reflection layer itself failed, though it may expose implementation details to multiple layers.

There is no universal rule requiring the Reflection wrapper to be stripped everywhere. What matters is **preserving the causal path**, without losing the target exception or forcing all cases into an inappropriate error type.

### 23.1. Do not silently drop suppressed exception info

If the target throwable has suppressed exceptions, passing **the same target object** as the cause preserves the suppressed exceptions on that object. If you create a new exception using only `getMessage()` without passing the cause, suppressed information can be lost from the error report.

This is especially important when the target uses try-with-resources: the body throws one error, `close()` throws a secondary error, and Reflection wraps the primary error in `InvocationTargetException`.

## 24. When should Reflection be used instead of a direct call?

If the target type and method name are known at compile time, a direct call is usually:

- Simpler, with clear static type checking and checked exception checking.
- Easier to refactor, with full IDE support.
- Free of lookup or Reflection wrapper unwrapping.
- Easier to read and test.

Reflection is appropriate when **dynamism** is genuinely required: frameworks loading plugins, discovering handlers by annotation, instantiating objects from metadata, invoking runtime-selected methods, test runners, dependency injection, or extension models.

**Design rule:** do not use Reflection just to invoke a method that is already statically known. If you must use it, encapsulate lookup/invoke/error translation in one layer rather than letting `InvocationTargetException` leak throughout business code unnecessarily.

## 25. Practice exercises

### Exercise 1 — Distinguishing wrapper and target

Run `ReflectiveMethodFailureDemo`. Change the error in `load("bad")` to `IllegalStateException("input")`. Predict `wrapper.getClass()` and `wrapper.getCause().getClass()`. Is `catch(IOException)` needed around `Method.invoke`? Explain using the API signature.

### Exercise 2 — Wrong argument vs. target-throw

In `ReflectionVsTargetDemo`, change `method.invoke(target, 123)` to `method.invoke(target, "boom")` and observe the exception type at the caller. Explain why one case produces a direct `IllegalArgumentException` from Reflection, while the other produces a wrapper with `IllegalStateException` as its cause.

### Exercise 3 — Target constructor

Add a condition `if (amount == 0) throw new IllegalStateException("zero");` to `Account`. Invoke the constructor reflectively with `0` and `-1`; determine whether the wrapper is the same and how the cause differs.

### Exercise 4 — Reading the cause chain

Run `ReflectionCauseChainDemo`. In the handler, print the message of the wrapper, the direct cause, and the root cause. Why shouldn't you rely on the wrapper message for business errors? Which getters do you use to inspect `IOException`?

### Exercise 5 — Rethrowing a checked exception

Run `RethrowTargetIOExceptionDemo`. Change `runReflectively` to wrap `IOException` in `IllegalStateException("...", cause)` instead of rethrowing it directly. How must the caller update its handler? Compare the stack trace of the new wrapper and the original cause.

### Exercise 6 — Comparing with `MethodHandle`

Run `MethodHandleVsReflectionDemo`. Name which API produces `InvocationTargetException` when `fail` throws `IOException` and which API lets `IOException` pass through directly in the example. Do not use this result to speculate about performance.

### Exercise 7 — Proxy

Run `ProxyUndeclaredExceptionDemo`. Add `throws IOException` to the `Task.run()` declaration. Predict the difference in whether the checked exception can pass through the proxy method when the handler throws `IOException`. Explain why you should not try to catch `InvocationTargetException` in code that only calls the proxy directly.

### Exercise 8 — Returning `void` and `static`

Run `ReflectiveReturnValuesDemo`. Why does `ping.invoke(target)` return `null`, whereas `version.invoke(null)` returns `"v1"`? If you call an **instance method** via `invoke(null)`, does the error belong to target failure or invocation preparation failure?

### Exercise 9 — API design

A plugin framework selects a method by name and invokes it via `Method.invoke`. Design the error-reporting API: should the caller see `InvocationTargetException`, or should it receive `PluginExecutionException` with the target throwable as its cause? State the pros and cons of both options.

### Exercise 10 — Root cause and suppressed

Suppose the target uses try-with-resources, the body throws `IOException("read")`, `close()` throws `IOException("close")`, and Reflection wraps the error. Draw the structure wrapper → target primary → suppressed. Which getter methods access each layer? Why can `wrapper.getSuppressed().length` be `0` while the target still has suppressed errors?

### Exercise 11 — Lookup failure

Create a public method `hello(int)`. Call `getMethod("hello", String.class)`. Does the compiler detect the mistake? What is the actual exception? Does the method body run? Why is this **not** `InvocationTargetException`?

### Exercise 12 — Stable testing

Write a JUnit 5 test using `assertThrows(InvocationTargetException.class, () -> method.invoke(target))` when the target body deliberately throws `IllegalArgumentException`. Assert the cause type/message without comparing stack trace text or JDK line numbers.

## 26. Checklist for understanding and handling correctly

- [ ] Do I know that `InvocationTargetException` is a checked subtype of `ReflectiveOperationException`?
- [ ] Do I clearly distinguish the exception **wrapped** by `Method.invoke`/`Constructor.newInstance` from the **actual** target error?
- [ ] Do I know that `getCause()`/`getTargetException()` returns the original `Throwable`, not a message?
- [ ] Do I understand that target errors whether checked, unchecked, or `Error` can all be wrapped?
- [ ] Do I avoid catching `IOException` alone around `Method.invoke` expecting a checked `IOException` from the body?
- [ ] Have I distinguished lookup failure (`NoSuchMethodException`) from invocation failure?
- [ ] Do I avoid confusing Reflection argument/access/null-receiver errors with errors from the target body?
- [ ] Do I understand that the wrapper's `getStackTrace()` differs from the cause's stack trace?
- [ ] When unwrapping, do I classify `IOException`, `RuntimeException`, `Error`, and other checked exceptions according to the contract?
- [ ] Do I avoid casting every cause directly to `RuntimeException`?
- [ ] When translating exceptions at a higher layer, do I preserve the target `Throwable` as the cause when appropriate?
- [ ] Do I remember that the wrapper does not roll back side effects of a method/constructor that ran before the error?
- [ ] For constructor reflection, do I know that finding metadata does not automatically grant permission to invoke?
- [ ] Do I know that the legacy `Class.newInstance()` is deprecated and has a different exception mechanism?
- [ ] Do I avoid assuming `MethodHandle` or proxies always use `InvocationTargetException`?
- [ ] Have I distinguished `UndeclaredThrowableException` from proxies from `InvocationTargetException` from `Method.invoke`?
- [ ] When there are multiple wrapping layers, do I traverse the cause chain purposefully without losing suppressed exception info?
- [ ] Do I log target failures completely without exposing internal stack traces to public clients?
- [ ] Have I considered a direct call when the method is known at compile time instead of unnecessary Reflection?
- [ ] Do I have tests for at least one success case, target failure, lookup failure, and argument failure?

**Conclusion:** `InvocationTargetException` is **the wrapper class reported by Reflection APIs such as `Method.invoke` and `Constructor.newInstance` when the invoked code throws an error**. To find the actual exception, use **`getCause()` or `getTargetException()`**. Do not equate Reflection API errors before the body runs with errors from the target, do not infer the target exception from the wrapper's message, and preserve the cause/stack when translating errors to an external contract. Reading the right exception layer makes diagnosing systems that use Reflection clearer and prevents mishandling failure types.