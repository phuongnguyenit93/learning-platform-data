# Creating Two Named Modules with requires and exports

## Objectives

After this lesson, you can:

- Create two independent named modules using the Java Platform Module System (JPMS).
- Write `module-info.java` for an API provider module and an API consumer module.
- Use `exports` to expose a package and `requires` to declare a dependency.
- Organize the source tree by module name and package.
- Compile multiple modules using `javac --module-source-path`.
- Run the application using the module path and understand how the JVM resolves both modules.

## 1. What will this lab build?

We will create a small application consisting of two named modules:

- `com.acme.greetings`: library module, providing the `Greeter` class.
- `com.acme.app`: application module, using `Greeter` to print a greeting.

The library module exposes the `com.acme.greetings.api` package using `exports`. The application module declares `requires com.acme.greetings` so it can read and use that API.

Dependency direction:

~~~text
+-----------------------+
|     com.acme.app      |
|       Main.java       |
+-----------+-----------+
            |
            | requires
            v
+-----------------------+
|  com.acme.greetings   |
|       Greeter.java    |
|                       |
| exports greetings.api|
+-----------------------+
~~~

This is a minimal example, yet it demonstrates the two core directives of named modules: the provider module decides which packages are exported; the consumer module declares which modules it needs to read.

## 2. Creating the directory structure

Create a project with a separate source root for each module:

~~~text
two-modules/
└── src/
    ├── com.acme.greetings/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── greetings/
    │               └── api/
    │                   └── Greeter.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

Rules to remember:

- Each named module has a `module-info.java` file at the module root.
- The module directory name in the module source path should match the name declared in the descriptor.
- The package path inside the module matches the `package` statement in the source.
- `module-info.java` has no package declaration.
- Each module can contain multiple packages, but only exported packages serve as the normal accessible API for other modules.

## 3. Writing the API provider module

In `src/com.acme.greetings/module-info.java`:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

The `exports` directive exposes the `com.acme.greetings.api` package to other modules. It allows modules that read this package to access public types and public/protected APIs according to Java rules.

Create the `Greeter` class in `src/com.acme.greetings/com/acme/greetings/api/Greeter.java`:

~~~java
package com.acme.greetings.api;

public final class Greeter {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            name = "World";
        }

        return "Hello, " + name + "!";
    }
}
~~~

Key points:

- The class's package must match the package exported in the descriptor.
- The class must be `public` so code in other modules can use it.
- Methods called by the consumer must also have appropriate access levels, here `public`.
- The class does not need to be in a package with the same name as the module. Module name and package name are two separate concepts.

After this step, the `com.acme.greetings` module has a small public API.

## 4. Writing the application module using the API

In `src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

The `requires` directive declares that the application module needs to read the `com.acme.greetings` module. This is a dependency in the module graph.

Create the main class in `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.greetings.api.Greeter;

public class Main {

    public static void main(String[] args) {
        Greeter greeter = new Greeter();

        String message = greeter.greet("Java Module System");
        System.out.println(message);
    }
}
~~~

The application can import `Greeter` because two conditions are met:

1. `com.acme.app` declares `requires com.acme.greetings`.
2. `com.acme.greetings` declares `exports com.acme.greetings.api`.

If either condition is missing, the compiler cannot use the API across the module boundary in the normal way.

## 5. Compiling both modules with javac

Open a terminal in the `two-modules/` directory and run:

~~~bash
javac -d out --module-source-path src -m com.acme.greetings,com.acme.app
~~~

Meaning of the options:

| Component | Meaning |
|---|---|
| `javac` | Launches the Java compiler |
| `-d out` | Selects `out/` as the root directory for output |
| `--module-source-path src` | Specifies where the source trees of the modules reside |
| `-m` | Selects the modules to compile |
| `com.acme.greetings,com.acme.app` | The two modules included in this compilation |

The compiler reads the descriptors of both modules, finds dependencies from `requires`, and compiles the necessary source files.

