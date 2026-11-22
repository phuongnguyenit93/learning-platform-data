# Cleaning Up Dependencies, Access Flags, and Transitional Code After the Transition Phase

Upgrading a Java application from an older JDK to a new JDK often requires temporary workarounds: adding API JARs to replace components previously bundled with the JDK, keeping legacy libraries, opening packages with --add-opens, adding --add-exports, writing adapters for two schemas, or using feature flags to run implementations side by side. Those measures help transition in phases, yet can become **compatibility debt** if left behind after they are no longer needed.

A service running stably on Java 21 can still carry Java 8 backports, unsupported libraries, overly broad module access flags, and two processing paths that are no longer tested equally. This increases security risk, dependency conflicts, makes failures harder to reproduce, and creates friction for the next JDK upgrade.

This lesson belongs to **Java Advance Compatibility Migration**, chapter **Release and Operations**, focusing on **cleaning up dependencies, access flags, and transitional code after the transition phase**. The goal is to remove unnecessary components **based on evidence**, while still protecting APIs/SPIs, historical data, consumer contracts, and rollback capability within the committed window.

## 1. Cleanup Differs from Merely Running Successfully on the New JDK

A project can reach a state like:

~~~text
Build JDK: Java 21
Production JVM: Java 21
Unit tests: PASS
Integration tests: PASS

Still remaining:
  old JAXB provider
  old bytecode manipulation tool
  --add-opens=java.base/java.lang=ALL-UNNAMED
  --add-exports=java.base/sun.nio.ch=ALL-UNNAMED
  LegacySerializer.java
  ReflectionFallback.java
  USE_NEW_SERIALIZER feature flag
  outdated GC logging script
~~~

Running on the new JDK only confirms part of compatibility. Post-migration cleanup also needs to answer:

- Which components are still actually invoked?
- Which components existed only for the transition?
- Are there runtime paths using reflection or ServiceLoader?
- Which library are the access-opening flags serving?
- Is legacy code still needed to read old data?
- Do public consumers still depend on the old binary interface?
- Has the rollback window closed yet?
- Do CI, containers, and runbooks still hold old configurations?

**Do not delete everything named Legacy without knowing its contract, nor keep everything merely out of fear of breaking production.**

### 1.1. Observable Benefits of Cleanup

| Aspect | Before Cleanup | Desired Post-Cleanup |
|---|---|---|
| Dependency graph | Old and new libraries overlapping | Only necessary and supported artifacts |
| Module access | Broad package-opening flags | Minimal permissions with justification |
| Source code | Two or more processing paths | Clear primary implementation |
| Build | Temporary configs and version overrides | Deterministic and reproducible configuration |
| Security | Libraries with CVEs/excess permissions | Reduced risk surface |
| Release | Unclear rollback conditions | Versioned artifacts and rollback window |
| Operations | Scattered flags | Managed effective runtime config |
| Observability | Old parsers and alerts | Monitoring compatible with the new JDK |

Cleanup does not mean minimizing lines of code at all costs. A compatibility reader is still required if historical data must be supported for years.

## 2. Classify Before Deleting

Each component should be labeled:

1. **Temporary workaround:** added to bypass a blocker with a concrete removal condition.
2. **Required runtime dependency:** used via import, reflection, provider, or native loading.
3. **Public compatibility contract:** serves still-supported consumers/plugins.
4. **Historical-data compatibility:** used to read old schemas and files.
5. **Permanent architectural adapter:** an intentional boundary, not leftover code.
6. **Dead code/dependency:** confirmed no longer used or committed to.
7. **Security exception:** temporarily approved JVM permission or relaxed policy.

### 2.1. Example of Justifiably Keeping an Adapter

A Java library commits to running on Java 17 and 21. An adapter that only selects public APIs available at runtime may still be needed, even if internal applications already run Java 21.

### 2.2. Example of a Workaround That Can Be Removed

An old mock library required --add-opens to java.lang. After upgrading the library to a version supporting the target JDK, there is no longer a reason to open the package if all test/runtime paths run fine without the flag.

## 3. Lifecycle of a Responsible Workaround

~~~text
Migration blocker
        |
        v
Introduce temporary workaround
        |
        v
Record reason, scope, owner, removal condition
        |
        v
Upgrade framework/dependency or migrate consumer
        |
        v
Evidence workaround is no longer used
        |
        v
Remove in controlled branch
        |
        v
Build + contract + integration + runtime tests
        |
        +-- failure --> investigate, retain with owner
        |
        v
Canary and operational verification
        |
        v
Close migration debt record
~~~

Maintain a dedicated registry or issue for each workaround.

| ID | Type | Scope | Reason | Removal Condition |
|---|---|---|---|---|
| MIG-101 | --add-opens | Test JVM | Legacy mock framework | Upgrade tool and tests pass without flag |
| MIG-102 | Legacy JAXB | Batch | Read old XML documents | Reader migrated or retention expired |
| MIG-103 | Serializer switch | API service | V1/V2 rollout | Consumers migrated and rollback window closed |
| MIG-104 | Reflection fallback | App runtime | Uses JDK internal API | Public replacement available |
| MIG-105 | Native agent | Production JVM | Agent did not support new JDK yet | Upgrade to vendor-supported release |

