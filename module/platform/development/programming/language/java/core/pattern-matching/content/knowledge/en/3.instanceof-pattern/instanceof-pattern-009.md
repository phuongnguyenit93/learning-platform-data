# `instanceof` with Subtypes and Supertypes in Java

## 1. Understanding the Question: Which Type Is Checked?

In Java, `instanceof` checks whether the **actual runtime object** is compatible with a given reference type. An object of a subclass is also an object of every superclass in its inheritance chain. Therefore, a `Dog` object typically satisfies both `instanceof Dog` and `instanceof Animal` if `Dog extends Animal`.

There are two concepts to distinguish:

- **Declared type (static/compile-time type):** the type of the variable in the source code, for example `Animal animal`. The compiler uses this type to check syntax, method invocation permissions, and the validity of the check.
- **Actual type (runtime type):** the class of the object created by `new`, for example `Dog` in the statement `Animal animal = new Dog("Milo");`. This is the basis for determining the result of `instanceof` at runtime.

For example, with the following classes:

```text
Animal
├── Dog
│   └── Puppy
└── Cat
```

`Dog` and `Cat` are two sibling subclasses; `Puppy` indirectly inherits from `Animal` through `Dog`. The "is-a" (IS-A) relationship is transitive: **Puppy is a Dog, Dog is an Animal, so Puppy is also an Animal**.

```java
Animal pet = new Dog("Milo");  // Upcasting: Dog -> Animal

System.out.println(pet instanceof Animal); // true
System.out.println(pet instanceof Dog);    // true
System.out.println(pet instanceof Cat);    // false
```

The three expressions above check the **same `Dog` object**. Declaring the `pet` variable with type `Animal` does not turn the object into a plain `Animal`, nor does it erase its subclass type information.

## 2. Rules with Parent, Child, Grandchild, and Sibling Classes

Suppose:

```java
class Animal {}
class Dog extends Animal {}
class Puppy extends Dog {}
class Cat extends Animal {}
```

The following table illustrates valid checks on a **variable with static type `Animal`**:

| Object referenced by `Animal a` | `a instanceof Animal` | `a instanceof Dog` | `a instanceof Puppy` | `a instanceof Cat` |
| --- | --- | --- | --- | --- |
| `new Animal()` | `true` | `false` | `false` | `false` |
| `new Dog()` | `true` | `true` | `false` | `false` |
| `new Puppy()` | `true` | `true` | `true` | `false` |
| `new Cat()` | `true` | `false` | `false` | `true` |
| `null` | `false` | `false` | `false` | `false` |

**Checking from subtype to supertype:** if a variable references a non-`null` `Dog` object, `instanceof Animal` evaluates to `true`, because the subclass object carries the full inheritance relationship to its superclass. This still holds when the variable is declared as `Dog` or `Object` and the check is accepted by the compiler.

**Checking from supertype to subtype:** a variable declared with type `Animal` *may* reference a `Dog`, `Puppy`, `Cat`, or plain `Animal`. Therefore, `animal instanceof Dog` can be `true` or `false` depending on the actual object. A variable of a supertype does not guarantee that it holds an object of a specific subclass.

**Checking between sibling classes:** a `Cat` object is not automatically a `Dog` just because both classes share the superclass `Animal`. If the expression has static type `Animal`, the check `animal instanceof Dog` is completely valid and returns `false` when the actual object is a `Cat`.

**The `null` case:** `null instanceof Animal`, `null instanceof Dog`, and any other `instanceof` check against a reference type all evaluate to `false`. `null` can be assigned to a class-typed variable, but it is not itself an object created from that class.

## 3. Standalone Runnable Java 17+ Example

Save the entire program to a file named `InstanceofInheritanceDemo.java`:

```java
public class InstanceofInheritanceDemo {
    static class Animal {
        final String name;

        Animal(String name) {
            this.name = name;
        }

        String describe() {
            return "Animal " + name;
        }
    }

    static class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        String describe() {
            return "Dog " + name;
        }

        String play() {
            return name + " fetches";
        }
    }

    static class Puppy extends Dog {
        Puppy(String name) {
            super(name);
        }
    }

    static class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    static void inspect(Animal animal) {
        String id = animal == null ? "null" : animal.name;

        System.out.println(
            id
                + ": Animal=" + (animal instanceof Animal)
                + ", Dog=" + (animal instanceof Dog)
                + ", Cat=" + (animal instanceof Cat)
        );

        if (animal instanceof Dog dog) {
            System.out.println("  " + dog.play());
        }
    }

    public static void main(String[] args) {
        inspect(new Dog("Milo"));
        inspect(new Animal("Base"));
        inspect(new Puppy("Nho"));
        inspect(new Cat("Mimi"));
        inspect(null);

        Animal x = new Dog("Milo");
        System.out.println("Describe: " + x.describe());
    }
}
```

