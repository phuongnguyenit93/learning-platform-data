# Masking Data Using show-values, roles, and SanitizingFunction

## 1. Masking Data for Bounded Diagnostics

When an application runs into an incident, operators may need to know where a configuration value was loaded from, which value is currently active, or whether a property group bound properly. However, diagnostic responses can also contain passwords, access keys, and internal information.

In Actuator, **sanitization** means replacing values in returned data with a safer representation, usually `******`. The application can still use the original values internally.

Three questions must be kept separate:

1. **Who is allowed to call the endpoint?** This is an access-control decision.
2. **May the caller see raw values or only masked values?** This is the `show-values` policy, optionally combined with `roles`.
3. **Are there fields that must be masked even when the caller is allowed to see raw values?** This is where `SanitizingFunction` is used.

A caller can succeed in calling the endpoint with status 200 yet receive only masked values. Conversely, a caller having the role to view raw values can still be blocked at the HTTP layer if they lack permission to call the endpoint.

The hands-on lab uses **Java 21, Spring Boot 3.3.13, and Spring MVC** to verify these three questions. Version 3.3.13 is pinned for examples in the 3.3.x line; it does not imply it is the latest version or current production choice.

## 2. What Needs Masking, and What Does This Mechanism Not Do?

`env` describes data from Spring's configuration environment; `configprops` describes beans belonging to `@ConfigurationProperties`. Those are two different views of configuration.

Example:

```yaml
demo:
  region: lab-east
  api-token: synthetic-token-not-real
```

We want callers with diagnostic rights to see `region=lab-east`, while still seeing only `api-token=******`. The token string in this article is completely synthetic data.

| Handling approach | Returned data | Internal value in the application |
| --- | --- | --- |
| Mask value | May still show field name, replaces value with mask | Preserved |
| Omit field from response | Does not return that field | May still be preserved |
| Encrypt stored data | Depends on storage and decryption | May be decrypted for use |
| Block endpoint access | Caller receives no endpoint document | Unchanged |

Masking values does not mean property names, source names, declaration locations, or other metadata disappear. Nor does it automatically mask the same secret in logs, error messages, custom endpoints, or heap dumps.

Therefore, seeing `******` in a response does not prove a secret is encrypted, removed from memory, or absent everywhere else.

## 3. show-values Chooses the Baseline Visibility Level

