# HTTP Client, Connections, Timeouts, and Resource Management

In a **Spring Security OAuth 2.0 / OIDC Resource Server** using **opaque access tokens**, authenticating a request can require the application to send a new HTTP request to the **Authorization Server** to **introspect** the token. Consequently, customizing introspection is not merely changing a URL or client secret: the Resource Server must manage the **HTTP client, TLS connections, timeouts, connection pool, resource limits, client lifecycle, and fault tolerance** as part of the authentication path.

A request with a valid bearer token can still fail if the pool runs out of connections, DNS fails, the TLS handshake is too slow, the Authorization Server responds late, or the client fails to release sockets. Conversely, trying to "fix" those incidents by accepting unintrospected tokens can break the API's security boundary.

Common Spring Boot configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

This configuration specifies the **introspection destination and credentials**. In high-traffic environments, however, you must also proactively answer:

- How long should connecting to the Authorization Server wait at most?
- If all connections in the pool are busy, how long should a request wait?
- Once connected, how long should waiting for an HTTP response take?
- Should TCP/TLS connections be reused? How many connections should the pool hold?
- When the Authorization Server errors or rate-limits, how do we both **fail closed** and avoid stalling the API?
- Who owns the HTTP client, and who is responsible for closing pools/threads when the application stops?
- Which metrics should we measure to detect pool exhaustion, latency, TLS errors, and configuration drift?

> **Context:** The Orders API runs Spring Boot 3.x / Spring Security 6.x on the Servlet stack, and the Authorization Server has the introspection endpoint `https://login.example.com/oauth2/introspect`. The timeout values and pool sizes in this lesson are **design examples**, not mandatory defaults or recommendations to copy verbatim for every system. Check the specific APIs of your Spring Security, Spring Boot, and HTTP client versions before integrating.

## 1. Why Is the HTTP Client a Security Component?

With an opaque token, the caller sends:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN
```

The Orders API must authenticate on a separate channel:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_INTROSPECTION_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN
```

There are two distinct credentials here:

1. The caller's **bearer token**, traveling from caller → Orders API.
2. The Resource Server's **introspection credentials**, traveling from Orders API → Authorization Server.

The introspection HTTP client carries **both the token under inspection and the credentials proving permission to introspect**. If it redirects to another host, disables TLS verification, or logs request bodies/headers, the application can leak these credentials.

### 1.1. Basic Processing Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as API Caller
    participant RS as Spring Resource Server
    participant Pool as Outbound HTTP Client / Pool
    participant AS as Authorization Server
    C->>RS: Authorization: Bearer opaque-token
    RS->>Pool: OpaqueTokenIntrospector.introspect(token)
    Pool->>Pool: Acquire connection / DNS / TLS
    Pool->>AS: POST introspection (token + client auth)
    AS-->>Pool: active=true/false + attributes
    Pool-->>RS: HTTP response
    RS->>RS: Validate active, map authorities
    RS->>RS: Check scope/tenant/ownership
    alt Token and permissions valid
        RS-->>C: 200 / business result
    else Token inactive or insufficient permissions
        RS-->>C: Reject
    end
```

Without caching, each API request can correspond to an outbound introspection request. Spring may verify the opaque token across consecutive requests even when the access token is the same; therefore, HTTP client behavior directly affects **latency and availability** of the Resource Server.

### 1.2. Which Parts Does Spring Security Handle?

| Component | Role |
|---|---|
| `BearerTokenAuthenticationFilter` | Extracts the Bearer token from the HTTP request |
| `OpaqueTokenAuthenticationProvider` | Coordinates opaque-token authentication |
| `OpaqueTokenIntrospector` | Contract asking whether a token is valid and returning principal/attributes |
| Introspector implementation | Sends HTTP introspection and converts the response into a principal |
| `RestOperations`/HTTP client | Controls requests, connections, TLS, timeouts, authentication, pooling |
| `AuthorizationFilter`/method security | Checks caller authorities |
| Domain service/policy | Checks tenant, ownership, resource state |

**Never modify the HTTP client to compensate for missing permission checks**: `active=true` and a successful connection do not allow every operation. The API must still verify scopes, audience/resource, client/subject, and per-object permissions.

## 2. HTTP Contract of Introspection Under RFC 7662

OAuth 2.0 Token Introspection (RFC 7662) uses a protected HTTP endpoint. The Resource Server sends the token in the **form body** of a **POST** request, optionally including `token_type_hint`:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json
Authorization: Basic BASE64_ID_COLON_SECRET

token=opaque-value&token_type_hint=access_token
```

