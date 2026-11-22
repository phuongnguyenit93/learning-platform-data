# Anonymous Classes: Extending a Class or Implementing an Interface in Java 17+

**An anonymous class** allows defining **a class with no name in source code** while simultaneously creating an instance of it via a **class instance creation expression**. Anonymous classes are used to:

1. **Extend a class** — it can be a regular class or an abstract class, provided that the class is not `final`, has an accessible constructor, and satisfies inheritance rules.
2. **Implement an interface** — providing the methods that remain abstract according to the interface's contract.

The two most important patterns:

~~~java
Runnable work = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

~~~java
Animal animal = new Animal("Milo") {
    @Override
    String sound() {
        return "woof";
    }
};
~~~

In the first pattern, the anonymous class **implements Runnable**, whereas in the second pattern, the anonymous class **extends Animal**. Both create an **object of an anonymous class** rather than a pure object of the interface/abstract class. The caller typically holds the reference through the **supertype**.

This lesson belongs to **Java Core — class-object / Anonymous Classes**, applicable to **Java 17+**. Complete programs include the file name, `javac`/`java` commands, and expected stdout. Snippets that intentionally cause a compile error are commented to distinguish them from runnable code.

## 1. Objectives

After completing this lesson, you will be able to:

- Recognize the `new Interface() { ... }` and `new Base(args) { ... }` syntax.
- Understand that an anonymous class is a **real class**, having runtime Class metadata but no simple name in the source.
- Distinguish between the declared class and the object instance created by the expression.
- Know that an anonymous class **directly extends a class or implements an interface** according to the type specified at the start of the expression.
- Understand why you cannot write `new Interface()` or `new AbstractClass()` without providing a body that implements the abstract methods.
- Use `@Override`, interface method contracts, and dynamic dispatch.
- Invoke the super constructor using constructor arguments in the expression.
- Understand that an anonymous class cannot declare a named constructor, but can use an instance initializer.
- Know that an anonymous class can have its own fields/methods, though a supertype reference cannot call methods outside the contract.
- Use anonymous classes in callbacks, `Comparator`, `Runnable`, strategy objects, or custom overrides.
- Distinguish between `this`, `super`, and `Outer.this`.
- Understand capturing `final` or `effectively final` local variables/parameters.
- Distinguish between modifying a mutable captured object and reassigning the reference.
- Distinguish between an anonymous class and a **lambda expression**.
- Know how an anonymous class differs from a **local named class**, a **member inner class**, and a **static nested class**.
- Understand the limitations: `final` classes, `sealed` types, type/access restrictions, and checked exceptions.
- Use generics and diamond syntax properly with Java 17.
- Understand type identity, equality, scope, memory retention, and thread safety.
- Write tests verifying dispatch, capture, constructor args, and callback behavior.

## 2. What Is an Anonymous Class Really?

In a regular declaration, we give the class a name:

~~~java
class NamedRunner implements Runnable {
    @Override
    public void run() {
        System.out.println("run");
    }
}
~~~

Then we create the object:

~~~java
Runnable r = new NamedRunner();
~~~

An anonymous class combines declaring an unnamed subclass/implementation into the instance creation expression:

~~~java
Runnable r = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
~~~

The runtime class of `r` is not the `Runnable` interface (an interface cannot be instantiated directly). It is a **generated anonymous implementation class** of Runnable.

### Relationship Diagram

~~~text
     Interface Runnable
             ^
             | implements
             |
    Anonymous class #1
             ^
             | instance-of
             |
          object r
~~~

If you use `new Base(...) { ... }`, the anonymous class has Base as its superclass. A Java class can inherit from at most **one superclass**, though it can implement multiple interfaces via a normal class declaration; the anonymous class syntax only chooses **one direct type** in the part before the body (class or interface).

## 3. First Program: Implementing an Interface

Create **`AnonymousRunnableDemo.java`**:

~~~java
public class AnonymousRunnableDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            @Override
            public void run() {
                System.out.println("Hello from anonymous class");
            }
        };

        task.run();

        System.out.println("anonymous=" +
                task.getClass().isAnonymousClass());
        System.out.println("runnable=" +
                (task instanceof Runnable));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousRunnableDemo.java
java AnonymousRunnableDemo
~~~

Stdout:

~~~text
Hello from anonymous class
anonymous=true
runnable=true
~~~

The line `new Runnable() { ... }` creates an object of an anonymous class implementing Runnable. The line `task.run()` dispatches to the overridden run method in the anonymous implementation.

## 4. Syntax for Implementing an Interface

Full pattern:

~~~java
InterfaceType variable = new InterfaceType() {
    @Override
    public ReturnType method(Parameters parameters) {
        // implementation
    }
};
~~~

Notes:

- `InterfaceType` is an interface type, **not a constructor** of the interface that can actually be called.
- The `()` in `new InterfaceType()` does not pass arguments to an interface constructor; interfaces do not have instance constructors like classes do.
- The body `{ ... }` is the class body of the anonymous class, where you implement the required methods.
- After the closing body `}`, an expression statement/variable initializer typically has a semicolon `;`.
- An interface with one or multiple abstract methods can be implemented by an anonymous class, provided they are fully implemented with matching signatures.
- If the interface already has `default` methods, the anonymous class can inherit the default behavior or override it.

### One Interface, Multiple Methods

Example of a domain interface:

~~~java
interface Formatter {
    String format(String value);

    boolean accepts(String value);
}
~~~

The anonymous implementation must provide both `format` and `accepts`, unless a method has a default implementation or is resolved through other type rules.

## 5. Runnable Program: Interface with Multiple Abstract Methods

Create **`AnonymousFormatterDemo.java`**:

~~~java
public class AnonymousFormatterDemo {
    interface Formatter {
        boolean accepts(String input);
        String format(String input);
    }

