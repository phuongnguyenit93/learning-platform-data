# Choosing the Resilience4j Starter for Blocking or Reactive Applications

When integrating Circuit Breaker into a Spring Cloud application, you need to choose the Resilience4j starter that matches how the application executes calls to dependent services. Applications making synchronous blocking calls use the standard Resilience4j starter; applications processing data through a reactive pipeline use the Reactor Resilience4j starter. Choosing the right starter enables Spring Cloud to create the appropriate Circuit Breaker factory and preserves the application's processing model.

Within the scope of `SPRING_CLOUD_CIRCUIT_BREAKER`, the environment setup step includes identifying the application style, choosing the corresponding dependency, managing a Spring Cloud version compatible with Spring Boot, and verifying that the dependency is on the classpath. The starter only provides the integration; protection policies such as failure threshold, sliding window, OPEN duration, and fallback still need to be configured according to the service's needs.

## 1. Distinguishing Blocking and Reactive Before Choosing a Dependency

The decision point is the return type and execution model of the protected call:

| Criterion | Blocking | Reactive |
|---|---|---|
| Common return type | Direct return value such as **Stock** or **Product** | Publisher such as **Mono<Stock>** or **Flux<Product>** |
| Execution model | Calling thread waits for the operation to complete | Pipeline emits signals when data, errors, or completion occur |
| Circuit Breaker API | **CircuitBreakerFactory** | **ReactiveCircuitBreakerFactory** |
| Resilience4j starter | **spring-cloud-starter-circuitbreaker-resilience4j** | **spring-cloud-starter-circuitbreaker-reactor-resilience4j** |
| Common web component | Spring MVC with **spring-boot-starter-web** | Spring WebFlux with **spring-boot-starter-webflux** |
| Common client | **RestClient**, **RestTemplate**, or synchronous client | **WebClient** returning **Mono** or **Flux** |

A Spring MVC application typically has methods calling dependent services that return results directly. When a call takes two seconds, the calling processing thread usually has to wait during that time. This is the blocking model.

In a WebFlux application, the client typically returns **Mono<T>** or **Flux<T>**. Processing steps are chained into a reactive pipeline; threads do not need to wait synchronously at each I/O step. This is the reactive model. The Circuit Breaker needs to wrap the publisher properly so that when in the OPEN state, a rejection error is emitted into the pipeline and handled by a reactive fallback.

Do not choose a starter solely based on whether the project uses Spring Boot or has an HTTP endpoint. Look at the signature of the operation calling the dependent service. If the operation returns a direct value and executes synchronously, use the blocking API. If the operation returns **Mono** or **Flux** and is processed in a reactive pipeline, use the reactive API. You should not call **block()** just to turn a publisher into a synchronous call and treat that as reactive integration.

## 2. Required Dependencies for Each Application Type

Spring Cloud CircuitBreaker supports Resilience4j via two main starters:

- **Blocking:** **org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j**
- **Reactive:** **org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j**

The application needs to add the web starter corresponding to the endpoint and client model in use. Spring MVC typically uses **spring-boot-starter-web**; WebFlux typically uses **spring-boot-starter-webflux**.

| Application Type | Spring Boot web starter | Spring Cloud CircuitBreaker starter |
|---|---|---|
| Spring MVC, synchronous client | **spring-boot-starter-web** | **spring-cloud-starter-circuitbreaker-resilience4j** |
| WebFlux, reactive client | **spring-boot-starter-webflux** | **spring-cloud-starter-circuitbreaker-reactor-resilience4j** |

The two CircuitBreaker starters above are choices for two different APIs. Do not add both out of habit. If an application genuinely has both blocking and reactive flows that need protection, clearly identify each flow, check the auto-configuration of the Spring Cloud version in use, and include only the dependencies the project needs. Having **spring-boot-starter-web** or **spring-boot-starter-webflux** alone does not substitute for selecting the CircuitBreaker starter.

## 3. Managing Spring Boot and Spring Cloud Versions

Spring Cloud has release trains and a compatibility matrix with Spring Boot versions. Therefore, you should not independently pick a CircuitBreaker starter version or take the latest Spring Cloud version without checking compatibility.

The standard approach is using the Spring Cloud BOM (**spring-cloud-dependencies**) to manage Spring Cloud dependency versions. The release train version must match the Spring Boot version the project uses. You can consult the compatibility matrix in the Spring Cloud documentation before setting the value of the **spring-cloud.version** property.

The Maven example below illustrates the version management structure. The value **REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN** is a placeholder to be replaced with a release train compatible with your project's Spring Boot version:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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
~~~

If the project uses the Spring Boot parent or Spring Boot dependency management, Spring Boot dependencies such as **spring-boot-starter-web** are usually already version-managed. The Spring Cloud BOM manages Spring Cloud dependencies. As a result, starter declarations do not need an arbitrary version attached to each dependency.

When upgrading Spring Boot, check the corresponding Spring Cloud release train and upgrade the BOM as a compatible pair. Avoid mixing multiple release trains or overriding Resilience4j's own version without a clear reason, as doing so can produce an inconsistent set of dependencies.

## 4. Maven Configuration for a Blocking Application

For a Spring MVC application calling dependent services with a synchronous client, add the following two dependencies to the **dependencies** section of **pom.xml**. The example assumes the project already declares the Spring Boot parent and imports the Spring Cloud BOM as shown above:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>
</dependencies>
~~~

The CircuitBreaker starter puts the Resilience4j integration for Spring Cloud CircuitBreaker onto the classpath. The application can inject **CircuitBreakerFactory** and create named circuit breakers for each dependent service.

Example of a gateway calling a synchronous client:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

