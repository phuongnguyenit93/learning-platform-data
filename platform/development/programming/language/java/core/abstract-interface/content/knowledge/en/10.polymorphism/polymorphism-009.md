# Why Field Access and Static Methods Are Not Polymorphic in Java

## 1. Objectives and the Problem to Understand

In Java, a variable declared with a parent class type can certainly reference an object of a subclass:

~~~java
Parent ref = new Child();
~~~

However, the results of the following three expressions do not necessarily all belong to `Child`:

~~~java
ref.name;             // Field access.
ref.describe();       // Call an overridable instance method.
ref.version();        // Call a static method via a variable (valid, but should not be written).
~~~

Key points:

- **Fields are selected by the expression's compile-time type.** A field in a subclass can *hide* a same-named field in the parent class, but it cannot override a field.
- **`static` methods are not overridden either.** If a subclass declares a corresponding `static` method, that is *method hiding*. `static` methods are resolved by the type or class name at compile time.
- **Instance methods can be overridden** and are selected based on the actual class of the object at runtime (runtime dispatch), when the call satisfies Java's rules.
- **Interface `default` methods** are also instance methods and can participate in overriding, whereas **interface `static` methods** belong to the interface itself.

The goal is not merely to memorize the printed output, but to understand whether each expression needs the **declared type**, the **actual class**, or **both** for Java to select the right member.

## 2. Runtime Polymorphism Applies to Overridden Instance Methods

Polymorphism (runtime polymorphism) in the context of inheritance is typically observed when an instance method call is selected based on the actual class of the object.

Example:

~~~java
abstract class Shape {
    abstract String draw();
}

class Circle extends Shape {
    @Override
    String draw() {
        return "Circle";
    }
}
~~~

When writing `Shape shape = new Circle();` and then calling `shape.draw()`, the compiler verifies that the `Shape` type has a matching `draw()` method. At runtime, the actual object is a `Circle`, so the `Circle.draw()` implementation is selected.

Thus, for an instance method call with a valid override:

1. **Compile time:** Java checks which methods can be called according to the static type of the reference expression and selects the appropriate signature.
2. **Runtime:** Java finds the instance implementation matching the actual object for the selected signature.
3. **Result:** Changing the actual object class (within an overriding hierarchy) can change behavior without changing the variable type on the caller side.

This mechanism differs fundamentally from field access and static method calls. The JVM may optimize dynamic calls once it has proved the call target, but the **Java semantics** remain polymorphic at the language level.

## 3. Complete Example: Three Ways of Accessing on the Same Object

Save the entire code below into the file **`DispatchDemo.java`**:

~~~java
class Parent {
    public String name = "parent-field";

    public static String version() {
        return "parent-static";
    }

    public String describe() {
        return "parent-instance";
    }
}

class Child extends Parent {
    public String name = "child-field";

    public static String version() {
        return "child-static";
    }

    @Override
    public String describe() {
        return "child-instance";
    }
}

