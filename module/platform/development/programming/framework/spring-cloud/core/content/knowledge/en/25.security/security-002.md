# Authentication and Authorization for env, refresh, restart, and serviceregistry

> **Chapter:** Security
> **Module:** `SPRING_CLOUD_CORE` — understand the core foundations of Spring Cloud in distributed systems, especially Spring Cloud Commons, Context, externalized configuration, and version compatibility with Spring Boot. Learners explore refresh scope, discovery, service registry, service communication, and how to test and operate common abstractions.
> **Focus:** Actuator endpoints added by Spring Cloud can read or modify the Environment, refresh beans, restart the ApplicationContext, and change service registration status. This lesson focuses on caller authentication, role-based authorization, restricting exposed endpoints, and protecting operational actions that impact the entire service.

## 1. Why Do Management Endpoints Need Protection?

Spring Boot Actuator provides endpoints for observing and controlling an application. Spring Cloud Context and Spring Cloud Commons add several endpoints for runtime configuration and service registry operations. While useful for operations, permission to call an endpoint can be equivalent to controlling a critical part of the application.

Four endpoints require special attention:

| Endpoint | Function | Risk if Called Without Authorization |
| --- | --- | --- |
| `/actuator/env` | Read Environment; POST can update properties, rebind `@ConfigurationProperties`, and update log levels | Alters runtime configuration, exposes property names or internal details |
| `/actuator/refresh` | Reload configuration and refresh `@RefreshScope` beans | Alters application behavior while running |
| `/actuator/restart` | Close and restart `ApplicationContext` | Causes downtime, re-initializes beans and connections |
| `/actuator/serviceregistry` | GET reads registration status; POST changes registration status | Takes an instance out of traffic or brings it back into traffic |

A caller authorized to POST to `env` can modify properties affecting database connections, logging, or business behavior if keys are not restricted. A caller authorized to invoke `serviceregistry` can alter an instance's status according to the provider's capabilities. Permission to invoke `restart` can impact service availability.

Therefore, these endpoints should not be treated like ordinary business APIs. They belong to the management plane and require dedicated authentication, authorization, network restrictions, and auditing.

### Learning Outcomes

After this lesson, learners can:

1. explain the functionality and risks of `env`, `refresh`, `restart`, and `serviceregistry`;
2. distinguish between enabled, exposed, and authorized endpoints;
3. configure the list of Actuator endpoints to expose;
4. use Spring Security `SecurityFilterChain` and `EndpointRequest` to protect endpoints;
5. assign operational permissions by role;
6. restrict properties updatable via `env` POST;
7. protect POST operations and understand CSRF;
8. isolate the management port and network from business traffic;
9. test unauthenticated, unauthorized, and authorized cases;
10. establish safe auditing and operational procedures.

## 2. Three Distinct Control Layers

### 2.1. Endpoint Availability

An endpoint only works if its dependencies, auto-configuration, and endpoint conditions allow it to be created. For example, `serviceregistry` requires an appropriate `Registration` bean in the ApplicationContext. The `restart` endpoint of Spring Cloud Context is disabled by default in the documented configurations.

An unavailable endpoint cannot be enabled merely by adding its URL to the exposure list.

### 2.2. Exposure

Exposure determines whether an endpoint is exposed over HTTP or JMX. By default, Spring Boot only exposes `health` over HTTP. Other endpoints do not automatically become public URLs.

For example, the following configuration exposes only the listed endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

If management endpoints need to be exposed, add only those that are strictly necessary:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - env
          - refresh
          - serviceregistry
