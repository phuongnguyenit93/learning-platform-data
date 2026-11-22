# The Relationship Between Compile-Time Type Checking and Runtime Data in Java Generics

Java Generics allow expressing and checking type relationships right in source code, but most type arguments (such as `String` in `List<String>`) do not become per-object runtime type information. To understand Generics properly, you must distinguish **the static type checked by the compiler** from **the actual class and values that exist when the JVM runs**.

## 1. Two Layers of Type Information

- **Compile time:** `javac` relies on declarations such as `List<String>`, `Box<Integer>`, method parameter types, `extends` bounds, and wildcards to check assignments, method calls, elements that can be added to collections, and return value types. The goal is to detect many mistakes before running.
- **Runtime:** the JVM operates on actual objects such as `ArrayList`, `String`, and `Integer`; it checks casts (`checkcast`), array stores (`aastore`), virtual dispatch, and other runtime rules. The JVM does not automatically know that an `new ArrayList<>()` instance currently carries the type argument `String` merely because a reference variable was declared as `List<String>`.
- **Type erasure:** Java generally compiles generic type arguments down to erased types: `List<String>` and `List<Integer>` share the same corresponding `List`/`ArrayList` runtime class. A type variable `T` is typically replaced by its upper bound, or `Object` if there is no explicit upper bound. The compiler inserts casts where needed and may generate bridge methods to preserve polymorphism.

This does not mean Java “loses all type checking” at runtime: the runtime still checks object types, and casts can still throw `ClassCastException`. What is erased is primarily **the generic type argument**, such as `String` in `List<String>`.

| Question | Compile time | Runtime |
| --- | --- | --- |
| Can you call `names.add(123)` when `names` is `List<String>`? | No, compile error. | Never gets a chance to run if the code does not compile. |
| Is the object an `ArrayList` or a `LinkedList`? | Known from initialization/flow analysis if enough information is available. | Determined by the actual class of the object. |
| Does an `ArrayList` hold `String` or `Integer`? | Uses the generic declaration to constrain operations. | An ordinary object itself does not retain that type argument information. |
| Is `String name = names.get(0)` guaranteed safe? | Valid under the assumption that the list obeys `List<String>`. | The compiler-inserted cast can fail if the list has been polluted. |
| Can `List<String>` be read from a field declaration? | Yes, in the compiler's type model. | Reflection can read the generic signature of the **declaration**, if metadata is present; this differs from per-object type arguments. |

## 2. Observing a Runnable Program

Create a file named `GenericsAtRuntime.java`:

```java
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

public class GenericsAtRuntime {
    static class Catalog {
        List<String> titles = new ArrayList<>();
    }

    public static void main(String[] args) throws Exception {
        List<String> titles = new ArrayList<>();
        titles.add("java");

        String title = titles.get(0);
        System.out.println(title.toUpperCase());

        ArrayList<Integer> counts = new ArrayList<>();
        System.out.println(titles.getClass() == counts.getClass());
        System.out.println(titles instanceof List<?>);

        Field field = Catalog.class.getDeclaredField("titles");
        System.out.println(field.getGenericType().getTypeName());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac GenericsAtRuntime.java
java GenericsAtRuntime
```

Expected output (`stdout`):

```text
JAVA
true
true
java.util.List<java.lang.String>
```

Step-by-step explanation:

1. `titles.add("java")` and `String title = titles.get(0)` are checked against the `List<String>` contract at compile time.
2. `titles` and `counts` are both instantiated with `new ArrayList<>()`. The type arguments in source code differ, but the runtime class is still the same `java.util.ArrayList`, so comparing `Class` objects returns `true`.
3. `instanceof List<?>` is valid: `List<?>` is a *reifiable* type that can be used in runtime checks. This only checks whether the object implements `List`; it does not verify element types.
4. `Field.getGenericType()` retrieves metadata of the **declared field** `Catalog.titles`, so it can read `List<String>`. That metadata does not prove every element currently inside the list is a `String`.

