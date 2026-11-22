# `getCause()`, `initCause()`, and Cause Initialization Conditions of `Throwable` in Java

In Java, an exception can be created **because it was caused by another exception**. The original object is called the *cause*; the outer wrapping exception object typically adds context at a higher handling layer. `Throwable.getCause()` allows tracing back the cause, while `Throwable.initCause(Throwable)` supports **attaching a cause after object creation** under very specific conditions.

The most important takeaway of this article:

> **`getCause() == null` does not mean `initCause(...)` can definitely be called.** Java distinguishes between the **uninitialized** cause state and the **initialized with `null`** cause state.

Although both show `getCause()` returning `null`, two objects created by `new Throwable("message")` and `new Throwable("message", null)` have different eligibility to call `initCause(...)`.

This article explains that difference, its relationship with constructors, how to build meaningful cause chains, the exceptions thrown by `initCause` itself, and the situations where constructors should be used instead of late cause initialization. The examples are compatible with Java 17+.

## 1. What is a Cause in Java Exceptions?

For example, an application is reading configuration from a file. The low-level error is `IOException`, but the service initialization layer wants to report that **the service cannot be initialized**:

~~~java
try {
    readConfiguration();
} catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Không thể khởi tạo dịch vụ", original);
}
~~~

This is an **illustrative snippet** assuming the `readConfiguration()` method can throw `IOException`.

In the example:

- `original` is the initial I/O exception.
- `new IllegalStateException("...", original)` creates a **new** exception object with the service layer's message.
- The constructor accepting a cause holds a **reference to the `original` exception itself**.
- The `throw` statement throws the new `IllegalStateException` object.
- A caller receiving the service-layer error can call `getCause()` to trace back to the I/O error.

Model:

~~~text
IllegalStateException: Không thể khởi tạo dịch vụ
    |
    +-- getCause() --> IOException: Không đọc được cấu hình
                           |
                           +-- getCause() --> null
~~~

**A cause is a link between `Throwable` objects, not a copy of the message string.** If an exception has a cause, Java can display the `Caused by:` relationship when printing the stack trace, aiding in diagnosing layers of causes.

A cause chain can have multiple layers:

~~~text
ServiceInitializationException
    -> ConfigurationException
        -> IOException
            -> FileNotFoundException
~~~

This is a **conceptual diagram**; the concrete types in an application may differ. Wrapping across too many layers is not helpful if each layer does not add meaningful semantics or a contract.

## 2. What Does `getCause()` Read and Return?

Basic API signature:

~~~java
public synchronized Throwable getCause()
~~~

This is an **illustrative API signature**, not a declaration to copy into a program. `getCause()` returns a reference to the `Throwable` object stored as the direct cause; if no cause is specified, it returns `null`.

~~~java
java.io.IOException root =
        new java.io.IOException("Đọc thất bại");

IllegalStateException outer =
        new IllegalStateException("Khởi tạo thất bại", root);

System.out.println(outer.getCause() == root); // true
System.out.println(outer.getCause().getMessage()); // Đọc thất bại
~~~

In the snippet above, the `==` operator shows that the cause is **the exact same object** `root`, not a newly recreated exception.

### Direct Cause vs. Deepest Cause

`getCause()` only returns **one step of the direct cause**. If A wraps B and B wraps C:

~~~text
A.getCause() == B
B.getCause() == C
C.getCause() == null
~~~

To find the root error, an application can traverse the chain. However, you should not write a blind loop in a system that receives `Throwable` instances from untrusted sources: due to custom code or unusual structures, a cause chain **can form a cycle**, so traversal algorithms need to avoid infinite loops. A later section provides a safe handling example.

### `null` Value Is a Public State, Not an "Uninitialized Flag"

A caller of `getCause()` only observes "no cause returned". That value **does not indicate** whether a constructor has already set the cause or not. The internal state of `Throwable` is what determines whether `initCause(...)` is valid.

## 3. All Constructors Related to `initCause` Eligibility

`Throwable` provides several constructors. Two groups must be distinguished:

| How `Throwable` is created | Initial `getCause()` | Cause state for `initCause` |
| --- | --- | --- |
| `new Throwable()` | `null` | **Uninitialized**, can be attached once |
| `new Throwable("message")` | `null` | **Uninitialized**, can be attached once |
| `new Throwable((Throwable) null)` | `null` | **Initialized with null**, cannot be re-attached |
| `new Throwable(root)` | `root` | **Initialized**, cannot be re-attached |
| `new Throwable("message", null)` | `null` | **Initialized with null**, cannot be re-attached |
| `new Throwable("message", root)` | `root` | **Initialized**, cannot be re-attached |
| Four-parameter `protected` constructor with cause | Matches the passed cause value | **Initialized**, even when cause is null |

