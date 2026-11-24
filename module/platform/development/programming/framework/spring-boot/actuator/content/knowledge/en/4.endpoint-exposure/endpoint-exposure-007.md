# Configuring the Discovery Page and Limiting Endpoint Discovery Scope

When operating an application, callers need to know where management endpoints are exposed. Actuator's **discovery page** provides those links at a root address. With the default path configuration, a `GET /actuator` request returns JSON containing a `_links` field.

The goal of this article is to configure the address and presence of this page, select which endpoints can appear in the link set, and understand the limits of "hiding the discovery page."

This article applies to **Spring Boot 3.3.x**. The runnable example uses **Spring Boot 3.3.13, Spring MVC, Java 21, and Gradle 8.5**. Details regarding a separate port and root path are verified against the source code of this exact version.

## 1. What Does the Discovery Page Help Callers Discover?

A program can call Actuator's root address, read `_links`, and then follow the appropriate link. Using links to guide subsequent operations is called **hypermedia**.

The example below illustrates the structure, keeping only two links `self` and `info`, rather than representing the full response:

```json
{
  "_links": {
    "self": {
      "href": "http://127.0.0.1:8087/actuator",
      "templated": false
    },
    "info": {
      "href": "http://127.0.0.1:8087/actuator/info",
      "templated": false
    }
  }
}
```

Components to understand:

| Component | Meaning |
| --- | --- |
| `_links` | Set of links returned by the discovery page |
| `self` | Link to the discovery page itself |
| Relation name, e.g., `info` | Key to identify the link to the related operation |
| `href` | Address or address template of the link |
| `templated` | Indicates whether the address is a template requiring parameter substitution |

The link set may also include operations using parameterized paths. Therefore, the number of keys in `_links` is not always equal to the number of endpoints plus one.

In the default implementation, `EndpointLinksResolver` builds links from the set of provided web endpoints and the request URL. This page does not scan the network, does not list all business controllers, and does not generate a catalog of JMX MBeans. [Link Resolution Mechanism in Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java)

"Page" here can be understood as a JSON resource for discovery; there does not need to be an HTML UI or Swagger UI.

## 2. Enabling or Disabling the Discovery Page

The controlling property is:

```properties
management.endpoints.web.discovery.enabled=true
```

The default value is `true`. It can be written in YAML:

```yaml
management:
  endpoints:
    web:
      discovery:
        enabled: true
```

To stop registering the discovery page:

```properties
management.endpoints.web.discovery.enabled=false
```

The property resides under `management.endpoints.web` because it configures the behavior of the web endpoint group. Do not use `management.endpoint.discovery.enabled`, and do not add an ID `discovery` to `exposure.include` to enable the page.

