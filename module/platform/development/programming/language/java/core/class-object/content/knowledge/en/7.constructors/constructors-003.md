# The `new` Operator: Allocation, Initialization, and Receiving a Reference in Java

When you write:

~~~java
Student student = new Student("Mai", 20);
~~~

Java does not merely "call a function named Student". The expression `new Student("Mai", 20)` requests the creation of **a new instance of the `Student` class**, runs the initialization process according to Java rules, and then **produces a reference value** to the newly created object upon success. Finally, the `=` assignment stores that reference in the `student` variable.

To understand classes and objects, distinguish the actions that are often lumped together into one:

1. **Declaring a reference variable**: `Student student;` creates a variable of type `Student`, but **does not create a Student object by itself**.
2. **Instance creation expression**: `new Student("Mai", 20)` is a *class instance creation expression*. It performs the steps related to allocating and initializing the instance.
3. **Constructor**: `Student(String, int)` is the selected constructor; it participates in establishing a valid state for the instance, not a method returning type `Student`.
4. **Receiving and storing the reference**: when the `new` expression completes normally, the caller has a reference value; `student = ...` or another way of using the result determines how that reference is stored or used.

This article uses Java 17 or later and focuses on the lifecycle of creating an object with `new`, initialization order, the difference between an object and a reference, failure cases, and common mistakes in constructors.

## 1. Components of a `new` Expression

The basic syntax for creating an instance of a class:

~~~java
new ClassName(argument1, argument2)
~~~

Where:

- `new` is the operator/keyword that begins the instance creation expression.
- `ClassName` specifies the class type to create, for example `Student`, `BankAccount`, or `ArrayList<String>`.
- The expressions `argument1`, `argument2` are evaluated and then passed to the appropriate **constructor**.
- The result of the `new` expression upon success is a **non-null reference value** to the created instance.

Example:

~~~java
Student a;                    // Only declares the reference variable.
a = new Student("Mai", 20);   // Creates an instance, then assigns the reference to a.
Student b = a;                // Copies the reference; NO new Student.
Student c = new Student("Mai", 20); // Another instance.
~~~

This is an illustrative snippet; an appropriate `Student` class is required and it must be placed in a valid method or block.

You need to recognize three kinds of values:

| Expression | Creates a new Student? | Meaning |
| --- | --- | --- |
| `Student a;` | No | Declares a reference variable |
| `a = new Student("Mai", 20);` | Yes | Creates an instance, initializes it, and then assigns the reference |
| `Student b = a;` | No | Two variables reference the same object |
| `Student c = new Student("Mai", 20);` | Yes | Creates an independent object |
| `a = null;` | No | Assigns the special `null` reference value |
| `new Student("Mai", 20);` | Yes, if it completes normally | Creates an object without directly storing the reference in a variable from this expression |

When you see `new` appear in code, do not confuse the number of **reference variables** with the number of **objects**. One object can be referenced by multiple variables at the same time; conversely, one variable can be assigned references to different objects in turn.

## 2. First Example: Creating, Using, and Distinguishing Two Objects

Save the file **`FirstNewDemo.java`**:

~~~java
public class FirstNewDemo {
    static final class Student {
        private final String name;
        private int lessons;

        Student(String name, int lessons) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            if (lessons < 0) {
                throw new IllegalArgumentException("lessons must be >= 0");
            }
            this.name = name;
            this.lessons = lessons;
        }

        void completeLesson() {
            lessons++;
        }

