# Type Erasure in Method Signatures and Array Types (Java Generics)

## 1. The big picture

**Type erasure** is the mechanism Java uses to compile most generic type information into forms compatible with JVM classes and method descriptors. When you write `List<String>`, `List<Integer>`, `T`, `T[]`, or a method `<T> T identity(T value)`, the compiler checks them using generic information and then emits bytecode containing erased types.

This lesson focuses on the **two places with the clearest consequences**:

1. **Method signatures**: parameters, return types, overloads, overrides, and the bridge methods the compiler can generate.
2. **Array types**: runtime element types of arrays, arrays containing type variables or generic parameterized types, *reifiable* types, and how to create arrays safely.

After reading this, you can predict the bytecode descriptor of a generic method, analyze `name clash`/`generic array creation` errors, understand why arrays and `List<T>` follow different rules, and use `javap` and reflection to inspect them.

This is a **compilation and type-representation** mechanism. Erasure does not delete objects from memory, nor does it turn every type check into an arbitrary delayed runtime check.

## 2. Type erasure rules for generic signatures

Key rules to know:

| Type in source | Form after erasure | Reason |
| --- | --- | --- |
| Unbounded type variable `T` | `Object` | The default bound is `Object`. |
| `<T extends Number>` | `Number` | The type variable is replaced by its first bound. |
| `<T extends Number & Comparable<T>>` | `Number` | Among multiple bounds, the **first bound** is used to erase `T`. |
| `<T extends Comparable<T> & java.io.Serializable>` | `Comparable` (raw) | The first bound is interface `Comparable<T>`; the parameterized type itself is also erased. |
| `List<String>` | `List` (raw at bytecode descriptor level) | The type argument `String` does not participate in the descriptor. |
| `Map<String, List<Integer>>` | `Map` | Nested type arguments no longer appear in the descriptor. |
| `T[]` when `T` is unbounded | `Object[]` | Erase component type `T` first while keeping the array dimensions. |
| `T[]` with `T extends Number` | `Number[]` | The component type is erased to `Number`. |
| `List<T>[]` | `List[]` | An array remains an array; component type `List<T>` is erased to `List`. |

The "first bound" rule relies on Java's valid declaration order: if there is a class bound, the class bound must precede any interface bounds. The remaining bounds are still used by the compiler **during source checking**; they do not mean the JVM keeps multiple parameter types in one descriptor.

A short example:

```java
static <T> T identity(T value) {
    return value;
}

static <T extends Number> T keep(T value) {
    return value;
}
```

At the JVM *method descriptor* level, they correspond to:

```text
identity: (Ljava/lang/Object;)Ljava/lang/Object;
keep:     (Ljava/lang/Number;)Ljava/lang/Number;
```

JVM notation:

- `L...;` denotes a class/interface reference type, with `/` separating packages.
- Types inside `(...)` are parameters in order.
- The part after `)` is the return type.
- `V` denotes `void`; a leading `[` denotes one array dimension. For example, `[Ljava/lang/String;` is `String[]`.

**Note:** Descriptors and the **generic `Signature` attribute** in a class file serve different roles. The descriptor records the erased form used to link calls in the JVM; `Signature`, if present, can store generic metadata for the compiler and reflection to inspect. Do not conclude that "generics exist nowhere in `.class` files" — what is true is that **each `List<String>` object does not carry a separate runtime `String` argument that can be tested with `instanceof List<String>`**.

## 3. Type erasure in method parameters and return values

### 3.1. Generic methods declaring their own type variable

Consider the method:

```java
static <T> T identity(T value) {
    return value;
}
```

From the source-code perspective:

```java
String s = identity("Java");
Integer n = identity(5);
```

The compiler infers `T` separately for each call. Yet the method in bytecode is not duplicated per type:

```text
identity(Object) -> Object
```

The JVM signature has only one method body. The compiler can insert `checkcast` at the site **consuming the result** when the context requires a concrete type such as `String`. It also applies boxing/unboxing conversions according to Java's rules.

That does not mean `identity` can return a `String` from an `Integer` input when source code declares `String s = identity(5);`: generic type checking catches the error before runtime.

### 3.2. Class type variables are also erased

