# Limitations of Static Analysis With Reflection, Configuration, and Dynamically Loaded Classes

During Java compatibility assessments, static analysis is an effective way to find dependencies, deprecated APIs, references to JDK internal APIs, and code fragments at risk when upgrading versions. However, static analysis results do not show everything the application actually loads and executes. Reflection, external configuration, and dynamic class loading can create dependencies invisible to tools inspecting ordinary source code or bytecode.

This matters especially when migrating across Java versions. An application may have zero direct references to a class or API in source code, yet still look up classes by names read from config files, invoke methods via reflection, load plugins from external directories, or receive implementations from `ServiceLoader`. Relying solely on scan reports can cause development teams to miss components needing upgrades or misjudge runtime compatibility.

## 1. What Does Static Analysis Tell You and What Does It Miss?

Static analysis inspects source code, bytecode, configs, or dependencies without executing the application through real business flows. Depending on the tool, analysis can find:

- Call relationships and class/package references inferable from source or bytecode.
- Direct and transitive dependencies declared in the build.
- Calls to deprecated Java APIs or internal APIs with static references.
- Certain code defects, data flows, access rights, and module structures.
- Strings or class names appearing inside source files and scanned resources.

Results depend on the inputs and model used by the tool. If a config file lies outside scan scope, a JAR downloaded from an external server sits outside the dependency graph, or a class name is concatenated only at runtime, the tool may fail to identify that dependency.

Distinguish three concepts:

| Concept | Meaning | Example |
| --- | --- | --- |
| Static reference | Directly visible in source or bytecode | `new com.example.Driver()` or calling `Driver.connect()`. |
| Declared dependency | Present in build files, module descriptors, or metadata | Maven dependency in `pom.xml`, Gradle `runtimeClasspath`. |
| Runtime-loaded dependency | Appears only when processing configs, reflection, plugins, or services | Class name read from `driver.class` in a properties file. |

These three sets overlap yet do not necessarily coincide. A class may be declared as a dependency yet never loaded; another class may be loaded from a plugin directory or external repository absent from the build's dependency graph.

### 1.1. Why Can Call Graphs Be Incomplete?

Static call graphs usually rely on rules inferable from source or bytecode. Direct calls like `service.process()` are far easier to analyze than calls whose target object is resolved only at runtime.

Example:

```java
PaymentService service = new CardPaymentService();
service.pay(order);
```

Here, the implementation type can be inferred from instantiation, though polymorphism still requires analyzing subtypes to identify all possible implementations.

Conversely:

```java
String implementation = settings.getProperty("payment.service.class");
Class<?> type = Class.forName(implementation);
Object instance = type.getDeclaredConstructor().newInstance();
```

The actual class depends on the value of `payment.service.class`. If that value comes from a config file, environment variable, database, or remote configuration service, source code alone cannot determine the exact implementation.

A tool may spot the `Class.forName` call, yet detecting the call does not mean knowing which class gets loaded in each environment.

## 2. Reflection Creates Hard-to-See Dependencies

Reflection lets a program discover classes, constructors, fields, methods, and annotations at runtime. It is heavily used by frameworks, ORMs, dependency injection, serializers, test frameworks, and plugin libraries.

### 2.1. Loading Classes by String Name

Common APIs include:

```java
Class.forName("com.example.Driver");
ClassLoader.getSystemClassLoader().loadClass("com.example.Driver");
Thread.currentThread()
      .getContextClassLoader()
      .loadClass("com.example.Driver");
```

String-based class names do not produce direct class references like `new Driver()`. A bytecode scanner can detect the `Class.forName` call without necessarily determining the string's value at runtime.

Class names can also be assembled from multiple pieces:

```java
String className = "com.example." + providerName + "." + "Client";
Class<?> clientType = loader.loadClass(className);
```

If `providerName` is read from configuration, a database, or data returned by an external system, the complete class name never appears as a literal in source code.

### 2.2. Invoking Methods and Constructors via Reflection

