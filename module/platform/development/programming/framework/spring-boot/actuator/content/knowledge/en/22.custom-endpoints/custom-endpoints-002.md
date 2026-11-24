# Defining an Endpoint with @Endpoint and Bean Registration

## 1. What Is a Custom Endpoint Used For?

Suppose an application has a product catalog cache. In operations, we want to know how many entries the cache currently holds without returning all product data.

A small management endpoint can return:

```json
{"name":"catalog","entries":2}
```

This is information about the application's internal state, suitable for illustrating a **custom Actuator endpoint**. APIs for customers to search or purchase products still have their own business contracts.

`@Endpoint` marks a type as an Actuator endpoint. Operation methods such as `@ReadOperation` are processed by technology adapters so they can be exposed over HTTP, JMX, or another supported technology. [Spring Boot 3.3: Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html)

Three things must be kept distinct from the outset:

1. **Endpoint definition:** a class annotated with `@Endpoint`, having an ID and operation methods.
2. **Bean registration:** Spring must manage an instance of that class.
3. **Access exposure:** configuration allows a technology such as HTTP to reach the endpoint.

An annotated class that has not become a bean is not equivalent to an active URL.

## 2. What Is Each Annotation Responsible For?

| Component | Responsibility in the Example |
| --- | --- |
| `@Endpoint(id = "catalogcache")` | Identifies the Actuator endpoint with ID `catalogcache` |
| `@ReadOperation` | Marks a read operation recognized by Actuator |
| `@Bean` | Registers the object returned from the method with Spring |
| `@Configuration` | Contains configuration that creates the example's beans |
| `@Component` | An alternative registration via component scanning, instead of the corresponding `@Bean` method |
| `management.endpoints.web.exposure.include` | Selects which IDs are exposed over HTTP |

`@Endpoint` is not itself a `@Component`. Placing a class in a scanned package and only adding `@Endpoint` is not how bean registration works. This lesson uses `@Bean` to make it clear where the instance is created and where dependencies are provided.

Spring allows `@Bean` methods to receive dependencies as parameters; the container supplies the matching bean. [Spring Framework: Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)

### 2.1. Do Not Confuse Bean Name, Endpoint ID, and Operation Method Name

In the complete example:

| Name | Value | Role |
| --- | --- | --- |
| Java type | `CatalogCacheEndpoint` | Implementation class |
| Bean name | `catalogCacheEndpoint` | Default bean name from the `@Bean` method |
| Endpoint ID | `catalogcache` | Actuator identifier |
| Operation method | `read()` | Code that reads information |
| Default URL in the example | `/actuator/catalogcache` | HTTP path from base path and ID |

Renaming `read()` to `snapshot()` does not automatically turn the URL into `/actuator/snapshot`. Similarly, giving the bean a different name is not how you change the endpoint ID.

An ID should be short, stable, and alphanumeric; per the `EndpointId` contract, it starts with a lowercase letter. `catalogcache` satisfies that rule. Do not set an ID to a path such as `/catalog/cache`. [Spring Boot 3.3: EndpointId](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/EndpointId.html)

## 3. Complete Runnable Example with Spring Boot 3.3 and Java 21

The following example is a standalone Maven project using Java 21. It has immutable sample data with two entries, one read-only endpoint, and two integration tests.

The value `entries=2` is computed from the size of the sample cache's Map. The endpoint does not simulate a number pulled from a production system.

### 3.1. File Structure

```text
actuator-endpoint-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/actuator/
    │   │   ├── ActuatorEndpointDemoApplication.java
    │   │   ├── CatalogCache.java
    │   │   ├── CatalogCacheEndpoint.java
    │   │   └── EndpointConfiguration.java
    │   └── resources/application.properties
    └── test/
        └── java/example/actuator/CatalogCacheEndpointTest.java
```

The startup class and configuration class reside together in `example.actuator`. `@SpringBootApplication` includes component scanning to detect configurations within its scope. [Spring Boot 3.3: SpringBootApplication](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html)

### 3.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>actuator-endpoint-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

The three dependencies serve three purposes:

- `spring-boot-starter-web`: HTTP application using Spring MVC.
- `spring-boot-starter-actuator`: infrastructure for discovering and exposing Actuator endpoints.
- `spring-boot-starter-test`: integration testing, used only in the test scope.

Boot's parent manages the versions of related libraries. There is no need to pin a separate version specifically for Actuator in this example.

### 3.3. Startup Class

Contents of `ActuatorEndpointDemoApplication.java`:

```java
package example.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorEndpointDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorEndpointDemoApplication.class, args);
    }
}
```

### 3.4. Object Holding Observable State

