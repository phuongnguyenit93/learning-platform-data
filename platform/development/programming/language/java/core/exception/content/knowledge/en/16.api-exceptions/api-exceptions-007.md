# ReflectiveOperationException and Reflection Lookup Errors in Java

## 1. Lesson Objectives

**Reflection** allows a Java program to inspect and manipulate class structures at runtime: finding classes by name, looking up methods, fields, and constructors, instantiating objects, reading/writing fields, and dynamically invoking methods. It is very useful in dependency injection frameworks, serialization, plugin loading, ORMs, test frameworks, and developer tools.

However, reflection shifts some errors that are normally checked at compile time into **errors raised at runtime**. For example, `getMethod("find", String.class)` may fail to find a method with the exact signature; `Class.forName("example.Plugin")` may fail to load the class; `Method.invoke(...)` may not be permitted to access the target, or the target method itself may throw an exception.

Java groups many **checked exceptions related to reflective operations** under `java.lang.ReflectiveOperationException`. Understanding this hierarchy helps you distinguish:

- **Metadata lookup errors**: failing to find a class, method, or field.
- **Access/instantiation errors**: lacking access permission, or being unable to instantiate the chosen class type.
- **Errors actually thrown by the invoked code**: wrapped in `InvocationTargetException`.
- **Other runtime errors outside the `ReflectiveOperationException` branch**: wrong arguments, modules disallowing reflective opening, class initialization errors, security, or linkage errors.
- **API contract errors**: using `getMethod` instead of `getDeclaredMethod`, confusing `int.class` with `Integer.class`, looking up the wrong package name, or mismatches in overloads.

This lesson uses **Java 17+**. Complete examples include filenames, `javac`/`java` commands, and expected `stdout`; code snippets or intentionally incorrect examples are clearly noted. No external libraries beyond the JDK are needed.

## 2. Reflection Operates in Two Phases: *Lookup* and *Use*

Consider the two distinct steps:

```text
Class / method / field name
          |
          v
[1] LOOKUP via reflection
    Class.forName(...)
    type.getMethod(...)
    type.getDeclaredField(...)
    type.getConstructor(...)
          |
          | returns Class / Method / Field / Constructor
          v
[2] USE the reflective object
    method.invoke(target, arguments)
    field.get(target), field.set(...)
    constructor.newInstance(arguments)
          |
          v
    Result or runtime exception
```

Errors in the **lookup** phase are not necessarily the same as errors in the **use** phase. `getDeclaredMethod(...)` returns a `Method` when a private member is found, but finding it does not automatically mean the caller has permission to `invoke(...)` it. Conversely, lookup and access may succeed, yet the **target method** throws `IllegalArgumentException`, `IOException`, or another `Throwable` in its body; Java wraps errors from the target method into `InvocationTargetException` when called via `Method.invoke`.

### Two Illustrative Snippets

```java
Class<?> type = Class.forName("java.lang.String");
java.lang.reflect.Method method =
        type.getMethod("substring", int.class);
```

`Class.forName` can throw `ClassNotFoundException`; `getMethod` can throw `NoSuchMethodException`.

```java
String value = (String) method.invoke("abcdef", 2);
```

This is a **code snippet** continuing from the previous one, inside a method that handles or declares checked exceptions. `invoke` can throw `IllegalAccessException` and `InvocationTargetException`, while passing the wrong target or arguments can cause `IllegalArgumentException` or other runtime exceptions.

**Key takeaway:** do not catch `NoSuchMethodException` at the `invoke` phase and assume it handles all errors. Those are two operations with **two different exception contracts**.

## 3. The `ReflectiveOperationException` Hierarchy

Simplified type tree in Java 17:

```text
Throwable
└── Exception
    └── ReflectiveOperationException               [checked]
        ├── ClassNotFoundException
        ├── IllegalAccessException
        ├── InstantiationException
        ├── NoSuchFieldException
        ├── NoSuchMethodException
        └── java.lang.reflect.InvocationTargetException
```

Every subtype listed above is a **checked exception**, because `ReflectiveOperationException` extends `Exception` but not `RuntimeException`. Callers must `catch` or declare `throws` when an API can propagate them.

| Exception | Common Phase | Core Meaning |
| --- | --- | --- |
| `ClassNotFoundException` | Loading a class by name | The loader could not find the requested class |
| `NoSuchMethodException` | `getMethod`, `getDeclaredMethod`, constructor lookup | No matching signature according to the lookup API |
| `NoSuchFieldException` | `getField`, `getDeclaredField` | No field with that name in the search scope |
| `IllegalAccessException` | `Method.invoke`, `Field.get/set`, `Constructor.newInstance` | Caller does not have permission to access the member |
| `InstantiationException` | Reflectively instantiating a non-instantiable class, such as an abstract class | The target type cannot be instantiated under the contract |
| `InvocationTargetException` | `Method.invoke`, `Constructor.newInstance` | The invoked method/constructor body threw a `Throwable` |

Not all reflection errors inherit from this class. For example:

- `IllegalArgumentException` is unchecked: passing the wrong number/types of arguments, or an incompatible receiver.
- `InaccessibleObjectException` is unchecked: attempting to open access restricted by modules.
- `SecurityException` is unchecked: security policy forbids the operation.
- `ExceptionInInitializerError` and `LinkageError` are `Error` types: class initialization/linkage failures, not `ReflectiveOperationException`.
- `NullPointerException` can occur with a `null` receiver when calling an instance method via reflection.
- `ClassCastException` can occur when the **caller casts the result** of `invoke` to the wrong type.

Therefore, `catch (ReflectiveOperationException e)` is very useful for grouping **a set of checked reflection failures**, but it must not be interpreted as “catching all reflection errors”.

## 4. Checked Exceptions in Reflection and the `throws` Contract

