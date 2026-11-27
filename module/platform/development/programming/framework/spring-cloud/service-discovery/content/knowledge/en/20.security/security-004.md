# CSRF Scope for the Eureka API and Protecting Remaining Paths

Eureka Client sends registration, heartbeat, and deregistration requests to the Eureka Server REST API. State-changing operations typically use POST, PUT, or DELETE under the default path `/eureka/**`. Spring Security enables CSRF protection for state-changing requests, so a backend client without a CSRF token may receive `403 Forbidden`.

The solution is to exempt CSRF strictly within the scope of the Eureka API while still requiring authentication and authorization. The dashboard, Actuator, and administrative endpoints continue to be protected by default CSRF protection.

## Why Does the Eureka API Encounter CSRF?

CSRF (Cross-Site Request Forgery) protects state-changing endpoints when browsers automatically attach user credentials, such as session cookies. Spring Security enables CSRF protection by default for unsafe HTTP methods like `POST`, `PUT`, `PATCH`, and `DELETE`.

Eureka Client is a backend application calling Eureka Server via REST. The client does not operate as a session-based browser and does not automatically fetch/send a user CSRF token. When the client sends a registration or heartbeat request, the CSRF filter may block the request before the Eureka Controller processes it.

| Eureka Operation | Common HTTP Method | Purpose |
|---|---|---|
| Register instance | `POST` | Create an application/instance record in the registry |
| Renew lease/heartbeat | `PUT` | Report that the instance is still active |
| Deregister | `DELETE` | Remove the instance from the registry during controlled shutdown |
| Read registry | `GET` | Retrieve the application/instance list |

The default REST endpoints of Eureka Server reside under `/eureka/**`, such as `/eureka/apps` and `/eureka/apps/{APP_NAME}`. The actual paths may change if the application sets a context path or configures different endpoints; always base rules on the URL that Eureka Client actually calls.

```mermaid
sequenceDiagram
    participant C as Eureka Client
    participant S as Spring Security
    participant E as Eureka Server
    C->>S: POST /eureka/apps/INVENTORY (Basic Auth)
    S->>S: Check CSRF by request matcher
    Note over S: /eureka/** is exempt from CSRF
    S->>S: Authenticate and check role
    S->>E: Allow request to Eureka API
    E-->>C: Registration response
```

Exempting CSRF only removes the CSRF token requirement. It does not mean requests are permitted anonymously or bypass authentication, authorization, network policies, and TLS.

## Scope to Exempt: The Eureka API

Under default configuration, the typical matcher is `/eureka/**`. This is the scope intended for the REST API called by Eureka Clients and peer Eureka Servers. Do not broaden the matcher to `/**`, `/api/**`, or the entire application if the goal is solely to handle Eureka registration.

