# InaccessibleObjectException Due to Missing Opens

When upgrading an application to the Java Platform Module System (JPMS), a common runtime error is **`java.lang.reflect.InaccessibleObjectException`**. The error typically occurs when a library or application code attempts to use reflection to access a non-public field, method, or constructor in a named module, yet **the package containing that member has not been opened to the module performing reflection**.

A common point of confusion: a package may already have `exports`, the Java type may be `public`, and the caller may `requires` the source module, yet `setAccessible(true)` is still rejected. The reason is that **`exports` and `opens` grant two different kinds of permission**: exports serve public API access under Java language rules; opens serve deep reflection at runtime.

This lesson guides you through reading the error message, identifying the source and caller modules, reproducing a case with two named modules, fixing it with `opens` or `--add-opens`, recognizing scenarios where frameworks sit on the classpath, and checking configurations across tests, builds, and containers.

## 1. Reading the InaccessibleObjectException message accurately

A typical message:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final java.lang.String
com.acme.domain.api.Person.name accessible:
module com.acme.domain does not
"opens com.acme.domain.api" to module com.acme.inspect
    at java.base/java.lang.reflect.AccessibleObject.checkCanSetAccessible(...)
    at java.base/java.lang.reflect.Field.setAccessible(...)
    at com.acme.inspect/com.acme.inspect.Main.main(...)
~~~

Components to identify:

- **`com.acme.domain`** is the module owning the accessed class/field.
- **`com.acme.domain.api`** is the package that needs opening; opening the entire module is not necessarily required.
- **`com.acme.inspect`** is the module directly performing the reflective access.
- **`Person.name`** is the private field the code attempted to access.
- **`Field.setAccessible`** is the signal that bypassing normal access-modifier checks was requested.

If the reflection library resides on the classpath, the message may read `to unnamed module` along with class loader or identity details. In that case, the target module has no name like named modules on the module path.

Do not fix by guessing solely from the main application name: an ORM/JSON library or test runner is often the actual caller invoking `setAccessible`.

## 2. exports differs from opens

Consider a module:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

A public class:

~~~java
package com.acme.domain.api;

public final class Person {
    private final String name;