Contents of `CatalogCache.java`:

```java
package example.actuator;

import java.util.Map;

public final class CatalogCache {
    private final Map<String, String> entries;

    public CatalogCache(Map<String, String> entries) {
        this.entries = Map.copyOf(entries);
    }

    public int entryCount() {
        return entries.size();
    }
}
```

`Map.copyOf(...)` holds an unmodifiable Map through this object. `entryCount()` returns the number of entries in the sample data, while the endpoint does not need to know the specific product codes.

In a real application, you can replace the sample object with a service that summarizes live operational state. Keep data collection in an appropriate service; the endpoint class only turns the information to be exposed into a clear result.

### 3.5. Endpoint Class

Contents of `CatalogCacheEndpoint.java`:

```java
package example.actuator;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;

@Endpoint(id = "catalogcache")
public final class CatalogCacheEndpoint {
    private final CatalogCache cache;

    public CatalogCacheEndpoint(CatalogCache cache) {
        this.cache = cache;
    }

    @ReadOperation
    public CacheSnapshot read() {
        return new CacheSnapshot("catalog", cache.entryCount());
    }

    public record CacheSnapshot(String name, int entries) {
    }
}
```

Details to read carefully:

- `@Endpoint` is imported from `org.springframework.boot.actuate.endpoint.annotation`.
- `@ReadOperation` marks the read method, not `@GetMapping`.
- The constructor accepts `CatalogCache`; it does not create another cache on its own.
- `CacheSnapshot` is a record containing exactly the exposed data.
- The class does not carry `@Component`; bean registration is done in the following configuration.

For HTTP exposure, the read operation is mapped to GET. The returned record is converted into a JSON response body in the example's web configuration. [Spring Boot 3.3: Endpoint operations and HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints)

You do not need to add `@RestController` or `@RequestMapping` to this class to create the Actuator URL.

### 3.6. Registering Beans and Supplying Dependencies

Contents of `EndpointConfiguration.java`:

```java
package example.actuator;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class EndpointConfiguration {
    @Bean
    public CatalogCache catalogCache() {
        return new CatalogCache(Map.of(
                "A100", "Notebook",
                "B200", "Pencil"));
    }

    @Bean
    public CatalogCacheEndpoint catalogCacheEndpoint(CatalogCache cache) {
        return new CatalogCacheEndpoint(cache);
    }
}
```

Spring performs two steps:

1. Invokes the `catalogCache()` method to register the sample data bean.
2. Supplies that bean to the `cache` parameter of `catalogCacheEndpoint(...)`, then manages the returned endpoint.

Calling `new CatalogCacheEndpoint(cache)` here accomplishes registration because **the result of the `@Bean` method** is received by the container. A similar `new` call in arbitrary code, not returned through a registration mechanism, only creates an ordinary Java object.

The configuration uses `proxyBeanMethods = false` and receives dependencies via parameters. You do not need to call `catalogCache()` directly inside the other method to obtain the dependency.

You should declare the specific return type `CatalogCacheEndpoint` so the bean type is clearly visible to the discovery mechanism. There is no educational benefit to changing it to `Object` and hiding the type information.

### 3.7. Allowing the Endpoint to Appear Over HTTP

Contents of `application.properties`:

```properties
spring.application.name=actuator-endpoint-demo
server.address=127.0.0.1
server.port=8080

management.endpoint.catalogcache.enabled=true
management.endpoints.web.exposure.include=health,catalogcache
```

Here:

- The application listens on loopback `127.0.0.1` for local testing.
- The `enabled=true` property specifies that the `catalogcache` endpoint is enabled.
- The HTTP exposure list includes `catalogcache`.
- The base path remains the default `/actuator`.

Being enabled and being exposed are two separate conditions. Under Boot 3.3's default configuration, only `health` is exposed over HTTP; therefore, you cannot omit the exposure list and expect every new endpoint to automatically have an accessible URL. [Spring Boot 3.3: Exposing endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

The list in the example contains `health` and `catalogcache`; you do not need to expose all endpoints to verify one new endpoint.

## 4. From Bean to HTTP Response: What Happened?

```text
EndpointConfiguration is discovered by Spring
    --> creates CatalogCache bean
    --> creates CatalogCacheEndpoint bean
    --> Actuator detects @Endpoint and @ReadOperation
    --> checks endpoint enablement and HTTP exposure
    --> creates GET /actuator/catalogcache mapping
    --> invokes read()
    --> returns CacheSnapshot as JSON
```

The `read()` method does not need to accept an HTTP request or serialize JSON itself. It expresses the management operation; the HTTP adapter handles invoking it and converting the result.

