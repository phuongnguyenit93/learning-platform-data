# Declared Type of a Variable and Actual Class of an Object in Java

When a Java variable has a **reference type**, we need to distinguish **the declared type of the variable** from **the actual class of the object that the variable references**. The two concepts often coincide in simple examples, but they can differ when **inheritance, interfaces, polymorphism, type conversion, generics, or reference assignments** are involved.

Example:

```java
Animal animal = new Dog();
```

- **`Animal`** on the left is the **declared type of the variable `animal`**. When the expression consists solely of the variable name `animal`, that is also the **type of the expression at compile time** (*compile-time/static type*).
- **`Dog`** on the right is the class specified in the `new Dog()` expression. The newly created object has the **actual class `Dog`** (*runtime class*).
- The value stored in `animal` is a **reference to the `Dog` object**. Java **does not convert the Dog object into an Animal object** upon assignment; it only views that reference through a broader type.
- The compiler allows calling members that are accessible from the static type `Animal`, but when calling an **overridden instance method**, the implementation executed can be selected from the actual class `Dog` at runtime.

**Key principle:** *The static type governs which operations are allowed to be written and how certain names/parameters are resolved at compile time; the actual class affects the implementation of overridden instance methods and type checks at runtime.*

This article covers topics from the fundamentals to commonly confused scenarios: upcasting, downcasting, `instanceof`, `getClass()`, overriding/overloading, field hiding, `static`, `null`, interfaces, arrays, generics, `var`, changing references, and a Java 17 practice exercise.

## 1. Reference Variables, Reference Values, and Objects

Consider the declaration:

```java
Dog dog = new Dog();
```

To understand this line accurately, break it down into three parts:

| Component | In the example | Explanation |
| --- | --- | --- |
| **Variable** | `dog` | Location storing a **reference value**; the variable has declared type `Dog` |
| **Reference value** | Value obtained from `new Dog()` | Used to access an object; not a copy of all fields |
| **Object** | New instance of `Dog` | Has identity, field state, and an actual class determined at creation |

Conceptual diagram:

```text
Variable dog (static type Dog)
          |
          | reference value
          v
Object #1 (actual class Dog)
    ├── inherited fields
    └── fields declared in Dog
```

`#1` is an illustrative notation, not a memory address. Java does not require programmers to use actual memory addresses to work with references.

When you write:

```java
Animal animal = dog;
```

`dog` and `animal` both hold a reference value pointing to **a single `Dog` object**, but **the two variables have different declared types**:

```text
dog    : Dog    ───┐
                   ├──> the same object #1, runtime class = Dog
animal : Animal ───┘
```

No new `Animal` object is automatically created by the assignment `animal = dog`.

### Comparison with Primitive Types

`int n = 10;` has the primitive type `int`; no `Integer` class object is necessarily created for that primitive value itself. The concept of the **runtime class of the referenced object** only has direct meaning when a reference points to an object.

In this article, examples like `Animal`, `Dog`, and `Cat` are reference classes; the keywords `int` and `boolean` are used for comparison when needed.

## 2. Static Type and Actual Class: Two Different Questions

Always ask separately:

1. **What type does the expression have at compile time?** If the expression is a variable name, read the **variable declaration**. If the expression is a cast, a method call, a conditional operator, or `new`, you must consider the type-determination rules for **that entire expression**.
2. **At runtime, what class of object is the reference pointing to?** This depends on the object created, the reference value passed/assigned, and the program state at the moment under consideration.

Example:

```java
Animal pet = new Dog();
```

For the **expression `pet`**:
- Static type: `Animal`.
- Runtime class of the referenced object: `Dog`.

For the **expression `new Dog()`**:
- Compile-time type: `Dog`.
- The new object has the runtime class: `Dog`.

For the **expression `(Animal) new Dog()`**:
- Compile-time type of **the entire expression after the cast**: `Animal`.
- The referenced object still has the runtime class `Dog`.

An object can be observed through multiple variables or expressions of different types without **the actual class of the object itself changing**. Only when a variable is **assigned a reference to another object** can the actual class of the object *currently referenced by the variable* differ.

## 3. Complete Example: Same Object, Different Declared Types

Save as **`DeclaredVsRuntimeDemo.java`**:

```java
class Animal {
    String kind() {
        return "Animal";
    }

    String speak() {
        return "Âm thanh chung";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }

    String fetch() {
        return "Đang nhặt bóng";
    }
}

public class DeclaredVsRuntimeDemo {
    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal pet = dog;
        Object unknown = dog;

        System.out.println(dog == pet);
        System.out.println(pet == unknown);
        System.out.println(pet.getClass().getSimpleName());

        System.out.println(pet.kind());
        System.out.println(pet.speak());
        System.out.println(dog.fetch());

        // pet.fetch();     // WRONG: Animal does not declare fetch()
        // unknown.speak(); // WRONG: Object does not declare speak()
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 DeclaredVsRuntimeDemo.java
java DeclaredVsRuntimeDemo
```

**Exact stdout:**

```text
true
true
Dog
Animal
Gâu
Đang nhặt bóng
```

Explanation:

- `dog`, `pet`, and `unknown` all reference the same `Dog` object, so both `==` comparisons are true.
- `pet.getClass().getSimpleName()` gives the simple name of the object's **actual class**: `Dog`.
- `pet.kind()` is valid because the static type `Animal` declares `kind()`; `Dog` does not override this method, so the result is `Animal`.
- `pet.speak()` is also valid through the `Animal` type. However, `Dog` **overrides** the `speak()` method, so the runtime executes the implementation in `Dog`, printing `Gâu`.
- `dog.fetch()` is valid because `dog` has the static type `Dog` and `Dog` declares `fetch()`.
- `pet.fetch()` **does not compile**, even though `pet` is pointing to a `Dog` object, because `fetch()` is not in the set of methods accessible through the static type `Animal`.
- `unknown.speak()` **does not compile** because the static type of `unknown` is only `Object`, which does not declare `speak()`.

