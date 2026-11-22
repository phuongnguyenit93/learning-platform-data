# Operations That Trigger Class Initialization in Java

## 1. The Problem: When Does a `static` Block Actually Run?

In Java, a class can be **known, loaded, or linked** before the JVM **initializes** that class. Therefore, just because source code mentions a class name **does not mean** the class's static field initializers and static initialization blocks have run.

Consider the class:

```java
class Example {
    static int number = initialize();

    static int initialize() {
        System.out.println("Example initialized");
        return 42;
    }

    static void hello() {
        System.out.println("hello");
    }
}
```

Different operations with `Example` can have different meanings:

- `Example.class`: obtains a `Class` object, **does not by itself trigger initialization of `Example`**.
- `new Example[3]`: creates a **reference array**, **does not by itself initialize `Example`**.
- `Example.hello()`: calls a static method declared in `Example`, **triggering initialization of `Example` before entering `hello`** if the class has not yet been initialized.
- `new Example()`: creates an instance, **triggering class initialization before executing the instance creation process**.
- `Example.number`: reads a non-constant static field declared in `Example`, **triggering class initialization** before reading.
- `Class.forName("Example")`: under the usual single-argument overload, **requires class initialization** when found successfully.

**Foundational rule:** class initialization typically occurs on the **first active use** under Java's defined conditions, not whenever the JVM encounters just any text resembling a class name.

This article is for **Java core, Java 17+**. The examples focus on classes running on the standard classpath; when custom class loaders, modules, interfaces, or reflection are involved, the additional explicitly noted context must be considered.

## 2. Loading, Linking, and Initialization Are Not a Single Phase

According to the Java Virtual Machine model, the process of preparing to use a class is commonly described as:

1. **Loading:** The JVM finds the representation of the class and creates the corresponding runtime information.
2. **Linking:** includes **verification**, **preparation**, and **resolution**. Resolution may occur according to an appropriate strategy of the JVM, not necessarily completing everything all at once.
3. **Initialization:** runs the **class initialization method** (`<clinit>` at the JVM level when there is content to initialize) to execute static field initializers and static initializer blocks according to the rules.

Conceptual diagram:

```text
Class requested / referenced
            |
            v
         Loading
            |
            v
         Linking
   (verify / prepare /
       resolve ...)
            |
            v
Does an operation require
   class initialization?
      /             \
     / no            \ yes
    v                 v
static initializers   Initialization
   not yet run              |
                            v
                    Continue operation
```

**Preparation** can assign JVM-level default values to static fields before the initializers in source run. For example, the static field `int count = 10` initially has a prepared state corresponding to the default value `0`; only at class initialization does the initializer set it to `10`.

**Do not confuse:** “loaded” does not mean “static block has run.” The JVM is permitted to load, verify, or resolve a class at an appropriate time provided it respects the observable semantics required by the specification.

### `<clinit>` Differs from Constructor `<init>`

- `<clinit>` is a special JVM-level name for **class/interface initialization**, not a Java source method that you declare or call yourself.
- An object's constructor corresponds to the instance initialization process and the special `<init>` methods.
- `new SomeClass()` may trigger **class initialization** first, and then **instance/constructor initialization**.
- `SomeClass.staticMethod()` may trigger **class initialization**, but **does not create an instance** and does not call the constructor of SomeClass.

## 3. Quick Reference Table: Important Operations

| Operation | Triggers initialization of the target class if not yet initialized? | Conditions / notes |
| --- | --- | --- |
| `new Target()` | **Yes** | Initializes the corresponding class before the instance creation process |
| `Target.staticMethod()` | **Yes** | When that static method is declared in Target; see the issue with inherited methods |
| Reading `Target.staticField` | **Yes**, if the field is declared in Target and **is not a constant variable** | Compile-time constants are an important exception |
| Assigning `Target.staticField = value` | **Yes** | Using the static field must satisfy access permissions / not be final |
| `Target.CONSTANT` | **Usually no**, if `CONSTANT` is a **constant variable** | `static final` primitive/String with a constant expression per JLS rules |
| `Target.class` | **No** | Obtaining a class literal does not by itself run static initializers |
| `new Target[5]` | **No** | Creating an array does not create `Target` elements |
| `Target[] refs = new Target[5]` | **No** | Reference array slots default to null |
| `Class.forName("Target")` | **Yes**, under the usual single-argument overload | Finds and initializes the class upon success |
| `Class.forName(name, false, loader)` | **Does not require initialization** | `false` means deferring initialization |
| `ClassLoader.loadClass(name)` | **Does not by itself require initialization** | Subsequent use of the class may trigger it |
| Importing a class/static member name | **No** | An import is a source declaration used at compile time |
| Declaring a variable `Target value;` | **No** | No active use operation yet |
| Casting or `instanceof Target` | **Does not by itself require initialization of Target** | May require loading/linking |
| Calling a constructor/reading a field via reflection | **Possibly yes** | Specific reflective operations have their own rules |
| `Class.getDeclaredMethods()` | **Not a default “initialize class” command** | Inspecting metadata differs from invoking a method |
| Running an application with an entry class | **Yes** | The JVM initializes the entry class before executing main per the rules |

The table refers to **initialization of the target class**, and does not rule out that an operation may trigger **another class** due to argument evaluation, auxiliary object creation, dependent static initializers, or other valid work performed by the JVM.

## 4. Triggering with `new`: Creating an Object Requires the Class to Be Initialized

Create the file **`NewTriggerDemo.java`**:

```java
class Widget {
    static {
        System.out.println("Widget: static init");
    }

    {
        System.out.println("Widget: instance block");
    }

    Widget() {
        System.out.println("Widget: constructor");
    }
}

public class NewTriggerDemo {
    public static void main(String[] args) {
        System.out.println("main begins");

        Widget first = new Widget();
        Widget second = new Widget();

        System.out.println(first != second);
    }
}
```

Run:

```bash
javac NewTriggerDemo.java
java NewTriggerDemo
```

Output:

```text
main begins
Widget: static init
Widget: instance block
Widget: constructor
Widget: instance block
Widget: constructor
true
```

Explanation in order:

1. `main` prints `main begins`.
2. On the first execution of `new Widget()`, the JVM ensures `Widget` is initialized before proceeding with instance creation. The static block prints **once**.
3. Next, the instance initialization block runs, followed by the constructor body for the first object.
4. The second `new Widget()` **does not re-run the static block** of the same runtime class that has already been successfully initialized, yet still runs the instance block and constructor for the **second object**.
5. The two references `first` and `second` point to two different objects, so `first != second` is `true`.

**Important:** static initialization is work tied to the **runtime class**, not work repeated every time an object is created.

## 5. Calling a Static Method Can Trigger Class Initialization

Create the file **`StaticMethodTriggerDemo.java`**:

```java
class Service {
    static {
        System.out.println("Service: static init");
    }

    static void work() {
        System.out.println("Service: work");
    }

    Service() {
        System.out.println("Service: constructor");
    }
}

public class StaticMethodTriggerDemo {
    public static void main(String[] args) {
        System.out.println("before first call");

        Service.work();
        Service.work();

        System.out.println("after calls");
    }
}
```

```bash
javac StaticMethodTriggerDemo.java
java StaticMethodTriggerDemo
```

```text
before first call
Service: static init
Service: work
Service: work
after calls
```

- The static block runs before the body of `Service.work()` on the first call.
- The `work` method **still executes on every call**; only class initialization is not repeated after succeeding.
- There is no `new Service()` in the program; therefore, the constructor **does not run**.

**Do not mistakenly conclude that** “a static method runs only once” or “a static method automatically creates a singleton.” It is simply one of the operations that can **trigger the class initialization process** when needed.

### Inherited Static Methods: Look at Where They Are Actually Declared

If:

```java
class Base {
    static void ping() {
        System.out.println("Base ping");
    }
}

class Child extends Base {
}
```

`Child.ping()` can compile, but `ping` is a method **declared in Base**. According to class initialization rules, that static member call targets the **class that declares the member**; you must not infer from the source text `Child.ping()` that `Child` is necessarily initialized as well.

Therefore, you should write `Base.ping()` to clearly indicate the declaration source when the code does not intentionally rely on static member inheritance.

## 6. Reading or Writing a Non-Compile-Time-Constant Static Field

Create the file **`StaticFieldTriggerDemo.java`**:

```java
class Settings {
    static int level = initialize();

    static int initialize() {
        System.out.println("Settings: initializing");
        return 3;
    }
}

public class StaticFieldTriggerDemo {
    public static void main(String[] args) {
        System.out.println("before read");
        System.out.println("level=" + Settings.level);

        Settings.level = 9;
        System.out.println("updated=" + Settings.level);
    }
}
```

```bash
javac StaticFieldTriggerDemo.java
java StaticFieldTriggerDemo
```

```text
before read
Settings: initializing
level=3
updated=9
```

- `Settings.level` is a static field that **is not a constant variable**, so reading it triggers initialization of `Settings`.
- During initialization, `initialize()` is called to assign `level=3`.
- Reading after assigning `Settings.level=9` simply sees the new value; the initializer does not run again.

### Writing a Static Field Can Also Trigger Initialization

If the first operation is:

```java
Settings.level = 9;
```

when `Settings` has not yet been initialized, the JVM must ensure the class is initialized before performing the write operation according to the rules. Therefore, the initializer may set level to 3 first, and then the **caller's assignment** replaces it with 9.

**Note:** this is a static field declared in `Settings`. If you access an inherited static field through a subclass name, the rule for the class **that declares the field** is the key, not just the name written before the dot.

## 7. Crucial Exception: `static final` Compile-Time Constants May Not Initialize the Class

A **constant variable** in Java must satisfy conditions on both its type and initializer:

- The variable has a **primitive** type or `String`.
- It is declared `final`.
- It is initialized with a **constant expression** according to the Java Language Specification rules.

For a static field:

```java
class Constants {
    static final int LIMIT = 100;
    static final String TITLE = "Java";

    static {
        System.out.println("Constants initialized");
    }
}
```

When the expressions `Constants.LIMIT` and `Constants.TITLE` are used as constants according to Java source semantics, they **are not operations that require initializing `Constants`**. The compiler can inline the constant values into the client code.

Create the file **`ConstantVariableDemo.java`**:

```java
class Constants {
    static final int LIMIT = 100;
    static final String TITLE = "Java Core";

    static {
        System.out.println("Constants: initialized");
    }

    static void ping() {
        System.out.println("Constants: ping");
    }
}

public class ConstantVariableDemo {
    public static void main(String[] args) {
        System.out.println(Constants.LIMIT);
        System.out.println(Constants.TITLE);
        System.out.println("before ping");

        Constants.ping();
    }
}
```

```bash
javac ConstantVariableDemo.java
java ConstantVariableDemo
```

```text
100
Java Core
before ping
Constants: initialized
Constants: ping
```

The two constant reads **do not cause the `Constants: initialized` line to appear**. Only when calling the static method `ping` does the class need to be initialized and the static block print.

**Do not confuse “has `static final`” with “is a compile-time constant.”** Only declarations that satisfy all `constant variable` conditions exhibit this exceptional behavior.

## 8. `static final` with a Runtime Initializer Still Triggers Class Initialization

Compare:

```java
static final int FIXED = 42;
static final int COMPUTED = Integer.parseInt("42");

static final String LITERAL = "hello";
static final String RUNTIME = new String("hello");
```

This is a **fragment of field declarations inside a class**:

- `FIXED` is a final `int` with a constant expression → **constant variable**.
- `COMPUTED` uses a method call → **not a constant variable** even though the result is 42.
- `LITERAL` is a final String assigned a literal → **constant variable**.
- `RUNTIME` uses `new String(...)` → **not a constant variable** even though the text value is identical to the literal.
- A static final reference to a `List`, array, `Integer`, or other object **cannot be a constant variable** by the primitive/String type definition, even when the entity is designed to be immutable.

### Runnable Example: Two static final Fields with Different Triggers

File **`NonConstantStaticFinalDemo.java`**:

```java
class Data {
    static final int COMPILE_TIME = 7;
    static final int RUNTIME = makeRuntime();

    static int makeRuntime() {
        System.out.println("Data: initializing runtime value");
        return 11;
    }
}

public class NonConstantStaticFinalDemo {
    public static void main(String[] args) {
        System.out.println("constant=" + Data.COMPILE_TIME);
        System.out.println("before runtime read");
        System.out.println("runtime=" + Data.RUNTIME);
    }
}
```

```bash
javac NonConstantStaticFinalDemo.java
java NonConstantStaticFinalDemo
```

```text
constant=7
before runtime read
Data: initializing runtime value
runtime=11
```

Reading `Data.COMPILE_TIME` does not yet initialize `Data`. Reading `Data.RUNTIME` requires class initialization, causing the static field initializer to call `makeRuntime()`.

### `String` Constant Concatenation Can Still Be a Compile-Time Constant

```java
static final String MESSAGE = "Java" + " Core";
```

Because the concatenation expression above is a **constant expression**, `MESSAGE` can be a constant variable. You cannot assume that whenever the `+` operator appears, the result must be computed at runtime; check Java's constant expression rules.

Conversely:

```java
static final String MESSAGE = System.getProperty("app.title");
```

is a runtime initializer, not a constant variable.

## 9. The Class Literal `SomeType.class` Does Not by Itself Run Static Initializers

File **`ClassLiteralDemo.java`**:

```java
class Passive {
    static {
        System.out.println("Passive: initialized");
    }

    static void activate() {
        System.out.println("Passive: activate");
    }
}

public class ClassLiteralDemo {
    public static void main(String[] args) {
        System.out.println("before literal");

        Class<Passive> type = Passive.class;
        System.out.println("class=" + type.getSimpleName());

        System.out.println("before active use");
        Passive.activate();
    }
}
```

```bash
javac ClassLiteralDemo.java
java ClassLiteralDemo
```

```text
before literal
class=Passive
before active use
Passive: initialized
Passive: activate
```

- `Passive.class` obtains `Class<Passive>`, but **does not by itself initialize `Passive`**.
- `type.getSimpleName()` retrieves the type name information; in this case, running Passive's static initializer is not needed.
- `Passive.activate()` is a call to a static method declared in Passive, so it triggers the initializer before the method call.

**Distinction:** `SomeType.class` does not mean **not loading/storing metadata**. It simply **is not a request to initialize the class**. The JVM may still perform the necessary class loading/linking steps.

## 10. Creating an Array of a Class Type Does Not Create Individual Objects

An easily misunderstood behavior:

```java
Target[] items = new Target[3];
```

This statement creates an **array object with three reference slots**, without automatically calling `new Target()` for each element. Initially, all slots contain `null`.

At the same time, merely creating an array with component type `Target` does not by itself require `Target` class initialization.

File **`ArrayDoesNotInitializeDemo.java`**:

```java
class Component {
    static {
        System.out.println("Component: class initialized");
    }

    Component() {
        System.out.println("Component: constructor");
    }
}

public class ArrayDoesNotInitializeDemo {
    public static void main(String[] args) {
        System.out.println("creating array");
        Component[] components = new Component[2];

        System.out.println("length=" + components.length);
        System.out.println("first null=" + (components[0] == null));

        components[0] = new Component();
        System.out.println("second null=" + (components[1] == null));
    }
}
```

```bash
javac ArrayDoesNotInitializeDemo.java
java ArrayDoesNotInitializeDemo
```

```text
creating array
length=2
first null=true
Component: class initialized
Component: constructor
second null=true
```

Explanation:

1. `new Component[2]` only creates the array; it does not initialize class Component via this trigger.
2. `components[0] == null` is true because no element object has been created yet.
3. `components[0] = new Component()` creates an instance, thus triggering Component initialization if it has not yet occurred, and then the constructor runs.
4. `components[1]` remains null.

**Advanced note:** an array has its own runtime class managed by the JVM, but that is **not** static initialization of the class used as the element type.

## 11. Class Loading with Reflection: `Class.forName`

Reflection can be used to locate classes or invoke members at runtime. Some APIs **require initializing the class**, while others do not.

### `Class.forName(String)`

For a class on the classpath that can be found by the appropriate loader, the overload:

```java
Class<?> type = Class.forName("LoadedByName");
```

normally requires **loading, linking, and initializing** the named class. It can cause static initializers to run even when no static method has been called and no instance has been created.

### `Class.forName(String, boolean, ClassLoader)`

The overload:

```java
Class<?> type = Class.forName(
        "LoadedByName", false, someLoader);
```

allows specifying `initialize=false`, meaning **class initialization is not requested at that time**. If an active use occurs later, the class can still be initialized.

### Runnable Example Demonstrating the Difference

File **`ReflectionInitializationDemo.java`**:

```java
class ReflectionTarget {
    static {
        System.out.println("ReflectionTarget: initialized");
    }

    static void run() {
        System.out.println("ReflectionTarget: run");
    }
}

public class ReflectionInitializationDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("before false");

        ClassLoader loader =
                ReflectionInitializationDemo.class.getClassLoader();

        Class<?> type =
                Class.forName("ReflectionTarget", false, loader);

        System.out.println("loaded=" + type.getSimpleName());
        System.out.println("before default forName");

        Class.forName("ReflectionTarget");

        System.out.println("after default forName");
        ReflectionTarget.run();
    }
}
```

```bash
javac ReflectionInitializationDemo.java
java ReflectionInitializationDemo
```

```text
before false
loaded=ReflectionTarget
before default forName
ReflectionTarget: initialized
after default forName
ReflectionTarget: run
```

The files are in the **default package**, and the class loader can locate `ReflectionTarget` on the classpath when run as shown above.

- `Class.forName(..., false, loader)` does not yet require initialization.
- `Class.forName("ReflectionTarget")` triggers initialization at the time it is called if it has not been initialized previously.
- `ReflectionTarget.run()` does not cause the static block to run again.

**Do not confuse “already having a Class object” with “having initialized the class.”** Class metadata and initialization state are two different concepts.

## 12. `ClassLoader.loadClass` Does Not Mean Initialization

`ClassLoader.loadClass(name)` essentially performs a request to **load the class**; it **does not by itself request executing the static initializers** of the target class as the single-argument `Class.forName(name)` typically does.

