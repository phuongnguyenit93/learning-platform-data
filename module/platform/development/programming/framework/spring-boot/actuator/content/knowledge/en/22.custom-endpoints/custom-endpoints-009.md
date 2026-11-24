# Designing Return Types, JSON Payloads, and Resource Responses

## 1. Understand the Endpoint Response Before Choosing a Java Type

A custom Actuator endpoint typically serves operators, diagnostic tools, or automated scripts. Consumers need to know what the result means, what structure to read it in, and when to treat a call as failed. Therefore, designing a response is designing a **usage contract**, not merely picking a type so the `return` statement compiles.

There are three related yet distinct decisions:

- **Java return type:** for example, a record holding metrics, a small `Map`, or a `Resource` holding report content.
- **HTTP representation:** JSON, plain text, or binary data; expressed via `Content-Type` and the response body.
- **HTTP semantics:** codes 200, 204, 404, 503… indicating the outcome of handling the request under the chosen contract.

For instance, `state="UNAVAILABLE"` is a data value. It does not automatically turn the response into HTTP 503. Likewise, a string that looks like a file path does not make the server automatically read and send that file.

In the Custom Endpoints chapter, a read operation answers the question “what is the application observing?”. A compact DTO helps monitoring tools read stable fields; a resource response helps operators retrieve exact report content. The two needs can use two different endpoints rather than forcing one URL to sometimes return JSON and other times return an unrelated data type.

This lesson uses the Spring Boot 3.3.x model with Spring MVC. The complete example in section 6 uses Java 21 and Spring Boot 3.3.0 to fix the practice environment; records in the example use syntax available since Java 17.

## 2. Choosing Return Types According to Data to Expose

| Need | Usable Type | What to Decide First |
| --- | --- | --- |
| Structured report for long-term use | DTO or `record` | Field names, data types, units, value meanings |
| Small set of fields changing infrequently | `Map<String, Object>` | Keep key names and value types consistent |
| A list of results | `List<ItemView>` or wrapper DTO | Maximum element count, ordering, empty-list case |
| A single value | Number, boolean, or string | Will readers have enough context to understand the value? |
| Report or file content | `Resource` | Format, size, whether the stream can be reopened |
| Need HTTP status control | `WebEndpointResponse<T>` in web-specific handling | Separate `T` data from HTTP information |
| Operation genuinely needs no body | `void` or `null` result as appropriate | Does default HTTP behavior match the intended meaning? |

A DTO is an object dedicated to data exchange. You do not need to send an entire business object just because it already sits in memory. A persistence entity may carry circular references, internal fields, or implementation details that operations tools do not need to know.

For example, a requirement “report the number of running jobs and the duration of the most recent run” can use:

```java
public record JobSnapshot(
        long activeJobs,
        long lastRunDurationMillis,
        java.util.List<String> warnings) {
}
```

This is an illustrative type declaration, not a standalone application. The three fields already tell readers the count, time unit, and list of warnings. Compared to returning `Object`, the `JobSnapshot` signature immediately shows code maintainers the expected shape of the result.

`record` is only immutable at the component-reference level; a mutable `List` can still be modified elsewhere. If constructing results from a shared list, snapshot the needed data and use an appropriate copy, such as `List.copyOf(warnings)` when elements are non-null. When metrics are updated concurrently, constructing a record does not guarantee all fields were read at the same instant; snapshot consistency must be handled where metrics are collected.

With `Map`, the problem often lies in a weaker contract:

```java
// Two results with the same key name but different data types.
java.util.Map<String, Object> first = java.util.Map.of("activeJobs", 3L);
java.util.Map<String, Object> second = java.util.Map.of("activeJobs", "3 jobs");
```

The snippet above illustrates a change that breaks programs parsing numbers. Using `Map` is not wrong, but key names and value types must be managed as carefully as with a DTO. `Map.of` also rejects null keys or values.

## 3. Designing JSON So Other Programs Read It Reliably

### 3.1. Put Names and Units Directly in the Contract

Suppose an endpoint returns:

```json
{
  "schemaVersion": 1,
  "state": "READY",
  "activeJobs": 3,
  "lastRunDurationMillis": 42,
  "warnings": []
}
```

This is a JSON structure defined by the lesson's example. `schemaVersion` is an application-designed field, not something Actuator adds automatically.

| Field | Meaning Chosen in Example |
| --- | --- |
| `schemaVersion` | Version of the data structure understood by consumers |
| `state` | State defined by this diagnostic check |
| `activeJobs` | Job count, using a JSON number |
| `lastRunDurationMillis` | Duration of the latest run, in milliseconds |
| `warnings` | List of messages; no warnings is `[]` |

Do not use a `duration` field that sometimes returns seconds and sometimes returns milliseconds. Do not embed units inside a string if consumers need numeric comparisons. If there is an observation timestamp, you can design a field like `observedAt` with an ISO 8601 string with timezone offset, but you must standardize the format and verify the actual JSON serializer.

Field names, types, units, and meanings are all part of the contract. Renaming `activeJobs` to `running` or changing a number to a string can break consumers even though the URL stays the same. Adding a field also requires checking whether recipients accept unknown fields; do not assume every additive change is compatible.

Do not require JSON parsers to depend on property order. For lists, conversely, element order can carry meaning; if a list is sorted by priority, document that rule explicitly.

### 3.2. Distinguishing Empty, Unknown, and Not Found

- `warnings: []`: the list is known and currently has no elements.
- `lastRunDurationMillis: null`: can represent “no run yet”, if the contract defines it that way.
- Missing `lastRunDurationMillis` field: recipients need to know whether this is an optional field, omitted, or an unmatched schema version.
- The entire operation result being `null`: no longer a JSON null field inside a DTO; it can affect the HTTP status code.

Do not use `0` to simultaneously represent “zero duration” and “not yet measured”. When a field can be unknown, choose a suitable reference type such as `Long` or design a separate measurement status. Do not rely on switching `long` to `Long` to automatically convey business meaning; that meaning must be documented.

An empty list is still a valid result. For instance, a request to “list running jobs” can return HTTP 200 with `[]`. It differs from a request to “read job by ID” when the ID does not exist.

### 3.3. Let the JSON Converter Handle Objects

When you want to send structured JSON, return a DTO or `Map` and let the HTTP conversion mechanism handle it. Do not concatenate strings from external data to build JSON; quotes, newlines, and special characters easily corrupt the output.

You should not write `return "{\"activeJobs\":3}";` just to replace a DTO. `String` is a different data type; converter selection and string rendering also depend on configuration. Having a particular response look like JSON does not turn that signature into a typed object contract.

