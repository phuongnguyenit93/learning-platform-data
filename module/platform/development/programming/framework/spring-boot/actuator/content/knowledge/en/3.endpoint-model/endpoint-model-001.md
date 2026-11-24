# Endpoint Identity and Relationship with the /actuator Path

## 1. health Is the Identity, /actuator/health Is the Path

When calling:

~~~text
GET http://127.0.0.1:8080/actuator/health
~~~

you must distinguish the following parts:

| Component | Value in example | Meaning |
| --- | --- | --- |
| Scheme and address | `http://127.0.0.1:8080` | Where the application is receiving requests |
| Management web prefix | `/actuator` | Base path of Actuator endpoints over HTTP |
| Endpoint ID | `health` | Logical name of the health check capability |
| HTTP path | `/actuator/health` | Location to call that capability in the current configuration |

The **endpoint ID** is not the entire URL. Nor is `actuator` in the default path the ID of an endpoint that contains all other endpoints.

The default relationship can be visualized as:

~~~text
Endpoint ID: health
       +
Web base path: /actuator
       ↓
HTTP path: /actuator/health
~~~

Changing the prefix to `/manage` changes the URL, but the endpoint still has the ID `health`. The default path convention is described in [Spring Boot 3.3 — Actuator REST API URLs](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html).

The goal of this lesson is to know which part preserves the endpoint's identity, which part determines where it is accessed, and which part only selects a sub-resource.

## 2. Which Capabilities Do Endpoint IDs Identify?

Common IDs:

| ID | Identified capability | Default root path over HTTP |
| --- | --- | --- |
| `health` | Application health | `/actuator/health` |
| `info` | Contributed application information | `/actuator/info` |
| `metrics` | Query registered metrics | `/actuator/metrics` |
| `loggers` | View or adjust log levels | `/actuator/loggers` |

The URLs only exist when the application has the corresponding component and the endpoint is exposed over HTTP.

### 2.1. An ID Is Not a Class Name, Bean Name, or Method Name

In a custom endpoint built with the Actuator model, `@Endpoint(id = "runtimeinfo")` declares the logical ID. The class name can be different, the bean name can be different, and the operation method name can also be different.

