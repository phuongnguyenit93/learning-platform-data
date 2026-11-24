# Testing the Endpoint Enablement, Exposure, and Security Matrix

An Actuator endpoint may be enabled in configuration yet have no HTTP route. A published route may also allow only certain callers. When testing, vary one condition at a time to identify which layer determines the outcome.

## Three Layers to Check

| Layer | Question to Answer | Example with the `info` Endpoint |
| --- | --- | --- |
| Enable endpoint or permit access | Does Actuator allow the requested operation? | Spring Boot 3.3 uses `management.endpoint.info.enabled`. From 3.4 onward, you can use `management.endpoint.info.access=none` to disable or `read-only` to allow read operations. |
| Expose over HTTP (exposure) | Is the endpoint published over HTTP? | Add `info` to `management.endpoints.web.exposure.include`. If `exclude` also contains `info`, the exclusion configuration takes precedence. |
| HTTP security | Is the caller authenticated and authorized to perform the operation? | A Spring Security filter chain can require callers to hold the `OPS` role when accessing `/actuator/info`. |

These layers solve different concerns. For instance, `access=read-only` lets Actuator provide the endpoint's read operation. The `OPS` role decides who is allowed to invoke that operation over HTTP in the test. The `management.endpoints.access.max-permitted` ceiling in versions supporting `access` can further cap operations across all endpoints. JMX exposure uses separate configuration. [Endpoints in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) · [Endpoints in Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)

## Building a Matrix for the Same Path

Use `GET /actuator/info` as the test target and keep `GET /actuator/health` as a control check. The sample configuration uses HTTP Basic. The security rule matches `/actuator/info` directly and requires the `OPS` role, even when Actuator has not mapped that path.

| `info` State | In `include` | In `exclude` | Caller | Expectation |
| --- | --- | --- | --- | --- |
| Disabled | Yes | No | `ops` | `404`. The caller passes security, but MVC has no endpoint mapping. |
| Disabled | Yes | No | Unauthenticated | `401`. The filter requires authentication before MVC looks up a mapping. |
| Read-only | No | No | `ops` | `404`. The endpoint is not exposed over HTTP. |
| Read-only | Yes | Yes | `ops` | `404`. `exclude` overrides `include`. |
| Read-only | Yes | No | Unauthenticated | `401`. Authentication required. |
| Read-only | Yes | No | `reader` | `403`. Authenticated, but lacks the `OPS` role. |
| Read-only | Yes | No | `ops` | `200` and JSON contains the `lab` field with value `matrix`. |

The first pair of cases illustrates why `401` is not enough to conclude that an endpoint is exposed. To test enablement and exposure, send requests with an identity known to be authorized. To test access permissions, keep the endpoint enabled and exposed, then vary the caller. The exact response code depends on the security chain, request matching, and error handling configuration of the application. [Securing Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.security)

## Running the Matrix with MockMvc

The example uses Java 17 or later, Gradle, Spring Boot 3.5.9, and Spring Security. MockMvc invokes the security filters and MVC dispatcher in-process. Each row of the matrix creates a fresh context so Actuator configuration takes effect from startup. In-memory user accounts and `{noop}` passwords belong strictly to the test fixture.

**`build.gradle`**

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.9')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

**`src/test/java/demo/actuator/ActuatorAccessMatrixTest.java`**

```java
package demo.actuator;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.Filter;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockServletContext;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.config.Customizer.withDefaults;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class ActuatorAccessMatrixTest {

    @ParameterizedTest(name = "{0}")
    @CsvSource(textBlock = """
        disabled for ops,         none,      true,  false, ops,       404
        disabled for anonymous,   none,      true,  false, anonymous, 401
        not published,            read-only, false, false, ops,       404
        exclude overrides include,read-only, true,  true,  ops,       404
        published for anonymous,  read-only, true,  false, anonymous, 401
        published for reader,     read-only, true,  false, reader,    403
        published for ops,        read-only, true,  false, ops,       200
        """)
    void checksInfoEndpoint(String scenario, String access, boolean includeInfo,
                            boolean excludeInfo, String caller, int expectedStatus)
        throws Exception {

        try (var context = new AnnotationConfigWebApplicationContext()) {
            context.setServletContext(new MockServletContext());
            context.getEnvironment().setConversionService(new ApplicationConversionService());
            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("matrix", Map.of(
                    "management.endpoint.info.access", access,
                    "management.endpoints.web.exposure.include", includeInfo ? "health,info" : "health",
                    "management.endpoints.web.exposure.exclude", excludeInfo ? "info" : ""
                ))
            );
            context.register(Fixture.class);
            context.refresh();

            var mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(context.getBean("springSecurityFilterChain", Filter.class))
                .build();
            assertEquals(200, mvc.perform(get("/actuator/health"))
                .andReturn().getResponse().getStatus());

            var request = get("/actuator/info");
            if (!caller.equals("anonymous")) {
                String credentials = caller + ":test-password";
                String encoded = Base64.getEncoder()
                    .encodeToString(credentials.getBytes(StandardCharsets.UTF_8));
                request.header(HttpHeaders.AUTHORIZATION, "Basic " + encoded);
            }

            var response = mvc.perform(request).andReturn().getResponse();

            assertEquals(expectedStatus, response.getStatus(), scenario);
            if (expectedStatus == 200) {
                var body = context.getBean(ObjectMapper.class).readTree(response.getContentAsString());
                assertEquals("matrix", body.path("lab").asText());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    @EnableWebSecurity
    static class Fixture {

        @Bean
        InfoContributor sampleInfo() {
            return builder -> builder.withDetail("lab", "matrix");
        }

        @Bean
        UserDetailsService users() {
            return new InMemoryUserDetailsManager(
                User.withUsername("ops").password("{noop}test-password").roles("OPS").build(),
                User.withUsername("reader").password("{noop}test-password").roles("READER").build()
            );
        }

        @Bean
        SecurityFilterChain security(HttpSecurity http) throws Exception {
            return http.authorizeHttpRequests(rules -> rules
                    .requestMatchers("/actuator/health").permitAll()
                    .requestMatchers("/actuator/info").hasRole("OPS")
                    .anyRequest().denyAll())
                .httpBasic(withDefaults())
                .build();
        }
    }
}
```

`ApplicationConversionService` enables the manually created context to bind configuration values such as `read-only`. `addFilters` registers the Spring Security filter chain in MockMvc. The `200` case also checks the data provided by `InfoContributor`, confirming that the response genuinely comes from the endpoint under test. Every case requires `/actuator/health` to return `200` so issues with the web context or shared Actuator configuration are caught immediately.

From the directory containing `build.gradle`, run the following command.

```bash
gradle test --tests demo.actuator.ActuatorAccessMatrixTest
```

Expect all seven cases to pass. For Spring Boot 3.3 projects, keep the exposure and access permission columns, and use `management.endpoint.info.enabled` with `false` for disabled rows and `true` for enabled rows. Since `info` only has a read operation, the `GET` cases keep the same meaning. For endpoints with write operations, test the HTTP method, write permission, and CSRF separately if a CSRF policy is active. A `403` response on a write can be caused either by CSRF or by an authorization rule. [Enabling Endpoints in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)
