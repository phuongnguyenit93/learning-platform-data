# --add-opens for Deep Reflection

## 1. The Reflection Access Problem in JPMS

Java Reflection allows a program to inspect classes, fields, methods, and constructors at runtime. Standard reflection can read public metadata; deep reflection also requires accessing non-public members, such as private fields or private constructors.

Before Java 9, code commonly used `setAccessible(true)` to request bypassing Java access checks. Since the Java Platform Module System (JPMS), access is also governed by module boundaries. A package belonging to a named module might not be opened to the module performing reflection, even when the class and member have been found.

For example, a framework needs to read a private field in `java.lang.String`. On modern JDKs, calling `Field.setAccessible(true)` can throw `InaccessibleObjectException` because package `java.lang` of module `java.base` is not open to the framework's module.

The JVM option `--add-opens` allows opening a specific package of a source module to a target module at runtime. This is a useful compatibility mechanism when legacy libraries or frameworks need deep reflection into packages that are not already open.

## 2. Syntax of --add-opens

General syntax:

~~~text
--add-opens source-module/package=target-module
~~~

You can open a package to multiple target modules using a comma-separated list:

~~~text
--add-opens source-module/package=target-module-1,target-module-2
~~~

Components:

- `source-module`: name of the module that owns the package to open, for example `java.base`.
- `package`: full package name, for example `java.lang`; do not add a leading slash and do not use wildcards.
- `target-module`: the module containing the code performing deep reflection, for example `com.acme.reflector`.
- `ALL-UNNAMED`: special symbol representing all unnamed modules, typically code loaded from the classpath.

Example opening package `java.lang` of `java.base` for an application running on the classpath:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Example opening the same package for a named module:

~~~bash
java \
  --add-opens=java.base/java.lang=com.acme.reflector \
  --module-path mods \
  --module com.acme.reflector/com.acme.reflector.Main
~~~

Be sure to identify the correct target module. If the framework resides in an unnamed module, use `ALL-UNNAMED`. If the framework is a named module, open it to that module's name. Opening to the wrong target can cause the flag to be accepted while the code performing reflection still lacks access.

## 3. Understanding the Direction of Opening a Package

An easy mistake to make is reversing the source module and target module.

Suppose application code resides in module `com.acme.reflector` and needs to access a private member of a class in `java.lang`:

~~~text
Source module: java.base
Source package: java.lang
Target module: com.acme.reflector
~~~

Correct configuration:

~~~text
--add-opens=java.base/java.lang=com.acme.reflector
~~~

The module before the slash is the module containing the package being opened. The module after the equals sign is the module granted permission for deep reflection into that package.

If the application runs on the classpath, the reflecting code belongs to an unnamed module:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

`ALL-UNNAMED` is meaningful only in the target module position. It includes unnamed modules in the JVM, including unnamed modules created after the JVM starts. Do not use it as the source module name.

## 4. Hands-On Example with a Private Member

The following program attempts to enable access to the internal `value` field of `String`:

~~~java
import java.lang.reflect.Field;

public class ReflectiveAccess {
    public static void main(String[] args) throws NoSuchFieldException {
        Field valueField = String.class.getDeclaredField("value");

        boolean accessible = valueField.trySetAccessible();

        System.out.println("trySetAccessible: " + accessible);

        if (!accessible) {
            throw new IllegalStateException(
                    "Package java.lang is not open to the application's module");
        }

        System.out.println("Deep reflection access is enabled");
    }
}
~~~

Compile and run on the classpath:

~~~bash
javac ReflectiveAccess.java
java ReflectiveAccess
~~~

On modern JDKs, if the package is not open, `trySetAccessible()` returns `false`. If `setAccessible(true)` is called directly in a disallowed situation, the program may receive an `InaccessibleObjectException`.

Run again with the option:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED ReflectiveAccess
~~~

Now `trySetAccessible()` can return `true` because module `java.base` has opened package `java.lang` to the unnamed module containing the program.

This example only checks the ability to enable access. Do not depend on the internal structure of `String` in real applications: fields and data representation can change between JDK versions. Being permitted to access a field also does not mean every read or write operation is supported by the JVM.

## 5. Checking Open Status with the Module API

You can check a package's open status directly from the JVM using `Module.isOpen(String, Module)`.

~~~java
public class CheckOpenPackage {
    public static void main(String[] args) {
        Module sourceModule = String.class.getModule();
        Module targetModule = CheckOpenPackage.class.getModule();

        boolean opened = sourceModule.isOpen("java.lang", targetModule);

        System.out.println("Source module: " + sourceModule.getName());
        System.out.println("Target module: " + targetModule.getName());
        System.out.println("java.lang opened: " + opened);
    }
}
~~~

When running on the classpath, `targetModule.getName()` is `null`, because unnamed modules have no name. If `--add-opens=java.base/java.lang=ALL-UNNAMED` is used, checking `isOpen` with the target module returns `true`.

You can use the `Module.isOpen(String)` overload to check whether a package is open unconditionally to all modules. When you need to verify permissions between two specific modules, use the overload that takes the target module.

Distinguish between two types of information:

- `ModuleDescriptor.opens()` reflects the `opens` directives declared in the descriptor.
- `Module.isOpen(packageName, targetModule)` reflects actual runtime accessibility, including open permissions granted dynamically via JVM options.

Therefore, a package can be opened by `--add-opens` even if the original `module-info.java` file does not declare `opens` for that package.

## 6. How Does --add-opens Differ from opens and exports?

These three mechanisms relate to module access but serve different purposes.

