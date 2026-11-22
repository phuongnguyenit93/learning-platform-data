# 10.6 Normalizing Return Types, Primitive Values, void, and null in Java Dynamic Proxy

A Java **dynamic proxy** implements interfaces at runtime. When a client calls a method on the proxy, the call is forwarded to `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`. This method **is always declared to return `Object`**, whereas the method on the interface may return `int`, `long`, `boolean`, `String`, `Optional<String>`, `void`, or another reference type. Therefore, the handler code needs to return **the exact form of value that the proxy-generated method can convert to the declared type**.

The most important differences:

- **Primitive:** the handler must return a **wrapper of the exact type** (`int` ↔ `Integer`, `long` ↔ `Long`...). `null` causes a `NullPointerException`; the wrong wrapper causes a `ClassCastException` at the call on the proxy.
- **Reference:** the handler may return `null` or an object **assignable to the declared return type**. An incompatible object causes a `ClassCastException`.
- **`void`:** the proxy **ignores the value** returned by the handler, even if the handler returns a non-`null` object; a clear design should return `null`.
- **Normalization:** if data from JSON/DB/remote API has an unnormalized type, check `method.getReturnType()`, perform intentional conversion **before returning from the handler**, and clearly define the `null`/overflow/validation policy.

This lesson focuses on **the return type contract of a dynamic proxy and how to normalize safely**; the complete Java 17+ example includes both the success path and expected errors.

## 1. Call flow: two signatures and one mandatory conversion point

Suppose an interface defines:

~~~java
interface Counter {
    int count();
    String label();
    void reset();
}
~~~

The handler still has the same single signature:

~~~java
@Override
public Object invoke(Object proxy, Method method, Object[] args) throws Throwable
~~~

The two snippets above only illustrate the structure, not a standalone runnable program.

~~~text
Client calls proxy.count()         -> int type at the call site
          |
          v
Proxy-generated method             -> calls handler.invoke(proxy, method, args)
          |
          v
InvocationHandler.invoke           -> Object: e.g. Integer.valueOf(7)
          |
          v
Proxy-generated method             -> casts to Integer, unboxes to int
          |
          v
Client receives 7 (int)

If handler returns null            -> unboxing null -> NullPointerException
If handler returns Long.valueOf(7) -> cast to Integer -> ClassCastException
~~~

The point to separate: Java automatically **boxes primitive arguments** passed into `args` of the handler and automatically **unboxes the matching wrapper** when the proxy method returns a primitive. However, the proxy **is not a general-purpose data conversion system**. It does not parse strings into numbers and does not guarantee widening across different numeric wrappers.

More precisely, the proxy call is checked against **the declared return type of the executed method**, not just against the `Object` variable in the handler. Returning `Object` is merely the Java signature of `InvocationHandler.invoke`; it does not allow returning arbitrary objects.

## 2. Return contract table

| Interface return type | Handler returns valid | Handler returns `null` | Handler returns invalid |
| --- | --- | --- | --- |
| `int` | `Integer` | `NullPointerException` | `Long`, `String` → `ClassCastException` |
| `long` | `Long` | `NullPointerException` | `Integer` → `ClassCastException` |
| `boolean` | `Boolean` | `NullPointerException` | `String("true")` → `ClassCastException` |
| `char` | `Character` | `NullPointerException` | `String("A")` → `ClassCastException` |
| `double` | `Double` | `NullPointerException` | `Float` → `ClassCastException` |
| `String` | `String` or subtype (String is final) | Valid | `StringBuilder` → `ClassCastException` |
| `Number` | `Integer`/`Long`/`BigDecimal`... | Valid | `String` → `ClassCastException` |
| `Optional<String>` | `Optional` (should match generic contract) | Allowed at runtime because it is a reference; usually **not recommended** by API contract | Not an `Optional` → `ClassCastException` |
| `void` | `null` is the clearest convention | Valid | A non-`null` value **is ignored**, not used as a result |

The rule of JDK `InvocationHandler.invoke`: if the interface method returns a primitive, the handler must return **an instance of the corresponding wrapper class**. Not every numeric wrapper “with the same number” is valid. For example, `Long.valueOf(5)` for `int` is invalid; `Integer.valueOf(5)` for `long` is also invalid **if you have not converted it to `Long`**.

The table above is **the contract when the value leaves the handler and is returned to the caller through the proxy**, which differs from the *method invocation conversion* rules when the compiler performs a normal Java call.