Even without a removal date yet, there must still be an owner and a review date.

## 4. Dependencies Can Hide in Many Places

A dependency is not just a Java import statement. It can reside in:

- Maven POM, parent POM, BOM, profiles.
- Gradle configurations, version catalogs, platforms.
- Transitive dependency graph.
- Maven/Gradle plugins.
- Annotation processors.
- Test-only or runtime-only classpath.
- ServiceLoader and META-INF/services.
- Framework auto-configuration.
- Reflection strings, plugin registration.
- Java agents or JVMTI agents.
- JNI/JNA native binaries.
- Container OS packages.
- JARs manually COPY'd into the image.
- Shaded/fat JARs or WAR libraries.
- Generated sources and toolchains.

Therefore, asking “does the IDE import classes from this JAR?” is only the first step.

### 4.1. Classification by Role

| Group | Example | Risk When Removing |
|---|---|---|
| Legacy API | javax EE, JAXB/JAX-WS | Old code/plugins lose types |
| New API | Jakarta API | Missing implementation/provider |
| Backport | API for older JDKs | Lower-baseline consumers still need it |
| Bytecode library | ASM/Byte Buddy | Agents/mocks/proxies fail to generate classes |
| Logging bridge | SLF4J/JUL/Log4j bridge | Lost logs or bridge loops |
| Native library | JNI/JNA codec | UnsatisfiedLinkError |
| Test dependency | Mocking/coverage | Tests fail to run, missing agent |
| JDBC driver | Service provider | Runtime cannot connect to database |
| Annotation processor | Code generation | Generated sources disappear |

## 5. Investigating Dependencies with Maven

~~~bash
./mvnw dependency:tree
~~~

When the project is multi-module:

~~~bash
./mvnw -pl service-app dependency:tree
~~~

An example filtering for an artifact:

~~~bash
./mvnw dependency:tree -Dincludes=org.example:legacy-adapter
~~~

Module and artifact names are illustrative only; adjust per project.

### 5.1. Direct and Transitive

~~~text
service-app
   |
   +-- framework-starter
   |      |
   |      +-- legacy-provider
   |
   +-- legacy-provider (direct)
~~~

Removing the direct dependency does not guarantee eliminating the library from runtime because the starter still pulls it in.

### 5.2. Exclusion May Be Needed, Yet Must Be Tested

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>framework-starter</artifactId>
    <version>1.2.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>legacy-provider</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

If the framework needs legacy-provider via reflection, an exclusion can yield a green build yet fail at runtime. You must know the dependency path and provider role.

### 5.3. Effective Configuration

~~~bash
./mvnw help:effective-pom
./mvnw help:active-profiles
~~~

Parent POM, dependencyManagement, pluginManagement, and profiles can retain versions or options thought to have been removed in the module.

## 6. Investigating Dependencies with Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight \
  --dependency legacy-adapter \
  --configuration runtimeClasspath
~~~

Some configurations:

| Configuration | Meaning |
|---|---|
| api | Dependency exposed through the API |
| implementation | Implementation dependency |
| compileOnly | Used only at compile time |
| runtimeOnly | Needed at runtime, usually not directly imported |
| testImplementation | Compile/run tests |
| testRuntimeOnly | Provider present only on the test runtime |
| annotationProcessor | Source generator |

Do not remove runtimeOnly just because source does not import it directly. A JDBC driver or provider may be discovered by ServiceLoader at runtime.

### 6.1. Version Catalogs Do Not Belong to a Single Module

Removing a module usage does not mean a version catalog entry is unused, because other modules may still use it. Check the entire repository within the scope assigned to the cleanup process.

### 6.2. Buildscript and Plugin Classpath

A library may serve only a build plugin or annotation processing, not appearing in runtimeClasspath. When cleaning up build tooling, inspect the right configuration.

## 7. Analyzing Dependencies via Source Code and JDK Tools

Some reference commands:

~~~bash
jdeps --jdk-internals target/app.jar
jdeprscan --release 17 target/app.jar
~~~

jdeps helps detect certain references to JDK internal APIs; jdeprscan helps identify deprecated APIs within the tool's supported scope.

These tools do not prove all runtime dependencies have been found because they do not necessarily detect:

- Reflection strings.
- ServiceLoader providers.
- Generated class names.
- Code loading plugins from configuration.
- Native libraries.
- Resource-driven class loading.
- Code present only in a specific deployment.

When necessary, analyze JARs beyond app.jar and supply the appropriate classpath.

### 7.1. Deprecated Differs from Removed

Deprecated is a design warning; deprecated for removal indicates the API may be removed; removed means the API no longer exists in that version. A deprecated public API may still be protected by the support policy and is not automatically allowed to be deleted.

## 8. ServiceLoader and Runtime-Only Code

Example:

~~~java
import java.util.ServiceLoader;

public final class DriverInventory {
    public static void main(String[] args) {
        for (java.sql.Driver driver
                : ServiceLoader.load(java.sql.Driver.class)) {
            System.out.println(driver.getClass().getName());
        }
    }
}
~~~

The code does not need to import each driver's implementation class name. Deleting a JAR merely due to lacking imports can strip the system of its JDBC provider at runtime.

Similar cases:

- Logging providers/bindings.
- JSON/XML serialization modules.
- ServletContainerInitializer.
- CDI/JPA providers.
- JDBC drivers.
- Native codec loaders.
- Third-party plugins.

**Dependency removal must be verified at the artifact/runtime level, not only at compile time.**

## 9. Common Post-Migration Dependency Conflicts

- Two versions of the same API/provider.
- Legacy javax EE and Jakarta EE providers sitting together on the runtime path.
- Two logging bindings or a bridging loop.
- Jackson modules with mismatched versions.
- Older ASM/Byte Buddy not understanding new class-file versions.
- JNI/JNA libraries with different architectures or ABIs.
- The same class in a shaded JAR and a regular dependency.
- Split packages on the Java module path.
- A library compiled for a higher Java release than the production JRE.

### 9.1. Legacy javax and Jakarta

javax.servlet.Filter and jakarta.servlet.Filter are two distinct types. Keeping both API JARs does not make an old servlet plugin compatible with a Jakarta Servlet runtime.

Do not delete all javax.*: javax.sql, javax.net.ssl, javax.crypto, and javax.xml.parsers remain Java SE APIs.

### 9.2. Logging Bridges

If adapter A forwards logs to B and bridge B forwards back to A, an infinite loop or duplication can occur. Choose the final logging architecture, a matching provider/binding, and remove redundant bridges.

### 9.3. Bytecode Tool Versions

An old instrumentation library may not support new Java class files. Clean up by upgrading to a vendor-supported version rather than keeping broad --add-opens forever to mask disparate kinds of errors.

## 10. Understanding the --add-opens Flag in JPMS

The Java Platform Module System restricts package access across modules. An older framework might reflectively access private fields of JDK classes and encounter InaccessibleObjectException.

Example flag:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

It opens java.lang of java.base to unnamed modules per runtime rules. This is an **additional permission**, not a configuration required for every Java program.

### 10.1. Why Review Flags?

If the framework has been upgraded to use public APIs and no longer needs deep reflection, the flag grants unnecessary broad access and makes it harder to spot dependencies still relying on internal behavior.

### 10.2. Scope of ALL-UNNAMED

ALL-UNNAMED grants unnamed modules (typically code on the classpath) the corresponding open scope, not just the library that originally triggered the error. When possible, remove it rather than widening permissions.

### 10.3. Do Not Rely on Flags as a Stable Contract

A JDK internal implementation can change or be removed. Opening a package does not give a private API the same commitment as a public Java SE API.

## 11. Distinguishing --add-opens and --add-exports

| Mechanism | Primary Effect |
|---|---|
| exports | Allows using a package's public types per module accessibility |
| opens | Allows deep reflection per module access rules |
| --add-exports | Supplements exports of a package |
| --add-opens | Supplements openness at runtime |

Workaround example:

~~~text
--add-exports=java.base/sun.nio.ch=ALL-UNNAMED
~~~

This example illustrates identifying **the risk of using internal APIs**, not a flag to add to every service.

If a library needs access to a non-exported public type, --add-exports serves a different role from --add-opens used for private reflection. Do not swap them arbitrarily.

### 11.1. Compiler and Runtime Have Separate Configurations

Source using a non-exported API may require the corresponding compiler option, yet runtime also needs permission if the code actually links against that API. Do not assume Maven compiler args automatically propagate to Surefire or the production Java command.

### 11.2. Public Replacements Are Better

Depending on the use case, you can switch to public NIO APIs, VarHandle, MethodHandles within valid access bounds, or upgrade the framework. Not every internal API has a direct replacement; test both behavior and performance.

## 12. Other Flags to Inventory

| Option | Meaning | Cleanup Question |
|---|---|---|
| --add-opens | Opens package for reflection | Who still needs it? |
| --add-exports | Adds export | Are JDK internals still used? |
| --add-reads | Adds readability | Is the module graph fixed properly? |
| --patch-module | Patches a module | Is there still a contract needing patching? |
| --add-modules | Adds modules | Which modules are actually needed? |
| --limit-modules | Limits observable modules | Are any providers missing? |
| --enable-preview | Enables preview features | Does code still use preview features? |
| --enable-native-access | Grants native access per JDK | Which components need it and at what scope? |

There is no rule to “delete all flags”. The goal is to remove temporary, obsolete, redundant, or overly broad flags.

### 12.1. --illegal-access Is a Historical Transition Flag

Certain post-Java 8 JDKs supported --illegal-access as a transition measure. Starting in Java 17, this option is no longer an effective way to relax strong encapsulation as in the earlier period.

Do not keep old flags on a new JVM and treat warnings/ignored flags as a solution. Consult the documentation of the exact target JDK.

### 12.2. Native Access

Newer JDKs have warning/control mechanisms for JNI or Foreign Function & Memory that vary by release. Do not grant --enable-native-access=ALL-UNNAMED by default to the entire application; identify the module/library that actually needs it and the specific policy.

## 13. Where Are JVM Flags Configured?

A project has multiple JVM processes:

~~~text
Maven/Gradle JVM
      |
Test JVMs
      |
Integration test process
      |
Production application JVM
      |
Batch/scheduler JVM
      |
Agent or maintenance process
~~~

Flags can appear in:

- JAVA_TOOL_OPTIONS/JDK_JAVA_OPTIONS.
- Shell scripts, systemd, Windows services.
- Docker ENTRYPOINT/CMD.
- Helm/Kubernetes args/env.
- Maven Surefire/Failsafe argLine.
- Gradle Test/JavaExec jvmArgs.
- Application server settings.
- CI workflows and secrets.
- IDE run configs.
- Runbooks.

Removing it in one place does not mean it has been removed from production.

### 13.1. Maven Surefire

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <argLine>
            --add-opens=java.base/java.lang=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
~~~

This example only illustrates where flags live. With JaCoCo and other agents, they may also modify argLine; do not overwrite all options without checking.

### 13.2. Gradle Test

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs("--add-opens=java.base/java.lang=ALL-UNNAMED")
}
~~~

This flag applies to the Test task's JVM, and does not automatically apply to the JVM running the production JAR.

### 13.3. Inspecting Effective JVM Configuration

Verify the actual command line/runtime args in the target environment. Differences may exist between configuration files in Git and options injected by the platform.

## 14. How to Remove --add-opens in a Controlled Manner

Suppose an old mock library needed java.lang opened, yet the new version supports the target JDK.

1. Record the stack trace/reason the flag was added.
2. Confirm the library version is vendor-supported.
3. Remove the flag in a test environment.
4. Run clean unit, contract, and integration tests.
5. Test reflection/proxy/DI/ORM/serializer paths.
6. Start the final production image.
7. Test dynamic plugins, agents, and scheduled jobs.
8. Verify the flag is not re-injected via environment variables.
9. Canary and monitor for errors.
10. Remove from all scripts/templates/runbooks.

### 14.1. Why Is java -version Not Enough?

This command does not trigger reflection or plugin loading. Errors may only occur when the first request touches a class or when a monthly scheduler runs.

### 14.2. Remove in Groups

If there are multiple --add-opens/--add-exports flags, prefer grouping by dependency/owner instead of removing all at once and not knowing which flag caused an error.

### 14.3. When It Cannot Be Removed Yet

Record the component needing access, package, JVM scope, support risk, owner, and review milestone. Do not leave broad permissions without anyone accountable.

## 15. Replacing Reflection Fallbacks with Public APIs

Transitional code:

~~~java
import java.lang.reflect.Field;

public final class LegacyReflection {
    public static Object read(
            Object instance, String fieldName) throws Exception {
        Field field = instance.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.get(instance);
    }
}
~~~

Can be blocked by module encapsulation. If the application owns the class, design a public accessor:

~~~java
public final class Order {
    private final String status;

    public Order(String status) {
        this.status = status;
    }

    public String status() {
        return status;
    }
}
~~~

Once consumers use the official API and tests verify correctness, the fallback and related opening permissions can be removed.

For third-party frameworks, prefer upgrading to a supported version or using a valid extension point. MethodHandles also obeys access control; it is not an unconditional way to bypass JPMS.

## 16. Cleaning Up Other JVM Flags After a JDK Upgrade

Besides module access, common items include:

- Java 8 GC logging flags migrated to Unified Logging.
- GC tuning flags that no longer apply.
- Unused preview flags.
- Diagnostic/trace flags meant only for an incident.
- Java agent options belonging to old versions.
- Temporary TLS/security compatibility settings.
- Locale/charset overrides with no remaining reason.
- Overly broad native access flags.

### 16.1. GC Log Example

Before:

~~~text
-XX:+PrintGCDetails
-Xloggc:/logs/gc.log
~~~

After with a JVM supporting Unified Logging:

~~~text
-Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Test log parsers/rotation/retention as well, not just JVM startup.

### 16.2. Do Not Delete Valid Tuning

-Xmx or collector choices may be measured performance settings. Do not make the shortest possible startup line a goal; only clean up unnecessary or unfounded flags.

## 17. Transitional Code in Migration

Some code patterns:

- OldSerializer/NewSerializer.
- LegacyDateBridge between java.util.Date and java.time.
- ReflectionFallback.
- JavaVersionStrategy.
- API aliases and compatibility shims.
- javax/Jakarta adapters.
- Database dual-read/dual-write.
- Event schema V1/V2 converters.
- Feature flag switches.
- CompatibilityFacade.
- Multi-release JAR classes.
- Native client/agent wrappers.

Not all of them are redundant. A domain adapter can be a long-term architectural boundary; a shim for older consumers may still be under commitment. Cleanup must distinguish carefully.

## 18. Dual Serializer Example and When to Clean Up

~~~java
public final class EventWriter {
    private final Serializer oldSerializer;
    private final Serializer newSerializer;
    private final boolean useNew;

    public EventWriter(
            Serializer oldSerializer,
            Serializer newSerializer,
            boolean useNew) {
        this.oldSerializer = oldSerializer;
        this.newSerializer = newSerializer;
        this.useNew = useNew;
    }

    public byte[] encode(Event event) {
        return useNew
            ? newSerializer.encode(event)
            : oldSerializer.encode(event);
    }
}
~~~

After all writers switch to the new implementation, consumer compatibility is verified, and the rollback window closes:

~~~java
public final class EventWriter {
    private final Serializer serializer;

    public EventWriter(Serializer serializer) {
        this.serializer = serializer;
    }

