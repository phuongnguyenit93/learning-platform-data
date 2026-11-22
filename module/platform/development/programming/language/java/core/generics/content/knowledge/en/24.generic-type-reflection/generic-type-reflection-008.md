# Capturing Nested Types via Subclasses and the Type Token Pattern in Java Generics

## 1. Problem: How to Describe `List<Map<String, Integer>>` at Runtime?

Suppose an API needs to know the **full type of data** to read JSON, validate a schema, map data, or build an adapter:

```java
List<Map<String, Integer>> records;
```

This type has multiple levels:

- The outer level is `List`.
- The element of `List` is `Map<String, Integer>`.
- The key of `Map` is `String`.
- The value of `Map` is `Integer`.

If you only pass:

```java
List.class
```

then the `Map<String, Integer>` information **is not present in that `Class` object**. Java also has no valid class literal such as:

```java
// Invalid:
// List<Map<String, Integer>>.class
```

A **super type token** (often shortened to *type token*) is a technique for storing a generic type description by declaring **a subclass whose superclass is parameterized with a concrete type**, then reading the superclass's *generic signature* via Reflection.

Desired usage example:

```java
TypeRef<List<Map<String, Integer>>> token =
        new TypeRef<List<Map<String, Integer>>>() {};

Type type = token.type();
System.out.println(type.getTypeName());
```

Java 17 result:

```text
java.util.List<java.util.Map<java.lang.String, java.lang.Integer>>
```

Notice the curly braces `{}` at the end of `new TypeRef<...>() {}`. They create an **anonymous subclass**. It is that subclass that carries the superclass declaration with parameterized types, allowing Reflection to read back the structural chain `List<Map<String,Integer>>` written in source code.

This lesson focuses on capturing nested types via a superclass, traversing `Type`, limitations due to type erasure, handling `TypeVariable`/wildcards/generic arrays, and rules for using type tokens accurately and safely in real APIs. All main examples use Java 17.

## 2. Distinguishing Static Type, Runtime Class, and Generic Metadata

Consider two variables:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

In source code, the compiler treats the two variables as having **different parameterized types** and guards element writes/reads according to those types.

However, both objects are instantiated via `new ArrayList<>()`; at runtime:

```java
System.out.println(
        names.getClass() == numbers.getClass()); // true
```

There is no separate runtime class `ArrayList<String>` and another class `ArrayList<Integer>`. That is a defining property of **type erasure** in Java Generics.

Even so, saying "Java erases all generic information" is inaccurate either. The compiler can record **generic signature metadata of declarations** in the class file, such as:

```java
class StringList extends ArrayList<String> {
}
```

Class `StringList` explicitly declares its superclass as `ArrayList<String>`. Reflection can read that metadata via `StringList.class.getGenericSuperclass()`.

Points of distinction:

| Where Info Is Found | Question Answered | Limitation |
| --- | --- | --- |
| Static type `List<String>` | Which operations does the compiler allow? | Does not create a separate runtime specialization. |
| `object.getClass()` | What runtime class does the object have? | Generally does not know an instance's type arguments. |
| `SomeClass.class.getGenericSuperclass()` | How did the class *declare* its generic superclass? | Reads the declaration, does not validate object data. |
| `Field.getGenericType()` | What generic type is the field declared with? | Does not inspect the value currently assigned to the field. |
| `Method.getGenericReturnType()` | What generic return type does the method declare? | Does not automatically infer concrete type arguments per call. |
| Type token via subclass | What parameterized type did source declare on the superclass? | Usually only stores a `Type` description, does not auto-validate objects. |

**Essence:** type tokens leverage **metadata preserved at a declaration**; they do not reverse type erasure to recover arbitrary generic arguments from an existing object.

## 3. Kinds of `java.lang.reflect.Type` You Must Know

`java.lang.reflect.Type` is the interface representing types used by Reflection. Common forms:

| `Type` Kind | Example | Used When |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]` | Type has a corresponding class object. |
| `ParameterizedType` | `List<String>`, `Map<String,Integer>` | Type has generic arguments written in a declaration. |
| `TypeVariable<?>` | `T`, `E`, `K`, `V` | Declaration still has a type variable not substituted with a concrete type. |
| `WildcardType` | `?`, `? extends Number`, `? super Integer` | Generic argument is a wildcard with bounds. |
| `GenericArrayType` | `T[]`, `List<String>[]` | Array type whose component is non-reifiable in generic description. |

Since Java 8, every `Type` has a `getTypeName()` method to obtain a type name representation suitable for diagnostics and display.

### 3.1. `Class<?>` Is Not Synonymous with `Type`

`Class<?>` **is one kind of `Type`**, yet not every `Type` is a `Class<?>`.

```java
Type stringType = String.class; // Class<String> is a Type.
```

Whereas:

```java
Type listType =
        new TypeRef<List<String>>() {}.type();
```

`listType` is typically a `ParameterizedType` and **cannot be cast directly** to `Class<?>`:

```java
// May throw ClassCastException:
// Class<?> cls = (Class<?>) listType;
```

A framework working with generic metadata must branch on the actual runtime kind of the `Type` object, rather than always assuming it is a Class.

### 3.2. `ParameterizedType`

A `ParameterizedType` gives three key pieces of information:

```java
Type raw = p.getRawType();
Type[] arguments = p.getActualTypeArguments();
Type owner = p.getOwnerType();
```

For `List<Map<String,Integer>>`:

- `getRawType()` of the outer layer is `java.util.List`.
- The outer arguments array has **one element**: `Map<String,Integer>`.
- That argument is itself a `ParameterizedType`.
- The raw type of that argument is `java.util.Map`.
- Map's two arguments are `String.class` and `Integer.class`, respectively.

`getOwnerType()` is for the owner relationship of member/nested classes, **not** List's type arguments. For top-level types such as `List` and `Map`, the owner is normally `null`.

### 3.3. `TypeVariable<?>`

A type variable like `T` has a name, generic declaration, and bounds. For example:

```java
static <T> void work(T value) {
}
```

`T` does not automatically become `String.class` when the caller invokes `work("Java")`. If an anonymous subclass's metadata still contains `T`, the type token remains **unresolved into a concrete type**.

### 3.4. `WildcardType`

A wildcard `? extends Number` has upper bound `Number`. A `? super Integer` has lower bound `Integer`.

`WildcardType.getUpperBounds()` and `.getLowerBounds()` let a parser/validator read the declared bounds. They do not mean you can tell the exact subtype used by each runtime object.

### 3.5. `GenericArrayType`

`List<String>[]` can appear in a **type description** even though Java forbids `new List<String>[n]` directly. Reflection uses `GenericArrayType` to describe arrays with non-reifiable generic components, such as `List<String>[]` or `T[]`.

The type token technique can **store the description** of this type; storing metadata does not make it legal to instantiate an array object using syntax forbidden by the compiler.

## 4. Why Can an Anonymous Subclass Store Type Arguments?

Suppose you define:

```java
abstract class TypeRef<T> {
}
```

Then write:

```java
TypeRef<List<String>> token =
        new TypeRef<List<String>>() {};