Note the `Throwable(Throwable)` and `Throwable(String, Throwable)` overloads: they **initialize the cause state right in the constructor**. This remains true even if the `cause` argument is `null`.

Comparison example:

~~~java
Throwable a = new Throwable("A");
Throwable b = new Throwable("B", null);

System.out.println(a.getCause() == null); // true
System.out.println(b.getCause() == null); // true

a.initCause(new java.io.IOException("root")); // Valid.
b.initCause(new java.io.IOException("root")); // Throws IllegalStateException.
~~~

This snippet **intentionally contains a statement that causes a runtime error at the end** to demonstrate the difference. Do not run it without a `try/catch` if you want the program to continue.

Similarly, the constructor taking only `Throwable cause` also marks the cause as initialized even when receiving null:

~~~java
Throwable noCause = new Throwable((Throwable) null);
System.out.println(noCause.getCause()); // null
noCause.initCause(new Exception("later")); // IllegalStateException
~~~

The `(Throwable) null` cast lets the reader know exactly which overload is being called.

## 4. Why Does an "Uninitialized" State Exist Even Though the Getter Returns Null?

In the standard implementation of `Throwable`, the cause state is represented by a special sentinel value before the user sets a cause, allowing `getCause()` to return `null` in that state and distinguishing it from "assigned null". You should not write code that depends on internal fields or try to modify them via reflection.

This can be visualized with a **conceptual** state diagram:

~~~text
Created with Throwable() or Throwable(String)
                 |
                 v
       [UNINITIALIZED CAUSE]
             |        |
             |        +--> getCause() returns null
             |
             +--> initCause(root) succeeds
             |       |
             |       v
             |  [INITIALIZED CAUSE: root]
             |
             +--> initCause(null) succeeds
                     |
                     v
               [INITIALIZED CAUSE: null]

Created with Throwable(cause) or Throwable(message, cause)
                 |
                 v
       [INITIALIZED CAUSE: cause]
                 |
                 +--> any subsequent initCause(...) is rejected
~~~

Even if the user calls `initCause(null)`, the state has transitioned to **initialized**. There is no public mechanism to revert it back to uninitialized.

### Do Not Infer Eligibility Based on `getCause() == null`

The following check pattern is **semantically wrong**:

~~~java
if (problem.getCause() == null) {
    problem.initCause(root);
}
~~~

`problem` and `root` here are assumed pre-existing variables. If `problem` was created using the `(String, Throwable)` constructor with a `null` cause, the `getCause() == null` condition is true, yet `initCause(root)` still throws `IllegalStateException`.

Better practice: choose one of the two paths right at the object creation site:

- Pass the cause **in the constructor** when the class supports that overload.
- If only a constructor without a cause exists and the API permits it, call `initCause` **once immediately after creation**.

Do not design a flow that "reads the getter and guesses whether `initCause` is allowed".

## 5. How Does `initCause(Throwable cause)` Work?

API signature:

~~~java
public synchronized Throwable initCause(Throwable cause)
~~~

This method sets the cause for the current `Throwable` object **when the cause state has not been initialized yet**.

~~~java
Throwable outer = new Throwable("Không thể tiếp tục");
java.io.IOException root =
        new java.io.IOException("Kết nối hỏng");

Throwable returned = outer.initCause(root);

System.out.println(outer.getCause() == root); // true
System.out.println(returned == outer);        // true
~~~

Both comparisons are `true`:

1. `outer.getCause()` points to the `root` object.
2. `initCause(...)` returns **the `outer` object itself**, without creating another `Throwable` object.

The existing message and stack trace data of `outer` are not automatically replaced by `root`'s data. `initCause` only serves to establish the cause relationship.

### Conditions for Success

A call to `initCause(cause)` is valid when it satisfies the requirements of the default `Throwable` behavior:

- The receiving object's cause **has not been initialized previously**.
- `cause` **is not the receiving object itself** (`cause != this`).
- No other constraints are imposed by a subclass according to its contract.

After succeeding, the ability to set the cause via this method is exhausted. Adding a second cause is not a valid operation.

### When Should It Be Used?

The original purpose of `initCause` was to support exception classes that do not provide a constructor accepting a cause, especially when compatibility with legacy APIs is needed.