## 3. Complete table of the eight primitives and required wrapper classes

| Primitive | Wrapper that must be returned from `invoke` | Example |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 1)` |
| `short` | `Short` | `Short.valueOf((short) 2)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(7)` |
| `long` | `Long` | `Long.valueOf(7L)` |
| `float` | `Float` | `Float.valueOf(1.5f)` |
| `double` | `Double` | `Double.valueOf(1.5d)` |

Do not write the return type as `Number` on the interface if the contract requires `int` and hope that `Long` or `BigDecimal` will be automatically converted. When the method is `int count()`, the handler must return `Integer`; when the method is `long total()`, the handler must return `Long`. `void` is **not** among the eight data primitives and has no wrapper to unbox. `Void.class` is a separate **reference type**, different from the primitive return type `void.class`.

### Wrong and right examples

~~~java
// Interface: long total();

return Integer.valueOf(5);                  // Wrong: proxy needs Long, causes ClassCastException.
return Long.valueOf(5L);                    // Correct: Long wrapper.
return Long.valueOf(Integer.valueOf(5));    // Correct: Integer is unboxed to int, widened to long, and creates Long.
return Long.valueOf(((Integer) raw).longValue()); // Correct if raw is actually an Integer.
~~~

These are **illustrative lines inside a handler**, not a single standalone runnable method block. In the last line, `raw` is assumed to hold an `Integer` value and converting to `long` is the author's intention.

### Numeric conversion requires an exact policy

- `BigDecimal.intValue()` can **truncate the fractional part** or lose information when out of range; if only exact integers are allowed, use `intValueExact()`.
- `Number.longValue()` can lose data in many subtypes; only convert when you know the data source, unit, and valid range.
- `float`/`double` have precision issues and `NaN`/`Infinity`; if the contract does not allow them, validate before returning the wrapper.
- `byte`/`short`/`char` should not be silently narrowed by casting in systems that process external data.
- `Boolean.valueOf("maybe")` **returns false** and does not throw an error; if the input must be a boolean literal, validate strictly for `"true"`/`"false"` before parsing.

A good normalizer distinguishes **already the right type**, **allowed conversion**, **missing value**, and **invalid data**. You should not use an unchecked `(T) raw` cast to hide problems.

## 4. `void`: the handler's return value is ignored, but side effects and exceptions are not

Example:

~~~java
interface Audit {
    void log(String message);
}
~~~

If `InvocationHandler.invoke` returns `"ok"` after handling `log(...)`, the generated proxy method has return type `void`, so **there is no value to pass to the caller**. The value `"ok"` is ignored, without becoming a `String` or an exception due to a wrong return type.

~~~java
if (method.getReturnType() == void.class) {
    // Perform the appropriate side effect.
    return null; // Just a clear convention; the proxy also ignores non-null Objects.
}
~~~

Notes:

1. **No return value** does not mean **nothing is executed**: the handler still runs, and can still write logs, call a delegate, mutate state, or throw an exception.
2. `void.class` differs from `Void.class`. If a method declares `Void apply()`, it is a **reference-returning method**. `null` is valid; any non-null returned object must be assignable to `Void`. `java.lang.Void` has no public constructor to create a useful instance.
3. Reflection's `method.invoke(target, args)` returns `null` when the target returns `void`; however, that is the semantics of the reflection API, **not** a requirement for a dynamic proxy to accept a `void` method.
4. If an async operation needs a result, do not try to stuff it into the return value of a `void` method; consider exposing a `CompletionStage<Void>`, `Future<Void>`, or another result contract on the API interface.
5. Do not ignore exceptions from the processing logic just because the method is `void`. Exceptions are propagated according to the proxy's exception rules.

## 5. `null`: valid for reference, but not for primitive

`null` has three different meanings depending on the signature:

| Return type | What does `return null` from the handler mean? |
| --- | --- |
| `int` / `long` / `boolean` / other primitive | **Wrong**: the proxy needs to unbox a wrapper; the caller receives `NullPointerException` |
| `String`, `User`, `List<?>`, array, `Optional<?>`, `Void` | **Type-valid**: a reference can be null; the application contract may forbid it |
| `void` | Clear, commonly used; the proxy ignores the return value |

Therefore, “missing data” does not have a single global policy applicable to every method:

- For `int count()`, choose to **return 0 if the contract specifies a default value**, or throw a clear exception; do not automatically substitute 0 for every missing-data case because it easily masks bugs.
- For `String nickname()`, `null` may be returned if the API permits nullable, but it must be documented.
- For `Optional<User> find(...)`, it is best to return `Optional.empty()` instead of `null` to preserve the “non-null” contract that callers usually expect. At proxy runtime, `null` can still pass through because `Optional` is a reference.
- For `void`, returning `null` makes the handler easy to understand; there is no need to create a `Void`.

Do not assume `@NotNull` or `@NonNull` on the method return type makes the JVM automatically check for null in the proxy. Annotations only take effect if a checker/framework or code validates according to the contract. The proxy core does not enforce Bean Validation on its own.

### Important error order

When the handler returns `null` for a primitive, the error is thrown **when the proxy method tries to unbox**, not necessarily right at the `return null;` statement. Similarly, returning `Integer` for a method returning `String` is detected when the generated proxy method casts the result. Errors caused by input data should be detected early in the normalizer step to produce a more specific message instead of waiting for a hard-to-debug `ClassCastException`.

## 6. Designing the result normalization step by `Method.getReturnType()`

Recommended design flow:

~~~text
1. Method method from InvocationHandler.invoke
          |
          v
2. Determine Class<?> returnType = method.getReturnType()
          |
          +-- void.class        -> execute logic -> return null
          |
          +-- primitive         -> check raw != null
          |                       intentionally convert to exact wrapper
          |                       reject wrong type / overflow
          |
          +-- reference         -> raw == null? apply nullable policy
                                  type.isInstance(raw)? accept
                                  intentional conversion? handle
                                  not valid? reject
          |
          v
3. Return the normalized Object from the handler
          |
          v
4. Proxy-generated method casts/unboxes to the interface return type
~~~

Suggested utility signature:

~~~java
static Object normalize(Class<?> returnType, Object raw)
~~~

Step by step:

- `returnType == void.class` must be checked **before** `isPrimitive()`, because `void.class.isPrimitive()` is `true` yet `void` has no primitive wrapper/unboxing like the eight data types.
- For primitives, use a mapping from the primitive type to the corresponding wrapper class; if `raw` already has the exact wrapper, keep it as is. If conversion is allowed, only convert under clear conditions, such as `BigDecimal.intValueExact()` or `Integer.longValue()`.
- For references, use `returnType.isInstance(raw)`; `Class.isInstance(null)` is `false`, so null must be handled separately. `isAssignableFrom` can also be used once the runtime `raw.getClass()` is obtained (must guard against null).
- If `raw` is invalid, **throw an intentional error** right inside the normalizer to report unsuitable data. Do not create wrappers by blind casting.
- `Method.getGenericReturnType()` can return `ParameterizedType` when the interface uses generics, but **does not replace** `getReturnType()` for runtime type checking. Element generic types are normally erased.

### Limitations of the normalizer

There is no single default solution that is right for every API. For example, should `"10"` be converted to `int 10`? Should `null` in `Integer` be turned into 0? Should `BigDecimal("1.5")` be rounded? Which time zone should `Instant` use when converted to `String`? All of these are **business rules** that need to be decided explicitly.

The example below intentionally supports only a few specific conversions and **rejects** the rest. It is not a general-purpose JSON mapper.

## 7. Complete Java 17+ program: normalization and observing errors

Save the file `ProxyReturnTypesDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.math.BigDecimal;
import java.util.Optional;

