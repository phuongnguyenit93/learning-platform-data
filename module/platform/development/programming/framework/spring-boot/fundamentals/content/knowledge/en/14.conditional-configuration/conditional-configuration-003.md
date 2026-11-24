# `@ConditionalOnClass`, `@ConditionalOnMissingClass`, and the Classpath

Spring Boot can automatically configure a feature when the required library appears in the application, or skip that feature when the library is absent. This mechanism is especially useful for starters and integration libraries: the application only needs to add the appropriate dependency, while Spring Boot decides which configurations can participate based on the actual environment.

Two annotations commonly used to express conditions on class presence are:

- **@ConditionalOnClass**: the condition is satisfied when the specified classes are present on the classpath accessible to Spring.
- **@ConditionalOnMissingClass**: the condition is satisfied when the specified classes are absent from that classpath.

To understand these two annotations properly, you need a solid grasp of the **classpath**, **class loaders**, the difference between compile-time and runtime, and how Spring evaluates conditions while building the ApplicationContext. Simply seeing an import in source code or a dependency in a build file is not enough to conclude that the condition will be satisfied when the application runs.

## 1. What Is the Classpath?

In Java, the **classpath** is the set of locations the compiler or runtime uses to look up classes and resources. Common locations include:

- Directories containing `.class` files.
- Library `.jar` files.
- Resource directories placed on the classpath.
- Artifacts provided to the application by the build tool and runtime environment.

Example of an application with a dependency structure:

~~~text
Spring Boot Application
├── application classes
├── spring-context.jar
├── spring-boot-autoconfigure.jar
├── vendor-client.jar
└── vendor-common.jar
~~~

If `vendor-client.jar` contains the class `com.vendor.client.VendorClient`, the runtime class loader can find that class when the application runs, provided the JAR is on the appropriate classpath or module path and there are no class-loading issues.

The classpath is part of the **Java runtime environment**. Spring Boot uses it to decide whether auto-configurations fit the current application.

### 1.1. An Import in Source Does Not Mean the Class Is on the Runtime Classpath

A Java file can have:

~~~java
import com.vendor.client.VendorClient;
~~~

An import only helps source code reference a type name. To compile, the compiler needs to find that type on the compile classpath. For the application to use that type at runtime, the corresponding class and its required dependencies must be present on the runtime classpath.

A library might be declared only for compilation, without being packaged for runtime. In that case:

- The code can compile successfully.
- The application can fail when loading the class at runtime.
- The classpath condition in Spring Boot may not be satisfied when the context is created.

Therefore, when an auto-configuration does not behave as expected, inspect the **actual runtime classpath**, not just the dependency declaration line.

### 1.2. The Classpath Can Differ Between Compile, Test, and Runtime

In Gradle, some common configurations are:

| Configuration | Typical role |
|---|---|
| **implementation** | Dependency of main code, participating in compile and runtime under the Java plugin model. |
| **compileOnly** | Present on the compile classpath but not automatically included on the main runtime classpath. |
| **runtimeOnly** | Needed at runtime but not needed to compile main sources. |
| **testImplementation** | Dependency used for test sources and the test classpath. |
| **testRuntimeOnly** | Dependency needed only when running tests. |

Example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    compileOnly 'com.vendor:vendor-client:2.1.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If `VendorClient` is only in `compileOnly`, code referencing it directly can compile, but the main application runtime will not necessarily have that JAR. When Spring evaluates the condition in the running application, the class may be considered absent.

With Maven, scopes such as `compile`, `runtime`, `test`, and `provided` also affect which artifacts are placed on each classpath. Do not mechanically map Maven scope names to Gradle configuration names; check the exact build model of the project.

### 1.3. The Test Classpath Can Cause Conditions to Produce Different Results from Production

Suppose a test declares a client dependency in `testImplementation`, while the production application does not have the corresponding dependency at runtime. The test context may see the class and activate auto-configuration; when running the production executable JAR, that class is no longer on the runtime classpath, so the configuration is skipped or direct references fail.

