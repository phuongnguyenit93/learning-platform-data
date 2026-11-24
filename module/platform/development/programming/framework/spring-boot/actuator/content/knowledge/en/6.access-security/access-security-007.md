# Distinguishing Endpoint Access Authentication From Data Detail Visibility Permissions

## 1. Successful Login Does Not Decide the Entire Response Content

A management endpoint can serve multiple groups of users. Support staff only need to know whether the application is still up; operators also need the status of individual components; an automated health checker only needs aggregate status.

If the only choice were “allow calling or forbid calling”, the application would struggle to serve those needs. Spring Boot Actuator also has a mechanism to adjust the level of detail displayed. Therefore you must distinguish three questions:

| Decision | Question to answer | Example |
| --- | --- | --- |
| Authentication | Who is the caller? | Are the username and password valid? |
| Endpoint access authorization | May that identity call this endpoint? | Does it have the `ENDPOINT_READER` role to call health? |
| Detail visibility permission | Once permitted to call, which data may that caller see? | Does it have the `HEALTH_DETAILS` role to see health details? |

**Access permission decides whether the request may reach the endpoint; visibility policy decides which data is returned.** A caller may succeed in calling yet see only aggregate status. Conversely, having the role used for detail checks does not automatically grant permission to call the URL.

This article uses **Spring Boot 3.3.x**. Examples run with Java 21, Spring Boot 3.3.0, and Spring Security 6.3 in a Servlet/Spring MVC application. Visibility concepts remain valid when using WebFlux, but WebFlux security chain configuration uses the corresponding Reactive types.

## 2. Visualizing the Path of a Request

```text
Endpoint enabled and exposed over HTTP
    |
    v
Security filter authenticates identity
    |
    v
Access rule allows calling the endpoint?
    | No -> access error response
    v Yes
Endpoint gathers information to return
    |
    v
Visibility policy + security context
    |
    +-- Aggregate status only
    +-- Component names/statuses, no details
    +-- Permitted detail data
```

Enabling the endpoint and exposing the endpoint are also separate conditions. `exposure.include` does not grant login permission; security rules do not make an unexposed endpoint appear on their own.

With HTTP Basic in the example:

- **401:** no valid credentials yet to pass the protected request.
- **403:** authenticated, but lacks permission to access the endpoint.
- **200 with reduced data:** allowed to call, and the visibility policy intentionally omits details from the response.

A health response with an unhealthy status can also use a different HTTP status code. Do not treat every non-200 code as a login failure, or every 200 response as proof that the caller was allowed to see all data.

## 3. Health Has Its Own Visibility Policy

Commonly used properties:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: HEALTH_DETAILS
```

- `show-details` controls whether detail data is included in the health output.
- `show-components` controls whether components of the health tree are displayed.
- `roles` specifies which roles qualify under the `when-authorized` policy.

The two levels “see component names/statuses” and “see component detail data” differ. You can intentionally allow the first level while hiding the second. These are properties of the health endpoint and health groups, not role declarations for user accounts. [Spring Boot 3.3 Health Properties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/health/HealthProperties.html).

### Visibility Values

| Value | Meaning once the request is authorized to access |
| --- | --- |
| `never` | Do not show the data controlled by that property |
| `when-authorized` | Show only when the caller qualifies under the endpoint's check |
| `always` | Show without requiring a detail-viewing role from this mechanism |

`always` does not disable security filters. A caller can still be blocked at the URL before the endpoint builds a response.

With `when-authorized`, the caller must be authenticated and have at least one role in the `roles` list. When no role list is configured, every authenticated user is considered eligible to view under this mechanism. By default `show-details` is `never`. [Health information and visibility conditions](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Therefore, `when-authorized` does not automatically mean “administrators only”. To restrict to a specific group, you must configure the matching role list and grant the right role to the identity.

## 4. Experiment: Two Independent Permission Types

### 4.1. Three Accounts

| Account | Roles | Purpose |
| --- | --- | --- |
| `reader` | `ENDPOINT_READER` | Allowed to call health, no permission to view details |
| `details` | `HEALTH_DETAILS` | Has the role used for visibility, but lacks permission to call health |
| `operator` | Both roles above | Allowed to call health and allowed to view details |

The two role names are chosen by the experiment. Spring Boot does not automatically create a relationship between them.

### 4.2. Preparing the Project

Use a Gradle project with Wrapper 8.5 and JDK 21. File `settings.gradle`:

```groovy
rootProject.name = 'actuator-visibility-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

### 4.3. A HealthIndicator With Synthetic Data

File `src/main/java/example/DetailVisibilityApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DetailVisibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(DetailVisibilityApplication.class, args);
    }

    @Bean
    HealthIndicator lab() {
        return () -> Health.up()
            .withDetail("sample", "synthetic")
            .withDetail("pendingJobs", 2)
            .build();
    }
}
```

