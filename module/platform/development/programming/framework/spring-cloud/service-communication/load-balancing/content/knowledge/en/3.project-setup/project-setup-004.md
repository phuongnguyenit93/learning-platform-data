# Distinguishing Required, Optional, and Transitive Dependencies

When setting up an application with Spring Cloud LoadBalancer, choosing the right dependencies ensures the application has the components needed to resolve a service ID and select a `ServiceInstance`, while avoiding pulling in libraries the project does not use. You should distinguish three groups: dependencies directly needed by the features in use, dependencies only needed for an additional capability, and dependencies automatically brought in by the build tool through another dependency.

In the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module, an application can integrate LoadBalancer with `RestClient`, `WebClient`, or OpenFeign; fetch the instance list from discovery; and then apply caching, health checks, retries, timeouts, and error observability. Each choice changes the set of dependencies needed. There is no single list that fits every application.

## 1. Three Concepts to Distinguish

### Required Dependencies

A required dependency is a library the application needs to compile or run the capability it has chosen. If the application wants to use Spring Cloud LoadBalancer to turn a URL containing a service ID such as `http://catalog-service/products/42` into an instance address, the application must bring LoadBalancer integration onto the classpath.

For a typical Spring Cloud application, the starting dependency is:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

This starter provides the integration configuration and required LoadBalancer components. The application should declare this starter directly because the application itself is actively using the load balancing capability.

### Optional Dependencies

An optional dependency is only needed when the application enables an additional capability. For example, Caffeine can be added to use Caffeine-based caching; Actuator can be added to provide health/metrics endpoints and support application observability; test libraries are only needed during testing.

If the application does not use that feature, there is no need to add the corresponding dependency. Adding an optional library also does not automatically configure the feature: the application still needs appropriate beans, properties, or integration mechanisms configured.

### Transitive Dependencies

A *transitive dependency* is a library automatically resolved by the build tool because another dependency declares it. For instance, the LoadBalancer starter depends on Spring Cloud modules that provide discovery abstractions and the LoadBalancer implementation. When you declare the starter, Maven or Gradle pulls in the required modules according to the starter's metadata.

The diagram below illustrates the conceptual relationship; the exact dependency tree depends on the Spring Cloud and Spring Boot versions your project uses:

```text
Application
└── spring-cloud-starter-loadbalancer       (declared directly)
    ├── spring-cloud-loadbalancer           (pulled in transitively)
    ├── spring-cloud-commons                (pulled in transitively)
    └── other core Spring libraries         (resolved via POM)
```

You do not need to re-declare every submodule just because you see it in the dependency tree. However, if your application source code directly uses a library's API, or exposes types from that library in your application's own API, consider declaring the dependency directly to make the contract explicit and avoid accidental reliance on the transitive tree.

## 2. Selecting Dependencies by HTTP Client

LoadBalancer does not replace the HTTP client. It decides the target instance; the HTTP client performs the connection and sends the request. Therefore, in addition to the LoadBalancer starter, the application needs the dependency for the client it chooses.

| Service Calling Approach | Client-Side Dependency | LoadBalancer Dependency |
|---|---|---|
| `RestClient` | `spring-boot-starter-web` on a Spring Framework version that includes `RestClient` | `spring-cloud-starter-loadbalancer` |
| `WebClient` | `spring-boot-starter-webflux` or WebFlux dependencies suited to the application's structure | `spring-cloud-starter-loadbalancer` |
| OpenFeign | `spring-cloud-starter-openfeign` | Add `spring-cloud-starter-loadbalancer` to enable load balancing integration for Feign |

Only add the client that the application actually uses. An application may use multiple clients, but there should be a clear architectural reason, and you should avoid pulling in two web stacks just because of a configuration example.

### Using RestClient

`RestClient` is Spring Framework's synchronous HTTP calling API. With Spring Boot 3.2 or later, `spring-boot-starter-web` provides the Spring MVC foundation and corresponding Spring Web libraries to use `RestClient`.

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Afterward, the application can declare a `RestClient.Builder` bean annotated with `@LoadBalanced` and send requests to a URL containing a service ID. If using a Spring Framework version that does not have `RestClient` yet, choose an HTTP client API compatible with your platform version rather than adding a separate dependency to mimic an unsupported API.

### Using WebClient

`WebClient` is suitable for reactive applications or cases requiring a non-blocking HTTP API. The WebFlux starter provides `WebClient` along with the necessary reactive components:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

The application creates a `WebClient.Builder` with `@LoadBalanced`, then calls a URI containing a service ID. If the current application runs Spring MVC and only wants to use `WebClient` as an HTTP client, consider adding only the necessary WebFlux modules rather than unintentionally switching the server architecture to reactive.

### Using OpenFeign

OpenFeign generates clients from interfaces declared with `@FeignClient`. To use OpenFeign and select instances via Spring Cloud LoadBalancer, the application needs both the OpenFeign starter and the LoadBalancer starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