A helper using multiple reflection APIs can declare the parent type:

```java
static Object createByName(String className)
        throws ReflectiveOperationException {
    Class<?> type = Class.forName(className);
    return type.getDeclaredConstructor().newInstance();
}
```

This is an **illustrative method**. `Class.forName` can throw `ClassNotFoundException`. `getDeclaredConstructor()` can throw `NoSuchMethodException`. `newInstance()` can throw `InstantiationException`, `IllegalAccessException`, and `InvocationTargetException`. All of them fall under `ReflectiveOperationException`.

**Advantage:** `throws ReflectiveOperationException` gives callers a single unified checked contract for the reflection process.

**Trade-off:** if the caller needs to make different decisions between “the class does not exist” and “the target constructor threw an error”, catching only the parent type can lose that level of classification on the spot. You can still check with `instanceof` or place specific `catch` blocks before `catch (ReflectiveOperationException)`.

```java
try {
    Object instance = createByName("sample.Plugin");
} catch (ClassNotFoundException missingClass) {
    // Handle missing class name configuration.
} catch (NoSuchMethodException missingConstructor) {
    // No-arg constructor not found.
} catch (ReflectiveOperationException otherReflectionFailure) {
    // Remaining checked reflection failures.
}
```

This is an **illustrative snippet**, not a standalone program. `ClassNotFoundException` should be distinguished from runtime errors, even when a general handler is present.

### Compared to Normal Java Method Calls

A call like `service.doWork()` has its method signature checked by `javac` at compile time. When using `type.getMethod("doWork").invoke(service)`, the lookup by string and `Class<?>` list happens at runtime. The compiler cannot prove that every class, overload, and visibility will be valid on every run. Reflection carries a corresponding dynamic error contract.

## 5. `ClassNotFoundException`: Class Not Found by Name

Common API:

```java
Class<?> type = Class.forName("com.example.Plugin");
```

This is an illustrative snippet. The `Class.forName(String)` form loads and **initializes** the class according to the API rules; if the target class cannot be found, it can throw `ClassNotFoundException`.

Common causes:

- Fully qualified class name has the wrong package or wrong letter casing.
- The JAR containing the class is not on the appropriate classpath/module path.
- The class loader in use cannot see the class.
- Plugin configuration references a class that was renamed, not deployed, or no longer exists.
- Incorrect binary name: a nested class may have the form `Outer$Inner` rather than `Outer.Inner` when using runtime name strings.

**Do not confuse** `ClassNotFoundException` with `NoClassDefFoundError`. The latter belongs to `LinkageError` and can occur during loading/linking of a class that was previously found by name but cannot have its required definition available at runtime, or due to a prior class initialization failure. The two situations are operationally related but **do not belong to the same exception branch**.

### Runnable Program: Loading an Existing Class and Catching a Missing Class

Create file **`ClassLookupDemo.java`**:

```java
public class ClassLookupDemo {
    public static void main(String[] args) {
        try {
            Class<?> found = Class.forName("java.lang.String");
            System.out.println("found=" + found.getName());
        } catch (ClassNotFoundException failure) {
            System.out.println("unexpected");
        }

        try {
            Class.forName("training.example.DefinitelyMissingClass");
        } catch (ClassNotFoundException failure) {
            System.out.println("missing="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac ClassLookupDemo.java
java ClassLookupDemo
```

`stdout`:

```text
found=java.lang.String
missing=ClassNotFoundException
```

The program intentionally looks up a non-existent name `training.example.DefinitelyMissingClass`. The run assumes this name is not provided by the application on the classpath/module path, which holds in a standard Java 17 environment.

### `Class.forName` and `ClassLoader.loadClass`

`Class.forName(String)` initializes the class; `ClassLoader.loadClass(String)` typically only loads the class without initializing it immediately. The `Class.forName(name, false, loader)` form allows requesting **no immediate initialization**. This matters because a class with a static initializer can cause side effects or fail during load/initialize.

Do not treat “loading a class” as a pure name check with no consequences in every API. When a class comes from an untrusted plugin or user configuration, evaluate the loader policy and the initialization process.

## 6. `NoSuchMethodException`: Wrong Method Signature Lookup

`Class.getMethod(name, parameterTypes...)` searches for a **public method** by name and parameter type list, including matching inherited public methods. `Class.getDeclaredMethod(name, parameterTypes...)` only searches for methods **declared directly in the class** being inspected, without searching superclasses; it can find private/protected/package-private methods.

Example:

```java
java.lang.reflect.Method method =
        String.class.getMethod("substring", int.class);
```

This is a valid code snippet inside a method that declares `throws NoSuchMethodException` or uses `try/catch`. `String.substring(int)` is a public method; the result is a `Method` object describing that method.

Wrong name or wrong parameters:

```java
String.class.getMethod("substring", String.class);
```

This snippet compiles, but **throws `NoSuchMethodException` at runtime**, because there is no matching public `substring(String)`.

### Parameter Types Must Be Exact

Method lookup via reflection relies on the **parameter types passed in** as `Class<?>` tokens:

- `int.class` is **different from** `Integer.class`.
- `String.class` is different from `Object.class`.
- Overloads with the same name but different parameter types are distinct methods.
- For arrays, use the matching array type, such as `String[].class`.
- `getMethod` does not guess an overload based on the values you plan to pass later to `invoke`.
- With generics, type erasure can cause the runtime parameter type to differ from how the type parameter is written in source.
- The return type is **not** part of the `getMethod` lookup argument list.

For example, `sum(int,int)` must be looked up with `getMethod("sum", int.class, int.class)`. Passing `Integer.class` will not be automatically unboxed during the **lookup phase**.

### Runnable Program: Public, Private, and Wrong Signature

Create file **`MethodLookupDemo.java`**:

```java
import java.lang.reflect.Method;

public class MethodLookupDemo {
    public static class Greeting {
        public String greet(String name) {
            return "Hello " + name;
        }

        private int code() {
            return 42;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Greeting target = new Greeting();

        Method publicMethod =
                Greeting.class.getMethod("greet", String.class);
        System.out.println("public="
                + publicMethod.invoke(target, "Java"));

        try {
            Greeting.class.getMethod("code");
        } catch (NoSuchMethodException failure) {
            System.out.println("getMethod private=not found");
        }

        Method privateMethod =
                Greeting.class.getDeclaredMethod("code");
        System.out.println("declared=" + privateMethod.getName());

        try {
            Greeting.class.getMethod("greet", int.class);
        } catch (NoSuchMethodException failure) {
            System.out.println("wrong signature=not found");
        }
    }
}
```

```bash
javac MethodLookupDemo.java
java MethodLookupDemo
```

`stdout`:

```text
public=Hello Java
getMethod private=not found
declared=code
wrong signature=not found
```

In this program:

1. `getMethod("greet", String.class)` succeeds because there is a public method matching the signature.
2. `getMethod("code")` fails because `code()` is private and not in the set of public methods searched by this API.
3. `getDeclaredMethod("code")` finds the **directly declared** private method, but finding it does not mean every caller is allowed to invoke it.
4. `getMethod("greet", int.class)` fails because `Greeting` has no `greet(int)` overload.

Do not substitute `ClassNotFoundException` for `NoSuchMethodException`: at this stage the class already exists, but the **member has the wrong name or signature**.

## 7. `getMethod` vs. `getDeclaredMethod` with Inheritance

For a subclass inheriting a public method:

- `Child.class.getMethod("inherited")` can succeed.
- `Child.class.getDeclaredMethod("inherited")` will not find it if the subclass **does not declare** that method itself.
- `getDeclaredMethod` can find a private method of the subclass itself that `getMethod` cannot see.
- `getMethods()` and `getDeclaredMethods()` have corresponding plural scopes; the returned array should not be relied upon for a stable default ordering.

### Standalone Program: Inherited Methods

Create file **`InheritedMethodLookupDemo.java`**:

```java
public class InheritedMethodLookupDemo {
    public static class Parent {
        public void inherited() {
        }
    }

    public static class Child extends Parent {
        private void local() {
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("public inherited="
                    + Child.class.getMethod("inherited").getName());
        } catch (NoSuchMethodException failure) {
            System.out.println("unexpected");
        }

        try {
            Child.class.getDeclaredMethod("inherited");
        } catch (NoSuchMethodException failure) {
            System.out.println("declared inherited=missing");
        }

        try {
            System.out.println("declared private="
                    + Child.class.getDeclaredMethod("local").getName());
        } catch (NoSuchMethodException failure) {
            System.out.println("unexpected");
        }
    }
}
```

```bash
javac InheritedMethodLookupDemo.java
java InheritedMethodLookupDemo
```

`stdout`:

```text
public inherited=inherited
declared inherited=missing
declared private=local
```

In class hierarchy examples, ask: *in which class is the method declared?* and *is the API asking for public/inherited or declared/direct?* This usually explains `NoSuchMethodException` faster than checking the same name repeatedly.

### Notes on Overloads, Bridge Methods, and Varargs

With generics, the compiler may generate **bridge methods** to preserve overriding after type erasure. `getDeclaredMethods()` may also expose synthetic/bridge members. Do not write a custom resolver that relies solely on the ordering of the reflection array. If you need to distinguish them, `Method.isBridge()` and `Method.isSynthetic()` are useful APIs.

Varargs are represented as **a single array parameter** at the signature level. For example, a method `log(String... parts)` uses `String[].class` during lookup, not an arbitrary number of `String.class` tokens.

## 8. `NoSuchFieldException`: Field Not Found in Scope

`Class.getField(name)` searches for a **public field** according to the API's lookup rules, including inherited public fields. `Class.getDeclaredField(name)` searches for a field **declared directly** in the class, regardless of modifier, but does not search superclasses.

Common mistakes:

- Confusing a field with a getter/setter (a JavaBean property is not necessarily a field).
- Misspelling the field name or using the wrong letter casing.
- The field is private, so `getField` cannot see it.
- The field is in a superclass, so `getDeclaredField` on the subclass cannot see it.
- Confusing a static field with an instance field during `Field.get`/`Field.set`.

### Runnable Program: Public and Private Fields

Create file **`FieldLookupDemo.java`**:

```java
import java.lang.reflect.Field;

public class FieldLookupDemo {
    public static class Box {
        public int count = 3;
        private String token = "secret";
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Box box = new Box();

        Field visible = Box.class.getField("count");
        System.out.println("count=" + visible.getInt(box));

        try {
            Box.class.getField("token");
        } catch (NoSuchFieldException failure) {
            System.out.println("public token=missing");
        }

        Field declared = Box.class.getDeclaredField("token");
        System.out.println("declared token=" + declared.getName());

        try {
            Box.class.getDeclaredField("unknown");
        } catch (NoSuchFieldException failure) {
            System.out.println("unknown=missing");
        }
    }
}
```

```bash
javac FieldLookupDemo.java
java FieldLookupDemo
```

`stdout`:

```text
count=3
public token=missing
declared token=token
unknown=missing
```

A field lookup failure throws `NoSuchFieldException`; once `Field` is found, calling `getInt`/`set` may encounter `IllegalAccessException` or `IllegalArgumentException` depending on permissions and receiver/type.

### `getField` and `getDeclaredField` Do Not Return the Field Value

They return a **`Field` metadata object**, not the value itself. You must use `field.get(receiver)`, `field.getInt(receiver)`, or the appropriate API to access the data. For an instance field, the receiver must have a compatible type. For a static field, the API allows a `null` receiver in the corresponding cases.

