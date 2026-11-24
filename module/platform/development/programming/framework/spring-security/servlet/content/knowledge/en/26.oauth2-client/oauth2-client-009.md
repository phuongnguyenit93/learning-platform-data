# Redirect URI Behind a Reverse Proxy and Public URL Configuration in Spring Security OAuth2 Client

## 1. The problem: the application sees an internal URL, while users access a public URL

In **Spring Security Servlet** with **OAuth2 Client / OAuth2 Login**, applications often run inside a private network while browsers connect through a reverse proxy, load balancer, or API gateway:

~~~text
User browser
  https://app.example.com
          |
          | HTTPS 443
          v
Reverse proxy / load balancer (TLS termination)
          |
          | Internal HTTP
          v
Spring Boot on http://service:8080
~~~

When logging in via **OAuth2 Authorization Code** (often paired with OpenID Connect), Spring Security redirects the browser to the identity provider (IdP). In this redirect URL is the **redirect_uri** parameter: the address where the IdP will send the browser back after the user logs in.

**Key requirement:** the IdP must receive the exact **public** callback, for example:

~~~text
https://app.example.com/login/oauth2/code/company
~~~

If Spring Security instead derives:

~~~text
http://service:8080/login/oauth2/code/company
~~~

then the IdP may report **redirect_uri_mismatch**, **invalid_redirect_uri**, **invalid_request**, or an equivalent error. Even if the IdP accepted it, the browser could not reach the internal hostname. The root problem usually lies in the **scheme, host, port, or path/prefix** the application receives from the reverse proxy.

This article focuses on **browser-based login with authorization_code** in the Servlet stack. An OAuth2 Client using only **client_credentials** for server-to-server API calls does not perform browser login/callbacks as shown in this example.

After this lesson, you will understand: (1) how Spring Security builds the redirect URI, (2) how **Forwarded / X-Forwarded-*** headers reconstruct the public URL, (3) configuring **server.forward-headers-strategy** and **redirect-uri**, (4) cases where a gateway adds or strips a path prefix, and (5) how to test the login flow and debug safely.

## 2. Distinguishing the authorization request URL and the callback URL

Two frequently confused endpoints:

| Endpoint | Who calls it and when? | Role |
| --- | --- | --- |
| **/oauth2/authorization/company** | Browser visits the application to **initiate login** | Spring Security builds the Authorization Request and returns 302 redirecting to the IdP |
| **/login/oauth2/code/company** | IdP redirects the browser **back** after login | Spring Security receives **code** and **state**, checks correlation, and exchanges the code for tokens |
| **IdP Authorization Endpoint** | Browser is redirected to the IdP | IdP authenticates the user and confirms the OAuth2 request |
| **IdP Token Endpoint** | Application backend calls the IdP | Exchanges the authorization code for tokens per the IdP's OAuth2/OIDC policy |

The name **company** is the **registrationId** in OAuth2 Client configuration. It is not the IdP's hostname and not necessarily a default provider name.

Full flow:

~~~text
(1) GET https://app.example.com/oauth2/authorization/company
    |
    v
(2) Spring Security builds authorization request, stores state in session
    |
    v
(3) HTTP 302 Location: https://idp.example.net/authorize?
          client_id=...
          &response_type=code
          &scope=...
          &state=...
          &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
    |
    v
(4) User logs in at IdP
    |
    v
(5) GET https://app.example.com/login/oauth2/code/company?code=...&state=...
    |
    v
(6) Proxy forwards request back to Spring Security
    |
    v
(7) Spring Security verifies state, exchanges code for token, and establishes authentication
~~~

In practice, the URL in step (3) often contains additional parameters depending on the provider, such as **nonce**, or **code_challenge** when using PKCE; do not use this diagram to conclude the parameter list is always identical. Step (5) uses a **GET query response** in standard configurations; a provider using another response mode requires reviewing how cookies/sessions behave.

**redirect_uri must match the configuration registered at the IdP.** IdP matching can be very strict, distinguishing **http/https**, hostname, port, path, letter casing, and trailing slashes. Never append dynamic query parameters or alter the callback arbitrarily.