An application can look up a method by name and invoke it without a direct method call:

```java
Class<?> type = Class.forName("com.example.LegacyAdapter");
Object adapter = type.getDeclaredConstructor().newInstance();

Method method = type.getMethod("initialize", String.class);
method.invoke(adapter, "production");
```

Static analysis can spot the `LegacyAdapter` string and method name in this example. However, if values arrive from configuration or dynamic concatenation, determining the actual implementation and signature grows harder. Methods can also be selected by annotations, operation names, or input data.

Notable APIs:

- `Class.forName`, `ClassLoader.loadClass`.
- `Class.getMethod`, `Class.getDeclaredMethod`.
- `Class.getConstructor`, `Class.getDeclaredConstructor`.
- `Method.invoke`, `Constructor.newInstance`.
- `Field.get`, `Field.set`, `AccessibleObject.setAccessible`.
- `MethodHandles.Lookup`, `MethodHandle.invoke`, and `invokeExact`.

Not every use of reflection is dangerous or unanalyzable. When class names and signatures are constants in source, tools can recover part of the relationship. Limitations arise when values depend on external data, runtime branches, or metadata the scanner does not understand.

### 2.3. Reflection Through Frameworks

An application might never invoke `Class.forName` directly while a framework does so on its behalf. Examples:

- ORMs locating entities, converters, listeners, and callbacks via annotations or configs.
- Dependency injection containers scanning packages and instantiating implementations.
- JSON/XML serializers locating constructors, getters, setters, or fields from metadata.
- Web frameworks loading controllers, filters, interceptors, and providers.
- Test frameworks locating test classes, extensions, or test engines.
- Logging frameworks locating matching implementations or plugins.

During a JDK upgrade, failures may erupt inside framework libraries rather than business source code. Thus, finding no reflection in application code does not prove the application uses no reflection.

### 2.4. Proxies and Runtime-Generated Classes

Some frameworks generate implementations or proxies at runtime:

```java
Object proxy = Proxy.newProxyInstance(
    interfaceType.getClassLoader(),
    new Class<?>[] { interfaceType },
    invocationHandler
);
```

The JVM synthesizes a proxy class implementing the interface. Libraries like Byte Buddy, CGLIB, Javassist, or ASM can also emit bytecode and load new classes at runtime.

Bytecode scanners inspect only classes already present in input artifacts. They cannot thoroughly analyze classes generated after application startup without understanding the generator, configuration, and input data. Compatibility bugs may lurk in how a generator emits bytecode or how a class loader defines the class.

## 3. External Configuration Can Hide Dependencies

### 3.1. Class Names and Implementations in Config Files

Many applications allow swapping implementations without editing source code:

```properties
storage.provider.class=com.example.storage.S3StorageProvider
database.driver.class=com.vendor.jdbc.Driver
serializer.class=com.example.json.LegacySerializer
```

In development, configs might point to a mock implementation; in production, a completely different driver or adapter is used. Scanning only source code and build files leaves the scanner blind to all classes needing checks.

Configuration sources to examine include:

- `.properties`, YAML, XML, JSON, and custom application config files.
- Environment variables and Java system properties.
- Command-line flags and JVM options.
- Config maps, secrets, volume mounts, and container environment settings.
- Databases, configuration tables, feature flags, and remote config services.
- Configuration supplied by application servers, plugin managers, or deployment platforms.

Never assume config files committed in the repository are the sole configs used in production. Identify the final effective configuration source and precedence order when multiple sources define the same key.

### 3.2. Profiles and Configuration Branches

An application may have `dev`, `test`, `staging`, `production`, or customer-specific profiles. Each profile can activate different implementations and dependencies.

Example:

```yaml
storage:
  provider: local

---
spring:
  config:
    activate:
      on-profile: production
storage:
  provider: cloud
```

This is merely an example of profile-based configuration. Real configs may assemble from multiple files or external sources. Scanning only the default config can miss classes used exclusively in production.

