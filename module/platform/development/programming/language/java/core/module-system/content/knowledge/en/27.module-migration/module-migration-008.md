# Removing Temporary --add-exports and --add-opens During JPMS Migration

When migrating a Java application from the traditional classpath to the Java Platform Module System (JPMS), many teams temporarily add **--add-exports** and **--add-opens** options. Those flags allow legacy code to keep working when a library needs access to an internal package or a framework needs deep reflection on non-public fields, constructors, and methods.

However, when these exceptions remain permanently in launch scripts, IDEs, build tools, or containers, actual access permissions are no longer fully described by **module-info.java**. Maintainers struggle to know which library genuinely needs an exception, may hit breakages on JDK upgrades, and sometimes grant broader access than necessary.

The goal of migration is to **replace temporary access flags with appropriate APIs, module descriptors, or library versions, and then remove each flag that is no longer needed**. Do not delete all flags en masse without knowing their original cause and verifying dependent features.

## 1. Why Do Temporary Flags Appear?

JPMS enforces boundaries that the classpath previously did not control at the module level:

- A consuming module must read the module providing data types, typically via **requires**.
- An API-providing package must be **exports**-ed to the consuming module.
- A framework needing deep reflection on a package generally needs the package **opens**-ed to the framework module.

Example domain descriptor:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Module **com.example.app** cannot arbitrarily import a public class inside **com.example.domain.internal** merely because domain is on the module path. Likewise, the JSON module is not implicitly allowed to call **setAccessible(true)** on private fields in package **com.example.domain.model**.

Runtime exceptions typically take the form:

~~~bash
--add-exports com.example.domain/com.example.domain.internal=com.example.app
--add-opens com.example.domain/com.example.domain.model=com.example.json
~~~

The first flag grants package export permission to the app module. The second flag opens the package for deep reflection from the json module.

These flags do not modify the descriptor packaged inside the JAR. When redesigning clear module boundaries, identify why each flag exists and replace it with the architecturally right solution.

## 2. Comparing Access Mechanisms

| Mechanism | Purpose | Problem solved |
| --- | --- | --- |
| requires M | Current module reads module M | Dependency between named modules |
| exports p | Exports package p to every module that can read it | Public API |
| exports p to M | Exports package p to named modules | Scoped internal API |
| opens p | Opens package p for deep reflection | Broad framework reflection |
| opens p to M | Opens package p to module M | Scoped reflection |
| --add-exports S/p=T | Adds export access at compile/runtime per tool | Compatibility for unauthorized consumers |
| --add-opens S/p=T | Adds open access at runtime | Compatibility for framework reflection |
| --add-reads S=T | Adds readability relationship | Compatibility when module readability is missing |

In the syntax **S/p=T**, S is the module owning package p; T is the module receiving access. T can be a module name or the special value **ALL-UNNAMED** in command-line options.

**--add-exports** does not make private members public. **--add-opens** does not replace exports when another module's source code needs to import public APIs. **--add-reads** does not grant access to an unexported package.

This distinction matters when choosing how to replace a flag: compile errors involving public APIs are usually not solved with opens, and deep reflection errors are not solved by exports alone.

## 3. Identifying the Real Error Before Removing Flags

Several common messages:

**Package is not visible**

~~~text
package com.example.domain.internal is not visible
(package ... is declared in module com.example.domain,
 which does not export it to module com.example.app)
~~~

This typically indicates a consumer is importing an unexported package. Check both requires and exports. If the package is internal, the best fix is usually moving to a stable public API.

**IllegalAccessError**

~~~text
java.lang.IllegalAccessError:
class ... cannot access class ... in module ...
~~~

Access errors can surface only at runtime when bytecode references an unauthorized type or member. Inspect the exact two modules involved, the package, and bytecode versions.

**InaccessibleObjectException**

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module com.example.domain does not "opens
com.example.domain.model" to module com.example.json
~~~

This signals a framework attempting deep access via reflection. Identify the framework invoking reflection, the accessed member kind, and whether you can switch to public accessors or declare scoped opens.

**ClassNotFoundException** and **NoClassDefFoundError** are typically related to classpath/module path, class loaders, or runtime dependencies. Do not assume these errors require adding --add-opens or --add-exports.

