# Abstract Classes With or Without Abstract Methods in Java

In Java, the `abstract` keyword on a **class** and on a **method** has two related but not identical meanings:

- **`abstract` class**: a class that cannot be instantiated directly with `new TênLớp(...)`. It can still contain state, constructors, methods with a body, `static` methods, and `final` methods.
- **`abstract` method**: declares only a signature, with no method body; a concrete subclass must provide an implementation, unless an implementation has already been validly inherited from another superclass.

**Core rule:** If a class declares an `abstract` method, that class itself must be declared `abstract`; the converse is **not required**. This means an `abstract` class can have **0, 1, or more** `abstract` methods.

| Case | Valid? | Consequence |
| --- | --- | --- |
| `abstract class A` has only methods with a body | Yes | `new A()` is not allowed, but a concrete subclass can inherit all behavior |
| `abstract class A` has `abstract` methods | Yes | A concrete subclass must implement the missing abstract methods |
| `class A` directly declares an `abstract` method | No | Compile error: the class must be `abstract` |
| A non-`abstract` subclass still inherits unimplemented `abstract` methods | No | The subclass must implement them or be declared `abstract` |

## 1. Abstract class declaring no abstract methods

A class can provide complete default behavior yet still be designed to **exist only through subclasses**. For example, every document has a code and a common way to describe itself, but the application only creates specific document types.

Create the file **NoAbstractMethodDemo.java**:

~~~java
abstract class Document {
    private final String code;

    protected Document(String code) {
        this.code = code;
    }

    public final String code() {
        return code;
    }

    public String describe() {
        return "Document: " + code;
    }
}

final class Receipt extends Document {
    Receipt(String code) {
        super(code);
    }
}

public class NoAbstractMethodDemo {
    public static void main(String[] args) {
        Document doc = new Receipt("R-01");
        System.out.println(doc.code());
        System.out.println(doc.describe());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac NoAbstractMethodDemo.java
java NoAbstractMethodDemo
~~~

Exact output:

~~~text
R-01
Document: R-01
~~~

**Why is this valid?** `Document` does not declare any `abstract` method. `Receipt` does not have to override `code()` or `describe()`, because those two methods already have bodies and are inherited. The constructor `Document(String)` is still called via `super(code)`; a constructor itself cannot be declared `abstract`.

Even without abstract methods, `new Document("R-02")` still **causes a compile error** because `Document` is an `abstract` class. A reference of type `Document` is still completely valid: `Document doc = new Receipt("R-01");` — the reference type is the superclass, and the actual object is a `Receipt`.

For a class that contains no `abstract` methods, the expression `new Document("TMP") {}` can also be valid: `{}` creates an **anonymous subclass** and instantiates that subclass, rather than creating a direct instance of `Document`. This approach can only be used if the constructor and inheritance constraints permit it.

**When is this useful?**

- When you want to prohibit instantiating an overly generic base type and force the application to use subclasses with business meaning.
- When you want to centralize fields, constructors, invariant checks, and shared behavior for a family of classes.
- When you want to reserve the ability to add extension points in the superclass in the future, while not currently needing an `abstract` method.

Do not use `abstract` solely to hold `static` utility methods: a `final` utility class with a `private` constructor usually expresses the intent more clearly.

## 2. Abstract class with abstract methods

When every subclass must define part of its behavior itself, an `abstract` method is a **mandatory contract**. The already-known part of the behavior can be written in the superclass and invoke the abstract method through polymorphism.

Create the file **WithAbstractMethodDemo.java**:

~~~java
abstract class Figure {
    private final String name;

    protected Figure(String name) {
        this.name = name;
    }

    abstract double area();

    String summary() {
        return name + " area = " + area();
    }
}

final class Square extends Figure {
    private final double side;

    Square(double side) {
        super("Square");
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}

public class WithAbstractMethodDemo {
    public static void main(String[] args) {
        Figure figure = new Square(3);
        System.out.println(figure.summary());
        System.out.println(figure.area());
    }
}
~~~

~~~bash
javac WithAbstractMethodDemo.java
java WithAbstractMethodDemo
~~~

Exact output:

~~~text
Square area = 9.0
9.0
~~~

The `Figure.area()` method has only a signature and a `;`, **with no `{ ... }`**. The `Square` class uses `@Override` and provides the method body. When `summary()` calls `area()` on a `Square` object, Java executes `Square.area()` via **dynamic dispatch**. This is also how a superclass shares a workflow while letting a subclass decide one step in the workflow.

The example above uses package-private access for `area()`; when overriding, you must not reduce the access level. In an API used across multiple packages, you can explicitly declare `public abstract double area();` and override it with `public double area()`.

## 3. Abstract subclasses and concrete subclasses

A subclass can still be declared `abstract` if it has not yet implemented all inherited abstract methods. The following snippet only illustrates the inheritance relationship; it is not a program with `main`:

~~~java
abstract class Writer {
    abstract String write();
}

abstract class NamedWriter extends Writer {
    String name() {
        return "named";
    }
    // Still leaves write() unimplemented.
}

class PlainWriter extends NamedWriter {
    @Override
    String write() {
        return "ok";
    }
}
~~~

`NamedWriter` **does not itself declare** a new `abstract` method, yet it **inherits** the obligation to implement `write()` from `Writer`; therefore, it must still be an `abstract` class. `PlainWriter` is a concrete class and has implemented `write()`, so it can be instantiated.

Distinguish accurately between the following two statements:

- “This class **does not declare** any abstract method” does not mean that the entire inheritance tree has no remaining abstract methods.
- “A concrete class can be instantiated” is only true when every inherited abstract method already has a valid implementation.

## 4. Errors to recognize

- If a class directly declares an `abstract` method, the class itself must be `abstract`.
- An `abstract` method has only a signature and ends with `;`; it must not be accompanied by a `{ ... }` body.
- A non-`abstract` subclass must have a valid implementation for every missing abstract method across the entire hierarchy, including indirectly inherited obligations.
- An abstract class can have regular, `static`, or `final` methods with bodies; details on forbidden modifier combinations belong to the dedicated lesson on modifiers.

## 5. Distinguishing from interfaces and how to choose a design

- **Abstract class**: suitable when classes have an “is-a” relationship and need to share **state**, **constructors**, common behavior, or certain steps that must be overridden. Each Java class can directly `extends` only **one class**.
- **Interface**: suitable when you need to expose a **capability/contract** that multiple classes from different hierarchies can satisfy. A class can `implements` multiple interfaces. An interface can contain `abstract` methods (typically implicitly understood as `public abstract`), while also having `default`, `static`, and `private` methods according to modern Java rules.

Having an abstract method does not automatically mean you should choose an abstract superclass: if you do not need to share state or constructors and only need to enforce a capability, an interface is usually simpler. If an inheritance relationship causes subclasses to depend too tightly on superclass details, consider **composition** (holding and delegating to another object).

**Self-check questions:** Is an `abstract` class that only has methods with bodies valid? **Yes.** Is its concrete subclass required to `@Override` any method? **No**, if there are no other inherited abstract obligations. What if an `abstract` method is added to the superclass? **The concrete subclass must have a valid implementation**, either directly or inherited from an intermediate class that has implemented it.

**Key takeaway:** An `abstract class` is about **direct instantiability** and serving as a base class; an `abstract method` is about **unimplemented behavior**. The two concepts are related, yet an `abstract` class is not required to possess an `abstract` method.
