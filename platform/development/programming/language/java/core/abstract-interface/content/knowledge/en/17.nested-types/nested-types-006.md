# Instantiating an anonymous subclass of an abstract class

In Java, an **anonymous class** is a class that is declared and instantiated directly within an expression, without a programmer-defined class name. When you need to create an object based on an **abstract class**, you can write an anonymous subclass using the syntax `new AbstractClass(...){ ... }`, providing implementations for the abstract methods in place.

This approach is useful when you only need a small implementation used in one place and there is no need to reuse it as a separate class. It also lets you use the abstract class's state, constructor, and already-implemented methods.

## 1. Basic syntax

General structure:

~~~java
AbstractClass reference = new AbstractClass(arguments) {
    @Override
    public ReturnType abstractMethod(Parameters parameters) {
        // Provide the concrete implementation
    }

    // You can override other methods if needed
};
~~~

Parts to understand:

- `AbstractClass` is the abstract class that the anonymous object inherits from.
- `arguments` are passed to the abstract class constructor. If the superclass does not have an accessible no-argument constructor, you must call an appropriate constructor.
- The body inside the curly braces `{ ... }` declares the anonymous subclass and implements the required abstract methods.
- The `reference` variable is usually declared with the abstract class type so that the object is used through the common contract.
- The semicolon after the `}` is required to terminate the variable declaration and initialization statement.

You cannot directly create an instance of an abstract class with `new AbstractClass(...)` without a subclass body. The body in the expression `new AbstractClass(...){...}` defines a concrete subclass, and the created object is an instance of that subclass.

## 2. Complete runnable example

Create the file **AnonymousAbstractSubclassDemo.java** with the following content:

~~~java
abstract class Report {
    private final String owner;

    protected Report(String owner) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner must not be blank");
        }
        this.owner = owner;
    }

    public String label() {
        return "Report for " + owner;
    }

    public abstract String format(String message);

    public abstract void deliver(String message);
}

public class AnonymousAbstractSubclassDemo {
    public static void main(String[] args) {
        Report report = new Report("Mai") {
            @Override
            public String format(String message) {
                return "[EMAIL] " + message.trim();
            }

            @Override
            public void deliver(String message) {
                System.out.println(label() + ": " + format(message));
            }
        };

        report.deliver("  Build passed  ");
        System.out.println(report.getClass().isAnonymousClass());
    }
}
~~~

Compile and run using Java 17 or later:

~~~bash
javac AnonymousAbstractSubclassDemo.java
java AnonymousAbstractSubclassDemo
~~~

Stdout output:

~~~text
Report for Mai: [EMAIL] Build passed
true
~~~

What happens in this example?

1. `new Report("Mai")` invokes the constructor of the abstract class `Report`; the string `"Mai"` is passed to the `owner` parameter.
2. The body after the parentheses declares an anonymous subclass of `Report`.
3. The subclass implements both abstract methods `format` and `deliver`, so it is a concrete, instantiable class.
4. The `label()` method is an inherited concrete method. Inside `deliver`, the `label()` call uses that inherited implementation.
5. The `report` variable has a declared type of `Report`, so calling code uses the methods defined in the abstract class. The actual type of the object is the anonymous subclass.
6. `getClass().isAnonymousClass()` returns `true`, confirming that the object belongs to an anonymous class.

The `Report` class is declared without the `public` keyword so that it can be placed in the same file as the public class `AnonymousAbstractSubclassDemo`. In application code, follow Java's file-naming and public class rules.

## 3. Why do we need an abstract class?

An abstract class lets you group shared state and behavior into a base class while requiring subclasses to provide certain specific behaviors. It can contain:

- Fields, including `private` and `final` fields.
- Constructors to validate or initialize shared state.
- Concrete methods that already have a body.
- Abstract methods that only declare a signature.
- `final` methods, `static` methods, or other members according to Java's rules.

An anonymous subclass inherits the accessible members of the abstract class. It must implement all unimplemented abstract methods from its superclass or its superclasses. If a required abstract method is omitted, the compiler reports an error; an anonymous class created in this expression cannot be declared abstract to defer implementation.

If the abstract class has a concrete method that you want to customize specifically for this object, you can also override that method. Overriding every concrete method is not required.

## 4. Passing arguments to the superclass constructor

The part inside the parentheses immediately following the abstract class name is the superclass constructor call. This allows the superclass to initialize shared state before the object's methods are used.

~~~java
abstract class Greeting {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    public String greetingPrefix() {
        return "Hello, " + name;
    }

    public abstract String message();
}
~~~

You can create an anonymous implementation as follows:

~~~java
Greeting greeting = new Greeting("Linh") {
    @Override
    public String message() {
        return greetingPrefix() + "!";
    }
};

System.out.println(greeting.message());
~~~

This is an illustrative snippet meant to be placed inside a method; it depends on the `Greeting` class above. Output:

~~~text
Hello, Linh!
~~~

If an abstract class does not declare a constructor, Java provides a default constructor when the language rules allow it. If the superclass declares a parameterized constructor and has no accessible no-argument constructor, the anonymous subclass creation expression must pass appropriate arguments. Constructor accessibility also applies just as it does for a regular subclass.

An anonymous class does not declare its own named constructor. If you need to pass initial data, you typically pass that data to the superclass constructor; additional fields of the anonymous class can be initialized using field initializers or instance initializer blocks when needed.

## 5. Reference types and polymorphism

An object created from an anonymous subclass can be stored in a variable of the abstract class type:

~~~java
Report report = new Report("Mai") {
    @Override
    public String format(String message) {
        return message.toUpperCase();
    }

    @Override
    public void deliver(String message) {
        System.out.println(format(message));
    }
};
~~~

