# `@FunctionalInterface` and Compile-Time Checking

`@FunctionalInterface` is an annotation used to indicate that an interface is designed as a **functional interface** and to require the compiler to verify this. If the declaration does not satisfy Java's rules, the compiler reports an error right at the interface, helping detect changes that break the lambda contract before the program runs.

## 1. What Does the Annotation Confirm?

```java
@FunctionalInterface
interface TextOperation {
    String apply(String input);
}

public class FunctionalInterfaceAnnotationDemo {
    public static void main(String[] args) {
        TextOperation upper = text -> text.toUpperCase(java.util.Locale.ROOT);
        System.out.println(upper.apply("java"));
    }
}
```

Save as `FunctionalInterfaceAnnotationDemo.java`, then run:

```bash
javac FunctionalInterfaceAnnotationDemo.java
java FunctionalInterfaceAnnotationDemo
```

Output:

```text
JAVA
```

The compiler accepts the declaration because `TextOperation` has one functional abstract method, `apply(String)`. The lambda is assigned to that type, so it must satisfy the signature taking `String` and returning `String`.

The annotation is **not required** to use a lambda. If you remove `@FunctionalInterface`, `TextOperation` is still a functional interface and the example still compiles. The benefit of the annotation is turning design intent into a condition the compiler can check.

## 2. When Adding a Second Abstract Method

The following snippet intentionally does not compile:

```java
@FunctionalInterface
interface InvalidOperation {
    String apply(String input);
    String label(String input);
}
```

The two methods have two independent purposes, so the interface does not have a single functional contract. The compiler rejects the annotation. If you only remove the annotation, the declaration can exist as a regular interface, but you still cannot use a simple lambda to implement both `apply` and `label`.

When an API needs additional behavior, choose according to the design semantics:

- Keep the new abstract method if every implementation must genuinely provide that behavior; in that case, the interface is no longer suitable as a lambda target type.
- Use `default` only when there is a default implementation that is correct and meaningful for every implementation.
- Use `static` for utilities belonging to the interface, or separate the responsibilities into a distinct interface if the two behaviors should not be tied together.

Do not turn a method into a default method just to keep the annotation if the default body is not correct for the business logic.

## 3. An Interface Without Abstract Methods Is Also Invalid

This example also does not compile:

```java
@FunctionalInterface
interface NoOperation {
    default void run() {
        System.out.println("running");
    }
}
```

`run()` already has a body, so there is no abstract method left for a lambda to implement. `@FunctionalInterface` does not mean “an interface can be called with a lambda”; it asserts that the interface must satisfy Java's functional interface rules.

## 4. The Compiler Applies the Full Java Rules

Determining the functional contract includes inherited abstract methods, equivalent signatures, and return types. Declarations corresponding to public instance methods of `Object`, as well as `default`, `static`, and `private` methods, are handled according to separate language rules. Therefore, you should not simply count the declaration lines in the current interface.

The lessons on interface inheritance, `Object` methods, and method types present those cases in detail. Here, what needs to be checked is whether the compiler accepts the entire declaration as a functional interface.

## 5. The Annotation Does Not Test Program Logic

`@FunctionalInterface` checks **the shape of the contract**; it does not prove that the method body is correct. The compiler can still accept a lambda that returns an incorrect business result, handles null improperly, or throws an unchecked exception at runtime.

For example, both lambdas below can match `TextOperation`, yet only one may meet the application's actual requirements:

```java
TextOperation upper = text -> text.toUpperCase(java.util.Locale.ROOT);
TextOperation constant = text -> "JAVA";
```

The annotation also does not generate an implementation, handle exceptions automatically, or guarantee performance. Use tests and contract documentation to verify behavior; use the annotation to maintain the correct functional interface structure.

## 6. How to Read Compiler Errors

Specific messages vary by JDK, but common situations include:

| Situation | Cause to Check |
| --- | --- |
| Annotation is rejected because there are multiple abstract methods | An independent abstract method was added or inherited |
| Annotation is rejected because there is no functional method | No functional abstract method remains after applying Java's rules |
| Annotation is placed on a class instead of an interface | `@FunctionalInterface` is only for interface declarations |
| A lambda uses the interface but does not compile | Check the target type and signature; removing the annotation does not turn a multi-method interface into a SAM |

When fixing an error, review the contract and inherited methods first. Removing the annotation can obscure the original intent without restoring lambda usability.

## 7. Checklist When Defining an API

1. Is the interface truly designed to accept a lambda or method reference?
2. Is there one valid functional abstract method according to Java's rules?
3. Does an additional method really need to be abstract, or does a default/static method have more accurate semantics?
4. Do the parameters, result, and checked exceptions clearly express the required contract?
5. Are separate tests needed for logic, boundary data, and runtime errors?

**Remember:** `@FunctionalInterface` is a compiler-checked confirmation, not a mechanism that automatically generates behavior. Use it to protect the interface design intent, while verifying logic and the runtime contract through appropriate means.