    public Person(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Another module with `requires com.acme.domain` can invoke the public constructor and `name()`:

~~~java
Person person = new Person("An");
System.out.println(person.name());
~~~

However, the following code requires deep reflection:

~~~java
Field field = Person.class.getDeclaredField("name");
field.setAccessible(true);
System.out.println(field.get(person));
~~~

Even when the package is exported, the field remains private. JPMS does not allow external modules to bypass access checks on private fields by default. If the package is not open to the caller, `setAccessible(true)` can throw `InaccessibleObjectException`.

Therefore, distinguish among:

| Question | JPMS mechanism |
|---|---|
| Can module A read module B? | `requires` or a valid readability relationship |
| Can B's package be used as API from A? | `exports` |
| Can Java code access a member according to its modifier? | `public`, `protected`, package-private, `private` |
| Can A perform deep reflection into B's package? | `opens` or `--add-opens` |

Ordinary reflection on public members of public types in exported packages does not necessarily require opens. Opens becomes crucial when a framework wants to suppress access checks on non-public members.

## 3. Minimal fixture: two named modules

Create the source directory:

~~~text
src/
├── com.acme.domain/
│   ├── module-info.java
│   └── com/acme/domain/api/Person.java
└── com.acme.inspect/
    ├── module-info.java
    └── com/acme/inspect/Main.java
~~~

Domain module:

~~~java
// src/com.acme.domain/module-info.java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Class containing a private field:

~~~java
// src/com.acme.domain/com/acme/domain/api/Person.java
package com.acme.domain.api;

public final class Person {
    private final String name;

    public Person(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

Inspector module:

~~~java
// src/com.acme.inspect/module-info.java
module com.acme.inspect {
    requires com.acme.domain;
}
~~~

Main:

~~~java
// src/com.acme.inspect/com/acme/inspect/Main.java
package com.acme.inspect;

import com.acme.domain.api.Person;
import java.lang.reflect.Field;

public final class Main {
    public static void main(String[] args) throws Exception {
        Person person = new Person("An");
        System.out.println("Getter: " + person.name());

        Field field = Person.class.getDeclaredField("name");
        field.setAccessible(true);
        System.out.println("Reflect: " + field.get(person));
    }
}
~~~

Compile:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.acme.domain,com.acme.inspect
~~~

Run:

~~~bash
java --module-path out \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

First, the public getter succeeds:

~~~text
Getter: An
~~~

Then `setAccessible(true)` fails because `com.acme.domain` only exports the package and has not opened it to `com.acme.inspect`. This is the empirical difference between ordinary API access and deep reflection permission.

## 4. Fixing in module-info.java when you control the source module

If the inspector module genuinely needs reflection on the API package, update the domain module's descriptor:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.api to com.acme.inspect;
}
~~~

Recompile and run with the same command:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.acme.domain,com.acme.inspect

java --module-path out \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

Expected output:

~~~text
Getter: An
Reflect: An
~~~

`opens com.acme.domain.api to com.acme.inspect` is a **qualified opens**: the package is opened only to the inspector module. Other modules do not automatically receive corresponding reflection rights.

If a framework needs reflection on a model package whose API is not public, exports and opens can be separated:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.serializer;
}
~~~

Other modules can import public types in `api` when they have readability; only module `com.acme.serializer` is permitted deep reflection on `model`. `opens` does not make `model` a public package to import like normal API.

## 5. Unqualified opens and open module

When a specific target module cannot be named, the descriptor can open a package to all modules:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model;
}
~~~

`opens com.acme.domain.model` is broader than qualified opens because it does not restrict target named modules.

Alternatively:

~~~java
open module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

`open module` opens all packages of the module for deep reflection. This occasionally serves a framework needing access to many packages, yet it weakens strong encapsulation across the entire module.

Do not switch to `open module` just to fix one error on one field. Prefer the smallest package and a specific target module whenever possible. Inside an `open module`, individual `opens` directives are not declared.

## 6. Runtime workaround using --add-opens

If the descriptor cannot yet be edited, the Java launcher supports:

~~~text
--add-opens source.module/package=target.module
~~~

Example:

~~~bash
java --module-path out \
     --add-opens com.acme.domain/com.acme.domain.api=com.acme.inspect \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

The `--add-opens` option adds package-open permission for that run without modifying `module-info.class` inside the JAR. Thus, if you drop the flag on a later run, the error may return.

Equals-sign form can also be used:

~~~bash
java --add-opens=com.acme.domain/com.acme.domain.api=com.acme.inspect \
     --module-path out \
     -m com.acme.inspect/com.acme.inspect.Main
~~~

For multiple target named modules, separate with commas:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.model=com.acme.json,com.acme.orm \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

`com.acme.json` and `com.acme.orm` are illustrative names only. In a real project, verify the framework's module name from the descriptor in the artifact; do not guess from package names or Maven Central artifact names.

If the application has a compile-time error because source imports a public type from an unexported package, `--add-opens` is not the right fix. Check `exports` or `--add-exports` and readability.

## 7. Frameworks on the classpath and ALL-UNNAMED

When a JSON serializer, ORM, or test framework runs on the classpath, its classes belong to the unnamed module. The error message usually looks like:

~~~text
module com.acme.domain does not
"opens com.acme.domain.model" to unnamed module ...
~~~

Workaround:

~~~bash
java --add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED \
     --module-path mods \
     --class-path "lib/*" \
     -m com.acme.app/com.acme.app.Main
~~~

`ALL-UNNAMED` is a special JVM option target that allows unnamed modules to perform deep reflection on that package.

Do not write:

~~~java
// Not valid module-info.java syntax:
opens com.acme.domain.model to ALL-UNNAMED;
~~~

Reason: `ALL-UNNAMED` is not a named module's name. In a descriptor, you can use unqualified `opens package;` if genuinely intended, or move the framework to a named module to use qualified opens where feasible.

`ALL-UNNAMED` has a wider scope than opening to one specific named framework. In environments with many libraries on the classpath, weigh the impact and use broad scope only when needed.

## 8. Identifying the exact module performing reflection

The call chain may look like:

~~~text
com.acme.app
    |
    v
com.acme.serializer
    |
    | Field.setAccessible(true)
    v
com.acme.domain.model.Customer
~~~

The target of `opens` is the **serializer module**, not necessarily `com.acme.app`. The app invokes the serializer, yet the serializer is what calls the reflection API.

Check the target class's module:

~~~java
Class<?> target = Person.class;
Module owner = target.getModule();

System.out.println("Class: " + target.getName());
System.out.println("Package: " + target.getPackageName());
System.out.println("Module: " + owner.getName());
~~~

If a framework class is accessible:

~~~java
Module caller = SomeFrameworkClass.class.getModule();
System.out.println(caller.getName());
~~~

`Module.getName()` returns `null` for an unnamed module.

When there is no API to import the framework class directly, read the stack trace: find the class calling `Field.setAccessible`, `Constructor.setAccessible`, or the equivalent reflection API. That is the starting point for identifying the named/unnamed caller.

## 9. Checking opens via the Module API

You can use:

~~~java
Module domain = Person.class.getModule();
Module inspector = Main.class.getModule();
String pkg = Person.class.getPackageName();

System.out.println(
    "exported=" + domain.isExported(pkg, inspector)
);
System.out.println(
    "open=" + domain.isOpen(pkg, inspector)
);
~~~

With the initial fixture, `exported` may be `true` while `open` is `false`. After adding the right `opens` or `--add-opens`, `open` should become `true` for the inspector module.

Two overloads to distinguish:

- `isOpen(String packageName)` checks whether the package is open unconditionally.
- `isOpen(String packageName, Module other)` checks open permission for a specific module.

For qualified opens, use the overload taking a target module. `canRead` or `isExported` may return true without proving `isOpen` is true.

## 10. setAccessible and trySetAccessible

The error is typically triggered by:

~~~java
Field field = Person.class.getDeclaredField("name");
field.setAccessible(true);
~~~

To proactively check permission before use:

~~~java
Field field = Person.class.getDeclaredField("name");

if (field.trySetAccessible()) {
    System.out.println(field.get(new Person("An")));
} else {
    System.out.println("Deep reflection is not allowed");
}
~~~

`trySetAccessible()` can return `false` if access checks cannot be suppressed due to module restrictions. It avoids throwing `InaccessibleObjectException` in some cases where `setAccessible(true)` would, yet it does not fix JPMS configuration.

`getDeclaredField` only retrieves metadata about the field; finding the field does not mean the caller is permitted to read/write the private value. Other exceptions such as `NoSuchFieldException` or `IllegalAccessException` have their own causes.

One library might fall back to a public getter/factory when deep reflection is disallowed; an ORM that strictly requires internal field access might need to fail fast with specific configuration guidance.

## 11. Comparing similarly named errors

| Exception/error | Common issue | Investigation direction |
|---|---|---|
| `InaccessibleObjectException` | Suppressing access checks via reflection is disallowed | `opens`, `--add-opens`, caller module |
| `IllegalAccessException` | Reflection lacks sufficient access rights during operation | Access modifiers, accessible flag |
| `IllegalAccessError` | Invalid access rights during bytecode linking/execution | Readability, exports, runtime artifacts |
| `NoSuchFieldException` | Field does not exist under looked-up name/class | Field name, API version, actual class |
| `ClassNotFoundException` | Class not found via loader | Module/class path, layer, loader |
| `FindException` | Module not found during resolution | Module name, path, runtime image |
| `ServiceConfigurationError` | Provider not found or not instantiated properly | `uses`, `provides`, service loading |

Do not use `--add-opens` for every runtime error. If a module cannot be found, resolve the module source; if public API is not exported, handle exports; if private reflection is blocked, opens is the right direction to investigate.

## 12. JDK internals and Java 17+

Older libraries may use reflection against internal JDK packages or core Java classes. A message might mention:

~~~text
module java.base does not "opens java.lang" to unnamed module ...
~~~

Temporary workaround:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -cp "lib/*" \
     com.acme.Main
~~~

This can help an older dependency run during a transition, yet it should not be treated as a permanent solution.

Since Java 17, strong encapsulation of JDK internals is enforced more strictly. The legacy `--illegal-access` option is no longer a way to restore all prior internal access. Prefer upgrading the framework or library, or replacing internal API calls with supported public APIs.

You cannot edit `module-info.java` of `java.base` like a normal application module. Thus `--add-opens java.base/...` may be a temporary compatibility measure while documenting the risk for future JDK upgrades.

## 13. ORM, JSON, and dependency injection

Frameworks may need to instantiate entities via non-public constructors, access private fields, or generate proxies.

Example descriptor for a module owning entities:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.entity to com.acme.orm;
}
~~~