```

This is **not simply** `new TypeRef<List<String>>()`. Since `TypeRef` is abstract, it cannot be instantiated directly. The `{}` syntax creates an anonymous concrete subclass, roughly analogous to:

```java
final class GeneratedTypeRef extends TypeRef<List<String>> {
}
```

The compiler records the generic superclass signature of the subclass as a declaration:

```text
TypeRef<java.util.List<java.lang.String>>
```

At runtime:

```java
Type superType = token.getClass().getGenericSuperclass();
```

Reflection returns the generic superclass description of the **anonymous class**. Because the superclass was declared with type arguments, the result is a `ParameterizedType`.

From there you can retrieve the argument `List<String>`.

### 4.1. The Exact Role of `{}`

Compare:

```java
new TypeRef<List<String>>() {};
```

with instantiating an ordinary generic class:

```java
new ArrayList<String>();
```

`new ArrayList<String>()` creates an `ArrayList` object without defining a subclass whose generic superclass signature contains `String`. By contrast, `new TypeRef<List<String>>() {}` creates an anonymous subclass of TypeRef whose **superclass signature** contains the specified structure.

Some anonymous-class diamond syntax has been supported since Java 9, yet when learning super type tokens, writing **all type arguments explicitly** inside `new TypeRef<...>() {}` makes it clear which type the metadata will capture.

### 4.2. This Is a Metadata-Retention Technique, Not Full Reification

Reflection reads information **in the class declaration of the anonymous subclass**. The JVM does not create `List<String>` objects with separate runtime classes, nor does it have a mechanism that automatically checks all elements of a list just received over the network or from a file.

In other words, a **type token describes the "expected type"**. Actual data checking or conversion is still performed by the library/application.

## 5. Building a Small, Standalone `TypeRef<T>`

A minimal example with clear checks:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.Objects;

abstract class TypeRef<T> {
    private final Type type;

    protected TypeRef() {
        Type parent = getClass().getGenericSuperclass();

        if (!(parent instanceof ParameterizedType p)
                || p.getRawType() != TypeRef.class) {
            throw new IllegalStateException(
                    "Use a direct parameterized subclass");
        }

        this.type = Objects.requireNonNull(
                p.getActualTypeArguments()[0]);
    }

    public final Type type() {
        return type;
    }
}
```

The class snippet above belongs in a Java file with the listed imports. It contains no JSON parsing logic; it simply **reads and holds metadata**.

Steps in the constructor:

1. `getClass()` gets the runtime class of the instance — an anonymous subclass or named subclass.
2. `getGenericSuperclass()` reads the declared superclass type.
3. The pattern `instanceof ParameterizedType p` verifies that superclass metadata has type arguments.
4. `p.getRawType() == TypeRef.class` confirms the **direct subclass** structure of `TypeRef` as designed.
5. `getActualTypeArguments()[0]` extracts the first type argument, which may be Class, ParameterizedType, TypeVariable, or another Type kind.
6. Field `type` stores that description for callers or frameworks to use.

### 5.1. Why Is the Constructor `protected`?

Users of this design create **subclasses**, not direct TypeRef instances. `protected` indicates that the constructor is intended for subclasses.

If external-package subclassing needs to be prevented, an API can choose another design; the example here prioritizes simplicity and verifiability.

### 5.2. Why Is Field `type` `final`?

The type structure is read once when the object is constructed. `final` makes clear that the token represents a **fixed type description**, not a mutable holder that can later switch from `List<String>` to `List<Integer>`.

Although `Type` is an interface, the implementations returned by the JDK from reflection represent declaration metadata. That does not guarantee every third-party `Type` implementation has proper immutability/`equals`/`hashCode` if you accept a Type from elsewhere.

### 5.3. Why Check `getRawType()`?

Just any `ParameterizedType` on the superclass **is not enough** to prove the first argument is `TypeRef`'s `T`. This code only handles the case:

```java
class NamedRef extends TypeRef<List<String>> {
}
```

or an equivalent direct anonymous subclass. With an intermediate class:

```java
class Intermediate<U> extends TypeRef<U> {
}

class Concrete extends Intermediate<List<String>> {
}
```

`Concrete.class.getGenericSuperclass()` is `Intermediate<List<String>>`, not `TypeRef<List<String>>`. The example's `getRawType() == TypeRef.class` check rejects it. This is an **intentional limitation of the simple `TypeRef`**, not an absolute limitation of every type token library.

An implementation supporting multiple inheritance levels must walk superclasses/interfaces and **substitute TypeVariables with actual type arguments level by level**. Calling `getGenericSuperclass()` once and taking argument `[0]` does not solve that general problem.

## 6. Nested Type Example `List<Map<String,Integer>>`

Declaration:

```java
TypeRef<List<Map<String, Integer>>> token =
        new TypeRef<List<Map<String, Integer>>>() {};
```

Reading:

```java
Type type = token.type();
System.out.println(type.getTypeName());
```

Output:

```text
java.util.List<java.util.Map<java.lang.String, java.lang.Integer>>
```

Decomposing level by level:

```java
ParameterizedType outer = (ParameterizedType) type;

Type rawList = outer.getRawType();
Type mapArgument = outer.getActualTypeArguments()[0];

ParameterizedType inner = (ParameterizedType) mapArgument;

Type rawMap = inner.getRawType();
Type key = inner.getActualTypeArguments()[0];
Type value = inner.getActualTypeArguments()[1];
```

Correspondingly:

| Component | Returned `Type` | Described Value |
| --- | --- | --- |
| `type` | `ParameterizedType` | `List<Map<String,Integer>>` |
| `rawList` | Typically `Class<?>` | `java.util.List` |
| `mapArgument` | `ParameterizedType` | `Map<String,Integer>` |
| `rawMap` | Typically `Class<?>` | `java.util.Map` |
| `key` | `Class<?>` | `java.lang.String` |
| `value` | `Class<?>` | `java.lang.Integer` |

There is no need to split the `getTypeName()` string by `<`, `,`, `>` and re-parse it. **Use the real `Type` tree** with `getRawType()` and `getActualTypeArguments()`; this handles wildcards, owner types, and nested arrays far better.

### 6.1. Why Is Casting to `ParameterizedType` Valid Here?

Because the token was written with type `List<Map<String,Integer>>`, and you inspect/know the `Type` structure from the example. In an API accepting **an arbitrary `Type`**, never cast unconditionally:

```java
Type t = String.class;

// Unsafe:
// ParameterizedType p = (ParameterizedType) t;
```

`String.class` is a `Class`, not a ParameterizedType. A general helper must use `instanceof` to branch.

### 6.2. `Type.getTypeName()` Is Not a Schema Validator

It is very handy for logging, debugging, and display. However, when a framework needs to turn JSON into objects, do not rely solely on this string to validate the whole structure. The reflection API already provides `Type` objects that carry clearer semantics than a display string.

## 7. Creating Type Tokens via Named Subclasses

An anonymous class is not mandatory.

```java
final class StringListRef extends TypeRef<List<String>> {
}
```

Then:

```java
Type type = new StringListRef().type();
```

Result:

```text
java.util.List<java.lang.String>
```

Advantage: gives a name to a frequently used type, making it easy to reuse and centralize. An anonymous subclass is more convenient when you just need a type token right at a call site:

```java
TypeRef<Map<String, List<Integer>>> token =
        new TypeRef<Map<String, List<Integer>>>() {};
```

### 7.1. Do Not Confuse a Named Subclass with a Class Instance Holding Data

`StringListRef` is **not** a `List<String>`. It is an object describing the type `List<String>`. Writing:

```java
StringListRef token = new StringListRef();
```

neither creates a new list nor holds any String elements.

A parsing API can accept `token.type()` and **based on metadata** construct a List; that is the parser's job, not the token's.

### 7.2. How to Use Constant Type Tokens

If a type description does not change, you can retain the token or `Type` within an appropriate scope, avoiding creating unnecessary anonymous subclasses at many call sites.

Even so, do not build an unbounded global static cache if the application has multiple class loaders, plugin classes, or dynamic types; cache lifecycle management is a separate responsibility.

## 8. A Type Token Can Contain Multiple Nested Kinds of `Type`

### 8.1. Bounded Wildcard

```java
TypeRef<List<? extends Number>> token =
        new TypeRef<List<? extends Number>>() {};
```

The outer level is List's `ParameterizedType`. The `? extends Number` argument is a `WildcardType`.

```java
ParameterizedType list =
        (ParameterizedType) token.type();

WildcardType wildcard =
        (WildcardType) list.getActualTypeArguments()[0];

Type upper = wildcard.getUpperBounds()[0];
```

`upper.getTypeName()` yields:

```text
java.lang.Number
```

This only indicates that source code declared upper bound Number. The token does not know whether an actual list object contains Integer, Double, or which specific subtype.

### 8.2. Generic Array

```java
TypeRef<List<String>[]> token =
        new TypeRef<List<String>[]>() {};
```

The `List<String>[]` description can appear as a `GenericArrayType`:

```java
GenericArrayType array =
        (GenericArrayType) token.type();

Type component = array.getGenericComponentType();
```

`component.getTypeName()`:

```text
java.util.List<java.lang.String>
```

Distinguish an **array type description** from **instantiating an array object**:

```java
// Invalid in Java:
// new List<String>[3];
```

Reading/storing a type token does not turn a forbidden allocation expression into a valid one.

### 8.3. `Class<?>` of a Normal Type

```java
TypeRef<String> token =
        new TypeRef<String>() {};
```

In this example `type()` is the `Class` for String:

```java
token.type() == String.class // true in this case
```

Not every token holds a ParameterizedType. A general API must accept different `Type` structures.

### 8.4. Deeply Nested Types

A token can describe deeper structures:

```java
TypeRef<Map<String, List<Map<Integer, String>>>> token =
        new TypeRef<Map<String, List<Map<Integer, String>>>>() {};
```

Traversal remains the same: descend from the outer `ParameterizedType` into each `getActualTypeArguments()` until reaching Class, TypeVariable, WildcardType, or GenericArrayType.

There is no "two-level limit" in this technique. The practical limits are validly declarable Java types, Reflection resources, and the processing capability of the framework consuming the `Type`.

## 9. Why Is `new TypeRef<List<T>>() {}` Not Enough to Know `T`?

This is the **most important limitation** when applying super type tokens inside a generic method.

```java
static <T> Type captureInside(T example) {
    return new TypeRef<List<T>>() {}.type();
}
```

Caller:

```java
Type type = captureInside("hello");
```

You might think the token already knows `T = String`. However, the anonymous subclass's class is generated by the compiler **from the generic method's common declaration**, not as a separate specialization per invocation.

The result represents:

```text
java.util.List<T>
```

The inner argument is a `TypeVariable`, **not `String.class`**.

### 9.1. Type Erasure Still Applies

In source code:

```java
static <T> Type makeToken() {
    return new TypeRef<List<T>>() {}.type();
}
```

type variable `T` is declared on the generic method. Metadata can preserve the **name and bounds** of T, but does not automatically replace it with the concrete class used by the caller at runtime.

