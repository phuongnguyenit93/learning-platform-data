# Configuring CORS for Management Endpoints Accessed From a Browser

## 1. What Problem Does CORS Solve?

An admin page at `http://127.0.0.1:5173` needs to read `http://127.0.0.1:8080/actuator/health`. The server may be running and credentials may be valid, yet JavaScript still cannot read the response because the two addresses have different origins. CORS (Cross-Origin Resource Sharing) allows the server to declare which browser origins are permitted to read the response.

In management infrastructure, first determine whether cross-origin calls are truly needed, which endpoints are exposed over HTTP, and who is authorized to call them, then configure CORS narrowly for the admin page. Adding an origin to CORS does not grant a user an account or role.

This lesson uses **Spring Boot 3.3.13, Java 21, Spring MVC/Servlet, and the bundled Spring Security**. This is the fixed version for the experiment, not a claim about the latest release. Actuator's CORS property group also works with WebFlux; the `HttpSecurity` code in this lesson is Servlet-only. Reactive applications must use the corresponding security API.

## 2. Identifying the Calling Page's Origin Accurately

For typical HTTP/HTTPS URLs, an origin consists of **scheme + host + effective port**; the path does not participate in the comparison. Taking server origin `http://127.0.0.1:8080` as the baseline:

| Page Address Currently Open | Relationship to Server Origin |
| --- | --- |
| `http://127.0.0.1:8080/admin/index.html` | Same origin, even though the path differs |
| `http://127.0.0.1:5173` | Different port, different origin |
| `http://localhost:8080` | Different host, different origin |
| `https://127.0.0.1:8080` | Different scheme, different origin |

`allowed-origins` contains the **calling page's origin**, such as `http://127.0.0.1:5173`, not the target endpoint URL, `/admin`, `/actuator/health`, or a trailing `/`. `localhost` and `127.0.0.1` both point to the current machine yet are still two different hostnames. The origin concept is defined in [RFC 6454](https://www.rfc-editor.org/rfc/rfc6454#section-3.2).

Enable CORS only when a browser needs to make cross-origin calls. A page served from the same origin calling relative path `/actuator/health` does not need another origin opened for that case. Prometheus, server-side applications, and `curl` are not subject to browser read-blocking; they remain subject to authentication, authorization, TLS, and network restrictions.

## 3. How Does CORS Relate to Actuator Security?

| Control Layer | Question It Must Answer | Example in This Lesson |
| --- | --- | --- |
| Enable/expose endpoint | Does the endpoint exist and is it mapped over HTTP? | Expose only `health` |
| Network and TLS | Can the caller reach the right address, port, and certificate? | Demo listens only on loopback |
| Authentication/authorization | Which identity is allowed to execute the actual request? | Role `ACTUATOR_READ` |
| CORS | JavaScript from which origin is allowed to read the response? | Only port `5173` origin |

