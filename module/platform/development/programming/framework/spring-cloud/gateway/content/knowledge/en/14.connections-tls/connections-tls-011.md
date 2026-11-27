# Configuring an outbound proxy when required by the deployment environment

## 1. Context: the Gateway is not always permitted to call the Internet directly

In a microservices system, **Spring Cloud Gateway** receives HTTP requests from clients, matches route predicates, executes filter chains, and calls backend APIs. Normally, for a route like `https://partner-api.example.test`, the Gateway uses Reactor Netty `HttpClient` to connect directly to the target host.

However, many enterprise environments or production Kubernetes clusters enforce **egress** policies:

- Pods or machines running the Gateway **cannot connect directly** to the Internet.
- Every outbound HTTP(S) connection must pass through an organization-managed **forward proxy** to enforce allowlists, auditing, and network controls.
- Internal APIs (e.g., `orders.default.svc.cluster.local`) should go **directly over the internal network** without detouring through an Internet proxy.
- The proxy may require a username/password, restrict `CONNECT` ports, or permit access only to certain hostnames.

A Gateway might work cleanly on a developer laptop yet repeatedly fail upon deployment because the laptop reaches the Internet directly while the cluster mandates an **outbound proxy**.

The goal of this lesson in the **Connections and TLS** chapter of **SPRING_CLOUD_GATEWAY** is to configure the **proxy the Gateway uses to reach upstreams**, understand HTTP `CONNECT` behavior, avoid sending internal traffic through the proxy, manage credentials safely, test HTTP/HTTPS, and diagnose network/TLS failures.

> **Scope:** Focuses on **Spring Cloud Gateway Server WebFlux** using Reactor Netty `HttpClient` for HTTP(S) routing. Properties in Gateway 5.x releases typically carry the `spring.cloud.gateway.server.webflux` prefix; WebFlux 4.x projects may use `spring.cloud.gateway`. Choose the right starter, release train, and namespace for your project; never copy **Gateway Server MVC** configuration into WebFlux.

## 2. Distinguishing three concepts all called "proxy"

The word "proxy" appears in multiple places in a system, so distinguish them clearly:

| Type | Location | Responsibility | Example |
| --- | --- | --- | --- |
| **Reverse proxy / API Gateway** | Sits in front of microservices, receives client requests | Selects routes, runs filters, routes to backends | Spring Cloud Gateway |
| **Inbound ingress / load balancer** | Sits in front of Gateway | Terminates TLS, load-balances Gateway, enforces access control | Ingress Controller, cloud LB |
| **Outbound forward proxy (egress proxy)** | Sits along the path from Gateway to upstream | Controls, forwards, or tunnels to target networks | Corporate HTTP proxy |
| **Service mesh egress gateway** | May be a hop managed by sidecars/mesh | Applies mesh-level egress policies | Platform-operated egress gateway |

This lesson addresses the **third row**: configuring the Gateway to connect **through a forward proxy when acting as an HTTP client**. That feature is completely distinct from `X-Forwarded-For`, `Forwarded`, `PreserveHostHeader`, `SetRequestHeader`, or `forward:` routes.

Traffic path diagram when an outbound proxy is enabled:

```mermaid
flowchart LR
    C["Client"] -->|"Public HTTPS"| G["Spring Cloud Gateway\nServer WebFlux"]
    G --> P{"Is target host bypassed?"}
    P -->|"No"| E["Forward proxy\nproxy.corp.internal:3128"]
    E -->|"CONNECT / tunnel"| O["Partner API\npartner-api.example.test:443"]
    P -->|"Yes"| I["Internal service\norders.default.svc.cluster.local:8081"]
    O --> G
    I --> G
    G --> C
```

The outbound proxy sits only on the **Gateway → upstream hop**. Clients connecting to the Gateway over HTTPS does not configure an outbound proxy; likewise, using an egress proxy does not configure HTTPS from clients to the Gateway.

## 3. Which HTTP client does the Gateway use for routing?

In **Gateway Server WebFlux**, once a route URI resolves to `http://...` or `https://...`, **Netty Routing Filter** uses Reactor Netty `HttpClient` to send the request to the backend. If a route starts with `lb://SERVICE-ID`, LoadBalancer selects a `ServiceInstance` and resolves the logical URL into an HTTP(S) URL before the HTTP client sends it.

High-level flow:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Spring Cloud Gateway
    participant L as Route / LoadBalancer
    participant P as Forward proxy
    participant U as Upstream
    C->>G: GET /partners/orders/42
    G->>L: Match route and resolve target URI
    L-->>G: https://partner-api.example.test/orders/42
    G->>P: Connect to proxy + HTTP CONNECT
    P->>U: Establish path to target host
    G->>U: TLS + HTTP request inside tunnel
    U-->>G: HTTP response via tunnel
    G-->>C: Status, headers, body
