# `super` to Invoke Constructors and Access Superclass Members in Java

## 1. What Is `super`, and What Problem Does It Solve?

In Java, **`super`** is syntax used in an inheritance context to **refer to declarations/behavior of the direct superclass** in cases permitted by the language. The two most important usages are:

- **`super(arguments)`**: invokes a **direct superclass constructor** from a subclass constructor.
- **`super.member` / `super.method(arguments)`**: accesses a field or invokes an **instance method implementation belonging to the superclass** from the instance context of the subclass.

The two forms look similar, yet they have **completely different semantics**. `super(...)` is an *explicit constructor invocation* executed during object construction. `super.method()` is a method call that explicitly selects the superclass implementation, commonly used when a subclass **overrides** a method while still wanting to use part of the parent behavior.

~~~java
class Parent {
    Parent(String name) {
        System.out.println("Parent: " + name);
    }

    String description() {
        return "From Parent";
    }
}

class Child extends Parent {
    Child(String name) {
        super(name); // Call Parent(String) constructor
    }

    @Override
    String description() {
        return super.description() + " + Child";
    }
}
~~~

These are **illustrative class declarations** and do not yet include a `main` method to run standalone.

**Key takeaway:** `super` **does not create a separate parent object**. With `new Child("Lan")`, Java constructs **a single object of runtime type Child**, and the Parent constructor participates in initializing the Parent portion of the state/contract within that object. The call `super.description()` still executes on the **same current receiver object**, while explicitly selecting the implementation from the appropriate superclass.

This lesson targets **Java 17+** and belongs to the **Inheritance and Polymorphism** topic in Java Core. We will cover, in order, syntax, constructor chaining, cases where `super()` is missing, initialization order, overriding and dynamic dispatch, `super.field`, access control, `InterfaceName.super`, compile-time/runtime errors, proper inheritance design, and complete examples with exact stdout.

## 2. Distinguishing `this` and `super`

A subclass has two ways to refer within an instance context:

- **`this`**: the *current object*, whose runtime class is the actual class being instantiated or receiving the method call.
- **`super`**: syntax that allows selecting members/constructors from the superclass portion according to Java's rules; **it is not a reference to another object**.

| Syntax | Purpose | Typical Location |
| --- | --- | --- |
| `this.field` | Accesses a field of the current object following name lookup rules | Instance method/constructor/instance initializer |
| `super.field` | Accesses a hidden or explicitly specified superclass field | Instance context of a subclass |
| `this.method()` | Calls an instance method on the current object; still uses dynamic dispatch if overridable | Instance context |
| `super.method()` | Calls the appropriate superclass implementation | Instance context of a subclass |
| `this(args)` | Delegates to another constructor in the **same class** | Constructor, at a position permitted by Java 17 |
| `super(args)` | Calls a constructor of the **direct superclass** | Constructor, at a position permitted by Java 17 |
| `ClassName.staticMethod()` | Calls a static method | Anywhere access is permitted |
| `InterfaceName.super.method()` | Selects a specific default method of a superinterface in a valid context | Implementing class or appropriate interface |

**Do not use `super` as a local variable or standalone object expression**:

~~~java
// Object other = super; // Invalid
// System.out.println(super); // Invalid
~~~

If you need the current object to pass as a parameter, use `this` in a valid instance context. If you need to call a superclass method, use `super.method(...)`; do not mistake `super` for a reference to an independent Parent object.

### 2.1. A Child Object Holds State Declared in Both Parent and Child

~~~java
class Base {
    private final String id;

    Base(String id) {
        this.id = id;
    }

    String id() {
        return id;
    }
}

class Derived extends Base {
    private final int version;

    Derived(String id, int version) {
        super(id);
        this.version = version;
    }
}
~~~

A `Derived` object contains the superclass state `Base.id` and the field `Derived.version`. `super(id)` initializes the Base part before the Derived constructor completes. No extra `Base` variable is automatically created inside Derived.

## 3. `super(...)` Calls a Direct Superclass Constructor

When a subclass has a constructor, it must go through a valid **constructor chain**. The explicit form:

~~~java
class Parent {
    Parent(int id) {
        System.out.println("Parent " + id);
    }
}

class Child extends Parent {
    Child(int id) {
        super(id);
        System.out.println("Child " + id);
    }
}
~~~

Calling `new Child(5)` will print:

~~~text
Parent 5
Child 5
~~~

**`super(id)` invokes a constructor of the class placed immediately after `extends`**, and does not arbitrarily pick a constructor from a grandparent class. The Parent constructor in the example takes an `int`; the compiler applies overload resolution rules to select the constructor matching the arguments.

### 3.1. Constructors Are Not Inherited

`class Child extends Parent` does not mean Child automatically "inherits" the `Parent(int)` constructor so that a caller can use `new Child(5)` if Child has not declared an appropriate constructor itself. Constructors belong to the class that declares them; they are not inherited instance methods.

~~~java
class Parent {
    Parent(int code) {
    }
}

class Child extends Parent {
    Child(int code) {
        super(code);
    }
}
~~~

The snippet above is valid. If Child does not declare a constructor, the compiler will attempt to generate a default constructor for Child containing a no-argument superclass constructor call. Because Parent only has `Parent(int)`, a version of Child without a declared constructor will **not compile**.

### 3.2. Why Must a Superclass Constructor Be Called?

The superclass is responsible for initializing its own state and protecting its invariants. For example, Parent requires a valid identifier:

~~~java
class Person {
    private final String name;

    Person(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name rỗng");
        }
        this.name = name;
    }

    public final String name() {
        return name;
    }
}
~~~

An Employee subclass that wants to construct a valid object must supply the required data:

~~~java
class Employee extends Person {
    private final int staffNumber;

    Employee(String name, int staffNumber) {
        super(name);
        if (staffNumber <= 0) {
            throw new IllegalArgumentException("Staff number sai");
        }
        this.staffNumber = staffNumber;
    }
}
~~~

The superclass validates/assigns `name` itself; the subclass validates/assigns `staffNumber` itself. This **separation of responsibilities** is more appropriate than having the subclass attempt to modify Parent's private field directly.

## 4. Implicit `super()` When No Constructor Invocation Is Written

In Java 17, if a constructor does not begin with an explicit `this(...)` or `super(...)` call, the compiler inserts an **implicit `super()`** call according to the applicable rules.

~~~java
class Parent {
    Parent() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    Child() {
        System.out.println("Child");
    }
}
~~~

In terms of constructor chaining behavior, `Child()` calls `Parent()` before executing its own body. It does not mean the compiler automatically generates a Parent constructor if the superclass lacks a no-argument constructor.

### 4.1. A No-Argument Constructor Might Not Exist

~~~java
class Parent {
    Parent(String name) {
    }
}

class BrokenChild extends Parent {
    // Compiler cannot generate an implicit super().
}
~~~

The `BrokenChild` snippet **does not compile**: Parent has a constructor taking a String but no no-argument constructor. The default constructor that the compiler tries to generate for BrokenChild would need an invalid `super()`.

How to fix it:

~~~java
class WorkingChild extends Parent {
    WorkingChild(String name) {
        super(name);
    }
}
~~~

The two examples are standalone illustrative fragments; in a real file, you only keep the valid version.

### 4.2. The Superclass Constructor Might Not Be Accessible

Even when Parent has a no-argument constructor, if that constructor is `private` and Child is not in an appropriate access context, Child cannot freely invoke it either.

~~~java
class Parent {
    private Parent() {
    }
}

// class Child extends Parent { } // Cannot access Parent()
~~~

Use a `protected` constructor when designing a class as a base for subclasses, or expose a factory/composition if subclassing is not intended to be supported.