List all supported profile combinations and record effective configuration values for each combination. If a sensitive config source cannot be accessed directly, use a secret-redacted copy that preserves class names, provider names, and values governing component loading.

### 3.3. XML Configuration and Framework Class Names

Some legacy frameworks declare classes in XML:

```xml
<bean id="paymentGateway"
      class="com.example.payment.LegacyGateway" />
```

The class name does not necessarily appear in Java source. Config files may sit inside JARs, deployment directories, or be generated during builds. During migration, scan both packaged resources inside artifacts and deployment-environment configs.

### 3.4. Configuration From Databases or Remote Services

Some systems store implementation names in database tables or fetch them from remote configuration. Static repository scans cannot know the active values of those records reliably.

Investigation workflows should:

1. Identify the tables, APIs, or services providing configuration.
2. Retrieve the list of active class/provider values in each environment.
3. Strip or mask sensitive data while keeping values needed for analysis.
4. Map each value to the artifact or dependency providing that class.
5. Verify rarely used values that remain within support scope.

If production configurations cannot be collected, explicitly mark that area unverified and require the system owner to confirm before declaring migration complete.

## 4. Dynamically Loaded Classes and Out-of-Build Dependencies

### 4.1. `ClassLoader` and Context Class Loader

Java uses class loaders to load classes into the JVM. Class loaders can form parent/child hierarchies with differing delegation policies.

Applications may use:

- The JVM's bootstrap/platform/application class loaders.
- Class loaders managed by an application server or servlet container.
- `URLClassLoader` loading JARs from a plugin folder.
- Custom class loaders loading classes over the network, from archives, or byte arrays.
- Thread context class loader (TCCL) allowing libraries to discover implementations in thread context.

Example:

```java
URL[] pluginUrls = {
    Path.of("plugins/payment-plugin.jar").toUri().toURL()
};

try (URLClassLoader pluginLoader = new URLClassLoader(
        pluginUrls,
        Thread.currentThread().getContextClassLoader())) {
    Class<?> pluginType = pluginLoader.loadClass("com.example.PaymentPlugin");
    Object plugin = pluginType.getDeclaredConstructor().newInstance();
}
```

JARs inside `plugins/` may never be declared in Maven/Gradle. If a scanner inspects only the build dependency graph, this plugin will not appear. Inspect plugin directories, installation workflows, manifests, class loader settings, and JAR loading origins.

### 4.2. Service Provider Interface and `ServiceLoader`

SPI lets an API consume implementations discovered at runtime. On the classpath, providers are commonly declared in `META-INF/services/<service-interface>` resources.

Usage example:

```java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    provider.initialize();
}
```

Source code references only `PaymentProvider`; implementations may be declared in a separate JAR. Therefore, inspect:

- `META-INF/services/*` files across runtime JARs.
- Dependencies supplying providers.
- The TCCL passed to `ServiceLoader` if the app calls that overload.
- `uses` and `provides` clauses in `module-info.java` when using named modules.
- Which provider is actually chosen when multiple implementations coexist.

A provider can exist on the classpath yet go undiscovered if class loader delegation or resource visibility is misconfigured. Conversely, dropping a plugin JAR at runtime can introduce a new provider unknown to build scans.

### 4.3. Plugin Directories and Externally Loaded Libraries

Plugin-based systems typically load JARs from configured directories like `plugins/`, `extensions/`, `lib/custom/`, or an internal repository. These JARs can update independently of the application artifact.

Identify:

- Plugin directories and JAR discovery rules.
- How plugin versions and plugin dependencies are tracked.
- Parent/child class loaders and class sharing across plugins.
- Whether plugins can be installed, removed, or updated while the application is running.
- Processes controlling JAR provenance and integrity.

Every plugin needs a compatibility contract: minimum Java version, host API version used, dependency versions, and test scope. If plugins load after application startup, inspecting startup logs once may be insufficient.

### 4.4. Loading Native Libraries and JNI

