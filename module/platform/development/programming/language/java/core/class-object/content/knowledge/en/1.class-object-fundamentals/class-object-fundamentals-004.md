# Distinguishing Class Declarations, Reference Variables, and Class Instances in Java

In Java, the three concepts of **class**, **reference variable**, and **instance/object** are closely related, yet **not the same thing**. Properly understanding the difference helps you accurately read the statement `Person p = new Person("An");`, predict data mutations across multiple variables, avoid `NullPointerException`, and distinguish a declared type from the actual object when using inheritance.

## 1. Quick Overview of the Three Concepts

| Concept | What is it? | Example | Does it create a new `Person` object? |
| --- | --- | --- | --- |
| **Class declaration** | Defines a reference type and the type's members: fields, methods, constructors, ... | `class Person { ... }` | **No** |
| **Reference variable declaration** | Declares a variable of a reference type; the variable can hold a reference to a compatible object or `null` | `Person p;` | **No** |
| **Creating a class instance** | Instantiates a new object of the class, usually using `new` and a constructor | `new Person("An")` | **Yes** |

The three lines below represent three different actions:

```java
class Person { }       // 1. Declare the Person class
Person p;              // 2. Declare the reference variable p (inside a method)
p = new Person();      // 3. Create an instance and assign the reference to p
```

The snippet above is for syntax illustration; the last two statements must reside in a context permitted by Java (such as a method body) and cannot be placed arbitrarily directly inside a class body.

**Reading formula:** `Person p = new Person();` combines a **variable declaration** (`Person p`), **object creation** (`new Person()`), and **reference assignment** (`=`). In that statement, `Person` on the left specifies the type of the variable, while `Person` after `new` specifies the class to instantiate.

## 2. Class Declaration: Describing Type and Behavior

```java
class Person {
    String name;                    // instance field belonging to each object
    static int totalCreated = 0;    // static field belonging to the class

    Person(String name) {           // constructor: name matches the class name, with no return type
        this.name = name;
        totalCreated++;
    }

    void introduce() {
        System.out.println("Mình là " + name);
    }
}
```

- `class Person` defines a type named `Person`. From then on, code can declare variables of type `Person`, invoke constructors, or use members with appropriate access permissions.
- `name` is an **instance field**: each `Person` object has its own `name` state. The `this` keyword inside a method/constructor refers to the object currently being operated on.
- `introduce()` is an **instance method**: when `p.introduce()` is called, the method operates on the object that `p` currently references.
- `totalCreated` is a **static field**: a class member shared across instances, accessed explicitly via `Person.totalCreated`. In this example, this value is incremented by the constructor; it is not a counter of live objects.

**Declaring a class is not the same as creating an object.** The `Person` definition only provides the type and the rules for creating and using objects. Java also has `static` members that can be used without creating a `Person` instance, depending on access permissions. A constructor is invoked when a corresponding instantiation operation occurs.

Class names are conventionally written in `UpperCamelCase` (`Person`, `BankAccount`), while variable names are written in `lowerCamelCase` (`person`, `currentAccount`). This is a naming convention, not a fundamental difference between classes and variables.

## 3. Reference Variables: Variables Holding a Reference Value

```java
Person first;                 // local variable declaration only
Person second = null;         // variable has value null: does not reference any object
first = new Person("An");     // first receives a reference to a new object
Person alias = first;         // copies the reference value; does NOT create a new Person
```

Key points to remember:

1. **The declared type** (`Person`) governs which operations are allowed at compile time. **The variable name** (`first`) is the name used to access the reference value stored in the variable.
2. A reference value logically denotes the object that the variable points to. Java does not provide C/C++-style address/pointer operators to directly manipulate an object's memory address.
3. Multiple variables can hold references to **the same object**. The assignment `alias = first` copies the reference value; it does not copy the object and does not call a constructor.
4. A reference variable can be **reassigned** to reference another object or `null` (subject to constraints such as `final` variables).
5. When an object is no longer referenced through appropriate reachable paths, it may become eligible for garbage collection; collection and its timing are not guaranteed to be immediate.

**Important note on uninitialized variables:** for a local variable `Person first;`, Java requires the variable to be definitely assigned a value before it is read. You must not assume that it is automatically `null`. In contrast, instance reference fields and `static` fields that are not explicitly initialized receive the default value `null`.

## 4. Instance: A Concrete Instantiated Object

Consider:

```java
Person an = new Person("An");
Person binh = new Person("Bình");
```

Each normal execution of the `new Person(...)` expression creates **a new `Person` object**, performs the initialization steps, and invokes the corresponding constructor. The `new` expression then yields a reference value pointing to the newly created object; the assignment stores that reference in the variable.

In the example above, there is **one `Person` class**, **two reference variables** `an` and `binh`, and **two distinct instances**. Both follow the same class definition but have their own `name` state:

```text
Variable an   ──────────> Person object #1 { name: "An" }
Variable binh ──────────> Person object #2 { name: "Bình" }
                (same Person type, different identity)
```

