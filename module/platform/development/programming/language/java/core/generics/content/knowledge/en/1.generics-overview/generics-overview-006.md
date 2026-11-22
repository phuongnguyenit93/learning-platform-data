# Distinguishing Type Generality from Inheritance and Polymorphism in Java

Generics, inheritance, and polymorphism all make Java programs more flexible, yet each mechanism solves a distinct problem. When reading examples such as `List<Dog>`, `Dog extends Animal`, and `Animal animal = new Dog()`, distinguish **type relationships**, **algorithmic generality**, and **how runtime behavior is selected**.

## 1. Definitions and Essence

**Generics (type generality)** allow declaring classes, interfaces, or methods with *type parameters* (`T`, `E`, `K`, `V`, ...). The same structure or algorithm works with many types, while the compiler preserves the type relationship among arguments, holding variables, and results. For instance, `Box<String>` and `Box<Dog>` share the same `Box<T>` definition; the method `<T> T first(List<T> items)` returns the exact element type of the input list. There does not need to be any parent/child class between `String` and `Dog` to share a generic algorithm.

**Inheritance** defines an “is-a” relationship: `Dog extends Animal` means `Dog` is a subtype of `Animal`, inherits inheritable members, and can extend or override behavior. `implements` establishes that a class implements an interface; an interface can also `extends` another interface. Class inheritance can also reuse code, though it should only be used when the classification relationship genuinely holds.

**Polymorphism** means using a common interface or type to work with many concrete forms. In **runtime subtype polymorphism**, an `Animal` reference can point to a `Dog` or `Cat`; calling an overridden instance method, such as `animal.sound()`, runs the implementation corresponding to the actual object. The compiler checks that `Animal` has a `sound()` method; the runtime decides which override executes.

Some literature classifies generics as **parametric polymorphism**, and overriding via a superclass/interface as **subtype polymorphism**. These are two different meanings of the word “polymorphism”. When comparing the three mechanisms in Java, “polymorphism” usually refers to behavioral polymorphism through overriding and dynamic dispatch.

| Design Question | Generics | Inheritance | Subtype Polymorphism |
|---|---|---|---|
| What does it solve? | Reusing structures/algorithms while preserving type relationships | Organizing subtypes and inheritable contracts | Common call with different behaviors |
| Typical syntax | `class Box<T>`, `<T> T id(T x)` | `extends`, `implements` | Overriding instance methods |
| When is selection/checking mostly done? | Compile time; ordinary Java generics use type erasure | Subtype relationship is checked at compile time | Runtime selects override based on the object |
| Does it require subtypes? | No | Has subtype relationships | Usually has multiple implementations of a superclass/interface |
| Does it make `List<Dog>` a `List<Animal>`? | No | No | No |

## 2. Program Demonstrating All Three Mechanisms

Standalone runnable example for Java 17 or later. Save with the exact name **`GenericVsInheritanceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericVsInheritanceDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        String sound() {
            return "(unknown)";
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "woof";
        }
    }

    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <T> T first(List<T> items) {
        return items.get(0);
    }

    static <T extends Animal> String soundOf(T animal) {
        return animal.sound();
    }

    static <T> void copy(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<Dog> dogs = List.of(new Dog("Milu"), new Dog("Bong"));

        Dog firstDog = first(dogs);
        System.out.println("generic: " + firstDog.name());

        Animal baseRef = firstDog;
        System.out.println("polymorphism: " + baseRef.sound());
        System.out.println("bound: " + soundOf(firstDog));

        Box<Dog> box = new Box<>(firstDog);
        System.out.println("box: " + box.get().name());

        List<? extends Animal> view = dogs;
        System.out.println("wildcard: " + view.get(1).name());

        List<Animal> copied = new ArrayList<>();
        copy(dogs, copied);
        System.out.println("copy count: " + copied.size());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac GenericVsInheritanceDemo.java
java GenericVsInheritanceDemo
```

Exact stdout:

```text
generic: Milu
polymorphism: woof
bound: woof
box: Milu
wildcard: Bong
copy count: 2
```

Breaking down each result:

1. `first(dogs)` uses a **generic method**; the compiler infers `T` as `Dog`, so the receiving variable has type `Dog` with no cast needed. It works with `List<String>`, `List<Integer>`, etc., without requiring those classes to share a user-defined superclass. The function assumes the list is non-empty; calling it with an empty list throws `IndexOutOfBoundsException`.
2. `Dog extends Animal` establishes an **inheritance** relationship. The assignment `Animal baseRef = firstDog` is a valid upcast because `Dog` is an `Animal`. Generics are not needed to assign a subclass object to a superclass variable.
3. `baseRef.sound()` prints `woof` thanks to **runtime polymorphism**: the variable's static type is `Animal`, but the object was created with `new Dog(...)`; `Dog`'s override executes.
4. `Box<T>` uses **generics** to store and return the same type `T`. `Box<Dog>` is not a subclass of `Box<Animal>`. The call `box.get()` is type-checked to return `Dog` at compile time.
5. `<T extends Animal>` is a **type parameter bound**: `soundOf` can call `animal.sound()` because every valid `T` is a subtype of `Animal`. It leverages the existing inheritance relationship rather than creating a new subclass.
6. `List<? extends Animal>` allows viewing a `List<Dog>` to read elements as `Animal`; the generic method `copy` uses wildcards on source and destination to safely copy objects into `List<Animal>`.