Example of a legacy custom error class:

~~~java
public class LegacyProblem extends Exception {
    public LegacyProblem(String message) {
        super(message);
    }
}
~~~

Suppose this class's API only provides a message constructor:

~~~java
LegacyProblem outer =
        new LegacyProblem("Lỗi nghiệp vụ");
outer.initCause(new java.io.IOException("Hỏng kết nối"));
throw outer;
~~~

This is an illustrative snippet inside a method that appropriately declares/catches the checked `LegacyProblem`. Because the `LegacyProblem(String)` constructor calls `super(message)` and does not set a cause, `initCause` can attach the cause once.

For new code under your control, consider adding a `LegacyProblem(String, Throwable)` constructor to the class rather than forcing every caller to use the two-step `initCause`.

## 6. `IllegalStateException`: Cause Already Initialized

The most common error:

~~~java
Throwable problem = new Throwable(
        "Không đọc được dữ liệu", null);

problem.initCause(new java.io.IOException("I/O"));
// Runtime: IllegalStateException
~~~

Although `problem.getCause()` is initially `null`, the `Throwable(String, Throwable)` constructor already initialized the cause state. Therefore `initCause` is no longer valid.

Another situation:

~~~java
Throwable error = new Throwable("Lỗi");
error.initCause(new java.io.IOException("Lỗi lần đầu"));
error.initCause(new java.io.IOException("Lỗi lần hai"));
// Runtime: IllegalStateException
~~~

`initCause` succeeds the first time, but **cannot replace** the cause on a subsequent call.

### `initCause(null)` Also Consumes the Initialization Right

~~~java
Throwable problem = new Throwable("Lỗi");
problem.initCause(null);
System.out.println(problem.getCause()); // null

problem.initCause(new Exception("Lý do mới"));
// Runtime: IllegalStateException
~~~

If you call `initCause(null)`, you have made the decision "the cause is null". It cannot be reversed by calling `initCause` again.

Therefore, avoid treating `initCause(null)` as a "reset" statement. It **does not reset the state** back to uninitialized.

## 7. `IllegalArgumentException`: Cannot Be Its Own Cause

Direct self-reference situation:

~~~java
Throwable problem = new Throwable("Lỗi");
problem.initCause(problem);
// Runtime: IllegalArgumentException
~~~

Java does not allow a `Throwable` to set **itself** as its own direct cause. Such direct self-reference adds no semantics and could send cause-chain traversal into a loop.

**Key distinction to remember:**

- Cause was already initialized earlier: `IllegalStateException` error.
- Cause is the receiving object itself: `IllegalArgumentException` error in an appropriate uninitialized situation.
- Cause is `null` on the first set: valid if the state is uninitialized; however, it still counts as an initialization.

Do not write business logic that depends on the **precedence order between multiple simultaneous invalid conditions**, unless the API of a specific version and class explicitly guarantees it. Always avoid both conditions.

### Cause Chains Can Form Indirect Cycles

Prohibiting `problem.initCause(problem)` only prevents **direct self-reference**. Do not infer that all indirect reference cycles are automatically prevented by every API:

~~~java
Throwable a = new Throwable("A");
Throwable b = new Throwable("B");

a.initCause(b);
b.initCause(a);
~~~

This is an **illustrative anti-pattern not to be used**: two different objects can form the chain A → B → A. A custom-written algorithm that simply loops `current = current.getCause()` until hitting `null` risks never terminating. Stack trace printing tools may have their own safeguards; custom traversal code must still be designed safely.

## 8. The Cause-Only Constructor and Message Semantics

Common `Throwable` constructors:

~~~java
new Throwable()
new Throwable("message")
new Throwable(cause)
new Throwable("message", cause)
~~~

The `Throwable(Throwable cause)` form both sets the cause and generates the message from `cause.toString()` when `cause` is non-null:

~~~java
Throwable root =
        new IllegalArgumentException("Tuổi không hợp lệ");

Throwable outer = new Throwable(root);

System.out.println(outer.getMessage());
// java.lang.IllegalArgumentException: Tuổi không hợp lệ
~~~

Notice the distinction:

- `root.getMessage()`: `"Tuổi không hợp lệ"`.
- `root.toString()`: typically `"java.lang.IllegalArgumentException: Tuổi không hợp lệ"`.
- `outer.getMessage()` from the cause-only constructor: equals the string produced from `root.toString()`.

