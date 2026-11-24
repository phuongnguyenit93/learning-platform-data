# Strict-Transport-Security, HTTPS, and Conditions for Enabling HSTS in Spring Security Servlet

## 1. HTTPS protects the connection; HSTS protects choosing HTTPS

**HTTPS** uses TLS to encrypt and authenticate the connection between the browser and the server. If a user accesses the exact HTTPS URL and certificate verification succeeds, a man-in-the-middle cannot arbitrarily read or modify application content over that connection. However, HTTPS by itself does not force the browser to always choose HTTPS on subsequent visits: users may type an address without a scheme, open a link starting with `http://`, or be redirected to HTTP before the server returns instructions to switch to HTTPS.

**HTTP Strict Transport Security (HSTS)** is a mechanism for a website to inform the browser: *for a specified period, all subsequent connections to this domain must use HTTPS*. The server includes the policy in the **Strict-Transport-Security** HTTP response header over a valid HTTPS connection. Supporting browsers store that policy and automatically upgrade future HTTP visits before sending a request over the network.

HSTS helps reduce the risk of HTTPS-to-HTTP downgrades and certain redirect interception/modification attacks (SSL stripping). It **does not replace** valid TLS certificates, HTTP-to-HTTPS redirects, secure TLS configuration, `Secure` cookies, CSRF protection, authentication, or authorization. In a Spring Security **Servlet** (Spring MVC) application, HSTS belongs to the security response headers that Spring Security can generate automatically.

Lesson objectives:

- Understand how browsers store and apply HSTS policies.
- Correctly interpret the **max-age**, **includeSubDomains**, and **preload** directives.
- Know when Spring Security sends the header, especially when TLS terminates at a reverse proxy.
- Configure and test HSTS for a Spring Boot 3.x / Spring Security 6.x application.
- Evaluate infrastructure prerequisites before enabling long-lived HSTS, including rollback planning.

## 2. How does the Strict-Transport-Security header work?

An HTTPS response may carry the header:

~~~http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Type: text/html; charset=UTF-8
~~~

When received over a valid TLS connection, an HSTS-capable browser remembers the policy for the response's **hostname**. For example, visiting `https://app.example.com` for the first time and receiving the header above causes the browser to remember that `app.example.com` and its subdomains must be accessed over HTTPS for roughly one year from when the policy is updated.

Simplified flow:

~~~text
First visit (no HSTS policy in browser yet):
User -> http://app.example.com
     -> server returns 301/308 to https://app.example.com
     -> TLS handshake, certificate verification
     <- HTTPS response with Strict-Transport-Security
     -> browser stores policy for app.example.com

Subsequent visit (policy still valid):
User -> http://app.example.com
     -> browser automatically upgrades to https://app.example.com
     -> initiates HTTPS connection only; does not send initial HTTP request
~~~

Distinguish two actions:

1. **HTTP → HTTPS redirect** is an instruction from the server (such as 301 or 308). To receive the redirect, the client typically had to connect over HTTP at least once if no HSTS policy was cached.
2. **HSTS upgrade** is performed by the browser as soon as it resolves the URL before sending the request. No new redirect from the server is needed on that visit.

**First-visit limitation:** if the browser has never learned the domain's HSTS policy and the domain is not in the browser's preload list, an initial HTTP request can still be intercepted before the browser receives a valid HTTPS response. Thus, learned HSTS protects subsequent visits; preload is an optional mechanism that can narrow this gap for browsers carrying the list.

Browsers only accept HSTS policies sent over **trusted HTTPS**. Headers appearing on plain HTTP responses are ignored for creating/updating HSTS policies. An HTTPS response with certificate errors is likewise not a trusted channel for activating or removing a policy. Merely emitting the header over HTTP does not make the page secure.

## 3. Explaining the directives accurately

Typical syntax:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

