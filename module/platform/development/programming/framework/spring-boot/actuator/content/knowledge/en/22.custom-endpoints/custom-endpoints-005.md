# Mapping Parameters from the Path with @Selector

## 1. Why Does an Endpoint Need a Selector?

Suppose an application tracks jobs by group. The same job ID `7` can appear in both the `exports` and `imports` groups. An operator wants to inspect the state of a specific job:

```http
GET /actuator/jobstate/exports/7
```

The two values `exports` and `7` are data-selection segments of the `jobstate` endpoint. In Actuator, we describe them using `@Selector` on the operation method parameters:

```java
@ReadOperation
public JobState read(@Selector String group, @Selector int jobId) {
    return jobs.get(new JobKey(group, jobId));
}
```

This is a method excerpt to illustrate the idea; the `JobState`, `JobKey` types and the `jobs` Map are provided in full in the project in section 4.

`@Selector` marks a parameter that selects a subset of an endpoint's data. When exposed over HTTP, selector parameters become path variables. [Spring Boot: Selector API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/annotation/Selector.html)

The goal of this lesson is to understand how the URL is assembled, how values are bound to the right parameters, and how errors are classified. Adding a selector does not automatically create a bean, open exposure, or grant access permissions.

## 2. Reading the Path Segment by Segment

With the example's default configuration:

```text
/actuator /jobstate /exports /7
    |         |        |     |
base path  endpoint   group  jobId
              ID
```

The template required by the operation is:

```text
/actuator/jobstate/{group}/{jobId}
```

Curly braces describe path variables, not literal characters the caller types into the actual URL.

| Segment | Governing Source | Example |
| --- | --- | --- |
| `/actuator` | Base path for exposing endpoints over the web | Project default |
| `jobstate` | `@Endpoint(id = "jobstate")` | Endpoint ID |
| `{group}` | First selector parameter | `exports` |
| `{jobId}` | Second selector parameter | `7` |

The order of selectors in the method signature determines the order of selector segments for the operation. With the signature above, `/exports/7` matches the order; `/7/exports` passes `exports` into the integer parameter and does not satisfy that contract.

The method name `read()` is not added to the URL. Do not call `/actuator/jobstate/read/exports/7` unless a different path contract is explicitly defined.

The base path can also change depending on application configuration. URLs in this lesson assume no context path or separate management port is configured.

## 3. How Does @Selector Differ from Query Parameters and @PathVariable?

### 3.1. A Selector Is Part of the Path Structure

In the example:

```text
Matches operation form:
/actuator/jobstate/exports/7

Does not replace the two selector segments:
/actuator/jobstate?group=exports&jobId=7
```

Query parameters do not supply missing path segments automatically. If there is no read operation at the root path `/actuator/jobstate`, the second request cannot match the operation at `/{group}/{jobId}`.

In an Actuator operation, parameters not marked as selectors can receive data from query parameters or the request body depending on the operation type. Parameters carrying `@Selector` are used to extend the path when exposed over the web. [Spring Boot 3.3: Endpoint Inputs and Paths](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints)

### 3.2. Do Not Substitute Controller Annotations

| Context | Appropriate Mechanism |
| --- | --- |
| Operation method on an Actuator endpoint | `@Selector` |
| Spring MVC controller method with `@RequestMapping` | `@PathVariable` per the controller contract |
| Filter parameter not in the path | Query parameter appropriate to the operation type |

An `@Endpoint` class is not a controller just because it is ultimately accessed over HTTP. Adding `@PathVariable` does not replace the path-building role of `@Selector`.

The required import is:

```java
import org.springframework.boot.actuate.endpoint.annotation.Selector;
```

`@Selector` does not have an attribute for writing an entire URL template like `"/jobs/{id}"`. In the standard case, simply place the annotation before the parameter. For capturing multiple remaining segments, use the `match` attribute as shown in section 7.

## 4. Complete Runnable Project: Selecting Jobs by Group and ID