## 5. Java 17: `this(...)` or `super(...)` Must Be the First Constructor Call

In **Java 17**, an explicit constructor invocation must appear as **the first statement** of the constructor body when used:

~~~java
class Child extends Parent {
    Child(String name) {
        super(name);
        // Other body statements can only be executed from here onward.
    }
}
~~~

You cannot write:

~~~java
class Child extends Parent {
    Child(String name) {
        // System.out.println("Start");
        // super(name); // Invalid in Java 17: not the first statement
    }
}
~~~

The note illustrating the error has been commented out. You also cannot place two explicit constructor invocations in the same constructor:

~~~java
// Child() {
//     this("A");
//     super("A"); // Invalid
// }
~~~

**Specifically:** some Java versions after Java 17 have language changes regarding statements before an explicit constructor invocation. This lesson standardizes on **Java 17+ for Java 17-compatible examples**, so the Java 17 rule applies here; do not extrapolate to newer versions without checking the project's actual language level.

### 5.1. `this(...)` and `super(...)` Select Two Different Targets

~~~java
class Base {
    Base(String name) {
    }
}

class Child extends Base {
    Child() {
        this("anonymous");
    }

    Child(String name) {
        super(name);
    }
}
~~~

`Child()` calls the `Child(String)` constructor, and then `Child(String)` calls `Base(String)`. This is **constructor chaining**, which helps centralize initialization/validation instead of repeating assignments to final fields across every overload.

### 5.2. Avoiding Recursive Constructor Invocation Cycles

~~~java
class Wrong {
    Wrong() {
        this(1);
    }

    Wrong(int n) {
        this();
    }
}
~~~

This snippet **does not compile** due to recursive constructor invocation. The compiler does not allow creating an infinite constructor chain `A → B → A` in place of superclass initialization.

## 6. `super(...)` Calls Must Use Valid Arguments Before Superclass Initialization

When placing `super(expression)` in a subclass constructor, Java needs to evaluate the arguments to select/supply data to the parent constructor. In **Java 17**, you cannot freely use `this`, instance fields of the object under construction, or ordinary instance methods on the current object before the superclass constructor.

Incorrect in intent/syntax:

~~~java
class Parent {
    Parent(String value) {
    }
}

class Child extends Parent {
    private String name = "Child";

    Child() {
        // super(this.name);       // Invalid in Java 17
        // super(makeName());      // Invalid if makeName is an instance method
        super("Child");
    }

    String makeName() {
        return name;
    }
}
~~~

Child's field initializer `name = "Child"` **has not run yet** before the Parent constructor. Attempting to use Child's instance state to compute an argument violates the initialization order.

### 6.1. Using Constructor Parameters and Static Helpers

~~~java
class Parent {
    private final String id;

    Parent(String id) {
        this.id = id;
    }
}

class Child extends Parent {
    Child(String raw) {
        super(normalize(raw));
    }

    private static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return raw.trim();
    }
}
~~~

`normalize` is a static helper and does not require the current Child object, making it suitable for computing data passed into `super(...)`. If normalize throws an exception, construction fails before the Parent constructor is called.

**Best practice:** pass **parameters, constants, or results of helpers that do not depend on uninitialized state**. Let the superclass establish its own invariants.

## 7. Complete Program: `super(...)` Across Multiple Constructor Levels

Create the file **`SuperConstructorDemo.java`**:

~~~java
public class SuperConstructorDemo {
    static class Person {
        private final String name;

        Person(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Name rỗng");
            }
            this.name = name;
            System.out.println("Person(" + name + ")");
        }

