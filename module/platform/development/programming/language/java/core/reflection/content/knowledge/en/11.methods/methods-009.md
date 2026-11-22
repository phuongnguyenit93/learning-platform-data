# Primitive returns are boxed and `void` returns `null` when using `Method.invoke`

In Java Reflection, `java.lang.reflect.Method.invoke(Object obj, Object... args)` has **return type `Object`**, even if the underlying method is declared to return `int`, `boolean`, `String`, `Integer`, or `void`. Therefore, when calling a method via Reflection, distinguish the **declared return type** from the **object returned by `invoke`**.

Two core rules:

1. If the invoked method **returns a primitive value** (`int`, `boolean`, `double`, ...), `Method.invoke` **boxes** that value into its corresponding wrapper object (`Integer`, `Boolean`, `Double`, ...) before returning it.
2. If the method is declared **`void`**, `Method.invoke` **returns `null` when the call completes normally**. Here `null` is a result defined by Reflection's contract, not a value explicitly `return`ed by a `void` method.

In addition, a method with a **reference return type** (`String`, `Integer`, any object) can itself return `null`. Hence, **looking at `result == null` alone cannot tell whether the original method is `void` or a reference-returning method whose value happened to be `null`**. You must inspect metadata using `Method.getReturnType()`.

## 1. What does `Method.invoke` do with return values?

Abbreviated signature:

```java
Object result = method.invoke(receiver, arguments);
```

- `method`: a `Method` object describing a specific method already obtained via Reflection.
- `receiver`: instance used to invoke an instance method; for static methods, `null` can be passed since no instance is needed.
- `arguments`: input arguments; must match the method's parameter count and types.
- `result`: the outcome of the call as an `Object` or `null`. If code inside the method throws an exception, the invocation does not produce a normal return value.

`Method.invoke` does not alter the **declared** return type of the method. It simply needs to represent a result that can belong to many different Java types through **a single API return type**: `Object`.

| Declared method | Logical value after method runs | Result from `Method.invoke` |
|---|---|---|
| `int count()` | `7` | `Integer.valueOf(7)` as `Object` |
| `long total()` | `30L` | A `Long` with value `30` |
| `boolean enabled()` | `false` | `Boolean.FALSE` as `Object` |
| `char letter()` | `'A'` | A `Character` with value `'A'` |
| `double rate()` | `2.5` | A `Double` with value `2.5` |
| `String name()` | `"Lan"` | Reference to `String` containing `"Lan"` |
| `String missing()` | `null` | `null` |
| `Integer nullable()` | `null` | `null` |
| `void update()` | No return value | `null` |

The examples above assume the method completes **normally** and the caller has access permission. If the method throws an exception, `invoke` typically reports `InvocationTargetException`, rather than returning `null` as a normal result.

### Boxing applies to all eight primitives

| Primitive return | Wrapper in Reflection result |
|---|---|
| `boolean` | `java.lang.Boolean` |
| `byte` | `java.lang.Byte` |
| `short` | `java.lang.Short` |
| `char` | `java.lang.Character` |
| `int` | `java.lang.Integer` |
| `long` | `java.lang.Long` |
| `float` | `java.lang.Float` |
| `double` | `java.lang.Double` |

Primitive values `0`, `false`, or `'\u0000'` do **not** become `null`. Reflection still creates or returns a wrapper representing that value. Whether the JVM uses a wrapper cache for certain values or allocates a new object is an implementation detail not to rely on: compare **values using `equals` or primitive comparisons**, not wrapper identity with `==`.

## 2. `void` differs from `Void` and from methods returning a `null` reference

The following three declarations have different semantics:

```java
public void log() {
    System.out.println("logged");
}

public String findName() {
    return null;
}

public Void noResultObject() {
    return null;
}
```

These are three illustrative methods, not yet a program with a class and `main`. When invoked via Reflection:

- `log()` executes its side effect of printing `logged`; `Method.invoke` returns **`null`** because the return type is `void`.
- `findName()` returns a **`null`** reference returned by the method itself.
- `noResultObject()` declares **`java.lang.Void`** (a reference class) and returns `null`. `Void` is commonly used in generic APIs to represent the absence of a result value; it **differs** from the `void` keyword.

No "wrapper object" is created by Reflection for a `void` result. The `null` returned by `invoke` in this case is **neither** `new Void()` **nor** an instance of `Void`.

