# `List<Integer>`, `Collection<Integer>`, and Inheritance-Declared Relationships

## Objectives

After this lesson, you should be able to distinguish two independent ideas: **inheritance relationships between declared types** and **relationships between type arguments in generics**. From there, you can explain why a `List<Integer>` can be assigned to `Collection<Integer>`, yet cannot be assigned to `Collection<Number>`, and know when to use wildcards.

## 1. Type Relationships Begin with API Declarations

In `java.util`, the interfaces declare relationships as follows (abbreviated only to show inheritance):

```java
interface Iterable<T> {
    // ...
}

interface Collection<E> extends Iterable<E> {
    // ...
}

interface List<E> extends Collection<E> {
    // ...
}
```

This is an **illustrative declaration diagram**, not complete source code meant to replace the JDK interfaces. With the same type parameter `T`, the relationship chain is:

```text
List<T>  <:  Collection<T>  <:  Iterable<T>
  ^
  |
ArrayList<T> (implements List<T>)
```

The notation `A <: B` means `A` is a subtype of `B`. `ArrayList<E>` implements `List<E>`, and `List<E>` extends `Collection<E>`. Substituting `E = Integer` consistently gives:

- `ArrayList<Integer>` is a subtype of `List<Integer>`.
- `List<Integer>` is a subtype of `Collection<Integer>`.
- `Collection<Integer>` is a subtype of `Iterable<Integer>`.

Therefore, **upcasting assignments are valid**:

```java
List<Integer> list = new ArrayList<>();
Collection<Integer> collection = list;
Iterable<Integer> iterable = collection;
```

Java checks this relationship at **compile time** via `extends`/`implements` declarations. The same `ArrayList` object is referenced through different static types; no list copy is created upon assignment.

Changing the reference type changes **which methods can be called through the variable**: `collection.add(1)` and `collection.size()` exist on `Collection`, while `collection.get(0)` does not compile because `get(int)` belongs to `List`. The actual object is still a list. In the reverse direction, a `Collection<Integer>` cannot automatically be assigned to `List<Integer>`, because an arbitrary collection could also be a `Set<Integer>`.

## 2. Standalone Runnable Java 17+ Example

Save the code as **`GenericInheritanceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class GenericInheritanceDemo {
    private static void appendForty(Collection<? super Integer> target) {
        target.add(40);
    }

    public static void main(String[] args) {
        List<Integer> list = new ArrayList<>(List.of(10, 20));

        Collection<Integer> collection = list; // valid upcast
        Iterable<Integer> iterable = collection;

        collection.add(30); // mutates the exact object that list references
        System.out.println(list);
        System.out.println(iterable.iterator().next());

        Collection<? extends Number> readableNumbers = list;
        Number first = readableNumbers.iterator().next();
        System.out.println(first);

        Collection<Number> destination = new ArrayList<>();
        appendForty(destination);
        System.out.println(destination);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac GenericInheritanceDemo.java
java GenericInheritanceDemo
```

Exact output:

```text
[10, 20, 30]
10
10
[40]
```

Explanation: `collection` and `list` point to the same `ArrayList<Integer>`, so adding `30` via `collection` also appears when printing `list`. The `iterable` variable exposes only the `Iterable` API, yet still iterates over that exact same object. The `? extends Number` wildcard allows reading elements as `Number`; the `? super Integer` wildcard allows the method to add `Integer` into a collection whose element type is `Integer` or one of its supertypes.

**Note on mutability:** the example uses `new ArrayList<>(List.of(...))` to create a modifiable list. If the reference pointed directly to `List.of(10, 20)`, calling `add` would throw `UnsupportedOperationException`, even though the `List<Integer> → Collection<Integer>` assignment is completely valid. Subtyping does not guarantee mutability.

## 3. Invariant Generics: Changing Type Arguments Does Not Create New Inheritance Relationships

`Integer` extends `Number`, yet **`List<Integer>` is not a subtype of `List<Number>`** and **`Collection<Integer>` is not a subtype of `Collection<Number>`**. This is the **invariance** property of Java generic types.

The following lines intentionally illustrate **compile errors**; do not add them to the runnable program above:

```java
List<Integer> integers = new ArrayList<>();

// Does not compile:
Collection<Number> wrong1 = integers;
List<Number> wrong2 = integers;
Collection<Object> wrong3 = integers;
```

Why must this be forbidden? Suppose `Collection<Number> wrong1 = integers` were accepted; then `wrong1.add(3.14)` would be valid under the static type `Collection<Number>`, yet would insert a `Double` into a `List<Integer>`. Java prevents that risk at compile time.

Clearly separate the two inferences:

1. **Changing the declared type along the inheritance chain while keeping the type argument unchanged:** `List<Integer> → Collection<Integer>`: valid.
2. **Changing the type argument `Integer` to `Number` in a concrete generic type:** `Collection<Integer> → Collection<Number>`: invalid.

Having `Integer <: Number` does **not** automatically imply `G<Integer> <: G<Number>` where `G` is `List`, `Collection`, or another invariant generic type.

## 4. Wildcards Express Broader Type Relationships

When a method only needs to read elements as `Number` or only needs to accept `Integer` values, you can declare a wildcard instead of requiring a fixed `Collection<Number>`.

