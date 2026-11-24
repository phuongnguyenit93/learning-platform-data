# Role of the info Endpoint and InfoContributors

## 1. Understanding the Exact Question That info Answers

When inspecting a running application, operators often need to know: which service is this, which release is it, which source code was it built from, and what deployment characteristics does it have. Spring Boot Actuator's `info` endpoint is where such descriptive information is gathered.

For example, two servers may both be serving requests, yet one is still running an older build. Version data or a commit hash on `info` helps compare the two deployments. Returning a version by itself does not confirm that the database is up or that the application is ready to receive traffic.

| Need | Appropriate tool |
| --- | --- |
| Identifying the application and deployment | `info` |
| Checking operational status and readiness | `health` and appropriate health groups |
| Monitoring request counts, processing time, and memory | `metrics` or a metrics collection system |
| Diagnosing configuration sources | `env`, within permitted access boundaries |

Data that describes an application is called metadata. You should select fields that are useful for identification instead of turning `info` into a copy of the entire configuration.

In this lesson, examples use Java 21 and Spring Boot 3.3.0 to reproduce behavior from the 3.3.x line. The default HTTP path is `/actuator/info`; when changing the management port or base path, the actual URL changes accordingly.

## 2. The Endpoint Aggregates; Contributors Provide Individual Data Pieces

Three components must be distinguished:

- `InfoContributor`: an object that contributes data, registered as a Spring bean.
- `Info.Builder`: where contributors jointly add key–value pairs.
- `InfoEndpoint`: invokes the contributors and returns the aggregated map of information.

The contributor interface has only a single method:

~~~java
void contribute(Info.Builder builder);
~~~

The method returns `void` because data is added to the passed-in builder. A contributor does not send an HTTP response directly and does not need `@RestController`. It is also a functional interface, so it can be implemented as a lambda when declaring a `@Bean`. See the [InfoContributor contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoContributor.html).

The processing flow can be visualized as follows:

~~~text
GET /actuator/info
        |
        v
Actuator infrastructure calls InfoEndpoint.info()
        |
        v
Create Info.Builder
        |
        +--> contributor A adds "app"
        +--> contributor B adds "build"
        +--> contributor C adds "release"
        |
        v
Build info map and serialize to JSON
~~~

The labels A/B/C only illustrate the contribution process; they do not prescribe bean ordering. If no contributor contributes data, the result can be `{}`. An empty JSON object is still a valid result and does not mean the request failed.

At the API level, `InfoEndpoint` takes a list of contributors and provides the `info()` read operation. Therefore, the aggregation mechanism can be tested in Java without starting an HTTP server. See the [InfoEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoEndpoint.html).

## 3. Built-in Information Sources

Spring Boot provides auto-configured contributors. The following list applies to the 3.3.x line:

| ID | Class | Main data | Condition or default |
| --- | --- | --- | --- |
| `build` | `BuildInfoContributor` | Build information | `BuildProperties` present, typically from `META-INF/build-info.properties`; enabled by default when eligible |
| `git` | `GitInfoContributor` | Git information | `GitProperties` present, typically from `git.properties`; enabled by default when eligible |
| `env` | `EnvironmentInfoContributor` | Properties prefixed with `info.` | Disabled by default |
| `java` | `JavaInfoContributor` | Running Java environment | Disabled by default |
| `os` | `OsInfoContributor` | Operating system | Disabled by default |
| `process` | `ProcessInfoContributor` | Running process | Disabled by default |

Bean creation conditions and default ordering are described in [InfoContributorAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.html).

Two practical consequences follow:

1. Adding the Actuator dependency does not mean build and Git information are automatically present. The corresponding resources must be generated during the build and placed on the application classpath.
2. Declaring `spring.application.name` or `<version>` in Maven does not automatically turn them into all desired fields on `info`. There must be a contributor that reads and contributes that data.

