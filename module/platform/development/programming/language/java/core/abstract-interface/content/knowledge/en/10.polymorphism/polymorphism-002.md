# Dynamic Binding When Calling Instance Methods in Java

**Dynamic binding** (*dynamic binding*, or *dynamic method dispatch*) is the mechanism by which Java selects the executing version of an **overridable instance method** based on the **actual type of the receiving object at runtime**, after the call has been validated and its signature determined at compile time. This is the foundation of **runtime polymorphism**: code using a parent type or interface can still execute different behaviors depending on each concrete object.

What is essential to grasp is that Java combines **two moments of decision**:

1. **At compile time:** determines whether the call is valid according to the expression type, selects the signature via overload rules, and checks access permissions, parameter types, and the return type.
2. **At runtime:** for dynamically dispatched instance calls, selects the overriding implementation matching the **actual class** of the receiving object.

Therefore, the reference type determines **which methods can be called**, while the runtime object type determines **which overridden method body is executed**.

## 1. Introductory Example: One Reference Type, Multiple Behaviors

Save the standalone example in the file `DynamicDispatchDemo.java`:

```java
abstract class Animal {
    abstract String sound();

    String describe() {
        return "Animal says: " + sound();
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}

public class DynamicDispatchDemo {
    public static void main(String[] args) {
        Animal first = new Dog();
        Animal second = new Cat();

        System.out.println(first.sound());
        System.out.println(second.sound());
        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac DynamicDispatchDemo.java
java DynamicDispatchDemo
```

Exact output:

```text
woof
meow
Animal says: woof
Animal says: meow
```

**Step-by-step explanation:**

- `first` and `second` have the same **declared type** `Animal`; the compiler sees that `Animal` has `sound()` and `describe()`, so it accepts the calls.
- `new Dog()` creates an object whose runtime class is `Dog`; `first.sound()` executes `Dog.sound()`.
- `new Cat()` creates an object whose runtime class is `Cat`; `second.sound()` executes `Cat.sound()`.
- `describe()` is only defined in `Animal`, so both calls to `describe()` use the body of `Animal.describe()`. However, when this body calls `sound()` (equivalent to `this.sound()`), that call is **still dynamically dispatched**. The result depends on whether the object is a `Dog` or a `Cat`, even though the code of `describe()` resides in the superclass.

This is the strength of polymorphism: a method in the superclass can call an “extension point” in a subclass without having to use `if (object instanceof Dog)` or a `switch` over each object type.

## 2. What Does the Compiler Do, and What Does the JVM Do?

Consider the expression:

```java
Animal animal = new Dog();
String text = animal.sound();
```

Semantically:

| Phase | Facts Used | Decision |
| --- | --- | --- |
| **Compile time** | The expression type of `animal` is `Animal`; the method is accessible; argument types and count | `sound()` is a valid call; the result type is `String`. |
| **Runtime** | The actual value of `animal` points to a `Dog` object | For a virtual call, the selected implementation is `Dog.sound()`. |

It cannot be interpreted that the compiler always locks in `Animal.sound()` as the final body to execute: if that were the case, Java would not have overriding polymorphism (*runtime polymorphism*).

Intuitive steps to understand dynamic dispatch:

```text
Reference expression x.method(arguments)
                 │
                 ▼
Compiler checks types, overloads, access permissions
                 │
                 ▼
At runtime: evaluate receiver and arguments
                 │
                 ▼
Receiver is null? ── yes ──► NullPointerException
                 │ no
                 ▼
Look up instance implementation matching the runtime class
                 │
                 ▼
Execute the selected implementation
```

The diagram is a **semantic** model for developers; it does not rigidly describe the internal algorithm of every JVM. The JVM can optimize using devirtualization, inlining, caching, and JIT compilation, but the observable behavior must still conform to Java semantics.

**Note on evaluation timing:** for a method invocation expression, Java performs the steps of evaluating the receiver/arguments according to the language rules; for example, a call on a `null` receiver can still evaluate argument expressions before throwing `NullPointerException`. The diagram above only summarizes the runtime check and does not replace the specification on evaluation order.

## 3. Overriding Enables Dynamic Dispatch

**Overriding** occurs when a subclass provides a valid instance method that replaces an inherited instance method or implements an interface contract. For a virtual call, the runtime selects the ultimate overriding method matching the object.

```java
class Vehicle {
    String move() {
        return "moving";
    }
}

class Bicycle extends Vehicle {
    @Override
    String move() {
        return "pedaling";
    }
}

class ElectricBicycle extends Bicycle {
    @Override
    String move() {
        return "assisted pedaling";
    }
}
```

With:

```java
Vehicle a = new Vehicle();
Vehicle b = new Bicycle();
Vehicle c = new ElectricBicycle();
```

The three expressions `a.move()`, `b.move()`, and `c.move()` return `"moving"`, `"pedaling"`, and `"assisted pedaling"`, respectively. The calls are all valid through `Vehicle`, but the executed implementations reside in `Vehicle`, `Bicycle`, and `ElectricBicycle`, respectively.

Overriding conditions to remember:

- The method must have a matching signature; you cannot “override” by changing the parameter list while keeping the same name.
- The access level of the overriding method cannot be narrower than that of the original method. For example, if the original method is `public`, the overriding version must also be `public`.
- The return type must be compatible (a **covariant return type** can be used with valid reference types).
- Rules regarding checked exceptions must be respected; the overriding version must not widen the set of checked exceptions contrary to the contract.
- A `final` method cannot be overridden.
- `@Override` does not create dynamic dispatch, but it instructs the compiler to verify the override relationship properly and helps catch typos or signature errors.

A subclass **not overriding** is also completely valid if there is already an inherited concrete method: the JVM will select the closest matching inherited implementation.

## 4. Polymorphism via Interfaces: Calling the Right Implementation

A “subclass of a superclass” relationship is not required to have dynamic dispatch. Objects can implement the same interface across multiple classes that share no specific superclass other than `Object`.

Create the file `NotificationDemo.java`:

```java
interface Notifier {
    void notifyUser(String message);
}

class EmailNotifier implements Notifier {
    @Override
    public void notifyUser(String message) {
        System.out.println("EMAIL: " + message);
    }
}

class SmsNotifier implements Notifier {
    @Override
    public void notifyUser(String message) {
        System.out.println("SMS: " + message);
    }
}

class NotificationService {
    void dispatch(Notifier notifier, String message) {
        notifier.notifyUser(message);
    }
}

public class NotificationDemo {
    public static void main(String[] args) {
        NotificationService service = new NotificationService();

        service.dispatch(new EmailNotifier(), "Hello");
        service.dispatch(new SmsNotifier(), "Hello");
    }
}
```

Run:

```bash
javac NotificationDemo.java
java NotificationDemo
```

Result:

```text
EMAIL: Hello
SMS: Hello
```

`NotificationService` only knows the `Notifier` contract; the call `notifier.notifyUser(message)` dispatches to the implementation based on the runtime class (`EmailNotifier` or `SmsNotifier`). This is why applications can use dependency injection, test doubles, mocks, or plugins without having to rewrite code that uses the interface whenever a new implementing class is added.

Interface `default` methods also have corresponding rules for implementation selection and overriding. A class can override a `default` method; if the class does not override it, the valid inherited default method will run. If there are multiple conflicting default methods that cannot be resolved, **the compiler will report an error**, rather than letting the JVM pick randomly at runtime.

## 5. Overloading Is a Different Decision from Dynamic Dispatch

**Overloading**: methods with the same name but **different parameter lists**. The compiler selects the appropriate applicable method based on the **types of the argument expressions at compile time**. After selecting the signature, if the implementation of that signature is virtual, the runtime then selects the corresponding overridden version.

Create the file `OverloadVsOverrideDemo.java`:

```java
class Creature { }

class Puppy extends Creature { }

class Presenter {
    String show(Creature value) {
        return "Presenter: Creature";
    }

    String show(Puppy value) {
        return "Presenter: Puppy";
    }
}

class SpecialPresenter extends Presenter {
    @Override
    String show(Creature value) {
        return "Special: Creature";
    }

    @Override
    String show(Puppy value) {
        return "Special: Puppy";
    }
}

public class OverloadVsOverrideDemo {
    public static void main(String[] args) {
        Creature creature = new Puppy();
        Puppy puppy = new Puppy();
        Presenter presenter = new SpecialPresenter();

        System.out.println(presenter.show(creature));
        System.out.println(presenter.show(puppy));
        System.out.println(presenter.show((Creature) puppy));
    }
}
```

Run:

```bash
javac OverloadVsOverrideDemo.java
java OverloadVsOverrideDemo
```

Exact result:

```text
Special: Creature
Special: Puppy
Special: Creature
```

Analysis:

1. `creature` has the **compile-time** type `Creature` even though it points to `new Puppy()`. The compiler selects the `show(Creature)` overload; the runtime selects the overridden `SpecialPresenter.show(Creature)`.
2. `puppy` has the compile-time type `Puppy`. The compiler selects the `show(Puppy)` overload; the runtime selects `SpecialPresenter.show(Puppy)`.
3. Casting `(Creature) puppy` causes the compiler to treat the argument expression as type `Creature`, and therefore select the `show(Creature)` overload. Casting does not turn the `Puppy` object into a new `Creature` object.

