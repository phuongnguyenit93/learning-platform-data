
# Tracking and Gradually Removing Access-Opening Flags After Upgrading Dependencies

During a Java version migration, an older application may require JVM options such as `--add-opens` and `--add-exports` to start up or allow a framework to continue accessing packages that are not exposed under the rules of the Java Platform Module System (JPMS). These flags are useful as **transitional measures**, but if they are copied forward indefinitely across dependency upgrades, the system will gradually accumulate unnecessary permissions, mask outdated libraries, and make the next JDK upgrade harder to control.

This lesson focuses on **cataloging, identifying root causes, verifying, and performing controlled removal** of access-opening flags once dependencies have been upgraded. The goal is not to delete every flag at all costs: some applications or frameworks genuinely require intentionally declared access permissions. The goal is that every remaining permission must have a **technical reason, minimal scope, test evidence, an owner, and a re-evaluation plan**.

This content is set in the context of *Java Advance Compatibility Migration*, under the *Reflection and Internal APIs* section.

## 1. Why Do Access-Opening Flags Appear When Upgrading Java?

Before the module system, many libraries used reflection to invoke constructors or methods or read non-public fields. Some libraries also directly referenced internal JDK APIs. Starting in Java 9, JPMS established clearer boundaries between modules and packages; these boundaries have been enforced increasingly strictly in subsequent JDK releases.

Example of a legacy framework attempting deep reflective access into `java.lang.String`:

~~~java
import java.lang.reflect.Field;

