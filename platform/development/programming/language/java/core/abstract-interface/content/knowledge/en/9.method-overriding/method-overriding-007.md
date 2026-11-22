# final, private, and static Methods in Java Inheritance

These three modifiers create three different relationships with subclasses. **Final** prevents overriding, **private** is not inherited to be overridden, while **static** uses method hiding instead of polymorphic dispatch based on the object.

## 1. Quick Comparison

| Superclass method type | Inherited by subclass? | Declaring the same signature in subclass |
| --- | --- | --- |
| Regular instance method | Yes, if accessible | Overrides if rules are satisfied |
| final instance method | Yes | Error if attempting to override |
| private instance method | No | Independent method, does not override |
| Inheritable static method | Yes | A corresponding static method hides it |
| Static final method | Callable according to access permissions | Cannot be hidden by a corresponding declaration |

## 2. Example: final, private, static, and Overriding

~~~java
public class MethodKindsDemo {
    static class Base {
        public final String category() { return "base"; }
        private String secret() { return "base-secret"; }
        public String reveal() { return secret(); }
        public static String kind() { return "Base"; }
        public String describe() { return "Base.describe"; }
    }

    static class Child extends Base {
        public String category(int level) { return "level-" + level; }
        public String secret() { return "child-secret"; }
        public static String kind() { return "Child"; }

        @Override
        public String describe() { return "Child.describe"; }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Base ref = child;
        System.out.println(ref.category());
        System.out.println(child.category(2));
        System.out.println(ref.reveal());
        System.out.println(child.secret());
        System.out.println(ref.kind());
        System.out.println(ref.describe());
    }
}
~~~

~~~text
base
level-2
base-secret
child-secret
Base
Child.describe
~~~

category() is final and is inherited; category(int) is a valid overload. Base.secret() is private, so Child.secret() is a separate method and does not change the call inside Base.reveal(). kind() is static, so the call through the ref variable is resolved according to the Base type. Only describe() is an instance override and dispatches to Child.

## 3. Easy-to-Forget Rules

- final on a method does not prohibit calling or inheriting that method; it prohibits overriding. final on a class prohibits subclassing.
- A method cannot be declared both abstract and final: one requires overriding to provide a body, while the other prohibits overriding.
- A private helper of the superclass can still be called from another method defined in the superclass when the actual object is a subclass. What does not happen is dispatching to a method with the same name declared by the subclass itself.
- A static method of an interface is not inherited by implementing classes. Call it using the interface name, for example Tools.version(). Private interface methods are internal helpers for methods with a body in the interface.
- If the superclass and subclass declare static/instance methods with the same signature respectively, the compiler reports an error; changing the modifier does not turn static into an override.

## 4. Using final to Control the Overall Algorithm

A common design pattern is *Template Method*: the superclass maintains the sequence using a final method and delegates a specific step to the subclass.

~~~java
abstract class Job {
    public final void run() {
        prepare();
        execute();
        finish();
    }

    private void prepare() { System.out.println("prepare"); }
    protected abstract void execute();
    private void finish() { System.out.println("finish"); }
}

final class ImportJob extends Job {
    @Override
    protected void execute() {
        System.out.println("import");
    }
}
~~~

run() fixes the order; execute() is the extension point; the private helpers are not an API for subclasses. This approach is useful when the overall process must run completely without depending on whether the subclass remembers to call super.

**Remember:** having the same name does not mean overriding. Determine the modifier, inheritability, and dispatch mechanism before concluding the relationship between two declarations.