This is why you need to distinguish:

- Tests have their own classpath.
- IDEs can construct their own runtime classpath for run configurations.
- `bootRun` uses Gradle's runtime classpath.
- An executable JAR contains the runtime dependencies packaged by the plugin.
- Production environments may add or alter class loading according to deployment settings.

Classpath conditions are evaluated in the **class loader that Spring uses at context runtime**, not based on the list of dependencies you remember declaring.

## 2. Class Loader and Class Lookup Capability

The JVM uses a **ClassLoader** to locate and load class definitions when needed. An application may have multiple class loaders, such as the application class loader, container class loader, or dedicated plugin loaders.

One way to visualize it:

~~~text
Spring ApplicationContext
        │
        ▼
ClassLoader used to check the class
        │
        ├── finds com.vendor.client.VendorClient
        │       └── OnClass condition can match
        │
        └── class not found
                └── OnClass condition does not match
~~~

Therefore, saying "the JAR is on the machine" is not enough. The JAR must be on the classpath/module path appropriate for the process and class loader that needs it. A JAR sitting in a downloads folder, Gradle cache, or an unconfigured directory does not automatically become an application dependency.

### 2.1. Class Presence Does Not Mean the Class Is Usable in Every Case

A class file may be found, but when the JVM actually links or initializes the class, it may need another class that does not exist. For example:

~~~text
vendor-client.jar
└── VendorClient.class
      └── references VendorTransport.class

runtime classpath:
└── vendor-client.jar
    (missing vendor-transport.jar)
~~~

A condition checking the presence of `VendorClient` does not replace verifying that the entire dependency graph is compatible and complete. When the class is used, the application can still encounter `NoClassDefFoundError`, `ClassNotFoundException`, linkage errors, or binary compatibility errors.

### 2.2. Classpath Conditions Do Not Verify Library Correctness

`@ConditionalOnClass` checks whether the specified class can be found. It does not verify:

- Whether the library version matches what Spring Boot supports.
- Whether the methods called by the application exist.
- Whether the API and implementation are binary-compatible.
- Whether transitive dependencies are complete.
- Whether the external service is configured and working.

A satisfied condition only indicates **a classpath signal**. Subsequent steps of bean instantiation and library usage can still fail for other reasons.

## 3. What Is `@ConditionalOnClass`?

`@ConditionalOnClass` is a Spring Boot annotation in the package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionalOnClass
~~~

It marks a configuration class or a `@Bean` method to be considered only when the required class is present.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(VendorClient.class)
public class VendorClientConfiguration {

    @Bean
    VendorService vendorService(VendorClient client) {
        return new VendorService(client);
    }
}
~~~

If `VendorClient.class` can be found by the classpath checking mechanism, the condition can match and the configuration is considered. If the class is absent, the configuration is skipped.

In an auto-configuration library, the goal is usually:

~~~text
Is vendor-client on the classpath?
          │
     ┌────┴────┐
     │         │
    Yes        No
     │         │
     ▼         ▼
Consider    Skip client
client      integration
config      config
~~~

This allows applications that do not use the vendor client to run without pulling that library in.

### 3.1. Using Class Literals in the `value` Attribute

The annotation supports declaring classes directly:

~~~java
@ConditionalOnClass(VendorClient.class)
~~~

Or multiple classes:

~~~java
@ConditionalOnClass({
    VendorClient.class,
    VendorTransport.class
})
~~~

When specifying multiple classes in a single `@ConditionalOnClass`, the condition requires **all listed classes to be present**. This is an AND relationship, not an OR.

### 3.2. Using the `name` Attribute

The annotation also supports class names as Strings:

~~~java
@ConditionalOnClass(
    name = "com.vendor.client.VendorClient"
)
~~~

The `name` attribute is useful when:

- You want to avoid importing the optional type into the auto-configuration source.
- You are writing a condition in a module that should not have a direct compile dependency on the checked library.
- You want to express the full class name as a string.

The name must be a **fully qualified class name**, including the package.

Multiple classes can be listed:

~~~java
@ConditionalOnClass(name = {
    "com.vendor.client.VendorClient",
    "com.vendor.transport.VendorTransport"
})
~~~

Here too, all required classes must be present for the condition to be satisfied.

### 3.3. Are Class Literals Safe When the Optional Library Is Absent?

Spring Boot has a mechanism that reads annotation metadata using ASM to evaluate conditions on configuration classes. As a result, **class literals in class-level annotations** can be processed without requiring the JVM to load the optional type in the usual way before the condition is checked.

The following example is a common usage in auto-configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(VendorClient.class)
public class VendorAutoConfiguration {
    // ...
}
~~~

The class-level condition is processed from metadata, so Spring Boot can skip the configuration class when `VendorClient` is absent.

However, do not generalize this into "writing optional classes anywhere is safe." **Method signatures, superclasses, interfaces, fields, or initialization code of a class can still cause the JVM to resolve the optional type too early.** A later section explains how to isolate configurations to avoid that error.

## 4. What Is `@ConditionalOnMissingClass`?

`@ConditionalOnMissingClass` is the opposite condition: the configuration is considered when the specified classes are **absent**.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.vendor.client.VendorClient")
public class FallbackClientConfiguration {

    @Bean
    LocalVendorService localVendorService() {
        return new LocalVendorService();
    }
}
~~~

If `VendorClient` does not appear on the classpath, the fallback configuration can be applied. If `VendorClient` is present, this configuration is skipped.

### 4.1. Declaring One or More Class Names

~~~java
@ConditionalOnMissingClass({
    "com.vendor.client.VendorClient",
    "com.vendor.transport.VendorTransport"
})
~~~

With multiple class names, the condition only matches when **all listed classes are absent**. If even one class appears, the condition is no longer satisfied.

This is also AND logic over the "must be absent" requirement. It does not mean "just one class in the list is absent."

If you need to express complex OR logic, you can use multiple configuration classes with separate conditions, a custom `Condition`, or an appropriate configuration structure. Do not misinterpret the meaning of the class list in the annotation.

### 4.2. Using a Fallback When the Main Library Is Missing

An integration library may operate in two ways:

- Use the vendor implementation when the SDK is present.
- Use a fallback implementation when the SDK is absent.

Conceptual example:

~~~java
@AutoConfiguration
public class SearchIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.search.SearchClient")
    static class VendorSearchConfiguration {
        @Bean
        SearchService vendorSearchService(SearchClient client) {
            return new VendorSearchService(client);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingClass("com.vendor.search.SearchClient")
    static class LocalSearchConfiguration {
        @Bean
        SearchService localSearchService() {
            return new LocalSearchService();
        }
    }
}
~~~

`SearchClient`, `SearchService`, `VendorSearchService`, and `LocalSearchService` are illustrative types. In real code, ensure optional types are only referenced inside configurations protected by appropriate conditions.

The two branches above illustrate this way of thinking:

~~~text
Is SearchClient on the classpath?
            │
       ┌────┴────┐
       │         │
      Yes        No
       │         │
       ▼         ▼
Vendor search  Local fallback
configuration  configuration
~~~

Avoid letting both branches register a bean without clear selection rules. When the same bean name or type is needed, design mutually exclusive conditions and write tests for both branches.

## 5. Distinguishing `@ConditionalOnClass` from `@ConditionalOnBean`

The two annotations have similar names, but they check two different layers of information:

| Annotation | What does it check? |
|---|---|
| **@ConditionalOnClass** | Is the class present on the classpath/class loader? |
| **@ConditionalOnMissingClass** | Is the class absent from the classpath/class loader? |
| **@ConditionalOnBean** | Does the Spring context already have a matching bean? |
| **@ConditionalOnMissingBean** | Does the Spring context not yet have a matching bean? |

For example, the `vendor-client.jar` dependency may be on the runtime classpath, yet there is no `VendorClient` bean:

~~~text
vendor-client.jar is present
        │
        ▼
VendorClient.class can be found
        │
        ├── @ConditionalOnClass can match
        │
        └── But a VendorClient bean does not necessarily exist
~~~

Class presence does not automatically create a bean. A bean must be registered via component scanning, `@Bean`, auto-configuration, or another registration mechanism.

Conversely, a bean may be created by a factory or another implementation without the specific class you intended to check. Therefore, classpath conditions and bean conditions answer two different questions.

### 5.1. Combining Classpath Conditions and Bean Conditions

An auto-configuration can use both:

~~~java
@AutoConfiguration
@ConditionalOnClass(VendorClient.class)
public class VendorAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(VendorService.class)
    VendorService vendorService(VendorClient client) {
        return new VendorService(client);
    }
}
~~~

