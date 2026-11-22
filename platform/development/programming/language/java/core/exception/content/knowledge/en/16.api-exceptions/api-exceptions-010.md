# UndeclaredThrowableException When Using Dynamic Proxies in Java

> **Java Core – Exception** · Group: **API Exceptions** · Focus: why an `InvocationHandler` can throw a checked exception yet a call through a JDK dynamic proxy receives `UndeclaredThrowableException`; how to preserve the cause, unwrap `InvocationTargetException` when delegating via reflection, and design `throws` contracts properly. Examples compatible with **Java 17+**.

## 1. Symptom: Method Does Not Declare IOException, Yet the Proxy Encounters an I/O Error

Suppose a public interface has the following method:

~~~java
interface Service {
    String find();
}
~~~

The snippet above is a valid standalone interface declaration. Because the `find()` method **declares no checked exceptions**, a normal caller can invoke it without catching or declaring `IOException`.

However, a JDK dynamic proxy created for that interface can be backed by an `InvocationHandler`, and the handler throws:

~~~java
throw new java.io.IOException("remote service offline");
~~~

This line is an example inside a handler or a method permitted to throw `IOException`. When the caller invokes `proxy.find()`, it normally **does not receive `IOException` directly**. Under the JDK dynamic proxy mechanism, a checked exception from `InvocationHandler.invoke(...)` that **is not compatible with the `throws` clause of the invoked method** is wrapped in:

~~~text
java.lang.reflect.UndeclaredThrowableException
    └── java.io.IOException: remote service offline
~~~

**Full name:** `java.lang.reflect.UndeclaredThrowableException`, commonly abbreviated as **UTE**.

UTE extends `RuntimeException`, making it an **unchecked exception**. The original exception can be retrieved via:

~~~java
Throwable original = ex.getUndeclaredThrowable();
// Or, using the standard exception chaining mechanism:
Throwable cause = ex.getCause();
~~~

This snippet illustrates code inside a handler with a variable `ex` of type `UndeclaredThrowableException`. The Java 17 UTE API specifies that `getUndeclaredThrowable()` and `getCause()` expose the same wrapped exception according to this class's chaining mechanism.

**Key takeaway:** UTE does not necessarily indicate a bug in the proxy class itself. It usually signals that **an exception escaping the invocation handler does not match the checked exception contract of the interface the proxy implements**.

## 2. Three Components to Distinguish

### 2.1. Interface: The Contract Visible to the Caller

~~~java
interface Repository {
    String load() throws java.io.IOException;
}
~~~

The `load()` contract allows the caller to receive `IOException` (or an appropriate checked subtype). If a dynamic implementation cannot complete the operation, it may propagate the original `IOException` along the permitted path.

In contrast:

~~~java
interface Service {
    String load();
}
~~~

The contract of `Service.load()` **does not allow a checked `IOException` to escape at compile time**. Consumers of the interface are not required (and in some usages cannot even validly write) a `catch (IOException)` block for this standalone call if there is no other source of checked `IOException` inside the `try` block.

### 2.2. InvocationHandler: The Dynamic Call Router

The JDK provides the interface:

~~~java
@FunctionalInterface
public interface InvocationHandler {
    Object invoke(Object proxy, Method method, Object[] args)
            throws Throwable;
}
~~~

This is an **abbreviated illustrative signature**: `Method` is `java.lang.reflect.Method`; in Java SE 17, `InvocationHandler` has a single abstract method `invoke` with this signature. The declaration above is not meant to redefine a class/interface with the same name in the standard package.

The three parameters:

- `proxy`: the proxy instance receiving the call.
- `method`: the `Method` metadata corresponding to the interface method invoked.
- `args`: the arguments passed, or `null` when there are no arguments.

The `Object` return type lets the proxy convert/cast the value to the method's return type. If an interface method returns a primitive type and the handler returns `null` or an incompatible wrapper type, the proxy may throw `NullPointerException` or `ClassCastException`; that is the **return-value mechanism**, distinct from UTE.

The most misleading part is the signature:

~~~java
Object invoke(...) throws Throwable
~~~

It allows **handler code** to write `throw new IOException(...)`, `throw new SQLException(...)`, or throw another checked exception as far as compiler checking inside the handler is concerned. **However, the handler's broad signature does not widen the `throws` clauses of the interface methods exposed by the proxy to the caller.**

### 2.3. Proxy Object: Where the Actual Contract Is Enforced

A proxy is created via:

~~~java
Service service = (Service) Proxy.newProxyInstance(
        Service.class.getClassLoader(),
        new Class<?>[] { Service.class },
        handler);
~~~

This is an illustrative snippet: you need to import `java.lang.reflect.Proxy` and define `Service` and `handler`. The generated object implements one or more **specified interfaces**, and most interface method calls are dispatched to the handler.

When the handler throws a `Throwable`, the proxy follows these rules:

1. If it is a **RuntimeException** or subtype → propagates directly; not wrapped in UTE because it is unchecked.
2. If it is an **Error** or subtype → propagates directly; not wrapped in UTE.
3. If it is a **checked Throwable** whose type is compatible with the proxy method's `throws` clause → permitted to propagate directly.
4. If it is an **incompatible checked Throwable** → the proxy creates/throws an `UndeclaredThrowableException` containing that `Throwable`.

These points describe the **JDK Proxy/InvocationHandler contract**, not a rule that every proxy type in every external framework implements identically.

## 3. Diagram of the Mechanism Leading to UTE

~~~text
Caller
  |
  | calls service.find()
  v
