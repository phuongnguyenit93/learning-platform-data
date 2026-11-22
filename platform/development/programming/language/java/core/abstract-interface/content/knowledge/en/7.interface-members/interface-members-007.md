# Access Restrictions and Invalid Modifiers of Interface Members

## 1. Distinguishing the Interface Type from the Members Inside It

The access rules of an interface itself differ from those of its members. A top-level interface can be package-private if public is omitted. However, a regular abstract method inside an interface is still implicitly public abstract; omitting public does not make it package-private.

This lesson is a reference table of modifier combinations. Full explanations and examples for each type of method are in the lesson on method classification and the lesson on implicitly public abstract methods.

## 2. Valid Modifier Matrix

| Member | Default or Required Rules | Important Restrictions |
| --- | --- | --- |
| Field | public static final, must have an initializer | Cannot be private, protected, volatile, or transient |
| Abstract method | public abstract, no body | Cannot be private, protected, static, or final |
| Default method (Java 8+) | Public instance method with a body | Cannot combine with abstract, static, or private |
| Static method (Java 8+) | Public static with a body, except private static helpers | Cannot be abstract; cannot be called as an inherited instance method |
| Private method (Java 9+) | Private instance or private static, always has a body | Cannot be abstract or default |
| Member type nested in an interface | Implicitly public static | Cannot be private or protected when declared directly in the interface |

These rules explain why a private field cannot be used to hide state in an interface. If private state is needed, place the field in a class. If an internal helper method is needed from Java 9 onward, use a private method with a body.

## 3. A Valid Interface as a Reference Example

~~~java
interface AccessRules {
    int LIMIT = 3;

    void execute();

    default String describe() {
        return "[" + LIMIT + "]";
    }

    static boolean valid(int value) {
        return value >= 0;
    }

    private String helper(String value) {
        return value.trim();
    }

    private static String normalize(String value) {
        return value.trim();
    }

    class Metadata {
        String category() {
            return "rules";
        }
    }
}
~~~

LIMIT is a public static final field. execute is public abstract. describe is a default instance method with a body; valid is a static method with a body; helper and normalize are private helper methods. Metadata is an implicitly public static member type. The code above uses Java 17+ syntax.

## 4. Common Invalid Combinations

| Invalid Declaration | Why It Is Invalid | How to Fix |
| --- | --- | --- |
| private int code = 1; | Interface fields are always public static final | Place private state in a class |
| protected void work(); | Interface methods do not have protected access | Use a public abstract method or a private helper with a body |
| private abstract void work(); | Private helpers cannot be abstract or overridden | Use a public abstract contract or a private method with a body |
| static void work(); | Static methods must have a body | Write the static method with a body |
| default void work(); | Default methods must have a body | Write a body or use an abstract declaration |
| static default void work() { } | Static and default describe two different kinds of methods | Choose the appropriate kind |
| final default void work() { } | Interface methods cannot be final | Use default or static depending on intent |
| private class Detail { } | Interface member types are implicitly public static | Place the type to be hidden inside an appropriate class |

Do not combine the invalid lines into a single program to test them: each line illustrates a separate compile-time error. Interface methods also cannot be declared synchronized or native. Abstract methods have no body; default, static, and private methods must have a body.

## 5. Java Versions to Note

- **Java 8:** supports default methods and static methods with a body in interfaces.
- **Java 9:** added private instance methods and private static methods to reuse internal logic.
- **Java 17+:** all of the forms above can be used together, as long as each modifier matches the member kind.

Do not infer that Java 9 allows all private members: private fields and private member types declared directly in an interface remain invalid.

## 6. Commonly Confused Scope Errors

A **top-level interface** without public may only be accessible within the package. That does not make the methods inside it package-private.

A **member type** directly inside an interface is implicitly public static. In contrast, a nested interface inside a class follows the member rules of the enclosing class; a class can have a private nested type.

An **abstract method** requires a compatible implementation in a concrete class, so the implementing class must use public. A **private helper** only supports logic inside the interface and is not inherited or overridden. A **static method** belongs to the interface type and is called via the interface name.

### Checklist

1. Does the field have an initializer and avoid disallowed modifiers?
2. Is the abstract method understood to be public even when the keyword is omitted?
3. Does the default/static/private method have a body and is it of the right kind?
4. Is the private method used only as an internal helper and not mistaken for an implementation contract?
5. Is the member type made public according to the interface's public static rule?
6. Has the concrete class implemented the abstract methods with public?

Use this matrix when reading compile-time errors. Before changing a modifier, identify whether the member is a field, an abstract/default/static/private method, or a member type; removing an incorrect keyword does not necessarily produce a valid declaration.
