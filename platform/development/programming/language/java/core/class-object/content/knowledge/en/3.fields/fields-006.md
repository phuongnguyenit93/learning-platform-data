# Name Scope, Lifetime, and Name Shadowing/Hiding in Java Fields

When a Java class has multiple fields, parameters, and local variables, the same name such as `count` can appear in multiple places. Which variable will the code `count = count + 1` affect? Why can `this.count` and `super.count` yield two different values? After a method finishes, does the object's field disappear? These are issues of **scope**, **lifetime**, and **shadowing/hiding**.

This lesson focuses on **class fields**, while using local variables, parameters, and inheritance to clarify the name resolution mechanism. The examples run on Java 17 and later, except for snippets explicitly marked as *compile-time error examples*.

Objectives:

1. Determine from which source code locations a field's name can be used.
2. Distinguish between *a name being in scope* and *an object/value still existing at runtime*.
3. Recognize that an instance field and a `static` field exist under different conditions.
4. Accurately predict when a parameter or local variable shadows a field; use `this.field` when needed.
5. Distinguish **field hiding** in inheritance from **method overriding**; know the effect of `super.field`.
6. Understand the limits of predicting garbage collection (GC), avoiding inferring that a variable leaving a block immediately frees the object.

## 1. Three Concepts Easily Mistaken for One

| Concept | Actual Question | Primarily Determined By |
| --- | --- | --- |
| **Scope** | At which locations in the source code can a simple name like `balance` be referenced? | Declaration structure, blocks, classes, packages, and the language's name resolution rules |
| **Accessibility** | Is code at that location allowed to access the member? | `private`, `protected`, package-private, `public`, inheritance/module rules |
| **Lifetime** | During execution, until when does a variable, field, or object remain meaningful/existent? | Method invocations, instance lifecycle, class initialization, whether it can still be referenced |
| **Shadowing/hiding** | If multiple declarations use the same name, which declaration does an unqualified name denote? | Name resolution rules, declaration order, class relationships, and inheritance |

**Important example:** A `private int count` field still **exists in the object** after a method that was just called finishes, even though that method's local variable `count` is no longer used in that invocation. A `static` field can continue to exist after all instances of the class are no longer used. Conversely, a name can be in scope from a source-code perspective but be shadowed by a closer declaration.

Scope is a **static** property of the source code; lifetime is a **runtime** matter. Accessibility is a separate condition: seeing a name in the class structure does not automatically grant permission to read every `private` field of another class.

## 2. Scope of Instance Fields and Static Fields

A **field** is a variable declared directly in the body of a class or interface according to Java rules, as opposed to a variable declared inside a method/constructor/block body.

~~~java
class CourseProgress {
    private String courseName;  // instance field
    private int lessonsDone;     // instance field
    private static int instances; // static field

    CourseProgress(String courseName) {
        this.courseName = courseName;
        instances++;
    }

    void completeLesson() {
        lessonsDone++;
    }
}
~~~

This is an **illustrative class snippet**; a complete runnable example appears later.

- `courseName` and `lessonsDone` belong to **each instance** of `CourseProgress`. Two objects can have different values.
- `instances` is a `static` field belonging to the corresponding class within the class loader context; all regular instances share a single `instances` field of that class.
- The scope of the simple name of a field declared in a class includes the class body according to the language rules, with exceptions regarding **forward references in initializers** and shadowed names.
- An instance method can reference an instance field using an unqualified name (`lessonsDone`) or `this.lessonsDone`.
- Inside a static method, there is no `this`; to read an instance field, you need a reference to an instance, such as `progress.lessonsDone`, and access conditions must be satisfied.
- A `private` field of `CourseProgress` cannot be read directly from an independent class outside its valid access scope. Public/package-private methods can provide the necessary behavior or data.

### Scope from the Point of Declaration and Execution Order

Inside a class, members can be declared before or after the methods that use them:

~~~java
class DeferredField {
    int read() {
        return number;
    }

    private int number = 7;
}
~~~

This class snippet is valid: the name `number` in `read()` resolves to the field even though the field declaration is placed below the method. This rule does **not** mean every use of a field before its declaration line is valid: initializers have forward reference restrictions, which will be analyzed in section 9.

