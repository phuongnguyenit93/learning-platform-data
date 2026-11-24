# Differences when calling an API from a browser, curl, and another service

The same Spring Boot API, same GET method, and same URL can hit a CORS error from a browser, return JSON from curl, and receive 401 from a Java service because it hasn't attached a token. To diagnose accurately, you must distinguish **HTTP and server rules** from **the specific behavior of each HTTP client type**.

This lesson is set in the context of Spring Security: requests are authenticated and authorized on the server, while browsers enforce additional policies on origins, cookies, JavaScript, and response reading. The curl tool and backend applications use HTTP without equivalent browser defense layers. They still must comply with the security policy enforced by the server.

## 1. Objectives and foundational principles

After this lesson, you should be able to do four things:

1. Explain why the same endpoint can yield different results across a browser, curl, and a service-to-service client.
2. Identify whether requests actually differ in **method, URL, headers, cookies, Authorization, body, Origin, proxy, or TLS**.
3. Distinguish **CORS, CSRF, authentication, and authorization**, and recognize 200, 302, 401, 403, 404, and 405 in the right context.
4. Reproduce a scenario with curl, Java HttpClient, and fetch; gather enough evidence to isolate whether an issue lies in the browser, gateway, Spring Security, or business logic.

**Important rule:** The server receives HTTP requests, not a trustworthy "client type" just because User-Agent claims to be Chrome, curl, or Java. Most client-created headers can be spoofed outside a browser. The server must verify credentials and principal permissions, validate data, and return only permitted information.

## 2. All three speak HTTP, differing in execution environment

A request may have the structure:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>

~~~

A successful response may be:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"user":"alice"}
~~~

The HTTP/1.1 examples above are illustrative representations. In practice, browsers or HTTP clients may use HTTP/2 or HTTP/3; method, URI, header, status, and body semantics correspond accordingly.

On the server side, a Spring MVC API typically follows the flow:

~~~text
Browser / curl / service client
             |
             | HTTP request
             v
     Reverse proxy / gateway
             |
             v
    Servlet Filter Chain
             |
             v
  Spring Security filters
     |             |
     | denied      | allowed
     v             v
  401/403/...    Controller
                    |
                    v
               Service/DB
                    |
                    v
                Response
~~~

This path is a conceptual model: gateways, middleware, and exception handlers can also return statuses before or after filters. Browsers additionally apply **client-side** security policies before sending certain requests and before letting JavaScript read responses.

### 2.1. Quick comparison table

| Aspect | Browser (fetch/AJAX) | curl | Backend service (Java HttpClient, RestClient, WebClient...) |
| --- | --- | --- | --- |
| Who emits the request? | Web page/script running in the browser, or browser document navigation. | Command-line user/script. | Code running on a server or worker. |
| Same-Origin Policy | Applies to access via JavaScript; some resources have separate rules. | Does not have this browser mechanism. | Does not have this browser mechanism. |
| CORS | Browser checks policy and may send OPTIONS preflight. | Does not enforce CORS; can explicitly send Origin header to test. | Does not enforce CORS; libraries can send Origin if programmed. |
| Cookies | Has a cookie jar and Domain, Path, Secure, HttpOnly, SameSite, credentials rules. | Does not reuse browser session cookies automatically; can specify cookies or a cookie jar. | Usually has no default cookie jar; depends on library/config. |
| Authorization | May be set by browser or JavaScript per login mechanism. | Must be explicitly supplied via flag/header or config. | Must obtain/attach user or service identity per policy. |
| CSRF | Browser may auto-send cookies creating CSRF risk; server checks tokens when applicable. | Does not auto-generate CSRF tokens; still rejected by server if required token is missing. | Does not auto-generate CSRF tokens; if calling session/cookie endpoints must still meet policy. |
| Redirects | Browser navigates/fetches per redirect rules and security policy. | Does not follow redirects by default; use -L when needed. | Library-dependent; JDK HttpClient does not follow redirects by default unless configured. |
| TLS | Browser verifies certificates per browser trust store/policy. | curl verifies certificates per config and CA bundle; do not use -k to bypass errors. | Java/HTTP stack verifies TLS per trust store/config. |
| Viewing errors | Network panel, Console, fetch response, or policy-blocked error. | Directly sees status/headers/body from server if no connection error. | Logs/exceptions/HTTP response per client code and policy. |
| Network location | User's machine with its own DNS/proxy/VPN. | Machine running curl; may be on same or different network. | Server/pod; its own DNS, egress, firewall, proxy, and permissions. |

**Compare actual requests, not just the typed URL.** A GET from a browser may carry a session cookie; a curl command carries no cookie, while a backend attaches a different service token. Hence the server can return three different statuses while endpoint and method look identical.

## 3. Browsers: origin, Same-Origin Policy, and CORS

