# Choosing @WebEndpoint or @JmxEndpoint When Supporting Only One Technology

An Actuator endpoint is a management point of an application, while HTTP and JMX are two ways operations tools call that management point. Having an endpoint exist in Java code does not mean it must be exposed on both channels.

When design requirements call for supporting only one technology, `@WebEndpoint` or `@JmxEndpoint` expresses that constraint directly on the endpoint type. Conversely, if the endpoint can be shared across channels while each environment wants only one channel open, `@Endpoint` combined with exposure configuration is usually more suitable.

This lesson focuses on how to choose the annotation, its relationship to configuration, and how to prove an endpoint appears only on the intended channel. Examples use Spring Boot 3.3 and JDK 21; Java code uses no preview features.

## 1. Distinguishing the Endpoint from the Exposure Technology

Picture a management operation as having two layers:

- **Operation content:** reading state, providing information, or performing a management action.
- **Invocation channel:** receiving HTTP requests or receiving calls to an MBean in JMX.

`@ReadOperation`, `@WriteOperation`, and `@DeleteOperation` describe operations in the Actuator model. The annotation on the class determines which channels the endpoint is allowed to participate in.

| Annotation on Class | Can Be Exposed Over HTTP | Can Be Exposed Over JMX | Design Intent |
| --- | --- | --- | --- |
| `@Endpoint` | Yes | Yes | Endpoint is not restricted to one of the two technologies |
| `@WebEndpoint` | Yes | No | Provides the endpoint over HTTP only |
| `@JmxEndpoint` | No | Yes | Provides the endpoint over JMX only |

“Can be” in the table indicates supported capability. The endpoint must still be registered as a bean, enabled, and included in the appropriate exposure configuration; HTTP also requires web application infrastructure.

Spring Boot 3.3's [`WebEndpoint` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html) defines HTTP scope, while the [`JmxEndpoint` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpoint.html) defines JMX scope.

For example, an endpoint meant solely for JConsole does not automatically get an `/actuator/...` URL. Calling with `curl` is not a complete verification method for that endpoint.

## 2. Choosing Based on Fixed Requirements vs. Deployment Policy

### 2.1. Choose @WebEndpoint When the Management Contract Is HTTP-Only

Use `@WebEndpoint` when consumers of the endpoint are HTTP clients and the development team intentionally provides no JMX contract for this feature.

For example, an operations tool in a system only reads deployment notices via HTTP. The team wants that endpoint to remain HTTP-only even if another environment enables JMX for the application.

This is a support-scope decision. Do not choose this annotation merely because there are no JMX users today if the endpoint is actually designed for shared use.

### 2.2. Choose @JmxEndpoint When the Management Contract Is JMX-Only

Use `@JmxEndpoint` when the feature is provided to JVM management tools via MBeans and has no HTTP contract.

For example, the operations team uses an existing JMX tool to read JVM notices. This endpoint must appear in the MBean list, without ever becoming a management URL if someone widens the HTTP exposure list.

A JMX-only application does not need the web starter just to expose that endpoint. The practice project below includes the web starter because it compares both channels in the same application.

### 2.3. Choose @Endpoint and Exposure When Restrictions Depend on Environment

If the feature works over both technologies but production only wants HTTP open, that restriction may be a **deployment policy**, not a limitation of the feature itself.

In that case, you can keep `@Endpoint`, include the ID in HTTP exposure, and exclude it from JMX. Another environment can still make the opposite choice without changing annotations or recompiling code.

A helpful question before choosing is: “If tomorrow we need the other channel, do we only want to change configuration, or must we actually design and commit to an additional usage contract?”

## 3. Annotation and Exposure Are Two Separate Conditions

Exposing an endpoint can be expressed as follows:

```text
Endpoint is already a bean
        |
        v
Endpoint is enabled
        |
        v
Annotation permits the target technology
        |
        v
That technology is ready and exposure permits the ID
        |
        v
Endpoint is exposed on the corresponding channel
```