Compile and run from the directory containing the file using JDK 17 or newer:

```bash
javac --release 17 InstanceofInheritanceDemo.java
java InstanceofInheritanceDemo
```

Output:

```text
Milo: Animal=true, Dog=true, Cat=false
  Milo fetches
Base: Animal=true, Dog=false, Cat=false
Nho: Animal=true, Dog=true, Cat=false
  Nho fetches
Mimi: Animal=true, Dog=false, Cat=true
null: Animal=false, Dog=false, Cat=false
Describe: Dog Milo
```

Explanation of each case:

1. **`Milo`:** the `Animal` reference points to a `Dog`. It matches the `Dog` and `Animal` patterns, but not `Cat`. The pattern variable `dog` is initialized and allows calling `play()`.
2. **`Base`:** the actual object was created from `Animal`. Being an `Animal` does not mean being a `Dog`, so only the check against the parent class is `true`.
3. **`Nho`:** the `Puppy` object inherits from `Dog`, so `instanceof Dog` is `true`, even though it was not created directly with `new Dog(...)`. The branch calling `play()` still executes because the method is inherited.
4. **`Mimi`:** the `Cat` object is an `Animal`, but not a `Dog`.
5. **`null`:** all type checks here return `false`.
6. **`Describe: Dog Milo`:** the variable `x` is declared as `Animal`, but the overridden method `describe()` is resolved according to the actual runtime type `Dog`. That is **runtime polymorphism (dynamic dispatch)**; this result is consistent with `x instanceof Dog` being `true`.

The `Animal`, `Dog`, `Puppy`, and `Cat` declarations in the short examples below can be understood as the corresponding classes in this program; those short snippets are only meant to illustrate a single rule and are not complete standalone files.

## 4. Upcasting Does Not Lose the Actual Type

**Upcasting** is assigning a reference of a subclass object to a superclass variable. Java performs this automatically because every `Dog` is an `Animal`:

```java
Dog dog = new Dog("Milo");
Animal animal = dog;   // Valid, no cast needed
Object object = dog;   // Valid because Java classes inherit from Object

System.out.println(animal instanceof Dog); // true
System.out.println(object instanceof Dog); // true
```

All three variables can point to the **exact same object**. `animal` only sees the members accessible through the `Animal` type at compile time; however, Java still knows the actual object is a `Dog`. Therefore, the following snippet does not compile:

```java
Animal animal = new Dog("Milo");
animal.play(); // Compile error: Animal does not declare play()
```

To use `Dog`-specific behavior, you need to check the type and narrow the reference safely.

## 5. Downcasting: Check Before Casting

**Downcasting** converts a reference whose static type is a supertype to a subtype. It only succeeds when the actual object is compatible with the requested subtype.

Traditional approach:

```java
Animal animal = new Dog("Milo");

if (animal instanceof Dog) {
    Dog dog = (Dog) animal; // Safe after check
    System.out.println(dog.play());
}
```

If you skip the check and cast a plain `Animal` or a `Cat` to `Dog`, the runtime throws `ClassCastException`:

```java
Animal animal = new Cat("Mimi");
Dog dog = (Dog) animal; // ClassCastException
```

Even though both `Dog` and `Cat` inherit from `Animal`, that does not make converting a `Cat` object to `Dog` valid. A cast **does not transform the object** into a new object: it asks the runtime to verify that the object is already compatible with the target type.

### Using Type Patterns Since Java 16 (Standardized in Java 17)

```java
Animal animal = new Dog("Milo");

if (animal instanceof Dog dog) {
    System.out.println(dog.play());
}
```

`instanceof Dog dog` both checks the type and declares and initializes the pattern variable `dog` when the object matches. Inside the matching branch, `dog` has type `Dog`, so `play()` can be called without writing `(Dog) animal`.

A pattern variable can only be used on paths where the compiler guarantees the pattern matched:

```java
static void process(Animal animal) {
    if (!(animal instanceof Dog dog)) {
        return;
    }

    System.out.println(dog.play()); // Valid after guard return
}
```