Meaning:

1. The required SDK class must be on the classpath for the configuration to be considered.
2. Only if the application has not provided a matching `VendorService` does Boot create the default bean.
3. If the application already has its own `VendorService`, the default configuration steps aside.

Here **@ConditionalOnClass** guards the optional integration, while **@ConditionalOnMissingBean** lets the user replace the default bean.

## 6. When Are Classpath Conditions Evaluated?

Spring Boot conditions are typically evaluated during configuration processing and `ApplicationContext` construction. They are not switches continuously re-checked on every HTTP request.

A conceptual sequence:

~~~text
SpringApplication starts
          │
          ▼
Environment and ApplicationContext prepared
          │
          ▼
Spring reads configuration and auto-configuration metadata
          │
          ▼
Evaluate classpath conditions
          │
          ├── Class present
          │       └── Configuration processing can continue
          │
          └── Class absent
                  └── Skip the corresponding configuration
          │
          ▼
Register matching bean definitions
          │
          ▼
Instantiate beans and finalize context
~~~

The classpath of a Java process is fundamentally established when the process starts. If you change JAR files on disk after the application is already running, the current class loader does not automatically refresh the entire classpath, nor does Spring automatically re-evaluate all conditions.

To change the set of libraries in use, you normally need to restart the process or use a dedicated class-loading/plugin architecture with explicit lifecycle management.

## 7. Using `@ConditionalOnClass` in Auto-Configuration

An important goal of Spring Boot is allowing libraries to provide auto-configuration without forcing every application to include every integration library.

Suppose the `acme-spring-boot-autoconfigure` library provides integration for the `acme-client` SDK. If a consumer does not use the SDK, they can still use other parts of the application without needing the `AcmeClient` class.

Simple example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeService acmeService(AcmeClient client) {
        return new AcmeService(client);
    }
}
~~~

The snippet illustrates the idea, but there is an important caveat: **if an optional type appears in the method signature of the outer configuration class, the JVM may need to resolve that type when processing class/method metadata**. A safer approach is to isolate methods referencing optional types into a conditional nested configuration.

### 7.1. Isolating Optional Types in Nested Configurations

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.client.AcmeClient")
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeService acmeService(AcmeClient client) {
            return new AcmeService(client);
        }
    }
}
~~~

Here, `AcmeClient` only appears inside a nested configuration guarded by the class condition. When the class is absent, Spring can skip that configuration branch before processing the methods that require the optional type.

This pattern is especially important when writing auto-configuration libraries used across many applications with differing dependency graphs.

### 7.2. Why Not Put Optional Types in the Outer Configuration?

Suppose the outer class has:

~~~java
@AutoConfiguration
public class AcmeAutoConfiguration {
    @Bean
    @ConditionalOnClass(name = "com.acme.client.AcmeClient")
    AcmeService acmeService(AcmeClient client) {
        return new AcmeService(client);
    }
}
~~~