The `@Endpoint` annotation and its operations are adapted to the technology that exposes the endpoint externally, such as HTTP or JMX. Therefore, an ID should not contain a hostname, port, or a path tied to a specific deployment. See [Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

A regular controller with `@GetMapping("/actuator/runtimeinfo")` does not automatically become an Actuator endpoint just because it uses the same prefix. You must distinguish the endpoint model from a URL character string.

### 2.2. ID Naming Rules and Legacy Name Compatibility

For new IDs, use names starting with a lowercase letter and consisting of letters and digits, such as `runtimeinfo` or `buildstatus`. Do not use `/health` or `/actuator/health` as an ID.

The `EndpointId` documentation specifies alphanumeric IDs starting with a lowercase letter. The ID comparison mechanism also performs normalization; that is not a guarantee that every HTTP URL will automatically ignore case or other characters. See [EndpointId API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/EndpointId.html).

There is a compatibility detail to know when reading legacy systems: the Boot 3.3.0 source code still accepts some IDs containing dots or hyphens and logs a warning. Therefore, you should not claim that all such legacy names always cause an immediate startup failure. Nor should you treat this compatibility behavior as the rule for naming new IDs. Compare with [EndpointId 3.3.0 source code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/EndpointId.java).

## 3. Path Prefix and Per-Endpoint Mapping

### 3.1. Changing the Base Path for the Whole Group

Properties configuration:

~~~properties
management.endpoints.web.base-path=/manage
~~~

Equivalent YAML:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

With an application using port 8080 and no other base path:

~~~text
ID health → http://127.0.0.1:8080/manage/health
ID info   → http://127.0.0.1:8080/manage/info
~~~

The ID does not change. Per-ID configuration properties such as `management.endpoint.health.show-details` still use the word `health`, not `manage`.

### 3.2. Changing the Path of a Single ID

You can configure:

~~~properties
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.health=status
~~~

Or:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: status
~~~

Result for the `health` endpoint:

~~~text
ID: health
Base path: /manage
Replacement path for ID health: status
HTTP path: /manage/status
~~~

`status` is the replacement path segment, not a new ID. The `info` endpoint is not changed along with it: it remains at `/manage/info` if available.

In this configuration, `/manage/health` is not implicitly an alias that remains active. Without additional mappings, the original path has been replaced by the new path.

### 3.3. Placing an Endpoint Directly Under the Root Path

Example:

~~~properties
management.endpoints.web.base-path=/
management.endpoints.web.path-mapping.health=healthcheck
~~~

Provided there is no other context path:

~~~text
ID health → /healthcheck
~~~

Not `/actuator/healthcheck`, and not `/health/healthcheck`.

The `base-path` and `path-mapping` properties are described in [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 3.4. Quick Reference Table

Assuming the same host/port and no additional context path:

| Base path | Path mapping for health | Health path | ID used in configuration |
| --- | --- | --- | --- |
| `/actuator` | Not configured | `/actuator/health` | `health` |
| `/manage` | Not configured | `/manage/health` | `health` |
| `/manage` | `status` | `/manage/status` | `health` |
| `/` | `healthcheck` | `/healthcheck` | `health` |

Read the table in two steps: choose the root location for the group, then choose the path segment for the endpoint. Do not append the ID again if it has already been replaced by a path mapping.

## 4. Configure by ID, Not by the Remapped URL

Suppose you have remapped `health` to `/manage/status`. To expose this endpoint over HTTP, you still write:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Do not change `include` to `status` just because you are calling a URL containing the word `status`. Also do not use `/manage/status` as an `include` entry.

You can separate three concerns:

~~~text
ID health
├── is enabled / meets creation conditions?
├── is in the set of endpoints exposed over HTTP?
└── is mapped to which path?
~~~

After that, a request to that path is also subject to access policies.

In Boot 3.3.x:

- `management.endpoint.health.enabled` controls enabling the `health` endpoint.
- `management.endpoints.web.exposure.include` and `exclude` select which IDs are exposed over the web.
- `management.endpoints.web.path-mapping.health` selects the replacement HTTP path segment.

Changing the path does not automatically re-enable a disabled endpoint, does not add missing libraries, and does not grant permissions to callers. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

A URL returning 404 is not enough to conclude that an endpoint ID is invalid. You might be calling the old prefix, the wrong port, missing exposure, or the component might not have been created.

## 5. One Endpoint Can Have Multiple Sub-Paths

### 5.1. Health and Health Components

The two paths:

~~~text
/actuator/health
/actuator/health/db
~~~

both belong to endpoint ID `health`. The `db` part selects a health component when that component exists and is accessible according to configuration.

Do not declare `health/db` as a separate ID in `include`. Nor should you assume every application has a `db` component. See [Spring Boot 3.3 — Health REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 5.2. Metrics and Metric Names

Example:

~~~text
/actuator/metrics
/actuator/metrics/jvm.memory.used
~~~

The ID is `metrics`. `jvm.memory.used` is the selected metric name, not a new endpoint ID.

Therefore, dots in a metric name do not conflict with the ID naming rules. The two strings serve two different roles. A query parameter such as `?tag=area:heap` further filters the data of that operation; it also does not change the ID. See [Spring Boot 3.3 — Metrics REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 5.3. Loggers and Operations on the Same Resource

Example:

~~~text
GET  /actuator/loggers/com.example
POST /actuator/loggers/com.example
~~~

Both belong to ID `loggers`. The `com.example` part selects the logger, while the HTTP method distinguishes a read operation from a configuration change.

Having one endpoint ID does not mean that endpoint only has a single URL or only supports a single HTTP method. Read the contract of the specific operation. See [Spring Boot 3.3 — Loggers REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 6. /actuator Can Also Be a Link Discovery Page

### 6.1. The Base Path Differs from the health Endpoint

When discovery is enabled in a typical configuration:

~~~text
GET /actuator        → link document pointing to web-exposed endpoints
GET /actuator/health → health check result
~~~

The link document usually has a `_links` field. Simplified structure for illustration:

~~~json
{
  "_links": {
    "self": {
      "href": "http://127.0.0.1:8080/actuator"
    },
    "health": {
      "href": "http://127.0.0.1:8080/actuator/health"
    }
  }
}
~~~

This is not the entire fixed response: there may also be other links, a `templated` flag, or addresses computed based on the environment.

Merely opening `/actuator` does not mean you are performing a health check. To read health status, follow the appropriate link.

### 6.2. After Changing the Path, Follow the Actual Link

With base path `/manage` and mapping `health=status`, the discovery document at `/manage` may contain a `health` link pointing to `/manage/status`.

The relation name `health` in the document and the path containing `status` can differ while still remaining consistent. The link resolver works with the corresponding endpoints and paths; see [EndpointLinksResolver API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.html).

External tools should be configured with the actual address rather than always assuming every application has `/actuator/health`.

### 6.3. Disabling Discovery Does Not Mean Disabling Endpoints

The configuration:

~~~properties
management.endpoints.web.discovery.enabled=false
~~~

removes the link document. With other conditions unchanged, `health` can still work at `/actuator/health`.

When the base path is `/`, Boot disables discovery to avoid mapping conflicts at the root path. That does not make a `health` endpoint mapped to `/healthcheck` disappear.

Therefore, do not use the fact that `GET /actuator` or `GET /` has no link document alone to conclude that all Actuator endpoints have stopped working.

## 7. Port and Context Path Complete the URL

### 7.1. Sharing the Same Port with a Servlet Application

Suppose:

~~~properties
server.port=8080
server.servlet.context-path=/shop
management.endpoints.web.base-path=/manage
~~~

When not using a separate management port, `health` has the path:

~~~text
http://127.0.0.1:8080/shop/manage/health
~~~

Here:

~~~text
Application context path: /shop
Actuator base path:       /manage
Endpoint segment:         health
~~~

`shop` is not an Actuator ID, and `/shop` does not need to be added to `include`.

### 7.2. Using a Separate Management Port

If configured with:

~~~properties
server.port=8080
management.server.port=8081
management.server.address=127.0.0.1
management.endpoints.web.base-path=/manage
~~~

and without an additional management base path, `health` is located at:

~~~text
http://127.0.0.1:8081/manage/health
~~~

When a separate management port is used, management paths are evaluated relative to the management server, and `server.servlet.context-path` of the main application port is not prepended to that URL by default. If `management.server.base-path` is configured, that segment must be included as well.

This is why you need to know the port configuration before combining path segments. There is no single formula that always concatenates every path property from both servers.

### 7.3. Behind a Reverse Proxy

The URL seen by a user or tool may also be affected by routing or path rewriting in a proxy. You must distinguish the external URL from the path the application receives.

Changing a prefix outside the proxy does not change the endpoint ID inside Spring Boot. When diagnosing, state clearly whether you are calling the application directly or going through a proxy to avoid comparing two addresses from different layers.

## 8. Experimenting with health: Change the Path, Keep the ID

The example uses a Spring Boot **3.3.0** project, JDK **21**, with dependency version management, Gradle wrapper, and the `bootRun` task already set up. The Java code uses syntax compatible with Java 17 and later.

The project uses only Web and Actuator, with no Spring Security, no context path, and no separate management port. These assumptions help isolate path mapping behavior.

### 8.1. Dependencies and Startup Code

Add the dependencies section to the existing `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Create `src/main/java/example/endpointidentity/EndpointIdentityApplication.java`:

~~~java
package example.endpointidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointIdentityApplication.class, args);
    }
}
~~~

There is no need to write a custom health controller. The Actuator library provides the corresponding capability when configuration conditions are met.

In `src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Run only one instance of the application at a time. After changing the arguments below, stop the previous process and start it again.

### 8.2. Run A: Default Path Configuration

~~~powershell
.\gradlew.bat bootRun
~~~

In another window:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/actuator/health
~~~

When existing health checks are healthy, the expected HTTP code is 200; minimal body:

~~~json
{"status":"UP"}
~~~

This is the HTTP response body, not stdout printed by `main`. Response headers and startup logs are not fixed strings.

You can view discovery at:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/actuator
~~~

### 8.3. Run B: Changing the Prefix

Stop the application and run:

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.base-path=/manage"
~~~

Address to call:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/manage/health
~~~

With this exact example and no other mappings:

| Path | Expected result |
| --- | --- |
| `/manage/health` | 200 when health is UP |
| `/manage` | Discovery document |
| `/actuator/health` | 404 |

The identity is still `health`. Neither the endpoint name nor the data it returns has changed.

### 8.4. Run C: Replacing Only the health Path Segment

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.health=status"
~~~

After the application starts:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/manage/status
~~~

The expected result is still health 200/UP when checks are healthy.

| Path | Expected result |
| --- | --- |
| `/manage/status` | Health |
| `/manage/info` | Info if available |
| `/manage/health` | 404 |
| `/actuator/health` | 404 |

The `include` configuration in the base file is still `health,info`. Do not change it to `status,info`.

YAML format if you want to save this mapping configuration permanently:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
      path-mapping:
        health: status
  endpoint:
    health:
      show-details: never
~~~

Merge this snippet into the project's configuration in a chosen format; do not create two duplicate `management` blocks in the same file.

### 8.5. Run D: Base Path Is a Slash

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.base-path=/ --management.endpoints.web.path-mapping.health=healthcheck"
~~~

Call:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/healthcheck
~~~

Health can still return 200/UP. `GET /` has no Actuator discovery document in this configuration. With no other controller or static page, the root path of the example returns 404.

### 8.6. Run E: Disabling Discovery Only

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.web.discovery.enabled=false"
~~~

In this run, do not pass the `base-path`/`path-mapping` arguments from previous runs:

~~~text
/actuator/health → health still works
/actuator        → no discovery document
~~~

To inspect only the status code:

~~~powershell
curl.exe --silent --show-error --output NUL --write-out "%{http_code}" http://127.0.0.1:8080/actuator
~~~

Expected output in the example is:

~~~text
404
~~~

Use `curl.exe` to avoid differences with the `curl` alias in some Windows PowerShell environments.

## 9. Checks When Tools Still Call the Old Address

Changing the base path or path mapping may require updating places that store URLs, such as health checkers, monitoring configurations, or operational runbooks.

A short checklist:

1. Record the desired ID, for example `health`.
2. Verify whether the endpoint is exposed over HTTP and accessible under the current policy.
3. Determine the actual management port.
4. Compute the context/base path appropriate for the server in use.
5. Check the `path-mapping` for that ID.
6. If discovery is enabled, check the actual links.
7. If there is a proxy, compare the external path with the path received by the application.

Changing a path is not an authentication mechanism. Security rules hardcoded to `/actuator/**` must be reviewed when the prefix changes.

In a Servlet application using Spring Security, `EndpointRequest` helps build matchers for Actuator endpoint locations instead of relying only on a fixed prefix string. Using the matcher still requires complete authorization rules for all other URLs as well. See [EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

## 10. Misconceptions to Avoid

| Misconception | Accurate understanding |
| --- | --- |
| `actuator` is the ID of health | `actuator` is the default web prefix; `health` is the ID |
| Changing `/actuator` to `/manage` changes all IDs | It only changes the root location over HTTP |
| Mapping `health` to `status` means `include` must use `status` | `include` still selects the ID `health` |
| The old path automatically remains active as an alias | There is no such guarantee unless additional mappings are configured |
| Every sub-path is a new endpoint ID | Sub-resources can belong to the same endpoint |
| Dots in `jvm.memory.used` violate `EndpointId` rules | That is a metric name, not an endpoint ID |
| No discovery means no health | The two mappings serve two different purposes |
| One endpoint ID only has one HTTP method | Operations of the same endpoint can use different methods |
| Just prepend the application's context path to every URL | A separate management port has its own path rules |
| Changing the URL makes an endpoint automatically safer | Access permissions and network routes must be checked separately |

### Self-Practice

1. With base path `/ops` and mapping `health=ready`, identify the health URL and the `include` value to use.
2. Break down `/actuator/metrics/jvm.memory.used` into prefix, endpoint ID, and selected target.
3. Disable discovery and predict the results for `/actuator` and `/actuator/health`.
4. Sharing port 8080, Servlet context path `/shop`, and base path `/ops`: where is `health` located when there is no path mapping?
5. When a health checker still calls `/actuator/health` after changing the base path, list the places to check before concluding the application is broken.

**Reference hints:** question 1 has path `/ops/ready` while the ID remains `health`; question 2 has ID `metrics`; question 3 requires separating discovery and operation; question 4 is `/shop/ops/health`. Always distinguish an endpoint's identity from the access location of a specific deployment.
