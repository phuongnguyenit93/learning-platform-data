# CORS and CSRF for Spring for GraphQL

When a web application calls a GraphQL API from another domain, two security mechanisms often need to be configured together: **CORS (Cross-Origin Resource Sharing)** and **CSRF (Cross-Site Request Forgery)**. CORS determines whether a browser is permitted by server policy to send cross-origin requests and read responses. CSRF protects state-changing requests when browsers automatically attach credentials such as session cookies.

The two mechanisms solve different problems. CORS does not replace CSRF, and CSRF does not configure cross-origin access permissions. With Spring for GraphQL, you must account for the default `/graphql` HTTP endpoint, POST requests, CSRF tokens in headers, CORS preflight requests, and how Spring Security processes requests before the GraphQL engine is invoked.

## 1. Origin and site are two different concepts

An **origin** is defined by scheme, host, and port. For example:

| URL | Origin |
|---|---|
| `https://app.example.com` | `https://app.example.com` |
| `https://api.example.com` | `https://api.example.com` |
| `http://app.example.com` | `http://app.example.com` |
| `https://app.example.com:8443` | `https://app.example.com:8443` |

The URLs above are distinct origins if any one of the three components—scheme, host, or port—differs. Thus, a frontend at `https://app.example.com` calling an API at `https://api.example.com` is a cross-origin request.

**Site** is used in `SameSite` cookie policies. Two subdomains can have different origins while still belonging to the same site. For example, `https://app.example.com` and `https://api.example.com` have different origins yet are typically considered same-site. Conversely, `https://app.example.net` calling `https://api.example.com` is cross-site.

Distinguishing these two concepts is critical:

- CORS checks the origin.
- `SameSite` cookies govern sending cookies in cross-site contexts.
- A CSRF token verifies that the request contains a value an external webpage cannot automatically obtain.

## 2. What do CORS and CSRF protect against?

| Mechanism | Problem solved | Primary enforcement point |
|---|---|---|
| CORS | Is a webpage on another origin allowed to call the API and read the response? | Browser and CORS headers returned by the server. |
| CSRF | Was a state-changing request genuinely initiated from a legitimate application? | Server checking a CSRF token or equivalent anti-forgery mechanism. |
| Authentication | Which user or service does the request belong to? | Spring Security, session, bearer token, or other auth mechanism. |
| Authorization | Does the caller have permission to perform this action or read this data? | Spring Security and application/domain policies. |

For example, a user logs in at `api.example.com` and the browser holds a session cookie. The user opens an untrusted page. That page might attempt to send a request to the API via the user's browser. If the cookie is sent automatically and the server does not require a CSRF token, the forged request could perform actions under the user's identity.

CORS alone does not prevent all such requests. For certain simple requests, the browser still sends the request to the server while blocking JavaScript on the foreign origin from reading the response. Therefore, the server still needs CSRF protection for state-changing operations when using automatically attached credentials.

## 3. How does CORS work?

When JavaScript calls an API on another origin, the browser enforces CORS policy. The server responds with HTTP headers such as:

- `Access-Control-Allow-Origin`: allowed origin.
- `Access-Control-Allow-Methods`: allowed HTTP methods.
- `Access-Control-Allow-Headers`: allowed request headers.
- `Access-Control-Allow-Credentials`: whether requests carrying credentials are allowed.
- `Access-Control-Expose-Headers`: response headers that JavaScript is allowed to read.
- `Access-Control-Max-Age`: how long the browser may cache preflight results.

Not every cross-origin request triggers a preflight. A browser can send a **simple request** directly if the request satisfies Fetch/CORS criteria, such as allowed methods and safelisted headers. Requests using `Content-Type: application/json`, `Authorization`, or custom headers typically require a preflight.

## 4. What is CORS preflight?

A preflight is an `OPTIONS` request automatically sent by the browser before the actual request to ask the server whether the intended method and headers are permitted.

Example of a frontend sending a GraphQL POST with a CSRF header:

```http
OPTIONS /graphql HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-xsrf-token
```

