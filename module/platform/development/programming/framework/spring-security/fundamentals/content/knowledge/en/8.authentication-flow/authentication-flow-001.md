# Stages of Credential Reception, Verification, and Identity Establishment in Spring Security

## 1. The Big Picture

A Spring Boot application with an endpoint requiring login does more than simply "compare username with password". Spring Security divides the authentication process into stages with distinct responsibilities and lifecycles:

1. **Receiving the HTTP request:** the servlet container and the security filter chain select the handling mechanism.
2. **Extracting authentication credentials:** an HTTP Basic header, form login, Bearer token, or another type of credential.
3. **Creating an untrusted Authentication request:** containing the information claimed by the client and the evidence to be verified.
4. **Verifying identity:** AuthenticationManager coordinates AuthenticationProvider, user source, password encoder, or token verifier.
5. **Creating a trusted Authentication result:** principal, authorities, authenticated status, and credential handling.
6. **Establishing the SecurityContext for the request:** the filter or authentication mechanism uses the authenticated result.
7. **Applying authorization:** whether the endpoint/method/resource is permitted or denied.
8. **Persisting or ending the context:** SecurityContextRepository/session or a stateless mechanism decides whether subsequent requests need to re-authenticate.

This lesson dives deep into **each stage of the authentication flow**, the collaboration among classes, and where 401/403 responses originate. Practical examples use **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet**, HTTP Basic, and an in-memory UserDetailsService so they can be observed with curl.

**Key takeaway:** Authentication answers "do the credentials prove the identity?", whereas Authorization answers "does the authenticated identity have permission to perform this action?". Successful login does not guarantee access to every URL or record.

### Learning Objectives

Learners will be able to:

- Clearly explain how filters receive credentials, untrusted Authentication, and the authenticated result.
- Trace the request path through FilterChainProxy, BasicAuthenticationFilter, ProviderManager, and DaoAuthenticationProvider.
- Understand how UserDetailsService, PasswordEncoder, and account status checks work together.
- State accurately who puts Authentication into SecurityContext and when the context is saved.
- Distinguish between success, missing credentials, wrong credentials, insufficient permissions, and non-existent URL branches.
- Describe the differences between HTTP Basic, form login, session, and Bearer token.
- Run a Spring Boot example testing HTTP 200, 401, 403 and reading identity in a Controller.
- Identify mistakes when writing a custom login endpoint or custom authentication filter.

## 2. Component Responsibility Map

| Component | Role in the flow | Not its responsibility |
| --- | --- | --- |
| Servlet container | Receives HTTP request, invokes filter chain | Does not verify passwords for the application |
| DelegatingFilterProxy | Bridge from Servlet Filter to a Spring bean | Does not decide whether a user is valid/invalid |
| FilterChainProxy | Selects the matching SecurityFilterChain, manages security filters | Does not load users or compare passwords |
| SecurityFilterChain | Set of filters/policies applied to the request | Not implicitly the combination of all chains |
| BasicAuthenticationFilter | Reads HTTP Basic header, creates untrusted Authentication, calls manager | Does not store the account repository |
| UsernamePasswordAuthenticationFilter | Reads form login and calls manager, handles login success/failure | Does not replace PasswordEncoder |
| Authentication | Carries principal, credentials, authorities, details, authenticated | Does not verify client information itself |
| AuthenticationManager | Interface authenticate(Authentication) | Does not send HTTP responses/cookies |
| ProviderManager | AuthenticationManager using a list of AuthenticationProvider | Does not know how to verify every credential type |
| AuthenticationProvider | Verifies one type of Authentication | Does not put context into the HTTP request |
| DaoAuthenticationProvider | Verifies username/password via UserDetailsService and PasswordEncoder | Does not decide URL permissions |
| UserDetailsService | Looks up UserDetails by username | Does not compare raw password against hash |
| PasswordEncoder | Hashes and matches passwords | Does not grant roles or authorization |
| SecurityContextHolder | Provides the currently active SecurityContext | Does not persist context to the next request |
| SecurityContextRepository | Loads/saves SecurityContext according to policy | Does not perform password authentication |
| AuthorizationFilter/AuthorizationManager | Checks HTTP policy using Authentication and rules | Does not verify passwords |
| AuthenticationEntryPoint/handlers | Converts security errors into HTTP responses/redirects | Does not replace AuthenticationProvider |

Think of it as: **filters receive and convert**, **managers coordinate**, **providers verify**, **context holds the result**, **authorization makes the decision**.

