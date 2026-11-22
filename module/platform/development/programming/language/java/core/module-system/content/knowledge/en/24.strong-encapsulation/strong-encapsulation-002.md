# JDK Internal APIs and Migration Warnings

## 1. Objectives

The JDK provides public APIs for long-term use by applications and libraries. Alongside them, the JDK source code contains many classes, packages, and mechanisms meant solely for internal platform implementation. These components are commonly called **JDK internal APIs**.

An application may have been able to use an internal API on an older JDK release, but upgrading the JDK can cause the code to fail to compile, fail to launch, or fail when accessed at runtime. Starting in Java 9, the module system created clearer boundaries between public APIs and internal implementation. JDK 17 continued applying strong encapsulation by default and disabled the earlier broad relaxation mechanism.

This lesson explains what internal APIs are, why they pose risks, how to recognize migration warnings and errors, how to use dependency analysis tools, and how to replace them with supported APIs.

After this lesson, you will be able to:
- Distinguish between Java SE APIs, supported JDK-specific APIs, and JDK internal APIs.
- Understand the milestones from JDK 9 to JDK 17.
- Recognize compile errors, runtime access errors, and reflection errors caused by strong encapsulation.
- Use **jdeps --jdk-internals** to find static dependencies on JDK internals.
- Recognize the limits of static analysis and additionally check reflection at runtime.
- Plan the replacement of internal APIs and test applications after upgrading the JDK.

## 2. What Is a JDK Internal API?

A public API is an interface that is documented and guaranteed to be supported according to the compatibility policy of the platform or vendor. Java SE APIs reside in packages such as **java.lang**, **java.util**, **java.io**, **java.nio**, and many others. These APIs are the default choice for Java applications.

The JDK also contains internal implementation components. They may reside in packages named **sun.***, **com.sun.***, or **jdk.internal.***, though you should not rely solely on the prefix to draw conclusions. You need to check the API documentation, module descriptor, export status, and vendor support policy.

Examples of internal components or unsupported non-Java SE APIs:

- **sun.nio.ch**: internal implementation classes related to channels and buffers.
- **sun.security.x509**: internal implementation classes for certificate structures and security.
- **jdk.internal.misc**: internal JDK utilities.
- **sun.misc.BASE64Encoder**: legacy class not part of supported Java SE APIs; a standard replacement API exists.
- **sun.misc.Unsafe**: a special API retained for compatibility reasons, though its methods are not supported APIs for long-term application dependency.

Not every API whose name starts with **sun.** has the same status. Some important packages such as **sun.misc** and **sun.reflect** remain open for certain uses for compatibility reasons. That does not turn them into stable Java SE APIs. Verify the status of each class and method in the documentation of the target JDK.

The key point is: **a class can exist in the JDK and still not be a supported API for applications**. That source code compiles or a class can be loaded in one release does not guarantee it will continue working in the next release.

## 3. Why Does the JDK Encapsulate Internal APIs?

Internal APIs allow the JDK development team to change implementations without having to maintain every detail as a public contract. If applications depend directly on internal classes, it becomes difficult for the JDK to fix security bugs, change data structures, optimize performance, or replace algorithms without breaking external applications.

Strong encapsulation helps:
- **Increase security:** applications are less likely to interfere with sensitive internal JDK implementation details.
- **Preserve evolvability:** the JDK can evolve internals without preserving every class and method that was never published as an API.
- **Reduce tight coupling:** applications communicate through public APIs rather than relying on the internals of a specific implementation.
- **Clarify module boundaries:** module descriptors specify which packages are exported and which are internal only.

For example, if a library relies on an internal class to read the structure of a String directly, the library can break when the JDK changes how strings are represented. If the library uses String's public API, it is far less affected by such internal changes.

## 4. Strong Encapsulation Milestones from JDK 9 to JDK 17

The module system was introduced in JDK 9. To reduce impact on legacy applications, early releases still permitted certain illegal reflective accesses to JDK packages that existed in JDK 8, while emitting warnings.

Key milestones:

| Version | Change |
|---|---|
| JDK 9–15 | Module system introduced; some reflective accesses to legacy internal APIs remained relaxed by default with warnings |
| JDK 16 | Strong encapsulation became the default; compatibility options could still be used to relax some legacy accesses |
| JDK 17 onward | Strong encapsulation applied by default; **--illegal-access** became obsolete and no longer has effect |

In JDK 9 through JDK 16, the launcher had the **--illegal-access** option with modes such as **permit**, **warn**, **debug**, and **deny**. These modes served the transition phase. Starting in JDK 17, passing that option only produces a warning that the option is ignored; it does not restore internal access.

The following example is not a fix for modern JDKs:

~~~bash
java --illegal-access=permit -jar app.jar
~~~

On JDK 17 and later, do not expect this command to reopen packages. Upgrade the library, replace the internal API, or if you cannot migrate immediately, grant only specific permissions using the appropriate options.

Strong encapsulation applies to JDK internals, though compatibility exceptions should be kept in mind. Oracle's migration documentation notes that **sun.misc** and **sun.reflect** are not strongly encapsulated in the same way as other internal packages. Even so, APIs in these packages may still be unsupported and may be deprecated or undergo policy changes per method.

## 5. Signs That an Application Depends on Internal APIs

Errors can appear at multiple stages. Read the error message to determine whether it is a compile error, module access error, reflection error, or removed API.

| Stage | Common Symptom | Possible Meaning |
|---|---|---|
| Compilation | package does not exist, package is not exported, type is not accessible | Source code references an internal package that the compiler does not allow accessing |
| Launch or bytecode linking | **IllegalAccessError** | Bytecode accesses a type/member disallowed by the module system |
| Reflection | **InaccessibleObjectException** or **IllegalAccessException** | Framework attempts to open or access a non-public member in a package that is not open |
| Class loading | **ClassNotFoundException** or **NoClassDefFoundError** | Internal class was moved, removed, or is no longer provided |
| Method/field linking | **NoSuchMethodError** or **NoSuchFieldError** | Internal API changed signature or structure across JDK releases |

Common reflection error example:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

This message indicates that code is attempting reflective access to a non-public member in **java.lang**, but module **java.base** does not open that package to the target module. This is an issue with package open permissions for deep reflection; merely adding a normal export will not solve this case.

Do not search only for a single specific error string. Libraries may catch and swallow exceptions, causing the application to merely exhibit incorrect behavior or log warnings. Run representative tests and inspect both JVM logs and framework logs.

## 6. Distinguishing export, open, and Internal APIs

The following three concepts are often confused:

- **Export package:** allows target modules to access public types and public/protected members of the package under module rules.
- **Open package:** allows deep reflection into the package at runtime, including reflective access to non-public members under reflection rules.
- **Internal API:** implementation detail not committed as a public API; opening the package does not make that API stable.

Compatibility options serve different purposes:

~~~text
--add-exports source-module/package=target-module
--add-opens source-module/package=target-module
~~~

**--add-exports** is appropriate when code needs to access public types in an unexported package. It can be used at compile time and runtime.

**--add-opens** is appropriate when a library needs deep reflection into a package that is not open. It is a runtime option.

Both are only targeted boundary relaxations. They do not turn an internal package into a supported API and do not guarantee compatibility when upgrading the JDK. Do not replace every strong encapsulation error with a broad option opening packages to **ALL-UNNAMED**; that can grant wide permissions to all code running in the unnamed module.

If the target module also lacks readability to the source module, check **requires** or **--add-reads**. Exporting does not automatically create a module readability relationship.

## 7. Finding Static Dependencies with jdeps

**jdeps** is a dependency analysis tool included with the JDK. The **--jdk-internals** option finds class-level dependencies on JDK internal APIs.

Example checking a JAR:

~~~bash
jdeps --jdk-internals app.jar
~~~

If the application uses external libraries, you can include them on the analysis classpath:

~~~bash
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

The output may list the application class, the internal API it references, and suggested replacements when the tool has corresponding data. Illustrative example from Oracle documentation:

~~~text
Sample.class -> JDK removed internal API
Sample -> sun.misc.BASE64Encoder
JDK Internal API: sun.misc.BASE64Encoder
Suggested Replacement: java.util.Base64
~~~