public class ProxyReturnTypesDemo {
    public interface ReportApi {
        int count();
        long total();
        boolean enabled();
        char grade();
        String title();
        String absent();
        Optional<String> optional();
        void notifyEvent(String event);
    }

    public interface UnsafeApi {
        int missingPrimitive();
        long wrongWrapper();
        String wrongReference();
        void ignored();
    }

    static final class NormalizingHandler implements InvocationHandler {
        @Override
        public Object invoke(Object proxy, Method method, Object[] args) {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "ReportProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new UnsupportedOperationException(method.getName());
                };
            }

            // Represents unnormalized data coming from a provider.
            Object raw = switch (method.getName()) {
                case "count" -> new BigDecimal("7");
                case "total" -> Integer.valueOf(5);
                case "enabled" -> "true";
                case "grade" -> "A";
                case "title" -> new StringBuilder("daily");
                case "absent" -> null;
                case "optional" -> Optional.empty();
                case "notifyEvent" -> {
                    System.out.println("event = " + args[0]);
                    yield "ignored by void";
                }
                default -> throw new UnsupportedOperationException(method.getName());
            };
            return normalize(method.getReturnType(), raw);
        }
    }

    static Object normalize(Class<?> type, Object raw) {
        if (type == void.class) return null;

        if (type.isPrimitive()) {
            if (raw == null) {
                throw new IllegalStateException("null for " + type.getName());
            }

            // Only convert data that is explicitly allowed.
            if (type == int.class && raw instanceof BigDecimal value) {
                return Integer.valueOf(value.intValueExact());
            }
            if (type == long.class && raw instanceof Integer value) {
                return Long.valueOf(value.longValue());
            }
            if (type == boolean.class && raw instanceof String value
                    && (value.equals("true") || value.equals("false"))) {
                return Boolean.valueOf(value);
            }
            if (type == char.class && raw instanceof String value && value.length() == 1) {
                return Character.valueOf(value.charAt(0));
            }

            Class<?> wrapper = switch (type.getName()) {
                case "boolean" -> Boolean.class;
                case "byte" -> Byte.class;
                case "short" -> Short.class;
                case "char" -> Character.class;
                case "int" -> Integer.class;
                case "long" -> Long.class;
                case "float" -> Float.class;
                case "double" -> Double.class;
                default -> throw new IllegalArgumentException("unknown primitive " + type);
            };

            if (wrapper.isInstance(raw)) return raw;
            throw new IllegalArgumentException("expected " + wrapper.getSimpleName());
        }

        if (raw == null || type.isInstance(raw)) return raw;
        if (type == String.class && raw instanceof CharSequence value) {
            return value.toString();
        }
        throw new IllegalArgumentException("expected " + type.getTypeName());
    }

    public static void main(String[] args) {
        ReportApi report = (ReportApi) Proxy.newProxyInstance(
                ReportApi.class.getClassLoader(),
                new Class<?>[] { ReportApi.class },
                new NormalizingHandler());

        System.out.println("count = " + report.count());
        System.out.println("total = " + report.total());
        System.out.println("enabled = " + report.enabled());
        System.out.println("grade = " + report.grade());
        System.out.println("title = " + report.title());
        System.out.println("absent = " + report.absent());
        System.out.println("optional = " + report.optional());
        report.notifyEvent("ping");
        System.out.println("toString = " + report.toString());
        System.out.println("equals self = " + report.equals(report));
        System.out.println("hashCode identity = " +
                (report.hashCode() == System.identityHashCode(report)));

        UnsafeApi bad = (UnsafeApi) Proxy.newProxyInstance(
                UnsafeApi.class.getClassLoader(),
                new Class<?>[] { UnsafeApi.class },
                (proxy, method, values) -> switch (method.getName()) {
                    case "missingPrimitive" -> null;
                    case "wrongWrapper" -> Integer.valueOf(3);
                    case "wrongReference" -> Integer.valueOf(123);
                    case "ignored" -> "unused";
                    default -> throw new UnsupportedOperationException(method.getName());
                });

        try {
            bad.missingPrimitive();
        } catch (NullPointerException ex) {
            System.out.println("primitive null -> " + ex.getClass().getSimpleName());
        }

        try {
            bad.wrongWrapper();
        } catch (ClassCastException ex) {
            System.out.println("wrong primitive wrapper -> " + ex.getClass().getSimpleName());
        }

        try {
            bad.wrongReference();
        } catch (ClassCastException ex) {
            System.out.println("wrong reference -> " + ex.getClass().getSimpleName());
        }

        bad.ignored();
        System.out.println("void ignores raw result = true");
    }
}
~~~

