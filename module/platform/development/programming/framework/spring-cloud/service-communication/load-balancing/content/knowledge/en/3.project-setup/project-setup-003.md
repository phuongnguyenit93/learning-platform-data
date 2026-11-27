# Starters for LoadBalancer and Each HTTP Client

For a Spring Cloud application to call services by service ID and distribute requests across instances, you need to combine the right dependencies across three layers: **HTTP client**, **Spring Cloud LoadBalancer**, and **service discovery source**. Each HTTP client has its own starter; LoadBalancer provides the shared instance-selection mechanism; discovery supplies the list of currently available instances.

For example, `order-service` wants to call `catalog-service`. The application can use `RestClient`, `WebClient`, or OpenFeign, but all three need a mechanism to resolve the name `catalog-service` into a specific instance. Declaring the right dependencies enables Spring Boot to create the HTTP client and Spring Cloud to wire that client with LoadBalancer.

## 1. Three Dependency Groups to Distinguish

### HTTP Client Starter

The HTTP client starter provides the API used to send requests:

| Calling Style | Commonly Used Starter | Key Components |
|---|---|---|
| `RestClient` | `spring-boot-starter-web` | Spring MVC and synchronous HTTP APIs; `RestClient` is available since Spring Framework 6.1 |
| `WebClient` | `spring-boot-starter-webflux` | Reactive HTTP client `WebClient` |
| OpenFeign | `spring-cloud-starter-openfeign` | Declares HTTP clients via interfaces and annotations |

`RestClient` and `WebClient` are Spring Framework APIs. OpenFeign is a Spring Cloud integration that generates clients from interfaces. Having one of these starters only provides the ability to make HTTP calls; it does not automatically produce an instance list for a service ID.

### Spring Cloud LoadBalancer Starter

The shared dependency is:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

This starter brings Spring Cloud LoadBalancer and the required integration components into the application. It provides `ServiceInstance` selection mechanisms, such as round-robin, and abstractions like `ServiceInstanceListSupplier`. For `RestClient` and `WebClient`, the application typically annotates the builder with `@LoadBalanced`. For OpenFeign, the LoadBalancer integration is automatically used when the corresponding dependency is present.

### Service Discovery Starter

LoadBalancer needs an instance source. In a registry-based system, add the starter for the discovery platform actually deployed. For example:

| Registry Platform | Discovery Starter |
|---|---|
| Eureka | `spring-cloud-starter-netflix-eureka-client` |
| Consul | `spring-cloud-starter-consul-discovery` |

Only select the starter matching your actual infrastructure. An application does not need both Eureka and Consul if it only uses one registry. If not using a registry, you can supply static instances via `SimpleDiscoveryClient` or an application-configured `ServiceInstanceListSupplier`.

## 2. Managing Spring Boot and Spring Cloud Versions

Spring Cloud starters must come from the same release train compatible with the project's Spring Boot version. Import the `spring-cloud-dependencies` BOM so Maven or Gradle manages versions consistently; do not manually assign different versions to individual starters.

Maven example (replace `SET_COMPATIBLE_RELEASE_TRAIN` with the release train compatible with your Spring Boot version):

```xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>SET_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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
```

After importing the BOM, declare dependencies without specifying `<version>` for each starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
```

With Gradle Groovy DSL, you can import the same BOM using `platform`:

```groovy
ext {
    springCloudVersion = 'SET_COMPATIBLE_RELEASE_TRAIN'
}

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
```

Consult the official compatibility matrix between Spring Boot and Spring Cloud before picking a release train. If you upgrade Spring Boot, re-check the corresponding release train and upgrade the Spring Cloud dependencies together.

## 3. Dependencies for Each HTTP Client

### Using RestClient

`RestClient` is suitable for synchronous HTTP calls. With Spring Boot 3.2 or later (using Spring Framework 6.1 or later), you can declare:

```xml
<dependencies>
    <!-- Provides Spring MVC and RestClient -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- Selects instances by service ID -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Only add if the application registers/discovers services via Eureka -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

If the system uses Consul, replace the Eureka dependency with `spring-cloud-starter-consul-discovery`. If the project already has another discovery provider, continue using that provider and do not add a second registry just to enable LoadBalancer.

Declare a builder annotated with `@LoadBalanced`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Then inject the builder into your client and use the service ID in the URL:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogRestClient {

    private final RestClient client;

    CatalogRestClient(
            @Qualifier("loadBalancedRestClientBuilder") RestClient.Builder builder) {
        this.client = builder.build();
    }

    ProductResponse getProduct(String productId) {
        return client.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .body(ProductResponse.class);
    }
}
```

`catalog-service` must match the registered service name or service ID provided by the discovery source. When a project has multiple `RestClient.Builder` beans, name the bean and use `@Qualifier` to inject the load-balanced builder.

### Using WebClient

`WebClient` provides a reactive, non-blocking API. Its starter is `spring-boot-starter-webflux`; add LoadBalancer and the discovery provider just as with `RestClient`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Declare the builder:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Use the builder to create the client:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
class CatalogWebClient {

    private final WebClient webClient;

    CatalogWebClient(
            @Qualifier("loadBalancedWebClientBuilder") WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<ProductResponse> getProduct(String productId) {
        return webClient.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .bodyToMono(ProductResponse.class);
    }
}
```

