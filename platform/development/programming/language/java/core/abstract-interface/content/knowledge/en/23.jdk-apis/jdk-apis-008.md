# Reading Javadoc on Implementation Requirements, Optional Methods, and Default Methods

The Javadoc of a Java API describes how to call the API and what implementers must guarantee. When reading an interface in the JDK, do not look only at method signatures: you need to know which methods are required to be implemented, which methods are optional, what the default implementation does, and what conditions cause a call to throw an exception.

Three related but non-synonymous concepts:

- **Implementation requirements** (*implementation requirements/specification*) describe what an implementation must do or uphold.
- An **optional method** (*optional operation*) is an operation that an implementation is permitted not to support under the API contract. When unsupported, the API typically specifies throwing `UnsupportedOperationException`.
- A **default method** is an instance method in an interface that has a default body. An implementing class can inherit that behavior or override it.

A method can be both a default method and an optional operation, but these two concepts are independent: having a default method does not automatically mean the operation is optional.

## 1. In What Order Should You Read Javadoc?

When encountering a type or method in the JDK, read the following sections:

1. **Short description and full description:** what problem the method solves, whether it has side effects, and what the general contract is.
2. **Signature and modifiers:** whether the method is abstract, default, static, or a class method; what the return type, parameters, and generic types are.
3. **`@param` and `@return`:** whether the input is allowed to be `null`, whether the return value can be `null`, whether the result is a copy or a view, and what state is guaranteed.
4. **`@throws`:** under what conditions an exception is thrown. Distinguish input error conditions from exceptions indicating that the implementation does not support the operation.
5. **Implementation Requirements / `@implSpec`:** the contract or requirements for implementation authors, especially when the API provides a default method.
6. **Implementation Note / `@implNote`:** information about how a specific implementation is built. Do not assume by default that these details are guaranteed for every implementation.
7. **API Note / `@apiNote`:** context and usage advice to help callers understand how to use the API.
8. **`@since`, `@see`, and inheritance links:** the API version in which it appeared, related methods, and contracts inherited from interfaces or superclasses.

The signature tells you what code can call; the Javadoc tells you what the call means and what guarantees you are allowed to rely on. When the contract explicitly states support conditions, mutability, ordering, consistency, or exceptions, rely on that contract instead of guessing from the method name.

## 2. `@implSpec`, `@implNote`, and `@apiNote`

These block tags help separate different kinds of information in Javadoc:

| Tag | What do you read it for? | How to apply |
| --- | --- | --- |
| `@implSpec` | Requirements or contracts that an implementation must adhere to; usually rendered as the **Implementation Requirements** section. | Use when implementing or overriding the API; do not violate the specified behavior. |
| `@implNote` | Notes on specific implementation details, such as how an implementation performs its work. | Use to understand that implementation; avoid assuming the details are a general property of the interface. |
| `@apiNote` | Useful notes for API users, such as usage examples or design context. | Use to understand how to call the API for its intended purpose. |

An example Javadoc for a default method might state:

```java
/**
 * Removes all entries.
 *
 * @implSpec The default implementation throws
 *           UnsupportedOperationException.
 * @throws UnsupportedOperationException if clearing is not supported
 */
default void clear() {
    throw new UnsupportedOperationException("clear");
}
```

`@implSpec` explains the default behavior that implementers need to understand when inheriting or overriding the method. `@throws` describes the exception condition. If an implementation overrides `clear()`, the author needs to read the entire contract so as not to accidentally break what callers are permitted to expect.

Do not interpret `@implNote` as a general commitment. For example, a note stating "this implementation stores elements in an `ArrayList`" does not allow callers to depend on `ArrayList` if the API type does not expose that.

## 3. Required Methods and Optional Methods

### Methods Required to Implement

An abstract method in an interface only declares a contract and has no default body. A concrete class implementing the interface must provide implementations for the abstract methods for which it has not already inherited a valid implementation; if it has not done so, the class must be declared `abstract`.

Example:

```java
interface Encoder {
    byte[] encode(String value);
}
```

A concrete class implementing `Encoder` must define `encode(String)`, unless the method has already been validly inherited from a superclass. The Javadoc of `encode` still needs to be read to know how `null`, charsets, errors, and the meaning of the returned byte array are handled.

