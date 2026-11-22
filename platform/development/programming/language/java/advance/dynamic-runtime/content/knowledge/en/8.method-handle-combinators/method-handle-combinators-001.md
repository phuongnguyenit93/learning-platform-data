# 8.1 Creating Base Handles with constant, identity, empty, and throwException

## 1. Why Do We Need Base Handles?

In Java, a `MethodHandle` is an object representing a computation with a specific type signature, rather than necessarily always pointing to a method declared in a class. Alongside `Lookup.findStatic`, `findVirtual`, and member lookup operations, the `java.lang.invoke.MethodHandles` class provides factories that create basic operations to compose into a dynamic invocation flow.

All four factories in this lesson **create handles directly, without needing `MethodHandles.Lookup`**:

| Factory | Created handle signature | Behavior when invoked |
| --- | --- | --- |
| `constant(T.class, value)` | `()T` | Returns the same value attached when the handle was created. |
| `identity(T.class)` | `(T)T` | Returns the received argument as is. |
| `empty(MethodType.methodType(R.class, A...))` | `(A...)R` | Ignores arguments, returns the default value according to `R`; if `R=void`, does nothing. |
| `throwException(R.class, E.class)` | `(E)R` | Throws the passed-in exception object of type `E`; does not return normally. |

Here `T` is a **non-void** type; `R` can be a value type or `void`; `E` is a subclass of `Throwable`. These handles often serve as the building blocks for constant branches, pass-through data paths, no-ops, and error branches of a combinator graph.

### 1.1. Learning Objectives

After this lesson, you will know how to:

1. Accurately predict the `MethodType` and value of each factory.
2. Understand type conversion at `constant` creation time, default values of `empty`, and the nominal return type of `throwException`.
3. Invoke using `invokeExact` with matching input/output types, avoiding `WrongMethodTypeException`.
4. Combine `dropArguments`, `insertArguments`, and `guardWithTest` to build a dynamic invocation flow from base handles.
5. Recognize pitfalls with `void`, `null`, mutable objects, and reused exceptions.

## 2. Foundations: Distinguishing Factories, Signatures, and Invocations

Each handle has a `type()` method that returns a `MethodType`, i.e., a list of **parameter types in order** and a **return type**. Some forms:

```text
()String                      no inputs, returns String
(String)String                takes String, returns String
(String,long)int              takes String and long, returns int
(IllegalArgumentException)int takes exception, has nominal return type int
```

`MethodType.methodType(int.class, String.class, long.class)` represents the signature `(String,long)int`. This is the **handle's type**, not standard Java method declaration syntax.

`invokeExact(...)` is a signature-polymorphic call that requires the signature at the call site to **match the handle exactly**: same number of parameters, same parameter types, same return type. For example, `()int` only matches a context expecting `int` and **0 arguments**; you cannot pass an arbitrary argument to it.

Therefore:

```java
MethodHandle h = MethodHandles.constant(int.class, 5);
int number = (int) h.invokeExact();  // valid: ()int
// int wrong = (int) h.invokeExact(9);  // invalid: call site (int)int
```

The snippet illustrates code inside a method that has imported `MethodHandle`/`MethodHandles` and handles `Throwable`. If you uncomment the last line and run it, the invalid call usually throws `WrongMethodTypeException`.

In the full example, `main` declares `throws Throwable` because `invokeExact` can throw `Throwable`. Application code should have clear error-handling boundaries and not swallow all exceptions.

## 3. `MethodHandles.constant(type, value)` — Constant Handle

Example:

```java
MethodHandle ready = MethodHandles.constant(String.class, "READY");
// ready.type() is ()String
String text = (String) ready.invokeExact();  // READY
```

**Characteristics:**

