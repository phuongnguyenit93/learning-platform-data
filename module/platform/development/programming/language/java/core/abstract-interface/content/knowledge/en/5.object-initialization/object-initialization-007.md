# Constructors Are Not Inherited and Cannot Be Abstract in Java

In Java, **constructors are not inherited** and **cannot be declared abstract**, even when the constructor belongs to an abstract class. These two rules do not contradict the fact that the superclass constructor still runs when creating a subclass.

- **Not inherited:** Parent(int) does not automatically become a Child(int) constructor. Each class has its own constructors.
- **Cannot be abstract:** a constructor needs a body to participate in the initialization process. Java has no mechanism to override a constructor so that a subclass supplies a missing body.
- **Still called:** a Child constructor can call a Parent constructor directly via super(...). This is constructor chaining, not constructor inheritance.

## 1. Constructors Are Tied to the Declaring Class

~~~java
class Parent {
    Parent() {}
    Parent(int value) {}
}

class Child extends Parent {
    // The compiler generates Child() because this class declares no constructor.
}
~~~

`new Child()` is valid because Child has a default no-argument constructor and Parent() can be called. However, `new Child(10)` is invalid: Parent(int) is not inherited as Child(int).

To create Child with an integer, declare Child's own constructor:

~~~java
class Child extends Parent {
    Child(int value) {
        super(value);
    }
}
~~~

`super(value)` calls Parent(int) to initialize the superclass part of the same Child object. It does not turn the parent constructor into a constructor of Child.

## 2. Inheritance, Overriding, Overloading, and Chaining

| Mechanism | Applies to constructors? | Meaning |
| --- | --- | --- |
| Inheritance | No | Parent(int) is not added to Child's set of constructors. |
| Overriding | No | Constructors do not participate in dynamic dispatch and do not use @Override. |
| Overloading | Yes | A class can declare multiple constructors with different parameter lists. |
| this(...) | Yes | Calls another constructor in the same class. |
| super(...) | Yes | Calls a constructor of the direct superclass. |

Java only generates a default no-argument constructor when a class **does not declare any constructor**. If Child(int) is already declared, the compiler does not automatically add Child(). The generated default constructor is also a constructor of that class itself and is only valid if the corresponding parent constructor call is valid.

Also, do not confuse a constructor with a method that has the same name as the class but has a return type. For example, `void Child(int value)` is a method, not a constructor.

## 3. Abstract Classes Have Constructors with Bodies

An abstract class cannot be instantiated directly, but it can have multiple constructors to initialize shared state. The following example is runnable; save it as **ConstructorRulesDemo.java**:

~~~java
abstract class Resource {
    private final String name;

    protected Resource(String name) {
        this.name = name;
        System.out.println("Resource(String): " + name);
    }

    protected Resource(String name, boolean verbose) {
        this(name);
        if (verbose) {
            System.out.println("Resource(String, boolean): verbose");
        }
    }

    public final String name() {
        return name;
    }

    public abstract String use();
}

final class FileResource extends Resource {
    private final String extension;

    FileResource(String name, String extension) {
        super(name, true);
        this.extension = extension;
        System.out.println("FileResource: " + extension);
    }

    @Override
    public String use() {
        return name() + "." + extension;
    }
}

