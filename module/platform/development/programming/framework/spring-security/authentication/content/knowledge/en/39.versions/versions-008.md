# Reviewing Differences Across Servlet, Reactive, and External Integration Libraries

## 1. Why Is “Right Version” Not Enough for Safe Application Authentication?

In the Java ecosystem, Spring Security provides both **Servlet security** and **Reactive WebFlux security**, yet they **are not interchangeable API layers**. An application can compile cleanly, serve endpoints, and still be insecure because the security chain is not triggered, principals come from the wrong context, or external IdP/JWT/LDAP integration libraries are incompatible with the framework version.

Examples:

- A tutorial snippet with `HttpSecurity` and `SecurityFilterChain` gets copied into a WebFlux project using `ServerHttpSecurity` and `SecurityWebFilterChain`. The beans may fail to guard the right request paths.
- A Spring MVC application adds `spring-boot-starter-webflux` just to use `WebClient`, then mistakenly assumes all authorization must move to reactive security.
- OAuth2 login client is enabled, yet the Bearer JWT API lacks resource-server configuration; token verification never happens where needed.
- A team upgrades Spring Boot 3.x to Boot 4.x while keeping an old `spring-security-test` or SSO library, causing classpath/auto-configuration errors and tests failing to construct the right security context.
- Another JWT library parses tokens on its own and builds an authenticated `Authentication` while skipping `aud`, `iss`, algorithm, and key rotation checks.
- Spring Security 7.x removed certain deprecated APIs, while an external integration plugin was still compiled for Security 5/6.
- The app uses `javax.servlet.*` from legacy integration code while Spring Framework 6+ moved to the Jakarta namespace; Boot 4 raises the Jakarta EE baseline further.

**Goal of this lesson:** learn how to **audit the version set, runtime stack, security filters, third-party library contracts, and test evidence** before upgrading or adding authentication features.

Three principles:

1. **Choose the stack by runtime:** Servlet MVC and WebFlux have different entry points, security contexts, and lifecycles.
2. **Choose a compatible dependency set:** Boot BOM, Spring Security modules, Spring Framework, servlet/reactive servers, and external libraries must be managed as one coherent set.
3. **Test real boundaries:** unit tests that only mock a principal do not prove browser login, JWT decoders, IdP callbacks, or reverse proxies behave correctly.

## 2. Conceptual Map: Layers That Must Be Verified

~~~text
[HTTP client / browser]
        |
        v
[Reverse proxy / Gateway / TLS termination]
        |
        v
[Spring Boot Runtime]
        |
        +--------------------------+
        |                          |
        v                          v
  Servlet / Spring MVC         Reactive / WebFlux
  - Servlet Filter             - WebFilter
  - HttpServletRequest         - ServerWebExchange
  - SecurityFilterChain        - SecurityWebFilterChain
  - HttpSecurity               - ServerHttpSecurity
  - AuthenticationManager      - ReactiveAuthenticationManager
  - SecurityContextHolder      - ReactiveSecurityContextHolder
  - HttpSession / Spring       - WebSession / reactive
    Session                      session support
        |                          |
        +-------------+------------+
                      |
                      v
           [External integrations]
           OAuth2 Client / Resource Server
           OIDC / SAML2 / LDAP / WebAuthn
           JWT libraries / IdP SDKs
           Spring Session / Gateway / Cloud
                      |
                      v
            [Authorization + Audit]
~~~

This is a **role diagram**, not a requirement that an application run both branches. Most services should pick **one primary server runtime stack**, adding client libraries from the other stack only for concrete reasons.

“Servlet” and “Reactive” in this lesson refer to the **server-side security execution model**. Java `CompletableFuture`, `WebClient`, or a service method returning `Mono` does not by itself turn the security chain into WebFlux.

## 3. Snapshot of Version Generations to Distinguish

At the time this document was cross-checked (November 2026), two common lines exist for preparation and migration:

| Layer | Spring Boot 3.x / Spring Security 6.x | Spring Boot 4.x / Spring Security 7.x |
|---|---|---|
| Java baseline | Java 17+. | Java 17+ remains baseline; use newer LTS if supported across the whole system. |
| Spring Framework | 6.x (Boot 3). | 7.x (Boot 4). |
| Jakarta | Jakarta EE 9+/10 depending on Boot/Framework version. | Jakarta EE 11 baseline; Servlet 6.1 for Servlet servers. |
| Embedded Servlet | Check specific runtime against Boot 3.x dependency management. | Tomcat 11.x or Jetty 12.1.x per Boot 4 release/docs; do not carry over old containers. |
| Security configuration | `SecurityFilterChain`, lambda DSL; address deprecations before moving to 7. | Deprecated APIs removed per migration; keep using matching Servlet/Reactive types. |
| Spring Security OAuth Authorization Server | Module/project managed per dependency generation. | Integrated into Spring Security 7; re-check artifact/starters and APIs. |
| Jackson | Typically Jackson 2 per Boot 3.x defaults. | Jackson 3 is the default direction; serialization APIs/configs require review. |
| Test support | `spring-security-test` matching Security/BOM version, Boot test starter. | Boot 4 modular test starters, e.g., `spring-boot-starter-security-test` for security test integration. |

**Never choose a version merely because “7 is bigger than 6”.** Read the **support policy, dependency constraints, and breaking changes** of your actual Boot + Security + Framework combination. Spring Security 6.5 is the guided branch to **prepare** for upgrading to 7.0; not every 6.x release can jump straight across without changes.

Per the referenced documentation, Spring Security stable docs provide the 7.1.x and 6.5.x lines; patch numbers evolve over time. **Pin patches in the BOM/build** and record the inspection date rather than hardcoding “latest” into modules.

### Java 17+ and Jakarta Packages

If older source contains:

~~~java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
~~~

on Spring Framework 6+/Boot 3+ it generally must switch to:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
~~~

This is a **namespace change** for Servlet APIs, not a blind replace of every `javax.*` across the project: `javax.crypto` and `javax.net` belong to Java SE and keep those names. A plugin binary compiled for `javax.servlet.Filter` cannot be considered compatible with `jakarta.servlet.Filter` merely because both run on Java 17.

With Boot 4, check Servlet 6.1 compatibility, JPA/Validation, app servers, the Spring Cloud release train, testing libraries, and related plugins—not just Servlet imports.

## 4. Why Not Mix Versions Manually in Maven/Gradle?