In the Spring Boot 3.3 line, endpoints supporting masking policies such as `env`, `configprops`, and `quartz` can use `show-values`. The default is `never`; values are masked with `******`. [Actuator 3.3 Sanitization Policy](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

For `env` and `configprops`, the properties used in this article are:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

The two endpoints have separate configurations. Changing `env`'s policy does not automatically change `configprops`'s policy.

| Mode | Once request is authorized to call the endpoint | Value not covered by extra masking rules |
| --- | --- | --- |
| `never` | Independent of value-viewing roles | Masked |
| `when-authorized` | Must satisfy endpoint's value-viewing condition | Shows original if permitted; otherwise masked |
| `always` | Requires no extra value-viewing role | Can show original |

The last column intentionally says “not covered by extra masking rules”. A `SanitizingFunction` can still mask data in `always` mode or when the caller is already permitted to view raw values.

`always` does not by itself let outsiders call the HTTP endpoint. However, if the endpoint is already public, public callers can also receive values not protected by masking functions. Do not use `always` as a quick fix for diagnostic failures in real environments.

## 4. roles Controls Value Viewing, Not Opening the HTTP Door

Example configuration:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: CONFIG_VIEWER
    configprops:
      show-values: when-authorized
      roles: CONFIG_VIEWER
```

For HTTP, when using `when-authorized`, the caller must be authenticated and satisfy the value-viewing role required by the endpoint. If no role list is configured, authenticated users are treated as eligible to view values by default. For JMX, this mechanism treats callers as authorized; do not infer that HTTP authorization also protects JMX. [Value viewing conditions over HTTP and JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

If multiple value-viewing roles are listed, any matching role is sufficient; it does not require the caller to hold all listed roles simultaneously.

Under Spring Security's default role mapping used in this article:

- `roles("CONFIG_VIEWER")` creates authority `ROLE_CONFIG_VIEWER`.
- Endpoint configuration uses role name `CONFIG_VIEWER`.
- Endpoint call permission will be configured separately using role `ACTUATOR_READER`.

We design three independent identities:

| Account | Roles | May call config endpoints? | May view raw values under when-authorized? |
| --- | --- | --- | --- |
| `reader` | `ACTUATOR_READER` | Yes | No |
| `viewer` | `ACTUATOR_READER`, `CONFIG_VIEWER` | Yes | Yes, except fields that must always be masked |
| `outsider` | `CONFIG_VIEWER` | No | No config response to view |

These are roles invented for the lab. Spring Boot does not create these accounts automatically.

Data-viewing roles do not replace `SecurityFilterChain`. If someone needs both call permission and raw-value viewing permission, both conditions must be explicitly configured. If using tokens or another role mapper, check actual authorities rather than merely looking at role names in config.

## 5. SanitizingFunction Defines Additional Masking Rules

### 5.1. Data Contract

A `SanitizingFunction` bean receives `SanitizableData` and returns `SanitizableData`.

Key members to know:

| Member | Meaning when writing the function |
| --- | --- |
| `getKey()` | Key name passed into sanitization by the endpoint |
| `getValue()` | `Object` value, not necessarily a string |
| `getPropertySource()` | Property source if present; may be `null` |
| `withSanitizedValue()` | Creates new data with value `******` |
| `withValue(value)` | Creates new data with a chosen replacement value |

`withSanitizedValue()` and `withValue(...)` do not overwrite the underlying property source; they create a new descriptor object for output. [SanitizableData Contract in 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/SanitizableData.java).

When no rule applies, return `data`. Do not return `null` to mean “skip”. Do not cast every value to `String`, and do not log raw values to trace function execution.

### 5.2. Decision Flow in Spring Boot 3.3.13

Behavior can be described in pseudocode:

```text
Original value is null?
    -> Return null.

Not allowed to show original value?
    -> Return masked value.

Allowed to show original value?
    -> Try SanitizingFunctions in the provided list.
    -> When a function changes the value from the original value, immediately return that result.
    -> If no function changed the value, return the original value.
```

Two easily missed consequences:

1. In the full-mask branch, custom functions do not need to be invoked. Do not use function invocation counts to infer the total number of masked fields.
2. Multiple functions do not automatically form a pipeline where all run to the end. The first modified value can terminate processing.

That is the direct behavior of `Sanitizer` in the version used by this article. [Sanitizer 3.3.13 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/Sanitizer.java).

If multiple rules must coordinate, a single combined function with explicit precedence is usually easier to verify than expecting every bean to run. Creating a new `SanitizableData` while keeping the value unchanged does not mean data was masked either.

### 5.3. Do Not Rely on the Word “password” for Automatic Safety

When allowing raw values to be shown, do not assume a key containing `password` or `token` will automatically be protected by a perfect secret detector.

In version 3.3.13, a `Sanitizer` with no custom functions returns the original value if the show-unsanitized flag is `true`. This article includes a dedicated test for that case.

Therefore, when switching from full masking to `when-authorized` or `always`, review masking rules for fields needing protection even from authorized viewers. Do not check only that ordinary fields became visible again.

## 6. Standalone Hands-On Project

The project consists of these files:

```text
actuator-sanitizing-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/sanitizing/
    │   │   ├── MaskingApplication.java
    │   │   ├── DemoSettings.java
    │   │   ├── DataMaskingConfig.java
    │   │   └── EndpointSecurity.java
    │   └── resources/application.yml
    └── test/java/com/example/sanitizing/
        ├── SanitizingHttpTest.java
        └── SanitizerContractTest.java
```

This is a Spring Boot application built with Maven and JDK 21. Classes depend on Spring, so do not run them standalone with `javac ClassName.java`. First build requires access to the Maven repository.

### 6.1. Dependencies: `pom.xml`

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
    <groupId>com.example</groupId>
    <artifactId>actuator-sanitizing-lab</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

### 6.2. Configuration: `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: env,configprops
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    env:
      enabled: true
      show-values: when-authorized
      roles: CONFIG_VIEWER
    configprops:
      enabled: true
      show-values: when-authorized
      roles: CONFIG_VIEWER

demo:
  region: lab-east
  api-token: synthetic-token-not-real

lab:
  auth:
    reader-password: ${READER_PASSWORD}
    viewer-password: ${VIEWER_PASSWORD}
    outsider-password: ${OUTSIDER_PASSWORD}
```

This configuration enables and exposes only two endpoints over HTTP: `env` and `configprops`. They are sensitive diagnostic endpoints; in this article, the application listens only on `127.0.0.1`, with authentication and separate authorization.

Disabling JMX and excluding all endpoints from JMX exposure ensures the article opens no management channel outside HTTP. If a real system uses JMX, design protection for that channel separately; do not rely on HTTP `roles`.

The three password environment variables must be supplied before running the application. `demo.region` and `demo.api-token` are synthetic values for observation.

### 6.3. Entry Point: `MaskingApplication.java`

Place at `src/main/java/com/example/sanitizing/MaskingApplication.java`.

```java
package com.example.sanitizing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DemoSettings.class)
public class MaskingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MaskingApplication.class, args);
    }
}
```

### 6.4. Properties Class: `DemoSettings.java`

Place at `src/main/java/com/example/sanitizing/DemoSettings.java`.

```java
package com.example.sanitizing;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public class DemoSettings {
    private String region;
    private String apiToken;

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public String getApiToken() {
        return apiToken;
    }

    public void setApiToken(String apiToken) {
        this.apiToken = apiToken;
    }
}
```

`demo.api-token` in configuration sources binds to Java property `apiToken`. Thanks to this class, we can observe the same data through both `env` and `configprops`.

Do not add an endpoint returning the raw token to “prove” the application still receives the token. Tests can read the bean inside the application context without creating a new secret-leaking endpoint.

### 6.5. Masking Rule: `DataMaskingConfig.java`

Place at `src/main/java/com/example/sanitizing/DataMaskingConfig.java`.

```java
package com.example.sanitizing;