**Takeaway:** looking only at the runtime class to predict valid calls is not enough. The compiler also has to check the type of **the expression to the left of the dot**.

## 4. Upcasting: Using a Subtype Reference as a Supertype

**Upcasting** is using a reference to an object of a subtype in a position that requires an appropriate superclass or interface.

```java
Dog dog = new Dog();
Animal animal = dog;     // Automatic upcast
Object object = dog;     // Wider upcast
```

With the inheritance `Dog extends Animal`:

- `Dog` is a subtype of `Animal`.
- `Animal` is a subtype of `Object`.
- Java allows converting a `Dog` reference to `Animal` or `Object` via **widening reference conversion** in many valid contexts.
- The operation **does not create a new object** and does not erase any data or methods of `Dog`.
- After upcasting, **the static type of the receiving variable** restricts which methods/fields can be accessed through that variable.

Example:

```java
Animal animal = new Dog();
animal.speak();         // Valid
// animal.fetch();      // Compile error
```

`animal` only sees the API allowed by the `Animal` type. This is an important characteristic of **subtype polymorphism**: code can work with a general type without needing to know each specific subclass.

### Upcasting to an Interface

```java
interface Payable {
    int amount();
}

class Invoice implements Payable {
    private final int total;

    Invoice(int total) {
        this.total = total;
    }

    @Override
    public int amount() {
        return total;
    }

    String label() {
        return "Invoice";
    }
}
```

With `Payable p = new Invoice(200);`:

- The static type of `p` is the **interface `Payable`**.
- The runtime class of the object is **`Invoice`**.
- `p.amount()` is valid and is implemented by `Invoice`.
- `p.label()` is invalid because `Payable` does not declare `label()`.

Assigning a reference through an interface does not create “half an Invoice object”; it is still a whole `Invoice` object, simply viewed through the `Payable` contract.

## 5. Downcasting: When You Need Subclass-Specific Capabilities

To call a method that exists only on a subclass through a superclass-typed variable, you sometimes need to **downcast** (cast a reference from a wider type to a narrower type).

```java
Animal animal = new Dog();
Dog dog = (Dog) animal;
System.out.println(dog.fetch()); // Fetching the ball
```

Here:

1. `animal` has the static type `Animal`.
2. `(Dog) animal` is an expression that has the static type `Dog` due to the cast.
3. The actual object is a `Dog`, so the cast **succeeds at runtime**.
4. `dog` references **the exact same original object**. A cast does not clone, convert the object, or modify fields.

### 5.1. A Cast Can Compile but Fail at Runtime

```java
Animal animal = new Cat();
Dog dog = (Dog) animal;
```

Suppose `Cat extends Animal` and `Dog extends Animal` as two separate subclasses. The compiler can allow casting from the static type `Animal` to `Dog`, but at runtime the actual object is a `Cat`, so a **`ClassCastException`** occurs.

Java does not “turn a Cat into a Dog” by casting. A cast only asks the JVM to **check** that the actual reference is compatible with the requested type.

### 5.2. An Impossible Cast Can Be Detected at Compile Time

Not every cast between two arbitrary classes is valid in terms of syntax/types:

```java
Dog dog = new Dog();
// Cat cat = (Cat) dog; // Compile error with two unrelated sibling classes
```

Because the two sibling types have no direct valid conversion relationship in this context, the compiler can reject it immediately. If you receive a superclass-typed variable and cast it to a subclass, the static information allows checking at runtime.

### 5.3. The Safe Way: `instanceof` and Java 17 Pattern Matching

`instanceof` checks whether the reference at runtime is compatible with the queried type. Java 17 supports **pattern matching for instanceof**:

```java
static String action(Animal animal) {
    if (animal instanceof Dog dog) {
        return dog.fetch();
    }
    return "Không phải Dog";
}
```

When the condition is true, the pattern variable `dog` has the static type `Dog` and references **the original object**. No additional cast is needed.

If `animal == null`, the expression `animal instanceof Dog` returns **`false`**; it does not throw a `NullPointerException` just from performing the check.

## 6. Java 17 Program: Checking the Runtime Class and Safe Casting

Save as **`RuntimeTypeCheckDemo.java`**:

```java
class Animal {
    String speak() {
        return "...";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }

    String fetch() {
        return "Nhặt bóng";
    }
}

class Cat extends Animal {
    @Override
    String speak() {
        return "Meo";
    }
}

public class RuntimeTypeCheckDemo {
    static String describe(Animal animal) {
        if (animal instanceof Dog dog) {
            return "Dog: " + dog.fetch();
        }
        if (animal instanceof Cat) {
            return "Cat: " + animal.speak();
        }
        if (animal == null) {
            return "Không có đối tượng";
        }
        return "Animal khác";
    }

    public static void main(String[] args) {
        Animal first = new Dog();
        Animal second = new Cat();
        Animal missing = null;

        System.out.println(first.getClass().getSimpleName());
        System.out.println(first instanceof Dog);
        System.out.println(second instanceof Dog);
        System.out.println(missing instanceof Dog);

        System.out.println(describe(first));
        System.out.println(describe(second));
        System.out.println(describe(missing));
    }
}
```

Run:

```bash
javac -encoding UTF-8 RuntimeTypeCheckDemo.java
java RuntimeTypeCheckDemo
```

**Exact stdout:**

```text
Dog
true
false
false
Dog: Nhặt bóng
Cat: Meo
Không có đối tượng
```

**Notes:**

- `getClass()` is an instance method. `first.getClass()` is valid because `first` is not null; `missing.getClass()` will throw a `NullPointerException`.
- `instanceof` checks runtime compatibility with the specified type, not exact type equality. For example, if there is a `class Puppy extends Dog`, a `Puppy` object still satisfies `instanceof Dog`.
- The pattern variable `dog` only has valid scope as determined by the compiler's control-flow analysis; it cannot be used outside the scope where Java guarantees the condition is true.

**Design:** if you have to use a very long chain of `instanceof` checks to handle subtypes, consider a **polymorphic method** or an appropriate design pattern. Runtime type checking is useful, but it should not completely replace interface design and overriding.

