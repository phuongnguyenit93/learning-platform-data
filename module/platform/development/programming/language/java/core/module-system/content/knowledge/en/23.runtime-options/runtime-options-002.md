# --add-exports: Opening Temporary Exports

## 1. Objectives

The Java Platform Module System (JPMS) controls which packages of a module can be accessed by other modules. A module can declare a package as publicly exported using the **exports** directive, or export it only to specific modules using a qualified export. Unexported packages are closed to normal access from other modules.

The JDK **--add-exports** option allows adding an export during compilation or application launch. It provides a narrow-scoped way to grant access for compatibility with legacy libraries, module testing, or necessary deployment scenarios without modifying the source module's descriptor.

After this lesson, you will be able to:
- Read and write **--add-exports** syntax correctly.
- Choose the correct source module, package, and target module.
- Distinguish export permissions from module readability and deep reflection access.
- Grant permissions at compile time and runtime when needed.
- Use **ALL-UNNAMED** for code running in unnamed modules.
- Recognize the limitations and risks of depending on internal JDK APIs.

## 2. Why Is --add-exports Needed?

In JPMS, every package belongs to a module. A source module can expose its package to other modules via a directive in **module-info.java**:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

In this example, another module that reads **com.example.library** can access the public types in package **com.example.api**.

If a package is not exported, another module cannot access the public types of that package under standard module access rules. Declaring a class or method as public in source code is not sufficient to cross module boundaries: the module system also checks whether the package is exported to the accessing module.

There are cases where an application needs to access an unexported package:

- A legacy library depends on an internal JDK API.
- An application needs to use a package that is only conditionally exported to another module.
- A development team needs to run a compatibility test in an environment with strict module configuration.
- An application is gradually migrating to public APIs and needs a temporary workaround during migration.

**--add-exports** adds an export relationship at runtime or compile time. This option does not modify the **module-info.class** file, does not alter the JAR on disk, and does not create a permanent export in the source module. The additional permission applies only to the process or compilation environment configured with that option.

## 3. Syntax and How to Read It

General syntax:

~~~text
--add-exports source-module/package=target-module(,target-module)*
~~~

It can be read as:

> Export package **package** of module **source-module** to target module **target-module**.

Example:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

In the command above:

- **java.base** is the source module containing the package to access.
- **sun.nio.ch** is the additionally exported package.
- **ALL-UNNAMED** is the target module, meaning all unnamed modules.
- The remainder is the classpath and the main class to launch.

Module names and package names are case-sensitive. A slash separates the source module from the package; an equals sign separates the package from the target module. Do not append a trailing slash to the package, do not specify a class name instead of a package, and do not omit the source module name.

You can grant access to multiple target modules using a comma-separated list:

~~~text
--add-exports java.base/sun.nio.ch=com.example.app,com.example.test
~~~

Or repeat the option to export multiple packages:

~~~text
--add-exports java.base/sun.nio.ch=ALL-UNNAMED
--add-exports java.base/jdk.internal.misc=com.example.app
~~~

Each option specifies a single source-module/package pair. If multiple packages need access, declare each package separately so that the scope of permissions remains clear.

## 4. Source Module and Target Module

### Source Module

The source module is the module that **owns the package**. In the example **java.base/sun.nio.ch**, module **java.base** owns package **sun.nio.ch**.

You can inspect JDK modules and packages using the tool:

~~~bash
java --describe-module java.base
~~~

To inspect the descriptor of a modular JAR:

~~~bash
jar --describe-module --file library.jar
~~~

Do not guess the source module solely from the package name. Verify which module actually owns the package in the JDK or in the application modules.

### Target Module

The target module is the module granted access to the package. If the application is a named module, use the exact module name from the module descriptor.

Example:

~~~bash
java --add-exports java.base/sun.nio.ch=com.example.app --module-path mods --module com.example.app/com.example.Main
~~~

Here, only module **com.example.app** receives the additional export. Other modules do not automatically gain access to that package.