The Authorization Server returns:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "customer-42",
  "client_id": "storefront-web",
  "aud": ["orders-api"],
  "iss": "https://login.example.com",
  "exp": 2000000000
}
```

or:

```json
{
  "active": false
}
```

Only **active tokens** can become a valid `Authentication`. An `active=true` response must still satisfy the conditions set by the Orders API.

### 2.1. HTTP 200 Does Not Mean Valid Token

An introspection endpoint normally returns **HTTP 200 with `{"active":false}`** for an inactive token. HTTP 200 only indicates that the introspection request was processed at the protocol layer; **`active`** indicates the token's state.

Conversely, HTTP 401 from the Authorization Server may be due to **wrong introspection `client-id`/`client-secret`**. It should not be interpreted as a normal `active=false` result when diagnosing incidents accurately.

| Outbound HTTP / Body | Meaning |
|---|---|
| `200 {"active":true,...}` | Introspection succeeded; proceed to enforce claim/resource policy |
| `200 {"active":false}` | Token is not accepted |
| `401` at introspection endpoint | Resource Server client authentication rejected or AS policy disallows introspecting |
| `403` at introspection endpoint | Introspection caller lacks permission under AS policy |
| `429` | AS applied rate limiting; this is not proof of a valid token |
| `5xx` | AS or infrastructure is failing |
| Timeout, TLS error, malformed response | No trustworthy introspection result |

**Do not classify every outbound error as "the user's token is invalid" and tell the user to log in again.** If the failure comes from a bad client secret or AS timeout, re-logging in will not fix the root cause.

### 2.2. Do Not Confuse `client_id` in the Response with Introspection Config

`client_id=storefront-web` in the JSON is the OAuth client **that received the access token**. It differs from `client-id=orders-api-introspector` in the Resource Server's configuration used to **authenticate when querying token state**.

Using dedicated introspection credentials per Resource Server reduces privileges and improves auditing. The HTTP client must protect those secrets; never send the client secret to the frontend.

## 3. Four Timeout Groups Commonly Confused

An HTTP call does not have just a single "timeout." HTTP client libraries typically expose distinct time thresholds.

| Type | When Does It Start/Apply? | If Exceeded |
|---|---|---|
| **Connection acquisition / pool lease timeout** | Waiting to obtain a free connection from the pool when busy | No connection available to send the request |
| **Connect timeout** | Establishing the network connection to the endpoint (precision varies by implementation) | Failed to connect within the limit |
| **Response/read/socket timeout** | Waiting for the server to send bytes/response after connecting, or waiting between reads, depending on client | Read/response wait failure |
| **Overall request deadline** | Bounds total duration of the entire introspection operation across phases | End-to-end budget exhausted; must cancel or fail |

In addition, there are **DNS lookup time**, TLS handshake time, proxy negotiation, and application queue wait time. **Not every library includes all of these in connect/read timeouts**, so read the semantics of your HTTP client version.

### 3.1. Connection Acquisition Timeout

If the application has a pool of at most 30 connections to the AS and 30 requests occupy them, the 31st request may wait in the pool's queue.

Without bounding how long acquiring a connection can wait, request threads can block for a long time even when the AS is healthy; under higher load, the queue grows and causes **pool exhaustion and thread starvation**.

Example policy:

```text
Connection request (pool lease): <= 150 ms
```

This threshold does not measure TCP connection setup speed; it only bounds waiting for **a usable connection**.

### 3.2. Connect Timeout

Connect timeout limits how long the client waits to establish a connection to the host/port. It is especially useful when:

- An IP is unreachable.
- A firewall drops packets instead of rejecting immediately.
- One endpoint among multiple IPs hangs.
- Network egress from a pod/container has issues.

Example configuration:

```text
Connect timeout: 300 ms
```

Keep in mind: DNS lookup and TLS handshake **may not be fully bounded by connect timeout** in some clients. Check separate deadlines or timeouts if end-to-end latency guarantees are needed.

### 3.3. Response/Read Timeout

An established TCP/TLS connection does not guarantee the AS responds quickly. The API must limit response wait time:

```text
Response/read timeout: 800 ms
```

Some APIs call this **socket read timeout**: idle time with no bytes received before failing, rather than total duration for the whole request. If the server trickles bytes very slowly, a pure read timeout may not bound total duration. Therefore, systems with strict SLAs should consider an **overall deadline**.

### 3.4. Overall Request Deadline and SLA Impact

Total time can include:

```text
T_total =
  T_queue_in_app
+ T_lease_from_pool
+ T_DNS
+ T_TCP_connect
+ T_TLS_handshake
+ T_send_request
+ T_wait_response
+ T_receive_response
+ T_parse_and_validate
+ T_retry_backoff_and_subsequent_attempts
```

Not every component occurs on every request: reused connections skip a fresh TLS handshake, and DNS may be cached. Still, a "1-second read timeout" **does not mean** the request is guaranteed to finish under 1 second.

Illustrative budget:

| Phase | Example Limit |
|---|---:|
| Pool wait | 150 ms |
| TCP connect | 300 ms |
| Response wait | 800 ms |
| Overall target for introspection | 1,200 ms |

These numbers **do not simply add up strictly**, because some phases do not co-occur and DNS/TLS have their own semantics. If you set an overall 1,200 ms deadline, the HTTP client or orchestration layer must actually enforce that deadline; **do not merely write 1,200 in documentation and assume it is guaranteed**.

## 4. Choose Timeouts Based on Your System, Not Someone Else's Numbers

A sound reasoning process:

1. Define the **Orders API's latency budget**, e.g., p95 below an agreed threshold.
2. Separate the time allocated for **introspection** from DB/business logic processing.
3. Measure normal AS and network latency per environment.
4. Choose connect/pool/read timeouts to detect failures quickly without dropping a significant fraction of valid requests.
5. Cap concurrent requests and retries to avoid saturating the whole API.
6. Test behavior when the AS is slow, disconnected, TLS handshakes fail, or the pool is full.
7. Re-measure whenever traffic or topology changes.

Example for an API targeting 1,500 ms response time:

```text
Inbound HTTP budget:            1,500 ms
    Introspection budget:         700 ms
    Business/DB budget:           550 ms
    Network/serialize/reserve:    250 ms
```

This is an **illustrative budget allocation**, not numbers for every API. If the AS normally has a p99 above 700 ms, optimize the AS/network or adjust the SLA contract; you cannot silently raise timeouts indefinitely.

### 4.1. Short Timeouts Can Cause Just as Many Incidents as Long Timeouts

Timeouts that are too short cause false negatives when the AS is under legitimate load, driving up 401/5xx errors and retries. Timeouts that are too long tie up threads/sockets for too long, easily overloading the entire system.

Timeout selection must be based on **latency distribution, capacity, concurrency, and error budget**, not a value "everyone uses."

## 5. Default Spring Boot Configuration with Opaque Tokens

A simple configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Security chain on the Servlet stack:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurity {

    @Bean
    SecurityFilterChain ordersChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

Here Spring Security uses `OpaqueTokenIntrospector` and the opaque token provider; it does **not** use `JwtDecoder` for access token introspection. The bearer token is sent over HTTP by the caller, while the Resource Server needs an outbound client to call the AS.

### 5.1. Why Customize `OpaqueTokenIntrospector`?

By default, the library may pick a generic HTTP client and default timeouts. When you have specific requirements for:

- Connect/read timeouts and pool lease timeouts.
- Connection pooling, TLS, proxies, mTLS.
- Observability, tracing, and request deadlines.
- Credential protection and redirect restrictions.
- Policy decorators, caching, or circuit breakers.

the application can **provide its own `OpaqueTokenIntrospector` bean** to configure the transport appropriately.

**Important note:** when a custom bean is present, Spring Boot's auto-configuration may back off to use that bean. Therefore, ensure your new implementation still performs **HTTP client authentication, `active` checks, and invalid-token handling**; do not accidentally drop all validation.

## 6. A Simple Timeout Configuration with `RestTemplate`

Spring MVC/Servlet typically uses blocking APIs such as `RestOperations` and `RestTemplate`. An easy-to-follow pattern for moderate-load applications uses `SimpleClientHttpRequestFactory`.

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;

@Configuration
public class SimpleIntrospectionHttpConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();

        // Milliseconds: example thresholds, tune per SLA.
        requestFactory.setConnectTimeout(300);
        requestFactory.setReadTimeout(800);

        RestTemplate restTemplate = new RestTemplate(requestFactory);

        // Attach the introspection client's Basic auth to outbound requests.
        restTemplate.getInterceptors().add(
            new BasicAuthenticationInterceptor(clientId, clientSecret)
        );

        // Constructor taking RestOperations is available in Spring Security
        // versions supporting NimbusOpaqueTokenIntrospector HTTP customization.
        return new NimbusOpaqueTokenIntrospector(
            introspectionUri,
            restTemplate
        );
    }
}
```

