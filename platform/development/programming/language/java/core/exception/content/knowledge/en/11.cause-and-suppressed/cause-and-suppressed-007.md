# Limits on Self-Cause, Self-Suppression, and `null` Values in Java

A `Throwable` object has two error-linking mechanisms that need to be distinguished: **cause** — the direct cause of an exception — and **suppressed exceptions** — secondary exceptions retained while another exception is being propagated outward. Both help preserve diagnostic context, but Java enforces different rules regarding references to **the object itself** and how `null` values are handled.

The four most important rules:

- **Self-cause is forbidden:** `ex.initCause(ex)` throws `IllegalArgumentException`. An exception cannot be designated as its own direct cause through this API.
- **Self-suppression is forbidden:** `ex.addSuppressed(ex)` also throws `IllegalArgumentException`. An exception cannot suppress itself.
- **`null` can be a cause:** `initCause(null)` or a constructor accepting a `null` cause is valid. However, `initCause(null)` still **consumes the single-use cause initialization allowance**.
- **`null` cannot be a suppressed exception:** `ex.addSuppressed(null)` throws `NullPointerException`. If there are no secondary errors, **do not call `addSuppressed`**, rather than passing `null`.

A common pitfall is checking `getCause() == null` and assuming the cause has never been initialized. A return value of `null` only means unknown or no cause; it **does not reflect** whether the right to call `initCause` has already been used.

This article explains the Java SE 21 contract of `Throwable.initCause()`, `addSuppressed()`, `getCause()`, `getSuppressed()`, the special case when suppression is disabled, implications in `try-with-resources`, and design patterns to avoid losing error information. The examples run on JDK **17 or later**.

## 1. Distinguishing cause and suppressed exceptions before examining limits

An exception can contain both a cause and multiple suppressed exceptions:

```text
DataLoadException("cannot load")
  |
  +-- getCause() --> IOException("read failed")
  |                     |
  |                     +-- getSuppressed()[0]
  |                           --> IOException("close failed")
  |
  +-- getSuppressed()[0]
        --> RuntimeException("secondary cleanup")
```

The diagram above is a **relational model**, not Java syntax. It shows that both relationships can exist on different objects within the same error graph.

| Criterion | Cause | Suppressed |
| --- | --- | --- |
| Purpose | Explains why the current exception occurred | Retains secondary exceptions that were ignored so another error could propagate |
| Setter API | Constructor taking `Throwable cause` or `initCause(cause)` | `addSuppressed(exception)` |
| Getter API | `getCause()` | `getSuppressed()` |
| Cardinality via standard API | At most one cause reference per `Throwable` | Multi-element list, in the order added |
| Value when absent | `null` | Empty `Throwable[]` array |
| Passing `null` when setting | Accepted in appropriate constructors and `initCause(null)` | Invalid: `NullPointerException` |
| Pointing to itself | `initCause(this)` is rejected | `addSuppressed(this)` is rejected |
| Common mechanism | Wrapping errors across business layers | `try-with-resources` when closing a resource also throws an error |

**There is no automatic one-to-one relationship between cause and suppressed.** A suppressed exception does not automatically become a cause; a cause does not automatically appear in `getSuppressed()`.

## 2. Self-cause: `initCause(this)` is rejected

`Throwable.initCause(Throwable cause)` is used to attach a cause after the object has been created, typically to support legacy exception classes that lack a cause-accepting constructor.

Signature:

```java
public synchronized Throwable initCause(Throwable cause)
```

According to the Java 21 Javadoc, if the argument is the `Throwable` object being updated itself, the method throws **`IllegalArgumentException`**. Consequently:

```java
Exception failure = new Exception("failure");
failure.initCause(failure); // Invalid: cannot be its own cause.
```

This is a **deliberate runtime exception**, not a compile-time error. Linking an exception to itself as a cause is meaningless in terms of causality and risks creating an invalid diagnostic graph.

An important comparison:

```java
Exception a = new Exception("same");
Exception b = new Exception("same");

a.initCause(b); // Valid: a and b are TWO different objects.
```

Two objects may have the same type, the same message, and even similar stack traces; what Java forbids is passing **the reference to `a` itself** as the cause of `a`. The check is based on **object identity**, not whether two exceptions have identical content.

