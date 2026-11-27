# Identifying `spring-cloud-commons`, `spring-cloud-context`, and `spring-cloud-starter`

In a Spring Boot project using Spring Cloud, three names—**`spring-cloud-commons`**, **`spring-cloud-context`**, and **`spring-cloud-starter`**—frequently appear together in the dependency tree. They **are not three names for the same library**. The first two artifacts are foundational libraries; the third artifact is a **starter** used to bundle common dependencies. Identifying their roles accurately helps decide which dependencies to add, understand which capabilities actually exist in the application, and diagnose why an integration fails.

This lesson sits in the **Versions and Dependencies** chapter of the **SPRING_CLOUD_CORE** module. Its scope covers the core foundations of Spring Cloud in distributed systems: Spring Cloud Commons, Context, externalized configuration, Spring Boot compatibility, refresh scope, discovery, service registry, inter-service communication, and verifying which abstractions have been activated.

## 1. Learning Objectives

After this lesson, learners can:

1. Look at Maven/Gradle coordinates to distinguish **libraries**, **starters**, **BOMs**, and **implementations**.
2. Explain the functions of `spring-cloud-commons` and `spring-cloud-context`, and state what capabilities they **do not supply by themselves**.
3. Identify how `spring-cloud-starter` differs from feature starters like `spring-cloud-starter-config` and `spring-cloud-starter-loadbalancer`.
4. Read a dependency tree to tell whether an artifact enters the classpath directly or transitively, and determine the actual selected version.
5. Align the **Spring Boot version** with the **Spring Cloud release train** and verify using Maven/Gradle alongside behavioral tests.

## 2. What Do Artifact Names Tell Us?

A Maven dependency is typically identified by **groupId**, **artifactId**, and **version**. In Spring Cloud, all three artifacts in this lesson normally belong to the **`org.springframework.cloud`** group, yet their `artifactId`s differ:

| Artifact | Kind | Primary role | When should you care? |
| --- | --- | --- | --- |
| `org.springframework.cloud:spring-cloud-commons` | Library JAR | Shared abstractions for service discovery, service registry, service instance, client-side load balancing, and shared integrations | When coding against shared APIs or finding out why `DiscoveryClient` is on the classpath |
| `org.springframework.cloud:spring-cloud-context` | Library JAR | Services related to `ApplicationContext`, config sources, environment change events, and refresh scope | When using `@RefreshScope`, refreshing config, or analyzing context lifecycle |
| `org.springframework.cloud:spring-cloud-starter` | Starter JAR | Bundles foundational Spring Cloud dependencies, typically pulling Commons and Context alongside Boot starter | When setting up the shared Cloud base or inspecting which libraries a feature starter brings in |
| `org.springframework.cloud:spring-cloud-dependencies` | BOM (POM) | Manages compatible versions within a Spring Cloud release train | When controlling dependency versions; **not a runtime library** |

> **Identification rule:** `commons` is about **shared API contracts**; `context` is about **application context and configuration**; `starter` is about **dependency bundling to initialize a capability**. Artifact names guide you, while actual behavior still depends on version, classpath, auto-configuration, and application configuration.

Do not confuse:

- **`spring-boot-starter`** is the foundational starter of **Spring Boot**; **`spring-cloud-starter`** is the foundational starter of **Spring Cloud**.
- **`spring-cloud-dependencies`** manages versions; it does not supply `DiscoveryClient`, `@RefreshScope`, or an HTTP client at runtime.
- **`spring-cloud-starter`** is the name of **one specific artifact**; the **`spring-cloud-starter-*`** naming pattern also represents many feature-specific starters, such as Config Client or LoadBalancer.
- **`spring-cloud-commons`** and **`spring-cloud-context`** are modules belonging to the Spring Cloud Commons ecosystem/source repository, yet repository name and Maven artifact name are two different concepts.

## 3. `spring-cloud-commons`: Shared Abstractions

