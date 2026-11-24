# Distinguishing origin, site, hostname, and path

## Learning objectives

When securing a Spring application, developers frequently encounter the terms *origin*, *site*, *hostname*, *domain*, and *path*. These words describe different scopes of a URL. Confusing them can lead to overly broad CORS configurations, misunderstanding cookie transmission scope, disabling CSRF for the wrong reasons, or assuming two endpoints at different paths are already security-isolated by the browser.

After this lesson, you will be able to:

1. Break a URL down into **scheme, hostname, port, path, query, and fragment**.
2. Compare **same-origin**, **same-site**, and **same-hostname** with concrete examples.
3. Explain the role of the **Public Suffix List** in determining a *site*, along with the impact of scheme and port.
4. Analyze the relationship between **Same-Origin Policy, CORS, cookie Domain/Path/SameSite, and CSRF**.
5. Distinguish browser URL boundaries from **API authorization in Spring Security**.
6. Use Java 17 to inspect URL components and configure Spring Boot/Spring Security intentionally.

**Context:** modern browser/HTTP concepts, Spring MVC running on Servlet, Java 17, and Spring Boot 3.x/Spring Security 6.x examples. When changing stacks or versions, check the corresponding APIs; the URL comparison principles here do not depend solely on Spring.

## 1. Dissecting a URL before discussing security

Consider the URL:

```text
https://api.shop.example.com:8443/v1/orders/42?view=detail#items
\___/   \__________________/ \__/ \____________/ \_________/ \___/
scheme        hostname      port      path        query     fragment
```

| Component | Value | Role |
| --- | --- | --- |
| Scheme | `https` | Indicates the protocol type and how to process the URL, including using HTTPS. |
| Hostname | `api.shop.example.com` | Server name in the URL (excluding scheme, port, path). |
| Port | `8443` | Port the client connects to; HTTP/HTTPS have default ports if omitted. |
| Path | `/v1/orders/42` | Resource path handled by the HTTP server/router. |
| Query | `view=detail` | Information after `?`; often used as search or filter parameters. |
| Fragment | `items` | Part after `#` handled by the user agent; **not sent in the HTTP request target** when making normal HTTP requests. |

Some related terms:

- **Host** in a URL is often used near-synonymously with hostname, but **host** should not be confused with **authority**. The authority in the example is `api.shop.example.com:8443`, consisting of hostname and port (general URLs can also include userinfo; avoid using userinfo for HTTP login).
- **Domain name** is a name in DNS; a URL's hostname may be a DNS name, an IP literal, or `localhost`. "Domain" also appears in the cookie `Domain` attribute and in public suffix rules, so the context must be stated accurately.
- **Origin** and **site** are two web security scope-comparison concepts derived from a URL; they are **not** standalone substrings in the address like path or query.
- **Path does not include query/fragment**. `/orders/42?mode=edit` and `/orders/42?mode=view` have the same path but different queries.
- Browsers and servers may normalize hosts, default ports, dots, percent-encoding, and dot segments differently from raw string inspection. Do not decide access permissions via naive URL string checks.

For example, `https://app.example.com/a` and `https://app.example.com/b` have two different paths, yet typically share the same **origin**, same **site**, and same hostname.

## 2. Four core concepts

### 2.1. Hostname: the host name the URL points to

In `https://api.example.com:8443/users`, the **hostname** is `api.example.com`.

A hostname **does not contain** scheme, port, path, query, or fragment. Subdomains are different hostnames:

- `app.example.com` and `api.example.com`: **different hostnames**.
- `app.example.com:443` and `app.example.com:8443`: **same hostname**, different ports.
- `http://app.example.com` and `https://app.example.com`: **same hostname**, different schemes.

DNS can map multiple hostnames to the same IP; conversely, one hostname can point to multiple IPs. **Sharing an IP does not create the same hostname, same origin, or same access rights.**

A hostname is not proof of user identity. Do not use the `Host` header, `X-Forwarded-Host`, or a hostname in a query parameter to determine role/ownership. Reverse proxy metadata may only be trusted when arriving through explicitly configured trusted proxies.

### 2.2. Origin: the scheme + host + effective port tuple

For a standard HTTP(S) URL with a *tuple origin*, the practical rule is:

```text
origin = (scheme, host, effective-port)
```

**Same-origin** holds when all three corresponding components match after proper normalization. Examples:

- `https://app.example.com/a` and `https://app.example.com/b`: **same-origin**.
- `https://app.example.com` and `https://app.example.com:443`: **same-origin**, because HTTPS defaults to port 443.
- `http://app.example.com` and `http://app.example.com:80`: **same-origin**, because HTTP defaults to port 80.
- `https://app.example.com` and `https://app.example.com:8443`: **cross-origin**, because the port differs.
- `https://app.example.com` and `https://api.example.com`: **cross-origin**, because the hostname differs.
- `http://app.example.com` and `https://app.example.com`: **cross-origin**, because the scheme differs.

Path, query, and fragment **do not participate** in determining origin. In browsers, the Same-Origin Policy uses origin as one of the key boundaries restricting how web pages/scripts access resources from another origin.

There are special cases such as `file:`, `data:`, sandboxed documents, opaque origins, and inherited origins. The tuple formula above is for **standard HTTP(S) URLs**; you should not use it on your own to emulate the browser's full origin algorithm for every scheme.

### 2.3. Site: scheme + registrable domain (schemeful site)

In modern web policy contexts such as `SameSite` cookies, **site** is typically defined as a *schemeful site*:

```text
site = (scheme, registrable domain)
```

The **registrable domain** is determined using the **Public Suffix List (PSL)**. For many ordinary domains, this is *eTLD+1* (the effective top-level domain plus one label registered by the owner).

Illustrative examples:

- `app.example.com` and `api.example.com` have registrable domain `example.com`; when both use `https`, they are **same-site** even though **cross-origin**.
- `example.co.uk` and `shop.example.co.uk` share registrable domain `example.co.uk`; you cannot simply take "the last two labels," because `co.uk` is a public suffix.
- `app.example.com` and `app.example.org` belong to two different registrable domains, so they are **cross-site**.
- `https://app.example.com` and `http://app.example.com` are **cross-site under schemeful site**, even though the hostname is identical.

**Port does not participate in site comparison.** Therefore `https://app.example.com:5173` and `https://app.example.com:8443` can be **same-site** yet **cross-origin**.

Site is not an authorization boundary for individual APIs. Two subdomains on the same site may be operated by two different systems, development teams, or providers; being *same-site* cannot automatically allow reading data or granting admin rights.

**Caution regarding PSL:** Certain hosting domains serving multiple customers have special public suffix rules. Computing site cannot be done safely just with `host.endsWith("example.com")` or splitting the hostname by dots and taking the last two labels. Do not write your own site checker to make authorization decisions; when web-standard handling is needed, use an algorithm/library backed by an up-to-date Public Suffix List.

`localhost`, IP literals, and some internal hostnames do not have a registrable domain in the public-domain sense. Browsers have specific handling rules; when testing locally, explicitly state scheme/hostname/port and test in the target browser, rather than casually assuming all internal hostnames are one site.

### 2.4. Path: resource path within an origin

In `https://app.example.com/admin/users`, the **path** is `/admin/users`.

- `/admin/users` and `/api/users` belong to the same origin if the scheme/hostname/port components match.
- Path is a key input for web routers, static resource handlers, reverse proxies, and Spring Security's `requestMatchers(...)` rules.
- Different paths **do not create a new origin**, nor do they create a new JavaScript sandbox or authentication boundary.
- Servers may treat path case sensitivity and trailing slashes differently; proxy, servlet container, and routing framework configurations can affect matching results.
- Query and fragment are not components for Spring Security to automatically infer URL authorization via manual string concatenation.

For example, a user logged into `/shop` is not automatically permitted to call `/admin` just because both paths share the same hostname. Access rights are still decided by **server policy**.

## 3. Quick comparison table: what is the same, what differs?

Take the base URL `https://app.example.com:443/dashboard`. Under standard HTTP(S) rules, compare:

| URL compared to base URL | Same hostname? | Same-origin? | Same-site? | Reason |
| --- | :---: | :---: | :---: | --- |
| `https://app.example.com/profile` | Yes | **Yes** | **Yes** | Only path changes; default port 443. |
| `https://app.example.com:8443/profile` | Yes | No | **Yes** | Different port; site ignores port. |
| `https://api.example.com/profile` | No | No | **Yes** | Different subdomain, same `https` and `example.com`. |
| `https://example.com/profile` | No | No | **Yes** | Different host, same registrable domain `example.com`. |
| `http://app.example.com/profile` | Yes | No | No | Different scheme; schemeful site also differs. |
| `https://app.example.org/profile` | No | No | No | Different registrable domain. |
| `https://evil-example.com/profile` | No | No | No | Having the substring `example` does not make it same-site. |
| `https://app.example.com:443/dashboard?tab=2#main` | Yes | **Yes** | **Yes** | Query and fragment do not participate in either comparison. |

