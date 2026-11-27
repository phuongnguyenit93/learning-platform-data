# Inventorying Dynamic Features and Assessing Migration Readiness of an Existing JVM Application

## 1. Don't Start by Changing the Build Command

A Spring Boot application running reliably on the JVM may have accumulated years of dependencies, plugins, configuration, and behaviors that are only decided at runtime. Moving to GraalVM Native Image changes when several decisions are made: Spring AOT analyzes the `ApplicationContext` at build time, while Native Image performs static analysis to determine which classes, methods, and resources need to be included in the executable.

Therefore, a migration assessment needs to answer two separate questions:

1. **Can the application run correctly with a classpath and bean graph determined at build time?**
2. **Are the benefits in startup, memory, deployment, or operational cost large enough to offset the additional native build, metadata, testing, and maintenance?**

Not every JVM application needs Native Image. A long-running service that is well-optimized by the JIT and has no cold-start requirements may not gain enough benefit. Conversely, frequently started workers, scale-to-zero workloads, CLIs, or services with tight memory limits can benefit significantly.

This lesson helps you inventory your current application before deciding to migrate. The end result is a reviewable migration profile: which dependencies are already compatible, which dynamic features require metadata or refactoring, what the blockers are, how to test, and the go/no-go criteria.

After this lesson, you can:

- Build an inventory of modules, dependencies, profiles, and runtime configuration of a JVM application.
- Identify reflection, resource loading, proxies, serialization, JNI, class loading, and other dynamic features.
- Evaluate Spring AOT limitations and dependency Native Image support levels.
- Use JVM, AOT-on-JVM, and native tests to measure readiness in stages.
- Classify risks as ready-compatible, requiring work, or blockers.
- Plan a per-module/service migration and decide whether to keep or skip Native Image.

## 2. Evaluate Benefits Before Technical Inventory

### 2.1. Cases Where Native Image Is Often Worth Testing

| Workload characteristic | Potential benefit |
|---|---|
| Scale-to-zero service or frequent instance creation | Reduced time from process start to serving requests |
| CLI, short-lived batch worker, or scheduled job | Reduced startup cost per execution |
| Container with a low memory limit | Can reduce RSS and allow higher instance density |
| Serverless or time/instance-billed environments | Reduced cold start and resource hold time if the workload fits |
| Service where startup latency is a critical SLO | Easier to meet readiness targets with faster native startup |

These are motivations to benchmark, not guarantees that native is always faster or uses less memory for every workload.

### 2.2. Costs to Account For

- Native compilation typically takes longer than JVM compilation and requires runners with more RAM/CPU/disk.
- Some libraries require reachability metadata, runtime hints, or code changes.
- Executables are tied to the build OS and architecture; separate builds are usually needed per target.
- The native runtime does not have the same progressive JIT optimization model as HotSpot. Post-warmup throughput may differ.
- Debugging, profiling, heap analysis, and certain agents/tooling can differ from the JVM.
- Upgrading Spring Boot, JDK, GraalVM, or dependencies may require re-running native compatibility tests.

### 2.3. Measure the JVM Baseline Before Migrating

Record metrics of the current application in a production-like environment:

| Metric | How to measure |
|---|---|
| Startup-to-ready | From process start until health/readiness allows receiving traffic |
| RSS after startup | Resident memory after the application is ready |
| RSS after warm-up | Memory after a representative workload and after JIT stabilizes |
| CPU and throughput | Requests/second or job throughput under representative load |
| p50/p95/p99 latency | Measured at startup, after warm-up, and under high load |
| Container image size | Size of the image stored in the registry and pulled to nodes |
| Build duration | Time to compile, test, package, and build the image |
| Operational cost | CPU/RAM reservations, replica count, cold starts, and deployment time |

Compare native and JVM on the same CPU architecture, same database, same request mix, same memory limit, and same readiness measurement method. Don't just compare `main()` time against JVM startup time; measure until the service can actually receive traffic.

## 3. Inventorying the Existing JVM Application

### 3.1. Define Migration Scope

First, list the independently buildable and deployable units:

- Spring Boot application/module.
- Shared libraries used by multiple services.
- Integration adapters for databases, message brokers, HTTP clients, or cloud SDKs.
- Plugins, extensions, or configuration-loaded modules.
- Batch jobs, schedulers, CLIs, or workers with separate entry points.

Do not evaluate an entire monorepo as a single application if individual services have different classpaths and workloads. One service may be ready for Native Image while another uses runtime plugins or unsupported libraries.

### 3.2. Collect the Dependency Tree and Versions

With Maven:

```bash
./mvnw dependency:tree -Dverbose > dependency-tree.txt
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath > runtime-dependencies.txt
./gradlew buildEnvironment > build-environment.txt
```

Record both direct and transitive dependencies. A Spring Boot starter can pull in libraries that use reflection, JNI, or classpath scanning even when application code does not call them directly.

For each important dependency, record:

- `groupId:artifactId:version` or Gradle module coordinates.
- Whether the version is managed by the Spring Boot BOM or overridden.
- Whether the dependency is compile/runtime/optional or test-only.
- Whether native metadata is provided by the library or available in the GraalVM Reachability Metadata Repository.
- Whether a newer version fixes native compatibility.
- Whether it requires OS/architecture-specific native libraries or toolchains.

Native Build Tools can automatically use metadata from the Reachability Metadata Repository. Even so, the presence of metadata does not prove every code path or library version is compatible; you still need to check versions and run tests on the native executable.

### 3.3. Inventory Environment-Specific Configuration

List:

- Spring profiles used in local, test, staging, and production.
- Properties that affect bean creation via `@ConditionalOnProperty`.
- Properties that only change configuration values without altering the bean graph.
- External services, endpoints, credentials, certificates, and DNS names.
- File directories mounted into the container.
- Libraries or plugins enabled only in certain environments.

Clearly distinguish properties that **determine whether a bean exists** from properties that only change values on an already-created bean. The first group directly impacts Spring AOT.

### 3.4. Overview Inventory Template

| Module/service | Runtime profile | Key dependencies | Dynamic features | Preliminary assessment |
|---|---|---|---|---|
| `order-api` | `production` | Web, Security, JPA, PostgreSQL | Hibernate, Jackson, proxies, Flyway | Needs metadata review and native tests |
| `billing-worker` | `batch` | JDBC, messaging, PDF SDK | Reflection in PDF SDK, resource templates | SDK dependency risk |
| `plugin-host` | `production` | Plugin API, scripting engine | Runtime class loading, script execution | High risk, needs architecture review |

The module names in the table are examples only. Replace them with actual modules and record evidence for each conclusion.

## 4. Inventorying Dynamic Features in Code and Dependencies

Native Image does not forbid all dynamic features. Many features still work if the set of classes/members/resources can be determined at build time and given appropriate reachability metadata. The highest risk comes from behavior that depends on runtime data the compiler cannot know in advance, or requires loading arbitrary code after the executable has been built.

### 4.1. Reflection and Introspection

Look for patterns:

- `Class.forName(...)`, `ClassLoader.loadClass(...)`.
- `getDeclaredMethod`, `getMethod`, `getDeclaredField`, `getConstructor`.
- `Method.invoke`, `Constructor.newInstance`, `Field.get/set`.
- `MethodHandles.Lookup` and `VarHandle`.
- Frameworks discovering annotations, DTOs, or models by class name.

Preliminary search command in source:

```bash
rg -n "Class\.forName|loadClass\(|getDeclaredMethod|getDeclaredField|getConstructor|Method\.invoke|newInstance\(" src
```

Also search code in shared libraries if the repository contains source. For binary dependencies, read the documentation, source, or use the tracing agent on the JVM to detect actual operations.

Classify each case:

| Usage pattern | Assessment |
|---|---|
| Fixed class/member, known name upfront | Usually handled via Spring hints or specific reachability metadata |
| Framework with integration/AOT support | May be handled automatically; verify generated hints and test |
| Class name from configuration but finite set of classes | Can register all valid choices at build time |
| Arbitrary class name supplied by user or plugin post-deploy | High risk; Native Image cannot automatically include unknown arbitrary classes in the executable |

Not every `Class.forName` is a blocker. What matters is which class is loaded, whether it can be known ahead of time, and whether corresponding metadata exists.

### 4.2. Resource Loading

Look for operations:

- `ClassPathResource`, `ResourceLoader`, `getResourceAsStream`.
- `ClassLoader.getResource` or `getResources`.
- `ResourceBundle.getBundle`.
- Scanning `classpath*:` or globs in resource directories.
- Template engines, XML schemas, JSON schemas, certificates, locale bundles.

```bash
rg -n "getResourceAsStream|getResource\(|getResources\(|ResourceBundle|getResourceLoader|classpath\*?:" src
```

Resources packaged inside the native image must be identified and retained. Spring AOT or libraries may already register resource hints; only add manual patterns when a resource is not detected. Resources located on the runtime filesystem need to be mounted/copied into the container and checked for read permissions, not solved with classpath hints.

### 4.3. Proxies and AOP

Inventory:

- Spring AOP, `@Transactional`, `@Async`, method security, and caching.
- JDK dynamic proxies via `Proxy.newProxyInstance`.
- CGLIB/Byte Buddy or libraries creating subclasses/proxies.
- Proxies created from an interface list read from runtime configuration.

Spring AOT can generate bytecode proxies for cases Spring recognizes. If application code creates JDK proxies directly, the interface combinations must be determined and registered. If a library generates arbitrary classes at runtime, check the library's support; proxy hints do not solve all forms of bytecode generation.

### 4.4. Serialization and Data Binding

Look for:

- Java serialization: `ObjectInputStream`, `ObjectOutputStream`, `Serializable`.
- Jackson/Gson or custom serializers.
- XML binding, JAXB, YAML mappers.
- Polymorphic type handling, default typing, or class discriminators.
- Models loaded from class names in payloads/configuration.

Frameworks can automatically generate hints for some models discovered via controllers or binding contracts. However, indirectly referenced models, polymorphic subtypes, or Java serialization may require separate metadata. Do not enable reflection for an entire package just to fix one DTO; identify the actual classes and members accessed by the serializer.

### 4.5. JNI, JNA, and Native Libraries

Inventory dependencies using:

- JNI/JNA or the Java Foreign Function and Memory API.
- Native libraries loaded via `System.loadLibrary` or `System.load`.
- Drivers, compression, cryptography, image processing, or database clients with native components.
- `.so`, `.dylib`, `.dll` files and OS/architecture-specific binaries.

Native Image supports JNI with appropriate metadata, but the native library must have a binary compatible with the target OS/architecture/ABI and be packaged properly. A dependency running on HotSpot does not automatically mean its native library is compatible with GraalVM.

### 4.6. Runtime Class Loading, Plugins, and Scripting

This group needs early evaluation:

- Plugin JARs copied into a directory after the application is built.
- `URLClassLoader` or custom class loaders loading classes from filesystem/network.
- Script engines running Groovy, JavaScript, or other languages.
- OSGi/container plugins or extensions discovered at runtime.
- Runtime bytecode generation and dynamic compilation.

A native executable does not have an open JVM classpath to arbitrarily load a new JAR like a typical HotSpot application. If the plugin set is finite, you can switch to compile-time inclusion, a static registry, or build one executable per plugin set. If the product requirement is loading new code post-deploy, treat this as an architectural blocker for standard Native Image migration or keep that service on the JVM.

### 4.7. ServiceLoader, Classpath Scanning, and Framework Discovery

Check `ServiceLoader`, `META-INF/services`, custom component scanning, package scanning, and registries built from resource files. Many frameworks can handle common contracts in AOT, but code that scans the classpath at runtime needs to move to build-time discovery or a static registry.

Spring AOT analyzes bean definitions at build time. If the application registers beans manually after context refresh or relies on dynamic classpath scanning to discover plugins, determine how to move that logic to `BeanDefinitionRegistry`, `ImportBeanDefinitionRegistrar`, or a build-time generated registry mechanism.

### 4.8. Class Initialization and Environment-Dependent State

Check static initializers or singletons created during class initialization:

- Reading environment variables, system properties, or configuration files.
- Resolving DNS, opening sockets, or connecting to databases.
- Creating threads, executors, timers, or native handles.
- Reading timezone, locale, random seed, or clock.
- Loading certificates, secrets, or build-machine-specific paths.

If a class is initialized at build time, values may be captured into the image heap. Separate environment config reading and resource initialization into an appropriate runtime lifecycle; only configure runtime initialization for specific classes after gathering evidence.

### 4.9. Security Providers, Instrumentation, and Tooling

Check libraries depending on:

- Dynamically registered security providers.
- Attach API, instrumentation agents, bytecode transformers.
- JMX or management extensions requiring runtime discovery.
- Profiler/APM agents, coverage agents, hot reload, or dynamic attach.
- Dynamically loaded URL protocol handlers or charset/locale data.

Do not assume all of these features are unsupported. Record the API name, provider/agent, activation timing, and native support for the specific version. An application can run natively while changing how monitoring, profiling, or secrets/certificates are deployed.

## 5. Checking Spring AOT Limitations

Spring AOT does not merely add metadata for GraalVM. It analyzes the `ApplicationContext` at build time and generates code to restore bean definitions according to a known configuration. That creates several constraints to inventory in the existing JVM application.

### 5.1. The Classpath Must Be Fixed

The classpath is fully determined at build time. The application cannot expect to add a new JAR to the classpath after the native executable is built and have Spring discover beans in that JAR.

If you currently deploy by mounting plugin JARs or adding an extension directory, switch to one of these models:

- Include the plugins in the dependency graph before building.
- Build separate artifacts for each known plugin set.
- Replace plugins with a static registry/configuration.
- Keep running that module on the JVM if arbitrary code loading is a core requirement.

### 5.2. `@Profile` and `@Conditional` Are Decided at Build Time

Required profiles must be selected when AOT processing runs. Environment properties that determine whether a bean exists via `@Conditional` are also evaluated at build time.

Example:

```java
@Configuration(proxyBeanMethods = false)
@Profile("production")
class ProductionGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
```

If the native artifact is AOT-processed with the `production` profile, you cannot expect switching to the `sandbox` profile when running the executable to make Spring create a `SandboxPaymentGateway` bean that was excluded from the bean graph at build time.

If multiple bean graph configurations are needed, you can build multiple artifacts per profile or design a stable bean graph and only vary runtime configuration values. Do not use runtime profiles to try to enable a bean that was excluded during AOT.

### 5.3. Bean Registration Must Be Observable by AOT

Beans registered via `registerSingleton` or callbacks that only run after AOT processing may not be converted into generated bean definitions. For dynamic registration, Spring recommends using `BeanDefinitionRegistry` and appropriate extension points such as `ImportBeanDefinitionRegistrar`.

Inventory:

- Custom `BeanFactoryPostProcessor` and `BeanDefinitionRegistryPostProcessor`.
- `ImportBeanDefinitionRegistrar`.
- Beans registered via `registerBeanDefinition` or `registerSingleton`.
- `FactoryBean` and custom instance suppliers.
- Beans created from lambdas/method references without a clear type.

Not all programmatic registration is incompatible. What matters is whether registration happens during an AOT-observable phase and produces a clear bean definition.

### 5.4. Declare Bean Types as Specifically as Possible

Example:

```java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
```

Declaring the return type as `PaymentGateway` may prevent AOT from seeing annotations or callbacks present only on `StripePaymentGateway`. If the actual bean has a concrete type and AOT needs to analyze that type, declare a more specific return type:

```java
@Bean
StripePaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

Only change this when the concrete type is an appropriate part of the bean contract. Do not change public APIs arbitrarily if doing so breaks application abstractions.

### 5.5. Custom Arguments and Constructor Selection

Spring AOT may not infer constructors/factory methods selected from custom arguments passed dynamically at bean creation time. Multiple constructors without a clear preferred constructor also make constructor selection unpredictable.

Inventory beans created with custom arguments, prototype factories, and constructor selection. Consider:

- Marking the preferred constructor with `@Autowired` where appropriate.
- Using a factory bean with an explicit type to create instances.
- Avoiding overly complex bean argument structures constructed manually via `RootBeanDefinition`.
- Providing minimal hints if a library truly needs dynamic introspection/invocation.

### 5.6. Nested Configuration Properties

Spring Boot automatically generates reflection hints for configuration properties recognized by AOT. For nested property types that are separate classes, check `@NestedConfigurationProperty` requirements based on declaration style and Spring Boot version. Missing the annotation can prevent nested properties from binding in a native image even though JVM runtime works.

### 5.7. Custom BeanPostProcessors and Extension Points

Spring AOT does not perform a full refresh like normal runtime. Regular `BeanPostProcessor` implementations are not invoked during AOT processing, except variants supported by Spring for AOT. If a custom processor modifies bean definitions or behavior based on actual instances, determine how to provide an AOT contribution or move the logic to the bean definition registration phase.

Do not assume every callback invoked during JVM startup is also invoked during AOT processing. Check the actual lifecycle and generated code.

## 6. Evaluating Dependency Native Image Support

### 6.1. Check the Reachability Metadata Repository

Look up each key dependency in the [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata). The repository contains community metadata for many libraries so they work with Native Image. GraalVM Native Build Tools can automatically use this metadata during the build.

Evaluate using these questions:

- Is there metadata for the exact artifact/version?
- Does it only support a specific GraalVM/JDK range?
- Is there metadata for all modules of the library or only the core module?
- Does the dependency change behavior across versions?
- Do the project's native tests exercise the features that the metadata supports?

If a library lacks metadata, you don't necessarily have to drop it immediately. You can provide `RuntimeHints`/JSON metadata yourself and contribute it upstream where appropriate. However, if the library requires runtime class loading or unconstrained dynamic code generation, that may be a real blocker.

### 6.2. Check Vendor-Published Native Support

Prioritize official documentation from the dependency vendor:

- Is GraalVM Native Image officially supported?
- Is there a separate native starter/module or artifact?
- Are special features, native libraries, or build arguments required?
- Are there API, protocol, driver, or OS limitations?
- Are there native image CI tests for that version?

A “GraalVM compatible” badge or metadata repository entry is an initial signal, not a substitute for testing in the actual application.

### 6.3. Classify Dependencies

| Status | Criteria | Action |
|---|---|---|
| Green | Official native support or exact-version metadata; representative tests pass | Keep dependency and include in the native regression suite |
| Amber | Can be supported via hints/refactoring/configuration; not yet fully verified | Create an MRE, add tests, and estimate effort |
| Red | Requires arbitrary runtime classpath/plugins, unsupported APIs/tooling, or vendor-confirmed incompatibility | Find an architectural alternative, keep module on JVM, or stop migration |
| Unknown | No documentation or not yet tested | Do not treat as Green; create a scoped spike with a clear deadline |

## 7. Use the Tracing Agent for Discovery, Not as Final Proof

The Tracing Agent runs on the JVM and records reflection, resources, proxies, JNI, and other dynamic operations executed by a scenario. It is useful when you don't know which library is accessing classes/members/resources dynamically.

Example:

```bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent/ \
  -jar target/order-service.jar