Even though the method has a condition, `AcmeClient` is still in the method signature of the outer class. The JVM or framework may need to inspect method metadata before the method-level condition is applied in the way you expect. If the optional class is absent, there is a risk of a class linkage error occurring prematurely.

Placing the method inside a conditional nested configuration helps Spring separate metadata containing optional types from the configuration that is always loaded.

### 7.3. When to Use Class Literals vs. When to Use `name`?

At the class level of an auto-configuration, a class literal is often clear:

~~~java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
public class AcmeAutoConfiguration {
}
~~~

When you want to avoid a direct compile-time reference to the optional class, use the name:

~~~java
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
~~~

Whether you use a class literal or `name`, the key rule remains **isolating signatures and code that actually depend on the optional type**. The `name` attribute does not by itself fix a method signature that already references an absent class.

## 8. `@ConditionalOnMissingClass` and Fallback Configuration

Some libraries provide an alternative implementation when the main library is absent. Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.acme.search.ElasticClient")
public class LocalSearchConfiguration {

    @Bean
    SearchService localSearchService() {
        return new LocalSearchService();
    }
}
~~~

When `ElasticClient` is absent, the local configuration can be considered. When that class appears, the local configuration is skipped.

### 8.1. Ensuring Both Branches Do Not Register Competing Beans

If there is a vendor branch and a fallback branch, design the conditions so they do not both register indistinguishable beans.

