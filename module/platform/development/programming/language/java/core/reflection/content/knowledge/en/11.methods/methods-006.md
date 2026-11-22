# Invoking static methods with a `null` receiver via Java Reflection

## 1. The meaning of the receiver in `Method.invoke`

In Java Reflection, a `java.lang.reflect.Method` object represents a method and allows invoking it at runtime using the API:

```java
Object result = method.invoke(receiver, arg1, arg2);
```

The API signature is:

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
```

There are **two distinct roles** in the call:

- `obj` (or `receiver`): the object on which an **instance** method will execute.
- `args`: the **actual arguments** passed into the method, in the exact declared order.

For a **`static`** method, the call is not tied to a specific instance. Under the contract of `Method.invoke`, the `obj` parameter **is ignored and may be `null`**. Therefore, the clearest and most idiomatic call is:

```java
Method method = Example.class.getDeclaredMethod("hello");
method.invoke(null); // Calls Example.hello() if the method is static and accessible
```

Here `null` is the **receiver**, not the first argument of `hello()`. The example above assumes an `Example` class and a no-argument `hello()` method exist.

**Direct conclusion:** `method.invoke(null, ...)` is the normal way to invoke a `static` method; there is no need to create an object via `new Example()` beforehand.

## 2. Why does `static` accept a `null` receiver while instance methods do not?

Consider two kinds of methods:

```java
class Demo {
    static String staticHello() {
        return "static";
    }

    String instanceHello() {
        return "instance";
    }
}
```

Normal Java expressions:

```java
Demo.staticHello();             // Does not need an instance
new Demo().instanceHello();     // Needs an instance
```

Correspondingly in Reflection:

```java
Method staticMethod = Demo.class.getDeclaredMethod("staticHello");
String a = (String) staticMethod.invoke(null);

Method instanceMethod = Demo.class.getDeclaredMethod("instanceHello");
String b = (String) instanceMethod.invoke(new Demo());
// instanceMethod.invoke(null); // Throws NullPointerException
```

These are **illustrative snippets** placed in a context that handles checked exceptions, such as a `main` method declaring `throws Exception`.

For an instance method, `receiver` must be an instance compatible with the class/interface declaring the method. If the receiver is `null`, `Method.invoke` throws `NullPointerException`; if it is an object of the **wrong type**, it throws `IllegalArgumentException`.

For a `static` method, the runtime does not look up an instance object to run the method. Even if a non-`null` object is passed, Reflection **ignores that object**. For instance, `staticMethod.invoke(new Object())` still calls the static method, provided access and arguments are valid. However, **you should pass `null`** to express the exact intent: no instance is needed.

| Reflected method | Passed receiver | Receiver outcome |
| --- | --- | --- |
| `static` | `null` | Valid; no object needed |
| `static` | Non-`null` object, even of an unrelated type | Ignored |
| Instance | Object of compatible type | Callable; still depends on access/arguments |
| Instance | `null` | `NullPointerException` |
| Instance | Object that is not a compatible instance | `IllegalArgumentException` |

The table only addresses the **receiver**; a successful invocation also requires matching parameter count/types, access permissions, and no errors occurring during execution.

## 3. Identifying a `static` method before invoking

When handling dynamically discovered `Method` objects, use:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

boolean isStatic = Modifier.isStatic(method.getModifiers());
```

`Method.getModifiers()` returns the method's modifier flags. `Modifier.isStatic(...)` checks the `static` flag. This is the clean way to decide the receiver needed by Reflection:

```java
Object receiver = Modifier.isStatic(method.getModifiers())
        ? null
        : existingInstance;
Object result = method.invoke(receiver, args);
```

This is a **code pattern**: `method`, `existingInstance`, and `args` must be defined beforehand. For an instance method, ensure `existingInstance` is of the right type. If the caller has no instance yet the method is not static, do not assume you can pass `null`.

### How to get the right `Method`

