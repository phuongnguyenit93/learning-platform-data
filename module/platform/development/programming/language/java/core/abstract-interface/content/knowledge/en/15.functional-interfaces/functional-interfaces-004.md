# Excluding Public Methods of `Object` When Determining the Functional Contract

In Java, a **functional interface** provides a contract consisting of one abstract method so that a lambda expression or method reference can represent its behavior. When determining that contract, Java **does not count abstract declarations that are override-equivalent to public methods of `Object`**, such as `equals(Object)`, `hashCode()`, and `toString()`, as functional methods.

This rule allows an interface to redeclare common methods of every object while still preserving a single functional method. Java examines the signature and the override-equivalent relationship, not just the method name.

## 1. What Is a Functional Contract?

A functional interface has one functional method (often called SAM — *Single Abstract Method*). The signature of this method defines the parameters, result type, and exceptions that a lambda or method reference must satisfy.

```java
@FunctionalInterface
interface TextConsumer {
    void accept(String value);
}
```

`TextConsumer` has one abstract method, `accept(String)`, so it can serve as a target type for a lambda:

```java
TextConsumer printer = value -> System.out.println(value);
printer.accept("Java");
```

At compile time, Java checks the target type and verifies that the lambda matches the signature of the functional method.

## 2. Why Exclude Public Methods of `Object`?

Every Java object has public methods inherited from `Object`. Common examples are:

- `boolean equals(Object other)` — compares equality.
- `int hashCode()` — provides a hash code.
- `String toString()` — provides a string representation.

An interface can redeclare these methods to express the contract it expects. However, those declarations do not create additional functional methods, because they correspond to public methods already present on every Java object.

```java
@FunctionalInterface
interface TextConsumer {
    void accept(String value);

    boolean equals(Object other);
    int hashCode();
    String toString();
}
```

The interface above is still a functional interface. `accept(String)` is the sole functional method; `equals(Object)`, `hashCode()`, and `toString()` are not counted as additional functional methods. The implementing class or lambda object still has the corresponding public methods of `Object`.

The rule is based on whether a declaration is *override-equivalent* to a public method of `Object`. The three methods above are common examples, not a rule based solely on names.

## 3. A Complete Example That Compiles and Runs

Save the following content to the file `FunctionalObjectMethodsDemo.java`:

```java
@FunctionalInterface
interface TextConsumer {
    void accept(String value);

    // These declarations do not increase the number of functional methods.
    boolean equals(Object other);
    int hashCode();
    String toString();
}

public class FunctionalObjectMethodsDemo {
    public static void main(String[] args) {
        TextConsumer printer =
                value -> System.out.println("Đã nhận: " + value);

        printer.accept("Java");
    }
}
```

Compile and run with JDK 17 or later:

```text
javac -encoding UTF-8 FunctionalObjectMethodsDemo.java
java FunctionalObjectMethodsDemo
```

Expected output:

```text
Đã nhận: Java
```

The lambda only provides behavior for `accept(String)`. The remaining three declarations do not require the lambda to write additional method bodies. They do not change the signature that the lambda must satisfy.

A method reference can be used instead of a lambda for the same target type:

```java
TextConsumer printer = System.out::println;
printer.accept("Java");
```

The method reference is also checked against the functional method `accept(String)`.

## 4. Signature Matters More Than Method Name

The exclusion rule does not apply to every method merely because it is named `equals`, `hashCode`, or `toString`. The signature must match according to the override-equivalent rule.

The following example is **not** a functional interface:

```java
@FunctionalInterface
interface InvalidAction {
    void run();

    boolean equals(String other);
}
```

`equals(String)` is not override-equivalent to `Object`'s `equals(Object)` because the parameter types differ. As a result, the interface has two independent abstract methods: `run()` and `equals(String)`. The `@FunctionalInterface` annotation causes the compiler to report an error because the interface does not meet the condition.

Similarly, a method that has the same name but adds parameters, changes parameter types, or has a different signature is not automatically excluded. Examine the full signature and inheritance relationships rather than looking only at the method name.

