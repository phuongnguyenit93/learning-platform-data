# Strong encapsulation and the causes of `InaccessibleObjectException`

When migrating a Java application from an old JDK to a new JDK, a common error is `java.lang.reflect.InaccessibleObjectException`. The application may still compile, yet at runtime a JSON library, ORM, dependency injection, proxy, test framework, or internal reflection code attempts to access a disallowed field, constructor, or method. The error may only appear in one business flow or when the framework initializes a certain data type.

A common cause is **strong encapsulation** in the Java Platform Module System (JPMS). Previously, some code could use reflection to bypass Java access levels for JDK internal classes; on modern JDKs, module boundaries are enforced more strictly. In particular, when a package **is not opened for deep reflection**, calling `setAccessible(true)` can fail, even if the application sees that class or its package is exported.

This lesson explains the mechanism leading to the error, how to read stack traces, how to distinguish `exports` and `opens`, how to diagnose in Java migration, how to use `--add-opens` in a controlled manner, and how to design long-term solutions that do not rely on unstable internal access.

## 1. What does reflection normally do?

Reflection allows a program to inspect metadata of a class, field, method, or constructor and, under permitted conditions, execute or access that member at runtime.

Example of a simple class:

~~~java
package com.example.model;

public class Customer {
    private final String customerId;

    public Customer(String customerId) {
        this.customerId = customerId;
    }

    public String getCustomerId() {
        return customerId;
    }
}
~~~

Normal code should call the public API:

~~~java
Customer customer = new Customer("C-42");
String id = customer.getCustomerId();
~~~

However, a framework may look up the `customerId` field using reflection:

~~~java
import java.lang.reflect.Field;

Field field = Customer.class.getDeclaredField("customerId");
field.setAccessible(true);

String id = (String) field.get(customer);
~~~

`getDeclaredField` only **finds and returns metadata** of the declared field; it does not grant permission to read the private value on its own. `setAccessible(true)` requests bypassing normal Java language access checks, within the bounds of the constraints permitted by the runtime.

On a typical application classpath, many classes of the application belong to the same unnamed module, so deep reflection into the application's own classes may still work. The issue becomes clearer when reflection code touches **classes in another module**, especially internal packages in JDK modules such as `java.base`.

## 2. What is strong encapsulation in JPMS?

JPMS was introduced in Java 9. It organizes code into modules that declare dependencies and control which packages are exported for use or opened for reflection. Not only do `public`, `protected`, package-private, and `private` access levels matter; **module boundaries** also participate in determining access rights.

A module may contain:

- **Exported package:** a package declared with `exports` so other modules can use public types and public/protected members according to Java rules.
- **Opened package:** a package declared with `opens` to allow deep reflection according to JPMS rules, including requesting access to non-public members.
- **Concealed package:** a package not exported or opened to the corresponding consumer, so it cannot be used as a public API or subjected to arbitrary deep reflection.
- **Qualified export/open:** a package only exported or opened to the listed modules, not to every module.

Strong encapsulation is the enforcement of this boundary so external code does not implicitly access a module's implementation details, even via `setAccessible(true)`.

The goal is to reduce reliance on internal APIs, improve the maintainability and security of the JDK, and make access contracts between modules clearer. This is not an accidental JVM bug: many blocked cases are the direct result of the designed encapsulation policy.

## 3. `exports` is not synonymous with `opens`

Two important keywords in `module-info.java` have different scopes:

| Declaration | Normal source code access | Deep reflection on private members | When to use |
|---|---|---|---|
| `exports p;` | Allows other modules to access the public API of package `p` | Does not grant permission automatically | Publishing a Java API for consumers to compile and call |
| `opens p;` | Does not grant compile-time access equivalent to `exports` | Allows reflection at runtime according to JPMS rules | Allowing serializers/DI/ORM to read or write members via reflection |
| `exports p to m;` | Exports only to module `m` | Does not grant permission automatically | Internal API used between specified modules |
| `opens p to m;` | Does not export to all callers automatically | Opens deep reflection only to module `m` | Minimally opening to a specific framework |
| Not declared | Not exported/opened by default | Does not allow deep reflection from other modules via normal mechanisms | Keeping the package as an implementation detail |

Example application module:

~~~java
module com.example.customer {
    exports com.example.customer.api;

    // Only the serializer module is allowed to deep-reflect into the DTO.
    opens com.example.customer.dto to com.example.serializer;
}
~~~