With the constructor accepting both message and cause, the message is independent:

~~~java
Throwable outer = new Throwable(
        "Không thể hoàn thành đăng ký", root);

System.out.println(outer.getMessage());
// Không thể hoàn thành đăng ký
~~~

Both constructor forms initialize the cause, so `initCause(...)` **cannot be used to change it**.

### Constructors Accepting `null` Have Confusing Overloads

Use:

~~~java
Throwable messageNull = new Throwable((String) null);
Throwable causeNull = new Throwable((Throwable) null);
~~~

The difference:

- `messageNull` is created using the `(String)` constructor, so its cause state is uninitialized.
- `causeNull` is created using the `(Throwable)` constructor, so its cause state is initialized to `null`.

Both initially return `null` from `getMessage()` and `getCause()`, but their eligibility to call `initCause(...)` differs.

Specifically, the statement `new Throwable(null)` **does not compile** because Java cannot choose between the `Throwable(String)` and `Throwable(Throwable)` overloads, as these two types do not have a suitable subtype relationship to select a most specific overload. Use a cast if you need to intentionally pass `null`.

## 9. The Four-Parameter Constructor and Cause

`Throwable` also has a `protected` constructor:

~~~java
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

It allows subclasses to control the ability to record suppressed exceptions and write the stack trace. However, as far as `initCause` is concerned, the key point is that **this constructor still initializes the cause at object creation time**, even when `null` is passed.

Subclass example:

~~~java
public final class DomainProblem extends Exception {
    public DomainProblem(
            String message,
            Throwable cause,
            boolean enableSuppression,
            boolean writableStackTrace) {
        super(message, cause, enableSuppression, writableStackTrace);
    }
}
~~~

This is a **standalone class** if saved in `DomainProblem.java`. `Exception` has a corresponding protected overload for subclasses to call `super(...)`.

Usage example:

~~~java
DomainProblem problem =
        new DomainProblem("Lỗi đặc biệt", null, true, false);

System.out.println(problem.getCause()); // null
System.out.println(problem.getStackTrace().length); // 0

problem.initCause(new java.io.IOException("Nguyên nhân"));
// Runtime: IllegalStateException
~~~

**The `writableStackTrace` flag does not determine `initCause` eligibility.** In the example, the cause was already initialized to `null`; disabling the stack trace is an independent configuration choice.

Similarly, disabling `enableSuppression` only affects the ability to retain `getSuppressed()`; it does not reopen the ability to call `initCause`.

## 10. When Wrapping Checked and Unchecked Exceptions

A cause is useful when a call layer needs to **change how an error is expressed** while preserving its origin.

~~~java
static int readPort(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Cổng không phải số nguyên: " + text, cause);
    }
}
~~~

This is an illustrative Java method. `NumberFormatException` is also unchecked; it is wrapped to add network port context and keep the cause link.

With a checked exception:

~~~java
static String loadRequired(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Thiếu cấu hình bắt buộc", cause);
    }
}
~~~

Here, `IOException` is checked, while the new `IllegalStateException` is unchecked. The `catch` and `throws` rules for the caller depend on **the actual exception type thrown at the outer layer**, not merely the type of the cause. A `catch (IOException e)` in the caller **does not automatically catch `IllegalStateException`** just because its cause is `IOException`.

Whether to convert a checked exception into an unchecked one is an API/architectural decision; do not wrap every exception out of habit. In particular, avoid creating chains of meaningless wrappers that only deepen the cause chain without adding context.

## 11. `getCause()` Is Not `getSuppressed()`

These two relationships in `Throwable` serve distinct purposes.

**Cause:** the underlying reason why another exception was created. For example, `IllegalStateException("Khởi tạo thất bại", ioError)` has `ioError` as its cause.

**Suppressed:** secondary exceptions stored **alongside a primary exception**, such as errors when closing resources in try-with-resources:

~~~java
Throwable primary = new Throwable("Thao tác thất bại");

primary.addSuppressed(
        new java.io.IOException("Đóng tài nguyên thất bại"));

System.out.println(primary.getCause()); // null
System.out.println(primary.getSuppressed().length); // 1
~~~

The snippet above shows that a suppressed exception **does not** automatically become a cause. `getCause()` remains `null` even though `getSuppressed().length` is `1`.

The reverse is also true: setting `initCause(root)` **does not automatically add `root` to the suppressed list**.

With try-with-resources, when the `try` body throws a primary exception and then `close()` throws an error, Java typically attaches the close error as suppressed on the primary exception. Whether the primary exception's cause has been initialized or not is a **separate matter**.

