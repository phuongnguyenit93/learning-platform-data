# Reverse proxies and the trust boundary of Forwarded, X-Forwarded-*

## 1. Objectives and real-world problem

In real web systems, HTTP requests rarely go straight from the browser to the Spring Boot application. They may pass through a CDN, WAF, load balancer, API gateway, or reverse proxy before reaching Tomcat and Spring Security.

For example, the browser sends an **HTTPS request to shop.example.test**, but the reverse proxy terminates TLS and forwards **HTTP to the internal application** on port 8080. Seen from the application's direct connection, the request may carry the **http** scheme, an internal host, and the proxy's IP address. Meanwhile, the real user is accessing **https** on the public host.

The **Forwarded** and **X-Forwarded-*** headers are used to pass along client-side request info, such as the original IP address, protocol, host, and port. The crucial security issue is: **HTTP headers by themselves do not prove the info inside is trustworthy**. If the application trusts values arbitrarily sent by clients, it can misidentify user addresses, generate redirects to malicious domains, or make security decisions on forged data.

After this lesson, you will be able to:

1. Explain which properties of an HTTP request a reverse proxy changes.
2. Distinguish the standard **Forwarded (RFC 7239)** header from the **X-Forwarded-*** group.
3. Read a multi-hop proxy chain without confusing the direct connection peer address with the client IP.
4. Identify the **trust boundary**: who is permitted to emit forwarded headers, and who must strip external data.
5. Understand the impact on URLs/redirects, Secure cookies, OAuth2 redirects, logging, rate limiting, and Spring Security decisions.
6. Configure **server.forward-headers-strategy** appropriately for Spring Boot MVC/Servlet applications.
7. Test real proxy flows, spoofed requests, and direct backend access paths.

## 2. What does a reverse proxy do to an HTTP request?

A **reverse proxy** is a server sitting in front of the application, receiving requests on behalf of the backend and forwarding requests to one or more internal services. It is commonly used to:

- Terminate TLS/HTTPS and manage certificates.
- Route multiple domains or paths to services.
- Load balance, health check, cache, and rate-limit traffic.
- Perform partial controls such as WAF, IP filtering, or authentication gateway duties.
- Hide the backend's network address from Internet users.

A simple topology:

~~~text
Browser                    Reverse proxy                 Spring Boot
198.51.100.24              192.0.2.10                   10.0.0.20:8080
     |                          |                               |
     | GET https://shop.example.test/profile                      |
     |---------- TLS ---------->|                               |
     |                          | GET http://10.0.0.20:8080/profile
     |                          |------------------------------>|
     |                          |  Host: backend.internal       |
     |                          |  X-Forwarded-Proto: https    |
     |                          |  X-Forwarded-Host: shop.example.test
     |                          |  X-Forwarded-For: 198.51.100.24
     |                          |                               |
     |<--------------------- HTTP response via proxy -----------|
~~~

IP addresses in the diagram use documentation-reserved ranges. The domain name **shop.example.test** is also illustrative.

Without handling forwarded headers, Servlet APIs typically reflect the **proxy → backend** connection:

| Servlet property | What backend may see | Browser's perspective |
| --- | --- | --- |
| request.getScheme() | http | https |
| request.isSecure() | false | true on browser → proxy connection |
| request.getServerName() | backend.internal | shop.example.test |
| request.getServerPort() | 8080 | 443 |
| request.getRemoteAddr() | Reverse proxy IP | Client IP observed by proxy |
| request.getRequestURL() | URL per connection into backend | Public Internet URL |

Actual values depend on how the proxy rewrites **Host**, how the connector/server is configured, and whether Spring interprets forwarded headers. The table explains why this mechanism is needed, not a guarantee that every environment returns those exact values.

### 2.1. Three easily confused addresses