If the application runs on the classpath, the application classes belong to an unnamed module. In that case, use **ALL-UNNAMED**:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

**ALL-UNNAMED** covers unnamed modules, commonly encountered when running applications or libraries on the classpath. It does not mean exporting to all named modules. Using this value grants broader access than specifying a particular named module.

## 5. Export and Readability Are Two Different Conditions

For the target module to access a public type in the source module, two important conditions apply:

1. The target module must **read** the source module.
2. The package containing the type must be **exported** to the target module.

**--add-exports** only supplies the second condition. It does not automatically create a readability relationship.

In many examples with **java.base**, the application module already reads it because every module has readability to java.base. However, with another library module, the application may need to add a **requires** directive in module-info.java.

If you cannot modify the target module's descriptor, the **--add-reads** option can add a read relationship at runtime:

~~~text
--add-reads target-module=source-module
~~~

Example:

~~~bash
java --add-reads com.example.app=com.example.library --add-exports com.example.library/com.example.internal=com.example.app --module-path mods --module com.example.app/com.example.Main
~~~

The command illustrates adding two separate permissions: module **com.example.app** reads **com.example.library**, and package **com.example.internal** is exported to the application. If the module descriptor already has **requires com.example.library**, the **--add-reads** part is usually unnecessary.

Do not use **--add-exports** to fix an error where a module cannot read a dependency. Identify which condition is missing and add only the required permission.

## 6. --add-exports at Compile Time

If source code references a public type belonging to an unexported package, the compiler may reject the code even though the type is public.

You can pass **--add-exports** to **javac**:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out src/com/example/Main.java
~~~

This option allows the compiler to treat package **sun.nio.ch** of module **java.base** as exported to unnamed modules during that compilation.

Example illustrating source code referencing an internal type:

~~~java
package com.example;

import sun.nio.ch.DirectBuffer;

import java.nio.ByteBuffer;

public class Main {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(16);
        DirectBuffer internalBuffer = (DirectBuffer) buffer;
        System.out.println(internalBuffer.address());
    }
}
~~~

During compilation, the JDK may issue a warning that **DirectBuffer** is an internal API and may be removed or changed in a future release. **--add-exports** handles the module export boundary; it does not turn an internal API into a public, stable, or supported API.

For a named module, use the target module name:

~~~bash
javac --add-exports java.base/sun.nio.ch=com.example.app --module-path mods -d out --module-source-path src -m com.example.app
~~~

This example illustrates the placement of the option when compiling a module; the source tree structure and module list must match the actual project.

## 7. --add-exports at Runtime

Successful compilation does not mean the program will run. The export option passed to **javac** applies only in the compilation environment. At runtime, the JVM creates its own module graph and must be granted the corresponding export.

For an application on the classpath:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out com.example.Main
~~~

For an application that is a named module:

~~~bash
java --module-path mods --add-exports java.base/sun.nio.ch=com.example.app --module com.example.app/com.example.Main
~~~

JVM options must be placed before the part specifying the application or module to run. For example, place **--add-exports** before **--module** in the modular application launch command.

If the application is launched by a script, service manager, IDE, application server, test runner, or container, the option must be configured in the exact place that creates the JVM process. Adding the option to a build command does not guarantee it appears in the runtime process.

When running an application with **java -jar**, the application JAR is run under the classpath/unnamed module mechanism. If you want to run a modular JAR as a named module, use **--module-path** and **--module** instead of relying on **-jar**.

## 8. Distinguishing --add-exports and --add-opens

The two options have similar names but different purposes.

| Option | Purpose | Timing |
|---|---|---|
| **--add-exports** | Allows the target module to access public types and public/protected members of the exported package | Can be used at compile time and runtime |
| **--add-opens** | Allows deep reflection into a package, including reflective access to non-public members subject to reflection rules | Runtime |
| **--add-reads** | Adds a readability relationship so the target module reads the source module | Runtime |

If source code has an import statement and calls a public class in an unexported package, consider **--add-exports**.

