# Turning a default method into an abstract requirement in a subinterface

A subinterface can redeclare a parent interface's default method as a method without a body. That declaration is `public abstract` by default and requires types implementing the subinterface to have a suitable implementation.

## 1. Syntax and meaning

```java
interface Greeting {
    default String greet(String name) {
        return "Hello, " + name;
    }
}

interface FormalGreeting extends Greeting {
    @Override
    String greet(String name); // public abstract
}
```

This is **re-abstraction** (*re-abstracting a default method*). It does not remove the body of `Greeting.greet` from the parent interface; it changes the contract of the `FormalGreeting` branch. Classes that only implement `Greeting` can still use the original default.

To re-abstract, the subinterface must have an inheritance relationship with the interface declaring the default, redeclare the method with a valid overriding signature without writing a body or the `default` keyword. Writing `public abstract` explicitly is also valid, but not required.

## 2. Complete example

```java
public class ReabstractDemo {
    interface Greeting {
        default String greet(String name) {
            return "Hello, " + name;
        }

        default String farewell(String name) {
            return "Goodbye, " + name;
        }
    }

    interface FormalGreeting extends Greeting {
        @Override
        String greet(String name);
    }

    static final class BasicGreeting implements Greeting {
    }

    static final class CorporateGreeting implements FormalGreeting {
        @Override
        public String greet(String name) {
            return "Dear " + name;
        }
    }

    public static void main(String[] args) {
        Greeting basic = new BasicGreeting();
        FormalGreeting formal = new CorporateGreeting();

        System.out.println(basic.greet("An"));
        System.out.println(formal.greet("An"));
        System.out.println(((Greeting) formal).greet("An"));
        System.out.println(formal.farewell("An"));
    }
}
```

Output:

```text
Hello, An
Dear An
Dear An
Goodbye, An
```

Casting the `formal` reference to `Greeting` does not reselect the parent's default body. The actual object is still `CorporateGreeting`, so dynamic dispatch invokes the class's `greet` implementation. The `farewell` method is not redeclared, so it remains the inherited default.

## 3. What does an implementing class need to do?

A concrete class needs a suitable `public` instance method. It can declare the method directly or inherit a valid public implementation from a superclass. Therefore, re-abstraction does not mean every class always has to rewrite the method if the class already has an implementation that satisfies the contract.

```java
abstract class GreetingBase {
    public String greet(String name) {
        return "Base: " + name;
    }
}

final class InheritedGreeting extends GreetingBase
        implements FormalGreeting {
    // The public greet(String) method from the superclass satisfies the contract.
}
```

The snippet above assumes `FormalGreeting` is declared as in the previous example. `InheritedGreeting` does not need to override `greet` itself because the concrete method inherited from the superclass has a matching signature.

Access cannot be reduced to package-private, `protected`, or `private`. The overriding rules for return types and checked exceptions also continue to apply.

## 4. When should you use it?

Re-abstraction is useful when the parent interface has a default that is good enough for most cases, yet a specialized branch needs to require specific behavior. For example, `SecureStorage` can redeclare `validate()` as abstract if the simple default of `Storage` does not satisfy that branch's security contract.

Only do this when there is no single reliable default for the entire branch. If the subinterface can provide a new default that is correct for every implementation, that option may be simpler. Re-abstraction checks for the existence of an implementation at the language level; it does not prove that the implementation's business logic is correct.

## 5. Common mistakes

- Writing `default String greet(String name);` without a body: invalid because a default method must have a body.
- Assuming you must write the `abstract` keyword: unnecessary; declaring `String greet(String name);` in an interface is already implicitly public abstract.
- Assuming the parent interface loses the default method: incorrect; the change only applies to the child branch.
- Assuming every class must declare the method directly: not always true if a superclass already provides a suitable public implementation.
- Redeclaring a static method or a method without an overriding relationship: this is not re-abstracting a default method.

## Self-check

1. In `interface Child extends Parent { void act(); }`, is the `act()` declaration abstract or default?
2. If a concrete class does not have a suitable implementation, will compilation succeed?
3. Why does casting an implementing object to the parent interface not invoke the original default again?
4. Is another default method of the parent interface affected?

**Remember:** A subinterface can turn a default method into an abstract requirement by redeclaring the method without a body. An implementing class needs a suitable public implementation, either directly or inherited from a superclass.
