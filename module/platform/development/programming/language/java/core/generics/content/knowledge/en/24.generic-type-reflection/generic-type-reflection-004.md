# ParameterizedType: Raw Type, Owner Type, and Actual Type Arguments in Java Generics

## 1. Learning Objectives

Java Generics allows writing types such as `List<String>`, `Map<String, List<Integer>>`, or `Outer<String>.Inner<Integer>`. After *type erasure*, the JVM does not create a separate class for each parameterization. However, **generic information declared on a field, method, superclass, interface, or anonymous subclass can still be stored in the class file** and read back via the reflection API.

`java.lang.reflect.ParameterizedType` is the interface representing **a parameterized type** in reflection. Its three most important methods are:

- `getRawType()`: the underlying declared type being parameterized, e.g. `List` in `List<String>`.
- `getOwnerType()`: the enclosing type that a member type belongs to, if any; especially important for nested/inner classes.
- `getActualTypeArguments()`: the list of direct type arguments, e.g. `String` in `List<String>`, or `String` and `List<Integer>` in `Map<String, List<Integer>>`.

After this lesson, you will know how to obtain a `ParameterizedType` from reflection APIs, understand **when the owner is `null`**, distinguish a generic owner from a static nested class, recursively read type arguments, recognize `Class`, `TypeVariable`, `WildcardType`, and `GenericArrayType`, and avoid confusing **declaration metadata** with **actual runtime-checked data types**.

## 2. Where Do `Type` and `ParameterizedType` Appear in Reflection?

Some useful reflection APIs:

```java
Field field = SomeClass.class.getDeclaredField("names");
Type declared = field.getGenericType();

Type superclass = SomeSubclass.class.getGenericSuperclass();
Type[] interfaces = SomeImplementation.class.getGenericInterfaces();
```

These illustrate API calls; the corresponding classes and fields must be defined if run standalone. The complete program in Section 8 provides a runnable example.

Key reflective types:

| API/Type | Meaning | Example |
| --- | --- | --- |
| `Type` | Common parent interface for reflection type descriptions. | Result of `Field.getGenericType()`. |
| `Class<?>` | Reifiable class, interface, primitive, or array type with a corresponding Class object. | `String.class`, `List.class`, `String[].class`. |
| `ParameterizedType` | A type usage with generic arguments or a member type with a parameterized owner. | `List<String>`, `Outer<String>.Inner<Integer>`. |
| `TypeVariable<?>` | Type variable declared on a class, interface, or method. | `T` in `class Box<T>`. |
| `WildcardType` | Wildcard along with upper/lower bounds. | `? extends Number`, `? super Integer`. |
| `GenericArrayType` | Array whose component type is non-reifiable in the generic reflection model. | `T[]`, `List<T>[]`. |

A `ParameterizedType` is **not** a `Class`. It describes the generic type structure appearing in a declaration. When you need to call `Class.isInstance` or `Class.cast`, you are checking a runtime type representable by `Class`, not automatically checking all generic arguments.

For example, `List.class` can identify an object implementing List; it does not distinguish `List<String>` from `List<Integer>`. Conversely, a `ParameterizedType` read from metadata can tell you that a field was declared as `List<String>`; that is information **about the field**, not a JVM mechanism scanning every element of the list at runtime.

### Getting a Field's Generic Type and Raw Type

Suppose:

```java
class Profile {
    List<String> names;
}
```

Place the declarations in the same file importing `java.util.List` and `java.lang.reflect.Field`:

```java
Field field = Profile.class.getDeclaredField("names");

Class<?> rawFieldType = field.getType();
Type genericFieldType = field.getGenericType();
```

`field.getType()` returns the `Class` representing `java.util.List`. `field.getGenericType()` typically returns a `ParameterizedType` representing `java.util.List<java.lang.String>`.

To access the three components, check the type first:

```java
if (genericFieldType instanceof ParameterizedType type) {
    Type raw = type.getRawType();
    Type owner = type.getOwnerType();
    Type[] arguments = type.getActualTypeArguments();
}
```

The resulting `Type` is not always a `ParameterizedType`. For example, a field declared as `String name` typically yields `Class<String>`; a field declared as raw `List names` typically yields `Class<List>`. Unconditionally casting `(ParameterizedType) field.getGenericType()` can cause a `ClassCastException`.

## 3. `getRawType()`: The Underlying Base Without Type Arguments

For `List<String>`, the raw type component is `java.util.List`:

```text
List<String>
┌───┘└────┘
 raw   actual type argument
```

Example:

```java
Type declared = field.getGenericType();

if (declared instanceof ParameterizedType p) {
    System.out.println(p.getRawType().getTypeName());
}
```

Output for field `List<String>`:

```text
java.util.List
```

For `Map<String, List<Integer>>`:

- Outermost raw type: `java.util.Map`.
- First actual type argument: `java.lang.String`.
- Second actual type argument: **another ParameterizedType** representing `List<Integer>`.
- Raw type of the second argument: `java.util.List`.
- Inner actual type argument: `java.lang.Integer`.

**Do not merely call `getRawType()` and conclude you understand the full type.** It intentionally omits type arguments, wildcard bounds, and parameterized owner info.

### `getRawType()` Returns `Type`, Not Declared as Returning `Class<?>`

The method signature is:

```java
Type getRawType();
```

In standard reflections over Java classes/interfaces, the returned value is usually a `Class<?>`. However, the API declares the general return type `Type`, so library code reading reflection should check before downcasting:

```java
Type raw = parameterized.getRawType();
if (raw instanceof Class<?> rawClass) {
    System.out.println(rawClass.getName());
}
```

`parameterized` here is a `ParameterizedType` variable obtained in context. If the goal is simply printing or comparing descriptions, `raw.getTypeName()` may suffice without casting.

### Raw Type vs. Raw Type Usage in Source Code

The same phrase "raw type" is used in two contexts:

- `getRawType()` describes the class/interface part behind a `ParameterizedType`.
- A **raw usage** in source code is a declaration omitting type arguments, e.g. `List raw;`.

A raw `List` field declaration can make `getGenericType()` return `Class<List>` directly, rather than a `ParameterizedType` with an empty argument list. Thus you should not treat "having `Class<List>`" and "having `ParameterizedType<List<String>>`" as equivalent reflective structures.

## 4. `getActualTypeArguments()`: List of Direct Type Arguments

For a simple type:

```java
List<String>
```

`getActualTypeArguments()` returns a `Type[]` array with **1 element**, describing `String`.

For:

```java
Map<String, List<Integer>>
```

it returns **2 elements**:

```text
Map<String, List<Integer>>
 ├── arg[0]: Class<String>
 └── arg[1]: ParameterizedType(List<Integer>)
                     ├── raw: Class<List>
                     └── arg[0]: Class<Integer>
```

Even though the nested type contains an Integer, that does **not** mean `Map` has three actual type arguments. `Map<K,V>` has exactly two direct arguments; to inspect Integer, you must descend into the second argument.

### Recursive Inspection

```java
static void inspectArguments(ParameterizedType type) {
    Type[] arguments = type.getActualTypeArguments();
    for (int index = 0; index < arguments.length; index++) {
        Type argument = arguments[index];
        System.out.println("arg[" + index + "]=" + argument.getTypeName());

        if (argument instanceof ParameterizedType nested) {
            inspectArguments(nested);
        }
    }
}
```

This is an illustrative helper requiring imports for `Type` and `ParameterizedType`. In a real application, a general Type walker must also handle `Class`, `WildcardType`, `TypeVariable`, and `GenericArrayType`, and avoid infinite recursion when analyzing self-referential recursive bounds.

**Key point:** `getActualTypeArguments()` returns `Type[]`, not `Class<?>[]`, because an argument can take several different forms.

| Declared Argument | Common Reflective Kind |
| --- | --- |
| `String` | `Class<?>`. |
| `List<Integer>` | `ParameterizedType`. |
| `T` | `TypeVariable<?>`. |
| `? extends Number` | `WildcardType`. |
| `T[]` when T is a type variable | `GenericArrayType`. |
| `String[]` | `Class<?>`, because a String array is reifiable. |

Do not force every element of `getActualTypeArguments()` to `Class`. That may work for `List<String>` but will throw `ClassCastException` on `List<T>` or `List<? extends Number>`.

## 5. `getOwnerType()`: The Enclosing Type of a Member Type

`Owner type` is often the easiest part to misunderstand. It is **not** simply the superclass, not the raw type, and not an argument placed in the same array as the direct type arguments of the member class.

For a top-level type `List<String>`, `getOwnerType()` is `null`, because `List` is not a member class inside an enclosing type.

Consider:

```java
class Outer<T> {
    class Inner<U> {}
    class Plain {}
    static class Nested<V> {}
}
```

The three member types relate to Outer differently. When inspecting the declaration:

```java
Outer<String>.Inner<Integer>
```

we have two "layers" of parameterization:

- **Inner<U>** has U = Integer.
- **Outer<T>** is the owner parameterized with T = String.

When reflecting this type, the `ParameterizedType` of `Inner<Integer>` has:

```text
getRawType()            -> Outer$Inner
getOwnerType()          -> ParameterizedType(Outer<String>)
getActualTypeArguments()-> [Integer]
```

The String info belongs to `getOwnerType()`, while Integer belongs to `Inner`'s `getActualTypeArguments()`. If you only inspect Inner's arguments and ignore the owner, you **will miss T = String**.

### 5.1. Non-Static Inner Class with a Generic Owner

Field declaration:

```java
Outer<String>.Inner<Integer> member;
```

If this is a field on a class and `getGenericType()` returns `ParameterizedType p`:

```java
Type owner = p.getOwnerType();
Type raw = p.getRawType();
Type[] ownArguments = p.getActualTypeArguments();
```

Typical output from the program in Section 8 is:

```text
inner.raw=ParameterizedTypeDemo$Outer$Inner
inner.ownerParameterized=true
inner.ownerRaw=ParameterizedTypeDemo$Outer
inner.ownerArg=java.lang.String
inner.arg=java.lang.Integer
```

The `$` in binary class names of nested types is how the JVM represents class names in the example. When presenting to readers, you may use the source name `Outer.Inner`, whereas when comparing `Class.getName()`/`Type.getTypeName()`, the binary name may contain `$`.

### 5.2. Inner Class That Does Not Declare Its Own Type Parameters

This is an important case:

```java
Outer<String>.Plain plain;
```

