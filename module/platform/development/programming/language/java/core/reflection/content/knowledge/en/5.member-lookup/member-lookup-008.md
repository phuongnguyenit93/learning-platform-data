# Primitive Parameter Types Differ from Wrapper Parameter Types in Reflection Member Lookup

## 1. The Core Issue

In Java, a *primitive* parameter and a *wrapper* parameter have **different declared types**, even though regular Java code can automatically box/unbox when calling a method.

For example, the following two declarations are **two valid overloads**:

```java
public void handle(int count) { /* ... */ }
public void handle(Integer count) { /* ... */ }
```

When looking up via Reflection, parameter signatures are matched against the corresponding `Class` objects:

| Declared Type | Reflection Representation | `getTypeName()` | `isPrimitive()` |
| --- | --- | --- | --- |
| `int` | `int.class` | `int` | `true` |
| `Integer` | `Integer.class` | `java.lang.Integer` | `false` |
| `boolean` | `boolean.class` | `boolean` | `true` |
| `Boolean` | `Boolean.class` | `java.lang.Boolean` | `false` |
| `long` | `long.class` | `long` | `true` |
| `Long` | `Long.class` | `java.lang.Long` | `false` |

**Invariant to remember:** `int.class != Integer.class`. The member lookup algorithm by `parameterTypes` does not automatically box/unbox, does not perform numeric widening, and does not pick overloads like the Java compiler.

`Integer.TYPE` is the `Class<Integer>` constant representing the primitive `int` type, so `Integer.TYPE == int.class` is `true`. However, `Integer.TYPE` is **not** `Integer.class`.

## 2. Which APIs Are Affected?

| API | Kind of Member Looked Up | Rule for Parameters |
| --- | --- | --- |
| `type.getMethod(name, parameterTypes...)` | `public` method, including inherited | Parameter `Class` objects must match exactly |
| `type.getDeclaredMethod(name, parameterTypes...)` | Method declared directly in the class, including `private` | Exact match; does not search superclasses |
| `type.getConstructor(parameterTypes...)` | `public` constructor of the class | Exact match |
| `type.getDeclaredConstructor(parameterTypes...)` | Constructor declared in the class, including non-`public` | Exact match |

Suppose a class only has `void onlyInt(int value)`:

```java
Example.class.getMethod("onlyInt", int.class);      // Found
Example.class.getMethod("onlyInt", Integer.class);  // NoSuchMethodException
Example.class.getMethod("onlyInt", short.class);    // NoSuchMethodException
```

You cannot rely on Java allowing an `Integer` to be passed to `onlyInt(5)` or converting `short` to `int` to assume Reflection lookup will find the method.

## 3. Complete Example Runnable on Java 17+

Save the following code as `PrimitiveVsWrapperReflection.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public class PrimitiveVsWrapperReflection {
    public static class Example {
        public Example(int initialValue) {
        }

        public void handle(int count) {
            System.out.println("int: " + count);
        }

        public void handle(Integer count) {
            System.out.println("Integer: " + count);
        }

        public void onlyInt(int count) {
        }

        private void hidden(long count) {
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("int == Integer: " + (int.class == Integer.class));
        System.out.println("Integer.TYPE == int.class: " + (Integer.TYPE == int.class));

        Method primitiveMethod = Example.class.getMethod("handle", int.class);
        Method wrapperMethod = Example.class.getMethod("handle", Integer.class);

        System.out.println("Primitive parameter: "
                + primitiveMethod.getParameterTypes()[0].getTypeName());
        System.out.println("Wrapper parameter: "
                + wrapperMethod.getParameterTypes()[0].getTypeName());

        Example example = new Example(0);
        primitiveMethod.invoke(example, Integer.valueOf(3));
        wrapperMethod.invoke(example, Integer.valueOf(4));

        try {
            Example.class.getMethod("onlyInt", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("No method onlyInt(Integer)");
        }

        Constructor<Example> constructor = Example.class.getConstructor(int.class);
        System.out.println("Constructor parameter: "
                + constructor.getParameterTypes()[0].getTypeName());

        try {
            Example.class.getConstructor(Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("No constructor(Integer)");
        }

        Method privateMethod = Example.class.getDeclaredMethod("hidden", long.class);
        System.out.println("Private method parameter: "
                + privateMethod.getParameterTypes()[0].getTypeName());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac PrimitiveVsWrapperReflection.java
java PrimitiveVsWrapperReflection
```

Expected output:

```text
int == Integer: false
Integer.TYPE == int.class: true
Primitive parameter: int
Wrapper parameter: java.lang.Integer
int: 3
Integer: 4
No method onlyInt(Integer)
Constructor parameter: int
No constructor(Integer)
Private method parameter: long
```

Meaning of each step:

1. `int.class` and `Integer.class` are two non-identical `Class` objects; `Integer.TYPE` is `int.class`.
2. The two `getMethod("handle", ...)` calls return two different `Method` objects, because the declared signatures `(int)` and `(Integer)` differ.
3. `getParameterTypes()` reflects the **parameter types in the declaration**, not the data types of arguments passed at invocation time.
4. `getMethod("onlyInt", Integer.class)` throws `NoSuchMethodException`; the name really exists, but the `(Integer)` signature does not.
5. Constructor `Example(int)` is looked up with `int.class`, while `Integer.class` does not match.
6. `getDeclaredMethod("hidden", long.class)` finds the `private` method declared on the class; the example only looks up metadata and does not invoke the private method.

## 4. Distinguishing **Lookup** and **Invocation**

These are two stages with different rules:

```text
Lookup: Class.getMethod("handle", int.class)
    → finds the exact member with declared parameter int

Invocation: Method.invoke(instance, Integer.valueOf(3))
    → after the Method is found, the Integer argument can be unboxed to int
```

- **At lookup time:** `getMethod`/`getConstructor` matches the exact declared types; no boxing/unboxing, no primitive widening (for example, `short.class` does not match `int.class`).
- **At `Method.invoke`/`Constructor.newInstance` time:** Reflection can unbox wrapper values for primitive parameters and apply valid **primitive widening** (for example, an `Integer` value for a `long` parameter). Arbitrary primitive narrowing is not applied (for example, `Long` to `int`).
- **With wrapper parameters:** `Integer` is a reference type, accepting `null` and compatible reference values. If the parameter declaration is `int`, passing `null` at invoke time is invalid and causes `IllegalArgumentException`. No `null` belongs to a primitive type.
- **With overloads:** once a `Method` object is obtained, `invoke` executes that exact chosen method. It does not re-select the `handle(Integer)` overload merely because the runtime argument is an `Integer`.

Thus, the Java call `example.onlyInt(Integer.valueOf(3))` compiles thanks to unboxing, yet `Example.class.getMethod("onlyInt", Integer.class)` still fails.

## 5. Inspecting and Constructing the Exact Signature

When working with code whose declarations are unknown, list and inspect the `Class` of each parameter:

```java
for (Method method : Example.class.getDeclaredMethods()) {
    if (method.getName().equals("handle")) {
        for (Class<?> parameter : method.getParameterTypes()) {
            System.out.println(parameter.getTypeName()
                    + ", primitive=" + parameter.isPrimitive());
        }
    }
}
```

The two corresponding output lines will show one parameter as `int, primitive=true` and the other as `java.lang.Integer, primitive=false` (do not rely on the order of the returned method array).

If you know the signature uses a primitive, pass `int.class` or `Integer.TYPE`; if the signature uses a wrapper, pass `Integer.class`. Likewise for `long.class`/`Long.TYPE` and `Long.class`, `boolean.class`/`Boolean.TYPE` and `Boolean.class`.

Do not use `Class.forName("int")` to obtain the `Class` for a primitive: the name `int` is not the binary name of a class loadable that way. Use `int.class` or `Integer.TYPE` directly.

## 6. Similar Easily Confused Situations

- **Primitive arrays and wrapper arrays:** `int[].class` differs from `Integer[].class`; `int[]` is not automatically converted to `Integer[]`. Even though both arrays themselves are reference types, their `getComponentType()` values are `int.class` and `Integer.class`, respectively.
- **Varargs in declarations:** `void accept(int... values)` has one parameter of type `int[]`; look it up with `getMethod("accept", int[].class)`, not `int.class`.
- **Return type:** `getMethod` does not accept return type as a search criterion; `getReturnType()` helps inspect it after the method is found. Distinguishing primitives and wrappers here refers to **parameters**.
- **Access scope:** switching from `getMethod` to `getDeclaredMethod` only adjusts the search scope between `public` and directly declared members; it does not make `Integer.class` automatically match `int.class`.

## 7. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `NoSuchMethodException` despite seeing `method(int)` in source | Looked up with `Integer.class` | Use `int.class` |
| Cannot find constructor `Example(int)` | Looked up with `Integer.class` or `short.class` | Use `getConstructor(int.class)` |
| Found `Method` but `invoke` fails on arguments | Runtime value does not convert validly to declared type; e.g., `null` for `int` | Check `getParameterTypes()`, values, and invoke conversion rules |
| Looking up `private void hidden(long)` with `getMethod` fails | `getMethod` only considers `public` members | Use `getDeclaredMethod("hidden", long.class)` if declaration lookup is needed |
| Mistaking `Integer.TYPE` for `Integer.class` | `TYPE` points to primitive `int` | Distinguish `Integer.TYPE == int.class` from `Integer.class` |

**Self-check:** For a class having only `void run(long value)`, both `getDeclaredMethod("run", Long.class)` and `getDeclaredMethod("run", int.class)` fail to find it. Only `getDeclaredMethod("run", long.class)` matches; afterward, calling `invoke(target, Integer.valueOf(5))` can succeed thanks to unboxing `Integer` to `int` and then widening to `long`.

**Takeaway:** Reflection lookup is based on **declared parameter types**, whereas boxing/unboxing of **arguments at invocation time** is a separate mechanism.