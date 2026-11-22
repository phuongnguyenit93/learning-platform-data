# Declaring a Named Class in a Method or Block in Java

A **local class** is a **named** class declared **inside a block**, such as a method body, constructor, instance initializer, or static initializer. This class name is in scope only within the corresponding block, according to Java's lexical scope rules.

~~~java
class GreetingService {
    String greet(String name) {
        class Formatter {
            String format() {
                return "Xin chào, " + name;
            }
        }

        Formatter formatter = new Formatter();
        return formatter.format();
    }
}
~~~

`Formatter` is a **local class**: it has a name, can have constructors/fields/methods, and multiple instances can be created. However, the declaration of `Formatter` **does not become a member class of GreetingService**; code outside `greet` cannot use `GreetingService.Formatter`.

In the example, `Formatter.format()` reads the parameter `name` from the enclosing method. This is **variable capture**. Java only allows a local class to capture a local variable or parameter if that variable is **final or effectively final** and satisfies the definite assignment condition at the point of use.

This lesson belongs to **Java Core — Class & Object / Local Classes**, applicable to **Java 17+**. Standalone runnable examples include a filename, `javac`/`java` commands, and stdout for comparison. Snippets intended only for illustration are explicitly noted.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain that a local class is a **named class inside a block**, not a top-level/member class.
2. Write and instantiate a local class inside a method.
3. Know that a local class name enters scope starting at its declaration and cannot be used outside the block.
4. Distinguish a local class declaration from an instance creation expression.
5. Understand that each `new Local()` can create a new object, while repeated method calls still use the same local class declaration/runtime type.
6. Know that a local class can have fields, methods, constructors, initializers, inheritance, and interfaces.
7. Understand that a local class can access **final or effectively final** local variables/parameters of the enclosing block.
8. Know that reassigning a captured local variable breaks effectively final and causes a compile error.
9. Distinguish between **reassigning a captured reference** and **mutating the object the reference points to**.
10. Understand how captured variables continue to be used after the enclosing method returns.
11. Know that a local class in an **instance context** can access enclosing instance state.
12. Distinguish `this` inside a local class from `Outer.this` when an enclosing Outer instance exists.
13. Know that a local class in a **static context** does not automatically have `Outer.this`.
14. Understand shadowing and name resolution among local class fields, parameters, and outer members.
15. Declare a local class in a constructor or initializer block.
16. Distinguish a local class from **member inner**, **static nested**, **anonymous class**, and **lambda** forms.
17. Use a local class to implement an interface and return the object through an appropriate public type.
18. Understand generic method type parameters and local class type parameters.
19. Know the Java 17 rules for static declarations inside local classes.
20. Distinguish a local class from a **local record** and **local enum** that have static semantics.
21. Understand reflection metadata `isLocalClass()`, `getEnclosingMethod()`, and binary names.
22. Evaluate benefits, API limitations, the lifetime of captured references, and testing behavior.

## 2. Concept of Local Classes

Example:

~~~java
class Outer {
    void execute() {
        class Local {
            void run() {
                System.out.println("run");
            }
        }

        new Local().run();
    }
}
~~~

`Local` is a **named class declaration**, but it has a name only within the scope of `execute` after the declaration. It is not a field, not a method, and not a class member of Outer.

**Three distinct layers:**

~~~text
Outer source declaration
    |
    +--- method execute() body
              |
              +--- declaration: class Local { ... }
              |
              +--- invocation: new Local()
                                      |
                                      v
                               Local object #1
~~~

- **Declaration:** defines the Local type and its code.
- **Instantiation:** `new Local()` creates an object.
- **Scope:** where source code is allowed to use the simple name `Local`.

A method can be called multiple times, creating multiple Local objects. Java does not define a new class with a different identity for each method call; a local class is compiled into class metadata with lexical source scope, and instances are created when the runtime executes `new`.

## 3. First Example: Declaring and Calling a Local Class

Create **`LocalGreetingDemo.java`**:

~~~java
public class LocalGreetingDemo {
    static String greet(String name) {
        class Formatter {
            String format() {
                return "Xin chao, " + name;
            }
        }

        Formatter formatter = new Formatter();
        return formatter.format();
    }