The labels `#1` and `#2` in the diagram are only for distinguishing object identity; they are **not memory addresses** or actual properties of `Person`.

An object **does not require a dedicated variable** bound to it. For example, `new Person("An").introduce();` creates the object, invokes the method via a temporary reference, and then does not retain that reference in any variable we declared.

## 5. Full Example: Class, Reference Variables, Objects, and Aliases

Save all of the following code to the file **`Demo.java`**:

```java
class Person {
    String name;
    static int totalCreated = 0;

    Person(String name) {
        this.name = name;
        totalCreated++;
    }

    void introduce() {
        System.out.println("Mình là " + name);
    }
}

public class Demo {
    public static void main(String[] args) {
        Person p;                         // declare variable, no object created yet
        p = new Person("An");             // first object
        Person same = p;                  // another variable pointing to the same object
        Person other = new Person("Bình");// second object

        same.name = "Lan";                // modify the shared object
        p.introduce();
        System.out.println(p == same);
        System.out.println(p == other);
        System.out.println(Person.totalCreated);

        p = other;                        // change p's reference, without modifying same
        p.introduce();
        same.introduce();
        System.out.println(p == same);
    }
}
```

Compile and run (Java 17 or later; the code also uses basic Java syntax):

```bash
javac -encoding UTF-8 Demo.java
java Demo
```

Expected output:

```text
Mình là Lan
true
false
2
Mình là Bình
Mình là Lan
false
```

Step-by-step explanation:

- `class Person` declares **one type**. The two executions of `new Person(...)` create **two objects**, incrementing `Person.totalCreated` to `2`.
- `p`, `same`, and `other` are **three reference variables**. After `Person same = p;`, both `p` and `same` point to the original object named `"An"`.
- The statement `same.name = "Lan";` modifies **the object's state**, so calling `p.introduce()` also prints `Mình là Lan`.
- `p == same` is initially `true` because both reference the same object; `p == other` is `false` because they are two different objects.
- `p = other;` **only changes the reference value of variable `p`**. It does not transfer data from one object to another and does not alter the variable `same`; therefore, the subsequent call on `p` prints `Bình`, while `same` still prints `Lan`.

Logical diagram after running `Person same = p;` and before `p = other;`:

```text
p      ────┐
           ├────> Person #1 { name: "Lan" }
same   ────┘
other  ─────────> Person #2 { name: "Bình" }
```

After `p = other;`:

```text
same   ─────────> Person #1 { name: "Lan" }
p      ────┐
           ├────> Person #2 { name: "Bình" }
other  ────┘
```

**Self-check question:** How many `Person` object creations occur in `main`? **Two**, because `new Person(...)` is executed only twice. How many `Person` reference variables are declared in `main`? **Three**: `p`, `same`, and `other`. The number of variables does not determine the number of objects.

## 6. Distinguishing Primitive Types, `null` References, and Unassigned Variables

| Code | Meaning | Consequence |
| --- | --- | --- |
| `int number = 7;` | `int` is a primitive type; the variable directly holds the value `7` | `int other = number;` copies the numeric value |
| `Person p;` | Declares a local reference variable, unassigned | `p` cannot be read before assignment |
| `Person p = null;` | The reference has been assigned the special value `null` | No `Person` instance has been created |
| `Person p = new Person("An");` | Creates an instance and stores the reference | A new object exists |
| `Person q = p;` | Copies the reference from `p` to `q` | `p` and `q` can point to the same object |

Syntax illustration, **not a standalone program**:

```java
Person p;
System.out.println(p);       // Compile error: variable p might not have been initialized
```

Meanwhile:

```java
Person p = null;
System.out.println(p);       // Prints: null
// p.introduce();            // If uncommented, throws NullPointerException at runtime
```

The `null` example does not instantiate an object; invoking an instance method or accessing an instance field through a `null` reference results in a `NullPointerException` (except in certain cases such as `static` member access syntax, which is resolved by type; access static members via the class name). The way to prevent this is to design your data to avoid unnecessary `null` values or check `p != null` before accessing when `null` is a valid state.

Do not conflate **declaration**, **assignment**, and **object instantiation**. These actions may appear on a single line, yet they are fundamentally independent.

## 7. Using a Test to Separate Identity and Content

After reading the syntax for variable declaration and instance creation, one more test is needed to avoid a false inference: **two successful `new` calls create two distinct objects**, even when all visible data looks identical.

~~~java
Person first = new Person("An");
Person second = new Person("An");
Person alias = first;
System.out.println(first == second);          // false
System.out.println(first == alias);           // true
System.out.println(first.name.equals(second.name)); // true
~~~

This is a **snippet** using Person as declared in section 2 and must be placed inside a method. `first == second` checks whether they are the same instance; comparing the contents of `name` checks the String value; `alias` only copies the reference. In the Person class, which does not override `equals`, the call `first.equals(second)` is also false due to Object's default behavior.

This article only uses these tests to **identify what is declared, what is actually created, and what is being shared**. Designing `equals/hashCode` based on value or business identity is a deeper decision that does not automatically arise from `new` syntax or variable names.