**Version note:** implementation names and constructors/builders for custom HTTP transport may differ across Spring Security branches (newer versions may provide `SpringOpaqueTokenIntrospector`). When applying this, check the Javadoc of **the exact library version in use** and preserve the core idea: standard introspector + `RestOperations` configured with HTTP client authentication and timeouts. Never replace it with a callback that claims every token is active.

### 6.1. What Does This Configuration Solve?

- `setConnectTimeout(300)` bounds connecting per the factory's semantics.
- `setReadTimeout(800)` bounds read wait time.
- `BasicAuthenticationInterceptor` authenticates the Resource Server to the introspection endpoint.
- `NimbusOpaqueTokenIntrospector` handles the introspection call and response per its implementation.
- `SecurityFilterChain` uses the authorities once the token is successfully introspected.

### 6.2. Limitations of `SimpleClientHttpRequestFactory`

`SimpleClientHttpRequestFactory` uses the traditional JDK HTTP client mechanism; it **does not provide full pool acquisition/concurrency/eviction controls** like a dedicated pooling HTTP client. Depending on the JDK platform, HTTP connections may be retained underneath, yet the application lacks an **explicitly configured pool with max-per-route, max-total, and lease timeouts** as in the Apache HttpClient example below.

For an AS with high traffic and explicit pool monitoring requirements, use an HTTP transport supporting deliberate pooling, lifecycle management, and metrics.

### 6.3. Avoid Logging Basic Auth and Tokens

The Basic interceptor is built in the server-side application, never using client credentials from incoming requests. Never add an HTTP logging interceptor that prints the full:

```text
Authorization: Basic ...
body: token=...
```

Even in dev environments, raw bearer tokens and introspection secrets remain credentials. If debugging is needed, log latency, status codes, error codes, request IDs, and allowed endpoint hostnames.

## 7. Connection Pooling: Why Does It Matter?

Each new outbound HTTPS connection can require a TCP handshake, TLS handshake, socket/file descriptor, and kernel resources. If every introspection request opens a new unpooled connection, the API incurs extra latency and pressure on:

- Socket/file descriptors.
- Ephemeral ports and `TIME_WAIT` states.
- CPU/TLS handshakes on both the API and AS.
- DNS/proxy/TLS setup.
- Network load and firewall connection tracking.

**Connection pooling** lets sequential or concurrent requests **reuse valid HTTP/TLS connections** within configured limits.

A pool does not mean tokens are cached. Tokens can still be introspected on every request while sockets are reused.

### 7.1. Total Connections vs. Per-Route Connections

| Parameter | Meaning |
|---|---|
| **Max total** | Maximum connections held by a pool across all routes/hosts |
| **Max per route** | Maximum connections for a single route such as `https://login.example.com:443` |
| **Connection request timeout** | Maximum time to wait for the pool to lease a connection |
| **Connection max lifetime/TTL** | Maximum age a connection may be reused if supported by the client |
| **Idle eviction** | Evicts connections unused for a given duration |
| **Expired eviction** | Evicts connections past their lifetime/validity |
| **Keep-alive** | Duration a connection may remain open per server/client policy |
| **Connection validate-after-inactivity** | Checks idle connections before reuse if supported by the client |

The pool must be **bounded**; too small a pool causes queuing and timeouts, while a huge pool can overload the AS and consume resources on each instance.

### 7.2. Do Not Confuse Pool Size with Thread Count

For instance, Tomcat may have 200 request threads while the introspection pool has only 20 connections to the AS. If 100 requests need introspection concurrently, 20 requests can proceed immediately while the rest wait on the pool or hit lease timeout.

Increasing Tomcat threads from 200 to 500 **does not solve** a 20-connection pool bottleneck; it may just leave more threads blocked waiting.

Conversely, raising the pool to 500 when the Authorization Server only handles 50 concurrent introspections well can overload the AS. Size pools based on **system-wide capacity**, not just the client side.

## 8. Estimating Concurrency from Rate and Latency

You can build intuition using **Little's Law** in steady state:

\[
\text{Concurrency} \approx \text{Requests per second} \times \text{Average service time (seconds)}
\]

Suppose one Orders API instance sees:

```text
500 introspection calls / second
Average outbound request time = 0.08 seconds
Estimated average in-flight = 500 × 0.08 = 40
```

During a latency spike:

```text
500 introspection calls / second
Average duration increases to 0.30 seconds
Estimated in-flight = 500 × 0.30 = 150
```

If the pool only has 40 connections, requests queue up when latency rises; queuing can push total duration past the SLA.

**This is an average estimate, not the final formula for picking pool size.** Account for burstiness, p95/p99, connection reuse, throttling, headroom, and instance count.

### 8.1. Sizing Must Sum Across All Replicas

If there are 12 pods, each with a 100-connection pool to a route, the AS could see **up to roughly 1,200 connections** from this system when all pods saturate their pools. If the AS expects only a few hundred connections, raising local pool sizes can trigger a cluster-wide outage.

A design approach:

1. Know the AS's maximum RPS/concurrent request capacity.
2. Allocate fair quotas across all Resource Servers sharing the AS.
3. Define pool and concurrency limits **per pod**.
4. Check whether autoscaling pod counts increases total connections.
5. Monitor active/idle/pending pool connections, timeouts, and AS saturation.
6. Use admission control/bulkheads to shed overload before thread pools fill up.

## 9. Pooling the HTTP Client with Apache HttpClient 5

On the Servlet stack, one option is **Apache HttpClient 5** paired with Spring's `HttpComponentsClientHttpRequestFactory`. This example demonstrates:

- Connection limits.
- Pool wait timeouts.
- Connect/socket/response timeouts.
- Connection reuse and idle eviction.
- Closing the client when the Spring container shuts down.

Add the dependency aligned with the Spring Boot BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
```

### 9.1. Defining a Spring-Managed `CloseableHttpClient`

```java
package com.example.orders.security;

