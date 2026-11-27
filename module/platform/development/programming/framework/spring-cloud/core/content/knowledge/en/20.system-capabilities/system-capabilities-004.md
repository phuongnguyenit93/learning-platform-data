# Reading Implementation Name, Version, and Vendor

## 1. Why Read Implementation Metadata?

Spring Cloud Commons defines multiple abstractions so applications do not depend directly on a specific provider. For example, a consumer can use `DiscoveryClient` to find services, while the actual implementation may come from Eureka, Consul, Zookeeper, or another discovery library.

In operations, merely knowing that the application has a `DiscoveryClient` bean is sometimes not enough. We also need to answer: which feature is recognized, which implementation class provides it, which version the package publishes, and who the vendor is.

Spring Cloud Commons provides the `/features` Actuator endpoint to publish this information. The response has two groups: `enabled` and `disabled`. For enabled features, each item has `name`, `type`, `version`, and `vendor` fields.

This lesson belongs to the **System Capabilities** chapter of **SPRING_CLOUD_CORE**. The focus is on how to read the endpoint, understand the origin of version/vendor metadata, distinguish the two feature types supported by the endpoint, and declare features for custom modules.

## 2. The `/actuator/features` Endpoint

`FeaturesEndpoint` is a Spring Boot Actuator endpoint with ID `features`. When the endpoint is exposed over HTTP and the default management base path is `/actuator`, it can be read using:

```bash
curl -i http://localhost:8080/actuator/features
```

The endpoint is a read operation. The response describes the features that Spring Cloud modules have declared via `HasFeatures` beans, along with enabled/disabled status according to how the endpoint handles each feature type.

For the endpoint to appear, the application typically needs:

1. Spring Boot Actuator on the classpath.
2. Spring Cloud Commons and the modules publishing features on the classpath.
3. Not disabling the feature with `spring.cloud.features.enabled=false`.
4. The endpoint considered available by Spring Boot and exposed over HTTP or JMX as needed.

Add the Actuator dependency if the project does not already have it:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Configure exposure specifically for the endpoints to read:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features
```

The `spring.cloud.features.enabled` property defaults to `true`. You can disable the endpoint with:

```yaml
spring:
  cloud:
    features:
      enabled: false
