# Handling URLs, Ports, and Proxy Headers in Container Environments

## 1. A Single Request Can Traverse Multiple Different Addresses

Suppose a user calls:

```text
https://ops.example.com/ops/actuator/health
```

An intermediary server (reverse proxy) can terminate TLS, strip the `/ops` prefix, and forward the request over HTTP to the application container:

```text
Caller
  -> https://ops.example.com:443/ops/actuator/health
  -> proxy
  -> http://app:9091/actuator/health
```

This is an analytical model, not a complete HTTPS deployment configuration yet. The parts of the two URLs differ because they belong to two hops:

| Component | Seen by Caller | Received by App on Internal Hop |
| --- | --- | --- |
| Protocol | HTTPS | HTTP |
| Hostname | `ops.example.com` | `app`, internal service name |
| Port | 443 | 9091 |
| Path | `/ops/actuator/health` | `/actuator/health` |

This lesson uses **Spring Boot 3.3.x**, referencing 3.3.13. Two things must be solved: routing the request to the right endpoint, and helping the application understand the caller-facing address to generate accurate links or redirects. Spring Boot provides a proxy-header handling mechanism for the second need. [Running Spring Boot behind a proxy server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server).

## 2. Distinguishing Container Port, Host Port, and Public Port

### Application Port Inside the Container

If the application listens on business port 8080 and management port 9091, a proxy on the same Compose network will call `app:9091` for Actuator.

Do not change `management.server.port` to 443 merely because the external URL uses HTTPS port 443. This property selects the port the management server actually listens on inside the Java process's environment.

### Port Published on the Host

Example of a Docker mapping:

```text
127.0.0.1:19091:9091
```

Meaning: port 19091 on the host's loopback is forwarded to port 9091 inside the container. That configuration does not change the listener inside the JVM to 19091.

On a Compose network, other containers still use the **service name and container port**. The host machine uses the published port. Do not use the host port as if it were the service's internal port. [Compose networking and HOST_PORT/CONTAINER_PORT differences](https://docs.docker.com/compose/how-tos/networking/).

### Listen Address and Localhost

In a container model using an isolated bridge network:

- `localhost` inside the proxy container is the proxy container itself.
- `localhost` on the host machine is the host machine.
- Service name `app` is provided by Compose to containers on the same network; it does not automatically become a domain name on the user's machine.
- If management binds only to `127.0.0.1` inside the application container, a proxy in another container cannot connect to that listener over the container network interface.

The hands-on lab will bind the management server to `0.0.0.0:9091` **inside the container**, while publishing only the proxy port on host loopback. You still must control who can join the internal network; not publishing a port on the host does not mean all other containers are blocked.

`EXPOSE` in a Dockerfile only documents the image's intended port. It does not start a listener, publish ports on the host, or create authorization controls. [Meaning of Dockerfile EXPOSE](https://docs.docker.com/reference/dockerfile/#expose).

## 3. What Does Proxy Information Help Restore?

When protocol, hostname, port, or path prefix changes, the proxy can pass original information via HTTP headers.

| Header | Information Commonly Expressed |
| --- | --- |
| `Forwarded` | Standard header containing parameters such as `for`, `proto`, `host` |
| `X-Forwarded-Proto` | Caller-side protocol, e.g., `https` |
| `X-Forwarded-Host` | Public hostname |
| `X-Forwarded-Port` | Caller-side port |
| `X-Forwarded-Prefix` | External prefix stripped by the proxy or needing reflection when generating URLs |
| `X-Forwarded-For` | Client address info per proxy-chain policy |

`X-Forwarded-*` headers are common conventions, not all parts of the standard `Forwarded` header. For Servlet apps, `ForwardedHeaderFilter` can adjust how the application sees protocol, hostname, port, and redirects. [ForwardedHeaderFilter API in Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html).

### Do Not Confuse Information Restoration With Path Rewriting

In the opening example:

```text
Proxy receives:             /ops/actuator/health
Proxy sends to application: /actuator/health
Prefix to reflect:          /ops
```

The proxy must actually perform the path-rewriting rule. `X-Forwarded-Prefix: /ops` does not replace the proxy's routing rules by itself.