Component `lab` always reports `UP`. The two details `sample` and `pendingJobs` are fixed synthetic data, helping observe what is hidden without using real sensitive information.

### 4.4. Exposure and Visibility Configuration

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  health:
    defaults:
      enabled: false
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: HEALTH_DETAILS
```

In the experiment, `management.health.defaults.enabled=false` turns off default health indicators so the response focuses solely on the `lab` bean declared by the application. This is a setup for observation, not a recommendation to disable health checks in a real system.

YAML only selects health for HTTP exposure and sets the visibility policy. It does not yet configure the `ENDPOINT_READER` rule for the URL.

### 4.5. Endpoint Access Permission Configuration

File `src/main/java/example/VisibilitySecurityConfig.java`:

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class VisibilitySecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .hasRole("ENDPOINT_READER")
                .anyRequest().denyAll())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-lab-pass"))
            .roles("ENDPOINT_READER")
            .build();
        var details = User.withUsername("details")
            .password(encoder.encode("details-lab-pass"))
            .roles("HEALTH_DETAILS")
            .build();
        var operator = User.withUsername("operator")
            .password(encoder.encode("operator-lab-pass"))
            .roles("ENDPOINT_READER", "HEALTH_DETAILS")
            .build();
        return new InMemoryUserDetailsManager(reader, details, operator);
    }
}
```

The Java rule requires `ENDPOINT_READER` to access health. Remaining requests are denied. This is a minimal application configuration solely for the experiment; an application with business APIs needs policies for those APIs.

The fixed passwords are for local use only. BCrypt hashes them before storing them in the in-memory user store. HTTP Basic over a network must be protected with HTTPS and use properly managed credentials.

`roles("HEALTH_DETAILS")` grants authority `ROLE_HEALTH_DETAILS` to the user in this Spring Security configuration. `management.endpoint.health.roles=HEALTH_DETAILS` checks that role to decide visibility; that property does not grant any authority to any account.

## 5. Calling the Same Endpoint With Different Identities

Start in PowerShell, in the project directory:

```powershell
.\gradlew.bat bootRun
```

In Bash, use `./gradlew bootRun`. This is an application requiring Spring dependencies; the project's build workflow prepares the classpath, rather than invoking `javac` directly without libraries.

### 5.1. Sending No Credentials

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

Result:

```text
401
```

The security filter has not allowed access, so the visibility policy does not produce a successful health response for this request.

### 5.2. Permitted to Call But Not Permitted to View Details

```powershell
curl.exe -s -u "reader:reader-lab-pass" http://localhost:8080/actuator/health
```

Response:

```json
{
  "status": "UP"
}
```

The HTTP code is 200 in the synthetic healthy state. There is no `components.lab.details` because the account lacks the `HEALTH_DETAILS` role. This is the expected result, not a missing-data bug.

### 5.3. Has Detail-Viewing Role But Lacks URL Call Permission

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "details:details-lab-pass" http://localhost:8080/actuator/health
```

Result:

```text
403
```

The account has valid credentials and the `HEALTH_DETAILS` role, but the access rule requires `ENDPOINT_READER`. The visibility check does not help bypass this rule.

### 5.4. Has Both Permission Types

```powershell
curl.exe -s -u "operator:operator-lab-pass" http://localhost:8080/actuator/health
```

Response structure:

```json
{
  "status": "UP",
  "components": {
    "lab": {
      "status": "UP",
      "details": {
        "sample": "synthetic",
        "pendingJobs": 2
      }
    }
  }
}
```

JSON property order is not part of the authorization rules. When testing, compare the structure and values of interest, without relying on formatting or field order.

### Result Matrix

| Caller | Valid authentication | Has ENDPOINT_READER | Has HEALTH_DETAILS | HTTP | Health payload |
| --- | --- | --- | --- | --- | --- |
| Unauthenticated | No | No | No | 401 | Does not receive a successful health payload |
| reader | Yes | Yes | No | 200 | Aggregate status only |
| details | Yes | No | Yes | 403 | Blocked at access rule |
| operator | Yes | Yes | Yes | 200 | Includes components and details |

This matrix shows that you must verify both status codes and payload structure. Confirming only 200 misses the difference between the aggregate payload and the detailed payload.

## 6. Changing Visibility Policy While Keeping URL Permissions Intact

Each test below keeps the Java code and accounts unchanged, only changing the visibility properties and restarting. Do not mix configurations from two tests.

| show-details | show-components | roles | What does reader see? | What does operator see? |
| --- | --- | --- | --- | --- |
| `when-authorized` | `when-authorized` | `HEALTH_DETAILS` | Aggregate status only | Components and details |
| `never` | `never` | `HEALTH_DETAILS` | Aggregate status only | Aggregate status only |
| `always` | `always` | `HEALTH_DETAILS` | Components and details | Components and details |
| `when-authorized` | `when-authorized` | No role configured | Components and details | Components and details |
| `never` | `always` | `HEALTH_DETAILS` | Component name/status, no details | Component name/status, no details |

In all five cases, unauthenticated callers still receive 401 and the `details` account still receives 403. Changing visibility policy does not replace access permissions.

### Show Components Only, Hide Details

```yaml
management:
  endpoint:
    health:
      show-components: always
      show-details: never
      roles: HEALTH_DETAILS
