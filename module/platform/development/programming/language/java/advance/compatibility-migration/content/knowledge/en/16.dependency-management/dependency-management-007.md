# Shading, relocation, and the impact on reflection or service metadata

In large Java systems, an application may use multiple libraries requiring different versions of the same dependency. Version conflicts occur when the classpath provides only one version of a class while multiple components expect different signatures or behaviors. When library versions cannot be unified, development teams sometimes use **shading** and **relocation** to package dependencies into an artifact and change the namespace of classes.

This solution is useful, yet also introduces risks when upgrading the JDK, upgrading frameworks, or changing the class-loading model. **Reflection, ServiceLoader, `META-INF/services` files, manifests, and class-name-based metadata** may not be updated in sync with bytecode. An application may compile successfully and pass basic unit tests yet still fail when a particular plugin, driver, or provider is activated in production.

This lesson belongs to the **Dependency Management** chapter in the **Java Advance Compatibility Migration** module. The focus is understanding the difference between shading and relocation, identifying boundaries that renaming does not automatically handle, using packaging tools within the proper scope, and verifying the artifact after transformation.

## 1. Learning outcomes

After this lesson, learners can:

- Distinguish fat JARs, shading, relocation, dependency exclusion, version alignment, and class-loader isolation.
- Explain how relocation alters class/package names in bytecode.
- Identify risks from `Class.forName`, custom class loaders, annotations, and configurations containing class names.
- Explain the SPI/`ServiceLoader` mechanism and why `META-INF/services` must be merged and transformed appropriately.
- Inspect special resources: manifests, Spring metadata, logging plugin caches, resource bundles, JNI, and multi-release JARs.
- Understand configuration examples for Maven Shade Plugin and Gradle Shadow along with the limits of resource transformers.
- Assess impacts on public APIs, binary compatibility, JPMS, Java serialization, and SBOMs.
- Establish a migration workflow with reporting, runtime testing, and rollback capability.

## 2. Why does the need for shading arise?

### 2.1. Dependency conflicts on the classpath

Suppose an application has the following dependencies:

```text
payment-service
├── gateway-sdk
│   └── com.vendor:json-core:1.x
└── report-sdk
    └── com.vendor:json-core:2.x
```

Both versions provide `com.vendor.json.Parser`. An ordinary class loader does not create two independent versions of a class solely from Maven coordinates. When the build tool selects one version, a component may find at runtime that the method signature it expects does not exist.

Symptoms may include:

- `NoSuchMethodError` if the target method signature is missing in the actual class.
- `NoClassDefFoundError` when a class exists in only one version of the dependency.
- `IllegalAccessError` or other errors due to API/runtime changes.
- Silent incorrect behavior if a method keeps its name yet has different semantics.
- Class-loading errors when a plugin or application server loads JARs in a different order.

It is important to determine **which JAR each class is actually loaded from**; the build-time dependency tree does not always reflect the entire runtime, especially with containers, agents, or manually installed libraries.

### 2.2. Shading should not be the immediate first choice

Before using shading, consider:

1. **Version alignment:** upgrade SDKs to versions that share a supported common dependency.
2. **Dependency management/constraints:** choose a shared version after confirming compatibility.
3. **Exclusion:** remove redundant or unnecessarily duplicated dependencies.
4. **Replacing APIs or updating frameworks:** drop old library versions that truly no longer support the target JDK.
5. **Class-loader isolation:** if using a plugin/application-server model that allows loading separate versions while keeping a stable shared API.
6. **Shading + relocation:** when the approaches above are not feasible and there is a clear reason to maintain two separate namespaces.

Shading does not fix bugs in the underlying dependency. If an older version has a vulnerability or does not support the new JDK, renaming its package does not make the code secure or compatible.

## 3. Distinguishing fat JAR, shading, and relocation

### 3.1. Fat JAR or uber JAR

A fat JAR is a JAR containing application code and the contents of multiple dependencies:

```text
application-all.jar
├── com/example/app/Main.class
├── com/vendor/json/Parser.class
├── com/vendor/codec/Encoder.class
└── META-INF/...
```

This technique simplifies distribution. However, if two dependencies both contain the entry `com/vendor/json/Parser.class`, the tool must resolve the duplicate entry. Merely merging JARs does **not** allow two versions of a class to coexist.

### 3.2. Shading

