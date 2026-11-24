# What is Spring Security and What Problems Does It Solve?

## 1. Why Does a Spring Application Need Security?

Imagine a sales system with APIs for viewing products, viewing orders, and administering accounts. A controller can handle the business logic correctly, but without security controls, anyone who knows the URL can try calling the endpoint. The system must answer at least three questions:

1. **Who is sending the request?** How is the user's identity verified?
2. **What is that person allowed to do?** Can a regular user call admin features, or read someone else's orders?
3. **Can the request be abused?** Could a browser unintentionally send a state-changing request triggered by a malicious page?

**Spring Security** is a framework in the Spring ecosystem that provides infrastructure for **authentication**, **authorization**, and **protection against several common web attack patterns**. The framework integrates into the application's request-processing pipeline, supporting a unified security policy for Spring MVC and REST APIs, along with a separate stack for Spring WebFlux.

Spring Security is not a user database, not JWT, not an identity provider, and does not automatically replace HTTPS or business-level checks. It provides the components for an application to **verify identity and enforce access policies**.

## 2. What Problems Does Spring Security Solve?

| Need | How Spring Security Supports It | Scenario |
| --- | --- | --- |
| Verify users | Authentication, AuthenticationManager/AuthenticationProvider, identity source integration | Only accounts with valid logins can access the profile page |
| Access authorization | URL and method rules, roles/authorities, authorization expressions | ADMIN can perform administration; USER cannot |
| Maintain security context | SecurityContext, session mechanism or per-request authentication | Services know the current user |
| Multiple authentication mechanisms | Form login, HTTP Basic, OAuth2/OIDC client and resource server when configured | Websites use sessions; APIs accept Bearer tokens |
| Reduce web attack risks | CSRF protection, session control, appropriate security headers | Block forged cookie-based POST requests |
| Centralize rules | SecurityFilterChain, method security | Multiple endpoints are protected together before reaching the Controller |

Available capabilities **do not mean every feature is automatically enabled properly for every application**. Developers need to determine the authentication mechanism, configure policies, and test them.

### 2.1. Authentication

Authentication answers **"Who are you?"**. A user may provide a username/password, a browser session, or a Bearer token. Spring Security passes those credentials through the configured authentication mechanism; if valid, the resulting **Authentication** represents the principal (identity) and associated authorities.

Example: the account "linh" logs in with the correct password and is recognized as "linh". That only confirms identity; it **does not prove** that linh is allowed to view every order.

For passwords, a real system should store **one-way hashed passwords using a suitable algorithm**, such as BCrypt or Argon2 via PasswordEncoder. Do not store plaintext, do not rely on reversible encryption, and do not treat simply calling SHA-256 as a complete password storage mechanism.

### 2.2. Authorization

Authorization answers **"What is this identity allowed to do on a specific resource?"**. Several levels of checks:

- Require **authenticated**: must be authenticated to view the profile.
- Require **role/authority**: only ADMIN can call administrative functions.
- Require **business permission**: a USER can only view orders whose ownerId matches their own identity.
- Require **state-based rules**: even someone with approval permission cannot approve a canceled order.

Spring Security supports request-level and Java method-level authorization (for example `@PreAuthorize` when the application enables method security). However, conditions based on actual data such as **order ownership** must be implemented properly. If you only check the USER role and omit the ownerId check, you can still suffer from IDOR/BOLA vulnerabilities.

| Case | Authentication | Authorization |
| --- | --- | --- |
| Unauthenticated guest accesses /private | None yet | Access not granted |
| Logged-in USER accesses /admin | Succeeded | Denied |
| USER views their own profile | Succeeded | Allowed by policy |
| USER views another USER's order | Succeeded | Must be denied by ownership check |

### 2.3. Protection Against Common Web Risks

**CSRF (Cross-Site Request Forgery):** A malicious site can trigger a request to a website where the victim is logged in; the browser may automatically send cookies along with it. In the default servlet configuration, Spring Security enables CSRF protection for unsafe HTTP methods such as POST, PUT, PATCH, and DELETE. Checking the CSRF token helps prevent forged state-changing requests. Do not disable CSRF globally just because you call the application a "REST API"; you must evaluate whether the browser automatically sends credentials. Applications using cookies or HTTP Basic in a browser may still need CSRF protection.

**Session security:** The framework provides mechanisms supporting session management, session fixation protection, and logout handling. Session configuration must fit the application type; for instance, an API authenticating via a token on every request has different needs than a website using sessions/cookies.

**HTTP security headers:** Spring Security can set several response headers that help reduce risks. You need to understand the limits of each header: Content-Security-Policy (CSP) does not automatically appear as a tailored policy for every website; HTTPS/TLS and cookie safety must be configured properly across the entire system.

**Distinguishing CSRF, CORS, and XSS:** CSRF is forging a user's request; CORS governs cross-origin response reading permissions in the browser; XSS is executing untrusted code inside a page. Enabling CORS does not replace authentication, authorization, or CSRF checks.

