# Customizing ReactiveOAuth2UserService and Mapping Claims to Authorities in Spring Security Reactive

## 1. Objective

In a **Spring WebFlux** application, users can sign in through an enterprise identity system using **OAuth2 Login/OpenID Connect (OIDC)**. The IdP provides identity and attributes such as `sub`, `email`, `groups`, or a custom claim `app_roles`. However, Spring Security cannot automatically infer that a string `"admin"` inside a custom claim corresponds to your application's `ROLE_ADMIN`. You need to **map trusted identity data into GrantedAuthority instances** before Spring Security makes authorization decisions.

This lesson explains how to choose and customize `ReactiveOAuth2UserService` in **Spring Security reactive**, preserving the framework's OIDC verification while producing controlled authorities. You will:

1. Distinguish OAuth2 Login, OIDC Login, and OAuth2 Resource Server JWT.
2. Understand the `ReactiveOAuth2UserService<R,U>.loadUser(...)` contract and the roles of `DefaultReactiveOAuth2UserService` and `OidcReactiveOAuth2UserService`.
3. Choose between `GrantedAuthoritiesMapper` and a custom user service depending on whether reactive I/O is needed.
4. Map the `app_roles` claim from an **ID Token issued by a trusted IdP** through an allowlist into `ROLE_USER`, `ROLE_ADMIN`, and `REPORT_VIEW`.
5. Preserve `OidcIdToken`, `OidcUserInfo`, the principal identity, and default authorities when constructing `DefaultOidcUser`.
6. Build a Spring Boot 4.1.x/Java 17+ application with WebFlux OAuth2 Login where roles are actually enforced by `hasRole` and `hasAuthority`.
7. Run a plain Java 17 program to test the mapping **without an IdP**, then run end-to-end login once a real IdP is provisioned.
8. Test missing/wrong claims, unknown roles, multiple issuers, post-login role changes, callbacks, and sessions.

**Security mindset:** roles must never come from request headers, query parameters, or client-editable fields. Privileged roles must come from a **source whose issuer/tenant/client has been verified and that has an explicit semantic contract**.

## 2. OAuth2/OIDC Login Flow and User Service Hook Point

~~~text
Browser                         Spring WebFlux                          IdP
   |                                 |                                    |
   | GET /reports                    |                                    |
   |-------------------------------->|                                    |
   | anonymous -> redirect login     |                                    |
   |<--------------------------------|                                    |
   | GET /oauth2/authorization/corp  |                                    |
   |-------------------------------->|  Authorization Request + state     |
   |                                 |----------------------------------->|
   |                                 |           IdP authenticates user   |
   |                                 |<-----------------------------------|
   | GET /login/oauth2/code/corp?... |                                    |
   |-------------------------------->|  Exchange code for tokens          |
   |                                 |----------------------------------->|
   |                                 |<-- access token / ID Token --------|
   |                                 | OIDC token validation              |
   |                                 | OidcReactiveOAuth2UserService      |
   |                                 | custom role mapping                |
   |                                 | OAuth2AuthenticationToken          |
   |                                 | WebSession SecurityContext         |
   | GET /reports + session cookie   |                                    |
   |-------------------------------->| hasAuthority("REPORT_VIEW")        |
   |<--------------------------------| 200 or 403                         |
~~~

This is a conceptual diagram, not a replacement for a protocol trace. Spring Security also handles `state`, redirect URIs, nonces, PKCE when applicable, token exchange, UserInfo, and validation. Never manually parse an ID Token received via the browser or write a callback controller just to map roles.

### 2.1. Easily Confused Components

| Concept | Role |
| --- | --- |
| `OAuth2AccessToken` | Access token issued to the client to call protected resources; **not automatically a role** |
| `OidcIdToken` | JWT containing user authentication info/claims, verified by the OIDC client |
| `OidcUserInfo` | Claims fetched from the protected UserInfo endpoint; may be absent |
| `OAuth2User` | OAuth2 principal with attributes/authorities |
| `OidcUser` | `OAuth2User` with OIDC ID Token/UserInfo added |
| `GrantedAuthority` | Authority used by Spring Security policies, e.g., `ROLE_ADMIN` |
| `OAuth2AuthenticationToken` | Authentication of OAuth2 Login holding final authorities |
| `JwtAuthenticationToken` | Authentication of a **Resource Server** after validating a Bearer JWT; a different mechanism |

**Crucial distinction:** an API application that only receives `Authorization: Bearer <token>` normally uses `oauth2ResourceServer().jwt(...)` and a JWT authorities converter. `ReactiveOAuth2UserService` for **OAuth2 Client Login** is not automatically invoked when a resource server validates an API access token.

### 2.2. Role of AuthorizationManager

After `OAuth2AuthenticationToken` is created, the authorization layer in `SecurityWebFilterChain` or method security checks authorities. For example, `hasRole("ADMIN")` checks `ROLE_ADMIN` per the default role prefix; `hasAuthority("REPORT_VIEW")` requires the exact authority `REPORT_VIEW`. Mapping claims into authorities **does not** modify IdP data or token contents.

## 3. ReactiveOAuth2UserService: Contract and Delegation

Javadoc defines the interface:

~~~java
@FunctionalInterface
public interface ReactiveOAuth2UserService<
        R extends OAuth2UserRequest, U extends OAuth2User> {

    Mono<U> loadUser(R userRequest)
            throws OAuth2AuthenticationException;
}
~~~

