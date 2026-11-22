# `extends`, Superclasses, Subclasses, and Subtype Relationships in Java

## 1. Goals and Core Idea

In Java, **class inheritance** allows a new class to **extend** an existing class, receiving its inheritable members and adding or overriding behavior according to the rules of the language. The class being extended is called the **superclass**; the class that declares `extends` is called the **subclass**.

The `extends` keyword is not just for "reusing a few lines of code." It also establishes a **subtype relationship**: in valid contexts, a subclass object can be used through a reference of the superclass type. This is the foundation for **polymorphism** and for designing APIs that can accept multiple object types conforming to the same contract.

Minimal example:

~~~java
class Animal {
    void eat() {
        System.out.println("Eating");
    }
}

class Dog extends Animal {
    void bark() {
        System.out.println("Woof");
    }
}
~~~

These are **two illustrative classes**, without a `main` to run standalone.

- `Animal` is the direct superclass of `Dog`.
- `Dog` is a subclass of `Animal`.
- `Dog` can use the instance method `eat()` inherited from `Animal`.
- `Dog` declares an additional method `bark()`.
- A variable of type `Animal` can refer to a `Dog` object: `Animal animal = new Dog();`.
- The reverse direction is **not automatically valid**: not every Animal is a Dog.

**Design question to answer before writing `extends`:** *"Can every instance of the subclass truly be used as an instance of the superclass according to the published contract?"* If the answer is no, you most likely need **composition**, an interface, or a different model.

This Knowledge README targets **Java 17+**. It explains the is-a relationship, `extends` syntax, member inheritance, access, constructors and initialization, subtypes/upcasting/downcasting, static and runtime types, overriding and dynamic dispatch, hiding, abstract/final/sealed classes, interfaces, generics, records, design mistakes, and exercises. Standalone runnable programs list the file, `javac`/`java` commands, and stdout.

## 2. How Is `extends` Written?

Common syntax:

~~~java
class Parent {
}

class Child extends Parent {
}
~~~

Class `Child` declares **one direct superclass**, `Parent`. It can extend that with its own methods, fields, constructors, and nested declarations.

An inheritance chain:

~~~java
class LivingThing {
}

class Animal extends LivingThing {
}

class Dog extends Animal {
}
~~~

These relationships exist:

- `Animal` is a **direct subclass** of `LivingThing`.
- `Dog` is a **direct subclass** of `Animal`.
- `Dog` is an **indirect subclass** of `LivingThing`.
- `LivingThing` is the direct/indirect superclass respectively.
- `Dog` is a subtype of `Animal` and `LivingThing` under class inheritance.

### 2.1. Java Allows Only One Direct Class Superclass

Java **does not support multiple inheritance of classes**:

~~~java
class A {
}

class B {
}

// class C extends A, B { } // Invalid in Java
~~~

A class with multiple collaborating behaviors can **implement multiple interfaces** and use composition instead of trying to extend multiple classes:

~~~java
interface Printable {
    void print();
}

interface Saveable {
    void save();
}

class Document implements Printable, Saveable {
    @Override
    public void print() {
        System.out.println("Print");
    }

    @Override
    public void save() {
        System.out.println("Save");
    }
}
~~~

`Document` is a **subtype** of both `Printable` and `Saveable` even though it does not directly `extends` two classes. An interface is a different type relationship from a class superclass; this article distinguishes them carefully in a later section.

### 2.2. When `extends` Is Omitted

An ordinary class that does not declare an explicit superclass has `java.lang.Object` as its direct superclass according to Java rules:

~~~java
class Box {
}
~~~

In terms of class relationships, `Box` directly inherits from `Object`. `Object` itself is the root class of the ordinary class hierarchy. You cannot write `class X extends String` because `String` is `final`; nor can you inherit from a user-defined `final` class.

### 2.3. Type Relationships and Object Relationships Are Not the Same

`Dog extends Animal` is a **relationship between two classes/types**. `Dog ownerDog = new Dog();` creates an **object** of runtime type Dog; that object has state/methods defined according to the superclass chain and the Dog declarations.

There are not two separate objects—"an Animal object inside a Dog object"—under Java semantics. The Animal constructor and the Dog constructor both participate in initializing **a single Dog object**. Field hiding can create two different fields within the same object, but it does not turn it into two independent objects.

## 3. "Is-a" and Substitutability

The `extends` relationship is often explained as **"Dog is an Animal"**: every Dog object can also be used as an Animal object when the program only needs Animal's contract.

~~~java
void feed(Animal animal) {
    animal.eat();
}
~~~

This is an **illustrative method snippet**, placed inside an appropriate class. A caller can pass `new Dog()` for the parameter `Animal animal`:

~~~java
feed(new Dog());
~~~

That is an expression of **subtype polymorphism**: the same `feed(Animal)` call accepts multiple object subtypes.

**However, the compiler only checks type relationships and language rules**. It does not automatically know whether a subclass actually preserves the **business semantics** that callers expect from the superclass. Therefore, "it compiles" is not synonymous with "correct design."

### 3.1. Liskov Substitution Principle (LSP)

A practical way to understand this: if code uses `Parent` according to Parent's contract, replacing a Parent object with a Child object should preserve the important expectations of that contract.

Examples of contracts:

- If the superclass `withdraw(amount)` allows withdrawing any valid amount within the balance, a subclass should not secretly tighten the conditions unreasonably and break all previous callers.
- If the superclass promises that state is always non-negative, the subclass must not break that invariant.
- If a superclass method guarantees a result corresponding to its input, the override needs to maintain an appropriate postcondition.
- If a public method has clearly specified side effects, a subclass should not silently omit them or replace them with conflicting effects.

LSP is a **design principle**, not a Java compiler rule that checks all preconditions/postconditions.

### 3.2. A Has-a Relationship Should Not Be Confused with Is-a

A `Car` **has** an `Engine`; a Car **is** not an Engine. In such a design, `Car extends Engine` is usually the wrong model. Replace it with composition:

~~~java
interface Engine {
    void start();
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    void start() {
        engine.start();
    }
}
~~~

Inheritance expresses a subtype contract, while composition expresses that an object **uses/has** a component. Do not use `extends` just because you want to call an existing helper method.

## 4. Terminology to Distinguish

| Term | Meaning |
| --- | --- |
| Superclass | A class directly/indirectly extended by another class |
| Direct superclass | The class appearing immediately after `extends` in a subclass |
| Subclass | A class that extends a superclass |
| Subtype | A type that can be used in certain contexts requiring a supertype according to Java rules |
| Supertype | A broader type, such as a superclass or superinterface |
| Inheritance | The mechanism by which a class/interface inherits members and establishes a type relationship |
| Overriding | A subclass providing an instance method implementation for an eligible inherited method |
| Overloading | Methods with the same name but different parameter lists, without necessarily depending on inheritance |
| Upcasting | Using a subtype reference/expression under a supertype |
| Downcasting | Casting a broader-typed reference to a subtype, requiring a valid runtime condition |
| Dynamic dispatch | Selecting the implementation of an overridable instance method based on the receiver's runtime class |
| Field hiding | Declaring a field with the same name that hides an inherited field |
| Static method hiding | A subclass static method hiding a matching superclass static method; not overriding |
| Composition | Combining objects via has-a/uses-a rather than subtype inheritance |

In the examples, the term "static type" (*compile-time type*) refers to the type the compiler knows for an expression or variable. "Runtime type" is the actual class of the object at runtime. These two concepts govern two different parts of the polymorphism mechanism.

## 5. Which Members Are Inherited?

A subclass may have permission to use eligible **instance methods**, **fields**, and **static members** of its superclass according to inheritance and access control rules. However, "inheritance" **does not mean** that every declaration in the superclass is copied into a separate declaration inside the subclass.

Example:

~~~java
class Account {
    protected long balance;

    public long getBalance() {
        return balance;
    }

    protected void deposit(long amount) {
        balance += amount;
    }

    private void audit(String event) {
        System.out.println(event);
    }
}

class SavingsAccount extends Account {
    void earnBonus() {
        deposit(5);
    }
}
~~~

This is a syntax illustration, not a production account design: `deposit` does not have validation or overflow checks yet.

`SavingsAccount` can use eligible members of `Account`, such as `getBalance()` and `deposit(...)`. However, `audit(String)` is **private** and is not inherited by the subclass as a method it can call directly.

### 5.1. Visibility of Superclass Members

| Modifier | Typical Access Meaning |
| --- | --- |
| `public` | The member can be accessed where class/member and module visibility allow |
| `protected` | Allows access within the same package and in subclasses according to special rules |
| No modifier (package-private) | Accessible within the same package |
| `private` | Only within the scope Java permits for the declaring class/nest; not inherited as an accessible member in a subclass |

Be careful: protected in **a different package** is not equivalent to public. In a subclass in another package, accessing a protected instance member through an **arbitrary receiver expression of the superclass type** can be rejected by the compiler. You must follow the receiver type and context rules; the safe approach is to use the member on `this`/an appropriate subclass receiver when the contract permits.

### 5.2. A Private Field Still Exists in the Object's Superclass State

If a superclass has `private int secret`, that does not mean the field is removed from the subclass object. The subclass simply **is not allowed direct access under access rules**. Superclass methods can still use that field on the same object.

~~~java
class Base {
    private int count = 3;

    public int count() {
        return count;
    }
}

class Derived extends Base {
    int readCount() {
        return count(); // Uses the inherited public method
    }
}
~~~

`Derived` can read the result via `count()` without needing or being allowed to use `this.count` directly.

### 5.3. Constructors **Are Not Inherited**

`Child extends Parent` **does not** make Parent's constructors become constructors of Child. To initialize the superclass part, a Child constructor **calls** a Parent constructor using `super(...)` (explicitly or implicitly), but a caller cannot treat `Parent(int)` as `Child(int)` automatically just because Child extends Parent.

### 5.4. Static Methods/Fields Also Have Inheritance Rules, but No Instance Overriding

A subclass can access an inherited static field/method when valid. However, static methods **do not dispatch on the runtime object**. If a subclass declares a static method with the corresponding signature, it **hides**, rather than overrides, the superclass method. A field with the same name can also hide another field. A separate program will illustrate this.

## 6. Complete Program 1: Subclasses Are Subtypes and Overriding Creates Polymorphism

Create the file **`AnimalHierarchyDemo.java`**:

~~~java
import java.util.List;

public class AnimalHierarchyDemo {
    static abstract class Animal {
        private final String name;

        protected Animal(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
            this.name = name;
        }

        public final String name() {
            return name;
        }

        public abstract String sound();

        public String describe() {
            return name() + " says " + sound();
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        public String sound() {
            return "Woof";
        }

        public void fetch() {
            System.out.println(name() + " fetches");
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }

        @Override
        public String sound() {
            return "Meow";
        }
    }

    static void introduce(Animal animal) {
        System.out.println(animal.describe());
    }

    public static void main(String[] args) {
        Dog dog = new Dog("Milo");
        Cat cat = new Cat("Luna");

        Animal first = dog; // Upcast, does not create a new object
        Animal second = cat;

        introduce(first);
        introduce(second);

        List<Animal> animals = List.of(first, second);
        for (Animal animal : animals) {
            System.out.println(animal.name() + ":" + animal.sound());
        }

        dog.fetch();

        System.out.println("Dog is Animal = " + (dog instanceof Animal));
        System.out.println("Same object = " + (first == dog));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 AnimalHierarchyDemo.java
java AnimalHierarchyDemo
~~~

**Exact stdout:**

~~~text
Milo says Woof
Luna says Meow
Milo:Woof
Luna:Meow
Milo fetches
Dog is Animal = true
Same object = true
~~~

**Analysis:**

1. `Animal` is an **abstract superclass** with a private field `name` and a public method `name()`. The Animal constructor validates the name.
2. `Dog extends Animal` and `Cat extends Animal`, so Dog and Cat are **subtypes** of Animal.
3. Each subclass calls `super(name)` in its constructor so Parent initializes the field belonging to the superclass part.
4. The `sound()` method is abstract in Animal; Dog/Cat must implement it because they are concrete classes.
5. `Animal first = dog` is a valid **upcast**; it does not clone the Dog object and does not call a new constructor. The identity remains the same Dog object.
6. `introduce(Animal animal)` calls `animal.describe()`. Inside `describe()`, the `sound()` call continues to dispatch based on the runtime object: Dog → Woof, Cat → Meow.
7. The loop over `List<Animal>` handles two concrete runtime types using the same contract.
8. `dog.fetch()` is valid because the `dog` variable has compile-time type Dog. `first.fetch()` will **not compile** without casting or narrowing the type, because the compiler only sees the Animal API on `first`.
9. `dog instanceof Animal` is true; `first == dog` is true because upcasting does not create a new object.

This is an example of **polymorphism based on subtypes and overriding**, rather than a set of `if (type == Dog)` or `if (type == Cat)` checks written manually for each class.

## 7. Static Type and Runtime Type

Consider:

~~~java
Animal pet = new Dog("Milo");
~~~

Two facts hold simultaneously:

- **Compile-time type of `pet`:** `Animal`.
- **Runtime class of the object that `pet` refers to:** `Dog`.

When the compiler analyzes `pet.someMethod()`, it checks whether the method can be called through the **static type Animal**. If valid and it is an overridable instance method, runtime dispatch can select the implementation of **Dog**.

~~~java
pet.sound(); // Valid if Animal declares sound()
~~~

~~~java
// pet.fetch(); // Compile error: Animal does not have fetch()
~~~

These are fragments based on the classes from the previous example. The runtime object being a Dog **does not automatically make the compiler accept a method that only exists in Dog** on a variable declared as Animal.

### 7.1. Upcasting Is Reference Assignment and Does Not Turn an Object into Another Superclass Object

~~~java
Dog dog = new Dog("Milo");
Animal animal = dog;
~~~

`animal` and `dog` refer to **one object**. Upcasting does not create a separate Animal object, does not strip away the Dog state, and does not change the object's runtime class.

However, the API callable **through the animal variable** is limited by its **static type**. This is an intentional safety design: code that accepts Animal should rely only on the Animal contract, rather than assuming every Animal is a Dog.

### 7.2. Every Subclass Is an Instance of Its Superclass, but Not Vice Versa

If Parent is concrete:

~~~java
class Vehicle {
}

class Car extends Vehicle {
}
~~~

`Vehicle v = new Car();` is valid. `Car c = new Vehicle();` is invalid because a Vehicle object is not necessarily a Car. Using an explicit cast also does not turn an object that is a Vehicle into a Car.

### 7.3. `null` Can Be Assigned to Subtype/Supertype References

~~~java
Animal animal = null;
Dog dog = null;
~~~

Both assignments are valid for reference types. However, `animal.sound()` when `animal == null` will throw `NullPointerException`. The subtype relationship does not eliminate null dereference rules.

`null instanceof Dog` evaluates to **false**. Using `instanceof` with pattern matching can help check the object before calling subtype-only APIs.

## 8. Overriding: The Subclass Replaces the Implementation, Not the Contract Arbitrarily

A subclass overrides an **instance method** when it declares a method matching the signature and Java rules:

~~~java
class Parent {
    String label() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String label() {
        return "Child";
    }
}
~~~

With `Parent p = new Child();`, calling `p.label()` can return `"Child"` due to dynamic dispatch.

### 8.1. `@Override` Should Be Used

`@Override` asks the compiler to verify that the method actually overrides/implements an eligible method. It helps catch typos:

~~~java
class Base {
    void execute() {
    }
}

class Derived extends Base {
    // @Override
    // void excute() { } // Misspelled, the compiler will report it
}
~~~

It is not syntactically required for every override, but it is generally a useful habit to catch signature mismatches when modifying a superclass API.

### 8.2. Some Important Conditions When Overriding

When a subclass overrides an instance method:

- It must not **reduce the access level** of the overriding method, for example from `public` to `protected`.
- The return type must be compatible; Java allows **covariant return types** for reference types.
- For **checked exceptions**, the overriding method must not broaden checked exceptions in violation of the rules of the overridden method.
- A `final` instance method cannot be overridden.
- A static method cannot be used to override an instance method with the same signature.
- A `private` superclass method is not overridden by a subclass as an ordinary inherited method.
- Overloading with a different parameter list is **not** overriding.
- You need to follow the business contract (LSP), in addition to the rules the compiler can check.

Covariant return example:

~~~java
class Food {
}

class Bone extends Food {
}

class Animal {
    Food favoriteFood() {
        return new Food();
    }
}

class Dog extends Animal {
    @Override
    Bone favoriteFood() {
        return new Bone();
    }
}
~~~

This is an illustrative snippet. The return type `Bone` is a subtype of `Food`, so Java allows the override to return a more specific type. The compiler may generate *bridge methods* in generics/covariant cases where compatibility needs to be ensured; that is a compiler mechanism, not something required to be written by hand here.

### 8.3. Instance Dispatch Can Continue from Superclass Code

~~~java
class Parent {
    String describe() {
        return "P:" + value();
    }

    String value() {
        return "base";
    }
}

class Child extends Parent {
    @Override
    String value() {
        return "child";
    }
}
~~~

With `new Child().describe()`, the `Parent.describe()` implementation can run (if describe is not overridden), yet the `value()` call inside it can still dispatch to `Child.value()`. This is the foundation of **template method**, while also creating a risk if a hook is called too early inside a constructor.

## 9. Constructors, `super(...)`, and the Subclass Initialization Process

A subclass cannot bypass superclass initialization. If a subclass constructor does not write an explicit constructor invocation, the compiler will attempt to use an implicit `super()` according to Java 17 rules.

~~~java
class Base {
    Base() {
        System.out.println("Base constructor");
    }
}

class Child extends Base {
    Child() {
        // super() is called implicitly before the constructor body.
        System.out.println("Child constructor");
    }
}
~~~

Creating `new Child()` prints Base before Child.

If Base **does not have an accessible no-arg constructor**, Child must call an appropriate constructor:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }
}

class Employee extends Person {
    private final int employeeNumber;

