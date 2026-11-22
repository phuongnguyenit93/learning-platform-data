# Classes and Objects in Java: Concepts, Purpose, and Relationship

In Java, a **class** describes a programmer-defined data type; an **object** is an entity created and used at runtime. A solid grasp of these two concepts helps you organize data along with its related behavior, model problems, and understand how reference variables interact with objects.

## 1. What Is a Class?

A class is a **definition** for objects of the same kind. Depending on its purpose, a class can declare:

- **Attribute/field:** data describing the state of an object, such as a student's name and number of credits.
- **Method:** behavior that an object can perform, such as adding credits or displaying information.
- **Constructor:** code that initializes state when a new object is created; its name matches the class name and it has no return type.
- **Access rules:** for example, `private` protects internal data, while appropriate methods provide ways to use that data.

Declaring a class **does not mean** an object of that class already exists. For example, the line `class Student { ... }` describes the `Student` type, whereas `new Student(...)` requests creating an instance (for an instantiable class).

Think of a class like a house blueprint: the blueprint specifies the general characteristics and structure, while each house built from the blueprint is a separate entity. This is an analogy to make learning easier; in Java, a class also contains `static` methods, access rules, and many other constructs.

## 2. What Is an Object?

An object is an **instance** of a class at runtime. You can observe an object through three aspects:

1. **State:** the values of the fields belonging to each object, such as `name = "An"`, `credits = 12`.
2. **Behavior:** the operations that can be called on the object, such as `earnCredits(3)` or `summary()`.
3. **Identity:** two objects can hold identical data and still be two separate objects. In Java, the `==` operator on two references checks whether they point to the same object.

When using `new` with an ordinary class, Java allocates the object, performs field initialization, and invokes the matching constructor. The object-creation expression produces a **reference** to the new instance, which can be stored in a variable. A reference should not be understood as a numeric memory address for programmers to manage manually.

| Criterion | Class (`class`) | Object (`object`) |
| --- | --- | --- |
| Role | Defines the type, structure, and behavior | Concrete entity of that type at runtime |
| Example | `Student` | Student An, student Bình |
| State data | Declares instance fields | Holds each object's own field values |
| Behavior | Declares/implements methods | Executes methods when invoked via a reference |
| Quantity | One definition can serve as the type for many instances | Multiple objects can be created from the same class |

A class is a concept about **type and organization**, whereas an object is a concept about **concrete entity and state**. A class can also exist without the program ever instantiating any object from it.

## 3. Complete Example: One Class, Multiple Objects

Create the file **`ClassObjectDemo.java`** with the following content. The file contains two top-level classes in the same file; only `ClassObjectDemo` is `public`, so the file name must match the `public` class.

~~~java
class Student {
    private final String name;
    private int credits;

    Student(String name, int credits) {
        this.name = name;
        this.credits = credits;
    }

    void earnCredits(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        credits += amount;
    }

    String summary() {
        return name + ": " + credits + " tín chỉ";
    }
}

public class ClassObjectDemo {
    public static void main(String[] args) {
        Student an = new Student("An", 12);
        Student binh = new Student("Bình", 9);

        System.out.println(an.summary());

        an.earnCredits(3);

        System.out.println(an.summary());
        System.out.println(binh.summary());
    }
}
~~~

Compile and run on Java 17 or later (from the directory containing the file):

~~~bash
javac -encoding UTF-8 ClassObjectDemo.java
java ClassObjectDemo
~~~

Expected output on stdout:

~~~text
An: 12 tín chỉ
An: 15 tín chỉ
Bình: 9 tín chỉ
~~~

Part-by-part analysis:

- `Student` is the **class**. It defines that a student has `name`, `credits`, and the behaviors `earnCredits`, `summary`.
- `Student an` declares a local variable named `an` of **reference type** `Student`; merely declaring the variable does not create an object.
- `new Student("An", 12)` creates the first object and initializes its two fields. `new Student("Bình", 9)` creates the second object.
- `an` and `binh` hold two references to two different objects. They both follow the `Student` class definition but have **independent state**.
- `this.name = name` refers to the object being initialized on the left-hand side and the `name` parameter on the right-hand side. `this` is a reference to the current object inside a constructor or instance method.
- `an.earnCredits(3)` only updates the `credits` field of the object referenced by `an`. The `credits` value of `binh` remains 9.
- `private` prevents code outside the class from modifying the fields directly. Changing state through `earnCredits` allows checking `amount > 0`.
- `final` on the `name` field prevents reassigning that field after it has been validly initialized; it does not by itself make the entire object immutable. `credits` can still change.