```

For routes bypassing the proxy, the Gateway connects directly to upstream without passing through `P`. This diagram represents logical flow; it does not imply the proxy can inspect HTTPS payloads protected inside the tunnel.

**Scope of effect:** `httpclient.proxy.*` properties apply to the Reactor Netty HTTP client **configured by the Gateway for Netty routing**. Never assume every outbound call in the application goes through it:

- A developer-created `WebClient` may use a separate `HttpClient`.
- Eureka/Consul clients, OAuth2 token clients, object-storage SDKs, or database drivers may use their own clients.
- `forward:///local-handler` routes dispatch to an in-process handler without necessarily making an outbound HTTP call.
- `RedirectTo` returns HTTP 3xx for the **client** to follow the new URL; it does not use the Gateway's egress proxy to follow redirects.
- WebSocket routing, TCP, or custom plugins may behave differently; check your exact version.

If an organization requires **all egress** to traverse a single checkpoint, combine per-HTTP-client settings with network policies/service mesh/firewalls rather than relying solely on one Spring Cloud Gateway property group.

## 4. Essential proxy properties

The properties below belong to `httpclient.proxy` in **Gateway Server WebFlux**. The full prefix depends on your version's namespace:

| Relative key | Meaning | Example |
| --- | --- | --- |
| `host` | Hostname/IP of the outbound proxy | `proxy.corp.internal` |
| `port` | Port the Gateway uses to connect to the proxy | `3128` |
| `type` | Proxy type supported by Reactor Netty | `http`, `socks4`, `socks5` |
| `username` | Proxy account username when authentication is required | Supplied from secret/deployment |
| `password` | Corresponding proxy password | Supplied from secret/deployment |
| `non-proxy-hosts-pattern` | **Java regex** matching hostnames to access directly | `localhost\|.*\\.internal\\.example` |

`host`, `port`, `username`, and `password` are **proxy credentials**, not microservice login credentials. `Authorization: Bearer ...` authenticating to a target API is distinct from **`Proxy-Authorization`** used to establish a tunnel with the proxy.

In primary examples we use proxy type `http`, common in enterprise networks. If your environment actually provides SOCKS4/SOCKS5, pick the appropriate `type` and verify DNS/auth support in your infrastructure. Never assume complex proxy authentication schemes work via username/password alone.

### 4.1. Do not pass a full URI as proxy.host

**Incorrect** example:

```yaml
proxy:
  host: http://proxy.corp.internal:3128
  port: 3128
```

`host` should contain only the **hostname or IP address**, while `port` is a separate number and `type` specifies the proxy kind:

```yaml
proxy:
  type: http
  host: proxy.corp.internal
  port: 3128
```

Never embed username/password inside `host` or a proxy URL like `http://user:password@...`; such strings risk leaking into logs, breaking parsing, and misusing the `host` field.

## 5. Configuring Gateway WebFlux 5.x: HTTP proxy for external upstreams

Suppose two routes exist:

- `GET /partners/**` to partner API `https://partner-api.example.test`, **which must traverse the egress proxy**.
- `GET /internal/orders/**` to `http://orders.default.svc.cluster.local:8081`, **going directly inside Kubernetes**.

Example in `application.yml` with the newer prefix:

```yaml
spring:
  application:
    name: api-gateway
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            proxy:
              type: http
              host: ${EGRESS_PROXY_HOST}
              port: ${EGRESS_PROXY_PORT:3128}
              non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
            connect-timeout: 3000
            response-timeout: 10s
          routes:
            - id: partner-api
              uri: https://partner-api.example.test
              predicates:
                - Path=/partners/**
              filters:
                - StripPrefix=1

            - id: orders-internal
              uri: http://orders.default.svc.cluster.local:8081
              predicates:
                - Path=/internal/orders/**
              filters:
                - StripPrefix=1
```

**Section-by-section explanation:**

1. `httpclient.proxy` configures the **Reactor Netty HttpClient** serving HTTP(S) routes, not just a single route. Bypass rules branch traffic based on the **actual target host**.
2. `${EGRESS_PROXY_HOST}` has **no fallback**: deployments requiring a proxy without providing the variable must not silently fall back to localhost or a fake proxy.
3. `${EGRESS_PROXY_PORT:3128}` uses an illustrative port fallback; supply the exact port provided by your network team.
4. `non-proxy-hosts-pattern` is a **Java regular expression**, not shell-style `NO_PROXY`. The sample expression covers `localhost`, `127.0.0.1`, and hosts ending in `.svc.cluster.local` or `.internal.example`.
5. The regex sits inside **YAML single quotes** to preserve backslashes; dots in regex must be escaped to match literal domain dots.
6. `connect-timeout` and `response-timeout` are additional HTTP client settings; they **do not create** retries, circuit breakers, or TLS certificates.
7. `StripPrefix=1` turns `/partners/orders/42` into `/orders/42`; the internal route turns `/internal/orders/42` into `/orders/42`. Predicates select routes **before** filters rewrite paths.