| Directive | Effect | Considerations |
| --- | --- | --- |
| **max-age=seconds** | Maximum time, in **seconds**, that the browser must treat the hostname as an HSTS host from the time a valid policy is received. | `max-age=300` is 5 minutes; `86400` is 1 day; `31536000` is roughly 1 year. |
| **includeSubDomains** | Applies to both the specified hostname and **all subdomains** beneath that hostname. | Enable only after inventorying and ensuring HTTPS works for subdomains in scope. |
| **preload** | Signal used for enrolling in the HSTS preload list of participating browsers. | Add only when the entire infrastructure meets preload requirements and the organization intentionally wants to register; adding this keyword **does not automatically** put the domain on the list. |

Details to remember:

- **max-age=0** requests deleting the learned HSTS policy for the hostname sending the header, **only when the browser receives it over valid HTTPS**. It does not automatically delete separate HSTS policies set individually by subdomains, nor does it mean immediate removal of a domain currently in the preload list.
- When receiving a valid header again with a positive `max-age`, the browser **refreshes the expiration time**. `max-age` is not seconds elapsed since website deployment.
- The policy applies per **hostname**, not scoped to an endpoint, `/login`, `/admin`, or an individual `SecurityFilterChain`. If the header comes from `app.example.com`, it does not automatically apply to the parent domain `example.com` or sibling domain `api.example.com`.
- A header with `includeSubDomains` on **example.com** covers `app.example.com`, `api.example.com`, and deeper subdomains. A header with `includeSubDomains` on **app.example.com** covers hosts underneath `app.example.com`, not `api.example.com`.
- HSTS is not designed as a per-port or per-path policy. Browsers rewrite HTTP URLs to HTTPS per HSTS rules; default port 80 typically switches to 443, while non-standard ports may be preserved. Do not use HSTS as an arbitrary port-switching workaround.
- HSTS is primarily meant for DNS domain names; browsers do not rely on HSTS on literal IP addresses the way they do for normal hostnames. For localhost or dev environments, do not take browser-specific behavior as proof of production domain policy.
- Some non-browser HTTP clients do not store or apply HSTS. Client, reverse proxy, and API configurations must still enforce HTTPS independently of HSTS.

If a browser has stored HSTS and the server later has an invalid certificate or stops serving HTTPS, the browser may **prevent users from bypassing the certificate error**. This is a security benefit, but also an operational risk if HSTS is enabled before infrastructure is ready.

## 4. When does Spring Security send HSTS?

In Spring Security 6.x on Servlet, while default security headers remain active, Spring Security uses **HstsHeaderWriter** to output `Strict-Transport-Security` on requests recognized as **secure** (HTTPS). Spring Security's common default policy is:

~~~http
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
~~~

That value corresponds to roughly one year and includes subdomains; whitespace in the formatting does not change meaning. No extra configuration is needed just to get the default header if default headers are enabled, the request is actually recognized as secure, and the response passes through the security filter chain containing the header writer.

Common points of confusion:

**The HSTS response header does not enable TLS on the server.** The application only emits the header over HTTPS when Spring Security knows the request is secure. If the application accepts HTTP without a separate redirect, clients can still call HTTP when no HSTS policy is cached.

**The HSTS response header is not an HTTPS redirect.** To force all HTTP requests to HTTPS, configure a redirect at the reverse proxy/load balancer or require a secure channel in Spring Security. Choose where to enforce it according to your architecture.

**The HSTS response header must be applied consistently across the hostname.** If multiple `SecurityFilterChain` beans, other servlet filters, or a reverse proxy generate responses before reaching Spring Security, verify which endpoints actually return the header. One hostname can have login pages, static pages, 4xx/5xx errors, redirects, and APIs served by different components.

**HSTS default `includeSubDomains` does not mean you have verified every subdomain.** Therefore, the default policy may technically be stronger than your infrastructure readiness, especially when the same domain hosts other apps or tenants. Make an explicit policy decision for the deployment domain before broadcasting the header widely.

## 5. Spring Boot 3.x / Spring Security 6.x example: cautious configuration

The example below uses Java 17+ with Spring Boot Web and Spring Security dependencies. The application exposes `GET /status` and configures a **short `max-age` of 300 seconds without `includeSubDomains`** for testing. Create `src/main/java/demo/hsts/HstsDemoApplication.java`:

~~~java
package demo.hsts;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class HstsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HstsDemoApplication.class, args);
    }

    @GetMapping(value = "/status", produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }
}

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/status").permitAll()
            .anyRequest().authenticated()
        );

        http.headers(headers -> headers
            .httpStrictTransportSecurity(hsts -> hsts
                .maxAgeInSeconds(300)
                .includeSubDomains(false)
            )
        );

        return http.build();
    }
}
~~~

Meaning:

- **@SpringBootApplication** starts the application; the controller handles `GET /status` and returns JSON. **SecurityConfig** sits in the same package so component scanning discovers it.
- **SecurityFilterChain** governs requests to the application; the example opens only `/status` to verify headers and does not imply all real application endpoints should be `permitAll`.
- **http.headers(...httpStrictTransportSecurity(...))** replaces the default HSTS configuration values with 300 seconds and disables `includeSubDomains`. Spring Security still writes the header only for requests deemed HTTPS.
- This example **does not configure a TLS listener or HTTP redirect**. To run over real HTTPS, TLS must be configured on the application or a reverse proxy. Do not call `http://localhost:8080/status`, see a missing header, and conclude HSTS configuration is broken.

After evaluation and once infrastructure prerequisites are met, you can transition to a longer policy:

~~~java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .maxAgeInSeconds(31536000)
        .includeSubDomains(true)
    )
);
~~~

This is a **replacement snippet for the HSTS configuration section above**, not a standalone Java program. Do not raise `max-age` to one year and enable `includeSubDomains` simply because requests to one endpoint passed unit tests.

When you do not want to customize HSTS, you can omit the **http.headers(...)** section; Spring Security uses the default header policy unless disabled or replaced. Do not call `headers.disable()` just to troubleshoot an HTTPS issue: that disables many other security headers, not just HSTS.

## 6. Testing Spring Security behavior at the Servlet layer

With `spring-boot-starter-test`, a MockMvc test confirms that the policy is only written on HTTPS requests and does not appear on HTTP. Create `src/test/java/demo/hsts/HstsHeaderTest.java`:

~~~java
package demo.hsts;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HstsHeaderTest {

    @Autowired
    MockMvc mvc;

    @Test
    void httpsResponseContainsConfiguredHsts() throws Exception {
        mvc.perform(get("/status").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=300")));
    }

    @Test
    void plainHttpResponseDoesNotSetHsts() throws Exception {
        mvc.perform(get("/status").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }
}
~~~

**MockMvc.secure(true)** simulates a Servlet request marked secure; it checks how Spring Security builds the response header, **does not perform a real TLS handshake**, and does not prove a browser stored the policy. With the sample code above, `GET /status` is `permitAll`, so both requests return status 200; only the HTTPS response includes HSTS. In real environments, also assert whether `includeSubDomains` is present or absent according to your chosen policy.

To verify externally, run against a hostname with HTTPS and a valid certificate and inspect the responses:

~~~bash
curl -sSI https://app.example.com/status
curl -sSI http://app.example.com/status
~~~

The first command should show `Strict-Transport-Security` matching the deployed policy; the second command in production typically returns **301 or 308 to HTTPS**. An HSTS header on a plain HTTP response, even if present, is ignored by browsers for updating HSTS policy.

Note that **curl does not simulate full browser HSTS state by default**. To observe URL upgrading, use a real browser with a test hostname, checking Developer Tools → Network/Security and connection status after receiving a valid header. Avoid using production domains with long `max-age` for experiments because browsers may retain the policy long after you remove the server configuration.

## 7. Deploying behind a reverse proxy / load balancer with TLS termination

In many Spring Boot deployments, TLS terminates at Nginx, ingress, an API gateway, or a load balancer:

~~~text
Browser --HTTPS/TLS--> Reverse proxy --internal HTTP--> Spring Boot
                       TLS certificate here             Servlet request
~~~

At the network edge, the client genuinely used HTTPS; however, if the proxy calls the backend over HTTP, the Servlet container may see **request.isSecure() = false**. Because `HstsHeaderWriter` only emits the header on secure requests, Spring Security may **omit HSTS even though the browser is accessing HTTPS**.

Two common patterns:

### Approach A — emit HSTS at the HTTPS edge

The reverse proxy knows directly whether the client connection is HTTPS. It sets HSTS directly on outgoing HTTPS responses while also handling HTTP-to-HTTPS redirects. This pattern often fits when multiple apps share an ingress and follow a uniform hostname policy.

Checks required: the header must appear on appropriate HTTPS responses, including redirects and key error responses; the HTTP listener must not advertise a misleading HSTS policy; edge policies must not duplicate or conflict with headers emitted by the app itself. Reverse proxies vary in syntax for emitting headers across all status codes.

### Approach B — let Spring Security emit HSTS using trusted proxy information

The proxy can forward original scheme information via **Forwarded** or **X-Forwarded-Proto**. Spring Boot supports processing forwarded headers via an appropriate framework or native strategy. A common setting:

~~~properties
server.forward-headers-strategy=framework
~~~

When deploying this approach, the proxy/load balancer **must strip or overwrite any `Forwarded`/`X-Forwarded-*` headers sent by external clients**, then set headers reflecting the actual connection. The backend must restrict access paths so clients cannot directly spoof those headers. Failing to protect this trust boundary can cause the application to misidentify request origins and introduce bugs in redirects, URL generation, cookies, or security controls.

Test by sending real HTTPS requests through the exact ingress path and checking whether client responses include HSTS; also verify the container receives the proper scheme. Do not assume `request.isSecure()` automatically becomes `true` just because a proxy attached `X-Forwarded-Proto` if the container/framework is not configured to process it.

**Operational rule:** pick a single policy owner per hostname (proxy or application) and verify all response paths. Multiple layers appending inconsistent HSTS values can be hard to diagnose; never rely on duplicate header ordering to determine policy.

## 8. HTTPS redirect, requiring a secure channel, and HSTS are three related concerns

| Mechanism | Where is it enforced? | Effect |
| --- | --- | --- |
| TLS/certificate | Server or TLS-terminating proxy | Encrypts the connection and proves server identity. |
| HTTP → HTTPS redirect | Proxy/server or Spring Security channel rules | Guides clients from HTTP URLs to HTTPS after the client sends a request. |
| HSTS | Browser after receiving a valid HTTPS header | Automatically upgrades visits to the HSTS hostname without starting with HTTP. |

One way to require a secure channel in Spring Security Servlet 6.x is:

~~~java
http.requiresChannel(channels -> channels
    .anyRequest().requiresSecure()
);
~~~

This is an additional configuration snippet in `SecurityFilterChain`, not a substitute for server TLS or HSTS. When receiving an HTTP request, Spring Security can redirect to HTTPS according to the configured channel rules. However, if a proxy terminates TLS and the backend still sees requests as HTTP, applying `requiresSecure()` without proper forwarded-header handling can cause a **redirect loop**.

For systems terminating TLS at ingress, it is usually better to let ingress handle HTTPS redirects while the application focuses on security headers, authentication, and authorization. Whichever option you choose, verify both URLs externally:

- `http://app.example.com/...` redirects to `https://app.example.com/...` with the right host/path and HTTP status.
- `https://app.example.com/...` serves a trusted certificate, proper TLS, and the desired HSTS policy.

An HTTP redirect, even 301/308, still does not protect the first visit from an active path attacker; learned HSTS or preload is what closes that risk in the browser.

## 9. Conditions to evaluate before enabling HSTS in production

### 9.1. HTTPS is genuinely ready

All HTTPS requests to the hostname must be served reliably with a valid certificate, complete intermediate chain, matching SANs, reliable automated renewal, supported TLS versions/ciphers, and no error paths forcing users back to HTTP. Verify login pages, static assets, APIs, file downloads, error pages, and redirect URLs.

If HTTPS becomes unavailable after browsers cache HSTS, users can be locked out of the site until certificates/TLS are fixed or the policy expires. You cannot rely on returning an HTTP response or sending `max-age=0` over HTTP to rescue browsers holding the policy.

### 9.2. All hostnames under `includeSubDomains` support HTTPS

On `example.com`, enabling `includeSubDomains` affects **every** subdomain, including assets outside this application's repository: `api.example.com`, mail/webmail, support pages, legacy hosts, browser-accessed internal domains, staging domains, or services managed by other teams. You must inventory DNS and owners of each related host and verify TLS/certificates for every service accessed via browser.

In particular, HSTS on `app.example.com` does not mask broken HTTPS on `api.example.com` when they are sibling domains; the policy applies only from the emitting host downward. Do not treat a wildcard certificate as proof that every service has sound HTTPS deployment.

### 9.3. Redirects and all proxy paths are consistent

Verify that HTTP listeners emit proper redirects; HTTPS listeners emit proper headers; CDNs, ingresses, web servers, applications, and caches do not strip headers on protected responses. With multiple hosts, preview environments, or shared domains, do not apply a broad domain-wide HSTS policy by default unless you control all subdomains.

### 9.4. TLS renewal and recovery are operationally sound

Have certificate expiration alerts, external TLS monitoring, and the ability to fix DNS/certs/ingress during incidents. When using `includeSubDomains`, a legacy HTTP-only host may become unreachable from browsers that learned the policy; prepare a migration path before enabling.

### 9.5. Policy matches the environment's risk level

For development environments using test hosts or unstable HTTPS services, do not immediately apply multi-year `max-age` or preload. For stable production, you can start with a short value and ramp up after verification. Example plan:

| Phase | Illustrative header | Purpose |
| --- | --- | --- |
| Trial | `max-age=300` | Verify the policy reaches browsers over HTTPS without breaking flows. |
| Observation | `max-age=86400` | Maintain 1 day, monitoring certificates, redirect errors, and clients. |
| Steady state | `max-age=31536000` | Maintain roughly 1 year once infrastructure and recovery procedures are verified. |
| Expanded scope | Add `includeSubDomains` after inventory | Expand scope only when all affected subdomains are ready. |
| Preload (optional) | `includeSubDomains` and `preload`, meeting registration policy | Requires long-term domain commitment and a complex removal process. |

These milestones are an **illustrative rollout plan**, not a mandatory timeline or security guarantee. The `max-age` length and coverage scope must be approved by domain and infrastructure owners based on testing evidence.

## 10. Preload: benefits and maintenance costs

Preload places a domain's HSTS policy into a pre-distributed list compiled into participating browsers, allowing browsers to upgrade connections even when a user has **never** visited the site before. This capability helps narrow the "first-visit" risk.

The following example header signals preload intent:

~~~http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

However, **adding `preload` to the header does not mean the domain is preloaded**. Enrollment requires meeting the HSTS preload ecosystem criteria (valid HTTPS, redirects, minimum `max-age`, `includeSubDomains`, header syntax, and current conditions), submitting the registration, and waiting for browser list updates. Exact criteria may evolve; before submitting, read the current requirements at `https://hstspreload.org` and proceed only when the organization manages the entire domain, subdomains, and certificate lifecycle.

Consequences:

- The domain and all subdomains are forced onto HTTPS by preload-supporting browsers, even for first-time visitors. A legacy HTTP subdomain may stop working.
- Removing a domain from preload requires going through a removal process and waiting for new browser releases to ship the updated list; changing the header does not take effect immediately.
- If HTTPS/certificates break, preloaded clients may have no bypass option. Treat preload as a cross-service, long-lived architectural commitment.

Preload is not mandatory just to use standard HSTS. A site can protect repeat visits using a positive `max-age` without registering for preload.

## 11. Removing or reducing HSTS when changing policy

If not preloaded, and you control HTTPS on the hostname, you can return:

~~~http
Strict-Transport-Security: max-age=0
~~~

over **valid HTTPS** to instruct browsers to clear the HSTS policy for that specific hostname. To keep the policy but shorten its lifetime, emit a smaller `max-age` over HTTPS; to drop `includeSubDomains`, emit a new policy without that directive, then evaluate any child hosts carrying their own HSTS policies.

Practical limitations of removal:

1. Browsers only accept the update directive when the HTTPS connection is verified successfully; if the certificate is broken, **fix TLS first**.
2. Browsers that do not revisit the hostname never receive the new policy; old state persists until expiration or update.
3. `max-age=0` on `example.com` does not automatically clear an HSTS entry separately sent by `api.example.com`.
4. Preloaded domains additionally require going through preload removal and waiting for affected browsers to update.

Do not treat changing `max-age=0` in configuration as an instant rollback switch for all clients. Keep HTTPS serving paths operational during transitions.

## 12. Common pitfalls

**Pitfall 1 — HTTPS works, yet HSTS is missing.** Check whether requests pass through Spring Security `HeaderWriterFilter`, whether `headers()` was disabled, whether `request.isSecure()` is accurate behind a proxy, or whether HSTS is actually emitted at the edge instead of the backend. Inspect the final response on the client side, not just on localhost.

**Pitfall 2 — Adding `Strict-Transport-Security` over HTTP.** Browsers ignore policies received over HTTP connections. Start with a proper TLS certificate, redirect HTTP to HTTPS, and use only valid HTTPS responses to establish the policy.

**Pitfall 3 — Enabling `includeSubDomains` immediately on the apex domain.** This can lock out child sites that do not support TLS. Inventory all hostnames/subdomains before widening scope, including systems operated by other teams.

**Pitfall 4 — Assuming HSTS is equivalent to a redirect.** HSTS does not provision certificates, open port 443, or rewrite server-side URLs. First-time visits without a cached policy still need a safe HTTPS redirect at the proxy/app.

**Pitfall 5 — Enabling `requiresSecure()` behind a proxy without handling forwarded headers.** The backend thinks every request is HTTP and loops redirecting to HTTPS. Establish the trust boundary and configure the forwarded strategy properly; test the real path from a browser.

**Pitfall 6 — Evaluating with MockMvc and concluding production is safe.** MockMvc only verifies header generation on simulated requests. Certificates, 301/308 redirects, proxies, CDNs, sibling hosts, and real browser behavior must be verified outside the app.

**Pitfall 7 — Treating preload as a configuration checkbox.** The `preload` header directive does not auto-enroll; once enrolled, removal is slow and requires control over every subdomain. Submit only when long-term requirements are met.

**Pitfall 8 — Error responses lack HSTS or have conflicting headers.** Responses may be generated at a CDN/gateway before Spring Security runs; inspect 3xx/4xx/5xx over HTTPS. Designate one policy owner per hostname and monitor real responses.

**Pitfall 9 — Assuming HSTS solves all web security issues.** HSTS does not stop XSS, CSRF, SQL injection, leaked application tokens, or mixed content loaded from a hostname outside HSTS scope. Continue applying CSP, `Secure`/`HttpOnly`/`SameSite` cookies as needed, authorization, and other security headers.

## 13. Checklist before deciding to enable long-term

- [ ] Valid TLS/certificates on the hostname and main HTTPS routes; automated renewal and monitoring in place.
- [ ] HTTP listener redirects to HTTPS with proper host/path; clear ownership of redirects vs. HSTS emission.
- [ ] Verified browsers receive `Strict-Transport-Security` **over HTTPS**, with proper `max-age` and `includeSubDomains` scope.
- [ ] If behind a reverse proxy/TLS terminator, request scheme is trusted or HSTS is emitted at the edge; spoofed forwarded headers are blocked.
- [ ] With `includeSubDomains`, affected hosts and services have been inventoried and all browser-accessed hosts support HTTPS.
- [ ] A staged `max-age` ramp-up plan, error monitoring, and emergency certificate/HTTPS recovery plan exist.
- [ ] If choosing preload, current criteria, all domains/subdomains, and browser-list removal timelines have been reviewed.
- [ ] Header integration tests and real ingress/proxy tests are in place; `secure(true)` tests are not treated as end-to-end TLS proof.

**Remember:** HTTPS secures the connection in the present; **HSTS instructs browsers to keep choosing HTTPS for the hostname in the future**. Spring Security Servlet can automatically emit `Strict-Transport-Security` on secure requests, but TLS setup, redirects, reverse proxies, subdomains, policy lifetime, and recovery capability determine whether HSTS is safe to deploy.