Note the distinction between `List<String> titles = new ArrayList<>();` and `new ArrayList<String>()`: the diamond syntax `<>` asks the compiler to infer the type argument, and does not change the nature of type erasure.

## 3. How Does Type Erasure Work?

Consider this illustrative source code:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class NumberBox<T extends Number> {
    T value;
}
```

At the level of visualizing the erased structure:

```java
// Explanatory model after erasure only,
// not the exact full source code that javac actually emits.
class Box {
    private Object value;

    Box(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}

class NumberBox {
    Number value;
}
```

Key rules:

- `T` without an explicit upper bound is typically erased to `Object`.
- `T extends Number` is erased to `Number`. With multiple bounds such as `T extends Number & Comparable<T>`, the **first** bound governs the erasure of `T`.
- Type parameters in `List<String>` and `Map<String, Integer>` do not exist as separate JVM classes like `ListOfString` or `MapOfStringInteger`.
- The compiler can insert casts or bridge methods. Some generic signatures are still stored in class/method/field metadata so tools and reflection can read them, so erasure does not mean deleting every trace of generics from `.class` files.

When you write:

```java
Box<String> box = new Box<>("hello");
String message = box.get();
```

The compiler knows `box.get()` has expression type `String`, but the erased version of `get` returns `Object`. In bytecode at the value's usage site, the compiler can insert `checkcast java/lang/String` to guard the assignment. If the actual data has the wrong type, the cast fails **at runtime**.

You can inspect the bytecode of the compiled example yourself with:

```bash
javap -c -p GenericsAtRuntime
```

Look for `List.get` calls and `checkcast` instructions where the result is used as a `String`. There is no need to assume exact bytecode offsets or ordering are identical across all JDK versions.

## 4. Why Can `ClassCastException` Still Happen After Passing the Compiler?

Generic type safety is guaranteed under the condition that a program uses generic APIs properly and does not break the contract via raw types, unchecked casts, unsafe array mutations, reflection, or separately compiled external code.

The following program intentionally creates **heap pollution**: a variable of a parameterized type pointing to a structure containing a value incompatible with its declared type.

Create a file named `HeapPollutionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");

        List raw = names; // Raw type: skips type argument checking.
        raw.add(42);      // Unchecked call: inserts Integer into List<String>.

