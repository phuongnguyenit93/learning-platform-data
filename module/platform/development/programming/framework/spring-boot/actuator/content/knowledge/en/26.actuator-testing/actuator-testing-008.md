# Verifying Sensitive Data Sanitization by Role

Actuator can help operations teams inspect which configuration an application has received. The same response can contain deployment region names, token values, and configuration source metadata. When testing, verify two independent decisions. **Who is allowed to call the endpoint?** And **which raw values is that caller allowed to see in the response?**

## Control Layers

| Layer | Related Configuration | Evidence to Verify |
| --- | --- | --- |
| Expose endpoint over HTTP | `management.endpoints.web.exposure.include` | Is the endpoint registered on the expected path and management port? |
| Endpoint call authorization | `SecurityFilterChain` rules | With HTTP Basic in the example, unauthenticated receives 401; authenticated without the role receives 403. |
| Value visibility permissions | `management.endpoint.<id>.show-values` and `management.endpoint.<id>.roles` | Two callers can both receive HTTP 200 yet see different values. |
| Per-value sanitization rules | `SanitizingFunction` bean | Sensitive data remains masked even for callers authorized to view raw values. |

`env` reports information from `Environment`. `configprops` reports information for `@ConfigurationProperties` beans, including bound configuration values (`properties`) and input data (`inputs`) when present. If the same value appears in multiple places, tests must cover every location where it could be exposed.

In Spring Boot 3.3 and 3.5, both endpoints mask values by default with `******`. `show-values=never` keeps masking enabled for all callers. `show-values=when-authorized` allows showing values to callers with configured roles when custom sanitization rules permit. Declare `roles` explicitly when enabling this mode because by default, every authenticated HTTP user is eligible to view values. `show-values=always` skips the role check at the value-visibility layer, while HTTP access rules and custom sanitization rules still apply. JMX is a separate channel with different visibility rules than HTTP. If JMX is exposed, test that channel separately.

## Test Matrix

The fixture uses two dummy values. `lab.region` is allowed to be shown to `OPS`. `lab.api-token` is a marker string used to detect leaks. The sanitizing function preserves the value for the `lab.region` key and masks all remaining keys. Consequently, a role authorized to view raw values still sees only fields whose names are in the example's allowlist.

| Caller | HTTP Code | Region Value | Token Value |
| --- | --- | --- | --- |
| Unauthenticated | 401 | Request blocked | Request blocked |
| Authenticated, role `OTHER` | 403 | Request blocked | Request blocked |
| Role `VIEWER` | 200 | `******` | `******` |
| Role `OPS` | 200 | `ap-southeast-1` | `******` |

## Integration Example with MockMvc

The example uses Java 17, Spring Boot 3.5.9, and Spring Security. `@SpringBootTest` loads the Actuator configuration. `@AutoConfigureMockMvc` sends mock requests through Spring MVC and the security filter chain. Each authenticated test case sends an HTTP Basic header using a test account so the filter chain performs authentication and authorization.

Create `pom.xml` in the project directory.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.9</version>
        <relativePath/>
    </parent>
    <groupId>demo.actuatorsafe</groupId>
    <artifactId>actuator-sanitization-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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
    </dependencies>
</project>
```

Create `src/main/resources/application.properties`.

```properties
management.endpoints.web.exposure.include=env,configprops
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=OPS
management.endpoint.configprops.show-values=when-authorized
management.endpoint.configprops.roles=OPS
lab.region=ap-southeast-1
lab.api-token=DEMO-ONLY-SECRET-7f21
```

Create `src/main/java/demo/actuatorsafe/SanitizationApp.java`. The `{noop}` passwords and marker token are strictly for this lab. The `denyAll()` policy at the end of the filter chain is intended for this sample application dedicated to testing these two endpoints.

```java
package demo.actuatorsafe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
@EnableConfigurationProperties(LabProperties.class)
public class SanitizationApp {
    public static void main(String[] args) {
        SpringApplication.run(SanitizationApp.class, args);
    }