```

The example above does not expose `restart`. Add this endpoint only after establishing appropriate operational procedures and administrative roles; exposing it does not automatically enable a disabled endpoint.

Do not use `include: "*"` in production without a clear requirement and corresponding security controls. When both `include` and `exclude` are configured, the exclude list takes precedence.

### 2.3. Authentication and Authorization

- **Authentication:** determines who the calling user or service is. Examples: HTTP Basic, OAuth2 Resource Server/JWT, or mTLS at a gateway.
- **Authorization:** determines which endpoints that identity may call and which operations it may perform. Example: role `OPS_VIEWER` only reads observability endpoints; role `OPS_ADMIN` is permitted to invoke state-changing endpoints.

An exposed endpoint without proper authentication and authorization can become a remote control point. Conversely, a user with the right role still cannot invoke an endpoint if it has not been exposed or enabled.

## 3. Understanding Permissions per Endpoint

### 3.1. env — Reading and Updating the Environment

The `/actuator/env` endpoint provides information about property sources and properties in the Environment. Sensitive values are sanitized by Spring Boot by default in current versions, yet property names, configuration source names, and environment structure can still reveal internal details.

POST to `env` can update the Environment, rebind `@ConfigurationProperties`, and update log levels. To enable POST operations, Spring Cloud requires the configuration:

```yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(acme\.runtime\.|feature\.).*'
```

`valid-keys-regex` is a regular expression restricting which property names are allowed to be updated. For example, it allows only keys starting with `acme.runtime.` or `feature.`.

Avoid overly broad regexes like `.*` or allowing arbitrary changes to property groups that can affect security and infrastructure, such as:

- `management.*`;
- `spring.security.*`;
- `spring.datasource.*`;
- `server.*`;
- properties containing endpoints or credentials for external systems.

Enable POST only when there is a specific operational use case. If only observation is needed, expose GET according to governance policy without enabling POST. Access roles must still be restricted; regex does not replace authorization.

### 3.2. refresh — Refreshing Configuration and Beans

`/actuator/refresh` instructs Spring Cloud Context to reload applicable configuration and refresh `@RefreshScope` beans. Target beans are invalidated and recreated the next time the proxy is used.

A refresh operation can change endpoints, timeouts, feature properties, or client configurations used by beans. If a new property is invalid, the application may encounter errors after refresh even while the process remains running.

Grant refresh permission only to operations teams who understand the configuration impact. After a refresh, perform a health check or smoke test on the affected functionality.

### 3.3. restart — Restarting the ApplicationContext

`/actuator/restart` closes and restarts the ApplicationContext. This endpoint is disabled by default according to Spring Cloud Context documentation.

Restart has a broader impact than refreshing beans: the context closes, bean lifecycles are destroyed, and the container re-initializes. Connections, listeners, clients, and dependent components may be interrupted during this process.

Enable restart only when the application has appropriate operational procedures. In container/orchestrator environments, consider letting the deployment platform manage rollouts or restarts rather than exposing arbitrary restart permissions via an application endpoint.

The `pause` and `resume` endpoints can also control the lifecycle of supported components. If exposed, apply the same strict protection policies.

### 3.4. serviceregistry — Changing Registration Status

Spring Cloud Commons provides the `/actuator/serviceregistry` endpoint when the ApplicationContext has a matching `Registration` bean:

- GET returns the current registration status.
- POST accepts a JSON payload with a `status` field and requests a registration status change.

Example payload:

```json
{
  "status": "OUT_OF_SERVICE"
}
```

Accepted values depend on the service registry provider. For example, Eureka supports `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`. Do not assume these values form a universal contract for Consul or other providers.

Changing status can affect whether LoadBalancer or discovery components select an instance. For instance, transitioning an instance to `OUT_OF_SERVICE` can stop the instance from receiving new traffic according to how the integrated provider handles that status.

Only a service registry administrator role should be allowed to POST. Audit the actor, service instance, before/after status, timestamp, and reason for the change.

## 4. Building a SecurityFilterChain for Actuator

### 4.1. Default Spring Boot Behavior

If Spring Security is on the classpath and the application does not declare its own `SecurityFilterChain`, Spring Boot automatically configures protection for Actuator endpoints other than `health`.

Once the application declares any `SecurityFilterChain`, Spring Boot's automatic Actuator security configuration backs off. The application then becomes responsible for writing rules for both management endpoints and all remaining routes.

This is a common source of errors: a development team adds a SecurityFilterChain to protect business APIs and inadvertently removes default Actuator rules without adding matchers for management endpoints.

### 4.2. Role-Based Authorization

Example servlet application using Spring Security and Actuator matchers:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to(
                        "env",
                        "refresh",
                        "restart",
                        "serviceregistry",
                        "pause",
                        "resume"
                )).hasRole("OPS_ADMIN")
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS_VIEWER")
                .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

In this example:

- `OPS_ADMIN` has access to sensitive management endpoints.
- `OPS_VIEWER` has access to all remaining Actuator endpoints.
- Other business routes require an authenticated caller.

`EndpointRequest.to("env", ...)` matches endpoints by ID and their subpaths without relying entirely on hardcoded default URL strings. This is helpful when the management base path is changed.

This example targets the servlet stack on Spring Boot 4. In Spring Boot 3.x, the `EndpointRequest` package is typically `org.springframework.boot.actuate.autoconfigure.security.servlet`. For WebFlux, use security configuration and matchers designed for the reactive stack.

HTTP Basic in this example merely illustrates an authentication mechanism. Production should integrate identities from a centralized system, such as an OAuth2 Resource Server/JWT or a gateway with mTLS and secure identity propagation.

### 4.3. Roles Do Not Create Identities

`hasRole("OPS_ADMIN")` checks for the `ROLE_OPS_ADMIN` authority on the current Authentication. The application still needs to configure the authentication source and map roles from the identity provider.

Do not hard-code administrative passwords in source code or committed configuration files. Manage credentials using a secret store, identity provider, or platform provisioning mechanism. Revoke permissions when personnel or service accounts no longer have operational duties.

### 4.4. Separating a Dedicated Management SecurityFilterChain

You can create a chain that applies only to Actuator using `securityMatcher(EndpointRequest.toAnyEndpoint())`. When doing so, you must have another chain protecting the remaining application routes.

Example:

```java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher(EndpointRequest.toAnyEndpoint());

    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .requestMatchers(EndpointRequest.to(
                    "env", "refresh", "restart", "serviceregistry", "pause", "resume"
            )).hasRole("OPS_ADMIN")
            .anyRequest().hasRole("OPS_VIEWER")
    );

    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
