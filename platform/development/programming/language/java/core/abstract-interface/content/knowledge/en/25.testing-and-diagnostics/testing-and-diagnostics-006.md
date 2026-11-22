# Diagnosing Unimplemented Method and Incorrect Access Scope Errors in Java

When a class implements an interface or extends an abstract class, the compiler checks whether that class fully satisfies the method contract. Two common error categories are **unimplemented abstract methods** and **overriding a method with too narrow an access scope**. An effective diagnostic approach is to identify which method is missing, match the method signature, check the access level, and recompile after each fix.

## 1. What Is an Unimplemented Method Error?

An interface can declare methods that implementing classes must provide. For example:

~~~java
interface Printer {
    void print(String message);
}
~~~

A concrete class implementing Printer must provide the print method with the exact name, parameter types, and a compatible return type. If the class does not have a matching method, Java typically reports an error like:

~~~text
PrinterImpl is not abstract and does not override abstract method print(String) in Printer
~~~

The exact class name and message text depend on the source code, but the meaning is that the PrinterImpl class is declared as a concrete class while it still has an abstract method that needs to be implemented.

There are two valid ways to handle this:

- **Implement the missing method** if the class is designed to be instantiated and perform that behavior.
- **Declare the class as abstract** if the class is only a base class that cannot yet complete all behavior and expects subclasses to implement the rest.

For example, an abstract class can leave a method unimplemented:

~~~java
abstract class BasePrinter implements Printer {
    // print(String) is not yet implemented, so the class must be abstract.
}
~~~

A concrete class extending BasePrinter must still implement print(String), unless that subclass itself is also declared abstract.

## 2. Check the Method Signature Before Adding Code

Having the same method name is not enough to create an override. You must compare at least the name, parameter type list, return type, and inheritance relationship. For inherited methods, also check generics, parameter types, compatible return types, and Java's exception rules.

The example below **intentionally does not compile**:

~~~java
interface Printer {
    void print(String message);
}

class ConsolePrinter implements Printer {
    public void print() {
        System.out.println("Hello");
    }
}
~~~

ConsolePrinter defines print() with no parameters. This is a different method and does not implement Printer's print(String). Therefore, the class is still missing the required method.

The fix is to use the exact signature:

~~~java
interface Printer {
    void print(String message);
}

class ConsolePrinter implements Printer {
    @Override
    public void print(String message) {
        System.out.println(message);
    }
}
~~~

**@Override** helps the compiler verify the intent to override. If you accidentally misspell the name or get the parameters wrong, the compiler will report that the method does not override or implement a method from a supertype. This is a helpful signal for catching errors early.

### Distinguishing Override and Overload

- **Override**: a subclass provides a new implementation for an inherited method with a compatible signature.
- **Overload**: the same name but with a different parameter list. An overload does not replace a missing abstract method.

For example, print() and print(String) are two different overloads. If the interface requires print(String), having only print() is not enough.

## 3. Why Does an Incorrect Access Scope Cause an Error?

Java does not allow an overriding method to become less accessible than the overridden method. This rule ensures that code calling through the supertype can still invoke the method when the object is substituted with an instance of a subclass.

Consider the interface:

~~~java
interface Sender {
    void send(String message);
}
~~~

Regular methods declared in an interface without a body are implicitly public abstract. Therefore, the implementing method must be public.

The snippet below **intentionally does not compile**:

~~~java
class EmailSender implements Sender {
    @Override
    void send(String message) {
        System.out.println(message);
    }
}
~~~

The send method omits public, so its default access level is only package-private. This reduces accessibility compared to the interface's public send(String). The compiler typically produces a message similar to:

~~~text
attempting to assign weaker access privileges; was public
~~~

The fix:

~~~java
class EmailSender implements Sender {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}
~~~

When implementing an interface, explicitly declare implementing methods as public, even when the method body is very short.

## 4. Access Scope Rules When Overriding Regular or Abstract Classes

The access level of an overriding method can be kept the same or broadened, but it cannot be narrowed. The following table summarizes the access levels:

| Method in superclass | Minimum access level in subclass | Notes |
|---|---|---|
| public | public | Cannot be changed to protected, package-private, or private |
| protected | protected or public | Cannot be changed to package-private or private |
| package-private | package-private or broader, if actually overriding within the same package | The package relationship affects whether the method is inherited and overridden |
| private | Not overridden in the polymorphic sense | Private methods are not inherited by subclasses; a method with the same name in a subclass is a separate method |

The following example **intentionally does not compile** because the subclass narrows protected to private:

~~~java
abstract class BaseTask {
    protected abstract void execute();
}

class ReportTask extends BaseTask {
    @Override
    private void execute() {
        System.out.println("Generate report");
    }
}
~~~

The fix is to keep protected or broaden it to public:

~~~java
abstract class BaseTask {
    protected abstract void execute();
}

