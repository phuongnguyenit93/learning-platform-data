# Using Wildcards for Flexible Inputs with PECS in Java Generics API Design

## 1. The problem: an API accepts `List<Dog>`? No, it rejects `List<Dog>` when expecting `List<Animal>`

You are building an API that takes a list of animals:

```java
class Animal {
    String name() {
        return "animal";
    }
}

class Dog extends Animal {
}

class Cat extends Animal {
}
```

A first version:

```java
static void printNames(List<Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
```

But the caller has a variable:

```java
List<Dog> dogs = new ArrayList<>();
```

and hits an error:

```java
// Does not compile:
// printNames(dogs);
```

**Cause:** Java Generics are *invariant*: even though `Dog extends Animal`, `List<Dog>` is not a subtype of `List<Animal>`.

If the method only **reads** the list, forcing callers to convert/copy into `List<Animal>` is unnecessary. A more flexible signature:

```java
static void printNames(List<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.name());
    }
}
```

Now the method can accept `List<Animal>`, `List<Dog>`, `List<Cat>`, and lists of other appropriate subtypes, while still reading each element as `Animal`.

If the method is responsible for **adding `Dog`** into a collection, the wildcard direction must flip:

```java
static void addDefaultDog(List<? super Dog> target) {
    target.add(new Dog());
}
```

A `List<Dog>`, `List<Animal>`, or `List<Object>` can all be a destination receiving `Dog`.

The rule to remember is **PECS — Producer Extends, Consumer Super**:

- **Producer `? extends T`**: a source supplying objects that we can read as `T`.
- **Consumer `? super T`**: a destination consuming/receiving `T` objects that we can write into.
- If neither reading nor writing a specific type is needed, `<?>` may suffice.
- If both reading and writing under the same determined type are required, a **type parameter `<T>`** or a concrete type is usually better than a wildcard.

This lesson focuses on choosing **flexible yet safe API method signatures**, rather than blindly replacing `List<T>` with wildcards everywhere. Valid and invalid examples have been verified with Java 17.

## 2. Distinguishing subtype relationships of values vs. generic containers

A `Dog` is an `Animal`:

```java
Dog dog = new Dog();
Animal animal = dog;
```

However:

```java
List<Dog> dogs = new ArrayList<>();

// Invalid:
// List<Animal> animals = dogs;
```

This is **invariance** of parameterized types. The same rule applies to `Collection<Dog>`, `Set<Dog>`, and many other generic types.

### 2.1. Why does Java forbid assigning `List<Dog>` to `List<Animal>`?

Suppose it were allowed:

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = dogs; // Suppose this were allowed.
animals.add(new Cat());      // Cat is also an Animal.
Dog value = dogs.get(0);     // Yet the slot could hold a Cat!
```

If Java allowed it, the code could break the `List<Dog>` contract: the list now holds a `Cat` while another caller trusts every element is a `Dog`.

Java blocks this at compile time instead of waiting until read time.

### 2.2. Java arrays differ from generic collections

Reference arrays in Java are *covariant*:

```java
Dog[] dogs = new Dog[1];
Animal[] animals = dogs;

// Compiles, but throws ArrayStoreException:
// animals[0] = new Cat();
```

The JVM has a runtime component type to block storing a `Cat` into an actual `Dog[]` array.

Generic `List<Dog>` generally has no separate runtime class `List<Dog>` for the JVM to perform a store check on the type argument. Hence generic invariance prevents type-safety risks right at the source.

**Do not extrapolate from arrays to Generics.** `Animal[]` and `List<Animal>` have different subtyping rules.

### 2.3. Wildcards open flexibility while also limiting operations

A `List<? extends Animal>` parameter accepts many subtype lists of `Animal`; in return, the called method cannot arbitrarily add any `Dog` or `Cat` into that list.

A `List<? super Dog>` parameter accepts many compatible destinations for adding `Dog`; in return, when reading elements, the method cannot assume every returned object is always a `Dog`.

This is not accidental inconvenience, but **the exact level of type guarantee the signature can provide**.

## 3. Producer Extends: reading data with `? extends T`

Consider the API:

```java
static String firstName(List<? extends Animal> source) {
    return source.get(0).name();
}
```

At the call site:

```java
List<Dog> dogs = List.of(new Dog());
List<Cat> cats = List.of(new Cat());

String fromDogs = firstName(dogs);
String fromCats = firstName(cats);
```

Inside the method:

- `source` could actually be `List<Dog>`, `List<Cat>`, or `List<Animal>`.
- Any element read can be used as `Animal`.
- The method has no right to know **the specific element type hidden behind the wildcard**.

### 3.1. Reading as the bound is safe

```java
Animal first = source.get(0);
```

If the actual element type is `Dog`, `Dog` is still an `Animal`. If the actual type is `Cat`, `Cat` is also an `Animal`. Reading as `Animal` upholds the common contract.

Conversely:

```java
// Does not compile:
// Dog first = source.get(0);
```

If the actual source is `List<Cat>`, a `Dog` variable would be wrong. The compiler forbids such an assertion.

### 3.2. Why can't `new Dog()` be added to a producer?

```java
static void invalid(List<? extends Animal> source) {
    // Does not compile:
    // source.add(new Dog());
}
```

Suppose the caller passed `List<Cat>`. Adding a `Dog` to it would be wrong. The compiler models `?` with an unknown **capture type** upper-bounded by `Animal`; it cannot prove `Dog` is valid for every possible capture type.

This is the **Producer Extends** principle: a source declared to **supply** elements should not be used to insert elements of an arbitrary subtype back in.

### 3.3. `null` is a special case

From the type system's perspective, `source.add(null)` may be accepted because `null` is assignable to any compatible reference type. However:

- The list may forbid `null`.
- The list may be immutable/unmodifiable.
- Adding `null` rarely matches the purpose of a "producer".

Do not turn this syntactic exception into usage advice. **PECS governs non-null values and normal type contracts**, whereas mutability and null policies are separate rules.

### 3.4. `? extends` does not mean the `List` is physically read-only

A `List<? extends Animal>` can reference a mutable `ArrayList<Dog>`. The wildcard only restricts **type-safe operations through that reference**; it does not make the object immutable or thread-safe.

The method can still call other operations such as `clear()` if the collection allows it, though that is usually unexpected behavior for a source API. When designing a read-only API, both use the right wildcard direction and commit by contract not to mutate the source.

## 4. Consumer Super: writing values with `? super T`

Suppose you have a new `Dog` and need to put it into a destination:

```java
static void addDefaultDog(List<? super Dog> target) {
    target.add(new Dog());
}
```

Valid destination kinds:

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = new ArrayList<>();
List<Object> objects = new ArrayList<>();
```

