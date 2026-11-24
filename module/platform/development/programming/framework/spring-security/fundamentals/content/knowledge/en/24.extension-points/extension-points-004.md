# Converting Input Data into Authentication

> **Topic:** Extension points in Spring Security — fundamentals. This lesson focuses on the Spring Security **Servlet stack** (Spring Boot 3.x, Spring Security 6.x, Java 17+). With WebFlux, similar concepts are implemented using dedicated reactive APIs; `HttpServletRequest` and Servlet filters cannot be used directly in WebFlux.

## 1. Why Convert Input into Authentication?

A request can carry identity information in many forms:

- Login form: `username=alice&password=...`.
- HTTP Basic: `Authorization: Basic ...`.
- Bearer access token: `Authorization: Bearer ...`.
- Application-defined API key, e.g., `X-Api-Key: ...`.
- Client certificate or assertion in a supported mechanism.

**Input data is not yet a trusted identity.** Spring Security needs to represent an authentication request as an object implementing `org.springframework.security.core.Authentication`. Then, `AuthenticationManager` and the appropriate `AuthenticationProvider` verify the evidence, returning an authenticated `Authentication` or throwing `AuthenticationException`.

This is an important **extension point**: when an application has a custom way of sending credentials, you can replace how **input is extracted and packaged**, while keeping a consistent authentication and authorization architecture.

Role diagram:

~~~mermaid
flowchart LR
    A["HTTP request<br/>header / form / token"] --> B["AuthenticationConverter<br/>read + parse input"]
    B -->|"Unauthenticated Authentication"| C["AuthenticationManager"]
    C --> D["AuthenticationProvider<br/>verify evidence"]
    D -->|"Authenticated Authentication"| E["SecurityContext"]
    E --> F["Authorization<br/>check permissions"]
    B -->|"null: no matching authentication request"| G["Continue filter chain"]
    B -->|"AuthenticationException"| H["Authentication error response"]
    D -->|"AuthenticationException"| H
~~~

**Core point:** the converter answers "what evidence is the client presenting?", while the provider/manager answers "is that evidence trustworthy?". Never grant permissions based on strings self-declared by the client inside the converter.

## 2. The Authentication Object Before and After Authentication

`Authentication` serves both as the **input** to the authentication process and as the **result** representing the user/application after authentication.

Properties to understand:

| Property | Before authentication | After successful authentication |
|---|---|---|
| `principal` | May be a self-claimed username, expected ID, or unknown | Server-verified identity, e.g., `UserDetails` or client ID |
| `credentials` | Password, API key, token… to be checked | Should be erased or not retained when no longer needed |
| `authorities` | Self-claimed roles/scopes from the client must not be trusted | Permissions verified by the server or mapped from valid evidence |
| `isAuthenticated()` | `false` | Normally `true`, set by a trusted component after verification |

Example with username/password:

~~~java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "secret-from-request");

// requestToken.isAuthenticated() == false
Authentication result = authenticationManager.authenticate(requestToken);
// If successful, result typically has verified principal + authorities.
~~~

The snippet above is an **illustration requiring a configured `authenticationManager`**; it is not a standalone Java program and produces no stdout. Do not call `UsernamePasswordAuthenticationToken.authenticated(...)` right after merely reading username/password from the request. That factory is meant for code that **already has a trusted basis** to create an authentication result.

An unauthenticated `Authentication` is normally just a **request for verification**. Even if it contains `principal="admin"` or `authorities=["ROLE_ADMIN"]` from a payload, those values cannot automatically become real permissions.

## 3. The AuthenticationConverter Extension Point

For the Servlet stack, Spring Security provides the interface:

~~~java
package org.springframework.security.web.authentication;

public interface AuthenticationConverter {
    Authentication convert(jakarta.servlet.http.HttpServletRequest request);
}
~~~

This is an abbreviated signature for learning the concept; `@Nullable` annotations and other metadata are omitted. `convert(...)` works with the HTTP request and returns one of three outcomes:

1. **Return an unauthenticated `Authentication`:** contains enough data for the scheme the converter handles, e.g., extracting username and password and creating `UsernamePasswordAuthenticationToken.unauthenticated(...)`.
2. **Return `null`:** no authentication request recognized by this converter was found; the filter using the converter can skip this authentication attempt and let the request proceed. `null` **does not mean login succeeded**.
3. **Throw `AuthenticationException`:** the request actively uses that scheme, but the data is malformed, has duplicate headers, blank credentials, or fails to parse per the contract. Typically use `BadCredentialsException`, and do not arbitrarily throw `RuntimeException` causing the server to return 500.