Compile and run from the directory containing the file, using **JDK 17 or later**:

~~~bash
javac --release 17 ProxyReturnTypesDemo.java
java ProxyReturnTypesDemo
~~~

**`stdout` verified when compiling/running with the JDK:**

~~~text
count = 7
total = 5
enabled = true
grade = A
title = daily
absent = null
optional = Optional.empty
event = ping
toString = ReportProxy
equals self = true
hashCode identity = true
primitive null -> NullPointerException
wrong primitive wrapper -> ClassCastException
wrong reference -> ClassCastException
void ignores raw result = true
~~~

### 7.1. What happens inside the normalizer?

- `count()` returns primitive `int`. The raw source is `BigDecimal("7")`; `intValueExact()` gives 7 and the utility wraps it in `Integer`. The proxy unboxes it to `int`.
- `total()` returns primitive `long`. Raw is `Integer.valueOf(5)`; the utility explicitly creates `Long.valueOf(5L)`. If `Integer` were returned as-is from the handler, the proxy **would not widen automatically** and would fail.
- `enabled()` returns `boolean`. The utility accepts strictly the strings `"true"` or `"false"`, then creates `Boolean`. Other strings are not silently coerced to `false`.
- `grade()` returns `char`. The utility requires a string of length exactly one `char` and creates `Character`. If Unicode code points outside the BMP need to be supported, the design must consider surrogate pairs instead of treating every visual character as a single `char`.
- `title()` requires `String` while raw is `StringBuilder`, which **is not a subtype of String**; the utility converts it via `toString()` before returning.
- `absent()` returns `String`, so `null` is valid at runtime; `optional()` returns an `Optional.empty()` to express missing data in the `Optional` style.
- `notifyEvent(...)` is declared `void`. The handler performs the side effect and has raw `"ignored by void"`, but the normalizer returns `null`. In `UnsafeApi.ignored()`, the handler directly returns the string `"unused"` **without normalization**, and the proxy still ignores it because the method returns `void`.