```java
class Box<T extends Number> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

In bytecode, the field and basic signatures use `Number`:

```text
value: Number
Box(Number)
get() -> Number
```

When writing `Box<Integer> box = new Box<>(7); Integer n = box.get();`, the target type `Integer` is still checked by the compiler, and the caller's bytecode may need a cast from `Number` to `Integer`.

If you declare two variables `Box<Integer>` and `Box<Double>`, there are not two specialized `Box` class definitions. Java generics primarily use **one erased class**, unlike template specialization per type argument in some other languages.

### 3.3. Combined type bounds: erasure vs. source-level checking

```java
static <T extends Number & Comparable<T>> T greater(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

In source code, `T` must simultaneously be a `Number` and implement `Comparable<T>`, so `compareTo` can be called. Because `Number` comes first, the descriptor is:

```text
(Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/Number;
```

This **does not mean** the JVM automatically treats every `Number` as `Comparable`: the compiler emits appropriate bytecode operations to access the required interface while still enforcing the generic constraints at compile time. For example, `greater(4, 9)` is valid because `Integer` satisfies the bounds; do not pass an arbitrary `Number` subclass that does not implement `Comparable` and expect erasure to check it for you.

## 4. Signature collision after type erasure: `name clash`

Java **does not allow overloading based solely on generic type arguments** if two declarations end up with the same signature after erasure:

```java
import java.util.List;

class InvalidOverloads {
    void print(List<String> strings) {}

    void print(List<Integer> numbers) {} // Compile-time error: name clash
}
```

Both methods above have their parameter erased to `List`, corresponding to:

```text
print(Ljava/util/List;)V
```

Renaming parameter variables or changing `String` to `Long` does not help. The JVM does not have enough information to distinguish these two calls by type arguments, so the compiler rejects them in source code.

Fixes depend on your intent:

```java
import java.util.List;

class DistinctOperations {
    void printStrings(List<String> strings) {}
    void printNumbers(List<Integer> numbers) {}
}
```

Or write **a single generic method** when the shared processing behavior is genuinely the same:

```java
static <T> void printAll(List<T> items) {
    items.forEach(System.out::println);
}
```

If business logic needs to dispatch based on element kind, consider an API or strategy carrying a type token (`Class<T>`) **when needed**, instead of assuming `List<String>` and `List<Integer>` will have two separate runtime classes.

Contrast this with overloads having different raw parameters: `work(List<String>)` and `work(ArrayList<Integer>)` **can** be two overloads because erasure gives `List` and `ArrayList` respectively for the first parameter. The issue is not whether a method "has generics", but whether **the erased signatures collide** under Java's rules.

### 4.1. Return types do not distinguish overloads

Two methods with the same name and same parameter type list that differ only in return type do not form a valid overload in Java:

```java
// Illustrative snippet that does not compile:
String pick() { return "a"; }
Integer pick() { return 1; }
```

In a class file, descriptors include the return type, but **the Java language's declaration and overload resolution rules** do not let you write two methods differing only by return type. Bridge methods that the compiler can generate exist to support overriding in bytecode, not as a feature allowing programmers to overload by return type.

## 5. Overriding with generics and bridge methods

Type erasure can make the **descriptor of an overridden method differ from the implementation's signature**. For example:

```java
class Parent<T> {
    T value() { return null; }
}
class Child extends Parent<String> {
    @Override String value() { return "child"; }
}
```

In `Parent<T>`, `value()` is erased to `()Ljava/lang/Object;`. Because `Child.value()` returns `String`, the compiler can emit a synthetic **bridge method** returning `Object` so polymorphic calls through `Parent<String>` still dispatch properly. Verify with `javap -v` or `Method.isBridge()`. This is **not** specialization of `Parent<T>`, and not every method involving generics needs a bridge.

The lesson on **first bound** further explains the case where a bridge descriptor uses `Number` instead of `Object`. The present lesson continues focusing on **method signatures and array types after erasure**.

## 6. Arrays in the JVM vs. generic containers

**Arrays have a runtime component type**: a `String[]` knows at runtime its components are `String`, and a `Number[]` knows its components are `Number`. Java arrays are **covariant**—for instance, `String[]` can be assigned to `Object[]`, and the JVM checks writes when storing elements:

```java
String[] names = new String[1];
Object[] objects = names;
objects[0] = 42; // ArrayStoreException at runtime
```

Conversely, `List<String>` is not a subtype of `List<Object>` because Java generics are **invariant**:

```java
List<String> names = List.of("Java");
// List<Object> objects = names; // Compile-time error
```

This difference is a major reason Java **disallows direct creation of arrays of most non-reifiable generic types**: the array's runtime element-checking mechanism cannot know the full type argument to protect `List<String>[]`.

### 6.1. What is a reifiable type?

A type is called *reifiable* if its runtime information is sufficient to represent that type under the conditions of the Java language. Common cases:

- `String`, `Integer`, `Number`, primitive types, and `String[]` are reifiable.
- The raw type `List` and `List<?>` where **all** type arguments are unbounded wildcards are reifiable.
- `List<String>`, `List<? extends Number>`, and type variable `T` are not reifiable types.
- An array whose component type is reifiable is also reifiable, such as `List<?>[]`.

That is why:

```java
String[] names = new String[2];      // Valid
List<?>[] all = new List<?>[2];      // Valid
// List<String>[] bad = new List<String>[2]; // generic array creation
// T[] bad = new T[2];                       // Invalid in a generic context
```

The `List<?>[]` line does not let you freely stuff wrong elements into a `List<String>` unchecked. It merely states that each slot holds a `List<?>`; elements read from it are treated as `Object` unless narrower type information is available.

### 6.2. Array types preserve dimensions after erasure

Given the signatures:

```java
static <T> T[] sameArray(T[] input) {
    return input;
}

// Illustrative declaration:
static <T extends Number> T[] echoNumbers(T[] input) {
    return input;
}
```

The corresponding descriptors are:

```text
sameArray:   ([Ljava/lang/Object;)[Ljava/lang/Object;
echoNumbers: ([Ljava/lang/Number;)[Ljava/lang/Number;
```

The `[` does not disappear; only the **component type** becomes `Object` or the bound `Number`. For `T[][]` with unbounded `T`, erasure is `Object[][]`, whose descriptor starts with `[[`.

At runtime, the **actual** array passed in may be `String[]`, and `sameArray` returns that exact array (without creating a new `Object[]`). Signature erasure does not alter the runtime array type of an already-created object.

### 6.3. Arrays of parameterized types can still be valid in declarations

Compare two situations:

```java
// Field declaration only, no array allocation:
List<String>[] buckets;
```

and:

```java
// Does not compile:
List<String>[] buckets = new List<String>[5];
```

**Declaring** a variable of an array type holding `List<String>` is allowed; **creating** the array with `new List<String>[5]` is not, because the component type is non-reifiable. Some legacy APIs supply values of such a type through unchecked casts; that neither makes the type reifiable nor makes read operations completely safe.

Avoid this pattern:

```java
// Illustrative unsafe workaround; NOT recommended:
@SuppressWarnings("unchecked")
List<String>[] values = (List<String>[]) new List<?>[2];
```

The runtime array only checks whether an element is a `List`, not whether it is a `List<String>`. An `Object[]` alias could store a `List<Integer>` into the array, causing **heap pollution**; when reading elements expecting `String`, the program can throw `ClassCastException`.

## 7. Creating and handling generic arrays safely

### 7.1. Accepting an array provided by the caller

A generic method can **accept, return, or copy** a `T[]` array without invoking `new T[...]` itself:

```java
static <T> T[] duplicate(T[] input) {
    return input.clone();
}
```

Calling `clone()` on an array preserves the runtime component type of the original array. If `input` is `String[]`, the returned array is also `String[]`. This copy is a *shallow copy*: if elements are mutable objects, they are still shared across both arrays.

### 7.2. Letting the caller allocate via a constructor reference

When you need to create a new array with the right component type, pass a factory:

```java
import java.util.function.IntFunction;

static <T> T[] createArray(int length, IntFunction<T[]> factory) {
    if (length < 0) {
        throw new IllegalArgumentException("length must be >= 0");
    }
    return factory.apply(length);
}

// Inside a method:
String[] names = createArray(3, String[]::new);
Integer[] ages = createArray(2, Integer[]::new);
```

The method makes no assumption about what the runtime class of `T` is; the factory supplies the real array. Check the factory contract in public APIs if you need to guarantee the length is not altered.

Another option is using `java.lang.reflect.Array.newInstance(componentClass, length)` and casting to `T[]`, though Java cannot check a cast to a type variable at runtime, typically requiring an unchecked cast inside a carefully encapsulated and tested helper. In modern APIs, an `IntFunction<T[]>` factory or `Collection.toArray(T[]::new)` is usually clearer.

### 7.3. Using `List<T>` when an array is not truly needed

If data needs dynamic sizing and the API does not require an array, `List<T>` is an easy choice:

```java
List<String> names = new ArrayList<>();
names.add("Java");
names.add("Generics");
String first = names.get(0);
```

When an array is genuinely needed to call another API:

```java
String[] array = names.toArray(String[]::new); // Java 11+
```

Creating the array at the usage boundary preserves compile-time type checking of `List<T>` while providing the exact runtime component type of `String[]`.

### 7.4. Generic varargs and `@SafeVarargs`

Varargs are actually passed as an **array**. A declaration like:

```java
static <T> void inspect(List<T>... groups) {
    // ...
}
```

involves an array with a non-reifiable component type. The compiler may warn about *possible heap pollution* at the declaration or *unchecked generic array creation* at call sites. An example method designed solely to **read the varargs array and copy data**:

```java
import java.util.ArrayList;
import java.util.List;

@SafeVarargs
static <T> List<T> flatten(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

`@SafeVarargs` is a promise by the **method author** that the method body performs no unsafe operations on the varargs array. The annotation does not prove correctness by itself, does not eliminate erasure, and does not "turn" a generic array into a reifiable array. In Java 17, it can only be applied to eligible methods such as `static`, `final`, or `private` instance methods (and constructors); do not place it carelessly on overridable instance methods.

In particular, never expose the varargs array to callers, write elements of a mismatched type into it, or pass it to another method that could cause heap pollution without fully controlling the contract. If API users see unchecked warnings, inspect **how the method actually handles the underlying array** before applying `@SafeVarargs`.

## 8. Standalone example: running and observing erasure with Java 17

The following example verifies the main forms: unbounded/bounded type variables, `T[]` arrays, `List<?>[]` arrays, bridge-generating overrides, and the Reflection API.

Create the file **`ErasureSignatureDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class ErasureSignatureDemo {
    static final class Box<T extends Number> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <T> T identity(T value) {
        return value;
    }

    static <T extends Number & Comparable<T>> T greater(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <T> T[] sameArray(T[] input) {
        return input;
    }

    static List<?>[] wildcardArray() {
        return new List<?>[] { List.of("Java"), List.of(17) };
    }

    static class Parent<T> {
        T value() {
            return null;
        }
    }

    static final class Child extends Parent<String> {
        @Override
        String value() {
            return "child";
        }
    }

    public static void main(String[] args) throws Exception {
        Box<Integer> box = new Box<>(7);
        String[] values = {"a", "b"};

        System.out.println(identity("ok"));
        System.out.println(greater(4, 9));
        System.out.println(box.get());
        System.out.println(Arrays.toString(sameArray(values)));
        System.out.println(wildcardArray()[0].get(0));
        System.out.println(new Child().value());

        Method identity = ErasureSignatureDemo.class.getDeclaredMethod(
                "identity", Object.class);
        Method greater = ErasureSignatureDemo.class.getDeclaredMethod(
                "greater", Number.class, Number.class);
        Method sameArray = ErasureSignatureDemo.class.getDeclaredMethod(
                "sameArray", Object[].class);
        Method bridge = Arrays.stream(Child.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("identity: "
                + identity.getReturnType().getSimpleName()
                + " / " + identity.getGenericReturnType().getTypeName());
        System.out.println("greater: "
                + greater.getReturnType().getSimpleName()
                + " / " + greater.getGenericReturnType().getTypeName());
        System.out.println("sameArray: "
                + sameArray.getReturnType().getTypeName()
                + " / " + sameArray.getGenericReturnType().getTypeName());
        System.out.println("bridge: " + bridge.getName()
                + " -> " + bridge.getReturnType().getSimpleName());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 ErasureSignatureDemo.java
java ErasureSignatureDemo
```

Exact stdout:

```text
ok
9
7
[a, b]
Java
child
identity: Object / T
greater: Number / T
sameArray: java.lang.Object[] / T[]
bridge: value -> Object
```

Explaining the final lines:

- `getReturnType()` sees the **raw erased type**: `Object`, `Number`, `Object[]`.
- `getGenericReturnType()` reads the **generic declaration**, because the class file contains the corresponding `Signature` metadata: `T`, `T`, `T[]`.
- `Child` has a bridge method (`isBridge() == true`) returning `Object` to match the erased signature of `Parent.value()`.
- None of the lines prove that a `List<String>` instance holds the `String` argument as a runtime field of the list object itself.

### 8.1. Inspecting real descriptors with `javap`

After `javac`, run:

```bash
javap -p -s ErasureSignatureDemo
javap -p -s 'ErasureSignatureDemo$Box'
javap -p -s 'ErasureSignatureDemo$Child'
```

Note the single quotes around nested class names in Unix shells to prevent `$` from expanding as an environment variable. In PowerShell, single-quoted strings like the above also work.

Key parts of the output:

```text
static <T> T identity(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;

static <T extends java.lang.Number & java.lang.Comparable<T>> T greater(T, T);
  descriptor: (Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/Number;

static <T> T[] sameArray(T[]);
  descriptor: ([Ljava/lang/Object;)[Ljava/lang/Object;
```

For `ErasureSignatureDemo$Box`, notable members include:

```text
private final T value;
  descriptor: Ljava/lang/Number;

T get();
  descriptor: ()Ljava/lang/Number;
```

For `ErasureSignatureDemo$Child`, you will see **two** `value()` methods at the class-file level, with descriptors:

```text
()Ljava/lang/String;
()Ljava/lang/Object;
```

Also run:

```bash
javap -v -p 'ErasureSignatureDemo$Child'
```

to view the `ACC_BRIDGE`/`ACC_SYNTHETIC` flags of the forwarding method. `javap -s` shows you both the human-readable generic signature and the JVM descriptor; therefore, check the exact `descriptor` line when evaluating erasure.

### 8.2. Why does `getDeclaredMethod` use `Object.class` and `Number.class`?

In the program:

```java
getDeclaredMethod("identity", Object.class)
getDeclaredMethod("greater", Number.class, Number.class)
getDeclaredMethod("sameArray", Object[].class)
```

Reflection takes **runtime parameter types**, meaning the types from the erased descriptor. If you try looking up `identity(String.class)`, you will not find an `identity(String)` overload: the compiler did not generate a separate method for `String`.

Reflection provides `getGenericParameterTypes()` / `getGenericReturnType()` to inspect **generic declarations stored in metadata**, but does not use that metadata to determine the type arguments of every call or the actual elements inside a collection. Do not confuse the presence of the `Signature` attribute with the runtime being able to distinguish `List<String>` from `List<Integer>` on its own.

## 9. Common pitfalls when combining methods and arrays

### Pitfall 1: thinking `T[]` and `Object[]` are identical at every level

Erasure may turn the **signature** `T[]` into `Object[]`, yet you cannot take an arbitrary `Object[]`, unconditionally cast it to `String[]`, and expect it to work. The runtime array still knows its real component type, and a bad cast throws `ClassCastException`:

```java
Object[] objects = new Object[2];
// String[] strings = (String[]) objects; // Cast may compile but fails at runtime
```

Distinguish the **erased method descriptor** from the **actual runtime class of an array** when debugging.

### Pitfall 2: confusing `new List<?>[n]` with `new List<String>[n]`

The first is valid because `List<?>` is reifiable; the second is invalid because `List<String>` is non-reifiable. The `?` here is not a way to "disable all type safety", rather it reflects that there is no concrete promise about each `List`'s element type.

### Pitfall 3: using `@SuppressWarnings("unchecked")` to "fix" erasure

Suppressing only hides the warning; the unchecked cast still exists. Use it only when an API forces interaction with legacy code or runtime reflection and you have a clear invariant proving element types are preserved. For arrays, prefer constructor references, factories, or converting through collections.

### Pitfall 4: choosing overloads or overrides by type argument

After erasure, `List<String>` and `List<Integer>` share the raw type `List`; two methods with the same name and corresponding raw parameters can cause a `name clash`. With generic subclasses, the compiler sometimes **must** generate a bridge even though you did not write that method. Check `javap` before concluding a class contains a "mystery method" added by another library.

### Pitfall 5: believing type erasure removes all generic information

`javap -v` can display the `Signature` attribute; `Method.getGenericReturnType()` can return `TypeVariable`, `ParameterizedType`, or `GenericArrayType`. However, metadata describes the **declaration**, and cannot always tell you the actual element type of each instance at runtime.

### Pitfall 6: ignoring `ArrayStoreException` because compile time allowed the assignment

Arrays have covariance and runtime store checks. For instance, `Object[] alias = new String[1]` is valid, but writing an `Integer` through `alias` throws `ArrayStoreException`. This differs from `ClassCastException` caused by reading wrong generics from a collection after heap pollution; the two error types have different causes.

## 10. Workflow for diagnosing an erasure-related error

When encountering `name clash`, `generic array creation`, `ClassCastException`, `ArrayStoreException`, or confusing overriding behavior:

1. **Write out the full source types** including type variables, type arguments, bounds, and all array dimensions.
2. **Compute erasure**: type variable to its first bound (or `Object`), parameterized type to its raw type, array erases its component type while keeping dimensions.
3. **Compare erased method signatures** to spot colliding overloads; for overrides, compare superclass/subclass descriptors to identify any needed bridge.
4. **Check actual runtime types** when data is an array (`getClass().getComponentType()`) or when unchecked casts exist.
5. **Use `javap -p -s`**, and `javap -v` when needing bridge/`Signature` details; invoke reflection with erased parameter types.
6. **Adjust the API contract in the right place**: rename overloads, unify into one generic method, choose collections or array factories, and avoid raw/unchecked casts.
7. **Compile and test at runtime** with both valid inputs and failure-prone inputs (arrays with different component types, multiple subtypes, subclass overriding).

Quick decision table:

| Situation | Check | Resolution |
| --- | --- | --- |
| `print(List<String>)` clashes with `print(List<Integer>)` | Same descriptor `List` | Rename by purpose or unify into a generic method. |
| `T[] result = new T[n]` | Non-reifiable component `T` | Accept an array factory `IntFunction<T[]>` or an array from the caller. |
| `List<String>[] x = new List<String>[n]` | Non-reifiable parameterized component | Use `List<List<String>>`, or `List<?>[]` if wildcard fits the semantics. |
| Caller needs `String` but `getReturnType()` returns `Object` | Erased descriptor | Check `getGenericReturnType()` and compiler-inserted casts; do not expect reflection to retrieve separate specializations. |
| `Child` has an extra synthetic method returning `Object` | Generic override has a bridge | Check `ACC_BRIDGE` flag, override relationships, and class hierarchy. |
| `String[]` via `Object[]` alias receives `Integer` | Runtime store check | Avoid writing mismatched component types; adjust data structure if heterogeneous types are needed. |

## 11. Self-check questions

**Question 1.** After erasure, what is the descriptor for the method below?

```java
static <T extends Number> T[] echo(T[] input) {
    return input;
}
```

<details>
<summary>Answer</summary>

`([Ljava/lang/Number;)[Ljava/lang/Number;` because `T` is erased to its bound `Number`, while the array type retains one dimension.

</details>

**Question 2.** Why can't you overload `find(List<String>)` and `find(List<Integer>)` in the same class?

<details>
<summary>Answer</summary>

Both parameter lists erase to `List`, so there is no difference in method signature under Java's overloading rules; the compiler reports a `name clash`.

</details>

**Question 3.** Why is `new List<?>[3]` valid whereas `new List<String>[3]` is invalid?

<details>
<summary>Answer</summary>

Arrays require a reifiable component type; `List<?>` is reifiable while `List<String>` is not. The JVM runtime component check cannot verify the `String` type argument on its own.

</details>

**Question 4.** A subclass overrides `T get()` of a generic superclass with `String get()`. Why can the subclass bytecode contain `Object get()` as well?

<details>
<summary>Answer</summary>

Unbounded `T` in the superclass erases to `Object`; the compiler generates a synthetic bridge forwarding to `String get()` to preserve polymorphic dispatch through superclass-typed references.

</details>

**Question 5.** `getGenericReturnType()` on `identity` displays `T`. Does that prove each call `identity(5)` generates a new bytecode method for `Integer`?

<details>
<summary>Answer</summary>

No. `T` is metadata about the generic **declaration** of one method, while the actual descriptor uses `Object`. The compiler checks type inference for each call; it does not generate a new specialization of `identity` for each parameter type.

</details>

## 12. Key takeaways

To read erasure accurately, separate **three layers**: the generic types the Java compiler checks in source code, the **JVM descriptor** after type erasure, and the **actual runtime type of the object/array**. In method signatures, `T` becomes `Object` or the first bound; `List<String>` and `List<Integer>` both become `List`; generic overrides may require bridges. In array types, `T[]` erases to `Object[]` or an array of the bound, yet the JVM still enforces the component type of created arrays. This is the foundation for avoiding colliding overloads, dangerous unchecked casts, and invalid generic array creations.