`spring-boot-starter-webflux` can be used solely to create the `WebClient` HTTP client; the application does not have to run a WebFlux server. If the project also includes `spring-boot-starter-web`, Spring Boot typically chooses a Servlet-based application at startup, while `WebClient` can still be injected and used as an HTTP client.

### Using Spring Cloud OpenFeign

OpenFeign lets you declare HTTP calls via an interface. The primary starter is `spring-cloud-starter-openfeign`; also declare `spring-cloud-starter-loadbalancer` explicitly to enable load balancing integration:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-openfeign</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Spring Cloud OpenFeign may declare LoadBalancer as an optional dependency. Therefore, do not assume LoadBalancer is already on the classpath just because you added the OpenFeign starter. Check the dependency tree and declare the LoadBalancer starter when the application needs load balancing by service ID.

Enable Feign client scanning and declare the interface:

```java
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableFeignClients
class OrderApplication {
}
```

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/products/{id}")
    ProductResponse getProduct(@PathVariable("id") String productId);
}
```

When LoadBalancer is present, the name `catalog-service` in `@FeignClient` is used as the service ID to select an instance. You do not need to create a `RestClient.Builder` or `WebClient.Builder` for Feign; OpenFeign's integration handles wiring with LoadBalancer.

## 4. Configuring the Discovery Source for Starters

The examples above assume a discovery provider is available. With Eureka, the calling application typically has configuration like:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
```

The target service registers with the name `catalog-service`; `order-service` looks up instances by that exact name. Instance registration properties, advertised addresses, and the registry URL must match the deployment environment.

In a hands-on exercise where a separate registry is not needed yet, you can declare static instances via `SimpleDiscoveryClient`:

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

With this configuration, LoadBalancer has two candidate instances for `catalog-service`. This is a convenient way to test instance selection; in real environments, the instance list usually comes from a registry or the deployment platform.

## 5. Choosing the Right Dependency Combination

| Need | HTTP Client Starter | LoadBalancer | Discovery |
|---|---|---|---|
| Synchronous calls with RestClient | `spring-boot-starter-web` | `spring-cloud-starter-loadbalancer` | Eureka, Consul, or SimpleDiscoveryClient |
| Reactive calls with WebClient | `spring-boot-starter-webflux` | `spring-cloud-starter-loadbalancer` | Eureka, Consul, or SimpleDiscoveryClient |
| Interface-based calls with OpenFeign | `spring-cloud-starter-openfeign` | `spring-cloud-starter-loadbalancer` | Eureka, Consul, or SimpleDiscoveryClient |

An application can use multiple HTTP clients at the same time. In that case, declare the required client starters and only one suitable discovery source. All clients can share the same service ID, though each client type needs its own integration setup as shown above.

## 6. Inspecting Dependencies and Common Errors

After adding dependencies, inspect the dependency tree to confirm the right starters are included in the application:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
```

When requests by service ID fail to resolve, check these in order:

1. **Wrong release train:** incompatible Spring Boot and Spring Cloud versions can cause startup failures or class linkage errors. Check the BOM and compatibility matrix.
2. **Missing LoadBalancer:** the HTTP client still runs, but lacks integration to select instances. Check for `spring-cloud-starter-loadbalancer` on the runtime classpath.
3. **Missing instance source:** LoadBalancer is configured, but discovery returns an empty list. Check the registry, discovery starter, and service ID.
4. **Wrong service ID:** the name in the URL or `@FeignClient` does not match the registered service name.
5. **Unannotated builder:** with `RestClient` and `WebClient`, verify the client is actually built from a builder annotated with `@LoadBalanced`; avoid accidentally injecting a plain builder.
6. **HTTP client starter only:** `spring-boot-starter-web`, `spring-boot-starter-webflux`, or OpenFeign do not by themselves provide a registry or instance list.

Distinguishing missing-dependency errors from discovery errors helps address the root cause. If the application fails to start due to missing classes or beans, check dependencies and auto-configuration. If the application starts up but cannot find instances, check the service ID and the data provided by `DiscoveryClient`. If an instance was selected but the request fails, inspect the target service's host, port, network, and response.

## 7. Key Takeaways

Choose the HTTP client starter based on the API you want to use: `spring-boot-starter-web` for RestClient, `spring-boot-starter-webflux` for WebClient, and `spring-cloud-starter-openfeign` for OpenFeign. Add `spring-cloud-starter-loadbalancer` to select instances by service ID, then connect a discovery source such as Eureka, Consul, or static instance configuration. Import a Spring Cloud BOM compatible with Spring Boot to keep dependencies aligned on the same version set and ensure stable application startup.
