# Exploring the Discovery Page and Links Between Endpoints

## 1. What Problem Does the Discovery Page Solve?

When operating an application, you need to know which management addresses the application is exposing: where to check health, where to view application info, and where to read the list of metrics. If you assemble every URL from memory, a change to the port or path can cause inspection tools to call the wrong address.

The discovery page is an HTTP entry point that returns a JSON document containing links to Actuator endpoints exposed over the web. By default, this entry point is `GET /actuator`. From there, callers read the relation name and use the URL in `href`.

Think of the discovery page like a directory board in a building: the board tells you where each room's door is; to see what is inside a room and whether you are allowed in, you still have to go to the right door.

In this lesson, you will learn in order:

1. Read the `_links` structure and understand the relationship between endpoint, operation, and link.
2. Call the discovery page and follow the `health` and `metrics` links.
3. Distinguish ready-to-use URLs from templated URLs that require filling parameters.
4. Observe links when changing paths, changing exposure scope, or disabling discovery.
5. Diagnose situations where a link exists yet calling the endpoint fails.

The example scope is Spring Boot **3.3.13**, Spring MVC application, JDK 21. The discovery page here is not a service registry and discovery mechanism like Eureka or Consul, nor is it a Swagger UI.

## 2. How Are Endpoints, Operations, and Links Related?

These three concepts sit at three different levels:

| Concept | Meaning | Example |
| --- | --- | --- |
| Endpoint | A management capability with its own ID | `health`, `metrics` |
| Operation | An action provided by the endpoint | Reading the list of metric names; reading one metric by name |
| Link | An advertised address for callers to locate a resource or operation | `metrics`, `metrics-requiredMetricName` in `_links` |

One endpoint can produce multiple links. For example, the `metrics` endpoint has a path to read the list of metric names and a path to read a specific metric. Therefore, **the number of entries in `_links` is not the number of endpoints**.

In Spring Boot 3.3.13, `EndpointLinksResolver` adds the `self` link, then collects links from the supplied set of endpoints; for web endpoints, it iterates through operations to generate links. This is why both a root link and a parameterized link appear for the same endpoint. [EndpointLinksResolver 3.3.13 source code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java).

The document shape we will read:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://localhost:8080/actuator/health",
      "templated": false
    },
    "health-path": {
      "href": "http://localhost:8080/actuator/health/{*path}",
      "templated": true
    },
    "info": {
      "href": "http://localhost:8080/actuator/info",
      "templated": false
    },
    "metrics": {
      "href": "http://localhost:8080/actuator/metrics",
      "templated": false
    },
    "metrics-requiredMetricName": {
      "href": "http://localhost:8080/actuator/metrics/{requiredMetricName}",
      "templated": true
    }
  }
}
```

This is the response structure of the example below when called via `localhost:8080`; JSON key order has no significance and may vary.

How to read it:

- `_links`: object containing the links.
- `self`: link pointing back to the discovery document itself.
- `health`, `info`, `metrics`: relation names used to select links.
- `href`: address of the link.
- `templated: false`: URL has no template variables left to substitute.
- `templated: true`: this is a URI template; appropriate variables must be filled in before sending a request.

The relation name does not always match a URL segment. After changing the path of `health` to `alive`, the relation can still be named `health`, while `href` points to the new path.

## 3. Preparing a Standalone Application

This example is a small Maven project, independent of a repository's custom build conventions. Requires JDK 21, Maven 3.6.3 or higher, port 8080 free, and network connectivity for the first dependency download.

File structure:

```text
actuator-discovery-demo/
  pom.xml
  src/main/java/example/discovery/DiscoveryApplication.java
  src/main/resources/application.yml
```

File `pom.xml`:

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
  <artifactId>actuator-discovery-demo</artifactId>
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

File `src/main/java/example/discovery/DiscoveryApplication.java`:

```java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryApplication.class, args);
    }
}
```

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
```

`spring-boot-starter-web` provides the HTTP environment and JSON conversion; `spring-boot-starter-actuator` provides the management capabilities. No custom controller is needed for `/actuator`. This project does not include Spring Security, so requests in the hands-on steps require no credentials.

In the directory containing `pom.xml`, package and run:

```shell
mvn -q package
java -jar target/actuator-discovery-demo-1.0.0.jar
```

Maven compiles and packages along with the required libraries; running `javac DiscoveryApplication.java` alone is not enough because this class depends on Spring Boot. Keep the process running in one window and send HTTP requests from another window. Use `Ctrl+C` to stop before restarting with another configuration.

Startup logs contain version and port information; timestamps, PID, and startup duration vary by machine. Do not use the full log as a fixed output for comparison.

## 4. Reading the Discovery Page and Following Links

### 4.1. Observing the HTTP Response

In a terminal with cURL:

```shell
curl -i -H "Accept: application/json" http://localhost:8080/actuator
```

On Windows PowerShell, you can use `curl.exe` to avoid confusion with the `curl` alias in some PowerShell versions.

In the sample application, a successful request returns HTTP 200 with JSON containing `_links` as in section 2. Without specifying `Accept`, the response may carry an Actuator media type such as `application/vnd.spring-boot.actuator.v3+json`; it is still a JSON document.

Read both the status code and the content. A redirected HTML login page is not a discovery document, even if a browser still renders content.

### 4.2. Following Links with PowerShell

Run the following snippet in PowerShell after the application has started:

```powershell
$entry = 'http://localhost:8080/actuator'
$index = Invoke-RestMethod -Uri $entry -Headers @{ Accept = 'application/json' }

$healthLink = $index._links.health
if ($null -eq $healthLink) {
    throw 'Discovery page does not have a health link.'
}
if ($healthLink.templated -eq $true) {
    throw 'Must process the URI template before calling.'
}

$healthUri = [uri]$healthLink.href
if ($healthUri.Authority -ne ([uri]$entry).Authority -or
    $healthUri.Scheme -ne ([uri]$entry).Scheme) {
    throw 'Link does not share the trusted base address.'
}

$health = Invoke-RestMethod -Uri $healthUri.AbsoluteUri
$health.status
```

With the sample application healthy, the last line prints:

```text
UP
```

Here, the `health` address is obtained from the response. The caller only needs to know the starting address and the relation to look up. When the endpoint path changes, the `href` lookup continues to work once the starting address is updated appropriately.

Checking the base address in the snippet is an appropriate choice for an example running on one machine. A tool used in a production system may allow a list of trusted addresses; you should not automatically forward credentials to a link pointing to an arbitrary host.