Spring Boot provides **dependency management (BOM)**. Each Boot generation manages a compatible set covering Spring Framework, Spring Security, Jackson, Reactor, Tomcat/Jetty, Spring Session, and many other dependencies.

Maven Boot 3.x example:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version><!-- Approved Boot 3.x patch --></version>
</parent>
~~~

In this guide, this is a **configuration template** with a comment in place of a version, not a ready-to-run POM. In real projects, specify an actual patch release and normally **omit versions** for dependencies managed by Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

A common mistake is:

~~~xml
<!-- Configuration risking ecosystem drift -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>7.1.2</version>
</dependency>
~~~

in a Boot 3.x app managing Security 6.x. Do not mix `spring-security-web` 7.x with `spring-security-config` 6.x just to grab a new feature; that can trigger `NoSuchMethodError`, `NoClassDefFoundError`, bean mismatches, or unexpected behavior changes.

With Gradle, use the Spring Boot plugin/dependency management or a matching Gradle platform BOM; **do not declare each security artifact at a different version**. When forced to override for a CVE, verify the override sits in a compatible line and test thoroughly; a higher patch number alone does not guarantee a safe drop-in replacement.

## 5. Maven/Gradle Dependency Graphs Are Part of Security Review

Before comparing Servlet and Reactive code, export the **effective dependency graph**:

~~~bash
# Maven (Linux/macOS/Git Bash):
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework
mvn help:effective-pom

# Gradle:
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core \
  --configuration runtimeClasspath
~~~

On Windows PowerShell/cmd, use `gradlew.bat` instead of `./gradlew` when using the Windows wrapper. These commands read dependencies and require a real Maven/Gradle project. Do not use `dependency:tree` alone to infer support policies if it only lists artifacts; cross-check release notes.

Signals to look for:

- Are there **two major versions** of Spring Security on the dependency tree?
- Are Jackson 2 and Jackson 3 used cleanly per integration contract, or does a third-party library pull old classes?
- Does the classpath include `javax.servlet` inside a plugin running alongside `jakarta.servlet`?
- Are `spring-boot-starter-web`/`webmvc` and `webflux` present at the same time? Why?
- Does any library pull its own `spring-security-oauth2-resource-server` version differing from the BOM?
- Are two different JWT decoders running, or does a library bypass Spring validators?
- Does `spring-security-test` match the runtime security version? Does Boot 4 have the right companion test starter?
- Does a SAML/LDAP/WebAuthn adapter require a specific JDK, Jakarta, Reactor, or Servlet version?

**SBOM, CVE scanning, license checks, and support matrices** should cover compile, runtime, and test scopes. A library in test scope alone can skew test outcomes; a library pulled transitively into runtime can bring old cryptography/JWT code.

## 6. Where Do Servlet Security and Reactive Security Differ?

| Capability | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| HTTP abstraction | `HttpServletRequest`, `HttpServletResponse`, `Filter`. | `ServerWebExchange`, `ServerHttpRequest`, `WebFilter`. |
| Security pipeline | `FilterChainProxy` and `SecurityFilterChain`. | `WebFilterChainProxy` and `SecurityWebFilterChain`. |
| Configuration | `HttpSecurity`. | `ServerHttpSecurity`. |
| Authentication entry | `AuthenticationManager` / `ProviderManager`. | `ReactiveAuthenticationManager`, reactive manager resolution. |
| User lookup | `UserDetailsService`, potentially blocking DB/LDAP access. | `ReactiveUserDetailsService` or reactive integration; avoid blocking the event loop. |
| Request principal | `SecurityContextHolder` in the Servlet request/thread model. | `ReactiveSecurityContextHolder`/Reactor Context along the reactive subscription. |
| Authorization | `authorizeHttpRequests`, Servlet `AuthorizationManager`, and method security. | `authorizeExchange`, reactive authorization managers, reactive method security. |
| Session | Servlet `HttpSession`; Spring Session Servlet. | WebFlux `WebSession`; reactive session implementation. |
| CSRF | `CsrfFilter` and Servlet token repositories. | Reactive CSRF WebFilter/repositories. |
| CORS | Servlet CORS filter/config. | Reactive CORS/WebFilter config. |
| Testing | `MockMvc` and Servlet security post-processors. | `WebTestClient` and reactive `SecurityMockServerConfigurers`. |
| Default server | Servlet container (e.g., Tomcat). | Typically Reactor Netty or supported reactive server. |

Never write a helper like “read `SecurityContextHolder` in every service” if services run in reactive pipelines; ThreadLocal does not follow Reactor scheduling reliably. Conversely, never treat `ReactiveSecurityContextHolder` as the source of truth in a normal synchronous Servlet controller without an intentionally designed bridge.

### The Difference Is Not Just the Return Type

Returning `Mono<ResponseEntity<?>>` from a method does not prove the security stack switched. Check the **server runtime, HandlerMapping, filter chain, request abstraction, and context propagation**. Spring WebFlux can coexist as a client dependency in a Servlet app; Boot’s default web application type when both MVC and WebFlux are on the classpath is usually Servlet unless explicitly configured otherwise.

## 7. Servlet `SecurityFilterChain`: Integration Example

This snippet uses Spring MVC/Spring Security Servlet and requires Boot-compatible dependencies plus a `JwtDecoder`/issuer URI if enabling a JWT resource server.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**This is an integration snippet**, not standalone JDK 17 code. It needs resource-server JOSE support, a decoder, and security policies for CSRF, sessions, errors, scopes, method security, and reverse-proxy trust. A valid JWT with the wrong `aud` must not be accepted automatically if the API has an audience policy; configure the corresponding `JwtDecoder` validator.

Important:

- `securityMatcher("/api/**")` selects **the chain’s scope**.
- `requestMatchers("/api/health")` decides **authorization inside the chain**.
- Without a fallback chain, endpoints outside `/api/**` matching no chain may **go unprotected by Spring Security**. Never mistake `anyRequest().authenticated()` for “every request on the whole server”.
- With multiple chains, `@Order` and matchers must be tested for every route, especially actuator, login, oauth2 callbacks, and new endpoints.
- Custom `OncePerRequestFilter` classes belong to the Servlet stack; filter order must be defined and never copied to WebFlux.

### Authentication in Servlet

`AuthenticationManager` receives an `Authentication` request and can dispatch via `DaoAuthenticationProvider`, `JwtAuthenticationProvider`, LDAP providers, or custom API-key providers. If no provider supports the request class, `ProviderNotFoundException` may occur. This arrangement belongs to Servlet-style manager/provider design; do not assume it copies verbatim to the reactive manager contract.