- The created handle has **0 parameters** and return type `type`. Every normal invocation returns the same chosen value.
- The value is converted to `type` **at handle creation time**. For primitives, Java performs unboxing and attempts an appropriate widening primitive conversion: `constant(long.class, Integer.valueOf(7))` is valid and returns `7L`.
- For reference types, the value must be compatible with the required type; `constant(CharSequence.class, "hi")` is valid, whereas `constant(String.class, new StringBuilder("hi"))` does not convert `StringBuilder` to `String`.
- `constant(String.class, null)` is valid and returns `null`. Do not use `constant` to parse a string into a number.
- `constant(void.class, value)` throws `IllegalArgumentException`; `type == null` throws `NullPointerException`; a value that cannot be converted to the required type may throw `ClassCastException`.

### 3.1. A Reference Constant Does Not Mean an Immutable Object

A `StringBuilder` bound into `constant(StringBuilder.class, builder)` **is not cloned**. The handle returns the same reference. If other code mutates `builder`, subsequent invocations of the handle may observe the new contents. Therefore, if you want an immutable configuration, bind immutable data (e.g., `String`) or copy it yourself before binding. `constant` does not replace synchronization mechanisms for mutable objects across threads.

### 3.2. Use Adapters to Accept Additional Parameters

A `()String` handle does not automatically accept extra arguments. To ignore a `long id` while still always returning `"OK"`:

```java
MethodHandle base = MethodHandles.constant(String.class, "OK");
MethodHandle withId = MethodHandles.dropArguments(
        base, 0, long.class);
// withId.type(): (long)String
```

This is an illustrative snippet, not a standalone file. `dropArguments` **inserts dummy parameters** into the handle's signature; they are supplied by the caller but do not affect the result of `base`.

## 4. `MethodHandles.identity(type)` — Receive and Return the Input Itself

`identity(T.class)` creates a `(T)T` handle: exactly one parameter and one return value of the same type. There is no `value` parameter at creation time; the value is provided at **invoke** time.

```java
MethodHandle textId = MethodHandles.identity(String.class);
MethodHandle intId = MethodHandles.identity(int.class);
// textId.type() is (String)String
// intId.type() is (int)int
String text = (String) textId.invokeExact("hello");
int number = (int) intId.invokeExact(42);
```

Both invocations return the exact input value. For reference types, `identity` returns **the exact same object**, without copying or cloning; a `null` input is returned as `null`. For primitives, it returns the exact primitive value of the same type.

**You cannot use `identity(void.class)`** because `void` is not a Java parameter type; the factory throws `IllegalArgumentException`. If `type == null`, the factory throws `NullPointerException`.

### 4.1. When Should You Use It?

- An optional transform step is not configured: use identity as a **pass-through** path.
- A branch does not need to modify data but must provide a handle with signature `(T)T`.
- A predicate for a boolean condition: `identity(boolean.class)` has signature `(boolean)boolean` and returns the condition as is (used in section 8).

Do not confuse `identity` with `constant`. `constant(String.class, "X")` takes no input; `identity(String.class)` requires a String input when invoked. It also differs in API from Java generics' `Function.identity()`: both return the input, but one is a `MethodHandle` with runtime typing, while the other is a `java.util.function.Function`.

## 5. `MethodHandles.empty(methodType)` — Do Nothing While Matching the Signature

`empty(MethodType type)` creates a handle **with the exact specified signature**. When invoked, the handle **ignores parameter values**, performs no custom operation, and returns a default value based on the return type:

| Return type | Result of empty |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` of the corresponding type |
| `float`, `double` | `0.0f` or `0.0d` |
| `boolean` | `false` |
| `char` | NUL character, code 0 |
| Reference type such as `String`, `Object`, array | `null` |
| `void` | Completes normally, no result |

Example:

```java
MethodHandle zeroInt = MethodHandles.empty(
        MethodType.methodType(int.class, String.class, long.class));
// zeroInt.type() is (String,long)int

MethodHandle noText = MethodHandles.empty(
        MethodType.methodType(String.class, int.class));
// noText.type() is (int)String

MethodHandle noOp = MethodHandles.empty(
        MethodType.methodType(void.class, String.class));
