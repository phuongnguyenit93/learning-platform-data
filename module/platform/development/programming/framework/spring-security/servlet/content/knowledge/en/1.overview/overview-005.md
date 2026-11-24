# Distinguishing Session-Based, HTTP Basic, and Bearer Token Security in Spring Security Servlet

## Objectives and Context

After this lesson, you will be able to: explain how browsers/clients transmit proof of authentication; distinguish server-side state, lifecycle, and revocation mechanisms of the three approaches; understand how CSRF/XSS relate; and choose Spring Security configurations for Servlet websites or APIs.

HTTP does not inherently remember that two requests came from the same sender. After the initial authentication, the client must carry proof to protected requests. Three common options are a **session ID in a cookie**, **username/password in HTTP Basic**, and an **access token in a Bearer header**. All three require HTTPS in real deployments.

**Authentication** answers "who is calling?"; **authorization** answers "does this user have permission to perform that action?". In Spring Security Servlet, Authentication holds the request's principal and authorities; SecurityContextHolder lets code during the request access Authentication. Whether SecurityContext is maintained across requests depends on how context is stored/restored and the session policy. Successful authentication does not mean access to every endpoint is permitted.

**Cookie is not synonymous with session**: a cookie is a browser mechanism for storing and automatically attaching a value. **Bearer is not synonymous with JWT**: Bearer is a way of presenting a token in a request; the token can be a JWT or an opaque string.

## 1. Session-Based Security

### Flow from Login to Logout

1. The browser opens the login form and POSTs username, password, and a CSRF token over HTTPS.
2. Spring Security verifies the account via AuthenticationProvider. Upon successful authentication, the form login flow saves the corresponding SecurityContext into HttpSession according to the configured mechanism.
3. The server sends the browser a session identifier, usually in the JSESSIONID cookie. The browser automatically attaches that cookie to subsequent requests if domain/path/cookie attributes permit.
4. The server looks up the session ID, finds the still-valid session, and restores Authentication to check permissions. The browser **does not have to re-send the password** on every request.
5. Valid logout can clear SecurityContext and invalidate HttpSession; sessions can also expire due to idle timeout or application policy.

Illustrative messages:

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<temporary-id>

username=alice&password=<password>&_csrf=<csrf-token>

HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=<new-id>; Path=/; HttpOnly; Secure; SameSite=Lax
Location: /
~~~

This is only a flow example, **not fixed output**: Set-Cookie/SameSite, whether a pre-login cookie exists, redirect URLs, and how session IDs are issued depend on version/configuration, reverse proxies, and the application. Spring Security includes **session fixation** protection, typically rotating the ID after successful login; never let the client dictate an authenticated session ID.

### Advantages, Limitations, and Protections

Session-based security is convenient for server-rendered HTML websites, form logins, or backend-for-frontend (BFF) architectures. The server can invalidate a session immediately, control idle time, and enforce server-side logout. When running multiple instances, you must have a shared session store strategy (for example, Spring Session with a centralized store) or an appropriate routing mechanism.

If an attacker obtains a still-valid session ID, they can hijack the session. You need HTTPS; appropriate **Secure**, **HttpOnly**, and **SameSite** cookies; minimal Domain/Path scope; clear timeouts and logout. HttpOnly reduces direct cookie reading by JavaScript, but does not stop malicious scripts from sending requests on the user's behalf. SameSite is an additional defense, not an automatic replacement for CSRF tokens.

**CSRF is especially critical for cookie-based sessions**: the browser automatically attaches cookies when a user visits matching URLs, including requests triggered from another site in certain situations. State-changing operations require CSRF protection or a properly designed alternative; Spring Security enables CSRF by default in standard Servlet security configurations.

## 2. HTTP Basic Authentication

HTTP Basic requires the client to send an Authorization header on requests requiring authentication:

~~~http
GET /api/profile HTTP/1.1
Authorization: Basic <Base64(username:password)>
~~~

The Basic value is Base64 of username:password. **Base64 is an encoding representation, not secret encryption**; simply decoding Base64 reveals the credentials. Therefore Basic must travel over HTTPS, restrict account privileges, never log headers, and never put real passwords into URLs/scripts/tickets.

In Spring Security, **BasicAuthenticationFilter** reads the header, authenticates via AuthenticationManager/Provider, and establishes Authentication for the request. With SessionCreationPolicy.STATELESS, Spring Security does not use HttpSession to store/retrieve SecurityContext; every request must carry the Basic header itself. Authentication may still require looking up users or password hashes.

