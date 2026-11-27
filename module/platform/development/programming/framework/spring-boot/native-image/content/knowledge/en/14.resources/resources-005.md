# ServiceLoader, Providers, and META-INF/services Resources

## 1. What Problem Does Java SPI Solve?

An application may need to select an implementation based on configuration or installed libraries: drivers, payment adapters, encoders, formatting strategies, file parsers, or extension plugins. If the caller depends directly on each implementation, adding a provider usually requires modifying code and recompiling the consumer.

Java provides the **Service Provider Interface (SPI)** via `java.util.ServiceLoader`. The application defines an interface or abstract service type; libraries provide classes implementing that interface. `ServiceLoader` locates registered providers and lets the application iterate over them without knowing each concrete implementation in advance.

In a Spring Boot application compiled with **Spring AOT and GraalVM Native Image**, SPI must be verified at build time and runtime. Providers must be present on the dependency/classpath or module path when building the native executable. GraalVM provides support for recognizing `ServiceLoader` configurations, but custom provider loading, reading descriptors directly, or dynamic class generation may require additional configuration.

This lesson belongs to the **Resources** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module and focuses on:

- The relationship between the service interface, provider implementation, and descriptor.
- The structure, filename, and contents of `META-INF/services`.
- How `ServiceLoader` locates and instantiates providers.
- ClassLoader, the Java Module System, and dependency packaging.
- GraalVM Native Image compatibility, Runtime Hints, and testing.

## 2. Three Components of Java SPI

A simple SPI has three parts:

1. **Service interface:** the contract used by the application.
2. **Provider:** a concrete class implementing the service interface.
3. **Provider configuration:** registration information so `ServiceLoader` can discover the provider.

For example, an application needs multiple ways to calculate transaction fees. Service interface:

```java
package com.example.payment.spi;

import java.math.BigDecimal;

public interface PaymentFeeProvider {
    String code();

    BigDecimal calculateFee(BigDecimal amount);
}
```

First provider:

```java
package com.example.payment.provider;

import com.example.payment.spi.PaymentFeeProvider;
import java.math.BigDecimal;

public final class StandardFeeProvider implements PaymentFeeProvider {

    public StandardFeeProvider() {
    }

    @Override
    public String code() {
        return "standard";
    }

    @Override
    public BigDecimal calculateFee(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.015"));
    }
}
```

Second provider:

```java
package com.example.payment.provider;

import com.example.payment.spi.PaymentFeeProvider;
import java.math.BigDecimal;

public final class PremiumFeeProvider implements PaymentFeeProvider {

    public PremiumFeeProvider() {
    }

    @Override
    public String code() {
        return "premium";
    }

    @Override
    public BigDecimal calculateFee(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.008"));
    }
}
```

The application calls the service interface:

```java
PaymentFeeProvider provider = ...;
BigDecimal fee = provider.calculateFee(new BigDecimal("100000"));
```

Business code only needs to know `PaymentFeeProvider`. Provider discovery is handled by `ServiceLoader`.

## 3. Structure of the META-INF/services File

For an application running on the classpath, providers are registered in a text file at the path:

```text
META-INF/services/<fully-qualified-service-interface>
```

In the example above, the service interface is `com.example.payment.spi.PaymentFeeProvider`, so the filename must be exactly:

```text
META-INF/services/com.example.payment.spi.PaymentFeeProvider
```

Structure in a Maven or Gradle project:

```text
src/main/
  java/
    com/example/payment/spi/PaymentFeeProvider.java
    com/example/payment/provider/StandardFeeProvider.java
    com/example/payment/provider/PremiumFeeProvider.java
  resources/
    META-INF/
      services/
        com.example.payment.spi.PaymentFeeProvider
```

Descriptor contents:

```text
com.example.payment.provider.StandardFeeProvider
com.example.payment.provider.PremiumFeeProvider
```