Even when the caller writes:

```java
makeToken();
```

in a position with a clear target type, a token created inside the method is still not reified into a new specialized class.

### 9.2. Distinguishing "Storing `T`" from "Resolving `T`"

A type token **can store** a TypeVariable object. Yet storing the name `T` is not enough to know the runtime type argument of a specific call.

If a framework needs a concrete type, it must have a **context mapping the type variable**, such as a concrete subclass chain binding `T = String`, or the caller must pass a complete `Type`/type token from a site that knows the structure.

### 9.3. Pass `Type` from the Caller Instead of Creating a Token with `T` Inside

Instead of:

```java
static <T> Type wrongExpectation() {
    return new TypeRef<List<T>>() {}.type();
}
```

supply the concrete type info at the caller:

```java
TypeRef<List<String>> token =
        new TypeRef<List<String>>() {};

// Pass token.type() into an API accepting Type.
```

Or pass an explicit `Class<T>`/factory if the API only needs a **non-nested class**. Do not believe that merely seeing `<T>` in a method is enough to recover `T` after erasure.

## 10. Multi-Level Inheritance Requires Resolving Type Variables Level by Level

Consider:

```java
abstract class BaseRef<T> {
}

class Middle<U> extends BaseRef<List<U>> {
}

class Concrete extends Middle<String> {
}
```

If Reflection reads:

```java
Concrete.class.getGenericSuperclass()
```

the result is `Middle<String>`, not `BaseRef<List<String>>` directly.

If you continue reading the declaration of:

```java
Middle.class.getGenericSuperclass()
```

you then see `BaseRef<List<U>>`, where `U` is Middle's `TypeVariable`.

A general resolver must combine:

```text
Concrete -> Middle<String>
Middle<U> -> BaseRef<List<U>>
U -> String
Therefore: BaseRef<List<String>>
```

### 10.1. Why Is One `getGenericSuperclass()` Call Not Enough?

It only returns the **direct generic superclass** of the queried class. When there are multiple levels, the type arguments can sit in one class while the type variable to substitute sits in another.

If a library claims to support multi-level inheritance, check how it resolves `TypeVariable`s in context, and how it handles interfaces, owner types, bounds, generic arrays, and wildcards.

### 10.2. This `TypeRef` Intentionally Supports Only One Level

In the complete runnable program:

```java
static class Intermediate<U> extends TypeRef<U> {
}

static final class TooDeep
        extends Intermediate<List<String>> {
}
```

When creating `new TooDeep()`, `TypeRef`'s constructor gets the direct superclass of `TooDeep`, namely `Intermediate<List<String>>`. Its raw type is not `TypeRef.class`, so it proactively throws:

```text
Use a direct parameterized subclass
```

This rejects it **instead of storing the wrong** argument and claiming to have resolved the type accurately. If multi-level capture is needed, replace the implementation with a real generic type resolver rather than removing the check.

## 11. Type Tokens Differ from `Class<T>` Tokens

`Class<T>` is very useful when the target type is a runtime-checkable class:

```java
static <T> T checkedCast(Object value, Class<T> type) {
    return type.cast(value);
}
```

Caller:

```java
String s = checkedCast("Java", String.class);
```

However, there is no class literal syntax:

```java
// Invalid:
// List<String>.class
```

`List.class` only expresses the runtime class/interface List, not the String type argument.

Comparison:

| Purpose | `Class<T>` | Super Type Token Holding `Type` |
| --- | --- | --- |
| Know class `String` | Suitable | Also describes it |
| Describe `List<String>` | Does not retain type argument | Preserved from subclass declaration |
| Describe `Map<String,List<Integer>>` | Insufficient | Preserves full declared structure |
| Runtime `isInstance` with a class | Yes | `Type` provides no full automatic equivalent |
| Instantiate object via reflection | Can look up constructor, though may fail | Requires a framework that understands Type and object creation |
| Check every List element | No | Also **does not auto-check** |
| Handle wildcards and type variables | Incomplete | Has specialized `Type` forms to describe them |

**Type tokens do not replace `Class<T>` in every scenario.** If you only need to check a simple runtime class, a Class token is usually sufficient and easier to use.

## 12. A Type Token Does Not Automatically Make a `List<String>` Safe

Suppose someone creates a polluted list through a raw alias:

```java
List raw = new ArrayList();
raw.add(42);

@SuppressWarnings("unchecked")
List<String> claimed = (List<String>) raw;
```

This snippet is **intentionally unsafe** for illustration; when lint is enabled, raw/unchecked operations can trigger warnings.

You can certainly create a type token:

```java
Type token = new TypeRef<List<String>>() {}.type();
```

Yet the token does not cause `claimed` to contain Strings. When:

```java
String first = claimed.get(0);
```

runtime can still throw `ClassCastException`.

A real deserialization/conversion library must use the Type token as the **target type description**, and then validate or convert each element according to its policy.

### 12.1. `Type` Is Metadata; Validation Is a Separate Process

With token `List<Map<String,Integer>>`, a validator may need to:

1. Confirm the outer value is a list or convertible to a list.
2. Confirm each list element is a map.
3. Confirm each map's key is a String.
4. Confirm each map's value is an Integer, or apply a conversion rule from the input data.
5. Construct a result structure obeying the appropriate generic contract.
6. Handle nulls, missing elements, out-of-range numbers, extra fields, errors, and object lifecycles.

**Reflection metadata does not perform these steps automatically.** Different parsers may have different policies: reject invalid data, coerce numbers, ignore unknown fields, or return detailed errors.

### 12.2. Do Not Treat the Absence of `ClassCastException` as Proof That a Generic Type Is Safe

A runtime cast from an Object to raw `List` only checks the outer interface/class. If an Integer sits inside instead of a String, an unchecked generic cast does not detect it until code reads an element and expects a String.

A type token is a tool for **knowing what to check**, not an automatic general check.

## 13. How Does `Type` Metadata from Fields and Methods Differ from Type Tokens?

You can read a generic type from a field declaration:

```java
class Model {
    List<Map<String, Integer>> records;
}
```