Conceptual example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.acme.search.ElasticClient")
class ElasticSearchConfiguration {
    @Bean
    SearchService searchService(ElasticClient client) {
        return new ElasticSearchService(client);
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingClass("com.acme.search.ElasticClient")
class LocalSearchConfiguration {
    @Bean
    SearchService searchService() {
        return new LocalSearchService();
    }
}
~~~

Two conditions on the same class are opposites, so logically one of the two branches is chosen. In real code, still ensure both configurations are registered properly and optional types are not referenced prematurely in an outer class.

### 8.2. Is a Fallback Always a Good Choice?

No. If the primary SDK is mandatory for a function, silently switching to another implementation can alter semantics or data guarantees.

Only use a fallback when the alternative implementation genuinely satisfies the contract consumers expect. If the feature must be disabled or startup must fail clearly without the primary library, design the conditions and error reporting according to that contract.

## 9. Optional Dependencies and Library Design

A Spring Boot library can be split into modules:

~~~text
acme-spring-boot-starter
├── acme-spring-boot
│   └── dependency metadata / starter
└── acme-spring-boot-autoconfigure
    ├── core integration
    └── optional integration
         └── acme-client (optional)
~~~

Depending on artifact organization, the auto-configuration module can declare optional dependencies so consumers are not forced to pull in the SDK if they do not use that integration.

When designing:

1. Separate core API/functionality that does not depend on optional SDKs.
2. Put code referencing the SDK in an appropriate module or nested configuration.
3. Guard auto-configuration with `@ConditionalOnClass`.
4. Register beans only when the classpath has all necessary components.
5. Allow consumers to provide their own beans if the library supports customization.
6. Test both when the SDK is present and when it is absent.

Classpath conditions are part of the optional dependency contract. They enable a starter to work across many applications with different dependency graphs.

### 9.1. Do Not Expose Optional Types in Mandatory Public APIs

If the core module publishes an API whose public signature directly requires a class from an optional SDK, consumers may be forced to have the SDK even when they do not use that feature.

Consider:

- Placing integration adapters in a separate module.
- Using internal interfaces in the core library.
- Referencing vendor types only in guarded configuration branches.
- Avoiding having core classes extend or implement an optional type that is not always present.

`@ConditionalOnClass` helps make configuration conditional, but it cannot fix an API design that forces every consumer to load an optional class.

## 10. Important Limitations of Class Conditions

### 10.1. Does Not Confirm a Bean Is Registered

`VendorClient.class` being present does not mean Spring created a `VendorClient` bean. A separate bean registration mechanism is required, such as component scanning or `@Bean`.

### 10.2. Does Not Validate External Configuration

The client class may exist, while the base URL, credentials, timeout, or endpoint is unconfigured. The condition can still match; errors only appear when creating the bean or using the client.

### 10.3. Does Not Check Version Compatibility

The condition can match with an older or newer SDK version. If code was compiled against a different API than the version running at runtime, you may hit `NoSuchMethodError`, `NoSuchFieldError`, or other linkage errors.

### 10.4. Does Not Guarantee Complete Transitive Dependencies

The target class may be found while another class it needs is missing. When the JVM links or runs the code, errors may occur.

### 10.5. Is Not Re-Evaluated Continuously

Conditions are evaluated during context creation. Adding a JAR or changing a class loader manually afterward does not automatically cause Spring to re-register beans.

### 10.6. Does Not Replace `@ConditionalOnBean`

The classpath is a signal of library availability. If you need to know whether the Spring context already has a specific bean, use a bean condition.

## 11. Combining Class Conditions with Other Conditions

A real auto-configuration often combines multiple conditions:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
@ConditionalOnProperty(
    prefix = "acme.client",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeService.class)
    AcmeService acmeService(AcmeClient client) {
        return new AcmeService(client);
    }
}
~~~

This example represents three decision layers:

1. The SDK class must be present.
2. The property enables the feature.
3. The application has not provided a replacement `AcmeService`.

The conditions are combined according to the requirements at each configuration/method level. If a mandatory condition fails, the corresponding part is not applied.

~~~text
Is AcmeClient on the classpath?
          │
          ├── No → Skip configuration
          │
          ▼ Yes
acme.client.enabled = true?
          │
          ├── No → Skip configuration
          │
          ▼ Yes
Does the application already have AcmeService?
          │
          ├── Yes → Default bean backs off
          │
          ▼ No
Create default AcmeService
~~~

If `AcmeClient` is an optional type, apply the nested configuration rule discussed earlier so you do not inadvertently force the JVM to resolve the class before the class condition is checked.

## 12. Diagnosing When `@ConditionalOnClass` Does Not Match

Suppose you expect `AcmeAutoConfiguration` to be applied, yet the bean does not appear. Check in order:

### Step 1: Confirm the Dependency Is on the Runtime Classpath

Inspect the build file and dependency resolution for the proper configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree
~~~

These are illustrative commands to inspect the dependency graph. Select the right module and configuration of the application. Do not infer the runtime classpath from test dependencies.

### Step 2: Check Which JAR Actually Contains the Class

A dependency may resolve, yet the artifact does not contain the class name checked by the annotation, due to:

- A different artifact or module.
- A different version.
- Package/class changes between versions.
- The dependency being excluded or substituted.
- The class residing only in another optional artifact.

Verify the fully qualified class name and artifact contents.

### Step 3: Check the Class Loader and Runtime Environment

If running in an IDE, test, `bootRun`, and executable JAR produce different results, compare their respective runtime classpaths. Also consider applications running inside servlet containers or environments with custom class loaders.

### Step 4: Inspect the Condition Evaluation Report

Launch with `--debug`:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot can print the **Condition Evaluation Report** in the startup logs. Look for the relevant auto-configuration and the reason the condition did not match.

Illustrative snippet:

~~~text
Negative matches:
-----------------
AcmeClientAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find required class
        'com.acme.client.AcmeClient'
~~~

Configuration names and wording are illustrative; actual output depends on the Boot version and how the condition is declared.

### Step 5: Check Whether It Was Excluded or Blocked by Another Condition

Even when the class condition matches, the configuration may be:

- Excluded via `exclude`, `excludeName`, or `spring.autoconfigure.exclude`.
- Failing `@ConditionalOnProperty`.
- Failing `@ConditionalOnBean` or `@ConditionalOnMissingBean` at the method level.
- Eliminated by a web application or resource condition.

The condition report helps distinguish these causes.

## 13. Diagnosing When the Condition Matches but the Application Still Fails

If the class condition matched yet the application fails to create the bean or startup fails, move on to check the subsequent stages:

### 13.1. Missing Linked Dependency

The target class exists, but initializing it requires another class that is missing. You may encounter `NoClassDefFoundError` or a linkage error.

### 13.2. Incompatible Version

The code was compiled against one API, while runtime loads a different version. You may see `NoSuchMethodError`, `AbstractMethodError`, or other compatibility errors.

### 13.3. Missing Bean Dependency

The SDK class is present, but the auto-configuration requires a user-provided bean or another bean that has not been registered yet. The error is then a dependency injection issue rather than a simple classpath condition.

### 13.4. Invalid Client Configuration

Invalid base URLs, tokens, or properties can cause the factory method or constructor to fail.

### 13.5. Factory Method Throws an Exception

The bean definition was selected, yet instance creation failed. Read `BeanCreationException` and the full `Caused by` chain to find the root cause.

Key point: **a condition match only allows the configuration to be considered; it does not guarantee the bean initializes successfully or the feature works properly**.

## 14. Testing Both Class-Present and Class-Absent Cases

An auto-configuration with a classpath condition should be tested on both sides. Spring Boot Test provides **ApplicationContextRunner** and related context runners to create lightweight contexts and verify registered beans under specific configurations.

Example configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.client.AcmeClient")
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeService acmeService() {
        return new AcmeService();
    }
}
~~~