## 3. How Spring Security builds redirect_uri from baseUrl

For registrations using Authorization Code, Spring Security supports template variables such as:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Where:

- **{baseUrl}**: the base URL seen from the request processed by Spring Security, including scheme, host, port (if needed), and appropriate public context path.
- **{registrationId}**: the registration name, e.g. **company**.
- **/login/oauth2/code/{registrationId}**: the default callback handled by the OAuth2 Login authentication filter when using standard configuration.

Three example cases:

| Browser visits | Internal backend | Correct redirect_uri |
| --- | --- | --- |
| https://app.example.com | http://service:8080 | **https://app.example.com/login/oauth2/code/company** |
| https://app.example.com:8443 | http://service:8080 | **https://app.example.com:8443/login/oauth2/code/company** |
| https://app.example.com/portal | http://service:8080 and proxy strips **/portal** | **https://app.example.com/portal/login/oauth2/code/company** |

If the backend sees **http://service:8080** because trusted proxy info is missing, **{baseUrl}** may be wrong. Conversely, if the gateway declares the wrong prefix, the callback may miss **/portal** or duplicate into **/portal/portal**.

Remediation should prioritize **fixing the public URL model and trusted headers**. You can set an absolute redirect-uri per environment when a fixed hostname is needed, but that does not replace ensuring the reverse proxy actually forwards the real callback to the right application.

### Two related configuration groups with different functions

- **spring.security.oauth2.client.registration.company.redirect-uri** determines the **redirect_uri** value put into the Authorization Request and used in the OAuth2 Client flow.
- **server.forward-headers-strategy** determines how the Spring Boot app processes forwarded headers supplied by the proxy. It can affect the scheme/host/port/context path seen by web components.

Enabling forwarded headers does not automatically change the value registered at the IdP. Editing `redirect-uri` in `application.yml` also does not automatically fix the gateway, cookies, or sessions.

## 4. Spring Boot 3.x, Spring Security 6.x, Java 17+ example

Place this example in a Spring Boot application that has a Gradle wrapper. In **build.gradle**, add the dependencies if not already present:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Configure **src/main/resources/application.yml**:

~~~yaml
server:
  forward-headers-strategy: framework

spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OAUTH_CLIENT_ID}
            client-secret: ${OAUTH_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Meaning:

1. **registration.company** creates a client registration with ID **company**, so the login initiation URL is **/oauth2/authorization/company** and the default callback is **/login/oauth2/code/company**.
2. **provider.company-oidc.issuer-uri** lets Spring look up the issuer's OIDC metadata, such as authorization endpoint, token endpoint, and JWK Set. The issuer must be a real value published by the IdP and reachable by the backend. This example requires an OIDC IdP supporting discovery; not every OAuth2 server supports OIDC discovery.
3. **OAUTH_CLIENT_ID** and **OAUTH_CLIENT_SECRET** are environment variables or deployment secrets. Never write real client secrets into Git, READMEs, logs, or redirect URLs.
4. **redirect-uri** uses the **{baseUrl}** template, so the scheme/host/port and prefix of the request after proxy processing determine the generated callback.
5. **forward-headers-strategy: framework** tells Spring Boot on Servlet to process forwarded headers at the framework layer (typically via **ForwardedHeaderFilter**). This configuration is only safe when forwarded headers are controlled by a trusted proxy.

File **src/main/java/com/example/loginproxy/LoginProxyApplication.java**:

~~~java
package com.example.loginproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginProxyApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}

@RestController
class ExampleController {
    @GetMapping("/")
    String home() {
        return "Visit /oauth2/authorization/company to sign in";
    }

    @GetMapping("/account")
    String account(@AuthenticationPrincipal OidcUser user) {
        return "subject=" + user.getIdToken().getSubject();
    }
}
~~~

**How to test in practice:** Configure a valid OIDC IdP, supply the three environment variables, and run the app behind an HTTPS reverse proxy. At the IdP, register the exact callback:

~~~text
https://app.example.com/login/oauth2/code/company
~~~

Visit **https://app.example.com/oauth2/authorization/company**. Spring Security will generate a request with **redirect_uri** pointing to the address above, provided forwarded headers are handled properly. After login, **GET /account** returns **subject=...** with the subject from the user's ID token; the exact value depends on the account/IdP and cannot be predicted beforehand.

**Example boundaries:** Without a real IdP/credentials, you cannot run the full login flow from demo code alone. Dependencies and Java source compile in a properly configured Boot 3.x project; an OIDC environment and public URL are needed to verify the callback. Never use illustrative tokens or secrets to log into production.

## 5. The reverse proxy must forward the exact public URL

Because HTTPS usually terminates at the proxy, the backend sees an internal HTTP socket. The proxy must pass **public** information via standardized headers within the trust boundary:

| Header | Example value | Effect |
| --- | --- | --- |
| **X-Forwarded-Proto** | https | Public scheme |
| **X-Forwarded-Host** | app.example.com | Public host |
| **X-Forwarded-Port** | 443 | Public port |
| **X-Forwarded-Prefix** | /portal, when an actual prefix exists | External path prefix that may have been stripped by the proxy |
| **Forwarded** | proto=https;host=app.example.com | RFC standard alternative header; pick a consistent approach |
| **X-Forwarded-For** | original IP address managed by trusted proxy | Related to client IP and logging; does not decide callback hostname |

**Only trusted proxies may set these values.** If an Internet client sends **Forwarded: host=evil.example** and the application trusts it, an attacker can influence URLs generated by the app and cause errors or redirect/host-poisoning risks. At the Internet boundary, the proxy must **strip or overwrite** client-supplied forwarded headers and regenerate them only from permitted hostnames/protocols. Restrict direct access to the backend port; never rely on users "not guessing" an internal port.

### Proxy config snippet for a deployment without a path prefix

Inside an HTTPS **server** block with **server_name app.example.com** and separately configured TLS certificates, the following Nginx location example shows the information to forward:

~~~nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host app.example.com;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.com;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;
}
~~~

This is a **snippet** inside an Nginx configuration, not a full deployment/TLS file. **X-Forwarded-For $remote_addr** describes a proxy at the direct edge; if there are multiple trusted proxies, building and accepting the IP chain requires dedicated design. Never take raw client-sent headers to construct public URLs.

Setting **proxy_set_header Forwarded "";** prevents keeping a client-supplied **Forwarded** value while Nginx explicitly sets the **X-Forwarded-*** family. The app should only trust these headers when the internal port is restricted and the proxy path genuinely satisfies the rules above.

You can use the standard **Forwarded** header instead of **X-Forwarded-*** if your infrastructure supports it, but verify precedence and overwriting so two header sets never describe two different hostnames.

### framework and native

In Spring Boot, **server.forward-headers-strategy** typically has these options:

- **none**: Spring Boot does not process forwarded headers.
- **native**: let the servlet container handle them per its capabilities/configuration.
- **framework**: use framework-level mechanisms to read forwarded headers.