Each line contains the **fully qualified class name** of a provider, without the `.class` extension. Whitespace around names and comment lines starting with `#` are allowed. Do not put the interface name inside the file; the interface name is used to name the descriptor file.

Example with comments:

```text
# Providers supporting transaction fee calculation
com.example.payment.provider.StandardFeeProvider
com.example.payment.provider.PremiumFeeProvider
```

Common naming mistakes:

- Naming the file `PaymentFeeProvider` without the package name.
- Using `META-INF/service/` instead of `META-INF/services/`.
- Adding a `.txt` or `.properties` extension to the filename.
- Writing `StandardFeeProvider.class` instead of the class name.
- Using the wrong package name or mismatched letter casing.
- Placing the descriptor in Java sources instead of the resources directory for packaging.

### 3.1. Provider Rules on the Classpath

With traditional provider configuration files, each provider class must implement the service interface and meet `ServiceLoader`'s instantiation requirements: the provider class must have an accessible no-argument constructor (typically `public`), and the class must be accessible from the classloader being used. If a provider violates these rules, `ServiceLoader` may throw `ServiceConfigurationError` when iterating or instantiating the provider.

Provider constructors should be lightweight, avoiding opening network connections, spawning threads, or performing hard-to-control side effects. `ServiceLoader` may instantiate providers lazily as the iterator/stream is consumed; do not assume merely calling `ServiceLoader.load` has already created every provider.

## 4. Finding and Using Providers with ServiceLoader

Basic usage:

```java
import com.example.payment.spi.PaymentFeeProvider;
import java.util.ServiceLoader;

public class PaymentFeeService {

    public PaymentFeeProvider findProvider(String code) {
        return ServiceLoader
            .load(PaymentFeeProvider.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .filter(provider -> provider.code().equals(code))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown fee provider: " + code)
            );
    }
}
```

Or iterate directly with an iterator:

```java
ServiceLoader<PaymentFeeProvider> loader =
    ServiceLoader.load(PaymentFeeProvider.class);

for (PaymentFeeProvider provider : loader) {
    System.out.println(provider.code());
}
```

`ServiceLoader.load(PaymentFeeProvider.class)` uses the current thread's thread context class loader (TCCL) per API rules. If the application runs in an environment with multiple classloaders or plugin frameworks, determine the appropriate classloader. There is an overload accepting an explicit classloader:

```java
ClassLoader providerClassLoader =
    Thread.currentThread().getContextClassLoader();

ServiceLoader<PaymentFeeProvider> loader =
    ServiceLoader.load(PaymentFeeProvider.class, providerClassLoader);
```

Do not pass an arbitrary classloader. The classloader must be able to see the service interface, the provider classes, and the corresponding descriptor. If the descriptor exists but the provider class resides in a different classloader, discovery or instantiation can still fail.

### 4.1. Lazy Loading and the Stream API

`ServiceLoader` supports lazy provider iteration. With `stream()`, you can inspect the provider type before instantiating an instance:

```java
ServiceLoader<PaymentFeeProvider> loader =
    ServiceLoader.load(PaymentFeeProvider.class);

loader.stream()
    .map(ServiceLoader.Provider::type)
    .forEach(providerType ->
        System.out.println(providerType.getName())
    );
```

Calling `Provider.get()` is what requests an instance of the corresponding provider. This is useful if the application wants to filter providers by annotations or metadata before instantiating them, though accessing types and metadata must still be compatible with how GraalVM analyzes the application.

### 4.2. Handling Missing Providers and Configuration Errors

If no matching provider exists, the iterator may have no elements; `findFirst().orElseThrow` produces a clear business error. If a descriptor is malformed or a provider cannot be instantiated, `ServiceLoader` may throw `ServiceConfigurationError`. Do not catch all exceptions and silently return a default provider, as that can leave a broken production configuration undetected.

You can explicitly validate the provider list at startup:

```java
List<String> providerNames = ServiceLoader
    .load(PaymentFeeProvider.class)
    .stream()
    .map(provider -> provider.type().getName())
    .toList();

if (providerNames.isEmpty()) {
    throw new IllegalStateException("No PaymentFeeProvider found");
}
```

In a Spring Boot application, you can place this check into startup validation or an integration test rather than letting the error surface only on a rare request.

## 5. META-INF/services in Dependencies and the Packaging Process

Provider descriptors can reside inside library JARs, not just in the application project. For example:

```text
payment-spi.jar
  com/example/payment/spi/PaymentFeeProvider.class

payment-provider-standard.jar
  com/example/payment/provider/StandardFeeProvider.class
  META-INF/services/com.example.payment.spi.PaymentFeeProvider

payment-provider-premium.jar
  com/example/payment/provider/PremiumFeeProvider.class
  META-INF/services/com.example.payment.spi.PaymentFeeProvider
```

If both provider JARs are on the classpath, `ServiceLoader` can find both of their descriptors through the classloader mechanism. However, **packaging into an uber/fat JAR** can cause files at the same path to overwrite each other if the packaging tool does not merge service descriptor contents.

### 5.1. Maven Shade Plugin

When using the Maven Shade Plugin to build an uber JAR, configure a transformer to merge service files instead of letting one descriptor overwrite another:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation=
                        "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
```

This configuration is for cases where you are actually building a shaded/uber JAR. Spring Boot executable JARs use their own nested JAR mechanism; do not blindly add the Shade Plugin to every Spring Boot project. If using multiple packaging tools, inspect the final output rather than assuming every tool merges service descriptors identically.

### 5.2. Gradle Shadow Plugin

If a Gradle project uses the Shadow Plugin to build an uber JAR, you can instruct it to merge service files:

```groovy
tasks.shadowJar {
    mergeServiceFiles()
}
```

This is a Shadow Plugin setting, not a default setting of the Gradle Java plugin or Spring Boot plugin. For a Spring Boot executable JAR, inspect nested dependency JARs and descriptor contents according to Spring Boot's packaging layout before adding another plugin.

### 5.3. Inspecting Descriptors Inside a JAR

Use the JDK tool:

```bash
jar tf target/payment-app.jar
```

Look for the path `META-INF/services/com.example.payment.spi.PaymentFeeProvider`. In a Spring Boot executable JAR, the descriptor may reside in `BOOT-INF/classes/META-INF/services/` or inside a dependency JAR under `BOOT-INF/lib/`. Run `jar tf` on individual dependencies when you need to verify providers contributed by libraries.

To view the contents of a file inside the JAR:

```bash
unzip -p target/payment-app.jar \
  BOOT-INF/classes/META-INF/services/com.example.payment.spi.PaymentFeeProvider
```

The example path above only applies when the descriptor is in the application's classes directory. If the descriptor resides inside a nested dependency JAR, extract that dependency and inspect it separately. Do not use a single assumed path to conclude a provider is missing.

## 6. Java Module System: uses and provides

Beyond classpath descriptors, the Java Platform Module System (JPMS) has a mechanism for declaring services in `module-info.java`. In the consuming module, declare `uses`; in the implementing module, declare `provides ... with ...`.

Application module consuming the service:

```java
module com.example.payment.app {
    requires com.example.payment.spi;
    uses com.example.payment.spi.PaymentFeeProvider;
}
```

Module providing a provider:

```java
module com.example.payment.provider.standard {
    requires com.example.payment.spi;