This is a **condensed signature** for explanation, not code you declare yourself. `R` holds client registration details and the access token; `U` is the OAuth2/OIDC principal. Returning `Mono<U>` allows calling UserInfo or a supplementary API with `WebClient` without blocking the event loop.

| Login Type | UserService Type | Spring Security Delegate |
| --- | --- | --- |
| **Non-OIDC** OAuth2 provider | `ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>` | `DefaultReactiveOAuth2UserService` |
| OIDC provider with `openid` scope | `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` | `OidcReactiveOAuth2UserService` |

`DefaultReactiveOAuth2UserService` uses the access token to call UserInfo via `WebClient`. For non-OIDC providers, you generally must specify `user-name-attribute` from the UserInfo response. `OidcReactiveOAuth2UserService` integrates the OIDC ID Token and UserInfo; `OidcUser.getUserInfo()` may return `null`. Never replace an OIDC user service with a generic OAuth2 user service and lose ID Token/principal semantics.

### 3.1. The Right Extension Point in Spring Security 7.1

In **Spring Security 7.1 WebFlux**, you can declare a **`@Bean ReactiveOAuth2UserService<OidcUserRequest, OidcUser>`** and keep `.oauth2Login(Customizer.withDefaults())`. Spring Security looks up the implementation by generic type.

A common mistake is copying a Servlet example:

~~~java
// Only to identify the API difference; DO NOT use for WebFlux:
http.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(userInfo ->
                userInfo.oidcUserService(oidcUserService)));
~~~

In the reactive `ServerHttpSecurity.OAuth2LoginSpec` Javadoc for version 7.1, **there is no `userInfoEndpoint(...)` method** like in the Servlet DSL. For WebFlux, use a user-service bean or `GrantedAuthoritiesMapper` per reactive documentation. In Spring Security 6.5 projects, also verify the exact API available rather than pasting Servlet snippets.

### 3.2. When Is loadUser Called?

It runs during the OAuth2/OIDC Login process, **not on every HTTP request** from a user who already has a session. Post-login Authentication is typically stored in `WebSession`. Therefore, **role changes at the IdP after login** will not automatically reflect in the current session's authorities.

### 3.3. Mono and Error Handling

Inside `loadUser`, use `delegate.loadUser(request).map(...)` or `flatMap(...)` when extra I/O is needed. Never call `block()` on the Netty event loop, and never call `subscribe()` and return a principal before the roles API completes. When the IdP/roles API fails, **never fall back to admin**; define a clear fail-closed policy or reject login.

## 4. Claims, Scopes, and Roles Are Not Synonymous

OIDC has common identity claims like `iss`, `aud`, `sub`, `name`, `email`, and `email_verified`. **There is no universal role claim required from every provider.** An enterprise IdP might emit:

~~~json
{
  "iss": "https://login.corp.example/realms/employees",
  "aud": "web-dashboard",
  "sub": "employee-123",
  "email": "reader@corp.example",
  "app_roles": ["viewer", "report_reader"]
}
~~~

This is an **example payload**, not a real token. `app_roles` must be explicitly configured by the IdP team and emitted in the **ID Token** if your code reads the ID Token. Some providers place groups only in UserInfo or a protected roles API. If using a nested claim like `realm_access.roles`, you cannot read it directly via `claims.get("app_roles")`.

### 4.1. Comparing Authorities

| Data | Example Policy | Notes |
| --- | --- | --- |
| `ROLE_USER` | `hasRole("USER")` | Role rule; default `ROLE_` prefix |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Application admin role |
| `REPORT_VIEW` | `hasAuthority("REPORT_VIEW")` | App-specific authority |
| `SCOPE_profile` | `hasAuthority("SCOPE_profile")` | Authority from OAuth2 scope, if present |
| `OIDC_USER` | Indicates OIDC principal type | **Not admin** |
| `OAUTH2_USER` | Indicates OAuth2 principal type | **Not admin** |
| `SCOPE_openid` | An OAuth2/OIDC scope | **Does not grant roles** |

Being granted the `openid profile email` scopes does not mean the user can act as admin, view reports, or manage users. Application permissions require separate mapping.

### 4.2. Allowlist-Based Mapping

This lesson uses a specific mapping table:

| `app_roles` Value | GrantedAuthority |
| --- | --- |
| `"viewer"` | `ROLE_USER` |
| `"admin"` | `ROLE_ADMIN` |
| `"report_reader"` | `REPORT_VIEW` |
| `"super_admin"` or undefined role | Grant no authority |
| Missing/null/wrong-type claim | Grant no app authority |
| Item is a number, object, or boolean | Ignore wrong-type item |

Never blindly turn every string into `"ROLE_" + claim`. For strict requirements, an unexpected role format might **fail the login** rather than being ignored; this lesson chooses the model of **granting no sensitive privilege** on invalid data. Either way, **never** default to a higher privilege when the role source errors out.

## 5. Trust Chain Before Granting Authorities

A claim in an ID Token is suitable for role decisions only if:

1. The client registration points to an **IdP authorized to assert application roles**.
2. Spring Security has verified the ID Token: signature, issuer, audience, expiry, and appropriate OIDC checks.
3. The role claim is **assigned server-side by the IdP**, not a user-editable profile field.
4. Roles are scoped to the **right client/tenant**; an IdP may issue realm roles for other apps—never mix namespaces.
5. Mapping passes strictly through a reviewed allowlist, never inferring privileges from similar-looking group names.
6. Internal accounts are linked using a durable key like `issuer + subject`, not email alone.
7. The system has a strategy for revoking privileges after a user has logged in.