JDK dynamic proxy (method declared by interface)
  |
  | delegates to InvocationHandler.invoke(...)
  v
Handler executes logic
  |
  +-- returns normal value ---------------> proxy returns to caller
  |
  +-- throws RuntimeException/Error ------> propagates to caller
  |
  +-- throws compatible checked ----------> propagates to caller
  |
  +-- throws incompatible checked
          |
          v
    UndeclaredThrowableException
          |
          +-- getUndeclaredThrowable() --> original Throwable
          +-- getCause() ----------------> original Throwable
          |
          v
       caller receives UTE
~~~

For example, `interface Service { String find(); }` has no `throws` clause. If the handler throws `IOException`, the caller receives UTE. If the contract is changed to `String find() throws IOException;`, the same `IOException` can propagate directly.

**Caveat:** The proxy is permitted to wrap a checked exception **thrown by the handler that is not compatibly declared**. If ordinary code manually executes `throw new UndeclaredThrowableException(...)`, you will also encounter the UTE class, but that alone is not proof that the error originated from a proxy. Inspect the stack trace and exception chain before drawing conclusions.

## 4. Complete Java 17 Program: Exception Types Through a Proxy

Save the full code as **`UndeclaredThrowableProxyDemo.java`**. The program demonstrates:

- `IOException` **declared by the interface method** → propagates directly.
- `IOException` **not declared by the interface method** → UTE.
- `IllegalStateException` (**unchecked**) → propagates directly.
- `AssertionError` (**Error**) → propagates directly.
- Handler uses `Method.invoke` but **forgets to unwrap `InvocationTargetException`** → UTE wrapping `InvocationTargetException`.
- Handler properly unwraps `InvocationTargetException` → the original `IOException` propagates directly, matching the interface contract.

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

public class UndeclaredThrowableProxyDemo {
    public interface Service {
        String declared() throws IOException;
        String undeclared();
        String unchecked();
        String serious();
    }