In the example, `com.example.serializer` is a hypothetical module. With a real framework, you must use the **exact module name** of the framework on the module path; the Maven artifact name is not necessarily the module name.

Declaring `exports` does not mean public classes inside can have their private fields read via reflection. A framework that needs to access private fields of a package in another module usually needs the package to be `opens` or an equivalent runtime configuration.

### 3.1. Opening a package and opening an entire module

Besides `opens p;`, JPMS has the syntax:

~~~java
open module com.example.customer {
    requires com.example.serializer;
}
~~~

`open module` opens all packages of the module for deep reflection at runtime. This is a broad option and can lose encapsulation benefits. When possible, prefer `opens package to framework.module;` to limit access permissions.

An `open module` does not mean all packages automatically become exported APIs for compile-time. The purpose of open is reflective access, not replacing public API contracts.

## 4. When is `InaccessibleObjectException` thrown?

`java.lang.reflect.InaccessibleObjectException` is an unchecked exception, under the `RuntimeException` branch, introduced in Java 9. It typically appears when a program requests disabling reflection access checks yet the runtime cannot grant that request.

A typical case:

1. A framework or application finds a member via `getDeclaredField`, `getDeclaredMethod`, or `getDeclaredConstructor`.
2. Code calls `setAccessible(true)` or an equivalent API to gain deeper access.
3. The member resides in a package of another module that is not opened to the calling module.
4. The JVM refuses to enable accessibility suppression and throws `InaccessibleObjectException`.

The error may appear when the framework initializes a serializer, maps an entity, scans fields, creates a proxy, or processes an object for the first time. It does not necessarily appear immediately when the application starts.

Not every reflection call fails. For example, looking up and calling a public method on a public class in a package already exported to the calling module can usually work without opening the package for deep reflection. Errors primarily relate to access scope exceeding the granted permissions.

## 5. Minimal example reproducing the error on JDK 17+

The following code looks up a private field named `value` of `java.lang.String` and then attempts to disable access checks. This is only a diagnostic example; real applications should not rely on the internal structure of String.

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");

        try {
            field.setAccessible(true);
            System.out.println("Reflective access granted");
        } catch (InaccessibleObjectException exception) {
            System.err.println("Deep reflection was denied:");
            exception.printStackTrace();
        }
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac ReflectionProbe.java
java ReflectionProbe
~~~

A typical message looks like:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field private final byte[] java.lang.String.value accessible:
  module java.base does not "opens java.lang" to unnamed module @...
~~~

This is an **illustrative error format**, not a mandatory output guaranteed to be identical across every JDK. The type of field `String.value` is an implementation detail and has changed in Java's history; that itself also shows why one should not depend on private JDK fields.

The key point to read is: **module `java.base` does not open package `java.lang` to the caller belonging to the unnamed module**. Before calling `setAccessible(true)`, `getDeclaredField` may still find the field's metadata; it is the request to cross the access boundary that is denied.

### 5.1. The `trySetAccessible()` case

Since Java 9, `AccessibleObject.trySetAccessible()` provides a way to attempt enabling access and returns a `boolean`. When permission cannot be granted due to module boundaries, it usually returns `false` instead of throwing `InaccessibleObjectException` like `setAccessible(true)`.

~~~java
Field field = String.class.getDeclaredField("value");

if (!field.trySetAccessible()) {
    System.out.println("Package is not open for deep reflection");
}
~~~

Switching from `setAccessible` to `trySetAccessible` should not be viewed as a way to bypass permissions. It only allows code to check accessibility and choose a different execution path when not permitted.

## 6. How to read the stack trace to find the exact cause

Example message:

~~~text
Unable to make field private java.lang.String.value accessible:
module java.base does not "opens java.lang" to unnamed module @5e2de80c
~~~

It can be broken down into parts:

| Component | How to interpret |
|---|---|
| `field private ... String.value` | The member the framework wants to access |
| `module java.base` | The module containing the member |
| `does not "opens java.lang"` | The package is not opened for deep reflection |
| `unnamed module @...` | The caller is on the classpath, not a JPMS named module in this case |
| Stack frame near `setAccessible` | Usually indicates which framework/library directly made the request |

Another message might say:

~~~text
module com.example.model does not "opens com.example.model.dto"
to module com.example.serializer
~~~

Here the source is not the JDK: it is **the application's own module** that has not opened the DTO package to the serializer module. A sustainable solution may be updating `module-info.java` of the application module or changing the serialization strategy, rather than adding flags to open `java.base`.