### Do Not Replace Cause with Suppressed or Vice Versa

If `IOException` is the root origin of a business failure, keep it as the wrapper's cause. If an additional error occurs during cleanup when a primary error already exists, suppressed exceptions are usually the appropriate relationship. Choosing the right relationship makes stack traces easier to read and keeps analysis tools accurate.

## 12. Cause and Stack Trace Do Not Replace Each Other

`Throwable` typically records the stack trace **when the object is instantiated**. The stack trace reflects the call frames leading to the creation site, whereas the cause links to **another exception**.

~~~java
IOException root = new IOException("Không đọc được");
IllegalStateException wrapper =
        new IllegalStateException("Không tải được", root);
~~~

This is an illustrative snippet in a scope that imports or uses the fully qualified name for `IOException`. When creating the wrapper, Java normally records a stack trace for the wrapper. It does not erase `root`'s stack trace.

Therefore, you can have:

- A wrapper with a message, stack trace, and cause.
- A cause with its own message and stack trace.
- A wrapper with no cause, yet still having a stack trace.
- A wrapper with a cause, whose own stack trace has been disabled via a special subclass configuration constructor.

**Read `getCause()` to find the underlying cause**, and **read the stack trace to find the location/call path**; do not use one as a substitute for the other.

### How Does `getLocalizedMessage()` Relate?

By default, `getLocalizedMessage()` returns the message according to `Throwable`'s behavior; subclasses may customize it. It does not alter the cause state. You should not treat a localized message as required data for identifying the official cause of an error.

## 13. Standalone Runnable Java 17+ Program

The following program directly demonstrates:

1. `getCause() == null` in **two different states**.
2. `initCause` succeeds once; a second call fails.
3. A cause initialized to `null` by a constructor **cannot be re-attached**.
4. Setting an exception as its own cause triggers `IllegalArgumentException`.
5. The cause-only constructor builds its message from `cause.toString()`.
6. Wrapping `NumberFormatException` preserves the root cause.
7. Suppressed exceptions are not causes.
8. Cause-chain traversal needs cycle protection.

Create the file **`ThrowableCauseDemo.java`**:

~~~java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class ThrowableCauseDemo {

    static final class ConfigException extends Exception {
        ConfigException(String message) {
            super(message);
        }

        ConfigException(String message, Throwable cause) {
            super(message, cause);
        }

        ConfigException(Throwable cause) {
            super(cause);
        }
    }

    public static void main(String[] args) {
        IOException root = new IOException("disk");

        System.out.println("== uninitialized ==");
        Throwable fresh = new Throwable("fresh");
        System.out.println("fresh.before=" + fresh.getCause());
        Throwable returned = fresh.initCause(root);
        System.out.println("fresh.same=" + (fresh.getCause() == root));
        System.out.println("init.returnedSelf=" + (returned == fresh));
        try {
            fresh.initCause(new IOException("later"));
        } catch (IllegalStateException e) {
            System.out.println("fresh.second=IllegalStateException");
        }

        System.out.println("== initialized null ==");
        Throwable explicitNull = new Throwable("empty", null);
        System.out.println("explicitNull.cause=" + explicitNull.getCause());
        try {
            explicitNull.initCause(root);
        } catch (IllegalStateException e) {
            System.out.println(
                    "explicitNull.later=IllegalStateException");
        }

        Throwable byCauseNull = new Throwable((Throwable) null);
        try {
            byCauseNull.initCause(root);
        } catch (IllegalStateException e) {
            System.out.println(
                    "byCauseNull.later=IllegalStateException");
        }

        Throwable nullViaInit = new Throwable("initially free");
        nullViaInit.initCause(null);
        try {
            nullViaInit.initCause(root);
        } catch (IllegalStateException e) {
            System.out.println("nullViaInit.again=IllegalStateException");
        }

        System.out.println("== self cause ==");
        Throwable self = new Throwable("self");
        try {
            self.initCause(self);
        } catch (IllegalArgumentException e) {
            System.out.println("self.error=IllegalArgumentException");
        }

        System.out.println("== constructors ==");
        Throwable onlyCause = new Throwable(root);
        Throwable messageAndCause = new Throwable("load failed", root);
        System.out.println("onlyCause.message=" + onlyCause.getMessage());
        System.out.println(
                "onlyCause.same=" + (onlyCause.getCause() == root));
        System.out.println(
                "messageAndCause.message=" + messageAndCause.getMessage());
        System.out.println(
                "messageAndCause.same="
                        + (messageAndCause.getCause() == root));

        System.out.println("== wrapping ==");
        try {
            parsePort("abc");
        } catch (ConfigException e) {
            System.out.println("outer.message=" + e.getMessage());
            System.out.println(
                    "inner.type=" + e.getCause().getClass().getSimpleName());
            System.out.println(
                    "inner.message=" + e.getCause().getMessage());
        }

        System.out.println("== suppressed ==");
        Throwable primary = new Throwable("primary");
        primary.addSuppressed(new IOException("close"));
        System.out.println("primary.cause=" + primary.getCause());
        System.out.println(
                "primary.suppressed=" + primary.getSuppressed().length);

        System.out.println("== traversal ==");
        Throwable outer = new Throwable("outer", root);
        System.out.println(
                "chain.length=" + countDistinctCauses(outer));

        Throwable a = new Throwable("A");
        Throwable b = new Throwable("B");
        a.initCause(b);
        b.initCause(a);
        System.out.println(
                "cycle.distinct=" + countDistinctCauses(a));
    }

    static int parsePort(String text) throws ConfigException {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException cause) {
            throw new ConfigException(
                    "Invalid port: " + text, cause);
        }
    }

    static int countDistinctCauses(Throwable error) {
        Set<Throwable> seen =
                Collections.newSetFromMap(
                        new IdentityHashMap<Throwable, Boolean>());
        Throwable current = error;

        while (current != null && seen.add(current)) {
            current = current.getCause();
        }
        return seen.size();
    }
}
~~~