All three can be passed into the method above:

```java
addDefaultDog(dogs);
addDefaultDog(animals);
addDefaultDog(objects);
```

Because all of those lists can hold a `Dog` under their declared type contracts.

### 4.1. `? super Dog` is an unknown type no narrower than Dog

In `List<? super Dog>`, the actual type argument could be `Dog`, `Animal`, `Object`, or another compatible supertype of `Dog`. Regardless of which one it is, writing `Dog` is safe:

```java
target.add(new Dog());
```

Adding a subtype of `Dog` (if `Dog` is not `final`) is also safe by subtyping.

But adding a general `Animal` or a `Cat` is not:

```java
// Unsafe and does not compile:
// target.add(new Animal());
// target.add(new Cat());
```

If the actual destination is `List<Dog>`, `Animal`/`Cat` does not satisfy the list's requirement.

### 4.2. Reading from `? super Dog` is only guaranteed to be Object

```java
Object value = target.get(0);
```

is allowed. However:

```java
// Does not compile:
// Dog value = target.get(0);
```

because the actual destination could be `List<Object>` and already contain a `String`, `Integer`, or any other `Object`.

**Consumer Super:** the method author has the right to **put `Dog` in**, but cannot assume **every existing element** is a `Dog`.

### 4.3. Using super for writable outputs

The destination parameter can also use a more general interface:

```java
static void addDog(Collection<? super Dog> target) {
    target.add(new Dog());
}
```

If only `add` is needed, accepting `Collection` is more flexible than accepting `List`. Callers can supply `ArrayList<Animal>`, `HashSet<Animal>`, or other `Collection` implementations with a suitable `add`.

**Additional design principle:** accept the **narrowest interface in capabilities that the method actually needs**, rather than always reaching for `List` out of habit. If indexed access is needed, `List` is appropriate; if only adding, `Collection` usually suffices.

## 5. Read and write permissions table to remember

Consider `Dog extends Animal`.

| Reference type | Safely read element as | Non-null value provably safe to write |
| --- | --- | --- |
| `List<Dog>` | `Dog` | `Dog` and subtypes of `Dog` |
| `List<Animal>` | `Animal` | `Animal` and subtypes of `Animal` |
| `List<? extends Animal>` | `Animal` | Cannot arbitrarily write `Dog`/`Animal` |
| `List<? super Dog>` | `Object` | `Dog` and subtypes of `Dog` |
| `List<?>` | `Object` | Cannot arbitrarily write elements |
| `List<Object>` | `Object` | Any `Object` |

`List<? extends Animal>` is not synonymous with `List<Animal>`. It can refer to different `Dog`/`Cat` lists.

`List<? super Dog>` is likewise not synonymous with `List<Dog>`. It can refer to an `Animal` or `Object` list.

### 5.1. Which limits come from Generics, and which from the runtime collection?

The compiler may allow calling `add`, yet the runtime object may be unmodifiable:

```java
List<Dog> fixed = List.of(new Dog());

// Valid generic syntax, but runtime throws
// UnsupportedOperationException if called:
fixed.add(new Dog());
```

Similarly with `Collections.unmodifiableList` or collection implementations with specific restrictions. PECS **does not grant physical mutation permission**; it checks type compatibility.

## 6. Both directions on the same method: copying from producer to consumer

This is the canonical PECS pattern:

```java
static <T> void appendAll(
        List<? extends T> source,
        Collection<? super T> target) {

    for (T item : source) {
        target.add(item);
    }
}
```

`source` is a **producer** of `T`: we read each element as `T`.

`target` is a **consumer** of `T`: we add each `T` element into it.

`<T>` links both sides so the compiler can verify that every element taken from `source` is valid for `target`.

### 6.1. Caller passes List<Dog> and List<Animal>

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = new ArrayList<>();

appendAll(dogs, animals);
```

The compiler can infer an appropriate type variable `T` given the subtype relationship between `Dog` and `Animal`. No need to copy or cast `List<Dog>` to `List<Animal>`.

### 6.2. Caller can also pass List<Dog> and List<Object>

```java
List<Object> objects = new ArrayList<>();
appendAll(dogs, objects);
```

The contract permits this because `Object` can also receive `Dog`. This shows how wildcards preserve flexibility on **both** sides.

### 6.3. Why not write both parameters as `List<T>`?

```java
static <T> void rigid(List<T> source, List<T> target) {
    target.addAll(source);
}
```

This signature ties both Lists to **the exact same type argument `T`**. When the caller has `List<Dog>` and `List<Animal>`, inferring a single shared `T` is blocked by invariance.

The PECS signature:

```java
static <T> void flexible(
        List<? extends T> source,
        List<? super T> target) {
    target.addAll(source);
}
```

clearly expresses the producer/consumer relationship, making it more flexible and safe.

### 6.4. Note on naming `append` vs. `copy`

`appendAll` in the example **adds** elements to the end of the `Collection`. It can increase the target's size.

In the JDK, `Collections.copy` is a different API: it **overwrites** existing positions in the destination list without growing the list to append. Do not confuse the two semantics when reading code.

### 6.5. Side effects and aliasing must be part of the contract

If `source` and `target` point to the same mutable collection, a `for-each` loop iterating while adding can lead to `ConcurrentModificationException` or unexpected behavior. A PECS signature only guarantees types; it does not resolve aliasing.

When designing an API, decide whether `source == target` is allowed. If you want to support it, you can snapshot the source first or use an appropriate algorithm, while considering memory cost.

## 7. JDK example: `Collections.copy` uses PECS

Java 17 declares the equivalent method:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Here:

- `src` (*source*) is the producer, so `? extends T`.
- `dest` (*destination*) is the consumer, so `? super T`.

Example:

```java
List<Integer> numbers =
        new ArrayList<>(List.of(3, 7));

