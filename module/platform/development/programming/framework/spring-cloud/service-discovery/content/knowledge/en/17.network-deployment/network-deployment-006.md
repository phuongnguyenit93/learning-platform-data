# Reverse Proxy, TLS Termination, and Advertised Address

In microservice deployments, the address an application listens on is not necessarily the address clients see. A service might run at `10.0.2.15:8080`, receive requests from a reverse proxy, while users access it via `https://api.example.com`. If the service registers the wrong address in Eureka or Consul, consumers may receive an unreachable endpoint, generate URLs with the wrong protocol, or bypass the required proxy layer.

To configure this properly, distinguish three types of addresses:

- **Bind address:** the address and port on which the web server process listens.
- **Advertised address:** the address and port published in the service registry for consumers to find and call the instance.
- **Public address:** the hostname, port, and scheme external clients use via a reverse proxy, load balancer, or ingress.

TLS termination and forwarded headers introduce another boundary: the client-to-proxy connection can be HTTPS, while the proxy calls the application over internal HTTP. The application must know the original request was HTTPS if it needs to generate accurate redirects, absolute URLs, cookies, or callbacks.

## 1. Reverse Proxy Architecture

A reverse proxy receives requests on behalf of one or more backends. Clients only know the proxy's hostname; the proxy chooses a backend based on host, path, headers, load-balancing algorithm, or route configuration.

For example:

- The client accesses `https://api.example.com/orders`.
- The reverse proxy receives the TLS connection on port 443.
- The proxy forwards the request into the internal network to `order-service` at `10.0.2.15:8080`.
- The application processes the request and returns the response through the proxy.

~~~mermaid
flowchart LR
    CLIENT["Browser / API client"] -->|"HTTPS :443"| PROXY["Reverse proxy / Ingress"]
    PROXY -->|"HTTP :8080"| APP["Spring Boot application"]
    APP --> DB[("Database")]
    APP --> REG[("Eureka / Consul")]
~~~

A reverse proxy typically takes on several responsibilities:

- Exposing the external hostname and access port.
- Terminating TLS and managing client-facing certificates.
- Routing by hostname, path, or headers.
- Load balancing across backends.
- Rate limiting requests, enforcing access policies, and writing access logs.
- Passing original request information to backends via forwarded headers.

A reverse proxy does not necessarily replace service discovery. It can use a service registry to look up backends, or use static endpoint configuration, DNS, Kubernetes Services, or another mechanism.

## 2. Distinguishing Bind, Advertised, and Public Addresses

These three addresses can be identical in simple deployments, but often differ when running in containers, VMs, Kubernetes, or behind a proxy.

| Address type | Example | Who uses it? | Meaning |
|---|---|---|---|
| Bind address | `0.0.0.0:8080` | Web server in container | Listens on container interfaces |
| Advertised address | `inventory-1.internal:8080` | Consumers on internal network | Instance endpoint registered in registry |
| Public address | `https://api.example.com:443` | Browser or external client | Address exposed by reverse proxy |

`0.0.0.0` is a bind address for listening on all matching IPv4 interfaces. It is not an address for consumers to connect to and should not be registered as an advertised address.

An internal hostname may resolve differently across networks. For example, `inventory-1.internal` only resolves inside a VPC or cluster. If consumers are outside that network, this endpoint is unsuitable for them. Conversely, if every internal service calls through `api.example.com`, the system establishes a single entry point but becomes dependent on proxy routing and policies.

### 2.1. The Registry Must Advertise an Address Consumers Can Reach

The registry does not turn a private address into a public one, nor does it know how a proxy routes requests. The provider or discovery integration must advertise a host, port, and scheme that fit the topology.

There are two common patterns:

**Pattern A — Internal direct discovery**

- Each instance registers its internal hostname/IP and port.
- Consumers in the same network query the registry.
- LoadBalancer selects an instance and calls it directly.
- The reverse proxy only serves external traffic.