- **Peer/socket IP:** The IP address of the party making the direct TCP connection to the backend. Behind a reverse proxy, this is usually the last proxy's address.
- **Forwarded client IP:** The address declared by a proxy as the sender of the request to it or into the proxy chain. This is **declared information** whose source must be verified.
- **User identity:** The post-authentication principal, such as an account or subject in an access token. An IP does not replace this identity; many users may share NAT, VPNs, or corporate networks.

You cannot infer "authenticated user" merely because an IP or X-Forwarded-For looks familiar.

## 3. Two main header families

### 3.1. Standard Forwarded header per RFC 7239

**Forwarded** is the header standardized in **RFC 7239**. Each element holds **name=value** pairs separated by semicolons; multiple hops can be represented by comma-separated elements.

~~~http
Forwarded: for=198.51.100.24;proto=https;host=shop.example.test
~~~

Key parameters:

| Parameter | Meaning |
| --- | --- |
| for | Node sending the request **to the proxy recording the info**; usually describes the client/previous hop |
| by | Request-receiving interface of the proxy, which may be an obfuscated identifier |
| host | Host received by the proxy on the incoming request |
| proto | Scheme/protocol seen by the proxy on the incoming request, usually http or https |

If multiple proxies append to the header, you may see:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=shop.example.test, for=192.0.2.10;proto=http
~~~

This example describes one element for the edge request and one element at the next hop. **proto=http** on the internal hop does not negate that the browser used HTTPS at the outermost hop. To interpret accurately, you must know how each proxy writes or preserves headers.

The RFC permits **for=unknown**, obfuscated identifiers, and IPv6 addresses inside quotes, for example:

~~~http
Forwarded: for="[2001:db8::42]";proto=https;host=shop.example.test
~~~

You cannot parse RFC 7239 correctly by taking an arbitrary string and splitting before a colon: IPv6 contains multiple colons, and quoted-string values have their own rules. In real applications, use a standards-compliant component configured properly.

### 3.2. Common X-Forwarded-* group

**X-Forwarded-*** predates RFC 7239 and remains widespread. These are multiple independent headers, with no single RFC specification applying uniformly across all variants.

| Header | Typical content | What to verify |
| --- | --- | --- |
| X-Forwarded-For | Comma-separated list of client/hop addresses | Entries before the trust boundary may have been client-supplied |
| X-Forwarded-Proto | Scheme used by the client externally, e.g. https | Easily forged if proxy does not overwrite or backend accepts direct calls |
| X-Forwarded-Host | Host of the external request | Host can be forged; requires canonical host/allowlist |
| X-Forwarded-Port | External port, e.g. 443 | Accurate only when source is trusted |
| X-Forwarded-Prefix | Public prefix when proxy rewrites paths | Not all servers/versions handle it identically |
| X-Real-IP | A custom header provided by some proxies | Not a universal standard header; must still cross the trust boundary |

Example:

~~~http
X-Forwarded-For: 198.51.100.24, 192.0.2.10
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
X-Forwarded-Port: 443
~~~

These are **assertions** from intermediate systems, not cryptographic proof that the client truly has IP 198.51.100.24 or connected over HTTPS. Browsers and HTTP clients can set many of these headers themselves before sending requests, unless a trusted network component blocks or rewrites them.

### 3.3. Are Forwarded and X-Forwarded-* completely equivalent?

No. Forwarded groups parameters per element/hop; X-Forwarded-* splits them across multiple headers, making it hard or ambiguous to correlate attributes to the same hop. Proxies and frameworks also differ in support, precedence, and interpretation.

**Operational rule:** Pick **one clear forwarded-headers contract** between proxies and backends. At the trust boundary, strip both the standard header and X-Forwarded headers from external sources, then emit only the header family the internal system actually uses. Do not rely on an unwritten precedence rule when two header sets conflict.

## 4. Where does the trust boundary sit?

A **trust boundary** is where information moves from an uncontrolled environment into an environment with clear rules and verification mechanisms. For forwarded headers, the typical boundary is a **managed edge proxy or load balancer**.