Compile and run:

~~~bash
javac ThrowableCauseDemo.java
java ThrowableCauseDemo
~~~

**Deterministic stdout:**

~~~text
== uninitialized ==
fresh.before=null
fresh.same=true
init.returnedSelf=true
fresh.second=IllegalStateException
== initialized null ==
explicitNull.cause=null
explicitNull.later=IllegalStateException
byCauseNull.later=IllegalStateException
nullViaInit.again=IllegalStateException
== self cause ==
self.error=IllegalArgumentException
== constructors ==
onlyCause.message=java.io.IOException: disk
onlyCause.same=true
messageAndCause.message=load failed
messageAndCause.same=true
== wrapping ==
outer.message=Invalid port: abc
inner.type=NumberFormatException
inner.message=For input string: "abc"
== suppressed ==
primary.cause=null
primary.suppressed=1
== traversal ==
chain.length=2
cycle.distinct=2
~~~

### Detailed Analysis of the Output

**Uninitialized group:** `fresh` is created with the `(String)` constructor, so its cause is uninitialized. `getCause()` returns `null`. `initCause(root)` is valid and returns `fresh` itself. When attempting to attach a second cause, Java throws `IllegalStateException`.

**Initialized null group:** `explicitNull` is created with the `(String, Throwable)` constructor with a `null` cause; `byCauseNull` is created with the `(Throwable)` constructor with a `null` cause. Both have already initialized their cause state and disallow calling `initCause`. `nullViaInit` calls `initCause(null)` successfully, but afterward the right to initialize the cause has also been consumed.

**Self cause group:** Java rejects `self.initCause(self)`; this error is an `IllegalArgumentException` when `self`'s cause is still uninitialized.

**Constructors group:** The cause-only form builds its message from `IOException.toString()`; the message+cause form keeps the wrapper's message separate. Both retain a reference to the original cause.

**Wrapping group:** `Integer.parseInt("abc")` throws `NumberFormatException`. `parsePort` wraps it in `ConfigException`; the caller reads the outer layer's message and the cause's type/message to see both layers. `NumberFormatException` does not disappear just because the outer exception is a checked `ConfigException`.

**Suppressed group:** `primary` has one suppressed exception, yet `getCause()` is still `null`; the two relationships do not automatically convert into one another.

**Traversal group:** `countDistinctCauses` uses a set based on object reference **identity** rather than `equals` to ensure the algorithm terminates when cycles exist. The chain `outer → root → null` has two objects; the chain `a → b → a` also has two distinct objects, so the method returns `2` instead of running infinitely.

## 14. Best Practice: Prefer Constructors with Cause

When an API provides a constructor:

~~~java
public SomeException(String message, Throwable cause)
~~~

prefer creating a complete object in a single step:

~~~java
throw new IllegalStateException(
        "Không thể tải tài nguyên", original);
~~~

