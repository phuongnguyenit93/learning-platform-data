# Limitations When Returning Wildcards from APIs in Java Generics

## 1. Goal and Practical Problem

The **PECS** (*Producer Extends, Consumer Super*) rule helps select wildcards for generic parameters: an object used to **supply data** usually suits `? extends T`, while an object used to **receive data** usually suits `? super T`. However, applying PECS mechanically to **an API's return type** can strip type information from calling code, restrict operations, and force wildcards to propagate across many other layers of code.

Example:

```java
static List<? extends Number> numbers() {
    return List.of(1, 2, 3);
}
```

The following call is valid:

```java
List<? extends Number> result = numbers();
Number number = result.get(0);
```

Yet these two operations are invalid:

```java
// List<Number> result = numbers(); // ERROR: return type does not guarantee List<Number>.
// numbers().add(4);               // ERROR: actual element type is unknown.
```

These are **compile-time limitations**, not necessarily design mistakes in every situation. This lesson distinguishes when a wildcard return makes sense, when it makes an API hard to use, and how to write clearer return signatures.

After studying this lesson, you will be able to:

- Explain what type information `List<?>`, `List<? extends T>`, and `List<? super T>` preserve for the caller.
- Distinguish **returning a value** from the producer/consumer role of **the returned object**.
- Understand why `List<? extends T>` is not synonymous with `List<T>` or an unmodifiable list.
- Design APIs returning concrete types, suitable supertypes, or generic `<T>` methods when callers need stronger type information.
- Recognize cases where wildcard returns are useful and avoid unchecked casts.

## 2. What Is a Wildcard Return?

Suppose we have the classes:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}
```

And a library provides the following methods:

```java
static List<Dog> dogs() {
    return List.of(new Dog());
}

static List<? extends Animal> animalsUnknownSubtype() {
    return dogs();
}

static List<?> unknownItems() {
    return dogs();
}
```

The signature `List<Dog>` tells the caller **the exact type argument is `Dog`**. The signature `List<? extends Animal>` only indicates the type argument is an unspecified subtype of `Animal`. The signature `List<?>` guarantees nothing more specific about elements than `Object`.

A method may return the exact same runtime object in all three cases. The main difference is **the type contract Java lets the caller use**.

### 2.1. The Published Type Governs Valid Operations

Inside library code, the author might know the result is `List<Dog>`. When publishing the signature `List<? extends Animal>`, the fact that it is **specifically `Dog`** is no longer guaranteed to the caller:

```java
List<? extends Animal> animals = animalsUnknownSubtype();

Animal first = animals.get(0); // Valid.
// Dog dog = animals.get(0);   // Error: value is only guaranteed to be Animal.
// animals.add(new Dog());     // Error: actual list might be List<Cat>.
```

The runtime object may contain `Dog`; however, Java must verify that the program is safe for **every type** permitted by the signature, not just the outcome of one execution.

## 3. Why Should PECS Not Be Applied Mechanically to Return Types?

In the signature:

```java
static void process(List<? extends Animal> source) { ... }
```

`source` is a parameter playing the **producer** role when `process` needs to read data. The upper-bounded wildcard lets callers pass `List<Dog>`, `List<Cat>`, or `List<Animal>` while guaranteeing elements can be read as `Animal`.

But in the signature:

```java
static List<? extends Animal> getAnimals() { ... }
```

the caller **receives a list object**. Once received, they may want to read, filter, copy, add elements, sort, or pass the result to another method. If the return declaration contains a wildcard, every subsequent operation is subject to that wildcard's restrictions.

Two perspectives must be distinguished:

1. **The method returning a value**: the API produces an object for the caller.
2. **The returned collection**: the caller may use that object to produce or consume elements.

Do not conclude that because a method is a producer of the returned object, its return type must use `? extends T`. Decide based on **the contract the caller needs**.

A common recommendation from Java Generics guidelines is to **avoid wildcards in return types when possible**, because callers then have to deal with unknown types. This is an API design principle, not a syntax prohibition.

## 4. Returning `List<?>`: Losing Element Information

Example:

```java
static List<?> loadItems() {
    return List.of("Java", "Generics");
}
```

At the caller:

```java
List<?> values = loadItems();
Object item = values.get(0);       // Valid.
int count = values.size();         // Valid.

