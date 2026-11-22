# Opening Packages for Frameworks Using `--add-opens`

## Objectives

After this lesson, you will be able to explain why frameworks need deep reflection in JPMS, read `--add-opens` syntax accurately, choose the right target module for frameworks running on the module path or classpath, configure the JVM when running applications, and resolve `InaccessibleObjectException` errors caused by unopened packages.

## 1. Why Do Frameworks Need Packages Opened?

Many frameworks need to read or modify object state using reflection. For instance, a dependency injection container may need to access constructors or fields; an ORM may need to read fields to map data; a serializer may need to access non-public constructors or fields to convert objects.

In Java prior to JPMS, many frameworks commonly used reflection to access non-public members without encountering explicit module boundaries. With the Java Platform Module System, each named module controls which packages are exported for ordinary access and which packages are opened for deep reflection.

When a framework calls `setAccessible(true)` or `trySetAccessible()` to access a private/protected/package-private member in a package of another module, the JVM checks whether that package is open to the module containing the framework. If it is not open, the operation may be denied, typically with the error:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module java.base does not "opens java.lang" to unnamed module ...
~~~

The error message usually provides three key pieces of information:

- The module owning the package, such as `java.base`.
- The package that needs to be opened, such as `java.lang`.
- The module requesting reflection permission, such as an unnamed module or a specific named module.

Use those exact three pieces of information to construct `--add-opens` accurately.

## 2. Syntax of `--add-opens`

General syntax:

~~~bash
--add-opens source-module/package=target-module
~~~

You can open a package to multiple target modules:

~~~bash
--add-opens source-module/package=target-one,target-two
~~~

Where:

- `source-module` is the module owning the package to open.
- `package` is the full package name, not the class name.
- `target-module` is the module containing the framework code that will perform reflection.
- `ALL-UNNAMED` is a special target representing all unnamed modules.

Example opening package `java.lang` of JDK module `java.base` for code running on the classpath:

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Example opening package `com.acme.model` in application module `com.acme.app` for a framework named module:

~~~bash
--add-opens com.acme.app/com.acme.model=org.example.framework
~~~

How to read the expression:

~~~text
com.acme.app / com.acme.model = org.example.framework
     source module     package          target module
~~~

The slash separates the source module and the package. The equals sign separates the opened package and the target module receiving permission. Do not append a class name after the package, do not use file paths, and do not omit the source module name.

## 3. Framework on the Classpath: Use `ALL-UNNAMED`

If a framework is loaded from the classpath, the framework code belongs to the unnamed module of its class loader. In that case, the target in `--add-opens` is `ALL-UNNAMED`.

