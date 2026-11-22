# `ParameterizedType` and `getActualTypeArguments()` in Java Reflection

Java Reflection can read more than just the name of a class. When a **generic signature** is stored in the class file, Reflection can also describe declared types such as `List<String>`, `Map<String, List<? extends Number>>`, or `Box<Integer>` through the `java.lang.reflect.Type` API. One particularly important form is **`ParameterizedType`**: it represents the use of a *generic type* with concrete *type arguments* in a signature.

For example:

~~~java
Map<String, List<Integer>> values;
~~~

`Map` is the **declared generic type**, while `String` and `List<Integer>` are the **actual type arguments** in that usage. The calls:

~~~java
Type signature = field.getGenericType();
ParameterizedType map = (ParameterizedType) signature;
Type[] arguments = map.getActualTypeArguments();
~~~

allow reading the structure above. `arguments[0]` is `String.class`; `arguments[1]` is **another `ParameterizedType`**, representing `List<Integer>`. **You cannot always cast an element of the `Type[]` array to `Class<?>`.**

This lesson focuses on **how to obtain a `ParameterizedType`, its three main methods (`getRawType`, `getActualTypeArguments`, `getOwnerType`), how to handle nested `Type` forms, owners of nested classes, generic superclasses/interfaces, and limitations due to type erasure**.

## 1. Distinguishing a Generic Declaration from a Parameterized Type Usage

Consider the declaration:

~~~java
class Box<T> {
    T value;
}
~~~

`Box<T>` declares a **type variable** named `T`. A usage site can write:

~~~java
Box<String> names;
Box<Integer> counts;
~~~

Here, `String` and `Integer` are **actual type arguments** in the declared signatures. When inspecting the metadata of both fields using `Field.getGenericType()`, you can obtain a `ParameterizedType` representing `Box<String>` and a `ParameterizedType` representing `Box<Integer>`, respectively.

However, two objects instantiated via `new Box<String>()` and `new Box<Integer>()` both have the **runtime class** `Box.class`. Because of **type erasure**, the type argument information of an *object instantiation* generally does not reside on the object so that it can be queried directly via `object.getClass()`.

Distinguish two questions:

- **"With what type arguments was this field/method/superclass *declared*?"** → Reflection generic metadata, often yielding a `ParameterizedType`.
- **"What element types does the object `new ArrayList<String>()` currently hold, or was it previously created with `String`?"** → Cannot be determined solely from `object.getClass()` and `ParameterizedType`; you must have another type contract or inspect the data.

## 2. Identifying Arguments Inside `ParameterizedType`

A `ParameterizedType` holds `Type[]`, not `Class<?>[]`. For example, `Map<String, List<? extends Number>>` has its first argument as `Class` (`String`) and its second argument as `ParameterizedType` (`List<? extends Number>`); inside `List` is a `WildcardType`. If an argument is `T` or `T[]`, it can be a `TypeVariable` or `GenericArrayType`. Therefore, reading arguments of a `ParameterizedType` must preserve the `Type` structure and check `instanceof` at each level. The diagram in the introductory lesson presents all five forms of `Type`; here the focus is the path through `getActualTypeArguments()`.

## 3. Finding `ParameterizedType` from Fields, Methods, and Inheritance

APIs to remember:

| Signature site | API for generic metadata | Example |
| --- | --- | --- |
| Field | `Field.getGenericType()` | `Map<String, Long> mapping` |
| Method parameters | `Method.getGenericParameterTypes()` | `void save(List<String> rows)` |
| Method return type | `Method.getGenericReturnType()` | `List<Integer> read()` |
| Direct superclass | `Class.getGenericSuperclass()` | `class StringBox extends Box<String>` |
| Direct interfaces | `Class.getGenericInterfaces()` | `class Repo implements Repository<User>` |
| Constructor parameters | `Constructor.getGenericParameterTypes()` | `new Holder(List<String> values)` |

Note that **`getGenericType()` differs from `getType()`**:

~~~java
Field field = Holder.class.getDeclaredField("records");

Class<?> erased = field.getType(); // Map.class
Type declared = field.getGenericType(); // Map<String, List<? extends Number>>
~~~

This is an illustrative snippet (requires class `Holder` with field `records`, `import java.lang.reflect.*`, and handling `NoSuchFieldException`). `getType()` returns a `Class<?>` representing the erased type; `getGenericType()` can return a `ParameterizedType`.

For methods, `getParameterTypes()` and `getReturnType()` also return erased information, whereas `getGenericParameterTypes()` and `getGenericReturnType()` preserve the generic signature if metadata is present.