// String value = values.get(0);   // Compilation error: only guarantees Object.
// values.add("new element");      // Compilation error: element type is unknown.
```

Type-wise, `List<?>` can represent `List<String>`, `List<Integer>`, or many other types. Hence the result of `get` is only guaranteed to be `Object`, and `add` cannot accept an arbitrary non-null object in a generally safe way.

### 4.1. When `List<?>` Is Still Appropriate

A `List<?>` return type can make sense when **the actual domain meaning is a collection with unknown or heterogeneous elements** and the caller only needs element-type-independent operations:

```java
static List<?> diagnosticValues() {
    return List.of("READY", 200, true);
}
```

The caller can print, count, display, or inspect each element:

```java
for (Object value : diagnosticValues()) {
    System.out.println(value);
}
```

Yet if the API truly guarantees all elements are `String`, publishing `List<String>` is much easier to use than `List<?>`.

### 4.2. Distinguishing `List<?>` from Raw `List`

```java
List<?> safe = List.of("a", "b");
List raw = List.of("a", "b"); // Raw type, should not be used for new APIs.
```

`List<?>` still preserves generic type checking. Raw `List` bypasses part of that protection and can produce unchecked warnings. Never replace a wildcard return with a raw type just to silence the compiler.

## 5. Returning `List<? extends T>`: Readable as T, Hard to Write

Suppose:

```java
static List<? extends Number> readNumbers() {
    return List.of(1, 2, 3);
}
```

At the caller:

```java
List<? extends Number> result = readNumbers();

Number first = result.get(0); // Valid.
Object same = result.get(0);  // Valid.
// result.add(4);             // Error: element type is not guaranteed to be Integer.
// result.add(2.5);           // Error: element type is not guaranteed to be Double.
```

`? extends Number` promises that elements read out **are `Number` or a subtype of `Number`**. It does not promise the collection can accept every `Number`: the actual list could be `List<Integer>`, `List<Double>`, etc.

### 5.1. Cannot Assign Directly to `List<T>`

```java
List<? extends Number> result = readNumbers();

// List<Number> numbers = result; // Compilation error.
List<? extends Number> view = result; // Valid.
```

`List<Number>` allows adding a `Double`, whereas `List<? extends Number>` does not guarantee that. Java Generics are **invariant**: `List<Integer>` is not a subtype of `List<Number>`.

Do not use an unchecked cast:

```java
// List<Number> unsafe = (List<Number>) (List<?>) result;
```

This cast can break safety and cause the caller to add the wrong kind of object into a library-owned list.

### 5.2. Can Copy into a New `List<T>`

If the caller needs a `List<Number>` capable of accepting additional `Number` types, **copy the elements**:

```java
List<? extends Number> source = readNumbers();
List<Number> numbers = new ArrayList<>(source);

numbers.add(3.14); // Valid because the destination type is actually List<Number>.
```

The constructor `ArrayList(Collection<? extends E>)` is explicitly designed to accept a source whose element type is a subtype of `E`. The copy and source list have separate structures; adding elements to the copy does not add them to the source.

However, this is a **shallow copy**: inner element references are shared, so mutating the state of a mutable element object may still affect both sides.

### 5.3. An Upper-Bounded Wildcard Does Not Guarantee Immutability

```java
List<? extends Number> view = new ArrayList<Integer>();
view.clear(); // Compiles and runs; the list here is mutable.
// view.add(123); // Does not compile.
```

The compiler blocking `add(123)` does not mean the list is immutable. Depending on the implementation, `clear()`, `remove(...)`, `removeIf(...)`, `sort(...)`, or structural mutations that do not pass an element value may be possible.

If an API wants to guarantee **no modifications are allowed** on the collection, it must use an explicit contract and implementation such as `List.copyOf(...)`, `List.of(...)`, or an unmodifiable wrapper. Wildcards do not replace immutability mechanisms.

### 5.4. Losing Concrete Subtype Information

If a library returns a `List<Dog>` yet publishes `List<? extends Animal>`:

```java
static List<? extends Animal> getAnimals() {
    return List.of(new Dog());
}
```

then the caller cannot assume they get a `Dog`:

```java
Animal animal = getAnimals().get(0); // Valid.
// Dog dog = getAnimals().get(0);    // Not type-valid.
```

Even if today's implementation only creates `Dog`, the signature permits tomorrow's implementation to return `List<Cat>`. A broader declaration may be intentional, but if the API **always guarantees `Dog` elements**, `List<Dog>` communicates the contract more accurately.

## 6. Returning `List<? super T>`: Writable as T, Hard to Read as T

Consider:

```java
static List<? super Integer> writableNumbers() {
    return new ArrayList<Number>();
}
```

At the caller:

```java
List<? super Integer> result = writableNumbers();
result.add(10);                  // Valid.
result.add(Integer.valueOf(20)); // Valid.
Object value = result.get(0);    // Valid.