Reflection:

```java
Field field = Model.class.getDeclaredField("records");
Type type = field.getGenericType();
```

If the field declaration is concrete, `getGenericType()` also returns a nested `ParameterizedType` structure.

Similarly:

```java
Method method = SomeClass.class.getDeclaredMethod("find");
Type type = method.getGenericReturnType();
```

This illustrative line assumes a no-arg method `find`. The method return type can be ParameterizedType, Class, or TypeVariable depending on the declaration.

### 13.1. When Should You Use Field/Method Reflection?

If the schema already exists on a concrete class/record/method, reflecting directly on the declaration may suffice. You do not always need to create an extra anonymous subclass.

A type token is useful when **the call site wants to describe an ad-hoc generic type** without a dedicated field/method to serve as the metadata source:

```java
new TypeRef<List<Map<String, Integer>>>() {}.type()
```

### 13.2. Do Not Confuse the Declared Type with the Current Value's Type

If a field `List<String> values` is assigned a list with invalid contents via unchecked code, `Field.getGenericType()` still returns the **declared** type. It does not know the current elements inside the list. That is the same limitation as a super type token.

## 14. Equality and Reusability of Type Descriptions

Two different anonymous subclasses can declare the same type:

```java
Type a = new TypeRef<List<String>>() {}.type();
Type b = new TypeRef<List<String>>() {}.type();

System.out.println(a.equals(b)); // true
```

With standard Reflection types, `ParameterizedType.equals` compares structural equivalence: raw type, owner type, and actual type arguments. Two tokens can originate from **two different anonymous classes**, yet still describe the same `List<String>`.

Conversely:

```java
Type x = new TypeRef<List<String>>() {}.type();
Type y = new TypeRef<List<Integer>>() {}.type();

System.out.println(x.equals(y)); // false
```

### 14.1. Do Not Compare the Classes of Anonymous Token Instances

Anonymous subclasses at two source sites have **separate classes**. Comparing:

```java
aToken.getClass() == bToken.getClass()
```

is not a sensible comparison for the data types they describe. Compare the **`Type` metadata** after capturing it.

### 14.2. Caching by `Type` Requires Attention to Scope

If you cache mappers/adapters by `Type`, the key usually needs to include the full generic structure, not just the raw class:

```text
List<String>  != List<Integer>
Map<String,Integer> != Map<String,Long>
```

However, do not automatically assume every third-party `Type` implementation has proper `equals`/`hashCode`; if you write your own `ParameterizedType` implementation, obey its contract. Also note that different classloaders can produce non-equivalent Class objects even with the same class name.

## 15. Complete Java 17 Program

Create the file **`NestedTypeTokenDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class NestedTypeTokenDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)
                    || p.getRawType() != TypeRef.class) {
                throw new IllegalStateException(
                        "Use a direct parameterized subclass");
            }
            type = Objects.requireNonNull(
                    p.getActualTypeArguments()[0]);
        }

        public final Type type() {
            return type;
        }
    }

    static final class NamedRef extends TypeRef<List<String>> {
    }

    static class Intermediate<U> extends TypeRef<U> {
    }

    static final class TooDeep
            extends Intermediate<List<String>> {
    }

    static <T> Type unboundInMethod(T value) {
        return new TypeRef<List<T>>() {}.type();
    }

    static String category(Type type) {
        if (type instanceof ParameterizedType)
            return "ParameterizedType";
        if (type instanceof GenericArrayType)
            return "GenericArrayType";
        if (type instanceof WildcardType)
            return "WildcardType";
        if (type instanceof TypeVariable<?>)
            return "TypeVariable";
        if (type instanceof Class<?>)
            return "Class";
        return "Unknown";
    }

    public static void main(String[] args) {
        TypeRef<List<Map<String, Integer>>> nested =
                new TypeRef<List<Map<String, Integer>>>() {};

        Type type = nested.type();
        System.out.println("nested=" + type.getTypeName());

        ParameterizedType outer = (ParameterizedType) type;
        System.out.println("outer-raw="
                + outer.getRawType().getTypeName());

        Type map = outer.getActualTypeArguments()[0];
        System.out.println("inner-kind=" + category(map));

        ParameterizedType inner = (ParameterizedType) map;
        System.out.println("map-raw="
                + inner.getRawType().getTypeName());
        System.out.println("map-key="
                + inner.getActualTypeArguments()[0].getTypeName());
        System.out.println("map-value="
                + inner.getActualTypeArguments()[1].getTypeName());

        TypeRef<List<String>> a =
                new TypeRef<List<String>>() {};
        TypeRef<List<String>> b =
                new TypeRef<List<String>>() {};
        TypeRef<List<Integer>> c =
                new TypeRef<List<Integer>>() {};

        System.out.println("type-equal="
                + a.type().equals(b.type()));
        System.out.println("type-different="
                + !a.type().equals(c.type()));
        System.out.println("named="
                + new NamedRef().type().getTypeName());

        Type boundType =
                new TypeRef<List<? extends Number>>() {}.type();
        WildcardType wildcard = (WildcardType)
                ((ParameterizedType) boundType)
                .getActualTypeArguments()[0];

        System.out.println("wildcard-kind="
                + category(wildcard));
        System.out.println("wildcard-upper="
                + wildcard.getUpperBounds()[0].getTypeName());

        Type arrayType =
                new TypeRef<List<String>[]>() {}.type();
        GenericArrayType ga = (GenericArrayType) arrayType;
        System.out.println("array-kind=" + category(arrayType));
        System.out.println("array-component="
                + ga.getGenericComponentType().getTypeName());

        System.out.println("simple-kind="
                + category(new TypeRef<String>() {}.type()));

        Type generic = unboundInMethod("actual String");
        Type nestedArgument = ((ParameterizedType) generic)
                .getActualTypeArguments()[0];

        System.out.println("method-capture="
                + generic.getTypeName());
        System.out.println("type-variable="
                + category(nestedArgument));

        List<String> strings = new ArrayList<>();
        List<Integer> integers = new ArrayList<>();
        System.out.println("same-runtime-class="
                + (strings.getClass() == integers.getClass()));

        try {
            new TooDeep();
        } catch (IllegalStateException ex) {
            System.out.println("indirect-rejected="
                    + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -Xlint:all NestedTypeTokenDemo.java
java NestedTypeTokenDemo
```