`management.endpoints.web.exposure.include` does not replace security configuration. When declaring your own `SecurityFilterChain`, the application must ensure appropriate access rules itself, because related security auto-configuration backs off. See [Boot 3.3 Actuator endpoints and security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Do not use CORS as a firewall: programs outside a browser can omit or spoof the `Origin` header. A CORS error in the browser console also does not prove the request never reached the server. Some requests are sent before the browser decides whether JavaScript may read the response; state-changing operations still require their own protections, including CSRF when appropriate.

## 4. Understanding Preflight Before Configuring

Browsers do not send `OPTIONS` before every `GET`. When a request qualifies for direct sending, the browser may send the actual request immediately. When JavaScript explicitly adds `Authorization`, the browser usually requires a preflight request first, unless a matching cached result is still valid.

Flow of the authenticated experiment:

1. The page on port `5173` wants to send `GET /actuator/health` with `Authorization`.
2. The browser sends `OPTIONS` to the endpoint with `Origin`, `Access-Control-Request-Method: GET`, and `Access-Control-Request-Headers: authorization`.
3. The server checks the origin, the method **intended for the actual request**, and the requested headers, returning allow headers if valid.
4. The browser sends `GET` with credentials; Spring Security checks identity and roles.
5. The `GET` response must also carry matching CORS headers so JavaScript can read it.

Preflight does not carry the actual request's password/token. If the security layer requires login immediately on `OPTIONS`, the browser can never reach the `GET` step. Adding `permitAll()` for `OPTIONS` alone also does not produce CORS headers. CORS must be integrated into the security chain so it runs before authentication. See [Spring Security: CORS integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).

`allowed-methods: GET` refers to the method of the actual request. You do not add `OPTIONS` just to serve preflight for `GET`; adding `OPTIONS` also does not make `POST` valid.

## 5. Actuator's CORS Property Group

The configuration group is **`management.endpoints.web.cors`**. When no origin is declared via `allowed-origins` or `allowed-origin-patterns`, Actuator CORS support is not yet enabled. For a few known admin pages, prefer an explicit origin list.

| Property Under `management.endpoints.web.cors` | Meaning | Choice for Example |
| --- | --- | --- |
| `allowed-origins` | Origin of the calling page | `http://127.0.0.1:5173` |
| `allowed-methods` | Actual request methods accepted | `GET` |
| `allowed-headers` | Request headers accepted during preflight check | `Authorization` |
| `exposed-headers` | Additional response headers JavaScript is allowed to read | None needed |
| `allow-credentials` | Allows response to be used with browser automatic credential sending mode | `false` |
| `max-age` | Duration for which preflight results may be cached | `10m` |

Property names and types are described in the [Boot 3.3 property table](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator.management.endpoints.web.cors.allowed-origins); the configuration binding class is [CorsEndpointProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/CorsEndpointProperties.html).

Do not confuse the two header directions: letting JavaScript **send** `Authorization` requires `allowed-headers`; letting it **read** a custom response header like `X-Trace-Id` involves `exposed-headers`. `exposed-headers` does not generate that header itself. That the server returns JSON does not require a `GET` request to send `Content-Type: application/json`; avoid adding unnecessary headers that trigger preflight.

These properties set a common policy for Actuator web endpoints, not per-endpoint authorization, and they do not automatically configure CORS for business controllers. Do not assume `@CrossOrigin` on controllers or controller CORS configuration handles Actuator. If different policies are needed per endpoint, design separate mapping scopes and verify against the security chain—avoid opening all of `/**` just for testing.

## 6. Standalone Example: Authenticated Health Read

This is a standalone hands-on project and does not require modifying the build of the module being studied. Requires JDK 21, Maven 3.6.3 or newer, and internet access to download libraries on the first run. Check `mvn -version` to ensure Maven is using Java 21.

Experiment design:

- Server at `http://127.0.0.1:8080`, exposing only `health`, without returning health details.
- Test page at `http://127.0.0.1:5173`; other origins are not in the list.
- Actual request uses HTTP Basic with account `operator`, role `ACTUATOR_READ`.
- JavaScript explicitly sets `Authorization` and uses `credentials: "omit"`, not relying on cookies or browser-attached credentials.
- Keeps default CSRF, performing only `GET` read operations.

HTTP Basic lets the small experiment run standalone. Basic strings are only Base64-encoded, not secure encryption. Run this plain HTTP only on loopback; over a network, use HTTPS and proper identity management. The hands-on page accepts only ASCII usernames and passwords for direct `btoa` encoding.

### 6.1. Directory Structure

```text
actuator-cors-demo/
├── pom.xml
├── src/main/java/example/
│   ├── CorsDemoApplication.java
│   └── ManagementSecurity.java
├── src/main/resources/application.yml
└── ui/index.html
```

### 6.2. `pom.xml`

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
  <groupId>example</groupId>
  <artifactId>actuator-cors-demo</artifactId>
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
```

The three starters provide HTTP Servlet, management endpoints, and security. No replacement controller is needed for `health`. The parent manages dependency versions and the Boot plugin packages an executable JAR; see [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/getting-started.html).

### 6.3. `src/main/java/example/CorsDemoApplication.java`

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

### 6.4. `src/main/java/example/ManagementSecurity.java`

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurity {
    @Bean
    SecurityFilterChain managementAccess(HttpSecurity http) throws Exception {
        http.cors(Customizer.withDefaults());
        http.authorizeHttpRequests(rules -> rules
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR_READ")
                .anyRequest().denyAll());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

`EndpointRequest.toAnyEndpoint()` matches Actuator endpoints according to Boot's mappings. `hasRole("ACTUATOR_READ")` checks authority `ROLE_ACTUATOR_READ`; `spring.security.user.roles` below omits the `ROLE_` prefix. The demo denies all requests outside Actuator; a real business application needs dedicated rules for its own paths.

`http.cors(Customizer.withDefaults())` lets Spring Security use CORS configuration from Spring MVC mappings when no other CORS source is provided. Valid preflights can thereby be handled before authentication. If the project already has a `CorsFilter`, `CorsConfigurationSource`, or multiple `SecurityFilterChain` beans, determine which configuration and chain are actually selected; do not assume adding one line overrides every existing policy.

The example shares the application port and management port. When configuring a separate `management.server.port`, test against the actual management server/context; a filter chain on the business server does not prove the management server is properly protected.

### 6.5. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  security:
    user:
      name: operator
      password: ${ACTUATOR_PASSWORD}
      roles: ACTUATOR_READ

management:
  endpoint:
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include:
          - health
      discovery:
        enabled: false
      cors:
        allowed-origins:
          - "http://127.0.0.1:5173"
        allowed-methods:
          - GET
        allowed-headers:
          - Authorization
        allow-credentials: false
        max-age: 10m
```

`ACTUATOR_PASSWORD` is supplied via the environment. Do not put real passwords into YAML or page code. Expose only `health`; there is no need to use `exposure.include: "*"` to test CORS. Disabling discovery keeps the experiment focused on the health URL.

`allow-credentials: false` does not make the endpoint public: Spring Security still requires valid Basic auth. Explicitly attached auth headers are checked via `allowed-headers`. Deciding to send cookies/automatic credentials is a separate issue explained in section 8.

### 6.6. `ui/index.html`

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Read health over CORS</title>
</head>
<body>
  <h1>Authenticated health check</h1>
  <form id="reader">
    <label>Username
      <input name="username" value="operator" required>
    </label>
    <label>Lab password
      <input name="password" type="password" autocomplete="off" required>
    </label>
    <button type="submit">Read health</button>
  </form>
  <pre id="result" aria-live="polite"></pre>
  <script>
    const form = document.getElementById("reader");
    const result = document.getElementById("result");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const username = form.elements.namedItem("username").value;
      const password = form.elements.namedItem("password");
      result.textContent = "Reading...";
      try {
        const basic = btoa(username + ":" + password.value);
        const response = await fetch("http://127.0.0.1:8080/actuator/health", {
          credentials: "omit",
          headers: { Authorization: "Basic " + basic }
        });
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        result.textContent = JSON.stringify(await response.json(), null, 2);
      } catch (error) {
        result.textContent = error.message;
      } finally {
        password.value = "";
      }
    });
  </script>