## 8. WebFlux `SecurityWebFilterChain`: Separate Integration Example

In a dedicated WebFlux application:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new org.springframework.security.web.server.util.matcher
                    .PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/health").permitAll()
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This is a **reactive integration snippet**; do not place it beside a Servlet config in the same project expecting both chains to guard one request together. It requires a `ReactiveJwtDecoder`/issuer config, WebFlux runtime, and a fallback chain plan protecting URLs outside `/api/**`. For Spring Security 7.x, verify APIs against the exact version managed by your BOM.

Key differences from Servlet:

- `ServerHttpSecurity` replaces `HttpSecurity`.
- `SecurityWebFilterChain` replaces `SecurityFilterChain`.
- `authorizeExchange` replaces `authorizeHttpRequests`.
- `pathMatchers` and `ServerWebExchangeMatcher` operate on server exchanges rather than Servlet RequestMatchers.
- `ReactiveAuthenticationManager` returns `Mono<Authentication>` and must preserve reactive context.
- Reactive CSRF/session/logout and token handlers use different server abstractions.

**Never block the event loop:** if a custom reactive authentication provider calls blocking JDBC/LDAP or `Thread.sleep` on a Netty event loop, throughput and login latency degrade severely. Use reactive-capable integrations, or offload blocking calls to a bounded scheduler by design while monitoring saturation and timeouts. Never assume `@Async` is a safe context-switching fix.

## 9. Reactive SecurityContext and ThreadLocal: A Common Project Trap

Servlet code typically retrieves the user via:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

In a reactive flow, a request can hop across threads; using Servlet-style ThreadLocal can return `null` or the wrong context’s authentication. Reactive paths should rely on Reactor Context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> authenticatedName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .filter(auth -> auth != null && auth.isAuthenticated())
        .map(Authentication::getName);
}
~~~

This is an **integration method** in a reactive project, not a standalone `javac` program. If no security context exists, the `Mono` may complete empty; endpoints must enforce explicit policies instead of treating “anonymous” as authenticated by default.

### Context Propagation

Be careful when using:

- `publishOn`/`subscribeOn`, Reactor operators, asynchronous callbacks.
- `CompletableFuture` or libraries unaware of Reactor Context.
- Custom schedulers, message listeners, background jobs.
- RSocket, GraphQL, gRPC adapters with their own context propagation.
- Blocking clients invoked inside a WebFlux security chain.

**Never copy `SecurityContextHolder` into a static field** or `InheritableThreadLocal` to “keep the user”; that risks leaking identities across requests/threads. For background jobs, pass a **trusted business identity/correlation** per explicit contract and re-check authorization at the resource operation.

## 10. Same Feature, Different Integration Modules

| Feature | Servlet Approach | Reactive Approach | External Integration to Audit |
|---|---|---|---|
| Username/password | Form login/Basic + UserDetailsService/AuthenticationProvider. | Reactive authentication + ReactiveUserDetailsService. | Password encoder, LDAP, blocking vs. reactive datastore. |
| OAuth2 Login/OIDC RP | Servlet OAuth2 client filters, session/authorization request repository. | Reactive OAuth2 client/OIDC support in WebFilter pipeline. | IdP discovery, issuer, callback/redirect, state/nonce, client registration. |
| Resource Server JWT | Bearer filter + JwtDecoder/JwtAuthenticationConverter. | Reactive bearer WebFilter + ReactiveJwtDecoder. | JOSE/JWK library, key rotation, issuer/audience validators. |
| Opaque token | Introspection client/opaque token provider. | Reactive introspection/client. | AS outage, introspection credentials, cache, TTL/revocation. |
| SAML2 Login | `spring-security-saml2-service-provider` module with Servlet support. | Check official support for your stack/version; do not assume identical feature set. | OpenSAML dependency, metadata, certificates, clock skew, logout. |
| LDAP | Spring Security LDAP provider. | Verify connector support; many LDAP drivers/binds are blocking. | LDAP SDK, TLS/LDAPS, pooling/timeouts. |
| WebAuthn/passkeys | Version-matched Spring Security WebAuthn support; custom ceremony/challenge policy. | Verify native reactive support before designing. | FIDO2/WebAuthn library, origin/RP ID, attestation/credential store. |
| Session | HttpSession/Spring Session Servlet. | WebSession/Spring Session reactive. | Redis/JDBC, serializers, cookie flags, cross-node revocation. |
| Gateway | Servlet gateway/proxy, forwarded headers trust. | Spring Cloud Gateway Reactive on WebFlux. | Gateway starter/release train, forwarded identity, token relay, route filters. |
| Testing | MockMvc, spring-security-test Servlet helpers. | WebTestClient + reactive security test configurers. | Test starters, embedded IdP, MockWebServer/WireMock variants. |

Do not infer from a feature appearing in the **Servlet reference guide** that an **equivalent reactive API** exists. Spring Security splits documentation into “Servlet Applications” and “Reactive Applications”; check feature availability, provider classes, test support, and lifecycles in the matching branch.

## 11. OAuth2 Login and Resource Server Are Not the Same Integration

They differ in both **purpose** and **dependencies**:

- **OAuth2 Client / OIDC RP (`oauth2Login`):** the app sends browsers to an IdP, receives callbacks, runs the authorization-code flow, and creates principals/sessions. Needs `state`, `nonce`, PKCE per client policy, client registration, and public redirect URIs.
- **OAuth2 Resource Server (`oauth2ResourceServer`):** the API receives Bearer tokens and verifies JWT signatures or opaque-token introspection, issuer, audience, expiry, scopes, and authority mappings.
- **OAuth2 Authorization Server:** issues tokens, manages clients/grants/consent, and signs/rotates keys; this is a distinct role, not automatically included by configuring Resource Server.

An application can play multiple roles, yet **each path must be configured separately**. Adding the OAuth2 client dependency does not add the JWT Resource Server filter; enabling JWT does not make the app handle OIDC callbacks.

### Changing Spring Authorization Server Versions

Spring Security 7 documentation notes that Spring Authorization Server **was brought into Spring Security**. When upgrading from older projects using a standalone Authorization Server artifact/starter to Security 7 / Boot 4, cross-check **new dependency coordinates, packages, configuration DSL, persisted authorization data, and Jackson serialization**. Never just bump `spring-security-oauth2-authorization-server` in the POM and assume existing DB token rows still deserialize.