Example of a classpath application using a framework that requires deep reflection into package `java.lang`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar;lib/*" com.acme.Main
~~~

The example above uses a semicolon as the path separator on Windows. On Linux and macOS, use a colon:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar:lib/*" com.acme.Main
~~~

If the framework needs to access a package in an application module, the source module is the application module:

~~~bash
java --add-opens com.acme.app/com.acme.model=ALL-UNNAMED -cp "app.jar;lib/*" com.acme.Main
~~~

Note: `ALL-UNNAMED` opens the specified package to all unnamed modules. It does not open all packages of the source module. For example, `java.base/java.lang=ALL-UNNAMED` opens only the `java.lang` package in module `java.base`.

Use `ALL-UNNAMED` only when the framework truly runs in an unnamed module. If the framework is a named module on the module path, specify that module's name to restrict permissions.

## 4. Framework Is a Named Module: Open Only to the Target Module

If the framework is packaged as a named module, use the framework's module name as the target.

Example where application `com.acme.app` has a model package that needs opening for framework `org.example.framework`:

~~~bash
java --add-opens com.acme.app/com.acme.model=org.example.framework      --module-path mods      --module com.acme.app/com.acme.app.Main
~~~

If the package needs to be opened to multiple framework named modules:

~~~bash
java --add-opens com.acme.app/com.acme.model=org.example.framework,org.example.orm      --module-path mods      --module com.acme.app/com.acme.app.Main
~~~

You can repeat the `--add-opens` option for different packages:

~~~bash
java   --add-opens java.base/java.lang=org.example.framework   --add-opens java.base/java.util=org.example.framework   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Determine the exact module name from the framework's descriptor. A Maven/Gradle artifact name or JAR filename is not necessarily the same as the module name. You can inspect the module with:

~~~bash
jar --describe-module --file path/to/framework.jar
~~~

Or view the descriptor discovered by the runtime:

~~~bash
java --module-path mods --describe-module org.example.framework
~~~

The target name must be the module name recognized by the JVM in the runtime graph.

## 5. Placing the Option in the Right Place: JVM Arguments

`--add-opens` is a launcher/JVM option. It must be passed to the JVM when the Java process starts, before the application selector such as `-m`, `-jar`, or the main class name.

Running an executable JAR:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Running a named module:

~~~bash
java --add-opens com.acme.app/com.acme.model=org.example.framework      -p mods      -m com.acme.app/com.acme.app.Main
~~~

Running on the classpath:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED      -cp "app.jar;lib/*"      com.acme.Main
~~~

If the framework runs inside a JVM launched by an IDE, build tool, test runner, application server, or container, add the option to the VM/JVM arguments configuration of that exact process. Do not put it in the application's program arguments.

With test runners that spawn a forked JVM, the option must be passed to the child JVM executing the tests. Adding the option to Maven's or Gradle's own JVM does not automatically guarantee it is forwarded to every forked test process.

In IntelliJ IDEA or a similar IDE, find the **VM options** field in the Run/Debug configuration and add:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

In Docker, add the option to the Java launch command in `ENTRYPOINT` or `CMD`, for example:

~~~dockerfile
ENTRYPOINT ["java", "--add-opens=java.base/java.lang=ALL-UNNAMED", "-jar", "/app/app.jar"]
~~~

The `--add-opens=...` syntax is also valid. With wrapper scripts, inspect the final command that actually invokes Java to ensure the option is placed on the JVM side.

## 6. When Should You Use `opens` in module-info.java?

If you develop a module and know which framework named module needs reflection into your package, you can declare the open permission directly in the module descriptor.

~~~java
module com.acme.app {
    requires org.example.framework;

    exports com.acme.api;

    opens com.acme.model to org.example.framework;
}
~~~

Here:

- `exports com.acme.api` allows other modules to use the public API of the package.
- `opens com.acme.model to org.example.framework` allows the framework to perform deep reflection in the model package.
- `requires org.example.framework` is a readability dependency if the application module's code needs to read framework types; simply opening a package does not replace this dependency.

Qualified `opens` grants reflection permission only to the specified target module. If multiple framework named modules need access, list them:

~~~java
opens com.acme.model to org.example.framework, org.example.orm;
~~~

If the framework resides in an unnamed module, you cannot write `ALL-UNNAMED` as a target in an `opens` directive in `module-info.java`. Use `--add-opens` at runtime or redesign how the framework is packaged into a named module.

A module can also use an `open module` declaration:

~~~java
open module com.acme.app {
    requires org.example.framework;
}
~~~

This declaration opens all packages of the module for deep reflection at runtime. It has a broader scope than qualified `opens`, so use it only when genuinely needed. An open module does not declare separate `opens` directives inside.

## 7. Distinguishing `--add-opens`, `--add-exports`, and `--add-reads`

These three options are often confused:

| Option | Permission Added | Use Case |
| --- | --- | --- |
| `--add-reads` | Readability edge between source module and target module | A module needs to read another module in the module graph. |
| `--add-exports` | Exports a package to a target module | Code in another module needs access to public types/members in a package. |
| `--add-opens` | Opens a package to a target module | A framework needs deep reflection into non-public members. |

Example:

~~~bash
--add-reads com.acme.app=org.example.api
--add-exports com.acme.internal/com.acme.spi=org.example.client
--add-opens com.acme.app/com.acme.model=org.example.framework
~~~

If a framework reports that it cannot access a private field or that `setAccessible(true)` failed, check `opens`. Adding `exports` is not a substitute for deep reflection.

Conversely, if normal Java code fails to compile or cannot access public types in a package, check `requires` and `exports`. `--add-opens` is a runtime reflection permission and does not turn a package into a public API for other code to compile against.

## 8. Strong Encapsulation on Modern JDKs

JPMS strengthens encapsulation of internal JDK packages. Starting in JDK 17, strong encapsulation of JDK internal packages is applied broadly by default under JEP 403. Legacy frameworks relying on reflection into JDK internals may start failing when upgrading Java.

The `--illegal-access` option was previously used as a transition mechanism in earlier Java releases. On JDK 17 and later, this option no longer restores the old broad access mechanism. When a specific package genuinely needs to be opened, use `--add-opens` with the exact source package and target module.

You should not open all JDK packages or an entire application module just to silence error messages. Use the stack trace to identify the blocked package, the module requesting reflection, and the operation the framework is performing.

## 9. Reading Errors and Finding the Right Package to Open

Error example:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final java.lang.String
java.lang.Throwable.detailMessage accessible:
module java.base does not "opens java.lang"
to unnamed module @4f3f5b24
~~~

This can be analyzed as:

- `java.lang.Throwable.detailMessage` is the member the framework wants to access.
- The package to open is `java.lang`.
- The module owning the package is `java.base`.
- The target is an unnamed module, because the message says `unnamed module`.

Corresponding option:

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

If the message states `does not "opens com.acme.model" to module org.example.framework`, the corresponding option will be:

~~~bash
--add-opens com.acme.app/com.acme.model=org.example.framework
~~~

Diagnostic steps:

1. Read the stack trace to find the exception and the accessed member.
2. Identify the package containing the member; do not use the class name as the package.
3. Identify the module owning the package.
4. Identify the target module from the `to ...` portion of the message.
5. Add the exact option to the JVM arguments of the process performing reflection.
6. Re-run and verify the error has moved past that access step; the framework may subsequently discover another package that also needs opening.

Do not add multiple packages by guessing. One option resolves only the exact package and target written in it.

## 10. Checking Open Status in Code

The `Module` API can help check whether a package is open to a target module:

~~~java
Module source = SomeModel.class.getModule();
Module target = FrameworkEntryPoint.class.getModule();

boolean openToFramework =
        source.isOpen("com.acme.model", target);

System.out.println("open to framework = " + openToFramework);
~~~

Call `isOpen(packageName, targetModule)` on the module owning the package. A result of `true` means the package is open to the target module under the current runtime configuration.

If the framework runs on the classpath, the target may be an unnamed module:

~~~java
Module target = FrameworkEntryPoint.class.getModule();

System.out.println(target.isNamed()); // false
~~~

This is a way to determine the actual target instead of guessing whether the framework is running on the classpath or the module path.

## 11. Security and Maintainability Considerations

Opening a package reduces the module's encapsulation with respect to the granted target. When a framework can deep-reflect into private state, the framework can depend on internal implementation details that the module does not commit to keeping stable.

Some practical guidelines:

- Open only the packages the framework actually needs.
- Specify a named target module whenever possible, rather than using `ALL-UNNAMED` for every case.
- Prefer opening required model packages rather than opening the entire module.
- If you own the module, consider qualified `opens` in the descriptor so access permissions are expressed alongside the module configuration.
- Document the reason for each JVM option and re-evaluate when upgrading frameworks or the JDK.
- Prefer public APIs or framework-supported extension points if deep reflection can be avoided.

`--add-opens` is a useful compatibility tool, especially when upgrading legacy applications, but it should not turn into an unmanaged list of broad permissions.

## Takeaways

`--add-opens source-module/package=target-module` opens a package for deep reflection from a target module. Use `ALL-UNNAMED` when the framework runs on the classpath; use the specific module name when the framework is a named module. Place the option in the JVM arguments of the right process, before `-m`, `-jar`, or the main class. For modules you manage, qualified `opens` in `module-info.java` is usually a more sustainable declaration. `exports` serves public API access, whereas `opens` serves deep reflection.