| Mechanism | Scope | Purpose |
| --- | --- | --- |
| `exports package` | Declared in `module-info.java` | Allows other modules to access the public API of the package under normal Java rules. |
| `opens package` | Declared in `module-info.java` | Opens the package for deep reflection at runtime. |
| `--add-opens` | JVM option at launch | Grants open access to a package for a target module without modifying the source module's descriptor. |
| `--add-exports` | JVM option at launch | Allows accessing public types in an unexported package; does not replace deep reflection permissions. |

Example module declaration:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.json;
}
~~~

Other modules can use the public API in `com.acme.domain.api`. The `com.acme.json` framework can perform deep reflection into `com.acme.domain.model`.

If you cannot modify the source module, you can open the package at runtime:

~~~bash
java --add-opens=com.acme.domain/com.acme.domain.model=com.acme.json ...
~~~

If code needs to directly reference a public class in an unexported package, consider `--add-exports`. If code needs to access a private field or private method via reflection, use `--add-opens`.

`--add-opens` does not grant permission to import or directly call an internal API at compile time. It also does not replace `requires`, does not add a module dependency, and does not turn a package into a public API.

## 7. When Is --add-opens Needed?

Common scenarios:

- A dependency injection framework needs to read or assign private fields of classes in another module.
- An ORM needs to access non-public constructors or fields to map objects.
- A serialization framework needs deep reflection to read object state.
- A legacy library accesses internal implementation details of the JDK or a third-party library.
- A test framework needs to access private members to verify behavior or prepare fixtures.
- A plugin or instrumentation tool needs introspection into another module's package.

Before adding the flag, check whether the framework has a newer version that supports JPMS. Modern frameworks may use public APIs, method handles, or require the application to open the appropriate package in its descriptor. If the module is owned by your own project, declaring `opens package to target.module;` in `module-info.java` usually helps keep configuration managed alongside source code.

Using `--add-opens` is appropriate when configuring the runtime environment, when the source module cannot be edited, or when a transitional solution is needed for a legacy dependency.

## 8. Configuration in Build and Deployment Environments

The option must be passed to the JVM running the application or the JVM running tests. Adding it to the `javac` command as a regular compiler option does not open the package for the application when it runs afterward.

### 8.1. Running a JAR Directly

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Place the JVM option before `-jar`. The option is passed to the Java process created by this command.

### 8.2. Gradle Tests

With Groovy DSL:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

If only one test task needs package open access, configure that specific task instead of applying it to the entire test suite.

For the `JavaExec` task:

~~~groovy
tasks.withType(JavaExec).configureEach {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

`Test` and `JavaExec` launch separate JVMs. Configuration for one task type does not automatically apply to the other task type.

### 8.3. Maven Surefire

In the Maven Surefire Plugin, pass the option via `argLine`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-opens=java.base/java.lang=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

If the project already uses `argLine` for JaCoCo or another agent, append the option to the existing configuration instead of overwriting the entire value. Otherwise, previous agents or JVM options may disappear.

### 8.4. IDEs, Containers, and Services

In an IDE, set the flag in the VM options field of the Run/Debug Configuration. In Docker or a service script, add the flag to the actual JVM launch command.

Example of a container running an application on the classpath:

~~~dockerfile
ENTRYPOINT ["java", "--add-opens=java.base/java.lang=ALL-UNNAMED", "-jar", "/app/app.jar"]
~~~

Ensure the flag is passed to the final Java process. Putting the flag in a shell script or build process configuration has no effect on another JVM if the build tool does not forward that option.

If the application spawns child Java processes, each process must be configured separately. Options of a parent JVM do not automatically become launch options of child JVMs.

## 9. Limitations and Security Considerations

`--add-opens` is a fairly broad package-opening permission: every class in the target module is granted deep reflection capability into the specified package. Therefore:

1. Open only the packages that are truly needed. Avoid opening all of `java.base` or multiple internal packages at once.
2. Prefer specifying a named target module instead of `ALL-UNNAMED` if the framework runs in a named module.
3. Do not treat the flag as a way to fix API design. If new code needs access to data, prefer a public API or an SPI exposed by the module.
4. The flag does not modify `module-info.class`, does not alter JAR files, and does not automatically cause dependencies to resolve.
5. The flag does not bypass all JVM restrictions. For example, certain special final fields still cannot be modified via reflection even when the package is opened.
6. The open permission exists only in the JVM launched with the flag. A passing test run does not prove production has the same configuration.
7. Avoid relying on internal JDK packages because they are not stable APIs and can change across releases.

Since JDK 16/17, strong encapsulation for many internal APIs has been enforced more strictly. The old `--illegal-access` option is not a reliable workaround on newer JDKs. When encountering `InaccessibleObjectException`, identify the module and package in the error message and open only the exact package for the exact target module if genuinely needed.

## 10. Workflow for Diagnosing Deep Reflection Errors

When a library throws `InaccessibleObjectException` or `trySetAccessible()` returns `false`, follow these steps in order:

1. Read the full error message to identify the blocked source module and package.
2. Identify the target module containing the code performing reflection. If the code is on the classpath, the target module is the unnamed module.
3. Confirm the API actually needs deep reflection. If it only needs public APIs of an unexported package, evaluate `--add-exports`.
4. Add exactly one `--add-opens=source-module/package=target-module` option to the JVM actually running the code.
5. Re-run the same command and verify `trySetAccessible()` or `Module.isOpen(package, targetModule)`.
6. If running via Gradle, Maven, an IDE, or a container, inspect the child JVM's command line; do not inspect only the build configuration.
7. If the module belongs to your own project, consider declaring `opens package to target.module;` in the descriptor so access permissions are managed alongside source.
8. After upgrading the framework or eliminating the need for reflection, remove the flag and verify that the application still works.

The goal is to open the right package, in the right module direction, on the right JVM. That resolves deep reflection requirements while keeping access scope controllable.
