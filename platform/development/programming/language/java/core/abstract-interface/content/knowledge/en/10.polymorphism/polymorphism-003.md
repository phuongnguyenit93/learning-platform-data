# Methods Allowed to Be Called Based on Declared Type in Java

## 1. Core Rule of Polymorphism

In Java, a reference variable always has a **declared type** (also called static type or compile-time type), and at runtime that variable can point to an object of an **actual type** (runtime class) that is a compatible subclass or implementing class.

Example:

```java
Animal animal = new Dog();
```

- `Animal` is the **declared type** of the reference expression `animal`.
- `Dog` is the **actual class** of the object created by `new Dog()`.
- When you write `animal.someMethod()`, **the compiler first checks whether the method can be called through the `Animal` type**, including the name, parameter list, access scope, and calling context.
- Once the call is valid, if it is an **overridable instance method**, the JVM selects the implementation to run based on the actual object type (`Dog`), following dynamic dispatch rules.

Therefore, two questions must be separated:

1. **Which calls are allowed to be written?** Decided primarily at compile time based on the **declared type of the receiver expression**.
2. **Which method body does that call execute?** For an overridden instance method, decided at runtime based on the **actual object**.

A `Dog` object does not lose its own behaviors just because it is assigned to an `Animal` variable. However, the compiler only allows calling behaviors that `Animal` exposes and that are accessible in the current context, unless a valid type-narrowing mechanism is used.

## 2. Complete Example: What Can Be Called Through a Supertype Variable?

Create the following `Main.java` file (Java 17+):

```java
abstract class Animal {
    public void eat() {
        System.out.println("Animal eats");
    }

    public abstract void speak();

    public String description() {
        return "Animal";
    }
}

final class Dog extends Animal {
    @Override
    public void speak() {
        System.out.println("Woof");
    }

    @Override
    public String description() {
        return "Dog";
    }

    public void fetch() {
        System.out.println("Fetching");
    }
}

public class Main {
    public static void main(String[] args) {
        Animal animal = new Dog();

        animal.eat();
        animal.speak();
        System.out.println(animal.description());

        Dog dog = (Dog) animal;
        dog.fetch();
    }
}
```

Compile and run from the directory containing `Main.java`:

```bash
javac Main.java
java Main
```

Output:

```text
Animal eats
Woof
Dog
Fetching
```

Analysis of each call:

| Expression | Valid at compile time? | Mechanism / result |
| --- | --- | --- |
| `animal.eat()` | Yes | `Animal` declares `eat()`; `Dog` does not override it, so `Animal.eat()` runs |
| `animal.speak()` | Yes | `Animal` declares `speak()`; the JVM runs `Dog.speak()` |
| `animal.description()` | Yes | `Animal` declares the method; the JVM runs the overridden `Dog.description()` |
| `animal.fetch()` | **No** | `Animal` does not declare or inherit the `fetch()` method |
| `((Dog) animal).fetch()` | Yes | After a valid cast, the expression has compile-time type `Dog` and can call `fetch()` |

The line `animal.fetch()` is intentionally **not present in the runnable program**: if you add that line, the compiler reports that it cannot find the `fetch()` method on the `Animal` type. The fact that the actual object is `Dog` does not cause the compiler to skip checking the declared type.

Conversely, the call `animal.speak()` is still valid even though `Animal.speak()` is an `abstract` method: the compiler needs to know that the contract exists; the concrete class `Dog` provides the method body that will run.

## 3. The Declared Type Determines the Visible Set of Methods

### 3.1. A Supertype Only Exposes the Supertype's Contract

Suppose:

```java
Animal animal = new Dog();
```

Through `animal`, code can call valid, accessible instance methods belonging to `Animal` and its superclasses; if `Animal` implements an interface, the matching methods from the interface contract are also considered according to the language rules. The compiler **does not automatically infer** `Dog`'s entire specific API just from the object on the right-hand side.

Similarly:

```java
Object object = new Dog();
```

