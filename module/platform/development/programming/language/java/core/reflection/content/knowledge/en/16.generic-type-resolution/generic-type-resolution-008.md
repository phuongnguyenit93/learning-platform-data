# Type Token Pattern and Anonymous Subclasses in Java Reflection

## 1. Why do we need a type token?

In Java, generic types help the compiler check type safety, yet most type parameters undergo **type erasure** at runtime. For example, both `List<String>` and `List<Integer>` share the raw class `java.util.List`. The expression `List<String>.class` is illegal; `List.class` only represents the raw type.

Even so, Java can store **declared generic signatures** in metadata of a class, field, method, or superclass. Reflection can read that signature as a `java.lang.reflect.Type`. The **type token** pattern uses an object representing a type description to pass complex types such as `List<String>` or `Map<String, List<Integer>>` to an API that needs type information.

Distinguish two cases:

- **Class token**: `String.class`, `List.class`, or `Class<T>` is suitable when only class/raw type identity is needed.
- **Generic type token**: `Type` describes the entire declared generic structure, such as `List<String>`, nested types, wildcards, or generic arrays. Not every `Type` is a `Class<?>`.

A type token **does not reverse type erasure on an arbitrary object**. It reads generic information preserved at a specific declaration site.

## 2. How does an anonymous subclass preserve generic arguments?

This is a common usage:

~~~java
Type type = new TypeRef<List<String>>() {}.type();
~~~

The `{}` creates an **anonymous subclass** of `TypeRef<List<String>>`. The compiler stores the generic signature of the superclass on the anonymous class. When the object is created:

1. `getClass()` returns the `Class` of the anonymous subclass, **not** `TypeRef.class` itself.
2. `getClass().getGenericSuperclass()` reads the declared superclass type, namely `TypeRef<List<String>>`.
3. The value obtained is a `ParameterizedType`; `getActualTypeArguments()[0]` is `List<String>`, still as a `Type`.
4. This `Type` can be retained to pass to a data-processing library or to inspect further with Reflection.

The syntax `new TypeRef<List<String>>()` **without** `{}` cannot instantiate an object in the example below because `TypeRef` is an `abstract` class. More importantly, the anonymous subclass is what carries a **concrete generic signature** to read. This pattern is sometimes called a *super type token*.

## 3. Building a simple TypeRef runnable on Java 17+

Save the following code as `TypeTokenDemo.java`:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;
import java.util.Map;