If a class has a public getter, calling the getter through a normal interface is often safer, more maintainable, and more type-safe than accessing a private field via reflection.

## 9. Missing Constructor: Still `NoSuchMethodException`

Constructor reflection uses `Class.getConstructor(parameterTypes...)` and `Class.getDeclaredConstructor(parameterTypes...)`.

- `getConstructor(...)` only searches for a matching **public constructor** in the target class.
- `getDeclaredConstructor(...)` searches for a constructor declared in that class, including private ones.
- Constructors **are not inherited**, so there is no “superclass constructor inherited by the subclass”.
- Failing to find a constructor matching the parameter list results in `NoSuchMethodException`; there is **no** `NoSuchConstructorException` class in this standard API.
- `newInstance(arguments...)` on the `Constructor` object is the step that **actually creates the object**.

### Runnable Program: Two Different Constructors

Create file **`ConstructorLookupDemo.java`**:

```java
import java.lang.reflect.Constructor;

public class ConstructorLookupDemo {
    public static class Config {
        private final String mode;

        public Config(String mode) {
            this.mode = mode;
        }

        private Config() {
            this.mode = "internal";
        }

        public String mode() {
            return mode;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<Config> publicConstructor =
                Config.class.getConstructor(String.class);
        Config created = publicConstructor.newInstance("production");
        System.out.println("public=" + created.mode());

        try {
            Config.class.getConstructor();
        } catch (NoSuchMethodException failure) {
            System.out.println("public empty=missing");
        }

        Constructor<Config> privateConstructor =
                Config.class.getDeclaredConstructor();
        System.out.println("declared empty="
                + privateConstructor.getParameterCount());
    }
}
```

```bash
javac ConstructorLookupDemo.java
java ConstructorLookupDemo
```

`stdout`:

```text
public=production
public empty=missing
declared empty=0
```

`getDeclaredConstructor()` **finds** the private no-arg constructor. The example intentionally does not attempt to invoke it here so as not to mix *lookup* errors with *access* issues. When there is a valid reason to invoke a non-public constructor, you must check access/module policies as covered in the following sections.

### Avoid `Class.newInstance()`

`Class.newInstance()` is deprecated in modern Java. Prefer:

```java
Object value = type.getDeclaredConstructor().newInstance();
```

This is a **code snippet** where `type` has type `Class<?>`. Using `Constructor.newInstance` cleanly separates lookup, access checks, and the `InvocationTargetException` wrapper, avoiding the dangerous behavior of `Class.newInstance()` where exceptions from the constructor propagate out in a way that bypasses checked exception handling.

## 10. `IllegalAccessException`: Finding It Does Not Mean You Can Call It

Reflection still respects Java access checks unless an appropriate mechanism is permitted. A `Method`, `Field`, or `Constructor` object can be looked up successfully and still **not be accessible** from the caller.

`IllegalAccessException` is a **checked exception** that can occur when:

- `Method.invoke(...)` tries to call a method the caller cannot access.
- `Constructor.newInstance(...)` tries to call a constructor without permission.
- `Field.get(...)`/`Field.set(...)` accesses a field without sufficient privileges.

### Runnable Program: Looking Up a Private Method and Attempting Access

Create file **`ReflectionAccessDemo.java`**:

```java
import java.lang.reflect.Method;

class PrivateVault {
    private String secret() {
        return "vault-value";
    }
}

public class ReflectionAccessDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        PrivateVault vault = new PrivateVault();
        Method secret =
                PrivateVault.class.getDeclaredMethod("secret");

        try {
            secret.invoke(vault);
        } catch (IllegalAccessException failure) {
            System.out.println("before=IllegalAccessException");
        }

        boolean opened = secret.trySetAccessible();
        System.out.println("trySetAccessible=" + opened);

        if (opened) {
            System.out.println("after=" + secret.invoke(vault));
        }
    }
}
```

```bash
javac ReflectionAccessDemo.java
java ReflectionAccessDemo
```

`stdout` in a typical Java 17 application running **on the classpath, in the unnamed module**:

```text
before=IllegalAccessException
trySetAccessible=true
after=vault-value
```

Subtle detail: `PrivateVault` is a separate top-level class, **not a nested class in the same nest** as `ReflectionAccessDemo`. Therefore, the caller code does not have direct permission to call the private `secret()` method before opening accessibility. In the same unnamed module in this example, `trySetAccessible()` can enable access.

**Do not generalize this output to every module setup.** In a named module where the package is not `opens` to the calling module, `trySetAccessible()` may return `false`. `setAccessible(true)` can throw `InaccessibleObjectException` (unchecked). With a `SecurityManager`/security policy in an applicable environment, `SecurityException` may also occur.

### `setAccessible(true)` Is Not a Skeleton Key for All Permissions

Since Java 9, the **Java Platform Module System (JPMS)** enforces strong encapsulation. There are cases where deep access to private members of another module is not permitted, even when the class and method have already been found.

- `getDeclaredMethod` only looks up metadata.
- `trySetAccessible` requests relaxed access and returns `true` if successful; it can return `false` when not possible.
- `setAccessible(true)` can throw `InaccessibleObjectException` when opening is not allowed.
- A module providing a public API should `exports` the appropriate package if external users need it.
- Deep reflection into non-public members across modules generally requires the package to be `opens` by design or via appropriate runtime configuration.

In application libraries, **prefer public APIs and interfaces** rather than relying on opening private members; do not advise overusing `--add-opens` merely to avoid fixing a broken access design.

## 11. `InvocationTargetException`: The Target Method or Constructor Threw an Error

This is a very common point of confusion.

Suppose the target method has the code:

```java
public void work() {
    throw new IllegalStateException("business failed");
}
```

