# Implementing with local classes and anonymous classes

In Java, **local classes** and **anonymous classes** allow placing an implementation right near where it is used. They are often useful when a method needs a dedicated implementation for an interface or abstract class, but that implementation type does not need to become a top-level class or a member class of another class.

- A **local class** has a name and is declared inside a code block, such as in a method, constructor, or initializer. The class name is valid only within the scope of that block.
- An **anonymous class** does not have a class name given by the programmer. It is declared directly inside an object creation expression using the syntax `new KiểuCha(...) { ... }`.

Both can contain their own fields, methods, and logic. The main differences lie in how they are declared, the scope of the class name, and whether they can declare their own constructors.

## 1. What is a local class?

A local class is a class declared inside a code block. The most common example is declaring a class inside a method:

~~~java
void process() {
    class LocalWorker {
        void work() {
            System.out.println("Đang xử lý");
        }
    }

    LocalWorker worker = new LocalWorker();
    worker.work();
}
~~~

The `LocalWorker` class can only be referenced by name within its declaration scope. Code outside the `process()` method cannot write `new LocalWorker()`, because this name does not exist outside that block.

A local class can:

- Implement one or more interfaces.
- Extend a superclass, including an abstract class.
- Declare its own fields, methods, and constructors.
- Be instantiated into multiple objects if needed within its declaration scope.
- Access members of the outer object when the class is declared in an instance context and has a corresponding outer object.

A local class can also use parameters and local variables of the enclosing method. These variables must be `final` or **effectively final**: after being assigned a value, they are never reassigned. Java guarantees that an object of the local class does not depend on a local variable having been modified afterward.

~~~java
void greet() {
    String prefix = "Xin chào"; // effectively final

    class LocalGreeter {
        String greet(String name) {
            return prefix + ", " + name;
        }
    }

    System.out.println(new LocalGreeter().greet("Lan"));
}
~~~

The example above is valid because `prefix` is not reassigned. If you add `prefix = "Hello";` after its initial assignment, referencing `prefix` inside `LocalGreeter` will cause a compilation error.

## 2. What is an anonymous class?

An anonymous class is an unnamed class declared directly at an object creation expression. It is commonly used to implement an interface or extend an abstract class at a specific location.

Syntax when implementing an interface:

~~~java
Greeter greeter = new Greeter() {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
};
~~~

Syntax when extending an abstract class:

~~~java
TextFormatter formatter = new TextFormatter() {
    @Override
    String format(String text) {
        return "[" + text + "]";
    }
};
~~~

In both cases, the body inside the curly braces is the definition of the anonymous class. The `new ... { ... }` expression creates an object of that anonymous class.

An anonymous class can have fields, methods, and instance initializer blocks. However, it **cannot declare its own named constructor**, because the class itself has no name to use as the constructor name. When creating an anonymous class that extends a class, the `new KiểuCha(...)` part calls the constructor of the superclass.

If an anonymous class implements an interface with multiple abstract methods, it must implement all required methods to become a concrete class. If you only need to implement the single abstract method of a functional interface and do not need additional state or special logic, a lambda is usually more concise.

### Variable scope and the `this` keyword

An anonymous class can also only use outer local variables if they are `final` or effectively final.

Inside the body of an anonymous class, `this` refers to the object of the anonymous class itself. If the class is declared inside an enclosing class and needs to reference the object of the enclosing class, you can use the syntax `OuterClass.this` in an appropriate instance context.

With a lambda, `this` has a different meaning: it refers to the object enclosing the lambda, because a lambda does not create an anonymous class with its own `this` object. This is a point to remember when switching from an anonymous class to a lambda.

## 3. Complete Java example

The following example demonstrates three cases: a local class implementing an interface, an anonymous class implementing the same interface, and an anonymous class extending an abstract class. Everything is placed in a single file so that it can be compiled and run directly.

~~~java
import java.util.Locale;

interface Greeter {
    String greet(String name);
}

abstract class TextFormatter {
    abstract String format(String text);
}