If allowed, the server responds similarly to:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-XSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
```

Only after the preflight succeeds does the browser send the actual POST request. Preflights do not carry session cookies. Therefore, CORS must be processed before Spring Security requires an authenticated user; if a security filter rejects `OPTIONS` before CORS runs, the browser will never send the real GraphQL request.

## 5. GraphQL HTTP transport and CORS

Spring for GraphQL provides HTTP transport via `GraphQlHttpHandler`. With Spring Boot, the default endpoint is:

```text
POST /graphql
Content-Type: application/json
```

The body typically contains `query`, `operationName`, `variables`, and `extensions`:

```json
{
  "operationName": "CreateOrder",
  "query": "mutation CreateOrder($input: CreateOrderInput!) { createOrder(input: $input) { order { id } } }",
  "variables": {
    "input": {
      "customerId": "customer-1",
      "items": [{ "productId": "product-1", "quantity": 2 }]
    }
  }
}
```

`application/json` is not one of the CORS-safelisted `Content-Type` values. When a frontend sends a GraphQL JSON POST, the browser usually performs a preflight. If the request also includes `Authorization` or `X-XSRF-TOKEN`, those headers must also be allowed.

Spring Boot provides `spring.graphql.cors.*` properties to configure CORS for the GraphQL endpoint. In systems with Spring Security, ensure the same CORS policy is integrated into the security filter chain so preflights are handled before authentication.

## 6. Configuring CORS via Spring Boot properties

For a frontend with a fixed origin, you can configure `application.yml`:

```yaml
spring:
  graphql:
    cors:
      allowed-origins:
        - "https://app.example.com"
      allowed-methods:
        - GET
        - POST
      allowed-headers:
        - Content-Type
        - Authorization
        - X-XSRF-TOKEN
        - X-CSRF-TOKEN
      allow-credentials: true
      max-age: 1800s
```

Meaning:

- `allowed-origins`: permits only the declared frontend.
- `allowed-methods`: permits the methods used by the GraphQL transport.
- `allowed-headers`: includes JSON content type, bearer authorization if applicable, and CSRF headers.
- `allow-credentials`: allows browsers to send credentials such as cookies when the client enables credentials mode.
- `max-age`: caches preflight results for 30 minutes.

If the frontend does not use cookies and does not need automatic HTTP authentication headers attached, do not enable `allow-credentials` merely to make CORS work. Enable it only when the authentication model truly requires it.

If JavaScript needs to read a custom response header, such as a token returned in `X-CSRF-TOKEN`, add that header to `exposed-headers`:

```yaml
spring:
  graphql:
    cors:
      allowed-origins:
        - "https://app.example.com"
      allowed-methods: [GET, POST]
      allowed-headers: [Content-Type, X-CSRF-TOKEN]
      exposed-headers: [X-CSRF-TOKEN]
      allow-credentials: true
```

`allowed-headers` lists the headers clients are allowed to send. `exposed-headers` lists the response headers JavaScript is allowed to read. These two properties do not replace each other.

## 7. Do not use wildcard origins with credentials

When `allow-credentials` is enabled, do not configure:

```yaml
spring:
  graphql:
    cors:
      allowed-origins: "*"
      allow-credentials: true
```

Browsers reject `Access-Control-Allow-Origin: *` for credentialed requests. The server must return a specific origin, for example:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Prefer declaring exact trusted origins. `allowed-origin-patterns` can be used when you have a controlled set of subdomains, but overly broad patterns can inadvertently allow untrusted applications.

An origin is the tuple of scheme, host, and port. `https://app.example.com` differs from `http://app.example.com` and differs from `https://app.example.com:8443`. Configured values should not have a trailing `/`.

## 8. Integrating CORS into Spring Security

Spring Security must process CORS before authentication. For Spring MVC applications using the Servlet stack, you can declare a `CorsConfigurationSource` and enable `.cors()` in `SecurityFilterChain`.

