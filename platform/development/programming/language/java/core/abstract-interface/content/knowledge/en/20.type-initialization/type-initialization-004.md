# Initializing an Interface Does Not Automatically Initialize All Parent Interfaces

In Java, **initialization of a child interface does not automatically initialize its parent interfaces**. This is an important difference compared to initializing a class: before a class is initialized, the JVM initializes its superclass and any superinterfaces that declare `default` methods. This rule helps avoid running the initialization of every interface simply because another interface inherits from it.

To understand this behavior properly, distinguish between the JVM loading/checking a type and initializing a type. Initialization is the phase that executes the initializer expressions for that type's `static` variables. An interface can be used as a parent type without running its initialization yet.

## 1. Direct Initialization of an Interface

An interface is typically initialized when code first actively uses a static member declared in that interface itself, such as calling a `static` method of the interface or reading a `static` field that is not a compile-time constant. Field access is a point to pay attention to: if the field is declared in a parent interface, writing the child interface's name in front does not turn that field into a field declared by the child interface.

When a child interface is initialized, the JVM **does not need to initialize all parent interfaces first**. Therefore, simply declaring `interface Child extends Parent` does not mean that `Parent`'s initializer expressions will run when `Child` is initialized.

## 2. Compilable and Runnable Java 17+ Example

Save the following code as `InterfaceInitializationDemo.java`:

```java
public class InterfaceInitializationDemo {
    static class InitLog {
        static String mark(String name) {
            System.out.println("init " + name);
            return name;
        }
    }

    interface Parent {
        String PARENT_VALUE = InitLog.mark("Parent");

        default void inheritedDefault() {
        }
    }

    interface Child extends Parent {
        String CHILD_VALUE = InitLog.mark("Child");
    }

    static class Impl implements Child {
        static {
            System.out.println("init Impl");
        }
    }

    public static void main(String[] args) {
        System.out.println("Access Child.CHILD_VALUE");
        System.out.println(Child.CHILD_VALUE);

        System.out.println("Create Impl");
        new Impl();

        System.out.println("Access Parent.PARENT_VALUE");
        System.out.println(Parent.PARENT_VALUE);
    }
}
```

Compile and run in the directory containing the file:

```text
javac InterfaceInitializationDemo.java
java InterfaceInitializationDemo
```

Output:

```text
Access Child.CHILD_VALUE
init Child
Child
Create Impl
init Parent
init Impl
Access Parent.PARENT_VALUE
Parent
```

## 3. Explaining the Initialization Order

**Step 1 — reading `Child.CHILD_VALUE`.** This field is initialized by a call to `InitLog.mark`, so it is not a compile-time constant. Reading it triggers the initialization of `Child` and prints `init Child`. Even though `Child extends Parent`, `Parent`'s initializer expression has not run yet; initializing a child interface does not automatically initialize its parent interface.

**Step 2 — creating `Impl`.** Before the JVM initializes class `Impl`, the JVM initializes its superclass and any superinterfaces in the inheritance hierarchy that declare `default` methods. `Parent` declares `inheritedDefault`, so `Parent` is initialized first and prints `init Parent`. Then the `static` block of `Impl` runs, printing `init Impl`.

**Step 3 — reading `Parent.PARENT_VALUE`.** `Parent` was already initialized in step 2, so the expression `InitLog.mark("Parent")` does not run again. The program only prints the field value `Parent`.

This example demonstrates two different rules: initializing an interface does not entail initializing all superinterfaces; initializing a class, by contrast, can entail initializing superinterfaces that declare `default` methods before running that class's initialization.

## 4. Rules to Remember

| Scenario | What happens |
| --- | --- |
| Reading a field declared directly in `Child` that is not a compile-time constant | Can trigger initialization of `Child`; does not automatically initialize all parent interfaces. |
| Calling a `static` method declared in an interface | Triggers initialization of the interface that declares that method. Interface `static` methods are not inherited like instance methods. |
| Initializing class `Impl` | The JVM initializes its superclass and any superinterfaces that declare `default` methods according to class initialization rules before executing the class's static initializer block. |
| Reading a field declared in `Parent` via the name `Parent` | If the field is not a compile-time constant, reading it triggers initialization of `Parent` if it has not been initialized yet. |
| Reading a compile-time constant such as `int LIMIT = 100` declared in an interface | Reading the constant itself does not trigger initialization of the interface. |

Fields declared in an interface are implicitly `public static final`. However, not every `final` field is a compile-time constant. Only a field of a primitive type or `String` assigned a constant expression is a constant variable according to Java's rules. For example, `String VALUE = InitLog.mark("Child")` is not a constant expression, so reading the field will trigger initialization of the interface that declares it.

If a field declared by `Parent` is referenced through the name `Child`, remember that the field still belongs to `Parent`. When the field is not a compile-time constant, the access may trigger initialization of `Parent`; do not infer solely from the name before the dot.

## 5. Common Misconceptions

- **Assuming `extends` means initializing the parent:** the inheritance relationship determines types and members, but interface initialization has its own rules. Initializing a child interface does not automatically initialize its parent interfaces.
- **Confusing class rules with interface rules:** when initializing a class, the JVM has special handling for superinterfaces that declare `default` methods. Do not apply that rule as if every initialization of a child interface must also initialize all parents.
- **Assuming that no `static final` field triggers initialization:** that is only true for a constant variable determined by Java to be a compile-time constant. A value obtained from a method call or a computation that is not a constant expression can trigger initialization.
- **Overlooking the interface that actually declares the field:** the interface name used in the access expression is not necessarily where the field is declared. Identify which interface declares the member to understand which interface will be initialized.

## 6. How to Apply This When Debugging

When you see static initialization logs appearing in an unexpected order, identify the first operation that causes initialization: which field is read, which `static` method is called, or which class is initialized. Then check whether that field is a constant variable and which interfaces in the inheritance hierarchy declare `default` methods. Do not conclude that a parent interface has been initialized just because a child interface inherits from it.

In practical design, avoid relying on complex side effects in interface field initializer expressions. If you need to trace the order, use a small example with clear logging like the one above and verify it with a standalone program.