In the Java build ecosystem, *shading* generally refers to bundling dependencies into the packaged artifact, potentially alongside class filtering, resource merging, and package renaming steps.

**Shading does not automatically imply relocation.** It is possible to create a shaded/fat artifact where every package keeps its original name. Isolating namespaces usually requires explicitly declaring relocations.

### 3.3. Relocation

Relocation renames packages/classes and the bytecode references recognized by the plugin.

Example:

```text
Before:
  com.vendor.json.Parser
  com.vendor.json.Node

After:
  com.example.payment.internal.shaded.json.Parser
  com.example.payment.internal.shaded.json.Node
```

As a result:

```text
gateway-sdk  --> com.example.payment.internal.shaded.json.Parser (1.x)
report-sdk   --> com.vendor.json.Parser                         (2.x)
```

These two `Parser` versions are now **two distinct Java types**. This creates an important limitation: an object of the relocated type cannot be used as an object of the unrelocated type simply because both implementations originated from the same source library.

### 3.4. Comparing options

| Technique | Benefit | Limitation |
| --- | --- | --- |
| Alignment | Reduces number of versions to maintain. | Consumers may be incompatible with a single shared version. |
| Exclusion | Removes redundant or wrong dependencies. | Can leave libraries missing required classes. |
| Fat JAR | Convenient single-artifact deployment. | Does not resolve duplicate class names by itself. |
| Shading | Packages and transforms artifacts. | Can drop or corrupt resources. |
| Relocation | Creates isolated namespaces. | Does not automatically rewrite every class name inside data. |
| Class-loader isolation | Isolates versions per loader. | Shared APIs and objects crossing boundaries remain complex. |

## 4. Relocation modifies bytecode, but not all data

### 4.1. Bytecode references that are recognized

An appropriate relocation tool typically handles elements such as:

- Class names inside class files and `.class` entry paths.
- References to superclasses, interfaces, fields, and methods.
- JVM descriptors containing class names.
- Certain generic signatures and annotations containing type references.
- Structured metadata specifically supported by that plugin.

Source example:

```java
import com.vendor.json.Parser;

Parser parser = new Parser();
```

The compiler places the class reference into bytecode in a structure the tool can analyze. After relocation, the call can reference `com.example.payment.internal.shaded.json.Parser`.

The exact transformation scope depends on the plugin version and class-file format. When upgrading the JDK, the bytecode-processing plugin must also support the target JDK's class-file version.

### 4.2. Class-name strings that are not type references

Consider:

```java
String providerName = configuration.getProperty("parser.provider");
Class<?> providerType = Class.forName(providerName);
Object provider = providerType.getDeclaredConstructor().newInstance();
```

The value of `parser.provider` may reside in a production configuration file, environment variable, or database. The build plugin cannot know what it is in each environment.

Even when the class name is a string literal:

```java
Class.forName("com.vendor.json.FastParser");
```

do not assume every plugin/version will automatically rewrite string constants. Some tools have mechanisms to rewrite certain strings; other configurations may leave them untouched to avoid breaking non-FQCN data. **Test the actual artifact and real execution scenarios.**

### 4.3. Other locations containing class/package names

```text
Bytecode:
  Lcom/vendor/json/Parser;

Configuration:
  parser.provider=com.vendor.json.FastParser

SPI resource path:
  META-INF/services/com.vendor.spi.ParserProvider

SPI resource body:
  com.vendor.impl.DefaultParserProvider

Resource:
  com/vendor/json/defaults.properties

Serialized payload:
  {"@class":"com.vendor.json.Parser"}

JNI binding:
  native function names based on Java package/class
```

You cannot assume a single package-renaming rule will automatically handle all of the locations above. Choose a migration strategy for each kind of metadata.

## 5. Reflection and dynamic class loading after relocation

### 5.1. Why does `Class.forName` fail?

Suppose the JAR before relocation contains:

```text
com.vendor.json.FastSerializer
```

A properties file contains:

```properties
serializer.class=com.vendor.json.FastSerializer
```

After relocation, the JAR only contains:

```text
com.example.payment.internal.shaded.json.FastSerializer
```

If configuration has not been updated, the call:

```java
Class<?> type = Class.forName(
        settings.getProperty("serializer.class"));
```

can throw `ClassNotFoundException`. No ordinary Java call makes the build plugin automatically update class names sitting in external configuration files.

### 5.2. Reflection through frameworks

An application that does not call `Class.forName` directly may still rely on reflection through:

- Dependency injection containers.
- ORMs and entity scanning.
- Serializers/deserializers.
- Proxy/AOP frameworks.
- Web frameworks and annotation scanning.
- Test frameworks, mocking tools, or bytecode generators.
- Plugin managers.

If the scanned package is `com.vendor.json`, relocated classes may vanish from the scan scope. If annotations contain FQCN strings, the plugin may not rewrite them. If a framework uses pre-generated metadata caches, the cache may still point to the old names.

Therefore, safety cannot be concluded merely by searching application source code for `Class.forName`.

### 5.3. Custom ClassLoaders

Example of a plugin manager:

```java
Class<?> pluginType = pluginLoader.loadClass(
        configuredImplementation);
```

Check all of the following:

1. Does the config still hold the old class name?
2. Does the relocated class exist properly inside the JAR?
3. Is the JAR on the classpath/module path that the loader actually reads?
4. Does the loader filter packages or enforce a child-first/parent-first policy?
5. Is there a shared API version on the host that the plugin must implement?

A class present in the JAR yet invisible to the expected loader can still cause `ClassNotFoundException`.

### 5.4. Deep reflection and JPMS

Relocation is not a way to automatically bypass Java Platform Module System access restrictions.

A framework may load the right class yet encounter:

```text
java.lang.reflect.InaccessibleObjectException
```

when calling `setAccessible(true)` on a field or constructor in a package of a named module that has not been opened. In that case, investigate `opens` or `--add-opens`, rather than inferring from relocation that all access is permitted.

### 5.5. Persistent data containing FQCNs

Class names may already reside in:

- JSON polymorphic type metadata.
- XML or mapping files.
- Database records and configuration services.
- Cache keys or job descriptors.
- Java serialization streams.
- Messages produced by other services.
- Internal plugin protocols.

If historical data contains old names, the new artifact may misread or fail to read it. Design aliases, adapters, or controlled schema migrations rather than blindly running string find-and-replace.

## 6. Java SPI and `META-INF/services`

### 6.1. How does ServiceLoader find implementations?

On a traditional classpath, SPI typically has a file:

```text
META-INF/services/com.vendor.spi.CompressionProvider
```

Its contents list the FQCNs of implementations:

```text
com.vendor.impl.FastCompressionProvider
com.vendor.impl.SafeCompressionProvider
```

The application calls:

```java
ServiceLoader<CompressionProvider> providers =
        ServiceLoader.load(CompressionProvider.class);

for (CompressionProvider provider : providers) {
    provider.initialize();
}
```

Java locates providers via the service interface and resource configuration; the `META-INF/services/*` files themselves are **text metadata** inside the JAR. They do not automatically follow bytecode renames.

### 6.2. Both path and contents must be updated as appropriate

Suppose we relocate:

```text
com.vendor.spi.CompressionProvider
  => com.example.shaded.spi.CompressionProvider

com.vendor.impl.FastCompressionProvider
  => com.example.shaded.impl.FastCompressionProvider
```

When **the service interface is also relocated**, the corresponding metadata may need to become:

```text
META-INF/services/com.example.shaded.spi.CompressionProvider

Content:
com.example.shaded.impl.FastCompressionProvider
```

However, if **the service interface is a shared API and is not relocated**, the resource name must remain:

```text
META-INF/services/com.vendor.spi.CompressionProvider

Content:
com.example.shaded.impl.FastCompressionProvider
```

That is why a metadata file-renaming rule cannot be applied blindly without knowing the shared API architecture.

### 6.3. Consequences when resources are not handled

| Situation | Possible consequence |
| --- | --- |
| Provider class renamed, descriptor contents still old name | `ServiceConfigurationError` or provider not loaded. |
| Service interface renamed, descriptor filename still old name | `ServiceLoader` fails to find the service configuration. |
| JAR merge drops one descriptor | Some providers disappear from the list. |
| Provider implements a relocated interface while consumer uses unrelocated one | Incompatible types; `ServiceConfigurationError` may occur. |
| JAR/provider not loaded by the right loader/module graph | `ServiceLoader` finds no implementations. |

### 6.4. Merging multiple `META-INF/services` files

Two libraries may both contain:

```text
META-INF/services/java.sql.Driver
```

One file registers provider A; the other registers provider B. If a fat JAR keeps only one resource on duplicate entry names, the other library's providers can be lost.