If `animal` is a `Cat`, a plain `Animal`, or `null`, the negated condition is `true` and the method returns early; only `Dog` objects (including `Puppy`) reach the line calling `play()`.

You can safely combine additional checks with `&&`:

```java
if (animal instanceof Dog dog && dog.name.startsWith("M")) {
    System.out.println(dog.play());
}
```

The right-hand side of `&&` is only evaluated when the pattern on the left-hand side matches, so `dog` already has a value. Conversely, writing `animal instanceof Dog dog || dog.name.startsWith("M")` is invalid: the right-hand side of `||` is only evaluated when the left-hand pattern does not match.

## 6. Static Type Determines Which `instanceof` Checks Are Valid at Compile Time

The `true`/`false` result depends on the runtime type, but **not every comparison is allowed by the compiler**. The compiler uses the static type and the inheritance hierarchy to reject checks that can never succeed.

With two sibling classes `Dog` and `Cat`:

```java
Dog dog = new Dog("Milo");

// Invalid: a Dog cannot simultaneously be a Cat
// System.out.println(dog instanceof Cat);
```

In this example, Java knows an object of type `Dog` cannot be an instance of `Cat`, because the two classes lie on different branches of the inheritance tree (with no parent-child relationship). This incompatible type check is rejected at compile time.

When replaced with a supertype variable, the check becomes valid:

```java
Animal animal = new Dog("Milo");
System.out.println(animal instanceof Cat); // false
```

The static type `Animal` allows the variable to reference a `Cat` in other assignments, so this is a meaningful check at runtime. However, in this specific run the variable points to a `Dog`, so the result is `false`.

It is also important to distinguish between **traditional type checks** and **type patterns**. In Java 17, a type pattern that is provably always true based solely on static type relationships is considered redundant and results in a compile error. For example:

```java
Dog directDog = new Dog("Milo");

System.out.println(directDog instanceof Animal); // Valid: true

// In Java 17, the type pattern below is rejected as a redundant check:
// if (directDog instanceof Animal parent) {
//     System.out.println(parent.name);
// }
```

Version note: the exact rules for *unconditional patterns* changed in newer Java versions. This distinction is especially important when compiling with `javac --release 17`. The clearest approach is to use direct upcasting if you already know the variable is a `Dog`, and only use `instanceof` when you need to branch on the actual runtime type.

## 7. Comparison with `getClass()` and the `==` Operator

`instanceof` checks **type compatibility**, including multi-level subclasses. `getClass()` returns the **exact runtime class**, so class comparison expressions have a different meaning:

```java
Animal a = new Puppy("Nho");

System.out.println(a instanceof Animal);       // true
System.out.println(a instanceof Dog);          // true
System.out.println(a instanceof Puppy);        // true
System.out.println(a.getClass() == Dog.class);  // false
System.out.println(a.getClass() == Puppy.class);// true
```

`Puppy` is a `Dog` by inheritance, but its *exact* runtime class is not `Dog`. Use `getClass() == Dog.class` when you require only objects of the exact class `Dog`, excluding subclasses. `getClass()` throws `NullPointerException` if called on a `null` reference, whereas `null instanceof Dog` evaluates to `false`.

**Do not use `==` between two references to check a parent–child relationship:** for example, `animal == dog` only checks whether they refer to the same object instance, not the type of the object.

## 8. Relationship with Interfaces and Inheritance Hierarchies

`instanceof` is not limited to direct superclasses/subclasses. It also supports interfaces: a `Dog` object can be both an `Animal` through class inheritance and a `Trainable` through interface implementation.

Standalone example illustrating an interface:

```java
interface Trainable {
    void train();
}

class Animal {}

class Dog extends Animal implements Trainable {
    @Override
    public void train() {
        System.out.println("Dog training");
    }
}
```

With these types:

```java
Animal animal = new Dog();

System.out.println(animal instanceof Animal);     // true
System.out.println(animal instanceof Dog);        // true
System.out.println(animal instanceof Trainable);  // true
```

The static type `Animal` does not need to declare `implements Trainable` itself. The actual `Dog` object implements the interface, so the expression still returns `true`. This is an appropriate check when you need to handle a specific **capability** represented by an interface.

An object can also implement multiple interfaces; `instanceof` checks for each interface are independent of the class inheritance hierarchy. Since Java supports single class inheritance but multiple interface implementation, this is useful when an object provides multiple roles.

## 9. When to Use `instanceof`, and When to Use Polymorphism?

