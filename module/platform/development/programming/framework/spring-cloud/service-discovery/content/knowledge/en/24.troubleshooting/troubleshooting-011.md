# Multiple DiscoveryClient Conflicts or Version Incompatibilities

A Spring Cloud application may bring multiple discovery libraries onto the classpath, such as Eureka, Consul, ZooKeeper, and Kubernetes. When multiple starters are active simultaneously, the app can create multiple `DiscoveryClient` beans, multiple service registration mechanisms, or multiple instance sources for the same service ID. If unintentional, consumers may query the wrong registry, providers may register twice, or health states across registries may diverge.

Another class of errors arises when Spring Boot, Spring Cloud release train, and starter versions are incompatible. The application may fail to start due to missing dependencies, bean creation failures, `NoSuchMethodError`, or abnormal discovery behavior after an upgrade.

This article helps distinguish multi-provider conflicts from dependency compatibility errors, identify which beans and auto-configurations are actually activated, select one provider cleanly or configure multiple providers intentionally, and resolve version errors in a verifiable sequence.

## 1. Distinguishing `DiscoveryClient`, `ServiceRegistry`, and Auto-Registration

Three concepts are often lumped together:

- **`DiscoveryClient`**: abstraction for consumers to query service instances by service ID via `getInstances(serviceId)` and list services via `getServices()`.
- **`ServiceRegistry`**: abstraction for registering, deregistering, or updating instance status in a registry.
- **Auto-registration**: provider lifecycle integration that automatically registers the instance on application startup and deregisters on shutdown.

A provider usually supplies both `DiscoveryClient` and `ServiceRegistry`, yet they serve two distinct roles. A consumer that only performs lookups can disable its own registration. A provider that other services must find needs registration and appropriate health/lease settings.

Spring Cloud Commons provides the common abstractions; Eureka, Consul, ZooKeeper, and Kubernetes supply specific implementations. Adding a starter to the classpath can trigger that provider's auto-configuration whenever configuration conditions match.

## 2. Multiple DiscoveryClients Do Not Mean a Standby Registry

When multiple discovery providers are active together, the application may hold multiple implementation beans. Spring Cloud Commons may create a `CompositeDiscoveryClient` to coordinate delegates. How the composite picks delegates, call ordering, and result handling depend on the implementation/version; do not assume it always merges all instances from every registry into a single unified list.

Example classpath containing both Eureka and Consul:

```text
ApplicationContext
  EurekaDiscoveryClient
  ConsulDiscoveryClient
  CompositeDiscoveryClient (if created by auto-configuration)
```

Composite discovery handles querying across multiple delegates according to its own mechanism. It does not automatically:

- Synchronize service registrations between Eureka and Consul.
- Pick primary/secondary registries by health or business priority.
- Guarantee both registries share identical service IDs, metadata, and health statuses.
- Deregister instances from all registries on application shutdown.
- Provide consistent failover across all `ServiceRegistry` instances.

In particular, do not mistake `CompositeDiscoveryClient` for a multi-registry registration coordinator. Each provider's auto-registration has its own lifecycle; inspect `AutoServiceRegistration` beans, `ServiceRegistry` beans, and actual registration logs.

## 3. Common Conflict Patterns

| Conflict type | Symptoms | Common causes |
| --- | --- | --- |
| Unintended extra discovery starter | Consumer finds services from an unexpected registry | A dependency transitively pulls in another provider starter |
| Multiple `DiscoveryClient` beans | Composite created or ambiguous delegate injection | Multiple provider auto-configurations satisfy conditions |
| Multiple registrars | Instance appears in multiple registries | Auto-registration active for multiple providers at once |
| Multiple `ServiceRegistry` beans | Ambiguous injection or registrar picks wrong bean | Custom bean code or multiple providers enabled together |
| Inconsistent service IDs | Registry has instances, yet consumer receives empty list | Differing casing, prefixes, namespaces, or application names |
| Discovery and registration use different providers | Provider registers in registry A, consumer looks up registry B | Inconsistent provider settings across services |
| Incompatible starter | Bean creation errors, `NoSuchMethodError`, `ClassNotFoundException` | Mismatched Spring Boot/Cloud/library versions |
| Duplicate versions of a dependency pulled | Behavior changes across classpaths or runtimes | No unified BOM or manual version overrides |

## 4. Choosing a Discovery Architecture Before Editing Dependencies

Before removing or adding starters, clarify which scenario the application belongs to:

| Requirement | Appropriate design |
| --- | --- |
| Use only one registry | Add only that provider's starter and disable other providers |
| Consumer only looks up, no need to register | Enable `DiscoveryClient`, disable application auto-registration |
| Application both provides a service and calls others | Enable discovery and registration for the same provider |
| Migrating from old registry to new registry | Establish a clear migration phase; verify data and traffic before removing the old registry |
| Need intentional multi-registry lookups | Design explicit ordering/fallback/merge; test composite and registration separately |
| Need active-active multi-registry | Define how to sync registrations, health, deregistration, and handle split-brain; do not rely solely on `CompositeDiscoveryClient` |

In most applications, a single primary provider keeps configuration, health checks, access control, and operations predictable. Keep multiple providers only with a clear architectural requirement and tests for every flow.

## 5. Checking Which Dependency Pulled a Provider into the App

Do not inspect only `pom.xml` or `build.gradle` directly. A starter can be pulled in transitively by another library.

With Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud
```

To inspect Spring Framework/Spring Boot specifically:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-context,org.springframework.boot
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Check why a specific dependency appears:

```bash
./gradlew dependencyInsight \
  --dependency spring-cloud-starter-consul-discovery \
  --configuration runtimeClasspath
```

Look for starters such as:

- `spring-cloud-starter-netflix-eureka-client`
- `spring-cloud-starter-consul-discovery`
- `spring-cloud-starter-zookeeper-discovery`
- `spring-cloud-starter-kubernetes-client` or the Kubernetes discovery starter matching your version
- `spring-cloud-starter-loadbalancer`

Kubernetes artifact names and starter splits can change across releases. Inspect the dependency tree rather than inferring solely from module names.

If an app only needs Consul yet the Eureka starter is pulled in by an internal module, identify which dependency introduces it and remove it at the right source. Do not add sweeping exclusions before understanding the dependency path, as you may accidentally exclude a library your chosen provider actually requires.

## 6. Inspecting Actual `DiscoveryClient` Beans

Once the application starts, check which beans exist in the `ApplicationContext`. You can use a temporary `ApplicationRunner` under a debug profile:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@Configuration
class DiscoveryClientDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryClientDiagnostics.class);

    @Bean
    ApplicationRunner logDiscoveryClients(ApplicationContext context) {
        return args -> context.getBeansOfType(DiscoveryClient.class)
                .forEach((beanName, client) -> log.info(
                        "Discovery client bean: name={}, type={}, description={}",
                        beanName,
                        client.getClass().getName(),
                        client.description()));
    }
}
```

This snippet logs only bean names, classes, and descriptions; do not dump the entire `ApplicationContext` or configurations that may contain credentials. You can also inspect `ReactiveDiscoveryClient` if the app uses reactive discovery.

Do not rush to add `@Primary` when seeing multiple beans. `@Primary` only helps Spring pick a bean when type-based injection is ambiguous; it does not disable another provider's auto-configuration, stop another registrar from running, or ensure composite lookups use only the chosen provider.

If you need to inject a specific implementation, use `@Qualifier` with a verified bean name. Do this only when code genuinely needs provider-specific APIs; regular business code should depend on the common abstraction.

## 7. Checking Which Conditions Activated Auto-Configuration

Run the application with the debug condition report:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Or pass `--debug` when starting the built artifact. Spring Boot prints the condition evaluation report showing which auto-configurations matched and which conditions did not match.

If Actuator is enabled, `/actuator/conditions` displays the condition report. Expose this endpoint only in a secured debug environment; never expose internal configuration details to the Internet.

Search for configurations related to:

- Eureka client auto-configuration.
- Consul discovery auto-configuration.
- ZooKeeper discovery auto-configuration.
- Kubernetes discovery auto-configuration.
- Composite DiscoveryClient.
- SimpleDiscoveryClient.
- ServiceRegistry and auto-registration.

The condition report is more reliable than guessing from dependency names because a starter may be present yet disabled by a property, missing class, or environment condition.

## 8. Disabling Unnecessary Providers

If using only one provider, disable other providers using the properties supported in your version and remove unneeded dependencies where possible.

Illustrative configuration when the application uses only Consul:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
    consul:
      discovery:
        enabled: true
    zookeeper:
      discovery:
        enabled: false
    kubernetes:
      discovery:
        enabled: false

eureka:
  client:
    enabled: false
