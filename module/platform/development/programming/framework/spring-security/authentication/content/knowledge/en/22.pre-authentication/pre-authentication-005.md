# Proxy Trust Boundaries and Preventing Client Header Spoofing (Spring Security Pre-authentication)

## 1. Objective and Important Warning

**Pre-authentication** is a model in which a system in front of the application (an identity-aware proxy, SSO gateway, authenticating reverse proxy, servlet container, etc.) has already verified the user. Spring Security receives the handed-off identity, maps it to an application account/permissions, and enforces authorization.

When passing identity via an HTTP header, **the header itself is not proof of authentication**. Any HTTP client can send a header identical to one produced by a proxy. Therefore:

> Trust an identity-bearing header only when you have ensured it was issued or overwritten by a proxy that authenticated the user, and the backend accepts traffic solely over that trusted path.

Spring Security explicitly notes that `RequestHeaderAuthenticationFilter` **does not authenticate users with passwords or tokens**; the filter simply reads the principal from a header. If a request reaches the backend carrying a forged header without passing through the trust barrier, the application may treat the sender as any user.

After this lesson, you should be able to explain and implement: trust boundaries at each hop; header spoofing vectors; proxy vs. backend responsibilities; Spring Security pre-auth configuration; defenses against direct backend access, duplicate/mismatched header names, and proxy-chain flaws; plus a test suite proving impersonation is prevented.

## 2. What Is a Trust Boundary?

A **trust boundary** is the boundary between where unverified external input may arrive and where data has been verified by a specific mechanism. For pre-auth headers, the boundary sits at **the point that performs authentication and re-issues the header**, typically an identity gateway or reverse proxy.

~~~text
          UNTRUSTED ZONE                      CONTROLLED ZONE
┌──────────────────────────┐      ┌──────────────────────────────┐
│ Browser, mobile, curl    │      │ Identity-aware proxy / SSO   │
│ Can send arbitrarily:    │      │ 1. Authenticate credentials  │
│ X-Verified-User: admin   ├─────>│ 2. Strip client headers      │
│ X-Verified-Roles: root   │ HTTPS│ 3. Write verified user       │
└──────────────────────────┘      └──────────────┬───────────────┘
                                                 │ Controlled internal path:
                                                 │ ACL + TLS/mTLS if possible
                                                 v
                                    ┌──────────────────────────────┐
                                    │ Spring Boot / Spring Security│
                                    │ Read X-Verified-User         │
                                    │ Load app's own permissions   │
                                    │ Check authorization          │
                                    └──────────────────────────────┘
~~~

**Division of responsibilities:**

| Component | Must Do | Must Never Assume |
|---|---|---|
| Client | Send credentials to gateway, use the application | Allowed to self-assert identity via `X-Verified-User` |
| Gateway/SSO proxy | Authenticate, strip forged headers, emit canonical header, block unauthenticated requests | Trust client-sent `X-Verified-User` |
| Network infrastructure | Restrict backend to accept connections only from approved gateways, encrypt and authenticate internal hops as required | Assume every machine in the VPC/Kubernetes cluster is trustworthy |
| Spring Security backend | Read identity **that traversed the gateway**, map user/authorities, authorize every request | Assume a header or `X-Forwarded-For` proves identity |
| Identity store | Determine account, status, and groups/permissions per policy | Trust a client-controlled `role=ADMIN` field |

### "Trusting the Proxy" Must Be Grounded

Trust is a **property of the entire path**, not a property of a header name. `X-Verified-User` on the Internet and the same header on a connection restricted to a trusted proxy share identical syntax yet carry completely different security meaning.

If the backend still exposes port `8080`, a user can bypass the gateway and send directly:

~~~http
GET /me HTTP/1.1
Host: backend.example.test:8080
X-Verified-User: alice
~~~

If Spring only runs a header-reading filter, that request can authenticate as `alice` even though the client never passed the gateway's login check. That is **authentication bypass / header spoofing**.

## 3. How Spring Security Pre-auth Works

