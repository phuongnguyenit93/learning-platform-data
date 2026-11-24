# Building an InfoContributor for Custom Application Information

## 1. Understanding the Role of InfoContributor

When operating an application, we often need to know: which service is this, which region is it running in, which release track does it belong to, and which capabilities does it support. This information helps compare deployments or explain differences between two environments.

`/actuator/info` is where descriptive application information is aggregated. An **`InfoContributor`** supplies one piece of data to that result. You write a contributor when you need to select, organize, or compute custom information that built-in build/Git data does not express.

For example, a course catalog service needs to expose:

```json
{
  "application": {
    "schemaVersion": 1,
    "service": "training-catalog",
    "region": "ap-southeast-1",
    "releaseTrack": "stable",
    "capabilities": ["catalog-search", "course-preview"]
  }
}
```

These fields form a **data contract chosen by the application**. `releaseTrack` is a configured deployment label and does not prove all pods run the same commit. `capabilities` describes intended supported capabilities and does not confirm dependent systems are operational.

Learning sequence in this lesson: understand the contributor–endpoint relationship → create the bean and data → expose the HTTP endpoint → verify results → handle ordering, errors, and dynamic data.

### Choosing the Right Tool for the Question

| Question | Appropriate tool |
| --- | --- |
| What identification and capabilities does this application have? | `InfoContributor` |
| Is the database currently ready? | `HealthIndicator` or corresponding health mechanism |
| What are the total request count, latency, or error rate? | Micrometer and metrics |
| Does the user want to search courses by criteria? | Business API |
| Need an administrative operation with custom inputs? | Consider a custom Actuator endpoint |

Do not put heavy-query business metrics, per-user data, or connectivity check results into `info` just because they can be represented as JSON.

## 2. Mechanism: Contributors Add Data, the Endpoint Aggregates

The interface has a single method:

```java
void contribute(Info.Builder builder);
```

The method receives a result builder and adds fields via `withDetail(key, value)` or `withDetails(map)`. It does not return an HTTP response directly and does not need `@RestController` or `@ReadOperation`. It is also a functional interface, so a bean can be declared using a lambda. [InfoContributor 3.3 Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoContributor.html).

Processing flow when the read operation actually executes:

```text
HTTP GET /actuator/info
  -> Actuator mappings and access control layers
  -> InfoEndpoint.info()
  -> create a new Info.Builder for this aggregation
  -> invoke contribute(builder) of each contributor
  -> builder.build().getDetails()
  -> serialize result to JSON
```

`InfoEndpoint` holds the list of contributors and iterates through them in order; the builder object is created inside the `info()` method. A contributor must not keep the builder in a field for reuse across requests. [InfoEndpoint source code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoEndpoint.java).

Three layers must be distinguished:

- **Bean:** the contributor must be managed by Spring and sit within component scan scope or be declared with `@Bean`.
- **Endpoint and exposure:** `info` must be enabled and exposed over HTTP if you want to call it by URL.
- **Data:** the contributor must actually add a field serializable to JSON.

A Java class implementing the interface without being registered as a bean will not automatically appear in the aggregation list. Conversely, having a bean does not mean the URL is already reachable.

## 3. Complete Example: Deployment Information of a Course Service

The example uses Java 21, Spring Boot 3.3.0, and Gradle 8.5, matching the Spring Boot 3.3.x knowledge branch. The code uses records and APIs available from Java 17 onward. This is a **standalone practice project**; the Gradle files below are not meant to replace the configuration of a multi-module repository.

### 3.1. Project Structure

