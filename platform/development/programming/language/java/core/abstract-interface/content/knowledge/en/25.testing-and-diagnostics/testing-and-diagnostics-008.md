# Distinguishing Compile-Time Errors from AbstractMethodError, InstantiationError, and Linkage Errors

When working with abstract classes and interfaces in Java, it is necessary to distinguish errors detected by the compiler from source code from linkage errors that occur when the JVM runs bytecode. The two groups of errors can stem from similar design issues, but the time of detection and diagnostic approach differ.

- **Compile-time error:** `javac` cannot generate valid bytecode from source code, for example when a concrete class has not implemented all abstract methods or the program attempts to instantiate an abstract class directly.
- **`AbstractMethodError`:** The JVM is executing a method call, but the actual class does not have the concrete implementation required for the resolved method. A common case is when classes were compiled at different times or against different API versions.
- **`InstantiationError`:** Bytecode attempts to create an instance of a class whose version currently loaded by the JVM is abstract. Newly compiled source code would normally be rejected before generating such bytecode; this error usually suggests a mismatch between class versions.
- **`LinkageError`:** A lower-level group of errors that occurs when the JVM loads, links, or uses incompatible types. Both `AbstractMethodError` and `InstantiationError` belong to the `LinkageError` branch.

An important diagnostic principle is to check **which bytecode was compiled against which API version, and which class version is actually loaded by the JVM at runtime**. You should not treat these runtime errors like ordinary syntax errors or try to fix them by adding a random method without first identifying the cause.

## 1. Overview: At Which Stage Do Errors Appear?

A Java program typically goes through the following stages: compiling source code, loading classes, linking and initializing classes, and then executing statements. These stages are related, but they are not the same.

| Error Type | When It Typically Occurs | Typical Example |
|---|---|---|
| Compile-time error | When running `javac` | Instantiating an abstract class; a concrete class missing an abstract method |
| `AbstractMethodError` | When a method call is executed | Bytecode expects a method, but the actual class does not provide an implementation |
| `InstantiationError` | When an instantiation instruction is executed | Bytecode uses `new` on a class that is now abstract |
| `NoSuchMethodError` | When the JVM resolves a method call | Compiled code calls a method that no longer exists in the running library version |
| `NoClassDefFoundError` | When the JVM needs a class but cannot use the required definition | The class was present at compile time but is missing at runtime, or previous class initialization failed |
| `IncompatibleClassChangeError` | When a member's kind or structure has changed in a way bytecode does not expect | Incompatible change to a member or type |
| `VerifyError` | When bytecode fails verification checks | Invalid bytecode or bytecode that fails to satisfy JVM constraints |

This table shows the typical timing, not every possible execution path. Some linkage errors are detected when a class is loaded or when a member is first used, so the exact timing depends on the bytecode and how the JVM performs loading and resolution.

## 2. Compile-Time Errors Related to Abstract Classes and Interfaces

The compiler checks language rules based on the source code and the type definitions visible on the classpath at compile time.

### Instantiating an Abstract Class Directly

The following example does not compile:

~~~java
abstract class Shape {
    abstract double area();
}

class Demo {
    public static void main(String[] args) {
        Shape shape = new Shape(); // Compile-time error
    }
}
~~~

An abstract class can contain unimplemented methods, so you cannot create an instance of it directly. Create a concrete subclass and implement the abstract methods:

~~~java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

public class ShapeDemo {
    public static void main(String[] args) {
        Shape shape = new Circle(2.0);
        System.out.printf("%.2f%n", shape.area());
    }
}
~~~

Save the code in **ShapeDemo.java**, then compile and run it with Java 17 or later:

~~~bash
javac ShapeDemo.java
java ShapeDemo
~~~

Stdout output:

~~~text
12.57
~~~

A variable with reference type `Shape` can still point to a `Circle` object. What is forbidden is creating an instance directly from an abstract class, not using an abstract class as a reference type.

### A Concrete Class Not Implementing All Abstract Methods

~~~java
abstract class Shape {
    abstract double area();
}

class Square extends Shape {
    // Missing area(), so this concrete class does not compile.
}
~~~

To be valid, `Square` must implement `area()`, or `Square` itself must be declared `abstract`. The compiler typically reports that the non-abstract class has not overridden the abstract method in the superclass.

### Invalid Override Signature

~~~java
abstract class Reader {
    abstract String read();
}

class FileReaderImpl extends Reader {
    @Override
    int read() { // Error: incompatible return type
        return 1;
    }
}
~~~

Such a signature error is detected at compile time. For reference return types, Java allows covariant return types in certain cases, but primitive return types must match; override rules also cover access levels and checked exceptions.

These examples differ fundamentally from `AbstractMethodError`: when all source code is visible and consistent, `javac` prevents common contract errors before the program runs.