If compilation succeeds, the output structure looks like:

~~~text
two-modules/
├── src/
│   ├── com.acme.greetings/
│   └── com.acme.app/
└── out/
    ├── com.acme.greetings/
    │   ├── module-info.class
    │   └── com/
    │       └── acme/
    │           └── greetings/
    │               └── api/
    │                   └── Greeter.class
    └── com.acme.app/
        ├── module-info.class
        └── com/
            └── acme/
                └── app/
                    └── Main.class
~~~

Each module has its own output directory. `module-info.java` is compiled into `module-info.class`; classes are placed according to their package paths.

You can inspect the output by opening the `out/` directory or using the `jar`/`javap` tools to view the compiled artifacts.

## 6. Running the application using the module path

Use the output root as the module path:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Where:

- `--module-path out` tells the JVM to look for modules in the `out` directory.
- `-m` selects the startup module and main class.
- `com.acme.app` is the application module name.
- `com.acme.app.Main` is the fully qualified name of the class containing `main`.

Output:

~~~text
Hello, Java Module System!
~~~

The JVM finds `com.acme.app`, reads its descriptor to learn that this module requires `com.acme.greetings`, and then resolves the dependency from the module path. When the application calls `Greeter.greet`, the class belonging to the library module is loaded via the module layer's class loading mechanism.

Full compile and run commands:

~~~bash
javac -d out --module-source-path src -m com.acme.greetings,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

## 7. Understanding requires and exports properly

These two directives solve two different questions.

### 7.1. requires: which module needs to be read?

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

`requires` declares a dependency between modules. It creates the readability relationship needed for the application module to reference types provided by the library module.

`requires` does not automatically expose all packages of the target module. Packages must still be exported appropriately.

### 7.2. exports: which package is exposed?

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

`exports` exposes a package to other modules. If a module does not export a package, consumer modules cannot import public types in that package in the normal way, even if they have declared `requires`.

`exports` does not open a package for deep reflection into private members. Deep reflection is the purpose of `opens`, a different directive.

### 7.3. Both sides are needed

| Provider module | Consumer module | Result |
|---|---|---|
| Exports API package | Requires provider module | Consumer can use the public API |
| Does not export package | Requires provider module | Consumer still cannot access the package |
| Exports package | Does not require provider module | Lacks the necessary readability in the normal module graph |
| Exports a different package | Requires provider module | Consumer can only access the properly exported package |

In this example, `exports` and `requires` must together point to the exact package/module names.

## 8. Experimenting with removing a directive

The errors below help understand the role of each declaration.

### 8.1. Removing requires from the application module

If the application descriptor only has:

~~~java
module com.acme.app {
}
~~~

but the source still imports `com.acme.greetings.api.Greeter`, the compiler will report that the package/module is not readable or not visible. The application module has not declared the required dependency.

Fix: add back:

~~~java
requires com.acme.greetings;
~~~

### 8.2. Removing exports from the library module

If the library descriptor is:

~~~java
module com.acme.greetings {
}
~~~

then `com.acme.greetings.api` is not exposed to other modules. Even though `com.acme.app` has `requires`, the compiler still disallows access to that API package.

Fix: export the right package:

~~~java
exports com.acme.greetings.api;
~~~

### 8.3. Exporting the wrong package

For example, the descriptor writes:

~~~java
module com.acme.greetings {
    exports com.acme.greetings;
}
~~~

but the `Greeter` class resides in `com.acme.greetings.api`. Exporting a parent package does not automatically export subpackages. You must export accurately:

~~~java
exports com.acme.greetings.api;
~~~

This is a common mistake when assuming that exporting a package includes all its subpackages.

## 9. Trying to add an internal package

Suppose the library has an implementation package:

~~~text
com/acme/greetings/internal/Formatter.java
~~~

If the descriptor only exports `com.acme.greetings.api`, the `com.acme.greetings.internal` package remains encapsulated.

Consumers should not import `Formatter` directly. This is how modules protect implementation details from accidentally becoming public dependencies.

