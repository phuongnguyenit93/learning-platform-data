# XForwardedRemoteAddr and proxy trust limits across supported versions

## 1. Problem to solve: which IP does the gateway see?

In **SPRING_CLOUD_GATEWAY**, route predicates can decide which microservice receives a request based on path, method, headers, or source address. This lesson in the **Route Predicates** chapter focuses on two easily confused questions when a gateway sits behind a load balancer, ingress, or web application firewall (WAF):

1. **Which address in the HTTP request does `XForwardedRemoteAddr` inspect?**
2. **When can `X-Forwarded-For` be trusted, and how must the number of trusted proxies be bounded?**

This is essential knowledge when building an API Gateway with route predicates and filter chains, transforming headers/paths, integrating service discovery, and adding authentication, rate limiting, circuit breakers, retries, TLS, and request observability. An incorrectly determined IP can route traffic to the wrong service, generate wrong rate-limiting keys, or let access policies be bypassed.

**Key principle:** `X-Forwarded-For` is an **HTTP header that can be crafted by the sender**. The fact that an address lies within an allowed CIDR range **does not prove that header was created by a trusted proxy**. Trust boundaries must be designed at both the network layer and the header-processing layer.

> **Version scope:** Primary examples use **Spring Cloud Gateway Server WebFlux**. Official documentation for **4.2, 4.3, and 5.x** describes both the `XForwardedRemoteAddr` and `RemoteAddr` route predicates. However, configuration namespaces and forwarded-header handling features differ across lines; check the documentation for the exact version you are running. Server MVC has its own APIs and namespaces.

## 2. Distinguishing connection IP and the X-Forwarded-For chain

Suppose a system has two trusted proxies in front of the gateway:

~~~mermaid
flowchart LR
    C["Client<br/>198.51.100.24"] --> W["WAF<br/>10.0.1.10"]
    W --> I["Ingress<br/>10.0.1.20"]
    I --> G["Spring Cloud Gateway"]
    G --> B["orders-service"]
~~~

If the WAF **strips any `X-Forwarded-For` value sent by the client** and creates a fresh header, and the ingress then appends the peer address it observes, the gateway can receive:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Forwarded-For: 198.51.100.24, 10.0.1.10
~~~

At the gateway, the direct connecting peer is typically the ingress `10.0.1.20`, while `X-Forwarded-For` describes earlier hops:

| Position | Illustrative IP | Role |
| --- | --- | --- |
| First element of `X-Forwarded-For` | `198.51.100.24` | Real client **only if** the WAF sanitized the incoming header |
| Next element | `10.0.1.10` | WAF in front of ingress |
| Connecting peer to gateway | `10.0.1.20` | Ingress directly connected to gateway |

The ranges `198.51.100.0/24`, `192.0.2.0/24`, and `203.0.113.0/24` are illustrative blocks reserved for documentation. In real deployments, replace them with verified real IP ranges; never copy example values into a production allowlist.

**Subtlety:** `ServerHttpRequest.getRemoteAddress()` represents the request's remote address in WebFlux context. By default, this is typically the connecting peer to the gateway, though early forwarded-header processors in WebFlux (if enabled) can alter how the request represents its remote address. Therefore, do not equate every `getRemoteAddress()` value with the "raw socket IP" without verifying runtime configuration.

### How is X-Forwarded-For appended?

In a typical proxy chain, the XFF list runs from **the client on the left** to proxies in front of the gateway on the right:

~~~text
X-Forwarded-For: client, proxy-1, proxy-2
                 leftmost          rightmost
~~~

This is a common convention, not proof of trust. A malicious client can send on its own:

~~~http
X-Forwarded-For: 203.0.113.9
~~~

If the edge proxy **merely appends** the real client address `198.51.100.24` without removing the initial forged value, the gateway may see:

~~~http
X-Forwarded-For: 203.0.113.9, 198.51.100.24
~~~

Naively taking the leftmost element in "trust all" style mistakes `203.0.113.9` for the client address. This is an **IP spoofing via header** risk; TLS protects the transport connection but does not make client-supplied header contents trustworthy.