The `entity` package is opened to the ORM framework, yet not exported as public API to other consumers.

The framework's actual module name should be verified:

~~~bash
jar --describe-module --file lib/framework.jar
~~~

The same library can sit on the classpath, on the module path as an automatic module, or as an explicit named module, depending on packaging and runtime config. Each case determines the opens target differently.

Do not copy the value `com.acme.orm` into a real configuration if it is not the exact module name. If only public constructors/getters in exported packages are needed, many frameworks can work without opening packages deeply.

## 14. JUnit and test runtime

In modular projects, a JUnit engine or mocking framework sometimes uses reflection on non-public test classes inside a named module.

Example:

~~~text
Test class: com.acme.app.internal.AppTest
Owner module: com.acme.app
Test engine: unnamed module on classpath
~~~

A JVM option may be required in the **exact process running tests**:

~~~bash
--add-opens com.acme.app/com.acme.app.internal=ALL-UNNAMED
~~~

Gradle Groovy DSL:

~~~groovy
tasks.named('test', Test) {
    jvmArgs(
        '--add-opens',
        'com.acme.app/com.acme.app.internal=ALL-UNNAMED'
    )
}
~~~

Maven Surefire example:

~~~xml
<configuration>
    <argLine>
        --add-opens com.acme.app/com.acme.app.internal=ALL-UNNAMED
    </argLine>