## 7. Method Overriding: Choosing the Implementation Based on the Actual Class

An eligible instance method is **overridden** in a subclass:

```java
class Animal {
    String speak() {
        return "Âm thanh";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }
}
```

With:

```java
Animal a = new Dog();
System.out.println(a.speak()); // Gâu
```

The compiler checks:

- The expression `a` has the static type `Animal`.
- `Animal` declares a callable instance method `speak()`.

At runtime, **dynamic method dispatch** uses the actual class of the receiver to select the appropriate overriding implementation. Because the object is a `Dog`, the `Dog.speak()` version runs.

Casting the receiver to a superclass **does not force the superclass's overridden method to run**:

```java
Dog dog = new Dog();
System.out.println(((Animal) dog).speak()); // Gâu
```

`((Animal) dog)` has the static type `Animal`, but the receiver is still a `Dog` object and the call is still dispatched to `Dog`'s override.

### Want to Call the Superclass Implementation?

Inside **the body of an instance method of a subclass**, `super.method()` has special dispatch syntax:

```java
class Dog extends Animal {
    @Override
    String speak() {
        return super.speak() + " + Gâu";
    }
}
```

`super.speak()` is how a subclass requests calling the superclass's implementation. This is **not** a mechanism that “casts a Dog object into an Animal” or changes the runtime class.

## 8. Overloading: Signature Selected by Type at Compile Time

**Overloading** is different from overriding. Overloads share the same name but have **different parameter lists**; at compile time, the compiler selects the applicable method based on **the static type of the arguments**, the number of arguments, type conversions, and overload resolution rules.

Example:

```java
static void handle(Animal animal) {
    System.out.println("Overload Animal");
}

static void handle(Dog dog) {
    System.out.println("Overload Dog");
}
```

With:

```java
Animal pet = new Dog();
Dog dog = new Dog();

handle(pet);          // Overload Animal
handle(dog);          // Overload Dog
handle((Dog) pet);    // Overload Dog, because the cast makes the expression type Dog
```

**The runtime class of `pet` does not automatically route the call `handle(pet)` to the `handle(Dog)` overload.**

### 8.1. Complete Program: Overriding and Overloading Side by Side

Save as **`DispatchComparisonDemo.java`**:

```java
class Animal {
    String speak() {
        return "Animal sound";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Dog sound";
    }
}

public class DispatchComparisonDemo {
    static void show(Animal animal) {
        System.out.println("Overload Animal: " + animal.speak());
    }

    static void show(Dog dog) {
        System.out.println("Overload Dog: " + dog.speak());
    }

    public static void main(String[] args) {
        Animal asAnimal = new Dog();
        Dog asDog = new Dog();

        show(asAnimal);
        show(asDog);
        show((Dog) asAnimal);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 DispatchComparisonDemo.java
java DispatchComparisonDemo
```

Output:

```text
Overload Animal: Dog sound
Overload Dog: Dog sound
Overload Dog: Dog sound
```

The first line shows **both mechanisms working in a single call**:

1. **Compile time:** `show(asAnimal)` selects the `show(Animal)` overload because `asAnimal` has the static type `Animal`.
2. **Runtime inside the body of `show(Animal)`:** the call `animal.speak()` executes the `Dog.speak()` override because the actual receiver is `Dog`.

When analyzing the results, always separate **overload selection** from **override dispatch**.

## 9. A Superclass-Typed Receiver Does Not See Every New Member of a Subclass

It is not only arguments: **the static type of the receiver to the left of the dot** also determines which method names the compiler can see.

```java
class Parent {
    void common() {
        System.out.println("Common");
    }
}

class Child extends Parent {
    void onlyChild() {
        System.out.println("Only child");
    }
}
```

```java
Parent variable = new Child();
variable.common();        // Valid
// variable.onlyChild();   // WRONG at compile time
```

`variable` has the static type `Parent`. Even though the actual object is a `Child`, the compiler **does not allow using** `onlyChild()` through an expression of type `Parent` because this method is not declared in the API visible from `Parent`.

If you truly need that specific functionality:

```java
if (variable instanceof Child child) {
    child.onlyChild();
}
```

Or **design a common API** directly in `Parent`/an interface if that functionality is polymorphic in nature, which helps reduce the need for casting.

A superclass-typed variable cannot “automatically update” the list of members allowed to be called after you assign a subclass object to it.

## 10. Field Hiding: Selecting Fields by Static Type, Not by Runtime Class

**Fields** do not have dynamic dispatch like instance methods. If a subclass declares a field with the same name as a field in the superclass, that is **field hiding**.

Example:

```java
class Animal {
    String label = "Animal field";
}

class Dog extends Animal {
    String label = "Dog field";
}
```

```java
Animal pet = new Dog();
System.out.println(pet.label);           // Animal field
System.out.println(((Dog) pet).label);   // Dog field
```

Because `pet` has the static type `Animal`, `pet.label` selects the field declared in `Animal`. After the cast, the static type of the receiver is `Dog`, so the name `label` selects `Dog`'s field.

**This is not the same field being overridden.** A `Dog` object contains **two distinct fields** with the same name in the hierarchy, accessed through the field-selection rules.

### Java 17 Program: Fields and Methods Produce Different Results

Save as **`FieldAndMethodDemo.java`**:

```java
class Parent {
    String label = "Parent field";

    String label() {
        return "Parent method";
    }
}

class Child extends Parent {
    String label = "Child field";

    @Override
    String label() {
        return "Child method";
    }
}

public class FieldAndMethodDemo {
    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        System.out.println(parentView.label);
        System.out.println(childView.label);
        System.out.println(parentView.label());
        System.out.println(childView.label());
    }
}
```

Run:

```bash
javac -encoding UTF-8 FieldAndMethodDemo.java
java FieldAndMethodDemo
```

Stdout:

```text
Parent field
Child field
Child method
Child method
```

Explanation:

- The two **field** reads follow the corresponding static types `Parent` and `Child`.
- The two calls to **instance method `label()`** follow the overridden implementation `Child.label()` because the runtime receiver in both calls is a `Child` object.

