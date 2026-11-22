# Object Method Dispatch by Actual Class in Java

**Dynamic method dispatch** (*dynamic method dispatch*, *virtual method invocation*) is the mechanism by which Java selects **the implementation of an overridden instance method** based on **the actual class of the object at runtime**, rather than simply based on the declared type of the variable holding the reference.

For example:

```java
Animal animal = new Dog();
animal.speak();
```

When `Animal` declares an instance method `speak()` that can be overridden, and `Dog` overrides that method, the call `animal.speak()` will run **`Dog.speak()`**. The variable `animal` still has the **declared type `Animal`**, but the object it points to belongs to the **runtime class `Dog`**.

This is the foundation of **dynamic polymorphism** in Java: clients write code against a superclass or interface, yet can receive objects belonging to different implementation classes.

However, you need to understand **two different phases**:

1. **At compile time:** the compiler uses the **static type of the receiver expression**, method name, argument list, access permissions, and overloading rules to determine whether the call is valid and which **method signature** to select.
2. **At runtime:** for an **instance method with dynamic dispatch**, the JVM uses the **runtime class of the receiver** to select the most appropriate overriding implementation according to Java's rules.

**Not every occurrence of `object.method()` is dynamic dispatch.** Static methods are subject to **hiding**, fields are subject to **hiding**, overloading is resolved at compile time, private methods are not overridden like public/protected methods, and `super.method()` specifies the superclass implementation in a special way.

This lesson targets **Java 17+**. Each standalone runnable example includes its file name, `javac`/`java` commands, and stdout; snippets illustrating intentional errors are commented out or explicitly noted.

## 1. Declared Type and Runtime Class: Two Pieces of Information to Keep Separate

Suppose:

```java
class Animal {
    void speak() {
        System.out.println("Animal");
    }
}

class Dog extends Animal {
    @Override
    void speak() {
        System.out.println("Dog");
    }
}
```

When writing:

```java
Animal pet = new Dog();
```

we have:

| Concept | In the example |
| --- | --- |
| **Declared type** of the variable `pet` | `Animal` |
| **Type of the expression `new Dog()`** | `Dog` |
| **Runtime class** of the object that `pet` points to | `Dog` |
| **Method `speak()` visible through `Animal`** | `Animal.speak()` |
| **Implementation of `pet.speak()` invoked** | `Dog.speak()` |

The compiler allows the assignment because `Dog` is a subtype of `Animal`. This assignment is commonly called **upcasting**; in this case, an explicit cast does not need to be written.

After the assignment, `pet` **does not become a new `Animal` object**. The object is still a `Dog` object. The variable's type only restricts how code can **use the object through that reference**.

### Why Must These Two Pieces of Information Be Separated?

The two calls:

```java
Animal first = new Animal();
Animal second = new Dog();

first.speak();
second.speak();
```

have the same receiver type at compile time (`Animal`) and the same visible method signature, yet can execute **two different implementations** because the two receiver objects have different runtime classes.

That is precisely the difference between **static type checking** and **dynamic dispatch**.

## 2. Complete Java 17 Example: Dispatching by Runtime Object

Save as **`DynamicDispatchDemo.java`**:

```java
class Animal {
    void speak() {
        System.out.println("Animal speaks");
    }
}

class Dog extends Animal {
    @Override
    void speak() {
        System.out.println("Dog barks");
    }
}

class Cat extends Animal {
    @Override
    void speak() {
        System.out.println("Cat meows");
    }
}

public class DynamicDispatchDemo {
    public static void main(String[] args) {
        Animal first = new Animal();
        Animal second = new Dog();
        Animal third = new Cat();

        first.speak();
        second.speak();
        third.speak();
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 DynamicDispatchDemo.java
java DynamicDispatchDemo
```

**Exact stdout:**

```text
Animal speaks
Dog barks
Cat meows
```

Explanation:
- `first` points to an `Animal` object → uses `Animal.speak()`.
- `second` points to a `Dog` object → the JVM selects the `Dog.speak()` override.
- `third` points to a `Cat` object → the JVM selects the `Cat.speak()` override.
- The three variables are all declared with type `Animal`, yet the implementations invoked are **not necessarily the same**.
- The `@Override` annotation helps the compiler verify that the method actually performs a valid override, but **it is not what creates dynamic dispatch**; overriding still has the corresponding semantics if the annotation is omitted.

## 3. A Reference Can Point to Different Subclass Objects at Different Times

```java
Animal animal = new Dog();
animal.speak();

animal = new Cat();
animal.speak();
```

The two calls above execute `Dog.speak()` and then `Cat.speak()`, respectively. The variable `animal` does not change its declared type; only **the reference value** is reassigned.

Diagram:

```text
Initially:
animal : Animal ─────► Dog object
                      Dog.speak()

After the assignment:
animal : Animal ─────► Cat object
                      Cat.speak()
```

**The static type of a variable does not change across assignments.** The referenced runtime object can change if the variable is allowed to be reassigned and the new object is a compatible subtype.

If `animal` is declared as `final Animal animal = new Dog();`, you cannot reassign `animal = new Cat();`, yet a call to `animal.speak()` still dispatches to `Dog.speak()`: **a final reference does not disable polymorphism**.

## 4. What Does the Compiler Resolve Before the JVM Dispatches?

Consider:

```java
Animal animal = new Dog();
animal.speak();
```

At compile time, Java needs to answer:
- What **static type** does the expression `animal` have?
- From that type, is the method `speak()` accessible with the given arguments?
- How many applicable overloads are there, and which overload is selected?
- Is the method restricted by access control?
- What return type is used for the call expression?
- Are argument type conversions, boxing/unboxing, or varargs application needed?

Only after the call is valid and bound to the **matching signature** can the selection of the **instance implementation** take place at runtime.

**Important:** the runtime class does not allow you to arbitrarily call a method that exists only in a subclass and is neither declared nor inherited by the receiver's static type.

```java
class Dog extends Animal {
    void fetch() {
        System.out.println("Fetch");
    }
}

Animal animal = new Dog();
// animal.fetch(); // ERROR if Animal does not declare fetch().
```

The error lies in **compile-time member lookup**. The fact that the runtime object is `Dog` does not make the compiler ignore the `Animal` type.

## 5. Program: Static Type Limits the API, Runtime Selects the Implementation

Save **`StaticViewRuntimeDemo.java`**:

```java
class Vehicle {
    String describe() {
        return "Vehicle";
    }
}

class ElectricCar extends Vehicle {
    @Override
    String describe() {
        return "ElectricCar";
    }

    int batteryPercent() {
        return 80;
    }
}

public class StaticViewRuntimeDemo {
    public static void main(String[] args) {
        Vehicle vehicle = new ElectricCar();

        System.out.println(vehicle.describe());

        // vehicle.batteryPercent();
        // ERROR: batteryPercent() does not exist in type Vehicle.

        ElectricCar car = (ElectricCar) vehicle;
        System.out.println(car.batteryPercent());
    }
}
```

```bash
javac -encoding UTF-8 StaticViewRuntimeDemo.java
java StaticViewRuntimeDemo
```

Stdout:

```text
ElectricCar
80
```

Here:
- `describe()` is in the `Vehicle` contract; the implementation is dispatched based on the runtime object.
- `batteryPercent()` exists only in `ElectricCar`; to call it, you must have a receiver expression with a sufficiently specific static type, such as the variable `car` after a valid cast.
- A cast **does not create a new object** and **does not change the runtime class** of the object; it only gives the compiler a different type view, along with a compatibility check at runtime when needed.

## 6. Overriding: Conditions for Dynamic Dispatch to Replace the Implementation

A method in a subclass is considered an override when it satisfies the language rules, including requirements related to:
- Same name and compatible signatures (*override-equivalent signatures*).
- Overridable method kind: an **instance method**, not a static method.
- The superclass method is not `final`, and the method must be inheritable/overridable according to access rules.
- The subclass access level is not narrowed in violation of the rules.
- Compatible return type (*return-type substitutability*, which may be covariant).
- Declared checked exceptions compatible with the overridden method.
- Generics, erasure, and bridge method rules when applicable.

The `@Override` annotation is recommended:

```java
class Base {
    protected String label() {
        return "Base";
    }
}

class Child extends Base {
    @Override
    public String label() {
        return "Child";
    }
}
```

`Child.label()` is valid because increasing visibility from `protected` to `public` is allowed. If changed to `private String label()`, the compiler rejects it because it reduces the accessibility of the overridden method.

**It is not only `public` methods that can be overridden.** `protected` and package-private methods can be overridden when package/access conditions are satisfied; `private` methods are not overridden under the same mechanism.

## 7. Where Is the Implementation Found When a Subclass Does Not Override?

Runtime dispatch does not necessarily select a method written **directly inside the runtime class**. The JVM uses the **closest matching** overriding implementation in the hierarchy/class–interface method resolution according to Java semantics.