This article uses **framework** to illustrate directly on Spring MVC. If choosing **native** (e.g., via Tomcat's `RemoteIpValve` config), verify each header type and trusted proxy configuration; do not assume it handles prefixes identically to **ForwardedHeaderFilter**. Avoid enabling multiple layers processing the same headers without knowing which is authoritative.

## 6. When the application has a public path prefix

This is often the hardest case to diagnose. Suppose the browser visits:

~~~text
https://app.example.com/portal/oauth2/authorization/company
~~~

But the reverse proxy **strips /portal** and forwards to the backend:

~~~text
http://service:8080/oauth2/authorization/company
~~~

The backend handles the security endpoint at path **/oauth2/authorization/company**. However, the IdP must return to a callback **with the public prefix**:

~~~text
https://app.example.com/portal/login/oauth2/code/company
~~~

In a prefix-stripping model, a trusted reverse proxy can send:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
~~~

and the application processes them with **forward-headers-strategy: framework**. Inspect the **Location** generated on an actual request; prefix accuracy depends on proxy config, servlet mapping, context path, and version. Never guess that adding one header is enough for every request/callback to work.

If the application already runs with **server.servlet.context-path: /portal** and the proxy passes the prefix intact, **do not** also force the same prefix into **X-Forwarded-Prefix**, unless you have verified paths are not doubled. There are two common architectures:

| Architecture | Proxy forwards to backend | URL resolution |
| --- | --- | --- |
| App actually has context path **/portal** | Keeps **/portal** on the request | Context path is part of the base URL; do not add prefix a second time |
| App is at root context **/**, proxy strips **/portal** | Forwards **/oauth2/...** to backend | Proxy declares external prefix properly; backend reconstructs external URL |

You must test **both directions**:
1. Browser hits the right public authorization URL.
2. Authorization Request sends the right **redirect_uri** to the IdP.
3. IdP calls back the **public callback** including the prefix.
4. Proxy maps the callback to **/login/oauth2/code/company** inside the backend.
5. Session cookie is still sent with the right path and host across the round trip.

If the proxy drops the prefix when building the authorization request or when forwarding the callback, you may see **redirect_uri_mismatch**, 404, or **authorization_request_not_found**. These are three errors with different causes; never work around them by disabling security.

## 7. Absolute redirect-uri configuration: when is it appropriate?

If the application only has **one fixed public hostname per environment**, you can choose an explicit URL instead of **{baseUrl}**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "https://app.example.com/login/oauth2/code/company"
~~~

The snippet above **only replaces the redirect-uri value** in the full configuration in Section 4; keep the other client/provider properties. This approach keeps the authorization request from depending on forwarded host/scheme to pick the callback, yet the browser still has to return to the endpoint routed by the proxy to the backend and the session must still remain valid.

Across multiple environments (**localhost/staging/production**), the IdP typically needs matching redirect URIs registered, or separate client registrations/secrets. Avoid wildcard callbacks and avoid allowing arbitrary hosts; choose public URIs in a controlled way via deployment configuration, such as profiles or system-supplied environment variables.

Do not hardcode a fixed **redirect_uri** just to avoid understanding request forwarding: login confirmation emails, form actions, absolute links, cookies, or other redirects can still break if the application does not know its accurate public URL.

### Do not change the callback path on one side only

If you choose a callback different from **/login/oauth2/code/{registrationId}**, you must configure **OAuth2LoginAuthenticationFilter** accordingly (e.g., **oauth2Login().redirectionEndpoint().baseUri(...)**) and the security chain must match that endpoint. Changing only **registration.redirect-uri** causes the IdP to call back a path not handled by the default OAuth2 Login filter, typically resulting in 404 or unintended login redirects.

For most applications, keeping the default callback reduces the number of places to configure.

## 8. Testing: inspecting redirect_uri before logging in

### A. HTTP check via public host

In staging or a test environment with valid DNS/TLS and a client registered at the IdP, run:

~~~bash
curl -i 'https://app.example.com/oauth2/authorization/company'
~~~

Expect a **302** response with a **Location** header pointing to the IdP's authorization endpoint. Inside the Location URL, decode the **redirect_uri** parameter and compare it with the registered callback:

~~~text
redirect_uri=https://app.example.com/login/oauth2/code/company
~~~

Many parameters in **Location** are percent-encoded; the entire Location URL does not need to be identical across two runs, because **state**, **nonce**, and random values change. Never post raw Location strings containing state to public channels.

If you receive **302 to /login** instead of the IdP, check the registration ID, selected `SecurityFilterChain`, and OAuth2 login setup. If you receive **500** or startup failures, check IdP discovery, environment variables, and issuer configuration. If Location points to **http://service:8080**, focus on **forwarded header trust** and whether Spring Boot is processing forwarded headers.

Then complete login in a browser and inspect Network:

- The outgoing Authorization Request contains the right `redirect_uri`.
- The actual callback arrives at the right public URL with **code/state** per the flow.
- The browser sends the session cookie the application needs to correlate **state**.
- The proxy routes the callback to the right backend.
- The application establishes authentication successfully without creating a redirect loop.

### B. Unit test for URL reconstruction from forwarded headers

The small test below verifies **ForwardedHeaderFilter** behavior in isolation. It does **not** replace an end-to-end OAuth2 test and **only uses simulated headers from a trusted source**.

File **src/test/java/com/example/loginproxy/ForwardedUrlTest.java**:

~~~java
package com.example.loginproxy;

import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.ForwardedHeaderFilter;

class ForwardedUrlTest {
    @Test
    void reconstructsPublicSchemeHostAndPort() throws Exception {
        MockHttpServletRequest request =
                new MockHttpServletRequest(
                        "GET", "/oauth2/authorization/company");
        request.setScheme("http");
        request.setServerName("service.internal");
        request.setServerPort(8080);

        request.addHeader("X-Forwarded-Proto", "https");
        request.addHeader("X-Forwarded-Host", "app.example.com");
        request.addHeader("X-Forwarded-Port", "443");

        MockHttpServletResponse response = new MockHttpServletResponse();

        new ForwardedHeaderFilter().doFilter(request, response, (req, res) -> {
            HttpServletRequest actual = (HttpServletRequest) req;
            assertEquals("https", actual.getScheme());
            assertEquals("app.example.com", actual.getServerName());
            assertEquals(443, actual.getServerPort());
            assertEquals(
                    "https://app.example.com/oauth2/authorization/company",
                    actual.getRequestURL().toString());
        });
    }
}
~~~

Run in a Boot project with Gradle wrapper:

~~~bash
./gradlew test --tests com.example.loginproxy.ForwardedUrlTest
~~~

On Windows, use **gradlew.bat test --tests com.example.loginproxy.ForwardedUrlTest**. The test is expected to complete without assertion failures. It proves the URL exposed by the Servlet request after the filter, but **does not prove** the IdP is registered properly, sessions persist, or the proxy routes callbacks accurately. To verify those factors, use the HTTP/browser test in part A.

### C. Minimal test matrix

| Scenario | What to verify |
| --- | --- |
| Browser hits https://app.example.com/oauth2/authorization/company | 302 to IdP; redirect_uri uses **https** and public hostname |
| Proxy passes backend HTTP :8080 | redirect_uri does **not** contain internal hostname/port |
| External path prefix **/portal** | redirect_uri has **/portal** exactly once; callback routes to app |
| Staging host and production host | Each environment produces the callback registered at the IdP |
| Callback after login | **state**, session cookie, and callback path correlate successfully |
| Direct request to backend | Backend is not arbitrarily publicly reachable; forged forwarded headers cannot alter security URLs used by external callers |
| Callback wrong path/port | No login loop; logs clearly indicate mapping or mismatch error |

## 9. Common errors

| Symptom | Likely cause | Check / fix |
| --- | --- | --- |
| **redirect_uri_mismatch** at IdP | Sent Redirect URI differs from registered allowlist | Decode `redirect_uri` in Location, compare scheme/host/port/path/trailing slash |
| `redirect_uri` contains **http://service:8080** | Backend is not using public forwarded info, or proxy is not passing it properly | Check **server.forward-headers-strategy**, trusted proxy, X-Forwarded-Proto/Host/Port |
| **http** instead of **https** | TLS terminates at proxy while backend only sees HTTP | Configure scheme forwarding properly; never trust headers from the Internet |
| Missing or duplicated **/portal** | Proxy strip/preserve prefix inconsistent with context path and X-Forwarded-Prefix | Inspect inbound/outbound requests, check IdP callback and gateway mapping |
| Callback returns **404** | Callback not routed properly by gateway, or security filter does not handle customized URI | Keep default **/login/oauth2/code/{registrationId}** or configure `redirectionEndpoint` accordingly |
| **authorization_request_not_found** / **invalid_state** | Session lost, cookie not returned, multiple replicas not sharing sessions, state altered | Check cookie host/path/SameSite/Secure, timeout, session store, reverse proxy, and multi-replica flow |
| Callback loops back to **/login** | Wrong security chain, authentication not restored, callback not handled by OAuth2 login filter | Inspect `FilterChainProxy` and Spring Security logs; avoid one-sided callback path changes |
| Works on localhost, fails on staging | Different host/port/prefix or IdP registration | Check public hostname and redirect URI specific to each environment |
| Set fixed redirect-uri, yet still fails | Proxy does not route callback, wrong cookie/session, or IdP still uses old allowlist | Check entire authorize → callback → token exchange cycle |
| Browser keeps losing session | Cookie blocked by Secure/SameSite, wrong domain/path, or load balancing | Check Set-Cookie and Cookie in Network; never log session/token values |

### Cookies, state, and multiple replicas

In common Spring Security OAuth2 Login setups, the authorization request (containing **state**) is held across the **HTTP session**, via the default **HttpSessionOAuth2AuthorizationRequestRepository**. When the browser returns to the callback, the system must retrieve the matching authorization request.

If the public host changes mid-login, the session cookie is not sent under the matching domain/path, the proxy sends the callback to a replica not sharing sessions, or the session expires, the flow can fail even when `redirect_uri` is 100% correct.

With multiple replicas, use an appropriate session mechanism such as a shared session store or controlled routing; never disable **state** checks to work around errors. For standard OIDC using top-level GET callbacks, **SameSite=Lax** is usually appropriate, though cookie policies must be tested in real browsers; flows using **form_post** and cross-site cookies have different requirements. In production, ensure session cookies are protected over HTTPS with the **Secure** flag where appropriate and cookie paths aligned with any public prefix.

### Security when trusting proxy headers

Setting **forward-headers-strategy: framework** does not authenticate the proxy. It merely tells the application to use the headers that are present. To prevent spoofing:

1. Restrict networking so external users cannot connect directly to the backend.
2. At public ingress, strip or overwrite client-supplied **Forwarded** and **X-Forwarded-*** headers.
3. Accept only configured public hostnames/ports; never concatenate an arbitrary client-chosen Host.
4. With multiple proxies, define which hop may set headers and ensure downstream hops preserve the validated values.
5. Maintain valid TLS on the public host; never put codes/tokens/client-secrets into logs or detailed user error messages.
6. Ensure the IdP accepts only exact registered redirect URIs; avoid broad wildcards or open redirects.

## 10. Checklist before deploying OAuth2 Client behind a reverse proxy to production

1. **Public URL:** Unambiguously define the scheme, host, port, and external prefix accessed by users.
2. **IdP registration:** Callback matches the exact value generated by the app (never confuse with the login initiation URL).
3. **Client registration:** Correct registrationId, issuer metadata, client ID/secret, scopes, and redirect-uri template.
4. **Proxy:** Route both **/oauth2/authorization/{registrationId}** and **/login/oauth2/code/{registrationId}**; handle prefixes consistently.
5. **Forwarded headers:** Generated by a trusted proxy, never reflecting uncontrolled client headers; Spring Boot **framework** or container **native** config verified.
6. **Security chain:** OAuth2 Login and callback are handled in the right chain; callbacks are not blocked by wrong matchers, redirect loops, or other filters.
7. **Cookies/sessions:** HTTPS, proper SameSite/Secure/Path; session survives until callback, and multiple replicas have a session storage design.
8. **Testing:** Check 302 Location and **decoded redirect_uri**, complete real login, confirm no internal hostname or wrong prefix appears.
9. **Environment isolation:** Staging/production have their own registrations, domains, and callbacks; never hardcode another environment's callback.
10. **Operations:** Record status, endpoint, correlation ID, and error category sufficient for diagnostics without exposing authorization codes, states, access tokens, ID tokens, or client secrets.

**A working configuration must stay consistent in all three places:** the browser's public URL, the redirect URI registered at the IdP, and the URL computed by Spring Security from the proxied request. When these three match and the session/callback route is preserved, the OAuth2 Client flow behind a reverse proxy works without relaxing security rules.