On the Servlet stack, the common components are:

1. `RequestHeaderAuthenticationFilter` extracts the username from a request header (defaults to `SM_USER`, configurable to `X-Verified-User`).
2. The filter builds a `PreAuthenticatedAuthenticationToken` and sends it to `AuthenticationManager`.
3. `PreAuthenticatedAuthenticationProvider` receives the token and uses `AuthenticationUserDetailsService` (or `UserDetailsByNameServiceWrapper`) to load the application account, status, and permissions.
4. `SecurityContext` holds the `Authentication`, while `authorizeHttpRequests` decides whether the request may access the endpoint.

~~~text
Trusted header → RequestHeaderAuthenticationFilter
               → PreAuthenticatedAuthenticationToken
               → PreAuthenticatedAuthenticationProvider
               → UserDetails / GrantedAuthority
               → SecurityContext
               → AuthorizationFilter
~~~

**What does NOT happen:** Spring Security does not contact the gateway itself to verify whether the user really is `alice` when you only configure `RequestHeaderAuthenticationFilter`. Loading `UserDetails("alice")` does not verify who sent the header either. The application can confirm that a username exists, yet **cannot prove the HTTP sender is authorized to use that username**.

You must distinguish **authentication** (the gateway verifies identity) from **authorization** (Spring checks user/role/permission against the resource). These are two separate steps; the app must still enforce authorization independently.

## 4. Common Spoofing Vectors and Misconfigurations

### 4.1. Proxy Forwards Client Headers As-Is

Dangerous configuration example:

~~~nginx
# WRONG: proxies directly upstream without re-establishing identity.
location / {
    proxy_pass http://internal_app;
}
~~~

If the backend trusts `X-Verified-User`, requests from the Internet can supply that header and have it forwarded verbatim. **Merely adding `RequestHeaderAuthenticationFilter` provides zero protection.**

Another dangerous variant:

~~~nginx
# WRONG: takes "authenticated identity" directly from the client.
proxy_set_header X-Verified-User $http_x_verified_user;
~~~

The `$http_x_verified_user` variable is the header value from the client request; it does not prove the proxy authenticated it. The value must originate from the gateway's authentication result (`$remote_user` after successful NGINX Basic authentication, a verified SSO claim, or an equivalent secure identity mechanism).

### 4.2. Bypassing the Proxy to Hit the Backend Directly

Common bypass paths: public IP/port, node port, an alternate load balancer, an internal Kubernetes Service callable by any pod in the cluster, debug/management ports, unguarded port-forwarding, VPN routes, or overly permissive internal networks.

With header-based pre-auth, **network isolation is a necessary condition**: no path may exist from clients or unauthorized workloads to the backend. If multiple ingresses/gateways exist, **every path** must enforce the same policy. `ClusterIP` alone is not a network authorization policy; enforceable firewall/security group/Kubernetes NetworkPolicy/service mesh rules are required.

TLS encryption between proxy and backend reduces eavesdropping/tampering in transit. **mTLS with client certificate verification** further lets the backend identify the exact proxy. Enabling HTTPS without authenticating allowed peers still does not prove the sender is the gateway.

### 4.3. Duplicate Headers or Header Name Variants

HTTP header names are case-insensitive. Account for variants such as:

~~~http
X-Verified-User: alice
x-verified-user: admin
X_Verified_User: admin
~~~

Proxies, frameworks, and servlet containers can differ in how they handle duplicate names, underscores, hyphens, whitespace, and header folding; `request.getHeader(...)` may return a value based on container-specific rules. There is a risk that **the gateway inspects one variant while the backend reads another**.

Countermeasures: at the edge, strip externally sent identity/role headers under a single canonicalization policy; reject duplicate/ambiguous headers; have the gateway emit **one single header name**; test end-to-end through the exact proxy/container deployed in production. Never rely solely on renaming a header to something hard to guess.

### 4.4. Self-Asserted Roles or IPs