If the goal is to invoke a behavior that **every subclass must have**, consider declaring that behavior in the superclass and having subclasses override it:

```java
Animal animal = new Dog("Milo");
System.out.println(animal.describe()); // Dog Milo
```

This is polymorphism: you do not need to check every subclass to call `describe()`. On the other hand, when handling an operation **specific to a subclass** (such as `Dog`'s `play()`), checking `instanceof Dog dog` can make sense.

A method that chains `instanceof Dog`, `instanceof Cat`, `instanceof Bird` to do all the work is often a sign to revisit the design: if the behavior is a shared responsibility, consider turning it into a polymorphic method or an interface. Conversely, at boundaries receiving general-typed data (`Object`), before a cast, or when adapting to an existing API, `instanceof` is the right tool.

**Preserve the principle:** check against the type that represents the *actual need* of the branch. If you only need `Trainable` behavior, checking `instanceof Trainable` is usually more flexible than listing a concrete subclass.

## 10. Common Mistakes

1. **"If a variable is declared as `Animal`, `instanceof Dog` is always false."** False: if the variable holds a `Dog` or `Puppy` object, the `Dog` check is `true`.
2. **"A superclass object is always a subclass."** False: `new Animal() instanceof Dog` is `false`. The IS-A relationship goes from subclass to superclass, not automatically in reverse.
3. **"Two classes with the same parent are the same type."** False: `Dog` and `Cat` have no inheritance relationship with each other. Static typing may even forbid checking between these two classes at compile time.
4. **"Casting turns a `Cat` into a `Dog`."** False: casting does not change the object. Casting to an incompatible type can throw `ClassCastException`.
5. **"`instanceof` checks for an exact class."** False: it also accepts subclasses; for example, `new Puppy() instanceof Dog` is `true`. To check the exact class, use `getClass()`, handling `null`.
6. **"A `null` reference belongs to its declared class."** False: `Animal a = null; a instanceof Animal` evaluates to `false`.
7. **"A pattern variable can be used in every branch."** False: it can only be used where the compiler proves the pattern has matched. Do not use a pattern variable in a failing branch or on the right-hand side of `||` without a match guarantee.
8. **"`instanceof` replaces all polymorphism."** Not recommended: if you only need to call a common superclass method, dynamic dispatch usually makes code shorter and easier to extend.

## 11. Quick Self-Check

Given the inheritance hierarchy `Animal <- Dog <- Puppy` and `Cat extends Animal`:

**Question 1.** `Animal a = new Puppy();`. What are the results of `a instanceof Animal`, `a instanceof Dog`, `a instanceof Puppy`, and `a instanceof Cat`?

Answer: `true`, `true`, `true`, `false`, respectively. The grandchild object retains its relationship with both parent and grandparent, but does not belong to the `Cat` branch.

**Question 2.** `Animal a = new Cat();`. Can you write `(Dog) a` and have it run successfully?

Answer: the cast may be syntactically valid because static type `Animal` can hold a `Dog`, but at runtime it will throw `ClassCastException`, since the actual object is a `Cat`. You must check `a instanceof Dog` first.

**Question 3.** `Animal a = null;`. Do you need to check `a != null` before `a instanceof Dog` to avoid an error?

Answer: no. `instanceof` with `null` automatically returns `false`. However, if you call `a.getClass()`, you must check for `null` first.

**Question 4.** `Animal a = new Puppy();`. Why is `a instanceof Dog` true while `a.getClass() == Dog.class` is false?

Answer: the first checks the inheritance relationship, while the second requires the exact runtime class to be `Dog`; here, the runtime class is `Puppy`.

**Question 5.** Can you call `a.play()` if `a` is declared as `Animal` and actually points to a `Dog`?

Answer: you cannot call it directly when `Animal` does not declare `play()`. Use `if (a instanceof Dog dog) { dog.play(); }` so the compiler can safely determine the `Dog` type.

### Key Takeaways

- **Child → parent:** a non-`null` subclass object is always compatible with supertypes in its inheritance chain.
- **Parent → child:** a variable declared as a supertype matches a subtype only when the **actual object** belongs to that subtype (or a descendant of it).
- **Sibling classes:** sharing a parent does not mean classes are types of each other.
- **`null`:** all reference-type `instanceof` checks above evaluate to `false`.
- **Pattern matching:** `instanceof Dog dog` both checks the type and lets you use the `Dog` variable safely in the matching branch.

### Official Documentation

- [JLS Java SE 17, §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JLS Java SE 17, §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