Example of a converter from a custom header:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationConverter;

final class ExampleHeaderConverter implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String username = request.getHeader("X-Demo-User");
        String password = request.getHeader("X-Demo-Password");

        if (username == null && password == null) {
            return null;
        }
        if (username == null || username.isBlank()
                || password == null || password.isBlank()) {
            throw new BadCredentialsException("Incomplete credentials");
        }
        return UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
    }
}
~~~

This example is **only to illustrate the converter contract**, is not yet wired into a filter/manager, and is not a custom password-transmission approach to use in production. Real applications should use standard mechanisms such as Basic over HTTPS, protected form login, or OAuth2/OIDC when appropriate.

### Distinguishing three easily confused tasks

- **Parsing/normalization:** identify headers or fields, validate format, and build the input token → converter.
- **Verification:** look up the user, verify password hash/token signature/revocation/issuer/audience, resolve the real principal → provider/manager or dedicated authentication component.
- **Authorization:** check `GrantedAuthority`, roles, scopes, and endpoint policies → `AuthorizationManager`/method security.

A converter should not decide `ROLE_ADMIN`, create trusted tokens, or write `SecurityContextHolder` directly. This separation makes it easy to test and swap input formats without breaking security policies.

## 4. Where Is a Converter Used in the Filter Chain?

A converter **does not run automatically** just by being a `@Component` bean. A filter/feature must call it and handle the result. A common pattern:

~~~text
Request -> SecurityFilterChain
    -> Authentication filter matching the request
        -> AuthenticationConverter.convert(request)
           - null: do not authenticate with this scheme
           - Unauthenticated Authentication:
                -> AuthenticationManager.authenticate(...)
                    -> AuthenticationProvider.authenticate(...)
                       -> success: authenticated Authentication
                       -> failure: AuthenticationException
           - exception: respond with error per filter mechanism
        -> success: SecurityContext or success handler
    -> AuthorizationFilter
    -> Controller
~~~

`AuthenticationFilter` is a general-purpose filter that can accept an `AuthenticationConverter` and an `AuthenticationManager`, usually configured with a **request matcher**, **success handler**, and **failure handler** for a dedicated authentication request such as a login endpoint. Upon success, this type of filter typically hands response handling off to the success handler; do not assume it always continues to the original controller.

For built-in mechanisms, Spring Security already provides matching credential extraction/conversion steps: HTTP Basic uses `BasicAuthenticationConverter`; a resource server accepts Bearer tokens via dedicated OAuth2 components. **Prefer built-in mechanisms** when the protocol is standardized.

If you want to **authenticate every request** with an API key and then continue processing the API endpoint, you can build a `OncePerRequestFilter` that invokes the converter and manager, stores the result in a new `SecurityContext`, and calls `filterChain.doFilter(...)`. The example below demonstrates this approach. This is a deliberate choice because it clearly shows the full "request → converter → manager/provider → context → authorization" path.

## 5. Complete Example: Converting X-Api-Key into Authentication

**Goal:** `GET /api/data` requires the `X-Api-Key` header. The converter only reads the header and creates an **unauthenticated** token. The provider compares the API key against a server-side demo value and returns an **authenticated** token carrying `ROLE_READER`. The filter puts the token into the `SecurityContext` for the **current request**. Only then does the controller run.

Uses **Java 17+**, **Spring Boot 3.5.0 / Spring Security 6.x**, Maven. The key value in the example is public for learning purposes; never use it as a production secret.

Structure:

~~~text
api-key-demo/
├── pom.xml
└── src/main/java/com/example/apikey/
    ├── ApiKeyDemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

### 5.1. pom.xml

~~~xml
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
    <artifactId>api-key-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 5.2. ApiKeyDemoApplication.java

~~~java
package com.example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

All demo components are grouped into a single file for ease of running. In a real project, the converter, token, provider, and filter can live in separate classes/files. **Do not register the custom filter as a `@Component`** in this example to prevent Spring Boot from auto-registering it a second time with the servlet container.