A public request may not need authentication. A request that already has a valid session can restore its SecurityContext without reloading UserDetails every time. Therefore, the following diagram depicts the common path of a request **that actually carries credentials**, without claiming every HTTP request calls DaoAuthenticationProvider.

## 3. Diagram of the Full HTTP Basic Flow

Suppose the client sends username alice and password learn123 to GET /private. Illustrative HTTP syntax:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic YWxpY2U6bGVhcm4xMjM=
~~~

The Base64 string represents alice:learn123. **Base64 is not security encryption**; use it only for localhost examples. When sending credentials over a real network, HTTPS and proper secret management are required.

~~~text
[1] HTTP request: GET /private + Authorization: Basic
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    v
SecurityFilterChain matching the URL
    |
    v
[2] BasicAuthenticationFilter
    |-- Parse Basic header -> username, raw password
    |-- Create unauthenticated UsernamePasswordAuthenticationToken
    v
[3] AuthenticationManager.authenticate(attempt)
    |
    v
ProviderManager
    |-- Find AuthenticationProvider supporting token type
    v
[4] DaoAuthenticationProvider
    |-- UserDetailsService.loadUserByUsername("alice")
    |-- PasswordEncoder.matches(rawPassword, storedHash)
    |-- Check relevant account status flags
    |
    +-- FAIL -> AuthenticationException
    |            |
    |            +-> filter/handler processes, may return HTTP 401
    |
    +-- SUCCESS -> Trusted Authentication
                  (principal, authorities, authenticated=true)
                         |
                         v
[5] ProviderManager -> BasicAuthenticationFilter
    |
    v
[6] Filter sets Authentication into SecurityContext
    |
    v
[7] AuthorizationFilter checks authenticated()/role
    |
    +-- Sufficient permissions -> DispatcherServlet -> Controller -> HTTP 200
    |
    +-- Insufficient permissions -> exception handling -> HTTP 403
    |
    v
[8] End of request: context is handled/cleared per lifecycle;
    next request restores or re-authenticates per repository/session/token
~~~

**Responsibility-focused diagram**, omitting several filters (SecurityContextHolderFilter, AnonymousAuthenticationFilter, ExceptionTranslationFilter, CsrfFilter...) and exact runtime ordering details. The exact order depends on the Spring Security version and configured SecurityFilterChain; do not use the diagram as an absolute filter list.

## 4. Stage 1 — HTTP Request Enters SecurityFilterChain

A Servlet container like Tomcat receives the request and passes it through Servlet filters. In a Spring Security application, **DelegatingFilterProxy** forwards the request to **FilterChainProxy**. FilterChainProxy selects the first security chain that matches the request, then runs the filters in that chain.

This determines:

- Whether Spring Security applies to the request.
- Which authentication filters are present: Basic, form login, Bearer token...
- Which CSRF, session, exception handling, and authorization rules take effect.
- Which URLs require authenticated, specific roles, or permitAll.

**Distinguish securityMatcher from requestMatchers:**

- **securityMatcher** on HttpSecurity restricts the scope of **the entire SecurityFilterChain**.
- **requestMatchers** inside authorizeHttpRequests applies an authorization rule **after the chain has been selected**.

If an application has multiple chains and no chain matches the URL, the request **is not protected by Spring Security**. Therefore, a multi-chain architecture needs a fallback with an appropriate policy.

In this lesson's sample application, there is only one SecurityFilterChain with no specialized securityMatcher; it receives normal Servlet requests and applies URL rules.

### 4.1. Do public endpoints bypass all filters?

Not by default. **permitAll** states that the request does not require Authentication to be permitted by authorization. It does not remove every filter from the chain. If a client actively sends an HTTP Basic header with wrong credentials to a permitAll endpoint, BasicAuthenticationFilter may still attempt authentication and return 401.

This is why you must distinguish between **having an authentication filter in the chain** and **an endpoint requiring authentication**.

## 5. Stage 2 — Filter Extracts Credentials

The authentication filter reads data from the request according to the configured protocol:

| Mechanism | Where credentials are carried | Common filter/mechanism |
| --- | --- | --- |
| HTTP Basic | Authorization: Basic Base64(username:password) | BasicAuthenticationFilter |
| Form login | Username/password in form POST login | UsernamePasswordAuthenticationFilter |
| HTTP Bearer | Authorization: Bearer access_token | BearerTokenAuthenticationFilter |
| OAuth2/OIDC login | Authorization code/callback via protocol | OAuth2LoginAuthenticationFilter and related components |
| Existing session login | Session cookie pointing to stored context | SecurityContextRepository and context filters |

Not every mechanism creates a UsernamePasswordAuthenticationToken. HTTP Basic and form login commonly use this type; Bearer tokens and OIDC have their own Authentication implementations.