~~~text
UNTRUSTED OUTSIDE           TRUST BOUNDARY              MANAGED INSIDE
Client / Internet           Edge proxy                  App / private services
      |                         |                              |
      | Forwarded: for=fake     |                              |
      | X-Forwarded-Host: evil  |                              |
      |------------------------>|                              |
      |                         | 1. Strip external forwarded  |
      |                         | 2. Verify peer, TLS, host    |
      |                         | 3. Emit chosen headers       |
      |                         |----------------------------->|
      |                         |       Only from here onward  |
      |                         |       may app read headers   |
~~~

**A header does not automatically become trustworthy by passing through a proxy.** If the edge proxy forwards client-supplied headers verbatim, the backend still receives self-asserted client data. The edge must **strip, overwrite, or normalize** per policy; internal proxies must know which upstream sources are trusted.

### 4.1. Four conditions for using forwarded headers safely

1. **Trusted sources exist:** The backend only accepts traffic from explicitly authorized reverse proxies. Block the Internet or unauthorized internal networks from reaching the backend directly.
2. **Strip client headers at the edge:** Including **Forwarded** and all **X-Forwarded-*** headers the app/stack might interpret. Only emit info determined by the proxy.
3. **Define trusted order and hops:** With multiple proxies, know exactly which proxy adds, overwrites, or preserves each header. Configure trust lists/CIDRs accurately; never open them unconditionally to all IPs.
4. **Protect connections inside the trust zone:** Control the network between proxy and backend; use TLS/mTLS when risk warrants it. A trusted proxy cannot protect headers if the internal wire can be modified by unauthorized parties.

Without these conditions, enabling Forwarded header reading in Spring Boot **can expose the application to header spoofing**.

### 4.2. Why strip both header families?

Suppose the edge only strips X-Forwarded-For while letting clients send:

~~~http
Forwarded: for=203.0.113.250;proto=https;host=attacker.example.test
~~~

One component in the stack may read **Forwarded**, while logging or another proxy reads **X-Forwarded-***. If components interpret different sources, they can disagree on **client IP, scheme, and host**. Therefore strip/reset both families at **the point receiving untrusted traffic**, then emit only verified values.

### 4.3. The boundary is at the network, not only in Java

Code checking that a header looks valid does not prove the request actually came through the proxy. Anyone able to send requests directly to the backend can craft headers identical to the proxy's.

Production policy typically combines:

- Firewalls/security groups/network policies blocking unauthorized direct connections to backend ports.
- An Internet-facing proxy stripping client-asserted info.
- Internal hops accepting only authorized upstreams; using TLS/mTLS where appropriate.
- Spring Boot enabling its header-reading strategy only after verifying the conditions above.
- API access rights still resting on authentication and authorization, not solely on forwarded IPs.

## 5. Reading a multi-proxy X-Forwarded-For chain correctly

Consider three parties:

~~~text
Client 198.51.100.24
    |
    v
Edge proxy 192.0.2.10
    |
    v
Internal proxy 10.0.0.10
    |
    v
Application 10.0.0.20:8080
~~~

If **the edge stripped X-Forwarded-For from the client** and recorded the address it observed, and then the internal proxy appended the peer address it observed, the app might receive:

~~~http
X-Forwarded-For: 198.51.100.24, 192.0.2.10
~~~

Meanwhile the socket peer at the app is **10.0.0.10**. By common convention, X-Forwarded-For lists addresses recorded across previous hops from left to right. However, **the leftmost address is not automatically the real client IP**, because:

- The client might have sent a value at the start of the list itself.
- A proxy might append without stripping client-supplied entries.
- One or more proxies might not write the header, or might use a different header.
- NAT, CDNs, VPNs, address-hiding mechanisms, and addresses insufficient for identity verification exist.

### 5.1. Spoofing example if the edge only appends

Client intentionally sends:

~~~http
X-Forwarded-For: 203.0.113.99
~~~

If the edge appends without sanitizing first, the final header can become:

~~~http
X-Forwarded-For: 203.0.113.99, 198.51.100.24, 192.0.2.10
~~~