~~~java
package com.example.apikey;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
public class SecurityConfig {

    private static final String HEADER = "X-Api-Key";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint entryPoint = (request, response, failure) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                    "{\"error\":\"authentication_required\"}");
        };

        AuthenticationConverter converter = new HeaderApiKeyConverter();
        AuthenticationManager manager =
                new ProviderManager(new DemoApiKeyProvider());

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .addFilterAfter(
                new ApiKeyFilter(converter, manager, entryPoint),
                LogoutFilter.class);

        return http.build();
    }

    // Token created by converter: untrusted; created by provider: trusted.
    private static final class ApiKeyToken extends AbstractAuthenticationToken {
        private final Object principal;
        private final Object credentials;

        private ApiKeyToken(
                Object principal,
                Object credentials,
                Collection<? extends GrantedAuthority> authorities,
                boolean trusted) {
            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(trusted);
        }

        static ApiKeyToken unauthenticated(String suppliedKey) {
            return new ApiKeyToken(null, suppliedKey, List.of(), false);
        }

        static ApiKeyToken verified(
                String trustedPrincipal,
                Collection<? extends GrantedAuthority> authorities) {
            return new ApiKeyToken(trustedPrincipal, null, authorities, true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return credentials;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                        "Only the verified factory can create trusted tokens");
            }
            super.setAuthenticated(false);
        }
    }

    // 1. Only parses HTTP input and creates an unauthenticated Authentication.
    private static final class HeaderApiKeyConverter
            implements AuthenticationConverter {

        @Override
        public Authentication convert(HttpServletRequest request) {
            Enumeration<String> values = request.getHeaders(HEADER);
            if (values == null || !values.hasMoreElements()) {
                return null;
            }

            String suppliedKey = values.nextElement();
            if (values.hasMoreElements()
                    || suppliedKey == null
                    || suppliedKey.isBlank()) {
                throw new BadCredentialsException("Malformed API key header");
            }

            return ApiKeyToken.unauthenticated(suppliedKey);
        }
    }

    // 2. Verifies evidence; authorities and principal are issued by the server.
    private static final class DemoApiKeyProvider
            implements AuthenticationProvider {

        private static final byte[] EXPECTED =
                "demo-key-123".getBytes(StandardCharsets.UTF_8);

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (!(authentication instanceof ApiKeyToken token)) {
                return null;
            }

            Object raw = token.getCredentials();
            if (!(raw instanceof String suppliedKey)) {
                throw new BadCredentialsException("Missing API key");
            }
            if (!MessageDigest.isEqual(
                    EXPECTED,
                    suppliedKey.getBytes(StandardCharsets.UTF_8))) {
                throw new BadCredentialsException("Invalid API key");
            }

            return ApiKeyToken.verified(
                    "demo-client",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));
        }

        @Override
        public boolean supports(Class<?> type) {
            return ApiKeyToken.class.isAssignableFrom(type);
        }
    }

    // 3. Uses converter + manager for each /api/... request.
    private static final class ApiKeyFilter extends OncePerRequestFilter {

        private final AuthenticationConverter converter;
        private final AuthenticationManager manager;
        private final AuthenticationEntryPoint entryPoint;

        ApiKeyFilter(
                AuthenticationConverter converter,
                AuthenticationManager manager,
                AuthenticationEntryPoint entryPoint) {
            this.converter = converter;
            this.manager = manager;
            this.entryPoint = entryPoint;
        }

        @Override
        protected boolean shouldNotFilter(HttpServletRequest request) {
            return !request.getServletPath().startsWith("/api/");
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            Authentication verified = null;
            try {
                Authentication candidate = converter.convert(request);
                if (candidate != null) {
                    verified = manager.authenticate(candidate);
                }
            } catch (org.springframework.security.core.AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                entryPoint.commence(request, response, ex);
                return;
            }

            if (verified != null) {
                SecurityContext context =
                        SecurityContextHolder.createEmptyContext();
                context.setAuthentication(verified);
                SecurityContextHolder.setContext(context);
            }

            chain.doFilter(request, response);
        }
    }
}
~~~

**How the components collaborate:**