Example:

```java
class Parent {
    void say() {
        System.out.println("Parent");
    }
}

class Middle extends Parent {
    @Override
    void say() {
        System.out.println("Middle");
    }
}

class Child extends Middle {
    // Does not override say().
}
```

With `Parent value = new Child(); value.say();`, the result is `Middle`. The runtime class `Child` **inherits** the `Middle.say()` implementation.

This is subtler than the statement “Java calls the method of the runtime class”: it should be understood that **Java selects the implementation corresponding to the runtime class along the override chain**, which may be inherited from a superclass.

### Complete Program

Save **`InheritedOverrideDemo.java`**:

```java
class Parent {
    String source() {
        return "Parent";
    }
}

class Middle extends Parent {
    @Override
    String source() {
        return "Middle";
    }
}

class Child extends Middle {
}

public class InheritedOverrideDemo {
    public static void main(String[] args) {
        Parent first = new Parent();
        Parent second = new Middle();
        Parent third = new Child();

        System.out.println(first.source());
        System.out.println(second.source());
        System.out.println(third.source());
    }
}
```

```bash
javac -encoding UTF-8 InheritedOverrideDemo.java
java InheritedOverrideDemo
```

Stdout:

```text
Parent
Middle
Middle
```

## 8. Overloading Differs from Overriding: Two Phases Not to Confuse

**Overloading:** same method name, **different parameter list** in the signature. The compiler selects the overload based on the **static types of the arguments** and resolution rules.

**Overriding:** a subclass redefines an **instance method with the same corresponding signature**, and runtime can select the implementation based on the **actual class of the receiver**.

Example:

```java
class Printer {
    void print(Animal animal) {
        System.out.println("Animal overload");
    }

    void print(Dog dog) {
        System.out.println("Dog overload");
    }
}

Printer printer = new Printer();
Animal value = new Dog();

printer.print(value); // Selects print(Animal), not print(Dog).
```

Even though the object of `value` is a `Dog`, the compiler sees that the **static type of the argument `value` is `Animal`**, so it selects the overload matching `Animal`.

Do not describe overloading as “runtime polymorphism”. It may be called compile-time polymorphism in common classification, yet **overload selection** is still based on static typing.

## 9. Core Example: Static Overloading, Dynamic Overriding in the Same Call

Save **`OverloadOverrideDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

class Handler {
    String handle(Animal animal) {
        return "Handler: Animal";
    }

    String handle(Dog dog) {
        return "Handler: Dog";
    }
}

class SpecialHandler extends Handler {
    @Override
    String handle(Animal animal) {
        return "Special: Animal";
    }

    @Override
    String handle(Dog dog) {
        return "Special: Dog";
    }
}

public class OverloadOverrideDemo {
    public static void main(String[] args) {
        Handler handler = new SpecialHandler();

        Animal first = new Dog();
        Dog second = new Dog();

        System.out.println(handler.handle(first));
        System.out.println(handler.handle(second));
        System.out.println(handler.handle((Animal) second));
    }
}
```

```bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
```

**Stdout:**

```text
Special: Animal
Special: Dog
Special: Animal
```

Let's analyze this very slowly:

1. `handler` has the declared type `Handler`, and the runtime receiver is `SpecialHandler`.
2. `first` has the declared type `Animal`, even though the object is `Dog`. The compiler selects the signature `handle(Animal)`.
3. The JVM dispatches the signature `handle(Animal)` to the `SpecialHandler.handle(Animal)` override → prints `Special: Animal`.
4. `second` has the static type `Dog`. The compiler selects `handle(Dog)`, and runtime selects the override in `SpecialHandler` → `Special: Dog`.
5. The cast `(Animal) second` makes the **static type of the argument expression** `Animal`. The compiler selects `handle(Animal)`, even though the object is still a Dog → `Special: Animal`.

**Formula:** *overloading selects the signature using static types; overriding selects the implementation using the runtime receiver*. The roles of the two phases should not be reversed.

## 10. The Runtime Type of an **Argument** Does Not Automatically Select an Overload

This is a case that is very easy to mispredict:

```java
void examine(Object value) {
    System.out.println("Object");
}

void examine(String value) {
    System.out.println("String");
}
```

With:

```java
Object object = "Java";
examine(object); // Selects examine(Object).
```

Even though the runtime object is `String`, the **static type of the argument** is still `Object`. The compiler does not run until runtime to “find a more specific overload”.

If you truly want to select behavior based on the runtime subtype of an argument, design options include:
- Use **method overriding on the participating object itself** (move the behavior to the right receiver if the contract allows).
- Use pattern matching `instanceof` or a sealed hierarchy when the set of variants is clear.
- Use **Visitor/double dispatch** if the problem is selecting an algorithm based on two runtime types and the complexity is appropriate.
- Use a strategy registry by event/domain type if extensibility outside the hierarchy is needed.

You should not assume that the JVM automatically performs multiple dispatch for an ordinary Java overloaded call.

## 11. Calls Through an Interface Still Use Dynamic Dispatch

An interface defines a **contract**. The caller does not need to know the concrete implementation.

```java
interface PaymentMethod {
    String pay(int amount);
}

class CardPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "CARD " + amount;
    }
}

class CashPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "CASH " + amount;
    }
}
```

If:

```java
PaymentMethod method = new CardPayment();
System.out.println(method.pay(100));
```

then the implementation of `CardPayment` is called.

**Key point:** Java interface method dispatch does not select an implementation by a “fixed interface name”. The runtime object gets to provide the appropriate implementation of the method contract.

### Runnable Interface Example

Save **`InterfaceDispatchDemo.java`**:

```java
interface Messenger {
    String send(String text);
}

final class EmailMessenger implements Messenger {
    @Override
    public String send(String text) {
        return "EMAIL: " + text;
    }
}

final class SmsMessenger implements Messenger {
    @Override
    public String send(String text) {
        return "SMS: " + text;
    }
}

public class InterfaceDispatchDemo {
    private static void deliver(Messenger messenger) {
        System.out.println(messenger.send("Hello"));
    }

    public static void main(String[] args) {
        deliver(new EmailMessenger());
        deliver(new SmsMessenger());
    }
}
```

```bash
javac -encoding UTF-8 InterfaceDispatchDemo.java
java InterfaceDispatchDemo
```

Stdout:

```text
EMAIL: Hello
SMS: Hello
```

The `deliver` method only knows the `Messenger` interface; it has no `if`/`instanceof` to detect the concrete class. Dynamic dispatch enables extension with new implementations.

## 12. Interface Default Methods Also Participate in Implementation Selection

Java allows an interface to have a **default instance method**:

```java
interface Greeter {
    default String hello() {
        return "Hello from interface";
    }
}
```

If a class implements the interface without overriding `hello()`, instances can use the default implementation according to interface method resolution rules.

```java
class BasicGreeter implements Greeter {
}
```

`new BasicGreeter().hello()` uses the default method `Greeter.hello()`.

If a class overrides it:

```java
class FriendlyGreeter implements Greeter {
    @Override
    public String hello() {
        return "Hi from class";
    }
}
```

then a call through `Greeter` can dispatch to `FriendlyGreeter.hello()`.

**Note:** interface static methods are **not** like default instance methods: they do not participate in instance override dispatch like `hello()`.

## 13. Class Methods Take Precedence Over Interface Default Methods When Applicable

Java has rules for resolving default method conflicts, often summarized as **class wins over interface defaults** when an applicable class method implementation exists.

Example:

```java
interface Greeter {
    default String hello() {
        return "Interface";
    }
}

class Parent {
    public String hello() {
        return "Parent";
    }
}

class Child extends Parent implements Greeter {
}
```

`new Child().hello()` uses `Parent.hello()`, not `Greeter`'s default.

When two unrelated interfaces both provide default methods with conflicting signatures, the implementing class may have to **explicitly override to resolve it**. You should not assume that Java arbitrarily picks the interface listed first in `implements`.

### Runnable Java 17 Program

Save **`DefaultMethodDispatchDemo.java`**:

```java
interface Greeter {
    default String hello() {
        return "Interface";
    }
}

class Parent {
    public String hello() {
        return "Parent";
    }
}

class Child extends Parent implements Greeter {
}

class CustomGreeter implements Greeter {
    @Override
    public String hello() {
        return "Custom";
    }
}

public class DefaultMethodDispatchDemo {
    public static void main(String[] args) {
        Greeter first = new Child();
        Greeter second = new CustomGreeter();

        System.out.println(first.hello());
        System.out.println(second.hello());
    }
}
```

```bash
javac -encoding UTF-8 DefaultMethodDispatchDemo.java
java DefaultMethodDispatchDemo
```

Stdout:

```text
Parent
Custom
```

In the call `first.hello()`, `Child` inherits the matching class implementation `Parent.hello()`, so `Greeter`'s default implementation is not selected. In the call `second.hello()`, the `CustomGreeter` class provides its own override.