When there are multiple JARs, analyze each application artifact and dependency. A transitive dependency may contain internal APIs even if your application source code does not directly import that package.

You can use the output to create an action list:

| Component | Internal API | Reference Location | Action |
|---|---|---|---|
| Application | sun.misc.BASE64Encoder | Data processing code | Replace with java.util.Base64 |
| Legacy library | sun.misc.Cleaner | Resource management component | Upgrade or switch to java.lang.ref.Cleaner |
| Native-memory library | sun.misc.Unsafe | Memory management | Evaluate VarHandle, ByteBuffer, or Foreign Function & Memory API |
| Reflection framework | Private members of java.* | Configuration/serialization | Upgrade framework or redesign the integration |

This table is an example of how to track tasks; replacement APIs must be chosen based on the actual functionality the code uses.

## 8. Limitations of jdeps and Checking Reflection

**jdeps is a static analysis tool**. It finds references that can be inferred from bytecode, but cannot fully detect accesses constructed dynamically.

For example, the tool may miss cases like:

~~~java
Class<?> type = Class.forName(classNameFromConfig);
Field field = type.getDeclaredField(fieldNameFromConfig);
field.setAccessible(true);
~~~

The class and field names are read from configuration at runtime, so the bytecode does not necessarily contain a direct reference to the internal API being sought.

Beyond **jdeps**, search source code and configuration for indicators:
- Imports or package names **sun.***, **com.sun.***, **jdk.internal.***.
- **Class.forName**, **getDeclaredField**, **getDeclaredMethod**, **getDeclaredConstructor**.
- **setAccessible(true)**, **trySetAccessible()**, **MethodHandles.privateLookupIn**.
- Configuration for reflection, serialization, dependency injection, mocking, ORM, or field-accessing frameworks.
- JVM arguments such as **--add-exports**, **--add-opens**, and **--illegal-access** in scripts, containers, CI, or IDE configurations.

These indicators need to be reviewed in context. Reflection is not always wrong; the issue is accessing internal members of another module without an API contract or proper open permission.

After static checks, run the application and test suite on the target JDK. Include realistic flows using reflection, serialization, native memory, logging, networking, frameworks, and plugins. If a framework catches exceptions and continues, inspect logs and output behavior, not just process exit status.

## 9. Choosing Supported Replacement APIs

The goal of migration is to preserve necessary application behavior using APIs with public contracts. There is not always a one-to-one replacement; you must identify what the code is using the internal API to accomplish.

Some examples:

| Legacy or Internal API | Replacement Direction | Notes |
|---|---|---|
| **sun.misc.BASE64Encoder / BASE64Decoder** | **java.util.Base64** | Standard API available since Java 8 |
| **sun.misc.Cleaner** | **java.lang.ref.Cleaner** | Standard API for cleanup when an object is no longer referenced; for explicitly closeable resources, prefer AutoCloseable and try-with-resources |
| Atomic/field/array operations via **sun.misc.Unsafe** | **VarHandle**, Atomic classes, or appropriate concurrent APIs | Choose according to memory ordering, atomicity, and data type actually needed |
| Native memory access via **sun.misc.Unsafe** | **Foreign Function & Memory API**, MemorySegment and Arena on JDKs supporting this API | FFM was finalized in JDK 22; check target JDK version |
| Routine byte/buffer manipulation via internal implementation | **ByteBuffer** and **java.nio** APIs | Use public APIs if specialized internal behavior is not needed |

Base64 replacement example:

~~~java
import java.util.Base64;