The code above compiles cleanly with Java 17 and `-Xlint:all`, with no warnings. **Exact stdout**:

```text
nested=java.util.List<java.util.Map<java.lang.String, java.lang.Integer>>
outer-raw=java.util.List
inner-kind=ParameterizedType
map-raw=java.util.Map
map-key=java.lang.String
map-value=java.lang.Integer
type-equal=true
type-different=true
named=java.util.List<java.lang.String>
wildcard-kind=WildcardType
wildcard-upper=java.lang.Number
array-kind=GenericArrayType
array-component=java.util.List<java.lang.String>
simple-kind=Class
method-capture=java.util.List<T>
type-variable=TypeVariable
same-runtime-class=true
indirect-rejected=Use a direct parameterized subclass
```

### 15.1. Analyzing the `nested`, `outer-raw`, `map-*` Group

The output shows a nested `ParameterizedType`, not just raw `List`. Navigating `getActualTypeArguments()[0]` from List down to Map, then from Map to String/Integer, recovers the exact structure **declared in the type token**.

### 15.2. `type-equal=true`, `type-different=true`

Two different anonymous subclasses describing the same `List<String>` have structurally equal `Type` metadata. `List<Integer>` differs from `List<String>` in its generic argument, so it is not the same `Type`.

### 15.3. `named=...`

`NamedRef` is an ordinary class declared as `extends TypeRef<List<String>>`. It also provides a readable superclass signature; using an anonymous class is not mandatory.

### 15.4. `wildcard-kind`, `array-kind`, `simple-kind`

The three results show that you cannot cast every `Type` to `ParameterizedType`:

- The wildcard inside `List<? extends Number>` is represented by `WildcardType`.
- `List<String>[]` is represented by `GenericArrayType`.
- `String` is `Class`.

Each kind must be interpreted according to Java semantics.

### 15.5. `method-capture` and `type-variable`

Even though the caller passes `"actual String"` to the generic method, Reflection still sees `List<T>`, with the inner argument being a `TypeVariable`. This proves that a type token does not reify `T` for each generic method invocation.

### 15.6. `same-runtime-class=true`

Two `ArrayList` instances with different type arguments still have the same runtime class, because Generics does not create separate runtime specializations per type argument. Type tokens do not change this.

### 15.7. `indirect-rejected=...`

The simple `TypeRef` only accepts a direct parameterized subclass. Class `TooDeep` has direct superclass `Intermediate<List<String>>`, so the constructor rejects it to avoid mistakenly recording an incompletely resolved `Type`.

## 16. Intentionally Non-Compiling Example: Generic Class Literal

Create the file **`InvalidClassLiteral.java`**:

```java
import java.util.List;

class InvalidClassLiteral {
    Class<List<String>> token = List<String>.class;
}
```

Compile:

```bash
javac --release 17 InvalidClassLiteral.java
```

The compiler reports a syntax error at the type arguments before `.class`, with the main message:

```text
error: <identifier> expected
```

This snippet is **intentionally wrong**. Java does not allow `List<String>.class` as a specialized class literal.

Fix depending on the goal:

```java
Class<?> rawClass = List.class;
```

if you only need the runtime class `List`.

Or use:

```java
Type nestedType =
        new TypeRef<List<String>>() {}.type();
```

if you need the full `List<String>` description for an API taking `Type`. This fix assumes you already have the `TypeRef` class from the complete program.

## 17. Common Mistakes When Writing Your Own `TypeRef`

### 17.1. Forgetting to Create a Subclass

A concrete `TypeRef` class that allows plain `new TypeRef<List<String>>()` will not store the type argument on the runtime class. Its constructor only sees `TypeRef`'s own superclass, not a declaration `extends TypeRef<List<String>>`.

Solution: create an anonymous/named subclass with a concrete parameterized superclass. In this example `TypeRef` is abstract so callers cannot instantiate it directly.

### 17.2. Forgetting `{}` After the Anonymous Subclass Creation Expression

```java
new TypeRef<List<String>>() {};
```

The `{}` syntax creates the anonymous class body. Changing it to:

```java
new TypeRef<List<String>>();
```

with an abstract `TypeRef` will not compile. Even if `TypeRef` is concrete, it still fails to declare a new subclass carrying the generic superclass signature as required by this technique.

### 17.3. Always Casting `getGenericSuperclass()` to `ParameterizedType`

Unsafe:

```java
ParameterizedType p =
        (ParameterizedType) getClass().getGenericSuperclass();
```

If the superclass is raw, not the expected generic declaration, or the class hierarchy differs, you may encounter `ClassCastException` or incorrect data.

You should check:

```java
if (!(parent instanceof ParameterizedType p)) {
    throw new IllegalStateException("Expected generic superclass");
}
```

And if the implementation only supports direct subclasses, check the specific raw type as in the example.

### 17.4. Taking the First Argument and Assuming You Already Have a `Class`

```java
Type t = p.getActualTypeArguments()[0];
```

`t` can be `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`, or `Class`. Do not cast directly to `(Class<?>)` without checking.

For `List<Map<String,Integer>>`, the outer argument is a **parameterized Map**, not a `Class` `Map` somehow carrying its arguments.

### 17.5. Ignoring Owner Types of Nested Classes

For nested/member generic classes, the owner portion can be a `Type` with its own generic structure. When building a general resolver, inspect `ParameterizedType.getOwnerType()` according to that class's rules.

Do not confuse an owner type with an argument of List or Map, and do not arbitrarily strip owner metadata when comparing or transforming types.

### 17.6. Using `Type.getTypeName()` as a Unique Identifier

Names are convenient for logs, yet two different class loaders can load classes with the same name that do not share the same `Class` identity. A cache/reflection resolver should key on `Type`/class identity with an appropriate contract, not merely a display string.

### 17.7. Thinking `TypeRef<List<T>>` Inside a Generic Method Has Resolved `T`

