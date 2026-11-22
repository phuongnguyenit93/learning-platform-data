# 3.11. Distinguishing Lookup Errors, Argument Errors, Access Errors, and `InvocationTargetException`

Reflection allows Java to find classes, methods, constructors, and fields using information known only at runtime. A reflection call typically goes through several different steps: **find the member → check accessibility → validate receiver/arguments → execute target code**. Each step fails in a different way, so the same symptom of "reflection not working" can require a completely different fix.

This lesson distinguishes the four main error groups in `java.lang.reflect`, shows how to read the root cause, and builds a standalone compilable/runnable Java 17+ example.

## 1. Quick Map: Where Does the Error Originate?

| Group | Timing | Typical Exceptions | Meaning and Check Direction |
| --- | --- | --- | --- |
| **Lookup** | Do not have the right class/member yet | `ClassNotFoundException`; `NoSuchMethodException`; `NoSuchFieldException` | Name, signature, search scope, class loader |
| **Argument/receiver** | Already have `Method`/`Constructor`/`Field`, but passed data is unsuitable | `IllegalArgumentException`; `NullPointerException` | Argument count, types, receiver object, primitive/wrapper, how varargs are passed |
| **Access** | Member found, but caller is not allowed to use it | `IllegalAccessException`; `InaccessibleObjectException`; sometimes `SecurityException` | `public`/`private`, declaring class, module `exports`/`opens`, `setAccessible` |
| **Target code throws** | Call has entered the method/constructor | `InvocationTargetException` | Call `getCause()` to see the real exception from target code |

**Checked/unchecked distinction:**

- `ClassNotFoundException`, `NoSuchMethodException`, `NoSuchFieldException`, `IllegalAccessException`, and `InvocationTargetException` are **checked exceptions**. When calling the API directly, code must catch them or declare `throws`.
- `IllegalArgumentException`, `NullPointerException`, `InaccessibleObjectException`, and `SecurityException` are **unchecked exceptions**.
- `InstantiationException` is another checked exception from `Constructor.newInstance` when a type cannot be instantiated (for example, an abstract class); it is not synonymous with the four groups above.
- `ExceptionInInitializerError` is an `Error` caused by class initialization failure, which can arise separately from `Class.forName` or during class initialization; it is not automatically wrapped in `InvocationTargetException`.

The table describes **where errors typically occur**, without guaranteeing the order of every internal JVM check. If a call both has a wrong receiver and lacks access permission, fix each condition one by one and observe the actual error.

## 2. Lookup Group: Correct Class or Member Not Found Yet

These are errors that occur when reflection **has not yet obtained the metadata of the exact target to call**. Corresponding APIs and exceptions:

| Operation | Typical API | Exception |
| --- | --- | --- |
| Load binary name of a class | `Class.forName("pkg.Type")` | `ClassNotFoundException` |
| Find method by name and parameter types | `getMethod`, `getDeclaredMethod` | `NoSuchMethodException` |
| Find constructor by parameter types | `getConstructor`, `getDeclaredConstructor` | `NoSuchMethodException` |
| Find field by name | `getField`, `getDeclaredField` | `NoSuchFieldException` |

**There is no standard exception named `NoSuchConstructorException`.** A constructor with a mismatched signature still reports `NoSuchMethodException`.

### 2.1. `getMethod` and `getDeclaredMethod` Are Different

- `type.getMethod("run", String.class)` finds **public** methods, including matching inherited public methods (and from interfaces, according to API rules).
- `type.getDeclaredMethod("run", String.class)` only finds methods **declared directly on `type`**, but can find `private`/`protected`/package-private ones as well. It does **not** automatically search in superclasses.
- Finding a private method **does not mean permission to invoke it**. Invoking it can still fail with `IllegalAccessException`.
- Lookup signatures use **exact** names and parameter types: `int.class` is different from `Integer.class`; `String[].class` is different from `String.class`. The API does not automatically resolve overloads like a normal Java call; return type is not passed as a lookup criterion.