        try {
            String second = names.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Run command:

```bash
javac -Xlint:rawtypes -Xlint:unchecked HeapPollutionDemo.java
java HeapPollutionDemo
```

`stdout` result:

```text
ClassCastException
```

`javac` emits warnings for the raw type and the unchecked element addition. Warnings do not automatically stop compilation. `raw.add(42)` can store an `Integer` because at runtime `ArrayList.add` accepts objects according to its erased type without automatically checking “must be String”. When retrieving the element and assigning it to `String`, the compiler-inserted cast discovers that the actual value is an `Integer`.

By contrast, writing `names.add(42)` directly is a compile error. The line `List raw = names` does not copy data: `raw` and `names` are two references to **the exact same list**. For the same reason, using `@SuppressWarnings("unchecked")` merely to hide warnings does not fix heap pollution.

Another unchecked cast:

```java
Object unknown = new ArrayList<Integer>();

@SuppressWarnings("unchecked")
List<String> assumed = (List<String>) unknown;
```

The runtime can only verify that `unknown` is a `List` matching the erased cast; it does not verify that the elements are `String`. The cast on this line can succeed, and the failure appears later when reading an element as a `String`. Only suppress warnings when you have independent grounds proving the data matches, and narrow the annotation scope to the exact line/variable needed.

## 5. Reifiable vs. Non-Reifiable: How Much Can Be Checked at Runtime?

A *reifiable* type retains enough information for the JVM's runtime type checks. Examples: `String`, `String[]`, `List<?>`, and the raw type `List`. A concrete parameterized type such as `List<String>` is generally *non-reifiable*: the `String` inside `<...>` is not used to verify every element at runtime.

| Expression | Valid? | Meaning |
| --- | --- | --- |
| `obj instanceof List<?>` | Yes | Checks whether the object has a runtime type compatible with `List`. |
| `obj instanceof List<String>` where `obj` has static type `Object` | No | Cannot verify the `String` type argument with `instanceof`. |
| `obj instanceof String` | Yes | Checks the runtime class type `String`. |
| `new List<String>[5]` | No | Cannot directly create an array with a non-reifiable generic component type. |
| `new List<?>[5]` | Yes | The array component type `List<?>` is reifiable. |
| `new T()` or `new T[5]` inside `class Box<T>` | No | The type variable `T` does not provide a suitable runtime constructor or component class. |

Java arrays and generic collections have different mechanisms:

- **Arrays are covariant and reified at the component-type level**: `String[]` is a valid `Object[]` under subtyping, but the JVM knows the real array holds `String` and can throw `ArrayStoreException` if someone tries to store an `Integer` into it.
- **Generics are invariant in their type arguments**: `List<Integer>` is not a subtype of `List<Number>`, even though `Integer extends Number`. This rule prevents someone receiving a `List<Number>` from putting a `Double` into a list that someone else treats as a `List<Integer>`.
- `List<? extends Number>` allows reading elements as `Number` but does not allow adding an arbitrary `Integer` or `Double` (except `null`), because the specific list type represented by the wildcard is unknown. `List<? super Integer>` allows adding `Integer` and reading elements out under the general safe type `Object`.

An array example for comparison:

```java
Object[] objects = new String[1];

try {
    objects[0] = 42;
} catch (ArrayStoreException ex) {
    System.out.println("ArrayStoreException");
}
```

This snippet prints `ArrayStoreException` if placed inside a runnable method. Arrays catch the error at the **write** site thanks to their runtime component type. By contrast, ordinary generic lists can be polluted via a raw type and have the error surface at the **read/cast** site.

## 6. Compile-Time Type Relationships Are Not Runtime Class Relationships

Several situations commonly cause confusion:

**a) Invariance does not disappear because of erasure.**

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Compile error.
List<? extends Number> readableNumbers = integers;
Number number = readableNumbers.isEmpty() ? 0 : readableNumbers.get(0);
```

Even though both lists erase to `List` at runtime, the compiler still enforces generic type relationships in the source program. Wildcards express usage capabilities; they do not make the JVM create a new kind of `List`.

**b) Two overloads differing only in type arguments can collide after erasure.**

```java
// The following two methods CANNOT both be declared in the same class:
// void process(List<String> values) {}
// void process(List<Integer> values) {}
```

After erasure both have parameter type `List`, causing a *name clash*. Give the methods different names, add genuinely distinct parameters, or design an appropriate single generic method.

**c) Overriding may require a bridge method.**

```java
class Parent<T> {
    T get() {
        return null;
    }
}

class Child extends Parent<String> {
    @Override
    String get() {
        return "child";
    }
}
```

At the source level, `Child.get()` overrides `Parent<String>.get()`. After erasure, `Parent`'s method returns `Object`, whereas `Child` returns `String`. The compiler can generate a synthetic bridge method so polymorphic calls through `Parent` still route to `Child.get()`. You can inspect this with `javap -c -p Child` after compiling the code in a suitable file.

**d) You cannot parameterize a generic type with a primitive.**

`List<int>` is invalid because generic type arguments must be reference types; use `List<Integer>`. Automatic boxing/unboxing makes working with `Integer` convenient, but it does not turn `int` into a JVM generic type argument.

## 7. What Does Reflection Know and Not Know?

A common misconception is “reflection has `ParameterizedType`, so erasure does not happen”. Both of these facts are true at the same time:

1. Metadata in class files can store **generic declarations** of fields, methods, superclasses, and interfaces. `Field.getGenericType()`, `Method.getGenericReturnType()`, `Class.getGenericSuperclass()`, or `Class.getTypeParameters()` allow reading this data.
2. An instance `new ArrayList<String>()` does not normally store `String` as a per-instance runtime property. `list.getClass()` returns `ArrayList.class`; `ArrayList.class.getTypeParameters()` reports that the class declares the type variable `E`, not the `String` argument used on the caller's reference variable.

For example, if you declare a specialized subclass:

```java
class StringList extends ArrayList<String> {
}
```

then `StringList.class.getGenericSuperclass()` can describe `ArrayList<String>` because the type is fixed in **the subclass declaration**. However, creating `new ArrayList<String>()` and querying `getClass().getGenericSuperclass()` does not provide the same information: the object belongs to `ArrayList`, whose superclass declaration does not bind `String`.

When an application needs to pass type information into runtime, there are two basic approaches:

- **Class token:** accept `Class<T>`, such as `String.class`, then use `type.cast(value)` or `type.isInstance(value)` to check a concrete class type. `Class<T>` cannot fully represent nested types such as `List<String>`.
- **Complex type representation:** pass `java.lang.reflect.Type` or a type token/type reference mechanism to preserve the `List<String>` structure for serializers/deserializers, frameworks, or mapping systems. Metadata only describes the expected type; checking individual elements still requires appropriate data-handling logic.

Do not infer element types solely from `collection.getClass()`; do not confuse a `ParameterizedType` describing a declaration or type token with the JVM automatically enforcing the generic argument on every collection instance.

## 8. What If You Want to Check Elements at Runtime Too?

When data comes from a type-untrusted source (JSON, reflection, legacy APIs, raw collections), validate it at the ingestion boundary.

**Approach 1 — explicitly check elements and build a typed copy:**

```java
import java.util.ArrayList;
import java.util.List;

public class CheckedConversion {
    static List<String> requireStrings(List<?> source) {
        List<String> result = new ArrayList<>();
        for (Object value : source) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException("Expected String");
            }
            result.add(text);
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> names = requireStrings(List.of("Lan", "Mai"));
        System.out.println(names);
    }
}
```

Running `javac CheckedConversion.java` and `java CheckedConversion` produces `stdout`:

```text
[Lan, Mai]
```

The function accepts `List<?>`, so reading each value as `Object` is safe. Pattern matching for `instanceof String text` (supported in Java 17) adds only verified values to the new list. With `List.of("Lan", 42)`, the function throws `IllegalArgumentException` at the conversion boundary. Using a copy also avoids aliasing input data that might be mutated later; if the resulting list should be unmodifiable, you can return `List.copyOf(result)` when elements are non-null.

**Approach 2 — use Collections' runtime-checked view:**

```java
List<String> checked = java.util.Collections.checkedList(
        new java.util.ArrayList<>(), String.class);
