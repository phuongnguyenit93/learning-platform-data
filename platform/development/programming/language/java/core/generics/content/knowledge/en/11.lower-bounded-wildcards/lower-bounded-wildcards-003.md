# Adding T and objects of subtypes of T into the `? super T` wildcard

## 1. Objective

In Java Generics, `? super T` is a **lower-bounded wildcard**. If a method accepts `List<? super T>`, it can **add elements of type `T` and any subtype of `T`** into the list, provided the list allows modification at runtime.

For example, `List<? super Number>` can accept `Number`, `Integer`, `Double`, and other subclasses of `Number`. However, that does **not** mean this reference accepts an arbitrary `Object`: `Object` is a **supertype** of `Number`, not a subtype.

This lesson explains why this rule is safe, the role of **static types** at compile time, how to write data-receiving methods (consumers), reading limitations, and common mistakes.

After this lesson, you will be able to:
- Identify exactly which types can be passed to `add` on `Collection<? super T>`.
- Prove via subtype relationships why adding `T` or a subtype of `T` is valid.
- Distinguish `List<? super T>`, `List<T>`, `List<? extends T>`, and `List<?>` at the point of writing data.
- Use generic methods to transfer data from a subtype source to a destination with a broader type.
- Distinguish compile-time errors from runtime errors when a list does not allow modification.

## 2. Type range that `List<? super T>` allows writing

Consider `List<? super Number>`: the hidden element type can be `Number` or a supertype of `Number`, such as `Object`. Therefore:

~~~java
List<? super Number> sink = new ArrayList<Object>();
sink.add(3.5);      // Double <: Number: valid.
sink.add(10);       // Integer <: Number: valid.
// sink.add("text"); // String is not Number: compile-time error.
~~~

You cannot assign `List<Integer>` to `List<? super Number>`, because `List<Integer>` does not accept every `Number` (for example, `Double`). The specific characteristic to analyze in this lesson is **the type of the expression being added**: both `T` and a subtype `S <: T` are compatible, whereas an expression whose static type is *a supertype of T* cannot be arbitrarily added, even if the runtime object is actually a subtype of `T`.

## 3. Proving the rule for adding `T` and subtypes of `T`

Let:

- `E`: the actual element type of the collection, though not known exactly.
- `T`: the lower bound in `Collection<? super T>`.
- `S`: the type of a value to be added.

The definition of `? super T` guarantees that `T` is a subtype of `E`: `T <: E`.

If `S` is `T` or a subtype of `T`, then `S <: T`.

By transitivity of the subtype relationship:

```text
S <: T <: E

S is a subtype of T
T is a subtype of the actual element type E
=> S is a subtype of E
=> A value of type S can be added to Collection<E>
```

For this reason, the compiler permits both `add(valueOfT)` and `add(valueOfSubtypeOfT)`.

### 3.1. Example with `Number`

```java
List<? super Number> sink = new ArrayList<Object>();

sink.add(Integer.valueOf(10)); // Integer <: Number: valid
sink.add(Double.valueOf(2.5)); // Double <: Number: valid
sink.add(Long.valueOf(7L));    // Long <: Number: valid
sink.add((Number) 8);          // Number: valid
sink.add(null);                // null: valid for type checking

// sink.add(new Object());     // ERROR: Object is not a subtype of Number.
// sink.add("hello");          // ERROR: String is not a subtype of Number.
```

This is an **illustrative** snippet and needs to be placed inside a method along with `import java.util.*;` if you want to compile it. The actual object is `ArrayList<Object>`, but the API of the `sink` variable only guarantees adding `Number` and its subtypes.

### 3.2. Boxing does not change the meaning of the lower bound

```java
List<? super Number> sink = new ArrayList<Number>();
sink.add(10);     // int is boxed to Integer, then upcast to Number.
sink.add(3.14);   // double is boxed to Double, then upcast to Number.
```

In the code above, `10` and `3.14` are initially primitives. The compiler can apply **autoboxing** to turn them into `Integer` and `Double`, which are subtypes of `Number`. Do not mistake this for proof that primitive `int` or `double` is a subtype of `Number`: the subtype relationship here is between the **reference types** after boxing.

## 4. Example with a multi-level inheritance hierarchy

