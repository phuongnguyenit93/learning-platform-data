# Common Misconceptions About Abstract Classes and Interfaces in Java, and How to Verify Them

When learning Java, many object-oriented design mistakes stem from incompletely remembered rules: assuming that an abstract class has no method bodies, that an interface contains only abstract methods, or that a class can create an object directly from any reference type. A reliable way to learn is to distinguish between **language rules**, **runtime behavior**, and **design conventions**, and then verify each one with the compiler or a small program.

This article focuses on **abstract class**, **interface**, inheritance, implementation, **default** methods, **static** methods, and polymorphism.

## 1. Misconception: An abstract class cannot have constructors or implemented methods

**Reality:** An abstract class can have fields, constructors, concrete methods, and abstract methods. What prevents the class from being instantiated directly is the abstract declaration, not that every method lacks a body.

The constructor of an abstract class runs when a subclass is instantiated. It typically sets up shared state and enforces the invariants of the superclass portion. Concrete methods can contain shared logic, while abstract methods leave the differing parts for subclasses to provide.

~~~java
abstract class BaseDocument {
    private final String title;

    protected BaseDocument(String title) {
        this.title = title;
    }

    public String title() {
        return title;
    }

    public abstract int pageCount();
}
~~~

This is an illustrative snippet, not a standalone program. BaseDocument has a constructor and a concrete method title(), while requiring subclasses to provide pageCount().

A concrete subclass must implement the missing abstract method:

~~~java
final class ShortDocument extends BaseDocument {
    ShortDocument(String title) {
        super(title);
    }

    @Override
    public int pageCount() {
        return 1;
    }
}
~~~

If ShortDocument does not implement pageCount(), the class must be declared abstract or the compiler will report an error. The @Override annotation helps the compiler confirm that the method actually overrides or implements an inherited method.

## 2. Misconception: Variables cannot be declared with an abstract class or interface type

**Reality:** You cannot create an object directly with new for an interface or an abstract class, but you can declare variables, parameters, return types, and fields with those types. A reference variable can point to an object of a compatible concrete class.

~~~java
// Invalid: cannot be instantiated directly
// BaseDocument document = new BaseDocument("Draft");

// Valid if ShortDocument is a concrete class:
BaseDocument document = new ShortDocument("Draft");
~~~

The valid line illustrates polymorphism: the declared type of the variable is BaseDocument, while the actual type of the object is ShortDocument. When an overridden instance method is called, Java selects the implementation based on the actual type of the object at runtime.

You should not conclude that a variable with an interface type can only point to an interface. An interface is a reference type; the actual object must be an instance of a concrete class that implements that interface.

## 3. Misconception: Interfaces only have abstract methods

**Reality:** An interface can declare abstract, default, static, and private methods (private methods in interfaces have been available since Java 9). These forms serve different purposes:

- An abstract method describes behavior that an implementing class must provide.
- A default method has a body, providing default behavior that an implementing class can keep as is or override.
- A static method belongs to the interface itself and is called using the interface name.
- A private method supports sharing logic between methods with bodies inside the interface; it is not a contract that an implementing class overrides.

Example:

~~~java
interface Auditable {
    String actor();

    default String auditLine() {
        return "actor=" + actor();
    }

    static String formatName() {
        return "audit";
    }

    private String normalize(String value) {
        return value.trim();
    }
}
~~~

The snippet above illustrates the method forms, though normalize is not currently called. In real code, a private method can be used inside a method with a body, such as a default method, to share logic. A private method in an interface cannot be called directly by implementing classes as part of the API and cannot be overridden.

Fields declared in an interface also have their own rules: they are implicitly public static final. Therefore, interfaces are generally not used to store per-object instance state. If each object needs mutable data, place that data in an implementing class or an appropriate base class.

## 4. Misconception: Default methods are always used without needing to worry about conflicts