**Recommendation:** avoid creating fields with the same name between superclass and subclass because it is easily confused with overriding. Prefer private fields and meaningful method APIs when polymorphism is needed.

## 11. Static Methods Do Not Use Dynamic Dispatch Like Instance Methods

If a subclass declares a static method with the same signature as the superclass, this is **static method hiding**, not dynamic overriding.

```java
class Parent {
    static String typeName() {
        return "Parent";
    }
}

class Child extends Parent {
    static String typeName() {
        return "Child";
    }
}
```

With:

```java
Parent p = new Child();
System.out.println(p.typeName());     // Parent
System.out.println(Child.typeName()); // Child
```

Java allows the expression `p.typeName()` in the example, but the compiler selects the static method based on **the static type `Parent`**. **You should write `Parent.typeName()` instead of `p.typeName()`** to avoid the false impression that the call will dispatch based on the runtime object.

**Quick summary:**

| Member kind | Primary selection factor |
| --- | --- |
| Overridden instance method | Signature is resolved at compile time; implementation is dispatched based on the runtime receiver |
| Method overloading | Overload signature is determined by compile-time types and overload rules |
| Hidden instance field | Field is selected based on the type of the receiving expression at compile time |
| Hidden static method | Static method name is bound according to compile-time rules, not dynamically overridden |
| Static field | Belongs to the selected class, not per-object state |

Do not say “Java always chooses by runtime class” or “Java always chooses by declared type”. Each kind of member has **specific rules**.

## 12. `null`: Has a Reference Type but No Object to Query for an Actual Class

Example:

```java
Animal pet = null;
```

- **The declared type of variable `pet`** is still `Animal`.
- The value of `pet` is currently `null`, meaning **it does not reference any object**.
- Because there is no object, there is no “runtime class of the object `pet` points to”.
- `pet instanceof Dog` returns **`false`**.
- `pet.getClass()` throws a **`NullPointerException`** when executed.
- A reference cast `(Dog) pet` with `pet == null` can produce `null` without throwing a `ClassCastException`; a cast does not create an object.

### Runnable Example of `null`

File **`NullRuntimeTypeDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

public class NullRuntimeTypeDemo {
    public static void main(String[] args) {
        Animal pet = null;

        System.out.println(pet == null);
        System.out.println(pet instanceof Dog);

        Dog casted = (Dog) pet;
        System.out.println(casted == null);

        try {
            System.out.println(pet.getClass().getSimpleName());
        } catch (NullPointerException exception) {
            System.out.println("Không có đối tượng để gọi getClass()");
        }
    }
}
```

```bash
javac -encoding UTF-8 NullRuntimeTypeDemo.java
java NullRuntimeTypeDemo
```

Stdout:

```text
true
false
true
Không có đối tượng để gọi getClass()
```

**Note:** `null` has no runtime class, yet expressions containing `null` still participate in compile-time type checking. For example, a `null` literal can be passed to a parameter of type `String` or `Integer`, and if there are two overloads that cannot be distinguished, `f(null)` may be reported as **ambiguous**.

## 13. A Variable Can Sequentially Reference Different Actual Classes

Example:

```java
Animal current = new Dog();
System.out.println(current.getClass().getSimpleName()); // Dog

current = new Cat();
System.out.println(current.getClass().getSimpleName()); // Cat
```

Suppose `Dog` and `Cat` both extend `Animal`. **The declared type of `current` remains `Animal`** throughout the variable's lifetime. However, the reference value assigned to the variable has changed, so the object currently being pointed to has a different runtime class.

**Do not interpret this as the original `Dog` object having its class changed to `Cat`.** The assignment `current = new Cat()` selects a **different** object for the variable `current`.

### Example Program Clearly Demonstrating Behavior After Reassignment

File **`ReassignmentTypeDemo.java`**:

```java
class Animal {
    String speak() {
        return "?";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }
}

class Cat extends Animal {
    @Override
    String speak() {
        return "Meo";
    }
}

public class ReassignmentTypeDemo {
    public static void main(String[] args) {
        Animal current = new Dog();
        Animal saved = current;

        System.out.println(current.speak());
        current = new Cat();
        System.out.println(current.speak());
        System.out.println(saved.speak());
        System.out.println(current == saved);
    }
}
```

```bash
javac -encoding UTF-8 ReassignmentTypeDemo.java
java ReassignmentTypeDemo
```

Stdout:

```text
Gâu
Meo
Gâu
false
```

`saved` still references the old `Dog` object. After `current` changes to `Cat`, **dynamic dispatch** of `speak()` on each variable produces the result according to its corresponding runtime object.

## 14. `Object` Is a Broad Reference Type; That Does Not Mean Every Method Is Accessible

Ordinary Java classes inherit from `Object` directly or indirectly. You can declare:

```java
Object value = "Java";
```

The actual object here is a `String`, but through a variable of type `Object`, the compiler only allows members belonging to `Object`'s API and the applicable type rules:

```java
System.out.println(value.getClass().getSimpleName()); // String
System.out.println(value.toString());                  // Java

// value.length(); // WRONG: Object does not declare length()
```

If you check:

```java
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

then in the valid branch, the pattern variable `text` has the static type `String`.

**Do not use `Object` for every variable** just to be “flexible”. An overly broad type loses compile-time type checking and API support, increasing the number of casts needed. Declare a type that is **general enough for the contract** while still accurately expressing the operations the code needs.

For example, prefer `List<String>` instead of `Object` for a variable storing a list of strings, or `Payable` instead of `Object` if the code only needs to call `amount()`.

## 15. Interfaces and Abstract Classes Are Valid Variable Types, Not Objects Created Directly

Interfaces and abstract classes can serve as the **declared type** of a variable:

```java
interface Shape {
    double area();
}

class Square implements Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    @Override
    public double area() {
        return side * side;
    }
}
```

```java
Shape shape = new Square(3);
System.out.println(shape.area()); // 9.0
```

The variable `shape` has the static type `Shape`, and the actual object has the class `Square`. No “interface Shape” object is created directly: an interface defines a **type contract**, whereas an object is created from a concrete class.

Similarly:

```java
abstract class Vehicle {
    abstract String move();
}