### `? extends Number`: Read Source

```java
static void printFirst(Collection<? extends Number> values) {
    Number first = values.iterator().next();
    System.out.println(first);
}
```

This method accepts `List<Integer>`, `List<Double>`, `Collection<Number>`, and collections whose element type is a subtype of `Number`. Elements can be read out as `Number`. However, you cannot call `values.add(42)` because the compiler does not know whether the actual element type is `Integer`, `Double`, or some other subtype. Do not mistake `Collection<? extends Number>` for `Collection<Number>`: they carry different constraints.

### `? super Integer`: Write Destination

```java
static void addAnswer(Collection<? super Integer> values) {
    values.add(42);
}
```

The method accepts `Collection<Integer>`, `Collection<Number>`, and `Collection<Object>`, since all of them are capable of holding an `Integer`. Conversely, when retrieving an element from `Collection<? super Integer>`, the compiler can only guarantee `Object`, because the actual element type could be `Integer`, `Number`, or `Object`.

Recall the **PECS** (*Producer Extends, Consumer Super*) rule: a source supplying data to read generally uses `? extends`; a destination receiving data to write generally uses `? super`. If you need to both read and write exact `Integer` values, use `Collection<Integer>`.

Distinguish further: `Collection<? extends Number>` can **reference** a `List<Integer>`, but that does not make a `Collection<Number>` variable accept a `List<Integer>`. A wildcard is a different target type with different operational limits.

## 5. Assignment Check Table

| Source (expression) | Target variable type | Result | Reason |
| --- | --- | --- | --- |
| `ArrayList<Integer>` | `List<Integer>` | Valid | `ArrayList<E> implements List<E>` |
| `List<Integer>` | `Collection<Integer>` | Valid | `List<E> extends Collection<E>` |
| `Collection<Integer>` | `Iterable<Integer>` | Valid | `Collection<E> extends Iterable<E>` |
| `Collection<Integer>` | `List<Integer>` | Not automatic | Collection could be a Set |
| `List<Integer>` | `Collection<Number>` | Invalid | Invariant generic type argument |
| `List<Integer>` | `List<Number>` | Invalid | Invariant generic type argument |
| `List<Integer>` | `Collection<? extends Number>` | Valid | Elements readable as Number |
| `List<Integer>` | `Collection<? super Integer>` | Valid | Can add Integer |
| `List<Number>` | `Collection<? super Integer>` | Valid | Number is a supertype of Integer |

The rows describe **compile-time assignment type checking**, not a guarantee that every received object supports modification operations. Whether `add` succeeds also depends on the concrete implementation.

## 6. Choosing Method Parameter Types by Need

A method that only needs to iterate, count, or check membership should not demand `List<Integer>` when `Collection<Integer>` suffices; that allows it to accept both `ArrayList` and `HashSet` containing `Integer`:

```java
static boolean containsForty(Collection<Integer> values) {
    return values.contains(40);
}
```

If the method only reads numbers without depending on the exact numeric type, widen the signature to `Collection<? extends Number>`. If it needs indexing or ordered access via `get(index)`, `List<Integer>` accurately reflects the API requirement. If the method only needs iteration, `Iterable<Integer>` is even more general.

Example showing the difference between upcasting and downcasting (error lines are commented out):

```java
List<Integer> list = new ArrayList<>(List.of(1, 2));
Collection<Integer> view = list; // valid
// List<Integer> notGuaranteed = view; // does not compile

// Only downcast when you know the object is actually a List:
if (view instanceof List<?>) {
    List<Integer> restored = (List<Integer>) view;
    System.out.println(restored.get(0)); // 1
}
```

In the last example, `list` itself initialized `view`, so the actual object is a `List`. Never cast an arbitrary `Collection` to `List`; with a `HashSet`, such a cast will fail at runtime. Do not use casts to bypass the invariance of generic type arguments.

## 7. Common Misconceptions

- **"`Integer extends Number`, so `Collection<Integer> extends Collection<Number>`."** False: inheritance of type arguments is not automatically propagated to invariant generic types.
- **"`List<Integer>` and `Collection<Integer>` are two different collections after assignment."** False: upcasting only changes the static type of the reference; both variables can point to the same object.
- **"`Collection<Integer>` can call every method of `List<Integer>`."** False: method invocation depends on the reference's compile-time type; `Collection` does not have `get(index)`.
- **"Because `List<Integer>` can be assigned to `Collection<Integer>`, elements can definitely be added."** False: unmodifiable implementations can still throw `UnsupportedOperationException`.
- **"Just use `Collection<Number>` to accept all numeric lists."** False: use `Collection<? extends Number>` if reading multiple numeric types, or `Collection<? super Integer>` if needing to add `Integer`.

## Conclusion to Remember

The **`List<E> extends Collection<E>`** relationship allows `List<Integer> → Collection<Integer>` because it **keeps `E = Integer` unchanged** along the inheritance hierarchy. **Invariance**, by contrast, prevents `List<Integer> → Collection<Number>` even though `Integer extends Number`. When an API needs to accept different element types, wildcards `? extends` or `? super` accurately express read/write capabilities and help the compiler preserve type safety.