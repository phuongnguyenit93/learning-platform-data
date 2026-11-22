# Hiding Implementation Packages and Inspecting Access Errors

## 1. Lab Objectives

In the Java Platform Module System (JPMS), a module can expose certain packages as its API while keeping implementation packages internal. This lab builds a library module with a public API, an unexported implementation package, and then tests various access approaches from a consumer module.

Objectives include:

- Create a named module with separate API and implementation packages.
- Export only the API package in the module descriptor.
- Attempt to access a public class inside the implementation package from another module.
- Distinguish between compile-time errors, runtime link errors, and deep reflection errors.
- Use JPMS options in a test environment to understand the effects of exports and opens.
- Keep implementation packages encapsulated in production configurations.

Core idea: a class declared as public can still be inaccessible from another module if the package containing that class is not exported. JPMS encapsulation adds a package- and module-level boundary alongside Java's access modifiers.

## 2. Creating the sample project structure

Create two modules:

    access-demo/
      src/
        com.example.library/
          module-info.java
          com/example/library/api/Greeter.java
          com/example/library/internal/DefaultGreeter.java
        com.example.client/
          module-info.java
          com/example/client/Main.java

The library module provides an API:

    package com.example.library.api;

    public interface Greeter {
        String greet(String name);
    }

The implementation resides in an internal package:

    package com.example.library.internal;

    import com.example.library.api.Greeter;

    public final class DefaultGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

The library module descriptor exports only the API:

    module com.example.library {
        exports com.example.library.api;
    }

The package **com.example.library.internal** does not appear in exports. Therefore, the client module cannot access types in this package under normal JPMS access rules.

In a real-world example, the library module should provide a factory or service API for consumers to obtain an implementation without knowing internal classes. This lab intentionally keeps the implementation class public to show that the public modifier does not automatically cross module boundaries.

## 3. Creating a client module that uses only the API

The client module declares a dependency on the library:

    module com.example.client {
        requires com.example.library;
    }

The main class uses the exported interface:

    package com.example.client;

    import com.example.library.api.Greeter;

    public class Main {
        public static void main(String[] args) {
            Greeter greeter = name -> "Hello, " + name;
            System.out.println(greeter.greet("Java"));
        }
    }

Here the client only depends on the API package. You can swap implementations inside the library without changing consumer code, as long as the Greeter contract remains compatible.

If the library has a public factory, the consumer can call that factory:

    Greeter greeter = Greeters.defaultGreeter();

The factory can instantiate DefaultGreeter inside the library module. The consumer does not need to import the implementation class and the internal package continues to remain hidden.

## 4. Compiling and running on the module path

From the access-demo root directory, compile both modules into the mods directory:

    javac -d mods/com.example.library src/com.example.library/module-info.java src/com.example.library/com/example/library/api/Greeter.java src/com.example.library/com/example/library/internal/DefaultGreeter.java

    javac --module-path mods -d mods/com.example.client src/com.example.client/module-info.java src/com.example.client/com/example/client/Main.java

Run the application:

    java --module-path mods --module com.example.client/com.example.client.Main

Output:

    Hello, Java

The client reads only the exported API. The implementation package does not need to be exported for the library itself to use classes in that package.

## 5. Attempting to access the implementation package directly

Modify the client to import the implementation:

    package com.example.client;

    import com.example.library.internal.DefaultGreeter;

    public class Main {
        public static void main(String[] args) {
            DefaultGreeter greeter = new DefaultGreeter();
            System.out.println(greeter.greet("Java"));
        }
    }

Recompile the client:

    javac --module-path mods -d mods/com.example.client src/com.example.client/com/example/client/Main.java

The compiler will report that package **com.example.library.internal** is not exported from module com.example.library to module com.example.client. Depending on the JDK version and context, the message may say the package is not visible or the module does not export the package.

This is a compile-time access error. The cause is not that the DefaultGreeter class lacks the public modifier; the cause is that the module descriptor does not export the package containing that class.

To reproduce, keep the module descriptor:

    module com.example.library {
        exports com.example.library.api;
    }

Do not add exports for internal in the standard configuration. After confirming the error, restore the client to use the Greeter API so the application runs normally.

## 6. Inspecting compile-time and runtime access errors

You must distinguish between two points in time:

| Time | Common symptom | Cause |
|---|---|---|
| Compile time | Compiler reports package is not exported or package is not visible | Consumer module lacks permission to access the package in the provider module |
| Link/runtime | IllegalAccessError | Bytecode or runtime configuration requests access to a type/member disallowed by the module |
| Deep reflection | InaccessibleObjectException or reflection-related error | Package has not been opened to the module performing reflection |
| Readability | Module cannot read another module | Missing requires or appropriate readability relationship |
| Class loading | ClassNotFoundException or NoClassDefFoundError | Class is not found or dependency is missing in the runtime configuration |

If the compiler blocks the code, you usually cannot recreate the exact runtime error by running the same source. To test a runtime access error, you can use bytecode compiled under a different configuration, reflection, or a specially crafted test fixture. Do not confuse all access errors as the same exception.

**IllegalAccessError** is a linkage error that occurs when the JVM encounters an invalid access to a class or member. It differs from **IllegalAccessException**, which is a checked exception commonly thrown by reflection APIs like Field.get or Method.invoke when access is denied.

## 7. Using --add-exports in a test environment