    public byte[] encode(Event event) {
        return serializer.encode(event);
    }
}
~~~

### 18.1. Old Writer Differs from Old Reader

Stopping V1 event writes does not mean V1 data has vanished. You can remove the old writer first while retaining the old reader until historical data is migrated or retention expires.

### 18.2. Feature Flags Are Not a Guaranteed Rollback

If the new writer produces data the old reader cannot understand, toggling the flag back to OFF does not guarantee rollback. Consider data schemas, event formats, and database compatibility.

### 18.3. Clean Up the Control Plane Too

After removing flags in Java source, also delete/retire the flag in the feature flag service, Helm values, configs, CI, dashboards, and documentation so operators do not assume a fallback path still exists.

## 19. Feature Flag Lifecycle

~~~text
OFF by default
      |
Canary for internal users
      |
Rollout by tenant/percentage
      |
ON for all traffic
      |
Observe rollback window
      |
Remove OFF path and flag
~~~

Before deleting, ask:

- Does any tenant still use the OFF path?
- Are there infrequent batch jobs or legacy consumers?
- Is the new data backward-compatible?
- Until when is rollback committed?
- Does monitoring prove traffic has shifted?
- Has historical data been tested?
- Does someone own the decision to retire the flag?

Keeping an unexecuted fallback for months can create a false sense of safety, because the old path is no longer tested.

## 20. Adapters, Facades, and Shims: Keep or Remove?

| Component | When to Keep | When to Clean Up |
|---|---|---|
| Domain facade | Stabilizes architectural boundary | Only serves an old library |
| API compatibility shim | Old consumers still supported | Support window closed |
| Schema converter | Historical data exists | Data migrated/retention expired |
| Reflection fallback | Old runtime still supported | JDK/library replaced and unneeded |
| Dual client | Both backends coexist | Old backend safely shut down |
| Multi-release JAR | Library supports multiple JDKs | Minimum JDK raised and old variant redundant |
| Native wrapper | Legacy ABI committed | New native client/vendor aligned |

Do not decide solely based on the name Legacy or call-site count. A public library may have no internal call sites yet still have external consumers.

## 21. Public API, SPI, and Plugin Compatibility

Old interface example:

~~~java
public interface LegacyPlugin {
    void execute(LegacyContext context);
}
~~~

New interface:

~~~java
public interface Plugin {
    void execute(PluginContext context);
}
~~~

If LegacyPlugin is deleted, previously built plugin binaries can hit linkage errors.

### 21.1. Before Deleting

- Have a support policy and consumer inventory.
- Published deprecation/migration guide.
- Have a breaking-version decision.
- Confirmed consumers/plugins migrated.
- Have binary compatibility tests when needed.
- Tested plugin loading on target JDK/container.
- Rollback no longer depends on the old interface.

### 21.2. Deprecated Does Not Mean End-of-Support

A deprecated public method may still be required during the support window. Removal must go through versioning and the consumer migration process.

### 21.3. ServiceLoader Metadata

If plugins are loaded via META-INF/services or config strings, removing an implementation requires updating metadata and testing discovery. Compile success is not enough.

## 22. Properly Scoped javax-to-Jakarta Cleanup

An application after migrating to Jakarta EE may still have:

~~~text
Legacy javax.servlet / javax.persistence APIs
New jakarta.servlet / jakarta.persistence APIs
Old web filters and providers
New Jakarta-compatible filters
Binary transformation utility
~~~

Enterprise APIs that changed namespaces are distinct types. Simply having both JARs does not make javax.servlet.Filter directly compatible with jakarta.servlet.Filter.

### 22.1. Do Not Remove javax Belonging to Java SE

javax.sql, javax.net.ssl, javax.crypto, and javax.xml.parsers remain Java SE APIs. Do not apply a blanket rule forbidding all javax imports.

### 22.2. Jakarta EE 8 Has Nuances

Some Jakarta EE 8-era artifacts carry the Jakarta name while class packages remain javax. Inspect the exact API release and JAR contents rather than inferring from the Maven groupId.

### 22.3. Cleaning Up Binary Transformers

Once vendor Jakarta-native releases are available, you can replace transformed legacy binaries, check service metadata and framework behavior, and remove the transformation step after testing succeeds.

## 23. Dependencies for APIs Formerly Included in the JDK

A classic example is JAXB/JAX-WS. When upgrading from Java 8 to newer JDKs, projects may need to add dependencies because some Java EE modules previously bundled with the JDK were removed by JDK 11.

A roadmap:

~~~text
Java 8
  Legacy javax.xml.bind code

Java 11 transition
  Explicit compatible JAXB API + runtime

Jakarta stack migration
  Switch source/generated code to jakarta.xml.bind
  Upgrade API and implementation

Post-transition cleanup
  Remove unused legacy JAXB stack
  Remove bridge/transformer
  Verify historic XML is still readable
~~~

An API JAR does not replace the runtime implementation. If a provider that needs no direct imports is deleted, JAXB operations can fail at runtime.

### 23.1. Generated Sources

If generators still emit javax.xml.bind imports, upgrade the generator/template; do not manually edit generated output.

### 23.2. Data History

If old XML/data must still be read per contract, retain an appropriate reader or migrate data with reconciliation before removal.

## 24. Historical Data and Schema Versions

