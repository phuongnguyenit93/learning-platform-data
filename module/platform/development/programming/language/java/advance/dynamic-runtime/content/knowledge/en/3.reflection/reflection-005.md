# 3.5 Invoking static or instance methods with Method.invoke

In reflection, `java.lang.reflect.Method` describes **a method that has been looked up**; `Method.invoke(...)` executes that method at runtime. The decisive difference between a **static** call and an **instance** call is the first argument (receiver): for `static`, we usually pass `null`; for an instance method, a compatible object must be passed. The actual arguments of the method follow the receiver.

This lesson focuses on how to look up and invoke both types of methods using `Method.invoke`, with runnable Java 17+ examples, handling data types, overloads, varargs, return values, and practical errors.

## 1. Reading the `Method.invoke` signature accurately

According to the Java SE API:

~~~java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
~~~

Meaning:

- `obj`: the object receiving the call. An **instance method** requires the receiver to be an instance of the class/interface declaring the method (or a compatible subtype). A **static method** ignores this receiver; pass `null` to express the intent clearly.
- `args`: the values passed to **the declared parameters of the target method**, in order. `Object...` is the varargs of the **reflection API** itself, distinct from varargs if the target method also declares `...`.
- The return value has declared type `Object`: primitive results are boxed (`int` becomes `Integer`, `boolean` becomes `Boolean`), while for a method returning `void`, the result of `invoke` is `null`.
- `IllegalAccessException`: not permitted to invoke the method; `InvocationTargetException`: the target method body threw an exception. Additionally, there are runtime errors from the receiver, argument count/types, class initialization, etc.

A reflection call has the form:

~~~text
                    metadata             receiver        actual arguments
                         │                    │                  │
                         ▼                    ▼                  ▼
Method method = ... ; method.invoke(    objOrNull,    arg0, arg1, ... );
                         │
                         └──> Java checks access and types, then executes the target method
~~~

Do not confuse `invoke` with `getMethod`: `getMethod` only **finds** metadata, whereas `invoke` **calls** the method.

## 2. Static vs. instance: differences in receiver and dispatch

| Aspect | `static` method | Instance method |
| --- | --- | --- |
| Declaration example | `static int add(int a, int b)` | `String hello(String name)` |
| Lookup | `Type.class.getMethod("add", int.class, int.class)` | `Type.class.getMethod("hello", String.class)` |
| Receiver when invoking | `method.invoke(null, 2, 3)` | `method.invoke(instance, "An")` |
| Need to create target object? | No | Yes |
| Receiver is `null` | Valid; actually ignored | `NullPointerException` |
| Execute override in subclass | Static methods do not override polymorphically | Can dispatch to override based on **runtime type of receiver** |
| Class initialization | Invoking a static method may trigger initialization of the declaring class | Creating/obtaining an instance has its own initialization rules |

Short example (these statements are in the context of a method that handles checked exceptions):

~~~java
Method staticMethod = Math.class.getMethod("max", int.class, int.class);
Object a = staticMethod.invoke(null, 4, 9);       // Integer(9)

Method instanceMethod = String.class.getMethod("substring", int.class);
Object b = instanceMethod.invoke("reflection", 3); // "lection"
~~~

`Math.max` is `static` so it has no actual receiver; `String.substring` is an instance method so it requires a `String`. With `invoke`, the return value is declared as `Object` even though you know the corresponding results are `Integer` and `String`.

**Note on static receiver:** according to the API, `obj` is **ignored** for static methods, even if a non-`null` object is passed. However, always use `null` for clear code and to avoid confusion with instance calls.

## 3. Three right steps: find Method, prepare receiver/args, execute

**Step 1 — find the method by name and parameter types**.

~~~java
Method m1 = Service.class.getMethod("calculate", int.class, int.class);
Method m2 = Service.class.getMethod("label", String.class);
~~~

