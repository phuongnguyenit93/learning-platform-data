# Primitives and Wrappers Do Not Have an Inheritance Relationship in Place of Boxing

When working with Java Reflection, we often encounter two seemingly related representations: a primitive type like `int` and a wrapper class like `Integer`. Both have corresponding `Class<?>` objects, yet **boxing/unboxing is a value conversion rule of the Java language, not an inheritance relationship between two types**. Therefore, type-relationship inspection APIs and reflective method-invocation APIs can yield different results while remaining completely consistent.

This article focuses on accurately reading `Class`, `isAssignableFrom`, `isInstance`, looking up method signatures, passing arguments via `Method.invoke`, and accessing `Field`.

## 1. Distinguishing Primitives, Wrappers, and Boxing

Java has primitive types such as `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Each primitive has a corresponding wrapper class: `Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`.

| Perspective | `int` | `Integer` |
| --- | --- | --- |
| Type kind | Primitive | Reference type (class) |
| Value | Direct integer value | Reference to an object holding an integer |
| `Class` token | `int.class` or `Integer.TYPE` | `Integer.class` |
| `isPrimitive()` | `true` | `false` |
| Inherits from `Number`/`Object` | No | `Integer` inherits from `Number`, and `Number` inherits from `Object` |
| Can accept `null` | No | Yes |
| `instanceof` | Cannot be used directly on primitive values | Can be used on wrapper objects |

Example where the Java compiler automatically inserts appropriate conversions:

```java
int primitive = 7;
Integer boxed = primitive;   // boxing: int -> Integer
int restored = boxed;       // unboxing: Integer -> int
Number number = primitive;  // boxing int -> Integer, then widening reference -> Number
Object object = primitive;  // boxing int -> Integer, then widening reference -> Object
```

`Integer` does not `extends int`; primitives are not classes in the inheritance tree. **Being assignable thanks to conversion** does not mean **having a subtype relationship**.

We also need to separate two other concepts: `int` can *widen* to `long` in numeric conversion contexts, yet `long` is not a superclass of `int`. And there is no general rule automatically converting `Integer` to `Long` just because the numeric value can change from `int` to `long`.

## 2. Class Tokens Represent Type Identity, Not Boxing

`int.class` and `Integer.class` are two distinct `Class` objects. `Integer.TYPE` is merely a constant referencing `int.class`, **not** `Integer.class`:

```java
System.out.println(int.class == Integer.TYPE);       // true
System.out.println(int.class == Integer.class);      // false
System.out.println(int.class.isPrimitive());         // true
System.out.println(Integer.class.isPrimitive());     // false
```

`Class` itself can describe primitives even though primitives are not objects in the `Object` inheritance hierarchy. For example, `int.class.getSuperclass()` returns `null`; `Integer.class.getSuperclass()` returns `Number.class`.

`value.getClass()` is always called on an **object**. With `int n = 7;`, the expression `((Object) n).getClass()` returns `Integer.class` because the compiler boxed `n` when casting to `Object`. You cannot infer from this that the object at runtime has class `int.class`.

## 3. `isAssignableFrom` Checks Type Relationships, Does Not Simulate Assignment with Conversion

Read the expression `Destination.class.isAssignableFrom(Source.class)` as: can a value of **Source type** be treated as **Destination type** via the same type or an appropriate widening type relationship? For reference types, this check inspects class/interface inheritance. For primitives, only that exact primitive type itself is compatible under this check. The API does **not** account for boxing, unboxing, or primitive widening like `int → long`.

| Expression | Result | Reason |
| --- | --- | --- |
| `Integer.class.isAssignableFrom(int.class)` | `false` | `int` is not a subtype of `Integer` |
| `int.class.isAssignableFrom(Integer.class)` | `false` | `Integer` is not a subtype of `int` |
| `Object.class.isAssignableFrom(int.class)` | `false` | Primitives do not inherit from `Object` |
| `Object.class.isAssignableFrom(Integer.class)` | `true` | `Integer` is a reference subtype of `Object` |
| `Number.class.isAssignableFrom(Integer.class)` | `true` | `Integer extends Number` |
| `long.class.isAssignableFrom(int.class)` | `false` | Primitive widening is not assignability per the API |
| `int.class.isAssignableFrom(int.class)` | `true` | Same type |

Note: the "assignable" phrasing in the API name can be misleading if you infer that it performs every conversion accepted by Java assignment syntax. For example, `Integer boxed = 7;` is valid thanks to boxing, yet `Integer.class.isAssignableFrom(int.class)` is still `false`.

## 4. `isInstance` Checks Runtime Objects

`someClass.isInstance(value)` checks whether `value` is an instance of the represented reference type; `null` always yields `false`. `int.class.isInstance(...)` is always `false` because no Java object has runtime class `int`:

```java
Integer value = Integer.valueOf(7);