Here, the declared type is `Object`. `object.toString()` or `object.getClass()` is valid because `Object` has those methods; however, `object.speak()` is invalid because `Object` does not declare `speak()`.

The actual object is still `Dog`. Calling the `toString()` method through an `Object` variable can still execute the `toString()` implementation overridden by the subclass, if the subclass provides a valid override.

### 3.2. With Interfaces, the Compiler Looks at the Interface Contract

Standalone example to place in `Main.java`:

```java
interface Payable {
    void pay(int amount);

    default String currency() {
        return "VND";
    }
}

final class CardPayment implements Payable {
    @Override
    public void pay(int amount) {
        System.out.println("Paid " + amount);
    }

    public void verifyCard() {
        System.out.println("Card verified");
    }
}

public class Main {
    public static void main(String[] args) {
        Payable payment = new CardPayment();
        payment.pay(120);
        System.out.println(payment.currency());

        if (payment instanceof CardPayment card) {
            card.verifyCard();
        }
    }
}
```

The commands `javac Main.java` and `java Main` produce the output:

```text
Paid 120
VND
Card verified
```

- `payment.pay(120)` is valid because `Payable` declares the `pay(int)` method. The body that executes belongs to `CardPayment`.
- `payment.currency()` is valid because `Payable` has a `default` method. If the implementing class overrides it validly, the JVM can select the overridden version.
- `payment.verifyCard()` is **invalid** under the declared type `Payable`. To call its specific behavior, you must check and narrow the type to `CardPayment` as shown in the example.

A class can implement multiple interfaces, but when a variable is declared with **one** interface, the compiler only knows what is accessible through that interface type (including its superinterfaces), plus the `Object` methods that Java allows calling in the corresponding context.

### 3.3. Access Scope Still Applies

The mere existence of a method in a class or interface is not enough. The compiler also checks `public`, `protected`, package-private, `private`, and the access context. For example, code in a different package cannot call a package-private method simply because the variable has the type of the class containing the method.

A supertype variable cannot call a `private` method of the superclass from outside; a subclass also cannot override a `private` method of the superclass because that method is not inherited in the sense of overriding.

**Practical rule:** Look at the **type declaration of the expression before the dot**, that type's API, and the current access permissions before concluding that a call is valid.

## 4. Overriding and Dynamic Dispatch: Where Does a Valid Call Run?

If the declared type `Animal` exposes `speak()`, the call `animal.speak()` is valid. With `Animal animal = new Dog();`, if `Dog` overrides `speak()`, the runtime executes `Dog.speak()`. However, the runtime object does not expose `Dog`'s specific API: `animal.fetch()` still causes a compile error if `fetch()` is declared only in `Dog`.

The lesson **Dynamic Binding When Calling Instance Methods** goes into detail on overriding conditions, `super` calls, constructor dispatch, and JVM behavior.

## 5. Overloading Differs from Overriding: The Compiler Selects the Signature by Static Type

Overloads are methods with the same name but different parameter lists. The compiler selects the signature based on the static types of the receiver and arguments; if the selected instance signature is overridden, the runtime then selects the implementation for that signature.

For example, the following declarations and calls are illustrative snippets that need to be placed inside an appropriate class/method:

```java
static void describe(Animal value) { }
static void describe(Dog value) { }
```

```java
Animal animal = new Dog();
describe(animal); // Selects describe(Animal) based on the static type.
```

Cases involving boxing/unboxing, varargs, ambiguous `null`, and generic erasure are analyzed in the lesson **Selecting Overloads at Compile Time and Overrides at Runtime**.

## 6. Casting and `instanceof`: Expanding the Visible API in a Controlled Way

If you need behavior that exists only in a subtype, narrow the type after checking:

```java
Animal animal = new Dog();
if (animal instanceof Dog dog) {
    dog.fetch();
}
```

