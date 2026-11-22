# Compatibility Impact When Changing Exception Contracts in Java

> **Scope:** Java Core → Exception → API Design. This article focuses on the consequences for calling code, implementation classes, old compiled binaries, and runtime behavior when an API changes the exceptions it can throw.

## 1. What Is an Exception Contract?

An *exception contract* describes the failure scenarios that API users need to anticipate, how to detect them, and how to recover or propagate errors to a higher layer. The contract is expressed through multiple sources:

- **`throws` declaration:** indicates the *checked exceptions* that the compiler forces the caller to handle or declare further. This declaration represents a possibility, not a guarantee that the exception will always be thrown.
- **Actual exception type:** the exception class and its inheritance hierarchy determine whether a `catch` block can intercept the error.
- **API documentation:** `@throws`, error conditions, recoverability, and the meaning of parameters or state when an operation fails.
- **Observable behavior:** when the exception is thrown, preservation of `cause`, resource or transaction state after failure, retry/cancel mechanisms, and signals for logging/monitoring.

For example, a configuration-reading method might promise to throw `IOException` when data access fails. Clients are entitled to write `catch (IOException e)` to perform a fallback. If a new version changes that error to `IllegalStateException`, the method signature might still compile, but the old fallback will no longer work. Therefore, compatibility evaluation must examine both the published contract and the actual behavior.

### Checked vs. Unchecked Exceptions

- **Checked:** subclasses of `Throwable` that are not under the `RuntimeException` or `Error` branch; for example, `IOException`, `SQLException`. They are checked at compile time according to Java rules.
- **Unchecked:** `RuntimeException`, `Error`, and their subclasses; for example, `IllegalArgumentException`, `IllegalStateException`. The compiler does not require `catch` or `throws`, but callers can still catch them.
- **Do not use `Error` as a business exception.** It typically indicates a serious runtime/system-level failure, not a routine error-handling path for an application API.

A good contract clearly states **the conditions under which an exception is thrown and the handling options**, rather than merely listing exception class names. Overly broad `throws Exception` or `throws Throwable` declarations make it difficult for callers to decide what to handle.

## 2. Three Compatibility Axes to Evaluate Separately

| Compatibility Type | Question to Answer | Example |
|---|---|---|
| **Source** | Will recompiling client code or implementation classes against the new API succeed? | Adding `throws IOException` causes an old call site to lack a `catch`. |
| **Binary** | Can previously compiled `.class` files link and run with the new library? | Changing only the `throws` clause does not alter the JVM method descriptor. |
| **Behavioral** | Do error-handling flows, retries, fallbacks, logging, and system responses retain their intended meaning? | An old exception is wrapped into a runtime exception without preserving `cause`. |

**Common misconception:** according to the Java Language Specification (JLS §13.4.21), changing only the `throws` clause of a method or constructor **does not break binary compatibility**; checked exception checking occurs at compile time. That does **not** mean the change is safe for source code or behavior. If you also change the method name, parameters, return type, accessibility, exception class, or execution logic, those changes must be evaluated independently.

## 3. Impact Matrix of Common Changes

| Change in Public API | When Recompiling Callers/Implementations | With Old Binaries if **Only `throws` Changes** | Behavioral Risk |
|---|---|---|---|
| **Add checked exception** `throws IOException` | Callers must catch/declare; related method references or lambdas may become invalid | Remains binary compatible | New error path may go unhandled |
| **Remove checked exception** from `throws` | Specialized `catch` blocks may become invalid; overriding classes declaring the old exception may fail | Remains binary compatible | Clients do not know what the error was changed to |
| **Widen from checked subtype to supertype** (e.g., `FileNotFoundException` → `IOException`) | Broadens the scope of errors to handle; callers catching the narrower type may miss handling | Remains binary compatible | Callers cannot distinguish certain cases |
| **Narrow from checked supertype to subtype** | Some overriding classes declaring the broader type will fail to recompile; callers with matching `catch` blocks usually remain valid | Remains binary compatible | May alter the meaning of the error commitment |
| **Add/switch to unchecked exception** | Usually requires no new declaration, but old checked `catch` source code may fail if the checked exception was removed | If only `throws` is modified, still links; throwing logic is a separate concern | Fallbacks, retries, error metrics, and transaction control may change |
| **Keep exception type but change throwing condition** | May still compile | May still link | Breaks semantic contract without changing the signature at all |
| **Change `cause`, error code, or wrapper type** | Usually not warned by the compiler | Usually does not cause linkage errors if public structure is unchanged | Debugging, error classification, and retry policies may become incorrect |