### Runnable example: self-cause is rejected

Save as `SelfCauseDemo.java`:

```java
public class SelfCauseDemo {
    public static void main(String[] args) {
        Exception failure = new Exception("failure");

        try {
            failure.initCause(failure);
        } catch (IllegalArgumentException ex) {
            System.out.println("self=" + ex.getClass().getSimpleName());
        }

        System.out.println("causeAfterRejected=" + failure.getCause());

        Exception original = new Exception("original");
        failure.initCause(original);
        System.out.println("linked=" + (failure.getCause() == original));

        try {
            failure.initCause(new Exception("replacement"));
        } catch (IllegalStateException ex) {
            System.out.println("secondInit="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SelfCauseDemo.java
java SelfCauseDemo
```

Output:

```text
self=IllegalArgumentException
causeAfterRejected=null
linked=true
secondInit=IllegalStateException
```

Analysis:

1. Calling `initCause(failure)` is rejected due to self-cause.
2. The object can still have a valid cause attached afterward, because the rejected call did not successfully set a cause.
3. Attaching `original` succeeds, so the identity comparison `==` returns `true`.
4. The subsequent call to `initCause` is rejected because the cause has already been initialized.

You should not handle self-cause by silently ignoring it and returning an error without a cause if that incident reflects a flawed exception-chaining design. Identify the original exception and the wrapper exception properly.

## 3. Cause initialization is allowed **once**, even when set to `null`

This detail is more important than what `getCause()` returns.

When creating an object using a constructor **that does not take a cause**, such as `new Exception("message")`, the initial cause state is **uninitialized**. You may call `initCause(...)` **once**.

After calling:

```java
Exception failure = new Exception("failure");
failure.initCause(null); // Valid and consumes the single initialization.
```

`getCause()` still returns `null`. However, another `initCause(...)` call will throw **`IllegalStateException`**, even though `null` was passed the first time.

With a constructor **that takes a cause parameter**, such as `new Exception("message", null)`, the cause is considered **already initialized**, even though its value is `null`. Therefore, `initCause(...)` cannot be called after that constructor either.

| Creation / Operation | `getCause()` | Can `initCause(...)` be called afterward? |
| --- | --- | --- |
| `new Exception("x")` | `null` | **Yes**, if `initCause` has never been called |
| `new Exception("x").initCause(null)` | `null` | **No**, already initialized once |
| `new Exception("x", null)` | `null` | **No**, cause was already specified in the constructor |
| `new Exception("x", original)` | `original` | **No**, already initialized in the constructor |
| `new Exception("x").initCause(original)` | `original` | **No**, the single initialization has been used |

The constructors `Throwable(Throwable cause)` and `Throwable(String message, Throwable cause)` carry the same restriction documented in the Javadoc; subclasses may provide corresponding constructors.

### Java 17+ example: `null` still counts as an initialization

Save as `NullCauseDemo.java`:

```java
public class NullCauseDemo {
    public static void main(String[] args) {
        Exception deferred = new Exception("deferred");

        System.out.println("initial=" + deferred.getCause());
        deferred.initCause(null);
        System.out.println("afterNull=" + deferred.getCause());

        try {
            deferred.initCause(new Exception("late"));
        } catch (IllegalStateException ex) {
            System.out.println("repeat="
                    + ex.getClass().getSimpleName());
        }

        Exception fromConstructor = new Exception("ctor", null);
        System.out.println("ctorCause=" + fromConstructor.getCause());

        try {
            fromConstructor.initCause(new Exception("late"));
        } catch (IllegalStateException ex) {
            System.out.println("ctorAlreadyInitialized="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 NullCauseDemo.java
java NullCauseDemo
```

Output:

```text
initial=null
afterNull=null
repeat=IllegalStateException
ctorCause=null
ctorAlreadyInitialized=IllegalStateException
```

The takeaway here: **`getCause() == null` is not enough to infer that `initCause(...)` can be called**. There is no standard public API to ask "has `initCause` been called yet?"; choose a consistent design, preferring a cause-accepting constructor when creating a new wrapper exception.

Some exception classes may override `getCause()` for compatibility with legacy chaining mechanisms. When using a specialized class, read its contract rather than inferring all internal state from the return value.