### Optional Methods

Javadoc refers to an operation as an **optional operation** when an implementation is permitted not to support that operation. Callers cannot infer that every object of the same interface supports every operation merely from the fact that the method appears in the API.

A JDK example is `Collection.add(E)`: the API documentation describes it as an optional operation and specifies `UnsupportedOperationException` if the collection does not support adding elements. An unmodifiable collection may allow reading while rejecting mutating operations. Callers need to know whether the collection in use supports the required operation, or handle the exception according to the appropriate contract.

Key points to remember:

- "Optional" describes whether the operation is supported under the API contract; it does not mean callers are allowed to ignore all rules of the method.
- An optional operation can be declared as abstract; the implementation must still provide a method body, but it can signal lack of support with an exception according to the contract.
- An API can also use a default method that throws `UnsupportedOperationException` as the default behavior for an optional operation.
- Not every `UnsupportedOperationException` proves that an operation is optional across the entire API; read the Javadoc of the exact method and specific type.

### `UnsupportedOperationException` Differs from Input Errors

`IllegalArgumentException` usually signals an invalid argument under the contract. `UnsupportedOperationException` usually signals that the object or implementation does not support the requested operation. The two exceptions have different meanings; you should not use them interchangeably at will or catch all exceptions and pretend the operation succeeded.

## 4. How Do Default Methods Work?

Since Java 8, an interface can declare an instance method with the `default` keyword and provide a body:

```java
interface Named {
    String name();

    default String displayName() {
        return "[" + name() + "]";
    }
}
```

A class implementing `Named` must provide `name()` if no valid implementation is already inherited. It can use `displayName()` directly or override that method. Default methods allow an interface to add shared behavior without forcing every class to rewrite the same body.

A default method is still an instance method: it is invoked on an object and can call other methods in the contract. The default body does not automatically guarantee that every operation it invokes is supported by the implementation; readers must still check the Javadoc and the conditions of the called methods.

### Implementation Selection Rules

When the same signature appears in a class and interfaces, keep these key principles in mind:

1. **Class implementations take precedence over interface default methods.** If a class or superclass has a matching instance method, it takes precedence according to Java's rules.
2. **More specific interfaces can take precedence over parent interfaces.** If a subinterface overrides a superinterface's default method, the implementation inherited through the subinterface takes precedence.
3. **Two conflicting default methods from interfaces with no more-specific relationship** can force the class to override and explicitly choose a behavior; if the conflict is not resolved, the code will not compile.
4. **Default methods do not replace abstract methods under a general name.** Only a method with a `default` body provides a default implementation; an interface's static method is not inherited as an instance method.

Conflict example:

```java
interface A {
    default String label() { return "A"; }
}
interface B {
    default String label() { return "B"; }
}

class Combined implements A, B {
    @Override
    public String label() {
        return A.super.label();
    }
}
```

`Combined` must resolve the conflict by overriding; in the example, it explicitly chooses the body from `A`. The `A.super.label()` syntax can only be used when the interface and method relationship allows such a direct call.

## 5. Default Methods and Optional Operations Are Not the Same Concept

You can distinguish them with two questions:

- **Default method:** "If a class does not override it, which body does Java use?"
- **Optional operation:** "According to the contract, is an implementation permitted not to support this operation?"

There are four cases to distinguish:

| Case | Meaning |
| --- | --- |
| Abstract method, required behavior | A concrete class must provide an implementation and fulfill the contract. |
| Abstract method, optional operation | A concrete class still provides a method body, but the contract permits signaling lack of support in the specified manner. |
| Default method, normal default behavior | A class can inherit the behavior and must uphold the contract when overriding it. |
| Default method, optional operation | The default behavior may throw `UnsupportedOperationException`; a class that supports the operation can override it. |

The JDK's `Collection.add(E)` is a useful example of an optional operation; `Iterator.remove()` illustrates an optional operation with a default implementation that throws `UnsupportedOperationException`. When reading documentation, look for both the "optional operation" statement and the `@implSpec`/`@throws` sections, rather than inferring from the `default` keyword in the signature.