### 6.1. Finding the actual caller

A stack trace can pass through multiple layers: service → mapper → reflection library → `AccessibleObject`. You need to distinguish:

- **Module owning the denied member:** usually appears in the error message.
- **Module of the code requesting access:** could be a framework, plugin, or application.
- **Dependency bringing in the reflection code:** identified from the stack trace, dependency graph, or class loading.
- **Business path triggering the error:** a specific batch job, endpoint, startup scanner, or test.

You should not look only at the first class in the stack trace and mistakenly modify the application's API. Accurately identifying the **member source** and the **module needing access** determines the fix direction.

## 7. Distinguishing from `IllegalAccessException`, `IllegalAccessError`, and other errors

Many access errors have similar names yet occur in different mechanisms:

| Symptom | Typical context | Investigation direction |
|---|---|---|
| `InaccessibleObjectException` | `setAccessible(true)` attempts to bypass access checks yet the module does not open the package | Check `opens`, `--add-opens`, the member, and the framework |
| `IllegalAccessException` | Reflection `Field.get`, `Method.invoke`, or similar lacks required access rights | Check member visibility and accessible state |
| `IllegalAccessError` | JVM linkage/access check at bytecode encounters invalid access, such as an unexported package to the caller | Check classpath/module path and `exports` |
| `NoSuchFieldException` | Reflection searches for a field that does not exist with the specified name | Check the member name and JDK/library differences |
| `NoSuchMethodException` | Reflection cannot find a method/constructor matching the parameter types | Check signature, overloads, and version |
| `NoClassDefFoundError` | A referenced class cannot be loaded/defined properly at runtime | Check dependencies, Java version, and class loading |

`IllegalAccessException` is a checked exception; `InaccessibleObjectException` is an unchecked exception. A `catch (ReflectiveOperationException e)` block does not catch `InaccessibleObjectException` because this exception does not belong to that hierarchy.

Do not treat every access error as “just needing --add-opens”. If calling an API via normal bytecode in an unexported package, inspect `--add-exports` or public API design. If the member does not exist, opening the package does not create that member.

## 8. Evolution from Java 9 to Java 17 and beyond

When finding migration causes, you need to know that strong encapsulation did not appear suddenly in a patch release:

### 8.1. Before Java 9

Applications could use reflection with many JDK components under the access rules at that time. Some libraries became accustomed to reading private fields or calling internal methods. Places relying on implementation details still carried risk, even though they ran previously.

### 8.2. Java 9: JPMS and the transition period

Java 9 added module boundaries. To reduce ecosystem impact, certain JDK packages that existed since JDK 8 were permitted reflective access under **relaxed strong encapsulation** mode for code from the classpath/unnamed module. The runtime could emit an “illegal reflective access” warning.

That did not mean every internal package was opened, or that every named module had the same permissions. Many new or encapsulated packages could be denied immediately.

### 8.3. Java 16: switching to strong encapsulation by default

JEP 396 made strong encapsulation the default in Java 16 for most JDK internal APIs, with a limited transition mechanism via certain options during that period. Applications that previously only received warnings on older JDKs could start failing.

### 8.4. Java 17: no more legacy global relaxation mechanism

JEP 403 continued strongly encapsulating JDK internals, removing the ability to use `--illegal-access` to restore broad opening as in the previous phase. This option became obsolete and must not be used as a migration solution on JDK 17 and above.

Scoped options such as `--add-opens` can still be used in permitted cases to open **a specific package to a specific target**. This is a transitional measure, not a guarantee that private APIs will remain stable.

### 8.5. Exceptions for certain critical internal APIs

Certain APIs such as `sun.misc.Unsafe` are maintained via the `jdk.unsupported` module in many modern JDKs to support library compatibility. However, an API's existence in a special module does not make it a stably supported Java SE API. You must consult the specific documentation and policies of the target version.

## 9. How do the classpath, module path, and calling module differ?

An application may not have `module-info.java` yet still be affected by JDK module boundaries. Code on the **classpath** usually belongs to the **unnamed module**, and when wanting to deep-reflect into a package in `java.base`, that package still has to be opened to the unnamed module.

With the **module path**, code may reside in a named module with its own name. Then the error message specifies the calling module and may require opening to that module name, not `ALL-UNNAMED`.

Example of an application running on the classpath:

~~~bash
java -cp "app.jar:lib/*" com.example.Main
~~~

Denying deep reflection into `java.base/java.lang` may state `to unnamed module`.

Example of a named module:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

When module `com.example.app` requests deep reflection into an unopened package, the message may state `to module com.example.app`.

For a library that automatically becomes an **automatic module** when placed on the module path, the module name can be determined from metadata or the JAR filename. Do not guess the module name from Maven coordinates: you can view the artifact description with:

~~~bash
jar --describe-module --file dependency.jar
~~~

The module name is required information when using qualified `opens` or `--add-opens` with a specific target.

## 10. `--add-opens`: temporary configuration for verification

When deep reflection is truly needed, the Java launcher has the option:

~~~text
--add-opens=<source-module>/<package>=<target-module>
~~~

It asks the runtime to open the specified package of the source module to the target module, beyond what is declared in the module descriptor. When the target is code on the classpath, the `ALL-UNNAMED` token can be used.

Example with ReflectionProbe:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED ReflectionProbe
~~~

At that point, `setAccessible(true)` on a field in the opened package can succeed. **This only allows testing access; it does not turn a private field of String into a stable API.** Internal structure can still change between JDKs.

When the caller is a named module, use the module name:

~~~bash
java --add-opens=java.base/java.lang=com.example.app \
  --module-path mods \
  --module com.example.app/com.example.Main
~~~

This is a syntax example. Specify the actual target appearing in the error message. Do not copy `com.example.app` or `ALL-UNNAMED` verbatim if the actual application has a different module structure.

### 10.1. Difference between `--add-opens` and `--add-exports`

| Option | Goal | Does it solve private reflection? |
|---|---|---|
| `--add-opens=module/package=target` | Opens the package for deep reflection at runtime | Possible, within the exact opened scope |
| `--add-exports=module/package=target` | Allows the target to access public types/members of an unexported package via the module mechanism | Does not grant private member access automatically |

For example, when an application calls a public class in an unexported JDK package directly via bytecode, `--add-exports` may be relevant to the compile/runtime process when necessary. However, if reflection uses `setAccessible(true)` on a private field, `--add-exports` alone usually does not solve the problem.

Similarly, `--add-opens` does not mean the compiler will allow importing every class in an internal package: its goal is **runtime reflective access**.

### 10.2. Why should flags not be added indiscriminately?

Each `--add-opens` flag expands configured access while creating an additional coupling to the JDK module structure:

- The package or member may be renamed or removed in a later JDK.
- The measure only handles one access permission; other errors may still arise.
- The flag must be maintained across tests, batch jobs, workers, services, containers, and production.
- The module/target name may change when a library moves from the classpath to the module path.
- It can mask the need to upgrade a dependency or fix an API.
- Expanding access to implementation details can increase the surface area for security and maintenance risks.

Treat `--add-opens` as a **migration bridge** with an owner, reason, scope, and review deadline, not as a default choice.

## 11. Configuration in Gradle, tests, and deployment environments

When the error only occurs in unit/integration tests, the VM argument must be passed to the JVM **running the tests**, not only added to compiler arguments.

Gradle Kotlin DSL example:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

If running the application via `JavaExec`, that task may need separate configuration:

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

The two examples above are only for situations needing to open this exact package. For real projects, take the source module/package and target from the stack trace; do not add `java.base/java.lang` out of habit.

Several key points:

- `JavaCompile`, Gradle daemon, test workers, and the JVM running the application can be separate processes.
- `--add-opens` needs to take effect on **the JVM where the error occurs**.
- If a framework runs inside a container or application server, local test configuration does not automatically carry over to deployment.
- If there are multiple services or multiple entry points, every launch configuration must be checked.
- Do not put flags into an artifact JAR and assume every Java launcher will apply them.
- If the project uses the module path, the flag's target may be a named module instead of `ALL-UNNAMED`.

### 11.1. Configuration in containers

Example starting an application via Docker entrypoint:

~~~dockerfile
ENTRYPOINT [
  "java",
  "--add-opens=java.base/java.lang=ALL-UNNAMED",
  "-jar",
  "/app/app.jar"
]
~~~

This is an illustration of a workaround; it should not be used universally for every application. In actual deployment, you need to track the JDK image, VM arguments, framework versions, and the plan to remove the flag after upgrading dependencies or fixing the design.

### 11.2. Why does it work locally yet fail in production?

Environments can differ:

- Local uses JDK 11 with transition mechanisms; production uses JDK 17.
- Tests run on the classpath, production runs on the module path.
- Tests have the JVM argument, the production service launcher lacks it.
- Artifacts/shaded JARs differ in framework dependencies.
- Reflection is only triggered for a certain DTO type or plugin present in production.
- The container uses a JDK distribution or image different from the tested baseline.

Therefore, before concluding the cause is a “Java 17 bug”, save the actual Java version, JVM command line, dependency list, module path, and full stack trace of the failing process.

## 12. Replacing workarounds with more stable options

The long-term solution is usually **not accessing private JDK APIs** or **intentionally opening the application's own packages to the necessary framework**.

### 12.1. Using public APIs instead of private JDK fields

If code is reading `String.value` to get the internal bytes of a String, use the public API and choose an explicit encoding:

~~~java
import java.nio.charset.StandardCharsets;

String text = "xin chào";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

`getBytes` has public semantics and is more stable than relying on private field layout. This replacement may create a copy of the data, yet avoids coupling to internal structure and should be evaluated based on actual performance.

Similarly, prefer `java.nio`, `java.time`, `java.util`, `java.lang.invoke`, or other supported APIs when they meet the need, rather than using `sun.*` or `jdk.internal.*` packages.

### 12.2. Turning deep reflection into an explicit API

A framework or library can be configured to use:

- Public constructors with clear parameters.
- Public getters/setters or controlled package-level adapters.
- DTOs/records appropriate to the Java baseline and the framework's public API.
- Purposeful annotations or metadata instead of scanning every private field.
- Official plugin/extension points instead of accessing implementation classes.

When removing deep reflection, verify old semantics, such as whether private fields without setters, final fields, inheritance, proxies, and historical data are still supported.

### 12.3. Opening application module packages according to the minimal principle

If an application actively uses a framework that needs reflection into its DTOs, it can declare in `module-info.java`:

~~~java
module com.example.customer {
    requires com.example.serializer;

    exports com.example.customer.api;
    opens com.example.customer.dto to com.example.serializer;
}
~~~

This is a decision to support a specific framework rather than opening JDK internals. If the serializer changes its module name or uses reflection from another module, adjust to the exact observed target.

If the application is still on the classpath without module-info, using `opens` in a module descriptor is not an immediately applicable step yet. In that case, you can revise the serialization/DI strategy, upgrade the framework, or prepare modularization under a separate plan.

### 12.4. Do not confuse MethodHandles with a way to bypass JPMS

`MethodHandles.Lookup`, `MethodHandles.privateLookupIn`, and `VarHandle` are supported Java APIs for many dynamic use cases. However, they **do not implicitly bypass module boundaries**. For example, `privateLookupIn` for a class in another module still requires appropriate access permission conditions, including package openness where applicable.

Switching from reflection to method handles merely to avoid an `InaccessibleObjectException` without changing access rights or API design usually does not solve the root cause.

### 12.5. Upgrading dependencies using internal reflection

When the error originates from a third-party library, appropriate steps usually are:

1. Identify the actual dependency and version in the stack trace/dependency graph.
2. Check whether a newer library version claims support for the target JDK.
3. Read migration guides or issues related to strong encapsulation.
4. Upgrade or replace the library when a version using public APIs is available.
5. Re-run tests on the target JDK, framework, and dependency graph.
6. Keep `--add-opens` only if no viable alternative exists and risks are managed.

Do not rush to override the module configuration of the entire application when the actual cause is an old framework version that already has a supported fix.

## 13. Inventorying internal APIs and reflection paths

`jdeps` is a tool provided by the JDK to analyze static dependencies. The `--jdk-internals` option helps find bytecode references to JDK internal APIs recognized by the tool:

~~~bash
jdeps --jdk-internals app.jar
~~~

With dependencies on the classpath:

~~~bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" \
  app.jar
~~~

The command can help locate library classes using JDK internal APIs. However, **jdeps does not fully detect dynamic reflection by string name** or classes loaded later. For example:

~~~java
Class<?> type = Class.forName("java.lang.String");
Field valueField = type.getDeclaredField("value");
valueField.setAccessible(true);
~~~

The class/field names are in strings and the access path happens at runtime. One cannot conclude there is no risk just because `jdeps` found no corresponding static references.

You need to combine:

| Technique | Role |
|---|---|
| `InaccessibleObjectException` stack trace | States the source module/package and target of the denied request |
| Dependency graph | Identifies the library/framework version performing reflection |
| `jdeps --jdk-internals` | Finds static references to internal APIs recognized by the tool |
| Source search | Searches for `setAccessible`, `trySetAccessible`, `Class.forName`, and internal package names |
| Testing on the target JDK | Exercises the actual code path containing reflection |
| Module metadata | Inspects exports, opens, module names, and module path |
| Runtime logs | Records JVM args, class loading, and errors when running in a representative environment |

Note: source search may not detect code residing in dependency JARs; binary scanning and dependency inventory are still necessary.

## 14. Process for handling a real incident

You can follow this sequence to avoid adding JVM flags arbitrarily.

### Step 1: Collect the full error message

Preserve verbatim the stack trace, `Caused by` section, and the line containing `does not "opens"`. Record the source module/package, caller module, and blocked member.

### Step 2: Identify the event and environment

Record the request, job, startup action, or test that triggered the error. Confirm the JDK version, vendor/build, Java launcher, OS, classpath/module path, and JVM args.

### Step 3: Find the code or library requesting deep reflection

Read the stack trace to find the class near the `setAccessible` call. Identify the responsible dependency, version, and component. If it is project code, check whether it can be replaced with a public API.

### Step 4: Classify the accessed package

Determine whether the package belongs to:

- JDK internals or JDK implementation details;
- An application module owned by the team;
- An external library/framework;
- An exported but unopened package;
- A completely concealed package.

Accurate classification helps choose the solution. Opening an application package to a serializer differs from accessing a private field of `java.lang.String`.

### Step 5: Choose a root-cause fix

Prioritize fixing code, APIs, dependencies, or module descriptors. If the package belongs to an application module, qualified `opens` can be used. If it is a private JDK internal, look for a replacement public API or a newer library version.

### Step 6: Use a narrow workaround if truly needed

Only when a root fix is not yet possible, use `--add-opens=source.module/package=target.module` directly from the error. Document why it is needed, who owns it, applicable environments, and when to review removing it.

### Step 7: Verify with runtime tests

Re-run the same operational flow on the target JDK. Evaluate startup, data processing paths, serialization, proxies, integration tests, and error paths. If a flag was only added for tests, it must be replicated in the actual deployment environment.

### Step 8: Save migration evidence

Save the JVM command line, JDK version, prior error logs, subsequent results, dependency versions, test reports, test scope, and unhandled exceptions. When errors reappear on a newer JDK, this record helps distinguish regressions from legacy dependencies.

## 15. JSON framework investigation example

Suppose an application has a DTO in a named module:

~~~java
package com.example.customer.dto;

public final class CustomerDto {
    private String id;

    public CustomerDto() {}

    public String getId() {
        return id;
    }
}
~~~

A mapper framework may use reflection to read/write the private field `id`. If the DTO package is not opened to the mapper's module, deserialization may fail with `InaccessibleObjectException`.

There are three directions:

**Direction A — use public APIs:** configure the mapper to call public constructors/getters/setters or public mechanisms supported by the framework, depending on the version and DTO style.

**Direction B — open the package in a controlled manner:** use `opens com.example.customer.dto to com.example.mapper;` in the application's module descriptor when that is the module actually requiring reflective access.

**Direction C — update the framework or DTO strategy:** if an old framework attempts unnecessary reflective access, upgrade to a JDK/JPMS-compatible version, or switch to a DTO style that the framework handles via public APIs.

Opening `java.base/java.lang` does not solve the issue of `com.example.customer.dto` not being opened. You must read **the exact package in the exception**, avoiding guessing flags from Internet examples.

## 16. Cases where Gradle/Maven/test frameworks use JDK internals

When upgrading Java, a build plugin or test framework may run on a different JDK than the JDK running the application. Strong encapsulation errors can arise in:

- The Gradle daemon or Maven process;
- The test worker JVM;
- Annotation processors or code generators;
- Java agents/instrumentation;
- Application runtime or container;
- IDE plugins running on their own JDK.

If the error comes from the daemon/build tool, JVM arguments added to a test task will have no effect on the daemon. Conversely, flags given to the daemon are not guaranteed to be passed to a forked test JVM.

Before fixing, identify **the JVM process where the error occurs** using logs and build tools. Then prioritize upgrading build tool/plugin versions compatible with the target JDK. Use package-opening flags only when needed for a managed transition period.