// Integer x = result.get(0); // Compilation error.
// result.add(3.14);          // Compilation error.
```

`? super Integer` states that the actual element type may be `Integer`, `Number`, or `Object`. It allows adding `Integer` and subtypes of `Integer`, while reading via `get` is only guaranteed as `Object`.

### 6.1. Why Is `? super T` Often Confusing in a Return API?

The signature:

```java
List<? super Animal> getSink();
```

implicitly tells the caller they are receiving a collection capable of **consuming `Animal`**. This may be true if the API intentionally returns a writable sink, yet it obscures questions such as:

- Who owns the list and who has permission to modify it?
- Is the list mutable?
- As what type does the caller need to read elements back?
- Why not expose a simpler behavior such as `void addAnimal(Animal item)`?

For example, an API that writes through a method is usually clearer:

```java
interface AnimalReceiver {
    void addAnimal(Animal animal);
}
```

This is a design suggestion when the API only provides the action of **accepting objects**, without needing to expose a `List` structure. It avoids unintentionally granting the caller access to all other `List` methods.

### 6.2. A Lower Bound Does Not Mean Adding Always Succeeds at Runtime

```java
List<? super Integer> immutable = List.<Number>of(1, 2);
immutable.add(3); // Compiles, but throws UnsupportedOperationException.
```

`? super T` is a **type-safety** guarantee, not a guarantee that the implementation supports modification. The API contract must document mutability and behavior when mutating operations are called.

## 7. Wildcards in Return Types Can Propagate Across Multiple Call Layers

Suppose a library declares:

```java
static List<? extends Animal> findAnimals() {
    return List.of(new Dog());
}
```

An application that only reads might do:

```java
static void printAnimals(List<? extends Animal> values) {
    for (Animal value : values) {
        System.out.println(value);
    }
}

printAnimals(findAnimals()); // Valid.
```

But if a downstream function requires `List<Animal>`:

```java
static void appendCat(List<Animal> values) {
    values.add(new Cat());
}