        String describe() {
            return name + ": " + lessons + " lessons";
        }
    }

    public static void main(String[] args) {
        Student first = new Student("Mai", 2);
        Student alias = first;
        Student second = new Student("Mai", 2);

        alias.completeLesson();

        System.out.println(first.describe());
        System.out.println(second.describe());
        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == second: " + (first == second));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FirstNewDemo.java
java FirstNewDemo
~~~

Stdout:

~~~text
Mai: 3 lessons
Mai: 2 lessons
first == alias: true
first == second: false
~~~

Explanation:

- `new Student("Mai", 2)` is executed **twice**, creating two separate instances.
- The constructor checks the parameters and then assigns `name` and `lessons` to the **corresponding instance**.
- `Student alias = first;` does not use `new`; it only copies the reference value.
- `alias.completeLesson()` updates the shared object of `first` and `alias` to 3 lessons.
- The `second` object is created separately, so it still keeps 2 lessons.
- The `==` operator on two reference values checks whether they point to the same object. Two objects with equal fields **do not automatically** become one object.

In the example, the `Student` class is declared as a `static nested class` so that everything sits in a single standalone file. The word `static` in the nested class declaration **does not mean** all Student instances share the two fields `name`, `lessons`; they are still **instance fields**.

## 3. Logical Stages of `new Class(...)`

The class instance creation process can be visualized as follows:

~~~text
Caller code encounters the expression new Student(...)
                   |
                   v
Determine the class type and appropriate constructor
(checked at compile time; class must be ready at runtime)
                   |
                   v
Allocate space for the new instance;
set fields to their initial default values
                   |
                   v
Evaluate argument expressions in the specified order
and perform the call to the selected constructor
                   |
                   v
Execute the relevant initialization chain:
superclass -> field/initializer block -> constructor body
                   |
           +-------+-------------------+
           |                           |
        Success                 Exception/Error
           |                           |
           v                           v
new yields a reference    new does not return a reference
           |                   normally to the caller
           v
Caller assigns/stores/passes/uses the reference
~~~

This is a **logical model**, not a map of how the virtual machine allocates every byte or a JIT execution schedule. JVM mechanisms and optimizations may cause the actual memory layout to differ from the diagram, but the observable results must conform to Java's rules.

Some important milestones:

1. **Selecting the constructor:** the compiler relies on the types and number of arguments, overload rules, and access permissions to determine the appropriate constructor. A constructor is not chosen arbitrarily based on runtime values.
2. **Preparing the class:** the JVM must have an appropriate class definition; using `new` may trigger class initialization if the class has not yet been initialized. Static initialization is handled separately from the initialization of each instance.
3. **Allocating the instance:** the runtime needs to create a new instance with the corresponding fields. If resources are insufficient, an `OutOfMemoryError` may occur.
4. **Default values:** fields have initial default values before the explicit initialization steps associated with them run. Do not treat default values as an already valid business state.
5. **Evaluating arguments and running the constructor:** argument expressions may have side effects or throw exceptions; the constructor can also throw an exception. There is no guarantee that `new` will complete.
6. **Returning the reference:** after the entire process completes normally, the expression produces a reference to the newly created instance. **A constructor does not declare a return type**; that is a characteristic that differs from a method returning an object.
7. **Caller receives the result:** the assignment, method call, or enclosing expression is what determines how the reference is used.

Class initialization (`static`) only takes place when needed for a corresponding runtime class and according to the relevant rules; **it is not repeated every time `new` is used on the same class**. Conversely, instance field initializers and constructors run for **each new instance** according to the applicable initialization chain.

## 4. First, Distinguish Class Initialization from Instance Initialization

These two things have similar names, but their purposes are different.

### Class initialization

`static field initializer`s and `static initializer block`s belong to the runtime class, not to individual objects. In a simple program, when `new Example()` first triggers the initialization of `Example`, the static initialization steps of `Example` (and necessary superclasses) are run as specified.

~~~java
class Example {
    static int created = 0;

    static {
        System.out.println("Example static initialization");
    }

    Example() {
        created++;
    }
}
~~~

This is an illustrative class without `main` yet. If two objects are created consecutively after the class has already been initialized, the static block does not print twice; the constructor can increment `created` on **each `new`**.

In applications with custom class loaders, two classes with the same name defined by different class loaders can be two distinct runtime classes and have different static state. You should not state "static runs exactly once for all time" in absolute terms.

### Instance initialization

Each time a new instance is created, the initialization of the **instance fields**, **instance initializer blocks**, and **constructor** of the classes in the inheritance chain is performed in the order specified by Java.

~~~java
class Counter {
    private int value = 10;  // Instance field initializer.

    {
        System.out.println("Counter instance block");
    }

    Counter() {
        System.out.println("Counter constructor");
    }
}
~~~

Here, the field initializer and instance block are steps that create state **for a new Counter**. They are not static, so they are executed for each normal instance initialization.

## 5. Runnable Example: Order of Static, Superclass, Field, and Constructor

A concrete program helps avoid vague guesswork about the order:

Save **`InitializationOrderDemo.java`**:

~~~java
public class InitializationOrderDemo {
    static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    static class Base {
        static {
            System.out.println("Base static");
        }

        int baseValue = trace("Base field", 1);

        {
            System.out.println("Base block");
        }

        Base() {
            System.out.println("Base constructor");
        }
    }

    static final class Child extends Base {
        static {
            System.out.println("Child static");
        }

        int childValue = trace("Child field", 2);

        {
            System.out.println("Child block");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("main begin");

        Child first = new Child();
        System.out.println("second new");
        Child second = new Child();

        System.out.println("values="
                + first.baseValue + "," + second.childValue);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InitializationOrderDemo.java
java InitializationOrderDemo
~~~

Stdout:

~~~text
main begin
Base static
Child static
Base field
Base block
Base constructor
Child field
Child block
Child constructor
second new
Base field
Base block
Base constructor
Child field
Child block
Child constructor
values=1,2
~~~

The first `Child` creation:

1. `main` prints `main begin`.
2. The JVM initializes `Base` (static block) before `Child` in the proper superclass order, then the static block of `Child`.
3. The `Child` instance is initialized with the `Base` superclass part first: `Base field` → `Base block` → `Base constructor`.
4. Then the instance initializers of `Child` run: `Child field` → `Child block` → `Child constructor`.
5. `new Child()` completes and the `first` variable receives the reference.

The second `Child` creation:

- Static blocks **do not run again** because the classes have already been initialized.
- Each new instance still has to run the sequence **Base field, Base block, Base constructor, Child field, Child block, Child constructor**.
- `first` and `second` reference **two different objects**.

**Do not infer incorrectly:** `Base constructor` is not synonymous with creating an additional independent Base object. In the `new Child()` example, the superclass initialization step is **part of initializing a Child instance**, not creating a second Base instance to return to the caller.

## 6. Default Values Exist Before Explicit Assignment

Before instance initializers, an object's fields are assigned default values by type:

| Field type | Default value |
| --- | --- |
| `byte`, `short`, `int`, `long` | 0 of the corresponding type |
| `float`, `double` | 0.0 of the corresponding type |
| `char` | `'\\u0000'`, UTF-16 code unit equal to 0 |
| `boolean` | `false` |
| Reference types, e.g., `String`, `List<?>`, arrays | `null` |

Do not confuse the default values of fields with **local variables**: a local variable must be determined by the compiler to have been assigned before it is read; there is no rule that "a local int always defaults to 0".

### Example of Initialization in Textual Order

Save the file **`DefaultFieldDemo.java`**:

~~~java
public class DefaultFieldDemo {
    static final class Sample {
        int observed = this.value;
        int value = 7;

        Sample() {
            System.out.println("observed=" + observed);
            System.out.println("value=" + value);
        }
    }

    public static void main(String[] args) {
        new Sample();
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultFieldDemo.java
java DefaultFieldDemo
~~~

Stdout:

~~~text
observed=0
value=7
~~~

When `observed = this.value` runs, `value` has not yet received the explicit value `7`, so it is still the default value `0`. Afterward, the field initializer of `value` assigns `7`.

**Subtle point:** Using the simple name `int observed = value;` when `value` is an instance field declared later in the same class can cause an `illegal forward reference` error. Using `this.value` in the example above makes the expression valid under forward-reference rules, **but can introduce a logic bug**. You should not take advantage of this capability to write initializers that depend on fields that have not been set yet.

## 7. A Constructor Establishes Valid State, but Is Not a Method Returning an Object

A constructor has the same name as the class and **has no return type**:

~~~java
class Book {
    private final String title;

    Book(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        this.title = title;
    }
}
~~~

This is an illustrative class definition. The line `Book(String title)` is the constructor; `this.title = title` stores the parameter into the field of **the object being initialized**.

Common mistake:

~~~java
class Book {
    void Book(String title) {
        // This is a METHOD named Book, not a constructor.
    }
}
~~~

This class snippet is valid Java syntax if the method body is valid: because it has the `void` return type, it is merely a method named `Book`. If the class declares no constructors, the compiler can provide a no-argument default constructor according to Java rules. The `void Book(String)` method **does not run automatically** on `new Book()`.

### A Constructor Does Not Return a Reference with `return object;`

Do not write:

~~~java
Book(String title) {
    return new Book(title); // NOT valid in a constructor.
}
~~~

The snippet above is **an illustration of a compilation error**, not runnable code. A constructor can use `return;` without an expression to return early according to Java rules, but it cannot return an object like a method.

The reference is the result of **the `new Book(...)` expression when it succeeds**, not a value explicitly returned with `return` by the constructor.

If you want to create an object using a **method with a name expressing business intent**, you can use a static factory:

~~~java
static Book titled(String title) {
    return new Book(title);
}
~~~

This is an illustrative method placed in an appropriate context. Here, **the `titled` method returns `Book`** via `return` syntax; the `Book(String)` constructor itself still returns no value.

## 8. Constructor Chaining: `this(...)` and `super(...)`

A class can have multiple constructors with different signatures. In Java 17, a call to another constructor using `this(...)` or a superclass constructor using `super(...)` must be placed as **the first statement** in the constructor when it appears as an explicit constructor invocation.

- `this(...)` calls another constructor of **the same class**, without creating an additional new object.
- `super(...)` calls a constructor of the **superclass**, which is also an initialization step of the same object being constructed.
- If a constructor does not write `this(...)` or `super(...)`, the compiler normally inserts an implicit `super()` call, and the superclass must have an accessible no-argument constructor.
- A chain of `this(...)` calls must eventually lead to a constructor that calls `super(...)` or implicit `super()`; a recursive constructor cycle must not be formed.

Save the file **`ConstructorChainDemo.java`**:

~~~java
public class ConstructorChainDemo {
    static final class Ticket {
        private final String label;
        private final int quantity;

        Ticket() {
            this("DEFAULT");
            System.out.println("no-arg constructor");
        }

        Ticket(String label) {
            this(label, 1);
            System.out.println("one-arg constructor");
        }

        Ticket(String label, int quantity) {
            if (label == null || label.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid ticket");
            }

            this.label = label;
            this.quantity = quantity;
            System.out.println("two-arg constructor");
        }

        String describe() {
            return label + " x" + quantity;
        }
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket();
        System.out.println(ticket.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorChainDemo.java
java ConstructorChainDemo
~~~

Stdout:

~~~text
two-arg constructor
one-arg constructor
no-arg constructor
DEFAULT x1
~~~

Even though constructors are called through multiple levels of `this(...)`, the `new Ticket()` statement **creates only one Ticket instance**. The constructors participate in setting up **the same object**; when the chain completes, the `new` expression returns a reference to that object.

### When the Superclass Has No No-Argument Constructor

~~~java
class Base {
    Base(int id) {}
}

class Child extends Base {
    Child() {
        super(1);
    }
}
~~~

The class snippet above is valid. If you remove `super(1);` in `Child()` without replacing it with an appropriate call, Java 17 will try to use an implicit `super()`, but `Base` has no no-argument constructor, resulting in a compilation error.

The question to remember is not "does each constructor create a new object?" but rather "which constructor is called **to initialize the object of the current `new` expression**?".

## 9. Evaluating Arguments: Results Can Change Before the Constructor Body

A constructor invocation can accept argument expressions that contain method calls or side effects. Those argument expressions are evaluated **from left to right**. If an expression throws an exception, the selected constructor invocation may not have run its body.

Save **`ConstructorArgumentsDemo.java`**:

~~~java
public class ConstructorArgumentsDemo {
    static int argument(String label, int value) {
        System.out.println("arg " + label);
        return value;
    }

    static final class Pair {
        private final int left;
        private final int right;

        Pair(int left, int right) {
            System.out.println("constructor");
            this.left = left;
            this.right = right;
        }

        int sum() {
            return left + right;
        }
    }

    public static void main(String[] args) {
        System.out.println("before new");
        Pair pair = new Pair(
                argument("left", 2),
                argument("right", 3));

        System.out.println("sum=" + pair.sum());
        System.out.println("after new");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorArgumentsDemo.java
java ConstructorArgumentsDemo
~~~

Stdout:

~~~text
before new
arg left
arg right
constructor
sum=5
after new
~~~

What can be observed is:

1. The two argument expressions are evaluated **before the body of the `Pair` constructor is executed**.
2. `argument("left", 2)` runs before `argument("right", 3)`.
3. The constructor body prints `constructor`.
4. `pair` only receives the reference via assignment if the `new Pair(...)` expression completes normally.
5. Afterward, `pair.sum()` invokes an instance method on the new object.

Do not equate the log order above with all internal JVM steps. At the language level, allocation and execution steps are constrained by the specification; the JIT may optimize in ways that preserve the observable effects. As for writing code, the question is usually: **when the constructor body starts, have the arguments already been computed?** — yes, if the constructor body is actually entered along this path.

### When an Argument Throws an Exception

~~~java
static int fail() {
    throw new IllegalStateException("argument failed");
}

// In a method:
Pair pair = new Pair(1, fail());
~~~

This is an illustrative code fragment; `Pair` is the type from the example above in the same context, not a standalone program. Because `fail()` throws an exception while preparing the arguments, the body of `Pair(int, int)` **is not invoked** for that call. Nor is there a successful reference to assign to `pair`.

## 10. Initialization Failure: `new` Does Not Produce a Normal Result

A constructor can throw `IllegalArgumentException` when the input is invalid; an initializer or superclass constructor can also throw an exception. If the exception propagates out of the entire object creation process, the `new` expression **completes abruptly**, providing no normal reference to the caller.

Save the file **`FailedConstructionDemo.java`**:

~~~java
public class FailedConstructionDemo {
    static final class Account {
        private final int balance;

        Account(int balance) {
            System.out.println("constructor balance=" + balance);

            if (balance < 0) {
                throw new IllegalArgumentException("negative balance");
            }

            this.balance = balance;
            System.out.println("constructed");
        }

        int balance() {
            return balance;
        }
    }

    public static void main(String[] args) {
        Account account = null;

        try {
            account = new Account(-5);
            System.out.println("assigned");
        } catch (IllegalArgumentException ex) {
            System.out.println("caught: " + ex.getMessage());
        }

        System.out.println("account is null: " + (account == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FailedConstructionDemo.java
java FailedConstructionDemo
~~~

Stdout:

~~~text
constructor balance=-5
caught: negative balance
account is null: true
~~~

Here:

- The constructor started, but threw an exception **before completing**.
- The `this.balance = balance` line and `constructed` do not run.
- The `account = new Account(-5)` assignment does not complete because the right-hand side finishes abruptly.
- The `account` variable was initialized to `null` before `try` and **remains null** after `catch`.
- The `assigned` line is not executed.

**Do not over-conclude:** the object under construction may have already gone through part of the allocation/initialization process before the exception occurred. What is certain from the caller's perspective is that **the `new` expression does not return a reference via the normal completion path**. Side effects that already took place before the exception (printing logs, updating a static counter, writing external data...) are not automatically rolled back.

### If an Initializer or Static Initialization Fails

A static initializer can terminate with an exception; the JVM typically reports `ExceptionInInitializerError` when the appropriate cause occurs during class initialization. Subsequent uses of the class may encounter a follow-up error such as `NoClassDefFoundError` because the class is in a failed initialization state, depending on the context. This is an error of **runtime class initialization**, not because a constructor has a different `return` keyword.

Similarly, if an instance initializer or superclass constructor throws an exception, the constructor below it does not complete, and `new` does not return a normal reference. Instead of guessing that every problem during `new` is an "out of memory" error, read the **exception type, message, and stack trace**.

## 11. The Risk of Exposing `this` Before the Object Finishes Initializing

Inside a constructor, `this` represents the object being constructed. If you send `this` outside (registering a callback, adding it to a static collection, creating a thread and starting it immediately...), external code can observe an object that **has not finished its initialization process**, causing state or concurrency bugs.

Example to avoid (illustrative, not a standalone runnable program):

~~~java
class Registry {
    static Object last;
}

class UnsafePublication {
    private final String name;

    UnsafePublication(String name) {
        Registry.last = this; // Lets other code see the object too early.
        this.name = name;
    }
}
~~~

When `Registry.last = this` is executed, the `name` field has not yet been assigned the parameter. If another component accesses that object at that exact moment, it may observe a state that does not satisfy the class's invariant. In a multithreaded environment, the publication and visibility rules of the Java Memory Model must also be considered.

Principles to prevent this:

- Finish setting up state in the constructor before publishing the reference.
- Avoid calling from a constructor an instance method that can be overridden and then depend on an uninitialized subclass field.
- Do not start a thread from a constructor if the thread can run and use `this` before initialization finishes.
- Use a static factory when a multi-step object creation process is needed and only return the object after configuration is complete.

Note: merely writing `private final` on a field does not automatically guarantee safety if `this` has been improperly published before the constructor finishes; the object lifecycle must be designed carefully.

## 12. Why Should You Not Call an Overridable Method from a Constructor?

In Java, an overridden instance method can dispatch based on the **runtime type** of the object even while the superclass constructor is running. Meanwhile, fields/initializers of the subclass may **not have finished initializing yet**, leading to unexpected default values.

Save **`OverrideDuringConstructionDemo.java`**:

~~~java
public class OverrideDuringConstructionDemo {
    static class Base {
        Base() {
            System.out.println("Base constructor");
            describe();
        }

        void describe() {
            System.out.println("Base describe");
        }
    }

    static final class Child extends Base {
        private String label = "ready";

        Child() {
            System.out.println("Child constructor");
        }

        @Override
        void describe() {
            System.out.println("Child label=" + label);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.describe();
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverrideDuringConstructionDemo.java
java OverrideDuringConstructionDemo
~~~

Stdout:

~~~text
Base constructor
Child label=null
Child constructor
Child label=ready
~~~

Explanation:

1. `new Child()` starts initializing an object of runtime type `Child`.
2. The superclass constructor `Base()` runs before `Child`'s initializer `label = "ready"` runs.
3. `Base()` calls `describe()`. Because this is an overridable instance method, dynamic dispatch selects **`Child.describe()`**.
4. At that moment, `Child.label` is still its default value `null`.
5. After the superclass constructor completes, `Child`'s initializer assigns `label = "ready"`, and the Child constructor runs.
6. The `child.describe()` call from `main` after initialization prints `Child label=ready`.

This code pattern **runs to illustrate the risk**, not as a recommended design. If a constructor needs internal operations, use an appropriate `private`/`static` helper, or structure the initialization process so that it does not call overridable methods before the subclass is ready.

## 13. `new` Produces a Reference, but the Caller Does Not Necessarily Store It

Valid ways to use a `new` result:

~~~java
Student a = new Student("Mai", 1);       // Store in a local variable.
Student b;
b = new Student("Nam", 2);               // Assign after declaration.
someMethod(new Student("Lan", 3));       // Pass directly as an argument.
new Student("An", 4).completeLesson();   // Call a method directly on the new result.
~~~

These are **illustrative code fragments**; an appropriate `Student` class and `someMethod` are required. A `new` expression does not have to appear after an `=` sign.

On the fourth line, an object is created and the `completeLesson()` method runs on that object, but the code does not directly keep the reference in a variable. That does not guarantee the object is garbage collected immediately after the statement; the object could be referenced elsewhere if the constructor/method passed it outside, and the JVM decides when to reclaim it according to GC semantics.

### The Result of `new` Can Be Returned Directly

~~~java
static Student createStudent(String name) {
    return new Student(name, 0);
}
~~~

This is an **illustrative method**. The `return` statement belongs to **the `createStudent` method**, not to the constructor. If the caller writes `Student student = createStudent("Mai");`, the reference from the `new` expression is passed through the method's return value and then assigned to `student`.

### Difference Between `new` and Assignment

~~~java
Student first = new Student("Mai", 1);
Student second = first;
first = new Student("Nam", 2);
~~~

After the three lines:

~~~text
first  --------> Student #2 { name = "Nam", lessons = 2 }
second --------> Student #1 { name = "Mai", lessons = 1 }
~~~

The third line **does not update object #1 to Nam**; it creates Student #2 and replaces **the reference value** of the `first` variable. `second` still holds object #1. That is why you must distinguish **assigning a reference** from **modifying a field on an object**.

## 14. `new`, `null`, and Object Accessibility

`null` is a special reference value that points to no object. The declaration:

~~~java
Student student = null;
~~~

does not create a Student instance. Before assigning a valid reference, calling `student.completeLesson()` will throw `NullPointerException`.

Conversely, if the `new Student(...)` expression **completes normally**, the result of the class instance creation expression is a reference to the new instance, not null. However, **a variable assigned from a factory method** can receive null if the method is designed to return null; this differs from the `new` expression itself.

### Comparing with `==`

For two references of compatible types:

- `a == b` is `true` if both point to the same object, or both are null.
- `a == b` is `false` if they point to two different objects, even when the internal data is equal.
- `a == null` checks whether the reference points to no object.

`equals` is a method with its own contract: a class can define **value-based equality** logic. Do not use `equals` to prove two variables share the same identity unless the equals contract of the class truly is identity, like the default `Object.equals`.

### Variable Names Are Not Memory Addresses

The "variable points to object" diagram is a useful model, but Java does not expose an object's memory address through normal reference assignment. You do not need to and should not use `System.identityHashCode(object)` to infer an address: this hash value is not a physical address and is not guaranteed to be unique for every object.

## 15. `new` with Arrays Differs from `new` with Classes

Java also uses `new` to create **array objects**:

~~~java
int[] numbers = new int[3];
String[] names = new String[2];
int[] values = new int[] {4, 5, 6};
~~~

These are **array creation expressions**:

- `new int[3]` creates an array of length 3 whose `int` elements default to 0.
- `new String[2]` creates an array of length 2 whose `String` reference elements default to null.
- `new int[] {4, 5, 6}` creates a three-element array with the specified values.
- An array creation expression does not invoke a constructor declared by the learner like `new Student(...)`.

Save the file **`NewArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class NewArrayDemo {
    public static void main(String[] args) {
        int[] numbers = new int[3];
        String[] names = new String[2];

        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("names=" + Arrays.toString(names));

        numbers[1] = 8;
        System.out.println("updated=" + Arrays.toString(numbers));

        int[] alias = numbers;
        System.out.println("same array=" + (alias == numbers));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NewArrayDemo.java
java NewArrayDemo
~~~

Stdout:

~~~text
numbers=[0, 0, 0]
names=[null, null]
updated=[0, 8, 0]
same array=true
~~~

An array is a **reference type**, so `alias = numbers` copies a reference to **the same array object** without automatically copying the elements. You can create a new array and copy its contents with `Arrays.copyOf` when needed; that is an explicit behavior different from merely assigning a reference.

### Invalid Array Size

`new int[-1]` is a syntactically valid expression, but will throw `NegativeArraySizeException` at runtime. An excessively large size can also fail due to memory resources or JVM limits. You must distinguish **array initialization errors** from class constructor errors, even though both use the `new` keyword.

## 16. Choosing an Instantiable Type: Class, Abstract Class, and Interface

Not every reference type can appear directly after `new` to create an instance of that type itself.

Valid:

~~~java
java.util.ArrayList<String> names = new java.util.ArrayList<>();
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

These two examples are **code fragments**, not standalone programs. Note:

- `new ArrayList<>()` creates a concrete instance; `<>` is the **diamond operator**, allowing the compiler to infer the appropriate type arguments in context.
- `new Runnable() { ... }` is the syntax for creating an instance of an **anonymous class** implementing `Runnable`; it does not directly create an object whose runtime type is the `Runnable` interface.
- You cannot write `new Runnable()` without an anonymous class body because an interface has no constructor to create an instance directly.

Invalid examples:

~~~java
abstract class Shape {}

// new Shape();    // Cannot directly instantiate an abstract class.
// new Runnable(); // Cannot directly instantiate an interface.
~~~

When a generic type variable does not yet have an appropriate concrete runtime type, you cannot simply write `new T()` inside a generic class/method just because `<T>` is declared. Instead, you can accept a factory, `Supplier<T>`, or an object already created by the caller. This is a limitation of generic semantics and erasure, not that "new does not support generics".

### Constructors Cannot Be Called Like Regular Methods

~~~java
Student s = new Student("Mai", 1);
// s.Student("Nam", 2); // Invalid: a constructor is not a method.
~~~

To change the data of an existing object, design a valid instance method or create a **new object** with `new`; do not "re-run the constructor" using method syntax to reinitialize an existing object.

## 17. Compilation and Runtime Errors Around `new`

| Symptom | Cause | How to Handle |
| --- | --- | --- |
| `cannot find symbol` when writing `new Student(...)` | Class name is not declared/imported properly or wrong package | Check the name, import/package, and compiled files |
| `constructor Student ... cannot be applied to given types` | Number/types of arguments do not match any constructor | Match the signature, types, and overloads |
| `Student() has private access` | Constructor has an access modifier that does not allow the caller to use it | Use a factory/creation mechanism exposed by the class |
| `no suitable constructor found` | No applicable constructor found for the arguments | Check required parameters and type conversions |
| `reference to Student is ambiguous` | Multiple overloaded constructors apply and the most specific one cannot be chosen | Clarify argument types, especially when passing null |
| `constructor ... is already defined` | Two constructors declared with the same signature | Change the parameter structure or factory name |
| `constructor ... cannot be applied ... required: ... found: no arguments` | Class has parameterized constructor(s), but caller wrote `new Class()` | Pass all required arguments or design an additional constructor |
| `cannot instantiate abstract class` | Used `new` directly on an abstract type | Create a concrete subclass |
| `OutOfMemoryError` | Runtime lacks sufficient memory/resources for allocation | Check object count, data, reference retention lifecycle, and memory limits |
| `IllegalArgumentException` in constructor | Data violates rules defined by the constructor | Validate and pass valid data |
| `NullPointerException` after variable declaration | The variable is null or another intermediate reference is improperly null | Identify where the object is created/assigned and check values |
| `NoClassDefFoundError` / initialization error | JVM cannot load or initialize the class in context | Read the cause and stack trace; check classpath and static initializers |
| Result on the new object differs from expectations | Fields initialized in the wrong order, constructor omitted an assignment, or shadowing occurred | Use `this.field` and check the initializer/constructor chain |
| Two variables change together | Two variables hold the same reference instead of having two independent `new` calls | Draw an alias diagram and identify where instances are created |

**Do not fix errors by adding an empty constructor to every class**. If an object requires a mandatory `id` or `name` to be valid, a no-argument constructor can allow invalid state to be created. You must prioritize the data contract over getting the compiler to accept a short syntax.

## 18. Constructor Design Rules When Using `new`

A good constructor should bring an object to a valid and predictable state upon success. Practical guidelines:

1. **Define invariants from the start:** what properties must the object have? For example, `price >= 0`, `name` non-null/non-blank.
2. **Validate parameters before modifying state or calling external services** when feasible. A constructor throwing an exception can leave behind external side effects, so do not use a constructor as the place to perform hard-to-reverse transactions.
3. **Use `this.field = parameter`** when names collide; avoid the `field = field` mistake of self-assigning the parameter.
4. **Do not publish `this` too early**, especially via listeners, static holders, and threads.
5. **Avoid calling overridable methods inside a constructor** because subclass fields may not have been initialized yet.
6. **Do not perform heavy tasks or complex I/O with an unclear contract** in a constructor if preparing and running the task can be separated.
7. **Use `final` for fields that are truly assigned only once**, while understanding that a `final` field referencing a mutable object does not automatically make that object immutable.
8. **Do not accidentally make mutable shared state static.** A static field is fundamentally different from an instance field, even though both can appear in a class with constructors.
9. **Use constructor overloading intentionally**, delegating with `this(...)` to avoid duplicating validation and divergent initialization approaches.
10. **Use a static factory/builder when object creation requires many expressive steps**, while understanding that inside the factory there can still be `new` and constructor calls as appropriate.

A result type may be an immutable value object, a mutable service, or a resource object; these kinds have different initialization needs. There is no single constructor pattern that applies optimally to every class.

## 19. Practice Exercises

### Exercise 1 — Count Objects, Not Variables

~~~java
Student a = new Student("A", 0);
Student b = a;
Student c = new Student("A", 0);
a = c;
~~~

There are **two** `new Student(...)` calls, creating two Student instances if both complete successfully. In the end, `a` and `c` both point to the second object; `b` points to the first object. Write the expected results of `a == b`, `a == c`, `b == c`: **false**, **true**, **false**, respectively.

### Exercise 2 — Predict Constructor Chaining

In `ConstructorChainDemo`, change `new Ticket()` to `new Ticket("VIP")`. Predict the stdout:

~~~text
two-arg constructor
one-arg constructor
VIP x1
~~~

Because the no-argument constructor is not called in this creation. Both constructors `Ticket(String)` and `Ticket(String, int)` still set up **one object**.

### Exercise 3 — Initializer Order

Based on `InitializationOrderDemo`, add two new field initializers to `Child` and an instance block between them. Predict the log positions. Run `new Child()` twice and prove that the static block only appears during class initialization, whereas the instance initializers appear for each object.

### Exercise 4 — Constructor Throwing an Exception

Change `new Account(-5)` to `new Account(0)` in `FailedConstructionDemo`. Predict what the constructor will print:

~~~text
constructor balance=0
constructed
assigned
account is null: false
~~~

If `balance = -5`, the assignment does not complete and the variable remains null. Explain the exact condition that causes the constructor to reject the object.

### Exercise 5 — Arrays and Instances Are Different

Create:

~~~java
int[] counts = new int[2];
Student[] students = new Student[2];
~~~

A `students` array initially consisting of two **null elements** is not equivalent to already having two Student objects. Only when you write `students[0] = new Student("A", 0);` is there a Student instance in the first element; the second element remains null until a valid reference is assigned.

### Exercise 6 — Analyzing an Anti-Pattern

Read `OverrideDuringConstructionDemo` and explain why the first `describe()` call prints `null`. Propose a refactoring so that the superclass constructor does not call an overridable method and only uses `label` after the object has finished initializing.

### Exercise 7 — Reference Returned from a Factory

Create a static factory:

~~~java
static Student newBeginner(String name) {
    return new Student(name, 0);
}
~~~

In the caller, write `Student s = newBeginner("Mai");`. Point out: where is the object created? Does the constructor return a Student? Does the factory method return a reference? Answer: **the object is created by the `new` expression inside the factory; the constructor returns no value; the factory method returns the reference produced by the `new` expression upon success**.

## 20. Mastery Checklist

- [ ] I can distinguish `Student x;` from `new Student(...)`.
- [ ] I can explain that `new` only provides a reference to the caller when it completes normally.
- [ ] I can accurately identify a constructor and know that a constructor **has no return type**.
- [ ] I know that constructor arguments are evaluated before the constructor body runs.
- [ ] I can distinguish class/static initialization from instance initialization.
- [ ] I can predict the sequence superclass → instance initializer → constructor when creating a subclass.
- [ ] I know that `this(...)` and `super(...)` are constructor calls within **the same process of creating one object**, and do not by themselves create a second object.
- [ ] I understand the default values of instance fields before explicit initialization steps.
- [ ] I know that a constructor throwing an exception prevents the `new` expression from returning a reference normally, and the assignment may not occur.
- [ ] I know that two variables can share an object, and two separate `new` calls create two different instances.
- [ ] I can distinguish `new Class(...)` and `new int[n]` regarding constructors and element initialization.
- [ ] I know that `new` does not directly create an instance of an interface/abstract class.
- [ ] I do not treat `System.identityHashCode` as a memory address.
- [ ] I avoid publishing `this` early and avoid calling overridable methods in a constructor.
- [ ] I can compile, run, and accurately explain the stdout of the Java 17+ programs in this article on my own.

**Summary:** The `new` operator ties the concepts **allocation → initialization → receiving a reference** together into a single object creation expression. A constructor is a step in the initialization process, not a method returning an object. After the `new` expression succeeds, Java gives the caller a **reference value** that can be assigned to a variable, passed to a method, or used immediately. Understanding these three steps clearly is the foundation for understanding object state, aliasing, constructor chaining, inheritance, initialization errors, and object lifecycle in Java.