## 4. Self-suppression: `addSuppressed(this)` is rejected

Signature:

```java
public final synchronized void addSuppressed(Throwable exception)
```

`addSuppressed` records a secondary error in the list of a primary error. The secondary object **must be a `Throwable` reference different from the primary object itself**.

Invalid example:

```java
Exception failure = new Exception("work");
failure.addSuppressed(failure); // IllegalArgumentException
```

This code compiles cleanly, but throws an error at runtime. The underlying issue is **self-suppression**: an exception acting as both the primary error and its own secondary error.

Two exceptions with the **same message but different object identities** do not constitute self-suppression:

```java
Exception primary = new Exception("same text");
Exception extra = new Exception("same text");

primary.addSuppressed(extra); // Valid.
```

Distinction is determined by object identity. `addSuppressed` **does not replace** the primary exception, does not turn `extra` into the cause, and does not automatically rethrow `extra`. It only appends a secondary error link.

### Java 17+ example: distinguishing self from another object

Save as `SelfSuppressionDemo.java`:

```java
public class SelfSuppressionDemo {
    public static void main(String[] args) {
        Exception failure = new Exception("failure");

        try {
            failure.addSuppressed(failure);
        } catch (IllegalArgumentException ex) {
            System.out.println("self="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("afterSelf="
                + failure.getSuppressed().length);

        Exception secondary = new Exception("failure");
        failure.addSuppressed(secondary);

        System.out.println("count=" + failure.getSuppressed().length);
        System.out.println("sameObject="
                + (failure.getSuppressed()[0] == failure));
        System.out.println("secondaryMessage="
                + failure.getSuppressed()[0].getMessage());
    }
}
```

```bash
javac -encoding UTF-8 SelfSuppressionDemo.java
java SelfSuppressionDemo
```

Output:

```text
self=IllegalArgumentException
afterSelf=0
count=1
sameObject=false
secondaryMessage=failure
```

Looking at `sameObject=false`, we can see that the secondary error **is not the primary object**, even though both objects share the same message. The rejected self-suppression attempt did not add a new element to the list.

## 5. `null` values: distinguishing three APIs precisely

Three operations have similar-looking signatures but different contracts:

| Expression | Result |
| --- | --- |
| `ex.initCause(null)` | **Valid** if the cause has never been initialized; consumes the initialization allowance |
| `new Exception("message", null)` | **Valid**; cause is considered initialized to `null` |
| `ex.addSuppressed(null)` | **`NullPointerException`** |
| `ex.getCause()` when there is no / unknown cause | Returns `null` |
| `ex.getSuppressed()` when there are no suppressed exceptions | Returns an **empty** array, not `null` |
| `throw null;` | Syntactically valid, but throws **`NullPointerException`** at runtime |
| `ex.setStackTrace(null)` | **`NullPointerException`**, belonging to a different stack trace API |

The reason is that each API serves a distinct purpose:

- **Cause `null`:** indicates there is no cause information. Standalone exceptions exist that do not need a cause.
- **Suppressed `null`:** does not describe any exception object. The suppressed list only accepts actual `Throwable` objects.
- **`throw null`:** the `throw` statement requires an exception reference; the JVM creates/throws `NullPointerException` when the expression evaluates to `null`.

Do not use `null` as a placeholder or sentinel in the suppressed list. If there are no secondary errors, leave the list empty.

### Java 17+ example: handling `addSuppressed(null)`

Save as `SuppressedNullDemo.java`:

```java
public class SuppressedNullDemo {
    public static void main(String[] args) {
        Exception primary = new Exception("main");

        try {
            primary.addSuppressed(null);
        } catch (NullPointerException ex) {
            System.out.println("nullRejected="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("empty="
                + (primary.getSuppressed().length == 0));

        try {
            throw null;
        } catch (NullPointerException ex) {
            System.out.println("throwNull="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedNullDemo.java
java SuppressedNullDemo
```

Output:

```text
nullRejected=NullPointerException
empty=true
throwNull=NullPointerException
```

In the example above, the `NullPointerException` from `addSuppressed(null)` is an **API argument** error. The error from `throw null` is caused by **throwing a `null` reference value**. Both are the same `NullPointerException` type, but they originate from two different mechanisms.