This also explains why an endpoint class should keep its operation contract simple. Adding input parameters, write/delete operations, or a web-specific endpoint type are separate extension steps; you do not need to include them just to register a read-only endpoint.

### 4.1. Three Checkpoints to Verify Independently

| Checkpoint | Question | Evidence in the Example |
| --- | --- | --- |
| Bean | Is there exactly one endpoint instance managed by Spring? | `getBeansOfType(CatalogCacheEndpoint.class)` has one element |
| Discovery | Does Actuator web recognize the ID? | `WebEndpointsSupplier` contains `catalogcache` |
| HTTP | Does a request to the right path invoke the operation? | GET returns 200 and the expected sample data |

A successful direct call to `new CatalogCacheEndpoint(...).read()` only tests the Java method. It does not prove that Spring registered the bean, Actuator discovered it, or HTTP mapped it.

Similarly, seeing a bean in the container is not enough to conclude that HTTP requests are allowed to access it. If the application has Spring Security, access rules are also applied separately; exposure configuration does not grant permissions to callers.

## 5. Compiling, Testing, and Running

You need JDK 21, Maven, and network access to download dependencies on the first run. Run the following commands in the directory containing `pom.xml`.

### 5.1. Testing and Packaging

After adding the test class in section 6:

```shell
mvn verify
```

This command compiles main code, runs tests, and packages the application. The Spring Boot Maven plugin produces an executable JAR:

```text
target/actuator-endpoint-demo-1.0.0.jar
```

The project uses Spring libraries and an embedded web server, so Maven prepares the classpath and packages the app instead of invoking `javac` on a single file.

### 5.2. Starting the JAR

```shell
java -jar target/actuator-endpoint-demo-1.0.0.jar
```

If port 8080 is already in use, you can choose another port:

```shell
java -jar target/actuator-endpoint-demo-1.0.0.jar --server.port=18080
```

When changing the port, use the same port in the subsequent HTTP command. Startup logs contain timestamps, PID, and environment details that vary per run; do not treat the entire log as fixed stdout.

### 5.3. Calling the Endpoint

In another terminal:

```shell
curl --silent --show-error --fail -H "Accept: application/json" http://127.0.0.1:8080/actuator/catalogcache
```

On Windows PowerShell, use `curl.exe` if `curl` is an alias for another PowerShell command.

Response body:

```json
{"name":"catalog","entries":2}
```

This is the result from the two sample data entries in `EndpointConfiguration`. JSON member order and whitespace are not part of the contract to compare; the values of `name`, `entries`, and the HTTP status code are the focus of verification.

Stop the application process with Ctrl+C when finished testing.

## 6. Testing Bean, Discovery, and Path

Contents of `CatalogCacheEndpointTest.java`:

```java
package example.actuator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.endpoint.web.WebEndpointsSupplier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CatalogCacheEndpointTest {
    @Autowired
    private ApplicationContext context;

    @Autowired
    private WebEndpointsSupplier webEndpoints;

    @Autowired
    private MockMvc http;

    @Test
    void registeredEndpointIsDiscoveredAndServesItsSnapshot() throws Exception {
        assertThat(context.getBeansOfType(CatalogCacheEndpoint.class))
                .hasSize(1);
        assertThat(context.getBean("catalogCacheEndpoint"))
                .isInstanceOf(CatalogCacheEndpoint.class);
        assertThat(webEndpoints.getEndpoints())
                .extracting(endpoint -> endpoint.getEndpointId().toString())
                .contains("catalogcache");

        http.perform(get("/actuator/catalogcache")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("catalog"))
                .andExpect(jsonPath("$.entries").value(2));
    }

    @Test
    void endpointIdIsNotAnOrdinaryControllerRoute() throws Exception {
        http.perform(get("/catalogcache"))
                .andExpect(status().isNotFound());
    }
}
```

The test loads the Spring context and uses MockMvc to go through Spring MVC's request-handling infrastructure without opening a server or network port. Thus it tests mapping and responses at the MVC layer, without verifying TCP connectivity or running the standalone JAR. [Spring Framework: MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)

The two tests verify two things:

- The bean with the expected name and type is registered, discovered by Actuator, and serves data over the management path.
- The ID `catalogcache` does not automatically create an ordinary controller route `/catalogcache` in the sample application.

The second test makes sense in the sample project that declares no corresponding controller. In another application, if there is a custom controller mapped to `/catalogcache`, the result for that path must be evaluated according to that controller.

The JSON assertions help avoid marking a test as “passing” just because the endpoint returns 200 with wrong data. Checking the bean and discovery helps isolate the cause if the HTTP step fails.

