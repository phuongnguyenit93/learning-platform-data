# Java 9 Milestone for Private Methods in Interfaces

Java 9 added **private methods in interfaces** so interface authors can share internal logic across multiple methods without exposing those helper methods as part of the public API. This feature is especially useful when an interface has multiple default or static methods that need to perform the same normalization, validation, or formatting step.

Point to remember: **a private method in an interface is an implementation detail of the interface itself**. An implementing class cannot call it directly, does not inherit it, and does not override it polymorphically.

## 1. Why Does Java Need Private Methods in Interfaces?

Java 8 allowed interfaces to declare **default** methods with a body and **static** methods with a body. As a result, an interface could add shared behavior without forcing every implementing class to rewrite that method.

However, when multiple default methods had to share a block of processing logic, before Java 9 authors often had to choose between duplicating code or making the helper a public method in the interface. A public method could become part of the contract that users of the interface see and can call, even though it was created solely for internal use.

Java 9 allows declaring private methods inside an interface to solve this:

- Private instance methods can be called from other instance methods in the same interface, such as default methods.
- Private static methods can be called from static methods or other code within the same interface in accordance with static rules.
- Helpers are kept in internal scope, so code calling the interface cannot rely on a helper as a public API.

## 2. Version Milestones and Method Forms

| Feature | Java Version |
|---|---|
| Abstract methods in interfaces | Available since the earliest Java versions |
| Default methods with a body | Java 8 |
| Static methods in interfaces | Java 8 |
| Private methods in interfaces | Java 9 |
| Private static methods in interfaces | Java 9 |

A Java 9+ interface can declare the following method forms:

- **Abstract method:** has no body; concrete classes implement this contract.
- **Default method:** has a body and is inherited by implementing classes unless another overriding rule applies.
- **Public static method:** belongs to the interface and is called via the interface name; it is not an instance method of an object.
- **Private instance method:** a helper with a body, used inside the interface by appropriate instance methods.
- **Private static method:** a static helper with a body, used inside the interface by appropriate internal methods.

In an interface, a method without an explicit access modifier is normally public. Regular default and static methods of an interface are also implicitly public. Starting in Java 9, the private keyword allows restricting helpers to the interface.

## 3. Runnable Example for Java 9 and Later

The example below has two default methods that share private instance helpers to normalize a name and wrap a message. The public static method uses a private static helper to normalize a code.

Save the following code to the file **PrivateInterfaceMethodsDemo.java**:

~~~java
import java.util.Locale;

interface MessageFormatter {
    default String greeting(String name) {
        return decorate("Hello, " + normalizeName(name) + "!");
    }

    default String farewell(String name) {
        return decorate("Goodbye, " + normalizeName(name) + "!");
    }

    static String formatCode(String code) {
        return "CODE-" + normalizeCode(code);
    }

    private String normalizeName(String name) {
        if (name == null || name.trim().isEmpty()) {
            return "guest";
        }
        return name.trim();
    }

    private String decorate(String message) {
        return "[" + message + "]";
    }

    private static String normalizeCode(String code) {
        if (code == null) {
            throw new IllegalArgumentException("code must not be null");
        }
        return code.trim().toUpperCase(Locale.ROOT);
    }
}

public class PrivateInterfaceMethodsDemo implements MessageFormatter {
    public static void main(String[] args) {
        PrivateInterfaceMethodsDemo demo = new PrivateInterfaceMethodsDemo();

        System.out.println(demo.greeting("Linh"));
        System.out.println(demo.farewell("Linh"));
        System.out.println(demo.greeting("  "));
        System.out.println(MessageFormatter.formatCode(" ab-7 "));
    }
}
~~~

Compile and run with JDK 9 or later:

~~~bash
javac PrivateInterfaceMethodsDemo.java
java PrivateInterfaceMethodsDemo
~~~

Exact stdout:

~~~text
[Hello, Linh!]
[Goodbye, Linh!]
[Hello, guest!]
CODE-AB-7
~~~

Both default methods call normalizeName and decorate, yet those helpers do not appear as public methods of MessageFormatter. The static method formatCode calls normalizeCode to share the normalization logic. The PrivateInterfaceMethodsDemo class only uses the public methods provided by the interface.

The example uses trim and isEmpty so it can run starting from Java 9. If the project sets a compilation level lower than Java 9, the compiler will reject the private method syntax in the interface. JDK 17 can also compile and run this example.

## 4. Access Rules to Know

**Private methods must have a body.** A private method cannot also be an abstract method, because abstract requires implementing classes to provide the body while private keeps the helper internal to the interface.

**Private methods are not default methods.** Do not declare a method as both private and default. Default methods are instance behavior exposed to implementing classes and callers; private instance methods are only internal helpers.

**Implementing classes cannot call private helpers.** External code cannot call a helper through an object or through the interface name. Only appropriate methods inside the interface can use them.

**Private methods are neither inherited nor overridden.** If an implementing class declares a method with the same name as a private helper of the interface, that method is a separate member of the implementing class; it does not override the interface's private helper.

**Distinguish between instance and static.** Instance helpers can work with instance calls in the interface. Static helpers have no object context and cannot directly access instance members without a suitable object. Reserve static helpers for logic that depends only on parameters and static data.

**Private static is also for internal use only.** Even though a static helper does not require an object, it still does not become an API callable from implementing classes. The static keyword does not remove the access restriction of private.

## 5. Common Mistakes

- **Using Java 8 to compile code with private methods in an interface.** The feature requires Java 9 or later; check the JDK and the project's source/release options.
- **Calling a private helper from an implementing class.** This helper is only for use within the interface. If the behavior genuinely needs to be called from outside, design a public method that fits the contract instead of trying to access the helper.
- **Putting all logic into public methods just for reuse.** Doing so enlarges the API and causes users to depend on details meant only to support the implementation. Use private methods when the logic only needs to be used inside the interface.
- **Duplicating the same logic across multiple default methods.** If the methods require the same processing step, consider extracting a private helper to avoid inconsistencies when making modifications.
- **Calling instance members from a static helper as if an object were available.** Static methods do not have this. Pass the required data through parameters or use an instance helper when the logic depends on instance context.
- **Confusing private methods with default methods.** Default methods create public behavior that implementing classes can inherit; private methods are a mechanism for organizing code inside an interface.

## 6. When Should You Use Them?

Use private methods in an interface when one or more default methods need to share a small routine such as normalizing input data, building messages, checking conditions, or composing processing steps. Use private static when a helper does not need instance state and is called from static methods or appropriate internal logic.

If a helper needs to be called from an implementing class, from an independent service, or from multiple unrelated types, consider moving it to a method on a helper class or turning it into a deliberately designed public API. Do not use private methods in an interface just because you can; they fit best when the behavior truly belongs to the interface's implementation.

This Java 9 feature helps interfaces maintain a cleaner API while still allowing authors to organize shared code clearly. When reading code, distinguish between public/default methods that users can call and private helpers that only serve inside the interface.