## 4. Inventorying All Sources of JVM and Compiler Arguments

Before making changes, list every flag and where it is passed. An application may have flags in:

- Maven Compiler Plugin, Surefire, Failsafe, or launch plugins.
- Gradle JavaCompile, Test, JavaExec, and application distributions.
- IDE Run/Debug configurations.
- Shell scripts, PowerShell, Dockerfiles, and container entrypoints.
- CI/CD pipelines, Kubernetes manifests, Helm values, or deployment scripts.
- **JDK_JAVA_OPTIONS**, **JAVA_TOOL_OPTIONS** environment variables, and Java agent options.
- Test frameworks, annotation processors, code generation tools, or coverage tools.

Sample inventory table:

| Flag in use | Environment | Consumer | Reason | Removal plan |
| --- | --- | --- | --- | --- |
| --add-exports ...internal=app | Build, run | com.example.app | Imports internal API | Switch to public API |
| --add-opens ...model=json | Test, run | com.example.json | Private-field reflection | Qualified opens or newer serializer |
| --add-opens java.base/...=ALL-UNNAMED | Run | Legacy framework | Reflection into JDK internals | Upgrade framework |

You can search configurations in a repository on Linux/macOS with:

~~~bash
grep -RInE -- '--add-(exports|opens|reads)' \
  pom.xml build.gradle build.gradle.kts scripts .github
~~~

Adjust paths to match your repository; not every project contains all of these files. On Windows, you can use your IDE's project-wide search or PowerShell.

Do not stop at source configurations. Inspect the actual java command constructed in runtime environments and flags injected by environment variables or launchers to avoid missing hidden exceptions.

## 5. Removing --add-exports by Moving to a Public API

Suppose the domain module has an internal class:

~~~java
package com.example.domain.internal;

public final class InternalCustomer {
    public String displayName() {
        return "Customer A";
    }
}
~~~

Domain exports only its API:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Yet the app module directly imports the internal class:

~~~java
import com.example.domain.internal.InternalCustomer;
~~~

The team previously added:

~~~bash
--add-exports com.example.domain/com.example.domain.internal=com.example.app
~~~

The long-term fix is designing a stable API type inside an exported package:

~~~java
// com.example.domain.api.CustomerView
package com.example.domain.api;

public record CustomerView(String displayName) {
}
~~~

A public service returns the API type:

~~~java
// com.example.domain.api.CustomerService
package com.example.domain.api;

public final class CustomerService {
    public CustomerView findCustomer() {
        return new CustomerView("Customer A");
    }
}
~~~

The app module updates to:

~~~java
import com.example.domain.api.CustomerService;
import com.example.domain.api.CustomerView;

CustomerView customer =
    new CustomerService().findCustomer();

System.out.println(customer.displayName());
~~~

The app descriptor only needs to read domain:

~~~java
module com.example.app {
    requires com.example.domain;
}
~~~

And domain continues exporting the API package:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Once no code imports the internal package, the add-exports flag for app can be removed. This fixes the root cause: app no longer depends on domain's implementation details.

If the domain library is an external library whose source you cannot edit, look for a version with an appropriate public API or use the official API rather than building a long-term dependency on a package marked internal.

## 6. Qualified Exports Instead of Launcher-Granted Access

Some packages are not public APIs for all consumers, but are SPIs or internal APIs meant for a known group of modules.

If you control the module descriptor, you can declare:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    exports com.example.domain.spi
        to com.example.persistence,
           com.example.reporting;
}
~~~

Now, persistence and reporting can access public types in the SPI package, provided they read domain.

Compared to:

~~~bash
--add-exports com.example.domain/com.example.domain.spi=com.example.persistence
~~~

the descriptor makes the module owner's intent explicit. That permission is stored in module-info.class and reviewed alongside source code.

Keep in mind the limits of this approach:

- Every new consumer may require updating the descriptor.
- Qualified exports still export the entire package, not an individual class.
- It does not automatically create a reads relationship from consumers to domain.
- If an SPI becomes a broadly used API, revisit package boundaries rather than lengthening the target module list.

The goal is not replacing a set of flags with an unprincipled complex descriptor, but expressing genuinely needed access where the module is owned.

## 7. Removing --add-opens When Frameworks Use Reflection