## 3. Where Does Spring Security Intercept Requests?

In a **Spring MVC/Servlet** application, Spring Security typically runs at the **Servlet filters** layer, before the Controller is invoked. Typical flow:

~~~text
HTTP Client
   |
   v
Servlet container
   |
   v
DelegatingFilterProxy -> FilterChainProxy
   |
   v
SecurityFilterChain selected for the request
   |-- security context, CSRF, authentication, authorization, ...
   |         |
   |         +-- Failure -> reject / prompt for login
   |
   v
DispatcherServlet -> Controller -> Service -> Repository
   |
   v
HTTP response
~~~

Key components:

- **SecurityFilterChain:** A set of security filters matching a group of requests. A system can use multiple filter chains, each with a different matcher scope. Rules must be placed in the right chain and in the right order.
- **AuthenticationManager / AuthenticationProvider:** Participates in verifying credentials according to a specific authentication mechanism; can connect to UserDetailsService, a password encoder, or other providers.
- **Authentication:** Represents the principal and authorities after authentication.
- **SecurityContext:** Holds the active Authentication. For Servlet applications, SecurityContextHolder typically uses a ThreadLocal strategy; do not assume that mechanism applies verbatim to WebFlux or arbitrary asynchronous threads.
- **Authorization:** Makes the allow or deny decision before protected code runs; checks can happen at the HTTP or method layer.

Spring WebFlux uses **reactive WebFilter and reactive security context**, and is not configured with HttpSecurity like the Servlet example below.

### HTTP 401, 403, and Login Redirects

- **401 Unauthorized:** The client has not sent valid authentication credentials or authentication failed for an endpoint requiring login.
- **403 Forbidden:** The identity is authenticated but lacks permission, or was rejected by another security policy such as CSRF.
- **302 Redirect:** In an application using form login, an unauthenticated user may be redirected to the login page instead of receiving 401.

The exact status code depends on the configured entry point and exception handling. You should not assume every Spring Security application returns the exact same response.

## 4. Java 17+ Practice: Distinguishing Public, Private, and Admin