Addresses `proxy.corp.internal`, `partner-api.example.test`, and `orders.default.svc.cluster.local` are **illustrative**. In real environments, use addresses provided by network administrators and confirm the Gateway has DNS/network routing to the proxy, internal services, and permitted targets.

### 5.1. Why not use localhost as the proxy host inside containers?

Inside a Gateway container, `localhost` refers only to **that container itself** (except under special network modes). If the proxy runs as another service in Docker Compose or Kubernetes, use its deployment network service DNS/hostname rather than `localhost:3128` just because the proxy listened there on a developer machine.

## 6. Corresponding configuration in Gateway Server WebFlux 4.x

If your project uses the common WebFlux 4.x namespace, properties sit directly under `spring.cloud.gateway.httpclient`:

```yaml
spring:
  cloud:
    gateway:
      httpclient:
        proxy:
          type: http
          host: ${EGRESS_PROXY_HOST}
          port: ${EGRESS_PROXY_PORT:3128}
          non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
        connect-timeout: 3000
        response-timeout: 10s
      routes:
        - id: partner-api
          uri: https://partner-api.example.test
          predicates:
            - Path=/partners/**
          filters:
            - StripPrefix=1
```

The examples in sections 5 and 6 are **version-specific alternatives**, not two blocks to copy into the same project simultaneously. If property names differ yet the app still boots, failing to apply the proxy often manifests as timeouts/connection errors rather than a clear startup error.

**Verify effective configuration for your exact version** before deploying; do not infer namespaces from Java code in outdated guides. Spring Cloud Gateway's configuration properties reference is the authoritative check for `proxy.host`, `proxy.port`, `proxy.type`, `non-proxy-hosts-pattern`, `username`, and `password`.

## 7. Proxy authentication: supplying credentials safely

If the proxy requires authentication, add **two properties** inside the `proxy` block under the matching namespace:

```yaml
proxy:
  type: http
  host: ${EGRESS_PROXY_HOST}
  port: ${EGRESS_PROXY_PORT:3128}
  username: ${EGRESS_PROXY_USERNAME}
  password: ${EGRESS_PROXY_PASSWORD}
  non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
```

This is a **fragment** nested under `httpclient.proxy`, not a standalone `application.yml`. Add `username/password` only when the proxy actually requires authentication and your client version supports that auth mechanism.

### 7.1. Passing values from deployment

Linux/macOS example:

```bash
export SPRING_PROFILES_ACTIVE=egress
export EGRESS_PROXY_HOST=proxy.corp.internal
export EGRESS_PROXY_PORT=3128
# EGRESS_PROXY_USERNAME and EGRESS_PROXY_PASSWORD
# must be supplied via secure secret/deployment injection; never type real secrets into scripts.
java -jar target/api-gateway.jar
```

If config references `${EGRESS_PROXY_USERNAME}` and `${EGRESS_PROXY_PASSWORD}` without the deployment supplying values, configuration resolution can fail. For unauthenticated proxies, omit those properties completely rather than setting dummy passwords.

In Kubernetes, reference a Secret:

```yaml
# containers snippet of a Deployment, not a full Deployment YAML:
containers:
  - name: gateway
    image: example/api-gateway:1.0.0
    env:
      - name: EGRESS_PROXY_HOST
        value: proxy.corp.internal
      - name: EGRESS_PROXY_PORT
        value: "3128"
      - name: EGRESS_PROXY_USERNAME
        valueFrom:
          secretKeyRef:
            name: gateway-egress-proxy
            key: username
      - name: EGRESS_PROXY_PASSWORD
        valueFrom:
          secretKeyRef:
            name: gateway-egress-proxy
            key: password
```

Kubernetes Secrets **do not solve every security concern by themselves**. Apply RBAC/least privilege, encryption at rest per policy, avoid dumping environment variables into logs, and maintain a rotation process. Updating environment variables on running Pods typically requires a rollout/restart for processes to pick up new values.

### 7.2. Distinguishing 401 from 407

- **`401 Unauthorized`** typically comes from the upstream/API requiring user or token authentication.
- **`407 Proxy Authentication Required`** comes from the proxy demanding credentials to allow the connection.