This lesson focuses on the roles and coordination of contributors. Setting up plugins to generate build/Git metadata is a separate task; the example below does not depend on those generated files.

## 4. Distinguishing Three Configuration Layers

Having a contributor with data is not enough for users to read it over HTTP. Three independent layers must be considered:

| Layer | Spring Boot 3.3.x configuration example | Meaning |
| --- | --- | --- |
| Allow the endpoint to exist in Actuator | `management.endpoint.info.enabled=true` | Enables the `info` endpoint |
| Expose over HTTP | `management.endpoints.web.exposure.include=health,info` | Includes the endpoint in the web-exposed set |
| Allow access | Spring Security, network, or proxy rules | Decides who can call the URL |

In Spring Boot 3.3.x, `info` is enabled by default, but only `health` is exposed over HTTP by default. `include=info` does not bypass authorization rules and does not restore an endpoint that has been disabled. If the same ID is listed in `exclude`, the exclusion rule takes precedence. These rules are described in [enabling and exposing Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Configuring data sources uses a different prefix:

~~~properties
management.info.env.enabled=true
~~~

This line enables the `env` contributor. It does not expose a URL and does not enable the `env` endpoint.

Distinguish accurately:

- `management.endpoint.info.enabled`: controls the endpoint.
- `management.endpoints.web.exposure.include`: controls web exposure.
- `management.info.env.enabled`: controls a contributor of `info`.

## 5. Complete Example: Configuration Information Combined with a Custom Contributor

### 5.1. Standalone Project Structure

Create a Maven project with the following files:

~~~text
info-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/info/
    │   │   ├── InfoApplication.java
    │   │   └── ReleaseInfoContributor.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/info/
            └── InfoContributorTest.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>info-demo</artifactId>
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
~~~

This is a standalone practice project. Maven needs access to the dependency repository on the first run if the machine does not already have all required libraries cached.

### 5.2. Starting the Application

`src/main/java/example/info/InfoApplication.java`:

~~~java
package example.info;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InfoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InfoApplication.class, args);
    }
}
~~~

### 5.3. Selecting Configuration Data to Expose

`src/main/resources/application.properties`:

~~~properties
spring.application.name=info-demo
server.address=127.0.0.1
server.port=8080

management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info

management.info.env.enabled=true
management.info.build.enabled=false
management.info.git.enabled=false
management.info.java.enabled=false
management.info.os.enabled=false
management.info.process.enabled=false

info.app.name=info-demo
info.app.purpose=actuator-learning
~~~

Other contributors are explicitly disabled so that the JSON output in this lab is predictable. Disabling `build` and `git` is not required if the project does not have their metadata.

`EnvironmentInfoContributor` takes properties under `info.*` and strips that prefix when building the result structure. The last two properties become an `app` object containing `name` and `purpose`. The name `env` here refers to the Spring `Environment` configuration source, not solely operating system environment variables.

### 5.4. Contributing Custom Release Information

`src/main/java/example/info/ReleaseInfoContributor.java`:

~~~java
package example.info;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.stereotype.Component;

@Component
public class ReleaseInfoContributor implements InfoContributor {

    @Override
    public void contribute(Info.Builder builder) {
        Map<String, Object> release = new LinkedHashMap<>();
        release.put("channel", "training");
        release.put("schemaVersion", 1);
        builder.withDetail("release", release);
    }
}
~~~

`@Component` registers the contributor as a bean. The class sits in a subpackage scanned from `InfoApplication`, so Spring Boot can discover it.

`withDetail("release", release)` adds a top-level key named `release`; the inner map becomes a nested JSON object. The `schemaVersion` value is an integer, so it is serialized as a JSON number. The fixed values in the example are labels for hands-on practice, not values automatically derived from a release pipeline.

Do not call `builder.build()` inside the contributor. Finalizing the map is the responsibility of the endpoint after all contributors have had a chance to contribute.

### 5.5. Running and Observing