The following example uses **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. You need a Java 17+ Spring Boot project with the Boot plugin and build tool already set up. In **build.gradle** (Groovy DSL), add the dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Create **src/main/java/com/example/securitydemo/SecurityDemoApplication.java**:

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint() {
        return "private OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

The source code above is a single valid Java file: one public class named **SecurityDemoApplication**, and one package-private class named **DemoController**. Spring Boot scans components in the same package and recognizes the Controller. Dependency versions come from the Spring Boot BOM, so you do not need to hardcode versions on the two dependency lines.

**Configuration analysis:**

1. **/public** uses permitAll so anyone can call it; **/private** requires authenticated; **/admin** uses hasRole("ADMIN"). Spring Security interprets hasRole("ADMIN") as requiring the authority **ROLE_ADMIN**.
2. **anyRequest().denyAll()** rejects requests not explicitly matched in the demo. A real project must add needed endpoints, such as health checks or static resources, with an intentional policy.
3. **httpBasic** enables HTTP Basic for testing with curl. **formLogin(form -> form.disable())** removes the login page redirect in the demo; it does not mean every application should disable form login.
4. **InMemoryUserDetailsManager** creates the test account **learner** with the USER role; it does not have the ADMIN role. BCryptPasswordEncoder hashes the password before storing it in memory.
5. The demo only has GET endpoints, so **CSRF is not disabled**. If you add POST/PUT/DELETE, you need to design CSRF tokens or policies suited to the authentication method.

Run from the project root directory (with Gradle Wrapper):

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell use **.\gradlew.bat bootRun**. Once started successfully and listening on localhost:8080, try:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner:learn123 http://localhost:8080/private
curl -i -u learner:learn123 http://localhost:8080/admin
~~~

On PowerShell, use **curl.exe** if **curl** is aliased to another command. Expected statuses:

| Request | HTTP status | Content/meaning |
| --- | --- | --- |
| /public, no credentials | 200 | Response body: public OK |
| /private, no credentials | 401 | HTTP Basic challenges for authentication |
| /private, learner:learn123 | 200 | Response body: private OK |
| /admin, learner:learn123 | 403 | Authentication succeeded, missing ROLE_ADMIN |

If a wrong password is sent, /private does not return 200. Only if an account is actually granted the ADMIN role can /admin return 200. This is a clear way to test the difference between **authentication** and **authorization**.

**Demo limitations:** Hard-coded accounts and passwords are for learning only. In production, you must use a managed identity source, store secrets securely, use **HTTPS**, apply proper session/token policies, and implement brute-force protection. HTTP Basic transmits credentials in Base64, **not encrypted passwords**, so it must never be sent over plain HTTP on a real network.

## 5. How Do Session, JWT, OAuth2, and OIDC Relate?

Spring Security supports these mechanisms, but they serve different roles:

| Option | High-level Operation | What Must Be Designed |
| --- | --- | --- |
| Session + cookie | Server stores login state, browser sends cookie | Secure/HttpOnly/SameSite cookies, session timeout, CSRF |
| HTTP Basic | Client sends username/password in Authorization header | Mandatory HTTPS, limit intended usage |
| Bearer token/JWT | Client presents token for API to verify signature and claims | Issuer, audience, expiry, keys, permissions, and revocation |
| OAuth2 | Delegated authorization standard; has client, authorization server, resource server | Flows, scopes, token management, and trust |
| OpenID Connect | Identity layer on top of OAuth2, with ID token and sign-in flow | Verify ID token, issuer, audience, nonce when applicable |

Example: an API receives a JWT access token from an identity provider. Spring Security can verify Bearer JWTs when properly configured as an **OAuth2 Resource Server**. Simply installing spring-boot-starter-security **does not issue JWTs**, does not make the app an SSO login server, and does not make every API stateless.

JWT is a **token format**; it does not mean the data inside is encrypted or that it grants access to every resource. Successful signature verification does not replace authorization checks at each endpoint and resource.

## 6. What Does Spring Boot Do by Default When Spring Security Is Present?

In a Spring Boot web application that has not declared its own replacement security configuration, adding Spring Security to the classpath typically causes HTTP endpoints to require authentication. Boot creates **a development user** with a random password printed in the logs and may use form login or HTTP Basic depending on the request/Accept header.

This is a **precautionary default** when first adding the library, not a production authentication system. Once you define your own **SecurityFilterChain**, Boot's default URL policy yields to your application's policy. When you define your own **UserDetailsService**, Boot's default user no longer needs to be created.

You should not expect defaults to automatically authorize data by ownerId, configure OAuth2/JWT, protect every business endpoint, or operate rate limiting for the system.

## 7. Common Misconceptions and Configuration Mistakes

1. **"Spring Security is enabled, so the app is secure."** False: overly broad permitAll, missing data checks, or business logic flaws still cause leaks.
2. **"Being logged in means accessing everyone's data."** False: you need resource ownership policies, permissions, and business state checks.
3. **"JWT is a built-in login feature of starter-security."** False: you must design the token issuer, resource server, and verification setup.
4. **"It's a REST API, so just disable CSRF."** False: models where cookies/credentials are auto-sent still face CSRF risk even when returning JSON.
5. **"CORS helps the server verify the user."** False: CORS is only a browser policy for cross-origin access.
6. **"Role USER is enough to authorize orders."** False: a role does not prove that ownerId matches the logged-in user.
7. **"Passwords can be stored in plaintext or reversible encryption."** False: use password hashing with proper salt/cost.
8. **"SecurityFilterChain automatically stops SQL injection, XSS, SSRF, and secret leaks."** False: you also need validation, parameterized queries, output encoding, outbound request controls, secret management, and dependency update processes.
9. **"401 and 403 are always identical across all applications."** False: it depends on the auth scheme, entry point, CSRF, and exception handler; form login may return a redirect.
10. **"A filter checking roles is enough to protect business logic."** False: many conditions depend on data only available in the Service/Repository layer; checks must use the real identity.

## 8. Checklist for Applying to a Real Application

1. **List endpoints:** public, authenticated-only, admin, method-specific, and owner-scoped resources.
2. **Choose the identity mechanism:** session or OAuth2/OIDC/token; account source and credential management approach.
3. **Configure policy:** matchers with explicit order, deny by default for unspecified paths, use method security when needed.
4. **Protect data:** check data ownership from the database and business state, not just roles.
5. **Protect the web layer:** HTTPS, secure cookies, CSRF according to the threat/risk model, intentionally configured CORS and security headers.
6. **Test different users:** anonymous, wrong password, USER, ADMIN, USER A trying to view USER B's data; check both status codes and payloads.
7. **Operations:** audit events, monitor abuse, rate limiting, secret management, update dependencies, and conduct periodic security reviews.

## 9. Self-Check

**Q1.** A USER logs in successfully but gets 403 when accessing /admin. Which step failed?  
**Answer:** Authorization; authentication succeeded.

**Q2.** Why is authenticated() on /orders/123 not secure enough?  
**Answer:** authenticated() does not check whether the current user owns order 123.

**Q3.** Does Spring Security automatically issue JWTs when adding starter-security?  
**Answer:** No. You must implement/configure token-issuing components, token verification, and the corresponding policies.

**Q4.** Should an API using login cookies disable CSRF just because it only accepts JSON?  
**Answer:** You cannot conclude that. You must evaluate how the browser automatically attaches cookies, the HTTP methods used, and how to prevent forged requests.

## 10. Official Documentation

- Servlet architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
- CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot security auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html
