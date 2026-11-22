# `Constructor.newInstance` with Properly Typed Argument Lists

## 1. From Constructor Signature to Initialization Arguments

In Java Reflection, `java.lang.reflect.Constructor<T>` represents **an identified constructor**, while `newInstance(Object... initargs)` uses that constructor to create and initialize an object.

Basic workflow:

1. Identify the exact constructor of the class using the **declared parameter type list**, in order.
2. Prepare the list of **argument values** with count and types compatible with that constructor.
3. Call `constructor.newInstance(args...)`; handle errors involving argument count, types, access permissions, and exceptions thrown during initialization.

For example, a class has the constructor `Order(String, long)`. To look it up, pass `String.class` and `long.class`. To invoke it, pass a value of type `String` and a value that can be validly converted to `long`.

~~~java
Constructor<Order> ctor =
        Order.class.getConstructor(String.class, long.class);

Order order = ctor.newInstance("Notebook", 3L);
~~~

The snippet above only illustrates syntax in a context where class `Order` exists and exceptions are declared/handled. **`getConstructor` takes types; `newInstance` takes values.** Do not confuse these two lists.

## 2. Selecting a Constructor: Must Match the Exact Declared Types

Common lookup methods:

| API | Scope | How it matches |
| --- | --- | --- |
| `Class.getConstructor(Class<?>... parameterTypes)` | `public` constructors of the class | Matches exact list of declared parameter types |
| `Class.getDeclaredConstructor(Class<?>... parameterTypes)` | Constructors declared in the class, including non-public | Also matches exact parameter types |
| `Class.getConstructors()` | `public` constructors | Returns metadata to iterate over, does not auto-select |
| `Class.getDeclaredConstructors()` | Constructors declared in the class | Returns metadata to iterate over, including non-public |

For example, with a class having two constructors `Order(String, int)` and `Order(String, long)`:

- `getConstructor(String.class, int.class)` retrieves the first constructor.
- `getConstructor(String.class, long.class)` retrieves the second constructor.
- `getConstructor(String.class, Integer.class)` **does not automatically find** `Order(String, int)`. If there is no constructor with the exact `Integer` type, it throws `NoSuchMethodException`.

The compiler has an **overload resolution** mechanism when processing the expression `new Order("A", 1)`. Reflection does not re-run that algorithm when looking up a constructor: calling `getConstructor` requires an exact signature.

Similarly, `getConstructor()` searches for a **no-arg** constructor; if not found, it throws `NoSuchMethodException`, even if the class has parameterized constructors or a non-`public` no-arg constructor.

The parameter types used during lookup are the **erased** types at runtime. If a constructor declares `Order(List<String> items)`, the parameter type for lookup is `List.class`; there is no `List<String>.class`.

## 3. How Does `newInstance` Validate and Convert Arguments?

Signature:

~~~java
public T newInstance(Object... initargs)
        throws InstantiationException,
               IllegalAccessException,
               IllegalArgumentException,
               InvocationTargetException
~~~

This is the API signature for explanation, not a method declaration to copy into an application class.

Once the right `Constructor<T>` has been obtained, `newInstance` requires the actual arguments to be **positionally compatible** with the constructor's formal parameters. The runtime can automatically **unbox** wrappers and perform appropriate **widening conversions**; it does not automatically narrow primitive types (*narrowing*) and does not re-run the overload selection algorithm.

| Declared parameter | Argument passed to `newInstance` | Result |
| --- | --- | --- |
| `long` | `Long.valueOf(3)` | Valid: unboxing `Long → long` |
| `long` | `Integer.valueOf(3)` | Valid: unboxing `Integer → int`, then widening `int → long` |
| `int` | `Long.valueOf(3)` | Invalid: requires narrowing `long → int` |
| `Number` | `Integer.valueOf(3)` | Valid: `Integer` reference is a `Number` |
| `Integer` | `Long.valueOf(3)` | Invalid: different wrapper type, not automatically converted to `Integer` |
| `String` | `null` | Valid: reference type can accept `null` |
| `long` | `null` | Invalid: cannot unbox `null` |
| `long` | `"3"` | Invalid: Reflection does not parse strings into numbers |

Primitive types passed in Java calling code are **boxed into Object** by the varargs syntax `newInstance(Object...)`. Accepting that wrapper and converting it to a primitive parameter is a separate step performed by Reflection.

Errors due to wrong argument count, wrong position, incompatible type, or disallowed narrowing typically cause `IllegalArgumentException`, **not** `NoSuchMethodException`. `NoSuchMethodException` belongs to the *constructor lookup* stage, before calling `newInstance`.

### Static Type of Variables vs. Runtime Value