`Plain` does **not** declare `<U>`, yet its **owner** is still `Outer<String>`. Reflection can return a `ParameterizedType` for the member with:

```text
getActualTypeArguments().length -> 0
getOwnerType()                   -> Outer<String>
```

This proves that **a `ParameterizedType` is not required to have at least one direct argument**. Parameterized metadata can live on the owner. You must not deduce "empty actual arguments ⇒ this type definitely has nothing to do with generics".

In the example verified on Java 17, `plain.ownArgs=0` and `plain.ownerArg=java.lang.String`.

### 5.3. Static Nested Class

Declaration:

```java
Outer.Nested<Long> nested;
```

`Nested<V>` is `static`, so it does not carry the type parameter T from a specific `Outer<T>` instance. In verified Java reflection output:

```text
static.ownerIsClass=true
static.owner=ParameterizedTypeDemo$Outer
static.arg=java.lang.Long
```

`getOwnerType()` here is a `Class` for Outer, **not** `ParameterizedType(Outer<String>)`. The Long argument belongs to Nested, not Outer.

Do not conclude that an owner is always a `ParameterizedType` just because the member is generic. The owner can be `Class<?>`, `ParameterizedType`, or `null`, depending on the declaration. With deeply nested member classes, the owner itself can have another owner; traverse structurally rather than concatenating strings arbitrarily.

### 5.4. Owner Is Not Superclass

`Outer<String>.Inner<Integer>` has owner `Outer<String>` because Inner is declared as a member of Outer. It does not mean Outer is the direct superclass of Inner. Inheritance is read via `getGenericSuperclass()`; member/owner declaration relationship is read via `getOwnerType()`.

These are two independent metadata dimensions:

```text
Owner:  Outer<String> ── contains declaration ──> Inner<Integer>

Extends: Child ── inherits ──> Parent<Something>
```

When writing a tool to build Type diagrams, do not draw an "extends" edge based solely on `getOwnerType()`.

## 6. Context-Appropriate Ways to Obtain `ParameterizedType`

Fields are not the only place with generic type metadata. Depending on where Java declares a type, you can read it using these APIs:

| Declaration Source | Reflection API | Example |
| --- | --- | --- |
| Field | `Field.getGenericType()` | `List<String> names`. |
| Superclass of a class | `Class.getGenericSuperclass()` | `class Names extends ArrayList<String>`. |
| Interfaces directly implemented by a class | `Class.getGenericInterfaces()` | `implements Supplier<List<String>>`. |
| Method return type | `Method.getGenericReturnType()` | `List<String> fetch()`. |
| Method parameter types | `Method.getGenericParameterTypes()` | `consume(List<String> values)`. |
| Exception types declared by a method | `Method.getGenericExceptionTypes()` | Valid cases where throws uses a type variable. |
| Generic superclass of an anonymous TypeRef | `getClass().getGenericSuperclass()` | `new TypeRef<List<String>>() {}`. |

**Not every returned value is a ParameterizedType.** A method returning `String` typically has `getGenericReturnType()` equal to `Class<String>`. A method returning T may yield `TypeVariable<?>`. Use `instanceof` to handle each kind properly.

### 6.1. Generic Superclass

Example:

```java
class StringList extends ArrayList<String> {
    private static final long serialVersionUID = 1L;
}
```

`StringList.class.getGenericSuperclass()` can be a `ParameterizedType` with raw type `ArrayList` and actual argument `String`.

`Class.getSuperclass()` only returns the parent's raw class `ArrayList.class`; `getGenericSuperclass()` preserves how the subclass declared its parent parameterization. The Section 8 program prints:

```text
super.raw=java.util.ArrayList
super.arg=java.lang.String
```

### 6.2. Generic Interface

Example:

```java
class StringSource implements Supplier<List<String>> {
    @Override
    public List<String> get() {
        return List.of("hi");
    }
}
```

`StringSource.class.getGenericInterfaces()[0]` describes `Supplier<List<String>>` and is a `ParameterizedType`. Supplier's direct actual argument is **another ParameterizedType**, `List<String>`.

In the program:

```text
interface.raw=java.util.function.Supplier
interface.arg=java.util.List<java.lang.String>
```

`getGenericInterfaces()` returns the interfaces declared **directly** on the inspected class/interface. It does not automatically return all interfaces from the entire inheritance chain or resolve all ancestor type variables to concrete types. Building a complete *type resolver* requires walking the inheritance tree and substituting type variables per relationship.

### 6.3. Generic Metadata Is Not the "Full Type" of an Instance

With:

```java
class Box<T> {
    List<T> items;
}
```

`Box.class.getDeclaredField("items").getGenericType()` describes `List<T>`, where T is a `TypeVariable`.

If you instantiate `new Box<String>()`, you cannot simply call `getClass()` on the instance and expect the JVM to return a separate `Box<String>` class. The runtime class is still `Box.class`, and metadata on the original field still says `List<T>`. When generics are specialized in a subclass, reflection can observe the specialized structure on the subclass's generic superclass; however, chaining multiple levels and substituting T requires additional algorithm logic.

## 7. Forms of `Type` Appearing in Actual Arguments

### 7.1. `Class<?>`

In `List<String>`, the argument is `Class<String>`. You can check:

```java
Type arg = p.getActualTypeArguments()[0];
if (arg instanceof Class<?> c) {
    System.out.println(c.getName());
}
```

Here `p` is the existing ParameterizedType of `List<String>`. The output is `java.lang.String`.

### 7.2. Nested `ParameterizedType`

In `Map<String, List<Integer>>`, the second argument is another `ParameterizedType`:

```java
Type valueArg = mapType.getActualTypeArguments()[1];
if (valueArg instanceof ParameterizedType nestedList) {
    Type listRaw = nestedList.getRawType();
    Type element = nestedList.getActualTypeArguments()[0];
}
```

`mapType` is the ParameterizedType describing the outer Map. `listRaw` represents List, and `element` represents Integer. Do not cast `valueArg` directly to `Class<List<?>>`.

### 7.3. `WildcardType`

With:

```java
List<? extends Number> producers;
List<? super Integer> consumers;
```

`getActualTypeArguments()[0]` of each declaration is a `WildcardType`.

- `? extends Number` has upper bound Number.
- `? super Integer` has lower bound Integer and default upper bound Object.

Reflection provides `getUpperBounds()` and `getLowerBounds()` returning `Type[]`. An unbounded wildcard `?` has upper bound Object and no explicit lower bounds.

Do not infer wildcard bounds merely from the `toString()` string; use the proper bounds APIs for structured analysis.

### 7.4. `TypeVariable<?>`

With:

```java
class Samples<N extends Number> {
    List<N> genericList;
}
```

The argument of `List<N>` is a `TypeVariable` representing N. You can read:

- `getName()` → `N`.
- `getBounds()` → Number (in this example).
- `getGenericDeclaration()` → where N is declared, i.e., a class or method/constructor.

Do not automatically replace N with Object if it has a Number bound. At the same time, seeing that N has bound Number does **not** prove N is literally Number in every instance parameterization.

### 7.5. `GenericArrayType`

With:

```java
class Samples<N extends Number> {
    N[] genericArray;
    List<N>[] listArray;
}
```

Both field declarations are valid even though you **cannot** directly instantiate `new N[3]` or `new List<N>[3]`.

- `N[]` can be represented by reflection as a `GenericArrayType` with component type N (`TypeVariable`).
- `List<N>[]` can be a `GenericArrayType` whose component is `ParameterizedType` `List<N>`.
- `String[]`, by contrast, has runtime `Class<String[]>` because the String component is reifiable.

This distinction avoids forcing every Type describing an array into `Class<?>`.

## 8. Complete Java 17 Program

The program below declares the types to reflect on and accurately prints raw type, owner type, actual arguments, wildcard bounds, type variables, and generic array types. It also demonstrates extracting metadata from a superclass/interface and a TypeRef.

**File `ParameterizedTypeDemo.java`:**

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

public class ParameterizedTypeDemo {
    static class Outer<T> {
        class Inner<U> {}
        class Plain {}
        static class Nested<V> {}
    }

    static class Samples<N extends Number> {
        List<String> names;
        Map<String, List<Integer>> nested;
        List<? extends Number> producers;
        List<? super Integer> consumers;
        List<N> genericList;
        N[] genericArray;
        List<N>[] listArray;
        Outer<String>.Inner<Integer> inner;
        Outer<String>.Plain plain;
        Outer.Nested<Long> staticNested;
    }

    static class StringList extends ArrayList<String> {
        private static final long serialVersionUID = 1L;
    }

    static class StringSource implements Supplier<List<String>> {
        @Override public List<String> get() {
            return List.of("hi");
        }
    }

