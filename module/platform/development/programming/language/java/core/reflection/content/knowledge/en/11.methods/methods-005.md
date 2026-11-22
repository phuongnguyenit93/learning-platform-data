# Method.invoke with receiver and argument array in Java Reflection

## 1. Understanding the two parameters of Method.invoke

Java Reflection allows invoking a method discovered at runtime via `java.lang.reflect.Method`. API signature:

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
```

Meaning:

- `Method` already identifies the **target method**: declaration, name, and parameter types. `invoke` does not re-select an overload based on the runtime class of each argument.
- `obj` is the **receiver**, the object on which an instance method executes. For a static method, the receiver is ignored, and passing `null` is usually the clearest approach.
- `args` is the list of actual arguments for the target method, in the form of an `Object[]` array. Each element of the array must correspond to **one formal parameter** in exact order, even when that formal parameter is itself an array.
- `invoke` returns `Object`: primitives are boxed; `void` returns `null`; references/arrays preserve their object types. Exceptions thrown by the target method are wrapped in `InvocationTargetException`.

For example, the target method `int add(int a, long b)` needs two elements in `args`; the target method `void print(String[] names)` needs only one element, which is a `String[]`.

The most common source of confusion: **`Method.invoke` has the syntax `Object... args`, while the target method might also declare `String... values`. Those are two separate layers of varargs**, and must be clearly distinguished.

## 2. Receiver for instance methods and static methods

### Instance methods require a compatible receiver

Suppose we have a class:

```java
class Greeter {
    public String hello(String name) {
        return "Hi, " + name;
    }
}
```

Inside a method that handles Reflection exceptions:

```java
Method hello = Greeter.class.getMethod("hello", String.class);
Greeter greeter = new Greeter();
Object answer = hello.invoke(greeter, "Mai"); // "Hi, Mai"
```

The receiver must be an instance compatible with the class or interface declaring the underlying method. `hello.invoke(null, "Mai")` throws `NullPointerException`; `hello.invoke(new Object(), "Mai")` throws `IllegalArgumentException`. These errors differ from errors thrown by the body of `hello`.

For **overridden instance methods**, Reflection still performs dynamic method lookup according to the runtime class of the receiver. A `Method` obtained from a superclass can execute the subclass's overridden implementation. `Method.getDeclaringClass()` still describes the class containing the original declaration and does not change to the receiver's runtime class.

### Static methods ignore the receiver

```java
class Settings {
    public static String status() { return "READY"; }
}
```

```java
Method status = Settings.class.getMethod("status");
Object a = status.invoke(null);         // "READY"
Object b = status.invoke(new Object()); // "READY"
```

These are illustrative snippets, with `java.lang.reflect.Method` imported and exceptions handled in the enclosing method. The receiver `new Object()` does not belong to `Settings` yet **is not checked for compatibility**, because a static method does not run on that object. A static method can cause its declaring class to **be initialized** for the first time upon `invoke`, so a Reflection call can trigger static initializers.

Distinguish ignoring the receiver **value** from skipping **evaluation of the receiver expression**: in `status.invoke(buildReceiver())`, Java still executes `buildReceiver()` before the call, and then Reflection ignores the returned value for the static method.

Choosing the receiver intentionally:

```java
Object target = Modifier.isStatic(method.getModifiers()) ? null : instance;
Object result = method.invoke(target, arguments);
```

This is a code fragment, not a complete program; variables `method`, `instance`, `arguments` and import `Modifier` are required. When `method` is an instance method, `instance` must be of the right type; for static, passing `null` clearly expresses that no object is needed.

| Method kind | Receiver | Behavior |
| --- | --- | --- |
| Instance | Object of the right type or subtype | Can invoke override on runtime class |
| Instance | `null` | `NullPointerException` |
| Instance | Incompatible object | `IllegalArgumentException` |
| Static | `null` | Valid |
| Static | Any object, even unrelated | Receiver value is ignored |

The table assumes access permissions, other arguments, and class initialization do not cause errors.

## 3. Reflection's Object[] array is the argument list, not the array's contents

For the method `add(int a, long b)`, two ways of passing arguments are equivalent:

```java
addMethod.invoke(service, 2, 5);
addMethod.invoke(service, new Object[]{2, 5});
```

Two formal parameters mean **two** elements in `Object[]`. When a formal parameter is an array such as `String[] names`, you must wrap that array itself into a **single element** of the list:

```java
Method join = Service.class.getMethod("join", String[].class);
Object result = join.invoke(service, new Object[]{new String[]{"a", "b"}});
```

Here `join` has one formal parameter `String[]`, so the outer `Object[]` has exactly one element, while the inner `String[]` has two elements. This holds whether the method is declared as `join(String[] values)` or `join(String... values)`: in metadata, both have formal parameter type `String[].class`. `join.isVarArgs()` indicates whether the declaration has the varargs flag, but **`Method.invoke` does not automatically gather `String` elements into an array for the target method**.

**Method lookup must match the exact signature**:

```java
Method m = Service.class.getMethod("join", String[].class);
Class<?>[] formalTypes = m.getParameterTypes();
int count = m.getParameterCount(); // 1
```

`getMethod` and `getDeclaredMethod` take the `Class<?>` list of formal parameters, not a list of runtime value wrappers, and do not select overloads via widening. For example, to look up `f(long)` you must use `getMethod("f", long.class)`; `getMethod("f", int.class)` will not find it just because `int` can widen to `long` when called.

## 4. Complete runnable Java 17+ program

Save the following program to **`InvokeReceiverDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvokeReceiverDemo {
    public static class Service {
        public String greet(String name) { return "Hello, " + name; }
        public int add(int a, long b) { return (int) (a + b); }
        public String join(String... values) { return String.join("/", values); }
        public static String label(int number) { return "ID=" + number; }
        public void noResult() { }
        public void boom() { throw new IllegalStateException("failed"); }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Service service = new Service();
        Method greet = Service.class.getMethod("greet", String.class);
        Method label = Service.class.getMethod("label", int.class);
        Method add = Service.class.getMethod("add", int.class, long.class);
        Method join = Service.class.getMethod("join", String[].class);
        Method noResult = Service.class.getMethod("noResult");
        Method boom = Service.class.getMethod("boom");

        System.out.println("instance = " + greet.invoke(service, "Ana"));
        System.out.println("static null = " + label.invoke(null, 7));
        System.out.println("static unrelated = " + label.invoke(new Object(), 7));

        Object result = add.invoke(service, Integer.valueOf(2), Integer.valueOf(5));
        System.out.println("widen = " + result + " (" +
                result.getClass().getSimpleName() + ")");
        System.out.println("isVarArgs = " + join.isVarArgs());
        System.out.println("join cast = " +
                join.invoke(service, (Object) new String[] {"a", "b"}));
        System.out.println("join wrapped = " +
                join.invoke(service, new Object[] {new String[] {"x", "y"}}));
        System.out.println("void returns null = " + (noResult.invoke(service) == null));

        try { greet.invoke(null, "Ana"); }
        catch (NullPointerException e) {
            System.out.println("null receiver = NullPointerException");
        }
        try { greet.invoke(new Object(), "Ana"); }
        catch (IllegalArgumentException e) {
            System.out.println("wrong receiver = IllegalArgumentException");
        }
        try { greet.invoke(service); }
        catch (IllegalArgumentException e) {
            System.out.println("wrong arity = IllegalArgumentException");
        }
        try { join.invoke(service, (Object[]) new String[] {"a", "b"}); }
        catch (IllegalArgumentException e) {
            System.out.println("spread array = IllegalArgumentException");
        }
        try { add.invoke(service, Long.valueOf(2), Integer.valueOf(5)); }
        catch (IllegalArgumentException e) {
            System.out.println("narrowing = IllegalArgumentException");
        }
        try { boom.invoke(service); }
        catch (InvocationTargetException e) {
            System.out.println("target cause = " +
                    e.getCause().getClass().getSimpleName() + ": " +
                    e.getCause().getMessage());
        }
    }
}
```

Use JDK 17 or later:

```bash
javac InvokeReceiverDemo.java
java InvokeReceiverDemo
```

Stdout compiled and verified on JDK 24:

```text
instance = Hello, Ana
static null = ID=7
static unrelated = ID=7
widen = 7 (Integer)
isVarArgs = true
join cast = a/b
join wrapped = x/y
void returns null = true
null receiver = NullPointerException
wrong receiver = IllegalArgumentException
wrong arity = IllegalArgumentException
spread array = IllegalArgumentException
narrowing = IllegalArgumentException
target cause = IllegalStateException: failed
```

Explanation:

1. `greet` is an instance method so it requires a properly typed receiver `service`.
2. `label` is a static method so both `null` and `new Object()` receivers are ignored. This is **not** valid behavior for an instance method.
3. `add` declares `(int, long)`. `Integer(2)` is unboxed to `int`, and `Integer(5)` is unboxed and then widened from `int` to `long`. The `int` result is boxed into `Integer`.
4. `join` has `isVarArgs() == true` and its signature accepts only **one `String[]`**; both successful calls pass the string array as **one argument**.
5. `noResult` declares `void`; the return value from Reflection is `null`.
6. The errors for `null` receiver, wrong class, wrong number of args, spread array, or converting `Long` to `int` all manifest as the printed exception types.
7. `boom` throws `IllegalStateException` inside its body; the Reflection caller receives `InvocationTargetException` and retrieves the cause from `getCause()`.

## 5. Distinguishing two layers of varargs, including null forms

### The target method's array must occupy a single slot of Object[]

For `join(String... values)`, the runtime formal parameter is `String[]`:

```java
join.invoke(service, (Object) new String[]{"a", "b"});       // valid
join.invoke(service, new Object[]{new String[]{"a", "b"}});   // valid
join.invoke(service, (Object[]) new String[]{"a", "b"});     // wrong arity
```

The `(Object)` cast in the first line forces Java to treat the `String[]` array as **one argument** of the `invoke` API, thereby creating an `Object[]` list with one element. The second line explicitly builds a one-element list. The third line casts the entire `String[]` to `Object[]` of `invoke` (valid because `String[]` is a subtype of `Object[]`) and thus spreads **two strings** as **two formal arguments**; `join` expects only one `String[]`, leading to `IllegalArgumentException`.

Writing `join.invoke(service, new String[]{"a","b"})` without a cast is also prone to causing a compiler warning "non-varargs call for last parameter" and spreading the array at the outer layer. For stable and readable framework code, always build `new Object[]{...}` or cast the array to `Object`.

For `int[]`, do not attempt to cast `int[]` to `Object[]`: primitive arrays are not subtypes of `Object[]`. For example, a method `sum(int[] numbers)` must receive:

```java
sumMethod.invoke(receiver, new Object[]{new int[]{1, 2, 3}});
```

This is an illustrative snippet, with `sumMethod` as metadata for a method taking `int[]`. Reflection does not automatically convert `Integer[]` into `int[]` or automatically unbox each element in an array.

### null receiver, null argument list, and a single null argument

The following calls have different semantics (variables `greet`, `noResult`, `service` are taken from the main example):

| Call | Meaning |
| --- | --- |
| `noResult.invoke(service)` | No arguments; valid because the target method takes no parameters |
| `noResult.invoke(service, new Object[0])` | Empty list; valid |
| `noResult.invoke(service, (Object[]) null)` | The `args` array is `null`, valid when the target method has no parameters |
| `greet.invoke(service, (Object) null)` | One argument with value `null`; body returns `"Hello, null"` |
| `greet.invoke(service, new Object[]{null})` | Same: one `null` argument |
| `greet.invoke(service, (Object[]) null)` | List has 0 arguments, while the method needs 1: `IllegalArgumentException` |
| `greet.invoke(null, "Ana")` | `null` receiver for an instance method: `NullPointerException` |

Uncast `invoke(service, null)` can trigger a compiler warning or be interpreted as an unintended varargs form. Explicitly write `(Object) null` to pass **one null argument**, or `new Object[0]`/`(Object[]) null` to pass **zero arguments**. If a formal parameter is primitive (`int`, `boolean`, etc.), a `null` value cannot be unboxed and is rejected.

**Note:** when the `args` array of `Method.invoke` is `null` and the target method has no formal parameters, the API accepts this; do not infer that every method can be invoked with a `null` list.

## 6. Argument and return conversions

### Method invocation conversions

Java checks argument count and type compatibility at the `invoke` call:

- Reference parameters accept `null` or a compatible reference subtype (e.g., `String` for `CharSequence`).
- Primitive parameters accept a suitable wrapper that gets unboxed; **widening primitive** conversions such as `int` to `long` are allowed.
- **Narrowing primitive** conversions such as `long` to `int` do not happen automatically. A `String` containing digits is not automatically parsed into `int`.
- Conversions apply **per element of `Object[]`**, and do not propagate into elements of an array formal parameter.

Example:

```java
Method m = Service.class.getMethod("add", int.class, long.class);
m.invoke(service, Integer.valueOf(2), Integer.valueOf(5)); // OK
m.invoke(service, Long.valueOf(2), Integer.valueOf(5));    // IllegalArgumentException
m.invoke(service, (Object) null, Integer.valueOf(5));       // IllegalArgumentException
```

This is an illustrative code fragment, not a standalone runnable program. Target method `add` is not re-selected to match `Long`; `Method` was already looked up by signature `(int,long)`.

### Return value

| Return type of target method | Value returned by `invoke` |
| --- | --- |
| `String` or reference type | Result reference, possibly `null` |
| `int`, `long`, or other primitive | Wrapper such as `Integer`, `Long` |
| `void` | `null` |
| `int[]` or other array | The array itself, without boxing each element |

`method.getReturnType()` describes the declared type. `result.getClass()` only describes the runtime class if the result is non-`null`; it cannot distinguish `void` from a reference-returning method that returns `null`. For generics, `getGenericReturnType()` can inspect the generic signature when metadata is available; runtime invocation does not check erased type arguments.

## 7. Exceptions: invocation errors vs. errors inside the method

Per the Java 17 Javadoc for `Method.invoke`:

| Error | Typical cause |
| --- | --- |
| `NoSuchMethodException` | Occurs when `getMethod`/`getDeclaredMethod` cannot find the exact signature; this is a **lookup** error, before invoking |
| `IllegalAccessException` | Caller lacks permission to call the underlying method under Java access control |
| `NullPointerException` | `null` receiver when the underlying method is an instance method |
| `IllegalArgumentException` | Wrong receiver type, wrong number of formal/actual args, or an argument cannot be converted to the formal type |
| `InvocationTargetException` | Target method ran and threw an exception/error; read `getCause()` |
| `ExceptionInInitializerError` | Initialization of the declaring class triggered by invoking a static method failed |
| `InaccessibleObjectException` | Can occur when requesting deep reflection with `setAccessible(true)` not permitted by the module |

Example pattern for handling the root cause properly:

```java
try {
    method.invoke(receiver, arguments);
} catch (InvocationTargetException ex) {
    Throwable underlying = ex.getCause();
    // Handle/log the exception thrown by the target method itself.
} catch (IllegalAccessException ex) {
    // Check method access permissions.
} catch (IllegalArgumentException ex) {
    // Check receiver, arity, and argument conversions.
}
```

This is a code fragment requiring context `method`, `receiver`, `arguments`. Do not lump `InvocationTargetException` together with "wrong Reflection parameters" errors; it is a **wrapper around an error that occurred inside the method**. In real applications, the policy for handling checked exceptions, unchecked exceptions, and `Error` at the framework layer must be clearly designed.

### getMethod vs. getDeclaredMethod and access permissions

- `getMethod(name, parameterTypes...)` searches for public methods according to lookup rules, and can see inherited public methods.
- `getDeclaredMethod(name, parameterTypes...)` searches for methods declared **directly** in the class, including private ones, without automatically walking superclasses.
- Obtaining a private `Method` **does not mean you can call it**. `Method.invoke` can throw `IllegalAccessException`; `trySetAccessible()`/`setAccessible(true)` can only relax access if module and runtime rules allow it.
- `Method.invoke` on an overridden instance method uses dynamic dispatch; static methods do not override in that sense. Passing a subtype receiver for a static method does not select a static method hidden in the subtype.
- If the target method resides in a Java module whose package is not open to the caller, do not rely on Reflection to bypass encapsulation. Prefer public APIs or configure `opens` only when truly needed.

## 8. A utility to reduce receiver errors and control signatures

Here is a complete Java class used as a helper in a project (without `main`):

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class ReflectiveCalls {
    private ReflectiveCalls() {}

    public static Object call(Method method, Object instance, Object[] arguments)
            throws IllegalAccessException, InvocationTargetException {
        Object target = Modifier.isStatic(method.getModifiers())
                ? null
                : instance;
        return method.invoke(target, arguments);
    }
}
```