## 14. Resolving a Conflict Between Two Default Methods

Snippet that is **invalid if not overridden**:

```java
interface Left {
    default String name() {
        return "Left";
    }
}

interface Right {
    default String name() {
        return "Right";
    }
}

// class Both implements Left, Right { }
// ERROR: inherited unrelated defaults conflict.
```

Fix: the class must provide an explicit implementation:

```java
class Both implements Left, Right {
    @Override
    public String name() {
        return Left.super.name() + "+" + Right.super.name();
    }
}
```

`Left.super.name()` and `Right.super.name()` are **qualified interface super invocations** in an applicable instance context; they are not arbitrary dynamic dispatch to just any interface. The syntax has constraining rules regarding direct superinterfaces and inheritance relationships.

### Runnable Example

Save **`DefaultConflictDemo.java`**:

```java
interface Left {
    default String name() {
        return "Left";
    }
}

interface Right {
    default String name() {
        return "Right";
    }
}

class Both implements Left, Right {
    @Override
    public String name() {
        return Left.super.name() + "/" + Right.super.name();
    }
}

public class DefaultConflictDemo {
    public static void main(String[] args) {
        Left value = new Both();
        System.out.println(value.name());
    }
}
```

```bash
javac -encoding UTF-8 DefaultConflictDemo.java
java DefaultConflictDemo
```

Stdout:

```text
Left/Right
```

The compiler determines the contract and the specific subclass method; runtime calls `Both.name()` when the actual receiver is `Both`. Inside the override, the code **intentionally specifies** the two interface default implementations to combine.

## 15. Static Methods Do **Not** Dispatch Based on the Runtime Class

A static method belongs to **the class/interface as declared**, with no dynamic dispatch based on the runtime instance. If a subclass declares a static method with the same name and matching signature, that is **method hiding**, not overriding.

```java
class Parent {
    static String kind() {
        return "Parent";
    }
}

class Child extends Parent {
    static String kind() {
        return "Child";
    }
}
```

```java
Parent reference = new Child();
System.out.println(reference.kind());
```

The result is `Parent`, because the compiler binds the static method call based on the applicable type of the expression `reference` (`Parent`), **not** on the runtime class `Child`.

**Recommended style:**

```java
Parent.kind();
Child.kind();
```

You should not call a static method through an object reference, even though Java may allow it, because it easily leads readers to assume the call will dispatch polymorphically.

## 16. Runnable Example: Static Hiding Differs from Instance Overriding

Save **`StaticVersusInstanceDemo.java`**:

```java
class Parent {
    static String staticLabel() {
        return "Parent static";
    }

    String instanceLabel() {
        return "Parent instance";
    }
}

class Child extends Parent {
    static String staticLabel() {
        return "Child static";
    }

    @Override
    String instanceLabel() {
        return "Child instance";
    }
}

public class StaticVersusInstanceDemo {
    public static void main(String[] args) {
        Parent value = new Child();

        System.out.println(value.staticLabel());
        System.out.println(value.instanceLabel());
        System.out.println(Parent.staticLabel());
        System.out.println(Child.staticLabel());
    }
}
```

```bash
javac -encoding UTF-8 StaticVersusInstanceDemo.java
java StaticVersusInstanceDemo
```

**Stdout:**

```text
Parent static
Child instance
Parent static
Child static
```

- `value.staticLabel()` is selected according to the static type `Parent`; this is a calling style to avoid in new code.
- `value.instanceLabel()` uses the runtime object `Child` and calls the override.
- `Parent.staticLabel()`/`Child.staticLabel()` directly specifies the class containing the desired static implementation.

**Warning:** a static method cannot be overridden by an instance method with the same signature in a subclass, and an instance method cannot be replaced by a static method with the same signature as a valid override/hiding. The compiler rejects invalid “static ↔ instance switching” forms.

## 17. Field Access Does Not Participate in Dynamic Method Dispatch

If a subclass declares a field with the same name as a superclass field, the expression `reference.field` is resolved using the compiler's **field access** rules — not based on the runtime class like an overridable instance method. A cast can change the **static type of the expression**, thereby changing which field is selected, yet **does not convert the object into a different instance**.

To observe this difference in this lesson on runtime dispatch, look directly at the `FieldVsMethodDemo` program in section 18: on the same `new Child()`, `reference.label` reads the Parent field while `reference.getLabel()` dispatches to the Child override.

Do not design polymorphism using fields; keep state `private` and provide meaningful overridable instance methods or an interface contract. **The lesson on field/static hiding** analyzes hiding and lookup rules in depth; this lesson only emphasizes that they **do not fall within the scope of dynamic method dispatch**.

## 18. Field vs. Method Example: One Object, Two Different Selection Behaviors

Save **`FieldVsMethodDemo.java`**:

```java
class Parent {
    String label = "Parent field";

    String getLabel() {
        return "Parent method";
    }
}

class Child extends Parent {
    String label = "Child field";

    @Override
    String getLabel() {
        return "Child method";
    }
}

public class FieldVsMethodDemo {
    public static void main(String[] args) {
        Parent reference = new Child();

        System.out.println(reference.label);
        System.out.println(reference.getLabel());

        Child child = (Child) reference;
        System.out.println(child.label);
        System.out.println(child.getLabel());
    }
}
```

```bash
javac -encoding UTF-8 FieldVsMethodDemo.java
java FieldVsMethodDemo
```

**Stdout:**

```text
Parent field
Child method
Child field
Child method
```

Explanation:
- `reference.label` → `Parent`'s field because the compiler sees `Parent`.
- `reference.getLabel()` → `Child`'s override because the runtime receiver is `Child`.
- `child.label` → `Child`'s field because the static type after the cast is `Child`.
- `child.getLabel()` → still `Child` because the runtime object has not changed.

**Note:** a cast to `Parent` does not “convert the object into a Parent” or strip away the Child part. It only changes the **expression type** at compile time.

## 19. `super.method()` Is an Intentional Call to the Superclass Implementation

Inside a subclass instance method, the `super.method()` syntax allows calling the appropriate superclass implementation **without selecting the override in the subclass itself as the direct target**.

Example:

```java
class Parent {
    String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "Child->" + super.describe();
    }
}
```

When `Child.describe()` is called:
- Runtime dispatch selects `Child.describe()`.
- Inside this body, `super.describe()` specifies the implementation from the superclass.
- The result is `Child->Parent`.

**Do not confuse** `super.describe()` with `((Parent)this).describe()`:
- `super.describe()` is a special superclass invocation.
- `((Parent)this).describe()` is still a normal virtual method call with the `Child` object as the receiver; therefore, it can dispatch back to `Child.describe()` and lead to recursion if used to replace `super`.

### Runnable Example

Save **`SuperDispatchDemo.java`**:

```java
class Parent {
    String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "Child/" + super.describe();
    }
}

public class SuperDispatchDemo {
    public static void main(String[] args) {
        Parent value = new Child();

        System.out.println(value.describe());
        System.out.println(((Child) value).describe());
    }
}
```

```bash
javac -encoding UTF-8 SuperDispatchDemo.java
java SuperDispatchDemo
```

Stdout:

```text
Child/Parent
Child/Parent
```

There is no `super` call from a static method of a class in the sense of an instance receiver: a static context has no implicit `this`/`super` for that class.

## 20. `private` Methods Are Not Overridden in the Usual Way

A `private` instance method of a superclass **is not inherited to be overridden**. If a subclass declares a method with the same name and potentially matching parameters, it may be **a separate method**, not an override of the superclass private method.

```java
class Parent {
    private void secret() {
        System.out.println("Parent secret");
    }

    void perform() {
        secret();
    }
}

class Child extends Parent {
    void secret() {
        System.out.println("Child secret");
    }
}
```

`Child.secret()` does not override `Parent.secret()`; `Parent.perform()` still calls Parent's private method.

### Runnable Example

Save **`PrivateMethodDispatchDemo.java`**:

```java
class Parent {
    private void secret() {
        System.out.println("Parent secret");
    }

    void perform() {
        secret();
    }
}

class Child extends Parent {
    void secret() {
        System.out.println("Child secret");
    }
}

public class PrivateMethodDispatchDemo {
    public static void main(String[] args) {
        Child child = new Child();

        child.perform();
        child.secret();
    }
}
```

```bash
javac -encoding UTF-8 PrivateMethodDispatchDemo.java
java PrivateMethodDispatchDemo
```

Stdout:

```text
Parent secret
Child secret
```

This is one reason to avoid claiming “any subclass method with the same name overrides”. **Access/inheritance** is part of the condition.

## 21. `final` Methods Lock Overriding

An instance method marked `final` cannot be validly overridden by a subclass.

```java
class Parent {
    final String category() {
        return "FIXED";
    }
}

class Child extends Parent {
    // String category() { return "OTHER"; }
    // ERROR if uncommented: cannot override final method.
}
```

