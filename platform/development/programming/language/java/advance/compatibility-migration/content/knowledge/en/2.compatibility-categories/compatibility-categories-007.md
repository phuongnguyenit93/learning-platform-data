# Why Compilation Success Does Not Prove an Application Runs Correctly

During a Java upgrade or library version change, a successful compilation often creates the impression that the system is already compatible. However, that outcome only verifies a narrow scope: the compiled source code passed the compiler's checks under the JDK, compiler options, and libraries present on the compile classpath at build time.

In reality, the application must still load classes, link calls, initialize frameworks, read configurations, connect to services, process data, and execute business logic properly in a concrete runtime environment. These occur after compilation and depend on the runtime classpath, deployed JDK/JRE, configuration, data, operating system, and external services. Therefore, **compile success is necessary evidence, yet insufficient on its own to conclude an application runs correctly or is compatible after migration**.

## 1. What Does Compilation Verify?

When compiling Java, the compiler reads source code, parses syntax, checks types, checks access modifiers, and resolves types, fields, and methods referenced by the source. It then emits bytecode into `.class` files.

Example:

```java
public class GreetingApp {
    public static void main(String[] args) {
        System.out.println("Hello Java");
    }
}
```

If compilation completes, we know this code is valid according to the Java language and the types visible to the compiler. Yet the compiler does not run `main`, open database connections, initialize a Spring `ApplicationContext`, read production config, or call payment gateway APIs.

A command such as `compileJava` in Gradle or `mvn compile` in Maven normally executes only the compilation phase. It does not inherently include testing, packaging, application startup, or verifying behavior in the target environment.

The deployment chain can be pictured as follows:

```text
Source code
   |
   v
Compilation succeeds
   |  Checks syntax, types, APIs on compile classpath
   v
Bytecode and resources
   |
   v
Artifact packaging
   |
   v
Class loading and linking on runtime classpath
   |
   v
Application, framework, and config initialization
   |
   v
Connecting services, reading/writing data
   |
   v
Executing business logic in a real environment
```

Errors at any later stage can still happen even when compilation succeeded earlier.

## 2. Compatibility Has Multiple Distinct Layers

In a Java upgrade, “compatible” does not merely mean source code still compiles. Distinguish these layers:

| Compatibility Layer | Question to Answer | Appropriate Evidence |
|---|---|---|
| Source compatibility | Does current source code compile with the target compiler and APIs? | Clean compile with exact target JDK and options |
| Binary compatibility | Can compiled bytecode link cleanly against classes and libraries at runtime? | Run the artifact on the exact runtime classpath; inspect dependencies and linkage |
| Behavioral compatibility | Do the same API calls still produce results and side effects expected by the application? | Unit tests, integration tests, contract tests, and regression testing |
| Platform/environment compatibility | Does the app run on the target JDK, OS, architecture, and deployment configuration? | Run in a production-like environment, verify startup and operations |
| Data and protocol compatibility | Does the new version read, write, and exchange data with related versions or services? | Schema testing, data migration, and cross-system contract tests |

Compilation success mainly provides evidence for the first layer. Issues in other layers often surface only when the JVM loads classes or when the application handles real inputs.

## 3. Compile Classpath and Runtime Classpath Can Differ

This is a frequent reason a project compiles yet fails to run.

The compiler needs libraries to understand types and check calls in source code. At runtime, the JVM needs the actual classes to load and link. Those two sets of libraries can differ.

In Gradle, `compileClasspath` and `runtimeClasspath` are separate configurations. A library may be declared only for compilation while the library required at runtime is missing or resolved to a different version. Transitive dependencies, dependency conflicts, `runtimeOnly`, packaging plugins, or deployment layouts can also make the runtime classpath diverge from what developers expect.

### Example: Compiling Against One Library Version, Running Against Another

Suppose `payment-client` version 1 defines:

```java
public class PaymentClient {
    public Receipt submit(Order order) {
        // Send payment request
        return new Receipt();
    }
}
```

A module or plugin was compiled while `submit(Order)` existed. Later, the runtime environment loads a library version where that method no longer exists. The client's bytecode still holds a reference to the old method; when the JVM resolves the call, the app may fail with:

```text
java.lang.NoSuchMethodError
```

A similar situation occurs when an application module compiles against a newer library while the deployment server prioritizes an older JAR. The compiler saw a matching API, yet the running JVM loaded a different API.

Key takeaway: **the library version used at compile time does not automatically guarantee the exact same library version is loaded at runtime**.

In Gradle, you can inspect each classpath's dependency tree with commands such as:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

To trace why a specific version was selected, use `dependencyInsight` for the right dependency and configuration. In Maven, `mvn dependency:tree` displays the resolved dependency tree. Inspect the final artifact and deployment environment whenever running inside an application server, container, or platform supplying its own libraries.