### 7.2. Why are there exactly three errors in `UnsafeApi`?

1. `missingPrimitive():int` — the handler returns `null`; the proxy tries to unbox an `Integer` from null, resulting in `NullPointerException`.
2. `wrongWrapper():long` — the handler returns `Integer` instead of `Long`, so the generated proxy method tries to cast to `Long` and throws `ClassCastException`.
3. `wrongReference():String` — the handler returns `Integer`; it is not assignable to `String`, resulting in `ClassCastException`.

The code catches only the three **intentionally triggered** exceptions at their exact call sites; it does not catch `Throwable` indiscriminately. This lets other unexpected errors surface as real failures for easier debugging.

### 7.3. `equals`, `hashCode`, and `toString` are also dispatched

A dynamic proxy also dispatches calls to `Object.equals(Object)`, `Object.hashCode()`, and `Object.toString()` into the handler. `method.getDeclaringClass() == Object.class` helps identify them. The demo returns:

- `toString()` → `"ReportProxy"`, which is a valid `String`.
- `hashCode()` → an `Integer` from `System.identityHashCode(proxy)`, valid for the `int` return type.
- `equals(...)` → `Boolean` from the identity comparison `proxy == args[0]`, valid for the `boolean` return type.

Do not accidentally return `null` in `hashCode` or `equals`: both return primitives. Do not call `proxy.toString()` inside the handler for `toString()` to build a string, because it calls back into the handler and can cause infinite recursion.

## 8. Forwarding to a real object using `Method.invoke`

A handler often does not compute all values itself, but **forwards** the call to a delegate. Distinguish between **the return result** and **exceptions**.

~~~java
Object raw;
try {
    raw = method.invoke(delegate, args);
} catch (java.lang.reflect.InvocationTargetException ex) {
    throw ex.getCause();
}
return normalize(method.getReturnType(), raw);
~~~

This is an **illustrative snippet inside `InvocationHandler.invoke`**: assume `delegate` is an object compatible with the declaring interface, `method`/`args` are the handler's parameters, `normalize` is defined in the appropriate class, and the method can `throws Throwable`.

- When the delegate method returns a primitive, `Method.invoke` **boxes** the value into the matching wrapper (`int` → `Integer`), which is suitable for returning through the proxy if the contract is intact.
- When the delegate method returns `void`, `Method.invoke` returns `null`; forwarding this value from the handler is valid.
- When the delegate returns a `null` reference, `Method.invoke` returns `null`; the handler must decide whether the API allows nullable.
- When the delegate method **throws an exception**, reflection wraps it in `InvocationTargetException`. If the handler throws the wrapper as-is, you may encounter an unexpected `UndeclaredThrowableException`; instead, you should usually `throw ex.getCause()` to propagate the target exception according to the interface contract.
- If the delegate does not implement the exact interface/Method used to invoke, `method.invoke(delegate,args)` can throw `IllegalArgumentException`; do not treat that as a return value normalization error.
- Never use `method.invoke(proxy,args)` if `proxy` is the dynamic proxy object currently dispatching into the handler: you will invoke the handler again, leading to a recursive loop instead of calling the real delegate.

In practice, `method.getDeclaringClass()` and interface metadata may be needed to select the appropriate implementation. When forwarding across interface versions, do not resolve methods solely by name if overloads exist; you must also check the parameter signature.

## 9. Input arguments are different from return values

`InvocationHandler.invoke` receives:

~~~java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable
~~~