import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DataMaskingConfig {
    @Bean
    SanitizingFunction hideLabSecrets() {
        return data -> {
            if (data.getKey() == null || data.getValue() == null) {
                return data;
            }
            String key = data.getKey()
                    .toLowerCase(Locale.ROOT)
                    .replaceAll("[^a-z0-9]", "");
            if (key.endsWith("apitoken") || key.endsWith("password")) {
                return data.withSanitizedValue();
            }
            return data;
        };
    }
}
```

The function makes three deliberate choices:

1. Do not process `null` values and do not assume a key name is always present.
2. Normalize key names to match `demo.api-token`, `apiToken`, and `DEMO_API_TOKEN` uniformly.
3. Mask the entire value when the normalized name ends with `apitoken` or `password`; return data untouched for other keys.

`Locale.ROOT` avoids case normalization depending on the host machine's default locale. The function needs not inspect the raw value to decide, makes no network calls, and logs no secrets.

This is a rule tailored for this article's dataset, not a detector for every secret. For example, a `client-secret` key, a URL containing credentials, or an `api-token[0]` element is not covered by just these two suffixes. Normalization can also collapse two distinct names into one and mask more broadly than intended.

In real environments, start from an inventory of sensitive fields and actual data shapes: Java fields, environment source names, nested keys, list elements, or maps. Then test directly on endpoint responses. Do not judge effectiveness merely by looking at Java method names.

### 6.6. Access Permissions: `EndpointSecurity.java`

Place at `src/main/java/com/example/sanitizing/EndpointSecurity.java`.

```java
package com.example.sanitizing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class EndpointSecurity {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var readableConfiguration = new AndRequestMatcher(
                EndpointRequest.to("env", "configprops"),
                request -> HttpMethod.GET.matches(request.getMethod()));

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(readableConfiguration)
                    .hasRole("ACTUATOR_READER")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        http.sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.logout(logout -> logout.disable());
        // Keep CSRF at default; no write operations are authorized.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${lab.auth.reader-password}") String readerPassword,
            @Value("${lab.auth.viewer-password}") String viewerPassword,
            @Value("${lab.auth.outsider-password}") String outsiderPassword) {
        var reader = User.withUsername("reader")
                .password(encoder.encode(readerPassword))
                .roles("ACTUATOR_READER")
                .build();
        var viewer = User.withUsername("viewer")
                .password(encoder.encode(viewerPassword))
                .roles("ACTUATOR_READER", "CONFIG_VIEWER")
                .build();
        var outsider = User.withUsername("outsider")
                .password(encoder.encode(outsiderPassword))
                .roles("CONFIG_VIEWER")
                .build();
        return new InMemoryUserDetailsManager(reader, viewer, outsider);
    }
}
```

This security chain covers all HTTP requests. Only GET to the two config endpoints is permitted when the caller holds `ACTUATOR_READER`; all other requests are denied. The `EndpointRequest` matcher relies on Actuator-managed endpoint locations, rather than opening all application paths.

The `outsider` account has the value-viewing role without the endpoint-reading role. That proves one condition does not automatically substitute for the other.

The example keeps default CSRF configuration and authorizes no write operations. There is no need to disable CSRF to read data via GET.

In-memory accounts and BCrypt are used so the lab runs standalone. In a real system, operator identities must be managed per individual, with revocation and audit capabilities. Changing environment passwords in the example requires restarting to recreate the in-memory accounts.

## 7. Run and Read the Results

### 7.1. Startup

In the directory containing `pom.xml`, using PowerShell with `JAVA_HOME` pointing to JDK 21:

```powershell
$env:READER_PASSWORD = 'reader-local-demo-only'
$env:VIEWER_PASSWORD = 'viewer-local-demo-only'
$env:OUTSIDER_PASSWORD = 'outsider-local-demo-only'
mvn spring-boot:run
```

The three passwords above are public data solely for the local lab. Do not use them on real servers. When transmitting credentials over a network, use HTTPS with proper certificate verification; HTTP Basic provides no confidentiality via Base64 encoding alone.

### 7.2. Distinguishing 200 With Masked Data From Access Denial Codes

Open a second PowerShell terminal:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -o NUL -w "%{http_code}\n" -u reader:reader-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -o NUL -w "%{http_code}\n" -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -o NUL -w "%{http_code}\n" -u outsider:outsider-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
```