```

`Collections.checkedList` creates a view that blocks adding elements incompatible with `String.class`, even if legacy code accesses the view via a raw type. It uses a runtime class token to check elements, rather than creating a reified `List<String>` type. Note that this view does not protect against external code holding a direct reference to the backing list and mutating it, nor does it clean up wrong-type data that already existed before wrapping.

**Approach 3 — maintain typed APIs from the start:** use `List<String>`, `Map<K,V>`, generic methods, and appropriate wildcards; avoid raw types, unchecked casts, reflective inserts, and passing mutable aliases to code that does not uphold the contract. This is the primary defense; runtime checks supplement it at necessary boundaries.

## 9. Designing and Reading Errors Across Both Phases

When designing a generic method:

```java
import java.util.List;
import java.util.NoSuchElementException;

class FirstElement {
    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new NoSuchElementException("Empty list");
        }
        return values.get(0);
    }
}
```

`<T>` expresses the relationship **input `List<T>` → output `T`**. The compiler infers the type at call sites:

```java
String name = FirstElement.first(List.of("Lan", "Mai"));
Integer count = FirstElement.first(List.of(1, 2, 3));
// String wrong = FirstElement.first(List.of(1, 2, 3)); // Type error.
```

This example focuses on the type contract and consists only of illustrative declarations/calls; place the three calls inside a method when actually running it. After erasure, the JVM does not need separate `first` versions for `String` and `Integer`. The return type is enforced by the compiler at call sites; if data is polluted, the cast can fail.

When investigating errors, use the right signals:

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `incompatible types` | Incorrect compile-time type relationship, invariance, or missing valid conversion. | Fix the generic signature, wildcard, or passed data; do not force a cast just to get past the compiler. |
| `unchecked` / `rawtypes` warning | The compiler cannot prove the generic contract. | Trace raw types or unchecked conversions/casts; replace with typed APIs or per-element validation. |
| `ClassCastException` when reading a collection | Actual data has a class different from what the cast site expected. | Trace back where the data was inserted; look for raw aliases, reflection, deserialization, or unchecked casts. |
| `ArrayStoreException` | A reified array rejects writing the wrong component type. | Do not rely on covariance when writing elements; use an appropriate array type or a collection with the right generic contract. |
| `cannot select from a type variable` / `generic array creation` | Needs runtime information unavailable from `T`. | Accept a `Class<T>`, factory, `IntFunction<T[]>`, or redesign the API. |
| `name clash ... same erasure` | Generic signatures differ in source code but collide after erasure. | Rename methods or use genuinely distinct signatures. |

The command `javac -Xlint:unchecked -Xlint:rawtypes TenFile.java` helps uncover risky spots before runtime errors appear. When reading a `ClassCastException` stack trace, also look for where **the wrong-type data originated**, because the throwing line is often only where the data was retrieved and cast.

## 10. Misconceptions to Avoid

1. **“With Generics, `ClassCastException` can never happen.”** False: Generics check contracts at compile time; contract-breaking data can still enter via unchecked/raw/reflection paths.
2. **“The JVM knows this is a `List<String>` because the variable is declared that way.”** False: variable declarations are information used by the compiler, and do not attach `String` to the `ArrayList` object.
3. **“All generic information is completely lost after compilation.”** False: erasure applies to generic execution, but class files can retain `Signature` metadata for declarations; reflection can read that metadata.
4. **“`instanceof List<?>` proves all elements have the right type.”** False: it only checks the runtime `List` class structure.
5. **“`List<Integer>` can be assigned to `List<Number>` because `Integer extends Number`.”** False: generics are invariant in their type arguments; use wildcards matching your read/write needs.
6. **“Casting `(List<String>) someList` scans all elements.”** False: a regular unchecked cast does not inspect individual elements.
7. **“Suppressing warnings with `@SuppressWarnings` makes the data safe.”** False: the annotation only controls compiler warnings; it does not alter objects or add runtime checks.

## 11. Self-Check

**Scenario A.** Given `Object value = new ArrayList<Integer>();`. Can you use `value instanceof List<?>`? Yes, if the object implements `List`, it returns `true`. Can you use `value instanceof List<String>`? No: the `String` type argument is not reifiable for the JVM to check.

**Scenario B.** A method receives a `List<String>` from a legacy system, but the list already contains an `Integer`. Why does a `get` call sometimes only fail afterward? At the bytecode level, `get` operates on values using the erased type; the error occurs when the value is cast to `String` at a usage site requiring `String`. You cannot successfully obtain a `String` from an `Integer` by casting.

**Scenario C.** If you need to accept a list of numbers for reading only, should you choose `List<Number>` or `List<? extends Number>`? Choose `List<? extends Number>` when you want to accept both `List<Integer>` and `List<Double>`; in return, you cannot arbitrarily add numbers to the list.

**Scenario D.** Does `Field.getGenericType()` returning `List<String>` prove that the runtime data is a list of Strings? No. It reflects the declared field's type; elements can still be polluted if safety barriers were bypassed.

## Key Takeaway

Generics are a **strong compile-time type-checking contract**; type erasure allows instantiations to share runtime classes and implementations. The JVM still checks actual class types and casts, but it does not automatically validate specific generic type arguments on each collection object. Therefore, rely on generic types to design safe APIs, treat raw/unchecked warnings as signals to investigate, and validate actual data at ingestion boundaries when runtime guarantees are needed.