// noOp.type() is (String)void
```

When calling `zeroInt` with `"unused"` and `99L`, the result is always `0`; `noText` returns `null`; `noOp` does nothing.

**Very important note:** Java still **evaluates argument expressions on the caller side** before invoking the handle. If an argument is `sideEffect()`, that side effect can occur even though `empty` does not use the value. Only the internals of the empty handle do nothing.

### 5.1. Relationship with `MethodHandles.zero`

`MethodHandles.zero(T.class)` (Java 9+) creates a `()T` handle that returns the **default value** of `T`. According to the Java 17 Javadoc, it is equivalent to `empty(MethodType.methodType(T.class))`. In general, `empty(type)` can be viewed as `zero(type.returnType())` with ignored parameters added via `dropArguments`.

Easily forgotten differences:

- `zero(void.class)` and `empty(methodType(void.class))` are **valid**.
- `constant(void.class, ...)` is **invalid**, because `constant` needs a value to return.
- `zero(int.class)` and `constant(int.class, 0)` produce the same result, but one factory creates the **default value** while the other takes a **caller-chosen value**.

### 5.2. Be Careful When Choosing a No-Op

`empty` is a good solution for an optional branch **that is allowed to do nothing**. However, it is not suitable if a missing handler should be treated as an error. In a pipeline, a `0`, `false`, or `null` result can be mistaken for success. When a state is invalid, a `throwException` branch may be more appropriate.

## 6. `MethodHandles.throwException(returnType, exType)` — A Branch That Always Throws

`throwException(R.class, E.class)` creates a handle of form **`(E)R`**, where `E extends Throwable`. It **takes an exception object** and **throws that exact object** when invoked; it does not create an exception itself.

```java
MethodHandle fail = MethodHandles.throwException(
        String.class, IllegalArgumentException.class);
