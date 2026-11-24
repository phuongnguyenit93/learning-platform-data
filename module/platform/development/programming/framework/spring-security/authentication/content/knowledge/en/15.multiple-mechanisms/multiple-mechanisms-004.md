# Determining Precedence When a Request Carries Multiple Credentials

## 1. An HTTP Request Can Carry Multiple Credentials at Once

In a Spring Security Servlet application, a single request can simultaneously carry:

- A `JSESSIONID` cookie pointing to an HTTP session authenticated via form login.
- An `Authorization: Basic …` header containing username/password.
- An `Authorization: Bearer …` header containing an access token.
- A custom header such as `X-API-Key`.
- A TLS client certificate, or an identity forwarded by a trusted reverse proxy.
- A remember-me cookie or credentials from another login mechanism.

For example, the request below carries **two different authentication sources**:

~~~http
GET /api/me HTTP/1.1
Host: example.test
Cookie: JSESSIONID=<browser-session-id>
Authorization: Basic <base64-api-user-password>
~~~

Suppose the session belongs to `web-alice` while the Basic credentials belong to `api-reader`. Which identity does the backend use to evaluate permissions?

There is no universal rule like **“cookies always win”**, **“Authorization always wins”**, or **“the highest-security credential automatically wins”**. The outcome depends on the Spring Security configuration: which `SecurityFilterChain` the request enters, which filters are enabled, how each filter recognizes credentials, whether any filter terminates the request, and the final `Authentication` object placed in `SecurityContext`.

An easily overlooked detail: `Authorization` normally holds **one authentication scheme at a time** (for example `Basic` *or* `Bearer`). Never combine two schemes into a single value. If a client or proxy sends multiple or conflicting `Authorization` headers, handle them according to an explicit policy (usually rejecting ambiguous requests) rather than trusting whichever “first” or “last” line the container picks.

This lesson covers **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Servlet/Spring MVC applications**. It focuses on how to **determine precedence and select the identity source** when multiple mechanisms exist, rather than collapsing every mechanism into one configuration.

## 2. Four Kinds of “Precedence” Must Be Distinguished

When debugging a request carrying multiple credentials, ask these four questions in order:

| Decision layer | Components | Question to answer |
| --- | --- | --- |
| **1. Chain selection order** | `FilterChainProxy` and `SecurityFilterChain`, `@Order`, `securityMatcher` | *Which chain* handles this request? |
| **2. Filter order inside the chain** | `SecurityContextHolderFilter`, authentication filters, `AnonymousAuthenticationFilter`, `AuthorizationFilter`… | Which filters *actually run*, which credentials do they read, and do they overwrite context or terminate the request? |
| **3. Provider/manager order** | `AuthenticationManager`, typically `ProviderManager` and `AuthenticationProvider`s | Once a filter builds an authentication token, which provider inspects that token first? |
| **4. Identity source policy** | API/web design, session policy, authentication entry point, authorization rules | Does the application **intend** to accept, ignore, or reject simultaneous credentials? |

These four orderings **do not substitute for one another**:

- Putting `@Order(1)` on a `SecurityFilterChain` does **not** mean HTTP Basic always has higher priority than JWT on every URL.
- Adding `.requestMatchers("/api/**").authenticated()` in authorization does **not** select the API chain; you need `http.securityMatcher(...)` at the chain level.
- Changing `AuthenticationProvider` order does not change the order of `BasicAuthenticationFilter` and `BearerTokenAuthenticationFilter`.
- Enabling two login methods in the same chain does not create an automatic rule to “fall back when the first method fails”.

**Best goal:** select allowed authentication mechanisms per **endpoint or protocol contract**, then test conflicting credential pairs. Avoid relying on accidental filter ordering resulting from configuration.

## 3. Step 1: FilterChainProxy Picks the First Matching Chain

Spring Security Servlet receives requests through `FilterChainProxy`. An application can register multiple `SecurityFilterChain` beans:

~~~text
Request: GET /api/me, Cookie + Authorization: Basic
                     |
                     v
              FilterChainProxy
                     |
           @Order(1) apiChain
           securityMatcher("/api/**")?
                     |
                    YES
                     |
                SELECT apiChain
                     |
            Do not evaluate webChain
                     |
            Filters of apiChain
                     |
                Controller
~~~

Only the **first matching chain** is invoked. Spring Security does not merge filters from the API chain with filters from the Web chain. Nor does it move on to a lower-priority chain if the first chain returns `401`, `403`, or fails authentication.

