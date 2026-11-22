# Testing `--add-opens`, Reflection, and Strong Encapsulation

## Objectives

After this lab, you can create a module with an internal package, demonstrate that deep reflection is blocked when the package is not opened, re-run with `--add-opens`, distinguish whether the target is a named module or `ALL-UNNAMED`, verify state using Reflection and the Module API, and properly configure JVM arguments for test runners.

## 1. Test Model

We create a `com.acme.domain` module with an API package and an internal implementation package. A probe program acts as a framework, using reflection to read a private field in the internal package.

Structure:

~~~text
project/
  src/
    com.acme.domain/
      module-info.java
      com/acme/domain/internal/Customer.java
  probe/
    ReflectionProbe.java
  mods/
  probe-classes/
~~~

The descriptor exports only the API package:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Class in the internal package:

~~~java
package com.acme.domain.internal;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }
}
~~~

Package `com.acme.domain.internal` is neither exported nor opened. The class has the `public` modifier, but that does not automatically grant other modules access to the package.

## 2. Creating ReflectionProbe on the classpath

Create file `probe/ReflectionProbe.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
                Class.forName("com.acme.domain.internal.Customer");

        Constructor<?> constructor =
                type.getDeclaredConstructor(String.class);

        boolean constructorOpen = constructor.trySetAccessible();
        System.out.println("constructor accessible = " + constructorOpen);

        if (!constructorOpen) {
            throw new IllegalStateException(
                    "Customer constructor is not open to this module");
        }

        Object customer = constructor.newInstance("Ada");

        Field name = type.getDeclaredField("name");
        boolean fieldOpen = name.trySetAccessible();
        System.out.println("field accessible = " + fieldOpen);

        if (!fieldOpen) {
            throw new IllegalStateException(
                    "Customer.name is not open to this module");
        }

        System.out.println("name = " + name.get(customer));
    }
}
~~~

The probe uses a string class name so it does not need to import classes from the internal package. It checks both the constructor and the field because frameworks may need to instantiate objects and read object state via reflection.

`trySetAccessible()` returns `false` if access cannot be opened. If using `setAccessible(true)`, the operation may throw `InaccessibleObjectException` when module boundaries disallow deep reflection.

## 3. Compiling and running while the package is unopened

From the `project` directory, compile the domain module:

~~~bash
javac -d mods --module-source-path src -m com.acme.domain
~~~

Compile the probe:

~~~bash
javac -d probe-classes probe/ReflectionProbe.java
~~~

Run the probe with the domain module resolved:

~~~bash
java --module-path mods --add-modules com.acme.domain --class-path probe-classes ReflectionProbe
~~~

`--add-modules com.acme.domain` adds the domain module into the startup graph, even though the probe's main class sits on the classpath. The probe belongs to the unnamed module of the application class loader.

Because the internal package is neither exported nor opened to the unnamed module, `trySetAccessible()` on the constructor will return `false`. The program stops with the message produced by the probe. This is the expected result of the first step.

You can switch the probe to `constructor.setAccessible(true)` to observe the exception directly. When a package is not opened to the caller, the JVM can throw `InaccessibleObjectException`. The exception message usually names the source module, package, and target module; that serves as evidence for writing an option with the exact scope.

## 4. Opening the package to the unnamed module with ALL-UNNAMED

Re-run with:

~~~bash
java --module-path mods --add-modules com.acme.domain --add-opens com.acme.domain/com.acme.domain.internal=ALL-UNNAMED --class-path probe-classes ReflectionProbe
~~~

Expected output:

~~~text
constructor accessible = true
field accessible = true
name = Ada
~~~

How to read the option:

~~~text
--add-opens source-module/package=target-module
~~~

- `com.acme.domain` is the module owning the package.
- `com.acme.domain.internal` is the package to open.
- `ALL-UNNAMED` is the target representing unnamed modules.

`ALL-UNNAMED` does not mean opening all packages or the entire module. It only grants permission to unnamed target modules for the specified package. If the framework resides on the classpath, this is usually the right target.

## 5. Testing with the framework as a named module

If the framework is placed on the module path, specify the framework's module name instead of `ALL-UNNAMED`.

Example descriptor for the probe module:

~~~java
module com.acme.framework {
    requires com.acme.domain;
}
~~~

The probe still uses `Class.forName("com.acme.domain.internal.Customer")`, so it does not need to import internal classes. The `requires` dependency lets the framework module read the domain module; the internal package remains unexported.

After compiling the framework onto the module path, run:

~~~bash
java --module-path mods --add-opens com.acme.domain/com.acme.domain.internal=com.acme.framework --module com.acme.framework/com.acme.framework.ReflectionProbe
~~~

The target in the option is `com.acme.framework`, because the code performing reflection belongs to this named module.

If opened to the wrong target module, the probe still lacks deep reflection permission. Identify the actual module of the framework class:

~~~java
Module frameworkModule = FrameworkEntryPoint.class.getModule();

System.out.println("name = " + frameworkModule.getName());
System.out.println("named = " + frameworkModule.isNamed());
~~~

If `isNamed()` returns `false`, the class belongs to the unnamed module and the corresponding target in the JVM option is `ALL-UNNAMED`.

## 6. Checking access permissions using the Module API

You can print module state and verify package openness from the probe:

~~~java
Module source = type.getModule();
Module target = ReflectionProbe.class.getModule();

System.out.println("source module = " + source.getName());
System.out.println("target module = "
        + (target.isNamed() ? target.getName() : "<unnamed>"));

boolean open = source.isOpen(
        "com.acme.domain.internal",
        target);

System.out.println("package open = " + open);
~~~

Call `isOpen(packageName, targetModule)` on the module owning the package. If `--add-opens` was applied for the right target, the result will be `true`.

You can add layer and class loader information:

~~~java
System.out.println("source layer = " + source.getLayer());
System.out.println("source loader = " + source.getClassLoader());
System.out.println("target layer = " + target.getLayer());
System.out.println("target loader = " + target.getClassLoader());
~~~

Layer and class loader details are useful when an application uses plugins or creates multiple module layers. A module name alone may not be enough to identify a module instance in a process with multiple layers.

## 7. Testing JDK strong encapsulation

JPMS applies module boundaries to the JDK's platform modules. On modern JDKs, many internal packages are no longer broadly opened for reflection as some legacy applications used to assume.

Example trying to access the private `detailMessage` field of `Throwable`:

~~~java
import java.lang.reflect.Field;

Field detailMessage =
        Throwable.class.getDeclaredField("detailMessage");

System.out.println(detailMessage.trySetAccessible());
~~~

Running the probe on the classpath without a JVM option opening the package may output `false`. To test compatibility in the lab:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED --class-path probe-classes JdkReflectionProbe
~~~

Package `java.lang` belongs to module `java.base`; the target is the probe's unnamed module. When the package is opened, `trySetAccessible()` can return `true`.

This is only a mechanism test. Do not rely on private fields or JDK internal implementations as a stable application API. Prefer public JDK and framework APIs. On JDK 17 and later, strong encapsulation of JDK internals is enforced by default; `--illegal-access` does not restore the old broad access mechanism.

## 8. Placing options properly in Maven, Gradle, and IDEs

`--add-opens` is a JVM option. It must be passed to the Java process performing reflection, not as an argument to `main`.

### Maven Surefire

If tests run in a forked JVM, configure options for the test process using `argLine`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-opens java.base/java.lang=ALL-UNNAMED --add-opens com.acme.domain/com.acme.domain.internal=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

Ensure the forked test JVM has the domain module on the module path and resolved. Module path configuration depends on how the modular project is built/tested; adding `argLine` alone does not automatically bring the domain module into the graph.

### Gradle

For test tasks using a forked JVM:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=com.acme.domain/com.acme.domain.internal=ALL-UNNAMED"
    )
}
~~~

If tests run in a named test module, replace target `ALL-UNNAMED` with the test module's name when appropriate.

### IDE

In Run/Debug configurations, put the option in the **VM options** field:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Do not put the option into **Program arguments**. If a framework runs inside a JVM spawned by an application server or test runner, the option must be configured on that exact process. The IDE's or build daemon's JVM does not automatically forward options to all child processes.

## 9. Confirming the option was applied

When suspecting a JVM option is not reaching the right process, print input arguments from inside the program:

~~~java
import java.lang.management.ManagementFactory;

ManagementFactory.getRuntimeMXBean()
        .getInputArguments()
        .forEach(System.out::println);
~~~

The output should contain the configured `--add-opens` option. This helps distinguish launcher configuration errors from picking the wrong source package or target module.

Access can be verified in two ways:

1. Call `trySetAccessible()` on the exact member the framework needs.
2. Call `Module.isOpen(packageName, targetModule)` on the module owning the package.

If `isOpen` is `false`, double-check the source module, package spelling, and target module. If `isOpen` is `true` yet the operation still fails, review the specific member, normal Java access rules, object type, or another bug in the framework.

## 10. Test Matrix

| Source package | Target | JVM option | Expected result |
| --- | --- | --- | --- |
| `com.acme.domain.internal` | Unnamed module | None | `trySetAccessible()` returns false |
| `com.acme.domain.internal` | Unnamed module | `--add-opens com.acme.domain/com.acme.domain.internal=ALL-UNNAMED` | Returns true |
| `com.acme.domain.internal` | Named framework module | Opened to `com.acme.framework` | Returns true from framework module |
| `com.acme.domain.internal` | Named framework module | Opened to another module | Does not grant permission to framework |
| `java.base/java.lang` | Unnamed module | None | Deep reflection blocked on modern JDKs |
| `java.base/java.lang` | Unnamed module | `--add-opens java.base/java.lang=ALL-UNNAMED` | Reflection probe can access member |

For each run, record the JDK version, module path, root modules, JVM arguments, and output. When testing the wrong-target case, keep the source module and probe unchanged, changing only the target to isolate the cause.

## 11. Diagnosing common errors

### `InaccessibleObjectException`

Read the `module ... does not "opens package" to ...` part. From that, identify the source module, package, and target module. Form the option following the exact pattern:

~~~text
--add-opens source-module/package=target-module
~~~

### `trySetAccessible()` returns false

Check:

- Does the package belong to the right source module?
- Is the target the module containing the calling framework?
- Is the framework a named or unnamed module?
- Has the JVM option been passed to the right process?
- Does the test runner fork a different JVM?

### `Module ... not found`

This is a module resolution error, not a deep reflection error. Check the module path, module name, and `--add-modules` or launched root module.

### `ClassNotFoundException`

The class being inspected was not found by the active class loader. Confirm the domain module is resolved, the class was compiled into module output, and the fully qualified class name is accurate.

### Option is printed yet package remains closed

Confirm the option uses the right source module/package and target module. An option opening `java.base/java.lang` does not open `java.util`; opening to `ALL-UNNAMED` likewise does not open to a named framework module.

## 12. Principles for real applications

- Open only packages the framework genuinely needs.
- Choose a named target module when the framework runs on the module path.
- Use `ALL-UNNAMED` when the framework runs in the unnamed module.
- For modules you own, consider qualified `opens package to framework.module` in `module-info.java`.
- Document the reason for each JVM option and review them when upgrading frameworks/JDKs.
- Prefer public APIs or framework extension points instead of accessing private implementations.
- Do not use `--add-opens` to mask poor dependency or access design in unrelated packages.

## Remember

`--add-opens source-module/package=target-module` grants deep reflection permission for the right package and target. The lab proves that an internal package is blocked when unopened, and works when opened to `ALL-UNNAMED` or the appropriate named framework module. `trySetAccessible()`, `InaccessibleObjectException`, and `Module.isOpen(...)` provide runtime evidence. Place the option in the JVM arguments of the right process and keep the scope of opened packages minimal.