Illustrative example (placed in a context with the corresponding classes; not yet a standalone program):

```java
Class<?> type = SomeService.class;
Method m = type.getDeclaredMethod("process", int.class);

// If process declares an Integer parameter instead of int,
// getDeclaredMethod above will throw NoSuchMethodException.
```

Lookup errors often stem from: wrong name (including case), wrong overload, confusing `getMethod` with `getDeclaredMethod`, looking up a constructor with a different signature, a type loaded by a different class loader, or loading a class with an incorrect name. For inner/nested classes, the binary name has `$` between the enclosing class name and the inner class name; a safe way to get the name is `SomeNestedClass.class.getName()`.

`Class.forName(String)` can trigger class initialization by default. If the class name **exists but the static initializer fails**, the error can be `ExceptionInInitializerError`; that is **not** `ClassNotFoundException`. When needing to defer initialization, consider `Class.forName(name, false, loader)`.

### 2.2. How to Handle Lookup Errors

Log the class name, member name, list of parameter `Class<?>` objects, and the class loader being used. If you see `NoSuchMethodException`, compare the expected signature with the actual declared signature, and check `public` vs. `declared` scope. Calling `setAccessible(true)` **cannot solve** the situation where the method has not been found.

Do not automatically replace `getDeclaredMethod` with `getMethod` (or vice versa) just to "make the error go away"; the API choice must reflect the intended contract. For library APIs, a signature/version change can be the real cause.

## 3. Argument Group: Member Found, but Passed Data Is Wrong

Once you have a valid `Method` or `Constructor` object, calling `invoke`/`newInstance` still requires the right receiver and arguments. Common errors:

1. **Wrong number of arguments:** the method requires two parameters, but `invoke` receives one or three.
2. **Wrong argument type:** passing an `Integer` to a `String` parameter; or passing a type that cannot be converted under invocation rules.
3. **Wrong receiver:** using an object that is not an instance of the class declaring the instance method.
4. **`null` receiver for an instance method:** `Method.invoke(null, ...)` throws `NullPointerException`. For **static methods**, the receiver is unused and can be `null`.
5. **Confusing `Object...` spreading of `Method.invoke`** with an array parameter of the target method itself.

Illustrative example:

```java
Method echo = Example.class.getMethod("echo", String.class);
Example service = new Example();

echo.invoke(service, "Java"); // OK
echo.invoke(service, 42);     // IllegalArgumentException: wrong type
echo.invoke(service);         // IllegalArgumentException: missing argument
echo.invoke(null, "Java");    // NullPointerException: missing receiver instance
```

Here `Example` is assumed to have a public method `String echo(String text)`; this snippet is illustrative code.

**Conversion note:** Reflection supports certain valid invocation conversions such as *unboxing* and *widening primitive* (for example, an `Integer` argument for a `long` parameter), but it does not perform narrowing primitive conversions like `long` to `int`, does not automatically convert `"42"` to a number, and does not turn `Integer` into `String`. Therefore, you must not conclude that every primitive/wrapper difference causes an error, nor assume that reflection will convert any type.

### 3.1. Special Trap: Arrays and Varargs of `Method.invoke`

`Method.invoke` declares its last parameter as `Object... args`. If **the target method itself** takes a `String[]`, you must ensure that array becomes **a single argument**, not spread by Java into multiple reflection arguments:

```java
Method accept = Example.class.getMethod("accept", String[].class);

// Correct: cast the array to an Object so invoke receives exactly one argument.
accept.invoke(service, (Object) new String[] {"A", "B"});

// Avoid passing String[] directly in invoke's varargs position:
// accept.invoke(service, new String[] {"A", "B"});
// Java may treat the array elements as multiple arguments to invoke.
```

The example assumes `Example` has `public void accept(String[] values)`. `Method.invoke` does not automatically "spread varargs" the way a direct call to the target method does; the number of arguments Java reflectively passes must still match the target method signature.

### 3.2. Fields and Constructors Also Have Argument Errors

