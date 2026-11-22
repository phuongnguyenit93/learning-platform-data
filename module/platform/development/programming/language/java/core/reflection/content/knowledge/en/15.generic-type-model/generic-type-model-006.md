# `WildcardType` with Upper Bounds and Lower Bounds in Java Reflection

In Java generics, the `?` symbol represents a **wildcard**: an unknown type argument at a generic type usage site. For example, `List<?>`, `List<? extends Number>`, and `List<? super Integer>` are all `ParameterizedType`s at the `List<...>` level, and each `?` inside is modeled by `java.lang.reflect.WildcardType`.

`WildcardType` is a branch of `java.lang.reflect.Type`. It provides two important methods:

- `Type[] getUpperBounds()`: gets the upper bounds of the unknown type.
- `Type[] getLowerBounds()`: gets the lower bounds of the unknown type.

This lesson focuses on reading **declared generic signatures** with Reflection, interpreting the two bound arrays, traversing nested generic types, and distinguishing generic metadata from runtime data.

## 1. Meaning of the Three Wildcard Forms

| Declaration | Upper bounds via Reflection | Lower bounds via Reflection | Meaning |
| --- | --- | --- | --- |
| `List<?>` | `[Object]` | `[]` | An unspecified type argument |
| `List<? extends Number>` | `[Number]` | `[]` | Type argument is `Number` or a subtype of `Number` |
| `List<? super Integer>` | `[Object]` | `[Integer]` | Type argument is `Integer` or a supertype of `Integer` |

The **upper bound** of `? extends T` is `T`: any actual type argument must satisfy the corresponding subtype constraint. The **lower bound** of `? super T` is `T`: the actual type argument must be `T` or a supertype of `T`.

For `?`, the default upper bound is `Object` and there is no lower bound. For `? super Integer`, the default upper bound **is still `Object`**, while the lower bound is `Integer`. Therefore, do not conclude `getUpperBounds()` is empty when the declaration uses `super`.

An easy point to mistake: `getLowerBounds().length == 0` **does not** prove the wildcard is `?`; `? extends Number` also has an empty lower array. Conversely, an upper bound of `Object` is not enough to conclude the declaration is just `?`, because `? super T` and `? extends Object` share that same upper bound.

## 2. Where Does `WildcardType` Sit in the `Type` Tree?

The generic-describing types under `java.lang.reflect.Type` include:

```text
Type
├── Class<?>            e.g. String.class, Number.class
├── ParameterizedType   e.g. List<String>, List<? extends Number>
├── TypeVariable<?>     e.g. T in class Box<T>
├── WildcardType        e.g. ?, ? extends Number, ? super Integer
└── GenericArrayType    e.g. T[] in a generic signature
```

If a field is declared as `List<? extends Number> numbers`, calling `Field.getGenericType()` returns a `ParameterizedType` representing **the entire** `List<? extends Number>`. To get `WildcardType`, you must go into `getActualTypeArguments()[0]`:

```text
Field: List<? extends Number> numbers
                 |
                 v
       field.getGenericType()
                 |
                 v
    ParameterizedType: List<? extends Number>
                 |
                 v
       getActualTypeArguments()[0]
                 |
                 v
      WildcardType: ? extends Number
             /                 \
            v                   v
    getUpperBounds()       getLowerBounds()
       [Number]                 []
```

Do not cast `field.getGenericType()` directly to `WildcardType`, because the field type here is `ParameterizedType`. For `List<String>`, the first argument is `String.class`, **not** `WildcardType`. For `List<T>`, the first argument can be `TypeVariable`.

## 3. Complete Java 17+ Program and Stdout