This helper only performs explicit receiver selection. It **does not automatically fix** arity, cast arbitrarily, resolve overloads, bypass private/module access, or catch errors from the target method. Before using it, calling code needs to know:

1. Which method is being requested and its exact formal parameter types (`getParameterTypes()`).
2. Whether the method is static or instance (`Modifier.isStatic(getModifiers())`), ensuring the receiver has the right type if it is an instance method.
3. That `Object[]` contains exactly one element per formal parameter, especially for array formal parameters and varargs.
4. Whether the caller has permission to invoke the method and whether static class initialization has side effects.
5. How to handle `InvocationTargetException.getCause()` and boxed/`null` return values.

When the method to call is known at compile time, a regular Java call usually offers clearer type checking. Reflection is appropriate when method names/types are only known at runtime, such as in mappers, test runners, plugin frameworks, or dependency injection containers.

## 9. Self-check

**Question 1.** `Method m` describes `static void run()`. Does `m.invoke(new Object())` have a wrong receiver? **No**; the target is ignored. Using `m.invoke(null)` is preferable for clarity.

**Question 2.** The target method is `void accept(String[] names)`. Can you pass two strings via `m.invoke(receiver, (Object[]) new String[]{"A","B"})`? **No**: this call creates two actual `String` args, whereas there is only one formal `String[]`. Use `m.invoke(receiver, (Object) new String[]{"A","B"})` or `m.invoke(receiver, new Object[]{new String[]{"A","B"}})`.