- `Field.get(receiver)` and `Field.set(receiver, value)` can report `IllegalArgumentException` if the receiver/value is unsuitable; for an instance field and a `null` receiver, they can report `NullPointerException`. Static fields do not use a receiver.
- `Constructor.newInstance(args)` reports `IllegalArgumentException` for a mismatched argument list; if the constructor does not exist, `getDeclaredConstructor(...)` reports `NoSuchMethodException` **beforehand**.
- `Constructor.newInstance` can also report `InstantiationException` if the type cannot be instantiated, such as an abstract class. This error is not an argument error and does not mean the constructor ran and threw an exception.

**Key point:** An `IllegalArgumentException` thrown **directly from `Method.invoke`** usually indicates a wrong reflection call; an `IllegalArgumentException` thrown **inside the target method** appears to the reflection caller as an **`InvocationTargetException` whose cause is `IllegalArgumentException`**. Looking only at the root exception class name while ignoring the wrapper will easily lead to misdiagnosis.

## 4. Access Group: Exists, but Not Allowed to Call

Java checks access permissions when using reflection. The state of the **declaring class**, member, package/module, and caller can all be involved.

### 4.1. `IllegalAccessException` When the Operation Is Denied

Methods such as `Method.invoke`, `Constructor.newInstance`, `Field.get`, and `Field.set` can throw **checked `IllegalAccessException`** if the caller lacks access permission under language/module rules. Obtaining metadata via `getDeclaredMethod` does not automatically bypass that permission.

`AccessibleObject.canAccess(receiver)` (Java 9+) can check current usage permission; calling it requires passing a valid receiver for an instance member, and `null` for a static member. If the receiver is wrong, `canAccess` itself can throw `IllegalArgumentException`.

Illustrative example:

```java
Method hidden = Example.class.getDeclaredMethod("hidden");
boolean allowed = hidden.canAccess(service); // may be false

// If hidden is private and the caller is outside the accessible scope:
hidden.invoke(service); // IllegalAccessException
```

### 4.2. `setAccessible`, `trySetAccessible`, and JPMS

`setAccessible(true)` requests bypassing certain Java access checks, **but it does not have an unbreakable right to open everything**.

- `member.trySetAccessible()` returns `true` if accessibility can be enabled; if restricted by a module and cannot be opened, it typically returns `false`.
- `member.setAccessible(true)` can throw **unchecked `java.lang.reflect.InaccessibleObjectException`** when the JVM does not allow opening that member.
- `IllegalAccessException` typically appears at the time of **using** an unpermitted member. `InaccessibleObjectException` typically appears at the time of **attempting to open** access via `setAccessible(true)`.
- Under the Java Platform Module System (JPMS), `exports` allows other modules to use the public API of a package as declared; `opens` allows *deep reflection* to non-public members as declared. A package that is only `exports` does not automatically allow `setAccessible(true)` on all private members.
- `SecurityException` remains a type of security error that can arise from certain APIs in environments with appropriate permission-checking policies; it should not be equated with `IllegalAccessException`.

For your own code, prefer public APIs or design the module with `opens package.name to consumer.module;` when frameworks genuinely need to reflect into internals. Depending on the environment, the runtime option `--add-opens module/package=target` can help with experimenting/running applications when the module descriptor cannot be edited; do not treat this as the default fix for production design.

`setAccessible(true)` also does not turn a non-existent member into an existing one, does not fix wrong arguments, and does not guarantee that every `final` field can be modified.

## 5. `InvocationTargetException`: Target Code Ran and Threw an Error

Representative reflection API signatures:

```java
Object result = someMethod.invoke(receiver, arguments);
Object created = someConstructor.newInstance(arguments);
```

If **the invoked method or constructor itself** throws a `Throwable`, the reflection API wraps that error in a **checked `InvocationTargetException`**. The purpose is to distinguish business exceptions of the target code from setup errors of the reflection call.

