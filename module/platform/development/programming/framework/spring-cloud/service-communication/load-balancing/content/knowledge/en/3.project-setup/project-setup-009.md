# Verifying Auto-Configuration Conditions and Library Conflicts

Spring Cloud LoadBalancer only works when the application has the right libraries, compatible versions, and required beans on the application context. Having a dependency present in the build file is not enough to conclude the feature is active: Spring Boot also evaluates auto-configuration conditions, and LoadBalancer needs a source providing a `ServiceInstance` list for the called service ID.

In this module, the application uses a service ID such as `inventory-service` to call the inventory service. Spring Cloud LoadBalancer selects an instance from the list supplied by a discovery client or static configuration source. When the client is misconfigured, the application might start without load balancing requests, or stop immediately during bean creation due to a missing class, missing bean, or version conflict. This lesson guides you through checking from dependencies down to auto-configuration conditions and identifying root causes before changing configuration.

## 1. Distinguish Three Layers to Verify

When diagnosing Spring Cloud LoadBalancer, separate three questions:

1. **Are the libraries on the runtime classpath?** The starter and core dependencies must resolve with compatible versions. If a required class is missing, `@ConditionalOnClass` is not satisfied and the corresponding configuration may not load.
2. **Is auto-configuration activated?** Spring Boot evaluates conditions on classes, beans, properties, application type, and more. An auto-configuration can be discovered yet skipped because a condition is not met.
3. **Does the application have the required data and client to call the service ID?** LoadBalancer needs an instance list for the service ID. The HTTP client must also be annotated or integrated with the corresponding load-balancing mechanism.

These three layers are related but do not substitute for each other. For example, `spring-cloud-starter-loadbalancer` may be resolved and auto-configuration may have run, yet `inventory-service` still has no instances to pick from. Conversely, the registry may contain full instances, while a plain `RestClient` not configured for load balancing fails to resolve the service ID.

## 2. Managing Dependencies with a Compatible BOM

Spring Boot and Spring Cloud release along separate version lines. The safe approach is to let Spring Boot manage Boot dependencies and import a Spring Cloud BOM from a release train compatible with your Spring Boot version. The BOM ensures modules such as `spring-cloud-commons`, `spring-cloud-loadbalancer`, OpenFeign, and discovery clients are selected from one synchronized version set.

Maven example:

```xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>YOUR_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Only add the discovery starter the application actually uses. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

`YOUR_COMPATIBLE_RELEASE_TRAIN` is a placeholder for the release train version matching your project's Spring Boot version. Consult the compatibility matrix in the Spring Cloud documentation when upgrading; do not copy a version number from another project without checking. Once the BOM manages dependencies, do not manually set individual versions on Spring Cloud starters.

With Gradle using native BOM support:

```groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation "org.springframework.cloud:spring-cloud-starter-loadbalancer"

    // Only add if the application uses Eureka as its discovery provider.
    implementation "org.springframework.cloud:spring-cloud-starter-netflix-eureka-client"
}
```

Declare `springCloudVersion` in the build's version management section. If the project already uses the `io.spring.dependency-management` plugin and imports BOMs via that plugin's configuration, continue following one consistent dependency management mechanism across the project.

Several notes when selecting starters:

- `spring-cloud-starter-loadbalancer` provides Spring Cloud LoadBalancer and related integrations.
- Discovery starters such as Eureka or Consul provide instance registration and lookup sources. Only add the provider the architecture actually uses.
- Spring Cloud OpenFeign and LoadBalancer are two separate integration pieces. If using OpenFeign to call by service ID, ensure LoadBalancer is on the runtime classpath according to the configuration of the Spring Cloud line in use.
- Do not directly add an arbitrary version of `spring-cloud-commons` or `spring-cloud-loadbalancer` as a quick fix when starters are already managed by the BOM.

## 3. How Does Auto-Configuration Evaluate Conditions?

Spring Boot uses auto-configuration classes to register default beans when conditions match. Common conditional annotations include:

| Condition | Question Spring Boot Evaluates | Example Scenario |
|---|---|---|
| `@ConditionalOnClass` | Is the specified class on the classpath? | Configure an HTTP client integration only when the corresponding client library is present. |
| `@ConditionalOnMissingClass` | Is the specified class absent? | Choose a configuration branch when an optional library is not installed. |
| `@ConditionalOnBean` | Does the application context already contain a matching bean? | An extension configuration runs only when the required foundational bean exists. |
| `@ConditionalOnMissingBean` | Does a matching bean not yet exist? | Provide a default bean while backing off for an application-declared bean. |
| `@ConditionalOnProperty` | Does the property value satisfy the condition? | Enable or disable part of configuration via a property. |
| `@ConditionalOnWebApplication` | Is the application the right web application type? | Register configuration intended for web applications only. |

Conditions can be combined. An auto-configuration might require a class to exist, a foundational bean to have been created, and a property not to be disabled. If any condition fails, Spring skips that configuration; this can be intentional behavior rather than an error.

`@ConditionalOnMissingBean` is especially important when customizing. If the application already declared a bean of the same type or qualifying name that the default configuration checks, Spring Boot normally backs off to avoid creating a second default bean. Therefore, a `did not match` entry may indicate the application is using a custom bean. Read the specific reason before concluding you need to add a dependency.

For Spring Cloud LoadBalancer, you may need to check conditions across multiple layers: LoadBalancer classes, discovery abstractions, HTTP client beans, and builder beans annotated with `@LoadBalanced`. Having the dependency without a properly annotated client bean can still prevent requests from going through instance selection.

## 4. Inspecting the Condition Evaluation Report at Startup

Spring Boot can print an auto-configuration condition evaluation report when run with `--debug`. The report groups configurations into matched and unmatched sets, along with reasons. This is a good starting point when an expected bean does not appear.

Run the application with debug:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Or when running a JAR file:

```bash
java -jar build/libs/application.jar --debug
```

With Gradle, you can pass `--args='--debug'` to the `bootRun` task:

```bash
./gradlew bootRun --args='--debug'
```

Look for entries with names related to LoadBalancer, discovery, RestClient, WebClient, or Feign in the report. Exact auto-configuration class names change across versions and integration types; rely on your application's actual report rather than assuming a class exists identically across every release train.

Another option is using the Actuator `conditions` endpoint in a development environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

After the application starts, access `/actuator/conditions` to view matched and unmatched conditions. This endpoint can reveal bean names, classes, and internal configuration; only enable it in appropriate environments and protect access before deploying to shared or production environments.

When reading the report, focus on three items:

- **Positive matches:** which auto-configurations or conditions were satisfied.
- **Negative matches:** which configurations were skipped and which conditions failed.
- **Exclusions:** which auto-configurations were explicitly excluded via annotations or properties.

For example, if configuration for a client did not match because the client's class is missing from the classpath, verify dependencies first. If it did not match because a bean already exists, check whether that bean is the custom bean you intended to use. If configuration is excluded, locate where the exclusion is declared before re-adding dependencies.

## 5. Verifying LoadBalancer-Enabled Clients

Each HTTP client has its own integration mechanism. Inspect the exact builder or client the application is injecting.

For `RestClient`, example configuration of a `@LoadBalanced` builder:

```java
@Configuration
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Inject the right builder when creating the gateway:

```java
@Service
class InventoryGateway {

    private final RestClient client;

    InventoryGateway(@LoadBalanced RestClient.Builder builder) {
        this.client = builder.build();
    }

    ProductResponse findProduct(String productId) {
        return client.get()
                .uri("http://inventory-service/api/products/{id}", productId)
                .retrieve()
                .body(ProductResponse.class);
    }
}
```

`RestClient` belongs to Spring Framework 6.1 and later. Therefore, only use this pattern when your project's Spring Boot/Spring Framework and Spring Cloud versions support the corresponding `RestClient` integration. On older versions without `RestClient`, use a client supported by that version, such as `RestTemplate` or `WebClient`.

For `WebClient`, the builder needs to be annotated similarly:

```java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
```

For OpenFeign, declare the service ID on the client:

```java
@FeignClient(name = "inventory-service")
interface InventoryClient {

    @GetMapping("/api/products/{id}")
    ProductResponse findProduct(@PathVariable("id") String productId);
}
```

OpenFeign needs to be integrated with Spring Cloud LoadBalancer to resolve `inventory-service` into an instance. If Feign calls a fixed hostname or configures a static URL, requests may bypass service-ID instance selection.

When the application has multiple builders of the same type, inject the `@LoadBalanced`-qualified builder explicitly. Avoid accidentally grabbing a plain builder, as that client may lack the interceptor or customizer needed to handle service IDs.

## 6. Checking the ServiceInstance Source

LoadBalancer needs an instance list for the service ID. This list usually comes from a discovery provider such as Eureka or Consul. In a small application or during local testing, you can use `SimpleDiscoveryClient` with a static instance list.

Example static instance configuration:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

The two URIs above are illustrative instances of the same service ID `inventory-service`. When calling `http://inventory-service/...` with a LoadBalancer-integrated client, this list serves as the input for instance selection. In real environments, the discovery provider updates the list according to service registration state.

If no instances are found, verify whether the service ID matches between caller and registry, whether the discovery client is enabled, and whether instances have registered. Also distinguish between having no provider at all versus having a working provider that returns an empty list.

## 7. Detecting Dependency Conflicts with Build Tools

A common mistake is declaring the right starter while dependency resolution selects incompatible versions because another library pulls in a transitive version or the project manually pins a version.

With Maven, inspect the dependency tree:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework.cloud,org.springframework.boot
```

To inspect the effective POM and dependency management rules:

```bash
./mvnw help:effective-pom
```

With Gradle, inspect the runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To trace why a specific dependency version was selected:

```bash
./gradlew dependencyInsight \
  --dependency spring-cloud-loadbalancer \
  --configuration runtimeClasspath