A distributed system may use Eureka, Consul, Kubernetes, or a static instance list to find services. If business code depends directly on one provider's proprietary API, changing discovery infrastructure becomes harder. Spring Cloud Commons places **shared interfaces** between the application and concrete implementations.

### 3.1. Representative Concepts

| Abstraction | Meaning | Key point to remember |
| --- | --- | --- |
| `DiscoveryClient` | Queries services and `ServiceInstance` entries by logical name | Only a lookup contract; does not yet mean the app is connected to Eureka/Consul |
| `ReactiveDiscoveryClient` | Reactive variant for instance lookup | Fits reactive pipelines when a matching implementation is present |
| `ServiceInstance` | Describes a callable target (service ID, host, port, URI, metadata, etc.) | Being present in the list does not guarantee the instance is healthy |
| `ServiceRegistry` | Service registration/deregistration contract | Requires an appropriate registry implementation and `Registration` |
| `LoadBalancerClient` / related APIs | Contracts supporting instance selection and service-name calls | Specific algorithms and implementations require appropriate libraries/beans |

Java example showing how an application depends on a **shared contract**, without using a registry-specific SDK:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDirectory {
    private final DiscoveryClient discoveryClient;

    public InventoryDirectory(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> availableInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

In the snippet above, `getInstances("inventory-service")` only requests an instance list. It **does not make an HTTP call to Inventory Service**, does not create a circuit breaker, and does not guarantee returned instances are reachable.

Spring Cloud Commons can configure a **`SimpleDiscoveryClient`** backed by an instance list declared in properties when no registry-based discovery client is present. Therefore, **seeing a `DiscoveryClient` bean is not enough to conclude Eureka, Consul, or an external registry is active**.

### 3.2. Example: Static Discovery for Exploring the API

When using a Spring Cloud version supporting `SimpleDiscoveryClient`, instances can be declared via configuration:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

The application can look up `inventory-service` through `DiscoveryClient`. This illustrates a **static instance list source**. It does not create a service registry, does not register the process with a discovery server, and does not replace dynamic discovery in environments where instances churn continuously.

### 3.3. Commons Does Not Implement the Entire Distributed System Alone

Separate these concepts:

- **Discovery contract** (`DiscoveryClient`) vs. **discovery provider** (e.g., Eureka client or Consul discovery).
- **Registry contract** (`ServiceRegistry`) vs. **registry server** and the implementation used for registration.
- **Selecting an instance** vs. **sending an HTTP request**. Spring Cloud LoadBalancer handles instance selection, yet the application still needs an integrated HTTP client.
- **Seeing a dependency on the classpath** vs. **auto-configuration activating and creating the expected bean**.

This explains a familiar error: adding `spring-cloud-commons` and trying to access `http://inventory-service/...` only for the name not to resolve. The cause is that the project lacks the proper `ServiceInstance` source / load balancer / HTTP client integration; the Commons JAR alone is neither a service mesh nor a DNS server.

## 4. `spring-cloud-context`: Context and Configuration Updates

Spring Boot creates and manages `ApplicationContext`. Spring Cloud Context adds mechanics helping Cloud applications handle **config sources** and **configuration changes during the application lifecycle**.

Representative components include:

- `@RefreshScope`: a scope for beans that need to be recreated after a refresh.
- `RefreshScope`: a service managing target caching of refresh-scoped beans; can refresh a single bean or the entire scope.
- Events/mechanics related to `Environment` changes and configuration rebinding, depending on version.
- Bootstrap/configuration context integrations, depending on configuration style and Spring Boot/Spring Cloud version.

### 4.1. What Is `@RefreshScope` Used For?

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class CatalogMessage {
    @Value("${catalog.banner:Welcome}")
    private String banner;

    public String text() {
        return banner;
    }
}
~~~

If the application receives a new `catalog.banner` value in `Environment` **and** an appropriate refresh action occurs, the target of the refresh-scoped bean can be recreated to use the new value on the next access.

Distinguish four distinct moments:

1. The external configuration source is edited.
2. The application **receives or reloads** the configuration values.
3. The **refresh** mechanism is triggered.
4. Beans consuming the configuration are **rebound or recreated**, depending on bean/scope type.

**Simply adding `spring-cloud-context` or annotating `@RefreshScope` does not make these four steps happen automatically.** If using Spring Cloud Config Server, add Config Client and design an appropriate update/refresh mechanism. If exposing a management refresh endpoint, consider Spring Boot Actuator, endpoint exposure, and access control. Exact behavior varies by release train.

### 4.2. `@ConfigurationProperties` Is Not Equivalent to `@RefreshScope`

Spring Boot's `@ConfigurationProperties` binds properties onto a data-holder bean. Some Spring Cloud mechanisms can **rebind** configuration when the environment changes, yet rebinding and **recreating a target bean** are two different behaviors.

For example, an HTTP client already constructed with a timeout read at startup may retain the old timeout even if the config object gets updated. For the timeout change to take effect, redesign the client lifecycle, dependent beans, and appropriate refresh behavior. Placing `@RefreshScope` on a `@Configuration` class also does not automatically put every `@Bean` produced by that class into refresh scope.

Limitations to check per version: refreshability of each bean, read-only / constructor-bound data, native/AOT runtime constraints, and behavior of in-flight requests during refresh. Never assume every change is instantaneous or atomic.

### 4.3. `spring-cloud-context` Is Not a Config Server

**Spring Cloud Context** provides context and refresh mechanics. **Spring Cloud Config** is a separate component comprising client and server modules/starters. Reading configuration over HTTP from a Config Server does not come from `spring-cloud-context` alone.

The example below illustrates **Config Client** setup via Config Data on supported Spring Boot/Spring Cloud versions, and **is only meaningful when the appropriate Config Client starter has been added**:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

Here `optional:` expresses a policy allowing the application to continue in certain cases when configuration cannot be fetched from the server; whether that is appropriate depends on operational requirements. Fetching configuration at startup and triggering refresh **are not the same operation**.

## 5. `spring-cloud-starter`: Bundling Foundational Dependencies

Starters solve a practical problem: if every application had to list numerous JARs manually to use one feature, the risk of missing dependencies or mismatched versions would rise. A starter is a **convenient entry point** bringing related dependencies onto the classpath.

### 5.1. Base Starter vs. Feature Starters

| Artifact | Category | Primary function |
| --- | --- | --- |
| `spring-cloud-starter` | Base starter | Pulls in core Spring Cloud libraries, typically including Commons and Context |
| `spring-cloud-starter-loadbalancer` | Feature starter | Provides Spring Cloud LoadBalancer integration to pick service instances |
| `spring-cloud-starter-config` | Feature starter | Installs the **client** side so the app fetches configuration from Spring Cloud Config |
| `spring-cloud-starter-netflix-eureka-client` | Feature starter | Adds client integration for the Eureka discovery service |
| `spring-cloud-starter-circuitbreaker-resilience4j` | Feature starter | Integrates the Spring Cloud CircuitBreaker API with Resilience4j for suitable fault handling |

The following **conceptual diagram** shows relationships among the application, starters, and base libraries. Exact dependency edges must be checked for your actual version.

~~~mermaid
flowchart TD
    A[Spring Boot Application] --> S[spring-cloud-starter]
    S --> C[spring-cloud-commons]
    S --> X[spring-cloud-context]
    A -. when instance selection is needed .-> L[spring-cloud-starter-loadbalancer]
    A -. when config from Config Server is needed .-> F[spring-cloud-starter-config]
    A -. when Eureka is needed .-> E[spring-cloud-starter-netflix-eureka-client]
    L --> C
    F --> X
    E --> C
    B[spring-cloud-dependencies BOM] -. manages versions .-> S
    B -. manages versions .-> L
    B -. manages versions .-> F
    B -. manages versions .-> E
~~~

The diagram does not exhaustively depict every transitive edge; it serves to identify **roles**. Feature starters can pull in foundational libraries themselves, so you usually **do not need to additionally declare** `spring-cloud-starter` separately if you already have a feature starter bringing in the needed libraries. Inspect the dependency tree rather than adding duplicate declarations out of habit.

### 5.2. Does Adding a Starter Automatically Enable the Feature?

**Not necessarily.** Three levels need verification:

1. **Dependency present:** the artifact is on the runtime classpath.
2. **Bean/configuration present:** auto-configuration conditions are satisfied and required beans are created.
3. **Behavior works:** the registry is reachable, instance lists are accurate, configuration is valid, and actual requests succeed.

For instance, adding the Eureka Client starter brings the client integration onto the classpath, yet the service registry server must still be running and URL, registration, and network settings must be right. Adding the LoadBalancer starter also does not supply instance addresses itself without a discovery implementation or a suitable `ServiceInstanceListSupplier`.

### 5.3. Identifying Direct and Transitive Dependencies

If you declare:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter</artifactId>
</dependency>
~~~

Maven can resolve foundational JARs via the starter's **transitive dependencies**. Similarly, declaring only `spring-cloud-starter-config` can cause `spring-cloud-context` to appear even though it is not directly declared in `pom.xml`.

Because a starter's POM contents can change across release trains, the **actual dependency tree** is the authoritative source for which artifacts are present and which versions were selected.

## 6. BOMs and Spring Boot – Spring Cloud Compatibility

Individual modules carry versions like `4.x`, `5.x`, etc., yet applications normally select Spring Cloud by **release train**. A release train groups compatible versions of multiple Cloud components; the `spring-cloud-dependencies` BOM specifies their aligned versions.

This concept appears in three distinct places:

| Where the version appears | Example | Role |
| --- | --- | --- |
| Spring Boot | `3.5.x` or `4.0.x` | Spring Boot baseline version |
| Spring Cloud release train | `2025.0.x` or `2025.1.x` | Coordinated Cloud version set designed to work together |
| Spring Cloud module | e.g., Commons/Context version belonging to the train | JAR version selected by dependency management |

Per the official matrix at the time of writing (November 18, 2026), **Spring Cloud 2025.0.x** targets **Spring Boot 3.5.x**; **Spring Cloud 2025.1.x** targets **Spring Boot 4.0.x**, and supports **Spring Boot 4.1.x from 2025.1.2**. This is data specific to release trains/patches, not a rule derivable from version numbers. Before creating or upgrading a project, re-check the [official Spring Cloud – Spring Boot matrix](https://spring.io/projects/spring-cloud/).

The Spring Cloud BOM **does not replace** Spring Boot's version management mechanism. In Maven using `spring-boot-starter-parent`, the parent continues managing Boot and related Boot dependencies; the Cloud BOM manages Cloud artifacts. With Gradle, configure dependency management matching your build setup.

### 6.1. Maven: Base Declaration Example

This example assumes the project already has a **Spring Boot parent compatible with Spring Cloud 2025.0.x**; Boot parent details and other build sections are omitted to focus on Cloud dependencies.

~~~xml
<properties>
    <!-- Example release train; pick an appropriate patch when deploying -->
    <spring-cloud.version>2025.0.0</spring-cloud.version>
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
        <artifactId>spring-cloud-starter</artifactId>
    </dependency>
</dependencies>
~~~

Key points:

- Inside `dependencyManagement`, `type=pom` and `scope=import` allow Maven to import the **version management table**.
- The `spring-cloud-starter` dependency goes inside `<dependencies>` to enter the classpath.
- There is no need to manually add `<version>` on every Spring Cloud starter when using the proper BOM.
- `2025.0.0` is an **illustrative example of a real release**, not a recommendation to always use that exact version; pick an appropriate and still-maintained patch in the corresponding release train.
- If a project **already has** a feature starter pulling in the desired libraries, adding the base starter just to re-include the same JARs is unnecessary.

If you need Config Client, replace or add the dependency matching your need:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-config</artifactId>
</dependency>
~~~

Do not use `spring-cloud-starter` in place of `spring-cloud-starter-config`: the two artifacts address different requirements.

### 6.2. Gradle: Managing Versions with a Platform BOM

Below is the `dependencies` snippet illustrating a **validly configured Spring Boot Gradle build**:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:2025.0.0"
    )
    implementation "org.springframework.cloud:spring-cloud-starter"
}
~~~

The snippet uses Gradle's `platform` mechanism. You may use Spring's dependency-management plugin according to project conventions; there is no need to blindly apply both approaches. Spring Boot dependencies must still be managed according to the proper Boot setup. In Gradle Kotlin DSL, the equivalent syntax is `implementation(platform("..."))`.

### 6.3. Why Shouldn't You Mix the Three Modules with Arbitrary Versions?

Suppose a project manually pins `spring-cloud-commons` from one release train, `spring-cloud-context` from another release train, and adds a starter from a third train. Maven/Gradle may still resolve a dependency tree, yet APIs and auto-configurations may not align. Common consequences include `NoSuchMethodError`, `ClassNotFoundException`, bean loading failures, or unexpected configuration behavior.

**Principle:** select Spring Boot first, check the compatible Cloud train, let the BOM manage Cloud versions, then inspect the dependency tree to verify actual versions. Override a module version only with a clear reason and thorough compatibility testing.

## 7. Reading the Dependency Tree to Find Root Causes

### 7.1. Maven

The following commands are suggestions to run in a **target project** during practice, not actions required for reading this lesson:

~~~bash
# View Cloud dependencies and paths in the dependency tree
mvn dependency:tree -Dincludes=org.springframework.cloud

# View the merged POM after parent and dependencyManagement
mvn help:effective-pom
~~~

How to read the output:

~~~text
com.example:orders-service:jar:1.0.0
\- org.springframework.cloud:spring-cloud-starter:jar:<resolved-version>:compile
   +- org.springframework.cloud:spring-cloud-context:jar:<resolved-version>:compile
   \- org.springframework.cloud:spring-cloud-commons:jar:<resolved-version>:compile
~~~

This is an **abbreviated illustrative tree**, not verbatim output from a specific release train. It shows:

- `spring-cloud-starter` is declared directly.
- `spring-cloud-context` and `spring-cloud-commons` can enter transitively.
- `<resolved-version>` must be replaced with the version Maven actually resolves.
- An artifact may be excluded or resolved to another version due to dependency management rules, exclusions, or dependency conflicts.

If `spring-cloud-context` appears in the tree, trace its path to see which starter pulled it in before adding a direct dependency.

### 7.2. Gradle

~~~bash
# Runtime dependencies tree
./gradlew dependencies --configuration runtimeClasspath

# Why this artifact appears and which version was selected
./gradlew dependencyInsight --dependency spring-cloud-context \
  --configuration runtimeClasspath

./gradlew dependencyInsight --dependency spring-cloud-commons \
  --configuration runtimeClasspath
~~~

In PowerShell/Windows, write the `dependencyInsight` command on **one line** and use `gradlew.bat` as appropriate; the `\` line breaks above only illustrate Unix shell syntax.

`dependencyInsight` is especially helpful when a version is picked by a BOM, constrained by rules, or bumped due to another dependency. The goal is to trace **why that version is present**, not merely check JAR presence/absence.

### 7.3. The JAR Is on the Classpath, Yet the Feature Doesn't Work?

Follow this inspection sequence:

1. **Right artifact?** Check the dependency tree on `runtimeClasspath`, not just `testRuntimeClasspath`.
2. **Right implementation?** For example, Commons has the `DiscoveryClient` interface, yet using Eureka requires the matching starter/client.
3. **Did auto-configuration match?** Read Spring Boot's condition evaluation report (via debug logging or Actuator with proper access controls).
4. **Were required beans created?** Inspect `ApplicationContext` in an integration test or check Actuator beans when enabled and secured.
5. **Does it actually work?** Send test calls, check instance lists, refresh, load balancing, or configuration data as required.

An application can **compile** because the API exists, yet **still fail at runtime** due to a missing provider, wrong registry URL, misconfigured property, or insufficient permissions.

## 8. Example Requirement Classification Before Choosing Dependencies

A team is building `orders-service`. Requirements evolve gradually:

| Practical requirement | Component to consider | Reason |
| --- | --- | --- |
| Only need shared APIs to work with `DiscoveryClient` | `spring-cloud-commons` (direct or pulled via starter) | Supplies the contract; may need `SimpleDiscoveryClient` for static data |
| Need a bean recreated after a controlled refresh | `spring-cloud-context` | Supplies `@RefreshScope` and context/refresh mechanics |
| Need general Cloud foundation in a Boot project | `spring-cloud-starter` | Bundles foundational libraries; doesn't supply all Cloud features yet |
| Want centralized config loaded from Config Server | `spring-cloud-starter-config` and proper Config Data setup | Needs the Config Client implementation |
| Want instance registration/lookup via Eureka | `spring-cloud-starter-netflix-eureka-client` | Needs the matching discovery/registry provider |
| Want to call `http://inventory-service` with client-side load balancing | `spring-cloud-starter-loadbalancer`, instance source, and integrated HTTP client | Must have instance lookup and an instance selector |
| Want fault control with Resilience4j | Appropriate CircuitBreaker starter and policy config | Commons/Context alone do not fully implement circuit breaking |

Do not add every starter "just in case." Every dependency alters the classpath, auto-configuration, configuration surface, and upgrade path. Select starters based on **needed behaviors**.

## 9. Testing to Confirm Correct Identification

Identifying by JAR name is the first step; tests must confirm the abstraction layer and implementation match properly.

### 9.1. Verifying Discovery

An integration test can inject `DiscoveryClient` and query instances of a service:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest
class DiscoveryWiringTest {
    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void findsConfiguredInventoryService() {
        assertThat(discoveryClient.getInstances("inventory-service"))
                .isNotEmpty();
    }
}
~~~

For the test to be meaningful, the test environment must declare a static instance list or an appropriate discovery server/test fixture. This test proves **instances can be queried under test configuration**, not that an external registry works in production. Testing real Eureka/Consul requires a separate integration test.

### 9.2. Verifying Refresh

With a `@RefreshScope` bean, a test can update the configuration source in the test environment, trigger refresh via a compatible mechanism, and verify that subsequent accesses receive the updated value. At the same time, verify the bean is recreated or rebound as designed.

Do not test by merely editing a config file and assuming Spring reloads it automatically. You must control the **configuration change event** and the **refresh point**. When using Config Client, also test behavior when Config Server is slow, unavailable, or returns incomplete config.

### 9.3. Verifying Load Balancing and Operational Behavior

- Prepare two `inventory-service` instances with distinguishable responses.
- Use a LoadBalancer-integrated client to send multiple requests.
- Confirm instances are picked based on the provided list and configured policy; never assume two instances always alternate strictly in every situation.
- Test timeouts, connection errors, and behavior when the instance list is empty.
- Measure metrics/tracing and inspect the application's auto-configuration conditions per environment.

## 10. Common Misconceptions

| Symptom | Common misconception | Where to check |
| --- | --- | --- |
| `DiscoveryClient` injects, yet returns no instances | "Commons includes its own registry" | Check discovery provider or `SimpleDiscoveryClient` plus instance source |
| `@RefreshScope` is present, yet config updates have no effect | "Context automatically detects every config change" | Check `Environment` reload, refresh trigger, bean scope, and dependent object lifecycles |
| Added `spring-cloud-starter`, yet cannot reach Config Server | "The base starter includes Config Client" | Add `spring-cloud-starter-config` and check matching `spring.config.import` |
| Cloud BOM is present, yet runtime misses classes | "The BOM downloads all JARs automatically" | Check `<dependencies>` or `implementation`; BOM only manages versions |
| Project reports compatibility error at startup | "Every Spring Cloud release supports every Spring Boot" | Consult release train/Boot matrix, remove mismatched overrides or stale dependencies |
| Dependency tree shows the same artifact via multiple starters | "Must delete every duplicate dependency path" | Inspect selected version and real conflicts; Maven/Gradle mediate versions |
| Starter added, yet auto-configuration does not run | "Having the JAR always creates the bean" | Inspect conditions, required properties, classpath, and custom beans |
| `ServiceInstance` returned, yet requests fail | "Discovery guarantees healthy instances" | Check endpoints, health, connectivity, timeouts, and how instance lists refresh |

### 10.1. When Should You Declare Core Libraries Directly?

You can declare `spring-cloud-commons` or `spring-cloud-context` directly in a library module that **publicly uses their APIs**, especially when documenting explicit compile dependencies. In runnable Spring Boot applications, feature starters are usually more convenient because they pull in required integration pieces. The choice depends on module architecture, needed features, and your team's transitive-dependency policy.

Avoid "seeing a compile error and directly adding the newest Commons version" without checking the BOM; that easily breaks release-train compatibility.

## 11. Hands-on Exercises

**Exercise 1 — Classifying artifacts.** Given four coordinates:

~~~text
org.springframework.cloud:spring-cloud-context
org.springframework.cloud:spring-cloud-starter
org.springframework.cloud:spring-cloud-commons
org.springframework.cloud:spring-cloud-dependencies
~~~

Label: the library supplying abstractions, the library managing context/refresh, the base starter, and the BOM. For each artifact, state one capability that is **not** guaranteed merely by declaring it.

**Exercise 2 — Fixing a dependency mistake.** A project imported the Cloud BOM and declared only `spring-cloud-starter`. The team wants to access Config Server, yet the application cannot read config from it. Propose the dependency and property to add, and explain why the already-present `spring-cloud-context` does not fulfill the entire requirement.

**Exercise 3 — Tracing a transitive dependency.** `dependencyInsight` shows `spring-cloud-context` was pulled in by a feature starter. Identify the entry artifact, the resolved version, and which constraint/BOM applied. Explain why adding a direct `spring-cloud-context` dependency just to "make sure it is there" is unnecessary.

**Exercise 4 — Runtime verification.** A service injects `DiscoveryClient`, yet `getInstances("inventory-service")` returns an empty list. Outline a verification sequence from classpath, bean, provider, and instance config through actual connectivity. Specify what evidence proves an external registry is genuinely working.

## 12. Takeaways and Reference Sources

Remember these three artifacts by **responsibility**:

- **`spring-cloud-commons`**: *shared contracts and abstractions* for distributed patterns such as discovery, service registry, and client-side load balancing.
- **`spring-cloud-context`**: *context, environment, and refresh mechanics* for the application.
- **`spring-cloud-starter`**: *foundational dependency bundle*. To gain concrete features like Config Client, Eureka, or LoadBalancer, add the matching integration—never infer it solely from the generic starter name.

When deploying, verify **artifact → dependency tree → auto-configuration → beans → actual runtime behavior**, while keeping a compatible **Spring Boot – Spring Cloud release train** pair.

Official sources to cross-check for your active version:

1. [Spring Cloud – overview and Spring Boot compatibility matrix](https://spring.io/projects/spring-cloud/)
2. [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
3. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
4. [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
5. [Maven Central – `org.springframework.cloud:spring-cloud-starter`](https://central.sonatype.com/artifact/org.springframework.cloud/spring-cloud-starter)
