# Observing Metadata vs. Executing or Mutating Objects in Java Reflection

## 1. Objectives and Core Boundaries

Java Reflection allows a program to inspect information about classes, fields, methods, constructors, modifiers, data types, and annotations at runtime. **Retrieving descriptive information (metadata) is not the same as invoking a method, running a constructor, or mutating the state of an object.** Those actions require separate APIs and can produce side effects.

For example, when calling `getDeclaredMethod("advance")`, you only receive a `Method` object describing the method named `advance`. Only when you call `method.invoke(target)` is the target method actually executed. Similarly, `getDeclaredField("status")` returns the field's metadata; `field.set(target, "DONE")` is the operation that writes state.

A subtle point: Reflection APIs themselves still execute library code to retrieve metadata, which can sometimes cause a class to be loaded or linked. Therefore, the statement "reading metadata does not execute code" must be understood precisely as **it does not automatically invoke the business logic of the described method/constructor**, rather than that the JVM does nothing at all.

## 2. Distinguishing Metadata, Reading State, and Side-Effecting Actions

| API or Operation | Category | Meaning and Potential Impact |
| --- | --- | --- |
| `SomeType.class`, `obj.getClass()` | Obtaining a `Class` object | Identifies the type; does not create a new instance. |
| `Class.getName()`, `getModifiers()`, `getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()` | Observing metadata | Reads declarations/structure; does not automatically run the discovered methods/constructors. |
| `Class.getAnnotation(...)`, `Field.getName()`, `Method.getParameterTypes()` | Observing metadata | Reads annotations, names, and signatures; does not invoke business logic of the target object. |
| `Field.get(target)` | Reading runtime value | Reads the **current state** of a field; not just metadata. Reading a `static` field can trigger class initialization. |
| `Method.invoke(target, args...)` | Execution | Actually invokes the target method; may write data, print logs, throw exceptions, make network calls... |
| `Constructor.newInstance(args...)` | Execution/object creation | Creates an instance and runs the constructor; the constructor may cause side effects. |
| `Field.set(target, value)` | Mutating state | Writes a field value (if permitted); distinct from `Field.get`. |
| `AccessibleObject.setAccessible(true)` | Changing Reflection access permissions | Requests bypassing Java access checks for subsequent Reflection operations; **this call itself does not modify the target field's value**. Can be rejected by the module system/access rules. |

The key takeaway: `Method` and `Field` are **member descriptor objects**. Having a descriptor object in hand does not mean you have used that member to affect an instance.

## 3. Complete Example: Inspecting Metadata First, Executing and Mutating Data Afterward

Save the following as `ReflectionBoundaryDemo.java` (Java 17 or later):

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionBoundaryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @interface Topic {
        String value();
    }

    @Topic("demo")
    static class Counter {
        private String status = "NEW";
        private int count = 0;

        public void advance() {
            count++;
            System.out.println("advance executed");
        }

        public String snapshot() {
            return status + ":" + count;
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Counter> type = Counter.class;
        Field field = type.getDeclaredField("status");
        Method method = type.getDeclaredMethod("advance");
        Topic annotation = type.getAnnotation(Topic.class);

        System.out.println("Class: " + type.getSimpleName());
        System.out.println("Field: " + field.getName() + " (" + field.getType().getSimpleName() + ")");
        System.out.println("Method: " + method.getName() + " -> " + method.getReturnType().getSimpleName());
        System.out.println("Annotation: " + annotation.value());

        Counter counter = new Counter();
        System.out.println("State before: " + counter.snapshot());

        method.invoke(counter);
        System.out.println("State after invoke: " + counter.snapshot());

        field.setAccessible(true);
        System.out.println("Read field: " + field.get(counter));

        field.set(counter, "DONE");
        System.out.println("State after field.set: " + counter.snapshot());
    }
}
~~~

Compile and run:

~~~bash
javac ReflectionBoundaryDemo.java
java ReflectionBoundaryDemo
~~~

Expected output:

~~~text
Class: Counter
Field: status (String)
Method: advance -> void
Annotation: demo
State before: NEW:0
advance executed
State after invoke: NEW:1
Read field: NEW
State after field.set: DONE:1
~~~

Step-by-step explanation:

1. `getDeclaredField`, `getDeclaredMethod`, `getAnnotation`, and the calls retrieving names/return types all serve **metadata observation**. They do not call `advance()`, so no `advance executed` line appears in the first part.
2. `new Counter()` is **object creation in regular Java**. `counter.snapshot()` is a regular method call to inspect state, not metadata inspection.
3. `method.invoke(counter)` executes `advance()`, increments `count` from `0` to `1`, and prints the message.
4. `field.setAccessible(true)` allows this example to access the `private` field; it does not change the `status` string.
5. `field.get(counter)` reads the existing value (`NEW`); `field.set(counter, "DONE")` is what changes it to `DONE`.

Because the example uses a nested class in the same file, the private access operation here works on Java 17+. When reflecting into a class belonging to another module, `setAccessible(true)` may throw `InaccessibleObjectException` if the package is not opened appropriately; Reflection should not be treated as an unconditional way to bypass encapsulation.

## 4. Reading Metadata vs. Class Initialization

Further distinguish three concepts that are easily lumped together:

- **Loading:** the JVM locates and defines the representation of the class.
- **Linking:** the JVM verifies, prepares, and may resolve references.
- **Initialization:** executes static initializers and static initialization assignments according to Java rules.

Referencing `SomeType.class` or querying metadata via `Class` normally does not initialize that class. By contrast, single-argument `Class.forName("ten.day.du")` **requests class initialization by default**. This matters greatly if a static initializer opens connections, changes configuration, or writes logs.

The file `InitializationBoundaryDemo.java` illustrates this:

~~~java
public class InitializationBoundaryDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Target.class;
        System.out.println("Class literal resolved");

        type.getDeclaredFields();
        System.out.println("Metadata inspected");

        Class.forName(Target.class.getName());
        System.out.println("Class.forName completed");
    }
}
~~~

~~~bash
javac InitializationBoundaryDemo.java
java InitializationBoundaryDemo
~~~

~~~text
Class literal resolved
Metadata inspected
Target initialized
Class.forName completed
~~~

In this program, the static initialization line only appears at the `Class.forName` step. If you need to obtain a `Class` from a class name **without requesting initialization yet**, you can use the overload `Class.forName(className, false, classLoader)`; you still need to handle `ClassNotFoundException` and any loading/linking errors that may occur. Do not assume that every information-reading API or every way of obtaining `Class` is strictly free of JVM-level side effects.

## 5. Knowing Exactly What You Are Observing

### 5.1. Class Metadata vs. Instance State

`Field.getType()` tells you what type the field **is declared as**; `Field.get(obj)` reads the **current value** on the corresponding object. One field metadata object can be used to read many different instances:

~~~java
Field statusField = Counter.class.getDeclaredField("status");
statusField.setAccessible(true);
Counter first = new Counter();
Counter second = new Counter();
statusField.set(first, "DONE");

System.out.println(statusField.get(first));  // DONE
System.out.println(statusField.get(second)); // NEW
~~~

The snippet above is only an **additional illustration within the scope of the `ReflectionBoundaryDemo` class**, not a standalone program; it requires the imports, `Counter` declaration, and access context from the previous example. Both instances share the same field structure but hold separate values. The `set` line changes only `first`, without affecting `second`.

### 5.2. Direct Declarations vs. Inherited Members

| API | Visible Members |
| --- | --- |
| `getDeclaredFields()` / `getDeclaredMethods()` | Fields/methods **declared directly in the class itself**, including private ones; does not collect inherited members. |
| `getFields()` / `getMethods()` | Accessible **public** fields/methods in the class and inherited hierarchy (including matching public members from interfaces). |
| `getDeclaredConstructors()` | Constructors of the class under inspection; constructors are not inherited. |
| `getConstructors()` | Public constructors of the class under inspection. |

Note that `getDeclaredMethods()` may include `synthetic` or bridge methods generated by the compiler. Before displaying metadata to learners/users, consider `Method.isSynthetic()`, `Method.isBridge()`, `Modifier`, and any necessary annotations. **Do not rely on the order** of the arrays returned by `getDeclaredFields()` or `getDeclaredMethods()`; if deterministic output is needed, sort them yourself.

### 5.3. Annotations Describe; They Do Not Implicitly Execute Behavior