Even though all three calls above can return `null` from `invoke`, their metadata differs:

```java
Method log = Example.class.getMethod("log");
Method findName = Example.class.getMethod("findName");
Method noResultObject = Example.class.getMethod("noResultObject");

System.out.println(log.getReturnType() == void.class);               // true
System.out.println(findName.getReturnType() == String.class);        // true
System.out.println(noResultObject.getReturnType() == Void.class);    // true
```

This is an **illustrative snippet**; assume `Example` is a public class containing the three public methods above, and the code resides in a method declaring `throws ReflectiveOperationException` or handling `NoSuchMethodException`.

Therefore, to distinguish **no return value per signature** from **a return value that happens to be null**, always check the declared type using `getReturnType()`.

## 3. Complete Java 17+ example

Save as **`MethodReturnDemo.java`**:

```java
import java.lang.reflect.Method;

public class MethodReturnDemo {
    public static class Service {
        public int count() { return 7; }
        public boolean active() { return false; }
        public char initial() { return 'A'; }
        public long total() { return 30L; }
        public void touch() { System.out.println("touch body"); }
        public String missing() { return null; }
        public Integer nullable() { return null; }
        public Integer boxed() { return 17; }
        public static double rate() { return 2.5; }
        public void fail() { throw new IllegalStateException("broken"); }
    }

    public static void main(String[] args) throws Exception {
        Service service = new Service();
        Class<Service> type = Service.class;

        Method count = type.getMethod("count");
        Object countValue = count.invoke(service);
        System.out.println("count return type: " + count.getReturnType().getName());
        System.out.println("count value: " + countValue + " / " + countValue.getClass().getSimpleName());

        Object active = type.getMethod("active").invoke(service);
        System.out.println("active value: " + active + " / " + active.getClass().getSimpleName());
        Object initial = type.getMethod("initial").invoke(service);
        System.out.println("initial value: " + initial + " / " + initial.getClass().getSimpleName());
        Object total = type.getMethod("total").invoke(service);
        System.out.println("total value: " + total + " / " + total.getClass().getSimpleName());

        Method touch = type.getMethod("touch");
        Object voidResult = touch.invoke(service);
        System.out.println("touch return type: " + touch.getReturnType().getName());
        System.out.println("touch result is null: " + (voidResult == null));

        Method missing = type.getMethod("missing");
        System.out.println("missing return type: " + missing.getReturnType().getName());
        System.out.println("missing result is null: " + (missing.invoke(service) == null));

        Method nullable = type.getMethod("nullable");
        Object nullableValue = nullable.invoke(service);
        System.out.println("nullable return type: " + nullable.getReturnType().getName());
        System.out.println("nullable result is null: " + (nullableValue == null));

        Object boxedValue = type.getMethod("boxed").invoke(service);
        System.out.println("boxed value: " + boxedValue + " / " + boxedValue.getClass().getSimpleName());

        Object rateValue = type.getMethod("rate").invoke(null);
        System.out.println("static rate: " + rateValue + " / " + rateValue.getClass().getSimpleName());

        int converted = (Integer) count.invoke(service);
        System.out.println("converted int: " + converted);

        try {
            int invalid = (Integer) nullableValue;
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("nullable unboxing: " + ex.getClass().getSimpleName());
        }

        try {
            type.getMethod("fail").invoke(service);
        } catch (java.lang.reflect.InvocationTargetException ex) {
            System.out.println("method threw: " + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run in the file's directory (JDK 17 or newer):

```bash
javac MethodReturnDemo.java
java MethodReturnDemo
```

**Stdout verified with JDK 21:**

```text
count return type: int
count value: 7 / Integer
active value: false / Boolean
initial value: A / Character
total value: 30 / Long
touch body
touch return type: void
touch result is null: true
missing return type: java.lang.String
missing result is null: true
nullable return type: java.lang.Integer
nullable result is null: true
boxed value: 17 / Integer
static rate: 2.5 / Double
converted int: 7
nullable unboxing: NullPointerException
method threw: IllegalStateException
```

### Step-by-step execution analysis

1. `Service.count()` declares returning `int`; `Method.getReturnType().getName()` is `int`, yet the object received from `invoke` has runtime class `Integer`. Both facts are true because **primitives are boxed at the Reflection boundary**.
2. `active()` returns primitive `false` so `invoke` yields `Boolean(false)`; `initial()` returns primitive `'A'` yielding `Character`; `total()` returns `30L` yielding `Long`.
3. `touch()` still runs its body and prints `touch body`. Upon completion, `Method.invoke` returns `null` because the method declares `void`. `getReturnType()` of the method remains `void.class`.
4. `missing()` and `nullable()` declare **reference** types and can return `null` from their own logic. The result of `invoke` is also `null`, which **does not mean** these two methods are `void`.
5. `boxed()` returns declared type `Integer` with value `17`. `invoke` returns the result reference itself without an extra Reflection boxing step for `int`: `return 17` was already boxed by Java per the method's semantics.
6. `rate()` is `static`, so `invoke(null)` validly uses a `null` receiver. It returns primitive `double`, and Reflection represents it as `Double`. **A `null` receiver** is completely different from **returning `null`**.
7. `(Integer) count.invoke(service)` casts the object to `Integer` and then auto-unboxes when assigning to `int`. Unboxing a `null` reference from `nullable()` causes `NullPointerException`.
8. `fail()` throws `IllegalStateException` inside the actual method. Reflection **does not return `null`**; `invoke` throws `InvocationTargetException`, and `getCause()` is `IllegalStateException`.

There is **only one public class file** (`MethodReturnDemo.java`); the nested `Service` class keeps the program standalone with no external library dependencies.

## 4. Checking the return type with `getReturnType()`

`Method.getReturnType()` returns a `Class<?>` object representing the **declared return type**. It does not call the method, does not read an actual value, and does not box the declared type into a wrapper.

| Declaration | `method.getReturnType()` | `getReturnType().getName()` |
|---|---|---|
| `int read()` | `int.class` | `int` |
| `boolean ok()` | `boolean.class` | `boolean` |
| `void reset()` | `void.class` | `void` |
| `Integer readBoxed()` | `Integer.class` | `java.lang.Integer` |
| `String name()` | `String.class` | `java.lang.String` |
| `int[] values()` | `int[].class` | JVM binary name `[I` |

If a method returns a **primitive array**, such as `int[]`, the array itself is a **reference type**. `Method.invoke` returns a reference to the **array**, without boxing each `int` element into `Integer`. You can use `getReturnType().isArray()` and `getReturnType().getComponentType()` to inspect the array type.

One way to classify results in generic code:

```java
// This is an illustrative snippet inside a function that already has variables:
// Method method, Object receiver, Object[] arguments.
Class<?> declaredType = method.getReturnType();
Object result = method.invoke(receiver, arguments);

if (declaredType == void.class) {
    System.out.println("Method has no return value");
} else if (declaredType.isPrimitive()) {
    System.out.println("A primitive was boxed: " + result.getClass().getName());
} else if (result == null) {
    System.out.println("Reference return type, actual value is null");
} else {
    System.out.println("Reference result: " + result.getClass().getName());
}
```

**Why check `void.class` first:** `void` has special result handling. Do not access `result.getClass()` when the method returns `void` because `result == null`. The snippet assumes invocation completes normally and exceptions are handled at an appropriate caller layer.

### How is `getGenericReturnType()` different?

`getReturnType()` returns the runtime type after *type erasure*, as `Class<?>`. `getGenericReturnType()` returns `java.lang.reflect.Type`, which can preserve `List<String>`, `T`, or other generic types in signature metadata.

For example, `List<String> names()` has `getReturnType() == List.class`; `getGenericReturnType()` can describe `List<String>`. Even so, **a `List<String>` is a reference type**, outside primitive boxing rules. For `void` and pure primitive types, `Method.invoke`'s logic remains as explained.

## 5. Unboxing Reflection results properly

Because `Method.invoke` returns `Object`, you cannot assign it directly to an `int` variable without an appropriate type conversion:

```java
// Assume m is Method for public int count() and receiver is valid.
Object raw = m.invoke(receiver);
Integer boxed = (Integer) raw;
int count = boxed;
```

- `(Integer) raw` is a reference cast from `Object` to the actual wrapper.
- `int count = boxed` uses **unboxing** performed by Java.
- If `raw` is `null`, unboxing will throw `NullPointerException`.
- If `raw` is an incompatible wrapper (e.g., `Long` cast to `Integer`), the cast will throw `ClassCastException`.

When a method actually declares `int` and completes normally, the result of `Method.invoke` is a **non-null** `Integer`. However, general-purpose Reflection code often does not know the passed-in method beforehand; therefore, do not cast all results to `Integer`.

`Number` can be used to handle multiple numeric wrappers (`Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`), yet methods like `intValue()`, `longValue()`, etc. can **lose precision** when narrowing numbers or converting floating-point values to integers. Do not apply `Number` to `Boolean` and `Character`. If the method contract requires an exact type, check `getReturnType()` before converting rather than silently coercing all numbers to the same type.

## 6. Distinguishing three common kinds of `null`

The word `null` can appear in the **receiver**, **input arguments**, and **return result**:

| Position | Example | Meaning |
|---|---|---|
| Receiver in `invoke` | `staticMethod.invoke(null)` | Valid: static method does not need an instance |
| Receiver in `invoke` | `instanceMethod.invoke(null)` | Invalid: instance method needs a valid object; can throw `NullPointerException` |
| Argument in `invoke` | `method.invoke(obj, (Object) null)` | Passes **one null argument** to a method with one compatible reference parameter; does not mean the method returns null |
| Return value | `Object result = voidMethod.invoke(obj)` | `null` is the standard result when the original method has type `void` and executes normally |
| Return value | `Object result = stringMethod.invoke(obj)` | Can be `null` because the reference-returning method actually returned `null` |

Specifically, `Method.invoke` is a **varargs method** with parameter type `Object... args`. If you need to pass **exactly one `null` argument** to a method taking one reference parameter, the clear way to write it is:

```java
method.invoke(receiver, (Object) null);
```

If the method declares **no parameters**, call:

```java
method.invoke(receiver);
```

For multiple parameters, pass arguments in order. Do not arbitrarily pass `null` to a primitive parameter: the call needs to unbox the input value, yet `null` has no corresponding primitive value, so reflective invocation cannot complete as a valid call.

The example `method.invoke(receiver, (Object) null)` only pertains to **input**. The method's return type still governs whether `invoke`'s result is boxed or `null` upon normal completion.

## 7. When a method throws an exception, does it return `null`?

**No.** If code executing inside the method throws an exception, the `Method.invoke` call typically throws `InvocationTargetException` wrapping the original exception:

```java
try {
    Object result = method.invoke(receiver);
    System.out.println("Completed with result: " + result);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable original = ex.getCause();
    System.err.println("Method failed: " + original.getClass().getName());
}
```

This is an **illustrative snippet**, with variables `method` and `receiver` supplied from the calling environment. When a `void` method **runs successfully**, `result` receives `null`. When a `void` method **throws an exception**, the assignment to `result` does not complete normally; there is no `null` result to inspect.

Also separate exceptions occurring **before the method is invoked**:

- `NoSuchMethodException`: method not found in `Class.getMethod`/`getDeclaredMethod`.
- `IllegalAccessException`: Reflection is not permitted to invoke the member under access rules.
- `IllegalArgumentException`: wrong argument types/count, wrong receiver type, or invalid invocation conditions.
- `NullPointerException`: `null` receiver for an instance method or a null-related error at the caller; when the method itself internally throws `NullPointerException`, that error is typically the **cause of `InvocationTargetException`**.
- `ExceptionInInitializerError` and class initialization errors can occur when actually invoking a static method whose class has not yet initialized cleanly.

Do not use `result == null` to conclude that the call failed: that can be the **normal** result of `void` or of a reference-returning method.

## 8. Application in dynamic method-invocation tools

An API/plugin invoker or framework may not know the return types of the methods it handles in advance. To represent results accurately, preserve **both metadata and value**:

```java
// Illustrative snippet; method/receiver/arguments are provided by the caller.
Class<?> returnType = method.getReturnType();
Object value = method.invoke(receiver, arguments);

if (returnType == void.class) {
    // Succeeded, with no return value per signature.
} else if (value == null) {
    // Reference-typed method returned null.
} else {
    // Result object present: wrapper for primitive,
    // or reference object returned from the method.
}
```

In a general result API, you can represent "no return value per signature" with one distinct state, and "has a reference return type with a null value" with another state. Avoid collapsing both cases into the same `null` label if API consumers need to tell them apart.

If a serialization system receives values from `invoke`:

- For primitive returns, `Integer`/`Boolean`/... wrappers can be handled by the serializer as ordinary values.
- For `void`, there is no payload per signature; the application can represent success with a bodyless response, status, or separate task info.
- For a reference returning `null`, an API contract might allow a nullable payload, omitted field, or error message depending on business semantics. Reflection **does not** decide these semantics for you.

**Performance note:** boxing/unboxing and reflective dispatch overhead can matter in very hot loops. Measure first and design to requirements; do not interpret seeing `Integer` in `invoke`'s result as proof that a brand-new object is allocated on every single call.

## 9. Common conceptual mistakes

1. **"If a method returns `int`, `invoke` also returns `int`."** False: the `invoke` API returns `Object`, and primitives are boxed into wrappers.
2. **"`void` is boxed into `Void`."** False: `void` has no value and `invoke` returns **`null`**, without creating a `Void` instance.
3. **"If `invoke` returns `null`, the method must be `void`."** False: a method with a reference return type can also genuinely return `null`.
4. **"A primitive-typed method can return `null` when its value is 0."** False: `0`, `false`, and other primitive values are still boxed normally.
5. **"`getReturnType()` returns `Integer.class` if the method declares `int`."** False: `getReturnType()` is `int.class`, while the `invoke` result object is `Integer`.
6. **"`Void.class` and `void.class` are the same."** False: `Void` is a reference type; `void` is the keyword indicating no return value.
7. **"`touch()` is `void`, so its code does not run when Reflection calls it."** False: the code still executes and can have side effects; it simply has no return value.
8. **"`null` from a method returning `Integer` unboxes to 0."** False: unboxing a `null` reference throws `NullPointerException`.
9. **"If a method throws an exception, `invoke` returns `null`."** False: the invocation does not complete normally; `InvocationTargetException` is typically thrown.
10. **"A `null` receiver means the method returns `null`."** False: a `null` receiver is valid for static methods and is completely independent of the return value.

## 10. Self-check questions

**Question 1.** A method declares `public double price() { return 1.5; }`. What object type does `Method.invoke(obj)` return?

**Answer:** `Double` containing `1.5`, typed as `Object`. `getReturnType()` remains `double.class`.

**Question 2.** `public void save() { System.out.println("saved"); }` is called via `invoke`. Does the print statement run, and what does `invoke` return?

**Answer:** Yes, the method actually runs and prints `saved`. Upon normal completion, `invoke` returns `null`.

**Question 3.** `public String lookup() { return null; }` and `public void clear() { }` both make `invoke` return `null`. How do you tell which case has no return value per signature?

**Answer:** Use `method.getReturnType() == void.class`. For `lookup`, the return type is `String.class` and the actual value is `null`; for `clear`, the return type is `void.class`.

**Question 4.** What is `getReturnType()` for a method declared `Integer count()`, and is `invoke` guaranteed to be non-`null`?

**Answer:** `Integer.class`. Not guaranteed: `Integer` is a reference type so the method can return `null`.

**Question 5.** When calling `public int compute() { throw new IllegalStateException(); }` via Reflection, is the result an `Integer` containing a default value?

**Answer:** No. Because the method throws an exception, the call fails; `Method.invoke` throws `InvocationTargetException` with `IllegalStateException` as its cause. There is no normal return value to box.

**Question 6.** Why shouldn't you call `result.getClass()` immediately after every `invoke`?

**Answer:** Because `result` can be `null` for a `void` method or a reference-returning method yielding null. Calling `result.getClass()` then throws `NullPointerException`; check `result == null` and `getReturnType()` first.

## Standard Java references

- Java SE API — `java.lang.reflect.Method.invoke(Object, Object...)`: how methods are invoked, boxing primitive returns, `null` result for `void`, and `InvocationTargetException`.
- Java SE API — `java.lang.reflect.Method.getReturnType()`, `getGenericReturnType()`: return type metadata.
- Java Language Specification — §5.1.7 *Boxing Conversion*, §5.1.8 *Unboxing Conversion*, §8.4.5 *Method Result*, §14.17 *The return Statement*.
- Java SE API — `java.lang.Void`: reference class representing the `void` type in certain APIs using `Class` or generics.

**Takeaway:** `Method.invoke` always has return type **`Object`**. Primitive returns are **boxed into wrappers**; a `void` method completing normally makes **`invoke` return `null`**. Reference-returning methods can also return `null`; use **`getReturnType()`** to distinguish the two cases, and handle exceptions separately from return results.