// appendCat(findAnimals()); // Compilation error.
```

The caller must change the design, for example by copying:

```java
List<Animal> copied = new ArrayList<>(findAnimals());
appendCat(copied);
```

In this example, `appendCat` is an illustrative method snippet placed in the same class, not a standalone program.

When multiple processing layers continually pass `List<? extends Animal>`, the wildcard can “spread” into the signatures of intermediate methods. That remains **type-correct** if every layer only reads. The problem surfaces when the next layer needs a more exact type, needs to write, or needs to describe a relationship among multiple values.

### 7.1. Never Narrow a Wildcard Based on Guesswork

```java
List<? extends Animal> values = findAnimals();
// List<Dog> dogs = values; // Compilation error.
```

Not every `List<? extends Animal>` is a `List<Dog>`. If `Dog` is required, either have the API guarantee `Dog` right in its signature or use appropriate filtering and runtime checks.

## 8. Alternative API Design: Return a Concrete Type When There Is a Concrete Guarantee

If the API manages a list of `Dog` and the contract guarantees the result is a list of `Dog`, return:

```java
static List<Dog> findDogs() {
    return List.of(new Dog());
}
```

The caller gets exact information:

```java
List<Dog> dogs = findDogs();
Dog first = dogs.get(0);
```

This is the simplest choice when the subtype is genuinely part of the contract.

**Concreteness does not mean exposing the implementation class**: you can still return the interface `List<Dog>`, `Collection<Dog>`, or `Iterable<Dog>`, depending on which methods the caller needs. What should be clear is **the element type argument** and usage contract, not forcing the caller to know the `ArrayList` implementation.

### 8.1. Returning `List<Animal>` by Creating a Copy

If the API deliberately wants to expose elements as `Animal` and give the caller a `List<Animal>`, while the underlying data is `List<Dog>`, it can create a copy:

```java
static List<Animal> animalSnapshot(List<Dog> dogs) {
    return new ArrayList<>(dogs);
}
```

`new ArrayList<>(dogs)` constructs a new `List<Animal>`. It decouples the list structure from the source list, though it does not deep-copy the `Dog` objects.

If you want to provide an **unmodifiable snapshot**:

```java
static List<Animal> immutableAnimalSnapshot(List<Dog> dogs) {
    return List.copyOf(dogs);
}
```

Type parameter inference for `List.copyOf` can use the target type `List<Animal>`. Note that `List.copyOf` does not accept `null` elements. Do not advertise the copy as a deep copy.

### 8.2. When an API Allows Adding, Still State Ownership

Returning `List<Animal>` allows the caller to write `result.add(new Cat())` **type-wise**; whether the result is actually mutable depends on the implementation. For instance, `List.copyOf` returns an unmodifiable list even though its declared type is `List<Animal>`.

State clearly in the API contract whether this is an immutable snapshot, a caller-owned mutable copy, or a view backed by internal data that may change over time. Those choices are independent of wildcards.

## 9. Alternative API Design: Generic Methods Preserving Type Relationships

When the caller supplies the necessary type information, the API can use a **named type parameter** to link input and output:

```java
static <T extends Animal> List<T> onlyType(
        List<? extends Animal> source,
        Class<T> requestedType) {

    List<T> result = new ArrayList<>();
    for (Animal animal : source) {
        if (requestedType.isInstance(animal)) {
            result.add(requestedType.cast(animal));
        }
    }
    return result;
}
```

Usage:

```java
List<Animal> source = List.of(new Dog(), new Cat());
List<Dog> dogs = onlyType(source, Dog.class);
Dog firstDog = dogs.get(0);
```

`Class<T>` provides a **runtime verification basis** before returning `List<T>`. Java can prove the elements in the result all belong to `T`, instead of forcing the caller to perform unchecked casts.

This snippet is illustrative code placed in a class with `import java.util.*;`.

### 9.1. Do Not Declare a Bogus Type Parameter Just to Please the Caller

Beware of an API like:

```java
// Example of a dangerous signature without a real constraint:
// static <T extends Animal> List<T> findAllAnimals() { ... }
```

If the call lets the caller freely infer `T = Dog` or `T = Cat`, while the actual data may contain both, the implementation has no safe way to fulfill that promise solely from a caller-chosen `T`.

A generic return type `List<T>` is only sound when there is a guaranteed type relationship: a `Class<T>` argument, a `List<T>` input parameter, a typed container `Repository<T>`, or an equivalent storage/verification mechanism.

Do not replace wildcards with `<T>` just to force code to compile; preserve the soundness of the contract.

## 10. Alternative API Design: Tying the Type Parameter to an Owning Object

A generic repository can fix the element kind at **object creation time**:

```java
interface Repository<T> {
    List<T> findAll();
}
```

Then:

```java
Repository<Dog> dogRepository = /* an implementation of Repository<Dog> */;
List<Dog> dogs = dogRepository.findAll();
```

The usage example above only illustrates the type relationship and has no concrete implementation yet. The advantage is that `T` is tied to the repository, so `findAll()` can return `List<T>` without needing `List<? extends T>`.

If the caller must not modify the list, the implementation can return `List.copyOf(stored)` or a clearly documented unmodifiable collection. The `List<T>` type still preserves exact type information.

## 11. When a Wildcard Return Is Intentional and Good

Not every wildcard return is a “design smell.”

### 11.1. Exposing a View Guaranteeing Only an Upper Bound

An API aggregating data from multiple sources may be unable to commit to an element type more specific than `Animal`:

```java
static List<? extends Animal> animalsFromSource(boolean dogsOnly) {
    return dogsOnly
            ? List.of(new Dog())
            : List.of(new Cat());
}
```

At the caller, the guarantee of “readable as `Animal`” may be enough. `List<? extends Animal>` accurately reflects the indeterminacy in the contract; it also preserves the implementation's ability to return a collection typed as `Dog` or `Cat` without copying the structure.

However, if you **only** want the caller to read as `Animal`, you can still consider `List<Animal>` by building an appropriate list. The choice depends on ownership, copy cost, flexibility, and caller manipulation needs.

### 11.2. Returning a Data Structure with Unknown Element Type

A diagnostic or discovery API may genuinely only guarantee `List<?>`:

```java
interface DiagnosticProvider {
    List<?> rawObservations();
}
```

The caller mainly cares about count, presentation, and introspection, without expecting all elements to share a uniform type beyond `Object`. Here the wildcard accurately expresses the data's indeterminacy.

### 11.3. Exposing a Data-Writing Target

A highly specialized API might return `Collection<? super Event>` for callers to add events:

```java
interface EventBuffer {
    Collection<? super Event> writableTarget();
}