Code that uses `report` only needs to know the contract declared in `Report`. When calling `report.deliver(...)`, Java executes the anonymous subclass's implementation. This is **polymorphism**: a call through a supertype reference can resolve to the overridden implementation in a subclass.

The declared type and the actual type play different roles:

- **The declared type** determines which members can be called directly at compile time.
- **The actual type** determines which instance method is selected at runtime via dynamic dispatch.
- If the anonymous class declares an additional method of its own that is not in the abstract class, you cannot call that method through a variable that only has the abstract class type without another type-safe way to access it. Typically, you should design the required contract directly in the base class or a suitable interface.

Using the object through its supertype keeps calling code less coupled to the details of the anonymous subclass and preserves polymorphic substitutability.

## 6. Overriding methods properly

You should place the `@Override` annotation before every overridden method. The compiler will catch cases where the signature does not match the method being overridden.

For example, if the superclass declares:

~~~java
public abstract int calculate(int value);
~~~

then the subclass needs to provide a compatible implementation:

~~~java
@Override
public int calculate(int value) {
    return value * 2;
}
~~~

The method name, parameter list, and return type must follow Java's overriding rules. You cannot reduce the access level of a method when overriding it; for example, you cannot override a `public` method with a `protected` method. If the superclass method declares checked exceptions, the overriding method must also obey the exception restrictions of the overriding rules.

If the abstract method has a return type other than `void`, every execution path must return a compatible value. If the return type is `void`, the implementation must perform the appropriate action and not return a value.

## 7. Lifecycle warning: superclass constructor calling an overridable method

When running `new AbstractClass(...) { ... }`, **the superclass constructor runs before the field initialization of the anonymous subclass**. If the superclass constructor calls an overridable method, Java dispatches the call to the subclass implementation, even though the subclass's own state has not yet been fully initialized.

The following example intentionally illustrates a dangerous design; place the `Base` declaration outside and the object creation statement inside a method:

```java
abstract class Base {
    Base() { display(); }
    abstract void display();
}

Base instance = new Base() {
    private final String status = " ready ".trim();
    @Override void display() {
        System.out.println(status);
    }
};
```

The output is `null`, **not** `ready`: the `display()` call occurs in the `Base` constructor before the `status` field is assigned. The `trim()` call causes the initializer expression to execute at object creation time; if you used `final String status = "ready"`, that is a compile-time constant and the compiler can *inline* the value, masking the initialization-order bug. This is a risk for any subclass, and it is especially easy to overlook when the subclass is written directly inside a `new` expression. Better yet, the superclass constructor should only set up its own state; call overridable methods after object construction is complete.

## 8. Boundaries with lambdas and outer variables

An anonymous subclass has a `this` representing the subclass object itself, can override multiple methods, and inherits state from `Report`. A lambda cannot extend an abstract class, even when the superclass has only one abstract method: the target type of a lambda must be a **functional interface**.

When the body of an anonymous class uses a local variable from its enclosing method, the variable must be `final` or *effectively final*. This rule applies to **captured local variables** and does not prevent the subclass from having its own instance fields. If the anonymous class is inside an instance method and needs the enclosing object, use `Outer.this` when an appropriate enclosing instance exists.

## 9. When should you use an anonymous subclass?

This approach is appropriate when:

- You need a single, small, local implementation of an abstract class.
- You want to leverage constructors, fields, or shared methods already defined in the base class.
- You need to override one or more methods for a specific scenario.
- Creating a separate named class would increase the number of classes without clear reuse benefits.

Consider creating a named subclass if the implementation is long, involves substantial state or business rules, needs to be reused in multiple places, or needs to be tested and understood independently. A named class often helps name the intent of the behavior and reduces complexity at the instantiation site.

An anonymous subclass is also not a good choice if the body turns into a long block of code with multiple responsibilities. In that case, extracting the logic into methods or a separate class will make the structure clearer.

## 10. Common mistakes

- **Failing to implement all abstract methods:** check all unimplemented abstract methods across the inheritance hierarchy. If any are missing, the compiler reports an error.
- **Calling a nonexistent or inaccessible constructor:** pass matching arguments and check the access level of the superclass constructor.
- **Forgetting the semicolon after the object creation expression:** a variable assignment statement must end with a `;` after the curly brace.
- **Wrong signature when overriding:** add `@Override` and verify the name, parameters, return type, and access level.
- **Reassigning a local variable used inside an anonymous class:** keep the variable `final`/effectively final or redesign how the data is passed.
- **Misunderstanding the object type:** a variable of the abstract class type only allows calling members accessible through the declared type; overridden methods are resolved at runtime.
- **Using a lambda to extend an abstract class:** lambdas only target functional interfaces. Use an anonymous subclass if you need to extend a class.
- **Letting an anonymous class become too complex:** convert the implementation into a named class when reuse, testing, or clear expression of business logic is needed.

## 11. Implementation procedure

1. Identify the abstract class to extend and the unimplemented abstract methods.
2. Check the superclass constructor, the parameters to pass, and the accessibility of that constructor.
3. Write `new AbstractClass(arguments) { ... }` and implement every required abstract method.
4. Use `@Override` to verify that the overriding methods have the correct signatures.
5. Assign the object to a reference of the abstract class type or pass it directly to an appropriate API.
6. Compile with `javac`, run the program, and verify the output.
7. If the body is large or needs to be reused, consider converting it into a named subclass.

An anonymous subclass is Java's way of creating a concrete subclass right where an object is needed. It lets you implement abstract methods, use the shared state and behavior of an abstract class, and leverage polymorphism without declaring a separate named subclass.
