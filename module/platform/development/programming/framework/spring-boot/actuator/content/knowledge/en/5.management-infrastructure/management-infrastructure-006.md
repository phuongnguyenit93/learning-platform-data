# Restricting Access via Internal Network, Reverse Proxy, and Firewall

## 1. Why Does Actuator Need a Separate Access Path?

Business APIs serve users; Actuator serves application monitoring and operations. These two groups of consumers usually need different access paths. For example, customers need to call order APIs, while a monitoring system only needs to read health status and selected metrics.

A strong password is still not a reason to open the management port to the entire Internet. Conversely, an internal network address alone does not prove the caller has management privileges. When designing infrastructure, answer two separate questions:

- **Network reachability:** which machines can establish a connection to the management service?
- **Usage permission:** once connected, which identities may read or perform each operation?

This lesson focuses on the first question and its relationship with the second. Examples use **Spring Boot 3.3.x** property names and a JAR-run web application model. The hands-on lab uses Java 21, Spring MVC, and Spring Boot 3.3.13 to fix a concrete version; this is not guidance for selecting the newest production version.

### Terms Used

| Term | Meaning in This Lesson |
| --- | --- |
| Bind address | Network interface address on which a process accepts connections |
| Loopback | Connection path looping back to the current network namespace, such as `127.0.0.1` |
| Management network | Network segment dedicated to monitoring and operations with controlled access sources |
| Reverse proxy | Server receiving requests and forwarding them to a backend application |
| Firewall | Connection/packet filter enforcing network policy |
| Allowlist | Permits only explicitly identified sources or paths |
| Trust boundary | Point where data or identity must be checked before trusting information from the other side |

Follow this order: draw the connection path → choose address/port → place rules at proxy and firewall → verify from multiple locations.

## 2. Composing the Control Layers Properly

A request to read Actuator must pass several conditions:

```text
Calling machine
  → has network route to destination
  → firewall permits connection
  → process listening on the right address and port
  → reverse proxy permits path, if going through proxy
  → endpoint exposed over HTTP
  → authentication/authorization policy permits, if configured
  → Actuator handles request
```

This is a path-analysis model and does not claim identical internal processing order across all infrastructures. For instance, firewalls may sit both before and after a proxy.