Visualizing inclusion relationships in a normal HTTP(S) context:

```text
Same origin  =>  same hostname, same scheme, same effective port
             =>  same site under schemeful site

Same site    =>  NOT NECESSARILY same origin
Same hostname=>  NOT NECESSARILY same origin or same-site if scheme differs
Same path    =>  NOT NECESSARILY same hostname, origin, or site
```

There is no "same hostname is safer" rule in the sense of granting user permissions. Each comparison serves **different browser policies**.

## 4. Origin in Same-Origin Policy and CORS

### 4.1. Same-Origin Policy (SOP) controls browser-mediated access

Suppose a page runs at:

```text
https://app.example.com
```

That page invokes JavaScript:

```javascript
fetch("https://api.example.com/api/me");
```

This is a **cross-origin request**, even though both hosts share `example.com` and HTTPS. The browser enforces cross-origin policy when JavaScript wants to read the response; the API needs appropriate CORS if it wants to allow access from this origin.

SOP **does not** mean the browser is strictly barred from sending any cross-origin requests. Links, navigations, form submissions, images, and certain resources are allowed to load/send under separate rules. Precisely because cross-origin requests **can be sent**, CSRF protection remains relevant for authentication mechanisms relying on auto-attached cookies.

### 4.2. CORS compares *origin*, not *site*

When the browser sends `Origin`, the value looks like:

```http
Origin: https://app.example.com
```

Typically an origin value contains no path, query, or fragment. The API can allow a specific origin:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

For requests with credentials such as cookies and matching browser mechanisms, configure accordingly, for example:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

When sending credentials, `Access-Control-Allow-Origin: *` cannot be used for the browser to grant permission to read credentialed responses. CORS must be configured with an allowlist of truly needed origins. Do not reflect every `Origin` value into `Access-Control-Allow-Origin` without validation, as doing so can open read access to unintended websites.

**Some common points of confusion:**

- `https://app.example.com` and `https://api.example.com`: **same-site yet still cross-origin, requiring CORS** if scripts on app want to read responses from the API.
- `http://localhost:5173` and `http://localhost:8080`: different ports, so **cross-origin**, even though same hostname and generally same site in a local context.
- A request with an `Authorization` header explicitly set by JavaScript usually triggers a **CORS preflight** if cross-origin; the browser sends `OPTIONS` first to ask the server which methods/headers are allowed.
- CORS is a rule enforced by the browser when scripts access responses. `curl` or backend-to-backend clients **are not governed by CORS as an authorization mechanism**.
- Having valid CORS **does not** mean the user is logged in or allowed to view the resource. The API still needs its own authentication and authorization.

### 4.3. Why does port matter so much in local development?

A React/Vite app at `http://localhost:5173` calls a Boot API at `http://localhost:8080`:

```text
Frontend: http://localhost:5173
Backend : http://localhost:8080
            \________________/
               same hostname
```

This is **cross-origin because port 5173 differs from 8080**. Even if you switch the frontend to `http://127.0.0.1:5173`, the hostname now differs from `localhost`. Declare the **exact full browser origin**; `localhost`, `127.0.0.1`, HTTP/HTTPS, and port all need to be evaluated in full scope.

Example frontend sending a request:

```javascript
const result = await fetch("http://localhost:8080/api/me", {
  headers: { Authorization: "Basic " + credentialsBase64 },
  credentials: "include"
});
```

This is **illustrative code for CORS mechanics**, not a way to store passwords in a frontend. In a real application, never hardcode credentials in JavaScript or public source code. `credentials: "include"` is a required option when you want the browser to send certain credentials on cross-origin requests; it does not grant permissions by itself and does not bypass cookie SameSite rules or browser policies on third-party cookies.

## 5. Site, cookie Domain/Path/SameSite, and CSRF

### 5.1. Cookies are not sent based solely on same-origin