The project uses Spring Boot 3.3.13, Java 21, and Spring MVC. Both endpoints are read-only:

- `jobstate`: two single selectors, where `jobId` is converted to `int`.
- `pathview`: one leading selector and one selector capturing all remaining segments.

The job data in the example is immutable sample data and does not connect to a real queue system.

### 4.1. Structure

```text
actuator-selector-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/selector/
    │   │   ├── SelectorDemoApplication.java
    │   │   ├── JobStateEndpoint.java
    │   │   └── PathViewEndpoint.java
    │   └── resources/application.properties
    └── test/
        └── java/example/selector/SelectorEndpointTest.java
```

### 4.2. pom.xml

```xml
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
    <artifactId>actuator-selector-demo</artifactId>
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

`spring-boot-starter-web` provides web infrastructure; Actuator provides endpoint mechanisms; the test starter supports mapping verification. Library versions are managed by the Boot parent.

### 4.3. Startup Class

Contents of `SelectorDemoApplication.java`:

```java
package example.selector;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SelectorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SelectorDemoApplication.class, args);
    }
}
```

The endpoint classes are in the same package as the startup class. They carry `@Component` so Spring creates beans via component scanning. In an application with a different package layout, ensure the endpoints lie within the scanned scope.

### 4.4. JobStateEndpoint.java

```java
package example.selector;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "jobstate")
public class JobStateEndpoint {
    private final Map<JobKey, JobState> jobs = Map.of(
            new JobKey("exports", 7),
            new JobState("exports", 7, "DONE"),
            new JobKey("exports", 8),
            new JobState("exports", 8, "RUNNING"),
            new JobKey("imports", 7),
            new JobState("imports", 7, "WAITING"));

    @ReadOperation
    public JobState read(@Selector String group, @Selector int jobId) {
        return jobs.get(new JobKey(group, jobId));
    }

    private record JobKey(String group, int jobId) {
    }

