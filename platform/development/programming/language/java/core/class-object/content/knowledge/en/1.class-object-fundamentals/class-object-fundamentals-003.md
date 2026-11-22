# A Class as a Programmer-Defined Data Type in Java

## 1. Why Define Custom Data Types?

A **data type (type)** specifies what a value means and what operations a program can perform on that value. Java provides primitive types such as `int`, `boolean`, `double`, and `char`; at the same time, it allows programmers to create new **reference types** by declaring a `class`.

Suppose you need to manage a course. Using only separate variables:

```java
String name = "Java";
int capacity = 2;
int enrolled = 0;
```

makes it very hard to ensure that the three values always belong to the same course, and rules such as “the number of students does not exceed capacity” must be checked in multiple places. A `Course` class lets you group **state** (`name`, `capacity`, `enrolled`) and **behavior** (`enroll()`, `summary()`) into a unit with a clear name and rules.

```java
class Course {
    // Fields, constructors, and methods are declared here.
}
```

Once the class is declared within an appropriate access scope, `Course` is also a type name that Java can use similarly to the built-in type name `String`:

```java
Course course;         // Declare a reference variable of type Course
Course[] courses;      // Declare a reference variable to a Course array
```

The two lines above **only declare variables**; they do not create any course yet. To create an object, you typically use `new Course(...)`.

> **Key takeaway:** A `class` is the declaration of a programmer-defined data type; an **object** is an instance created from that class; a **class-typed variable** holds a reference that can point to a compatible object, or have the value `null`.

## 2. What Does a Class Define?

A typical class declaration has the form:

```java
class ClassName {
    // Fields: data/state of each object or of the class.
    // Constructors: set up the initial state.
    // Methods: behavior, operations, and rules.
}
```

| Component | Role | Example in `Course` |
| --- | --- | --- |
| Class name | Creates a **type name** to use in declarations and type checking | `Course` |
| Instance field | Stores the individual state of each object | `name`, `capacity`, `enrolled` |
| Constructor | Validates and initializes the object when `new` is called; has the same name as the class and no return type | `Course(String name, int capacity)` |
| Instance method | Defines behavior based on the object's state | `enroll()`, `summary()` |
| Access modifier | Restricts where a member is allowed to be accessed | `private` for internal data, `public` for API if needed |
| `static` member | Belongs to the class, not tied to a specific instance | For example, `static int totalCreated` |

A class may declare no fields, constructors, or methods at all. If no constructor is declared, the compiler provides a default no-argument constructor with an access level matching the class; **once you declare a constructor yourself, Java does not automatically add a no-argument constructor**. A constructor differs from a regular method: it has no return type (not even `void`), is invoked during object creation, and is not called like an instance method after the object has been created.

Curly braces define the class body; executable statements such as `System.out.println(...)` are typically placed inside an appropriate method/constructor/initializer, not arbitrarily placed directly in the class body.

## 3. Complete Example: `Course` as a Custom Data Type

Create the file **`CourseDemo.java`** with all of the following code:

```java
class Course {
    private final String name;
    private final int capacity;
    private int enrolled;

    Course(String name, int capacity) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên khóa học không hợp lệ");
        }
        if (capacity <= 0) {
            throw new IllegalArgumentException("Sức chứa phải dương");
        }

        this.name = name;
        this.capacity = capacity;
        this.enrolled = 0;
    }

    boolean enroll() {
        if (enrolled == capacity) {
            return false;
        }
        enrolled++;
        return true;
    }

    String summary() {
        return name + ": " + enrolled + "/" + capacity;
    }
}

public class CourseDemo {
    static void printCourse(Course course) {
        System.out.println(course.summary());
    }

    public static void main(String[] args) {
        Course first = new Course("Java", 2);
        Course alias = first;
        Course second = new Course("Java", 2);

        System.out.println(first.enroll());
        printCourse(alias);
        System.out.println(first == alias);
        System.out.println(first == second);
        System.out.println(second.summary());
    }
}
```

Compile and run with JDK 17 or later (from the directory containing the file):

```bash
javac CourseDemo.java
java CourseDemo
```

Expected output:

```text
true
Java: 1/2
true
false
Java: 0/2
```

Reading the example step by step:

1. `class Course` declares the `Course` type. Each course object has its own data. `name` and `capacity` are marked `final`, meaning they cannot be reassigned after the constructor finishes; `enrolled` can change.
2. The constructor guards the input preconditions: the name must have content, and the capacity must be greater than 0. `this.name = name` assigns the parameter `name` to the field `name` of **the object being initialized**. Without `this`, the two identical names could cause confusion.
3. `new Course("Java", 2)` requests creating a new object, runs the constructor, and returns a reference to that object. `first` has the **static type `Course`**, so the compiler knows which `Course` methods are allowed to be called.
4. `first.enroll()` changes the state of **the object `first` points to** and returns `true`; therefore, `alias` also sees `Java: 1/2` because `alias = first` only copies the **reference**, not the object.
5. `first == alias` is `true` because both references point to the same object. `first == second` is `false` because the two `new` calls create two different objects, even though their initial data is identical.
6. `printCourse(Course course)` shows that `Course` is used as a **method parameter type**. `summary()` returns `String`, which is also a reference type. `main` belongs to `CourseDemo` and uses `static` so that the JVM can invoke it as the program entry point.