Results in exact order:

```text
401
200
200
403
```

The two 200 responses have different data levels. Inspect the JSON documents:

```powershell
curl.exe -s -u reader:reader-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/env/demo.region
curl.exe -s -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/env/demo.api-token
```

Read the `property.value` field in the responses:

| Request | Value at property.value |
| --- | --- |
| `reader` reads `demo.region` | `******` |
| `viewer` reads `demo.region` | `lab-east` |
| `viewer` reads `demo.api-token` | `******` |

The response also includes source details and other metadata, so do not treat the entire JSON as a fixed string. Here we inspect the exact field holding the value and verify the raw token does not appear anywhere in the entire response.

Passwords in the commands are synthetic data for reproducibility. When using real credentials, avoid placing passwords in shell history or process argument lists; you can use `curl.exe -u viewer` to prompt interactively for the password.

### 7.3. Cross-Checking configprops

```powershell
curl.exe -s -u reader:reader-local-demo-only http://127.0.0.1:8080/actuator/configprops
curl.exe -s -u viewer:viewer-local-demo-only http://127.0.0.1:8080/actuator/configprops
```

Inside `contexts`, find the bean with `prefix` equal to `demo`, then read `properties`.

For `reader`, this bean's values section is:

```json
{
  "region": "******",
  "apiToken": "******"
}
```

For `viewer`, that section is:

```json
{
  "region": "lab-east",
  "apiToken": "******"
}
```

The JSON blocks above are only the `properties` part of the `demo` bean, not the entire HTTP document. Do not hardcode bean IDs or context names by guessing; the test locates the bean by `prefix`.

You should also inspect configuration input descriptions in the document, such as `inputs`, rather than checking only fields under `properties`. The test checks that the entire response does not contain the initial synthetic token.

### 7.4. Changing Modes and Predicting Results Beforehand