## 3. What Is LinkageError?

`java.lang.LinkageError` is an `Error` class for linking issues between type definitions or components that the JVM needs to use. These issues typically appear when bytecode is compiled against one version of a library but run against another, or when the classpath contains incompatible versions.

An important part of the hierarchy:

~~~text
java.lang.Error
└── java.lang.LinkageError
    └── java.lang.IncompatibleClassChangeError
        ├── java.lang.AbstractMethodError
        └── java.lang.InstantiationError
~~~

Beyond this branch, there are other kinds of linkage errors—for example, `NoSuchMethodError`, `NoSuchFieldError`, `NoClassDefFoundError`, and `VerifyError` reside in related branches of `LinkageError`. Not every runtime error is a linkage error: `NullPointerException`, `IllegalArgumentException`, and `ClassCastException` have different causes and hierarchies.

Because `LinkageError` is an `Error`, you should generally not catch it broadly to keep running as if it were a recoverable business error. In application code, the appropriate approach is usually to diagnose and fix the classpath, dependency versions, or bytecode compatibility. Catching a specific error type can be useful in demonstration programs or diagnostic tools, but it is no substitute for fixing the cause.

## 4. AbstractMethodError: When a Call Cannot Find a Concrete Implementation

`AbstractMethodError` is a subclass of `IncompatibleClassChangeError`. This error can appear when code was compiled against a method contract, but the actual class at runtime does not provide the concrete implementation required by the call.

A common scenario is **binary incompatibility**: the API version changes after the implementing class has already been compiled, without recompiling the implementing class. For example, a new abstract method is added to an abstract class. The old subclass may still be loaded by the JVM in some cases, but when new code calls the new method on an instance of the old subclass, the JVM can throw `AbstractMethodError`.

This differs from compiling all current source code together. If the subclass is recompiled against the new abstract method without implementing it and remains declared concrete, `javac` will reject the program. The runtime error appears because the old bytecode is not rechecked the way a fresh source compilation against all current definitions would be.

## 5. Reproducing AbstractMethodError with Two API Versions

This example intentionally creates two versions of the same abstract class to demonstrate the mismatch between a new API and an old implementing class. Do not use such a multi-version layout in normal applications; this is a diagnostic exercise.

Directory structure:

~~~text
abstract-method-demo/
├── src-v1/
│   └── demo/
│       ├── Base.java
│       └── Impl.java
├── src-v2/
│   └── demo/
│       ├── Base.java
│       └── Client.java
└── build/
~~~

Version 1, file **src-v1/demo/Base.java**:

~~~java
package demo;

public abstract class Base {
    public abstract void run();
}
~~~

Version 1, file **src-v1/demo/Impl.java**:

~~~java
package demo;

public final class Impl extends Base {
    @Override
    public void run() {
        System.out.println("old run");
    }
}
~~~

Compile the old API and implementation:

~~~bash
javac -d build/v1 src-v1/demo/Base.java src-v1/demo/Impl.java
~~~

Now API version 2 adds a new abstract method. File **src-v2/demo/Base.java**:

~~~java
package demo;

public abstract class Base {
    public abstract void run();
    public abstract void close();
}
~~~

File **src-v2/demo/Client.java**:

~~~java
package demo;

public final class Client {
    public static void main(String[] args) throws ReflectiveOperationException {
        Base target = (Base) Class.forName("demo.Impl")
                .getDeclaredConstructor()
                .newInstance();

        try {
            target.close();
        } catch (AbstractMethodError error) {
            System.out.println(error.getClass().getSimpleName());
        }
    }
}
~~~

Compile API version 2 and the client against the new API:

~~~bash
javac -d build/v2 src-v2/demo/Base.java
javac -cp build/v2 -d build/v2 src-v2/demo/Client.java
~~~

Run with the new API first and the old implementation second on the classpath. On Linux/macOS, the classpath separator is a colon:

~~~bash
java -cp "build/v2:build/v1" demo.Client
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
java -cp "build/v2;build/v1" demo.Client
~~~

Stdout output:

~~~text
AbstractMethodError
~~~

In this run, the JVM loads version 2 of `demo.Base` but loads `demo.Impl` compiled against version 1. `Impl` has an implementation for `run()` but has no implementation for `close()`. Calling `target.close()` therefore causes an `AbstractMethodError`, which the example catches specifically just to print the error class name.

The real fix is to synchronize the API version and implementations: implement the new method, recompile dependent modules, inspect packaged artifacts, and remove old class versions from the classpath. You should not simply catch `AbstractMethodError` and ignore the call, because the required business behavior may not have been executed.

## 6. InstantiationError: Bytecode Instantiating a Class That Is Now Abstract

`InstantiationError` is also a subclass of `IncompatibleClassChangeError`. It can occur when bytecode contains an instantiation operation for a class, but the definition loaded by the JVM at runtime has become abstract.

