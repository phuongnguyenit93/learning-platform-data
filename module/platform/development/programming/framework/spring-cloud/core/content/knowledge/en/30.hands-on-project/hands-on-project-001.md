# Minimal Foundation Application with Commons, Context, and Actuator

> **Chapter:** Hands-on Project  
> **Module:** SPRING_CLOUD_CORE

This hands-on lab builds a small Spring Boot application to combine three foundational parts of Spring Cloud: **Commons** provides the discovery abstraction and feature information, **Context** manages refreshable configuration, and **Actuator** provides observability and administrative endpoints. The application includes a REST API that returns a greeting from configuration, an API that reads a static list of instances via `DiscoveryClient`, a `@RefreshScope` bean, and a set of endpoints for inspection.

We use `SimpleDiscoveryClient` to run the exercise without setting up Eureka or Consul. The sample configuration has a `catalog-provider` instance with the URI `http://localhost:8091`; reading this list does not make a network call to port 8091. The goal is to verify the discovery abstraction and metadata. When dynamic registration, health-aware discovery, or load balancing is needed, the implementation can be replaced with the corresponding provider.

The project uses a compatible GA version pair at the time of writing: Spring Boot **4.1.2**, Spring Cloud **2025.1.4**, and Java **17 or later**. Spring Cloud 2025.1.x supports Boot 4.0.x and Boot 4.1.x starting from 2025.1.2. When working at a different time, choose a version pair from the official compatibility matrix instead of manually mixing two independent versions.

## 1. Expected Outcomes

Upon completion, the application provides the following capabilities:

| Component | Implementation | Verification Evidence |
| --- | --- | --- |
| Spring Cloud Commons | Inject DiscoveryClient, read services and instances | GET /api/platform/discovery |
| SimpleDiscoveryClient | Read instances from static configuration | catalog-provider appears in response |
| Features endpoint | Declare and observe application features | GET /actuator/features |
| Spring Cloud Context | Use @RefreshScope for the configuration-reading service | Greeting changes after refresh |
| @ConfigurationProperties | Bind configuration with Duration type | GET /actuator/configprops |
| Spring Boot Actuator | Inspect health and configuration | GET /actuator/health |
| Integration testing | Verify APIs, discovery, and refresh | mvn test |

Main flow:

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["GreetingController"]
    B --> C["GreetingService"]
    C --> D["RefreshScope proxy"]
    D --> E["CatalogProperties"]
    E --> F["Environment"]

    G["DiscoveryController"] --> H["DiscoveryClient"]
    H --> I["SimpleDiscoveryClient"]
    I --> J["Static instance properties"]

    K["Actuator"] --> L["health / features / configprops"]
    K --> M["refresh"]
    M --> D
    M --> E
~~~

## 2. Project Setup and Version Management

Create a Maven project with the following structure:

~~~text
platform-core-lab/
├── pom.xml
├── config/
│   └── lab-overrides.yml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/platform/
    │   │       ├── PlatformCoreLabApplication.java
    │   │       ├── config/
    │   │       │   ├── CatalogProperties.java
    │   │       │   └── FeatureConfiguration.java
    │   │       ├── service/
    │   │       │   └── GreetingService.java
    │   │       └── web/
    │   │           ├── GreetingController.java
    │   │           └── DiscoveryController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-lab.yml
    └── test/
        └── java/
            └── com/example/platform/
                └── PlatformCoreLabApplicationTest.java
~~~

### 2.1. POM with Spring Cloud BOM

Create the pom.xml file:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>platform-core-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>platform-core-lab</name>
    <description>Spring Cloud Commons, Context and Actuator lab</description>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.1.4</spring-cloud.version>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-commons</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-context</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The dependencies are selected by role:

- `spring-cloud-commons`: DiscoveryClient, ServiceInstance, HasFeatures, SimpleDiscoveryClient, and the Features Actuator endpoint.
- `spring-cloud-context`: @RefreshScope, RefreshScope, and Environment update/rebind mechanisms.
- `spring-boot-starter-actuator`: Health, Environment, Configuration Properties, and Spring Boot administrative endpoints.
- `spring-boot-starter-webmvc`: REST controllers running on Spring MVC.
- `spring-boot-starter-webmvc-test`: MVC testing utilities in Spring Boot 4.

The Spring Cloud BOM manages the versions of Cloud modules within the same release train. Do not declare separate versions for spring-cloud-commons or spring-cloud-context when the BOM already manages them.

If an existing project is using Spring Boot 3.5.x, select the corresponding Spring Cloud 2025.0.x release and use the web/test starters supported by that Boot version. Do not mix dependencies from the Boot 4 example into a Boot 3 project without adjusting them.

## 3. Creating the Spring Boot Application

Create the file src/main/java/com/example/platform/PlatformCoreLabApplication.java:

~~~java
package com.example.platform;

import com.example.platform.config.CatalogProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(CatalogProperties.class)
public class PlatformCoreLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(PlatformCoreLabApplication.class, args);
    }
}
~~~

`@SpringBootApplication` enables component scanning and auto-configuration. `@EnableConfigurationProperties` registers the `CatalogProperties` bean so Spring Boot binds values with the `catalog` prefix.

In this exercise, `@EnableDiscoveryClient` is not required to create a specific registry. When no registry-based discovery implementation is on the classpath, Spring Cloud Commons can provide `SimpleDiscoveryClient` from static configuration. If Eureka or Consul is added later, that provider will supply its corresponding implementation.

## 4. Declaring Typed Configuration with ConfigurationProperties

Create the file src/main/java/com/example/platform/config/CatalogProperties.java:

~~~java
package com.example.platform.config;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties {

    private String greeting;
    private Duration timeout = Duration.ofSeconds(2);

    public String getGreeting() {
        return greeting;
    }

    public void setGreeting(String greeting) {
        this.greeting = greeting;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

This class uses JavaBean binding with getters and setters. `Duration` lets the application represent the timeout as a time type rather than keeping a free-form string. This mutable binding style is suitable for demonstrating the rebind process of Spring Cloud Context.

Do not use constructor binding or a Java Record for a bean that needs to be refreshed in this exercise. Objects using constructor binding, including Java Records annotated with `@ConfigurationProperties`, are not refreshed through the standard rebind mechanism of Spring Cloud Context.

## 5. Creating a Service with RefreshScope

Create the file src/main/java/com/example/platform/service/GreetingService.java:

~~~java
package com.example.platform.service;

import java.time.Duration;

import com.example.platform.config.CatalogProperties;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Service;

@Service
@RefreshScope
public class GreetingService {

    private final String greeting;
    private final Duration timeout;

    public GreetingService(CatalogProperties properties) {
        this.greeting = properties.getGreeting();
        this.timeout = properties.getTimeout();
    }

    public GreetingResponse currentGreeting() {
        return new GreetingResponse(greeting, timeout.toString());
    }

    public record GreetingResponse(String message, String timeout) {
    }
}
~~~

`@RefreshScope` creates a proxy for the bean. On refresh, Spring Cloud clears the cached target bean; the next call initializes a new target. `CatalogProperties` is rebound against the Environment before the new service target is used.

In this example, the service captures the greeting and timeout into fields when the constructor runs. Therefore, rebinding `CatalogProperties` alone does not change the snapshot held by the cached target. After the refresh scope is cleared, the next call creates a new target and reads the updated values. This approach makes the effect of `@RefreshScope` clearly visible in the lab.

Here, only `GreetingService` is placed in refresh scope. You should not mark every bean in an application as refreshable. Choose only beans whose configuration changes at runtime and whose lifecycle can be safely reinitialized.

## 6. Creating a REST API to Read Configuration

Create the file src/main/java/com/example/platform/web/GreetingController.java:

~~~java
package com.example.platform.web;

import com.example.platform.service.GreetingService;
import com.example.platform.service.GreetingService.GreetingResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public GreetingResponse greeting() {
        return greetingService.currentGreeting();
    }
}
~~~

The controller does not read the Environment directly. It invokes the service through the `RefreshScope` proxy, allowing configuration changes and target bean recreation to be managed at the service layer.

## 7. Using DiscoveryClient to Inspect Instances

Create the file src/main/java/com/example/platform/web/DiscoveryController.java:

~~~java
package com.example.platform.web;

import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/platform")
public class DiscoveryController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/discovery")
    public Map<String, List<String>> discoverySnapshot() {
        Map<String, List<String>> result = new TreeMap<>();

        for (String serviceId : discoveryClient.getServices()) {
            List<String> instances = discoveryClient.getInstances(serviceId)
                    .stream()
                    .map(ServiceInstance::getUri)
                    .map(Object::toString)
                    .toList();

            result.put(serviceId, instances);
        }

        return result;
    }
}
~~~