These are two **illustrative forms**, where `SomeException` is a placeholder name and `original` is an existing cause.

Compared to:

~~~java
IllegalStateException outer =
        new IllegalStateException("Không thể tải tài nguyên");
outer.initCause(original);
throw outer;
~~~

both can represent a similar message and cause when `original` is valid. However, the constructor ensures:

- The cause is initialized right at object creation time.
- The code has fewer steps and fewer intermediate states.
- Reduced risk of forgetting to attach the cause.
- Avoiding accidental `initCause` calls when a constructor has already set the cause.

You do not need to rewrite existing code merely for shorter syntax if the API contract requires otherwise; choose based on the exception type and the behavior callers need.

### Do Not Change Exception Type Just to Have a Cause Constructor

If the original `IOException` already fits the contract, you can rethrow it or declare `throws IOException` instead of wrapping it into a different exception type. Wrapping an exception should provide genuinely useful **contextual information or API boundaries**.

## 15. When a Legacy Exception Class Only Has a Message Constructor

Some libraries or historical error classes only provide the overload:

~~~java
LegacyException(String message)
~~~

When you need to preserve the cause, if `LegacyException` inherits the `Throwable` behavior that permits `initCause`, you can use:

~~~java
LegacyException error =
        new LegacyException("Thao tác thất bại");
error.initCause(original);
throw error;
~~~

The snippets above are illustrative, not the real API of a JDK class named `LegacyException`. **Always check the constructors and contract of the specific class**:

- Some specialized exception classes have their own mechanism for storing/reading the cause or override the related API.
- Some classes intentionally lock down the ability to set a cause.
- Do not infer a class's behavior solely from its name or inheritance hierarchy while ignoring its API documentation.

If you control the source code of the legacy class, you can add a `(String, Throwable)` overload so that new callers do not need late cause attachment.

## 16. What Happens If `initCause` Is Called After `throw`?

Technically, `Throwable` is an object and `initCause` checks the **cause state**, with no separate requirement that it "may only be called before the first throw". If an object still has an uninitialized cause, the default API may allow attaching a cause once the object is caught after a `throw`.

Example:

~~~java
static void lateLink() {
    Throwable problem = new Throwable("late");
    try {
        throw problem;
    } catch (Throwable e) {
        e.initCause(new java.io.IOException("cause"));
        System.out.println(e.getCause().getMessage());
    }
}
~~~

This is an illustrative method that can be placed in a Java class. It prints `cause`. However, **this should not be treated as a default design pattern**: the cause should be decided when you create or wrap the exception, before it is propagated across handling layers. Adding a cause after throwing/logging can lead to components observing inconsistent information.

If multiple threads hold a reference to the same exception, the specific synchronization behavior of `getCause` and `initCause` is no substitute for a clean immutable/error-reporting design. Avoid reusing a single shared exception object whose cause mutates over time to represent multiple independent failures.

## 17. Common Pitfalls

### Pitfall 1 — Seeing `getCause() == null` and Always Calling `initCause`

Wrong. A cause **initialized to `null`** still makes the getter return null, yet disallows re-attaching.

### Pitfall 2 — Assuming the message+cause Constructor with a Null Cause Is Equivalent to the Message-Only Constructor

They are not equivalent regarding `initCause` eligibility. `new Throwable("x", null)` locks the cause state; `new Throwable("x")` leaves the state uninitialized.

### Pitfall 3 — Thinking `initCause(null)` Is a Reset

No. It counts as a cause initialization. A subsequent `initCause(nonNull)` is invalid.

### Pitfall 4 — Calling `initCause` Twice to Change the Cause

Wrong. `initCause` is not a repeatable setter; the second call throws `IllegalStateException`.

### Pitfall 5 — Self-Referencing as Cause

`error.initCause(error)` is disallowed because becoming its own direct cause creates a reference cycle.

### Pitfall 6 — Traversing Causes Without Cycle Protection

Do not assume every custom chain terminates with `null`; error-processing algorithms handling data from multiple sources must detect already-visited references.

### Pitfall 7 — Confusing Cause with Suppressed Exceptions

`getCause()` returns the direct cause. `getSuppressed()` returns the list of retained secondary errors; adding a suppressed exception does not populate the cause.

### Pitfall 8 — Only Copying `cause.getMessage()` into the New Message

If you only concatenate strings without storing the cause, you lose the object link and the cause's stack trace in the thrown error structure.

### Pitfall 9 — Assuming `Throwable(Throwable)` Uses the Cause's Message Directly