    private static Service proxyFor(InvocationHandler handler) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] {Service.class},
                handler);
    }

    private static void show(String label, Runnable call) {
        System.out.println("== " + label + " ==");
        try {
            call.run();
        } catch (UndeclaredThrowableException ex) {
            Throwable root = ex.getUndeclaredThrowable();
            System.out.println("outer=" + ex.getClass().getSimpleName());
            System.out.println("wrapped=" + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
            System.out.println("same-cause=" + (ex.getCause() == root));
        } catch (RuntimeException ex) {
            System.out.println("runtime=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        } catch (AssertionError ex) {
            System.out.println("error=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }

    public interface Repository {
        String load() throws IOException;
    }

    public static final class RepositoryImpl implements Repository {
        @Override
        public String load() throws IOException {
            throw new IOException("disk offline");
        }
    }

    private static Repository reflected(Repository target, boolean unwrap) {
        InvocationHandler handler = (Object proxy, Method method, Object[] args) -> {
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                if (unwrap) {
                    throw ex.getCause();
                }
                throw ex;
            }
        };
        return (Repository) Proxy.newProxyInstance(
                Repository.class.getClassLoader(),
                new Class<?>[] {Repository.class},
                handler);
    }

    public static void main(String[] args) {
        Service service = proxyFor((proxy, method, arguments) -> {
            switch (method.getName()) {
                case "declared":
                    throw new IOException("declared checked");
                case "undeclared":
                    throw new IOException("not in interface");
                case "unchecked":
                    throw new IllegalStateException("business state");
                case "serious":
                    throw new AssertionError("fatal condition");
                default:
                    throw new IllegalArgumentException("unknown method");
            }
        });

        System.out.println("== declared checked ==");
        try {
            service.declared();
        } catch (IOException ex) {
            System.out.println("checked=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }

        show("undeclared checked", service::undeclared);
        show("unchecked", service::unchecked);
        show("error", service::serious);

        Repository target = new RepositoryImpl();
        System.out.println("== reflection without unwrap ==");
        try {
            reflected(target, false).load();
        } catch (UndeclaredThrowableException ex) {
            Throwable wrapper = ex.getUndeclaredThrowable();
            System.out.println("outer=" + ex.getClass().getSimpleName());
            System.out.println("wrapped=" + wrapper.getClass().getSimpleName());
            System.out.println("target=" + ((InvocationTargetException) wrapper)
                    .getTargetException().getMessage());
        } catch (IOException ex) {
            System.out.println("unexpected=" + ex);
        }

        System.out.println("== reflection with unwrap ==");
        try {
            reflected(target, true).load();
        } catch (IOException ex) {
            System.out.println("checked=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }
}
~~~

### Compile and Run

~~~bash
javac --release 17 -encoding UTF-8 UndeclaredThrowableProxyDemo.java
java UndeclaredThrowableProxyDemo
~~~

**Verified stdout from compiling and running:**

~~~text
== declared checked ==
checked=IOException: declared checked
== undeclared checked ==
outer=UndeclaredThrowableException
wrapped=IOException: not in interface
same-cause=true
== unchecked ==
runtime=IllegalStateException: business state
== error ==
error=AssertionError: fatal condition
== reflection without unwrap ==
outer=UndeclaredThrowableException
wrapped=InvocationTargetException
target=disk offline
== reflection with unwrap ==
checked=IOException: disk offline
~~~

The program runs on a JDK supporting Java 17 at `javac --release 17`. The exceptions are created intentionally, there is no external network or file I/O, and stdout does not depend on stack trace line numbers.

**Note on the `show` helper:** It uses `Runnable` and method references to represent calls **that declare no checked exceptions**. By contrast, `service.declared()` is called in its own `try/catch (IOException)` block because its signature is checked. This also illustrates the compile-time difference between methods on the same interface.

## 5. Breakdown of Each Branch in the Example

### 5.1. Declared Checked: IOException Propagates Directly

The interface defines:

~~~java
String declared() throws IOException;
~~~

The handler throws:

~~~java
throw new IOException("declared checked");
~~~

At the proxy, the runtime type `IOException` matches `throws IOException`. Therefore, the caller catches `IOException` **directly** and prints:

~~~text
checked=IOException: declared checked
~~~

There is no UTE here. `InvocationHandler.invoke() throws Throwable` does not cause every checked exception to be wrapped: the proxy **wraps only if the checked type is incompatible with the method contract**.

Subtypes are also accepted. For example, if the method declares `throws IOException`, the handler can throw `FileNotFoundException`, which extends `IOException`, and the proxy will propagate that subtype directly.

### 5.2. Undeclared Checked: IOException Is Wrapped in UTE

The interface defines:

~~~java
String undeclared();
~~~

The handler still throws `IOException`:

~~~java
throw new IOException("not in interface");
~~~

The caller invokes a method with no checked `throws` clause, so the proxy throws:

~~~text
outer=UndeclaredThrowableException
wrapped=IOException: not in interface
same-cause=true
~~~

Checking:

~~~java
ex.getUndeclaredThrowable() == ex.getCause()
~~~

evaluates to `true` in the program; the wrapped exception is the exact `IOException` thrown by the handler.

**Important:** The original `IOException` is not lost. UTE is a **wrapper**. When diagnosing issues, do not log only `ex.getMessage()`; preserve the `Throwable` object and inspect its cause and stack trace.

### 5.3. Unchecked Exceptions Pass Through Without Declaration

The handler throws:

~~~java
throw new IllegalStateException("business state");
~~~

`IllegalStateException extends RuntimeException`, which is unchecked. The proxy propagates the same exception type, and the caller prints:

~~~text
runtime=IllegalStateException: business state
~~~

This is not UTE. The same rule applies to other `RuntimeException` types, including `IllegalArgumentException` and `NullPointerException`.

**Do not assume every unchecked exception is safe to ignore and continue business logic.** Letting exceptions pass through a proxy does not exempt you from designing error handling, rollback, logging, and task termination at appropriate boundaries.

### 5.4. Errors Are Not Converted to UTE by the Proxy Either

The handler throws:

~~~java
throw new AssertionError("fatal condition");
~~~

`AssertionError` belongs to the `Error` branch, which is unchecked. Output:

~~~text
error=AssertionError: fatal condition
~~~

Here the example **catches `AssertionError` solely to demonstrate** that `Error` types are not wrapped in UTE. In real applications, do not catch all `Error` instances and treat them as ordinary business failures; `Error` typically indicates severe conditions or broken invariants where execution cannot reliably continue.

### 5.5. Catch Order Also Applies to UTE

Because UTE extends `RuntimeException`, if both appear in the same `catch` chain, the UTE handler must precede the `RuntimeException` handler:

~~~java
try {
    service.undeclared();
} catch (UndeclaredThrowableException ex) {
    handleProxyMismatch(ex);
} catch (RuntimeException ex) {
    handleOtherRuntimeFailure(ex);
}
~~~

This is an illustrative snippet; the handler methods must be defined. If `catch (RuntimeException)` is placed first, the subsequent UTE handler is shadowed and rejected by the compiler as an unreachable catch block.

Conversely, `catch (IOException)` **cannot automatically catch an `IOException` hidden inside a UTE**. A `catch` block matches the `Throwable` type **actually thrown at the current layer**. To trace the `IOException`, inspect the cause and check its original type, or fix the contract/handler to propagate it directly if appropriate.

## 6. The Biggest Trap: Method.invoke Creates InvocationTargetException

A dynamic proxy is often used to add logging, metrics, retries, or access control before and after calling a real target object.

Delegating via reflection:

~~~java
InvocationHandler handler = (proxy, method, args) -> method.invoke(target, args);
~~~

This is an illustrative snippet requiring a `target` variable with the corresponding method.

**The problem:** When a method **invoked via reflection** throws an exception, `Method.invoke(...)` uses a separate checked wrapper:

~~~text
InvocationTargetException
    └── actual exception thrown by target method
~~~

For example, the target's `Repository.load() throws IOException` method throws `IOException("disk offline")`. `method.invoke(target, args)` does not propagate that `IOException` directly to the handler; instead, it throws `InvocationTargetException`.

`InvocationTargetException` is a checked exception in `java.lang.reflect` and **is not a subtype of `IOException`**.

If the handler simply writes:

~~~java
return method.invoke(target, args);
~~~

then `InvocationTargetException` can escape `InvocationHandler.invoke()` (because the handler declares `throws Throwable`). However, the interface method `Repository.load()` only permits checked `IOException`. The proxy checks **the actual checked type escaping the handler**, sees that `InvocationTargetException` is incompatible, and **wraps it further in UTE**:

~~~text
UndeclaredThrowableException
    └── InvocationTargetException
          └── IOException("disk offline")
~~~

This is the **double wrapping** phenomenon commonly seen in AOP or custom proxy frameworks.

### 6.1. Output Proving Double Wrapping

In the full program, `reflected(target, false)` does not unwrap `InvocationTargetException`. Output:

~~~text
== reflection without unwrap ==
outer=UndeclaredThrowableException
wrapped=InvocationTargetException
target=disk offline
~~~

The critical point: even though the interface method **already declares `throws IOException`**, the caller **still receives UTE** because the checked object thrown out of the handler is **`InvocationTargetException`**, not the original `IOException`.

This is why you cannot look solely at the original exception's name or the interface signature and conclude that the proxy will propagate it directly. You must check **which wrapper class escapes the handler**.

### 6.2. The Fix: Unwrap InvocationTargetException Inside the Handler

Excerpt from the example:

~~~java
InvocationHandler handler = (proxy, method, args) -> {
    try {
        return method.invoke(target, args);
    } catch (InvocationTargetException ex) {
        throw ex.getCause();
    }
};
~~~

Illustrative code inside a method with a valid `target` variable and imports for `InvocationHandler` and `InvocationTargetException`.

`ex.getCause()` or `ex.getTargetException()` retrieves the actual `Throwable` thrown by the target. The handler rethrows the **original exception**:

- If the original is `IOException` and the interface allows `IOException` → the proxy propagates it directly.
- If the original is `RuntimeException`/`Error` → the proxy propagates it directly via the unchecked branch.
- If the original is a checked exception **not in the interface contract** → the proxy **still** wraps it in UTE. Unwrapping does not make an out-of-contract exception valid.

Output of the fixed branch:

~~~text
== reflection with unwrap ==
checked=IOException: disk offline
~~~

**Why unwrap in the handler rather than catching UTE at every caller?** The handler is the layer that introduced the reflection wrapper. Fixing it there preserves the public API contract, avoids forcing every caller to understand implementation details, and keeps interface usage clean and straightforward.

### 6.3. Other Exceptions from Method.invoke

`Method.invoke` can throw `IllegalAccessException` if access is denied, `IllegalArgumentException` when arguments or the receiver are invalid, and other reflection-related errors. Do not catch all `Exception` types and assume they are all "business `IOException`s from the target."

If the issue is a **reflection configuration** error, it may be more appropriate to throw an unchecked exception with a clear message and cause to report the framework/implementation bug. Do not turn `IllegalAccessException` into `IOException` just to satisfy an interface signature when the proxy infrastructure itself is misconfigured.

## 7. Reading UTE and Tracing the Root Cause

When you catch a UTE, start with:

~~~java
catch (UndeclaredThrowableException ex) {
    Throwable original = ex.getUndeclaredThrowable();
    // Log ex along with original/cause in full according to policy.
}
~~~

This is an illustrative handler inside an appropriate `try/catch` structure.

Commonly used APIs:

| API | Value |
| --- | --- |
| `ex.getUndeclaredThrowable()` | The wrapped `Throwable` per UTE's specialized contract; may be `null` with some constructors |
| `ex.getCause()` | The cause per `Throwable`'s general chaining mechanism; for UTE constructed with a wrapped exception, references the same `Throwable` |
| `ex.printStackTrace()` | Prints UTE, its cause, and stack trace, revealing the wrapping layers |
| `ex.getSuppressed()` | Suppressed exceptions attached to the UTE itself, if any; does not automatically imply a proxy bug |

Do not log only:

~~~java
System.err.println(ex.getMessage());
~~~

UTE's message may be uninformative or contain a string representation of the wrapped layer rather than sufficient business context. Log the **exception object**, preserving the stack trace and cause.

### 7.1. Should You Unwrap Every Exception in a Loop?

When acting as an **observability/diagnostics layer**, you may need to walk the chain UTE → `InvocationTargetException` → `IOException` to identify the root cause.

However, **do not automatically rethrow the "deepest root cause" everywhere**: a wrapper may represent important context or a public API contract; stripping all wrappers can cause callers to receive a checked exception that no longer matches their signatures. Distinguish between:

- **Unwrapping when delegating via reflection in a handler** so the technical `InvocationTargetException` wrapper does not leak.
- **Traversing the chain to log/diagnose** when needed.
- **Translating exceptions** at API boundaries according to the contract, preserving the cause instead of breaking the contract or losing information.

### 7.2. What If the Cause Is Null or an Unexpected Type?

Java allows constructing a UTE manually via the constructor taking a `Throwable`; the API notes that `getUndeclaredThrowable()` **can return `null`**. Therefore, in library code or when handling a UTE of unknown origin, check for `null` before calling `getClass()`.

Safe example:

~~~java
Throwable cause = ex.getUndeclaredThrowable();
if (cause == null) {
    System.err.println("Undeclared throwable unavailable");
} else {
    System.err.println("Original type: " + cause.getClass().getName());
}
~~~

This is an illustrative snippet where `ex` is a UTE. Do not cast blindly to `IOException` just because you saw `IOException` in logs once before.

## 8. Advanced Example: Two Interfaces with the Same Method but Different Throws Clauses

A less common but important case when writing dynamic proxies is **duplicate interface methods**: a proxy implements multiple interfaces that declare a method with the **same name and signature**, yet the interfaces declare **different checked exceptions**.

Example:

~~~java
interface FileAction {
    void execute() throws java.io.IOException;
}

interface DbAction {
    void execute() throws java.sql.SQLException;
}
~~~

The same proxy object can be invoked through `FileAction.execute()` or `DbAction.execute()`.

Any checked exception escaping the handler must be **compatible with the `throws` clauses of all interface methods with matching signatures** that can be called through the proxy. Because `IOException` and `SQLException` are two checked hierarchies **neither of which extends the other**, throwing `IOException` is **invalid for `DbAction.execute()`**. In this case, the proxy cannot let `IOException` escape directly, even if the caller casts the proxy to `FileAction`.

A very subtle pitfall: the `Method` object passed to the handler may come from **the interface that appears first in the proxy interfaces list**, so `method.getExceptionTypes()` **does not necessarily** represent the full checked exception constraints of **every interface sharing that method**.

### 8.1. Standalone Program Verifying Duplicate Methods

Save as **`DuplicateProxyThrowsDemo.java`**:

~~~java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.sql.SQLException;

public class DuplicateProxyThrowsDemo {
    interface FileAction { void execute() throws IOException; }
    interface DbAction { void execute() throws SQLException; }

    public static void main(String[] args) {
        Object proxy = Proxy.newProxyInstance(
                DuplicateProxyThrowsDemo.class.getClassLoader(),
                new Class<?>[] {FileAction.class, DbAction.class},
                (obj, method, arguments) -> {
                    System.out.println("handler-declaring="
                            + method.getDeclaringClass().getSimpleName());
                    throw new IOException("read failed");
                });

        try {
            ((FileAction) proxy).execute();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("file-call=" + ex.getClass().getSimpleName());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        } catch (IOException ex) {
            System.out.println("direct-io=" + ex.getMessage());
        }

        try {
            ((DbAction) proxy).execute();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("db-call=" + ex.getClass().getSimpleName());
        } catch (SQLException ex) {
            System.out.println("direct-sql=" + ex.getMessage());
        }
    }
}
~~~

Compile and run independently:

~~~bash
javac --release 17 -encoding UTF-8 DuplicateProxyThrowsDemo.java
java DuplicateProxyThrowsDemo
~~~

**Verified stdout:**

~~~text
handler-declaring=FileAction
file-call=UndeclaredThrowableException
cause=IOException
handler-declaring=FileAction
db-call=UndeclaredThrowableException
~~~

Key takeaways:

1. The proxy was declared with `FileAction` before `DbAction`, so the `Method` metadata in this example is identified as `FileAction`.
2. The handler throws `IOException`, but the corresponding method on `DbAction` does not declare `IOException`.
3. UTE appears both when the caller invokes through `FileAction` and when it invokes through `DbAction`.
4. Relying solely on `Method.getExceptionTypes()` of the `Method` passed to the handler is **not sufficient** to guarantee that a checked exception will pass through when duplicate methods exist across multiple interfaces.

According to the Java 17 `Proxy` Javadoc, duplicate methods must satisfy compatibility across all interface methods through which the proxy can be invoked. A simpler design can avoid this issue by separating the APIs or unifying the checked exception contract across interfaces.

## 9. When Does a Proxy Throw UTE and When Does It Not?

| Throwable escaping `InvocationHandler.invoke` | Interface method | Typical outcome |
| --- | --- | --- |
| `IOException` | `throws IOException` | Direct `IOException` |
| `FileNotFoundException` | `throws IOException` | Direct `FileNotFoundException` |
| `IOException` | No checked `throws` | UTE wrapping `IOException` |
| `SQLException` | `throws IOException` | UTE wrapping `SQLException` |
| `IllegalStateException` | No `throws` | Direct `IllegalStateException` |
| `NullPointerException` | `throws IOException` | Direct `NullPointerException` |
| `AssertionError` | No `throws` | Direct `AssertionError` |
| `InvocationTargetException` | `throws IOException` | UTE wrapping `InvocationTargetException` |
| `IOException` after unwrapping `InvocationTargetException` | `throws IOException` | Direct `IOException` |
| `IOException` with two duplicate-signature methods, one interface allowing only `SQLException` | Both interfaces must be satisfied | UTE wrapping `IOException` |

This table applies to **JDK dynamic proxies** created by `java.lang.reflect.Proxy`; do not apply it mechanically to all framework proxies or subclass-based proxies.

## 10. Compile-Time and Runtime Checked Exceptions Do Not Contradict Each Other

A common question: "If `String undeclared()` does not declare `IOException`, why does the handler compile when throwing `IOException`?"

You must distinguish **two places where the compiler checks**:

**At the handler implementation site:**

~~~java
InvocationHandler handler = (proxy, method, args) -> {
    throw new IOException("network failed");
};
~~~

This code is valid because `InvocationHandler.invoke` declares `throws Throwable`.

**At the interface method call site:**

~~~java
Service service = ...;
service.undeclared();
~~~

The caller sees that `Service.undeclared()` has no checked `IOException`. The compiler does not force handling `IOException` here. At runtime, the proxy receives the checked `IOException` from the handler and creates an unchecked UTE to propagate the failure while still respecting the method's checked `throws` limit.

There is no contradiction between compile time and runtime; **the proxy provides a runtime wrapping mechanism** for situations where the handler was allowed to throw more broadly than the interface signature.

### Why Can't You Write `catch (IOException)` Directly?

If a `try` block only contains a call to a method that does not declare checked `IOException` (and no other source of checked `IOException`), the statement:

~~~java
// INTENTIONALLY DOES NOT COMPILE IN THIS CONTEXT:
try {
    service.undeclared();
} catch (IOException ex) {
    System.out.println("Could not load");
}
~~~

is rejected by the compiler because `IOException` is never thrown according to compile-time analysis of the `try` block. The fact that the handler can throw `IOException` at runtime before the proxy converts it into UTE **does not change compile-time analysis at the caller**.

If a service exposes a contract that can fail with I/O errors that callers should handle explicitly, consider declaring `throws IOException` on the interface from the start, or use a custom contract runtime exception with `IOException` as its cause if the API policy avoids checked exceptions.

## 11. Fixing at the Right Layer

### 11.1. Update the Interface When Checked IOException Is Part of the Contract

If the public API permits I/O failures and callers need to know about this type:

~~~java
interface RemoteReader {
    byte[] read() throws IOException;
}
~~~

This is an illustrative interface requiring an `IOException` import. The handler can throw `IOException` or an appropriate subtype. Callers catch/declare `IOException` in the standard Java way. This is the cleanest option when **a checked exception is expected and meaningful to callers**.

Do not change the `throws` clause of a widely used public interface without evaluating source/binary compatibility and versioning policy; this is a contract change.

### 11.2. Use a Runtime Wrapper with Cause If the API Avoids Checked Throws

If the interface intentionally omits checked exceptions, instead of letting a raw `IOException` escape the handler and turn into a generic UTE, you can translate it to an appropriate unchecked exception:

~~~java
try {
    return readFromDisk();
} catch (IOException ex) {
    throw new java.io.UncheckedIOException("Cannot load data", ex);
}
~~~

This is illustrative code inside a handler or appropriate method, requiring `readFromDisk()` to be defined. `UncheckedIOException` is specifically designed to wrap `IOException` while preserving its cause. If the error belongs to a different domain, choose a custom runtime exception suited to the **caller contract** rather than defaulting to `UncheckedIOException` for every checked `Throwable`.

The advantage is that the caller receives an error **intentionally named for the domain**, rather than an unexpected technical UTE wrapper. Still, switching from checked to unchecked must follow API policy; it does not by itself solve error recovery or retries.

### 11.3. Unwrap InvocationTargetException in Reflective Handlers

If the handler delegates via `Method.invoke`, prefer:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
~~~

Pattern excerpted from the main program. Do not pass a raw `InvocationTargetException` to the proxy if the public interface only declares the original checked exception.

### 11.4. Handle Reflection Setup Errors Separately

Situations such as `IllegalAccessException`, access permission misconfiguration, wrong target, wrong arguments, or wrong method are framework/implementation problems. Categorize and report these technical failures clearly rather than wrapping them all in `IOException` to "bypass" the contract.

### 11.5. At the Caller: Log the Cause and Apply a Safe Fallback

If the caller does not own the interface or handler (for example, when using a third-party library), it can catch UTE **at the integration boundary** and inspect the cause to take a documented action.

Example:

~~~java
try {
    invokeThirdPartyService();
} catch (UndeclaredThrowableException ex) {
    Throwable cause = ex.getUndeclaredThrowable();
    logUnexpectedProxyFailure(ex, cause);
    throw ex; // Or translate to an explicit contract exception at the boundary.
}
~~~

This is an illustrative snippet requiring the corresponding methods and variables to be defined. Do not catch UTE and ignore it to continue as if the operation succeeded. If you decide to translate it to a domain exception, preserve the cause and context, and do not rely on the wrapper's message.

## 12. Proxies Apply Only to Interfaces, Not Subclass Proxies

A JDK dynamic proxy created via `java.lang.reflect.Proxy` implements **interfaces**. It does not turn an arbitrary class into a dynamic subclass through the same API.

In frameworks, multiple proxy mechanisms may exist:

- **JDK interface-based dynamic proxy:** uses `Proxy` and `InvocationHandler`, following the UTE rules covered here.
- **Subclass-based proxy or bytecode enhancement:** may use different mechanisms to generate/intercept methods; exception behavior depends on the framework and actual method contracts.
- **Remote proxy (RPC):** may translate failures from another process into domain/transport exceptions; does not necessarily use `java.lang.reflect.Proxy`.

If you encounter UTE in a framework-based application, check the stack trace and proxy configuration to confirm the proxy is actually a JDK proxy. **Do not conclude that every proxy wraps checked exceptions the same way** merely because the word "proxy" is used.

## 13. Special Methods: equals, hashCode, toString

A JDK proxy typically routes calls to public `Object` methods such as `equals`, `hashCode`, and `toString` to the `InvocationHandler` as well.

If the handler assumes every method is a business API (such as `load` or `save`), a logger or debugger calling `proxy.toString()` can trigger unexpected errors.

A simple strategy:

~~~java
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "toString" -> "ServiceProxy";
        case "hashCode" -> System.identityHashCode(proxy);
        case "equals" -> proxy == args[0];
        default -> throw new UnsupportedOperationException(method.getName());
    };
}
~~~

This is an **illustrative snippet inside a handler**, requiring `method`, `proxy`, and `args`, and real implementations must consider appropriate equality/hashCode semantics.

A dangerous design mistake is handling `Object` methods by calling `method.invoke(proxy, args)` directly inside the handler: a reflective call on the proxy itself can re-enter the handler, causing **infinite recursion**. Delegate to an appropriate target object or apply dedicated logic instead.

`equals`, `hashCode`, and `toString` declare no checked exceptions. Therefore, if a handler tries to throw a checked `IOException` from these calls, the UTE rule can also trigger. However, this is just one part of the broader picture of proxy contracts.

## 14. Methods Shared Across Interfaces and Object: Don't Rely Solely on Method Metadata

For `equals`, `hashCode`, and `toString`, JDK proxies have special rules regarding the `Method` passed to the invocation handler. For duplicate methods across multiple interfaces, `Method` metadata may be bound to the interface that appears earlier.

This leads to two recommendations:

1. **Do not treat `method.getDeclaringClass()` as the sole proof** of all `throws` contracts across the interfaces implemented by the proxy.
2. When a handler depends on method signatures, distinguish between `Object` methods, duplicate interface methods, and specialized interfaces. Pay special attention to cases with multiple incompatible `throws` clauses.

For complex proxies, inspect the proxy's interface list and design an **explicit mapping** for method/exception policies instead of calling `Method.getExceptionTypes()` and assuming it is sufficient.

## 15. Is UTE the Same as InvocationTargetException?

**No.** These two classes have different roles and appear at different layers.

| Characteristic | `UndeclaredThrowableException` | `InvocationTargetException` |
| --- | --- | --- |
| Package | `java.lang.reflect` | `java.lang.reflect` |
| Category | **Unchecked** (extends `RuntimeException`) | **Checked** (extends `ReflectiveOperationException`) |
| Typical cause | JDK proxy encounters an out-of-contract checked `Throwable` | `Method.invoke`/reflection reports an exception thrown by the target method |
| Retrieving wrapped `Throwable` | `getUndeclaredThrowable()`, `getCause()` | `getTargetException()`, `getCause()` |
| Must declare/catch when throwable? | Not required by compiler (unchecked) | Yes, unless handled in the handler/method |
| Common prevention | Keep checked `throws` contracts aligned or translate intentionally | Unwrap the target exception immediately when delegating via reflection |

The two classes **can be nested**: UTE wraps `InvocationTargetException` if the handler lets the checked reflection wrapper escape through an interface that does not declare that checked type.

## 16. How to Debug When a Stack Trace Shows UndeclaredThrowableException

Follow this sequence:

1. **Confirm the proxy source:** was the object created via `Proxy.newProxyInstance`? Use the stack trace and class/framework info; you can check `Proxy.isProxyClass(instance.getClass())` if appropriate.
2. **Identify the interface method the caller invoked**, especially its public `throws` clause.
3. **Inspect UTE's wrapped throwable:** `getUndeclaredThrowable()` or `getCause()`.
4. If the wrapped exception is `InvocationTargetException`, **inspect `getTargetException()`/`getCause()` next** to find the target's error.
5. Identify **which checked exception the handler actually threw out**, as distinct from the message or the deepest exception in the chain.
6. **Compare the actual checked type against the `throws` clause** of the interface method, including any duplicate methods if multiple interfaces are implemented.
7. **Check the delegation site:** if `Method.invoke` is used, did the handler catch `InvocationTargetException`?
8. **Check exception translation logic:** is it wrapping every exception into an undeclared checked type?
9. **Fix at the layer that owns the contract or handler** if you have access. Do not force every caller to handle UTE with ad-hoc casts.
10. **Log thoroughly**—both wrapper and cause—with sufficient context and without exposing sensitive data.

A typical chain to read:

~~~text
UndeclaredThrowableException
  Caused by: InvocationTargetException
    Caused by: IOException("disk offline")
~~~

This is a causal diagram, not verbatim output from every `printStackTrace()`; frame names, line numbers, and formatting vary by JVM.

## 17. Common Design Mistakes

1. **"Because `InvocationHandler.invoke` throws `Throwable`, the public interface allows throwing `Throwable` too."** False: they are two different contracts.
2. **"UTE is a checked exception."** False: UTE extends `RuntimeException`.
3. **"UTE loses the original exception."** False: it is usually accessible via `getUndeclaredThrowable()`/`getCause()`.
4. **"Every exception thrown by a handler is wrapped in UTE."** False: `RuntimeException` and `Error` pass through; compatible checked exceptions also pass through.
5. **"If the interface method has `throws IOException`, an `IOException` from the target via `Method.invoke` is guaranteed to pass straight through."** False if the handler lets `InvocationTargetException` escape.
6. **"`InvocationTargetException` is a subtype of `IOException`."** False: it is a separate checked reflection exception.
7. **"Simply changing the `catch` block at the caller fixes the proxy."** Not necessarily: fix the handler/contract when you own it.
8. **"Catching `IOException` around a method that does not declare checked `IOException` is always valid."** No: the compiler checks for checked exception sources inside the `try` block.
9. **"You can convert every checked exception into `IOException` just to satisfy `throws`."** Wrong if the failure semantics do not match.
10. **"Unwrapping every `Throwable` to the deepest layer and rethrowing is always good."** False: it can break API boundary contracts and lose context.
11. **"`getUndeclaredThrowable()` is always non-null."** Not guaranteed for manually constructed UTEs.
12. **"If the wrapped exception is `IOException`, the cause must be a file error."** No: `IOException` is used for many I/O operations; inspect the context.
13. **"If a proxy has two interfaces with the same method, the allowed checked `throws` is the union of declared types."** False: it must be compatible with all relevant method contracts.
14. **"`Method.getExceptionTypes()` on the `Method` passed to the handler always captures all constraints."** False in the case of duplicate methods.
15. **"Calling `method.invoke(proxy, args)` inside the handler is a safe delegation pattern."** It can cause the proxy to re-enter the handler and recurse.
16. **"`equals`/`hashCode`/`toString` have nothing to do with the handler."** False for JDK dynamic proxies.
17. **"All AOP libraries use JDK `Proxy`."** False: multiple proxy mechanisms exist.
18. **"Creating a runtime wrapper automatically handles retries/transactions."** False: a wrapper only changes how errors are represented/propagated, not recovery logic.
19. **"Logging only `UTE.getMessage()` is enough."** Usually not: you need the cause and stack trace.
20. **"Adding `throws` to the proxy implementation solves every case."** For JDK-generated proxies, the public interface contract and duplicate methods are what matter.

## 18. Self-Check Exercises

**Q1.** An interface has `void run();`, and the handler throws `IOException`. What type will the caller typically receive?

*Answer:* `UndeclaredThrowableException` wrapping `IOException`, because checked `IOException` is not declared by the interface method.

**Q2.** Change the interface to `void run() throws IOException;` while the handler still throws `IOException`. What is the result?

*Answer:* `IOException` can propagate directly without UTE.

**Q3.** The handler throws `IllegalArgumentException` even though the interface method has no `throws` clause. How does the proxy handle it?

*Answer:* It is an unchecked `RuntimeException`, so it propagates directly.

**Q4.** The handler throws `AssertionError`. Does the proxy create a UTE?

*Answer:* No; `Error` is unchecked, so it propagates directly.

**Q5.** The interface declares `throws IOException`, but the handler executes `method.invoke(target, args)` without catching `InvocationTargetException`. The target throws `IOException`. What might the caller receive?

*Answer:* UTE wrapping `InvocationTargetException`, which in turn wraps the target's `IOException`.

**Q6.** How do you fix the handler so the original `IOException` propagates according to the contract?

*Answer:* Catch `InvocationTargetException` and `throw ex.getCause()`. If the cause is an `IOException` compatible with `throws`, the proxy propagates it directly.

**Q7.** Which two getters on UTE let you inspect the wrapped exception?

*Answer:* `getUndeclaredThrowable()` and `getCause()`.

**Q8.** If the wrapped exception is `InvocationTargetException`, which APIs should you check next?

*Answer:* `getTargetException()` or `getCause()` to see the `Throwable` actually thrown by the target.

**Q9.** Why can a handler be written with `throw new SQLException(...)` even when the interface does not declare `SQLException`?

*Answer:* Because `InvocationHandler.invoke()` declares `throws Throwable`, yet the proxy still enforces the interface contract at runtime and may wrap it in UTE.

**Q10.** Two interfaces share the method `execute()`; one declares `IOException` and the other declares `SQLException`. The handler throws `IOException`. Can it propagate directly through every caller?

*Answer:* No. Because `IOException` is incompatible with the other interface's `throws` clause, the proxy can produce UTE; the Java 17 example above produces UTE for both call paths.

**Q11.** Should UTE be used as a custom business exception across all APIs?

*Answer:* No. It is primarily a wrapper indicating a mismatch at a JDK dynamic proxy. If an API needs clear business error handling, a dedicated exception contract is more meaningful.

**Q12.** Is it safe to catch UTE, print the message, and return success?

*Answer:* No. The underlying failure still occurred; ignoring it can cause the program to return bogus results and mask bugs.

**Q13.** What is the risk of calling `Method.invoke(proxy, args)` directly on the proxy inside the handler?

*Answer:* It can re-enter the same handler and cause uncontrolled recursion.

**Q14.** Why doesn't `method.getDeclaringClass()` always reflect the complete checked exception contract when a proxy implements multiple interfaces?

*Answer:* For duplicate-signature methods, the handler may receive a `Method` from one chosen interface, while the `throws` rules remain constrained by all interfaces declaring the matching method.

## 19. InvocationHandler Design Checklist

Before shipping a JDK dynamic proxy to production:

- **Interface contract:** are checked exceptions declared appropriately for caller needs?
- **Handler throwing policy:** which checked `Throwable` types can escape the handler?
- **Reflection delegation:** is `InvocationTargetException` unwrapped when invoking the target via `Method.invoke`?
- **Cause preservation:** is the original error preserved when translating to a runtime/domain exception?
- **Multiple interfaces:** are there duplicate methods with different `throws` clauses?
- **Object methods:** is there a sensible policy for `equals`, `hashCode`, and `toString`?
- **Return values:** is the `Object` returned by the handler compatible with the method's return type, including primitives?
- **Access/arguments:** are reflection configuration errors separated from business errors thrown by the target?
- **Logging:** is the full chain UTE → `InvocationTargetException` → root error logged with context and without sensitive data?
- **Tests:** have you tested declared checked, undeclared checked, unchecked, `Error`, reflection wrappers, and duplicate interfaces where applicable?
- **Caller policy:** is any caller catching/swallowing UTE and reporting false success?
- **Ownership:** should you fix the interface/handler contract, or do you need a boundary adapter because an external library cannot be modified?
- **Maintenance:** if upgrading Java or changing proxy/framework mechanisms, have exception contracts been re-tested?

## 20. Official Java 17 Documentation

- [Java SE 17 API – UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): conditions under which a proxy creates the wrapper, getters, and cause behavior.
- [Java SE 17 API – InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `invoke(Object,Method,Object[]) throws Throwable` and unchecked/checked rules.
- [Java SE 17 API – Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): interface proxy creation, duplicate methods, checked exception constraints.
- [Java SE 17 API – InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): checked reflection wrapper and retrieving the target exception.
- [Java SE 17 API – Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `Method.invoke` and exceptions thrown.
- [Java SE 17 API – RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): the unchecked branch in the `Throwable` hierarchy.
- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, message, stack trace, suppressed exceptions.
- [JLS Java SE 17 – Chapter 11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked exceptions and compiler analysis.
- [JLS Java SE 17 – Section 8.4.8.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked `throws` restrictions during normal method overriding.

**Conclusion:** `UndeclaredThrowableException` occurs in a JDK dynamic proxy when `InvocationHandler.invoke` lets a **checked exception escape that is incompatible with the interface method's `throws` clause**. `RuntimeException` and `Error` are not wrapped by this mechanism; validly declared checked exceptions also propagate directly. When delegating via reflection, **unwrap `InvocationTargetException`** to preserve the original exception and the caller contract, especially when the target throws an `IOException` permitted by the interface. Always inspect the cause, account for duplicate interface methods, and never use catching UTE as a substitute for proper API contract design.