```java
try {
    someMethod.invoke(receiver, arguments);
} catch (InvocationTargetException wrapper) {
    Throwable actual = wrapper.getCause(); // actual error from target code
    System.err.println("Target threw: " + actual);
    // Here, decide how to report/propagate actual according to the application contract.
}
```

- `getCause()` returns the original exception. `getTargetException()` is the older API with equivalent meaning; in new code, `getCause()` is usually chosen.
- The original exception can be `IOException`, `IllegalArgumentException`, `NullPointerException`, any `RuntimeException`, or even an `Error`. Do not just log "`InvocationTargetException`" and lose the stack trace/cause.
- **Same `IllegalArgumentException` type but different stage:** if arguments passed to `invoke` are wrong, the API throws `IllegalArgumentException` directly; if the method runs and throws `IllegalArgumentException` itself, the caller receives `InvocationTargetException` with cause `IllegalArgumentException`.
- When a constructor throws an error itself, `Constructor.newInstance` also wraps it in `InvocationTargetException`.
- `Field.get`/`Field.set` do not execute a target method/constructor, so these two operations themselves do not use `InvocationTargetException` to wrap a business call.
- `ExceptionInInitializerError` during class initialization and certain other JVM errors can arise outside the wrapper; do not force every reflection error into the `InvocationTargetException` group.

Avoid simply doing `catch (Exception e)` and returning `null` or printing only `e.getMessage()`: that loses stage information and the root cause.

## 6. Complete Java 17+ Example