### 5.1. The input token must be in an unauthenticated state

For example, when receiving username/password, the filter may create:

~~~java
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "learn123"
    );
~~~

This snippet is **code inside a Java method with imports already present**, not a standalone application.

At that moment:

- the input principal is typically the username claimed by the client.
- credentials is the unverified password.
- authenticated=false.
- trusted authorities have not been granted yet.
- details may contain auxiliary metadata, but must not be treated as proof of identity.

A client can claim the name "admin" without having proved it is admin. **Never create an Authentication with authenticated=true based solely on a username, ID, or role passed by the client.**

### 5.2. Handling credentials upon receipt

- HTTP Basic sends the password as Base64, which is trivially decoded; HTTPS must be used over the network.
- Do not log the Authorization header, raw password, OTP, token, or cookie.
- Limit request/header sizes, normalize input per protocol, and avoid error messages that reveal whether a user exists.
- Do not handle it manually by comparing plaintext passwords in a Controller.
- Do not use URL query parameters to transmit passwords.
- With browser form login, CSRF and session lifecycle must be thoroughly evaluated.

The authentication filter does not need to know how the database stores users. This is the benefit of separating **credential collection** from **credential verification**.

## 6. Stage 3 — AuthenticationManager Receives the Request

AuthenticationManager defines the contract:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

The call takes an untrusted Authentication and returns an authenticated Authentication, or throws AuthenticationException. It **does not** return HTTP 200/401/403, does not directly redirect, does not create cookies itself, and does not place the context into the request itself.

The common implementation is **ProviderManager**, configured with a list of AuthenticationProvider instances.

### 6.1. ProviderManager selects a provider

General flow:

1. Check provider.supports(authentication.getClass()).
2. Providers that do not support the token type are skipped.
3. A matching provider has authenticate(authentication) called.
4. Returning a valid non-null Authentication means authentication succeeded according to that provider.
5. A provider may return null if it cannot decide and let another provider try.
6. When an AuthenticationException is thrown, ProviderManager handles it by exception type; certain exceptions can stop processing immediately, such as AccountStatusException.
7. If a parent AuthenticationManager is configured, it may be consulted when appropriate.
8. If no provider supports the token, ProviderNotFoundException may be thrown.

**supports=true does not mean the password is correct.** It only indicates the provider can attempt to process that token type.

Do not build a fallback chain where a second provider accepts credentials that a first provider rejected for security reasons. Retry behavior between providers must be explicitly designed and tested for exceptions.

### 6.2. AuthenticationManager has no HTTP response

Example:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

This call only provides the result to the **caller**. If a custom Controller calls this line itself and returns JSON "login OK", the next request is not guaranteed to be logged in. You still need to handle **SecurityContext**, context/session persistence, or appropriate token issuance.

## 7. Stage 4 — Provider Verifies Identity

For username/password, Spring Security typically uses **DaoAuthenticationProvider**, combining:

- **UserDetailsService** to look up UserDetails by username.
- **PasswordEncoder** to execute matches(raw, encoded).
- **UserDetails** carrying username, encoded password, authorities, and account status flags.
- Checks for enabled, accountNonLocked, accountNonExpired, credentialsNonExpired as configured.

~~~text
UsernamePasswordAuthenticationToken("alice", rawPassword)
                     |
                     v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername("alice")
    |           |
    |           +--> username=alice
    |           +--> password=<BCrypt hash>
    |           +--> authorities=[ROLE_USER]
    |           +--> flags enabled/nonLocked/...
    |
    +--> PasswordEncoder.matches(rawPassword, hash)
    |
    +--> account status checks
    |
    +--> SUCCESS: Authenticated Authentication
    |
    +--> FAIL: AuthenticationException
~~~

### 7.1. Why finding the user is still not enough?

UserDetailsService only retrieves the account record; finding a username **does not prove the request was sent by the account owner**. DaoAuthenticationProvider must verify the password and relevant status conditions.

With BCrypt, each hash typically includes a salt, so you must not compare the raw password directly against the hash using String.equals. Use PasswordEncoder.matches to verify according to the configured algorithm.

### 7.2. Common errors

- **BadCredentialsException:** wrong credentials or the system chooses not to reveal whether the username exists.
- **UsernameNotFoundException:** user source did not find the name; the provider may mask this as a bad credentials error to reduce user enumeration.
- **LockedException / DisabledException:** account status prevents login.
- **ProviderNotFoundException:** no provider matches the Authentication.
- **User/credential source failures:** may be configuration or system errors; do not treat every HTTP 401 solely as a wrong password.