**Not every result from `getGeneric...` APIs is a `ParameterizedType`**. For a field declared as `List raw;`, `getGenericType()` returns `Class`. For a field `T data;` in a generic class, the result can be a `TypeVariable`. Always check the variant.

## 4. The Three Core APIs of `ParameterizedType`

`ParameterizedType` has three central methods:

~~~java
Type rawType = parameterized.getRawType();
Type[] args = parameterized.getActualTypeArguments();
Type ownerType = parameterized.getOwnerType();
~~~

### 4.1. `getRawType()`

Returns the `Type` representing the **generic type** to which actual type arguments are being passed. For `List<String>`, the raw type is usually `List.class`; for `Map<String, Integer>`, it is `Map.class`.

Example:

~~~java
Type raw = map.getRawType();
if (raw instanceof Class<?> rawClass) {
    System.out.println(rawClass.getName()); // java.util.Map
}
~~~

In standard Java Reflection cases, the raw type is `Class<?>`. The API is still declared to return `Type`, so general-purpose library code should check the variant before casting. `getRawType()` **does not return the first type argument** and does not turn a generic type argument into a new runtime class.

### 4.2. `getActualTypeArguments()`

Returns a **`Type[]`** array representing the type arguments of the **current parameterized type declaration** in source order:

~~~java
Type[] arguments = map.getActualTypeArguments();
Type key = arguments[0];
Type value = arguments[1];
~~~

For `Map<String, List<? extends Number>>`:

- `arguments[0]` represents `String`, i.e., `Class<String>`.
- `arguments[1]` represents `List<? extends Number>`, i.e., a `ParameterizedType`.
- From `arguments[1]`, calling `getActualTypeArguments()[0]` next yields a `WildcardType`.

**The number of type arguments is not the number of fields, methods, or object instantiations.** Normally it corresponds to the type parameters on the generic member itself that is being parameterized. There are cases where a nested type *does not declare type parameters of its own*, yet its owner is parameterized: `getActualTypeArguments()` of the nested type can be an **empty array**, while `getOwnerType()` still holds the owner's type information.

This `Type[]` array describes metadata; **it does not guarantee `arguments[i] instanceof Class`**. To handle complex types, you must classify `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType`.

### 4.3. `getOwnerType()`

Indicates the **enclosing type** (*owner*) if the parameterized type is a nested type. For example:

~~~java
class Outer<X> {
    class Inner<Y> { }
}

Outer<String>.Inner<Integer> pair;
~~~

For `pair`:

- `getRawType()` describes the `Inner` class.
- `getActualTypeArguments()` of `Inner` contains `Integer`.
- `getOwnerType()` describes `Outer<String>` — which is itself a `ParameterizedType`, with raw type `Outer` and actual argument `String`.

`getOwnerType()` **can return `null`** for types without an owner, such as top-level `List<String>` or `Map<K,V>`. Conversely, do not assume the owner is always `Class<?>`: the owner can also carry type arguments and itself be a `ParameterizedType`. For a static member class, the owner relationship has different semantics from a non-static inner class; do not infer from an owner that an enclosing instance always exists.

## 5. Reading Nested `ParameterizedType` and Wildcards

Suppose the field is:

~~~java
Map<String, List<? extends Number>> records;
~~~

Access the outer layer, then the inner layer:

~~~java
Type type = Holder.class.getDeclaredField("records").getGenericType();

if (!(type instanceof ParameterizedType map)) {
    throw new IllegalStateException("records is not parameterized");
}

Type[] args = map.getActualTypeArguments();
Type keyType = args[0]; // String.class
Type listType = args[1]; // List<? extends Number>

if (listType instanceof ParameterizedType list) {
    Type itemType = list.getActualTypeArguments()[0];
    if (itemType instanceof WildcardType wildcard) {
        Type[] upper = wildcard.getUpperBounds();
        Type[] lower = wildcard.getLowerBounds();
        // Here upper contains Number, lower is empty.
    }
}
~~~

This is an illustrative snippet (requires matching `Holder.records`, `import java.lang.reflect.*`, and field-lookup exception handling). Diagram:

~~~text
Map
├─ String
└─ List
   └─ ? extends Number
~~~

### Two Important Forms of Wildcards

| Signature | Metadata to read | Meaning |
| --- | --- | --- |
| `List<? extends Number>` | `WildcardType.getUpperBounds()` → `Number`; lower bounds empty | Elements have an upper bound of `Number` |
| `List<? super Integer>` | `getLowerBounds()` → `Integer`; upper bounds contain `Object` | Wildcard has lower bound `Integer` |

