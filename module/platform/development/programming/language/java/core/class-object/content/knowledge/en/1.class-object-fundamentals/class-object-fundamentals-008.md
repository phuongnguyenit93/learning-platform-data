# Learning Roadmap and Foundational Java Knowledge Needed Before Learning Class & Object

In Java, a **class** describes the structure and behavior of a type of object; an **object** is a concrete instance created and used when the program runs. To learn **Java Core – Class & Object** effectively, learners need to connect Java syntax knowledge with how objects are initialized, store state, receive method calls, and collaborate with other objects.

This article is a **learning map and prerequisite competency checklist**, helping to answer three questions:

1. What do you need to know to get started?
2. In what order should you learn class/object concepts so that they do not feel disconnected?
3. What criteria can confirm that you understand the concepts and can write programs using objects on your own?

You do not need to finish learning all of Java or frameworks before learning class/object. You only need a solid grasp of basic syntax, variables and data types, conditionals, loops, methods, and a preliminary distinction between primitive values and references. Advanced topics such as reflection, in-depth generics, multithreading, Spring, or class loading mechanisms can be learned later.

## 1. The Big Picture: What Depends on What?

~~~text
JDK, javac, java, source file structure
                  |
Data types, variables, expressions, operators
                  |
Conditionals, loops, arrays; methods
                  |
Distinguishing primitive and reference, null
                  |
        class and object, new
                  |
         Field, method, this
                  |
Constructor, initialization, and valid state
                  |
 instance / static, data scope and lifecycle
                  |
Encapsulation, access modifier, invariant checks
                  |
    Object identity, alias, == and equals
                  |
Two or more collaborating objects; comprehensive exercises
~~~

The diagram illustrates the **recommended order**, not a rigid sequence for all curricula. For example, you may encounter `String` (a class) very early on even before studying object theory; at that point you only need to know how to use strings, and later you will dive deeper into why `String` is a reference type.

| Stage | Core Knowledge | Deliverable / Competency Check |
| --- | --- | --- |
| 0. Java Environment | JDK, terminal, `javac`, `java`, `.java` files | Compile and run a program independently |
| 1. Syntax and Data | Variables, primitives, `String`, `null`, operators, casting | Predict expression values, avoid mismatched-type comparisons |
| 2. Control Flow and Methods | `if`, `switch`, loops, arrays, parameter, return | Decompose algorithms into small methods |
| 3. Object Model | `class`, `new`, field, method, `this` | Create two objects and demonstrate independent state |
| 4. Initialization and Access Control | Constructor, `static`/instance, `private`/`public`, getter, update behavior | Prevent creating an object in or moving it into an invalid state |
| 5. References and Comparison | Alias, parameter passing, `==`, `equals`, `final`, null | Explain why two variables both observe the same change |
| 6. Application | Multiple interacting objects, data processing, and simple testing | Complete an object management exercise with valid and invalid cases |

## 2. Stage 0 — Knowing How Tools Run a Java Program

### JDK, JVM, and the Process from Source Code to Program

- **JDK (Java Development Kit)** contains the required development tools, including the `javac` compiler and the `java` execution tool.
- **JVM (Java Virtual Machine)** executes Java bytecode. A typical Java compiler translates `.java` source code into bytecode in `.class` files.
- **`javac`** is used to compile; **`java`** is typically used to launch a program with an appropriate entry point. For this lesson, use JDK 17 or higher.

Terminal check:

~~~bash
java -version
javac -version
~~~

Both commands need to run. The exact version and output message string depend on the installed JDK.

Create the file **`HelloJava.java`**:

~~~java
public class HelloJava {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac HelloJava.java
java HelloJava
~~~

Stdout:

~~~text
Hello, Java!
~~~

Initial details you must be able to recognize:

- The file name `HelloJava.java` matches the name `public class HelloJava`.
- Code blocks are enclosed in curly brace pairs `{ }`; the statement calling `println` ends with a semicolon.
- `public static void main(String[] args)` is the standard entry point for a Java console program. `static` allows `main` to run without having to manually create an instance of `HelloJava`.
- `System.out.println(...)` prints a string to the standard output stream and moves to a new line.
- For a source file containing multiple top-level classes, at most one class can be `public`; the file name must match the name of that public class.
- Class names follow the `UpperCamelCase` convention; methods and variables follow `lowerCamelCase`. Naming conventions make code easier to read, though not all of them are mandatory compiler rules.

**Checkpoint:** You can create a new file, compile it, fix an intentional syntax error, read the error message, and run it again. If you cannot do this yet, master it before moving on to multi-class examples.

## 3. Stage 1 — Variables, Data Types, and Expressions

### Primitive and Reference: The Most Important Prerequisite Knowledge

Java distinguishes between **primitive types** and **reference types**.

| Primitive | Examples | Key Notes |
| --- | --- | --- |
| Integer | `byte`, `short`, `int`, `long` | Stores an integer value within the type's representable range |
| Floating-point | `float`, `double` | Binary approximation; does not represent every decimal number exactly |
| Character | `char` | A single UTF-16 code unit, not synonymous with a complete Unicode character |
| Boolean | `boolean` | `true` or `false` |

Types such as `String`, arrays like `int[]`, and classes you write are **reference types**. A reference variable holds a reference value pointing to an object or `null`; assigning a reference to another variable does not automatically create an additional object.

Expression example:

~~~java
int quantity = 3;
double unitPrice = 19.5;
double total = quantity * unitPrice;
String label = "Sách";
boolean available = quantity > 0;
~~~

`quantity`, `unitPrice`, `total`, and `available` have primitive types; `label` has type `String`, which is an object immutable in its string value. Do not assume that a type written shortly or using quotation marks becomes a primitive.

### What You Need to Know Before Writing Classes

1. **Declaration and assignment:** `int age = 18;`, reading the value back, and changing it with the assignment `age = 19;`.
2. **Variable scope:** a method's local variable has only its corresponding scope; an object's field has a different scope and lifecycle.
3. **Operators:** `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `>`, `>=`, `&&`, `||`, `!`.
4. **Type casting:** `(double) total / count` differs from performing integer division first and casting afterward.
5. **Strings:** concatenate strings with `+`; compare contents with `equals`; note that `null` is not the empty string `""`.
6. **Literals:** distinguish `5` (`int`), `5L` (`long`), `5.0` (`double`), `'A'` (`char`), and `"A"` (`String`).
7. **`final`:** a local variable `final int limit = 10;` cannot be assigned again. For a `final` reference variable, it cannot be reassigned to another reference; the object it points to can still be mutable.

Note on integer division: `7 / 2` yields `3`, whereas `7.0 / 2` yields `3.5`. This can easily produce wrong results if a field is calculated from integers.

### Distinguishing Default Values of Fields from Local Variables

**Instance fields** have default values when an object is allocated before specific initialization steps take place: `int` defaults to `0`, `boolean` defaults to `false`, and references default to `null`. **Local variables** are not allowed to be read before the compiler determines that a value has been assigned.

~~~java
class Example {
    int count;              // Defaults to 0 when the instance is initialized
    String description;     // Defaults to null
    void work() {
        int localCount = 0; // Must be initialized before reading
        System.out.println(localCount);
    }
}
~~~

Default values are only Java's initialization mechanism; they do not guarantee business validity. For example, an `email` field defaulting to `null` may not meet an application's requirements.

## 4. Stage 2 — Conditionals, Loops, Arrays, and Methods

Object methods use the same control structures as basic Java programs. You need to be able to read and write on your own:

- `if / else` for conditional branching;
- basic `switch` when a problem has multiple cases;
- `for`, enhanced `for`, and `while` for looping;
- `int[]` arrays along with `length` and indices starting from `0`;
- `break` and `continue` when there is a clear reason;
- methods with parameters, return types, `return`, and `void`.

A comprehensive checkpoint program, saved as **`BasicsCheckpoint.java`**:

~~~java
public class BasicsCheckpoint {

    static int sumPositive(int[] numbers) {
        int sum = 0;

        for (int value : numbers) {
            if (value <= 0) {
                continue;
            }
            sum += value;
        }

        return sum;
    }

    static int countPositive(int[] numbers) {
        int count = 0;

        for (int value : numbers) {
            if (value > 0) {
                count++;
            }
        }

        return count;
    }

    public static void main(String[] args) {
        int[] scores = {3, 0, 5, -1};

        int sum = sumPositive(scores);
        int count = countPositive(scores);
        double average = count == 0 ? 0.0 : (double) sum / count;

        System.out.println("Số phần tử dương: " + count);
        System.out.println("Tổng: " + sum);
        System.out.println("Trung bình: " + average);
    }
}
~~~

~~~bash
javac -encoding UTF-8 BasicsCheckpoint.java
java BasicsCheckpoint
~~~

Stdout:

~~~text
Số phần tử dương: 2
Tổng: 8
Trung bình: 4.0
~~~

Explanation: `sumPositive` and `countPositive` accept an `int[]` parameter, respectively summing and counting the elements greater than `0`. `(double) sum / count` makes the division produce a floating-point result. Before learning objects, try replacing the array with `{0, -2}` and explain why `count == 0` must be checked before the division. The example includes `0.0` to represent the case of having no positive elements according to the exercise rules; a real application might choose to return "no data" information instead of `0.0`.

### Methods Are the Building Blocks for Object Behavior

A method declaration has a return type, a name, a parameter list, and a method body:

~~~java
static int twice(int value) {
    return value * 2;
}
~~~

`static` in the example allows calling it directly from `main`. After learning class/object, you will write **instance methods** such as `wallet.deposit(amount)`; the main difference is that an instance method is attached to a specific object and can access instance state via `this`.

**Checkpoint:** You understand that parameters are used to receive data, `return` returns a result, and you know how to explain each conditional branch. If a method does too much work, try splitting it into two methods with clear responsibilities.

## 5. Stage 3 — Transitioning from Programming with Separate Variables to Classes and Objects

When handling an entity with multiple related pieces of data, using individual variables easily leaves information disconnected:

~~~java
String learnerName = "Mai";
int pagesRead = 12;
~~~

This is valid for a very small example. When an application needs to manage multiple readers, we want to group the closely associated data and the behavior controlling it into a class:

~~~java
class ReadingList {
    String owner;
    int pagesRead;

    void recordPages(int pages) {
        pagesRead += pages;
    }
}
~~~

The snippet above is only **class-illustration code**, not a standalone runnable console application. It helps identify:

- **`class`:** the general description of fields and methods.
- **Instance/object:** an individual entity created using `new ReadingList()`.
- **Field:** `owner` and `pagesRead` store the state of each instance.
- **Instance method:** `recordPages` represents behavior bound to an instance.
- **`this`:** inside an instance method, `this` refers to the object receiving the call.
- **The dot `.`:** `list.recordPages(5)` accesses behavior; `list.pagesRead` accesses the field if Java access rules permit it.

It is important to distinguish that "a class is a blueprint" is only an introductory analogy. An actual class also defines access scopes, constructors, type information, and language rules; and an object is not merely a copy of declaration lines.

## 6. Stage 4 — Constructors, Instance/Static, and Encapsulation

### Constructors Establish Initial State

A constructor has **the same name as the class** and **declares no return type**, not even `void`. It is invoked during initialization with `new`. For example:

~~~java
class ReadingList {
    private final String owner;
    private int pagesRead;

    ReadingList(String owner) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner is required");
        }
        this.owner = owner;
        this.pagesRead = 0;
    }

    void recordPages(int pages) {
        if (pages <= 0) {
            throw new IllegalArgumentException("pages must be positive");
        }
        pagesRead += pages;
    }

    int getPagesRead() {
        return pagesRead;
    }
}
~~~

This is an **illustrative class definition**, which will be incorporated into a complete runnable program in a later section.

Key points:

- `ReadingList(String owner)` is a one-parameter constructor. Because this constructor has been declared, the class does not automatically get a default no-argument constructor.
- `this.owner = owner` distinguishes the instance field (`this.owner`) from the parameter with the same name (`owner`).
- `private` prevents code outside the class from directly accessing the field; it still allows internal methods to read and modify it.
- `final` on the `owner` field requires assignment in accordance with Java initialization rules and disallows reassignment afterward via normal Java code.
- `recordPages` checks `pages > 0`; the number of pages read must not decrease due to negative input.
- `getPagesRead` only reads the field; not every field must have both a getter and a setter.
- If a developer wants an object to always start in a valid state, the constructor is an important place to validate inputs.

A brief way to distinguish them:

| Component | Belongs to Instance or Class? | Example |
| --- | --- | --- |
| Instance field | Specific to each object | `pagesRead` of each ReadingList |
| Instance method | Called on an object | `list.recordPages(5)` |
| `static` field | A class-level field, jointly referenced by instances per Java semantics | `ReadingList.createdCount` |
| `static` method | Called using the class name, without `this` | `ReadingList.totalCreated()` |
| Constructor | Executed when creating a new instance | `new ReadingList("Mai")` |

Do not use `static` for data specific to each object. If `pagesRead` is made static, instances can all observe a single shared value, contradicting the model of multiple independent reading lists.

### Encapsulation Protects Invariants

**Encapsulation** is managing access to data and placing valid operations alongside that data. An **invariant** is a condition that needs to be maintained across valid states, for example `pagesRead >= 0`.

You should not provide an arbitrary setter such as `setPagesRead(-999)` if the design does not allow negative numbers. Instead, provide a business-meaningful behavior `recordPages(pages)` and validate the parameter. This design helps reduce the number of places where state can become invalid.

Common access modifiers:

| Modifier | Basic Access Scope |
| --- | --- |
| `public` | Code that has access to the type/member under Java rules (including the module system if applicable) |
| `protected` | Same package and appropriate access from subclasses in another package |
| *No modifier written* (package-private) | Within the same package |
| `private` | Within the corresponding class/nest scope according to language rules |

At the introductory level, start with `private` fields and `public` methods when the API truly needs to be public. Later, delve into inheritance and complex access rules.

## 7. Stage 5 — Checking References, Object Identity, Null, and Parameter Passing

In this stage, the focus of the **learning roadmap** is confirming for yourself that you can read an object graph, rather than relearning the full definitions of `class` and `new`. Before moving on to the integration exercise in stage 6, use the `ReadingList` class from the previous stage to complete the following checks.

| Output Check | What You Must Be Able to Explain |
| --- | --- |
| `ReadingList a = new ReadingList("Mai"); ReadingList b = a;` | Both variables hold the same reference; the constructor is not called a second time |
| `ReadingList c = new ReadingList("Mai");` | Matching owner names do not mean the same instance |
| `b.recordPages(5)`, then read `a.getPagesRead()` | State changed through b is observed by a because of alias |
| `a == b` and `a == c` | `==` on references compares object identity, not contents |
| `b = c;`, then read via `a` | Reassigning variable b does not revert the state of object a |
| `ReadingList missing = null;` | There is no object to call an instance method on; null must be handled before access |
| `final ReadingList fixed = a;` | Variable fixed cannot be reassigned; the referenced object can still be mutable |

**Pass-by-value check:** write a method `static void update(ReadingList value)` that calls `value.recordPages(2)`, then assigns `value = new ReadingList("Khác")`. When called with `a`, the old object is increased by two pages, but the caller's variable a is **not** switched to the new object. Java copies the **reference value** into the parameter.

**Equality check:** compare with `String.equals` to check string content, and compare references with `==` if you need to know whether they are the **same instance**. `Object.equals` compares identity by default, whereas a class/record can define value equality differently. To clearly see that `==` does not always produce the desired value relationship, try two separate `new String("Java")` instances and compare `==` and `equals`. This is an experiment on reference equality; using `new String` is not recommended in regular business code.

**Passing criteria:** you do not need to memorize long definitions; you must be able to draw arrows between three variables and two objects, count the exact number of constructor calls, predict state changes, distinguish null from an object, and explain why reassigning a parameter does not change the variable in the caller. If you are unsure about a check, run a minimal example and compare; once mastered, proceed to stage 6.

## 8. Stage 6 — Complete Program Combining the Concepts

This example gathers the goals of the roadmap: class, two instances, constructor, `private` fields, input validation, instance methods, static method, alias, and reference comparison.

Create **`ClassObjectRoadmapDemo.java`**:

~~~java
public class ClassObjectRoadmapDemo {

    static final class ReadingList {
        private static int createdCount;

        private final String owner;
        private int pagesRead;

        ReadingList(String owner) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("owner is required");
            }
            this.owner = owner;
            this.pagesRead = 0;
            createdCount++;
        }

        void recordPages(int pages) {
            if (pages <= 0) {
                throw new IllegalArgumentException("pages must be positive");
            }
            pagesRead = Math.addExact(pagesRead, pages);
        }

        int getPagesRead() {
            return pagesRead;
        }

        String summary() {
            return owner + ": " + pagesRead + " pages";
        }

        static int totalCreated() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        ReadingList mai = new ReadingList("Mai");
        ReadingList alias = mai;
        ReadingList nam = new ReadingList("Nam");

        mai.recordPages(12);
        alias.recordPages(5);
        nam.recordPages(9);

        System.out.println(mai.summary());
        System.out.println(nam.summary());
        System.out.println("Cùng instance: " + (mai == alias));
        System.out.println("Khác instance: " + (mai == nam));
        System.out.println("Số đối tượng đã tạo: " + ReadingList.totalCreated());
    }
}
~~~

In the directory containing the file:

~~~bash
javac -encoding UTF-8 ClassObjectRoadmapDemo.java
java ClassObjectRoadmapDemo
~~~

Stdout:

~~~text
Mai: 17 pages
Nam: 9 pages
Cùng instance: true
Khác instance: false
Số đối tượng đã tạo: 2
~~~

### How Does Each Line Connect to the Concepts?

1. `static final class ReadingList` is a nested class declared inside the class containing `main`. This nested class is static, so it does not require an instance of the enclosing class. Using a nested class here allows the example to run in **a single file**; you can also use two top-level classes placed properly in source files.
2. `owner` and `pagesRead` are instance fields. Each ReadingList holds its own data, so Mai read 17 pages and Nam read 9 pages.
3. `createdCount` is a static field. Both constructor calls increment one shared counter variable. The example runs sequentially; this counter increment is not designed for concurrent access.
4. The constructor validates the name, assigns the `final` field, and sets `pagesRead = 0`. If the name is null or all whitespace, `IllegalArgumentException` is thrown before counting a valid object.
5. `recordPages` demonstrates behavior: accepting only positive page counts. `Math.addExact` detects `int` overflow by throwing `ArithmeticException` instead of silently recording an overflowed result.
6. `alias = mai` only copies the reference, so `mai.recordPages(12)` and `alias.recordPages(5)` update the same ReadingList.
7. `nam = new ReadingList("Nam")` creates a separate instance. It is not affected by operations via `mai` and `alias`.
8. `mai == alias` is `true`; `mai == nam` is `false`. Those values reflect object identity rather than names or page counts.
9. `ReadingList.totalCreated()` is a static method call on the class name to read shared data.

**Deliberate self-experimentation:** replace `alias.recordPages(5)` with `alias.recordPages(-5)` and explain why the program terminates with an exception; try replacing `"Mai"` with `""`; try changing `alias` to refer to `nam` before recording pages. Each change clarifies a specific rule.

## 9. Practice Exercises by Level and Passing Criteria

Do not just read the code and feel familiar with it. **Type it out from scratch yourself**, run it, and explain the output and the cause of any errors.

### Level 1 — Syntax and Methods

**Exercise:** Write `calculateTotal(int price, int quantity)` returning the total amount. If any parameter is negative, throw `IllegalArgumentException`.

**Passing criteria:** runs with `price = 25`, `quantity = 3` producing `75`; distinguishes between input parameters, local variables, and return value; explains why input is validated before calculating. You can use `Math.multiplyExact` if you want to detect overflow.

### Level 2 — Two Independent Objects

**Exercise:** Create a `Counter` class with a `private int value` field, a constructor receiving an initial number, an `increment()` method, and a `getValue()` method.

**Scenario:** Create `Counter left = new Counter(1)` and `Counter right = new Counter(1)`, and increment `left` twice. The result must be `left = 3`, `right = 1`.

**Passing criteria:** can explain why two objects can have the same initial value yet their states are not linked. If `value` is made `static`, you can explain why the design does not fit the problem.

### Level 3 — Valid State Validation

**Exercise:** Write `BankAccount` with `private long balance`, a constructor requiring a non-negative balance, `deposit(long amount)` accepting only positive numbers, and `withdraw(long amount)` rejecting withdrawals exceeding the balance.

**Passing criteria:** creates a valid object and updates state properly after three operations; tests negative amounts, zero, and withdrawing over the balance. No public API call path allows keeping a negative balance.

### Level 4 — References and Aliasing

**Exercise:** Create a `Counter a`, then `Counter b = a`; increment via `b` and read via `a`. Next, create `Counter c = new Counter(...)` with the same initial number as `a`.

**Passing criteria:** correctly predicts `a == b` and `a == c`; knows that `b = c` does not modify variable `a` or undo the previous increment.

### Level 5 — Two Collaborating Object Types

**Exercise:** Write a `Book` class holding `title` and a valid page count; and a `ReadingProgress` class holding a reference to `Book` and the number of pages read. The `read(int pages)` behavior does not allow the number of pages read to exceed the book's total pages.

**Passing criteria:** each class has clear responsibilities; constructors check conditions; creates two reading progress instances for the same `Book` and identifies which progress is independent and which object is being shared. Consider how sharing a mutable `Book` can affect the invariant of `ReadingProgress`.

### Level 6 — Self-Testing Small Programs

Use `if` and throw `AssertionError` to verify results, for instance placed inside `main`:

~~~java
if (mai.getPagesRead() != 17) {
    throw new AssertionError("Expected Mai to read 17 pages");
}
~~~

This is a basic check needing no additional libraries. When studying on a larger scale, you can move to JUnit to manage many test cases. Passing criteria are met when you can devise at least one normal case, one boundary case, and one invalid-input case for each update behavior.

## 10. Checklist Before Moving to Deeper Class & Object Knowledge

Use the following questions as exit criteria. Just keep practicing the exact areas where you are not sure yet; there is no need to wait until you have "finished learning all of Java".

| Self-Assessment Question | Sign of Mastery |
| --- | --- |
| Can I run a `.java` file on my own? | Create a file, run `javac`, `java`, and understand class name/file name errors |
| Can I distinguish primitive and reference types? | Explain how `int x = 2` differs from `Counter c = new Counter(2)` |
| Can I read `if`, loops, and methods? | Predict output, understand parameters and `return` |
| Do I know how a class differs from an instance? | Create two objects, each holding its own state |
| Can I use constructors and `this`? | Initialize properly, explain `this.field = parameter` |
| Do I know instance fields vs. static fields? | Choose the right place to store per-object or shared data |
| Do I know how to protect state? | `private` fields, behaviors that validate inputs, preserving invariants |
| Do I know what an alias is? | Explain why two variables can point to the same object |
| Can I distinguish `==` and `equals`? | Know how to compare reference identity and class-based value equality |
| Do I handle `null` at a basic level? | Avoid calling methods on null; check at input boundaries |
| Do I know what `final` restricts? | Do not confuse a final variable with an immutable object |
| Do I test my own code? | Have valid, boundary, and invalid cases; check values after operations |

If you can accomplish all of these items in programs you write yourself, you have a solid foundation to move on to more detailed lessons on object lifecycle, constructor overloading, class declarations, access levels, relationships between objects, and comparison rules.

## 11. Common Errors and Self-Diagnosis

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `class HelloJava is public, should be declared in a file named HelloJava.java` | File name does not match the public class name | Fix the file/class name pair properly, paying attention to case sensitivity |
| `cannot find symbol` | Wrong name, wrong scope, undeclared, or the class is not yet on the compilation path | Read the reported symbol name, and check the syntax and source files |
| `non-static variable ... cannot be referenced from a static context` | Using an instance field/method directly from a static method | Create an instance and access it through a reference variable, or reconsider the static design |
| `variable ... might not have been initialized` | Reading a local variable before the compiler confirms it has been assigned | Initialize it or ensure every branch before the read assigns a value |
| `NullPointerException` | Calling a method or using data from a null reference | Check where the data is created, input validation, and the reference lifecycle |
| Two variables change together unexpectedly | The two variables may be pointing to the same mutable object | Check reference assignments and methods that update state |
| Two objects have identical data, yet `==` is false | `==` on references compares identity | Choose an `equals` definition or compare business data when appropriate |
| Error when calling `new Class()` | The class only has parameterized constructors or the constructor is inaccessible | Check the constructor signature, modifier, and how it is instantiated |
| A setter allows an object to enter an invalid state | Missing invariant checks in constructors/methods | Restrict update paths, validate parameters and results |
| "Cannot run `main`" | Running the file name instead of the class name under the chosen workflow, or missing a suitable entry point | Verify `public static void main(String[] args)` and the run command |

From Java 11 onward, the `java` tool also supports running a single source file directly in certain situations (`java HelloJava.java`). Even so, while learning the fundamentals, separating `javac` and `java` helps you clearly understand which errors are compile-time errors and which are runtime errors.

## 12. What to Learn Next and What Can Wait

**Right after this roadmap lesson**, you should dive deeper into each class/object topic: class structure; constructors and overloading; instance fields/methods; `this`; access and encapsulation; reference relationships; state, behavior, identity; `Object` methods; value comparison; and designing objects with valid state. These items are interconnected: each time you encounter a new concept, return to the small class you wrote yourself to modify it and observe its behavior.

**Only after using classes/objects proficiently** should you dedicate a separate stage to inheritance and polymorphism, interfaces and abstract classes, advanced exceptions, collections/generics, lambdas, test frameworks, concurrency, Java modules, or Spring. Those topics build upon an understanding of instances, references, and methods; rushing ahead before clarifying the fundamentals often leads to code that works by accident but is hard to explain.

### How to Study for Long-Term Retention

1. **Read a concept → run a minimal example → modify one scenario yourself:** for example, after `new`, add a second object; after constructors, try an invalid input value.
2. **Predict before running:** write down the expected stdout, then check with the compiler and runtime. If it is wrong, explain the cause using concepts of state, reference, or scope.
3. **Draw reference relationships:** with `a`, `b`, and `c`, draw arrows to objects to understand aliases and independent instances.
4. **Ask questions at three levels:** does this data belong to the class or the instance? Which state does this method affect? Are two variables the same object or do they merely have equal values?
5. **Practice explaining in your own words:** if you can explain why `alias.recordPages(5)` changes the result when read through `mai`, the knowledge will be more useful than memorizing definitions.

**Expected outcome:** You will not only memorize `class` and `new` syntax, but also know how to create objects with valid state, design clear behaviors, choose instance/static in the right places, distinguish values from references, predict the effects of methods, and run and verify Java 17+ programs using multiple objects on your own.