## 3. Three similarly named mechanisms with different meanings

| WebFlux Gateway mechanism | Reads from? | Configuration / usage point | Warning |
| --- | --- | --- | --- |
| **`RemoteAddr` predicate** | Request remote address, typically the direct peer or a value already processed by WebFlux | YAML `RemoteAddr=10.0.1.0/24` | Behind a proxy, this is usually the proxy's address, not the client's |
| **`XForwardedRemoteAddr` predicate** | `X-Forwarded-For` HTTP header | YAML `XForwardedRemoteAddr=198.51.100.0/24` | Matches purely on header data; the predicate itself does not verify header origin |
| **`XForwardedRemoteAddressResolver.maxTrustedIndex(n)`** | Address list in `X-Forwarded-For`, picking position counted right-to-left | Java DSL with `remoteAddr(resolver, CIDR...)` | Requires knowing exact trusted hop count, ingress restrictions, and proxy sanitization |

Spring's documentation describes `XForwardedRemoteAddr` as accepting **at least one CIDR** in the `sources` parameter, supporting IPv4/IPv6, and using `X-Forwarded-For` for matching. The documentation does not turn it into a proxy-chain verifier or a substitute for locking down trust boundaries.

### CIDR syntax

CIDR consists of a network address and a prefix length:

~~~text
198.51.100.0/24   → example IPv4 network with 256 addresses
10.0.0.0/8        → very wide private range; unsuitable as a
                    trusted client list without an explicit reason
2001:db8::/32     → illustrative IPv6 range for documentation
~~~

CIDR is **not a regular expression**. This matters because the `trusted-proxies` property covered later takes a **Java regular expression**, not CIDR notation.

## 4. Example XForwardedRemoteAddr configuration

Suppose the edge proxy is tightly managed, always sanitizes the XFF header, and you want to route requests whose proxy-confirmed address falls in `198.51.100.0/24` to a dedicated backend.