To test an actual classpath condition, the test must run with the corresponding classpath. Merely changing a property cannot make a class already on the test classpath disappear from the class loader.

### 14.1. Testing the Class-Present Branch

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AcmeAutoConfigurationTests {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void createsServiceWhenClientClassIsPresent() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeService.class);
        });
    }
}
~~~

This test only succeeds if the required class is actually on the test runtime classpath and the configuration has no other missing required dependencies. In the illustrative example, `AcmeAutoConfiguration` compiles using the class name as a string; the bean method does not reference the SDK, so no client bean is needed.

### 14.2. Testing the Class-Absent Branch

To test class absence, you need a test runtime classpath **without the artifact providing that class**, or a dedicated class loader/test fixture designed for that purpose.

You cannot simulate an absent class solely with:

~~~java
.withPropertyValues("acme.client.enabled=false")
~~~

because properties do not alter the classpath. They only affect property conditions, if the configuration uses `@ConditionalOnProperty`.

A practical approach is to split optional auto-configuration tests into modules/test source sets with controlled dependencies, so one test runs when the SDK is present and another runs when the SDK is excluded from the runtime classpath.

### 14.3. Testing Fallback Configurations

If a library has a `@ConditionalOnMissingClass` branch, verify:

- When the SDK is present, the fallback branch is not registered.
- When the SDK is absent, the fallback branch is registered.
- The two branches do not create duplicate bean names or unintended multiple candidates.
- Consumers receive the right implementation in each environment.

For optional integrations, testing both classpaths separately is often more important than checking a single default startup.

## 15. Real-World Usage Examples

### 15.1. Optional JSON Library Integration

A starter may provide an adapter only when a specific JSON library appears:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class JsonAdapterAutoConfiguration {
    // Configurations depending on Jackson.
}
~~~

If Jackson is absent, the adapter configuration does not participate. If present, Boot can proceed to evaluate required beans and properties.

### 15.2. Cloud Client Integration

A module may support an optional cloud SDK:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.cloud.CloudClient")
public class CloudIntegrationAutoConfiguration {
    // Register integration beans when the SDK is present.
}
~~~

Consumers not using the cloud SDK do not have to be forced to load that library just to use other parts of the starter.

### 15.3. Selecting an Implementation Based on Present Libraries