With a `Child` object, `category()` can still be **inherited and called**; there simply cannot be another subclass override replacing the implementation.

`final` on a method **does not** prohibit overloading:

```java
class Child extends Parent {
    String category(int id) {
        return "ID=" + id;
    }
}
```

`category(int)` is a different signature and does not override `category()`.

### A `final class` Also Ends the Hierarchy

A `final` class cannot have subclasses. However, an object of a final class can still be referenced through an interface/other superclass, and calls through the interface continue to work according to the contract.

`final` does not turn an instance method into a static one. It only restricts future implementations that can override it.

## 22. Program: Inherited final Method and Another Overridable Method

Save **`FinalMethodDispatchDemo.java`**:

```java
class Parent {
    final String fixed() {
        return "Parent fixed";
    }

    String flexible() {
        return "Parent flexible";
    }
}

class Child extends Parent {
    @Override
    String flexible() {
        return "Child flexible";
    }
}

public class FinalMethodDispatchDemo {
    public static void main(String[] args) {
        Parent value = new Child();

        System.out.println(value.fixed());
        System.out.println(value.flexible());
    }
}
```

```bash
javac -encoding UTF-8 FinalMethodDispatchDemo.java
java FinalMethodDispatchDemo
```

Stdout:

```text
Parent fixed
Child flexible
```

**Do not be mistaken:** Java does not perform a “runtime search arbitrary override” for a final method. The final contract of the method is locked, even though the call still has a receiver instance and usage access depends on static typing.

## 23. Abstract Methods: No Implementation in the Superclass, Yet Still Dynamically Dispatched

An `abstract` instance method defines part of a contract without having a body in the class that declares it abstract.

```java
abstract class Notification {
    abstract String channel();
}
```

A concrete subclass implements it:

```java
final class Email extends Notification {
    @Override
    String channel() {
        return "EMAIL";
    }
}
```

The call:

```java
Notification notification = new Email();
System.out.println(notification.channel());
```

still uses dynamic dispatch to execute `Email.channel()`. The fact that `Notification.channel` has no body **is not an exception** to dispatch; it is a characteristic example of polymorphism.

**An object cannot be created directly from an abstract class** with `new Notification()`, yet a variable of type `Notification` can hold an appropriate concrete subtype.

### Template Method: final Orchestration, abstract Customizable Step

```java
abstract class Task {
    final void run() {
        System.out.println("start");
        execute();
        System.out.println("finish");
    }

    protected abstract void execute();
}
```

`run()` is final and cannot be overridden; however, `execute()` is an abstract method that is dynamically dispatched according to the runtime subtype.

This is a controlled way of using polymorphism: the base class preserves the sequence invariant, while subclasses only replace specific extension points.

## 24. Runnable Template Method: One Call, Multiple Implementations

Save **`TemplateDispatchDemo.java`**:

```java
abstract class Task {
    final void run() {
        System.out.println("start");
        execute();
        System.out.println("finish");
    }

    protected abstract void execute();
}

final class EmailTask extends Task {
    @Override
    protected void execute() {
        System.out.println("send email");
    }
}

final class FileTask extends Task {
    @Override
    protected void execute() {
        System.out.println("save file");
    }
}

public class TemplateDispatchDemo {
    public static void main(String[] args) {
        Task first = new EmailTask();
        Task second = new FileTask();

        first.run();
        second.run();
    }
}
```

```bash
javac -encoding UTF-8 TemplateDispatchDemo.java
java TemplateDispatchDemo
```

Stdout:

```text
start
send email
finish
start
save file
finish
```

Because `run()` cannot be overridden, both runtime objects execute the same `start/finish` skeleton; upon reaching `execute()`, the JVM selects the corresponding subtype's implementation.

**Note:** an overridable hook can throw an exception or produce side effects. `final run` does not automatically guarantee all business invariants if the hook contract is not strict enough.

## 25. Covariant Return Types: Overriding Still Dispatches Dynamically

Java allows a subclass to override a method with a **more specific reference return type** when it satisfies the *return-type substitutability* rules.

Example:

```java
class AnimalFactory {
    Animal create() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() {
        return new Dog();
    }
}
```

With `AnimalFactory factory = new DogFactory();`, the call `factory.create()` dispatches to `DogFactory.create()` and creates a `Dog`.

However, at compile time, the expression `factory.create()` is typically checked according to the **return type seen through `AnimalFactory`**, namely `Animal`:

```java
Animal animal = factory.create(); // Valid.
// Dog dog = factory.create();     // Requires a cast/specific factory type.
```

Covariant returns **do not change the caller's static type-checking rules**.

### Java 17 Program

Save **`CovariantReturnDemo.java`**:

```java
class Animal {
    String name() {
        return "Animal";
    }
}

class Dog extends Animal {
    @Override
    String name() {
        return "Dog";
    }
}

class Factory {
    Animal create() {
        return new Animal();
    }
}

class DogFactory extends Factory {
    @Override
    Dog create() {
        return new Dog();
    }
}

public class CovariantReturnDemo {
    public static void main(String[] args) {
        Factory general = new DogFactory();
        DogFactory specific = new DogFactory();

        Animal first = general.create();
        Dog second = specific.create();

        System.out.println(first.name());
        System.out.println(second.name());
    }
}
```

```bash
javac -encoding UTF-8 CovariantReturnDemo.java
java CovariantReturnDemo
```

Stdout:

```text
Dog
Dog
```

Both calls execute `DogFactory.create()`. The difference is the **compile-time type of the expressions** `general.create()` and `specific.create()`; the dynamic dispatch of `name()` is also based on the Dog runtime object.

## 26. Casting Does Not Change an Object's Runtime Class

Suppose:

```java
Animal animal = new Dog();
Dog dog = (Dog) animal;
```

Both references can point to **the same `Dog` object**. A cast does not clone, copy, downgrade, or “relabel the actual class”.

When:

```java
((Animal) dog).speak();
```

If `Dog` overrides `speak()`, the call still dispatches to `Dog.speak()`. Casting the receiver to `Animal` does not force `Animal`'s implementation to run.

To call the superclass implementation from a subclass instance method, use `super.speak()` in a valid context, not `((Animal)this).speak()`.

### An Invalid Downcast Throws `ClassCastException`

```java
Animal animal = new Cat();
// Dog dog = (Dog) animal; // Throws ClassCastException at runtime.
```

The compiler may allow a cast if the two types have a compatible type relationship, but the runtime check rejects it if the actual object is not an appropriate subtype.

A safer approach when a subtype-specific API is needed: Java 17 has **pattern matching for `instanceof`**.

## 27. `instanceof` Pattern Matching in Java 17

```java
if (animal instanceof Dog dog) {
    dog.fetch();
}
```

The condition both checks the runtime type and introduces the pattern variable `dog` with type `Dog` within the valid scope.

### Runnable Program

Save **`InstanceofDispatchDemo.java`**:

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }

    String fetch() {
        return "fetching";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}

public class InstanceofDispatchDemo {
    private static void inspect(Animal animal) {
        System.out.println(animal.sound());

        if (animal instanceof Dog dog) {
            System.out.println(dog.fetch());
        }
    }

    public static void main(String[] args) {
        inspect(new Dog());
        inspect(new Cat());
    }
}
```

```bash
javac -encoding UTF-8 InstanceofDispatchDemo.java
java InstanceofDispatchDemo
```

Stdout:

```text
woof
fetching
meow
```

`inspect` calls `sound()` according to the `Animal` contract and receives polymorphic behavior; only when it needs the `fetch()` method, which is not in the Animal contract, does the program check the subtype.

**Do not overuse `instanceof`** just to manually dispatch every behavior that could have been placed as a polymorphic method in a superclass/interface. If many subtype branches appear throughout the code, the abstraction may need to be redesigned.

## 28. `null` Has No Runtime Object for Dispatch

A reference variable can have the value `null`:

```java
Animal animal = null;
animal.speak(); // NullPointerException at runtime.
```

The compiler can accept the call because the static type `Animal` provides the method `speak()`, yet at runtime there is no valid **receiver object** on which to perform the instance method invocation.

This is a different issue from compile-time method resolution:
- **Compile-time:** `Animal.speak()` is a valid call.
- **Runtime:** null receiver → an instance method cannot be invoked on an object.

### Runnable Example with Error Catching

Save **`NullReceiverDemo.java`**:

```java
class Animal {
    String sound() {
        return "sound";
    }
}