Suppose a JSON framework needs access to a model's private fields:

~~~java
package com.example.domain.model;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

The framework may attempt:

~~~java
Field field = Customer.class.getDeclaredField("name");
field.setAccessible(true);
Object value = field.get(customer);
~~~

If the model package is not open to the framework, deep reflection is blocked. The team temporarily added:

~~~bash
--add-opens com.example.domain/com.example.domain.model=com.example.json
~~~

There are two replacement paths.

**Option A — eliminate the need for private access.** If the serializer supports public constructors, public accessors, records, or custom adapters, switch to that mechanism. For example, create a public DTO:

~~~java
package com.example.domain.api;

public record CustomerDto(String name) {
}
~~~

The domain module converts internal models to CustomerDto before handing data to the framework. When the framework operates strictly on public APIs and needs no deep reflection, the model package can stay closed.

**Option B — declare qualified opens.** If reflection is a legitimate part of the design and the framework is a named module:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.json;
}
~~~

Reflection access is now recorded in module-info.java. The corresponding launcher flag can be removed once runtime tests pass.

If the framework remains on the classpath, it belongs to the unnamed module. You cannot write **opens package to ALL-UNNAMED** in module-info.java because ALL-UNNAMED is not a valid module name to declare in a descriptor. In that case, consider moving the framework to a named module with a stable name, changing how the serializer uses models, or keeping a minimal runtime flag temporarily.

## 8. Avoiding Confusion Between exports, opens, and open module

An exported package does not mean all private fields are open for reflection:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

An opened package does not mean public classes in that package become a normal API importable by other modules:

~~~java
module com.example.domain {
    opens com.example.domain.model
        to com.example.json;
}
~~~

Java also permits:

~~~java
open module com.example.domain {
    exports com.example.domain.api;
}
~~~

An open module opens all of its packages for deep reflection. It is far broader in scope than targeted opens.

During migration, prefer opening the exact package to the exact module. Only use open module if the architecture truly requires opening the entire module and the encapsulation impact is understood.

A framework failing due to missing permissions is not sufficient reason to immediately add open module without checking the packages and callers.

## 9. ALL-UNNAMED Is Not a Specific Module

Two common configurations are:

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
--add-exports com.example.domain/com.example.domain.internal=ALL-UNNAMED
~~~

**ALL-UNNAMED** refers to all unnamed modules. It is used in launcher/compiler options, not as a module name you can declare with requires or opens ... to in module-info.java.

ALL-UNNAMED has broad scope: many libraries on the classpath can receive access to the same package.

Narrowing roadmap:

1. Identify the exact classes and libraries requiring permission.
2. Check whether the current library version supports the Java module system.
3. Move consumers to named modules with stable names if feasible.
4. Use exports ... to or opens ... to when you own the source module.
5. If it cannot be replaced yet, retain the flag with a documented reason, owner, and removal condition.

Do not replace ALL-UNNAMED with a module name guessed from a JAR filename. First verify that the consumer is truly a named module with that name on the module path.

## 10. Flags Opening JDK Internal APIs

Some legacy libraries access classes in JDK internal packages or use reflection on classes in java.base. You may encounter:

~~~bash
--add-exports java.base/jdk.internal.misc=ALL-UNNAMED
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

The application does not own java.base's descriptor. Therefore, you cannot edit the platform module's module-info.java to create custom permissions.

Preferred remediation:

- Upgrade the framework or library to a version officially supporting the target JDK.
- Replace internal APIs with supported Java APIs.
- Evaluate standard APIs for reflection, method handles, serialization, and concurrency where suitable.
- Remove old dependencies providing APIs that are no longer needed.
- Test on the JDK version used in production.

You can use **jdeps** to find bytecode references to JDK internal APIs:

~~~bash
jdeps --jdk-internals path/to/legacy-library.jar
~~~

Its results do not cover every reflection access constructed dynamically from strings at runtime. Combine with integration tests, logs, and stack traces to identify the offending library.

Since JDK 17, strong encapsulation is enforced more strictly for many internal packages, and **--illegal-access** is no longer an effective relaxation option. Do not swap specific --add-opens flags for --illegal-access expecting legacy libraries to keep working.

## 11. Executing Migration in Phases

