# Getting a `Class` Object Using a Class Literal in Java

## 1. What is a class literal?

In Java, a **class literal** is an expression of the form `TypeName.class`, used to obtain the `java.lang.Class` object representing **a type already known in the source code**. It describes a class, interface, enum, annotation, primitive type, or array type. The `.class` operator does not create an instance of the class.

```java
Class<String> stringClass = String.class;
Class<Integer> integerClass = Integer.class;
Class<?> primitiveClass = int.class;
Class<?> arrayClass = String[].class;
```

For the same type defined by the same class loader, the JVM uses the same `Class` object. Class literals are useful when you need to pass a known type to an API instead of looking up the class from a character string at runtime.

- `new String("Java")` creates a **data object** of class `String`.
- `String.class` obtains the **object describing the `String` type**; it does not create a new `String`.
- `text.getClass()` obtains the **runtime type of the `text` instance**; `text` must not be `null`.

## 2. Syntax and supported types

| Expression | Described type | Notes |
| --- | --- | --- |
| `String.class` | Class `java.lang.String` | Assignable to `Class<String>`. |
| `Runnable.class` | Interface `Runnable` | Interfaces also have a `Class` object. |
| `Override.class` | Annotation `Override` | Annotations are a special kind of interface type. |
| `Thread.State.class` | Enum `Thread.State` | Applies to enum types and nested types. |
| `int.class`, `boolean.class` | Primitive types | Different from wrappers `Integer.class`, `Boolean.class`. |
| `void.class` | The `void` type | Used to represent the `void` return type. |
| `String[].class` | Array `String[]` | Different from the element type `String.class`. |
| `int[][].class` | Two-dimensional array `int[][]` | Each dimension count is a distinct array type. |
| `java.util.List.class` | Interface `List` | Does not carry the generic argument `String`. |

**Invalid:** `List<String>.class`, because generic type arguments do not create a separate `Class` at runtime. Use `List.class`; if you need to describe the `String` argument, you need the corresponding `Type`/`ParameterizedType` mechanism—it cannot be obtained from `List.class` alone.

You also cannot use `myObject.class` to get the type of a variable. Use `myObject.getClass()` for an instance, or `MyType.class` when the type name is known in advance.

## 3. Distinguishing class literals from other ways to get `Class`

| Way to get `Class` | When is the type decided? | Requires an instance? | Characteristics |
| --- | --- | --- | --- |
| `Animal.class` | At compile time | No | Always `Animal`, the exact type written in source. |
| `animal.getClass()` | At runtime | Yes | Can be a subclass `Dog` if `animal` points to a `Dog`. |
| `Class.forName("pkg.Animal")` | At runtime, by string name | No | Can throw `ClassNotFoundException`; the single-parameter overload triggers class initialization by default. |

With `Animal animal = new Dog();`, `Animal.class` represents `Animal`, while `animal.getClass()` represents `Dog`. Both are `Class` objects, but only the second depends on the actual instance.

An important point: **merely referencing `SomeType.class` does not trigger class initialization**, so it does not run the `static initializer` just for obtaining the literal. Other actions, such as calling a `static` method, can trigger class initialization. Distinguish three things: obtaining type metadata, class initialization, and instance creation.

## 4. Standalone compilable/runnable Java 17+ example

Save the following code as `ClassLiteralDemo.java`:

```java
import java.util.List;

public class ClassLiteralDemo {
    static class Animal {}

    static class Dog extends Animal {}

    static class Lazy {
        static {
            System.out.println("Lazy initialized");
        }

        static void ping() {}
    }

    public static void main(String[] args) {
        Animal animal = new Dog();

        Class<Animal> declaredType = Animal.class;
        Class<?> runtimeType = animal.getClass();

        System.out.println("declared=" + declaredType.getSimpleName());
        System.out.println("runtime=" + runtimeType.getSimpleName());
        System.out.println("isInstance=" + declaredType.isInstance(animal));
        System.out.println("assignable="
                + declaredType.isAssignableFrom(Dog.class));

        System.out.println("string=" + (String.class == "Java".getClass()));
        System.out.println("primitive=" + (int.class == Integer.TYPE));
        System.out.println("wrapper=" + (int.class == Integer.class));
        System.out.println("array=" + String[][].class.getTypeName());
        System.out.println("interface=" + List.class.getTypeName());

        Class<?> lazyType = Lazy.class;
        System.out.println("literal=" + lazyType.getSimpleName());
        Lazy.ping();
    }
}
```

Run from the directory containing the file:

```bash
javac ClassLiteralDemo.java
java ClassLiteralDemo
```

Expected stdout:

```text
declared=Animal
runtime=Dog
isInstance=true
assignable=true
string=true
primitive=true
wrapper=false
array=java.lang.String[][]
interface=java.util.List
literal=Lazy
Lazy initialized
```

Explanation:

1. `declared=Animal` and `runtime=Dog` demonstrate that `.class` specifies the type in the source code, while `getClass()` reflects the runtime class of the instance.
2. `isInstance=true`: the `Dog` object is an `Animal`. `isAssignableFrom=true`: a `Dog` can be assigned to a variable of type `Animal`. Always pay attention to the direction `Animal.class.isAssignableFrom(Dog.class)`.
3. `String.class == "Java".getClass()` is `true` because both represent `String`.
4. `int.class == Integer.TYPE` is `true` because `TYPE` represents the primitive `int`. However, `int.class == Integer.class` is `false`, because a primitive differs from its wrapper.
5. `String[][].class.getTypeName()` describes the two-dimensional array type; `List.class` describes the `List` interface.
6. `Lazy.class` has not yet run the `static` block. The line `Lazy initialized` only appears after calling `Lazy.ping()`.

## 5. Type safety: `Class<T>` and `Class<?>`

`Class<T>` records the type `T` at the declaration level, whereas `Class<?>` is suitable when the concrete type is unknown or does not need to be constrained.

```java
Class<String> exact = String.class;
Class<?> unknown = int[].class;
Class<? extends Number> numeric = Integer.class;

// Compile error due to incompatible types:
// Class<String> wrong = Integer.class;
```

For example, `Class<String>` helps the compiler prevent accidentally assigning `Integer` metadata to a variable meant to represent `String`.

**Primitive trap:** in terms of generics, Java gives `int.class` the type `Class<Integer>` at compile time, yet that object **still represents the primitive `int`**. Therefore `int.class` and `Integer.class` are not the same `Class`. They can be distinguished using `int.class.isPrimitive()` (`true`) and `Integer.class.isPrimitive()` (`false`).

## 6. Applications when using reflection APIs

**Passing a type token to an API.** A function that takes `Class<T>` to know the exact result type can be called with `String.class`, `User.class`, etc. The compiler checks the class name, and the IDE supports navigation and refactoring/renaming.

The example below only illustrates using `Class.cast` to check/cast an already compatible object; it is **not** a data converter between arbitrary types:

```java
static <T> T asType(Object value, Class<T> targetType) {
    return targetType.cast(value);
}

// Placed inside a method when used:
String result = asType("Java", String.class);
```

If `value` is not compatible with `targetType`, `cast` throws `ClassCastException`. The snippet above illustrates individual fragments and is **not** a standalone `main` program.

**Checking type relationships and metadata.** Once you have a `Class`, you can call:

- `SomeType.class.isInstance(object)` to check whether an instance belongs to that type or a compatible subtype.
- `Base.class.isAssignableFrom(Sub.class)` to check whether type `Sub` can be assigned to a variable of type `Base`.
- `SomeType.class.getDeclaredMethods()` to retrieve methods declared directly in the class, not including inherited methods by default.

A class literal provides the **object describing the type**; APIs use it to perform lookups or checks. Techniques for accessing members and executing detailed reflection belong to other lessons.

## 7. Common mistakes

- **Confusing `.class` with `new`:** `Person.class` does not call a constructor and does not create a new `Person`.
- **Confusing the declared type with the runtime type:** `Base.class` does not change based on the instance assigned to a `Base` variable; `base.getClass()` does.
- **Confusing primitives and wrappers:** `int.class != Integer.class` even though `Integer.TYPE == int.class`.
- **Using generic arguments in a literal:** `List<String>.class` is invalid; `List.class` only describes `List` without `<String>`.
- **Calling `getClass()` on `null`:** throws `NullPointerException`; `SomeType.class` does not require an instance.
- **Inferring array names from `getName()`:** `String[].class.getName()` yields the JVM form `[Ljava.lang.String;`, whereas `getTypeName()` yields `java.lang.String[]`.
- **Comparing names while ignoring the class loader:** class identity in the JVM depends on the binary name **and the defining class loader**. Two different loaders can define two distinct classes with the same name.
- **Assuming a class literal runs the `static` block:** obtaining `SomeType.class` does not initialize the class by itself.

## 8. Self-check

**Question 1.** Given `Object value = "abc";`, are `Object.class` and `value.getClass()` the same?

**Answer:** No. The first represents `Object`, while the second is `String`.

**Question 2.** Does `int[].class == int.class` return `true` or `false`?

**Answer:** `false`, because the array `int[]` and the primitive `int` are two different types.

**Question 3.** Why can't you write `List<String>.class`?

**Answer:** A class literal describes the `Class` of a type represented directly at runtime; the generic argument `<String>` does not create a separate runtime class due to type erasure. Use `List.class` and the `Type` mechanism when parameterized type information is needed.

**Remember:** Use `TypeName.class` when **the type name is already known in the source code** and you need the metadata of that exact type. Use `instance.getClass()` when you need **the actual runtime type of the object**.