HTTP Basic is **not automatically stateless in every configuration**. Session policy and SecurityContextRepository determine whether the application uses sessions; if you want a session-independent API, set the policy explicitly.

Advantages are simplicity and compatibility with curl, HTTP tools, and internal scripts. Disadvantages are that raw credentials are sent frequently, and it is difficult to revoke a single device or client if multiple places share one password. Browsers can cache and automatically re-send Basic credentials, resulting in poor logout UX, and **Basic over a browser cannot be assumed immune to CSRF**.

Missing/invalid credentials in a Basic API typically result in **401 Unauthorized** with a WWW-Authenticate: Basic realm="..." header. When a user is authenticated but lacks permission, the response is typically **403 Forbidden**.

## 3. Bearer Token Authentication

The client obtains an access token from an authorization server or identity provider via an appropriate flow, such as OAuth 2.0 Authorization Code + PKCE for user applications, or Client Credentials for backends. The client sends the token to the resource server:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <access-token>
~~~

**Bearer** means whoever holds a valid token can generally use it. Bearer itself does not bind the token to a specific sender, machine, or connection. Consequently, you must protect tokens from leakage/replay and minimize permission scope and lifetime; systems needing stronger replay protection may consider sender-constrained token mechanisms.

Two common types of access tokens:

- **Opaque token**: a string issued by the issuer whose structure the API does not decode to infer permissions. The resource server typically uses token introspection or a trusted state store to confirm the token is still active and check scopes.
- **JWT access token**: claims packaged inside the token, usually consisting of three Base64URL parts. The API can verify the signature and check exp, nbf, iss, appropriate audience, permission scopes, and trust policy. **Decoding a JWT payload is not signature verification**. Signed JWTs normally do not encrypt their contents, so never place secrets in claims.

Spring Security OAuth2 Resource Server reads Bearer tokens via **BearerTokenAuthenticationFilter**, using a JwtDecoder/validator or an opaque-token introspector. Upon successful authentication, the system places the principal/authorities into SecurityContext; afterward, authorizeHttpRequests rules still decide access permissions. With a JWT Resource Server, scopes typically map to authorities like SCOPE_orders.read if the token has scope orders.read.

### Lifetime, Revocation, and Storage

Access tokens should have short lifetimes, the right API audience, and minimal scopes. **Self-verifying JWTs** save the resource server from introspection on every request, but a leaked token can continue to be accepted until expiration unless additional revocation mechanisms exist. **Opaque tokens** make centralized status control/querying convenient, at the cost of extra dependency and latency. JWTs need short lifetimes and supplementary denylists/introspection if immediate revocation is required.

Refresh tokens (if issued) are used to request new access tokens at the token endpoint—**never send them in place of access tokens to resource APIs**; protect and rotate refresh tokens according to the issuer's design. Logging out by deleting tokens on the client **does not automatically revoke a JWT on the server**.

For browsers, tokens stolen via XSS can be reused. Avoid treating storing long-lived access tokens in localStorage as a safe default. A BFF can keep tokens on the server side and give the browser a protected session cookie. If placing a Bearer token in a cookie for the browser to send automatically, evaluate CSRF just like any other auto-sent credential. Using an Authorization header explicitly added by code reduces cookie-style CSRF surface, but does not eliminate XSS and does not replace HTTPS.

## 4. Comparison Table

| Criterion | Session | HTTP Basic | Bearer Token |
| --- | --- | --- | --- |
| Proof sent | Session ID, typically via Cookie | Authorization: Basic ... | Authorization: Bearer ... |
| Password per request | No; typically only at login | Yes, as Base64 username:password | No; sends access token |
| Server-side auth state | Typically needs HttpSession/store | No session needed if set STATELESS, but still validates credentials | JWT typically self-verifying; opaque typically needs introspection/store |
| Expiration | Session timeout/app policy | Depends on password/credential policy | Token lifetime/exp and issuer policy |
| Revocation/logout | Invalidating session is relatively direct | Hard to log out a single browser/client that cached credentials | Depends on token type, short lifetime, and revocation strategy |
| CSRF | Must consider because browser auto-sends cookies | Must consider if browser auto-sends Basic | Explicitly added headers rarely face cookie-style CSRF; tokens in cookies carry CSRF risk |
| Characteristic risks | Session hijacking, fixation, CSRF | Password exposure, credential reuse, browser cache | Token theft/replay, overly broad scopes, flawed JWT verification |
| Common use cases | Browser websites, BFF | Simple tools/scripts over HTTPS | APIs, mobile, OAuth2, and service-to-service |