In source code compiled against the new definition, the statement `new SomeAbstractClass()` is invalid and rejected by `javac`. However, if a client was compiled when the class was still concrete, the old bytecode can still contain the `new` instruction. When the runtime replaces that class definition with an incompatible abstract version, the instantiation instruction can throw `InstantiationError`.

## 7. Reproducing InstantiationError with Mismatched Class Versions

Version 1, file **src-v1/demo/Product.java**:

~~~java
package demo;

public class Product {
    public Product() {
    }
}
~~~

Version 1, file **src-v1/demo/Client.java**:

~~~java
package demo;

public final class Client {
    public static void main(String[] args) {
        try {
            new Product();
            System.out.println("created");
        } catch (InstantiationError error) {
            System.out.println(error.getClass().getSimpleName());
        }
    }
}
~~~

Compile both the client and the original concrete class:

~~~bash
javac -d build/v1 src-v1/demo/Product.java src-v1/demo/Client.java
~~~

Version 2, replace **src-v2/demo/Product.java** with an abstract class:

~~~java
package demo;

public abstract class Product {
    public Product() {
    }

    public abstract void execute();
}
~~~

Compile the new class version into a separate directory:

~~~bash
javac -d build/v2 src-v2/demo/Product.java
~~~

Run the old client with the new class first on the classpath. On Linux/macOS:

~~~bash
java -cp "build/v2:build/v1" demo.Client
~~~

On Windows:

~~~powershell
java -cp "build/v2;build/v1" demo.Client
~~~

Stdout output:

~~~text
InstantiationError
~~~

The client was compiled when `Product` was still a concrete class, so its bytecode has an instantiation operation. At runtime, the JVM finds version 2 of `Product`, which is now abstract, and cannot perform that operation.

To fix this, synchronize the client and dependencies with the current API. If `Product` was intentionally made abstract, the client must instantiate an appropriate concrete subclass instead of continuing to instantiate `Product` directly. For normal releases, build and deploy compatible artifacts together, and avoid allowing an older class version to take precedence on the classpath.

## 8. Other Linkage Errors to Distinguish

Not every error caused by mismatched library versions is an `AbstractMethodError` or `InstantiationError`.

- **`NoSuchMethodError`:** Bytecode calls a method whose resolved signature does not exist in the class/interface definition loaded at runtime. Check API changes, dependency versions, and duplicate JARs.
- **`NoSuchFieldError`:** Bytecode references a field that no longer exists or is no longer compatible in the class at runtime.
- **`NoClassDefFoundError`:** The JVM cannot use a required class definition at runtime. The class may be missing from the runtime classpath, or a previous initialization of the class failed. The missing-class case is often compared with `ClassNotFoundException`, though the two errors are not synonymous.
- **`IncompatibleClassChangeError`:** Bytecode expects a type or member structure different from what is provided at runtime; specific subclasses include `AbstractMethodError` and `InstantiationError`.
- **`VerifyError`:** Bytecode fails JVM verification, usually because the bytecode is invalid or has bytecode-level compatibility issues.
- **`ExceptionInInitializerError`:** Static initialization of a class failed due to an exception; this is also a subclass of `LinkageError`, though you generally need to investigate the failure inside the static initializer rather than just looking for a missing API signature.

The error message and stack trace provide initial clues, but you need to inspect the exact class and JAR actually loaded by the runtime. The top line of the stack trace usually indicates where the error was observed; the root cause may lie in a dependency or an artifact loaded earlier.

## 9. Why Does Code Compile Successfully but Fail at Runtime?

The compiler and the JVM can use different class definitions at two different times. For example:

1. Version 1 of a library declares an abstract class or interface.
2. A module is compiled against version 1 and produces bytecode.
3. The library is upgraded to version 2 with binary-incompatible changes.
4. The old module is still deployed without being recompiled.
5. When execution reaches the affected member, the JVM detects the mismatch and can throw a linkage error.

Common root causes include:

- An old JAR is packaged alongside a new JAR.
- The classpath order causes the JVM to load an unintended version.
- One module was recompiled, but the deployed module has not been updated.
- Changing a concrete method to abstract, or adding an abstract contract that old implementing classes do not yet satisfy.
- Changing a member's kind or method signature that compiled bytecode depends on.
- The build environment and deployment environment use different sets of dependencies.

Not every API change causes a linkage error. Java has specific binary compatibility rules, and the outcome depends on the nature of the change, the member type, and the execution path. When an error occurs, verify the actual case rather than drawing conclusions from the error class name alone.

## 10. Systematic Diagnostic Workflow

### Step 1: Identify the Exact Error Type

Read the first exception/error class name in the stack trace and determine whether the error occurred at compile time or runtime. If `javac` reports an error, resolve the source code and type contracts. If the JVM throws a `LinkageError`, focus on the bytecode and the class versions being used.