**Pattern B — Discovery via gateway**

- Providers register internal endpoints so the gateway can find backends.
- External clients only know the gateway's hostname.
- The gateway uses discovery or route configuration to forward requests to instances.
- The public address is not treated as an individual endpoint of each provider instance.

~~~mermaid
flowchart TB
    subgraph INTERNAL["Internal Network"]
        R[("Service Registry")]
        O["order-service"]
        I1["inventory instance A"]
        I2["inventory instance B"]
        GW["API Gateway"]
        R --> O
        R --> GW
        O -->|"Internal service call"| I1
        GW -->|"Discovery / route"| I2
    end
    EXT["External client"] -->|"HTTPS api.example.com"| GW
~~~

Do not register the gateway's public hostname as the address of each instance if the gateway cannot distinguish and route to the exact instance the way LoadBalancer expects. In a gateway architecture, let the registry advertise internal endpoints for the gateway; the gateway itself is the public entry point.

## 3. What Is TLS Termination?

TLS termination is when an intermediary component such as Nginx, HAProxy, a cloud load balancer, or Kubernetes ingress decrypts TLS connections from clients. The proxy holds the public certificate and forwards requests to backends.

Basic flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Reverse proxy
    participant A as Spring Boot app

    C->>P: HTTPS request (TLS)
    Note over P: TLS termination / decrypt
    P->>A: HTTP request over private network
    A-->>P: HTTP response
    P-->>C: HTTPS response (TLS)
~~~

In this model:

- Clients see the `https` scheme.
- The proxy accepts TLS on public port 443.
- The backend may listen only on HTTP port 8080.
- The proxy typically sends `X-Forwarded-Proto: https` to indicate the original scheme.

TLS termination reduces certificate management on individual applications, yet the proxy-to-backend hop still needs protection according to the threat model. If the internal network is untrusted, use TLS re-encryption or mutual TLS between the proxy and services.

### 3.1. Three Common Connection Modes

| Mode | Client → Proxy | Proxy → Backend | Characteristics |
|---|---|---|---|
| TLS termination | HTTPS | HTTP | Proxy decrypts TLS; backend receives HTTP |
| TLS re-encryption | HTTPS | HTTPS | Proxy decrypts request then opens a new TLS connection to backend |
| TLS passthrough | Intact TLS | Intact TLS | Proxy routes at TCP/SNI level without decrypting HTTP |

TLS passthrough generally cannot perform routing by HTTP path or headers because the proxy cannot read encrypted HTTP content. It fits cases where backends must terminate TLS themselves or end-to-end TLS to the workload is required.

TLS re-encryption creates two independent TLS sessions. Backend certificates should be verified by the proxy; do not disable certificate verification just to make connections work.

## 4. Forwarded Headers Carry Original Request Information

After TLS termination, the backend only sees an HTTP connection from the proxy. If the backend infers scheme, host, and port from the socket, it might assume the original request was `http://order-service:8080`.

The proxy can send headers:

| Header | Meaning |
|---|---|
| `Forwarded` | RFC 7239 standard header carrying `for`, `host`, `proto` |
| `X-Forwarded-For` | Original client IP address or proxy chain |
| `X-Forwarded-Host` | Host used by the client to access the service |
| `X-Forwarded-Port` | Public port of the request |
| `X-Forwarded-Proto` | Original scheme, usually `https` |
| `X-Forwarded-Prefix` | External path prefix if the proxy strips a prefix before forwarding |

Example client call:

~~~text
https://api.example.com/orders
~~~

The proxy may forward to the backend:

~~~http
GET /orders HTTP/1.1
Host: order-service:8080
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-Proto: https
X-Forwarded-For: 203.0.113.25
~~~

If Spring Boot handles forwarded headers properly, the application can construct redirects, absolute links, and URLs in responses based on the public address.

### 4.1. Spring Boot 3.x Configuration