A system may stop writing V1 yet still hold millions of V1 records.

~~~text
Old data: V1
New data: V2

New writer: writes V2
Current reader: reads V1 + V2
~~~

Removing the V1 reader is safe only when:

1. All V1 data has been migrated to V2 with validation/rollback.
2. V1 data has exceeded retention and been deleted per policy.
3. The V1 support contract is terminated and consumer impact has been addressed.

Do not treat 100% rollout of the new writer as proof that the old reader is useless.

### 24.1. Expand-Contract

~~~text
Expand schema
      |
Support old/new readers and writers
      |
Migrate data and consumers
      |
Close rollback window
      |
Contract old columns/adapters
~~~

Dropping old columns or mappers before the rollback window closes can break the previous application version.

### 24.2. Dual Write

Writing V1/V2 simultaneously requires idempotency and transaction safeguards; otherwise duplicate events/payments can occur. When cleaning up, verify only a single logical side effect is produced.

## 25. Rollback Also Has a Contract

A rollback plan must consider multiple layers:

~~~text
Application release
   |
   +--> Java runtime and JVM flags
   +--> Container image digest
   +--> Database schema
   +--> Event/serialization format
   +--> Native libraries and agents
   +--> Feature flag configuration
~~~

If V2 writes data that V1 cannot read, simply reverting the image to V1 can cause application failures or data loss.

### 25.1. Decision to Close the Rollback Window

Needs:

- Supported rollback window.
- Upgraded consumer inventory.
- Verified data format compatibility.
- Backup/restore/replay strategy.
- Approver for the point of no return from V1.
- Schedule to clean up adapters, flags, and old configs.

### 25.2. Runtime Flags by Release

A Java 8 image and a Java 21 image may use different GC logging/module flags. Rollback config must stay bound to the artifact instead of sharing one command line containing invalid flags.

## 26. Build Configuration Cleanup

Common remnants:

- maven.compiler.source/target overlapping with maven.compiler.release.
- Temporary Maven profiles.
- Temporarily pinned compiler executable paths.
- Old plugin version overrides.
- Annotation processors not supporting the new JDK.
- Shading/exclusion rules no longer needed.
- Gradle JVM args for tests that production does not need.
- Copy tasks containing old native binaries.
- Legacy BOM or version catalog entries.

Maven example with a Java 17 baseline:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

If the artifact must support Java 17, do not raise release to 21 merely because Maven runs on JDK 21.

### 26.1. Conflicting source/target/release

~~~xml
<maven.compiler.source>8</maven.compiler.source>
<maven.compiler.target>8</maven.compiler.target>
<maven.compiler.release>17</maven.compiler.release>
~~~

If standardizing on release, clean up conflicting settings and then inspect the effective POM.

### 26.2. Gradle Toolchain Differs from Release

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

A JDK 21 compiler can produce a Java 17-targeted artifact. These two versions serve different purposes.

## 27. Cleanup from Source to Production

A change may require updating:

~~~text
Source and tests
    |
    +--> pom.xml / build.gradle
    +--> generated-code templates
    +--> Dockerfile / container image
    +--> Kubernetes / Helm / systemd
    +--> CI workflows
    +--> feature flag control plane
    +--> agent settings
    +--> logs / dashboards / alerts
    +--> rollback scripts and runbooks
~~~

Removing a dependency from source while still copying the JAR into the container means the runtime still contains that library.

### 27.1. Inspect the Final Artifact

Cross-check the resolved dependency graph against executable JARs, WARs, and container images. If shading is used, duplicated classes or old providers may remain.

### 27.2. Inspect Effective JVM Args

A flag removed from the POM yet still present in JAVA_TOOL_OPTIONS injected in the cluster will still take effect. Look at the actual runtime configuration.

### 27.3. Update Runbooks

After cleanup, runbooks should not advise adding broad --add-opens as the default way to handle reflection errors. Instead, guide how to identify dependency/version/module boundaries.

## 28. How to Test Dependency Removal

Practical workflow:

1. Identify artifact, version, dependency path, and scope.
2. Locate code/references and configs.
3. Check ServiceLoader, reflection, plugins, and native components.
4. Identify public APIs/SPIs and consumers.
5. Remove the dependency in a controlled branch.
6. Run clean compile, unit/contract/integration tests.
7. Inspect the resolved dependency graph.
8. Inspect the final packaged JAR/WAR/image.
9. Exercise paths using runtime providers.
10. Smoke test on the target JDK/container.
11. Canary and measure business/error metrics.
12. Clean up exclusions, overrides, and related docs.

Do not use compile success as sole proof: a runtime-only provider can be missing without javac reporting an error.

## 29. Testing Transitional Code Removal

At minimum, test:

- Contract tests for APIs and event formats.
- Historical data fixtures.
- Database migration/rollback tests.
- Serializer round-trip.
- Idempotency and duplicate side-effect tests.
- Authorization and validation negative tests.
- Dynamic plugin/agent loading.
- Concurrency/retry behavior.
- Performance regressions.
- Startup/graceful shutdown.

An adapter can contain caching, batching, error mapping, or retry logic. Removing it is not just deleting a class; verify the new behavior does not diverge from the contract.

## 30. Canary After Removing JVM Access Flags