### 5.1. Vulnerability-Prone Anti-Patterns

~~~java
// Wrong: trusting a client-sent header.
String role = exchange.getRequest()
        .getHeaders().getFirst("X-Role");
new SimpleGrantedAuthority("ROLE_" + role);

// Wrong: trusting any string in the token as a safe app role.
String input = (String) claims.get("role");
new SimpleGrantedAuthority(
        "ROLE_" + input.toUpperCase());

// Wrong: email domain is not sufficient to grant admin.
if (email.endsWith("@corp.example")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

These are **dangerous snippets to recognize**, never to use in real programs. The ID Token signature protects claim integrity, but **does not by itself guarantee the semantics** that a claim represents an admin privilege in your app.

## 6. Choosing GrantedAuthoritiesMapper vs. a User Service

| Criterion | `GrantedAuthoritiesMapper` | `ReactiveOAuth2UserService` |
| --- | --- | --- |
| Only needs to read existing claims | Suitable | Suitable |
| Needs access to `OidcIdToken`/`OidcUserInfo` | Via `OidcUserAuthority` | Via delegate's `OidcUser` |
| Needs HTTP call to protected roles API | Unsuitable (synchronous mapper) | Suitable via reactive `WebClient` |
| Needs to change principal name/attributes | Not its primary purpose | Can rebuild principal |
| Wiring into WebFlux | `GrantedAuthoritiesMapper` bean | `ReactiveOAuth2UserService<...>` bean |
| Easy to unit-test pure policy | Yes | Yes; extract pure mapper |
| Risk | Dropping default authorities | Losing default ID Token/UserInfo/flow handling |

**If you only need to transform already-present claims into authorities, `GrantedAuthoritiesMapper` is usually simpler.** If you need custom delegation, extra data fetched via access token, or principal transformation, a user service is more suitable.

### 6.1. GrantedAuthoritiesMapper Example

~~~java
@Bean
GrantedAuthoritiesMapper authoritiesMapper() {
    return incoming -> {
        Set<GrantedAuthority> result =
                new LinkedHashSet<>(incoming);

        for (GrantedAuthority authority : incoming) {
            if (authority instanceof OidcUserAuthority oidc) {
                Object claim = oidc.getIdToken()
                        .getClaims().get("app_roles");
                for (String granted :
                        ClaimRolePolicy.mapProviderRoles(claim)) {
                    result.add(new SimpleGrantedAuthority(granted));
                }
            }
        }
        return result;
    };
}
~~~

This is a **method snippet** inside a Spring configuration; it requires importing `GrantedAuthoritiesMapper`, `OidcUserAuthority`, `GrantedAuthority`, `SimpleGrantedAuthority`, `Set`, and `LinkedHashSet`. It uses the utility from section 7.

**Note:** this mapper does not have direct access to `ClientRegistration` to inspect `registrationId` like a user service does. If the app supports multiple IdPs, this **is not enough** to decide which issuer's claims are trusted. Design a provider/issuer-aware policy or use a custom user service with full request context.

In the main integration example below, we **do not register this mapper bean**, avoiding double-mapping and confusion over final authorities.

## 7. WebFlux Java 17+ Project with Custom Role Claims

The application uses Spring Boot 4.1.2, **Spring Reactive Web**, **Spring Security**, and **OAuth2 Client**. There are two testing parts:

- **Pure Java role mapping** runs standalone with `javac`, requiring no network/IdP.
- **Spring WebFlux OAuth2/OIDC Login** completes end-to-end login only when you supply a real IdP/`ClientRegistration`.

### 7.1. pom.xml

Create a Maven project, group `com.example`, artifact `reactive-oidc-roles`, Java 17+.

**Spring Boot 4** renamed the OAuth2 Client starter to `spring-boot-starter-security-oauth2-client`; the older name `spring-boot-starter-oauth2-client` is kept for compatibility but renamed/deprecated. Complete `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-oidc-roles</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
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

Let the Spring Boot BOM manage compatible versions of Spring Security, Framework, and Reactor. Do not add Servlet's `spring-boot-starter-web`. `oauth2-client` differs from `oauth2-resource-server`; the latter is for Bearer/JWT APIs.

### 7.2. application.properties

Create `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.client.registration.corp.provider=corp
spring.security.oauth2.client.registration.corp.client-id=${CORP_CLIENT_ID}
spring.security.oauth2.client.registration.corp.client-secret=${CORP_CLIENT_SECRET}
spring.security.oauth2.client.registration.corp.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.corp.scope=openid,profile,email
spring.security.oauth2.client.registration.corp.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}

spring.security.oauth2.client.provider.corp.issuer-uri=${CORP_OIDC_ISSUER_URI}
~~~

When the lesson is saved, the `${...}` placeholders in the snippet above use **Spring Property Placeholder `$...`** syntax; the application uses environment variables `CORP_CLIENT_ID`, `CORP_CLIENT_SECRET`, and `CORP_OIDC_ISSUER_URI`.