</body>
</html>
```

The page does not embed passwords in code, does not save passwords in `localStorage`, and clears the password input after each call. `response.ok` is checked because `fetch` does not reject on HTTP `401` or `403`. This is a practice page, not a complete production admin portal.

### 6.7. Running the Server and Page

At the hands-on project root, open PowerShell and enter a dedicated ASCII password for this test:

```powershell
$labPassword = Read-Host 'Enter ASCII password for this test' -AsSecureString
$env:ACTUATOR_PASSWORD = [System.Net.NetworkCredential]::new('', $labPassword).Password
mvn -q -DskipTests package
java -jar target/actuator-cors-demo-1.0.0.jar
```

Run the JAR only after Maven packages successfully. The app has external libraries, so do not use bare `javac` in place of dependency resolution. You can use `mvn spring-boot:run` instead of packaging and running the JAR.

Open a second terminal in the same directory, using JDK 21's static file server tool:

```powershell
jwebserver -b 127.0.0.1 -p 5173 -d ui
```

Open **`http://127.0.0.1:5173/`** specifically, enter the same password, and click **Read health**. Do not open via `file://` and do not switch to `localhost` during this test. `jwebserver` serves only the `ui` directory, not the project root containing configs; see [JDK 21 jwebserver documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jwebserver.html).