## 8. A Variable's Declared Type Can Differ from the Object's Actual Class

With inheritance/polymorphism, the variable type on the left can be a superclass or interface, while the instance on the right is a compatible subclass. This scenario most clearly illustrates why **the variable type** and **the referenced object** must not be conflated.

Save the following code to **`ReferenceTypeDemo.java`**:

```java
class Animal {
    void sound() {
        System.out.println("Âm thanh chung");
    }
}

class Dog extends Animal {
    @Override
    void sound() {
        System.out.println("Gâu");
    }

    void fetch() {
        System.out.println("Nhặt bóng");
    }
}

public class ReferenceTypeDemo {
    public static void main(String[] args) {
        Animal animal = new Dog();
        animal.sound();
        System.out.println(animal instanceof Dog);

        if (animal instanceof Dog dog) {
            dog.fetch();
        }
    }
}
```

```bash
javac -encoding UTF-8 ReferenceTypeDemo.java
java ReferenceTypeDemo
```

Output:

```text
Gâu
true
Nhặt bóng
```

In `Animal animal = new Dog();`:

- `Animal` is the **declared type** (static type) of the variable `animal`.
- `animal` is the **reference variable**, holding a reference to an instance.
- `new Dog()` creates **an object whose actual class is `Dog`**; it does not create a separate `Animal` object.
- `animal.sound()` is valid because `Animal` declares the `sound()` method; the overridden version in `Dog` runs due to dynamic dispatch.
- `animal.fetch()` does not compile, because the declared type `Animal` does not provide `fetch()`. Checking `instanceof` with the pattern `Dog dog` (officially supported since Java 16) provides a `Dog`-typed reference in the true branch to safely call `fetch()`.

This does not turn any object into any type: a variable can only accept reference values whose types are **compatible according to Java's rules**.

## 9. `final` and Parameter Passing: Still Distinguishing Variables from Objects

**`final` references:** 

```java
final Person p = new Person("An");
p.name = "Lan";                 // Valid: modifies a field of the object
// p = new Person("Bình");      // Compile error: cannot reassign a final variable
```

`final` restricts **the reference variable `p` from being reassigned after initialization**; it does not automatically make the referenced object immutable. Immutability requires appropriate class and state design.

**Java passes arguments by value (pass-by-value)**, even when that value is a reference. Consider the following illustration inside the same class that can access `Person`:

```java
static void rename(Person target) {
    target.name = "Lan";         // affects the external object
}

static void replace(Person target) {
    target = new Person("Khác"); // only reassigns the local parameter variable
}
```

When `rename(p)` is called, the parameter `target` receives **a copy of the reference value**, so changing `target.name` is also observed through `p`. When `replace(p)` is called, reassigning `target` does not reassign the caller's variable `p`. This is a direct consequence of the fact that a reference variable and an object are two distinct entities.

## 10. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| “Declaring `class Person` already creates a `Person`.” | A class declaration defines a type; creating an instance is a separate operation. |
| “`Person p;` automatically creates a `Person`.” | It only declares a variable; a local variable does not even have a value to read yet. |
| “`Person p = null;` means there is an empty object.” | `null` means no object is referenced through `p`. |
| “`Person q = p;` copies all fields to create a new object.” | It only copies the reference value; two variables can point to the same object. |
| “Assigning `p = other;` modifies the contents of the old object.” | It changes `p`'s reference; the old object's state only changes if an operation modifies that object. |
| “If there are three reference variables, there must be three objects.” | The number of variables and the number of objects are independent; one object can have multiple references. |
| “If two objects have identical fields, then `a == b` is `true`.” | `==` checks object identity for reference types. |
| “`final Person p` creates an immutable Person.” | `final` forbids reassigning `p`; an object's immutability depends on the class design. |
| “A variable's type always equals the object's actual class.” | `Animal animal = new Dog();` shows that the declared type and runtime type can differ. |
| “Once a reference is lost, the object is immediately garbage-collected.” | The object may still have other references; garbage collection has no guaranteed timing. |

## 11. Code-Reading Practice and Comprehension Check

Based on the `Person` class in section 5, predict the number of objects and the output before reading the solution:

```java
Person a = new Person("Một");
Person b = a;
Person c = new Person("Hai");

b.name = "Đã đổi";
a = c;

System.out.println(b.name);
System.out.println(a.name);
System.out.println(a == c);
System.out.println(a == b);
```

**Answer:** Two `Person` instances are created. The output in order is:

```text
Đã đổi
Hai
true
false
```

Reason: initially, `a` and `b` point to the same object; `b.name` modifies that object. After `a = c`, variable `a` switches to the same object as `c`, while `b` continues pointing to the original object. This snippet is an illustrative method body and can be placed inside `main` of a test class if `Person` has already been declared.

When reading any Java line that has a class name and an `=` sign, ask yourself: **(1)** what type is being declared? **(2)** which variable holds the reference? **(3)** is `new` actually being called to create an object? **(4)** which variables are referencing the same object? Those four questions are enough to accurately distinguish class declarations, reference variables, and instances in most basic Java scenarios.
