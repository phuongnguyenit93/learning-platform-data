# Distinguishing Loading, Linking, and Initialization of a Class or Interface in Java

When the JVM uses a Java type, the three concepts of **loading**, **linking**, and **initialization** describe different tasks. They are sequentially related, but they are not synonymous and do not necessarily all happen as soon as the program starts. Understanding the difference properly helps explain why errors can occur before or inside a `static` block, why a class has not run its initializers even though it has already been loaded, and why an interface with a default method is sometimes initialized when a class implements it.

## 1. The Big Picture

Typically, the lifecycle of a type can be described as follows:

```text
Loading
    ↓
Linking
    ├─ Verification
    ├─ Preparation
    └─ Reference Resolution
    ↓
Initialization
```

This is a general model. The JVM may defer loading a type until it is needed and may resolve certain references later than the time of initial linking. Therefore, you should not infer that every class in an application is completely loaded, linked, and initialized right at startup.

| Phase | What does the JVM do? | What does that not mean yet? |
|---|---|---|
| Loading | Finds the binary representation of the type, creates the type's representation in the JVM, and determines the responsible class loader. | Does not yet run `static` blocks or ordinary field initializers. |
| Linking | Verifies validity, prepares `static` fields, and resolves symbolic references when needed. | Does not yet execute all of the type's static initialization code. |
| Initialization | Executes `static` field assignments and `static` blocks according to Java's rules. | Not a new loading or linking step; each class or interface is initialized at most once per class identity in the JVM. |

## 2. Type Loading

Loading is the step where the JVM finds the binary data of a class or interface and creates the corresponding runtime representation. The data source is usually a `.class` file, but it can also come from a custom class loader or another source supported by the loader.

Key points to remember:

- A **class loader** is responsible for finding and loading the type. The delegation mechanism usually lets a loader query its parent loader first, but a custom loader may have its own policy.
- After loading, the JVM has information about the type and can create a `java.lang.Class` object representing that type.
- Loading does not mean running the statements inside `static { ... }`. Those statements belong to the initialization phase.
- The JVM can load types on demand. Declaring a variable of a certain type does not necessarily cause all of that type's code to be initialized immediately.
- Type identity depends on both the binary name and the class loader that defines it. Two different class loaders can define two distinct types even with the same binary name; this matters for plugins, containers, and custom-built module systems.

You can request loading a class without initializing it yet using `Class.forName(name, false, loader)`. Conversely, the standard `Class.forName(name)` overload requests initialization of the found class. Reflection and class loader calls should be chosen appropriately for the intended purpose.

## 3. Linking

Linking makes a loaded type ready for use at runtime. According to the JVM model, linking consists of three parts.

### 3.1. Verification

The JVM checks the structure and bytecode to ensure the type complies with the constraints of the class file format and the virtual machine's safety rules. For example, bytecode must have a valid structure and operations on the operand stack must be consistent.

If the type is invalid, the JVM may throw an error such as `VerifyError`. This error belongs to the verification process, unlike an exception thrown by code inside a `static` block during initialization.

### 3.2. Preparation

The JVM creates the required class fields and sets default values for `static` variables, such as:

- `int` has a default value of `0`;
- `boolean` has a default value of `false`;
- reference types have a default value of `null`.

This is not yet the time to execute Java expressions such as `static int count = calculate();` or `static` blocks. Those expressions and blocks are executed when the type is initialized. Compile-time constant fields declared with `static final` and a constant expression have their own JVM rules; you should not use them to observe initialization timing, because the constant value can be inlined directly into the caller's code.

### 3.3. Reference Resolution

Bytecode typically contains symbolic references to classes, fields, or methods. Resolution converts those references into links that the JVM can use at runtime.

The JVM may resolve references eagerly or defer resolution until a reference is used, depending on the rules and the implementation. Therefore, you should not treat the fact that a class is loaded as proof that all of its references have been fully resolved.

## 4. Initialization

Initialization is when Java initializers actually run. For a class, the JVM executes the class initialization code, which the compiler typically represents in the special `<clinit>` method. This code consists of `static` field assignments and `static` blocks, in the textual order in which they appear in the class declaration.

Example:

```java
class Example {
    static int first = printAndReturn("first", 1);

    static {
        System.out.println("static block");
    }

    static int second = printAndReturn("second", 2);

    private static int printAndReturn(String name, int value) {
        System.out.println(name);
        return value;
    }
}
```

When `Example` is initialized for the first time, the static initializers run in source-code order: printing `first`, printing `static block`, and then printing `second`. The fact that the JVM loaded or prepared the class beforehand does not change that order.

### 4.1. Operations That Commonly Trigger Class Initialization

According to Java language rules, class initialization is typically triggered before active uses such as:

- Creating an instance with `new`.
- Calling a `static` method declared by that class.
- Reading or writing a `static` field declared by that class that is not a compile-time constant variable.
- Certain reflection operations that require initialization, such as `Class.forName(name)` with the default overload.

Merely referencing a type in contexts that do not require initialization does not necessarily trigger static initializers. In particular, reading a compile-time constant variable such as `static final int LIMIT = 10;` usually does not trigger initialization of the class that declares the constant, because the compiler can inline the value `10` into the caller's code.