When the app is healthy, the page displays:

```json
{
  "status": "UP"
}
```

This is the endpoint payload, not the full Spring Boot startup stdout. If the environment changes health status, inspect the HTTP status and actual data—do not treat every non-`UP` result as a CORS error. Stop both processes with `Ctrl+C`; after stopping the server, you can remove the environment variable in that terminal with `Remove-Item Env:ACTUATOR_PASSWORD`.

## 7. Verifying Both Preflight and Actual Requests

The table below applies to the unmodified demo, healthy endpoint, and shared port `8080`:

| Case | Result to Verify | Meaning |
| --- | --- | --- |
| Preflight from origin `5173`, requesting `GET` and `authorization` | `200`, with matching CORS headers | CORS accepts the proposal; does not prove valid login |
| `GET` from origin `5173`, valid Basic auth and right role | `200`, health JSON and origin-allow header for `5173` | Both CORS and security pass |
| `GET` from origin `5173`, no authentication | `401`, still includes origin-allow header for `5173` | CORS is valid, identity is missing |
| Preflight from origin `5174` | `403`, no allow header for that origin | Origin rejected |
| Preflight from origin `5173`, requesting `POST` | `403` | Policy permits only actual method `GET` |
| Preflight requesting only `x-admin-debug` | `403` | None of the requested headers are allowed |
| Preflight requesting `authorization,x-admin-debug` | May return `200` but allows only `authorization` | Browser blocks actual request because not all requested headers were allowed |
| `GET` without `Origin`, valid Basic auth | `200` when endpoint is healthy | Non-browser tools do not need CORS to read |

### 7.1. Testing Preflight Without a Password

In PowerShell on Windows, use `curl.exe` to avoid the alias. Each command below is on a single line:

```powershell
curl.exe -i -X OPTIONS "http://127.0.0.1:8080/actuator/health" -H "Origin: http://127.0.0.1:5173" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
```

Compare these parts of the response:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: http://127.0.0.1:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 600
```

These are the values to verify. Header order/casing, status line, and additional headers may differ by server. Do not expect `Access-Control-Allow-Credentials: true` because the demo disables it. `10m` is represented as `600` seconds in the header.

Test a rejected origin:

```powershell
curl.exe -i -X OPTIONS "http://127.0.0.1:8080/actuator/health" -H "Origin: http://127.0.0.1:5174" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
```

With origin `5174`, the default processor returns `403` with body `Invalid CORS request`. Keeping the right origin and changing the requested method to `POST` is also rejected. When requesting only header `x-admin-debug`, none of the requested headers are accepted so Spring returns `403`. Default rejection behavior is documented at [DefaultCorsProcessor](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/cors/DefaultCorsProcessor.html).

**Do not look only at the `200` status of preflight.** With the mixed list `authorization,x-admin-debug`, in the demo config Spring returns `200`, yet `Access-Control-Allow-Headers` contains only `authorization`. The browser checks the full requested list, sees `x-admin-debug` missing, and refuses to send the actual request. This is the difference between the server returning HTTP and the browser completing the CORS check. Only add headers when genuinely needed; do not widen policy to make negative tests succeed.

### 7.2. Testing Actual Requests and Authentication Errors

`curl.exe --user operator` prompts for the password without putting it on the command line:

```powershell
curl.exe -i --user operator "http://127.0.0.1:8080/actuator/health" -H "Origin: http://127.0.0.1:5173"
```

When entered correctly, you should see `200`, header `Access-Control-Allow-Origin: http://127.0.0.1:5173`, and JSON `{"status":"UP"}` if the app is healthy. Omit `--user operator` and rerun to verify `401`; the CORS header on this error lets the page see the auth failure rather than masking it as a response-read failure.