class Car extends Vehicle {
    @Override
    String move() {
        return "Drive";
    }
}
```

`Vehicle v = new Car();` is valid; `new Vehicle()` is invalid because `Vehicle` is an abstract class.

**Avoid confusing these three statements:**

- “The variable has the **interface type** `Shape`” — correct.
- “The `Square` object **implements the interface** `Shape`” — correct.
- “The created object is an instance of the **interface** in the sense of an object directly instantiated with `new Shape()`” — incorrect.

You can say that the `Square` object **is an instance of the type `Shape`** according to the subtype relationship and `instanceof Shape` check, but its **actual class** is still `Square`.

## 16. Static Type Affects Overload Selection When Accepting Interface-Typed Parameters

Example:

```java
interface Worker {
    String work();
}

class Developer implements Worker {
    @Override
    public String work() {
        return "Code";
    }
}
```

With two overloads:

```java
static void process(Worker worker) {
    System.out.println("Worker");
}

static void process(Developer developer) {
    System.out.println("Developer");
}
```

If:

```java
Worker w = new Developer();
Developer d = new Developer();

process(w); // Worker
process(d); // Developer
```

Both `w` and `d` can reference a `Developer` object, yet the overload is selected based on **the type of the argument expression**.

Meanwhile, `w.work()` still invokes the `Developer.work()` implementation thanks to **instance method overriding**.

**A good design:** if two overloads carry completely different business behavior, consider giving the methods meaningful names or using polymorphic methods to avoid unintended dependence on the variable's declared type.

## 17. `getClass()` and `instanceof` Differ in Purpose

Two common ways to check runtime type:

| Approach | Meaning | Characteristics |
| --- | --- | --- |
| `obj.getClass()` | Obtains the `Class` object representing the **exact actual class** of the receiver | Receiver **must not be null**; returns `Class<?>` according to context |
| `obj instanceof Dog` | Checks whether the object is compatible with the `Dog` type according to `instanceof` rules | `null instanceof Dog` is `false`; subtypes of Dog can also match |
| `obj.getClass() == Dog.class` | Checks for **the exact `Dog` class**, not a subclass | Receiver must be non-null |
| `Dog.class.isInstance(obj)` | Checks through the reflection-like Class API whether obj is an instance of Dog or a subtype | Returns false for `null` |
| `obj instanceof Dog d` | Checks + introduces the pattern variable `d` in the matching branch (Java 17) | Avoids repeated casting |

If you have:

```java
class Dog extends Animal {
}

class Puppy extends Dog {
}
```

then with `Animal animal = new Puppy();`:

- `animal instanceof Dog` is **`true`**.
- `animal.getClass() == Dog.class` is **`false`**.
- `animal.getClass() == Puppy.class` is **`true`**.
- `Dog.class.isInstance(animal)` is **`true`**.

**Key point to remember:** `instanceof` checks **subtype compatibility**, whereas `getClass() == Type.class` usually checks **exact class**. Do not choose a check just because its name sounds close to your goal; consider whether the API requires polymorphism or exactness.

### Do Not Overuse `getClass()` to Control Business Logic

Example:

```java
if (animal.getClass() == Dog.class) {
    // Only accepts the exact Dog class, not subclasses of Dog.
}
```

This snippet can break extensibility: the subclass `Puppy` will not satisfy it. If the behavior can be expressed via an overridden method, it is usually better to call a polymorphic method rather than branching repeatedly on the runtime class. Checking the exact class is still useful when **that itself is the business rule**, such as certain comparison policies or serialization handling.

## 18. Arrays: Array Variable Type and Actual Array Type

Arrays in Java are objects and also have a concrete runtime type. Reference arrays are **covariant**: in many situations, a `String[]` can be assigned to a variable of type `Object[]`.

```java
Object[] items = new String[]{"A", "B"};
```

Here:

- The declared type of the variable `items` is `Object[]`.
- The runtime type of the array object is `String[]`.
- `items[0] = "C";` is valid because `String` is compatible with the runtime component type of the array.
- `items[1] = Integer.valueOf(42);` **compiles** via the static element type `Object`, but **throws an `ArrayStoreException` at runtime** because the actual array only holds `String`.

### Runnable Java 17 Example

Save as **`ArrayRuntimeTypeDemo.java`**:

```java
import java.util.Arrays;

public class ArrayRuntimeTypeDemo {
    public static void main(String[] args) {
        Object[] items = new String[]{"A", "B"};

        System.out.println(items.getClass() == String[].class);
        items[0] = "C";
        System.out.println(Arrays.toString(items));

        try {
            items[1] = Integer.valueOf(42);
        } catch (ArrayStoreException exception) {
            System.out.println("Không thể lưu Integer vào String[]");
        }

        System.out.println(Arrays.toString(items));
    }
}
```

```bash
javac -encoding UTF-8 ArrayRuntimeTypeDemo.java
java ArrayRuntimeTypeDemo
```

Stdout:

```text
true
[C, B]
Không thể lưu Integer vào String[]
[C, B]
```

**Takeaway:** the static type `Object[]` lets the compiler treat assigning an `Object` element as valid, but the JVM also **checks the actual element type of the array** to protect the `String[]` array object.

**Do not assume primitive arrays behave like reference arrays:** `int[]` can be assigned to `Object`, but it is **not a subtype of `Object[]`**:

```java
Object any = new int[]{1, 2}; // Valid
// Object[] array = new int[]{1, 2}; // WRONG
```

The primitive array `int[]` is an object, but its `int` elements are not reference objects compatible with `Object[]`.

## 19. Generics: Reference Types That Include Type Parameters

With generics, the static type is not just a “raw” class name. For example:

```java
java.util.List<String> names = new java.util.ArrayList<>();
```

- The declared type of the variable is **`List<String>`**.
- The actual class of the collection object is **`ArrayList`**.
- `ArrayList` implements `List`.
- The `String` information in `List<String>` serves **compile-time** type checking. Because of *type erasure*, `names.getClass()` does not directly report “`ArrayList<String>`” as a separate runtime class parameterized by `String`.

### 19.1. Generics Are Not Covariant Like Arrays

The following snippet is **invalid**:

```java
java.util.List<String> strings = new java.util.ArrayList<>();
// java.util.List<Object> objects = strings; // WRONG: generics are invariant
```

Even though `String` is a subtype of `Object`, that does **not** make `List<String>` a subtype of `List<Object>`.

If it were allowed, an `objects.add(42)` call could break the guarantee that every element of `strings` is a `String`. Therefore, Java's generic type system does not allow such a conversion.

### 19.2. Using Wildcards When You Need to View Through a Broader Type

```java
java.util.List<? extends Animal> animals =
        new java.util.ArrayList<Dog>();