In this topology, **203.0.113.99** is a client-entered value with no proof of being the caller's address. An app taking the **first** element as the real IP will be fooled.

### 5.2. Analysis rules when handling multiple hops

Start from the **direct TCP peer** the backend actually sees, then rely on the trusted proxy list **defined via out-of-band configuration outside the request**:

1. Confirm the direct peer is a proxy permitted to connect to the backend. If not, do not trust the request's forwarded headers.
2. Know which contract the proxy closest to the app used to validate or preserve headers.
3. If traversing the IP list, evaluate from the **app-facing side (right)** toward the client, stepping only across hops that are genuinely trusted and properly configured.
4. Upon hitting an untrusted hop, do not treat entries further toward the client side as trustworthy evidence.
5. If the chain cannot be proven, use the observed peer IP or mark the client IP as unknown; do not guess.

These are **design principles**, not instructions to write your own `split(",")` parser for production security. Trust configuration for Tomcat, ingress, or gateways must be tested against the exact topology.

### 5.3. What if a CDN sits in front?

When a CDN sits in front of the edge, the TCP connection observed by the edge typically comes from a **CDN IP**, not the end user's IP. Taking `remote_addr` directly from the socket at the edge would then only record the CDN IP.

To restore the client IP, follow **the CDN and ingress's trusted proxy mechanism**: accept data only from the allowed upstream IP list, verify CDN-specific headers per vendor docs, sanitize external request info, and update CIDR lists when needed. Never pick a "client IP" header just because its value looks like a real IP.

## 6. X-Forwarded-Proto, Host, Port, Prefix, and security consequences

### 6.1. Protocol/scheme and Secure cookies

When the browser accesses the proxy over HTTPS while the proxy speaks HTTP to the backend, `request.getScheme()` on the backend may be **http** if the app does not know about external HTTPS.

This causes problems:

- Generated absolute links or redirects from the backend may become `http://` instead of `https://`.
- Some callback URL construction logic may use the wrong scheme.
- Application code relying on `request.isSecure()` may make wrong decisions.
- Cookie policies requiring **Secure** must be configured explicitly per browser TLS and deployment rules. Do not assume every cookie automatically gets the Secure attribute merely because X-Forwarded-Proto exists.

If the app blindly trusts **X-Forwarded-Proto: https** from a direct client, `request.isSecure()` can return **true** even though the client-to-backend connection has no TLS. Therefore **a header does not prove TLS exists**; TLS must be controlled at the edge and across a valid topology.

### 6.2. Host and host header poisoning attacks

A system may construct absolute URLs for redirects, email verification links, password resets, or OAuth2 callbacks. If the app uses a forged **X-Forwarded-Host** as the public hostname, it risks generating URLs pointing to an attacker-specified domain.

Example forged request:

~~~http
X-Forwarded-Host: attacker.example.test
X-Forwarded-Proto: https
~~~

If the server builds sensitive links using this value without checking the source and canonical host, links can point to an unwanted domain. You need to:

- Accept only **defined public hostnames or an explicit allowlist**.
- Have the edge proxy reject hosts not matching a valid virtual host.
- Prevent external clients from setting an X-Forwarded-Host that reaches and affects the backend.
- For security-critical links, prefer a **statically configured base URL** or one chosen from a valid domain set.
- Never build OAuth2 redirect URIs or password reset paths from an untrusted host.

### 6.3. X-Forwarded-Prefix

A proxy may receive **https://shop.example.test/api/orders** and forward **/orders** to the backend. In that case, X-Forwarded-Prefix can announce the **/api** prefix of the public URL.

However, not every container, Spring Framework version, or forwarded-headers strategy handles prefixes identically. You must verify specifically how **context paths, redirects, absolute URLs, and resource URLs** are built in the app; never treat a client-supplied prefix as proof of real routing.

### 6.4. How are authentication and Spring Security affected?

