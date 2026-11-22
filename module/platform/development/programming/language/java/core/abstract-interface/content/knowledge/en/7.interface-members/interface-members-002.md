# Implicitly public abstract Methods in a Java Interface

## 1. Language Rules

A method declared in an interface without a body and without modifiers for methods with a body is implicitly **public abstract**. Both keywords can be written explicitly or omitted without changing the meaning.

~~~java
interface Formatter {
    String format(String text);
}
~~~

The declaration above is equivalent to:

~~~java
interface Formatter {
    public abstract String format(String text);
}
~~~

**public** makes the method a public part of the contract. **abstract** indicates that the interface only specifies the signature, while the behavior is provided by a concrete class or by a suitable inherited implementation. A semicolon ends the declaration because there is no method body.

## 2. Why Must an Implementing Class Use public?

A concrete class implementing this contract must provide a method with a compatible signature and must not reduce its access level.

~~~java
interface Printer {
    void print(String message);
}

final class ConsolePrinter implements Printer {
    @Override
    public void print(String message) {
        System.out.println(message);
    }
}
~~~

The following example is invalid:

~~~java
class BrokenPrinter implements Printer {
    @Override
    void print(String message) {
        System.out.println(message);
    }
}
~~~

In a class, a method without an access modifier is package-private. The implicit public rule applies only to abstract methods in an interface; it does not automatically elevate the access level of a method in a class. Using protected or private cannot satisfy the public contract either.

A class declared abstract can defer some implementations. When creating a concrete class, every missing abstract method must be satisfied with a valid implementation.

## 3. Observing Modifiers with Reflection

Save the following code in the file **InterfaceAbstractDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Locale;

interface Formatter {
    String format(String text);
}

final class UppercaseFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}

public class InterfaceAbstractDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Formatter formatter = new UppercaseFormatter();
        System.out.println(formatter.format("java"));

        Method method = Formatter.class.getDeclaredMethod("format", String.class);
        System.out.println(Modifier.toString(method.getModifiers()));
        System.out.println(Modifier.isPublic(method.getModifiers()));
        System.out.println(Modifier.isAbstract(method.getModifiers()));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac InterfaceAbstractDemo.java
java InterfaceAbstractDemo
~~~

Output:

~~~text
JAVA
public abstract
true
true
~~~

Reflection confirms the actual modifiers of the method declared in the interface. The call formatter.format("java") still executes the implementation of the UppercaseFormatter object; the interface specifies the contract, while dynamic dispatch selects the override based on the actual object.

## 4. Comparison with abstract Methods in an Abstract Class

| Declaration | Access level when modifier is omitted | Where the implementation can be provided |
| --- | --- | --- |
| Abstract method in an interface | public | Concrete class or compatible inherited implementation |
| Abstract method in a class | package-private | Subclass, following the declared access level |

~~~java
interface Task {
    void execute();             // public abstract
}

abstract class BaseTask {
    abstract void execute();    // package-private abstract
}
~~~

The method in BaseTask can be overridden by a subclass in the same package while remaining package-private; if subclasses in another package need to be able to implement it, the parent class's access design must be appropriate, such as protected or public. An interface does not allow protected for its methods.

## 5. Two Cases to Understand Correctly

**Methods corresponding to Object.** A concrete class may already inherit public equals(Object), hashCode(), or toString() from Object. A suitable inherited method can satisfy the corresponding interface declaration; the class does not always need to write a separate override of its own.

**Functional interface.** default, static, and private methods with a body do not increase the number of abstract contracts that need to be implemented. Methods corresponding to public methods of Object are handled according to a separate rule when determining a functional interface.

~~~java
@FunctionalInterface
interface Validator {
    boolean isValid(String text);

    default boolean isNonEmpty(String text) {
        return text != null && isValid(text);
    }
}
~~~

A lambda can provide isValid; the default method remains available. To distinguish the types of methods with a body in detail, see the article on classifying methods in an interface.

## 6. Common Mistakes

| Mistake | Why | Fix |
| --- | --- | --- |
| Declaring a protected or private abstract method in an interface | Interface abstract methods are public | Remove the invalid modifier or design a private helper with a body starting from Java 9 |
| Omitting public when implementing in a class | The class method becomes package-private | Write public explicitly |
| Assuming all interface methods are abstract | default, static, and private methods with a body are other forms | Check both the modifiers and whether there is a body |
| Assuming different parameter names change the contract | Parameter names do not determine overriding | Compare the method name, parameters, return type, and exception rules |

### Self-Check

1. What modifiers does the declaration **void run();** in an interface have? **public abstract**.
2. Can a concrete class implementing an interface write **void run() {}**? **No**, because that is package-private.
3. Can an abstract class defer implementation? **Yes**, as long as the class remains declared abstract and the eventual concrete class completes the contract.
4. Is **default void log() {}** an abstract method? **No**, it has a body and is a public instance method.

Key takeaway: the public modifier still takes effect even if it does not appear in the source code. When implementing an interface, satisfy the public contract properly and use @Override so the compiler detects an incorrect signature.