```

Then exercise representative business flows: login, order creation, report export, message processing, external API calls, file upload/download, and production-only features. When the process stops, the agent writes metadata to the output directory.

You can run the agent through the test suite, but the output may include metadata for test frameworks, mocks, assertion libraries, or test-only code. You must filter and review it before putting it into a production artifact.

The Tracing Agent only records code paths that are executed. If an export feature is never triggered, the agent cannot know what reflection/resources that feature needs. Therefore:

- Use multiple test scenarios and representative inputs.
- Cover all feature flags and supported profiles.
- Compare agent output against hints provided by Spring AOT and dependencies.
- Remove test-harness-only entries once verified with evidence.
- Run `--exact-reachability-metadata` and native integration tests after consolidating.

## 8. Test AOT on the JVM Before Native Compilation

### 8.1. Maven

With the Spring Boot Maven Parent, create a JAR with AOT assets using the `native` profile:

```bash
./mvnw -Pnative package
```

Then run on the JVM with AOT-generated code:

```bash
java -Dspring.aot.enabled=true -jar target/order-service.jar
```

Ensure the JAR actually contains generated AOT assets. During application startup, logs can confirm that the AOT-processed context is used. Simply enabling the property on a JAR that was not AOT-processed makes the test meaningless.

### 8.2. Gradle

With Gradle, ensure the build applies the Spring Boot Gradle plugin and the GraalVM Native Image plugin:

```groovy
plugins {
    id 'org.springframework.boot'
    id 'org.graalvm.buildtools.native'
}
```

The example assumes plugin versions are already managed in `pluginManagement` or the project's version catalog. When applying the Spring Boot Gradle plugin alongside the GraalVM Native Image plugin, Spring Boot configures the required AOT tasks. After building the executable JAR with AOT assets:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/order-service.jar
```

Versions in examples are illustrative. Use Spring Boot, Gradle, and Native Build Tools versions compatible with your project.

### 8.3. What AOT-on-JVM Can Catch

- Incorrect profile/conditional bean graphs.
- Failing generated initializers or bean registrations.
- Configuration properties failing to bind properly.
- Proxies or custom AOT contributions not generated as expected.
- Startup paths depending on runtime classpath/bean discovery.

AOT-on-JVM does not prove reflection/resource metadata is complete for Native Image. It is an intermediate checkpoint, not a replacement for native builds and native runtime tests.

## 9. Tiered Migration Testing Roadmap

Spring Boot recommends keeping most unit/integration tests on the JVM for fast feedback. Focus native tests on behaviors that may differ in AOT/Native Image.

### 9.1. Tier 1 — JVM Regression Suite

Run the entire existing test suite to ensure migration does not alter business behavior. Retain tests for:

- API contracts and serialization.
- Database transactions and migrations.
- Messaging, retries, and scheduling.
- Security, authentication, and authorization.
- File upload/download, resource loading, and encoding.
- Feature flags, profiles, and conditional configuration.

### 9.2. Tier 2 — AOT-on-JVM Smoke Tests

Run the application or integration tests with generated AOT code. Prioritize startup, bean graph, custom registration, proxies, and configuration.

### 9.3. Tier 3 — Native Build

Build the native executable with exact reachability metadata when supported by your GraalVM version:

```bash
./mvnw -Pnative native:compile
```

Or Gradle:

```bash
./gradlew nativeCompile
```

Record build duration, peak RAM, executable size, and any warnings/errors. If the build fails, classify the error as unsupported API, metadata, class initialization, toolchain, or resource constraint.