class Event {}
```

Such a signature describes **the ability to accept `Event`**, though it requires documentation on mutability, ownership, synchronization, side effects, ordering, and error handling. If the job is truly just recording events, an `append(Event event)` method is usually clearer than handing out an entire `Collection`.

## 12. Complete Java 17+ Program

Save as **`WildcardReturnApiDemo.java`**. The program compares a wildcard return signature, an exact type, a supertype snapshot, and a generic method returning a verified typed result.

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardReturnApiDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return getClass().getSimpleName() + "(" + name + ")";
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

    static List<Dog> findDogs() {
        return List.of(new Dog("Rex"), new Dog("Bolt"));
    }

    static List<? extends Animal> findAnimalsWildcard() {
        return findDogs();
    }

    static List<Animal> animalSnapshot() {
        return new ArrayList<>(findDogs());
    }

    static <T extends Animal> List<T> filterByClass(
            List<? extends Animal> source,
            Class<T> requestedType) {

        List<T> result = new ArrayList<>();
        for (Animal animal : source) {
            if (requestedType.isInstance(animal)) {
                result.add(requestedType.cast(animal));
            }
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<? extends Animal> wildcard = findAnimalsWildcard();
        Animal firstAnimal = wildcard.get(0);
        // wildcard.add(new Dog("Max")); // Compilation error.

        List<Dog> typed = findDogs();
        Dog firstDog = typed.get(0);

        List<Animal> snapshot = animalSnapshot();
        snapshot.add(new Cat("Mia"));

        List<Animal> mixed = List.of(
                new Dog("Rex"),
                new Cat("Luna"),
                new Dog("Bolt")
        );
        List<Dog> filtered = filterByClass(mixed, Dog.class);

        List<Object> storage = new ArrayList<>();
        List<? super Animal> writableView = storage;
        writableView.add(new Cat("Coco"));
        Object fromWritable = writableView.get(0);

        System.out.println("wildcard=" + firstAnimal);
        System.out.println("typed=" + firstDog);
        System.out.println("snapshot=" + snapshot);
        System.out.println("filtered=" + filtered);
        System.out.println("super-read=" + fromWritable);
    }
}
```

Compile and run:

```bash
javac WildcardReturnApiDemo.java
java WildcardReturnApiDemo
```

Stdout:

```text
wildcard=Dog(Rex)
typed=Dog(Rex)
snapshot=[Dog(Rex), Dog(Bolt), Cat(Mia)]
filtered=[Dog(Rex), Dog(Bolt)]
super-read=Cat(Coco)
```

Explanation of points to verify:

1. `findAnimalsWildcard()` publishes `List<? extends Animal>`; the caller can read `Animal` but cannot add arbitrarily.
2. `findDogs()` publishes `List<Dog>`, so the caller receives `Dog` directly from `get`.
3. `animalSnapshot()` copies into `List<Animal>`; the caller can add `Cat` to **the copy** because `ArrayList` is mutable.
4. `filterByClass(..., Dog.class)` returns `List<Dog>` via `isInstance` and `cast` checks, performing no unchecked cast.
5. `List<? super Animal>` supports adding `Cat` because `Cat <: Animal`, yet `get` is only guaranteed to have type `Object`.

The `List.of(...)` lists in the program are unmodifiable lists. The `new ArrayList<>(...)` copy is modifiable. Both states exist independently of wildcards in signatures.

## 13. Wildcard Capture Can Arise on the Caller Side

Another limitation when returning `List<?>`: although the element type is unknown specifically, **there is still a single consistent type** within each list.

Example:

```java
static void swapFirstTwo(List<?> items) {
    swapCaptured(items);
}

private static <T> void swapCaptured(List<T> items) {
    if (items.size() >= 2) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }
}
```

The `swapCaptured` method uses a type parameter `T` to maintain the relationship between the read element and the written element. The compiler can **capture** the wildcard of the `List<?>` parameter when calling the helper. These are illustrative method snippets placed inside a class with `import java.util.List;`.

Distinction to note:

- `items.add(new Dog())` on `List<?>` is unsafe because `?` could be an unrelated type.
- Swapping two elements **of the very same `List<T>`** is type-safe: taking a `T` out and writing it back to another slot also expects `T`.

The `set` call may throw `UnsupportedOperationException` if the list does not permit modification. If an API returns a wildcard yet callers repeatedly have to write helpers just to use ordinary data, reconsider the return type.

## 14. Impact on Generic Inference and Method Overloading

### 14.1. Generic Methods Can Accept Wildcard Sources Without Casting

```java
static <T> void copyTo(List<? super T> target, List<? extends T> source) {
    target.addAll(source);
}
```

The caller can write:

```java
List<? extends Number> source = List.of(1, 2);
List<Number> target = new ArrayList<>();

copyTo(target, source);
```

This snippet goes inside a class with `import java.util.*;`. `copyTo` gives the compiler a type parameter `T` to link both parameters. This technique is useful when an existing API returning a wildcard cannot be changed; it **does not** turn the source into `List<Number>`.

### 14.2. Do Not Define Overloads Differing Only by Generic Wildcard

You cannot write two overloads differing only in the type argument inside `List`, such as:

```java
// void inspect(List<? extends Number> values) {}
// void inspect(List<? super Integer> values) {}
```

The two signatures conflict due to **type erasure**: both have the same raw parameter form `List` in bytecode. If an API needs two behaviors, give them two distinct meaningful names or change the parameters so they truly have distinct signatures.

The erasure issue applies to generic parameters in general; wildcard returns do not create a special overloading mechanism.

## 15. API Signature Selection Table

| Caller's need | Usually suitable signature | Reason |
| --- | --- | --- |
| API always returns `Dog` instances | `List<Dog> findDogs()` | Caller reads `Dog` directly without losing subtype information |
| API exposes elements as `Animal` and wants to return a fixed-type list | `List<Animal> findAnimals()` | No wildcard propagation; must build/return an actual `List<Animal>` |
| API only guarantees elements are subtypes of `Animal` and wants to return a non-copy view | `List<? extends Animal> findAnimals()` | Keeps subtype flexibility; caller primarily reads |
| API cannot guarantee a concrete element type | `List<?> inspect()` | Caller must handle elements as `Object` |
| Caller requests a subtype and the API can verify it | `<T extends Animal> List<T> find(Class<T> type)` | `T` is constrained via input information and checked at runtime |
| Element kind is tied to a repository | `Repository<T>.findAll(): List<T>` | Type `T` is fixed when creating the repository |
| Caller only needs to submit additional data | `void append(Animal value)` | Exposes behavior without exposing internal collection |
| API intentionally provides a general write target | `Collection<? super Animal> writableTarget()` | Permits `add(Animal)`, while reading only guarantees `Object` |

This table is a selection guide, not a one-signature-fits-all rule. You also need to consider mutability, nulls, ownership, copy cost, contract stability, and API evolution.

## 16. Common Misconceptions and Mistakes

### Mistake 1: “Returning a wildcard is always wrong”

A wildcard return is valid syntax and can accurately express indeterminacy that an API intentionally publishes. The question is whether callers genuinely need to deal with wildcards and the resulting limitations.

### Mistake 2: “`? extends T` makes a collection read-only”

`? extends T` restricts **writing new values of an unknown type** into the collection. It does not block all mutating operations such as `clear()`; nor does it guarantee a snapshot, immutability, or thread safety.

### Mistake 3: “A `List<? extends T>` result can be assigned to `List<T>`”

Generics do not automatically vary with element subtype relationships. If a dedicated `List<T>` is needed, copy it or design the API to return `List<T>` from the start.

### Mistake 4: “A returned `List<? super T>` is a `List<T>` that can read T”

No. The actual element type can be a supertype of `T`; the result of `get` is only guaranteed to be `Object`.

### Mistake 5: “Changing to `<T> List<T>` fixes everything”

Without a source constraining/verifying `T`, a method cannot safely promise that actual data matches every type chosen by the caller. Never use unchecked casts to turn an unsound API into one that “looks generic.”

### Mistake 6: “Returning `List<T>` means the caller can modify it”

The `List<T>` signature permits `add(T)` at compile time, but the implementation may return `List.of`, `List.copyOf`, or an unmodifiable wrapper. Modification rights must be specified by the API contract.

### Mistake 7: “Using `Object` or raw `List` to eliminate wildcards is an improvement”