With Spring Boot 3.x, the common property is `server.forward-headers-strategy`:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Values:

- `NONE`: do not process forwarded headers.
- `NATIVE`: use support from the web server such as Tomcat or Jetty.
- `FRAMEWORK`: use `ForwardedHeaderFilter` for Servlet or `ForwardedHeaderTransformer` for WebFlux.

If the web server cleanly supports the headers the proxy sends, `NATIVE` is often an efficient choice. If processing via Spring Framework is needed, you can use `FRAMEWORK`.

### 4.2. Spring Boot 4.2 Configuration

In Spring Boot 4.2 documentation, configuration is organized under `server.request.header.forwarded.strategy`:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
~~~

Options described in current documentation include:

- `none`: ignore forwarded headers.
- `web-server`: use embedded web server support.
- `framework`: use Spring Framework support.

For standard RFC 7239 headers, you can configure naming accordingly:

~~~yaml
server:
  request:
    header:
      forwarded:
        naming: rfc-7239
        strategy: framework
        use-prefix: true
~~~

The `use-prefix` property only needs to be enabled when the proxy sends `X-Forwarded-Prefix` and the application needs to recognize the original path prefix. Use the exact property names and values for your project's Spring Boot version; do not copy 3.x config to 4.2 without checking.

## 5. Configuring Reverse Proxies to Send Forwarded Headers