No. It may only store `TypeVariable T`. Pass a concrete `Type` from the caller, or use a resolver with context type mappings, rather than claiming you captured `String` from a runtime value.

### 17.8. Assuming a Type Token Validates Data Automatically

No. If a raw alias inserts an Integer into a list declared for Strings, a `List<String>` token neither fixes nor checks it. Guaranteeing data belongs to a generic type requires real parsing/validation code.

### 17.9. Writing an API Taking Only `Class<T>` and Trying to Squeeze Nested Data In

`Class<List>` does not hold `String`, and `Class<Map>` does not hold key/value arguments. If the goal is an API to deserialize generic structures, define the input to take `Type`/type token or an equivalent abstraction.

### 17.10. Using a Type Token as an Object-Creation Factory

`TypeRef<List<String>>` only stores `Type`; it has no method to construct an `ArrayList<String>` or resolve constructors for every generic type. Creating objects requires separate rules for choosing implementations, constructors, dependencies, and data policies.

### 17.11. Treating Reflection `Signature` as Always Complete

Generic metadata describes compiled declarations. Class files from non-standard sources, modified bytecode, or overly complex generic hierarchies can produce unexpected Reflection results or raise exceptions related to malformed/unresolvable types.

A robust framework needs error handling rather than hard-casting every `Type` to a single shape.

### 17.12. Using Type Tokens for Compile-Time Type Safety While Ignoring Unchecked Warnings

Type tokens are useful for carrying metadata across APIs; however, an unchecked cast from `Object` to `List<String>` still needs its invariant proven. Do not treat `@SuppressWarnings("unchecked")` as validation behavior.

## 18. Type Tokens in JSON / Deserialization Design

A hypothetical API might look like:

```java
<T> T fromJson(String json, TypeRef<T> targetType);
```

With call syntax:

```java
List<Map<String, Integer>> result =
        fromJson(json,
            new TypeRef<List<Map<String, Integer>>>() {});
```

This is an **illustrative signature and call**, not a built-in JDK API. It requires an actual library/parser implementation.

An implementation can use `targetType.type()` to walk the type structure and decide:

- Which collection implementation type to instantiate.
- Which adapter to use for keys/values.
- Whether nulls are accepted.
- What to do if JSON contains a number unsuitable for Integer.
- Whether unresolved wildcards/TypeVariables are supported.
- How to report detailed errors when the schema does not match.

Different libraries have different API names, such as the `TypeToken`, `TypeReference`, and `ParameterizedTypeReference` families; consult the exact version/documentation of the library you use. The core technique is identical: **conveying a generic `Type` description from a declaration into runtime logic**.

### 18.1. Verify Whether the Library Supports Nested `Type`s

Not every parser supports every kind:

- `Class<?>`.
- Multi-level `ParameterizedType`.
- `WildcardType`.
- Unresolved `TypeVariable<?>`.
- `GenericArrayType`.
- Owner types of nested classes.

An API accepting `Type` does not guarantee the implementation handles every kind of `Type`. Read the contract and test the actual structures you need.

### 18.2. Avoid "Parse JSON to Object and Then Unchecked Cast"

If a parser only produces `Object` or raw `Map`, casting to `Map<String, List<Integer>>` does not verify generic arguments. Pass the type token at parse time so the converter has the needed metadata, or explicitly validate and copy each level after parsing.

## 19. Designing an Appropriate `Type`-Tree Traversal Helper

A diagnostic helper can branch as follows:

```java
static String kind(Type type) {
    if (type instanceof ParameterizedType)
        return "ParameterizedType";
    if (type instanceof GenericArrayType)
        return "GenericArrayType";
    if (type instanceof WildcardType)
        return "WildcardType";
    if (type instanceof TypeVariable<?>)
        return "TypeVariable";
    if (type instanceof Class<?>)
        return "Class";
    return "Unknown";
}
```

This snippet requires Reflection imports and must be placed inside a class. It only classifies the type; it is not yet a serializer or validator.

When writing a **general resolver**, the branches can continue:

- For `ParameterizedType`: inspect owner, raw type, and actual arguments.
- For `GenericArrayType`: inspect component type.
- For `WildcardType`: inspect upper/lower bounds.
- For `TypeVariable`: inspect bounds and look up mappings by generic declaration/context.
- For `Class`: inspect array component via `getComponentType()` if the class is an array.

### 19.1. Beware of Type Graphs and Cycles

A type variable can have a recursive bound:

```java
class Node<T extends Comparable<T>> {
}
```

If a recursive walker does not track visited `Type` nodes or lacks a stopping rule, it can loop when moving from TypeVariable to bounds and back to TypeVariable.

A complete implementation needs cycle detection and type mapping policies, rather than naively recursing infinitely through all bounds.

### 19.2. Do Not Build Your Own Generic Type Parser When Using a Library Suffices

When application code only needs to deserialize JSON into a nested structure, using the library's built-in type token is usually enough. Implementing every branch of `Type`, owner, wildcard, and variable substitution yourself easily introduces subtle bugs.

You should understand the metadata to debug and design APIs, without necessarily writing a new generics framework for each project.

## 20. Key Misconceptions

| Claim | True or False? | Why |
| --- | --- | --- |
| `new TypeRef<List<String>>() {}` preserves `List<String>` metadata. | True, with a TypeRef that reads the superclass signature properly. | The anonymous subclass declares a generic superclass. |
| `List<String>.class` is valid. | False. | Java has no specialized class literal of that form. |
| `List.class` suffices to describe `List<Map<String,Integer>>`. | False. | It only describes the raw runtime class/interface. |
| `new TypeRef<List<T>>() {}` inside a generic method always knows `T=String` at the caller. | False. | Metadata can still hold `TypeVariable` `T`. |
| A type token automatically proves every list element is a `String`. | False. | Metadata and data validation are two separate things. |
| `Type` can always be cast to `Class`. | False. | There are `ParameterizedType`/`WildcardType`/`TypeVariable`/`GenericArrayType`. |
| `TypeRef<List<String>[]>` can store a generic array description. | True. | Reflection has `GenericArrayType`. |
| You can write `new List<String>[3]` thanks to `TypeRef`. | False. | Java generic array creation remains restricted. |
| Two different anonymous subclasses can represent equal `Type`s. | True. | Same generic declaration structure. |
| Multi-level subclasses only need one `getGenericSuperclass()` call. | False. | Usually requires substituting type variables across the hierarchy. |