```

For callers who pass the URL rule, the structure received is:

```json
{
  "status": "UP",
  "components": {
    "lab": {
      "status": "UP"
    }
  }
}
```

Component names are also a form of information about the system. Therefore, deliberately choose the appropriate visibility level rather than only checking whether a `details` field is present.

Health groups can have their own visibility and role configurations. If using a group such as `/actuator/health/internal`, verify the effective configuration and output of that exact group; do not assume every group behaves like the aggregate endpoint.

## 7. With env/configprops: Call Permission and Value Visibility Remain Separate

Some data endpoints have value sanitization mechanisms. Example properties for the env endpoint:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: CONFIG_DETAILS
```

This snippet illustrates the **value visibility** policy of env; it does not add env to the demo application above and does not grant permission to call `/actuator/env`. You must design endpoint exposure and access separately if actually using it.

`EnvironmentEndpointProperties` has `showValues` and `roles` properties to configure this. [Spring Boot 3.3 env config API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/env/EnvironmentEndpointProperties.html).

For env, configprops, and quartz in Spring Boot 3.3, values in responses are masked by default. `show-values` accepts `never` to keep values masked, `when-authorized` to check viewing permissions, and `always` to permit showing values for requests that passed access rules. Values can still be processed by custom `SanitizingFunction` beans; therefore, `always` does not guarantee every value is output verbatim.

Distinguish:

- Not allowed to call the endpoint: request is rejected under access policy.
- Allowed to call but not allowed to view values: response may still succeed with masked values.
- Eligible to view: values still depend on active sanitization rules.

Do not treat “values are masked” as “no sensitive information remains”. Property names, data structures, and configuration sources can still reveal system characteristics.

Nor is there a single global `roles` property that protects all Actuator endpoints in the same way. You must inspect each specific endpoint's mechanism: `health.show-details` and `env.show-values` address two different shapes of data.

## 8. Access Channels Are Part of Permission Design

`SecurityFilterChain` in the example controls HTTP. It does not create authentication or authorization policies for JMX.

Specifically for the `show-values` mechanism above, Spring Boot 3.3 treats JMX callers as eligible in the endpoint's visibility check. Do not rely on HTTP roles to conclude values are similarly masked over JMX. You must evaluate enabling the channel, exposing endpoints, and controlling JMX callers separately. [Value visibility rules over HTTP and JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

Similarly, moving management HTTP to a separate port does not by itself decide who gets to see detail data. Port, network path, identity, call permission, and visibility level must align under a single design.

## 9. Common Reasoning Mistakes

### “If login succeeds, the full JSON must be visible”

Authentication only verifies identity. The user may still lack permission to call the endpoint, or be allowed to call yet lack the condition to view details. Check each layer separately.

### “health.roles already protects the URL”

This property serves health's visibility check. To protect the URL, you must have appropriate HTTP security rules. If the URL is `permitAll()`, declaring `health.roles` does not automatically turn the URL into requiring login.

### “when-authorized always means admins only”

If no role list is configured, all authenticated users are treated as eligible under this visibility mechanism. Check both the mode and the actual role list.

### “always will bypass Spring Security”

In the experiment, the account having only `HEALTH_DETAILS` is still blocked when using `always`. Only requests passing the access rule receive the endpoint response under that policy.

### “If details are missing, relax the endpoint call permission”

Before changing access rules, check the response code. If the request already succeeded and only lacks data, check `show-details`, `show-components`, roles, group configuration, or corresponding sanitization rules.

### “Both aggregate and detailed payloads return 200 so checking response bodies is unnecessary”

A data permission test must assert which fields are present and which are hidden. At minimum, test that `components.lab.details` is absent for `reader`, the expected synthetic data is present for `operator`, and an account lacking URL permission does not receive a successful response.

## 10. Practice Exercises

1. Use the three accounts to call health; explain the results using both the Java rules and the YAML policy.
2. Change both visibility properties to `never`; confirm URL call permission does not change while `operator`'s data is reduced.
3. Change to `always`; confirm `reader` sees details while the `details` account remains blocked.
4. Restore `when-authorized`, remove the `roles` setting; observe why `reader` sees details.
5. Enable components but disable details; explain the difference between `components.lab.status` and `components.lab.details`.

When describing a caller's permissions, state completely: **how they are authenticated, which endpoints they may call, and which parts of the data they may see**. Those three pieces of information accurately assess behavior that a single “logged in” status cannot capture.