**Question 3.** `m` describes `void greet(String s)`. What does `m.invoke(receiver, (Object) null)` pass? **One `null`**. What about `m.invoke(receiver, (Object[]) null)`? **Zero actual args**, missing a parameter and failing.

**Question 4.** A method returns `long`; what type does `Method.invoke` return? **`Object` containing `Long`** via boxing. For a `void` method, `invoke` returns `null`.

**Question 5.** The target method throws `IOException`. Will Reflection invoking this method throw `IOException` directly? **No**; `InvocationTargetException` wraps the original exception—check `getCause()`.

**Question 6.** You have a `Method` for an instance method on class `Base`; the receiver is `Derived` which overrides that method. Which version runs? **The overridden implementation on `Derived`**. If it is a static method, there is no dynamic overriding.

**Question 7.** Why can't `getMethod("f", int.class)` find `f(long)` even though `Integer` can widen to `long` during `invoke`? **Lookup uses the exact formal signature; value conversion only happens at invocation time**.

## 10. Official documentation

- [Java SE 17 Javadoc — Method.invoke(Object, Object...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 Javadoc — Class.getMethod / getDeclaredMethod](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 Javadoc — Executable.isVarArgs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [Java SE 17 Javadoc — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [JLS 17, Section 15.12.4: Runtime Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4)