```

You can read an element as type `Animal`:

```java
// Animal first = animals.get(0); // Type-valid if an element exists
```

However, you cannot arbitrarily add a `Dog` or `Cat` to a `List<? extends Animal>` because the compiler does not know the concrete element type on the receiving end:

```java
// animals.add(new Dog()); // Type error
```

**Central point:** with generics, seeing the runtime class `ArrayList` is not enough to infer the compile-time element type `String`/`Dog`. You need to read the **generic declaration** and wildcard bounds.

### 19.3. Runnable Example: Interface, Generics, and Runtime Class

File **`GenericReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericReferenceDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Bình");

        System.out.println(names.getClass().getSimpleName());
        System.out.println(names.get(0));
        System.out.println(names.size());
        System.out.println(names instanceof ArrayList);
    }
}
```

```bash
javac -encoding UTF-8 GenericReferenceDemo.java
java GenericReferenceDemo
```

Stdout:

```text
ArrayList
An
2
true
```

`names` has the static type `List<String>`; its actual class is `ArrayList`. The `get` method returns a value represented by the type system as `String` at the call site, even though the collection's runtime class is not specialized for `String`.

### 19.4. `instanceof List<String>` Cannot Be Used as a Normal Runtime Check

Due to type erasure, you cannot simply write:

```java
Object value = new ArrayList<String>();
// if (value instanceof List<String>) { } // WRONG: parameterized type is not reifiable
```

You can check the raw runtime type in a valid way:

```java
if (value instanceof List<?> list) {
    System.out.println(list.size());
}
```

`List<?>` indicates that the object can be used as a list with an unknown element type; it **does not prove** that every element is a `String`. If you truly need to check the contents, you must inspect each element or use an API contract that guarantees the type.

## 20. `var`: Compile-Time Type Inference, No “Dynamically Changing Type”

Java 10+ can use `var` for local variables when the compiler infers the type from the initializer:

```java
var dog = new Dog();
```

**`var` does not turn Java into a language with dynamic typing.** It asks the compiler to infer a **concrete static type** when declaring the variable.

- With `var dog = new Dog();`, the inferred type of `dog` is `Dog`.
- With `Animal animal = new Dog();`, the declared type of `animal` is `Animal`.
- After declaration, a `var` variable cannot automatically change its static type on subsequent assignments.

Example:

```java
var dog = new Dog();
// dog = new Cat(); // Invalid if Cat is not a subtype of Dog
```

Whereas:

```java
Animal pet = new Dog();
pet = new Cat(); // Valid if both Dog and Cat extend Animal
```

With generic types, `var names = new ArrayList<String>();` infers the static type of `names` as `ArrayList<String>`, not `List<String>`. If you want code to depend on the `List` interface, **explicitly declare `List<String> names = ...`**.

### Limitations of `var`

`var` cannot be used arbitrarily as a field type or a normal method return type. It also requires an initializer to infer the type and does not allow initializing a local variable solely from a `null` literal such as `var value = null;`.

Thanks to this, `var` still remains within the **static type checking** model, without switching to a mechanism where “whichever runtime class the variable has, its members can be called”.

## 21. A Method's Return Type Also Affects How the Object Can Be Used

A method can declare that it returns a superclass/interface while actually returning a subclass object:

```java
static Animal choose() {
    return new Dog();
}
```

With:

```java
Animal pet = choose();
```

- The **declared return type** of `choose()` is `Animal`.
- The static type of the call expression `choose()` is `Animal`.
- The object returned on this run has the runtime class `Dog`.
- `choose().speak()` is valid if `Animal` declares `speak()`.
- `choose().fetch()` is invalid even though the method currently creates a `Dog`, because the compiler looks at the return type `Animal`.

If the API needs to let callers use specialized `Dog` functionality, you must consider declaring an appropriate return type, a specialized factory API, or a polymorphic design.

### Covariant Return When Overriding

An overriding instance method is allowed to have a **more specific reference return type** in cases accepted by Java:

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

When the receiver variable has the static type `DogFactory`, `factory.create()` can be viewed with the return type `Dog`. However, when the receiver is only declared as `AnimalFactory`, the compiler resolves the method's return type through **the static type `AnimalFactory`**, even though runtime dispatch invokes the `DogFactory.create()` implementation.

**Do not be mistaken:** the implementation can return a `Dog` object, while the expression at the call site still has the compile-time type `Animal` depending on the static type of the receiver and the visible method.

## 22. `final` Does Not Force a Variable to Point to the Exact Declared Class and Does Not Lock the Object

`final` on a reference variable means **the variable's value cannot be reassigned after valid initialization**. It does not mean the runtime class must match the declared type exactly.

```java
final Animal pet = new Dog();
```

Completely valid:
- Declared type: `Animal`.
- Runtime class: `Dog`.
- The variable `pet` cannot be reassigned with `pet = new Cat();`.
- If `Dog` has mutable fields/methods, the object's state **can still change** through permitted APIs.

**Distinguish `final` attached to different things:**

| Placement of `final` | Core meaning |
| --- | --- |
| `final Animal pet = new Dog();` | Cannot reassign the variable `pet` |
| `final class Dog { ... }` | Prevents other classes from extending `Dog` |
| `final void speak() { ... }` | Prevents subtypes from overriding that instance method |
| `final SomeType field;` | The field must be assigned according to final initialization rules and cannot be reassigned afterward |

A **final class** can still be referenced through a superclass/interface; `String` is an example of a final class commonly used through broader types such as `Object` or `CharSequence`.

## 23. One Object Can Satisfy Multiple Interfaces at the Same Time

An actual class can implement multiple interfaces, while a variable is declared with **one specific reference type** at that location.

```java
interface Named {
    String name();
}