public class NullReceiverDemo {
    public static void main(String[] args) {
        Animal animal = null;

        try {
            System.out.println(animal.sound());
        } catch (NullPointerException error) {
            System.out.println("No receiver");
        }
    }
}
```

```bash
javac -encoding UTF-8 NullReceiverDemo.java
java NullReceiverDemo
```

Stdout:

```text
No receiver
```

**Do not use NullPointerException as normal conditional branching** in production when you can perform an explicit null check or design a non-null contract.

A static method can be invoked through an expression whose syntax looks like an instance receiver (`reference.staticMethod()`), but that is **not** instance dispatch. Avoid that calling style so as not to mix null/static rules with dynamic dispatch.

## 29. Constructors Are Not Dynamically Overridden

A constructor is not an overridable instance method. When writing:

```java
Animal animal = new Dog();
```

Java determines the type of object to create from the **class name in the `new Dog()` expression**, rather than “dynamically dispatching the constructor” based on the variable type `Animal`.

During the initialization of a Dog object, constructors along the superclass chain are invoked according to `this(...)`/`super(...)` and initialization rules, yet **constructors do not participate in overriding polymorphism** the way `speak()` does.

```java
// Animal animal = new Dog();
```

does not mean the runtime will arbitrarily look up another constructor based on `Animal`.

### Serious Pitfall: Superclass Constructor Calling an Overridable Method

Although constructors do not override, they **can call overridable instance methods**, and dynamic dispatch still occurs **before the subclass completes initialization**.

## 30. Dispatch Inside a Constructor: Observing Uninitialized Subclass Fields

Save **`ConstructorDispatchDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent constructor");
        describe();
    }

    void describe() {
        System.out.println("Parent describe");
    }
}

class Child extends Parent {
    private String state = initializeState();

    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child constructor");
    }

    private String initializeState() {
        System.out.println("Child field initializer");
        return "READY";
    }

    @Override
    void describe() {
        System.out.println("Child describe: " + state);
    }
}

public class ConstructorDispatchDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 ConstructorDispatchDemo.java
java ConstructorDispatchDemo
```

**Exact stdout:**

```text
Parent constructor
Child describe: null
Child field initializer
Child block
Child constructor
```

Step by step:

1. `new Child()` allocates the object containing state for Parent/Child, with fields initially receiving their **default values**.
2. The `Parent` constructor runs before `Child`'s instance initializer phase.
3. `Parent()` calls `describe()`; because this is an overridable instance method and the runtime receiver is `Child`, the JVM calls `Child.describe()`.
4. `Child.describe()` reads the `state` field, which is still `null` at this point.
5. Only after the Parent constructor finishes does `Child` run the initializer setting `state = "READY"`, the block, and the constructor body.

**Design principle:** avoid calling overridable methods from constructors or leaking `this` before the object is fully initialized. Use appropriately scoped private/final helpers, simple constructors, or post-construction initialization methods if needed.

Marking a method final can prevent subclass overriding, yet you must still check **whether it uses state that is already ready**; do not infer that final automatically makes all code safe.

## 31. Instance Method References and Lambdas Still Follow the Runtime Receiver

Method references take several forms:

- `receiver::instanceMethod`: *bound instance method reference*, receives an existing receiver object.
- `TypeName::instanceMethod`: *unbound instance method reference* when assigned to a compatible functional interface; the receiver comes from the call's argument.
- `TypeName::staticMethod`: static method reference, which does not perform instance dispatch like the two cases above.

If `Animal.speak()` is overridden in `Dog`, a call created using an appropriate instance method reference can still execute the override of the Dog runtime object.

### Runnable Program

Save **`MethodReferenceDispatchDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.Supplier;

class Animal {
    String sound() {
        return "Animal";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "Dog";
    }
}

public class MethodReferenceDispatchDemo {
    public static void main(String[] args) {
        Animal animal = new Dog();

        Supplier<String> bound = animal::sound;
        Function<Animal, String> unbound = Animal::sound;

        System.out.println(bound.get());
        System.out.println(unbound.apply(animal));

        animal = new Animal();
        System.out.println(bound.get());
        System.out.println(unbound.apply(animal));
    }
}
```

```bash
javac -encoding UTF-8 MethodReferenceDispatchDemo.java
java MethodReferenceDispatchDemo
```

**Stdout:**

```text
Dog
Dog
Dog
Animal
```

Explanation:
- `bound` is created from the receiver expression `animal` while it points to the Dog object; the method reference **retains the already-evaluated receiver**.
- `unbound` receives the receiver through its parameter on each `apply`, so the last call uses the new Animal object.
- Reassigning the variable `animal` does not change the receiver object previously bound to `bound`.
- In both forms of instance invocation, the override is still selected according to the runtime class of the receiver used in the call.

**Important:** do not confuse **when the receiver is chosen** with **the rules for selecting the implementation**.

## 32. Generic Interfaces Still Have Dynamic Dispatch

Generic methods/classes do not eliminate polymorphism:

```java
interface Transformer<T> {
    T transform(T value);
}
```

A concrete implementation:

```java
final class UppercaseTransformer
        implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
```

A client can use:

```java
Transformer<String> transformer = new UppercaseTransformer();
System.out.println(transformer.transform("java")); // JAVA
```

The compiler checks the contract's `String` type parameter, and the method invocation dispatches to the corresponding runtime implementation.

### Type Erasure and Bridge Methods

In Java generics, the compiler may generate **synthetic bridge methods** to preserve overriding behavior after **type erasure**.

For example, `Transformer<T>.transform(T)` has an erasure similar to `transform(Object)`; the implementation `UppercaseTransformer.transform(String)` needs an appropriate bridge so that calls through the erased interface still find the correct implementation.

That is an implementation detail handled by the **compiler/JVM**. You do not need to write `transform(Object)` yourself in the implementation; attempting to write the same name after erasure can cause a name clash.

## 33. Runnable Generics Dispatch Example

Save **`GenericDispatchDemo.java`**:

```java
import java.util.Locale;

interface Transformer<T> {
    T transform(T value);
}

final class UppercaseTransformer
        implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}

final class SuffixTransformer
        implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value + "!";
    }
}

public class GenericDispatchDemo {
    private static void show(
            Transformer<String> transformer, String text) {
        System.out.println(transformer.transform(text));
    }

    public static void main(String[] args) {
        show(new UppercaseTransformer(), "java");
        show(new SuffixTransformer(), "java");
    }
}
```

```bash
javac -encoding UTF-8 GenericDispatchDemo.java
java GenericDispatchDemo
```

Stdout:

```text
JAVA
java!
```

The example illustrates a generic interface in a static API combined with **dynamic dispatch** to two runtime implementations. Erased names/signatures and bridge behavior are handled by the compiler; client source code still works with `Transformer<String>`.

## 34. Runtime Objects from a Collection: Polymorphism in a Loop

An application often processes a collection containing multiple subtypes:

```java
List<Shape> shapes = List.of(
        new Circle(...),
        new Rectangle(...),
        new Triangle(...));
```

The call:

```java
for (Shape shape : shapes) {
    System.out.println(shape.area());
}
```

will dispatch each time to the corresponding implementation according to the runtime class of the **object retrieved from the list**, provided the `area()` method belongs to the `Shape` contract.

A `List<Shape>` **does not** require every element to have a runtime class equal to `Shape`. It can hold valid subtypes.

### Java 17 Program with Stable Output

Save **`CollectionDispatchDemo.java`**:

```java
import java.util.List;

interface Shape {
    int area();
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

record Square(int edge) implements Shape {
    @Override
    public int area() {
        return edge * edge;
    }
}

public class CollectionDispatchDemo {
    public static void main(String[] args) {
        List<Shape> shapes = List.of(
                new Rectangle(3, 4),
                new Square(5),
                new Rectangle(2, 6));

        for (Shape shape : shapes) {
            System.out.println(shape.area());
        }
    }
}
```

```bash
javac -encoding UTF-8 CollectionDispatchDemo.java
java CollectionDispatchDemo
```

Stdout:

```text
12
25
12
```

Records are **final classes** in Java 17, yet they can still implement `Shape` and provide interface method implementations. A final class cannot be subclassed, yet its objects **still participate in polymorphism through an interface**.

## 35. Dynamic Dispatch and Interface Segregation

If clients often have to downcast from an interface that is too broad or too narrow:

```java
if (animal instanceof Dog dog) {
    dog.fetch();
}
```

ask:
- Is `fetch` truly a required behavior for **every `Animal`**? If so, why is it not in the contract yet?
- If only some animals are capable of fetching, should there be a `Fetchable` interface?
- Should the client accept the `Fetchable` interface instead of `Animal` when that matches the use case?
- Is the set of variants closed so that sealed types/pattern matching can be used?

Example:

```java
interface Fetchable {
    void fetch();
}

class Dog extends Animal implements Fetchable {
    @Override
    public void fetch() {
        System.out.println("fetch");
    }
}
```

If a service only needs `fetch()`, the method can accept `Fetchable`. Runtime dispatch will run the receiver's implementation without forcing the client to know `Dog` specifically.

**Designing the right contract** usually brings greater benefits than scattering `instanceof`/casts to simulate dynamic dispatch manually.

## 36. Polymorphism Does Not Mean Multiple Inheritance

A Java class has only **one direct superclass**, yet can implement **multiple interfaces**.

```java
interface Printable {
    void print();
}

interface Savable {
    void save();
}

final class Report implements Printable, Savable {
    @Override
    public void print() {
        System.out.println("print");
    }