public final class LegacyInspector {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
~~~

On newer runtimes, `setAccessible(true)` may fail with `java.lang.reflect.InaccessibleObjectException` because the `java.lang` package of the `java.base` module is not opened to the caller's module.

A common workaround is:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

This flag opens the `java.lang` package of `java.base` for **deep reflection** from unnamed modules. It does not turn private implementation access into a stable API, nor does it guarantee that the code will continue working if internal structures change.

If the framework is upgraded to a version that no longer accesses that private field, the opening flag may have become redundant. At that point, keeping the flag provides no compatibility benefit while still widening the access scope.

### 1.1. Flags Are Traces of Past Issues

A flag may have been added because:

- An older framework version attempted to access private members in the JDK.
- A library depended on a JDK internal API.
- A serialization/ORM/proxy framework needed reflection into an application package.
- A Java agent or instrumentation library did not yet support the new JDK.
- A test framework needed access to create mocks or run tests.
- A transitive dependency, plugin, or code generator triggered an error.
- Operators copied a set of JVM flags from another project without verifying them.

Not every flag present in the system is still necessary. Therefore, distinguish **historical reasons** from **current needs**.

### 1.2. Why Should You Not Remove All Flags at Once?

If multiple flags are removed simultaneously and the system fails, it is hard to tell which flag corresponds to which module, code path, or dependency. A flag might be needed only when running a batch job, an integration test, or when activating a rarely used plugin. The proper approach is to capture a baseline, test removing small groups at a time, monitor, and keep a rollback plan.

## 2. Understanding the Exact Meaning of Each Flag Type

To remove flags accurately, you must understand what permission each flag grants.

| Flag/Mechanism | Primary Meaning | Common Scenario |
|---|---|---|
| `--add-opens` | Opens a source module's package for deep reflection from the target module at runtime | Frameworks needing to read/invoke non-public members |
| `--add-exports` | Exports a package for regular access to public types in the package per module rules | Compile-time or runtime code referencing public APIs in an unexported package |
| `--add-reads` | Adds a module readability relationship | A named module needing to read another module |
| `opens ... to ...` in `module-info.java` | Source module proactively opens a specific package to a target module | Modular applications intentionally granting access to ORMs/serializers |
| `open module ...` | Opens all packages in the module for reflection | Requires caution due to broad scope |
| `--illegal-access` | Legacy compatibility mechanism on certain earlier releases | Should no longer be relied upon on JDK 17+ |

### 2.1. Syntax of --add-opens

~~~text
--add-opens <source-module>/<package>=<target-module>(,<target-module>)*
~~~

Example:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

In this example:

- `java.base` is the module containing the package.
- `java.lang` is the package being opened.
- `ALL-UNNAMED` refers to unnamed modules, typically code on the classpath.

If the consumer is a **named module**, you can specify the target module name instead of opening to all unnamed modules:

~~~bash
java --add-opens java.base/java.lang=com.example.inspector --module-path mods \
  -m com.example.inspector/com.example.inspector.Main
~~~

This is a syntax example. The `com.example.inspector` module and actual access permissions must be verified in the system. Using a specific target module narrows scope compared to `ALL-UNNAMED`, though code on the classpath cannot always be replaced by a module name.

### 2.2. Syntax of --add-exports

~~~text
--add-exports <source-module>/<package>=<target-module>(,<target-module>)*
~~~

Illustrative example:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

This flag is not equivalent to opening a package for reflecting on private members. If the error is `InaccessibleObjectException` when calling `setAccessible`, evaluate deep reflection conditions rather than defaulting to `--add-exports`.

Conversely, if the error is `IllegalAccessError` caused by accessing a class in an unexported package, merely adding `--add-opens` will not necessarily solve the normal API access issue.

### 2.3. Compile-Time and Runtime Flags Are Two Different Scopes

A dependency might compile because the compiler was given `--add-exports` yet fail on the JVM at runtime, or vice versa. Separate:

- Parameters passed to `javac`.
- JVM arguments running tests.
- JVM arguments running the application or JavaExec tasks.
- Parameters injected by containers or launchers.
- Configurations for agents and bytecode tools.

`--add-opens` primarily serves runtime reflection. Do not treat a list of flags in Gradle compiler options as evidence that the production application uses the same flags.

### 2.4. Do Not Rely on --illegal-access on Newer JDKs

During JPMS's transition period, some releases included `--illegal-access` to relax access to older JDK packages. On JDK 17, this mechanism no longer expands access as before; the old option may be ignored with a warning. The migration process must fix the root cause or use **explicit, scoped** opening permissions if truly needed.

Never conclude that “the application is safe because `--illegal-access=permit` is set” when running on a modern JDK.

## 3. Management Lifecycle of an Access-Opening Flag

A flag should be managed as a technical exception with a lifecycle:

~~~mermaid
flowchart TD
    A["Flag detected in configuration"] --> B["Record owner and reason"]
    B --> C["Identify dependency / code path needing access"]
    C --> D["Upgrade dependency or replace implementation"]
    D --> E["Test running without the flag"]
    E --> F{"Relevant tests pass?"}
    F -->|Yes| G["Remove from all relevant configurations"]
    F -->|No| H["Collect errors, narrow scope, plan fix"]
    H --> C
    G --> I["Add guardrails and monitor subsequent releases"]
~~~

Governance statuses that can be used:

| Status | Meaning |
|---|---|
| DISCOVERED | Flag found, need not yet verified |
| JUSTIFIED | Backed by runtime evidence and an assigned owner |
| CANDIDATE | Dependency upgraded; flag is likely no longer needed |
| TESTING | Testing execution without the flag across relevant environments |
| REMOVED | Flag removed and verified |
| RETAINED | Still needed; has documented reason, scope limit, and review date |
| BLOCKED | Cannot be removed immediately due to a specific reproduced issue |

Status names are only examples, not a mandatory standard. What matters is avoiding the vague status “used to be needed, so keep it.”

## 4. Creating a Baseline of All Active Flags

Before changing dependencies or removing flags, build an **inventory** that can be compared across versions and environments.

### 4.1. Do Not Search Only One Startup File

Sources that may contain JVM flags:

- `run.sh`, `start.sh`, batch files, PowerShell scripts.
- Dockerfiles, container entrypoints, or image startup configurations.
- Kubernetes Deployments/StatefulSets, Helm values, Kustomize overlays.
- CI pipelines and runner configurations.
- Gradle `Test`, `JavaExec`, `applicationDefaultJvmArgs`.
- Maven Surefire/Failsafe `argLine`.
- Application servers or service wrappers.
- Systemd service units and environment variables.
- IDE run configurations.
- Java agent installers or bootstrap scripts.
- Environment variables such as `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, or `_JAVA_OPTIONS` when supported by the runtime.
- Environment-specific configurations: development, test, staging, production, batch workers, and scheduled jobs.

Searching with ripgrep in the repository:

~~~bash
rg -n --hidden --glob '!**/.git/**' -- \
  '--add-opens|--add-exports|--add-reads|--illegal-access' .
~~~

Depending on the shell and tool version, multiple separate search patterns can be used if needed. If an environment variable is set only outside the repository, searching source code will not find it; inspect the approved deployment configuration.

### 4.2. Identifying Flags Active at Runtime

For a running JVM where diagnostics are permitted, you can inspect the command line:

~~~bash
jcmd <pid> VM.command_line
~~~

Or in Java code when appropriate:

~~~java
import java.lang.management.ManagementFactory;

public final class VmArgs {
    public static void main(String[] args) {
        for (String arg :
                ManagementFactory.getRuntimeMXBean().getInputArguments()) {
            System.out.println(arg);
        }
    }
}
~~~

Be cautious when logging all JVM arguments because they may contain secrets or sensitive data. Extract only the flags under review; avoid placing tokens, passwords, or confidential configuration details into public tickets.

Flags can enter the JVM through multiple channels, so diagnostic output must be cross-checked against the actual launcher and environment. Always record the JDK version as well:

~~~bash
java -version
~~~

### 4.3. Standardizing the Inventory Format

Sample tracking table:

| ID | Exact Flag | Environment | Historical Reason | Dependency/Call Site | Owner | Status |
|---|---|---|---|---|---|---|
| OPEN-01 | `--add-opens java.base/java.lang=ALL-UNNAMED` | Test | Legacy mock framework | Mocking adapter | Test team | CANDIDATE |
| OPEN-02 | `--add-opens java.base/java.time=ALL-UNNAMED` | Production | Serializer accessing private fields | JSON mapper | Backend team | JUSTIFIED |
| EXP-03 | `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` | Batch | Native buffer utility | Legacy buffer lib | Platform team | BLOCKED |

The rows above are **illustrative examples**, not recommendations to add those flags.

Each row should also include:

- The recorded reason when the flag was introduced.
- The JDK and dependency versions at the time it originated.
- The initial error or stack trace.
- The opened module/package.
- The specific target or `ALL-UNNAMED`.
- The processes that actually use the flag.
- The dependency version expected to eliminate the need.
- Tests covering the relevant code path.
- The last check date and next review milestone.
- A PR/ticket for change traceability.

## 5. Root-Cause Diagnosis: Who Actually Needs the Flag?

Do not decide to keep a flag based solely on a hunch that “library X used to need it.” Identify the **current consumer**.

### 5.1. Reading Exceptions by Category

Reflection error example:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

From the error, identify:

1. The source module is `java.base`.
2. The accessed package is `java.lang`.
3. The consumer is in the unnamed module or a specified named module.
4. The stack trace shows which framework/dependency invokes reflection.
5. Which code path triggers the call.

If the message is:

~~~text
java.lang.IllegalAccessError:
class ... cannot access class ... because module ...
does not export ... to ...
~~~

this is usually a **module export/access** issue, distinct from deep reflection. Find the code using the unexported API and check whether the library has an updated version using public APIs.

Other related errors:

| Error/Symptom | Question to Check |
|---|---|
| `InaccessibleObjectException` | Does the package need to be opened for deep reflection? Which caller is accessing it? |
| `IllegalAccessException` | Are reflection access checks, visibility, and module boundaries satisfied? |
| `IllegalAccessError` | Is bytecode accessing a disallowed member or package? |
| `NoClassDefFoundError` | Is a class or dependency missing, moved to a separate module, or failing to load? |
| `NoSuchMethodError` | Binary incompatibility of a dependency, not necessarily a missing `--add-opens` |
| `UnsupportedClassVersionError` | Bytecode requires a newer JVM; cannot be fixed with opens flags |
| Framework fails to scan classes | Are annotation metadata/visibility, classpath, or module openness configured properly? |

**Do not use `--add-opens` as a catch-all fix for every error after a Java upgrade.**

### 5.2. Identifying the Component from the Stack Trace

Proceed in order:

- Capture the full stack trace from a reproducible environment.
- Identify the first frame belonging to the relevant application library or framework.
- Check the dependency version actually resolved.
- Check the release notes or migration guide for the newer version.
- Inspect the classpath to avoid having two versions of the library.
- Verify whether the failing path still occurs after upgrading the dependency.

When reflection is used, the error can originate from a helper buried deep in a transitive dependency. Trace the module owning the access call, not just the outer module invoking the business method.

### 5.3. Static Dependency Analysis with jdeps

`jdeps` helps find static references to internal JDK APIs:

~~~bash
jdeps --jdk-internals --recursive path/to/library.jar
~~~

You can analyze alongside the appropriate classpath:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

Keep in mind:

- `jdeps` does not prove that an `--add-opens` flag is still needed.
- Reflection using dynamic class names or strings may not appear in static results.
- Some dependencies inside nested JARs must be extracted or analyzed separately.
- Analysis must run against the exact artifact and dependency versions.
- An internal API reference does not necessarily equate to deep reflection; distinguish `--add-exports` from `--add-opens`.

Static analysis helps identify targets to investigate; **runtime testing with the flag removed** is the direct evidence for a given code path.

## 6. Upgrade Dependencies Before Removing Flags

The most sustainable way to reduce flags is to upgrade dependencies to versions using public APIs or appropriate module mechanisms. Merely deleting a flag while keeping an old library can break a rarely used feature in production.

### 6.1. Identify Which Dependencies Are Actually Loaded

In Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency byte-buddy \
  --configuration runtimeClasspath
~~~

In Maven:

~~~bash
mvn dependency:tree
~~~

These commands are examples for learners to run on their projects; it is not mandatory to apply every command to every build.

Record:

- Direct dependencies and transitive dependencies.
- Actual resolved versions, not just declared versions.
- Dependency management, BOMs, and forced resolutions.
- Plugins or agents with their own dependency sets.
- Modules present only in testRuntimeClasspath.
- JARs loaded by custom class loaders.

### 6.2. Read Release Notes for the Target JDK

For example, a serialization or mocking framework may upgrade how it performs reflection, use method handles, or change its access strategy. However, a new version stating “supports JDK 21” does not by itself prove that all flags can be removed. The vendor may still require opening a package due to the framework's official design.

Check the documentation for:

- Minimum supported JDK and tested JDKs.
- Changes in reflection/module access.
- Requirements for agents, bytecode generation, or native integration.
- Release notes regarding elimination of illegal reflective access.
- New configurations replacing an old flag.
- Breaking changes in the serializer/ORM when upgrading a major version.

An upgraded dependency may resolve an access error while simultaneously altering JSON formatting, proxy behavior, or data. Run regression tests for the affected business logic, not just startup checks.

### 6.3. Do Not Confuse Opening Application Packages with Opening JDK Packages

There are two distinct groups:

**Group A — opening a JDK package**:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Usually stems from internal JDK access. The long-term goal is to use libraries/APIs that do not need deep reflection into JDK implementations.

**Group B — opening an application-owned package**:

~~~text
--add-opens com.example.app/com.example.domain=com.fasterxml.jackson.databind
~~~

If the application uses a named module and the serializer needs reflection into fields/constructors of domain objects, you can explicitly declare scoped `opens` in `module-info.java`:

~~~java
module com.example.app {
    requires com.fasterxml.jackson.databind;
    opens com.example.domain to com.fasterxml.jackson.databind;
}
~~~

This is a different design: the application **owns the package** and decides to open it to a specific framework. Do not try to eliminate it at all costs when it is a legitimate access mechanism, yet still prefer minimal scope and record it in the module contract.

Note: each library's module name and compatibility must be verified against the actual version. Not every library is a named module or requires identical access permissions.

## 7. Step-by-Step Process for Testing Flag Removal After Upgrading Dependencies

### Step 1: Lock the Baseline

Before making changes:

- Record the JDK vendor, version, and update level.
- Record artifact checksums and dependency versions.
- Record all currently active flags.
- Save the smoke/integration test baseline.
- Record the execution timestamp and environment.
- Identify features that may trigger reflection and agents.

A “PASS” result is unreliable if the before and after runs used two different artifacts or dependency sets without recording the difference.

### Step 2: Select a Candidate Flag

Prioritize flags with clear evidence:

- Added solely to support the dependency that was just upgraded.
- No application code directly uses the corresponding internal API.
- No stack trace with that error remains on the new version.
- Tests can exercise the relevant code path.
- The flag applies to a single low-dependency process that is easy to roll back.

If a flag is duplicated across multiple configuration sources, address **remaining occurrences in other sources**; removing a line from one startup file does not prove the runtime no longer receives the flag.

### Step 3: Remove the Flag in a Test Environment

Example before:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  --add-opens java.base/java.time=ALL-UNNAMED \
  -jar app.jar
~~~

Suppose you have verified that the new dependency no longer performs deep access into `java.time`. You can test:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

Do not simultaneously alter a second flag, dependency versions, and module configuration if the goal is to isolate the impact of a single flag.

### Step 4: Run Tests Exercising the Code Paths

Include:

- Startup and dependency injection initialization.
- Serialization/deserialization of data types with custom fields/constructors.
- ORM entity scanning and query mapping.
- Reflection into private members or annotations.
- Proxies, mocking, and bytecode generation.
- Java agent startup, instrumentation, or dynamic attach.
- Dynamically loaded plugins and service discovery.
- Scheduled jobs, batch flows, and rarely used execution paths.
- Tests inside the deployed container image and JDK.

Tests that miss a code path do not prove the flag is no longer needed.

### Step 5: Monitor Errors and Behavior

Collect exceptions, logs, JVM warnings, error rates, traces, and business metrics. Do not search only for the string `InaccessibleObjectException`; a serializer may silently skip fields and return incomplete data, or a framework may fall back to an alternative execution path that degrades performance.

Signals to watch for:

- APIs returning results with missing fields or wrong formatting.
- Beans/handlers failing to register.
- ORM mapping behavior changing.
- Test mocks/proxies failing to be created.
- Agents failing to instrument classes as expected.
- Exceptions appearing only on first-time execution.
- Newly appearing timeouts, retries, or CPU overhead.

### Step 6: Conclude According to the Tested Scope

If tests pass, do not record “the flag is definitely useless in all cases.” Record:

- The removed flag.
- The dependency/JDK versions tested.
- Which tests/code paths were executed.
- Which configurations/environments remain untested.
- Observations from staging/canary.
- The rollback mechanism.

If tests fail, keep the flag temporarily, record the error, and return to root-cause investigation. Avoid opening a batch of new packages to work around symptoms before understanding the dependency.

### Step 7: Remove Everywhere and Add Guardrails

Once sufficient evidence is gathered:

- Remove it from the primary configuration source.
- Remove duplicates in CI, staging, production, test launchers, or service wrappers.
- Verify actual startup arguments after deployment.
- Update technical documentation and the inventory.
- Add checks to prevent old flags from creeping back in.
- Monitor post-rollout according to agreed milestones.

## 8. Examples of Control in Gradle, Maven, and Deployment Environments

### 8.1. Gradle Test Task

An old test configuration:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'java.base/java.lang=ALL-UNNAMED'
    )
}
~~~

If the new test framework no longer needs this permission, remove the arguments from the `Test` task, then run the exact suite involving those mocks/reflection.

If `test` and `integrationTest` are two separate tasks, check both tasks. Removing a flag from `test` does not mean `integrationTest` is clean.

Do not replace an explicit flag by widening permissions across all JavaExec/worker tasks if only one task needs it. Flag scope should remain as narrow as possible.

### 8.2. Gradle JavaExec and Application

Example:

~~~groovy
tasks.named('run', JavaExec) {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

With the Gradle Application Plugin, you may also encounter:

~~~groovy
application {
    applicationDefaultJvmArgs = [
        '--add-opens=java.base/java.lang=ALL-UNNAMED'
    ]
}
~~~

The examples above show places that may hold flags, **not recommendations to add flags**. When removing them, inspect the startup scripts generated by the application plugin or the packaged distribution.

### 8.3. Maven Surefire and Failsafe

An older project might declare:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>--add-opens java.base/java.lang=ALL-UNNAMED</argLine>
  </configuration>
</plugin>
~~~

If the project uses Failsafe for integration tests, Failsafe's configuration may differ. Additionally, JaCoCo or other plugins may append to `argLine` in their own way. When editing, ensure you do not inadvertently drop unrelated agents or JVM flags; change only the flag proven redundant.

### 8.4. Containers and Kubernetes

Example of container startup using `JDK_JAVA_OPTIONS`:

~~~bash
export JDK_JAVA_OPTIONS="--add-opens=java.base/java.lang=ALL-UNNAMED"
java -jar app.jar
~~~

A Helm chart may supply the same flag in configuration values across multiple environments. If you delete only the line in the Dockerfile while the deployment injects the flag again, the actual runtime still opens that package.

After deploying, verify the runtime arguments of the exact pod/instance and exact JDK version rather than drawing conclusions from an unrolled-out manifest.

### 8.5. Automated Checks Once an Allowlist Exists

You can use a lightweight CI check to detect newly added flags without an owner:

~~~bash
rg -n -- '--add-opens|--add-exports' \
  deploy scripts build.gradle settings.gradle pom.xml
~~~

In practice, a useful guardrail should:

1. Scan known configuration files.
2. Compare against an approved exception list.
3. Require a ticket ID, owner, and reason for any new permission.
4. Fail when a flag appears outside the allowlist.
5. Have an approval workflow for allowlist changes.

Do not automatically block every occurrence in READMEs or test fixtures containing flag examples; keep the scan scope appropriate.

## 9. Narrowing Permissions When Full Removal Is Not Yet Possible

There are cases where an upgraded dependency still needs an opening permission. In such cases, tighten the configuration toward **least privilege** instead of leaving all legacy permissions intact.

### 9.1. Narrowing the Target Module

If a library runs as a named module and its module name has been confirmed as `com.example.framework`, consider replacing:

~~~text
--add-opens com.example.app/com.example.domain=ALL-UNNAMED
~~~

with:

~~~text
--add-opens com.example.app/com.example.domain=com.example.framework
~~~

But do so only when the framework actually runs inside that named module. If it resides on the classpath, the `ALL-UNNAMED` target may still be necessary; substituting an inaccurate module name will strip its access.

### 9.2. Moving to opens in module-info When You Own the Package

For modular application code, a directive:

~~~java
opens com.example.domain to com.example.framework;
~~~

can express intent more clearly than scattered startup flags. This does not apply to JDK packages that the application does not own.

Do not open the entire module if the framework needs only one package; avoid `open module` when the goal is restricting permissions.

### 9.3. Replacing Unnecessary Reflection with Public APIs

If the application itself uses reflection to read data from a private JDK class, consider a public API alternative, an adapter, or a different design.

For example, do not access an internal encoder/decoder simply because an old library did so; for standard Base64, Java SE has a public API:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class Encoder {
    public static String encode(String value) {
        byte[] input = value.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(input);
    }
}
~~~

Do not assume `MethodHandles.privateLookupIn` is a way to “bypass” JPMS: it still obeys module access rules and can require the package to be appropriately opened. The goal is to avoid accessing private implementations when not genuinely needed, not merely to change syntax.

### 9.4. Flags Can Be an Intentional Design Requirement

Some frameworks are designed to access domain models via reflection, and the application accepts that model. For application-owned packages, the solution may be a properly scoped module `opens`; for an agent or instrumentation tool, a special configuration may be part of its documented setup.

While removal is not yet possible:

- Keep the package and target scope as small as possible.
- Do not hide flags inside hard-to-trace environment variables.
- Document the reason, owner, and re-evaluation deadline.
- Track new dependency releases and JDK policies.
- Test that specific permission in CI.

## 10. Monitoring Security and Operational Impact

Access-opening flags reduce module encapsulation within the specified scope. They do not automatically grant operating-system privileges, but they can allow permitted code deep access into implementations or members that JPMS normally blocks.

This introduces several risks:

- **Implementation-dependency risk:** code continues relying on internal fields/methods that can change between JDKs.
- **Maintenance risk:** without documentation, it is very hard to tell which flags remain useful.
- **Scope risk:** `ALL-UNNAMED` applies to many more components on the classpath than just one library.
- **Release risk:** a flag ignored or incompatible on a Java version can alter behavior.
- **Operational risk:** flags differing between production and testing invalidate verification results.
- **Observability risk:** a framework may silently fall back when reflection fails.

Balance the risk of **keeping unnecessary flags** against the risk of **removing them prematurely**. The practical approach is evidence-based removal per permission rather than purely procedural decisions.

## 11. Staged Migration Example

Suppose an application running on Java 17 has three startup flags:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
--add-opens java.base/java.time=ALL-UNNAMED
--add-exports java.base/sun.nio.ch=ALL-UNNAMED
~~~

From initial investigation:

| ID | Initial Reason | Dependency Change | Resolution Path |
|---|---|---|---|
| A | Legacy test mocking accessed private JDK | Mocking/bytecode library upgraded | Test removing the `java.lang` flag from tests first |
| B | Legacy JSON mapper reflected into `java.time` | Mapper upgraded to use public APIs | Test removing the `java.time` flag in staging |
| C | Buffer library used internal `sun.nio.ch` | No replacement available yet | Retain temporarily; evaluate public APIs and dependencies |

**Stage 1 — Inventory:** capture JVM arguments across test, staging, and production. Record artifact checksums and dependency versions.

**Stage 2 — Upgrade dependencies:** test the exact new libraries in a test environment and run regression tests. Keep the flags initially to separate dependency-upgrade issues from permission-revocation issues.

**Stage 3 — Remove A:** drop the flag from the test task and run relevant mock/proxy tests; if they pass, record status REMOVED for tests. Verify no duplicates exist in other tasks.

**Stage 4 — Remove B:** run staging without the `java.time` flag and test serialization/deserialization across various date/time types, timezones, and legacy data formats. Monitor error rates before deploying to production.

**Stage 5 — Evaluate C:** because `--add-exports` serves a different purpose than `--add-opens`, do not blindly swap it for an opens flag. Prioritize upgrading or replacing the buffer library, or verify whether it is genuinely required via bytecode and runtime analysis.

**Stage 6 — Guardrail:** update the allowlist: A and B are removed; C remains with an owner, ticket, scope, and review milestone.

The table only illustrates a common scenario. Do not treat it as proof that a specific framework version will or will not require flags.

## 12. Detecting Flags Returning After Upgrades

Flags can reappear due to:

- Copying configurations from an old branch.
- Out-of-sync Docker images or Helm values.
- Another dependency still requiring the same permission.
- A test plugin adding flags programmatically.
- A build script generating startup scripts from an outdated template.
- An engineer adding a workaround following outdated instructions.
- A subsequent JDK upgrade introducing a new issue resolved by opening multiple packages broadly.

To prevent this:

1. Manage the inventory and allowlist in version control.
2. Require review whenever a new flag is added.
3. Document the exact reason by module/package/target.
4. Link each permission to the dependency version and relevant tests.
5. Compare actual staging and production JVM arguments against the baseline.
6. Re-evaluate exceptions whenever upgrading the JDK or dependencies.
7. Maintain a policy for removing unused flags.

A report saying “flag count dropped from 7 to 2” is helpful but insufficient. Pay attention to the **opening scope**, since a single flag with `ALL-UNNAMED` can be far broader than several flags opening packages only to specific named modules.

## 13. Common Mistakes

### 13.1. Removing Flags and Testing Only Startup

Many reflection failures surface only when serializing a special model, creating proxies, or running batch jobs. Passing startup does not prove all execution paths pass.

### 13.2. Upgrading Dependencies Without Checking Resolved Versions

A BOM or forced dependency can pull in an older version. Inspect the actual dependency graph instead of looking only at declarations in the build file.

### 13.3. Editing Flags Only in the IDE

IDE configurations differ from test tasks, containers, and production launchers. A change in one place may have no effect elsewhere.

### 13.4. Using --add-exports to Fix All Reflection Errors

`--add-exports` serves normal API access to a package; `--add-opens` serves deep reflection. Classify the error first.

### 13.5. Using --illegal-access as a Long-Term Solution

The legacy compatibility option no longer meets expectations on newer JDKs. Do not rely on it to demonstrate Java 17+ compatibility.

### 13.6. Removing Unnecessary Flags but Forgetting to Update the Allowlist

If documentation and guardrails still list the old flag, it may be added back in a future release.

### 13.7. Adding Flags from Stack Traces Without Tracing the Source

An error involving a missing method, class-file version, or serialization schema is not necessarily caused by module access. An improper workaround can mask the real issue that needs fixing.

### 13.8. Assuming Reflection on Application Packages Is Always Bad

A framework may require deep access to domain models by design. When the application owns the package, opening the package with scoped access in the module descriptor can be a valid choice. The goal is **intentional, minimal permission**, not banning all reflection.

### 13.9. Failing to Tie Test Results to Specific Artifacts and JDKs

The same flag may behave differently across JDK/agent/dependency versions. A local conclusion cannot become a production guarantee if the environment or artifact differs.

## 14. Sample Exception Record

Each flag can be documented using a concise template:

~~~yaml
id: OPEN-017
option: "--add-opens=java.base/java.lang=ALL-UNNAMED"
applies_to:
  - integration-test
source_module: java.base
package: java.lang
target: ALL-UNNAMED
reason: "Legacy test mocking library accesses JDK implementation via reflection"
owner: "Test Platform"
introduced_with: "Migration from older Java runtime"
dependency_to_upgrade: "Mocking / bytecode instrumentation stack"
evidence:
  - "Stack trace captured before dependency upgrade"
  - "Integration test suite exercising dynamic proxies"
status: TESTING
removal_criteria:
  - "Same artifact passes targeted tests without this option"
  - "Runtime arguments verified after deployment"
review_at: "Next dependency refresh"
~~~

This is sample YAML for internal management; it contains no secrets. Field names and statuses can be customized. Crucially, each exception should answer three questions: **why it is needed, who owns it, and when it can be removed**.

## 15. Checklist for Removing Access-Opening Flags

### Inventory

- [ ] Searched for `--add-opens`, `--add-exports`, `--add-reads`, and related legacy options.
- [ ] Audited build, test, CI, Docker, Kubernetes, service wrappers, and environment variables.
- [ ] Verified which flags are active on the actual JVM.
- [ ] Documented source module, package, target module, and owner.
- [ ] Distinguished JDK internal packages from application-owned packages.

### Investigation and Dependency Upgrade

- [ ] Captured stack traces, logs, or concrete evidence for the permission under review.
- [ ] Identified the dependency/module/call site requiring the permission.
- [ ] Checked the dependency graph and resolved versions.
- [ ] Read the migration guide/release notes of the upgraded dependency.
- [ ] Distinguished deep reflection from access to non-exported packages.
- [ ] Evaluated public APIs or alternative designs where needed.

### Testing Removal

- [ ] Saved the baseline artifact, JVM version, flags, and test results.
- [ ] Removed flags one at a time or in small groups for clear attribution.
- [ ] Ran tests exercising relevant reflection, serialization, ORM, proxies, agents, and plugins.
- [ ] Executed on the target JDK and deployment environment.
- [ ] Checked for runtime errors and silent behavioral changes without exceptions.
- [ ] Documented uncovered code paths and the rollout plan.
- [ ] Prepared a rollback plan in case failures occur.

### Completion

- [ ] Removed the flag from all declaration sites within the migration scope.
- [ ] Verified actual JVM arguments after deployment.
- [ ] Updated the inventory, documentation, and tickets.
- [ ] Added guardrails to prevent unapproved flags from returning.
- [ ] Retained flags have an owner, minimal scope, and a re-evaluation schedule.
- [ ] Separated flag-removal work from QA/publishing steps for training content.

## Conclusion

After upgrading dependencies, flags such as `--add-opens` and `--add-exports` must be **systematically re-evaluated**—neither kept out of habit nor removed in bulk without verification. Clearly understand which package each flag opens to which module, which dependency needs the permission, and which code paths may be affected.

A sustainable workflow consists of **inventory → root-cause tracing → upgrading dependencies → testing single-flag removal → runtime verification → removing across all configurations → protecting with guardrails**. Retained flags remain exceptions backed by evidence and an owner; removed flags are verified against specific artifacts and environments. This governance approach improves long-term compatibility, reduces reliance on internal APIs, and makes future Java migrations more predictable.