```

Exact properties depend on the provider and release train. Common examples include `spring.cloud.consul.discovery.enabled`, `eureka.client.enabled`, `spring.cloud.zookeeper.discovery.enabled`, `spring.cloud.kubernetes.discovery.enabled`, and the global switch `spring.cloud.discovery.enabled`. Check configuration metadata/reference docs for your exact starter before applying.

If you want to keep `DiscoveryClient` while disabling application self-registration:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

This property disables generic auto-registration when the provider integrates with the corresponding Spring Cloud Commons mechanism; it does not guarantee every provider-specific registration path is disabled in every version. Check logs and the registry to confirm the instance is no longer registered.

Do not set `spring.cloud.discovery.enabled=false` if the application still needs discovery lookups. It is a broad switch that can disable the very discovery client consumers depend on.

## 9. Distinguishing `CompositeDiscoveryClient` from Explicit Provider Selection

If multiple providers are intentional, verify whether the composite matches your desired semantics. Questions to answer:

- When a service ID exists in both registries, which delegate is queried first?
- Is the returned result from the first delegate with results, or merged across multiple lists?
- If the first delegate errors, does the composite continue to try subsequent delegates?
- If the first delegate returns an empty list, does it try the next delegate?
- Can `getServices()` list names from multiple registries while `getInstances()` pulls from a different one?
- How long does LoadBalancer cache the result list?
- Do metadata/health share the same semantics between the two providers?

Do not answer these questions by guessing. Check your exact API/version, inspect actual beans, and write integration tests against two registries holding different data to observe behavior.

If business logic requires prioritizing registry A with fallback to B, build an explicit adapter/strategy instead of relying on implicit bean ordering. The adapter must explicitly define which errors trigger fallback, how empty results are handled, and how duplicate instances are avoided.

## 10. Disabling Registration While Retaining Service Lookup

A consumer calling only downstream services may not need to register itself in the registry. Example:

```yaml
spring:
  application:
    name: report-worker
  cloud:
    consul:
      discovery:
        enabled: true
        register: false
```

With Eureka, the typical configuration is:

```yaml
eureka:
  client:
    enabled: true
    register-with-eureka: false
    fetch-registry: true
```

`register-with-eureka=false` disables registering the client with Eureka while still fetching the registry. This is a key distinction from `fetch-registry=false`, which can prevent consumers from obtaining service lists.

Property names and defaults can vary by provider/version. After configuring, verify both sides: the app can still look up target services and creates no unintended registrations.

## 11. Managing Multiple `ServiceRegistry` Instances When Multi-Registry Registration Is Needed

Some migration or hybrid architectures require registering the same instance in two registries. In that case, having two `DiscoveryClient`s is not enough.

Define a registration coordinator responsible for:

1. Creating a consistent service identity or explicit ID mapping per registry.
2. Registering into registries A and B according to a defined sequential/parallel policy.
3. Recording each registry's outcome independently.
4. Handling the case where A succeeds while B fails.
5. Retrying the failed part without creating duplicate registrations.
6. Deregistering from every registry the coordinator registered into.
7. Syncing health/status and metadata per each provider's semantics.

This is a distributed workflow problem: there is no shared ACID transaction across two registries. Compensation may be necessary if one step succeeds and another fails. Logs/metrics must separate outcomes by provider so partial-success states are visible.

Unless you have an explicit migration or hybrid requirement, avoid multi-registry registration purely for "redundancy." One primary registry with infrastructure-level backup/replication is usually far simpler than syncing two registration planes from every application.

## 12. Spring Boot and Spring Cloud Must Use Compatible Versions

Spring Boot and Spring Cloud are released in version lines governed by a compatibility matrix. A Spring Cloud release train supports only specific Spring Boot lines. Do not pick the latest version individually for each starter.

Dependency management rules:

- Choose the Spring Boot version first.
- Choose the Spring Cloud release train published as compatible with that Boot line.
- Import the release train's `spring-cloud-dependencies` BOM.
- Do not set individual versions on Spring Cloud starters when the BOM manages them.
- Keep Spring Cloud Commons, LoadBalancer, and provider starters within the same release train.
- Only override a dependency version with a clear reason and verified compatibility.

### Maven: Importing the Spring Cloud BOM

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
        <artifactId>spring-cloud-starter-consul-discovery</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
```

`YOUR_COMPATIBLE_RELEASE_TRAIN` is a placeholder; replace it with a release train verified against the official compatibility matrix. The Spring Boot parent/BOM must also align. Do not copy a specific version from another project without confirming the Boot and Java versions in use.

### Gradle: Importing the BOM

```groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation "org.springframework.cloud:spring-cloud-starter-consul-discovery"
    implementation "org.springframework.cloud:spring-cloud-starter-loadbalancer"
}
```