The table above is not a guarantee that every change is binary safe: the binary column's scope is strictly **changes solely to `throws`**. Removing a public exception class, changing the class hierarchy, removing a method, or changing a descriptor can cause compile-time, linkage, or runtime errors.

## 4. Adding a Checked Exception: Errors Surface at Call Sites

Suppose version 1 publishes:

~~~java
// API declaration snippet for version 1, not a standalone program.
public String fetch(String key);
~~~

Version 2 changes to:

~~~java
// API declaration snippet for version 2.
public String fetch(String key) throws java.io.IOException;
~~~

Client code previously wrote:

~~~java
String value = service.fetch("theme");
System.out.println(value);
~~~

When recompiling against API version 2, the compiler detects an unhandled checked exception. The caller must wrap the statements in a `try/catch` or add `throws IOException` to the enclosing method; if it is a constructor, the `throws` clause of that constructor must also be considered. Merely "adding a declaration to get it to compile" can keep pushing the error up to layers that are not ready to handle it.

The impact also extends to lambda expressions and method references:

~~~java
// Illustration: Supplier.get() does not declare any checked exceptions.
java.util.function.Supplier<String> supplier = () -> service.fetch("theme");
~~~

The expression above might be valid in version 1, but it is no longer valid if `fetch` in version 2 throws `IOException`. A custom functional interface with `run() throws IOException` can express the contract more appropriately, or the API may need to provide a deliberate error-translation branch.

## 5. Removing or Narrowing a Checked Exception Can Also Break Source Code

Version 1:

~~~java
// API snippet, not a standalone program.
public String read() throws java.io.IOException;
~~~

Caller:

~~~java
// Caller-side code snippet.
try {
    return api.read();
} catch (java.io.IOException ex) {
    return "default";
}
~~~

If version 2 changes to `public String read()` and the `try` body has no other statement that can throw `IOException`, `catch (IOException)` will trigger a compile error because this checked exception cannot be thrown from the `try` block according to static analysis. This is a classic example of a change that appears to "relax constraints" yet breaks client source code.

Beyond callers, there is the **inheritance hierarchy**. The overriding rule: an overriding method must not declare checked exceptions broader than those permitted by the overridden method. For example:

~~~java
// These snippets represent the old API and a currently valid implementation class.
interface Loader {
    String load() throws java.io.IOException;
}

class DiskLoader implements Loader {
    @Override
    public String load() throws java.io.IOException {
        throw new java.io.IOException("unavailable");
    }
}
~~~

If in a later version `Loader.load()` drops `throws IOException` or narrows it to only `FileNotFoundException`, then `DiskLoader.load()` above **will fail to recompile** if it still declares `IOException`. Conversely, adding an allowed checked exception to an interface declaration does not force existing implementations to throw it, but **callers** through the interface will still need to update.

The same rules apply to abstract classes, overriding methods, and functional interfaces. For constructors, changing `throws` directly affects `new` expressions and constructors calling `super(...)`.

## 6. Changing the Exception Class or Converting Checked to Unchecked

For example, a data access API previously declared `SQLException`, and later switched to `DataAccessException extends RuntimeException`. The new signature may be more concise, but a caller that previously wrote `catch (SQLException)` will not automatically catch `DataAccessException`. Upon recompilation, the old checked `catch` may no longer be valid; for already-compiled callers, the new exception may pass straight through old handlers.

To decide on the conversion, you need to answer:

1. Does the caller have a **specific recovery path** from the original checked exception (retry, switch to a fallback source, prompt the user to fix input)?
2. Do error-interception points rely on the **specific type** or inheritance hierarchy of the exception?
3. When wrapping the exception, is `cause` still accessible for troubleshooting and message classification?
4. Does the error occur **before or after** side effects (writing files, mutating state, committing transactions)? Can the caller safely retry?
5. What behavior has the API published in its Javadoc and versioning documentation?

If you choose an unchecked exception because callers cannot reasonably handle it at the call site, use a sufficiently descriptive type, such as `UncheckedIOException` for translated I/O errors, or a business-domain exception carrying a `cause`. Avoid converting all errors into a generic `RuntimeException`, as callers will lose the ability to branch based on the root cause.

### Runnable Java 17+ Program: Translating Errors While Preserving the Cause