Next, omit `Origin` while keeping authentication:

```powershell
curl.exe -i --user operator "http://127.0.0.1:8080/actuator/health"
```

`curl` can still read the response. Origin restrictions do not replace identity verification. `curl` only checks HTTP and does not run the browser CORS algorithm; a successful `curl` test does not prove JavaScript works.

### 7.3. Inspecting Browser Network Activity

On the first button click you usually see `OPTIONS` followed by `GET`. If preflight is still cached, you may see only `GET`; use a fresh browser session or wait for the cache to expire when you need to observe it again. Do not manually call `fetch` with `method: "OPTIONS"` to substitute for browser-controlled preflight.

In `OPTIONS`, check URL/port, `Origin`, requested method, and requested headers. In `GET`, check status and the origin-allow header. JavaScript cannot set `Origin` itself to spoof another origin; to test in a browser, serve the page on another port. Do not share Network screenshots containing `Authorization`.

## 8. When Cookies, Login Sessions, or Tokens Are Needed

### 8.1. Sending Cookies Cross-Origin

Only when login truly relies on cookies/automatic credentials should you consider `credentials: "include"` in `fetch` and `allow-credentials: true` in Actuator. In that mode you must return a specific origin matching the request; do not use `allowed-origins: "*"`. Spring checks this combination and can fail when initializing or using the configuration. See [Spring Framework 6.1 CorsConfiguration](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/cors/CorsConfiguration.html).

The YAML below only illustrates CORS policy for a page that **already** has cookie-based login; it does not create sessions, cookies, or a login API:

```yaml
management:
  endpoints:
    web:
      cors:
        allowed-origins:
          - "https://ops.example.com"
        allowed-methods:
          - GET
        allow-credentials: true
        max-age: 10m
```

A logged-in page can call:

```javascript
const response = await fetch("https://management.example.com/actuator/health", {
  credentials: "include"
});
if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
const health = await response.json();
```

This is an integration snippet and does not replace the entire section 6 demo. Browsers also enforce `SameSite`, `Secure`, and third-party cookie blocking; valid CORS alone does not guarantee cookies are sent. `SameSite` evaluates site relationship while CORS evaluates origin: different ports can be different origins yet still the same site. Do not disable CSRF globally to fix cookie issues.

### 8.2. JavaScript Explicitly Attaching Tokens

With `Authorization: Bearer ...`, allow the `Authorization` header, verify token authentication on the server, and keep endpoint authorization. Having a token header alone does not require setting `allow-credentials` to `true`; evaluate the `credentials` mode and whether cookies/automatic credentials are used.