If using Kotlin DSL, the corresponding syntax is `implementation(platform("..."))`. Do not declare per-starter versions when the BOM manages them.

## 13. Identifying Binary Incompatibility Errors

Several exceptions commonly point to version skew:

| Error | Common meaning | Inspection direction |
| --- | --- | --- |
| `NoSuchMethodError` | Compiled code expects a method, yet runtime loaded a class version lacking it | Dependency tree, actual classpath, BOM alignment |
| `AbstractMethodError` | Implementation lacks a method compatible with runtime interface/abstract class | Spring Cloud module or provider implementation version mismatch |
| `NoClassDefFoundError` | Required class missing at runtime or class initialization failed | Missing/excluded dependency or earlier static initialization failure |
| `ClassNotFoundException` | Classloader cannot find requested class | Artifact/version/classpath and optional dependencies |
| `IncompatibleClassChangeError` | Class/interface kind or binary signature incompatible | Duplicate dependency versions or changed API |
| `BeanCreationException` | Bean failed during initialization; root cause may sit deep in cause chain | Read root cause, condition report, and provider config |
| `NoSuchBeanDefinitionException` | Auto-configuration did not create bean or dependency missing | Starter, property enablement, and condition report |
| `NoUniqueBeanDefinitionException` | Multiple beans of same type make injection ambiguous | Qualifier/Primary or disable extra provider after verification |

Do not fix `NoSuchMethodError` by adding `@Primary`; that is a binary dependency mismatch, not a bean-selection error. Likewise, `NoUniqueBeanDefinitionException` does not by itself prove libraries are incompatible; it may simply mean multiple providers were enabled as present on the classpath.

## 14. `javax`/`jakarta` Differences and Java Baseline

When upgrading from Spring Boot 2 to Spring Boot 3, many APIs moved from the `javax.*` namespace to `jakarta.*`. An older discovery library compiled against `javax` may be incompatible with a Spring Boot 3 app using `jakarta`.

When encountering class or method errors involving servlet, validation, annotation, or persistence packages:

- Check whether the provider starter has a release supporting your Spring Boot major version.
- Check that the Java runtime matches Spring Boot's requirements.
- Do not add both `javax` and `jakarta` APIs simultaneously just to make compilation pass if the library does not support both.
- Upgrade provider integrations together with the release train, not Spring Cloud Commons alone.
- Check whether internal libraries pull in legacy transitive dependencies.

No single version bump guarantees resolving all namespace errors; pinpoint the exact class in the stack trace and the dependency owning it.

## 15. Using the Compatibility Verifier Properly

Spring Cloud includes a compatibility verifier to catch unsupported Spring Boot/Spring Cloud combinations. When the app reports incompatible versions, treat it as a signal to fix.

Do not disable the verifier merely to get the application to start:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: false
```

This property may bypass the early check in supporting versions, yet it cannot fix binary API mismatches, auto-configuration failures, or untested behavior. Disable temporarily only after engineering evaluation, knowing the exact dependency matrix, and with regression testing; never use it as a default configuration.

## 16. Workflow When Multiple `DiscoveryClient`s Exist

Proceed in this order:

1. Document which provider the architecture requires for the current environment.
2. Inspect the dependency tree to locate direct and transitive starters.
3. Enable the condition report to see which auto-configurations matched.
4. List actual `DiscoveryClient`, `ReactiveDiscoveryClient`, `ServiceRegistry`, and auto-registration beans.
5. Inspect per-provider enablement properties.
6. Disable unintended providers and remove unneeded dependencies.
7. Verify consumers still obtain instances from the desired registry.
8. Verify providers register only with the intended registry.
9. Check health, deregistration, and shutdown lifecycles.
10. Run integration tests against a real registry or container to confirm no unintended registrations or lookups remain.

If multiple providers are intentional, write tests explicitly verifying delegate ordering, behavior when a service ID exists in both registries, behavior when one registry fails, and partial failures in registration/deregistration.

## 17. Workflow When Versions Are Incompatible

1. Record Java version, Spring Boot version, Spring Cloud release train, and provider starter versions.
2. Capture the full root cause, not only the outermost `BeanCreationException` line.
3. Run Maven/Gradle dependency trees for `org.springframework.cloud`, `org.springframework.boot`, and `org.springframework`.
4. Locate overridden, duplicate, or transitively skewed dependency versions.
5. Select the right Spring Cloud BOM per Spring Boot's compatibility matrix.
6. Remove unnecessary version overrides and let the BOM manage release-train modules.
7. Verify provider artifacts support the current Boot major, Java version, and namespace.
8. Perform a clean build and run context startup tests.
9. Run integration tests for registration, discovery lookup, health updates, and deregistration.
10. Only after verification consider narrowly scoped exclusions or overrides.

Do not upgrade Boot, Cloud, providers, logging, and HTTP clients all in one step unless necessary. Split changes into verifiable groups so regressions can be isolated.

## 18. Tests Confirming Only the Intended Provider Is Active

You can write a test inspecting actual beans in the context:

```java
@SpringBootTest
class DiscoveryProviderConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void exposesExpectedDiscoveryClient() {
        Map<String, DiscoveryClient> clients =
                context.getBeansOfType(DiscoveryClient.class);