Suppose we have:

```text
Object
  └── Animal
        ├── Bird
        └── Mammal
              ├── Dog
              └── Cat
```

With a `List<? super Mammal>` variable, the actual element type can be `Mammal`, `Animal`, or `Object`. All three types can hold `Mammal`, `Dog`, and `Cat`.

```java
List<? super Mammal> sink = new ArrayList<Animal>();

sink.add(new Mammal("Mia")); // VALID: Mammal itself.
sink.add(new Dog("Rex"));    // VALID: Dog <: Mammal.
sink.add(new Cat("Luna"));   // VALID: Cat <: Mammal.

// sink.add(new Animal("Any")); // ERROR: Animal is a supertype of Mammal.
// sink.add(new Bird("Sky"));   // ERROR: Bird is not a subtype of Mammal.
// sink.add(new Object());      // ERROR: Object is not a subtype of Mammal.
```

The classes above are fully defined in the runnable program in Section 7. This snippet only demonstrates type checking. The rule does not depend on the class names: if `S <: T`, then a value with static type `S` can be passed to `add` on `List<? super T>`.

**Note on “subtype objects”:** a reference may point to a runtime object of type `Dog`, but if the variable is declared with type `Animal`, the compiler treats it as `Animal` and does not allow adding it to `List<? super Mammal>`. Section 6 analyzes this case.

## 5. Three actual collection types that can serve as write destinations

With `T = Mammal`, the following destination types are all accepted:

```java
List<Mammal> mammals = new ArrayList<>();
List<Animal> animals = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Mammal> first = mammals; // E = Mammal.
List<? super Mammal> second = animals; // E = Animal.
List<? super Mammal> third = objects; // E = Object.

first.add(new Dog("D1"));
second.add(new Dog("D2"));
third.add(new Dog("D3"));
```

Notably, **the actual type `E` can differ**, yet every type in the three cases is broad enough to accept `Mammal` and subtypes of `Mammal`.

You cannot infer in reverse that `List<Dog>` is also valid:

```java
List<Dog> dogs = new ArrayList<>();
// List<? super Mammal> wrong = dogs; // COMPILE-TIME ERROR
```

If such an assignment were allowed, `wrong.add(new Cat("Luna"))` would violate the promise that the original list holds only `Dog`.

**Rule for choosing destination variables:** `List<T>` and `List<SupertypeOfT>` can be assigned to `List<? super T>`; `List<SubtypeOfT>` cannot.

## 6. Static type determines the `add` call

The Java compiler checks additions based on **the declared type of the expression**, not based on the subclass the object happens to have at runtime.

Suppose `Dog extends Mammal extends Animal`:

```java
List<? super Mammal> sink = new ArrayList<Object>();

Dog dog = new Dog("Rex");
Mammal mammal = dog;
Animal animal = dog;
Object object = dog;

sink.add(dog);    // VALID: static type Dog <: Mammal.
sink.add(mammal); // VALID: static type Mammal.

// sink.add(animal); // ERROR: static type Animal, even though runtime is Dog.
// sink.add(object); // ERROR: static type Object, even though runtime is Dog.
```

This protects the program. If `Animal animal` were accepted merely because the current object is a `Dog`, the very same line of code would be unsafe when `animal` points to a `Bird`.

If the program genuinely needs to narrow the type from `Animal` down to `Mammal`, it must verify at runtime:

```java
Animal candidate = new Dog("Max");
if (candidate instanceof Mammal mammalValue) {
    sink.add(mammalValue); // VALID: mammalValue has static type Mammal.
}
```

`instanceof` with a pattern variable has been officially supported since Java 16, so it runs on Java 17+. Do not blindly cast `(Mammal) candidate` because for a `Bird` it will throw `ClassCastException`.

### 6.1. Case where the subtype is inferred in a method

```java
static <T> void appendOne(List<? super T> target, T value) {
    target.add(value);
}
```

Because the `target` parameter guarantees it can hold `T`, the method can add `value` itself. For example, `appendOne(new ArrayList<Animal>(), new Dog("Rocky"))` is valid; Java can infer a type argument satisfying both the `Dog` source and the `Animal` destination.

There is no need to cast to a raw `List` to make the call compile.