Example of Nginx terminating TLS and forwarding HTTP requests to a backend:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/nginx/tls/api.crt;
    ssl_certificate_key /etc/nginx/tls/api.key;

    location / {
        proxy_pass http://order_backend;

        proxy_set_header Host $host;
        proxy_set_header Forwarded "";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

This is an illustrative example. `order_backend` needs to be declared in an Nginx upstream or the service discovery mechanism Nginx uses. The example places Nginx at the public edge, so it overwrites `X-Forwarded-For` with the direct peer address `$remote_addr`. If a trusted load balancer sits in front, configure chained proxies to preserve the hop chain according to the trust boundary and only trust configured proxies.

Proxies must handle forwarded headers intentionally:

- Strip or overwrite forwarded headers sent by clients.
- Generate new values based on the connection the proxy actually receives.
- If multiple proxies are chained, clearly define which proxies may append and read each part of the chain.
- Do not pass an arbitrary `X-Forwarded-Host` from the Internet into the application.

If a proxy only appends `$proxy_add_x_forwarded_for`, the IP list can contain multiple hops. The backend needs to know the trust boundary to identify the real client IP.

## 6. Trusting Proxies and Preventing Forwarded Header Spoofing

Forwarded headers can affect redirects, absolute URLs, client IP addresses, cookies, and security decisions. If a backend accepts these headers from any client, an attacker can send:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
X-Forwarded-For: 127.0.0.1
~~~

The application might build links or redirects to a fake hostname, log an incorrect client IP, or misjudge the request origin.

Measures to apply:

1. Allow backends to accept traffic only from controlled reverse proxies or network segments.
2. Configure proxies to strip and overwrite incoming forwarded headers.
3. Enable forwarded header processing only when the application sits behind a trusted proxy.
4. Restrict the list of trusted proxies by IP/subnet.
5. Test multi-proxy chains to ensure accurate client IP extraction.
6. Do not use `X-Forwarded-For` as an identity authentication mechanism.

With Tomcat, `RemoteIpValve` can use `server.tomcat.remoteip.internal-proxies` to specify trusted internal proxies. Do not configure trusting all addresses in production.

## 7. Tomcat and Redirects When TLS Terminates at the Proxy

A common scenario is users calling HTTPS while the proxy forwards HTTP to Tomcat. When the application issues a redirect, Tomcat may view the internal request as HTTP if forwarded headers are not processed before redirecting.

With Spring Boot 3.x and Tomcat, Spring Boot documentation notes the configuration:

~~~yaml
server:
  forward-headers-strategy: native
  tomcat:
    redirect-context-root: false
~~~

In Spring Boot 4.2, the Tomcat property name becomes:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
  tomcat:
    servlet:
      redirect-context-root: false
~~~

Exact settings depend on the version and redirect type. Check embedded web server documentation for your exact version before applying. After configuring, test 301/302 responses, login redirects, and URLs in responses to confirm they use HTTPS and the public hostname.

## 8. Advertising Addresses with Eureka

Eureka registrations contain the instance's host, port, status URL, health URL, and metadata. Consumers use this information to build URIs to call the service.

Commonly used properties:

| Property | Meaning |
|---|---|
| `eureka.instance.hostname` | Advertised hostname |
| `eureka.instance.ip-address` | Advertised IP |
| `eureka.instance.prefer-ip-address` | Prefer IP over hostname when determining host |
| `eureka.instance.non-secure-port` | Advertised HTTP port |
| `eureka.instance.non-secure-port-enabled` | Enable advertising the non-secure port |
| `eureka.instance.secure-port` | Advertised HTTPS port |
| `eureka.instance.secure-port-enabled` | Enable advertising the secure port |
| `eureka.instance.status-page-url` | Absolute status page URL |
| `eureka.instance.health-check-url` | Absolute health check URL |
| `eureka.instance.home-page-url` | Absolute home page URL |

### 8.1. Internal Endpoint Registration Pattern

If consumers in the cluster call providers directly over internal HTTP:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  address: 0.0.0.0
  port: 8080

eureka:
  instance:
    hostname: inventory-1.internal
    prefer-ip-address: false
    non-secure-port-enabled: true
    non-secure-port: 8080
    secure-port-enabled: false
~~~

In this pattern, the registry advertises an internal hostname and port reachable by consumers. Do not register `0.0.0.0` since that is only a bind address.

When running in containers or Kubernetes, the hostname/IP must be resolvable from every consumer authorized to call the service. You can use pod IP, internal DNS, VM hostname, or a service address suitable for the topology.

### 8.2. Direct HTTPS Advertisement Pattern

If each instance actually accepts HTTPS on port 8443:

~~~yaml
eureka:
  instance:
    hostname: inventory-1.internal
    non-secure-port-enabled: false
    secure-port-enabled: true
    secure-port: 8443
    status-page-url: https://inventory-1.internal:8443/info
    health-check-url: https://inventory-1.internal:8443/health
    home-page-url: https://inventory-1.internal:8443/
~~~

When secure port is enabled and non-secure port is disabled, Spring Cloud DiscoveryClient returns URIs starting with `https` for this service. Ensure certificates, hostname verification, and consumer trust stores are valid.

### 8.3. When TLS Terminates at the Proxy

If TLS terminates at the proxy while Eureka registers each backend instance for internal consumers to call directly, advertise the backend's actual internal endpoint. Do not declare the proxy's secure port 443 for every instance unless the proxy properly routes to each specific instance via that host/port.

If all consumers must go through a proxy/gateway, register the gateway as a service or have consumers use a configured public route. Do not mix the gateway's public URL into internal provider registrations without a corresponding route.

Eureka also has status, health, and home page URLs. If using a proxy to expose these pages, set appropriate absolute URLs. These URLs are separate metadata; do not assume they automatically follow the public hostname when a proxy terminates TLS.

## 9. Advertising Addresses with Consul

Spring Cloud Consul registers host, port, service ID, name, and tags via the Consul HTTP API. According to Spring Cloud Consul documentation, the application determines the local instance's hostname and IP by default; you can override them using:

- `spring.cloud.consul.discovery.hostname`
- `spring.cloud.consul.discovery.ip-address`
- `spring.cloud.consul.discovery.prefer-ip-address`

Example advertising an internal IP:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        prefer-ip-address: true
        ip-address: 10.0.2.15
~~~

If using an internal hostname:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        hostname: inventory-1.internal
        prefer-ip-address: false
~~~

The registered address must be reachable from consumers and the health check agent. If the Consul Agent runs on another node or in another network, verify the route from the agent to the health check endpoint.

### 9.1. Health Checks When Behind a Proxy

Spring Cloud Consul typically registers an HTTP health check pointing to `/actuator/health`. The agent calls the URL constructed from the registered address and port plus the health check path.

If the application only accepts requests via a public proxy, yet the Consul Agent cannot reach the public endpoint or health path, the check can turn critical even while the external API works. Conversely, if the check goes through a shared proxy, it may check the gateway instead of the specific instance.

For per-instance health checks, ensure the Consul Agent can reach that specific instance's endpoint on the internal network. If the management server uses a separate port, configure the management service or corresponding health check port/path.

### 9.2. Public URL and Service Address Are Two Different Pieces of Data

A Consul registration address usually serves instance routing. A public URL can be exposed via ingress, API Gateway, DNS, or separate metadata. Do not use one address field for both purposes if they have different reachability.

When external consumers need access, design public routes and DNS/TLS at the proxy. When internal consumers use DiscoveryClient, advertise a directly reachable internal service address.

## 10. Public Routes via API Gateway or Ingress

A gateway is often the single entry point for external clients. The gateway can route by path or host:

| Public route | Backend |
|---|---|
| `https://api.example.com/orders/**` | `order-service` |
| `https://api.example.com/inventory/**` | `inventory-service` |
| `https://api.example.com/payments/**` | `payment-service` |

The gateway can use service discovery to find backends, while external clients only know `api.example.com`. Each backend's registry entry can still hold internal endpoints.

With Kubernetes Ingress, TLS usually terminates at the ingress controller. Behind it, Services/pods may receive HTTP within the cluster or HTTPS if re-encryption is configured. `Ingress` and `Service` are two distinct layers: Ingress exposes hosts/paths; Service provides internal endpoints for workloads.

Do not register an application-wide Ingress hostname into Eureka as if it were each pod's individual hostname. That loses per-instance identity and can cause LoadBalancer to pick a shared address repeatedly across multiple registrations.

## 11. End-to-End Example: External HTTPS, Internal HTTP

Suppose:

- Public host: `https://api.example.com`
- Nginx listens on port 443.
- `order-service` runs at `10.0.2.15:8080`.
- `inventory-service` runs at `10.0.2.16:8081`.
- Internal consumers call services through Eureka.

Topology:

~~~mermaid
flowchart TB
    EXT["External client"]
    NGINX["Nginx / Ingress<br/>TLS termination :443"]
    ORDER["order-service<br/>10.0.2.15:8080"]
    INV["inventory-service<br/>10.0.2.16:8081"]
    EUREKA[("Eureka Server")]

    EXT -->|"HTTPS api.example.com"| NGINX
    NGINX -->|"HTTP internal"| ORDER
    ORDER -->|"DiscoveryClient + LoadBalancer"| EUREKA
    EUREKA -->|"inventory-1.internal:8081"| ORDER
    ORDER -->|"HTTP internal call"| INV
~~~

Nginx forwards requests to order-service and adds forwarded headers. Spring Boot processes those headers to generate accurate redirects or absolute URLs. Meanwhile, order-service calls inventory-service via the internal address advertised by Eureka.

Illustrative configuration of `order-service`:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: native

eureka:
  client:
    serviceUrl:
      defaultZone: http://eureka.internal:8761/eureka/
~~~

Illustrative configuration of `inventory-service`:

~~~yaml
server:
  address: 0.0.0.0
  port: 8081

eureka:
  instance:
    hostname: inventory-1.internal
    prefer-ip-address: false
    non-secure-port-enabled: true
    non-secure-port: 8081
~~~

In Spring Boot 4.2, replace `server.forward-headers-strategy` with `server.request.header.forwarded.strategy` per the earlier configuration.

The key point is that the two call paths can differ: external clients go through the TLS proxy; internal service-to-service calls go directly to the advertised address. If policy requires internal traffic to also traverse a proxy or TLS, design dedicated routes and certificates for that path.

## 12. Common Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| Consumer receives `0.0.0.0` from registry | Bind address used as advertised address | Set a reachable hostname/IP |
| Consumer calls wrong port | Registry advertises container port or wrong proxy port | Check actual host/port and NAT mapping |
| Browser receives redirect to `http://` | Backend does not process `X-Forwarded-Proto` | Configure forwarded headers for the right version |
| Response links contain internal hostname | App uses internal Host instead of forwarded host | Check proxy and `X-Forwarded-Host` |
| Cookie or redirect has wrong domain | Proxy header not processed or path prefix lost | Check forwarded host, proto, prefix |
| Eureka DiscoveryClient returns `http` when client wants HTTPS | Secure port not enabled or wrong instance metadata | Check `secure-port-enabled` and `non-secure-port-enabled` |
| Eureka advertises wrong health URL | Context path, management path, or proxy URL mismatch | Set explicit URLs/paths and inspect metadata |
| Consul health check is critical | Agent cannot reach registered host/port/path | Call endpoint from the agent's network |
| Public proxy works but service-to-service fails | Registry holds public hostname unreachable from internal network | Separate internal advertised address and public route |
| Client spoofs forwarded host/IP | Backend trusts headers from untrusted sources | Have proxy overwrite headers and restrict trusted proxies |

## 13. Deployment Checklist

Before bringing a reverse proxy and service discovery to production, verify:

1. Clearly distinguish bind address, advertised address, and public address.
2. Ensure advertised host/port is reachable from every consumer that needs it.
3. Do not register `0.0.0.0`, loopback, or container hostnames unresolvable from consumers.
4. Decide between TLS termination, re-encryption, or passthrough.
5. If the proxy terminates TLS, send accurate forwarded headers.
6. Configure Spring Boot forwarded header handling for the exact Boot version.
7. Trust forwarded headers only from controlled proxies.
8. Proxy strips or overwrites client-supplied forwarded headers.
9. Verify Eureka secure port or Consul service address against the actual topology.
10. Ensure health check agents reach each individual instance's endpoint.
11. Do not advertise the public gateway URL as the individual address of each backend instance.
12. Test redirects, absolute URLs, cookies, callbacks, and health URLs.
13. Verify certificate chains and hostname verification on TLS hops.
14. Log both the original client address and peer address to aid troubleshooting.

## 14. Key Takeaways

- A reverse proxy receives requests on behalf of backends; TLS termination decrypts TLS at the proxy.
- Bind address is where the application listens; advertised address is what consumers use to call the instance; public address is what external clients access.
- Forwarded headers inform the backend of the original scheme, host, port, IP, and prefix.
- Spring Boot 3.x uses `server.forward-headers-strategy`; Spring Boot 4.2 uses `server.request.header.forwarded.strategy`.
- Process forwarded headers only from trusted proxies; proxies must strip/overwrite client-sent headers.
- Eureka provides `hostname`, `prefer-ip-address`, `secure-port`, and port enable/disable flags to advertise appropriate endpoints.
- Consul provides `hostname`, `ip-address`, and `prefer-ip-address` to control the service registration address.
- Health checks need to reach the specific instance; going through a shared proxy can check the wrong target.
- Public gateway routes and internal service registrations should be designed as two separate addressing scopes.

Reverse proxies, TLS termination, and service registries all participate in the request path yet have distinct responsibilities. When the advertised address reflects the exact network consumers use, forwarded headers are properly trusted, and TLS is clearly configured on each hop, service discovery routes reliably both inside internal networks and behind public gateways.

## References

- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 4.2 — Embedded Web Servers and Forwarded Headers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Cloud Netflix — Registering a Secure Application and Eureka Metadata](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Configuring the Service Hostname and IP Address](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