### Fields Are Members, Not Local Variables

In the example:

~~~java
class Sample {
    int field = 1;

    void work(int parameter) {
        int local = 2;
        if (parameter > 0) {
            int insideBlock = 3;
            field += local + insideBlock;
        }
        // insideBlock is no longer in scope here
    }
}
~~~

`field` is a member storing instance state. `parameter` is only present during the call to `work`. `local` is a local variable in the method block; `insideBlock` is declared only inside the `if` block. Code after the block cannot use the name `insideBlock` because **it is out of scope**, not because an object field has just disappeared on its own.

## 3. Lifetime of Instance Fields

When executing `new CourseProgress("Java")`, Java creates an instance and allocates the instance fields that the object needs. During initialization, fields receive **default values** before the relevant field initializers and constructors run in the specified initialization order.

| Field Type | Default Value Before Explicit Initialization |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` of the corresponding type |
| `float`, `double` | `0.0` of the corresponding type |
| `char` | the null character `'\\u0000'` |
| `boolean` | `false` |
| Reference types such as `String`, `CourseProgress`, arrays | `null` |

These default values do not replace the responsibility of initializing valid data; for example, `null` may not be a permitted state for a course name.

**Instance fields semantically exist along with the instance**; they are not cleared simply because a method using them finishes. Subsequent method calls can accurately read the updated state of the object if the same instance is still used.

~~~text
Create object with new
       |
       v
Instance fields are set up
       |
       v
Call method A -> modifies field
       |
       v
Method A returns
       |
       v
Call method B -> can still read new field value
       |
       v
Object is no longer needed/no longer reachable per JVM rules
       |
       v
Garbage collector may reclaim memory in the future
~~~

**Do not predict GC timing:** Java does not guarantee that an object is reclaimed immediately when a variable goes out of scope, right when a method returns, or right after assigning a reference to `null`. The JVM may optimize and determine that an object is no longer needed earlier than what we would infer from variable names; at the same time, an object may still be referenced through multiple different paths. Write programs based on behavior and correctness, not on GC timing.

### Reference Variables and Objects Have Different Lifecycles

~~~java
CourseProgress first = new CourseProgress("Java");
CourseProgress alias = first;
~~~

`first` and `alias` are **two reference variables**, yet they point to **the same object**. When `first`'s scope ends, the object does not automatically disappear if `alias` or another reference path still holds it.

~~~text
first ------\
             > CourseProgress object { courseName: "Java", ... }
alias ------/
~~~

The arrows represent a model of reference relationships, not an actual memory address diagram. An object's liveness is evaluated based on reachability/execution needs, not on a single variable name.

### `final` Does Not Automatically Make an Object Immutable

`final CourseProgress progress = new CourseProgress("Java");` prevents the variable `progress` from being assigned another reference after initialization according to Java rules. However, if `completeLesson()` is permitted to modify `lessonsDone`, calling `progress.completeLesson()` is still valid. Having `final` on a reference variable neither shortens nor extends an object's lifetime according to a simple rule, and does not automatically freeze mutable fields of the referenced object.

## 4. Lifetime of Static Fields

A `static` field is associated with the class when the class is prepared/initialized and is maintained as part of that class's runtime state, rather than being tied to individual instances. For example, two `CourseProgress` objects share a single `instances` field within the same class context.

Distinction:

| | Instance field | Static field |
| --- | --- | --- |
| Belongs to | Each individual object | The class defined/loaded by the JVM in the corresponding context |
| Number of data copies | One field value per instance | One class-level field per corresponding runtime class |
| Appropriate access | `object.field`, `this.field` inside an instance | `ClassName.field` |
| When no instances remain | The instance field disappears with the object when the object is reclaimed | The static field can still exist as long as the class is retained by the runtime |
| Effect of modification | Typically affects only that instance | All code accessing the same runtime class can see the same static field |

For example, accessing `CourseProgress.instances` from code **outside** the class in the previous snippet is invalid because that field is `private`. To read it, provide an appropriate `static` method, such as `totalCreated()`, or test directly inside the class. **Access modifiers remain in effect** even when the field is static.

A static field does not necessarily live until the entire JVM shuts down in every application: a class can be unloaded when class loader collection conditions and runtime factors align; plugin systems or servers that load classes repeatedly are examples to watch out for. For small console applications using the application class loader, static state can be viewed as existing while the class remains in use during the run, though that is a simplified learning model rather than a guarantee that “static lives forever”.

If a static field holds a reference to an object, this reference can help keep the object reachable. For example, storing a list of objects in a long-lived static collection can prevent memory from being freed as intended. Proactively manage long-lived references when an application requires specific resource lifecycles.

**Note:** A static field is not thread-safe simply because it is static. Operations like `counter++` can suffer from race conditions if multiple threads update it concurrently without proper synchronization mechanisms.

## 5. Comparing Scope and Lifetime Through a Complete Java 17+ Program

Save the file **`ScopeLifetimeDemo.java`** in UTF-8:

~~~java
public class ScopeLifetimeDemo {
    static final class Meter {
        private static int createdCount = 0;

        private final String name;
        private int reading = 0;

        Meter(String name) {
            this.name = name;
            createdCount++;
        }

        void add(int amount) {
            int oldReading = reading;
            reading = oldReading + amount;

            if (amount > 0) {
                String event = "increased";
                System.out.println(name + " " + event + " by " + amount);
            }
            // event is not in scope here.
        }

        int reading() {
            return reading;
        }

        static int createdCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        Meter first = new Meter("A");
        Meter second = new Meter("B");

        first.add(3);
        first.add(2);
        second.add(7);

        System.out.println("A: " + first.reading());
        System.out.println("B: " + second.reading());
        System.out.println("Created: " + Meter.createdCount());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ScopeLifetimeDemo.java
java ScopeLifetimeDemo
~~~

Stdout:

~~~text
A increased by 3
A increased by 2
B increased by 7
A: 5
B: 7
Created: 2
~~~

Explanation by data kind:

1. `first` and `second` are local variables in `main`; they hold two references to two different `Meter` objects.
2. `name` and `reading` are instance fields. Each Meter has its own data; after three calls to `add`, Meter A has `reading = 5`, Meter B has `reading = 7`.
3. `oldReading` is a new local variable in each call to `add`. The previous call finishing does not cause the field `reading` to lose its value.
4. `event` can only be used inside the `if` block; code outside the block is not permitted to reference this name.
5. `createdCount` is a static field of `Meter`, incremented once each time the constructor runs, and has the value 2 after creating two objects.
6. `name` is a `final` field that cannot be reassigned after normal initialization, whereas `reading` is a mutable field. This distinction is independent of whether a field is an instance or static field.

If the statement `System.out.println(event);` is added outside the `if` block, the program **does not compile** because the name `event` cannot be found in scope. Conversely, the statement `System.out.println(reading);` inside the instance method `add` is valid because the field `reading` remains within the class's scope.

## 6. Shadowing: Parameters or Local Variables Shadowing Fields

**Shadowing** occurs when a declaration in a closer scope causes a simple name that could otherwise denote another declaration to denote the new declaration. A very common case is a constructor parameter having the same name as an instance field.

~~~java
class Account {
    private String owner;

    Account(String owner) {
        this.owner = owner;
    }
}
~~~

Inside the constructor, the two occurrences of `owner` do not refer to the same variable:

- `owner` **without a prefix** on the right side of the assignment is the **parameter** `owner`.
- `this.owner` on the left side is the **field** `owner` of the current object.
- If you write `owner = owner;`, both names refer to the parameter; the statement assigns the parameter to itself, the field is not updated, and it may remain `null`.

`this` is a reference to the current instance in an appropriate instance context. In a static method, there is no `this`, so a field cannot be resolved using `this.field`.

### Complete Example: The Name `value` in Three Locations

Create the file **`FieldShadowingDemo.java`**:

~~~java
public class FieldShadowingDemo {
    static final class Counter {
        private int value = 10;

        Counter(int value) {
            this.value = value;
        }

        void add(int value) {
            int before = this.value;
            this.value = before + value;
            System.out.println("Parameter: " + value);
            System.out.println("Field: " + this.value);
        }

        void printNames() {
            int value = 99;
            System.out.println("Local: " + value);
            System.out.println("Field: " + this.value);

            if (value > 0) {
                String message = "positive";
                System.out.println("Block: " + message);
            }
        }

        int current() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(5);
        counter.add(3);
        counter.printNames();
        System.out.println("Result: " + counter.current());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FieldShadowingDemo.java
java FieldShadowingDemo
~~~

Stdout:

~~~text
Parameter: 3
Field: 8
Local: 99
Field: 8
Block: positive
Result: 8
~~~

Key points to note:

1. In the constructor, the parameter `value` shadows the field of the same name. `this.value = value` assigns the value 5 to the field.
2. In `add(int value)`, the unprefixed `value` is the parameter 3; `this.value` is the field currently holding 5, which is then updated to 8.
3. In `printNames()`, the local variable `int value = 99` shadows the field, so `value` yields 99 while `this.value` yields 8.
4. `message` is only in scope inside the `if` block.
5. In `current()`, there is no parameter or local variable named `value`, so `return value;` directly reads the field.

**Shadowing does not delete the field.** The field still resides in the object, can still be accessed via `this.value`, and retains its value after `printNames()` finishes.

### Not Every Duplicate-Name Declaration Is Permitted

In Java, declaring two local variables or duplicating a parameter with the same name in **overlapping nested scopes** within the same method is not allowed. The following example **intentionally does not compile**:

~~~java
void invalid(int count) {
    if (count > 0) {
        int count = 2; // Error: variable name duplicates parameter in an overlapping scope.
    }
}
~~~

Another situation is also invalid:

~~~java
void invalidAgain() {
    int count = 1;
    {
        int count = 2; // Error: cannot redeclare local variable in a nested block.
    }
}
~~~

These two snippets are **error illustrations** and must not be combined into the standalone runnable examples above. By contrast, a local variable/parameter **is allowed to shadow a class field**, because the two kinds of declarations follow different naming rules. Do not infer that Java allows nested local variables to shadow any local variable as some other languages do.

### Local Variables with the Same Name in Two Disjoint Blocks

~~~java
void separateBlocks(boolean flag) {
    if (flag) {
        int score = 1;
        System.out.println(score);
    } else {
        int score = 2;
        System.out.println(score);
    }
}
~~~

This is an **illustrative method snippet** that can be placed inside a class. The two `score` variables reside in two non-overlapping blocks, so this is valid. If there is also a field named `score`, the simple name inside each block will denote the local variable currently in effect.

## 7. Shadowing Differs from Field Hiding in Inheritance

When a subclass declares a field with the same name as a field inherited from its superclass, the subclass field **hides** the superclass field where applicable. This is commonly referred to as **field hiding**. The two fields remain two separate members; a subclass does not override a field using the polymorphic mechanism of methods.

**Two rules must be kept separate:**

- Field access such as `reference.label` is resolved based on the **declared type (compile-time type)** of the reference expression and the access/hiding rules.
- Calling an overridden instance method such as `reference.describe()` is generally selected based on the object's **runtime type** (dynamic dispatch), after the compiler determines the callable method signature.

Create **`FieldHidingDemo.java`**:

~~~java
public class FieldHidingDemo {
    static class Parent {
        String label = "parent";

        String describe() {
            return "Parent.describe";
        }
    }

    static class Child extends Parent {
        String label = "child";

        @Override
        String describe() {
            return "Child.describe";
        }

        void printBothFields() {
            System.out.println("this.label: " + this.label);
            System.out.println("super.label: " + super.label);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Parent parentView = child;

        System.out.println("child.label: " + child.label);
        System.out.println("parentView.label: " + parentView.label);
        System.out.println("child.describe(): " + child.describe());
        System.out.println("parentView.describe(): " + parentView.describe());
        child.printBothFields();
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FieldHidingDemo.java
java FieldHidingDemo
~~~

Stdout:

~~~text
child.label: child
parentView.label: parent
child.describe(): Child.describe
parentView.describe(): Child.describe
this.label: child
super.label: parent
~~~

The same `Child` object is referenced through the variable `child` of type `Child` and the variable `parentView` of type `Parent`. When reading `child.label`, the compiler selects the field belonging to `Child`; when reading `parentView.label`, it selects the field belonging to `Parent`. Changing the declared type of the reference affects **field access** without altering the runtime object.

Inside `Child`:

- `this.label` refers to the `Child.label` field.
- `super.label` refers to the `Parent.label` field.
- `describe()` is an **overridden** instance method. Both `child.describe()` and `parentView.describe()` execute the `Child.describe()` version.

This is an important difference between fields and methods in Java. **Fields are not overridden via dynamic dispatch.** When using the same field name in a superclass and a subclass, consider renaming or restricting the field to `private` and providing appropriate methods to avoid confusion.

### Access Rules Still Apply

In the example, `Parent.label` has package-private access, and `Child` is declared within the same package/nested class scope, so the access statement is valid. If `Parent.label` is changed to `private` in another design, a typical subclass is not permitted to read it directly via `super.label`; it must use the API provided by the superclass.

Inheritance does not break the `private` rule. At the same time, Java also has rules allowing classes belonging to the same *nest* to access each other's private members; this differs from the access rights of an independent subclass.

### `static` Fields Can Also Be Hidden

In inheritance, a `static` field in a subclass with the same name as an applicable field in the superclass can hide the superclass field, and is likewise selected based on the class name/reference type in the expression. To keep code clear, access static fields using the **declaring class name** such as `Parent.category` or `Child.category`, rather than accessing them through an object variable.

You cannot declare a static field and an instance field **with the same name in the very same class** and treat them as two separate fields. Allowing duplicate field names across **two classes in an inheritance hierarchy** differs from the naming rules within the same class body.

## 8. Nested Classes and Distinguishing `this` from `Outer.this`

An inner class can have a field with the same name as a field of its enclosing class. In that case, `this.field` inside the inner class refers to the inner object's field; `Outer.this.field` refers to the enclosing instance's field.

Create **`NestedNameDemo.java`**:

~~~java
public class NestedNameDemo {
    private String label = "outer";

    class Inner {
        private String label = "inner";

        void show(String label) {
            System.out.println("Parameter: " + label);
            System.out.println("Inner: " + this.label);
            System.out.println("Outer: " + NestedNameDemo.this.label);
        }
    }

    public static void main(String[] args) {
        NestedNameDemo outer = new NestedNameDemo();
        NestedNameDemo.Inner inner = outer.new Inner();
        inner.show("argument");
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedNameDemo.java
java NestedNameDemo
~~~

Stdout:

~~~text
Parameter: argument
Inner: inner
Outer: outer
~~~

In `show(String label)`, the simple name `label` refers to the parameter; `this.label` refers to the field of `Inner`; `NestedNameDemo.this.label` refers to the field of `NestedNameDemo` enclosing the inner object.

**Do not use `Outer.this` inside a static nested class** to refer to an instance of the outer class: a static nested class is not automatically associated with an enclosing instance the way a non-static inner class is. When a problem does not require an enclosing instance relationship, a static nested class is usually clearer and simpler.

## 9. Forward References and Field Initialization Timing

A field's scope within a class does not mean you can freely **read it by its simple name before its declaration line in a field initializer**. Java enforces an *illegal forward reference* rule to reduce declaration-order dependency bugs.

The following snippet **intentionally does not compile**:

~~~java
class InvalidForwardReference {
    int first = second; // illegal forward reference
    int second = 10;
}
~~~

In `first`'s initializer, the name `second` is written unqualified and refers to an instance field declared later. In this situation, the compiler reports `illegal forward reference`. The rule also has specific details for static fields, instance fields, initializer blocks, simple-name references, and positions on the left-hand side of an assignment; do not oversimplify this as “you cannot refer to any field declared later”.

An example that is **valid yet prone to logic bugs**:

~~~java
class QualifiedForwardReference {
    int first = this.second;
    int second = 10;
}
~~~

At the time the `first` initializer runs, `second` is still at its default value `0`. The expression `this.second` is a qualified reference, so it is valid in this case; only afterwards does `second`'s initializer assign 10. Therefore, a new instance has `first == 0` and `second == 10`. **Syntactic validity does not mean design soundness.**

For a standalone runnable example to verify this, save **`InitializationOrderDemo.java`**:

~~~java
public class InitializationOrderDemo {
    static final class Pair {
        int first = this.second;
        int second = 10;

        int first() {
            return first;
        }

        int second() {
            return second;
        }
    }

    public static void main(String[] args) {
        Pair pair = new Pair();
        System.out.println("first=" + pair.first());
        System.out.println("second=" + pair.second());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InitializationOrderDemo.java
java InitializationOrderDemo
~~~

Stdout:

~~~text
first=0
second=10
~~~

A good design should avoid reading a field before it has been intentionally initialized. Place field initializers in an easy-to-follow order, or explicitly perform interdependent state initialization inside the constructor.

### Static Initializer, Instance Initializer, and Constructor

The initialization sequence in Java includes details regarding superclasses, static initialization, instance field initializers, instance initializer blocks, and constructors:

1. When a class needs to be initialized according to JVM rules, its static field initializers and static initializer blocks are executed in their textual order, following the appropriate superclass initialization steps.
2. When creating an instance, the object's fields first receive default values; then superclass-related initialization and the instance initialization/constructor steps are executed according to Java rules.
3. Within the same class, instance field initializers and instance initializer blocks are executed in the order they appear in source code, at the appropriate point in the constructor execution.
4. The constructor finally completes the state. If a constructor calls an overridable method before the subclass finishes initializing, that method may observe subclass fields at their default values — a design pattern to avoid.

When studying “scope”, you must distinguish **initialization order** from **name scope**. Just because the compiler can determine which field is referenced does not guarantee that the field already holds its intended design value at the time it is read.

## 10. Name Scope Does Not Determine When Resources Are Released

Do not rely on the intuition “leaving curly braces = everything inside is immediately destroyed”.

Consider an illustrative snippet placed inside a method:

~~~java
CourseProgress saved;

{
    CourseProgress temporary = new CourseProgress("Core");
    saved = temporary;
}

// The name temporary has gone out of scope.
// The object is still referenced via saved.
~~~

The local variable `temporary` goes out of scope after the closing brace `}`. However, the object it referenced can still be accessed via `saved`. For a valid Java program, the compiler checks that `saved` has been assigned before being read; this example assigns `saved` inside the block before using it.

Similarly, a method that creates an object and **returns its reference** to the caller can allow the object to remain in use after the method finishes:

~~~java
static CourseProgress createProgress() {
    CourseProgress local = new CourseProgress("Java");
    return local;
}
~~~

This is an illustrative method snippet that requires a suitable `CourseProgress` class in the program. `local` is a local variable and goes out of scope after the method ends, yet the object can be retained by the caller via the return value.

### Off-Heap Resources Must Be Closed Explicitly

An object no longer being referenced does not mean an operating system file, socket, or connection is closed at the moment you expect. For resources implementing `AutoCloseable`, use **try-with-resources** to close them appropriately for the operation's lifecycle:

~~~java
// Illustrative snippet, placed in a method declaring throws IOException:
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

This example requires a variable `path` of type `java.nio.file.Path`, as well as handling or declaring `IOException`; it is not a standalone program. Its purpose is to distinguish **ending the scope of a variable name** from **closing a finite resource**. Detailed I/O topics should be studied in the Java I/O section; here, simply remember that GC does not replace intentional resource closing.

## 11. Captured Variables and `effectively final`: A Notable Scope Boundary

Local classes, anonymous classes, and lambdas can use certain local variables from an enclosing scope if those variables are **final or effectively final**. “Effectively final” means the variable is never reassigned after being assigned a value according to the compiler's analysis rules.

Standalone runnable example—save **`CaptureScopeDemo.java`**:

~~~java
public class CaptureScopeDemo {
    private int base = 10;

    Runnable makeTask() {
        int bonus = 3; // Effectively final

        return () -> {
            System.out.println(base + bonus);
        };
    }

    public static void main(String[] args) {
        CaptureScopeDemo demo = new CaptureScopeDemo();
        Runnable task = demo.makeTask();
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 CaptureScopeDemo.java
java CaptureScopeDemo
~~~

Stdout:

~~~text
13
~~~

After `makeTask()` returns, `bonus` no longer has a local name accessible to caller code. However, the lambda can still use the **captured value** of `bonus`. At the same time, the lambda can reference the field `base` through the enclosing instance captured as needed. Do not conclude that a local variable must continue living in a stack frame as it did while the method was running; the compiler/runtime may represent captured values differently while still preserving Java semantics.

If you add `bonus++;` after its declaration, the example above will fail to compile because `bonus` is no longer effectively final. For the field `base`, Java does not apply an analogous effectively final rule; a field can be mutable, so a lambda using a field can observe updated values of the object at runtime.

## 12. Name Resolution Rules in Code Review: Looking from Closest Outward

When you see a simple name like `value`, do not rush to assume it is a field. Check according to the context:

1. Within the expression, is there a parameter/local variable declaration named `value` currently in effect? If so, the simple name usually refers to that nearby declaration.
2. If not, does the current class have a field `value`? The name can denote an instance/static field depending on context and shadowing rules.
3. If not, a field inherited from a superclass or an accessible field from an enclosing class may be involved.
4. If you need to read the exact field of the **current instance**, use `this.value` in an instance context.
5. If you need the **superclass** field, use `super.value` in an appropriate context with proper access.
6. If you need a static field, prefer `ClassName.value` so readers know it is class-level state.
7. If the name is shadowed by another declaration but a field of another object is the target, use `object.value` when that field is accessible.
8. If the compiler reports an error, read the specific message before changing modifiers or adding `static` arbitrarily.

Java's detailed rules also involve interactions with type names, local classes, imports, and inheritance. For this lesson on fields, the practical approach is to **locate the exact declaration**, check its scope and accessibility, and then explicitly indicate the object/class that owns that field.

### Naming Practices to Help Prevent Unintended Shadowing

- Use descriptive field names indicating their role, such as `remainingSeats`, `customerName`, `createdCount`.
- Use `this.field = field;` consistently in constructors when parameters match field names; this is a common and clear Java idiom.
- Use `ClassName.staticField` instead of `instance.staticField`.
- Avoid declaring a subclass field with the same name as a superclass field unless there is a clear design reason.
- In long methods, limit reusing the same variable name for multiple meanings, even when the compiler permits it in non-overlapping blocks.
- Do not use `private`/getters/setters merely to silence warnings; instead, determine who needs read access and who needs permission to mutate state.

## 13. Common Errors and Misconceptions

| Symptom / Statement | Cause or Accurate Understanding |
| --- | --- |
| Constructor runs but the field remains `null` | You may have written `name = name;`, assigning the parameter to itself instead of `this.name = name;`. |
| `non-static variable ... cannot be referenced from a static context` | Accessing an instance field through a class or from a static context without an instance. |
| `cannot find symbol` when using a variable after `}` | The local variable name is no longer in that scope. |
| `variable ... is already defined` | Duplicate local/parameter declaration in overlapping scopes; Java does not allow this form of shadowing. |
| `illegal forward reference` | Reading a field by its simple name from an initializer before its declaration line in a prohibited case. |
| `parentRef.field` differs from `childRef.field` even for the same object | Field hiding: the compiler selects the field based on the declared reference type. |
| `parentRef.method()` calls subclass code | Instance methods are overridden and dynamically dispatched; this mechanism differs from fields. |
| “A local variable went out of scope so the object is destroyed immediately” | Leaving a name's scope does not guarantee object reclamation; the object may still be reachable, and GC has no fixed schedule. |
| “A static field belongs to the first object” | A static field belongs to the runtime class, not specifically to the first object. |
| “A `final` field makes the entire object immutable” | `final` does not automatically guarantee immutability of all referenced data. |
| “A field name is declared after a method, so the method cannot read it” | A method body can reference a field declared later; forward references in initializers are a different case. |
| “`System.gc()` will reclaim the object immediately” | This is only a request/hint to the JVM; it cannot be relied on as a guarantee of reclamation timing. |

## 14. Comprehension Exercises

### Exercise 1: One Name, Two Variables

Given the illustrative class snippet:

~~~java
class Box {
    int size = 4;

    void setSize(int size) {
        size = size;
    }
}
~~~

If you create `Box b = new Box();`, call `b.setSize(9)`, and then read `b.size` where access is allowed, the result is still **4**. Both occurrences of `size` in `size = size;` refer to the **parameter**, while the field has not been updated. Fix it to `this.size = size;` and predict the new result as **9**.

### Exercise 2: Block Scope

~~~java
class BlockExample {
    int points = 1;

    void run(boolean active) {
        if (active) {
            int points = 10;
            System.out.println(points);
        }
        System.out.println(points);
    }
}
~~~

This is an **illustrative class**, requiring a call site for the method to run. With `run(true)`, the two printed lines are:

~~~text
10
1
~~~

The print inside the block uses the local `points`; the print after the block uses the field `points`. The field does not change. With `run(false)`, only one line `1` is printed.

### Exercise 3: Field Hiding vs. Method Overriding

Based on `FieldHidingDemo`, replace `Parent parentView = child;` with `Child childView = child;` and then read `childView.label`. It produces **`child`** because the reference type is `Child`; creating a new reference variable does not create a new object. With the valid cast `((Parent) child).label`, the result is **`parent`**, even though the runtime object is still Child.

### Exercise 4: Reasoning About Lifetime

~~~java
class Container {
    static Object shared;

    static void save() {
        Object local = new Object();
        shared = local;
    }
}
~~~

After `save()` returns, the local name `local` is no longer in scope, yet the created object can still be referenced through `Container.shared`. If `Container.shared = null` is set, the object **may** become unreachable if there are no other reference paths; there is no guarantee of immediate reclamation. This exercise is about references and object liveness, not how to request GC.

### Exercise 5: Adding a Check to a Program

In `FieldShadowingDemo`, add the following lines at the end of `main`:

~~~java
if (counter.current() != 8) {
    throw new AssertionError("Field value must be 8");
}
~~~

That is an **additional snippet**, not a separate file. If there are no errors, the statement prints nothing. Next, intentionally change the constructor from `this.value = value;` to `value = value;`; the field value then starts from 10 and has 3 added to become 13, causing the check to throw `AssertionError`. This is a way to observe a shadowing bug yourself by checking expected state.

## 15. Checklist for Applying to Real-World Classes

- [ ] Distinguish between fields, parameters, and local variables simply by declaration location.
- [ ] Know that an instance field still belongs to the object after a method finishes; a local variable does not become a field.
- [ ] Know that a static field is data belonging to the runtime class, not specifically to each individual object.
- [ ] Do not equate “going out of scope” with “the object is immediately garbage-collected”.
- [ ] Know that a parameter or local variable can shadow a field, and use `this.field` when needed.
- [ ] Know that Java forbids duplicate local/parameter names when scopes overlap.
- [ ] Know why `this.field`, `super.field`, and `ClassName.staticField` can differ.
- [ ] Explain that field hiding selects based on the expression type, whereas method overriding generally dispatches based on the runtime object.
- [ ] Distinguish a field's scope inside a class from forward reference restrictions in field initializers.
- [ ] Identify which class or object actually owns the state being read or updated.
- [ ] Compile and run `ScopeLifetimeDemo`, `FieldShadowingDemo`, `FieldHidingDemo`, `NestedNameDemo`, and `InitializationOrderDemo` yourself.
- [ ] Write constructors yourself that avoid the `field = field` bug and predict the outcome before running the program.

A useful practical rule when reading any expression containing a field is to answer in order: **“Which declaration does this name resolve to? Which object or class does this field belong to? When is the value created and when can it change?”**. Those three answers resolve most bugs involving scope, lifetime, and name shadowing/hiding in Java.