In Spring Boot 3.3, `management.endpoints.web.exposure.include` selects endpoints exposed over HTTP; it does not select which subnets may connect. `health` is exposed over HTTP by default. Spring Security policy is a separate layer; when declaring your own `SecurityFilterChain`, you must ensure necessary protection rules yourself. [Endpoints 3.3 documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

For example, an endpoint listed in `include` may still be unreachable from the monitoring machine because a firewall blocks the port. Conversely, permitting connections to the port does not make an unexposed endpoint appear.

**Design goal:** for every path that can reach Actuator, identify the allowed sources, where other sources are blocked, and verification evidence. Do not inspect only one URL via a public domain name and conclude the entire system is restricted.

## 3. Choosing the Right Network Model

### 3.1. Proxy and Application on the Same Host

```text
Internet → NGINX :443 → 127.0.0.1:8080, business API

Operations network → NGINX 10.20.0.10:9443
                   → 127.0.0.1:9090, Actuator

Connections from another machine → host address:9090
                                 → no matching listener
```

Here, `10.20.0.10` is an illustrative address that must actually be assigned to the host running NGINX. NGINX and the JVM must reside in the **same network namespace** for NGINX to reach the JVM's loopback.

This model narrows entry to the backend: other machines must go through NGINX's management listener. However, processes on the same host can still access loopback; a compromised host account or SSRF flaw could create extra paths. Thus, loopback does not replace access-control policies.

### 3.2. Proxy and Application on Different Hosts

If the proxy is on host A and the JVM is on host B, `127.0.0.1` on A is A itself. For the proxy to connect to the JVM, use B's real private address and restrict sources at B's firewall:

```text
Management proxy 10.20.0.10
  → application firewall: accept only from required proxy
  → JVM 10.20.0.20:9090
```

If the monitoring system accesses B directly, grant network access to that exact source. Do not open a wide CIDR block just to make a single test succeed.

### 3.3. Same Port vs. Different Port

| Option | Where Can Controls Be Applied? | Considerations |
| --- | --- | --- |
| API and Actuator on same port | Proxy by path and application policy | Standard TCP firewalls do not distinguish API from Actuator on the same port |
| Actuator on separate port | Adds filtering by port, bind address, and network route | The new port can still be publicly exposed if network config is wrong |
| Actuator over HTTP not needed | Disable HTTP management path | Must choose another suitable monitoring method |

Renaming `/actuator` to a hard-to-guess path only changes the path name; access policy still must be designed thoroughly.

## 4. Configuring Address and Port in Spring Boot

For the proxy-and-JVM-on-same-host option, the base configuration can be:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  forward-headers-strategy: none

management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
      show-components: never
```

`server.address` applies to the main listener; `management.server.address` applies to the separate management listener. In Spring Boot 3.3, configuring a separate management address is supported only when the management port differs from the main port. Disabling management HTTP with `management.server.port=-1` is an option when this channel is unnecessary. [Monitoring and Management Over HTTP 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

The configuration above chooses two loopback listeners. They are reused in the hands-on lab below. Exposing only `health` and `info` is the example's choice; a Prometheus scraping setup must add the needed library and endpoint, then open the right path for the scraper.

`show-details` and `show-components` limit health response content; they are not IP-filtering rules. Choosing the minimal needed endpoints and choosing the minimal needed access sources are complementary decisions. [Spring Boot 3.3 property reference](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

If the JVM runs on a separate host instead of alongside the proxy, the replacement snippet can be:

```yaml
management:
  server:
    address: 10.20.0.20
    port: 9090
```

This is a **replacement snippet**, not a second YAML document to append with a duplicate `management` key. The address must belong to a network interface of the JVM host. You cannot pick an arbitrary private IP and expect the process to create that interface automatically.

After deployment, verify the effective configuration from the actual listener. Environment variables, startup arguments, or deployment profiles can make the runtime state differ from the file being read.

## 5. Reverse Proxy: Separating Public Ingress and Management Ingress

The example below consists of **two `server` blocks placed inside NGINX's `http` context**, not a complete `nginx.conf`. NGINX and the JVM share a host; backends are still the two loopback listeners from section 4.

Deployment conditions:

- The host has private address `10.20.0.10`.
- TLS certificate/key files referenced in the config are issued for the domain names.
- The operational source actually seen by NGINX belongs to `10.20.30.0/24`.
- The proxy keeps whatever authentication mechanism the system requires; this snippet illustrates network restriction and routing.

### 5.1. Public Ingress Routes Only to the Business Port

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/app.crt;
    ssl_certificate_key /etc/nginx/tls/app.key;

    location = /actuator {
        return 404;
    }

    location ^~ /actuator/ {
        return 404;
    }

    location / {
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:8080;
    }
}
```

The first two rules cover both the `/actuator` root path and subpaths under the current configuration. `location =` is an exact match; `^~` gives prefix match priority over regex locations. When a real configuration has additional virtual hosts, rewrites, or locations, recheck the entire routing path. [NGINX location](https://nginx.org/en/docs/http/ngx_http_core_module.html#location)

The more important safeguard in this model is that **the public upstream points only to port 8080**. Do not create another management route under `/internal`, a fallback virtual host, or a secondary HTTP listener and proxy it to 9090 while forgetting equivalent policies.

If you change base path or context path, update and retest proxy rules. The `/actuator` string in the example does not automatically track Spring Boot's configuration.

### 5.2. Management Ingress Accepts From Selected Subnet

```nginx
server {
    listen 10.20.0.10:9443 ssl;
    server_name ops.example.com;

    ssl_certificate     /etc/nginx/tls/ops.crt;
    ssl_certificate_key /etc/nginx/tls/ops.key;

    allow 10.20.30.0/24;
    deny all;

    location = /actuator/health {
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:9090;
    }

    location = /actuator/info {
        proxy_set_header Host $host;
        proxy_pass http://127.0.0.1:9090;
    }

    location / {
        return 404;
    }
}
```

NGINX evaluates `allow`/`deny` rules in order until a match. In the example, the allowed source entering the two proxy locations is the stated subnet; remaining sources are denied at the access control phase. Locations without their own `allow`/`deny` inherit these rules from the server level. [NGINX access module](https://nginx.org/en/docs/http/ngx_http_access_module.html)

Paths not matching the two selected endpoints return 404 via the fallback location. Do not use the fallback path's status code to infer that the ACL ran: `return` can terminate the request before the access phase.

`proxy_pass` without a URI part after the port preserves the request URI for the backend. Avoid appending a trailing `/` or adding a rewrite without understanding how NGINX replaces the URI. [NGINX proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)

If health groups with subpaths are needed, add only paths actually used; the current exact-match config intentionally does not allow them yet. Likewise, if another endpoint is needed, add HTTP exposure, the proxy route, and corresponding application permissions.

### 5.3. TLS and Identity

Connections from operational machines over the network to the proxy should use TLS with certificate verification. If proxy and JVM are on different hosts, consider TLS for the proxy-JVM hop as well per infrastructure requirements.

You can add mTLS at the management ingress to verify calling machines, or retain application authentication. An IP allowlist only describes the network source, especially when multiple people share a VPN/NAT; it does not distinguish individual users behind that source.

## 6. Firewall: Limiting Connections Before HTTP Is Processed

Before writing commands, draft a policy table for the single-host model:

| Destination | Allowed Sources | Intended Policy |
| --- | --- | --- |
| NGINX 443/TCP | Product user sources | Allow per business API requirements |
| NGINX 10.20.0.10:9443/TCP | Operations network 10.20.30.0/24 | Allow only this subnet |
| JVM 8080/TCP | Processes on the same host | Loopback listener, not opened directly remotely |
| JVM 9090/TCP | Proxy/processes on the same host | Loopback listener, not opened directly remotely |
| SSH 22/TCP | Approved server admin sources | Separate rule, not broadened alongside APIs |

On a fresh Ubuntu lab machine where UFW is intentionally managed and has no conflicting broad rules, part of the policy can be expressed as:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow proto tcp from 10.20.30.0/24 to any port 22
sudo ufw allow 443/tcp
sudo ufw allow proto tcp from 10.20.30.0/24 to 10.20.0.10 port 9443
sudo ufw enable
sudo ufw status numbered
```

This is a configuration example for a **lab machine matching the described model**, not commands you must run to read the lesson. Before enabling a firewall on a remotely managed machine, the actual SSH source must match the policy and a recovery path must exist. Do not change the default policy on an active system without reviewing other services.

UFW supports rules by source/destination/port and has `--dry-run` for previewing. Always inspect current state: default deny does not automatically delete an existing broad allow rule. [Ubuntu Server: Firewall](https://ubuntu.com/server/docs/how-to/security/firewalls/)

In the cloud, apply the same policy table to security groups/firewalls and load balancers. When multiple allow rule sets apply together, examine the combined result; adding one narrow rule does not prove an old broad rule ceased to apply.

For the multi-host model, the firewall on the JVM host must block direct access to the backend, accepting only from the designated proxy or scraper. A good ACL on the proxy will be bypassed if callers can still reach JVM port 9090 via another path.

### IPv4 and IPv6 Must Be Evaluated Separately

`0.0.0.0` denotes all local IPv4 addresses; `::` is the IPv6 wildcard address. Whether an IPv6 listener also accepts IPv4 depends on the OS/socket configuration. Do not infer IPv6 status from a single IPv4 test.

Inspect listeners, DNS A/AAAA records, and corresponding network rules. If you only design an IPv4 management path, confirm there is no unintended IPv6 listener or published route.

## 7. Do Not Turn Forwarded Headers Into Access Permits

Behind a reverse proxy there are two distinct pieces of information:

- The peer address of the TCP connection seen by each layer.
- The address claimed by an HTTP header to be the original caller's address.

An external machine can send on its own:

```http
X-Forwarded-For: 10.20.30.25
```

This header does not make the TCP packet's source address become `10.20.30.25`. In the NGINX configuration directly receiving connections in section 5, the default ACL does not rely on that self-reported header.

If there is a load balancer in front of NGINX, NGINX may see only the load balancer's IP. In that case:

1. Identify the exact trusted proxy and the connection path to it.
2. Block direct access paths that could bypass that proxy.
3. The edge proxy must strip or overwrite headers sent by external clients.
4. Restore the caller address only from trusted proxies.
5. Re-verify the IP actually used by ACLs and logs, including when NAT is present.

The NGINX real-IP module provides `set_real_ip_from`, `real_ip_header`, and `real_ip_recursive` to configure this relationship. Never declare the entire Internet as a trusted source. Using the module also requires an NGINX build with corresponding support. [NGINX real-IP module](https://nginx.org/en/docs/http/ngx_http_realip_module.html)

On the Spring Boot side, `server.forward-headers-strategy` controls how forwarded information is handled. `NATIVE` uses the web server's mechanism; `FRAMEWORK` uses Spring Framework's support. These options do not authenticate the machine sending the headers. The lab keeps `none` because it does not need to infer address or protocol from the proxy. [Spring Boot 3.3: Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)

If the application needs to generate accurate URLs/redirects when TLS terminates at the proxy, design and test that trust chain separately. Merely enabling forwarded-header reading is not enough to protect an IP check in application code. [Spring Framework: Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)

## 8. Containers and Kubernetes: Internal Networks Have Multiple Scopes

### 8.1. Container Loopback Differs From Host Loopback

Two containers normally do not share loopback. NGINX in container A cannot use `127.0.0.1:9090` to call a JVM in container B. Use the service address/name on the container network, and the JVM listener must accept connections on an appropriate interface.

Also separate two decisions:

- Where the JVM listens **inside the container**.
- Which port Docker publishes, and on which address **of the host**.

The following mapping example is for a scenario where the JVM accepts connections on port 9090 of the container interface:

```text
127.0.0.1:9090:9090
```

It describes binding the host port to loopback; it does not require the JVM to bind to loopback inside the container. On a standard bridge network, if the JVM listens only on `127.0.0.1` inside the container, traffic routed to the container interface address will not reach that listener.

Publishing a Docker port without specifying a host address can make the port reachable externally. Do not publish the management port if only authorized containers need to call it; also inspect other containers on the same network since they can reach the service as well. [Docker: Port Publishing](https://docs.docker.com/engine/network/port-publishing/)

On Linux, Docker's forwarding path can precede standard UFW rules. Therefore, seeing UFW deny does not prove a container port is blocked. Check how Docker manages firewalls and test from another machine after publishing. [Docker: Packet Filtering and Firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)

### 8.2. Kubernetes

Do not add the management port to a public Ingress/LoadBalancer just because another internal Service exists. A ClusterIP Service does not by itself create an allowlist of pods permitted to call it.

NetworkPolicy can restrict connections between pods if the cluster's CNI plugin enforces it. Policies are additive; another broad policy can make the scope wider than intended. If both source and destination are isolated, the connection must be allowed by both the source's egress and the destination's ingress. [Kubernetes: Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

When applying policies, identify the actual source of scrapers and health probes. Do not open the whole cluster to fix a failing probe without knowing where the probe originates.

## 9. Local Hands-On Lab: Verifying Proxy and Spoofed Headers

This lab uses Linux or WSL with Java 21, Maven 3.9+, NGINX, and `curl`. Run the JVM and NGINX directly in the same network namespace—do not put one process on Windows and the other inside a separate container/WSL instance.

The goal is to observe routing and ACLs. All listeners bind to loopback and use HTTP; this lab does not yet simulate TLS, VPNs, or real-host firewalls.

### 9.1. Create the Standalone Application

Create a dedicated working directory with this structure:

```text
actuator-network-lab/
├── pom.xml
├── nginx.conf
└── src/main/
    ├── java/lab/NetworkLabApplication.java
    └── resources/application.yml
```

Contents of `pom.xml`:

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
    <groupId>lab</groupId>
    <artifactId>actuator-network-lab</artifactId>
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

Contents of `src/main/java/lab/NetworkLabApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class NetworkLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(NetworkLabApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "hello\n";
    }
}
```

Use the exact YAML configuration from section 4 as `src/main/resources/application.yml`. This project omits Spring Security to isolate network/ACL behavior; do not use the lab config as the protection policy for a real management service.

Because this is a Spring Boot program with dependencies, use Maven to compile/package rather than running `javac` on a single file:

```bash
mvn package
java -jar target/actuator-network-lab-1.0.0.jar
```

The first run needs access to the Maven repository to download dependencies. Keep the JVM running in the first terminal and wait for the application to start successfully.

### 9.2. Lab NGINX Configuration

Place the following content in `nginx.conf` at the lab root. This is a **complete configuration file for a separate lab NGINX process**, unlike the illustrative production blocks in section 5.

```nginx
pid nginx.pid;
error_log error.log;

events {
    worker_connections 128;
}

http {
    access_log access.log;

    server {
        listen 127.0.0.1:8088;
        server_name localhost;

        location = /actuator {
            return 404;
        }

        location ^~ /actuator/ {
            return 404;
        }

        location / {
            proxy_pass http://127.0.0.1:8080;
        }
    }

    server {
        listen 127.0.0.1:9099;
        server_name localhost;

        location = /actuator/health {
            allow 127.0.0.1;
            deny all;

            proxy_pass http://127.0.0.1:9090;
        }

        location / {
            return 404;
        }
    }
}
```

Open a second terminal at the lab root. Ports 8080, 9090, 8088, and 9099 must be free:

```bash
nginx -p "$PWD/" -c nginx.conf -t
nginx -p "$PWD/" -c nginx.conf -g 'daemon off;'
```

The first command validates the configuration; the second keeps NGINX in the foreground. If the system already runs another NGINX instance, use this exact lab command and do not alter the running service's config.

### 9.3. Testing With curl

In a third terminal, call the business API directly:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8080/hello
curl --noproxy '*' -sS http://127.0.0.1:8088/hello
```

Each command prints one line:

```text
hello
```

The business API still works when going through the simulated public proxy port. Next, print only HTTP status codes for easy comparison:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:9090/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8088/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  --interface 127.0.0.1 \
  http://127.0.0.1:9099/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  --interface 127.0.0.2 \
  http://127.0.0.1:9099/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  --interface 127.0.0.2 \
  -H 'X-Forwarded-For: 127.0.0.1' \
  http://127.0.0.1:9099/actuator/health
```

With the right configuration, a healthy application, and a Linux environment allowing `127.0.0.2` as a loopback source address, the five commands have expected stdout in order:

```text
200
404
200
403
403
```

Explanation:

1. Direct call to the local management listener succeeds.
2. Business proxy blocks the Actuator path.
3. Management proxy allows source `127.0.0.1`.
4. Source `127.0.0.2` is not in the single-address allowlist.
5. A header claiming to be `127.0.0.1` does not change the ACL outcome.

`127.0.0.2` is still loopback; it merely simulates a different source for the ACL. If `curl --interface` fails to bind this source, that test was not executed—do not record it as blocked by a firewall.

Try two more cases:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:9099/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:9090/actuator/info
```

Expected stdout is `404` and `200`, respectively. The `info` endpoint is in the HTTP exposure list, but the lab management proxy only forwards `health`. This is a concrete example showing that access outcome is the intersection of multiple policy layers.

Finish with Ctrl+C in the terminals running NGINX/JVM. The lab only verifies local routing and ACLs; to conclude remote access is impossible, perform the next infrastructure verification step.

## 10. Verifying Infrastructure From Allowed and Denied Sources

On the Linux application host, check listeners:

```bash
ss -lnt
```

For the lab, you should see 8080, 9090, 8088, and 9099 bound to `127.0.0.1`. Do not expect a fixed stdout table because columns, ordering, and other services depend on the host.

For a real deployment, pick at least three observation points: the application host itself, an authorized operations machine, and a machine outside the allowed scope. Use addresses/domains you manage:

```bash
curl --noproxy '*' --connect-timeout 3 --max-time 5 \
  --cacert ops-ca.pem \
  -i https://ops.example.com:9443/actuator/health
```

`ops-ca.pem` is the trusted CA that issued the certificate for the management server; if the CA is already in the OS trust store, this parameter is unnecessary. Do not use `-k` to turn a certificate error into a passing check.

| Check | Outcome to Prove |
| --- | --- |
| Operations host → valid management path | Connection/TLS succeeds; endpoint then responds according to health and app permissions |
| Host outside allowlist → management listener | Blocked at network or proxy; no management data retrieved |
| Internet → business domain with Actuator path | Not routed to the management backend |
| Remote host → backend address:9090 directly | Cannot bypass the proxy |
| Denied source adds spoofed forwarded header | Does not become a valid source |
| IPv6 path if IPv6 DNS/listener exists | Obeys the same restriction intent |
| Real health probe/scraper path | Continues operating per approved policy |

`200` on health is not guaranteed for real systems: `DOWN` or `OUT_OF_SERVICE` states commonly return `503`. When authentication exists, a test without credentials is not a complete test of an allowed source either.

### Distinguishing Outcomes Instead of Lumping All Errors Into "Secure"

| Observation | What Can Be Concluded? |
| --- | --- |
| HTTP 401 | HTTP response received from a layer requiring authentication |
| HTTP 403 | An HTTP layer denied access; logs needed to identify which layer |
| HTTP 404 | URL not served on the tested path; does not prove all other paths are blocked |
| HTTP 502/504 from proxy | Proxy had trouble with upstream; not proof of a sound blocking policy |
| Connection refused | Usually no matching listener or an active reject layer |
| Timeout | Could be drop, missing route, DNS, or outage; cross-check further |
| TLS certificate error | Failed server identity verification; do not count as success |

When `curl -w` prints `000`, that is not a server HTTP status code. Read curl's error message and exit code. There is no single fixed network error stdout across all operating systems.

In the NGINX lab, inspect `access.log` to check source addresses and statuses. When multiple proxies exist, add per-hop logs, effective configs, and firewall counters for correlation. Log only necessary fields; avoid writing credentials or full endpoint payloads into logs.

## 11. Common Deployment Mistakes and Fixes

| Mistake | Why It Misleads or Broadens Access | Fix |
| --- | --- | --- |
| Only changing management port to 9090 | A publicly open port can still be scanned and found | Choose bind address and filter network sources explicitly |
| Only protecting the management domain name | Backend still has a direct IP:port path | Block proxy-bypass paths and test from another machine |
| Seeing a private IP and assuming it is restricted enough | Many other hosts/pods may have a route to it | List allowed sources and block all others |
| Placing proxy in another container and calling localhost | Localhost belongs to the proxy's own namespace | Use the proper service network and matching listener |
| Allowing an entire NAT/VPN subnet without identity checks | Multiple users share the egress IP | Keep separate authentication/authorization |
| Trusting `X-Forwarded-For` sent by callers | Header data does not prove true source | Identify trusted proxies, sanitize headers, test spoofing |
| Adding a narrow allow while forgetting an old broad allow | Combined result may still permit all sources | Audit all effective rules |
| Testing health only from the host itself | Fails to test paths from denied sources | Test all points in the matrix |
| Probe gets blocked, so opening 9090 to all sources | Treats the symptom by breaking the boundary | Identify the probe's source and grant only needed access |
| Using CORS to "lock down" Actuator | Browser restrictions do not stop curl/network connections | Use network policies and application permissions |
| Testing only IPv4 | An IPv6 listener or DNS record may still exist | Test both address families if the system supports them |
| Changing base path while keeping old ACLs | New paths may hit a different location block | Update paths and rerun the test matrix |

Network restrictions do not disable other management channels such as JMX if separately enabled. Inventory every active channel separately; this lesson only verifies the Actuator HTTP path.

## 12. Practice Exercises

### Exercise 1: Choose Boundaries for a Single Server

One host runs the JVM and NGINX; only monitoring machines in subnet `10.20.30.0/24` need to read health. Draw the path from the monitoring machine to the JVM and label address/port at each hop.

**Self-check criteria:** JVM can bind only loopback; NGINX has a management listener on a private address; both firewall and ACL match the monitoring source; no direct remote access path to the backend remains.

### Exercise 2: Find a Proxy Bypass Path

Domain `ops.example.com` has a proper ACL, yet the JVM listens on `0.0.0.0:9090` and the cloud firewall still allows source `0.0.0.0/0`.

**Analysis:** external machines can hit the backend IP directly without going through that domain/proxy. Narrow the listener or backend network per the chosen model, then retest both the valid path and the direct path. Changing domain names does not fix the root cause.

### Exercise 3: Verify When Changing Environments

Move the JVM into its own container while NGINX still runs on the host. Which parts of the same-host configuration cannot be kept mechanically unchanged?

**Analysis:** re-evaluate loopback scope, the listener address inside the container, host port mapping, and Docker's firewall path. Test connectivity both from NGINX and from another machine; a single successful curl on the host is not enough.

### Exercise 4: Prepare Evidence Before Handover

Create a table listing caller source, target URL, path across each layer, expected result, and actual result. Include denied sources, spoofed headers, direct paths, and IPv6 if present.

**Self-check criteria:** mark as passing only when there is evidence for both paths that must work and paths that must be blocked. Record which layer blocked and the limits of the test, rather than treating any connection failure as a pass.