- **URL-based authorization:** Security filters evaluate requests against the path seen by the application. Proxy path rewrites can make matchers differ from public URLs; test paths after rewrites and prefixes.
- **OAuth2/OIDC login:** Redirect URIs and callbacks must match the allowed config on the authorization server. Wrong scheme/host/port can break login; a forged host can create redirect risks.
- **SecurityContext and sessions:** Cookies and sessions must align with domain, scheme, path, TLS termination, and cookie policies.
- **IP-based controls:** Audits, rate limits, allowlists, and fraud rules can malfunction if fed a forged XFF.
- **CSRF/CORS:** Origin, host, scheme, and browser behavior must be evaluated consistently. CORS does not verify IPs; forwarded headers do not replace CSRF protection.
- **Redirects:** Absolute links and Location responses must not contain internal hostnames or arbitrary client-injected domains.

## 7. Configuring Spring Boot 3.x behind a reverse proxy

In Spring Boot 3.x, the key property is **server.forward-headers-strategy**:

| Value | Meaning | When to use |
| --- | --- | --- |
| none | Does not ask Boot to apply a specific forwarded-headers strategy; exact default also depends on platform | When no trusted proxy exists or forwarded headers need no interpretation |
| native | Uses the embedded web server/container's native mechanism, e.g., Tomcat RemoteIpValve | When the container supports the headers you need and trusted proxies are configured |
| framework | Uses Spring Framework's mechanism, such as ForwardedHeaderFilter for Servlet or ForwardedHeaderTransformer for WebFlux | When framework-level handling capabilities suited to the app are needed |

Example when **the topology is already protected** and the proxy supplies standard headers intended for the app:

~~~properties
server.forward-headers-strategy=framework
~~~

If using Tomcat and native handling fits, you can choose:

~~~properties
server.forward-headers-strategy=native
~~~

**Do not enable either value merely because the backend needs to display the https scheme.** They **interpret** the info; they do not prove the headers came from a trusted proxy. On some cloud platforms, Boot may auto-select native; check the actual runtime value in deployment rather than guessing the default.

### 7.1. What does ForwardedHeaderFilter do?

In the **Spring MVC/Servlet** stack, ForwardedHeaderFilter can adjust the request view based on received headers, so downstream code sees the corresponding scheme, host, port, request URL, or remote address, and redirects generate the right external URLs. It also has a **removeOnly** mode to strip forwarded headers **without using their values**.

**removeOnly is not a header validity verifier**. It is an option to discard metadata when the app does not want to use it. If the app needs to read forwarded headers to build URLs, the network trust boundary must be established first.

In **WebFlux**, the corresponding mechanism is typically ForwardedHeaderTransformer; do not carry HttpSecurity, servlet filters, or ThreadLocal assumptions into the reactive stack.

### 7.2. When using native in Tomcat

Tomcat can use **RemoteIpValve** to interpret addresses and protocols from proxies. With Spring Boot, common properties include **server.tomcat.remoteip.remote-ip-header**, **server.tomcat.remoteip.protocol-header**, and **server.tomcat.remoteip.internal-proxies**.

The key lesson here is that **internal-proxies is a trust configuration, not a list taken from the request**. Set the exact range of real proxies in your system and test behavior when requests arrive from outside that range. Never set an empty trust list that trusts every proxy in production; Spring Boot docs also warn against that setup.

### 7.3. Do not process twice

Do not configure multiple forwarded-header processors simultaneously across proxy, Tomcat, and Spring in a way that applies the same metadata twice or uses conflicting precedence. Choose one clear pipeline, know which layer normalizes host/scheme/remote IP, and verify results with real requests through the edge.

## 8. At the boundary example: intentional proxy configuration

The following NGINX snippet **only illustrates the location/proxy headers portion** inside a TLS virtual host already configured with a certificate, valid hostname, and serving only **shop.example.test**. It is not a complete NGINX file:

~~~nginx
location / {
    proxy_pass http://127.0.0.1:8080;

    proxy_set_header Host shop.example.test;
    proxy_set_header Forwarded "";

    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host shop.example.test;
    proxy_set_header X-Forwarded-Port 443;
}
~~~

