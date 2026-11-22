# Classes Describe Types and Objects Are Concrete Instances — Java 17+

## 1. How Is a Class Different from an Object?

In Java, a **class** defines a **data type**: the type name, its attributes (*fields*), its behaviors (*methods*), and how it is initialized (*constructors*). An **object** is a **concrete instance** of that type, created when the program runs.

~~~java
class Student {                          // Defines a class.
    String name;                         // Instance field.
    int score;

    Student(String name, int score) {    // Constructor.
        this.name = name;
        this.score = score;
    }

    void printInfo() {                   // Instance method.
        System.out.println(name + ":" + score);
    }
}
~~~

~~~java
Student an = new Student("An", 70);       // One object.
Student binh = new Student("Binh", 85);   // A second object.
an.printInfo();
binh.printInfo();
~~~

**Exact expected stdout** (when placing the two calls in `main`):

~~~text
An:70
Binh:85
~~~

`Student` is the **shared type** describing characteristics and operations; `an` and `binh` are **two variables referencing two different Student objects**. They share the same class definition but have their own `name` and `score` data.

## 2. Distinguishing class, object, reference, and constructor

| Concept | Example | Role |
|---|---|---|
| Class | `class Student { ... }` | Declares a type and its members |
| Object/instance | An object created by `new Student(...)` | An instance with its own state |
| Reference variable | `Student an` | A variable of type `Student`, holding a reference value to an object (or `null`) |
| Constructor | `Student(String name, int score)` | Initializes an object when invoked via `new` |
| Instance field | `name`, `score` | Data belonging to each individual instance |
| Instance method | `printInfo()` | Behavior invoked on an instance |
| Static member | `static int created` | A member associated with the class, without a separate copy per object |

The statement:

~~~java
Student student = new Student("Lan", 90);
~~~

has two sides:

1. `Student student` declares a **reference variable** named `student`.
2. `new Student("Lan", 90)` creates an **object**, invokes the constructor, and provides the reference value to store in `student`.

Simply writing `Student student;` **does not create an object**, and because it is an unassigned local variable, you cannot read it before assigning it. If you explicitly write `Student student = null;`, the variable has been assigned, but **does not point to any object yet**.

## 3. Each Object Has Independent Instance State

~~~java
Student an = new Student("An", 70);
Student binh = new Student("Binh", 85);

an.score = 75; // Illustrates when the field is accessible.
System.out.println(an.score);
System.out.println(binh.score);
~~~

**Exact expected stdout:**

~~~text
75
85
~~~

Changing `an`'s `score` field does not change `binh`'s `score` field, because the two objects were created by **two separate `new` calls**.

A reference model:

~~~text
Student an   ──────> Object #1: {name="An",   score=75}
Student binh ──────> Object #2: {name="Binh", score=85}

              Same Student type, different objects and state.
~~~

The names `Object #1` and `Object #2` are only annotations; they are not identifiers that Java automatically prints. Java does not guarantee that objects reside at specific memory locations that a program is allowed to rely on.

In real-world code, you usually declare fields as `private` and provide accessor/mutator methods with validation, instead of allowing arbitrary assignments to `student.score`.

## 4. Two Variables Can Point to the Same Object

~~~java
Student an = new Student("An", 70);
Student alias = an;                 // Does not call new, does not create a new Student.
alias.score = 80;
System.out.println(an.score);
System.out.println(an == alias);
~~~

**Exact expected stdout:**

~~~text
80
true
~~~

`alias = an` **copies the reference value**. Since `an` and `alias` point to the same object, modifying state through either variable is visible from the other.

If afterwards:

~~~java
alias = new Student("Chi", 90);
System.out.println(an == alias);
~~~

**Exact expected stdout (continued):**

~~~text
false
~~~

`alias` switches to the new object; `an` still holds a reference to the old object. **Reassigning a reference variable** does not automatically change another reference variable.

For two objects created separately with `new`, the `==` operator compares whether the references point to the **same object**. It does not automatically compare every field inside. If you need to check equivalent business values, you can design appropriate `equals`/`hashCode` methods in an advanced lesson.