If called normally, the caller receives `IllegalStateException` directly. However, when called via:

```java
method.invoke(target);
```

the **error thrown by the target method** is wrapped by `Method.invoke` in an `InvocationTargetException`. The caller needs to read `getCause()` or `getTargetException()` on the wrapper to see what the actual target error is.

Do not state that “`InvocationTargetException` always means the lookup failed”. Usually the lookup succeeded; the **target invocation** happened and the target code failed.

### Runnable Program: `RuntimeException` and Checked `IOException`

Create file **`InvocationTargetDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationTargetDemo {
    public static class Worker {
        public void failRuntime() {
            throw new IllegalStateException("invalid state");
        }

        public void failChecked() throws IOException {
            throw new IOException("disk failed");
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Worker target = new Worker();

        Method runtime =
                Worker.class.getMethod("failRuntime");
        try {
            runtime.invoke(target);
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println("runtime wrapper="
                    + wrapper.getClass().getSimpleName());
            System.out.println("runtime cause="
                    + cause.getClass().getSimpleName());
            System.out.println("runtime message=" + cause.getMessage());
        }

        Method checked =
                Worker.class.getMethod("failChecked");
        try {
            checked.invoke(target);
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getTargetException();
            System.out.println("checked cause="
                    + cause.getClass().getSimpleName());
            System.out.println("checked message=" + cause.getMessage());
        }
    }
}
```

```bash
javac InvocationTargetDemo.java
java InvocationTargetDemo
```

`stdout`:

```text
runtime wrapper=InvocationTargetException
runtime cause=IllegalStateException
runtime message=invalid state
checked cause=IOException
checked message=disk failed
```

Explanation:

1. `getMethod(...)` finds the public method; there is no `NoSuchMethodException` on the success path.
2. `invoke(...)` actually executes the method body.
3. The body throws `IllegalStateException` in the first case and `IOException` in the second.
4. `Method.invoke` wraps the target `Throwable` in `InvocationTargetException`.
5. `getCause()` and `getTargetException()` retrieve the **original `Throwable` object** thrown by the target.

If a constructor is called via `Constructor.newInstance(...)` and the **constructor body** throws an exception, it can also be wrapped in `InvocationTargetException`. However, if the class is abstract and cannot be instantiated, you may receive `InstantiationException` before the constructor body has a chance to run.

### Do Not Automatically Assume `cause` Is “Unchecked”

The error in `InvocationTargetException#getCause()` can be checked, unchecked, or an `Error`. Reflection does not erase the runtime class of the target throwable. When translating the error into a domain exception, preserve the proper `cause` if you must wrap it further.

## 12. `InstantiationException`: The Class Cannot Be Instantiated

`InstantiationException` is a checked exception in the `ReflectiveOperationException` branch. A familiar scenario is attempting to instantiate an **abstract class** via reflection.

- `AbstractType.class.getDeclaredConstructor()` can **find the constructor**.
- However, `constructor.newInstance()` cannot create a direct instance of an abstract class → `InstantiationException`.
- This is a failure **at the object creation step**, not a `NoSuchMethodException` from the lookup step.

### Runnable Program: Abstract Class

Create file **`InstantiationReflectionDemo.java`**:

```java
import java.lang.reflect.Constructor;

public class InstantiationReflectionDemo {
    public static abstract class AbstractTask {
        public AbstractTask() {
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<AbstractTask> constructor =
                AbstractTask.class.getDeclaredConstructor();

        System.out.println("constructor found");

        try {
            constructor.newInstance();
        } catch (InstantiationException failure) {
            System.out.println("instantiate="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac InstantiationReflectionDemo.java
java InstantiationReflectionDemo
```

`stdout`:

```text
constructor found
instantiate=InstantiationException
```

If a class has a public no-arg constructor and is an appropriate concrete class, `Constructor.newInstance()` can create an instance. Still, the constructor can execute business logic and fail, in which case the error from the body is wrapped as `InvocationTargetException`.

**Do not merely check “does a constructor exist” and conclude “instantiation will definitely succeed”.** You also have to account for abstract classes, access permissions, arguments, initialization, and environment conditions.

## 13. `IllegalArgumentException`: Wrong Target or Argument List

Most errors caused by passing an invalid receiver or arguments when calling **invoke** are represented by **unchecked** exceptions, not `ReflectiveOperationException`. For example:

- Passing a `String` as the target to an instance method belonging to `Worker`.
- Calling a method that takes two parameters while passing only one.
- Passing `null` for a required primitive parameter.
- Passing a type that cannot be converted under `Method.invoke` rules.
- Calling a constructor with an incompatible number of arguments.

At lookup:

```java
Method method = Calculator.class.getMethod(
        "add", int.class, int.class);
```

Then at invocation:

```java
method.invoke(new Calculator(), "bad", 2);
```

These are **two illustrative code snippets** assuming a `Calculator` class with public `add(int,int)`. The lookup can **succeed**, but invoking with `"bad"` is incompatible with `int` and causes `IllegalArgumentException` — not `NoSuchMethodException`.

### Runnable Program: Do Not Equate Wrong `invoke` with Wrong Lookup

Create file **`InvocationArgumentsDemo.java`**:

```java
import java.lang.reflect.Method;

public class InvocationArgumentsDemo {
    public static class Calculator {
        public int add(int a, int b) {
            return a + b;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method add = Calculator.class.getMethod(
                "add", int.class, int.class);

        System.out.println("correct="
                + add.invoke(new Calculator(), 3, 4));

        try {
            add.invoke(new Calculator(), "wrong", 4);
        } catch (IllegalArgumentException failure) {
            System.out.println("bad args=IllegalArgumentException");
        }

        try {
            Calculator.class.getMethod(
                    "add", Integer.class, Integer.class);
        } catch (NoSuchMethodException failure) {
            System.out.println("wrong lookup=NoSuchMethodException");
        }
    }
}
```

