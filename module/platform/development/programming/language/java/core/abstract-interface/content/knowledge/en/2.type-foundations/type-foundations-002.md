# Supertype and Subtype Relationships in Java

In Java, a **subtype** can be used wherever an API requires a supertype. This relationship forms the foundation for polymorphism and flexible API design. You need to distinguish a type relationship from an inheritance relationship between two classes: an interface can also be a supertype even though it is not a superclass.

## 1. How does a subclass differ from a subtype?

Suppose `Dog extends Animal`:

- `Dog` is a **subclass** of `Animal`; `Animal` is the superclass.
- `Dog` is also a **subtype** of `Animal`; `Animal` is the supertype.
- If `Animal implements CanMove`, then `Dog` is also a subtype of `CanMove` through the inheritance relationship. `CanMove` does not become a superclass of `Dog`.
- The subtype relationship is transitive: if `Poodle extends Dog` and `Dog extends Animal`, then `Poodle` is a subtype of `Animal`.

A class that does not directly declare `extends` has `Object` as its superclass (except `Object` itself). An interface is not a subclass of `Object`, but an object of a class implementing an interface can still be assigned to an `Object` variable. Primitive types such as `int` do not belong to the class/interface hierarchy; boxing is a separate conversion mechanism.

**“Is-a” and “has-a” answer two different questions.** `Dog extends Animal` expresses that Dog is an Animal. `Car` holding the field `Engine engine` expresses that Car has an Engine; it does not make `Car` a subtype of `Engine`. Only use inheritance when the public behavior of the supertype still holds true for the subtype.

## 2. Declarations that create type relationships

| Declaration | Relationship | Key Limitation |
|---|---|---|
| `class Dog extends Animal` | `Dog` is a subtype of `Animal`. | A class has only one direct superclass. |
| `class Dog implements CanMove, Named` | `Dog` is a subtype of both interfaces. | A concrete class must satisfy any missing abstract methods. |
| `interface Smart extends CanMove, Named` | `Smart` inherits the contracts of multiple interfaces. | An interface uses `extends`, not `implements`. |
| `abstract class Animal implements CanMove` | `Animal` is a subtype of `CanMove`. | Because `Animal` is abstract, it can pass implementation obligations on to its subclasses. |
| `final class Dog extends Animal` | Still a subtype of `Animal`. | `final` prevents creating new subclasses of `Dog`. |

In Java 17+, a `sealed` class/interface can restrict the direct subtypes permitted to be declared. Those restrictions do not change the fundamental meaning of the subtype relationship.

## 3. Runnable example: multiple subtypes, one contract

Save the entire code below as `TypeRelationDemo.java`:

```java
public class TypeRelationDemo {
    interface CanMove {
        void move();
    }

    static abstract class Animal implements CanMove {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        abstract String sound();

        @Override
        public void move() {
            System.out.println(name + " moves");
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

        void fetch() {
            System.out.println(name() + " fetches");
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "meow";
        }
    }

    static void describe(Animal animal) {
        System.out.println(animal.name() + ": " + animal.sound());
    }

    public static void main(String[] args) {
        Dog rex = new Dog("Rex");

        Animal animal = rex;
        CanMove mover = rex;
        Object any = rex;

        describe(animal);
        mover.move();
        System.out.println(animal instanceof Dog);

        if (animal instanceof Dog dog) {
            dog.fetch();
        }

        Animal other = new Cat("Mimi");
        describe(other);
        System.out.println(any.getClass().getSimpleName());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac TypeRelationDemo.java
java TypeRelationDemo
```

Stdout:

```text
Rex: woof
Rex moves
true
Rex fetches
Mimi: meow
Dog
```

`animal`, `mover`, and `any` all reference the same `Dog` object; upcasting does not copy the object. `describe(Animal)` works with both `Dog` and `Cat`. The `animal` variable does not expose the `fetch()` method, so a type check is needed before using `Dog`'s specific capability. Detailed resolution between declared type, runtime class, overloads, and fields is explained in the article **Reference Type and Actual Type of an Object**.

## 4. Type compatibility and behavioral substitutability