## 6. When suppression is disabled, Java still validates invalid arguments

`Throwable` has a protected constructor:

```java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
```

An exception subclass can call the corresponding `Exception` constructor to set `enableSuppression=false`. When suppression is disabled:

- `getSuppressed()` always returns an empty array.
- `addSuppressed(other)` with a **valid other object** records nothing in the list.
- **However**, `addSuppressed(null)` still throws `NullPointerException`.
- **And** `addSuppressed(this)` still throws `IllegalArgumentException`.
- The `enableSuppression` and `writableStackTrace` flags are independent settings; disabling suppression does not automatically require disabling the stack trace.

This is a subtle detail in the Javadoc: when suppression is disabled, `addSuppressed` merely skips storing the data; **it does not skip argument validation**.

### Java 17+ example: testing disabled suppression mode

Save as `DisabledSuppressionDemo.java`:

```java
public class DisabledSuppressionDemo {
    static final class NoSuppressionException extends Exception {
        NoSuppressionException(String message) {
            super(message, null, false, true);
        }
    }

    public static void main(String[] args) {
        NoSuppressionException primary =
                new NoSuppressionException("main");

        primary.addSuppressed(new Exception("ignored"));
        System.out.println("count=" + primary.getSuppressed().length);

        try {
            primary.addSuppressed(null);
        } catch (NullPointerException ex) {
            System.out.println("null="
                    + ex.getClass().getSimpleName());
        }

        try {
            primary.addSuppressed(primary);
        } catch (IllegalArgumentException ex) {
            System.out.println("self="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("finalCount="
                + primary.getSuppressed().length);
    }
}
```

```bash
javac -encoding UTF-8 DisabledSuppressionDemo.java
java DisabledSuppressionDemo
```

Output:

```text
count=0
null=NullPointerException
self=IllegalArgumentException
finalCount=0
```

The `NoSuppressionException` class disables the suppressed list in its constructor. Adding a valid exception has no effect; both invalid arguments are still rejected. In normal business implementations, **you should not disable suppression just to reduce log volume**, because doing so loses information about cleanup failures.

## 7. Why can self-suppression occur in `try-with-resources`?

Normally, the `try` body and `close()` create **two independent exception objects**. Java keeps the body error as the primary exception and calls `primary.addSuppressed(closeFailure)`. If a developer deliberately reuses **the exact same `Throwable` object** in both places, the internal call can become:

```java
Throwable primary = shared;
Throwable closeFailure = shared;

primary.addSuppressed(closeFailure); // Self-suppression!
```

This is an explanatory model, not the exact line-by-line code generated by every compiler. When `primary == closeFailure`, `addSuppressed` is rejected with `IllegalArgumentException`. Thus, a flaw in **how exception objects are structured** can alter the final exception that escapes instead of preserving the primary error as usual.

### Java 17+ program: intentionally rethrowing the same object

Save as `SameThrowableResourceDemo.java`:

```java
public class SameThrowableResourceDemo {
    static final IllegalStateException SHARED =
            new IllegalStateException("shared failure");

    static class BadResource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close");
            throw SHARED;
        }
    }

    public static void main(String[] args) {
        try (BadResource resource = new BadResource()) {
            System.out.println("body");
            throw SHARED;
        } catch (IllegalArgumentException ex) {
            System.out.println("observed="
                    + ex.getClass().getSimpleName());
            System.out.println("causeIsShared=" + (ex.getCause() == SHARED));
        }
    }
}
```

```bash
javac -encoding UTF-8 SameThrowableResourceDemo.java
java SameThrowableResourceDemo
```

Output according to `Throwable.addSuppressed` rules on JDK 17+:

```text
body
close
observed=IllegalArgumentException
causeIsShared=true
```

Process:

1. The `try` body throws `SHARED`.
2. Java calls `close()`, and `close()` also throws **the exact same `SHARED` reference**.
3. The primary-exception retention logic attempts to attach `SHARED` to the suppressed list of **`SHARED` itself**.
4. `addSuppressed` throws `IllegalArgumentException` due to self-suppression. In a standard JDK, that `IllegalArgumentException` retains `SHARED` as its cause.
5. `catch (IllegalArgumentException)` catches the new error. This is not the expected outcome of normal cleanup.