```

Read the output to look for:

- Multiple different versions of the same Spring Cloud artifact.
- Modules replaced or forced to a version by resolution rules.
- Dependencies excluded from a starter or placed in the wrong scope/configuration.
- Spring Boot or Spring Framework libraries upgraded individually outside dependency management.
- Integration starters (Feign, discovery, HTTP client) missing from `runtimeClasspath` even though present in the build configuration under another scope.

Do not draw conclusions solely from a dependency appearing in the build file. The runtime classpath reveals which artifacts are actually selected when the application runs.

## 8. Identifying Errors from Specific Symptoms

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `ClassNotFoundException` or `NoClassDefFoundError` | Missing artifact or excluded dependency; or classpath mismatch between compile and runtime. | Inspect the dependency tree and runtime classpath. |
| `NoSuchMethodError` or `NoSuchFieldError` | Modules were compiled against a different API version than what is present at runtime. | Compare resolved Boot, Framework, and all Spring Cloud module versions. |
| `NoSuchBeanDefinitionException` when injecting builder/client | Auto-configuration did not create the bean, missing starter, or bean excluded by conditions. | Check the Condition Evaluation Report and matching bean list. |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type exist and injection cannot disambiguate. | Check qualifiers, `@Primary`, and application-declared beans. |
| `BeanDefinitionOverrideException` | Two configurations register beans with the same name while overriding is disallowed. | Locate bean-declaring configurations and check for duplicate configuration imports. |
| Requests report no instances found | Discovery provider has no data, wrong service ID, or empty instance list. | Check the registry, discovery configuration, and service ID. |
| Requests go straight to a fixed hostname | Client uses a static URL or a builder without LoadBalancer integration. | Check the URL and qualifiers of the injected client/builder. |

Error messages are only clues. For instance, `NoSuchBeanDefinitionException` can be caused by a missing starter, but also by an unmet property condition or an excluded configuration. Read the `Caused by` chain and the Condition Evaluation Report to identify the closest root cause.

## 9. Troubleshooting Process When Auto-Configuration Does Not Appear

Follow these steps in order to narrow down the cause:

1. Confirm which Spring Boot version the project uses and choose a compatible Spring Cloud release train.
2. Verify `spring-cloud-starter-loadbalancer` is on the runtime classpath and not excluded.
3. If using Eureka, Consul, or another provider, verify the right discovery starter and registry connection settings.
4. Start with `--debug` or inspect `/actuator/conditions`, looking for unmatched conditions related to the client and LoadBalancer.
5. Check whether the injected builder/client has the `@LoadBalanced` qualifier or properly declares the service ID.
6. Verify the service ID has an instance list and that instance URIs are reachable.
7. After fixing dependencies or configuration, restart the application and re-check both the condition report and actual requests.

Do not add extra starters or enable bean overriding just to make the application start. Those changes can mask the root cause and introduce further conflicts into the application context.

## 10. Minimal Configuration Verification Example

Suppose the application only needs to call two local instances of `inventory-service`. You can use the LoadBalancer starter, `SimpleDiscoveryClient` configuration, and a builder annotated with `@LoadBalanced`.

Minimal Maven dependency for LoadBalancer:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Two-instance configuration:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Declaring the builder and gateway:

```java
@Configuration
class LoadBalancedClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder restClientBuilder() {
        return RestClient.builder();
    }
}

@Service
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    ProductResponse getProduct(String id) {
        return restClient.get()
                .uri("http://inventory-service/api/products/{id}", id)
                .retrieve()
                .body(ProductResponse.class);
    }
}
```

This example requires a Spring Boot/Spring Cloud line that supports `RestClient` integration. If the project uses an older line, substitute a client supported in that version while keeping the same verification principles for dependencies, auto-configuration conditions, qualifiers, and instance lists.

When verifying, you should see the application start without bean creation errors, the condition report show the relevant configurations matched, and requests using the service ID routed to an instance in the list. One successful request only verifies the call path at that moment; it does not prove every instance is healthy or that all retry/timeout policies are configured properly.

## 11. Checklist Before Concluding Configuration Is Correct

- [ ] Spring Boot and Spring Cloud release train fall within the compatibility matrix.
- [ ] `spring-cloud-starter-loadbalancer` is present on the runtime classpath.
- [ ] Discovery starter or static instance source is properly configured for the architecture.
- [ ] Condition Evaluation Report shows no unexpected missing required conditions.
- [ ] The client/builder used to call the service ID is integrated with LoadBalancer.
- [ ] The service ID matches the service name in the discovery source and has at least one valid instance.
- [ ] Dependency tree shows no conflicting Spring Boot/Spring Framework/Spring Cloud versions.
- [ ] Actuator diagnostic endpoints, if enabled, are restricted and secured appropriately for the environment.

When these conditions are verified, the development team can clearly distinguish errors caused by dependencies, auto-configuration, discovery, or application requests. That makes setting up Spring Cloud LoadBalancer repeatable and easier to maintain across version upgrades.