List<Number> target =
        new ArrayList<>(List.of(0, 0, 0));

Collections.copy(target, numbers);
System.out.println(target); // [3, 7, 0]
```

`Collections.copy` replaces destination elements at corresponding indices. **Condition:** the destination list must have a size at least as large as the source list. `new ArrayList<>(capacity)` only sets capacity—it **does not pre-populate elements**—so it cannot serve as a sufficiently sized destination for `Collections.copy`.

### 7.1. When you want to append instead of overwrite

Use:

```java
target.addAll(numbers);
```

or a clearly named `appendAll` API.

The instance method signature on `Collection<E>`:

```java
boolean addAll(Collection<? extends E> collection)
```

uses an `extends` wildcard on the **source argument**. The current collection acts as the consumer of `E`; the passed-in collection supplies elements that are `E` or subtypes.

### 7.2. Why does `Collections.copy` have type parameter T?

`T` links **source** and **destination**. If there were only two unlinked independent wildcards such as:

```java
// Does not sufficiently express the relationship between the two types:
// void copy(List<?> target, List<?> source)
```

then the compiler could not safely take an object of unknown type from `source` and write it into a `target` of unknown type.

**Key point:** PECS typically combines wildcards **with a `<T>` linking two parameters**, rather than eliminating the type parameter.

## 8. Generic method to merge multiple sources with different subtypes

Suppose you want to combine a `Dog` list and a `Cat` list into a new `Animal` list:

```java
static <T> List<T> concat(
        List<? extends T> left,
        List<? extends T> right) {

    List<T> result = new ArrayList<>(
            left.size() + right.size());
    result.addAll(left);
    result.addAll(right);
    return result;
}
```

Call:

```java
List<Dog> dogs = List.of(new Dog());
List<Cat> cats = List.of(new Cat());

List<Animal> combined = concat(dogs, cats);
```

Both sources are producers of subtypes compatible with `T`; `T` is inferred from arguments and target type to produce a `List<Animal>` result.

### 8.1. Why should the result be `List<T>`?

The method **creates** a new list that it owns. It knows it only added values compatible with `T`, so it can return `List<T>`; callers use the result under a clear contract.

Returning `List<? extends T>` here can make it hard for callers to add `T` elements to the result without bringing corresponding benefits. **Wildcards are generally useful at input parameter positions**; overly wildcarded return types can make APIs awkward to use.

### 8.2. Avoid obscuring the type relationship after merging

```java
List<? extends Animal> combined = concat(dogs, cats);
```

can be used if only reading, yet the caller cannot subsequently add a `Dog` through the `? extends Animal` reference. If the method genuinely creates a new `List<Animal>` for callers to manipulate, declaring:

```java
List<Animal> combined = concat(dogs, cats);
```

usually conveys intent better.

### 8.3. Check mutability/immutability

`new ArrayList<>()` creates a mutable result. If the API promises an immutable snapshot, you can return `List.copyOf(result)` when data contains no nulls and the contract matches. `List.copyOf` has its own restrictions such as rejecting nulls; "switching to unmodifiable" should not be done without considering business requirements.

## 9. PECS in `Function`, `Comparator`, and other APIs

PECS does not apply only to lists. It also appears in functional interfaces.

### 9.1. `Function<? super T, ? extends R>`

Consider a generic transform:

```java
static <T, R> void transformAll(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper,
        Collection<? super R> target) {

    for (T item : source) {
        target.add(mapper.apply(item));
    }
}
```

Each component has a role:

- `Iterable<? extends T> source`: source supplying `T`.
- `Function<? super T, ? extends R> mapper`: **consumes** a `T`, **produces** an `R`.
- `Collection<? super R> target`: destination receiving `R`.

This is PECS seen across multiple layers of a single call.

Example:

```java
Function<Animal, String> names = Animal::name;

List<Dog> dogs = new ArrayList<>();
List<String> result = new ArrayList<>();

transformAll(dogs, names, result);
```

Even though `mapper` takes `Animal`, it handles `Dog` because `Dog` is a subtype of `Animal`. `? super T` on `Function`'s input expresses this exact flexibility.

### 9.2. Why is Function's result `? extends R`?

If a mapper returns a subtype of `R`, callers can still use that value as `R`. The `extends` wildcard on the **output** expresses producer behavior.

A conceptual example: a `Function<Animal, Dog>` produces `Dog`; a site expecting `Function<? super Animal, ? extends Animal>` can accept it when constraints match. `R` serves as the common type of the resulting data.

Do not flip it to `Function<? extends T, ? super R>` when you want to consume `T` and return `R`: an input of `? extends T` may be too narrow to accept every `T`; an output of `? super R` could return a type wider than `R`, losing the guarantee that the result is `R`.

### 9.3. `Comparator<? super T>`

`List<E>.sort` has the signature:

```java
void sort(Comparator<? super E> comparator)
```

With `List<Dog>`, you can use a `Comparator<Animal>` because the comparator accepts `Dog`s as `Animal`s.

```java
Comparator<Animal> byName =
        Comparator.comparing(Animal::name);