When LoadBalancer integration is detected and enabled according to the version in use, Feign can use the service name in `@FeignClient(name = "catalog-service")` to locate instances. If only OpenFeign is present without LoadBalancer integration, do not assume the service name will automatically resolve to an instance.

## 3. Selecting Dependencies for Service Discovery

LoadBalancer needs a list of `ServiceInstance` objects to choose from. The source of that list depends on how the system is deployed:

| Instance Source | Additional Dependency | When to Use |
|---|---|---|
| `SimpleDiscoveryClient` | Usually no separate registry starter needed | Declaring static instances, testing, or simple environments |
| Eureka | Corresponding Eureka Client starter, usually `spring-cloud-starter-netflix-eureka-client` | Systems registering and looking up services via Eureka |
| Consul | Corresponding Consul Discovery starter, usually `spring-cloud-starter-consul-discovery` | Systems using Consul as the registry |
| Kubernetes | Discovery module compatible with Spring Cloud Kubernetes and the deployment platform | Integrating discovery with Kubernetes |

Only choose the provider that the actual environment uses. Do not put Eureka, Consul, and Kubernetes discovery into the same application unless the architecture requires multiple discovery sources.

With `SimpleDiscoveryClient`, instances can be declared in configuration:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

This example uses two static addresses for the `catalog-service` service ID. When switching to Eureka or Consul, the registry supplies a dynamic list of instances; the application must configure the registry address and registration details matching the environment.

Note that discovery and LoadBalancer are two distinct responsibilities. Discovery finds registered instances; LoadBalancer chooses one instance from the list supplied by the supplier. Simply adding a registry dependency does not automatically produce client-side load balancing configuration if the HTTP client is not integrated with LoadBalancer.

## 4. Common Optional Dependencies

### Caffeine for Caching

Spring Cloud LoadBalancer has an instance list caching mechanism. When you want to use Caffeine-based caching, you can add the Caffeine library:

```xml
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
```

This is an optional dependency for cache selection. Do not add it just because you see the word "cache" in the documentation; determine whether the default cache of the version in use already meets your requirements before considering Caffeine and configuring an appropriate TTL. Caching for too long can retain stale instance lists after the registry changes.

### Actuator and System Observability

If the application needs management, health, or metrics endpoints, you can add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Actuator supports observing application state and provides configured endpoints. It is not a core dependency for LoadBalancer to select instances. Enabling endpoints, access permissions, and exposure levels must suit the deployment environment.

### Testing Dependencies

In Maven, `spring-boot-starter-test` is typically declared with `test` scope; in Gradle, `testImplementation` is used. These dependencies are for testing configuration, clients, and behavior when the registry has no instances. They should not be packaged as runtime dependencies of the application.

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

## 5. Managing Versions with the Spring Cloud BOM

Spring Boot and Spring Cloud have a version compatibility matrix. Do not pick starter versions independently or mix Spring Cloud modules from multiple release trains. Choose the release train compatible with your project's Spring Boot version and use the BOM to manage versions consistently.

Maven example:

```xml
<properties>
    <spring-cloud.version>YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN</spring-cloud.version>
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
</dependencies>
```

`YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN` is a placeholder: replace it with the release train published by Spring as compatible with the Spring Boot version in use. When the BOM already manages versions, you normally omit `<version>` on individual Spring Cloud starters.

With Gradle, you can import the BOM via `platform`:

```groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )
    implementation "org.springframework.cloud:spring-cloud-starter-loadbalancer"
}
```

The BOM only manages dependency versions; it does not automatically add every Spring Cloud module to the application. To use LoadBalancer, you must still declare the starter in `dependencies`.

## 6. Scopes and the Meaning of Optional in Maven and Gradle

The concepts of required, optional, and transitive describe the role of a dependency in an application. Maven and Gradle also have scope/configuration mechanisms to decide which phase a dependency is present in and whether it is propagated downstream.

### Maven

| Scope | Common Meaning | Example |
|---|---|---|
| `compile` | Present on both compile classpath and runtime classpath; this is the default scope | Starters needed by both application code and runtime |
| `runtime` | Needed at runtime but not needed to compile source code | A driver or implementation loaded only at runtime |
| `test` | Only used for compiling and running tests | `spring-boot-starter-test` |
| `provided` | Expected to be provided by the runtime environment | APIs provided by a container or platform |

In Maven, `<optional>true</optional>` affects dependency propagation: the module declaring that dependency does not automatically transitively pass it on to downstream consuming modules. It does not simply mean "this dependency will not be loaded at runtime in the current project." If the current application needs a feature provided by an optional dependency, the application must declare the appropriate dependency directly.

### Gradle