**Phase 1 — baseline.** Record the JDK version, library versions, javac/java commands, test suite, and all add-exports/add-opens flags. Run the current system as a comparison point before making changes.

**Phase 2 — classify.** For each flag, identify the source package, consumer, access kind (public API vs. deep reflection), environments needing the flag, and original stack trace. Flags lacking evidence of usage should be tested for removal individually, not deleted blindly.

**Phase 3 — fix root causes.** Refactor code to public APIs, update descriptors, upgrade frameworks, or replace serializers/adapters. Do not introduce broader new exceptions to replace older ones.

**Phase 4 — remove flags one by one.** After each change, compile and run unit tests, reflection/service tests, and integration tests. If something breaks, record the evidence and fix the root cause instead of immediately restoring all flags.

**Phase 5 — verify on a production-equivalent runtime.** Use the exact JDK, classpath/module path, artifacts, and JVM args intended for deployment. Green tests on the classpath do not prove a named-module runtime works.

**Phase 6 — update operations.** Remove flags from IDEs, CI/CD, containers, distributions, and documentation. Verify the actual command line passed to the JVM.

Migration is complete for a flag when no supported code, framework, or environment depends on that exception anymore.

## 12. Places to Update in Maven

The compiler may be configured as:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--add-exports</arg>
            <arg>com.example.domain/com.example.domain.internal=com.example.app</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Forked tests often have separate JVM arguments in Maven Surefire or Failsafe:

~~~xml
<argLine>
    --add-opens com.example.domain/com.example.domain.model=com.example.json
</argLine>
~~~

After migrating to public APIs or qualified opens, remove the corresponding flags everywhere they are no longer needed.

Note that a module POM may inherit settings from a parent POM or CI profiles. If you edit only the child POM without inspecting the effective configuration, flags may still continue to be passed.

Packaging or launcher configurations generated by other plugins must also be updated if production uses them.

## 13. Places to Update in Gradle

In Gradle Groovy DSL, compiler arguments may exist:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'com.example.domain/com.example.domain.internal=com.example.app'
    ]
}
~~~

Application run configuration:

~~~groovy
tasks.withType(JavaExec).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.domain/com.example.domain.model=com.example.json'
    )
}
~~~

Tests may also pass a different set of arguments:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.domain/com.example.domain.model=com.example.json'
    )
}
~~~

When cleaning up flags, check build.gradle, build.gradle.kts, convention plugins, buildSrc, and parent project configurations. If using an application distribution, inspect startup scripts generated after the build as well.

Do not conclude production is flag-free just because a local JavaExec task was cleaned up.

## 14. Example Running Without Exceptions

Suppose domain now has a public API and scoped opens:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.json;
}
~~~

Consumer app:

~~~java
module com.example.app {
    requires com.example.domain;
    requires com.example.json;
}
~~~

Compile the modular source tree:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.domain,com.example.json,com.example.app
~~~

Launch:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

The two temporary flags from the initial example are gone because API and reflection permissions are accurately expressed in source descriptors.

If the framework sits in an external JAR, that JAR must be placed properly and recognized with the right module name. Do not guess a module name from a filename if it is an explicit module; use **jar --describe-module**.

## 15. Verifying Actual Permissions via the Module API

You can check whether the domain module exports to the consumer:

~~~java
Module domain = CustomerService.class.getModule();
Module app = Main.class.getModule();

boolean exported =
    domain.isExported("com.example.domain.api", app);

System.out.println("API exported to app: " + exported);
~~~

Check open permissions:

~~~java
Module json = ModuleLayer.boot()
    .findModule("com.example.json")
    .orElseThrow();

boolean opened =
    domain.isOpen("com.example.domain.model", json);

System.out.println("Model open to JSON: " + opened);
~~~

If this returns true while the launcher still passes --add-opens or --add-exports, you have only confirmed runtime permission **exists**, not that the descriptor replaced the temporary flag.

Cross-check module-info.java, the descriptor inside the artifact, and the launcher with flags removed. Inspect the modular JAR:

~~~bash
jar --describe-module --file mods/com.example.domain.jar
~~~

When testing the exact configuration without exceptions, Module API checks confirm runtime boundaries match the new module graph.

## 16. Regression Testing When Removing Flags