If a framework uses reflection to access a private field, private constructor, or non-public member of a package belonging to a named module, the issue usually relates to **--add-opens**. Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
~~~

The option above opens package **java.lang** for deep reflection from unnamed modules. It does not allow source code to import an internal class from that package at compile time.

**--add-opens** is not a general replacement for **--add-exports**. Conversely, **--add-exports** does not allow frameworks to bypass all reflection boundaries to read/write private members.

## 9. Relationship with exports in module-info.java

There are two ways to create an export relationship:

**Permanent export declared by the source module:**

~~~java
module com.example.library {
    exports com.example.api;
    exports com.example.legacy to com.example.app;
}
~~~

The first directive exports **com.example.api** to every module that reads the source module. The second directive exports **com.example.legacy** only to **com.example.app**.

**Additional export from the command line:**

~~~bash
java --add-exports com.example.library/com.example.internal=com.example.app --module-path mods --module com.example.app/com.example.Main
~~~

The second approach does not modify the module descriptor. It adds an export in the process's module configuration. Therefore:

- If you own the source module and the package is an API that other modules need over the long term, consider declaring **exports** in module-info.java.
- If you only need to grant compatibility access for a specific application, the command-line option may be more appropriate.
- If the package is an internal JDK API, prefer a supported public API rather than turning this option into a long-term dependency.
- If the source module changes its name or packages, the old command line may no longer be valid.

A qualified export in a module descriptor can allow only certain modules to access it. **--add-exports** adds another target module to the export scope at runtime/compile time accordingly; it does not rewrite the original directive.

## 10. Complete Example: Application on the Classpath

Suppose an application has a class using the **sun.nio.ch.DirectBuffer** type:

~~~java
package com.example;

import java.nio.ByteBuffer;
import sun.nio.ch.DirectBuffer;

public class Main {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(32);
        DirectBuffer direct = (DirectBuffer) buffer;
        System.out.println(direct.address());
    }
}
~~~

Compile:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out src/com/example/Main.java
~~~

Run:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out com.example.Main
~~~

Both phases require the option. If the option is omitted at compile time, javac may report that the package is not exported. If compilation succeeds but the option is omitted at runtime, the JVM may throw **IllegalAccessError** when the code attempts to access that type.

The example using an internal API is solely to illustrate the mechanism. In real applications, look for a supported alternative API before applying this approach.

## 11. Complete Example: Application on the Module Path

Suppose the application module has the descriptor:

~~~java
module com.example.app {
    requires java.base;
}
~~~

Source code in the module uses a public type belonging to package **sun.nio.ch**. It can be compiled with an additional export:

~~~bash
javac --add-exports java.base/sun.nio.ch=com.example.app --module-source-path src -d mods -m com.example.app
~~~

After compiling, run the module with the same export:

~~~bash
java --module-path mods --add-exports java.base/sun.nio.ch=com.example.app --module com.example.app/com.example.Main
~~~

Here, the target module is **com.example.app**, because the code is running inside a named module. Do not use **ALL-UNNAMED** for this example because the application does not belong to an unnamed module.

If the application depends on modules other than java.base, ensure the descriptor has the corresponding **requires** or configure appropriate readability. Additional exports do not replace application dependencies.

## 12. Configuration in Build and Runtime Environments

In Maven or Gradle projects, distinguish between compiler arguments and runtime JVM arguments.

- **Compile:** pass the option to the compiler plugin or compile task so source code can see the required package.
- **Test:** pass the option to the JVM running tests. Some test runners fork a separate process, so configuration on Maven/Gradle's own JVM does not necessarily apply automatically to the forked process.
- **Run:** pass the option to the application run task, launch script, or IDE JVM configuration.
- **Deploy:** update the configuration of the service/container that actually launches the application; then inspect the command line or startup logs to verify that the option was applied.

Do not simply add **--add-exports** to the compile configuration and assume the problem is solved. Identify which process actually needs package access and configure it at the right phase.

In CI environments, you can place the option in a centralized configuration so compile, test, and run commands use it consistently. Clearly document the module/package/target and the reason access is needed so the operations team knows when it can be removed.