```

This chain only handles Actuator. An additional SecurityFilterChain with an appropriate order must be configured to protect business endpoints. Otherwise, requests that do not match the Actuator chain will not be protected by this chain.

## 5. Protecting POST Operations and CSRF

### 5.1. POST Is a State-Changing Operation

Among the endpoints under consideration:

- `POST /actuator/env` updates the Environment;
- `POST /actuator/refresh` reloads configuration and refresh scope;
- `POST /actuator/restart` restarts the context;
- `POST /actuator/serviceregistry` changes registration status.

These are operations with side effects. Do not only test whether an endpoint is accessible via GET and conclude it is fully protected.

### 5.2. CSRF Protection

Spring Security enables CSRF protection by default for applicable web applications. When a POST endpoint is protected by CSRF, requests without a valid CSRF token may receive HTTP 403 even if the caller is logged in.

Do not disable CSRF globally just to make a curl POST command work. For browser clients using sessions/cookies, supply and submit CSRF tokens. For management APIs intended solely for machine-to-machine communication, design stateless authentication with bearer tokens and a CSRF policy suited to that client model.

Spring Boot documentation recommends disabling CSRF completely only when the service is consumed by non-browser clients. Clarify the authentication mechanism before changing this policy.

### 5.3. Distinguishing 401, 403, and 404

| HTTP status | Common Meaning | Where to Check |
| --- | --- | --- |
| 401 Unauthorized | Unauthenticated or invalid credentials | Token, Basic credentials, identity provider |
| 403 Forbidden | Authenticated but missing permission, or missing CSRF token | Role/authority, CSRF policy |
| 404 Not Found | Endpoint not exposed, unavailable, or wrong URL/base path | Exposure, dependencies, endpoint enablement, management base path |
| 405 Method Not Allowed | Endpoint exists but does not support that HTTP method | Check endpoint operations and use the right method |
| 400 Bad Request | Payload missing fields or invalid format | JSON body and field names required by the endpoint |

Do not resolve 403 by disabling CSRF entirely or opening the endpoint to anonymous access. First determine whether the request failed at the authentication, authorization, or CSRF filter.

## 6. Isolating the Management Port and Network

### 6.1. Using a Separate Management Port

You can move Actuator to a separate port:

```yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: health,info,env,refresh,serviceregistry
```

A separate management port separates management traffic from business traffic. However, using a different port does not automatically create authentication, authorization, or firewall rules.

Restrict this port using network policies, security groups, firewalls, or internal services. Only monitoring systems and operations teams should be permitted access. Do not publish the management port to the Internet unless explicitly required and protected by appropriate layers.

### 6.2. Management Address and Containers

If the management server is configured to bind only to loopback, components outside the process may not be able to reach it. If binding to the container's network interface, restrict ingress at the network layer.

Verify the actual topology: Kubernetes Services, Ingresses, service meshes, load balancers, and firewalls can unintentionally route management endpoints publicly even when the application did not intend to do so.

### 6.3. Separating Monitoring and Operational Permissions

Monitoring typically only needs to read health, metrics, and permitted observability data. Operations teams may need to refresh or view registrations. Higher-level administrators are required to restart or change registration status.

Do not share a single admin account across monitoring agents, deployment automation, and human operators. Each identity should have only the minimum necessary permissions.

## 7. Secure Configuration by Environment

### 7.1. Local Development

Locally, you can expose the necessary endpoints for debugging:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,refresh,serviceregistry
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(demo\.|feature\.).*'
```

