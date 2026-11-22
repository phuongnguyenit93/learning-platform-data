# Field Initialization and Initializer Blocks When an Anonymous Class Has No Named Constructor

## Learning Objectives

After this lesson, you will be able to:

- Explain that `new Interface() { ... }` or `new Base(args) { ... }` creates an **anonymous class** and an instance of that class, rather than merely creating an object of the interface or of the exact Base class.
- Understand why an anonymous class **cannot declare an explicit constructor**, yet the Java compiler still generates an **implicit anonymous constructor** to call the appropriate superclass constructor.
- Use **instance field initializers** (`int value = expression;`) and **instance initializer blocks** (`{ ... }`) to set up state, run validation, and perform necessary initialization steps.
- Distinguish an instance initializer block from a method body, constructor body, static initializer, and lambda body.
- Grasp the execution order: evaluating relevant qualifier/constructor arguments when present, allocating the object and assigning default values to fields, calling the superclass constructor, and then executing the anonymous class's field initializers and initializer blocks in **the order they appear in source**.
- Predict stdout when multiple field initializers/blocks are interleaved, when creating multiple instances, and when a superclass constructor calls a method overridden by the anonymous class.
- Initialize `final` instance fields using an expression or a block according to definite assignment rules; know why that logic cannot be placed in a constructor **bearing the anonymous class's name**.
- Understand captured local variables (final/effectively final), outer instance references, `this`, and `super` inside an anonymous class initializer.
- Handle checked/unchecked exceptions from anonymous class instance initializers, where checked exceptions may be listed by the compiler via the implicit anonymous constructor.
- Recognize common pitfalls: forward field references, using a field before it is set, an overridden method called inside a superclass constructor, `this` escaping before construction completes, confusing static context, and interface-target types.
- Compare initializers with factory methods, named subclasses, lambdas, and object composition to choose a readable, testable design in Java 17+.
- Compile/run standalone programs; read stdout, distinguish illustrative code that does not run standalone from verifiable test behavior.

## 1. What Is an Anonymous Class and Why Does It Have No Named Constructor?

An anonymous class is defined and instantiated in **the same class instance creation expression**:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

`Runnable` is an interface; the expression above creates **an unnamed class in source** that implements the interface and then creates an instance of that class. The code calls the method through the `Runnable task` variable.

Another example, with a class as the superclass:

~~~java
abstract class Work {
    abstract String message();
}

Work w = new Work() {
    @Override
    String message() {
        return "ready";
    }
};
~~~

These are **illustrative snippets that need to be placed in an appropriate scope/file**. An anonymous subclass of Work is created and overrides `message()`.

To write a **constructor declaration** in Java, you need the **class name** of the constructor. An anonymous class has no simple name that you can put into a declaration; therefore:

~~~java
Runnable bad = new Runnable() {
    // Runnable() { }  // Not a valid constructor here.
    // SomeName() { }  // There is also no anonymous class name to use.
    @Override
    public void run() {
    }
};
~~~

An anonymous class **cannot declare an explicit constructor**. According to JLS §15.9.5.1, the compiler provides an **implicit anonymous constructor**, passing valid parameters to the superclass constructor and handling related checked exceptions.

> Not having an **explicit, named** constructor does not mean the object **is not initialized**. An anonymous instance still goes through all Java instance creation steps; you have field initializers, instance initializer blocks, superclass constructors, and (when appropriate) external factory methods.

## 2. Two Tools in Place of a Constructor Body in an Anonymous Class

### 2.1. Field initializer

Place an expression in the declaration of an instance field:

~~~java
Runnable task = new Runnable() {
    private int count = 3;
    private final String name = "job";

    @Override
    public void run() {
        System.out.println(name + ":" + count);
    }
};
~~~

Each **new instance** of the anonymous class has its own instance fields. `count = 3` and `name = "job"` perform initialization when the object is created (after the superclass constructor).

### 2.2. Instance initializer block

Place a block **with no method/constructor name and no modifier** in the anonymous class body:

~~~java
Runnable task = new Runnable() {
    private int count;

    {
        count = 3;
        if (count < 0) {
            throw new IllegalArgumentException("count");
        }
    }

    @Override
    public void run() {
        System.out.println(count);
    }
};
~~~

The `{ count = 3; ... }` block is an **instance initializer**, running automatically during object initialization. It is **not** the `run()` method and does not wait until the caller calls `run()`.

In Java 17, an anonymous class can declare instance fields, methods, and initializer blocks as a valid class body; it must obey access, definite assignment, and exception rules.

### 2.3. Which one should you use?

- An expression is clear enough to compute the initial value: use `private final int limit = Math.max(...);`.
- Need a few statements, validation, or assigning a `final` field after processing: use an instance initializer block.
- Need to coordinate multiple paths, dependencies, resource lifetimes, or complex error handling: it is usually better to use a **named class** or **factory method** instead of making an anonymous block too long.

## 3. First Program: Field Initializer, Then Block, Then Method

Save **`AnonymousSimpleInitializerDemo.java`**:

~~~java
public class AnonymousSimpleInitializerDemo {
    public static void main(String[] args) {
        Runnable action = new Runnable() {
            private int counter = 2;

            {
                System.out.println("initial block");
                counter *= 3;
            }

            @Override
            public void run() {
                System.out.println("run counter=" + counter);
            }
        };

        System.out.println("object ready");
        action.run();
        action.run();
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac AnonymousSimpleInitializerDemo.java
java AnonymousSimpleInitializerDemo
~~~

**Stdout:**

~~~text
initial block
object ready
run counter=6
run counter=6
~~~

Reading the order:

1. `new Runnable() { ... }` starts creating the anonymous instance.
2. The `counter` field defaults to 0 when memory is allocated; after the superclass constructor (`Object()`), the field initializer assigns 2.
3. The instance block prints `initial block` and multiplies counter to 6.
4. The `new ...` expression completes; the caller prints `object ready`.
5. The two `run()` calls only run the method body and do **not** re-run the initializer. Counter remains 6 because `run` does not change it.

**Rule to remember:** **initializers run during object creation; methods run when called**.

## 4. Complete Initialization Sequence

Consider a general expression:

~~~java
Base object = new Base(arg1, arg2) {
    int a = initA();

    {
        initializeMore();
    }

    int b = initB();

    @Override
    void work() {
    }
};
~~~

This is only a **code outline**; Base and the helper methods must be declared to compile. For an anonymous subclass, logically in Java 17:

1. Evaluate the relevant receiver/qualifier and the constructor argument expressions in Java's order.
2. Allocate the object instance and set instance fields to default values: `0`, `false`, `null`, ...
3. Set up the enclosing/captured state required by the compiler according to the semantics; do not rely on ordering/synthetic field names as a public API.
4. Run the superclass constructor chain (including ancestors). If a parent constructor throws an exception, the anonymous field/instance initializers **do not run**.
5. Inside the anonymous class, run **instance variable initializers** and **instance initializer blocks** interleaved, **from left to right/in the order they appear in the class body**.
6. The anonymous class does not have an **explicit constructor body** of its own running after the blocks. The implicit constructor completes, and the expression returns the reference if successful.

This applies JLS §12.5 (*Creation of New Class Instances*) and §15.9.5.1 (*Anonymous Constructors*). Do not swap "field initialization" ahead of the superclass constructor just because the field declaration is placed at the top of the anonymous body.

### 4.1. Easy-to-Compare Order Table

| Event | When does it happen? | Does it repeat when calling a method? |
| --- | --- | --- |
| Constructor argument expressions | When evaluating `new` | No |
| Default values of instance fields | Before the constructor chain | No |
| Superclass constructor | During object initialization | No |
| Anonymous field initializer | After the superclass constructor; in source order | No |
| Anonymous instance initializer block | After the superclass constructor; interleaved in source order | No |
| Anonymous overridden method body | When called or dispatched by other code | Possibly multiple times |
| Static initializer of a class | According to class initialization rules | Not per instance |

**Important exception:** if the superclass constructor calls an overridable method and the override in the anonymous class is dispatched **right then**, the method may run **before** the anonymous class's field/initializer blocks. This does not violate the order: the method dispatch originates from the running superclass constructor.

## 5. Program: Interleaving Multiple Field Initializers and Blocks

Save **`AnonymousInitializerOrderDemo.java`**:

~~~java
public class AnonymousInitializerOrderDemo {
    static int log(String step, int value) {
        System.out.println(step + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int first = log("field-first", 1);

            {
                System.out.println("block-one=" + first);
                first += 4;
            }

            private int second = log("field-second", first * 2);

            {
                System.out.println("block-two=" + second);
                second++;
            }

            @Override
            public void run() {
                System.out.println("run=" + first + "," + second);
            }
        };

        System.out.println("after-new");
        task.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousInitializerOrderDemo.java
java AnonymousInitializerOrderDemo
~~~

Output:

~~~text
field-first=1
block-one=1
field-second=10
block-two=10
after-new
run=5,11
~~~

Analysis without needing to guess the compiler:

- Field `first` is initialized to the value 1.
- Block-one reads 1 and adds 4 → `first = 5`.
- Field `second` computes `first * 2 = 10`.
- Block-two sees 10 and increments `second` to 11.
- After the object is ready, `run()` prints 5 and 11.

If you change the **position** of block-one to after `second`, the result will be different. It is the **source order** of the field/instance initializers that matters, not the order of names or declaration types.

## 6. Superclass Constructor Runs Before Anonymous Initializers

An anonymous class can extend **a superclass with constructor parameters**:

~~~java
abstract class Job {
    Job(String name) {
        System.out.println("base constructor: " + name);
    }

    abstract void execute();
}
~~~

When creating `new Job("A") { ... }`, `"A"` is used to select and call the `Job(String)` constructor. The anonymous class does not declare a constructor with its own name and cannot add `super("A")` inside a nonexistent constructor.

### 6.1. Runnable program

Save **`AnonymousSuperclassOrderDemo.java`**:

~~~java
public class AnonymousSuperclassOrderDemo {
    static abstract class Job {
        Job(String name) {
            System.out.println("super=" + name);
        }

        abstract void execute();
    }

    static int printAndReturn(String label, int value) {
        System.out.println(label + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        Job job = new Job("REPORT") {
            private int size = printAndReturn("field-size", 3);

            {
                System.out.println("block-size=" + size);
                size += 2;
            }

            @Override
            void execute() {
                System.out.println("execute-size=" + size);
            }
        };

        System.out.println("created");
        job.execute();
    }
}
~~~

Run:

~~~bash
javac AnonymousSuperclassOrderDemo.java
java AnonymousSuperclassOrderDemo
~~~

Output:

~~~text
super=REPORT
field-size=3
block-size=3
created
execute-size=5
~~~

The superclass constructor runs before **field-size**, followed by the initializer block. The `created` line appears once the `new` expression has completed. An anonymous initializer is not an option for **running before the superclass constructor**.

### 6.2. What if the superclass constructor uses arguments with side effects?

Java evaluates constructor argument expressions before calling the constructor; if `log("arg", x)` prints a log, that printing can happen before the log inside the superclass constructor. However, do not confuse **argument evaluation** with **initializing the anonymous subclass's instance fields**, which still runs after the superclass constructor.

## 7. Using an Instance Initializer to Assign a `final` Field

A `final` instance field must be assigned strictly according to Java definite assignment rules. An anonymous class **cannot write an explicit constructor**, but it can use a field initializer:

~~~java
private final int limit = 10;
~~~

or a **blank final** assigned inside an instance initializer block:

~~~java
private final int limit;

{
    int base = 2;
    limit = base * 5;
}
~~~

You cannot reassign `limit` once it has been assigned. A local variable `int base` in the block is only for computation and does not automatically become a field.

### 7.1. Program: blank final field

Save **`AnonymousFinalFieldDemo.java`**:

~~~java
public class AnonymousFinalFieldDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private final int threshold;
            private final String label;

            {
                int units = 4;
                threshold = units * 3;
                label = "T-" + threshold;

                if (threshold <= 0) {
                    throw new IllegalArgumentException("threshold");
                }
            }

            @Override
            public void run() {
                System.out.println(label);
                System.out.println("threshold=" + threshold);
            }
        };

        task.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousFinalFieldDemo.java
java AnonymousFinalFieldDemo
~~~

Output:

~~~text
T-12
threshold=12
~~~

`threshold` and `label` are assigned exactly once in the block, before the `run` method is called. If the code attempts to modify a final field afterward, the compiler will reject it according to Java assignment rules.

### 7.2. Validation does not replace a constructor contract

Checking invariants in a block can be useful, but an anonymous class with too many lines of object-creation logic is often hard to read. For public/domain objects with complex validation, a **named class constructor or static factory** makes the API and unit tests clearer.

## 8. Captured Local Variables in Field/Instance Initializers

An anonymous class is an inner class; code inside the anonymous class body can use **final/effectively final** local variables from the enclosing method, when Java capture rules are satisfied.

~~~java
int factor = 4; // effectively final

Runnable task = new Runnable() {
    private final int result = factor * 3;

    @Override
    public void run() {
        System.out.println(result);
    }
};
~~~

The field initializer uses the value of `factor` to construct state. Java does not allow an anonymous class to capture a local variable that is reassigned in a way that breaks the effectively-final constraint.

### 8.1. Program combining capture with a block

Save **`AnonymousCapturedInputDemo.java`**:

~~~java
public class AnonymousCapturedInputDemo {
    static Runnable create(int input) {
        int adjustment = 5; // Effectively final.

        return new Runnable() {
            private final int result = input + adjustment;

            {
                System.out.println("built result=" + result);
            }

            @Override
            public void run() {
                System.out.println("run result=" + result);
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = create(7);
        Runnable second = create(10);

        first.run();
        second.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousCapturedInputDemo.java
java AnonymousCapturedInputDemo
~~~

Output:

~~~text
built result=12
built result=15
run result=12
run result=15
~~~

The two method calls create two anonymous instances with their own captured values. `input` is a method parameter that is not reassigned, while `adjustment` is an effectively final local.

**Important:** a `final` reference to a mutable object can still point to an object modified through another alias. Capturing a list or array reference does not make that object immutable.

## 9. Do Not Use an Instance Initializer to "Declare a Constructor"

Compare three constructs:

~~~java
Runnable task = new Runnable() {
    private int value = 1;  // Field initializer.

    {                        // Instance initializer block.
        value++;
    }

    private void update() {  // Method, runs only if called.
        value++;
    }

    @Override
    public void run() {
        update();
        System.out.println(value);
    }
};
~~~

`value` will be 2 after construction and increase to 3 when `run()` calls `update()`.

**Invalid:**

~~~java
Runnable task = new Runnable() {
    // Task() { }          // No anonymous type name to declare a constructor.
    // Runnable() { }      // Cannot declare a constructor with the interface name.
    // { return; }         // return cannot appear inside an instance initializer.
    @Override
    public void run() {
    }
};
~~~

The invalid lines are commented out. An **instance initializer** cannot contain a `return` statement; JLS §8.6 also requires that an initializer **can complete normally** under reachability rules, even though it may throw an exception on some paths.

**Do not confuse** this with code inside `run()`: the method can `return;` because it is a `void` method.

## 10. Calling Its Own Method from an Initializer

An anonymous class can declare a helper method and call it from a field initializer or instance block. However, if the helper **reads other uninitialized fields**, it is very easy to see default values.

~~~java
Runnable task = new Runnable() {
    private int left = compute();

    private int right = 9;

    private int compute() {
        return right + 1;
    }

    @Override
    public void run() {
        System.out.println(left + "," + right);
    }
};
~~~

According to this source order, the `left` initializer calls `compute()` **before** the `right = 9` initializer executes. Therefore, `right` still has its default value of 0 at that time, and `left = 1`. Afterward, `right = 9`.

### 10.1. Runnable program

Save **`AnonymousMethodIndirectionDemo.java`**:

~~~java
public class AnonymousMethodIndirectionDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int first = readSecond();
            private int second = 9;

            private int readSecond() {
                return second + 1;
            }

            @Override
            public void run() {
                System.out.println("first=" + first);
                System.out.println("second=" + second);
            }
        };

        task.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousMethodIndirectionDemo.java
java AnonymousMethodIndirectionDemo
~~~

Output:

~~~text
first=1
second=9
~~~

The `readSecond` method is called when the field initializer executes; it does not automatically make all fields "initialized." To avoid bugs, prefer declaring dependencies **before the fields that use them** or computing dependencies using already available explicit values.

## 11. Forward Reference: Simple Name and Access via `this`

Java has specific rules for using a field **before its declaration** in an initializer:

~~~java
Runnable task = new Runnable() {
    // int first = second;  // Simple-name forward reference error.
    private int first = this.second;
    private int second = 7;

    @Override
    public void run() {
        System.out.println(first + "," + second);
    }
};
~~~

Here `this.second` is a qualified field access, so it avoids the **simple-name forward reference** error of JLS §8.3.3 itself, yet it **does not make initialization happen earlier**. `second` is still 0 when `first` is computed, so `first = 0`; afterward, `second = 7`.

**Do not use `this.second` as a trick to mask a wrong init order.** That the compiler allows it does not mean the state is ready.

### 11.1. Demonstration program

Save **`AnonymousForwardReferenceDemo.java`**:

~~~java
public class AnonymousForwardReferenceDemo {
    public static void main(String[] args) {
        Runnable action = new Runnable() {
            private int first = this.second;
            private int second = 7;

            @Override
            public void run() {
                System.out.println("first=" + first);
                System.out.println("second=" + second);
            }
        };

        action.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousForwardReferenceDemo.java
java AnonymousForwardReferenceDemo
~~~

Output:

~~~text
first=0
second=7
~~~

**Recommendation:** place field `second` before field `first` if `first` needs the initialized value of `second`:

~~~java
private int second = 7;
private int first = second;
~~~

This is a valid snippet **inside a class body**, not a standalone Java file.

## 12. Superclass Constructor Calls an Overridden Method Too Early

A subtle pitfall of inheritance: a superclass constructor may call an overridable instance method. Java dispatches based on the **runtime class of the object**, so the override in the anonymous subclass can run **before** the anonymous class's field/instance initializers execute.

### 12.1. Program whose stdout intentionally observes the default field

Save **`AnonymousEarlyDispatchDemo.java`**:

~~~java
public class AnonymousEarlyDispatchDemo {
    static class Parent {
        Parent() {
            System.out.println("super sees=" + value());
        }

        int value() {
            return -1;
        }
    }

    public static void main(String[] args) {
        Parent child = new Parent() {
            private int number = 5;

            {
                System.out.println("block number=" + number);
            }

            @Override
            int value() {
                return number;
            }
        };

        System.out.println("after construction=" + child.value());
    }
}
~~~

Run:

~~~bash
javac AnonymousEarlyDispatchDemo.java
java AnonymousEarlyDispatchDemo
~~~

Output:

~~~text
super sees=0
block number=5
after construction=5
~~~

**Detailed explanation:**

1. Memory has been allocated for the anonymous subclass object; field `number` has the default value 0.
2. `Parent()` runs and invokes the virtual method `value()`.
3. Runtime dispatch selects **the anonymous subclass's override**.
4. `number = 5` has not run yet, so the method sees 0.
5. The Parent constructor finishes; the anonymous initializer `number = 5` runs, and then the block prints 5.
6. After construction finishes, calling `value()` again returns 5.

This is not because the field initializer was skipped; it runs **after** the superclass constructor. Design lesson: **avoid calling overridable methods from constructors** when subclass logic might depend on state that is not ready yet. The same bug happens with named subclasses as well, not only anonymous classes.

## 13. What Does `this` Point to Inside an Anonymous Block?

Inside an anonymous class initializer, `this` is the **anonymous instance**, not the enclosing outer object. If the expression appears inside an instance method of Outer, `Outer.this` can be a reference to the enclosing instance when valid.

~~~java
class Outer {
    private int id = 10;

    Runnable make() {
        return new Runnable() {
            private int id = 3;

            {
                id += 1; // Anonymous field.
            }

            public void run() {
                System.out.println(id);
                System.out.println(Outer.this.id);
            }
        };
    }
}
~~~

The snippets belong to the same class context above. `this.id` in the anonymous class is the anonymous class's `id` field; `Outer.this.id` is the enclosing Outer's field. Do not write `Outer.this` in a static context where there is no Outer instance.

### 13.1. Illustrative program

Save **`AnonymousThisDemo.java`**:

~~~java
public class AnonymousThisDemo {
    private final int outerValue = 20;

    Runnable newAction() {
        return new Runnable() {
            private int innerValue = 2;

            {
                innerValue += 3;
            }

            @Override
            public void run() {
                System.out.println("inner=" + this.innerValue);
                System.out.println("outer=" +
                        AnonymousThisDemo.this.outerValue);
            }
        };
    }

    public static void main(String[] args) {
        AnonymousThisDemo owner = new AnonymousThisDemo();
        Runnable task = owner.newAction();
        task.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousThisDemo.java
java AnonymousThisDemo
~~~

Output:

~~~text
inner=5
outer=20
~~~

An anonymous class has no source name, so you cannot write `new AnonymousThisDemo.Anonymous()` or declare a constructor for it. However, the code still has access to read the enclosing instance state according to inner class rules.

### 13.2. Difference from a lambda

A lambda placed inside an instance method uses `this` according to its **lexical context** (usually the outer object). In an anonymous class, `this` is the **anonymous object**. A lambda also has no class body where you can place an instance field initializer/initializer block using anonymous class syntax.

## 14. With an Interface: Constructor Arguments Are Always Empty

When creating an anonymous class that implements an interface:

~~~java
Runnable action = new Runnable() {
    {
        System.out.println("initialized");
    }

    @Override
    public void run() {
    }
};
~~~

`Runnable` is an interface and has no constructor for you to call with arguments. `new Runnable() { ... }` uses empty parentheses. The anonymous class has Object as its direct superclass and implements Runnable.

**Invalid:**

~~~java
// Runnable action = new Runnable(42) {
//     public void run() { }
// };
~~~

You cannot pass `42` as an argument to a Runnable constructor. If you want to use a value from the caller, use a **captured effectively final local variable**, or create a named class/constructor accepting the value, or a factory returning Runnable.

With **a class as the superclass**, `new Base(args) { ... }` can have arguments matching Base's constructors.

## 15. Program: Superclass Arguments and Anonymous Initializers

Save **`AnonymousArgumentDemo.java`**:

~~~java
public class AnonymousArgumentDemo {
    static abstract class Report {
        private final String title;

        Report(String title) {
            this.title = title;
            System.out.println("base title=" + title);
        }

        String title() {
            return title;
        }

        abstract String render();
    }

    public static void main(String[] args) {
        int extra = 4;

        Report report = new Report("Sales") {
            private final int count = extra + 1;

            {
                System.out.println("anonymous count=" + count);
            }

            @Override
            String render() {
                return title() + ":" + count;
            }
        };

        System.out.println("render=" + report.render());
    }
}
~~~

Run:

~~~bash
javac AnonymousArgumentDemo.java
java AnonymousArgumentDemo
~~~

Output:

~~~text
base title=Sales
anonymous count=5
render=Sales:5
~~~

- The `Report(String)` constructor processes `"Sales"`.
- The anonymous class initializes `count` itself from the captured local `extra`.
- The anonymous initializer block prints count only after the superclass constructor has completed.
- `render()` can read the inherited `title()` method and the anonymous field `count`.

There is no valid place to add `Report(String) { ... }` inside the anonymous class to "override the constructor."

## 16. Instance Initializers Can Run Validation and Throw Exceptions

An anonymous initializer block can check invariants:

~~~java
Runnable job = new Runnable() {
    private final int amount = 5;

    {
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
    }

    @Override
    public void run() {
    }
};
~~~

If validation fails and the block throws an exception, the creation expression **does not return a successfully initialized object** to the caller. Any initializers placed after the exception **are not executed**.

### 16.1. Fail-fast program with deterministic stdout

Save **`AnonymousInitializerFailureDemo.java`**:

~~~java
public class AnonymousInitializerFailureDemo {
    static Runnable create(int input) {
        return new Runnable() {
            private final int amount = input;

            {
                System.out.println("checking=" + amount);
                if (amount < 0) {
                    throw new IllegalArgumentException(
                            "amount must be nonnegative");
                }
                System.out.println("validated");
            }

            @Override
            public void run() {
                System.out.println("run amount=" + amount);
            }
        };
    }

    public static void main(String[] args) {
        Runnable valid = create(2);
        valid.run();

        try {
            create(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("creation rejected");
        }
    }
}
~~~

Run:

~~~bash
javac AnonymousInitializerFailureDemo.java
java AnonymousInitializerFailureDemo
~~~

Output:

~~~text
checking=2
validated
run amount=2
checking=-1
creation rejected
~~~

The `validated` line is **not** printed for the second creation because the exception halts initialization. There is no `run amount=-1` because the creation expression does not complete normally.

### 16.2. Avoid turning an initializer into a workflow with heavy side effects

If the block opens resources, registers listeners, or writes global state and then fails at a later step, there is a risk of leaving side effects behind even though object creation failed. Use a factory/try-with-resources/cleanup transaction if initialization is no longer straightforward.

## 17. Checked Exceptions: A Special Case of Anonymous Initializers

This is a point easily confused with named classes.

JLS §11.2.3 allows **an instance variable initializer or instance initializer of an anonymous class** to throw checked exceptions. The compiler generates an **implicit anonymous constructor with the appropriate `throws` clause**, so the site where `new ... { ... }` is written must catch or declare the checked exception.

It is incorrect to claim that "an initializer block can never throw IOException because an anonymous class has no constructor `throws`." It is precisely the **implicit anonymous constructor** that resolves this constraint.

### 17.1. Program: checked exception from a field initializer

Save **`AnonymousCheckedExceptionDemo.java`**:

~~~java
import java.io.IOException;

public class AnonymousCheckedExceptionDemo {
    static String load(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("simulated input failure");
        }
        return "loaded";
    }

    static Runnable create(boolean fail) throws IOException {
        return new Runnable() {
            private final String text = load(fail);

            {
                System.out.println("initialized=" + text);
            }

            @Override
            public void run() {
                System.out.println("run=" + text);
            }
        };
    }

    public static void main(String[] args) {
        try {
            Runnable good = create(false);
            good.run();
        } catch (IOException unexpected) {
            System.out.println("unexpected input failure");
        }

        try {
            create(true);
        } catch (IOException expected) {
            System.out.println("creation failed with IOException");
        }
    }
}
~~~

Run:

~~~bash
javac AnonymousCheckedExceptionDemo.java
java AnonymousCheckedExceptionDemo
~~~

Output:

~~~text
initialized=loaded
run=loaded
creation failed with IOException
~~~

`load(true)` throws IOException while the **field initializer** is executing. The block printing `initialized=...` comes after that field, so it does not run on the failure branch. The `create` method declares `throws IOException` so the compiler allows propagation of the checked exception from the anonymous class creation expression.

### 17.2. Checked exception from a block is also valid

Example snippet:

~~~java
Runnable job = new Runnable() {
    {
        if (someFailureCondition()) {
            throw new java.io.IOException("failed");
        }
    }

    @Override
    public void run() {
    }
};
~~~

This is a **snippet with an undefined placeholder method `someFailureCondition()`**, intended to illustrate the throw location; if putting it into real code, replace it with a valid boolean/condition and handle IOException at the creation site. The anonymous block **does not need** to declare `throws` because a block has no explicit method/constructor signature.

Remember the distinction: `Runnable.run()` does not allow overriding `run() throws IOException` due to the interface contract, whereas a checked exception in an **initializer during object creation** is a separate matter from a checked exception in the **`run` method**.

## 18. Superclass Constructor Failure Prevents Initializers from Running

If the superclass constructor throws before completing, the anonymous subclass instance initializers **do not execute**.

### 18.1. Verification program

Save **`AnonymousSuperFailureDemo.java`**:

~~~java
public class AnonymousSuperFailureDemo {
    static abstract class Base {
        Base(boolean fail) {
            System.out.println("base constructor");
            if (fail) {
                throw new IllegalStateException("base failure");
            }
        }

        abstract void run();
    }

    public static void main(String[] args) {
        try {
            Base item = new Base(true) {
                private final int value = printValue();

                private int printValue() {
                    System.out.println("anonymous field");
                    return 1;
                }

                @Override
                void run() {
                    System.out.println(value);
                }
            };

            item.run();
        } catch (IllegalStateException expected) {
            System.out.println("caught base failure");
        }
    }
}
~~~

Run:

~~~bash
javac AnonymousSuperFailureDemo.java
java AnonymousSuperFailureDemo
~~~

Output:

~~~text
base constructor
caught base failure
~~~

There is no `anonymous field` line because the Base constructor throws an exception before starting the anonymous subclass field initializer. The caller does not receive a successfully constructed instance.

## 19. Each `new` Creates an Instance and Runs Its Own Initializer

An anonymous class is declared once in source, yet it can be instantiated **multiple times**, for example each time a factory method is called. Each instance will have its own instance fields and perform instance initialization.

### 19.1. Program observing two creations

Save **`AnonymousMultipleInstancesDemo.java`**:

~~~java
public class AnonymousMultipleInstancesDemo {
    private static int nextId;

    static Runnable create() {
        return new Runnable() {
            private final int id = ++nextId;

            {
                System.out.println("init id=" + id);
            }

            @Override
            public void run() {
                System.out.println("run id=" + id);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = create();
        Runnable b = create();

        System.out.println("different instances=" + (a != b));
        a.run();
        b.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousMultipleInstancesDemo.java
java AnonymousMultipleInstancesDemo
~~~

Output:

~~~text
init id=1
init id=2
different instances=true
run id=1
run id=2
~~~

`nextId` is a static field of the enclosing class to demonstrate assigning IDs; you **should not** use unsynchronized ++ for a production concurrent counter.

Two distinct `Runnable` instances are created from **the same anonymous class declaration**, yet each time the field initializer/initializer block runs separately.

## 20. Why Not Use a Static Initializer Instead of a Constructor?

In Java 17, an anonymous class body can contain static members/initializers under the Java 16+ rules for inner classes; many older Java 8 articles describe different restrictions. However:

- **Static initialization** is initialization of the **class**, not of **each instance**.
- Even though declaring a static member is valid at the current source level, it does not give the anonymous class an explicit constructor.
- If the goal is to validate/set up **instance state**, use a field/instance initializer.
- Static mutable state in an anonymous class can make objects share a dependency on one variable, causing coupling and concurrency issues.
- When static logic actually makes sense, a **named static nested class** is usually easier to read and use than an anonymous class.

### 20.1. Conceptual comparison

~~~java
Runnable a = new Runnable() {
    private int count = 1;

    {
        count++; // Per instance.
    }

    @Override
    public void run() {
        System.out.println(count);
    }
};
~~~

This is a snippet with its own value in the block. Do not mistake `count` for a class-level static field; it belongs to the anonymous object `a`.

## 21. An Anonymous Class Cannot Name Itself to Call New Methods Through an Interface

Consider:

~~~java
Runnable task = new Runnable() {
    private int count = 2;

    private void increase() {
        count++;
    }

    @Override
    public void run() {
        increase();
        System.out.println(count);
    }
};
~~~

The caller sees the `task` variable as having compile-time type **Runnable**, so only members accessible through Runnable/Object (and other methods per type resolution) can be called. You cannot simply write `task.increase()` when `increase` does not belong to Runnable; moreover, it is a private method of the anonymous class.

If you need to expose a custom API with a constructor, fields, and additional methods, declare an explicit **named class** or interface. Do not use an anonymous class as a way to "define an unnamed public type."

### 21.1. `var` in Java 17 is not a long-term API solution

Local variable type inference `var` sometimes infers the anonymous type and the compiler may allow operations on appropriate non-private members, but this approach easily makes code depend on the anonymous implementation shape and does not produce a class name usable in other APIs. Keep implementation details hidden behind an interface if you only need behavior through the interface.

## 22. Resource Initialization: Guarding Against Mid-Way Failure

An instance initializer is often used to configure a small anonymous object. However, if the block:

1. Registers a callback into a registry.
2. Opens a file/socket or adds a listener.
3. Then encounters an exception before completing the implicit constructor.

Then **the earlier side effect may already have occurred** even though the object was not returned to the caller. This poses a risk of *this escape* and resource leaks.

### 22.1. Anti-pattern: letting `this` escape from an initializer

~~~java
java.util.List<Runnable> listeners = new java.util.ArrayList<>();

Runnable callback = new Runnable() {
    private int ready;

    {
        listeners.add(this); // Callback is published before construction finishes.
        ready = 1;
    }

    @Override
    public void run() {
        System.out.println(ready);
    }
};
~~~

The code above is a snippet **illustrating an anti-pattern** and should not be used as a design template. If the registry/event bus invokes the callback **immediately upon add** or on another thread, it may observe the object before `ready` is assigned. The Java Memory Model also has rules about safe publication; an initializer `this` escape makes reasoning harder.

### 22.2. A safer approach

~~~java
Runnable callback = new Runnable() {
    private final int ready = 1;

    @Override
    public void run() {
        System.out.println(ready);
    }
};

listeners.add(callback);
~~~

This snippet requires a `listeners` variable declared in the appropriate scope. Here the callback is configured before being **published** to the registry. If the registry runs concurrently across threads, appropriate thread-safe publication/coordination is still needed.

**Lesson:** an anonymous initializer is suitable for setting up internal state, not for automatically executing all lifecycle-related side effects.

## 23. Program: Publishing After the Anonymous Object Has Been Constructed

Save **`AnonymousSafeRegistrationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousSafeRegistrationDemo {
    public static void main(String[] args) {
        List<Runnable> listeners = new ArrayList<>();

        Runnable listener = new Runnable() {
            private final String label;

            {
                label = "READY";
                System.out.println("initialized " + label);
            }

            @Override
            public void run() {
                System.out.println("callback " + label);
            }
        };

        listeners.add(listener);
        System.out.println("registered=" + listeners.size());

        for (Runnable callback : listeners) {
            callback.run();
        }
    }
}
~~~

Run:

~~~bash
javac AnonymousSafeRegistrationDemo.java
java AnonymousSafeRegistrationDemo
~~~

Output:

~~~text
initialized READY
registered=1
callback READY
~~~

Through the output order, the callback is configured before registration. In real-world Java, you also need to manage **unregister/dispose/close** if the registry retains the callback longer than the owner's lifetime.

## 24. Initializing a Value from Mutable Input: Snapshot or Live Reference?

An anonymous class can have a field initializer:

~~~java
final String title = builder.toString();
~~~

If `builder` is a captured effectively-final StringBuilder reference, `title` is a **String snapshot** at the time of object creation. Conversely:

~~~java
final StringBuilder shared = builder;
~~~

`shared` is the same mutable StringBuilder object; external code mutating builder can change the result afterward.

Both are valid field initializers, yet they have different **ownership semantics**. The `final` keyword guarantees that the field reference cannot be reassigned after initialization; it does not make a mutable referent immutable.

### 24.1. Snapshot and live program

Save **`AnonymousCaptureSnapshotDemo.java`**:

~~~java
public class AnonymousCaptureSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");

        Runnable task = new Runnable() {
            private final String snapshot = source.toString();
            private final StringBuilder live = source;

            @Override
            public void run() {
                System.out.println("snapshot=" + snapshot);
                System.out.println("live=" + live);
            }
        };

        source.append("B");
        task.run();
    }
}
~~~

Run:

~~~bash
javac AnonymousCaptureSnapshotDemo.java
java AnonymousCaptureSnapshotDemo
~~~

Output:

~~~text
snapshot=A
live=AB
~~~

Field `snapshot` holds an immutable String created during object initialization, whereas `live` holds a reference to the mutable StringBuilder. Even though both fields are final, their observability differs.

## 25. Instance Initializers and Method Overrides: Do Not Call Behavior Too Early

A superclass constructor calling an overridable method is a risk we already saw in section 12. Inside an **anonymous initializer block**, you should also avoid calling overridable methods without control, because:

- It may invoke methods overridden via inheritance.
- The method may read uninitialized fields declared after the block.
- It may publish `this` through callbacks.
- If the method modifies external state or throws an exception, object creation becomes harder to manage.

For a simple anonymous class that just overrides an interface method, the initializer can compute final fields and validate; letting complex business behavior run **after creation completes** is clearer.

### 25.1. Evaluation table

| Need | Appropriate place | Why |
| --- | --- | --- |
| Compute a single value | Field initializer | Less boilerplate, clear dependency |
| Assign blank `final` in several steps | Instance initializer block | Executes when the object is created |
| Simple input validation | Field/helper + block | Fail-fast, error occurs at creation |
| Need superclass state | Constructor arguments / accessible superclass methods | Follows the constructor chain |
| Invoke business-specific operations | Method override or factory after creation | Avoids side effects during init |
| Register a listener with a bus | After `new` in owner/factory | Avoids `this` escape; clear lifecycle |
| Resource needing cleanup on failure | Named class/factory/try-with-resources | Easier exception safety |
| Need constructor overloads | Named subclass | Anonymous constructors cannot be declared |

## 26. Can an Anonymous Class Be Created with Multiple Interfaces?

An anonymous class expression specifies only **a single superclass type or a single interface type** after `new`. It does not have an arbitrary `implements I1, I2` clause like a named class declaration.

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
    }
};
~~~

If you need to implement multiple interfaces, choose a named class or a superclass/interface that already combines the appropriate contracts. This does not change the instance initialization rules: field initializers and instance blocks remain the way to set up state for an anonymous object.

## 27. Example: Anonymous Subclass with a Superclass Having a final Field

The superclass can have a constructor that sets immutable state, and then the anonymous subclass has its own field:

~~~java
class Base {
    final int id;

    Base(int id) {
        this.id = id;
    }
}
~~~

Anonymous subclass:

~~~java
Base value = new Base(7) {
    private final int twice = id * 2;
};
~~~

`id` has already been assigned by the superclass constructor beforehand, so the `twice` field initializer reads 7 and computes 14. However, a caller holding a `Base` reference cannot directly access `twice` if Base does not expose a corresponding accessor.

### 27.1. Runnable program with method override

Save **`AnonymousInheritedStateDemo.java`**:

~~~java
public class AnonymousInheritedStateDemo {
    static class Base {
        protected final int id;

        Base(int id) {
            this.id = id;
        }

        int score() {
            return id;
        }
    }

    public static void main(String[] args) {
        Base instance = new Base(7) {
            private final int twice = id * 2;

            @Override
            int score() {
                return twice;
            }
        };

        System.out.println("id=" + instance.id);
        System.out.println("score=" + instance.score());
    }
}
~~~

Run:

~~~bash
javac AnonymousInheritedStateDemo.java
java AnonymousInheritedStateDemo
~~~

Output:

~~~text
id=7
score=14
~~~

The superclass manages `id` via its constructor, and the anonymous initializer computes `twice` afterward. This is an example of two classes sharing initialization responsibilities, without needing an explicit anonymous constructor.

## 28. Checked Exception vs. Unchecked Exception: Handling Table

| Error source | Exception | Must declare/catch the checked exception? |
| --- | --- | --- |
| Anonymous field initializer calls `load() throws IOException` | `IOException` (checked) | Yes, at the `new` expression / enclosing method |
| Anonymous instance block `throw new IOException(...)` | `IOException` (checked) | Yes, the compiler records it on the implicit anonymous constructor |
| Field initializer performs `1 / 0` at runtime | `ArithmeticException` (unchecked) | Not required to declare |
| Validation block throws `IllegalArgumentException` | Unchecked | Not required to declare |
| Superclass constructor declared `throws IOException` | Checked | Yes, at `new Base(args){...}` |
| Overridden `Runnable.run()` attempts `throws IOException` | Signature error | Cannot add a broader checked exception than the original method |

**Key point:** a checked exception in **anonymous initialization** can be supported by the language rules **via the implicit constructor**, yet the caller still has the responsibility to handle it. A checked exception in an **overridden method** must separately obey overriding rules.

## 29. Testing: Verifying That the Initializer Runs Exactly Once

Use a simple counter/interface to self-verify:

- Each `new` causes the initializer to run exactly once if creation completes.
- Calling `run()` multiple times does not re-execute the initializer.
- The superclass constructor completes before anonymous initializers.
- Field dependencies follow source order.
- Validation failure halts initialization.
- Checked exceptions are caught at the creation site.
- Fields assigned via `final` are not mutated.
- No `this` escape before completion.
- Do not confuse an anonymous class's prototype/type name with Runtime class metadata.

### 29.1. Contract test program

Save **`AnonymousInitializerContractTest.java`**:

~~~java
public class AnonymousInitializerContractTest {
    private static int initialized;

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static Runnable make() {
        return new Runnable() {
            private final int value;

            {
                value = 10;
                initialized++;
            }

            @Override
            public void run() {
                check(value == 10, "value");
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = make();
        check(initialized == 1, "first initialization");

        first.run();
        first.run();
        check(initialized == 1, "run does not reinitialize");

        Runnable second = make();
        check(initialized == 2, "second initialization");
        check(first != second, "distinct instances");

        second.run();
        System.out.println("anonymous initializer checks passed");
    }
}
~~~

Run:

~~~bash
javac AnonymousInitializerContractTest.java
java AnonymousInitializerContractTest
~~~

Output:

~~~text
anonymous initializer checks passed
~~~

Here the `check` method always executes, without depending on Java `assert` (which is disabled by default when `-ea` is not used). Do not rely on garbage collection, reflection on compiler synthetic names, or thread execution order.

## 30. Quick Comparison with Named Subclasses and Lambdas

### 30.1. Named class

~~~java
final class NamedJob implements Runnable {
    private final int limit;

    NamedJob(int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException("limit");
        }
        this.limit = limit;
    }

    @Override
    public void run() {
        System.out.println(limit);
    }
}
~~~

This is a valid named class snippet inside an appropriate source file. With a named class, the explicit constructor has signature `NamedJob(int)`, can be overloaded, declare `throws`, call `super(...)` per constructor rules, and be tested directly.

### 30.2. Anonymous class

~~~java
int limit = 10;

Runnable job = new Runnable() {
    private final int configured;

    {
        configured = limit;
    }

    @Override
    public void run() {
        System.out.println(configured);
    }
};
~~~

Here there is no constructor declaration with its own name. State is configured using a captured effectively final value and an initializer block.

### 30.3. Lambda

~~~java
int limit = 10;
Runnable job = () -> System.out.println(limit);
~~~

A lambda is more concise when you only need to implement **functional interface behavior** and capture a few local values. It does not allow a class-declaration-style body with field initializers/instance initializer blocks like an anonymous class.

**Choose the right tool:** if you need multiple dedicated fields, instance initialization, and overriding several methods, an anonymous class may make sense; if you need a complex constructor API, a named class is usually better; if there is only a single function behavior, a lambda is usually clearest.

## 31. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "An anonymous class has no constructor, so it has no init." | There is an **implicit** anonymous constructor; field/instance initializers still run. |
| "You can declare `Runnable() { ... }` in an anonymous body." | Explicit constructors cannot be declared. |
| "The `{...}` block only runs when `run()` is called." | Instance initializers run during object creation. |
| "Field initializers run before the superclass constructor." | The opposite: the superclass constructor finishes before anonymous initializers. |
| "All field initializers finish before the blocks run." | Field initializers and blocks run **interleaved in source order**. |
| "Every time a method is called, the initializer re-runs." | It only runs when creating a new instance. |
| "`final` fields must always be assigned right at their declaration." | A blank final can be validly assigned inside an instance initializer. |
| "Creating an anonymous class from an interface can pass constructor args." | No; an interface has no constructor accepting args. |
| "Creating an anonymous subclass cannot call a superclass constructor with args." | You can write `new Base(args){...}` if the constructor is valid. |
| "An anonymous initializer cannot throw a checked exception." | The JLS allows it; the compiler generates a corresponding `throws` on the anonymous constructor. |
| "A checked exception in init is the same as a checked exception in Runnable.run()." | No; overriding method throws rules apply separately. |
| "`this` inside an anonymous initializer is the enclosing Outer." | `this` is the anonymous object; for Outer, use `Outer.this` if valid. |
| "A forward reference via `this.field` means the field is already initialized." | It can read the **default value** if the field initializer has not run yet. |
| "Calling a helper method waits until fields are ready." | The helper is called immediately when the initializer invokes it; it may read defaults. |
| "When the superclass calls an overridden method, subclass fields are ready." | It may dispatch early before anonymous initializers run. |
| "A static initializer can replace a constructor for each anonymous instance." | Static init is class-level; instance initializers are what run per-instance. |
| "An anonymous class does not create a new object." | Each successful `new` creates a new instance. |
| "A final reference to a StringBuilder makes the builder immutable." | Final locks the reference; the mutable referent can still be changed. |
| "You can safely publish `this` inside a block at all times." | It can cause the object to escape before it is fully constructed. |
| "A caller using a Runnable variable can call any private method in the anonymous class." | Only members accessible via the compile-time type; private helpers are not exposed. |
| "`var` gives an anonymous class a stable name usable outside the method." | It does not create a public class name/API. |
| "A Throwable from an initializer always has a fixed stack trace." | No; test exception type/behavior, do not rely on uncommitted messages/traces. |

## 32. Checklist for Reviewing Anonymous Initialization Code

1. Is the supertype an interface or a class? Are the constructor arguments valid?
2. Is an explicit constructor accidentally declared in the anonymous body?
3. Which fields need an initialization expression and which fields need a block?
4. Is there any `final` field not properly assigned along every normal path?
5. Are there multiple instance blocks/field initializers? Does the source order match the dependencies?
6. Is any field read before its initializer, especially via `this.field`/helper methods?
7. Does the superclass constructor call an overridable method where the anonymous override needs uninitialized state?
8. Is there a captured local that is no longer effectively final?
9. Are outer `this` and anonymous `this` confused?
10. For IOException/checked exceptions from the initializer, does the creation site have a valid catch/throws?
11. If the superclass constructor throws, does the code assume the anonymous block still runs?
12. Is the `run()` method mistakenly called before construction completes?
13. Does a `return` statement appear directly inside an initializer block?
14. Is there an initializer that cannot complete normally due to an unconditional throw/loop?
15. Are there resource/registry/listener side effects in init? If it fails, how is cleanup handled?
16. Does `this` escape to a thread/registry during init?
17. If a field initializer captures a mutable object, do you need a live reference or a snapshot?
18. Does the code rely on a synthetic class name/field name instead of public semantics?
19. Is the anonymous implementation small enough to read easily, or does it need a named class/factory?
20. Do the tests distinguish creation time from method invocation time?

## 33. Review Questions and Answers

**Question 1.** Can an anonymous class declare a constructor named `Runnable` or `Base` in its body?  
**Answer:** No. An anonymous class constructor is always declared **implicitly**.

**Question 2.** If you want to assign `int count=3` for each instance, what do you use?  
**Answer:** An instance field initializer, or a valid instance initializer block.

**Question 3.** When does `{ count++; }` directly inside an anonymous class body run?  
**Answer:** During the creation of each instance, after the superclass constructor in source order.

**Question 4.** If `run()` is called three times, does the instance initializer run three times?  
**Answer:** No, unless you create three separate objects; calling a method does not re-initialize.

**Question 5.** Which runs first: the superclass constructor or the anonymous field initializer?  
**Answer:** The superclass constructor.

**Question 6.** Do two instance blocks run in source order?  
**Answer:** Yes, interleaved with field initializers in declaration order inside the anonymous body.

**Question 7.** Can a blank final field be assigned in an instance initializer?  
**Answer:** Yes; it must follow definite assignment and cannot be reassigned.

**Question 8.** Is `new Runnable(5){...}` valid?  
**Answer:** No; the Runnable interface has no constructor accepting arguments.

**Question 9.** Is `new Base("X"){...}` valid?  
**Answer:** Yes, if the Base class has a matching accessible constructor and subclassing rules are satisfied.

**Question 10.** If the superclass constructor throws, does the anonymous block run?  
**Answer:** It does not run if the superclass constructor did not complete normally.

**Question 11.** Why can an overridden method called from a superclass constructor see field = 0?  
**Answer:** Java dynamic dispatch happens before the anonymous field initializer, so the field still holds its default value.

**Question 12.** What value can `int first=this.second; int second=7;` produce for first?  
**Answer:** `first=0`, because field second has not yet been assigned 7 at the time it is read.

**Question 13.** Is `int first=second; int second=7;` using a simple name before declaration valid?  
**Answer:** Restricted by JLS §8.3.3; this case is a compile-time forward-reference error.

**Question 14.** Does calling `readSecond()` from a field initializer automatically complete all initializers?  
**Answer:** No. The method may read default values of the remaining fields.

**Question 15.** Can an anonymous initializer throw IOException?  
**Answer:** Yes. The compiler includes the checked exception in `throws` on the implicit anonymous constructor.

**Question 16.** Who must catch/declare IOException from an initializer?  
**Answer:** The creation expression context/caller method according to exception-checking rules.

**Question 17.** Can you declare `public void run() throws IOException` when implementing Runnable?  
**Answer:** No, because it exceeds the checked exceptions permitted by `Runnable.run()`.

**Question 18.** Is `this` inside an anonymous class the Outer object?  
**Answer:** No; `this` is the anonymous object.

**Question 19.** With what syntax do you read an enclosing Outer field when valid?  
**Answer:** `Outer.this.field` or appropriate resolution, if there is an enclosing Outer instance.

**Question 20.** Does `final StringBuilder builder` protect builder from mutation?  
**Answer:** No. It fixes the reference, yet the builder object remains mutable.

**Question 21.** What risk can passing `this` into a registry inside an initializer cause?  
**Answer:** The object may be observed before initialization completes; escape should be avoided.

**Question 22.** Can you write `return;` directly inside an instance initializer block?  
**Answer:** No, JLS §8.6 prohibits return statements.

**Question 23.** Can an anonymous block consist solely of a `throw` that always executes?  
**Answer:** If the block cannot complete normally under compile-time reachability, it is rejected.

**Question 24.** If you need multiple constructor overloads and a public API, anonymous class or named class?  
**Answer:** A named class is usually appropriate.

**Question 25.** If you only need a simple callback, are a field initializer/instance block necessary?  
**Answer:** Usually you can use a lambda and captured values; an anonymous class is not required.

**Question 26.** Why does the `after-new` log print after initializer logs?  
**Answer:** The object creation expression must complete before the next statement executes.

**Question 27.** Does each factory call creating an anonymous instance run the initializer?  
**Answer:** Yes, on every successful `new` execution.

**Question 28.** Why does the type of the `Runnable action` variable not expose private fields of the anonymous class?  
**Answer:** The variable's compile-time type is Runnable, and private members are not part of the interface API.

**Question 29.** Can you register a listener after the object has finished building?  
**Answer:** Yes, and it is usually safer since the initializer does not let `this` escape.

**Question 30.** What general order should you memorize?  
**Answer:** **Constructor arguments → allocation/defaults → superclass constructor → anonymous field/instance initializers in source order → creation completes → caller uses object**.

## 34. References

- Java Language Specification (Java SE 17), [§15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): anonymous class declarations and allowed class bodies.
- Java Language Specification, [§15.9.5.1 — Anonymous Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5.1): implicit constructor, superclass arguments, and checked exception list.
- Java Language Specification, [§12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): order of constructor/instance field initializers and blocks.
- Java Language Specification, [§8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): field initializer semantics.
- Java Language Specification, [§8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): self/forward references.
- Java Language Specification, [§8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): initializer blocks and return restrictions.
- Java Language Specification, [§11.2.3 — Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): special checked exception handling for anonymous instance initializers.
- Java Language Specification, [§15.9.3 — Choosing Constructor and Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.3): choosing the superclass constructor.
- Java Language Specification, [§15.9.4 — Run-Time Evaluation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.4): how creation expressions are evaluated.
- Java Language Specification, [§8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): an anonymous class is an inner class.
- Java Language Specification, [§4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final local variables/fields.
- Java Language Specification, [§16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): blank final fields.

## Summary

**An anonymous class does not have a named explicit constructor**, yet the Java compiler still provides an **implicit anonymous constructor** to create the object and call the superclass constructor. Inside the anonymous class body, developers can use **instance field initializers** and **instance initializer blocks** to set up fields, assign `final` state, perform validation, and carry out valid initialization steps.

The initialization order determines the result: the superclass constructor runs first, and then the anonymous class's field initializers/instance blocks run **in order of appearance**. If the superclass constructor calls an overridden method too early, the override may observe fields still holding their default values. If an initializer throws an exception, creation fails; checked exceptions are still handled by the compiler via the implicit anonymous constructor, and the creation site must catch/declare them.

Keep initializers **small, with clear dependencies, and without publishing `this` before construction finishes**. For complex resource/constructor logic, prefer a named class or factory. For simple callbacks, a lambda may be cleaner. Properly understanding **implicit constructor + field initializer + instance block + superclass order** is the key to reading and writing anonymous classes accurately in Java 17+.