## 21. Practice Questions with Answers

### Exercise 1. Why can't you use `List<Map<String,Integer>>.class`?

<details>
<summary>Answer</summary>

Java does not create a specialized runtime Class object per set of generic type arguments. Class literals can only be written in forms permitted by the language, which exclude specialized parameterized forms like `List<String>.class`. Use `List.class` if you only need the raw class, or `TypeRef`/type token if you want to describe a nested generic structure.

</details>

### Exercise 2. What does `{}` do in `new TypeRef<List<String>>() {}`?

<details>
<summary>Answer</summary>

It creates an anonymous subclass of TypeRef whose superclass is declared as `TypeRef<List<String>>`. That subclass's generic superclass signature is the metadata source that Reflection can read.

</details>

### Exercise 3. Does `getClass()` on `new ArrayList<String>()` reveal `String`?

<details>
<summary>Answer</summary>

No. The runtime class of an ordinary object is `ArrayList`, with no separate specialization for the String type argument. Type tokens work via superclass metadata **on the created subclass**, not via the runtime contents of ArrayList.

</details>

### Exercise 4. Which category does the outer `Type` of `List<Map<String,Integer>>` belong to?

<details>
<summary>Answer</summary>

`ParameterizedType` for List. Its sole argument is another `ParameterizedType` for Map; Map's raw type is Map, with arguments String and Integer.

</details>

### Exercise 5. Why isn't `getActualTypeArguments()[0]` always a `Class`?

<details>
<summary>Answer</summary>

Because a generic argument can be a parameterized type, wildcard, type variable, or generic array. For example, the argument of `List<Map<String,Integer>>` is a `ParameterizedType`, not a `Map.class` that automatically holds key/value arguments.

</details>

### Exercise 6. Does `new TypeRef<List<T>>() {}` inside method `<T>` guarantee knowing the concrete subtype chosen by the caller?

<details>
<summary>Answer</summary>

No. It can store `List<T>` with an unresolved TypeVariable T. To get a concrete type like List<String>, the caller must provide a concrete Type token or the framework must have a context mapping T.

</details>

### Exercise 7. Why did `TypeRef` in the program above reject `TooDeep`?

<details>
<summary>Answer</summary>

The constructor checks that the direct superclass has raw type equal to TypeRef. `TooDeep` directly extends `Intermediate<List<String>>`, not TypeRef. Supporting multiple levels requires a resolver that substitutes generic variables along the inheritance chain.

</details>

### Exercise 8. Does a type token for `List<? extends Number>` know whether the actual list contains Integers or Doubles?

<details>
<summary>Answer</summary>

No. A wildcard describes the upper bound Number, not a runtime specialization of an individual list object. You can use `WildcardType` to read the bound, while actual data must be checked separately if needed.

</details>

### Exercise 9. Can you store a generic array type even though `new List<String>[n]` cannot be created?

<details>
<summary>Answer</summary>

Yes. `TypeRef<List<String>[]>` can store `GenericArrayType` metadata, though that does not make generic array creation with a non-reifiable component valid.

</details>

### Exercise 10. What do you need to verify that JSON conforms to `Map<String,List<Integer>>`?

<details>
<summary>Answer</summary>

Provide a `Type` describing the expected structure to a parser/validator that supports nested types, and ensure the parser/validator actually validates/converts keys, values, collections, and each element. A type token only conveys metadata; it does not validate JSON or an object graph on its own.

</details>

## 22. Project Application Checklist

1. **Identify the real requirement:** do you only need `Class<T>`, or do you need to preserve `List<Map<String,Integer>>`?
2. When nested types are needed, create the token **where concrete type arguments are known**, e.g. `new TypeRef<List<Map<String,Integer>>>() {}`.
3. Check whether `getGenericSuperclass()` returns Class or ParameterizedType; do not cast blindly.
4. Walk the `Type` tree level by level instead of manually splitting `getTypeName()` strings.
5. Recognize unresolved `TypeVariable`s; do not advertise them as concrete `String.class`.
6. If multi-level subclasses are needed, use a resolver with substitution mapping rather than a single Reflection call.
7. For JSON/deserialization, verify how your library handles nested Types, wildcards, and null policies.
8. Separate **metadata** from **validation**, avoiding unchecked casts of external data without checks.
9. When caching type-based adapters, distinguish full type arguments, owner types, and class loader context where applicable.
10. Use Java 17 to compile examples/tests covering nested types, named subclasses, wildcards, generic arrays, and unresolved type variables.
11. If an API only requires a concrete runtime class, `Class<T>` remains the simpler and right tool.
12. Never read generic metadata of an instance and assume all current runtime data conforms to the declaration.

## 23. Summary

**A super type token preserves nested generic information by declaring a subclass whose superclass is concretely parameterized.** With:

```java
new TypeRef<List<Map<String, Integer>>>() {}
```

the anonymous subclass holds metadata for `TypeRef<List<Map<String,Integer>>>`, so Reflection can retrieve the `Type` of `List<Map<String,Integer>>` and traverse nested `ParameterizedType`s down to `String`/`Integer`.

This technique is especially useful when an API needs a **complete type description** rather than just `List.class`. Remember three limitations:

- **Type erasure remains**: a type token does not turn every `List<String>` into a separate runtime class.
- **TypeVariables may remain unresolved**: `List<T>` inside a generic method does not automatically become `List<String>` at each call.
- **Metadata is not validation**: a parser/validator must actually read and verify data against the described schema.

Use a simple, direct `TypeRef` at call sites with concrete generic structures; use a capable resolver/framework if you must handle multi-level inheritance, owner types, wildcards, or type variables. Once you clearly understand the metadata source and its limits, you can pass nested type info into Reflection, serialization, and data mapping without confusing it with runtime type checks.