**InventoryClient.getStock** in the example is a synchronous operation returning **Stock**. If the Circuit Breaker allows the call, the supplier is executed. If the breaker is OPEN, the supplier is rejected and the fallback function is invoked to return a fallback result. **Stock.unavailable** is an illustrative method defined by the application; actual fallback data must adhere to business rules.

## 5. Maven Configuration for a Reactive Application

For a WebFlux application using **WebClient** and a reactive pipeline, declare WebFlux alongside the Reactor Resilience4j starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
~~~

In a reactive application, use **ReactiveCircuitBreakerFactory**. The protected call returns a **Mono** and the fallback must also return a **Mono**:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryGateway {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Mono<Stock> getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getStock(sku),
            error -> Mono.just(Stock.unavailable(sku))
        );
    }
}
~~~

Here, **ReactiveInventoryClient.getStock** returns **Mono<Stock>**. When the breaker is OPEN, a rejection error is emitted in the reactive pipeline; the fallback function returns an alternative publisher. Do not call **block()** inside the fallback or inside a WebFlux controller, as that can block processing threads and diminish the benefits of the reactive model.

If the client returns **Flux<T>**, check the reactive API provided by the Spring Cloud version in use and keep data processing within the corresponding pipeline. Do not convert back and forth arbitrarily between **Mono**, **Flux**, and synchronous values just to match signatures.

## 6. Dependency Configuration with Gradle

With Gradle, you can import the Spring Cloud BOM using **platform** and then declare the appropriate starter. The Groovy DSL example below uses a **springCloudVersion** variable already defined in the project configuration with a compatible release train:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    // Choose a dependency pair that matches the application model.
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j"
}
~~~

For a reactive application, replace the two dependencies in the example with the following pair:

~~~groovy
implementation "org.springframework.boot:spring-boot-starter-webflux"
implementation "org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j"
~~~

If the project uses Gradle Kotlin DSL or another dependency management plugin, the BOM declaration syntax may differ; the principle remains to import the right Spring Cloud release train and avoid pinning starter versions separately from the BOM.

## 7. Verifying the Right Starter Was Chosen

After modifying dependencies, verify that dependencies are resolved and the application receives the right factory type. With Maven, you can inspect the dependency tree using:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud,io.github.resilience4j
~~~

With Gradle, inspect the runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Verify the output against the following points:

1. The exact CircuitBreaker starter needed by the call flow is present.
2. Spring Cloud dependencies are managed by the chosen release train.
3. There are no unwanted multiple versions of the same Resilience4j library.
4. The application starts and Spring can inject the right factory: **CircuitBreakerFactory** for blocking flows or **ReactiveCircuitBreakerFactory** for reactive flows.
5. Protected calls use the proper return type. A blocking fallback returns a value; a reactive fallback returns a publisher.

If the factory cannot be found, check the artifact name, dependency scope, BOM, and auto-configuration before adding individual Resilience4j libraries. If the classpath has the right starter but fails due to version incompatibility, adjust the Spring Cloud release train to match the Spring Boot version in use. Do not fix errors by randomly adding multiple starters or overriding individual library versions.

## 8. Common Mistakes When Choosing a Starter

- **Using the blocking starter for a reactive publisher:** the code may lack the needed reactive factory or be forced into the wrong conversion model. Choose the Reactor starter when the protected operation returns **Mono** or **Flux**.
- **Using the reactive starter just because the project has WebFlux:** part of the code might still call a synchronous client. Choose based on the API and execution model of each flow, not just the endpoint framework.
- **Confusing the CircuitBreaker starter with the standalone Resilience4j library:** the Spring Cloud CircuitBreaker starter provides Spring Cloud's integration layer and factory. If the application intentionally uses Resilience4j APIs directly, dependency declarations and configuration will differ.
- **Skipping the Spring Cloud BOM:** Spring Cloud and Spring Boot modules may be incompatible when using arbitrary versions.
- **Declaring both starters without checking auto-configuration:** in an application with multiple call models, verify which factory is created and injected into each component.
- **Using the wrong fallback type:** a blocking fallback must return an appropriate value; a reactive fallback must return the corresponding publisher. Returning **Stock** where **Mono<Stock>** is expected causes type errors or forces unnecessary conversions.

## 9. Environment Preparation Checklist

Before moving on to configuring Circuit Breaker policies, confirm:

- [ ] You have determined whether the dependent call is blocking or reactive.
- [ ] You have chosen the appropriate Spring Cloud CircuitBreaker Resilience4j starter.
- [ ] You have chosen a web starter matching the application, if the application needs a web stack.
- [ ] You have imported the Spring Cloud BOM compatible with the Spring Boot version.
- [ ] The dependency tree has no unexpected version conflicts.
- [ ] The application starts and injects the corresponding factory.
- [ ] Sample calls and fallbacks use the proper synchronous or reactive data types.

Once the steps above are complete, the environment is ready for configuring sliding window, failure rate, slow-call rate, OPEN wait duration, HALF_OPEN probe count, timeout, bulkhead, and fallback. Choosing the starter only defines the integration layer and API model; service protection effectiveness still depends on the policies and error handling in subsequent steps.

## Conclusion

Applications making synchronous calls should use **spring-cloud-starter-circuitbreaker-resilience4j** with the **CircuitBreakerFactory** API. Applications processing publishers with Reactor should use **spring-cloud-starter-circuitbreaker-reactor-resilience4j** with the **ReactiveCircuitBreakerFactory** API. Managing Spring Cloud with a BOM compatible with Spring Boot, verifying the classpath, and keeping call and fallback return types consistent will establish a stable foundation for configuring Circuit Breakers for each dependent service.