Illustrative example:

```java
ClassLoader loader = MyType.class.getClassLoader();
Class<?> type = loader.loadClass("MyType");
```

This is a **code snippet** that needs to be placed in an environment that has the `MyType` class and handles checked exceptions. Obtaining `MyType.class` to get the loader also does not by itself initialize MyType.

However:

- A custom class loader may perform its own actions depending on its implementation.
- The JVM may load a class earlier or resolve dependencies at a different time.
- **Subsequent active uses** of the class still trigger initialization according to the rules.

**Accurate conclusion:** class-loading APIs and class-initialization-requesting APIs are two different things; do not equate `loadClass` with calling a constructor or static initializer.

## 13. Retrieving Metadata via Reflection Differs from Calling a Method or Reading a Field

Suppose we have:

```java
class Probe {
    static {
        System.out.println("Probe: initialized");
    }

    public static void execute() {
        System.out.println("Probe: execute");
    }
}
```

Operations that only retrieve information such as `Probe.class`, `getName()`, or `getDeclaredMethods()` **do not by default carry the same active execution semantics** as `Probe.execute()`.

Meanwhile, reflection that **actually invokes a static method** through `Method.invoke` or accesses a static field via reflection APIs may require initialization according to the API's rules.

### Java 17+ Example Using Reflection to Call a Static Method

File **`ReflectiveInvocationDemo.java`**:

```java
import java.lang.reflect.Method;

class Probe {
    static {
        System.out.println("Probe: initialized");
    }

    public static void execute() {
        System.out.println("Probe: execute");
    }
}

public class ReflectiveInvocationDemo {
    public static void main(String[] args) throws Exception {
        Class<Probe> type = Probe.class;

        System.out.println("before method lookup");
        Method method = type.getDeclaredMethod("execute");

        System.out.println("before invoke");
        method.invoke(null);
    }
}
```

```bash
javac ReflectiveInvocationDemo.java
java ReflectiveInvocationDemo
```

```text
before method lookup
before invoke
Probe: initialized
Probe: execute
```

- `Probe.class` and `getDeclaredMethod` only retrieve type/method information.
- `method.invoke(null)` executes the static method; a `null` receiver argument is valid when invoking a static method via reflection.
- At execution time, Probe is initialized before the method body, so the static message is printed before `Probe: execute`.

Do not assume that **all reflective APIs** are the same. For example, `Constructor.newInstance`, `Field.get`/`set` for static fields, and the method handles mechanism each have their own rules. When using reflection for a framework, you need to read the specific contract of the relevant method.

## 14. When a Subclass Initializes, the Superclass Normally Initializes First

A subclass cannot complete normal class initialization without first handling the superclass initializations required before it.

Example:

File **`SuperclassInitializationDemo.java`**:

```java
class Base {
    static {
        System.out.println("Base: static init");
    }

    Base() {
        System.out.println("Base: constructor");
    }
}

class Child extends Base {
    static {
        System.out.println("Child: static init");
    }

    Child() {
        System.out.println("Child: constructor");
    }
}

public class SuperclassInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before new Child");
        new Child();
    }
}
```

```bash
javac SuperclassInitializationDemo.java
java SuperclassInitializationDemo
```

```text
before new Child
Base: static init
Child: static init
Base: constructor
Child: constructor
```

Explanation:

1. `new Child()` requires class Child to be initialized.
2. Before initialization of Child completes, the JVM ensures **Base** is initialized according to the superclass relationship.
3. Base's static initializer prints before Child's static initializer.
4. After the class initialization phase, the object creation process calls the Base constructor part before the Child constructor part.

Therefore, **class initialization order** and **instance constructor order** are both related to inheritance, yet they are **two distinct sequences of operations**.

### Avoiding the Reverse Conclusion

Reading a static field of `Base` does not by itself force initialization of `Child` just because Child extends Base. A subclass may remain uninitialized even though its superclass has been initialized.

## 15. Accessing a Static Field Declared in a Superclass via a Subclass Name

This is a counterintuitive scenario:

```java
class Parent {
    static int value = init();

    static int init() {
        System.out.println("Parent: initialized");
        return 7;
    }
}

class Child extends Parent {
    static {
        System.out.println("Child: initialized");
    }
}
```

If you write `Child.value`, the field `value` **is declared in Parent**, not Child. Accessing the field can trigger **Parent initialization**, while **not necessarily initializing Child**.

### Runnable Program

File **`DeclaringClassTriggerDemo.java`**:

```java
class Parent {
    static int value = init();

    static int init() {
        System.out.println("Parent: initialized");
        return 7;
    }
}

class Child extends Parent {
    static {
        System.out.println("Child: initialized");
    }

    static void ownMethod() {
        System.out.println("Child: ownMethod");
    }
}

public class DeclaringClassTriggerDemo {
    public static void main(String[] args) {
        System.out.println("value=" + Child.value);
        System.out.println("before ownMethod");

        Child.ownMethod();
    }
}
```

```bash
javac DeclaringClassTriggerDemo.java
java DeclaringClassTriggerDemo
```

```text
Parent: initialized
value=7
before ownMethod
Child: initialized
Child: ownMethod
```

Lesson: **the class that actually declares the static field/method** is the key factor in determining the trigger. You should use `Parent.value` when you want readers to clearly see the declaration source, rather than using the Child name just because Java permits it.

## 16. How Does Interface Initialization Differ from Class Inheritance?

An interface can declare static fields initialized with runtime expressions and static methods with bodies. However, interface initialization has differences compared to classes.

**Key points:**

- Using a **static field that is not a constant variable declared in an interface** can trigger initialization of that interface itself.
- Calling a **static method declared in an interface** triggers interface initialization according to the rules.
- When initializing an interface, **all superinterfaces do not automatically have to be initialized** solely because of the `extends` relationship.
- When initializing a class, certain **superinterfaces declaring default methods** are also included in the initialization process according to Java rules. This is a subtle exception to the statement “initializing a class does not trigger initializing interfaces.”

### Example of a Runtime Interface Static Field

File **`InterfaceInitializationDemo.java`**:

```java
interface Flags {
    int RUNTIME = announce();

    static int announce() {
        System.out.println("Flags: initialized");
        return 5;
    }

    static void ping() {
        System.out.println("Flags: ping");
    }
}

public class InterfaceInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before read");
        System.out.println(Flags.RUNTIME);

        Flags.ping();
    }
}
```

```bash
javac InterfaceInitializationDemo.java
java InterfaceInitializationDemo
```

```text
before read
Flags: initialized
5
Flags: ping
```

Although interface fields are `public static final` by default, the `RUNTIME` field **is not a constant variable** because its initializer calls the `announce()` method. Therefore, reading `Flags.RUNTIME` triggers initialization.

### Interface Compile-Time Constants Remain an Exception

```java
interface Configuration {
    int MAX = 10;
}
```

`Configuration.MAX` is a compile-time constant according to the relevant rules, so merely using this constant **is not an operation that requires interface initialization**.

## 17. Default Methods Can Cause an Interface to Be Initialized Together with a Class

The JLS has a specific rule: when initializing a class, the JVM also initializes those superinterfaces that **declare default methods** in the required order. This is a case often overlooked when discussing triggers.

File **`DefaultInterfaceInitDemo.java`**:

```java
interface Feature {
    int MARKER = announce();

    static int announce() {
        System.out.println("Feature: initialized");
        return 1;
    }

    default void perform() {
    }
}

class FeatureImpl implements Feature {
    static {
        System.out.println("FeatureImpl: initialized");
    }
}

public class DefaultInterfaceInitDemo {
    public static void main(String[] args) {
        new FeatureImpl();
    }
}
```

```bash
javac DefaultInterfaceInitDemo.java
java DefaultInterfaceInitDemo
```

```text
Feature: initialized
FeatureImpl: initialized
```

- `Feature` declares a `default void perform()`, so it is considered under the rule for superinterfaces with default methods when initializing `FeatureImpl`.
- `Feature.MARKER` is not a compile-time constant because it calls `announce()`; initialization of Feature executes the initializer and prints the message.
- Afterward, `FeatureImpl` is initialized and prints the class's message.

**Note:** you should not generalize that any implemented interface always initializes before the class; you need to consider the default-method rule and the interface's own active uses.

## 18. A Static Nested Class Has a Separate Initialization Cycle from Its Enclosing Class

When you have:

```java
class Outer {
    static class Nested {
        static void work() {
        }
    }
}
```

`Outer.Nested` is **a separate class at runtime**, and its static initialization is not automatically equated with the initialization of `Outer`. Because Nested is a `static nested class`, it does not need an enclosing `Outer` instance.

File **`NestedClassInitializationDemo.java`**:

```java
class Outer {
    static {
        System.out.println("Outer: initialized");
    }

    static class Nested {
        static {
            System.out.println("Nested: initialized");
        }

        static void run() {
            System.out.println("Nested: run");
        }
    }

    static void run() {
        System.out.println("Outer: run");
    }
}

public class NestedClassInitializationDemo {
    public static void main(String[] args) {
        Outer.Nested.run();
        System.out.println("between");
        Outer.run();
    }
}
```

```bash
javac NestedClassInitializationDemo.java
java NestedClassInitializationDemo
```

```text
Nested: initialized
Nested: run
between
Outer: initialized
Outer: run
```

At first, only `Nested` is initialized because the static method declared in Nested is called. Only afterward does `Outer.run()` require initializing Outer.

**Common mistake:** seeing the source name `Outer.Nested` and assuming `Outer`'s initializer must run before any operation on `Nested`. Java has no such rule merely because of a lexical nesting relationship.

## 19. Order of Static Field Initializers and Static Blocks Within the Same Class

When a class is initialized, static field initializers and static initialization blocks are executed in **their order of appearance in source code**, in a process governed by definite assignment/forward reference rules.

File **`StaticOrderDemo.java`**:

```java
class Config {
    static int first = announce("field first", 1);

    static {
        System.out.println("static block A");
    }

    static int second = announce("field second", 2);

    static {
        System.out.println("static block B");
    }

    static int announce(String label, int value) {
        System.out.println(label);
        return value;
    }
}

public class StaticOrderDemo {
    public static void main(String[] args) {
        System.out.println("before read");
        System.out.println("sum=" + (Config.first + Config.second));
    }
}
```

```bash
javac StaticOrderDemo.java
java StaticOrderDemo
```

```text
before read
field first
static block A
field second
static block B
sum=3
```

Explanation:

1. `Config.first` is requested for the first time → Config must initialize.
2. The first static field initializer calls `announce("field first",1)`.
3. Static block A runs.
4. Static field initializer `second` runs.
5. Static block B runs.
6. After class initialization completes, the addition `Config.first + Config.second` returns 3.

**Do not confuse the declaration order of static members with the order of method calls.** The body of `announce` defined at the end can still be called from an initializer before it, in accordance with method resolution rules.

## 20. Static Initialization Occurs Before Instance Initialization

The same class can contain:

- Static field initializers.
- Static blocks.
- Instance field initializers.
- Instance initialization blocks.
- Constructors.

**General order when creating an object for the first time:** initialize the class (and relevant superclasses) → allocate/initialize the instance following the chain of constructors and instance initializers.

Complete example:

File **`ClassAndObjectOrderDemo.java`**:

```java
class Machine {
    static {
        System.out.println("Machine.static");
    }

    int code = printAndReturn("Machine.field", 1);

    {
        System.out.println("Machine.instanceBlock");
    }

    Machine() {
        System.out.println("Machine.constructor");
    }

    static int printAndReturn(String label, int value) {
        System.out.println(label);
        return value;
    }
}

public class ClassAndObjectOrderDemo {
    public static void main(String[] args) {
        System.out.println("before new");
        new Machine();
        System.out.println("second new");
        new Machine();
    }
}
```

```bash
javac ClassAndObjectOrderDemo.java
java ClassAndObjectOrderDemo
```

```text
before new
Machine.static
Machine.field
Machine.instanceBlock
Machine.constructor
second new
Machine.field
Machine.instanceBlock
Machine.constructor
```

The static block prints once, whereas the instance field initializer, instance block, and constructor run for each instance.