        assertThat(clients.values())
                .anyMatch(client -> client.description().contains("Consul"));

        assertThat(clients.values())
                .noneMatch(client -> client.description().contains("Eureka"));
    }
}
```

This is an illustrative example; `description()` is a descriptive string that can change across versions. In project tests, check bean types/qualifiers or actual behavior rather than depending too tightly on string text.

Checking beans alone is insufficient. Integration tests should:

- Register a provider instance with a unique service ID.
- Confirm `DiscoveryClient` returns the right instance.
- Confirm unintended registries receive no registration.
- Stop or disconnect the primary registry and observe behavior per policy.
- Close the context and verify deregistration.

## 19. Common Errors and Remediation

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Service appears in both Eureka and Consul | Two provider auto-registrations active together | Disable unused registrar or design an explicit multi-registry coordinator |
| Consumer returns instance from wrong registry | Multiple DiscoveryClients/composite active | Check delegates/ordering, disable extra provider, and test lookups |
| `NoUniqueBeanDefinitionException` for `ServiceRegistry` | Multiple implementations registered | Use qualifiers if intentional or disable unused provider |
| `NoSuchMethodError` in Spring Cloud | Cloud modules misaligned across release trains | Import aligned BOM and remove version overrides |
| `NoClassDefFoundError` at startup | Missing/excluded dependency or incompatible namespace | Inspect dependency tree and provider support matrix |
| `BeanCreationException` in provider config | Bad property, invalid endpoint, or auto-config mismatch | Read root cause and condition report |
| Eureka client does not fetch registry | `fetch-registry=false` or client disabled | Check `eureka.client.enabled` and `fetch-registry` |
| Consumer does not register, yet lookup works | Auto-registration intentionally disabled | Confirm this is a consumer-only role |
| `@Primary` does not stop registration in another registry | Other registrar still runs | Disable auto-registration/provider, not just injection selection |
| Works locally, fails in CI | Different runtime classpath/profile or env properties | Compare dependency tree, active profiles, and condition report |
| Compatibility verifier reports unsupported | Boot/Cloud release trains mismatched | Pick compatible release train; do not disable verifier to hide error |

## 20. Checklist Before Concluding Resolution

- [ ] Distinguished `DiscoveryClient`, `ServiceRegistry`, and auto-registration.
- [ ] Identified the exact count and classes of discovery beans in the context.
- [ ] Checked `CompositeDiscoveryClient` semantics for your running version.
- [ ] Checked all direct and transitive starters in the runtime classpath.
- [ ] Disabled unintended providers or removed dependencies at the proper source.
- [ ] Tested consumer lookup and provider registration separately.
- [ ] Used `@Primary`/`@Qualifier` only for injection resolution, not to replace provider configuration.
- [ ] Verified Spring Boot and Spring Cloud release trains match the compatibility matrix.
- [ ] Managed all Spring Cloud modules through a single unified BOM.
- [ ] Removed version overrides skewing Commons/LoadBalancer/provider starters.
- [ ] Checked Java baseline and `javax`/`jakarta` differences during major upgrades.
- [ ] Did not disable the compatibility verifier merely to ignore warnings.
- [ ] Verified registration, lookup, health, and deregistration against the right registry via integration tests.
- [ ] Ensured logs and condition reports do not leak tokens or credentials.

When multiple DiscoveryClients appear together, determine whether multi-registry setup is intentional or a starter was pulled in inadvertently. `CompositeDiscoveryClient` handles lookups only per its implementation semantics; it neither syncs registrations nor replaces a multi-registry strategy. When errors stem from versions, align Spring Boot, the Spring Cloud release train, and provider starters via a compatible BOM, then re-verify beans, registration, and lookups with integration tests. This layered approach avoids masking unresolved root causes with `@Primary`, exclusions, or disabling the compatibility verifier.
