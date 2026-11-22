# Method Signatures and Overriding Conditions in Java

Overriding (*method overriding*) allows a subclass to provide its own implementation for an inherited instance method or an interface contract. When a call is made through a parent type, Java can select the subclass body at runtime. To determine a valid override, it is first necessary to distinguish the **method signature** from the entire method declaration.

## 1. What Does a Method Signature Consist Of?

According to the Java Language Specification, a signature is primarily determined by the method name, the type parameters of a generic method, and the types of the formal parameters in order. With generics, type specialization and the *subsignature* relationship can affect whether two declarations correspond.

| Declaration Element | Distinguishes Signature? | Notes |
| --- | --- | --- |
| Method name | Yes | read and load are different. |
| Number, order, and types of parameters | Yes | find(String) differs from find(Object). |
| Parameter variable names | No | send(String text) and send(String message) have the same signature. |
| Return type | No | Changing only the return type does not create an overload. |
| Modifiers such as public, final, static | No | Can affect the validity of an override. |
| throws clause | No | Must still comply with exception rules when overriding. |
| String... versus String[] | No | Varargs uses an array type as the parameter type. |

A JVM *method descriptor* contains the return type, but that is a bytecode concept distinct from the Java source signature used when evaluating overloads.

## 2. Basic Conditions of an Override

A declaration in a subclass must satisfy the following main conditions:

1. There is an appropriate inheritance or interface implementation relationship; the method must actually be allowed to be inherited/overridden.
2. The name and parameter type list must form a corresponding signature according to Java rules.
3. The return type must be compatible. Primitives must retain the same type; reference types may use a subtype in the case of covariant return.
4. The access level must not be narrowed compared to the overridden method.
5. Checked exceptions must not be broadened in a way the parent contract does not allow.
6. A final method cannot be overridden; static uses the hiding mechanism, while private is not inherited to be overridden.
7. A concrete subclass must implement the abstract methods still in effect.

The following lessons focus individually on each group of rules: distinguishing override/overload/hiding, visibility, return type, exceptions, modifiers, annotations, varargs, and super calls.

## 3. Runnable Example: Reference Type and Actual Object

~~~java
public class OverrideBasics {
    public static void main(String[] args) {
        Message parentView = new DetailedMessage();
        System.out.println(parentView.text());
        System.out.println(parentView.describe());
    }
}

class Message {
    public String text() {
        return "base";
    }

    public String describe() {
        return "Message: " + text();
    }
}

class DetailedMessage extends Message {
    @Override
    public String text() {
        return "child";
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac OverrideBasics.java
java OverrideBasics
~~~

Output:

~~~text
child
Message: child
~~~

The variable parentView has the declared type Message, so the compiler checks calls against the API visible on that type. The actual object is DetailedMessage, so the instance call text() dispatches to the override. Even the inherited Message.describe() calls DetailedMessage.text() when running on this object.

## 4. How to Avoid an Override Accidentally Becoming a New Method

If the superclass has process(String) and the subclass writes process(Object), that is usually an overload, not an override. The program may still compile, but a call through the parent type does not select the new method just because the actual object is a subclass.

Use @Override on methods intended to override. If the signature does not match, the compiler will report an error instead of letting that mismatch silently exist.

**Remember:** the signature determines which method is being compared; the rules on inheritance, return type, access level, checked exceptions, and modifiers decide whether that declaration is a valid override.