Java Reflection reflects **declared bounds**, not proof of the runtime contents of every element in a `List`. For a wildcard without an explicit upper bound (or of the form `? super ...`), `getUpperBounds()` typically returns `Object`.

A wildcard can be nested deeply inside a parameterized argument, inside an array, or inside a generic superclass. If writing a general formatter/validator, process `Type` as a **recursive tree** rather than only one level of `getActualTypeArguments()`.

## 6. `TypeVariable` and `GenericArrayType` Are Not `ParameterizedType`

### Type Variable

For example:

~~~java
class Bucket<T extends Number> {
    T number;
}
~~~

With `Bucket.class.getDeclaredField("number").getGenericType()`, we receive a `TypeVariable<?>` representing `T`. It exposes:

- `getName()`: the name `T`.
- `getBounds()`: the upper bounds; here, `Number`.
- `getGenericDeclaration()`: the class, method, or constructor that declares this type variable.

A `TypeVariable` is **different from** the actual type argument `Integer` in the field `Bucket<Integer> bucket;`. If reading an inherited method that uses a type variable from a generic superclass, you must resolve the mapping from the concrete superclass/interface if you want to know which type `T` corresponds to in the subclass context.

### Generic Array

Java allows **declaring references** to arrays with generic components, for example:

~~~java
List<String>[] buckets;
~~~

When reading `Field.getGenericType()` of that field, the result can be a `GenericArrayType`, with:

~~~java
Type component = ((GenericArrayType) type).getGenericComponentType();
// component describes List<String> and can be a ParameterizedType
~~~

This **does not mean** Java allows directly creating `new List<String>[10]`. Generic array creation with a non-reifiable component type is rejected by the compiler. In practice, prefer `List<List<String>>` or a suitable structure, avoiding unchecked array casts unless truly necessary.

Conversely, `String[]` is a reifiable array class; `String[].class` is `Class<?>`. Thus a parser must not treat **every array** as a `GenericArrayType`.

## 7. Complete Java 17+ Example: Inspecting Generic Type Arguments

Create the file **`ParameterizedTypeDemo.java`** in a separate directory and enter the entire following program. It verifies nested fields, wildcard upper/lower bounds, generic arrays, inner class owner types, generic superclasses, raw declarations, and method signatures.

~~~java
import java.lang.reflect.*;
import java.util.*;

public class ParameterizedTypeDemo {
    static class Box<T> { }
    static class StringBox extends Box<String> { }

    static class Outer<X> {
        class Inner<Y> { }
    }

    static class Holder {
        Map<String, List<? extends Number>> records;
        List<? super Integer> sink;
        List<String>[] buckets;
        Outer<String>.Inner<Integer> pair;
        @SuppressWarnings("rawtypes")
        List raw;
    }

    static class Service {
        public Map<String, Integer> convert(List<? extends Number> input) {
            return Collections.emptyMap();
        }
    }