An `InaccessibleObjectException` caused by an old test library does not mean the application's Java business logic is wrong. However, it is still a migration barrier that needs to be resolved in the toolchain.

## 17. Security and stability risks when opening permissions broadly

Strong encapsulation is not an absolute secrecy protection mechanism between all code in the same process; a Java system still needs a comprehensive security model at the operational permissions, dependency, and data levels. However, opening packages with broad flags creates additional internal access capability for targeted components.

Therefore:

- Only open **necessary packages**, do not open lists of JDK packages copied unverified.
- Restrict targets to specific **named modules** if possible, instead of `ALL-UNNAMED` for all classpath components.
- Do not use opened access permissions as a new API for business logic.
- Review untrusted dependencies/agents before deeply opening sensitive packages.
- Monitor errors after JDK upgrades; internal structures can change even when flags are still accepted.
- Assign an owner and removal conditions for workarounds, avoiding accumulating configurations that are no longer needed.

The most important impact on migration is **maintainability**: applications relying on private JDK fields/methods bear risk when the JDK changes implementations.

## 18. Common misconceptions

**“The class is public so reflection on private fields always works.”** A public class can be used via its public API, yet that does not mean the package is open for deep reflection.

**“`exports` and `opens` are the same.”** `exports` supports public API accessibility; `opens` serves deep reflection. Choosing the wrong mechanism will not fix the error properly.

**“Applications without `module-info.java` are not affected by JPMS.”** Code on the classpath belongs to the unnamed module and is still restricted by JDK module boundaries when accessing internals.

**“Adding `--add-exports` will fix every `InaccessibleObjectException`.”** For private reflection, the issue is usually a missing `opens`. `--add-exports` does not open private members automatically.

**“`--add-opens` completely solves the migration.”** A flag can open permissions in one environment, yet does not guarantee private members still exist or keep the same type/behavior in the next JDK.

**“Switching to MethodHandles will bypass module restrictions.”** Method handle APIs also respect module access conditions and are not a universal backdoor.

**“For JDK 17, you just need to enable `--illegal-access=permit` like on older JDKs.”** This global relaxation mechanism no longer works to restore access as it did during the transition period before JDK 17.

**“`jdeps` seeing no internal APIs means there is definitely no unauthorized reflection.”** Reflection from string names, JNI, dynamic proxies, or dynamically loaded classes can lie outside static analysis scope.

**“Opening `java.lang` solves every serializer error.”** You must identify the actual source module/package from the message; the error might lie in a separate DTO module.

**“Only testing startup is enough.”** Reflection may be executed for the first time when a request, batch job, serializer, or plugin runs; testing must trigger the exact error path.

## 19. Checklist when upgrading Java with reflection

- [ ] Identified the current JDK, target JDK, distribution, OS, and the JVM process causing the error.
- [ ] Saved the full stack trace, including the source module/package and target module.
- [ ] Identified which framework/dependency or project code is calling `setAccessible`.
- [ ] Distinguished access via `exports` from deep reflection via `opens`.
- [ ] Determined whether the caller is in the unnamed module or a named module.
- [ ] Checked replacement public APIs or framework versions supporting the new JDK.
- [ ] If the package belongs to an application module, considered qualified `opens`.
- [ ] If using `--add-opens` temporarily, restricted source/target and documented an owner.
- [ ] Confirmed the flag is applied to the exact JVM causing the error, including tests and production if needed.
- [ ] Tested runtime code paths triggering serialization, ORM, proxies, plugins, or reflection.
- [ ] Combined static analysis, dependency inventory, and integration tests.
- [ ] Saved before/after evidence, remaining warnings, and the plan to remove workarounds.

## Conclusion

`InaccessibleObjectException` usually occurs because code attempts to perform **deep reflection across an unopened module boundary**. Strong encapsulation in JPMS, enforced more strictly across modern Java versions, prevents using `setAccessible(true)` to arbitrarily access JDK internal members or members belonging to another module's packages. To handle it properly, you must clearly read the source module, package, target module, member, and involved framework; distinguish `exports` from `opens`; and test the code path causing the error in actual runtime.

`--add-opens` can help transition within a narrow scope, yet the sustainable solution is using public APIs, updating dependencies/frameworks, or intentionally declaring openness for packages under your own management. Combining static analysis with testing on the target JDK and saving migration evidence helps systems move forward to a new JDK without creating additional long-term dependencies on implementation details.