List<Dog> dogs = new ArrayList<>();
dogs.sort(byName);
```

A `Comparator` is a **consumer of the objects to compare**: it takes two `E`s and computes ordering, so `? super E` is the sensible direction.

### 9.4. `Comparable<? super T>` in standard APIs

The JDK also uses the pattern:

```java
<T extends Comparable<? super T>>
```

in APIs like `Collections.max(Collection<? extends T>)`. This lets a `T` be compared through `Comparable` of `T` **or of an appropriate supertype**.

This example combines:

- A bound on **type variable T**.
- A `? super T` wildcard on the interface consuming objects for comparison.
- `Collection<? extends T>` as the source of values from which to pick the maximum element.

You do not need to memorize every JDK signature, but reading this API helps you recognize PECS appearing in places beyond `List`.

## 10. `List<?>` when the element type does not need to be known

An API that only counts elements:

```java
static int count(List<?> items) {
    return items.size();
}
```

does not need `<T>` because the method does not link the element type to the return value or another parameter.

`List<?>` corresponds to "a list of **some unknown kind**", not "a list of Object":

```java
List<String> words = List.of("Java");
List<?> any = words; // Valid.

// Invalid:
// List<Object> objects = words;
```

### 10.1. Reading through `List<?>`

```java
Object first = any.get(0);
```

is valid. However, the compiler does not promise `String` from the static type `List<?>` alone.

### 10.2. Do not add arbitrarily to `List<?>`

```java
// Does not compile:
// any.add("new");
```

Because the true element type could be `Integer`, `Dog`, `Cat`, or something else. The `?` has no specific bound proving `String` can be added.

### 10.3. When is `<T>` no better than `<?>`?

A signature:

```java
static <T> int countGeneric(List<T> items) {
    return items.size();
}
```

is still valid, yet `T` contributes no new relationship information. When a method only inspects size or prints objects as `Object`, `List<?>` is usually simpler and more accurate.

**Design tip:** only declare a type parameter when **the name `T` needs to link at least two meaningful positions**, or serve a bound/return type/constraint. This is a heuristic, not a mandatory Java syntax rule.

## 11. Wildcard capture: when the compiler names the `?`

Some safe operations on *the same list* are still hard to express directly with `List<?>`.

For instance, swapping two elements of a list while preserving their real type:

```java
static void swapFirstTwo(List<?> items) {
    swapCaptured(items);
}

private static <T> void swapCaptured(List<T> items) {
    T first = items.get(0);
    items.set(0, items.get(1));
    items.set(1, first);
}
```

`swapCaptured` uses a type parameter `T` to express that both elements are read/written **on the same list with the same captured type**.

### 11.1. Why can't arbitrary objects be added directly?

The helper only takes values already in the list and writes them back into the same list. It **does not insert an external `Dog` into a `List<?>` that might actually be `List<Cat>`**.

This is where wildcard capture helps express a safe operation when bare `?` gives the compiler no way to connect "same type" between two read/write statements.

### 11.2. Wildcard capture does not bypass subtype limits

```java
static void unsafe(List<?> items) {
    // items.add(new Dog()); // Still invalid.
}
```

Adding a helper does not allow arbitrarily inserting an object of another actual type. The type variable in the helper merely names an unknown type and keeps that relationship consistent.

### 11.3. Requires a mutable List and enough elements

`swapCaptured` may throw `IndexOutOfBoundsException` if the list has fewer than two elements, or `UnsupportedOperationException` if the list does not support modification.

PECS/capture solves the **static typing** problem, not length or mutability checks. Production APIs may check `size() >= 2` and document the mutability requirement.

## 12. When **not** to use wildcards?

PECS is a guideline for methods **receiving** data; overusing wildcards everywhere makes APIs less clear.

### 12.1. Must both read and write values of the same T

```java
static <T> void replaceFirst(List<T> list, T replacement) {
    list.set(0, replacement);
}
```

`List<T>` links the type of the list and the replacement. This is usually the right design if the method needs to write a caller-supplied `T` while still reading `T` from the list.

Using `List<? extends T>` makes writing `replacement` impossible/hard. Using `List<? super T>` fails to guarantee reading `T`.

### 12.2. Returning wildcards makes callers harder to use

An API:

```java
static List<? extends Animal> makeAnimals() {
    return List.of(new Dog(), new Cat());
}
```

may be valid if you only want to publish a readable list. Yet if the API genuinely creates a clear `List<Animal>`, the return type:

```java
static List<Animal> makeAnimals() {
    return new ArrayList<>(List.of(new Dog(), new Cat()));
}
```

is easier to use when callers need to add an `Animal`.

Do not choose a wildcard in the return type just to "seem more generic"; it can push complexity onto callers.

### 12.3. Do not use wildcards to hide a missing domain model

If a method needs to know whether its input is a list of `Dog` or `Cat` to perform very different actions, `List<? extends Animal>` does not supply a runtime generic argument. Use polymorphism on `Animal`, strategy, visitor, or clear domain structures instead of unchecked casting `List<?>` to `List<Dog>`.

### 12.4. Do not confuse `? extends` with immutability

`List<? extends T>` only provides a restricted compile-time contract, not freezing the actual object. When you need to prevent others from modifying a collection, use copies/unmodifiable views per contract together with aliasing control.

## 13. Complete Java 17 example: PECS in a realistic API

Create the file **`PecsApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;

