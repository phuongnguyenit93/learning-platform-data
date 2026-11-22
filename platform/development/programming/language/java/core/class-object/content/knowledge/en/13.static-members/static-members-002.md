# `static` Fields and Shared Data Across Instances in Java

In Java, each time an object is created with `new`, it typically creates an **instance** with its own state. However, not every field declared in a class belongs to each individual object. If a field is declared with the **`static`** keyword, that field belongs to the **class at runtime**, and instances of the same runtime class can read or modify the **same logical state area** through that field.

Example:

~~~java
class Student {
    String name;                // Instance field: each Student has its own name.
    static int studentCount;    // Static field: shared within the Student class.

    Student(String name) {
        this.name = name;
        studentCount++;
    }
}
~~~

If two Student instances are created, each object's `name` is independent, while `studentCount` is **one shared field** for the `Student` class. Modifying a static field does not mean modifying every instance field at the same time. This is a useful mechanism for managing **class-level configuration, the number of instances created under a specific definition, constants, caches, or registries** — but it is also a source of bugs when sharing uncontrolled mutable state.

This article belongs to the **Static Members** section of Java Core — Class & Object, using Java 17+, explaining step by step the syntax, semantics, initialization timing, behavior across multiple objects, inheritance, testing, lifecycle management, and concurrency issues.

## 1. Learning Outcomes

After this article, you should be able to:

1. Distinguish between **instance fields** and **static fields** regarding where logical state is stored, sharing scope, and how they are accessed.
2. Predict the outcome when multiple objects read/write a static field.
3. Know why **`ClassName.staticField`** is usually clearer in meaning than `object.staticField`.
4. Understand that a static field can be used **before an instance is created**, but using it can initialize the class.
5. Understand default values, **static initializers**, class initialization order, and how they differ from instance initialization.
6. Distinguish a **static field** from a **static local variable** — Java does not have local static syntax like some other languages.
7. Explain when to use **`static final`**, and why a `static final List` does not automatically become immutable.
8. Track **static fields under inheritance**, field hiding, and static method hiding.
9. Recognize the risks of **shared mutable state**, lack of thread safety, state leakage between tests, and memory retention.
10. Choose an appropriate design option: instance field, static constant, singleton, dependency injection, or class-level service.

Complete programs include file names and `javac`/`java` commands; non-standalone examples are explicitly noted.

## 2. Visual Diagram: Shared and Separate Parts

Suppose:

~~~java
class Counter {
    int value;
    static int totalCreated;

    Counter() {
        totalCreated++;
    }
}
~~~

After:

~~~java
Counter a = new Counter();
Counter b = new Counter();
a.value = 10;
b.value = 20;
~~~

There are two Counter instances, each with its own `value` field; however, both relate to **the same `Counter.totalCreated` field**:

~~~text
             Class Counter (runtime)
         +---------------------------+
         | static totalCreated = 2   |
         +---------------------------+
               ^                ^
               |                |
         +-----------+    +-----------+
a ------>| Counter #1|    | Counter #2|<------ b
         | value=10  |    | value=20  |
         +-----------+    +-----------+
~~~

The arrows from the objects up to the class are a **semantic illustration**, not a claim that the JVM actually stores the static field right next to some object block in RAM. The key points:

- Each normal successful `new Counter()` creates a new Counter instance.
- Each Counter instance has **its own `value` field**.
- `totalCreated` is attached to the `Counter` runtime class, so it is not duplicated per instance.
- Variables `a` and `b` are references to two different objects; creating the alias `Counter c = a;` does not run the constructor and does not increment the counter.

### Quick Reference Table

| Criterion | Instance field | Static field |
| --- | --- | --- |
| Declaration | `int score;` | `static int total;` |
| Attached to | A specific object | The corresponding runtime class |
| Does each `new` create a separate field copy? | Yes, for the new instance | Does not create a new static field copy for each object |
| Common way to access | `student.score` or `this.score` | `Student.total` |
| Usable when no instance exists yet? | Requires an instance for normal reading/writing | Can be used via the class if access permissions allow |
| Default value | According to the field type, during instance creation | According to the field type, during class preparation/initialization |
| Can a change affect other objects? | When sharing the same object | Yes: all code using the same runtime class sees the same state per memory model rules |
| Thread-safe by default? | No | No |

## 3. First Runnable Example: Two Objects, One Static Counter

Save the file **`StaticFieldBasicsDemo.java`**:

~~~java
public class StaticFieldBasicsDemo {
    static final class Student {
        private static int createdCount = 0;

        private final String name;
        private int lessons;

        Student(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            this.name = name;
            createdCount++;
        }

        void completeLesson() {
            lessons++;
        }

        String describe() {
            return name + ": " + lessons;
        }

        static int createdCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        System.out.println("before=" + Student.createdCount());

        Student mai = new Student("Mai");
        Student an = new Student("An");
        mai.completeLesson();
        mai.completeLesson();
        an.completeLesson();

        System.out.println(mai.describe());
        System.out.println(an.describe());
        System.out.println("after=" + Student.createdCount());

        Student alias = mai;
        alias.completeLesson();

        System.out.println("through alias=" + mai.describe());
        System.out.println("after alias=" + Student.createdCount());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StaticFieldBasicsDemo.java
java StaticFieldBasicsDemo
~~~

Stdout:

~~~text
before=0
Mai: 2
An: 1
after=2
through alias=Mai: 3
after alias=2
~~~

Explanation:

1. When calling `Student.createdCount()`, the class needs to be ready for use; the static field is initialized to 0, **without needing to create a Student instance first**.
2. `new Student("Mai")` and `new Student("An")` execute the constructor twice; `createdCount` increases to 2.
3. `lessons` is an instance field: Mai has 2 lessons, An has 1 lesson.
4. `Student alias = mai;` only copies the reference to the **same Mai object**, without `new`.
5. `alias.completeLesson()` changes `lessons` of the Mai object to 3, but does not run the constructor, so the static `createdCount` remains 2.

In this example, `Student` is a **static nested class** solely to bundle the program in one file. The `static` keyword on the nested class and the `static` keyword on the `createdCount` field have **two different roles** and should not be conflated.

## 4. How to Declare and Access a Static Field

Syntax:

~~~java
class Configuration {
    static int timeoutSeconds = 30;
}
~~~

Accessing by class name:

~~~java
int timeout = Configuration.timeoutSeconds;
Configuration.timeoutSeconds = 45;
~~~

These snippets are **illustrative code** placed in a valid method/context. `Configuration.timeoutSeconds` clearly expresses that the field belongs to the `Configuration` class.

### Can an Instance Reference Be Used to Access a Static Field?

For a static field with appropriate access permissions, Java generally **allows** it:

~~~java
Configuration config = new Configuration();
int timeout = config.timeoutSeconds;
~~~

However, this style **should not be used**: it leads readers to assume `timeoutSeconds` belongs specifically to `config`. The recommended style:

~~~java
int timeout = Configuration.timeoutSeconds;
~~~

There is also a subtle point: in the `expression.staticField` syntax, the qualifier expression may be evaluated for side effects, but **the object value of the qualifier is not where the static field is stored**. Writing `object.staticField` does not create an extra copy of the field.

### Do Not Access Static Fields Through `this` as a Routine Design

Inside an instance method, a static field can be read via its simple name when permitted, but prefer the class name:

~~~java
class Session {
    private static int maxSessions = 100;