- `SomeClass.class.getMethod("name", ParamType.class)` searches for a `public` method by name and **parameter types**, including inherited public methods per API rules.
- `SomeClass.class.getDeclaredMethod("name", ParamType.class)` searches for a method declared **directly** in that class/interface, even if non-`public`, but does not automatically search superclasses.
- Both return `Method` and can throw `NoSuchMethodException` when the name/signature does not match.
- When overloads exist, you must select the exact `Class<?>` values of the parameter types. `getDeclaredMethod("add", int.class, int.class)` differs from `getDeclaredMethod("add", Integer.class, Integer.class)`.

`getDeclaredMethod` does not automatically grant permission to call a `private` method. For a `private static` method, **a `null` receiver is still valid**, but access can be blocked by Java access control / JPMS. Use `trySetAccessible()` in a controlled manner if deep access is genuinely needed.

## 4. Complete Java 17+ example

Save the entire program to **`StaticReceiverDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class StaticReceiverDemo {
    public static String greet(String name) {
        return "Hi " + name;
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void ping() {
        System.out.println("ping");
    }

    public static String join(String[] values) {
        return String.join("-", values);
    }

    public static void fail() {
        throw new IllegalStateException("failure");
    }

    public String instanceHello() {
        return "instance";
    }

    public static void main(String[] args) throws Exception {
        Class<StaticReceiverDemo> type = StaticReceiverDemo.class;

        Method greet = type.getMethod("greet", String.class);
        System.out.println("null receiver: "
                + greet.invoke(null, "Lan"));
        System.out.println("ignored receiver: "
                + greet.invoke(new Object(), "Minh"));
        System.out.println("is static: "
                + Modifier.isStatic(greet.getModifiers()));

        Method add = type.getMethod("add", int.class, int.class);
        Object sum = add.invoke(null, 3, 4);
        System.out.println("sum: " + sum
                + ", type: " + sum.getClass().getSimpleName());

        Method ping = type.getMethod("ping");
        Object noResult = ping.invoke(null);
        System.out.println("void result is null: "
                + (noResult == null));

        Method join = type.getMethod("join", String[].class);
        System.out.println("join: "
                + join.invoke(null, (Object) new String[] {"red", "blue"}));

        try {
            // Intentionally pass 2 arguments instead of 1 String[] argument.
            join.invoke(null, (Object[]) new String[] {"red", "blue"});
        } catch (IllegalArgumentException e) {
            System.out.println("spread array: IllegalArgumentException");
        }

        Method instance = type.getMethod("instanceHello");
        try {
            instance.invoke(null);
        } catch (NullPointerException e) {
            System.out.println("instance null: NullPointerException");
        }

        Method fail = type.getMethod("fail");
        try {
            fail.invoke(null);
        } catch (InvocationTargetException e) {
            System.out.println("target failure: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run in the file's directory:

```bash
javac StaticReceiverDemo.java
java StaticReceiverDemo
```

**Exact stdout:**

```text
null receiver: Hi Lan
ignored receiver: Hi Minh
is static: true
sum: 7, type: Integer
ping
void result is null: true
join: red-blue
spread array: IllegalArgumentException
instance null: NullPointerException
target failure: IllegalStateException
```

**Program analysis:**

1. `greet.invoke(null, "Lan")` calls `greet` even without a `StaticReceiverDemo` instance, because the method has the `static` modifier.
2. `greet.invoke(new Object(), "Minh")` also succeeds: `new Object()` is an **ignored** receiver. This works, yet is misleading; in real code, use `null`.
3. `Modifier.isStatic(greet.getModifiers())` identifies the method kind correctly, returning `true`.
4. `add.invoke(null, 3, 4)` passes two `int` arguments (placed into the `Object...` array and boxed by Java). Reflection automatically converts `Integer` back to `int` when calling. `Method.invoke` returns `Object`, so the primitive `int` result is **boxed** back into `Integer`.
5. `ping` has return type `void`: the method body prints `ping`, then `invoke` returns `null`.
6. `join(String[])` accepts **one** array parameter. The `(Object)` cast passes the array as a single argument to `Method.invoke`.
7. The `(Object[])` cast in the error branch causes the array's elements to be treated as **two** arguments to `invoke`'s varargs; `join` takes only **one** parameter so Reflection throws `IllegalArgumentException`.
8. `instanceHello` lacks the `static` modifier; calling it with a `null` receiver throws `NullPointerException`.
9. `fail` executes and throws `IllegalStateException`. Reflection wraps the target method's error in `InvocationTargetException`; `getCause()` returns the root cause.

## 5. Distinguishing a `null` receiver from a `null` parameter

`Method.invoke` has two parameter "layers":

```java
method.invoke(obj, args...);
              ^    ^
              |    +-- arguments of the target method
              +------- receiver of the invoke call