</configuration>
~~~

Verify that the JVM options reach the actual forked test process. Adding flags to the JVM running the build tool does not guarantee the test runner's forked JVM receives those flags.

If the engine is a named module, open to its actual module name rather than `ALL-UNNAMED`. If test sources need to reside inside the same module to access package-private code, also look at `--patch-module`; it addresses a different goal than `--add-opens`.

## 15. CI and container configuration

A common failure is local runs succeeding while CI/containers fail with `InaccessibleObjectException`. Causes can include inconsistent JVM arguments or different JDK versions.

Verification checklist:

1. Actual Java binary, vendor, and version.
2. Startup command, Docker ENTRYPOINT, or process manager.
3. JVM options passed **before the main class or `-m`**.
4. Named module/classpath placement of the framework.
5. Deployed module descriptor/JAR artifacts.
6. The list of `--add-opens` in the IDE, Gradle/Maven tests, CI, and production.
7. Readiness, integration tests, and the real code path triggering reflection.

You can inspect the command line of a running JVM using JDK tooling:

~~~bash
jcmd <pid> VM.command_line
~~~

`<pid>` is a placeholder to replace with the process ID.

Running only a smoke test that exercises public getters gives no proof that ORM/serialization paths are free of errors. You must test the exact path that previously called `setAccessible`.

## 16. ModuleLayer and dynamic package opening

Some plugin systems create `ModuleLayer`s at runtime. `ModuleLayer.Controller` can be used to adjust `opens` for modules managed by the controller:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(parent),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer layer = controller.layer();

Module plugin = layer
    .findModule("com.acme.plugin")
    .orElseThrow();

controller.addOpens(
    plugin,
    "com.acme.plugin.internal",
    frameworkModule
);
~~~