public class LocalAndAnonymousClassesDemo {
    public static void main(String[] args) {
        String prefix = "Xin chào";

        // Local class: named, scoped within main().
        class LocalGreeter implements Greeter {
            @Override
            public String greet(String name) {
                // prefix is captured because it is effectively final.
                return prefix + ", " + name + "!";
            }
        }

        Greeter localGreeter = new LocalGreeter();

        // Anonymous class: implements Greeter right at the object creation site.
        Greeter anonymousGreeter = new Greeter() {
            @Override
            public String greet(String name) {
                return "Hello, " + name + "!";
            }
        };

        // Anonymous class: extends an abstract class and overrides the method.
        TextFormatter formatter = new TextFormatter() {
            @Override
            String format(String text) {
                return "[" + text.toUpperCase(Locale.ROOT) + "]";
            }
        };

        System.out.println(localGreeter.greet("Lan"));
        System.out.println(anonymousGreeter.greet("Minh"));
        System.out.println(formatter.format("java"));
    }
}
~~~

Save the content to the file `LocalAndAnonymousClassesDemo.java`, then run it with Java 17 or later:

~~~text
javac LocalAndAnonymousClassesDemo.java
java LocalAndAnonymousClassesDemo
~~~

Expected output of the program:

~~~text
Xin chào, Lan!
Hello, Minh!
[JAVA]
~~~

The file name must match the class name `public LocalAndAnonymousClassesDemo` exactly. The two supporting interface/class declarations in the example are not declared `public`, so they can reside in the same file. `Locale.ROOT` performs uppercase conversion using rules that do not depend on the default locale of the runtime machine.

## 4. Comparing local classes and anonymous classes

| Criterion | Local class | Anonymous class |
|---|---|---|
| Class name | Has a name given by the programmer | Has no class name given in the source code |
| Declaration | Class declared inside a code block | Class body declared inside a `new ... { ... }` expression |
| Scope | Class name can be used within the declaration block | No class name to reference directly elsewhere |
| Object creation | Can create multiple objects from the declared class | Creates a new object each time the expression is executed |
| Own constructor | Can declare a constructor | Cannot declare its own named constructor |
| State and logic | Suitable when multiple fields, methods, or longer logic are needed | Suitable for short implementations tied to a single point of use |
| Inheritance/implementation | Can extend a class and implement interfaces | Can extend a class or implement an interface at the object creation expression |

Both can access effectively final local variables and both can be used to provide an implementation for an abstract type. The difference lies in how the class is named and how the source code is organized.

## 5. When should you use each type?

Choose a **local class** when the implementation has multiple steps, needs a clear name, requires a constructor, or needs to create multiple objects of the same type within a method. Placing the class close to where it is used still keeps its scope small, while making the implementation easier to read than a long anonymous class block.

Choose an **anonymous class** when you need a short local implementation and only need to use the class at that expression. Typical examples include overriding a callback or providing a specific implementation of an interface for a particular call.

If the type to implement is a functional interface and you only need to provide the body for a single abstract method, consider a lambda:

~~~java
Greeter greeter = name -> "Xin chào, " + name;
~~~

Lambdas cannot replace anonymous classes in all cases. A lambda can only be used with a functional interface, whereas an anonymous class can also extend an abstract class. An anonymous class can also have instance fields and override multiple methods, so it remains suitable when those capabilities are needed.

## 6. Common mistakes and how to handle them

1. **Using a local class name outside its declaration scope.** Move the usage into the right block, or choose a class with a broader scope if multiple places genuinely need to use it.
2. **Reassigning a captured local variable.** Keep the variable effectively final, or redesign how state is passed instead of mutating that variable directly.
3. **Forgetting to implement abstract methods.** Check all required methods of the interface or abstract class. For interface methods, the implementation normally must be declared `public`.
4. **Trying to declare a constructor for an anonymous class.** An anonymous class has no class name to name a constructor. If you need a dedicated constructor or multiple initialization configurations, a local class or a named class is usually more suitable.
5. **Calling additional methods through an overly general reference type.** If a variable is declared as an interface type, only the methods present in the interface can be called directly through that variable, even if the anonymous class adds its own methods.
6. **Confusing the meaning of `this`.** In an anonymous class, `this` points to the anonymous object; use `OuterClass.this` when you need the enclosing object and the context allows it.

When reading or designing code, determine beforehand the abstract type to implement, the scope of use, the amount of state to store, and the number of methods to override. These factors help you decide clearly between a local class, an anonymous class, and a lambda.