~~~text
Remove flag in test configuration
              |
       Build and tests
              |
       Staging with final image
              |
       Canary selected instances
              |
       Monitor access/linkage errors
              |
       Expand rollout or rollback
              |
       Close flag cleanup record
~~~

Monitor:

- InaccessibleObjectException.
- IllegalAccessError.
- NoClassDefFoundError.
- NoSuchMethodError.
- ServiceConfigurationError.
- Startup failures.
- Serialization/ORM/proxy errors.
- Agent/JNI problems.
- Business error rates and latency.

### 30.1. Rare Paths

A few hours of canary do not guarantee monthly batch or plugin code paths ran. Create synthetic/replay tests or extend the observation window appropriately.

### 30.2. Prove Permissions Were Reduced

After canary, inspect effective JVM arguments to ensure --add-opens is not being injected from another source.

## 31. SBOM and Dependency Security

After migration, the SBOM may still report old libraries due to:

- Shaded/relocated classes.
- Manually copied JARs.
- OS packages in the base image.
- Duplicate providers.
- Forgotten native libraries.

Verify actual artifacts, licenses, support status, CVEs, and provenance.

### 31.1. Do Not Remove a Dependency Just to Lower CVE Counts

A still-needed library may have to be upgraded or have its implementation swapped. Deleting it can break runtime functionality.

### 31.2. Immutable Images

When changing dependencies or base images, record the image digest and run security/functional tests. Mutable tags are insufficient to reproduce a production artifact.

## 32. Cleaning Up Operational Debt

Beyond code/dependencies, review:

- Legacy GC parsers not understanding Unified Logging.
- Alerts matching old exception text.
- Debug JVM flags left enabled too long.
- Old native agent versions.
- Dashboards querying migrated javax.* packages.
- Heap dump/JFR download scripts incompatible with the new image.
- CI still testing against unsupported profiles.
- Runbooks containing old JDK command lines.

### 32.1. Do Not Remove Metrics and Lose Alerting

If an old metric is no longer emitted, create replacement metrics/alerts before removing it. Detection for OOME, GC pauses, TLS failures, queue lag, and security issues must be preserved.

### 32.2. Debug Flags Have a Cost

Trace-level logs can increase CPU/I/O and expose runtime metadata. Once migration stabilizes, return logging to the designed baseline.

## 33. Guardrails So Compatibility Debt Does Not Return

Measures:

- Maven Enforcer/Gradle constraints for version alignment.
- jdeps/internal API scans.
- Rules checking forbidden or unsupported dependencies.
- CI detecting new --add-opens/--add-exports requiring review.
- Contract tests for API/SPI.
- Test matrix for minimum supported JDK.
- Runtime smoke tests on the final container image.
- SBOM diff and security review.
- PR template requiring owner and removal condition declarations.

### 33.1. Do Not Ban with Overly Broad Patterns

A rule banning all javax imports will falsely flag javax.sql and javax.net.ssl belonging to Java SE. A rule banning all --add-opens can block approved exceptions. Define specific policies and an exception register with owners.

### 33.2. Justification Template When Adding a New Workaround

~~~text
Workaround ID:
Why needed:
Affected dependency:
Affected JVM process:
Minimal scope:
Security impact:
JDK versions:
Owner:
Removal condition:
Review date:
Integration tests:
~~~

This makes cleanup during the next migration easier.

## 34. Comprehensive Scenario: Java 11 to Java 21

An order service already runs Java 21 yet still has:

~~~text
Dependencies:
  legacy XML binding library
  Jakarta XML Binding runtime
  older bytecode tool
  temporary JSON adapter

JVM:
  --add-opens=java.base/java.lang=ALL-UNNAMED
  --add-exports=java.base/sun.nio.ch=ALL-UNNAMED

Code:
  OldJsonWriter
  NewJsonWriter
  ReflectionFallback
  USE_NEW_JSON
~~~

### Step 1 — Inventory Graph and Usage

Inspect Maven/Gradle, generated code, providers, and container images. Do not conclude from import counts.

### Step 2 — Assess Data/Consumers

Are there historical XML or JSON V1 records? Do consumers still use old schemas/APIs? Is rollback still committed?

### Step 3 — Upgrade Dependencies

Replace the bytecode framework with a JDK 21-supported version. Align Jakarta APIs and runtimes, avoiding duplicate providers.

### Step 4 — Clean Up Reflection Fallbacks

Move to official public APIs/libraries and run regression tests. Once no references remain, remove temporary code.

### Step 5 — Revoke JVM Permissions

Remove --add-exports/--add-opens by component, testing reflection/proxies/ORM/agents. Canary using the final production image.

### Step 6 — Close Out Serializer Rollout

Confirm all new writes use V2, consumers have migrated, and historical data remains readable. Remove the old writer/feature flag at the right time; retain the V1 reader if data still exists.

### Step 7 — Clean Up Artifacts and Runbooks

Remove legacy JARs, stale flags, CI variables, and old scripts; update SBOM/digest and record the cleanup decision.

## 35. Common Mistakes

### “No direct import means the dependency is useless”

False. ServiceLoader, reflection, generated code, native loading, and framework provider discovery can use it.

### “Once on the new JDK, remove all --add-opens flags immediately”

