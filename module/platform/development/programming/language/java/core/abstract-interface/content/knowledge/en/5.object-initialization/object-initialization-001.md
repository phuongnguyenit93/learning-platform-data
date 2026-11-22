# Superclass Constructors When Initializing a Subclass in Java

When calling `new Child(...)`, Java creates **a single Child object**. That object has both the instance fields declared in Parent and Child; Java does not create a separate independent Parent object to put inside Child. Parent's constructor runs to set up the portion of state owned by the superclass before Child's constructor completes.

Constructors are not inherited or overridden. However, the superclass constructor still participates in the initialization chain via `super(...)`. These are two different points: **not inheriting constructors** does not mean **skipping the parent constructor**.

## 1. Visualizing the Constructor Chain

~~~text
new Child(...)
   |
   v
Child constructor
   |
   +-- this(...) ? --> another Child constructor
   |
   +-- super(...) / implicit super()
                    |
                    v
              Parent constructor
                    |
                    v
              ... -> Object constructor
                    |
                    v
              complete superclass part
   |
   v
complete Child part
   |
   v
return Child reference
~~~

Each class only calls the constructor of its **direct superclass**. If Parent also extends Grandparent, Grandparent's constructor is also in the chain. Java completes the initialization of ancestor classes in turn before Child's instance initialization and constructor body complete.

## 2. Calling a Parent Constructor with super(...)

The following standalone example shows a subclass passing data to a parent constructor. Save it to the file **SuperConstructorDemo.java**:

~~~java
public class SuperConstructorDemo {
    static class Parent {
        private final String id;

        Parent(String id) {
            this.id = id;
            System.out.println("Parent(" + id + ")");
        }

        String id() {
            return id;
        }
    }

    static class Child extends Parent {
        private final int level;

        Child(String id, int level) {
            super(id);
            this.level = level;
            System.out.println("Child(level=" + level + ")");
        }

        int level() {
            return level;
        }
    }