    Employee(String name, int employeeNumber) {
        super(name);
        this.employeeNumber = employeeNumber;
    }
}
~~~

`super(name)` is a **constructor invocation**; it does not mean "create a separate Person object." The superclass state is initialized on the same Employee object being constructed.

### 9.1. Constructors Are Not Inherited

If only `Person(String)` exists, the compiler **does not** automatically generate an `Employee(String)` with an equivalent body. Employee must declare an appropriate constructor or have a valid default constructor if conditions allow.

### 9.2. Basic Initialization Order

For a subclass instance:

1. The object's fields first have **default values**.
2. The superclass constructor chain is executed according to the rules.
3. Each class's field initializers and instance initializer blocks run during the phase when that class is initialized, in the appropriate declaration order.
4. The subclass constructor body runs after the superclass step, aside from `this(...)` constructor chaining details.
5. Only when all steps complete normally does the caller receive the object from `new`.

Distinguish **instance initialization** from **static class initialization**. Static fields/blocks have their own class initialization rules; they do not re-run once per created object.

### 9.3. Special Risk: Calling an Overridable Method from a Constructor

A superclass constructor calling `hook()` can dispatch to a subclass override **before subclass fields are initialized**:

~~~java
class Base {
    Base() {
        hook(); // Dangerous if the Child override uses state that is not ready yet.
    }

    void hook() {
    }
}

class Child extends Base {
    private String message = "ready";

    @Override
    void hook() {
        System.out.println(message);
    }
}
~~~

When `new Child()` runs, `hook()` can print `null`, because Child's field initializer `message = "ready"` has not run yet. **Do not use a constructor as a place to call polymorphic hooks based on subclass state**. Pass the required data via `super(args)` or call the hook **after the entire object has completed its constructor**.

## 10. Complete Program 2: Superclass and Subclass Initialization Order

Create the file **`ConstructorOrderDemo.java`**:

~~~java
public class ConstructorOrderDemo {
    static class Base {
        private final String id;
        private int baseValue = initBaseValue();

        private int initBaseValue() {
            System.out.println("Base field initializer");
            return 10;
        }

        Base(String id) {
            this.id = id;
            System.out.println("Base constructor " + id);
        }

        public final String id() {
            return id;
        }

        public final int baseValue() {
            return baseValue;
        }
    }

    static final class Child extends Base {
        private int childValue = initChildValue();
        private final String tag;

        private int initChildValue() {
            System.out.println("Child field initializer");
            return 20;
        }

        Child(String id, String tag) {
            super(id);
            this.tag = tag;
            System.out.println("Child constructor " + tag);
        }

        String summary() {
            return id() + "/" + tag
                    + "/base=" + baseValue()
                    + "/child=" + childValue;
        }
    }