A value of `true` still needs to combine with appropriate path-mapping registration conditions. Section 5 explains the case of the root path `/`. [Discovery Property in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

### 2.1. Disabling Discovery Does Not Disable the Underlying Endpoints

In Spring MVC, Actuator registers endpoint operations and the links-page mapping through two separate branches. The discovery flag decides whether to register the links mapping.

Therefore, if `info` is still exposed, `discovery.enabled=false` can cause:

- `GET /actuator` is no longer handled by the discovery handler.
- `GET /actuator/info` is still handled by the `info` endpoint.

The specific HTTP code also depends on controllers, resources, and filters in the application. With the minimal project in this article, the two requests above yield expected results `404` and `200`, respectively. [How Endpoint Handlers and Links Handlers Are Registered](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/AbstractWebMvcEndpointHandlerMapping.java)

## 3. Selecting the Scope of Discoverable Endpoints

Three configuration layers must be distinguished:

| Decision layer | Mechanism | Effect |
| --- | --- | --- |
| Endpoint activity | `management.endpoint.<id>.enabled` | Enables or disables the endpoint |
| HTTP exposed set | `management.endpoints.web.exposure.include/exclude` | Selects endpoints exposed over HTTP |
| Link-providing page | `management.endpoints.web.discovery.enabled` | Enables or disables the links page at the root path |

In normal auto-configuration, the selected set of web endpoints is the input for link generation. To narrow that set, use the exposure lists:

```yaml
management:
  endpoints:
    web:
      discovery:
        enabled: true
      exposure:
        include:
          - health
          - info
```

When `health` and `info` are enabled, eligible, and there are no custom filters, the discovery page can provide the corresponding links.

If you add:

```properties
management.endpoints.web.exposure.exclude=info
```

then `info` is excluded from the HTTP exposed set, even if that ID remains in `include`. Its link is also no longer in the default discovery page.

The lists contain **endpoint IDs**, such as `health`, not paths like `/actuator/health`. `exclude` takes precedence when overlapping with `include`. [Endpoint Enablement and Exposure Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

### 3.1. Limiting the Exposed Set Differs from Only Removing the Links Page

Two intents lead to two different choices:

- Want tools to still call endpoints directly, without using the links page: set `discovery.enabled=false`.
- Want an endpoint to stop being served over Actuator HTTP: exclude it with the appropriate exposure configuration.

If an endpoint needs to be disabled globally, use the endpoint's `enabled` property, taking auto-configuration conditions into account. Discovery relates only to the web channel's discovery page.

There is no standard configuration list like `discovery.include` to create a "small catalog" independent of the exposed set in this article. If a product requirement calls for a separate catalog while keeping all endpoints behind it, that is a custom design that must be distinguished from built-in Actuator configuration.

### 3.2. Do Not Use Link Count to Assert Security

A page with few links does not prove other paths are blocked. A page that is no longer served also does not prove direct endpoints have disappeared.

To verify the result, observe both:

1. What the discovery page returns and which link relations it contains.
2. Whether direct requests to the target endpoint are still processed.

## 4. Setting the Address for the Discovery Page

### 4.1. Changing Actuator's Base Path

```properties
management.endpoints.web.base-path=/manage
```

With an application using the same port and no other context path set:

| Resource | Default address | After changing base path |
| --- | --- | --- |
| Discovery page | `/actuator` | `/manage` |
| `info` endpoint | `/actuator/info` | `/manage/info` |

The discovery page follows Actuator's root; by default it is not located at `/manage/discovery`.

If a servlet application has `server.servlet.context-path=/app` and still shares the port, the addresses above also carry the `/app` prefix. For instance, discovery becomes `/app/manage`.

### 4.2. Using a Separate Management Port

You can configure:

```properties
server.port=8087
management.server.port=9087
management.server.address=127.0.0.1
management.endpoints.web.base-path=/manage
```

When there is no additional management prefix, the discovery page is located at:

```text
http://127.0.0.1:9087/manage
```

With a separate management port, the endpoint base path is resolved relative to `management.server.base-path`. When sharing the port, it is resolved relative to the servlet application's context path. Both the port and all prefixes must be identified when locating the discovery page. [HTTP Management Path and Port](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

Moving to another port separates the management access point; who can connect to that port still depends on listening address, networking, and security rules.

## 5. Special Case: Base Path Is `/`

The 3.3 reference documentation describes disabling discovery when the management path is `/` to avoid conflicts with other mappings. When reading this rule, you must also consider **shared port versus separate port**.

In the Spring MVC 3.3.13 implementation:

- Base path `/` is normalized to an empty string.
- The discovery handler is registered when the discovery flag is enabled **and** at least one of two conditions holds: the normalized base path is non-empty, or a separate management port is used.

The condition can be written as a logic model:

```text
register discovery =
    discovery is enabled
    AND (base path is non-empty OR management port differs from application port)
```

Result table, assuming the remaining web auto-configuration conditions are met:

| discovery.enabled | Base path | Port | Discovery handler |
| --- | --- | --- | --- |
| `true` | `/actuator` | Shared | Registered |
| `false` | `/actuator` | Shared | Not registered |
| `true` | `/` | Shared | Not registered |
| `true` | `/` | Separate | Can register at management port root |
| `false` | `/` | Separate | Not registered |

This is a point where the high-level description in the documentation does not cover every execution condition of Spring MVC 3.3.13. Do not conclude that setting `/` always disables discovery under every port configuration. If the intent is to disable the page, explicitly set `management.endpoints.web.discovery.enabled=false`.

You can cross-check the normalization in [`WebEndpointProperties`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.java) and the registration condition in [`WebMvcEndpointManagementContextConfiguration`](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/servlet/WebMvcEndpointManagementContextConfiguration.java).

## 6. Hands-on: Checking the Links Page and Direct Endpoint

The sample project adds no Spring Security, business controllers, or custom resource mappings. The application listens only on the local machine at port `8087`; ensure the port is free before running.

The results below are **expected results in this exact sample project**, not inferences drawn from a single HTTP code in an arbitrary application.

### 6.1. Creating the Minimal Project

```text
actuator-discovery-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/DiscoveryPageApplication.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-discovery-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

File `src/main/java/example/DiscoveryPageApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryPageApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryPageApplication.class, args);
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087
spring.jmx.enabled=false

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true

management.endpoints.web.base-path=/actuator
management.endpoints.web.discovery.enabled=true
management.endpoints.web.exposure.include=health,info
```

The project explicitly enables only the two endpoints to be observed. There is no need to create a custom controller named `discovery`.

### 6.2. Case A: Discovery Page Enabled

In the project directory, using JDK 21 and Gradle 8.5:

```powershell
gradle bootJar
java -jar build/libs/actuator-discovery-demo-1.0.0.jar
```

If Gradle Wrapper 8.5 is already present, you can replace the first command with `.\gradlew.bat bootJar`. Gradle supplies the Spring libraries and builds a runnable JAR; do not compile this program with standalone `javac`.

In another PowerShell window:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:8087/actuator'
$page._links.PSObject.Properties.Name -contains 'info'
$page._links.info.href
```

Expected output:

```text
True
http://127.0.0.1:8087/actuator/info
```

The check relies on the presence of the `info` link, not on key ordering or total link count.

Check the endpoint directly:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
200
```

`curl.exe` invokes cURL on Windows; `-o NUL` discards the body so the check prints only the HTTP status code.

### 6.3. Case B: Disabling the Page, Keeping the Endpoint

Stop run A with `Ctrl+C`, then run again:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.discovery.enabled=false
```

Check both addresses:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output in order of the two commands:

```text
404
200
```

The result shows the discovery handler is no longer registered, while the `info` endpoint remains exposed. A program that already knows the URL can still call it directly under the sample conditions.

### 6.4. Case C: Keeping the Page, Excluding `info` from the HTTP Set

Stop run B, then run:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.exposure.exclude=info
```

This is a fresh startup; the discovery-disabling argument from run B does not carry over automatically. The discovery flag in the file is `true` again.

Check:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:8087/actuator'
$page._links.PSObject.Properties.Name -contains 'info'
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
False
404
```

The discovery page is still read successfully, yet no longer contains the `info` link. The direct endpoint is also no longer exposed over HTTP. These two pieces of evidence reflect an exposure change, unlike merely disabling the links page.

### 6.5. Case D: Changing Root to `/manage`

Stop run C, then run:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/manage
```

Check:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:8087/manage'
$page._links.info.href
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/manage/info
```

Expected output:

```text
http://127.0.0.1:8087/manage/info
200
```

The new root address provides links under the new path. In the sample project, the old `/actuator` is no longer used as the discovery page.

### 6.6. Case E: Base Path `/`, Still Sharing the Port

Stop run D, then run:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/
```

Check:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/info
```

Expected output:

```text
404
200
```

Discovery is not registered at the shared root. The `info` endpoint is now at `/info` because Actuator's base path changed.

If a controller or home page is added at `/`, the first response may differ; what must be verified is whether it is Actuator's `_links` page or not.

### 6.7. Case F: Base Path `/`, Separate Management Port

Stop run E, ensure port `9087` is also free, and run:

```powershell
java -jar build/libs/actuator-discovery-demo-1.0.0.jar --management.endpoints.web.base-path=/ --management.server.port=9087 --management.server.address=127.0.0.1
```

In this Spring MVC 3.3.13 configuration, the separate management port satisfies the discovery registration condition:

```powershell
$page = Invoke-RestMethod -Uri 'http://127.0.0.1:9087/'
$page._links.PSObject.Properties.Name -contains 'info'
$page._links.info.href
```

Expected output:

```text
True
http://127.0.0.1:9087/info
```

Compare runs E and F to see why the port condition must be checked when talking about base path `/`.

### 6.8. Run Comparison Table

Each row uses the initial config file plus the exact arguments for that run:

| Case | Discovery page | `info` link on page | `info` endpoint |
| --- | --- | --- | --- |
| A: sample config | `8087/actuator` has page | Yes | `8087/actuator/info` returns `200` |
| B: discovery disabled | `8087/actuator` returns `404` | No page to read | Still returns `200` |
| C: HTTP exclude `info` | Page still present | No | `8087/actuator/info` returns `404` |
| D: base path `/manage` | `8087/manage` has page | Yes | `8087/manage/info` returns `200` |
| E: base path `/`, shared port | Not registered at root | No page to read | `8087/info` returns `200` |
| F: base path `/`, separate port | `9087/` has page | Yes | `9087/info` returns `200` |

The abbreviated addresses in the table all use host `127.0.0.1` and HTTP. The table reflects the sample project, without security filters or proxies added.

## 7. Protecting Discovery Scope and Access Scope

Discovery is a separate access point that must be considered in security policy. Spring Boot provides the `EndpointRequest.toLinks()` matcher for the links page. The `EndpointRequest.toAnyEndpoint()` matcher also includes the links page; `excludingLinks()` allows separating it from the matcher set when a distinct rule is needed. [Spring Boot 3.3 `EndpointRequest` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

A policy might allow health check tools to call `health`, while only allowing an operations role to read the discovery page and other management endpoints. When deploying, protect both the links page and the target endpoints according to that intent.

### 7.1. Do Not Treat `_links` as a Per-User Permission List

The default handler invokes the links resolver with the request URL and returns the result in `_links`. The standard links resolver does not filter the link set per role of the user currently reading the page.

From this mechanism it follows: someone permitted to read discovery may see a link to an endpoint that another security rule still blocks them from calling directly. The presence of a link does not grant access permission. [Handler Returning the Links Page](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/WebMvcEndpointHandlerMapping.java)

Similarly, knowing paths from documentation, logs, or configuration still lets callers attempt direct requests when discovery is disabled. Call permissions must be decided at the appropriate security layer.

### 7.2. Separating Operational Goals Properly

| Goal | Mechanism to use |
| --- | --- |
| Do not provide the links page | `discovery.enabled=false` |
| Expose only a subset of endpoints over HTTP | `web.exposure.include/exclude` |
| Restrict who may read the page or call endpoints | HTTP authentication and authorization |
| Restrict where connections to the management port can originate | Listening address and network policy |
| Reduce detailed info in an endpoint response | Per-endpoint configuration of that endpoint |

CORS partially controls whether browsers permit cross-origin response reading; it does not replace authentication or make an endpoint disappear from HTTP. No CORS configuration is needed to perform the cURL and PowerShell checks in this article.

## 8. Diagnosis and Self-check

When results differ from expectations, check using specific questions:

1. Are you calling the right port and all path prefixes?
2. What is the effective discovery value; is an argument or profile overriding it?
3. Is the base path empty after normalization, and is the management port separate?
4. Is the target endpoint enabled, eligible, and in the effective HTTP set?
5. Was the request handled by a security filter or proxy before reaching the handler?
6. Are the links being read a fresh response from the right process after restarting?

Editing a config file does not automatically guarantee running mappings were recreated. With the sample project, always stop and restart with the new arguments. `401`, `403`, or `404` errors must be interpreted in the context of configuration and the processing chain; do not use a single status code to deduce the entire discovery state.

Exercises:

- To keep `info` callable directly while not providing the links page: which property do you change?
- To remove `info` from discovery and also stop exposing it over HTTP: which configuration layer do you change?
- Why does a link key having a parameterized template make counting keys differ from counting endpoints?
- Why can setting base path `/` and switching from shared port to separate port make discovery reappear in Spring MVC 3.3.13?
- If only the operations role is allowed to read discovery, do you still need to check direct call permissions for each endpoint?

Answers must point to the right mechanism: the discovery flag for the page, exposure for the HTTP set, path/port conditions for mapping registration, and security for access rights. That is the basis for limiting discovery scope while properly controlling actual management capabilities.