    public record JobState(String group, int jobId, String state) {
    }
}
```

The same ID `7` is associated with two different groups. `JobKey` holds both the group and the ID, making it observable that **both selectors participate in data selection**.

`@ReadOperation` defines the read operation. `@Selector String group` receives the first segment; `@Selector int jobId` receives the next segment after type conversion.

The method does not take `HttpServletRequest` and does not split URL strings itself. Actuator's web adapter performs the mapping before invoking the read logic.

### 4.5. HTTP Configuration

Contents of `application.properties`:

```properties
spring.application.name=actuator-selector-demo
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,jobstate,pathview
```

The example listens only on loopback for local testing. Both endpoints are included in the HTTP exposure list. `@Selector` does not replace the requirements that an endpoint be registered, enabled, and exposed.

Exposure configuration uses the ID `jobstate`, not the string `jobstate/exports/7`. Selectors are path parts of the operation and do not create new endpoint IDs.

## 5. What Happens When a Request Arrives?

For `GET /actuator/jobstate/exports/7`, you can trace the flow step by step:

```text
1. Select GET operation shaped /jobstate/{group}/{jobId}
2. Extract group = "exports", jobId = "7" from path
3. Convert "7" to int
4. Invoke read("exports", 7)
5. Look up data by key (group, jobId)
6. Serialize JobState into JSON response
```

Result:

```json
{"group":"exports","jobId":7,"state":"DONE"}
```

If we change the group:

```http
GET /actuator/jobstate/imports/7
```

then the result is:

```json
{"group":"imports","jobId":7,"state":"WAITING"}
```

The JSON fields and values are the contract to verify; member ordering or whitespace are not semantic conditions on the data.

### 5.1. Type Conversion Is Not Business Validation

In the path, `7` starts out as string data. Actuator uses its input conversion mechanism to provide an `int` value to the method. A value that cannot be converted to the required type causes the request to fail before operation logic is invoked. [Spring Boot 3.3: Input Type Conversion](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.input-type-conversion)

Having an `int` type does not mean the job ID definitely exists or is always positive. If system rules require a positive ID, enforce that rule in appropriate logic. This example looks up the ID in an existing dataset; a non-existent numeric ID produces a not-found result.

### 5.2. Distinguishing Three Kinds of Failure

| Request in the Sample Project | Result | Cause |
| --- | --- | --- |
| `/actuator/jobstate/exports/not-a-number` | 400 | Path shape matches, but `jobId` cannot be converted to `int` |
| `/actuator/jobstate/exports` | 404 | Missing one segment; does not match the operation's path |
| `/actuator/jobstate/exports/999` | 404 | Operation matched, but method returned `null` because no data exists |
| `/actuator/jobstate/exports/7/extra` | 404 | Extra segment compared to two single selectors |
| `/actuator/jobstate?group=exports&jobId=7` | 404 | Query cannot replace selector segments, and example has no root operation |

Two requests both returning 404 may fail at two different stages: selecting the operation or finding the data. Do not conclude “the selector is broken” from a 404 code alone.

For read operations, returning a value produces a 200 response; returning no value produces 404 under Actuator's response rules. [Spring Boot 3.3: Web Endpoint Response Status](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.web.response-status)

## 6. Parameter Names and the -parameters Compiler Option

Actuator needs parameter name metadata to map inputs to operation methods. When compiling Java, preserve parameter names using the `-parameters` option. The Spring Boot Maven parent in this project configures the necessary support; Boot's Gradle plugin also configures compilation for that contract. [Spring Boot 3.3: Receiving Input for Operations](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.receiving-input)

If using a custom build configuration, do not assume parameter metadata is intact just because the Java code compiles. A missing parameter name error can surface when the framework discovers or prepares to invoke operations.

Things not to confuse:

- `group` and `jobId` are Java parameter names, not two literal strings that must appear in the concrete URL.
- The concrete URL is `/exports/7`; do not write `/group/exports/jobId/7`.
- Changing selector order changes path segment order.
- Merely renaming the `read` method does not add a new name into the path.

## 7. Capturing Multiple Remaining Segments with ALL_REMAINING

By default, selectors use `Selector.Match.SINGLE`: each single selector corresponds to one segment. For data with multi-level logical paths, you can choose `ALL_REMAINING`.

Full contents of `PathViewEndpoint.java`:

```java
package example.selector;

import java.util.List;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "pathview")
public class PathViewEndpoint {
    @ReadOperation
    public PathView read(
            @Selector String area,
            @Selector(match = Selector.Match.ALL_REMAINING) String[] segments) {
        return new PathView(area, List.of(segments));
    }