Example explicit configuration for GraphQL and a CSRF token endpoint:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class GraphQlWebSecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST"));
        configuration.setAllowedHeaders(List.of(
            "Content-Type",
            "Authorization",
            "X-CSRF-TOKEN",
            "X-XSRF-TOKEN"
        ));
        configuration.setAllowCredentials(true);
        configuration.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/graphql", configuration);
        source.registerCorsConfiguration("/csrf", configuration);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/csrf").permitAll()
                .requestMatchers("/graphql").authenticated()
                .anyRequest().denyAll()
            );

        return http.build();
    }
}
```

`CorsFilter` is integrated into the security chain to handle preflights before authentication. `OPTIONS` preflights do not need session cookies; the CORS filter verifies `Origin`, method, and requested headers and returns the appropriate response.

This is a Servlet/MVC example. Once you use a `CorsConfigurationSource` in the security chain, treat it as the source of CORS policy for that chain. Do not declare multiple conflicting CORS sources without clearly specifying which chain uses which source.

The earlier `application.yml` snippet and the `CorsConfigurationSource` bean here are two ways of declaring the same policy. When using an explicit bean for Spring Security, keep the list of origins, methods, and headers consistent; do not let properties or a reverse proxy emit a different policy.

## 9. Choosing a single consistent CORS configuration source

CORS can be configured via Spring Boot properties, Spring MVC, `CorsConfigurationSource`, or a gateway/reverse proxy. A common issue is multiple layers adding CORS headers with different values.

For example, a reverse proxy returns `Access-Control-Allow-Origin: *` while the application returns a specific origin alongside `Access-Control-Allow-Credentials: true`. Browsers may reject the response due to duplicate or inconsistent headers.

Choose one clear place of ownership:

- If the application handles CORS itself, configure one policy for the GraphQL path and wire it into Spring Security.
- If the gateway handles CORS, ensure the gateway has an exact allowlist and the backend does not add a conflicting set of headers.
- If using multiple `SecurityFilterChain`s, configure the corresponding CORS source for each chain.

Do not use CORS as a substitute for authentication, authorization, or network policy. Non-browser clients are not bound by CORS.

## 10. Clients sending cookies in cross-origin requests

Browser `fetch` does not send credentials in cross-origin requests by default. If the API authenticates via session cookies, the frontend must request sending credentials:

```javascript
const response = await fetch("https://api.example.com/graphql", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    query: "query { currentUser { id email } }"
  })
});
```

For JavaScript to read the response, the server must allow the specific origin and return `Access-Control-Allow-Credentials: true`. Both server and client must agree on sending credentials.

If cookies/sessions are not needed, do not set `credentials: "include"` just because it is GraphQL. With bearer tokens, the client can send the `Authorization` header and CORS must allow that header.

## 11. CORS is not a CSRF defense mechanism

CORS primarily controls JavaScript access to responses inside the browser. A simple cross-origin request can still be sent to the server even when the browser blocks scripts from reading the response. This is why the server still must defend against CSRF.

A GraphQL JSON request usually triggers a preflight, yet preflight should not be treated as a CSRF token:

- CORS configuration can change or be broadened by mistake.
- The endpoint might also enable GET or another transport.
- Non-browser clients do not enforce CORS.
- A simple request can be sent without a preflight.
- CORS does not prove the request was actively initiated by the user from a legitimate UI.

A CSRF token is a value expected by the server that the client must send back in a header or parameter that browsers do not attach automatically to requests. The server compares that value against the stored token.

## 12. How does CSRF work?

A common defense is the **synchronizer token pattern**:

1. The server generates a CSRF token tied to the session or a repository.
2. The legitimate application obtains the token via HTML, a cookie, or a dedicated endpoint.
3. When sending a state-changing request, the client attaches the token in a header or hidden form field.
4. Spring Security reads the token from the request and compares it with the token stored by the server.
5. If the token is missing or mismatches, the request is rejected before reaching controllers or GraphQL handlers.

An attacker can cause the browser to send login session cookies, but another website cannot read the CSRF token from the legitimate application's origin under the browser's same-origin policy. Thus, forged requests lacking a valid token are rejected.

## 13. Spring Security enables CSRF by default for unsafe methods

In Servlet applications, Spring Security enables CSRF protection by default for unsafe HTTP methods such as POST, PUT, PATCH, and DELETE. Safe methods like GET, HEAD, TRACE, and OPTIONS do not require a token under the default matcher.

You can keep the default configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class CsrfConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
```

When the application uses session cookies or any credential automatically sent by the browser, keeping CSRF protection enabled is the right default. Do not disable CSRF simply because the request body is JSON or the endpoint is GraphQL.

## 14. How does CSRF apply to GraphQL POST?

Spring for GraphQL's HTTP transport receives JSON POSTs at `/graphql` by default. Spring Security inspects the HTTP method and does not parse the GraphQL body to determine whether it is a query or a mutation.

Therefore, when using session/cookie authentication:

- POST queries require a CSRF token.
- POST mutations require a CSRF token.
- A POST subscription over Server-Sent Events also requires a token if the endpoint uses the default CSRF filter.
- Requests missing or having an invalid token are blocked before the GraphQL engine runs.

CSRF protection is not solely for mutations. Queries must be side-effect-free per GraphQL semantics, yet HTTP POST remains an unsafe method to the default CSRF matcher.

When the CSRF filter rejects a request, clients typically receive HTTP 403. This is an HTTP/security-layer error; GraphQL resolvers have not been invoked and the response does not necessarily follow the GraphQL `data`/`errors` structure.

## 15. Do not ignore CSRF for all of `/graphql` when using cookie auth

A common yet dangerous configuration:

```java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/graphql")
);
```

This matcher disables CSRF for every GraphQL POST request at the endpoint, including mutations that create orders, update profiles, or process payments. If the browser sends session cookies automatically, forged requests can execute under that session.

Do not ignore CSRF just because:

- The body is JSON.
- The request carries `Content-Type: application/json`.
- There is only a single `/graphql` URL.
- GraphQL contains both queries and mutations.
- The frontend has CORS enabled.

If you have an API chain that genuinely uses no automatically attached credentials, isolate that chain and its authentication model before disabling CSRF. Never apply an exemption to a GraphQL endpoint that uses session cookies.

## 16. Session token repository

Spring Security defaults to `HttpSessionCsrfTokenRepository` to store tokens in the HTTP session. This is a good choice for server-rendered applications or SPAs that can fetch the token via an endpoint.

Tokens are sent in requests as a header or parameter. The default header is `X-CSRF-TOKEN`; the default request parameter is `_csrf`.

For GraphQL JSON requests, a header is usually more suitable than a parameter:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: token-value
Cookie: JSESSIONID=session-id
```

The browser sends the session cookie automatically per cookie policy. JavaScript must explicitly add the CSRF header to POST requests.

## 17. Issuing CSRF tokens via a `/csrf` endpoint

For JavaScript frontends, you can create a dedicated endpoint to retrieve the token:

```java
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfController {

    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
```

Spring Security supplies `CsrfToken` via an argument resolver. If the frontend needs to obtain a token before logging in, you can permit `GET /csrf` in authorization rules:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/csrf").permitAll()
    .requestMatchers("/graphql").authenticated()
    .anyRequest().denyAll()
)
```

When called from another origin, `/csrf` also needs an appropriate CORS policy. If the token is returned in a JSON body, CORS must allow the frontend origin to read the response, and credentials must be enabled if a session cookie needs to be sent.

The client reads `headerName` and `token` from the response and uses `token` as the value of the corresponding request header:

```javascript
const csrfResponse = await fetch("https://api.example.com/csrf", {
  credentials: "include"
});

if (!csrfResponse.ok) {
  throw new Error("Cannot obtain CSRF token");
}

const csrf = await csrfResponse.json();

const graphQlResponse = await fetch("https://api.example.com/graphql", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({
    query: "mutation { cancelOrder(id: \"order-101\") { order { id } } }"
  })
});
```

This example uses session-based CSRF tokens. If you choose a cookie-based SPA token repository, follow that repository's request handler and header format rather than mixing two token handling approaches.

## 18. Refreshing CSRF tokens after login and logout

Spring Security clears the current CSRF token upon successful authentication and upon successful logout. This prevents an old token from continuing to be used after a security context change.

With a session-based token repository, the frontend should re-fetch `/csrf`:

- When the application initializes.
- After a successful login.
- After a successful logout if the application continues using a session.
- When receiving a response indicating the token is no longer valid and the auth flow allows obtaining a new token.

If the client keeps sending an old token after login, `POST /graphql` can receive HTTP 403. Do not automatically retry a mutation with a new token if you do not know whether the prior mutation already executed; idempotency is required for operations with side effects.

## 19. Cookie-based CSRF tokens for SPAs

For SPAs, Spring Security provides `CookieCsrfTokenRepository`. This repository uses these defaults:

| Component | Default value |
|---|---|
| Cookie name | `XSRF-TOKEN` |
| Request header | `X-XSRF-TOKEN` |
| Request parameter | `_csrf` |

JavaScript reads the `XSRF-TOKEN` cookie and sends that value in the `X-XSRF-TOKEN` header on unsafe requests. This cookie is not a session cookie; it only holds the CSRF token that the server compares against the header value sent by the client.

To allow JavaScript to read the cookie, `CookieCsrfTokenRepository.withHttpOnlyFalse()` sets `HttpOnly=false`. Use this only when the application actually needs JavaScript to read the cookie. If direct cookie reading is not needed, keep `HttpOnly` to reduce the chance of scripts reading the value.

## 20. Spring Security 7.2: concise SPA configuration

In Spring Security 7.2, you can use the `spa()` helper to configure CSRF integration for SPAs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf.spa());
        return http.build();
    }
}
```

This helper configures the cookie repository for SPAs and the request handler needed to accept raw tokens in headers while preserving BREACH protection for tokens rendered into responses. The default cookie name is `XSRF-TOKEN`; clients send the value back in `X-XSRF-TOKEN`.

After login/logout, the CSRF cookie may be cleared and regenerated. Clients must re-read the new cookie before sending the next POST.

## 21. Spring Security 6.5: SPA configuration with a request handler

With Spring Security 6.5, SPA configuration needs to combine `CookieCsrfTokenRepository` with a custom `CsrfTokenRequestHandler`. This is because Spring Security enables BREACH protection by default: tokens placed in request attributes can be encoded/masked, whereas JavaScript reads the raw value from the cookie.

Register the repository and handler:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf
            .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
            .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
        );

        return http.build();
    }
}
```