Stop the application, then rerun with both endpoints using the same mode:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.endpoint.env.show-values=never --management.endpoint.configprops.show-values=never"
```

Or:

```powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.endpoint.env.show-values=always --management.endpoint.configprops.show-values=always"
```

These are two alternative runs, not two applications running simultaneously on port 8080. The password environment variables must still be present in the startup terminal's environment.

Prediction matrix for `demo.region`:

| show-values | reader | viewer | outsider |
| --- | --- | --- | --- |
| `never` | HTTP 200, `******` | HTTP 200, `******` | HTTP 403 |
| `when-authorized` | HTTP 200, `******` | HTTP 200, `lab-east` | HTTP 403 |
| `always` | HTTP 200, `lab-east` | HTTP 200, `lab-east` | HTTP 403 |

For `demo.api-token`, every permitted response for `reader` and `viewer` must still have value `******`. `SanitizingFunction` is what creates this difference.

## 8. Testing to Prove Every Layer Works

### 8.1. Testing Three Modes Through Spring MVC and Spring Security

Place the following file at `src/test/java/com/example/sanitizing/SanitizingHttpTest.java`.

The test uses `WebApplicationContextRunner` to create an isolated context for each mode, loads `application.yml` via `ConfigDataApplicationContextInitializer`, and builds MockMvc with Spring Security filters. Requests use HTTP Basic through the authentication filter.

No real network port needs to be opened for this test. It tests in-application request handling and does not replace TLS, firewall, or port access verification in the deployment environment.

```java
package com.example.sanitizing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class SanitizingHttpTest {
    private static final String MASK = "******";
    private final ObjectMapper json = new ObjectMapper();

    @ParameterizedTest
    @ValueSource(strings = {"never", "when-authorized", "always"})
    void visibilityPolicyIsEnforcedOverHttp(String mode) {
        new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(MaskingApplication.class)
                .withPropertyValues(
                        "management.endpoint.env.show-values=" + mode,
                        "management.endpoint.configprops.show-values=" + mode,
                        "lab.auth.reader-password=reader-test-only",
                        "lab.auth.viewer-password=viewer-test-only",
                        "lab.auth.outsider-password=outsider-test-only")
                .run(context -> {
                    MockMvc mvc = MockMvcBuilders
                            .webAppContextSetup(context.getSourceApplicationContext())
                            .apply(springSecurity())
                            .build();

                    assertThat(call(mvc, "/actuator/env/demo.region", null)
                            .getStatus()).isEqualTo(401);
                    assertThat(call(mvc, "/actuator/env/demo.region", "outsider")
                            .getStatus()).isEqualTo(403);

                    for (String user : new String[]{"reader", "viewer"}) {
                        boolean canSeeOriginal = mode.equals("always")
                                || (mode.equals("when-authorized")
                                        && user.equals("viewer"));
                        String expectedRegion = canSeeOriginal ? "lab-east" : MASK;

                        var region = call(mvc, "/actuator/env/demo.region", user);
                        assertThat(region.getStatus()).isEqualTo(200);
                        assertThat(json.readTree(region.getContentAsString())
                                .path("property").path("value").asText())
                                .isEqualTo(expectedRegion);

                        var token = call(mvc, "/actuator/env/demo.api-token", user);
                        assertThat(token.getStatus()).isEqualTo(200);
                        assertThat(json.readTree(token.getContentAsString())
                                .path("property").path("value").asText())
                                .isEqualTo(MASK);
                        assertThat(token.getContentAsString())
                                .doesNotContain("synthetic-token-not-real");

                        var config = call(mvc, "/actuator/configprops", user);
                        assertThat(config.getStatus()).isEqualTo(200);
                        JsonNode properties = findDemoProperties(
                                config.getContentAsString());
                        assertThat(properties.path("region").asText())
                                .isEqualTo(expectedRegion);
                        assertThat(properties.path("apiToken").asText())
                                .isEqualTo(MASK);
                        assertThat(config.getContentAsString())
                                .doesNotContain("synthetic-token-not-real");
                    }

                    assertThat(context.getEnvironment().getProperty("demo.api-token"))
                            .isEqualTo("synthetic-token-not-real");
                    assertThat(context.getBean(DemoSettings.class).getApiToken())
                            .isEqualTo("synthetic-token-not-real");
                });
    }

    private MockHttpServletResponse call(MockMvc mvc, String path, String user)
            throws Exception {
        var request = get(path);
        if (user != null) {
            request.with(httpBasic(user, user + "-test-only"));
        }
        return mvc.perform(request).andReturn().getResponse();
    }

    private JsonNode findDemoProperties(String body) throws Exception {
        for (JsonNode context : json.readTree(body).path("contexts")) {
            for (JsonNode bean : context.path("beans")) {
                if (bean.path("prefix").asText().equals("demo")) {
                    return bean.path("properties");
                }
            }
        }
        throw new AssertionError("Missing demo configuration properties");
    }
}
```

These checks serve distinct purposes:

- 401 and 403 prove the access-control layer still works.
- `region` proves the three visibility modes behave properly per role.
- `apiToken` proves the extra masking rule still holds even when raw values of other fields are shown.
- Checking both `env` and `configprops` proves more than a single view is protected.
- Checking the entire response body catches tokens leaked elsewhere in the document.
- Reading `Environment` and `DemoSettings` proves output masking does not erase values used by the application.

Passwords in test properties are synthetic data. The test does not need the password environment variables from the application run session.

### 8.2. Contract Testing the Masking Function

Place the following file at `src/test/java/com/example/sanitizing/SanitizerContractTest.java`.

```java
package com.example.sanitizing;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.endpoint.SanitizableData;
import org.springframework.boot.actuate.endpoint.Sanitizer;