From the directory containing `pom.xml`, using JDK 21:

~~~shell
mvn spring-boot:run
~~~

Once the application has started, open a second terminal:

~~~shell
curl -sS -H "Accept: application/json" http://127.0.0.1:8080/actuator/info
~~~

On Windows PowerShell, use `curl.exe` if `curl` is aliased to another command.

The expected HTTP status is `200`. The body has the following content; JSON whitespace and property order may differ:

~~~json
{
  "app": {
    "name": "info-demo",
    "purpose": "actuator-learning"
  },
  "release": {
    "channel": "training",
    "schemaVersion": 1
  }
}
~~~

`app` is contributed by the `env` contributor; `release` is contributed by the custom bean. No `status` field is automatically added as in `health`.

The example does not add Spring Security and binds only to loopback for practice. In an application with Spring Security, permission to call the endpoint depends on the actual security configuration; do not infer access rights solely from `exposure.include`.

## 6. Three Experiments to Understand the Mechanism Instead of Just Copying Configuration

Each experiment below starts from the original configuration in section 5. Stop the application and restart it after modifying the file.

### 6.1. Disabling the env Contributor

Change:

~~~properties
management.info.env.enabled=false
~~~

Only the following remains in the result:

~~~json
{
  "release": {
    "channel": "training",
    "schemaVersion": 1
  }
}
~~~

The `info.app.*` properties still exist in configuration, but the `env` contributor is no longer active to put them into the response. The custom bean still runs.

### 6.2. Disabling Contributors Enabled by Default

Add:

~~~properties
management.info.defaults.enabled=false
~~~

Keep `management.info.env.enabled=true` as in the original configuration. The response still contains both `app` and `release`: the `env` contributor is enabled explicitly, while the `ReleaseInfoContributor` bean is not conditioned by `management.info.defaults.enabled`.

Similarly, a property such as `management.info.release.enabled=false` does not automatically disable any bean whose name is related to `release`. To have a switch for a custom contributor, the application itself must attach an appropriate condition, such as `@ConditionalOnProperty`, or control bean registration directly.

### 6.3. Unexposing Over HTTP

Change:

~~~properties
management.endpoints.web.exposure.include=health
~~~

With this exact sample project, the URL `/actuator/info` is no longer exposed and returns `404`. This differs from a `200` response with body `{}`: `404` indicates there is no corresponding resource at the requested URL, whereas `{}` indicates the read operation ran but no data was contributed.

In a real system, when encountering `404` you must also check the port, base path, and context path; do not conclude from the status alone that a contributor is broken.

## 7. Testing Aggregation and Key Collisions in Java

A common design mistake is having two contributors use the same top-level key. `Info.Builder` stores entries in a map; writing to the same key again replaces the previous value rather than deep-merging two sub-maps.

For example: one contributor writes `release.channel` via a map under the `release` key, and another contributor writes a map containing `release.region` also under the `release` key. Those two maps do not automatically become a single object containing both fields.

Create `src/test/java/example/info/InfoContributorTest.java`:

~~~java
package example.info;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.actuate.info.InfoEndpoint;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InfoContributorTest {

    @Test
    void combinesDifferentTopLevelKeys() {
        InfoContributor app = builder ->
                builder.withDetail("app", Map.of("name", "info-demo"));

        InfoEndpoint endpoint = new InfoEndpoint(
                List.of(app, new ReleaseInfoContributor()));

        assertEquals(
                Map.of(
                        "app", Map.of("name", "info-demo"),
                        "release", Map.of(
                                "channel", "training",
                                "schemaVersion", 1)),
                endpoint.info());
    }

    @Test
    void laterContributorReplacesTheSameTopLevelKey() {
        InfoContributor first = builder ->
                builder.withDetail("release", Map.of("channel", "training"));
        InfoContributor second = builder ->
                builder.withDetail("release", Map.of("region", "lab"));

        InfoEndpoint endpoint = new InfoEndpoint(List.of(first, second));

        assertEquals(
                Map.of("release", Map.of("region", "lab")),
                endpoint.info());
    }

    @Test
    void noContributorsProducesAnEmptyMap() {
        InfoEndpoint endpoint = new InfoEndpoint(List.of());

        assertEquals(Map.of(), endpoint.info());
    }
}
~~~