`instanceof` does not change the variable's declared type; pattern matching creates the `dog` variable within a scope determined by the compiler. An invalid cast can throw `ClassCastException`. Cast relationships, pattern scope, and cast errors are explained in the lessons **Upcasting and Downcasting Between Classes, Abstract Classes, and Interfaces**, **instanceof, Pattern Matching, and Checking Before Casting**, and **ClassCastException and Limits on Invalid Casting**.

## 7. `static` Methods and Fields Do Not Behave Like Overrides

| Member | Selection rule |
| --- | --- |
| Overridable instance method | The runtime type of the receiver selects the implementation after the signature is determined. |
| Field | The static type of the expression determines which field is accessed. |
| `static` method | The class type/name determines the method; there is no object-based dispatch. |

Field hiding and static method hiding are covered in full in the lesson **Why Field Access and Static Methods Are Not Polymorphic**.

## 8. `var`, Generics, and Expression Types: Do Not Just Look at Variable Names

### 8.1. `var` Still Has a Type Determined at Compile Time

`var` (for local variables, since Java 10) lets the compiler infer the type of the initializer expression; it does **not** turn Java into a language that resolves methods entirely at runtime.

```java
var directDog = new Dog();         // Inferred static type: Dog
Animal typedAnimal = new Dog();    // Static type: Animal
var copiedAnimal = typedAnimal;    // Inferred static type: Animal

directDog.fetch();                // Valid.
// typedAnimal.fetch();            // Compile error.
// copiedAnimal.fetch();           // Compile error.
```

This is an illustrative snippet that requires `Animal` and `Dog` to be declared as in the Section 2 example; it is not a standalone program. Renaming variables, using `var`, or assigning from another reference does not automatically expose the subtype's API.

### 8.2. Generics Return the Type Known to the Compiler

If you have a `List<Animal>`, then `animals.get(0)` has the compile-time type `Animal`, even though the concrete element is currently a `Dog`:

```java
java.util.List<Animal> animals = java.util.List.of(new Dog());

Animal first = animals.get(0);
first.speak();
// first.fetch(); // Compile error.
```

This is also an illustrative snippet reusing `Animal` and `Dog` from Section 2. To call `fetch()`, you must make the subtype explicit with an appropriate check/cast, or redesign the contract when it is general functionality.

`List<Dog>` is not automatically a subtype of `List<Animal>`: Java generics are invariant with respect to such type parameters. Even when using a read wildcard `List<? extends Animal>`, the compiler views the element at most as type `Animal` and does not rely on runtime data to allow calling `Dog.fetch()`.

### 8.3. Expression Type, Not Just Variable Type, Is Key

Consider:

```java
((Dog) animal).fetch();
```

The `animal` variable is still declared as `Animal`, but the expression `((Dog) animal)` has compile-time type `Dog`. Therefore, the compiler allows `fetch()`, after the cast passes the runtime check.

Similarly, an expression returned from a method is typed according to the **declared return type**, not automatically according to the actual implementation. If a factory declares `Animal makeAnimal()` and returns `new Dog()`, the result of `makeAnimal()` has static type `Animal` when evaluating calls at the usage site.

## 9. Special Cases: `super`, `private`, and `final`

- `super.method()` inside a subclass is the syntax for calling the superclass implementation according to language rules, allowing the subclass's override to be bypassed for that call. `super` cannot be used from code outside the subclass.
- A `final` method can **be called** through a supertype reference if valid under access scope rules, but it cannot be overridden in a subclass. Therefore, the runtime cannot select a different override of a final method.
- A `private` method of a superclass is not overridden by a subclass. A method with the same name declared in a subclass (when valid) does not turn a private call inside the superclass into a polymorphic call.
- Constructors are not methods that are inherited/overridden under the model above. The `new Dog()` expression checks `Dog`'s constructor; `super(...)` constructor chaining is handled separately.

These rules help distinguish **instance method polymorphism** from other naming/initialization mechanisms in Java.