**To run real login**, provision an IdP supporting OIDC discovery over HTTPS, obtain Client ID/Secret, and register callback `http://localhost:8080/login/oauth2/code/corp` for **local dev**. Production requires HTTPS and a real public redirect URI, never committing the client secret to Git. Spring Boot may query OIDC discovery on startup; an unreachable issuer causes startup/login failure, not a mapping bug.

**Important:** The IdP must be configured to **emit `app_roles` in the ID Token** for the `corp` client. This lesson does not assume a public provider emits that claim automatically.

### 7.3. ClaimRolePolicy.java — Runs Standalone with JDK 17

Create `src/main/java/com/example/oidcroles/ClaimRolePolicy.java`:

~~~java
package com.example.oidcroles;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public final class ClaimRolePolicy {

    private ClaimRolePolicy() {
    }

    public static Set<String> mapProviderRoles(Object claim) {
        if (!(claim instanceof Collection<?> values)) {
            return Set.of();
        }

        Set<String> result = new LinkedHashSet<>();
        for (Object item : values) {
            if (!(item instanceof String role)) {
                continue;
            }
            switch (role) {
                case "viewer" -> result.add("ROLE_USER");
                case "admin" -> result.add("ROLE_ADMIN");
                case "report_reader" -> result.add("REPORT_VIEW");
                default -> {
                    // Unknown role cannot create app privileges.
                }
            }
        }
        return Set.copyOf(result);
    }

    public static void main(String[] args) {
        Set<String> allowed = mapProviderRoles(List.of(
                "viewer", "admin", "report_reader", "super_admin"));

        System.out.println("allowed=" +
                String.join(",", new TreeSet<>(allowed)));

        System.out.println("unknown=" +
                mapProviderRoles(List.of("super_admin")).size());

        System.out.println("wrong_type=" +
                mapProviderRoles("admin").size());
    }
}
~~~

This program **uses only the Java standard library**, needing neither Spring nor an IdP. Filename, package, and class name match. It:

- Processes only collection-typed claims; a scalar `"admin"` claim is not mapped.
- Accepts only strings in the allowlist; `super_admin` is not mapped.
- Never prepends `ROLE_` to arbitrary user input strings.
- Skips wrong-type items without escalating privileges.
- Returns an immutable `Set`; ordering is stabilized for printing via `TreeSet`.

Run with JDK 17 from the project directory:

~~~bash
mkdir -p out
javac -d out src/main/java/com/example/oidcroles/ClaimRolePolicy.java
java -cp out com.example.oidcroles.ClaimRolePolicy
~~~

Windows PowerShell: create the directory with `New-Item -ItemType Directory -Force out`, then run `javac` and `java` identically. **Deterministic stdout per the code**:

~~~text
allowed=REPORT_VIEW,ROLE_ADMIN,ROLE_USER
unknown=0
wrong_type=0
~~~

This is an **allowlist policy test**, not signature verification of a real ID Token.

### 7.4. OidcRolesApplication.java — WebFlux OAuth2 Login

Create `src/main/java/com/example/oidcroles/OidcRolesApplication.java`:

~~~java
package com.example.oidcroles;