Do not trust headers such as `X-Role: ADMIN`, `X-User-Groups: superuser`, or `X-Is-Admin: true` unless the gateway guarantees provenance and the app validates/maps them. Even with a valid username, **permissions must still be checked** against trustworthy data.

`X-Forwarded-For`, `Forwarded`, and `X-Real-IP` primarily carry request path metadata, **not identity credentials**. IP headers can be injected by clients if the edge does not sanitize them. Never rely solely on `X-Forwarded-For` or `request.getRemoteAddr()` after proxy header rewriting to prove a user is logged in.

### 4.5. Flawed Error and Session Policies

- If the identity service/gateway times out and the reverse proxy lets requests through (`fail open`), that is a critical flaw; fail closed is mandatory.
- A backend exposing form login, Basic auth, or endpoints bypassed via misconfigured `securityMatcher`/routes can open paths outside the pre-auth model.
- Applications holding stale `Authentication` in sessions when the proxy switches users or logs out: design session synchronization, principal-change detection, and invalidation. For APIs needing per-request pre-auth, stateless configuration is usually easier to control.
- Do not treat CORS as an anti-spoofing barrier: `curl`, server-to-server scripts, and direct HTTP clients are unaffected by browser CORS restrictions.

## 5. Defense-in-Depth Architecture

Implement in sequence rather than relying on a single control:

1. **Authenticate at the edge:** the gateway enforces authentication on all protected routes; validates session/token/IdP, expiration, and account status; if authentication fails, never forwards the request to the backend.
2. **Strip then re-create:** remove/overwrite all inbound identity and role headers, including duplicates and spelling variants; populate `X-Verified-User` solely from a successful authentication result. Never copy from client `$http_...` variables.
3. **Lock down backend paths:** firewalls, security groups, NetworkPolicies, or mesh policies permit only verified gateways to connect to the application port; block direct paths and alternate ingresses.
4. **Protect every hop:** HTTPS client→gateway, TLS or mTLS gateway→backend based on risk level; manage certificates, trust roots, DNS, and peer identities properly.
5. **Fail closed in the app:** missing header, non-existent user, disabled account, or missing authority must be denied; never fall back to an anonymous user with privileges or an elevated default role.
6. **App-controlled permissions:** load roles/permissions from a managed source; map external subjects to internal users with stable identifiers; never grant admin solely because a client sent `X-Role`.
7. **Test real paths:** test direct backend ports, spoofed requests to the edge, duplicate/alias headers, auth outages, multi-hop chains, and session changes; audit periodically whenever ingress/service mesh changes.

If the architecture cannot guarantee **the proxy is the sole origin** of the identity header, consider having the backend verify cryptographic proof itself—such as a **JWT/OIDC access token** with signature, issuer, audience, expiration, scopes, and transport bindings as required. That shifts from "trusting a plain username header" to "verifying a token"; never confuse a raw username string with a verified JWT.

## 6. NGINX Example: Proxy Actually Authenticating and Overwriting Username

The example below uses **NGINX HTTP Basic authentication** to clarify where identity is verified. In enterprise setups an SSO/OIDC gateway may replace Basic; the principles of sanitizing inbound headers, deriving from verified identity, and locking down the backend remain identical.

Assumptions:
- Public hostname: `app.example.test`.
- Backend listens only on an internal network: `10.30.0.15:8080` and the firewall permits only NGINX to connect.
- NGINX has a valid TLS certificate and the gateway password file is configured securely.
- The Spring backend reads `X-Verified-User` specifically.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        # Authenticate before forwarding request to backend.
        auth_basic "Application Gateway";
        auth_basic_user_file /etc/nginx/auth/users.htpasswd;

        # Derive identity FROM NGINX AUTHENTICATION RESULT.
        # Do not take from client's $http_x_verified_user.
        proxy_set_header X-Verified-User $remote_user;

        # Strip other headers that the app might mistakenly treat as role/user.
        proxy_set_header X-Verified-Roles "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header Authorization "";

        # Reconstruct forwarding metadata at the trust boundary.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;

        proxy_pass http://10.30.0.15:8080;
    }
}
~~~