Insufficient. Rare code paths, plugins, and agents must be checked; remove based on evidence and scope.

### “--add-opens and --add-exports are the same”

False. They address different types of access, and both require control.

### “Granting export for an internal API means that API is supported long-term”

False. JDK internal APIs can still change or disappear.

### “A flag doesn't crash the JVM, so leave it in”

Unwise. It may be obsolete, ignored, or grant unnecessary permissions.

### “The old code path gets no traffic, so it can be deleted”

Uncertain. There may still be historical data, legacy consumers, batch jobs, or rollback needs.

### “Feature flags always enable rollback”

False if data written by the new code is incompatible with the old code.

### “Removing the dependency from the POM means the container is clean”

Uncertain. Shading, manual COPYs, or stale runtime assets may remain.

### “Green unit tests prove cleanup succeeded”

Insufficient if providers/agents are only loaded at runtime or by infrequent scheduled jobs.

### “Deprecated APIs can be deleted anytime”

False under public compatibility contracts; a versioning/deprecation policy is required.

### “Known defects can be documented as allowed differences”

Unwise. Defects need separate tracking and risk acceptance, not legitimizing as expected behavior.

### “Fewer JARs is always better”

Not if it drops a required provider. Correctness and support contracts matter more than library count.

## 36. Post-Migration Cleanup Checklist

- [ ] Identified target JDK and minimum supported runtime.
- [ ] Listed dependencies, JVM flags, and transitional code.
- [ ] Every workaround has an owner, scope, and removal condition.
- [ ] Inspected Maven/Gradle resolved graphs.
- [ ] Distinguished compile/runtime/test/annotation processor scopes.
- [ ] Checked reflection, ServiceLoader, config strings, and native loading.
- [ ] Evaluated public API/SPI and plugin consumers.
- [ ] Checked generated code.
- [ ] Distinguished --add-opens from --add-exports.
- [ ] Found internal API replacements or vendor-supported libraries.
- [ ] No overly broad module permissions remain unnecessarily.
- [ ] Obsolete flags are not kept as error-masking measures.
- [ ] Checked build/test/production JVMs separately.
- [ ] Properly classified Java SE javax vs. Jakarta EE.
- [ ] Verified historical data/event compatibility.
- [ ] Closed rollback window or designed data migration.
- [ ] Cleaned up unneeded feature flags and fallbacks.
- [ ] Retained legacy readers where contracts still apply.
- [ ] Ran clean build, contract, and integration tests.
- [ ] Inspected final JAR/WAR/container image.
- [ ] Tested plugins, agents, reflection, and scheduled paths.
- [ ] Canaried and observed runtime.
- [ ] Updated SBOM and security review.
- [ ] Cleaned up Docker/Helm/CI/scripts/runbooks.
- [ ] Guardrails in place for new workarounds.

## 37. Cleanup Item Record Template

~~~text
IDENTITY
  ID:
  Owner:
  Type: dependency / JVM option / adapter / feature flag
  Introduced in release:
  Original blocker:
  Reason:
  Security and maintenance impact:

SCOPE
  Service/module:
  JDK vendor/version:
  Dependency/framework version:
  Build/test/runtime processes:
  Consumers/plugins:
  Historical data:

REMOVAL
  Artifact/flag/class:
  Proposed replacement:
  Vendor support evidence:
  Removal condition:
  Rollback window:
  Data migration/retention:

VALIDATION
  Source references:
  Dependency graph:
  ServiceLoader/reflection:
  Final image:
  Unit/contract tests:
  Integration tests:
  Agent/plugin tests:
  Runtime smoke:
  Canary:
  Security/performance:

DECISION
  Remove / retain / defer:
  Reviewer:
  Release:
  Remaining exceptions:
  Review date:
  Rollback artifact/config:
~~~

The record must be updated with the release so future operators and JDK upgraders know which components were kept and why.

## 38. Summary

Cleaning up dependencies, access flags, and transitional code is the responsible completion step of a Java compatibility migration. An application may already run well on the new JDK while still carrying risks from the old platform if it keeps excess libraries, broadened reflection permissions, and unmaintained fallback branches.

Key principles:

1. **Clean up based on evidence, not by name.** Runtime discovery can use a dependency without a Java import.
2. **Manage module permissions by scope.** --add-opens and --add-exports have different semantics; opening permissions does not make internal APIs stable.
3. **Prefer public APIs and supported libraries.** Do not replace an old workaround with another uncommitted workaround.
4. **Honor public contracts and historical data.** Consumers, plugins, and rollback may require keeping adapters within a bounded window.
5. **Do not maintain dual-path code indefinitely.** After rollout, clean up feature flags and old code paths per plan.
6. **Clean up source, build, and runtime alike.** JARs, containers, CI, startup arguments, and runbooks must align.
7. **Test rare code paths.** Reflection, ServiceLoader, batch jobs, agents, and historical data may fail only days later.
8. **Deploy with canary and rollback.** Revoking a workaround is a production change, not merely a source refactor.
9. **Maintain guardrails.** New workarounds need a clear owner, minimal scope, and removal condition.

A migration is only truly complete when the system not only runs properly on the target JDK, but also has supported dependencies, explainable JVM permissions, redundant transitional code removed, and a reliable operational process for subsequent upgrades.