Save the **entire** snippet below as `ReflectionFailureGuide.java`. Two top-level classes in the same file are valid because only `ReflectionFailureGuide` is declared `public`; `SampleService` is intentionally separated so that invoking a private method from `ReflectionFailureGuide` undergoes access checking (not a Java nestmate).

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFailureGuide {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<SampleService> type = SampleService.class;
        SampleService service = new SampleService();

        // 1. Method, field, or constructor not found.
        try {
            type.getDeclaredMethod("missing");
        } catch (NoSuchMethodException e) {
            System.out.println("lookup.method: " + e.getClass().getSimpleName());
        }

        try {
            type.getDeclaredField("missing");
        } catch (NoSuchFieldException e) {
            System.out.println("lookup.field: " + e.getClass().getSimpleName());
        }

        try {
            type.getDeclaredConstructor(String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup.constructor: " + e.getClass().getSimpleName());
        }

        // 2. Method found, but arguments or receiver are wrong.
        Method echo = type.getMethod("echo", String.class);
        try {
            echo.invoke(service, 42);
        } catch (IllegalArgumentException e) {
            System.out.println("argument: " + e.getClass().getSimpleName());
        }

        try {
            echo.invoke(null, "Java");
        } catch (NullPointerException e) {
            System.out.println("receiver: " + e.getClass().getSimpleName());
        }

        // 3. Private method found, but not allowed to invoke.
        Method hidden = type.getDeclaredMethod("hidden");
        System.out.println("access.canAccess: " + hidden.canAccess(service));
        try {
            hidden.invoke(service);
        } catch (IllegalAccessException e) {
            System.out.println("access: " + e.getClass().getSimpleName());
        }

        // 4. Valid arguments, target code throws IllegalArgumentException itself.
        Method explode = type.getMethod("explode");
        try {
            explode.invoke(service);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("target.method: " + e.getClass().getSimpleName()
                    + " -> " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        // 5. Constructor runs and throws IllegalStateException itself.
        Constructor<SampleService> ctor = type.getDeclaredConstructor(int.class);
        try {
            ctor.newInstance(1);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("target.constructor: " + e.getClass().getSimpleName()
                    + " -> " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        // 6. A valid call for comparison.
        System.out.println("success: " + echo.invoke(service, "Java"));
    }
}

class SampleService {
    public SampleService() {}

    public SampleService(int value) {
        throw new IllegalStateException("ctor failed");
    }

    public String echo(String text) {
        return "Hello " + text;
    }

    private void hidden() {}

    public void explode() {
        throw new IllegalArgumentException("from method");
    }
}
```

In the directory containing the file, run:

```bash
javac --release 17 ReflectionFailureGuide.java
java ReflectionFailureGuide
```

Expected `stdout`:

```text
lookup.method: NoSuchMethodException
lookup.field: NoSuchFieldException
lookup.constructor: NoSuchMethodException
argument: IllegalArgumentException
receiver: NullPointerException
access.canAccess: false
access: IllegalAccessException
target.method: InvocationTargetException -> IllegalArgumentException: from method
target.constructor: InvocationTargetException -> IllegalStateException: ctor failed
success: Hello Java
```

**Line-by-line output explanation:**

1. The three `lookup.*` lines are produced before having the corresponding Method/Field/Constructor. A non-existent method, a non-existent field, and a constructor with a wrong signature are three separate lookup errors.
2. `argument`: `echo(String)` was found, but `42` is an `Integer` and cannot replace `String`. `receiver`: an instance method does not accept a `null` receiver.
3. `access.canAccess: false` and `access: IllegalAccessException`: `hidden()` is private to another top-level class. `getDeclaredMethod` retrieves the metadata but does not grant invocation permission.
4. `target.method`: `explode()` actually ran and threw `IllegalArgumentException("from method")` itself. Reflection wrapped that exception. Thus, even though both the `argument` line and the `target.method` line contain "`IllegalArgumentException`", **the failure point is completely different**.
5. `target.constructor`: `SampleService(int)` started running and threw `IllegalStateException` itself; `Constructor.newInstance` returns the error as `InvocationTargetException`.
6. `success`: with the right signature, receiver, access permission, and arguments, the call returns `Hello Java`.

The example above uses classes in the default package so it can be run with two commands; when moving into a project, place both classes in appropriate packages. If you put them into **different modules**, `exports`/`opens` conditions and actual access permissions may change the outcome.

## 7. How to Design Error Handling in Applications

An adapter layer that runs plugins or calls APIs via reflection should define boundaries for each operation and log enough context so operators know **whether the right member was found, whether it is permitted to use, whether the data is suitable, and whether the target code had started running**.

Recommended process:

1. **Lookup:** identify the appropriate class loader; load `Class<?>` and look up the member by exact name/signature. If not found, clearly report the class and signature; distinguish public APIs from `declared` members.
2. **Access:** use public APIs when possible. If deep reflection is needed, check `canAccess`/`trySetAccessible` and module configuration, handling `InaccessibleObjectException` separately.
3. **Argument validation:** match the receiver against `getDeclaringClass()` and parameter types from `getParameterTypes()`; check argument count and primitive/wrapper/array conversions. Do not log sensitive values if unnecessary.
4. **Invoke:** call `Method.invoke` or `Constructor.newInstance`. Catch `IllegalAccessException`, `IllegalArgumentException` (and `NullPointerException` when appropriate), and `InvocationTargetException` separately.
5. **Unwrap target failure:** retrieve `InvocationTargetException.getCause()`, preserving the cause and stack trace; classify business errors, retryable errors, and programming errors according to the module's contract. Do not blindly retry a method with side effects because it **may have already executed partially before throwing**.

Handling skeleton example (illustrated inside a method that already has variables `method`, `receiver`, and `args`; not a standalone program):

```java
try {
    Object result = method.invoke(receiver, args);
    // Handle result.
} catch (IllegalAccessException e) {
    // Missing access permission: check visibility and opens/exports.
    throw new IllegalStateException("Reflection access denied", e);
} catch (IllegalArgumentException e) {
    // Wrong receiver/arity/argument type before executing target code.
    throw new IllegalArgumentException("Invalid reflective invocation", e);
} catch (InvocationTargetException e) {
    Throwable cause = e.getCause();
    // Target code ran; preserve cause and decide how to report the error according to the contract.
    throw new IllegalStateException("Target execution failed", cause);
}
```

At a real API boundary, if the target error is a checked business exception that needs to be preserved or mapped to a business response, design the corresponding signature/exception mapping. The example above wrapping into `IllegalStateException` is only **an illustrative policy**, not a mandatory handling approach. If `cause` is a serious `Error`, the application needs an appropriate propagation policy rather than always converting it into a recoverable business error.

### 7.1. Diagnostic Information to Record

When an error is unclear, the following information is usually sufficient to isolate it without dumping entire objects:

- Binary name of the class and class loader, method/constructor/field name, signature from `getParameterTypes()`.
- Member kind (`static` or instance), receiver type, argument count, and runtime type of each argument (actual values can be masked).
- Module/package name of the declaring class, access status, and `exports`/`opens` requirements.
- **Outermost** exception type name, stack trace, and the **cause** of `InvocationTargetException` if present.

For example, if logging "`NoSuchMethodException: execute(java.lang.Integer)`", check whether the method declares `execute(int)` or `execute(Integer)`; if logging "`InvocationTargetException` → `IOException`", investigate the code and dependencies that the target method uses, do not change the reflection signature.

## 8. Easily Misdiagnosed Cases

| Symptom | Correct Explanation | Do Not Conclude |
| --- | --- | --- |
| `getDeclaredMethod` finds a private method, but `invoke` fails | Lookup succeeded; access failed | "Wrong method name" |
| `setAccessible(true)` throws `InaccessibleObjectException` | Package/module does not allow deep reflection in the current context | "Method does not exist" |
| `invoke` throws `IllegalArgumentException` directly | Check receiver/arity/arguments of the reflection call | "Target method's logic threw this error itself" |
| `invoke` throws `InvocationTargetException` with cause `IllegalArgumentException` | Target code started and threw the error itself | "Arguments passed to `invoke` definitely have the wrong type" |
| `newInstance` throws `InvocationTargetException` | Constructor threw an error during execution | "Constructor not found" |
| `getDeclaredConstructor(...)` throws `NoSuchMethodException` | No constructor matching that signature on that class | "Constructor threw an exception itself" |
| `Class.forName` throws `ExceptionInInitializerError` | Class initialization failed (static initializer) | "Just rename the class" |
| `Field.set` fails when the field is `final` | Field access/write restriction, depending on field kind and context | "This is an InvocationTargetException" |
| Two classes have the same name, but type check fails | Need to check class loaders and actual type identity | "Same name means always compatible" |

**Note on ordering:** If a call is both inaccessible and has invalid arguments, do not build application logic that depends on the JVM reporting one specific error type first. Check each condition and adjust each cause one by one.

## 9. Self-Check Exercises

**Scenario A:** `type.getMethod("calculate", Integer.class)` throws `NoSuchMethodException`, but the source defines `public int calculate(int n)`. Why? What is the right fix?

**Scenario B:** `getDeclaredMethod("secret")` returns a `Method` successfully, but `invoke` throws `IllegalAccessException`. What do you need to check before trying deep reflection?

**Scenario C:** `Method.invoke` throws `InvocationTargetException` and `getCause()` is `NullPointerException`. Where is this NPE?

**Scenario D:** A plugin call inserts a record into the database and then throws `InvocationTargetException`. Should you retry calling it immediately without inspecting the cause, transaction, or side effects?

**Answers:**

- **A:** Reflection looks up exact parameter signatures; `Integer.class` is different from `int.class`. If the contract is `calculate(int)`, look it up using `int.class`.
- **B:** Check access permissions of the declaring class, member, caller, and package/module; use `canAccess` to confirm status, design a public API, or intentionally open the package if needed.
- **C:** The target method ran and threw the NPE (or a helper inside it threw the NPE); analyze the stack trace of `getCause()`. In contrast, `invoke` with a `null` receiver for an instance method can throw NPE **directly**.
- **D:** No. The method may have already produced side effects before failing. You must inspect the cause and idempotency/transaction behavior before deciding to retry.

**Takeaway:** **Not found → lookup error; found but called with wrong data → argument error; found but not permitted → access error; entered target code and that code threw an error → `InvocationTargetException` with `getCause()`.** Looking at the right stage leads to the right fix.