**Do not use legacy OAuth2 libraries `spring-security-oauth`/`@EnableAuthorizationServer` from years-old examples for new production configs** without verifying maintenance and compatibility. Those older-generation modules may not support Spring Security 6/7 or Jakarta EE.

## 12. JWT/JOSE: Never Let External Libraries Bypass Spring Validators

Spring Security Resource Server commonly uses `spring-security-oauth2-resource-server` with `spring-security-oauth2-jose` for JWTs. `Nimbus JOSE + JWT` and related libraries may appear transitively; the dependency tree must confirm versions expected by the BOM and your integrations.

### What Token Validators Must Verify

1. Signatures under an algorithm allowlist; reject `alg=none` unless policy explicitly allows it (it should not).
2. Keys/JWKS from a trusted issuer/key provider; clear rotation and caching policies.
3. Exact `iss` matching a trusted issuer; never trust an arbitrary issuer just because it exposes a public JWKS.
4. `aud` includes the target API resource; never accept an OIDC ID Token as an API access token.
5. `exp`, `nbf`, and reasonable clock skew; reject expired tokens.
6. Client/scopes/authorities mapped from trusted claims; never grant `ROLE_ADMIN` from a self-asserted client claim.
7. Token purpose and multi-tenant identity binding `(iss,sub)` or verified identity links.
8. Revocation/epoch/introspection strategy if tokens must be blocked prior to `exp`.

### Risks When Using External JWT SDKs

If an external SDK decodes the Base64 JWT payload and code executes:

~~~java
// NEVER treat parsing claims as token verification:
// String payload = new String(Base64.getUrlDecoder().decode(parts[1]));
// Authentication auth = makeAuthenticatedFrom(payload);
~~~

then attackers can forge claims if signatures go unverified. Use a properly configured `JwtDecoder`/`ReactiveJwtDecoder` or security-reviewed library **before** creating an authenticated `SecurityContext`.

Never construct `JwtAuthenticationToken` directly from client JSON and think real authentication occurred. `jwt()` in `spring-security-test` is a **mock helper**; it does not check signatures, issuers, or audiences. Add integration tests with signed test tokens and negative cases.

## 13. SAML2, LDAP, Kerberos, CAS, and WebAuthn: Check the Feature Matrix

**SAML2 Service Provider:** Spring Security supports SAML2 login with appropriate integrations. Verify OpenSAML libraries, security dependencies, Java/Jakarta versions, XML signature validation, metadata/certificate rotation, clock skew, and logout. SAML2 feature availability/hooks must be checked **for Servlet vs. reactive specifically**. Never copy SAML’s `Saml2WebSsoAuthenticationFilter` into WebFlux.

**LDAP/Active Directory:** LDAP clients can use blocking I/O and custom TLS trust rules. In Servlet, `LdapAuthenticationProvider` and `UserDetailsService` are common patterns. In WebFlux, never place blocking LDAP binds on the Netty event loop; evaluate adapters, timeouts, and schedulers where needed. Accounts locked/disabled in the directory must produce authentication failures rather than failing open when LDAP is unavailable.

**CAS/Kerberos:** some integrations have dedicated modules/security extensions. Spring Security 7 docs note that the Kerberos extension was integrated into Spring Security; do not assume older CAS/Kerberos adapter libraries automatically support Jackson 3/Jakarta EE 11. Inspect specific modules, maintainers, and release trains.

**WebAuthn/FIDO2/passkeys:** WebAuthn requires origin/RP IDs, challenge binding, public-key credential stores, counter/replay policies, session/user binding, and browser support. An older provider library may limit Servlet APIs even if core crypto runs on JDK 17. Verify native support in the exact Spring Security version/stack and integrated FIDO2 libraries.

**MFA libraries:** TOTP, push, SMS/email OTP, and backup codes may come from separate solutions. Never turn a password-success event into “MFA completed” merely because an external provider returned `authenticated=true`; enforce consistent assurance evidence and step-up policies.

## 14. Spring Session, Redis/JDBC, and Serializer Versioning

Sessions are fragile when upgrading Boot/Security/Framework or switching from Servlet to reactive:

| Area to Check | Servlet | Reactive |
|---|---|---|
| Session abstraction | `HttpSession` / Spring Session Servlet. | `WebSession` / Spring Session reactive. |
| `SecurityContext` persistence | `SecurityContextRepository` and session storage. | `ServerSecurityContextRepository`/Reactor exchange. |
| Repository | Spring Session Redis/JDBC depending on type. | Supported reactive-compatible repository/store. |
| Cookie name/flags | Servlet container or Spring Session `CookieSerializer`. | Reactive WebSession/session cookie configurator. |
| Logout/revocation | Invalidate server-side session, remember-me, related grants. | Invalidate WebSession, security context, and token grants. |
| Serializer | May hold serialized security principals/contexts. | May use a different serializer/context contract. |

Never migrate Java-serialized `SecurityContext` objects from an older system straight into a newer one without migration testing, especially as **Spring Security 7 / Boot 4 shifts to Jackson 3** for related JSON serialization. With JDK serialization, class/version compatibility raises its own issues. Isolate session-store migration, enforce TTLs, and plan fallback logout/re-auth.

Changing an auth-principal class or package can make persisted sessions from the previous release fail to deserialize. Test canary deployments where sessions created by the old release are read by the new one, especially during blue/green rolling upgrades when **two versions share a Redis keyspace**.

**Not every cookie name is controlled by `server.servlet.session.cookie.*`** if a Spring Session custom `CookieSerializer` owns the cookie; inspect actual `Set-Cookie` headers. Even while cookies remain valid, JWT resource servers can operate independently of sessions and require separate grant revocation.

## 15. Spring Cloud Gateway, Service Mesh, and Proxy Identity Libraries

Many Spring Cloud Gateway projects run **Reactive WebFlux**, yet Spring Cloud Gateway also offers a **Server MVC** option; never infer from the word “Gateway” that the entire pipeline is reactive. Check the starter, runtime, WebFilter/Servlet Filter stack, and release train compatible with Boot.

Key boundaries:

- Gateways terminate TLS, can act as **OAuth2 clients**, and relay tokens downstream.
- Backend resource servers must **verify tokens themselves or enforce an explicit trust contract**; never trust `X-Forwarded-User` from the Internet.
- `X-Forwarded-For`/`Forwarded`/`Host` can be spoofed by clients; trusted edges must strip and rewrite them.
- Gateways can apply rate limiting and route filtering, yet service-side authorization must still guard bypass paths.
- Token relay only forwards tokens; it **never creates downstream permissions** if claims/audiences are wrong.
- A security SDK in the gateway may depend on Servlet classes if you choose the wrong artifact, causing missing classes or unexecuted filters.