1. `HeaderApiKeyConverter` only checks presence, uniqueness, and basic format of the header; it returns `ApiKeyToken.unauthenticated(...)`. With only the converter, **no one is authenticated yet**.
2. `DemoApiKeyProvider` verifies the key; when valid, it assigns the `demo-client` principal and `ROLE_READER` authority and omits the API key from the result token. Clients cannot declare roles via headers.
3. `ProviderManager` dispatches to providers by token type. `supports(...)` determines which provider can handle this `Authentication` type; if no provider matches, authentication does not succeed.
4. `ApiKeyFilter` places the **verified** `Authentication` into a fresh `SecurityContext` before letting the filter chain continue. If the header is absent, the converter returns `null`: the request proceeds and the `authenticated()` rule denies protected endpoints; `ExceptionTranslationFilter` invokes the entry point for anonymous callers.
5. If the header is malformed or the key is wrong, the converter/provider throws `AuthenticationException`; the filter catches the exception around **the conversion/authentication step itself** and invokes the entry point to return 401. `chain.doFilter(...)` is **outside** this `try/catch` so it does not accidentally swallow errors from downstream filters or controllers.
6. `SessionCreationPolicy.STATELESS` means the example does not store `SecurityContext` in an HTTP session for subsequent calls. The client must send a valid key on every protected request.
7. Basic and form login are disabled so they do not compete with the custom header. Placing the custom filter **after `LogoutFilter`** ensures authentication runs before authorization.
8. CSRF protection **remains at its default**. The example only uses `GET`; if state-changing APIs are added, CSRF design must be based on client type and credential delivery mechanism, rather than disabling it by default for every application.

**Note on the demo API key:** `demo-key-123` is hard-coded and shown openly so learners can reproduce results. Production versions require a secure secret manager/config, keys with sufficient entropy, rotation, revocation, permission scoping, HTTPS, rate limiting, and mapping identity/authorities from a trusted system. Using `MessageDigest.isEqual` only illustrates avoiding naive string equality; it does not replace a full secure API key design.

### 5.4. DemoController.java

~~~java
package com.example.apikey;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/data")
    public String data(Authentication authentication) {
        return "data:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }
}
~~~

### 5.5. Running and Observing Results

Requires JDK 17+ and Maven installed. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Second terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/data
curl -i -H "X-Api-Key: wrong" http://localhost:8080/api/data
curl -i -H "X-Api-Key: demo-key-123" http://localhost:8080/api/data
curl -i -H "X-Api-Key: demo-key-123" http://localhost:8080/api/admin
~~~

With Windows PowerShell, use `curl.exe` instead of the `curl` alias if needed. Only the request lines above count as test steps; status and body can be seen directly in the `-i` output.

| Case | Expected status | What is observed |
|---|---|---|
| `GET /public` | `200` | Body `public` |
| `GET /api/data` without `X-Api-Key` | `401` | JSON body `{"error":"authentication_required"}` |
| `GET /api/data` key `wrong` | `401` | Same error JSON, without leaking detailed cause |
| `GET /api/data` key `demo-key-123` | `200` | Exact body `data:demo-client` |
| `GET /api/admin` valid key | `403` | Authenticated but only has `ROLE_READER`, lacking `ROLE_ADMIN` |

Note: for `403`, the example only guarantees the **status**; the body is determined by the default handler/servlet container. Auxiliary headers such as `Date`, `Content-Length`, and `Cache-Control` may also vary by environment. A successful request **does not log in subsequent requests** because this configuration is stateless.

Try two more cases:

~~~bash
curl -i -H "X-Api-Key:" http://localhost:8080/api/data
curl -i -H "X-Api-Key: demo-key-123" -H "X-Api-Key: another" http://localhost:8080/api/data
~~~

The second line tests the policy rejecting **two header values**. The first line with an empty header may be normalized by a client/proxy to "no header", yet both paths must result in `401` for protected endpoints.

## 6. Why Conversion Is Not Yet Authentication

The trace below highlights the key takeaway:

~~~text
X-Api-Key: demo-key-123
    |
    v
HeaderApiKeyConverter.convert(request)
    -> ApiKeyToken(credentials="demo-key-123", authenticated=false)
    |
    v
ProviderManager.authenticate(token)
    -> DemoApiKeyProvider verifies secret
    -> ApiKeyToken(principal="demo-client",
                   authorities=["ROLE_READER"],
                   credentials=null,
                   authenticated=true)
    |
    v
SecurityContextHolder: verified Authentication
    |
    v