    provides com.example.payment.spi.PaymentFeeProvider
        with com.example.payment.provider.StandardFeeProvider;
}
```

When running on the module path, `ServiceLoader` uses the service information in the module descriptor. For a provider in a named module, the provider class can expose a `public static` method named `provider` returning the service type, per `ServiceLoader` rules; when using a `provider` method, a public no-argument constructor like traditional classpath provider classes is not strictly required.

Distinction:

| Deployment approach | Where providers are declared | Environment |
| --- | --- | --- |
| Classpath SPI | `META-INF/services/<service-FQCN>` | Classpath, regular JARs |
| Modular SPI | `module-info.java` with `provides` | Module path, named modules |
| Consuming module | `module-info.java` with `uses` | Named module requiring the service |

Do not declare both approaches simultaneously without reason. Determine whether the application runs on the classpath or module path, and verify the artifact structure and launch configuration accordingly.

## 7. ServiceLoader and Spring Dependency Injection

Both SPI and Spring DI can supply multiple implementations, but their purpose and lifecycle differ.

| Criterion | Java ServiceLoader | Spring dependency injection |
| --- | --- | --- |
| Registration | Descriptor or module `provides` | Bean definition, component scan, `@Bean` |
| Discovery | ClassLoader/module layer | ApplicationContext |
| Lifecycle | `ServiceLoader` manages discovery/caching of provider instances | Spring manages scope, lifecycle, and post-processors |
| AOP/transactions | Does not create Spring proxies automatically | Beans can receive proxies/advice |
| Spring-independent libraries | Well suited | Requires Spring dependency |
| Extension via dependency | Can add provider JARs to classpath at build time | Add beans/configuration to context |

If all implementations are Spring beans and the application wants to use transactions, security advice, configuration binding, or Spring's lifecycle, it is usually better to inject a collection of beans:

```java
@Service
class PaymentFeeRegistry {

    private final Map<String, PaymentFeeProvider> providers;

    PaymentFeeRegistry(List<PaymentFeeProvider> providerList) {
        this.providers = providerList.stream()
            .collect(Collectors.toUnmodifiableMap(
                PaymentFeeProvider::code,
                Function.identity()
            ));
    }