## 5. What If an Interface Only Redeclares a Method of `Object`?

```java
@FunctionalInterface
interface EqualityOnly {
    boolean equals(Object other);
}
```

This interface has no remaining functional methods after applying the exclusion rule. Therefore, it is not a functional interface, and the compiler will reject `@FunctionalInterface`. It cannot be used as a target type for a lambda as if it had a SAM.

This differs from `TextConsumer` in the previous example: `TextConsumer` also has `accept(String)`, so after excluding the declarations corresponding to `Object`, there is still exactly one functional method left.

## 6. Inherited Methods with the Same Signature

When an interface inherits multiple abstract declarations that have the same signature and compatible return types, those declarations can resolve to the same functional method. Therefore, you should not simply count the number of abstract declaration lines in the source code.

```java
interface HasName {
    String value();
}

interface HasLabel {
    String value();
}

@FunctionalInterface
interface NamedValue extends HasName, HasLabel {
}
```

`NamedValue` can still be a functional interface because the two `value()` declarations are compatible and resolve to the same signature. This case differs from excluding `Object` methods: here, the declarations are merged due to signature and inheritance; in contrast, public methods of `Object` are ignored when determining the functional method.

If the inherited declarations are incompatible—for example, if their return types cannot be reconciled—the interface itself may fail to compile. The `Object` method exclusion rule does not resolve such type conflicts.

## 7. The Role of `@FunctionalInterface`

`@FunctionalInterface` is a compile-time check annotation. It asks the compiler to confirm that the interface satisfies the functional interface rules. This annotation does not turn an arbitrary interface into a functional interface, nor does it change how the functional method is determined.

You should use this annotation when intentionally designing an interface for a lambda or method reference. If an abstract method incompatible with the existing functional method is added later, a compilation error helps detect the change that breaks the contract.

`default`, `static`, and `private` methods in an interface are not abstract methods counted toward the SAM. When checking, focus on the abstract declarations and inherited abstract methods.

## 8. How to Determine Whether an Interface Is a Functional Interface

You can check in the following order:

1. List the abstract methods declared directly and inherited from superinterfaces.
2. Exclude declarations that are override-equivalent to public methods of `Object`, such as `equals(Object)`, `hashCode()`, and `toString()`.
3. Check whether the remaining declarations have the same signature and compatible return types to resolve to a single functional method.
4. Verify that the result has exactly one functional method.
5. Add `@FunctionalInterface` so that the compiler confirms this intent.

When a lambda fails with a not-a-functional-interface error, check the actual signatures of the abstract methods, including methods coming from superinterfaces. Do not assume that methods with the same name are always merged, or that redeclaring `equals(Object)` creates an additional SAM.

## 9. Common Misconceptions

- **"An interface with multiple abstract declarations is definitely not a functional interface."** Incorrect. Declarations that are override-equivalent to public methods of `Object` are excluded; inherited declarations with compatible signatures can also resolve to the same functional method.
- **"Any method named `equals` is excluded."** Incorrect. `equals(String)` has a different signature from `equals(Object)` and can still be an independent abstract method.
- **"Adding `@FunctionalInterface` makes an interface valid."** Incorrect. The annotation only requests a check and reports an error if the condition is not met.
- **"A lambda must provide bodies for `equals`, `hashCode`, and `toString` if the interface declares them."** Incorrect. Declarations corresponding to public methods of `Object` are not counted as functional methods.
- **"There must be exactly one abstract declaration line in the file."** Incorrect. What needs to be determined is the functional method after considering signatures, inheritance, and the exclusion rule.

## Conclusion

When determining the functional contract of an interface, look for the abstract method that remains after applying the signature and inheritance rules. Declarations that are override-equivalent to public methods of `Object` do not increase the number of functional methods. As a result, an interface can redeclare `equals(Object)`, `hashCode()`, or `toString()` and still be usable with a lambda, provided it has exactly one true functional method.