When debugging, check the login mechanism, Authentication type, the actual manager/provider used, how users are loaded, and the password encoder before modifying authorization.

### 7.3. Non-password mechanisms

With Bearer JWT, the provider/decoder typically checks signature, issuer, audience, expiry, and configured claims/validators. With OIDC login, the app also verifies the protocol callback and identity provider. Do not try to use DaoAuthenticationProvider to compare passwords for every token type.

By the same principle, the final result must be **an identity proved by a trusted source**, with authorities mapped and scoped appropriately.

## 8. Stage 5 — Authentication Result After Success

After valid verification, Authentication may contain:

| Field | Typical form |
| --- | --- |
| principal | Verified UserDetails, custom principal, or mechanism-specific object |
| credentials | Usually erased/nulled when no longer needed |
| authorities | ROLE_USER, ROLE_ADMIN, or permissions from a trusted source |
| authenticated | true |
| details | Minimal metadata per filter/mechanism |

Example in a DaoAuthenticationProvider flow:

~~~text
Authentication result
  principal = UserDetails(username=alice, ...)
  authorities = [ROLE_USER]
  authenticated = true
  credentials = may be erased
~~~

**Authorities are not information the client gets to choose.** If the frontend sends role=ADMIN, the backend must not use that role to create a successful Authentication. Roles must come from UserDetails, an identity provider, a verified JWT, or a trusted permission source.

### 8.1. Credential erasure after authentication

ProviderManager by default attempts to erase credentials data from the returned Authentication if the object implements **CredentialsContainer**. This reduces how long the password lives inside the Authentication result, though it does not automatically erase all copies in Java Strings, request buffers, caches, logs, or the heap.

If UserDetails is cached and shares a reference with the principal, credential erasure may affect the cached object. Cache/lifecycle design must be handled properly rather than arbitrarily disabling credential erasure.

**Do not return the raw Authentication/UserDetails from an API** just because Spring Security erased credentials. The principal may contain email, password hash, or internal fields depending on the implementation. Use a response DTO selecting only the needed fields.

## 9. Stage 6 — Establishing the SecurityContext

This is the step most often confused with AuthenticationManager.

**AuthenticationManager.authenticate() returns the result**; whereas the **filter/authentication mechanism** typically creates or updates the SecurityContext and puts the Authentication into the request's SecurityContextHolder.

With HTTP Basic, **BasicAuthenticationFilter** inspects the Authorization header, calls AuthenticationManager, receives the result, and places the authenticated Authentication into SecurityContext. With form login, **UsernamePasswordAuthenticationFilter/AbstractAuthenticationProcessingFilter** handles success and failure along its own pipeline.

Diagram:

~~~text
AuthenticationManager.authenticate(attempt)
            |
            v
Authentication verified
            |
            v
Authentication filter handles success
            |
            v
SecurityContext.setAuthentication(verified)
            |
            v
SecurityContextHolder.setContext(context)
            |
            v
Controller and AuthorizationFilter read current Authentication
~~~

### 9.1. What is SecurityContextHolder?

SecurityContextHolder typically uses a ThreadLocal in Servlet applications to provide the SecurityContext of the current execution. Code can access:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

This is an illustrative snippet placed inside a class with necessary imports; in a Controller, injecting Principal or Authentication is often more convenient and reduces direct coupling to the holder.

**Do not assume the context automatically crosses threads.** For asynchronous work, executors, or reactive stacks, appropriate context propagation mechanisms must be used. Do not store SecurityContextHolder in an application static variable to "share a user".

### 9.2. Per-request context vs. saving for subsequent requests

Calling:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
~~~

only puts Authentication into the context **currently being processed**. In Spring Security 6, custom code that wants the context to persist across requests may need **SecurityContextRepository.saveContext(context, request, response)** along with the appropriate repository and filter/session policy.

This snippet is **placed after the verified variable has already been authenticated**. It is not a complete custom login implementation. Building a custom login endpoint also requires handling CSRF, session fixation, session lifecycle, failure/success handlers, persistence, and cookie policy. For most applications, prefer the built-in authentication filters.

### 9.3. Who clears the context at the end of the request?

Security filters manage the context lifecycle, including preventing a previous request's Authentication from leaking into another request on a reused thread. In the Servlet stack, the system must have the proper context holder/filter/repository mechanism; do not arbitrarily hold context in a ThreadLocal and forget to clear it.

If implementing asynchronous execution or custom filters, pay attention to lifecycle and how context is restored/cleared for the exact framework version.

## 10. Stage 7 — Authorization Is Evaluated After Identity Exists