    @Override
    public void save() {
        System.out.println("save");
    }
}
```

`Report` is the concrete runtime class for both interface roles. A `Printable` reference can call `print()`; a `Savable` reference can call `save()`. Both are selected according to the runtime implementation of the Report object.

If a variable only has type `Printable`, you cannot call `save()` through that variable if `Printable` does not declare that method. You need a reference with an appropriate `Savable` type, for example through API design or an `instanceof` pattern when needed.

## 37. Dispatch in Lambda Callbacks and the Strategy Pattern

A strategy interface lets clients swap algorithms without knowing the concrete class:

```java
interface DiscountPolicy {
    int apply(int amount);
}
```

The service class holds a reference:

```java
final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = policy;
    }

    int total(int amount) {
        return policy.apply(amount);
    }
}
```

`policy.apply(...)` is an instance interface invocation: the compiler knows the `DiscountPolicy` contract, and runtime selects the implementation of the policy object.

If selecting:
- `FixedDiscount` runtime → fixed amount behavior.
- `PercentageDiscount` runtime → percentage behavior.
- A lambda implementing the functional interface `DiscountPolicy` → runs the matching lambda logic.

**Composition + interface polymorphism** is a very common combination. Checkout **uses** a policy; it **is** not a policy.

### Runnable Strategy Program

Save **`StrategyDispatchDemo.java`**:

```java
interface DiscountPolicy {
    int apply(int amount);
}

final class FixedDiscount implements DiscountPolicy {
    private final int off;

    FixedDiscount(int off) {
        this.off = off;
    }

    @Override
    public int apply(int amount) {
        return Math.max(0, amount - off);
    }
}

final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = policy;
    }

    int total(int amount) {
        return policy.apply(amount);
    }
}

public class StrategyDispatchDemo {
    public static void main(String[] args) {
        Checkout fixed = new Checkout(new FixedDiscount(20));
        Checkout percent = new Checkout(
                amount -> amount - amount / 10);

        System.out.println(fixed.total(100));
        System.out.println(percent.total(100));
    }
}
```

```bash
javac -encoding UTF-8 StrategyDispatchDemo.java
java StrategyDispatchDemo
```

Stdout:

```text
80
90
```

The callback logic is invoked through the interface contract. The results differ because **the runtime policy objects are different**, without needing subclasses of Checkout. The example only illustrates dispatch and strategy, and does not handle domain constraints on amounts or percentages in production.

## 38. Dispatch and Equality: An Overridden `equals` Can Affect Collections

`Object.equals(Object)` is an instance method that can be overridden according to Java's rules. When calling:

```java
Object left = new UserId("A");
Object right = new UserId("A");

left.equals(right);
```

the implementation of the runtime class `UserId` can be used if the class overrides `equals`.

Example of object identity vs. value equality:

```java
record UserId(String value) {
}
```

A record generates `equals/hashCode` based on its components; with `UserId("A")` and `UserId("A")`, `equals` returns true.

**Note:** an `equals` implementation must comply with the reflexive, symmetric, transitive, consistent, and non-null requirements under the Java API contract to work properly with collections. Incorrect overriding can cause `HashSet`/`HashMap` to produce unexpected results.

### Runnable Example

Save **`EqualsDispatchDemo.java`**:

```java
record UserId(String value) {
}

public class EqualsDispatchDemo {
    public static void main(String[] args) {
        Object first = new UserId("A");
        Object second = new UserId("A");
        Object third = new UserId("B");

        System.out.println(first.equals(second));
        System.out.println(first.equals(third));
        System.out.println(first == second);
    }
}
```

```bash
javac -encoding UTF-8 EqualsDispatchDemo.java
java EqualsDispatchDemo
```

Stdout:

```text
true
false
false
```

`first.equals(second)` dispatches to the equality behavior of the runtime record class, whereas `first == second` compares **object identity/reference values** without calling `equals`.

**Do not be confused:** `==` on references is not a method invocation and therefore does not perform dynamic dispatch.

## 39. `toString()` Is Also Polymorphic

`Object.toString()` can be overridden to represent an object in a more readable way.

```java
record Point(int x, int y) {
}
```

With `Object point = new Point(2, 3);`, `point.toString()` dispatches to the corresponding record implementation even though the variable is declared with type `Object`.

This can be made clearer with a class that provides its own override:

```java
class Item {
    private final int id;

    Item(int id) {
        this.id = id;
    }

    @Override
    public String toString() {
        return "Item#" + id;
    }
}
```

In `System.out.println(object)`, Java has a mechanism to convert an object to a string and may call `toString`; the fact that the output depends on the override is a familiar application of polymorphism.

### Runnable Example

Save **`ToStringDispatchDemo.java`**:

```java
class Item {
    private final int id;

    Item(int id) {
        this.id = id;
    }

    @Override
    public String toString() {
        return "Item#" + id;
    }
}

public class ToStringDispatchDemo {
    public static void main(String[] args) {
        Object value = new Item(7);

        System.out.println(value.toString());
        System.out.println(value);
    }
}
```

```bash
javac -encoding UTF-8 ToStringDispatchDemo.java
java ToStringDispatchDemo
```

Stdout:

```text
Item#7
Item#7
```

## 40. `getClass()` Reflects the Runtime Class, Yet Is Not an Overridden Method

`Object.getClass()` is a `final` native instance method according to the Java API. A subclass cannot override `getClass()`.

Nevertheless:

```java
Object value = new Dog();
System.out.println(value.getClass().getSimpleName());
```

returns the runtime class name of the object, which in the ordinary class example is `Dog`.

**Do not be mistaken:**
- `getClass()` returns information about the **runtime class**.
- Dynamic dispatch of the `speak()` method selects the overriding implementation based on the runtime object.
- Just because `getClass()` returns the runtime class does **not** mean a subclass has overridden `getClass()`; this method is final.

### Distinguishing Between `getClass()` and `instanceof`

`value instanceof Animal` returns true if the runtime object is compatible with `Animal`, including subtypes.

`value.getClass() == Animal.class` is true only if the runtime class is **exactly `Animal`** in the case of a normal class object, not a Dog subclass.

When writing polymorphic code, you generally **should not** check runtime class equality just to disable subtypes. Rely on the contract unless the domain requirement genuinely calls for an exact-type check.

## 41. Java 17 Sealed Hierarchy: Runtime Dispatch Within a Restricted Set of Subtypes

Java 17 has **sealed classes/interfaces** that help control which direct implementations/subclasses are allowed:

```java
sealed interface Result permits Success, Failure {
    String message();
}

record Success(String value) implements Result {
    @Override
    public String message() {
        return "OK " + value;
    }
}

record Failure(String reason) implements Result {
    @Override
    public String message() {
        return "ERROR " + reason;
    }
}
```

Caller:

```java
Result value = new Success("saved");
System.out.println(value.message()); // OK saved
```

still uses interface method dispatch. `sealed` restricts the hierarchy to the declared types, **without changing the instance method selection mechanism**.

### Runnable Program

Save **`SealedDispatchDemo.java`**:

```java
sealed interface Result permits Success, Failure {
    String message();
}

record Success(String value) implements Result {
    @Override
    public String message() {
        return "OK " + value;
    }
}

record Failure(String reason) implements Result {
    @Override
    public String message() {
        return "ERROR " + reason;
    }
}