    public static void main(String[] args) throws Exception {
        Field records = Holder.class.getDeclaredField("records");
        System.out.println("erased records: " + records.getType().getTypeName());
        ParameterizedType map = (ParameterizedType) records.getGenericType();
        System.out.println("map raw: " + map.getRawType().getTypeName());
        System.out.println("map arguments: " + map.getActualTypeArguments().length);
        System.out.println("key: " + map.getActualTypeArguments()[0].getTypeName());
        ParameterizedType values = (ParameterizedType) map.getActualTypeArguments()[1];
        System.out.println("value raw: " + values.getRawType().getTypeName());
        WildcardType wildcard = (WildcardType) values.getActualTypeArguments()[0];
        System.out.println("value upper: " + wildcard.getUpperBounds()[0].getTypeName());
        System.out.println("value lower count: " + wildcard.getLowerBounds().length);
        ParameterizedType sink = (ParameterizedType) Holder.class.getDeclaredField("sink").getGenericType();
        WildcardType lower = (WildcardType) sink.getActualTypeArguments()[0];
        System.out.println("sink lower: " + lower.getLowerBounds()[0].getTypeName());
        System.out.println("sink upper: " + lower.getUpperBounds()[0].getTypeName());

        Type buckets = Holder.class.getDeclaredField("buckets").getGenericType();
        System.out.println("buckets generic array: " + (buckets instanceof GenericArrayType));
        Type component = ((GenericArrayType) buckets).getGenericComponentType();
        System.out.println("buckets component: " + component.getTypeName());

        ParameterizedType pair = (ParameterizedType) Holder.class.getDeclaredField("pair").getGenericType();
        System.out.println("pair raw simple: " + ((Class<?>) pair.getRawType()).getSimpleName());
        System.out.println("pair argument: " + pair.getActualTypeArguments()[0].getTypeName());
        ParameterizedType owner = (ParameterizedType) pair.getOwnerType();
        System.out.println("owner raw simple: " + ((Class<?>) owner.getRawType()).getSimpleName());
        System.out.println("owner argument: " + owner.getActualTypeArguments()[0].getTypeName());

        ParameterizedType base = (ParameterizedType) StringBox.class.getGenericSuperclass();
        System.out.println("base raw simple: " + ((Class<?>) base.getRawType()).getSimpleName());
        System.out.println("base argument: " + base.getActualTypeArguments()[0].getTypeName());

        Type raw = Holder.class.getDeclaredField("raw").getGenericType();
        System.out.println("raw list is Class: " + (raw instanceof Class<?>));

        Method convert = Service.class.getDeclaredMethod("convert", List.class);
        System.out.println("method arg: " + convert.getGenericParameterTypes()[0].getTypeName());
        System.out.println("method return: " + convert.getGenericReturnType().getTypeName());
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac --release 17 -Xlint:all ParameterizedTypeDemo.java
java ParameterizedTypeDemo
~~~

**Exact stdout** from a verified compilation/run:

~~~text
erased records: java.util.Map
map raw: java.util.Map
map arguments: 2
key: java.lang.String
value raw: java.util.List
value upper: java.lang.Number
value lower count: 0
sink lower: java.lang.Integer
sink upper: java.lang.Object
buckets generic array: true
buckets component: java.util.List<java.lang.String>
pair raw simple: Inner
pair argument: java.lang.Integer
owner raw simple: Outer
owner argument: java.lang.String
base raw simple: Box
base argument: java.lang.String
raw list is Class: true
method arg: java.util.List<? extends java.lang.Number>
method return: java.util.Map<java.lang.String, java.lang.Integer>
~~~

Explaining the output:

1. `records.getType()` only sees `Map.class`, while `getGenericType()` has `Map<String, List<? extends Number>>`, consisting of **two actual arguments**.
2. The second argument of `Map` is itself `ParameterizedType List<...>`; the wildcard argument inside has upper bound `Number`.
3. `sink` contains the wildcard `? super Integer`, so the lower bound is `Integer` and the upper bound is `Object`.
4. `buckets` contains a generic array, with generic component `List<String>`. Declaring this field still compiles, even though you cannot directly write `new List<String>[n]`.
5. `pair` is a member `Inner<Integer>` owned by `Outer<String>`; `getOwnerType()` retains the `String` information of the outer class.
6. `StringBox extends Box<String>` shows the actual type argument in the *generic superclass*. This is metadata of the inheritance relationship, **not a type argument guessed from an arbitrary object**.
7. A field declared as raw `List` returns `Class`, proving you must not cast every `Type` to `ParameterizedType`.
8. Method `convert` shows an example of `getGenericParameterTypes()` and `getGenericReturnType()` with generic signatures.

The program does not depend on the ordering of `getDeclaredFields()`, so the result is reproducible: each field is looked up explicitly by name.

## 8. Inheritance, Generic Interfaces, and Resolving Type Variables

Type argument information is not always directly on a field. For example:

~~~java
interface Repository<T> { }

class UserRepository implements Repository<String> { }
~~~

Reading it:

~~~java
Type[] interfaces = UserRepository.class.getGenericInterfaces();
ParameterizedType repository = (ParameterizedType) interfaces[0];
Type argument = repository.getActualTypeArguments()[0]; // String.class
~~~

This is an illustrative snippet; it must be placed inside a class/method with `import java.lang.reflect.*`. `getGenericInterfaces()` describes directly declared generic superinterfaces; if a subclass only inherits an interface indirectly, you need to traverse the appropriate class/interface hierarchy.

A more complex case:

~~~java
class Parent<T> {
    T value;
}

class Child extends Parent<String> { }
~~~

`Parent.class.getDeclaredField("value").getGenericType()` is still **`TypeVariable T`**, because the field was declared in `Parent<T>`. Meanwhile, `Child.class.getGenericSuperclass()` returns `ParameterizedType Parent<String>`.

To deduce that field `value` has type argument `String` in the **context of `Child`**, you must build a mapping `T → String` and apply it to the field's signature; `Field.getGenericType()` does not perform that substitution automatically.

This is especially important in ORM frameworks, serializers, or dependency injection: if you only read `Field.getGenericType()` and always cast the result to `Class<?>`, the parser will fail on generic subclasses, wildcards, or nested types.

## 9. Scope of Conclusions That Can Be Drawn

`ParameterizedType` reflects **the generic signature at the declaration site**, such as `Repository<User>` on a field or `Child extends Parent<String>` on a superclass. It does not determine the element type of an ordinary `new ArrayList<String>()` object: `new ArrayList<Integer>().getClass()` and `new ArrayList<String>().getClass()` both yield `ArrayList.class`.

To turn `Parent<T>`'s `T` into `String` in the context of `Child`, a tool must read the `Child extends Parent<String>` edge, map the type variable, and substitute it into the declaration. If you need to pass `List<String>` to a serializer, the caller can keep the `Type` from a field or a type token; the type token technique relies on the superclass signature of a subclass that explicitly declares the type. In all cases, metadata does not automatically validate runtime data. The final lesson of this chapter analyzes erasure, class-file `Signature`, and a complete Reflection invocation experiment.

## 10. Checking Structure Before Processing

When reading a field/method/supertype, verify `type instanceof ParameterizedType p` before calling its three methods. Traverse each `Type` from `p.getActualTypeArguments()`; if an argument is also a `ParameterizedType`, recurse depth-first; if it is a `WildcardType`, read upper/lower bounds; if it is a `TypeVariable`, inspect its generic declaration/bounds; if it is a `GenericArrayType`, read its generic component. **Also traverse `p.getOwnerType()` when non-null**, because `Outer<String>.Inner<Integer>` carries `String` in the owner, not in the inner's arguments.

For display you can use `getTypeName()`; for a resolver/cache, you must retain the `Type` structure rather than splitting strings. Self-referential bounds such as `T extends Comparable<T>` require a visited-node set to avoid infinite recursion. If a signature in bytecode is missing or malformed, generic APIs can throw `TypeNotPresentException`, `MalformedParameterizedTypeException`, or `GenericSignatureFormatError`: report a metadata error instead of fabricating type arguments.

## 11. Common Mistakes and Fixes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Casting every `field.getGenericType()` to `ParameterizedType` | A field may be raw `List`, `T`, `String`, or an array | Check `instanceof` first |
| Casting every `getActualTypeArguments()[i]` to `Class<?>` | An argument can be a wildcard, type variable, or nested parameterized type | Handle the entire `Type` family |
| Confusing raw type with the first argument type | `getRawType()` returns `Map`, not `String` | Get args via `getActualTypeArguments()` |
| Reading one level of `Map` and concluding the value is `List.class` | `List<? extends Number>` contains deeper metadata | Traverse the tree of nested parameterized arguments |
| Assuming `getOwnerType() == null` | Member classes have owners, which may be parameterized owners | Handle the owner when present |
| Treating `List<String>[]` as a `Class<List<String>[]>` | Generic components are not reifiable | Recognize `GenericArrayType` |
| Using `getClass()` of `ArrayList<String>` to get `String` | Type erasure does not retain instance type arguments | Use a declared signature or an explicitly passed type token |
| Reading field `T` on parent and expecting child's `String` | `Field` belongs to generic declaration `Parent<T>` | Resolve the `T → String` mapping from `Child extends Parent<String>` |
| Comparing `Type.getTypeName()` by string to classify | Types have nested structure, owners, and bounds | Use `instanceof` and each subtype's API |
| Believing actual type arguments automatically validate a collection object | Generic metadata does not enforce runtime data state | Validate data/contracts at a separate boundary |

## 12. When Should You Use `ParameterizedType`?

- **Serializers and JSON mappers:** read `Map<String, List<Item>>` in declarations to guide object structure handling, paired with separate data validation logic.
- **Dependency injection / framework registration:** recognize injection points like `Repository<User>` and distinguish specializations based on generic metadata.
- **API documentation and schemas:** accurately present generic parameters, return types, or superclasses instead of only raw `Map` or `List`.
- **Static/runtime inspection tools:** detect raw type declarations, wildcard bounds, nested generic arguments, and owner types in signatures.
- **Generic type resolvers:** follow relationships like `Child extends Parent<String>` to substitute type variable `T` in a concrete context.

**Rule of thumb:** `getRawType()` tells you the *underlying generic type*; `getActualTypeArguments()` tells you the *type arguments at the current layer*; `getOwnerType()` tells you the *enclosing type if it is a nested type*. Each actual argument is itself a **`Type`**, so it must be analyzed structurally — and all of that information is still constrained by **type erasure** when trying to reason about a runtime object.

### Standard References

- [Java SE 21 — `java.lang.reflect.ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html): `getRawType`, `getActualTypeArguments`, `getOwnerType`.
- [Java SE 21 — `Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java SE 21 — `Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html) and [`Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html) for APIs that read generic signatures.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6) and [§4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.5).