In this example, there are two top-level classes in the same file: `Course` is not `public`, while `CourseDemo` is `public`, so the file must be named `CourseDemo.java`. When organizing real-world projects, each `public` top-level class is usually placed in its own file with the same name (for example, `Course.java` and `CourseDemo.java`); if a `package` is used, both files must be placed in the proper source structure for that package.

## 4. Declared Type and Compile-Time Checking

Read `Course course = new Course("Java", 2);` as a **type contract**, not merely as creating an object: `Course` on the left determines the API that the compiler allows to be called through the `course` variable; the `new` expression on the right creates a matching instance and returns a reference. If you only write `Course course;`, you have only **declared a variable**, not created a course yet; and that local variable must be assigned before being read.

The specific focus of this lesson is not counting how many variables are pointing to the same object (that is the variable-versus-instance distinction), but rather **where the Course type appears at API boundaries**:

- `Course current` in a parameter specifies the kind of value that the caller is allowed to pass.
- `Course create()` in the return type describes the result that the method promises to return.
- `Course[]` or `List<Course>` expresses the element type at compile time.
- `Object raw = new Course("Java", 2);` is a valid assignment, but `raw.enroll()` does **not** compile: the API of the declared type `Object` does not have an `enroll` method. The actual object is still a Course.

`null` is a reference value that points to no object, not an empty Course. The array `new Course[3]` creates **an array** with three initially null elements, without instantiating three Courses. These two notes help avoid confusing the *element type* with the *element objects*.

When you need to distinguish precisely between `class Person`, `Person p`, and `new Person()`, use the dedicated trace for variables/instances; in the current lesson, try writing a method that accepts `Course` and check which calls the compiler accepts or rejects.

## 5. Where Can a Class Serve as a Type?

A class can be used in almost any position where a reference type is needed:

| Context | Usage | Meaning |
| --- | --- | --- |
| Local variable | `Course current = new Course("Java", 2);` | Reference variable accepts only values compatible with `Course` |
| Parameter | `void print(Course current)` | Specifies the kind of object the method accepts |
| Return type | `Course createCourse()` | The method promises to return a reference of a compatible type |
| Field | `private Course favorite;` | Another object can store a reference to a `Course` |
| Array | `Course[] courses = new Course[2];` | Each element has reference type `Course`, initially `null` |
| Generic type parameter | `List<Course> courses` | A list whose `Course` element type is checked at compile time |
| Type casting/type checking | `value instanceof Course` | Checks whether the reference points to a compatible instance |

The rows in the table are **illustrative code snippets**, not a standalone runnable program. For `List<Course>`, you need to import `java.util.List` when compiling in a real program.

Java uses a **nominal typing** system. Two classes whose fields/methods look alike do not automatically become the same type because of that. For example, `Course` and `Workshop` cannot be assigned to each other merely because both have `summary()`; there must be a valid type relationship, such as inheriting from a common class or implementing the same interface, for appropriate assignments to be permitted. This helps the compiler catch misuse early.

Example of **invalid code that intentionally fails to compile**:

```java
Course course = new Course("Java", 2);
course = 10; // COMPILE ERROR: int cannot be assigned to Course
```

The variable's type name also limits the members visible at compile time. With `Object value = new Course("Java", 2);`, the actual object is a `Course`, yet you cannot call `value.enroll()` directly through an `Object`-typed variable: the `enroll()` method is not declared in `Object`. Learners will encounter upcasting, downcasting, and polymorphism in the inheritance section; those topics build upon this type-checking principle.

## 6. Designing Classes So Data Types Are Meaningful

A programmer-defined type is useful when it **expresses a concrete concept** and **enforces the rules of that concept**.

### Encapsulating Data and Behavior

If you write `public int enrolled;`, external code can directly assign `course.enrolled = -7` and break the rule. In the example, the fields are `private`; calling `enroll()` modifies the data through the `enrolled == capacity` check. This is an important reason to combine state and behavior in the same class, rather than merely creating a “bag of variables”.

`private` restricts access from outside the class; `public` makes a member accessible wherever Java allows it; omitting a modifier on a top-level declaration or a regular member uses package-private scope. There is also `protected` in inheritance design. Access scope does not change the fact that `Course` is a type: it determines **where** it can be named, instantiated, or have that member used.