interface Identified {
    int id();
}

class Member implements Named, Identified {
    @Override
    public String name() {
        return "An";
    }

    @Override
    public int id() {
        return 7;
    }
}
```

Variables:

```java
Member member = new Member();
Named named = member;
Identified identified = member;
Object object = member;
```

All four variables can reference **a single `Member` instance**, yet:

- `named.name()` is valid; `named.id()` is invalid through the static type `Named`.
- `identified.id()` is valid; `identified.name()` is invalid through the static type `Identified`.
- `member.name()` and `member.id()` are both valid.
- `object.toString()` is valid because of `Object`; `object.name()` is invalid through the static type `Object`.

If you need an API requiring **both contracts**, you can declare a combined interface, or use generic bounds as needed. You do not always have to cast the reference to a single implementation class.

## 24. Comprehensive Example: One Object Through Multiple Views

Save to **`TypeViewReview.java`**:

```java
interface Named {
    String name();
}

class Person implements Named {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }

    String role() {
        return "Person";
    }
}

class Student extends Person {
    Student(String name) {
        super(name);
    }

    @Override
    String role() {
        return "Student";
    }

    String school() {
        return "Java Academy";
    }
}

public class TypeViewReview {
    static String accept(Person person) {
        return "Person overload: " + person.role();
    }

    static String accept(Student student) {
        return "Student overload: " + student.role();
    }