If you get 407 while opening a tunnel, never blindly edit JWT route predicates or upstream tokens. Inspect proxy credentials, the auth scheme demanded by the proxy, and proxy logs. Some enterprise proxies require schemes beyond basic username/password; coordinate with the network team to verify supported options.

Never log `Proxy-Authorization`, Basic credentials, access tokens, or HTTP bodies containing sensitive data in logs or wiretap.

## 8. HTTP CONNECT: a subtle difference that easily causes errors

Reactor Netty supports proxies via Netty's `ProxyProvider`. **For HTTP proxies, Reactor Netty docs state the client uses `CONNECT` to tunnel both HTTP and HTTPS targets**. This differs from some traditional HTTP clients that send `GET http://host/path` directly to a forward proxy.

Example when the Gateway calls `https://partner-api.example.test:443`:

```text
Gateway -> Proxy TCP:  proxy.corp.internal:3128

Gateway -> Proxy HTTP: CONNECT partner-api.example.test:443 HTTP/1.1
Proxy -> Gateway HTTP: 200 Connection Established
Gateway <-> Upstream:   TLS handshake inside tunnel
Gateway -> Upstream:    GET /orders/42 (encrypted over TLS)
```

From the outside, callers still hit the Gateway URL. `CONNECT` is an internal exchange between the Gateway's HTTP client and the forward proxy to open a path to the upstream host/port.

### 8.1. Not every proxy permits CONNECT to port 80

Some enterprises allow `CONNECT` only to port 443; some enforce authentication or hostname allowlists. When the Gateway calls an `http://...:80` target through Reactor Netty's proxy mechanism, the proxy may reject `CONNECT host:80` even if plain `curl -x proxy http://host` works.

Confirm with your network team that the proxy **permits HTTP CONNECT to all required target ports**, including HTTP targets if applicable. If policy allows `CONNECT` only on port 443, the proper fix is typically using HTTPS upstreams or an approved infrastructure design — never bypassing the proxy.

### 8.2. A CONNECT tunnel does not mean every hop is encrypted

| Scenario | What is protected |
| --- | --- |
| Gateway → HTTP proxy, CONNECT → **HTTPS** upstream | Application HTTP traffic inside the tunnel is TLS-protected between the Gateway and the upstream's TLS endpoint, absent TLS interception |
| Gateway → HTTP proxy, CONNECT → **HTTP** upstream | The tunnel can carry **plaintext** HTTP; it does not add TLS automatically |
| Corporate proxy with TLS inspection | Proxy may terminate and re-establish TLS per policy; requires CA, permission, and audit management |
| Gateway calls HTTPS upstream directly via bypass | Bypasses proxy; TLS still requires certificate/hostname validation |

"HTTP proxy" describes the **proxy protocol type**, not that enabling `type: http` encrypts the Gateway-to-proxy hop with TLS. If proxy credentials or connection traffic require protection, understand your platform's exact topology, proxy type, and encryption layers.

## 9. Bypassing the proxy: non-proxy-hosts-pattern is a Java regex

A Gateway often calls both public APIs and internal services. Pushing all traffic through an Internet proxy can cause:

- The proxy failing to resolve Kubernetes `.svc.cluster.local` DNS.
- The proxy blocking internal IP ranges or non-public services.
- Internal traffic detouring, adding latency or violating network segmentation.
- `lb://` discovery returning instance IPs unreachable by the proxy.
- Proxy overload from east-west traffic that never needed egress.

`non-proxy-hosts-pattern` accepts a **Java regular expression for hostnames that should connect directly**. Example:

```yaml
non-proxy-hosts-pattern: '(localhost|127\.0\.0\.1|.*\.svc\.cluster\.local|.*\.internal\.example)'
```

Cases:

| Target URI host | Matches sample regex? | Expected path |
| --- | --- | --- |
| `localhost` | Yes | Direct |
| `127.0.0.1` | Yes | Direct |
| `orders.default.svc.cluster.local` | Yes | Direct |
| `auth.internal.example` | Yes | Direct |
| `partner-api.example.test` | No | Via proxy |
| `10.20.1.12` | **No** | May route via proxy unless a matching pattern is added |

**Especially with `lb://`:** logical routes hold only a service ID, yet after load balancing, the Gateway can receive an instance **IP address**. Bypassing only `.svc.cluster.local` may **not** match that internal IP. Observe the **actual host/port received by the HTTP client**, then refine the regex or routing design accordingly.

To bypass a specific IP range, use a bounded Java regex like `10\\.20\\.\\d+\\.\\d+` if infrastructure exclusively uses `10.20.x.x` for direct endpoints. Regex is **not a CIDR parser** and not a network firewall; when network-level enforcement is required, use real network policies, firewalls, or egress gateways.