Incorrect. The cause-only constructor uses `cause.toString()` when the cause is non-null, which usually includes the class name.

### Pitfall 10 — Assuming Subclasses Inherit Cause Constructors

Constructors are not inherited; a subclass must define the overloads or use the API it provides.

### Pitfall 11 — Using the Cause to Predict Which Exception Type Will Be Caught

An `IllegalStateException` whose cause is an `IOException` is **not** caught directly by `catch (IOException)`. Handlers match on the type of the outer propagating exception, not by inspecting its cause.

### Pitfall 12 — Assuming Cause Is a Property Updatable from Multiple Places

The default design targets single initialization. Do not build error-dispatching systems that depend on "modifying the cause" multiple times.

### Pitfall 13 — Using `printStackTrace()` as Stable Machine-Readable Data

Stack traces are helpful for diagnostics but are not a stable formatting contract. Use structured APIs when building error observability systems.

### Pitfall 14 — Putting Secrets in the Message/Cause

Cause information may appear in stack traces, logs, and observability tools. Avoid putting tokens, passwords, personal data, or sensitive internal content in error messages.

### Pitfall 15 — Wrapping Exceptions Across Too Many Layers Without Adding Context

A long chain of identical wrappers increases investigation complexity. Wrap at meaningful boundaries, keeping the cause and a sufficiently specific message.

## 18. Self-Check Questions

1. How does a cause differ from a message?
2. What does `getCause()` return if no cause has been set?
3. Why is `getCause() == null` insufficient to conclude that `initCause(...)` is valid?
4. With `new Throwable()`, can `initCause(root)` be called once?
5. With `new Throwable("message", null)`, can `initCause(root)` be called?
6. With `new Throwable((Throwable) null)`, what is `getCause()`? Is the cause initialized yet?
7. Does `initCause(null)` allow a subsequent `initCause(root)` call?
8. Does `initCause` return a new object or the receiving object itself?
9. What are the two common runtime errors when misusing `initCause`, and what condition corresponds to each?
10. Does `getCause()` immediately return the deepest root exception or only one direct level?
11. Why should custom cause-chain traversal use an identity-based set?
12. Where does the `Throwable(Throwable cause)` constructor derive its message from?
13. Does passing a cause to a constructor change whether the outer class is checked or unchecked?
14. Does a suppressed exception automatically become a cause?
15. When is the `(String, Throwable)` constructor better than `initCause`?
16. When is `initCause` still useful in legacy code or for old API compatibility?
17. Why does the four-parameter protected constructor with a null cause still disallow calling `initCause` again?
18. If the outer exception already has a cause, might you still need to read `getStackTrace()` of the cause?
19. Does throwing the same exception twice automatically make `initCause` valid again?
20. Should a caller rely on `getCause().getMessage()` without checking `getCause() != null`?

### Suggested Answers

1. A message is descriptive text; a cause is a reference to the underlying `Throwable`.
2. `null`.
3. `null` can mean either uninitialized or initialized with `null`.
4. Yes, if the cause has not been initialized yet.
5. No, the constructor already initialized the cause to `null`.
6. The getter returns `null`, but the cause is already initialized.
7. No; attaching `null` also consumes the initialization right.
8. The receiving object itself.
9. `IllegalStateException` if the cause is already initialized; `IllegalArgumentException` if setting itself as its own cause.
10. Only one direct cause step.
11. To detect cycles by object reference rather than depending on `equals`.
12. `cause.toString()` when `cause` is non-null.
13. No; the classification of the outer exception depends on its own class.
14. No.
15. When the constructor is available and you want to create a complete object with context immediately.
16. When an exception class only has overloads without a cause parameter but allows attaching a cause once.
17. Because the four-parameter overload already initializes the cause, even with a `null` value.
18. Possibly yes, because the cause has its own stack trace.
19. No; `throw` does not reset the cause state.
20. No; the case where the cause is `null` must be handled.

## 19. Key Takeaways

**`getCause()` returns the direct cause reference, while `initCause(...)` only sets the cause when the `Throwable`'s cause state has never been initialized.** Constructors without a cause parameter may allow calling `initCause` once; constructors with a cause parameter have already decided the state even when `null` is passed. A second attempt to set the cause throws `IllegalStateException`; setting an exception as its own cause throws `IllegalArgumentException`. In new Java code, prefer constructors that accept both message and cause; use `initCause` when compatibility with error classes lacking an appropriate overload is required.