### 9.4. Tier 4 — Native Runtime Smoke Tests

Run the executable and verify:

- Startup-to-ready.
- Health/readiness endpoints.
- A critical API flow.
- Database connection and migrations.
- Outbound TLS/DNS.
- Resources/templates/serialization.
- Graceful shutdown and signal handling.

Run inside a container with a base image, libc, user, filesystem permissions, and network policy close to production.

### 9.5. Tier 5 — Native Integration Tests

Select tests for features with dynamic behavior or libraries with native integrations. Native Build Tools native tests can run in CI/nightly rather than forcing every developer to build a native image for every change.

### 9.6. Tier 6 — Performance and Soak Tests

Measure startup-to-ready, RSS, throughput, latency percentiles, and CPU under representative workloads. Check both the warm-up time of the JVM baseline and steady-state behavior of native. Run soak tests to detect leaks or resource lifecycle differences.

## 10. Handling Metadata and Incompatibilities

### 10.1. Add Hints per Feature

If Spring AOT cannot infer required reflection/resource/proxy/serialization, provide a `RuntimeHintsRegistrar` or reachability metadata JSON. Attach hints close to the owning component so metadata does not become an unmaintainable global configuration dump.

Example registering a specific resource:

```java
public class InvoiceRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/invoice.html");
    }
}
```

Do not add classpath-wide wildcards just to make the build pass. Every hint should have a test predicate and a native test proving the code path needs it.

### 10.2. Enable Exact Reachability Metadata

With GraalVM JDK 23 or later, enable exact reachability metadata in Native Build Tools configuration. Maven example:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--exact-reachability-metadata</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