### 9.1. Differences between regex and NO_PROXY

`NO_PROXY` is commonly interpreted by CLI/container tools as a comma-separated host/domain/IP list, with wildcard, leading-dot, and CIDR support **varying across tools**. In the Gateway, `non-proxy-hosts-pattern` is a Java regex.

Example **never to copy verbatim** into the regex property:

```text
NO_PROXY=localhost,.svc.cluster.local,10.0.0.0/8
```

This is not a valid regex for `non-proxy-hosts-pattern`. In Java regex, `.` matches any character, `*` is a quantifier, and `10.0.0.0/8` does not represent a CIDR block. Compile and test patterns thoroughly before deploying.

In many environments, it is cleaner to **run a dedicated Gateway for a distinct outbound group**, or rely on controlled network policies and DNS, rather than maintaining a long, hard-to-review regex.

### 9.2. Where is DNS resolved?

With an HTTP proxy configured and no custom resolver, Reactor Netty typically **delegates target hostname resolution to the proxy**, rather than performing DNS lookups on the Gateway for every remote host. When a host is bypassed, the Gateway connects directly and generally relies on the Gateway environment's DNS.

If a developer configures a custom DNS resolver on Reactor Netty, resolution behavior can change; the resolver must resolve hosts when needed even when proxying. Distinguish four distinct errors:

- Gateway cannot resolve the **proxy hostname**.
- Proxy cannot resolve the **upstream hostname**.
- Gateway cannot resolve a **bypassed hostname**.
- Actual host after `lb://` is an IP that misses hostname regexes.

These are four separate failures. Test DNS from whichever component actually opens the connection; never run `nslookup` against upstream from the Gateway and assume the proxy can resolve it too.

## 10. Profiles and environment variables: enable egress proxy only where needed

A sound operational practice is running the same artifact with **two distinct network profiles**:

- `local`: test APIs accessed directly, **omitting** the proxy section.
- `staging` or `prod`: environments requiring an egress proxy declare `httpclient.proxy` and inject credentials from secrets.

You can place proxy settings in `application-egress.yml` and activate the `egress` profile alongside the environment profile, for example:

```bash
export SPRING_PROFILES_ACTIVE=prod,egress
export EGRESS_PROXY_HOST=proxy.corp.internal
export EGRESS_PROXY_PORT=3128
java -jar target/api-gateway.jar
```

`application-egress.yml` should use the **exact namespace** for your version and require `${EGRESS_PROXY_HOST}`. Enabling the `egress` profile without host/port should fail early during deployment.

**Note on `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, and JVM flags:** tools like `curl` support those variables automatically, and legacy Java clients use `-Dhttp.proxyHost`/`-Dhttps.proxyHost`. However, **you must not assume Reactor Netty HttpClient created by Spring Cloud Gateway automatically reads/applies all those environment variables and system properties**.

For Gateway HTTP(S) routes, explicitly configure `spring.cloud.gateway...httpclient.proxy.*` or an HTTP client customizer **supported by your version**, then verify proxy logs. Never assume `export HTTPS_PROXY=...` alone routes Gateway traffic through the proxy.

### 10.1. Scope is the shared HTTP client, not arbitrary per-route overrides

`httpclient.proxy.*` configures the proxy on the Gateway's **shared HTTP client**. There is no built-in `proxy` field inside each route YAML to pick different proxies per route.

If requirements demand:

- API A through partner group A's proxy;
- API B through proxy B;
- internal APIs without any proxy;

then **one** `httpclient.proxy.host` plus `non-proxy-hosts-pattern` only expresses part of that. Consider splitting Gateways/egress components by policy, using a service mesh/egress gateway, or writing a cleanly tested, maintainable customization for your exact version. Never assume Spring supports independent per-`RouteDefinition` proxy properties out of the box.

## 11. TLS, HTTPS, and certificate verification on the upstream hop

Configuring an egress proxy **does not replace** client TLS configuration:

1. The Gateway resolves upstream URL `https://partner-api.example.test`.
2. The Gateway connects to the HTTP proxy and requests tunnel `CONNECT partner-api.example.test:443`.
3. Once the tunnel is allowed, Netty `HttpClient` runs the **TLS handshake with the TLS endpoint** inside the tunnel.
4. Certificates, hostname/SNI, CA/truststore, and mTLS requirements must still be valid.
5. The actual HTTP request is transmitted after the TLS handshake succeeds.

If a corporate proxy performs **TLS inspection**, the certificate seen by the Gateway may be signed by a corporate CA rather than the original public CA. That requires explicit security approval/policy and trusting the managed CA properly. Never add unverified CAs or disable hostname verification.