- `getMethod` finds `public` methods accessible according to the API search mechanism, including inherited `public` methods.
- `getDeclaredMethod` finds methods **declared directly** in the class/interface, including `private`; finding metadata **does not automatically grant permission to invoke** that method.
- The name and `Class<?>` parameter type list must match the signature. For example, `int.class` differs from `Integer.class`, `String[].class` differs from `String.class`. The return type is **not** a parameter of `getMethod`.
- You can inspect the found method with `m.getName()`, `m.getParameterTypes()`, `m.getReturnType()`, `m.getDeclaringClass()`, `m.getModifiers()`, `m.isVarArgs()`.

**Step 2 — determine static/instance and prepare arguments.**

~~~java
boolean isStatic = java.lang.reflect.Modifier.isStatic(m1.getModifiers());
Object receiver = isStatic ? null : new Service();
~~~

In real applications, you usually already know the method kind by contract. If handling methods dynamically, read `Modifier.isStatic(...)` to avoid passing the wrong receiver.

**Step 3 — invoke and handle the result or error.**

~~~java
Object result = m1.invoke(receiver, 10, 20);
~~~

Java does not use `args` to automatically find the "best overload" based on runtime values. The overload was already selected at the **Method lookup step**; `invoke` only checks whether the provided values match the parameters of the already-selected method.

## 4. Complete Java 17+ example: static, instance, override, overload, varargs, void, and exception

