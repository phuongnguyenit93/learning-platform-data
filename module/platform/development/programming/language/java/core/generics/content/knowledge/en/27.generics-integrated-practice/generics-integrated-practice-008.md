# Building a Heterogeneous Typed Store and Type Tokens for Nested Structures in Java Generics

## 1. Problem Statement and Expected Outcome

Normally, a generic collection stores multiple values of the **same element type**:

~~~java
List<String> names = List.of("Java", "Kotlin");
Map<String, Integer> points = Map.of("A", 10, "B", 20);
~~~

However, some applications need a **heterogeneous typed store**, where each key identifies the type of its associated value:

- Key `String.class` pairs with a `String`.
- Key `Integer.class` pairs with an `Integer`.
- Key representing `List<String>` pairs with a list of strings.
- Key representing `List<Integer>` pairs with a list of integers.
- Key representing `Map<String, List<Integer>>` pairs with that nested structure.

We want methods with generic signatures:

~~~java
<T> void put(TypeRef<T> key, T value);
<T> T get(TypeRef<T> key);
~~~

so the compiler checks the relationship between **key type** and **inserted data type**, while internally the store holds values of different types side by side.

Goals of this lesson:

1. Build a simple version using **`Class<T>` as a type token** for reifiable types like String/Integer.
2. Recognize the limitation: `List<String>.class` and `Map<String, List<Integer>>.class` do not exist in Java.
3. Build **`TypeRef<T>`** storing `java.lang.reflect.Type` to represent nested generic structures.
4. Build a store using `Map<Type, Object>` for internal storage, with a generic external API.
5. Understand precisely what is guaranteed at **compile time** versus **runtime validation** that a type token alone cannot guarantee.
6. Experiment in Java 17+, including catching mistyped data.

Do not call `TypeRef<T>` a "new runtime type" or assume it forces the JVM to preserve all generic info for every object. It holds a **type descriptor via Reflection**, while actual data still undergoes type erasure.

## 2. How Does a Heterogeneous Store Differ from a Plain Map<String, Object>?

An initial design:

~~~java
Map<String, Object> values = new HashMap<>();
values.put("title", "Java");
values.put("count", 3);
~~~

This stores multiple types, yet the value's type **is not linked to the key's type** by the type system:

~~~java
String title = (String) values.get("title");
Integer count = (Integer) values.get("count");
~~~

Manual casts written by callers can fail from typos in keys or if the entry under that key was overwritten.

A type-token store moves that relationship into **generic signatures**:

~~~java
store.put(String.class, "Java");
store.put(Integer.class, 3);

String title = store.get(String.class);
Integer count = store.get(Integer.class);
~~~

The compiler infers `T = String` or `T = Integer` from `Class<T>`, so callers need no cast on read.

Even though internal storage still uses Object, a properly designed API maintains the invariant:

> For each type token used as a key, the value stored under that key conforms to the type bound to that token at write time.

This is an **API invariant**, not runtime memory magic. If raw types, unchecked casts, reflection, or unsafe aliases mutating nested data are permitted, the invariant can still be broken.

## 3. First Version: Class<T> Type Token

`Class<T>` is a familiar, useful token for types directly checkable at runtime:

~~~java
final class ClassStore {
    private final Map<Class<?>, Object> values = new HashMap<>();

    <T> void put(Class<T> type, T value) {
        values.put(type, type.cast(value));
    }

    <T> T get(Class<T> type) {
        return type.cast(values.get(type));
    }
}
~~~

This is an **illustrative snippet**, assuming `java.util.*` is imported. The complete program appears in a later section.

Mechanism:

- `Map<Class<?>, Object>` stores token-value pairs of varied types.
- `put(Class<T>, T)` ties the token's type and the value's type within a single call.
- `Class.cast` checks the top-level runtime class, e.g., rejecting casting an `Integer` to `String`.
- `get(Class<T>)` returns T, inferred from the token supplied by the caller.

Invalid call blocked by the compiler:

~~~java
// store.put(String.class, 123); // Does not compile: incompatible T.
~~~

**Limitation:** `Class<T>` cannot directly represent nested type arguments like `List<String>`. `List.class` is the class token for raw `List`; it carries no String element information.