public class SealedDispatchDemo {
    public static void main(String[] args) {
        Result first = new Success("saved");
        Result second = new Failure("invalid");

        System.out.println(first.message());
        System.out.println(second.message());
    }
}
```

```bash
javac -encoding UTF-8 SealedDispatchDemo.java
java SealedDispatchDemo
```

Stdout:

```text
OK saved
ERROR invalid
```

Records are final classes, yet still implement `Result`'s instance method and participate in dynamic dispatch through the interface.

## 42. JVM Bytecode Invocation: Understand the Idea, Avoid Rote Memorization

The Java compiler typically emits bytecode invocation forms corresponding to the semantics of the call:

| Invocation form | Typical role |
| --- | --- |
| `invokevirtual` | Invokes an instance method with virtual dispatch on a class receiver |
| `invokeinterface` | Invokes an instance method through an interface contract |
| `invokestatic` | Invokes a static method, with no instance receiver dispatch |
| `invokespecial` | Special invocations such as constructors, private methods, and `super` calls |
| `invokedynamic` | Dynamic call site mechanism; Java can use it to implement lambdas and other runtime features |

**Important warning:** do not treat the table as a rule that “whenever you see `invokevirtual`, the target method definitely has an override” or “every Java lambda always generates exactly one class in a single fixed way”. The JVM and javac can optimize or represent things differently within semantic bounds.

At the Java language level, what to remember is:
- **Instance overrides** can be selected according to the runtime class.
- **Static invocations** do not dispatch according to the runtime object.
- **Explicit superclass invocations** select the superclass implementation in a special way.
- **Overload resolution** has already taken place at compile time.

If you want to inspect the bytecode of a compiled runnable program, you can use:

```bash
javap -c DynamicDispatchDemo
```

This command prints the bytecode disassembly; this lesson does not include specific `javap` stdout because the output can contain compiler-dependent information and class file details. Use it for study; it does not change Java source rules.

## 43. The JVM Can Optimize Dispatch Without Changing the Result

The JVM's JIT compiler can:
- **Inline** method implementations when appropriate evidence exists.
- **Devirtualize** call sites when it knows which runtime classes can appear.
- Use profiling and speculative optimizations to improve performance.
- Recompile/deoptimize when optimization assumptions change.

However, optimizations must preserve the program's **observable behavior** according to Java semantics.

**Do not claim**:
- “Calling through an interface is always slower than calling through a concrete class.”
- “Adding `final` is guaranteed to make every method call faster.”
- “Dynamic dispatch always performs a reflection lookup by method name on every call.”

Those statements do not accurately describe modern Java/JVM. Choose your design based on the API, LSP, extensibility, and testing; if performance is decisive, measure with reliable benchmarks under a real workload.

## 44. Dynamic Dispatch Is Not Reflection

Reflection can look up methods via metadata at runtime, for example using `Class.getMethod` and `Method.invoke`. This is a **different API mechanism** from an ordinary `animal.speak()` call.

A call:

```java
animal.speak();
```

is type-checked and method-bound by the compiler at compile time according to Java's rules; the JVM performs the appropriate instance dispatch. A program **does not need** to write reflection code for polymorphism to work.

Reflection has different characteristics:
- Can retrieve metadata by name.
- Has checked exceptions/`InvocationTargetException` when using Method.invoke.
- Is subject to accessibility/module system constraints.
- Has different overhead and operating mechanisms.

**Do not use reflection just to “call the right subclass method”** when an interface/overriding is sufficient.

## 45. Limitations of Runtime Polymorphism

Dynamic dispatch does not automatically solve every design need:

**Not supported**:
- Calling a method that exists only on a subtype through a base variable without a corresponding cast/contract.
- Selecting an overload simply because the **runtime class of the arguments** is more specific.
- Changing the dynamic class of an existing object.
- Bypassing access modifier constraints.
- Overriding a final instance method or a private method as an inherited override.
- Dispatching a static method/field based on the runtime object.
- Automatically making a mutable object immutable.
- Automatically handling a null receiver.

When you see code full of casts or ``if (obj instanceof X)``, examine whether the abstraction properly represents the **common behavior**. Still, there are problems such as multi-type serialization, visitors, pattern matching on sealed types, or domain-specific routing where intentional subtype checking is reasonable.

## 46. Common Java Errors and How to Solve Them

| Symptom | True Cause | How to Fix |
| --- | --- | --- |
| `Animal a = new Dog(); a.fetch();` compile error | Type `Animal` does not have method `fetch()` | Use an interface matching the role, downcast safely, or change the API |
| Calling `Animal a = new Dog(); a.speak();` expecting the Animal version | Instance override dispatches according to runtime Dog | Call `super.speak()` inside the subclass when needed |
| `obj.staticMethod()` calls the superclass method | Static hiding selects according to the static type | Call `ClassName.staticMethod()` explicitly |
| `obj.field` reads the superclass field | Field access is not virtual | Use a polymorphic getter or avoid field hiding |
| Overload selects `handle(Animal)` even though the runtime argument is Dog | Overload resolution uses the static type of the argument | Adjust the signature/cast intentionally, or design with polymorphism |
| Removing `@Override` to avoid a final override error | The annotation is not the cause | Do not override a final method |
| Subclass private method shares the same name, yet parent still runs the private version | Private methods are not overridden through regular inheritance | Use a protected/public contract if overriding is truly needed |
| `((Parent)this).work()` keeps calling Child's override | Casting does not change the runtime class and still uses virtual dispatch | Use `super.work()` inside a valid instance method |
| `Dog dog = (Dog) new Cat();` causes an error | The runtime object is incompatible with Dog | `instanceof` pattern or change the model |
| Null receiver causes `NullPointerException` | There is no runtime object to invoke on | Check for non-null or change the contract |
| Parent constructor calls Child override and reads a null field | Dispatch runs before Child's initializer | Do not call overridable methods from a constructor |
| Interface default is superseded by a class method | Class implementation wins according to resolution rules | Understand the hierarchy or override explicitly |
| Two unrelated default methods conflict | Cannot pick a default based solely on implements order | Override to resolve explicitly |
| Covariant return type on method, yet base call still has type Animal | Compile-time expression type follows the base signature | Use a subtype reference/cast when needed |
| Generic bridge method causes confusion when decompiling | Type erasure needs to preserve overriding | Rely on the source generic contract; do not write bridges manually |
| Thinking a final class does not participate in polymorphism | Final only prevents subclassing that class | It can implement an interface and dispatch through the interface |
| Thinking runtime dispatch uses reflection every time | JVM virtual invocation has its own mechanism | Reflection is not needed for polymorphism |
| Using `instanceof` everywhere in code to invoke behavior | The abstraction may be placed in the wrong spot | Move common behavior into an interface/base method |
| Assuming two methods with the same name mean overriding | It could be overloading/hiding/a private method | Check signature, static/instance, visibility, return type, and exceptions |
| Assuming the compiler ignores overloading because a runtime type exists | Compile time resolves it before invocation | Distinguish between compile-time and runtime stages |

## 47. Method for Solving “What Does This Print?” Problems Yourself

When encountering polymorphic code, follow a **fixed order**:

1. **Draw the class/interface hierarchy**. Mark `extends` and `implements`.
2. **Identify the static type of the receiver expression**. For example, `Animal a` → `Animal`.
3. **Identify the runtime object of the receiver** at the call site. For example, `a = new Dog()` → Dog.
4. **Look at the method name and arguments**. Are there multiple overloads? What is the static type of each argument?
5. **Select the valid signature at compile time**, checking access and applicable overloads.
6. **Check the member kind**: static method? instance method? field? constructor? special `super` call?
7. **If it is an overridable instance method**, follow the runtime class to select the matching overriding implementation; it may inherit the implementation from an intermediate superclass.
8. **Read the body of the invoked implementation**; inside, it may in turn call other virtual methods.
9. **Check for `null`/casts/runtime exceptions**, especially inside constructors and initializers.
10. **Write out stdout line by line** based on execution order and the newlines of `print/println`.

### Table Template for Learners

| Expression | Static receiver type | Runtime receiver | Compile-time signature | Runtime implementation |
| --- | --- | --- | --- | --- |
| `a.speak()` | `Animal` | `Dog` | `speak()` of the Animal contract | `Dog.speak()` |
| `a.toString()` | `Animal` | `Dog` | `toString()` inherited from Object | Override according to the runtime object if present |
| `a.staticLabel()` | `Animal` | `Dog` | Static label of Animal | No runtime virtual dispatch |
| `a.field` | `Animal` | `Dog` | Field of Animal | Field access does not dispatch |
| `handler.handle(a)` | `Handler` | `SpecialHandler` | `handle(Animal)` because a is static Animal | `SpecialHandler.handle(Animal)` if overridden |
| `((Animal) dog).speak()` | `Animal` after cast | `Dog` | `speak()` seen through Animal | `Dog.speak()` |
| `super.speak()` in Dog | Special super invocation | `Dog` object | Superclass method selected specially | Specified superclass implementation |

## 48. Exercise 1 — Same Variable Type, Different Objects

```java
class A {
    String value() { return "A"; }
}

class B extends A {
    @Override
    String value() { return "B"; }
}

class C extends A {
    @Override
    String value() { return "C"; }
}

A x = new B();
A y = new C();
System.out.println(x.value());
System.out.println(y.value());
```

**Answer:**

```text
B
C
```

The method signature seen through A is the same, while the runtime receivers differ, so the implementations differ.

## 49. Exercise 2 — Subclass Does Not Override

```java
class A {
    String value() { return "A"; }
}

class B extends A {
    @Override
    String value() { return "B"; }
}

class C extends B {
}

A ref = new C();
System.out.println(ref.value());
```

**Answer:** `B`. `C` inherits the `B.value()` implementation and does not force the JVM to fall back to `A.value()`.

## 50. Exercise 3 — Overloading by Argument

```java
class Animal { }
class Dog extends Animal { }

class Printer {
    void show(Animal a) { System.out.println("Animal"); }
    void show(Dog d) { System.out.println("Dog"); }
}