**This example is a cautionary lesson on what to avoid**, not a guide for building resource classes. Using a global exception object and throwing it repeatedly across layers can lead to stale stack traces, hard-to-manage cause/suppressed graphs, and multithreading issues.

### The right way: create two separate error objects

Save as `DistinctResourceFailureDemo.java`:

```java
public class DistinctResourceFailureDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("count=" + ex.getSuppressed().length);
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 DistinctResourceFailureDemo.java
java DistinctResourceFailureDemo
```

Output:

```text
primary=body failed
count=1
suppressed=close failed
```

The body error and the close error are two fresh objects, so `try-with-resources` can keep the body error as primary and attach the close error as expected.

## 8. Choosing the primary exception differs from establishing a cause relationship

In `try-with-resources`, the pre-existing exception from the `try` body takes precedence, and the subsequent `close()` exception may be suppressed. This does not mean the close error **caused** the body error.

Conversely, when a service layer catches an `IOException` and creates a `ServiceException`, the lower-level exception is the **cause** in the wrapper error's cause chain.

```java
try {
    repositoryOperation();
} catch (IOException ex) {
    throw new ServiceException("Unable to process request", ex);
}
```

This is an **illustrative snippet**, assuming `repositoryOperation() throws IOException` and `ServiceException` has a cause-accepting constructor. The object `ex` is the cause of the new exception; it is **not suppressed** by default.

A design can contain both relationships:

```text
ServiceException("request failed")
    └── cause → IOException("read failed")
                   └── suppressed[0] → IOException("close failed")
```

When reading logs, examine the cause chain and suppressed exceptions at each layer. Avoid flattening everything into a single message and losing the distinction between **an error that caused another error** and **a secondary error that occurred during cleanup**.

## 9. `getSuppressed()` returns an independent array and may be empty

For `Throwable.getSuppressed()`:

- If no exceptions have been suppressed, it returns an **empty** array.
- If suppression is disabled, it also returns an **empty** array, even if a valid exception was passed to `addSuppressed`.
- The returned array is for reading; **modifying elements in the returned array does not modify the stored suppressed list**.
- The array elements are **references to the actual `Throwable` objects**, not deep copies of each object. Those related error objects may still have their own cause/stack trace.

Illustrative snippet inside a method:

```java
Exception root = new Exception("root");
Exception first = new Exception("first");
root.addSuppressed(first);

Throwable[] snapshot = root.getSuppressed();
snapshot[0] = new Exception("replacement");

System.out.println(root.getSuppressed()[0].getMessage());
// Prints: first
```

Never use `getSuppressed() == null` to check for the absence of secondary errors; the API returns an array, so use `getSuppressed().length == 0`.

If you want to store error details in another structure, distinguish **copying the reference array** from **copying the `Throwable` objects**. Do not mutate the diagnostic data of shared exceptions just to change how logs are displayed.

## 10. Can the same suppressed object be added multiple times?

`addSuppressed` forbids **an exception from suppressing itself**, but the Javadoc does not require automatic deduplication by message or identity for **objects other than the receiver**.

For example:

```java
Exception primary = new Exception("primary");
Exception sameExtra = new Exception("extra");

primary.addSuppressed(sameExtra);
primary.addSuppressed(sameExtra);

System.out.println(primary.getSuppressed().length); // 2
```

This is an illustrative snippet inside a method. Adding the same object **different from `primary`** twice is recorded as two elements in call order. That does not trigger self-suppression because `sameExtra != primary`.

However, repeating the same secondary error in the list can make logs harder to read and mislead readers into thinking two independent failures occurred. If you build your own error collector, decide clearly on a deduplication policy by **identity** or **event**, rather than simply relying on whether two error messages are equal.

## 11. Non-null cause assumptions and unsafe access still cause NPE

A very common practical mistake:

```java
Exception ex = new Exception("independent");
System.out.println(ex.getCause().getMessage()); // NPE when cause == null
```

This is an example that **intentionally fails at runtime**. `getCause()` can return `null`; always check before dereferencing.

Valid pattern:

```java
Throwable cause = ex.getCause();
if (cause == null) {
    System.out.println("No known cause");
} else {
    System.out.println(cause.getMessage());
}
```

In the following example, `ex` already exists in scope. With `getSuppressed()`, you do not need to check the array for `null` under the standard contract, but you still must check its **length** before accessing the first element:

```java
Throwable[] extras = ex.getSuppressed();
if (extras.length > 0) {
    System.out.println(extras[0].getMessage());
}
```

Do not write `ex.getSuppressed()[0]` without checking if the application might not produce secondary errors. Such code often triggers `ArrayIndexOutOfBoundsException` while handling another exception, obscuring the error that needs analysis.

## 12. Designing new exceptions: choose a cause-accepting constructor over late `initCause`

When you can design a custom exception class, the clearest approach is usually to declare a constructor that accepts a cause:

```java
class DataLoadException extends Exception {
    DataLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a **valid class**, without a `main` method to run standalone. When used:

```java
throw new DataLoadException("Cannot load configuration", original);
```

The new exception already has the exact cause from the moment of creation. There is no need to call `initCause()`, and you avoid the risk of accidentally initializing it twice.

`initCause()` remains useful when you must integrate a legacy exception type that does not provide a cause-accepting constructor. If used, call it **immediately after instantiation** and only once:

```java
LegacyException wrapper = new LegacyException("operation failed");
wrapper.initCause(original);
throw wrapper;
```

This is an **illustrative pattern** with a `LegacyException` lacking a cause constructor, having a suitable `initCause` signature, and `original` being a `Throwable` different from `wrapper`. Deferring cause attachment until after the exception has passed through multiple layers makes the error state harder to predict.

**Do not make an exception the cause of itself** to "preserve the stack trace." If you need to rethrow the exact same error, use `throw original;` (when the checked type matches the method signature). If you need to add context, create **another wrapper** and pass `original` as the cause.

## 13. Other cases of reference cycles

Java forbids *direct self-cause* via `initCause(this)` and *direct self-suppression* via `addSuppressed(this)`. Do not assume that these APIs **automatically check for all complex reference cycles**.

For example, two objects created without causes can be incorrectly linked into an indirect cycle:

```java
Exception a = new Exception("A");
Exception b = new Exception("B");

