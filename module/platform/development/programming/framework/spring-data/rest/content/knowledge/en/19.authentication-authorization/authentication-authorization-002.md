# Session or Bearer Token Authentication by Application Architecture

Spring Data REST exports repositories as an HTTP API. Every request to collection, item, search, and association resources must pass through the application's authentication and authorization policies. Spring Security supports multiple authentication mechanisms, among which two common models are **session cookies** and **bearer tokens**.

- **Session authentication** fits interactive web applications with user login. The server maintains the session, and the browser sends the session cookie on subsequent requests.
- **Bearer token authentication** fits API clients, mobile apps, or service-to-service communication. The client explicitly sends an access token in the Authorization header.
- Both can be supported in one system, but routes and credential policies must be clearly separated. CSRF protection must match how the browser sends credentials.

Authentication identifies who the request belongs to; authorization decides what that principal is allowed to do. CORS only controls cross-origin requests from a browser and the ability to read responses. CORS does not replace authentication or authorization.

## 1. Spring Data REST requests go through Spring Security

Requests pass through the Spring Security filter chain before reaching the Spring Data REST dispatcher and repositories. Typical flow:

1. A browser or API client sends a request to a resource, such as GET /people.
2. Spring Security reads credentials from a session cookie or the Authorization header.
3. The authentication mechanism verifies the credentials and creates an Authentication object.
4. Authorization rules check whether the request is allowed to proceed.
5. Spring Data REST handles the request and invokes the repository.
6. If method security is enabled, annotations on the repository or service can also check permissions when the method is called.

Exporting a repository as a REST resource does not mean that endpoint is automatically public. Access depends on the filter chain, method security, and application configuration.

Unauthenticated requests typically receive 401 Unauthorized or are redirected to a login page depending on the application type. Authenticated users lacking sufficient permissions typically receive 403 Forbidden.

## 2. How does session authentication work?

Sessions are suitable when a browser is the primary client and users log into a stateful web application.

After a successful login:

- Spring Security authenticates the login credentials.
- The server stores the SecurityContext in the HTTP session.
- The browser receives a session identifier cookie, typically JSESSIONID.
- Subsequent requests send that cookie according to the browser's cookie policy.
- The server looks up the session to restore the user's identity and authorities.

Session cookies should be configured with Secure, HttpOnly, and SameSite appropriate to the application topology. HttpOnly prevents JavaScript from reading the cookie; Secure restricts the cookie to HTTPS. SameSite must be chosen based on how the frontend and API are deployed, especially if they reside on different sites.

Example filter chain configuration for a web application using form login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .build();
    }
}
~~~

IF_REQUIRED allows Spring Security to create a session when the authentication flow requires it. For traditional web applications, this is usually the right behavior. Spring Security's default CSRF protection remains enabled; do not disable it just to make POST, PUT, PATCH, or DELETE from the browser work.

## 3. CSRF protection when using session cookies

Browsers automatically send cookies according to domain, path, SameSite, and credential policies. A malicious site could try to make a logged-in user's browser send a state-changing request to the API. That is why applications using session cookies need CSRF protection for state-changing requests.

With Spring Security:

- Keep CSRF protection enabled for requests using session cookies.
- Obtain the CSRF token using the mechanism configured by the application.
- Send the token in the header or parameter expected by the server.
- Do not treat SameSite as a complete replacement for CSRF tokens.
- Do not use GET to perform state-changing operations.

An SPA can use CookieCsrfTokenRepository so the browser receives a cookie containing the CSRF token and sends the token back in a request header. Basic configuration example:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

In this configuration, the CSRF cookie must be readable by JavaScript to send the token in a request header, so the CSRF cookie is marked non-HttpOnly. The session cookie should remain HttpOnly. Implement the SPA request handler according to the Spring Security version in use; starting with Spring Security 6, deferred tokens and BREACH protection may require a dedicated token request handler.

Spring Data REST write operations such as POST, PUT, PATCH, and DELETE require a CSRF token when authenticated via session cookie. If the token is missing, Spring Security typically rejects the request before the repository is invoked.

## 4. How does bearer token authentication work?

Bearer tokens are suitable when the client explicitly sends an access token on each request. Tokens are usually issued by an authorization server after an appropriate OAuth 2.0 or OpenID Connect flow.

The request looks like:

~~~http
GET /people
Authorization: Bearer eyJ...
Accept: application/hal+json
~~~

The resource server verifies the token and builds an Authentication. For JWTs, verification typically includes signature, issuer, expiration, and required claims; the system may also check audience and scopes as required.

A bearer token is not trustworthy just because it looks like a JWT string. The server must verify the token with the appropriate issuer, keys, and trust configuration. Do not accept tokens from query parameters or URLs; tokens should only be passed via secure headers.

## 5. Configuring Spring Security Resource Server for JWT