All three can be replayed if credentials are stolen. Properly configured HTTPS prevents eavesdropping in transit; it does not protect against accidental logging, XSS, malicious extensions, or a compromised client machine.

## 5. Spring Boot 3.x / Spring Security 6 Servlet Examples

The examples use **Java 17+**, Spring MVC Servlet, spring-boot-starter-web, and spring-boot-starter-security. The JWT Resource Server also requires spring-boot-starter-oauth2-resource-server. The configuration classes below are **alternative options** in one application: pick one option while learning, or if you want them to coexist, use separate SecurityFilterChains with specific securityMatcher and @Order.

Place the Java classes under a package scanned by @SpringBootApplication, such as example.security. These are configuration snippets for a Spring Boot project with the required dependencies; they are not standalone Java files compiled with javac without libraries.

### 5.1. Session + formLogin

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SessionSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(withDefaults())
                .logout(withDefaults())
                .build();
    }
}
~~~

With default formLogin, an unauthenticated browser hitting a protected endpoint is usually redirected to /login. After valid login, the browser holds a session cookie. CSRF protection remains enabled; sending POST /logout requires a valid CSRF token under default configuration. In production, enforce HTTPS and cookie security flags appropriate to your network/proxy, control session expiry, and manage real users.

### 5.2. HTTP Basic Without HttpSession

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class BasicSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(withDefaults())
                .build();
    }
}
~~~

Here STATELESS instructs Spring Security not to rely on HttpSession to maintain SecurityContext. **The example still keeps CSRF enabled by default**; state-changing requests such as POST without a CSRF token may receive 403. Only decide to disable CSRF after verifying the system accepts no credentials automatically attached by browsers (be especially careful with browser-cached Basic credentials).

### 5.3. Bearer JWT Resource Server

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class BearerSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
                .build();
    }
}
~~~

Only disable CSRF as above when this is an API accepting Bearer tokens via the Authorization header and **not** using cookies/Basic credentials automatically sent by browsers. Using a JWT Resource Server requires a trusted identity provider that issues JWTs; this API does not issue JWTs itself.

File application.yml—replace issuer-uri with a real issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

Add the dependency to your application's Gradle build if not already present:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The JWT decoder validates the token based on the issuer and appropriate keys, while checking configured validators. If the API requires a specific audience, you must configure audience validation accordingly; issuer-uri alone does not enforce all application-specific audience policies. In this example, GET /api/** requires authority SCOPE_orders.read. A missing, expired, or invalid token typically causes 401; an authenticated token lacking the authority causes 403. For opaque tokens, configure introspection instead of jwt(...).

### 5.4. Demo User and Endpoint for Observing Basic/Form Login

For local study environments only, you can add a user with a real PasswordEncoder instead of storing plaintext passwords in configuration:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode("local-example-only"))
                        .roles("USER")
                        .build());
    }
}
~~~

Create a controller in package example.web (under @SpringBootApplication's example package):

~~~java
package example.web;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/api/hello")
    public String hello(Principal principal) {
        return "Xin chào " + principal.getName();
    }
}
~~~

When running the Boot application with **BasicSecurityConfig**, **DemoUsersConfig**, **HelloController**, and a localhost HTTP URL for local study, the following command sends a Basic header:

~~~bash
curl -i -u learner:local-example-only http://localhost:8080/api/hello
~~~

If the server and configuration above are running, the exact response body is **Xin chào learner** (no newline from the controller). Do not use unencrypted HTTP over real networks; switch to HTTPS and do not leave production credentials in command history. Omitting -u or supplying the wrong password typically yields HTTP 401. When switching to **SessionSecurityConfig** instead of Basic, opening /api/hello in an unauthenticated browser will typically redirect to /login; log in and reload to observe the browser sending the JSESSIONID cookie. This demo user does not enable the JWT Resource Server to issue tokens.

## 6. Debugging Requests Properly