## 10. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `cannot find symbol: method fetch()` when calling `animal.fetch()` | The declared type `Animal` does not have a `fetch()` method | Use behavior belonging to the supertype contract, or check the subtype and then call `Dog.fetch()` |
| Casting `(Dog) animal` compiles but throws `ClassCastException` | The actual object is not a `Dog` | Use `instanceof` and handle other type branches |
| Overload `describe(Animal)` runs even though the object is `Dog` | Overloads are selected based on the compile-time type of the argument | Understand that the signature is chosen at compile time; use overriding if polymorphic behavior is needed |
| `Parent p = new Child(); p.label()` calls `Parent`'s static method | Static method hiding, not dynamic dispatch | Call static methods through the class name; use an instance method if you want overriding |
| `p.name` reads the superclass field | Field hiding is resolved by static type | Use private fields and explicit getters/instance methods |
| `var x = typedAnimal` still cannot call `fetch()` | `var` infers the `Animal` type | Check the inferred type or change the declaration according to actual needs |
| `List<Animal>.get(0).fetch()` fails to compile | `get(0)` is declared to return `Animal` | Read according to the contract or narrow the subtype after checking |
| Calling `private`/package-private outside the permitted scope | Java checks access scope at compile time | Expose an appropriate API or change the design context, rather than relying on the runtime object |

Specific compiler messages may vary depending on context and version, but the essence remains that **expression types and access rules** determine whether a call is valid.

## 11. Thought Process When Reading a Method Call

When encountering an expression `receiver.method(argument)`:

1. **Determine the compile-time type of `receiver`**: the variable's declared type, the method's declared return type, the type inferred by `var`, or the type of a cast expression.
2. **List the methods named `method` that the compiler can consider** from that type, according to inheritance/interfaces, access scope, and call form.
3. **Check the arguments and overload resolution** to determine the valid, most specific signature at compile time. If no applicable method is found or the call is ambiguous, compilation fails.
4. **Classify the selected method**: if it is an overridable instance method, the JVM dispatches based on the actual object; if it is `static`, compile-time resolution is used; if it is `private`/`final`, no valid override of it exists.
5. **If a subtype-specific method is needed**, consider redesigning the API or using `instanceof`/checked casting; remember that casting does not transform the object.

This process helps avoid the mistaken assumption that simply because the actual object has a method, any reference variable can call that method.

## 12. Self-Check

**Question 1.** Suppose `Animal a = new Dog();`, and the `Dog.fetch()` method is not declared in `Animal`. Is writing `a.fetch()` valid?

**Answer:** No. The compiler checks against the `Animal` type. To use `fetch()`, there must be an appropriate expression of type `Dog`, for example after `instanceof`.

**Question 2.** With the same declaration, if `Dog` overrides `Animal.speak()`, which body does `a.speak()` execute?

**Answer:** The compiler accepts it because `Animal.speak()` exists; the runtime dispatches to `Dog.speak()`.

**Question 3.** Given two overloads `describe(Animal)` and `describe(Dog)`, which one does `Animal a = new Dog(); describe(a);` select?

**Answer:** `describe(Animal)`, based on the static type of `a`.

**Question 4.** Given `Parent p = new Child();` where both classes declare `static label()`, which version does `p.label()` call?

**Answer:** The static version on `Parent`. You should write `Parent.label()` explicitly to avoid confusion.

**Question 5.** Does using `var a = someAnimalReference;` make subtype-specific methods callable?

**Answer:** No. `var` infers the compile-time type from the initializer expression. If the expression has type `Animal`, the inferred variable is also `Animal`.

**Question 6.** Why can `Payable payment = new CardPayment();` call `payment.pay(100)` but not `payment.verifyCard()`?

**Answer:** `Payable` exposes `pay(int)`, not `verifyCard()`. The runtime object implements the contract, but the API visible through the variable still depends on the declared type.

**Key takeaway:** **The declared type/expression type determines which methods are allowed to be called and which overload is selected; the actual object type determines which overridden implementation of an instance method runs.** Understanding these two phases helps you use interfaces, abstract classes, inheritance, and polymorphism accurately without overusing casts.