**Rule of thumb:** *Overloading selects the signature by type at compile time; overriding selects the executing body by runtime class*. Java does not “re-select the overload” simply because the actual argument object belongs to a subclass.

## 6. Cases That Do Not Dynamically Dispatch in the Usual Overriding Sense

Not everything called with the dot `.` syntax has its implementation chosen based on runtime type.

| Case | Overridden/dynamically dispatched like a regular instance method? | Key Point to Remember |
| --- | --- | --- |
| Non-`static`, non-`private`, overridable instance method | **Yes**, when an appropriate override exists | Determines the implementation based on the runtime class of the receiver. |
| `static` method | **No**; the method can be *hidden* | Selected according to the type/identifier resolved at compile time. |
| `private` method | **Not overridden** | The method belongs only to the declaration that grants access; a method with the same name in a subclass is a separate method. |
| `final` instance method | **Cannot be overridden** | There is no other override for the runtime to choose, even though the syntax can still be an instance call. |
| `super.method()` | **Does not** dispatch to the current class's override based on the runtime receiver | Accesses the superclass's implementation according to `super` rules. |
| Constructor (`new`, `super(...)`, `this(...)`) | **Not** overridden | Constructors initialize the object; it is still possible to **call a virtual method inside a constructor**, see section 8. |
| Field with the same name in superclass/subclass | **No**; the field is *hidden*, not overridden | The field is selected based on the expression/declared type. |
| Overloaded methods with different signatures | Overload selects a **static signature**; the implementation can be **dynamic** | The two processes take place at two different phases. |

### 6.1. Field Hiding and Static Hiding Belong to a Separate Lesson

Accessing `ref.field` relies on the static type of the expression; calling `ref.staticMethod()` is also resolved by class type/name, not by runtime class. These two mechanisms are **field hiding** and **method hiding**, which differ from instance method overriding. The table above is sufficient to distinguish them in this dynamic binding lesson; detailed examples and interface-specific rules are covered in the lesson **Why Field Access and Static Methods Are Not Polymorphic**.

### 6.2. Calling `super` and Calling `this`

File `SuperCallDemo.java`:

```java
class Base {
    String greet() {
        return "base";
    }
}

class Extended extends Base {
    @Override
    String greet() {
        return "extended";
    }

    String compare() {
        return super.greet() + " / " + this.greet();
    }
}

public class SuperCallDemo {
    public static void main(String[] args) {
        Base x = new Extended();
        System.out.println(x.greet());
        System.out.println(((Extended) x).compare());
    }
}
```

Run:

```bash
javac SuperCallDemo.java
java SuperCallDemo
```

Result:

```text
extended
base / extended
```

`super.greet()` is bound to the superclass, allowing the subclass to reuse the original behavior. Meanwhile, `this.greet()` is a virtual call on the current object. If a subclass of `Extended` overrides `greet()` again, `this.greet()` can still dispatch to that new version.

## 7. Changing the Reference Type Does Not Change the Object's Runtime Class

`Animal a = new Dog(); Animal b = (Animal) a;` creates two references to the same `Dog` object. Both `a.sound()` and `b.sound()` still dispatch to `Dog.sound()`. Upcasting/casting only changes the type visible at compile time, not the runtime class; casting relationships and how to check subtypes are presented in the lesson **Upcasting and Downcasting Between Classes, Abstract Classes, and Interfaces**.

## 8. Crucial Pitfall: Calling an Overridable Method from a Constructor

Java still uses virtual dispatch while a constructor is running. When a superclass constructor calls an overridable method, it can execute the subclass's method **before subclass initialization has completed**. This easily leads to `null` or an unready state.

File `ConstructorDispatchDemo.java`:

```java
class Parent {
    Parent() {
        System.out.println("Parent sees: " + value());
    }

    String value() {
        return "parent";
    }
}

class Child extends Parent {
    private String name = "ready";

    @Override
    String value() {
        return name;
    }
}

public class ConstructorDispatchDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

Run:

```bash
javac ConstructorDispatchDemo.java
java ConstructorDispatchDemo
```

Result:

```text
Parent sees: null
```

**Why is it `null`?** The new object has runtime class `Child` from the very beginning. While `Parent()` is running, `value()` is dispatched to `Child.value()`; at that moment, the field `Child.name` still holds its default value `null`, because the subclass initializer `= "ready"` has not been executed yet. Only after the superclass finishes does the subclass initialization run.

**Practice:** avoid calling overridable methods in constructors, field initializers, or initialization logic that requires the subclass state to be ready. Instead, initialize using appropriate constructors or private/final helpers, or invoke the polymorphic behavior after the object is completely constructed.

## 9. Dynamic Dispatch and `null`

An instance method call requires a non-`null` receiver; if the receiver is `null`, the runtime throws `NullPointerException` and does not execute the method body. `instanceof` with `null` returns `false`, whereas `static` methods do not require a receiver instance. The lesson **Null Objects and Calls Through Interface References** explains the null contract, default methods, method references, and argument evaluation order.

## 10. How Does the JVM Execute the Call?

At the bytecode level, Java has multiple invocation instructions serving different types of binding:

| Bytecode Instruction | Typical Scenario Group | Relationship to Dispatch |
| --- | --- | --- |
| `invokevirtual` | Calling an instance method on a class in most virtual cases | Selects the appropriate implementation according to the runtime type, taking relevant selection/resolution rules into account. |
| `invokeinterface` | Calling an instance method through an interface | Selects the runtime object's implementation that satisfies the interface contract. |
| `invokespecial` | Calling constructors, `private` methods, and applicable `super` calls | Has special semantics; does not perform virtual dispatch in the usual way. |
| `invokestatic` | Calling a static method | Has no receiver instance to select an override. |
| `invokedynamic` | Call-site mechanism with bootstrap, for example in certain lambda/string concatenation implementations | Is a different binding mechanism; **not synonymous** with the “dynamic method dispatch” of `animal.sound()`. |

You can inspect the bytecode generated by `javac` yourself. With the file `DynamicDispatchDemo.java` from section 1:

```bash
javac DynamicDispatchDemo.java
javap -c DynamicDispatchDemo
```

In the `javap` output, look for the `Animal.sound` / `Animal.describe` calls and their corresponding opcodes. Bytecode line numbers, constant-pool indices, and optimization details may vary by compiler/JDK, so do not assign a single `javap` output as fixed output. The `notifyUser` call through the interface variable in the example in section 4 is a typical case that uses `invokeinterface`.

A common mental model for JVM implementation is looking up methods via type information tables (vtable/itable) or equivalent metadata. **This is an implementation detail, not a guarantee that every JVM is required to use a specific table structure.**

The JIT can observe that only one receiver type appears at a call site and directly inline that implementation, accompanied by a guard condition or deoptimization mechanism when assumptions change. This helps explain why **polymorphism does not mean every call must necessarily perform a slow table lookup**. Performance should be measured with a reliable profiler/benchmark rather than prematurely optimizing away interfaces or overrides without data.

## 11. Special Rules and Advanced Misconceptions

### 11.1. `private` and `final` Are Different

- A `private` method is not inherited to be overridden. A method with the same name/signature in a subclass is typically a different declaration.
- A `final` method is a method that can be inherited normally but **cannot be overridden**, helping protect stable behavior.
- A `final` instance call still operates on a receiver; lacking a valid receiver can still cause a `NullPointerException`. Do not equate “non-overridable” with “static”.

### 11.2. A Superclass Method Calling an Overridden Subclass Method

The `Animal.describe()` example calling `sound()` in section 1 demonstrates that **which class contains the source code of the calling method does not determine the implementation of a virtual call**. The `this` receiver is still the actual object. If the subclass wants to use the parent logic, it can call `super.sound()` when the parent method is concrete and accessible.

### 11.3. Covariant Return Types and Bridge Methods

When a subclass overrides a method with a more specialized reference return type (for example, the parent method returns `Animal` and the child method returns `Dog`), the compiler may generate a **bridge method** to preserve dispatch rules and binary compatibility in certain situations, especially with generics/erasure. A bridge method is a compiler detail to keep overriding semantics consistent; you still call the method according to the contract without needing to write a bridge yourself.

### 11.4. Package-Private Access Affects Overriding

A package-private method in a superclass **is not inherited as an overridable method** by a subclass located in a different package. A method with the same name/signature in a subclass in a different package is not automatically an override of that method. Use `@Override` so the compiler explicitly verifies when an override relationship is truly valid.

### 11.5. `Object` and Interfaces

Every regular class inherits from `Object`. Overridable instance methods such as `toString()`, `equals(Object)`, and `hashCode()` still follow dynamic dispatch. Therefore, `Object value = "hello"; System.out.println(value.toString());` will run the version appropriate for `String`, not necessarily the original `Object` implementation.

An interface can be used as a reference type for an implementing class. The `public` methods of `Object` also play a role in what can be invoked on an interface-typed expression according to Java specification rules; however, one should not assume every new member of the implementation is automatically available on the interface type.

## 12. Designing with Dynamic Dispatch

A simple model:

```text
                       Shape
                         │ area()
               ┌─────────┴─────────┐
               │                   │
             Circle             Rectangle
             area()               area()
               ▲                   ▲
               └──── Shape ref ────┘
                      s.area()
 Depending on runtime object, selects matching override