import static org.assertj.core.api.Assertions.assertThat;

class SanitizerContractTest {
    @Test
    void configuredSecretSpellingsAreMasked() {
        var sanitizer = new Sanitizer(
                List.of(new DataMaskingConfig().hideLabSecrets()));
        for (String key : new String[]{
                "demo.api-token", "apiToken", "DEMO_API_TOKEN",
                "lab.auth.viewer-password"}) {
            var data = new SanitizableData(null, key, "test-secret");
            assertThat(sanitizer.sanitize(data, true)).isEqualTo("******");
        }
    }

    @Test
    void ordinaryValueAndNullKeepTheirMeaning() {
        var sanitizer = new Sanitizer(
                List.of(new DataMaskingConfig().hideLabSecrets()));
        assertThat(sanitizer.sanitize(
                new SanitizableData(null, "demo.region", "lab-east"), true))
                .isEqualTo("lab-east");
        assertThat(sanitizer.sanitize(
                new SanitizableData(null, "demo.api-token", null), false))
                .isNull();
    }

    @Test
    void allowedOriginalHasNoAutomaticPasswordNameProtection() {
        var sanitizer = new Sanitizer();
        var data = new SanitizableData(null, "demo.password", "test-secret");
        assertThat(sanitizer.sanitize(data, true)).isEqualTo("test-secret");
        assertThat(sanitizer.sanitize(data, false)).isEqualTo("******");
    }