An appropriate **service resource transformer** can merge provider lists. However, verify that it also applies relocation mappings properly to provider classes and service interfaces (if applicable). Specific capabilities depend on the plugin/version.

Do not use naive plain-text concatenation for all resources, because different formats handle duplicate keys and class names differently.

### 6.5. Testing SPI via runtime behavior

A proper test does not merely check that the JAR contains the class. It must actually discover the provider:

```java
import java.util.ServiceLoader;

public final class ServiceProbe {
    public static void check() {
        boolean found = false;

        for (CompressionProvider provider :
                ServiceLoader.load(CompressionProvider.class)) {
            System.out.println(provider.getClass().getName());
            found = true;
        }

        if (!found) {
            throw new IllegalStateException(
                "Không tìm thấy CompressionProvider");
        }
    }
}
```

If the interface is also relocated, `CompressionProvider` in the test must be the **actual interface of the final artifact**. Tests should verify required providers — not just count > 0 — and invoke a business operation to catch non-functional implementations.

## 7. Other resources and metadata

### 7.1. Manifest

`META-INF/MANIFEST.MF` may contain:

```text
Main-Class: com.example.app.Main
Automatic-Module-Name: com.example.app
Premain-Class: com.example.agent.Agent
Agent-Class: com.example.agent.Agent
```

These related class and module names must match the packaged artifact. When merging multiple JARs, original manifests cannot all be kept unconditionally. Configure the output artifact's manifest explicitly and verify the actual entry point.

### 7.2. Spring metadata

Certain resources may contain class names or implementation lists:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring.handlers
META-INF/spring.schemas
```

These files do not share a single format. Some are properties with special keys; others are lists of classes or schema URLs. Simple file concatenation can lose or overwrite information on key collisions, and relocating bytecode does not guarantee class names inside metadata are updated.

For a specific framework, choose transformers compatible with that framework version and inspect the final resource contents.

### 7.3. Logging plugin descriptors

Some logging frameworks use service metadata or build-generated plugin caches. For example, Log4j 2 may store plugin cache metadata in `META-INF`. If shading drops cache files, merges them incorrectly, or leaves old class names intact, an appender/layout used only in production may fail to be discovered.

Do not handle binary cache resources via text appending. Use a transformer or regeneration step following the documentation for the exact framework version.

### 7.4. Relative and absolute resource paths

Example:

```java
Parser.class.getResourceAsStream("defaults.properties");
```

This resource is resolved relative to `Parser`'s package. If the class is relocated without moving the properties file along with it, the call can return `null`.

Another case:

```java
Parser.class.getClassLoader().getResourceAsStream(
        "com/vendor/json/defaults.properties");