```

A function accepting `Shape` does not need to know how many shape types exist, as long as each type provides `area()`. You can add new implementations without rewriting the calling logic on `Shape`.

Useful points when using it:

1. **Design interfaces/abstract classes around stable behavior**, so clients depend on the contract rather than concrete classes.
2. **Keep varying logic inside implementations**; use a virtual call instead of a collection of `if/else` checks for each object type when there is genuinely polymorphic behavior.
3. **Avoid calling overridable methods before the object finishes initialization**, especially in a superclass constructor.
4. **Do not overuse overriding** in ways that make behavior unpredictable: an overriding method must respect the conditions and invariants of the contract; do not unexpectedly narrow the promised behavior.
5. **Prioritize readability and testability**. An interface with sufficiently clear multiple implementations helps substitute dependencies and write unit tests; adding an interface merely out of “fear” of concrete classes sometimes makes the structure more complex without benefit.

## 13. Common Mistakes and How to Identify Them

| Misconception | Accurate Explanation |
| --- | --- |
| “The variable type is `Parent`, so it always calls `Parent.method()`” | For an overridden virtual method, the runtime selects the implementation of the actual object, for example `Child.method()`. |
| “Java selects overloads by the runtime class of the argument” | The compiler selects the overload by expression type/signature at compile time; it can then dynamically dispatch the implementation of that signature. |
| “`static` methods also override like instance methods” | `static` methods are hidden, not overridden; call them using the class name for clarity. |
| “Fields in a subclass are accessed dynamically via a superclass variable” | Fields are hidden; field access follows the reference/declared type, not overriding. |
| “`super.method()` still calls the ultimate override in the subclass” | `super` requests a special call into the appropriate superclass path. |
| “Adding `@Override` is what enables polymorphism” | `@Override` is a compile-time check, not a runtime switch. |
| “The object is changed into a superclass when upcast” | Upcasting only changes the type visible at compile time; the object's runtime class remains unchanged. |
| “An overriding method cannot run before the superclass constructor finishes” | A virtual call inside a constructor can dispatch to the subclass, causing access to uninitialized state. |
| “Every instance method can be overridden” | `private` and `final` have different rules; constructors and static methods are not overridden. |
| “Dynamic dispatch is always slow because of table lookups” | The JVM has many JIT optimizations; evaluate cost only using real benchmarks/profilers. |

## 14. Self-Check

**Question 1.** Given `Parent p = new Child();` and `Child` has overridden `Parent`'s `public void run()`, which body does `p.run()` call?

**Answer:** `Child.run()`, because the object's runtime type is `Child`; the compiler only needs to verify that `run()` can be called through `Parent`.

**Question 2.** `Parent` has `static String kind()`; `Child` has a static method with the same signature. With `Parent p = new Child(); p.kind()`, which class's method is called?

**Answer:** `Parent.kind()`; static methods are not dispatched by the runtime object. You should write `Parent.kind()` directly.

**Question 3.** There are two overloads `send(Parent)` and `send(Child)`. An argument variable is declared as `Parent x = new Child();`. If `send(x)` is called, which signature does the compiler select?

**Answer:** `send(Parent)`, if no other overload is a better match for the static type `Parent`. Afterwards, if that `send(Parent)` version is an instance method overridden on the receiver, the runtime can still select the overriding implementation.

**Question 4.** The method `Parent.execute()` calls `this.validate()`. If `Child` overrides `validate()` and the actual receiver is `Child`, which `validate()` method is called?

**Answer:** `Child.validate()` (if it is a validly overridden virtual method). The location of `execute()`'s source code in `Parent` does not lock dispatch to `Parent.validate()`.

**Question 5.** Why can `new Child()` cause an overriding method of `Child` to run while the `Parent()` constructor is executing?

**Answer:** The created object has the runtime class `Child` from the very beginning; virtual instance calls from `Parent()` use the runtime class to select the override, even when `Child`'s field initializers and constructor have not finished executing yet.

**Knowledge takeaway:** Dynamic binding in Java is the selection of **the implementation of an overridable instance method according to the runtime receiver**. Determining call validity and overload resolution happens earlier at compile time. Clearly distinguishing these two steps, while recognizing the exceptions for `static`, `private`, `final`, `super`, constructors, and fields, will help accurately predict polymorphic behavior in real-world code.