On the Spring side, prefix handling allows caller-facing URLs to be `/ops/actuator/health` even when the internal URI dropped `/ops`. Servlet prefix handling is implemented in the [ForwardedHeaderFilter 6.1.21 source](https://github.com/spring-projects/spring-framework/blob/v6.1.21/spring-web/src/main/java/org/springframework/web/filter/ForwardedHeaderFilter.java).

Do not mechanically put `/ops` into every layer at once. If the proxy already preserves the prefix, the app also has a matching context path, and headers declare another prefix, URLs can end up missing or duplicating segments. First write down the exact URI entering each hop.

## 4. Choosing How Spring Boot Processes Forwarded Headers

Key property:

```properties
server.forward-headers-strategy=framework
```

| Value | Handling Selected by Boot |
| --- | --- |
| `NONE` | Does not automatically apply this forwarded-headers mechanism |
| `NATIVE` | Relies on embedded web server support |
| `FRAMEWORK` | Uses Spring Framework support |

With `FRAMEWORK`, Servlet uses `ForwardedHeaderFilter`; Reactive uses `ForwardedHeaderTransformer`. Capabilities and configuration of `NATIVE` depend on the server—do not assume every prefix header is handled identically to `FRAMEWORK`.

The hands-on lab picks `framework` to demonstrate path prefixes. Do not register an extra custom filter just to duplicate what Boot already configures. Boot 3.3 documentation also notes the default can be `NATIVE` on supported cloud platforms and `NONE` elsewhere; merely running in a container does not mean the application already processes forwarded headers. [Boot 3.3 forwarded headers strategies](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server).

### Trust Boundaries Are Part of Configuration

The application cannot tell by itself whether a header came from a real proxy or was sent by the caller. At the system's ingress boundary:

1. The proxy strips untrusted incoming forwarded headers from outside.
2. The proxy regenerates values from information it is allowed to trust.
3. The internal path to the application is restricted per the chosen network architecture.

With a single edge proxy, do not blindly append caller-supplied `X-Forwarded-For` values. With multiple proxies, specify which hops are trusted and who normalizes the chain. Tomcat native's trusted-proxy rules also do not automatically act as an IP filter for the Framework strategy. [ForwardedHeaderFilter trust notes](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html).

## 5. Local Lab: Proxy and Application in Two Containers

The goal is to test **Actuator paths and generated links**, so the lab uses local HTTP. External HTTPS is analyzed separately in section 7.

Prepare a new lab directory with an executable Spring Boot 3.3.x JAR named `app.jar`. The JAR needs a startup class, `spring-boot-starter-web`, and `spring-boot-starter-actuator`; the lab assumes no Spring Security, custom filters, or custom code altering the example. Use Docker Engine/Desktop supporting Linux containers and Compose.

Required files:

```text
proxy-lab/
  app.jar
  Dockerfile
  application.yml
  compose.yml
  nginx.conf
```

This is a guide for learners to build a standalone lab; the configuration requires no edits to business controller code.

### 5.1. application.yml

```yaml
server:
  port: 9091
  address: 0.0.0.0
  forward-headers-strategy: framework
  ssl:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      base-path: /actuator
      discovery:
        enabled: true
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

In the lab, the app and Actuator share listener 9091; `management.server.port` is not set. The config selects internal port and paths, not host port 8088 or external prefix `/ops` as listener/base-path settings.

`framework` configuration participates in Boot's filter registration on the Servlet server used in the lab. If a real project separates the management port or overrides filters/server config, verify links on the management port itself; do not take results on the business port as proof for the other port. [Boot 3.3.13 forwarded filter registration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/web/servlet/ServletWebServerFactoryAutoConfiguration.java).

### 5.2. Dockerfile

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar
COPY application.yml /app/application.yml
EXPOSE 9091
ENTRYPOINT ["java", "-jar", "/app/app.jar", "--spring.config.location=file:/app/application.yml"]
```

JRE 21 runs the prebuilt JAR; this Dockerfile does not compile source code. Uses the Java image from the [Eclipse Temurin Official Image](https://hub.docker.com/_/eclipse-temurin).

### 5.3. compose.yml

```yaml
services:
  app:
    build: .

  proxy:
    image: nginx:stable-alpine
    depends_on:
      - app
    ports:
      - "127.0.0.1:8088:80"
    volumes:
      - "./nginx.conf:/etc/nginx/conf.d/default.conf:ro"
```

Proxy and app share the default Compose network; the proxy calls `app:9091`. The app has no `ports` publishing 9091 directly to the host in this lab. Host port 8088 maps to port 80 of the proxy container.

The Nginx image tag in the lab comes from the [Nginx Official Image](https://hub.docker.com/_/nginx). For environments needing exact reproducibility, pin versions/digests per project process.

### 5.4. nginx.conf

```nginx
server {
    listen 80;
    server_name localhost;

    location /ops/ {
        proxy_pass http://app:9091/;

        proxy_set_header Host localhost:8088;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host localhost;
        proxy_set_header X-Forwarded-Port 8088;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header X-Forwarded-Prefix /ops;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Ssl "";
    }

    location / {
        return 404;
    }
}
```

The values `localhost`, 8088, and `http` are the **local lab's** public address, set explicitly. Do not copy them verbatim onto a real HTTPS domain.

Read the two independent parts:

- `location /ops/` combined with `proxy_pass http://app:9091/;` replaces `/ops/` with `/` before forwarding. Thus `/ops/actuator/health` enters the app as `/actuator/health`.
- The headers reconstruct external details. Incoming `Forwarded` and `X-Forwarded-Ssl` are dropped; remaining headers are overwritten according to this lab's single-proxy policy.

The trailing `/` after the port in `proxy_pass` governs URI replacement rules. Do not remove or add it without recalculating paths. Nginx also specifies that headers with empty values are not forwarded. [`proxy_pass` and `proxy_set_header` rules](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

The port declared in headers is **8088**, not 80 where Nginx listens inside the container. This is precisely the difference between the caller-facing port and an internal hop's port.

## 6. Verifying Both Data and Generated Links

### Start the Lab

In PowerShell, at the lab directory:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs app
docker compose exec proxy nginx -t
```

Wait until the application starts successfully before making HTTP calls. List-form `depends_on` only orders container startup; it does not guarantee Spring Boot is ready to accept connections the moment the proxy starts. [Startup order and readiness in Compose](https://docs.docker.com/compose/how-tos/startup-order/).

### 6.1. Verify Health Through the Proxy

```powershell
curl.exe --silent --show-error --max-time 5 --output NUL --write-out "%{http_code}\n" "http://localhost:8088/ops/actuator/health"
```

When the application is healthy and lab assumptions hold, expected stdout:

```text
200
```

This code shows the request reached the endpoint. It does not yet prove every URL generated by the application is correct.

### 6.2. Read Links From the Discovery Page

```powershell
$document = curl.exe --silent --show-error --max-time 5 "http://localhost:8088/ops/actuator" | ConvertFrom-Json
$document._links.health.href
```

Expected output is one line:

```text
http://localhost:8088/ops/actuator/health
```

Verify all four components: `http`, `localhost`, `8088`, `/ops/actuator/health`. Do not accept it merely because the URL ends with `health`.

Actuator builds links from the discovery page's request URL, so properly processing request metadata prevents returning links with container names, internal ports, or missing prefixes. This is inferred by applying [Boot 3.3.13 EndpointLinksResolver source](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java).

If you switch `server.forward-headers-strategy` to `none` in an app with no other forwarded-header handling, health may still return 200 because the proxy routed properly, yet links can miss `/ops`. Retest after rebuilding/restarting the config to observe the two independent responsibilities.

### 6.3. Verify the Proxy Does Not Keep Spoofed External Headers

Send test values through the **lab's proxy port**:

```powershell
$document = curl.exe --silent --show-error --max-time 5 -H "Forwarded: proto=https;host=untrusted.invalid" -H "X-Forwarded-Host: untrusted.invalid" "http://localhost:8088/ops/actuator" | ConvertFrom-Json
$document._links.health.href
```

Expected link remains:

```text
http://localhost:8088/ops/actuator/health
```

This result tests the two headers sent in the lab scenario; it does not replace testing the entire trust boundary, proxy chains, or direct paths that could bypass the proxy.

The outputs in section 6 are conditional expected results, not a claim of running across all Docker/Spring Boot setups. When finished with the standalone lab:

```powershell
docker compose down
```

## 7. Moving the Model to HTTPS or Multi-Layer Infrastructure

Suppose a real proxy terminates TLS directly at `https://ops.example.com` port 443, while the app receives HTTP on port 9091. Trusted info passed to the app must reflect the external side:

| Info | Value in HTTPS Model |
| --- | --- |
| Original protocol | `https` |
| Original host | `ops.example.com` |
| Original port | `443` |
| External prefix | `/ops` |
| URI forwarded to app | `/actuator/health` |
| External health URL | `https://ops.example.com/ops/actuator/health` |

Do not set `X-Forwarded-Proto=https` just so links "look secure" when callers actually use HTTP. The header describes an already-completed hop; it does not encrypt the proxy → app connection.

If Nginx sits behind a load balancer that already terminated TLS, `$scheme` at Nginx may only be `http`. Identify which proxy owns trusted original info, restrict connection sources, and normalize headers at the right boundary. Do not take raw client-sent headers to infer security state.

With a separate management port, also clearly define `management.server.base-path`, `management.endpoints.web.base-path`, and actual endpoint mappings. Those properties pick the paths the app serves; forwarded prefix describes the external prefix, not a universal substitute for every path property. [Relationship between paths and management port](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 8. Troubleshooting Hop by Hop Instead of Randomly Editing URLs

| Symptom | Hop to Check |
| --- | --- |
| Cannot connect to `localhost:8088` | Host port, proxy container, and port publishing |
| Proxy returns 502 | Service name, internal port, app bind address, whether app is ready |
| Proxy reaches app but gets 404 | Prefix strip/keep rules and internal endpoint paths |
| Health 200 but links contain `app:9091` | Original host/port and forwarded-headers strategy |
| Links missing `/ops` | Prefix header, handling strategy, and whether rewrite rules align |
| Links duplicate prefix | Did two layers prepend the prefix twice |
| Generated URLs use HTTP while external is HTTPS | TLS termination point and original protocol info source |
| URL changes based on client's spoofed headers | Trust boundary and direct paths bypassing the proxy |
| 401/403 occurs | Authentication, authorization, or filters; not just ports/rewrites |

When documenting diagnostics, tabulate each hop with **protocol, host, port, URI, and normalized headers**. Check both `Location` on redirects and the JSON links Actuator actually returns.

If the app container is recreated, the service name remains the config target while its IP address may change. Proxies or long-lived connections need resolution/reconnection mechanisms suited to the deployment; in the lab, you may need to restart the proxy after recreating the app. Do not hardcode container IPs to mask that behavior. [Updating containers in a Compose network](https://docs.docker.com/compose/how-tos/networking/).

## 9. Model Self-Check

**Scenario 1:** The host publishes `19091:9091`. Should a proxy on the same Compose network call `app:19091` or `app:9091`?

Use `app:9091`: inter-service communication uses the container port.

**Scenario 2:** `GET /ops/actuator/health` returns 200, yet links on the discovery page lack `/ops`. Can you conclude the proxy is completely wrong?

Not yet. Request routing may be fine while info used to generate URLs was not restored properly.

**Scenario 3:** Only `X-Forwarded-Prefix: /ops` is added, while the proxy still sends a URI the application does not serve.

Fix the routing/URI rewrite rule according to each hop's contract. Headers do not create endpoints or replace proxy routing rules.

**Scenario 4:** The app enables `FRAMEWORK`, yet any client can call the app port directly and send its own forwarded headers.

Control the connection path and header normalization boundary. Picking a processing strategy does not authenticate proxy identity.

**Scenario 5:** The external URL is HTTPS 443 and the internal app is HTTP 9091. Should `management.server.port` be changed to 443?

No. Keep the internal listener port as designed; forward traffic and external metadata cleanly through a trusted proxy.