## 4. Bytecode May Not Match the Running JVM

The JDK used to compile and the Java runtime used to execute are related yet not necessarily the same installation.

If compiled on a newer JDK without setting appropriate bytecode/API targets, the compiler can emit class files an older JVM cannot read. The app then halts at class loading with:

```text
java.lang.UnsupportedClassVersionError
```

For instance, classes compiled for Java 21 cannot run by default on Java 17. Having JDK 21 on developer machines and passing builds does not prove production runs Java 21.

When targeting a specific Java version, configure toolchains and release levels appropriately. With `javac`, `--release` constrains both bytecode format and allowed Java SE APIs for that release. In Gradle, align Java toolchains and `options.release` consistently with your project baseline.

Illustrative setup for a project targeting Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

This helps govern the build compiler and target APIs. Still, run the artifact on a real Java 17 or equivalent runtime to verify behavior, because build configuration alone cannot validate every aspect of deployment hosts.

## 5. Classes and Methods Can Fail to Link at Runtime

The compiler checks references against the libraries it sees. At runtime, the JVM must locate matching class and member definitions inside actual JARs. If library structure changed incompatibly, errors can surface only during loading or invocation.

Common failures:

| Error | Typical Meaning |
|---|---|
| `ClassNotFoundException` | Code explicitly requests loading a class, often via `Class.forName` or a classloader, and cannot find it |
| `NoClassDefFoundError` | The JVM needs a class definition yet cannot use it; either missing at runtime or prior class initialization failed |
| `NoSuchMethodError` | Bytecode references a method absent from the class loaded at runtime |
| `NoSuchFieldError` | Bytecode references a field absent from the class loaded at runtime |
| `AbstractMethodError` | A runtime call requires a concrete implementation, yet the actual loaded class lacks a compatible implementation |
| `IncompatibleClassChangeError` | Structural or usage contract of a member/class changed binary-incompatibly, such as static vs instance or class vs interface |

These errors signal that you must inspect the dependency graph, classpath order, packaged JARs, and active classloaders. Avoid adding random dependencies just to silence an error, as that can mask version conflicts or introduce new ones.

## 6. Code Compiles, Yet API Behavior Has Changed

A library can keep identical class names, method names, and parameter types so source continues compiling. Nevertheless, the API's behavioral contract may have changed across releases.

For example, an older API accepted timeout values in seconds, whereas the new version interprets timeout in milliseconds while keeping type `long`. This call still type-checks cleanly:

```java
client.setTimeout(30L);
```

Yet if parameter semantics changed, passing `30` meant 30 seconds before and now means only 30 milliseconds. The compiler cannot infer caller intent to warn about this semantic shift.

Other behavioral changes include:

- Changed defaults, such as retries, timeouts, pool sizes, or authentication modes.
- Changed result ordering when ordering was previously unspecified.
- Changed handling for `null`, empty inputs, encoding, or timezones.
- Exceptions thrown in scenarios that previously returned a normal value.
- API keeps running yet changes synchronization, thread safety, or resource lifecycle.
- Operations becoming asynchronous or introducing side effects.

This is why you must read library release notes and migration guides, and write tests asserting behaviors your application actually relies upon. Tests proving only that a method returns without crashing are not enough; verify outputs, side effects, and edge cases.

## 7. Frameworks Often Detect Errors Only at Startup

In Java applications using Spring or similar frameworks, compile success does not guarantee bootstrap succeeds.

The compiler typically does not verify component scanning, bean wiring, auto-configuration conditions, proxy creation, configuration binding, or connection initialization. Mechanisms driven by reflection and string-configured class names are not checked like ordinary Java method calls either.

Example:

```java
@Service
public class OrderService {
    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

This class compiles even if no matching bean for `PaymentGateway` exists in the runtime application context. When Spring attempts to instantiate `OrderService`, startup fails because the required dependency cannot be injected.

Startup errors often arise from:

- Beans or modules missed by scanning, unregistered, or excluded by auto-configuration conditions.
- Incompatible combinations of Spring Boot, Spring Framework, and integration libraries.
- Changes in constructors, proxies, packages, or reflection breaking legacy config.
- Missing required properties, wrong profiles, or mismatched environment variable names.
- Resources missing from the packaged artifact or altered resource paths.
- Service provider metadata or plugin config missing from packaged JARs.

Therefore, launch the packaged application and observe the entire startup sequence. A unit test instantiating one isolated class cannot replace application context or full application bootstrap checks.

## 8. Configuration and Deployment Environments Are Not Verified by the Compiler

Applications read critical inputs from outside source code: environment variables, YAML/properties files, secrets, JVM flags, file paths, network ports, TLS certificates, and container settings.

This code compiles normally:

```java
String jdbcUrl = System.getenv("DB_URL");
```

At runtime, `DB_URL` may be unset, malformed, or point to an unreachable database. Similarly, config files may be syntactically valid yet contain profile names, keys, or values no longer supported by the newer framework version.

Common environment discrepancies include:

- Developer machines run Java 21 while production containers run Java 17.
- Local machines have config files or environment variables absent in CI.
- Operating systems differ on path formats, file permissions, encodings, or case-sensitive filenames.
- Production uses different certificates, proxies, DNS, firewalls, or TLS policies from local setups.
- Database engines or message brokers differ in version and configuration from test environments.
- JVM flags, memory limits, timezones, locales, or default charsets differ.

One successful local run on a laptop proves behavior only inside that environment. To validate migration, run the packaged artifact on the target JDK, configuration, and deployment topology while verifying external dependencies.

## 9. Existing Data and Cross-Service Protocols Can Still Break

The compiler primarily validates program source and in-memory types. It does not check rows stored in databases, files serialized by prior versions, or payloads sent by external services.

For example, an upgrade might rename a column, alter a column type, or switch a field from required to optional. Updated Java code compiles cleanly yet queries fail against legacy schemas. Similarly, a service can compile after upgrading a JSON library yet misread payloads due to changed naming strategies, date formats, or missing-field defaults.

With Java serialization, class layout and `serialVersionUID` changes can render previously serialized payloads unreadable as intended. With REST, messaging, or RPC, having both ends compile does not guarantee agreement on fields, enums, versions, encodings, timeouts, or message semantics.

When migration affects data or protocols, verify:

1. Can the new application read data produced by the older version?
2. Can the older application still read data written by the new version during rolling deployments?
3. Do database migrations execute in proper order and recover cleanly on failure?
4. Do calling producers/consumers or services agree on the updated contract?
5. Is an expand-migrate-contract strategy required for multi-version coexistence during transition?

These questions must be answered through data and integration tests—they cannot be deduced from compilation results.

## 10. Reflection, ServiceLoader, and Classloaders Create Hidden Dependencies

Not every dependency between classes appears as a static import and method call in source code.

Example:

```java
Class<?> type = Class.forName("com.example.plugin.FastExporter");
Object exporter = type.getDeclaredConstructor().newInstance();
```

The compiler cannot generally verify that `"com.example.plugin.FastExporter"` refers to a class present in the runtime artifact. If packages were renamed, JARs dropped from `runtimeClasspath`, or modules fail to open needed packages, failure surfaces only when that code runs.

Mechanisms easily impacted during migration include:

- `Class.forName`, reflection, and string-based member lookups.
- `ServiceLoader` and provider files under `META-INF/services`.
- Annotation scanning and runtime proxy generation.
- Plugin architectures using custom classloaders.
- Java Platform Module System (JPMS), notably `requires`, `exports`, and `opens`.
- Libraries accessing JDK internals or relying on unspecified Java SE behavior.

When upgrading the JDK, audit deprecated/removed API warnings, reflection access, and internal API dependencies. Compilable source can still trigger `IllegalAccessException`, `InaccessibleObjectException`, or provider loading failures under newer module boundaries and JDKs.

## 11. Certain Operational Risks Appear Only Under Load or Over Time

Even when startup succeeds and core functional flows run properly, migration can shift performance or operational behavior.

Examples:

- Garbage collector characteristics, memory footprint, or pause times differ from before.
- Thread pools, connection pools, or schedulers increase latency or exhaust resources.
- An API shifting between synchronous and asynchronous execution triggers race conditions.
- Misaligned retry policies amplify load onto downstream dependencies.
- Resources like files, sockets, threads, or connections leak or close improperly.
- Bugs surface only with large datasets, high concurrency, or hours of continuous uptime.

Compilation catches none of these, and overly brief smoke tests often miss them too. Choose load tests, soak tests, metrics/logs/traces observation, and failure-injection scenarios scaled to your application's risk profile.

## 12. Verification Workflow After Compilation Succeeds

A trustworthy migration workflow expands verification in stages, each targeting a distinct category of risk.

### Step 1: Confirm the Exact JDK and Bytecode Targets

- Check the real JDKs running in CI and locally.
- Explicitly declare Java toolchains and release targets.
- Check the Java version in target runtime environments.
- Ensure every module, plugin, and internal library builds against a compatible baseline.

### Step 2: Inspect the Dependency Graph

- Compare compile classpath against runtime classpath.
- Watch for unexpected upgrades, downgrades, or exclusions.
- Audit transitive dependencies and libraries provided by containers/application servers.
- Inspect final packaged artifacts to confirm required JARs and resources are bundled.

### Step 3: Clean Build and Execute Automated Tests

- Run a clean build to avoid stale cached outputs.
- Run unit tests covering business logic and boundary cases.
- Run integration tests against required databases, brokers, and services.
- Run contract tests wherever modules or external systems communicate.
- Scrutinize skipped tests, flaky tests, or tests restricted to a single JDK.

### Step 4: Execute the Exact Deployable Artifact

Do not run solely from an IDE or developer source layout. Package the artifact exactly as deployed and run it on the target runtime. This catches discrepancies in manifests, resources, packaged dependencies, entry points, classloaders, and JVM versions.

### Step 5: Verify Real Startup and Configuration

- Boot with production-like profiles and configuration.
- Confirm the framework creates required beans, routes, schedulers, and listeners.
- Test connections to databases, caches, brokers, and external services.
- Check secrets, TLS, permissions, and health endpoints.
- Confirm graceful shutdown releases resources properly.

### Step 6: Run Regression and Data Compatibility Tests

- Exercise end-to-end critical business flows.
- Test with representative data, legacy data, and boundary inputs.
- Verify schema migrations and multi-version rollout compatibility.
- Compare business outcomes against the pre-migration baseline.

### Step 7: Validate Operational Behavior

For high-impact changes, execute load testing and monitor metrics, logs, and traces over an adequate window. Define clear thresholds for latency, error rates, memory, CPU, connection pools, and recovery. During deployment, maintain health checks, observability, and a tested rollback plan.

## 13. Selecting Tools by Risk Category

No single tool proves full compatibility across every dimension. Combine these tools by objective:

| Tool / Technique | Helpful for Checking | Limitations |
|---|---|---|
| `javac --release` / Gradle Java toolchain | Language level, bytecode format, and target Java SE APIs | Does not verify configuration or runtime behavior |
| `./gradlew dependencies` / `dependencyInsight` | Dependency graph per configuration and selection rationale | Must cross-check against packaged artifacts and runtime classloaders |
| `mvn dependency:tree` | Resolved Maven dependency tree | Does not prove external runtime libraries match |
| `jar tf app.jar` | Inspecting classes and resources inside a JAR | Does not prove classes initialize or behave properly |
| `javap -verbose` | Viewing bytecode, class-file version, and class descriptors | Does not replace executing on the target JVM |
| `jdeps` | Static class/package dependency analysis and detecting some JDK internals | Misses dynamic reflection, string-configured types, and behavioral shifts |
| Unit/integration/contract tests | Verifying behaviors and interactions encoded in tests | Covers only scenarios explicitly tested |
| Smoke/load/soak tests & observability | Verifying startup, critical paths, and operational stability | Requires well-designed workloads and pass/fail thresholds |

Static analysis narrows the search space, yet final judgment must rely on packaged artifacts, target runtimes, and real execution scenarios.

## 14. Example of an Evidence-Backed Migration Conclusion

Suppose a team upgrades an application from Java 17 to Java 21. The pipeline runs `compileJava` cleanly. That result supports only concluding that the compiled sources are compatible with the chosen compiler and compile classpath.

To conclude the application is compatible with Java 21, gather additional evidence such as:

- All modules and plugins built with agreed target settings.
- Runtime classpath contains no conflicting library versions or missing dependencies.
- The packaged artifact starts cleanly on Java 21.
- Application context, configs, resources, and service connections initialize properly.
- Regression test suites confirm critical business workflows remain accurate.
- Stored data and inter-service contracts remain compatible under the new deployment.
- Operational metrics stay within acceptable bounds under representative load.

If the only observed signal is `BUILD SUCCESSFUL` on a compile task, report status accurately as **compilation verified**, not **runtime or behavioral compatibility verified**. Recording status by evidence level keeps migration reporting honest and prevents turning a single green compile step into a false claim of whole-system compatibility.

## 15. Principles to Uphold When Assessing Compatibility

1. **Define the exact scope of each piece of evidence.** Compile proves compile; tests prove tested scenarios; startup proves application initialization under tested configuration.
2. **Verify the real artifact on the real runtime.** Launching from an IDE never replaces running the deployable package on the target JDK.
3. **Cross-check dependencies at both stages.** APIs seen by the compiler must match the classes actually loaded by the JVM.
4. **Verify behavioral contracts.** Unchanged method signatures do not guarantee unchanged semantics, defaults, or side effects.
5. **Include data and environments in testing.** Configurations, schemas, protocols, and external services are integral to compatibility.
6. **Report conclusions strictly by evidence tier.** Clearly separate compiled, unit-tested, executed on target runtime, and operationally verified.

Compilation success is the first milestone in migration. Only once bytecode loads cleanly, the application initializes, interactions and stored data remain intact, and the system meets requirements in its target environment do we have solid evidence that the upgrade achieves full compatibility.