### Spring Cloud Compatibility

Never upgrade Spring Boot while keeping an arbitrary Spring Cloud BOM. **Each Spring Cloud release train supports specific Boot versions**. Check the Spring Cloud compatibility matrix and starters like Gateway, Config, Circuit Breaker, and Security integrations at actual versions. With reactor-netty/reactive gateway, also verify Netty/Reactor baselines.

A compiling dependency tree does not prove starter auto-configuration did not back off or filter order did not change. Integration tests through the proxy/routes are mandatory.

## 16. Spring Boot 4 Modular Starters and Test Starters

Per the Boot 4 migration guide, dependency/starter coordinates are modularized more granularly. Notable coordinate changes:

| Capability | Common Boot 3 Coordinate | Boot 4 Migration Guide Coordinate |
|---|---|---|
| MVC server | `spring-boot-starter-web`. | `spring-boot-starter-webmvc`. |
| WebFlux server | `spring-boot-starter-webflux`. | `spring-boot-starter-webflux`. |
| Security core/web | `spring-boot-starter-security`. | `spring-boot-starter-security`. |
| OAuth2 client | `spring-boot-starter-oauth2-client`. | `spring-boot-starter-security-oauth2-client`. |
| OAuth2 resource server | `spring-boot-starter-oauth2-resource-server`. | `spring-boot-starter-security-oauth2-resource-server`. |
| Spring Session Redis | `spring-session-data-redis` or Boot integrations. | `spring-boot-starter-session-data-redis`. |
| Security test | `spring-security-test` + Boot starter test. | `spring-boot-starter-security-test` per Boot 4 test modularity docs. |
| Web MVC test | `spring-boot-starter-test` and MVC test support. | `spring-boot-starter-webmvc-test`; choose companion tech test starters. |

This table is a **starting point for auditing**, not a claim that older coordinates stop resolving in every repository. Update only dependencies actually used in your project and read the migration guide for your patch release; do not copy all starters if the app does not use them.

The Boot 4 migration guide also emphasizes test-infrastructure modularization. Annotations like `@WithMockUser`/`@WithUserDetails` should run with the **matching security test starter**, rather than relying on an accidental combination of leftover transitive dependencies.

In Boot 4, the Servlet 6.1 baseline **removed Undertow support** per the Boot 4.0 migration guide at the time of reference; if an older app uses Undertow, that is a **migration decision**, not just a dependency version bump. Evaluate alternative containers, performance, and deployment constraints.

## 17. What Needs Special Attention When Upgrading Spring Security 6.5 → 7.x?

Spring Security migration docs recommend moving to **Security 6.5** and completing preparation steps before upgrading to 7.x. Audit:

1. **Removed deprecated APIs:** locate APIs marked deprecated in 6.x and switch to replacements per migration docs.
2. **Lambda/Customizer DSL:** remove unsupported chaining styles and verify `HttpSecurity` and `ServerHttpSecurity` APIs for the right branch.
3. **Authorization management:** check `AuthorizationManager`, request matching, and method security; never assume old configs continue matching routes identically.
4. **Default behavior:** re-verify public/protected endpoints, CORS/CSRF, session fixation, request caches, headers, and stateless APIs after upgrading.
5. **Serialization:** check Jackson 2 → Jackson 3, `SecurityJackson` modules, and OAuth2 Authorization Server persisted objects.
6. **Integrated extensions:** Authorization Server/Kerberos modules and third-party adapters may change coordinates.
7. **Test dependencies:** Boot 4 companion starters, Spring Security test helpers, JUnit compatibility.
8. **Servlet containers:** Jakarta EE 11/Servlet 6.1, proxy/forwarded headers, and `HttpSession` behavior.
9. **Reactive context:** Reactor/WebFlux/Netty versions and custom reactive filters.
10. **Monitoring:** exception mapping, authentication events, authorization denials, and log redaction.

### Jackson 3 Is Especially Important

Per the Security 7 migration guide, configuring Jackson 2 `ObjectMapper` with `SecurityJackson2Modules` transitions to Jackson 3 `JsonMapper.Builder` with `SecurityJacksonModules`. Authorization Server in Security 7 defaults to Jackson 3. If token/authorization/session stores hold serialized security objects, test **reading old data, writing new data, and rollback/rolling upgrades**; never assume persisted JSON stays compatible just because the security API builds.

**Migration is not just running `mvn versions:set`.** Audit runtime behavior and live data (sessions, OAuth grants, JWK keys, refresh token families).

## 18. Audit Process for External Integration Libraries

When a project needs Auth0/Okta/Keycloak SDKs, LDAP adapters, Nimbus/JJWT, Spring Cloud Gateway, CAS/SAML plugins, Spring Session Redis, or custom OAuth providers, build a compatibility profile for each library:

| Attribute | What to Record |
|---|---|
| `group:artifact:version` | Exact coordinates and artifact source. |
| Maintainer / release date | Is the library actively maintained and receiving security patches? |
| Java baseline | Java 17/21/25, bytecode compatibility, JPMS/module restrictions. |
| Spring Framework/Security baseline | Must run with Security 6 or 7, Servlet or reactive? |
| Jakarta/Servlet/Netty | `javax.servlet` or `jakarta.servlet`? Servlet version? Reactor Netty baseline? |
| Jackson/JSON | Jackson 2 vs. 3, serializer modules, API types. |
| Role in authentication | Client, Resource Server, Authorization Server, Gateway, token parser, or Identity Provider adapter? |
| Authentication principal type | `OAuth2User`, `OidcUser`, `JwtAuthenticationToken`, custom `Authentication`? |
| Filter/WebFilter | Which chain, what order, which matchers? |
| Trust contract | Token signature/issuer/audience, TLS, forwarded headers, IdP trust. |
| Configuration properties | Auto-config metadata, property names, bean-conditional behavior. |
| Tests | Unit, integration, contract tests against IdP/backend, negative security cases. |
| Vulnerabilities / license | CVEs, transitive dependencies, EOL, upgrade path. |

**A vendor’s “Spring Boot compatible” claim is insufficient.** It must specify **Boot 3.x vs. Boot 4.x, Servlet vs. reactive, and Spring Security 6.x vs. 7.x**. If an adapter only supports Servlet filters, never force it into WebFlux and treat a compiling unit test as proof.