`args` can be **`null` when the method has no parameters**, not always `new Object[0]`. A primitive-typed argument is boxed into its wrapper before being passed into the handler. If a method declares `int add(int x, int y)`, the handler normally sees `Integer` at `args[0]` and `args[1]`.

Example:

~~~java
Object[] actualArgs = args == null ? new Object[0] : args;
int numberOfArguments = actualArgs.length;
~~~

This illustrative snippet is safe for zero-argument methods. However, **do not conflate argument handling with return handling**: `args==null` only indicates that the method has no arguments; it does not mean the handler must return `null`. A zero-argument `int count()` must still return `Integer`.

For varargs interface methods, such as `void log(String... messages)`, `args` typically contains **a single `String[]` array element** at the last argument position, not necessarily each string as a separate element in `args`. Reflection forwarding via `Method.invoke` has its own varargs layer; do not manually flatten the array into multiple parameters different from the target method signature.

## 10. Handler errors, proxy errors, and `UndeclaredThrowableException`

Do not confuse the error classes:

| Error | Where does it occur? | Cause | How to fix |
| --- | --- | --- | --- |
| `NullPointerException` | Proxy method, when returning a primitive | Handler returns `null` | Do not return null for primitives; validate or report missing data clearly |
| `ClassCastException` | Proxy method, when casting/unboxing return | Wrong primitive wrapper or incompatible reference | Normalize to the exact wrapper or compatible reference type before returning |
| `IllegalArgumentException` / `IllegalStateException` | Normalizer code (if you choose to throw) | Data does not satisfy the conversion policy | Report expected type, source value, and method context |
| `ArithmeticException` | `BigDecimal.intValueExact()`, etc. | Number cannot be converted exactly | Reject overflow/fraction, adjust contract |
| `InvocationTargetException` | `Method.invoke` used inside handler | Real delegate method threw an exception | Extract `getCause()` and decide to rethrow the target exception |
| `UndeclaredThrowableException` | Proxy method | Handler throws a **checked exception** that the interface does not declare in a compatible `throws` clause | Declare the checked exception, convert per policy, or unwrap the cause properly |
| `StackOverflowError` | Handler calls back into the proxy | Handler accidentally invokes a method on `proxy` itself | Call the real delegate, do not call the proxy from the handler |
| `ClassCastException` when caller processes generic data | Caller side or code reading generic values | Wrong generic element after erasure | Deep-validate against generic schema/`Type` if the contract requires it |

`InvocationHandler.invoke` can throw `Throwable`, but when a client calls an interface method, a valid checked exception must belong to the declared exceptions (according to proxy rules), whereas unchecked `RuntimeException`/`Error` can propagate directly. If the handler throws an undeclared checked exception, the proxy wraps it in `UndeclaredThrowableException`. Therefore, handler design normalizes not only **return values** but also the **exception contract**.

For example, if the interface declares `String load() throws IOException`, the handler can validly throw `IOException`; for `String load()` with no checked exception declared, throwing `IOException` can result in `UndeclaredThrowableException`. For a proxy implementing multiple interfaces with matching method signatures, the `throws` clauses must be compatible with **all** corresponding declarations, not just the method the handler receives at runtime.

## 11. Return types of duplicate methods, covariant returns, and generic erasure

A dynamic proxy has constraints right at **proxy class creation time**:

- If multiple proxy interfaces declare **the same name and parameter signature**, and one return type is a primitive or `void`, **all** methods with that signature must have **that exact same return type**. You cannot create a unified proxy for `int size()` and `long size()` with the same parameters.
- If all return types are references, there must be **at least one** return type assignable to all the remaining return types (a suitable covariant type). For example, two interfaces returning `Number` and `Integer` can be combined because `Integer` is a subtype of `Number`.
- When methods collide across multiple interfaces, the `Method` passed to the handler may be the method from **the interface that appears earlier** in the interfaces list when creating the proxy; it does not necessarily match the static reference type the caller used. Do not rely solely on `method.getDeclaringClass()` to infer every context of a duplicate method.
- Even though the proxy allows covariant reference returns, the handler should return an object **compatible with all callable API branches**, not just a broader return type chosen as the Method metadata.

### Generics are not deeply checked automatically

For example, `List<String> names()`: the return type at the JVM level is `List.class`; the proxy can verify that the returned object is a `List`, but **does not check that every element is a String** per the generic source contract. If the handler returns `List.of(123)` for a `List<String>` contract, code reading elements as `String` can hit a `ClassCastException` later. Do not treat `method.getReturnType().isInstance(list)` as sufficient if your API requires checking generic contents.