The diagram describes the conditions to understand; it does not assert the internal call order of every Spring Boot component.

Common configuration properties in Spring Boot 3.3:

| Property | Role |
| --- | --- |
| `management.endpoint.<id>.enabled` | Enables or disables the endpoint with that ID |
| `management.endpoints.web.exposure.include` | IDs selected for exposure over HTTP |
| `management.endpoints.web.exposure.exclude` | IDs excluded from HTTP |
| `spring.jmx.enabled` | Enables Spring Boot's JMX management support |
| `management.endpoints.jmx.exposure.include` | IDs selected for exposure over JMX |
| `management.endpoints.jmx.exposure.exclude` | IDs excluded from JMX |

When the same ID appears in both `include` and `exclude` for a channel, `exclude` takes precedence. The [Spring Boot 3.3 Actuator endpoint documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) describes enablement and exposure separately.

**Exposure does not convert an endpoint's technology.** Adding a `@JmxEndpoint`'s ID to HTTP `include` does not create an HTTP version of the endpoint. Similarly, adding a `@WebEndpoint`'s ID to JMX `include` does not create an MBean for it.

On the JMX side, Spring Boot disables this management feature by default; setting `spring.jmx.enabled=true` is a necessary condition when using auto-configuration in the practice exercise. It does not mean all JMX in the JVM and every library is controlled by this property. See [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

## 4. Practice: Comparing Three Endpoint Types in One Application

The goal of the experiment is to observe simultaneously:

- `webnotice`: HTTP only.
- `jvmnotice`: JMX only.
- `sharednotice`: supports both as a control reference.

The operations simply return fixed notices, isolating endpoint exposure behavior from business processing.

### 4.1. Structure and Build Configuration

This is a standalone sample project using Gradle 8.x and JDK 21. Spring Boot version `3.3.0` is pinned to reproduce behavior in the 3.3 line; this is not a statement about the latest version.

```text
transport-endpoint-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/actuatortech/
    │   └── TransportEndpointApplication.java
    └── resources/
        └── application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'transport-endpoint-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

The web starter provides HTTP infrastructure for the experiment. The Actuator starter provides the endpoint model and endpoint exposure mechanism. The BOM manages dependency versions.

### 4.2. A Complete Single-File Java Program

Save at the exact path `src/main/java/example/actuatortech/TransportEndpointApplication.java`:

```java
package example.actuatortech;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.jmx.annotation.JmxEndpoint;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TransportEndpointApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransportEndpointApplication.class, args);
    }

    @Bean
    WebNoticeEndpoint webNoticeEndpoint() {
        return new WebNoticeEndpoint();
    }

    @Bean
    JvmNoticeEndpoint jvmNoticeEndpoint() {
        return new JvmNoticeEndpoint();
    }

    @Bean
    SharedNoticeEndpoint sharedNoticeEndpoint() {
        return new SharedNoticeEndpoint();
    }

    @Bean
    ApplicationRunner inspectJmx(MBeanServer server) {
        return args -> {
            ObjectName jvm = new ObjectName(
                    "learning.actuator:type=Endpoint,name=Jvmnotice");
            ObjectName web = new ObjectName(
                    "learning.actuator:type=Endpoint,name=Webnotice");
            ObjectName shared = new ObjectName(
                    "learning.actuator:type=Endpoint,name=Sharednotice");
            System.out.println("jvmnotice registered=" + server.isRegistered(jvm));
            System.out.println("webnotice registered=" + server.isRegistered(web));
            System.out.println("sharednotice registered=" + server.isRegistered(shared));
            if (server.isRegistered(jvm)) {
                Object result = server.invoke(
                        jvm, "notice", new Object[0], new String[0]);
                System.out.println("jvmnotice result=" + result);
            }
        };
    }

    @WebEndpoint(id = "webnotice")
    public static class WebNoticeEndpoint {
        @ReadOperation
        public Map<String, String> notice() {
            return Map.of("channel", "http");
        }
    }

    @JmxEndpoint(id = "jvmnotice")
    public static class JvmNoticeEndpoint {
        @ReadOperation
        public String notice() {
            return "jmx-ready";
        }
    }

    @Endpoint(id = "sharednotice")
    public static class SharedNoticeEndpoint {
        @ReadOperation
        public String notice() {
            return "shared-ready";
        }
    }
}
```

Things to read carefully in the code:

1. The three endpoint classes use three different annotations and three different IDs.
2. Each object is registered via `@Bean`; do not merely place an annotation on a class and expect Spring to create the instance automatically.
3. All operations use `@ReadOperation`, since the content is reading information.
4. `ApplicationRunner` is purely for verification: it checks whether MBeans are registered and invokes one JMX operation directly.
5. `javax.management` is the JDK's JMX package and keeps this name on Java 21; do not change the import to `jakarta.management`.

The `Map` returned by `webnotice` lets us observe a JSON-formatted HTTP response. Having `jvmnotice` return `String` focuses on the JMX operation call; there is no JSON or HTTP status code in that `MBeanServer.invoke` call.

### 4.3. application.properties

```properties
server.address=127.0.0.1