Understand each line:

1. **Forwarded ""** does not forward any client-sent Forwarded header.
2. **X-Forwarded-For $remote_addr** replaces whatever the client sent with the peer IP **directly observed by NGINX**; this example is only accurate when NGINX is truly the client-facing edge, without an un-restored CDN in front.
3. **X-Forwarded-Proto https** reflects the TLS virtual host of the example, rather than taking a random value from client headers.
4. **Fixed Host and X-Forwarded-Host** matching the configured public domain avoids using an un-allowlisted Host to construct links.
5. The backend listens only on loopback **127.0.0.1:8080** in this single-machine example. Across multiple machines or containers, equivalent firewall/network policies are required to block direct bypasses.

This is not a copy-paste config for every topology. If a CDN sits in front, client IP must be restored via a mechanism **trusting only CDN IPs** at the edge; if internal proxies exist, specify clearly which hop appends XFF and how the browser's scheme is preserved. In multi-hop architectures, do not overwrite **X-Forwarded-Proto** with **http** at an internal hop and lose the client-side HTTPS scheme.

### 8.1. Why not append everywhere?

A common NGINX config uses **$proxy_add_x_forwarded_for**, meaning it takes the existing X-Forwarded-For value and appends the peer IP. This is useful **after a trusted upstream has already sanitized the header**, but if used directly at the edge on unsanitized input, client-spoofed entries remain in the list.

Distinguish **append** and **reset** by each proxy's role. Do not apply one config template to every hop without analyzing the trust boundary.

## 9. Spring Boot practice: observe requests before/after header processing

This example is for an **isolated local environment** to see how requests change. Do not expose an endpoint returning network/header info to the Internet in production.

**Requirements:** A Spring Boot 3.x project using Java 17+ and Gradle Wrapper, with the following dependencies in build.gradle (Groovy DSL); the Spring Boot plugin and rest of the project are already created:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Create **src/main/java/com/example/forwardeddemo/ForwardedDemoApplication.java** with complete content:

~~~java
package com.example.forwardeddemo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@SpringBootApplication
public class ForwardedDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ForwardedDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/probe").permitAll()
                .anyRequest().denyAll()
            )
            .build();
    }
}

@RestController
class ProbeController {

    @GetMapping("/probe")
    Map<String, Object> probe(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();

        result.put("scheme", request.getScheme());
        result.put("secure", request.isSecure());
        result.put("serverName", request.getServerName());
        result.put("serverPort", request.getServerPort());
        result.put("requestURL", request.getRequestURL().toString());
        result.put("remoteAddr", request.getRemoteAddr());

        result.put("rawForwarded", request.getHeader("Forwarded"));
        result.put("rawXForwardedFor", request.getHeader("X-Forwarded-For"));
        return result;
    }
}
~~~

**Structure explanation:** Public class matching the filename, with main launching Spring Boot. Package-private class **ProbeController** is in the same package so it gets component-scanned. Spring MVC injects HttpServletRequest and Jackson converts the Map to JSON. The **SecurityFilterChain** bean permits only GET /probe for easy testing; other endpoints are denyAll. This is an observation endpoint for localhost, not a business API or production security design.

### 9.1. Run 1: without processing forwarded headers

In **src/main/resources/application.properties**, set:

~~~properties
server.forward-headers-strategy=none
server.address=127.0.0.1
~~~

Run with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell you can use **.\gradlew.bat bootRun**. From your local machine, send test requests:

~~~bash
curl -i http://127.0.0.1:8080/probe
curl -i -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: attacker.example.test" -H "X-Forwarded-For: 198.51.100.77" http://127.0.0.1:8080/probe
~~~

**What to observe:** With the none strategy and a direct HTTP connection, Servlet properties usually report **http**, **secure=false**, **serverName=127.0.0.1**, and remoteAddr matching the local socket. Raw headers can still be read via `request.getHeader()`, because **none does not sanitize all headers for the app**. Never use those raw headers to make IP allowlist decisions.

