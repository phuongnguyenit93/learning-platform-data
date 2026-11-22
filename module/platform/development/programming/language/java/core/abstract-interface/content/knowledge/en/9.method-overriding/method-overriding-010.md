# Calling the Superclass Implementation with super When Overriding Methods in Java

In an override, a normal instance call such as this.run() can route back to the override itself. **super.run()** instructs Java to invoke the implementation looked up via the superclass, allowing the subclass to reuse the base logic and then extend it. super does not create a separate parent object: the call still executes on the same subclass object.

## 1. Example: A Superclass Calling an Overridable Hook

~~~java
public class SuperDispatchDemo {
    static class Parent {
        void run() {
            System.out.println("Parent.run");
            hook();
        }

        void hook() {
            System.out.println("Parent.hook");
        }
    }

    static class Child extends Parent {
        @Override
        void run() {
            System.out.println("Child.before");
            super.run();
            System.out.println("Child.after");
        }

        @Override
        void hook() {
            System.out.println("Child.hook");
        }
    }

    public static void main(String[] args) {
        new Child().run();
    }
}
~~~

~~~text
Child.before
Parent.run
Child.hook
Child.after
~~~

super.run() invokes the body of Parent.run(). However, the hook() call inside that body is still a normal instance call on the same Child object, so it dispatches to Child.hook(). Therefore, super only binds the current call; it does not disable dynamic dispatch for all calls originating inside the superclass.

## 2. When to Use super?

Use super.method(...) when the contract requires preserving the parent behavior, such as adding before/after logging, extending the result, or performing cleanup. Not every override needs to call super: if the subclass replaces the algorithm completely, calling the superclass can produce unintended side effects.

A few points to remember:

- If the immediate superclass does not override the method, super.method() can invoke the implementation inherited from an ancestor.
- There is no super.super.method() syntax to arbitrarily bypass intermediate classes.
- You cannot call an abstract method body via super, because that method has no implementation.
- super does not bypass access rules and cannot be used to call a parent's private helper.
- super(...) calls a superclass constructor; super.method(...) calls a method. These are two different syntaxes.

## 3. Interface Default Methods

When you want to reuse a default method from a superinterface, the syntax is **InterfaceName.super.method()** in contexts permitted by Java.

~~~java
interface Greeter {
    default String greet(String name) {
        return "Hello, " + name;
    }
}

final class FriendlyGreeter implements Greeter {
    @Override
    public String greet(String name) {
        return Greeter.super.greet(name) + "!";
    }
}
~~~

Greeter.super.greet(name) invokes the interface's default method body and then appends an exclamation mark. When a class inherits two conflicting default methods from unrelated interfaces and has no suitable concrete implementation from a superclass, the class must override the method itself to resolve the conflict. If one interface extends the other and overrides the default method, the subinterface's version can be selected without needing an override in the class. In an override, `InterfaceName.super.method()` is valid only for a superinterface that satisfies Java's rules; you cannot arbitrarily choose any ancestor. A concrete method inherited from a superclass takes precedence over an interface default method.

## 4. Exceptions and Side Effects

A super.method() call is subject to the same return value and exception handling rules as a normal method call. If the superclass throws a checked exception, the override needs to catch or declare it appropriately; if calling the superclass causes state changes, logging, or I/O, the subclass must consider the ordering and avoid duplicate execution.

When a superclass requires a common process to run in the proper sequence, *Template Method* can be used: a final method orchestrates the process and calls hooks overridden by subclasses. This approach reduces dependence on whether each subclass remembers to call super.

**Remember:** super selects the superclass implementation for the current call; instance hooks that this implementation subsequently invokes can still dispatch to the subclass. Trace the entire call path, exceptions, and side effects when debugging an override.