The relationship among the class, reference variables, and objects can be visualized as follows:

~~~text
        Student class definition
        (fields, constructor, methods)
                  |
         describes the type of
                  |
            +-----+-----+
            |           |
          an            binh        <- reference variables
            |           |
            v           v
     Student object  Student object  <- two separate instances
     name = "An"     name = "Bình"
     credits = 15    credits = 9
~~~

**Key takeaway:** field and method definitions reside in the class, while the values of instance fields belong to each individual object. Calling an instance method typically acts on the receiver object.

## 4. A Reference Variable Is Not the Object Itself

A common mental mistake is treating `Student an` or `Box first` as the object itself. In reality, a reference-type variable **stores a reference** to an object or the value `null`. Therefore, multiple variables can refer to the same object; creating a new variable does not automatically create a new instance.

Create a standalone file **`ReferenceDemo.java`**:

~~~java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class ReferenceDemo {
    public static void main(String[] args) {
        Box first = new Box(5);
        Box alias = first;
        Box separate = new Box(5);

        alias.value = 7;

        System.out.println(first.value);
        System.out.println(separate.value);
        System.out.println(first == alias);
        System.out.println(first == separate);

        first = null;
        System.out.println(alias.value);
    }
}
~~~

~~~bash
javac ReferenceDemo.java
java ReferenceDemo
~~~

Stdout:

~~~text
7
5
true
false
7
~~~

Why?

1. `first` points to a `Box` object with `value = 5`.
2. `alias = first` **copies the reference**, not the object. Both variables point to the same `Box`.
3. `separate = new Box(5)` creates another `Box`, even though it initially has the same value 5.
4. `alias.value = 7` modifies the shared object, so `first.value` is also 7; `separate.value` remains 5.
5. `first == alias` is `true`, whereas `first == separate` is `false`: `==` here compares **reference identity**, not field contents.
6. `first = null` only changes the value of the `first` variable; the original object is still accessible through `alias`.

Visualization:

~~~text
first ------+
            |
alias ------+----> Box { value = 7 }

separate --------> Box { value = 5 }
~~~

When `first = null`, only `first`'s arrow disappears. `alias` still holds a reference to the object. If an object no longer has any reachable reference path to it, it **may be eligible** for the garbage collector to reclaim later; assigning `null` does not mean immediate reclamation.

Java passes arguments **by value**: when passing a reference variable into a method, the value that gets copied is the reference itself. Consequently, the method can modify the shared object's state if permitted, but reassigning the parameter variable does not make the caller's variable point to another object. This is a direct consequence of how references work, not a C++-style pass-by-reference mechanism.

## 5. Why Do We Need Classes and Objects?

Classes and objects help solve problems that a loose collection of variables handles poorly:

- **Bundling data with behavior:** instead of scattering `studentName`, `studentCredits`, and all processing functions across multiple places, `Student` provides a single place to define related operations.
- **Reusing templates:** write the class once and create multiple objects for multiple students, with each object maintaining its own state.
- **Modeling the problem:** concepts such as an order, an account, or a study session can become classes; each specific case is an object.
- **Encapsulation and rule enforcement:** keep fields `private` and provide methods to validate conditions before modifying data.
- **Ease of change and testing:** calling code works through meaningful operations; classes with clear responsibilities are easier to maintain.

Not every noun in the requirements has to become a class. Only create a class when it genuinely represents data/behavior or rules that need to be managed. Avoid classes that merely hold a bunch of `public` fields, forcing other components to modify state directly without validation.

## 6. Instance Members and Static Members

Within the same class, there are two groups of members to distinguish:

| Kind | Belongs to | Typical usage |
| --- | --- | --- |
| Instance field, such as `credits` | Each individual object | `an.summary()`, accessing the field from the object's methods |
| Instance method, such as `earnCredits` | Behavior invoked with a receiver object | `an.earnCredits(3)` |
| `static` field | The class, shared across objects of the class within the same runtime context | `Student.createdCount` |
| `static` method | The class, with no `this` receiver object | `Math.max(2, 5)` |

Example illustrating class members (this snippet is **part of a class**, not a standalone program):

~~~java
class Counter {
    static int created = 0;

    Counter() {
        created++;
    }
}
~~~