AuthorizationFilter: /api/data -> allow; /api/admin -> deny
~~~

If `AuthenticationConverter` called `setAuthenticated(true)` itself or built a trusted token using roles sent by the client, an attacker could bypass proving identity. The input token object is not verified evidence. Therefore, the example defines two separate factories, forbids flipping an untrusted token to `authenticated=true` via a public setter, and allows only the provider to produce authenticated tokens.

Choosing the **`Authentication` type** also matters. `ProviderManager` selects an `AuthenticationProvider` via `supports(Class<?> type)`. If the converter returns `ApiKeyToken` while the system only has `DaoAuthenticationProvider` supporting username/password, no matching provider will be found. Adding a converter does not automatically create a matching provider.

## 7. Common Input Conversion Patterns

| Input source | Typical token/input | Next verification needed |
|---|---|---|
| Form login username/password | Unauthenticated `UsernamePasswordAuthenticationToken` | Account, password hash, account status |
| HTTP Basic | Username/password extracted from Basic header | Username/password via suitable provider |
| Bearer token | Bearer credential representation (mechanism-dependent) | Signature, timestamps, issuer, audience, permissions, and token policies |
| Custom API key | Unauthenticated custom `Authentication` | Whether key exists/is valid/unexpired, and which principal it maps to |
| Client certificate | Certificate details provided by TLS/container | Trust chain, validity, identity mapping, related policies |

**Do not infer from `Authorization: Bearer ...` that the token is valid.** Header reading only handles syntax/format; validity evaluation must rely on OAuth2 Resource Server or a dedicated provider.

**Do not confuse `JwtAuthenticationConverter` with Servlet's `AuthenticationConverter`:** `JwtAuthenticationConverter` receives a `Jwt` that has already been decoded/verified by resource server, and maps it into an `AbstractAuthenticationToken` (specifically principal/authorities). Meanwhile, the `AuthenticationConverter` covered here receives `HttpServletRequest` directly. Both convert data, but take inputs at **two different stages**.

If an application supports multiple schemes, you can use `DelegatingAuthenticationConverter` (available in Spring Security 6.3+ versions) to try multiple converters in order and take the **first non-`null`** result. Design request matchers and ordering clearly: do not let a converter for scheme A swallow errors from scheme B or accept an unexpected header.

## 8. Rules for Designing Safe Converters

### 8.1. Distinguish absence from malformation

- **No credentials for the scheme**: return `null` so the filter can decide whether to proceed.
- **Credentials for the scheme are present but malformed**: throw an appropriate `AuthenticationException` to return an authentication error.
- **Credentials appear well-formed**: build an **unauthenticated token** and pass it to the manager/provider.

If a converter returns `null` even when a header was sent with invalid syntax, another filter might treat the request as anonymous and lose the authentication intent. This makes error handling inconsistent, especially with multiple schemes.

### 8.2. Do not trust client-supplied attributes

Avoid assigning authorities from `X-Role`, `isAdmin=true`, a username in the request, or an unverified JWT. Only the server or a trusted issuer after verification is the source of principal and permissions. When supporting multi-tenancy, bind the key/token to the tenant and actual permissions of the identity, rather than merely parsing a tenant ID and granting access.

### 8.3. Handle input robustly

Limit header/body lengths, and check for duplicate values, blank values, encoding, and syntax. For JSON credentials, use a standard parser, avoid manual string splitting, and prevent the request body from being read twice by unaware components. Do not call `getParameter(...)` assuming it reads JSON; `getParameter` is mainly for query/form params.

### 8.4. Do not leak secrets

Use TLS; never put passwords/API keys/tokens in query strings; never log `Authorization`, `Cookie`, or custom credential headers; never return `AuthenticationException.getMessage()` verbatim to clients. When storing `Authentication` in context/session, avoid retaining `credentials`. If a token can be cached or logged, review its `toString()` implementation as well.

### 8.5. Correct filter order and SecurityContext lifecycle

The authentication filter must run before the authorization decision for the request; Spring Security populates and clears `SecurityContextHolder` per the request lifecycle. In a custom filter, **create a new `SecurityContext`** to hold the trusted result; do not casually place an unauthenticated token into the context. If the app uses session-based login, configure persisting `SecurityContext` with an appropriate `SecurityContextRepository`; calling `setContext(...)` alone does not guarantee persistence across subsequent requests.