**Reality:** Default methods allow an interface to add default behavior, but Java has resolution rules when multiple sources provide methods with the same signature.

1. A matching instance method defined in a class usually takes precedence over a default method from an interface.
2. If a subinterface extends a superinterface and overrides a default method, the definition in the subinterface is more specific.
3. If a class inherits two conflicting default methods from two independent interfaces, the class usually must override the method to resolve the conflict.

The following example **intentionally does not compile** because CombinedLogger inherits two default methods with the same signature without choosing how to handle them:

~~~java
interface ConsoleLog {
    default String channel() {
        return "console";
    }
}

interface FileLog {
    default String channel() {
        return "file";
    }
}

// Intentionally incorrect: does not resolve the channel() conflict
class CombinedLogger implements ConsoleLog, FileLog {
}
~~~

The fix is to override explicitly:

~~~java
class CombinedLogger implements ConsoleLog, FileLog {
    @Override
    public String channel() {
        return ConsoleLog.super.channel() + "+" + FileLog.super.channel();
    }
}
~~~

The ConsoleLog.super.channel() syntax allows calling the specific default implementation from that interface. Use it only when you genuinely want to reuse the corresponding default logic.

## 5. Misconception: Interface static methods are inherited like instance methods

**Reality:** An interface's static method is called using the interface name. It is not inherited like a regular instance method of an implementing class.

~~~java
interface Identifier {
    static String kind() {
        return "identifier";
    }
}

class UserId implements Identifier {
}
~~~

The valid call is Identifier.kind(). Calling UserId.kind() or new UserId().kind() is not a valid way to invoke a static method declared only in the Identifier interface. Clearly distinguish static methods from default methods: default methods are called on an object and can be overridden; static methods are called on the declaring type and do not participate in polymorphic instance dispatch.

## 6. Misconception: An interface can implement another interface using implements

**Reality:** A class uses implements to implement an interface. An interface extends one or more other interfaces using extends. A class can directly extend only one class, but can implement multiple interfaces.

~~~java
interface HasId {
    String id();
}

interface HasLabel extends HasId {
    String label();
}

abstract class EntityBase {
    public abstract String type();
}

final class UserEntity extends EntityBase implements HasLabel {
    @Override
    public String id() {
        return "u-17";
    }

    @Override
    public String label() {
        return "User";
    }

    @Override
    public String type() {
        return "account";
    }
}
~~~

HasLabel inherits the id() contract from HasId, so UserEntity must implement both id() and label(). In addition, UserEntity also implements type() inherited from the abstract class EntityBase. Therefore, when checking a concrete class, examine all remaining abstract methods from both the superclass and the interfaces.

## 7. Complete Example: Verifying with the Compiler and at Runtime

The example below shows an abstract class with a constructor and concrete methods; a subclass completing the abstract method; a reference type that is an interface; a default method that can be overridden; and an interface static method called using the interface name.

Save the entire code to the file **AbstractInterfaceChecks.java**:

~~~java
interface Describable {
    String describe();

    default String source() {
        return "interface default";
    }

    static String contract() {
        return "Describable";
    }
}

abstract class BaseReport implements Describable {
    private final String title;

    protected BaseReport(String title) {
        this.title = title;
        System.out.println("BaseReport constructor: " + title);
    }

    @Override
    public String describe() {
        return "Report: " + title;
    }

    protected abstract int itemCount();

    public final int itemCountForDisplay() {
        return itemCount();
    }
}

final class SalesReport extends BaseReport {
    SalesReport(String title) {
        super(title);
    }

    @Override
    public String source() {
        return "SalesReport override";
    }

    @Override
    protected int itemCount() {
        return 3;
    }
}

public class AbstractInterfaceChecks {
    public static void main(String[] args) {
        Describable value = new SalesReport("Q3");

        System.out.println(value.describe());
        System.out.println(value.source());
        System.out.println(Describable.contract());
        System.out.println(value instanceof Describable);
        System.out.println(((BaseReport) value).itemCountForDisplay());
    }
}
~~~

