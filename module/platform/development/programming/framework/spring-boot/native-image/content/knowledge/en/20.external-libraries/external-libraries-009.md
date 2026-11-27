# Contract Testing for Integrations Involving Reflection, Service Loading, or JNI

## 1. Why Are Contract Tests Needed for External Libraries?

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot applications are processed with **Spring AOT** and compiled into GraalVM Native Image. External libraries can run fine on the JVM yet fail natively if they rely on reflection, `ServiceLoader`, dynamically located resources, or JNI.

Unit tests that merely mock the SDK typically verify adapter logic without confirming that the real library can:

- locate constructors, methods, or fields via reflection;
- discover providers via `ServiceLoader` and `META-INF/services` resources;
- load shared libraries matching the target OS/architecture;
- invoke native methods or callbacks from C/C++ back into Java;
- read required resources and configuration inside a native executable.

**Contract tests** verify observable behavior at integration boundaries. The same test suite should run against the real implementation on both the JVM and the native executable. This enables the team to catch differences in discovery, reachability metadata, resources, errors, and packaging early.

## 2. What Do Contract Tests Verify?

An integration contract describes the guarantees the application depends on:

| Guarantee category | Examples to verify |
| --- | --- |
| Input/output | Written and read data preserve content, encoding, and format |
| Error mapping | Timeouts, invalid data, and SDK errors translate into handleable application errors |
| Discovery | Required providers or plugins are discovered properly |
| Reflection | Constructors/methods invoked dynamically by the library are accessible natively |
| Resources | Valid schemas, templates, or configuration files are found |
| JNI | Native libraries load and native calls return accurate results |
| Lifecycle | Resources are closed and callbacks are not retained after completion |
| Runtime behavior | Timeouts, concurrency, and runtime settings are respected |

Contract tests do not need to verify every internal vendor method. Focus on behaviors the application actually uses and risks that may shift when moving from JVM to Native Image.

## 3. Isolate External Libraries Behind an Adapter

A testable design places third-party libraries behind an application-owned interface. For example, a document archive service:

~~~java
public interface DocumentArchive {
    void save(String documentId, byte[] content);
    byte[] load(String documentId);
    boolean exists(String documentId);
}
~~~

An adapter implements the interface using the real SDK:

~~~java
public final class VendorDocumentArchive implements DocumentArchive {

    private final VendorArchiveClient client;

    public VendorDocumentArchive(VendorArchiveClient client) {
        this.client = client;
    }

    @Override
    public void save(String documentId, byte[] content) {
        client.put(documentId, content);
    }

    @Override
    public byte[] load(String documentId) {
        return client.get(documentId);
    }

    @Override
    public boolean exists(String documentId) {
        return client.contains(documentId);
    }
}
~~~

`VendorArchiveClient` is an illustrative type; replace it with the actual API of the library in use. The adapter can convert data types, map vendor errors to application exceptions, and apply timeouts. Avoid letting controllers or domain services depend directly on the SDK unnecessarily.

Benefits of the interface:

- Contract tests can run against any implementation.
- You can swap SDKs or upgrade versions without changing the application contract.
- JVM tests can use a fake implementation for logic not requiring the vendor.
- Native integration tests can still run against the real adapter and dependency to verify metadata.

Mocks do not replace contract tests against the real SDK. Use fakes/mocks for fast unit tests, then run the contract suite against the real implementation during integration.

## 4. Build a Reusable Contract Suite

JUnit 5 allows shared tests to live in an abstract base class. Each implementation supplies factories for the adapter and test resources:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

abstract class DocumentArchiveContractTests {

    protected abstract DocumentArchive createArchive();
    protected abstract void cleanUp();

    @AfterEach
    void releaseResources() {
        cleanUp();
    }

