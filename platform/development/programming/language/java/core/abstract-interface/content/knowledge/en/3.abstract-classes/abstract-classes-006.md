# `static`, `final`, and `private` Members in Abstract Classes (Java 17+)

## 1. Context and Objectives

In Java, an `abstract class` is a class that cannot be instantiated directly with `new`. It typically holds shared state and behavior, and can also declare abstract methods for subclasses to implement. **An abstract class still has all standard members**: fields, methods with bodies, constructors, initializer blocks, and nested classes. The three keywords `static`, `final`, and `private` still apply according to Java's general rules, but how they combine with `abstract` must be understood precisely.

After this lesson, you will be able to:
- Identify whether a member belongs to the class or the object, which members may be overridden, and which members are for internal use only.
- Explain why `static abstract`, `final abstract`, and `private abstract` are invalid.
- Design abstract classes with encapsulated state, fixed processing steps, and extension points for subclasses.
- Distinguish **method hiding** in `static` methods from **overriding** in instance methods.

Opening example:

~~~java
abstract class Document {
    private final String title;
    private static int created;

    protected Document(String title) {
        this.title = title;
        created++;
    }

    public final String title() {
        return title;
    }

    public static int createdCount() {
        return created;
    }

    public abstract String render();
}
~~~

`Document` does not define `render()`, so it is an abstract class. However, `title`, `created`, the constructor, `title()`, and `createdCount()` are all valid. A concrete subclass must implement `render()` (or else declare itself `abstract`).

## 2. Quick Rules Table

| Declaration in `abstract class` | Valid? | Meaning |
| --- | --- | --- |
| `static` field/method | Yes | Member bound to the declaring class, not to each instance. |
| `final` field | Yes | Variable can only be assigned once according to definite assignment rules. |
| `final` instance method with a body | Yes | Subclasses cannot override this method. |
| `private` field/method with a body | Yes | Accessible only within Java's `private` scope; does not create an override contract for subclasses. |
| `private static final` field | Yes | Common declaration for internal constants or references. |
| `private final` method with a body | Yes | Valid, though `final` is usually redundant because `private` methods cannot be overridden anyway. |
| `abstract` instance method (without a body) | Yes | Concrete subclasses must provide the missing implementation; conflicting modifier combinations are consolidated in the lesson on `abstract` and `final`. |

The "Yes" and "No" columns refer to syntax and language rules; which combination **should** be used also depends on design.

## 3. `static`: Members Belonging to the Abstract Class

### 3.1. `static` Fields Are Shared State

A `static` field is bound to the declaring class. If `Document` has `private static int created`, each time `Document`'s constructor is invoked via a subclass constructor, `Document`'s `created` variable is incremented. Instances of different subclasses still share **a single `Document.created` field**. This field is not recreated separately for each object.

Access should clearly indicate the owning class: `Document.createdCount()` rather than calling a `static` method through an object reference. If multiple threads concurrently increment a `static int` variable, the `++` operation is not automatically safe for concurrency; synchronization or `AtomicInteger` may be needed, depending on the problem.

### 3.2. `static` Methods Do Not Override

A `static` method can be declared in an abstract class and called without creating an instance of the abstract class itself: `Document.createdCount()`. This method **cannot be marked `abstract`**. A subclass can declare a `static` method with a matching signature to *hide* the superclass method; method selection is based on the compile-time type, not on the actual runtime type of the object.

`@Override` cannot be used on a `static` method, and a `static` method cannot replace an instance method with the same signature through inheritance (or vice versa).

### 3.3. Initialization Notes

A `static` field is initialized when the corresponding class is initialized according to JVM rules; instance constructors are a separate matter. A `static final` field can receive its value at its declaration or in a `static` initializer block, as long as it satisfies the single-assignment rule. Do not assume that every `static final` field is a compile-time constant: `static final int LIMIT = 10` can be a *constant variable*, whereas `static final Object LOCK = new Object()` is not.

## 4. `final`: Controlling Variable Assignment, Overriding, and Inheritance

### 4.1. `final` Instance Fields

`private final String title` must be assigned properly before the constructor completes; for a *blank final instance field*, normal initialization paths must ensure the variable is assigned exactly once. Because of this, subclasses cannot reassign this field after initialization.

However, **`final` locks the reference; it does not make the referenced object immutable**:

~~~java
import java.util.ArrayList;
import java.util.List;

abstract class TaggedItem {
    private final List<String> tags = new ArrayList<>();

    public void addTag(String tag) {
        tags.add(tag); // Valid: modifies the contents of the List.
    }

    public List<String> tags() {
        return List.copyOf(tags); // Returns an unmodifiable copy.
    }
}
~~~

`tags = new ArrayList<>()` again in an instance method will be a compile-time error, whereas `tags.add(...)` is valid. If true immutability is required, the design must control both content mutability and reference exposure.

### 4.2. `final` Methods

An instance method with a body marked `final` cannot be overridden by subclasses. This is a tool for keeping a common workflow fixed—for example, `execute()` performing input validation, logging, or calling extensible steps. A `final` method can still **call** an `abstract` method: the fixed skeleton is decided by the superclass; the varying details are implemented by subclasses. This is an idea close to *Template Method*.

An `abstract` method has no body and needs to be implemented by subclasses, so `abstract final` is invalid. A `static final` method with a body is also valid; in this case, `final` forbids subclasses from hiding the `static` method with a matching signature.

### 4.3. `final` on Classes

An `abstract class Base` can have a subclass `final class Concrete extends Base`. The subclass `Concrete` cannot be extended further, yet it still validly inherits from `Base`. Conversely, **a class cannot be both `abstract` and `final`**.

## 5. `private`: Encapsulation in Abstract Classes

`private` typically protects internal invariants such as the count of created objects, validated data, or helper methods that should not become part of the API for subclasses.

- **`private` fields**: subclasses cannot access them directly by field name; instead, use constructors and appropriate `protected`/`public` methods to maintain invariants. You should not make a field `protected` just to avoid writing an API.
- **`private` methods with a body**: used internally by the declaring class, and can be either instance or `static`. These methods are not inherited for overriding; a method with the same name and parameters in a subclass is a separate method of its own, not an override.
- **`private abstract` methods**: invalid because a subclass cannot fulfill an override contract to which it has no access.
- **`private` constructors**: an `abstract` class can syntactically declare a `private` constructor, but ordinary subclasses outside the enclosing class cannot invoke that constructor. Typically, a `protected` constructor or a constructor with an appropriate access level is used to allow controlled inheritance.

`private` and `final` answer two different questions: "Who has access?" and "Can it be overridden/reassigned?". For example, a `private final` field is both hidden from external code and assignable only according to `final` rules. For a `private final` method, `final` adds little value because overriding already does not apply.

## 6. Runnable Example: Combining All Three Keywords

Save the entire snippet below as **`TaskDemo.java`**. The code consists of an abstract class, a concrete subclass, and a class containing `main`; they reside in the same file, and only `TaskDemo` is `public`.

~~~java
abstract class Task {
    private static int createdCount = 0;
    private static final String PREFIX = "[task] ";
    private final String name;

    protected Task(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
        createdCount++;
    }

    public static int totalCreated() {
        return createdCount;
    }

    public final String getName() {
        return name;
    }

    private String displayLabel() {
        return PREFIX + getName();
    }

    public final void execute() {
        System.out.println(displayLabel() + ": " + doWork());
    }

    protected abstract String doWork();
}

final class PrintTask extends Task {
    public PrintTask(String name) {
        super(name);
    }

    @Override
    protected String doWork() {
        return "xong";
    }
}