public class PecsApiDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        @Override
        public String toString() {
            return getClass().getSimpleName()
                    + "(" + name + ")";
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    static <T> void appendAll(
            List<? extends T> source,
            Collection<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    static <T, R> void transformAll(
            Iterable<? extends T> source,
            Function<? super T, ? extends R> mapper,
            Collection<? super R> target) {
        for (T item : source) {
            target.add(mapper.apply(item));
        }
    }

    static <T> List<T> concat(
            List<? extends T> left,
            List<? extends T> right) {
        List<T> result = new ArrayList<>(
                left.size() + right.size());
        result.addAll(left);
        result.addAll(right);
        return result;
    }

    static void addDefaultDog(List<? super Dog> target) {
        target.add(new Dog("Bolt"));
    }

    static String firstName(
            List<? extends Animal> animals) {
        return animals.get(0).name();
    }

    static void swapFirstTwo(List<?> items) {
        swapCaptured(items);
    }

    private static <T> void swapCaptured(List<T> items) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }

    public static void main(String[] args) {
        List<Dog> dogs = new ArrayList<>(
                List.of(new Dog("Rex"), new Dog("Amy")));
        List<Cat> cats = new ArrayList<>(
                List.of(new Cat("Miu")));

        List<Animal> animals = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        appendAll(dogs, animals);
        appendAll(dogs, objects);
        addDefaultDog(animals);

        System.out.println("animals=" + animals);
        System.out.println("objects=" + objects);
        System.out.println("first=" + firstName(dogs));

        List<Animal> combined = concat(dogs, cats);
        System.out.println("combined=" + combined);

        List<String> names = new ArrayList<>();
        Function<Animal, String> getName = Animal::name;
        transformAll(dogs, getName, names);
        System.out.println("names=" + names);

        Comparator<Animal> byName =
                Comparator.comparing(Animal::name);
        dogs.sort(byName);
        System.out.println("sorted=" + dogs);

        List<Integer> numbers = new ArrayList<>(
                List.of(3, 7));
        List<Number> numericTargets = new ArrayList<>(
                List.of(0, 0, 0));

        Collections.copy(numericTargets, numbers);
        System.out.println("copy=" + numericTargets);

        List<String> words = new ArrayList<>(
                List.of("one", "two"));
        swapFirstTwo(words);
        System.out.println("swapped=" + words);

        List<?> unknown = dogs;
        System.out.println("unknown-read=" + unknown.get(0));

        List<? super Dog> sink = animals;
        Object readBack = sink.get(0);
        System.out.println("super-read=" + readBack);
    }
}
```

Compile with Java 17:

```bash
javac --release 17 -Xlint:all PecsApiDemo.java
java PecsApiDemo
```

Verified: the program compiles cleanly **with zero warnings** under `-Xlint:all` and produces exact stdout:

```text
animals=[Dog(Rex), Dog(Amy), Dog(Bolt)]
objects=[Dog(Rex), Dog(Amy)]
first=Rex
combined=[Dog(Rex), Dog(Amy), Cat(Miu)]
names=[Rex, Amy]
sorted=[Dog(Amy), Dog(Rex)]
copy=[3, 7, 0]
swapped=[two, one]
unknown-read=Dog(Amy)
super-read=Dog(Rex)
```

### 13.1. `animals` and `objects`

`appendAll(dogs, animals)` and `appendAll(dogs, objects)` are both valid thanks to the `<T>` link between producer and consumer. Afterward, `addDefaultDog(animals)` appends `Dog(Bolt)`.

`List<Dog>` does not need to be forced or copied into `List<Animal>` **before passing**. Values are copied into the target list inside the method because that is the specific purpose of `appendAll`.

### 13.2. `first=Rex`

`firstName(List<? extends Animal>)` accepts `List<Dog>` and reads an `Animal`, calling `name()`. The API does not need to know the list's exact type argument.

### 13.3. `combined`

`concat` creates a result list that can hold both `Dog` and `Cat`. The caller declares `List<Animal>`, and the compiler infers an appropriate `T`. There is no invalid assignment from `List<Dog>` to `List<Animal>`; this is **a new collection**.

### 13.4. `names`

`Function<Animal,String>` can handle `Dog` because the mapper input is `? super T`. `transformAll` reads `Dog` from `Iterable<? extends T>` and writes `String` into `Collection<? super R>`.

### 13.5. `sorted`

`Comparator<Animal>` is accepted by `List<Dog>.sort(Comparator<? super Dog>)`. It compares `Dog`s via behavior defined on `Animal`. The result sorts `Amy` before `Rex`.

### 13.6. `copy=[3, 7, 0]`

`Collections.copy` **overwrites** the first two positions of a three-element destination list. It does not append: the third position keeps `0`.

### 13.7. `swapped=[two, one]`

The generic helper captures the type of a specific `List<?>` and reads/writes those same existing elements. This is not adding an arbitrary `String` to a `List<?>`.

### 13.8. `unknown-read` and `super-read`

`List<?> unknown` allows reading as `Object`. `List<? super Dog> sink` likewise only allows reading as `Object`. The runtime object happens to be `Dog` in the example, yet the compiler cannot infer `Dog` from the `? super Dog` signature alone.

## 14. Four examples that intentionally fail to compile

Place **each example in its own file** to observe the exact diagnostic; do not copy these errors into `PecsApiDemo.java`.

### 14.1. `WrongInvariant.java`

```java
import java.util.List;

class WrongInvariant {
    static class Animal {
    }

    static class Dog extends Animal {
    }

    static void test(List<Dog> dogs) {
        List<Animal> animals = dogs;
    }
}
```

Run:

```bash
javac --release 17 WrongInvariant.java
```

The compiler reports:

```text
error: incompatible types:
List<Dog> cannot be converted to List<Animal>
```

Solution if read-only:

```java
List<? extends Animal> animals = dogs;
```

If an independent `List<Animal>` is needed to add `Cat`:

```java
List<Animal> animals = new ArrayList<>(dogs);
```

The fix requires importing `ArrayList` if placed in a separate file.

### 14.2. `WrongProducer.java`

```java
import java.util.List;

class WrongProducer {
    static class Animal {
    }

    static class Dog extends Animal {
    }