byte[] data = "Java modules".getBytes(java.nio.charset.StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(data);
byte[] decoded = Base64.getDecoder().decode(encoded);
~~~

The snippet uses the standard API and does not depend on **sun.misc.BASE64Encoder** or **sun.misc.BASE64Decoder**.

Example of resource cleanup using a standard API:

~~~java
try (var input = java.nio.file.Files.newInputStream(path)) {
    // Read and process data.
}
~~~

If a resource has a clear lifecycle, **try-with-resources** is generally easier to control than garbage-collection-based cleanup. **Cleaner** is suitable for certain fallback cleanup scenarios, but should not be used to replace actively closing resources.

With **sun.misc.Unsafe**, you should not replace every call with a single API. If you need variable access with memory ordering, evaluate **VarHandle**. If you need to manage native memory or call native functions, evaluate **Foreign Function & Memory API**. If you only process bytes, **ByteBuffer** may suffice. Unsafe methods are not supported APIs; many methods have been replaced by standard APIs and were deprecated for removal in JDK 23. JDK 24 onward issues runtime warnings when calling replaced memory-access methods.

## 10. Upgrading Dependencies Before Writing Workarounds

Internal APIs often appear in third-party libraries rather than directly in application code. An older framework might use reflection or internal classes to optimize serialization, manage buffers, generate proxies, or inspect JDK structures.

Priority workflow:

1. Identify the dependency and the version actually loaded at runtime.
2. Check whether the library maintainer has released a version supporting the target JDK.
3. Upgrade the library and related build/test plugins.
4. Read release notes for compatibility changes and new configuration methods.
5. Re-run tests on the target JDK.
6. If the library has no fix yet, contact the maintainer or plan to replace the dependency.

Do not update only directly declared dependencies. Maven/Gradle can pull in many transitive dependencies. Inspect the dependency tree and ensure the artifact actually executed is the upgraded version.

If you must keep an old library in the short term, use **--add-exports** or **--add-opens** only for the specific package and target module required by the error. Document the reason, the dependency owning the workaround, the version to upgrade to, and the removal criteria. An unowned workaround easily becomes a permanent dependency.

## 11. Practical Migration Workflow

You can organize migration in the following steps:

1. **Lock in the target JDK.** Record the vendor, feature release, update version, operating system, and deployment method.
2. **Run the current application on the target JDK.** Record startup errors, JVM warnings, test failures, and behavioral differences before changing code.
3. **Upgrade dependencies.** Check frameworks, drivers, plugins, build tools, test runners, and native libraries.
4. **Scan static dependencies.** Run **jdeps --jdk-internals** on the application and dependent JARs.
5. **Search for dynamic reflection.** Find reflection calls, MethodHandles, class name configurations, and JVM flags currently opening packages.
6. **Build a migration inventory.** For each API, record the functionality used, call site, owning dependency, replacement API, risks, and required tests.
7. **Replace by functional group.** Keep changes small for easy verification and rollback. Create an internal adapter if multiple places call the same functionality.
8. **Reduce workarounds.** Remove obsolete **--illegal-access** flags; keep add-exports/add-opens flags only if proven necessary and with a removal timeline.
9. **Recompile and retest.** Run unit, integration, packaging, and startup tests on the target JDK.
10. **Verify real deployment.** Confirm scripts, service managers, containers, and JVM options in production match the tested configuration.

Oracle's migration documentation recommends trying to run the application on the new JDK before recompiling, updating libraries, compiling when needed, and running jdeps. Migration is often an iterative process: fixing one error can expose another dependency in the next step.

## 12. Using --add-exports and --add-opens as Temporary Bridges

If a library cannot be upgraded yet, you can temporarily grant access for the exact package.

Example exporting public types of an internal package:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp app.jar com.example.Main
~~~

Example opening a package for deep reflection:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
~~~

In both examples:
- **java.base** is the source module.
- **sun.nio.ch** or **java.lang** is the package needing permission.
- **ALL-UNNAMED** applies to code in the unnamed module, usually an application running on the classpath.

Choose **--add-exports** for accessing public types/members; choose **--add-opens** when a framework needs deep reflection into non-public members. Runtime flags do not necessarily resolve compile errors; if source code directly references internal types, the compiler must also be configured accordingly.

Do not use **--illegal-access=permit** to replace the two options above on JDK 17+. That option is no longer effective. Also avoid adding packages wholesale to **ALL-UNNAMED** to make all errors disappear: the broader the access granted, the weaker the module boundaries and the harder they are to remove later.

## 13. Testing and Migration Completion Criteria

A single successful run is not enough to prove migration is complete. An internal API may only be called on a rare code path or by a plugin when special data is present.

You should verify:

- **Build:** compiles with the target JDK, with no remaining imports of unsupported internal APIs.
- **Static analysis:** **jdeps --jdk-internals** output is addressed; any remaining dependency has a clear justification.
- **Reflection:** test flows using serialization, ORM, DI, proxies, mocking, and reflection frameworks.
- **Runtime:** run both classpath and module path applications if the product supports both.
- **Packaging:** check scripts, Docker images, service configs, test runners, and IDE launch options.
- **Behavior:** compare output, performance, resource handling, and errors with the previous version.
- **Future JDK:** test on the next JDK release or a CI matrix matching your upgrade schedule.
- **Workaround:** each remaining add-exports/add-opens flag has an owner, package, target module, justification, and removal plan.

**jdeps does not fully detect dynamic reflection**, so completion criteria must combine static analysis and runtime testing. If jdeps output is clean but the application still throws InaccessibleObjectException, investigate reflection paths and framework dependencies.

## 14. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| javac reports internal package is not exported | Source code references a JDK internal API | Find a public replacement API; use --add-exports only as a bridge |
| IllegalAccessError at runtime | Bytecode accesses an unexported package | Check source/target modules and runtime exports |
| InaccessibleObjectException | Deep reflection into a package that is not open | Upgrade framework or open the specific package temporarily with --add-opens |
| --illegal-access=permit has no effect | Running on JDK 17 or later | Remove obsolete flag; migrate or grant specific access if truly needed |
| jdeps reports no dependency but runtime still fails reflection | Access is constructed dynamically or class names come from config | Search for reflection in source/dependencies and run representative tests |
| NoClassDefFoundError after upgrade | Internal API or class was removed/moved | Identify old dependency and replace with a supported API |
| NoSuchMethodError after upgrade | Library depends on an internal method that changed | Upgrade library or replace the integration |
| Error occurs only in container | Actual JVM options or dependencies differ from local environment | Check image, command line, classpath/module path, and deploy configuration |

Do not handle every case by adding **--add-opens**. If a class was removed, opening the package cannot recreate that class. If the error is a dependency version conflict, fix the dependency graph. If the API changed, replace the code or upgrade the library.

## 15. Self-Check

**1. Why can a public class still be inaccessible from another module?**

Because the module system also checks whether the package is exported to the target module. The `public` modifier in Java does not cross module boundaries on its own.

**2. Starting from JDK 17, does --illegal-access=permit reopen internal packages?**

No. Starting in JDK 17, this option is ignored and only emits a warning. You must migrate to supported APIs or grant specific permissions using add-exports/add-opens during the compatibility phase.

**3. Does jdeps --jdk-internals detect every reflective usage of JDK internal APIs?**

No. jdeps is static analysis and can miss dynamically constructed class/field names, reflection, or config-based lookups. You must inspect source/dependencies and run runtime tests.

**4. When should you use --add-exports and when should you use --add-opens?**

Use add-exports when code needs access to public types/members of an unexported package. Use add-opens when deep reflection into non-public members in an unopened package is required.

**5. Why is upgrading third-party libraries often a key migration step?**

Because internal APIs may be called inside frameworks or dependencies that the application does not import directly. Newer versions may already have switched to standard APIs and addressed strong encapsulation.

**6. Can sun.misc.Unsafe be considered a supported API because it is still in the JDK?**

No. Existing for compatibility does not turn its methods into supported APIs. Many methods have been replaced by VarHandle or the Foreign Function & Memory API and deprecated for removal.

## 16. Takeaways

JDK internal APIs are implementation details, not stable contracts for applications. Strong encapsulation helps the JDK evolve more safely, but exposes legacy dependencies during upgrades. Use **jdeps --jdk-internals** to find static references, inspect dynamic reflection as well, upgrade dependencies, and replace with public APIs.

**--add-exports** and **--add-opens** can help legacy applications keep running during a transition period, but they do not replace migration. Each workaround should be scoped to the exact package, have an owner, and have a removal plan.

## References

- [Oracle JDK 27 Migration Guide — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [Oracle JDK 25 Migration Guide — Preparing for Migration](https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html)
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [JEP 396: Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [JEP 498: Warn upon Use of Memory-Access Methods in sun.misc.Unsafe](https://openjdk.org/jeps/498)