    PaymentFeeProvider get(String code) {
        PaymentFeeProvider provider = providers.get(code);
        if (provider == null) {
            throw new IllegalArgumentException("Unknown provider: " + code);
        }
        return provider;
    }
}
```

If you want to keep SPI so a library stays Spring-independent, you can create a Spring adapter that reads `ServiceLoader` and registers the results under a clear design. Do not mix the two mechanisms without clarifying which providers are container-managed. A provider instantiated by `ServiceLoader` does not automatically become a Spring bean and does not inherently receive dependency injection, AOP, or lifecycle callbacks.

## 8. How Does GraalVM Native Image Detect ServiceLoader?

Native Image performs reachability analysis at build time. Some dynamic Java behaviors cannot be inferred from a static call graph alone. `ServiceLoader` is a case where GraalVM provides dedicated support: Native Image can analyze provider configuration files on the classpath and module service declarations to identify service providers during the build.

This means **an application using standard `ServiceLoader` does not automatically need manual reflection hints for every provider**. First, use the standard `ServiceLoader` API, place descriptors in the right location, ensure provider classes and dependencies are on the build classpath/module path, and test the native executable.

However, distinguish between these scenarios:

- **Standard ServiceLoader:** descriptors and providers are present on the classpath/module path when the native image is built. GraalVM has built-in detection; verify with build and runtime tests.
- **Reading descriptors as ordinary resources:** if code directly calls `getResourceAsStream("META-INF/services/...")` to read the contents, that is a separate resource access path. When automatic metadata does not detect it, `ResourceHints` may be needed for that specific descriptor.
- **Instantiating providers manually via reflection:** if code uses `Class.forName`, `getDeclaredConstructor().newInstance()`, or custom reflection mechanisms, declare corresponding reflection hints when analysis does not detect them.
- **Plugins installed after the native executable is built:** new provider classes and descriptors will not magically appear in an already-built binary. Providers must be present at build time, or you need a different out-of-process extension architecture suitable for native.
- **Custom ClassLoader/ModuleLayer:** discovery differs from the default classpath; verify support in your GraalVM version and packaging approach.

Do not register all of `META-INF/**` or reflection for an entire package just to make the build pass. Identify the exact discovery path and add minimal metadata when there is evidence something is missing.

### 8.1. When You Need to Register a Resource Hint for a Descriptor

If the application actually reads a descriptor as a resource file, you can declare a precise pattern via `RuntimeHints`:

```java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class PaymentSpiResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern(
            "META-INF/services/com.example.payment.spi.PaymentFeeProvider"
        );
    }
}
```

Link the registrar to Spring AOT:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentSpiResourceHints.class)
class NativeSpiConfiguration {
}
```

This is an example for cases where the descriptor needs to be accessed as a regular resource or automatic metadata does not cover the application's specific reading pattern. If you only use standard `ServiceLoader` and GraalVM already detects the providers automatically, do not add this hint mechanically.

### 8.2. When You Need a Reflection Hint for a Provider

If the application instantiates providers manually via reflection instead of calling `ServiceLoader`, you may need to declare the appropriate constructor/method:

```java
hints.reflection().registerType(
    StandardFeeProvider.class,
    MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
);
```

Do not assume every provider requires such declarations. GraalVM's `ServiceLoader` support and library metadata may already handle discovery/instantiation. Reflection hints only solve the described reflective access; they do not fix wrong descriptors, missing dependencies, or incompatible custom classloaders.

## 9. Testing SPI on the JVM and Native Image

### 9.1. Unit Test for Provider Discovery

A simple test confirms that expected providers are discovered:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ServiceLoader;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class PaymentFeeProviderTests {

    @Test
    void discoversExpectedProviders() {
        Set<String> providerCodes = ServiceLoader
            .load(PaymentFeeProvider.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .map(PaymentFeeProvider::code)
            .collect(Collectors.toSet());

        assertTrue(providerCodes.contains("standard"));
        assertTrue(providerCodes.contains("premium"));
    }
}
```

This test must run with the proper provider JARs/dependencies on the test runtime classpath. If the test runs only inside the SPI module without provider dependencies, an empty result is expected for that classpath; configure the test module accordingly.

### 9.2. Verifying Descriptors and Provider Constructors

Beyond unit tests, verify:

1. The descriptor filename matches the fully qualified name of the service interface.
2. Descriptor contents point to provider classes in the right package.
3. Provider classes have constructors and visibility matching the registration style.
4. Provider classes are on the dependency/classpath during the native build.
5. If using an uber JAR, descriptors from dependencies are merged.
6. If using JPMS, the consumer module has `uses` and the provider module has `provides`.

You can write tests checking the provider count or list of provider class names to catch overwritten descriptors, missing dependencies, or duplicate declarations.

### 9.3. Building and Running the Native Executable

With Maven configured for Spring AOT and Native Build Tools:

```bash
./mvnw -Pnative native:compile
./target/payment-app
```

With Gradle:

```bash
./gradlew nativeCompile
./build/native/nativeCompile/payment-app
```

Executable paths depend on artifact name and plugin configuration. Call an endpoint/job that actually uses the service provider, then verify the result matches the JVM. If providers are initialized lazily, tests must trigger that branch; merely starting the context successfully does not prove discovery works.

### 9.4. Required Compatibility Test Suite

| Check | What to prove |
| --- | --- |
| JVM discovery | `ServiceLoader` finds expected providers |
| Descriptor | File is at the right path; interface and provider class names are valid |
| Dependency packaging | Provider JARs and descriptors are not excluded or overwritten |
| ClassLoader | `ServiceLoader` uses a classloader that sees both interface and providers |
| Provider construction | Constructor/provider method works without throwing `ServiceConfigurationError` |
| Native discovery | Native executable discovers the same provider set as the JVM |
| Business behavior | Providers execute business logic and error handling properly |
| Container target | Binary and dependencies are compatible with target OS/CPU/runtime image |

## 10. Common Errors and How to Handle Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Provider not found | Missing/misnamed descriptor or provider dependency not on classpath | Check `META-INF/services/<service-FQCN>` and dependencies |
| `ServiceConfigurationError` | Provider class does not exist, is not assignable, or fails to instantiate | Check class name, interface, constructor, and initialization errors |
| Found on JVM, missing in native | Provider absent at build time, metadata/build tool missed discovery path | Verify classpath/build log; check Native Image support and add targeted metadata |
| Only one provider appears after packaging | Service descriptors overwritten in uber JAR | Use transformer/merge service files; inspect final artifact |
| Provider in descriptor cannot be loaded | ClassLoader cannot see class or provider constructor is unsuitable | Specify proper classloader; check module/classpath |
| Directly read resource descriptor returns null | Descriptor not packaged or missing resource metadata | Inspect JAR and add exact resource hint when needed |
| `ClassNotFoundException` in custom discovery | Provider name chosen from runtime config or custom classloader | Check class name, dependencies, and dynamic loading capability in native |
| Provider instantiated multiple times | Creating a new `ServiceLoader` or calling provider factory in multiple places | Define desired scope/lifecycle; manage registry clearly |
| Swapped provider JAR after build, native unchanged | Provider set was fixed when creating the executable | Rebuild native image or design out-of-process extension protocol |
| JPMS cannot find provider | Missing `uses`/`provides`, incorrect module path | Check module descriptors and modular launch configuration |

Do not fix discovery errors by registering every class in a package or opening all of `META-INF`. First determine whether the bug lies in the descriptor, dependency, classloader, constructor, module declaration, or native metadata.

## 11. Hands-On Exercise: Registering and Running Two Providers

**Context:** A Spring Boot application calculates payment fees via `PaymentFeeProvider`. There are two providers: `StandardFeeProvider` and `PremiumFeeProvider`.

**Steps:**

1. Create the `PaymentFeeProvider` service interface.
2. Create two provider implementations with no-argument constructors suitable for classpath SPI.
3. Create the file `META-INF/services/com.example.payment.spi.PaymentFeeProvider`.
4. List the fully qualified names of both providers, one per line.
5. Write a service using `ServiceLoader.load(PaymentFeeProvider.class)` to find providers by code.
6. Run unit tests on the JVM and verify both providers are discovered.
7. Inspect descriptors in the JAR and dependency JARs; if using a shaded JAR, verify service descriptors were merged.
8. Build the GraalVM Native Image and call an actual endpoint to verify provider discovery.
9. If the code reads the descriptor directly or uses reflection/custom classloaders, identify needed metadata; do not add unnecessary hints.
10. Compare the provider set and business results between the JVM and the native executable.

**Pass criteria:**

- Service interface does not depend on concrete implementations.
- Descriptor has a compliant filename and contents.
- Both providers are discovered on the JVM.
- Dependencies/descriptors are not lost during packaging.
- Native executable locates providers and returns accurate business results.
- Understand when GraalVM supports `ServiceLoader` automatically and when `ResourceHints`/reflection hints are required.
- Know the limitation of dynamic plugins added after the native image is built.

## 12. Summary

Java `ServiceLoader` implements SPI by separating the **service interface**, **provider implementation**, and **provider configuration**. On the classpath, providers are declared in `META-INF/services/<fully-qualified-service-interface>`, with one fully qualified provider name per line. On the Java Module System, consumers use `uses` and provider modules declare `provides ... with ...`.

GraalVM Native Image has dedicated support for `ServiceLoader` and can detect provider declarations during build-time analysis. Therefore, start with proper descriptors, dependencies, and classloaders; only add `ResourceHints` when the application reads descriptors as resources or automatic handling does not cover your specific case, and only add reflection hints when code genuinely uses reflection requiring metadata. Test on the **actual native executable** to prove the provider set and business behavior match the JVM build.