Example Spring Security 6 configuration, commonly used with Spring Boot 3:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/eureka/**").hasRole("REGISTRY_CLIENT")
                .requestMatchers("/actuator/**").hasRole("OPS")
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .ignoringRequestMatchers("/eureka/**")
            );
        return http.build();
    }
}
```

In this example, `/eureka/**` does not require a CSRF token but still requires the `REGISTRY_CLIENT` role. `/actuator/health` is permitted for health probes; only do this if the response does not expose sensitive details. The remaining Actuator endpoints and the Eureka dashboard require the `OPS` role.

`hasRole("REGISTRY_CLIENT")` checks for the authority `ROLE_REGISTRY_CLIENT`. Operators who need to access the dashboard and inspect the registry can also be granted this role. In real systems, manage users and roles with an appropriate identity source rather than sharing a single account across all applications.

### Why Not Use csrf.disable()?

Do not use the following configuration just to fix Eureka registration errors:

```java
http.csrf(csrf -> csrf.disable());
```

This disables CSRF for the entire SecurityFilterChain. Other forms or state-changing endpoints in the application will no longer be protected by CSRF tokens. Instead, use `ignoringRequestMatchers("/eureka/**")` to exclude only the Eureka REST API. Any request not matching that matcher still passes through the CSRF filter as usual.

## Protecting Remaining Paths

When designing a SecurityFilterChain, explicitly list each endpoint group and required permissions:

| Path | Purpose | Recommended Policy |
|---|---|---|
| `/eureka/**` | Eureka REST API for clients and peers | Exempt from CSRF; still require authentication and a registry-client role |
| `/` and Eureka dashboard | Registry observation UI | Require operator account; keep default CSRF |
| `/actuator/health` | Health probe | May be opened on internal networks; do not show sensitive details |
| `/actuator/**` | Metrics, env, beans, config, and admin endpoints | Operations role only; expose only required endpoints |
| Custom admin endpoints | Refresh, maintenance, or configuration-changing operations | Require privileged role and keep CSRF |
| All other paths | Static resources or unlisted endpoints | Strict default policy; do not automatically permit all |

In the SecurityFilterChain example, `anyRequest().hasRole("OPS")` requires operator privileges for the dashboard and remaining paths. You can adjust static resources if the dashboard version you use requires dedicated access, but add exact matchers and verify you do not accidentally open administrative APIs.

Avoid adding a broad `/**` matcher with `permitAll()` after configuring Eureka. An overly broad rule can undermine preceding protective rules or expose an unintended attack surface.

## Illustrative Accounts and Roles

For the SecurityFilterChain to take effect, the application needs a `UserDetailsService` or equivalent authentication mechanism with matching roles. The snippet below uses in-memory users for lab illustration; do not use an in-memory account store as a production identity management solution.

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class UserConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${security.registry-client.username}") String clientUsername,
            @Value("${security.registry-client.password}") String clientPassword,
            @Value("${security.operator.username}") String operatorUsername,
            @Value("${security.operator.password}") String operatorPassword) {
        var registryClient = User.withUsername(clientUsername)
            .password(encoder.encode(clientPassword))
            .roles("REGISTRY_CLIENT")
            .build();
        var operator = User.withUsername(operatorUsername)
            .password(encoder.encode(operatorPassword))
            .roles("REGISTRY_CLIENT", "OPS")
            .build();
        return new InMemoryUserDetailsManager(registryClient, operator);
    }
}
```

Inject username/password into configuration from a secret manager or environment variables:

```yaml
security:
  registry-client:
    username: ${EUREKA_CLIENT_USERNAME}
    password: ${EUREKA_CLIENT_PASSWORD}
  operator:
    username: ${EUREKA_OPS_USERNAME}
    password: ${EUREKA_OPS_PASSWORD}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
```

In production, replace `InMemoryUserDetailsManager` with an appropriate user store or identity provider, assign separate permissions for clients, peers, and operators, rotate credentials, and monitor audit logs. Never commit passwords to Git or write them to logs.

## Eureka Client Authenticating with Eureka Server

Eureka Client can use HTTP Basic by placing username/password in the `service-url.defaultZone` URL. Example client configuration in a container environment:

```yaml
eureka:
  client:
    service-url:
      defaultZone: "http://${EUREKA_CLIENT_USERNAME}:${EUREKA_CLIENT_PASSWORD}@eureka-server:8761/eureka/"
    register-with-eureka: true
    fetch-registry: true
```

When the URL contains credentials, Eureka Client can send Basic Auth to Eureka Server. `eureka-server` is an internal hostname resolvable from the client's network; replace it with the actual registry hostname and port in your deployment environment.

Never put credentials directly in committed YAML. If the password contains URI user-info special characters such as `@`, `:`, `/`, or `%`, properly URL-encode the user/password components or use a transport credential mechanism suited to your version. Check logs to ensure URLs containing credentials are not printed.

### Peer Eureka Servers Are Also Clients

In a peer-aware Eureka cluster, each Eureka Server can register with and fetch the registry from peers. Peer requests to `/eureka/**` must also be authenticated and granted the appropriate role. Configure peer URLs with credentials similarly to regular clients:

```yaml
eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: "http://${EUREKA_PEER_USERNAME}:${EUREKA_PEER_PASSWORD}@eureka-b:8762/eureka/"
```

For a standalone server without peers, set `register-with-eureka: false` and `fetch-registry: false` so it does not generate client requests to nonexistent peers. Even then, the Eureka API and dashboard still require their own authentication policy.

## CSRF Does Not Replace Authentication and Authorization

These three mechanisms solve three distinct problems:

| Mechanism | Question to Answer | Example in Eureka Server |
|---|---|---|
| CSRF protection | Was the state-changing request initiated from a legitimate browser context? | CSRF token for forms/dashboard or admin endpoints |
| Authentication | Who is sending the request? | HTTP Basic, client certificate, or another identity mechanism |
| Authorization | What is that identity permitted to do? | Registry client role may call registration API; OPS role may access dashboard/Actuator |

When exempting `/eureka/**` from CSRF, requests without a token still must pass authentication and authorization. If you skip those two steps as well or use `permitAll`, any workload able to reach the endpoint can attempt to register, alter state, or read the registry depending on the API.

Do not use CORS as a substitute for CSRF. CORS primarily controls whether a browser can read cross-origin responses; it is not an authentication mechanism and does not guarantee prevention of all state-changing requests.

## Risks When Using HTTP Basic and Browsers

CSRF usually protects applications using session cookies, but HTTP Basic must also be considered if user browsers can reach the Eureka API. Browsers can cache or automatically send Basic credentials in certain situations; therefore, exempting `/eureka/**` from CSRF should not be considered safe if that API is exposed to user networks or the Internet.

To reduce risk:

- Restrict `/eureka/**` access exclusively to authorized workloads and peers via firewalls, security groups, or network policies.
- Use dedicated machine-to-machine accounts; never use operator credentials in applications.
- Enable TLS to protect Basic Auth and registry contents in transit.
- Consider mTLS or workload-to-workload identity if infrastructure supports it.
- Never expose the Eureka API directly to the Internet; place the registry in a management/backend network.
- Protect the dashboard with operator identities and retain CSRF for UI/admin paths.
- Scope read/write permissions according to the authorization capabilities of the deployed security layer.

Basic Auth only Base64-encodes username/password in the header; it does not encrypt transport. Never use plain HTTP over untrusted networks.

## If the Eureka API Runs Under a Different Context Path

The matcher `/eureka/**` assumes the REST API uses the default path. If the application sets `server.servlet.context-path`, a reverse proxy adds or strips a prefix, or server configuration changes the base path, determine the path seen by Spring Security and adjust the matcher accordingly.

Do not guess the matcher solely from external URLs. Check:

1. The client's `eureka.client.service-url.defaultZone` value.
2. Spring Boot context path and reverse proxy configuration.
3. The actual request path in access logs or tests.
4. Which SecurityFilterChain is selected if the application has multiple chains.
5. The CSRF matcher result for Eureka requests and out-of-scope requests.

If multiple `SecurityFilterChain` beans exist, a chain with a specific `securityMatcher` and higher `@Order` may handle the request first. Ensure `/eureka/**` routes through the chain with the CSRF exemption; remaining requests must match the general protection chain. A request not matching a chain does not mean it is automatically safe.

## Testing CSRF Scope

Do not test only that Eureka Client registers successfully. Verify both requests within the CSRF-exempt scope and requests outside it remain protected.

Example test using MockMvc and Spring Security Test:

```java
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class EurekaSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void eurekaApiDoesNotRequireCsrfButStillRequiresRole() throws Exception {
        mockMvc.perform(post("/eureka/apps/INVENTORY")
                .with(user("registry-client").roles("REGISTRY_CLIENT")))
            .andExpect(result -> assertNotEquals(
                403, result.getResponse().getStatus()));
    }

    @Test
    void eurekaApiStillRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/eureka/apps"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void otherMutatingPathsStillRequireCsrf() throws Exception {
        mockMvc.perform(post("/ops/maintenance")
                .with(user("operator").roles("OPS", "REGISTRY_CLIENT")))
            .andExpect(status().isForbidden());
    }

    @Test
    void otherMutatingPathsAcceptValidCsrfToken() throws Exception {
        mockMvc.perform(post("/ops/maintenance")
                .with(user("operator").roles("OPS", "REGISTRY_CLIENT"))
                .with(csrf()))
            .andExpect(result -> assertNotEquals(
                403, result.getResponse().getStatus()));
    }
}
```

These tests illustrate the filter boundary: requests to the Eureka API are not rejected simply for lacking a CSRF token; out-of-scope requests are still blocked when missing a token; authentication and roles for the Eureka API are still enforced. Real endpoint tests may return `404`, `405`, or business errors depending on the controller and payload, so do not force all tests to expect one specific success status if the goal is solely verifying CSRF.

Add tests for cases where a user with only the `OPS` role calls the registry API, or a `REGISTRY_CLIENT` user calls the dashboard/Actuator. Those requests must be rejected according to the defined authorization policy.

## Troubleshooting Common Errors

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Eureka Client receives `403` on registration | CSRF still applies to `/eureka/**` or matcher uses wrong path | Check actual request URL and `ignoringRequestMatchers` |
| Eureka Client receives `401` | Missing/wrong Basic Auth or credentials not bound | Check user, password, URL, and secret injection |
| Eureka Client receives `403` despite authenticating | User lacks `REGISTRY_CLIENT` role or request matched another rule | Check authorities and authorization matcher ordering |
| Dashboard cannot be opened | Account lacks OPS role or static resources are blocked by a rule | Check request paths and dashboard permissions |
| Actuator health returns `401` | Health matcher not permitted or endpoint path differs | Check endpoint exposure and security matchers |
| Admin endpoint accepts POST without token | CSRF was disabled globally or matcher is too broad | Re-enable CSRF and ignore only `/eureka/**` |
| Peer replication authentication fails | Peer URL lacks credentials or peer user lacks role | Sync credentials/roles bidirectionally and check TLS |
| API accessed from external network | Relying solely on CSRF or Basic Auth without network boundary | Restrict network, enable TLS/mTLS, and review firewalls |

When investigating a blocked request, determine whether the response is `401` or `403`: `401` usually indicates authentication failed; `403` can be caused by CSRF or authorization. Enable controlled Spring Security logging in test environments to inspect filter and authorization decisions, without logging Authorization headers or tokens.

## Implementation Checklist

1. Confirm the Eureka REST API base path; default is typically `/eureka/**`.
2. Exempt CSRF only for the Eureka API matcher needed to serve clients/peers.
3. Keep `httpBasic`, mTLS, or an equivalent authentication mechanism.
4. Require a dedicated role for registry clients; separate operator permissions where possible.
5. Keep CSRF enabled for the dashboard, Actuator, and admin endpoints outside the Eureka API.
6. Never use `csrf.disable()` or `permitAll()` application-wide.
7. Configure credentials via a secret manager/environment variables; do not commit to Git.
8. Use TLS and restrict network access to the registry; do not expose the Eureka API directly to the Internet.
9. Check context paths, reverse proxies, and ordering of multiple SecurityFilterChain beans.
10. Write tests confirming the Eureka API does not need CSRF yet still requires authentication/roles, while out-of-scope POSTs still require tokens.

## Conclusion

For Eureka Server, registration, heartbeat, and deregistration requests under `/eureka/**` are machine-to-machine flows and generally need a CSRF token exemption for Eureka Client to work. The exemption scope must stay narrow and must not strip away authentication or authorization: clients/peers still need proper credentials and roles. The remaining dashboard, Actuator, and administrative endpoints continue to be protected by CSRF alongside dedicated authorization policies. Combining exact matchers, TLS, network isolation, dedicated credentials, and 401/403 tests enables the Eureka API to function without exposing an unprotected surface across the rest of the server.
