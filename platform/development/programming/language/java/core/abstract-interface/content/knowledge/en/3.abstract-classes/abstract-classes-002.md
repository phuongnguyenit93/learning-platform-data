# Why Can't an Abstract Class Be Instantiated Directly in Java?

## 1. Direct Answer

In Java, a class declared with the `abstract` keyword **cannot be used directly on the right-hand side of `new`**. For example, if `Animal` is an abstract class, then `new Animal()` causes a **compilation error**, even if that class has a constructor and even if that class does not declare any `abstract` methods.

The reason lies in **the contract of the type**: an abstract class describes a general type intended for subclasses to inherit from and complete its behavior. An abstract class may contain methods without a body, so Java does not allow creating an object of that class itself directly. This rule is checked based on the `abstract` declaration, rather than depending on how many abstract methods a particular class has.

To obtain an object, create **a concrete subclass** that fulfills all the missing abstract methods. A reference variable can still have the abstract class type:

```java
Animal pet = new Cat("Mimi"); // Valid if Cat is a concrete subclass of Animal
// Animal pet = new Animal("Mimi"); // Invalid: Animal is abstract
```

On the valid line, **the declared type of the variable** is `Animal`, but **the actual object created** has type `Cat`.

## 2. What Happens When Using `new` with an Abstract Class?

Suppose we have a general template for animals:

```java
abstract class Animal {
    abstract String sound();
}

class InvalidExample {
    void demo() {
        Animal a = new Animal(); // Compilation error
    }
}
```

If you save the code above as `InvalidExample.java` and run `javac InvalidExample.java`, the compiler rejects the expression `new Animal()` and reports a message to the effect of: `Animal is abstract; cannot be instantiated`.

Here, `sound()` only states **the required behavior** without specifying **concrete behavior**. If `new Animal()` were allowed, there would be no implementation of `sound()` for an object belonging to the `Animal` class itself. Therefore, the design requires the program to provide a complete subclass before creating an object.

Two levels must be distinguished:

- **The cause in the example:** `Animal` has not implemented `sound()`.
- **The rule of the language:** any class declared `abstract` cannot be instantiated directly, even when all methods already have bodies.

This is a **compile-time error** when `new Animal()` is written directly; the program does not need to execute up to that line for the error to be detected.

## 3. An Abstract Class Does Not Necessarily Have Abstract Methods

A common point of confusion is that the `abstract` keyword by itself is enough to prohibit direct instantiation:

```java
abstract class BaseConfiguration {
    String environment() {
        return "production";
    }
}

class InvalidExample {
    void demo() {
        BaseConfiguration config = new BaseConfiguration(); // Still a compilation error
    }
}
```

`BaseConfiguration` has no abstract methods; however, the designer still intends for it to serve as **a base class for extension**, not a type to be created independently. The `abstract` declaration expresses this intent, and the compiler enforces the rule accordingly.

Conversely, a class **not declared `abstract`** must not leave any abstract methods unimplemented (whether directly or inherited). If any required behavior remains incomplete, the subclass must also continue to be declared `abstract`.

## 4. The Right Way: Instantiate a Concrete Subclass

The following example is a standalone Java program that runs on Java 17 or later. The `Animal` class defines the `sound()` contract; the `Cat` class implements that contract.

**File `Main.java`:**

```java
abstract class Animal {
    private final String name;

    protected Animal(String name) {
        this.name = name;
        System.out.println("Animal constructor: " + name);
    }

    protected abstract String sound();

    public String introduce() {
        return name + " says " + sound();
    }
}

final class Cat extends Animal {
    Cat(String name) {
        super(name);
    }

    @Override
    protected String sound() {
        return "meow";
    }
}

public class Main {
    public static void main(String[] args) {
        Animal pet = new Cat("Mimi");

        System.out.println(pet.introduce());
        System.out.println(pet instanceof Cat);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Expected output on stdout:**

```text
Animal constructor: Mimi
Mimi says meow
true
```

Point-by-point breakdown:

1. `new Cat("Mimi")` creates **a `Cat` object**, because `Cat` is not abstract and has implemented `sound()`.
2. `Animal pet` is completely valid: a parent-type reference can point to a subclass object (polymorphism).
3. The call `pet.introduce()` invokes the method inherited from `Animal`; the `sound()` call inside is dispatched to `Cat`'s version, returning `"meow"`.
4. The `Animal(String)` constructor still runs via `super(name)` when instantiating `Cat`. The first line on stdout proves this.
5. `pet instanceof Cat` returns `true` because the actual type of the object is `Cat`.

If you remove the implementation of `sound()` in `Cat` while keeping `Cat` as a concrete class, the program will not compile. In that case, you must either implement `sound()` or declare `Cat` as `abstract` and leave it for a later subclass to complete.

## 5. Why Do Abstract Classes Still Have Constructors?

An abstract class's constructor initializes the state shared by all subclasses. When creating `new Cat("Mimi")`, Java calls the `Animal` constructor via `super(name)`; that does not mean a separate `Animal` object is created, nor does it make `new Animal(...)` valid.

Constructors are not inherited and cannot be declared `abstract`. If the superclass only has parameterized constructors, the subclass constructor must call a matching constructor using `super(...)`; otherwise, the implicit `super()` call can cause a compilation error. The rules for choosing access modifiers, `this(...)`/`super(...)` chaining, and initialization order are covered in full in the lesson on constructors.

## 6. Why Can the Syntax `new Animal() { ... }` Be Valid?

The syntax with curly braces after `new` creates **an anonymous subclass**. It does not create an object belonging directly to the `abstract` class.

**Another standalone example, saved as `Main.java`:**

```java
abstract class Action {
    abstract String execute();
}