When truly needed, you can read `Method.getGenericReturnType()`, inspect `ParameterizedType`, and validate the contents against a custom schema; that is a validation concern **beyond** the minimal return-type checks of a dynamic proxy.

### Default methods

An interface can define `default String label() { ... }`. On a dynamic proxy, calls to that method still go through `InvocationHandler`; the default body does not run automatically just because the method has the `default` modifier. Since Java 16, the handler can call `InvocationHandler.invokeDefault(proxy, method, args)` (provided the method is valid) if it wants to use the default implementation. The result returned from the default method must still comply with the return type contract when passing through the handler.

~~~java
if (method.isDefault()) {
    Object[] callArgs = args == null ? new Object[0] : args;
    return InvocationHandler.invokeDefault(proxy, method, callArgs);
}
~~~

This is an **illustrative snippet inside a handler** with `import java.lang.reflect.InvocationHandler;` and `throws Throwable`. Not every default method can be invoked across every interface configuration when overridden or conflicting; the Javadoc specifies the exact resolution conditions.

## 12. Designing null and conversion policies in real systems

A large application should explicitly write out its **normalization contract**, rather than letting each handler infer on its own:

| Design question | Example policy |
| --- | --- |
| How are missing primitive values handled? | Throw `IllegalStateException` instead of arbitrarily converting to 0 |
| Is numeric widening allowed? | `Integer` → `Long` for `long`, under explicit conditions; **do not** leave it to the proxy |
| Is rounding/truncation allowed? | No; `BigDecimal.intValueExact()` for `int`; reject fractional parts/overflow |
| Which literals are accepted for `boolean` from strings? | Only `"true"` and `"false"`, case-sensitive or case-insensitive per contract |
| Does `String` automatically accept `CharSequence`? | If allowed, call `toString()`; otherwise reject |
| Can nullable references return null? | Per method specification; if `Optional`, use `Optional.empty()` |
| What should `void` return? | `null` from the handler for readability, even though the proxy ignores any Object return |
| Should runtime validation apply to generic collections? | If the contract requires it, iterate and validate elements explicitly, do not rely on the proxy |
| Where do conversion errors go? | Throw an informative exception with method name, expected type, and actual class; do not log sensitive data |

For frameworks, you can attach a `ReturnPolicy`/`ResultAdapter` to method metadata, cache `Method.getReturnType()` if optimization is needed for high-frequency calls, and separate three blocks: **delegate invocation → normalize result → return to proxy**. If using a JSON mapper, distinguish boundary validation from post-deserialization conversion; an object that already has the right runtime type can still carry an invalid business value.

**Security note:** do not allow untrusted input to freely choose an arbitrary method name and result adapter to execute through a proxy; validate allowed interfaces/members and do not log raw secret values when reporting conversion errors. The normalizer should inspect types and produce minimal useful messages rather than leaking payloads.

## 13. Required tests for handlers with multiple return types

A test suite should include at least these groups:

1. **All primitives:** verify each exact wrapper (`Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`), then verify the unboxed result at the caller.
2. **Wrong wrapper with the same numeric value:** `Integer` returned for `long`, `Long` returned for `int`; must be rejected, not widened automatically.
3. **Primitive null:** verify the exception per policy; without a normalizer, expect `NullPointerException` from the proxy.
4. **Valid/invalid references:** `String`, subtype of the interface, non-assignable object; null reference valid if allowed by contract.
5. **Void:** handler executes side effect and returns an arbitrary object; proxy returns no value. Handler does not swallow exceptions.
6. **Missing data:** test null, empty string, `Optional.empty()`, and cases that must throw a specific exception.
7. **Numeric boundaries:** negative numbers, 0, max/min of primitives, fractional parts when converting to integer, overflow, `NaN`, and infinity when relevant to policy.
8. **Object methods:** `equals` returns Boolean, `hashCode` returns Integer, `toString` returns String; avoid recursion.
9. **Delegate exceptions:** test runtime exceptions, valid checked exceptions and undeclared checked exceptions, and proper unwrapping of `InvocationTargetException`.
10. **Generic/covariant returns:** proxy interfaces with colliding signatures, reference result assignable across all call paths; validate collection elements if required by contract.

Avoid testing only by calling `handler.invoke(...)` directly. Calling the handler directly **bypasses** the generated proxy method, so you will not observe the proxy's unboxing/casting errors. Critical tests must **invoke through the actual proxy object** such as `api.count()`, `api.total()`, `api.title()` to capture exact production semantics.