### Step 2: Find the First Failing Usage Site

For `AbstractMethodError`, locate the specific method call and identify both the declared type and the actual runtime type of the object. For `InstantiationError`, locate the `new` instruction or related instantiation path. Use the stack trace to narrow down the scope, while still checking the dependency origin.

### Step 3: Verify Runtime Class Versions

Check the runtime classpath, JAR order, packaged artifacts, and library versions in the deployment environment. In a diagnostic program, you can print the location from which a class was loaded:

~~~java
System.out.println(
    SomeType.class.getProtectionDomain()
        .getCodeSource()
        .getLocation()
);
~~~

This snippet only works when `CodeSource` and class information are available; some environments may return `null`. Identify the suspected type accurately and inspect related classes, not just a single class.

### Step 4: Compare Contracts Between Build and Runtime Versions

Inspect abstract methods, access levels, signatures, return types, abstract/concrete status, and API changes. Determine which implementation was compiled against the old contract and whether it was deployed alongside the new API.

### Step 5: Perform a Clean Build and Synchronized Deployment

Clean old build outputs through the project's standard build process, recompile the relevant modules, and produce consistent artifacts. Avoid randomly deleting files in a running environment before verifying how deployment works. Then rerun in an environment whose classpath matches production.

### Step 6: Add Compatibility Tests

If a library is used by multiple modules, add integration tests or API compatibility checks to detect changes that break old implementations. Tests should use the same packaging and dependency resolution as the real application; running only unit tests under a different classpath may fail to reproduce the issue.

## 11. How to Resolve Each Error Type

| Finding | Resolution Approach |
|---|---|
| Compile-time error due to a concrete class missing an abstract method | Implement the method properly or declare the class abstract if the design requires it |
| Compile-time error due to instantiating an abstract class | Instantiate a concrete subclass or use a factory that returns an appropriate implementation |
| `AbstractMethodError` after upgrading a dependency | Locate the old implementation, synchronize versions, implement the new method, and rebuild the related modules |
| `InstantiationError` after an API changes from concrete to abstract | Update the client to instantiate a concrete subclass; check the classpath and old artifacts |
| `NoSuchMethodError` or `NoSuchFieldError` | Compare the signatures/members between the build version and the runtime version and remove incompatible dependencies |
| `NoClassDefFoundError` | Check the runtime classpath and the cause of any class initialization failure |
| `VerifyError` | Verify the bytecode source, bytecode transformation tools, and artifact consistency |

Avoid addressing these errors by adding a broad catch block around the entire application, skipping the call, or changing source code in only a single module. If the problem is binary incompatibility, even with fixed source code, the error can continue to occur as long as the old runtime artifact remains on the classpath.

## 12. Common Misconceptions

- **“AbstractMethodError means I forgot to override.”** If all current source code is compiled together, a missing override in a concrete class is normally caught at compile time. When encountering this runtime error, check the bytecode and API versions.
- **“InstantiationError is the same as `new AbstractClass()` in source code.”** Such source code is rejected by `javac`. `InstantiationError` typically indicates that old bytecode is running against a new class definition that has become abstract.
- **“Every LinkageError is caused by a missing JAR.”** A missing class is one cause, but signature changes, type structure changes, or incompatible class versions can also cause it.
- **“A successful build means runtime compatibility is guaranteed.”** A build checks only against the definitions used at build time. The runtime environment may load different artifacts.
- **“You can catch LinkageError and continue normally.”** Continuing after a type contract is broken can cause business operations not to run or leave program state unreliable.
- **“You only need to check the versions in the build file.”** You need to verify the actual artifacts packaged and loaded at runtime, because the classpath may contain multiple versions or different class sources.

## 13. Checklist When Encountering Abstract/Linkage Errors

- Confirm whether the error is a compile-time error or a runtime error.
- Record the error type and the call site in the stack trace.
- For `AbstractMethodError`, identify the method being called, the runtime type of the object, and the implementation being loaded.
- For `InstantiationError`, identify the class being instantiated and check whether the runtime version is still concrete.
- Check the classpath order, dependency tree, and JARs with duplicate versions.
- Compare the API used at compile time with the actual API at runtime.
- Synchronize versions and rebuild dependent modules; rerun tests in an equivalent deployment environment.
- Document the lessons learned in the release process to avoid mixing old and new artifacts.

Distinguishing compile-time errors from `AbstractMethodError`, `InstantiationError`, and other `LinkageError` types helps choose the right direction for investigation. Compile-time errors usually indicate that the source code does not yet satisfy the current type contract; linkage errors generally require checking the relationship between compiled bytecode and actual class definitions at runtime. Fix the consistency of the API, implementations, and deployed artifacts rather than merely treating the symptom of the error.