```text
info-contributor-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/example/info/
│   ├── InfoDemoApplication.java
│   ├── ApplicationMetadata.java
│   └── ApplicationInfoContributor.java
├── src/main/resources/application.yml
└── src/test/java/example/info/
    ├── ApplicationInfoContributorTest.java
    ├── InfoEndpointIntegrationTest.java
    └── InfoEndpointDisabledIntegrationTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'info-contributor-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`starter-web` provides the HTTP server for the practice exercise; `starter-actuator` provides the endpoint infrastructure. The test suite uses JUnit Jupiter and MockMvc from `starter-test`. No extra library is required to implement `InfoContributor`.

### 3.2. Declaring the Application and Registering Configuration

File `src/main/java/example/info/InfoDemoApplication.java`:

```java
package example.info;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ApplicationMetadata.class)
public class InfoDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(InfoDemoApplication.class, args);
    }
}
```

File `src/main/java/example/info/ApplicationMetadata.java`:

```java
package example.info;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.metadata")
public record ApplicationMetadata(
        String service,
        String region,
        String releaseTrack) {

    public ApplicationMetadata {
        service = requireText(service, "app.metadata.service");
        region = requireText(region, "app.metadata.region");
        releaseTrack = requireText(releaseTrack, "app.metadata.release-track");
    }

    private static String requireText(String value, String property) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(property + " must not be blank");
        }
        return value;
    }
}
```

`@ConfigurationProperties` binds related properties into one data type. The YAML key `release-track` binds to the `releaseTrack` record component. The record has a single canonical constructor, so the example does not need `@ConstructorBinding`.

The constructor validates the three required values when binding configuration. Missing identification data is a configuration error and fails startup, rather than letting the first `/actuator/info` call blow up because `Map.of` rejects `null`.

This is the example's policy. For optional data, intentionally omit the field or use an agreed descriptive value; never fake a value that looks like real data. Also remember that an immutable record does not automatically make the whole object graph immutable if one of its components is a mutable collection.

### 3.3. Writing the Contributor

File `src/main/java/example/info/ApplicationInfoContributor.java`:

```java
package example.info;

import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "app.metadata",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ApplicationInfoContributor implements InfoContributor {

    private final Map<String, Object> details;

    public ApplicationInfoContributor(ApplicationMetadata metadata) {
        this.details = Map.of(
                "schemaVersion", 1,
                "service", metadata.service(),
                "region", metadata.region(),
                "releaseTrack", metadata.releaseTrack(),
                "capabilities", List.of("catalog-search", "course-preview"));
    }

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("application", this.details);
    }
}
```

Explanation of decisions:

1. `@Component` registers the bean inside the application's subpackage.
2. The constructor receives configuration via dependency injection and pre-builds slowly changing data.
3. `application` is the top-level key owned by this contributor; the bean name does not determine the JSON key.
4. `Map.of` and `List.of` along with string/number values ensure the example has no shared collection mutated during reads.
5. `contribute` only attaches data to the builder, without making network calls, writing to a database, or mutating business state.
6. `schemaVersion` helps consumer tools recognize the contract version if the structure later evolves.
7. `app.metadata.enabled` is a custom switch the application itself attaches to the bean creation condition.

If choosing `@Bean` registration instead of `@Component`, remove `@Component` and move the enable/disable condition onto the `@Bean` method if still needed. Do not register both ways for the same contributor, as that could cause it to run twice.

### 3.4. Configuring Data and Exposing the Endpoint

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: info-contributor-demo

app:
  metadata:
    enabled: true
    service: training-catalog
    region: ap-southeast-1
    release-track: stable

management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
  info:
    defaults:
      enabled: false
```

The server is restricted to loopback for this practice exercise. The example does not add Spring Security so there is no login step. When integrating into a secured application, requests must comply with the application's security filter chain; adding `info` to exposure does not grant access permission.