### 9.2. Run 2: illustrating the risk if FRAMEWORK is enabled in the wrong place

Change only the following property in application.properties and restart:

~~~properties
server.forward-headers-strategy=framework
server.address=127.0.0.1
~~~

Resend the request with self-asserted X-Forwarded-Proto, X-Forwarded-Host, and X-Forwarded-For as above. **Several JSON fields may change** to the spoofed metadata (scheme, host, URL, and possibly remote address), because ForwardedHeaderFilter is interpreting forwarded headers. In Framework mode, the original headers may be hidden from downstream code because the filter consumed and removed them from the request.

**This experiment demonstrates the danger of trusting headers on a direct path**—run only on localhost. In real systems, you must **block direct paths** from untrusted sources and force requests through a header-sanitizing proxy before using framework/native mode.

Do not use this experiment's output as proof that a real client connected over HTTPS. Fields influenced by headers **do not change the TLS state of the real connection**.

### 9.3. Verification table for a reverse proxy deployment

| Test flow | Condition to satisfy |
| --- | --- |
| Browser accesses HTTPS on public host | App builds links and redirects with the exact allowed public scheme/host |
| Client sends forged Forwarded at edge | Edge strips it; app is unaffected by client-asserted values |
| Client sends forged X-Forwarded-* at edge | Edge resets them; only proxy-controlled values are used |
| Client tries calling backend directly | Network blocks it, or backend distrusts headers and rejects per policy |
| Two internal proxies present | XFF is built accurately from trusted hops; scheme/host stay consistent |
| Adding a CDN in front | Client IP resolved via trusted upstream config, not blindly taking first XFF |
| Sending Host outside allowlist | Proxy rejects or canonicalizes; never builds URLs to foreign domains |
| Testing OAuth2 callback/login | Redirect URI has exact registered host, scheme, port, and path |
| Accessing via /api prefix | URLs, redirects, and Spring Security request matchers match real topology paths |
| API requiring CSRF/session | Cookies and CSRF policy operate properly across TLS termination |
| IP-based audit/rate limit | IP derived from trusted chain, impossible to spoof arbitrarily via request headers |

You must test **through the real edge/proxy path**. MockMvc or a local request with manually attached headers only tests header-reading mechanics; it **does not verify** that firewalls, CDNs, ingress, or proxy chains are sanitizing headers properly.

## 10. Common configuration mistakes

### Mistake 1: Treating the first element of X-Forwarded-For as the guaranteed IP

That can be a client-supplied value. A trust boundary, a proxy chain with a contract, and topology-appropriate parsing are required. Never use raw header strings as identity.

### Mistake 2: Enabling framework/native while the backend is open directly to the Internet

This is where header spoofing easily arises: clients send forged X-Forwarded-Proto or Host and the app treats them as truth. The primary fix lies in **network and proxy controls**, not Java alone.

### Mistake 3: Stripping only X-Forwarded-For while forgetting Forwarded or X-Forwarded-Host

Different libraries may read different headers. Conflicting data can affect logging, redirects, security links, or access control. Strip all headers outside the trust boundary, then regenerate one consistent header family.

### Mistake 4: Thinking HTTPS at the proxy means HTTPS to the backend

TLS termination at the proxy means the **browser → proxy** hop uses HTTPS; the **proxy → backend** hop may use HTTP or HTTPS. Evaluate internal path protection and separate it from the scheme the browser saw.

### Mistake 5: Using unverified X-Forwarded-Host to generate reset-password URLs

If the host is client-controlled, the server can issue links pointing to foreign domains. Canonicalize/allowlist hosts at the edge and prefer configured base URLs for security-sensitive links.

### Mistake 6: Using IP as the primary authentication method

IPs can belong to NAT, mobile networks, VPNs, CDNs, or forged headers. IP-based policies can serve as an extra layer when the source is verified, but do not replace user and resource authentication/authorization.