    public static void main(String[] args) {
        System.out.println(greet("Mai"));
        System.out.println(greet("An"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalGreetingDemo.java
java LocalGreetingDemo
~~~

Stdout:

~~~text
Xin chao, Mai
Xin chao, An
~~~

Each `greet(...)` call has its own `name` parameter. Each `new Formatter()` creates a new object; Formatter's method is allowed to read `name` because name is not reassigned after being received.

## 4. Which Blocks Can a Local Class Be Declared In?

A local class declaration can appear inside a **block**, for example:

- The block of an instance method.
- The block of a static method.
- The block of a constructor.
- An instance initializer block.
- A static initializer block.
- A nested block `{ ... }`, an `if` block, a `try` block, or other blocks with appropriate syntax.

The class name can only be used within the **lexical scope** applicable to that declaration. Example:

~~~java
void example() {
    {
        class InBlock {
        }

        InBlock value = new InBlock();
    }

    // InBlock other = new InBlock(); // Error: out of scope.
}
~~~

The local class object itself can **outlive the block** if the reference is returned or stored under an externally accessible type, such as an interface. The scope of the **name** and the lifetime of the **object** are two different matters.

## 5. Runnable Program: Block Scope

Create **`LocalBlockDemo.java`**:

~~~java
public class LocalBlockDemo {
    public static void main(String[] args) {
        System.out.println("begin");

        {
            class Job {
                String describe() {
                    return "inside block";
                }
            }

            Job job = new Job();
            System.out.println(job.describe());
        }

        System.out.println("end");
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalBlockDemo.java
java LocalBlockDemo
~~~

Stdout:

~~~text
begin
inside block
end
~~~

After the `}` of the nested block, the simple name `Job` is no longer in the outer scope. Even so, the JVM was already able to create a Job instance when the block ran; scope restricts **name access in source code**, and does not automatically call a destructor for the object.

## 6. Scope of a Local Class Name Starts at Its Declaration

Like other local declarations, the **declaration position** matters.

~~~java
void example() {
    // Local value = new Local(); // Wrong: Local has not been declared yet.

    class Local {
    }

    Local value = new Local();    // Valid.
}
~~~

You cannot arbitrarily move `class Local` to the end of the method and use it beforehand as if it were a member class found throughout the entire class body.

### Cannot Write a Qualified Name Like a Member Class

~~~java
class Outer {
    void method() {
        class Local {
        }
    }
}

// Outer.Local value; // Invalid: Local is not a member type.
~~~

If an API needs to return a type to an external caller, return an **accessible interface/supertype**; do not expose the local class name.

## 7. A Local Class Can Have State and Constructors

Example:

~~~java
void report() {
    class Row {
        private final int index;

        Row(int index) {
            this.index = index;
        }

        int index() {
            return index;
        }
    }

    Row first = new Row(1);
    Row second = new Row(2);
}
~~~

Each Row object has its own `index` instance field, and its constructor is called on `new Row(...)`. A local class **is not a lambda**, so it supports common class mechanisms in full, even though its declaration scope is narrow.

### Runnable Program

Create **`LocalConstructorDemo.java`**:

~~~java
public class LocalConstructorDemo {
    static void show() {
        class Row {
            private final int index;

            Row(int index) {
                this.index = index;
            }

            String label() {
                return "row-" + index;
            }
        }

        Row first = new Row(1);
        Row second = new Row(2);

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println("same object=" + (first == second));
    }

    public static void main(String[] args) {
        show();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalConstructorDemo.java
java LocalConstructorDemo
~~~

Stdout:

~~~text
row-1
row-2
same object=false
~~~

## 8. Local Classes and `final` / Effectively Final

A local class can reference a local variable or method parameter in the surrounding lexical scope when the variable is **final or effectively final**.

**Explicit final:**

~~~java
final int base = 10;

class Adder {
    int add(int value) {
        return base + value;
    }
}
~~~

**Effectively final:**

~~~java
int base = 10; // Not declared final, but not reassigned.

class Adder {
    int add(int value) {
        return base + value;
    }
}
~~~

**Effectively final** means the variable is not reassigned according to Java's definite assignment and effective-final rules. This allows capture even though the developer did not write the `final` keyword.

Note: the captured value is the value of the local variable/parameter semantically; if it is an object reference, **the captured value is the reference** to that object, not a deep copy of the object.

## 9. Runnable Program: Capturing Two Local Values

Create **`CaptureLocalDemo.java`**:

~~~java
public class CaptureLocalDemo {
    static int calculate(int input) {
        final int base = 10;
        int factor = 2;

        class Calculator {
            int apply() {
                return base + factor * input;
            }
        }

        return new Calculator().apply();
    }

    public static void main(String[] args) {
        System.out.println("result=" + calculate(3));
        System.out.println("next=" + calculate(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CaptureLocalDemo.java
java CaptureLocalDemo
~~~

Stdout:

~~~text
result=16
next=20
~~~

`base` is explicitly final; `factor` and `input` are not reassigned, so they are effectively final. The local class Calculator reads all three. Each method invocation has its own set of argument/local values.

## 10. What Breaks Effectively Final?

When a local variable is assigned and then reassigned, it is no longer effectively final:

~~~java
void example() {
    int count = 1;
    count = 2;

    class Reader {
        int read() {
            // return count; // Compile error when capturing count.
            return 0;
        }
    }
}
~~~

This is **a snippet that intentionally avoids the error line with a comment**. If you uncomment `return count`, javac reports that the captured local variable must be final or effectively final.

### Not Every ++ Operation Is Harmless

~~~java
int count = 0;
// count++; // If count needs to be captured in a local class, this breaks effectively final.
~~~

Increment/compound assignment is a modification of the **local variable value**, so it violates the effective-final requirement. Even if the modification occurs **after the class declaration**, the compiler still examines the entire applicable scope.

### Why Does This Rule Exist?

Local variables normally belong to the method invocation lifecycle; a local class instance can outlive the invocation. Capturing stable values helps avoid some confusion about “a local variable staying alive and being updated concurrently”. Java allows a captured reference to point to a mutable object, but the captured reference variable cannot be reassigned.

## 11. Object Mutation Can Still Be Valid

Distinguish:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();

class Appender {
    void add(String name) {
        names.add(name); // Modifies the List object; does not reassign the names variable.
    }
}
~~~

`names` is effectively final because it is not reassigned to another List. The method `names.add` modifies **the referenced object**, so compilation is valid.

However:

~~~java
// names = new ArrayList<>(); // If this line is present, names is no longer effectively final.
~~~

**Effectively final does not mean immutable**. It only applies to the captured variable.

## 12. Runnable Program: Capturing a Mutable Reference

Create **`CapturedMutableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CapturedMutableDemo {
    static List<String> build() {
        List<String> names = new ArrayList<>();

        class Collector {
            void add(String name) {
                names.add(name);
            }
        }

        Collector collector = new Collector();
        collector.add("Mai");
        collector.add("An");

        return names;
    }

    public static void main(String[] args) {
        System.out.println(build());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedMutableDemo.java
java CapturedMutableDemo
~~~

Stdout:

~~~text
[Mai, An]
~~~

The `names` reference is not reassigned; the List contents still change. If multiple threads mutate the List concurrently through captured references, effective-final does not automatically guarantee thread safety.

## 13. A Local Class Can Outlive Its Enclosing Method

Example of a method returning an interface:

~~~java
static Runnable makeTask(String text) {
    class PrintTask implements Runnable {
        @Override
        public void run() {
            System.out.println(text);
        }
    }

    return new PrintTask();
}
~~~

After `makeTask("Java")` returns, the caller holds a `Runnable`. The local class name `PrintTask` is not visible to the caller, but **the object still exists and the run() method still uses the captured text**.

For this reason, capture cannot rely on an overly simplistic model where a method's local stack variable “is still active”. The compiler/JVM implements appropriate capture semantics so that the object works after the method has returned.

## 14. Runnable Program: Returning a Local Class via an Interface

Create **`LocalRunnableDemo.java`**:

~~~java
public class LocalRunnableDemo {
    static Runnable makeTask(String message) {
        class PrintTask implements Runnable {
            @Override
            public void run() {
                System.out.println(message);
            }
        }

        return new PrintTask();
    }

    public static void main(String[] args) {
        Runnable first = makeTask("Java");
        Runnable second = makeTask("Objects");

        first.run();
        second.run();

        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
        System.out.println("same object=" + (first == second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalRunnableDemo.java
java LocalRunnableDemo
~~~

Stdout:

~~~text
Java
Objects
same class=true
same object=false
~~~

There are **two PrintTask instances**, but they are created from the same local class declaration at one source location. They have the same runtime class metadata within the same class-loader context; the captured message differs per method invocation.

## 15. Runnable Program: Captured Method Parameter

A method parameter that is not reassigned may be captured by a local class.

Create **`CapturedParameterDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class CapturedParameterDemo {
    static IntUnaryOperator makeAdder(int offset) {
        class Adder implements IntUnaryOperator {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        }

        return new Adder();
    }

    public static void main(String[] args) {
        IntUnaryOperator plusTen = makeAdder(10);
        IntUnaryOperator plusTwenty = makeAdder(20);

        System.out.println(plusTen.applyAsInt(5));
        System.out.println(plusTwenty.applyAsInt(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedParameterDemo.java
java CapturedParameterDemo
~~~

Stdout:

~~~text
15
25
~~~

Each Adder stores/receives access to the captured offset of the invocation that created it. The public API only exposes the `IntUnaryOperator` interface; the class name `Adder` remains local.

## 16. Local Classes and the Enclosing Instance

If a local class is declared inside an **instance method** of an outer class, it can reference instance members of the enclosing outer class:

~~~java
class Document {
    private String title;

    String render() {
        class Renderer {
            String output() {
                return title;
            }
        }

        return new Renderer().output();
    }
}
~~~

In `Renderer.output()`, `title` is taken from the **enclosing Document instance**. If you want to emphasize the specific owner, you can use `Document.this.title` in a valid instance context.

This differs from capturing a method local variable: an outer field does not need to be effectively final. If the outer object is mutable and changes title later, the local class can observe the new value.

## 17. `this` and `Outer.this` Inside a Local Class

Inside an instance method of a local class:

- `this` is the local class object.
- `Outer.this` is the enclosing Outer object, when the declaration has an enclosing Outer instance.
- A parameter with the same name as a field can shadow the field.
- `Outer.this.member` explicitly specifies the outer field.

Create **`LocalOuterThisDemo.java`**:

~~~java
public class LocalOuterThisDemo {
    static final class Document {
        private String title;

        Document(String title) {
            this.title = title;
        }

        String render(String prefix) {
            class Renderer {
                String output() {
                    return prefix + ":" + Document.this.title;
                }

                boolean hasDocument() {
                    return Document.this != null;
                }
            }

            Renderer renderer = new Renderer();
            return renderer.output() +
                    " attached=" + renderer.hasDocument();
        }
    }

    public static void main(String[] args) {
        Document document = new Document("Java");
        System.out.println(document.render("doc"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalOuterThisDemo.java
java LocalOuterThisDemo
~~~

Stdout:

~~~text
doc:Java attached=true
~~~

The local Renderer captures `prefix` (an effectively final parameter) and accesses `Document.this.title` (an outer instance field). These are **two different data sources** even though both pieces of code are inside the same local class.

## 18. Local Classes in a Static Context

A static method has no enclosing outer **instance**. A local class declared in a static method is still a named local class and can capture effectively final local variables/parameters:

~~~java
class Utility {
    static Runnable task(String text) {
        class Worker implements Runnable {
            @Override
            public void run() {
                System.out.println(text);
            }
        }
        return new Worker();
    }
}
~~~

However, it cannot reference `Utility.this` because a static context has no receiver object.

### Runnable Program

Create **`StaticLocalClassDemo.java`**:

~~~java
public class StaticLocalClassDemo {
    private static final String PREFIX = "job:";

    static Runnable task(String name) {
        class Worker implements Runnable {
            @Override
            public void run() {
                System.out.println(PREFIX + name);
            }
        }

        return new Worker();
    }

    public static void main(String[] args) {
        Runnable job = task("compile");
        job.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticLocalClassDemo.java
java StaticLocalClassDemo
~~~

Stdout:

~~~text
job:compile
~~~

The static local Worker is allowed to access the static constant PREFIX and capture the effectively final parameter name. There is no `StaticLocalClassDemo.this` inside a Worker declared in a static method.

## 19. Local Classes in a Constructor

You can declare a local class inside a constructor block and use it to perform internal validation or computation. However, **you should not call overridable methods or publish `this` from a constructor before state initialization is complete**.

Create **`ConstructorLocalClassDemo.java`**:

~~~java
public class ConstructorLocalClassDemo {
    static final class Interval {
        private final int length;

        Interval(int length) {
            class Validator {
                boolean valid() {
                    return length > 0;
                }
            }

            if (!new Validator().valid()) {
                throw new IllegalArgumentException("length must be positive");
            }
            this.length = length;
        }

        int length() {
            return length;
        }
    }

    public static void main(String[] args) {
        Interval interval = new Interval(7);
        System.out.println("length=" + interval.length());

        try {
            new Interval(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorLocalClassDemo.java
java ConstructorLocalClassDemo
~~~

Stdout:

~~~text
length=7
rejected=length must be positive
~~~

The constructor-local Validator reads the constructor parameter length. This is a valid example, but for simple validation, direct `if (length <= 0)` code can be shorter and easier to read. Use a local class when there is truly structure/behavior worth naming; do not create a class just to replace a conditional expression.

## 20. Local Classes in an Instance Initializer Block

An instance initializer block runs during object construction, in the order defined by the Java specification. You can declare a local class inside the block:

Create **`InstanceInitializerLocalDemo.java`**:

~~~java
public class InstanceInitializerLocalDemo {
    static final class Holder {
        private final String text;

        {
            class Initializer {
                String make() {
                    return "ready";
                }
            }
            text = new Initializer().make();
        }

        String text() {
            return text;
        }
    }

    public static void main(String[] args) {
        Holder holder = new Holder();
        System.out.println(holder.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceInitializerLocalDemo.java
java InstanceInitializerLocalDemo
~~~

Stdout:

~~~text
ready
~~~

The local class `Initializer` is visible only within the initializer block. This approach can be valid, but it is usually unnecessary if a simple helper method is sufficient. Understand constructor chaining, field initializers, and instance block order before complex usage.

## 21. Local Classes in a Static Initializer Block

A static initializer block is also a valid block for declaring a named local class.

Create **`StaticInitializerLocalDemo.java`**:

~~~java
public class StaticInitializerLocalDemo {
    private static final String STATUS;

    static {
        class Initializer {
            String create() {
                return "initialized";
            }
        }
        STATUS = new Initializer().create();
    }

    public static void main(String[] args) {
        System.out.println(STATUS);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializerLocalDemo.java
java StaticInitializerLocalDemo
~~~

Stdout:

~~~text
initialized
~~~

There is no enclosing instance of StaticInitializerLocalDemo inside a static initializer. The local class can still create objects and use values that have valid scope within the block.

## 22. A Local Class Can Extend a Class or Implement Interfaces

A local class is a full-fledged class, so it can **extend a class** (non-final) or **implement interfaces** according to Java inheritance rules.

Example:

~~~java
abstract class Task {
    abstract String description();
}

void process() {
    class LocalTask extends Task implements Runnable {
        @Override
        String description() {
            return "local";
        }

        @Override
        public void run() {
            System.out.println(description());
        }
    }

    new LocalTask().run();
}
~~~

This is an illustrative snippet; the Task/method context needs to be placed inside a valid class. A local class is not a subclass of the **enclosing outer class** just because it is declared inside an outer method. `extends` and lexical nesting are two independent relationships.

### Runnable Program

Create **`LocalInheritanceDemo.java`**:

~~~java
public class LocalInheritanceDemo {
    static abstract class BaseTask {
        abstract String label();
    }

    static Runnable newTask(String text) {
        class LocalTask extends BaseTask implements Runnable {
            @Override
            String label() {
                return text;
            }

            @Override
            public void run() {
                System.out.println("task=" + label());
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        Runnable task = newTask("review");
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalInheritanceDemo.java
java LocalInheritanceDemo
~~~

Stdout:

~~~text
task=review
~~~

## 23. A Local Class Cannot Have Class Member Access Modifiers

A local class declaration does not use access modifiers such as `public`, `protected`, or `private`, nor does it use the `static` modifier the way a member class declaration does:

~~~java
void process() {
    // private class Local {} // Wrong.
    // public class Local {}  // Wrong.
    // static class Local {}  // Wrong for a local class declaration.

    class Local {             // Valid.
    }
}
~~~

This is an illustrative snippet that intentionally comments out the invalid lines.

Modifiers valid for local classes under the JLS, such as `final` or `abstract` in the appropriate situations, can be used. A local class does not become a public member type just because the enclosing method is public.

### How Is It Accessed from Outside?

Return an object through an accessible supertype/interface:

~~~java
Runnable create() {
    class LocalTask implements Runnable {
        public void run() {
            System.out.println("done");
        }
    }
    return new LocalTask();
}
~~~

The caller receives a Runnable and cannot use the name LocalTask outside the block.

## 24. Scope and Shadowing

If a method parameter and a local class field have the same name, the local class method can use qualification to clarify the target:

~~~java
int number = 10;

class Local {
    private int number = 20;

    String describe(int number) {
        return number + ":" + this.number;
    }
}
~~~

In `describe(30)`, the parameter number is 30 and `this.number` is 20. If the local class resides inside an instance method of Outer and Outer has a field with the same name, `Outer.this.number` refers to the outer instance field when the context is valid.

### Runnable Program

Create **`LocalShadowingDemo.java`**:

~~~java
public class LocalShadowingDemo {
    static String make() {
        int number = 10;

        class Local {
            private int number = 20;

            String describe(int number) {
                return "parameter=" + number +
                        ", field=" + this.number;
            }

            String captured() {
                return "outer local=" + number;
            }
        }

        Local value = new Local();
        return value.describe(30) + "; " + value.captured();
    }

    public static void main(String[] args) {
        System.out.println(make());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalShadowingDemo.java
java LocalShadowingDemo
~~~

Stdout:

~~~text
parameter=30, field=20; outer local=20
~~~

In the `captured()` method, the name number **prioritizes Local's instance field**, so it returns 20 — it does **not** access the same-named local variable number=10 in the enclosing method. There is no `OuterMethod.this.number` syntax for a shadowed local variable.

If you want to use the captured outer local, choose a non-conflicting name, or adjust the design to pass the value into a constructor/field with a different name.

## 25. Avoiding Confusion Between Shadowing a Local Variable and a Member Field

A field of a local class can shadow a surrounding local variable with the same name. To ensure reading the local variable without shadowing, you can rename it or pass it through a constructor:

~~~java
int outerNumber = 10;

class Local {
    private final int innerNumber;

    Local(int innerNumber) {
        this.innerNumber = innerNumber;
    }

    String describe() {
        return outerNumber + "/" + innerNumber;
    }
}
~~~

Clear, meaningful names are usually better than trying to use complex qualification. Local variables in an enclosing method do **not** have a receiver object like `this` to reference in the same way as outer instance fields.

## 26. Scope of Local Classes Across Branches

You can declare a local class inside each branch block, but each declaration's name is visible only within that block:

~~~java
void perform(boolean special) {
    if (special) {
        class Result {
            String value() {
                return "special";
            }
        }
        System.out.println(new Result().value());
    } else {
        class Result {
            String value() {
                return "normal";
            }
        }
        System.out.println(new Result().value());
    }
}
~~~

This is an illustrative snippet. The two `Result` declarations reside in two separate scopes, not a single unified runtime class parameterized by a boolean. If you want a shared type for both branches, create an interface/top-level/member class or return an appropriate common supertype.

### Making Code Easier to Read

You should not duplicate multiple local class implementations just to avoid an `if` in a small method. A local class is useful when the dedicated logic is genuinely complex and relevant only to that block.

## 27. Local Classes and Generic Method Type Parameters

A local class can use a type parameter from the enclosing method in an appropriate context:

~~~java
static <T> String describe(T value) {
    class Description {
        String text() {
            return "value=" + value;
        }
    }
    return new Description().text();
}
~~~

`T` is a method type parameter at compile time; the local class uses value, which is effectively final.

### Runnable Program

Create **`LocalGenericMethodDemo.java`**:

~~~java
public class LocalGenericMethodDemo {
    static <T> String describe(T value) {
        class Description {
            String text() {
                return "value=" + value;
            }
        }

        return new Description().text();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(17));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalGenericMethodDemo.java
java LocalGenericMethodDemo
~~~

Stdout:

~~~text
value=Java
value=17
~~~

Type erasure means that a separate runtime Class object for the local Description is not created for `T=String` or `T=Integer` on each call.

## 28. A Local Class Can Also Have Its Own Generic Type Parameter

Example:

~~~java
void example() {
    class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    Holder<String> words = new Holder<>("Java");
    Holder<Integer> numbers = new Holder<>(17);
}
~~~

The local class Holder has a type parameter T, independent of any type parameters of the outer method/class if present. After the block ends, the name Holder is no longer visible in other source contexts, but objects can be used through a supertype/interface if needed.

### Runnable Program

Create **`GenericLocalClassDemo.java`**:

~~~java
public class GenericLocalClassDemo {
    static void run() {
        class Holder<T> {
            private final T value;

            Holder(T value) {
                this.value = value;
            }

            T get() {
                return value;
            }
        }

        Holder<String> first = new Holder<>("Java");
        Holder<Integer> second = new Holder<>(17);

        System.out.println("first=" + first.get());
        System.out.println("second=" + second.get());
        System.out.println("same runtime class=" +
                (first.getClass() == second.getClass()));
    }

    public static void main(String[] args) {
        run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericLocalClassDemo.java
java GenericLocalClassDemo
~~~

Stdout:

~~~text
first=Java
second=17
same runtime class=true
~~~

## 29. Java 17: Static Declarations in a Local Class

Older documentation may say that inner/local classes cannot have static members except for constant variables. **Starting in Java SE 16, the restrictions on static declarations in inner classes were relaxed**.

In Java 17, a local class can have static methods/fields under the current language rules. This **does not turn the local class into a member class**, nor does it make the class name accessible outside the enclosing block.

### Runnable Program with Java 17

Create **`StaticMembersLocalDemo.java`**:

~~~java
public class StaticMembersLocalDemo {
    public static void main(String[] args) {
        class LocalMath {
            static int doubleOf(int value) {
                return value * 2;
            }
        }

        System.out.println(LocalMath.doubleOf(7));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticMembersLocalDemo.java
java StaticMembersLocalDemo
~~~

Stdout:

~~~text
14
~~~

Even with a static method, `LocalMath` is still declared **locally in the main method** and cannot be used as `StaticMembersLocalDemo.LocalMath` from external code. A static method has no `this` receiver and cannot capture the surrounding instance/local context the way an instance method can.

## 30. Local Records in Java 17: Local Name Without Capturing Enclosing State

A `Record` can be declared inside a block, but it has **implicitly static** semantics rather than being an ordinary local class. Inside a record body, you cannot directly use `Outer.this` or capture a local variable from the enclosing method; pass data through components/constructor instead:

~~~java
void calculate(int input) {
    record Pair(int first, int second) {
        int total() { return first + second; }
    }

    Pair value = new Pair(input, 3); // Passes input; does not capture.
    System.out.println(value.total());
}
~~~

This is a **method fragment**, not a standalone program. Record components are final by default, but if they hold mutable objects, the record is not necessarily deeply immutable. The dedicated lesson **Local Enums and Local Records Are Implicitly Static** presents the full rules on constructors, generic contexts, value semantics, and capture restrictions.

## 31. Local Enums: Named States in a Narrow Scope

An enum declared inside a method/block only has its name available within the corresponding block:

~~~java
void run() {
    enum State { NEW, DONE }
    State current = State.NEW;
    System.out.println(current.name());
}
~~~

This is a **method fragment**. A local enum has **implicitly static** semantics and fixed constants; it does not have `Outer.this` or directly capture local variables like an ordinary local class. Do not use `new State()` to create an enum constant. Details on constructors, identity, switch, and runtime behavior belong to the dedicated lesson on local enums/records.

## 32. Local Class vs. Anonymous Class

**Local named class**:

~~~java
class Handler implements Runnable {
    @Override
    public void run() {
        System.out.println("run");
    }
}

Runnable handler = new Handler();
~~~

**Anonymous class**:

~~~java
Runnable handler = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
~~~

Both can implement an interface. Differences:

- A local named class has a **name within the block**, can create multiple instances using `new Handler()`, and can declare constructors.
- An anonymous class declaration has no simple class name to invoke a constructor in the usual way; instance creation occurs within an expression.
- An anonymous class usually fits a one-off implementation, while a local named class fits behavior with a name/structure/reuse within the block.
- Both can capture effectively final locals from the lexical context according to the appropriate rules.

## 33. Local Class vs. Lambda

For a functional interface, a lambda is usually shorter:

~~~java
Runnable job = () -> System.out.println("run");
~~~

Comparison:

| Aspect | Local class | Anonymous class | Lambda |
| --- | --- | --- | --- |
| Has a name in the source block | Yes | No | No |
| Has its own declared constructors | Yes | Not in the usual way | No |
| Can freely have multiple instance fields/methods | Yes | Yes, in the anonymous class body | No |
| Can have an arbitrary extends/implements class body | Yes | Yes, an anonymous subclass/implementation | No |
| Captures effectively final locals | Yes | Yes | Yes |
| `this` in the body | Local instance | Anonymous instance | Enclosing instance (lexical) |
| Suitable for long logic with its own state | Yes | Possible | Usually less suitable |
| Suitable for a one-line callback | Yes, but verbose | Yes, but verbose | Usually suitable |

**A very common point of confusion:** `this` inside a lambda does **not** refer to a “lambda instance” the way `this` does inside an anonymous/local class body. A lambda resolves `this` according to the lexical context where it is written.

## 34. Runnable Program: Local and Anonymous Metadata

Create **`LocalVsAnonymousDemo.java`**:

~~~java
public class LocalVsAnonymousDemo {
    static Runnable local() {
        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println("local");
            }
        }

        return new LocalTask();
    }

    static Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = local();
        Runnable b = anonymous();

        a.run();
        b.run();

        System.out.println("a is local=" +
                a.getClass().isLocalClass());
        System.out.println("b is anonymous=" +
                b.getClass().isAnonymousClass());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalVsAnonymousDemo.java
java LocalVsAnonymousDemo
~~~

Stdout:

~~~text
local
anonymous
a is local=true
b is anonymous=true
~~~

The local class has the name `LocalTask` inside the method; the anonymous class is a type without a named source class declaration. Do not hardcode generated binary class names because compilers/JVMs may differ.

## 35. Reflection Metadata of a Local Class

Java reflection provides:

- `type.isLocalClass()`: whether the type is a local class.
- `type.isAnonymousClass()`: whether the type is an anonymous class.
- `type.isMemberClass()`: whether the type is a member class.
- `type.getEnclosingMethod()`: the enclosing method if the class is declared in a method according to metadata.
- `type.getEnclosingConstructor()`: the enclosing constructor when the class is declared in a constructor.
- `type.getEnclosingClass()`: the enclosing class, if any.
- `type.getDeclaringClass()`: the declaring class for a member class; a local class is not a member class, so this is normally null.

**Do not confuse this:** `getEnclosingClass()` returns the **Class object describing the type**. It does not retrieve a specific captured instance object.

## 36. Runnable Program: Observing Local Class Metadata

Create **`LocalClassMetadataDemo.java`**:

~~~java
public class LocalClassMetadataDemo {
    static Class<?> localType() {
        class Worker {
        }

        return Worker.class;
    }

    public static void main(String[] args) {
        Class<?> type = localType();

        System.out.println("simple=" + type.getSimpleName());
        System.out.println("local=" + type.isLocalClass());
        System.out.println("member=" + type.isMemberClass());
        System.out.println("anonymous=" + type.isAnonymousClass());
        System.out.println("enclosing method=" +
                type.getEnclosingMethod().getName());
        System.out.println("enclosing class=" +
                (type.getEnclosingClass() ==
                        LocalClassMetadataDemo.class));
        System.out.println("declaring null=" +
                (type.getDeclaringClass() == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalClassMetadataDemo.java
java LocalClassMetadataDemo
~~~

Stdout:

~~~text
simple=Worker
local=true
member=false
anonymous=false
enclosing method=localType
enclosing class=true
declaring null=true
~~~

Distinguish **enclosing method/class declaration metadata** from whether a local class object captures a particular variable or outer instance. Reflection `Class` does not provide a generic `getCapturedLocals()` API with semantics like reading “all current local variables”.

## 37. The Generated Binary Name Is an Implementation Detail

Compilers often generate bytecode files with a naming pattern such as `Outer$1Local.class` for a local class, but production code should not depend on the exact sequence number `1` or the generated binary name.

If you want to check type identity at runtime, use `obj.getClass()`, or `Local.class` inside the scope where the name Local is still visible. If you need reflection metadata, use `isLocalClass()`, `getEnclosingMethod()`, and related APIs instead of parsing the generated name.

A local class is still a runtime class defined by the JVM; having a small scope does not make it “an object constructed by an interpreter inside a method” without type metadata.

## 38. Does Each Method Call Create a New Class?

No. Each invocation of the method can create a **new instance** of the local class, but the local class declaration is not an independent class definition recreated on every method call.

In the `LocalRunnableDemo` example: the two Runnable objects have different identities, yet `getClass() ==` is true. The captured values (message) differ between instances, while the runtime class metadata is the same within the same class-loader identity.

### When Can Class Loading Occur?

The timing of class loading/linking/initialization is governed by JVM semantics. Do not try to assume that “entering the method reloads the class every time” or that “a local class does not need a class file”. The key point to understand is: **declaration scope differs from instance lifetime and runtime type identity**.

## 39. A Local Class Does Not Automatically Create a Public Class-Level API

Even if the enclosing method is declared `public`, a local class remains a local declaration:

~~~java
public Runnable create() {
    class PrivateImplementation implements Runnable {
        @Override
        public void run() {
            System.out.println("hello");
        }
    }

    return new PrivateImplementation();
}
~~~

A caller invoking `create()` receives a Runnable and cannot directly call `new PrivateImplementation()` outside the method. This is an effective way to hide implementation details.

If the class needs to be reused across multiple methods or modules, a `private static nested class` or a top-level class may be more appropriate than copy-pasting the same local declaration into multiple blocks.

## 40. Captured References and Memory Retention

A returned local-class object can retain access to captured objects:

~~~java
static Runnable task(SomeResource resource) {
    class Runner implements Runnable {
        public void run() {
            resource.execute();
        }
    }
    return new Runner();
}
~~~

This snippet is illustrative pseudocode because `SomeResource` is not defined. If Runner is stored in a long-lived global registry, the resource may be kept reachable longer than intended.

Similarly, if a local class is declared in an instance method and uses outer state, the object can keep the enclosing outer instance reachable. Manage **register/unregister**, callback lifetime, and ownership just as with anonymous/inner member classes.

### Caution When Switching to a Lambda

Lambda capture can also hold references when needed. Converting a local class to a lambda **does not automatically solve every memory-retention problem**; lifecycles and dependencies must be designed appropriately.

## 41. Thread Safety When Capturing Mutable Data

Effectively final only restricts **reassignment of the local variable**. If the captured reference points to a mutable object, threads can still encounter data races.

Example:

~~~java
java.util.List<String> shared = new java.util.ArrayList<>();
class Job implements Runnable {
    public void run() {
        shared.add("x");
    }
}
~~~

If multiple threads run Job on the same ArrayList without synchronization, the code has no thread-safety guarantee just because the shared variable is effectively final.

### Runnable Program: Atomic Shared State

Create **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    static Runnable counterTask(AtomicInteger counter) {
        class IncrementTask implements Runnable {
            @Override
            public void run() {
                counter.incrementAndGet();
            }
        }

        return new IncrementTask();
    }

    public static void main(String[] args) {
        AtomicInteger count = new AtomicInteger();
        Runnable task = counterTask(count);

        task.run();
        task.run();

        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

Stdout:

~~~text
count=2
~~~

The `counter` parameter is effectively final, while the AtomicInteger object mutates internally through a thread-safe method. Capture and concurrency synchronization are two separate concerns.

## 42. Why Can't You Arbitrarily Replace a Local Class with a Member Class?

A local class has access to **local variables/parameters** from the block where it is declared. A member class is declared in the class body and is **not** within the scope of a specific method parameter.

Example:

~~~java
void process(String message) {
    class Printer {
        String text() {
            return message;
        }
    }
}
~~~

If you move Printer out to the class body as a member class, `message` is no longer in scope. You must pass it through a constructor/field:

~~~java
class Printer {
    private final String message;

    Printer(String message) {
        this.message = message;
    }

    String text() {
        return message;
    }
}
~~~

A local class keeps code close to the data flow; a member/static nested class supports clear reuse and explicit dependency management.

## 43. When Should You Use a Local Class?

Using a local class is beneficial when:

- A piece of logic has a **clear semantic name** and is used only inside one method/block.
- The implementation needs multiple methods/fields or a small constructor.
- You want to implement an interface to return an object while hiding the implementation type.
- The logic needs to capture a few effectively final values and has few external dependencies.
- A local implementation is more readable than an anonymous class or a complex lambda.
- There is no need for direct reuse from other methods.

Examples: a method creating a customized comparator with a few helper methods, an iterable adapter tied to a local data snapshot, or a multi-step callback used only at one point.

### When to Avoid It?

- Logic is just a single expression → a lambda/helper method may be easier to read.
- The class is needed from multiple methods → a private static nested/top-level class is clearer.
- The local class is too large, making the method long/hard to test.
- There are many hard-to-see captured mutable dependencies → constructor injection/explicit dependencies are clearer.
- The public API genuinely needs to expose the type → a local name is not suitable.
- There is complex concurrency/lifecycle management → extract a separate type with an ownership contract.

## 44. Quick Comparison Table

| Concept | Scope/type | Captures outer local variables? | Has a reusable name in the block? |
| --- | --- | --- | --- |
| Local named class | Block containing the declaration | Yes, final/effectively final | Yes |
| Member inner class | Class body without static | Does not capture locals of a specific method | Yes, in member type scope |
| Static nested class | Class body with static | No | Yes |
| Anonymous class | Expression | Yes, final/effectively final | No |
| Lambda | Expression with a functional interface | Yes, final/effectively final | No |
| Local record | Block, implicitly static | Does not capture locals in its body | Yes |
| Local enum | Block, implicitly static | Does not capture enclosing instance state | Yes |

This is a core conceptual table and does not replace Java's specific access/definite assignment and type inference rules.

## 45. Checklist When Encountering a Compile Error

**Step 1 — Is the local class name still in scope?** Do not use it before the declaration or after the block.

**Step 2 — Was an invalid access modifier used?** A local class does not take `public/private/protected/static` declaration modifiers the way a member class does.

**Step 3 — Is the captured local variable effectively final?** Look for reassignment, increment, or compound assignment in scope.

**Step 4 — Was the local/parameter definitely assigned before use?** Capture does not bypass the definite assignment rule.

**Step 5 — Is there shadowing?** `this.field` of the local class may hide a local variable name in the enclosing method.

**Step 6 — Are you in a static context?** Do not use `Outer.this` when there is no enclosing Outer instance.

**Step 7 — Does the overridden method have sufficient visibility?** Implementing `Runnable.run()` must be `public`.

**Step 8 — Is a local record/enum trying to capture?** They are implicitly static; pass values through components/constructor or method parameters.

**Step 9 — Is the compile target correct?** Static declarations in inner/local classes and local records/enums depend on the Java version; this lesson uses Java 17.

**Step 10 — Is the object returned through an accessible type?** Do not try to use the local class name as a public return type at class scope.

## 46. Exercise 1 — Scope of a Class Name

~~~java
static void run() {
    {
        class Helper {}
        Helper first = new Helper();
    }

    // Helper second = new Helper();
}
~~~

**Answer:** If you uncomment the last line, the code does not compile because `Helper` is no longer in lexical scope. A local class declaration is not a member of the outer type.

## 47. Exercise 2 — Reassigning a Captured Variable

~~~java
static void run() {
    int number = 5;
    number++;

    class Reader {
        int read() {
            // return number;
            return 0;
        }
    }
}
~~~

**Answer:** `number` is not effectively final because of ++, so uncommenting `return number` produces a compile error. Fix this by not reassigning number or by passing the value into Reader's constructor.

## 48. Exercise 3 — Mutation Differs from Reassignment

~~~java
static void run() {
    java.util.List<String> names =
            new java.util.ArrayList<>();

    class Writer {
        void write() {
            names.add("Java");
        }
    }

    new Writer().write();
}
~~~

**Answer:** Valid, because the `names` reference is not reassigned; mutating the List object does not break the local variable's effectively final status. However, the List is still mutable.

## 49. Exercise 4 — Runtime Class of Two Instances

A method declares `class Local implements Runnable` and returns `new Local()`. A caller invokes the method twice. What are `a == b` and `a.getClass() == b.getClass()`, respectively?

**Answer:** Normally `a == b` is false because two `new Local()` calls create separate objects; `a.getClass() == b.getClass()` is true within the same runtime class-loader identity because they use the same local class declaration.

## 50. Exercise 5 — Static Context

Can a local class in a static method use `Outer.this.name`?

**Answer:** There is no enclosing Outer instance in a static context, so `Outer.this` cannot be used. If the value is needed, pass an Outer reference explicitly or declare the local class inside an instance method.

## 51. Exercise 6 — Does a Local Record Capture?

~~~java
static int compute(int input) {
    record Pair(int a, int b) {}
    Pair value = new Pair(input, 2);
    return value.a() + value.b();
}
~~~

**Answer:** Valid. The record does not directly capture input; the code passes input as a component into the constructor. This is the right way to use data from the surrounding scope with a local record.

## 52. Exercise 7 — Anonymous and Lambda `this`

Why is `this` inside a lambda not the same as `this` in a method of a local class?

**Answer:** A lambda uses the lexical `this` of the enclosing context, whereas a method of a local class is an instance method so `this` points to the local class object. Do not use lambda syntax as a “shorthand anonymous class” in every case.

## 53. Exercise 8 — Design Decision

A parser helper has 30 methods, is used in five methods, and does not capture locals. Should you keep copying the local class across all five blocks?

**Answer:** Usually no. Making the helper a `private static nested class`, top-level class, or dedicated parser service improves reuse, testing, and clarity of ownership. A local class suits small, localized logic tied to a single block.

## 54. Common Mistakes

| Misconception | Fact |
| --- | --- |
| “A class inside a method is a member class.” | It is a local class declaration. |
| “A local class has no name.” | It is an anonymous class that has no simple named declaration. |
| “Each run of the method creates a new class type.” | It creates new instances from one declaration/runtime class. |
| “A local class name can be used from any method.” | Only within its lexical scope. |
| “A local class must be declared at the end of the file.” | Declared directly inside the appropriate block. |
| “A local class has no constructors/fields.” | It can have them like an ordinary class. |
| “A captured variable must be written as final.” | Effectively final is also sufficient. |
| “You can ++ a captured int local.” | No, that breaks effectively final. |
| “Effectively final means the object is immutable.” | The referenced object can still be mutable. |
| “Captured variables die right when the method returns.” | The returned object still uses the captured values. |
| “A static method has Outer.this.” | There is no enclosing outer instance. |
| “this in a local class is the outer object.” | this is the local instance; Outer.this applies if the context is valid. |
| “Private outer state cannot be read from a local class.” | It can be accessed according to nesting/access rules. |
| “A shadowed outer local variable is read via Outer.this.” | Outer.this is for outer instance members, not method locals. |
| “A local class can be public/private like a member class.” | Those access modifiers are not used. |
| “A local record can capture like a local class.” | A local record is implicitly static. |
| “Java 17 forbids all static members in an inner local class.” | The old restriction changed starting in Java 16. |
| “getEnclosingClass() returns the outer object.” | It returns Class metadata. |
| “The generated binary name is stable enough to parse.” | You should not depend on compiler-generated names. |
| “Converting a local class to a lambda always avoids memory leaks.” | Captured references and lifecycle still matter. |

## 55. End-of-Lesson Checklist

- [ ] I can declare a named local class inside a method/block.
- [ ] I distinguish a local class declaration from `new Local()`.
- [ ] I know that a local class name has only lexical scope.
- [ ] I do not use a local class name before its declaration.
- [ ] I know that objects can outlive the block through an interface return.
- [ ] I know that each new creates an instance, not a new Java class identity per method call.
- [ ] I can write a local class constructor/fields/methods.
- [ ] I know that captured locals/parameters must be final or effectively final.
- [ ] I distinguish reassigning a local from mutating the referenced object.
- [ ] I understand that capturing a local value does not mean deep-copying a mutable object.
- [ ] I return a local class object through an accessible interface.
- [ ] I know that a local class in an instance method can use Outer.this.
- [ ] I know that a static local class has no enclosing outer instance.
- [ ] I understand that `this` differs across a local class, an anonymous class, and a lambda.
- [ ] I recognize shadowing by local class fields.
- [ ] I know that a local class can be declared in a constructor/initializer.
- [ ] I know that a local class can extend/implement.
- [ ] I do not use public/private/protected/static as class member modifiers on a local class.
- [ ] I know that a local class can have a generic type parameter.
- [ ] I know that Java 17 allows static methods in an inner/local class.
- [ ] I distinguish a local class from an implicitly static local record/enum.
- [ ] I use Class.isLocalClass and getEnclosingMethod with their proper meanings.
- [ ] I do not depend on a compiler-generated binary name.
- [ ] I understand that captured references can extend object lifetime.
- [ ] I design concurrency/lifecycle when a local instance escapes the method.
- [ ] I know when to use a lambda, anonymous class, member/static nested class, or top-level type.
- [ ] I can explain the stdout results of the Java 17+ programs.

**Conclusion:** **A local class is a named class declared inside a block**, typically a method or constructor, and its name can only be used within the corresponding scope. It still has constructors, fields, methods, inheritance, instances, and Class metadata like a real Java class. Its notable strength is access to **final/effectively final local variables and parameters** of the surrounding block, while also being able to access enclosing instance state in an instance context. Use a local class when an implementation has its own name, state, and behavior yet is needed only within a narrow scope; if the code must be reused broadly, consider a member/static nested/top-level class for clearer responsibilities and API.