The handler selects how to resolve the token based on where it was sent:

```java
import java.util.function.Supplier;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain = new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor = new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {

        this.xor.handle(request, response, csrfToken);
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request, CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());
        CsrfTokenRequestHandler handler = StringUtils.hasText(headerValue) ? this.plain : this.xor;
        return handler.resolveCsrfTokenValue(request, csrfToken);
    }
}
```

The handler always uses the XOR request attribute handler when preparing tokens for responses to preserve BREACH protection. When the client sends a header read from the raw cookie token, the handler uses the plain resolver. When the token comes from a request parameter such as a hidden HTML form field, the handler uses the XOR resolver.

This example is for the Servlet stack. Do not use Servlet's `CsrfTokenRequestHandler` in a WebFlux configuration; the reactive stack has its own APIs and context.

## 22. Sending the CSRF cookie in GraphQL fetch

When the SPA and API share an origin or the cookie has an appropriate domain scope, JavaScript can read `XSRF-TOKEN`:

```javascript
function readCookie(name) {
  const prefix = `${name}=`;
  const value = document.cookie
    .split(";")
    .map(item => item.trim())
    .find(item => item.startsWith(prefix));

  return value ? decodeURIComponent(value.slice(prefix.length)) : undefined;
}

async function executeGraphQl(query, variables) {
  const token = readCookie("XSRF-TOKEN");

  if (!token) {
    throw new Error("CSRF token is missing; refresh the application token first");
  }

  return fetch("https://api.example.com/graphql", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify({ query, variables })
  });
}
```

The `X-XSRF-TOKEN` header must be listed in CORS `allowed-headers`. Because this is a custom header, the browser will send a preflight before the GraphQL POST.

If the cookie cannot be read from the frontend origin, do not attempt to access another host's cookie from JavaScript. Use a session-based `/csrf` endpoint or a token-issuance design compatible with your domain/cookie policy.

## 23. Cookie domain when frontend and API are on different subdomains

Suppose:

- Frontend: `https://app.example.com`.
- GraphQL API: `https://api.example.com`.

These two URLs have different origins yet share the same site. A host-only cookie set for `api.example.com` will be sent to the API, but JavaScript running on `app.example.com` cannot read that cookie.

There are two common design approaches:

1. Use a session-based CSRF token endpoint `/csrf`, allowing the frontend to obtain the token via a CORS-permitted response.
2. Configure a shared cookie domain such as `.example.com` if security policy allows subdomains to trust one another.

Sharing cookies across all subdomains widens the set of hosts that can receive the cookie. Use this only when you control all subdomains and fully understand their risks.

## 24. SameSite, Secure, and cross-site cookies

`SameSite` cookies control when browsers send cookies in cross-site requests:

| Value | General behavior | When to use |
|---|---|---|
| `Strict` | Does not send cookies in most cross-site contexts. | Applications that can maintain strict behavior without needing cookies on off-site navigation flows. |
| `Lax` | Allows certain safe top-level navigations, blocks most cross-site subrequests. | Suitable default choice for many session cookies. |
| `None` | Allows sending cookies cross-site if browser policy permits; requires `Secure`. | Frontend and API on different sites requiring cookie credentials. |

`SameSite` is an additional defense layer, not a replacement for CSRF tokens. Two subdomains with different origins can still be same-site; thus, `SameSite` does not prove a request came from the right frontend origin.

For cross-site cookies, `SameSite=None; Secure` is typically required. However, browser third-party cookie policies may still block cookies even when the server enables CORS credentials. CORS cannot force browsers to accept third-party cookies.

## 25. Customizing the CSRF cookie