```bash
javac InvocationArgumentsDemo.java
java InvocationArgumentsDemo
```

`stdout`:

```text
correct=7
bad args=IllegalArgumentException
wrong lookup=NoSuchMethodException
```

In the valid invocation, the two `Integer` arguments from autoboxing can be used for the `int` parameters under `Method.invoke` unwrapping/widening rules. However, **`getMethod` does not perform autoboxing when looking up signatures**: `int.class` is different from `Integer.class`.

**Remember the distinction:** wrong signature in `getMethod` → `NoSuchMethodException`; method already found but wrong arguments passed to `invoke` → typically `IllegalArgumentException`.

## 14. Class Initialization and Linkage Errors Are Not Fully Covered

Even when `Class.forName` receives a valid name, **class initialization** can fail in a static initializer. That can throw `ExceptionInInitializerError`, which belongs to the `Error` branch, not `ReflectiveOperationException`.

Some types to recognize:

| Situation | Typical Result / Error Type | Under `ReflectiveOperationException`? |
| --- | --- | --- |
| Class loader cannot find the class in `Class.forName` | `ClassNotFoundException` | Yes |
| A required class cannot be linked/defined | `NoClassDefFoundError` or appropriate `LinkageError` | No |
| Class static initializer throws an unhandled error | `ExceptionInInitializerError` or corresponding initialization error | No |
| Method/constructor called via reflection throws on its own | `InvocationTargetException` wrapping the target error | Wrapper is yes |
| `setAccessible(true)` rejected by module | `InaccessibleObjectException` | No |
| Wrong argument at `Method.invoke` | `IllegalArgumentException` | No |

**Do not lump everything into `ClassNotFoundException`** or catch `ReflectiveOperationException` and assume the program has no remaining runtime errors.

### How Does `Class.forName(name, false, loader)` Help?

It lets you request **not to initialize the class immediately**. However, loading/linking can still fail according to the loader's contract. When the class is later initialized upon use, initializer errors can still happen. It is a tool for controlling initialization timing, not for “disabling all class errors”.

If creating a plugin from a user-supplied class name, you should consider *which class loader is used*, whether the class implements the expected interface, and when plugin code is allowed to execute.

## 15. Designing Type-Safe Factories with `Class<T>`

Reflection often returns `Object`, which easily leads to unsafe casts. If an API needs to create objects belonging to a specific interface or supertype, you can use `Class<? extends T>` or check `Class.asSubclass(...)` to enforce a type contract.

Simple factory method example:

```java
static <T> T instantiate(Class<? extends T> type)
        throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
```

This is a **valid method snippet**. It only works for classes with a no-arg constructor **that the caller is permitted to access**, not every arbitrary class. It can throw `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException`, and `InvocationTargetException` depending on the situation.

### Runnable Program: Typed Factory

Create file **`TypedReflectionFactoryDemo.java`**:

```java
public class TypedReflectionFactoryDemo {
    public interface Job {
        String run();
    }

    public static class GreetingJob implements Job {
        public GreetingJob() {
        }

        @Override
        public String run() {
            return "job completed";
        }
    }

    static <T> T instantiate(Class<? extends T> type)
            throws ReflectiveOperationException {
        return type.getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args) {
        try {
            Job job = instantiate(GreetingJob.class);
            System.out.println("result=" + job.run());

            Class<?> loaded = Class.forName(
                    TypedReflectionFactoryDemo.GreetingJob.class.getName());
            Class<? extends Job> jobType =
                    loaded.asSubclass(Job.class);
            Job another = instantiate(jobType);
            System.out.println("dynamic=" + another.run());
        } catch (ReflectiveOperationException failure) {
            System.out.println("reflection failed");
        }
    }
}
```

```bash
javac TypedReflectionFactoryDemo.java
java TypedReflectionFactoryDemo
```

`stdout`:

```text
result=job completed
dynamic=job completed
```

Explanation:

1. `instantiate(GreetingJob.class)` preserves the contract of returning a `Job`.
2. `Class.forName(...)` represents loading the class by name at runtime.
3. `loaded.asSubclass(Job.class)` verifies that the class is actually a subtype of `Job`.
4. `instantiate(jobType)` creates the object after the subtype check.
5. If the loaded class is not a `Job`, `asSubclass` can throw **`ClassCastException` (unchecked)**; generics do not automatically eliminate all runtime errors.

A production factory also needs to control the **list of allowed classes**, constructor parameters, module access, resource lifecycles, and the fact that constructor code can execute side effects.

### Do Not Load Arbitrary Classes from Untrusted Data

Class names from untrusted configuration or requests can cause the program to load and execute unintended code on the deployed classpath. Even if `Class.forName` finds the class successfully, that **does not prove the class is safe to instantiate**. Use an allowlist, specific interfaces, an appropriate class loader, and permission checks at plugin boundaries.

## 16. Wrapping Exceptions Properly Across Abstraction Layers

In internal API layers, using `throws ReflectiveOperationException` can be reasonable. At business boundaries, however, callers usually do not need to know that a framework is using reflection.

Example of translating the error into a domain exception:

```java
try {
    return instantiate(type);
} catch (ReflectiveOperationException original) {
    throw new IllegalStateException(
            "Cannot create configured service", original);
}
```

This is a **code snippet** assuming `instantiate` and `type` are declared. The `(message, cause)` constructor preserves `original` as the `cause`.

If `original` is an `InvocationTargetException`, the actual cause from the target method/constructor may be at:

```java
original.getCause()
```

However, do not assume every `ReflectiveOperationException` has a cause. For instance, a `NoSuchMethodException` from a bad lookup may have no cause. Good diagnostic tooling should read the **exception type, message, cause, and suppressed exceptions**, rather than calling `getCause().getMessage()` without a null check.