This example assumes `frameworkModule` is the framework's exact `Module` object and the package exists in the plugin module. Not every controller has permission to open arbitrary packages on arbitrary other modules.

`Module.addOpens` also enforces caller/ownership rules: code from another module cannot arbitrarily open a package without permission from the source module. When designing plugins, restrict runtime adjustments to modules managed by the framework and open only necessary packages.

## 17. Path to a sustainable transition

When fixing the error, consider three strategies in order:

**A. Eliminate private reflection when unnecessary.** If a stable public API, constructor, factory, adapter, or service interface can be designed, use it instead of accessing private state directly.

**B. Declare scoped opens in descriptors you own.** When reflection is a genuine integration contract, use qualified `opens package to framework.module`. Do not export internal packages just for framework reflection.

**C. Keep runtime workarounds controlled.** For dependencies outside your control to edit, use `--add-opens` with exact module/package/target; document the reason, affected library version, and removal condition on upgrade.

Avoid these habits:

- Opening every package of `java.base` or every module in the app because of a single error.
- Converting every module to `open module` when only one entity needs reflection.
- Adding `--add-exports` expecting it to substitute for `--add-opens`.
- Adding flags while forgetting to check the actual JVM running in CI/containers.
- Dropping all flags in one upgrade without running integration tests.

Every open permission should have a concrete reason, specific module/package scope, and clear maintenance ownership.

## 18. Practical diagnostic workflow

When encountering `InaccessibleObjectException`:

1. **Read the full message**, identifying the source module, package, and target module/unnamed module.
2. **Find the caller in the stack trace**, determining which library invoked reflection.
3. **Check class identity**, verifying the expected class/module and JAR.
4. **Assess necessity**, whether private reflection is mandatory or a public API alternative exists.
5. **Measure permissions**, using `Module.isOpen(package, targetModule)` when possible.
6. **Apply a narrow fix**, choosing qualified opens or `--add-opens`.
7. **Ensure the target module exists**, without guessing from artifact filenames.
8. **Apply to the right JVM**, including test forks or containers.
9. **Re-run the failing flow**, not merely startup checks.
10. **Document a long-term plan**, removing workarounds once dependencies support stable integration.

If opening package A shifts the error to package B, do not immediately add an endless list of opens. The framework may be coupling too deeply to internal implementation details or its reflection setup may not match JPMS architecture.

## 19. Quick resolution matrix

| Scenario | Preferred solution |
|---|---|
| Team-owned app module needs regular reflection | Qualified `opens` in `module-info.java` |
| Named framework module needs to read private entity fields | `opens entity.package to framework.module` |
| Framework sits on classpath | Workaround `--add-opens source/pkg=ALL-UNNAMED` if needed |
| Legacy framework reflects into JDK internals | Upgrade/replace API; selectively open JDK packages only |
| Unit test engine needs reflection | Test-only `--add-opens`, on the right test JVM |
| Cannot import a public type | Check `requires` and `exports` |
| Cannot find module/class | Check module path, class loader, ModuleLayer |
| Service provider not found | Check `uses`, `provides`, module resolution |
| Only want to inspect member metadata | Simple metadata queries typically do not need opens |
| Want to access a private field | Need appropriate deep reflection permission or design change |

## 20. Key takeaways

**`InaccessibleObjectException` usually indicates missing deep reflection permission, not simply missing `public` or `requires`.** `exports` allows public APIs to be used across module boundaries; `opens` allows target modules to perform reflection on non-public members in a package.

When you control the source module, use `opens pkg to target.module` with the smallest scope. When you cannot edit the descriptor yet, use `--add-opens source.module/pkg=target.module`, or `ALL-UNNAMED` if the caller is on the classpath. For internal JDK APIs, prefer upgrading libraries and using public APIs over maintaining broad open permissions long-term.

To verify the fix, pinpoint the exact source module/package and caller in the error, inspect open status, apply the permission to the right JVM process, and re-run the real reflection code path. The goal is not opening every package for convenience, but **opening the right package to the right module that needs access, in the right environment, and for a clear technical reason**.