    public static void main(String[] args) {
        Formatter formatter = new Formatter() {
            @Override
            public boolean accepts(String input) {
                return input != null && !input.isBlank();
            }

            @Override
            public String format(String input) {
                if (!accepts(input)) {
                    return "INVALID";
                }
                return input.strip().toUpperCase(
                        java.util.Locale.ROOT);
            }
        };

        System.out.println(formatter.format(" java "));
        System.out.println(formatter.format("  "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousFormatterDemo.java
java AnonymousFormatterDemo
~~~

Stdout:

~~~text
JAVA
INVALID
~~~

The Formatter interface is not a functional interface because it has two abstract methods, yet an anonymous class can still implement it. A lambda cannot directly implement an interface with two unrelated abstract methods; an anonymous class has a broader scope of use in this regard.

## 6. An Anonymous Class Can Extend an Abstract Class

When you have an abstract base class:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

You cannot write `new Shape()` without an anonymous subclass body because Shape is abstract. However, you can write:

~~~java
Shape shape = new Shape() {
    @Override
    double area() {
        return 10.0;
    }
};
~~~

The expression creates **an instance of a concrete anonymous subclass of Shape**.

### Dynamic Dispatch

When calling `shape.area()`, the variable `shape` has the declared type Shape; the JVM selects the implementation of the actual anonymous subclass via dynamic dispatch. This is normal Java OOP polymorphism, not a special exception for anonymous classes.

## 7. Runnable Program: Extending an Abstract Class

Create **`AnonymousShapeDemo.java`**:

~~~java
public class AnonymousShapeDemo {
    static abstract class Shape {
        abstract int area();
    }

    public static void main(String[] args) {
        Shape rectangle = new Shape() {
            @Override
            int area() {
                return 3 * 4;
            }
        };

        Shape square = new Shape() {
            @Override
            int area() {
                return 5 * 5;
            }
        };

        System.out.println("rectangle=" + rectangle.area());
        System.out.println("square=" + square.area());
        System.out.println("different objects=" +
                (rectangle != square));
        System.out.println("same class=" +
                (rectangle.getClass() == square.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousShapeDemo.java
java AnonymousShapeDemo
~~~

Stdout:

~~~text
rectangle=12
square=25
different objects=true
same class=false
~~~

The two `new Shape() { ... }` expressions are at **two different source locations**, so they are **two different anonymous class declarations**, not merely two objects from one declaration. Therefore, `getClass() ==` is false in the example.

## 8. Extending a Concrete Class to Change Behavior

The superclass **does not have to be abstract**. An anonymous subclass can override a virtual method of a concrete class as long as the class is not final and the method can be overridden.

~~~java
class Greeter {
    String message() {
        return "Hello";
    }
}

Greeter custom = new Greeter() {
    @Override
    String message() {
        return "Xin chao";
    }
};
~~~

`custom` is still used under the declared type Greeter. `custom.message()` calls the override in the anonymous subclass.

### When Is It Useful?

- Replacing part of the behavior of an abstract/concrete base that has a clear contract.
- Creating a local customization instead of declaring a named subclass elsewhere.
- Writing a small test double or callback adapter.

However, if you override many methods or have complex behavior, a named class is usually easier to debug/test/read.

## 9. Runnable Program: Overriding a Concrete Method

Create **`AnonymousConcreteSubclassDemo.java`**:

~~~java
public class AnonymousConcreteSubclassDemo {
    static class Greeter {
        String message(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) {
        Greeter standard = new Greeter();

        Greeter custom = new Greeter() {
            @Override
            String message(String name) {
                return "Xin chao, " + name;
            }
        };

        System.out.println(standard.message("Mai"));
        System.out.println(custom.message("Mai"));
        System.out.println("custom is subclass=" +
                (custom.getClass() != Greeter.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousConcreteSubclassDemo.java
java AnonymousConcreteSubclassDemo
~~~

Stdout:

~~~text
Hello, Mai
Xin chao, Mai
custom is subclass=true
~~~

`new Greeter() { ... }` is an object of an anonymous subclass, not a pure Greeter base instance. It is still `instanceof Greeter`, because the subclass inherits the base type.

## 10. Can One Anonymous Class Declaration Create Multiple Instances?

An anonymous class does not have a simple name for a caller to write `new AnonymousClassName()` elsewhere. However, **the same source expression** can be executed multiple times, for example inside a factory method:

~~~java
static Runnable newTask(String message) {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(message);
        }
    };
}
~~~

Each call to `newTask` creates a new object of **the same anonymous class definition** at that source location. Unlike the example with two `new Shape() { ... }` expressions at two source locations, this case has the same runtime Class metadata for the same declaration in the same defining-class-loader context.

## 11. Runnable Program: Same Anonymous Class, Multiple Objects

Create **`AnonymousFactoryDemo.java`**:

~~~java
public class AnonymousFactoryDemo {
    static Runnable newTask(String message) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(message);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = newTask("A");
        Runnable b = newTask("B");

        System.out.println("same object=" + (a == b));
        System.out.println("same class=" +
                (a.getClass() == b.getClass()));

        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousFactoryDemo.java
java AnonymousFactoryDemo
~~~

Stdout:

~~~text
same object=false
same class=true
A
B
~~~

The two different anonymous instances have different captured message values, yet have the same class definition created at a single source location.

## 12. Superclass Constructor in an Anonymous Class

An anonymous class **has no name to declare its own constructor**. If it extends a class whose constructor requires arguments, pass the arguments in the expression:

~~~java
Base value = new Base("A", 7) {
    @Override
    void execute() {
        // ...
    }
};
~~~

Object creation invokes **a matching superclass constructor** for the arguments according to Java's class instance creation and constructor resolution rules.

However, you **do not** declare:

~~~java
// Inside the anonymous class body:
// Anonymous(...) { ... } // There is no class name to define a constructor.
~~~

If separate initialization is needed for the anonymous class's fields, you can use field initializers or an instance initializer block. If initialization is complex, a named subclass/copy factory is usually clearer.

## 13. Runnable Program: Superclass Constructor Parameters

Create **`AnonymousConstructorDemo.java`**:

~~~java
public class AnonymousConstructorDemo {
    static abstract class Job {
        private final String label;

        Job(String label) {
            this.label = label;
            System.out.println("base constructor:" + label);
        }

        String label() {
            return label;
        }

        abstract String result();
    }

    public static void main(String[] args) {
        Job job = new Job("compile") {
            @Override
            String result() {
                return label() + ":done";
            }
        };

        System.out.println(job.result());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousConstructorDemo.java
java AnonymousConstructorDemo
~~~

Stdout:

~~~text
base constructor:compile
compile:done
~~~

`new Job("compile") { ... }` calls Job(String) before the object completes initialization. The anonymous subclass overrides the result method and inherits label().

**Constructor override dispatch warning:** If a superclass constructor calls an overridable method, the call can dispatch to the subclass override **before the subclass fields are fully initialized**. Avoid that pattern.

## 14. Instance Initializer in an Anonymous Class

An anonymous class can declare an instance initializer:

~~~java
Runnable runner = new Runnable() {
    private int runs;

    {
        runs = 10;
    }

    @Override
    public void run() {
        System.out.println(++runs);
    }
};
~~~

The instance initializer runs when the instance is created, following Java initialization order, and before the instance is normally used. It **does not replace** the superclass constructor.

### Runnable Program

Create **`AnonymousInitializerDemo.java`**:

~~~java
public class AnonymousInitializerDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int count;

            {
                count = 10;
                System.out.println("initialized");
            }

            @Override
            public void run() {
                count++;
                System.out.println("count=" + count);
            }
        };

        task.run();
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousInitializerDemo.java
java AnonymousInitializerDemo
~~~

Stdout:

~~~text
initialized
count=11
count=12
~~~

An anonymous class has its own instance state. You do not need a lambda or static globals to manage a counter if the state is tied to each callback instance.

## 15. Anonymous Classes Have Fields, Helper Methods, and Private State

The body of an anonymous class can contain valid members just like a regular class: instance fields, methods, initializers, and (depending on the Java version) static declarations, provided they comply with context rules.

Example:

~~~java
Runnable task = new Runnable() {
    private int count;

    private void increment() {
        count++;
    }

    @Override
    public void run() {
        increment();
        System.out.println(count);
    }
};
~~~

A client with a `Runnable` reference can call `run()`, and cannot directly call `increment()` or access count because those members are not part of Runnable's public API.

**Important:** Having an anonymous-class-only method does not mean the caller automatically sees the method through the declared supertype.

## 16. Runnable Program: Internal Fields and Helpers

Create **`AnonymousStateDemo.java`**:

~~~java
public class AnonymousStateDemo {
    static Runnable counter() {
        return new Runnable() {
            private int count;

            private void next() {
                count++;
            }

            @Override
            public void run() {
                next();
                System.out.println("call=" + count);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = counter();
        Runnable b = counter();

        a.run();
        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousStateDemo.java
java AnonymousStateDemo
~~~

Stdout:

~~~text
call=1
call=2
call=1
~~~

Each anonymous instance has its own `count` state. The two instances do not share the count field, even though they were created by the same anonymous class declaration in the factory method.

## 17. Declared Type Determines Which Members the Caller Can Invoke

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }

    public void extra() {
        System.out.println("extra");
    }
};
~~~

`task.extra()` **does not compile** because the compiler looks at the declared type Runnable, which does not have an extra() method. The anonymous runtime object has the extra method, but a Runnable-typed reference only exposes Runnable methods.

### Using a Supertype for Encapsulation

In practice, this is often an advantage: the anonymous class is just an implementation detail; the client uses the interface/base class contract. If the caller genuinely needs extra behavior, add it to **an appropriate interface** or use a named class rather than relying on reflection.

### Useful Exception: `var` and Anonymous Type Inference

In Java 10+ local variable inference, `var example = new Object() { String extra() {...} };` can retain the inferred anonymous class type within the variable's scope, allowing the extra() member to be called according to typing rules. However, this pattern is rarely suitable for a public API; do not build a system that depends on anonymous-specific members from outside the method.

## 18. Runnable Example: Local `var` Retains an Anonymous-Specific Method

Create **`AnonymousVarDemo.java`**:

~~~java
public class AnonymousVarDemo {
    public static void main(String[] args) {
        var value = new Object() {
            String describe() {
                return "anonymous-only";
            }
        };

        System.out.println(value.describe());
        System.out.println("anonymous=" +
                value.getClass().isAnonymousClass());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AnonymousVarDemo.java
java AnonymousVarDemo
~~~

Stdout:

~~~text
anonymous-only
anonymous=true
~~~

`var` infers the anonymous class type within the local scope. If you change it to `Object value = new Object() { ... };`, then `value.describe()` will not compile because Object does not have describe(). You should not mistake this inference convenience for a mechanism to expose an anonymous class type in a public API.

## 19. `@Override` Checks the Method Signature

You should use `@Override` when implementing an interface method or overriding a superclass method:

~~~java
Runnable r = new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

Benefits:

- The compiler detects an incorrect method name/signature.
- Avoids creating a new method due to a typo instead of overriding the intended method.
- Clarifies the polymorphic contract for the reader.

### Visibility When Implementing an Interface

Interface abstract methods are public by default in most common cases; the implementation must be `public`:

~~~java
new Runnable() {
    @Override
    public void run() {
        System.out.println("ok");
    }
};
~~~

If you write `void run()` without public, the compiler will reject it because you cannot reduce the visibility of a public method in Runnable.

## 20. Runnable Program: Interface with a Default Method

Create **`AnonymousDefaultMethodDemo.java`**:

~~~java
public class AnonymousDefaultMethodDemo {
    interface Messenger {
        String name();

        default String message() {
            return "Hello, " + name();
        }
    }

    public static void main(String[] args) {
        Messenger messenger = new Messenger() {
            @Override
            public String name() {
                return "Mai";
            }
        };

        System.out.println(messenger.name());
        System.out.println(messenger.message());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousDefaultMethodDemo.java
java AnonymousDefaultMethodDemo
~~~

Stdout:

~~~text
Mai
Hello, Mai
~~~

The anonymous class only implements `name()`; the default `message()` can be inherited and invokes name() via dynamic dispatch.

## 21. `this` in an Anonymous Class

Inside an instance method of an anonymous class:

- `this` points to **the anonymous class instance itself**.
- `this` does **not** automatically point to the outer class object.
- In an outer instance context, `Outer.this` refers to the enclosing outer instance if valid.
- `super` refers to the behavior of the **anonymous class's superclass** if extending a class, not the enclosing outer class.

This is an important difference compared to a lambda. In a lambda, `this` is resolved according to the lexical enclosing context and does not create an “anonymous callback instance” meaning like an anonymous class body does.

## 22. Quick Distinction Between `this` and `Outer.this` When Implementing an Interface

An anonymous class implementing an interface is **a different class/instance** from the enclosing owner. Example Java 17 snippet:

~~~java
class Owner {
    private final String id = "A";

    Runnable makeTask() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        this.getClass().isAnonymousClass());
                System.out.println(Owner.this.id);
            }
        };
    }
}
~~~

If you create and execute `new Owner().makeTask().run()` in an appropriate program, the two lines will be `true` and `A`, respectively. `this` refers to the callback instance, while `Owner.this` refers to the instance of the enclosing class. **Enclosing** is different from **superclass**: this anonymous callback implements `Runnable`, and does not extend `Owner`.

The lesson “Meaning of this and Accessing the Enclosing Object” explores multiple levels of nesting, shadowing, and lifecycle in depth. Here, this brief comparison only serves to safeguard the understanding of extends/implements.

## 23. `super` When an Anonymous Class Extends a Class

Suppose a concrete superclass has a greet() method:

~~~java
class Greeter {
    String greet() {
        return "Hello";
    }
}

Greeter custom = new Greeter() {
    @Override
    String greet() {
        return super.greet() + " Java";
    }
};
~~~

In the override, `super.greet()` calls the implementation of the superclass Greeter according to Java rules. It does not call a method of an enclosing outer object.

### Runnable Program

Create **`AnonymousSuperDemo.java`**:

~~~java
public class AnonymousSuperDemo {
    static class Greeter {
        String greet() {
            return "Hello";
        }
    }

    public static void main(String[] args) {
        Greeter custom = new Greeter() {
            @Override
            String greet() {
                return super.greet() + " Java";
            }
        };

        System.out.println(custom.greet());
        System.out.println("superclass Greeter=" +
                (custom.getClass().getSuperclass() ==
                        Greeter.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousSuperDemo.java
java AnonymousSuperDemo
~~~

Stdout:

~~~text
Hello Java
superclass Greeter=true
~~~

The anonymous class extends Greeter and can use protected/accessible inherited behavior according to inheritance rules.

## 24. Capturing Local Variables and Parameters

An anonymous class declared inside a method/block can use enclosing method locals/parameters if they are **final or effectively final**:

~~~java
static Runnable task(String name) {
    int repeat = 2;

    return new Runnable() {
        @Override
        public void run() {
            for (int i = 0; i < repeat; i++) {
                System.out.println(name);
            }
        }
    };
}
~~~

`name` and `repeat` are not reassigned; the code is valid. `repeat` is a captured primitive value, and `name` is a captured String reference to immutable text.

Note that captured local variables can be used after the method has returned, because the anonymous object is still retained by the caller. The compiler/JVM implements capture semantics rather than relying on direct access to a terminated stack frame.

## 25. Runnable Program: Capturing Effectively-Final Locals

Create **`AnonymousCaptureDemo.java`**:

~~~java
public class AnonymousCaptureDemo {
    static Runnable task(String text) {
        int times = 2;

        return new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < times; i++) {
                    System.out.println(text);
                }
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = task("A");
        Runnable b = task("B");

        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
~~~

Stdout:

~~~text
A
A
B
B
~~~

Each instance captures the value of text from the invocation that created it. `times` is effectively final even though `final` is not written.

## 26. Why Can't a Captured Local Be Reassigned?

~~~java
static Runnable invalid() {
    int count = 1;
    count++;

    return new Runnable() {
        @Override
        public void run() {
            // System.out.println(count); // Compile error if uncommented.
            System.out.println("count unavailable");
        }
    };
}
~~~

`count++` causes the variable to lose its effectively final status. If the anonymous class reads count, javac rejects the capture.

### Solutions

- If you want a fixed value, compute it beforehand and capture it into a variable **that is not reassigned**.
- If you want separate mutable state for the anonymous object, declare a field inside the anonymous class.
- If multiple instances need to share mutable state in a controlled manner, pass an explicit state holder with appropriate synchronization/ownership.
- Do not use a single-element array just to “work around” effectively final while ignoring thread-safety and API clarity.

## 27. Capturing a Mutable Reference Does Not Freeze the Object

~~~java
java.util.List<String> names = new java.util.ArrayList<>();

Runnable r = new Runnable() {
    @Override
    public void run() {
        names.add("Java");
    }
};
~~~

`names` is not reassigned, so it is effectively final; however, the `ArrayList` object remains mutable. When run() is called, the List changes.

### Runnable Program

Create **`AnonymousMutableCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousMutableCaptureDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();

        Runnable append = new Runnable() {
            @Override
            public void run() {
                names.add("Java");
            }
        };

        append.run();
        append.run();

        System.out.println(names);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousMutableCaptureDemo.java
java AnonymousMutableCaptureDemo
~~~

Stdout:

~~~text
[Java, Java]
~~~

**Effectively final ≠ immutable ≠ thread-safe.** The capture rule only restricts reassignment of the variable; it does not prohibit mutating the mutable object it points to.

## 28. Anonymous Class vs Lambda: Syntax

With a functional interface:

~~~java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("A");
    }
};

Runnable lambda = () -> System.out.println("B");
~~~

Both can be used as a Runnable callback. However, they are not always semantically equivalent:

- An anonymous class defines a class body; a lambda is a **lambda expression** type-checked against a target functional interface.
- Anonymous `this` is the anonymous object; lambda `this` is the lexical enclosing receiver (if any).
- An anonymous class can implement an interface with **multiple abstract methods**; a lambda requires a functional interface.
- An anonymous class can extend a concrete/abstract class; a lambda does not extend an arbitrary class.
- An anonymous class has instance fields, instance initializers, and helper methods; a lambda body does not declare an anonymous class body of the same kind.
- The runtime Class metadata/caching/identity mechanism of a lambda should not be assumed to be identical to that of an anonymous class.

## 29. Runnable Program: Anonymous Callback and Lambda

Create **`AnonymousVsLambdaDemo.java`**:

~~~java
public class AnonymousVsLambdaDemo {
    static void execute(Runnable runnable) {
        runnable.run();
    }

    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };

        Runnable lambda = () -> System.out.println("lambda");

        execute(anonymous);
        execute(lambda);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousVsLambdaDemo.java
java AnonymousVsLambdaDemo
~~~

Stdout:

~~~text
anonymous
lambda
~~~

In cases where you only run a single line and do not need state/helpers/inheritance, a lambda is usually shorter and clearer. For multiple methods, superclass constructor arguments, or a class body that needs fields, an anonymous class remains useful.

## 30. Differences in `this` Between an Anonymous Class and a Lambda

You cannot replace `new Runnable() { ... }` with `() -> ...` solely based on the target type being `Runnable`. Check the **receiver and type contract**:

| Inside the callback | Anonymous class | Lambda |
| --- | --- | --- |
| `this` | Current anonymous instance | Lexical enclosing instance (if any) |
| `Outer.this` | Enclosing Outer if in a valid context | Also follows the lexical enclosing context |
| Separate instance field declared by the callback | Available in the anonymous class body | No separate class body to declare a field |
| `super.method()` | Superclass of the anonymous class | `super` according to the lexical enclosing class |
| Inside a static method | The anonymous instance still has `this` | No enclosing `this` available to use |

For the **interface implementation** topic we are studying, the first thing to determine is whether the API expects an object carrying its own state or merely a single function of a functional interface. When the body of an anonymous class uses `this` to retain/unregister the callback, switching to a lambda can change the reference target. The dedicated anonymous–lambda comparison lesson has runnable examples and stdout for each context; those programs should not be duplicated here.

## 31. Anonymous Class vs Local Named Class

**Local named class:**

~~~java
void method() {
    class LocalRunner implements Runnable {
        public void run() {
            System.out.println("run");
        }
    }

    Runnable a = new LocalRunner();
    Runnable b = new LocalRunner();
}
~~~

**Anonymous class:**

~~~java
void method() {
    Runnable a = new Runnable() {
        public void run() {
            System.out.println("run");
        }
    };
}
~~~

LocalRunner has a **name inside the block**, can declare explicit constructors, and can create multiple instances via `new LocalRunner()`. An anonymous class has no class name in source; if you want to create the same type multiple times, you typically place the expression inside a factory method that runs multiple times.

If the implementation is long or needs to be reused within a block, a local named class is clearer. If it is only a one-off customization at a single expression, an anonymous class may be appropriate.

## 32. Anonymous Class Extending an Abstract Adapter Class

Some APIs/frameworks define an adapter base class with concrete/default implementations so that clients only need to override the method they care about:

~~~java
abstract class ListenerAdapter {
    void onStart() {}
    void onStop() {}
}
~~~

An anonymous subclass can override the exact hook:

~~~java
ListenerAdapter listener = new ListenerAdapter() {
    @Override
    void onStart() {
        System.out.println("started");
    }
};
~~~

This is an example of **extending a class**, not implementing an interface. Be sure to distinguish interface `default` methods from concrete methods of an adapter superclass.

### Runnable Program

Create **`AnonymousAdapterDemo.java`**:

~~~java
public class AnonymousAdapterDemo {
    static class ListenerAdapter {
        void onStart() {
        }

        void onStop() {
        }
    }

    public static void main(String[] args) {
        ListenerAdapter listener = new ListenerAdapter() {
            @Override
            void onStart() {
                System.out.println("started");
            }
        };

        listener.onStart();
        listener.onStop();
        System.out.println("completed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousAdapterDemo.java
java AnonymousAdapterDemo
~~~

Stdout:

~~~text
started
completed
~~~

`onStop()` is inherited from the base class so it prints nothing, yet the invocation is valid.

## 33. Polymorphism: Declared Type vs Runtime Type

The snippet:

~~~java
Shape shape = new Shape() {
    @Override
    double area() {
        return 5;
    }
};
~~~

has three layers:

1. `Shape` is the **declared type** of the reference variable.
2. `new Shape() { ... }` is the **anonymous subclass declaration + instance creation**.
3. `shape.area()` dispatches to the implementation in the runtime anonymous subclass.

Dynamic dispatch does not depend on the variable name or file name, but rather on the actual receiver class and override resolution.

### `instanceof`

An anonymous subclass instance is also an instance of the supertype:

~~~java
System.out.println(shape instanceof Shape); // true
~~~

You cannot write `shape instanceof AnonymousClassName` because there is no source name for an anonymous class.

## 34. Object Identity and Equality

If there are two distinct expressions:

~~~java
Runnable a = new Runnable() { public void run() {} };
Runnable b = new Runnable() { public void run() {} };
~~~

`a == b` is false; the two `new` expressions create different objects. Each anonymous class is also a separate runtime class declaration.

If the anonymous class does not override `equals`, the default Object.equals is based on identity. Having two callbacks print the same line does not make them equal by value.

You should not override equals/hashCode on anonymous callbacks arbitrarily; callback registration/unregistration APIs typically rely on **the exact object reference** that was registered. Store the reference to unregister accurately.

## 35. Runnable Program: Identity and Class Metadata

Create **`AnonymousIdentityDemo.java`**:

~~~java
public class AnonymousIdentityDemo {
    public static void main(String[] args) {
        Runnable first = new Runnable() {
            @Override
            public void run() {
            }
        };

        Runnable second = new Runnable() {
            @Override
            public void run() {
            }
        };

        System.out.println("same object=" + (first == second));
        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
        System.out.println("first anonymous=" +
                first.getClass().isAnonymousClass());
        System.out.println("second anonymous=" +
                second.getClass().isAnonymousClass());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousIdentityDemo.java
java AnonymousIdentityDemo
~~~

Stdout:

~~~text
same object=false
same class=false
first anonymous=true
second anonymous=true
~~~

These are **two anonymous class declarations at two source locations**, so they have different runtime Class objects. In contrast, the factory example in the previous section had a single expression executed twice, so the Class was the same.

## 36. Cannot Extend a `final` Class

An anonymous class is a **subclass** when the expression names a class. However, a `final` class does not allow any subclass:

~~~java
final class ImmutableValue {
}

// ImmutableValue x = new ImmutableValue() { }; // Compile error.
~~~

You can still create an instance of the final class normally:

~~~java
ImmutableValue x = new ImmutableValue();
~~~

Only the anonymous subclass body `{ ... }` requires subclassing and is forbidden.

### Why Is This Commonly Encountered with String?

`String` is final. You cannot write `new String("A") { ... }` to override String methods. If you need different behavior, use composition/helper/service instead of inheritance.

## 37. `sealed` Classes and Interfaces in Java 17

Java 17 supports sealed types that restrict which direct subclasses/implementations are permitted. An anonymous class does not have a source-level simple class name to be listed in the usual way in a permits clause.

Conceptual example:

~~~java
sealed interface Result permits Success, Failure {}

final class Success implements Result {}

final class Failure implements Result {}

// Result r = new Result() { }; // Not allowed as a direct anonymous implementation.
~~~

If you want to create a result according to the permitted model, instantiate a permitted concrete class, or design a non-sealed extension point in the hierarchy if the domain needs to allow extensions.

**Do not assume:** “Because an anonymous class has no name, it is exempt from sealed restrictions.” It is still a direct subclass/implementation within the type rules system.

## 38. Abstract Methods and Compile-Time Obligations

When extending an abstract class with multiple abstract methods, the anonymous class must provide **all concrete implementations** that have not yet been resolved by the superclass hierarchy.

~~~java
abstract class Converter {
    abstract String encode(String s);
    abstract String decode(String s);
}
~~~

Anonymous subclass:

~~~java
Converter c = new Converter() {
    @Override
    String encode(String s) {
        return s.toUpperCase(java.util.Locale.ROOT);
    }

    @Override
    String decode(String s) {
        return s.toLowerCase(java.util.Locale.ROOT);
    }
};
~~~

If `decode` is missing, the compiler rejects it because an anonymous class must be a concrete class that gets instantiated. An anonymous class does not allow you to attach the `abstract` modifier and create an abstract object.

## 39. Runnable Program: Implementing the Entire Abstract Contract

Create **`AnonymousConverterDemo.java`**:

~~~java
public class AnonymousConverterDemo {
    static abstract class Converter {
        abstract String encode(String text);
        abstract String decode(String text);
    }

    public static void main(String[] args) {
        Converter converter = new Converter() {
            @Override
            String encode(String text) {
                return text.toUpperCase(java.util.Locale.ROOT);
            }

            @Override
            String decode(String text) {
                return text.toLowerCase(java.util.Locale.ROOT);
            }
        };

        System.out.println(converter.encode("Java"));
        System.out.println(converter.decode("JAVA"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousConverterDemo.java
java AnonymousConverterDemo
~~~

Stdout:

~~~text
JAVA
java
~~~

An abstract class can also contain concrete methods and fields that the anonymous subclass inherits.

## 40. Can an Anonymous Class Directly Implement More Than One Interface?

An anonymous class expression has **one type in the `new Type(...)` part**. There is no syntax:

~~~java
// new Runnable(), AutoCloseable() { ... } // Does not exist.
~~~

If you need an object that implements both Runnable and AutoCloseable, define a named interface that extends both:

~~~java
interface ManagedTask extends Runnable, AutoCloseable {
}
~~~

Then create the anonymous implementation:

~~~java
ManagedTask task = new ManagedTask() {
    @Override
    public void run() {
        System.out.println("run");
    }

    @Override
    public void close() {
        System.out.println("close");
    }
};
~~~

The anonymous class has the direct superinterface ManagedTask, and ManagedTask extends Runnable and AutoCloseable. Therefore, an anonymous object can implement **multiple interface contracts through a single interface type**; the limitation is that the `new` clause specifies one type and does not allow listing multiple directly.

## 41. Runnable Program: Interface Extending Multiple Interfaces

Create **`AnonymousMultipleContractsDemo.java`**:

~~~java
public class AnonymousMultipleContractsDemo {
    interface ManagedTask extends Runnable, AutoCloseable {
    }

    public static void main(String[] args) throws Exception {
        ManagedTask task = new ManagedTask() {
            @Override
            public void run() {
                System.out.println("work");
            }

            @Override
            public void close() {
                System.out.println("closed");
            }
        };

        System.out.println("runnable=" +
                (task instanceof Runnable));
        System.out.println("closeable=" +
                (task instanceof AutoCloseable));
        task.run();
        task.close();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousMultipleContractsDemo.java
java AnonymousMultipleContractsDemo
~~~

Stdout:

~~~text
runnable=true
closeable=true
work
closed
~~~

One object satisfies both contracts because the ManagedTask interface extends both. If an API requires a complex nominal intersection type, a named interface is usually clearer and more usable for a public API.

## 42. Interface vs Superclass Constructors

The syntax can look similar, but the semantics differ:

~~~java
Runnable task = new Runnable() {
    public void run() {
    }
};
~~~

`Runnable` is an interface and has no instance constructor arguments. The anonymous class has Object as its superclass and implements Runnable.

~~~java
Base task = new Base(42) {
    @Override
    void execute() {
    }
};
~~~

`Base` is a class; `Base(42)` selects an appropriate accessible superclass constructor. The anonymous subclass extends Base.

### Constructor Selection Errors

If Base only has `Base(int)`, writing `new Base() { ... }` will fail because there is no accessible no-arg constructor. Fix it with appropriate arguments or use a named factory.

## 43. Generic Interfaces with Anonymous Implementation

Anonymous classes support parameterized target interfaces:

~~~java
java.util.function.Supplier<String> supplier =
        new java.util.function.Supplier<String>() {
            @Override
            public String get() {
                return "Java";
            }
        };
~~~

No raw types are needed. The compiler checks that `get()` returns String. Diamond syntax can reduce repeating type arguments in cases allowed by Java 17.

### Runnable Program

Create **`AnonymousGenericInterfaceDemo.java`**:

~~~java
import java.util.function.Supplier;

public class AnonymousGenericInterfaceDemo {
    public static void main(String[] args) {
        Supplier<String> words = new Supplier<String>() {
            @Override
            public String get() {
                return "Java";
            }
        };

        Supplier<Integer> number = new Supplier<>() {
            @Override
            public Integer get() {
                return 17;
            }
        };

        System.out.println(words.get());
        System.out.println(number.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AnonymousGenericInterfaceDemo.java
java AnonymousGenericInterfaceDemo
~~~

Stdout:

~~~text
Java
17
~~~

`new Supplier<>() { ... }` with diamond is valid in Java 17 (diamond syntax with anonymous classes has been supported since Java 9), but it must obey the typing restrictions of anonymous classes with diamond.

## 44. Diamond Anonymous Classes and Non-Private Methods

When using `new GenericType<>() { ... }` in Java 9+, the compiler places additional restrictions on non-private methods declared in the anonymous class, because those methods need to override a corresponding supertype method under certain conditions. Avoid arbitrarily adding non-overriding public/helper methods when using a diamond anonymous class.

Safe and clear:

~~~java
java.util.function.Supplier<String> supplier =
        new java.util.function.Supplier<>() {
            @Override
            public String get() {
                return "ok";
            }

            private String helper() {
                return "internal";
            }
        };
~~~

This snippet illustrates a private helper (in this example, helper is not called), and a public `get()` overriding Supplier's method.

If you need many public implementation-specific methods, a named class usually provides a better contract.

## 45. Anonymous Class from a Generic Factory Method

A generic method can return an anonymous implementation parameterized by the method's type parameter.

Create **`AnonymousGenericFactoryDemo.java`**:

~~~java
import java.util.function.Supplier;

public class AnonymousGenericFactoryDemo {
    static <T> Supplier<T> fixed(T value) {
        return new Supplier<T>() {
            @Override
            public T get() {
                return value;
            }
        };
    }

    public static void main(String[] args) {
        Supplier<String> text = fixed("Java");
        Supplier<Integer> number = fixed(17);

        System.out.println(text.get());
        System.out.println(number.get());
        System.out.println("same runtime class=" +
                (text.getClass() == number.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousGenericFactoryDemo.java
java AnonymousGenericFactoryDemo
~~~

Stdout:

~~~text
Java
17
same runtime class=true
~~~

Type erasure means the same anonymous class declaration has the same runtime class within a class-loader context, even when the method type arguments differ. The captured value still retains type safety at compile time.

## 46. Anonymous Class in a Static vs Instance Context

An anonymous class written in a static method still has its **own instance `this`**, but **does not have `Outer.this`** naturally from the static method.

~~~java
static Runnable makeStaticTask() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(this.getClass().isAnonymousClass());
        }
    };
}
~~~

In an instance method:

~~~java
Runnable makeInstanceTask() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(Outer.this.toString());
        }
    };
}
~~~

The second snippet is an illustrative snippet inside class Outer. The anonymous instance and the enclosing Outer instance are two different objects.

If a static method needs Outer state, pass an explicit Outer reference and capture it; do not try to use `Outer.this` when there is no enclosing outer instance.

## 47. Runnable Program: Two Creation Contexts

Create **`AnonymousContextsDemo.java`**:

~~~java
public class AnonymousContextsDemo {
    private final String id;

    AnonymousContextsDemo(String id) {
        this.id = id;
    }

    Runnable fromInstance() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("instance:" +
                        AnonymousContextsDemo.this.id);
            }
        };
    }

    static Runnable fromStatic(String name) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("static:" + name);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = new AnonymousContextsDemo("A").fromInstance();
        Runnable b = fromStatic("B");

        a.run();
        b.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousContextsDemo.java
java AnonymousContextsDemo
~~~

Stdout:

~~~text
instance:A
static:B
~~~

Both are anonymous Runnable objects. The difference is that `fromInstance` has an enclosing Outer instance, whereas `fromStatic` only captures the String argument name.

## 48. Do Not Call Overridable Methods in a Base Constructor

A superclass constructor might call a virtual method overridden by an anonymous subclass. In that case, the override runs **before the anonymous subclass state finishes initializing**, leading to unexpected default values or a NullPointerException.

Anti-pattern example (illustrative):

~~~java
class Base {
    Base() {
        initialize(); // Dangerous virtual call inside constructor.
    }

    void initialize() {
    }
}

// Base x = new Base() {
//     private String text = "ready";
//     @Override void initialize() {
//         System.out.println(text.length()); // text may still be null.
//     }
// };
~~~

Use constructors to initialize private/final base state and avoid calling overridable methods before the object finishes construction. If a callback is needed, invoke it after construction completes, via an explicit API.

**Do not confuse:** This issue is not specific to anonymous classes; any subclass and polymorphic constructor dispatch can suffer from it.

## 49. Checked Exceptions and Anonymous Methods

When implementing an interface/overriding a superclass method, the anonymous implementation must obey the `throws` contract:

~~~java
interface Loader {
    String load() throws java.io.IOException;
}
~~~

The anonymous class can implement it:

~~~java
Loader loader = new Loader() {
    @Override
    public String load() throws java.io.IOException {
        throw new java.io.IOException("missing");
    }
};
~~~

A caller through `Loader` must handle or declare IOException. If the method contract does not allow the corresponding checked exception, the implementation cannot arbitrarily add a broader checked exception.

### Runnable Program

Create **`AnonymousCheckedExceptionDemo.java`**:

~~~java
import java.io.IOException;

public class AnonymousCheckedExceptionDemo {
    interface Loader {
        String load() throws IOException;
    }

    public static void main(String[] args) {
        Loader loader = new Loader() {
            @Override
            public String load() throws IOException {
                throw new IOException("missing");
            }
        };

        try {
            System.out.println(loader.load());
        } catch (IOException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousCheckedExceptionDemo.java
java AnonymousCheckedExceptionDemo
~~~

Stdout:

~~~text
error=missing
~~~

An anonymous class does not eliminate checked-exception rules.

## 50. Access Modifiers and Package/Private Contracts

If an anonymous class implements an interface, the method implementation must satisfy the interface's public contract. When overriding a protected method of a superclass, the override can keep protected or broaden accessibility according to the rules, but cannot reduce it.

~~~java
abstract class Base {
    protected abstract String text();
}
~~~

An anonymous subclass can:

~~~java
Base x = new Base() {
    @Override
    protected String text() {
        return "ok";
    }
};
~~~

Accessing `x.text()` from code that is not permitted under protected access rules can still be rejected even though the actual instance overrode it. The declared type and access context determine what the caller sees.

An anonymous class body cannot arbitrarily lower the visibility of inherited public methods.

## 51. Small Test Double / Stub in Unit Tests

An anonymous class is often useful as a **test double** for a small interface:

~~~java
interface RateProvider {
    int centsPerUnit();
}
~~~

In a test, we can create a stub returning a fixed value to verify business logic.

Create **`AnonymousStubDemo.java`**:

~~~java
public class AnonymousStubDemo {
    interface RateProvider {
        int centsPerUnit();
    }

    static int total(RateProvider provider, int units) {
        if (units < 0) {
            throw new IllegalArgumentException("negative units");
        }
        return Math.multiplyExact(provider.centsPerUnit(), units);
    }

    public static void main(String[] args) {
        RateProvider fake = new RateProvider() {
            @Override
            public int centsPerUnit() {
                return 250;
            }
        };

        System.out.println("total=" + total(fake, 3));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousStubDemo.java
java AnonymousStubDemo
~~~

Stdout:

~~~text
total=750
~~~

The stub does not use an external network/database and satisfies the RateProvider contract, allowing you to test the total-amount logic. For multiple behaviors/cases, a named fake class or mocking framework may be easier to maintain.

## 52. Comparator Anonymous Class

`Comparator<T>` is a functional interface, so a lambda can be used; however, an anonymous class is still valid and useful when the comparator needs helper methods or state.

Create **`AnonymousComparatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class AnonymousComparatorDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(
                List.of("Java", "Go", "Python"));

        Comparator<String> byLength = new Comparator<String>() {
            @Override
            public int compare(String a, String b) {
                return Integer.compare(a.length(), b.length());
            }
        };

        names.sort(byLength);
        System.out.println(names);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousComparatorDemo.java
java AnonymousComparatorDemo
~~~

Stdout:

~~~text
[Go, Java, Python]
~~~

If multiple strings have the same length, their relative order during sorting is stable according to the List.sort contract. The code uses Integer.compare to avoid integer subtraction overflow in a general comparator.

## 53. Anonymous Class Declared at an Argument Position

You do not have to assign an anonymous instance to a variable; you can pass it directly to a method:

~~~java
static void execute(Runnable task) {
    task.run();
}

execute(new Runnable() {
    @Override
    public void run() {
        System.out.println("direct");
    }
});
~~~

It still creates an anonymous class instance and passes the reference value to the method. Java parameter passing is always pass-by-value, even when the argument is an anonymous object.

### Runnable Program

Create **`AnonymousArgumentDemo.java`**:

~~~java
public class AnonymousArgumentDemo {
    static void execute(Runnable task) {
        task.run();
    }

    public static void main(String[] args) {
        execute(new Runnable() {
            @Override
            public void run() {
                System.out.println("direct");
            }
        });
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousArgumentDemo.java
java AnonymousArgumentDemo
~~~

Stdout:

~~~text
direct
~~~

For a very short callback for a functional interface, a lambda can also make sense: `execute(() -> System.out.println("direct"));`. Choose based on readability and behavior requirements, not just line count.

## 54. An Anonymous Class Can Access Private Outer Members

An anonymous class declared in an **instance context** can access private outer members according to Java nesting access rules. It can read/write mutable outer state if the logic allows.

Example:

~~~java
class Wallet {
    private int cents;

    Runnable depositTask(int amount) {
        return new Runnable() {
            @Override
            public void run() {
                cents += amount;
            }
        };
    }
}
~~~

However, direct addition can break invariants/overflow and is not thread-safe. A good design should **delegate through an outer method that validates invariants**:

~~~java
private void deposit(int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("negative");
    }
    cents = Math.addExact(cents, amount);
}
~~~

The anonymous implementation in `depositTask` calls `Wallet.this.deposit(amount)` instead of modifying cents without validation.

## 55. Runnable Program: Callback Protecting Invariants

Create **`AnonymousInvariantDemo.java`**:

~~~java
public class AnonymousInvariantDemo {
    static final class Wallet {
        private int cents;

        private void deposit(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative");
            }
            cents = Math.addExact(cents, amount);
        }

        Runnable depositTask(int amount) {
            return new Runnable() {
                @Override
                public void run() {
                    Wallet.this.deposit(amount);
                }
            };
        }

        int cents() {
            return cents;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet();

        wallet.depositTask(100).run();
        System.out.println("balance=" + wallet.cents());

        try {
            wallet.depositTask(-5).run();
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("after=" + wallet.cents());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousInvariantDemo.java
java AnonymousInvariantDemo
~~~

Stdout:

~~~text
balance=100
rejected=negative
after=100
~~~

An anonymous callback can use private domain logic, but proper encapsulation must reside in Wallet's own logic.

## 56. Memory Retention and Callback Lifecycle

Anonymous instances can hold references to captured objects and the enclosing owner. If a long-lived registry stores a callback without unregistering it, the outer UI/controller/services can remain reachable longer than intended:

~~~text
long-lived event registry
         |
         v
  anonymous callback
         |
         +------> captured service
         |
         +------> enclosing owner (when retained)
~~~

The Java compiler/runtime may represent captured state using fields/synthetic implementation details. Do not rely on the field name `this$0` as an official API.

### Safe Design

- Keep the reference to the registered callback in order to unregister the exact instance.
- Use the `close/dispose/unsubscribe` lifecycle when required by the API.
- Avoid capturing a broad outer object when only a small immutable value is needed.
- Use a static helper/named class if the enclosing owner is not needed.
- Avoid assuming that converting a callback to a lambda automatically eliminates retention; a lambda can also capture references.

## 57. Runnable Program: Unsubscribing the Exact Callback Instance

Create **`AnonymousListenerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousListenerDemo {
    static final class EventBus {
        private final List<Runnable> listeners = new ArrayList<>();

        void add(Runnable listener) {
            listeners.add(listener);
        }

        void remove(Runnable listener) {
            listeners.remove(listener);
        }

        void publish() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        Runnable listener = new Runnable() {
            @Override
            public void run() {
                System.out.println("event");
            }
        };

        bus.add(listener);
        bus.publish();

        bus.remove(listener);
        System.out.println("after unsubscribe");
        bus.publish();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousListenerDemo.java
java AnonymousListenerDemo
~~~

Stdout:

~~~text
event
after unsubscribe
~~~

`remove(listener)` uses a reference to the exact object that was registered. Creating another `new Runnable() { ... }` with the same behavior does not remove the old object.

## 58. Thread Safety of Captured State

An anonymous Runnable can run on another thread. If it captures a mutable List/Map/counter, that object must satisfy an appropriate synchronization/ownership policy.

~~~java
java.util.List<String> list = new java.util.ArrayList<>();
Runnable task = new Runnable() {
    public void run() {
        list.add("x");
    }
};
~~~

This is an illustrative snippet; if run concurrently from multiple threads, ArrayList is not safe. The effective-final rule **is not a synchronization primitive**.

### Using AtomicInteger

Create **`AnonymousAtomicDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AnonymousAtomicDemo {
    public static void main(String[] args) {
        AtomicInteger count = new AtomicInteger();

        Runnable increment = new Runnable() {
            @Override
            public void run() {
                count.incrementAndGet();
            }
        };

        increment.run();
        increment.run();

        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousAtomicDemo.java
java AnonymousAtomicDemo
~~~

Stdout:

~~~text
count=2
~~~

AtomicInteger has atomic increment semantics. This program calls it twice sequentially so stdout is well-defined; in a multithreaded design, coordination/termination must still be considered to read the result at the right time.

## 59. Exceptions in Instance Initializers and Constructor Flow

If extending a class with constructor arguments, the superclass constructor runs according to initialization semantics before the anonymous subclass instance initialization completes. An instance initializer of an anonymous class can throw a runtime exception, causing the expression not to return an object successfully.

### Do Not Publish a Partial Object

An anonymous subclass undergoing initialization should not register `this` in a global registry before finishing its fields/invariants; if initialization fails or another thread runs the callback early, inconsistent state may be observed.

### An Anonymous Class Is Not Mandatory

If creation involves multiple steps requiring validation, checked exceptions, or resource cleanup, a named class/factory is usually clearer. An anonymous class should stay small in scale with localized behavior.

## 60. Serialization Is Not Guaranteed Automatically

An anonymous class instance can be held in an object graph, but you should not assume it is `Serializable`:

- Implementing `Runnable` does not automatically implement `Serializable`.
- Captured/enclosing references may not be serializable.
- Generated anonymous class names may not be stable when the code changes.
- Distributing the serialization format depends on the API/framework contract.

If you need to persist a callback/job/config, typically store an **explicit data/command DTO** and then reconstruct the behavior from named types; do not arbitrarily serialize anonymous runtime implementations.

## 61. Reflection Metadata of an Anonymous Class

An anonymous class object has Class metadata:

- `getClass().isAnonymousClass()` is typically true.
- `getClass().getSimpleName()` is typically an empty string for an anonymous class.
- `getClass().getSuperclass()` reveals the superclass; an anonymous implementation of an interface typically has Object as its superclass.
- `getClass().getInterfaces()` reveals the directly implemented interfaces according to class metadata.
- `getEnclosingClass()`/`getEnclosingMethod()` can describe the lexical declaration location.

**Important:** Reflection metadata does not replace the compiler using the declared type to check method accessibility. Do not parse generated class names for production logic.

## 62. Runnable Program: Reflection Distinguishing implements and extends

Create **`AnonymousMetadataDemo.java`**:

~~~java
public class AnonymousMetadataDemo {
    static class Base {
    }

    public static void main(String[] args) {
        Runnable runnable = new Runnable() {
            @Override
            public void run() {
            }
        };

        Base subclass = new Base() {
        };

        System.out.println("runnable anonymous=" +
                runnable.getClass().isAnonymousClass());
        System.out.println("runnable superclass Object=" +
                (runnable.getClass().getSuperclass() ==
                        Object.class));
        System.out.println("runnable interface Runnable=" +
                (runnable.getClass().getInterfaces()[0] ==
                        Runnable.class));

        System.out.println("subclass anonymous=" +
                subclass.getClass().isAnonymousClass());
        System.out.println("subclass superclass Base=" +
                (subclass.getClass().getSuperclass() ==
                        Base.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousMetadataDemo.java
java AnonymousMetadataDemo
~~~

Stdout:

~~~text
runnable anonymous=true
runnable superclass Object=true
runnable interface Runnable=true
subclass anonymous=true
subclass superclass Base=true
~~~

Each anonymous class still has real runtime type metadata, even though that class cannot be named in source code from elsewhere.

## 63. When to Choose an Anonymous Class?

Choose an anonymous class when:

- A small implementation is specific to one call site.
- You need to **extend a class** and override behavior on the spot.
- The interface has **multiple abstract methods**, so a simple lambda cannot be used.
- The callback needs fields/helpers or a small instance initializer.
- You want to hide the implementation class name and only expose the contract.
- A test needs a short stub/fake interface implementation.

### When Not to Use It?

- The implementation is long and hard to review/debug; use a named local/member/top-level class.
- The behavior is reused across multiple sites; avoid copy-pasting anonymous bodies.
- There is only a single very short functional method; a lambda is usually clearer.
- Explicit constructor validation/complex object lifecycle is needed.
- A public API needs to expose methods not present in the base type.
- Stable serialization/persistence/versioned type names are needed.
- A DI framework/reflection mapping/class discovery needs to operate on a named concrete type.

## 64. Decision Table

| Need | Typically Suitable Option |
| --- | --- |
| Runnable printing one line | Lambda |
| Interface with two abstract methods, short logic | Anonymous class |
| Override an abstract base class method at one call site | Anonymous subclass |
| Small custom instance state inside a callback | Anonymous class or named local class |
| Reuse an implementation in multiple places | Named class |
| Helper not needing outer state and using multiple methods | Static nested class |
| Return an object via a public interface, hide implementation | Anonymous/local named class |
| Framework requiring a stable named class/constructor contract | Named class |
| Large captured state and long-lived listener | Design ownership/cleanup before choosing syntax |
| Base type `final` or sealed disallowing extension | Composition/permitted implementation |

Syntax does not replace contract design. If a behavior must be extended over the long term, naming the class and its responsibility usually aids maintainability.

## 65. Common Misconceptions

| Misconception | What Is True |
| --- | --- |
| “`new Interface() { ... }` directly creates an interface object.” | Creates an anonymous implementation class instance. |
| “An anonymous class has no runtime Class object.” | Still has Class metadata. |
| “All anonymous instances are the same class.” | Only at the same corresponding declaration/site; different sites have different anonymous types. |
| “`new Base() { ... }` is not inheritance.” | The anonymous subclass extends Base. |
| “Only an abstract class can be anonymously extended.” | Concrete non-final classes work as well. |
| “You can anonymously extend a final class.” | Final forbids subclassing. |
| “Sealed types automatically allow anonymous subclasses.” | Must follow permits restrictions. |
| “An anonymous class can omit required abstract methods.” | A concrete anonymous class must implement all of them. |
| “An anonymous class has an explicit named constructor.” | There is no class name to declare a constructor. |
| “The superclass constructor does not run.” | It does, according to constructor invocation semantics. |
| “An anonymous helper method can always be called through an interface variable.” | The declared supertype restricts members. |
| “`this` inside an anonymous class is the outer object.” | This is the anonymous instance. |
| “`super` calls an outer method.” | Super belongs to the superclass of the anonymous class. |
| “An anonymous class in a static method has Outer.this.” | A static context has no outer instance. |
| “A captured local does not need to be effectively final.” | Must be final/effectively final. |
| “A captured mutable List becomes immutable.” | No; only the local reference is not reassigned. |
| “A lambda and an anonymous class have the same this.” | A lambda uses lexical this; an anonymous class uses its own instance this. |
| “An interface with multiple abstract methods can always be written as a lambda.” | A lambda requires a functional interface. |
| “You can write `new A(), B() { ... }`.” | There is no syntax for multiple direct supertypes like that. |
| “Diamond syntax with anonymous classes is not supported in Java 17.” | Supported since Java 9 with restrictions. |
| “`@Override` is unnecessary because the code is short.” | Strongly recommended so the compiler checks the contract. |
| “An anonymous callback object is automatically GC'd after the method returns.” | Registries/captured refs can keep it reachable. |
| “You do not need to save the callback reference to unregister.” | Many APIs require the exact listener instance. |
| “Effectively final guarantees thread safety.” | No; synchronization is separate. |
| “An anonymous class allows adding arbitrary checked exceptions.” | The override throws contract still applies. |

## 66. Exercise 1 — Implementing an Interface

~~~java
Runnable r = new Runnable() {
    @Override
    public void run() {
        System.out.println("A");
    }
};
r.run();
~~~

**Answer:** Prints `A`. The expression creates an anonymous implementation of Runnable and then calls the run method.

## 67. Exercise 2 — Extending an Abstract Class

~~~java
abstract class Animal {
    abstract String sound();
}

Animal a = new Animal() {
    @Override
    String sound() {
        return "meow";
    }
};
~~~

**Question:** Is an Animal abstract object created directly?

**Answer:** No. There is a concrete anonymous subclass extending Animal, and `a.sound()` returns `meow`.

## 68. Exercise 3 — Extending a Concrete Class

~~~java
class Greeting {
    String text() { return "Hello"; }
}

Greeting g = new Greeting() {
    @Override
    String text() { return "Hi"; }
};
~~~

**Answer:** `g.text()` returns `Hi` due to dynamic dispatch. The anonymous class extends concrete Greeting even though Greeting is not abstract.

## 69. Exercise 4 — Two `new` Expressions at Two Source Sites

~~~java
Runnable a = new Runnable() { public void run() {} };
Runnable b = new Runnable() { public void run() {} };
~~~

**Answer:** `a == b` is false, and `a.getClass() == b.getClass()` is false because these are two declarations at two source locations.

## 70. Exercise 5 — Same Factory Site

A method `create()` returns `new Runnable() { ... }` at one source location. If `create()` is called twice, how do identity and runtime class compare?

**Answer:** The two returned objects typically differ in identity, yet share the same anonymous runtime class in the same defining-loader context. Captured values may differ.

## 71. Exercise 6 — Method Present Only in the Anonymous Class

~~~java
Runnable r = new Runnable() {
    public void run() {}
    public void extra() {}
};
// r.extra();
~~~

**Answer:** Uncommenting `r.extra()` will cause a compile error because the declared type Runnable does not have extra(). To expose extra, change the interface contract or use an appropriate named type.

## 72. Exercise 7 — Reassigning a Captured Local

~~~java
int counter = 0;
counter++;

Runnable r = new Runnable() {
    public void run() {
        // System.out.println(counter);
    }
};
~~~

**Answer:** If uncommented, the compiler rejects capturing counter because counter is not effectively final. If you want a mutable per-callback counter, use an instance field inside the anonymous class.

## 73. Exercise 8 — Anonymous `this` and Lambda `this`

In an instance method, an anonymous class method prints `this.getClass().isAnonymousClass()`; a lambda body prints `this.getClass().getSimpleName()`.

**Answer:** Anonymous `this` is the anonymous object; lambda `this` is the enclosing instance of the lexical context. They are not equivalent.

## 74. Exercise 9 — Superclass Constructor

~~~java
abstract class Job {
    Job(String id) {}
    abstract void execute();
}

// new Job() {
//     void execute() {}
// };
~~~

**Answer:** If uncommented, the compiler reports there is no compatible no-arg constructor. You must write `new Job("X") { @Override void execute() {} }` (with valid access).

## 75. Exercise 10 — Choosing Lambda or Anonymous Class?

An interface only has `void run()` and the behavior is printing one line: lambda or anonymous class?

**Answer:** A lambda is usually shorter and clearer. If you need anonymous class identity/instance fields, or multiple abstract methods, an anonymous class may be more suitable.

## 76. Exercise 11 — Sealed Type

Given a `sealed interface Result permits Success, Failure`, is `new Result() { ... }` allowed directly?

**Answer:** No, because an anonymous class is not in the list of permitted direct implementations. Use a permitted concrete class or design another extension point according to the sealed type model.

## 77. Exercise 12 — Callback Lifecycle

You register an anonymous listener on EventBus and later want to unregister it without saving the reference. What is the risk?

**Answer:** You have no reference to the exact instance that was registered; creating a new anonymous listener with the same code is not the same object and may fail to remove the right listener. Save the handle/reference and unregister according to EventBus's contract.

## 78. Quick Check Checklist

- [ ] I distinguish between new Interface() { ... } and new Base(args) { ... }.
- [ ] I know an anonymous class is a real class with no source simple name.
- [ ] I know implementing an interface differs from extending a concrete/abstract class.
- [ ] I know dynamic dispatch reaches the anonymous override.
- [ ] I know abstract methods must be fully implemented.
- [ ] I know methods implementing an interface must be public.
- [ ] I use `@Override` for interface/superclass methods.
- [ ] I know superclass constructors run and receive args in the new expression.
- [ ] I know an anonymous class has no named constructor.
- [ ] I use an instance initializer when truly needed, without leaking partial this.
- [ ] I know anonymous fields/helpers are not automatically accessible through the declared supertype.
- [ ] I understand local `var` can infer an anonymous type in Java 17.
- [ ] I know `this` is the anonymous object, and `Outer.this` is the owner when valid.
- [ ] I know `super` refers to superclass behavior.
- [ ] I know captured locals/parameters must be final or effectively final.
- [ ] I distinguish between a captured primitive snapshot and a mutable object reference.
- [ ] I know lambdas differ in terms of this/capture and the functional-interface requirement.
- [ ] I know an anonymous class can extend a concrete non-final class.
- [ ] I know extending a final class or directly implementing a sealed type is forbidden.
- [ ] I know an anonymous expression specifies only one direct supertype.
- [ ] I know generic interfaces and diamond syntax in Java 17.
- [ ] I do not make a public API depend on the generated anonymous class name.
- [ ] I use reflection `isAnonymousClass()` instead of parsing names.
- [ ] I know the same source expression can create multiple objects of the same runtime class.
- [ ] I know two different source anonymous class expressions have different runtime types.
- [ ] I know captured state/callback registries can extend the owner's lifetime.
- [ ] I keep the exact callback reference to unsubscribe.
- [ ] I know effectively final does not make shared mutable state thread-safe.
- [ ] I obey checked exceptions/visibility/access contracts.
- [ ] I choose a named class when behavior is large or needs reuse/versioning.
- [ ] I can predict stdout and compile errors in the examples.

**Conclusion:** An anonymous class is a Java construct that defines **an unnamed subclass or interface implementation right at the object creation expression**. `new Interface() { ... }` is used to implement an interface; `new Base(args) { ... }` is used to extend a class and invoke the appropriate superclass constructor. An object of an anonymous class still has identity, runtime Class, and dynamic dispatch like other objects. Anonymous classes are well-suited for small customizations/local callbacks, but they cannot replace contract/interface design, constructor safety, capture rules, lifecycle management, or thread safety. For a short functional callback, consider a lambda; for long and reusable behavior, consider a named class.