### 11.1. Do not use an insecure trust manager as a quick fix

Some versions provide `httpclient.ssl.use-insecure-trust-manager`. **Never set `true` in production** to bypass certificate errors; doing so eliminates upstream identity verification guarantees.

On `SSLHandshakeException`, inspect the certificate chain, SAN/hostname, SNI, TLS version/cipher policy, and possible proxy TLS interception. If an `HTTP CONNECT` error happens **before TLS starts**, tweaking truststores will not fix it because the tunnel was never established.

### 11.2. Inbound certificates differ from outbound certificates

A Gateway can have:

- **Inbound TLS:** client → ingress/Gateway, configuring server certificates.
- **Outbound TLS:** Gateway → target API inside tunnel, configuring HTTP client trust/mTLS.
- **Proxy authentication:** Gateway → forward proxy, configuring proxy credentials when needed.

These are **three distinct boundaries**. Inbound HTTPS does not ensure outbound HTTPS; proxy username/password does not satisfy JWT authentication to upstream.

## 12. Testing in local/staging before production

A proper test must **verify the connection path**, not just observe HTTP status 200.

### 12.1. Testing the proxy independently with curl

On a machine permitted to reach the proxy and test target:

```bash
# curl syntax only verifies network/proxy connectivity; it does not prove the Gateway uses the proxy.
curl -v --proxy http://proxy.corp.internal:3128 \
  https://partner-api.example.test/health
```

Use `-v` to inspect the `CONNECT` phase, HTTP status, and TLS details. Replace sample URLs with organization-managed test endpoints. **Never pass passwords directly in shared URLs/curl commands** where they can be saved in shell history and logs.

Note: `curl` has its own proxy/CONNECT behavior, **not 100% identical** to Reactor Netty. In particular, a proxy might accept traditional forward HTTP requests while rejecting `CONNECT` to HTTP ports; testing through Netty itself remains essential.

### 12.2. Calling the Gateway instead of calling upstream directly

With the Gateway running at `http://localhost:8080` in a test environment:

```bash
curl -i http://localhost:8080/partners/health
curl -i http://localhost:8080/internal/orders/42
```

Inspect both routes:

- `partner-api`: proxy logs/access policies record `CONNECT partner-api.example.test:443`; upstream receives `/health`.
- `orders-internal`: proxy logs show **no** connection to `orders.default.svc.cluster.local` (if bypass matched); the service receives `/orders/42` directly.
- Never rely solely on `200 OK`: responses can be cached or served by another upstream. Correlate route IDs, request IDs, proxy access logs, and upstream counters as needed.

To verify bypassing, test with a **logging mock/egress test proxy** and a mock upstream recording incoming requests. Never use personal or untrusted proxies for testing real data.

### 12.3. Recommended test matrix

| Case | Description | Signals to verify |
| --- | --- | --- |
| P1 | Gateway with proxy, calls external HTTPS | `CONNECT 443`, TLS handshake, and upstream response |
| P2 | Gateway with proxy, calls external HTTP | Does the proxy permit `CONNECT` to HTTP ports? |
| P3 | Calls host matching `non-proxy-hosts-pattern` | No `CONNECT`; direct connection |
| P4 | Calls `lb://internal-service` returning an IP | Does regex bypass the **post-selection IP**? |
| P5 | Proxy requires auth, no credentials supplied | `407` or matching tunnel setup error |
| P6 | Proxy blocks hostname/port | `403`/`407`/`5xx`/timeout per proxy; check proxy logs |
| P7 | HTTPS upstream uses untrusted CA | TLS handshake failure during/after tunneling |
| P8 | Proxy is down | Connection timeout/refused; upstream never called |
| P9 | `egress` profile not enabled | Gateway tries direct access; likely fails due to network policy |
| P10 | Wrong `httpclient.proxy.*` namespace | Property ignored; zero traffic through proxy |
| P11 | Internal service under `.svc.cluster.local` called by IP | Suffix bypass insufficient; check actual resolved host |

**Status codes in this table are not Gateway guarantees:** proxies, infrastructure, and error handlers may translate connection errors into different 5xx codes. What matters is identifying **which layer generated the error**.

### 12.4. Checking `lb://` routes and discovery

If the Gateway uses `lb://ORDER-SERVICE`:

1. `ReactiveLoadBalancerClientFilter` selects a `ServiceInstance`.
2. The concrete URL carries host/port and `isSecure` indicating HTTP vs. HTTPS.
3. The HTTP client decides whether to proxy or bypass based on the **resolved connection address** and configuration.
4. If the instance advertises `isSecure=false` while route/infra expects HTTPS, the proxy will not automatically fix that mismatch.