public class DispatchDemo {
    public static void main(String[] args) {
        Parent asParent = new Child();
        Child asChild = (Child) asParent;

        System.out.println(asParent.name);
        System.out.println(asChild.name);

        System.out.println(Parent.version());
        System.out.println(Child.version());

        // To illustrate the difference: Java allows calling static methods through a reference.
        System.out.println(asParent.version());
        System.out.println(asChild.version());

        System.out.println(asParent.describe());
        System.out.println(asChild.describe());

        System.out.println(((Parent) asChild).name);
        System.out.println(((Child) asParent).name);
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 DispatchDemo.java
java DispatchDemo
~~~

Exact output:

~~~text
parent-field
child-field
parent-static
child-static
parent-static
child-static
child-instance
child-instance
parent-field
child-field
~~~

**Step-by-step explanation:**

- `asParent.name` → `parent-field`: the variable `asParent` has the declared type `Parent`, so it accesses `Parent.name`.
- `asChild.name` → `child-field`: the reference expression has the type `Child`, so it accesses `Child.name`.
- `Parent.version()` and `Child.version()` select the `static` method on the named class.
- `asParent.version()` → `parent-static` even though the actual object is `Child`. Java allows this syntax, but binds the call to `Parent.version()` based on the static type of the variable.
- `asChild.version()` → `child-static` because the static type of the expression is `Child`. You should write `Parent.version()` or `Child.version()` directly to make the intent clear.
- Both `asParent.describe()` and `asChild.describe()` → `child-instance`: `describe()` is an instance method overridden by `Child`, and both variables point to the same `Child` object.
- The last two casts **do not create new objects**; they only change the static type of the expression used for field lookup, and therefore produce different results.

The example demonstrates: **changing the static type of a variable or expression can change the selected field or static method, but does not by itself change the actual class of the object or the behavior of overridden instance methods.**

## 4. Field Hiding: Same Name Does Not Mean the Same Field

When `Child` declares `name` with the same name as `Parent.name`, the new field **hides the name** of the inherited field in the appropriate lookup contexts. The two declarations remain **two distinct fields**, with no overriding relationship.

For instance fields, a `Child` object can contain the state defined by `Parent` *and* the state defined by `Child`. Consequently, the values of the two fields can differ.

Standalone runnable example in the file **`HiddenFieldDemo.java`**:

~~~java
class BaseRecord {
    protected String code = "BASE";
}

class DetailedRecord extends BaseRecord {
    protected String code = "CHILD";

    void changeBoth() {
        super.code = "BASE-UPDATED";
        this.code = "CHILD-UPDATED";
    }

    void printFields() {
        System.out.println(super.code);
        System.out.println(this.code);
    }
}

public class HiddenFieldDemo {
    public static void main(String[] args) {
        DetailedRecord record = new DetailedRecord();
        record.changeBoth();
        record.printFields();

        BaseRecord baseView = record;
        System.out.println(baseView.code);
        System.out.println(record.code);
    }
}
~~~

~~~bash
javac --release 17 HiddenFieldDemo.java
java HiddenFieldDemo
~~~

~~~text
BASE-UPDATED
CHILD-UPDATED
BASE-UPDATED
CHILD-UPDATED
~~~

`super.code` accesses the field of `BaseRecord`, whereas `this.code` accesses the field of `DetailedRecord`. The variable `baseView` still points to the same `record` object, but `baseView.code` reads the field of `BaseRecord` because the static type of `baseView` is `BaseRecord`.

**Distinguishing two commonly encountered terms:**

- *Field hiding*: a subclass declares a field with the same name as an inherited field. Whether the field is instance or static, field access still does not use runtime overriding.
- *Variable shadowing*: a local variable or parameter can shadow a field name within a scope; for example, in a constructor with a parameter `code`, `this.code = code` is needed. Scope-based shadowing is not runtime polymorphism either.

To avoid confusion and maintenance bugs, you should not design two fields with the same name across inheritance levels merely to represent "variants" of the same property.

## 5. Why Are `static` Methods Not Dispatched by Object Either?

A `static` method belongs to **the class or interface where it is declared**, rather than being tied to a specific instance. Therefore, Java can determine the target method from the class being called or the static type of the expression, without needing to inspect the runtime class of the object.

~~~java
class Server {
    static String kind() {
        return "server";
    }
}

class WebServer extends Server {
    static String kind() {
        return "web-server";
    }
}
~~~

The two `kind()` declarations form a **method hiding** relationship, not an overriding relationship. In another program:

~~~java
Server service = new WebServer();
System.out.println(Server.kind());    // server
System.out.println(WebServer.kind()); // web-server
System.out.println(service.kind());   // server; syntax to avoid
~~~

The line `service.kind()` does not select `WebServer.kind()` based on the `WebServer` object. The proper, readable form that does not create a false impression of polymorphism is **`Server.kind()`** when you want the behavior in `Server`, or **`WebServer.kind()`** when you want the behavior in `WebServer`.

At the bytecode level, static calls typically use the `invokestatic` instruction, whereas many instance calls may go through `invokevirtual` or `invokeinterface`. That is an implementation compatible with the semantic difference: static calls have no mechanism to select an overriding method based on the receiver like instance calls do. You should not equate every form of instance method call with polymorphism: constructors, `private` methods, and `final` methods have their own rules; the essential point is whether a method **is validly overridden** or not.

### `static` Methods Cannot Be Overridden by Instance Methods

The following snippets are **intentionally invalid code that does not compile**:

~~~java
class A {
    static void go() {}
}

class B extends A {
    // void go() {}       // Error: an instance method cannot override a static method.
    // @Override
    // static void go() {} // Error: @Override does not apply to static methods.
}
~~~

Similarly, if `A.go()` is an instance method, a subclass cannot declare `static void go()` with the same signature to "replace" it. For valid static hiding, Java still enforces constraints on signature, access level, and compatible return type; a parent class static method declared `final` cannot be hidden with the same signature in a subclass.

Using `@Override` is a very helpful check: this annotation is valid for an overriding method, but the compiler will reject it if you try to attach it to static method hiding.

## 6. Decision Table: What Information Does Java Rely On?

| Expression / Declaration | Mechanism | Factor Determining the Selected Member |
| --- | --- | --- |
| `parentRef.field` | Field lookup / field hiding | Static type of `parentRef`, name lookup rules, and access checks |
| `Child.field` for a static field | Static field lookup | The named class |
| `parentRef.staticMethod()` | Static method hiding | Static type of the expression; syntax via a reference should not be used |
| `Child.staticMethod()` | Static call by class name | The named class |
| `parentRef.instanceMethod()` with override | Runtime dispatch after signature resolution | Actual class of the receiver and the corresponding overriding implementation |
| `InterfaceName.staticMethod()` | Static interface method call | The interface itself that declares the method |
| `parentRef.defaultMethod()` of an interface | Instance method / overridable | Matching runtime implementation and method precedence/resolution rules |
| `Parent.CONSTANT` of an interface or class | Static field access | Type name; not polymorphic |

A practical rule: **When you need behavior that varies by object type, represent that behavior as an instance method of a parent class or interface contract.** Do not expect a field or static method to switch targets based on the subclass of the object.

## 7. Looking Through an Interface: How Do Fields, static, default, and abstract Methods Differ?

With interfaces, the distinction is even clearer:

- Every **field declared in an interface** is implicitly `public static final`. There are no instance fields in an interface.
- **Static methods of an interface** belong to the interface; they are not inherited like an instance method by an `implements` class or a subinterface. They must be called using **the name of the interface that declares them**.
- **Abstract methods of an interface** are instance contracts that must be implemented by a concrete class, unless a valid implementation already exists in the hierarchy.
- **Default methods of an interface** are also instance methods. An implementing class can override them; calls through an interface-typed reference participate in runtime dispatch.

Complete example in the file **`InterfaceDispatchDemo.java`**:

~~~java
interface Processor {
    String CATEGORY = "processor-field";

    static String family() {
        return "interface-static";
    }

    String process();

    default String description() {
        return "default:" + process();
    }
}

final class TextProcessor implements Processor {
    @Override
    public String process() {
        return "text";
    }

    @Override
    public String description() {
        return "custom:" + process();
    }

    // Independent static declaration of the class; does not override the interface's static method.
    public static String family() {
        return "class-static";
    }
}

public class InterfaceDispatchDemo {
    public static void main(String[] args) {
        Processor processor = new TextProcessor();

        System.out.println(Processor.CATEGORY);
        System.out.println(Processor.family());
        System.out.println(TextProcessor.family());
        System.out.println(processor.process());
        System.out.println(processor.description());
    }
}
~~~

~~~bash
javac --release 17 InterfaceDispatchDemo.java
java InterfaceDispatchDemo
~~~

~~~text
processor-field
interface-static
class-static
text
custom:text
~~~

**Analysis:**

1. `Processor.CATEGORY` is a `public static final` field, not tied to a `TextProcessor` object.
2. `Processor.family()` always invokes the static method of `Processor`.
3. `TextProcessor.family()` invokes the static method declared by `TextProcessor` itself. Because interface static methods **are not inherited** by implementing classes, these two methods do not form an overriding relationship.
4. `processor.process()` is an instance method call through the interface type, dispatched to `TextProcessor.process()`.
5. `processor.description()` is also an instance method call; although `Processor` provides a `default` implementation, `TextProcessor` overrides it, so the output is `custom:text`.

If the class does not override `description()`, the call will use the `default` implementation in the interface (unless a superclass has an instance implementation that takes precedence, or there is a conflict that must be resolved according to Java's rules).

**Invalid syntax to avoid:**

~~~java
// Processor processor = new TextProcessor();
// processor.family(); // Compile error: Processor's static method cannot be called through an instance.
// TextProcessor does not have family() unless it declares this method itself.
// interface ChildProcessor extends Processor {}
// ChildProcessor.family(); // Error: static methods in Processor are not inherited by subinterfaces.
~~~

Unlike **class** static methods, **interface** static methods are designed to be called through the interface name; do not use syntax like `processor.family()` as a test for polymorphism.

## 8. Getter Methods Can Be Polymorphic, Whereas the Fields They Read Cannot

Sometimes we want subclasses to expose "different values" under the same contract. Declaring fields with the same name and accessing them directly through a parent class variable will not achieve that goal. You can declare an **instance method** and override it.

File **`PolymorphicValueDemo.java`**:

~~~java
abstract class Shipping {
    public abstract int baseFee();

    public final int totalFee(int surcharge) {
        return baseFee() + surcharge;
    }
}

final class StandardShipping extends Shipping {
    @Override
    public int baseFee() {
        return 20;
    }
}

final class ExpressShipping extends Shipping {
    @Override
    public int baseFee() {
        return 50;
    }
}

public class PolymorphicValueDemo {
    public static void main(String[] args) {
        Shipping standard = new StandardShipping();
        Shipping express = new ExpressShipping();

        System.out.println(standard.baseFee());
        System.out.println(express.baseFee());
        System.out.println(standard.totalFee(5));
        System.out.println(express.totalFee(5));
    }
}
~~~

~~~bash
javac --release 17 PolymorphicValueDemo.java
java PolymorphicValueDemo
~~~

~~~text
20
50
25
55
~~~

`Shipping.baseFee()` is an abstract instance method, so each subclass provides its own behavior. `totalFee()` is declared `final`: it cannot be overridden, yet **the `baseFee()` call inside it is still polymorphic**, and the result depends on the object receiving the `totalFee()` call.

This is a subtle point: a method that is not overridden can **call another method that is overridden**, so the overall result still depends on the actual object class. There is no need to use field hiding to solve this requirement.

## 9. Do Not Confuse Compile-Time Overload Resolution with Runtime Override Selection

Overloads are selected based on the static types of the receiver and arguments; afterward, if the chosen signature is an overridable instance method, the runtime selects the implementation based on the actual receiver. The article **Compile-Time Overload Selection and Runtime Override Selection** presents examples combining both steps along with cases of boxing, varargs, ambiguous `null`, and generic erasure.

## 10. Easily Confused Scenarios

### 10.1. Casting a Reference Does Not Change the Object

~~~java
Parent one = new Child();
Child two = (Child) one;
~~~

In the `DispatchDemo` example, both variables point to the same `Child` instance. `one.name` and `two.name` differ because field lookup uses the static type; `one.describe()` and `two.describe()` both run `Child.describe()`. Casting **does not discard the object's state** and does not construct a new parent-class object.

### 10.2. Do `static` and `final` Mean the Same Thing?

No:

- `static` defines a member that belongs to the class or interface, rather than to each instance.
- `final` has different meanings depending on where it appears: a field cannot be reassigned after initialization, a method cannot be overridden/hidden when Java's rules forbid it, and a class cannot be subclassed.
- A **`static final`** field is accessed via the class just like other static fields; `final` itself does not make a field polymorphic.
- A **`final` instance method** cannot be overridden by a subclass, but not because it "becomes static." It is still a method on the object and can use instance state or call other instance methods.

### 10.3. Can a `private` Field Be "Overridden"?

No. Fields are not overridden at any access level. A `private` field in a parent class is not inherited in a way that can be accessed directly from a subclass. A subclass can declare its own field with the same name; the two fields are still two separate storage locations. Good design typically keeps fields `private` and provides an appropriate instance API if polymorphic behavior is needed.

### 10.4. Can a Static Method Read an Object's State?

Yes, if the object is passed in as a parameter or a valid object reference is obtained by other means. However, the method is still selected **statically** based on the type at the call site. For example, `Math.max(a, b)` is a static method operating on arguments; computing from passed-in data does not turn it into a polymorphic method on a receiver object.

### 10.5. Are Interface Constants Polymorphic?

No. `interface Config { int TIMEOUT = 10; }` declares a `public static final` field. Using `Config.TIMEOUT` accesses the field via the interface name. For `int`/`String` constants initialized with constant expressions, the value may even be inlined by the compiler into the consumer's code. Therefore, updating a public compile-time constant sometimes requires recompiling previously compiled clients. This is another practical consequence of constant fields, unrelated to runtime polymorphism.

### 10.6. Accessing a Static Method Through a `null` Variable

For a static method declared in a class, `ref.staticMethod()` can run even when `ref` is `null`, because the call does not need a receiver instance; however, the receiver expression is still evaluated. You should call `ClassName.staticMethod()` to make the intent clear. An interface's static method must be called via the name of the interface that declares it and is not inherited by implementing classes or subinterfaces.

Calling an instance method through `null` causes a `NullPointerException`; the article **Null Objects and Calls Through Interface References** explains these cases.

## 11. Self-Check with Code

Read the snippet below:

~~~java
class A {
    String label = "A";

    static String source() {
        return "A-static";
    }

    String message() {
        return "A-method";
    }
}

class B extends A {
    String label = "B";

    static String source() {
        return "B-static";
    }

    @Override
    String message() {
        return "B-method";
    }
}
~~~

Suppose we have:

~~~java
A ref = new B();
~~~

Try answering on your own before looking at the answers:

1. What is the value of `ref.label`?
2. What is the value of `ref.source()`? Should this syntax of calling a static method through a variable be used?
3. What is the value of `ref.message()`?
4. If `ref.label` is replaced with `((B) ref).label`, does the result change? Is a new object created?
5. Can `@Override` be added above `static String source()` in `B`?
6. If `A.message()` is declared `final`, can `B` override it?

**Answers:**

1. `"A"` because the field is accessed according to the static type `A`.
2. `"A-static"` because the static method is selected according to the static type `A`; you should write `A.source()`.
3. `"B-method"` because the instance method is overridden by `B` and the actual object is `B`.
4. Yes: the result is `"B"` because the expression after the cast has the static type `B`. No new object is created by the cast.
5. No. A static method in a subclass *hides* the parent class's static method rather than overriding it; `@Override` will produce a compile error.
6. No. A `final` instance method cannot be overridden; a compile error will occur if the subclass tries to declare an override.

## 12. Design Choice Guidelines

When writing a Java library or application with multiple classes implementing the same contract:

- When you need **behavior specific to each object type**: use an abstract instance method, an interface instance method, or an appropriate default method.
- When you need **data specific to each object**: store it in instance fields (typically `private`), and access it through methods with a clear API; do not use same-named fields to simulate overriding.
- When you need **utility functions that do not depend on a receiver**: use static methods and explicitly call them with the class or interface name.
- When you need **shared constants**: use `static final` with an appropriate type and declaration location, keeping in mind that fields are not polymorphic and a `final` reference does not necessarily point to an immutable object.
- When reading an unfamiliar expression, ask: (1) is the member a field, static, or instance member? (2) what is the static type of the expression? (3) is there a valid override? (4) what is the actual class of the object? Predict the output only after classifying these properly.

## 13. Knowledge Summary

**Field access and static methods are not polymorphic because Java resolves them based on the type or class name at compile time.** Field hiding and static method hiding merely create declarations with the same name in different classes; there is no step that re-resolves the member according to the actual object's class.

**Runtime polymorphism belongs to overridable instance methods**, including interface `default` methods when validly overridden. A parent-class-typed variable can reference a subclass and invoke the subclass's instance behavior properly; however, that same variable still accesses fields and static methods according to its declared type. When you need behavior that varies by class, represent the contract with instance methods instead of relying on field hiding or static method hiding.