Compile and run using JDK 17 or later:

~~~text
javac AbstractInterfaceChecks.java
java AbstractInterfaceChecks
~~~

Exact stdout output:

~~~text
BaseReport constructor: Q3
Report: Q3
SalesReport override
Describable
true
3
~~~

How to read the output:

- The first line confirms that the abstract class constructor runs when creating SalesReport.
- describe() uses the shared implementation in BaseReport, even though the value variable has type Describable.
- source() calls SalesReport's override, instead of the default body in the interface.
- Describable.contract() is called through the interface name because it is a static method.
- instanceof returns true because the actual object is SalesReport, which implements Describable through its superclass.
- itemCountForDisplay() is a public concrete method that calls the abstract method itemCount() completed by SalesReport.

## 8. How to Verify Each Misconception

You do not need to just rely on the explanation. Design a small test for each rule:

| What to Check | Test | Expected Result |
|---|---|---|
| Can an abstract class be instantiated directly? | Try instantiating BaseReport in the example code | The compiler rejects it because the class is abstract |
| Can a concrete class omit an abstract method? | Remove itemCount() from SalesReport while keeping the class concrete | The compiler reports that the abstract method is not implemented |
| Can a default method be overridden? | Call source() before and after adding the override | The output changes from interface default to SalesReport override |
| How is an interface static method called? | Call Describable.contract() | Returns Describable |
| Does the reference type determine the instance method implementation? | Keep Describable value, change the actual class to another class that overrides describe() | The call uses the actual object's implementation |
| If two default methods share the same signature, is one automatically chosen? | Implement two interfaces with the same default method without overriding it | The compiler reports a conflict |

Tests that intentionally cause errors should be run one case at a time, because one compilation error can prevent the remaining parts from being checked. After each change, recompile and read the new message.

## 9. Error-Reading and Verification Workflow in a Project

1. Read the compiler message and identify the relevant file, line, class, and method.
2. Locate the original declaration in the interface or superclass, then compare the signature and access level.
3. Check whether the class is abstract or concrete. A concrete class must complete all remaining abstract methods.
4. Add @Override to methods intended to override so that the compiler catches incorrect names or parameters.
5. Check for conflicts between default methods, differences between static and instance methods, and access rules.
6. Re-run the project's standard build command. If the project has multiple modules, use the build tool to ensure the classpath and source path are correct; a missing dependency error does not mean an interface design error.

Do not remove @Override just to make an error message disappear. The annotation helps detect contract errors; removing it can hide an incorrect intent without fixing the cause.

## 10. Misconceptions to Avoid

- **“An abstract class has no logic.”** False: an abstract class can provide state, constructors, and shared logic.
- **“An abstract class cannot be used as a variable type.”** False: it can be used as a reference type; it just cannot be instantiated directly.
- **“An interface only has abstract methods.”** False: modern interfaces can have default, static, and private methods.
- **“A default method cannot be overridden.”** False: an implementing class can provide its own implementation.
- **“An interface static method is an inherited instance method.”** False: it is called using the interface name, not through polymorphic instance dispatch.
- **“A class implementing a subinterface only needs to implement the methods declared directly in the subinterface.”** False: contracts can be inherited from superinterfaces and abstract classes.
- **“The compiler only checks syntax.”** False: the compiler also checks types, method contracts, access scope, and many other language rules.

## 11. How to Remember

An abstract class is well suited for sharing state and behavior among classes in an inheritance relationship; an interface describes a contract that multiple types can fulfill. Both support polymorphism, but they have different rules regarding constructors, state, default methods, and how types are combined.

When encountering a claim about Java, turn it into a verifiable question: does this code compile, which method is called at runtime, or what value is printed? A small example, a prediction before running, and the actual result are a good way to distinguish language rules from guesswork.