Animal animal = new Dog();
new Printer().show(animal);
```

**Answer:** `Animal`. The compiler selects the overload based on the **static type of the argument `animal`**, not the runtime Dog.

## 51. Exercise 4 — Overloading Combined with Overriding

```java
class A { }
class B extends A { }

class Parent {
    String work(A value) { return "P-A"; }
    String work(B value) { return "P-B"; }
}

class Child extends Parent {
    @Override
    String work(A value) { return "C-A"; }
}

Parent p = new Child();
A arg = new B();
System.out.println(p.work(arg));
```

**Answer:** `C-A`. The overload signature `work(A)` is selected by the compiler because `arg` has static type A; the override `Child.work(A)` is called because the runtime receiver object is Child.

## 52. Exercise 5 — Static Hiding

```java
class Parent {
    static String name() { return "Parent"; }
}

class Child extends Parent {
    static String name() { return "Child"; }
}

Parent ref = new Child();
System.out.println(ref.name());
```

**Answer:** `Parent`. Static methods do not virtually dispatch according to Child at runtime; avoid calling them through an instance reference in production code.

## 53. Exercise 6 — Field Hiding

```java
class Parent {
    String label = "P";
}

class Child extends Parent {
    String label = "C";
}

Parent ref = new Child();
System.out.println(ref.label);
System.out.println(((Child) ref).label);
```

**Answer:**

```text
P
C
```

Field lookup is based on the static type of the expression, not the runtime class.

## 54. Exercise 7 — Casting Does Not Change Dispatch

```java
class Parent {
    String name() { return "P"; }
}

class Child extends Parent {
    @Override
    String name() { return "C"; }
}

Child child = new Child();
System.out.println(((Parent) child).name());
```

**Answer:** `C`. The cast changes the static view, not the Child runtime object.

## 55. Exercise 8 — `super` Is a Special Selection

```java
class Parent {
    String name() { return "P"; }
}

class Child extends Parent {
    @Override
    String name() {
        return super.name() + "C";
    }
}

System.out.println(new Child().name());
```

**Answer:** `PC`. Runtime selects Child's override; inside it, `super.name()` calls Parent's implementation.

## 56. Exercise 9 — Private Method

```java
class Parent {
    private String name() { return "P"; }

    String read() { return name(); }
}

class Child extends Parent {
    String name() { return "C"; }
}

System.out.println(new Child().read());
```

**Answer:** `P`. `Child.name()` does not override the private `Parent.name()`. `Parent.read()` calls Parent's private method.

## 57. Exercise 10 — Constructor Virtual Call

```java
class Parent {
    Parent() { show(); }
    void show() { System.out.println("P"); }
}

class Child extends Parent {
    int number = 5;

    @Override
    void show() {
        System.out.println(number);
    }
}

new Child();
```

**Answer:** `0`. Runtime selects Child's override when the Parent constructor calls show, yet the `number = 5` initializer has not run yet.

## 58. Exercise 11 — Final Method

```java
class Parent {
    final String type() { return "fixed"; }
}

class Child extends Parent {
}

System.out.println(new Child().type());
```

**Answer:** `fixed`. A final method can be inherited/called, yet cannot be overridden.

## 59. Exercise 12 — Interface Runtime Dispatch

```java
interface Task {
    String run();
}

class EmailTask implements Task {
    public String run() { return "email"; }
}

class FileTask implements Task {
    public String run() { return "file"; }
}

Task task = new EmailTask();
System.out.println(task.run());

task = new FileTask();
System.out.println(task.run());
```

**Answer:**

```text
email
file
```

The interface-typed variable points to different runtime implementations; the calls are dispatched accordingly.

## 60. Exercise 13 — Default Interface and Class Wins

```java
interface Label {
    default String get() { return "I"; }
}

class Parent {
    public String get() { return "P"; }
}

class Child extends Parent implements Label {
}

Label value = new Child();
System.out.println(value.get());
```

**Answer:** `P`. The class method implementation takes precedence over the default method in this valid case.

## 61. Exercise 14 — Covariant Return

```java
class Parent {
    Number count() { return 1; }
}

class Child extends Parent {
    @Override
    Integer count() { return 2; }
}

Parent ref = new Child();
Number value = ref.count();
System.out.println(value);
```

**Answer:** `2`. Runtime selects Child's override returning Integer, while the compile-time return type seen through Parent is Number.

## 62. Exercise 15 — Method Reference with Bound Receiver

```java
class Parent {
    String label() { return "P"; }
}

class Child extends Parent {
    @Override
    String label() { return "C"; }
}

Parent x = new Child();
java.util.function.Supplier<String> f = x::label;
x = new Parent();

System.out.println(f.get());
System.out.println(x.label());
```

**Answer:**

```text
C
P
```

`f` retains the Child receiver object from when the method reference was created; reassigning the variable `x` does not change the bound receiver.

## 63. Exercise 16 — Compile-Time Type Does Not Know Subclass Methods

```java
class Animal {
    void speak() { }
}

class Dog extends Animal {
    void fetch() { }
}

Animal animal = new Dog();
// animal.fetch();
```

**Answer:** If uncommented, this produces a compile error because `fetch` is not in the contract seen through `Animal`. You can use `instanceof Dog dog` to call `dog.fetch()` or design a `Fetchable` interface if the use case requires it.

## 64. Exercise 17 — `null` and Runtime Receiver

```java
class Animal {
    String sound() { return "A"; }
}

Animal value = null;
// value.sound();
```

**Answer:** If uncommented and run, it throws a `NullPointerException` (when the instance call is evaluated) because the receiver is null. This is not a compiler error when the method is type-valid.

## 65. Exercise 18 — Record Implements Interface

```java
interface Identified {
    String id();
}

record User(String id) implements Identified {
}

Identified ref = new User("A");
System.out.println(ref.id());
```

**Answer:** `A`. A final record still provides the `id()` implementation via the record component accessor and participates in interface method dispatch.

## 66. Checklist for Checking Polymorphic Programs

1. Have you identified the **declared type** of the receiver expression?
2. Have you identified the **runtime class** of the receiver object at the call site?
3. Is the method **present/accessible through the static type** of the receiver?
4. Are there any **overloads** with the same name? Have you selected the signature using the **static types of the arguments**?
5. Is the member an **instance method**, a **static method**, or a **field**?
6. If it is an instance method, is it a valid override according to signature/access/return/exception rules?
7. Does the runtime class have its own override or inherit an override from an intermediate superclass?
8. Is the method **`final`**? If so, is overriding locked for subclasses?
9. Is the superclass method **`private`**? Do not infer that a subclass method with the same name is an override.
10. Is there a `super.method()`/`Interface.super.method()` special invocation?
11. Is there an **interface default method** competing with a class method or another interface default?
12. Is a **cast** being used only to change the visible type? Remember that a cast does not change the object.
13. Is there a **null receiver** or an invalid downcast causing a runtime exception?
14. Is there a **constructor calling an overridable method** before the subclass completes initialization?
15. Is there generic type erasure or a covariant return causing the compile-time syntax to differ from the runtime bridge?
16. Are static methods being called **through an object reference**, causing confusion about runtime dispatch?
17. Is there field hiding with the same name across classes? Should methods/encapsulation be used instead?
18. Is `instanceof` being used repeatedly to manually dispatch behavior that polymorphism can solve?
19. Is a smaller role interface needed to avoid downcasting for a subclass-specific API?
20. Is there a false performance assumption that virtual dispatch is always slow or always uses reflection?
21. Have you checked **stdout** line by line considering both static resolution and dynamic implementation?
22. When replacing an implementation with a new subclass, does the LSP contract of the base/interface still hold?

## Key Takeaways

- **The static type determines the valid API/method signature at compile time**; **the runtime class of the receiver** determines the implementation of an **overridden instance method**.
- **Overloading** is selected according to the static types of the arguments; the runtime type of an argument does **not** automatically make the compiler select a different overload.
- **Instance methods** called through a superclass/interface reference can dispatch to an override in the concrete subtype, even when the subtype does not write its own override and inherits it from an intermediate class.
- **Static methods** use hiding/static binding, and **fields** use hiding/field resolution by static type; they are not polymorphic like instance methods.
- **Casting** does not change the runtime object; casting up to a superclass does not force calling the superclass method implementation. `super.method()` is a separate mechanism.
- **Private** methods are not overridden through ordinary inheritance relationships; **final** methods lock overriding; **abstract** methods require valid implementations.
- **Default interface methods**, **covariant returns**, **generic bridge methods**, and **record/sealed types** all must follow Java's contract + runtime invocation model.
- **Constructors are not overridden**, yet an overridable method called from a constructor can dispatch to a subclass before the subclass state is ready.
- A **null receiver** has no object to invoke on; dynamic dispatch does not bypass access control or compile-time type checking.
- Write polymorphic code against a **meaningful interface/base contract**, preserve LSP, and use composition/strategies when you want to swap collaborators; do not replace polymorphism with a web of unnecessary casts/`instanceof` checks.