In the Boot 3.3 line, `info` must be included in HTTP exposure if you want to call it by URL. `management.endpoint.info.enabled` controls the endpoint; `management.endpoints.web.exposure.include` controls web exposure. These two differ from creating contributor beans. [Endpoint and exposure configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#enabling).

`management.info.defaults.enabled=false` keeps the practice output free of default contributors such as build/Git. It **does not automatically disable the custom bean** above. `management.info.<id>.enabled` conditions apply to contributors whose auto-configuration attaches the corresponding condition; the `application` name in JSON does not automatically create a `management.info.application.enabled` switch. [Contributor auto-configuration in Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.java).

Configuration still binds and validates `ApplicationMetadata` when the contributor is disabled, because `@EnableConfigurationProperties` registers the record independently. The switch in the example only decides information contribution, not disabling that configuration validation.

### 3.5. Running and Observing

From the project directory, with JDK 21 and Gradle 8.5 installed:

```shell
gradle wrapper --gradle-version 8.5
```

Once Gradle Wrapper is present, on PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

On Linux/macOS, use `./gradlew test` and `./gradlew bootRun`. Do not compile individual classes separately with `javac` without the classpath, as this is a Spring-dependent application requiring configuration and resources.

Open a second terminal:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/info
```

On Windows, use `curl.exe` if `curl` points to a PowerShell alias. The result has the structure:

```json
{
  "application": {
    "schemaVersion": 1,
    "service": "training-catalog",
    "region": "ap-southeast-1",
    "releaseTrack": "stable",
    "capabilities": ["catalog-search", "course-preview"]
  }
}
```

The JSON is reformatted for readability; key ordering and whitespace are not a contract. The element ordering of the `capabilities` list in the example is preserved by `List.of`. Do not test JSON strings using comparisons that depend on the key ordering of `Map.of`.

Try changing `release-track` to `canary`, restarting, and reading the endpoint again. The `releaseTrack` field changes with configuration. Editing the config file does not automatically recreate existing beans; the example does not configure a configuration refresh mechanism.

Stop the application and run with the contributor disabled:

```powershell
.\gradlew.bat bootRun --args="--app.metadata.enabled=false"
```

With the exact sample configuration and no other contributors added, the `/actuator/info` output is:

```json
{}
```

The HTTP endpoint still exists. What was excluded is the `ApplicationInfoContributor` bean, not all of `info`.

## 4. Testing from the Java Contract to HTTP

Seeing one successful curl call does not prove the contributor preserves the right data, avoids overwriting other sections, and is properly registered by Spring. We test at two distinct levels.

### 4.1. Unit Tests: Data and Key Boundaries

File `src/test/java/example/info/ApplicationInfoContributorTest.java`:

```java
package example.info;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.actuate.info.InfoEndpoint;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ApplicationInfoContributorTest {

    private final ApplicationMetadata metadata =
            new ApplicationMetadata(
                    "training-catalog", "ap-southeast-1", "stable");

    @Test
    void contributesOnlyTheExpectedApplicationContract() {
        var builder = new Info.Builder();
        new ApplicationInfoContributor(metadata).contribute(builder);

        Map<String, Object> expected = Map.of(
                "schemaVersion", 1,
                "service", "training-catalog",
                "region", "ap-southeast-1",
                "releaseTrack", "stable",
                "capabilities", List.of("catalog-search", "course-preview"));

        assertEquals(Map.of("application", expected),
                builder.build().getDetails());
    }

    @Test
    void preservesUnrelatedTopLevelInformation() {
        var builder = new Info.Builder();
        builder.withDetail("operations", Map.of("owner", "learning-team"));

        new ApplicationInfoContributor(metadata).contribute(builder);

        assertEquals(Map.of("owner", "learning-team"),
                builder.build().getDetails().get("operations"));
    }

    @Test
    void laterContributorReplacesTheWholeDuplicateTopLevelValue() {
        InfoContributor first = builder -> builder.withDetail(
                "application", Map.of("service", "first"));
        InfoContributor second = builder -> builder.withDetail(
                "application", Map.of("region", "second"));

        var endpoint = new InfoEndpoint(List.of(first, second));

        assertEquals(
                Map.of("application", Map.of("region", "second")),
                endpoint.info());
    }

    @Test
    void rejectsMissingRequiredMetadata() {
        var error = assertThrows(IllegalArgumentException.class,
                () -> new ApplicationMetadata(
                        "training-catalog", " ", "stable"));

        assertEquals("app.metadata.region must not be blank",
                error.getMessage());
    }
}
```

The first test verifies the entire contract, including not accidentally adding stray keys. The second protects another contributor's data. The third intentionally creates a key collision to observe the replacement rule; it does not depend on bean scan order because it passes an explicitly ordered list to the endpoint. The last test verifies the required-data policy.

### 4.2. Integration Tests: Beans, Configuration, and URLs

File `src/test/java/example/info/InfoEndpointIntegrationTest.java`:

```java
package example.info;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class InfoEndpointIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void exposesApplicationMetadataThroughActuator() throws Exception {
        mvc.perform(get("/actuator/info"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.application.schemaVersion").value(1))
                .andExpect(jsonPath("$.application.service")
                        .value("training-catalog"))
                .andExpect(jsonPath("$.application.region")
                        .value("ap-southeast-1"))
                .andExpect(jsonPath("$.application.releaseTrack")
                        .value("stable"))
                .andExpect(jsonPath("$.application.capabilities.length()")
                        .value(2))
                .andExpect(jsonPath("$.application.capabilities[0]")
                        .value("catalog-search"))
                .andExpect(jsonPath("$.application.capabilities[1]")
                        .value("course-preview"));
    }
}
```

File `src/test/java/example/info/InfoEndpointDisabledIntegrationTest.java`:

```java
package example.info;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "app.metadata.enabled=false")
@AutoConfigureMockMvc
class InfoEndpointDisabledIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void keepsTheEndpointAvailableWhenTheContributorIsDisabled()
            throws Exception {
        mvc.perform(get("/actuator/info"))
                .andExpect(status().isOk())
                .andExpect(content().json("{}", true));
    }
}
```

Run `.\gradlew.bat test` to execute these six tests. They do not print JSON results to stdout; the HTML report is at `build/reports/tests/test/index.html`. Build messages, timings, and startup logs vary by environment, so do not use them as fixed assertions.

MockMvc tests HTTP mappings within the Spring context without opening a real TCP socket. The curl commands earlier complement this by testing against a running server. If bringing this into an application with Spring Security, HTTP tests must include proper authentication/authorization rather than disabling security to force tests to pass.

## 5. Multiple Contributors: Key Ownership and Ordering

### 5.1. Each Data Region Has One Owner

Independent contributors can contribute together:

```json
{
  "application": {
    "service": "training-catalog"
  },
  "operations": {
    "owner": "learning-team"
  }
}
```

However, if two contributors both call `withDetail("application", ...)`, the value written later replaces **the entire value at that key**. Nested maps are not automatically merged field by field. The duplicate-key test above is executable proof of this behavior.

Similarly, `withDetails(map)` adds the map's entries at the top level; it does not automatically create a group named after the bean. To create an `application` group, pass a map as the value to `withDetail("application", map)`.

A maintainable design gives each contributor ownership of one top-level key. If multiple sources jointly build the `application` group, there should be one contributor aggregating from small data-provider objects and writing that group only once. Avoid claiming `build`, `git`, `java`, or `os` as keys for unrelated data while the corresponding contributors remain in use.

### 5.2. Ordering Can Be Controlled but Cannot Replace Good Design

Auto-configuration collects beans via `orderedStream()`. You can use `@Order` or `Ordered`; lower numbers take precedence. When declaring a bean with a `@Bean` method, you can put `@Order` on that method. Do not infer ordering from class names, file names, or component discovery order. [InfoEndpointAutoConfiguration source code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoEndpointAutoConfiguration.java).

A contributor can intentionally write later to override, yet this makes content dependent on ordering and bean configuration. Unless there is an explicit compatibility requirement, partitioning keys is easier to understand. Contributor execution order is also not a guarantee of JSON field display order for consumers.

## 6. Dynamic Information, Performance, and Errors

### 6.1. Separating Slowly Changing Data from Runtime-Updated Data

In the example, metadata is captured when the bean is created. That fits service name, deployment region, and release track, which do not change during a process's lifetime.

If you need to expose a runtime-updated business configuration snapshot, the contributor should read **a pre-prepared data snapshot**, such as an immutable record stored in an `AtomicReference`. A background task swaps the whole snapshot on successful update; the contributor simply reads once and produces JSON. This is a design example, not an extra file for the sample project:

```java
record CatalogSnapshot(String revision, String observedAt) {}
```

The corresponding JSON group could be:

```json
{
  "catalogMetadata": {
    "revision": "catalog-42",
    "observedAt": "2026-01-01T00:00:00Z",
    "sourceState": "cached"
  }
}
```

`observedAt` must reflect when the source was successfully observed. Do not replace it with the endpoint call time and make stale data look freshly updated. When the background task fails, you can keep the old snapshot with a stale/expired state per an agreed contract, or omit the optional group. Do not put exceptions, private connection addresses, or stack traces into JSON.

### 6.2. Do Not Turn Metadata Reads into Heavy Transactions

A problematic implementation is calling multiple remote APIs or running full-table statistics queries inside every `contribute` call. When monitoring systems poll continuously, cost scales with call frequency; one slow source also slows down the entire endpoint.

Prefer in-memory data, precomputed values, or controlled updated snapshots. Contributors must be thread-safe when multiple threads read concurrently. Do not mutate a shared `HashMap` while another thread is serializing it; prefer creating immutable data and swapping references atomically.

For data that genuinely must be fetched externally, define timeouts, cost limits, behavior when data is unavailable, and acceptable staleness clearly. Do not place business logic with side effects inside the `info` read operation.

### 6.3. Distinguishing Endpoint Caching from Data-Source Caching

Every direct call to `InfoEndpoint.info()` creates a builder and iterates through contributors. Through Actuator infrastructure, the read operation's result can be cached when an appropriate TTL is configured. Therefore, do not assert that a contributor always runs exactly once per HTTP request under all configurations.

Additional configuration example, merged into the existing `management` tree:

```yaml
management:
  endpoint:
    info:
      cache:
        time-to-live: 10s