Even when running locally, do not reuse this configuration in production by copying the file. Separate profiles and verify which profile is active.

### 7.2. Minimal Production Default

If production only needs health and info:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      post:
        enabled: false
```

Do not expose env, refresh, restart, or serviceregistry unless an administrative procedure requires them. The restart endpoint is disabled by default in Spring Cloud Context documentation; keep it disabled unless there is a clear justification.

### 7.3. Production Requiring Refresh

If operational procedures require configuration refresh, expose the refresh endpoint only within the management network and require an operational role:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
```

The SecurityFilterChain must still enforce authentication and the appropriate role. The exposure list is not an authorization mechanism.

### 7.4. Protecting Environment Data

Do not configure Actuator to return plaintext secrets to all users. On versions that support `show-values` configuration, retain the default sanitization mode or allow only administrative roles to view values after risk assessment.

Do not include passwords, tokens, private keys, or connection secrets in request bodies of tickets, logs, or audit records. If a secret needs rotation, use a secret management workflow with rotation and auditing rather than POSTing secret values directly through an open endpoint.

## 8. Auditing and Controlling Operational Actions

For endpoints with side effects, record:

- identity of the human user or service account performing the action;
- endpoint and HTTP method;
- target instance/application/environment;
- timestamp and outcome;
- changed property key (avoid logging secret values);
- registration status before and after;
- reason, change ticket, or approval code if required by procedure.

Audit records must be sufficient for traceability without leaking credentials. Synchronize clocks across instances to correlate logs. Protect logs from unauthorized modification/deletion and restrict read access.

Establish confirmation procedures before broad-impact operations. For example, before invoking restart or switching registration to `OUT_OF_SERVICE`, verify the remaining instance count and traffic status. This is an operational control; role authorization alone does not guarantee a safe operation.

## 9. Testing Endpoint Security

### 9.1. Testing Unauthenticated Callers

For an exposed and protected endpoint, requests without credentials must be rejected:

```java
mockMvc.perform(get("/actuator/env"))
        .andExpect(status().isUnauthorized());
```

The exact response depends on the authentication entry point. If the endpoint is not exposed, the response may be 404 instead of 401; tests must establish the expected configuration.