Only annotations with `@Retention(RetentionPolicy.RUNTIME)` can be read at runtime using Reflection. Reading an annotation does not automatically turn the annotation's content into processing rules. For example, the `@Topic("demo")` annotation in the program only provides the string `demo`; the code using the annotation (the framework or application) decides whether to register a bean, run a check, or invoke a function. `getAnnotations()` and `getDeclaredAnnotations()` also differ in how they handle inherited elements according to `@Inherited` rules for class annotations.

## 6. Application: Separating the Discovery Phase and Execution Phase

Suppose you are building a tool to list commands on a plugin:

1. **Discovery phase:** use `Class`, `Method`, annotations, and modifiers to determine command names, parameter counts, and return types; validate signatures and build the selection menu.
2. **Validation phase:** verify execution permissions, input data, allowed plugin scope, object state, and error handling.
3. **Execution phase:** only when there is a valid request do you create an object (if needed) and call `Method.invoke`.

This phase separation helps an application **display documentation or list APIs** without inadvertently triggering actions. In particular, a "class structure viewer" UI should not speculatively call every method to inspect results: even a getter can perform heavy computation, write to a cache, read files, or throw exceptions. A name starting with `get` does not guarantee a method has no side effects.

In dependency injection, serializers, ORMs, or testing frameworks, **scanning annotations/fields** is usually the descriptive step; **instantiating objects, invoking lifecycle callbacks, and reading/writing fields** are subsequent steps with different runtime semantics. When debugging, pinpoint exactly which step occurred.

## 7. Common Mistakes and Practical Limits

- **Confusing "finding a method" with "invoking a method":** `getMethod`/`getDeclaredMethod` does not call the target method. To call it, you must use `invoke`, or normal Java call syntax.
- **Confusing "field metadata" with "field value":** `getDeclaredField` gives the name, type, modifiers, and annotations; `Field.get` reads the runtime value; `Field.set` writes the runtime value.
- **Ignoring initialization side effects:** `Class.forName(String)`, accessing certain `static` members, instantiating objects, or invoking methods can trigger class initialization. "Just inspecting" must be verified against the actual APIs used.
- **Assuming private members are always accessible:** finding a private member does not mean you are allowed to read/write/call it. `setAccessible` can fail with closed modules; prefer public APIs and explicit access design.
- **Treating Reflection as exempt from type checks:** `Method.invoke` must receive the right receiver, argument count, and argument types; `Field.set` must receive a compatible value. Calls can throw `IllegalAccessException`, `IllegalArgumentException`, or `InvocationTargetException`; errors from the invoked method are typically in `InvocationTargetException.getCause()`.
- **Guessing metadata order:** APIs returning field/method arrays do not guarantee source order. Sort them if deterministic results are needed.
- **Mutating fields that should not be mutated:** do not treat Reflection as a valid mechanism to alter arbitrary `final` fields, invariants, hidden fields, or JDK internals. Direct mutation can break object consistency and hit access restrictions.
- **Equating annotations with behavior:** annotations provide descriptive data; annotation-processing logic performs the actual work.

## 8. Checklist When Reading or Writing Reflection Code

Before each call, ask yourself:

1. Am I asking **how a class/member is declared** (`Class`, `Field`, `Method`, annotations), or retrieving **the value of an instance** (`Field.get`)?
2. Does this API **invoke a constructor/method** or **write a value** (`newInstance`, `invoke`, `set`)?
3. Is there a chance it will **initialize a class**, trigger a static initializer, call a lifecycle callback, or perform I/O?
4. Have I properly handled **public/private, inherited/declared, module access, receiver, and exceptions**?
5. If I only want to inspect metadata, can I stop at the descriptor-fetching APIs without instantiating objects or calling business code?

**Self-check:** In the `ReflectionBoundaryDemo` example, if you remove the two lines `method.invoke(counter)` and `field.set(counter, "DONE")` (along with the state-printing lines used only to observe after them), then no Reflection operation increments `count` or changes `status`. Collecting `Method` and `Field` still works completely.

**Conclusion:** Reflection helps you **know how a program is structured**; making **the program do something** belongs to execution or state-mutating calls. Clearly separating these two layers of responsibility helps you write reliable introspection tools, debug accurately, and keep side effects under control.