When inspecting DevTools Network, HTTP logs, or curl, observe the **presence of headers** and status codes, but mask all passwords, tokens, and session IDs before sharing.

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Unauthenticated browser calling a protected URL gets 302 | Form login AuthenticationEntryPoint redirects to /login | Check chain, entry point, and redirect flow |
| Basic API with missing/wrong username/password gets 401 | Authentication failed | Check Basic header, PasswordEncoder, user store |
| Missing, expired, or bad-signature JWT gets 401 | Resource Server could not validate Bearer | Check issuer, JWK, expiry, token type, and clock skew |
| Logged in but gets 403 | Missing authority/role or blocked by CSRF protection | Check permissions, scope mapping, HTTP method, and CSRF token |
| Session user suddenly becomes anonymous | Cookie not sent, session expired/not shared across instances | Check Secure/SameSite/Path, proxy, TTL, session store |
| API with valid token returns 401 | Request may hit the wrong SecurityFilterChain or validator rejects it | Check securityMatcher/@Order, JWT vs. opaque, and validation |

**HTTP 401** usually means no valid authentication is present and may include WWW-Authenticate (Basic or Bearer). **HTTP 403** usually means the request lacks sufficient permissions or is rejected by CSRF policy. For HTML form login pages, unauthenticated requests typically receive a 302 redirect instead of 401. Exact responses are governed by AuthenticationEntryPoint and exception handling.

Key filters to recognize in Spring Security Servlet: UsernamePasswordAuthenticationFilter for form login; BasicAuthenticationFilter for Basic; BearerTokenAuthenticationFilter for Bearer; AuthorizationFilter for permission rules. SecurityContextHolderFilter/SecurityContextRepository assist in restoring context per configuration. Filters do not automatically turn a credential-valid request into an authorized request.

When a system has both a session-based website at /web/** and a Bearer API at /api/**, separate SecurityFilterChains with clear securityMatcher and @Order; consider dedicated CSRF, session policy, entry point, and permissions for each endpoint group. Do not put every mechanism onto a single chain and assume clients will always receive the desired challenge.

## 7. Choosing an Approach and Avoiding Common Mistakes

**Traditional website or BFF:** session cookies with CSRF protection, Secure/HttpOnly/SameSite, timeout, and invalidation. Suitable when the server owns the login experience and can manage sessions.

**Mobile API, SPA, or OAuth2/OIDC integration:** Bearer access tokens with limited lifetime, scope, and audience; Resource Server verifies issuer/signature/claims or introspects opaque tokens. For browsers, consider PKCE, token storage, XSS, and BFF instead of long-lived localStorage.

**Simple internal scripts:** Basic can fit if HTTPS is enforced and secrets are managed carefully; avoid sharing one broad-privilege password across many clients. As permission granularity/credential lifecycle grows, consider dedicated per-client tokens.

**Service-to-service calls:** Bearer tokens via OAuth2 Client Credentials or short-lived workload identities are usually easier to scope and manage in lifecycle than passing user passwords.

Misconceptions to correct immediately:

1. "Basic uses Base64 so it is as safe as encryption." — No; Base64 is reversible.
2. "Bearer tokens are always JWTs." — No; opaque tokens are also Bearer.
3. "A JWT with three parts is definitely valid." — No; you must verify signature, issuer, expiration, audience, scope, and trust policy.
4. "STATELESS means the entire system has no state." — No; it is an HttpSession/SecurityContext policy in Spring Security.
5. "Any REST API should disable CSRF." — No; you must check which credentials browsers send automatically.
6. "An Authorization header eliminates all CSRF." — Not if the system also accepts cookies or cached Basic; client design and CORS/CSRF must be evaluated.
7. "Deleting a JWT in the browser revokes the token on the server." — No; the JWT can still remain valid until expiration.
8. "Being authenticated grants access to all URLs." — No; authorization checks permissions independently.

## Self-Check Questions

1. Why does a session ID avoid re-sending the password every time, while Basic still sends username:password on each request?
2. Why can browser-cached Basic credentials be vulnerable to CSRF even though they do not use a session cookie?
3. If a JWT has a valid signature but the wrong audience or is expired, should the API accept it?
4. Why is invalidating a server-side session easier than immediately revoking an unexpired self-verifying JWT?
5. When a Servlet application needs both form login at /web/** and Bearer JWT at /api/**, how should SecurityFilterChain, CSRF, and SessionCreationPolicy be organized?

When comparing any options, always identify in order: **where the proof of authentication lives**, **how the server verifies and maintains that proof**, and **how permission to perform actions is checked**.