`AuthenticationFilter`, built-in filters, and a custom `OncePerRequestFilter` have **different success/failure handling policies**. Choose the hook that matches the desired behavior, especially when redirects, JSON responses, or continuing to controllers are needed.

### 8.6. Separate request matchers and response protocols

`/api/login`, `/api/**`, browser pages, or webhooks may need different converters/filters. Only enable a converter within its intended scope. With HTTP Basic/Bearer, `401` usually requires a protocol-compliant `WWW-Authenticate` header; do not send a `Basic` challenge for a custom API key if the server does not support Basic. `403` is typically used for an authenticated user lacking permissions. Cases blocked by the CSRF filter follow a separate protection path and may return `403` before a custom converter runs.

## 9. Common Mistakes When Extending

1. **Converter returns a token with `authenticated=true`:** trust boundary bug. Switch to an unauthenticated token and let the provider return the trusted token.
2. **Converter creates `ROLE_ADMIN` from a header/query:** privilege escalation bug. Only take permissions from server-verified data.
3. **`ProviderNotFoundException` when calling manager:** the token type returned by the converter has no matching `AuthenticationProvider.supports(...)`; check token class, the manager wired to the filter, and the provider list.
4. **Converter returns `null` for malformed credentials:** wrong semantics, which can cause the error to be treated as anonymous. Distinguish "not sent" from "sent invalidly".
5. **Key is valid yet the endpoint still returns `401`:** check whether the filter is in the right `SecurityFilterChain`, whether `shouldNotFilter` and request matchers match, whether the provider returns an authenticated token, and whether the context is set before authorization.
6. **Key is valid yet the endpoint returns `403`:** authentication succeeded, but role/scope is missing. `hasRole("ADMIN")` requires `ROLE_ADMIN`; the converter is not responsible for fixing permissions.
7. **Custom filter runs twice:** if the filter is both a Spring bean auto-registered by Boot into the servlet container and added inside `HttpSecurity`, it can run outside the chain in the wrong order. Avoid auto-registration or disable registration outside Spring Security.
8. **Catching every `Exception` as 401:** programming bugs, database errors, or authorization errors get hidden. Only handle `AuthenticationException` at the authentication step; let other errors reach appropriate handlers.
9. **Authentication does not persist on the next request:** inspect stateless/session policy and `SecurityContextRepository`. The current demo intentionally requires the API key every time.
10. **Using Servlet classes in a reactive application:** WebFlux uses `ServerWebExchange`, `ServerAuthenticationConverter`, `AuthenticationWebFilter`, and reactive security context; it is a different pipeline.

When debugging in development, enable selectively:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Use logs to inspect `SecurityFilterChain` and filter ordering; **do not enable logging credentials**. Test branches with/without headers, wrong keys, valid keys, and missing roles rather than testing only the happy path.

## 10. Self-Check and Practice Exercises

1. Why should `convert(request)` not query the database and return `authenticated=true` itself? How does separating the two phases help testing?
2. If `X-Api-Key` is absent from the request, what does `HeaderApiKeyConverter` return? Why is `/api/data` still inaccessible?
3. Why does `/api/admin` return `403` when the API key is valid, even though the provider authenticated successfully?
4. If an API key is sent twice in two headers, which branch handles the error? What is the benefit of using `AuthenticationException`?
5. What happens if `ApiKeyFilter` is placed **after** `AuthorizationFilter`? Why can the result be wrong?
6. Modify `DemoApiKeyProvider` to check multiple externalized keys with expiration dates and distinct principals/roles. Keep the converter **unchanged**; that is the benefit of this extension point.
7. Add an API key with server-granted `ROLE_ADMIN` and prove `/api/admin` succeeds only with that key. Never accept roles from the request to decide permissions.
8. Design tests for: missing header, blank header, duplicate header, wrong key, valid key, missing authority, converter returning `null`, and provider not supporting the token.

**You have completed this lesson when you can pinpoint:** where HTTP data is converted into a token; who verifies the evidence; who puts the authenticated `Authentication` into the context; who decides 401/403; why the converter is not the place to "trust" the client; and how to change the input format while keeping the provider and authorization consistent.

## Official References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — AuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationConverter.html)
- [Spring Security — AuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html)
- [Spring Security — Servlet filter chain, adding filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