**Identification tip:** `static` is tied to **class initialization**; the absence of `static` on a field/initialization block is tied to **instance initialization**.

## 21. Running a Class Containing `main` Also Requires Initializing the Entry Class

When using the Java launcher to run a main class via the traditional mechanism, the JVM must initialize the class holding the entry method before executing the body of `main`.

File **`MainClassInitializationDemo.java`**:

```java
public class MainClassInitializationDemo {
    static {
        System.out.println("main class initialized");
    }

    public static void main(String[] args) {
        System.out.println("main method");
    }
}
```

```bash
javac MainClassInitializationDemo.java
java MainClassInitializationDemo
```

```text
main class initialized
main method
```

This explains why static initializers **inside the entry class itself** can run before the first line of `main` without you writing `new EntryClass()`.

**Do not conclude:** that if a non-entry class has a static block, the JVM will run the static block merely because the `.class` file exists in the directory. For other classes, you must consider active uses and required initialization relationships.

## 22. A Normal Class Is Successfully Initialized Only Once Within a Runtime Identity

“Only once” here must be understood within its proper scope: **each class/interface is identified at runtime by its name and defining class loader according to the JVM model**. If the same class name is defined by different class loaders, those can be **different runtime classes**, each with its own static state/initialization.

In a simple application using only a single standard loader, you typically observe:

```text
First active use -> static initialization runs
Subsequent active uses -> use the state of the already initialized class
```

**But it does not mean:** that the JVM across the whole machine initializes a class with the same name only once across all processes, JVM sessions, or class loaders.

### Multiple Threads Reaching an Uninitialized Class Simultaneously

The JVM coordinates class initialization according to the synchronization mechanism prescribed by the specification:

- Two threads simultaneously triggering the same uninitialized class are not allowed to independently run two overlapping successful passes of static initializers.
- Another thread may have to wait for the initialization currently in progress.
- If initialization fails, subsequent requests may receive an error related to the erroneous class state.

Do not try to simulate a “run once” static initializer using an unsynchronized boolean and assume it matches JVM behavior; rely on the standard class initialization rules.

## 23. When a Static Initializer Throws an Exception: The Class Can Enter an Erroneous State

An error in a static initializer affects **the entire class initialization process**, not just the current method call.

File **`FailedInitializationDemo.java`**:

```java
class Broken {
    static final int VALUE = fail();

    static int fail() {
        System.out.println("Broken: initializing");
        throw new IllegalStateException("boom");
    }

    static void work() {
        System.out.println("unreachable in this demo");
    }
}

public class FailedInitializationDemo {
    public static void main(String[] args) {
        try {
            Broken.work();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first: initialization failed");
        }

        try {
            Broken.work();
        } catch (NoClassDefFoundError ex) {
            System.out.println("second: class unusable");
        }
    }
}
```

```bash
javac FailedInitializationDemo.java
java FailedInitializationDemo
```

```text
Broken: initializing
first: initialization failed
second: class unusable
```

Explanation:

1. Calling `Broken.work()` is an active use, requiring Broken to be initialized before entering the method body.
2. While initializing `VALUE`, `fail()` prints a message and throws `IllegalStateException`.
3. Under initialization error-handling rules, an exception other than `Error` that escapes an initializer is wrapped in an `ExceptionInInitializerError` in this scenario.
4. `Broken` does not complete initialization and is marked as being in an erroneous state in the corresponding runtime context.
5. A subsequent active-use attempt does not “try running the initializer again” like a normal retry; the example catches `NoClassDefFoundError`.

**Do not use the exception type on the subsequent attempt to prove the class file was deleted**. `NoClassDefFoundError` in this scenario can appear because the class is unusable after an initialization failure, unlike the common “missing .class file” error.

### Note on `Error`

If a static initializer throws an `Error`, error propagation has its own rules: not every error is wrapped like the runtime exception in the example above. Learn the general rule rather than claiming that any `Throwable` always becomes `ExceptionInInitializerError`.

## 24. Avoid Hard-to-Control Side Effects in Static Initializers

A static initializer can run **later than beginners expect**: for example, only when a class undergoes active use via a static method call or a non-constant static field. If the initializer performs many complex tasks, the first use of the class can cause surprises:

- Opening files or network connections.
- Reading environment/configuration variables.
- Registering callbacks or starting threads.
- Writing data to a database.
- Throwing exceptions because the environment is not yet prepared.
- Waiting on a lock and inadvertently interacting with other classes that are currently initializing.

A cautious design:

1. Keep static initialization **simple, with a predictable execution time**.
2. Do not assume the static initializer is the application-wide business startup point.
3. Move I/O or initialization that can fail into **factory/service/lifecycle methods** with clear contracts when appropriate.
4. If using a lazy holder to defer resource initialization, understand the behavior when initialization fails and how retries work.
5. Do not rely on a side effect of compile-time constant access to “trigger the class.”

**Important:** class initialization has the JVM's synchronization mechanism, but it does not by itself guarantee that side effects outside the JVM are atomic, idempotent, or rollback-capable.

## 25. Lazy Initialization via a Static Holder Class

A commonly used idiom is the **initialization-on-demand holder**: placing an instance or value that needs lazy creation inside a static nested class. The nested class will be initialized when its corresponding static member experiences an active use.

Example file **`LazyHolderDemo.java`**:

```java
public class LazyHolderDemo {
    private LazyHolderDemo() {
    }

    private static class Holder {
        static final String VALUE = makeValue();

        static String makeValue() {
            System.out.println("Holder: computing value");
            return "ready";
        }
    }

    static String value() {
        return Holder.VALUE;
    }

    public static void main(String[] args) {
        System.out.println("before first value");
        System.out.println(value());
        System.out.println(value());
    }
}
```

```bash
javac LazyHolderDemo.java
java LazyHolderDemo
```

```text
before first value
Holder: computing value
ready
ready
```

Because `Holder.VALUE` is initialized via a **method call**, it **is not a compile-time constant**. The first time `value()` accesses Holder.VALUE, Holder is initialized and `makeValue()` runs. The second time uses the existing value.

If changed to:

```java
static final String VALUE = "ready";
```