Java code may call:

```java
System.loadLibrary("nativecodec");
```

Native libraries are not Java classes yet remain mandatory runtime components. Compatibility depends on OS, architecture, ABI, native build toolchain, and library lookup paths.

Java static analysis can spot `System.loadLibrary` calls, yet cannot pinpoint which native file will be resolved if paths are configured externally. Inspect native libraries bundled inside JARs, installation folders, environment variables, and deployment images.

### 4.5. Remotely Loaded or Generated Bytecode

Some systems synthesize classes from schemas, expressions, scripts, or runtime data. Others download plugins or bytecode from remote stores. These classes do not exist in the source tree for scanners to analyze.

During migration, identify:

- Which component generates bytecode and its version.
- Which class-file version is generated.
- Which platform APIs the generated bytecode references.
- How classes are defined and attached to class loaders/modules.
- Caching, updating, and invalidation lifecycles for generated classes.

If a generator or bytecode library lacks JDK 11 support, failures may appear only on one specific business branch after class generation runs.

## 5. Why Can Static Analysis Tools Miss These Dependencies?

### 5.1. Unknown Runtime Configuration Values

A scanner can find `Class.forName(config.get("adapter.class"))`, yet cannot know `adapter.class` in production if configuration resides in a database or remote service. Even when config files live in the repository, effective values may be overridden by environment variables or JVM properties.

### 5.2. Inability to Infer All Dynamically Constructed Class Names

Class names can be assembled from packages, tenants, driver types, or feature flags. Static scanners generally cannot simulate every value flowing through the system. Reflection may also sit wrapped inside a third-party library so application source contains no direct call.

### 5.3. Dependency Graphs Do Not Cover Every JAR Source

Maven/Gradle describe dependencies known to the build. JARs copied manually onto servers, mounted via volumes, downloaded at runtime, or installed by plugin managers lie outside this graph.

### 5.4. Bytecode Analysis Inspects Only Input Artifacts

`jdeps` and bytecode scanners analyze classes inside the artifacts and dependencies passed to the tool. They cannot know classes synthesized at runtime, fetched over the network, or added post-deployment.

### 5.5. Not Executing Every Profile and Business Flow

A rarely exercised config branch may harbor an incompatible dependency. Static scans can miss config-driven class names; dynamic tests can also miss them unless the matching profile, plugin, or business workflow is activated.

### 5.6. Detecting a Call Does Not Identify the Implementation

Finding `ServiceLoader.load`, `Class.forName`, or `Method.invoke` proves only that a dynamic loading/invocation mechanism exists. Learning which class actually runs requires combining effective configuration, provider metadata, runtime logs, and tests across supported configurations.

## 6. Combining Static Analysis With Runtime Verification

Do not discard static analysis just because it has limits. Static analysis still narrows investigation scope and catches many errors early. Use it to build a verification checklist, then supplement with configuration and runtime evidence.

### 6.1. Inventorying Dynamic Loading Sites

Search for common APIs and patterns:

```bash
rg -n "Class\.forName|loadClass\(|getDeclaredMethod|getDeclaredField|setAccessible|Method\.invoke|ServiceLoader|URLClassLoader|defineClass|loadLibrary|ScriptEngineManager|Proxy\.newProxyInstance" .
```

Also search for class or provider names inside resources:

```bash
rg -n "\.class|provider|driver|adapter|implementation|plugin|className" config src resources
```

Adjust paths to match your repository. Text searches can return false positives and miss values stored outside the repository; classify every hit carefully.

### 6.2. Inspecting Effective Configuration by Environment

For each environment or profile, build a table:

| Config key | Source | Effective value | Class/implementation to check |
| --- | --- | --- | --- |
| `payment.provider.class` | Config file / environment | Actual class name | Payment provider |
| `database.driver` | Secret / config service | Driver name | JDBC driver |
| `serializer.type` | Application profile | Serializer type | Serializer implementation |
| `plugin.directory` | JVM property / mount | Directory path | Loaded plugin JARs |