If another module genuinely needs to use a type, consider whether that type belongs to the API contract. If it does, place it in the API package and export it explicitly. Do not export an entire package just to bypass a compile error.

## 10. Experimenting with qualified exports

If only one consumer module should be allowed to access a package, you can use a qualified export:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api to com.acme.app;
}
~~~

This restricts package access to the `com.acme.app` module. Other modules, even if they have `requires com.acme.greetings`, do not automatically gain access to that package.

Qualified exports are useful when an API is intended only for a specific set of consumers. For libraries exposed to many applications, unqualified `exports` is usually more appropriate.

## 11. Separating compile and run steps

In practice, compiling and running are usually two separate steps.

Compile:

~~~bash
javac -d out --module-source-path src -m com.acme.greetings,com.acme.app
~~~

Run:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

This means:

- The compiler needs the source tree and module descriptors to check dependencies.
- The JVM needs the compiled modules on the module path to resolve and run them.
- The source directory `src` is not the runtime module path in this example.
- The output directory `out` contains the exploded modules and is used at runtime.

If running reports that a module cannot be found, check whether the module path points to the parent directory containing both modules.

## 12. Packaging into modular JARs (optional)

After compiling, each exploded module can be packaged into a modular JAR:

~~~bash
jar --create --file dist/com.acme.greetings.jar -C out/com.acme.greetings .
jar --create --file dist/com.acme.app.jar --main-class com.acme.app.Main -C out/com.acme.app .
~~~

The `dist/` directory must exist before running the commands. The JAR files retain `module-info.class`, so module identity and dependencies are preserved.

Run from modular JARs:

~~~bash
java --module-path dist -m com.acme.app/com.acme.app.Main
~~~

You can use `jar --describe-module` to view the descriptor inside each JAR:

~~~bash
jar --describe-module --file dist/com.acme.greetings.jar
jar --describe-module --file dist/com.acme.app.jar
~~~

The packaging step does not change the `requires` and `exports` relationships declared in the source descriptors.

## 13. Common errors and how to handle them

| Symptom | Common cause | Resolution |
|---|---|---|
| `module not found` | Module dependency is missing from module path/source path | Check module names and source/output locations |
| `package ... is not visible` | Package is not exported or module is not readable | Check both `exports` and `requires` |
| `module ... does not read ...` | Missing `requires` or dependency is not in the graph | Declare the dependency properly |
| `package does not exist` | Wrong package name, source path, or import | Cross-check package declaration and folder |
| JVM cannot find main module | Module path points to the wrong directory | Point to the parent directory containing the modules |
| Main class not found | Wrong class name after `/` or class not compiled | Check package, class name, and output |

When debugging, check in this order:

1. Does the source tree have the right module roots and package paths?
2. Does each module have a `module-info.java`?
3. Has the provider module exported the right package?
4. Has the consumer module required the right module?
5. Are both modules present in the output/module path?
6. Are the module name and main class name in the run command accurate?

## 14. Lab completion checklist

- [ ] Two separate module roots exist under `src/`.
- [ ] Module `com.acme.greetings` has `module-info.java`.
- [ ] The library module exports `com.acme.greetings.api`.
- [ ] Class `Greeter` is in the exported package and has a public method.
- [ ] Module `com.acme.app` has `module-info.java`.
- [ ] The application module declares `requires com.acme.greetings`.
- [ ] The `javac` command compiles both modules.
- [ ] The output contains `module-info.class` for each module.
- [ ] The JVM runs the application using `--module-path`.
- [ ] The output displays the expected greeting.

## Conclusion

This lab created two named modules with a clear relationship: `com.acme.greetings` provides a public API via `exports`; `com.acme.app` declares a dependency via `requires` and uses that API.

Remember: **requires answers which module needs to be read; exports answers which package is exposed**. When both directives are declared accurately, the compiler can verify module dependencies and the JVM can resolve and load the modules to run the application.