## 6. Java 17+ Example: Implementations Inheriting and Overriding an Optional Operation

This example creates an interface with a default `clear()` method that throws `UnsupportedOperationException`. `AppendOnlyLog` inherits that behavior; `EditableLog` overrides `clear()` to support clearing. The Javadoc explicitly describes that the operation is optional.

Save the complete code to `JavadocContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class JavadocContractDemo {
    interface MessageLog {
        void append(String message);
        int size();

        /**
         * Removes all messages from this log.
         * This is an optional operation.
         *
         * @implSpec The default implementation throws
         *           UnsupportedOperationException.
         * @throws UnsupportedOperationException if clearing is not supported
         */
        default void clear() {
            throw new UnsupportedOperationException("clear");
        }
    }

    static final class AppendOnlyLog implements MessageLog {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void append(String message) {
            messages.add(message);
        }

        @Override
        public int size() {
            return messages.size();
        }
    }

    static final class EditableLog implements MessageLog {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void append(String message) {
            messages.add(message);
        }

        @Override
        public int size() {
            return messages.size();
        }

        @Override
        public void clear() {
            messages.clear();
        }
    }

    public static void main(String[] args) {
        MessageLog appendOnly = new AppendOnlyLog();
        appendOnly.append("one");
        appendOnly.append("two");
        System.out.println("append-only size before clear=" + appendOnly.size());
        try {
            appendOnly.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("append-only clear unsupported");
        }

        MessageLog editable = new EditableLog();
        editable.append("one");
        editable.clear();
        System.out.println("editable size after clear=" + editable.size());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac JavadocContractDemo.java
java JavadocContractDemo
```

Exact stdout:

```text
append-only size before clear=2
append-only clear unsupported
editable size after clear=0
```

`AppendOnlyLog` does not override `clear()`, so the call uses the default body and throws `UnsupportedOperationException`. `EditableLog` overrides the same method, so the clear operation succeeds. Both are still `MessageLog`, but their support for the operation differs according to the documented contract. In real APIs, callers should read the documentation and not assume an optional operation will always succeed.

This example illustrates the language mechanism. For public APIs, carefully consider adding optional operations to an interface and clearly document support conditions, side effects, safety on repeated calls, and exceptions.

## 7. Adding a Default Method to an Existing Interface: Benefits and Risks

Default methods allow library authors to add shared behavior that many older classes can inherit, rather than forcing every implementation to immediately write a new method. This is why default methods are important for JDK interfaces and libraries with many implementations.

However, adding a default method is not always completely risk-free:

- A class that already has a method with the same signature may select the class's method under the precedence rules, leading to behavior different from what the interface author anticipated.
- When a class implements multiple interfaces, default methods with the same signature can create conflicts that require overriding.
- The new default behavior may not fit the invariants or constraints of an older implementation, even when the code still compiles.
- The Javadoc must describe the contract clearly, including support conditions, exceptions, and effects on state.

When upgrading the JDK or a library, review the documentation for the version in use and check relevant implementations; do not assume a default method will always automatically fit every existing class.

## 8. Checklist When Reading a JDK API

Before using or implementing a method, ask yourself:

- Is the method abstract, default, or static? If default, what does the default body do?
- Does the Javadoc state "optional operation"? If so, which exception is specified when unsupported?
- Does `@implSpec` impose conditions or requirements that an implementation must adhere to?
- What internal details does `@implNote` merely describe? Are those details actually a public commitment?
- What do `@param`, `@return`, and `@throws` say about `null`, mutability, state, results, and errors?
- If overriding, does the implementation preserve the contract that callers rely on?
- If multiple interfaces provide a default method with the same signature, which inheritance rules apply?
- If upgrading a library, is a new default method behaviorally compatible with existing implementations?

## Conclusion

When reading Javadoc, separate the API contract from implementation details. `@implSpec` helps you understand requirements for implementations; `@implNote` provides technical notes; "optional operation" indicates that an operation might not be supported; `default` indicates that the interface provides an instance body ready to be inherited. Reading the signature, description, `@throws`, and these notes together will help you implement interfaces according to the contract and avoid wrong assumptions about JDK API behavior.