## 4. Why Does List<String>.class Not Exist?

Java permits class literals:

~~~java
String.class
Integer.class
List.class
Map.class
~~~

But the following expressions are **invalid**:

~~~java
// List<String>.class
// Map<String, List<Integer>>.class
~~~

Because generics in Java largely rely on **type erasure**. Instances of `ArrayList<String>` and `ArrayList<Integer>` share the same runtime class:

~~~java
var strings = new ArrayList<String>();
var integers = new ArrayList<Integer>();

System.out.println(strings.getClass() == integers.getClass()); // true
~~~

If the store used only `List.class`, lists with different element types would collide on the same key:

~~~java
// Same Class object used as key:
values.put(List.class, List.of("A"));
values.put(List.class, List.of(1)); // Overwrites the previous value.
~~~

You cannot solve this with an unchecked cast from `Class<List>` to `Class<List<String>>` and claim the type argument is restored. The JVM does not track String element info per List instance that way.

We need **an object describing a composite type**. Java Reflection provides `java.lang.reflect.Type` to represent types, not to make generic arguments reifiable.

## 5. Type and ParameterizedType Represent Nested Structures

`java.lang.reflect.Type` is the type-description abstraction in the Reflection API. Key subtypes include:

| Reflection API | Typical representation | Meaning |
| --- | --- | --- |
| `Class<?>` | `String.class`, `List.class` | Direct class/interface, without a type argument list. |
| `ParameterizedType` | `List<String>` | Type with a raw type and type arguments. |
| `TypeVariable<?>` | `T` in `class Holder<T>` | Bounded type variable, not necessarily holding a concrete runtime type. |
| `WildcardType` | `? extends Number` | Wildcard with upper/lower bounds. |
| `GenericArrayType` | `T[]` or compatible generic component array | Array type described by a composite Type. |

For `Map<String, List<Integer>>`, the type descriptor has a **nested** structure:

~~~text
ParameterizedType: Map<String, List<Integer>>
├── raw type: Map
├── argument 0: Class<String>
└── argument 1: ParameterizedType List<Integer>
    ├── raw type: List
    └── argument 0: Class<Integer>
~~~

This allows a key for `List<String>` to be distinguished from a key for `List<Integer>` by Type structure, even though both lists' runtime class may be ArrayList.

`ParameterizedType` typically uses structural equality: two Types describing the same generic declaration with the same type arguments are `equals`. That lets `Type` serve as a `HashMap` key, provided Types are constructed consistently.

Important: this is **type metadata**. Carrying a `ParameterizedType` does not guarantee every element inside an object associated with that metadata has the exact right type.

## 6. TypeRef<T>: Preserving Generic Signatures via Anonymous Subclasses

A common technique is the **super type token**:

~~~java
abstract class TypeRef<T> {
    private final Type type;

    protected TypeRef() {
        Type parent = getClass().getGenericSuperclass();

        if (!(parent instanceof ParameterizedType parameterized)) {
            throw new IllegalStateException("Use an anonymous subclass");
        }

        this.type = parameterized.getActualTypeArguments()[0];
    }

    public final Type type() {
        return type;
    }
}
~~~

This snippet uses Reflection imports and appears inside the complete program in section 8.

Creating tokens:

~~~java
TypeRef<List<String>> names =
        new TypeRef<List<String>>() {};

TypeRef<Map<String, List<Integer>>> nested =
        new TypeRef<Map<String, List<Integer>>>() {};
~~~

The `{}` creates an **anonymous subclass** extending `TypeRef<List<String>>` or `TypeRef<Map<...>>`. Reflection reads the **generic superclass** of the anonymous class to extract the Type describing the exact type argument written in source.

Inside the constructor:

1. `getClass()` is the actual anonymous subclass.
2. `getGenericSuperclass()` returns a `ParameterizedType` describing `TypeRef<List<String>>`.
3. `getActualTypeArguments()[0]` extracts the Type for `List<String>`.
4. The `type` field retains that Type, and the store can use it as a key.

**Requirement:** this technique requires the subclass to actually have a recorded generic superclass with concrete type argument info. `new TypeRef<String>() {}` works, whereas `new TypeRef() {}` uses a raw superclass, provides no `ParameterizedType`, and is actively rejected by the constructor above.