    boolean hasCapacity(int openSessions) {
        return openSessions < Session.maxSessions;
    }
}
~~~

`Session.maxSessions` describes class-level state; `this.maxSessions`, although it may compile in an appropriate instance context, obscures the **shared state** meaning.

## 5. Static Fields Exist When There Is No Object Instance

A static member can be used by class name:

~~~java
System.out.println(Math.PI);
System.out.println(Integer.MAX_VALUE);
~~~

There is no need to create `new Math()` or `new Integer()` to get the static constants above.

A custom class:

~~~java
class AppSettings {
    static String environment = "development";
}

class Bootstrap {
    public static void main(String[] args) {
        System.out.println(AppSettings.environment);
    }
}
~~~

This two-class snippet can be placed in a single appropriate file because no public top-level class is declared. `AppSettings.environment` has a value without needing any `AppSettings` instance.

**Do not draw the converse conclusion:** "a static field can exist when no instance exists yet" does not mean every static class is already initialized as soon as the JVM runs. Java initializes classes according to **class initialization** rules; when it is triggered depends on code behavior.

## 6. A Static Field Has a Default Value Before Static Initializers

Each static field has a default value based on its type, for example:

| Field type | Default value |
| --- | --- |
| `int` / `long` and integral types | 0 according to type |
| `float` / `double` | 0.0 according to type |
| `boolean` | `false` |
| `char` | zero character `'\\u0000'` |
| Reference types such as `String`, `List<?>`, arrays | `null` |

Then, static field initializers and static initializer blocks are executed in the **textual order** applied within the class, according to Java rules.

~~~java
class Example {
    static int count = 5;
    static String name = "Java";

    static {
        count += 2;
    }
}
~~~

When the `Example` class is initialized normally, `count` after the steps above is 7 and `name` is `"Java"`.

### Same Type, Different Timing

- Static fields have a preparation/initialization process tied to the **runtime class**.
- Instance fields are initialized for **each new object instance**.

This difference helps explain why static initialization does not run again merely because another object of the same already-initialized runtime class is created.

## 7. Runnable Example: Static Initializer vs. Instance Constructor

Save **`StaticInitializationDemo.java`**:

~~~java
public class StaticInitializationDemo {
    static class Gadget {
        static int nextId = 1;

        static {
            System.out.println("Gadget static block");
        }

        private final int id;

        {
            System.out.println("Gadget instance block");
        }