spring.jmx.enabled=true
management.endpoints.jmx.domain=learning.actuator

management.endpoints.web.exposure.include=health,webnotice,sharednotice
management.endpoints.jmx.exposure.include=health,jvmnotice,sharednotice
```

The JMX domain is explicitly set so the verification code uses stable `ObjectName`s. The example assumes a single context for the practice app and does not enable context-specific unique name generation.

The `ApplicationRunner` verification requires the `MBeanServer` bean, so keep `spring.jmx.enabled=true` when running the prototype as written. If you trim the project down to an HTTP-only example and turn off JMX, also remove the JMX verification bean; it is not a required part of the endpoints.

There is no Spring Security in the prototype's dependencies. If merging code into an application that already has security, HTTP access permissions also depend on that application's security configuration.

### 4.4. Launching

From the root directory of the sample project, generate the Gradle Wrapper with an installed Gradle 8.x if not already present:

```shell
gradle wrapper --gradle-version 8.5
```

Windows PowerShell:

```powershell
.\gradlew.bat clean bootRun
```

Linux/macOS:

```shell
./gradlew clean bootRun
```

Aside from normal startup logs, the JMX check prints these exact lines:

```text
jvmnotice registered=true
webnotice registered=false
sharednotice registered=true
jvmnotice result=jmx-ready
```

`jvmnotice` has an MBean and the `notice` call succeeds. `webnotice` is not registered as a corresponding Actuator MBean. `sharednotice` is present because both the shared annotation and JMX exposure allow it.

## 5. Checking HTTP and JMX with the Right Tools

### 5.1. HTTP

Open another terminal. On Windows use `curl.exe`; on Linux/macOS replace with `curl`:

```shell
curl.exe -s "http://127.0.0.1:8080/actuator/webnotice"
curl.exe -i "http://127.0.0.1:8080/actuator/jvmnotice"
curl.exe -s "http://127.0.0.1:8080/actuator/sharednotice"
```

With the prototype running:

| Endpoint | HTTP Result |
| --- | --- |
| `/actuator/webnotice` | 200; response body `{"channel":"http"}` |
| `/actuator/jvmnotice` | 404; no corresponding HTTP operation |
| `/actuator/sharednotice` | 200; response body `shared-ready` |

The response from `sharednotice` here is a text string, not a JSON object. Do not infer that every `@ReadOperation` returns the same payload format.

The 404 code for `jvmnotice` is the expected result in the prototype. In another application, a standalone 404 is not enough to prove the cause; you must also check path, port, exposure, and intermediate layers.

### 5.2. JMX

The program already checked via `MBeanServer` inside the same process, so no remote JMX connection setup is needed.

If using JConsole and the environment permits attaching to local Java processes, select the application process and inspect the `learning.actuator` domain, group `type=Endpoint`. In the sample configuration:

| ObjectName | Registered |
| --- | --- |
| `learning.actuator:type=Endpoint,name=Jvmnotice` | Yes |
| `learning.actuator:type=Endpoint,name=Webnotice` | No |
| `learning.actuator:type=Endpoint,name=Sharednotice` | Yes |

On the `Jvmnotice` MBean, invoking the zero-argument `notice` operation returns the string `jmx-ready`.

Distinguish ID from object name: exposure configuration uses the ID `jvmnotice`, whereas the default MBean name in the experiment contains `name=Jvmnotice`. Do not use the HTTP URL directly as the MBean name. Customizing the domain or naming strategy changes the `ObjectName`.

## 6. Exposure Experiment: Configuration Does Not Override Annotation Limits

### 6.1. Put All Three IDs in Both Lists

Replace the two exposure lines in the sample project with:

```properties
management.endpoints.web.exposure.include=health,webnotice,jvmnotice,sharednotice
management.endpoints.jmx.exposure.include=health,webnotice,jvmnotice,sharednotice
```

Restart the application and check again. The result remains:

| Endpoint | HTTP | JMX MBean |
| --- | --- | --- |
| `webnotice` | Yes | No |
| `jvmnotice` | No | Yes |
| `sharednotice` | Yes | Yes |

This experiment directly verifies what “supports only one technology” means. The `include` list selects from the set of eligible endpoints; it does not transform one endpoint type into another.

In the prototype, the two specialized annotations enforce the limit at the type level. Do not stack `@Endpoint` onto the same class to “enable” the other channel. Choose one clear model per endpoint class.

### 6.2. Keep @Endpoint but Expose HTTP Only by Environment

Keep `SharedNoticeEndpoint` using `@Endpoint`, and add:

```properties
management.endpoints.jmx.exposure.exclude=sharednotice
```

Even though `sharednotice` remains in JMX `include`, the corresponding MBean is not exposed because `exclude` takes precedence. Meanwhile, HTTP `/actuator/sharednotice` still returns `shared-ready`.

The stdout verification line changes to `sharednotice registered=false`. No endpoint code changes are needed. This is an example of limiting by configuration, different from changing the annotation to `@WebEndpoint`.

When an endpoint genuinely does not support JMX by design, using `@WebEndpoint` expresses that decision more clearly than relying solely on a configuration file in one environment.

## 7. Things Specialized Annotations Do Not Solve Automatically

### 7.1. They Do Not Replace Bean Registration and the Operation Model

`@WebEndpoint` or `@JmxEndpoint` still needs a Spring-managed object. In this practice exercise, `@Bean` handles that. Methods must also be marked with appropriate Actuator operation annotations; an ordinary `public` method does not automatically become a management operation.

If an operation has Java parameters and needs name-based mapping, parameter name metadata must still be preserved during compilation. Changing the exposure technology does not remove general requirements of the endpoint model.

### 7.2. @WebEndpoint Is Not Synonymous with @RestController

`@WebEndpoint` remains within Actuator's operation model. It does not mean you can arbitrarily apply every Spring MVC controller mapping style, such as adding `@GetMapping` and expecting Actuator to treat it like a regular controller.

Choosing HTTP does not mean choosing Servlet exclusively. Web Actuator endpoints can integrate with supported web infrastructures, such as Spring MVC or WebFlux, depending on the application. If framework-specific request handling is needed, check the corresponding integration mechanism rather than assuming this annotation provides all HTTP parameter types automatically.

### 7.3. They Do Not Imply Authorization or Remote Port Exposure

`@JmxEndpoint` limits the endpoint to the JMX channel; it does not create a remote JMX connection or govern who can invoke the MBean. Managing remote JMX connectivity is a separate JVM environment configuration.

Similarly, `@WebEndpoint` does not automatically protect URLs with authentication. Technology restrictions and access control are two separate decisions to evaluate. An HTTP security filter does not automatically control JMX calls.

### 7.4. Not Annotations for Extending Existing Endpoints

If you already have a shared endpoint and only want to change how certain operations are represented on one technology, distinguish these from `@EndpointWebExtension` and `@EndpointJmxExtension`.

`@WebEndpoint`/`@JmxEndpoint` declare standalone specialized endpoints. Extension annotations attach an extension to an existing endpoint. You do not need to create a new endpoint and duplicate business logic just to customize the exposure layer. The [Implementing Custom Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom) section presents these options.

## 8. How to Test the Single-Technology Decision

A test that only calls `new JvmNoticeEndpoint().notice()` directly proves the return value, but does not prove the endpoint is not exposed over HTTP.

For a technology-restriction requirement, test both **presence on the supported channel** and **absence on the other channel**:

| Requirement | Required Evidence |
| --- | --- |
| HTTP-only endpoint | HTTP request succeeds; corresponding MBean is not registered |
| JMX-only endpoint | MBean exists and operation can be invoked; no corresponding HTTP mapping |
| Exposure does not change endpoint type | Putting ID into the other channel's list does not alter exposure outcome |
| `@Endpoint` limited by environment | Changing exposure alters exposed channels without changing code |

You can use MockMvc for the HTTP side of a Spring MVC app and `MBeanServer` for JMX in the same test suite. There is no need to open a remote JMX connection just to verify MBean registration.

When testing multiple application contexts in the same JVM, close contexts after each case or configure separate names/domains to avoid `ObjectName` collisions. If using unique naming, tests must look up the actual name rather than hardcoding one that is no longer valid.

## 9. Common Errors and How to Cross-Check

| Symptom | What to Review |
| --- | --- |
| `@JmxEndpoint` has no URL even though added to HTTP include | This is the annotation's technology limit, not a missing URL bug |
| `@WebEndpoint` does not appear in JConsole | Recheck expectations: this endpoint is not exposed over JMX |
| Endpoint appears nowhere | Bean registration, operation annotations, enablement, exposure, and required infrastructure |
| JMX MBean missing despite right annotation | `spring.jmx.enabled`, JMX exposure, domain/object name, and registration errors |
| HTTP returns 401/403 | Application authentication/authorization policy, not just endpoint annotations |
| `@Endpoint` endpoint unexpectedly appears via JMX in another environment | Check whether this is intended capability or a fixed restriction that belongs in code |
| Changing annotation breaks operations tools | Technology contract changed; check and update callers |

Do not use a failing HTTP management operation to conclude JMX is also broken, or vice versa. The two channels have distinct exposure configurations and access mechanisms.

## 10. Decision Exercises

For each scenario, choose an annotation and state your reasoning:

1. A management feature has an official contract exclusively over HTTP; enabling JMX for other features must never cause this feature to appear as an MBean.
2. A JVM management tool only invokes MBeans; the system commits to no URL for that feature.
3. The same feature is used over HTTP in staging and JMX in production, depending on deployment policy.
4. A shared endpoint already exists, and you only want to change how one operation is represented on the HTTP side.

Reference answers:

1. `@WebEndpoint`: expresses the HTTP-only support boundary directly in the endpoint type.
2. `@JmxEndpoint`: expresses the JMX-only support boundary.
3. `@Endpoint` and per-environment exposure configuration: the feature still supports both technologies.
4. Consider `@EndpointWebExtension` for the existing endpoint, rather than defaulting to creating another independent endpoint.

Before finalizing a choice, write down the names of calling tools, the committed technologies, and how you will verify the endpoint does not appear on out-of-scope channels. That forms the basis for selecting the annotation and building appropriate test evidence.
