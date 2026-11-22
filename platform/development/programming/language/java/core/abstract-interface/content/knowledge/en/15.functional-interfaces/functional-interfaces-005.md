# Default, static, and private methods in functional interfaces

In Java, a **functional interface** has exactly one abstract method according to the rules of the language. This abstract method is the contract that an implementing class must provide; it is also the method used when assigning a lambda or method reference to the interface type.

An interface can still declare multiple additional `default`, `static`, and `private` methods. These methods have a body, so they do not create additional abstract method requirements. Therefore, an interface with multiple declared methods can still be a functional interface.

## 1. The abstract method is the required part of the contract

A method declared in an interface without a body is typically an abstract method. That method must be implemented by an implementing class, unless the implementing class remains `abstract`.

```java
String process(String text);
```

With the method above, a concrete class implementing the interface must provide an implementation for `process`. If the interface has another independent abstract method, it typically no longer meets the functional interface condition.

`@FunctionalInterface` helps the compiler check this condition. The annotation is not required to write a lambda, but it is very useful because the compiler will report an error if subsequent changes cause the interface to no longer be a functional interface.

## 2. `default` methods provide default behavior

A `default` method is an instance method with a body in an interface. An implementing class inherits the default behavior and can override it when needed.

```java
default String processOrEmpty(String text) {
    return process(text == null ? "" : text);
}
```

In this example, `processOrEmpty` calls the abstract method `process` and handles the `null` input case. An implementing class only needs to define `process`; it is not required to override `processOrEmpty`. Therefore, a `default` method does not increase the number of abstract methods.

`default` methods are suitable when you want to add shared behavior for implementing classes while maintaining compatibility with older classes. If two interfaces provide conflicting `default` methods with the same signature, the implementing class may have to provide its own override to resolve the conflict.

## 3. `static` methods belong to the interface

A `static` method has a body and is called using the interface name. It is not instance behavior that an implementing class must provide, nor is it inherited like a regular instance method.

```java
TextProcessor.trimmed();
```

You can place creation functions, utilities, or factory methods in an interface. For example, a static method can return a lambda of the interface type. A static method itself is not an abstract method and does not cause the interface to lose its functional nature.

## 4. `private` methods are internal helper methods

Interfaces have supported `private` methods since Java 9. A private method must have a body and is used to share processing logic among other methods within the same interface.

- A `private` instance method can be called from instance methods in the interface that have access, such as a `default` method.
- A `private static` method can be called from other static methods in the interface.
- Implementing classes and subinterfaces do not inherit or directly call these private methods.

Because it has a body and serves only internal implementation, a `private` method does not create an additional abstract contract for implementing classes.

## 5. Complete Java example

The following example has one abstract method, `process`, along with `default`, `static`, `private`, and `private static` methods. The interface is still annotated with `@FunctionalInterface` and can accept a lambda.

```java
import java.util.Locale;

public class FunctionalInterfaceMethodsDemo {

    @FunctionalInterface
    interface TextProcessor {
        String process(String text);

        default String processOrEmpty(String text) {
            return process(text == null ? "" : text);
        }

        default String processWrapped(String text) {
            return "[" + trimForDisplay(process(text)) + "]";
        }

        static TextProcessor trimmed() {
            return text -> normalize(text);
        }

        static TextProcessor normalized() {
            return text -> normalize(text).toLowerCase(Locale.ROOT);
        }

        private String trimForDisplay(String text) {
            return text == null ? "" : text.trim();
        }

        private static String normalize(String text) {
            return text == null ? "" : text.trim();
        }
    }

    public static void main(String[] args) {
        TextProcessor upper = text -> text.toUpperCase(Locale.ROOT);
        System.out.println(upper.process("java"));
        System.out.println(upper.processOrEmpty(null));
        System.out.println(TextProcessor.trimmed().process("  Java  "));
        System.out.println(TextProcessor.normalized().process("  JaVa  "));
        System.out.println(upper.processWrapped(" java "));
    }
}
```

Save the code to the file `FunctionalInterfaceMethodsDemo.java`, then run it with JDK 17 or later:

```bash
javac FunctionalInterfaceMethodsDemo.java
java FunctionalInterfaceMethodsDemo
```

Stdout output:

```text
JAVA

Java
java
[JAVA]
```

The second line is a blank line: `processOrEmpty(null)` converts `null` into an empty string and passes that string to the lambda `upper`.

In the example:

- `process` is the only abstract method that the lambda must implement.
- `processOrEmpty` and `processWrapped` are inherited `default` instance methods. `processWrapped` uses `trimForDisplay`, a private instance helper.
- `trimmed` and `normalized` are static factory methods, called using `TextProcessor`. Both use the private static helper `normalize`.
- `trimForDisplay` and `normalize` have bodies and only support implementation inside the interface.

## 6. Quick comparison

| Method type | Has a body | Implementing class must provide | Counted as an abstract method |
| --- | --- | --- | --- |
| Abstract method | No | Yes, if the class is concrete | Yes |
| `default` | Yes | No; can be overridden | No |
| `static` | Yes | No | No |
| `private` instance | Yes | No | No |
| `private static` | Yes | No | No |

The table above covers the method types in an interface. The rules for determining a functional interface also consider inherited methods and equivalent signatures; you should not simply count the number of declaration lines in an interface.

## 7. Common points of confusion

1. **A functional interface does not mean only one method can be declared in total.** It can have multiple `default`, `static`, and `private` methods, as long as it still meets the rule for abstract methods.
2. **Adding another independent abstract method can break the lambda contract.** When an interface has `@FunctionalInterface`, the compiler will report an error if that change causes the interface to no longer qualify.
3. **Call static methods through the interface name.** An example is `TextProcessor.trimmed()`. This method does not become an instance method of a `TextProcessor` object.
4. **Private interface methods require Java 9 or later.** If compatibility with Java 8 is needed, you cannot use private methods in an interface.
5. **A `default` method is behavior that is already provided.** An implementing class can use it directly or override it, so it does not create an additional abstract implementation requirement.

Public methods of `Object` such as `equals(Object)` are also handled under separate rules when determining a functional interface; do not conclude that every visible abstract signature adds an independent lambda requirement.

## Conclusion

What determines a functional interface is the abstract method contract, not the total number of declared methods. `default` provides ready-to-use instance behavior, `static` provides behavior belonging to the interface, and `private` and `private static` are internal helper methods. These methods have a body, so they do not create additional abstract method requirements for implementing classes.