A library may have adapters for different versions or providers. Classpath conditions allow registering only adapters matching the available APIs. However, if multiple providers are present at the same time, you need to design ordering or qualifier/bean conditions to avoid ambiguity.

Do not use the classpath as the sole implementation selection mechanism if multiple libraries can appear together. In that case, add property, bean, or user configuration conditions.

## 16. Common Pitfalls

### 16.1. `@ConditionalOnClass` Does Not Match Even Though Dependency Is Declared

Possible causes include the dependency only being in `compileOnly`/`provided`/`test`, being excluded, or the class belonging to another artifact. Check the runtime classpath and fully qualified class name.

### 16.2. Class Is Present, Yet `NoClassDefFoundError` Still Occurs

The condition only checks the specified class. Another dependency required by that class may be missing. Inspect the cause chain and full dependency graph.

### 16.3. `@ConditionalOnMissingClass` Does Not Trigger

The checked class may actually be present on the runtime classpath via a transitive dependency or another starter. Inspect the dependency tree instead of only reading direct declarations.

### 16.4. Using Class Literals in a Method with Optional Types

A method-level class condition does not protect every type in the method signature from premature JVM resolution. Isolate the method into a nested configuration guarded by a class condition.

### 16.5. Using `name` While Still Referencing Optional Types in the Outer Class

`name` only changes how the class name is written in the annotation, without protecting fields, superclasses, constructors, method parameters, or return types that reference the optional class. Isolate the entire dependent part.

### 16.6. Confusing Class Conditions with Bean Conditions

A class being on the classpath does not mean a bean is registered. If you need to check for a bean, use `@ConditionalOnBean` or query the context.

### 16.7. Thinking Conditions Will Automatically Update When Adding a JAR at Runtime

Conditions are evaluated during context creation. Changing files on disk does not automatically update the classpath or bean registry of the running process.

### 16.8. Thinking a Condition Match Means the Feature Is Guaranteed to Work

A condition match does not confirm version compatibility, client configuration, external service connectivity, or successful bean creation.

## 17. Misconceptions to Avoid

**"Importing a class in Java means the class exists at runtime."**  
No. An import is source syntax; the runtime classpath must contain the class and its related dependencies.

**"A dependency appearing in `build.gradle` means `@ConditionalOnClass` is guaranteed to match."**  
No. You must check the configuration and actual runtime classpath.

**"`@ConditionalOnClass` checks whether a bean has been created."**  
No. It checks class presence, not the bean registry.

**"`@ConditionalOnMissingClass` is the opposite of `@ConditionalOnMissingBean`."**  
No. One annotation checks the classpath; the other checks beans in the Spring context.

**"Class presence means all dependencies of that class are also complete."**  
No. The class may be found, yet another class may still be missing during linking or execution.

**"Using the `name` attribute lets you reference an optional class in any method signature."**  
No. `name` only changes how the class name is written in the annotation; it does not protect other type references from early resolution.

**"`@ConditionalOnMissingClass` with two classes matches if either one is absent."**  
No. All listed classes must be absent for the condition to match.

**"Conditions are re-evaluated on every request."**  
No. Conditions are evaluated during configuration processing and context construction.

**"A positive match in the condition report proves the bean was created successfully."**  
No. The bean method may have its own conditions or fail during initialization.

## Core Takeaways

The **classpath** determines which classes the runtime can locate via a class loader. **@ConditionalOnClass** allows Spring Boot to apply a configuration only when required classes are present; **@ConditionalOnMissingClass** allows selecting a fallback branch when those classes are absent. When multiple classes are listed, the condition requires all specified classes to satisfy the corresponding state.

These two annotations are especially important when writing starters and auto-configurations with **optional dependencies**. Verify the actual runtime classpath, distinguish class presence from bean existence, and isolate methods/signatures referencing optional types in nested configurations guarded by class conditions. A condition match is only the configuration-selection step; bean creation, version compatibility, and service connectivity still need to be verified separately.