### Invariants and Mutability

An invariant of `Course` is `capacity > 0` and `0 <= enrolled <= capacity`. The constructor establishes a valid state; the `enroll()` method preserves the invariant across every call. `final` on the `name`/`capacity` fields prevents reassigning those fields after initialization; `final` alone **does not automatically make every object immutable**. If a `final` field references a mutable object, the internal state of the referenced object can still change.

If you want completely immutable data, you need a design with no way to modify observable state; a `record` can be convenient for simple data models, though `record` has its own rules and does not replace every regular class.

### Instance and `static` Members

`enroll()` and `enrolled` are **instance** members: state is tied to each individual course. A field or method declared `static` belongs to **the class**. For example, `Integer.parseInt("42")` is called via the class name `Integer`; there is no need to create an `Integer` instance to perform that operation. In the design of `Course`, `static` can be used for a shared constant or a utility method that does not need `this`.

A `static` method has no `this` and cannot directly access instance fields without a reference to a specific object. Conversely, the fact that multiple instances can all use a method does not make that method `static`.

### Naming and Responsibilities

Name classes after domain nouns or concepts (`Course`, `Invoice`, `Coordinate`), following the `UpperCamelCase` convention; methods usually follow verbs or information requests (`enroll`, `summary`). Prefer classes with clear responsibilities; avoid lumping multiple independent concepts into one large class. A good data type helps readers understand the meaning of a `Course` parameter much more clearly than a group of `String`, `int`, and `int` variables without context.

## 7. From Source Code to the Type Used at Runtime

When `javac CourseDemo.java` compiles the example, it checks syntax, types, access permissions, and calls within the compiled code scope. The normal result is two files, `Course.class` and `CourseDemo.class`. The JVM loads the required class definitions at runtime; the program starts from `main(String[] args)` in `CourseDemo`.

Distinguish three things with similar-looking names:

- `Course`: the **type/class** declared by the programmer.
- `new Course("Java", 2)`: an **instance object** created at runtime.
- `Course.class`: an expression that produces a reference to a metadata object of type `Class<Course>` describing the `Course` class; that metadata itself is **not a `Course` instance**.

Having a `Course.class` file does not mean the JVM has created a `Course` instance. A class can be used for a parameter type, a field, or metadata processing without any object being created yet.

## 8. Common Mistakes and How to Recognize Them

| Misconception | Why It Is Wrong / How to Handle It |
| --- | --- |
| “Declaring `Course course;` means you already have a course” | This is a reference variable declaration; a valid value is required before reading the variable, typically from `new Course(...)`. |
| “Two variables of type `Course` are two objects” | `Course a = existing; Course b = a;` can simply both point to the same object. |
| “If two objects have the same data, `==` is `true`” | `==` checks references; you must design `equals()` if domain-based equality is needed. |
| “Calling a method on `null` is still safe” | `null` has no target object for the call; a `NullPointerException` can occur. |
| “Making fields `public` is the simplest approach” | External code can break invariants; use access visibility and validating methods when state needs protection. |
| “`final Course x` makes the object immutable” | `final` on a reference variable only prevents **reassigning the variable**; you can still call methods that mutate the referenced object. |
| “All fields and methods are accessed through the class name” | Only `static` members belong to the class; instance members require a target object. |
| “All constructors are generated automatically by Java” | A default no-argument constructor is only generated when the class declares no constructors at all. |
| “You can name a Java file whatever you want” | A `public` top-level class `CourseDemo` must be in the file `CourseDemo.java`. |
| “`new Course[3]` has created three Courses” | It only creates an array of three `null` references; each `Course` must be created when needed. |

## 9. Self-Check Questions

1. From `class Course` in the example, identify the type name, the three fields, one constructor, and two instance methods. Why does `enroll()` need to access the object's state?
2. If you add `Course third = first; third.enroll();` right after the five print statements in the example, what will `first.summary()` return? **Answer:** `Java: 2/2`, because `third` and `first` reference the same object; on the second `enroll()` call there is one spot left.
3. If you continue by calling `first.enroll()` one more time, what does the method return and what is `enrolled` equal to? **Answer:** it returns `false`, and `enrolled` remains `2`; the invariant is preserved.
4. Why does `Course c = null;` compile, yet `c.summary()` throws an error at runtime? **Answer:** the static type is valid, but there is no actual object to receive the call.
5. Explain the difference between `Course`, `Course course`, `new Course(...)`, and `Course.class` in one sentence for each expression.

**Remember:** Defining a `class` is how Java lets you create a **reference type whose name and meaning are decided by the programmer**. Each instance carries its own state; a class-typed variable holds a reference; constructors and methods help the class control how objects are created and used. Through compile-time type checking and encapsulating state together with behavior, business concepts become program components that are clear, reusable, and harder to misuse.