public class ConstructorRulesDemo {
    public static void main(String[] args) {
        FileResource file = new FileResource("bao-cao", "txt");
        Resource resource = file;
        System.out.println("use: " + resource.use());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ConstructorRulesDemo.java
java ConstructorRulesDemo
~~~

Stdout:

~~~text
Resource(String): bao-cao
Resource(String, boolean): verbose
FileResource: txt
use: bao-cao.txt
~~~

The FileResource constructor calls Resource(String, boolean) using super(...). That constructor calls Resource(String) via this(...), so the assignment of name is centralized in one place. Only after the parent constructor chain completes does FileResource assign extension. Resource is abstract, yet its constructors have bodies and still run when creating FileResource.

## 4. Why Can't Constructors Be Abstract?

An abstract method describes unimplemented behavior and requires subclasses to provide an implementation. A constructor has a different role: it participates in creating and initializing an object, and must place the parent constructor call into a valid chain. Because constructors are not overridden, there is no mechanism to select an “implementation constructor” at runtime as with instance methods.

The following declaration is invalid:

~~~java
abstract class InvalidResource {
    abstract InvalidResource(); // ERROR: a constructor cannot be abstract.
}
~~~

The right approach is to give the constructor a body and extract the behavior that subclasses need to implement into an abstract method:

~~~java
abstract class ResourceBase {
    protected ResourceBase() {
        // Initialize shared state.
    }

    public abstract void use();
}

final class ConcreteResource extends ResourceBase {
    @Override
    public void use() {
        System.out.println("using");
    }
}
~~~

`ResourceBase()` initializes the shared part; use() is the behavioral contract that concrete subclasses must implement. That an abstract class has constructors and that constructors cannot be abstract are both true.

## 5. Typical Compilation Errors

| Scenario | Cause and resolution |
| --- | --- |
| Child declares no constructor, but Parent only has Parent(int) | The compiler attempts to generate Child() calling super(), but Parent() does not exist. Declare Child(int) calling super(value). |
| Parent constructor is private or inaccessible | There is no matching superclass constructor that the subclass has permission to call. Check the access modifier and package. |
| Placing @Override on a constructor | Constructors do not override. Remove the annotation and declare Child's own constructor. |
| Placing regular statements before super(...) in Java 17 | An explicit constructor invocation must come first. Move other work after super(...). |
| Calling both this(...) and super(...) in the same constructor | Choose only one first call; the target constructor continues the chain. |
| Using the abstract, final, or static modifier on a constructor | Those modifiers do not apply to constructors; only use access modifiers and throws when needed. |

Example of a missing no-argument parent constructor:

~~~java
class Base {
    Base(int id) {}
}

class Derived extends Base {
    // Error: the default constructor Derived() will call super().
}
~~~

Fix with an explicit constructor:

~~~java
class Derived extends Base {
    Derived(int id) {
        super(id);
    }
}
~~~

The issue is that the super() call is invalid, not whether the Base(int) constructor is inherited or not.

## 6. A Warning Related to Polymorphism

Constructors cannot be overridden, but a parent constructor can call an instance method that a subclass overrides. When that happens, Java still dispatches based on the runtime class, and the subclass's fields may not yet be initialized. Avoid calling overridable hooks from a constructor; the article on the risks of calling overridden methods in a constructor presents examples, consequences, and safe design approaches.

Do not try to fix this by adding @Override or replacing the constructor with a similarly named method. What needs to change is the call site of the polymorphic behavior, or the initialization design, rather than the constructor inheritance mechanism.

## 7. Self-Check Exercises

**Question 1.** Parent has Parent() and Parent(int). Child declares no constructor. Are the calls new Child() and new Child(5) valid?  
**Answer:** new Child() is valid because the compiler generates Child() calling super(). new Child(5) is invalid because Child(int) is not inherited.

**Question 2.** Abstract class Base only has Base(String). Write a constructor for Concrete so that new Concrete("A") can be created.  
**Answer:** Concrete(String name) { super(name); }.

**Question 3.** Why is protected Base() valid while abstract Base() is invalid?  
**Answer:** A constructor can have a body and an access level; a constructor cannot be abstract because it cannot be overridden. Unimplemented behavior should be described using an abstract method.

**Question 4.** Can both this(...) and super(...) be called directly in the same Java 17 constructor?  
**Answer:** No. If a constructor calls this(...), the delegated constructor will continue the chain to the superclass.

Remember four things: constructors are not inherited, are not overridden, can be overloaded, and can call a parent constructor. Abstract classes have constructors with bodies; subclasses use super(...) to initialize the superclass part and use abstract methods to supply the missing behavior.