The section 6 demo explicitly attaches Basic auth with `credentials: "omit"` to keep those two decisions separate. Do not generalize this into advice to store long-lived admin tokens in page code or browser storage. Credentials mode and headers are defined in the [Fetch Standard, CORS section](https://fetch.spec.whatwg.org/#http-cors-protocol).

### 8.3. Origin Patterns and Wildcards

`allowed-origin-patterns` allows more flexible patterns than `allowed-origins`. For management, a pattern like `https://*.example.com` is only suitable when every matching subdomain is trusted; a single compromised subdomain can make the policy overly broad. Do not use `"*"` as a pattern to bypass the wildcard rule when credentials are enabled. A few explicit origins are usually easier to audit.

## 9. Separate Management Port and Proxies

If you move Actuator to `management.server.port: 9090`, the page's target URL must change to the actual management server. The allowed origin remains the **page's origin**, not `http://127.0.0.1:9090` just because the server changed ports. Recheck bind address, TLS, paths, firewall, and security chain of the management server specifically.

Browsers evaluate visible URLs. If a proxy serves both the page and `/management/health` on the same scheme, host, and port, the page can use relative paths even if the proxy calls Java internally on another port. Protect the proxy route and access permissions; do not open CORS for internal communication just because two processes use different ports.

Choose clearly where CORS headers are added. Both the proxy and the application adding `Access-Control-Allow-Origin` can create duplicate headers or malformed origin lists. If a proxy/cache stores responses varying by `Origin`, preserve `Vary` and proper cache partitioning to avoid serving one origin's response to another origin.

An HTTPS page calling an HTTP endpoint can also be blocked due to mixed content. DNS, TLS certificates, and CSP `connect-src` can also block connections; these are separate layers to inspect, not problems solved by adding `allowed-origins`.

## 10. Troubleshooting Common Errors

| Symptom | Check First | Appropriate Fix |
| --- | --- | --- |
| `curl` can read, JavaScript cannot | Did the test command have `Origin`? What is the page's real origin? | Test in a browser and inspect response headers |
| Preflight returns `401` or redirects to login | Which security chain handles `OPTIONS`, and is CORS integrated there? | Handle CORS before auth; avoid redirecting preflight to login |
| `GET` returns `401`, CORS is right | Actual credentials | Fix login/token; do not broaden origins |
| `GET` returns `403` after auth | Roles, permission rules; CSRF for write operations | Find the exact rejecting layer; do not treat every `403` as CORS |
| Origin rejected | `localhost`/`127.0.0.1`, port, scheme, trailing path | Declare the exact calling page origin |
| Header rejected | `Access-Control-Request-Headers` list in Network | Add only genuinely needed headers or drop extra ones |
| Preflight passes, actual request fails | Actual status/headers, proxy, authentication | Inspect both responses |
| Endpoint returns `404` | Exposure, base path, port, and proxy route | Verify HTTP mapping; security/proxies can also use `404` to hide paths |
| `file://` page has origin `null` | How the page was opened | Serve over loopback HTTP; do not allow `null` origin just to test |
| Edited YAML yet seeing old result | Application restart, preflight cache | Verify active config and test in a fresh browser session |
| Origin-allow header has multiple values | Are both proxy and app adding the header? | Keep policy in one place; do not concatenate multiple origins in one header |

Do not use `mode: "no-cors"` to fix errors: opaque responses do not let JavaScript read JSON as this lesson requires. Do not install extensions disabling browser protections, sprinkle `@CrossOrigin("*")` everywhere, or expose all endpoints just to make the error disappear.

## 11. Practice Exercises

1. Run the demo and confirm both valid preflight and authenticated `GET` succeed. Explain why `OPTIONS` does not need a password while `GET` still does.
2. Serve the page on port `5174`, keeping YAML unchanged. Predict, then observe Network. Add the new origin only after confirming it is a legitimate requirement.
3. Keep the right origin but enter a wrong password. Distinguish HTTP `401` from the browser blocking response reads due to CORS.
4. Request `POST`, then only `x-admin-debug`, then `authorization,x-admin-debug`. Distinguish Spring's `403` from the `200` case where a missing allowed header stops the browser from sending the actual request. Keep the policy unchanged during these tests.
5. Describe a design putting both the page and management route on the same origin behind a proxy. Specify which authentication/authorization layers must still exist.

Self-check: why must you declare the page origin instead of the endpoint URL; why does a passing preflight not prove invocation permission; how does `allowed-headers` differ from `exposed-headers`; and when is `allow-credentials: true` actually needed?