    abstract static class TypeRef<T> {
        final Type getType() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException("Missing type metadata");
            }
            return p.getActualTypeArguments()[0];
        }
    }

    static Type fieldType(String name) throws ReflectiveOperationException {
        return Samples.class.getDeclaredField(name).getGenericType();
    }

    static ParameterizedType requireParameterized(Type type) {
        if (!(type instanceof ParameterizedType p)) {
            throw new IllegalArgumentException("Not parameterized: " + type);
        }
        return p;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Field field = Samples.class.getDeclaredField("names");
        ParameterizedType names = requireParameterized(field.getGenericType());
        System.out.println("field.rawClass=" + field.getType().getTypeName());
        System.out.println("field.generic=" + field.getGenericType().getTypeName());
        System.out.println("list.raw=" + names.getRawType().getTypeName());
        System.out.println("list.owner=" + names.getOwnerType());
        System.out.println("list.arg=" + names.getActualTypeArguments()[0].getTypeName());

        ParameterizedType nested = requireParameterized(fieldType("nested"));
        Type nestedValue = nested.getActualTypeArguments()[1];
        System.out.println("map.arity=" + nested.getActualTypeArguments().length);
        System.out.println("map.valueParameterized=" + (nestedValue instanceof ParameterizedType));
        System.out.println("map.valueArg=" + requireParameterized(nestedValue)
                .getActualTypeArguments()[0].getTypeName());

        ParameterizedType inner = requireParameterized(fieldType("inner"));
        ParameterizedType innerOwner = requireParameterized(inner.getOwnerType());
        System.out.println("inner.raw=" + inner.getRawType().getTypeName());
        System.out.println("inner.ownerParameterized=" + (inner.getOwnerType() instanceof ParameterizedType));
        System.out.println("inner.ownerRaw=" + innerOwner.getRawType().getTypeName());
        System.out.println("inner.ownerArg=" + innerOwner.getActualTypeArguments()[0].getTypeName());
        System.out.println("inner.arg=" + inner.getActualTypeArguments()[0].getTypeName());

        ParameterizedType plain = requireParameterized(fieldType("plain"));
        System.out.println("plain.ownArgs=" + plain.getActualTypeArguments().length);
        System.out.println("plain.ownerArg=" + requireParameterized(plain.getOwnerType())
                .getActualTypeArguments()[0].getTypeName());

        ParameterizedType staticNested = requireParameterized(fieldType("staticNested"));
        System.out.println("static.ownerIsClass=" + (staticNested.getOwnerType() instanceof Class<?>));
        System.out.println("static.owner=" + staticNested.getOwnerType().getTypeName());
        System.out.println("static.arg=" + staticNested.getActualTypeArguments()[0].getTypeName());

        WildcardType upper = (WildcardType) requireParameterized(fieldType("producers"))
                .getActualTypeArguments()[0];
        WildcardType lower = (WildcardType) requireParameterized(fieldType("consumers"))
                .getActualTypeArguments()[0];
        System.out.println("wildcard.upper=" + upper.getUpperBounds()[0].getTypeName());
        System.out.println("wildcard.lower=" + lower.getLowerBounds()[0].getTypeName());

        TypeVariable<?> variable = (TypeVariable<?>) requireParameterized(fieldType("genericList"))
                .getActualTypeArguments()[0];
        System.out.println("variable.name=" + variable.getName());
        System.out.println("variable.bound=" + variable.getBounds()[0].getTypeName());

        GenericArrayType genericArray = (GenericArrayType) fieldType("genericArray");
        GenericArrayType listArray = (GenericArrayType) fieldType("listArray");
        System.out.println("array.component=" + genericArray.getGenericComponentType().getTypeName());
        System.out.println("array.listComponentParameterized="
                + (listArray.getGenericComponentType() instanceof ParameterizedType));

        ParameterizedType subclass = requireParameterized(StringList.class.getGenericSuperclass());
        System.out.println("super.raw=" + subclass.getRawType().getTypeName());
        System.out.println("super.arg=" + subclass.getActualTypeArguments()[0].getTypeName());

        ParameterizedType implemented =
                requireParameterized(StringSource.class.getGenericInterfaces()[0]);
        System.out.println("interface.raw=" + implemented.getRawType().getTypeName());
        System.out.println("interface.arg=" + implemented.getActualTypeArguments()[0].getTypeName());

        Type captured = new TypeRef<List<String>>() {}.getType();
        System.out.println("captured=" + captured.getTypeName());
        System.out.println("captured.equalsField=" + captured.equals(names));

        List<?> runtimeList = List.of(1, 2);
        System.out.println("runtime.isList=" + List.class.isInstance(runtimeList));
        System.out.println("runtime.isArrayList=" + (runtimeList instanceof ArrayList<?>));
    }
}
```

**Compile and run:**

```bash
javac --release 17 -Xlint:all ParameterizedTypeDemo.java
java ParameterizedTypeDemo
```

**Verified stdout on a JDK supporting Java 17:**

```text
field.rawClass=java.util.List
field.generic=java.util.List<java.lang.String>
list.raw=java.util.List
list.owner=null
list.arg=java.lang.String
map.arity=2
map.valueParameterized=true
map.valueArg=java.lang.Integer
inner.raw=ParameterizedTypeDemo$Outer$Inner
inner.ownerParameterized=true
inner.ownerRaw=ParameterizedTypeDemo$Outer
inner.ownerArg=java.lang.String
inner.arg=java.lang.Integer
plain.ownArgs=0
plain.ownerArg=java.lang.String
static.ownerIsClass=true
static.owner=ParameterizedTypeDemo$Outer
static.arg=java.lang.Long
wildcard.upper=java.lang.Number
wildcard.lower=java.lang.Integer
variable.name=N
variable.bound=java.lang.Number
array.component=N
array.listComponentParameterized=true
super.raw=java.util.ArrayList
super.arg=java.lang.String
interface.raw=java.util.function.Supplier
interface.arg=java.util.List<java.lang.String>
captured=java.util.List<java.lang.String>
captured.equalsField=true
runtime.isList=true
runtime.isArrayList=false
```

When testing the program with `javac --release 17 -Xlint:all` after declaring `serialVersionUID` for `StringList`, the compiler emits no warnings in the test.

### Reading the Output in Three Main Groups

**Raw type:** `field.getType()` and `names.getRawType()` both represent `List`. `getGenericType()` represents the full `List<String>`.

**Owner type:** field `inner` has parameterized owner `Outer<String>`, field `plain` has **0** direct actual arguments yet its owner still holds String, and field `staticNested` has an owner of type Class Outer.

**Actual arguments:** `names` has String; `nested` has String and List<Integer> in the two direct slots; the `producers`/`consumers` fields have wildcards; `genericList` has TypeVariable N, without turning into Number or Integer on its own; the generic array fields use GenericArrayType.

### Why Not Print the Implementation Class Name of `ParameterizedType`?

A JDK implementation may use an internal class to implement the `ParameterizedType` interface. That internal class name is not a stable public API contract. Therefore, the program prints `instanceof ParameterizedType` checks and semantic data from getters, rather than relying on `type.getClass().getSimpleName()`.

## 9. TypeRef: Preserving the Description `List<String>` via an Anonymous Subclass

In Java, `List<String>.class` is not a valid expression and `List.class` does not store the String argument. A common technique for passing generic descriptions to a framework is a **type reference** (or *super type token*).

Minimal pattern:

```java
abstract static class TypeRef<T> {
    final Type getType() {
        Type superclass = getClass().getGenericSuperclass();
        if (!(superclass instanceof ParameterizedType type)) {
            throw new IllegalStateException("Missing type metadata");
        }
        return type.getActualTypeArguments()[0];
    }
}