import org.apache.hc.client5.http.classic.HttpClient;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IntrospectionHttpClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient introspectionHttpClient() {
        var connectionManager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(120)
                .setMaxConnPerRoute(80)
                .setDefaultConnectionConfig(
                    ConnectionConfig.custom()
                        .setConnectTimeout(
                            Timeout.ofMilliseconds(350)
                        )
                        .setSocketTimeout(
                            Timeout.ofMilliseconds(900)
                        )
                        .build()
                )
                .build();

        RequestConfig requestConfig = RequestConfig.custom()
            .setConnectionRequestTimeout(
                Timeout.ofMilliseconds(150)
            )
            .setResponseTimeout(
                Timeout.ofMilliseconds(900)
            )
            .build();

        return HttpClients.custom()
            .setConnectionManager(connectionManager)
            .setDefaultRequestConfig(requestConfig)
            .disableRedirectHandling()
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .build();
    }
}
```

**Explanation:**

- `setMaxConnTotal(120)` caps connections across the entire client.
- `setMaxConnPerRoute(80)` caps connections per route; if there is only one AS host, this is typically the effective limit.
- `ConnectionConfig` configures connect/socket timeouts at HttpClient 5's connection layer.
- `RequestConfig` configures pool acquisition and response timeouts.
- `disableRedirectHandling()` prevents automatically sending introspection data to another endpoint upon unexpected redirects.
- `evictExpiredConnections()` / `evictIdleConnections(...)` clean up unused connections.
- `@Bean(destroyMethod = "close")` ensures Spring calls `close()` on the HTTP client holding pool/thread resources when the application context stops.

**Version compatibility:** Apache HttpClient 5 API names/classes can change in detail across releases, and some setters are deprecated in newer versions. Check the version managed by the Spring Boot BOM when integrating. In particular, never copy old Apache HttpClient **4.x** configuration to **5.x**, as packages and semantics differ.

### 9.2. Creating `RestOperations` Using the Pooling Client

```java
package com.example.orders.security;

import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
public class IntrospectionRestOperationsConfiguration {

    @Bean
    RestOperations introspectionRestOperations(
            CloseableHttpClient introspectionHttpClient,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        var requestFactory = new HttpComponentsClientHttpRequestFactory(
            introspectionHttpClient
        );

        RestTemplate template = new RestTemplate(requestFactory);

        template.getInterceptors().add(
            new BasicAuthenticationInterceptor(clientId, clientSecret)
        );

        return template;
    }
}
```

Here `RestTemplate` **reuses** the container-managed HTTP client. Never create a new `CloseableHttpClient` inside each `introspect()` call or each user HTTP request.

### 9.3. Wiring `RestOperations` into `OpaqueTokenIntrospector`

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.web.client.RestOperations;

@Configuration
public class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            RestOperations introspectionRestOperations,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri) {

        return new NimbusOpaqueTokenIntrospector(
            introspectionUri,
            introspectionRestOperations
        );
    }
}
```

This pattern targets versions providing that constructor. If your Spring Security version introduces a newer implementation/builder (such as `SpringOpaqueTokenIntrospector`), use the **equivalent API** per Javadoc to supply the custom HTTP client; **never** replace `OpaqueTokenIntrospector` with a self-made function returning `active=true`.

### 9.4. Bean Lifecycle: Never Close the Pool After Each Call

**Right:**

```text
Spring application context
  ├── One CloseableHttpClient (connection pool)
  ├── One RestOperations for introspection
  └── One OpaqueTokenIntrospector
       └── Many HTTP requests reuse the same client
```

**Wrong:**

```java
// Anti-pattern illustration: creating a new client per token.
public OAuth2AuthenticatedPrincipal introspect(String token) {
    CloseableHttpClient client = HttpClients.createDefault();
    // Risks wasting connections, TLS handshakes, and leaking resources
    // if client/response are not closed along every error path.
    throw new UnsupportedOperationException("Example of bad design");
}
```

With pooling, you need **one shared client closed in a controlled way**, never closing the HTTP pool after every token. HTTP responses/bodies must be properly consumed/closed by the transport/introspector so connections return to the pool. If writing a low-level client yourself, failing to close responses prevents connections from **returning to the pool**, exhausting the pool over time.

## 10. Which Resources Must Be Managed?

| Resource | Risk If Unmanaged | Strategy |
|---|---|---|
| TCP sockets/file descriptors | File descriptor exhaustion, connection failures | Bounded pool, close lifecycle, metrics |
| HTTP connection pool | Unbounded queuing, pool exhaustion | Max per route/total, lease timeout, pending limit |
| Request threads (Servlet) | Thread starvation while waiting on AS | Timeouts, bulkheads, concurrency limits |
| TLS sessions/handshakes | Elevated CPU and latency | Reuse connections, optimize TLS properly |
| DNS cache/stale connections | Continuing to call old IPs/hosts after failover | Connection lifetime/eviction/DNS policy |
| Memory for requests/responses | Heap spikes on large/malformed payloads | Response body size limits, HTTP client policies |
| Scheduled eviction threads | Resource leaks on app shutdown | Manage in bean lifecycle, close client |
| Secrets in headers/interceptors | Credential leakage in logs/traces | Redaction, never log raw headers/bodies |
| Metrics tags | High cardinality from dynamic token/client tags | Use only status, allowed host/route, error class |
| Cache if enabled | Revoked tokens still accepted, data leakage | Short TTL per risk, protected cache keys |

### 10.1. Long-Lived Pool Resources

A connection pool normally lives for the lifetime of the instance. It is not tied one-to-one to individual user requests. Therefore:

- Create the pool at application startup or bean initialization, never per request.
- Close it on application shutdown and allow in-flight requests to finish per graceful shutdown strategy.
- Do not share an HTTP client carrying an introspection Basic credential interceptor with HTTP calls to unrelated hosts.
- Use a **dedicated HTTP client for introspection** to avoid sharing credentials, pools, and timeouts with other outbound APIs.
- In tests, close the client and fake server appropriately after each test context/suite.

### 10.2. HTTP Redirects Can Leak Tokens

If the introspection endpoint returns:

```http
HTTP/1.1 302 Found
Location: https://unexpected.example.net/collect
```

and the HTTP client automatically follows redirects with a request carrying the token/`Authorization` header, there is a risk of sending credentials to an unintended host; exact redirect-following behavior depends on implementation and status code.

**Safe approach:** the URI must be a configured/allowlisted URL; handle redirects deliberately, and for introspection **avoid automatic redirect following** unless path and credentials are controlled. Never obtain the introspection URL from HTTP headers or an unverified JWT.

### 10.3. Proxies and TLS Interception

If outbound HTTPS goes through an enterprise proxy:

- The proxy must be configured explicitly in the HTTP client/egress policy.
- If the proxy performs TLS interception, identify the organization-approved CA and content-control policies.
- Never import unknown CAs just to silence `PKIX path building failed`.
- Never place `client-secret` in proxy URLs or logs.
- Verify hostname/SNI and truststore **inside the actual container/JVM**, not only on a laptop.

## 11. TLS, Truststores, and Mutual TLS

Introspection requests carry sensitive credentials; HTTPS must protect the channel:

```text
Orders API (HTTP client)
   |
   | HTTPS + certificate validation
   v
login.example.com (introspection endpoint)
```

Verify:

1. The endpoint uses `https` in real environments.
2. The certificate SAN matches the hostname the HTTP client connects to.
3. The certificate chain is valid against the JVM truststore or TLS configuration.
4. The certificate is not expired and container clocks are accurate.
5. Never use a `TrustManager` that accepts all certificates.
6. Secrets are sent only to the exact trusted endpoint.

### 11.1. The JVM Truststore Is Not the JWT Signing Key

With introspection, the HTTPS certificate serves **endpoint authentication and transport protection**. It is not the RSA/ECDSA public key used to verify JWTs from a JWKS.

An opaque Resource Server may not fetch a JWKS, yet still needs a proper truststore/CA for the introspection connection.

### 11.2. Private CAs and Staging

Staging may use a private CA. A clean principle:

```text
Dedicated JVM truststore for staging
  └── Add only organization-approved CAs

Introspection URL:
  https://login.staging.example.com/oauth2/introspect
Certificate SAN:
  login.staging.example.com
```

Never use `--insecure` or `trustAll` in production. Never copy production credentials into staging, as environment trust boundaries differ.

### 11.3. mTLS or `private_key_jwt`

Not every AS accepts HTTP Basic client ID/secret; some endpoints require:

- **mTLS client certificate**.
- `private_key_jwt` client authentication.
- A custom contracted authentication mechanism.

With mTLS, the HTTP client must load the **Resource Server client's** certificate/private key in a keystore and configure the TLS context and rotation accordingly. An mTLS client certificate **is not a bearer token**. Never assume that establishing an HTTPS connection implies mutual mTLS authentication took place.

If the AS uses `private_key_jwt`, introspection requests must attach a client assertion per registration. A standard `BasicAuthenticationInterceptor` is **not sufficient**; an appropriate HTTP/client authentication module must be used.

## 12. Retries: Do Not Turn an AS Incident into a Request Storm

When the AS fails transiently, retrying sounds reasonable, yet a high-traffic Resource Server can worsen the outage.

Example:

```text
1,000 API requests/s
× 1 introspection per request
× 3 attempts when AS fails
= up to 3,000 HTTP attempts/s
```

If multiple replicas retry simultaneously, a **retry storm** can prevent the AS from recovering.

### 12.1. Retry Principles for Introspection

- Retry only errors **classified as transient**, if allowed by contract.
- Never retry `active=false`: that is a valid introspection result.
- Never retry HTTP `401` indefinitely for a wrong client secret.
- On `429`, honor rate limits/`Retry-After` if applicable, without holding request threads past the deadline.
- On timeouts or `5xx`, consider a small retry count with backoff and jitter.
- Every attempt must stay within the **overall request budget**.
- Never switch URIs to an AS outside the allowlist to "find whichever endpoint is alive."
- Never log tokens/secrets on each retry.

### 12.2. Retry Decision Table

| Outcome | Should Retry? | Notes |
|---|---|---|
| `200 active=true` | No | Proceed to validate claims/policy |
| `200 active=false` | **No** | Token rejected |
| `400` malformed request | Usually no | Fix configuration/request format |
| `401/403` of introspection client | Usually no | Investigate client authentication/permissions |
| `429` | Conditional | Follow quota and deadline; avoid thundering herd |
| `502/503/504` | Conditional | Only while budget remains and AS can recover |
| Connect/read timeout | Conditional | Bounded retries; watch latency/AS load |
| TLS certificate invalid | **No** | Fix truststore/certificate; never bypass TLS |

### 12.3. Use a Circuit Breaker, Yet Fail Closed

A circuit breaker can temporarily halt outbound calls when the AS fails continuously to protect servlet threads and reduce load.

```text
Circuit CLOSED → allow introspection calls
Circuit OPEN   → do not call AS, report dependency error
Circuit HALF_OPEN → probe with limited requests
```

**Never** write "when breaker is OPEN, treat `active=true`" or "when AS loses connectivity, let all tokens through temporarily." Without trustworthy introspection evidence, protected actions must not proceed.

### 12.4. Distinguishing Retries from Backpressure

- **Retries** generate extra requests for the same token.
- **Backpressure/admission control** limits how many new requests may consume introspection resources.
- **Bulkheads** cap concurrency for the AS dependency, protecting the rest of the application.

When a dependency is saturated, adding retries can cause harm; throttle load and control queues instead.

## 13. Introspection Caching: Performance vs. Revocation Delay

Caching can reduce HTTP calls to the AS. However, introspection exists to detect revoked tokens; caching too long undermines fresh state checks.

Suppose the AS revokes a token at 12:00, yet the Orders API cached `active=true` until 12:05. During those 5 minutes, the cache may keep treating the token as active unless an invalidation mechanism exists.

### 13.1. Variables to Determine

- Maximum TTL for which the product tolerates delayed revocation visibility.
- How much time remains until the access token's `exp`?
- Does the AS return a reliable `exp`?
- Can permissions/tenants/roles change during the cache window?
- Does the cache key protect the secret raw token?
- Does each pod cache locally or use a distributed cache? Is cluster-wide invalidation needed?
- Should inactive tokens be negatively cached, and for how long?
- What is the policy for cache/AS failures?

A useful inequality:

```text
effectiveCacheTTL <= min(
  configuredMaxTTL,
  remainingLifetimeUntilExp,
  acceptableRevocationDelay
)
```

This is a **design principle**, not a complete algorithm. If the response lacks `exp` when required by contract, fail closed or use an approved mechanism rather than assuming access tokens are always valid.

### 13.2. Cache Keys Must Never Expose Bearer Credentials

An opaque token is a bearer credential; anyone obtaining the token string can replay it while active. Avoid:

- Recording raw tokens as metric labels.
- Putting raw tokens into cache admin UIs or logs.
- Sending tokens to unapproved cache systems.
- Writing tokens to files/dumps/debug endpoints.
- Caching sensitive principals/permissions without access control.

You can use a properly designed hash/HMAC-derived lookup key to avoid storing plaintext tokens in keys, though you must analyze collisions, key management, and operations. Do not treat hashing the cache key as sufficient system-wide protection if the raw token still appears in cache values or logs.

### 13.3. Caching Does Not Replace HTTP Connection Pooling

**Connection pooling:** reuses TLS/HTTP connections, **still calling the AS to introspect** on every uncached request.

**Introspection caching:** reuses `active`/principal/authority results, **potentially skipping AS calls** during the TTL.

These two optimizations are independent with different risks. Pooling cuts connection overhead without making introspection results stale; caching cuts traffic at the cost of affecting revocation timeliness.

## 14. Preventing DoS When Every Token Triggers an HTTP Request

An API lets any caller send a bearer token. If every arbitrary token triggers a call to the AS, an attacker can send floods of garbage tokens to exhaust:

- Servlet threads.
- Pool connections.
- TLS handshake CPU.
- Network bandwidth.
- AS introspection capacity.
- Log/metric capacity.

Therefore, enforce **limits before or alongside authentication** without weakening security checks.

### 14.1. Mitigations

1. Rate-limit inbound requests by appropriate source/network layer.
2. Cap `Authorization` header and token length per API policy.
3. Reject syntactically invalid Bearer tokens before sending introspection calls.
4. Limit concurrent introspection calls per instance.
5. Size pools and lease timeouts to match AS capacity.
6. Consider short-lived negative caching of inactive results if contracted and safe from resource-exhaustion risks.
7. Monitor invalid-token rates, requests by source, and pending pool counts.
8. Never let clients choose the introspection URI, preventing SSRF and token exfiltration.
9. Avoid revealing overly granular differences for nonexistent tokens in responses to prevent enumeration.

**Never accept tokens merely because their syntax "looks like a real token."** Pre-introspection limits only prevent abuse; authentication must still rely on the AS and policy.

### 14.2. Prevent One Bad Actor from Exhausting the Entire Pool

If a wave of invalid-token requests can consume the entire pool, legitimate users are impacted too. You may need:

- Edge/gateway rate limiting.
- Per-caller quotas where applicable.
- Dedicated bulkheads and bounded queues for introspection.
- A connection pool large enough for normal traffic without exceeding AS capacity.
- Monitoring `pool.pending`, `connection_request_timeout`, and `introspection.error_rate`.

A huge pool cannot replace proper rate limiting.

## 15. Returning the Right Errors: Inactive Token vs. Dependency Outage

Example conditions and expected behavior:

| Condition | Authentication Result | Typical Inbound Response |
|---|---|---|
| No bearer token on a protected endpoint | Unauthenticated | `401 Unauthorized` |
| Introspection returns `active=false` | Token rejected | `401 invalid_token` |
| Token active, missing `orders.write` | Authenticated, insufficient permissions | `403 Forbidden` |
| Token active, sufficient scope, does not own order | Business authorization denied | `403` or `404` per policy |
| AS rejects client secret | Cannot verify token due to RS → AS error | Fail closed; classify configuration error |
| Pool lease timeout | No introspection result received | Fail closed; classify client overload |
| AS read timeout or TLS failure | No trustworthy result | Fail closed; report dependency failure per error mapping |
| Malformed JSON response | Cannot verify token | Reject; investigate AS/proxy/client |
| Circuit breaker OPEN | Not introspected | Never accept tokens by default |

Spring Security and HTTP error handlers may map specific exceptions to 401, 5xx, or other statuses depending on implementation and customization. **Do not claim the framework always returns 503 automatically during an AS outage.** If you need to distinguish infrastructure errors (503) from inactive tokens (401), configure exception translation and test it explicitly.

### 15.1. "Fail Closed" Does Not Mean Masking Every Error as 401

Fail closed means **denying access when authentication/authorization evidence is insufficient**. Operationally, a wrong client secret or AS outage is a service fault where returning `503 Service Unavailable` to callers may be more accurate than 401, which misleads them into thinking their personal token is bad.

However, distinguishing 401 vs. 503 must rely on the actual exception/system behavior without exposing secrets or internal details. Do not map every `RestClientException` to `401 invalid_token` without considering root-cause separation.

### 15.2. Deadlines and Request Cancellation

When a deadline expires, the HTTP client must cancel or close the pending request properly, releasing connections/responses/threads per the implementation. Timing out an outer `Future.get(...)` alone **does not guarantee** the underlying HTTP request stops.

Therefore, configure timeouts **directly on the HTTP client**, and if using an orchestration deadline, pair it with compatible cancellation/cleanup.

## 16. Observability: Measure Client Health Without Logging Tokens

Useful metrics:

| Metric/Signal | Purpose |
|---|---|
| `introspection.requests.total` | Total calls to the introspection endpoint |
| `introspection.duration` histogram/p95/p99 | Measures latency |
| `introspection.result.active/inactive` | Tracks active vs. inactive tokens statistically |
| `introspection.http.status` | Categorizes HTTP statuses from the AS |
| `introspection.error.type` | DNS, TLS, connect timeout, read timeout, parse, client auth |
| `http.pool.leased` | Connections currently in use |
| `http.pool.available` | Idle connections |
| `http.pool.pending` | Requests waiting on the pool |
| `http.pool.timeout.total` | Measures pool lease exhaustion |
| `introspection.circuit.state` | CLOSED/OPEN/HALF_OPEN |
| `introspection.cache.hit_ratio` | Only when caching is enabled and TTL/risk are understood |
| `jvm.threads.busy` / servlet active threads | Detects thread starvation |
| `AS rate_limit/429` | Alerts on capacity limits or retry storms |

Metric names in the table are **naming suggestions**, not all automatically built into Spring Security. Integrate Micrometer/Actuator, Apache HttpClient metrics, or instrument a suitable introspector wrapper.

### 16.1. Which Tags Are Safe?

Use low-cardinality tags such as:

- `outcome=active|inactive|error`.
- `error_type=timeout|tls|client_auth|invalid_response`.
- `environment=staging|prod`.
- `as_host=login.example.com` when the host is already allowlisted.
- `method=POST`, `client_type=introspection`.

**Never use raw bearer tokens, `sub`, `client-secret`, per-request IDs, or unbounded token hashes as metric tags.** They both leak information and explode cardinality.

### 16.2. What Should Logs Record?

Example:

```text
WARN introspection_failed
  requestId=...
  dependency=authorization-server
  phase=pool_acquisition
  error=timeout
  elapsedMs=151
```

Never log:

```text
token=<raw opaque access token>
Authorization=Basic <base64 client secret>
introspection_response=<all claims and PII>
```

If distributed tracing is needed, emit a span for outbound introspection with status/latency and safe attributes. Never put tokens or credentials into span attributes, baggage, or headers that exporters may persist.

## 17. Kubernetes and Multi-Instance Deployment

Suppose the Orders API runs 8 pods, each with 250 request threads and an introspection pool capped at 80 connections to the AS:

```text
8 pods × 80 connections/pod = 640 possible connections
```

That is the **theoretical ceiling from pool configuration** for one route under heavy load, not a guarantee that 640 connections are always open. Still, the AS must be sized to withstand the combined load from all pods and other Resource Servers.

### 17.1. Readiness and Graceful Shutdown

At startup:

- The app must have complete URI, TLS trust, secret, and network policy configuration.
- Do not mark the app ready if token verification cannot operate at the required readiness policy level.
- However, **never ping introspection with a real production token** in health checks. If synthetic checks are needed, use an approved credential/test path.
- Avoid having all pods reconnect/restart simultaneously and hit the AS with a spike.