Save the code to `WildcardTypeDemo.java`. The program inspects fields, method parameters, nested wildcards, and bounds that are generic types; it then illustrates read/write operations under `extends`/`super`.

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class WildcardTypeDemo {
    static class Examples {
        List<?> anything;
        List<? extends Number> numbers;
        List<? super Integer> integers;
        List<? extends Comparable<String>> comparable;
        Map<String, ? super List<String>> mappings;
        List<List<? extends Number>> nested;

        void accept(List<? super Integer> values) {
        }
    }

    static Type argument(String fieldName, int index)
            throws NoSuchFieldException {
        Field field = Examples.class.getDeclaredField(fieldName);
        Type generic = field.getGenericType();
        if (!(generic instanceof ParameterizedType parameterized)) {
            throw new IllegalArgumentException("Not parameterized");
        }
        return parameterized.getActualTypeArguments()[index];
    }

    static String format(Type[] bounds) {
        return Arrays.stream(bounds)
                .map(Type::getTypeName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    static void printBounds(String label, Type type) {
        if (!(type instanceof WildcardType wildcard)) {
            throw new IllegalArgumentException("Not wildcard");
        }
        System.out.println(label
                + ": upper=" + format(wildcard.getUpperBounds())
                + "; lower=" + format(wildcard.getLowerBounds()));
    }

    public static void main(String[] args) throws Exception {
        printBounds("unbounded", argument("anything", 0));
        printBounds("extends", argument("numbers", 0));
        printBounds("super", argument("integers", 0));
        printBounds("parameterizedUpper",
                argument("comparable", 0));
        printBounds("parameterizedLower",
                argument("mappings", 1));

        Type inner = argument("nested", 0);
        ParameterizedType innerList = (ParameterizedType) inner;
        printBounds("nested",
                innerList.getActualTypeArguments()[0]);

        Method method = Examples.class.getDeclaredMethod(
                "accept", List.class);
        ParameterizedType parameter = (ParameterizedType)
                method.getGenericParameterTypes()[0];
        printBounds("method",
                parameter.getActualTypeArguments()[0]);

        System.out.println("erased="
                + Examples.class.getDeclaredField("numbers")
                        .getType().getName());

        List<? extends Number> source = List.of(1, 2);
        Number first = source.get(0);
        List<Number> storage = new ArrayList<>();
        List<? super Integer> target = storage;
        target.add(7);
        Object stored = target.get(0);

        System.out.println("producerRead=" + first);
        System.out.println("consumerRead=" + stored);
    }
}
```

In the directory containing the file, compile and run:

```bash
javac WildcardTypeDemo.java
java WildcardTypeDemo
```

Expected output:

```text
unbounded: upper=[java.lang.Object]; lower=[]
extends: upper=[java.lang.Number]; lower=[]
super: upper=[java.lang.Object]; lower=[java.lang.Integer]
parameterizedUpper: upper=[java.lang.Comparable<java.lang.String>]; lower=[]
parameterizedLower: upper=[java.lang.Object]; lower=[java.util.List<java.lang.String>]
nested: upper=[java.lang.Number]; lower=[]
method: upper=[java.lang.Object]; lower=[java.lang.Integer]
erased=java.util.List
producerRead=1
consumerRead=7
```

**Explanation of each case:**

1. `anything` is `List<?>`, so upper bound is `Object` and there is no lower bound.
2. `numbers` is `List<? extends Number>`, so upper bound is `Number`.
3. `integers` is `List<? super Integer>`, so lower bound is `Integer` and implicit upper bound is `Object`.
4. The bound of `? extends Comparable<String>` is not a simple `Class<?>` but a `ParameterizedType`; `getTypeName()` produces `java.lang.Comparable<java.lang.String>`.
5. For `Map<String, ? super List<String>>`, the wildcard is in the **second type argument** of `Map`; the lower bound `List<String>` is also a `ParameterizedType`.
6. `List<List<? extends Number>>` has an inner `List` layer. You must first pass through the type argument `List<? extends Number>`, and only then find the wildcard `? extends Number`.
7. `accept(List<? super Integer>)` is looked up with `getDeclaredMethod("accept", List.class)` because generic parameters are erased in the method signature used for lookup. Then `getGenericParameterTypes()` supplies the generic signature containing the wildcard.
8. `Field.getType()` returns `java.util.List` for `List<? extends Number>`; it contains no wildcard information. Only `Field.getGenericType()` lets you retrieve `ParameterizedType`.
9. The last two lines use ordinary collections: `? extends Number` allows reading as `Number`; `? super Integer` allows adding `Integer` and safely reading as `Object`. These constraints are checked by the compiler, not Reflection policing collections at runtime.

The program uses Java 17's pattern matching for `instanceof` and formats bounds via `Type.getTypeName()`, avoiding reliance on `toString()` of a specific implementation.

## 4. Reading Bounds via `Type[]` Instead of Casting to `Class[]`

Both `getUpperBounds()` and `getLowerBounds()` return **`Type[]`**. Elements can be `Class<?>` or more complex generic representations, especially `ParameterizedType`. Do not write code assuming every bound is `Class<?>`:

```java
// Illustrative snippet assuming you already have a WildcardType wildcard object:
for (Type upper : wildcard.getUpperBounds()) {
    System.out.println(upper.getTypeName());
    if (upper instanceof ParameterizedType parameterized) {
        System.out.println(parameterized.getRawType().getTypeName());
    }
}

for (Type lower : wildcard.getLowerBounds()) {
    System.out.println(lower.getTypeName());
}
```

This snippet **is not a standalone program**; it requires a `wildcard` variable and imports `Type`, `ParameterizedType`. You may also encounter `TypeVariable` or other `Type` forms in complex metadata. Therefore, when serious handling is needed, traverse the entire `Type[]` array and classify each element using `instanceof`.

In common Java source syntax, `? extends T` produces upper bound `T` and `? super T` produces lower bound `T`. Do not write code that makes the absolute deduction "having an upper bound means `extends`": both unbounded wildcards and `super` wildcards have the default upper bound `Object`. When Reflection describes bounds, it reflects type semantics rather than necessarily preserving every syntactic detail written by the author.

## 5. Finding Wildcards in Fields, Methods, and Generic Superclasses/Interfaces

The first step is always choosing **generic** Reflection APIs, not APIs that return only raw classes:

| Declaration site | API for generic metadata | How to locate the wildcard |
| --- | --- | --- |
| Field `List<? extends Number> values` | `Field.getGenericType()` | `ParameterizedType.getActualTypeArguments()` |
| Parameter `void take(List<? super Integer> values)` | `Method.getGenericParameterTypes()[i]` | Retrieve the type argument of `ParameterizedType` |
| Return type `List<?> load()` | `Method.getGenericReturnType()` | Retrieve the type argument of `ParameterizedType` |
| `class Child extends Parent<? extends Number>` | `Class.getGenericSuperclass()` | Check `ParameterizedType` |
| `class HandlerImpl implements Handler<? super Integer>` | `Class.getGenericInterfaces()` | Check each `Type` in the array |

Return type declaration example:

```java
public List<? extends Number> find() {
    return List.of(1, 2);
}
```

With a `Method method` variable pointing to `find`, the reading logic is:

```java
Type result = method.getGenericReturnType();
if (result instanceof ParameterizedType parameterized) {
    Type first = parameterized.getActualTypeArguments()[0];
    if (first instanceof WildcardType wildcard) {
        System.out.println(
                wildcard.getUpperBounds()[0].getTypeName());
    }
}
```

The two snippets above are **contextual illustrations**, not a full program: put the method in a class, obtain the corresponding `Method`, and import the required `Type` interfaces. In the case above, the printed line is `java.lang.Number`.

Note the difference between `Method.getParameterTypes()` (returns `Class<?>[]` after erasure) and `getGenericParameterTypes()` (returns `Type[]` preserving generic metadata). Similarly, `Field.getType()` and `getGenericType()` serve two different purposes.

## 6. `WildcardType` Is Not `TypeVariable`

Example:

```java
class Box<T extends Number> {
    T element;
    List<? extends Number> elements;
}
```

- `T` in the declaration `Box<T extends Number>` is a **named type variable**, modeled by `TypeVariable<?>`. When reading `element` via `getGenericType()`, you can call `TypeVariable.getBounds()` to see that `T` has bound `Number`.
- `? extends Number` in `List<? extends Number>` is a **wildcard**, modeled by `WildcardType` when inspecting the type argument of `ParameterizedType`.

If a field is `List<T>`, the type argument is `TypeVariable`, not a wildcard — even though `T` may have the same `Number` bound. Therefore, do not force every generic argument with `extends` to be `WildcardType`. A type variable is a named parameter reused within a generic declaration's scope; a wildcard is an unknown type argument at a **usage site**.

This affects type resolution tools: to resolve `T` for a specific subclass, you may need to read generic parameters of superclasses/interfaces and build a type-variable mapping. Calling `WildcardType.getUpperBounds()` alone does not resolve a `TypeVariable`.

## 7. PECS: Why `extends` for Reading and `super` for Writing?

The **Producer Extends, Consumer Super (PECS)** guideline describes choosing a wildcard according to a collection's role:

**`? extends T`** is usually suitable when an API only needs to **read** data as `T`. For example:

```java
static double sum(List<? extends Number> numbers) {
    double result = 0;
    for (Number number : numbers) {
        result += number.doubleValue();
    }
    return result;
}
```

With `List<? extends Number>`, the actual type argument could be `Integer`, `Double`, or `Number`. You cannot add an arbitrary `Number` value because it might not match the unknown type argument; the special case `null` can still be added.

**`? super T`** suits when an API needs to **put in** values of type `T`:

```java
static void appendOne(List<? super Integer> destination) {
    destination.add(1);
}
```

The collection could actually be `List<Integer>`, `List<Number>`, or `List<Object>`; all three can accept `Integer`. However, when reading from `List<? super Integer>`, the guaranteed common type is `Object`, which cannot be assigned directly to `Integer` without checking/casting.

**`?`** is used when code does not need to know the specific type argument. You can read as `Object`, but cannot arbitrarily add any value other than `null`.

Both methods in this section are **illustrative code**, requiring `import java.util.List` and placement inside a class. `WildcardType` only lets Reflection **observe** the declared signature; it does not enforce PECS rules at runtime. The compiler is where most generic constraints in Java source are checked.

## 8. Type Erasure and Limitations of Generic Metadata

Suppose code creates two objects:

```java
List<String> names = new ArrayList<>();
List<Integer> counts = new ArrayList<>();
```

In this situation, `names.getClass()` and `counts.getClass()` are both `java.util.ArrayList.class`. The `String` or `Integer` type argument of each variable does not exist as a runtime property that can be queried from the object via `getClass()`.

Conversely, the signature of a **declared field** like `List<? super Integer>` can still be stored in bytecode, allowing `Field.getGenericType()` to read the wildcard. You must distinguish:

1. **Runtime class of an object** — e.g., `ArrayList.class`.
2. **Declared generic signature** — e.g., `List<? extends Number>`.
3. **Actual elements inside the collection** — may require checking each value; a generic signature does not replace validation.

Raw types, unchecked casts, or bytecode that violates generic type safety can break source-level generic assumptions. Do not treat `getUpperBounds()` as proof that all runtime elements in a collection conform to the bound.

When parsing an inconsistent class file or one referencing a type that no longer exists, generic APIs can throw `TypeNotPresentException`, `MalformedParameterizedTypeException`, or `GenericSignatureFormatError` depending on the API/context. A `ClassCastException` when casting `ParameterizedType` to `WildcardType`, by contrast, is a bug in your application's `Type` branching logic.

## 9. Common Mistakes

| Mistake | Truth |
| --- | --- |
| `getUpperBounds()` of `? super Integer` is an empty array | The implicit upper bound is `Object` |
| Empty `getLowerBounds()` means `?` | `? extends T` also has an empty lower bound |
| `? extends Number` corresponds only to `Number` itself | It can correspond to any subtype of `Number` |
| Reading from `? super Integer` guarantees `Integer` | Type-safe reading only guarantees `Object` |
| `Field.getGenericType()` of `List<?>` is `WildcardType` | It is `ParameterizedType`; the wildcard is the type argument inside |
| Every bound is `Class<?>` | A bound can be a `ParameterizedType` such as `Comparable<String>` |
| Both `T extends Number` and `? extends Number` are wildcards | `T` is a `TypeVariable`, `?` is a `WildcardType` |
| `Field.getType()` reveals the wildcard | `getType()` returns the raw/erased class; use `getGenericType()` |
| You can write `List<?>.class` | Java has no class literal for parameterized types; read from declarations |
| Reflection checks the real type argument of every collection object | Reflection reads declared metadata; it does not replace compile-time generic type checking |

## 10. Workflow When Building a Generic Reader Tool

1. Identify where the **signature** lives: field, parameter, return type, superclass, or interface.
2. Use the appropriate `getGeneric...` API to obtain a `Type`.
3. Branch using `instanceof`: `ParameterizedType` to enter type arguments; `WildcardType` to read upper/lower bounds; `TypeVariable` to read generic parameter bounds.
4. For nested generics like `List<List<? extends Number>>`, step through each `ParameterizedType` layer rather than assuming the wildcard is always at index 0 of the outer layer.
5. Traverse the entire `Type[]` of upper/lower bounds, retaining `ParameterizedType` information when a bound itself contains type arguments.
6. Interpret according to `extends`/`super` and actual read/write requirements; do not use Reflection metadata as runtime element validation.

**Takeaway:** `WildcardType` represents **`?` inside a generic signature**. `getUpperBounds()` describes upper bounds; `getLowerBounds()` describes lower bounds. `?` has upper `Object` and empty lower; `? extends T` uses upper `T`; `? super T` uses lower `T` and implicit upper `Object`. To find the wildcard in `List<? ...>`, you must go through `ParameterizedType.getActualTypeArguments()` first.