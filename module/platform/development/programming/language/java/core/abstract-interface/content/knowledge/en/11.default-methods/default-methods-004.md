# Overriding a default method in a Java implementing class

An implementing class can use an interface's default method as-is or override it to provide its own behavior. An override is a regular instance method in the class; it must satisfy the interface's public contract.

## 1. Using the default or replacing it

```java
public class DefaultOverrideDemo {
    interface Messenger {
        default String send(String message) {
            return "Default: " + message;
        }

        default String channel() {
            return "unspecified";
        }
    }

    static final class BasicMessenger implements Messenger {
        // Uses both default methods.
    }

    static final class EmailMessenger implements Messenger {
        @Override
        public String send(String message) {
            return "Email: " + message;
        }
    }

    public static void main(String[] args) {
        Messenger basic = new BasicMessenger();
        Messenger email = new EmailMessenger();

        System.out.println(basic.send("hello"));
        System.out.println(email.send("hello"));
        System.out.println(email.channel());
    }
}
```

Output:

```text
Default: hello
Email: hello
unspecified
```

`BasicMessenger` inherits both methods. `EmailMessenger` only overrides `send`; `channel` still comes from the interface. A reference of type `Messenger` still invokes the actual object's override according to polymorphism rules.

## 2. Rules when overriding

| Element | Requirement |
| --- | --- |
| Name and parameters | Must have a compatible override signature. `execute(int)` and `execute(long)` are two different signatures. |
| Access | Must remain `public` because an interface's default method is public. |
| Return type | Keep a compatible type; for reference types, a valid covariant return type may be used. |
| Checked exception | Do not add a checked exception broader than allowed by the overridden method's contract. |
| `static` | Cannot use a static method to override a default instance method. |
| `final` | An override in a class can be `final` to prevent subclasses from overriding it further, if the class structure permits. |

You should place `@Override` on the method. The annotation does not create polymorphism, but it helps the compiler detect an intended override with the wrong signature. A class does not write the `default` keyword before the overriding method.

The following example is incorrect because it reduces access privileges:

```java
interface Renderer {
    default String render() {
        return "default";
    }
}

class BrokenRenderer implements Renderer {
    @Override
    String render() { // Incorrect: package-private is narrower than public.
        return "hidden";
    }
}
```

Write `public String render()`. Similarly, a method with the same name but different parameters is merely an overload and does not replace the original default method.

## 3. Superclass methods and default methods

When a class or superclass has a matching concrete instance method, the method from the class takes precedence over a default method with the same signature. This is commonly called the *class wins* rule.

```java
interface Named {
    default String name() {
        return "interface";
    }
}

class BaseNamed {
    public String name() {
        return "class";
    }
}

class UserNamed extends BaseNamed implements Named {
}
```

`new UserNamed().name()` returns `class`. The variable's declared type does not make the default method win over the method inherited from the class. Cases where a class has an abstract method or an incompatible signature/access must be evaluated according to Java's overriding rules, and cannot be concluded merely from the two names being the same.

## 4. When to override?

Override when the default does not meet the class's business requirements, when you need to add pre-/post-processing, or when you need to resolve inheritance conflicts. If you only want to call the default method and return the result unchanged, overriding usually adds no value. The syntax for directly calling a specific default implementation has its own conditions and is explained in the article on `InterfaceName.super`.

**Remember:** use `@Override public` with a compatible signature. A class can override some default methods and inherit the remaining ones; a class's instance method takes precedence in selecting the implementation according to Java's inheritance rules.