The controller depends on the `DiscoveryClient` interface rather than directly on Eureka or Consul. It retrieves service IDs, then reads the corresponding list of `ServiceInstance` objects and returns their URIs.

`DiscoveryClient` is an abstraction for querying discovery. It does not perform load balancing or send requests to the URIs on its own. To select an instance for an HTTP request, you need to add Spring Cloud LoadBalancer or another routing mechanism.

## 8. Declaring Features for the Features Endpoint

Create the file src/main/java/com/example/platform/config/FeatureConfiguration.java:

~~~java
package com.example.platform.config;

import com.example.platform.service.GreetingService;
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    HasFeatures discoveryFeature() {
        return HasFeatures.abstractFeatures(DiscoveryClient.class);
    }

    @Bean
    HasFeatures catalogGreetingFeature() {
        return HasFeatures.namedFeatures(
                new NamedFeature("Catalog greeting", GreetingService.class));
    }
}
~~~

Spring Cloud Commons provides the Features endpoint. An abstract feature uses an interface or abstract class to identify the implementing bean, such as `DiscoveryClient`. A named feature uses a name and a class representing an application capability.

`HasFeatures` declarations should be placed inside conditional configurations that match the actual features. Do not declare a feature as enabled if its implementation has not been created or activated.

## 9. Configuring application.yml

Create the file src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: platform-core-lab
  cloud:
    features:
      enabled: true
    discovery:
      client:
        simple:
          instances:
            catalog-provider:
              - uri: http://localhost:8091
                metadata:
                  environment: local

catalog:
  greeting: "Hello from default configuration"
  timeout: 2s

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

The `spring.cloud.discovery.client.simple.instances` configuration creates a `catalog-provider` service ID with one instance. This is a static list supplied by the application.

The same property can be expressed in an application.properties file as follows:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-provider[0].uri=http://localhost:8091
~~~

You do not need to start a service on port 8091 to test `DiscoveryClient.getServices()` and `getInstances()`. `SimpleDiscoveryClient` only returns the configured metadata. If you want to test real connectivity, create the provider service or switch to a registry-backed discovery implementation.

### 9.1. Creating the lab Profile to Test Refresh

Do not enable Environment write operations in the default configuration. Create a separate file src/main/resources/application-lab.yml:

~~~yaml
server:
  address: 127.0.0.1

spring:
  config:
    import: file:./config/lab-overrides.yml

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - configprops
          - refresh
~~~

The `lab` profile binds the web server only to loopback and imports an additional configuration file outside the classpath. Create the `config/lab-overrides.yml` file at the project root:

~~~yaml
catalog:
  greeting: "Hello from lab-overrides file"
~~~

When running with the lab profile, the value in this file overrides the default greeting. While the application is running, you can edit this file and then call `/actuator/refresh`; the Config Data refresher reloads the configuration sources and refreshes beans in refresh scope.

Relative file paths are resolved from the working directory. When running the JAR from a different directory, provide an appropriate path or configure an explicit location. This configuration is intended for local lab exercises. Do not use this profile on shared networks or in production; protect the refresh endpoint with authentication/authorization and restrict the management network.