Type captured = new TypeRef<List<String>>() {}.getType();
```

The block above is an excerpt that must be placed inside a class (and the instantiation line inside a method); the complete example in Section 8 places it properly.

Why does it work?

1. The expression `new TypeRef<List<String>>() {}` creates an anonymous subclass.
2. The generic superclass of the subclass is **declared** as `TypeRef<List<String>>`.
3. The class file can store metadata about how the subclass declared its generic superclass.
4. `getGenericSuperclass()` reads the `ParameterizedType` of `TypeRef<List<String>>`.
5. `getActualTypeArguments()[0]` retrieves the `List<String>` description as a `Type`.

In the Section 8 program, `captured.equalsField=true` because `TypeRef` and field `names` describe the same `List<String>` structure. This proves equivalence of **declared types** in reflection; it does not mean two List objects hold the same runtime data.

### When Does TypeRef Not Help?

If the source is:

```java
Object input = List.of(42);
```

then `TypeRef<List<String>>` does **not** prove `input` contains only Strings. It merely stores the type description desired by the caller. A deserializer library can use that description to decide how to construct/convert each element, yet **the library must execute the check/conversion**; the JVM does not attach TypeRef metadata onto `input`.

Another case: if a TypeRef is created across a generic layer where the argument is still only a type variable `T`, the metadata may contain `TypeVariable<T>` rather than a concrete Class. Do not expect reflection to always substitute T with the actual runtime type of a held value.

## 10. Parsing `ParameterizedType` Safely: Algorithmic Pattern

A useful Type explorer needs to branch on the **interface kind of Type**, not on string names or internal implementation classes.

Illustrative pseudocode:

```java
static void inspect(Type type) {
    if (type instanceof Class<?> clazz) {
        System.out.println("Class: " + clazz.getName());
    } else if (type instanceof ParameterizedType p) {
        System.out.println("Raw: " + p.getRawType().getTypeName());
        Type owner = p.getOwnerType();
        if (owner != null) {
            System.out.println("Owner:");
            inspect(owner);
        }
        for (Type arg : p.getActualTypeArguments()) {
            inspect(arg);
        }
    } else if (type instanceof TypeVariable<?> variable) {
        System.out.println("Variable: " + variable.getName());
        for (Type bound : variable.getBounds()) {
            System.out.println("Bound: " + bound.getTypeName());
        }
    } else if (type instanceof WildcardType wildcard) {
        for (Type upper : wildcard.getUpperBounds()) {
            System.out.println("Upper: " + upper.getTypeName());
        }
        for (Type lower : wildcard.getLowerBounds()) {
            System.out.println("Lower: " + lower.getTypeName());
        }
    } else if (type instanceof GenericArrayType array) {
        System.out.println("Generic array component:");
        inspect(array.getGenericComponentType());
    }
}
```

This is an illustrative method: it must be placed in a class importing `java.lang.reflect.*` or the individual interfaces. A production Type explorer also needs a policy to avoid cycles/infinite recursion on type variables with self-referential bounds, such as `E extends Enum<E>`, and depth limits if processing untrusted metadata.

Notes:

- Access `getOwnerType()` **before or alongside** arguments, so you do not miss generics on a member's enclosing type.
- Do not assume `getActualTypeArguments()` always has at least one element.
- Do not force every argument to Class; use `instanceof`.
- If the owner is a `ParameterizedType`, you can continue walking into the owner's owner.
- If a `TypeVariable` has multiple bounds, `getBounds()` returns those bounds; bounds can reference type variables themselves, so guard against cycles when analyzing the whole graph.
- `getTypeName()` is suitable for display, **not** a canonical serialization format for writing a custom generic parser with `split("<")` or `split(",")`.

## 11. Common Pitfalls When Using Generic Reflection

| Misconception | Consequence | Correct Understanding |
| --- | --- | --- |
| "`getRawType()` returns the full `List<String>`." | Loses String during analysis. | Raw type is only the underlying class/interface; read arguments separately. |
| "`getOwnerType()` is always null." | Misses Outer<String> in inner classes. | Member types have an owner; top-level types usually do not. |
| "Owner is always `Class<?>`." | Cast breaks on `Outer<String>.Inner<Integer>`. | Owner can be a ParameterizedType carrying type arguments. |
| "All arguments of a nested type live in one arguments array." | Mixes up or drops owner arguments. | Inner own args and owner args live at two different levels. |
| "ParameterizedType must have at least one argument." | Misses `Outer<String>.Plain`. | A non-generic member can still have a parameterized owner and 0 own args. |
| "`List<T>` always has a Class argument." | `ClassCastException` on encountering TypeVariable. | Argument is a Type, which can have multiple forms. |
| "`List<? extends Number>` has argument Number." | Loses wildcard information. | Actual arg is a WildcardType with upper bound Number. |
| "Field.getGenericType() is always ParameterizedType." | Cast fails on String, raw List, or T[]. | Check the actual Type kind first. |
| "`TypeRef<List<String>>` validates a runtime List." | Trusts unverified data. | It holds type declaration metadata; a separate validator/deserializer is needed. |
| "Internal reflection class names are stable APIs." | Code depends on JDK implementation details. | Depend on interfaces Type, Class, ParameterizedType, etc. |
| "`getOwnerType()` means superclass." | Builds an incorrect type diagram. | Owner is a member-declaration relationship, distinct from inheritance. |
| "`getGenericSuperclass()` substitutes all T in inherited fields." | Generic resolver returns wrong results. | Must traverse the type hierarchy and substitute type variables in context. |

## 12. When Do Raw Type, Owner, and Actual Args Matter in Real Projects?

### 12.1. JSON Deserialization and Data Binding

A library receiving the description `List<User>` needs to know:

- Raw container: `List`.
- Type argument: `User`.
- With `Map<String,List<User>>`, it must descend into the second argument and then into List's argument.

A `Class<List>` alone only identifies the container, not the object type of each element. `ParameterizedType` helps convey the **description**; the framework must still construct objects and validate/convert data according to its own logic.

### 12.2. Dependency Injection and Generic Repositories

Dependencies like `Repository<Order>` and `Repository<Customer>` share the same raw type Repository. A tool can read actual arguments in field/constructor declarations to distinguish the two requested dependencies.

For an inner class with a generic owner, the resolver must inspect `getOwnerType()`; comparing only the raw type and actual arguments of the inner class can miss enclosing generic information.

### 12.3. ORM / Serializer / Schema Generator

A schema generator can read `Field.getGenericType()` to distinguish `List<String>`, `List<Money>`, and `Map<String,Amount>`. When encountering `List<T>`, the tool may need to walk the type hierarchy to resolve T or accept that T is unknown.

Do not treat metadata as proof that runtime data is valid. For instance, a field declared as `List<String>` can still point to a collection into which an Integer was inserted via raw/unchecked operations.

### 12.4. API Analysis and Documentation Tools

When generating documentation from reflection, display the exact generic declaration rather than just `getType()`. For a nested member type, the owner matters to show `Outer<String>.Inner<Integer>` rather than just `Inner<Integer>`.

You must accept that metadata is not always complete, especially in legacy code, raw declarations, erased generic methods, and dynamically generated classes that do not preserve generic Signature metadata as expected.

## 13. `equals`, Immutability, and Things Not to Assume

`ParameterizedType` defines `equals` so implementations must compare based on the same generic declaration and matching type parameters. Therefore, two equivalent type descriptions can be compared with `equals`, rather than checking object reference identity with `==`.

The Section 8 program created:

- Type from field `Samples.names`: `List<String>`.
- Type from `new TypeRef<List<String>>() {}`: also `List<String>`.

The line `captured.equalsField=true` illustrates this equivalence. Do not assume `ParameterizedType` instances are interned, singletons, or the exact same instance across APIs.

`getActualTypeArguments()` provides a result array for callers to read; do not mutate the returned array expecting to alter class-file metadata or the original Type. Treat type descriptions as reflection structures for reading and comparing; if a framework needs to transform a graph of types, build your own model with clear equivalence rules.

## 14. Edge Cases to Consider

### 14.1. Top-Level Types vs. Member Types

`List<String>` has a null owner. `Outer<String>.Inner<Integer>` has owner `Outer<String>`. `Outer.Nested<Long>` has owner Class Outer. There is no single owner shape applicable to all member types.

### 14.2. Generic Metadata Can Be Missing or Malformed

Reflection may encounter `Signature` metadata referencing a missing class or a malformed signature structure. Generic reflection APIs can throw `TypeNotPresentException`, `MalformedParameterizedTypeException`, or other exceptions depending on the scenario/call path. For tools analyzing class files from untrusted sources, handle errors rather than assuming metadata is always valid.

### 14.3. Complex Owners and Type Variables

With deeply nested types, an inner type can be affected by type variables from multiple owners. Mapping a name T across different scopes must rely on `TypeVariable.getGenericDeclaration()` and the owner structure, not merely comparing the literal name `T`.

For example, `Outer<T>` and `Inner<T>` can both declare a parameter named T in two different scopes; two TypeVariables are not identical simply because `getName()` matches.

### 14.4. Generic Array Arguments

A field `List<String>[]` can be validly declared even though directly allocating `new List<String>[2]` is disallowed. `getGenericType()` gives a Type reflecting an array with a parameterized component. Distinguish **field type declaration** from **array creation expression**.

### 14.5. TypeName Is for Display, Not Data Proof

`type.getTypeName()` prints a human-readable type representation. It performs no runtime checks on collections, does not resolve type variables from an object instance, and does not replace a type resolver.

### 14.6. Reflection API and JDK Compatibility

Use the public interfaces `java.lang.reflect.Type`, `ParameterizedType`, `WildcardType`, `TypeVariable`, and `GenericArrayType`. Avoid depending on names or constructors of internal JDK implementation classes because they are implementation details. The sample examples were tested on Java 17 and do not require accessing internal packages.

## 15. Guide to Reading `ParameterizedType` When Debugging

If a log says "unable to determine generic type" or a framework misreads a nested repository:

1. **Identify the declaration site.** Is it a field, generic superclass, implemented interface, return type, or method parameter?
2. **Use the corresponding `getGeneric...` API**, not just `getType()`/`getSuperclass()`.
3. **Check the Type subtype** with `instanceof` before casting.
4. **Read the raw type** to identify the base structure: List, Map, Repository, Outer.Inner.
5. **Read the owner type** and traverse the owner if non-null, especially for non-static inner classes.
6. **Read actual arguments** level by level; do not arbitrarily flatten nested ParameterizedTypes.
7. **Handle wildcards, variables, and generic arrays** with their dedicated APIs; do not cast everything to Class.
8. **If an unknown T is encountered**, trace generic superclasses/interfaces and the type variable environment instead of blindly assigning T=Object.
9. **If data validation is required**, separate value checking from metadata reading. A TypeRef or field annotation is not sufficient as a validator.
10. **Verify against the exact bytecode/JDK being executed** when metadata or proxy classes differ from expectations.

A reliable logging approach is to print `Type.getTypeName()` alongside structured components and `instanceof` flags, avoiding logging internal reflection implementation class names.

## 16. Exercises and Answers

### Exercise 1: Reading List of String

Field declared as `List<String> names`. What are `getRawType()`, `getOwnerType()`, and `getActualTypeArguments()`?

**Answer:** Raw type is List; owner is null; there is one actual argument, Class String.

### Exercise 2: Nested Map

For `Map<String,List<Integer>>`, how many direct actual arguments does Map have?

**Answer:** Two. The second argument is ParameterizedType List<Integer>, and Integer is in List's actual arguments, not Map's third argument.

### Exercise 3: Inner Class

For `Outer<String>.Inner<Integer>`, where is String located?

**Answer:** In `getOwnerType()`, which is ParameterizedType Outer<String>. Inner's direct argument is Integer.

### Exercise 4: Member Without Its Own Generics

Why can `Outer<String>.Plain` still reflect as a ParameterizedType with 0 own arguments?

**Answer:** Plain is a non-static member of a parameterized owner. The owner's type carries String, while Plain declares no type parameters of its own.

### Exercise 5: Static Nested

For `Outer.Nested<Long>`, does the owner carry Outer's T?

**Answer:** No. A static Nested class is not tied to an `Outer<T>` instance; in the Java 17 example, the owner is Class Outer and the direct actual argument is Long.

### Exercise 6: Wildcard

Does `List<? extends Number>` have an actual argument of kind Class Number or WildcardType?

**Answer:** WildcardType. Number is the upper bound read from `getUpperBounds()`.

### Exercise 7: Type Variable

How does reflection describe the generic argument T of a field in `class Box<T> { List<T> xs; }`?

**Answer:** TypeVariable, not Class String automatically inferred from an existing Box<String> object.

### Exercise 8: GenericArrayType

Why can `T[]` and `String[]` return different Type kinds?

**Answer:** The array `T[]` has a non-reifiable type-variable component so it can be a GenericArrayType; `String[]` has a concrete runtime Class.

### Exercise 9: TypeRef

Does `new TypeRef<List<String>>() {}.getType()` verify that a List contains only Strings?

**Answer:** No. It describes the generic superclass of an anonymous subclass. A validator or deserializer must actually inspect/convert the data.

### Exercise 10: Comparing Types

Should you compare `ParameterizedType`s with `==` to check whether two descriptions both represent `List<String>`?

**Answer:** No. Use `equals` for equivalence of type descriptions; two APIs do not have to return the exact same Type instance.

### Exercise 11: Diagnosing ClassCastException

If `Field.getGenericType()` returns `Class<?>` but code casts directly to `ParameterizedType` and fails, what needs to be fixed?

**Answer:** Check the Type kind with `instanceof ParameterizedType`. Raw fields or ordinary classes do not have a ParameterizedType.

### Exercise 12: Owner Is Different from Extends

Does `getOwnerType()` return the superclass?

**Answer:** No. It describes the owner of a member type; the generic superclass relationship is read via `getGenericSuperclass()`.

## 17. Summary

`ParameterizedType` lets Java reflection read back the structure of a **declared type** after type erasure leaves runtime instances without separate runtime classes for each parameterization. Understand the three core parts:

- **Raw type:** the underlying class/interface, such as List, Map, or Outer.Inner.
- **Owner type:** the enclosing type of a member type, which may be null, Class, or ParameterizedType.
- **Actual type arguments:** the type parameters applied directly to this type, which may be Class, ParameterizedType, WildcardType, TypeVariable, or other Type structures.

For member classes, never omit the owner: `Outer<String>.Inner<Integer>` holds String in the owner and Integer in its own arguments. For complex generic APIs, traverse Type as a **structural tree**, check subtypes with `instanceof`, track bounds/type variables when necessary, and separate metadata from runtime validation.

**Takeaway:** Reflection can describe "the type written in the declaration", but it does not turn `List<String>` into a new runtime class and does not automatically guarantee that the actual data inside a List is String.