    public static void main(String[] args) {
        Student student = new Student("An");
        Person person = student;
        Named named = student;
        Object any = student;

        System.out.println(student == person);
        System.out.println(person == named);
        System.out.println(named == any);
        System.out.println(any.getClass().getSimpleName());

        System.out.println(named.name());
        System.out.println(person.role());

        System.out.println(accept(person));
        System.out.println(accept(student));

        if (person instanceof Student match) {
            System.out.println(match.school());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 TypeViewReview.java
java TypeViewReview
```

Stdout:

```text
true
true
true
Student
An
Student
Person overload: Student
Student overload: Student
Java Academy
```

Detailed explanation:

1. One `Student` object is created by `new Student("An")` and referenced through four differently typed variables: `Student`, `Person`, `Named`, and `Object`.
2. All three `==` comparisons are true because the variables still point to one object; different declared types **do not create new objects**.
3. `any.getClass().getSimpleName()` returns `Student`, the actual class of the object.
4. `named.name()` is valid because the static type `Named` has the `name()` method.
5. `person.role()` is valid because `Person` declares `role()`; at runtime the `Student.role()` override runs, so it prints `Student`.
6. `accept(person)` selects the **overload taking `Person`** due to the static type of the argument expression `person`. Inside that overload, `person.role()` still runs `Student`'s override.
7. `accept(student)` selects the overload taking `Student` because the static type of the argument is `Student`.
8. `person instanceof Student match` checks the runtime type; when true, the variable `match` has the static type `Student` and can call `school()`.

This is an important example because it simultaneously demonstrates **static type**, **runtime class**, **overload resolution**, **dynamic dispatch**, and **safe downcasting** without changing the original object.

## 25. Common Mistakes and How to Fix Them

| Situation | Common mistake | Correct understanding/fix |
| --- | --- | --- |
| `Animal a = new Dog();` | Thinking the `Dog` object turns into an `Animal` | Only referenced through a superclass-typed variable; the runtime class is still `Dog` |
| `a.fetch()` with `fetch` only in `Dog` | Thinking Java sees runtime Dog and will let it compile | The compiler checks the static type `Animal`; needs a shared API or cast/`instanceof` |
| `Dog d = a;` with `a` declared as `Animal` | Thinking no cast is needed because runtime is Dog | Requires a valid downcast and may need a runtime check |
| `(Dog) a` when the actual object is `Cat` | Thinking the cast will convert the object into Dog | Can throw `ClassCastException` |
| `a.speak()` runs the `Dog` version | Thinking variable `a` changed its static type | Static type does not change; this is overriding and dynamic dispatch |
| `handle(a)` chooses the `Animal` overload | Thinking runtime should select `Dog` | Overloads are resolved by the compile-time type of the argument |
| `a.label` and `((Dog)a).label` differ | Thinking fields are overridden | Field hiding selects based on the static type of the receiver |
| `Parent p = new Child(); p.staticMethod()` | Thinking static methods dispatch at runtime | Static hiding/selection happens at compile time; should be called via the class name |
| `a.getClass()` when `a == null` | Thinking `null` has a runtime class | Throws `NullPointerException`; use a guard |
| `a instanceof Dog` with `a == null` | Thinking an error occurs due to null | Result is `false` |
| `Object x = "Hi"; x.length()` | Thinking the compiler sees the String inside | Object does not declare `length()`; use intentional pattern/cast |
| `List<String> l = new ArrayList<>();` | Thinking `l.getClass()` specifically represents `ArrayList<String>` | Runtime class is `ArrayList`; generic type arguments are typically subject to erasure |
| `List<Object> dst = List<String>` | Thinking generics are covariant like arrays | Generics are invariant; use wildcards or compatible APIs |
| `Object[] a = new String[2]; a[0] = 1;` | Thinking Object[] allows any object into the array | Runtime check throws `ArrayStoreException` |
| `var x = new Dog();` | Thinking the type changes dynamically with assignments | `var` infers the static type `Dog` once |
| `final Animal a = new Dog();` | Thinking the runtime class must be exact `Animal` | `final` forbids reassigning the variable, not requiring the object to belong strictly to the superclass |
| `Animal a = new Dog(); a = new Cat();` | Thinking the Dog object turns into a Cat | Variable `a` changes its reference to a new object; the old Dog does not change class |

## 26. Self-Practice Exercises and Answers

### Exercise 1 — Which Type Is Static, Which Is Runtime?

```java
Object value = new StringBuilder("Java");
```

**Answer:** variable `value` has the declared type `Object`; the runtime class of the object is `StringBuilder`. `value.append(" 17")` does not compile because `Object` does not have `append`; you can use the check:

```java
if (value instanceof StringBuilder builder) {
    builder.append(" 17");
}
```

Then the original `StringBuilder` object is modified; no new object is created just because the pattern variable `builder` appears.

### Exercise 2 — Overriding by Runtime Class

```java
class Parent {
    String text() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String text() {
        return "Child";
    }
}
```

```java
Parent p = new Child();
System.out.println(p.text());
```

**Answer:** prints `Child`. The compiler knows `Parent.text()`; the runtime selects `Child`'s implementation.

### Exercise 3 — Overloading by Argument Type

```java
static void print(Object value) {
    System.out.println("Object");
}

static void print(String value) {
    System.out.println("String");
}
```

```java
Object a = "Hi";
String b = "Hi";
print(a);
print(b);
```

**Answer:**

```text
Object
String
```

Both expressions can reference a string, but the static type of `a` is `Object`, and that of `b` is `String`. The overload is selected at compile time.

### Exercise 4 — Does the Runtime Class Change When Reassigning a Variable?

```java
Animal a = new Dog();
Animal old = a;
a = new Cat();
```

**Answer:** `a` now references a `Cat` object; `old` continues to reference the original `Dog` object. Neither object changes its actual class. The declared type of both `a` and `old` remains `Animal`.

### Exercise 5 — Casting with `null`

```java
Animal a = null;
Dog d = (Dog) a;
System.out.println(d == null);
System.out.println(a instanceof Dog);
```

**Answer:**

```text
true
false
```

Casting `null` to reference type `Dog` produces `null`; `instanceof` on `null` returns false. Calling `d.fetch()` will throw a `NullPointerException`.

### Exercise 6 — Fields and Methods Differ

```java
class A {
    String value = "A";

    String value() {
        return "method A";
    }
}

class B extends A {
    String value = "B";

    @Override
    String value() {
        return "method B";
    }
}
```

```java
A ref = new B();
System.out.println(ref.value);
System.out.println(ref.value());
```

**Answer:**

```text
A
method B
```

The field is selected according to the static type `A`; the overridden instance method is selected according to the runtime object `B`.

### Exercise 7 — Generics and Actual Class

Suppose:

```java
java.util.List<String> names = new java.util.ArrayList<>();
Object object = names;
```

**Answer:**

- Static type of `names`: `List<String>`.
- Static type of `object`: `Object`.
- Runtime class of the object both variables point to: `ArrayList`.
- `names.add("A")` is valid; `object.add("A")` does not compile because `Object` has no `add`.
- `object instanceof java.util.ArrayList` can be used to check the runtime class type, but it does not itself prove that the list contains only `String`.

### Exercise 8 — Choosing a Better Declared Type

If the code needs to use the `add`, `get`, and `size` methods of a list of strings and does not need `ArrayList`-specific APIs, you should write:

```java
java.util.List<String> names = new java.util.ArrayList<>();
```

instead of:

```java
Object names = new java.util.ArrayList<String>();
```

**Reason:** declaring via the `List<String>` interface exposes the **required contract**, while still allowing the implementation class to be changed later without scattered casts.

## 27. Checklist for Analyzing a Reference Variable

1. **Read the variable declaration**: what is `Type variable`? Is it a generic type like `List<String>`?
2. **Read the creation/assignment expression**: `new Subtype()`, a method return value, a cast, or another reference?
3. **Determine the compile-time type of the expression being used**: variable names, casts, `new`, method calls, and ternary expressions can have different types.
4. **Determine the runtime class** if the reference is non-`null`: which class does the created object belong to?
5. **Count objects by `new` and actual creation paths, not by variable names**: multiple variables can alias the same object.
6. **If calling a method**, does the compiler see the name/signature through the static type? If not, you must change the API or check/cast properly.
7. **If an instance method is overridden**, inspect the runtime receiver to determine which implementation runs.
8. **If there are multiple overloads**, inspect the static types of the arguments rather than relying on the runtime object to guess the signature.
9. **If reading a field or calling a static method**, remember they do not use dynamic dispatch like overridden instance methods.
10. **If downcasting**, check runtime compatibility; prefer `instanceof` patterns in Java 17 when appropriate.
11. **If `null`**, there is no object to query with `getClass()`; `instanceof` returns false and dereferencing can throw `NullPointerException`.
12. **If using arrays/generics**, consider array runtime checks, erasure, and generic invariance.
13. **If the variable is reassigned**, the runtime class of the currently referenced object may change, but **the variable's declared type stays the same**.
14. **Design APIs around an appropriate interface/superclass**, so you can use polymorphism while keeping compile-time type safety and limiting unnecessary casts.

## Key Takeaways

- **Declared type/static type** is the information the compiler uses to check member access, type compatibility, and overload selection.
- **Actual class/runtime class** belongs to **the object being referenced** and does not always match the variable's declared type.
- `Animal a = new Dog();` is **one Dog object referenced through an Animal-typed variable**; it does not create a second Animal object.
- **Upcasting** widens the static type view; **downcasting** checks a narrower view at runtime without transforming the object.
- **Overriding** allows an instance method implementation to execute according to the runtime receiver; **overloading**, **field hiding**, and **static method hiding** have selection rules based on compile-time information.
- `instanceof` is used to check a subtype-compatible runtime type; `getClass()` retrieves the exact actual class of a non-`null` receiver.
- **`null` does not reference any object**; a variable still retains its declared type even when its value is `null`.
- **Reassigning a variable does not change the class of the old object**; it only changes which object the variable references. The static type of the variable does not automatically change on assignment.