class ReportTask extends BaseTask {
    @Override
    protected void execute() {
        System.out.println("Generate report");
    }
}
~~~

Also keep in mind that a private method cannot be an abstract method because subclasses cannot override it. An abstract method also cannot simultaneously be static or final: static belongs to the class, final forbids overriding, whereas abstract requires subclasses to provide an implementation.

## 5. Complete Runnable Example

This example combines an interface, an abstract class, and a concrete class. BaseChannel implements the interface's public send method and requires subclasses to provide the format method with protected access. EmailChannel completes the missing method with the exact signature and access level.

Save the code to the file **AccessDiagnosticsDemo.java**:

~~~java
interface NotificationChannel {
    void send(String message);
}

abstract class BaseChannel implements NotificationChannel {
    protected abstract String format(String message);

    @Override
    public final void send(String message) {
        System.out.println(format(message));
    }
}

final class EmailChannel extends BaseChannel {
    @Override
    protected String format(String message) {
        return "[email] " + message.trim();
    }
}

public class AccessDiagnosticsDemo {
    public static void main(String[] args) {
        NotificationChannel channel = new EmailChannel();
        channel.send("  Xin chào  ");
    }
}
~~~

Compile and run using JDK 17 or later:

~~~text
javac AccessDiagnosticsDemo.java
java AccessDiagnosticsDemo
~~~

Exact stdout output:

~~~text
[email] Xin chào
~~~

What makes this example valid?

1. NotificationChannel requires a public send(String). BaseChannel provides a public send method, so it implements the interface contract.
2. BaseChannel declares format(String) as protected abstract. Because BaseChannel is abstract, it can leave this method for subclasses to implement.
3. EmailChannel implements format(String) with protected, matching the access level in the superclass.
4. EmailChannel is a concrete class and has provided implementations for all remaining abstract methods.
5. The channel variable has type NotificationChannel, while the actual object is an EmailChannel. Calling send still works thanks to polymorphism; the calling code does not need to know the concrete implementing class.

## 6. Diagnostic Workflow When javac Reports Errors

When encountering errors in a large project, follow this sequence to avoid fixing the wrong place:

1. **Read the class and method names in the message.** Find the class reported as not abstract and does not override abstract method, then locate the interface or superclass that declares that method.
2. **Check whether the class is concrete.** If the class needs to be instantiated, it must implement all abstract methods. If the class is only an incomplete base, consider declaring it abstract.
3. **Match the signature.** Compare the name, parameter types and order, and return type; check generics or imports if two types have the same name but belong to different packages.
4. **Add @Override.** Place the annotation directly above the method intended to override so the compiler checks that intent.
5. **Check the access scope.** Public methods of an interface must be implemented as public. A protected method in a superclass cannot be narrowed to private or package-private.
6. **Check other override constraints.** The return type must be compatible; it cannot throw additional checked exceptions broader than the rules permit; final methods cannot be overridden. If the parent method is private or static, verify whether this is actually an override or just a separate/hiding method.
7. **Recompile and read the first relevant error.** One signature error can trigger multiple cascading messages. Fixing the root cause and recompiling reduces noise.

Command to compile a standalone file:

~~~text
javac AccessDiagnosticsDemo.java
~~~

If the project has multiple packages or external dependencies, use the project's standard build command so the compiler receives the correct classpath and source path. A “cannot find symbol” error caused by a missing classpath is not the same as an unimplemented method error, so classify the error message before editing code.

## 7. Common Mistakes

- **Omitting public when implementing an interface.** Methods in an interface are public by default if declared as regular methods without a body. The implementing class must keep the public level.
- **Assuming the same method name is enough.** A different parameter list usually creates an overload, not an override.
- **Declaring a concrete class while leaving abstract methods.** Change the class to abstract if that is the intent; otherwise, complete the missing methods.
- **Reducing protected to private in a subclass.** Doing so violates the access contract of the overridden method.
- **Removing @Override to make the error disappear.** Removing the annotation does not fix the signature or access scope; the method may still fail to satisfy the contract and the compiler will continue reporting other errors.
- **Editing the method in the wrong class.** If an abstract superclass has left the method for a subclass to implement, find the exact concrete class reported in the error.
- **Confusing private with protected.** Private is only accessible within the declaring class itself; protected allows access within the package and according to inheritance rules. They cannot be substituted for each other arbitrarily when overriding.

## 8. How to Remember

An unimplemented method error means a concrete class has not yet satisfied the inheritance contract. An incorrect access scope error means an overriding method narrows access privileges compared to the parent method. Using @Override, matching the signature, checking whether the class should be abstract, and preserving the access level will resolve most cases.

When reading a javac message, identify the failing class, locate the original abstract method, compare the signature, and then check the access level. Fix the actual root cause and rerun the compiler to confirm the class fully fulfills the contract.