```

If the application changed `management.endpoints.web.base-path` or runs the management server on a separate port, the actual URL changes according to that configuration.

**Exposing the endpoint is a separate step from enabling features.** A feature may already be declared in the context yet clients cannot read the endpoint if Actuator is missing, the endpoint is disabled, or it is not exposed.

## 3. Response Structure

The response has two arrays:

- `enabled`: list of features recorded as enabled by the endpoint.
- `disabled`: names of abstract features for which no corresponding bean was found in the ApplicationContext.

Illustrative example:

```json
{
  "enabled": [
    {
      "type": "com.example.discovery.ConsulDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.3",
      "vendor": "Example Vendor"
    },
    {
      "type": "com.example.payment.StripePaymentConnector",
      "name": "Payment Connector",
      "version": null,
      "vendor": null
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

The version/vendor values in the JSON only illustrate the response shape. They depend on the actual manifest metadata of the running package; do not assume an implementation will always have both values.

| Field | Meaning |
| --- | --- |
| `name` | Feature name determined by the abstraction or `NamedFeature` |
| `type` | Fully qualified (canonical class name) of the class used to describe the implementation |
| `version` | `Implementation-Version` retrieved from the metadata of the package containing the class |
| `vendor` | `Implementation-Vendor` retrieved from the metadata of the package containing the class |
| `enabled` | Array of features recorded as enabled |
| `disabled` | Array of abstract feature names without a bean by type |

`type` helps distinguish two implementations providing the same abstraction. `version` and `vendor` help cross-check running artifacts against release notes, advisories, or SBOMs.

## 4. Two Feature Types: Abstract and Named

Spring Cloud Commons divides features into two types: **abstract features** and **named features**. How the endpoint determines status and retrieves metadata differs between the two.

### 4.1. Abstract Feature

An abstract feature is described by an interface or abstract class. Examples:

- `DiscoveryClient`
- `LoadBalancerClient`
- `LockService`

The endpoint uses this class/interface as a key to look up a bean in the ApplicationContext.

Process:

1. Retrieve the class declared in the abstract features list.
2. Use `ApplicationContext.getBean(type)` to look up a bean by type.
3. If no bean is found, add `type.getSimpleName()` to the `disabled` array.
4. If a bean is found, retrieve the actual class from `bean.getClass()`.
5. Create a feature descriptor with name as the simple name of the abstraction and type as the bean's runtime class.
6. Read canonical name, implementation version, and implementation vendor from the runtime class's package.

For example, the discovery module declares `DiscoveryClient.class`. If the context has a `ConsulDiscoveryClient` bean implementing this interface, the response may contain:

```json
{
  "type": "org.springframework.cloud.consul.discovery.ConsulDiscoveryClient",
  "name": "DiscoveryClient",
  "version": "5.0.3",
  "vendor": "Example Vendor"
}
```

If no matching bean exists, the endpoint places `DiscoveryClient` into the `disabled` array. Therefore, names in `disabled` are usually abstraction names, not specific implementation names.

### 4.2. Named Feature

A named feature is used when a capability has no common interface/abstract class suitable for the endpoint to look up a bean. The module provides a readable feature name and a class representing the implementation or artifact from which metadata should be read.

Example:

```java
new NamedFeature(
        "Payment Connector",
        StripePaymentConnector.class
)
```

For a named feature, the endpoint takes `name` and `type` from the declared descriptor, then reads package metadata from the passed-in class. It does not perform the `ApplicationContext.getBean(type)` step like an abstract feature.

This has a consequence: a named feature is **metadata declared by the module**. If a module declares a feature unconditionally while the actual implementation is not created, the endpoint may still list it in `enabled`. Place the `HasFeatures` bean inside an appropriately conditioned configuration matching whether the feature is truly provided.

### 4.3. Comparison of the Two Types

| Criterion | Abstract feature | Named feature |
| --- | --- | --- |
| Declaration | Interface or abstract class | Name and representative class |
| How endpoint determines status | Look up bean by type in context | Based on declared descriptor |
| Display name | Simple name of abstraction | Name passed to `NamedFeature` |
| Class for metadata | Actual class of bean | Class passed to descriptor |
| When no bean exists | Places abstraction name in `disabled` | Does not automatically check bean; descriptor is still added to `enabled` |
| Suitable use case | Contract with multiple swappable implementations | Standalone feature without a common contract |

## 5. Where Are Version and Vendor Retrieved From?

In `FeaturesEndpoint`'s implementation, feature metadata is built from the implementation class's package:

```java
Package implementationPackage = implementationType.getPackage();

String version = implementationPackage.getImplementationVersion();
String vendor = implementationPackage.getImplementationVendor();
```

Both Java `Package` methods read manifest attributes:

- `getImplementationVersion()` reads `Implementation-Version`.
- `getImplementationVendor()` reads `Implementation-Vendor`.

These attributes are typically packaged in `META-INF/MANIFEST.MF` of the JAR containing the class.

Example manifest contents:

```text
Manifest-Version: 1.0
Implementation-Title: Example Discovery Adapter
Implementation-Version: 5.0.3
Implementation-Vendor: Example Vendor
```

If `ConsulDiscoveryClient` resides in a JAR whose manifest declares `Implementation-Version: 5.0.3`, the endpoint can return that version. If the manifest lacks this field, the result may be `null`.

### 5.1. This Is Not the Spring Boot or Spring Cloud Release Train Version

Do not conflate the following values:

| Information | Source |
| --- | --- |
| Implementation version in `/features` | Package metadata of the implementation class |
| Spring Boot version | Spring Boot dependency/runtime |
| Spring Cloud release train | BOM/release train managing Spring Cloud modules |
| Application version | Application-declared build metadata, e.g., `BuildProperties` or `/actuator/info` |
| Version declared in dependency management | Build-time POM/BOM |

An application can run Spring Boot version A, Spring Cloud release train B, while a specific implementation adapter has version C. These three values serve different purposes.

The `/features` endpoint also does not read the full dependency tree, `pom.xml`, or SBOM. It only reports features registered via `HasFeatures`.

### 5.2. Why Can Version/Vendor Be `null`?

Common causes:

- The JAR does not declare `Implementation-Version` or `Implementation-Vendor` in its manifest.
- Repackaging/shading dropped or failed to preserve the required manifest attributes.
- Classes are loaded from a compiled classes directory instead of a JAR with an appropriate manifest.
- A named feature passes an application class whose artifact does not declare implementation metadata.
- An abstract feature resolves a proxy bean; the returned runtime class has different package metadata than the target class or lacks metadata.

Therefore, `null` does not necessarily mean a dependency is missing or the implementation is broken. It simply indicates the package metadata read by the endpoint had no value.

If reliable version/vendor values are needed for auditing, combine the endpoint with artifact manifests, dependency trees, SBOMs, or build provenance. Do not guess versions from class names or JAR filenames.

## 6. How to Register Features for Custom Modules

Each module can declare one or more `HasFeatures` beans. Spring Cloud documentation recommends placing this bean in an appropriately conditioned `@Configuration` so the feature is only published when the corresponding module is present.

Example of a payment module having implementation `StripePaymentConnector` and wanting to publish that class's name, version, and vendor:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import com.example.payment.StripePaymentConnector;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(StripePaymentConnector.class)
public class PaymentFeatureConfiguration {

    @Bean
    HasFeatures paymentFeatures() {
        return HasFeatures.namedFeatures(
                new NamedFeature(
                        "Payment Connector",
                        StripePaymentConnector.class
                )
        );
    }
}
```

In this example:

- `@ConditionalOnClass` prevents registering the descriptor if the implementation class is not on the classpath.
- `NamedFeature` sets the display name to `Payment Connector`.
- `StripePaymentConnector.class` is the class the endpoint uses to read canonical name and package metadata.
- `HasFeatures.namedFeatures(...)` packages the descriptor for the endpoint to aggregate.

If the feature should only appear when a bean has been successfully created, you can add `@ConditionalOnBean` or use an abstract feature with an appropriate contract.

### 6.1. Registering an Abstract Feature

Suppose the payment module defines a `PaymentConnector` interface and has a `StripePaymentConnector` bean implementing it. You can declare an abstract feature by contract:

```java
import org.springframework.cloud.client.actuator.HasFeatures;
import com.example.payment.PaymentConnector;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PaymentContractFeatureConfiguration {

    @Bean
    HasFeatures paymentFeatures() {
        return HasFeatures.abstractFeatures(PaymentConnector.class);
    }
}
```

When a `PaymentConnector` bean exists, the endpoint takes the bean's runtime class, such as `StripePaymentConnector`, to report metadata. When no bean exists, the endpoint places `PaymentConnector` in `disabled`.

Spring Cloud Commons already declares several of its own features, such as `DiscoveryClient` and `LoadBalancerClient` in their respective configurations. Other integration modules can add their own features. Avoid unnecessary duplicate declarations because the endpoint aggregates all `HasFeatures` beans and may return multiple descriptors with the same name.

## 7. Reading Metadata Directly from a Class

When you need to inspect the manifest in a unit test or diagnostic tool, you can read package metadata in Java:

```java
public record ImplementationMetadata(
        String className,
        String version,
        String vendor
) {
}

public final class ImplementationMetadataReader {

    private ImplementationMetadataReader() {
    }

    public static ImplementationMetadata read(Class<?> implementationType) {
        Package implementationPackage = implementationType.getPackage();

        return new ImplementationMetadata(
                implementationType.getCanonicalName(),
                implementationPackage.getImplementationVersion(),
                implementationPackage.getImplementationVendor()
        );
    }
}
```

This illustrates the same data source used by `FeaturesEndpoint`. If you need to handle classes without a package or special environments, add appropriate null-checks before calling methods on the package.

Usage example:

```java
ImplementationMetadata metadata =
        ImplementationMetadataReader.read(StripePaymentConnector.class);

System.out.println("Class: " + metadata.className());
System.out.println("Version: " + metadata.version());
System.out.println("Vendor: " + metadata.vendor());
```

Do not use this code to guess Maven versions from the classpath. It only reads package manifest metadata.

## 8. Enabling, Reading, and Checking the Endpoint at Runtime

### 8.1. Minimal Configuration

The application requires Actuator and Spring Cloud Commons. Then expose the endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,features

spring:
  cloud:
    features:
      enabled: true
```

`spring.cloud.features.enabled` defaults to `true`, so this property can be omitted unless you want to make it explicit. The important part for HTTP access is the exposure list containing ID `features`.

### 8.2. Calling an Authenticated Endpoint

In environments with authentication, use an account with read-only permissions for management endpoints:

```bash
curl -u monitor-user:REDACTED \
  http://localhost:8080/actuator/features
```

Do not record real passwords in shell history or documentation. If the management server uses a separate port or base path, update the URL to match the environment.

### 8.3. Reading the Output

Suppose the response has:

```json
{
  "enabled": [
    {
      "type": "org.springframework.cloud.consul.discovery.ConsulDiscoveryClient",
      "name": "DiscoveryClient",
      "version": "5.0.3",
      "vendor": "Example Vendor"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
```

You can read it in order:

1. `name` indicates the published abstraction/feature.
2. `type` indicates the implementation class used by the endpoint to describe the feature.
3. `version` indicates which version the implementation package publishes.
4. `vendor` indicates which vendor the implementation package publishes.
5. `disabled` indicates which abstract feature has no corresponding bean in the context.

This example does not mean all Consul implementations share the same version/vendor. Cross-check the returned values against your application's actual artifacts.

## 9. Distinguishing `/features` from Other Actuator Endpoints

Endpoints answer different operational questions:

| Endpoint | Primary Question | Contents |
| --- | --- | --- |
| `/actuator/features` | Which implementation features are declared and what is their metadata? | Feature name/type/version/vendor and list of abstract features without beans |
| `/actuator/health` | Is the application or dependency currently healthy? | Health status and health contributors |
| `/actuator/info` | What information does the application publish? | Build/app-configured metadata, possibly including build version or git commit |
| `/actuator/conditions` | Why was an auto-configuration applied or skipped? | Condition evaluation report |
| `/actuator/beans` | Which beans currently exist in the context? | List of beans and dependencies |

`/features` is not a health check. An implementation can appear in `enabled` while the registry connection is failing. Conversely, a health contributor can report good status while the endpoint has no descriptor for that implementation.

The endpoint also does not replace `/actuator/conditions`. Feature metadata indicates which implementation a module published; the condition report explains which auto-configuration conditions matched or did not match.

## 10. Security and Operations

Implementation information is helpful for inventory and troubleshooting, yet it can also reveal the application's technology stack.

Class names, versions, and vendors can help operators identify running artifacts. At the same time, they can help outsiders identify outdated dependencies or components with known vulnerabilities.

When exposing the endpoint:

- Only open the endpoint on a management network or through an administrative gateway.
- Protect with appropriate authentication and authorization.
- Do not expose all of Actuator with a wildcard without a clear reason.
- Only grant endpoint read permissions to necessary monitoring/support roles.
- Do not send responses containing classpath inventory to public logs or uncontrolled tickets.
- Cross-check version/vendor against dependency trees and SBOMs before drawing conclusions about security patches.
- Monitor implementation changes after deployment to detect unintended dependency substitutions.

If the endpoint returns `null` for version/vendor, do not fill in guessed values in reports. Check the artifact manifest, build pipeline, or SBOM for an authoritative source.

## 11. Troubleshooting Common Issues

| Symptom | Possible Cause | Investigation Steps |
| --- | --- | --- |
| `/actuator/features` returns 404 | Missing Actuator, endpoint unavailable, disabled, or not exposed | Check dependencies, `spring.cloud.features.enabled`, endpoint availability, and web exposure |
| `features` does not appear in response | No `HasFeatures` bean or module has not declared features | Check module auto-configuration and `HasFeatures` registration conditions |
| Feature is in `disabled` | Abstract type declared but context has no bean of that type | Check starter, conditional beans, module enable property, and classpath |
| Feature is in `enabled` yet implementation does not work | Named feature declares metadata; endpoint does not verify bean or health | Check actual bean, health indicator, and dependency connectivity |
| `version` or `vendor` is `null` | Manifest lacks `Implementation-Version`/`Implementation-Vendor` | Check `META-INF/MANIFEST.MF` of the JAR containing the class |
| `type` is a proxy class or unexpected package | Abstract feature uses `bean.getClass()` as runtime class | Check proxy strategy and target/artifact metadata |
| Duplicate features with the same name | Multiple `HasFeatures` beans declare the same abstraction/name | Check auto-configuration modules that registered descriptors |
| Endpoint access denied | Management endpoint security rules | Check roles, request matchers, management port, and network policy |

## 12. Post-Deployment Implementation Verification Workflow

1. Confirm Spring Cloud Commons and implementation starter versions are managed consistently via the appropriate BOM.
2. Confirm Actuator is on the runtime classpath.
3. Verify `spring.cloud.features.enabled` is not disabled.
4. Expose only `features` on an appropriate management interface.
5. Call the endpoint with an account that has read permissions.
6. Store the response in an internal inventory system if operational policy allows.
7. Compare `name` and `type` against the expected implementation.
8. Cross-check `version` and `vendor` against manifests, dependency trees, or SBOMs.
9. If a feature is in `disabled`, check the contract bean and auto-configuration conditions.
10. If a feature is in `enabled` yet the dependency fails, check health/connectivity separately.
11. Repeat after upgrading starters, switching providers, or changing the packaging pipeline.

Consider archiving responses by release/deployment ID so implementations can be compared before and after a rollout. Avoid using version/vendor from the endpoint alone as sole proof of dependency safety.

## 13. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| `/features` lists every dependency on the classpath | It aggregates features declared by modules via `HasFeatures` |
| `version` is the Spring Boot version | It is `Package.getImplementationVersion()` of the implementation class |
| `vendor` is the running registry provider | It is `Package.getImplementationVendor()` from package metadata |
| `enabled` means health UP | It only reflects the endpoint's feature declaration/lookup logic |
| Named features always check whether a bean exists | Named features are added per descriptor without looking up a bean like abstract features |
| `disabled` lists every uninstalled module | It only lists abstract features declared without a matching bean by type |
| `null` version means the JAR was not loaded | Usually just means the manifest/package does not publish that metadata |
| The endpoint reads the Maven dependency tree itself | It does not read POM/BOM/SBOM; it only uses class and package metadata |
| Exposing Actuator is safe by default | Network access and permissions must be restricted because the endpoint discloses implementation inventory |

## 14. Self-Check Questions

1. Which endpoint does Spring Cloud Commons provide to read feature name, type, version, and vendor?
2. Which two data groups does the endpoint return?
3. How is an abstract feature determined to be enabled?
4. How does a named feature differ from an abstract feature in the bean checking step?
5. From which class is the `type` field constructed in the two feature types?
6. Where does `Package.getImplementationVersion()` read metadata from?
7. Why is a feature's version not necessarily equal to the Spring Boot version?
8. What reasons cause version/vendor to have a `null` value?
9. Why can a feature be in `enabled` while the service is still unhealthy?
10. How should the endpoint be protected when used in production?

## 15. Official References

- [Spring Cloud Commons — Common Abstractions, Enabled Features](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html) — the two feature types, endpoint contents, and how to declare `HasFeatures`.
- [FeaturesEndpoint.java — Spring Cloud Commons](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/actuator/FeaturesEndpoint.java) — how the endpoint classifies enabled/disabled and reads package metadata.
- [CommonsClientAutoConfiguration.java — Spring Cloud Commons](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/CommonsClientAutoConfiguration.java) — conditions for creating the endpoint and Commons features registered.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) — the `spring.cloud.features.enabled` property.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — exposing, access control, and protecting management endpoints.
- [Java `Package` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Package.html) — `getImplementationVersion()` and `getImplementationVendor()`.

*This document focuses on the metadata Spring Cloud Commons publishes via Actuator. Use `/features` as an inventory source for registered features, then cross-check manifests, dependency trees, and health signals when concluding what implementation is operating.*