`CookieCsrfTokenRepository` supports cookie customization. Example with the Servlet stack:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class CsrfCookieConfiguration {

    @Bean
    CookieCsrfTokenRepository csrfTokenRepository() {
        CookieCsrfTokenRepository repository = CookieCsrfTokenRepository.withHttpOnlyFalse();
        repository.setCookieCustomizer(cookie -> cookie
            .secure(true)
            .sameSite("Lax")
            .path("/")
        );
        return repository;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CookieCsrfTokenRepository csrfTokenRepository) throws Exception {

        http.csrf(csrf -> csrf
            .csrfTokenRepository(csrfTokenRepository)
            .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
        );
        return http.build();
    }
}
```

This example is for a same-site frontend. For cross-site deployments, evaluate `SameSite=None` and `Secure`, and check browser cookie policies. Do not configure `Domain` more broadly than necessary.

This example uses `SpaCsrfTokenRequestHandler` defined in the Spring Security 6.5 section. With Spring Security 7.2, you can use the `csrf.spa()` helper if you do not need to customize the cookie repository. Do not declare a standalone repository bean and assume Spring Security automatically picks it up.

`CsrfCookieConfiguration` is an alternative way to configure the CSRF part of the earlier `GraphQlWebSecurityConfiguration`. When integrating into an application, use a single appropriate `SecurityFilterChain` combining both CORS and CSRF in that chain; do not register two default chains that both match every request.

## 26. How cookie authentication and bearer tokens differ on CSRF

CSRF relies on browsers automatically attaching credentials that another webpage can exploit.

| Authentication method | Does the browser send credentials automatically? | Needs CSRF consideration? |
|---|---|---|
| Session cookie | Yes, per cookie policy | Yes. |
| JWT/access token in a cookie | Yes, per cookie policy | Yes. Being a JWT does not eliminate CSRF risk. |
| HTTP Basic cached in browser | Can be sent automatically by the browser | May require CSRF protection. |
| Bearer token in `Authorization` explicitly added by JavaScript | Not automatically attached by the browser | Classic CSRF typically does not apply if no other automatic cookie/credential exists. |
| API key sent by a server-to-server client | Not a browser auto-sent credential | Browser CSRF is usually not the primary threat. |

A "stateless" API can still be vulnerable to CSRF if it authenticates using a JWT stored in a cookie. Conversely, an API accepting bearer tokens solely via the `Authorization` header with no cookie/session authentication may have grounds to disable CSRF for that dedicated security chain.

Do not decide to disable CSRF solely because a token uses JWT format or the server stores no session. Identify which credentials the browser automatically attaches to requests.

## 27. When can CSRF be disabled?

An API that only accepts bearer tokens in the `Authorization` header, does not use cookies for authentication, and has no other browser auto-attached credential mechanism may not need CSRF protection.

For example, a filter chain dedicated to a stateless API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class StatelessApiSecurityConfiguration {

    @Bean
    SecurityFilterChain statelessApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/service-api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(resourceServer -> resourceServer.jwt());

        return http.build();
    }
}
```

This example only illustrates a separate API chain. Do not copy `.csrf(disable)` into a chain serving web sessions or cookie-authenticated GraphQL. Ensure endpoints in the chain accept only bearer authentication and never fall back to cookies/sessions.

If the same `/graphql` endpoint serves both cookie sessions and bearer tokens, disabling CSRF for the entire endpoint can reopen vulnerabilities for cookie-authenticated clients. Design distinct security chains or endpoints instead of relying on client-supplied headers to decide whether to skip CSRF.

## 28. GraphQL HTTP GET and CSRF

Spring for GraphQL can enable HTTP GET, though GET is disabled by default. GET is only allowed for queries; mutations sent via GET are rejected.

GET is a safe HTTP method, so Spring Security does not require a CSRF token for GET. This does not mean you should convert mutations into GET. Mutations must always use unsafe methods such as POST and retain CSRF protection when using cookie authentication.

Before enabling GET, note:

- Queries and variables appear in URLs, which can be recorded in access logs, browser history, `Referer` headers, or proxy caches.
- GET without `Content-Type` is typically a CORS simple request and skips preflight.
- Browsers can send GET with cookies even when scripts on another origin cannot read the response.
- Query resolvers must not produce side effects.
- Rate limiting, query cost limits, and audit logging still need to be enforced.

Therefore, GET is suitable when caching is needed or clients only support GET and queries contain no sensitive data. Do not use GET to bypass CSRF.

## 29. Server-Sent Events and WebSocket subscriptions

Spring for GraphQL supports subscriptions via Server-Sent Events or WebSocket. Each transport has a distinct security model.

**Server-Sent Events (SSE):** POST requests are the default, so the CSRF filter protects them just like other POSTs. If enabling GET for SSE, remember GET is a safe method and does not require a CSRF token. HTTP CORS still applies.

**WebSocket:** WebSocket handshakes do not use CORS preflight like HTTP fetch. Validate `Origin` and allow only trusted origins. Spring Framework restricts WebSocket requests to same-origin by default; if opening cross-origin access, declare an explicit allowlist.

Spring Boot does not enable the GraphQL WebSocket endpoint by default. When enabling it, configure the path and required dependencies. Spring for GraphQL provides `AuthenticationWebSocketInterceptor` to extract authentication details from the `connection_init` payload and propagate the security context to subsequent requests.

An origin allowlist does not replace authentication. Authenticate the connection, limit subscriptions, and enforce authorization on emitted data. Do not mistakenly apply HTTP CORS properties to WebSocket handshakes.