Another note: if a `static` method is called through a subclass name while the method is actually declared in a superclass, the class initialized follows the rule for the class declaring the method. You should not look only at the name before the dot to conclude which class will be initialized.

### 4.2. Initialization Order Among Superclasses, Interfaces, and Subclasses

When a class is initialized:

1. Its superclass is initialized first.
2. Superinterfaces of the class that declare a `default` method are initialized in the specified order, including traversing the relevant superinterfaces.
3. Then the static initializers of the class itself are executed in textual order.

The rule for interfaces has one difference: **initializing an interface does not automatically mean initializing all of its superinterfaces**. However, when initializing a class, the JVM initializes the relevant superinterfaces that declare a default method according to the rule above. Therefore, an interface with a `default` method may be initialized right before the class implementing it, even when the program has not called that default method.

## 5. Testing the Distinction Between Type Loading and Initialization (Java 17+)

This example focuses on the boundary between **knowing a type has been loaded** and **executing static initializers**. We explicitly instruct the JVM to look up the type with the no-initialization flag, and only afterward trigger initialization in a separate operation. Save this to the file `InitializationPhasesDemo.java`.

~~~java
public class InitializationPhasesDemo {
    static class Target {
        static int value = initialize();

        private static int initialize() {
            System.out.println("Target: initialized");
            return 42;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("main: before load");

        Class<?> target = Class.forName(
                "InitializationPhasesDemo$Target",
                false,
                InitializationPhasesDemo.class.getClassLoader());
        System.out.println("loaded: " + target.getSimpleName());

        System.out.println("main: before active initialization");
        Class.forName(target.getName(), true, target.getClassLoader());
        System.out.println("Target.value = " + Target.value);
    }
}
~~~

Compile and run:

~~~bash
javac InitializationPhasesDemo.java
java InitializationPhasesDemo
~~~

Example stdout:

~~~text
main: before load
loaded: Target
main: before active initialization
Target: initialized
Target.value = 42
~~~

`Class.forName(name, false, loader)` requests finding and loading the type without requiring initializer execution. Therefore, the `loaded: Target` message appears without `Target: initialized`. The `true` argument in the second call requests type initialization: at that point, the `initialize()` method runs and assigns `value = 42`. The final read of `Target.value` uses the existing value and does not re-run the initializer.

The example **does not directly measure linking**. The JVM can perform verification, preparation, and part of resolution at different times without printing traces from Java code. To distinguish loading and linking in real-world diagnostics, you need to combine the JVM specification with appropriate diagnostic tools; the `println` order alone only demonstrates when the initializer executes.

The rules for superclasses and superinterfaces declaring a `default method` during class initialization are examined in depth in the lesson on superclass and superinterface initialization. This is behavior that occurs **before the class's initializer**, and it does not change the three phases of loading, linking, and initialization being distinguished.

## 6. What Happens If Initialization Fails?

If static initialization code throws an exception that is not an `Error`, the JVM typically represents the first initialization failure with an `ExceptionInInitializerError`. If the failure itself is an `Error`, that error may be propagated directly. The class is marked as having failed initialization; subsequent uses usually encounter `NoClassDefFoundError` instead of re-running the initializer as if nothing had happened.

This explains why an error can appear the first time a class is used, even though the program compiled successfully and the class was already loaded. Compilation, bytecode verification, and running initializers are different steps, so success at one step does not guarantee success at later steps.

## 7. Common Misconceptions and How to Check

- **Confusing loading with initialization:** a class may already be loaded without its `static` blocks having run yet. Use `Class.forName(name, false, loader)` when you need to request loading without requesting initialization.
- **Assuming every class is initialized when the application starts:** the JVM can defer loading and initialization until the type is used in a way that requires it.
- **Treating linking as a single operation:** verification, preparation, and resolution serve different purposes; resolution can also be deferred.
- **Assuming interfaces and classes follow the exact same order:** initializing an interface does not automatically initialize all of its superinterfaces; whereas when initializing a class, superinterfaces that declare a `default` method are handled according to specific rules.
- **Using `static final` constants to test initialization timing:** compile-time constant variables can be inlined into the calling code, so reading them is not a reliable test.
- **Assuming an initializer failure will be retried each time:** after initialization fails, the JVM records the type's erroneous state; later uses may throw another error such as `NoClassDefFoundError`.

When diagnosing an issue, identify which operation first requires initializing the type, inspect its superclass and any interfaces with default methods, and then read the `static` assignments and `static` blocks in source-code order. Separating format/bytecode errors, linking errors, and errors inside initializers helps isolate the cause faster.

## 8. Key Takeaways

- **Loading:** finds and creates the runtime representation of the type.
- **Linking:** verifies the type, prepares fields, and resolves references when needed.
- **Initialization:** runs static initializers in the order specified by Java.
- Superclasses are initialized before subclasses; superinterfaces declaring a `default` method have special initialization rules when a class is initialized.
- Each class or interface is initialized at most once per type identity in the JVM. Loading and linking may occur earlier and are not synonymous with initialization.
