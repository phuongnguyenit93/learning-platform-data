# Testing Custom Endpoints for Valid, Missing, and Wrong-Type Parameters

Suppose the Actuator endpoint `jobpreview` previews a list of jobs, with `limit` as the maximum number of items to return. `limit=2` is a valid request, `limit=abc` cannot be converted to `Integer`, and `limit=21` converts cleanly but exceeds the example's upper bound. Both of the latter inputs can return `400`, yet the failure occurs in two different places. Designing test cases for each stage helps distinguish when Actuator rejects a request before invoking the method, versus when the method receives the value and rejects it itself.

## Tracing a Value from Request to Method

1. **Operation mapping.** Spring Boot 3.3 discovers the endpoint bean and exposes its `@ReadOperation` over `GET` if the endpoint is exposed over HTTP. The example uses `@WebEndpoint(id = "jobpreview")` because the response carries a custom HTTP status code. With the default `/actuator` base path, the path is `/actuator/jobpreview`.
2. **Name binding and type conversion.** Actuator extracts the query value by the Java parameter name—here `limit`—and converts it to the target type. Java must be compiled with `-parameters` so parameter names are available at runtime. Operation parameters are required by default, even when using the wrapper type `Integer`. If a required parameter is missing or its value cannot be converted, Actuator returns `400 Bad Request` before calling the method.
3. **Semantic validation.** After receiving the integer, the method checks that `limit` falls within 1 to 20. It returns `400` with a JSON error code if the value is out of range. With the default converter in this example, a parameter present with an empty string value is converted to `null`. The method handles that case explicitly before comparing numbers to avoid an unboxing failure on `Integer`.

## Test Matrix

Send all requests to the same `GET /actuator/jobpreview` operation.

| Input | Outcome | Point to Verify |
| --- | --- | --- |
| `limit=2` | `200`, JSON contains `limit: 2` and the first two jobs | Right path, right parameter, successful conversion, and expected payload. |
| `limit=1`, `limit=20` | `200` | Both bounds of the range are valid. When the list is shorter than the limit, returns up to the available items. |
| Omit `limit` completely | `400` | Missing required parameter. |
| `limit=` | `400`, `error: "limit_empty"` | Parameter sent with an empty value. The example handles the post-conversion value in a dedicated branch. |
| `limit=abc`, `limit=2.5`, `limit=2147483648` | `400` | Non-numeric strings, decimal numbers, and values overflowing `Integer` are all rejected during type conversion. |
| `limit=0`, `limit=21` | `400`, `error: "limit_out_of_range"` | Both are type-valid integers rejected by the endpoint's business rule. |

## Runnable Example with Spring Boot 3.3 and MockMvc

Create a separate Gradle project and run with JDK 17 or later and a compatible Gradle version. In `settings.gradle`, set `rootProject.name = 'job-preview-endpoint-test'`. The project uses the `java` plugin and the Spring Boot BOM to select dependency versions, so configure `-parameters` explicitly.

File `build.gradle`

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

tasks.named('test') {
    useJUnitPlatform()
}
```

File `src/main/java/demo/preview/PreviewApplication.java`

```java
package demo.preview;

import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PreviewApplication {

    @Bean
    JobPreviewEndpoint jobPreviewEndpoint() {
        return new JobPreviewEndpoint();
    }

    @WebEndpoint(id = "jobpreview")
    static class JobPreviewEndpoint {

        private static final List<String> JOBS = List.of("import", "archive", "refresh");

        @ReadOperation
        public WebEndpointResponse<Map<String, Object>> preview(Integer limit) {
            if (limit == null) {
                return new WebEndpointResponse<>(Map.of("error", "limit_empty"),
                        WebEndpointResponse.STATUS_BAD_REQUEST);
            }
            if (limit < 1 || limit > 20) {
                return new WebEndpointResponse<>(Map.of("error", "limit_out_of_range"),
                        WebEndpointResponse.STATUS_BAD_REQUEST);
            }
            return new WebEndpointResponse<>(Map.of(
                    "limit", limit,
                    "jobs", JOBS.subList(0, Math.min(limit, JOBS.size()))));
        }
    }
}
```

File `src/test/java/demo/preview/JobPreviewEndpointTest.java`

```java
package demo.preview;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.contains;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = PreviewApplication.class,
        properties = "management.endpoints.web.exposure.include=jobpreview"
)
@AutoConfigureMockMvc
class JobPreviewEndpointTest {