`List<Object>` cannot arbitrarily substitute for `List<String>` due to invariance. Raw `List` weakens type checking. If the data truly has an unknown type, `List<?>` may be the safest expression.

## 17. Self-Assessment Exercises

Given:

```java
class Vehicle {}
class Car extends Vehicle {}
class Bike extends Vehicle {}

static List<? extends Vehicle> loadVehicles() {
    return List.of(new Car(), new Bike());
}
```

### Exercise 1. Which assignments are valid?

```java
List<? extends Vehicle> a = loadVehicles(); // (1)
// List<Vehicle> b = loadVehicles();         // (2)
Vehicle c = loadVehicles().get(0);          // (3)
// Car d = loadVehicles().get(0);           // (4)
```

**Answer:** (1) and (3) are valid; (2) is invalid because a wildcard cannot be narrowed to `List<Vehicle>`; (4) is invalid because the read result is only guaranteed to be `Vehicle`, which could be a `Bike`.

### Exercise 2. Can a `Car` be added to the result?

```java
List<? extends Vehicle> vehicles = loadVehicles();
// vehicles.add(new Car()); // (1)
```

**Answer:** No. The actual element type could be `Car`, `Bike`, or `Vehicle`. If the caller needs a structure that can accept `Vehicle` additions, copy it:

```java
List<Vehicle> editable = new ArrayList<>(vehicles);
editable.add(new Car());
```

### Exercise 3. When should `List<Car>` be returned?

A method `loadCars()` always returns only `Car` instances, and the caller needs to operate on the `Car` type. Choose `List<Car>`, because it accurately reflects the contract. If an API intentionally hides the subtype to expose only `Vehicle`, evaluate the reason and resulting limitations before using `List<? extends Vehicle>`.

### Exercise 4. Point out the risk of this signature

```java
// static <T extends Vehicle> List<T> loadAll() { ... }
```

If actual data contains both `Car` and `Bike`, the caller might expect `List<Car>`, which the implementation cannot guarantee. Add a verifiable filter such as `Class<T>`, or switch to `List<Vehicle>` / a typed repository model.

### Exercise 5. Find a suitable signature for receiving data

An API wants callers to send `Vehicle` objects without requiring callers to read an internal collection. Provide:

```java
void addVehicle(Vehicle vehicle);
```

It exposes the necessary behavior without tying callers to a `List` storage structure. Internally, the implementation can still use `Collection<? super Vehicle>` as a consumer.

## 18. Checklist When Reviewing a Return Signature

1. **What exact element type does the caller need to know?** If there is a clear guarantee, consider a concrete `List<T>`.
2. **Does the caller only read, or also write?** With `? extends T`, do not expect to add `T`; with `? super T`, do not expect to read out `T`.
3. **Do wildcards propagate across many layers of code?** If users must repeatedly cast, copy, or wrap, review the public contract.
4. **Is preserving the exact subtype necessary?** When it is, return `List<Dog>` instead of needlessly widening to `List<? extends Animal>`.
5. **Is there a verifiable source for a generic `<T>` return?** A `Class<T>` parameter, a `List<T>` argument, or an owning `Repository<T>` object are common patterns.
6. **Does the API return a view or a snapshot?** State clearly whether data is shared internally, whether it can change over time, and if copied, whether shallow or deep.
7. **Is the list mutable?** Wildcards and mutability are independent; clearly document add/remove/update support and runtime exceptions.
8. **Is returning the whole collection necessary?** If the goal is simply receiving data, an `add(T)` behavior may be a better API.
9. **Is code relying on unchecked casts or raw types to suppress errors?** Revisit the original types; do not discard compiler protection.

## 19. Further Reading

- Oracle Java Tutorials — [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): producer/consumer and notes on wildcard return types.
- Oracle Java Tutorials — [Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html): relationships between generic types containing wildcards.
- Oracle Java Tutorials — [Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): how to handle unknown wildcards with generic helpers.
- Java Language Specification 17 — [§4.5.1 Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): syntax, containment, and wildcard semantics.
- Java SE 17 API — [List.copyOf(Collection)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot, null behavior, and copy contract.

**Conclusion:** PECS is most useful when determining **the data direction of generic parameters**. For return types, the goal is to convey **accurate and sufficient type information** to the caller for using the API. Use `List<T>` when `T` is guaranteed; use wildcards when element-type indeterminacy is precisely what the API intends to publish; and always document mutability, ownership, and copying semantics separately.