## 7. Complete Java 17+ program

Save as file **`SuperWildcardInsertDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class SuperWildcardInsertDemo {
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

    static class Mammal extends Animal {
        Mammal(String name) {
            super(name);
        }
    }

    static final class Dog extends Mammal {
        Dog(String name) {
            super(name);
        }
    }

    static final class Cat extends Mammal {
        Cat(String name) {
            super(name);
        }
    }

    static final class Bird extends Animal {
        Bird(String name) {
            super(name);
        }
    }

    static <T> void appendAll(
            Collection<? super T> destination,
            Iterable<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Animal> animals = new ArrayList<>();
        List<? super Mammal> sink = animals;

        sink.add(new Mammal("Mia"));
        sink.add(new Dog("Rex"));
        sink.add(new Cat("Luna"));

        Mammal asMammal = new Dog("Max");
        sink.add(asMammal);

        List<Mammal> more = List.of(
                new Dog("Bolt"),
                new Cat("Coco")
        );
        appendAll(animals, more);

        Object first = sink.get(0);
        System.out.println("animals=" + animals);
        System.out.println("first=" + first);

        List<Object> mixed = new ArrayList<>();
        mixed.add("existing");
        List<? super Mammal> anotherSink = mixed;
        anotherSink.add(new Dog("Jet"));
        System.out.println("mixed=" + mixed);
    }
}
```

Compile/run:

```bash
javac SuperWildcardInsertDemo.java
java SuperWildcardInsertDemo
```

Exact stdout output:

```text
animals=[Mammal(Mia), Dog(Rex), Cat(Luna), Dog(Max), Dog(Bolt), Cat(Coco)]
first=Mammal(Mia)
mixed=[existing, Dog(Jet)]
```

Explanation:

1. `sink` references `List<Animal>`, which is allowed because `Animal` is a supertype of `Mammal`.
2. `sink.add` accepts `Mammal`, `Dog`, `Cat`, and a variable of static type `Mammal` holding a `Dog` object.
3. `appendAll` takes `List<Mammal>` as source and `List<Animal>` as destination, because `T = Mammal` satisfies both the source's upper bound and the destination's lower bound.
4. Reading `sink.get(0)` is only guaranteed to be `Object` by the expression type, even though the runtime object prints as `Mammal(Mia)`.
5. `mixed` already contains a `String`. It can still be viewed through `List<? super Mammal>` and have a `Dog` added, because the actual list has type `List<Object>`.

The program requires no libraries outside the JDK.

## 8. Do not infer existing data types backwards from `add` permission

`List<? super Mammal>` could be `List<Object>`, which may already contain `String` or `Bird`. Successfully adding `new Dog(...)` type-wise does not make every element read out become `Mammal`:

~~~java
List<Object> actual = new ArrayList<>();
actual.add("before");
List<? super Mammal> sink = actual;
sink.add(new Dog("Rex"));
Object first = sink.get(0); // "before"
// Mammal m = sink.get(0); // Does not compile.
~~~

Thus **the permission to add `T` and its subtypes** is the focus of this lesson; when you need to read elements as a type stronger than `Object`, you must choose an appropriate producer or check each object individually. A case requiring both reading and writing the exact same type parameter can use `List<T>` instead of a consumer wildcard.

## 9. Comparing adding capabilities across wildcards

Assume `Dog <: Mammal <: Animal <: Object`:

| Reference type | Can add `Dog`? | Can add `Mammal`? | Minimum safe read type |
| --- | --- | --- | --- |
| `List<Mammal>` | Yes | Yes | `Mammal` |
| `List<? super Mammal>` | Yes | Yes | `Object` |
| `List<? super Dog>` | Yes | Not guaranteed | `Object` |
| `List<? extends Mammal>` | Not guaranteed | Not guaranteed | `Mammal` |
| `List<?>` | Not guaranteed | Not guaranteed | `Object` |
| `List<Animal>` | Yes | Yes | `Animal` |

“Not guaranteed” means an `add` call with a non-null object of the corresponding type **is not accepted by the compiler**, even if the actual object happens to be capable of storing the data.

For `List<? extends Mammal>`, the actual list could be `List<Cat>`, so `Dog` cannot be added. For `List<?>`, the actual element type could be any reference type, so a `Mammal` or `Dog` cannot be arbitrarily added.