## 7. Alternative Registration Approach: @Component

If you want component scanning to register the endpoint automatically, you can add `@Component` to the endpoint class. When choosing this approach, **remove the corresponding `@Bean` method that creates the endpoint**; keep the `CatalogCache` bean to provide the dependency.

The alternative endpoint class version will be:

```java
package example.actuator;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "catalogcache")
public final class CatalogCacheEndpoint {
    private final CatalogCache cache;

    public CatalogCacheEndpoint(CatalogCache cache) {
        this.cache = cache;
    }

    @ReadOperation
    public CacheSnapshot read() {
        return new CacheSnapshot("catalog", cache.entryCount());
    }

    public record CacheSnapshot(String name, int entries) {
    }
}
```

This is an alternative to the endpoint class and registration approach above. In `EndpointConfiguration`, keep only the method creating `CatalogCache`; remove the method creating `CatalogCacheEndpoint` so the endpoint is not registered twice.

Choose an approach based on your needs:

| Registration Approach | Appropriate When |
| --- | --- |
| `@Bean` in configuration | You want to clearly see how the endpoint is constructed, configure dependencies, or register a class that does not carry a stereotype itself |
| `@Component` on the class | The endpoint is owned by the application and lies within the component scan scope |

Do not use both approaches simultaneously to create two endpoint beans with the same ID. Renaming the bean does not create two independent Actuator identifiers either: the ID is still `catalogcache`.

If you add `@Component` while the class is outside the scanned scope, Spring may still fail to create the bean. Bring the configuration/class into the scan scope or import the appropriate configuration, rather than randomly changing the HTTP path.

## 8. Common Errors and How to Check

| Symptom | What to Check | How to Fix |
| --- | --- | --- |
| Has `@Endpoint` class but no bean | Missing `@Bean` or scanned stereotype | Register using one explicit mechanism |
| Has `@Bean` but endpoint not seen | Configuration class was not loaded | Check package, component scan, or import |
| Endpoint has no read operation | Method lacks `@ReadOperation` or wrong import | Use Actuator's annotation from the right package |
| `GET /actuator/catalogcache` returns 404 | Bean, operation, enabled, exposure, base path, and port | Check in order instead of just changing the URL |
| `GET /catalogcache` returns 404 | Using the ID as a controller URL | Call the example's Actuator path |
| Duplicate endpoint error at startup | Two beans share the same ID, often from keeping both `@Bean` and `@Component` | Keep only one registration for this endpoint |
| `CatalogCache` dependency error | No bean of the right type or multiple ambiguous candidates | Fix dependency provisioning before testing HTTP |
| HTTP 401 or 403 | Authentication/authorization rules are in effect | Check the appropriate security configuration |
| HTTP 200 but wrong entry count | Endpoint reads a different data object or counting logic is wrong | Check the injected bean and source data |

In a real application, the path can also be affected by management base path, context path, or a separate management port. The table above uses the sample project's defaults; do not infer that every application has the same full URL.

A custom endpoint should return the information necessary for observation. For example, expose only the name and entry count, and avoid returning the entire Map or service objects directly with data not intended for exposure.

## 9. Practice to Understand Registration Properly

Make each change individually, restart, and observe the result:

1. **Rename the operation method** from `read()` to `snapshot()`. Keep the ID and annotations. The Actuator path still relies on `catalogcache`.
2. **Change the bean name** using `@Bean("internalCatalogEndpoint")` on the endpoint creation method. Update the bean name assertion in the test, then verify the URL is unchanged.
3. **Remove only the endpoint's `@Bean`**, keeping the `@Endpoint` class without `@Component`. Verify the container no longer has the endpoint bean created by that configuration.
4. **Restore the bean but expose only `health` over HTTP**. Separately verify bean existence and that the endpoint is no longer in the exposed web set.
5. **Change the endpoint ID** to `catalogsummary`. Update the exposure list, the `enabled` property, and the path in the test; do not only rename the class.
6. **Choose the `@Component` approach** and remove the corresponding `@Bean` method. Verify the endpoint is registered exactly once.

Self-check questions:

- Does `@Endpoint` automatically replace `@Component`? **No.**
- Can a `@Bean` method receive dependent services via parameters? **Yes.**
- Does the bean name determine the Actuator path by default? **No; the management path is based on the endpoint ID and related web configuration.**
- Does calling the Java method directly prove the endpoint is accessible over HTTP? **No.**
- Can a bean be registered properly while the endpoint is still not exposed over HTTP? **Yes.**

You have completed the lesson when you can point out exactly where the endpoint is defined, where Spring creates the bean, and where HTTP is allowed to expose that endpoint.