System.out.println(Integer.class.isInstance(value)); // true
System.out.println(Number.class.isInstance(value));  // true
System.out.println(Object.class.isInstance(value));  // true
System.out.println(int.class.isInstance(value));     // false
System.out.println(Integer.class.isInstance(null));  // false
```

Here `value` is an `Integer` object. When writing `int.class.isInstance(7)`, the number `7` is boxed first to pass into the `Object` parameter of `isInstance`, yet the `int.class` token still does not represent the runtime type of that object.

**API selection rule:** `isPrimitive()` to identify the kind of `Class`; `isAssignableFrom` to check type relationships; `isInstance` to check an actual object at runtime. None of these APIs replaces the full set of compiler conversion rules.

## 5. Looking Up Methods by Exact Signature; Invoking Methods Performs Argument Conversion

This is the easiest point to confuse in Reflection: **method lookup** and **method invocation** are two distinct steps.

Suppose a class has `void consume(int n)`:

- `getMethod("consume", int.class)` finds the exact signature and succeeds; `getMethod("consume", Integer.class)` cannot find that signature and throws `NoSuchMethodException`.
- Once you have the `Method` corresponding to `int`, `method.invoke(target, Integer.valueOf(5))` can run: arguments to `Method.invoke` pass through `Object...`, and when invoking the target method, reflection unboxes `Integer` to `int`.
- If the target method takes `long`, an `Integer` argument can be **unboxed to `int` and then widened to `long`**.
- Reflection does not automatically choose an overload from argument objects: you must look up the exact `int.class`, `long.class`, or `Integer.class` for the method you want to call.

These rules do not turn `Integer` into a subtype of `int` or `long`; this is **invocation conversion at call time**. A `Long` passed to an `int` parameter is rejected because it requires narrowing; an `Integer` passed to a `Long` parameter is also rejected because no such wrapper-to-wrapper conversion exists. For a primitive parameter, `null` cannot be unboxed and is rejected.

### Standalone Runnable Java 17+ Example

Save the following snippet into `BoxingAndReflectionDemo.java`. The program clearly distinguishes `Class` checks, signature lookup, `Method.invoke`, and reading/writing a primitive field.

```java
public class BoxingAndReflectionDemo {
    public static class Target {
        public int count = 3;

        public void takeInt(int x) {
            System.out.println("takeInt=" + x);
        }

        public void takeLong(long x) {
            System.out.println("takeLong=" + x);
        }