## 5. Constructors Give Objects an Initial State

When calling `new Student("Lan", 90)`, Java selects the matching constructor to initialize **that new instance**. A constructor has the same name as the class, declares no return type, and typically validates input before completing. For example:

~~~java
class Student {
    private final String name;
    private int score;

    Student(String name, int score) {
        if (name == null || name.isBlank() || score < 0 || score > 100) {
            throw new IllegalArgumentException("invalid student");
        }
        this.name = name.strip();
        this.score = score;
    }
}
~~~

`this.name` is the field of the object being created, while `name` is the parameter. `final` prevents reassigning the `name` field after initialization, which does not make the entire object immutable. If the constructor throws an exception, the `new` expression does not return a reference to the caller. Rules regarding default constructors, overloading, `this(...)`, and `super(...)` are practiced in the lesson **Constructors Set Initial Values**.

## 6. Objects Have Individual Behavior, Classes Have Shared Members

~~~java
// For an instance method:
an.increase(5); // Mutates the state of the object an.

// For a static method defined by the class:
Student.getCreatedCount(); // Reads the counter attached to the Student class.
~~~

An **instance** method runs on the object receiving the call; inside its body, `this` can be used to refer to that object. A **static** member is attached to the class, does not have a separate copy on each object, and a static method does not have `this`. The complete example below illustrates both, while the lesson **Distinguishing Static Members from Instance Members** explains scope and the risks of shared state.

## 7. Complete Java 17+ Program

Save the exact file **`ClassObjectBasicsDemo.java`**:

~~~java
public final class ClassObjectBasicsDemo {
    private ClassObjectBasicsDemo() {}

    // Class describing the Student object type.
    static final class Student {
        private static int createdCount;

        private final String name;
        private int score;

        Student(String name, int score) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is blank");
            }
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException("score out of range");
            }
            this.name = name.strip();
            this.score = score;
            createdCount++;
        }

        String getName() {
            return name;
        }

        int getScore() {
            return score;
        }

        void increase(int points) {
            if (points < 0 || points > 100 - score) {
                throw new IllegalArgumentException("invalid increase");
            }
            score += points;
        }

        String describe() {
            return name + ":" + score;
        }

        static int getCreatedCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        System.out.println("created initially=" + Student.getCreatedCount());

        Student an = new Student(" An ", 70);
        Student binh = new Student("Binh", 85);
        System.out.println("created after two=" + Student.getCreatedCount());

        System.out.println("an=" + an.describe());
        System.out.println("binh=" + binh.describe());
        System.out.println("an name=" + an.getName());

        an.increase(5);
        System.out.println("an after increase=" + an.getScore());
        System.out.println("binh unchanged=" + binh.getScore());
        System.out.println("two objects same=" + (an == binh));

        Student alias = an;
        alias.increase(5);
        System.out.println("alias same=" + (an == alias));
        System.out.println("an via alias=" + an.describe());
        System.out.println("created after alias=" + Student.getCreatedCount());

        alias = new Student("Chi", 90);
        System.out.println("alias replaced same=" + (an == alias));
        System.out.println("an still=" + an.describe());
        System.out.println("alias now=" + alias.describe());
        System.out.println("created after third=" + Student.getCreatedCount());

        Student missing = null;
        System.out.println("missing null=" + (missing == null));

        try {
            new Student("", 10);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid name=" + ex.getMessage());
        }
        try {
            an.increase(30);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid increase=" + ex.getMessage());
        }
        System.out.println("created at end=" + Student.getCreatedCount());
    }
}
~~~

**Requirements:** JDK 17 or later; open a terminal in the directory containing the file. No Maven, Gradle, external libraries, or preview features needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ClassObjectBasicsDemo.java
java -cp . ClassObjectBasicsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ClassObjectBasicsDemo.java
java -cp . ClassObjectBasicsDemo
~~~

### Exact expected stdout