The browser decides whether to send a cookie on a request based on multiple attributes: host/domain, path, Secure, SameSite, lifetime, partitioning when applicable, request type, and privacy policies.

Example server response:

```http
Set-Cookie: SESSION_ID=opaque-value; Secure; HttpOnly; Path=/; SameSite=Lax
```

Explanation:

- **No `Domain`**: the cookie is **host-only**, usually only sent back to the hostname that set it, not automatically opened to all subdomains.
- **`Domain=example.com`** (if valid): may allow sending the cookie to `example.com` and matching subdomains; not a safe default if sharing is unnecessary.
- **`Path=/`**: the cookie can be sent for matching request paths within the allowed host/domain scope; `Path=/admin` generally narrows cookie *sending* by path but **does not create an absolute security boundary between paths**.
- **`Secure`**: the cookie is restricted to secure connection contexts per browser rules; should be used with HTTPS in production. Browsers have some exceptions/special behaviors for localhost.
- **`HttpOnly`**: blocks direct reading via `document.cookie`, but does not stop the browser from auto-sending the cookie with requests and does not replace XSS defense.
- **`SameSite=Lax`**: restricts some cross-site cookie-sending scenarios, yet still has exceptions, such as top-level navigations using safe methods. Do not treat Lax as complete CSRF protection for all flows.
- **`SameSite=Strict`**: more restrictive for cross-site contexts; can affect redirect/login flows.
- **`SameSite=None; Secure`**: configuration supporting cases where cookies must be sent in cross-site contexts per modern standards; browsers or third-party cookie policies may still block them.

**Distinguish "browser allowed to send cookie" from "JavaScript allowed to read response":** cookies are evaluated by Domain/Path/SameSite/Secure and browser credentials mode; cross-origin response-reading permission is governed by SOP/CORS. They are not the same check.

### 5.2. Cookie Domain can span multiple origins, but should not be shared recklessly

Example:

```text
https://app.example.com
https://api.example.com
https://blog.example.com
```

These three hostnames may be **same-site**, yet they are **three distinct origins**. A cookie with `Domain=example.com` has a broader scope than a host-only cookie at `api.example.com`. If one subdomain is compromised, a broad cookie domain configuration increases the risk surface. Therefore, prefer host-only session cookies unless there is a genuine sharing requirement.

Where appropriate, the `__Host-` cookie prefix is used by supporting browsers to enforce key constraints: `Secure`, `Path=/`, and **no `Domain`**. This reduces the risk of cookies inadvertently spanning hosts. Cookie names/prefixes do not replace session management, HTTPS, or XSS/CSRF defenses.

You cannot use `Domain=co.uk` or other public suffixes to share cookies across all sites; browsers enforce public suffix rules. This illustrates why PSL matters more than manual hostname splitting.

### 5.3. Same-site does not mean same-origin, much less trustworthy

A page at `https://blog.example.com` and the API `https://api.example.com` may be **same-site**. Yet they are **cross-origin**; browsers still apply CORS to restrict response reading from JavaScript.

If a subdomain is hijacked or hosts arbitrary user-posted content, requests to an API on the same site can still carry cookies depending on cookie attributes and browser rules. **SameSite cookies are not enough to decide who may perform an operation**; the API should verify CSRF on vulnerable flows, along with user permissions on the server.

### 5.4. CORS is not an anti-CSRF mechanism

Separate the goals:

| Question | Relevant mechanism |
| --- | --- |
| Can a script on origin A **read the response** from origin B? | **Same-Origin Policy and CORS**. |
| Is the session cookie **sent** in the request? | Cookie host/domain/path, Secure, SameSite, browser credentials mode, and browser policies. |
| Did a state-changing request truly originate from an intentional user action? | **CSRF protection**, combined with authentication architecture and other layers. |
| Is the logged-in user allowed to change account X's balance? | **Server-side authorization** by user, resource, tenant, and business rules. |

For example, a form from another website can send a `POST` request to the application if the browser permits. The attacker **not being able to read the response** does not mean the request had no effect. With auto-attached session cookies, CSRF risk must be evaluated. Spring Security Servlet enables CSRF protection by default for state-changing HTTP methods. When building stateless APIs, only adjust CSRF based on how credentials are actually sent, not solely on the claim "CORS is configured."

## 6. Spring Security evaluates path for authorization, CORS evaluates origin for browser access