    public record PathView(String area, List<String> segments) {
    }
}
```

Example:

```http
GET /actuator/pathview/config/services/mail/smtp
```

Mapping in the example:

```text
area     = "config"
segments = ["services", "mail", "smtp"]
```

Response:

```json
{"area":"config","segments":["services","mail","smtp"]}
```

Points to maintain:

1. Selector `area` captures the first segment.
2. Selector `segments` captures the remainder and preserves order.
3. Use `String[]` for multi-segment input data.
4. Place the remaining-segments selector at the end of the signature as shown; do not add a fixed selector after it.
5. Write the Java attribute in lowercase as `match`: `@Selector(match = Selector.Match.ALL_REMAINING)`.

The Actuator contract requires the type of the remaining-segments parameter to be convertible from `String[]`. [Spring Boot 3.3: Selectors in Paths](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.web.request-predicates.path)

Do not treat `String segments` as a drop-in replacement for a multi-segment array. If you want to handle a list or custom type, define the conversion rule explicitly rather than guessing how segments are joined.

This example only reflects the received **logical path**; it does not read files or access directories on the server. If path segments are used to access real resources, validating names, allowed scopes, and access permissions remains the application's responsibility.

For paths with no trailing segments, define the desired contract explicitly and test that case before relying on it. Do not add `@Nullable` hoping to automatically turn a path template missing segments into a different operation.

## 8. Compiling, Running, and Testing Manually

The project requires JDK 21, Maven, and network access to download dependencies on the first run. Run commands in the directory containing `pom.xml`.

### 8.1. Testing and Packaging

After adding the test class in section 9:

```shell
mvn verify
```

Maven compiles code, runs tests, and packages the JAR. This is an application using many Spring libraries, so you cannot replace it with a single `javac` command on just the endpoint file without preparing the classpath and resources.

### 8.2. Starting the Application

```shell
java -jar target/actuator-selector-demo-1.0.0.jar
```

If you need to change the port:

```shell
java -jar target/actuator-selector-demo-1.0.0.jar --server.port=18080
```

Use the chosen port in subsequent commands. Startup logs contain timestamps and process info that vary per run; the JSON body is the stable illustrative result.

### 8.3. Calling Single and Multi-Segment Selectors

```shell
curl --silent --show-error --fail -H "Accept: application/json" http://127.0.0.1:8080/actuator/jobstate/exports/7
```

Response body:

```json
{"group":"exports","jobId":7,"state":"DONE"}
```

Call the remaining-path endpoint:

```shell
curl --silent --show-error --fail -H "Accept: application/json" http://127.0.0.1:8080/actuator/pathview/config/services/mail/smtp
```

Response body:

```json
{"area":"config","segments":["services","mail","smtp"]}
```

In Windows PowerShell, use `curl.exe` if `curl` is a different alias. Stop the application with Ctrl+C when finished testing.

To clearly inspect the response status code for error cases, you can use `curl -i` on the URL under test. With `--fail`, curl treats HTTP error codes as failures; do not confuse curl's exit code with the HTTP status code.

## 9. Testing Mappings with MockMvc

Contents of `SelectorEndpointTest.java`:

```java
package example.selector;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SelectorEndpointTest {
    @Autowired
    private MockMvc http;

    @Test
    void bindsSelectorsInDeclaredOrderAndConvertsTheNumber() throws Exception {
        http.perform(get("/actuator/jobstate/exports/7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.group").value("exports"))
                .andExpect(jsonPath("$.jobId").value(7))
                .andExpect(jsonPath("$.state").value("DONE"));
    }

    @Test
    void theGroupIsPartOfTheLookupKey() throws Exception {
        http.perform(get("/actuator/jobstate/imports/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.group").value("imports"))
                .andExpect(jsonPath("$.state").value("WAITING"));
    }

    @Test
    void rejectsASelectorThatCannotBeConvertedToInt() throws Exception {
        http.perform(get("/actuator/jobstate/exports/not-a-number"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void aMissingPathSegmentDoesNotMatchTheOperation() throws Exception {
        http.perform(get("/actuator/jobstate/exports"))
                .andExpect(status().isNotFound());
    }

    @Test
    void queryParametersDoNotReplaceSelectorSegments() throws Exception {
        http.perform(get("/actuator/jobstate")
                        .param("group", "exports")
                        .param("jobId", "7"))
                .andExpect(status().isNotFound());
    }

    @Test
    void anUnknownJobReturnsNotFound() throws Exception {
        http.perform(get("/actuator/jobstate/exports/999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void singleSelectorsDoNotConsumeExtraSegments() throws Exception {
        http.perform(get("/actuator/jobstate/exports/7/extra"))
                .andExpect(status().isNotFound());
    }

    @Test
    void allRemainingCollectsTheRemainingSegmentsInOrder() throws Exception {
        http.perform(get("/actuator/pathview/config/services/mail/smtp"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.area").value("config"))
                .andExpect(jsonPath("$.segments.length()").value(3))
                .andExpect(jsonPath("$.segments[0]").value("services"))
                .andExpect(jsonPath("$.segments[1]").value("mail"))
                .andExpect(jsonPath("$.segments[2]").value("smtp"));
    }
}
```

The tests load the Spring context and traverse Spring MVC's request-handling infrastructure via MockMvc. They verify paths, parameter conversion, and response payloads without opening a TCP server port. [Spring Framework: MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)

The eight tests focus on meaningful behaviors:

- Values bind to the right selectors and `jobId` is converted to a number.
- The group participates in data selection, avoiding testing only a numeric ID.
- Unconvertible values are rejected.
- Missing and extra segments do not match the operation.
- Query parameters do not substitute for selector segments.
- Non-existent data produces an appropriate response.
- `ALL_REMAINING` segments preserve order.

These tests do not merely call `read(...)` directly: a direct Java call does not test how Actuator constructs paths or converts HTTP inputs.

TCP testing, reverse proxies, special path encoding, and authentication rules are additional verification layers in real deployments; do not infer them from MockMvc results.

## 10. Notes When Designing Selector Contracts

### 10.1. Do Not Use Java Types to Distinguish Two Identical URL Shapes

Two operations differing only by `int id` and `String name` do not automatically become two clear routes for the same selector position. Over HTTP, path values start as strings; the framework selects the operation by request predicates before converting inputs.

If two kinds of data are needed, choose clearly distinct path contracts or endpoint IDs. Do not rely on Java overloading as a routing mechanism.

### 10.2. Selectors Are Not an Authorization Mechanism

A `group=exports` value coming from the URL is only an input. It does not prove the caller is allowed to view jobs in that group. With real management data, check appropriate permissions before exposing results.

Use short, stable names or IDs for selectors. Do not put secrets in URLs because paths commonly appear in access logs and intermediary tools.

### 10.3. Do Not Use Encoded Slashes to Bypass the Contract

A single selector picks one segment, while `ALL_REMAINING` is designed to receive multiple segments. Do not treat `%2F` as a guaranteed way to cram a multi-level path into a single selector: servers, proxies, and filters may process or reject it differently.

In the practice exercise, selectors use simple ASCII characters to focus on the mapping mechanism. When a contract requires special characters, test the entire request path in the corresponding deployment environment.

### 10.4. HTTP and JMX Do Not Represent Inputs the Same Way

`@Endpoint` belongs to Actuator's technology-neutral model, not exclusively Spring MVC. When called over HTTP, selectors are represented as path segments. When invoking an operation over JMX, inputs are JMX operation parameters, not an HTTP URL to split manually.

Therefore, do not replace the selector mechanism with `@PathVariable` just to tie code to a specific technology if the goal remains an Actuator operation.

## 11. Common Errors

| Symptom | What to Check |
| --- | --- |
| URL has the trailing segment but does not invoke the operation | Does the parameter have `@Selector`, and is the import correct? |
| Group value enters the numeric parameter | Does URL segment order match selector order? |
| HTTP 400 on job ID | Can the value be converted to the required Java type? |
| HTTP 404 when a segment is missing | Does the operation's template require that segment? |
| Passing query params still fails | Are required selector segments being omitted? |
| Capturing multiple segments but only one works | Is `SINGLE` mode used instead of `ALL_REMAINING`? |
| Parameter metadata error when loading endpoint | Does the build preserve parameter names with `-parameters`? |
| Same numeric ID returns the wrong group | Does the data-selection logic use all necessary selectors? |
| All endpoint URLs are unreachable | Are bean, enabled, exposure, base path, port, and security all configured properly? |

Do not fix a missing selector by exposing all endpoints or disabling security. Check along the chain: path structure → parameter conversion → data logic → relevant exposure/access conditions.

## 12. Practice

1. Change the request from `exports/7` to `imports/7` and explain why the state changes despite the identical number.
2. Swap the order of the two selectors in the signature, then update the URL and test accordingly. Distinguish changing parameter names from changing positions.
3. Try a value that cannot be converted to a number and a non-existent numeric ID; point out the difference between 400 and 404 errors.
4. Extend the tail of `pathview` by one more segment; verify the returned array grows by one element and preserves order.
5. If root-path access needs to be supported, design a meaningful separate operation and verify it does not conflict with the selector operation.

After this lesson, you should be able to derive the URL template from an operation method signature and point out exactly which value enters each parameter.