```

Given the method:

```java
public static String describe(String text) {
    return text == null ? "<null>" : text;
}
```

Look up the `Method` and invoke it:

```java
Method describe = Example.class
        .getMethod("describe", String.class);

Object a = describe.invoke(null, (Object) null);
```

This is an **illustrative snippet**, not a standalone file. `Example` must have the `describe` method declared above.

In `describe.invoke(null, (Object) null)`:

- The first `null` is the receiver, ignored because `describe` is static.
- The second `(Object) null` is **one `String` argument with value `null`**, so the call is valid.
- The result is the string `"<null>"`.

A quirk of varargs `Object... args`: `describe.invoke(null, (Object[]) null)` passes a **`null` argument array**, which is treated as **passing zero arguments**. Since `describe` requires exactly one parameter, this causes `IllegalArgumentException` due to wrong argument count. Similarly, `describe.invoke(null, new Object[0])` is a call with zero target arguments, not one `null` argument.

Avoid writing `describe.invoke(null, null)` when the intent is to pass one `null` argument; Java may treat the trailing `null` as a null varargs array and the compiler warns about a non-varargs call. Explicitly write `(Object) null` or `new Object[] {null}`.

| Intent | Clear syntax |
| --- | --- |
| Static method with no parameters | `method.invoke(null)` |
| Static method taking one String `"a"` | `method.invoke(null, "a")` |
| Static method taking one parameter with value `null` | `method.invoke(null, (Object) null)` |
| Static method taking one `String[]` array parameter | `method.invoke(null, (Object) new String[] {"a", "b"})` |
| Static method taking two `int` parameters | `method.invoke(null, 1, 2)` |

**A `null` receiver and a `null` parameter are two completely different decisions.** Do not confuse a receiverless call with a method receiving a null input.

## 6. Why do array parameters easily cause errors?

`Method.invoke` is declared to accept `Object... args`; in Java terms, this is a variant of an `Object[]` array containing the actual arguments. That is **not identical** to a varargs declaration on the **target method**.

For example, even if the target method accepts exactly one `String[]`, when writing:

```java
Method m = SomeClass.class.getMethod("process", String[].class);
String[] input = {"x", "y"};