| Configuration | Common Meaning | Example |
|---|---|---|
| `implementation` | Internal dependency needed to compile and run the module | LoadBalancer starter in an application |
| `api` | Dependency exposed in a library's API and propagated to consumers | Dependency types appearing in a public API |
| `runtimeOnly` | Needed only at runtime; API not used at compile time | Dynamically loaded drivers or implementations |
| `compileOnly` | Needed for compilation but not packaged as a runtime dependency | APIs provided by another environment |
| `testImplementation` | Only used for compiling and running tests | Test libraries |

Do not replace `implementation` with `compileOnly` for the LoadBalancer starter in a normal application: integration configuration must be present when the application starts. Also avoid using `api` just "to be safe"; only use it when the dependency is genuinely part of a public API that the module wants consumers to see.

## 7. Inspect the Dependency Tree Instead of Guessing

The dependency tree shows which dependencies are declared directly, which are pulled in transitively, and which versions are selected after conflict resolution.

With Maven:

```bash
mvn dependency:tree
```

To focus on Spring Cloud modules:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To trace why a module is present or why a version was chosen:

```bash
./gradlew dependencyInsight --dependency spring-cloud-loadbalancer --configuration runtimeClasspath
```

When reading the output, check:

1. Is the LoadBalancer starter present on the runtime classpath?
2. Is the HTTP client used by the application present and compatible?
3. If using a registry, is the corresponding discovery provider declared?
4. Are there multiple competing versions of Spring Cloud or Spring Framework?
5. Has any test-only dependency been accidentally placed into runtime?
6. Is a directly added library truly necessary, or is it merely duplicating a transitive dependency?

If a dependency appears multiple times in the tree, that does not necessarily mean multiple JARs will be packaged. Maven and Gradle apply version resolution rules; inspect the final resolved version and the path bringing the dependency in rather than simply counting lines.

## 8. Dependency Selection Examples by Scenario

| Scenario | Declare Directly | Add Only When Needed |
|---|---|---|
| Synchronous REST with RestClient and static instances | `spring-boot-starter-web`, `spring-cloud-starter-loadbalancer` | Caffeine, Actuator, test starter |
| Reactive calls with WebClient and Eureka | `spring-boot-starter-webflux`, `spring-cloud-starter-loadbalancer`, Eureka Client starter | Caffeine, Actuator, test starter |
| Calls using OpenFeign and Consul | `spring-cloud-starter-openfeign`, `spring-cloud-starter-loadbalancer`, Consul Discovery starter | Caffeine, Actuator, test starter |
| Testing two local instances only | The HTTP client in use and `spring-cloud-starter-loadbalancer` | External registry, Caffeine, Actuator if not serving the test goal |

The tables above categorize dependencies by role, not as complete POMs for every project. Cross-check against your specific Spring Boot/Spring Cloud versions, packaging setup, and discovery infrastructure before finalizing dependencies.

## 9. Common Mistakes When Declaring Dependencies

**Adding only OpenFeign and expecting Feign to load balance automatically.** OpenFeign provides the mechanism to generate HTTP clients from interfaces. To resolve service names into instances with Spring Cloud LoadBalancer, LoadBalancer integration must be on the classpath and configured properly.

**Adding a registry dependency without LoadBalancer.** The registry can supply instance information, but the HTTP client still needs the selector integration to translate logical URLs into concrete addresses.

**Specifying individual versions for each Spring Cloud module.** This easily creates incompatible combinations. Use the appropriate BOM to manage versions by release train.

**Directly adding every module seen in the dependency tree.** This makes the POM or Gradle build harder to maintain and can lock the application to internal implementation details. Only declare submodules directly when the application explicitly uses their APIs or features.

**Treating optional dependencies as never needed.** Optional only means the additional feature is not always required, and in Maven it also controls transitive propagation. If you enable Caffeine caching or a specific integration, the application must still supply the library that feature requires.

**Adding both Web MVC and WebFlux without understanding the impact.** Both starters can coexist in one application, but Spring Boot will choose the web application type based on the classpath and configuration. Clearly determine the server stack and client API the application needs.

## 10. Process for Finalizing Project Dependencies

Before adding libraries, answer each question in order:

1. Will the application call services using `RestClient`, `WebClient`, or OpenFeign?
2. Does the application need client-side load balancing, or does it only call a fixed address?
3. Do instances come from `SimpleDiscoveryClient`, Eureka, Consul, or Kubernetes?
4. Are custom caching, health/metrics endpoints, or advanced observability required?
5. Which Spring Boot version is in use and which Spring Cloud release train is compatible?
6. Does the dependency tree after building show the right runtime classpath with no conflicting versions?

Once selected, declare the required starters directly, let the BOM manage versions, only add discovery providers and optional libraries matching actual features, and then inspect the dependency tree. This keeps the project configuration aligned with the architecture: the HTTP client sends requests, discovery supplies the instance list, and Spring Cloud LoadBalancer picks the right instance for the service ID.
