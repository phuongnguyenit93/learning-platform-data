# Member Classes Inside an Interface and Implicit Modifiers

## Objectives

After this lesson, you will be able to explain why a class declared directly inside an interface is `public static` by default, create objects from that class, correctly read the scope of modifiers, and avoid confusing the modifiers of a nested class with the modifiers of an interface.

## 1. What Is a Member Class in an Interface?

Java allows declaring a class directly inside an interface body. When a class is declared directly at the member level of an interface, it is a **member class**. For example:

~~~java
interface Payment {
    class Receipt {
        public String render() {
            return "Receipt";
        }
    }
}
~~~

The `class Receipt` declaration above is equivalent in type modifiers to:

~~~java
interface Payment {
    public static class Receipt {
        public String render() {
            return "Receipt";
        }
    }
}
~~~

According to the Java language rules, every **member type** declared in an interface is implicitly `public static`. This rule applies to member classes, nested interfaces, enums, and other valid member types. Therefore, the `public` and `static` keywords may be written explicitly to emphasize their meaning, but they are not required.

- **Implicit `public`:** the nested type is a publicly accessible part of the interface API, subject to the accessibility of the enclosing interface itself.
- **Implicit `static`:** the nested type is not tied to an instance of the enclosing interface. It is neither necessary nor possible to create it using the syntax of an inner class that requires an enclosing object.
- **Not implicitly `final` or `abstract`:** the class still follows the normal modifier rules for Java classes; it can be declared `final` or `abstract` when appropriate, but both cannot be used at the same time.
- **Cannot make this member type `private` or `protected`:** those modifiers conflict with the member type in an interface being implicitly `public`.

## 2. Creating and Using Objects

Save the following program in the file `InterfaceNestedClassDemo.java`. The `Payment` interface is left at package scope so that the entire example can reside in a single file; the `Receipt` class still demonstrates the implicit `public static` rule inside an interface.

~~~java
interface Payment {
    String CURRENCY = "VND";

    class Receipt {
        private final String transactionId;

        public Receipt(String transactionId) {
            this.transactionId = transactionId;
        }

        public String render() {
            return "Receipt " + transactionId + " in " + CURRENCY;
        }
    }
}

public class InterfaceNestedClassDemo {
    public static void main(String[] args) {
        Payment.Receipt receipt = new Payment.Receipt("TX-101");
        System.out.println(receipt.render());
    }
}
~~~

Compile and run using Java 17 or later:

~~~text
javac InterfaceNestedClassDemo.java
java InterfaceNestedClassDemo
~~~

Standard output:

~~~text
Receipt TX-101 in VND
~~~

The full type name is `Payment.Receipt`. You can create an object directly with `new Payment.Receipt("TX-101")`; no `Payment` object is needed as an enclosing object. `Payment` is an interface, so it cannot itself be instantiated with `new`.

In the example, `CURRENCY` is a field declared directly in the interface, so it is implicitly `public static final`. By contrast, `transactionId` and `render()` are inside the `Receipt` class; they follow normal class access and modifier rules. The implicit modifiers of the `Receipt` type do not automatically make every member inside the class `public` or `static`.

## 3. Scope of Implicit Modifiers

| Declaration | Rule |
|---|---|
| `class Receipt { }` directly inside an interface | Member type is implicitly `public static` |
| `public static class Receipt { }` directly inside an interface | Valid; `public static` is written explicitly but redundant |
| `private class Receipt { }` or `protected class Receipt { }` directly inside an interface | Invalid because the access modifier conflicts with the implicit `public` |
| Field declared directly inside an interface | Implicitly `public static final` |
| Method declared directly inside an interface | Follows the rules specific to interface methods; not inferred from nested class modifiers |
| Local class declared inside a method body | It is a local class, not a direct member type of the interface; it does not receive the `public static` rule above |

A common point of confusion is that **the modifiers of the nested type and the modifiers of the constructor are two different things**. If no constructor is declared, Java generates a default constructor with an access level matching the class. If you declare a constructor yourself and omit the access modifier, that constructor has package-private scope, even though the `Receipt` class is `public`. When code in another package needs to instantiate the class, declare the constructor as `public`.

A member class in an interface can have instance fields, constructors, and instance methods just like a regular class. Because this class is `static`, it has no implicit reference to an enclosing instance. If you need to use the instance behavior of another object, pass that object in or invoke it through an appropriate reference variable.

## 4. Other Nested Member Types

The implicit `public static` rule also applies to member types declared in an interface, not just classes:

~~~java
interface Registry {
    interface Reader {
        String read();
    }

    enum State {
        READY, CLOSED
    }

    record Item(String id) {
    }
}
~~~

In this example, `Reader`, `State`, and `Item` are member types of `Registry`; they are declared inside the interface and can be referenced by qualified names such as `Registry.Reader`, `Registry.State`, and `Registry.Item`. Enums are inherently static according to the rules for enums; member records are also static types. Records have been supported since Java 16, so this combined example requires Java 16 or later (Java 17 meets this requirement).

Do not confuse these public member types with internal helper classes. If a class serves only a single implementation and should not appear in the API, consider placing it in an appropriate scope outside the interface or inside the implementing class, rather than declaring it directly inside the interface.

## 5. Common Mistakes and How to Avoid Them

1. **Trying to instantiate the nested class like an inner class:** writing `payment.new Receipt(...)` or assuming an enclosing instance is required. The correct way is `new Payment.Receipt(...)`.
2. **Assuming a nested class automatically has all its members as public static:** only the member type declared directly in the interface receives the `public static` rule; fields, constructors, and methods inside the nested class still follow the class's own rules.
3. **Using `private` or `protected` for a member type:** these modifiers are invalid for a member type declared directly in an interface because that type is already implicitly `public`.
4. **Assuming `static` means it cannot have state:** this modifier only indicates that the nested class does not need an enclosing instance. Each `Receipt` object can still hold its own state, such as the `transactionId` field.
5. **Overlooking constructor scope:** when you need to provide instantiation capability to callers in another package, set a clear access modifier on an explicitly declared constructor.
6. **Placing a private implementation class into the interface API:** an interface's member type is public according to the language. Only declare it here when the type should truly be part of the API.

## 6. Quick Verification Process

When you encounter a class inside an interface, check in this order:

1. Is it declared directly inside the interface body, or inside another method/class?
2. If it is a direct member type, remember that `public static` is implicit; no enclosing interface instance is required.
3. Separately check the modifiers and access scope of constructors, fields, and methods inside the class.
4. Use the interface-qualified name, such as `Payment.Receipt`, to make it clear which type is being referenced.
5. If you add a runnable example, compile the exact file name and check the actual stdout instead of guessing the output.

## Conclusion

A member class declared directly in an interface always has the implicit modifiers `public static`. This determines the type's accessibility and how objects are instantiated, but it does not replace the normal modifier rules inside the class itself. Understanding this boundary helps make interface API design predictable and prevents errors when compiling or using nested classes.
