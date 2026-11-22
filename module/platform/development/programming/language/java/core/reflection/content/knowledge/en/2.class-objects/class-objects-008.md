# Why Does `int.class` Differ from `Integer.class`?

In Java, `int` is a **primitive type**, whereas `Integer` is a **reference type** (class) used to represent an integer value as an object. Therefore, `int.class` and `Integer.class` return **two different `Class` objects**, describing two different Java types. The autoboxing mechanism does not make them the same type.

## 1. What does `.class` actually represent?

In Java, the expression `TypeName.class` is a *class literal*: it returns the `java.lang.Class` object representing the specified type. This syntax applies to classes, interfaces, arrays, and primitive types alike.

- `int.class`: the `Class` object representing the **primitive type `int`**. Despite the API name `Class`, `int` is not an ordinary class, has no objects of type `int`, and has no constructors or superclass.
- `Integer.class`: the `Class` object representing the **`java.lang.Integer` class**. `Integer` is a `final` class extending `Number`, used with objects and providing methods such as `parseInt`, `valueOf`, `compare`.
- Both have expression types compatible with `Class<?>`, yet each `Class` object stores information about **one separately represented type**.

This is similar to how `String.class` differs from `Object.class`: being represented by the same `Class` API does not mean being the same type.

## 2. Comparison via Reflection

| Check | `int.class` | `Integer.class` |
| --- | --- | --- |
| Described Java type | Primitive `int` | Reference `java.lang.Integer` |
| `getName()` | `"int"` | `"java.lang.Integer"` |
| `isPrimitive()` | `true` | `false` |
| `getSuperclass()` | `null` | `Number.class` |
| `isInstance(Integer.valueOf(10))` | `false` | `true` |
| Can be used as type argument in `List<T>` | No: `List<int>` is invalid | Yes: `List<Integer>` is valid |
| Used in method signatures | Parameter/return value `int` | Parameter/return value `Integer` |

One frequently confusing detail is the constant `Integer.TYPE`: **`Integer.TYPE == int.class`**, whereas **`Integer.TYPE != Integer.class`**. The `TYPE` field on wrapper classes holds the `Class` object of the corresponding primitive type; it is not an alias for `Integer.class`.

### Standalone runnable Java 17+ example

Save the complete code below in the file `IntVsIntegerClass.java`:

~~~java
import java.lang.reflect.Method;

public class IntVsIntegerClass {
    public static void accept(int value) {
    }

    public static void accept(Integer value) {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> primitive = int.class;
        Class<?> wrapper = Integer.class;

        System.out.println(primitive == wrapper);
        System.out.println(primitive.getName());
        System.out.println(wrapper.getName());
        System.out.println(primitive.isPrimitive());
        System.out.println(wrapper.isPrimitive());
        System.out.println(primitive.getSuperclass());
        System.out.println(wrapper.getSuperclass().getName());
        System.out.println(Integer.TYPE == primitive);
        System.out.println(wrapper.isInstance(Integer.valueOf(10)));
        System.out.println(primitive.isInstance(Integer.valueOf(10)));

        Method primitiveMethod =
                IntVsIntegerClass.class.getMethod("accept", int.class);
        Method wrapperMethod =
                IntVsIntegerClass.class.getMethod("accept", Integer.class);

        System.out.println(primitiveMethod.equals(wrapperMethod));
        System.out.println(primitiveMethod.getParameterTypes()[0].getName());
        System.out.println(wrapperMethod.getParameterTypes()[0].getName());
    }
}
~~~

Compile and run in a terminal with JDK 17 or newer:

~~~bash
javac IntVsIntegerClass.java
java IntVsIntegerClass
~~~

Expected output:

~~~text
false
int
java.lang.Integer
true
false
null
java.lang.Number
true
true
false
false
int
java.lang.Integer
~~~

Explanation of the key lines:

1. `primitive == wrapper` is `false` because the two `Class` objects represent two different types.
2. `isPrimitive()` is only true for `int.class`; `Integer.class` describes an actual object class.
3. `getSuperclass()` of a primitive type returns `null`; the direct superclass of `Integer` is `Number`.
4. `isInstance(Object)` checks whether **the passed object** is an instance of the described type. An `Integer` object cannot be an instance of a primitive type, so `int.class.isInstance(...)` returns `false`.
5. Reflection finds two distinct `accept` methods: one taking `int`, one taking `Integer`. They do not have the same signature.

## 3. Why doesn't autoboxing make the two `Class` objects equal?

**Autoboxing** lets the compiler convert an `int` value into an `Integer` reference when the context requires a wrapper type; **unboxing** converts back to a primitive value. Example:

~~~java
int number = 42;
Integer boxed = number;      // autoboxing, semantically equivalent to Integer.valueOf(number)
int again = boxed;           // unboxing, equivalent to boxed.intValue()
~~~

This is a **value conversion at compile/runtime**, not an inheritance relationship; it creates no identity between the two types and does not change the `Class` objects. Therefore:

- `int.class == Integer.class` remains `false`.
- `Integer.class.isAssignableFrom(int.class)` is `false` and `int.class.isAssignableFrom(Integer.class)` is also `false`; this API checks assignability based on reference-type relationships, not treating autoboxing as inheritance.
- An `int` variable has no `getClass()` method; writing `number.getClass()` when `number` is `int` causes a compile error. To query the primitive type, use `int.class` or `Integer.TYPE`.
- When `boxed` is an `Integer` object, `boxed.getClass() == Integer.class` is `true` (provided `boxed` is non-`null`).

Note that `Integer` can hold `null`, whereas `int` cannot. Unboxing a `null` value throws `NullPointerException`:

~~~java
Integer missing = null;
// int value = missing; // If executed, throws NullPointerException.
~~~

The commented snippet above illustrates the risk, not a separate program.

## 4. Direct impact when using Reflection

### 4.1. Method lookup must use the exact declared parameter types

`Class.getMethod(String, Class<?>...)` and `Class.getDeclaredMethod(String, Class<?>...)` look up **the exact parameter signature**. If there is a method `process(int)`, calling `getMethod("process", Integer.class)` does not automatically fall back to `getMethod("process", int.class)`.

In the standalone example in section 2, the two lookups below point to two separate overloads:

~~~java
Method primitiveMethod =
        IntVsIntegerClass.class.getMethod("accept", int.class);
Method wrapperMethod =
        IntVsIntegerClass.class.getMethod("accept", Integer.class);
~~~

If the class only declares the `accept(int)` overload, querying with `Integer.class` throws `NoSuchMethodException`. The same rule applies when comparing return types with `Method.getReturnType()`, field types with `Field.getType()`, and parameter types with `Method.getParameterTypes()`.

**Distinguish lookup time from invocation time:** `Method.invoke` can automatically unbox an `Integer` object to pass to an `int` parameter (and perform certain valid primitive widening conversions) when invoking an already found method. That does not change the signature or the result of `getMethod`.

### 4.2. Do not use `Class.forName("int")` to get a primitive type

`Class.forName("java.lang.Integer")` looks up the wrapper class by its full name. However, `Class.forName("int")` does not accept primitive names that way and throws `ClassNotFoundException`. When you need the `Class` of a primitive, obtain it directly via `int.class` or `Integer.TYPE`. When reading a type from Reflection, use `isPrimitive()` to distinguish it.

### 4.3. Array types are not the same either

`int[].class` and `Integer[].class` both have `isArray() == true`, yet they are two distinct array classes. `getComponentType()` yields `int.class` and `Integer.class`, respectively. An `int[]` array stores primitive elements; an `Integer[]` array stores references to `Integer` objects (and can contain `null` elements).

You cannot directly convert `int[]` to `Integer[]` via autoboxing; to convert, you must transform each element individually.

## 5. How to choose the right `Class` in real code

- **Signatures declaring primitives** (e.g., `void setAge(int age)`, `int getCount()`, a `Field` of type `int`): use `int.class` when comparing or looking up via Reflection.
- **Signatures declaring wrappers** (e.g., `void setAge(Integer age)`, `Integer findCount()`, a field of type `Integer`): use `Integer.class`.
- **Frameworks/mappers handling both forms:** you can write explicit mapping logic from `int.class` to `Integer.class` (and vice versa) if the problem treats them as equivalent; do not assume `Class.equals` or `isAssignableFrom` performs this conversion.
- **Generic data structures:** use `Integer` because type arguments of generics must be reference types. For large integer datasets where object overhead should be avoided, an `int[]` array may be more suitable than `Integer[]`; choose based on `null` requirements, API, and actual performance.

## 6. Common mistakes and self-check

| Misconception | Correct understanding |
| --- | --- |
| "`int.class` is `Integer.class` after boxing." | Boxing converts **values**, not type identity. |
| "`Integer.TYPE` is `Integer.class`." | `Integer.TYPE` is `int.class`. |
| "`getMethod` automatically applies boxing to find overloads." | You must specify `int.class` or `Integer.class` matching the declared signature. |
| "Every `int` value has `getClass()`." | Primitives are not objects; use a class literal. |
| "`isAssignableFrom` returns true because Java autoboxes." | This check does not treat boxing as reference-type assignability. |
| "`int[].class` and `Integer[].class` are the same." | Their components are primitive and wrapper, respectively; two independent array types. |

Predict the output yourself before trying on Java 17:

~~~java
System.out.println(int.class == Integer.TYPE);              // true
System.out.println(int.class.isPrimitive());                // true
System.out.println(Integer.class.isPrimitive());            // false
System.out.println(int[].class.getComponentType() == int.class); // true
System.out.println(Integer.class.isAssignableFrom(int.class));  // false
~~~

The final snippet consists of illustrative statements to place **inside a method** (such as `main`); it is not a standalone Java file.

**Remember:** `int.class` refers to the **primitive value type `int`**; `Integer.class` refers to the **`Integer` object class**. Java supports converting between their values in certain contexts, but Reflection still distinguishes the two types strictly.