### 9.1. Do not reverse the relationship between two `super` bounds

If `Dog <: Mammal`, then a destination guaranteed to accept **any Mammal** also accepts **Dog**:

~~~java
List<? super Mammal> mammals = new ArrayList<Animal>();
List<? super Dog> dogs = mammals; // Valid.
dogs.add(new Dog("D"));
~~~

The direction from `List<? super Dog>` to `List<? super Mammal>` is not guaranteed: the source might actually be `List<Dog>`, which does not accept `Cat`. This is an assignment of **wildcard-typed references**, not `List<Dog>` becoming a subtype of `List<Mammal>`. The dedicated lesson on relationships between two lower-bounded wildcards examines type-argument containment and method forwarding in detail.

## 10. How to apply: methods receiving data from multiple subtypes

When an API only wants to **add data** into a collection, choose parameter type `Collection<? super T>` or `List<? super T>`:

```java
static void collectMammals(
        Collection<? super Mammal> destination,
        Mammal first,
        Mammal second) {
    destination.add(first);
    destination.add(second);
}
```

The method above accepts `Collection<Mammal>`, `Collection<Animal>`, and `Collection<Object>`. Callers can pass both `Dog` and `Cat` to the `Mammal` parameters thanks to reference upcasting.

### 10.1. General copy method with `extends` and `super`

Pattern used in the runnable program:

```java
static <T> void appendAll(
        Collection<? super T> destination,
        Iterable<? extends T> source) {
    for (T element : source) {
        destination.add(element);
    }
}
```

- `source` is a **producer**: it yields a `T` or subtype of `T`.
- `destination` is a **consumer**: it accepts a `T` and any subtype of `T`.
- When the for-each loop obtains `T element`, passing `element` directly to `add` is safe.

This pattern exemplifies **PECS — Producer Extends, Consumer Super**. `appendAll` here **appends** each element; unlike `Collections.copy(destination, source)`, which overwrites existing positions and requires the destination list to be large enough.

Several APIs in the Java library also use the safe-writing capability of the `super` wildcard, such as `Collections.copy(List<? super T> dest, List<? extends T> src)`. When reading these signatures, directly connect them to the ability to add/accept `T`.

### 10.2. Interface destination instead of concrete class

If only `add` is needed, declaring `Collection<? super T>` is usually more flexible than `ArrayList<? super T>` because callers can pass different implementations:

```java
static void saveNames(Collection<? super String> target) {
    target.add("Lan");
    target.add("Minh");
}
```

`String` is `final`, so there are no user-defined subclasses of `String`. Nevertheless, the rule for adding `T` still applies: `String` can be added to `Collection<String>`, `Collection<CharSequence>`, and `Collection<Object>`, because those element types are `String` or supertypes of `String`.

## 11. Interface types and polymorphism

The rule does not apply only to `extends` inheritance between classes. If `Dog implements Pet`, then `Dog` is a subtype of the interface `Pet`. Therefore:

```java
interface Pet {
    String getName();
}

class Dog implements Pet {
    @Override
    public String getName() {
        return "Rex";
    }
}

List<? super Pet> pets = new ArrayList<Object>();
pets.add(new Dog()); // VALID: Dog <: Pet.
```

This is a standalone example of an interface named `Pet`, not sharing the `Dog` class from the program in Section 7. Place the declarations in a file with `import java.util.*;` if trying to run it.

An object can implement multiple interfaces. If `T` is an interface, any class implementing or extending that interface can be added when the expression's static type matches.

You cannot arbitrarily add another type **just because it has similar methods**. Java is a nominal typing language: subtype relationships must come from `extends`/`implements` declarations or subtype rules recognized by the language.

## 12. Limitations outside the type rules

### 12.1. Compile-time permission does not mean runtime mutability

```java
List<? super Number> sink = List.<Number>of(1, 2, 3);
sink.add(4); // Compiles, but throws UnsupportedOperationException.
```

`List.of(...)` returns an **unmodifiable** list. The wildcard only describes data type safety, not permission to mutate the list structure.

The same applies to `Collections.unmodifiableList(...)` or a custom `Collection` that does not support `add`.