public class TaskDemo {
    public static void main(String[] args) {
        Task first = new PrintTask("Alpha");
        Task second = new PrintTask("Beta");

        System.out.println(Task.totalCreated());
        first.execute();
        second.execute();
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 TaskDemo.java
java TaskDemo
~~~

Expected output:

~~~text
2
[task] Alpha: xong
[task] Beta: xong
~~~

Execution flow explanation:
1. `new PrintTask(...)` calls `super(name)`. `Task`'s constructor stores `name` via the `private final` field and increments `private static createdCount`. After two creations, the counter equals `2`.
2. `Task.totalCreated()` reads class-level data without needing to access the `private` field from outside.
3. `execute()` is a `final` instance method, so `PrintTask` cannot change its order of operations. This method calls the helper `private displayLabel()` and then calls `doWork()`.
4. `doWork()` is `protected abstract`; at runtime, calls on `first` and `second` resolve to the `PrintTask.doWork()` implementation. The result `"xong"` is printed.
5. `PrintTask` is `final`, yet it is still allowed to extend `Task`. The system can add **another subclass of `Task`** if a different behavior is desired.

This is a useful organizational pattern when you need to enforce that all tasks follow a common processing framework while still allowing specialized steps to vary.

## 7. Runnable Example: How Do Hiding (`static`) and Overriding (`abstract`) Differ?

Save as **`BindingDemo.java`**:

~~~java
abstract class Animal {
    public static String category() {
        return "Animal";
    }

    public abstract String sound();
}

class Cat extends Animal {
    public static String category() {
        return "Cat";
    }

    @Override
    public String sound() {
        return "meow";
    }
}

public class BindingDemo {
    public static void main(String[] args) {
        Animal pet = new Cat();

        System.out.println(Animal.category());
        System.out.println(Cat.category());
        System.out.println(pet.category()); // Valid, but this calling style should be avoided.
        System.out.println(pet.sound());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BindingDemo.java
java BindingDemo
~~~

Expected output:

~~~text
Animal
Cat
Animal
meow
~~~

In `pet.category()`, the **declared** type of the variable `pet` is `Animal`, so the compiler selects `Animal.category()`. This is hiding, not polymorphism. In `pet.sound()`, the JVM uses the actual object type `Cat` to select the overridden instance method, so the result is `meow`. Writing `Animal.category()` or `Cat.category()` makes the intent clearer and avoids confusion.

## 8. Common Compilation Errors

Combinations such as `abstract final class`, `static abstract`, `private abstract`, and `final abstract` are errors to watch out for; the full matrix, including differences between top-level and member classes as well as `sealed` modifiers, is consolidated in the lesson on `abstract`/`final` conflicts. The remainder of this lesson illustrates the distinct behaviors of `final`, `private`, and `static`, such as overriding, member access, and mutable state.

## 9. Design Choices

| Need | Recommended Usage | Reason |
| --- | --- | --- |
| Per-object state assigned at initialization | `private final` field | Preserves reference/value immutability and restricts direct modification. |
| Internal class constant | `private static final` field | Represents a shared value and avoids exposing implementation details. |
| Counting or managing shared state | `private static` field, explicit access API | Prevents subclasses from arbitrarily modifying shared state; consider thread safety. |
| Helper method used only by the superclass | `private` method | Reduces API surface area and unnecessary coupling with subclasses. |
| Workflow that subclasses must not alter | `public/protected final` instance method | Keeps the execution skeleton consistent. |
| Step that must be implemented by subclasses | `protected/public abstract` instance method | Creates a valid polymorphic contract. |
| Final implementation class, preventing further inheritance | `final class Concrete extends AbstractBase` | Locks down extension of the concrete class. |

Do not mark a method `static` when you want its behavior to depend on the actual type of the object. Do not mechanically use `protected` to expose data; consider behavioral APIs instead. Do not rely on `final` as a guarantee of thread safety: an object can still hold mutable state, and a shared `static` variable can still suffer from race conditions.

## 10. Self-Check

1. **Can you call a `static` method of an `abstract` class without creating an instance?** Yes; for example, `Task.totalCreated()`. Calling the method does not mean you can do `new Task()`.
2. **Why is `private abstract` invalid?** Because subclasses cannot override a `private` method; the abstract contract would be impossible to fulfill.
3. **Why can a `final` instance method still call an `abstract` method?** Because `final` only forbids overriding the `final` method itself; the internal call to the abstract hook is still dynamically dispatched to the subclass.
4. **Is a `private static final List<?>` immutable?** Only the field reference cannot be reassigned; the elements or the list itself can still change if the object allows it and code has an appropriate access path.
5. **Which method does `Animal pet = new Cat(); pet.category()` invoke?** `Animal.category()`, because `category()` is `static` and selection is based on the compile-time type of the expression. `pet.sound()`, on the other hand, invokes `Cat.sound()` because it is an overridden instance method.

**Key takeaway:** `static` defines class-level members and does not participate in overriding; `final` restricts reassignment or overriding; `private` restricts access and excludes methods from the override contract. In an abstract class, this trio works well alongside a few `protected abstract` methods to create an encapsulated design with controlled extensibility.