Suppose there are two chains:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    // ...
    return http.build();
}

@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    // No securityMatcher declared -> fallback for remaining requests.
    // ...
    return http.build();
}
~~~

This snippet **illustrates matcher placement**, not a complete configuration; runnable code appears in section 8.

A routing table:

| Request URL | Selected chain | What decides it? |
| --- | --- | --- |
| `GET /api/me` | API | `@Order(1)` is evaluated first; matcher `/api/**` matches. |
| `GET /api/admin` | API | Same API prefix. |
| `GET /web/me` | Web | Does not match API; falls back to Web. |
| `POST /login` | Web | Does not match API; Web's form login filter handles it. |
| `GET /unknown` | Web | Fallback protects new routes too; leaves no gap. |

### 3.1. securityMatcher vs. requestMatchers

Inside one chain:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/admin").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

- `securityMatcher("/api/**")`: should this chain **be selected for the request**?
- `requestMatchers("/api/admin")`: once the chain is selected, what **permissions** does this specific path require?
- `anyRequest()` in the API chain applies only to **requests that entered the API chain**; it does not turn the chain into a system-wide fallback.

If all chains have narrow matchers and a URL matches none of them, that URL can end up **unprotected by Spring Security**. Always design a fallback or a policy covering the entire served URL space.

### 3.2. @Order Is Not “Credential Priority”

`@Order(1)` has higher precedence than `@Order(2)` during **chain selection**. However, if both Basic and Bearer are enabled *inside the same chain*, the chain bean's `@Order` does not decide whether Basic or Bearer wins. In that case, you must inspect the actual filter set and the policy for conflicting credentials.

## 4. Step 2: Which Filters Are Present and in What Order Do They Run?

In a typical Servlet chain, the flow can be visualized as:

~~~text
SecurityContextHolderFilter / SecurityContextRepository
     → (restores Authentication from session, or empty context)
CORS / CSRF / security headers (if configured)
     → Enabled authentication filters
        (form login, Basic, Bearer, custom, remember-me...)
     → AnonymousAuthenticationFilter if still unauthenticated
     → ExceptionTranslationFilter
     → AuthorizationFilter
     → Controller
~~~

This is a **conceptual diagram**, not an exhaustive list or exact filter position for every version. Spring Security uses a deterministic filter order; inspect the actual filter list logged at runtime instead of guessing from the order of DSL lines in code.

Three behaviors of an authentication filter are key:

1. **No matching credential scheme seen:** the filter may do nothing and call the next filter.
2. **Valid credentials present:** the filter may create an authenticated `Authentication` and set it in `SecurityContextHolder`.
3. **Invalid or unsuitable credentials:** the filter may clear the context and invoke `AuthenticationEntryPoint`, returning 401 or stopping processing. Thus you cannot assume “try every mechanism until one succeeds”.

For example, if a chain enables both `httpBasic` and session-based form login: when a request arrives, the context from the session may already be restored. A Basic header later in the chain may be processed, ignored, replace the authentication, or fail the request depending on internal conditions inside the filter and the version/configuration. There is no universal contract that **session always beats Basic**. Nor can you deduce from `SecurityContextHolderFilter` running earlier that the session identity is the final identity.

Similarly, if the same chain enables `oauth2ResourceServer` for Bearer, `BearerTokenAuthenticationFilter` inspects Bearer tokens according to the configured resolver. When a token is invalid, it can call the entry point and terminate the request immediately, rather than falling back to a valid session.

### 4.1. SecurityContext Is Not a Place to “Merge All Users”

`SecurityContextHolder.getContext().getAuthentication()` is the single identity visible at the moment the context is read. It is not a simultaneous list of:

~~~text
Authenticated by session: alice
Authenticated by Basic: bob
Authenticated by Bearer: carol
~~~

nor does it automatically merge the roles of those principals. Any “merging” mechanism requires explicit design and verification (for example, multi-factor authentication on **the same identity**), and must never accidentally combine privileges from different accounts.

When a filter creates a new `Authentication`, verify whether it overwrites the current context, whether it saves to `SecurityContextRepository`, and whether subsequent requests inherit the state. In Spring Security 6, a custom filter or controller that wants to **persist authentication across requests** must save the context explicitly using an appropriate repository.

### 4.2. How STATELESS and Session Cookies Affect the Outcome