**Authorization** is distinct from authentication. A request may:

- Have no trusted Authentication and be prompted to log in.
- Have a valid Authentication but lack ROLE_ADMIN.
- Have the right role but lack resource ownership permission.
- Have Authentication and sufficient permissions, and be processed by the Controller.

A SecurityFilterChain can declare:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/private").authenticated()
    .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

This is DSL inside a configuration method, not a standalone Java file.

**authenticated()** uses Spring Security's trust resolver mechanism. Do not manually check only isAuthenticated() and treat every Authentication as logged in: **AnonymousAuthenticationToken** may carry authenticated=true as a property while still being recognized by the framework as anonymous for rules requiring a real user.

**hasRole("ADMIN")** typically checks for the **ROLE_ADMIN** authority. A user with ROLE_USER but without ROLE_ADMIN who has authenticated successfully will still receive HTTP 403 at /admin.

If an API reads /orders/42, checking ROLE_USER alone is usually insufficient: you must check **ownerId, tenantId, permission, and business state**. Spring Security does not automatically know which record belongs to which user.

## 11. Stage 8 — Request Completion and Identity Persistence

### 11.1. HTTP Basic

The client typically sends Authorization: Basic on subsequent requests. When the header is present, the filter can authenticate from the credentials; do not assume a single successful Basic request automatically creates a long-lived login session.

HTTP Basic can be configured with different SecurityContextRepository or remember-me settings. If you want stateless behavior, configure SessionCreationPolicy, repository, request cache, and cookie/session behavior explicitly.

### 11.2. Form login with HTTP session

The browser sends a login POST, the filter authenticates username/password, runs the session authentication strategy, and can save SecurityContext for subsequent requests. The session cookie helps the server retrieve the established context/session.

Spring Security 6 uses the **SecurityContextHolderFilter**/SecurityContextRepository mechanism by default and emphasizes **explicit save** for custom code. Built-in authentication mechanisms already perform the necessary lifecycle steps according to their configuration; do not write a custom login controller just to mimic part of the flow.

You must manage session fixation, timeout, logout, CSRF tokens, cookie flags, and invalidation when permissions change. Do not assume an AuthenticationManager result automatically issues cookies or saves users to a database.

### 11.3. Bearer token/stateless API

The client sends a Bearer token on every request. The system verifies the token, creates an Authentication, and puts it into the current request's SecurityContext, then evaluates authorization. When the request ends, the thread-local context is cleared; the next request relies on the token again if there is no other persistence.

Standard JWTs have a readable payload; signatures verify integrity, **not encrypt secrets inside claims**. Do not put passwords, password hashes, refresh tokens, or unnecessary personal data into a JWT.

### 11.4. Anonymous request

When no authenticated user exists, **AnonymousAuthenticationFilter** can set an AnonymousAuthenticationToken so downstream components have a guest identity per policy. This does not prove a successful login.

As a result, permitAll endpoints can proceed, while authenticated endpoints are handled by the authentication-required flow.

## 12. Comparing HTTP Basic and Form Login Flows

| Aspect | HTTP Basic | Form login |
| --- | --- | --- |
| Where do credentials come from? | Authorization: Basic header | Form POST login |
| Main filter | BasicAuthenticationFilter | UsernamePasswordAuthenticationFilter |
| Common input token | UsernamePasswordAuthenticationToken | UsernamePasswordAuthenticationToken |
| Manager/provider | Typically ProviderManager + DaoAuthenticationProvider | Can share that same manager/provider |
| Missing Authentication on private URL | Usually 401 + challenge | Usually 302 redirect to login page |
| Wrong password | Filter/entry point may return 401 | Failure handler processes, may redirect to error page |
| Success | Continues filter chain/request | Success handler/redirect, session strategy |
| Subsequent request persistence | Client usually resends credentials | Usually session and context persistence |
| CSRF | Must be evaluated when browsers auto-send Basic | Usually requires CSRF token with form/session |

Both can use the same DaoAuthenticationProvider because they differ only in how they **receive credentials** and handle HTTP. The provider does not need to know whether the password came from an HTML form or an Authorization header.

If an application configures its own SecurityFilterChain, enable the desired mechanism with httpBasic(...) or formLogin(...), rather than assuming starter-security automatically provides every protocol after defining a custom chain.

## 13. Runnable Spring Boot 3.3.x Example

The example uses HTTP Basic to clearly show the flow of receiving credentials, authenticating, placing identity into SecurityContext, and enforcing authorization. Avoid writing custom filters or providers so a foundational lesson does not turn into a homegrown mechanism demo.