Suppose an API has three route groups:

```text
/public/**   : public access allowed
/api/**      : authentication required
/admin/**    : ADMIN role required
```

This is a **path and user permission** policy. It is completely different from allowing only the frontend page at `http://localhost:5173` to read cross-origin responses from the backend at `http://localhost:8080`.

| Scenario | Relevant mechanism | Correct reasoning |
| --- | --- | --- |
| `GET /public/ping` on API | Spring Security URL authorization | Can be `permitAll()`. |
| `GET /api/me` without credentials | Spring Security authentication | Denied/challenged per login mechanism. |
| `GET /admin/reports` with regular USER | Spring Security authorization | Lacks ADMIN permission despite same origin/different path prefix. |
| JS on `http://localhost:5173` reads `http://localhost:8080/api/me` | Browser CORS | Needs CORS for the exact frontend **origin** and still requires login. |
| JS on `http://localhost:3000` calls same API | Browser CORS | If origin is not in allowlist, browser does not grant CORS read access; server still must protect API. |
| Two pages `/a` and `/b` with same hostname/scheme/port | Same-Origin Policy | Different paths do not create separate origins. |

In Spring Security, matcher order matters: rules are evaluated in order; an overly broad rule too early can prevent specific later rules from being evaluated. `requestMatchers("/admin/**").hasRole("ADMIN")` is a rule for the **HTTP request path** on the server, not a way to define a browser origin. Conversely, a CORS origin `http://localhost:5173` should not be written as `requestMatchers(...)`.

## 7. Practice A — Java 17 parsing URLs and comparing origins

To test understanding, let's write a **standalone Java program requiring no external libraries**. It only handles absolute HTTP/HTTPS URLs with valid hostnames; its purpose is to illustrate tuple origins, **not replace the browser's full origin/site algorithm**.

Create file `UrlOriginDemo.java`:

```java
import java.net.URI;
import java.util.Locale;
import java.util.Objects;

public class UrlOriginDemo {

    static int effectivePort(URI uri) {
        if (uri.getPort() >= 0) {
            return uri.getPort();
        }
        return switch (uri.getScheme().toLowerCase(Locale.ROOT)) {
            case "http" -> 80;
            case "https" -> 443;
            default -> throw new IllegalArgumentException("Only HTTP(S)");
        };
    }

    static boolean sameOrigin(URI a, URI b) {
        Objects.requireNonNull(a.getHost());
        Objects.requireNonNull(b.getHost());
        return a.getScheme().equalsIgnoreCase(b.getScheme())
                && a.getHost().equalsIgnoreCase(b.getHost())
                && effectivePort(a) == effectivePort(b);
    }

    public static void main(String[] args) {
        URI base = URI.create("https://app.example.com/home");
        URI pathChanged = URI.create("https://app.example.com/settings?tab=1");
        URI explicitDefault = URI.create("https://app.example.com:443/anything");
        URI portChanged = URI.create("https://app.example.com:8443/home");
        URI subdomainChanged = URI.create("https://api.example.com/home");
        URI schemeChanged = URI.create("http://app.example.com/home");

        System.out.println("path changed: " + sameOrigin(base, pathChanged));
        System.out.println("explicit :443: " + sameOrigin(base, explicitDefault));
        System.out.println("port changed: " + sameOrigin(base, portChanged));
        System.out.println("subdomain changed: " + sameOrigin(base, subdomainChanged));
        System.out.println("scheme changed: " + sameOrigin(base, schemeChanged));

        System.out.println("hostname: " + base.getHost());
        System.out.println("path: " + pathChanged.getPath());
        System.out.println("query: " + pathChanged.getQuery());
    }
}
```

Compile and run with Java 17+:

```bash
javac UrlOriginDemo.java
java UrlOriginDemo
```

**Exact stdout**:

```text
path changed: true
explicit :443: true
port changed: false
subdomain changed: false
scheme changed: false
hostname: app.example.com
path: /settings
query: tab=1
```

From the example:

- `getHost()` reads the hostname; `getPort()` can return `-1` when the URL omits the port, so the code resolves default ports for HTTP/HTTPS.
- Changing path or query does not change origin.
- Changing port, hostname, or scheme changes origin.
- There is **no** `sameSite()` function written in a few lines, because Java `URI` does not provide a built-in Public Suffix List/browser schemeful site algorithm. Do not infer site by taking the last two parts of the hostname.
- The code is intentionally scoped to valid URIs as shown in the example. For arbitrary inputs, you would also need to validate scheme, host, URL parsing, normalization, and opaque/IDN/IPv6 cases as needed; do not reuse this function as a production security policy.