// fail.type(): (IllegalArgumentException)String
```

`String` is the **nominal return type**; the handle never has a normal return path, whether this type is `String`, `int`, or `void`. The nominal return signature allows it to participate in a graph alongside a branch that returns type `R`.

**Difference between creation and invocation:**

- Calling the `throwException(...)` factory creates the handle; it does not throw the business exception.
- Calling `fail.invokeExact(problem)` throws **problem**, provided the call site has the exact signature `(IllegalArgumentException)String`.
- Because the actual parameter is an exception object, you control the type, message, and stack trace by creating the exception before invoking.
- `returnType` / `exType` must not be `null`; `exType` must be a subtype of `Throwable`.

### 6.1. Checked Exceptions Still Work

`throwException(void.class, IOException.class)` creates a `(IOException)void` handle. When invoked with an `IOException`, it throws that checked exception. The `void` type does not suppress the exception; it only describes the return type that the handle will **never reach**.

### 6.2. Composing a Throw Branch with `insertArguments`

If a `(boolean)String` branch needs to throw `IllegalStateException("disabled")` without taking an exception at the final call site, use:

1. `throwException(String.class, IllegalStateException.class)` creates `(IllegalStateException)String`.
2. `insertArguments(thrower, 0, exception)` binds the exception, creating `()String`.
3. `dropArguments(bound, 0, boolean.class)` creates `(boolean)String`, ready to compose with another branch.

You should not bind a mutable or stack-trace-sensitive exception and reuse it across all requests if per-invocation error details are needed. When an exception is pre-bound, each call may rethrow **the same object**, rather than a new exception with that request's stack trace.

If `null` is passed as the exception argument at invoke time, attempting to throw null produces a `NullPointerException`. This is not an error-reporting mechanism that should be used intentionally.

## 7. Runnable Java 17 Example: Four Factories in One Program

Create the file **`BaseHandlesDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BaseHandlesDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle fixed =
                MethodHandles.constant(String.class, "READY");
        MethodHandle wide =
                MethodHandles.constant(long.class, Integer.valueOf(7));
        MethodHandle textId = MethodHandles.identity(String.class);
        MethodHandle intId = MethodHandles.identity(int.class);
        MethodHandle ignored = MethodHandles.empty(
                MethodType.methodType(int.class, String.class, long.class));
        MethodHandle noText = MethodHandles.empty(
                MethodType.methodType(String.class, int.class));
        MethodHandle noOp = MethodHandles.empty(
                MethodType.methodType(void.class, String.class));
        MethodHandle fail = MethodHandles.throwException(
                String.class, IllegalArgumentException.class);

        System.out.println("constant type: " + fixed.type());
        System.out.println("constant: " + (String) fixed.invokeExact());
        System.out.println("widened: " + (long) wide.invokeExact());
        System.out.println("identity type: " + textId.type());
        System.out.println("identity text: "
                + (String) textId.invokeExact("hello"));
        System.out.println("identity int: " + (int) intId.invokeExact(42));
        System.out.println("empty type: " + ignored.type());
        System.out.println("empty int: "
                + (int) ignored.invokeExact("unused", 99L));
        System.out.println("empty reference null: "
                + ((String) noText.invokeExact(123) == null));

        noOp.invokeExact("discarded");
        System.out.println("empty void: returned normally");

        System.out.println("throw type: " + fail.type());
        IllegalArgumentException problem =
                new IllegalArgumentException("invalid");
        try {
            String result = (String) fail.invokeExact(problem);
            System.out.println("unreachable: " + result);
        } catch (IllegalArgumentException ex) {
            System.out.println("same exception object: " + (ex == problem));
            System.out.println("exception message: " + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 BaseHandlesDemo.java
java BaseHandlesDemo
```

Stdout:

```text
constant type: ()String
constant: READY
widened: 7
identity type: (String)String
identity text: hello
identity int: 42
empty type: (String,long)int
empty int: 0
empty reference null: true
empty void: returned normally
throw type: (IllegalArgumentException)String
same exception object: true
exception message: invalid
```

**Output explanation:**

- `fixed` takes no input; `wide` demonstrates converting an `Integer` wrapper to a primitive `long` when creating the constant.
- `textId` has `(String)String`; `intId` returns the primitive `int` as is.
- `ignored` accepts two values of types `String` and `long` but does not use them, returning `0`.
- `noText` returns `null` for reference type `String`; `noOp` has type `(String)void`.
- `fail` is created normally; **only the invocation** throws `IllegalArgumentException`. The expression `ex == problem` is `true` because it is the exact instance that was passed in.

The `javac --release 17` command is an example using Java 17-compatible APIs; `MethodHandles.empty` and `zero` have existed since Java 9. You need to run with a runtime that supports at least the APIs used.

## 8. Java 17 Example: Composing into a Dynamic Branch with `guardWithTest`

Use `identity(boolean.class)` as the condition, and `constant` for the branch values. Because constant has type `()String` while the graph accepts `boolean`, you must add a dummy parameter using `dropArguments`.

Create the file **`BaseCompositionDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class BaseCompositionDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle test = MethodHandles.identity(boolean.class);
        MethodHandle yes = MethodHandles.dropArguments(
                MethodHandles.constant(String.class, "ACCEPT"),
                0, boolean.class);
        MethodHandle no = MethodHandles.dropArguments(
                MethodHandles.constant(String.class, "REJECT"),
                0, boolean.class);
        MethodHandle choose = MethodHandles.guardWithTest(test, yes, no);

        System.out.println("choose type: " + choose.type());
        System.out.println("choose true: "
                + (String) choose.invokeExact(true));
        System.out.println("choose false: "
                + (String) choose.invokeExact(false));

        MethodHandle throwOne = MethodHandles.insertArguments(
                MethodHandles.throwException(
                        String.class, IllegalStateException.class),
                0, new IllegalStateException("disabled"));
        MethodHandle bad = MethodHandles.dropArguments(
                throwOne, 0, boolean.class);
        MethodHandle enforce =
                MethodHandles.guardWithTest(test, yes, bad);

        System.out.println("enforce true: "
                + (String) enforce.invokeExact(true));
        try {
            String value = (String) enforce.invokeExact(false);
            System.out.println("unreachable: " + value);
        } catch (IllegalStateException ex) {
            System.out.println("enforce false: " + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 BaseCompositionDemo.java
java BaseCompositionDemo
```

Stdout:

```text
choose type: (boolean)String
choose true: ACCEPT
choose false: REJECT
enforce true: ACCEPT
enforce false: disabled
```

### 8.1. Observing Handle Type Changes

```text
identity(boolean.class)                    : (boolean)boolean
constant(String.class,"ACCEPT")             : ()String
  + dropArguments(..., boolean.class)      : (boolean)String
constant(String.class,"REJECT")             : ()String
  + dropArguments(..., boolean.class)      : (boolean)String
guardWithTest(test, yes, no)               : (boolean)String

throwException(String, IllegalStateException): (IllegalStateException)String
  + insertArguments(..., exception)        : ()String
  + dropArguments(..., boolean.class)      : (boolean)String
guardWithTest(test, yes, bad)              : (boolean)String
```

- `test` takes `boolean` and returns `boolean`.
- `yes` and `no` both have signature `(boolean)String`, so they can be combined using `guardWithTest`.
- `throwOne` holds a bound `IllegalStateException`; `bad` has type `(boolean)String` but never returns `String` when selected.
- In `enforce`, `true` returns `ACCEPT`, and `false` throws an exception with the message `disabled`.

This is an example of **assembling an invocation flow at runtime**. For static `if/else` in ordinary Java, prefer simpler code if there is no need to generate/swap graphs at runtime.

## 9. Java 17 Example: Checking Type Boundaries and Immutability

Create the file **`BaseHandleEdgesDemo.java`**:

```java
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class BaseHandleEdgesDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle zero = MethodHandles.zero(int.class);
        MethodHandle empty = MethodHandles.empty(
                MethodType.methodType(int.class));
        System.out.println("zero and empty: "
                + ((int) zero.invokeExact() == (int) empty.invokeExact()));

        MethodHandle typedNull =
                MethodHandles.constant(String.class, null);
        System.out.println("typed null: "
                + ((String) typedNull.invokeExact() == null));

        StringBuilder buffer = new StringBuilder("A");
        MethodHandle captured =
                MethodHandles.constant(StringBuilder.class, buffer);
        buffer.append("B");
        System.out.println("same mutable object: "
                + (((StringBuilder) captured.invokeExact()) == buffer));
        System.out.println("current contents: "
                + ((StringBuilder) captured.invokeExact()).toString());

        try {
            MethodHandles.identity(void.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("identity void: rejected");
        }
        try {
            MethodHandles.constant(void.class, "ignored");
        } catch (IllegalArgumentException ex) {
            System.out.println("constant void: rejected");
        }

        MethodHandle fixed = MethodHandles.constant(int.class, 5);
        try {
            int value = (int) fixed.invokeExact(9);
            System.out.println(value);
        } catch (WrongMethodTypeException ex) {
            System.out.println("invokeExact signature: rejected");
        }

        IOException problem = new IOException("IO stopped");
        MethodHandle checked = MethodHandles.throwException(
                void.class, IOException.class);
        try {
            checked.invokeExact(problem);
        } catch (IOException ex) {
            System.out.println("checked same instance: "
                    + (ex == problem));
            System.out.println("checked message: " + ex.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 BaseHandleEdgesDemo.java
java BaseHandleEdgesDemo
```

Stdout:

```text
zero and empty: true
typed null: true
same mutable object: true
current contents: AB
identity void: rejected
constant void: rejected
invokeExact signature: rejected
checked same instance: true
checked message: IO stopped
```

**Key takeaways:**

- `zero(int.class)` and `empty(methodType(int.class))` both have `()int` and return `0`.
- `constant(String.class, null)` creates a `null` value with a specific reference type.
- `constant(StringBuilder.class, buffer)` does not copy `buffer`; changing its contents to `AB` is visible on subsequent invocations.
- Both `identity` and `constant` factories reject `void` at creation time.
- Passing argument `9` to `fixed` of type `()int` causes `WrongMethodTypeException` **at invoke time**.
- `throwException(void.class, IOException.class)` still throws the exact checked exception passed in, even though the return type is `void`.

## 10. Choosing the Right Factory and Adapter for Your Needs

| Problem | How to choose | What to avoid |
| --- | --- | --- |
| Branch always returns configuration `"OFF"` | `constant(String.class, "OFF")` | Do not invoke with arguments if you have not applied `dropArguments`. |
| Optional transform step does not modify input | `identity(T.class)` | Do not assume it clones mutable input. |
| Handler is not configured but allowed to be skipped | `empty(expectedMethodType)` | Do not use default `null`/`0` if business logic requires reporting an error. |
| Invalid branch must fail with an error | `throwException(R.class, E.class)` | Do not assume it instantiates the exception itself. |
| Function takes no input, returns default of type `T` | `zero(T.class)` or `empty(methodType(T.class))` | `constant(void.class,...)` cannot replace `zero(void.class)`. |
| Constant branch needs to accept dummy input | `dropArguments(constant(...),0,inputTypes...)` | Branch signatures must be aligned. |
| Error branch needs a fixed exception | `insertArguments(throwException(...),0,exception)` | Binding the same exception for every request can make debugging harder. |

### 10.1. Practical Scenarios

**Dynamic router/dispatcher:** if a route is disabled, the branch that returns an error code or throws an exception is built using a base handle with the same signature as an enabled route. However, if "disabled" is a business state that needs to be tracked in metrics, a typed error result may be better than throwing an exception.

**Transformer chain:** an inapplicable step can use `identity(String.class)` to preserve data instead of creating a `String passthrough(String s)` implementation.

**Schema/serialization:** `empty(MethodType)` can be used to produce a default value for an optional field. If the attribute is required, defaulting to `0`/`null` is unsafe; explicit validation or a throwing branch is needed.

**Dynamic runtime/DSL:** the factories create `return constant`, `pass input`, `no-op`, and `throw error` nodes so a graph can be linked/swapped at runtime. The advantage is expressing small behaviors using properly typed handles without defining many auxiliary Java methods.

## 11. Common Errors and How to Handle Them

| Error | Symptom / Reason | How to handle |
| --- | --- | --- |
| `constant(void.class, x)` or `identity(void.class)` | `IllegalArgumentException` at factory | Use `empty(methodType(void.class,...))` for a no-op. |
| `constant(int.class, "123")` | Does not parse string to primitive; may throw `ClassCastException` | Convert to a valid numeric wrapper before creating. |
| `constant(String.class, someStringBuilder)` | Value type cannot be cast to String | Use `CharSequence.class` or `someStringBuilder.toString()` as appropriate. |
| Attempting to call a `()T` handle with an argument | `WrongMethodTypeException` on `invokeExact` | Call with 0 arguments or use `dropArguments` to accept dummy input. |
| `invokeExact` call site has wrong return type | Signature mismatch even when parameter count is right | Add a cast/assignment matching `h.type()`; proactively use adapters when needed. |
| Assuming `empty` also prevents argument side effects | Caller's expressions are still evaluated | Do not pass expressions with side effects if you do not want them to run. |
| Using `empty` to signal a mandatory error | Downstream pipeline receives default `null`/`0` unaware of the error | Use `throwException` or an explicit error result. |
| Sharing a constant handle holding a mutable object | Multiple callers observe unintended mutations | Use an immutable value or defensive copy and manage thread-safety. |
| Assuming `throwException` instantiates the exception itself | Must pass an exception object at each invocation | Create a new one at the caller or intentionally bind with an adapter. |
| Combining branches with different signatures | `IllegalArgumentException` at combinator | Print `type()` and adjust with `dropArguments` / `insertArguments` / `asType` in a controlled manner. |

### 11.1. Distinguishing Error Timing

- **At factory:** invalid `void` type for `constant`/`identity`, unconvertible value, invalid `MethodType`.
- **At combinator:** incompatible signatures between branches.
- **At invocation:** `invokeExact` with wrong descriptor throws `WrongMethodTypeException`; `throwException` actually throws the passed-in object; `empty` returns the default.

Do not catch every `Throwable` and turn it into a generic message. Separate graph configuration errors, call-site type errors, and application exceptions actually raised by the branch.

## 12. Performance, Security, and Testing

**Performance:** base factories are generally suitable for caching/reusing in a stable graph, though there is no default guarantee that they are faster than regular Java methods or lambdas. The JIT can optimize a handle chain when eligible; measure real workloads with warmed-up benchmarks instead of a few `nanoTime()` calls. Avoid recreating many handles on the hot path if they can be prepared at bootstrap.

**Permissions and data:** these four factories do not require `Lookup` and do not grant access to private methods on their own. However, `constant` can hold sensitive objects, and `throwException` can hold exceptions containing sensitive information. Sharing a handle means sharing the ability to retrieve the bound value or receive the bound error. Reference lifetimes, thread-safety, and logging must be controlled.

**Testing:** assert both `type()` and the value/exception. A minimal test suite should cover primitive/reference/void types, null references, mutable objects, checked exceptions, mismatched `invokeExact` signatures, and a combinator with success/failure branches. Such tests define the contract more clearly than testing only a single output value.

## 13. Self-Check Questions

**1. Can `constant(int.class, 10)` accept a `String` parameter directly?**

No. Its signature is `()int`. Use `dropArguments(constant(int.class, 10), 0, String.class)` if you want a `(String)int` handle that ignores the String.

**2. How do `identity(String.class)` and `constant(String.class, "hello")` differ?**

Identity has signature `(String)String` and returns the input on each invocation; constant has `()String` and returns the value attached at creation time.

**3. Can you create `empty(methodType(void.class, int.class))`?**

Yes. The `(int)void` handle accepts `int` and completes normally. Conversely, `identity(void.class)` and `constant(void.class,...)` are invalid.

**4. What does `empty(methodType(boolean.class, String.class))` return when given `"yes"`?**

It returns `false`. It does not parse or inspect the string contents; it only returns the default for type `boolean`.

**5. Does `throwException(String.class, IOException.class)` actually create a String result?**

No. `String` is the handle's nominal return type for composing into a graph; when invoked, the handle throws the passed-in IOException object.

**6. Does `constant(StringBuilder.class, buffer)` guarantee the buffer contents will not change?**

No. It holds the same reference rather than cloning. Changes from elsewhere can show up on later invocations.

**7. Why must `dropArguments` be used before plugging a constant into a `(boolean)String` branch?**

Because the original constant is `()String`. The adapter adds an ignored `boolean` parameter, giving the new branch a signature compatible with the graph.

## 14. Key Takeaways

- **`constant(type,value)` → `()T`:** fixed result, type cannot be `void`, value is checked/converted at creation time.
- **`identity(type)` → `(T)T`:** single input, returns input as is, type cannot be `void`.
- **`empty(methodType)` → `(A...)R`:** accepts exact signature but ignores input, returns default or completes `void`.
- **`throwException(returnType,exType)` → `(E)R`:** takes a throwable and throws it, no normal return path; `R` is a nominal type.
- These factories **do not require `Lookup`**; signatures must be checked when using `invokeExact` and when composing combinators.
- Ensure business semantics when using defaults/null, mutable objects, or reused exceptions.

### Official Java SE 17 Documentation

- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `constant`, `identity`, `empty`, `zero`, `throwException`, `dropArguments`, `insertArguments`, and `guardWithTest`.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, and the signature-polymorphic model.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): parameter/return type representation.