    @Test
    void savesAndLoadsTheSameBytes() {
        DocumentArchive archive = createArchive();
        byte[] content = new byte[] { 0, 1, 2, 10, 127, -1 };

        archive.save("contract-doc-001", content);

        assertThat(archive.exists("contract-doc-001")).isTrue();
        assertThat(archive.load("contract-doc-001"))
            .containsExactly(content);
    }

    @Test
    void reportsMissingDocument() {
        DocumentArchive archive = createArchive();
        assertThat(archive.exists("does-not-exist")).isFalse();
    }
}
~~~

Test implementation for the real SDK:

~~~java
class VendorDocumentArchiveContractTests
        extends DocumentArchiveContractTests {

    private VendorArchiveClient client;

    @Override
    protected DocumentArchive createArchive() {
        client = VendorArchiveClient.connect(testEndpoint());
        return new VendorDocumentArchive(client);
    }

    @Override
    protected void cleanUp() {
        if (client != null) {
            client.close();
        }
    }

    private String testEndpoint() {
        return System.getenv("ARCHIVE_TEST_ENDPOINT");
    }
}
~~~

This is an illustrative skeleton; in real projects, validate endpoints and credentials before creating clients, generate unique document IDs per test, and delete test data afterward. If the SDK implements `AutoCloseable`, prefer managing lifecycle via try-with-resources or appropriate fixtures.

The contract suite should run against the vendor adapter on both JVM and native executable, as well as other implementations if the application supports multiple providers. Never put real secrets in source code or test reports. Use least-privilege test credentials, CI secret stores, and sandbox endpoints.

## 5. Reflection-Based Integrations

### 5.1. Reflection Alters Reachability

A library may look up classes or methods by name at runtime:

~~~java
Class<?> type = Class.forName("com.vendor.codec.JsonCodec");
Object codec = type.getDeclaredConstructor().newInstance();

Method encode = type.getMethod("encode", Object.class);
String json = (String) encode.invoke(codec, payload);
~~~

On the JVM, the classloader and reflection can locate types on the classpath. Native Image analyzes under a closed-world assumption; classes/members accessed solely dynamically can be excluded without proper reachability metadata.

When that happens, the application may build cleanly yet fail at runtime with errors like:

- `ClassNotFoundException` or `NoClassDefFoundError`;
- `NoSuchMethodException`;
- `IllegalAccessException`;
- Native Image reflection errors for unregistered constructors/methods.

### 5.2. Test the Exact Reflection Paths the Application Uses

A contract test should call the adapter's public API so the library executes its actual reflection paths. Do not merely test `Class.forName()` in isolation and conclude the integration works.

~~~java
@Test
void vendorCodecCanEncodeAndDecodeInTheApplicationFlow() {
    PayloadCodec codec = codecFactory.create("com.vendor.codec.JsonCodec");
    Payload input = new Payload("doc-01", "invoice");

    byte[] encoded = codec.encode(input);
    Payload decoded = codec.decode(encoded, Payload.class);

    assertThat(decoded).isEqualTo(input);
}
~~~

Run this test on both JVM and native executable. The test must pass through the real factory/adapter to confirm the actual class names, constructors, methods, and mappings used.

### 5.3. Add Appropriately Scoped Metadata

Before writing hints yourself:

1. Check whether the library supplies GraalVM reachability metadata.
2. Check whether that metadata exists in the dependency version in use.
3. Identify the exact classes, constructors, methods, or fields accessed dynamically.
4. Run native tests to verify that call path.

With Spring, you can register types needing reflection using `RuntimeHintsRegistrar` or `@RegisterReflectionForBinding` where appropriate. Illustrative example registering a specific constructor and method:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(VendorCodecHints.class)
class VendorCodecConfiguration {
}

class VendorCodecHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        try {
            Class<?> codecType = ClassUtils.forName(
                "com.vendor.codec.JsonCodec", classLoader
            );
            hints.reflection().registerConstructor(
                codecType.getDeclaredConstructor(),
                ExecutableMode.INVOKE
            );
            hints.reflection().registerMethod(
                codecType.getMethod("encode", Object.class),
                ExecutableMode.INVOKE
            );
        }
        catch (ClassNotFoundException | NoSuchMethodException ex) {
            throw new IllegalStateException(
                "The configured vendor codec is unavailable", ex
            );
        }
    }
}
~~~

This example assumes the dependency is present when configuration is processed. If the dependency is optional, place the configuration in an auto-configuration guarded by `@ConditionalOnClass(name = "...")` and avoid directly importing vendor types in always-loaded classes.

Registering specific constructors/methods is narrower than enabling all declared methods/fields across an entire package. If the vendor already publishes metadata, prefer using that metadata instead of duplicating configuration.

## 6. ServiceLoader-Based Integrations

### 6.1. How Does ServiceLoader Discover Providers?

Java `ServiceLoader` locates implementations of a service interface. On a standard classpath, providers can be declared in:

~~~text
META-INF/services/com.example.compression.CompressionProvider
~~~

Contents are the fully qualified provider names:

~~~text
com.vendor.compression.FastCompressionProvider
~~~

When using the Java module system, providers can also be declared with `provides ... with ...` in `module-info.java`.

Example service interface:

~~~java
public interface CompressionProvider {
    String id();
    byte[] compress(byte[] input);
    byte[] decompress(byte[] input);
}
~~~

Application provider lookup:

~~~java
CompressionProvider provider =
    ServiceLoader.load(CompressionProvider.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(candidate -> candidate.id().equals("fast"))
        .findFirst()
        .orElseThrow(() ->
            new IllegalStateException("No 'fast' compression provider found")
        );
~~~

Select providers by explicit ID or configuration. Do not rely on `findFirst()` without criteria when the classpath may contain multiple providers; discovery order should never become a business contract.

### 6.2. Why Does ServiceLoader Need Native Tests?

Native Image can analyze service providers at build time, yet discovery still depends on service descriptors, module declarations, classpath, and how the application loads providers. If a descriptor or provider is omitted from the executable, the application may fail to find the implementation even when JVM tests pass.

Contract tests should verify:

- present providers are discovered;
- provider ID is accurate and unique per application configuration;
- the provider can be instantiated;
- compression/decompression preserves data;
- missing-provider cases fail with clear errors or defined fallbacks.

~~~java
@Test
void discoversAndUsesConfiguredCompressionProvider() {
    List<CompressionProvider> providers =
        ServiceLoader.load(CompressionProvider.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .toList();

    assertThat(providers)
        .extracting(CompressionProvider::id)
        .contains("fast");

    CompressionProvider provider = providers.stream()
        .filter(candidate -> candidate.id().equals("fast"))
        .findFirst()
        .orElseThrow();

    byte[] input = "native-image-contract".getBytes(StandardCharsets.UTF_8);
    assertThat(provider.decompress(provider.compress(input)))
        .containsExactly(input);
}
~~~

This test must run with the real provider on the classpath. On the native executable, run the same test logic or a smoke endpoint/command invoking that provider.

### 6.3. Inspect Service Descriptors

Verify that the dependency JAR includes `META-INF/services/...`:

~~~bash
jar tf target/application.jar | grep 'META-INF/services'
~~~

Spring Boot executable JARs use a nested JAR layout; inspect descriptors inside the nested dependency JARs if the command above only lists entries of the outer JAR. You can extract the specific dependency or inspect the library artifact before packaging.

If providers are registered through the module system, inspect `module-info.class`/module descriptors and the build's module path configuration.

Do not add resource hints mechanically if Native Image or the library already handles service provider metadata. Check native build outputs and logs first; add metadata only per guidance for your GraalVM/Native Build Tools version.

## 7. JNI-Based Integrations

### 7.1. JNI Operates in Both Directions

JNI allows Java to call native code and native code to call back into Java objects. For example, Java declaring a native method:

~~~java
public final class NativeChecksum {

    static {
        System.loadLibrary("checksum");
    }

    private NativeChecksum() {
    }

    public static native int checksum(byte[] input);
}
~~~

In a JVM application, `System.loadLibrary` locates the shared library by name using the OS library loader. With a native executable, the shared library must still match the target OS/CPU and sit where the loader can find it.

JNI can also call back into Java via `JNIEnv`, `FindClass`, `GetMethodID`, `GetFieldID`, or object allocation. Dynamic accesses from native code into Java classes/members require corresponding JNI metadata in Native Image.

### 7.2. What Should Contract Tests Verify?

For JNI libraries, the contract suite should check:

- the shared library loads in the target environment;
- native methods return accurate results for known inputs;
- byte array/string data passes with correct encoding and boundaries;
- errors from native code map to exceptions or results per contract;
- native resources are released properly;
- callbacks from native back to Java work if used by the library;
- concurrent execution does not corrupt state or share buffers unsafely.

~~~java
class NativeChecksumContractTests {

    @Test
    void computesExpectedChecksum() {
        byte[] input = "abc".getBytes(StandardCharsets.UTF_8);
        assertThat(NativeChecksum.checksum(input))
            .isEqualTo(knownChecksumForAbc());
    }
}
~~~

`knownChecksumForAbc()` is an independently computed test value matching the library's algorithm. Do not call `NativeChecksum.checksum()` itself to compute the expected value, as the test would simply repeat the same bug.

### 7.3. JNI Metadata and Native Image

If a native library calls back into Java via JNI, Native Image needs to know which classes/members native code will access. Supply JNI metadata via GraalVM-supported mechanisms or register via runtime hints where Spring Framework APIs fit the access type.

Distinguish:

- Java calling a declared `native` method: requires a platform-matching native library and working library loading inside the executable.
- C/C++ calling back into Java classes/methods/fields via JNI: requires reachability declarations for dynamically accessed types and members.
- Library using reflection from Java code: requires reflection metadata, not automatically solved by JNI metadata alone.

Do not assume adding a generic `jni-config.json` fixes every failure. Metadata must match exact packages, classes, method signatures, fields, and library version. If the vendor ships reachability metadata, use the exact version bundled with the dependency.

### 7.4. Native Libraries and Deployment Platforms

Shared libraries typically vary by:

- operating system: Linux, Windows, macOS;
- architecture: x86_64, AArch64/ARM64;
- ABI, libc, and system versions;
- static/dynamic linking and system dependencies.

A `.dll` cannot substitute for a `.so`; a macOS library will not run inside a Linux container. Build and test native images in an environment matching the deployment platform, or use builders/runners configured for that target.

## 8. One Contract Suite Across Multiple Integration Types

Tests can be organized in layers:

| Test layer | Verifies | Environment |
| --- | --- | --- |
| Adapter unit test | Input/output mapping, errors, timeouts, close | JVM, using fakes where appropriate |
| Library contract test | Real SDK behavior, reflection, and provider discovery | JVM with real dependency |
| Native contract test | Identical behavior through native executable | Native Image target |
| Deployment test | Library paths, resources, env, permissions, and container | Target container/OS |
| Compatibility test | Dependency/GraalVM/JDK version upgrades | CI across supported version matrix |

Example matrix:

| Integration | JVM test | Native test | Deployment test |
| --- | --- | --- | --- |
| Reflection codec | Encode/decode via real SDK | Same payload via executable | Run with packaged metadata |
| ServiceLoader provider | Provider discovered and chosen accurately | Provider located inside binary | Verify provider descriptor/dependency |
| JNI checksum | Load library and assert expected value | Native method and callbacks (if any) | Shared library matching OS/CPU |
| Storage SDK | Save/load, timeouts, error mapping | Same contract on native binary | Sandbox endpoint, credentials, and network |

Not every test has to run at every stage. Fast unit tests can run frequently; native contract tests run in build/release pipelines; deployment tests run in the target environment or matching container.

## 9. Use Library-Provided Reachability Metadata

Before adding reflection, resource, proxy, serialization, or JNI hints yourself, check whether the dependency provides metadata.

Metadata may reside inside the library in a structure recognized by Native Image, or be supplied via the GraalVM Reachability Metadata Repository/Native Build Tools. Library version matters: metadata for a newer version may not match APIs of an older version.

Workflow:

1. Record dependency coordinates and version.
2. Check vendor release notes/native support documentation.
3. Verify metadata present in the actual artifact.
4. Build native with the exact dependency.
5. Run contract tests covering reflection, service loading, or JNI paths.
6. Add application hints only when evidence proves metadata is missing.

Avoid copying broad reflection configurations from old articles without knowing which classes/members must be retained. Excessive metadata inflates footprint and masks library API changes.

## 10. Optional Dependencies and Both Classpath States

Some integrations exist only in certain application variants. Test both when the dependency is present and when it is absent.

Spring Boot can guard auto-configuration with `@ConditionalOnClass`. For example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.JsonCodec")
@ImportRuntimeHints(VendorCodecHints.class)
class VendorCodecAutoConfiguration {
}
~~~

When the SDK is absent from the build classpath, the SDK's configuration and hints should not be applied. When the SDK is present, AOT processes the configuration and the native build must retain required metadata.

JVM tests can simulate an absent dependency using `FilteredClassLoader`:

~~~java
contextRunner
    .withClassLoader(new FilteredClassLoader("com.vendor.codec"))
    .run(context -> {
        assertThat(context).doesNotHaveBean(PayloadCodec.class);
    });
~~~

With native images, the classpath is baked into the executable. You cannot add an SDK after the binary is built and flip a runtime property to recreate excluded beans, providers, or metadata.

## 11. Testing Failures and Stability

Contract tests should cover failure scenarios, not just the happy path:

- missing provider or multiple providers sharing the same ID;
- reflection target class/method missing after upgrading the SDK;
- missing or wrong-architecture native library;
- library returning data, timeout, permission, or network errors;
- empty inputs, oversized inputs, bad encodings, or boundary data;
- missing resources/configuration;
- concurrent calls and repeated resource closes.

Example testing a missing provider error:

~~~java
assertThatThrownBy(() -> compressionFactory.create("unknown"))
    .isInstanceOf(UnsupportedCompressionProviderException.class);
~~~

The application should translate external library failures into meaningful exceptions/domain errors while preserving the underlying cause for diagnostics. Do not leak sensitive data in exception messages or test reports.

For JNI, test empty inputs, large buffers, and native errors as well. If the API involves buffer/handle ownership, the contract must specify who allocates, who frees, and whether `close()` is idempotent.

## 12. Running Contract Tests in Maven and Gradle

### 12.1. Maven

Run unit and JVM integration tests:

~~~bash
./mvnw test
~~~

Create the native executable using the project's profile/plugin configuration:

~~~bash
./mvnw -Pnative native:compile
~~~

Then run the native contract suite via the executable or test harness configured by the project. If the project configures GraalVM Native Build Tools native test execution, invoke the corresponding goal/test phase. Do not assume `mvn test` automatically runs tests on a native image by default.

### 12.2. Gradle

Run JVM tests:

~~~bash
./gradlew test
~~~

If the plugin and project configure the native test task:

~~~bash
./gradlew nativeTest
~~~

Build the native executable:

~~~bash
./gradlew nativeCompile
~~~

Task names depend on plugins and configuration. Check the task list and Native Build Tools setup before adding commands to pipelines. For JNI, builds must run on runners equipped with shared libraries for the matching OS/CPU and proper loader paths.

## 13. CI Pipeline for External Integrations

A pipeline can be organized as follows:

~~~mermaid
flowchart TB
    D["Resolve dependency versions"] --> J["JVM unit + contract tests"]
    J --> A["Spring AOT"]
    A --> N["Build Native Image"]
    N --> R["Native contract tests"]
    R --> C["Container / target OS tests"]
    C --> P["Publish artifact"]
    J --> F["Fail: fix adapter or dependency"]
    N --> F
    R --> F
    C --> F
~~~

Keep inputs traceable:

- JDK, Spring Boot, GraalVM, and Native Build Tools versions;
- SDK and provider coordinates/versions;
- runner OS/CPU architecture;
- native library checksums;
- reachability metadata accompanying dependencies;
- JVM/native contract suite results.

When upgrading external library versions, re-run the contract suite before publishing. If a vendor changes constructors, service descriptors, native ABI, or metadata, tests will catch the change at the integration boundary.

## 14. Troubleshooting

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| JVM passes, native reports missing constructor/method | Insufficient reflection metadata | Check stack trace, vendor metadata, and exact member called |
| `ServiceConfigurationError` or provider not found | Service descriptor/module declaration/provider absent from build inputs | Inspect `META-INF/services`, module descriptor, and native output |
| `UnsatisfiedLinkError` | Missing shared library, wrong name, wrong ABI, or loader path | Check OS/CPU, loader path, and image packaging |
| JNI callback cannot find Java method | Missing JNI reachability metadata or changed signature | Check class/member/signature in JNI metadata |
| Native runs but SDK resource is missing | Resource unpackaged or wrong hint | Inspect dependency JAR, resource path, and metadata |
| Contract test fails only in container | Missing system library, file permissions, network, or env vars | Compare runtime image against runner and inspect deployment config |
| Test depends on provider ordering | Code picks first provider without criteria | Select by ID/priority and test duplicate cases |
| SDK upgrade breaks native build | Changed API, metadata, or ABI | Pin version, read release notes, and re-run contract suite |

When investigating, retain stack traces and dependency versions, but strip tokens, passwords, URLs with credentials, and customer data before sharing logs.

## 15. Pre-Release Checklist

- [ ] External library integration is placed behind an application adapter/interface.
- [ ] Contract specifies input/output, errors, timeouts, and lifecycle.
- [ ] Tests run against real dependencies, not only mocked SDKs.
- [ ] Reflection paths are exercised through real integration APIs in native mode.
- [ ] `ServiceLoader` discovers the exact provider without relying on arbitrary ordering.
- [ ] JNI library matches target OS/CPU/ABI and loads in the target environment.
- [ ] JNI callbacks have metadata for Java classes/members accessed by native code.
- [ ] Required resources and service descriptors exist in the artifact.
- [ ] Reachability metadata verified for the exact library version.
- [ ] Contract suite runs on both JVM and native executable.
- [ ] Presence and absence tested when the dependency is optional.
- [ ] Deployment tests executed in the matching container or target OS.
- [ ] JDK, Spring Boot, GraalVM, SDK, and native library versions recorded.
- [ ] Logs/test reports contain no credentials or sensitive data.

**Remember:** contract tests confirm an external library fulfills the exact behaviors the application relies on. JVM tests verify the baseline contract; native contract tests confirm reflection, service loading, JNI, and resources work after AOT/Native Image; deployment tests confirm shared libraries and the target environment align. Test real integration paths, use version-matched metadata, and keep hints scoped to what is needed.

## References

- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata for reflection, resources, proxies, serialization, and JNI.
- [GraalVM Native Image — JNI](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/): JNI support and metadata requirements when native code accesses Java.
- [GraalVM Native Build Tools](https://graalvm.github.io/native-build-tools/latest/): Maven/Gradle integration, native tests, and reachability metadata.
- [Java ServiceLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): mechanism for locating and loading providers by service interface.
- [Spring Framework — Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): runtime hints API and Spring AOT integration.