    static void test(List<? extends Animal> source) {
        source.add(new Dog());
    }
}
```

Run:

```bash
javac --release 17 WrongProducer.java
```

The compiler reports the core message:

```text
error: incompatible types:
Dog cannot be converted to CAP#1
```

`CAP#1` is an unknown capture type upper-bounded by `Animal`. If the real list is `List<Cat>`, adding a `Dog` would be wrong.

**Fix:** if it is genuinely a destination receiving `Dog`, define the API to take `List<? super Dog>`. If it is a source, do not add elements to it.

### 14.3. `WrongConsumer.java`

```java
import java.util.List;

class WrongConsumer {
    static class Animal {
    }

    static class Dog extends Animal {
    }

    static void test(List<? super Dog> target) {
        Dog dog = target.get(0);
    }
}
```

Run:

```bash
javac --release 17 WrongConsumer.java
```

The compiler reports:

```text
error: incompatible types:
CAP#1 cannot be converted to Dog
```

A `List<? super Dog>` could be `List<Object>`; an existing element is not guaranteed to be a `Dog`. Use `Object dog = target.get(0)` if only an `Object` is needed, or design a different signature when reading an exact `Dog` is required.

### 14.4. `WrongWildcard.java`

```java
import java.util.List;

class WrongWildcard {
    static void test(List<?> input) {
        input.add("hello");
    }
}
```

Run:

```bash
javac --release 17 WrongWildcard.java
```

The compiler reports:

```text
error: incompatible types:
String cannot be converted to CAP#1
```

`List<?>` has an unknown type argument. If the method needs to write `String`, use `List<? super String>` or `List<String>` depending on the required read/write capabilities.

The failing cases above were verified directly with `javac --release 17`. Line numbers and capture variable names may vary by code/JDK, but the underlying type-safety reason remains unchanged.

## 15. Designing PECS for multi-operation APIs

A real-world API often has several distinct read/write functions. Do not try to force all of them into **one** overly general wildcard signature.

### 15.1. Read-only API

```java
static double sum(
        Collection<? extends Number> numbers) {
    double result = 0;
    for (Number n : numbers) {
        result += n.doubleValue();
    }
    return result;
}
```

This illustrative method requires importing `Collection`. It reads `Number`s without modifying the dataset. `? extends Number` lets callers pass collections containing `Integer`, `Double`, and other `Number` subtypes.

### 15.2. Write-only API

```java
static void emitDefaults(
        Collection<? super Integer> target) {
    target.add(1);
    target.add(2);
}
```

It can accept `Collection<Integer>`, `Collection<Number>`, and `Collection<Object>` when those collections are modifiable.

### 15.3. Copy API between source and destination

```java
static <T> void transfer(
        Iterable<? extends T> source,
        Collection<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}
```

`T` links the element type flowing across both sides. `Iterable` can be more suitable than `List` if only iteration is needed.

### 15.4. Read-and-modify API under the same type

```java
static <T> void replaceFirst(
        List<T> values, T replacement) {
    values.set(0, replacement);
}
```

Do not force wildcards if `T` must be consistent across reading/writing and between parameters.

### 15.5. Size-only API

```java
static int sizeOf(Collection<?> values) {
    return values.size();
}
```

`<?>` expresses this accurately because no type relationship needs to be named.

## 16. Wildcards in return types and public APIs

A useful design guideline is **generally prefer wildcards for input parameters**, and rarely return wildcards if callers need to manipulate the result further.

Example:

```java
static List<? extends Animal> getAnimals() {
    return List.of(new Dog(), new Cat());
}
```

Callers can iterate `Animal`s, yet cannot easily add an `Animal` through that return type.

If the method owns the collection and genuinely publishes an `Animal` list:

```java
static List<Animal> getAnimals() {
    List<Animal> result = new ArrayList<>();
    result.add(new Dog());
    result.add(new Cat());
    return result;
}
```

then the return type `List<Animal>` can be clearer.

Still, returning a wildcard is **not always wrong**. In APIs that need to express an unspecified concrete collection or protect a read contract without letting callers write arbitrary types, it can fit well. Decide based on caller needs, not a rigid ban.

### 16.1. `? extends` does not perform a defensive copy

If you directly return a mutable list as `List<? extends Animal>`, callers might still hold another alias that mutates the list. Or callers themselves can call `clear()` on the reference if the object allows it.

If the goal is avoiding mutation or keeping a snapshot, use proper ownership and unmodifiable copies, not wildcards alone.

### 16.2. APIs with multiple generic versions

When an API has a generic helper and an overload taking `List<?>`, watch out for **erasure/name clashes**. Two overloads differing only in the type argument of the same raw `List` cannot be declared together because their erasures collide.

Intentionally invalid example:

```java
// Cannot coexist in the same class:
// void inspect(List<String> values) {}
// void inspect(List<Integer> values) {}
```

Both erase to a `List` parameter. Wildcards add flexibility, yet do not permit overloading methods that differ only in erased generic type arguments.

## 17. PECS with `Optional`, `Stream`, and `Predicate`

The input/output direction rule also appears in non-Collection APIs.

### 17.1. `Optional.map`

Its signature has the form:

```java
<U> Optional<U> map(
    Function<? super T, ? extends U> mapper)
```

The mapper **accepts `T`** (consumer) so its input has `? super T`; the mapper **produces `U`** (producer) so its output has `? extends U`.

This is the exact `Function` pattern of `transformAll`, merely with an `Optional` container.

### 17.2. `Stream.map`

The Stream API likewise uses `Function<? super T, ? extends R>` to allow lambdas/method references to consume a supertype and produce a subtype of the result type under inference.

Example:

```java
List<String> names = dogs.stream()
        .map(Animal::name)
        .toList();
```

The snippet above assumes `dogs` is `List<Dog>` and `Animal` has a `name` method. `Animal::name` takes an `Animal` and can therefore be applied to each `Dog`.

### 17.3. `Predicate<? super T>`