    @Bean
    SanitizingFunction exposeOnlyLabRegion() {
        return data -> "lab.region".equals(data.getKey()) ? data : data.withSanitizedValue();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("viewer").password("{noop}lab-only").roles("VIEWER").build(),
                User.withUsername("ops").password("{noop}lab-only").roles("OPS").build(),
                User.withUsername("other").password("{noop}lab-only").roles("OTHER").build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                        .requestMatchers(EndpointRequest.to("env", "configprops"))
                        .hasAnyRole("VIEWER", "OPS")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@ConfigurationProperties("lab")
record LabProperties(String region, String apiToken) {
}
```

Create `src/test/java/demo/actuatorsafe/SanitizationTest.java`. The 200 cases check both the values at the exact JSON fields and the absence of the dummy token anywhere in the full response body from each URL under test. Checking exact fields catches calling the wrong URL, incorrect JSON structure, or missing fields. Checking the entire body catches the token appearing in locations other than the primary field.

```java
package demo.actuatorsafe;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(print = MockMvcPrint.NONE)
class SanitizationTest {
    private static final String ENV_REGION = "/actuator/env/lab.region";
    private static final String ENV_TOKEN = "/actuator/env/lab.api-token";
    private static final String CONFIG = "/actuator/configprops/lab";
    private static final String MASK = "******";
    private static final String REGION = "ap-southeast-1";
    private static final String FAKE_TOKEN = "DEMO-ONLY-SECRET-7f21";

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void anonymousGets401() throws Exception {
        mvc.perform(get(ENV_TOKEN)).andExpect(status().isUnauthorized());
        mvc.perform(get(CONFIG)).andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserWithoutEndpointRoleGets403() throws Exception {
        mvc.perform(get(ENV_TOKEN).header(HttpHeaders.AUTHORIZATION, basic("other")))
                .andExpect(status().isForbidden());
        mvc.perform(get(CONFIG).header(HttpHeaders.AUTHORIZATION, basic("other")))
                .andExpect(status().isForbidden());
    }

    @Test
    void viewerSeesOnlyMaskedValues() throws Exception {
        assertVisibleValues("viewer", MASK);
    }

    @Test
    void opsSeesRegionButTokenRemainsMasked() throws Exception {
        assertVisibleValues("ops", REGION);
    }

    private void assertVisibleValues(String user, String expectedRegion) throws Exception {
        JsonNode envRegion = readWithoutToken(user, ENV_REGION);
        assertEquals(expectedRegion, envRegion.at("/property/value").asText());

        JsonNode envToken = readWithoutToken(user, ENV_TOKEN);
        assertEquals(MASK, envToken.at("/property/value").asText());

        JsonNode config = labBean(readWithoutToken(user, CONFIG));
        assertEquals(expectedRegion, config.at("/properties/region").asText());
        assertEquals(MASK, config.at("/properties/apiToken").asText());
        assertEquals(expectedRegion, config.at("/inputs/region/value").asText());
        assertEquals(MASK, config.at("/inputs/apiToken/value").asText());
    }

    private JsonNode readWithoutToken(String user, String path) throws Exception {
        String body = mvc.perform(get(path).header(HttpHeaders.AUTHORIZATION, basic(user)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertFalse(body.contains(FAKE_TOKEN), "The response exposed the fixture token");
        return mapper.readTree(body);
    }

    private static JsonNode labBean(JsonNode body) {
        for (JsonNode context : body.path("contexts")) {
            for (JsonNode bean : context.path("beans")) {
                if ("lab".equals(bean.path("prefix").asText())) {
                    return bean;
                }
            }
        }
        throw new AssertionError("Expected a configuration properties bean with prefix lab");
    }

    private static String basic(String username) {
        return "Basic " + HttpHeaders.encodeBasicAuth(username, "lab-only", StandardCharsets.UTF_8);
    }
}
```

Run from the directory containing `pom.xml` using Maven and JDK 17 or later.

```bash
mvn test
```

When all four cases pass, the Surefire summary reports the following counts.

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

## Extending Checks for the Deployment Contract

- For endpoints that have both a root path and filtered paths, test both if users can invoke both. The example above calls `env` by property name and `configprops` by prefix to focus on the fixture data. When multiple configuration sources exist, add cases to check values across sources, alternate key names, and nested fields within your application's policy scope.
- Every case that permits viewing values should include both a value allowed to be shown and a value required to be masked. If every value is masked due to misconfiguration, the `OPS` deployment-region assertion will fail instead of giving a false pass.
- Run tests with an easily recognizable dummy secret and avoid printing responses into CI reports. Masking values can still expose key names, structure, or configuration sources. If the contract requires hiding that information as well, verify that the corresponding fields or endpoints genuinely do not appear.

Official documentation. [Actuator Value Sanitization Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization) · [env REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/env.html) · [configprops REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/configprops.html)