After sequentially calling `new Counter()` twice, `Counter.created` equals 2; the count is **shared**, without a separate copy for each object. In multithreaded applications, the `created++` operation does not by itself guarantee concurrency safety; that is a separate issue, not a default property of `static`.

A `static` method has no `this` to access instance state directly. However, it can still receive an object reference via a parameter and operate on that object.

## 7. From Real-World Requirements to Classes and Objects

Suppose you need to manage academic results. A useful way to think about it is:

1. **Identify the entity to manage:** each student has their own data and operations, so the `Student` class can be used.
2. **Choose the state:** name and credit count are a minimal example; only add fields that are truly needed for behavior.
3. **Choose the behavior:** adding credits, retrieving summary information; behaviors should have names that express business meaning.
4. **Choose validation rules:** added credits must be positive; the state-changing method should be responsible for validating this.
5. **Create the necessary instances:** `an` and `binh` represent two different students. Changes to one do not automatically alter the other.
6. **Check identity and reference sharing:** if two variables need to manage the exact same student, the same reference can be passed; if two independent entities are needed, two appropriate objects must be created.

A class does not necessarily correspond to exactly one object. The common relationship is **one class definition → zero, one, or many instances**; multiple reference variables can point to **one instance**.

## 8. Basic Lifecycle and Limits to Understand Correctly

- **At write/compile time:** a `class` declaration establishes a type for the compiler to check syntax, access permissions, and data types. The class may be loaded/initialized by the JVM when needed at runtime.
- **At object creation:** the expression `new Student(...)` requests creating an instance and running the constructor. For an abstract class (`abstract class`) or an interface, you cannot directly use `new` on that abstract type itself.
- **During use:** a variable holds a reference; instance members are accessed through a valid reference. Calling a method on a `null` reference causes a `NullPointerException` in normal cases.
- **When no longer reachable:** the object may be reclaimed by the garbage collector at a time determined by the JVM. Do not program on the assumption that dropping a reference will destroy the object immediately.

Not every Java object is written in the form `new T(...)`: for example, the literal `"hello"` represents a `String` through a language-specific mechanism. Still, both `String` and `Student` are reference types (unlike primitives `int`, `boolean`, `double`).

A further distinction: an unassigned reference-type instance field receives the value `null` during default initialization; a **local** variable inside a method is not automatically considered initialized for reading. The compiler requires a local variable to be definitely assigned before use.

## 9. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Writing `class Student` has already created a student” | Declaring a class defines a type; creating an instance is a separate operation. |
| “`Student x;` already has an object” | That only declares a variable; no object is created by that statement. |
| “Two reference variables always mean two objects” | Two variables can point to the same object after the assignment `alias = first`. |
| “Two objects with the same fields have `==` evaluate to `true`” | `==` on references checks whether they refer to the same object; comparing logical values requires appropriate `equals` rules. |
| “`static` has one copy per object” | A `static` field belongs to the class and is shared per class-loading context. |
| “Assigning `null` destroys the object immediately” | It only removes one reference; memory reclamation is decided by the JVM. |
| “A `final` field makes all state immutable” | `final` prevents reassigning that field itself; other fields can still change. |

Do not confuse **having identical data** with **having the same object identity**. This is the foundation before diving deeper into `equals()`, `hashCode()`, object copying, encapsulation, inheritance, and polymorphism.

## 10. Knowledge Self-Check

1. Given `Student a = new Student("An", 12);`, which part is the class name, which part is the reference variable, and which part performs object creation?
2. Why does another `Student` object keep its original credit count after calling `a.earnCredits(3)`?
3. If `Student b = a;`, does calling `b.earnCredits(2)` change the result of `a.summary()`? Explain.
4. If you create `Student c = new Student("An", 12);`, what does the condition `a == c` indicate? Does having two people with the same name affect the identity comparison result?
5. When should a member be declared `static` instead of instance?

**Answer key:** (1) `Student` is the class, `a` is the variable, and `new Student(...)` creates the object; (2) the two instances hold separate `credits` fields; (3) yes, because `b` and `a` refer to the same object; (4) it checks for the same instance, does not depend on the name, and calling `new` again creates a different instance; (5) when the data or behavior belongs to the class level and does not depend on the individual state of a specific object.

A solid understanding of the relationship **a class defines the type — an object holds the state — a reference variable points to the object** will help you read and write object-oriented Java programs accurately.