## 8. Practice B — Spring Boot 3.x: separating CORS origin from path-based access rights

The following lab runs an API at `http://localhost:8080`, with endpoints `/public/ping` and `/api/me`. CORS only allows the frontend origin `http://localhost:5173` to access the API via browser; the `/api/me` endpoint still requires HTTP Basic authentication. Other endpoints are denied by rule. This is a **GET-only** lab to clarify origin and path; it is not a production login design.

### 8.1. Create the project structure

```text
origin-path-lab/
├── pom.xml
└── src/main/java/com/example/originpath/
    ├── LabApplication.java
    ├── WebSecurityConfig.java
    └── DemoController.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>origin-path-lab</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

Spring Boot manages compatible dependency versions in its BOM. The version above is an illustrative point in the Boot 3.x line; for real projects, pick a supported patch release.

### 8.3. `LabApplication.java`

```java
package com.example.originpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LabApplication.class, args);
    }
}
```

### 8.4. `WebSecurityConfig.java`

```java
package com.example.originpath;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.webbuilders.WebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of("Authorization"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-secret"))
                .roles("USER")
                .build()
        );
    }
}
```

**Explanation of each mechanism:**

1. `.cors(Customizer.withDefaults())` integrates CORS handling with Spring Security, so valid CORS preflights are processed before normal authentication logic. Browser preflights usually lack login cookies, so CORS is needed at the appropriate position in the filter chain.
2. `cors.setAllowedOrigins(...)` declares the **full origin** of the frontend, including scheme, hostname, and port; do not declare a path, and do not use an inferred domain suffix.
3. `source.registerCorsConfiguration("/api/**", cors)` specifies **which server-side paths** use this CORS policy. It does not mean `/api/**` is an origin.
4. `cors.setAllowCredentials(true)` allows the browser to consider reading responses with credentials when other conditions match. It does not make cookies automatically bypass SameSite/Path/Secure or create a login session.
5. `.requestMatchers("/public/**").permitAll()` allows public routes; `.requestMatchers("/api/**").authenticated()` requires callers to log in; `.anyRequest().denyAll()` blocks routes not defined in the policy.
6. Spring Security supports CSRF by default for protected requests. This lab only declares GET and **does not disable CSRF**; when adding POST/PUT/DELETE APIs, you must design appropriately for the authentication style and CSRF threat model.
7. `InMemoryUserDetailsManager` and illustrative credentials are for local runs. In real systems, use an identity provider, secret handling, HTTPS, and proper session/token policies.

To avoid confusion, **`setAllowedOrigins` checks the origin of the web page calling the API via browser**, while **`authenticated()` checks the identity of the user calling the endpoint**. A request from a CORS-allowed origin without logging in still cannot access `/api/me`.

### 8.5. `DemoController.java`

```java
package com.example.originpath;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("username", auth.getName());
    }
}
```

The two `@GetMapping` endpoints are **two paths within the same origin** of the backend. Spring MVC maps paths to controllers; Spring Security decides whether each path requires authentication.

### 8.6. Testing with curl

From the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

On macOS/Linux invoke `curl`; on Windows PowerShell prefer `curl.exe` if `curl` is an alias. The following commands use standard curl syntax:

```bash
curl -i http://localhost:8080/public/ping

curl -i http://localhost:8080/api/me

curl -i -u student:demo-secret http://localhost:8080/api/me

curl -i -X OPTIONS http://localhost:8080/api/me \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"

curl -i -u student:demo-secret http://localhost:8080/api/me \
  -H "Origin: http://localhost:5173"

curl -i -u student:demo-secret http://localhost:8080/api/me \
  -H "Origin: http://localhost:3000"
```

**Expected results with the exact configuration:**

| Request | Notable result |
| --- | --- |
| `GET /public/ping` | `200 OK`, body `pong`. |
| `GET /api/me` without credentials | `401 Unauthorized` with HTTP Basic challenge. |
| `GET /api/me` with `student:demo-secret` | `200 OK`; JSON `{"username":"student"}`. |
| `OPTIONS` preflight from `http://localhost:5173` with `authorization` header | Processed per CORS policy; response permits the corresponding origin, method, and header. |
| `GET /api/me` with valid credentials and `Origin: http://localhost:5173` | `200` with corresponding CORS allow-origin, typically adding `Access-Control-Allow-Credentials: true`. |
| `GET /api/me` with `Origin: http://localhost:3000` | Not in allowlist; CORS filter may reject with `403 Invalid CORS request` in this configuration. |

Do not equate curl printing a response with browser JavaScript being allowed to read the response. **curl does not enforce Same-Origin Policy or CORS.** To test CORS for real, open a page at origin `http://localhost:5173` and observe the browser's Network/Console, including preflight. If no frontend is running on that port yet, curl preflight is sufficient to inspect server headers, though it does not replace browser verification.

Accounts/passwords in this lesson are for local runs only; never put demo credentials in public SPAs or use Basic without HTTPS in real products.

## 9. Harder cases: proxies, host headers, URL encoding, and multiple domains

### 9.1. A reverse proxy can make the external origin differ from the internal URL

A Boot app may run internally at `http://localhost:8080` yet be accessed by users via `https://api.example.com` behind a load balancer. **The origin the browser sees** is the external URL, not the internal socket between proxy and app.

If the app builds redirects, cookies, or absolute URLs based on `X-Forwarded-Proto`/`Forwarded`, accept those headers only from **trusted, explicitly configured proxies**. Internet clients can send forged headers if the proxy does not strip/overwrite them. Never use self-asserted headers from a browser as proof to bypass authorization.

### 9.2. Partial string similarity in hostnames does not mean the same domain

Example URLs:

```text
https://app.example.com/
https://app.example.com.evil.test/
https://evil-example.com/
https://app.example.com@evil.test/
```

In the last URL, the part before `@` is **userinfo**; the actual hostname is `evil.test`, not `app.example.com`. Checks like `url.startsWith("https://app.example.com")` can be fooled. For any decision whitelisting network destinations or callbacks, parse URLs with a standard parser, verify scheme/host/port and redirect/destination policies; when protecting outbound HTTP, also control DNS resolution, target IP, and egress to prevent SSRF.

Also do not use `host.endsWith("example.com")` to identify valid subdomains because `notexample.com` will match. If a host allowlist is needed, compare exact canonical hostnames or dot boundaries, with explicit policies for subdomains, IDN, and PSL.

### 9.3. Path matching should not rely on unnormalized strings

Strings containing `..`, encoded slashes `%2F`, encoded dots, or multiple slashes may be handled differently by proxies/servlets/routers depending on settings. The path shown in logs, the actual request target, and the path used for security matching may not exactly match the original string.

With Spring Security, use matchers compatible with your current stack and web configuration; test important path variants behind your proxy. Do not write manual checks like `request.getRequestURI().startsWith("/admin")` as your sole primary authorization layer, because routing and security may disagree on normalization.

Another distinction: **query does not create a new origin, yet it is still business input**. `GET /api/users?role=admin` still belongs to the same origin as `GET /api/users?role=user`; the server endpoint must never grant admin permissions solely from that query parameter.

### 9.4. Multiple apps under the same root domain still need separate permission boundaries

For example, an organization has `help.example.com`, `app.example.com`, and `admin.example.com`. These origins may share the same schemeful site. You should not share a session cookie across all of `example.com` or use CORS `https://*.example.com` if some subdomains are operated by third parties or host arbitrary user content.

Good design typically includes: host-only cookies; CORS allowlists of specific origins; clearly defined identity and audience/tokens for APIs; CSRF controls matching the credential mechanism; server-side business permissions; and restricting permissions and data across services.

## 10. Checklist for choosing the right boundary type

When encountering login/CORS/cookie issues or writing a new endpoint, answer in order:

1. **What is the exact client-side URL?** Write down scheme, hostname, explicit/default port, and path; separate query and fragment.
2. **Are frontend and backend same-origin or cross-origin?** Compare all three parts `scheme + host + port`, not just hostname or company name.
3. **If cookies are involved, are the requests same-site or cross-site?** Evaluate schemeful site using registrable domain/PSL; do not guess by splitting the last two labels.
4. **Is the cookie eligible to be sent?** Check host-only/Domain, Path, Secure, SameSite, browser credentials mode, and third-party cookie policies.
5. **Does JavaScript need to read cross-origin responses?** If so, configure CORS with only the required origins/methods/headers/credentials. CORS does not replace authentication/authorization.
6. **Do state-changing requests carry CSRF risk?** Evaluate how the browser auto-attaches cookies/credentials; keep server checks per design.
7. **Which endpoint paths require which permissions?** Apply Spring Security URL rules and business authorization; do not infer permissions from CORS-allowed origins.
8. **Are there proxies, callback URLs, or client-supplied URLs?** Validate host/scheme/redirects and only trust forwarded metadata from identified proxies.
9. **Are there negative tests?** Test different ports, different subdomains, different schemes, different paths, invalid cookies, under-privileged users, and an Origin not in the allowlist.

## 11. Self-check exercises (with solutions)

**Exercise 1.** `https://shop.example.com/cart` and `https://shop.example.com/checkout` have different paths. Are they cross-origin?

**Answer:** No. If scheme, hostname, and effective port match, they are same-origin and same-site. The two paths can still have **two different server authorization policies**.

**Exercise 2.** `https://app.example.com` calls `https://api.example.com`. Are the two URLs same-site or same-origin?

**Answer:** Same-site if the registrable domain is `example.com` for both and the scheme is HTTPS for both; cross-origin because the hostnames differ. JavaScript reading API responses must comply with CORS.

**Exercise 3.** `http://localhost:5173` calls `http://localhost:8080`. If both share the hostname `localhost`, why does the browser still report CORS?

**Answer:** Because the ports differ, so the origins differ. The CORS allowlist must match the frontend origin, e.g. `http://localhost:5173`.

**Exercise 4.** Are `https://app.example.com` and `http://app.example.com` same-site?

**Answer:** Under schemeful site, **no**: HTTPS and HTTP are two different schemes; they are also cross-origin despite sharing the same hostname.

**Exercise 5.** Does a cookie `Domain=example.com; Path=/admin` create a separate JavaScript security zone for `/admin` versus `/profile`?

**Answer:** No. Path is a condition for selecting which cookies to send, not something that creates a separate origin; scripts on the same origin are not isolated solely by differing paths. The server must authenticate/authorize every operation.

**Exercise 6.** The API returns `Access-Control-Allow-Origin: https://app.example.com`. Is an unauthenticated user allowed to read `/api/me`?

**Answer:** CORS only governs the browser's permission to read the response. If the server requires authentication, an unauthenticated request is still denied/challenged.

**Exercise 7.** If two hostnames share the same IP, do they become same-origin?

**Answer:** No. Origin evaluates scheme/hostname/port, not the IP address resolved by DNS.

**Exercise 8.** For `www.example.co.uk` and `api.example.co.uk`, is taking the last two labels `co.uk` to compute site correct?

**Answer:** No. `co.uk` is a public suffix; the registrable domain in the example is `example.co.uk`. PSL must be consulted, not manual label counting.

**Exercise 9.** Why do cross-origin requests still carry CSRF risk even when the server does not enable CORS?

**Answer:** Browsers can send certain cross-origin requests such as form submissions. Not letting JavaScript read the response does not guarantee the request never reached the server or had no effect; CSRF, cookies, and server permissions must be evaluated.

**Exercise 10.** Does Spring Security's `requestMatchers("/admin/**").hasRole("ADMIN")` mean "the `/admin` page is a separate origin"?

**Answer:** No. The matcher applies an access policy for server paths; origin is determined by scheme, host, and port. The two concepts operate independently yet complement each other to protect the application.

## Conclusion

Four concepts answer four kinds of questions:

- **Hostname:** which host is the URL pointing to?
- **Origin:** do two URLs share scheme, host, and effective port, to evaluate Same-Origin Policy/CORS boundaries?
- **Site:** do two URLs share the same schemeful registrable domain, to understand many cookie/SameSite behaviors?
- **Path:** which resource or endpoint is the server routing to, and which policy should be applied there?

In Spring applications, CORS is an **origin** policy for browsers; SameSite cookies work with the **site** concept; hostname/Domain defines many parts of cookie scope and routing; Spring Security `requestMatchers` together with business authorization control **paths and access permissions**. Clearly distinguishing these scopes helps configure things properly without confusing the browser being allowed to read a response with a user being allowed to perform an action.