- A `SessionCreationPolicy.STATELESS` chain does not use an HTTP session to obtain `SecurityContext` for authentication and does not create sessions for security context persistence. It fits Basic, Bearer, or per-request credentials.
- A standard form-login chain stores `SecurityContext` in the session; the browser sends the session cookie on subsequent requests.
- For a request carrying both a cookie and a Basic header, if the **stateless API chain only enables Basic**, Basic is the identity source accepted by that chain; any Web cookie present is not used to authenticate the API request.
- If the **web chain only enables form login/session**, a Basic header is not handled by a `BasicAuthenticationFilter` in that chain; the session is the identity source. Without a valid session, the user must log in via the form.

**Do not confuse** “stateless” with “disable all CSRF/CORS” or “the browser will not send cookies”. Browsers can still send cookies depending on site/policy; the question is whether the chain uses that cookie to establish authentication.

## 5. Step 3: AuthenticationProviders Are Evaluated Only After a Filter Creates a Token

Suppose `BasicAuthenticationFilter` reads a syntactically valid Basic header and creates a `UsernamePasswordAuthenticationToken`. It passes this object to `AuthenticationManager`. The manager typically uses `ProviderManager` to evaluate `AuthenticationProvider`s in order.

~~~text
BasicAuthenticationFilter
     └─ UsernamePasswordAuthenticationToken
           └─ ProviderManager
                 ├─ Provider A: supports(token)?
                 │      ├─ no → skip
                 │      ├─ null → try next provider
                 │      ├─ success → return Authentication
                 │      └─ AuthenticationException → handle by type
                 └─ Provider B ...
~~~

How this differs from chain selection:

- `AuthenticationProvider.supports(Class<?>)` inspects the **Authentication token type**, not the URI for selecting a Spring Security filter chain.
- Returning `null` from a provider means it could not handle that instance, so the manager may try another provider.
- A typical `BadCredentialsException` may be recorded while the manager continues evaluating later providers; if a later provider succeeds, the manager may return success.
- Cases like `AccountStatusException` or `InternalAuthenticationServiceException` trigger early termination in `ProviderManager`.
- A successful provider does not force other authentication filters in the same chain to run as well.

Therefore, **provider order** is distinct from **authentication mechanism order**. When Basic and Bearer coexist, each mechanism typically produces a different token class (such as `UsernamePasswordAuthenticationToken` and `BearerTokenAuthenticationToken`); you must inspect the filters, manager, and providers together.

Never use provider fallback as a bypass when a stronger credential is rejected. If policy states an invalid Bearer token must be rejected, do not convert that failure into `null` so a weaker API key or session cookie accidentally accepts the request.

## 6. Design the Precedence Policy Before Writing Filters

An easily testable strategy is to **partition endpoints by allowed credential source**:

| Endpoint group | Accepted authentication source | Other credentials in request | Proper failure behavior |
| --- | --- | --- | --- |
| Programmatic `/api/**` | Basic or Bearer (choose **one** standard per API group) | Browser session cookies are ignored by the stateless API chain | Missing/invalid API credentials → 401; no session fallback. |
| Browser `/web/**` | Form login + HTTP session | Basic/Bearer headers are not processed by Web if those filters are off | Missing session → redirect to login; valid session missing role → 403. |
| `/admin/**` | Defined strong mechanism and admin privileges | No self-elevation via an anonymous “second credential” | Failing authentication/policy → deny. |
| Endpoint genuinely supporting multiple schemes on one URL | **Written** precedence policy: pick one or reject simultaneous credentials | Inspect header types, cookies, and tokens in one unified layer | Present but invalid credential → fail closed, no silent downgrade. |

There are two sound designs depending on the product:

**Approach A — Clear endpoint partitioning (preferred for mixed web/API apps):** `/api/**` uses stateless tokens/headers; `/web/**` uses sessions. Two filters never race to overwrite `SecurityContext`. When an API call receives both a cookie and a header, only the source allowed on the API chain takes effect.

**Approach B — Same URL must accept multiple mechanisms:** define request-level ordering/policy, for example “if `Authorization` is present, it **must** be verified; even if the header is invalid, never fall back to the cookie; check the session only when no header is present”, or “if both sources appear together, reject with 400/401”. Implement this via `RequestMatcher`, an authentication converter/filter, or a tested coordinator component—never rely solely on the declaration order of two DSL blocks.

For sensitive data, a policy that **rejects ambiguous credentials** is easier to defend and debug than trying to blend identities. However, remember that browsers can attach cookies automatically to API requests even when client code explicitly sends a header, so if you choose to reject both, design your origins, domains, and cookie scopes accordingly.