    @Test
    void firstChangedValueStopsLaterFunctions() {
        var data = new SanitizableData(null, "demo.api-token", "test-secret");
        var sanitizer = new Sanitizer(List.of(
                value -> value.withValue("first-mask"),
                value -> value.withValue("second-mask")));
        assertThat(sanitizer.sanitize(data, true)).isEqualTo("first-mask");
    }
}
```

These four tests verify behaviors easily misunderstood when looking only at an endpoint's masked output:

1. Chosen key spellings are protected, even without a `PropertySource`.
2. Ordinary values stay intact when raw output is permitted; `null` is not turned into a fake secret.
3. A key name containing `password` is not automatically masked when raw output is allowed and no custom function is present.
4. The first value-changing function terminates processing; later functions are not guaranteed to run.

Do not add tests using real secrets. A synthetic test token with a distinctive marker catches leaks without putting sensitive information into source code or test reports.

### 8.3. Running Tests

In the directory containing `pom.xml`:

```powershell
mvn test
```

Output to see on success:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Three parameterized runs of `SanitizingHttpTest` plus four tests of `SanitizerContractTest` make seven cases. Spring startup logs and timings can differ across machines.

This test suite does not verify every endpoint or every payload of another application. When adding configuration fields or upgrading Spring Boot versions, re-verify response shapes and corresponding masking rules.

## 9. Choosing Policies for Real Environments

### 9.1. Prefer Full Masking When Raw Values Are Unneeded

If a job only needs to check whether a key is present, which source supplies it, or which property group loaded, evaluate whether `never` already suffices.

Do not switch to `always` just because a response contains many masks. First identify which fields a task truly needs, who needs to read them, and for how long.

Full masking also does not replace endpoint authorization: configuration metadata can still reveal application and environment structure.

### 9.2. when-authorized Is a Data-Exposure Decision

When enabling `when-authorized`, users satisfying the role can receive raw values of many properties not covered by masking rules. With the `env` endpoint, the scope can extend beyond the configuration groups defined by the application itself.

Therefore you must:

1. Clearly identify the allowed viewer group and actual role mapping.
2. Audit configuration sources and the catalog of sensitive fields.
3. Add masking rules for fields that must never be revealed even to that group.
4. Inspect both main data and input, source, and error descriptions.
5. Pair permission changes with revocation, monitoring, and re-evaluation when the need ends.

In the lab design, matching two suffixes is enough to illustrate. It is not a configuration to copy verbatim into every production system.

### 9.3. Choosing Allowlists or Denylists Based on Real Data

Lists of names to mask are easy to understand, yet can miss a new secret field. An allowlist of names permitted to be shown can limit that risk, yet needs enough context not to accidentally expose colliding field names.

For example, two different beans both have a `value` or `token` field. Looking only at the leaf field name may not suffice to determine what is safe to expose. A rule relying on source names must also not assume `getPropertySource()` is always non-null.

If a reliable allow boundary cannot be defined, keeping `never` or providing a narrow diagnostic mechanism with explicitly chosen data is usually easier to verify than exposing raw values of the entire configuration.

A masking function should be a pure transformation: decide from input data and return a new descriptor. Avoid network lookups, mutating configuration objects, or deciding based on a user identity pulled implicitly from elsewhere.

## 10. Mistakes That Easily Leak Data or Cause Misinterpretation

| Mistake | Why it is wrong | How to verify or adjust |
| --- | --- | --- |
| Treating `roles` as the list of callers allowed to invoke the endpoint | Raw-value viewing role and HTTP permission are two separate conditions | Test an account with the viewing role but lacking call permission |
| Leaving roles blank and assuming nobody can view raw values | With when-authorized over HTTP, authenticated users are eligible to view by default | Declare roles explicitly and test callers outside the group |
| Assuming `always` still masks all passwords by name | Raw values are shown if no masking rule applies | Test secret keys when raw values are permitted |
| Configuring only `env` | `configprops` can present another view of configuration | Check policy and response of each endpoint |
| Checking only `properties` in configprops | Data may also appear in inputs descriptions | Verify the entire response contains no test token marker |
| Thinking the masking function alters Environment or beans | The function transforms output descriptor data | Verify internal values stay accurate without adding a secret-returning endpoint |
| Returning `null` when not masking | Violates the data contract used by Sanitizer | Return `data` unchanged |
| Casting every value to String | Input values may not be strings | Match by key or handle types safely |
| Logging raw values inside the masking function | The protection mechanism itself creates a leak path | Never log secrets; trace only necessary non-sensitive info |
| Assuming every custom function runs | The first modified value can end processing | Use a combined rule or test actual list and order |
| Testing only YAML key names | Other endpoints may use Java field names or differently formatted keys | Test env, configprops outputs and actual key formats |
| Believing HTTP roles also protect JMX | The two channels have different access mechanisms | Disable unused channels or protect separately |
| Treating mask symbols as proof secrets no longer exist | Values in memory and other output paths remain independent | Check logs, custom APIs, and related diagnostic paths |

Two testing mistakes must also be avoided:

- **Testing secret fields only with never.** When all values are masked, a missing or buggy custom function can go undetected. Also test a mode that allows raw values.
- **Testing only callers allowed to view raw values.** You must also prove callers with only endpoint-call permission still receive masked output, and callers lacking call permission are genuinely rejected.

## 11. Extension Exercise With Clear Criteria

Suppose we add:

```yaml
demo:
  client-secret: synthetic-client-secret-not-real
```

With the current two-suffix rule, you must not assume the new field is protected when raw values are allowed to be shown.

Implement in the lab project:

1. Write tests showing the new field must be masked in `env` across all three modes.
2. If the field belongs to a `@ConfigurationProperties` bean, check the `configprops` response too.
3. Add a rule matching the field name using real key spellings, not only an unverified Java name.
4. Confirm `region` still shows properly for authorized viewers; avoid masking everything just to make the secret-field test pass.
5. Confirm the application still receives the right raw value and the synthetic token appears nowhere in test responses.

The goal is an explainable and verifiable policy: callers must be allowed into the endpoint; visibility level decides raw-value viewing permission; identified sensitive fields stay masked via additional rules; configuration values used by the application remain unchanged.