public class Main {
    public static void main(String[] args) {
        Action action = new Action() {
            @Override
            String execute() {
                return "Action completed";
            }
        };

        System.out.println(action.execute());
    }
}
```

Running `javac -encoding UTF-8 Main.java` and then `java Main` will print:

```text
Action completed
```

The expression `new Action() { ... }` declares an anonymous subclass extending `Action` inline, implements `execute()`, and then creates an object of that **anonymous subclass**. If the missing abstract methods are not fully implemented, this expression will not compile either.

Therefore, the two expressions look similar but have different meanings:

| Expression | Result | Explanation |
| --- | --- | --- |
| `new Action()` | Compilation error | Attempts to instantiate the abstract class directly |
| `new Action() { /* cài đặt đầy đủ */ }` | Valid | Creates a concrete anonymous subclass and instantiates it |
| `new ConcreteAction()` | Valid if the subclass is concrete and the constructor is accessible | Creates an object of a named subclass |

An anonymous subclass is useful for a short implementation in one place. When the behavior is large, needs to be reused, or has many dependencies, a named subclass is usually easier to read and test.

## 7. Design Mechanism and Cases to Distinguish

**An abstract class is a type that can be used in declarations, but not as a target for direct instantiation.** Java allows using an abstract class as the type of variables, parameters, return types, fields, and array elements. For example, a method can accept `Animal` to handle any subclass without depending on `Cat`, `Dog`, or any specific implementation.

Several cases often cause confusion:

| Scenario | Valid? | Reason |
| --- | --- | --- |
| `Animal a;` | Yes | Only declares a reference; no object has been created yet |
| `Animal a = null;` | Yes | `null` is not an object of the abstract class |
| `Animal a = new Cat("Mimi");` | Yes | The created object belongs to a concrete subclass |
| `Animal[] animals = new Animal[3];` | Yes | Creates an **array holding references** of type `Animal`, not three `Animal` objects |
| `new Animal("Mimi")` | No | Directly instantiates a class declared `abstract` |
| `new Cat("Mimi")` when `Cat` has not implemented all abstract methods | No, if `Cat` is forced to be an abstract class | The subclass does not yet meet the requirements to be instantiated |

You can think of an abstract class as a **contract accompanied by a shared implementation**. The contract specifies what behaviors every concrete subclass must provide; the shared implementation avoids code duplication. Actual objects have the types of the subclasses that fulfill the contract.

Abstractness can also be used to **prevent instantiating the base class** even when all behaviors have already been implemented. Therefore, the explanation “because there are still methods without a body” states a common motivation, but **is not a necessary condition** for a class to be declared `abstract`.

### Common Mistakes

- **Confusing “cannot create an object” with “cannot declare a variable”.** `Animal pet` is valid; it is `new Animal()` specifically that is prohibited.
- **Assuming adding a public constructor will allow `new`.** Constructor accessibility and the `abstract` rule are two separate checks; a `public` constructor does not turn an abstract class into a concrete class.
- **Assuming every subclass can be instantiated.** Only a concrete subclass that has fulfilled the entire abstract contract and has a suitable constructor can be instantiated.
- **Assuming an abstract superclass has no constructor.** The superclass constructor is still called during subclass object creation.
- **Assuming `new AbstractType() { ... }` breaks the rule.** This is a way to define and create a concrete anonymous subclass; the superclass is still not instantiated directly.
- **Assuming a class is only abstract when it has `abstract` methods.** An author can mark a class `abstract` to dictate how it is used, regardless of whether that class has abstract methods or not.

## 8. How to Self-Check When Encountering the Error

When you see an error similar to `SomeType is abstract; cannot be instantiated`, check the following in order:

1. **What is the type immediately after `new`?** If it is an `abstract` class or an interface, you cannot use `new SomeType()` directly.
2. **Is there already a suitable concrete subclass?** If so, use `new ConcreteSubtype(...)` and keep a reference variable of the parent type if polymorphism is needed.
3. **Has the subclass implemented all abstract methods?** Check methods inherited from both the superclass and interfaces, method signatures, return types, and access levels when overriding.
4. **Can the subclass constructor call a superclass constructor?** If the superclass requires parameters, pass them via `super(...)`.
5. **Do you only need a short inline implementation?** Consider an anonymous subclass, though you still must implement all abstract behavior.

**Remember:** `abstract` describes a parent type and specifies that this type must not be instantiated directly. An object must belong to a concrete subclass; the abstract class's constructors and shared methods still play their full role during initialization and execution.