If you have `Object quantity = Integer.valueOf(3)`, when calling `ctor.newInstance("Notebook", quantity)` Reflection looks at the runtime value `Integer`. If the selected constructor takes `long`, it can unbox and widen. However, `getConstructor(String.class, Object.class)` cannot be used to find constructor `(String, long)`, because lookup requires the exact declared types.

Do not take `arg.getClass()` and treat that as the constructor type list to search for. This fails for `null`, primitives (already boxed), and overloads taking a superclass or interface.

## 4. Runnable Java 17+ Example

Create the file **`ConstructorArgumentsDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.util.Arrays;

public class ConstructorArgumentsDemo {
    public static class Order {
        private final String summary;

        public Order(String name, long quantity) {
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity must be >= 0");
            }
            summary = name + " x" + quantity;
        }

        public Order(String name, String... labels) {
            summary = name + " " + Arrays.toString(labels);
        }

        @Override
        public String toString() {
            return summary;
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Order> numeric =
                Order.class.getConstructor(String.class, long.class);

        System.out.println("exact lookup: "
                + Arrays.toString(numeric.getParameterTypes()));
        System.out.println("widening: "
                + numeric.newInstance("Notebook", Integer.valueOf(3)));

        try {
            Order.class.getConstructor(String.class, Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup(Integer): NoSuchMethodException");
        }

        try {
            numeric.newInstance("Notebook", "3");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "invoke(String quantity): IllegalArgumentException");
        }

        try {
            numeric.newInstance("Notebook", (Object) null);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "invoke(null primitive): IllegalArgumentException");
        }

        Constructor<Order> labels =
                Order.class.getConstructor(String.class, String[].class);

        System.out.println("isVarArgs: " + labels.isVarArgs());
        System.out.println("array argument: "
                + labels.newInstance(
                        "Notebook", (Object) new String[]{"A", "B"}));

        try {
            labels.newInstance("Notebook", "A", "B");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "expanded arguments: IllegalArgumentException");
        }

        try {
            numeric.newInstance("Notebook", -1L);
        } catch (InvocationTargetException e) {
            System.out.println(
                    "constructor threw: " + e.getCause().getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac ConstructorArgumentsDemo.java
java ConstructorArgumentsDemo
~~~

Exact output:

~~~text
exact lookup: [class java.lang.String, long]
widening: Notebook x3
lookup(Integer): NoSuchMethodException
invoke(String quantity): IllegalArgumentException
invoke(null primitive): IllegalArgumentException
isVarArgs: true
array argument: Notebook [A, B]
expanded arguments: IllegalArgumentException
constructor threw: quantity must be >= 0
~~~

Explanation:

1. `getConstructor(String.class, long.class)` finds the exact declared signature; `Integer.valueOf(3)` is a **callable argument** for the constructor taking `long` due to unboxing followed by widening.
2. `getConstructor(String.class, Integer.class)` fails at **lookup**: there is no constructor taking `Integer`; this error occurs before object creation.
3. `numeric.newInstance("Notebook", "3")` and `numeric.newInstance("Notebook", (Object) null)` already identified the constructor, but the **argument has the wrong type** for `long`, so `IllegalArgumentException` occurs.
4. The constructor declared as `String... labels` is reflected as a **`String[]`** parameter. When calling `newInstance`, that array must be passed in **a single argument slot**; `(Object) new String[]{...}` expresses this explicitly.
5. Calling `labels.newInstance("Notebook", "A", "B")` passes **three actual arguments** to a constructor that only has **two declared parameters** (`String`, `String[]`). Reflection does not automatically pack the two strings into the target constructor's varargs array.
6. The `Order(String, long)` constructor itself throws `IllegalArgumentException` when the quantity is negative. Reflection wraps exceptions **originating inside the constructor** in `InvocationTargetException`; retrieve the original exception via `getCause()`.

The example uses a `static` nested class and `public` constructors, so `setAccessible` and passing an enclosing instance are not needed.

## 5. Varargs: Distinguishing Two Layers of `...`

The most common point of confusion is that there are **two places where varargs appear**:

- Target constructor: `Order(String name, String... labels)`, represented at runtime by the type list `(String, String[])`.
- Reflection API: `Constructor.newInstance(Object... initargs)`, which accepts an `Object[]` array containing **the arguments used to invoke the target constructor**.

Model:

~~~text
Constructor to invoke: Order(String, String[])
                               ^
                               | String[] array is a single argument
newInstance(Object... initargs)
    Object[0] = "Notebook"
    Object[1] = new String[]{"A", "B"}
~~~

Therefore:

~~~java
Constructor<Order> ctor =
        Order.class.getConstructor(String.class, String[].class);

// Correct: two arguments for the target constructor, position 2 is String[].
Order a = ctor.newInstance(
        "Notebook", (Object) new String[]{"A", "B"});

// Wrong for the target constructor: three arguments, not auto-packed into String[].
// ctor.newInstance("Notebook", "A", "B");
~~~

The snippet above illustrates with the already-defined `Order` class. `(Object)` avoids confusing the varargs layer of `newInstance` itself; manually packing with `new Object[]{"Notebook", new String[]{"A", "B"}}` also produces the right argument list.

**Not automatically expanding target varargs** is a special rule to remember: `Constructor`'s `isVarArgs() == true` property does not make Reflection perform variable-argument call syntax like the compiler does.

For a **no-arg** constructor, calling `ctor.newInstance()` or `ctor.newInstance(new Object[0])` both work. The Javadoc also allows the `initargs` array to be `null` when the constructor takes no parameters, but `newInstance()` is clearer and less error-prone.

## 6. `null`, Argument Arrays, and Exact Order

Each argument corresponds to its **parameter position**:

~~~java
// Suppose there is a constructor User(String name, Integer age):
Constructor<User> ctor =
        User.class.getConstructor(String.class, Integer.class);

User u = ctor.newInstance("Mai", null);
~~~

This is an illustrative snippet; a matching `User` class is required. `null` is valid at the `Integer` position because it is a reference type. However, `null` is invalid for `int` or `long`.

Distinguish:

- `ctor.newInstance((Object) null)`: passes **one actual argument** with value `null`.
- `ctor.newInstance((Object[]) null)`: passes a **null `initargs` argument array** to the Reflection API; use this form only if you clearly understand the API rules, especially for a no-arg constructor.
- `ctor.newInstance(new Object[]{"Mai", null})`: passes **two explicit arguments**.
- `ctor.newInstance("Mai", null)`: convenient syntax corresponding to two arguments for a constructor taking `String`, `Integer`.

If arguments are swapped in position, such as `(Integer, String)` instead of `(String, Integer)`, Reflection does not reorder them automatically. It checks position 1, 2, ... sequentially against the exact selected constructor.

For dynamic data (JSON, forms, or configuration), **do not infer constructors solely from runtime values**. Design a schema mapping each parameter clearly and convert string/numeric data to the desired types before invoking Reflection.

## 7. Non-Public Constructors and the Java Platform Module System

`getDeclaredConstructor(...)` can retrieve metadata for `private`, `protected`, or package-private constructors, but metadata does not equal permission to invoke:

~~~java
Constructor<Example> ctor =
        Example.class.getDeclaredConstructor(String.class);

if (!ctor.canAccess(null) && !ctor.trySetAccessible()) {
    throw new IllegalAccessException(
            "Cannot open access to constructor");
}

Example value = ctor.newInstance("demo");
~~~

This is an illustrative snippet for an `Example` class, not a standalone Java file. **`Constructor.canAccess` must receive `null`**, because there is no target object yet before creating the instance. `trySetAccessible()` returns `false` when the flag to bypass access checks cannot be enabled under JPMS conditions; `setAccessible(true)` can throw `InaccessibleObjectException`.

When a package belongs to a **named module** that is not appropriately opened, Reflection code from another module cannot arbitrarily access private members. `opens` or `--add-opens` permissions must be configured intentionally; `exports` only permits public access paths within the export scope and does not automatically allow deep reflection.

Recommendation: prefer supported public constructors/factory methods. Only open Reflection access where genuinely needed, and check the permission-request result before invoking.

## 8. Constructors of Non-Static Inner Classes

For a non-static inner class:

~~~java
class Outer {
    class Inner {
        Inner(String message) { }
    }
}
~~~

An `Outer.Inner` instance is always tied to an `Outer` instance. Therefore, the compiler adds an **enclosing instance parameter** to the reflected constructor. A typical lookup example is:

~~~java
Outer owner = new Outer();

Constructor<Outer.Inner> innerCtor =
        Outer.Inner.class.getDeclaredConstructor(
                Outer.class, String.class);

// In the example where classes are in a valid access context:
Outer.Inner value = innerCtor.newInstance(owner, "hello");
~~~

This snippet illustrates within a Java context with valid access permissions; place the code in a location compatible with the visibility of the classes. Passing `"hello"` while forgetting `owner` will cause the argument count/types not to match. For **`static`** nested classes, this enclosing instance parameter does not exist.

Some compiler-generated constructors also have hidden/synthetic parameters, so when actual metadata differs from source code, inspect `getParameterTypes()`, `getParameterCount()`, and `getParameters()` rather than guessing from the signature shown in an IDE.

## 9. Error Categories to Distinguish

| Error | Where it occurs | How to identify |
| --- | --- | --- |
| `NoSuchMethodException` | Lookup `getConstructor` / `getDeclaredConstructor` | Requested parameter type list does not exist |
| `IllegalArgumentException` | `newInstance` | Wrong argument count/type, invalid narrowing, or attempting to instantiate an enum via Reflection |
| `IllegalAccessException` | `newInstance` | Caller lacks permission to access a controlled constructor |
| `InvocationTargetException` | `newInstance` | **The target constructor itself** threw an exception; inspect `getCause()` |
| `InstantiationException` | `newInstance` | Cannot create instance due to class nature, e.g. abstract class |
| `ExceptionInInitializerError` | Class initialization during `newInstance` | Static initializer failed |
| `InaccessibleObjectException` | Possibly at `setAccessible(true)` | Cannot enable deep reflection permission due to module boundaries |

**Special distinction:** if `newInstance` arguments have the wrong type, `IllegalArgumentException` comes directly from the API. But if the constructor runs and **the constructor itself** throws `IllegalArgumentException`, Reflection wraps it in `InvocationTargetException`. These are two cases with different handling paths.

Do not attempt to reflectively invoke an `enum` constructor: `Constructor.newInstance` forbids creating enums this way, even when constructor metadata exists. Interfaces, primitive types, and arrays also do not have ordinary constructors to look up like concrete classes.

## 10. The Legacy `Class.newInstance()` Case

`Class.newInstance()` has been **deprecated since Java 9**. Main limitations:

- Only invokes the no-arg constructor.
- Can directly propagate exceptions thrown by the constructor, including checked exceptions, making the exception contract unclear.
- Handling of non-public constructors does not match obtaining a `Constructor` and controlling access explicitly.

Instead:

~~~java
T value = clazz.getDeclaredConstructor().newInstance();
~~~

This is illustrative syntax when `clazz` has type `Class<T>` and the caller handles Reflection exceptions. If the constructor is non-public, access permissions must still be satisfied according to the rules.

## 11. Checklist for Calling `newInstance` Correctly

1. **Verify the class can be instantiated**: a concrete class, not an enum invoked via Reflection; watch out for static initialization.
2. **Look up the right constructor**: use `getConstructor` for public, `getDeclaredConstructor` when metadata at any access level is needed; pass `Class<?>...` with the exact count and order.
3. **Inspect the runtime signature**: `getParameterTypes()` and `getParameterCount()`; if `isVarArgs()`, the last parameter is an **array**.
4. **Prepare the `Object[]` arguments**: convert string data to actual domain types; evaluate wrappers, unboxing, widening, `null`, and inner enclosing instances.
5. **Check access permissions**: `canAccess(null)`; only request expanded access when necessary and permitted.
6. **Invoke `newInstance` and classify errors**: lookup errors, argument errors, access errors, and errors from the target constructor are distinct categories.
7. **Do not resolve overloads by array order**: if dynamic constructor selection is needed, build explicit selection rules and handle ambiguous cases; avoid grabbing the first constructor from `getConstructors()`.

### Self-Check

**Question 1:** A constructor is declared `(String, long)`. Can `getConstructor(String.class, Integer.class)` find it?  
**No.** Lookup requires the exact type `long.class`.

**Question 2:** Having found the `(String, long)` constructor, is `newInstance("A", Integer.valueOf(2))` valid?  
**Yes.** `Integer` is unboxed to `int`, then widened to `long`.

**Question 3:** The target constructor is declared `(String, String...)`. Does passing three arguments `"A", "B", "C"` to `newInstance` automatically pack `"B", "C"` into `String[]`?  
**No.** Prepare exactly two arguments: `"A"` and a `String[]`.

**Question 4:** `newInstance` throws `InvocationTargetException`. Is it always due to wrong argument types?  
**No.** It usually indicates **the constructor code ran and threw an exception**; call `getCause()` to see the root error.

**Question 5:** Does being able to find a private constructor with `getDeclaredConstructor` mean it can always be invoked?  
**No.** Java access control and module restrictions must be satisfied.

**Key takeaway:** `getConstructor(...)` finds the **exact signature**; `Constructor.newInstance(...)` executes the **selected constructor** with matching argument count and types. Understanding these two steps clearly avoids common bugs with primitives/wrappers, `null`, varargs, and exceptions.

### References

- [JDK 17 — `Constructor<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [JDK 17 — `Class.getConstructor` and `getDeclaredConstructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Dev.java — Invoking Constructors](https://dev.java/learn/api/reflection-method-handles/reflection/constructors/)
- [Java Language Specification §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9)