        Gadget() {
            id = nextId++;
            System.out.println("Gadget constructor " + id);
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) {
        System.out.println("main start");

        Gadget first = new Gadget();
        Gadget second = new Gadget();

        System.out.println("first=" + first.id());
        System.out.println("second=" + second.id());
        System.out.println("next=" + Gadget.nextId);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializationDemo.java
java StaticInitializationDemo
~~~

Stdout:

~~~text
main start
Gadget static block
Gadget instance block
Gadget constructor 1
Gadget instance block
Gadget constructor 2
first=1
second=2
next=3
~~~

Sequence of events:

1. `main start` appears before `Gadget` is used in a way that triggers class initialization.
2. On the first `new Gadget()`, the static field `nextId` is initialized to 1, and then the static block prints its log.
3. The instance initializer block runs for Gadget #1, and the constructor takes ID 1 and increments the static `nextId` to 2.
4. The second `new Gadget()` **does not run the static block again**, but the instance block and constructor still run for the new object; the ID is 2.
5. After two creations, `Gadget.nextId == 3`.

If the JVM or tooling has other class loading mechanisms, the time a class is **loaded** does not necessarily coincide with the time the class is **initialized**. The observation above only describes the guaranteed sequence for this learning program.

## 8. When Is a Class Initialized?

According to Java/JVM rules, using a class in certain ways can trigger **class initialization**, such as:

- Creating an instance with `new`.
- Calling a static method declared by the class.
- Reading/writing a static field declared by the class, except for special constant variable cases.
- Other cases such as reflective initialization via APIs and the corresponding JVM rules.

Do not think a class is **only** initialized when a `new` statement appears. In the example at the start of the article, `Student.createdCount()` can trigger class initialization before a Student instance exists.

### Referencing a Class Name Does Not Always Run the Static Block

Example of a **compile-time constant**:

~~~java
class Constants {
    static final int LIMIT = 10;

    static {
        System.out.println("Constants initialized");
    }
}
~~~

A caller reading `Constants.LIMIT` in a normal context may not trigger class initialization because `LIMIT` is a **constant variable** (`static final int` with a constant expression initializer). The compiler can use the constant value itself in the compiled code.

Conversely, a static field that is **not a constant variable**, including a `static final` field assigned through a method call, generally requires class initialization when read directly.

This is an important nuance: **`static final` does not always have the same initialization behavior as an ordinary static field**.

## 9. Runnable Example: Compile-Time Constants and Static Initialization

Save the file **`StaticConstantInitializationDemo.java`**:

~~~java
public class StaticConstantInitializationDemo {
    static final class Constants {
        static final int LIMIT = 10;
        static final Integer BOXED_LIMIT = Integer.valueOf(20);

        static {
            System.out.println("Constants initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("limit=" + Constants.LIMIT);
        System.out.println("boxed=" + Constants.BOXED_LIMIT);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticConstantInitializationDemo.java
java StaticConstantInitializationDemo
~~~

Stdout:

~~~text
limit=10
Constants initialized
boxed=20
~~~

On the first line, `LIMIT` is a constant variable of type `int` whose initializer is a compile-time constant expression, so using it here does not trigger initialization of `Constants`.

On the second line, `BOXED_LIMIT` is an `Integer` object reference and is created from a method call, **not a constant variable** under Java rules; accessing it triggers class initialization, causing the static block to print its log before printing `boxed=20`.

**Do not assume that every `static final` has its value inserted into the caller by the compiler.** You need to distinguish the field type and the initializer form.

## 10. Static Fields Are Initialized in Textual Order

A static initializer or field initializer can read a static field declared after it along expression paths permitted by Java. At the moment of reading, that field may still be at its **default value**, producing unexpected results.

Save **`StaticOrderDemo.java`**:

~~~java
public class StaticOrderDemo {
    static class Example {
        static int observed = readLater();
        static int later = 9;

        static int readLater() {
            return later;
        }

        static {
            System.out.println("observed=" + observed);
            System.out.println("later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("final=" + Example.later);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticOrderDemo.java
java StaticOrderDemo
~~~

Stdout:

~~~text
observed=0
later=9
final=9
~~~

Explanation:

1. Static fields have default values, so `later` is initially 0.
2. `observed = readLater()` runs before the initializer `later = 9`.
3. `readLater()` reads `later` while it is still 0, so `observed = 0`.
4. Next, `later = 9`.
5. The static block prints `observed=0`, `later=9`.
6. `main` reads `Example.later` after initialization, so it prints 9.

**Do not design business logic that depends on reading default values during static initialization.** Complex initialization order often reduces clarity and can create hard-to-find bugs when multiple classes cross-reference each other.

## 11. A Static Field Can Hold a Primitive or an Object Reference

`static` does not prescribe the type of the field:

~~~java
class SharedData {
    static int counter;                       // Primitive int.
    static String title = "Java";             // Reference to String.
    static java.util.List<String> names =
            new java.util.ArrayList<>();      // Reference to an ArrayList.
}
~~~

This is an illustrative class.

- `counter` is a primitive value stored in the static field.
- `title` is a reference to a String object; String is immutable.
- `names` is a reference to a mutable List object. When one method adds an element, other methods reading the same list will see the change according to the applicable visibility rules.

**Do not confuse:** "Shared static field" does not mean Java automatically creates a shared object for every access. Each static field holds only **one value** at a time for its corresponding runtime class; that value can be a primitive, null, or a reference to an object.

## 12. Shared Data Across Instances: Small Registry Example

Save **`SharedRegistryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SharedRegistryDemo {
    static final class Employee {
        private static final List<String> NAMES = new ArrayList<>();

        private final String name;

        Employee(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }

            this.name = name;
            NAMES.add(name);
        }

        String name() {
            return name;
        }

        static List<String> namesSnapshot() {
            return List.copyOf(NAMES);
        }
    }

    public static void main(String[] args) {
        Employee first = new Employee("Mai");
        Employee second = new Employee("An");

        System.out.println("first=" + first.name());
        System.out.println("second=" + second.name());
        System.out.println("all=" + Employee.namesSnapshot());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedRegistryDemo.java
java SharedRegistryDemo
~~~

Stdout:

~~~text
first=Mai
second=An
all=[Mai, An]
~~~

`name` is a separate instance field for each Employee. `NAMES` is a **static reference** to a shared ArrayList object of `Employee`. Each constructor writes to the same List object.

`private static final` does not automatically make the ArrayList immutable:

- `private`: outside the class, the field cannot be accessed directly under normal rules.
- `static`: the field is attached to the class.
- `final`: the field reference cannot be reassigned after valid initialization.
- The `ArrayList` inside remains mutable and can accept `add`.

In the example, `namesSnapshot()` returns an unmodifiable list using `List.copyOf` to prevent callers from modifying the internal list directly. However, **a real user/name registry** may require uniqueness, cleanup, synchronization, and authorization; the example only illustrates the sharing capability.

## 13. Appropriate Cases for Using Static Fields

| Need | Is static appropriate? | Notes |
| --- | --- | --- |
| A class constant `MAX_ITEMS` | Usually yes | Use `static final` with an immutable value |
| Instance creation counter in a demo | Yes, when clearly defined | A constructor can fail; subclasses can affect counting |
| Application-wide fixed configuration | Possibly | Avoid mutable static globals if configuration is needed per request/test/tenant |
| Class-level logger | Usually yes | For example, `private static final Logger LOG` depending on the framework |
| Stateless helper | Use static methods, not necessarily static fields | `Math.max` is an example of a static method |
| Process-wide cache | Possibly, but with caution | Thread-safety, capacity limits, eviction, lifecycle |
| A variable describing each customer | No | That is instance data |
| Current login session information | Usually should not be a global static field | Easily mixes up users/requests/threads |
| Data that varies by tenant | Should not be shared globally unconditionally | Use an appropriately scoped context/service |
| Multi-threaded counter | Possibly, if using synchronization tools | `static int count++` is not atomic |

**Main criterion:** Is this data truly a **shared fact for the class/runtime scope**, or does it belong to a specific **object, request, session, tenant, or service instance**?

## 14. Typical Mistake: Making Per-User State Static

Consider a flawed class:

~~~java
class UserSession {
    static String currentUser;

    UserSession(String user) {
        currentUser = user;
    }
}
~~~

If you create:

~~~java
UserSession alice = new UserSession("Alice");
UserSession bob = new UserSession("Bob");
~~~

then the field `UserSession.currentUser` ends up as `"Bob"`. The `alice` object does not own its own `currentUser` copy. If a screen displays Alice's information via the static field, it may read `"Bob"` instead.

### Runnable Program Demonstrating the Bug

Save the file **`StaticPerUserBugDemo.java`**:

~~~java
public class StaticPerUserBugDemo {
    static final class BadSession {
        private static String currentUser;

        BadSession(String user) {
            currentUser = user;
        }

        String display() {
            return currentUser;
        }
    }

    static final class GoodSession {
        private final String currentUser;

        GoodSession(String user) {
            this.currentUser = user;
        }

        String display() {
            return currentUser;
        }
    }

    public static void main(String[] args) {
        BadSession badAlice = new BadSession("Alice");
        BadSession badBob = new BadSession("Bob");

        System.out.println("bad Alice=" + badAlice.display());
        System.out.println("bad Bob=" + badBob.display());

        GoodSession goodAlice = new GoodSession("Alice");
        GoodSession goodBob = new GoodSession("Bob");

        System.out.println("good Alice=" + goodAlice.display());
        System.out.println("good Bob=" + goodBob.display());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticPerUserBugDemo.java
java StaticPerUserBugDemo
~~~

Stdout:

~~~text
bad Alice=Bob
bad Bob=Bob
good Alice=Alice
good Bob=Bob
~~~

The answer is not that "the static field copies data incorrectly on its own", but that **two session objects write to the same class-level field**. With `GoodSession`, the field is instance state, so each session keeps its own information.

**Lesson:** Using `static` for current user data is a global-state bug that is especially dangerous in multi-user/multi-request systems. This information must be attached to a context/instance with an appropriate lifecycle and its own security strategy.

## 15. Static Fields and Constructors: What Does the Counter Actually Count?

A textbook example is often written as:

~~~java
class Product {
    private static int created;

    Product() {
        created++;
    }
}
~~~

In a simple sequential program, `created` increments each time the constructor body passes the increment statement. However, define the **meaning of the counter** precisely:

- It counts **how many times the body reaches the `created++` statement**, and does not automatically count "all living objects".
- If the class has multiple constructors and uses `this(...)`, place the increment in an appropriate location to avoid double-counting a single instance creation.
- A constructor can throw an exception **after incrementing the counter**. In that case, the counter increases even though the `new` call did not complete successfully.
- A superclass constructor may increment the counter when the subclass constructor later fails.
- If objects are created through special mechanisms other than normal constructor calls, a constructor counter does not necessarily cover all cases.
- Across multiple threads, `created++` does not guarantee accurate counting without synchronization/atomicity.

If you want to measure **the number of successful creation requests** under a business contract, it is sometimes better to count in a factory/service at the success boundary rather than inferring it from every constructor call.

## 16. Runnable Example: Constructor Rejecting Data and Counter

Save **`StaticCounterFailureDemo.java`**:

~~~java
public class StaticCounterFailureDemo {
    static final class Ticket {
        private static int acceptedCount;

        private final String code;

        Ticket(String code) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code required");
            }

            this.code = code;
            acceptedCount++;
        }

        static int acceptedCount() {
            return acceptedCount;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket("A");
        System.out.println("first=" + first.code());

        try {
            new Ticket("");
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected invalid ticket");
        }

        Ticket second = new Ticket("B");
        System.out.println("second=" + second.code());
        System.out.println("accepted=" + Ticket.acceptedCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticCounterFailureDemo.java
java StaticCounterFailureDemo
~~~

Stdout:

~~~text
first=A
rejected invalid ticket
second=B
accepted=2
~~~

In this specific example, validation occurs **before** the increment, and no other step in the constructor can throw an exception after the increment. Therefore, `acceptedCount` equals 2. However, the `acceptedCount()` method should not be interpreted as a general measure of "the number of Ticket objects currently still in existence": the Java garbage collector does not automatically decrement the counter when an object is no longer reachable.

## 17. `static final`: Class-Scoped Constants

Some shared values should not be modified:

~~~java
public final class Limits {
    public static final int MAX_ITEMS = 100;
    public static final String DEFAULT_LANGUAGE = "vi";

    private Limits() {
        throw new AssertionError("utility class");
    }
}
~~~

This is an illustrative class; the constant values belong to the class and do not require an instance. Creating a private constructor also expresses the intent not to allow callers to create `new Limits()`.

Java convention usually names static constants in **UPPER_SNAKE_CASE** (`MAX_ITEMS`). This is a naming convention, not a compiler syntax requirement.

### When Is `static final` Truly a Constant Variable?

In Java, a `final` field of a primitive type or `String` initialized with a **constant expression** can be a *constant variable* according to the specification. Its value can be embedded into callers' class files at compile time.

~~~java
public static final int MAX_ITEMS = 100;
~~~

If a library changes the value to 200 but the client **is not recompiled**, old client code may still use the value 100 embedded earlier. That is why you should think carefully before making a constant public when it might change between versions.

A field such as:

~~~java
public static final java.time.Duration TIMEOUT =
        java.time.Duration.ofSeconds(5);
~~~

is not a compile-time constant variable under the same primitive/String rule, even though the reference is final and the Duration object is immutable.

## 18. A `static final` Reference Does Not Make a Mutable Object Immutable

Consider:

~~~java
class SharedNames {
    static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();
}
~~~

`NAMES` is a **static final reference** and cannot be reassigned to another List after initialization. However, the call:

~~~java
SharedNames.NAMES.add("Mai");
~~~

still modifies the **shared ArrayList object**.

If you want exposed data not to be modified through mutation APIs:

~~~java
public static final java.util.List<String> DEFAULT_NAMES =
        java.util.List.of("Mai", "An");
~~~

`List.of` provides a List that does not support normal mutation operations and rejects null elements. When the elements are immutable `String` objects, this is a relatively easy default structure to protect. If the elements are mutable objects, even a list that disallows add/remove does not by itself prevent modifying **the state of the element objects**.

### Constant or Global Mutable State?

- `static final int MAX_RETRIES = 3`: a simple constant.
- `static final List<String> NAMES = List.of(...)`: a static reference to an unmodifiable List.
- `static final List<String> NAMES = new ArrayList<>()`: a non-reassignable static reference, yet a **shared mutable list**.
- `static int count`: mutable class-level primitive state.

Do not treat the word `final` as proof that "the shared data is immutable at every layer".

## 19. Inheritance: Static Fields Belong to the Declaring Class, Not Individual Subtype Objects

With class inheritance:

~~~java
class Parent {
    static int count;
}

class Child extends Parent {
}
~~~

`Child` can refer to the inherited static member `count` according to access rules, but that **does not necessarily create a new count field in Child**. If Child **does not declare a field with the same name**, `Parent.count` and `Child.count` refer to **the field declared in Parent** in a valid context.

**Do not infer:** "Each subclass has its own copy of all static fields of the superclass." No. A static field remains attached to **the declaring class**.

### Runnable Example: Static Field Shared Through a Subclass

Save **`InheritedStaticFieldDemo.java`**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int count = 0;
    }

    static final class Child extends Parent {
    }

    public static void main(String[] args) {
        Parent.count = 3;

        System.out.println("parent=" + Parent.count);
        System.out.println("child=" + Child.count);

        Child.count++;
        System.out.println("after parent=" + Parent.count);
        System.out.println("after child=" + Child.count);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

Stdout:

~~~text
parent=3
child=3
after parent=4
after child=4
~~~

Both `Parent.count` and `Child.count` in the example refer to the static field **declared in Parent**. The syntax `Child.count` does not mean Child stores a separate count of its own.

As a matter of style, you should access it via **the actual declaring class** (`Parent.count`) so readers do not mistakenly think there is a separate field in Child.

## 20. Field Hiding: A Subclass Declares a Static Field with the Same Name

If Child declares a new field with the same name, it **hides** Parent's field instead of overriding the field:

~~~java
class Parent {
    static int count = 10;
}

class Child extends Parent {
    static int count = 20;
}
~~~

Now there are **two different fields**:

- `Parent.count` belongs to Parent.
- `Child.count` belongs to Child.

Which field is selected depends on the **name/compile-time type of the access expression**, with no dynamic dispatch like overridden instance methods.

### Runnable Example: Two Static Fields with the Same Name

Save **`StaticFieldHidingDemo.java`**:

~~~java
public class StaticFieldHidingDemo {
    static class Parent {
        static int value = 10;
    }

    static final class Child extends Parent {
        static int value = 20;
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = new Child();

        System.out.println("Parent=" + Parent.value);
        System.out.println("Child=" + Child.value);
        System.out.println("parentView=" + parentView.value);
        System.out.println("childView=" + childView.value);

        Child.value = 99;
        System.out.println("after Parent=" + Parent.value);
        System.out.println("after Child=" + Child.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFieldHidingDemo.java
java StaticFieldHidingDemo
~~~

Stdout:

~~~text
Parent=10
Child=20
parentView=10
childView=20
after Parent=10
after Child=99
~~~

`parentView` and `childView` both reference runtime objects of type Child (created independently here). However, the statement `parentView.value` is resolved according to the **declared type Parent** of the expression and selects `Parent.value`; `childView.value` selects `Child.value`. Accessing static members through references like this is **valid but should not be used** because it causes confusion. Use `Parent.value` and `Child.value`.

### Static Method Hiding Differs from Instance Method Overriding

Static methods can be hidden by static methods with the same signature in a subclass; calls through a reference name/type are resolved according to compile-time rules. Conversely, overridden instance methods use dynamic dispatch based on the runtime object. Do not equate the two mechanisms.

## 21. Static Members in Static Context and Instance Context

Inside a static method, **there is no `this` of an object instance**:

~~~java
class Calculator {
    private int instanceValue = 5;
    private static int sharedValue = 10;

    static int readShared() {
        return sharedValue;
    }

    static int readOneInstance(Calculator instance) {
        return instance.instanceValue;
    }
}
~~~

The `readShared()` method reads the static field directly. Since the `readOneInstance` method wants to read an instance field, it takes **a reference to a Calculator object**.

Intentionally wrong:

~~~java
static int invalid() {
    // return this.instanceValue; // Wrong: this does not exist in a static context.
    // return instanceValue;      // Wrong: no instance receiver.
    return Calculator.readShared();
}
~~~

The snippets above are illustrative and need to be placed in an appropriate class. You cannot use a static method as an implicit instance method and expect `this` to exist.

### Note on Local Variables

Java does not support declaring:

~~~java
void method() {
    // static int visits = 0; // Syntax error in Java.
}
~~~

If you want to store data shared across multiple method calls, you can use a **static field** in the class or an object state with an appropriate lifecycle. Do not unconditionally turn every "variable that needs to persist across calls" into static; in many cases, an instance field on a service object is better.

## 22. A Static Nested Class Is Not a Static Field

These are two different forms:

~~~java
class Outer {
    static int shared = 7;

    static class Nested {
        int ownValue = 3;
    }
}
~~~

- `Outer.shared` is a **static field** belonging to Outer.
- `Outer.Nested` is a **static nested class**, a nested type inside Outer that does not require an automatic enclosing instance.
- Each `new Outer.Nested()` still creates a **Nested instance** with its own `ownValue`.
- `Nested` can also have its own static fields according to Java rules.

The `static` keyword before a nested class declaration **does not make all fields inside Nested static**.

### Example

~~~java
Outer.Nested a = new Outer.Nested();
Outer.Nested b = new Outer.Nested();
a.ownValue = 5;
b.ownValue = 9;
~~~

`a.ownValue` and `b.ownValue` are different, even though the `Nested` class has `static` in its declaration. If `Nested` has `static int sharedCounter`, that is a static field of `Nested`.

## 23. Shared Mutable Static State Is Not Thread-Safe by Default

A static field can be read/written by multiple threads at the same time. However, **`static` does not mean synchronized, atomic, or volatile**.

Counterexample:

~~~java
class UnsafeCounter {
    static int count;

    static void increment() {
        count++;
    }
}
~~~

`count++` consists of the logical steps read, increment, and write. When two threads do this at the same time, an update can be lost. You cannot assume that if two threads each increment 1,000 times, the final counter will always be exactly 2,000.

Besides atomicity, there is also **visibility**: if one thread writes a field without proper synchronization, another thread will not necessarily observe the update in the way you expect.

### Does `volatile` Solve Everything?

`volatile` supports specific visibility and ordering guarantees under the Java Memory Model, but **does not make `count++` atomic**. If you need to increment/decrement a count safely, use `AtomicInteger` or appropriate synchronization/locks, depending on the invariant.

## 24. Runnable Example: Shared Static `AtomicInteger` Across Threads

Save **`AtomicStaticCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicStaticCounterDemo {
    static final class Counter {
        private static final AtomicInteger VALUE = new AtomicInteger();

        static void increment() {
            VALUE.incrementAndGet();
        }

        static int value() {
            return VALUE.get();
        }
    }

    static void work() {
        for (int i = 0; i < 1_000; i++) {
            Counter.increment();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread first = new Thread(AtomicStaticCounterDemo::work);
        Thread second = new Thread(AtomicStaticCounterDemo::work);

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("count=" + Counter.value());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicStaticCounterDemo.java
java AtomicStaticCounterDemo
~~~

Stdout:

~~~text
count=2000
~~~

`VALUE` is a static final reference to a shared `AtomicInteger` object. Each thread calls `incrementAndGet()` on the same object. AtomicInteger guarantees that increment is an atomic operation according to the API; `join()` ensures `main` waits for both threads to finish before reading the result.

**Points to distinguish:**

- `static` only specifies class-level state sharing.
- `final` only prevents reassigning the `VALUE` reference.
- `AtomicInteger` is the mechanism that supports atomic updates of the count value.

If an invariant involves **multiple interdependent fields**, using one AtomicInteger per field **does not necessarily** make the entire multi-field operation atomic. An overall concurrency design is required.

## 25. A Static Field Holding a Shared Collection Also Needs Thread Safety

~~~java
private static final java.util.List<String> EVENTS =
        new java.util.ArrayList<>();
~~~

If multiple threads call `EVENTS.add(...)` without synchronization, `ArrayList` does not guarantee thread safety. Concurrent calls can cause a race, missing/extra results, or invalid state depending on the situation.

Options depending on the need:

- Use an appropriate concurrent collection, such as `ConcurrentHashMap` for certain map tasks.
- Use `Collections.synchronizedList(...)` and **synchronize properly during iteration as well**, per the wrapper's contract.
- Protect operations consistently using lock/synchronized.
- Move state into a service instance and manage thread ownership.
- Use an immutable snapshot when only reading is needed and there are no complex mutations.

Do not mechanically convert every ArrayList into a concurrent collection: you must determine **which operations must be atomic**, which invariants span multiple steps, and what synchronization cost is acceptable.

## 26. Static State Can Make Tests Dependent on Each Other

A static counter persists across test methods running on the **same runtime class**. If test A calls `visit()`, test B may see values left over from A, regardless of whether the tests create a new `VisitCounter` object:

~~~java
class VisitCounter {
    static int visits;
    static void visit() { visits++; }
}
~~~

This problem differs from a **race condition**: even when run sequentially, test order can still alter the outcome. Resetting shared state is a solution that should only be used when there is a clear management boundary; if run in parallel, one test might reset the state while another test is using it.

In this lesson on **static fields**, the key thing to remember is that a class-level field **does not belong to each test's fixture instance**. When state must be independent, prefer an instance-owned counter. The mechanisms causing flaky tests, test isolation design, JUnit lifecycle, parallel execution, reset/cleanup, and dependency injection are practiced in depth in the article **"Risks of Mutable Static State and Interdependent Tests"**.

## 27. Runnable Example: Instance Counter Helps Separate Test State

Save **`StaticVsInstanceCounterDemo.java`**:

~~~java
public class StaticVsInstanceCounterDemo {
    static final class StaticTracker {
        private static int calls;

        static void visit() {
            calls++;
        }

        static int calls() {
            return calls;
        }
    }

    static final class InstanceTracker {
        private int calls;

        void visit() {
            calls++;
        }

        int calls() {
            return calls;
        }
    }

    public static void main(String[] args) {
        StaticTracker.visit();
        StaticTracker.visit();

        InstanceTracker first = new InstanceTracker();
        InstanceTracker second = new InstanceTracker();

        first.visit();
        first.visit();
        second.visit();

        System.out.println("static=" + StaticTracker.calls());
        System.out.println("first=" + first.calls());
        System.out.println("second=" + second.calls());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticVsInstanceCounterDemo.java
java StaticVsInstanceCounterDemo
~~~

Stdout:

~~~text
static=2
first=2
second=1
~~~

`StaticTracker` has a class-level `calls` field; static method calls affect the same value. With `InstanceTracker`, the two tracker instances have separate `calls` fields, making it easy to create a new tracker for each test or working session.

This does not mean instance fields are automatically thread-safe. If two threads share the same `InstanceTracker`, the same race condition still has to be considered. **The difference is the sharing scope**, not an automatic synchronization mechanism.

## 28. Static References and Object Lifecycle / Garbage Collection

When a static field points to an object, that object can remain reachable as long as the runtime class and the corresponding reference path exist.

~~~java
class Cache {
    static Object recent;

    static void keep(Object value) {
        recent = value;
    }

    static void clear() {
        recent = null;
    }
}
~~~

If `Cache.keep(bigObject)` runs, `Cache.recent` holds a reference to that object; the local variable `bigObject` going out of scope does not automatically cause the object to be reclaimed.

`Cache.clear()` removes the reference from the static field, but:

- The object may still be referenced from elsewhere.
- The JVM is not required to reclaim the object immediately.
- `System.gc()` does not allow the user to reliably "destroy object X immediately".

### Memory Retention in Static Caches

A static `Map` that keeps adding data without eviction can hold many objects reachable in a long-running application. Signs:

- Temporary data attached to a static registry.
- A cache holding every user/session without a TTL or size cap.
- Event listeners remaining in a static collection after a component finishes.
- Class loader/callback references retaining an entire graph of unnecessary objects.

The solution is not just calling GC; you must **intentionally manage ownership, lifecycle, and reference-clearing policies**.

## 29. Class Loaders: "One Static Copy" Must Be Stated Accurately

A textbook summary is often "each class has one copy of a static field". In a Java runtime with class loaders, it must be expressed more accurately:

> Each **defined runtime class** has its corresponding static state. Two classes with the same binary name defined by **two different class loaders** can be two separate runtime classes and therefore have separate static state.

In a simple console program with a standard class loader, you can treat `Student.createdCount` as a shared value across the Student instances in the program. However, in application servers, plugin systems, test isolation, or environments using class loaders, "static is unique across the entire JVM regardless of class loader" is **inaccurate**.

### Modules and Class Loaders Are Not the Same Thing

Java modules (JPMS) control namespaces, readability, exports, and certain access permissions. Class loading/defining classes has its own mechanism. When discussing static state, you must consider **runtime class identity**, not just the package/module name written in source.

You do not need to implement custom class loading to study this lesson; what matters is avoiding overstating that static is always an absolute single global variable.

## 30. Static Initialization Can Fail

A static field initializer or static initializer block can throw an exception.

~~~java
class DangerousConfig {
    static final int PORT = parsePort();

    static int parsePort() {
        throw new IllegalArgumentException("invalid configuration");
    }
}
~~~

This is an illustrative class. When the class is initialized along a path requiring reading `PORT`, the error occurs during **class initialization**; the JVM can report `ExceptionInInitializerError` for an unchecked exception like in the example and mark the class in a failed-initialization state.

Subsequent uses of the class may encounter `NoClassDefFoundError` because the class failed during initialization, depending on the context. Therefore, you should not arbitrarily place heavy tasks, I/O lacking error handling, or error-prone environment-dependent data directly in static initializers.

**Distinction:** Static initialization occurs according to the lifecycle of the runtime class; constructors handle creating **each instance**. Failures in the two phases have different diagnostic paths and impacts.

## 31. Static Initialization Across Multiple Classes: Circular Dependencies

Suppose class A initializes a static field by reading a static field of B, while B reads A while A has not finished yet. The observed state may contain **default values or incomplete values** according to initialization rules.

This is a form of **circular static initialization dependency**. It is even harder to read than an ordinary constructor dependency cycle because it involves class initialization timing.

How to avoid it:

- Avoid complex cross-initialized static fields.
- Keep static initialization simple, without executing behavior that depends on another class not yet ready.
- Place dependencies in explicitly created objects or a factory with a clear setup order.
- Consider the lazy holder pattern or a service lifecycle when lazy initialization is genuinely needed.

Do not use a static initializer as a place to orchestrate a large dependency network just because it runs automatically.

## 32. Are a Singleton and a Static Field the Same Thing?

**Singleton** is a design pattern aiming for a single instance shared within a chosen scope; a static field can be used to hold a reference to that instance. However, a static field and a singleton are **two different concepts**:

- `static int count`: a class-level field, **not a singleton object**.
- `static final Service INSTANCE = new Service()`: a static reference to a Service instance.
- `new Service()`: creates an instance; if the constructor is public, many other Service instances can still exist.
- The Singleton pattern requires clear constraints on instance creation paths, lifetime, and semantics.

### Enum Singleton Example

~~~java
enum AppRegistry {
    INSTANCE;

    private int requests;

    void register() {
        requests++;
    }

    int requests() {
        return requests;
    }
}
~~~

`AppRegistry.INSTANCE` is an enum constant representing an enum instance of the corresponding runtime class. This is a commonly used way to represent a runtime-class-scoped singleton in Java, yet the `requests` field is still **mutable** and not automatically thread-safe.

### Why Not Use a Singleton by Default for Every Service?

A shared global singleton can:

- Make tests dependent on state.
- Make it hard to substitute another implementation.
- Increase coupling.
- Make per-tenant/session configuration difficult.
- Cause races if the service is mutable.

When you only need **one service object within a coordinated application scope**, dependency injection and lifecycle scope may be more appropriate than a hardcoded global static field.

## 33. A Static Factory Does Not Mean Static Shared Data

A static factory method can create a new object **every time it is called**:

~~~java
class Ticket {
    private final String code;

    private Ticket(String code) {
        this.code = code;
    }

    static Ticket of(String code) {
        return new Ticket(code);
    }
}
~~~

`Ticket.of("A")` is a **static method**, yet each call in this example returns a reference to a **new Ticket instance**. The presence of `static` in a method **does not mean** the method must return a shared object.

Conversely, a static factory may cache and return the same instance, depending on the contract. You cannot infer **object identity** solely from the fact that the factory carries the `static` keyword; you must read the specific implementation/contract.

## 34. Static Imports Do Not Create Copies of Data

The syntax:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

allows using `PI` and `max(...)` by simple name in a valid context.

It **does not copy the static field** into the importing class, nor does it create extra state. `import static` only affects how names are resolved at compile time and still obeys access rules.

### Be Careful with Name Collisions

If a class defines its own `PI` or imports two static members with the same name, conflicts/ambiguity can occur under Java rules. Using the `Math.PI` qualifier often makes code easier to read when a file has many static imports.

## 35. Static Fields and Access Modifiers

Static fields can be `private`, package-private, `protected`, or `public` according to Java rules.

Example:

~~~java
public final class Statistics {
    private static int requests;

    public static void recordRequest() {
        requests++;
    }

    public static int requests() {
        return requests;
    }
}
~~~

This class controls changing the counter through the `recordRequest` API, rather than letting callers do `Statistics.requests = -10`.

However, private + public methods **do not automatically solve concurrency**: `requests++` can still race. If multiple threads use the class together, you need to choose an atomic/synchronized strategy.

### Do Not Expose Class-Level Mutable Collections

~~~java
public static final java.util.List<String> ALL_USERS =
        new java.util.ArrayList<>();
~~~

This is a **public static final reference to a mutable List**, not an immutable constant. Any caller with access can `add/remove/clear`; the class loses control over the registry. It is usually better to do:

~~~java
private static final java.util.List<String> USERS =
        new java.util.ArrayList<>();

public static java.util.List<String> usersSnapshot() {
    return java.util.List.copyOf(USERS);
}
~~~

These snippets are class-member illustrations; they must be placed in a valid class. In a multi-threaded environment, you must synchronize properly when adding and taking snapshots, not just copy arbitrarily.

## 36. Design Scenario: One Config for the Whole Application or Separate Per Instance?

Suppose `EmailSender` needs a timeout configuration:

**Static approach:**

~~~java
class EmailSender {
    static int timeoutMillis = 5_000;
}
~~~

All EmailSender instances share a single timeout if they read this field. Changing `EmailSender.timeoutMillis` will affect other instances.

**Instance approach:**

~~~java
class EmailSender {
    private final int timeoutMillis;

    EmailSender(int timeoutMillis) {
        if (timeoutMillis <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        this.timeoutMillis = timeoutMillis;
    }
}
~~~

Each EmailSender has its own timeout. You can create a shared configuration object and pass its reference to the senders if you want them to share it within a specific scope.

### When to Choose Which?

- If the timeout is an **immutable constant** applied everywhere by design, static final can be reasonable.
- If the timeout is allowed to vary by environment/request/tenant, instance configuration or dependency injection is usually easier to control.
- If hot configuration changes are required, the design needs safe **publication/visibility** across threads and an update policy.
- If a library is used across multiple applications inside the same JVM, mutable static config can cause unwanted collisions.

## 37. Common Mistakes with Static Fields

| Misconception or mistake | Consequence | Correct perspective |
| --- | --- | --- |
| "`static` is a field of each individual object." | Predicting each instance has its own counter | A static field is attached to the runtime class |
| "Every `new` increments all static counters." | Wrong when the constructor does not update it | Only executed code changes the value |
| "`Student b = a;` creates a new instance." | Miscounting objects | It only copies the reference |
| "`object.staticField` accesses that object's field." | Easy to confuse shared state with separate state | Use `ClassName.staticField` |
| "`static final ArrayList` cannot be modified." | Callers can still add/remove | Final keeps the reference, the List remains mutable |
| "`static` is thread-safe." | Lost updates, race conditions | Use appropriate atomic/synchronization mechanisms |
| "`volatile int count; count++` is atomic." | Updates can be lost | Volatile does not make compound updates atomic |
| "`Child.count` is always a different field from `Parent.count`." | Miscounting when it is only inherited | Identify the class **declaring** the field |
| "Static fields are overridden like methods." | Wrong dynamic dispatch prediction | Field hiding follows compile-time resolution |
| "One JVM has only one static copy for the same class name." | Wrong with class loaders | Tied to runtime class identity |
| "Reading any `static final` triggers initialization." | Wrong for constant variables | Distinguish constant expressions |
| "The static block runs every time an object is created." | Wrong log prediction | Class initialization does not repeat per instance |
| "A static counter is the number of living objects." | No correspondence with GC | The counter only follows the code's update logic |
| "A static field disappears as soon as the method creating the object ends." | Misunderstanding reachability | A static reference can keep an object alive |
| "A local `static int` variable is valid." | Java syntax error | Use a static field at class scope |
| "A static factory always returns the same object." | Wrong identity inference | A factory can create new/cached objects depending on its contract |
| "A static import creates a new field." | Misunderstanding state sharing | Import only affects name resolution |
| "Making currentUser static is convenient for a web app." | Mixing user/request data | Use the proper scope for each session/tenant |
| "A private static field definitely has no shared mutation." | Public methods still modify the field | Review all update paths |
| "A singleton is equivalent to stateless." | A singleton still has mutable state | Design thread-safety and lifecycle |

## 38. Process for Analyzing Code with Static Fields

When reading Java code with multiple instances and static members, follow these steps:

**Step 1 — Identify the runtime class and the class declaring the field.** If there is inheritance, check whether the field is defined in the superclass or subclass, and whether hiding occurs.

**Step 2 — Classify the field.** Explicitly note `instance field` or `static field`; for `static final`, also note whether it has a mutable object reference.

**Step 3 — Determine class initialization timing.** In what order do static initializers run? Are there any special constant variables?

**Step 4 — Count actual `new` invocations.** Which statements does each constructor run? Are there thrown exceptions, constructor chaining, factories, or aliases?

**Step 5 — Track separate and shared state in two tables:**

| Execution point | Instance #1 | Instance #2 | Static state |
| --- | --- | --- | --- |
| Initially | Does not exist yet | Does not exist yet | Not yet used / initialized value when class is initialized |
| First `new X()` | Own fields | Does not exist yet | May change |
| Second `new X()` | Unchanged | Own fields | May change |
| `instance1.method()` | May change | Not necessarily changed | May change if the method writes static |
| `X.staticMethod()` | No instance needed | No instance needed | Can read/write |

**Step 6 — Predict the output based on values at the exact point in time.** Remember Java class initialization, statement order, and possible thread interleaving.

**Step 7 — Check the design contract.** Should the data really be shared class-wide, or does it belong to an object/request/tenant? Is thread safety or lifecycle cleanup needed?

## 39. Exercise 1 — Predicting the Counter with Two Objects

Given:

~~~java
class Device {
    static int total;
    int uses;

    Device() {
        total++;
    }

    void use() {
        uses++;
    }
}
~~~

Caller:

~~~java
Device first = new Device();
Device second = new Device();
first.use();
first.use();
second.use();
Device alias = first;
alias.use();

System.out.println(Device.total);
System.out.println(first.uses);
System.out.println(second.uses);
~~~

**Answer:**

~~~text
2
3
1
~~~

There are two `new Device()` calls, so `total = 2`. `alias = first` does not create a new object. `uses` of first increments three times via `first` and `alias`; `uses` of second increments once.

These are **practice code snippets**; they must be assembled into a valid Java file (with the caller placed inside a method) to run.

## 40. Exercise 2 — Choose Static or Instance?

Choose the field type for each piece of data and explain:

- `MAX_CART_ITEMS = 100` applying to all carts in a module.
- `cart.items` is the individual product list of each cart.
- `currentUserId` for each HTTP request.
- `createdCount` of a textbook example counting constructor calls in a class.
- `currency` of each order.
- `logger` associated with a class.
- `lastSearchResult` which can vary per user.

Hint: `MAX_CART_ITEMS` and logger are usually static final candidates. Each cart's list, the request's user, the order's currency, and per-user last search **should not be global static state**. A static counter can be appropriate if scope and thread safety are clearly defined.

## 41. Exercise 3 — Analyzing Inheritance and Field Hiding

Given:

~~~java
class Parent {
    static int value = 1;
}

class Child extends Parent {
    static int value = 2;
}
~~~

If:

~~~java
Parent p = new Child();
Child c = new Child();

System.out.println(Parent.value);
System.out.println(Child.value);
System.out.println(p.value);
System.out.println(c.value);
~~~

**Answer:**

~~~text
1
2
1
2
~~~

The two static fields are declared separately, not overridden. `p.value` and `c.value` depend on the compile-time type of the reference; use `Parent.value` and `Child.value` directly instead of syntax through an instance.

## 42. Exercise 4 — Designing a Shared Registry

A `ClubMember` class wants to record member names. Design:

- An instance field `name`, with each member keeping its own name.
- A class-level registry recording registered names.
- Do not expose a mutable List reference directly to callers.
- Reject null/blank names.
- Have a clear duplicate-name policy.
- Have a cleanup plan and capacity limit if the registry lives long.
- If there are multiple threads, use appropriate synchronization or a concurrent structure.

Then answer: must the registry really be global/static? A `ClubRegistry` instance passed into multiple ClubMember objects or services can be **easier to test and manage in scope** if there are multiple separate clubs.

## 43. Exercise 5 — Fixing a Multi-Threaded Counter

Unsafe code:

~~~java
class Hits {
    static int count;

    static void hit() {
        count++;
    }
}
~~~

Replace it with `private static final AtomicInteger` and a public static method `hit()` using `incrementAndGet()`. Try running multiple threads incrementing together and then `join()` before reading; explain why the result becomes predictable and why `final` only fixes the AtomicInteger reference rather than fixing its value.

## 44. Exercise 6 — Behavior of a static final Constant

Given:

~~~java
class Constants {
    static final int A = 5;
    static final Integer B = Integer.valueOf(6);

    static {
        System.out.println("initialized");
    }
}
~~~

Write `main` yourself to print `Constants.A` and then `Constants.B`. Predict that `A` is a primitive constant variable, so reading it may not trigger class initialization; `B` is not a constant variable, so accessing it will initialize the class and print `initialized`. Compare with `StaticConstantInitializationDemo` to verify.

## 45. End-of-Article Checklist

- [ ] I know that a static field belongs to the runtime class rather than each individual instance.
- [ ] I know that an instance field belongs to the separate state of each object.
- [ ] I trace the result accurately when multiple objects read/write a static field.
- [ ] I do not treat alias assignment as a constructor call.
- [ ] I access a static field using `ClassName.field` when appropriate.
- [ ] I distinguish a static field from a static method and a static nested class.
- [ ] I understand how class initialization differs from instance initialization.
- [ ] I can predict the order of static field initializers and static blocks.
- [ ] I know that static fields have default values before explicit initializers.
- [ ] I recognize constant variables and the limits of compile-time inlining.
- [ ] I know that a `static final` reference does not make a mutable object immutable.
- [ ] I know that an inherited static field does not automatically create a copy in a subclass.
- [ ] I understand field hiding and how it differs from overriding instance methods.
- [ ] I do not use static to hold per-user/per-request data.
- [ ] I know that static mutable fields require a thread-safety strategy.
- [ ] I understand that `volatile` does not make `++` atomic.
- [ ] I use `AtomicInteger`/synchronization appropriately when needed.
- [ ] I know that static collections can keep objects reachable for a long time.
- [ ] I understand that static state can leak between tests.
- [ ] I know that class loaders can lead to multiple runtime classes with the same name having separate static states.
- [ ] I do not confuse a static field with the singleton pattern.
- [ ] I know that a static factory can create a new object on each call.
- [ ] I independently compile, run, and explain the stdout of the Java 17+ programs in this article.

**Conclusion:** The `static` keyword on a **field** means that field belongs to the **runtime class**, rather than being duplicated per object instance. This is an intentional way to share data across instances, useful for constants and certain class-level resources. However, **shared mutable state** requires explicit control over update permissions, concurrency, isolation, lifecycle, and usage scope. If data belongs individually to each object, request, or user, **an instance field or appropriately scoped service state** is usually the better choice.