### What Should You Do When Handling `InvocationTargetException`?

There are three valid policies depending on the layer:

1. **Keep the wrapper as-is** as the cause of the domain error: preserves the full reflective invocation context and the target cause.
2. **Unwrap the cause** when you genuinely want to propagate the original business error: you must account for the fact that it could be an `Exception`, `RuntimeException`, or `Error`, while preserving stack traces and suppressed exceptions.
3. **Classify specifically** by target throwable type to decide whether to retry, stop, or recover.

Do not blindly write `throw (Exception) wrapper.getCause()`: this cast can fail if the cause is an `Error`. Likewise, do not replace all errors with `new RuntimeException(wrapper.getMessage())`, because that loses the target cause.

## 17. Summary Program: Classifying Lookup Failures and Target Failures

Create file **`ReflectionFailureDecisionDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFailureDecisionDemo {
    public static class Handler {
        public void run() {
            throw new IllegalArgumentException("invalid request");
        }
    }

    static void call(String methodName)
            throws ReflectiveOperationException {
        Method method =
                Handler.class.getMethod(methodName);
        method.invoke(new Handler());
    }

    public static void main(String[] args) {
        for (String name : new String[] {"missing", "run"}) {
            try {
                call(name);
            } catch (NoSuchMethodException failure) {
                System.out.println(name + ": method not found");
            } catch (InvocationTargetException failure) {
                System.out.println(name + ": target threw "
                        + failure.getCause()
                                .getClass().getSimpleName());
            } catch (ReflectiveOperationException failure) {
                System.out.println(name + ": other reflection failure");
            }
        }
    }
}
```

```bash
javac ReflectionFailureDecisionDemo.java
java ReflectionFailureDecisionDemo
```

`stdout`:

```text
missing: method not found
run: target threw IllegalArgumentException
```

`NoSuchMethodException` in the first iteration occurs **before invocation**. In the next iteration, lookup succeeds; `Handler.run()` throws `IllegalArgumentException` and `Method.invoke` wraps it in `InvocationTargetException`. The two failures require different diagnostics.

**Do not reverse the catch order**: `catch (ReflectiveOperationException)` must come **after** the subtype handlers if you want separate classification. If placed first, the subtype branches become unreachable and `javac` may report an unreachable catch block.

## 18. Checklist for Handling Reflection Failures in Applications

| Question | What to Check |
| --- | --- |
| Class not found? | Binary name, package, classpath/module path, class loader |
| Method not found? | `getMethod` vs `getDeclaredMethod`, name, overload, `int.class`/`Integer.class`, type erasure |
| Field not found? | `getField` vs `getDeclaredField`, field vs JavaBean property, declaring class |
| Constructor not found? | Public/declared, exact parameters, whether class has a matching constructor |
| Found but cannot invoke? | Java access modifiers, receiver, named module, `exports`/`opens` |
| `Method.invoke` throws `InvocationTargetException`? | Inspect `getCause()`/`getTargetException()`; error is in target code |
| `Constructor.newInstance` throws `InstantiationException`? | Abstract/non-instantiable class |
| `invoke` throws `IllegalArgumentException`? | Wrong receiver, arg count/types, primitive conversion |
| `Class.forName` causes `ExceptionInInitializerError`? | Static initializer and runtime conditions, not just class lookup |
| Is catching only `ReflectiveOperationException` enough? | No; define a policy for unchecked exceptions and `Error` |
| How should it be logged? | Log the full `Throwable`, cause/suppressed, and add safe context |
| Where does class configuration come from? | Validation, allowlist, restricting execution/instantiation permissions |
| Can reflection be avoided? | Interfaces, explicit factories, `ServiceLoader`, public APIs |

**Do not overuse broad catches that return fake success.** Method/constructor configuration errors are important signals of version incompatibility or a broken API contract. Report failures with sufficient context rather than just printing a stack trace and ignoring the result.

## 19. Common Misconceptions

**“`ReflectiveOperationException` is unchecked.”** False. It extends `Exception` and is a checked exception.

**“`catch (ReflectiveOperationException)` catches all reflection errors.”** False. `IllegalArgumentException`, `InaccessibleObjectException`, `ExceptionInInitializerError`, and `LinkageError` are outside this branch.

**“`ClassNotFoundException` and `NoClassDefFoundError` are the same error class.”** False. One is a checked subtype of `ReflectiveOperationException`, and the other is an `Error`.

**“`getDeclaredMethod` also searches inherited methods.”** False. It searches members declared directly in the class being inspected.

**“`getMethod` can find private methods if you know the exact name.”** False. It searches public methods within its API scope.

**“If `getDeclaredMethod` finds a private method, it can definitely be called right away.”** False. Metadata lookup and invocation permission are two separate steps.

**“`getMethod("sum", Integer.class)` finds `sum(int)` via autoboxing.”** False. Reflection method lookup requires exact matching parameter type tokens.

**“Missing a no-arg constructor throws `NoSuchFieldException`.”** False. Use `getDeclaredConstructor()` and expect `NoSuchMethodException`.

**“There is a dedicated `NoSuchConstructorException` class.”** False in the standard reflection API used in this lesson. Constructor lookup fails with `NoSuchMethodException`.

**“`InvocationTargetException` means the method does not exist.”** False. The method was usually found and the target code actually threw an error.

**“`InvocationTargetException#getCause()` is always a `RuntimeException`.”** False. The target can throw a checked exception or an `Error`.

**“`Method.invoke` with wrong arguments throws `NoSuchMethodException`.”** False. Once `Method` has been obtained, invalid arguments typically cause `IllegalArgumentException`.

**“`InstantiationException` means no constructor was found.”** False. A constructor may be found, yet an abstract class cannot be instantiated.