With Gradle:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--exact-reachability-metadata')
        }
    }
}
```

Then build with the corresponding plugin, e.g. `./mvnw -Pnative native:compile` or `./gradlew nativeCompile`.

Run the native executable with:

```bash
./order-service -XX:MissingRegistrationReportingMode=Warn
```

After resolving warnings, run tests with `Exit` to catch metadata errors that code catches and ignores:

```bash
./order-service -XX:MissingRegistrationReportingMode=Exit
```

Option names and behavior may differ on older GraalVM/JDK versions. Check the documentation for your exact version before adding to CI.

### 10.3. Generate Metadata from the Tracing Agent

Metadata collected by the agent can serve as input, but must be reviewed and stripped of test-only entries. If the dependency is a shared library, consider shipping metadata inside the artifact itself or contributing to the Reachability Metadata Repository instead of having every application maintain a copy.

### 10.4. Refactor Dynamic Behavior into Static Contracts

Several changes can typically reduce risk:

| Current pattern | Refactoring direction |
|---|---|
| `Class.forName` from arbitrary property | Registry mapping valid names to build-time-known classes/beans |
| Plugin JAR mounted post-deploy | Include plugins in dependency graph or build artifacts per plugin set |
| Runtime classpath scanning | Perform discovery at AOT/build time and generate a registry |
| Beans registered via `registerSingleton` | Register `BeanDefinition` in an AOT-visible extension point |
| Arbitrary resource path from request | Allowlist resources and register valid patterns |
| Dynamically selected constructor/method | Explicit factory or hints for a finite member set |
| Static initializer reading DNS/files/secrets | Move operations to runtime lifecycle and external configuration |

Do not refactor solely to satisfy Native Image if doing so sacrifices an important product requirement. When runtime extensibility is a core characteristic, keeping that service on the JVM may be the better decision.

## 11. Choosing a Migration Strategy

### 11.1. No Need to Migrate the Entire System at Once

A microservices system can run both JVM and native executables. Choose services by workload and risk:

- Go native first for workers or services with clear cold-start/memory pressure.
- Keep the JVM for plugin hosts or services using arbitrary dynamic class loading.
- Assign shared library and service owners so metadata is maintained in the right module.
- Only migrate services whose dependencies and runtime behavior have been verified.

### 11.2. Two Artifacts in Parallel

During the transition, you can continue publishing both JVM and native artifacts from the same source revision. Use separate pipelines to build/test, tag clearly, and deploy into test environments. This enables comparing behavior/performance and rolling back without forcing the entire organization to switch at once.

Native executables are typically tied to OS/architecture. If deploying to multiple platforms, the pipeline must build separate artifacts or use appropriate packaging for each target. Do not assume a Linux x64 binary will run on Linux ARM64 or Windows.

### 11.3. Traffic Rollout and Rollback Capability

Once the native artifact passes tests:

1. Deploy to an integration/staging environment with production-equivalent traffic and external dependencies.
2. Run smoke, contract, performance, and soak tests.
3. Roll out to a small percentage of instances or a canary service.
4. Monitor startup failures, readiness, error rate, latency, RSS, and restart count.
5. Expand rollout once metrics meet defined thresholds.
6. Keep the JVM artifact and rollback procedure ready during the observation period.

Do not use better startup time as the sole criterion. The native artifact must still meet correctness, throughput, latency, and operational SLOs.

## 12. Risk Matrix and Go/No-Go Criteria

### 12.1. Evaluation Matrix

| Category | Green | Amber | Red |
|---|---|---|---|
| Spring AOT | AOT-on-JVM passes on all supported artifact profiles | Some configurations need refactoring | Bean graph must change arbitrarily at runtime or AOT context cannot be created |
| Dependencies | All key dependencies have tested native support/metadata | Some dependencies need hints or version upgrades | Mandatory dependency relies on unchangeable dynamic code loading |
| Reflection/resource | Access set is finite and has metadata | Not yet covering all feature paths | Needs to load arbitrary classes/resources unknowable at build time |
| JNI/native library | Target-matching binary exists and tests pass | Needs additional building/packaging | No binary or vendor does not support the required target |
| Runtime config | Stable bean graph, runtime config changes within supported scope | Needs multiple artifacts per profile | Must create arbitrary beans/plugins from config post-deploy |
| Testing | JVM, AOT, and native smoke/integration tests all pass | Some features lack native tests | Cannot test or unexplained native failures |
| Performance | Measurable benefit aligned with goals | Minor or unstable benefit | No benefit offsetting build/operational cost |
| CI/CD | Runners/toolchains have sufficient resources and reproducibility | Needs runner upgrade or pipeline split | Cannot build target within acceptable time/cost |

### 12.2. Decision

**Go** when critical dependencies are supported, the bean graph can be fixed at build time, dynamic features have full metadata/tests, native runtime passes, and measurements show benefits matching goals.

**Conditional Go** when some dependencies or features still need work, but owners, effort, tests, and deadlines are clearly defined. Only expand rollout after amber items are closed.

**No-go or keep JVM** when the application requires loading arbitrary plugins/classes post-deploy, essential dependencies lack native solutions, or benefits do not offset operational costs and risks.

Do not treat a successful `native-image` build as proof that migration is complete. Only native runtime tests and workload measurements confirm the artifact is suitable.

## 13. Migration Assessment Profile Template

### 13.1. Application Information

| Field | Value |
|---|---|
| Service/module | _(record)_ |
| Spring Boot / Framework | _(record)_ |
| JDK vendor/version | _(record)_ |
| Build tool/version | Maven / Gradle / _(record)_ |
| Deployment target | Linux x64 / ARM64 / Windows / _(record)_ |
| Runtime profiles | _(record)_ |
| SLO startup-to-ready | _(record)_ |
| Memory limit | _(record)_ |
| Current JVM baseline | _(record)_ |

### 13.2. Dependency Inventory

| Dependency | Version | Native metadata/support | Dynamic feature | Risk | Owner/action |
|---|---|---|---|---|---|
| _(artifact)_ | _(version)_ | Green/Unknown/No | Reflection/JNI/Resource/... | Green/Amber/Red | _(record)_ |

### 13.3. Dynamic Feature Inventory

| Feature | Code/dependency location | Finite class/resource set? | Metadata/refactor | Required tests | Status |
|---|---|---|---|---|---|
| Reflection | _(record)_ | Yes/No | _(record)_ | _(record)_ | Green/Amber/Red |
| Resource loading | _(record)_ | Yes/No | _(record)_ | _(record)_ | Green/Amber/Red |
| Proxy/AOP | _(record)_ | Yes/No | _(record)_ | _(record)_ | Green/Amber/Red |
| Serialization | _(record)_ | Yes/No | _(record)_ | _(record)_ | Green/Amber/Red |
| JNI/JNA/FFM | _(record)_ | Yes/No | _(record)_ | _(record)_ | Green/Amber/Red |
| Class loading/plugin | _(record)_ | Yes/No | _(record)_ | _(record)_ | Green/Amber/Red |
| Class initialization | _(record)_ | Build/runtime | _(record)_ | _(record)_ | Green/Amber/Red |

### 13.4. Testing and Performance Results

| Check | Result | Evidence/link |
|---|---|---|
| JVM regression tests | PASS/FAIL | _(record)_ |
| Spring AOT processing | PASS/FAIL | _(record)_ |
| AOT-on-JVM | PASS/FAIL | _(record)_ |
| Native compilation | PASS/FAIL | _(record)_ |
| Native smoke tests | PASS/FAIL | _(record)_ |
| Native integration tests | PASS/FAIL | _(record)_ |
| Native runtime in container | PASS/FAIL | _(record)_ |
| Exact reachability metadata | PASS/FAIL/N/A | _(record)_ |
| Startup-to-ready | _(record)_ | _(record)_ |
| RSS steady state | _(record)_ | _(record)_ |
| Throughput/p95 latency | _(record)_ | _(record)_ |
| Build duration/runner peak | _(record)_ | _(record)_ |

### 13.5. Migration Conclusion

| Question | Conclusion |
|---|---|
| Can classpath and bean graph be fixed? | Yes / No / Conditional |
| Are there unchangeable dynamic features? | Yes / No |
| Are there dependency blockers? | Yes / No |
| Are there metadata/refactor solutions for Amber items? | _(record)_ |
| Does native runtime meet functional requirements? | Yes / No |
| Does native meet SLO/performance targets? | Yes / No |
| Are CI/maintenance costs acceptable? | Yes / No |
| Decision | GO / CONDITIONAL GO / NO-GO |
| Owner and milestone | _(record)_ |

## 14. Hands-on Exercise: Assessing a JVM Service Before Migration

**Context:** `order-service` is a Spring Boot application currently running on the JVM. The service uses Web, Security, JPA, PostgreSQL, Flyway, Jackson, a PDF library, and an export plugin selected via a property.

### Step 1 — Capture Baseline

Record startup-to-ready, RSS, throughput, p95/p99 latency, image size, and build duration of the JVM artifact in a representative environment.

### Step 2 — Build Dependency Inventory

Run `dependency:tree` or Gradle `dependencies`. Look up metadata/native support for the PostgreSQL driver, Flyway, the PDF library, and key dependencies. Record versions and owners.

### Step 3 — Inventory Dynamic Features

Search for reflection, resource loading, proxies, serialization, JNI, ServiceLoader, and plugin class loading. Determine whether the export plugin is a finite build-time set or allows arbitrary JARs to be added post-deploy.

### Step 4 — Check Spring AOT Constraints

Check the `production` profile, `@Conditional` annotations, programmatic bean registration, `registerSingleton`, custom suppliers, and `@Bean` return types. Record configurations that must be fixed at build time.

### Step 5 — Run AOT-on-JVM

Build a JAR with AOT assets and run it with `-Dspring.aot.enabled=true`. Run regression tests for API, database, security, and export.

### Step 6 — Build Native Spike

Create a native executable for the exact target OS/architecture. Use exact reachability metadata and run export, database, TLS, and resource flows. Record warnings, required metadata additions, and build duration.

### Step 7 — Measure Native Runtime

Run the native container with the same memory limit and workload as the JVM. Compare startup-to-ready, RSS, throughput, latency, and CI cost.

### Step 8 — Decide

If the export plugin is only a finite set, register it at build time or build artifacts per plugin set. If plugin JARs must be added arbitrarily post-deploy, mark this as a blocker for that service or keep the JVM. Record GO/CONDITIONAL GO/NO-GO along with owner and effort.

### Result Sheet

| Item | Result to record |
|---|---|
| Dependency inventory completed | PASS/FAIL |
| Dynamic feature inventory completed | PASS/FAIL |
| Spring AOT constraints evaluated | PASS/FAIL |
| Metadata gaps identified | PASS/FAIL |
| AOT-on-JVM | PASS/FAIL |
| Native build | PASS/FAIL |
| Native runtime tests | PASS/FAIL |
| Performance comparison | PASS/FAIL |
| Migration decision | GO / CONDITIONAL GO / NO-GO |

## 15. Key Takeaways

A Native Image migration assessment starts with an application inventory, not by swapping the build command. Record dependencies and versions, profile/conditional beans, dynamic features, native libraries, class initialization, and runtime environment. Distinguish dynamic features describable via metadata from requirements to load arbitrary code post-deploy.

Spring AOT requires the classpath and bean graph to be determined at build time; profiles and conditions affecting bean creation are decided then as well. Native Image needs reachability metadata for dynamic accesses that static analysis cannot infer. Use AOT-on-JVM, native builds, native integration tests, and workload measurements in layers. Migrate only when the application meets correctness, operational, and economic criteria; keeping the JVM for modules with incompatible dynamic runtime requirements is a valid choice.

### Official References

- [Spring Framework — Ahead-of-Time Optimizations and Restrictions](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Boot — Advanced Native Images Topics and Known Limitations](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Boot — GraalVM Native Image Support](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Collect Metadata with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/)
- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata)
- [Spring AOT Smoke Tests](https://github.com/spring-projects/spring-aot-smoke-tests)