On shutdown:

1. Stop accepting new requests.
2. Let in-flight requests complete within the grace period when possible.
3. Close `CloseableHttpClient` and the pool via the bean lifecycle.
4. Leave no orphaned background eviction threads or sockets behind.

### 17.2. DNS Rotation, Stale Connections, and Failover

If the AS changes IP after failover or DNS rotation, open connections may still point to the old node. Evicting idle/expired connections and setting a reasonable connection lifetime lets new connections pick up fresh DNS.

Never configure infinite connection lifetimes without stale/closed connection detection. Also, **DNS TTL** in the JVM/HTTP client and network layer may differ: an HTTP pool timeout does not by itself force a DNS refresh.

### 17.3. Environment Separation

| Environment | Example Endpoint | HTTP Client Configuration |
|---|---|---|
| Development | `https://login.dev.example.com/oauth2/introspect` | Testing timeouts, dedicated dev CA |
| Staging | `https://login.staging.example.com/oauth2/introspect` | Pool/limits sufficient for load testing, staged cert/secret |
| Production | `https://login.example.com/oauth2/introspect` | Pool sized to AS capacity, monitoring, alerting, secret rotation |

Never copy production secrets or truststores into development. Every environment needs its own client authentication, TLS hostname/CA, and resource/audience policy.

## 18. Servlet Blocking vs. WebFlux Reactive Are Different Models

On the **Servlet stack**, introspection is normally **blocking**: the request thread waits for the outbound HTTP response. If the AS slows down, many Servlet threads are occupied. Connection pools and timeouts are especially critical.

On the **WebFlux reactive stack**, Spring Security provides **`ReactiveOpaqueTokenIntrospector`** and implementations using an appropriate reactive HTTP client. Concurrency, connection pooling, timeout/cancellation, and backpressure models differ from Servlet/RestTemplate.

| Characteristic | Servlet Resource Server | Reactive Resource Server |
|---|---|---|
| Security HTTP chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Introspector contract | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Typical HTTP client | Blocking `RestOperations`/Apache classic | Nonblocking WebClient/reactive HTTP client |
| Main risk when AS is slow | Servlet thread starvation and pool queuing | Event-loop blockage if using blocking APIs, in-flight/backpressure issues |
| Timeout/cancellation | Blocking client, thread, and connection | Reactive operators/HTTP client and signal propagation |
| Authentication result | `Authentication` in Servlet context | `Authentication` in reactive security context |

**Never call blocking `RestTemplate` directly on the WebFlux event loop** and expect the system to remain nonblocking. If building a Reactive Resource Server, design HTTP transport and timeouts with the corresponding reactive APIs rather than copying Servlet code verbatim.

## 19. Testing Timeouts and Connection Management

A test using only MockMvc `opaqueToken()` usually **does not call the real introspection endpoint**, so it tests neither the HTTP client nor timeouts. Separate test layers are required.

### 19.1. Policy Tests

Use `opaqueToken()` or a mock principal to test:

- Scope mapping.
- Audience/resource policy when enforced at the appropriate layer.
- Tenant/ownership.
- Responses when authorities are missing.
- Never granting access when the principal is unauthenticated.

These test authorization, not HTTP transport.

### 19.2. Integration Tests with a Fake Introspection Server

Use a controlled HTTP test server to exercise scenarios:

| Scenario | Fake AS Behavior | Expected Outcome |
|---|---|---|
| Active token | Returns `200 {"active":true,...}` | Valid authentication; service continues checking permissions |
| Inactive token | Returns `200 {"active":false}` | Token rejected |
| Wrong client secret | Returns `401` | Fail closed; classify client authentication error |
| Read timeout | Connects, then delays body | HTTP client aborts per timeout |
| Connect timeout | Unreachable network path | Does not hang request indefinitely |
| Pool exhaustion | Concurrent requests fill pool | Lease timeout, no unbounded queue |
| AS rate limit | Returns `429` | No retry storm; fail closed |
| AS returns 503 | Dependency failure | Never accept token; clear health/metrics |
| Malformed JSON | Structurally invalid body | Never turns into a valid principal |
| HTTPS invalid certificate | TLS handshake fails | Never enable trust-all |
| Redirect to unknown host | `302 Location` to another host | Never leak tokens/secrets |
| Connection closed mid-response | Network error | Release resources, report error, obey retry policy |
| Secret rotation | Some pods still use old secret | Detect failure per instance, never let through |

To genuinely test the **pool**, drive concurrent requests through the integrated HTTP client rather than calling `introspector.introspect(...)` sequentially against an instant fake AS.

### 19.3. Resource-Limit Tests

A simple scenario:

```text
pool max per route = 2
request A: AS holds connection for 1 second
request B: AS holds connection for 1 second
request C: starts while A/B are still busy
connectionRequestTimeout = 100 ms
Expected: C hits pool wait timeout, does not hang forever
```

Test with the **exact HTTP client/pool implementation** used in code. `SimpleClientHttpRequestFactory` does not provide pool-lease semantics like Apache client.

When testing connect timeouts, be careful: an unroutable IP may cause the OS to fail immediately rather than waiting for timeout; use network fault injection or a controlled test environment to verify behavior. Do not rely on calling a "slow-looking" public host as a deterministic test.

### 19.4. Verifying Graceful Shutdown and Leaks

After a load test run:

- Leased pool connections return near 0 once requests finish.
- No unbounded growth in sockets/file descriptors.
- No leftover eviction threads from the old HTTP client after the application context closes.
- Connection/request timeouts are categorized accurately.
- No raw tokens/client secrets appear in logs or traces.
- During rolling restarts, old pods close pools and in-flight requests are handled within the grace period.

**These are resource and operational tests**, distinct from JWT/opaque token logic tests.

## 20. Common Anti-Patterns

### 20.1. Creating a New `RestTemplate`/`HttpClient` Per Request

Wrong:

```text
for each bearer token:
   new HTTP client
   new pool
   introspection
   abandon client/pool
```

Consequence: lost connection reuse, extra TLS handshakes, and hard-to-reclaim sockets/file descriptors and threads. Replace with a **Spring-lifecycle-managed client/pool** reused across requests.

### 20.2. Setting Huge Read Timeouts to Reduce Errors

If the AS is slow, raising the timeout from 1 second to 60 seconds holds request threads for far too long; both the pool and Tomcat can jam. Base limits on SLAs, metrics, and capacity—never use huge timeouts to hide incidents.

### 20.3. Configuring Only Connect Timeout

A fast connect does not mean a fast response. Bound **response/read timeouts and pool lease timeouts** when the transport pools connections. If you have a total latency target, enforce an end-to-end deadline.