**Why is this an example with clear boundaries?**

- NGINX populates `$remote_user` only after Basic authentication accepts the credentials. `proxy_set_header X-Verified-User $remote_user` **replaces any client-sent value** with the verified result.
- `proxy_set_header ... ""` prevents NGINX from forwarding those headers upstream; clearing `Authorization` avoids accidentally passing Basic credentials to the backend.
- `X-Forwarded-For $remote_addr` sets the value to the peer seen by NGINX, avoiding preservation of externally injected IP chains. If a legitimate load balancer sits in front, configure trusted upstream/real-IP rules separately and verify the trust chain; never copy blindly.
- **The NGINX snippet is only one piece**—it does not establish firewalls, mTLS, password management, monitoring, or detection of every header alias. Those must be configured in the actual deployment environment.

**Limitation:** NGINX Basic authentication does not replace modern SSO, MFA, or enterprise session management. With `auth_request`/OIDC, the identity must come from **the verified authentication system's response**, not from a client request header. Flows missing a user or encountering auth service errors must be blocked. Even with a trusted proxy, use appropriate TLS/mTLS channels on proxy→backend links.

## 7. Spring Boot 3.x / Spring Security 6.x / Java 17+ Example

The Servlet application example below uses standard pre-auth APIs. It illustrates that Spring **trusts the username received in the header** and loads permissions only for a known user. This setup is safe only when combined with the network and proxy boundaries from the previous sections; **starting the app standalone on a public port and sending headers manually is insecure**.

### 7.1. Dependencies

In a Maven Spring Boot 3.x application using `spring-boot-starter-parent` or the Spring Boot BOM:

~~~xml
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
~~~

Use Java 17+ and a Spring Boot 3.x project with sources under `src/main/java/com/example/preauth/`.

### 7.2. Entry Point

File `DemoApplication.java`:

~~~java
package com.example.preauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityFilterChain and Pre-auth Provider

File `SecurityConfiguration.java`:

~~~java
package com.example.preauth;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    UserDetailsService users() {
        return username -> {
            // Demo example: load user/role from allowlist.
            // Production must integrate with internal identity/permission source.
            if (!"alice".equals(username)) {
                throw new UsernameNotFoundException("Unknown internal user");
            }
            // Password is not used by the pre-authentication provider.
            return new User(
                    "alice",
                    "",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, UserDetailsService users) throws Exception {

        var provider = new PreAuthenticatedAuthenticationProvider();

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
                detailsService = new UserDetailsByNameServiceWrapper<>(users);

        provider.setPreAuthenticatedUserDetailsService(detailsService);

        var preAuth = new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(new ProviderManager(provider));

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(
                                new Http403ForbiddenEntryPoint()))
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .addFilterBefore(
                        preAuth, UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

**Explanation of key decisions:**

- `PreAuthenticatedAuthenticationProvider` does not check passwords. `UserDetailsByNameServiceWrapper` takes the name from `PreAuthenticatedAuthenticationToken` to look up `UserDetails`; in production, use a trusted directory/database/identity mapping instead of an `alice` allowlist.
- `RequestHeaderAuthenticationFilter` sets `principalRequestHeader` explicitly; never trust arbitrary similarly named headers or a self-asserted role field.
- `setExceptionIfHeaderMissing(false)` lets requests proceed when the principal is absent; **`anyRequest().authenticated()` still denies** unauthenticated requests. `Http403ForbiddenEntryPoint` returns HTTP 403 rather than redirecting to a login form. Do not confuse "filter continues" with "access granted."
- `SessionCreationPolicy.STATELESS` avoids using Spring sessions to hold stale identities across requests in the example. If the application uses sessions, explicitly design logout, principal changes, invalidation, and gateway cookie coordination.
- `httpBasic` and `formLogin` are disabled so no competing login mechanism exists outside the pre-auth model. Depending on the system, other mechanisms may be valid, but they require a clearly proven design.
- **Do not register `preAuth` as a standalone `@Bean Filter`** if already adding it manually to `SecurityFilterChain`: Spring Boot may auto-register the Servlet `Filter` bean and run it twice in two different chains. Here the filter is instantiated locally and attached in one place.
- The example **does not disable default CSRF protection**. With browsers automatically sending cookies/credentials, CSRF must still be evaluated for state-changing operations; enabling stateless mode does not grant CSRF immunity.
- Leaving the password as an empty string is a technical placeholder in the demo `UserDetails`; pre-auth neither reads nor compares it. Do not use this example as a production password-storage pattern.

### 7.4. Endpoint Checking the Principal

File `IdentityController.java`:

~~~java
package com.example.preauth;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/me")
    Map<String, Object> me(Authentication auth) {
        List<String> roles = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList();
        return Map.of(
                "username", auth.getName(),
                "authorities", roles);
    }
}
~~~

When a request travels **through the gateway that authenticated `alice`**, the response contains these two fields (JSON key order is not guaranteed):

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
~~~

To run in a complete Maven Spring Boot 3.x project, use `mvn spring-boot:run` or build with `mvn package` and launch the JAR via `java -jar target/<jar-name>.jar`. This source spans **three Java files of a Spring Boot application**, not a standalone file compiled with bare `javac`; it requires dependencies and a configured gateway.

**Note on internal testing:** If you call the backend directly with `X-Verified-User: alice`, the sample app can respond with `alice`. That demonstrates why **blocking direct connections at the network layer** is mandatory; never treat that as a test proving spoofing protection succeeded.

## 8. Proving Security with Realistic Requests

With NGINX properly configured, `alice` present in the gateway's Basic-auth file, and the backend permitting access only from NGINX:

### 8.1. Unauthenticated Client Claiming to Be Admin

~~~bash
curl -i -H 'X-Verified-User: admin' https://app.example.test/me
~~~

**Expected:** HTTP 401 because the gateway has not received Basic credentials; the backend must never see the `admin` identity header. Never let a client bypass the gateway simply by supplying `X-Verified-User`.

### 8.2. Client Is Alice Attempting to Spoof Another User's Header

~~~bash
curl -i --user alice \
  -H 'X-Verified-User: admin' \
  https://app.example.test/me
~~~

`curl` prompts for a password if not provided. Once `alice`'s credentials validate, **the gateway must overwrite** the header to `alice`; the backend receives only `X-Verified-User: alice`. The `/me` response must be `alice`, not `admin`. If the gateway rejects duplicate headers outright, that is also safe behavior; exact behavior must be defined and tested.

### 8.3. Bypassing the Gateway to Send a Valid Header to the Backend

~~~bash
curl -i -H 'X-Verified-User: alice' \
  http://10.30.0.15:8080/me
~~~

**Expected from a client machine or unauthorized workload:** the connection is blocked by firewall/NetworkPolicy/mTLS access policy. Merely getting HTTP 403 from the app is insufficient proof of security because `alice` is a valid user; if the connection gets through, Spring may treat the request as `alice`.

### 8.4. Missing Header or User Unknown to the Application

When called via a valid proxy without supplying an identity header, or supplying a non-existent username: the application creates no privileged principal and denies access (in the illustrative config: HTTP 403). If the auth service is unavailable, the gateway returns an error / fails closed; unauthenticated requests must never reach the backend.

### 8.5. Duplicate / Mismatched Header Scenarios

Test through the **exact production NGINX/Ingress/CDN/servlet container**:

~~~bash
curl -i --user alice \
  -H 'X-Verified-User: admin' \
  -H 'x-verified-user: bob' \
  -H 'X_Verified_User: carol' \
  https://app.example.test/me
~~~

None of the client-asserted values may become the principal. Either reject immediately at the edge, or cleanly normalize and emit **one** `alice` identity. Header-handling behavior must be verified empirically because it depends on the proxy and container.

### 8.6. Mandatory Test Matrix

| Case | Expected Result | Layer to Verify |
|---|---|---|
| Unauthenticated request sending `X-Verified-User` | Gateway rejects, never reaches app | Gateway |
| Authenticated as `alice` sending `admin` header | App receives `alice` or gateway rejects | Header sanitization + gateway |
| Direct connection to backend port sending `alice` header | Connection blocked at infrastructure | NetworkPolicy / firewall / mTLS |
| Missing identity header from proxy | No authenticated principal | Spring Security |
| Username absent from internal store | No permissions granted | UserDetails service |
| Client-sent `ADMIN` role header | No admin permissions granted | Gateway + authorization |
| Two headers with same name differing in case | Rejected or safely canonicalized | Proxy + servlet container |
| Underscore / alias headers | Rejected or completely stripped | Gateway parser/normalizer |
| Auth service disconnected | Requests fail to reach backend | Gateway fail closed |
| Logout or user switch over existing connection | Wrong user's `Authentication` not retained | Gateway + session strategy |
| Multi-hop: client supplies `X-Forwarded-For` | Trust decision unaffected | Proxy chain |
| Side routes like `/actuator`, WebSocket, gRPC, admin | Same policy enforced or independent auth | Ingress/port routing |
| Cookie + browser POST request | CSRF protection matching session model | Spring Security |

## 9. `Forwarded` and `X-Forwarded-*` Are Not Identity Headers

Many Spring Boot deployments behind proxies enable:

~~~properties
server.forward-headers-strategy=native
~~~

Or choose `framework` so Spring processes `ForwardedHeaderFilter`. Its primary purpose is restoring scheme, host, port, client address, and prefix to build accurate redirects and links behind a reverse proxy.

However, `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host` can all be **spoofed by clients** if the edge fails to strip/overwrite them. Spring Framework documentation advises that proxies at the trust boundary must strip external `Forwarded` and `X-Forwarded-*` headers before emitting valid values.

**Common confusions:**
- `ForwardedHeaderFilter` does not turn `X-Verified-User` into authentication proof.
- `server.forward-headers-strategy` does not replace an auth gateway.
- An NGINX setting like `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` can preserve client-injected IP chains unless trust-chain rules are configured; specify exactly which proxies may append hops.
- If using an IP allowlist, enforce it at the network/transport layer or on equipment aware of trusted hops—never read an arbitrary client-supplied IP header.

Never rely on `request.getRemoteAddr()` populated by `ForwardedHeaderFilter`/container from unsanitized headers to conclude a connection came from a trusted gateway.

## 10. Multi-Proxy and Kubernetes Scenarios

### Multi-Hop Chains

~~~text
Client → CDN → Load Balancer → Auth Gateway → Service Mesh → Spring Boot
             ^           ^             ^              ^
             Each hop must know whom it trusts and which headers it writes/reads.
~~~

Multiple hops may append `X-Forwarded-*`, yet **there must be a single clear boundary** responsible for authenticating users, stripping identity headers from prior hops, and issuing the identity header for the backend. If an intermediate proxy can be reached directly or inject `X-Verified-User` arbitrarily, the model breaks down.

In Kubernetes:
- Public Ingress must sit in front of authentication; prevent alternate Ingresses from bypassing the gateway to the same Service.
- `ClusterIP` does not restrict other Pods in the cluster by identity; use a default-deny ingress NetworkPolicy and explicitly allow only authorized gateway pods/namespaces.
- If using a service mesh, peer authentication/mTLS and authorization policies must match exact workload identities; do not rely on mutable Pod IP addresses.
- Watch `/actuator`/management ports, probes, admin ports, and internal routes; clearly distinguish which endpoints need pre-auth and which carry separate policies.
- Do not protect only one hostname if the backend is also exposed under another hostname or port.

## 11. Common Mistakes and Fixes

1. **Configuring only the filter and thinking headers are security:** build/verify a gateway that truly authenticates, strips and overwrites headers, while blocking direct backend access.
2. **Using `$http_x_verified_user` in NGINX:** that comes from the client; switch to `$remote_user` after valid authentication or an SSO-gateway-verified identity.
3. **Relying on a "secret header name":** clients can guess, probe, inspect requests, or read documentation; security must come from the issuing source and transport channel.
4. **Assigning roles directly from headers:** clients can send `ROLE_ADMIN`; load permissions only from internal stores or verified claims mapped by policy.
5. **Filter invoked twice:** avoid registering a `Filter` as a Servlet container `@Bean` while also calling `addFilterBefore` on the Spring Security chain without managing registration/order.
6. **Adding unguarded login fallbacks:** another `formLogin`/Basic/JWT flow may accidentally bypass the gateway; separate routes/chains cleanly and test thoroughly.
7. **App returns 200 on direct spoof:** fix network access/mTLS and the proxy chain. Simply checking in a controller whether a username exists does not stop impersonation of valid users.
8. **Confusing client IP with proxy identity:** `X-Forwarded-For` can be untrusted data, and NAT places multiple users behind one IP; never use it instead of user authentication.
9. **Missing header still proceeds with privileges:** configure `anyRequest().authenticated()`, grant no roles to anonymous, and review policies and custom filters.
10. **Forgetting logout/principal changes when using sessions:** consider stateless mode or detect principal changes and invalidate sessions appropriately.
11. **Allowing duplicate/parser-divergent headers:** test the actual gateway/container, strip or reject ambiguous values that could lead to request smuggling.
12. **Trusting all internal workloads:** isolate network and identity permissions across services; a compromised Pod must not impersonate the gateway.

## 12. Review and Operations Checklist

- [ ] Map every client→backend path, including secondary ingresses, admin ports, and multi-hop routes.
- [ ] Every request to protected endpoints is authenticated by the gateway **before** forwarding.
- [ ] Edge strips/overwrites client-asserted identity, permission, and forwarded metadata headers.
- [ ] Backend accepts connections only from authorized gateways/workloads; negative tests verify bypass rejection.
- [ ] TLS/mTLS and peer identity verification are deployed per risk and network policy.
- [ ] `UserDetails`/authorities are loaded and mapped from trusted sources; unknown/disabled users are denied.
- [ ] Spring Security covers all routes and HTTP methods; no unintended login fallback exists.
- [ ] Proxy/header parsers reject or safely handle duplicates, casing, underscores, and aliases.
- [ ] Auth service timeouts/errors fail closed; logging and alerting suffice to detect incidents.
- [ ] Session/logout/CSRF behavior is verified for cookies, SPAs, APIs, or browser flows.
- [ ] Integration tests traverse the production path, including curl spoofing and direct-backend attempts.
- [ ] Never log access tokens, Basic passwords, or credentials; log verified identity with request ID and hop provenance.

## 13. Key Takeaway

**The question is not "what is this header named?"—it is "who is authorized to create this header, and how does the backend verify the path?"**

`RequestHeaderAuthenticationFilter` is an adapter that moves an identity into `SecurityContext`, **not an anti-spoofing defense**. A secure system requires all three conditions: **the gateway authenticates and rewrites the header**, **the backend receives traffic solely from the controlled gateway**, and **Spring Security continues enforcing user/authorities and access control**. Missing any one of the three leaves a header username vulnerable to attacker self-assertion.

## References

- [Spring Security — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): nature of pre-auth and limits of request-header authentication.
- [Spring Security API — RequestHeaderAuthenticationFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): `principalRequestHeader`, `exceptionIfHeaderMissing`, and header forgery warnings.
- [Spring Security API — AbstractPreAuthenticatedProcessingFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): principal handling, `SecurityContext`, and failure behavior.
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `SecurityFilterChain` ordering and registering authentication filters.
- [Spring Framework — Forwarded Headers, Security Considerations](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): sanitizing `Forwarded` and `X-Forwarded-*` at the edge.
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`.
- [NGINX — proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header): overwriting and removing request headers sent upstream.
- [NGINX — auth_request](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html): upstream auth delegation, `auth_request_set`, and subrequest allow/deny rules.