### 6.1. “Header Present” Differs from “Header Valid”

When policy says headers take precedence over sessions, consider three cases:

1. **No `Authorization` header**: by design, the session cookie may be used.
2. **`Authorization: Bearer <token>` present, but invalid/expired**: **never** silently ignore Bearer and use the session cookie; that can create a downgrade path.
3. **`Authorization` with an unknown or malformed scheme**: define explicit behavior; usually reject rather than treating it as “no header present”.

Avoid logic like “if JWT parsing fails, let the request continue with the cookie user” when security policy requires tokens to be the authoritative source. Distinguish “no credentials supplied” from “credentials supplied but invalid”.

## 7. Conflicting Request Example: Decide First, Then Verify

Suppose a Web session cookie holds principal `web-alice`, while a Basic header holds principal `api-reader`. The system specifies:

- `GET /api/me` → API chain uses Basic only, stateless, requires `ROLE_API`.
- `GET /web/me` → Web chain uses form login/session only, requires `ROLE_WEB`.
- `POST /login` / `POST /logout` → Web chain, standard form login and CSRF.
- Test accounts: `api-reader` has `ROLE_API`, `web-alice` has `ROLE_WEB`.

Expected results:

| Request | Credentials | Result |
| --- | --- | --- |
| `GET /api/me` | `web-alice` cookie **and** valid `api-reader` Basic | **200**, principal `api-reader`. |
| `GET /api/me` | Only `web-alice` session cookie | **401**; API does not use sessions. |
| `GET /api/me` | `web-alice` cookie + `api-reader` Basic with wrong password | **401**; cookie does not “rescue” bad API credentials. |
| `GET /api/me` | Valid `web-alice` Basic, who only has `ROLE_WEB` | **403**; authenticated, but lacks API authority. |
| `GET /web/me` | `web-alice` cookie and valid `api-reader` Basic | **200**, principal `web-alice`. |
| `GET /web/me` | Only valid `api-reader` Basic, no session | **302** to login; Web chain does not enable Basic. |
| `GET /api/me` | `Authorization: Bearer …`, no Basic | **401**; example does not configure Bearer. |
| `GET /web/me` | Expired cookie + valid Basic | **302** to login; no Basic fallback. |

This table is the **policy contract for the example below**, not the default behavior of every Spring Security application. If another app enables Basic, Bearer, and form login in the same chain, write dedicated tests for it.

## 8. Runnable Example: Two Chains Eliminating Ambiguity

The example uses **Spring Boot 3.x, Spring Security 6.x, and Java 17+**. API and Web live in the same backend but accept credentials scoped by path. No JWT server is needed to illustrate the rule; HTTP Basic on the API suffices to demonstrate conflict with session cookies.

### 8.1. Dependencies and Structure

Create a Spring Initializr project with Java 17+, Spring Web, and Spring Security. With Gradle, dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This snippet goes **into a Spring Boot project that already has the plugin and dependency management**, not a complete `build.gradle`. The Java files use package `com.example.multischeme`.

~~~text
src/main/java/com/example/multischeme/
  MultiSchemeApplication.java
  SecurityConfig.java
  IdentityController.java
src/test/java/com/example/multischeme/
  CredentialPriorityTest.java
~~~

### 8.2. MultiSchemeApplication.java

~~~java
package com.example.multischeme;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiSchemeApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiSchemeApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfig.java