then `VALUE` can be a **constant variable**, and **reading it does not necessarily trigger initialization of Holder**. That is a key difference when using the holder pattern.

**Note:** in a real singleton holder, the holder typically holds `static final Singleton INSTANCE = new Singleton();` — an object reference field is not a compile-time constant; active use triggers holder initialization. Whether the singleton remains a true singleton across all reflection/serialization/classloader scenarios is a separate topic.

## 26. Constant Inlining Also Affects Library Updates

When a compiled client uses:

```java
public static final int LIMIT = 100;
```

the compiler can inline the constant value into the client's bytecode. If the library changes to `LIMIT=200` without **recompiling the client**, the old client may still use 100 as it was compiled.

This is not “slow JVM initialization,” but rather a **constant variable using its value at compile time**. Therefore:

- Do not use public compile-time constants for configuration expected to change at runtime or across library versions without accounting for compatibility.
- If flexible values are needed, you can use a **static method** or a **non-constant static field** as appropriate for the API.
- Recompile clients when the contract of public constants changes, and check binary compatibility in released libraries.
- Do not use constant access merely to deliberately trigger a static initializer.

For example, declaring `static final int LIMIT = readConfig();` is no longer a constant variable and has runtime initialization; however, reading configuration during class initialization also carries timing/error risks that need to be managed.

## 27. Operations That May Trigger Classes Other Than the One You Are Focused On

The active-use rule for a target class does not mean “the entire program initializes no other classes.”

For example:

```java
System.out.println(Settings.level);
```

This expression simultaneously involves operations on `System`, `PrintStream`, and `Settings` depending on runtime state. What you control/interpret here is that **reading `Settings.level` can require initializing Settings**.

Similarly:

```java
new Child(computeArgument());
```

If `computeArgument()` has side effects or active uses of other classes, the output depends on the rules for **evaluating object creation expressions**, **arguments**, **superclass initialization**, static/instance initializers, and constructors. You should not predict an overall order with the phrase “static always runs first in the entire program.”

**The right way to reason:**

1. Identify which line **actually executes**.
2. Identify which class/interface is **actively used**.
3. Identify **where the static member is declared**.
4. Determine whether that class/interface has already been successfully initialized previously.
5. Consider superclasses and superinterfaces according to the relevant rules.
6. After initialization completes, continue evaluating the call/field read/constructor in Java's order.

## 28. Comparing Three Easily Confused Call Forms

### A. Static Method of the Class Itself

```java
Target.compute();
```

If `compute` is a static method declared in Target and Target has not yet been initialized this time, that is a trigger.

### B. Static Method of a Superclass Called Through a Subclass Name

```java
Subclass.inheritedStatic();
```

If `inheritedStatic` is actually declared in Superclass, identify the **declaring class**. Do not infer that Subclass must be initialized merely because of the qualifier shown in source.

### C. Static Method of an Interface

```java
SomeInterface.helper();
```

Static interface methods are called through the **declaring interface name** and are not inherited like interface instance methods. Calling an interface's helper causes that interface to be initialized if needed.

This distinction helps avoid errors when analyzing code that uses inheritance or when refactoring static methods between classes.

## 29. Self-Check Questions: Does It Trigger Initialization?

Suppose `Target` has not yet been initialized, and the following expressions appear in a running method with the classes located normally:

| Expression | Short answer | Why |
| --- | --- | --- |
| `Class<Target> t = Target.class;` | **No** | A class literal does not by itself initialize |
| `Target[] arr = new Target[4];` | **No** | Only creates the array, does not create Target instances |
| `Target x;` | **No** | Only a local variable declaration |
| `new Target();` | **Yes** | Instance creation triggers class initialization |
| `Target.run();` | **Yes** if static run is declared in Target | Static invocation |
| `Target.value` | **Yes** if it is a non-constant static field declared in Target | Field read |
| `Target.value = 3;` | **Yes** if the static field is assignable | Field write |
| `Target.LIMIT` | **No** if LIMIT is a constant variable | Constant-variable exception |
| `Class.forName("Target")` | **Yes** when resolution/lookup succeeds under that overload | Reflection API requires initialization |
| `Class.forName("Target", false, loader)` | **Not from this call** | `initialize=false` |
| `loader.loadClass("Target")` | **Not solely because of loadClass** | Loading differs from initialization |
| `Target.class.getName()` | **Does not by itself initialize Target** | Metadata, not active execution |
| `target instanceof Target` | **Does not by itself initialize Target** | Type check differs from class initialization |
| `import static pkg.Target.run;` | **No** | Imports are processed at compile time |

The table assumes valid declarations and context; if the compiler rejects the expression before execution (for example, assigning to a `final` field), there will be **no runtime trigger to observe**.

## 30. Common Misconceptions

| Misconception | What is true |
| --- | --- |
| “Writing a class name in source already initializes the class” | Only operations according to the rules require initialization |
| “Loading equals initialization” | Loading/linking and initialization are different phases |
| “The class literal `X.class` runs the static block” | It does not run by itself |
| “Creating `new X[3]` calls three X constructors” | Only creates the array; slots are null |
| “Reading every static field runs the static block” | Constant variables are an exception |
| “Anything `static final` is a compile-time constant” | Requires primitive/String and a constant expression |
| “Calling `Class.forName(name,false,loader)` initializes just like the single-argument overload” | `false` does not require initialization |
| “`loadClass` runs the initializer immediately” | Does not by itself require initialization |
| “Retrieving metadata via reflection and invoking a method are the same” | Lookup and invocation have different rules |
| “When calling a static method initially, the constructor also runs” | No instance creation is needed |
| “The static initializer runs on every static method call” | Successful initialization does not repeat within the same runtime class |
| “`Child.parentField` definitely initializes Child” | Consider the class that declares the static field |
| “Initializing Parent automatically initializes all descendants” | No |
| “All implemented interfaces initialize before the class” | There are special rules related to default methods |
| “A static nested class must initialize the outer class first” | Not solely because of the lexical nesting relationship |
| “`static` always runs before the first line of `main` of any class” | Only consider the entry class and actual active uses |
| “Every initialization failure will automatically retry” | The class can become erroneous within the runtime identity |
| “NoClassDefFoundError after an error means the .class file is missing” | It can occur because initialization already failed |
| “Static initialization is atomic for all external side effects” | No; transactions/external systems have their own rules |
| “A `final` reference to an object means the object is initialized at compile time” | No; final does not determine the initialization trigger |
| “A class named X across all class loaders always shares one static state” | Runtime class identity is tied to the defining loader |
| “A static block is where all production resources should be started” | Complex side effects in initialization are hard to control |