For Actuator 3.3, there is the property `management.endpoints.jackson.isolated-object-mapper`, which defaults to `true`. Therefore, when customizing JSON naming or formatting in the application, verify the actual Actuator response instead of assuming that configuration is always shared. Examples in this lesson use direct field names, numeric types, and simple lists to reduce dependence on extra configuration. [Actuator 3.3 Jackson properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 3.4. Expose Only the Data Operators Need

Build an allowlist of fields permitted in the response, rather than pushing a large object onto HTTP and trying to redact fields later. For example, queue diagnostics typically need counts and states; they do not need passwords, tokens, user request payloads, or full connection strings.

Do not treat built-in endpoint sanitization rules such as `env` as a guarantee for every field in custom DTOs. Every new field must be reviewed where the response is constructed. For large lists or reports, bound data size and generation cost; a diagnostic endpoint must not overload the application simply by being polled continuously.

## 4. Relationship Between Return Values and HTTP Status

### 4.1. Default Behavior to Understand

Without an HTTP-control wrapper, Actuator maps operation results according to the following cases:

| Operation Type | Result | Default HTTP Status |
| --- | --- | --- |
| `@ReadOperation` | Has value, including an empty list | 200 |
| `@ReadOperation` | No value | 404 |
| `@WriteOperation` or `@DeleteOperation` | Has value | 200 |
| `@WriteOperation` or `@DeleteOperation` | No value | 204 |

Thus, returning `void` from a read operation is generally unsuitable if you expect a successful response with content. Also distinguish a `null` top-level result from a DTO with a null component. [Endpoint response status rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.response-status).

### 4.2. Controlling Status with WebEndpointResponse

`WebEndpointResponse<T>` holds a body `T`, a status, and the ability to specify a content type. For example, a method in a web extension can return:

```java
return new WebEndpointResponse<>(
        body,
        WebEndpointResponse.STATUS_SERVICE_UNAVAILABLE);
```

This is an illustrative method body snippet; `body` is the DTO constructed in that method. With this wrapper, the JSON sent is the DTO in `body`, not a JSON object forced to have `body` and `status` keys. `WebEndpointResponse` is not a mechanism for adding arbitrary HTTP headers. [WebEndpointResponse 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html).

Use `@EndpointWebExtension` when the base endpoint provides data and the extension needs to add HTTP-specific decisions. In the full example, the base endpoint returns `Snapshot`; the web extension uses that snapshot to decide 200 or 503. `@EndpointWebExtension(endpoint = DiagnosticsEndpoint.class)` identifies the endpoint whose behavior the extension augments. [EndpointWebExtension API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/EndpointWebExtension.html).

Here, 503 is a **design decision of the sample diagnostic check**: callers treat `READY` as success and other states as not ready. An informational endpoint can still use 200 and describe a warning in JSON. Pick the meaning first and encode it, rather than leaving monitoring tools to guess.

Do not assume `ResponseEntity` in an Actuator operation is handled identically to a `@RestController` method's return value. Operations go through Actuator's endpoint handling mechanism. For this lesson's sample, use `WebEndpointResponse` to control status; when Spring MVC-specific headers or file-download mechanisms are needed, choose the appropriate HTTP handler layer and verify with real requests.

## 5. JSON, Content Types, and Resources Are Different Things

`Content-Type` describes the representation the server sends. `Accept` expresses the content types the caller accepts. An operation's `produces` attribute participates in determining supported representations; it does not turn a record into a PDF or turn a path string into file contents.

For a `Resource` return type, operations default to `application/octet-stream`; you can specify another type explicitly. For example, use `text/plain;charset=UTF-8` for a text report and `application/json` for a DTO. Default rules also distinguish `void`/`Void` from results with content. [Actuator produces rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.request-predicates.produces).

If a URL only supports JSON and the caller only accepts `text/html`, the response can be 406. Changing `Accept` is not a command for the server to synthesize a representation the endpoint does not support.

In the sample where the base endpoint and web extension replace the same read operation, both use the same `produces = "application/json"`. Keep mapping predicates consistent on both sides instead of accidentally creating two different operations competing on the same URL. This is also something to check when encountering ambiguous mapping errors after adding an extension.

## 6. Complete Example: Typed JSON and Text Report

The application has two URLs:

- `GET /actuator/diagnostics` returns a JSON snapshot. The web extension sets status 200 or 503.
- `GET /actuator/diagnosticreport` returns the content of a text resource.

`@WebEndpoint` is used for the HTTP-only report. It differs from `@Endpoint` in the scope of exposed technologies. [WebEndpoint 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html).

### 6.1. Standalone Project Structure

```text
actuator-response-demo/
├── pom.xml
└── src/main/
    ├── java/example/actuator/DemoApplication.java
    └── resources/application.properties
```

Contents of `pom.xml`:

```xml
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
    <artifactId>actuator-response-demo</artifactId>
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

Contents of `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18080
management.endpoints.web.exposure.include=health,diagnostics,diagnosticreport
```

This is a configuration for local experimentation. The two starters above do not add Spring Security. If placing the endpoints into an application that already has security, access results also depend on that application's authentication and authorization rules.

### 6.2. Java Code

Contents of `src/main/java/example/actuator/DemoApplication.java`:

```java
package example.actuator;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.EndpointWebExtension;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

@SpringBootApplication(proxyBeanMethods = false)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    DiagnosticsEndpoint diagnosticsEndpoint(
            @Value("${demo.state:READY}") String state) {
        return new DiagnosticsEndpoint(state);
    }

    @Bean
    DiagnosticsWebExtension diagnosticsWebExtension(DiagnosticsEndpoint endpoint) {
        return new DiagnosticsWebExtension(endpoint);
    }

    @Bean
    DiagnosticReportEndpoint diagnosticReportEndpoint() {
        return new DiagnosticReportEndpoint();
    }

    public record Snapshot(
            int schemaVersion,
            String state,
            long activeJobs,
            long lastRunDurationMillis,
            List<String> warnings) {
    }

    @Endpoint(id = "diagnostics")
    public static class DiagnosticsEndpoint {
        private final String state;

        public DiagnosticsEndpoint(String state) {
            this.state = state;
        }

        @ReadOperation(produces = "application/json")
        public Snapshot snapshot() {
            return new Snapshot(1, state, 3L, 42L, List.of());
        }
    }

    @EndpointWebExtension(endpoint = DiagnosticsEndpoint.class)
    public static class DiagnosticsWebExtension {
        private final DiagnosticsEndpoint endpoint;

        public DiagnosticsWebExtension(DiagnosticsEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @ReadOperation(produces = "application/json")
        public WebEndpointResponse<Snapshot> snapshot() {
            Snapshot body = endpoint.snapshot();
            int status = "READY".equals(body.state())
                    ? WebEndpointResponse.STATUS_OK
                    : WebEndpointResponse.STATUS_SERVICE_UNAVAILABLE;
            return new WebEndpointResponse<>(body, status);
        }
    }

    @WebEndpoint(id = "diagnosticreport")
    public static class DiagnosticReportEndpoint {

        @ReadOperation(produces = "text/plain;charset=UTF-8")
        public Resource report() {
            byte[] content = "status=READY\nactiveJobs=3\n"
                    .getBytes(StandardCharsets.UTF_8);
            return new ByteArrayResource(content);
        }
    }
}
```

Three `@Bean` methods register the endpoints and extension. Nested classes are used so the example fits in one file; they can be split into separate files in the same package while preserving the same responsibilities.

`DiagnosticsEndpoint` returns data; `DiagnosticsWebExtension` adds the HTTP decision. `DiagnosticReportEndpoint` produces a fixed report, independent of the `demo.state` property, making it easy to observe the `Resource` path separately. The numbers 3 and 42 are sample data, not metrics measured automatically by Actuator.

### 6.3. Compiling and Running

From the directory containing `pom.xml`, using Maven with JDK 21:

```shell
mvn clean package
java -jar target/actuator-response-demo-1.0.0.jar
```

Maven downloads dependencies if the machine does not have them yet. In this experiment, `javac DemoApplication.java` alone is not enough because the code needs Spring libraries on the classpath. Maven handles that compilation and packaging.

Open another terminal. The commands below use `curl.exe` on Windows to avoid confusion with the PowerShell alias; on other operating systems use `curl`.

```powershell
curl.exe -sS -i -H "Accept: application/json" http://127.0.0.1:18080/actuator/diagnostics
```

Relevant response parts:

```http
HTTP/1.1 200
Content-Type: application/json

{"schemaVersion":1,"state":"READY","activeJobs":3,"lastRunDurationMillis":42,"warnings":[]}
```

Other headers may appear. The JSON above describes the exact values of the sample; consumers must read by field name rather than relying on property order or whitespace.

To observe the unavailable state, stop the Java process with `Ctrl+C` and run again:

```shell
java -jar target/actuator-response-demo-1.0.0.jar --demo.state=UNAVAILABLE
```

Call the diagnostics URL again:

```http
HTTP/1.1 503
Content-Type: application/json

{"schemaVersion":1,"state":"UNAVAILABLE","activeJobs":3,"lastRunDurationMillis":42,"warnings":[]}
```

`state` is injected into the DTO from configuration. The logic inside the web extension chooses 503; neither Jackson nor the `state` field name infers the HTTP status automatically.

### 6.4. Receiving Resource Content

```powershell
curl.exe -sS -i http://127.0.0.1:18080/actuator/diagnosticreport
```

Relevant response parts:

```http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

status=READY
activeJobs=3
```

The body is `status=READY\nactiveJobs=3\n`: there are newlines after both lines, totaling **26 bytes** since all characters are ASCII. This is the resource's content, not JSON describing a `Resource` object.

To save it locally:

```powershell
curl.exe -sS -o diagnostic-report.txt http://127.0.0.1:18080/actuator/diagnosticreport
```

The name `diagnostic-report.txt` here is chosen by the caller via `-o`. It does not prove the server sent a `Content-Disposition` header, nor is it a filename that `ByteArrayResource` must have.

### 6.5. Requesting a Partial Resource

```powershell
curl.exe -sS -i -H "Range: bytes=0-5" http://127.0.0.1:18080/actuator/diagnosticreport
```

With this Spring MVC and `ByteArrayResource` sample:

```http
HTTP/1.1 206
Content-Type: text/plain;charset=UTF-8
Content-Range: bytes 0-5/26

status
```

Start position 0 and end position 5 are inclusive, giving six bytes: `status`. The actual body of this request has no trailing newline. If using `Range: bytes=100-110`, the sample returns 416 because the requested range lies outside the 26-byte resource.

Range support for endpoints returning `Resource` is documented by Actuator for Spring MVC and WebFlux; Jersey does not support it through the same mechanism. Do not extrapolate results of a reopenable resource to every kind of stream. [Range requests in Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.range-requests).

Finally, try a content type not supported by the JSON endpoint:

```powershell
curl.exe -sS -i -H "Accept: text/html" http://127.0.0.1:18080/actuator/diagnostics
```

The sample returns 406. This is a content negotiation issue, different from the 503 explicitly returned by the web extension after reading data.

## 7. Designing Resource Responses in Real Applications

### 7.1. Resource Describes How to Read Content

`Resource` is Spring's content-access abstraction. For a resource response, the HTTP handling layer needs a way to open the content to write it out to the response. Choose an implementation based on where the data resides:

| Implementation | Appropriate When | Considerations |
| --- | --- | --- |
| `ByteArrayResource` | Small content already in memory as `byte[]` | All data resides in memory |
| `FileSystemResource` | Report already exists on the filesystem | Read permissions, lifecycle, and file stability |
| `ClassPathResource` | Resource packaged with the application | Do not assume a resource inside a JAR is an ordinary `File` |
| `InputStreamResource` | Cases needing to wrap a single-use stream | Do not treat as a source that can be reread arbitrarily |

With `ByteArrayResource`, each read can open a stream over the byte array. Memory footprint grows with content size, so this pattern fits small reports. For large reports, calling `Files.readAllBytes` and wrapping it still loads the entire file into memory; changing the return type name does not eliminate that cost. [Resource Abstraction and Implementations](https://docs.spring.io/spring-framework/reference/core/resources.html).

For example, a method returning a pre-generated report can use:

```java
// Illustrative snippet in a class that already has an approvedReportPath field of type Path.
@ReadOperation
public Resource report() {
    return new org.springframework.core.io.FileSystemResource(approvedReportPath);
}
```

`approvedReportPath` in the snippet is a path determined and controlled by the application. Constructing `FileSystemResource` does not guarantee the file will still exist or remain readable when HTTP begins writing the body. The stream is opened when read, and operations like getting the length or reading the file can fail. [FileSystemResource API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/FileSystemResource.html).

If a report must be selected from input, prefer a report ID mapped to an allowlist of resources. Do not convert arbitrary path strings or URLs from callers directly into resources to read. Size limits and data-exposure restrictions still apply to file contents just as they do to JSON.

### 7.2. The Stream Must Still Be Usable When Writing the Response

Do not open a stream with `try-with-resources`, wrap it in `InputStreamResource`, and return it after the `try` block ends. By then the stream is already closed before the HTTP handler reads it.

`InputStreamResource` is single-use in nature; do not retain one instance to share across multiple requests and do not assume it supports repeated reads. When content length, seeking, or Range serving is required, the data source's capabilities must be evaluated specifically. [InputStreamResource 6.1 API](https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/core/io/InputStreamResource.html).

A reopenable resource also needs stable content. If the file is overwritten between two Range requests, the client may assemble parts from two different versions. For large reports, you can design each completed report as an immutable artifact before publishing its download ID.

### 7.3. Distinguishing Content, Filename, and HTTP Headers

The following three things are not synonymous:

1. `Resource` supplies content to read.
2. `Content-Type` indicates the format of the body.
3. `Content-Disposition` can suggest download handling and a filename to the client.

Do not assume `getFilename()` or the resource description will produce the exact download headers desired across every HTTP handler. If a specific filename, cache headers, or specialized download behavior is required, pick a web handler supporting those requirements and inspect actual headers.

Also do not mix a file-type success result with a JSON error while keeping an inappropriate fixed content type. For example, `application/octet-stream` with a JSON error body causes clients to potentially save the error as a report file. The contract must clearly describe error statuses, bodies, and content types callers need to handle.

## 8. Common Design Errors and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JSON still returns 200 despite an `error` field | Data fields do not control HTTP status | Decide success/failure semantics and use appropriate web response |
| Read operation returns 404 unexpectedly | Operation result is null or absent | Distinguish not-found from an empty list and check signature |
| Ambiguous mapping after adding web extension | Base operation and extension have mismatched mapping predicates | Compare selectors, operations, and `produces` |
| Consumer only sees a path string | Returning a `String` containing a path | If file contents are needed, supply a `Resource` from a safe source |
| JSON changes with internal object structure | Returning an object not designed for exchange directly | Create a DTO with explicitly chosen fields |
| Consumer fails parsing numbers | Same field is sometimes a number, sometimes a string | Fix the type and state the unit clearly |
| Downloaded report is empty or fails to read | Stream closed, already consumed, or reused | Control lifecycle and pick an appropriate `Resource` |
| A report request consumes too much memory | Building a byte array for a huge file | Avoid loading entire content unnecessarily; enforce size limits |
| Changed JSON config but Actuator behaves unexpectedly | Modified converter is not the one Actuator uses | Inspect Actuator's Jackson config and real responses |
| Calling JSON URL with `Accept: text/html` gets 406 | Endpoint has no acceptable representation | Use a content type supported by the endpoint |

When diagnosing, check in order: mapped URL and operation → accepted content types → value the method actually returns → HTTP handling mechanism → received JSON or bytes. Do not simply call a Java method directly and conclude the entire HTTP contract is correct.

## 9. Contract Testing Practice

Perform these on the sample application:

1. Call the JSON endpoint with `Accept: application/json`. Verify `activeJobs` is a number and `warnings` is an empty array.
2. Restart with `--demo.state=UNAVAILABLE`. Verify both HTTP 503 and `state="UNAVAILABLE"` in JSON.
3. Download the report and verify both lines plus the trailing newline. Do not parse this report as JSON.
4. Send `Range: bytes=0-5`. Verify status 206, total length 26, and the exact six bytes `status`.
5. Send an out-of-range byte range and an unsupported `Accept` type. Distinguish 416 from 406.
6. Design adding a “last run timestamp” field. Before writing code, decide the time representation, timezone, and meaning when no run has occurred yet.

Self-check your decisions:

- **When there are no warnings, should you return null?** No. Under the sample contract, `[]` expresses a known and currently empty list.
- **Does a record with a null field force a 404?** No. The DTO is still a non-null result; the whole result being null is a different case.
- **Does setting `produces="application/pdf"` generate a PDF from a DTO?** No. You must actually supply PDF bytes and an appropriate writer.
- **Does switching the report to FileSystemResource guarantee zero memory use or no I/O errors?** No. It changes the source access method; filesystem read/write costs and errors still exist.
- **Does a test calling `snapshot()` prove HTTP 503?** No. You must go through the web handler layer to test status, content type, and body together.
