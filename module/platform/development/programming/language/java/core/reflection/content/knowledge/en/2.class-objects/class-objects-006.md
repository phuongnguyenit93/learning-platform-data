# `Class<T>`, `Class<?>`, and Type-Checking Limits in Java Reflection

## 1. Learning objectives

After this lesson, you can:

- Understand how a `java.lang.Class` object represents a type at runtime, and how the type parameter `T` in `Class<T>` enables compile-time type checking.
- Distinguish `Class<String>`, `Class<?>`, `Class<? extends Number>`, and how to use them properly when writing Reflection APIs.
- Use `Class.isInstance`, `Class.cast`, `Class.isAssignableFrom`, and `Class.asSubclass` for runtime type checks; understand the direction of type relationships and the limits of each check.
- Accurately identify what type information is removed (*type erasure*) and why `List<String>` cannot be verified using `List.class` alone.
- Apply *class tokens* in a generic API without assuming the JVM can verify every type argument.

## 2. What is `Class` and what does `T` mean?

Each `Class` object describes a type known to the JVM at runtime: a class, interface, enum, record, array, primitive type, or `void`. `String.class` returns the `Class` object describing `java.lang.String`; `someObject.getClass()` reveals the object's actual class. Within the scope of one class loader defining a class, the JVM maintains one corresponding `Class` object; two classes with the same name defined by different class loaders can be two distinct types.

The declaration `Class<T>` is *parameterized* so the compiler tracks the relationship between the class token and type `T`:

```java
Class<String> stringType = String.class;
Class<Integer> integerType = Integer.class;
Class<?> unknownType = String.class;
```

`T` in `Class<T>` is a **compile-time** type parameter, not a different runtime version of the `Class` class. All three variables above reference a `Class` object; they differ in the assignments and result types the compiler accepts.

The following example **does not compile**:

```java
Class<Object> objectType = String.class; // Error: Class<String> is not Class<Object>
Class<String> textType = Integer.class; // Error: incompatible type tokens
```

Because generics in Java are *invariant*, `String` extending `Object` does not make `Class<String>` extend `Class<Object>`. If you simply want to hold an arbitrary token, use `Class<?>`.

## 3. `Class<T>` versus `Class<?>`

| Declaration | What is known at compile time | Suitable cases |
| --- | --- | --- |
| `Class<String>` | Token representing `String` | APIs needing the exact type `String` |
| `Class<T>` | Token matching an inferred/declared type parameter `T` | Generic methods or classes needing to return `T` safely |
| `Class<?>` | There is a class token, but the specific type is unknown | Inspecting metadata, reading Reflection, storing tokens of various types |
| `Class<? extends Number>` | Token of a class that is `Number` or a subclass | Constraining tokens to a hierarchy |
| `Class<? super Integer>` | Token of `Integer` or one of its supertypes | Working with tokens having a supertype bound |

Example:

```java
Class<?> a = String.class;
Class<?> b = Integer.class;
Class<? extends Number> numberType = Double.class;

// Invalid: Double.class has type Class<Double>, not Class<Number>.
// Class<Number> exactNumber = Double.class;
```

`Class<?>` **does not mean** `Class<Object>`. The `?` represents an unknown type (*wildcard capture*). You can still call `getName()`, `getDeclaredMethods()`, `isInterface()`, or `isInstance(...)`; however, the result of `type.cast(value)` when `type` is `Class<?>` can only be safely used as `Object` without additional information.

```java
Class<?> type = String.class;
Object value = type.cast("hello"); // Valid; compile time has not proven it is String
// String s = type.cast("hello");   // Does not compile: lacking proof of String type
```

Conversely, with `Class<String>`, the compiler knows the `cast` method returns `String`:

```java
Class<String> type = String.class;
String value = type.cast("hello"); // No explicit cast needed
```

You should not convert `Class<?>` to `Class<String>` merely via an unchecked cast: doing so forfeits the benefits of the type system and can lead to runtime errors.

## 4. Ways to obtain a `Class` object