## 3. Important Pitfall: Element Inheritance Does Not Transfer to Lists

Suppose `Dog extends Animal`. The following **does not compile**:

```java
List<Dog> dogs = new ArrayList<>();
List<Animal> animals = dogs; // incompatible types error
```

In Java, ordinary parameterized generic types are **invariant**: `Dog` is a subtype of `Animal`, yet `List<Dog>` is not a subtype of `List<Animal>`. This protects type safety.

Imagine if the assignment above were allowed: through the `animals` variable, the program could add a `Cat` to the `dogs` list; later, `Dog d = dogs.get(0)` could mistakenly receive a `Cat`. The compiler prevents this from the start.

When greater generality is needed, choose a wildcard according to usage direction:

- **Reading:** `List<? extends Animal> view = dogs;`. The variable `view` can read `Animal a = view.get(0)`. You cannot call `view.add(new Dog(...))`: the concrete type behind `?` is unknown (it could actually be `Cat`). Only `null` is an exception for adding.
- **Writing:** `List<? super Dog> target = new ArrayList<Animal>();`. You can call `target.add(new Dog(...))`. When reading from `target`, the only guaranteed general type is `Object`, because the target could be a list of `Dog`, `Animal`, or `Object`.
- **Reading and writing one exact type:** use `List<Dog>` when both directions need to be known precisely.
- **Unknown type:** `List<?>` can be read as `Object` but cannot accept non-null elements. `List<?>` differs from `List<Object>`: a `List<Object>` allows adding `String`, `Dog`, or any `Object` arbitrarily.

The mnemonic **PECS: Producer Extends, Consumer Super**. A source that *supplies* elements uses `? extends T`; a destination that *receives* elements uses `? super T`. This wildcard expresses the container's type range rather than creating a subtype relationship between `List<Dog>` and `List<Animal>`.

## 4. When Do You Need a Bounded Type Parameter vs. Just a Superclass?

Compare these two standalone signatures:

```java
static void printSound(Animal animal) {
    System.out.println(animal.sound());
}

static <T extends Animal> T echoSound(T animal) {
    System.out.println(animal.sound());
    return animal;
}
```

- `printSound(Animal)` is sufficient when only the common `sound()` behavior is needed, with no requirement to preserve the subtype on a return value.
- `echoSound(T)` is valuable because it **links the argument type to the return type**. If you pass a `Dog`, the compiler can infer the result as `Dog`; if replaced with `Animal echoSound(Animal)`, the caller only receives static type `Animal`.
- The bound `T extends Animal` lets the method body use valid members of `Animal`. It does not guarantee that every `Dog`-specific method exists on `T`, since `T` could be a different subtype.

`<T extends Animal>` is a **named type parameter** with an upper bound. `? extends Animal` is an unnamed **wildcard**. Use `T` when you need to express a constraint between two or more positions in an API; use a wildcard when you do not need to refer back to that same unknown type. Do not add `<T>` just to make a method look more generic: `void log(Animal a)` is clearer than `<T extends Animal> void log(T a)` if `T` provides no additional guarantee.

A bound can include multiple contracts, such as `<T extends Animal & Runnable>` (if there is a class bound, that class must precede the interface bounds). Bounds affect compile-time type checking; overridden methods are still dispatched according to the real object at runtime.

## 5. When Type Checking and Behavior Selection Happen

**Generics are primarily a compile-time mechanism.** The compiler checks element types, infers `T`, checks bounds, and verifies assignments. Ordinary Java generics use **type erasure**: an unbounded `T` is typically erased to `Object`, while `T extends Animal` erases to its bound `Animal`. The compiler may insert casts and generate bridge methods when needed to preserve override semantics after erasure. Consequently, two objects `new ArrayList<String>()` and `new ArrayList<Integer>()` are both instances of the runtime class `ArrayList`; they are not two separately “specialized” classes.

**Runtime subtype polymorphism still has actual class information.** When `Animal a = new Dog("Milu")`, the actual object is a `Dog`, so calling an overridden instance method `a.sound()` executes `Dog.sound()`. There is no requirement to store `T = Dog` at runtime to achieve this.

You cannot check `value instanceof List<String>` in Java because the concrete type argument `String` is erased and cannot be tested that way. You can check `value instanceof List<?>`, which only tells you it is a `List`, without concluding that its elements are `String`.

You should also distinguish **overriding** from **overloading**:

- **Overriding**: a subclass or interface implementation provides a new implementation of an instance method with a valid overriding signature; the runtime selects the implementation based on the object.
- **Overloading**: same method name with different parameter lists; overload selection relies on the static types of arguments and compile-time rules, rather than switching to a different overload just because the runtime object is a `Dog`.

Generics can participate in compile-time overload selection, but they **do not replace dynamic dispatch of overridden methods**.

## 6. Choosing Mechanisms in Real-World Design

| Requirement | How to Express It | Why |
|---|---|---|
| A box holding the exact data type chosen by the caller | `Box<T>` | Store/read by `T`, avoiding casts |
| An algorithm returning an element of the same type as the input list | `<T> T first(List<T> xs)` | Preserves type link between parameter and result |
| Multiple species having different sounds | `Animal.sound()` overridden by `Dog`, `Cat` | One common call, different runtime behaviors |
| Multiple classes implementing a unified service | `interface Service`; classes `implements Service` | Polymorphism via a shared contract without forcing a specific superclass |
| A function that only needs to read any subtype of Animal | `List<? extends Animal>` | Accepts `List<Dog>`, `List<Cat>` for reading |
| A function wanting to add Dog into a list capable of holding Dog | `List<? super Dog>` | Ensures write operations are safe |
| A function receiving and returning the exact subtype of Animal | `<T extends Animal> T process(T input)` | Constrains input/output types |

An API can combine all three mechanisms: an interface or superclass expresses the **behavioral contract**; implementations override **specific behaviors**; generics protect the **type relationships** of structures or algorithms. Only add abstractions that genuinely serve the requirement.

## 7. Common Conceptual and Compilation Mistakes

1. **“An `extends` bound means declaring a subclass.”** False. `<T extends Animal>` is a type parameter bound. `class Dog extends Animal` is what creates a class inheritance relationship.
2. **“`Dog extends Animal`, so `List<Dog> extends List<Animal>`.”** False due to type parameter invariance. Solve with wildcards or element-by-element copying via an appropriate API.
3. **“With `List<? extends Animal>`, you can add any `Dog`.”** False because the list's concrete type argument is hidden; the list might be `List<Cat>`.
4. **“Using `Object` is completely equivalent to `<T>`.”** `Object identity(Object x)` loses the concrete type information of the result; `<T> T identity(T x)` lets the compiler preserve the input–output relationship.
5. **“Generics always remain intact at runtime.”** False due to standard erasure. Do not use `instanceof List<String>` to determine element types; check individual elements or design an appropriate type-token mechanism when truly needed.
6. **“Casting or raw types solve every generic issue.”** Raw `List` and unchecked casts weaken compile-time checking and can cause `ClassCastException` later. Prefer accurate generic/wildcard signatures instead of bypassing type checks.
7. **“Java 17 accepts `List<int>` or `new T()`.”** False. Type arguments must be reference types (use `Integer`, with autoboxing); you cannot directly instantiate `new T()` because `T` does not specify a runtime constructor. When creating generic instances is needed, accept a `Supplier<T>` or factory.
8. **“Adding generics automatically gives you runtime polymorphism.”** False. `Box<T>` may not override any method at all. Dynamic dispatch comes from overridden instance methods and the runtime object, not from the name `T`.

## 8. Self-Check Questions with Answers

**Question 1.** `Dog extends Animal`, and variable `Animal a = new Dog("Milu")` calls `a.sound()`. If `Dog` overrides `sound()`, which version runs? **Answer:** `Dog.sound()` thanks to runtime polymorphism.

**Question 2.** Can `List<Dog>` be assigned directly to `List<Animal>`? **Answer:** no; generics are invariant. You can accept the list via `List<? extends Animal>` when you need to read elements as `Animal`.

**Question 3.** What can `<T> T identity(T x)` do that `Object identity(Object x)` cannot? **Answer:** it preserves the static type of the return value based on the argument, avoiding casts at the call site.

**Question 4.** A parameter `List<? super Dog>` allows adding `Dog`; why does reading elements only guarantee `Object`? **Answer:** the concrete type could be `Dog`, `Animal`, or `Object`, and nothing more specific is known.

**Question 5.** Does a function that only prints `animal.sound()` require `<T extends Animal>`? **Answer:** no; `void printSound(Animal animal)` is enough if you do not need to preserve type `T` elsewhere.

**Question 6.** Is `Box<Dog>` a subtype of `Box<Animal>`? **Answer:** no, unless the `Box` type itself has another explicitly defined subtype relationship; generic instantiations do not inherit from one another automatically.

When facing a new problem, ask yourself: **Which contract do the objects share?** → superclass/interface. **How do they implement behaviors differently?** → overriding and runtime polymorphism. **Which type relationships must a structure or algorithm preserve?** → generics, bounds, and wildcards. Distinguishing those three questions is the foundation for writing safe, easy-to-use Java APIs.