| Check group | Goal |
| --- | --- |
| Compile-time | Consumers only import exported API packages |
| Domain unit tests | Business logic unchanged after API separation |
| Reflection tests | Framework genuinely reads/writes models where opens is needed |
| Serialization tests | Serialize and deserialize private state via supported mechanisms |
| ServiceLoader tests | Providers are still discovered in the right module/layer |
| Integration tests | Core business flows run on the module path |
| Packaging tests | Final JAR contains module-info.class and needed resources |
| Negative tests | Unauthorized modules remain blocked from internal packages |
| Production-like smoke tests | Real JDK and JVM args run without the removed flags |

Reflection tests must exercise actual deep-reflection paths, such as deserializing objects with private fields. If tests only check public getters, they may stay green even while private-field reflection fails.

A module-path test should launch with the main module:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

When multiple JDK versions must be supported, test across those versions because internal API dependencies are often sensitive to runtime upgrades.

## 17. When Immediate Removal Is Not Possible

Sometimes an exception must remain for a period:

- Upstream library lacks a release supporting JPMS/current JDK.
- Source module belongs to an external product whose descriptor cannot be edited.
- Framework lacks public accessors or suitable adapter mechanisms.
- Specialized agent/instrumentation requires access with no immediate alternative.
- Regression tests are not yet in place to prove critical execution paths.
- Removing the flag causes real regressions whose root cause is not yet fixed.

In such cases, document each flag:

~~~text
Flag: --add-opens java.base/java.lang=ALL-UNNAMED
Owner: Platform team
Consumer: legacy framework
Reason: runtime deep reflection
Replacement: upgrade to supported framework version
Validation: integration + production-like smoke test
Removal condition: tests pass without the flag
~~~

Keep the scope as narrow as possible; do not automatically consolidate multiple specific flags into one broader open configuration.

This is a tracked migration task, not proof that JPMS encapsulation can be permanently bypassed.

## 18. Common Mistakes When Cleaning Up Flags

**Removing from the IDE but forgetting CI:** runtime configurations can differ. Check every place that supplies JVM arguments.

**Editing the descriptor while using an old JAR:** source is fixed yet runtime uses a stale artifact; inspect module-info.class inside the deployed JAR.

**Using exports instead of opens:** code compiles yet frameworks still throw InaccessibleObjectException when accessing private members.

**Using opens instead of exports:** deep reflection works yet consumer source code still cannot import an unexported package.

**Removing runtime flags while forgetting compile-time flags:** the compiler might still depend on package access; fix the API/descriptor rather than keeping compiler workarounds.

**Running tests only on the classpath:** classes in the unnamed module do not fully reflect named-module access rules.

**Replacing multiple flags with open module:** eliminates errors but makes reflection boundaries overly broad.

**Missing JDK internals:** another library still uses internal APIs even after application source is fixed; check artifacts and dependency trees.

**Trying too many changes at once:** when errors appear, you cannot tell whether flags, dependencies, or the module path caused them; isolate changes per root cause.

## 19. End-of-Migration Checklist

1. Have a complete list of all add-exports/add-opens flags across build and runtime.
2. Each flag has a clear source package, target module, and justification.
3. Source code no longer imports internal packages solely via temporary flags.
4. Shared APIs are exported or qualified-exported with appropriate scope.
5. Frameworks needing deep reflection have valid qualified opens, or no longer need deep reflection.
6. Libraries using JDK internal APIs are upgraded, replaced, or have a tracked remediation plan.
7. Compiler, test runner, IDE, and production launcher have unneeded flags removed.
8. Final JARs contain the right descriptors and are not stale artifacts.
9. Unit, reflection, integration, and service tests run on the module path.
10. Critical business flows no longer throw package visibility, IllegalAccessError, or InaccessibleObjectException errors.
11. Remaining flags have an owner, removal target, and minimal permission scope.
12. Results are verified on the actual JDK and environments supported by the system.

**Removing temporary --add-exports and --add-opens is not merely deleting two command-line arguments.** It is the process of shifting access permissions from hard-to-track exceptions to public APIs, intentionally exported/opened packages, and clearly managed dependencies. Proceeding step by step and verifying the real runtime makes a modular application easier to maintain and less dependent on temporary compatibility workarounds.