### 3.1. What is an origin?

An **origin** is the **scheme + host + port** tuple:

- https://app.example.test and https://api.example.test: two different origins because the hosts differ.
- http://localhost:3000 and http://localhost:8080: two different origins because the ports differ.
- http://localhost:8080 and https://localhost:8080: two different origins because the schemes differ.

**Same-site** does not mean **same-origin**. Two subdomains on the same site can be different origins even though SameSite cookie rules treat them as same-site under the applicable model. CORS uses origin, whereas SameSite uses the site concept.

**Same-Origin Policy (SOP)** restricts JavaScript from one origin accessing content from another origin. However, it does not mean the browser is strictly barred from sending cross-origin requests: navigations, forms, images, or certain fetches can send requests; whether scripts can **read the response** depends on security policy and CORS.

### 3.2. Browser making a fetch call to another origin

Suppose the UI runs at http://localhost:3000 and the API at http://localhost:8080. The code is run in the Console of a page at the UI origin:

~~~javascript
const response = await fetch("http://localhost:8080/api/public");
console.log(response.status);
console.log(await response.text());
~~~

If the API does not allow origin http://localhost:3000 to read the response, the browser may send GET and the server **still returns 200**, yet JavaScript receives a CORS error or TypeError: Failed to fetch. In DevTools Network you can sometimes still see the network response. **A CORS error does not mean the backend failed to process the request.**

If the server allows it via an appropriate policy, the response may contain:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Vary: Origin
~~~

When the server returns a matching Access-Control-Allow-Origin, the browser lets JavaScript read the response per CORS rules. This header **is not proof of user authentication** and does not replace server-side permission controls.

### 3.3. When does an OPTIONS preflight happen?

Some cross-origin requests require a **CORS preflight**. For example, if a script attaches Authorization or sends Content-Type: application/json for a POST, the browser usually sends OPTIONS first:

~~~http
OPTIONS /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization

~~~

The server returns the permitting headers, for example:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Allow-Credentials: true
Vary: Origin

~~~

**This is an example response**; a successful preflight status may vary by server. Only after a valid preflight does the browser send the corresponding business request. If preflight fails, the browser does not send the business request for that fetch flow.

Notes:

- A "simple" cross-origin GET may be sent **without a preflight**, though reading the response is still subject to CORS.
- Not every OPTIONS is a CORS preflight. A preflight has **Origin**, **Access-Control-Request-Method**, and when needed **Access-Control-Request-Headers**.
- Preflight is not login and usually carries no credentials like cookies; CORS must be handled appropriately before requiring authentication for business requests.
- Accepting OPTIONS **does not mean** the corresponding GET/POST will be allowed: the real request still must pass authentication, authorization, and other checks.
- Do not use Access-Control-Allow-Origin: * together with Access-Control-Allow-Credentials: true. When credentials are needed, the server must allow specific origins and verify the policy properly.

### 3.4. Browsers do not let JavaScript arbitrarily set every header

JavaScript fetch cannot arbitrarily set certain browser-managed headers, such as Host, Cookie, and Origin. The browser determines those headers based on URL, cookie jar, and policy. Meanwhile, curl can craft forged Origin values and many kinds of request headers for testing.

Therefore **never trust Origin, User-Agent, or X-Role just because "the browser sets it automatically."** Outside a browser, those headers can be spoofed. Origin is meaningful in CORS and can serve as a CSRF defense signal per threat model, yet does not prove a principal is authorized.

### 3.5. Cookies and fetch credentials mode

When an application logs in with session cookies, the browser can retain cookies and auto-send them on matching requests per domain/path/SameSite/Secure. JavaScript does not need to read an HttpOnly cookie for the browser to send that cookie.

With fetch:

- Default credentials: "same-origin": the browser sends credentials in same-origin contexts per policy.
- Cross-origin fetch wanting to send valid cookies usually needs **credentials: "include"**, and cookies must also be permitted by Domain/Path/Secure/SameSite and browser policies.
- The server also needs CORS allowing the specific origin and Access-Control-Allow-Credentials: true if the browser is allowed to let scripts receive credentialed responses.
- credentials: "include" **does not create login info on its own**; it only affects how the browser handles existing credentials.
- SameSite and CORS solve different problems. An origin may be allowed by CORS while cookies are still withheld due to SameSite or third-party cookie rules.

Example request config from a UI (only meaningful if the real server uses cookie sessions):

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include",
  headers: { Accept: "application/json" }
});
console.log(response.status);
~~~

Without a valid cookie, a protected endpoint may still return 401 or redirect to login. Adding credentials: "include" cannot fix the lack of a valid session.

### 3.6. Browser, CORS, and CSRF are three separate layers of issues

**CORS** primarily governs whether JavaScript on one origin may read responses from another origin.