For custom integrations, prefer **thin adapters implementing standard Spring Security interfaces**, separating cryptographic verification, subject mapping, and token/permission policy from web filters; this eases migration and reduces vendor lock-in.

## 19. Auditing Filter Order and “Bypass Paths” When Integrating SDKs

An external SDK often supplies a Servlet `Filter`, `OncePerRequestFilter`, Spring `AuthenticationProvider`, or WebFlux `WebFilter`. When installing it:

~~~text
Ingress -> Spring Security FilterChainProxy
             |
             +-- request matcher picks chain
             +-- custom SDK filter at chosen order
             +-- bearer / form / oauth2 filter
             +-- SecurityContext
             +-- AuthorizationFilter
             |
          Controller / Method security
~~~

Questions to answer:

- Does the SDK filter run **inside** or outside `FilterChainProxy`?
- Does it populate `SecurityContextHolder` before verifying the token?
- Does it bypass `AuthorizationFilter` or return HTTP 200 when authentication fails?
- Does it build the right `Authentication` type and use the right manager/provider?
- Does it emit duplicate audit events, or emit none on custom paths?
- If the SDK throws an exception, do the app’s `AuthenticationEntryPoint`/`AccessDeniedHandler` handle it?
- Does it read bearer tokens/cookies from query strings or log them?
- In reactive apps, does it use Reactor Context instead of Servlet ThreadLocal?
- Do logout/revocation and session cleanup still work when a new SDK version changes principal classes?

**Never fix an SDK mismatch by putting `permitAll` on sensitive endpoints or setting `authenticated=true` manually.** Integration failures must fail closed.

## 20. Testing: MockMvc vs. WebTestClient and Client-Bound Testing

**Servlet / MockMvc:**

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

// Integrates into a Spring MVC WebApplicationContext test:
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

`MockMvc` + `springSecurity()` runs the test context’s Servlet security filters. `@WithMockUser`/`user()` simulate an authenticated principal to test authorization. To prove password login, submit `formLogin()` against a real `UserDetailsService`/provider in the test profile.

**Reactive / WebTestClient:**

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

// Integrates into a WebFlux ApplicationContext test:
WebTestClient client = WebTestClient.bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

`mockUser()`/`mockJwt()` reactive security configurers populate authentication on the reactive exchange. They differ from Servlet `SecurityMockMvcRequestPostProcessors.user()`/`jwt()`.

**Note:** `WebTestClient` also has an adapter for MockMvc or live HTTP servers; the client name alone does not prove the runtime uses WebFlux. Choose security mutators matching the **server binding type**.

### What Mocks Do Not Verify

- `jwt()`/`mockJwt()` do not verify real token JWT signatures, issuers, audiences, or expiry.
- `@WithMockUser` does not test `PasswordEncoder`, account lock/disable, or login providers.
- `mockOAuth2Login`/`oidcLogin()` do not test authorization-code callbacks, `state`, `nonce`, or PKCE.
- A controller test slice may omit the full security configuration or custom filters.

To test safely, combine **positive/negative HTTP integration tests**, decoder/provider unit tests, and external IdP/LDAP/Redis contract tests via Testcontainers or reliable mock servers.

## 21. Standalone Java 17: A Decision Matrix Instead of Guessing the Stack

The following program **runs on pure JDK 17** with no Spring dependencies. It illustrates how to **select the right configuration and flag conflicts** from a deployment descriptor. It **does not** introspect Maven dependencies, includes no real security filters, and never replaces test results. Use it to learn how to formalize decisions before reviewing integration libraries.

Save `SecurityStackAuditDemo.java`:

~~~java
public class SecurityStackAuditDemo {

    enum Stack { SERVLET, REACTIVE }
    enum LibraryKind { SERVLET_FILTER, REACTIVE_WEBFILTER, PURE_CRYPTO }

    record AuditRequest(Stack stack, LibraryKind library,
                        int bootMajor, int securityMajor,
                        boolean jackson2Serializer) {}

    static String audit(AuditRequest request) {
        if (request.bootMajor() == 3 && request.securityMajor() != 6) {
            return "VERSION_MISMATCH";
        }
        if (request.bootMajor() == 4 && request.securityMajor() != 7) {
            return "VERSION_MISMATCH";
        }
        if (request.bootMajor() != 3 && request.bootMajor() != 4) {
            return "UNSUPPORTED_EXAMPLE_PAIR";
        }
        if (request.stack() == Stack.SERVLET
                && request.library() == LibraryKind.REACTIVE_WEBFILTER) {
            return "WRONG_WEB_STACK";
        }
        if (request.stack() == Stack.REACTIVE
                && request.library() == LibraryKind.SERVLET_FILTER) {
            return "WRONG_WEB_STACK";
        }
        if (request.bootMajor() == 4 && request.jackson2Serializer()) {
            return "REVIEW_JACKSON_MIGRATION";
        }
        return "REVIEW_EXTERNAL_CONTRACT";
    }

    static void show(String name, AuditRequest request) {
        System.out.println(name + ": " + audit(request));
    }

    public static void main(String[] args) {
        show("mvc-ok", new AuditRequest(
                Stack.SERVLET, LibraryKind.SERVLET_FILTER,
                3, 6, false));
        show("wrong-security-major", new AuditRequest(
                Stack.SERVLET, LibraryKind.SERVLET_FILTER,
                3, 7, false));
        show("reactive-servlet-sdk", new AuditRequest(
                Stack.REACTIVE, LibraryKind.SERVLET_FILTER,
                4, 7, false));
        show("mvc-reactive-filter", new AuditRequest(
                Stack.SERVLET, LibraryKind.REACTIVE_WEBFILTER,
                4, 7, false));
        show("jackson-migration", new AuditRequest(
                Stack.REACTIVE, LibraryKind.PURE_CRYPTO,
                4, 7, true));
        show("reactive-ok", new AuditRequest(
                Stack.REACTIVE, LibraryKind.REACTIVE_WEBFILTER,
                4, 7, false));
    }
}
~~~

Run:

~~~bash
javac SecurityStackAuditDemo.java
java SecurityStackAuditDemo
~~~

**Exact stdout:**

~~~text
mvc-ok: REVIEW_EXTERNAL_CONTRACT
wrong-security-major: VERSION_MISMATCH
reactive-servlet-sdk: WRONG_WEB_STACK
mvc-reactive-filter: WRONG_WEB_STACK
jackson-migration: REVIEW_JACKSON_MIGRATION
reactive-ok: REVIEW_EXTERNAL_CONTRACT
~~~

Explanation:

- A **generation-aligned** Boot 3/Security 6 or Boot 4/Security 7 pair does not prove transitive dependencies are safe; contract tests are still needed.
- A Servlet filter inside a reactive server belongs to the wrong server abstraction.
- A Reactive WebFilter inside a Servlet MVC server does not protect servlet requests.
- Boot 4/Security 7 with a serializer still depending on Jackson 2 requires reviewing data migration/config.
- The program intentionally performs only coarse classification; it does not determine patch-level compatibility, availability, annotations, or exact release trains.

In practice, gather inputs from Maven/Gradle `dependency:tree`, the Spring Boot BOM, security filter chains, IdP contracts, and release notes, **not merely from a major-version check**.

## 22. Post-Upgrade and Post-Integration Test Matrix

| Scenario | Servlet | Reactive | External Libraries / Data |
|---|---|---|---|
| Anonymous hits protected endpoint. | Expected redirect/401 per entry point. | Expected 401/redirect per WebFilter config. | Gateway does not bypass. |
| Role USER calls ADMIN endpoint. | `403` or policy-defined denial. | Reactive authorization denial. | SDK does not invent admin authorities. |
| Right/wrong password. | Real provider/PasswordEncoder executes. | Real reactive manager/user store executes. | LDAP/IdP timeouts, disabled status. |
| Valid Bearer JWT. | Servlet JwtDecoder/claims converter. | ReactiveJwtDecoder/converter. | JWKS/kid rotation, issuers. |
| JWT invalid `aud`/`iss`/`exp`/signature. | Rejected. | Rejected. | Not bypassed by external decoder. |
| OAuth2 Login callback/state/nonce. | Session request repository and OIDC login. | Reactive login flow. | IdP redirect URI, client auth, PKCE. |
| Incomplete MFA. | No elevated permissions. | Equivalent reactive policy. | MFA SDK proves assurance, challenge expiry. |
| Logout and session revocation. | Servlet session store invalidated. | WebSession invalidated. | Redis/IdP grants revoked in proper scope. |
| Missing/invalid CSRF on state-changing cookie POST. | Blocked. | Blocked. | Gateway does not strip headers/protections. |
| Multiple chains + custom matchers. | Exact chain per `@Order`. | Exact WebFilterChain per matcher. | SDK filter in right chain/order. |
| Cross-tenant access. | Denied. | Denied. | Trusted issuer/tenant mapping. |
| Spoofed reverse-proxy headers. | Host/scheme/IP not spoofable. | Equivalent. | Gateway sanitizes headers. |
| Session created on prior version. | Read or force logout per migration plan. | Read or planned re-auth. | Jackson 3 serializer/Redis key compatibility. |
| Authorization Server persisted grants. | Client/server interaction succeeds. | If server supports this stack. | Jackson 2→3, token revocation, JWK. |
| `@WithMockUser` test fixture. | Only proves mock authorization. | Only proves mock auth context. | Matching security-test version/starter. |
| Blue/green upgrade. | Old/new nodes permit no bypass. | Old/new nodes leak no context. | Token/session/Redis schema and rollback. |

**Categorize regressions clearly:** startup/classpath, filter configuration, authentication, authorization, session/serialization, external protocols, observability. A build that compiles yet lacks negative authorization tests **is not ready** to approve migration.

### Why Are Contract Tests with the IdP Also Required?

An OIDC client can pass tests with a mock `OAuth2AuthenticationToken`, yet fail in production callbacks due to redirect URIs, issuer metadata, client secrets, JWK `kid`, or `SameSite` cookies. Contract tests against an IdP sandbox (or faithful protocol simulation) catch these issues. Never let CI use real production credentials or send real user OTPs.

## 23. Audit Runbook When Changing Major Versions

### Phase 1 — Inventory

1. Record Boot, Spring Framework, Spring Security, Java, Servlet/Jakarta, Reactor/Netty, and Spring Cloud versions.
2. Identify Servlet vs. Reactive by **runtime** (not merely dependency names).
3. List all Spring Security modules and external auth providers/SDKs.
4. Locate extension points: filters, WebFilters, providers, converters, managers, security contexts, sessions, token serializers.
5. Document public URLs, issuer/audience, OAuth2 callback/redirect URIs, cookie policies, and Gateway trust boundaries.

### Phase 2 — Compatibility Review

1. Select the target Boot BOM per support policy/maintenance release.
2. Follow the corresponding Spring Security migration guide; if moving from 6.x to 7.x, upgrade to 6.5 and complete preparation steps first.
3. Cross-check Jakarta EE 11 / Servlet 6.1 and server dependencies when moving to Boot 4.
4. Compare Boot 4 starter/test-starter artifact names and Jackson 3 migration.
5. Cross-check the Spring Cloud release train and external SDK matrix.
6. Classify incompatible libraries: replace, isolate behind an adapter, upgrade, or defer upgrading the main app.
7. Prepare persisted session/grant/cache schema migrations and design rollback.

### Phase 3 — Implement

1. Keep Servlet code strictly in Servlet modules and reactive code strictly in WebFlux modules, or behind an explicit contract bridge.
2. Fix deprecated/removed APIs, Jakarta imports, and dependency coordinates.
3. Update custom authentication/authorization providers and error mapping.
4. Verify principal/context propagation and ensure nothing blocks the reactive event loop.
5. Audit JWT validators, IdP metadata, multi-tenant mappings, and token revocation.
6. Update test starters, security test helpers, mocks/fixtures, and negative tests.

### Phase 4 — Verify & Deploy

1. Run dependency convergence, SBOM/CVE scans, unit tests, MockMvc/WebTestClient integration tests, and external contract tests.
2. Test live through the public proxy with TLS/cookies/redirects; verify `Location`, `Set-Cookie`, and IdP callbacks.
3. Test blue/green and rollback while sessions/tokens coexist across versions.
4. Use canaries and metrics: `401`/`403`, redirect loops, auth failures, latency, WebFlux event-loop saturation, and session deserialization errors.
5. Set rollback thresholds if login success rates drop or any authorization bypass appears.
6. Post-deploy, inspect application logs to ensure no tokens, passwords, OTPs, cookies, or sensitive claims leak.

**Never treat a security major version upgrade as a place to experiment randomly with every integration at once.** Break migration into verifiable steps and maintain rollback mechanisms compatible with live persisted data.

## 24. Common Reasoning Mistakes

**Mistake 1 — “Having WebClient means the app is WebFlux.”** False; a Servlet app can use WebClient. The runtime web application type and filter/security context are what decide.