## 7. Designing a Store Using Map<Type, Object>

A unified store can hold both simple tokens and nested tokens:

~~~java
final class TypedStore {
    private final Map<Type, Object> values = new HashMap<>();

    public <T> void put(Class<T> token, T value) {
        values.put(token, token.cast(Objects.requireNonNull(value)));
    }

    public <T> T get(Class<T> token) {
        return token.cast(values.get(token));
    }

    public <T> void put(TypeRef<T> token, T value) {
        values.put(token.type(), Objects.requireNonNull(value));
    }

    @SuppressWarnings("unchecked")
    public <T> T get(TypeRef<T> token) {
        return (T) values.get(token.type());
    }
}
~~~

This component is part of the complete program in the next section.

### Why is Object needed internally?

No single `T` represents every stored value: the store holds String, Integer, List<String>, Map<String,List<Integer>>, and more. Therefore `Map<Type,Object>` serves as the heterogeneous backing store; the `put/get` APIs use method-level generics per call.

### Why is there an unchecked cast in get(TypeRef<T>)?

Runtime cannot use a `ParameterizedType` to perform a full deep cast to `List<String>` or `Map<String,List<Integer>>`. Here, `(T) values.get(token.type())` performs only an erased cast. The compiler may insert an additional cast for the reifiable outer type at the caller site.

The call is expected to be safe **by the store's invariant**: every entry must be inserted via `put(TypeRef<T>, T)` with matching types, with no raw/unchecked pathways corrupting data.

`@SuppressWarnings("unchecked")` should be placed **narrowly** on the single method containing the justified cast, not scattered across the entire class or project. It does not turn an uncheckable cast into a checked cast.

### Designing null values and missing keys

`put` above deliberately **rejects null** via `Objects.requireNonNull` to reduce ambiguity when `get` returns null. Even so, `get` returns null when no entry exists. Production APIs can use `Optional<T>`, `contains`, or throw an exception on missing keys; that is a contract choice independent of the type-token principle.

## 8. Complete Runnable Java 17+ Program