    private static final String PATH = "/actuator/jobpreview";

    @Autowired
    MockMvc mvc;

    @Test
    void returnsAtMostTheRequestedNumberOfJobs() throws Exception {
        mvc.perform(get(PATH).param("limit", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.limit").value(2))
                .andExpect(jsonPath("$.jobs", contains("import", "archive")));
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 20})
    void acceptsBothBoundsOfTheBusinessRange(int limit) throws Exception {
        mvc.perform(get(PATH).param("limit", Integer.toString(limit)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.limit").value(limit));
    }

    @Test
    void rejectsMissingLimit() throws Exception {
        mvc.perform(get(PATH))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsAnExplicitlyEmptyLimit() throws Exception {
        mvc.perform(get(PATH).param("limit", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("limit_empty"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"abc", "2.5", "2147483648"})
    void rejectsValuesThatCannotBeConvertedToInteger(String raw) throws Exception {
        mvc.perform(get(PATH).param("limit", raw))
                .andExpect(status().isBadRequest());
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 21})
    void rejectsIntegersOutsideTheBusinessRange(int limit) throws Exception {
        mvc.perform(get(PATH).param("limit", Integer.toString(limit)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("limit_out_of_range"));
    }
}
```

Run from the project directory.

```bash
gradle test --tests demo.preview.JobPreviewEndpointTest
```

The verified result with Java 17, Spring Boot 3.3.0, and the JUnit Platform is **10 passed, 0 failed**. Each `@ValueSource` entry runs as a separate test case. You can view the Gradle report at `build/reports/tests/test/index.html` after running the task above.

`@SpringBootTest` loads the Actuator configuration, while `@AutoConfigureMockMvc` sends mock requests through the Spring MVC pipeline in that context. This tests the path, type conversion, and operation status codes without opening a network port. Calling `preview(2)` directly only tests logic after an `Integer` has already been obtained. To also verify a separate management port or server configuration, add a `RANDOM_PORT` test sending HTTP requests to the real port.

## Reading Results and Extending Test Cases

- **Start with a valid case.** Assert both `200` and the JSON field reflecting the received value. If this case yields `404`, check that the endpoint is registered as a bean, enabled, exposed over HTTP, and at the expected base path. If the operation is blocked by authentication or authorization, configure appropriate credentials for the parameter tests.
- **Assert on payload by error source.** For type conversion or missing parameter errors, the Spring Boot contract here is status `400`. For application-defined errors, also assert `$.error` to distinguish causes. Asserting individual JSON fields avoids depending on key ordering. For write operations with side effects, inspect business state or use a test double to verify that invalid input is rejected before updating data.
- **Optional parameters need dedicated cases.** If the contract allows omitting `limit`, declare `@Nullable Integer limit` and assign the default inside the method. Then test the omitted case, empty string case, and invalid type case separately. `@Nullable` permits a missing value, whereas sending an unconvertible string still results in a type conversion error.
- **For write operations, test the right input format.** `@WriteOperation` uses `POST` and can bind simple parameters from top-level JSON properties. If the contract requires JSON, set `Content-Type: application/json` and test missing properties or unconvertible values case by case. A malformed JSON body is its own test case because the request may be rejected while reading the body.

## Reference Documentation

- [Spring Boot 3.3 · Declaring Endpoints, Parameter Binding, and Response Codes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 · WebEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html)
- [Spring Boot 3.3 · WebEndpointResponse API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html)
- [Spring Boot 3.3 · Testing with a Mock Web Environment](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)