Never put secrets or credentials into reports. Keep only the values needed to identify classes, dependencies, profiles, and artifact paths.

### 6.3. Checking SPI and Metadata Inside JARs

List provider resources inside runtime JARs, checking `META-INF/services`, manifests, `Automatic-Module-Name`, and module descriptors if present. For a specific JAR, use:

```bash
jar tf path/to/library.jar
jar --describe-module --file path/to/library.jar
```

Compare declared providers against the implementation actually chosen. When multiple JARs provide the same service, classpath order and class loaders can alter the outcome.

### 6.4. Observing Loaded Classes at Runtime

JDK 11 supports unified JVM logging. Enable class-loading logs in a test environment:

```bash
java -Xlog:class+load=info -jar application.jar
```

Logs reveal loaded classes and their load origins during that run. Filter logs by package or class afterward to trim volume.

On JDK 8, a common approach is:

```bash
java -verbose:class -jar application.jar
```

Compare JDK 8 and JDK 11 logs to spot classes no longer found, classes coming from different JARs, or class loader differences. Note that runtime logs reflect only executed paths; they do not prove every profile, plugin, or business branch was exercised.

### 6.5. Recording Class Origin Inside the Application

When deeper investigation is needed, print an implementation's class loader and `CodeSource`:

```java
static void printClassOrigin(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    var protectionDomain = type.getProtectionDomain();
    var codeSource = protectionDomain == null
            ? null
            : protectionDomain.getCodeSource();

    System.out.println("class=" + type.getName());
    System.out.println("loader=" + loader);
    System.out.println("source=" +
            (codeSource == null ? "unknown" : codeSource.getLocation()));
}
```

This is a diagnostic technique; avoid enabling verbose origin logging unconditionally in production if it leaks paths or floods logs. For dynamically generated classes or classes loaded from special sources, `CodeSource` may lack a value; pair with custom class loader logs.

## 7. Evaluating Results and Limits of Evidence

Classify findings by certainty level, avoiding turning a single warning into a blanket failure claim or one clean run into a compatibility promise.

| Evidence level | Meaning | How to record |
| --- | --- | --- |
| Statically confirmed | Explicit reference in source/bytecode or dependency metadata | Record class/API, reference location, and associated artifact. |
| Config-confirmed | Class/provider name appears in environment effective configuration | Record config source, profile, and secret-masked value. |
| Runtime-observed | Class actually loaded during a concrete run | Record logs, JDK, profile, business flow, and class origin. |
| Scenario-verified | Build/test or business test passed under a defined setup | Record JDK version, artifact, environment, and test outcome. |
| Unverified | Insufficient config, artifacts, or scenarios to conclude | Explicitly state missing data and owner needed to confirm. |

A warning-free `jdeps` run shows only that the tool found none of the dependency kinds it looks for in the supplied inputs. It does not prove zero reflection, dynamic class loading, config-driven dependencies, or internal API access via another path.

Likewise, class-loading logs missing suspicious classes prove only that those classes were not loaded during that logged run. Exercise all supported profiles and business flows, and inspect plugins that may install or activate after startup.

## 8. Practical Investigation Workflow in Migration Projects

### Step 1: Define Runtime Scope

List services, artifacts, modules, profiles, environments, application servers, plugin directories, and operational components. Clarify which components are mandatory, optional, or test-only.

### Step 2: Collect Source, Dependencies, and Configuration

Gather the runtime configuration's dependency tree, resources packaged in JAR/WAR files, `META-INF/services` files, module descriptors, manifests, config files, and per-environment effective values. When configs reside outside the repository, coordinate with environment owners to get secret-redacted copies.

### Step 3: Locate Reflection and Dynamic Loading Sites

Search for `Class.forName`, `loadClass`, `Method.invoke`, `setAccessible`, `MethodHandles`, `ServiceLoader`, `URLClassLoader`, `defineClass`, `System.loadLibrary`, and frameworks performing component scanning. Cross-reference every site with real configurations and libraries.