**CSRF** is the risk of an attacker causing a user's browser to send a side-effecting request to an application to which the browser auto-attaches credentials (especially session cookies). Some requests can be sent even when scripts are not allowed to read the response. Hence **CORS does not replace CSRF protection**.

With sessions/cookies, POST/PUT/PATCH/DELETE typically require a CSRF token or a properly designed anti-forgery equivalent. Spring Security has a CSRF mechanism. For stateless APIs accepting only Bearer tokens explicitly attached by the app in Authorization and rejecting auto-sent credentials, CSRF risk typically differs, though token protection and XSS defense remain necessary.

If an API alters state via GET, relying on the default rule "GET is safe so no CSRF token is needed" can be dangerous. Design HTTP methods with accurate semantics before choosing a CSRF policy.

## 4. curl: sending HTTP directly and controlling requests explicitly

curl is a command-line HTTP client. It **does not enforce browser SOP/CORS**, does not carry active Chrome/Edge login sessions, and does not automatically pull browser cookies. The user must explicitly supply credentials and required headers.

On Windows PowerShell use **curl.exe** to avoid conflicting with the `curl` alias in some PowerShell versions. On Linux/macOS normally use `curl`.

### 4.1. Basic commands

~~~bash
curl.exe -i https://api.example.test/api/public
curl.exe -i -X GET https://api.example.test/api/profile
curl.exe -i -H "Accept: application/json" https://api.example.test/api/public
~~~

- **-i:** displays both response headers and body.
- **-I:** usually requests HEAD and displays only response headers, not substituting for an actual GET when checking the body.
- **-X:** sets the method; avoid unnecessary -X GET/POST because curl selects the appropriate method for bodies automatically.
- **-v:** shows HTTP/TLS exchange for debugging, though it can expose credentials or sensitive data; redact details before sharing logs.
- **--fail-with-body:** makes curl exit with an error code when the HTTP response indicates a server error while keeping the body for diagnosis; available in supporting curl versions.

HTTP 401/403 **is not necessarily a command-line execution failure** for curl unless flags treating HTTP status as failure are used. Distinguish curl's process exit code from the HTTP status returned by the server.

### 4.2. Sending Authorization

With a Bearer token used in a test environment:

~~~bash
curl.exe -i -H "Authorization: Bearer DEMO_TOKEN" \
  https://api.example.test/api/profile
~~~