A predicate **consumes** `T` to test it:

```java
static <T> long countMatching(
        Iterable<? extends T> source,
        Predicate<? super T> check) {
    long count = 0;
    for (T value : source) {
        if (check.test(value)) count++;
    }
    return count;
}
```

This example requires importing `java.util.function.Predicate`. The source is a producer (`extends`), and the predicate is a consumer (`super`).

### 17.4. Do not flip wildcard direction based on interface name

`Supplier<? extends T>` is a producer because `get()` **returns** `T`. `Consumer<? super T>` is a consumer because `accept` **takes** `T`. `Comparator<? super T>` consumes objects for comparison.

Look at **how the interface uses `T`**, not just the interface name. A `Function` both consumes an input and produces an output, so it has both directions.

## 18. Wildcard bounds and type inference

A general PECS method:

```java
static <T> void appendAll(
        List<? extends T> from,
        Collection<? super T> to) {
    to.addAll(from);
}
```

when called as:

```java
appendAll(dogs, animals);
```

needs to find a `T` allowing:

- Elements of `dogs` to be read as `T`.
- `animals` to accept `T`.

The compiler solves these constraints via generic method type inference.

### 18.1. Explicit type witness if needed

In some cases, you can write:

```java
MyClass.<Animal>appendAll(dogs, animals);
```

`MyClass` is the class containing the static method in the illustration. Specifying `T=Animal` can help clarify intent in hard-to-infer code, yet **does not turn an invalid assignment into a valid one**.

When unnecessary, letting Java infer types usually keeps code cleaner.

### 18.2. When inference reports incompatible bounds

If a method receives producer/consumer arguments with incompatible types, the compiler may report:

```text
inference variable T has incompatible bounds
```

At that point, write down the subtype relationships that must hold and identify which constraints conflict. For instance, trying to copy a `List<Cat>` into a `List<Dog>` is unsafe because `Cat` is not of element type `Dog`.

Do not add raw casts or `@SuppressWarnings("unchecked")` just to silence the compiler. If converting `Cat` to `Dog` is genuinely required by business logic, define an actual **mapper** returning `Dog` instead of forcing Generics to ignore data types.

## 19. Not all wildcards can be combined arbitrarily

### 19.1. Two wildcards have no automatic relationship with each other

```java
static void broken(
        List<?> from, List<?> to) {
    // Does not compile:
    // to.add(from.get(0));
}
```

Each `?` has **its own capture type**. The compiler cannot assume the hidden type arguments of the two lists are the same.

The solution when you want a safe copy is a `<T>` linking both sides:

```java
static <T> void copyOne(
        List<? extends T> from,
        List<? super T> to) {
    to.add(from.get(0));
}
```

### 19.2. `? extends Number` is not `? super Number`

- `List<? extends Number>` can hold `Integer`, `Double`, `BigDecimal`; read as `Number`.
- `List<? super Number>` can be `List<Number>` or `List<Object>`; `Number` can be added.

Flipping the wildcard completely changes what the API does. A method that only wants to compute a sum does not want `? super Number`. A method writing `Number` into a destination should not accept `? extends Number`.

### 19.3. `List<Object>` is not "accept any list"

```java
static void inspect(List<Object> list) {
}
```

only accepts references compatible with `List<Object>`, not `List<String>`. If the method only observes any list, use `List<?>`; if it needs to read as a parent type, use `List<? extends Parent>`.

## 20. Common misconceptions

**Misconception 1: `Dog extends Animal` implies `List<Dog> extends List<Animal>`.** False: generic parameterized types are invariant.

**Misconception 2: `? extends T` makes a List completely read-only.** False: it restricts adding arbitrary `T` elements; it does not guarantee the object is immutable or has no mutating aliases.

**Misconception 3: `? super Dog` lets you read `Dog` out.** False: elements could come from a `List<Object>`; read safely under the general type `Object`.

**Misconception 4: `List<?>` is the same as `List<Object>`.** False: `List<?>` accepts lists with different type arguments; `List<Object>` is not a supertype of every `List<T>`.

**Misconception 5: Just use PECS without `<T>`.** False: when linking source, destination, mapper, and return type, a type parameter `<T>` lets parts of the signature share a type relationship.

**Misconception 6: Every API should use `? extends` on inputs.** False: if an input is a destination to add `T`, consider `? super T`.

**Misconception 7: `? super T` means adding any supertype of `T` is allowed.** False: the method can add `T` or subtypes; it cannot arbitrarily add `Object`/`Animal` when the actual destination might be `List<Dog>`.

**Misconception 8: PECS copies data or guarantees no mutation.** False: wildcards only constrain compile-time typing. Side effects, aliasing, nulls, and mutability require separate contracts.

**Misconception 9: `Collections.copy` means append.** False: it overwrites elements by index; the destination must have sufficient size.

**Misconception 10: `Comparator<Animal>` cannot be used with `List<Dog>`.** False: `List.sort` accepts `Comparator<? super E>`, so an `Animal` comparator can compare `Dog`s.

**Misconception 11: Wildcard capture is a trick to bypass type safety.** False: the helper names a captured type to preserve relationships, without making mismatched objects addable to the list.

**Misconception 12: As long as the compiler accepts `add`, the collection definitely supports modification.** False: the runtime collection may be unmodifiable or reject nulls.

## 21. Checklist for choosing wildcards by parameter role

When designing a public method, ask in order:

1. **Does the method only need to read elements as `T`?** Use `Collection<? extends T>` or an appropriate interface.
2. **Does the method only need to insert `T` elements into a destination?** Use `Collection<? super T>`.
3. **Does the method only need size or `Object` iteration?** Use `Collection<?>` instead of declaring an unnecessary `T`.
4. **Does the method need to link types across multiple parameters?** Declare `<T>` and place wildcards in the right direction for each parameter.
5. **Does the method need to both read and write on the same structure as `T`?** Consider `Collection<T>`/`List<T>` or a capture helper.
6. **Are `List` semantics genuinely needed?** If not, consider `Iterable`/`Collection`.
7. **Can the return type remain a clear `List<T>`?** Avoid wildcard return types that make life harder for callers unnecessarily.
8. **Can data contain nulls or be an unmodifiable collection?** Document contracts and test independently of Generics.
9. **Can source and destination alias the same object?** Evaluate side effects and modification during iteration.
10. **Is an actual conversion needed between two types with no subtype relation?** Use a mapper/adapter, not unchecked casts.
11. **Are there compiler warnings about raw/unchecked types?** Fix the root type-safety issue rather than reflexively suppressing.
12. **Are there tests for subtype, supertype, and compile-error cases?** Ensure the API truly accepts intended inputs while rejecting type errors.

### 21.1. Quick review workflow

A reviewer can read the signature:

```java
static <T, R> void transformAll(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper,
        Collection<? super R> target)
```

and ask:

- Is `source` truly a producer of `T`?
- Does `mapper` accept `T`/supertype and return `R`/subtype?
- Does `target` receive `R`?
- Does any method mutate `source` or expose mutable aliases against the contract?
- Are return/exception semantics clear?

If the answers are consistent, the PECS signature accurately reflects the data flow.

## 22. Exercises with answers

### Exercise 1. Accepting `List<Dog>` to read Animal

Write the parameter type of a method that reads `Animal` names such that callers can pass `List<Dog>` or `List<Cat>`.

**Answer:**

```java
static void printAll(List<? extends Animal> source) {
    for (Animal value : source) {
        System.out.println(value.name());
    }
}
```

Because `source` is a producer of `Animal`, use `? extends Animal`.

### Exercise 2. Adding Dog into multiple list types

To accept `List<Dog>`, `List<Animal>`, and `List<Object>` for adding a `Dog`, which type should be used?

**Answer:**

```java
static void addDog(List<? super Dog> target) {
    target.add(new Dog());
}
```

The destination is a consumer of `Dog`.

### Exercise 3. Why is reading a Dog from `List<? super Dog>` unsafe?

**Answer:** The reference might actually be a `List<Object>` already containing non-`Dog` data. The safe read type guaranteed by the compiler is `Object`, not `Dog`.

### Exercise 4. Fix a rigid copy method

```java
static <T> void copy(List<T> src, List<T> dest) {
    dest.addAll(src);
}
```

How do you allow copying `Dog` into `List<Animal>`?

**Answer:**

```java
static <T> void copy(
        List<? extends T> src,
        List<? super T> dest) {
    dest.addAll(src);
}
```

Source producer (`extends`), destination consumer (`super`).

### Exercise 5. Are `List<?>` and `List<Object>` the same?

**Answer:** No. `List<?>` can refer to `List<String>`, `List<Integer>`, and many other types; `List<Object>` is not a supertype of all `List<T>`.

### Exercise 6. Does `Collections.copy` append new elements to the destination list?

**Answer:** No. It replaces elements by index and requires the destination to have sufficient size. To append, use `addAll` or an API dedicated to adding elements.

### Exercise 7. Why is there `Comparator<? super E>` in `List.sort`?

**Answer:** A `Comparator` receives `E` elements to compare, making it a **consumer** of `E`. A comparator of a supertype like `Animal` can compare `Dog`s, so `? super E` fits.

### Exercise 8. Why does a `Function` have both `super` and `extends`?

**Answer:** A `Function` both **consumes input** `T` and **produces output** `R`, hence input `? super T` and output `? extends R`.

### Exercise 9. Can two `List<?>` instances copy into each other directly?

**Answer:** Not by arbitrarily doing `to.add(from.get(0))`, because the two wildcards have independent capture types. You need a type parameter linking source/destination via `? extends T` and `? super T`, or a capture helper when operating on a single matching source.

### Exercise 10. When should `List<T>` be used instead of `List<? extends T>`?

**Answer:** When the method needs an exact type relationship to **both read and write `T` on the same list**, or needs the caller to provide a `T` and store it in that list. `List<? extends T>` does not allow adding an arbitrary `T` because the real type argument might be narrower than `T`.

### Exercise 11. Is `List<? extends Animal>` guaranteed to be immutable?

**Answer:** No. It could be a mutable `ArrayList<Dog>`; the wildcard only limits operations by generic type, without blocking all mutations or aliases.

### Exercise 12. Why does the compiler reject putting `Cat` into `List<? super Dog>`?

**Answer:** The destination might be `List<Dog>`, so `Cat` is incompatible. `? super Dog` guarantees safety when adding `Dog`/subtypes of `Dog`, not every `Animal`.

## 23. Summary

**PECS is a tool for designing flexible, type-checked inputs**, not a trick for sprinkling `? extends`/`? super` arbitrarily:

- **Producer Extends**: `Collection<? extends T>` lets callers supply collections whose elements are `T` or subtypes; readable as `T`.
- **Consumer Super**: `Collection<? super T>` lets callers supply collections able to receive `T`; adding `T` is safe.
- **Combine `<T>`** to link source/target: `copy(List<? extends T>, List<? super T>)`.
- **`Function<? super T, ? extends R>`** both consumes `T` and produces `R`; `Comparator<? super T>` consumes `T` for comparison.
- **`<?>`** fits when a specific element type does not need to be mentioned; a wildcard capture helper fits when keeping an unknown type consistent.
- **`List<T>`** remains the right choice when a method must both read and write exact `T`.

Although the compiler verifies PECS, the application contract must still specify size, nulls, mutability, ownership, and aliasing. A good API chooses **parameter types wide enough to accept valid inputs without becoming so wide as to lose guarantees**, while returning result types that are easy for callers to use. Combining these rules with Java 17 examples and compiler testing will help you read and design clear, flexible, and safe Generic APIs.