With Spring Boot, add the resource server starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Configure the issuer URI so Spring Security discovers metadata and JWT verification keys from the authorization server:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.com/issuer
~~~

Example filter chain for a bearer-token API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
~~~

Only disable CSRF in a filter chain for stateless APIs when credentials are sent explicitly via Authorization: Bearer and the API does not rely on automatically sent cookies for authentication. If the same endpoint accepts either session cookies or bearer tokens, you cannot arbitrarily disable CSRF for cookie-based requests. Separate the routes/filter chains or design an explicit credential policy.

STATELESS instructs Spring Security not to create or use an HTTP session to store the SecurityContext for that chain. Tokens are verified on every request. This is the right choice for stateless bearer APIs.

## 6. Distinguishing scopes, roles, and authorities

JWTs may carry claims such as scope, scp, roles, or permission groups depending on the authorization server. Spring Security Resource Server typically maps OAuth scopes to authorities prefixed with SCOPE_.

For example, a token with scope people.read can be checked using:

~~~java
.requestMatchers(HttpMethod.GET, "/people/**")
.hasAuthority("SCOPE_people.read")
~~~

Method security can also check authorities:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.data.repository.CrudRepository;

@PreAuthorize("hasAuthority('SCOPE_people.write')")
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~

Enable method security if using PreAuthorize:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Do not assume a roles claim is automatically mapped the same way as scope. If the authorization server issues roles under a custom claim, configure a JwtAuthenticationConverter or appropriate converter to map claims to GrantedAuthority instances. Then check the exact authority names in the filter chain and method annotations.

URL-level and method-level authorization can complement each other. URL rules decide whether a request can enter a resource; method rules protect repository/service operations even when called from another flow within the application.

## 7. Supporting both sessions and bearer tokens in one system

An application may have a browser UI using sessions and a mobile/service API using bearer tokens. A clean approach is to split the API surface by route, then use separate SecurityFilterChain beans with explicit priority ordering.

Example architecture:

| Route | Credential | Session policy | CSRF |
|---|---|---|---|
| /web/** | Session cookie | IF_REQUIRED | Enabled |
| /api/** | Bearer JWT | STATELESS | Can be disabled if cookie auth is not used |
| /actuator/health | Public per deployment policy | Independent of UI session | Per endpoint configuration |

A filter chain for the API can be scoped with securityMatcher("/api/**"); the remaining chain handles web routes. Ensure the Spring Data REST base path falls cleanly within the chosen route matcher.

Do not create two chains that both match all requests with unclear ordering. Spring Security only uses the first chain that matches the request. If matchers are wrong, a request may fall into another chain with unintended authentication, CSRF, or session policies.

If the same URI must support both cookies and bearer tokens, clearly design how credentials are distinguished and keep CSRF protection for cookie-authenticated requests. Do not simply disable CSRF across the whole API just because some clients send bearer tokens.

## 8. CORS when the frontend has a different origin

If the browser frontend and Spring Data REST API have different origins, configure CORS for allowed frontend origins, methods, and required headers.

Example:

~~~java
@Configuration
public class RestCorsConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        cors.addMapping("/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-XSRF-TOKEN",
                "If-Match",
                "If-None-Match"
            )
            .allowCredentials(true)
            .exposedHeaders("Location", "ETag", "Link");
    }
}
~~~

Adjust the configuration according to the authentication mode:

- Cross-origin session cookies may require allowCredentials(true) and appropriate SameSite/Secure cookie configuration.
- Bearer tokens typically require allowing the Authorization request header.
- If the client sends a CSRF header, that header must be allowed.
- If the frontend reads Location or ETag, expose those response headers.

Do not combine wildcard origin * with credentialed CORS. CORS does not grant data access permissions and does not replace CSRF or authorization. When using Spring Security, ensure CORS is processed before preflight requests are blocked by authentication.

## 9. Session cookies and bearer tokens have different storage risks

Session cookies are typically managed by the browser and sent automatically according to cookie policy. Cookie configuration should include:

- Secure when running over HTTPS.
- HttpOnly so JavaScript cannot read the session cookie.
- SameSite suited to the topology and login flow.
- Path and Domain as narrow as possible for the deployment.

Bearer tokens are possession credentials: anyone possessing the token can use it until it expires or is revoked. Therefore:

- Do not log tokens or place them in URLs, analytics, or error reports.
- Use HTTPS for all requests.
- Prefer short-lived access tokens with minimal scopes.
- Store tokens according to an appropriate threat model; avoid long-term storage where arbitrary JavaScript can read them if safer options exist.
- Use refresh-token rotation/revocation according to the authorization server's policy.
- Do not forward tokens to another host merely because the API returned a link.

If a bearer token is placed in a cookie automatically sent by the browser, requests again exhibit CSRF characteristics like cookie credentials. Never treat a JWT as an automatic reason to disable CSRF.

## 10. Checking 401 and 403 responses

The two status codes must be distinguished:

| Status | Meaning | Examples |
|---|---|---|
| 401 Unauthorized | Request lacks valid credentials or token is invalid/expired | Missing token, expired session, wrong JWT issuer |
| 403 Forbidden | Authenticated but insufficient permissions or rejected by CSRF policy | Missing scope, insufficient role, missing CSRF token |

For browsers using form login, unauthenticated requests may be redirected to a login page instead of returning 401 JSON. For bearer APIs, return 401/403 responses according to the API contract so clients handle them clearly.

Do not return internal details about signatures, keys, or sensitive claims in the error body. Log on the server with a correlation ID and enough diagnostic information, without logging raw bearer tokens or session IDs.

## 11. Example API calls using a session cookie

You can test a session flow with curl by saving cookies in a cookie jar. Illustrative example with form login:

~~~bash
curl -i -c cookies.txt -X POST https://api.example.com/login -H "Content-Type: application/x-www-form-urlencoded" --data "username=demo&password=REPLACE_ME"
~~~

After logging in, use the cookie jar for subsequent requests:

~~~bash
curl -i -b cookies.txt -H "Accept: application/hal+json" https://api.example.com/people
~~~

For write requests, obtain the CSRF token according to the application contract and send it along with the session cookie:

~~~bash
curl -i -b cookies.txt -X POST https://api.example.com/people -H "Content-Type: application/json" -H "X-XSRF-TOKEN: REPLACE_WITH_CSRF_TOKEN" --data '{"name":"An Nguyen"}'
~~~

The login endpoint name, how the CSRF token is obtained, and the exact header depend on configuration. Do not put real passwords in shell history or shared scripts.

## 12. Example API calls using a bearer token

The client sends the access token in the header:

~~~bash
curl -i -H "Authorization: Bearer REPLACE_WITH_ACCESS_TOKEN" -H "Accept: application/hal+json" https://api.example.com/people
~~~

If the endpoint requires a write scope:

~~~bash
curl -i -X POST https://api.example.com/people -H "Authorization: Bearer REPLACE_WITH_ACCESS_TOKEN" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data '{"name":"An Nguyen"}'
~~~

Tokens must be issued by a trusted issuer and carry the appropriate scope/authority. Do not rely on fake or expired tokens to conclude an endpoint works; test valid tokens, missing scopes, and expired tokens in tests.

## 13. Testing sessions and bearer tokens with MockMvc

Spring Security Test provides request post-processors to test different authentication states. Example for an authenticated session/user:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void authenticatedSessionUserCanReadPeople() throws Exception {
    mockMvc.perform(get("/people").with(user("alice").roles("USER")))
        .andExpect(status().isOk());
}

@Test
void sessionWriteRequiresCsrfToken() throws Exception {
    mockMvc.perform(post("/people")
            .with(user("alice").roles("USER"))
            .contentType("application/json")
            .content("{\"name\":\"An\"}"))
        .andExpect(status().isForbidden());
}

@Test
void sessionWriteSucceedsWithCsrfToken() throws Exception {
    mockMvc.perform(post("/people")
            .with(user("alice").roles("USER"))
            .with(csrf())
            .contentType("application/json")
            .content("{\"name\":\"An\"}"))
        .andExpect(status().isCreated());
}
~~~

To test bearer JWTs, use the jwt() request post-processor from Spring Security Test:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void bearerScopeCanReadPeople() throws Exception {
    mockMvc.perform(get("/people")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_people.read")
            )))
        .andExpect(status().isOk());
}
~~~

These tests assume corresponding URL rules and repository fixtures. For integration tests verifying real JWTs, validate issuer, signature, audience, and expiry using the actual resource server configuration; jwt() mainly tests authorization behavior without needing to sign real tokens.

## 14. Checklist for choosing and implementing authentication

- Identify the primary clients: web browser, SPA, mobile, service, or a mix.
- Choose session for interactive browser flows needing server-side sessions; choose bearer for API clients sending explicit tokens.
- With session cookies, keep CSRF protection enabled and configure Secure/HttpOnly/SameSite cookies.
- With bearer JWTs, configure trusted issuer/JWK and validate expiry, issuer, audience, and scopes.
- Only make an API stateless and disable CSRF when the API genuinely does not use automatically sent cookie credentials.
- If supporting both, separate routes/filter chains or apply an appropriate CSRF policy per credential type.
- Protect Spring Data REST in the filter chain and consider method security for repositories/services.
- Configure CORS for the origins, request headers, and response headers needed by the browser.
- Return 401 for unauthenticated requests and 403 for authenticated requests lacking permissions per the API contract.
- Do not log passwords, session IDs, or raw bearer tokens.
- Test anonymous requests, valid sessions, expired sessions, missing CSRF, valid bearer tokens, expired tokens, and missing scopes.

Official references:

- [Spring Security — Servlet Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