```

This is a resource path inside a string. Even though the class was relocated, the string path may still use the old name. Check both lookup styles.

### 7.5. ResourceBundle

`ResourceBundle` may look up a base name such as `com.vendor.i18n.Labels`, corresponding to files:

```text
com/vendor/i18n/Labels.properties
com/vendor/i18n/Labels_vi.properties
```

After relocation, the base name or resource path may no longer match. Ensure proper mapping and test actual locales rather than testing only the default language.

### 7.6. Native/JNI

A JNI library may map Java package/class names to native symbol names or registration routines. Relocating Java classes without updating native bindings can cause `UnsatisfiedLinkError`.

If a dependency contains JNI/JNA, native extraction, or OS-architecture-specific libraries, test on all supported platforms. Do not assume relocation is safe merely because Java classes were renamed successfully.

## 8. Java serialization and data transport protocols

### 8.1. Java Object Serialization

Java Object Serialization data can record class names in class descriptors. If a stream previously contained `com.vendor.model.Record` and after relocation only `com.example.shaded.model.Record` exists, deserializing old streams may fail.

Keeping the same `serialVersionUID` does not automatically fix changed class names. If legacy data must be read, design compatibility/migration at the serialization boundary and audit deserialization security.

### 8.2. JSON/XML polymorphism

Some serializers write class names into payloads:

```json
{
  "@class": "com.vendor.model.Record",
  "id": 17
}
```

If a new producer outputs shaded names while an old consumer still expects original names (or vice versa), the two systems can be incompatible despite valid JSON.

Prefer stable schema identifiers decoupled from implementation packages. If legacy data already exists, use allowlisted mappings, versioning, and backed-up migrations; never allow arbitrary class deserialization from untrusted input.

### 8.3. Caches and databases

Cache values or database records may store FQCNs to select decoders, job handlers, or plugins. Such data typically lives outside build artifacts, so relocation tools cannot update it automatically.

When changing packages, inventory existing stored data and coordinate multi-version rollouts if necessary. Avoid releasing new code that can only read new names while historical data still carries old names.

## 9. Maven Shade Plugin: configuration example

### 9.1. Relocation and service transformer

The following Maven example uses an illustrative plugin version; projects must select and pin **an actual version verified to support their JDK and build tool**:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-shade-plugin</artifactId>
      <version>3.6.1</version>
      <executions>
        <execution>
          <phase>package</phase>
          <goals>
            <goal>shade</goal>
          </goals>
          <configuration>
            <relocations>
              <relocation>
                <pattern>com.vendor.json</pattern>
                <shadedPattern>
                  com.example.payment.internal.shaded.json
                </shadedPattern>
              </relocation>
            </relocations>
            <transformers>
              <transformer implementation=
                "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
              <transformer implementation=
                "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                <mainClass>com.example.payment.Main</mainClass>
              </transformer>
            </transformers>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Meaning:

- `relocations` specifies source/destination package prefixes.
- `ServicesResourceTransformer` handles `META-INF/services`, including provider merging; check actual behavior in documentation for your plugin version.
- `ManifestResourceTransformer` helps specify the artifact's entry point.
- No default transformer should be treated as a universal solution for all Spring metadata, logging caches, or configs outside the JAR.

If a library only needs to shade a specific dependency, control the included artifacts list and relocation scope to avoid accidentally relocating public API or shared SPI packages.

### 9.2. `minimizeJar` and reflection

Some Maven Shade configurations offer JAR size reduction via class-usage analysis. In systems using reflection, `ServiceLoader`, or dynamically loaded plugins, classes referenced only via strings/configuration may appear "unused" to static analysis.

If a class is stripped, the application will break when that dynamic loading path runs. During migration, prioritize complete artifacts and functional correctness, enabling class-stripping optimizations only once tests and explicit keep lists are in place.

### 9.3. Signed JARs

Shading alters bytecode/resources, invalidating digital signatures of original JARs. Entries such as:

```text
META-INF/*.SF
META-INF/*.RSA
META-INF/*.DSA
```

must be handled according to packaging and security policy. Stripping old signature metadata from the output artifact does not mean the new artifact has been verified. If the organization requires signatures/provenance, run signing and verification after the build.

## 10. Gradle Shadow: configuration example

For a project with a compatible Shadow plugin installed and a `shadowJar` task, Gradle Groovy DSL example:

```groovy
tasks.named('shadowJar') {
    relocate(
        'com.vendor.json',
        'com.example.payment.internal.shaded.json'
    )

    mergeServiceFiles()
}
```

Key points:

- `relocate` changes the specified namespace.
- `mergeServiceFiles` merges service descriptors according to plugin capabilities.
- Framework-specific resources may require additional transformers.
- Both the plugin and Gradle must be compatible with the JDK running the build.
- When publishing a library, explicitly decide how the shadow artifact and consumer dependency metadata are structured.

Do not infer from a successful `shadowJar` task that external config files or string-loaded classes were rewritten.

## 11. Specific characteristics when using JPMS

### 11.1. Unnamed module and classpath

An executable fat JAR run with:

```bash
java -jar application-all.jar
```

typically uses the classpath for application classes. In this model, JPMS still applies to JDK modules, while package visibility among legacy JARs is not governed as explicit named modules.

Reflection, SPI, and resources still require separate verification. Absence of `module-info.java` does not mean absence of class-loading errors.

### 11.2. Automatic modules and module names

If a shaded JAR without an explicit module descriptor is placed on the module path, it may be treated as an automatic module. Its module name comes from `Automatic-Module-Name` or is derived from the filename.

Relocating packages **does not automatically rename the module**. If consumers declare `requires com.vendor.lib` while the new artifact carries a different module name, module resolution can fail.

Inspect actual module metadata:

```bash
jar --describe-module --file path/to/shaded-library.jar
```

### 11.3. Explicit module descriptors

Merging multiple modular JARs into one artifact does not allow multiple `module-info.class` files to coexist as a single valid module descriptor. Individual descriptors may differ in:

- `requires` and module names.
- `exports` and `opens`.
- `uses`/`provides`.
- Package boundaries and access policies.

Explicitly decide whether the final artifact targets the classpath, automatic module, or explicit named module. If a new module descriptor is needed, redesign and re-verify the module graph rather than copying metadata as-is.

### 11.4. Multi-release JARs

A dependency may contain:

```text
META-INF/versions/9/...
META-INF/versions/17/...
```

When shading, the tool must support JDK-versioned class variants. Transforming only root classes while missing versioned classes can yield an artifact that works on JDK 11 yet fails on JDK 17.

Inspect the `Multi-Release` manifest entry, versioned paths, and run tests across all supported JDKs.

### 11.5. Split packages

Relocation can sometimes resolve split packages, yet can also introduce new split packages if rules are inconsistent. Inspect package layout, module graph, dependency versions, and actual class loaders before declaring the modular setup healthy.

## 12. Public API and binary compatibility

### 12.1. When dependency types leak into the API

Example public library signature:

```java
public com.vendor.json.Document parse(String source);
```

If relocation changes the return type to `com.example.shaded.json.Document`, the public method descriptor changes. Previously compiled binary clients can hit `NoSuchMethodError`; source clients also have to change imports and types.

Better yet, expose a library-owned DTO or interface:

```java
public ParseResult parse(String source);
```

With an appropriate adapter, implementation details can move into a shaded namespace without forcing every client onto internal packages.

### 12.2. Shared API between host and plugin

In a plugin architecture, host and plugin usually must share **the same runtime interface**. Relocating the shared SPI into the plugin JAR causes the plugin's class to no longer implement the type the host expects.

Example:

```text
Host:   com.example.spi.PaymentPlugin
Plugin: com.example.internal.shaded.spi.PaymentPlugin
```

These are two distinct types. Identify packages that must not be relocated:

- Host/plugin SPIs.
- DTOs passed across boundaries.
- Shared application-server or framework APIs.
- Public APIs promised to consumers.

Relocate only the implementation dependencies needing isolation whenever possible.

### 12.3. POM and module metadata of published artifacts

If a library publishes a shaded JAR, dependency metadata (POM/Gradle Module Metadata) must reflect which dependencies are embedded and which must still be fetched separately.

Some configurations generate a dependency-reduced POM. Accidentally dropping a dependency still needed at runtime causes missing classes for consumers. Both embedding a library and keeping its original transitive dependency can cause consumers to receive two copies and hit new conflicts.

Test the artifact from **a separate consumer project**, rather than only running the producing project's build.

## 13. Security, licenses, and SBOM

### 13.1. Renaming packages does not remove CVEs

If `json-core:1.x` has a vulnerability, its vulnerable code remains after package renaming. Some dependency scanners may fail to recognize its origin once the JAR is merged and namespace-shifted.

Therefore preserve:

- Original Maven coordinates or identifiers.
- Versions and checksums of embedded dependencies.
- Relocation rules and plugin versions.
- Licenses, NOTICE files, and attributions.
- An SBOM listing embedded components.
- CVE checking workflows for both original libraries and the final artifact.

Prefer upgrading dependencies to fixed versions before using shading as a compatibility measure.

### 13.2. Reproducibility and provenance

Building a shaded artifact can alter entry ordering, timestamps, or metadata across plugin/build environments. For verifiable releases, pin inputs, plugins, dependencies, and packaging configurations.

If the artifact must be signed, sign after transformation per policy; do not rely on old signatures from rewritten JARs.

### 13.3. Reflection and class names from untrusted data

When loading classes by name from configuration or payloads, restrict the allowlist of permitted classes/providers. Do not loosen dynamic loading arbitrarily to "support both old and new names", especially with deserialization or plugins receiving untrusted input.

## 14. Verifying the artifact after shading

### 14.1. Listing actual entries

```bash
jar tf target/application-all.jar
```

Verify:

- Classes moved to the intended paths.
- No unexpected old-named classes remain.
- `META-INF/services` entries are complete.
- Framework resources, bundles, and manifests remain intact.
- No duplicate entries or mis-merged packages exist.
- Multi-release variants are present.

### 14.2. Inspecting class names and method descriptors

```bash
javap -classpath target/application-all.jar \
  -p -s com.example.payment.internal.shaded.json.Parser
```

If a class is missing or a public API changed unexpectedly, investigate relocation rules and shaded artifact scope.

### 14.3. Manually checking service descriptors

Inspect each `META-INF/services/<actual-service-interface>` entry inside the archive and cross-check against classes in the JAR:

- Does the filename match the runtime interface?
- Are provider names accurate after relocation?
- Do providers implement the right interface?
- Were any providers dropped during merge?
- Are providers from unbundled dependencies missing?

Distinguish between relocating *the service interface* and relocating *only the provider*, as the two cases have different filename rules.

### 14.4. Identifying the class loader at runtime

When deep investigation is required, print:

```java
static void printOrigin(Class<?> type) {
    System.out.println("Class: " + type.getName());
    System.out.println("Module: " + type.getModule());
    System.out.println("Loader: " + type.getClassLoader());

    var domain = type.getProtectionDomain();
    var source = domain == null ? null : domain.getCodeSource();
    System.out.println("CodeSource: " +
        (source == null ? "unknown" : source.getLocation()));
}
```

With dynamically generated classes, `CodeSource` may have no data. This is supplementary diagnostic information, not a replacement for inspecting class loaders, module graphs, and metadata.

## 15. Recommended migration workflow

### Step 1: Capture baseline

Record the dependency graph, JDK vendor/version, build plugin versions, classpath/module path, class loaders, conflict errors, existing services/providers, and affected business flows.

Collect the original artifacts for post-change comparison.

### Step 2: Define the exact objective

Shading to build an executable JAR differs from shading to run two versions concurrently. If only deployment convenience is desired, relocation is not strictly necessary.

When resolving conflicts, clearly identify which dependencies need separate namespaces and which APIs must remain shared.

### Step 3: Map classes and metadata

| Component | Before | Intended after | Additional checks |
| --- | --- | --- | --- |
| Implementation class | `com.vendor.json.Parser` | `com.example.shaded.json.Parser` | Bytecode, reflection. |
| Service interface | `com.vendor.spi.Provider` | Keep or relocate per contract | `META-INF/services` filename. |
| Provider class | `com.vendor.impl.ProviderImpl` | Relocated name | Descriptor contents. |
| Resource | `com/vendor/json/defaults.properties` | Keep/move per lookup method | `getResource`/`ResourceBundle`. |
| Framework metadata | Spring/logging/config | Dedicated transformer | Scanning/cache and startup. |
| Public API | `com.vendor.json.Document` | Prefer keeping via adapter | Source/binary compatibility. |

Do not inspect only repository files if production has remote configs, plugin directories, or databases storing class names.

### Step 4: Choose scoped tools and rules

Pin the Maven Shade/Gradle Shadow version. Choose:

- A sufficiently narrow namespace prefix.
- Appropriate resource transformers.
- Rules preserving shared APIs.
- Policies for manifests, signatures, licenses, natives, and multi-release JARs.
- How the shaded artifact and dependency metadata are published.

Do not enable static-analysis class removal until dynamic loading paths are tested.

### Step 5: Build and inspect the final JAR

Inspect `jar tf`, manifests, service descriptors, and relocated classes. Do not treat a successful package build as proof that metadata is valid.

### Step 6: Test dynamic loading paths

Include:

- `Class.forName` with realistic configurations.
- `ServiceLoader` and required providers.
- Dependency injection, ORM, serializers, and component scanning.
- Resource lookups and ResourceBundle.
- Plugins installed/loaded after startup.
- Historical serialized data, if any.
- JNI/natives across supported platforms.

### Step 7: Test consumers and target JDKs

For public libraries, build a separate client and verify both source/binary compatibility per commitments. For JDK migrations, test all runtimes in the support matrix, especially with JPMS or multi-release JARs.

### Step 8: Security and release

Update SBOMs, license/NOTICE files, checksums, signatures, dependency metadata, and rollback instructions. Record the relocation mapping so operations teams can interpret class names in stack traces during incidents.

## 16. Common errors

| Symptom | Common cause | Investigation |
| --- | --- | --- |
| `ClassNotFoundException` with old name | Config/reflection was not renamed. | Compare FQCNs across config, JAR, and class loader. |
| `ServiceConfigurationError` | Descriptor points to missing provider or incompatible interface. | Inspect `META-INF/services` and verify implementations. |
| `ServiceLoader` returns empty | Metadata file lost or module/provider not loaded. | Check resource merging, SPI, and module graph. |
| `NoSuchMethodError` | Dependency conflict or changed public descriptor. | Compare runtime JARs and `javap -s`. |
| `ClassCastException` | Two copies of class/shared API lack common runtime identity. | Print class loader, module, and class name. |
| `MissingResourceException` | Base name/resource path mismatch after relocation. | Inspect bundle and lookup mechanism. |
| `NullPointerException` reading resource | `getResourceAsStream` returned `null`. | Check resource presence in JAR and exact path. |
| Framework misses component | Metadata, package scan, or plugin cache unchanged. | Verify framework configs/transformers. |
| `UnsatisfiedLinkError` | JNI/native mapping renamed or native library missing. | Inspect native bindings and platform. |
| `java -jar` fails to run | Wrong or missing manifest `Main-Class`. | Inspect final artifact's manifest. |
| Error appears on only one JDK | Multi-release classes/JPMS or incompatible bytecode plugin. | Inspect versioned entries and test matrix. |
| SCA fails to flag vulnerable library | Dependency embedded and repackaged, hiding identity. | Check SBOM, original coordinates, packaged code. |

Do not fix every error by adding `--add-opens`, extra JARs, or skipping verification. Categorize first: **renamed symbol, lost metadata, missing class, module resolution, or incompatible API**.

## 17. Hands-on SPI scenario after relocation

### 17.1. Context

A plugin uses `ServiceLoader<CompressionProvider>`. The host's shared API interface `com.example.spi.CompressionProvider` must stay unchanged. The legacy implementation `com.vendor.impl.FastProvider` is relocated to `com.example.plugin.shaded.impl.FastProvider`.

### 17.2. Desired artifact state

```text
Class:
  com/example/plugin/shaded/impl/FastProvider.class

Service metadata:
  META-INF/services/com.example.spi.CompressionProvider

Service file content:
  com.example.plugin.shaded.impl.FastProvider
```

Do **not** rename the service file to `META-INF/services/com.example.plugin.shaded.spi.CompressionProvider` if the shared API interface was not relocated.

### 17.3. Minimum test

At runtime, invoke `ServiceLoader.load(CompressionProvider.class)`, verify `FastProvider` is discovered, and execute compression/decompression logic or a matching functional method.

Tests must not check class existence solely via `Class.forName`. Having the class in the JAR with a broken service descriptor still causes SPI to fail.

### 17.4. Failure scenarios

If the service file still lists `com.vendor.impl.FastProvider` after the class was renamed, `ServiceLoader` may fail reporting the provider class does not exist. If the service file was dropped during packaging, the iterator may find no providers. If the plugin relocated the shared API interface too, the provider may no longer implement the type the host expects.

These are three distinct failures that must be distinguished to choose the right fix.

## 18. Pre-release checklist

- [ ] Confirmed reason for shading and evaluated version alignment/exclusion.
- [ ] Separated implementation namespaces to relocate from shared APIs to preserve.
- [ ] Pinned plugin versions and reproducible build rules.
- [ ] Identified class names used via reflection and external configuration.
- [ ] Checked both filenames and provider names in `META-INF/services`.
- [ ] Merged service descriptors without dropping providers.
- [ ] Handled manifests and framework-specific metadata.
- [ ] Verified relative/absolute resource lookups and ResourceBundles.
- [ ] Assessed JNI/native libraries, signed JARs, and multi-release JARs.
- [ ] Identified impact on Java serialization and FQCN-containing data.
- [ ] Verified JPMS/module path if the product uses named/automatic modules.
- [ ] Verified source/binary compatibility and POM when publishing for consumers.
- [ ] Inspected the final artifact structure rather than trusting build logs alone.
- [ ] Ran integration tests for ServiceLoader, reflection, scanning, and plugins.
- [ ] Recorded embedded original dependencies in SBOM, license/NOTICE, and security reports.
- [ ] Established rollback plan, relocation mapping, and accountable owners.

## 19. Conclusion

**Shading** packages dependencies; **relocation** creates isolated namespaces to reduce class-name conflicts. However, Java also relies on class/package names in reflection, `ServiceLoader`, `META-INF/services`, manifests, resources, configuration, serialization, and plugin mechanisms. These pieces may not be updated solely by a bytecode-renaming rule.

In Java Advance Compatibility Migration, the completion criterion is not "a JAR was built", but that **the new artifact resolves the right classes, preserves all providers, loads the right resources, and continues satisfying consumer contracts on the target JDK**. Treat relocation as a scoped transformation with runtime tests and explicit dependency records, rather than a workaround that hides conflicts and leaves long-term risk behind.