~~~java
package com.example.multischeme;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("API")
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    SecurityFilterChain browserSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/web/**").hasRole("WEB")
                .anyRequest().authenticated()
            )
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("api-reader")
                .password(encoder.encode("api-pass"))
                .roles("API")
                .build(),
            User.withUsername("web-alice")
                .password(encoder.encode("web-pass"))
                .roles("WEB")
                .build()
        );
    }
}
~~~

Clear explanation of each decision:

1. `@Order(1)` and `securityMatcher("/api/**")`: the API chain is evaluated first and applies only to `/api/**` paths.
2. `anyRequest().hasRole("API")` does **not** mean every Basic user is allowed into the API. The principal must hold `ROLE_API`.
3. `SessionCreationPolicy.STATELESS`: the API does not load `SecurityContext` from a session. Thus a Web user's `JSESSIONID` cookie is not enough to authenticate API calls.
4. `formLogin(AbstractHttpConfigurer::disable)` on API: without Basic credentials, the API returns 401/Basic challenge instead of redirecting to a login page.
5. Web chain declares no `securityMatcher`: serves as fallback, keeping `/login` and `/logout` URLs within protected coverage.
6. `httpBasic(AbstractHttpConfigurer::disable)` on Web: Basic headers do not establish a Web login session.
7. `formLogin(Customizer.withDefaults())`: Web uses form login and HTTP sessions.
8. Both demo accounts share `UserDetailsService` but have different roles. Hard-coded usernames/passwords in source are for local demo only; production must store credentials securely and use HTTPS.

**Demo scope:** API endpoints are illustrated with read-only **GET** methods. Spring Security still keeps default CSRF enabled; if you add POST/PUT/PATCH/DELETE from browsers or cookie-bearing requests, evaluate CSRF separately. Never infer that stateless or HTTP Basic is automatically safe against every CSRF scenario.

### 8.4. IdentityController.java

~~~java
package com.example.multischeme;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("page", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> apiMe(Principal principal) {
        return Map.of(
            "channel", "api-basic",
            "username", principal.getName()
        );
    }

    @GetMapping("/web/me")
    public Map<String, String> webMe(Principal principal) {
        return Map.of(
            "channel", "web-session",
            "username", principal.getName()
        );
    }
}
~~~

`Principal` comes from the request after passing through Spring Security. The controller does not read cookies or decode Base64 itself. The `channel` value only shows which endpoint was called; **it is not independent evidence proving how Spring Security authenticated the call**. Evidence must come from filter configuration, sessions, and tests with conflicting credentials.

### 8.5. Testing with an HTTP Client

~~~bash
./gradlew bootRun
~~~

On Windows run `gradlew.bat bootRun`. For the local demo:

~~~bash
# API without Basic credential -> 401.
curl -i http://localhost:8080/api/me

# Valid Basic and ROLE_API -> 200.
curl -i -u api-reader:api-pass http://localhost:8080/api/me

# Valid Basic but ROLE_WEB -> 403.
curl -i -u web-alice:web-pass http://localhost:8080/api/me

# Web without session -> 302 to /login.
curl -i http://localhost:8080/web/me

# Basic header does not auto-log in to Web chain -> redirect /login.
curl -i -u api-reader:api-pass http://localhost:8080/web/me
~~~

Successful JSON response from the API:

~~~json
{"channel":"api-basic","username":"api-reader"}
~~~

After a successful Web login, `GET /web/me` with the corresponding session returns:

~~~json
{"channel":"web-session","username":"web-alice"}
~~~

Both accounts and passwords above are dummy data. The `-u username:password` flag on the command line can appear in shell history or process lists; never put real secrets into demo commands. Real environments must use HTTPS.

To observe the **simultaneous cookie and Basic header** scenario more reproducibly, use the MockMvc test in the next section. It creates a real Web session via login and attaches another user's Basic credentials in the same request.

## 9. Integration Tests: Request Carrying Both Cookie and Authorization

Use `spring-security-test` with `MockMvc` to establish a Web login session and test API/web with opposing credentials. Create file:

`src/test/java/com/example/multischeme/CredentialPriorityTest.java`

~~~java
package com.example.multischeme;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CredentialPriorityTest {

    @Autowired
    private MockMvc mvc;

    private static String basic(String username, String password) {
        String raw = username + ":" + password;
        return "Basic " + Base64.getEncoder().encodeToString(
            raw.getBytes(StandardCharsets.UTF_8));
    }

    private MockHttpSession loginWeb() throws Exception {
        MvcResult result = mvc.perform(
                post("/login")
                    .with(csrf())
                    .param("username", "web-alice")
                    .param("password", "web-pass")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session, "Form login must create a Web session");
        return session;
    }

    @Test
    void apiChoosesBasicWhenBothCredentialsExist() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/api/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "api-pass"))
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.channel").value("api-basic"))
            .andExpect(jsonPath("$.username").value("api-reader"));
    }

    @Test
    void apiDoesNotAcceptBrowserSessionByItself() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(get("/api/me").session(browserSession))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicDoesNotFallBackToValidSession() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/api/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "wrong-password"))
            )
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAuthenticatesButRejectsWrongRole() throws Exception {
        mvc.perform(
                get("/api/me")
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("web-alice", "web-pass"))
            )
            .andExpect(status().isForbidden());
    }

    @Test
    void webChoosesSessionWhenBothCredentialsExist() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/web/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "api-pass"))
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.channel").value("web-session"))
            .andExpect(jsonPath("$.username").value("web-alice"));
    }

    @Test
    void basicAloneDoesNotAuthenticateWeb() throws Exception {
        mvc.perform(
                get("/web/me")
                    .header(HttpHeaders.AUTHORIZATION,
                        basic("api-reader", "api-pass"))
            )
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void unsupportedBearerDoesNotAuthenticateBasicApi() throws Exception {
        MockHttpSession browserSession = loginWeb();

        mvc.perform(
                get("/api/me")
                    .session(browserSession)
                    .header(HttpHeaders.AUTHORIZATION,
                        "Bearer example.invalid.token")
            )
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests com.example.multischeme.CredentialPriorityTest
~~~

Or on Windows:

~~~powershell
.\gradlew.bat test --tests com.example.multischeme.CredentialPriorityTest
~~~

When the code is placed in a valid Spring Boot 3.x project with all dependencies and assertions passing, Gradle reports `BUILD SUCCESSFUL`; the tests do not print a fixed stdout string. This is the **expected test outcome**, not a record of a run already executed.

Meaning of the seven tests:

| Test | What it proves |
| --- | --- |
| `apiChoosesBasicWhenBothCredentialsExist` | Another user's Web cookie does not replace the Basic identity on the API. |
| `apiDoesNotAcceptBrowserSessionByItself` | API does not rely on Web sessions; having a cookie still returns 401 without Basic. |
| `invalidBasicDoesNotFallBackToValidSession` | Wrong Basic → 401, does not fall back to a valid session. |
| `apiAuthenticatesButRejectsWrongRole` | Valid username/password does not mean sufficient role: 403. |
| `webChoosesSessionWhenBothCredentialsExist` | Web still uses `web-alice`; an API Basic header does not replace Web's principal. |
| `basicAloneDoesNotAuthenticateWeb` | A Basic header on a Web route does not become a login session. |
| `unsupportedBearerDoesNotAuthenticateBasicApi` | Merely sending `Authorization` is not accepted; this API only enables Basic. |

The advantage of testing with **two distinct usernames** is that you cannot “coincidentally match the right person” and misjudge precedence. Never use the same user in both cookie and header: a 200 response alone does not tell you which filter actually authenticated.

However, the API policy in the example also checks `ROLE_API`, so testing the API with a Web user's cookie and the same Web user's valid Basic header yields **403** (authenticated but missing permission); to prove the session is ignored, use the **Web cookie without Basic → 401** test shown above.

## 10. What If One URL Must Truly Accept Both Bearer and Session?

For instance, a `/profile` endpoint is called by a browser app with a session, and by a mobile app with a Bearer token. Sometimes the browser holds a session while JavaScript also sends `Authorization: Bearer …`. This scenario needs an explicit **precedence contract**:

~~~text
Proposed Contract A: Header takes precedence if present
------------------------------------------------
Is Authorization header present?
  YES → accept only the declared scheme
         valid token → authenticate via token
         invalid/malformed/expired token → 401, DO NOT fall back to cookie
  NO  → check session
         valid session → authenticate via session
         invalid session → 401 or redirect per client
~~~

Or:

~~~text
Proposed Contract B: Reject ambiguous requests
---------------------------------------------
Are both Bearer and an authenticated cookie present?
  YES → 400/401 per API contract, no implicit choice
  NO  → process only the single mechanism provided
~~~

Option A fits when maintaining client compatibility; option B is stricter when there is no reason to support multiple sources on one request. In all cases, status codes, challenges, and the CSRF/cookie model must be defined.

### 10.1. Why Simply Enabling Both oauth2ResourceServer and formLogin Is Not Enough

A configuration like this **does not automatically express** “Bearer always beats session”:

~~~java
// Illustrates configuring multiple mechanisms only; not a complete policy.
http
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
        org.springframework.security.config.Customizer.withDefaults()))
    .formLogin(org.springframework.security.config.Customizer.withDefaults());
~~~

The filters will have a specific execution order, yet **you cannot deduce the full semantics solely from the DSL call order**. Check:

- Does `BearerTokenAuthenticationFilter` recognize the header? Which schemes does the resolver accept?
- Is `SecurityContext` being restored from a session?
- When the Bearer token is invalid, does the filter end the request via `AuthenticationEntryPoint`?
- When the token is valid, does the filter overwrite the existing authentication?
- Does the request have compatible CSRF tokens, cookies, roles/authorities, and request cache behavior?
- Do HTTP response rules distinguish browser redirects from API 401s as intended?

A working Bearer setup also needs the resource-server dependency and a matching `JwtDecoder`/issuer/JWK; the snippet above **cannot run standalone**. The runnable example in section 8 deliberately uses Basic to stay focused on determining precedence.

### 10.2. Selecting a Chain by Credential Is Also an Option, With Caution

`SecurityFilterChain` can use a custom `RequestMatcher`, including conditions on headers. For example, a higher-priority chain for a mixed endpoint when `Authorization` is present, and a session chain when no header is present. When building such a policy:

1. Clearly define which chain receives requests with a **malformed or unknown-scheme** `Authorization` header; do not treat them as an absent header.
2. Never send a request on to the session chain just because the header chain returned 401. `FilterChainProxy` does **not** fall back to the next chain after the chosen chain rejects.
3. Never feed untrusted header inputs into permission/trust-level selection without validation.
4. Test requests with repeated headers, proxy-introduced conflicts, and all case variants of the scheme name.
5. Ensure a fallback chain protects all remaining URLs; never let requests “fall outside Spring Security”.

If you must adjust filter ordering manually, use `addFilterBefore`, `addFilterAfter`, or `addFilterAt` with knowledge of existing filters. **Placing a custom filter before Basic does not by itself define precedence** if it fails to handle context, errors, request termination, and sessions properly. In many cases, redesigning routing or using a unified authentication filter is better than stacking extra filters.

## 11. Reading Logs to See Who Actually Handled the Request

When multiple mechanisms exist, guessing from a `200` response is insufficient. In development, you can enable logging:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

This configuration reveals which filter chain protects a URL and which filters execute. Exact log messages vary by version and log level; **do not hardcode expectations on a single exact log line**.

Debugging workflow:

1. **Determine the URL after proxy/context-path.** Sometimes a reverse proxy rewrites `/v1/api` to `/api`, causing matchers to behave differently than expected.
2. **Inspect the selected chain.** For `/api/me`, it must be the API chain, not the Web fallback.
3. **Print/inspect the filter list in that chain.** Are `BasicAuthenticationFilter` or `BearerTokenAuthenticationFilter` present? Did the Web chain accidentally enable Basic?
4. **Check credential presence without logging values.** Is `Authorization` present, what is the scheme, is a session cookie present? Never log Basic base64, JWTs, secrets, or session IDs.
5. **Identify the first exception or entry point ending the request.** A bad password may return 401 before authorization runs; a missing role usually returns 403 after authentication.
6. **Inspect the principal in the controller** or via integration tests. Use different usernames to tell them apart in tests. Never log `Authentication.getCredentials()` or raw principals containing secrets.
7. **Verify persistence:** a `STATELESS` API does not restore sessions; does Web's `HttpSessionSecurityContextRepository` hold the context after form login?
8. **Test one credential at a time, then both, then one invalid credential.** The “one invalid + one valid” case usually uncovers unintended fallbacks.

Quick diagnostic table:

| Symptom | Potential cause to check |
| --- | --- |
| API receives a session cookie and still returns 200 without a header | API is using a session repository or accidentally entered the Web chain. |
| API receives an invalid token yet returns 200 via cookie | Unintended fallback exists, filter swallows errors, or chain selection condition is wrong. |
| Web receives a Basic header and shows an HTTP Basic browser prompt | Web chain has a Basic entry point/filter or the request hit the API chain by mistake. |
| Valid Basic request receives 403 | Authentication succeeded but lacks role/scope; check `AccessDeniedHandler`. |
| Valid session + invalid Bearer returns only 401 | A Bearer filter terminated the request before the session could be used; review policy. |
| New endpoint is not controlled by Spring Security | No chain matches, or `securityMatcher` is too narrow. |
| Cannot tell which user won because both share the same name | Retest with **two different principals** and assert the identity in the controller. |

## 12. Security When Multiple Identity Sources Coexist

### 12.1. Avoid Credential Downgrade

An expired access token does not mean the client should be allowed to drop down to an old session cookie and still reach the API. If policy designates the token as the prioritized source when present, **an invalid token must be rejected**. Fallback is allowed only when explicitly designed and when it does not weaken the resource's security requirements.

### 12.2. Never Mix Authorities from Two Different Principals

Never combine `ROLE_ADMIN` from session A with `scope=write` from bearer token B to form a “super principal” C. Those authorities may belong to two completely separate accounts. If a request requires two authentication factors, verify they belong to the **same principal** and enforce a stateful MFA workflow with proper proof—never blindly merge `Authentication` objects.

### 12.3. Session Cookies and CSRF Remain Separate Concerns

A session-based Web chain needs CSRF protection on state-changing actions per policy. HTTP Basic can also carry CSRF risk when a browser sends credentials automatically. CORS controls whether JavaScript from another origin can read responses; it does **not** replace CSRF. Getting precedence right does not automatically secure against CSRF, session fixation, credential stuffing, or XSS.

### 12.4. HTTP Challenges Must Match the Client Audience

Basic APIs typically return `401` with `WWW-Authenticate: Basic …`, whereas browser form logins typically redirect to `/login`. Mixing entry points can leave an HTTP client receiving HTML instead of JSON, or trigger an unwanted Basic popup in browsers. Separating chains by URL helps select the right response and allows independent testing.

### 12.5. Accounts and Secrets Must Be Managed Independently of Routing

`@Order` and `securityMatcher` do not hash passwords, revoke tokens, or isolate user stores. Across channels with different trust levels, consider separate `AuthenticationManager`/providers, authorities, token audiences, MFA, or session policies. Never treat a URL path alone as sufficient proof for elevated privileges; endpoints must still verify the authenticated principal and authorities.

### 12.6. Never Log Credentials to Observe Precedence

For Basic auth, Base64 easily decodes back to username/password; JWTs, API keys, and session IDs are likewise secrets. Logging/tracing must redact data, use correlation IDs, and record only the credential category (Basic/Bearer/session) **without logging raw values**. Avoid leaving verbose DEBUG/TRACE logging on in production for extended periods without assessing sensitive data exposure.

## 13. Pre-Deployment Testing Checklist

For every URL group, you must be able to answer:

| Question | Evidence |
| --- | --- |
| Which chain is selected when a URL matches multiple matchers? | `FilterChainProxy` logs and `@Order` tests. |
| If a URL does not match a priority matcher, which fallback chain handles it? | Tests for paths outside the prefix. |
| Which authentication filters actually exist in the chain? | Filter list at DEBUG/startup or configuration review. |
| What happens when a request carries only a session cookie? | Clear expectation of 200 or 401/302 depending on endpoint. |
| What happens when a request carries only Basic/Bearer? | Expected 200/401 per configured scheme. |
| What happens when a request carries both a cookie and a header from **two different users**? | Assert the exact principal in the controller. |
| What if the header is present with invalid credentials while the cookie is valid? | Verify no unintended fallback/downgrade occurs. |
| Valid credentials but missing role/scope? | 403, distinguished from 401. |
| Header carrying an unsupported scheme or duplicate headers? | Reject/ignore per published contract; do not pick implicitly from a proxy. |
| After logout or session expiration, does the API still depend on cookies? | Test session and header independently. |
| Are CSRF/CORS/session fixation handled properly? | Test POST/login/logout/cross-origin, not only GET. |
| Do logs leak Authorization, Cookie, passwords, or JWTs? | Verify redaction and operational policies. |

Every test should use **distinct identities** so it is unmistakable which source was actually used. Test happy paths, invalid credentials, missing credentials, insufficient authorities, and requests carrying multiple credentials simultaneously.

## 14. Summary

When a request carries multiple credentials, determine in sequence:

1. **Which chain is selected?** `@Order` + `securityMatcher`; **only the first matching chain** runs.
2. **Which filters run and which credentials may they process?** Filter ordering affects context and request termination; there is no built-in “cookie always wins” or “header always wins” rule.
3. **Which AuthenticationManager/Provider inspects the token?** Provider order is separate from filter/chain order; `supports`, `null`, and exceptions each have their own semantics.
4. **What is the intended architectural policy?** Prioritize credentials by endpoint/protocol or reject ambiguous signals; invalid credentials must never silently downgrade.
5. **Is the outcome proven by tests?** Test requests carrying both a Web cookie and another user's Basic/Bearer credentials, add invalid-credential tests, and assert the actual principal and status code.

For applications serving both browsers and APIs, **a stateless header-based API in a dedicated chain + a form-session Web fallback chain** is a transparent, observable, and easily testable design. When forced to support multiple methods on the same URL, establish a clear policy and test thoroughly rather than relying on DSL declaration order.

### References

- Spring Security 6.5 — Java Configuration, Multiple HttpSecurity Instances: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — Servlet Architecture and Filter Ordering: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Basic Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — Session Management / Stateless Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — OAuth2 Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/index.html
- Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — MockMvc Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