~~~text
created initially=0
created after two=2
an=An:70
binh=Binh:85
an name=An
an after increase=75
binh unchanged=85
two objects same=false
alias same=true
an via alias=An:80
created after alias=2
alias replaced same=false
an still=An:80
alias now=Chi:90
created after third=3
missing null=true
invalid name=name is blank
invalid increase=invalid increase
created at end=3
~~~

**Overflow note:** Because `score` is always within `0..100`, comparing `points > 100 - score` rejects even very large arguments such as `Integer.MAX_VALUE`; checking `score + points > 100` could fail because `int` addition overflows before the comparison.

**Verification:** the first two `new` calls create two objects so `createdCount == 2`. `alias = an` does not create an object; calling `alias.increase(5)` modifies the exact object `an` points to. After `alias = new Student("Chi", 90)`, there is a third object, while `an` keeps its state of 80. The constructor rejects an empty name, so the failed creation does not increment the counter in this code.

## 8. Common Mistakes

| Mistake | Why is it wrong? | Correct understanding |
|---|---|---|
| Thinking `class Student` automatically creates a concrete student | It only defines the type | You need `new Student(...)` to create an instance |
| Thinking `Student s;` creates an object | It only declares a local reference variable | Assign an object reference before using it |
| Thinking `Student s = null;` is an empty object | `null` means pointing to no object | Do not call `s.method()` when null |
| Thinking `Student b = a;` creates a copy | It only copies the reference | `a` and `b` point to the same object |
| Thinking changing `alias` to `new` changes `an` as well | Two reference variables are assigned independently | Reassigning `alias` does not reassign `an` |
| Thinking objects share all instance fields | Instances have separate state | Only `static` members are shared at the class level |
| Writing constructor `void Student(...)` | That is a method, not a constructor | A constructor has no return type |
| Accessing a `private` field from outside the class | Violates access control | Use an appropriate method |
| Using `==` to compare the contents of all fields | `==` on object references compares identity | Use an `equals` policy when needed |
| Printing an object directly and expecting a stable format | The default `toString` does not describe business values | Write `describe`/`toString` as needed |

## 9. Exercises with Answers

**A — How many objects are created?**

~~~java
Student first = new Student("Lan", 50);
Student second = first;
Student third = new Student("Mai", 60);
~~~

**Answer:** **2 Student objects** because there are two `new Student` calls. `second` is just an alias of `first`.

**B — What happens after an update through an alias?**

~~~java
Student first = new Student("Lan", 50);
Student alias = first;
alias.increase(10);
System.out.println(first.getScore());
~~~

**Answer:** `60`, because both variables point to the same object.

**C — Are two objects with the same data guaranteed to have `==` true?**

~~~java
Student a = new Student("An", 70);
Student b = new Student("An", 70);
System.out.println(a == b);
~~~

**Answer:** `false`. Two `new` calls create two separate objects, even if their fields have identical values.

**D — When should `static` be used?** When data/behavior belongs to the **class**, such as the counter of successfully created objects in the example. For each individual student's data, use instance fields.

**E — Which fields belong to each object?** In `Student` from the program, `name` and `score` are instance fields; `createdCount` is a static field.

## 10. Checklist and Conclusion

- [ ] Understand that a **class defines a type**, and an object is a concrete instance.
- [ ] Distinguish declaring a reference variable from creating an object with `new`.
- [ ] Know that constructors establish initial state.
- [ ] Recognize that each object has its own set of instance fields.
- [ ] Understand that `b = a` shares the object, rather than automatically copying it.
- [ ] Know that `==` compares object reference identity.
- [ ] Distinguish instance methods and `static` members.
- [ ] Recognize `null` and avoid dereferencing when there is no object.
- [ ] Know how to use `private` and methods to manage state.
- [ ] Compile and run `ClassObjectBasicsDemo.java` with JDK 17+, and verify exact stdout.

**Conclusion:** **A class is the definition of type and behavior; an object is a concrete instance created at runtime**. Multiple objects can share the same type while holding separate state; multiple reference variables can also point to **one** object. That is the foundation for understanding constructors, instance fields, instance methods, and `static` in Java.