public class TypeTokenDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType parameterized)
                    || parameterized.getRawType() != TypeRef.class) {
                throw new IllegalStateException(
                        "Must subclass TypeRef<T> with a concrete type argument");
            }
            type = parameterized.getActualTypeArguments()[0];
        }

        public final Type type() {
            return type;
        }
    }

    static final class Example {
        List<String> names;
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Type a = new TypeRef<List<String>>() {}.type();
        Type b = new TypeRef<Map<String, List<Integer>>>() {}.type();
        Type c = new TypeRef<List<Integer>>() {}.type();

        System.out.println(a.getTypeName());
        System.out.println(b.getTypeName());
        System.out.println(a.equals(c));

        if (b instanceof ParameterizedType p) {
            System.out.println(p.getRawType().getTypeName());
            for (Type arg : p.getActualTypeArguments()) {
                System.out.println(arg.getTypeName());
            }
        }

        Type fieldType = Example.class.getDeclaredField("names")
                .getGenericType();
        System.out.println(a.equals(fieldType));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 TypeTokenDemo.java
java TypeTokenDemo
~~~

Stdout:

~~~text
java.util.List<java.lang.String>
java.util.Map<java.lang.String, java.util.List<java.lang.Integer>>
false
java.util.Map
java.lang.String
java.util.List<java.lang.Integer>
true
~~~

Explanation of results:

- `a` and `c` have the same raw type (`List`) but different generic arguments (`String` and `Integer`), so `Type.equals` evaluates to `false`.
- `b` is a `ParameterizedType` for `Map<String, List<Integer>>`. `getRawType()` returns `Map.class`; the two elements of `getActualTypeArguments()` are `String.class` and a `ParameterizedType` for `List<Integer>`, respectively.
- Field `names` directly declares `List<String>`, so `Field.getGenericType()` gives a type description equivalent to `a`; the comparison result is `true`. No instance of `Example` is needed to read the field declaration.
- The `TypeRef` constructor rejects direct subclassing with a raw type or failing to declare `TypeRef<T>` as a parameterized superclass. This simple implementation **only supports classes directly extending `TypeRef<...>`** and does not walk multi-level inheritance.

The generic signature is read from the compiled class structure; this operation **does not check the actual runtime contents** of a `List`. The `TypeRef` pattern also does not parse JSON, convert data, or validate individual elements on its own.

## 4. Reading the Type tree properly

`Type` is a common interface. Values read can belong to the following kinds:

| Reflection kind | Example | Meaning and main APIs |
| --- | --- | --- |
| `Class<?>` | `String.class`, `List.class`, `String[].class` | Class or array with reifiable component type; `getTypeName()` |
| `ParameterizedType` | `List<String>`, `Map<String, Integer>` | Raw type, owner type, and type arguments; `getRawType()`, `getOwnerType()`, `getActualTypeArguments()` |
| `TypeVariable<?>` | `T` in `class Box<T>` | Type variable from a declaration; `getName()`, `getBounds()`, `getGenericDeclaration()` |
| `WildcardType` | `? extends Number`, `? super Integer` | Upper/lower bounds; `getUpperBounds()`, `getLowerBounds()` |
| `GenericArrayType` | `List<String>[]`, `T[]` | Array with non-reifiable component type; `getGenericComponentType()` |

For example, `new TypeRef<List<? extends Number>>() {}.type()` has an outer node that is a `ParameterizedType` for `List`; that node's type argument is a `WildcardType`. For `new TypeRef<List<String>[]>() {}.type()`, the outer node is typically a `GenericArrayType` whose component is a `ParameterizedType` for `List<String>`.

To analyze nested generics accurately, traverse recursively by **node kind**; do not cast every result to `Class<?>`. Example of checking a `Type` before handling it:

~~~java
if (type instanceof ParameterizedType p) {
    Type raw = p.getRawType();
    Type[] args = p.getActualTypeArguments();
    // Continue checking the kind of each element in args.
} else if (type instanceof Class<?> cls) {
    // Class type, primitive, or reifiable array.
} else if (type instanceof TypeVariable<?> tv) {
    // Name and bounds of the type variable; not necessarily a concrete type.
}
~~~

The snippet above is an **illustrative code fragment** assuming `type` is already available; the complete program in section 3 can run standalone.

Other Reflection sources also provide `Type`: `Field.getGenericType()`, `Method.getGenericReturnType()`, `Method.getGenericParameterTypes()`, `Class.getGenericInterfaces()`, and `Class.getGenericSuperclass()`. Using the versions **without "Generic"**, such as `Field.getType()` or `Method.getReturnType()`, yields only the post-erasure `Class<?>`.

## 5. Applying when designing APIs

When a function needs to know the target type structure to parse data, have it accept `Type` (or an equivalent abstraction) rather than accepting only `Class<?>`. Client-side call sites can look like:

~~~java
Type listOfNames = new TypeRef<List<String>>() {}.type();
Type index = new TypeRef<Map<String, List<Integer>>>() {}.type();
~~~

These two variables are type descriptions suitable as inputs for an API **that supports `Type`**. That API must define how to handle `ParameterizedType`, wildcards, and nested types; `TypeRef` only holds and supplies type information.

For simple types, `String.class` is usually sufficient and cleaner. For types declared inside a specific class, reading from a field/method via Reflection can be more appropriate than creating a new anonymous subclass. Many libraries already include similar types (such as `TypeToken` or `TypeReference`); API names, type variable support, and token creation methods can vary across libraries.

## 6. Common limitations and mistakes

### 6.1. Cannot infer generics of an ordinary object

~~~java
List<String> names = new java.util.ArrayList<>();
System.out.println(names.getClass() == java.util.ArrayList.class);
~~~

The result is `true`. The runtime class of the instance is `ArrayList`, which does not carry the `String` argument of the `names` variable. `names.getClass().getGenericSuperclass()` gives the generic superclass declaration of the **ArrayList class**, not proving the list holds `String` elements.

You cannot use `new TypeRef<>(...)` to "read back" lost generic types from an arbitrary instance without additional declaration metadata.

### 6.2. Capturing a type variable does not guarantee capturing a concrete type

Inside a generic method:

~~~java
static <T> Type captureInGenericMethod() {
    return new TypeRef<List<T>>() {}.type();
}
~~~

The resulting `Type` describes `List<T>`, where `T` is a `TypeVariable` of the method declaration. Even if called from a context whose argument is `String`, `List<String>` cannot be inferred automatically from this token alone. To obtain a concrete type, pass in an already resolved `Type` or provide a mechanism to resolve type variables from the appropriate context. The snippet above assumes `TypeRef` from section 3 and `Type` imported; it is illustrative, not a standalone program.

### 6.3. Confusing `ParameterizedType` with `Class`

Casting `(Class<?>) new TypeRef<List<String>>() {}.type()` will throw `ClassCastException` because the outer node is a `ParameterizedType`. Check with `instanceof` and only extract `getRawType()` when you genuinely need the raw type.

### 6.4. Raw types and multi-level inheritance

Writing `new TypeRef() {}` loses the type argument and is caught by the example constructor. For `class Mid<T> extends TypeRef<T>` and `class Final extends Mid<String>`, `Final.class.getGenericSuperclass()` is `Mid<String>`, not directly `TypeRef<String>`; the section 3 implementation will reject it. A general-purpose version supporting multi-level hierarchies must walk the hierarchy and resolve `TypeVariable` mappings across each level instead of reading only `getActualTypeArguments()[0]` at the first level.

### 6.5. Do not confuse metadata with runtime safety guarantees

A `List<String>` token describes type intent. It does not prevent raw-type code from adding wrong-type elements into the list and does not make `instanceof List<String>` valid. Data validation/deserialization must be handled separately, including subtypes, nulls, wildcards, and malformed formats.

## 7. Takeaways when using generic Reflection

- When you need generic arguments **declared on a superclass**, use `getGenericSuperclass()` and check `ParameterizedType`.
- For a concrete type token, use `new TypeRef<TargetType>() {}`; the `{}` creates a subclass carrying a signature for Reflection to read.
- After obtaining a `Type`, traverse `Class`, `ParameterizedType`, `WildcardType`, `TypeVariable`, and `GenericArrayType` as needed. Do not assume every node directly has a class.
- Distinguish **declared types** from **runtime data types**; type erasure still applies.
- Only pass tokens to APIs that understand `Type`. Separately test nested generics, wildcards, generic methods, and raw types if your framework supports them.

The essence of this pattern is **placing a concrete generic expression into the superclass signature of an anonymous subclass**, then retrieving that description via Reflection. This is a way to pass richly structured type information to APIs while staying within Java's type erasure model.