## 31. Comprehensive Practice Exercise: Predicting the Exact Output

Create **`InitializationTraceDemo.java`**:

```java
class Parent {
    static final int CONST = 10;

    static {
        System.out.println("Parent.init");
    }

    static int state = compute();

    static int compute() {
        System.out.println("Parent.compute");
        return 20;
    }

    static void ping() {
        System.out.println("Parent.ping");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child.init");
    }

    Child() {
        System.out.println("Child.constructor");
    }
}

public class InitializationTraceDemo {
    public static void main(String[] args) {
        System.out.println("A");
        System.out.println(Child.CONST);

        System.out.println("B");
        System.out.println(Child.state);

        System.out.println("C");
        Child child = new Child();

        System.out.println("D");
        Parent.ping();

        System.out.println(child != null);
    }
}
```

```bash
javac InitializationTraceDemo.java
java InitializationTraceDemo
```

**Answer:**

```text
A
10
B
Parent.init
Parent.compute
20
C
Child.init
Child.constructor
D
Parent.ping
true
```

### Line-by-Line Solution

1. `System.out.println("A")` runs normally in main.
2. `Child.CONST` accesses the constant variable `CONST` declared in Parent; prints `10` **without yet needing to initialize Parent or Child**.
3. Prints `B`.
4. `Child.state` accesses the non-constant static field `state` **declared in Parent**. Parent is initialized: the static block prints `Parent.init`, then the field initializer calls `compute()` which prints `Parent.compute`.
5. The value of `state` is 20, so it prints `20`. **Child still does not need to be initialized** solely because of `Child.state`.
6. Prints `C`.
7. `new Child()` requires initializing Child; Parent has already been initialized, so it does not run again. Prints `Child.init`, and then Child's constructor prints `Child.constructor`.
8. Prints `D`.
9. `Parent.ping()` calls a static method; Parent is already initialized, so it only prints `Parent.ping`, without re-printing the block or compute.
10. The `child` variable holds a non-null reference, so it prints `true`.

**Key learning point:** you cannot guess the output just by counting `static`. You must consider the **declaring class**, **constant variable**, **whether it has been initialized yet**, **superclass relationships**, and **expression execution order**.

## 32. Exercise: Correcting Wrong Predictions

Read the following independent modifications to the program above and reason through them yourself:

**Scenario A:** change `static final int CONST = 10;` to `static final int CONST = Integer.parseInt("10");`.

- `CONST` is no longer a constant variable.
- The line `System.out.println(Child.CONST)` can become the first trigger for Parent initialization.
- Therefore, `Parent.init` and `Parent.compute` will appear **before printing the value 10**, rather than waiting until `state` is read.

**Scenario B:** add a static block printing `Child.extra` after the existing block in Child.

- When Child initializes, Child's two static blocks run in source order.
- That does not cause Child to initialize early at `Child.CONST` or `Child.state` in the original program.

**Scenario C:** replace `new Child()` with `Child[] array = new Child[1];`.

- Only creates an array, does not create a Child instance.
- If there is no other active use of Child, the static block `Child.init` and Child's constructor **do not run** solely because of this line.

**Scenario D:** call `Class.forName("Child")` before `new Child()`.

- If the class is found with the appropriate loader/context, the invocation can require initializing Child first.
- `new Child()` afterward will not print Child's static initialization again; the constructor still runs.

These scenarios are **reasoning exercises on modifying the sample program**, not independent Java programs pasted verbatim into the same file.

## 33. Checklist When Debugging “When Does a Static Block Run?”

1. **Identify which class/interface has a static initializer**; do not rely solely on names appearing in source.
2. **Separate loading/linking from initialization**; obtaining a `Class` object does not by itself mean it has been initialized.
3. **List the first active uses**: `new`, static method, reading/writing a non-constant static field, reflective invocation.
4. **If accessing a static member through a subclass**, look up the member's **declaring class/interface**.
5. **If a field is `static final`**, check accurately whether it is a **constant variable**: primitive/String + constant expression.
6. **If it is an array**, distinguish `new ElementType[n]` from `new ElementType()` for each slot.
7. **If using reflection**, check whether the overload/API requires initialization; `Class.forName(name,false,loader)` differs from `Class.forName(name)`.
8. **If superclass/subclass**, consider the superclass initialization dependency.
9. **If interface**, check default methods and the specific initialization rules.
10. **If nested class**, do not assume the outer class initializes solely because of the name `Outer.Nested`.
11. **Within a class**, check the order of static field initializers and static blocks in source.
12. **Compare with instance field initializers/constructors**; they only run when creating an instance according to the relevant process.
13. **Check whether the class has already been initialized previously** within the same runtime identity.
14. **If an error occurs**, distinguish between the exception on the first initialization attempt and the error when trying to use the erroneous class next.
15. **If multiple threads**, consider initialization synchronization constraints and do not confuse them with transactions.
16. **If library constants change**, consider compile-time inlining and client rebuilds.
17. **Keep static initializers simple**, without depending on arbitrary startup order of application components.
18. **Run `javac`/`java` with the right files and environment** to observe actual behavior when concrete code is available.

---

**Final takeaway:** The operations that commonly **trigger class initialization** are **creating an instance with `new`**, **calling a static method actually declared in that class**, **reading/writing a non-constant-variable static field**, and **reflective operations that require initialization** such as `Class.forName(String)`. Conversely, **`SomeClass.class`**, **merely declaring a variable**, **creating an array `new SomeClass[n]`**, **imports**, **reading a compile-time constant variable**, and **merely loading a class** are not the same thing as running a static initializer. When you need to predict the exact timing, always consider **whether initialization has already occurred, where the member is declared, superclasses/superinterfaces, the order of static initializers, and the specific reflection API**.