**“`setAccessible(true)` always bypasses every barrier in Java 17.”** False. Named modules enforce strong encapsulation.

**“`getDeclaredField("name")` returns the field value.”** False. It returns `Field` metadata; you must use `get`/`getInt` with an appropriate receiver.

**“`Class.newInstance()` is still the preferred way in modern Java.”** False. It is deprecated; prefer `getDeclaredConstructor().newInstance()`.

**“Wrapping a reflection error with a new message automatically keeps the cause.”** False. You must pass the original exception object to a constructor that accepts a cause.

**“`Class.forName` only looks up metadata and cannot trigger code.”** False for the default overload: class initialization can execute static initializers.

**“A class name that loads successfully means the plugin is definitely safe.”** False. Instantiating objects and running code can cause side effects; you must verify allowed types and permissions.

**“A broad catch that returns null keeps the system running.”** It can hide critical configuration errors and cause a `NullPointerException` later. Use an explicit recovery policy.

## 20. Self-Check Exercises

1. **Is `ReflectiveOperationException` checked or unchecked?** Checked.
2. **Which APIs typically throw `ClassNotFoundException`?** `Class.forName(...)` or `ClassLoader.loadClass(...)` when the class cannot be found.
3. **What happens when failing to find a public method named `run` with `getMethod`?** `NoSuchMethodException`.
4. **Does `getDeclaredMethod` on a subclass automatically search methods in the superclass?** No.
5. **Can a private method be found via `getMethod`?** No, unless there is another matching public method.
6. **Does `getDeclaredMethod` finding a private method mean it can be invoked?** No, access permissions still apply.
7. **What is thrown when no matching constructor is found with `getConstructor`?** `NoSuchMethodException`.
8. **Do `getField("x")` and `getDeclaredField("x")` have the same scope?** No; public/inherited differs from declared/direct.
9. **When `Method.invoke` calls a target that throws `IOException`, what wrapper does the caller receive?** `InvocationTargetException`, with the target `IOException` as its cause.
10. **How do you retrieve the original `Throwable` from `InvocationTargetException`?** `getCause()` or `getTargetException()`.
11. **If an abstract class has a constructor that is found, will `newInstance` always succeed?** No, it can throw `InstantiationException`.
12. **If a method has an `int` parameter, does looking it up with `Integer.class` match automatically?** No.
13. **Does `Method.invoke` with a wrong target type typically throw checked `NoSuchMethodException` or unchecked `IllegalArgumentException`?** Typically unchecked `IllegalArgumentException`.
14. **Does `trySetAccessible()` always return `true` in a closed named module?** No; it can return `false`.
15. **What can `setAccessible(true)` throw when rejected by strong encapsulation?** `InaccessibleObjectException` (unchecked).
16. **Does `ExceptionInInitializerError` belong to `ReflectiveOperationException`?** No; it belongs to the `Error` branch.
17. **Does catching only `ReflectiveOperationException` catch `ClassCastException` caused by casting the result to the wrong type?** No.
18. **Why should `Class.forName("...")` be evaluated with static initialization in mind?** The single-argument overload can initialize the class and run initializers.
19. **Does `getDeclaredMethods()` guarantee an array order for your resolver?** No ordering should be assumed.
20. **What problem does a generic factory with `Class<? extends T>` solve?** It increases type safety when creating subtypes, though lookup/access/invocation failures must still be handled.
21. **How do you report a business error from `ReflectiveOperationException` while still diagnosing the original error?** Wrap it with a cause: `new DomainException("context", original)`.
22. **Can the target error inside `InvocationTargetException` carry its own suppressed exceptions?** Yes, because it remains the original `Throwable` object.
23. **If an interface or public factory suffices, is reflection better by default?** No; prefer static APIs when appropriate.
24. **What is the most important information when debugging `NoSuchMethodException`?** Class name, method name, exact parameter type list, and lookup scope.
25. **If a plugin class exists but does not implement the required interface, what can `Class.asSubclass` cause?** `ClassCastException` (unchecked).

## 21. Official Java 17 Documentation

- [Java SE 17 — ReflectiveOperationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ReflectiveOperationException.html): checked supertype of common reflection errors.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName`, `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredConstructor`, `asSubclass`.
- [Java SE 17 — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html): error loading a class by name.
- [Java SE 17 — NoSuchMethodException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodException.html): method/constructor lookup error.
- [Java SE 17 — NoSuchFieldException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchFieldException.html): field lookup error.
- [Java SE 17 — IllegalAccessException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html): access permission for reflective operations.
- [Java SE 17 — InstantiationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InstantiationException.html): error when an object cannot be instantiated.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke`, `isBridge`, `isSynthetic`.
- [Java SE 17 — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `get`, `set`, access control.
- [Java SE 17 — Constructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): constructor lookup and `newInstance`.
- [Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapper for throwables from target invocation.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible`, strong encapsulation.
- [Java SE 17 — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): runtime error when a module disallows opening access.
- [Java Language Specification 17 — `11 Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked exceptions.
- [Java Language Specification 17 — `12 Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization, and related errors.

**Remember:** `ReflectiveOperationException` is the **checked superclass** for many reflection lookup and usage errors. `ClassNotFoundException` is a class lookup failure; `NoSuchMethodException`/`NoSuchFieldException` are member lookup failures; `IllegalAccessException` is a member access permission failure; `InstantiationException` is an object creation failure; and `InvocationTargetException` wraps an error **actually thrown by the target method/constructor**. Distinguish lookup from invocation, use `getMethod`/`getDeclaredMethod` and parameter type tokens properly, respect Java 17 access/module rules, and keep in mind that runtime errors like `InaccessibleObjectException` or `IllegalArgumentException` are **not** automatically covered by `catch (ReflectiveOperationException)`.