        public final String name() {
            return name;
        }
    }

    static class Employee extends Person {
        private int level = initializeLevel();
        private final int number;

        private int initializeLevel() {
            System.out.println("Employee field initializer");
            return 1;
        }

        Employee(String name, int number) {
            super(name);
            if (number <= 0) {
                throw new IllegalArgumentException("Number sai");
            }
            this.number = number;
            System.out.println("Employee(" + number + ")");
        }

        public final String summary() {
            return name() + "#" + number + ",level=" + level;
        }
    }

    static final class Manager extends Employee {
        Manager(String name, int number) {
            super(name, number);
            System.out.println("Manager constructor");
        }
    }

    public static void main(String[] args) {
        Manager manager = new Manager("Lan", 7);
        System.out.println("Ready = " + manager.summary());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 SuperConstructorDemo.java
java SuperConstructorDemo
~~~

**Exact stdout:**

~~~text
Person(Lan)
Employee field initializer
Employee(7)
Manager constructor
Ready = Lan#7,level=1
~~~

**Explanation of the order:**

1. `new Manager("Lan", 7)` begins constructing an object with runtime class Manager.
2. `Manager(...)` calls `super(name, number)`, i.e., `Employee(String,int)`.
3. `Employee(...)` calls `super(name)`, i.e., `Person(String)`.
4. `Person` initializes the field `name`, validates the input, and then prints `Person(Lan)`.
5. Once the Person constructor completes, Employee's instance initialization runs the field initializer `initializeLevel()`, prints the corresponding line, and assigns `level=1`.
6. The body of the Employee constructor validates `number`, assigns the final field, and prints `Employee(7)`.
7. The Manager constructor body prints `Manager constructor`.
8. The caller only receives the Manager object after the entire constructor chain finishes normally; `summary()` can then read the initialized state.

**There are not three separate Person, Employee, and Manager objects.** It is **a single Manager object** initialized through a three-level superclass chain.

### 7.1. What If a Parent Constructor Throws an Exception?

If the Person constructor throws `IllegalArgumentException`, execution will **not** proceed to the Employee field initializer, Employee constructor body, or Manager constructor body in the example. A failed constructor call does not return a completely initialized object to the caller.

### 7.2. What If the Subclass Has Multiple Constructors?

One constructor can call `this(...)` to delegate, but the final chain still needs a valid path to a superclass constructor. `this(...)` is not a way to bypass `super(...)` or initialize Parent state twice.

## 8. `super.method()`: Calling a Superclass Implementation

When a subclass overrides an instance method, calling `this.method()` or `method()` can run the subclass implementation via dynamic dispatch. If the code **wants to invoke the superclass behavior**, it can use `super.method()`:

~~~java
class Parent {
    String greeting() {
        return "Hello";
    }
}

class Child extends Parent {
    @Override
    String greeting() {
        return super.greeting() + ", Java";
    }
}
~~~

With `new Child().greeting()`, the result is `"Hello, Java"`.

Here:

- `Child.greeting()` is the overriding implementation.
- `super.greeting()` explicitly targets the superclass method instead of calling `Child.greeting()` again.
- If you wrote `return greeting() + ", Java";` inside Child.greeting, the call would repeatedly invoke the override itself (unbounded recursion) and cause a `StackOverflowError`.
- `super.greeting()` executes on the same receiver Child object without creating a new Parent.

### 8.1. Is It Always Necessary to Call `super.method()` When Overriding?

**No.** Java does not require an overriding method to invoke the superclass implementation. It depends on the contract:

- Override **completely replaces** behavior: you may omit calling `super`.
- Override **extends** behavior: typically calls `super.method()` and then performs additional work.
- Override wants to **add checks before or after**: you need to consider execution order, side effects, and exceptions.
- If the superclass method manages a mandatory invariant or lifecycle, the subclass must follow the documented contract; sometimes an API should mark the entry point `final` and only expose protected hooks rather than expecting subclasses to remember to call `super`.

**Design rule:** call `super` because it matches the API contract, not out of a mandatory "ritual" in every override.

## 9. Pattern for Extending Behavior While Preserving the Parent Portion

For example, the parent class handles standard data, and the child class adds metadata:

~~~java
class Report {
    String render() {
        return "Core report";
    }
}

class DetailedReport extends Report {
    @Override
    String render() {
        String base = super.render();
        return base + " / details";
    }
}
~~~

`new DetailedReport().render()` returns `"Core report / details"`.

### 9.1. Should `super` Be Called Before or After Custom Behavior?

There is no single right order for every domain:

~~~java
@Override
void execute() {
    validateSpecialInput();
    super.execute();
    afterExecute();
}
~~~

This is an illustrative **method fragment** and requires the corresponding methods in the class. If validation before `super.execute()` can throw an exception, the superclass action will not run. If `super.execute()` throws an exception, `afterExecute()` will not run either unless there is a `finally` block or appropriate handling.

**For cleanup/resources**, do not automatically call `super.close()` in an arbitrary order not backed by a documented contract. You should check whether the superclass manages resources, whether idempotency is required, and how exceptions are handled.

### 9.2. `super` Is Not a Way to "Call the Parent Method and Automatically Merge Both Results"

The return value of `super.method()` must be handled explicitly. If the method is `void`, you simply call it; if it returns a String/object, you can store the result, modify it, or return it directly depending on the API semantics.

When an override has a covariant return type, the result must still obey return type compatibility according to Java's rules.

## 10. Complete Program: Dynamic Dispatch and `super.method()`

Create the file **`SuperMethodDemo.java`**:

~~~java
public class SuperMethodDemo {
    static class Base {
        String kind() {
            return "base";
        }

        String describe() {
            return "Base[" + kind() + "]";
        }
    }

    static final class Child extends Base {
        @Override
        String kind() {
            return "child";
        }

        @Override
        String describe() {
            return "Child<" + super.describe() + ">";
        }

        String compareKinds() {
            return super.kind() + "/" + this.kind();
        }
    }

    public static void main(String[] args) {
        Base ref = new Child();
        Child child = (Child) ref;

        System.out.println("Description = " + ref.describe());
        System.out.println("Kinds = " + child.compareKinds());
        System.out.println("Runtime = "
                + ref.getClass().getSimpleName());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SuperMethodDemo.java
java SuperMethodDemo
~~~

**Exact stdout:**

~~~text
Description = Child<Base[child]>
Kinds = base/child
Runtime = Child
~~~

**What happens?**

1. `Base ref = new Child()` is upcasting; it does not create a new Base object.
2. `ref.describe()` is a virtual instance method call; the runtime class Child causes Java to select `Child.describe()`.
3. Child.describe calls `super.describe()` to execute **Base.describe() on the same Child object**.
4. **Inside Base.describe(), the call to `kind()` is still a virtual call**. The receiver is still the Child object, so Java selects `Child.kind()`, returning `"child"`. Therefore, Base.describe returns `"Base[child]"`.
5. Child.describe wraps the result with `Child<...>`.
6. `super.kind()` in Child.compareKinds selects `Base.kind()`, returning `"base"`.
7. `this.kind()` is a virtual call and returns `"child"`.
8. `ref.getClass()` returns the runtime class Child, not the compile-time type Base of the variable ref.

**Especially important:** `super.describe()` selects Base.describe at the **call entry point**, but **does not lock every method call inside Base.describe to Base**. Virtual calls invoked inside can still dispatch to subclass overrides.

## 11. Why Does `super.method()` Not Call the Same Override Infinitely?

Given the code:

~~~java
class Child extends Parent {
    @Override
    void run() {
        super.run();
    }
}
~~~

`super.run()` is not treated like `this.run()` to immediately dispatch to Child.run again. It resolves the appropriate superclass implementation according to Java's rules, so it can help extend behavior without directly causing self-recursion.

However, that does **not** guarantee the superclass method will never **indirectly** call another overridable method that Child has overridden. For example, Parent.run() might call `hook()`, and if Child.hook() in turn calls Child.run(), the call graph can still become recursive. You must examine the entire call path, not just the `super` syntax on a single line.

### 11.1. Can `super.method()` Be Called Outside an Overriding Method?

Yes, provided it is valid under access and method resolution rules. For example, Child has a method `displayBase()` that does not override any method, yet wants to call `super.describe()` from an instance context:

~~~java
class Child extends Parent {
    String displayBase() {
        return super.describe();
    }
}
~~~

This form is valid only when the superclass declares/provides `describe()` accessible from Child with a compatible return type. The method being written does not have to share the same name as the method being called.

## 12. `super.field`: Accessing a Field Hidden by a Subclass Declaration

Fields in Java **do not override via dynamic dispatch**. If Parent and Child declare a field with the same name, the Child field can **hide** the Parent field, creating two distinct fields within **the same object**.

~~~java
class Parent {
    protected String label = "P";
}

class Child extends Parent {
    private String label = "C";

    String both() {
        return this.label + "/" + super.label;
    }
}
~~~

In Child.both():

- `this.label` selects the field declared in Child.
- `super.label` selects the field declared in the superclass Parent.
- There is no separate Parent object; they are two fields declared along an inheritance chain and both exist in the Child instance.

### 12.1. Cases Using Field Hiding Require Careful Consideration

Field hiding is valid, yet easily misleading:

~~~java
Parent ref = new Child();
System.out.println(ref.label);
~~~

`ref.label` is resolved according to the **compile-time type Parent** of `ref`, not the runtime Child object. This is an important difference from instance method overriding. If you want polymorphic behavior, use a method with a clear contract rather than trying to rely on field hiding.

**Recommendation:** do not deliberately declare a field with the same name as one in the superclass just to "replace Parent's value." Typically, use private fields + protected/public methods with validation, or constructor parameters when the subclass needs to specify superclass state.

## 13. Complete Program: `super.field` and Field Hiding

Create the file **`SuperFieldDemo.java`**:

~~~java
public class SuperFieldDemo {
    static class Parent {
        protected String code = "P";

        String parentCode() {
            return code;
        }
    }

    static final class Child extends Parent {
        private String code = "C";

        String bothCodes() {
            return this.code + "/" + super.code;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Parent ref = child;

        System.out.println("Parent ref field = " + ref.code);
        System.out.println("Parent method = " + ref.parentCode());
        System.out.println("Child both = " + child.bothCodes());
        System.out.println("Same object = " + (ref == child));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SuperFieldDemo.java
java SuperFieldDemo
~~~

**Exact stdout:**

~~~text
Parent ref field = P
Parent method = P
Child both = C/P
Same object = true
~~~

Explanation:

1. `ref` has compile-time type Parent, so `ref.code` selects `Parent.code`.
2. `Parent.parentCode()` is inherited; its body reads the `code` declared in Parent, returning P.
3. `Child.bothCodes()` accesses both `this.code` (Child field C) and `super.code` (Parent field P).
4. Both `child` and `ref` are references to **the same Child object**, so the identity comparison returns true.

### 13.1. Why Shouldn't `super.field` Be Used to Modify a Private Field?

If Parent declares `private String code`, Child **cannot** write `super.code` merely because of the extends relationship. `super` does not bypass visibility. To let Child interact under a controlled contract, Parent can provide an appropriate `protected final` method, constructor parameter, or public API instead of exposing the field.

## 14. `super` and Access Modifiers

A subclass can only access a superclass member if Java's access rules allow it. `super` **is not a mechanism for breaking `private`**, package boundaries, or JPMS module encapsulation.

| Superclass member | Can `super` be used? | Notes |
| --- | --- | --- |
| `public` instance method | Yes, when the class/member is accessible | Commonly used to extend an override |
| `protected` instance method | Yes, in an appropriate subclass context | Pay special attention to different packages and receiver rules |
| Package-private member | Only if package-level access is valid | Not automatically exposed across packages |
| `private` field/method | No, cannot be accessed directly from a subclass | Use a controlled API if needed |
| `final` instance method | Can be called if accessible | However, the subclass cannot override that method |
| Static method | Should be called via `DeclaringClass.method()` | Static hiding, not instance overriding |
| Constructor | Use `super(args)` if accessible | Not inherited like an instance method |

### 14.1. `protected` Does Not Mean `public`

Suppose Parent is in package `model` and Child is in package `app`. Child can use a protected instance member from a subclass context following the rules, but cannot arbitrarily access that member through **any Parent object**.

Example with two files:

**`model/Base.java`**

~~~java
package model;

public class Base {
    protected int value = 10;

    protected void check() {
        System.out.println(value);
    }
}
~~~

**`app/Derived.java`**

~~~java
package app;

public class Derived extends model.Base {
    public int readOwnInheritedValue() {
        return super.value;
    }

    public void runBaseCheck() {
        super.check();
    }

    // public int readAnyBase(model.Base other) {
    //     return other.value; // Not valid merely because Derived extends Base
    // }
}
~~~

This is a **package structure illustration**, not one of the standalone runnable programs. If you build it, place the files in the matching package directories and ensure compatible modules/exports when using JPMS.

### 14.2. `private` Superclass Constructor

If Parent has a private constructor, only contexts permitted by access rules can call it. Another class Child cannot assume `super()` can access a private constructor, even if it writes `extends Parent`.

If you do not want a class to be subclassed, a `final class` or appropriate constructor visibility design makes the intent clearer.

## 15. `super` and Overriding a `final` Method

A superclass can lock a method with `final`:

~~~java
class Base {
    public final String id() {
        return "fixed";
    }
}

class Child extends Base {
    // public String id() { return "changed"; } // Error: overriding final method
}
~~~

Child cannot override `id()`, but it can **call that method** via an inherited method call `id()`, `this.id()`, or the `super.id()` syntax in an instance context if valid. The `super.id()` syntax does not turn a final method into an overridable one.

When you want a subclass to extend a workflow without altering mandatory validation, you can design a `final template method` in Base that calls appropriate protected hooks at safe stages. That is usually better than hoping every overriding subclass remembers to call `super.validate()` properly.

## 16. Static Method Hiding Is Not the Same as `super.method()` for Overrides

If Parent and Child have static methods with matching names/signatures:

~~~java
class Parent {
    static String category() {
        return "Parent";
    }
}

class Child extends Parent {
    static String category() {
        return "Child";
    }
}
~~~

This is **static method hiding**, not instance overriding. There is no current object receiver used for dynamic dispatch of a static method.

You should call them explicitly:

~~~java
System.out.println(Parent.category());
System.out.println(Child.category());
~~~

Do not treat `super.category()` as a necessary polymorphism tool for static methods. In modern code, accessing a static member by the **declaring class name** makes the intent clearer.

### 16.1. `super` Is Invalid in a Subclass's Static Context

~~~java
class Child extends Parent {
    static void test() {
        // super.toString(); // Invalid: super in a static context
    }
}
~~~

A static method has no current Child instance, so `super` cannot be used to call a superclass instance method on the current object. If you need to process a Parent/Child object, pass the receiver explicitly into the static method or change the design to an instance method.

### 16.2. `super` and `this` in Nested Classes

In a **non-static inner class**, `this` is the inner object, and a syntax like `Outer.this` can refer to the enclosing outer object in a valid context. `super` inside an instance method of the inner class refers to the superclass of the **inner class**, and does not automatically become the superclass of Outer.

A **static nested class** still has instance methods and its own `this`/`super` for the nested instance itself, even though it has no implicit enclosing Outer instance.

Unless nested inheritance is truly needed, it is generally better to keep `super` examples on top-level classes or static nested classes so the superclass is easy to identify.

## 17. `super.method()` Still Uses the Actual Receiver, Not a "Parent Copy"

When Child overrides an instance method:

~~~java
class Base {
    protected int count;

    void increase() {
        count++;
    }

    int current() {
        return count;
    }
}

class Child extends Base {
    @Override
    void increase() {
        super.increase();
        super.increase();
    }
}
~~~

With `Child child = new Child(); child.increase();`, the field `count` of the Base part inside **the Child object itself** increments to 2. No implicit `new Base()` occurs at the call `super.increase()`. A subclass can access Base's state through a protected field/method following the applicable rules.

### 17.1. There Is No `super.super.method()`

Java does not allow writing:

~~~java
// super.super.method(); // Invalid
~~~

to "skip over" the direct superclass to a grandparent. With `GrandParent → Parent → Child`, if you want to reuse grandparent behavior, design methods with appropriate contracts so Parent and Child coordinate, such as a protected method or composition. `super.method()` selects an implementation following resolution rules along the superclass chain, rather than being syntax to arbitrarily pick any ancestor.

### 17.2. What If the Superclass Does Not Declare the Method, but Inherits It?

`super.method()` can resolve to the appropriate inherited implementation from a more distant superclass according to lookup rules. The direct superclass does not necessarily have to define the method body itself.

~~~java
class Root {
    String label() {
        return "Root";
    }
}

class Middle extends Root {
}

class Leaf extends Middle {
    String baseLabel() {
        return super.label();
    }
}
~~~

`Leaf.baseLabel()` is valid and receives `"Root"` even though Middle does not declare its own `label()`. This is **not** `super.super` syntax; valid lookup along the inheritance chain finds the appropriate method.

## 18. `super` Across Three Inheritance Levels

~~~java
class Root {
    String label() {
        return "Root";
    }
}

class Middle extends Root {
    @Override
    String label() {
        return "Middle>" + super.label();
    }
}

class Leaf extends Middle {
    @Override
    String label() {
        return "Leaf>" + super.label();
    }
}
~~~

`new Leaf().label()` returns:

~~~text
Leaf>Middle>Root
~~~

Explanation:

1. Virtual call selects Leaf.label.
2. `super.label()` in Leaf selects Middle.label.
3. `super.label()` in Middle selects Root.label.
4. The strings are concatenated as the call stack unwinds.

This is a good example of **extending behavior across multiple levels** when Parent/Middle already have an appropriate contract. However, if a deep hierarchy forces everyone to call `super` in a complicated order to preserve business logic, it may be time to consider composition or a controlled template method.

## 19. `super(...)` and `super.method()` When the Superclass Is Abstract

An **abstract superclass** still has a constructor to initialize its shared state:

~~~java
abstract class Device {
    private final String serial;

    protected Device(String serial) {
        this.serial =
                java.util.Objects.requireNonNull(serial);
    }

    public final String serial() {
        return serial;
    }

    public abstract String kind();
}

class Sensor extends Device {
    Sensor(String serial) {
        super(serial);
    }

    @Override
    public String kind() {
        return "Sensor";
    }
}
~~~

`new Device(...)` is invalid because Device is abstract, whereas `new Sensor("S1")` is valid provided the entire constructor chain and abstract method implementations satisfy the rules.

### 19.1. Do Not Use `super.abstractMethod()` If There Is No Superclass Implementation

If the superclass only declares:

~~~java
abstract class Parent {
    abstract void work();
}
~~~

A subclass implementing `work()` cannot call `super.work()` to execute the "parent implementation" because an abstract method **has no method body** there.

~~~java
class Child extends Parent {
    @Override
    void work() {
        // super.work(); // Invalid: abstract method has no body
        System.out.println("Child work");
    }
}
~~~

If you want to reuse shared logic, the superclass should provide a concrete helper such as `protected final void validate()`, or delegate behavior to a collaborator.

### 19.2. An Abstract Superclass Constructor Should Not Call an Abstract Hook

A common design mistake:

~~~java
abstract class Base {
    Base() {
        onReady(); // May dispatch to Child before Child is initialized
    }

    abstract void onReady();
}
~~~

When instantiating a concrete subclass, the JVM can still dispatch to Child's override **before Child's fields/constructor body run**. `super(...)` does not guarantee the subclass is ready during the superclass constructor. Reserve abstract hooks for the stage after object construction completes, or pass required data via constructor arguments.

## 20. `InterfaceName.super.method()`: Selecting an Interface's Default Method

Alongside class superclasses, Java also has **interfaces with default methods**. A class implementing multiple interfaces that have a default method with the same signature may need to override it to resolve the conflict.

The syntax:

~~~java
InterfaceName.super.method(arguments)
~~~

is the way to select a **default method implementation** from an appropriate **superinterface** in a valid context.

### 20.1. Example with Two Default Methods Sharing the Same Name

~~~java
interface English {
    default String greeting() {
        return "Hello";
    }
}

interface Vietnamese {
    default String greeting() {
        return "Xin chào";
    }
}

class Bilingual implements English, Vietnamese {
    @Override
    public String greeting() {
        return English.super.greeting()
                + " / "
                + Vietnamese.super.greeting();
    }
}
~~~

If the Bilingual class does not resolve the conflict itself, the compiler cannot choose one of the two unrelated default methods by default. The syntax `English.super.greeting()` and `Vietnamese.super.greeting()` makes the intent explicit.

**Difference from `super(...)`:** interfaces do not have constructors like classes and cannot be instantiated with `new Interface()`. `English.super.greeting()` is a default method call, **not a constructor call**.

### 20.2. When Both a Class Method and an Interface Default Method Exist

Java has precedence rules, often summarized as **class methods win over interface defaults** in applicable cases. Do not assume that merely having a default implementation means Java will always use it when a superclass already provides a matching concrete instance method.

If you want to explicitly choose a superinterface's default implementation, you need to check the rules regarding direct superinterfaces, overriding, and validity of qualified-super invocations; not every `SomeInterface.super.method()` expression is valid merely because that type appears somewhere in the hierarchy.

## 21. Complete Program: Selecting Multiple Interface Default Implementations

Create the file **`InterfaceSuperDemo.java`**:

~~~java
public class InterfaceSuperDemo {
    interface English {
        default String greeting() {
            return "Hello";
        }
    }

    interface Vietnamese {
        default String greeting() {
            return "Xin chào";
        }
    }

    static final class Bilingual
            implements English, Vietnamese {
        @Override
        public String greeting() {
            return English.super.greeting()
                    + " / "
                    + Vietnamese.super.greeting();
        }
    }

    public static void main(String[] args) {
        Bilingual speaker = new Bilingual();

        System.out.println("Combined = " + speaker.greeting());
        System.out.println("English subtype = "
                + (speaker instanceof English));
        System.out.println("Vietnamese subtype = "
                + (speaker instanceof Vietnamese));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 InterfaceSuperDemo.java
java InterfaceSuperDemo
~~~

**Exact stdout:**

~~~text
Combined = Hello / Xin chào
English subtype = true
Vietnamese subtype = true
~~~

**Things to remember:**

- `Bilingual` does not extend two classes; it implements two interfaces.
- Each interface declares a default method `greeting()`.
- Bilingual overrides the method to resolve the conflict and selects both implementations using `InterfaceName.super.method()`.
- `speaker instanceof English` and `speaker instanceof Vietnamese` are both true because the object implements both contracts.
- This is not multiple inheritance of class state/constructors: there is no `English()` or `Vietnamese()` to call with `super(...)`.

## 22. An Interface That `extends` Another Interface Also Has No `super(...)` Constructor

An interface can extend one or more other interfaces:

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWrite extends Readable, Writable {
}
~~~

`ReadWrite` is a subinterface of both Readable and Writable. However, **interfaces do not have instance constructors**. Do not place `super()` in an interface to initialize superinterfaces.

A class implementing ReadWrite may need to implement the corresponding abstract methods. If the interfaces have default methods, qualified-super syntax related to method resolution/default inheritance can be useful.

**Distinguishing the two uses of `extends`:**

- `class Child extends Parent`: a single direct class superclass, constructor chain, and class state/method inheritance.
- `interface ChildI extends ParentI1, ParentI2`: multiple superinterfaces, with no interface constructor chain.
- `class Concrete implements Interface`: an interface subtype relationship, which can also extend a valid class at the same time.

## 23. `super` Does Not Bypass the Single Direct Superclass Rule

A Java class has only **one direct superclass**. Therefore, `super(...)` does not mean "pick any parent class from a list":

~~~java
// class Child extends A, B { } // Java does not allow multiple class inheritance
~~~

If Child needs to combine two independent behaviors, it can:

- Extend one superclass if it is genuinely a subtype.
- Implement multiple interfaces.
- Use **composition** to hold references to collaborators.
- Call methods on collaborators instead of trying to use multiple `super` constructor calls.

A class containing `private final Engine engine` is a **has-a** relationship, not a `super` relation. The Child/Car constructor can create/inject Engine, but that is explicit initialization of a component object, not a new superclass.

## 24. Error Handling When Calling `super(...)`

A superclass constructor can throw an exception if input is invalid:

~~~java
class Base {
    Base(int capacity) {
        if (capacity < 1) {
            throw new IllegalArgumentException("Capacity sai");
        }
    }
}

class Child extends Base {
    Child(int capacity) {
        super(capacity);
        System.out.println("Child ready");
    }
}
~~~

When calling `new Child(0)`:

- The Parent/Base constructor is called before the Child body.
- Base throws `IllegalArgumentException`.
- The Child body does not run, so `Child ready` is not printed.
- The `new Child(0)` call completes abruptly.

If a superclass constructor declares a checked exception, the subclass constructor must handle it according to **Java constructor invocation/throws rules**, typically by declaring an appropriate `throws` clause; you cannot wrap a `super(...)` call inside a `try/catch` in the constructor body as if it were an ordinary call placed after another statement in Java 17.

### 24.1. A Valid Constructor Does Not Guarantee the Object Is Always Invariant-Safe

If the superclass constructor calls an overridable method that relies on uninitialized Child state, the entire constructor chain can still **compile** while failing with a bug at runtime. `super(...)` only guarantees sequential initialization; **it does not guarantee that every polymorphic hook called inside a constructor is safe**.

## 25. Complete Program: Handling Errors from a Parent Constructor

Create the file **`SuperValidationDemo.java`**:

~~~java
public class SuperValidationDemo {
    static class Capacity {
        private final int limit;

        Capacity(int limit) {
            if (limit < 1) {
                throw new IllegalArgumentException("Limit phải dương");
            }
            this.limit = limit;
            System.out.println("Base accepted " + limit);
        }

        int limit() {
            return limit;
        }
    }

    static final class LimitedQueue extends Capacity {
        private final String name;

        LimitedQueue(String name, int limit) {
            super(limit);
            this.name = java.util.Objects.requireNonNull(
                    name, "name");
            System.out.println("Queue ready " + name);
        }

        String summary() {
            return name + "/" + limit();
        }
    }

    public static void main(String[] args) {
        LimitedQueue valid = new LimitedQueue("jobs", 3);
        System.out.println("Summary = " + valid.summary());

        try {
            new LimitedQueue("bad", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Command:

~~~bash
javac -encoding UTF-8 SuperValidationDemo.java
java SuperValidationDemo
~~~

**Exact stdout:**

~~~text
Base accepted 3
Queue ready jobs
Summary = jobs/3
Rejected = Limit phải dương
~~~

`new LimitedQueue("bad",0)` does not print `Queue ready bad` because `super(0)` throws an exception before the Child constructor body runs. The parent still controls `limit` validation, while the subclass controls `name` if the parent constructor completes.

**Note:** in the exception case, no Queue object that completed construction is returned to the caller. That does not mean any side effects that already occurred in a failing constructor automatically roll back; avoid registering `this`, writing non-rollbackable resources, or publishing events too early.

## 26. `super.method()` with Checked Exceptions and Override Contracts

If a superclass method declares a checked exception:

~~~java
class ReaderBase {
    String read() throws java.io.IOException {
        return "base";
    }
}
~~~

A subclass override wanting to use `super.read()` must comply with checked exception handling:

~~~java
class ReaderChild extends ReaderBase {
    @Override
    String read() throws java.io.IOException {
        return super.read().toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

If the overriding method wants to **omit** declaring the checked exception, it can catch the exception and handle it appropriately in the body. However, it must not silently swallow semantics if the contract requires the caller to know about IO errors.

### 26.1. Visibility and Return Type When Overriding

An overriding method cannot reduce visibility (for example, Parent public → Child protected), and the return type must be compatible. For reference types, Java allows a **covariant return type**.

The `super.method()` syntax does not bypass those override rules. The compiler still checks whether Child's declaration is valid with respect to the superclass method.

### 26.2. Overloading and Selecting a Superclass Overload

`super.print(argument)` is a method call, so the compiler still applies overload resolution based on the **compile-time types** of the argument.

~~~java
class Base {
    String print(Object value) {
        return "Object";
    }

    String print(String value) {
        return "String";
    }
}

class Child extends Base {
    String sample(Object value) {
        return super.print(value);
    }
}
~~~

`new Child().sample("hello")` returns `"Object"` because the formal parameter `value` in `sample` has compile-time type Object. The runtime String object does not force overload resolution to select print(String).

**Do not confuse** compile-time overload selection with runtime override dispatch. In the case of `super.print(...)`, selecting the superclass implementation is also governed by qualified-super invocation rules.

## 27. When Should You Call `super.method()` in Real-World Code?

### 27.1. Extending Behavior While Preserving the Superclass Contract

For example, an override of `toString()` wants to append Child state after calling `super.toString()`:

~~~java
class Base {
    @Override
    public String toString() {
        return "Base";
    }
}

class Child extends Base {
    @Override
    public String toString() {
        return super.toString() + "(Child)";
    }
}
~~~

`new Child().toString()` is `"Base(Child)"`. This is a simple use case and can be reasonable when the superclass `toString()` already publishes an appropriate representation.

### 27.2. Adding Processing Before/After a Step Managed by the Superclass

For example, a framework has a protected hook where a subclass must call `super.hook()` to preserve cleanup/base behavior. Only do this if **the documented contract requires it or the semantics genuinely call for it**. Another framework might define an independent hook and not want `super` to be called.

### 27.3. Accessing Overridden Behavior to Combine Logic

If Child wants to use both the Base version and Child-specific logic:

~~~java
@Override
String label() {
    String parentPart = super.label();
    return parentPart + "-" + childPart;
}
~~~

This is a method fragment; `childPart` must belong to the actual class. The goal is to **reuse an already-defined behavior**, not to force every subclass to "always super-call."

### 27.4. When Not to Call `super.method()`

- The override needs to replace the entire algorithm according to the contract.
- The superclass implementation has side effects that are inappropriate in the subclass.
- Calling super twice causes duplicate processing or a double charge.
- The super call closes resources or changes state before Child finishes what it needs to do.
- The subclass uses `super` merely for "code reuse," while not actually being a valid subtype.
- You need the behavior of another collaborator rather than superclass behavior; use composition.

## 28. When Is `super.field` a Sign to Improve the Design?

Using `super.field` to distinguish hidden fields may be necessary when analyzing legacy code, but you should generally avoid creating a hierarchy that intentionally reuses the same field name.

~~~java
class Base {
    protected int size = 10;
}

class Child extends Base {
    int size = 20;

    int both() {
        return size + super.size;
    }
}
~~~

There are two `size` fields; Child does not "change the value of Base.size." When class Base has a method that reads its own `size`, it can still see 10 while Child code sees 20. This easily tangles invariants.

It is usually clearer to:

- Keep only **one field** in Base and pass the value via `super(size)`.
- Make the field private in Base and provide a controlled setter/protected method if it needs to change.
- Use a different field name in Child if the information has different semantics.
- Use composition if the data does not genuinely belong to the same subtype contract.

**`super.field` is a syntactic tool; it does not turn field hiding into a recommended pattern.**

## 29. `super` Does Not Allow Bypassing Everything the Superclass Forbids

Some misconceptions:

- "With `super`, you can read a private Parent field" → **False**.
- "With `super`, you can call a private Parent constructor from any subclass" → **False**.
- "With `super`, you can override a final method" → **False**.
- "With `super`, you can skip an abstract method that has no body" → **False**.
- "With `super`, you can call a grandparent constructor directly using `super.super()`" → **False**.
- "With `super`, a subclass is allowed to break Parent invariants" → **False** in terms of design, and access controls are still enforced by the compiler.
- "Using `super` in a static method automatically creates a Parent instance" → **False**.

Remember that `super` is checked by the compiler according to **declaration context, inheritance relationship, accessibility, and member-resolution rules**. It is not a privilege that overrides all restrictions in Java.

## 30. `super(...)` and Final Fields

A superclass's blank final instance field must generally be assigned exactly once by a superclass constructor or a valid instance initializer on all initialization paths that complete normally:

~~~java
class Base {
    private final String id;

    Base(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    String id() {
        return id;
    }
}

class Child extends Base {
    private final String tag;

    Child(String id, String tag) {
        super(id);
        this.tag = java.util.Objects.requireNonNull(tag);
    }
}
~~~

`super(id)` lets Base assign `Base.id` itself. Child should not and cannot validly reassign a final field already initialized by Parent. Child is responsible for assigning `Child.tag`.

### 30.1. Do Not Fix Definite Assignment Errors by Making a Parent Field protected

If Child needs to give Parent an ID, **pass it through the constructor**; do not change `private final String id` to `protected String id` and let Child assign it freely. That weakens Parent's invariant and can break immutability.

### 30.2. Static final Fields Are Not Initialized by a Constructor

`static final` belongs to the class and has different initializer rules. Calling `super(...)` does not mean a subclass can assign a blank static final field of the superclass from a constructor. The superclass must manage static state according to Java's rules.

## 31. Special Considerations with `Object`

Any ordinary class without an explicit superclass has `java.lang.Object` as its direct superclass according to Java's rules. Object's constructor participates in the instance initialization chain.

~~~java
class Simple {
    Simple() {
        super(); // Valid: calls Object()
    }
}
~~~

You do not need to write `super()` explicitly in every constructor. Java can insert an implicit super() call when appropriate.

Regarding Object methods:

- `toString()` can usually be overridden; Child can call `super.toString()` to get the superclass implementation.
- `equals(Object)` and `hashCode()` have important contracts; inheritance/overriding must preserve symmetry, transitivity, and consistency.
- `getClass()` is final, cannot be overridden, and when called on a Child object still returns the runtime class Child.
- `wait()`, `notify()`, and `notifyAll()` relate to monitor synchronization; do not use `super` as a way to bypass thread synchronization.

### 31.1. `super.toString()` Does Not Guarantee Bypassing All Subclass Behavior

If the direct superclass has overridden `toString()` and calls a virtual hook inside it, calling `super.toString()` from Child enters the superclass toString, but the hook can still dispatch to Child. This is similar to the earlier example where `Base.describe()` called `kind()`.

If you need to log state in a constructor, avoid calling a polymorphic `toString()` on an incompletely initialized object.

## 32. `super` and sealed/final/record/enum in Java 17

### 32.1. Final Class

If a superclass is `final`, no subclass can be declared with `extends`, so there is no valid subclass context in which to use `super(...)` for that final class.

~~~java
final class Closed {
}

// class Child extends Closed {} // Invalid
~~~

A **final subclass** still has a superclass (if not Object) and can call `super(...)` in its constructor. The `final` modifier on the subclass only forbids **further subclasses**, not extending a superclass.

### 32.2. Sealed Class

Java 17 allows a `sealed` class to restrict its direct permitted subclasses:

~~~java
sealed class Base permits ChildA, ChildB {
    Base(String id) {
    }
}

final class ChildA extends Base {
    ChildA() {
        super("A");
    }
}

final class ChildB extends Base {
    ChildB() {
        super("B");
    }
}
~~~

`ChildA` and `ChildB` still use `super(...)` just like ordinary class inheritance. Sealed controls **who may extend**, without changing the fundamental semantics of the superclass constructor.

### 32.3. Records

A Java 17 record is implicitly final and inherits from `java.lang.Record` according to language semantics. You cannot write a record declaration with `extends CustomParent`, nor can you use a record as an arbitrary subclass in a class hierarchy.

~~~java
record Point(int x, int y) {
}
~~~

Record constructors have their own rules for components and compact/canonical constructors; **you do not write an explicit `super(...)` to call a custom superclass constructor** as in an ordinary subclass. A record can implement interfaces with appropriate default methods.

### 32.4. Enums

An enum type has its own constructor/superclass characteristics related to `java.lang.Enum`. Enum constructors cannot explicitly write `super(...)` to call Enum's constructor with arbitrary syntax:

~~~java
enum Mode {
    FAST, SAFE
}
~~~

This is not an ordinary subclass where developers explicitly call `super(...)` to `Enum`. The compiler and the language manage the construction of enum constants under special rules.

## 33. Common Errors and How to Fix Them

| Error / Misconception | Cause | How to Fix |
| --- | --- | --- |
| Parent has no no-arg constructor, and Child omits `super(args)` | Implicit `super()` does not exist or is not accessible | Declare a Child constructor that calls an appropriate Parent constructor |
| Writing code before `super(...)` in Java 17 | Explicit constructor invocation must be the first statement | Compute input via parameters/static helper; place `super(...)` at the start of the body |
| Using both `this(...)` and `super(...)` in one constructor | Two explicit constructor invocations cannot coexist in the body like that | Chain `this(...)` to a target constructor that calls `super(...)` |
| Writing `super.super.method()` | Java has no syntax to arbitrarily target a grandparent | Design an appropriate API/protected helper |
| Accessing `super.privateField` | `super` does not bypass private access | Use a controlled accessor/constructor argument |
| Calling `super.abstractMethod()` | There is no method body to invoke | Extract a concrete base helper, or implement the method yourself |
| Using `super` in a static method | There is no current instance receiver | Pass the object explicitly; use the class name for static members |
| Thinking `super(...)` creates a separate Parent object | A single Child object holds the superclass state portion | Revisit how the constructor chain works |
| Calling `this.method()` instead of `super.method()` in an override wanting base behavior | Dynamic dispatch may call the override again | Use `super.method()` when the contract needs the parent implementation |
| Thinking `super.method()` disables dispatch for all calls inside the base body | Deeper virtual calls still dispatch based on the runtime receiver | Inspect the call graph/invariants |
| Calling `super.method()` in every override as a ritual | Not every override needs base behavior | Follow contract/hook documentation |
| Using `super.field` to simulate overriding state | Fields use hiding, not dispatch like methods | Private state + controlled APIs |
| Calling `super(...)` with a reference to an uninitialized Child instance field | Java 17 forbids it and the state is not ready yet | Use constructor parameters/static helper |
| Parent constructor calls an overridable hook | Child override runs before Child fields are ready | Do not call virtual hooks in constructors |
| Confusing `InterfaceName.super.defaultMethod()` with a constructor | Interfaces do not have constructors | Use it only to select a default implementation |
| Using `ClassName.super.method()` arbitrarily | Qualified super has specific context/lexical enclosing rules | Learn and use the proper syntax only when needed |
| Trying to extend a final superclass | `final` forbids subclassing | Use composition/interfaces or a class permitted to be extended |
| Using `super.method()` on an inaccessible API | Access rules still apply | Adjust design/access appropriately |
| Parent constructor throws an exception while Child expects its body to run | Construction does not complete normally | Validate input and handle the exception in the caller |
| Trying to call `super(...)` on a record/enum like a normal class | Records/enums have special construction rules | Use the appropriate constructor/canonical/compact enum syntax |

## 34. A Reasoning Method When Reading `super`

When encountering a line of code using `super`, ask in order:

1. **Is the token after `super` parentheses `(...)` or a dot?**
   - `super(...)`: constructor invocation.
   - `super.member`: member access/invocation.
2. **Are you inside a constructor or an instance method?**
   - Constructor invocations belong in a constructor.
   - Super member access requires an appropriate instance context.
3. **What direct superclass does the class have?**
   - Identify the class after `extends`, or `Object` where applicable.
4. **If it is a constructor:** which superclass constructor is selected by overload resolution?
5. **Does a no-argument constructor exist?** Do not assume Parent has `Parent()`.
6. **Is access valid?** Private/package/protected/JPMS rules still matter.
7. **If it is a method:** is Child overriding that method or simply calling an inherited implementation?
8. **If there is a method override:** does the contract require executing superclass behavior?
9. **If it is a field:** do Parent and Child hide a field with the same name?
10. **If it is an interface default method:** is `InterfaceName.super` valid in the current declaration?
11. **If the code is in a constructor:** does the superclass/hook rely on uninitialized Child state?
12. **If the code runs concurrently:** calling super does not automatically synchronize shared mutable state.
13. **If there are multiple inheritance levels:** `super` goes to the method resolved along the superclass chain; there is no arbitrary `super.super`.
14. **If exceptions occur:** the constructor chain may stop before the Child body.
15. **If the code depends too heavily on `super`:** should independent behavior be replaced with composition?

Asking these questions helps distinguish a **compile-time syntax/access error**, a **runtime initialization-state bug**, and an **inheritance-contract design issue**.

## 35. Self-Check Questions with Answers

**Question 1.** Which class's constructor does `super(...)` inside a Child constructor call?

**Answer:** Child's direct superclass along the class inheritance chain. It does not create a separate superclass object.

**Question 2.** What happens if Child writes neither an explicit `super(...)` nor `this(...)` in a Java 17 constructor?

**Answer:** The compiler attempts to insert an implicit `super()` according to the rules. If the superclass has no accessible no-argument constructor, the code does not compile.

**Question 3.** Parent has `Parent(int)` but no `Parent()`. Can Child have an auto-generated default constructor?

**Answer:** No, because the default constructor would need a nonexistent or inaccessible `super()`. Child needs a constructor that calls `super(int)`.

**Question 4.** Can a Java 17 Child constructor print a log statement before `super(args)`?

**Answer:** No, if `super(args)` is an explicit constructor invocation placed after the log statement. Under Java 17 rules, it must be at the beginning of the constructor body.

**Question 5.** When should `this(args)` be used instead of `super(args)`?

**Answer:** When a constructor wants to delegate to another constructor in the same class. The final target constructor still participates in superclass initialization.

**Question 6.** Can two `super()` calls be written in one Child constructor?

**Answer:** No. Constructor invocation syntax allows a single appropriate explicit call; superclass initialization cannot be arbitrarily repeated.

**Question 7.** If the Parent constructor throws an exception, does the Child constructor body continue running?

**Answer:** No. Construction terminates abruptly if the exception is not handled in a valid manner, and `new Child()` does not return a completed Child object.

**Question 8.** Does `super.method()` create a new Parent object?

**Answer:** No. It invokes the superclass implementation on the same current receiver object according to Java's rules.

**Question 9.** Inside Child's override of `greet()`, why is `super.greet()` usually different from `this.greet()`?

**Answer:** `super.greet()` selects the superclass implementation. `this.greet()` uses normal instance invocation and can dispatch to Child.greet, causing the override to call itself again.

**Question 10.** If Base.describe() calls an overridable `kind()`, does `super.describe()` from Child force `kind()` to run Base.kind()?

**Answer:** No. Inside Base.describe, `kind()` can still dynamically dispatch to Child.kind based on the runtime object.

**Question 11.** Can `super.field` access a private Parent field?

**Answer:** No. Private access rules still apply; use a controlled superclass API if needed.

**Question 12.** Can `this.code` and `super.code` yield two different values?

**Answer:** Yes, if Child and Parent declare **two fields with the same name**; that is field hiding, not polymorphic overriding.

**Question 13.** When Parent has a final method, can Child write an override and call `super.finalMethod()`?

**Answer:** A final method cannot be overridden. Child can still call the inherited final method if access permits, but it cannot replace its implementation.

**Question 14.** Can `super.method()` invoke an abstract method of Parent that has no body?

**Answer:** No, if the selected method is abstract and has no valid implementation to call.

**Question 15.** Can `super.toString()` be written inside a static method of Child?

**Answer:** No. A static method has no current instance receiver on which to call a superclass instance implementation.

**Question 16.** Does Java have `super.super.method()` syntax?

**Answer:** No. Use a valid inheritance API, or design an appropriate helper/delegation.

**Question 17.** If Middle does not declare `label()` but inherits Root.label(), can Leaf extending Middle call `super.label()`?

**Answer:** Yes, provided lookup/access is valid; it can select the inherited implementation from Root along the superclass chain.

**Question 18.** Can `super.method()` be used inside a method that does not override any method?

**Answer:** Yes, as long as the instance context and method resolution/access are valid. The current method does not have to share the same name.

**Question 19.** Why does `super(...)` not allow bypassing the superclass's validation?

**Answer:** The superclass constructor itself is called to perform the superclass's initialization/validation. There is no mechanism to bypass a valid constructor chain with normal `super` syntax.

**Question 20.** Does `English.super.greeting()` call an English constructor?

**Answer:** No. Interfaces have no constructors; this syntax selects a default method implementation in a valid context.

**Question 21.** Why does a class implementing two interfaces with the same default `greeting()` usually have to override it?

**Answer:** Two unrelated defaults create a conflict that Java does not arbitrarily resolve on its own; the class must resolve the method according to the rules.

**Question 22.** Does `super.method()` make a static method polymorphic?

**Answer:** No. Static methods follow their own resolution/hiding rules and should be called via the declaring class name.

**Question 23.** When class Child is final, can it still call `super(...)`?

**Answer:** Yes. `final` on Child forbids other classes from extending Child; it does not forbid Child from extending a valid superclass.

**Question 24.** Can a Java 17 record `extends Person` and call `super(name)`?

**Answer:** No. Records have their own superclass/constructor rules and are implicitly final, so they cannot extend an arbitrary class.

**Question 25.** Should `super.field` be used as a primary design for two classes to store identically named state?

**Answer:** Usually no. Field hiding easily causes confusion. Use a single field with clear ownership, constructor arguments, or a controlled API.

**Question 26.** Is calling `super.method()` inside a Child constructor always safe?

**Answer:** No. The called method may depend on uninitialized state or call other overridable hooks. You must examine the call graph and initialization order.

**Question 27.** Can a subclass in another package use any `protected` field on any superclass object?

**Answer:** No. Java has special protected access/receiver-type rules across package boundaries.

**Question 28.** If an override wants to **completely replace** Parent behavior, is it mandatory to call `super.method()`?

**Answer:** No. Only call it if the superclass contract or business semantics genuinely require it.

**Question 29.** Why is `super(...)` not equivalent to `new Parent(...)`?

**Answer:** `super(...)` participates in initializing the superclass portion of the current Child object. `new Parent(...)` creates an independent Parent object.

**Question 30.** When should you choose composition instead of overusing `super`?

**Answer:** When you want to reuse a capability or coordinate with a collaborator without Child genuinely being a subtype of Parent, or when the hierarchy relies too heavily on super-calls and hard-to-maintain hooks.

## 36. Checklist When Writing Code with `super`

Before finalizing your code, verify:

1. **Is the subtype relationship reasonable?** Do not use `extends` just to borrow a helper.
2. **Is the direct superclass right?** `super(...)` points along the appropriate superclass chain.
3. **Which Parent constructor is selected?** Is there a compatible and accessible overload?
4. **Is there an implicit `super()`?** If an explicit invocation is omitted, does Parent() exist?
5. **Is `super(...)` placed at the start of the body as required by Java 17?**
6. **Are you using `this(...)`?** Do not also use an explicit `super(...)` in the same delegating body.
7. **Do arguments to `super(...)` depend on uninitialized Child instance state?** Avoid this.
8. **Does the Parent constructor validate and possibly throw an exception?** The Child body runs only if the chain succeeds.
9. **Is an overridable method called from the superclass constructor?** Avoid using Child state that is not ready yet.
10. **Does Child actually override the method?** Use `@Override` so the compiler verifies it.
11. **Does the override need superclass behavior?** Call `super.method()` according to the contract, not mechanically.
12. **Is there accidental recursion from calling `this.method()` inside an override?** Check the call path.
13. **Does `super.method()` call a deeper virtual hook?** Do not assume the Base body is completely non-polymorphic.
14. **Is `super.field` masking field hiding?** Revisit representation/invariants.
15. **Is the Parent member accessible?** `super` does not bypass private/protected/package/module restrictions.
16. **Are there conflicting default methods from interfaces?** Use `InterfaceName.super.method()` when valid.
17. **Is it a static member?** Call it through the class name to avoid confusing it with dynamic dispatch.
18. **Is the class a record/enum/sealed/final type?** Respect its specific extension/construction rules.
19. **Are there checked exceptions from the super-call?** Handle them according to the constructor/method signature.
20. **If inheritance is growing complex, would composition be clearer?** Consider this before adding another subclass.

## Conclusion

`super` is a core tool of Java class inheritance, but you must distinguish between its **two completely different roles**:

- **`super(arguments)`**: invokes a direct superclass constructor to initialize the superclass state portion of **the same subclass object**. In Java 17, an explicit constructor invocation has a mandatory position and cannot be used to bypass constructor/access/initialization rules.
- **`super.member` / `super.method()`**: accesses a superclass member or invokes the appropriate superclass implementation, commonly useful when a subclass wants to **extend an overridden method** or needs to distinguish a hidden field.

A `super.method()` call does not create a new parent object, nor does it **lock down all virtual dispatch** in methods that the superclass implementation subsequently calls. `super` cannot arbitrarily access private members, cannot call an abstract method with no body, cannot run in a static context as a receiver instance, and does not replace the `InterfaceName.super.method()` syntax reserved for default methods.

When using `super`, focus on **the subtype contract, initialization responsibilities, visibility, lifecycle ordering, and overriding correctness**. If the logic to be reused is merely an independent collaborator, **composition** is usually more appropriate than introducing another subclass just to be able to call `super`.