    public static void main(String[] args) {
        System.out.println("Before");
        Child child = new Child("ID-1", "X");
        System.out.println("After = " + child.summary());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstructorOrderDemo.java
java ConstructorOrderDemo
~~~

**Exact stdout:**

~~~text
Before
Base field initializer
Base constructor ID-1
Child field initializer
Child constructor X
After = ID-1/X/base=10/child=20
~~~

**Explanation:**

- `Before` is printed before object creation.
- The `Child(String,String)` constructor calls `super(id)`.
- During Base initialization, the Base instance field initializer runs, and then the Base constructor body prints the ID.
- After the Base constructor completes, the Child instance field initializer runs, and then the Child constructor assigns `tag` and prints the message.
- The `summary()` method is called only **after `new Child(...)` completes**, so it reads the initialized state.

**There are not two separate Base and Child objects**: the same Child object carries both Base fields and Child fields.

## 11. Scope of Using `super`: Calling a Superclass Implementation Explicitly

Inside a subclass instance method, `super.method()` lets you select the implementation inherited from the appropriate superclass instead of the current overriding implementation.

~~~java
class Base {
    String greeting() {
        return "Hello";
    }
}

class Child extends Base {
    @Override
    String greeting() {
        return super.greeting() + ", Java";
    }
}
~~~

`new Child().greeting()` returns `"Hello, Java"`. Calling `super.greeting()` **does not create a new Base object** and does not bypass all virtual dispatch inside the Base method. If Base.greeting calls an overridable helper, that helper can still dispatch based on the runtime receiver.

### 11.1. `super(...)` and `super.method()` Are Not the Same

- `super(arguments)`: an explicit invocation of a **superclass constructor**, inside a subclass constructor according to syntax rules.
- `super.method(arguments)`: a call to an **instance method implementation** from the superclass in an appropriate instance context.

In Java 17, an explicit `super(...)`/`this(...)` must normally appear at the beginning of the constructor body; do not call `super(...)` from an ordinary static/instance method.

### 11.2. `this` Is Still the Runtime Subclass Object

If code inside the Base constructor calls `this.toString()`, the runtime method can be the override from Child, even when Child has not finished initializing. Therefore, avoid logging `this` or calling overridable members early in a constructor.

## 12. Field Hiding Differs from Method Overriding

One of Java's important distinctions: **instance fields do not have dynamic dispatch like overridable instance methods**. If a subclass declares a field with the same name, it can **hide** the superclass field; Java selects the field according to the appropriate static type/lexical qualification, not according to runtime method dispatch.

~~~java
class Parent {
    String label = "Parent-field";

    String describe() {
        return "Parent-method";
    }
}

class Child extends Parent {
    String label = "Child-field";

    @Override
    String describe() {
        return "Child-method";
    }
}
~~~

If:

~~~java
Parent ref = new Child();
~~~

then `ref.label` selects **Parent.label**, while `ref.describe()` runs **Child.describe()** due to overriding.

### 12.1. Do Not Declare Duplicate-Named Fields to "Override Data"

Field hiding easily causes confusion:

- There are **two different fields** in the same object when the subclass defines a field with the same name.
- Parent's field does not disappear when Child hides it.
- Inside the subclass, `super.label` can access the superclass field according to the applicable rules.
- Calling an inherited method whose body reads `label` declared in the superclass can still read the **superclass field**, rather than "automatically switching" to the Child field.

In practice, prefer **private fields + methods with clear contracts**, and avoid using field hiding as a tool to simulate overriding.

## 13. Static Method Hiding Is Not Overriding

A subclass can declare a `static` method with a signature matching a static method of its superclass; Java calls this **method hiding**, not overriding. Unlike an overridden instance method, a static call is determined by **the type the compiler uses to resolve the call**, not by the runtime class of the object.

~~~java
class Parent {
    static String label() { return "Parent-static"; }
    String describe() { return "Parent-instance"; }
}
class Child extends Parent {
    static String label() { return "Child-static"; }
    @Override String describe() { return "Child-instance"; }
}
~~~

If you place the following statements inside a method:

~~~java
Parent value = new Child();
System.out.println(value.label());    // Parent-static
System.out.println(value.describe()); // Child-instance
~~~

The `value.label()` syntax is permitted by Java but easily causes confusion; in new code, call `Parent.label()` or `Child.label()` when you want to specify a static member clearly. This example is intended to **distinguish subtyping and dispatch**, not to recommend using static methods to simulate polymorphism.

The in-depth coverage of **field hiding, static method hiding, the relationship with `super`, compile-time lookup, and many runtime examples** belongs to the article **"Hiding Fields and Static Methods by Declared Type"**. Remember one rule in this introductory article: **only overridable instance methods are dynamically dispatched by the runtime receiver; fields and static methods do not work that way**.

## 14. Overloading Is Not Overriding

**Overloading** is declaring multiple methods with the same name and **different parameter lists**, within the same class or in an inheritance context. **Overriding** is providing an instance method implementation with a matching signature from the superclass.

~~~java
class Base {
    void log(Object value) {
        System.out.println("Object");
    }
}

class Child extends Base {
    void log(String value) {
        System.out.println("String");
    }
}
~~~

Here, `Child.log(String)` **overloads** `Base.log(Object)` rather than overriding it, because the parameter type differs.

### 14.1. Overload Resolution Is Affected by Compile-Time Types

~~~java
Child child = new Child();
Object text = "Java";
child.log(text);       // Selects log(Object)
child.log("Java");     // Selects log(String)
~~~

The compiler selects the matching overload based on the **expression type at compile time**. The runtime object of the variable `text` is String, but its compile-time type is Object, so the call `log(text)` selects `log(Object)`.

If the selected method is an overridable instance method, runtime dispatch afterward can still choose the corresponding override based on the runtime class. **Overload resolution and override dispatch are two different steps**.

### 14.2. Changing Only the Return Type Does Not Create an Overload

~~~java
class Wrong {
    // int calculate() { return 1; }
    // String calculate() { return "1"; }
}
~~~

If both are uncommented, the class does not compile because Java does not use return type alone to distinguish overloads with the same parameter list.

## 15. Upcasting and Downcasting in Subtype Relationships

An important aspect of `extends` is enabling **upcasting**: using a `Dog` where an `Animal` is expected without creating a new object. If `Dog extends Animal`:

~~~java
Animal animal = new Dog();  // Implicit upcast.
~~~

The compiler only allows calling members provided by the **static type `Animal`**. To call Dog's own API, the receiver needs to be type-checked/narrowed:

~~~java
if (animal instanceof Dog dog) {
    dog.fetch();  // Pattern matching for instanceof, standard since Java 17.
}
~~~

`instanceof` returns false for `null`. A direct downcast `(Dog) animal` succeeds only when the runtime object is compatible; otherwise, the JVM throws `ClassCastException`. **Casting does not change the runtime class and does not create a different object**.

Standalone example **`SubtypeIntroDemo.java`**:

~~~java
public class SubtypeIntroDemo {
    static class Animal {
        String name() { return "Animal"; }
    }
    static final class Dog extends Animal {
        @Override String name() { return "Dog"; }
        String fetch() { return "Fetch"; }
    }
    static final class Cat extends Animal {
        @Override String name() { return "Cat"; }
    }
    public static void main(String[] args) {
        Animal first = new Dog();
        Animal second = new Cat();
        System.out.println(first.name());
        if (first instanceof Dog dog) {
            System.out.println(dog.fetch());
        }
        System.out.println(second instanceof Dog);
        try {
            Dog wrong = (Dog) second;
            System.out.println(wrong.fetch());
        } catch (ClassCastException ex) {
            System.out.println("incompatible cast rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SubtypeIntroDemo.java
java SubtypeIntroDemo
~~~

Stdout:

~~~text
Dog
Fetch
false
incompatible cast rejected
~~~

In this introductory `extends` article, you only need to understand that **a subtype relationship enables upcasting**, while runtime checking determines whether downcasting is safe. Deeper rules for `instanceof`, flow scoping, `null`, generics erasure, arrays, and `ClassCastException` are covered in detail in the article **"Upcasting, Downcasting, instanceof, and ClassCastException"**.

## 16. A Superclass Reference Limits the Method API Without Changing Object Identity

An upcast reference still points to the original object:

~~~java
Child child = new Child();
Parent parent = child;
System.out.println(parent == child); // true
~~~

Even though the static type of `parent` is Parent, the object is not copied. This implies:

- Modifying the **shared instance state of the same object** through one reference can be observed through another reference.
- Override dispatch operates based on the same runtime receiver.
- `getClass()` on the object yields the corresponding runtime class, not the variable's declared type.
- If Parent has its own fields and Child adds fields, all of those fields belong to the same object.
- Casting a reference does not invoke a constructor, does not copy data, and does not automatically change the API's access modifiers.

### 16.1. When Is a Cast to a Subtype a Design Sign Worth Reviewing?

A function that accepts `Animal` yet always writes:

~~~java
if (animal instanceof Dog dog) {
    dog.fetch();
} else if (animal instanceof Cat cat) {
    // Other Cat-specific behavior
}
~~~

may indicate that the function **needs a different abstraction** (such as `Playable`) or should delegate the behavior to a polymorphic method. However, pattern matching remains appropriate when the logic truly depends on the **data shape** or needs to distinguish among certain subtypes, especially when processing ASTs, compilers, or data modeled with a sealed hierarchy.

## 17. `Object` Is the Root of Class Inheritance

Ordinary Java reference classes all relate back to `java.lang.Object`. Familiar methods of Object include:

- `toString()`
- `equals(Object)`
- `hashCode()`
- `getClass()`
- `wait()`, `notify()`, `notifyAll()` (related to synchronization)
- `clone()` (protected, with conditions)
- `finalize()` still exists in Java 17 but is deprecated; you should not build lifecycle logic on it.

A subclass can override eligible methods such as `toString()`, `equals(...)`, and `hashCode()` according to their contracts. You cannot override `getClass()` because that method is final in Object.

### 17.1. `equals` and `hashCode` Are Part of the Subtype Contract

When overriding `equals`, you need to ensure key properties such as symmetry, transitivity, consistency, and compliance with the `hashCode` contract.

One risk with inheritance is:

- The superclass considers two objects equal based on ID.
- The subclass adds a field and defines equality based on ID **and** the new field.
- `base.equals(child)` may differ from `child.equals(base)` if not designed carefully.

**Do not automatically include every subclass field in `equals/hashCode`** just because inheritance is used. For value objects, a final class or a record sometimes provides a clearer equality model. For entities, consider identity and mutable state to avoid HashMap/HashSet bugs when a key's hash changes.

### 17.2. `Object` Is Not a Substitute for a Semantically Rich API

You can declare `Object value = new Dog()`, but through the static type Object, the compiler does not allow calling `sound()` or `fetch()` directly. If you want a shared contract, it is better to use `Animal` or an appropriate interface.

## 18. Abstract Superclass and Concrete Subclass

An **abstract class** lets you define shared state/behavior as well as methods that do not yet have a complete implementation:

~~~java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    String color() {
        return color;
    }

    abstract double area();
}
~~~

A concrete subclass implements the abstract method:

~~~java
final class Rectangle extends Shape {
    private final double width;
    private final double height;

    Rectangle(String color, double width, double height) {
        super(color);
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Kích thước sai");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }
}
~~~

`new Shape(...)` is invalid because Shape is abstract; `new Rectangle(...)` is valid when constructor validation succeeds.

### 18.1. An Abstract Class Still Has a Constructor

An abstract class **cannot be instantiated directly with `new AbstractClass()`**, yet its constructor **runs when a concrete subclass is instantiated**. It can validate and assign superclass fields.

Avoid calling abstract or overridable instance methods from an abstract superclass constructor if those methods depend on subclass state that has not finished initializing. Java can still dispatch into the subclass implementation too early.

### 18.2. When to Use an Abstract Class

When there is a **shared contract along with some meaningful state/implementation** and the subclasses are truly subtypes of the superclass. If you only want to publish behavior and allow multiple implementations that do not share a base implementation, an interface is usually simpler.

## 19. An Interface Is a Supertype, but `implements` Differs from `extends class`

~~~java
interface Payable {
    long amountCents();
}

class Invoice implements Payable {
    private final long amount;

    Invoice(long amount) {
        this.amount = amount;
    }

    @Override
    public long amountCents() {
        return amount;
    }
}
~~~

`Invoice` is a subtype of `Payable`. The variable `Payable payable = new Invoice(500);` is valid if class and constructor access are appropriate.

A class can **extend one class** and **implement multiple interfaces**:

~~~java
class Entity {
}

interface Identified {
    String id();
}

interface Auditable {
    void audit();
}

class Document extends Entity
        implements Identified, Auditable {
    @Override
    public String id() {
        return "D-1";
    }

    @Override
    public void audit() {
        System.out.println("Audited");
    }
}
~~~

Document is a subtype of both Entity and the two interfaces.

### 19.1. An Interface Can `extends` Other Interfaces

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWrite extends Readable, Writable {
}
~~~

**Interface inheritance** allows multiple superinterfaces. Do not confuse this with class inheritance, where a class has only one direct superclass.

### 19.2. Default Methods Are Not "Full Multiple Class Inheritance"

Interfaces can declare default methods. When multiple defaults conflict, Java has resolution rules and sometimes the implementing class must override to choose the behavior explicitly.

~~~java
interface A {
    default String name() {
        return "A";
    }
}

interface B {
    default String name() {
        return "B";
    }
}

class Both implements A, B {
    @Override
    public String name() {
        return A.super.name() + B.super.name();
    }
}
~~~

This is a valid declaration snippet in an appropriate file. `A.super.name()` and `B.super.name()` invoke the default implementation specified by each interface, without creating new objects.

## 20. `final` Prevents Class Extension or Method Overriding

A `final class` cannot be extended:

~~~java
final class ImmutableToken {
    private final String value;

    ImmutableToken(String value) {
        this.value = value;
    }
}

// class SpecialToken extends ImmutableToken {} // Compile error
~~~

`final` on a class prevents subclasses; **it does not guarantee by itself that the entire instance is immutable**, because a final class can still have non-final mutable fields.

A `final method` in a superclass cannot be overridden by a subclass:

~~~java
class Base {
    public final String id() {
        return "fixed";
    }
}

class Child extends Base {
    // @Override
    // public String id() { return "changed"; } // Error
}
~~~

You can use a final method to keep entry-point validation or orchestration consistent while still leaving other hooks open.

### 20.1. Do Not Remove final Simply for Code Reuse

If a class has stable semantics and no subtype contract, using final + composition can be more appropriate than opening inheritance just to share a few lines of code. When you decide to allow `extends` on a public API, you are committing to many details about lifecycle, accessibility, and method contracts that subclasses may depend on.

### 20.2. An Abstract Class Cannot Also Be Final

`abstract` expects subclasses to implement the abstract methods; `final` forbids subclasses. Therefore, the combination `abstract final class` is invalid.

## 21. Sealed Classes in Java 17: Restricting Permitted Subtypes

Java 17 supports **sealed classes/interfaces** to declare a controlled **set of direct permitted subclasses/implementations**.

Example:

~~~java
sealed abstract class Result
        permits Success, Failure {
}

final class Success extends Result {
}

final class Failure extends Result {
}
~~~

If placed in different source files, the permitted subclasses must follow the package/module rules of the sealed hierarchy. A direct subclass of a sealed class must declare one of the eligible modifiers: `final`, `sealed`, or `non-sealed` (except in special cases such as an implicitly final record).

**Significance:** the compiler knows the direct permitted subclasses, and the API restricts arbitrary extension. Yet the hierarchy still has inheritance, subtyping, and dynamic dispatch as appropriate.

### 21.1. `non-sealed` Reopens Subclassing

~~~java
sealed class Base permits Closed, Open {
}

final class Closed extends Base {
}

non-sealed class Open extends Base {
}
~~~

Class `Open` is a permitted subclass of Base and chooses `non-sealed`, so Open itself can be extended further (if other rules permit). The set of **direct** subclasses of Base is controlled; not every descendant is necessarily finite when a non-sealed branch exists.

### 21.2. Records Cannot `extends` Another Application Class

Record types are implicitly final and directly extend `java.lang.Record` under language semantics, so you cannot write:

~~~java
// record UserView(String name) extends Person {} // Invalid
~~~

A record can **implement interfaces**:

~~~java
interface Named {
    String name();
}

record UserView(String name) implements Named {
}
~~~

`UserView` is a subtype of Named, even though it does not use `extends Person`. This is a good approach for representing immutable-style value data with an interface contract; remember that a record only guarantees **shallow immutability** and does not automatically deep-copy mutable reference components.

## 22. Complete Program 5: Java 17 Sealed Hierarchy and Subtypes

Create the file **`SealedShapeDemo.java`**:

~~~java
public class SealedShapeDemo {
    sealed interface Shape permits Square, Rectangle {
        int area();
    }

    record Square(int side) implements Shape {
        Square {
            if (side <= 0) {
                throw new IllegalArgumentException("Cạnh sai");
            }
        }

        @Override
        public int area() {
            return Math.multiplyExact(side, side);
        }
    }

    record Rectangle(int width, int height)
            implements Shape {
        Rectangle {
            if (width <= 0 || height <= 0) {
                throw new IllegalArgumentException("Cạnh sai");
            }
        }

        @Override
        public int area() {
            return Math.multiplyExact(width, height);
        }
    }

    static void printArea(Shape shape) {
        System.out.println(
                shape.getClass().getSimpleName()
                        + "=" + shape.area());
    }

    public static void main(String[] args) {
        Shape a = new Square(3);
        Shape b = new Rectangle(2, 5);

        printArea(a);
        printArea(b);

        System.out.println("Square is Shape = "
                + (a instanceof Shape));

        try {
            new Square(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Compile/run with Java 17:

~~~bash
javac -encoding UTF-8 SealedShapeDemo.java
java SealedShapeDemo
~~~

**Exact stdout:**

~~~text
Square=9
Rectangle=10
Square is Shape = true
Rejected = Cạnh sai
~~~

**Explanation:**

1. `Shape` is a sealed interface that allows only the listed direct implementors `Square` and `Rectangle`.
2. Both records are implicitly final, so they satisfy the permitted implementations rule.
3. Each record defines `area()` to fulfill the interface contract; a `Shape` reference can call `shape.area()`, and runtime dispatch selects the corresponding record implementation.
4. `getClass().getSimpleName()` on the nested records in this file returns the simple name `Square` or `Rectangle`.
5. Compact constructors validate data; `new Square(0)` throws an exception before a valid object is returned.
6. `Math.multiplyExact` is used to detect overflow instead of silently returning an incorrect area if the arguments are too large.

**Note:** the records here are **nested member types** inside `SealedShapeDemo`; the condition that permitted subclasses reside in the same module/package is satisfied. If split across files or packages, you must follow the corresponding sealed type declaration rules.

## 23. Generic Types: A Subclass Relation Does Not Automatically Imply Subtyping Across All Parameterizations

If `Dog extends Animal`, we have:

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

However, **`List<Dog>` is not a subtype of `List<Animal>`**:

~~~java
java.util.List<Dog> dogs = new java.util.ArrayList<>();

// java.util.List<Animal> animals = dogs; // Compile error
~~~

Why? If the assignment were allowed, a caller could add a Cat to `animals`, while the same runtime collection is supposed to hold Dogs. **Java generics are invariant** for ordinary parameterized types, even though Dog is a subtype of Animal.

### 23.1. Wildcard `? extends Animal` for Reading from a Source Containing Subtypes

~~~java
static void printAnimals(
        java.util.List<? extends Animal> animals) {
    for (Animal animal : animals) {
        System.out.println(animal.sound());
    }
}
~~~

The method can accept `List<Dog>` or `List<Cat>` when the class definitions match. However, through `List<? extends Animal>`, you cannot arbitrarily add `new Animal(...)` or `new Cat()` to the list, because the compiler does not know the concrete element type of the list passed in.

The common **PECS** principle:
- **Producer Extends:** if the collection mainly supplies values of type Animal for the caller to read, `? extends Animal` may be appropriate.
- **Consumer Super:** if the collection accepts Dogs being added to it, `? super Dog` may be appropriate.

PECS is a heuristic for using wildcards; it does not make all generic types covariant.

### 23.2. Generics and Array Covariance Are Two Different Mechanisms

Java arrays of reference types are **covariant**: `Dog[]` can be assigned to `Animal[]`. However, writing a Cat into an array that is actually a Dog[] is checked at runtime and throws `ArrayStoreException`.

~~~java
Dog[] dogs = new Dog[1];
Animal[] animals = dogs;
// animals[0] = new Cat(); // Runtime ArrayStoreException
~~~

This is a fragment. The fact that arrays are covariant does not mean generics such as `List<Dog>` are covariant as well. Do not use raw-type casts to bypass generic checks just to force an invalid subtype relation.

## 24. Access Control Across Packages When Extending

Inheritance does not bypass visibility.

An example organized across two packages:

~~~text
src/
  model/
    Base.java
  app/
    Derived.java
~~~

Contents of `src/model/Base.java`:

~~~java
package model;

public class Base {
    private int privateValue = 1;
    int packageValue = 2;
    protected int protectedValue = 3;
    public int publicValue = 4;

    protected void check() {
        System.out.println(protectedValue);
    }
}
~~~

Contents of `src/app/Derived.java`:

~~~java
package app;

public class Derived extends model.Base {
    public int read() {
        check();
        return protectedValue + publicValue;
    }

    // Cannot directly access privateValue or packageValue.
}
~~~

In a subclass in a different package, `check()` and `protectedValue` are used from Derived's instance context according to protected access rules. `privateValue` and `packageValue` cannot be accessed directly from Derived.

### 24.1. Protected Access Through References Is Not Arbitrary

In Derived's code inside package `app`, operations such as:

~~~java
// model.Base other = new model.Base();
// int x = other.protectedValue; // Not arbitrarily accessible
~~~

differ from `this.protectedValue` in a subclass instance context. Java enforces receiver type rules for protected instance members when the declaring class is in a different package; **protected does not mean all Base objects expose that field to every subclass**.

### 24.2. Public Classes Are Also Subject to Module Rules

In code organized using the **Java Platform Module System (JPMS)**, accessing types across modules also involves `requires`/`exports` and other rules. A public class located in a package that is not properly exported may not be accessible from another module. Inheritance does not break module boundaries.

This article focuses on class-object mechanics, so the standalone runnable examples do not require JPMS configuration.

## 25. Do Not Increase Visibility Just to Let Subclasses Access State Directly

A superclass with the field:

~~~java
protected long balance;
~~~

gives subclasses read/write access to the field according to access rules. That can let a subclass break the base class invariant if it writes `balance = -100;`.

Sometimes a better API is:

~~~java
abstract class Account {
    private long balance;

    protected final void credit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount sai");
        }
        balance = Math.addExact(balance, amount);
    }

    public final long balance() {
        return balance;
    }
}
~~~

A subclass can use `credit(...)` without assigning the field freely. The `final` method helps protect the contract of the update operation. However, the superclass still needs to decide explicitly which protected hooks make sense for the inheritance contract; not every domain class needs to be extended.

**Principle:** give subclasses only the capabilities they need, and limit coupling to internal representation.

## 26. LSP: Designing a Proper Subtype Is Harder Than Sharing Code

Imagine a superclass `Rectangle` with `setWidth`/`setHeight` allowing the two dimensions to change independently. A subclass `Square extends Rectangle` wants to enforce that width always equals height. If a user has code:

~~~java
void resize(Rectangle rectangle) {
    rectangle.setWidth(10);
    rectangle.setHeight(20);
}
~~~

The caller may expect width=10 and height=20 at the end. However, a Square subclass that enforces width==height can cause this postcondition to no longer hold. This is a classic example showing that **the geometric "a square is a rectangle" does not automatically yield a good inheritance API when mutable classes have incompatible setter contracts**.

Other options:

- Immutable shape value types with a shared `area()` interface.
- Rectangle/Square independently implementing Shape.
- Composition of an immutable Dimensions object.
- Removing setters to make the subtype contract more viable.
- Defining shared behavior with an interface instead of forcing all types to share base state/constructors.

Proper inheritance occurs when **the subclass genuinely honors everything the superclass promises**, including state, exceptions, lifecycle, and side effects.

### 26.1. Behavioral Subtyping Is Not Just About "Same Method Name"

An override with the same signature can still break LSP if it:

- Throws a new exception when the input is valid under the superclass contract.
- Returns results that violate invariants.
- Has inappropriate side effects.
- Fails to respect the superclass's thread-safety contract.
- Changes semantics in ways callers do not anticipate.
- Uses a superclass constructor with overridden hooks that are not yet ready.

The Java compiler checks certain language rules such as checked exceptions and access widening; **it does not prove the entire behavioral contract**.

## 27. The Fragile Base Class Problem and Risks of Changing a Superclass

A base class that exposes subclassing creates dependencies from its subclasses:

- A subclass may override a protected method called by other methods.
- The base class may call overridable methods in a specific sequence.
- Base fields/constructor hooks may establish lifecycle assumptions.
- Adding a new method to Base can sometimes conflict with an existing method in a subclass.
- Changing Base's implementation can alter the number of times or timing at which a hook that a subclass depends on is called.

That is part of the **fragile base class problem**: seemingly internal changes to the superclass can affect subclasses.

### 27.1. Designing a Superclass for Inheritance

If a class is **intentionally** an extension point, you should:

1. Document invariants, preconditions, and postconditions.
2. State clearly which methods are overridable and which methods are final.
3. Do not call overridable methods from constructors when subclass state is not ready.
4. Keep the protected API minimal and intentional.
5. Use a template method if you need to preserve a workflow and allow hooks only at appropriate steps.
6. Isolate state that should not be modified into private fields/controlled methods.
7. Test with multiple concrete subclasses.
8. Consider backward compatibility when changing the public/protected API.

If you do not want to support an inheritance contract, a **final class or composition** is usually clearer than leaving `extends` open by default.

## 28. Override, Access Modifiers, and Checked Exceptions: An Exact Illustration

Superclass:

~~~java
import java.io.IOException;

class BaseReader {
    protected Number read() throws IOException {
        return 1;
    }
}
~~~

Subclass:

~~~java
class FastReader extends BaseReader {
    @Override
    public Integer read() {
        return 2;
    }
}
~~~

This override is valid because:

- `public` is not narrower than `protected`.
- `Integer` is a subtype of `Number` (covariant return).
- It does not declare a new or broader checked exception.
- The signature and overriding context are valid.

An override such as:

~~~java
// @Override
// private Number read() throws Exception { return 0; }
~~~

would be invalid in the subclass because it reduces access privileges and broadens the checked exception against the contract. This snippet only illustrates the error; it is not standalone Java source.

### 28.1. Checked vs. Unchecked Exceptions

An overriding method can usually throw an unchecked exception such as `IllegalArgumentException` without Java requiring a throws declaration. However, the **behavioral contract** must still be respected. Do not use the ability to throw unchecked exceptions to evade substitutability obligations.

## 29. Abstract Methods, Default Methods, and Overload Resolution Across Multiple Levels

A class can:

- Inherit a concrete instance method from its superclass.
- Override that method.
- Provide another overload with a new parameter list.
- Implement an abstract method of its superclass.
- Implement or receive a default method from an interface if there is no conflict with a class method/other defaults.

**When reading `object.method(args)`, answer two questions:**

1. *Which method declaration does the compiler select?* Based on compile-time types and overload applicability/access.
2. *Which implementation runs at runtime?* If the declaration corresponds to an overridable instance method, dynamic dispatch proceeds based on the runtime receiver.

This split helps explain why fields/static methods do not behave like virtual instance methods and why downcasting can let the compiler see additional APIs.

## 30. `getClass()`, `instanceof`, and Keeping Type Checks Limited

~~~java
Animal animal = new Dog("Milo");
System.out.println(animal.getClass().getSimpleName());
~~~

The result is `Dog` when using the corresponding Dog classes, because `getClass()` reports the runtime class.

However, you should not drive all domain logic with:

~~~java
if (animal.getClass() == Dog.class) {
    // ...
}
~~~

An **exact** class comparison using `getClass() == ...` ignores instances of further subclasses, whereas `instanceof Dog` checks compatibility with the Dog type. They serve two different purposes.

If behavior is part of the Animal contract, you should usually call a **virtual Animal method** instead of `getClass()` followed by `if/else`. Exact runtime type checks are appropriate when business logic truly must distinguish the exact class, but that is not the default for OOP design.

## 31. Some Common Compile-Time and Runtime Errors

### 31.1. Trying to Extend Two Classes

~~~java
// class C extends A, B {} // Invalid
~~~

Java allows only one direct class superclass; use interfaces or composition if you need multiple capabilities.

### 31.2. Extending a `final` Class

~~~java
// class SpecialString extends String {} // Invalid
~~~

`String` is final. Not every class in the JDK is open for inheritance.

### 31.3. Relying on a Superclass Constructor as a Subclass Constructor

~~~java
class Base {
    Base(int code) {
    }
}

class Child extends Base {
    // Child(int) does not exist automatically. A constructor calling super(int) is needed.
}
~~~

This snippet **does not compile** if Child is left without a constructor: the compiler tries to generate a default constructor calling `super()`, yet Base has no no-arg constructor. You need to declare:

~~~java
class Child extends Base {
    Child(int code) {
        super(code);
    }
}
~~~

In a real example, only use one version of Child in a file; the snippets above are separated to illustrate the invalid and valid cases.

### 31.4. Calling a Subclass-Only Method Through a Superclass Reference

~~~java
// Animal pet = new Dog("Milo");
// pet.fetch(); // Animal does not declare fetch
~~~

If the use case needs the `fetch` method, you can keep a Dog reference, use pattern matching with `instanceof`, or design an appropriate interface. Do not cast blindly just because you know an object is "usually a Dog."

### 31.5. Incompatible Downcast

~~~java
// Animal a = new Cat("Luna");
// Dog dog = (Dog) a; // Runtime ClassCastException
~~~

The compiler may accept a cast between two suitably related reference types, but the runtime object must actually belong to the target subtype.

### 31.6. Using `@Override` on an Accidental Overload

~~~java
class Base {
    void print(Object data) {
    }
}

class Child extends Base {
    // @Override
    // void print(String data) {} // Does not override print(Object)
}
~~~

Remove the annotation if you genuinely intend to overload, or fix the parameter signature if you intend to override.

### 31.7. Reducing the Visibility of an Overriding Method

A public superclass method cannot be overridden in a subclass as package-private/protected/private.

### 31.8. Overriding a Static Method as an Instance Method

You cannot use an instance method to override a superclass static method with the same signature, nor can you validly use a static method to hide an instance method with the same signature.

### 31.9. Assuming Fields Have Dynamic Dispatch

`Parent p = new Child(); p.field` reads the field according to static access rules and does not automatically pick Child.field. Use an overridable method if you need runtime polymorphism.

### 31.10. Calling an Overridable Method from a Constructor

A subclass override can run while subclass fields are still null/0, which can cause an NPE or side effects. Avoid dynamic hooks in the constructor initialization chain.

### 31.11. Changing Every Field to `protected` for Subclasses to Use

This exposes the representation, allowing subclasses to break invariants. Prefer private fields and controlled protected/public behaviors.

### 31.12. Treating `List<Dog>` as `List<Animal>`

Generics are invariant. Use `List<? extends Animal>` for a read-only producer-style parameter when appropriate, or create an independent Animal list.

### 31.13. Treating `extends` as an Automatic Multi-Purpose Solution

If the subclass only wants one capability from the superclass without following its entire contract, an is-a relationship is inappropriate. Composition is usually clearer.

### 31.14. Using Subclassing Solely for Mocking in Tests

A final service can collaborate via an injectable interface/constructor; tests can supply a fake collaborator. You do not have to open an entire class to inheritance just to swap out a dependency.

### 31.15. Using a Class Cast as a Way to "Add Methods" to an Object

A cast does not create new behavior. It only changes how the reference is type-checked/viewed; the runtime object still keeps its original type.

## 32. Designing Before Writing `extends`: A Practical Checklist

Before declaring `class Child extends Parent`:

1. **Is "is-a" accurate?** Can a caller using Parent's contract substitute Child?
2. **Is Parent designed for subclassing?** Is there documentation about hooks/lifecycle?
3. **Is there a dependency that only needs "has-a"?** Composition may be simpler.
4. **Are superclass fields private?** Does the subclass access them through controlled methods?
5. **Is the constructor chain valid?** Does Parent have an appropriate constructor for `super(...)` to call?
6. **Is any overridable method called too early?** Check both field initializers and the constructor call graph.
7. **Does Child need additional invariants?** Do they conflict with Parent behavior?
8. **Does any override tighten preconditions or break postconditions?** Check LSP.
9. **Do methods use `@Override`?** Are there any accidental overloads?
10. **Do static methods/fields share duplicate names?** Avoid confusing hiding.
11. **Are multiple capabilities needed?** Is implementing interfaces more suitable than simulated multiple inheritance?
12. **Is the parent class `final`, sealed, or abstract?** Understand extension limits.
13. **Are there many runtime casts?** A better polymorphic API may be needed.
14. **Do generics need wildcards?** `List<Child>` is not automatically a `List<Parent>`.
15. **Is protected access across another package valid?** Pay attention to receiver and module rules.
16. **Is the equality/hashCode contract sound under inheritance?** Check symmetry and mutable state.
17. **Will changing the superclass affect external subclasses?** Consider backward compatibility.
18. **Is the design still easier to understand than composition?** Prioritize a model that fits the domain.

## 33. Self-Check Exercises with Answers

**Question 1.** What relationships does `class Dog extends Animal` establish?

**Answer:** Dog is a direct subclass of Animal (when Animal is written right after extends), Dog has a subtype relationship with Animal, and it can be used in many contexts requiring an Animal reference.

**Question 2.** Does Java allow `class C extends A, B`?

**Answer:** No. Each class has only one class direct superclass. A class can implement multiple interfaces.

**Question 3.** If `extends` is not declared for an ordinary class, what is its direct superclass?

**Answer:** Ordinarily `java.lang.Object`; Object itself is the root exception.

**Question 4.** Does `Animal animal = new Dog();` create a new Animal object besides the Dog object?

**Answer:** No. This is an upcast reference to the same Dog object.

**Question 5.** Given `Animal animal = new Dog();`, does the compiler allow `animal.fetch()` if fetch is only declared in Dog?

**Answer:** No, because the static type of animal is Animal. Runtime Dog does not automatically change compile-time method availability.

**Question 6.** Where does `animal.sound()` invoke the method if Dog overrides Animal.sound?

**Answer:** The instance method call is dynamically dispatched at runtime to the Dog implementation when the runtime receiver is Dog.

**Question 7.** Which field does `Parent p = new Child(); p.label` select when both classes have `label`?

**Answer:** The field is resolved according to the compile-time type Parent of p; field hiding is not overriding.

**Question 8.** Does `p.staticMethod()` call Parent or Child when Child hides a static method with the same signature?

**Answer:** It selects based on the compile-time type of the expression (Parent), not the runtime object Child. Static methods should be called through the class name to make intent clear.

**Question 9.** Are Parent's constructors inherited as Child's constructors?

**Answer:** No. Child declares its own constructors; they call a Parent constructor via an appropriate explicit or implicit `super(...)`.

**Question 10.** If Base only has `Base(int)`, will a Child that declares no constructor compile on its own?

**Answer:** No, if the compiler cannot call a valid no-arg Base constructor. Child needs a constructor calling `super(int)` with an appropriate argument.

**Question 11.** Why should you avoid calling an overridable method from a superclass constructor?

**Answer:** Runtime dispatch can select the subclass override before the subclass fields/constructor body have finished initializing, causing the method to observe null/0 or throw an exception.

**Question 12.** When do you use `super.method()`?

**Answer:** In an appropriate subclass instance context, to call the superclass implementation instead of the current override itself.

**Question 13.** What are `this(...)` and `super(...)`?

**Answer:** Explicit constructor invocations: `this(...)` calls another constructor of the same class, and `super(...)` calls a superclass constructor; they are not ordinary method calls.

**Question 14.** How do overloading and overriding differ?

**Answer:** Overloading differs in parameter lists, and the compiler selects an overload based on static types; overriding provides a matching instance implementation for an inherited method and involves runtime dispatch.

**Question 15.** What is `@Override` useful for?

**Answer:** It makes the compiler verify that the method actually overrides/implements an eligible method, catching signature errors or typos.

**Question 16.** Can a public method in Parent be overridden as protected in Child?

**Answer:** No, because narrower access violates overriding rules.

**Question 17.** Can a final method be overridden?

**Answer:** No. A final class also cannot be extended.

**Question 18.** Does an abstract superclass have constructors?

**Answer:** Yes. An abstract superclass constructor runs while a concrete subclass is being instantiated; you cannot directly instantiate an abstract superclass with new.

**Question 19.** Can a class both extend a class and implement two interfaces?

**Answer:** Yes, with the syntax `extends Base implements I1, I2` when the contracts are satisfied.

**Question 20.** Can `record Product(String name)` `extends BaseProduct`?

**Answer:** No. A record is implicitly final and inherits from java.lang.Record under Java semantics, though it can implement interfaces.

**Question 21.** What does a sealed class control?

**Answer:** It controls direct permitted subclasses. The permitted subclasses must declare an appropriate modifier such as final, sealed, or non-sealed according to Java 17 rules.

**Question 22.** Is `List<Dog>` a subtype of `List<Animal>`?

**Answer:** No. Ordinary generic parameterizations are invariant. Consider `List<? extends Animal>` for a producer list.

**Question 23.** Can `Dog[]` be assigned to `Animal[]`?

**Answer:** Yes, with array covariance, but storing a Cat into an array whose runtime type is Dog[] will cause ArrayStoreException.

**Question 24.** What is the benefit of `animal instanceof Dog d` in Java 17?

**Answer:** It checks the runtime type and binds a Dog reference in the valid branch, avoiding repeated explicit casts.

**Question 25.** Does casting `(Dog) cat` turn a Cat object into a Dog?

**Answer:** No. A cast only checks/treats the reference as the requested type. If the runtime object is incompatible, it throws ClassCastException.

**Question 26.** Why can `Square extends Rectangle` be a wrong design with mutable setters?

**Answer:** If Square enforces width==height, overriding the setters can break Rectangle's contract allowing width and height to change independently, violating behavioral substitutability.

**Question 27.** Does a private field of Parent disappear from a Child object?

**Answer:** No. It remains part of the state according to the superclass declaration; Child cannot access it directly due to visibility rules.

**Question 28.** Can a subclass have a field with the same name as one in its superclass?

**Answer:** Yes in some contexts, but that is field hiding, not overriding; it easily causes confusion when code uses Parent/Child references.

**Question 29.** Is `Animal animal = null;` valid, and what does `animal instanceof Dog` give?

**Answer:** Assigning null to an Animal reference is valid. `null instanceof Dog` is false; calling an instance method directly on null throws an NPE.

**Question 30.** When should you use composition instead of `extends`?

**Answer:** When a class needs to **have/use** a collaborator or reuse a capability, rather than genuinely being a subtype that complies with the entire contract of that class.

## 34. Conclusion: A Subtype Is a Commitment, Not Just an Arrow

`extends` is the syntax that establishes class inheritance and a subtype relation in Java. A subclass can receive inherited members, declare new state/behavior, call a superclass constructor with `super(...)`, and **override** instance methods to participate in dynamic dispatch. Upcasting lets code use a Child object through a Parent reference without creating a new object. However, the compile-time type still determines the callable API and overload resolution, while the runtime class determines the implementation of overridable instance methods.

To use inheritance properly, you must distinguish **overriding from hiding**, **subtyping from casting**, **constructor invocation from inherited methods**, **class inheritance from interface implementation**, and **is-a from has-a**. Modifiers such as `final`, `abstract`, and `sealed` help control how a hierarchy can be extended in Java 17.

Most importantly: **every `extends` is a design commitment** that the subclass can substitute for the superclass in the scenarios described by the parent contract. If the goal is merely to assemble components to work together, composition is usually clearer and more flexible. If you genuinely need subtype polymorphism, design a rigorous superclass/interface contract, preserve invariants, and test concrete subclasses—that is the sustainable way to leverage inheritance in Java.