| Way to obtain | Expression/result type | Notes |
| --- | --- | --- |
| `String.class` | `Class<String>` | Class known at compile time; no instance needed |
| `Integer.class` | `Class<Integer>` | Token for the `Integer` wrapper |
| `int.class` | `Class<Integer>` per class literal typing rules | Token still describes **primitive `int`**, distinct from `Integer.class` |
| `String[].class` | `Class<String[]>` | Arrays retain component type information at runtime |
| `obj.getClass()` | `Class<? extends ...>` based on the erased static type of the expression | Returns the actual class; `obj == null` causes `NullPointerException` |
| `Class.forName("java.lang.String")` | `Class<?>` | Looks up class by name; can throw `ClassNotFoundException` and triggers class initialization by default |

Example:

```java
String text = "Java";
Class<?> runtimeType = text.getClass();
Class<?> loadedType = Class.forName("java.lang.String");

System.out.println(runtimeType == loadedType); // true under normal class-loader setups
System.out.println(int.class == Integer.class); // false
```

The class's simple name (`getSimpleName()`) and full name (`getName()`) are type-describing metadata; by themselves they do not verify an object's generic structure. With `Class.forName`, only load class names from controlled configuration/input if the program uses Reflection to instantiate objects or invoke members; do not treat loading a class as confirmation that the class satisfies an interface.

## 5. Type checks that `Class` supports at runtime

### 5.1. `isInstance(Object)`: does the object belong to this type?

`type.isInstance(value)` is equivalent in runtime checking semantics to `value instanceof SomeKnownType`, except `type` can be determined dynamically.

```java
System.out.println(Number.class.isInstance(Integer.valueOf(7))); // true
System.out.println(String.class.isInstance(7));                  // false
System.out.println(String.class.isInstance(null));               // false
```

The call returns `boolean` and does not change the variable's type to `T`. For primitive tokens specifically: `int.class.isInstance(Integer.valueOf(7))` returns `false` because an `Integer` object is not an instance of the primitive type `int`.

### 5.2. `cast(Object)`: checking and casting with a token

The `Class<T>.cast(Object)` method has a signature returning `T`. When the object is incompatible, it throws `ClassCastException`. For `null`, `cast(null)` returns `null`.

```java
static <T> T requireType(Object value, Class<T> expected) {
    return expected.cast(value);
}

String ok = requireType("Java", String.class);
// String bad = requireType(123, String.class); // Compiles, throws ClassCastException
```

Because the parameter `value` only has type `Object`, the compiler **cannot guarantee** that the input data matches the expected type. The compiler guarantees the *API's return type* is `T`, while `Class.cast` performs the actual class check at runtime. If you want clearer error reporting, you can check `expected.isInstance(value)` before calling `cast`; remember to handle `null` separately per business requirements.

### 5.3. `isAssignableFrom(Class<?>)`: direction of assignment relationship

`Target.class.isAssignableFrom(Source.class)` returns `true` if a value of `Source` can be assigned to a variable of type `Target` according to the runtime relationship between classes/interfaces (including the same type). **Read left to right: target receives source**.

```java
System.out.println(Number.class.isAssignableFrom(Integer.class)); // true
System.out.println(Integer.class.isAssignableFrom(Number.class)); // false
System.out.println(CharSequence.class.isAssignableFrom(String.class)); // true
```

This check operates on `Class` objects, does not inspect an instance, and does not verify type arguments of `List<String>`. Primitive tokens are only compatible with that exact primitive type in this check; there is no automatic boxing rule as in ordinary Java method calls.

### 5.4. `asSubclass(Class<U>)`: narrowing a token to a parent type

`candidate.asSubclass(Base.class)` checks whether `candidate` is `Base` or a subclass/implementation of `Base`. On success it returns `Class<? extends Base>`; on failure it throws `ClassCastException`.

```java
Class<?> discovered = Integer.class;
Class<? extends Number> numericType = discovered.asSubclass(Number.class);

// discovered.asSubclass(Runnable.class); // Throws ClassCastException at runtime
```

This is a reasonable way to filter classes discovered via Reflection before treating them as a plugin, strategy, or implementation of an API. `asSubclass` verifies the **inheritance/implements relationship**, not whether a constructor exists, member access permissions, or application runtime conditions.

## 6. Complete example: type tokens and runtime checks (Java 17+)