### Mistake 7: Trusting the entire internal network range as trusted proxies

A private network can host many services or unauthorized workloads. Trust only explicitly permitted ingress/load balancers, enforce proper network policies, and update the list as deployments change.

### Mistake 8: Misunderstanding URL rewrites and context paths

A proxy exposing `/api` while the backend receives `/` can break login redirects, cookie paths, or request matchers. Verify X-Forwarded-Prefix for your framework version and active processor.

### Mistake 9: Reading raw forwarded headers in audits after Framework normalized the request

Downstream code may no longer see raw headers once the filter processes them. Design appropriate observability to record **trusted peer IP, normalized client IP, and determination basis**, while minimizing sensitive data collection.

### Mistake 10: Fixing redirect bugs by disabling security checks

For example, OAuth2 login callback has the wrong scheme, so someone disables CSRF, skips redirect URI verification, or opens broad permitAll. Such changes fail to fix the root cause—**trust boundary / forwarded scheme-host**—and can introduce new vulnerabilities.

## 11. How to think when designing reverse proxies and Spring Security

Split the questions into three layers:

**Connection layer:** Which proxies does the request cross? Who is the direct peer? Which hops have TLS? Can the backend be called directly?

**Metadata layer:** Who emits Forwarded/X-Forwarded-*? Which headers are stripped at the edge? Which proxies may append? Which host/scheme/port/prefix are canonical? Which addresses are observed vs merely declared?

**Application layer:** Does Spring Boot interpret headers via native or framework? Which URL and scheme does Spring Security use for authorization and redirects/cookies? Do business services accurately verify roles, resource ownership, and tokens?

Do not invert the order by enabling `server.forward-headers-strategy` first and figuring out which proxies are trusted later. **The ability to read metadata** and **the trustworthiness of metadata** are two separate concerns.

## 12. Self-check questions

**Question 1.** The backend receives a TCP connection from 10.0.0.10, with X-Forwarded-For `203.0.113.99, 198.51.100.24, 192.0.2.10`. Is 203.0.113.99 guaranteed to be the real client?

**Answer:** No. If the edge only appends, 203.0.113.99 could have been entered by the client. You must know the trusted proxies and how they reset/append headers.

**Question 2.** Spring Boot is configured with `framework` and receives `X-Forwarded-Proto: https`. Does that verify the client established TLS?

**Answer:** No. Framework interprets the header; TLS must be confirmed at the edge and within a trusted topology. If the backend is reachable directly, clients can forge this header.

**Question 3.** Why strip both Forwarded and X-Forwarded-* at the edge?

**Answer:** Components may read different header families; to avoid using client-asserted info and avoid conflicts, the edge must reset both and emit trusted metadata under a unified contract.

**Question 4.** The backend generates a password reset link based on a client-chosen X-Forwarded-Host. What is the risk?

**Answer:** Host header poisoning—links get generated to unintended domains. Hosts must be canonicalized and allowlisted, or a fixed base URL must be used.

**Question 5.** Behind a CDN, the edge only uses socket `remote_addr` to identify user IPs. What will the result likely be?

**Answer:** The CDN's IP. To obtain the client IP, process CDN info via a trusted upstream list, verify ingress config, and sanitize headers at the boundary.

**Question 6.** If the app does not use forwarded headers, do they still need to be stripped?

**Answer:** You still need to review the entire stack and components that might consume them. You can strip headers at the edge and use `removeOnly` or disable interpretation in the app. Untrusted headers should not accidentally influence other libraries.

**Question 7.** Why does testing with curl adding X-Forwarded-For on localhost not prove the production system is safe?

**Answer:** It only demonstrates how the framework parses a header string over a simulated connection. The real trust boundary lies in firewalls, CDNs, load balancers, proxy rewrites, and backend access paths.

## 13. Official documentation

- IETF RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239.html
- Spring Framework — Forwarded Headers / ForwardedHeaderFilter: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot 3.3 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