The Health documentation describes `status` and the details sections that may appear. `UP` is the expected result for the healthy example, not a value every application always returns. [Health API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 4.3. Do Not Assume Every Response Contains Links

Calling `health` in the example returns health data, typically just:

```json
{"status":"UP"}
```

There is no mandatory rule that this response must contain `_links.metrics` or a link back to the discovery page. To move from checking health to reading metrics, the caller can reuse the discovery document already fetched.

The relationship here is **navigation from the entry point to management capabilities**. It does not mean `health` calls `metrics`, does not prove the two endpoints depend on each other, and does not produce a business dependency graph.

## 5. Understanding and Using Templated URLs

The `metrics-requiredMetricName` link in the example has the form:

```text
http://localhost:8080/actuator/metrics/{requiredMetricName}
```

This is not yet the URL of a specific metric. The `requiredMetricName` variable must be replaced with an actual metric name.

First, fetch the list of names from the `metrics` link:

```powershell
$metricsLink = $index._links.metrics
if ($null -eq $metricsLink) {
    throw 'Discovery page does not have a metrics link.'
}

$metrics = Invoke-RestMethod -Uri $metricsLink.href
$metricName = 'jvm.memory.used'
if ($metricName -notin $metrics.names) {
    throw 'The application has not registered the jvm.memory.used metric.'
}
```

Then fill in the URI template:

```powershell
$metricLink = $index._links.'metrics-requiredMetricName'
if ($null -eq $metricLink -or $metricLink.templated -ne $true) {
    throw 'Metrics URI template not found as in the example.'
}

$metricUri = $metricLink.href.Replace(
    '{requiredMetricName}',
    [uri]::EscapeDataString($metricName)
)

$metric = Invoke-RestMethod -Uri $metricUri
$metric.name
```

Result of the last line in the example:

```text
jvm.memory.used
```

The numbers in `measurements` fluctuate as the application runs; do not assign a fixed memory value for every run. The mechanism for reading the list of names and reading a metric by name is described in [Metrics API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Points to understand from the example:

- Relation keys containing hyphens should be accessed with `$index._links.'metrics-requiredMetricName'`.
- The `Replace` snippet only handles the known single-variable template in this lesson; it is not a general-purpose URI Template processor.
- Check `templated` before calling. Do not send literal curly braces to the server or expect cURL to fill variables automatically.
- The list of metric names resides in the `metrics` endpoint data; the discovery page does not advertise a separate link for every metric.

With `health-path`, the `{*path}` template can represent multiple path segments. Do not mechanically apply the single-segment encoding used for `requiredMetricName` to all such cases. Query only health components or groups that actually exist and are permitted to be viewed; the presence of the template does not guarantee every value you supply is valid.

In the 3.3.13 codebase, the operation reading one metric has a selector parameter named `requiredMetricName`; the operation reading health by path uses a selector accepting the remaining segments. The templates above reflect those operations. [MetricsEndpoint](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/MetricsEndpoint.java), [HealthEndpointWebExtension](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointWebExtension.java).

## 6. How Do Links Change When Addresses Change?

### 6.1. Changing the Base Path and One Endpoint's Path

Stop the application, then run again:

```shell
java -jar target/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.health=alive
```

Now:

| Component | Before | After |
| --- | --- | --- |
| Discovery page | `/actuator` | `/manage` |
| Health path | `/actuator/health` | `/manage/alive` |
| Relation used to find health | `health` | `health` |

Read the document again from the new starting address:

```powershell
$entry = 'http://localhost:8080/manage'
$index = Invoke-RestMethod -Uri $entry
$index._links.health.href
```

The last line prints:

```text
http://localhost:8080/manage/alive
```

Thus, a caller that manually concatenates `$entry + '/health'` will use the wrong path, whereas a caller reading `_links.health.href` gets the mapped address.

The endpoint ID remains `health`; the `exposure.include` list continues to use `health`, not `alive`.

### 6.2. Context Path and Management Port

The table below describes **independent** configurations, each row starting from the initial sample application:

| Additional startup configuration | Discovery address |
| --- | --- |
| None added | `http://localhost:8080/actuator` |
| `--server.servlet.context-path=/demo` | `http://localhost:8080/demo/actuator` |
| `--management.server.port=8081` | `http://localhost:8081/actuator` |
| `--management.server.port=8081 --management.server.base-path=/ops --management.endpoints.web.base-path=/manage` | `http://localhost:8081/ops/manage` |

When sharing the same port in a Servlet application, the endpoint base path is relative to `server.servlet.context-path`. When using a separate management port, it is relative to `management.server.base-path`. Therefore, do not prepend the main application's context path to the management URL by default. [Monitoring and Management over HTTP 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-endpoint-paths).

Discovery helps find paths beyond the entry point; the starting address, port, and network connectivity permissions to the management network must still come from deployment configuration.

### 6.3. Case Where Base Path Equals `/`

With Spring MVC 3.3.13, distinguish:

- Sharing **the same port** with `management.endpoints.web.base-path=/`: discovery is not registered at root to avoid conflicts with other mappings. Endpoints like `/health` can still work.
- Using a **separate management port**: the discovery mapping at the management side's root can still be registered if `management.endpoints.web.discovery.enabled=true`.

In the sample application with no root controller, the first case causes `GET /` to return `404` while `GET /health` still succeeds. With management port 8081 and base path `/`, the entry point on the management side is `http://localhost:8081/`.

The overview documentation describes disabling discovery when the root path is `/`; the condition in Spring MVC 3.3.13 code is more specific: discovery is enabled and there is a non-empty base path **or** the management port differs from the application port. When applying this edge case, check the exact version and web stack in use. [shouldRegisterLinksMapping condition in Spring MVC 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/servlet/WebMvcEndpointManagementContextConfiguration.java).

## 7. Why Does a Link Appear or Disappear?

In Boot 3.3, separate three questions:

1. Does that management capability exist and is it enabled?
2. Is it exposed over HTTP?
3. Does the caller have permission to make that request?

By default only `health` is exposed over HTTP. The example intentionally added `info` and `metrics` so you have multiple links to observe. If you add:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
        exclude: metrics
```

then `exclude` beats `include`: discovery no longer advertises web links for `metrics`. You cannot use discovery to see endpoints that are only exposed over JMX. Endpoint enablement and web exposure are two separate settings. [Endpoint exposure in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

A regular business controller such as `GET /orders` does not appear on the discovery page just because it resides in the same application. Actuator discovery has its own management scope.

Conversely, **having a link does not mean you are authorized to call it**. Links are generated from the server-side endpoint set; do not treat them as a per-user personalized permission list. A subsequent request may still hit `401` or `403` due to security configuration.

Similarly, `href` does not fully describe the HTTP method, request content type, or execution conditions of an operation. For endpoints with state-changing operations, read the API contract before using them; do not assume every link works with `GET`.

## 8. Does Disabling Discovery Make Endpoints Disappear?

Stop the application and restart from the sample configuration:

```shell
java -jar target/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.discovery.enabled=false
```

Try two requests:

```shell
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/health
```

In this exact sample application:

| Request | Expected result | Explanation |
| --- | --- | --- |
| `GET /actuator` | 404 | Discovery mapping is gone |
| `GET /actuator/health` | 200 and status `UP` when healthy | Health endpoint is still enabled and exposed |

This setting turns off the directory board; it does not alter individual endpoint configurations. Therefore, disabling discovery cannot replace access control or endpoint exposure scope. The property is described in [Hypermedia for Actuator Web Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.hypermedia).

## 9. Diagnosing Common Errors

| Symptom | What to check |
| --- | --- |
| Discovery returns 404 while `health` works directly | Check `discovery.enabled`, base path `/`, context path, and management port |
| `metrics` missing from `_links` | Check whether the endpoint is created, enabled, exposed over web, or excluded |
| `metrics` present but missing desired metric name | Read the endpoint's `names`; metrics depend on what the application registered |
| Calling URL with literal `{requiredMetricName}` returns error | Read `templated`, fill variable with valid name, and encode value per URI position |
| Link exists yet returns 401 or 403 | Check authentication credentials and authorization rules; do not conclude endpoint is unexposed |
| Calling discovery returns HTML | Check login redirect or whether you are calling the wrong application/proxy page |
| `href` has internal scheme, host, or prefix behind reverse proxy | Check proxy and application forwarding headers config; test via the URL callers actually use |
| Changed `health` path to `alive` and cannot find `alive` relation | Look up by relation `health`; path in `href` and relation name play different roles |

Status codes are clues to investigate, not absolute proof of a single cause: proxies or custom security rules can alter responses.

When diagnosing, proceed in order: check starting address → check status code and content type → confirm JSON has `_links` → find relation → process URI template if any → call endpoint → read result per that endpoint's contract.

## 10. Exercises to Verify Understanding

Start each exercise from the sample application, stopping the previous process before restarting to avoid mixing configurations between exercises.

1. **Change how URLs are found:** call discovery, read `_links.health.href`, and check health without manually concatenating `'/health'`. The takeaway to explain is that you pick a relation and follow the address the server provides.
2. **Count the right objects:** expose `health,info,metrics`, compare the three endpoints with the keys in `_links`. Explain the difference using `self` and templated-URL operations; do not treat each key as an independent endpoint.
3. **Change paths:** set base path `/manage` and map `health` to `alive`. Update only the entry point in the discovery-reading snippet, then confirm the `health` relation leads to `/manage/alive`.
4. **Try a URI template:** fetch the list of metric names, pick an existing name, fill the `metrics-requiredMetricName` template, and read the `name` field. Explain why `measurements` values are not fixed across runs.
5. **Separate discovery from endpoints:** disable discovery, then test `/actuator` and `/actuator/health` separately. State clearly that a `404` on the directory board does not prove the health endpoint is disabled.
6. **Change exposure scope:** add `exposure.exclude=metrics` while `include` still contains `metrics`. Confirm `metrics` links disappear and explain the precedence order.

After these exercises, you should be able to explain why callers still need to know the entry point, why reading `href` is better than assembling URLs, and why finding an address is not enough to conclude a request to that address will succeed.