Do not treat `isSecure` as a toggle for "use egress proxy or not." It governs only instance transport security; **proxy selection** is a separate policy.

## 13. Troubleshooting across connection layers

| Symptom | Likely cause | How to diagnose |
| --- | --- | --- |
| Gateway works locally, times out in Kubernetes | Direct egress blocked, proxy not enabled, or wrong proxy DNS | Check profile, proxy host/port, and network policy |
| `curl --proxy` works, Gateway bypasses proxy | Missing matching property, wrong namespace, or different HTTP client | Compare Gateway Netty route, proxy logs, and effective config |
| `UnknownHostException` on proxy host | Pod cannot resolve proxy hostname | Check DNS inside Gateway's Pod/namespace |
| `UnknownHostException` on upstream via proxy | Proxy cannot resolve upstream name, or custom resolver resolves locally | Separate DNS at proxy vs. Gateway |
| Proxy returns `407` | Missing/wrong proxy credentials, unsupported auth mechanism | Check username/password config and proxy policy |
| Proxy returns `403` or rejects CONNECT | Allowlist, port policy, or CONNECT method blocked | Inspect proxy access logs, target hostname/port |
| HTTPS through proxy fails with `SSLHandshakeException` | CA/trust, SNI, cert hostname, or TLS interception | Inspect TLS handshake after CONNECT and certificates |
| External HTTP fails via proxy while HTTPS succeeds | Proxy forbids CONNECT on port 80 or blocks host | Check CONNECT policy for HTTP targets |
| `orders.default.svc.cluster.local` hits egress proxy | Missing/mis-escaped bypass regex or unexpected actual host | Inspect `non-proxy-hosts-pattern` and resolved host |
| Internal `lb://` route still hits proxy | Discovery returns IP/hostname missing the pattern | Inspect `ServiceInstance` host/port and adjust regex |
| 404 from Gateway | Route predicate/path mismatch | Check route registration and `StripPrefix`/rewrites |
| 401 from backend | Invalid token/auth to backend | Do not confuse with `407` from proxy |
| Intermittent 502/503/504 | Proxy outage, timeouts, pool saturation, upstream unavailable | Check each hop, Netty metrics, and proxy health |
| Enabling wiretap leaks credentials | Overly verbose debugging in production | Disable wiretap/sensitive logs; rotate exposed secrets |

### 13.1. Distinguishing failures before and after HTTP CONNECT

Quick diagnostic checklist:

```text
(1) Can Gateway connect to proxy host:port?
        No  -> DNS/network/firewall/connection timeout
        Yes
(2) Does proxy accept CONNECT target-host:target-port?
        No  -> 407/403/502/proxy policy
        Yes
(3) Does HTTPS handshake with target succeed?
        No  -> CA/hostname/SNI/TLS interception
        Yes
(4) Does upstream return an HTTP response?
        No  -> timeout/upstream/transport
        Yes -> inspect status/headers/body and filter chain
```

Always identify the exact **hostname, port, and scheme** used by the Gateway. An `lb://` route can switch instances between requests; never diagnose under the assumption every request hit the same backend.

## 14. Security: a proxy does not replace API policies

An egress proxy governs the **network path**, yet Gateway security also requires:

- **Authentication and authorization:** Spring Security/JWT at the edge and business authorization inside services.
- **Rate limiting:** throttling based on trusted identity/API keys rather than relying solely on proxies.
- **Circuit breakers, timeouts, retries:** handling slow or failing proxies/upstreams; never unconditionally retry non-idempotent writes.
- **Per-hop TLS:** protecting client → Gateway and Gateway → upstream, managing trust and mTLS as required.
- **Secret management:** keeping proxy credentials, JWT secrets, and certificates out of source code, traces, and logs.
- **Network enforcement:** proxy bypass is a connection routing choice, **not a firewall policy**; block unauthorized direct egress at the infrastructure layer.
- **Observability:** route IDs, validated upstream hosts, proxy status, latency, and SSL errors; avoid logging sensitive URLs or bodies.

A notable risk is **SSRF and egress abuse**: if route URIs, target hosts, or upstream-controlling headers come directly from client input, attackers can abuse the Gateway/proxy to reach internal services or metadata endpoints. Pin routes to allowlisted backends, guard against DNS rebinding on dynamic targets, enforce network policies, and never treat "having an egress proxy" as absolute SSRF immunity.

### 14.1. Never expose proxy credentials

`Proxy-Authorization` is meant strictly for the proxy and must never be forwarded arbitrarily to upstreams. Distinguish hop-by-hop headers from forwarded request headers. Never write to logs:

- Proxy passwords or sensitive usernames.
- Bearer tokens, Cookies, Set-Cookie headers, API keys.
- Request/response bodies containing user data.
- Full HTTP headers without filtering/redaction.

When rotating proxy passwords, know your HTTP client configuration's restart/reload procedure. Never assume a running process automatically picks up new environment secrets without a supported refresh mechanism.

## 15. Design scenario: outbound to partners and internal Kubernetes

Suppose a Gateway serves three APIs:

| Public API | Backend URI | Network policy |
| --- | --- | --- |
| `/partners/invoices/**` | `https://billing.partner.example.test` | Must go through approved egress proxy |
| `/internal/orders/**` | `lb://order-service` | Direct calls to internal pods/services |
| `/status` | `forward:///internal/status` | Handled by local WebFlux handler |

Recommended design:

1. Declare routes and path/header filters explicitly without accepting arbitrary target hosts from clients.
2. Configure HTTP client proxy from environment variables **only in profiles needing egress**.
3. Build the bypass regex from **actual ServiceInstance hostnames/IPs**, not merely the logical `order-service` name.
4. Configure ingress/network policies forcing public outbound traffic through the proxy while permitting scoped internal traffic.
5. Confirm the proxy allows `CONNECT` to `billing.partner.example.test:443`.
6. Verify TLS certificates/hostnames and proxy authentication.
7. Send test requests; cross-check proxy logs, upstream logs, route IDs, and responses.
8. Test proxy outages: ensure the Gateway fails gracefully with proper timeouts and no retry storm.
9. Verify the local `forward` route is not mistaken for proxied outbound HTTP.

If an `lb://` pool contains instances registered by IP, a `.svc.cluster.local` suffix regex will not bypass them. This is frequently where staging and production diverge despite nearly identical configuration files.

## 16. Pre-production checklist

- [ ] Identified the **outbound forward proxy** cleanly, without confusing it with reverse proxies/ingresses.
- [ ] Matched the Gateway Server WebFlux starter and `httpclient.proxy` namespace for your running version.
- [ ] Supplied proxy `host`, `port`, and `type` from deployment config and verified DNS/network reachability.
- [ ] Confirmed the proxy permits `CONNECT` to all required upstream hostnames/ports.
- [ ] Protected `username/password` via secret management, with rotation and log redaction.
- [ ] Verified `non-proxy-hosts-pattern` is a **Java regex** tested against both internal hostnames and discovery IPs.
- [ ] Did not assume `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` configure all Gateway clients automatically.
- [ ] Separated HTTP proxy, HTTP upstream, HTTPS upstream, and TLS interception cleanly.
- [ ] Enforced CA/truststore, SNI/hostname, and mTLS policies; never enabled insecure trust managers.
- [ ] Verified bypassing via proxy logs, not HTTP 200 alone.
- [ ] Distinguished proxy `407` errors from upstream `401` auth errors.
- [ ] Distinguished `CONNECT`, TLS handshake, timeout, and upstream status errors.
- [ ] Tested `lb://`, discovery/caching, varying IPs/hosts, and proxy outages.
- [ ] Configured custom `WebClient` and discovery/SDK clients with separate egress settings if needed.
- [ ] Enforced network policies, target allowlists, SSRF protections, and retry/circuit breaker monitoring.
- [ ] Ensured zero proxy credentials/tokens appear in logs, traces, or public config.

## 17. Summary

**Configuring an outbound proxy for Spring Cloud Gateway Server WebFlux** configures the **Reactor Netty HttpClient** used to reach upstreams. Core properties are `httpclient.proxy.host`, `port`, `type`, `username`, `password`, and `non-proxy-hosts-pattern`; the full prefix depends on WebFlux 4.x vs. 5.x.

The key takeaway is that **an HTTP proxy in Reactor Netty generally uses `CONNECT` even for HTTP upstreams**, so corporate proxies must permit that method and port. Bypassing uses a **Java regex**, not a container `NO_PROXY` string copied verbatim. When routes use `lb://`, inspect resolved `ServiceInstance` addresses before assuming bypasses work.

Proxying is one piece of connection and TLS operations — it does not replace route predicates, filter chains, authentication, rate limiting, circuit breakers, retries, service discovery, or observability. An effective workflow is **map topology → configure per environment → verify CONNECT/bypass/TLS → inject per-hop faults → monitor and enforce with network policies**.

### References

- [Spring Cloud Gateway — Configuration Properties (WebFlux HttpClient Proxy)](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway 4.1 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.1/configprops.html).
- [Spring Cloud Gateway Server WebFlux — Global Filters / Netty Routing Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Reactor Netty — HTTP Client / Proxy Support](https://projectreactor.io/docs/netty/release/reference/http-client.html).