The example below illustrates **an API publicly designed to return unchecked errors**. If migrating from an already-released checked API, a compatibility path from Section 8 is still required; simply applying a wrapper does not automatically guarantee compatibility.

Save the entire code into `ExceptionContractDemo.java`:

~~~java
import java.io.IOException;

public class ExceptionContractDemo {
    static final class ConfigurationException extends RuntimeException {
        ConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String loadRaw(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("storage unavailable");
        }
        return "mode=prod";
    }

    static String load(boolean fail) {
        try {
            return loadRaw(fail);
        } catch (IOException cause) {
            throw new ConfigurationException("cannot load config", cause);
        }
    }

    public static void main(String[] args) {
        System.out.println(load(false));

        try {
            load(true);
        } catch (ConfigurationException ex) {
            System.out.println(ex.getClass().getSimpleName());
            System.out.println(ex.getCause().getClass().getSimpleName());
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac ExceptionContractDemo.java
java ExceptionContractDemo
~~~

Exact standard output:

~~~text
mode=prod
ConfigurationException
IOException
cannot load config
~~~

Here `loadRaw` has a checked `IOException` contract, while `load` exposes an unchecked `ConfigurationException` contract. The `super(message, cause)` constructor preserves the cause chain. Caller-side handlers of `load` must catch `ConfigurationException` specifically; it cannot mechanically replace the handler of an old checked API.

## 7. Behavioral Commitments That Are Easily Overlooked

### 7.1. Catch Scope and `catch` Ordering

`catch (IOException)` catches `IOException` and its subclasses, but does not catch an unrelated `RuntimeException`. When changing exceptions, fallback branches may stop executing. With multiple `catch` blocks, specific types must precede broader types to avoid unreachable branches; re-verify `multi-catch` declarations when changing the exception hierarchy.

### 7.2. Root Cause and Diagnostic Data

Preserve `cause` when translating exceptions; avoid catching and throwing a new exception with only a message that loses the original stack trace. Exception messages are typically for diagnostics and should not become a stable machine-readable format unless the API explicitly commits to it. If callers need durable classification, use **exception types**, public error codes, or strongly typed properties.

### 7.3. Thread Interruption and Task Cancellation

`InterruptedException` is a control signal for waiting/task cancellation. If an API catches it and converts it to an unchecked exception, consider restoring the interrupt status so outer layers can observe it:

~~~java
// Illustrative snippet inside a method catching InterruptedException.
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("operation interrupted", ex);
}
~~~

If the API can declare `throws InterruptedException`, propagating the exception usually lets the caller decide on task cancellation more accurately. Do not swallow the interrupt signal and continue processing as if nothing happened.

### 7.4. Resource Closing and Suppressed Exceptions

With `try-with-resources`, an exception thrown in the `try` block body is typically the primary error; exceptions from `close()` may be recorded in `Throwable.getSuppressed()`. Error translation should not discard this information. Changing the `throws` declaration of `AutoCloseable.close()` or changing the resource type can introduce checked exception handling requirements at usage sites.

### 7.5. Asynchronous Code, Reflection, and Frameworks

In `CompletableFuture`, failures may be propagated via exceptional completion; `join()` typically throws `CompletionException`, whereas `get()` uses `ExecutionException` to wrap the cause. Switching a synchronous operation to asynchronous therefore changes the entire **channel** for receiving errors, not just the exception name.

Reflection and some frameworks inspect the declared exception list via `Method.getExceptionTypes()`; reflective invocation may wrap errors in `InvocationTargetException`. Proxies, interceptors, logging, HTTP mappers, retry configurations, and transactions may also branch based on exception type. A change that is not rejected by the JVM can still cause integration layers to behave differently than before.

## 8. API Evolution Strategies to Reduce Client Breakage Risk

### Approach 1: Keep the Old API and Add a New Entry Point

When you want to provide an unchecked variant, a clear strategy is to **keep the old method intact** (name, parameters, return type, and error contract) while adding a new method with a different name. For example, if a library class already has `read(Path)`:

~~~java
// Snippet in a library class, with imports java.io.*,
// java.nio.file.Files, and java.nio.file.Path.
public byte[] read(Path path) throws IOException {
    return Files.readAllBytes(path);
}

public byte[] readUnchecked(Path path) {
    try {
        return read(path);
    } catch (IOException ex) {
        throw new UncheckedIOException("cannot read " + path, ex);
    }
}
~~~

Existing callers continue calling `read` and handling `IOException`; new callers can explicitly opt into `readUnchecked`. Both paths should be tested to ensure the same underlying failure is not unintentionally interpreted differently.

### Approach 2: Extend Using a Meaningful Subtype

If an API declares `throws IOException`, having the implementation throw a **subtype of `IOException`** can still pass through existing `IOException` catch handlers. This is usually less disruptive than throwing an unrelated checked exception. However, callers catching specific subtypes, monitoring concrete error types, or applying retry policies may still be affected; document the new conditions.

### Approach 3: Deprecation Roadmap and Versioning

If changing the old contract is unavoidable, publish the error conditions, migration path, `catch` replacement examples, deprecation timeline, and target version in advance. For major changes where source breakage is hard to avoid, consider releasing a new API version with a separate name or package, or bumping the major version according to the library's compatibility policy. Do not treat marking `@Deprecated` as having solved the problem: the annotation only notifies users and does not by itself ensure both behaviors remain correct.

### What Not to Use as a "Quick Fix"

- Adding `throws Exception` across application layers: code may compile, but the contract becomes much harder to control.
- Converting all checked exceptions to `RuntimeException` and assuming there is no breaking change.
- Catching `Exception` or `Throwable` everywhere to mask incompatibilities.
- Catching an exception and returning `null` or `Optional.empty()` without distinguishing **no data** from **operation failed**, unless the API explicitly commits to that.
- Dropping `cause`, dropping `suppressed` exceptions, or swallowing `InterruptedException` when building a wrapper.
- Relying on the contents of `getMessage()` as a stable protocol when the message is intended only for humans.

## 9. Pre-Release Compatibility Verification Process

1. **List old and new contracts:** every public method/constructor, checked exceptions in `throws`, documented runtime exceptions, error conditions, published exception classes, and subtypes.
2. **Cross-reference usages:** direct call sites, specialized `catch` blocks, method references, lambdas, constructor chaining, `extends` or `implements` classes, transaction handling, and retries.
3. **Recompile client code:** specifically check cases of adding checked exceptions, removing checked exceptions that have dedicated `catch` blocks, and narrowing contracts of overridden methods.
4. **Test old binaries against the new library:** use caller artifacts compiled before the change. Distinguish JVM linkage errors from behavioral errors when the actual exception changes; you can inspect method descriptors with `javap -s` and exception declaration metadata with `javap -v`.
5. **Test failure behavior:** verify exact exception class/`cause`, closed resources, interrupt flag, side effects, fallbacks, retries, logs, and public-facing responses. Include multiple exceptions that are close in the hierarchy.
6. **Publish migration notes:** state the changed conditions, impact scope, how to update handlers, and the removal schedule for the old API. Only certify compatibility along the axes that were actually tested.

### Quick Decision Table

| Scenario | Preferred Approach |
|---|---|
| Need to add a checked error cause to a released API | Consider keeping the old contract and providing a new API, or using a subtype compatible with the published type; evaluate callers before adding `throws`. |
| Want to simplify callers with an unchecked exception | Keep the old checked API and add a new method with a clear name, semantics, and `cause`. |
| Want to remove an exception that is no longer thrown | Check old checked `catch` blocks and overriding classes; document replacement behavior and avoid direct removal if it causes compile errors for clients. |
| Want to narrow `throws` on an interface | Check all existing implementations and their ability to recompile. |
| Changing only error message text | Confirm no system relies on that text as a machine-readable code; prefer stable error codes. |
| Code still links but fallback does not run | Inspect the actual exception type, wrappers, and `cause`; do not conclude safety solely from build results. |

## 10. Takeaways

- **`throws` belongs to the compile-time contract of checked exceptions; actual exception types and handling rules form the behavioral contract.**
- **Binary compatibility does not equal source or behavioral compatibility.** Changing only the `throws` clause is guaranteed by the JLS not to break binary linkage, but recompiling clients can still fail.
- **Removing a checked exception can also be a breaking change** due to existing `catch` blocks and method overrides.
- When evolving a widely used API, keeping the old path working and publishing a clear new path is usually easier to control than abruptly changing exception types.
- Final evaluation must include **recompilation**, **running old binaries**, and **testing failure behavior**.

### Standard References

- [JLS §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2)
- [JLS §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3)
- [JLS §13.4.21 — Method and Constructor Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.21)