Run:

~~~shell
mvn test
~~~

All three tests should pass: combining different keys, replacing values on duplicate keys, and returning an empty map when there are no contributors. No Spring context or HTTP server needs to be started because this directly tests the aggregation contract.

In the second test, order is fixed with `List.of(first, second)`. In a real application, do not rely on class names or component scan order to decide who writes later. If ordering is truly needed, Spring supports bean ordering mechanisms; however, a more resilient design is to assign one owner per top-level key.

Example of clear key partitioning:

~~~text
app       -> identification information taken from configuration
build     -> build metadata
git       -> source code metadata
release   -> release labels contributed by the application
~~~

If multiple sources must belong inside `release`, aggregate them intentionally in a single contributor rather than letting beans overwrite one another.

## 8. Reliability and What Data Should Be Exposed

A contributor may compute data when the read operation is executed; do not assume every `contribute()` runs only once at startup. Endpoint caching, if configured, can reduce how often it executes and introduce staleness into the data.

For identification metadata, prefer small, cheap, and stable data: service labels, schema versions, and curated build identifiers. If an external service must be called to gather information, consider preparing a time-bounded snapshot with clear error handling. Do not let reading a release label depend on a chain of slow requests.

In Spring Boot 3.3.0's aggregation mechanism, a contributor throwing an exception is not automatically turned into an `UNKNOWN` entry by `InfoEndpoint` so that other contributors can safely continue. It can fail the entire info read; the final HTTP error also depends on the error-handling layer. Do not use a contributor to check database connectivity in place of a `HealthIndicator`.

Contribute only fields that are explicitly approved for exposure. Never put passwords, tokens, connection strings containing credentials, or user data into `info.*` or `withDetail`. Do not rely on the `env` endpoint's value-masking mechanism to protect data returned by `info`: these are two separate endpoints.

For instance, a property named `info.app.password` still falls under `info.*`, which the `env` contributor reads. Having the word "password" in the name is no reason to treat that data as safe on the `info` endpoint.

## 9. Symptom-Based Troubleshooting

| Symptom | Where to check |
| --- | --- |
| `404` when calling the sample URL | Check whether the endpoint is enabled/exposed, and verify the port and path |
| `401` or `403` | Check authentication and authorization rules in the application or proxy |
| `200` with `{}` | Check whether contributors are created and have data to contribute |
| `release` present but `app` missing | Check `management.info.env.enabled` and `info.app.*` properties |
| `app` present but `release` missing | Check whether the contributor is a bean and within component scan scope |
| `build` or `git` missing | Check metadata resources, corresponding beans, and contributor switches |
| One data group wipes out a prior group with the same name | Check top-level key collisions; do not assume maps are deep-merged |
| Slow or failing requests after adding a contributor | Check computation, I/O, and exceptions inside `contribute()` |

## 10. Hands-on Practice

1. Add `info.app.owner=learning-team`. Predict where the new field will appear and verify over HTTP.
2. Rename the `release` key in `withDetail` to `deployment`. Observe that the JSON structure changes according to the data key, not the class name.
3. Try writing two different maps to the same key using the second test; explain why the first data disappears.
4. Disable `env` and then unexpose `info` over HTTP in two separate runs. Explain the difference between a missing data group and a missing URL.
5. Choose three identification fields appropriate for one of your applications. For each field, identify the data source, the owning contributor, and who is permitted to read it.

After these experiments, you should be able to explain the relationship: contributors decide what data is contributed; the endpoint aggregates it; exposure and authorization configuration decide accessibility.
