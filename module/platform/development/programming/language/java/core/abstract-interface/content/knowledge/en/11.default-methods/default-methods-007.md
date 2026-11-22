# Calling a default method using InterfaceName.super in Java

When you override a default method but want to reuse the interface's exact body, Java provides the `InterfaceName.super.method(arguments)` syntax. It is useful for extending a default behavior or explicitly choosing between conflicting default methods.

## 1. Distinguishing the three call forms

| Syntax | Meaning |
| --- | --- |
| `this.method()` or `method()` | Calls the method on the current object according to normal dispatch rules. |
| `super.method()` | Looks up the implementation via the superclass branch. |
| `InterfaceName.super.method()` | Specifies a default implementation from a suitable superinterface. |

`InterfaceName.super` is not a variable or an object that can be stored in a reference. It is a special Java syntax, used only in a valid context and with a callable default implementation.

## 2. Extending a default method

```java
public class InterfaceSuperDemo {
    interface Greeting {
        default String sayHello(String name) {
            return "Xin chào, " + name;
        }
    }

    static final class FriendlyGreeting implements Greeting {
        @Override
        public String sayHello(String name) {
            String base = Greeting.super.sayHello(name);
            return base + "!";
        }
    }

    public static void main(String[] args) {
        Greeting greeting = new FriendlyGreeting();
        System.out.println(greeting.sayHello("Lan"));
    }
}
```

Output:

```text
Xin chào, Lan!
```

`FriendlyGreeting` calls the default body to create the greeting, then adds an exclamation mark. If you write `return sayHello(name) + "!";` inside this override itself, the method will call itself and recurse until `StackOverflowError`. A qualified super call avoids that.

## 3. Choosing between two default methods

```java
public class DefaultConflictDemo {
    interface Left {
        default String source() { return "Left"; }
    }

    interface Right {
        default String source() { return "Right"; }
    }

    static final class Combined implements Left, Right {
        @Override
        public String source() {
            return Left.super.source() + " + " + Right.super.source();
        }
    }

    public static void main(String[] args) {
        System.out.println(new Combined().source());
    }
}
```

The output is `Left + Right`. Two independent interfaces provide the same signature, so the class must override the method to resolve the conflict. The override can choose one side, combine both, or write new logic; the order of interfaces in `implements` does not create precedence.

## 4. A subinterface can also call its parent's default method

```java
interface Parent {
    default String label() {
        return "parent";
    }
}

interface Child extends Parent {
    @Override
    default String label() {
        return Parent.super.label() + "/child";
    }
}
```

`Child` can call `Parent.super.label()` because `Parent` is a direct superinterface of `Child`. When a class implements `Child` without overriding the method, it receives `Child`'s new default.

## 5. Conditions to remember

- The called method must have a suitable default implementation; you cannot call a purely abstract method.
- The call must be in a valid instance context, not in a static method.
- The interface qualifier must match the superinterface relationship at the call site. You cannot arbitrarily call any interface that the object can be cast to.
- Static methods of an interface are called using the interface name, not `InterfaceName.super`.
- A qualified super call does not allow bypassing all inheritance rules or arbitrarily calling an implementation that has been replaced in a more specific branch.

The subtle conditions regarding direct superinterfaces, intermediate interfaces, and more specific branches are analyzed separately in the article on the restrictions of calling super through a direct interface.

**Remember:** `InterfaceName.super.method()` explicitly specifies a default implementation within the scope Java allows. Use it inside an override when you need to extend behavior or resolve conflicts; do not confuse it with a class's `super.method()`.