Example using the **Spring Cloud Gateway Server WebFlux 5.x** namespace:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: gateway-routing-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: trusted-source-demo
              order: -10
              uri: http://localhost:9001
              predicates:
                - Path=/demo/**
                - Method=GET
                - XForwardedRemoteAddr=198.51.100.0/24
              filters:
                - AddResponseHeader=X-Lab-Route, trusted-source-demo
~~~

The route is selected when `Path`, `Method`, and `XForwardedRemoteAddr` **all** match simultaneously. `AddResponseHeader` only marks the selected route in this lab; it performs no proxy validation or authentication.

Official documentation examples also use concise syntax like:

~~~yaml
predicates:
  - XForwardedRemoteAddr=192.168.1.1/24
~~~

The address `192.168.1.10` lies inside the range permitted by this example. Multiple CIDRs can be configured per the version's `sources` parameter syntax, though you must define the exact trusted address set and verify behavior when the header has **multiple hops** before relying on it to protect resources.

### If your project uses Spring Cloud Gateway 4.3.x or earlier

Per WebFlux docs for **4.3.x, 4.2.x, and older compatible lines**, move the entire route list block to:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: trusted-source-demo
          order: -10
          uri: http://localhost:9001
          predicates:
            - Path=/demo/**
            - Method=GET
            - XForwardedRemoteAddr=198.51.100.0/24
          filters:
            - AddResponseHeader=X-Lab-Route, trusted-source-demo
~~~

**Never define duplicate route IDs under both `spring.cloud.gateway.routes` and `spring.cloud.gateway.server.webflux.routes`.** When seeing `404` for every URL even though YAML looks valid, first verify that the gateway version loaded routes from the right namespace.

### Predicate mismatch does not mean 403 on non-match

If a request fails `XForwardedRemoteAddr`, the route above **is not selected**. Gateway keeps checking other routes; if no other handler exists, the outcome is normally **404**, not an automatic 403. Another broader route may still accept the same request, so **never use a single route predicate as an entire authorization mechanism**.

To return `403 Forbidden` or `401 Unauthorized` per security policy, configure Spring Security or an appropriate access-control layer independent of which route is chosen. The target service must still enforce business authorization for the resources it owns.

## 5. Bounding trust with XForwardedRemoteAddressResolver

When you genuinely need to pick **the client address across a known number of trusted proxies**, WebFlux Gateway documentation provides `XForwardedRemoteAddressResolver` with two factory methods:

- `trustAll()`: takes the first IP in `X-Forwarded-For`; **vulnerable to spoofing** whenever clients can send forged headers.
- `maxTrustedIndex(n)`: picks the IP according to the number of trusted hops in front of the gateway; `n` must be a positive integer determined from the **actual topology** and network access constraints.

Documentation example:

~~~http
X-Forwarded-For: 0.0.0.1, 0.0.0.2, 0.0.0.3
~~~

| `maxTrustedIndex(n)` | Selected address |
| ---: | --- |
| `1` | `0.0.0.3` (rightmost) |
| `2` | `0.0.0.2` |
| `3` | `0.0.0.1` (leftmost) |
| `4` or higher | `0.0.0.1` when the chain has only 3 addresses |
| `0` or negative | Invalid; throws an error when constructing the resolver |

With the topology in section 2, the header sanitized by the WAF is:

~~~http
X-Forwarded-For: 198.51.100.24, 10.0.1.10
~~~

`maxTrustedIndex(1)` yields `10.0.1.10`; `maxTrustedIndex(2)` yields `198.51.100.24`. The number `2` is valid **only when the gateway is always reached through exactly two controlled proxy hops, each hop appends headers as expected, and no bypass path exists**.

If in reality there is only one proxy while `maxTrustedIndex(2)` is configured, a forged entry on the left can end up selected. Conversely, setting `n` too low picks a proxy IP instead of the client, skewing IP-based metrics, rate limits, or routing.

### 5.1. Java DSL example with RemoteAddr and resolver

When you need to control XFF position by hop count rather than using the `XForwardedRemoteAddr` predicate directly in YAML, you can configure routes via Java DSL. The following example **assumes two trusted inbound proxies** and a backend listening at `localhost:9001`:

~~~java
package demo.gateway;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.cloud.gateway.support.ipresolver.RemoteAddressResolver;
import org.springframework.cloud.gateway.support.ipresolver.XForwardedRemoteAddressResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GatewayRoutes {

    @Bean
    RouteLocator trustedClientRoutes(RouteLocatorBuilder builder) {
        RemoteAddressResolver resolver =
                XForwardedRemoteAddressResolver.maxTrustedIndex(2);

        return builder.routes()
                .route("partner-api", r -> r
                        .path("/partner/**")
                        .and()
                        .remoteAddr(resolver, "198.51.100.0/24")
                        .uri("http://localhost:9001"))
                .build();
    }
}
~~~

Here `remoteAddr(resolver, ...)` resolves the address via **the supplied resolver** and then matches it against the CIDR. This is the `RemoteAddr` route predicate customized with a resolver; it is not a way to attach `maxTrustedIndex` to the `XForwardedRemoteAddr=...` shortcut. The Java configuration must be used in a matching Spring Cloud Gateway **Server WebFlux** project with compatible dependencies and Spring Cloud BOM.

> **Safety critical:** `maxTrustedIndex` only picks an **index** in the XFF list; it does not verify proxy certificates, block outsiders from connecting directly to the gateway, or validate each hop in the list. Restricting connection sources, sanitizing inbound headers, and enforcing network access controls remain mandatory.

### 5.2. Do not try to "count hops" from arbitrary header chains

The count of trusted proxies must come from the deployment design (load balancer, CDN, WAF, ingress) and how they actually write XFF. Conditions that invalidate the assumption include:

- Clients can call the gateway directly, bypassing the ingress.
- Some requests pass through one WAF, while others pass through two WAFs or a CDN.
- The first proxy appends to the header without stripping Internet-supplied entries.
- A reverse proxy layer changes how headers are set or merges multiple XFF fields.
- WebFlux `ForwardedHeaderTransformer` or upstream infrastructure already normalized forwarded headers before route predicates run.

If the topology is not fixed, normalize the client address at a trusted boundary proxy and pass verified metadata explicitly, rather than hardcoding an index and treating the result as a trusted identity.

## 6. `trusted-proxies` configuration changes across versions

Spring Cloud Gateway has a **`trusted-proxies`** concept tied to **`HttpHeadersFilters`** that process `Forwarded` and `X-Forwarded-*` headers before sending requests downstream. It is often confused with `XForwardedRemoteAddr` or `maxTrustedIndex`, yet their roles **differ**.

| WebFlux Gateway line (per Spring docs) | Common route declaration namespace | Trusted-proxies property for forwarded header filters |
| --- | --- | --- |
| **4.2.x** | `spring.cloud.gateway.routes` | `spring.cloud.gateway.trusted-proxies` |
| **4.3.x** | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.trusted-proxies` |
| **5.0.x / 5.1.x** | `spring.cloud.gateway.server.webflux.routes` | `spring.cloud.gateway.server.webflux.trusted-proxies` |

The value of `trusted-proxies` is a **Java regular expression** describing trusted proxies as they appear in `Forwarded`/`X-Forwarded-*` headers, **not a CIDR list**. Illustrative example for proxies at `10.0.1.10` or `10.0.1.20` in versions using the newer namespace:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '10\.0\.1\.(?:10|20)'
~~~

For the 4.2 line, the documented property path is:

~~~yaml
spring:
  cloud:
    gateway:
      trusted-proxies: '10\.0\.1\.(?:10|20)'
~~~

This regex is **illustrative**; test actual matching and verify real proxy IPs before deploying. Avoid using `.*` as a "trust all proxies" setting in public environments. At the network level, still lock down direct paths to the gateway and configure proxies to normalize headers.

### 6.1. Does this property automatically protect XForwardedRemoteAddr?

**Do not assume so.** Spring's documentation covers `trusted-proxies` under **HttpHeadersFilters**, while `XForwardedRemoteAddr` resides under **Route Predicate Factories**. Enabling `trusted-proxies` for forwarded header filters does not replace:

1. Verifying connections to the gateway originate from permitted proxies.
2. Sanitizing client-supplied `X-Forwarded-For` at the edge.
3. Selecting the right address in the chain via a supported mechanism.
4. Testing behavior on the **exact version** of gateway, WebFlux, and reverse proxy you run.

You must also distinguish the gateway's `XForwarded Headers Filter`, which builds/updates headers forwarded **down to the backend**, from validating the trusted origin of headers **entering** the gateway. The two flows relate but are not identical.

### 6.2. Other X-Forwarded parameters

Recent WebFlux versions provide properties such as `spring.cloud.gateway.server.webflux.x-forwarded.for-enabled` and `...for-append` to control generating/appending XFF on **forwarded requests**. They help design trace/proxy chains, yet **do not make inbound XFF values trustworthy**.

When accurate forwarded headers are needed so the backend knows the HTTPS scheme, original host, or original path, inspect TLS termination and ingress forwarding configuration separately. Never accept a client-sent `X-Forwarded-Proto: https` as proof that the request arrived over HTTPS.

## 7. Practical protection model based on trust boundaries

A solid design requires defense in depth, especially if IP contributes to privileged routes, partner allowlists, rate limiting, or geolocation.

~~~mermaid
flowchart TD
    C["Client from Internet"] --> E["Edge WAF / ingress<br/>strips client-supplied XFF"]
    E --> A["Set / append XFF<br/>from observed peer IP"]
    A --> N{"Connection to gateway<br/>allowed by network policy?"}
    N -->|"No"| D["Block at network layer"]
    N -->|"Yes"| G["Gateway evaluates routes<br/>and resolver per topology"]
    G --> S["Spring Security / policy<br/>and backend authorization"]
    S --> B["Microservice"]
~~~

Controls to apply:

1. **Lock down gateway ingress:** security groups, firewalls, `NetworkPolicy`, or private listeners allow only managed load balancers/ingresses to connect. In development, `localhost` is a simplified model and says nothing about production policy.
2. **Sanitize at the first trusted proxy:** strip Internet-sent `X-Forwarded-For`/`Forwarded` headers and rebuild from the observed peer IP; subsequent internal proxies append using consistent rules. Some infrastructures use PROXY protocol or dedicated client-IP forwarding modes—verify their semantics.
3. **Fix or explicitly document topology:** know how many hops precede the gateway; use `maxTrustedIndex(n)` only when the chain truly matches, and audit unintended entry paths.
4. **Independent authentication/authorization:** IP-based route predicates are merely routing conditions. Sensitive APIs still require token/API key authentication and authorization at gateway/backend according to responsibilities.
5. **Observe without leaking data:** you may log route ID, verified peer address, derived client IP, hop count, routing decision, and trace ID; avoid logging full client forwarded headers or personal data. Follow log retention policies.

## 8. Hands-on testing and verifying spoofing risks

Testing should only be run in a **local/lab environment**. Use the gateway app configured with `trusted-source-demo` from section 4 (port `8080`) and any HTTP backend at `localhost:9001` handling `GET /demo/check`. If the backend returns 200, responses through the matching route include `X-Lab-Route: trusted-source-demo`.

### 8.1. Sending a single XFF value

~~~bash
# Illustrative address inside 198.51.100.0/24:
curl -i "http://localhost:8080/demo/check" \
  -H "X-Forwarded-For: 198.51.100.24"

# Address outside the allowed range:
curl -i "http://localhost:8080/demo/check" \
  -H "X-Forwarded-For: 203.0.113.77"

# Without X-Forwarded-For:
curl -i "http://localhost:8080/demo/check"
~~~

In an example with only one route and no other handlers, the first request **can match the route** and forward to the backend, while the next two typically fail to match and return `404`. Treat this as expected only when your gateway version and proxy configuration process headers as in this lab.

**If you send an arbitrary `X-Forwarded-For` directly to the gateway and still control which route wins, that proves why you cannot rely on this header for security without a trusted ingress.** Test success does not prove the client is authenticated.

### 8.2. Creating a two-hop scenario

Use a real reverse proxy or integration test environment to verify:

~~~http
X-Forwarded-For: 198.51.100.24, 10.0.1.10
~~~

With the Java DSL `maxTrustedIndex(2)` in section 5, the value matched against `198.51.100.0/24` must be `198.51.100.24`, **provided** the chain was controlled by the edge proxy as assumed. Also test these cases:

| Scenario | Behavior to verify |
| --- | --- |
| Valid two-proxy chain | Resolver picks the right client IP for `n=2` |
| Client sends forged XFF before edge | Edge strips spoofed prefix; gateway never trusts forged value |
| One proxy is bypassed | Network gates block direct shortcut requests to gateway |
| Missing or malformed XFF | Route is not improperly accepted; observe error behavior per version |
| Hop count changes | Re-verify `maxTrustedIndex` assumption; do not leave stale config hardcoded |
| Mixed IPv4/IPv6 | Verify proxy formatting and Gateway parsing on your deployed version |

### 8.3. Distinguishing 404, 403, and backend errors

- **404 from route mismatch:** request failed the XFF predicate and no other route/handler matched. The backend never sees the request.
- **403 from access policy:** Security/filter explicitly denied access; not a default predicate behavior.
- **404/5xx from backend:** the route may have matched and gateway forwarded the request, but the backend returned an error; check logs/traces on both sides.
- **503 when discovery finds no instances:** if a route uses `lb://service-id` and no instances exist, Gateway WebFlux LoadBalancer typically returns 503 by default. This differs from a predicate mismatch.

When debugging, follow the sequence: **connection into gateway → header contents after trusted proxies → route predicate → URL/instance selection → filter chain → backend → response**.

## 9. Frequently asked questions

### Should XForwardedRemoteAddr be used to protect internal APIs?

It can serve as **a supplementary routing condition** when the entire header path is controlled. Never use it alone in place of firewalls/`NetworkPolicy`, authentication, or authorization. If a fallback `Path=/**` route could send the same API path to another backend, check route order and security to prevent unintended bypasses.

### Should XForwardedRemoteAddr's CIDR contain client IPs or proxy IPs?

It depends on policy intent and which header value the gateway evaluates. The predicate's CIDR applies to **the address selected from XFF**, whereas direct peer IPs belong to network connection controls and `RemoteAddr`. Never add a WAF's IP range to a client allowlist simply because the WAF sits in front of the gateway, nor treat user-supplied XFF addresses as "trusted client IPs".

### Is maxTrustedIndex a YAML property inside XForwardedRemoteAddr?

No. `maxTrustedIndex(n)` is a factory method creating an **`XForwardedRemoteAddressResolver`**, used via APIs accepting `RemoteAddressResolver` (such as Java DSL `remoteAddr(resolver, ...)`). Do not add `maxTrustedIndex` into `XForwardedRemoteAddr=...` syntax assuming the framework will parse it.

### Should trustAll be enabled to read the leftmost IP?

Avoid using `trustAll()` as an input for access control or IP-based rate limiting in environments that can receive headers from the Internet. That method intentionally trusts the first XFF element and is explicitly warned against for spoofing in Spring's docs.

### Does trusted-proxies apply identically to WebFlux and Server MVC?

No. Newer versions have distinct properties such as `spring.cloud.gateway.server.webflux.trusted-proxies` and `spring.cloud.gateway.server.webmvc.trusted-proxies`; underlying frameworks and filter implementations differ. This lesson covers **WebFlux** examples only. When using MVC, read the corresponding docs rather than copying WebFlux Java DSL/namespaces verbatim.

## 10. Checklist before using IP to make decisions

- [ ] Identified exact Spring Cloud Gateway, Spring Boot, and WebFlux/MVC mode; using matching config namespaces.
- [ ] Diagrammed topology client → CDN/WAF → ingress → gateway; know where TLS terminates and where forwarded headers are processed.
- [ ] Verified gateway exposes no bypass port for external clients to connect directly.
- [ ] First trusted proxy strips or normalizes forwarded headers from untrusted sources.
- [ ] Clear on whether the policy uses `RemoteAddr`, `XForwardedRemoteAddr`, or `RemoteAddr` with `maxTrustedIndex`; no confusion.
- [ ] When using `maxTrustedIndex`, hop count and append direction are verified in a real runtime environment.
- [ ] `trusted-proxies` uses a **regex** in the right namespace/version and is tested; not treated as complete input authentication.
- [ ] Tested header spoofing, proxy bypass, missing/malformed headers, fallback routes, and status codes.
- [ ] Authorization at gateway/backend remains enforced; IP rate limiting uses verified trusted addresses.
- [ ] Logs/traces capture route ID, address source, and outcomes without exposing tokens or sensitive data.

## References and version comparison

The links below point to **official Spring documentation**; select the matching version branch when upgrading:

1. [Route Predicate Factories — Spring Cloud Gateway Server WebFlux 5.1](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/request-predicates-factories.html): `RemoteAddr`, `XForwardedRemoteAddressResolver`, and `XForwardedRemoteAddr` sections.
2. [Route Predicate Factories — Spring Cloud Gateway 4.2](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): `spring.cloud.gateway.routes` namespace examples.
3. [HttpHeadersFilters — Spring Cloud Gateway 4.2](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/httpheadersfilters.html): `spring.cloud.gateway.trusted-proxies`.
4. [HttpHeadersFilters — Spring Cloud Gateway 4.3](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html): `spring.cloud.gateway.server.webflux.trusted-proxies`.
5. [HttpHeadersFilters — Spring Cloud Gateway 5.1](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html): forwarded headers and `x-forwarded.*` parameters.

**Key takeaway:** `XForwardedRemoteAddr` matches addresses from `X-Forwarded-For`; default `RemoteAddr` uses the request's remote address; `maxTrustedIndex(n)` selects an address position based on expected hops in the XFF chain. None of these mechanisms proves a proxy is trustworthy by itself. Lock down gateway ingress, normalize headers at the edge, apply the right properties for your version, and keep authentication/authorization independent of routing decisions.