    public static void main(String[] args) {
        Child child = new Child("A-01", 3);
        System.out.println(child.id() + " / " + child.level());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac SuperConstructorDemo.java
java SuperConstructorDemo
~~~

Stdout:

~~~text
Parent(A-01)
Child(level=3)
A-01 / 3
~~~

When creating Child, the `super(id)` call selects the Parent(String) constructor. Parent assigns its private final field; only after the parent constructor returns does Child assign level. Both fields belong to the same Child object.

`super(id)` is an explicit constructor call to the direct superclass, not a regular method call, and it does not create a new Parent. The argument list selects the overload according to Java's rules.

## 3. When Does Java Automatically Call super()?

In Java 17, if a constructor does not begin with `this(...)` or `super(...)`, the compiler inserts a **no-argument super()** call. That no-argument constructor must exist and be accessible.

~~~java
class Parent {
    Parent(String id) {}
}

class BrokenChild extends Parent {
    BrokenChild() {
        // ERROR: Java inserts super(), but Parent() does not exist.
    }
}
~~~

Fix it by calling an existing overload:

~~~java
class FixedChild extends Parent {
    FixedChild(String id) {
        super(id);
    }
}
~~~

Once Parent has declared at least one constructor, Java does not automatically generate a default no-argument constructor for Parent. If both Parent() and Parent(String) are needed, both must be declared. A constructor that is private or inaccessible from Child also cannot be selected merely via an implicit `super()`.

## 4. this(...) Does Not Run the Parent Constructor Twice

`this(args)` delegates to another constructor **in the same class**; `super(args)` calls the direct superclass constructor. In Java 17, an explicit constructor call must come first in a constructor, so both calls cannot be written directly in one constructor body.

Suppose `Child()` calls `this("guest")` and `Child(String role)` calls `super(role)`. The execution order of the **bodies** is `Parent(String)` → `Child(String)` → `Child()`. The delegation chain only selects the initialization path; it does not create extra Parent or Child objects and does not cause instance initializers to run twice.

The lesson "Super Call Chains and Passing Required Data" will trace how parameters are forwarded and how data is validated across multiple inheritance levels.

## 5. Abstract Class Constructors Still Run

An abstract class cannot be instantiated directly, yet it can still own shared state and constructors with a body:

~~~java
abstract class Account {
    private final String id;

    protected Account(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        this.id = id;
    }

    public final String id() {
        return id;
    }
}

final class SavingsAccount extends Account {
    SavingsAccount(String id) {
        super(id);
    }
}
~~~

`new SavingsAccount("A-01")` calls the Account constructor via `super(id)`. The parent constructor validates and assigns the data owned by Account. Interfaces do not have constructors; a class implementing an interface only runs the constructors of the classes in its extends chain.

## 6. Exceptions and Access Control

If a parent constructor declares a checked exception, a child constructor calling `super(...)` must declare a compatible exception in `throws` (or choose a superclass overload that does not throw that exception). In Java 17, a `super(...)` call cannot be wrapped in `try/catch` because an explicit constructor call must come first in the constructor; the caller can handle the exception around the `new Child(...)` expression.

If the parent constructor throws an exception, initialization is halted; the rest of the child constructor does not run, and the `new Child(...)` expression does not return a successfully initialized object. Therefore, a constructor should validate data and establish the state belonging to its class's responsibility; avoid performing external side effects that are difficult to undo.

Access levels also apply to constructors: public, protected, package-private, and private determine where they can be called. A private constructor of Parent cannot be called with `super(...)` by an ordinary Child outside the access scope.

## 7. Warning When a Constructor Calls an Overridden Method

A parent constructor may call an instance method overridden by Child. Java still selects the method according to the object's runtime class, while Child's fields and initializers may not be ready yet. For example, if Parent() calls `label()` and Child overrides that method to read `label = "ready"`, the early call may see null.

Avoid direct or indirect calls to overridable methods in a constructor. Detailed analysis of dynamic dispatch, this escape, and fixes belongs to the subsequent specialized lessons; here, just remember that **the parent constructor runs before Child's own initialization completes**.

## 8. Distinguishing Syntax

| Syntax | Effect |
| --- | --- |
| `super(args)` | Calls the direct superclass constructor to initialize the parent part of the same object. |
| `this(args)` | Calls another constructor in the same class. |
| `super.method(args)` | Calls the superclass implementation of the method at a valid location. |
| `this.method(args)` | Calls the method on the current object; an override may still be dispatched. |
| `new Parent(args)` | Creates a separate Parent object. |

`super(...)` and `super.method(...)` do not use the same mechanism: one is a constructor call, and the other is a method call.

## 9. Common Mistakes and Self-Check

- **No-argument parent constructor does not exist:** call `super(args)` with the matching signature or provide an accessible parent constructor.
- **Assuming Child inherits Parent(int):** declare the subclass's own Child(int) constructor and then call `super(value)`.
- **Writing both this(...) and super(...) in the same constructor:** choose one as the first call; the invoked constructor continues the chain.
- **Assuming abstract classes do not have constructors:** abstract classes do have constructors, though they cannot be instantiated directly with `new`.
- **Assuming a parent constructor cannot affect Child:** calling an overridden method from the parent constructor can observe an incomplete Child state.

**Question 1.** Parent only has Parent(String). Does Child() {} compile?  
**Answer:** No, because Java 17 inserts super() while Parent() does not exist.

**Question 2.** When Child() calls this("guest") and Child(String) calls super("guest"), how many times does the Parent constructor run?  
**Answer:** Once for that object.

**Question 3.** Does new SavingsAccount("A-01") run the Account constructor?  
**Answer:** Yes. Account is not instantiated separately, but its constructor runs as part of the SavingsAccount initialization chain.

Remember: the parent constructor initializes its own portion of state within the same subclass object; `super(...)` selects the parent constructor, whereas `this(...)` delegates between constructors of the same class.