## 14. Common misconceptions

### “The handler returned Long for int, doesn't Java convert numeric types automatically?”

No. The fact that Java can widen `int` to `long` in a normal Java call **does not** mean the generated proxy method will convert across numeric wrappers. `long total()` requires the handler to return `Long`; if raw is `Integer`, the conversion must be done before returning from the handler.

### “Can I just return null for any method I don't know how to handle?”

No. `null` causes `NullPointerException` for primitive returns. For references, null may be type-valid but violate the application contract. For `void`, null is the clear choice. The handler should throw `UnsupportedOperationException` for unsupported methods, or follow a documented policy, rather than silently returning null across the entire API.

### “Is `Method.getReturnType()` Object because `handler.invoke` returns Object?”

No. `method` represents the method **on the interface**, so `method.getReturnType()` is its declared type, such as `int.class`, `String.class`, or `void.class`. `Object.class` is only the return type of `InvocationHandler.invoke` **itself**, and does not replace the return type of the proxied method.

### “If a method returns Optional, will null be rejected by the proxy?”

No. `Optional` is a reference type, so the proxy runtime accepts `null` at the type level. However, `Optional.empty()` is usually a better API policy; callers may invoke `optional.isPresent()` and hit a `NullPointerException` if the handler violates the contract.

### “Does returning a non-null object from the handler for void cause ClassCastException?”

No. The generated proxy method declared `void` ignores the handler's return value. Even so, returning `null` keeps the code easier to understand.

### “Are all exceptions from a delegate automatically unwrapped by the proxy?”

No. `Method.invoke` wraps exceptions in `InvocationTargetException`; the handler must decide to `throw ex.getCause()` when forwarding. The proxy also has its own rules for undeclared checked exceptions, which can surface as `UndeclaredThrowableException`.

## 15. Self-check questions

**Question 1.** An interface has `int getCount()`, and the handler returns `Long.valueOf(3)`. What does the caller receive?

**Answer:** `ClassCastException`, because the proxy needs `Integer` to unbox `int`. Numeric data must be converted to `Integer` in the handler according to a valid policy.

**Question 2.** An interface has `long getTotal()`, and the handler returns `Integer.valueOf(3)`. The numeric value is right, but is the handler contractually correct?

**Answer:** No. The proxy needs `Long`. You can explicitly do `Long.valueOf(integer.longValue())` in the normalizer.

**Question 3.** A method returns `void`, and the handler returns `"done"`. Does the proxy throw `ClassCastException`?

**Answer:** Not just because of that value. The proxy ignores the handler's Object return for `void`; the handler's side effects or exceptions still occur.

**Question 4.** A method returns `String`, and the handler returns `null`. Is this valid?

**Answer:** Valid at the dynamic proxy's type layer; it may be forbidden by the application contract.

**Question 5.** A method returns `boolean`, and the handler returns `null`. What is the result?

**Answer:** `NullPointerException` when the proxy tries to unbox `Boolean`.

**Question 6.** What is the difference between `method.getReturnType() == void.class` and `method.getReturnType() == Void.class`?

**Answer:** `void.class` describes a method that returns no value; `Void.class` describes a return type that is a reference class, so `null` can be returned as a reference.

**Question 7.** Is calling `handler.invoke(...)` directly in tests sufficient to verify the proxy's return conversions?

**Answer:** No. When calling directly, you receive `Object` from the handler, bypassing the proxy-generated method that performs casting/unboxing.

**Question 8.** Why can `List<String>` returning `List<Integer>` pass the proxy's return type check?

**Answer:** Because erasure causes the runtime check in the proxy to see only `List`; checking element contents requires separate validation.

**Question 9.** The handler forwards to a delegate using `method.invoke(...)`, and the delegate throws `IOException`. What needs to be considered?

**Answer:** Reflection throws `InvocationTargetException`, so the handler needs to unwrap the cause; `IOException` can only pass through the proxy as a checked exception if the interface method declares a compatible `throws` clause. Otherwise, the proxy may wrap it in `UndeclaredThrowableException`.

## Official Documentation

- [Java SE 21 — InvocationHandler.invoke and primitive, reference, null, and exception contracts](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 21 — Proxy: Object methods, return types across multiple interfaces, duplicate methods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 21 — Method.getReturnType and getGenericReturnType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 21 — InvocationTargetException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Java SE 21 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html)