        public void takeInteger(Integer x) {
            System.out.println("takeInteger=" + x);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("int.class.isPrimitive(): "
                + int.class.isPrimitive());
        System.out.println("Integer.class.isPrimitive(): "
                + Integer.class.isPrimitive());
        System.out.println("Integer.class.isAssignableFrom(int.class): "
                + Integer.class.isAssignableFrom(int.class));
        System.out.println("int.class.isAssignableFrom(Integer.class): "
                + int.class.isAssignableFrom(Integer.class));
        System.out.println("Number.class.isAssignableFrom(Integer.class): "
                + Number.class.isAssignableFrom(Integer.class));
        System.out.println("Object.class.isAssignableFrom(int.class): "
                + Object.class.isAssignableFrom(int.class));
        System.out.println("int.class.isInstance(Integer.valueOf(1)): "
                + int.class.isInstance(Integer.valueOf(1)));
        System.out.println("Integer.class.isInstance(Integer.valueOf(1)): "
                + Integer.class.isInstance(Integer.valueOf(1)));

        try {
            Target.class.getMethod("takeInt", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("getMethod(Integer.class): NOT_FOUND");
        }

        Target target = new Target();
        Target.class.getMethod("takeInt", int.class)
                .invoke(target, Integer.valueOf(5));
        Target.class.getMethod("takeLong", long.class)
                .invoke(target, Integer.valueOf(8));

        try {
            Target.class.getMethod("takeInt", int.class)
                    .invoke(target, Long.valueOf(5));
        } catch (IllegalArgumentException e) {
            System.out.println("Long -> int: REJECTED");
        }

        java.lang.reflect.Field field = Target.class.getField("count");
        Object read = field.get(target);
        System.out.println("field.get returns: "
                + read.getClass().getSimpleName() + "=" + read);

        field.set(target, Integer.valueOf(9));
        System.out.println("field int after set: " + target.count);
        try {
            field.set(target, null);
        } catch (IllegalArgumentException e) {
            System.out.println("null -> primitive: REJECTED");
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac BoxingAndReflectionDemo.java
java BoxingAndReflectionDemo
```

Output:

```text
int.class.isPrimitive(): true
Integer.class.isPrimitive(): false
Integer.class.isAssignableFrom(int.class): false
int.class.isAssignableFrom(Integer.class): false
Number.class.isAssignableFrom(Integer.class): true
Object.class.isAssignableFrom(int.class): false
int.class.isInstance(Integer.valueOf(1)): false
Integer.class.isInstance(Integer.valueOf(1)): true
getMethod(Integer.class): NOT_FOUND
takeInt=5
takeLong=8
Long -> int: REJECTED
field.get returns: Integer=3
field int after set: 9
null -> primitive: REJECTED
```

Explanation of three key results:

1. `getMethod("takeInt", Integer.class)` fails because the declaration uses `int`; Java signatures are not "equivalent" merely because the compiler has boxing.
2. `takeInt=5` and `takeLong=8` occur because the reflective invocation API receives wrapper values and then applies **unboxing**, combined with **primitive widening** when valid. This is not the result of `isAssignableFrom`.
3. `Field.get(target)` returns `Object`; when reading the `int count` field, reflection creates/returns an `Integer` wrapper. Conversely, `Field.set(target, Integer.valueOf(9))` unboxes to write the `int` field. `null` cannot be assigned to a primitive.

## 6. Argument Conversion Table to Remember

This table describes **arguments passed to target method parameters via `Method.invoke`**, not the result of `Class.isAssignableFrom` and not the lookup rules of `getMethod`.

| Actual argument object type | Declared parameter | On reflective invocation | Reason |
| --- | --- | --- | --- |
| `Integer` | `int` | Accepted | Unboxing |
| `Integer` | `long` | Accepted | Unboxing then primitive widening |
| `Byte` | `double` | Accepted | Unboxing then primitive widening |
| `Long` | `int` | Rejected | No implicit primitive narrowing |
| `Integer` | `Long` | Rejected | No implicit conversion from one wrapper to another |
| `Integer` | `Number` or `Object` | Accepted | Reference widening |
| `null` | `int` | Rejected | Primitives do not accept `null` |
| `null` | `Integer` | Accepted | Reference types accept `null` |

Because the declaration `Method.invoke(Object obj, Object... args)` accepts arguments via `Object...`, if in caller code you write `invoke(target, 5)`, the Java compiler first boxes `5` into `Integer` to place it into the `Object[]` array. Reflection can then unbox `Integer` back to the target `int` parameter. **Two different conversion points**, not two types having an inheritance relationship.

If an argument of the wrong type is passed at the reflection layer, you usually get `IllegalArgumentException`. If *code inside the target method itself* throws an exception, `Method.invoke` wraps the cause in `InvocationTargetException`; do not confuse the two cases when diagnosing errors.

## 7. Fields and Primitive Arrays Follow the Same Principle

For a `Field`, the declared type is accurately described by `field.getType()`. If the field is declared `int`, the result is `int.class`, **not** `Integer.class`:

```java
java.lang.reflect.Field field =
        BoxingAndReflectionDemo.Target.class.getField("count");
System.out.println(field.getType() == int.class); // true
```

`Field.get(Object)` always returns `Object`, so primitive values are boxed in the result. When writing via `Field.set(Object, Object)`, the API can unbox wrappers and perform permitted primitive widening; `Field.setInt`, `Field.getInt`, and specialized primitive getters/setters are options when you want to express the data type more explicitly.

Arrays `int[]` and `Integer[]` remain different types:

```java
System.out.println(int[].class.isAssignableFrom(Integer[].class)); // false
System.out.println(Integer[].class.isAssignableFrom(int[].class)); // false
```

Reflective `java.lang.reflect.Array.get(intArray, index)` returns `Object`, so the `int` element is boxed. That does not make `int[]` inherit from `Integer[]` or vice versa.

## 8. Common Mistakes When Designing Reflection Code

**Mistake 1 — Using `isAssignableFrom` to check whether an argument can be passed to a primitive.** For example, `long.class.isAssignableFrom(Integer.class)` is `false`, yet an `Integer` can be unboxed and widened to be passed to a `long` parameter in a reflective call. If you want to build your own argument checker, you must explicitly account for `null`, reference subtypes, the corresponding wrapper, and the primitive widening table rather than relying on a single `isAssignableFrom` call.

**Mistake 2 — Replacing `int.class` with `Integer.class` when looking up a `Method`/`Constructor`.** `getMethod`, `getDeclaredMethod`, and constructor lookup APIs use exact declared parameter types; the existence of boxing does not change the signature. For example, `void save(int id)` must be looked up with `int.class`. If both `save(int)` and `save(Integer)` exist, those are **two separate overloads**.

**Mistake 3 — Thinking `getClass()` on a boxed value reveals the original primitive type.** `Object obj = 10;` holds a reference to an `Integer`, so `obj.getClass() == Integer.class`. The information "originally was `int`" is no longer retained in the object's runtime class.

**Mistake 4 — Conflating numeric widening with inheritance.** `int → long` is a primitive conversion; it does not make `int.class.isAssignableFrom(long.class)` or the reverse become `true`. Similarly, widening `int → long` does not create an `Integer → Long` conversion.

**Mistake 5 — Ignoring `null` and exceptions.** Unboxing turns `null` into an error; via reflection, `null` to a primitive is rejected at the invocation layer. Do not automatically catch every exception and treat it as "incompatible", because an error thrown by the method body means something different from an argument-passing error.

## 9. Workflow When Writing a Reflection Library

When looking at a value and a target type, distinguish the question before choosing an API:

1. **Analyzing declarations?** Use `getParameterTypes()`, `getReturnType()`, `Field.getType()`, and preserve primitive tokens like `int.class`.
2. **Checking pure type relationships?** Use `isAssignableFrom` for true subtype/identity semantics; do not add boxing into the conclusion.
3. **Checking an existing instance?** Use `isInstance` for reference objects, handling `null` separately.
4. **Passing values into an invocation?** Determine primitive vs. reference; for primitives, check wrapper/unboxing and widening; for references, check `null` and reference relationships.
5. **Looking up overloads?** Specify the exact `Class<?>` list matching the signature; `Method.invoke` does not choose an overload for you.
6. **Reading results or fields?** Remember that the reflection interface returns `Object` which may box primitive values; do not infer backward that the declared type is a wrapper.

**Quick self-check:** If `Method m` represents `void f(long n)`, both `m.getParameterTypes()[0] == long.class` and `long.class.isAssignableFrom(Integer.class) == false` are true; yet `m.invoke(instance, Integer.valueOf(3))` can still invoke `f` successfully. That invocation capability comes from *unboxing + primitive widening*, never from inheritance.

## Key Takeaways

- **Type relationships:** `int` and `Integer` are two distinct types that do not inherit from each other; `Integer` sits in the class hierarchy `Number → Object`.
- **Value conversions:** boxing/unboxing and widening are conversions in contexts permitted by Java.
- **Reflection APIs:** `isAssignableFrom`/`isInstance` describe types and objects; `getMethod` requires exact signatures; `Method.invoke` and `Field.set` have their own argument conversion rules.

Distinguishing the three layers **type identity → method lookup → invocation conversion** will help accurately explain every seemingly "contradictory" result between primitives and wrappers in Java Reflection.
