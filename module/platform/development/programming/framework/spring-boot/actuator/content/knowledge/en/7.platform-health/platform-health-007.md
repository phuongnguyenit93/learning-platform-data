# Managing show-details, show-components, and Health Viewing Permissions

A monitoring system only needs to know whether the application is operational; an operator, however, needs to know which component failed and the associated diagnostic data. If both call `/actuator/health`, how do you return the right amount of information to each?

In Spring Boot Actuator, you must separately define **permission to call the endpoint**, **permission to see components**, and **permission to see detail information**. This lesson uses Spring Boot 3.3.x, Java 21, and a Servlet application with Spring Security. The visibility configuration has a similar meaning in reactive applications, but the `HttpSecurity` code below is for Servlet.

## 1. Identifying three layers of information in a response

Consider an illustrative response with one component `sample`:

```json
{
  "status": "UP",
  "components": {
    "sample": {
      "status": "UP",
      "details": {
        "check": "demo-only",
        "target": "sample-service"
      }
    }
  }
}
```

| Location | Meaning | Related configuration |
| --- | --- | --- |
| Outermost `status` | Aggregated status of the application | Not hidden merely by turning off components/details |
| `components.sample.status` | Status of the component named `sample` | `management.endpoint.health.show-components` |
| `components.sample.details` | Supplementary data provided by the component | `management.endpoint.health.show-details` |

`show-components` controls whether the component structure is revealed. `show-details` controls whether `details` fields are retained. Enabling details only allows showing data already produced by the check; it does not generate additional diagnostic data on its own.