## 30. Spring WebFlux and CORS

If the application uses WebFlux, Spring Security uses the reactive security chain. The CORS source belongs to the reactive package, not Servlet.

Example reactive CORS source configuration:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST"));
        configuration.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-XSRF-TOKEN"
        ));
        configuration.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/graphql", configuration);
        source.registerCorsConfiguration("/csrf", configuration);
        return source;
    }
}
```

The reactive security chain uses `ServerHttpSecurity` and the reactive CORS configuration source. Do not pass a Servlet `CorsConfigurationSource` into `SecurityWebFilterChain`.

CSRF in WebFlux is also supported by Spring Security, though token configuration and tests use reactive APIs. Use the proper `ServerHttpSecurity`, `ServerCsrfTokenRepository`, and test support matching your application's Spring Security version.

## 31. Testing CORS preflight with MockMvc

CORS tests must traverse the HTTP/security filter chain. Running `GraphQlTester` directly against GraphQL execution is not enough to verify the CORS filter.

Example preflight test for a Servlet application:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GraphQlCorsTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsPreflightFromConfiguredFrontend() throws Exception {
        mockMvc.perform(options("/graphql")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-xsrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"));
    }
}
```

This test verifies that the preflight is handled and the specific origin is echoed back. You can add assertions for allowed methods and allowed headers for stricter verification.

## 32. Testing disallowed origins

Origins not on the allowlist must not receive a valid `Access-Control-Allow-Origin`:

```java
@Test
void doesNotAllowUnknownOrigin() throws Exception {
    mockMvc.perform(options("/graphql")
            .header(HttpHeaders.ORIGIN, "https://evil.example.net")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type"))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
}
```

With Spring Framework's default `CorsProcessor`, preflights from disallowed origins return HTTP 403. If CORS is handled at a gateway or reverse proxy, the status may depend on that layer's configuration; in all cases, never return `Access-Control-Allow-Origin` for untrusted origins.

## 33. Testing CSRF for GraphQL POST

CSRF tests must pass through the Spring Security filter chain. Use `spring-security-test` and MockMvc for the Servlet stack:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Example POST request missing a token:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GraphQlCsrfTests {

    @Autowired
    MockMvc mockMvc;

    private static final String QUERY = """
        { "query": "query { greeting }" }
        """;

    @Test
    void rejectsGraphQlPostWithoutCsrfToken() throws Exception {
        mockMvc.perform(post("/graphql")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content(QUERY))
            .andExpect(status().isForbidden());
    }
}
```

The example assumes the schema has a `greeting` query and the endpoint requires authentication. The CSRF filter rejects the request before the resolver runs, so the status is 403.

## 34. Testing requests with a valid CSRF token

Spring Security test provides the `csrf()` request post processor to attach a valid token:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@Test
void acceptsGraphQlPostWithValidCsrfToken() throws Exception {
    mockMvc.perform(post("/graphql")
            .with(user("alice"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content(QUERY))
        .andExpect(status().isOk());
}
```

A 200 response assumes the query is valid and the resolver succeeds. If the query or schema is invalid, the GraphQL result depends on response media type and transport version; the goal of this test is to prove the CSRF filter lets the request proceed.

## 35. Testing invalid tokens

You can also verify that a wrong token is rejected:

```java
@Test
void rejectsGraphQlPostWithInvalidCsrfToken() throws Exception {
    mockMvc.perform(post("/graphql")
            .with(user("alice"))
            .with(csrf().useInvalidToken())
            .contentType(MediaType.APPLICATION_JSON)
            .content(QUERY))
        .andExpect(status().isForbidden());
}
```

Include all three tests: missing token, wrong token, and valid token. Only testing that requests with a token succeed does not prove the filter rejects requests missing a token.

## 36. Testing tokens with GraphQlTester and HTTP testers

`GraphQlTester` has several implementations. When using a tester directly with `ExecutionGraphQlService`, requests bypass the Servlet filter chain, so those tests do not prove CORS or CSRF work.

To test transport security:

- Use MockMvc for Spring MVC.
- Use `WebTestClient` and Spring Security reactive test support for WebFlux.
- Send requests to the actual `/graphql` HTTP endpoint.
- Check HTTP status and CORS headers before inspecting the GraphQL response.

Then use `GraphQlTester` to test the schema, resolvers, payloads, and GraphQL errors at the execution layer. The two test groups complement each other.

## 37. Handling HTTP 403 due to CSRF on the frontend

If the frontend receives 403 when calling GraphQL, identify where the error originated:

1. Verify the request was sent to `/graphql`.
2. Verify whether the session cookie or credentials were sent.
3. Verify the CSRF header is present in the request.
4. Verify the token is the latest one after login/logout.
5. Verify that header is allowed by CORS `allowed-headers`.
6. Verify the CORS preflight succeeded before the actual request.
7. Inspect Spring Security logs to distinguish missing tokens from invalid tokens.

If the preflight fails, the browser typically reports a CORS/network error and does not send the real POST. If the preflight succeeds yet the CSRF token is missing or wrong, the POST is rejected with 403 by the security filter.

Do not automatically retry mutations on 403 if you do not know whether the request reached the application. The CSRF filter normally blocks before GraphQL execution, yet the frontend should refresh the token and only resend the operation when certain the prior request produced no side effects.

## 38. Common configuration pitfalls

**Allowing `allowed-origins: "*"` with credentials.** Browsers reject credentialed responses. Use specific origins or controlled origin patterns.

**Forgetting `X-XSRF-TOKEN` in allowed headers.** Preflights fail even when the origin and POST are allowed. Add the exact CSRF header sent by the client.

**Forgetting to enable credentials on the client.** Session cookies are not sent in cross-origin fetch calls. Use `credentials: "include"` when authenticating via cookies.

**Enabling `allow-credentials` without cookie authentication.** Unnecessary credential configuration widens access exposure. Enable it only when the auth model requires it.

**Letting Spring Security block `OPTIONS` before CORS.** Preflights carry no session cookies. Configure CORS before authentication via `.cors()` and a valid source.

**Disabling CSRF for all of `/graphql`.** Every mutation using cookie auth loses protection. Keep default CSRF enabled and supply tokens to the frontend.

**Assuming JSON POST is automatically exempt from CSRF.** Spring Security protects unsafe HTTP methods regardless of whether the body is JSON or GraphQL.

**Assuming JWTs are always exempt from CSRF.** A JWT stored in a cookie is still a credential automatically sent by the browser. Identify where tokens are stored and how they are sent.

**Not refreshing tokens after login/logout.** The old token is cleared, so the next POST receives 403. Fetch a new token whenever the security context changes.

**Using CORS as authorization.** Non-browser clients can call the API regardless of CORS. Always authenticate and authorize server-side.

**Enabling GET to evade CSRF.** GET is strictly for safe queries and must have no side effects. Never use GET for mutations.

**Applying HTTP CORS to WebSocket.** WebSocket handshakes need their own origin validation and connection authentication.

## 39. CORS and CSRF implementation checklist

- [ ] List exact frontend origins by scheme, host, and port.
- [ ] Allow only the HTTP methods GraphQL actually uses.
- [ ] Allow `Content-Type`, `Authorization`, and required CSRF headers.
- [ ] Enable `allow-credentials` only when browsers need to send cookies/credentials.
- [ ] Never use wildcard origins for credentialed requests.
- [ ] Process CORS preflights before authentication.
- [ ] Keep CSRF protection enabled for GraphQL POSTs when using cookie/session authentication.
- [ ] Issue tokens to the frontend via SPA cookies or a `/csrf` endpoint.
- [ ] Refresh tokens after login and logout.
- [ ] Never skip CSRF for all of `/graphql` if the endpoint accepts cookie auth.
- [ ] Distinguish bearer headers from JWTs stored in cookies.
- [ ] Enable GET only for side-effect-free queries and understand URL logging risks.
- [ ] Configure origins and authentication separately for GraphQL WebSocket.
- [ ] Test preflights, disallowed origins, and missing/invalid/valid CSRF tokens.
- [ ] Use HTTP-level tests to verify the security filter chain.

## Conclusion

CORS and CSRF should be designed as two separate protective layers for a GraphQL HTTP API. CORS restricts which origins browsers may call from and read responses from; CSRF protects unsafe requests using automatically attached credentials. Spring Boot provides `spring.graphql.cors.*`, while Spring Security integrates CORS via `.cors()` and protects POSTs by default with the CSRF filter. For SPAs, you can use `CookieCsrfTokenRepository` with `X-XSRF-TOKEN` or a session token `/csrf` endpoint. Keep origin allowlists exact, handle preflights before authentication, refresh tokens after login/logout, and test through the HTTP filter chain so GraphQL mutations never lose this protection.

## References

- [Spring Boot — Spring for GraphQL and CORS](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot — Application Properties (`spring.graphql.cors.*`)](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring GraphQL — WebSocket Authentication](https://docs.spring.io/spring-graphql/reference/transports.html#server-transports-websocket)
- [Spring Framework — WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Cross-Site Request Forgery](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF)