### 12.2. `null` is a special case

```java
List<? super Mammal> sink = new ArrayList<Animal>();
sink.add(null); // VALID for type checking.
```

`null` is compatible with every reference type. It is not an object of a specific subtype of `Mammal`; therefore, adding `null` should not be taken as evidence that any arbitrary object can also be added.

A collection implementation may forbid `null`, such as many immutable implementations or collections with a non-null contract. In that case, the operation may fail at runtime.

### 12.3. Generic invariance is still preserved

```java
List<Dog> dogs = new ArrayList<>();
// List<Mammal> mammals = dogs; // ERROR: List<T> is invariant.
```

Using `? super T` provides **a type-safe write view** into broader element types; it does not turn `List<Dog>` itself into `List<Mammal>`, and does not allow mixing `Cat` into `List<Dog>`.

### 12.4. Do not abuse raw types and unchecked casts

```java
List<Dog> dogs = new ArrayList<>();
// List<? super Mammal> invalid = dogs; // ERROR.
// List<? super Mammal> forced = (List) dogs; // Dangerous raw cast.
```

A raw cast can hide warnings and let code add `Cat` into a list declared as `List<Dog>`. When retrieving elements as `Dog`, the program may throw `ClassCastException`. The proper fix is to adjust the destination collection's type (for example `List<Mammal>` or `List<Animal>`), or adjust the method's contract to match the data it needs to support.

## 13. Valid/invalid scenarios table

With the type hierarchy `Dog, Cat <: Mammal <: Animal <: Object` and the declaration:

```java
List<? super Mammal> sink = new ArrayList<Animal>();
```

| Expression | Compiles? | Reason |
| --- | --- | --- |
| `sink.add(new Mammal("M"))` | Yes | Exact type `Mammal` |
| `sink.add(new Dog("D"))` | Yes | `Dog <: Mammal` |
| `sink.add(new Cat("C"))` | Yes | `Cat <: Mammal` |
| `sink.add(new Animal("A"))` | No | `Animal` is a supertype of `Mammal` |
| `sink.add(new Bird("B"))` | No | `Bird` is not a subtype of `Mammal` |
| `sink.add(new Object())` | No | `Object` is not a subtype of `Mammal` |
| `sink.add(null)` | Yes | `null` is compatible with every reference type |
| `Object x = sink.get(0)` | Yes | Reading is guaranteed to return `Object` |
| `Mammal m = sink.get(0)` | No | Read type is not guaranteed to be `Mammal` |
| `sink.add((Mammal) animal)` | Yes at compile-time | Runtime cast is only safe if `animal` is actually a `Mammal` |

The expressions in the table assume classes `Animal`, `Mammal`, `Dog`, `Cat`, `Bird` as in Section 7, and that variable `animal` in the last row is already declared with type `Animal`.

## 14. Common mistakes when designing write methods

### Mistake 1: Reading `super` in the reverse direction

Wrong: “`List<? super Mammal>` is a list that only adds `Animal` or `Object`.”

Right: `Animal`/`Object` are the **possible actual element types of the list**. When operating through the wildcard reference, only adding `Mammal` or subtypes of `Mammal` is guaranteed.

### Mistake 2: Choosing `? extends T` for an argument that needs `add`

```java
// static void addDog(List<? extends Mammal> sink) {
//     sink.add(new Dog("Rex")); // ERROR.
// }
```

A source of type `List<? extends Mammal>` might actually be `List<Cat>`. If the method wants to accept `Dog`, declare `List<? super Dog>` (accepting `List<Dog>`, `List<Mammal>`, `List<Animal>`, `List<Object>`). If it wants to accept any `Mammal`, use `List<? super Mammal>`.

### Mistake 3: Assuming a runtime subtype is always enough

```java
Animal animal = new Dog("Rex");
// sink.add(animal); // ERROR because static type is Animal.
```

The fix is to express the right type contract from the start (`Mammal mammal = new Dog("Rex")`) or use `instanceof Mammal m` when handling an `Animal` object whose subtype is unknown.

### Mistake 4: Putting `List<? super T>` on every parameter