The structure above is Actuator's standard V3 health JSON format. A composite component can also contain nested `components`. When reading the example, distinguish overall `status` from each component's `status`. [Spring Boot 3.3 Health Response Description](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

## 2. Placing visibility properties in the right processing flow

An HTTP request passes through the following decisions:

```text
Endpoint is enabled and exposed over HTTP
        ↓
Spring Security authenticates and checks access permission
        ↓
Health is collected and aggregated
        ↓
Evaluate show-components / show-details per caller
        ↓
Return appropriate HTTP code and health body
```

Exposing an endpoint via `management.endpoints.web.exposure.include` is not the same as granting permission to call it. Similarly, `show-details: always` does not bypass a Spring Security rule that blocks the request.

For applications with Spring Security, Boot's auto-configuration and the application's own configuration must be distinguished: when the application provides a `SecurityFilterChain`, the application is responsible for setting appropriate access rules. [Endpoint Exposure and Security in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Example design goals:

- Unauthenticated guests may call health to see the overall status.
- Authenticated users who do not operate the system still see only the overall status.
- Users with an operations role may view components and details.
- Other management endpoints have separate access rules.

These four requirements must be expressed through both health configuration and Spring Security configuration.

## 3. Three visibility modes and default values

Both properties accept the same three values:

| Value | When is the corresponding information shown? |
| --- | --- |
| `never` | Never shown, even if the caller has an operations role |
| `when-authorized` | Shown when the caller's security context satisfies health roles |
| `always` | Shown to everyone who passes the access-control step |

In Boot 3.3:

- `management.endpoint.health.show-details` defaults to `never`.
- If `management.endpoint.health.show-components` is not declared, Boot uses the `show-details` setting to decide component visibility.
- Therefore, leaving both at defaults means the root response normally has only the overall status.

This inheritance explains why setting only `show-details: always` also causes `components` to appear. If you want different policies, declare both explicitly. [Boot 3.3 Health Properties Reference](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.health.show-components).

Balanced configuration for this lesson's example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: when-authorized
      show-details: when-authorized
      roles:
        - ACTUATOR
```

Properties under `management.endpoint.health` use singular `endpoint`; HTTP exposure under `management.endpoints.web` uses plural `endpoints`. Placing a key under the wrong YAML branch is an easy configuration mistake to miss.

## 4. How do the two switches interact?

The table below applies to the **root endpoint** `/actuator/health`, assuming the request has been permitted by Spring Security and components are UP.

| show-components | show-details | Caller | Main visible content |
| --- | --- | --- | --- |
| `never` | `never` | Anyone | Overall status |
| `always` | `never` | Anyone | Overall status and each component, without details |
| `always` | `when-authorized` | Lacks health role | Overall status and each component, without details |
| `always` | `when-authorized` | Has health role | Components along with details if provided by components |
| `when-authorized` | `when-authorized` | Lacks health role | Overall status |
| `when-authorized` | `when-authorized` | Has health role | Components along with details if present |
| `never` | `always` | Anyone | Overall status; component tree is hidden |
| Undeclared | `always` | Anyone | Components along with details if present |

In the `show-components: never` case, there is no component object in the root response to hold its `details`. Do not use this configuration and expect individual component details to appear alongside the overall status.

Hiding information does not exclude a component from aggregation. A DOWN component can still make the overall status DOWN even when the caller is not allowed to see that component's name or details. Status calculation and presentation are two separate decisions. [Aggregation and Visibility Filtering in Boot 3.3.13 Source](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

## 5. "Authorized to view" differs from "logged in"

With `when-authorized`, `management.endpoint.health.roles` specifies the roles permitted to view the corresponding information:

- Empty role list: any authenticated user may view.
- List containing `ACTUATOR`: the caller needs that role.
- List with multiple roles: matching at least one role is sufficient; having all is not required.
- Unauthenticated guests do not automatically become authorized to view merely because the endpoint has `permitAll()`.

The `roles` property does not create accounts, does not assign roles, and does not establish a login mechanism. It also has no effect limiting information configured as `always`. [Health Role Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

### Role names and the ROLE_ prefix

In a typical Servlet setup:

```text
User builder:        .roles("ACTUATOR")
Generated authority: ROLE_ACTUATOR
Health roles:        ACTUATOR
HTTP rule:           .hasRole("ACTUATOR")
```

`roles("ACTUATOR")` and `hasRole("ACTUATOR")` follow Spring Security's role convention. Servlet role checks also integrate with the `ROLE_` prefix convention. Use consistent names as shown; do not pass `ROLE_ACTUATOR` into `roles(...)` and accidentally create a misconfiguration. [Spring Security and Servlet API](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html#servletapi-isuserinrole).

If the system authenticates via JWT granting only `SCOPE_...` authorities, verify how authorities map to roles before using this health configuration. Having a valid token does not prove the caller has `ROLE_ACTUATOR`. With security mechanisms that customize prefixes or role checking, verify against the actual security context.

## 6. Standalone example: guests see status, operators see details

The following example is a standalone learning project requiring no database. The `sample` check always returns UP with fixed data so the focus stays on viewing permissions; it does not prove an external service is working.

Prepare JDK 21 and Gradle 8.5. Create four files with this structure:

```text
health-visibility-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/health/HealthVisibilityApplication.java
    └── resources/application.yml
```

### 6.1. Project declaration

File `settings.gradle`:

```groovy
rootProject.name = 'health-visibility-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

The BOM manages related library versions, so no individual version is pinned on each starter. This is the Gradle native BOM usage supported by Boot. [Managing Dependencies with Gradle in Boot 3.3](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html#managing-dependencies.gradle-bom-support).

### 6.2. Health configuration

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: when-authorized
      show-details: when-authorized
      roles:
        - ACTUATOR
      probes:
        enabled: false
  health:
    defaults:
      enabled: false
```

The example disables default checks so the response contains only `sample`, avoiding dependence on machine disk space. This is a choice for the experiment; real applications must keep checks appropriate for monitoring goals.

### 6.3. Declaring the check and security

File `src/main/java/example/health/HealthVisibilityApplication.java`:

```java
package example.health;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class HealthVisibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthVisibilityApplication.class, args);
    }

    @Bean
    HealthIndicator sample() {
        return () -> Health.up()
                .withDetail("check", "demo-only")
                .withDetail("target", "sample-service")
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
                .password(encoder.encode("reader-demo"))
                .roles("USER")
                .build();

        var ops = User.withUsername("ops")
                .password(encoder.encode("ops-demo"))
                .roles("ACTUATOR")
                .build();

        return new InMemoryUserDetailsManager(reader, ops);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR")
                .anyRequest()
                    .authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Explanation of decisions directly tied to this lesson:

1. The bean named `sample` creates component `sample` with two non-sensitive diagnostic values.
2. The health rule appears before the rule for all Actuator endpoints, so guests are permitted to reach health.
3. `permitAll()` allows passing the HTTP authorization step. Visibility of components/details is still decided by health configuration.
4. Other Actuator endpoints, if exposed later, require role `ACTUATOR`; current configuration exposes only health.
5. The final rule requires authentication for remaining requests.
6. The two accounts and passwords in code are strictly for a local learning project. In real deployments, use the system's identity and secrets management; HTTP Basic must be protected by HTTPS.

CSRF does not need to be disabled to execute GET requests in this lesson.

### 6.4. Launching

From the project directory, run:

```shell
gradle bootRun
```

Or generate the Gradle Wrapper and use the wrapper:

```shell
gradle wrapper --gradle-version 8.5
```

In PowerShell:

```powershell
.\gradlew.bat bootRun
```

On Linux/macOS:

```shell
./gradlew bootRun
```

Use Gradle to compile because the program depends on Spring libraries. A standalone `javac` command does not fetch dependencies. The application prints startup logs; the evidence to observe in this lesson is the HTTP code and JSON, not a fixed log string.

## 7. Verifying three callers hitting the same URL

The commands below use `curl.exe` in PowerShell on Windows. On Linux/macOS, substitute `curl`. Run only after the application starts successfully.

### 7.1. Unauthenticated guest

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/health
```

Expected HTTP 200 and body:

```json
{"status":"UP"}
```

The guest can call the endpoint because the HTTP rule permits it, yet cannot see components/details.

### 7.2. Regular user

```powershell
curl.exe -i -u reader:reader-demo http://127.0.0.1:8080/actuator/health
```

Expected HTTP 200 and body:

```json
{"status":"UP"}
```

`reader` is authenticated yet only has role `USER`. With `health.roles: ACTUATOR`, logging in successfully is not enough to view details.

### 7.3. Operator

```powershell
curl.exe -i -u ops:ops-demo http://127.0.0.1:8080/actuator/health
```

Expected HTTP 200 and JSON equivalent to:

```json
{
  "status": "UP",
  "components": {
    "sample": {
      "status": "UP",
      "details": {
        "check": "demo-only",
        "target": "sample-service"
      }
    }
  }
}
```

JSON field order and line breaks are not pass/fail criteria. Verify the exact fields, values, and HTTP status code.

### 7.4. Credentials supplied with wrong password

```powershell
curl.exe -i -u ops:wrong-password http://127.0.0.1:8080/actuator/health
```

Expected HTTP 401 in the example's HTTP Basic setup. `permitAll()` does not turn a failed authentication attempt into success; the authentication filter can terminate the request before health handles it.

## 8. If the requirement is that only operators may call health

Some systems do not want to expose even the overall status to guests. In that case, replace the **HTTP rule for health** in the example:

```java
.requestMatchers(EndpointRequest.to(HealthEndpoint.class))
    .hasRole("ACTUATOR")
```

This is a replacement snippet inside `SecurityFilterChain`, not a standalone Java program.

With HTTP Basic as in the example:

| Caller | HTTP permission | Expected result when system is UP |
| --- | --- | --- |
| Guest | No valid identity | HTTP 401 |
| `reader` with role USER | Authenticated, lacks required role to call | HTTP 403 |
| `ops` with role ACTUATOR | Permitted to call | HTTP 200 and info per visibility config |

If `show-details: never` is still kept, `ops` cannot see details either. Invocation permission and display permission must both satisfy the goal; they do not substitute for one another.

The 401/403 results in the table are tied to this HTTP Basic configuration. An application using form login or a custom error handler may produce different authentication responses; do not infer that every login mechanism returns the same responses.

## 9. Component paths, health groups, and status codes

### 9.1. Querying a component directly

In Boot 3.3, when the caller is not permitted to see components, a direct query such as `/actuator/health/sample` is not a way to bypass display restrictions. If the request passes the Security layer yet components are hidden from the caller, health may return 404 for the component path. Therefore, 404 on a sub-path is not enough to conclude the component does not exist.

With the configuration in section 6:

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/health/sample
curl.exe -i -u ops:ops-demo http://127.0.0.1:8080/actuator/health/sample
```

Expected results are 404 for the guest and 200 for `ops`, respectively. The successful sub-path response directly contains `status` and `details` of `sample`, without wrapping an extra `components.sample` layer. [Conditions for Component Paths in Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### 9.2. Health groups can have separate policies

If the system has declared health groups, inspect the effective configuration of the specific group being called. Groups can override `show-components`, `show-details`, and `roles`; do not read only the root health configuration and assume every sub-URL behaves the same. For instance, a group for status probes and a group for operators may require different amounts of information.

Here you only need to recognize the configuration scope; selecting components for liveness/readiness is a separate topic. [Health Group Configuration and Inheritance in Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

### 9.3. Hiding details does not turn DOWN into UP

With default mapping, DOWN or OUT_OF_SERVICE statuses map to HTTP 503. Visibility switches do not alter that rule. Thus, an HTTP 503 response with `{"status":"DOWN"}` can be a valid result: the system has an outage, while the caller is only permitted to see the overall status. [Mapping Health Status to HTTP in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

## 10. Common issues and targeted checks

| Symptom | What to inspect |
| --- | --- |
| Everyone sees details despite declaring roles | Is `show-details` set to `always`? Roles only restrict `when-authorized` mode |
| Regular users only see status and get 200 | May be completely intentional: HTTP permits calling, health denies seeing more |
| Operators still do not see details | Actual authentication, authority/role, `never` mode, overridden config, and data supplied by indicator |
| Only wanted to hide details yet component names still appear | Check `show-components`; that is a separate decision |
| Changed show-details yet all requests fail with 401/403 | Check SecurityFilterChain before analyzing JSON |
| Root endpoint returns 404 | Check Actuator dependency, enablement, exposure, and effective address/base path |
| Root endpoint exists yet component path returns 404 | Check component visibility permission alongside component name |
| Config looks right yet behavior differs | Check active profile, environment variables, command-line arguments, and group called |

Even component names can reveal system architecture; `show-components: always` must be an intentional decision. Furthermore, `show-details` is not an automatic redactor for sensitive fields by key name. When writing indicators, put only necessary diagnostic data into `withDetail`; avoid credentials, connection strings containing secrets, or customer data.

If a proxy or cache sits in front of the endpoint, avoid sharing detailed health responses across identities. Verify with independent requests to ensure an operator's response is never served back to a guest.

## 11. Practice and self-check

Keep the section 6 example. After each configuration change, restart the application and call again as guest, `reader`, and `ops`.

1. Change `show-components` to `always`, keeping `show-details: when-authorized`. Predict who sees the name `sample` and who sees `target`.
2. Keep both as `when-authorized`, remove the `roles` list. Compare `reader` with guest.
3. Set `show-details: never`, `show-components: always`. Check whether details are hidden even for `ops`.
4. Remove `show-components` specifically, set `show-details: always`. Explain why guests can see both components and details.
5. Restore section 6 configuration, replace `Health.up()` with `Health.down()` in the `sample` bean. Observe the HTTP code and information volume for guest versus `ops`.
6. Restore UP and change the health HTTP rule to `hasRole("ACTUATOR")`. Distinguish 401, 403, and a successful health response.

Compare predictions:

- Exercise 1: all three see `sample`; only `ops` sees `target`.
- Exercise 2: `reader` and `ops` see components/details; guest sees only overall status.
- Exercise 3: all three see `sample`'s status; nobody sees details.
- Exercise 4: `show-components` inherits the `show-details` setting, so anyone passing the HTTP layer sees the extra information.
- Exercise 5: with default mapping, both guest and `ops` get HTTP 503; guest sees overall DOWN status, `ops` additionally sees component and details.
- Exercise 6: with HTTP Basic in the example, guest gets 401, `reader` gets 403, `ops` gets 200.

Before applying to a real application, write down the desired policy for each caller group, then verify both HTTP codes and the presence of `components` and `details`. A "callable" response alone does not prove information has been properly restricted.