### 9.2. Testing Users with the Viewer Role

A user with only the `OPS_VIEWER` role can read permitted endpoints but cannot invoke administrative endpoints:

```java
mockMvc.perform(post("/actuator/refresh")
        .with(user("observer").roles("OPS_VIEWER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
```

This example assumes CSRF protection is enabled and the endpoint is exposed. `csrf()` adds a valid token so the assertion focuses on authorization.

### 9.3. Testing Users with the Admin Role

A user with the `OPS_ADMIN` role is permitted to invoke management operations if the endpoint is available and the payload is valid:

```java
mockMvc.perform(post("/actuator/refresh")
        .with(user("operator").roles("OPS_ADMIN"))
        .with(csrf()))
    .andExpect(status().is2xxSuccessful());
```

In real tests, verify the appropriate side effect or mock collaborators to confirm refresh was invoked. Do not check HTTP 2xx alone if the goal is to verify that beans were actually refreshed.

### 9.4. Testing env valid-keys-regex

Test POST `env` with an allowed property key and a disallowed key. Confirm that keys outside the whitelist are rejected or not applied according to the behavior of the version in use.

Pay special attention to sensitive namespaces such as security, datasource, management, and server. An overly broad regex can turn the env endpoint into an unrestricted configuration modification mechanism.

### 9.5. Testing serviceregistry

Test:

1. GET returns the current registration status;
2. viewer users cannot POST status changes;
3. admin users can POST valid provider-supported status values;
4. invalid statuses are rejected per provider rules;
5. auditing records the identity and before/after statuses;
6. status changes properly affect discovery/load balancing in integration.

Do not hard-code Eureka status lists in tests targeting Consul or another provider.

### 9.6. Testing restart in an Isolated Context

Restart can close the running test context. Test endpoint enablement and authorization in separate tests, and avoid invoking restart in a suite sharing an ApplicationContext. If end-to-end restart verification is needed, run the test application in a separate process or container and observe the lifecycle externally.

## 10. Common Failure Scenarios

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `/actuator/env` returns 404 | Endpoint not exposed or endpoint unavailable | Check Actuator dependency, exposure, and endpoint availability |
| POST `/actuator/env` returns 404/405 | POST not enabled or endpoint does not support operation | Check `management.endpoint.env.post.enabled` and version |
| POST `/actuator/env` rejected for a key | Key does not match `valid-keys-regex` | Check whitelist and property name |
| Request returns 401 | Missing or invalid credentials/token | Check authentication |
| Request returns 403 | Missing role or missing CSRF token | Distinguish between authorization and CSRF |
| Admin user still receives 403 | Role mapping does not produce `ROLE_OPS_ADMIN`, or invalid CSRF | Check authorities and request token |
| Refresh endpoint returns 404 | Spring Cloud Context endpoint missing or not exposed | Check dependencies, endpoint availability, and exposure |
| Restart does not work | Endpoint disabled by default or not exposed | Check endpoint enablement per release and operational policy |
| `/serviceregistry` returns 404 | No matching Registration bean | Check discovery provider and registration lifecycle |
| POST serviceregistry rejected | Status not supported by provider or insufficient permission | Check provider contract and security policy |
| Actuator loses protection after adding SecurityFilterChain | Custom chain caused Boot security auto-configuration to back off | Add matchers and rules for Actuator |
| Management port still accessible from Internet | Overly permissive network route/firewall/security group | Check ingress and network policy |

## 11. Process for Designing Administrative Permissions

When adding an endpoint to production, follow these steps in order:

1. Identify the required operation and its business/operational justification.
2. Identify the endpoint ID, HTTP method, and side effects.
3. Confirm the endpoint is available in the Spring Cloud version in use.
4. Expose the endpoint only through the required management interface.
5. Configure authentication via an identity provider or service identity.
6. Map separate roles for viewer, operator, and admin.
7. Protect POST requests with appropriate authorization and CSRF policies.
8. For env POST, restrict property keys using valid-keys regex.
9. Restrict network access to the management port.
10. Enable auditing for state-changing operations.
11. Write tests for 401, 403, success, and invalid payloads.
12. Rehearse refresh/restart/registry status changes in staging before production.