## 10. Running the Application

Check Java and Maven:

~~~bash
java -version
mvn -version
~~~

Run tests and build:

~~~bash
mvn clean test
mvn package
~~~

Start with the lab profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=lab
~~~

If the application starts successfully, the server listens on `127.0.0.1:8080`. Inspect the startup logs to confirm that Spring Boot creates the web context, Spring Cloud Context, and discovery client.

You can view the resolved Spring Cloud dependencies:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
~~~

This command verifies that Commons and Context are included on the runtime classpath and helps detect unexpected transitive versions.

## 11. Verifying Application APIs

### 11.1. Reading the Greeting

Send a request:

~~~bash
curl http://127.0.0.1:8080/api/catalog/greeting
~~~

Expected output:

~~~json
{
  "message": "Hello from default configuration",
  "timeout": "PT2S"
}
~~~

`PT2S` is the ISO-8601 representation of `Duration.ofSeconds(2)`.

### 11.2. Reading the Discovery List

~~~bash
curl http://127.0.0.1:8080/api/platform/discovery
~~~

Expected output:

~~~json
{
  "catalog-provider": [
    "http://localhost:8091"
  ]
}
~~~

This output comes from `SimpleDiscoveryClient`, not from a registration in Eureka/Consul, and it does not prove that a service on port 8091 is running.

### 11.3. Checking Actuator

Health:

~~~bash
curl http://127.0.0.1:8080/actuator/health
~~~

Features:

~~~bash
curl http://127.0.0.1:8080/actuator/features
~~~

Configuration properties:

~~~bash
curl http://127.0.0.1:8080/actuator/configprops
~~~

`features` shows declared features and detected implementations. `configprops` shows `@ConfigurationProperties` beans and their binding status. Sensitive values are sanitized by Actuator by default; in the lab configuration, `show-values` is also explicitly set to `never`.

## 12. Modifying Config Data and Refreshing Beans

In the lab profile, the greeting is imported from `config/lab-overrides.yml`. Open the file while the application is running and change its content to:

~~~yaml
catalog:
  greeting: "Hello after refresh"
~~~

Save the file and then trigger Spring Cloud Context to reload the Environment and refresh scoped beans:

~~~bash
curl -X POST http://127.0.0.1:8080/actuator/refresh
~~~

Query the API again:

~~~bash
curl http://127.0.0.1:8080/api/catalog/greeting
~~~

Expected output:

~~~json
{
  "message": "Hello after refresh",
  "timeout": "PT2S"
}
~~~

The greeting changed because the Config Data refresher reread the imported file, `CatalogProperties` received the new value, and the `GreetingService` target was recreated via refresh scope. The refresh endpoint is not a file watcher; changes are only picked up when you invoke refresh or when the application receives an appropriate refresh event. With Config Server or other configuration sources, you need to configure the corresponding integration and event-publishing workflow.

## 13. Integration Testing with MockMvc

Create the file src/test/java/com/example/platform/PlatformCoreLabApplicationTest.java:

~~~java
package com.example.platform;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,features,configprops,refresh",
        "spring.cloud.refresh.additional-property-sources-to-retain=testOverride"
})
@AutoConfigureMockMvc
class PlatformCoreLabApplicationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ConfigurableEnvironment environment;

    @Test
    void returnsGreetingFromConfiguration() throws Exception {
        mockMvc.perform(get("/api/catalog/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello from default configuration"))
                .andExpect(jsonPath("$.timeout").value("PT2S"));
    }

    @Test
    void exposesConfiguredDiscoveryInstances() throws Exception {
        mockMvc.perform(get("/api/platform/discovery"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("catalog-provider")))
                .andExpect(content().string(containsString("http://localhost:8091")));
    }

    @Test
    void exposesSpringCloudFeatures() throws Exception {
        mockMvc.perform(get("/actuator/features"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").isArray())
                .andExpect(jsonPath("$.disabled").isArray());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void refreshesScopedServiceFromRetainedPropertySource() throws Exception {
        environment.getPropertySources().addFirst(new MapPropertySource(
                "testOverride",
                Map.of("catalog.greeting", "Hello after refresh")));

        mockMvc.perform(get("/api/catalog/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello from default configuration"));

        mockMvc.perform(post("/actuator/refresh"))
                .andExpect(status().is2xxSuccessful());

        mockMvc.perform(get("/api/catalog/greeting"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello after refresh"));
    }
}
~~~

The tests verify four behaviors: initial configuration binding, static discovery, the Features endpoint, and bean updates via refresh. `@DirtiesContext` instructs Spring Test to discard the context after the refresh test so Environment modifications do not affect other tests.

The refresh test adds a property source named `testOverride` to the Environment. The `spring.cloud.refresh.additional-property-sources-to-retain` property instructs `ContextRefresher` to retain this source when rebuilding the Config Data Environment; this allows the test to simulate a runtime configuration source and verify the refresh endpoint.

Run:

~~~bash
mvn test
~~~

If the refresh test receives a 404, verify that `management.endpoints.web.exposure.include` contains `refresh` and that the `spring-cloud-context` dependency is on the classpath. If it receives a 403, check the security/CSRF settings in the test configuration. If the greeting does not change, confirm that the `testOverride` property source name matches the value of `spring.cloud.refresh.additional-property-sources-to-retain` and that the service is injected through the `@RefreshScope` proxy.

## 14. Observing Module Lifecycles and Roles

| Module | Components in Project | Role |
| --- | --- | --- |
| Spring Cloud Commons | DiscoveryClient, ServiceInstance, HasFeatures, SimpleDiscoveryClient | Common API for querying discovery and publishing features |
| Spring Cloud Context | @RefreshScope, RefreshScope | Managing refreshable target beans |
| Spring Boot Configuration | @ConfigurationProperties, Environment | Binding and managing configuration values |
| Spring Boot Actuator | health, features, configprops, refresh | Observability and administrative operations |
| Spring MVC | REST controllers | Providing test APIs |

When a request calls `/api/catalog/greeting`, the controller calls the `GreetingService` proxy. The proxy retrieves the current target from refresh scope. The target reads `CatalogProperties`, which receives values bound from the Environment.

When a refresh is performed, Context refreshes beans in the corresponding scope. The next call through the proxy creates a new target. Other singleton beans are not automatically recreated just because one bean has `@RefreshScope`.

## 15. Extending to a Real Registry

The exercise uses `SimpleDiscoveryClient` to avoid external infrastructure requirements. When dynamic discovery is needed, a provider such as Eureka or Consul can be added.

For example, when choosing Eureka Client:

- Add the `spring-cloud-starter-netflix-eureka-client` dependency with the version managed by the Spring Cloud BOM.
- Configure the Eureka Server URL.
- Remove the `spring.cloud.discovery.client.simple.instances` configuration if static discovery is no longer used.
- Keep the controller dependent on `DiscoveryClient`; there is no need to rewrite instance lookup logic against a provider-specific API.

Example client configuration:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
~~~

This is an extension and not part of the minimal project. Eureka Server must be running and the client must register and send heartbeats successfully before the instance list reflects dynamic state.

If client-side load balancing is needed, add Spring Cloud LoadBalancer and write a separate test for instance selection. `DiscoveryClient` only returns the instance list; it does not distribute requests on its own.

## 16. Securing Actuator Outside Localhost

In the lab profile, the server is bound to `127.0.0.1` and exposes only the refresh endpoint and the read endpoints required for the exercise. Do not use this configuration as a production default.

In real deployments:

- Expose only `health` and endpoints required for operations.
- Keep `configprops` in sanitization mode; expose `env` only when there is a clear diagnostic need.
- Do not enable Environment write operations via Actuator without a controlled configuration change process.
- Protect `POST /actuator/refresh` with authentication and authorization.
- Place management endpoints on a restricted network or port.
- Record audit logs for Environment changes and refresh operations.
- Do not include credentials in responses, logs, or feature metadata.

By default, Spring Boot exposes only `health` over HTTP. Having an endpoint on the classpath does not mean that endpoint is automatically opened externally.

## 17. Completion Criteria

The project is considered complete when:

- [ ] `mvn clean test` passes.
- [ ] The application starts with compatible Spring Boot and Spring Cloud BOM versions.
- [ ] `GET /api/catalog/greeting` returns the greeting and timeout.
- [ ] `GET /api/platform/discovery` displays `catalog-provider`.
- [ ] `GET /actuator/features` returns the enabled/disabled lists.
- [ ] `GET /actuator/health` returns UP status.
- [ ] `GET /actuator/configprops` displays configuration beans with sanitized values.
- [ ] The lab profile imports `config/lab-overrides.yml` from outside the classpath.
- [ ] After editing the file and sending POST refresh, the greeting returns the new value.
- [ ] No configuration-writing endpoints are exposed on public network addresses.

## 18. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot inject DiscoveryClient | Missing Commons implementation or auto-configuration excluded | Check spring-cloud-commons and SimpleDiscoveryClient conditions |
| Discovery returns an empty list | Wrong prefix or index in service ID/instance configuration | Check spring.cloud.discovery.client.simple.instances |
| Features endpoint returns 404 | features not exposed or feature endpoint disabled | Check exposure and spring.cloud.features.enabled |
| Refresh endpoint returns 404 | Missing Spring Cloud Context or refresh not exposed | Check spring-cloud-context dependency and management exposure |
| Greeting does not change after refresh | Imported file not reloaded or bean not accessed via refresh proxy | Check `spring.config.import`, file path, `@RefreshScope`, and refresh logs |
| Configprops hides secrets | Actuator is sanitizing values | This is the default protective behavior |
| Compatibility verifier error | Boot and Cloud release trains are incompatible | Select BOM from the official compatibility matrix |
| Discovery URI exists but cannot be called | SimpleDiscoveryClient only holds static metadata | Start the provider service or use a real registry |
| Refresh test affects other tests | Context is reused after modifying Environment | Use @DirtiesContext or isolate the test context |

## 19. Extension Exercises

After completing the minimal project, you can extend it step by step:

1. Add Eureka or Consul and replace SimpleDiscoveryClient with a real provider.
2. Add Spring Cloud LoadBalancer to select an instance from the discovery list.
3. Add a custom health indicator for a business-required dependency.
4. Move the greeting to Config Server and verify refresh when the remote property changes.
5. Write a test to confirm that singleton beans are not recreated when refreshing another bean.
6. Add Spring Security for management endpoints and test the role allowed to POST refresh.
7. Measure how many times the GreetingService target is instantiated before/after refresh using logs or a test counter.
8. Try different profiles and confirm that @ConfigurationProperties binds the right values.

Each extension should have its own tests. Do not add a registry, broker, or LoadBalancer to the initial project if the goal is solely to understand Commons, Context, and Actuator.

## 20. Conclusion

This application brings together three core pillars of **SPRING_CLOUD_CORE** in a small project: Commons provides `DiscoveryClient` and the Features endpoint; Context provides `@RefreshScope` for refreshing beans; Spring Boot Actuator provides health, configprops, and administrative endpoints. `SimpleDiscoveryClient` makes it possible to test discovery without standing up a registry, while the lab profile imports an external configuration file outside the classpath to observe Config Data refresh locally.

When moving to production, replace static discovery with a real provider if dynamic registration is needed, add LoadBalancer if instance selection is required, and secure all administrative endpoints. Keep the BOM compatible, test refresh behavior, and expose only the endpoints that are genuinely needed.

## References

- [Spring Cloud Release Trains — Compatibility Matrix](https://spring.io/projects/spring-cloud)
- [Spring Cloud Commons — Common Abstractions and Features Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Context — Refresh Scope and Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Boot — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Actuator Endpoints and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