Create the file `ClassTokenDemo.java`:

```java
public class ClassTokenDemo {
    static <T> T requireType(Object value, Class<T> expected) {
        return expected.cast(value);
    }

    static void describe(Class<?> type, Object value) {
        System.out.println(type.getSimpleName() + ": " + type.isInstance(value));
    }

    public static void main(String[] args) {
        Class<String> textType = String.class;
        Class<?> unknownType = Integer.class;
        Class<? extends Number> numberType =
                unknownType.asSubclass(Number.class);

        System.out.println(textType.getSimpleName());
        System.out.println(unknownType.getName());
        System.out.println(numberType.getSimpleName());
        System.out.println(Number.class.isAssignableFrom(Integer.class));

        describe(String.class, "Java");
        describe(String.class, 42);

        String name = requireType("HELLO", textType);
        System.out.println(name.toLowerCase());

        try {
            requireType(42, textType);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile and run:

```bash
javac ClassTokenDemo.java
java ClassTokenDemo
```

Expected output:

```text
String
java.lang.Integer
Integer
true
String: true
String: false
hello
ClassCastException
```

Here `textType` helps the compiler infer `T = String` for `requireType`. The token `unknownType` only knows there is a class; `asSubclass(Number.class)` verifies that the class belongs to the `Number` family and returns an appropriately bounded token type. Notice the line `requireType(42, textType)` is still valid at compile time: the error is only caught at runtime, right where `Class.cast` checks the object.

## 7. Key limitation: *type erasure* and generics are not fully verified

The information `Class` retains at runtime is the *reified* type such as `String`, `Integer`, `List`, `String[]`. For most generic types, the JVM does not store the concrete type arguments of individual `List<String>` or `List<Integer>` instances inside the `Class` object. Both lists have the runtime class `ArrayList` if both were created via `new ArrayList<>()`.

The following syntax examples are **invalid in Java**:

```java
// Class<List<String>> tokens = List<String>.class; // This class literal does not exist
// boolean ok = obj instanceof List<String>;         // Cannot check the String type argument
```

You can use `List.class` or `obj instanceof List<?>` to check that an object is a `List`; you cannot conclude from that that all elements are `String`. Casting `(List<String>) object` on a value only known to be `Object` typically produces an *unchecked cast* warning, because the compiler cannot verify the type arguments.

Runnable example `ErasureDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;

public class ErasureDemo {
    List<String> declaredNames;