import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcReactiveOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class OidcRolesApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcRolesApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .pathMatchers("/reports")
                                .hasAuthority("REPORT_VIEW")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @Bean
    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
            oidcUserService() {

        OidcReactiveOAuth2UserService delegate =
                new OidcReactiveOAuth2UserService();

        return request -> delegate.loadUser(request).map(user -> {
            Set<GrantedAuthority> mapped =
                    new LinkedHashSet<>(user.getAuthorities());

            // Only this trusted client registration grants app roles.
            if ("corp".equals(
                    request.getClientRegistration().getRegistrationId())) {

                Object claim = user.getIdToken().getClaims()
                        .get("app_roles");

                for (String role :
                        ClaimRolePolicy.mapProviderRoles(claim)) {
                    mapped.add(new SimpleGrantedAuthority(role));
                }
            }

            // Preserve ID Token, UserInfo, default authorities.
            // Default name uses the OIDC subject (sub).
            return new DefaultOidcUser(
                    mapped, user.getIdToken(), user.getUserInfo());
        });
    }

    @RestController
    static class DemoController {

        @GetMapping(value = "/",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> index() {
            return Mono.just(
                    "Open /oauth2/authorization/corp to sign in");
        }

        @GetMapping("/me")
        Mono<Map<String, Object>> me(
                @AuthenticationPrincipal OidcUser user) {
            return Mono.just(Map.of(
                    "subject", user.getSubject(),
                    "authorities", user.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList()));
        }

        @GetMapping(value = "/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> admin() {
            return Mono.just("ADMIN_OK");
        }

        @GetMapping(value = "/reports",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> reports() {
            return Mono.just("REPORT_OK");
        }
    }
}
~~~

**Design decisions explained:**

1. `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` is registered as a bean, fitting Spring Security WebFlux 7.1.
2. The standard `OidcReactiveOAuth2UserService` still handles UserInfo/OIDC logic; default validation is preserved.
3. `delegate.loadUser(...).map(...)` is reactive, never calling `block()` or `subscribe()`.
4. `registrationId == "corp"` is the minimum guard preventing untrusted social logins from granting app roles. In multi-issuer production setups, also verify claim/tenant provenance per contract and validated issuer.
5. Claims are read from the **ID Token**: `user.getIdToken().getClaims().get("app_roles")`. If the IdP emits roles only in UserInfo, this code will **not** see them; pick the right source and verify the schema.
6. `new LinkedHashSet<>(user.getAuthorities())` keeps default authorities from the delegate, such as `OIDC_USER` and `SCOPE_*`, then adds mapped authorities.
7. `DefaultOidcUser` is constructed with the same ID Token/UserInfo; the 3-argument constructor uses `sub` as the principal name, not email as an identifier key.
8. `/admin` requires `ROLE_ADMIN` via `hasRole("ADMIN")`; `/reports` requires `REPORT_VIEW` verbatim.
9. `/me` returns only `subject` and authority names for easy testing. **Never return the ID Token, access token, or full UserInfo** through a debug API.
10. `httpBasic(disable)`/`formLogin(disable)` remove unused mechanisms from the sample while `oauth2Login` handles OAuth2 authorization/callbacks.
11. Never disable CSRF for a cookie/session app; this demo only exposes GET.
12. If multiple `SecurityWebFilterChain` beans exist, the chain handling OAuth2 must cover `/oauth2/authorization/**` and `/login/oauth2/code/**`.

**If the app needs a custom name attribute:** for OIDC, use the `DefaultOidcUser(..., nameAttributeKey)` constructor only when that field is guaranteed present per the IdP contract. `sub` combined with `iss` is generally more trustworthy than email/username for identity linking. Never switch `getName()` to email and assume every IdP with the same email represents the same user.

### 7.5. The IdP Must Emit the Exact Claim

For a user to log in and receive `REPORT_VIEW`, the IdP must emit the **exact claim** in the ID Token for the trusted client, e.g.:

~~~json
{
  "iss": "https://login.corp.example/realms/employees",
  "sub": "employee-123",
  "aud": "web-dashboard",
  "app_roles": ["viewer", "report_reader"]
}
~~~

If login succeeds without `app_roles`, the user can still be authenticated, but **no app roles are granted from the allowlist**. This is fail-closed behavior for protected routes and should not be “patched” by granting `ROLE_ADMIN` by default.

### 7.6. Running OAuth2 Login with a Real IdP

First run the pure Java test as in section 7.3. Once the IdP is configured:

~~~bash
export CORP_CLIENT_ID='web-dashboard'
export CORP_CLIENT_SECRET='secret-issued-by-your-idp'
export CORP_OIDC_ISSUER_URI='https://login.corp.example/realms/employees'
./mvnw clean package
./mvnw spring-boot:run
~~~

The values above are **illustrative only**. Replace them with real credentials and your real issuer; never commit secrets. On Windows PowerShell, use `$env:CORP_CLIENT_ID="..."` and the same for the other two variables, then `.\mvnw.cmd spring-boot:run`.

While running, you can inspect:

~~~bash
# Public page:
curl -i http://localhost:8080/

# Start Authorization Code flow (302 redirect to IdP):
curl -i http://localhost:8080/oauth2/authorization/corp

# Unauthenticated anonymous requests:
curl -i http://localhost:8080/me
curl -i http://localhost:8080/admin
~~~

`curl` cannot complete the browser login/callback at the IdP by itself. Use a browser with a test profile:

1. Open `http://localhost:8080/oauth2/authorization/corp` and complete login on the IdP.
2. Open `http://localhost:8080/me` to see the principal subject and authorities.
3. If the IdP issued `app_roles=["viewer","report_reader"]`, the user gets `ROLE_USER` and `REPORT_VIEW`; `GET /reports` succeeds with **200** `REPORT_OK`, and `GET /admin` gets **403**.
4. If the IdP issued `app_roles=["admin"]`, `GET /admin` succeeds with **200** `ADMIN_OK`.
5. If the claim is missing or wrong-typed, `/admin` and `/reports` are denied for the authenticated user; there is no admin fallback.
6. If the user is not logged in, private endpoints normally redirect to the login/OIDC flow rather than returning 403 for missing roles.

**Verification boundary:** the pure mapping code is runnable without an IdP. The end-to-end OAuth2 flow can only be tested once a valid IdP, client registration, and role claim mapper are in place. Never claim you ran login or verified real token signatures without that environment.

## 8. Non-OIDC OAuth2: DefaultReactiveOAuth2UserService

Providers without the `openid` scope/ID Token use the other service interface. In a Spring configuration for registration `legacy`, you can use:

~~~java
@Bean
ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
        oauth2UserService() {

    DefaultReactiveOAuth2UserService delegate =
            new DefaultReactiveOAuth2UserService();

    return request -> delegate.loadUser(request).map(user -> {
        Set<GrantedAuthority> mapped =
                new LinkedHashSet<>(user.getAuthorities());

        if ("legacy".equals(
                request.getClientRegistration().getRegistrationId())) {
            Object claim = user.getAttributes().get("app_roles");

            for (String role :
                    ClaimRolePolicy.mapProviderRoles(claim)) {
                mapped.add(new SimpleGrantedAuthority(role));
            }
        }

        String nameKey = request.getClientRegistration()
                .getProviderDetails().getUserInfoEndpoint()
                .getUserNameAttributeName();

        if (nameKey == null || nameKey.isBlank()) {
            throw new IllegalStateException(
                    "Configure user-name-attribute for the provider");
        }

        return new DefaultOAuth2User(
                mapped, user.getAttributes(), nameKey);
    });
}
~~~

**This is a method snippet, not a standalone Java file.** It requires importing `OAuth2UserRequest`, `OAuth2User`, `DefaultReactiveOAuth2UserService`, `DefaultOAuth2User`, `ReactiveOAuth2UserService`, `Set`, `LinkedHashSet`, `GrantedAuthority`, and `SimpleGrantedAuthority`, plus a real `legacy` registration.

- Non-OIDC OAuth2 receives UserInfo attributes and has no OIDC ID Token.
- `DefaultReactiveOAuth2UserService` calls UserInfo via `WebClient` (with the access token).
- `DefaultOAuth2User` needs `nameKey` pointing to a real attribute in UserInfo, e.g., `id` if the provider supplies `id`.
- UserInfo schemas can vary across providers; always check API docs before mapping.
- Never fabricate an `OidcUser` without a valid ID Token.

If a provider exposes groups only on a separate API, add an explicit reactive call rather than expecting `DefaultReactiveOAuth2UserService` to discover that endpoint on its own.

## 9. Fetching Roles from a Protected API with an Access Token

When roles are absent from both the ID Token and UserInfo and reside on an IdP API, a custom `ReactiveOAuth2UserService` can call that API with `WebClient` and the issued access token. Conceptual logic:

~~~java
// Snippet: rolesWebClient, RoleResponse, and addTrustedAuthorities
// are application components that must be defined per the provider API.
return delegate.loadUser(request)
        .flatMap(user -> rolesWebClient.get()
                .uri("/v1/my-roles")
                .headers(h -> h.setBearerAuth(
                        request.getAccessToken().getTokenValue()))
                .retrieve()
                .bodyToMono(RoleResponse.class)
                .timeout(Duration.ofSeconds(2))
                .map(roles -> addTrustedAuthorities(user, roles)));
~~~

This is **application pseudocode**, not a runnable standalone file: `RoleResponse` and `addTrustedAuthorities` must be implemented per the API contract. Do not drop this into the main example without a real roles API.

Principles:

- The endpoint must use HTTPS and a **fixed trusted base URL**; never accept arbitrary URLs from requests (SSRF).
- The access token must have a valid audience/scope for the roles API. **Never use an ID Token instead of an access token.**
- Configure timeouts, bounded retries, and clear 401/403/5xx error handling.
- Never log Bearer tokens, raw UserInfo, or responses containing PII.
- If the roles API is unavailable, **never grant admin**. Either fail login or log in with minimal privileges if policy permits.
- Use reactive I/O; avoid blocking JDBC or `RestTemplate` directly on the Netty event loop.
- Never write `Mono.just(blockingCall())`, because `blockingCall()` still executes eagerly before the `Mono` is constructed.

### 9.1. When Is a Custom User Service Unnecessary?

If you only need to map an already-available OIDC claim, a `GrantedAuthoritiesMapper` bean is simpler and easier to audit. When there is no I/O or principal transformation, avoid writing a lengthy user service just to add one `SimpleGrantedAuthority`.

## 10. Testing Role Mapping at Multiple Levels

### 10.1. Testing the Pure Policy

`ClaimRolePolicy.java` has a deterministic `main`; add JUnit assertions for these cases:

| Input Claim | Expected App Authorities |
| --- | --- |
| `["viewer"]` | `ROLE_USER` |
| `["admin"]` | `ROLE_ADMIN` |
| `["report_reader"]` | `REPORT_VIEW` |
| `["viewer","admin"]` | `ROLE_USER`, `ROLE_ADMIN` |
| `["super_admin"]` | None |
| `null` | None |
| `"admin"` (scalar) | None |
| `["ADMIN"]` | None |
| `[]` | None |
| Mixed list of Strings and numbers | Maps only allowlisted Strings |

JUnit snippet:

~~~java
@Test
void unknownRoleIsNotAdmin() {
    assertFalse(ClaimRolePolicy
            .mapProviderRoles(List.of("super_admin"))
            .contains("ROLE_ADMIN"));
}

@Test
void knownAdminMapsExactly() {
    assertEquals(Set.of("ROLE_ADMIN"),
            ClaimRolePolicy.mapProviderRoles(List.of("admin")));
}
~~~

This is a **test method snippet**, requiring JUnit 5 and static imports `assertFalse`, `assertEquals`. `List.of(null)` is disallowed in Java; to test null items use a mutable `List` or `Arrays.asList`.

### 10.2. Testing the User Service with a Mocked Delegate

Extract mapping logic into a pure policy and inject a fake OIDC delegate in tests to assert:

- `registrationId="corp"` + trusted ID Token `app_roles=["admin"]` → grants `ROLE_ADMIN`.
- Another registration (social/unknown) → grants no app roles from identically named claims.
- Missing claim, invalid type, duplicate values → creates no undefined privileged authorities.
- `OIDC_USER`/`SCOPE_*` and `getIdToken()/getUserInfo()` are preserved.
- Delegate errors → user service does not turn an error into an admin login.
- `getName()` stays stable on `sub`, never using email as a linking key unless designed to.

A mocked delegate tests **mapping and reactive composition**, not JWT signatures. Testing the OIDC protocol requires a real IdP or a compliant mock OIDC provider.

### 10.3. WebTestClient: HTTP Authorization

Spring Security Test reactive provides `mockOidcLogin()` to simulate post-login OAuth2 authentication. Example:

~~~java
// Snippet inside an integration test with an appropriate WebTestClient:
webTestClient.mutateWith(
        mockOidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")))
        .get().uri("/admin")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(
        mockOidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_USER")))
        .get().uri("/admin")
        .exchange()
        .expectStatus().isForbidden();
~~~

This is a **test snippet**, not a complete class. It requires Spring Security Test reactive `SecurityMockServerConfigurers.mockOidcLogin`, `WebTestClient`, and a configured test runtime. `mockOidcLogin().authorities(...)` **assigns authorities directly**, meaning it **skips `ReactiveOAuth2UserService` and does not validate ID Token signatures**. Test the policy and user service separately, then run an E2E OIDC flow with an IdP to verify the entire system.

### 10.4. Test Matrix

| Case | Expected Result |
| --- | --- |
| Trusted `corp` with `app_roles=["admin"]` | Has `ROLE_ADMIN` |
| Trusted `corp` with `app_roles=["viewer","report_reader"]` | Has `ROLE_USER` and `REPORT_VIEW` |
| Unknown/uppercase role | Elevated role not added |
| Missing/wrong-type claim | App roles not added |
| Claim with non-String elements | No privileges granted from those elements |
| Social provider happens to have same `app_roles` field | `corp` policy not applied |
| Null UserInfo | ID Token kept, no NPE |
| Protected roles API returns 403 | Does not default to admin |
| OIDC ID Token invalid issuer/audience/signature | Login fails before authorization |
| Non-OIDC OAuth2 | Uses `DefaultReactiveOAuth2UserService` |
| API receiving only Bearer JWT | Uses resource server's JWT converter |
| Admin revoked from user while `WebSession` still open | Requires revoke/refresh/recheck |
| Multi-tenant with same email | Authorities not auto-merged |
| App behind proxy | Callback redirect URI and HTTPS are accurate |

## 11. Post-Login Privilege Lifecycle

One risk is a **role snapshot**. `ReactiveOAuth2UserService` is normally called at login time, while the user's `OAuth2AuthenticationToken` may remain stored in `WebSession`:

~~~text
10:00 IdP issues app_roles=["admin"]
10:00 user logs in -> ROLE_ADMIN in Authentication
10:05 IdP admin revokes admin role
10:06 browser still holds authenticated WebSession
10:06 app may still see old ROLE_ADMIN
      without session revocation, re-login, or dynamic authorization
~~~

To reduce privilege revocation lag:

- Cap session lifetimes and require re-authentication for sensitive actions.
- Build a workflow to revoke `WebSession` when accounts/roles change; support cluster/distributed stores.
- When OIDC back-channel logout from the IdP is available, integrate the appropriate component if supported by the provider; do not assume every role-change event triggers a logout.
- For high-risk actions, query a live policy service or database in `ReactiveAuthorizationManager` with an appropriate cache TTL.
- For Bearer JWT access tokens at a resource server, enforce dedicated expiry/revocation/introspection or token-version policies. **Invalidating an OAuth2 Login `WebSession` does not automatically invalidate already-issued JWTs.**

Do not confuse “correct mapping at login” with “real-time up-to-date permissions”. Those are two separate problems.

## 12. Common Mistakes

### 12.1. Copying Servlet DSL into WebFlux

`HttpSecurity.oauth2Login(...userInfoEndpoint(...))` is not part of WebFlux 7.1's `ServerHttpSecurity.OAuth2LoginSpec` API. Use a `ReactiveOAuth2UserService` or `GrantedAuthoritiesMapper` bean matching the reactive stack; never add Servlet filters to fix compile errors.

### 12.2. OIDC User Service Reading the Wrong Claim Source

The app reads `user.getIdToken().getClaims().get("app_roles")` while the IdP sends roles in UserInfo instead. Result: no app roles despite successful login. Verify the claim-location contract, IdP config, and schema before changing the mapper.

### 12.3. Keeping the Wrong Principal Type

With OIDC, do not construct a `DefaultOAuth2User` holding only attributes while discarding `OidcIdToken`. Preserve `OidcUser`, the ID Token, UserInfo (possibly null), and principal name via `DefaultOidcUser`.

### 12.4. Dropping Default Authorities

Building a new authorities list containing only `ROLE_ADMIN` can drop `OIDC_USER`, `SCOPE_*`, or provider-granted authorities. Copy `user.getAuthorities()` first and then append mapped roles.

### 12.5. ROLE_ADMIN Differs from SCOPE_ADMIN

`hasRole("ADMIN")` checks `ROLE_ADMIN`, not `ADMIN` or `SCOPE_ADMIN`. Inspect final Authentication authorities when debugging; never log full tokens.

### 12.6. Trusting Every Token Claim

Applying `"ROLE_" + string` to an arbitrary claim can accidentally map roles meant for another app or user-editable fields. Use an allowlist and enforce trusted issuer/client/tenant checks.

### 12.7. Using Email as a Cross-Provider Identity Key

Two IdPs can assert the same email or an email can change. Use `iss + sub` or a verified local account-linking key; `email_verified` does not grant admin.

### 12.8. Blocking HTTP Inside the Service

`ReactiveOAuth2UserService` executes within reactive login. Blocking I/O can stall the event loop. Use `WebClient`, timeouts, and non-escalating error handling.

### 12.9. Mapping the Same Claim in Both a Mapper Bean and a User Service

This can duplicate authorities and obscure where decisions happen and how to test them. Pick one primary mapping location and document responsibilities clearly, especially with multiple providers.

### 12.10. Testing Only mockOidcLogin and Concluding Mapping Works

Mock OIDC login injects a prebuilt Authentication and may bypass the user service entirely. Unit-test the claim policy/delegation and test real OIDC login or a mock provider with a token flow.

### 12.11. Using OAuth2 Login User Service to Handle Bearer JWT APIs

These are two different capabilities. Resource Server JWTs require a converter inside `oauth2ResourceServer().jwt(...)`; OAuth2 Login's user service does not run automatically when validating API JWTs.

### 12.12. Role Revoked, Yet Session Still Retains Access

Login is an event, not a per-request role check. Implement session revocation, reauthentication, or dynamic policy checks if required.

### 12.13. Exposing Tokens/Claims in Logs or Debug Endpoints

Never log ID Tokens, access tokens, refresh tokens, client secrets, or full UserInfo. The demo `/me` endpoint only shows subject and authority names; consider removing debug endpoints in production.

## 13. Production Checklist

1. Distinguish OAuth2 Login, OIDC Login, and Resource Server JWT.
2. Use proper Spring Security WebFlux reactive APIs, not Servlet DSL.
3. Align compatible Spring Boot/Security BOM dependencies and the OAuth2 Client starter for your Boot version.
4. Verify IdP issuer/discovery, client ID/secret, HTTPS redirect URI, and TLS.
5. Delegate custom services to the right base implementation without bypassing ID Token validation.
6. Ensure role claims are server-assigned by the IdP for the right client/tenant/issuer, never user-editable.
7. Enforce allowlist mapping, failing closed on missing/invalid/unknown roles.
8. Preserve existing authorities, ID Token, UserInfo, and principal identifier.
9. Distinguish `ROLE_*`, `SCOPE_*`, `OIDC_USER`, and app authorities.
10. Never grant roles from HTTP headers/queries/forms or email domains.
11. If calling a roles API, enforce HTTPS, fixed URL, proper audience/scope, timeouts, and fail-safe handling.
12. Keep CSRF, state/nonce, WebSession/cookie policies intact; never disable security just to make login work.
13. Verify callback URLs behind reverse proxies/ingress.
14. Unit-test pure mapping, user service, HTTP rules, and OIDC integration flows.
15. Have a strategy to re-evaluate/revoke authorities when users/roles/accounts change.
16. Never expose secrets/tokens/PII in debug responses, logs, or analytics.
17. Enforce strict isolation and account linking across multiple issuers/tenants.
18. Document the provider claim contract and review whenever the IdP schema changes.

## 14. Self-Check

**Q1.** Why doesn't `app_roles=["admin"]` automatically pass `hasRole("ADMIN")`?

**Answer:** Spring Security checks for `ROLE_ADMIN` in `Authentication.getAuthorities()`. Custom claims are not automatically converted into authorities; they must be mapped explicitly.

**Q2.** When should you use `GrantedAuthoritiesMapper`?

**Answer:** When you only need to read already-present claims/authorities and map them synchronously. If you need to call a roles API with an access token, use a reactive user service with `WebClient`.

**Q3.** Why delegate to `OidcReactiveOAuth2UserService` before mapping?

**Answer:** To preserve Spring Security's default OIDC UserInfo handling and principal construction; the custom mapper only adds authority logic.

**Q4.** `app_roles="admin"` is a scalar string; does the code grant admin?

**Answer:** No. The policy accepts only collections and Strings present in the allowlist.

**Q5.** Why copy `user.getAuthorities()` before adding roles?

**Answer:** To preserve `OIDC_USER`, `SCOPE_*`, and existing authorities without accidentally wiping out valid permissions/metadata.

**Q6.** A provider other than `corp` returns the same `app_roles=["admin"]` claim; does it grant admin?

**Answer:** Not in the sample: the `registrationId == "corp"` check must match. Production must also validate issuer/tenant and the IdP contract.

**Q7.** What does `mockOidcLogin().authorities(...)` prove?

**Answer:** It proves HTTP 200/403 rules for the given authorities; it **does not** prove claim mapping or token validation.

**Q8.** Why might a user retain admin after their role is revoked at the IdP?

**Answer:** `WebSession`/Authentication can hold a snapshot of authorities from login time. Session revocation, reauthentication, or dynamic authorization checks are needed.

**Q9.** Does `ReactiveOAuth2UserService` handle Bearer JWTs on a resource server?

**Answer:** Not automatically. A resource server uses a separate JWT authentication converter and authorization setup.

**Q10.** Can `email_verified=true` or an email domain be used to grant `ROLE_ADMIN` automatically?

**Answer:** No. A verified email is only contact/identification data; admin privileges require a separate, trusted, application-specific authorization source.

## 15. Official Documentation

- [Spring Security — Reactive OAuth2 Login: Advanced Configuration and Mapping Authorities](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html)
- [Spring Security — Reactive OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html)
- [Spring Security — Reactive OAuth2 Login Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Javadoc — ReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/ReactiveOAuth2UserService.html)
- [Javadoc — OidcReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcReactiveOAuth2UserService.html)
- [Javadoc — DefaultReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultReactiveOAuth2UserService.html)
- [Javadoc — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Javadoc — ServerHttpSecurity.OAuth2LoginSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html)
- [Spring Security — Reactive Testing OAuth2/OIDC](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Spring Boot 4.0 Migration Guide — Renamed OAuth2 Client Starter](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