m.invoke(null, (Object) input);           // 1 String[] argument: valid
m.invoke(null, new Object[] {input});     // 1 String[] argument: valid
// m.invoke(null, (Object[]) input);      // 2 String arguments: invalid
```

This is an illustrative snippet assuming `SomeClass` has a public static method `process(String[])`, not a standalone program.

- `(Object) input` prevents the `String[]` array from being **spread** into multiple elements of `invoke`'s varargs.
- `new Object[] {input}` explicitly represents an array **containing one argument**, and that argument is the `String[]` array.
- `(Object[]) input` turns the `String[]` array into the varargs array passed to `invoke`, causing Reflection to see each String element as **a separate argument**.
- Do not infer from `m.isVarArgs()` that `Method.invoke` will automatically pack arguments into an array for the target method. Reflection requires providing an argument array matching the formal parameter count and types.

This is an **`args` packaging** error; it is unrelated to the validity of `receiver = null`.

## 7. Access conditions still apply to static methods

A `null` receiver **does not** mean bypassing Java access control.

Example:

```java
class Secrets {
    private static String token() {
        return "hidden";
    }
}
```

`Secrets.class.getDeclaredMethod("token")` can return the `Method` object, yet a caller from a class/package/module **without sufficient permissions** can encounter `IllegalAccessException` when calling `invoke(null)`. If deep reflection is needed, use:

```java
Method method = Secrets.class.getDeclaredMethod("token");
if (method.trySetAccessible()) {
    Object value = method.invoke(null);
}
```

This is an illustrative snippet requiring handling of checked exceptions. Whether `trySetAccessible()` returns `true` depends on the caller, Java permissions, and JPMS; success is not guaranteed when the named module's package is not open to the caller. `setAccessible(true)` can throw `InaccessibleObjectException` if module boundaries forbid the request.

Distinguish three layers of concerns:

1. **Method kind:** `static` allows a `null` receiver.
2. **Access rights:** whether the caller is allowed to invoke the method (or request suppressing access checks).
3. **Arguments:** whether the target parameter count and types are compatible.

A method can be static and have a valid `null` receiver, yet the call still fails due to `IllegalAccessException` or `IllegalArgumentException`.

When code lives in a framework, the actual caller of `trySetAccessible` may reside in the framework module. You must open the package to **that** module, rather than assuming the application's startup module is always the Reflection caller.

## 8. Return values, static initialization, and hidden methods

### 8.1. The result of `invoke` is always `Object`

Whether the target method returns `int`, `boolean`, `double`, or a reference type, `Method.invoke` is declared to return `Object`:

- For primitives, the result is **boxed** into the corresponding wrapper, e.g., `int` into `Integer`.
- For reference types, the reference value itself is returned per contract.
- For `void`, `null` is returned.
- If the method returns a primitive array such as `int[]`, the result is the **`int[]` array**, not automatically converted to `Integer[]`.

```java
Method count = Example.class.getMethod("count");
Object result = count.invoke(null);
int value = (Integer) result;
```

This illustrative code assumes `Example.count()` is a public static method returning `int`. Check `getReturnType()` when handling dynamic signatures to avoid wrong type casts.

### 8.2. Static methods can trigger class initialization

If the class declaring a static method has not yet been initialized, `Method.invoke` will cause **the declaring class to be initialized before the static method runs**. This is standard Java behavior, not a specific effect of the `null` argument.

```java
class LazyInit {
    static {
        System.out.println("initialized");
    }

    public static void ping() {
        System.out.println("called");
    }
}
```

If `LazyInit` has never been initialized and a caller with permission retrieves `Method` and calls `invoke(null)`, the static initializer runs before `ping()`, logging `initialized` and then `called`. When testing, note that other operations initializing the class earlier may prevent the `initialized` log from repeating.

If class initialization fails, Reflection can throw `ExceptionInInitializerError`, distinct from `InvocationTargetException` wrapping an exception thrown by the **target method body**.

### 8.3. Static methods do not dispatch by instance

Static methods belong to the declaring type; Java does not override static methods using the polymorphism mechanism of instance methods. If a subclass declares a static method with the same signature, that is **method hiding**, not overriding.

Once you have a `Method` representing a static method in class A, passing an instance of class B as the receiver argument **does not** cause Reflection to switch to another static method in B. The receiver is ignored; whichever `Method` was selected determines the target method.

Do not use `method.invoke(instance, ...)` on a static method and infer the call target from the runtime type of `instance`.

## 9. Diagnosing failed static calls

A `null` receiver is valid for a static method, yet the call still requires the **right Method, right access rights, and right argument list**. When diagnosing, separate three phases:

| Phase | Symptom | What to check |
| --- | --- | --- |
| Lookup | `NoSuchMethodException` | Name, erased parameter types, `getMethod` vs. `getDeclaredMethod` |
| Call preparation | `IllegalAccessException`, `IllegalArgumentException` | Access permissions/JPMS, count and types of `args`; a `null` receiver does not resolve these errors |
| Execution | `InvocationTargetException` | `getCause()` to read the error thrown by the static method body |
| Class initialization | `ExceptionInInitializerError` | Error during initialization of the declaring class prior to the static call |

If `setAccessible(true)` fails with `InaccessibleObjectException`, review package opening permissions; do not treat a `null` receiver as a way to bypass access checks. Before invoking in framework code, use `Modifier.isStatic(method.getModifiers())` to confirm the method is actually static.

## 10. A safer dynamic invocation helper pattern

If your tool only needs to support **static methods**, you can validate explicitly to catch contract violations early:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Objects;

public final class StaticCaller {
    private StaticCaller() {
    }

    public static Object invokeStatic(Method method, Object... arguments)
            throws IllegalAccessException, InvocationTargetException {
        Objects.requireNonNull(method, "method");
        if (!Modifier.isStatic(method.getModifiers())) {
            throw new IllegalArgumentException("Method is not static: "
                    + method.getName());
        }
        return method.invoke(null, arguments);
    }
}
```