Assigning a `Dog` to an `Animal` or `CanMove` variable is implicit **upcasting** enabled by the subtype relationship; the variables still reference the same object. The opposite direction is **downcasting**: the expression type becomes narrower, but the object does not change. You must check the actual type, such as `candidate instanceof Dog dog`, before calling `dog.fetch()` when you are not sure `candidate` is a `Dog`; an invalid cast can throw a `ClassCastException`. `instanceof` returns `false` for `null`.

**The compiler accepting an assignment does not guarantee behavioral substitutability.** According to the Liskov Substitution Principle (LSP), a program using a supertype must continue to behave according to the supertype's guarantees when given a subtype. A subclass should not tighten input conditions already accepted by the parent, break invariants, or reject operations guaranteed by the parent's contract. If `CanMove.move()` promises valid movement, an implementation that always throws `UnsupportedOperationException` violates that expectation. Only let objects that are genuinely capable of moving implement `CanMove`.

Therefore, you need to check **two levels**: the subtype relationship at the language level, and the ability to uphold the contract at the design and testing levels.

## 5. Subtyping does not automatically carry over through generics

Having `Dog extends Animal` does **not** mean `List<Dog>` is a subtype of `List<Animal>`. Java generics are generally invariant:

```java
java.util.List<Dog> dogs = java.util.List.of(new Dog("Rex"));
// java.util.List<Animal> animals = dogs; // Compile error

java.util.List<? extends Animal> view = dogs;
Animal first = view.get(0); // Safe to read as Animal
// view.add(new Dog("Max")); // Cannot arbitrarily add a Dog
```

`? extends Animal` allows reading elements as `Animal`, but the actual subtype of the list is unknown; it could be `List<Cat>`. When an API needs to **consume** `Dog` values, `? super Dog` may be more appropriate. Choose the wildcard according to the input/output data direction instead of trying to force two `List` types to be the same type.

Java arrays are covariant, but element writes are checked at runtime:

```java
Animal[] animals = new Dog[1];  // Valid at compile time
animals[0] = new Cat("Mimi");  // ArrayStoreException at runtime
```

Therefore, the relationships between element types, container types, and runtime safety are separate concerns. Do not infer from `Dog <: Animal` that every structure containing `Dog` can be assigned to a structure containing `Animal`.

## 6. Choosing a supertype for an API

Prefer the smallest abstract type that meets the caller's needs:

- Use `CanMove` if the function only needs to call `move()`, so that `Animal`, `Robot`, or classes not in the same inheritance hierarchy can all participate.
- Use `Animal` when you genuinely need the shared properties/behaviors of the animal family.
- Use a concrete class like `Dog` only when the business logic requires specific capabilities such as `fetch()`.

Composition is appropriate when the relationship is “has-a” or “delegates-to”, such as `Car` containing `Engine`. Inheritance is appropriate when an “is-a” relationship makes sense and the subtype upholds the supertype's contract. You should not inherit just to get a utility method.

## 7. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| An implemented interface is a superclass. | It is a supertype, whereas a superclass is only a class in the `extends` branch. |
| Two classes with the same superclass can be directly assigned to each other. | `Dog` and `Cat` are both `Animal`, but neither is a subtype of the other. |
| Upcasting creates a new superclass object. | Variables after upcasting can all reference the same original instance. |
| `instanceof` replaces polymorphism. | Overriding uses automatic dispatch; `instanceof` is a type check when branching is needed. |
| `List<Dog>` can be used like `List<Animal>`. | Generics are invariant; use the appropriate wildcard. |
| Syntactic inheritance is enough to prove a design is correct. | A subtype must also uphold the behavioral guarantees of its supertype. |

## 8. Self-check

1. If `Dog extends Animal` and `Animal implements CanMove`, can `Dog` be assigned to `CanMove`? **Yes**, because the subtype relationship is transitive.
2. `Dog` and `Cat` both inherit from `Animal`; can a `Dog` be directly assigned to a `Cat` variable? **No**, the two branches do not have that subtype relationship.
3. Why can't `List<Dog>` be assigned to `List<Animal>`? **Because generics are invariant**; if it were allowed, code could add a `Cat` to a list that only accepts `Dog`.
4. When is composition more appropriate than `extends`? When an object has or delegates to a component without actually being a subtype of it.

**Remember:** the subtype relationship answers “can this value be used where that other type is required?”. Class inheritance and interface implementation can establish that relationship, but a good API also requires a sound behavioral contract and parameter types that do not overly constrain callers.