### 13.1. Create project and dependencies

Create a Spring Boot 3.3.x, Java 17+ project with Spring Initializr or an existing Gradle Wrapper. In **build.gradle** (Groovy DSL), you need:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This is the dependencies block of a Boot project with plugins/build tool already set up, not an entire standalone build.gradle file.

### 13.2. Complete single Java file

Create **src/main/java/com/example/authstages/AuthStagesApplication.java**:

~~~java
package com.example.authstages;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthStagesApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthStagesApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    Map<String, Object> privateEndpoint(Authentication authentication) {
        var authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "user", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "authorities", authorities
        );
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

This is a **complete Java file inside a Boot project**. The public class AuthStagesApplication matches the filename, and the Controller is a package-private class in the same package so component scan discovers it. Java 17 supports var and Stream.toList. Spring Security is configured via the SecurityFilterChain bean.

**How do the beans work?**

1. **PasswordEncoder** creates a BCryptPasswordEncoder.
2. **UserDetailsService** creates two in-memory accounts: alice with ROLE_USER, admin with ROLE_ADMIN. Passwords are hashed before storage; hard-coded data is for learning only.
3. Spring Security can use UserDetailsService and PasswordEncoder to build the standard username/password authentication mechanism, with an appropriate DaoAuthenticationProvider/AuthenticationManager per configuration.
4. **SecurityFilterChain** requires GET /private authenticated, GET /admin ROLE_ADMIN, and allows GET /public publicly; other URLs denyAll.
5. **httpBasic** enables the HTTP Basic filter, and **formLogin.disable** avoids form redirects during testing.
6. The Controller **does not return the raw Authentication**; it returns only selected fields to illustrate principal and authorities.

**Do not blindly disable CSRF.** This example only has GET endpoints. If adding POST/PUT/DELETE, design CSRF based on the browser model and how credentials are transmitted; HTTP Basic cached by browsers can still be exposed to CSRF risks.

### 13.3. Running the application

In a project directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

In PowerShell, use **.\gradlew.bat bootRun**. Once the server is running on localhost:8080, try:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

In PowerShell you may need **curl.exe** if curl is an alias. Use HTTP Basic on localhost for demos only; sending credentials over a network requires HTTPS. To avoid putting passwords in shell history, run **curl -i -u alice URL** and enter the password at the prompt.

### 13.4. Expected status table

| Request | HTTP status | Deciding stage |
| --- | --- | --- |
| GET /public without credentials | **200**, body public OK | Authorization permitAll; Controller executes |
| GET /private without credentials | **401** | No valid Authentication; HTTP Basic entry point |
| GET /private with alice:wrong | **401** | DaoAuthenticationProvider cannot verify password |
| GET /private with alice:learn123 | **200** | Authentication succeeds; Authorization authenticated() |
| GET /admin with alice:learn123 | **403** | Authentication succeeds, Authorization lacks ROLE_ADMIN |
| GET /admin with admin:admin123 | **200**, body admin OK | Has ROLE_ADMIN, Controller executes |

With alice logged in properly, GET /private is expected to return JSON:

~~~json
{
  "user": "alice",
  "authenticated": true,
  "authorities": ["ROLE_USER"]
}
~~~

JSON key order is not guaranteed. The table and JSON are **expected results predicted from the configuration**, not measured execution logs captured in this document. If you add filters, handlers, or proxies, verify the actual response.

### 13.5. Step-by-step walkthrough of the same request

For GET /private with alice:learn123:

1. Tomcat receives the request.
2. FilterChainProxy selects the SecurityFilterChain.
3. BasicAuthenticationFilter reads the Authorization header.
4. Creates an unauthenticated UsernamePasswordAuthenticationToken.
5. Calls AuthenticationManager; ProviderManager delegates to the username/password provider.
6. DaoAuthenticationProvider loads alice, checks BCrypt matches, and checks account flags.
7. Returns an Authentication with principal alice, ROLE_USER, authenticated=true.
8. BasicAuthenticationFilter sets the Authentication into SecurityContext.
9. AuthorizationFilter checks authenticated() and lets the request proceed.
10. Controller reads the current Authentication and builds a response DTO/Map containing only user, authenticated, and authorities.

No step requires the Controller to read raw passwords itself or call UserDetailsService to re-authenticate the user.

## 14. Three Failure Flows to Distinguish

### 14.1. Request without credentials

~~~text
GET /private, no Authorization
      |
      v
Authentication filter does not establish a successful login
      |
      v
AuthorizationFilter requires authenticated()
      |
      v
ExceptionTranslationFilter/AuthenticationEntryPoint
      |
      v