Save with exact filename **HeterogeneousStoreDemo.java**:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class HeterogeneousStoreDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType parameterized)) {
                throw new IllegalStateException("Use an anonymous subclass");
            }
            type = parameterized.getActualTypeArguments()[0];
        }

        public final Type type() {
            return type;
        }
    }

    static final class TypedStore {
        private final Map<Type, Object> values = new HashMap<>();

        public <T> void put(Class<T> token, T value) {
            values.put(token, token.cast(Objects.requireNonNull(value)));
        }

        public <T> T get(Class<T> token) {
            return token.cast(values.get(token));
        }

        public <T> void put(TypeRef<T> token, T value) {
            values.put(token.type(), Objects.requireNonNull(value));
        }

        @SuppressWarnings("unchecked")
        public <T> T get(TypeRef<T> token) {
            return (T) values.get(token.type());
        }
    }

    // Validate the entire Map<String, List<Integer>> structure at runtime
    // before accepting data from an untrusted source.
    static Map<String, List<Integer>> checkedNested(Object candidate) {
        if (!(candidate instanceof Map<?, ?> map)) {
            throw new IllegalArgumentException("Map required");
        }

        Map<String, List<Integer>> result = new HashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            String key = String.class.cast(entry.getKey());

            if (!(entry.getValue() instanceof List<?> raw)) {
                throw new IllegalArgumentException("List required");
            }

            List<Integer> numbers = new ArrayList<>();
            for (Object element : raw) {
                numbers.add(Integer.class.cast(element));
            }

            result.put(key, List.copyOf(numbers));
        }

        return Map.copyOf(result);
    }

    public static void main(String[] args) {
        TypedStore store = new TypedStore();

        // Class<T> type tokens: check top-level runtime class.
        store.put(String.class, "Hello");
        store.put(Integer.class, 3);

        // TypeRef<T> type tokens: preserve nested type arguments.
        TypeRef<List<String>> labels =
                new TypeRef<List<String>>() {};
        TypeRef<List<Integer>> scores =
                new TypeRef<List<Integer>>() {};
        TypeRef<Map<String, List<Integer>>> nested =
                new TypeRef<Map<String, List<Integer>>>() {};

        store.put(labels, List.of("Java", "Kotlin"));
        store.put(scores, List.of(10, 20));

        store.put(
                nested,
                checkedNested(
                        Map.of(
                                "odd", List.of(1, 3),
                                "even", List.of(2, 4)
                        )
                )
        );

        System.out.println("greeting=" + store.get(String.class));
        System.out.println("count=" + store.get(Integer.class));
        System.out.println("labels=" + store.get(labels));
        System.out.println("scores=" + store.get(scores));
        System.out.println("odd=" + store.get(nested).get("odd"));

        // Type serves as key structurally, not by identity of the token wrapper.
        System.out.println(
                "sameType=" +
                labels.type().equals(
                        new TypeRef<List<String>>() {}.type()
                )
        );
        System.out.println(
                "differentType=" + labels.type().equals(scores.type())
        );
        System.out.println(
                "nestedCaptured=" +
                (nested.type() instanceof ParameterizedType)
        );

        // A String element in an integer slot is rejected during validation.
        try {
            checkedNested(Map.of("bad", List.of("wrong")));
        } catch (ClassCastException error) {
            System.out.println("invalid=ClassCastException");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -Xlint:unchecked HeterogeneousStoreDemo.java
java HeterogeneousStoreDemo
~~~

Exact stdout:

~~~text
greeting=Hello
count=3
labels=[Java, Kotlin]
scores=[10, 20]
odd=[1, 3]
sameType=true
differentType=false
nestedCaptured=true
invalid=ClassCastException
~~~

Output explanation:

- Two simple values are stored using `String.class` and `Integer.class`, requiring no manual cast on read.
- The two keys `List<String>` and `List<Integer>` **differ** despite sharing raw type List. Thus the string list and integer list do not overwrite each other.
- The nested token records `Map<String, List<Integer>>`. Looking up key `"odd"` returns `List<Integer>` with `[1, 3]`.
- `sameType=true` shows two distinct anonymous TypeRef instances hold Types describing the same `List<String>`.
- `differentType=false` because `List<String>` is not `List<Integer>`.
- `nestedCaptured=true` confirms the nested Map token is represented by a `ParameterizedType`.
- `invalid=ClassCastException` arises inside **checkedNested** when `Integer.class.cast` encounters the String `"wrong"`. This is an explicit runtime check, **not an automatic check performed by TypeRef**.

The example uses `List.of` and `Map.copyOf` so returned collections resist casual modification through returned references. That lowers the risk of later mutation, though if mutable values originate elsewhere, watch out for aliases and unchecked operations.

## 9. Compile-Time Type Checking

Given token:

~~~java
TypeRef<List<String>> words =
        new TypeRef<List<String>>() {};
~~~

Valid call:

~~~java
store.put(words, List.of("Java", "Go"));
~~~

Intentionally invalid call:

~~~java
// store.put(words, List.of(1, 2)); // Does not satisfy List<String>.
~~~

In a normal method invocation with a `TypeRef<List<String>>` token, the compiler checks whether the list argument can be used as `List<String>`. Do not assume the store automatically converts Integers to Strings or filters bad elements.

With a nested token:

~~~java
TypeRef<Map<String, List<Integer>>> nested =
        new TypeRef<Map<String, List<Integer>>>() {};
~~~

Correct usage:

~~~java
store.put(nested, Map.of("scores", List.of(1, 2, 3)));
~~~

Misuse is caught by type parameter constraints:

~~~java
// store.put(nested, Map.of("scores", List.of("bad")));
~~~

The commented lines are **compile-error illustrations**, not part of a standalone runnable program.

### Loopholes a generic signature alone cannot close

A caller can still break type checking with raw types or unchecked casts:

~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafeInsert(TypedStore store, TypeRef<List<String>> key) {
    TypeRef raw = key;
    store.put(raw, List.of(123));
}
~~~

This illustrates intentionally unsafe code and compiles only where the referenced classes are accessible. When later retrieved as `List<String>`, reading an element as String can throw `ClassCastException`. Reason: the raw token dropped generic constraints, and TypeRef only holds type metadata rather than scanning every element of the value.

Never do this in real applications. When integrating legacy code, isolate unchecked casts inside a controlled adapter and validate data before placing it in the store.

## 10. Runtime Type Validation for Nested Structures

`Class.cast` can verify whether a top-level object is String or Integer. However, `Map<String, List<Integer>>` has multiple layers to check:

1. Outer object is a Map.
2. Every **key** is a String.
3. Every **value** is a List.
4. Every element of each List is an Integer.
5. If the system rejects null, enforce the policy across map, keys, lists, and elements.
6. To prevent modification after validation, create independent copies and restrict mutation.

That is why the program includes `checkedNested(Object)` using `instanceof Map<?, ?>`, `instanceof List<?>`, `String.class.cast`, and `Integer.class.cast`. After verifying every element, it constructs a fresh `Map<String, List<Integer>>`.

The method:

~~~java
static Map<String, List<Integer>> checkedNested(Object candidate)
~~~

acts as a **trust boundary**: accepting Object, validating structure, producing a verified typed value, and only then placing it into TypedStore.

**Note:** the example uses `List.copyOf` and `Map.copyOf` and thus **rejects null**; if null is valid in your domain, write a validation and copy step with an explicit null policy. Moreover, this validator is written specifically for one structure; TypeRef does not automatically supply a general-purpose validator.

### Why not use instanceof List<String>?

Java does not allow checking full generic type arguments with:

~~~java
// if (candidate instanceof List<String>) { } // Invalid.
~~~

Correct initial check:

~~~java
if (candidate instanceof List<?> list) {
    for (Object value : list) {
        // Validate each element against the expected type.
    }
}
~~~

`List<?>` can be checked at runtime as raw List, while the wildcard preserves unknown element typing in source. Type arguments like String do not become runtime checks enforced automatically by `instanceof`.

## 11. Type Tokens for Nested Generics and Key Equality

Given tokens:

~~~java
TypeRef<List<String>> a = new TypeRef<List<String>>() {};
TypeRef<List<String>> b = new TypeRef<List<String>>() {};
TypeRef<List<Integer>> c = new TypeRef<List<Integer>>() {};
~~~

Typically:

~~~java
a.type().equals(b.type()); // true
a.type().equals(c.type()); // false
~~~

When the store uses **`Type` itself** as the key, a and b access the same entry because they describe the same generic type. That matches "one structural type equals one key."

Watch out for two cases, however:

- If you use **the TypeRef object itself** as the key without defining `equals/hashCode` based on `type()`, two distinct TypeRef instances will not be equal.
- If multiple distinct values share the same type — e.g., two `List<String>` entries for "linguistics" and "translation" — **Type alone cannot distinguish them**. You need a key combining a name/id with Type, such as `record TypedKey<T>(String name, Type type)` with a type-checked API. Never assume a store keyed solely by Type handles multiple entries of the same type.

In the main program, `Map<Type,Object>` clearly models **at most one value per Type**; a subsequent `put` with the same Type replaces the previous value.

## 12. When a Super Type Token Cannot Record a Concrete Type

Reading the generic superclass does not automatically turn every type variable into a concrete runtime type argument.

Consider this pattern:

~~~java
static <X> TypeRef<List<X>> captureInGenericMethod() {
    return new TypeRef<List<X>>() {};
}
~~~

The captured Type may hold **`TypeVariable` X**, because when javac compiles the generic method, X remains a type variable. Calling the method with String at a call site does not generate a new anonymous class with `List<String>` baked into Reflection metadata.

Therefore, if the system requires exact keys like `List<String>` or `Map<String,List<Integer>>`, construct tokens where type arguments **are written concretely**, or build `Type` programmatically from provided tokens.

Some type-token libraries resolve type variables from context, wildcards, arrays, and complex generic supertypes. The minimal TypeRef in this lab only demonstrates **direct anonymous subclasses** with concrete types; it does not resolve TypeVariables, inspect generic owner types, perform full canonicalization, or provide general runtime validation.

Never promise `getGenericSuperclass()` is always a ParameterizedType: a raw subclass, a non-generic intermediate class, or unexpected inheritance structures can break the check. The example constructor explicitly throws an error when the expected form is absent.

## 13. Safety Limitations of the Store

### 13.1. Cannot stop mutable aliases containing mistyped data

If you store a mutable `ArrayList<String>`, other code holding a reference to that same object can mutate it; raw/unchecked code can even add mistyped elements.

~~~java
List<String> mutable = new ArrayList<>(List.of("A"));
store.put(new TypeRef<List<String>>() {}, mutable);

// If another party uses a raw alias to add an Integer, the invariant breaks.
// Fix: copy and validate at a trust boundary.
~~~

In the demo, lists from `List.of` and copies from `List.copyOf` disallow normal modification. Yet a minimal generic store does not automatically freeze every collection passed in by callers.

### 13.2. TypeRef records a type description, not a validator

These two statements are completely different:

- "I hold a token representing `List<String>`."
- "I have verified the runtime value is actually a List containing only Strings."

The first is metadata; the second requires **iterating/validating the data** or trusting an API with enforced invariants.

### 13.3. Type erasure still applies

The compiler inserts casts where results of generic method `get` are received. For `List<String>`, runtime checks the top-level List, not every inner element at the caller's cast. Errors can still surface when reading elements as String.

### 13.4. Missing keys and null are not type issues

In the demo, `get` returns null for missing keys while `put` rejects null to avoid conflating the two states. Production systems should explicitly specify missing-key behavior: Optional, exception, default value, or `contains` API. Never use casts or raw types to solve missing-key semantics.

### 13.5. Thread safety and versioning

`HashMap` in the demo is **not thread-safe** under concurrent writes or mixed reads/writes. In concurrent environments, use appropriate synchronization or `ConcurrentHashMap` alongside atomic operation and publication designs.

If using Reflection `Type` as a key in persisted data, do not assume `Type.getTypeName()` is a stable serialization format across refactoring, classloaders, or package renames. Persistence requires explicit schemas and versioning.

## 14. Common Mistakes and Fixes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using `List.class` to distinguish List<String> and List<Integer> | Type arguments do not exist in Class literals | Use TypeRef and `ParameterizedType` as keys. |
| Calling put with raw `TypeRef` | Loses T constraint between token and value | Keep `TypeRef<T>`, never use raw. |
| Assuming tokens make the JVM auto-check nested elements | Type erasure; token is metadata | Write a validator/checking adapter. |
| Using `Map<Type,Object>` and returning Object publicly | Forces callers to cast manually | Wrap with generic get/put methods taking tokens. |
| Storing mutable data and assuming the store stays valid | Aliases can mutate contents | Copy/freeze as appropriate; restrict write paths. |
| Using TypeRef as a key by object identity | Two tokens for the same type are distinct objects | Key by `type()` or define equals/hashCode. |
| Writing `new TypeRef() {}` | Raw subclass records no type argument T | Write `new TypeRef<List<String>>() {}`. |
| Capturing `List<X>` in a generic method expecting X to become String | Reflection still sees TypeVariable X | Supply concrete tokens from caller or resolve type variables explicitly. |
| Trying to store two distinct entries both typed List<String> | Type-only key collides | Use a typed key combining an identifier plus Type. |
| Conflating null and missing entries | API lacks a stated null contract | Pick Optional/exception/contains and enforce consistently. |

### Type mismatch caught early by the compiler

Example:

~~~java
TypeRef<Map<String, List<Integer>>> matrix =
        new TypeRef<Map<String, List<Integer>>>() {};

// store.put(matrix, Map.of("x", List.of("not a number")));
// Must fix the data to List<Integer>.
~~~

### Type mismatch the compiler cannot detect because input is Object

~~~java
Object externalData = receiveFromExternalSource();

// Do not immediately cast externalData to Map<String,List<Integer>>.
Map<String, List<Integer>> checked = checkedNested(externalData);
store.put(matrix, checked);
~~~

`receiveFromExternalSource()` is a placeholder name for a data-source API, not a standalone Java program. The lesson is to **validate and convert** an Object before binding it to a meaningful generic token.

## 15. Evolving a Real-World Heterogeneous Store

Depending on requirements, you can extend the demo pattern:

1. **TypedKey<T>** with id and `Type`: distinguish different roles sharing the same structural type.
2. **Validator<T>** paired with keys: validate at `put` time, especially for JSON, config, and external API data.
3. **Data copies/immutability**: prevent mutable aliases or raw APIs from breaking invariants after validation.
4. **Missing-value contract**: pick Optional, exceptions, or well-defined defaults.
5. **Inheritance/variance rules**: clarify when subtypes, wildcards, or exact token types are accepted; never use unchecked casts to fake covariance.
6. **Thread safety**: use synchronization, immutable snapshots, or concurrent maps if accessed concurrently.
7. **Negative tests**: ensure mistyped puts fail compilation and malformed data sources are rejected by validators.
8. **Storage format**: use versioned schemas and codecs if reading/writing outside the JVM.

Those additions address concerns beyond the demo store; **TypeRef is solely the type-identification piece**, not a replacement for validation, authorization, concurrency control, or persistence schemas.

## 16. Self-Check Questions

**Question 1.** Why can't a `Map<Class<?>,Object>` store use `List.class` to tell List<String> apart from List<Integer>?

**Answer:** Both share the same runtime raw class List. Generic arguments do not exist in `List.class`, so they produce the exact same key.

**Question 2.** Can two separately created `new TypeRef<List<String>>() {}` tokens access the same entry in Map<Type,Object>?

**Answer:** Yes. When `type()` returns two `ParameterizedType` instances describing the same List<String>, they compare equal via `equals` and map to the same key. This does not compare object identity of the TypeRef wrappers.

**Question 3.** Why doesn't `TypeRef<Map<String,List<Integer>>>` automatically catch a String element inside List<Integer> at runtime?

**Answer:** TypeRef is Reflection metadata describing type structure. Because of erasure, the JVM does not validate every nested element from TypeRef alone. You need a validator traversing the Map, Lists, and elements.

**Question 4.** A typed store still uses Map<Type,Object> internally. Does that contradict having a generic API?

**Answer:** No. The store needs a common container for disparate types; the generic methods tie token and data types together at compile time. Safety of the internal cast rests on well-typed write invariants and controlled data ingestion.

**Question 5.** Does `new TypeRef<List<X>>() {}` inside a generic method always represent List<String> if the caller uses X=String?

**Answer:** No. The generic superclass may capture TypeVariable X because the anonymous subclass was compiled while X had no concrete type. Provide a concrete token or resolve type variables from context.

**Question 6.** How do you store two List<String> entries with the same type but different roles?

**Answer:** Create a key combining a name/identifier with Type instead of using Type alone. The API must still link `TypedKey<T>` to value T.

**Question 7.** In the example, where is the string "wrong" caught?

**Answer:** Inside `checkedNested` while iterating List elements and calling `Integer.class.cast(element)`, not automatically by `get` or TypeRef.

**Question 8.** If the store is used in a multi-threaded environment, is replacing HashMap with ConcurrentHashMap enough to solve all safety issues?

**Answer:** Not yet. ConcurrentMap handles concurrent access to the map itself, yet you still must address value immutability, key/value contracts, validation, and atomicity for multi-step operations.

## 17. Key Takeaways

An API-safe heterogeneous store uses constraints `<T> put(Token<T>, T)` and `<T> T get(Token<T>)` to link key type and value type.

- **`Class<T>`** fits directly checkable runtime classes like String and Integer.
- **`TypeRef<T>` backed by `ParameterizedType`** distinguishes `List<String>`, `List<Integer>`, and `Map<String,List<Integer>>` as structured keys.
- **`Map<Type,Object>`** provides heterogeneous storage; internal casts rely on well-typed write invariants and should never leak raw storage to callers.
- **Metadata is not validation:** nested data sources, raw aliases, or unchecked casts can still violate types, requiring validation and copying at appropriate data boundaries.
- **Type-only keys** store at most one value per structural type; when multiple entries share a type, add domain-meaningful identifiers.

Mastering the boundary between **compile-time generic safety**, **Reflection type metadata**, and **runtime validation** is essential when designing heterogeneous stores in Java.