## 13. Limitations and Risks

**--add-exports** is a compatibility mechanism, not a promise of API stability.

Packages such as **sun.nio.ch**, **jdk.internal.misc**, or other internal packages are not part of the supported public API. Structure, class names, methods, and behavior can change between JDK versions. A command that works on the current JDK may fail after a JDK upgrade.

This option also weakens module encapsulation boundaries for the target module. If an export is granted to **ALL-UNNAMED**, every unnamed module in the process can access the exported package. That is broader than granting it to a specific named module.

Some operational principles:

1. Grant access to the exact package and the exact target module.
2. Avoid exporting to **ALL-UNNAMED** if a named module can be specified.
3. Do not grant broad permissions just to make another error disappear.
4. Document the reason, owner, and condition for removing the option.
5. Re-verify when upgrading the JDK or libraries.
6. Monitor compiler warnings about internal APIs and plan for replacements.
7. Do not confuse successful access with that API being supported or guaranteed compatible.

Since JDK 17, strong encapsulation of internal packages in the JDK has been enforced more strictly. The old **--illegal-access** option is no longer a general way to open these packages. If you need access to a specific package, understand and use the right **--add-exports** or **--add-opens** option according to the type of access.

## 14. Common Errors and Diagnosis

| Symptom | Possible Cause | Resolution |
|---|---|---|
| javac reports package is not exported | Missing export at compile time or wrong module/package | Add --add-exports to javac with the right source module and target |
| Runtime throws IllegalAccessError | Compile has permission but runtime JVM lacks the export | Add the same option to the java command |
| Module cannot read type of another module | Missing readability, not export | Check requires or --add-reads |
| Reflection reports InaccessibleObjectException | Needs deep reflection into an unopened package | Consider --add-opens for the target module |
| Still fails even after adding option | Wrong source module, package, target module, or option placed on wrong process | Identify the module containing the class, the calling module, and the JVM actually launched |
| Classpath works but named module fails | Target module differs or descriptor lacks requires | Use the right named module name and check the module graph |
| Fails after JDK upgrade | Internal API changed or was removed | Migrate to a public API and check release notes |

When diagnosing, obtain the full error message, identify the accessing class, the package containing the class, the module owning the package, and the target module. Then check both the compiler command line and the runtime command line. Do not assume that having the option in a configuration file means the JVM process definitely received it.

## 15. Self-Check

**1. What does --add-exports java.base/sun.nio.ch=ALL-UNNAMED mean?**

It adds an export of package **sun.nio.ch** from module **java.base** to all unnamed modules within the configured scope. This is commonly how permissions are granted to application code running on the classpath.

**2. Does --add-exports modify module-info.class?**

No. The option only adds the export in the respective compile or runtime environment; the module descriptor file on disk is not altered.

**3. Why is the option needed both at compile time and at runtime?**

Because javac and the JVM have separate module configurations. The compile-time option allows source code to reference the package; the runtime option allows bytecode to actually access the package when the application runs.

**4. Does --add-exports allow accessing private fields via reflection?**

No. It exports the package for normal access to public types/members. Deep reflection into non-public members typically requires **--add-opens** at runtime.

**5. Does --add-exports automatically make the target module read the source module?**

No. Export and readability are two different conditions. If the target module does not read the source module, you must fix **requires** or consider **--add-reads**.

**6. Does ALL-UNNAMED include all named modules?**

No. It applies only to unnamed modules, typically code on the classpath. Named modules must be specified explicitly by name.

## 16. Key Takeaways

**--add-exports** creates an additional export scoped by source module, package, and target module. It is useful for compiling or running applications that need access to an unexported package, but it does not modify the module descriptor, does not add readability, and does not open private members for deep reflection.

Use the correct target module, grant permissions at both compile time and runtime when needed, and prefer public APIs over depending on internal JDK packages. Treat this option as a compatibility measure that can be removed once the application has migrated to supported APIs.

## References

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