HTTP 401, usually with WWW-Authenticate when using Basic
~~~

UserDetailsService is not necessarily called in this branch. The error is the lack of an authenticated identity to access a private resource, not necessarily a wrong password.

### 14.2. Credentials provided, but verification fails

~~~text
GET /private, Authorization: Basic alice:wrong
      |
      v
BasicAuthenticationFilter -> AuthenticationManager
      |
      v
DaoAuthenticationProvider -> PasswordEncoder.matches = false
      |
      v
AuthenticationException
      |
      v
Filter/AuthenticationEntryPoint handles error
      |
      v
HTTP 401 (in the demo configuration)
~~~

The Controller does not run. On the standard Basic flow, the filter clears the failed context and issues a challenge; exact behavior depends on handlers, ignoreFailure, and other configuration.

### 14.3. Correct password, missing authority

~~~text
GET /admin, Authorization: Basic alice:learn123
      |
      v
AuthenticationManager authenticates successfully
      |
      v
SecurityContext contains ROLE_USER
      |
      v
AuthorizationFilter requires ROLE_ADMIN
      |
      v
AccessDenied -> HTTP 403
~~~

The authentication layer did its job properly. Do not fix this error by disabling security, skipping password checks, or giving ROLE_ADMIN to every user. Review the account's permissions and business policy.

### 14.4. Unmapped URL and HTTP 404

If SecurityFilterChain lets the request through but MVC has no mapping, it may return 404. With anyRequest().denyAll, an unpermitted URL may be rejected before MVC runs, resulting in 401/403 instead of 404. Do not use the status of a non-existent URL as proof that the security policy is complete.

## 15. Custom Login Endpoint: The Hard Part Is Setting and Saving Context

A custom Controller can call AuthenticationManager directly:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

But that alone **does not establish login for the current request or the next request**.

If designing session login, after valid authentication, custom code needs to create a SecurityContext, attach the Authentication, and **save it to SecurityContextRepository** with request/response per Security 6:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

This is a **snippet belonging to a login mechanism where variables/beans verified, securityContextRepository, request, and response already exist**, not a standalone program. Do not paste these four lines into an arbitrary Controller and consider it a complete login solution.

Custom login also requires handling session fixation strategy, CSRF, cookie/session settings, success/failure handlers, logout, rate limiting, MFA, secret storage, and post-login permissions. Therefore, unless there is a special requirement, prefer **formLogin/httpBasic/oauth2Login/Resource Server** supported by the framework.

### 15.1. Why does Spring Security 6 emphasize explicit save?

SecurityContextHolderFilter loads context from the repository but is not responsible for automatically saving every modification made by custom code after the request ends. If you attach an Authentication to the holder yourself and want to keep it for subsequent requests, you must call saveContext at the right time with the right repository.

With built-in login filters, Spring Security already manages that mechanism's lifecycle. Do not create arbitrary extra filters and rely on implicit auto-save behavior from older versions.

### 15.2. Authentication succeeds, yet the next request is anonymous

Check:

- Did you only call manager.authenticate() and forget to put the result into SecurityContext?
- Did you set the context but fail to call saveContext even though you wanted session persistence?
- Is SessionCreationPolicy set to STATELESS?
- Is the client sending the cookie/session ID back?
- Did the session expire or get rotated/logged out?
- Is the next request entering a different SecurityFilterChain?
- Are you trying to access the context from another thread without context propagation?

Each cause resides at a different stage; you cannot fix all of them by changing PasswordEncoder.

## 16. Common Misconceptions and How to Debug

| Symptom | Suspected stage | How to check |
| --- | --- | --- |
| Authorization header present, but filter ignores it | Reception/extraction | Correct SecurityFilterChain and Basic/Bearer mechanism? |
| supports() returns false | Provider selection | Does the Authentication type created by the filter match the provider? |
| UserDetailsService finds user, yet still 401 | Verification | PasswordEncoder, account status, provider |
| Auth succeeds, yet Controller sees no user | SecurityContext | Did the filter set Authentication, did the request enter the right chain? |
| Next request loses login | Persistence | Repository, explicit save, session/cookie, policy |
| Correct password, yet /admin returns 403 | Authorization | ROLE_ADMIN, policy, owner/tenant |
| POST returns 403 despite being logged in | CSRF/Authorization | Check CSRF token and rights; do not disable blindly |
| Public URL with wrong credentials gets 401 | Authentication filter | Did the filter attempt to verify provided credentials before permitAll? |
| User with USER role reads another user's data | Business authorization | Must check ownerId/resource |
| Controller returns raw Authentication as JSON | Output boundary | Return allowlisted DTO only, avoid credentials/details |
| UserDetails loses password after auth, stale cache | Credential erasure/cache | Check shared references and eraseCredentials |
| WebFlux code uses HttpSecurity | Wrong stack | Requires ServerHttpSecurity and reactive context |
| HTTP 401 turns into 302 | Entry point | Is form login/redirect configured instead of Basic? |
| Async task cannot see context | Context propagation | Use appropriate context-propagating wrapper/delegating support |