### 20.4. Retrying Every Error

Retrying `active=false`, HTTP 401 wrong client secret, or invalid TLS certificates does not make a token valid; it only adds load. Classify errors and cap attempts.

### 20.5. Letting Requests Pass When the Circuit Breaker Is OPEN

This turns an AS outage into an authentication bypass. Without introspection evidence, **fail closed**; use caching only if designed/approved with explicit staleness bounds.

### 20.6. Printing Full Outbound Requests for Debugging

Bearer tokens and Basic secrets can end up in logs, APM, proxies, or traces. Log status/latency/error class, never sensitive credentials/response claims.

### 20.7. One Shared Pool for Every Outbound Service

If a shared `RestTemplate` has `BasicAuthenticationInterceptor`, introspection credentials could be sent to unrelated hosts. There is also the risk that a slow downstream service exhausts the pool and starves introspection. **Separate transports/credentials/limits by dependency.**

### 20.8. Pool Size Many Times Larger Than AS Capacity

Combined connections across all pods can overload the AS. Compute cluster-wide concurrency and coordinate quotas/rate limits with the AS team.

### 20.9. Letting the Caller Choose `introspection-uri`

This introduces **SSRF and token exfiltration** risks. The URI must come from trusted configuration, never from a client-supplied token/header.

### 20.10. Treating HTTP 200 Alone as Active Token

`200 {"active":false}` means the token is inactive. Never parse HTTP responses as "2xx means authenticated" while ignoring the `active` field.

## 21. A Reference Production Design

Suppose the Orders API runs 6 replicas, each receiving about 350 requests/s, with no introspection caching. Total traffic may be roughly:

```text
350 requests/s × 6 pods = 2,100 introspection calls/s
```

Align with the AS team:

- Can the AS handle 2,100 RPS of introspection at target latency?
- Is there a per-client-ID rate limit?
- Must capacity be shared with other Resource Servers?
- If AS p99 latency climbs, how much do in-flight requests and pool demand grow?
- What revocation delay is acceptable if caching is considered?
- Are multiple AS replicas/load balancers and a failover strategy needed?

On each pod:

```text
Ingress
  |
  v
BearerTokenAuthenticationFilter
  |
  v
OpaqueTokenAuthenticationProvider
  |
  v
OpaqueTokenIntrospector (singleton bean)
  |
  v
RestOperations / Apache HttpClient 5
  ├─ Basic client auth
  ├─ TLS validation
  ├─ Connection pool (bounded)
  ├─ Pool lease timeout
  ├─ Connect timeout
  ├─ Response/socket timeout
  ├─ Idle/expired connection eviction
  └─ Metrics, bounded retry, fail-closed handling
  |
  v
Authorization Server introspection endpoint
```

Operational principles:

1. **Bound** all queues/connections/concurrency.
2. **Isolate** introspection Basic credentials and pools from other HTTP clients.
3. **Measure** latency, pool saturation, and error categories.
4. **Protect** the entire token/secret path with TLS and allowlisted URIs.
5. **Close** clients via the Spring bean lifecycle.
6. **Never** skip authentication when the AS is unavailable.
7. **Enforce** scope/audience and object-level authorization after introspection.

### 21.1. Operational Team Responsibilities

| Team | Responsibilities |
|---|---|
| Authorization Server team | Endpoint capacity, client auth methods, quotas, metadata, secret rotation, token state |
| API/Resource Server team | Custom introspector, HTTP timeouts/pools, Bearer handling, claims/authorities, fail closed, service policy |
| Platform/Infrastructure | DNS, TLS certs/CAs, egress/firewalls, load balancing, autoscaling, node time sync |
| Observability/SRE | Safe tracing, dashboards, p95/p99, pool metrics, alerting, incident runbooks |
| Security team | Least privilege for introspection clients, secret handling, risk acceptance for caching/revocation |

Teams must agree on an **error budget and capacity contract**, not merely confirm "the introspection-uri is currently reachable."

## 22. Technical Handoff Checklist

| Item | Question to Answer |
|---|---|
| URI | Is it the official introspection endpoint for the right issuer/realm/environment? |
| Client authentication | Does it use Basic secret, mTLS, or `private_key_jwt` as registered? |
| Secrets | Are they injected securely, rotated, and never exposed in logs? |
| TLS | Are hostname, chain, CA/truststore, proxy, and SNI verified at runtime? |
| Connection reuse | Does the HTTP client/pool actually reuse connections? |
| Pool limits | Are `max-total`, `max-per-route`, and pool-lease timeout configured? |
| Timeouts | Are connect, read/response, and overall budgets properly understood? |
| Queue/concurrency | Are thread/connection/in-flight limits and backpressure in place? |
| Retries | Are errors classified with bounded attempts, jitter, and deadlines? |
| Circuit breaker | When open, does it fail closed without granting access? |
| Cache | Are revocation delay, `exp`, and secret protection accounted for? |
| Redirects | Is sending credentials to other hosts prevented? |
| HTTP semantics | Is `200 inactive` distinguished from HTTP 401 client auth failure? |
| Authorization | Are scope, audience/resource, and tenant/owner business policies enforced? |
| Observability | Are p95/p99/pool-pending/error-type metrics and redacted logs in place? |
| Lifecycle | Are pools/clients/eviction threads closed on shutdown? |
| Tests | Are network faults, pool exhaustion, timeouts, secret rotation, and revoked tokens tested? |
| Multi-instance | Does total connections/RPS across all pods fit AS capacity? |

This is an **implementation checklist**, not certification that any system already meets these criteria. Results must be verified against the live environment and real measurements.

## 23. References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): requests, `active`, introspection endpoint authentication/authorization.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer tokens, `invalid_token`, and `insufficient_scope`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): publishing the introspection endpoint and supported client authentication methods.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector` and Servlet introspection configuration.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bearer token authentication and Resource Server policies.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestTemplate`, HTTP request factories, and REST client configuration.
- [Apache HttpClient 5 Documentation](https://hc.apache.org/httpcomponents-client-5.4.x/index.html): connection managers, request config, and HTTP client lifecycle.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): managing environment properties and configuration without hardcoding secrets.

**Conclusion:** Customizing the HTTP client for opaque token introspection is not just bumping timeouts to make requests "fail less." It is designing a **resource-bounded, fail-closed outbound authentication path**: controlled URIs/credentials, trusted TLS, pooled connection reuse, budgeted timeouts, bounded retries, risk-accepted caching, bean-lifecycle resource cleanup, and token-free observability. When these layers are built properly, the Resource Server preserves both **authentication security** and **operational resilience** under load or Authorization Server incidents.