**Mistake 2 — “`SecurityFilterChain` protects reactive requests too.”** False in WebFlux; use `SecurityWebFilterChain`/`ServerHttpSecurity`.

**Mistake 3 — “`SecurityContextHolder` always holds the right principal in Reactor.”** False; reactive requires Reactor Context and proper context propagation.

**Mistake 4 — “Boot manages versions, so external SDKs must be compatible.”** The BOM manages many artifacts, yet does not prove a proprietary adapter supports Security 7/Jakarta 11.

**Mistake 5 — “Adding `oauth2Login` automatically validates API JWTs.”** False; resource servers have a distinct role and configuration from OAuth2 clients.

**Mistake 6 — “Being able to Base64-decode a JWT payload means the token is valid.”** False; you must verify signatures and policy claims.

**Mistake 7 — “Passing mock JWT tests proves the production JWT verifier is safe.”** False; `jwt()`/`mockJwt()` construct test authentications.

**Mistake 8 — “Changing `javax.servlet` to `jakarta.servlet` finishes migration.”** Not enough; runtime containers, frameworks, filter registration, Jakarta APIs, and dependencies must also align.

**Mistake 9 — “Boot 4 only changes the web starter version.”** No; Boot 4 modular starters/test starters, Jackson 3, and Servlet 6.1 have substantial impact.

**Mistake 10 — “Spring Session Redis sharing a keyspace can read contexts across two major versions.”** Not guaranteed; test serialization and rolling upgrades.

**Mistake 11 — “The proxy authenticated the caller, so the backend can trust any `X-Forwarded-User`.”** False; strip inbound headers, lock down backend access, and define a strict trust contract.

**Mistake 12 — “Reactor event loops can run blocking LDAP/JDBC naturally.”** False; evaluate throughput and bounded scheduling, never blocking the event loop.

**Mistake 13 — “A provider bean exists, so every security chain will use it.”** Not necessarily; manager/chain-local wiring governs it.

**Mistake 14 — “Bumping each Security module individually to the latest patch is safe.”** False; keep a unified managed version set.

## 25. Final Checklist for Implementers

- [ ] Identified the **runtime server stack** from real config: Servlet MVC vs. WebFlux.
- [ ] Inventoried Boot, Security, Framework, Java, Jakarta/Servlet, Reactor/Netty, Cloud, and third-party dependencies.
- [ ] Using a compatible BOM/release train without mixing Security major versions.
- [ ] Read the 6.5→7.x migration guide if upgrading to Security 7, including deprecations and Jackson 3.
- [ ] When moving to Boot 4, audited Servlet 6.1/Jakarta EE 11, starter/test-starter names, and embedded containers.
- [ ] Servlet configs use `HttpSecurity`/`SecurityFilterChain`; reactive configs use `ServerHttpSecurity`/`SecurityWebFilterChain`.
- [ ] Never reading principals from Servlet ThreadLocal inside reactive flows lacking a context bridge.
- [ ] Custom filters/WebFilters, AuthenticationManagers/providers, and request matchers sit on the right chains.
- [ ] JWT/OIDC/SAML/LDAP/WebAuthn modules audited by stack and version, not library name alone.
- [ ] OAuth2 Client, Resource Server, and Authorization Server roles separated and configured individually.
- [ ] IdP discovery/issuer/audience/signatures, callback URIs, and state/nonce/PKCE tested against reality.
- [ ] Spring Session serialization and rolling upgrade/rollback verified.
- [ ] Gateway/proxy trust, token relay, headers, and CSRF/CORS/session boundaries introduce no bypasses.
- [ ] `spring-security-test`/mock helpers treated solely as auth mocks; integration tests verify real credential checks.
- [ ] External SDKs documented with support matrix, release dates, CVEs, bytecode/Jakarta/Jackson alignment, and contract tests.
- [ ] Full coverage of positive/negative, cross-tenant, disabled account, expired token, revoked session, and missing factor cases.
- [ ] Logs exclude raw tokens/passwords/OTPs/cookies; metrics, canary checks, and rollback thresholds are defined.

## 26. Summary

Auditing Spring Security versions **is more than checking a version number**. You must verify three layers:

1. **Stack contract:** Servlet filters/`HttpSecurity`/`SecurityFilterChain` differ from Reactive WebFilters/`ServerHttpSecurity`/`SecurityWebFilterChain`, particularly around security context, sessions, and blocking I/O.
2. **Version contract:** the Spring Boot BOM selects a compatible Framework/Security/Jakarta/Reactor/Jackson set; Spring Security 6.5 is the recommended preparation step before Security 7, and Boot 4 brings major shifts in Jakarta EE 11, Servlet 6.1, Jackson 3, and modular starters/test infrastructure.
3. **Integration contract:** OAuth2 clients, resource servers, authorization servers, SAML2, LDAP, WebAuthn, Spring Session, Gateway, and external SDKs must officially support **your exact runtime and major version**, and pass integration and negative security tests.

A secure system is one with **evidence** at every authentication boundary: tokens are verified, providers run in the right chain, principals/contexts never leak across requests, roles/tenants/assurance are enforced at resources, persisted sessions/grants stay readable across migrations, and rollbacks are planned. Never turn a compatibility error into an excuse to weaken security.

## Official References

- [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/): preparation recommendations in Security 6.5, migration, and Jackson 3.
- [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): features, removals, and module changes.
- [Spring Security — Project Modules and Dependencies](https://docs.spring.io/spring-security/reference/modules.html): Core, Web, Config, LDAP, OAuth2 Client/JOSE/Resource Server, Test.
- [Spring Security — Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `HttpSecurity`, `SecurityFilterChain`, and multiple chains.
- [Spring Security — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`, and multiple chains.
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): reactive authentication architecture.
- [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoders, issuers, validators, and bearer token processing.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): reactive decoder/resource server.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc security integration.
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): WebTestClient security integration.
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): Servlet/reactive auto-configuration and customization.
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): inspecting BOM-managed versions.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters/test starters, Servlet baseline, breaking changes.
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java/Framework/Servlet container baselines.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): Jakarta EE 11, Java baseline, Jackson 3, and core changes.
- [Spring Cloud — Release Trains](https://spring.io/projects/spring-cloud): aligning Cloud trains with Boot releases.
- [Spring Session — Reference](https://docs.spring.io/spring-session/reference/): session stores, Servlet/reactive integration, and persistence.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication, anti-enumeration, and security policy implications.
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT validation and common pitfalls.