Line continuation with trailing `\` is Unix shell syntax. In PowerShell, write it on **one line** or use PowerShell's line continuation syntax:

~~~powershell
curl.exe -i -H "Authorization: Bearer DEMO_TOKEN" https://api.example.test/api/profile
~~~

HTTP Basic for test environments:

~~~powershell
curl.exe -i -u reader:demo-password http://localhost:8080/api/private
~~~

In real environments, avoid putting real secrets in command history, process arguments, shared screens, or logs; prefer managing credentials via proper mechanisms. HTTP Basic only Base64-encodes credentials; **HTTPS is required** when exchanging over real networks.

### 4.3. Cookie jar in curl

If the server logs in with cookies, calling one API URL does not mean curl has a session like a browser. You can use a cookie jar:

~~~bash
curl.exe -i -c cookies-demo.txt https://api.example.test/login
curl.exe -i -b cookies-demo.txt https://api.example.test/api/me
~~~

These two commands only illustrate how to **save/read cookies**; the first command does not prove login succeeded because real login usually requires POST, form data, or OAuth flows, and possibly a CSRF token. Cookie jar files hold sensitive info and must be protected and properly deleted after tests.

Manually sending a test cookie:

~~~powershell
curl.exe -i -b "SESSION=example-session" http://localhost:8080/api/me
~~~

The cookie must be valid on the server side. A fabricated cookie string does not grant access. If the server requires a CSRF token, curl must send the matching token; using curl **does not bypass** server-side CSRF checks.

### 4.4. curl with CORS and redirects

Simulating a browser's Origin:

~~~powershell
curl.exe -i -H "Origin: http://localhost:3000" http://localhost:8080/api/public
~~~

Sending a full preflight:

~~~powershell
curl.exe -i -X OPTIONS -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization" http://localhost:8080/api/private
~~~

curl prints the response even when Access-Control-Allow-Origin is absent. However, **the server can still actively reject** requests carrying an unpermitted Origin—for example, Spring's CORS processor returning 403. This does not turn Origin into a credential: curl can omit Origin entirely, while actual access rights must be decided by authentication/authorization.

With redirects:

~~~powershell
curl.exe -i http://localhost:8080/api/private
curl.exe -i -L http://localhost:8080/api/private
~~~

The first command does not follow Location automatically; the second tells curl to follow redirects. If the server uses form login, the first response may be 302 to the login page. Following redirects can yield 200 **for the login page**, not 200 for the protected API resource. Check the final URL and Content-Type before concluding success.

In TLS, curl verifies certificates per CA store/config. Never casually use **-k/--insecure** to bypass certificate checks; fix CA, hostname, or trust chain to match the environment.

## 5. Service calling another service: HTTP client running in a backend

Another service may use Java HttpClient, Spring RestClient, WebClient, OpenFeign, or similar libraries. At the HTTP level, it still sends method, URL, headers, and body. Unlike a browser:

- It has no browser Same-Origin Policy, so there is no need to "enable CORS so two microservices can talk."
- It does not automatically hold a user's browser session. Code must decide whether to **call with service identity** or **on behalf of a user**; the two delegation models differ.
- It may run inside a cluster or internal network with its own DNS, firewall, service discovery, proxy, TLS, and egress policies.
- Timeouts, connection pooling, retries/idempotency, observability, token caching/refresh, certificate trust, and outbound data limits must be configured.
- If the service uses cookies, it must actively manage cookies/sessions and satisfy server CSRF policies when applicable. There is no "backends are exempt from CSRF" privilege in the protocol.

### 5.1. Two common identity types

**Service identity:** Backend A calls Backend B to perform A's own work. This may use OAuth2 Client Credentials, mTLS, or another designed machine-to-machine mechanism. Tokens/credentials need least-privilege scopes, audience, and lifetimes.

**User delegation:** Backend A calls Backend B to complete an operation on behalf of a user. Backend B must know and verify the user context via an authorized mechanism (e.g., delegated token or token exchange). **Do not blindly forward tokens received from clients** to every service: the token may not be issued for B's audience and may expose broader permissions than intended.

Example flow:

~~~text
Browser -> Service A -> Service B -> Database
         (user token) (service/delegated token)

Service B must verify:
- Who is calling? Service A or which represented user?
- Is the credential valid and issued for B?
- Does the caller have scope/authority for the action?
- Does the specific resource belong to the user/tenant or caller's permissions?
~~~

Even if A already authenticated the user, B still needs **trust boundary controls**. Never blindly treat requests "coming from internal" as valid, and never trust roles placed by A in arbitrary headers without inter-service authentication guarantees.

### 5.2. Common backend client errors

- **401:** missing token, expired, wrong issuer/audience, or misconfigured credentials.
- **403:** service has a valid identity yet lacks scope/role/object permissions.
- **404:** wrong internal URL or path rewrite, non-existent route, or resource hidden per policy.
- **429:** rate limit exceeded; retries need backoff and must respect Retry-After when present.
- **502/503/504:** gateway, upstream, or network issue; configure reasonable timeouts and retries.
- **SSLHandshakeException:** certificate/trust store/hostname/mTLS mismatch; do not fix by disabling TLS verification.
- **Unexpected redirect:** service may receive a 302 to HTML login instead of JSON, especially when a browser-oriented endpoint is called by a backend HTTP client.

When a service accepts target URLs as input, watch for **SSRF** and outbound network limits: allowlist business destinations, check scheme/host, handle DNS/redirects, and never pass credentials to untrusted hostnames.

## 6. Same API: three real requests can differ

Suppose GET /api/profile requires login. These are illustrative requests, without assuming the three clients share the same identity:

### 6.1. Browser with an existing session cookie

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Cookie: SESSION=<session-id>
Origin: https://app.example.test

~~~

Cookies can be auto-sent if browser policy allows; Origin appears when browser context requires it. If it is a cross-origin fetch, the response also needs to satisfy CORS for JavaScript to read it. If the cookie is blocked or not logged in, the request may result in 401/302.

### 6.2. curl with no credentials

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Accept: */*

~~~

If the server requires credentials, curl may receive 401 and WWW-Authenticate. Missing cookies in curl differ from a logged-in browser. To reproduce accurately, compare cookies/Authorization with sensitive values redacted.

### 6.3. Service sending its own Bearer token

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer <service-token>
Accept: application/json

~~~

A service token may authenticate successfully yet **not represent a user** needing to read a profile. The endpoint may return 403 or another outcome per policy. Conversely, a service token issued with the right scope may work on dedicated machine-to-machine endpoints.

### 6.4. Same HTTP status, different meanings

| Symptom | Browser | curl | Backend service |
| --- | --- | --- | --- |
| API requires login | May get 401, 302, or CORS error hiding response from JavaScript. | Sees 401/302 directly. | Receives 401/302 or exception if client treats status as error. |
| Server returns 403 due to missing role | May see 403 in fetch response if CORS is valid. | Receives 403. | Receives 403. |
| POST missing CSRF token | May receive 403 from Spring Security. | Also gets 403 if endpoint enforces CSRF. | Also gets 403 if using mechanism/endpoint requiring token. |
| Origin not allowed to read response | Browser blocks JavaScript read; preflight may fail. | No browser enforcement; server may still reject if Origin is sent. | No browser enforcement; server/gateway may still have separate rules. |
| Request gets 200 yet data not guaranteed right | Read may be blocked by CORS, or readable after proper auth. | Prints 200 body. | Parses 200 body per client; still must verify schema and permissions. |
| Server redirects to /login | Browser usually follows redirect; fetch may hit HTML/CORS response. | Needs -L to follow. | Depends on client's redirect policy. |

**Do not infer "curl works so CORS is right," or "browser shows CORS error so Spring Security is wrong."** You must analyze the sent request, actual response, preflight, and each component's policy.

## 7. Spring Boot 3.3.x, Java 17+ demo: the same API for three clients

The example below creates an API with three endpoints, educational HTTP Basic, CORS allowing only origin http://localhost:3000, and CSRF kept at its default configuration. The goal is **observing HTTP policies**, not building a production login system.

Requirements: Java 17+, Maven 3.9+, ports 8080 and 3000 free. The `reader/demo` account is for testing only—never use on the Internet or for real data.

Structure:

~~~text
demo-client-calls/
  pom.xml
  src/main/java/com/example/demo/ApiApplication.java
~~~

### 7.1. The pom.xml file

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>demo-client-calls</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

### 7.2. The src/main/java/com/example/demo/ApiApplication.java file

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
@RestController
public class ApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/private")
    public String privateEndpoint(Authentication auth) {
        return "private:" + auth.getName();
    }

    @PostMapping("/api/actions")
    public String action() {
        return "changed";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers("/api/private", "/api/actions").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Keep default CSRF: POST usually needs a CSRF token.
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("http://localhost:3000"));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-CSRF-TOKEN")
        );
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Explanation:

- GET /api/public is public thanks to the explicit GET matcher.
- GET /api/private requires a valid identity; here it uses HTTP Basic and an in-memory user.
- POST /api/actions also requires identity; furthermore default CSRF will reject state-changing requests missing a token when CSRF rules apply.
- http.cors() integrates CORS so preflights are handled properly before authentication in the filter chain.
- CORS allows only **http://localhost:3000**. Origins http://localhost:3001 or file:// are not automatically accepted.
- anyRequest().denyAll() closes routes outside the demonstration scope.
- There is no role/ownership logic in the demo. Real APIs must also add object permissions, quotas, logging, and proper session/token configuration.

**Run the application** in the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Because the example uses HTTP Basic with a test account and localhost HTTP, only test on your own machine; **do not deploy publicly**. When sending real credentials over a network, HTTPS and proper identity management are required.

### 7.3. Calling with curl

In PowerShell, run:

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/private
curl.exe -i -u reader:demo http://localhost:8080/api/private
curl.exe -i -u reader:demo -X POST http://localhost:8080/api/actions
~~~

**Expected results:**

| Test | Status | Body/explanation |
| --- | --- | --- |
| GET /api/public without credentials | 200 | public |
| GET /api/private without credentials | 401 | Includes WWW-Authenticate: Basic ... |
| GET /api/private with reader/demo | 200 | private:reader |
| POST /api/actions with reader/demo, missing CSRF token | 403 | Spring Security rejects before calling action() |

Extra headers may vary by Spring Security/Servlet container. A 403 response does not say the user lacks a role: in the POST case above it is **CSRF protection**. If a valid CSRF token is supplied or policy is adjusted for a stateless API per threat model, the outcome can differ.

Try preflight:

~~~powershell
curl.exe -i -X OPTIONS -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization" http://localhost:8080/api/private
~~~

The expected result is an accepted preflight containing matching Access-Control-Allow-Origin, Access-Control-Allow-Methods, and Access-Control-Allow-Headers headers. **A successful preflight does not return private:reader data and does not authenticate the user.**

Next call GET with a valid Origin:

~~~powershell
curl.exe -i -u reader:demo -H "Origin: http://localhost:3000" http://localhost:8080/api/private
~~~

The server can return 200 with Access-Control-Allow-Origin: http://localhost:3000. Sending an Origin outside the allowed list may cause the CORS handler to return 403; however, calling with curl **without sending Origin** still reaches the API and is protected by HTTP Basic. That is why CORS is not used as an authentication system.

### 7.4. Calling from a browser

Create **index.html** in a separate folder:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Browser API demo</title>
</head>
<body>
  <button id="call">Call API</button>
  <pre id="result"></pre>
  <script>
    document.getElementById("call").addEventListener("click", async () => {
      const result = document.getElementById("result");
      const basic = btoa("reader:demo"); // Demo account only.
      try {
        const response = await fetch(
          "http://localhost:8080/api/private",
          {
            method: "GET",
            credentials: "include",
            headers: {
              Authorization: "Basic " + basic,
              Accept: "text/plain"
            }
          }
        );
        result.textContent =
          "HTTP " + response.status + ": " + await response.text();
      } catch (error) {
        result.textContent = "Fetch failed: " + String(error);
      }
    });
  </script>
</body>
</html>
~~~

Use a static server to serve the page at **http://localhost:3000** (for example, in the directory containing index.html, if Python is installed):

~~~bash
python -m http.server 3000
~~~

On Windows you can also use **py -m http.server 3000** if Python is installed with the launcher. Open http://localhost:3000/index.html and click the button.

**Expected result on the page:** HTTP 200: private:reader. In DevTools Network there will be an OPTIONS preflight because the cross-origin request carries Authorization, followed by the authenticated GET. CORS on the backend allows the exact origin http://localhost:3000. The snippet exposing a demo password in JavaScript is **for lesson purposes only**; production apps must never embed fixed passwords or service secrets in frontend code.

To see a different result, open the same file via another origin, such as http://127.0.0.1:3000 or http://localhost:3001 once hosted appropriately. The browser will emit an Origin not in the allowed list and may block the request at preflight. The Console message is a CORS error, not a "password is definitely wrong" message.

Do not open index.html via file:// to compare origins in this example: file:// pages usually produce a special origin (often represented as null) which is not in the allowlist.

### 7.5. Calling from a Java 17 service

The **ServiceClient.java** file below is a standalone Java program. The Spring Boot API above must be running.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

public class ServiceClient {

    public static void main(String[] args) throws Exception {
        String demo = "reader:demo";
        String basic = Base64.getEncoder().encodeToString(
            demo.getBytes(StandardCharsets.UTF_8)
        );

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:8080/api/private"))
            .timeout(Duration.ofSeconds(10))
            .header("Accept", "text/plain")
            .header("Authorization", "Basic " + basic)
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("HTTP " + response.statusCode());
        System.out.println("Body " + response.body());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac ServiceClient.java
java ServiceClient
~~~

**Exact expected stdout**, when the demo server is running with no other interceptors/proxies:

~~~text
HTTP 200
Body private:reader
~~~

The program **does not send Origin**, because it is not a script running inside a browser. Spring Security still checks HTTP Basic just as with curl. Java HttpClient does not need CORS to read the response. In real projects, do not hardcode passwords or send Basic over HTTP; use secret management, OAuth2 client credentials/delegation, or mTLS per design, HTTPS, and business-appropriate timeouts/retries.

HTTP client libraries handle cookies, redirects, and exceptions differently. With **JDK HttpClient** in the example, without a CookieHandler there is no browser cookie jar; without configuring followRedirects the default is **NEVER**. These do not automatically match curl or fetch.

## 8. Analyzing a range of common error scenarios

### 8.1. Browser reports CORS, curl receives 200

Check the actual **Origin** in DevTools, OPTIONS preflight, Access-Control-Allow-Origin, and credentials mode. curl does not enforce the browser's cross-origin read policy; it can fetch content even when the response lacks CORS headers. Also check whether the server actually rejected the request with Origin, since Spring's CORS processor can return 403 for disallowed origins.

The right solution is configuring allowed origins per business requirements. Do not casually open wildcards, enable credentials for all origins, or turn off API protection.

### 8.2. Browser works after login, curl gets 401

The browser may carry a session cookie or HTTP Basic credentials saved per policy. curl usually lacks the corresponding cookie/Authorization. Compare cookie jars, Authorization headers, scopes, expiry, and auth mechanisms. Do not copy real tokens into docs or logs when comparing.

### 8.3. curl receives JSON 401, browser sees login page

Form login can return a 302 redirect to the login page, the browser follows the redirect, and then displays HTML with final status 200. HTTP Basic/Bearer APIs typically return 401/challenge. Identify **AuthenticationEntryPoint**, Accept, endpoint matchers, and the final URL after redirects. A final HTTP status of 200 does not prove the initial request accessed the protected resource.

### 8.4. GET succeeds across all three, POST gets 403

This may be due to a **missing CSRF token** in an app using cookies/sessions or HTTP Basic with CSRF enabled; it could also be a missing role/permission. Inspect status, security logs, and Spring Security config. Do not rush to disable CSRF just because POST from curl or Postman returns 403.

### 8.5. Service has a token yet gets 403

The service's token may be valid yet have the wrong scope, audience, role, or object permissions. "Authenticated service" differs from "service authorized to perform every action." Re-check the target API's policy and the token type in use.

### 8.6. curl on a personal machine succeeds, service in cluster times out

This may be a difference in **DNS, proxy, egress firewall, service discovery, TLS/mTLS, certificate trust, or timeouts**. CORS is rarely involved. Inspect requests on each network, resolved hostnames, TLS handshakes, and gateway traces.

### 8.7. API returns 200 in Network, JavaScript still reports Failed to fetch

Network success does not mean JavaScript may read the response. The browser may block it due to CORS, mixed content, TLS, extension policies, or other connection issues. Read the **Console error**, inspect request/preflight and response headers; do not infer from status alone.

### 8.8. Real endpoint returns 404 when switching token or switching user

This may be due to hiding existence of resources not owned by the subject, gateway routing, a different URL, or non-existent data. Distinguish a routing 404 from an object-access-policy 404. Regardless of returning 403 or 404, the body must never leak someone else's data.

## 9. Authentication, authorization, and CORS belong at the right layers

| Mechanism | Who enforces it? | What does it decide? | Does not replace |
| --- | --- | --- | --- |
| **TLS/HTTPS** | Client and TLS endpoints | Protects connection, verifies certificates/peer per config. | Data access permissions and business logic. |
| **Authentication** | Trusted backend/API/gateway | Are credentials valid? Who is the identity? | Permissions on individual operations/resources. |
| **Authorization** | Backend/Service/domain | Which actions may this identity perform on which data? | Forged request controls or malicious input checks. |
| **CORS** | Browser enforces response-reading policy; server configures headers/accepted origins | Scripts from which origins may read cross-origin responses? | Authentication, authorization, CSRF, API firewall. |
| **CSRF protection** | Primarily server with corresponding browser client | Is a state-changing request an intentional action in session context? | Authentication, role checks, XSS defense. |
| **Rate limiting/quota** | Gateway/API/infra | Limits request volume and consumed resources. | Auth/permissions and data validation. |
| **Service identity/mTLS** | Services and trusted infra | Which machine/service is calling? How is the inter-service channel verified? | User/tenant permissions and business rules. |

A common mistake is seeing Access-Control-Allow-Origin and thinking "this API only allows calls from this website." In reality, browsers only restrict scripts from reading data under origin policy; curl/services usually face no such restriction. If data needs protection, **the server must require proper identity and permissions** regardless of the HTTP client source.

At the same time, do not treat every browser request as trustworthy: input validation, object-level authorization, anti-CSRF, CSP/XSS prevention, file upload controls, and auditing remain necessary.

## 10. Workflow to debug the same API across three clients

To compare systematically, gather info in the following order.

**Step 1 — Confirm target request.** Compare scheme, host, port, path, query, method, and environment. A URL that looks identical may traverse different DNS/proxies.

**Step 2 — Compare credentials.** Does an Authorization header exist (mask its value), are cookies sent, and which principal and scopes/roles are authenticated on the server? Do not take a browser session and assume curl shares the same permissions.

**Step 3 — Distinguish main request and preflight.** In DevTools, treat OPTIONS and GET/POST as two separate requests. When OPTIONS fails, there may be no business request in logs yet.

**Step 4 — Read both status and headers.** Inspect Location, WWW-Authenticate, Access-Control-Allow-Origin, Access-Control-Allow-Credentials, Set-Cookie, Content-Type, Cache-Control, and relevant gateway headers. Check the final URL if redirected.

**Step 5 — Correlate timestamps and correlation IDs.** Use request IDs to search gateway/API logs; never log raw Authorization or Cookies. If the browser reports errors yet the backend has no logs, check preflight, TLS, DNS, proxy, or client policy.

**Step 6 — Test object-level permissions and side effects.** A 200 request with another user's body is still a bug; a POST returning 403 after mutating the DB is still a bug. Ensure denied requests cause no unauthorized effects.

**Step 7 — Check environment-specific policies.** Compare localhost, staging, and production variants, frontend origins, reverse proxies, trusted forwarded headers, management ports, and which Spring SecurityFilterChain matches.

Use a short diagnostic table:

| Characteristic | Browser | curl | Service |
| --- | --- | --- | --- |
| Actual method + URL | Record from Network | Record from -v/-i | Record from HTTP client diagnostics |
| Origin/preflight | May be auto-generated | Only present if explicitly sent | Only present if code/framework sends it |
| Credential | Cookie/Basic/Bearer per policy | Supplied header/cookie | Service token/delegated token per code |
| Response status | Distinguish network status from fetch-access error | Printed directly | Status/exception per client |
| Data & side effects | Check Network and UI | Check body | Check body + downstream state |

Never capture, paste, or share raw tokens, passwords, session cookies, client secrets, or customer data when recording evidence.

## 11. Testing across three clients and security expectations

On the same API, use multiple identities and HTTP client types to verify different properties:

| Test case | How to call | Expectation to verify |
| --- | --- | --- |
| Anonymous GET private | curl without credentials | 401/challenge or corresponding entry point policy. |
| Browser fetch from allowed origin | fetch + valid auth | Preflight (if needed) succeeds, response is readable. |
| Browser fetch from disallowed origin | fetch + different origin | Script cannot read response; actual request may not be sent if preflight fails. |
| curl without Origin but valid auth | curl -u / Bearer | Evaluated by server authn/authz; CORS is not an "API lock." |
| Regular user calls admin function | Any client with USER credentials | Denied by authorization, no side effects. |
| POST missing CSRF token on session endpoint | Browser or curl | Denied when CSRF protection applies. |
| Service token with wrong audience | Java HTTP client | Rejected by server; do not forward mis-targeted tokens. |
| User A reads User B's resource | Browser, curl, or service delegated for A | Does not receive B's data even though request is valid HTTP. |
| Retried transaction-creating request | Service client | Does not create duplicate effects if business logic requires idempotency. |
| API error through gateway | curl inside pod / separate host | Isolate DNS, TLS, proxy, timeout, upstream status. |

Tests for credentials, URLs, CSRF, and CORS must use **the exact mechanism the endpoint actually supports**. Do not assume every REST API uses Bearer or every browser uses session cookies.

## 12. Misconceptions to eliminate

1. **"curl succeeds, so CORS is broken or security is missing."** Curl does not enforce browser CORS; authn/authz must still be checked on the server.
2. **"Only website A can call the API because Allow-Origin is A."** Allow-Origin restricts JavaScript's ability to read responses in browsers, not other HTTP clients from sending requests.
3. **"POST 403 error definitely means missing role."** It may be CSRF, another policy, or access control. Read logs/filters and the actual request.
4. **"Just add credentials: include to log in."** Fetch does not create sessions/tokens; cookies still depend on policy, server, and login state.
5. **"Origin and User-Agent are trustworthy proof of request source."** Outside browsers they can be spoofed. Do not use them as user identity.
6. **"Internal services don't need authentication or authorization."** An internal network does not replace service identity, scopes, audience, and data permissions.
7. **"HTTP Basic uses Base64 so passwords are encrypted."** Base64 is trivially decoded; HTTPS and proper secret management are required.
8. **"Using curl means the server skips CSRF checks."** If the CSRF filter applies to the request, curl missing a token can also receive 403.
9. **"Network shows 200 means fetch succeeded."** The response may be blocked from reading by the browser due to CORS or another policy.
10. **"302 then 200 means the API call succeeded."** The 200 status may belong to the login page after redirect, not the requested resource.
11. **"X-Forwarded-For guarantees the real IP."** The header is only trustworthy when managed by trusted proxies per architecture.
12. **"With JWT, every service can share one token."** Tokens must be issued for the right audience/scope and passed across trust boundaries by design.

## 13. Self-assessment exercises

**Exercise 1.** A web frontend runs on http://localhost:3000, the API on http://localhost:8080. GET with valid Authorization returns 200 to curl, yet fetch reports a CORS error. Write down the steps to check whether the browser sends OPTIONS and which header the response is missing. Explain why you must not solve it by removing authentication.

**Exercise 2.** A browser is logged in and accesses /api/me successfully. curl to the same URL returns 401. Name at least three pieces of information to compare in the request (suggested answers: Cookie, Authorization, host/domain/path, redirect/login entry point).

**Exercise 3.** Using the demo API, prove with curl that GET private requires credentials, POST actions without CSRF gets 403, and OPTIONS preflight is not a data-mutating action. Observe status alongside the necessary response headers.

**Exercise 4.** Write a service client sending a token issued for service B to service C's API. By security design, what needs verification? (Hint: audience, issuer, expiry, scope, subject, per-resource permissions; do not blindly forward tokens between services.)

**Exercise 5.** User A has a valid session and uses a browser, curl, and service delegation to read B's order ID. Although all three clients use HTTP differently, which security property must be preserved? (Hint: object-level authorization and zero leakage of B's data.)

### Closing checklist

- Can you distinguish **origin** from **site** and **CORS** from **authorization**?
- Do you view **OPTIONS preflight** requests separately from business requests?
- Do you know which clients auto-send **cookies** and which must explicitly attach credentials?
- Can you explain why 401/403/302 appear differently when the **authentication entry point** or cookies/sessions differ?
- Do you know a service needs tokens with the right **audience/scope**, TLS, and outbound restrictions?
- Can you prove with tests that an unauthorized request **causes no side effects** and leaks no data?

## Conclusion

Browsers, curl, and backend services all make HTTP calls yet differ in security environment, credential management, cookies, preflight, redirects, TLS, and network paths. Browsers apply SOP/CORS to JavaScript; curl crafts requests explicitly; backend services must manage identities and inter-system connections. **Spring Security and the business layer still must authenticate, authorize, and protect data for every client.** When the same API behaves differently, compare actual requests, distinguish browser-policy errors from server responses, and verify security decisions with reproducible tests.