### 16.1. Reasonable debugging order

1. Record request method, URL, Accept, Authorization scheme (do not log secrets), and whether a cookie/session ID is present.
2. Identify which SecurityFilterChain FilterChainProxy selects.
3. Determine whether the specific authentication filter processes the request.
4. Check which Authentication type is created before verification.
5. Check which AuthenticationManager/AuthenticationProvider is used and which exception is thrown.
6. Check UserDetailsService/PasswordEncoder or token decoder.
7. Upon success, check principal and authorities in SecurityContext (log only safe fields).
8. Distinguish whether AuthorizationFilter rejected it, CSRF rejected it, or the Controller has no mapping.
9. If the issue only appears on the next request, check repository, session policy, and cookies.
10. Write integration tests for the happy path as well as missing credentials, wrong credentials, missing role, and expired session branches.

You can enable Spring Security DEBUG logging in a controlled development environment, but **never log raw passwords, tokens, Authorization headers, cookies, or PII** for debugging.

## 17. Self-Check Questions

**Question 1.** Is the HTTP Basic filter or DaoAuthenticationProvider responsible for reading the Authorization header?  
**Answer:** BasicAuthenticationFilter reads the header; DaoAuthenticationProvider verifies credentials using the user source and password encoder.

**Question 2.** Does UsernamePasswordAuthenticationToken.unauthenticated mean login has succeeded?  
**Answer:** No. It only holds data claimed by the client; the manager/provider must verify it.

**Question 3.** Does UserDetailsService finding the user prove the password is correct?  
**Answer:** No. DaoAuthenticationProvider uses PasswordEncoder.matches and account status checks.

**Question 4.** Does ProviderManager return HTTP 401 directly?  
**Answer:** No. It returns an Authentication or throws an AuthenticationException; the filter/entry point translates that into an HTTP response.

**Question 5.** After manager.authenticate() succeeds, does a controller calling it directly create a login session for the next request?  
**Answer:** No. You need SecurityContext and the corresponding context persistence or token/session mechanism.

**Question 6.** What happens when calling /admin with the correct password but without ROLE_ADMIN?  
**Answer:** Authentication succeeds, Authorization denies access, usually returning HTTP 403 in the HTTP Basic demo.

**Question 7.** Why can a permitAll endpoint still return 401 when the client sends a wrong Basic header?  
**Answer:** The authentication filter may attempt the provided credentials and fail before the permitAll authorization step.

**Question 8.** Does HttpSecurity SessionCreationPolicy.STATELESS mean there is never an Authentication in a request?  
**Answer:** No. A request still has an Authentication after tokens/credentials are verified; only session persistence policy differs.

**Question 9.** Why does AnonymousAuthenticationToken have isAuthenticated=true yet the authenticated() rule still blocks anonymous users?  
**Answer:** Authorization uses a trust resolver mechanism to distinguish anonymous tokens from real authenticated user principals.

**Question 10.** Does SecurityContextHolder in Servlet automatically propagate to all async threads?  
**Answer:** Not by default. Appropriate framework propagation mechanisms must be used.

**Question 11.** What is the difference between HTTP 401 and 403 in the example?  
**Answer:** 401 usually means missing/wrong credentials; 403 means already authenticated but lacking permissions or denied by another policy.

**Question 12.** Why is checking ROLE_USER alone not enough for GET /orders/42?  
**Answer:** You must verify the user has permission for that specific order, ownerId/tenantId, and business state.

## 18. Official Spring Security Documentation

- Servlet Authentication Architecture (ProviderManager, AuthenticationProvider, SecurityContextHolder): https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/architecture.html
- Servlet Basic Authentication: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/basic.html
- Servlet Form Login: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/form.html
- Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/session-management.html
- Servlet Architecture and FilterChainProxy: https://docs.spring.io/spring-security/reference/6.3/servlet/architecture.html
- Authorization HTTP Requests: https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/authorize-http-requests.html
- DaoAuthenticationProvider API Spring Security 6.3.3: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Authentication interface API Spring Security 6.3.4: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/core/Authentication.html
- Spring Boot 3.3 Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