If a method **only reads** elements as `T`, `? extends T` is usually more suitable. If it both reads as `T` and writes `T`, preserve the type relationship using `List<T>` or a generic method `<T>`.

There is no single wildcard optimal for every data direction.

### Mistake 5: Ignoring mutability and runtime error checks

`Collection<? super T>` only guarantees that calling `add(T)` is **type-safe**. It does not force every implementation to support adding; callers must pass a collection matching the method's contract if mutation is required.

## 15. Self-assessment exercises

Given:

```java
class Vehicle {}
class Car extends Vehicle {}
class Taxi extends Car {}
class Bike extends Vehicle {}
```

### Exercise 1: Decide on `add` calls

```java
List<? super Car> destination = new ArrayList<Vehicle>();

destination.add(new Car());  // (1)
destination.add(new Taxi()); // (2)
// destination.add(new Vehicle()); // (3)
// destination.add(new Bike());    // (4)
destination.add(null);       // (5)
```

**Answer:** (1), (2) are valid because `Car` is the lower bound and `Taxi <: Car`; (5) is valid type-wise. (3), (4) are invalid because `Vehicle` and `Bike` are not subtypes of `Car`.

### Exercise 2: Choose valid source lists

Given `List<? super Car> sink`, indicate which list types can be assigned to this variable: `List<Car>`, `List<Vehicle>`, `List<Object>`, `List<Taxi>`.

**Answer:** `List<Car>`, `List<Vehicle>`, and `List<Object>` are all valid; `List<Taxi>` is invalid, because an arbitrary `Car` cannot be added to `List<Taxi>`.

### Exercise 3: Compare static type and actual type

```java
Vehicle a = new Taxi();
Car b = new Taxi();

// sink.add(a); // (1)
sink.add(b);    // (2)
```

**Answer:** (1) is invalid even though runtime is `Taxi`, because `a` has static type `Vehicle`. (2) is valid because `b` has static type `Car`.

### Exercise 4: Why can't `Car` be read?

```java
List<Object> objects = new ArrayList<>();
objects.add("not a vehicle");
List<? super Car> sink = objects;

// Car c = sink.get(0);
Object value = sink.get(0);
```

**Answer:** `sink` may reference a `List<Object>` containing other types. `get` only guarantees returning `Object`. Casting to `Car` when the first element is a string would throw `ClassCastException`.

### Exercise 5: Fill in the appropriate wildcards

A method needs to take each element of type `Car` or a subtype from a source and add it into a collection capable of holding `Car`. Which signature is suitable?

```java
static void transfer(
        Collection<? super Car> destination,
        Iterable<? extends Car> source) {
    for (Car car : source) {
        destination.add(car);
    }
}
```

**Answer:** Destination uses `? super Car` because it **consumes** `Car`; source uses `? extends Car` because it **produces** `Car`. This method accepts an `Iterable<Taxi>` source and a `Collection<Vehicle>` destination.

## 16. Checklist when needing to add elements to a generic collection

1. Identify `T`: the minimum type the receiving collection must support.
2. If the parameter is a write destination, use `Collection<? super T>` or an appropriate general interface.
3. Check **the static type `S` of the expression being added**: require `S <: T` or `S = T`.
4. Check whether the actual element type of the collection (`E`) is `T` or a supertype of `T`.
5. Do not infer subtypes solely from the runtime object when the variable is declared with a broader type.
6. Do not assume `get()` returns `T` on a `? super T` variable: the safe default is `Object`.
7. Check whether the collection supports `add` and its `null` policy at runtime.
8. Avoid raw types or unchecked casts to bypass compile errors.

## 17. References

- Oracle Java Tutorials — [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): consumer rules and how to choose `? super T`.
- Oracle Java Tutorials — [Lower Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html): examples and usage of lower-bounded wildcards.
- Java Language Specification, Java SE 17 — [§4.5.1 Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcard type arguments and bound relationships.
- Java API — [Collection.add(E)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#add(E)): element-addition contract, unsupported operation cases, and runtime exceptions.

**Core takeaway:** With `List<? super T>`, any value whose **static type is `T` or a subtype of `T`** can be passed to `add` in a type-safe manner. The `super` bound indicates that the collection's actual element type is broad enough to accept those values; when reading from the wildcard reference, the compiler still only guarantees `Object`.