    public static void main(String[] args) throws Exception {
        List<String> names = new ArrayList<>();
        names.add("Ada");

        List<Integer> scores = new ArrayList<>();
        scores.add(10);

        System.out.println(names.getClass() == scores.getClass());
        System.out.println(List.class.isInstance(names));
        System.out.println(List.class.isInstance(scores));

        Field field = ErasureDemo.class.getDeclaredField("declaredNames");
        Type declaredType = field.getGenericType();
        System.out.println(declaredType.getTypeName());
        System.out.println(declaredType instanceof ParameterizedType);
    }
}
```

Run:

```bash
javac ErasureDemo.java
java ErasureDemo
```

Output:

```text
true
true
true
java.util.List<java.lang.String>
true
```

There are two layers of information that must be kept separate:

1. `names.getClass()` and `scores.getClass()` only indicate the list's runtime class, so they are identical. `List.class.isInstance(...)` only confirms the `List` interface and **does not check element types**.
2. `Field.getGenericType()` can read the `List<String>` declaration from the generic signature metadata of the **field** `declaredNames`; that is information about the member's declaration, **not** proof that every object assigned to the field/list always contains `String` at runtime. `Type` and `ParameterizedType` describe declared types; they do not turn a `Class<List>` into a token capable of validating every element.

If business logic needs to verify `List<String>` when receiving untrusted data, you must check the container **and each element**, or use a decoding/schema-validation mechanism that checks structure. For example:

```java
static boolean isStringList(Object candidate) {
    if (!(candidate instanceof java.util.List<?> list)) {
        return false;
    }
    for (Object item : list) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

The snippet above is an illustrative method to place inside a Java 17+ class; its convention is **not accepting `null` elements**, because `null instanceof String` is `false`. If `null` is allowed, the condition must be adjusted according to domain requirements. An empty list returns `true` under the rule "every element is a `String`", which does not imply a generic argument can be inferred from an empty list.

## 8. Using `Class<T>` to design safer APIs

A typical scenario is retrieving an object from a shared store, then checking with a class token before returning a concrete type:

```java
import java.util.Map;

public class TypedLookupDemo {
    static <T> T lookup(Map<String, Object> values,
                        String key,
                        Class<T> expectedType) {
        Object value = values.get(key);
        if (value == null) {
            throw new IllegalArgumentException("Missing value: " + key);
        }
        return expectedType.cast(value);
    }

    public static void main(String[] args) {
        Map<String, Object> values = Map.of("port", 8080, "host", "localhost");
        Integer port = lookup(values, "port", Integer.class);
        String host = lookup(values, "host", String.class);
        System.out.println(host + ":" + port);
    }
}
```

```bash
javac TypedLookupDemo.java
java TypedLookupDemo
```

```text
localhost:8080
```

Benefit: calling `lookup(values, "port", Integer.class)` yields an `Integer` result without requiring an unchecked cast by the caller. Limitation: the `Map<String,Object>` store can still hold a value of the wrong type; `cast` will throw `ClassCastException` at runtime. This approach fits concrete types like `Integer`, `String`, or an interface/superclass; it does not automatically verify nested generic arguments such as `Map<String, List<Integer>>`.

In a framework/plugin using Reflection, a similar safe pattern is receiving `Class<?>` after looking up a class, then calling `asSubclass(ExpectedInterface.class)` to prove the type bound before continuing. If instantiation and method calls are also needed, you must separately check constructors, access permissions, exceptions, and the corresponding API contract.

## 9. Common mistakes and how to avoid them

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| Treating `Class<?>` as `Class<Object>` | Generics are invariant; wildcard means an unknown type | Use `Class<?>` for class inspection, `Class<T>` when tying to a `T` result |
| Thinking `Class<T>` verifies data is `T` at compile time | Input can be `Object`/dynamic data | Use `cast` or `isInstance` to check at runtime |
| Reversing `isAssignableFrom` direction | `Target.isAssignableFrom(Source)` checks target accepts source | Put target type on the left and test both directions |
| Using `List.class` to conclude `List<String>` | Erasure removes type arguments on individual instances | Check elements or use schema validation |
| Assuming `getGenericType()` is runtime validation | It returns declaration metadata | Distinguish field/method metadata from object contents |
| Treating `int.class` and `Integer.class` as the same token | Primitive and wrapper are two distinct runtime types | Pick the token matching the actual data type to check |
| Casting `Class<?>` to `Class<X>` without basis | Unchecked casts can break type promises to callers | Use `asSubclass` to check subtypes; use `cast` to check instances |
| Assuming `asSubclass` guarantees instantiation | Inheritance relationship says nothing about constructors or access | Separately check instantiation and Reflection requirements |

## 10. Self-check

1. Why can't `Class<String>` be assigned to `Class<Object>` even though `String` is an `Object`? Because `Class<T>` is invariant; to hold an arbitrary token, choose `Class<?>`.
2. What does `Number.class.isAssignableFrom(Integer.class)` return? `true`, because an `Integer` object can be assigned to a `Number` variable; the reverse direction is `false`.
3. How does `String.class.cast(42)` differ from `String.class.isInstance(42)`? The first throws `ClassCastException`; the second returns `false`.
4. Why doesn't `List.class.isInstance(List.of(1, 2))` prove the list is `List<String>`? Because it only checks the `List` type at runtime, knowing nothing about the element type arguments.
5. After `Class<?> candidate = Integer.class;`, how do you get a token bounded by `Number` without an unchecked cast? Use `Class<? extends Number> sub = candidate.asSubclass(Number.class);`; the method checks the subtype before returning.

**Remember:** `Class<T>` links the **static type `T`** to a runtime type token, `Class<?>` represents a token of unknown concrete type, and `Class.isInstance/cast/isAssignableFrom/asSubclass` only verify type relationships that actually exist at runtime. Arguments of most generic types like `List<String>` undergo erasure; do not infer that `String` can be verified just because you have `List.class`.