## 12. Practice Exercises

### Exercise 1 — POST env Can Modify Sensitive Configuration

An application enables POST `/actuator/env`. Operators can update both `feature.*` and `spring.datasource.*`.

Explain the risk and design a `valid-keys-regex` allowing only approved runtime property groups. State the required roles and audit fields.

### Exercise 2 — Viewer Calls refresh

A monitoring account with role `OPS_VIEWER` calls POST `/actuator/refresh` and receives 403.

Explain why this is the expected outcome. Recommend the minimum role needed for refresh and how to verify the request was not inadvertently blocked by CSRF.

### Exercise 3 — Adding a SecurityFilterChain Leaves Actuator Unprotected

After the development team adds a SecurityFilterChain for business APIs, `/actuator/env` no longer requires authentication.

Explain why Boot security auto-configuration backed off. Write matchers for sensitive endpoints and rules protecting the remaining endpoints.

### Exercise 4 — Restart Endpoint in Production

A team wants to expose `/actuator/restart` so support users can restart the service themselves.

Analyze the impact on ApplicationContext, availability, and lifecycle resources. Propose an alternative workflow or controlled operational role.

### Exercise 5 — Changing Registration Status

A Eureka instance is currently serving traffic. An operator POSTs `OUT_OF_SERVICE` via `/actuator/serviceregistry`.

Explain the expected impact on discovery and load balancing, how to validate allowed statuses, and what information should be audited.

### Exercise 6 — Separate Management Port That Is Still Insecure

An application moves Actuator to port 9001, but a public load balancer still routes traffic to this port.

Explain why a separate port does not replace authentication/authorization and propose a network policy so only monitoring and operations teams can access it.

## 13. Quick Self-Check

1. Which endpoint does Spring Boot expose over HTTP by default? **Health.**
2. Does exposure mean callers are permitted to operate the endpoint? **No, authentication and authorization are still required.**
3. Which property must be enabled for POST `/actuator/env`? **`management.endpoint.env.post.enabled=true`.**
4. Which property restricts updatable keys via env POST? **`management.endpoint.env.post.valid-keys-regex`.**
5. What does `/actuator/refresh` do? **Reloads applicable configuration and refreshes RefreshScope beans.**
6. Is `/actuator/restart` enabled by default? **No, this endpoint is disabled by default in Spring Cloud Context.**
7. Which bean does `/actuator/serviceregistry` require? **A Registration bean appropriate for the provider.**
8. Are serviceregistry statuses identical across all providers? **No, they depend on the implementation.**
9. When a custom SecurityFilterChain exists, does Boot continue auto-configuring Actuator security? **No, the application must configure the rules itself.**
10. Does `EndpointRequest.to("env")` match endpoint subpaths? **Yes, it matches by endpoint ID and its subpaths.**
11. Can Spring Security's default CSRF protection cause POST requests to return 403? **Yes, if the request lacks a valid token.**
12. Does a separate management port automatically protect endpoints? **No, security and network policies are still required.**

**Key Takeaway:** `env`, `refresh`, `restart`, and `serviceregistry` are critical control points of a service. Enable and expose only strictly necessary endpoints, authenticate identities, authorize by role, restrict updatable properties, protect POST/CSRF, isolate the management network, and audit all operations with side effects. A secure management API must control the caller, the scope of operations, and the environment impacted by those operations.

**References:**

- [Spring Cloud Commons — Application Context Services and Actuator Endpoints](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Commons — Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Boot — Actuator Endpoints, Exposure and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot API — EndpointRequest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/servlet/EndpointRequest.html)

Endpoint availability, matcher package names, access policies, and certain properties may vary across Spring Boot/Spring Cloud versions. Cross-check your project's compatible release train before applying.