### Step 4: Determine Class Origins

For every configured or observed implementation, record class name, class loader, source JAR, artifact version, profile, and owning component. Check whether the JAR belongs to the dependency graph or loads from an external source.

### Step 5: Verify Target JDK Compatibility

Analyze bytecode, platform APIs, module access, dependencies, and runtime requirements. For external components, consult vendor support docs for the exact version. Pay special attention to frameworks using reflection, plugins, providers, and native libraries.

### Step 6: Add Tests for Uncovered Paths

Activate each profile and provider, run business workflows hitting rare plugins or implementations, inspect class-loading logs, and verify outcomes. If a branch cannot be activated, explicitly document the gap instead of marking it verified.

### Step 7: Maintain a Dynamic Dependency Inventory

Add dynamically loaded classes/providers to project dependency documentation. Whenever adding plugins or changing configured class names, update the inventory and matching tests so assessment results stay current.

## 9. Report Template for a Finding

A finding regarding reflection or dynamic loading should carry enough detail for others to reproduce and resolve it:

| Field | Content |
| --- | --- |
| Finding ID | ID or ticket key |
| Component | Service, module, or plugin |
| Loading point | Reflection API, `ServiceLoader`, custom class loader, or framework |
| Class/provider | Identified implementation name or config value |
| Source | JAR, dependency, plugin directory, remote config, or other origin |
| Configuration | Activated environment/profile |
| Evidence | Source location, secret-redacted config, dependency metadata, runtime log |
| Tested JDK | JDK version and vendor |
| Outcome | Passed, failed, warning, or unverified |
| Action | Upgrade library, fix config, add tests, or investigate further |
| Owner | Responsible team and target date |

Example conclusion write-up:

> The payment service loads `com.vendor.payment.FastProvider` via `ServiceLoader`. The provider resides in `payment-fast-provider.jar`, mounted into the production plugin directory and absent from the build dependency tree. The class was observed in class-loading logs when running the production profile on JDK 11. Verify plugin version compatibility with the vendor and add it to the deployment test matrix.

Conclusions must state what was observed, observation scope, and what remains unverified. Never generalize from one profile to all environments.

## 10. Security Risks of Dynamic Class Loading

Loading classes by name from configuration makes applications extensible, yet creates security risk if untrusted actors can alter config values or JAR contents.

Measures to consider:

- Allow only implementations on an approved package/class allowlist.
- Verify plugin origin, signatures, or checksums per organizational policy.
- Restrict write permissions on plugin directories and runtime configuration.
- Never take class names directly from user input and load them arbitrarily.
- Log class name, source JAR, and version whenever a plugin loads.
- Enforce approval and compatibility testing workflows before deploying new plugins.

Class loading is not a security sandbox. If a plugin runs in the same JVM as the application, treat it as code with execution privileges inside the process and govern its provenance accordingly.

## 11. Survey Completion Criteria

- [ ] Located reflection and dynamic class-loading sites in source code and frameworks.
- [ ] Collected effective configurations across relevant environments/profiles.
- [ ] Checked runtime dependencies, `META-INF/services`, module descriptors, and out-of-build plugin JARs.
- [ ] Identified class loaders and artifact sources of critical implementations.
- [ ] Combined static scan results with class-loading logs and runtime testing.
- [ ] Exercised supported profiles, providers, and business workflows.
- [ ] Distinguished static findings, config findings, runtime observations, and scenario-verified checks.
- [ ] Documented unverified branches and owners of missing data.
- [ ] Updated dynamic dependency inventories and tests when adding or swapping plugins/providers.

Static analysis remains a valuable foundation for migration surveys, yet cannot replace understanding configuration and runtime observation. Bringing reflection, configuration, and dynamic class loading into scope gives development teams a far truer picture of which classes actually participate in the application and which dependencies must be verified on the target Java version.