Create file `ReflectInvokeDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectInvokeDemo {

    public static class Service {
        public static int add(int left, int right) {
            return left + right;
        }

        public String greet(String name) {
            return "Xin chào, " + name;
        }

        public String show(int number) {
            return "int=" + number;
        }

        public String show(String text) {
            return "text=" + text;
        }

        public static String join(String... items) {
            return String.join("|", items);
        }

        public void mark() {
            System.out.println("mark() called");
        }

        public void fail() {
            throw new IllegalStateException("lỗi nghiệp vụ");
        }
    }

    public static class PoliteService extends Service {
        @Override
        public String greet(String name) {
            return "Kính chào, " + name;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Service> type = Service.class;

        // static: receiver is null; returned int is boxed into Integer
        Method add = type.getMethod("add", int.class, int.class);
        System.out.println("add static? " + Modifier.isStatic(add.getModifiers()));
        Object sum = add.invoke(null, 2, 3);
        System.out.println("add = " + sum
                + " (" + sum.getClass().getSimpleName() + ")");

        // instance: pass an object of Service
        Service service = new Service();
        Method greet = type.getMethod("greet", String.class);
        System.out.println("greet = " + greet.invoke(service, "An"));

        // instance: same Method, receiver is a subtype -> invokes override
        System.out.println("override = " + greet.invoke(
                new PoliteService(), "Bình"));

        // overload: select show(int) right when calling getMethod
        Method showInt = type.getMethod("show", int.class);
        System.out.println("overload = " + showInt.invoke(service, 7));

        // Varargs target actually has one String[] parameter
        Method join = type.getMethod("join", String[].class);
        String[] items = { "A", "B", "C" };
        System.out.println("join = " + join.invoke(null, (Object) items));

        // void: invoke returns null
        Method mark = type.getMethod("mark");
        Object voidResult = mark.invoke(service);
        System.out.println("void result = " + voidResult);

        // Target exception is wrapped by InvocationTargetException
        Method fail = type.getMethod("fail");
        try {
            fail.invoke(service);
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println("cause = "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
~~~

Compile and run (from the directory containing `ReflectInvokeDemo.java`):

~~~bash
javac ReflectInvokeDemo.java
java ReflectInvokeDemo
~~~

Expected `stdout`:

~~~text
add static? true
add = 5 (Integer)
greet = Xin chào, An
override = Kính chào, Bình
overload = int=7
join = A|B|C
mark() called
void result = null
cause = IllegalStateException: lỗi nghiệp vụ
~~~

Comparing the points:

1. `add.invoke(null, 2, 3)`: a static method does not need an instance; the `int` result is boxed into `Integer`, so `sum.getClass().getSimpleName()` is `Integer`.
2. `greet.invoke(service, "An")`: the receiver is `Service`; with the same `Method greet`, if the receiver is `PoliteService`, the JVM executes the subclass override.
3. `showInt.invoke(service, 7)`: the overload was already selected by `getMethod("show", int.class)`. Passing the string `"7"` does not make reflection automatically choose `show(String)`.
4. `join.invoke(null, (Object) items)`: casts `String[]` to `Object` to pass **one argument** to `Method.invoke`, because the target method has one `String[]` parameter.
5. `mark.invoke(service)`: executes a method returning `void` and receives `null` from reflection.
6. `fail.invoke(service)`: the method body throws `IllegalStateException`, accessed via `InvocationTargetException.getCause()`.

The example uses `public` classes nested inside a `public` class so that `public` methods can be looked up and invoked directly. In real modules/apps, access permission also depends on package and module boundaries.

## 5. Instance methods: receiver, inheritance, and override

For a regular method on a class:

~~~java
Method method = Parent.class.getMethod("run");
method.invoke(new Child());
~~~

This is an **illustrative snippet**, assuming `Parent` has `public void run()` and `Child extends Parent` overrides `run()`; it is not a standalone program. The JVM uses virtual dispatch rules: when the receiver is `Child`, the appropriate overridden method may be called, even though `Method` was found from `Parent.class`. This differs from the idea that "Method always runs the exact body of the class we used for getMethod".

The receiver must be compatible with the class/interface declaring the method:

| Receiver | Instance call | Result |
| --- | --- | --- |
| `new Parent()` | `method.invoke(receiver)` | Valid if class/method access permits |
| `new Child()` | `method.invoke(receiver)` | Valid, may dispatch to override |
| `null` | `method.invoke(null)` | `NullPointerException` |
| Object not in a compatible hierarchy | `method.invoke(new Object())` | `IllegalArgumentException` |

A `static` method is not overridden like an instance method, even though a subclass may declare a static method with the same signature to *hide* it. When a specific `Method` represents a static method, invoking it does not dispatch to a static method of the same name based on the type of `obj`.

When an instance call needs to mutate state, use **the exact object owning that state**. Passing `new Service()` on each `invoke` operates on a new object, which may not be the instance you intended to process.

## 6. Parameter types: boxing, unboxing, widening, and what is not converted

`Method.invoke` checks the number of parameters and applies *method invocation conversions* allowed by Java, including appropriate unboxing and primitive widening. The API does not perform arbitrary conversions.

Example with the method `public static long doubleValue(long input)`:

~~~java
Method twice = Example.class.getMethod("doubleValue", long.class);
Object result = twice.invoke(null, Integer.valueOf(6));
~~~

This is an illustrative snippet assuming `Example.doubleValue(long)` exists: `Integer` can be unboxed to `int` and then widened to `long`. Conversely, passing `Long.valueOf(6)` for an `int` parameter of another method is **not** automatically narrowed to `int`. The string `"6"` is also not automatically converted to a number.

Rules to remember:

- `null` can only be a valid value for reference parameters; passing `null` for `int`, `boolean`, etc. will fail.
- For primitive parameters, reflection can unbox an appropriate wrapper type and then widen; it does not automatically narrow to avoid data loss.
- For reference parameters, the object must be compatible with the required type; it does not automatically parse strings or create new objects from other types.
- Arguments must match the **count**, **order**, and types of the resolved method.
- If the method returns a primitive, `invoke` returns a wrapper; if it returns a reference, you receive an object; if it returns `void`, `null`. You need to cast the return type when using it, e.g. `int n = (Integer) method.invoke(receiver);`.
- A returned primitive array remains the primitive array itself (e.g. `int[]`), without converting each element into `Integer`.

## 7. Overloads are decided at lookup, not at `invoke`

Suppose we have:

~~~java
public String format(int value) { return "number"; }
public String format(String value) { return "text"; }
~~~

These two declarations are **illustrative inside a class**, not standalone top-level code. To call a specific overload, look up the exact one:

~~~java
Method intOverload = type.getMethod("format", int.class);
Method textOverload = type.getMethod("format", String.class);
~~~

Here `type` is the `Class<?>` of the class containing both methods. `getMethod("format", Integer.class)` will not automatically select `format(int)` if the class has no overload accepting `Integer`, because the **signature lookup** step requires the exact `Class<?>` of each parameter. Valid conversions are only applied **after** `Method` has been found.

This is especially important when reading method names and argument values from JSON/config. If you only have runtime data without knowing the signature, you must design overload selection logic carefully rather than randomly trying each `Method`. Evaluating `null` requires even more care because it does not reveal the expected reference type.

## 8. Varargs and array parameter traps in `invoke`

There are **two independent varargs layers**:

1. The reflection method: `invoke(Object receiver, Object... args)`.
2. The target method, e.g. `static String join(String... words)`, which at the JVM signature level is a method with **one `String[]` parameter**.

With `Method join = Service.class.getMethod("join", String[].class)` and `String[] words = {"A", "B"}`:

~~~java
join.invoke(null, (Object) words);          // Correct: one String[] argument
join.invoke(null, new Object[] { words }); // Correct: args has one String[] element
// join.invoke(null, words);                // Wrong intent: may treat each String
//                                          // in words as a separate argument.
~~~

The first two calls both place *one* `String[]` into the target's argument list. The third line easily leads to `IllegalArgumentException` due to wrong argument count/type, because `String[]` is also an `Object[]` and the compiler may pass it as the varargs array of **`Method.invoke`**. This is the difference between "a method expecting an array" and "the `invoke` API accepting an array of arguments".

For a target method **with no parameters**, use `method.invoke(receiver)` or `method.invoke(receiver, new Object[0])` for clarity. The Javadoc also allows the `args` array to be `null` when the target has 0 formal parameters, but writing `new Object[0]` helps avoid ambiguity between "no arguments" and "one argument with value null".

For a target method with **one reference parameter that needs to receive `null`**, you can write:

~~~java
method.invoke(receiver, (Object) null);
~~~

In that case, the cast expresses a single argument with value `null`; it is not a call to a target method with no arguments.

## 9. Exception handling: reflection errors vs. target method errors

Not all errors in `invoke` are wrapped the same way. Distinguish two groups:

| Issue | Primary exception | How to handle |
| --- | --- | --- |
| Signature not found in `getMethod` | `NoSuchMethodException` | Check name, parameter type list, public/declared |
| Method exists but caller lacks access | `IllegalAccessException` | Check visibility, module exports/opens, runtime permissions |
| Instance receiver is `null` | `NullPointerException` | Provide an actual receiver |
| Incompatible receiver, wrong argument count/type | `IllegalArgumentException` | Check `getDeclaringClass()`, `getParameterTypes()`, arg order/types |
| Target method body throws exception/error | `InvocationTargetException` | Read `getCause()` to determine the actual error |
| Static initialization fails during execution | `ExceptionInInitializerError` | Check class initialization errors, static initializer |

Example of properly unwrapping **target** errors:

~~~java
try {
    Object value = method.invoke(receiver, arguments);
    // process value
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // log/handle business cause; may need to rethrow per contract
} catch (IllegalAccessException ex) {
    // handle case where reflection is not allowed to invoke method
}
~~~

This is an illustrative snippet inside a method where variables `method`, `receiver`, `arguments` were created beforehand; note that `arguments` should have type `Object[]`. In practice, `NoSuchMethodException` occurs at the lookup step, not inside `Method.invoke`. `InvocationTargetException` is a wrapper with a cause; logging only the wrapper while ignoring the cause makes diagnosis difficult.

For a target method returning `void` and throwing an exception, the result is never "`null` representing an error": the call fails with an exception before returning. Therefore, do not infer that "returning `null` means invoke failed".

## 10. Access permissions and Java modules

Looking up a `Method` does not guarantee permission to execute it:

- `getMethod` returns `public` methods, but **the declaring class** or the module/package containing the class may not expose access to the caller in real scenarios.
- `getDeclaredMethod` can find `private`, `protected`, or package-private methods, but calling them with `invoke` still goes through access checks.
- `setAccessible(true)` requests bypassing some normal access checks; since Java 9, JPMS strong encapsulation can block this action. `trySetAccessible()` may return `false` when access cannot be opened; `setAccessible(true)` may throw `InaccessibleObjectException`.
- `exports` opens a package's public API according to module rules; `opens` allows deeper reflective access within the declared scope. Using `--add-opens` as a default solution is not recommended without understanding access permissions and operational needs.

In frameworks/libraries, keep permissions minimal, respect public contracts, and validate type/method names coming from untrusted input. Reflection can also accidentally invoke dangerous methods if an application allows users to choose arbitrary method names without control.

## 11. Performance and best practices

- **Prefer direct calls** when the method is known at compile time: `service.greet("An")` is simpler than `getMethod` + `invoke`, with type checking and better IDE refactoring.
- If reflection is needed for plugins/serializers/DI, **look up once when appropriate**, cache `Method` by signature and reuse it; do not re-lookup by name on every request just for convenience.
- Separate the two steps **lookup** and **invoke** so name/signature errors are distinct from execution errors.
- Check `Modifier.isStatic(method.getModifiers())` in dynamic dispatchers; set receiver to `null` for static, and a properly typed object for instance.
- For performance-sensitive code, measure with proper benchmarks (JMH, warm-up, representative data). `MethodHandle` may suit typed pipelines, but one cannot claim `MethodHandle` is always faster than reflection for every use case.
- Avoid writing complex custom overload resolvers without a clear contract. Restrict callable methods to avoid unintentionally opening runtime permissions.
- Reflection itself does not replace synchronization or thread safety. An instance method mutating shared state still requires proper concurrency coordination just like a direct call.

## 12. Self-check questions

1. Given `public static int sum(int,int)` and a `Method sum` looked up with the exact signature: which receiver should be passed? → `null`; the two numeric values are the subsequent arguments.
2. `greet` is an instance method of `Parent`, while the receiver is `Child extends Parent` overriding `greet`: can the `Child` version run? → Yes; virtual dispatch is based on the runtime type of the receiver.
3. Will `getMethod("sum", Integer.class, Integer.class)` find a method declared as `sum(int,int)`? → No. Lookup uses exact parameter `Class<?>` types; boxing/unboxing during invoke does not change lookup rules.
4. If the target method is declared `void` and succeeds, what does `invoke` return? → `null`.
5. If the target method throws `IllegalStateException`, what does the reflection caller catch? → `InvocationTargetException`; call `getCause()` to get `IllegalStateException`.
6. Why can `m.invoke(null, words)` be wrong when `words` is `String[]` and the target has exactly one `String[]` parameter? → Because the varargs layer of `Method.invoke` may interpret elements of `words` as separate arguments; use `(Object) words` or `new Object[]{words}`.
7. `getDeclaredMethod` found a private method; can it be invoked by default from another module? → No; access control and JPMS still apply.
8. If a `static` target method requires initializing its declaring class, when can initialization occur? → When reflective `invoke` executes that method if the class has not been initialized yet.

## References

- [Java SE 21 — `Method.invoke`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Java SE 21 — `Class.getMethod` and `getDeclaredMethod`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Oracle Java Tutorials — Invoking Methods, including arrays and varargs](https://docs.oracle.com/javase/tutorial/reflect/member/methodInvocation.html)
- [Oracle Java Tutorials — Troubleshooting `Method.invoke`](https://docs.oracle.com/javase/tutorial/reflect/member/methodTrouble.html)