```

When caching is enabled, a data update may not appear immediately in the response. Endpoint caching reuses the read result for a period of time; data-source caching avoids expensive fetches inside a contributor. The two layers address different costs. [Configuring Actuator read-operation caching](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#configuring).

### 6.4. A Contributor Throwing an Exception Can Break the Entire Aggregation

`InfoEndpoint`'s loop does not wrap each contributor in its own `try/catch` block. If a contributor throws an exception, the operation does not automatically skip that contributor and return a partial success; over HTTP, the error can become a 5xx response depending on the error-handling layer.

Thus, two categories of errors must be separated:

- **Invalid required configuration:** validate early at startup, like the record in the example.
- **Supplementary source temporarily unreadable:** handle at the data-provider layer with a concrete missing/stale policy.

Do not use `catch (Exception)` to silently return fake data. Record errors through the appropriate operational channel and keep the JSON contract consistent. Dependency readiness still needs a dedicated health mechanism if it affects request serving.

## 7. Exposing Data via an Allowlist

A custom contributor controls output data. Treat every field passed into `Info.Builder` as data visible to anyone authorized to access the endpoint.

Do not pass the entire `Environment`, process environment variables, configuration objects, or service objects into `withDetail`. Explicitly picking `service`, `region`, and `releaseTrack` in the example creates an allowlist of exposed fields and makes contract testing clear.

Values to avoid include passwords, tokens, signing keys, user-identifying information, connection strings with credentials, and internal configuration not meant for endpoint readers. Do not expect `/actuator/env`'s value-masking rules to apply automatically to maps created by your contributor.

Keep data easy to serialize to JSON: strings, numbers, booleans, lists, and maps with clear keys. Avoid returning JPA entities, request/session objects, or objects with circular references because they can pull in unintended fields, trigger lazy queries, or cause serialization failures.

If later enabling `management.info.env.enabled=true` to include `info.*` in the result, re-audit the entire exposure contract and the risk of key collisions. That is independent of the contributor reading `app.metadata.*` in this lesson.

## 8. Common Errors and Diagnostics

| Symptom | Where to check |
| --- | --- |
| `404` when calling the URL | Verify port, base path/context path, endpoint enabled, and `info` in HTTP exposure; also check exclusions |
| `401` or `403` | Authentication and authorization rules in Spring Security/proxy; exposure does not grant permission |
| `200` with `{}` | Check whether the contributor bean exists, its package is scanned, a switch disabled the bean, and any contributor actually contributes |
| Missing part of a JSON group | Check whether another contributor writes to the same top-level key |
| Config has `info.*` yet does not appear | That is the `EnvironmentInfoContributor` path; inspect that contributor separately |
| Set `management.info.application.enabled=false` yet custom group remains | JSON key names do not automatically wire into bean creation conditions; use the declared switch |
| Startup fails due to blank metadata | Check the three required properties and active profile/property overrides |
| Endpoint slow or returning 5xx | Check whether the contributor performs synchronous I/O, hits serialization errors, or throws from a supplementary source |
| Edited YAML yet old values remain | Beans do not auto-refresh; check restart, snapshots, and caching |
| Data varies per caller | Revisit design: application metadata should have a stable operational contract, without mixing in personalized data |

Diagnostic order should go from reachability → bean → data → aggregation → performance. An HTTP error does not necessarily originate in the `contribute` method.

## 9. Hands-on Practice with Verifiable Criteria

1. Add a `deployment-group` config field to the record, YAML, and JSON; test the bound value under the chosen JSON key name.
2. Add a contributor owning the `operations` key with mock public values, then verify both groups coexist.
3. Intentionally have a second contributor use the `application` key; write a test with explicit ordering to observe the value being replaced. Then fix it by restoring separate key ownership.
4. Disable `app.metadata.enabled`, keep the endpoint exposed, and verify the `application` group disappears while the URL stays readable.
5. Test with a blank required metadata field to observe the startup configuration error, then restore valid values.
6. For a dynamic-data design, document the update timing, acceptable data age, and failure behavior when fetching the source before writing the contributor.

You have completed the lesson when you can explain **who creates the data, who owns each key, when the contributor runs, and why the HTTP endpoint is reachable**, while proving the JSON contract with tests that do not depend on field order.