a.initCause(b);
b.initCause(a); // Not b.initCause(b); creates an indirect cycle.
```

This is illustrative code **that should not be used**. Neither call passes the receiver itself as the argument, so the direct self-cause restriction does not protect against an indirect cycle like A → B → A. Printing tools may detect and mark cycles to avoid infinite output, but creating meaningless relationships like this still makes diagnostic information unreliable.

Similarly, avoid creating cross-linked networks of cause/suppressed references among multiple objects unless there is a genuine causal or cleanup meaning. Model error collections **from the reported error toward its cause or secondary errors**, rather than turning them into an arbitrary cyclic graph.

If multiple independent errors are needed in a processing step, use a composite exception with suppressed exceptions **distinct from the primary object**, or a purposefully designed composite result structure. Do not fabricate fake causes to stack multiple peer errors.

## 14. Common mistakes and fixes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| `ex.initCause(ex)` | `IllegalArgumentException` due to self-cause | Create another wrapper and attach `ex` as the wrapper's cause |
| `ex.addSuppressed(ex)` | `IllegalArgumentException` due to self-suppression | Only add distinct secondary error objects |
| `ex.addSuppressed(null)` | `NullPointerException` | Do not add anything if there are no secondary errors |
| `ex.getCause() == null` and assuming `initCause` can be called | May encounter `IllegalStateException` | Attach the cause at creation time or track the single-initialization policy |
| `new Exception("x", null)` then calling `initCause(real)` | `IllegalStateException` | Use the constructor with the real cause from the start |
| `initCause(null)` then trying to replace the cause later | `IllegalStateException` | Initialize only once; use `null` only when there truly is no cause |
| Disabling suppression and thinking `null`/self arguments are ignored | Still throws NPE/IAE | Always pass a valid error object distinct from the primary |
| Sharing a single exception instance for both the `try` body and `close()` | May cause self-suppression from automatic closing code | Create a new exception for each independent failure |
| Checking only `getSuppressed() != null` | Fails to check for an empty list | Check `getSuppressed().length > 0` |
| Accessing `getCause().getMessage()` without checking | NPE when cause is absent | Check `getCause() != null` first |
| Accessing `getSuppressed()[0]` when there are no secondary errors | `ArrayIndexOutOfBoundsException` | Check the array length |
| Wrapping an error with only a message | Loses original stack trace/cause/suppressed | Pass the original object to a cause-accepting constructor |
| Creating indirect cause cycles | Hard-to-read traces, may show circular reference warnings | Keep the causal graph meaningful and acyclic |
| Adding the same secondary error multiple times | May duplicate the same object in logs | Define a deduplication policy when aggregating |

## 15. Checklist when analyzing an error with cause and suppressed exceptions

1. **Identify the thrown object:** which object is primary, what is its type, and what is its message?
2. **Read the cause:** is `getCause()` `null`? If so, do not infer that `initCause` has never been run.
3. **Read suppressed exceptions:** how many elements does `getSuppressed()` have? Were the secondary objects created during cleanup/resource closing?
4. **Check identity:** is the code trying to add the primary itself to the suppressed list or attach it as its own cause?
5. **Review initialization:** was the cause set via constructor or `initCause`? Was it called multiple times?
6. **Check null handling:** cause may be absent; suppressed must not receive `null`; `throw null` statements and `getCause()` dereferences need separate handling.
7. **Check suppression mode:** does a custom exception class disable suppression? Missing suppressed entries in logs is sometimes due to the class design itself.
8. **Check `try-with-resources` logic:** do body/close errors create distinct objects? Could self-suppression occur by rethrowing a singleton exception?
9. **Check layer boundaries:** when wrapping errors, does the wrapper preserve the original object as the cause?
10. **Log only reliable information:** `printStackTrace()` can display cause and suppressed exceptions, but the linking information provided by code must still be designed properly.

## 16. Self-check

**Question 1.** What error does `ex.initCause(ex)` produce?  
**`IllegalArgumentException`**, because an object cannot be its own direct cause.

**Question 2.** What error does `ex.addSuppressed(ex)` produce?  
**`IllegalArgumentException`**, due to self-suppression.

**Question 3.** Is `ex.initCause(null)` valid? Can `initCause(real)` be called again afterward?  
**Valid if the cause has not been initialized before. It cannot be called again**: the first call consumed the initialization allowance.

**Question 4.** Does `new Exception("x", null)` allow attaching another cause later using `initCause`?  
**No.** The cause-accepting constructor already initialized the cause to `null`.

**Question 5.** What does `ex.addSuppressed(null)` throw?  
**`NullPointerException`**. An empty list is represented by an empty array from `getSuppressed()`, not by a `null` element.

**Question 6.** When `enableSuppression=false`, is calling `addSuppressed(null)` rejected?  
**Yes**, because the API still validates arguments.

**Question 7.** Can two exceptions with different object identities but the same message form a cause or suppressed relationship?  
**Yes**, when that relationship is meaningful: what is forbidden here is an object linking to itself, not duplicate messages.

**Question 8.** In `try-with-resources`, what error can occur if both the body and `close()` throw the same singleton exception instance?  
**Self-suppression**, which can lead to `IllegalArgumentException` when Java attempts to attach the exception to itself.

**Question 9.** Is `getSuppressed() == null` the right way to check for no secondary errors?  
**No.** The method returns an array, which is empty if there are no secondary errors.

**Question 10.** Does `getCause() == null` prove that the cause has never been initialized?  
**No.** The cause may have been set to `null` via a constructor or `initCause(null)`.

## References

- [Java SE 21 — `Throwable.initCause()`, `getCause()`, `addSuppressed()`, `getSuppressed()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html).
- [JLS Java SE 21 — §14.20.3: `try-with-resources` and suppressed exceptions](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS Java SE 21 — §14.18: `throw` Statement](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.18).

**Key takeaway:** Java allows a `null` cause, but only allows cause initialization **once**; `getCause()==null` does not prove it can still be initialized. Meanwhile, a suppressed exception must be a `Throwable` object **different from its containing object and non-null**. Following these limits preserves original error information and avoids creating new exceptions during error handling.