You can temporarily export the internal package to the client module at compile time:

    javac --module-path mods --add-exports com.example.library/com.example.library.internal=com.example.client -d mods/com.example.client src/com.example.client/module-info.java src/com.example.client/com/example/client/Main.java

At runtime, you need to grant the corresponding permission to the JVM:

    java --module-path mods --add-exports com.example.library/com.example.library.internal=com.example.client --module com.example.client/com.example.client.Main

The option has the form:

    --add-exports source-module/package=target-module

In the example:

- Source module is com.example.library.
- The additionally exported package is com.example.library.internal.
- Target module is com.example.client.

**--add-exports** allows the target module to access public types in the specified package. It does not automatically open the package for deep reflection and does not modify the JAR's module-info.java.

Use this option to reproduce package access when diagnosing or testing. Do not put it into production commands if that package is not a supported API.

If the client runs in the unnamed module, you can use the target **ALL-UNNAMED**. With named modules, prefer specifying the exact module name to limit access scope.

## 8. Testing deep reflection and --add-opens

Exporting a package allows accessing public types according to Java rules. Frameworks may need additional permission to read or modify private members via reflection. In that case, **opens** is required.

Add a test class in the client module:

    package com.example.client;

    import java.lang.reflect.Field;

    public class ReflectionProbe {
        public static void main(String[] args) throws Exception {
            Class<?> type =
                Class.forName("com.example.library.internal.DefaultGreeter");

            Field field = type.getDeclaredField("somePrivateField");
            field.setAccessible(true);
        }
    }

The example above only illustrates where the reflection call happens; for actual testing, the class needs a private field named somePrivateField. When the package is not open to the client module, calling setAccessible(true) can throw **InaccessibleObjectException**.

You can open the package to the client for a single run:

    java --module-path mods --add-opens com.example.library/com.example.library.internal=com.example.client --module com.example.client/com.example.client.Main

The option has the form:

    --add-opens source-module/package=target-module

**--add-opens** allows deep reflection from the target module into the specified package. It does not grant compile-time permission to import types in an unexported package.

If a framework both needs to import public types in an internal package and perform deep reflection, the test configuration may need both --add-exports at compile time and --add-opens at runtime. Grant only the permissions actually needed.

## 9. Comparing exports, opens, and runtime options

| Mechanism | Purpose | Usage example |
|---|---|---|
| exports | Expose a package for normal access | Public API of a library |
| qualified exports | Expose a package to specific target modules | SPI intended for an adapter module |
| opens | Allow deep reflection | ORM reading private fields |
| --add-exports | Supplement export in compile/runtime config | Tests accessing a public implementation type |
| --add-opens | Supplement open at runtime | Test framework needing deep reflection |
| --add-reads | Supplement readability | Module needing to read another module in a special configuration |

Do not use --add-exports to solve a deep reflection error if the package needs to be opened. Do not use --add-opens to fix a compiler error where a package cannot be imported. Identify the exact type of access being blocked.

## 10. Inspecting module descriptors and module resolution

You can view an artifact's module descriptor:

    jar --describe-module --file mods/com.example.library

The output should show the API package exported and the internal package not exported. If the module descriptor is packaged in a JAR, run the command on the corresponding JAR file.

To observe module resolution:

    java --show-module-resolution --module-path mods --module com.example.client/com.example.client.Main

This option displays which modules are resolved and their dependency relationships. It helps diagnose readability and module path issues, though it does not resolve package access by itself.

If a module is not found, check the module path. If the module is found but a package is inaccessible, check exports. If the error only occurs with reflection, check opens. Do not add every option at once, as that makes it difficult to identify the root cause.

## 11. Designing production and test configurations

In production, the module descriptor should preserve the intended boundaries:

    module com.example.library {
        exports com.example.library.api;
    }

Tests can use a separate configuration:

- Black-box tests only need to require the library and call the public API.
- Tests that need to import a public implementation type can use --add-exports during test compile/runtime.
- Frameworks that need deep reflection can use --add-opens in the test JVM.
- Tests that need package-private access can use --patch-module to put test classes into the target module during test runtime.

Do not modify production module-info.java just to make tests compile. Do not save test-only options into deployment scripts or production launchers.

If using Maven or Gradle, place the options in the corresponding test task configuration. Property names and how JVM arguments are passed depend on the plugin/build tool; ensure the options are passed to both the compiler if compile-time access is needed and the test JVM if runtime reflection is needed.

## 12. Key Takeaways

- A public class in an unexported package still cannot be accessed normally by another module.
- **exports** exposes a package; **opens** allows deep reflection.
- A compile error about a package not being visible differs from an IllegalAccessError at runtime.
- IllegalAccessException and InaccessibleObjectException are different reflection errors; check the exact API causing the error.
- --add-exports can grant access to public types in a package for a target module.
- --add-opens grants deep reflection permission at runtime, and does not replace compile-time export.
- Use runtime options only for diagnostics or testing when needed; keep production module descriptors small and clear.
- Check module path, requires, exports, and opens according to the error type.
- Use jar --describe-module and --show-module-resolution to observe the actual configuration.

**Hiding implementation packages helps a module retain control over its API and limit external entry points.** When inspecting access errors, identify whether the error occurs at compile time, link time, or reflection time, then choose the right JPMS mechanism instead of exporting or opening the entire module.

## References

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Java SE 21 Tool Specifications — javac: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html