This is a **standalone compilable utility class** saved as `StaticCaller.java`; it does not look up methods itself, does not alter access rights, and does not swallow exceptions from the target method. Callers must pass a valid `Method` and, if `arguments` contains an array as a single argument, package the array properly.

When calling the utility:

```java
Method add = Math.class.getMethod("addExact", int.class, int.class);
Object answer = StaticCaller.invokeStatic(add, 20, 22);
System.out.println(answer); // 42
```

This usage example requires importing `java.lang.reflect.Method` and handling checked exceptions (for instance, placed in a `main` with `throws Exception`), alongside the `StaticCaller` class above. `Math.addExact(int,int)` is a public static method; from the call snippet you can verify no `Math` instance needs to be created.

If Reflection is used repeatedly on a hot performance path, consider another controlled invocation mechanism such as `MethodHandle`. Regardless of the mechanism used, access checks and signatures must be respected; there is no need to create an instance just to call a static method.

## 11. Self-check questions

**Question 1.** `Method m` points to `public static int add(int a, int b)`. Is `m.invoke(null, 2, 3)` valid, and what is the result type on the Reflection side?

**Answer:** Valid if access and other runtime conditions are met; returns an `Object` containing an `Integer` with value `5`.

**Question 2.** Why does `m.invoke(null)` fail for a no-argument instance method?

**Answer:** `null` is used as the receiver of an instance method; Reflection throws `NullPointerException`. "No parameters" does not mean "no instance required".

**Question 3.** For `public static void process(String[] items)`, are these two lines equivalent?

```java
m.invoke(null, (Object) new String[] {"x", "y"});
m.invoke(null, (Object[]) new String[] {"x", "y"});
```

**Answer:** No. The first line passes **one array argument**; the second line passes **two `String` arguments** to `invoke`'s varargs and does not match the single-parameter method.

**Question 4.** Can a `private static` method always run with `invoke(null)`?

**Answer:** A `null` receiver is valid from a static standpoint, but does not guarantee **access permissions**. The method may be rejected when the caller lacks access or deep reflection permission.

**Question 5.** With a `Method` representing a static method in a superclass, does passing a subclass instance to `invoke` call a hidden static method in the subclass?

**Answer:** No. The receiver is ignored; the call target is the static method that the `Method` already represents.

**Question 6.** When a static method body throws `IllegalStateException`, what does the caller typically see?

**Answer:** `Method.invoke` throws `InvocationTargetException`, and `getCause()` contains the target method's `IllegalStateException`.

## 12. Takeaway

`Method.invoke(Object receiver, Object... args)` interprets the first parameter according to **method kind**: static methods **ignore the receiver**, so `null` should be used; instance methods require a compatible object. A `null` receiver is not a null argument for the target method. Distinguish **receiver**, **`args` varargs array**, **access control**, **class initialization**, and **target method exceptions** to diagnose errors accurately.

Standard references: [Java SE 21 — java.lang.reflect.Method, invoke](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html) and [Java SE 21 — java.lang.reflect.Modifier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Modifier.html).
