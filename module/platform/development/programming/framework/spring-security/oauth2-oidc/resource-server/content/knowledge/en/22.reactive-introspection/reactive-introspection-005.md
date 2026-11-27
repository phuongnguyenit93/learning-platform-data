# OAuth2AuthenticatedPrincipal in BearerTokenAuthentication

## 1. After Introspection, What Data Does the Resource Server Have?

In a **Spring Security OAuth 2.0/OIDC Resource Server using WebFlux**, a client sends an opaque access token over HTTP:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer opaque-access-token
~~~

An opaque token is a credential managed by the Authorization Server (AS). The Resource Server (RS) typically cannot deduce the subject, scopes, or expiry merely by parsing the string. The RS calls **OAuth 2.0 Token Introspection** per RFC 7662 to verify the token is active and receive metadata.

For example, the AS returns:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "iss": "https://auth.example.com/realms/shop",
  "aud": ["orders-api"],
  "exp": 1794731400,
  "iat": 1794729600
}
~~~

When introspection succeeds, two Spring Security types appear:

- **OAuth2AuthenticatedPrincipal**: represents the identity, attributes, and authorities resolved after introspection.
- **BearerTokenAuthentication**: the Authentication result wrapping that principal, the verified OAuth2AccessToken, and authorities to be placed in the reactive security context.

Core point: **the principal is not the raw token; the raw token is not a verified Authentication; claims do not automatically equate to business permissions**.

Diagram:

~~~text
HTTP Authorization: Bearer opaque-token
             |
             v
ReactiveOpaqueTokenIntrospector
  verifies active status and retrieves token attributes
             |
             v
OAuth2AuthenticatedPrincipal
  name + attributes + authorities
             |
             v
OpaqueTokenReactiveAuthenticationManager
  builds BearerTokenAuthentication
             |
             v
ReactiveSecurityContextHolder
             |
             v
WebFlux authorization and business handler
~~~

This lesson explains the exact APIs, the data inside the principal, how to read and customize them in WebFlux, and the security boundaries.

## 2. Five Distinct Concepts

| Object | Responsibility | Authenticated? |
|---|---|---|
| **Raw Bearer token** | Credential string sent by caller | No |
| **BearerTokenAuthenticationToken** | Authentication request carrying the token string | No |
| **OAuth2AuthenticatedPrincipal** | Name, attributes, and authorities from successful introspection | Valid after trust validation |
| **BearerTokenAuthentication** | Default Authentication result for the opaque Bearer flow | Authenticated |
| **SecurityContext** | Holds the Authentication for authorization | Per authenticated pipeline |

A logical illustration:

~~~text
"opaque-abc123"
  is only a raw credential.

BearerTokenAuthenticationToken("opaque-abc123")
  is only an authentication request.

OAuth2AuthenticatedPrincipal:
  name="user-42"
  attributes={sub, scope, client_id, aud, ...}
  authorities=[SCOPE_orders.read, SCOPE_orders.write]
  comes from trusted introspection.

BearerTokenAuthentication:
  principal=OAuth2AuthenticatedPrincipal
  accessToken=verified OAuth2AccessToken
  authorities=...
  authenticated=true
  is the authentication result.
~~~

Never manually construct an authenticated BearerTokenAuthentication from an unverified raw token just to avoid calling the AS. That is an authentication bypass.

## 3. Reactive Processing Chain in WebFlux

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as AuthenticationWebFilter
    participant X as ServerBearerTokenAuthenticationConverter
    participant M as OpaqueTokenReactiveAuthenticationManager
    participant I as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    participant S as Reactive Security Context
    participant Z as Authorization

    C->>F: Authorization Bearer opaque-token
    F->>X: convert(exchange)
    X-->>F: BearerTokenAuthenticationToken
    F->>M: authenticate(raw credential)
    M->>I: introspect(token)
    I->>AS: POST introspection, RS credentials
    alt active=true
      AS-->>I: Token attributes
      I-->>M: OAuth2AuthenticatedPrincipal
      M-->>F: BearerTokenAuthentication
      F->>S: Authentication success
      S->>Z: Authorities and principal
    else active=false
      AS-->>I: Inactive token
      I-->>M: Authentication error
    else upstream error
      AS-->>I: HTTP 401, 5xx, timeout
      I-->>M: Introspection failure
    end
~~~

Components:

| WebFlux component | Role |
|---|---|
| **ServerWebExchange** | Reactive HTTP request/response |
| **ServerBearerTokenAuthenticationConverter** | Extracts the raw Bearer token |
| **AuthenticationWebFilter** | Invokes the authentication manager and manages the result |
| **OpaqueTokenReactiveAuthenticationManager** | Verifies the opaque Bearer token and builds Authentication |
| **ReactiveOpaqueTokenIntrospector** | Verifies the token via AS/trusted token store |
| **ReactiveOpaqueTokenAuthenticationConverter** | Converts token + authenticated principal into Authentication |
| **OAuth2AuthenticatedPrincipal** | Attributes/authorities after introspection |
| **BearerTokenAuthentication** | Default Authentication result |
| **ReactiveSecurityContextHolder** | SecurityContext inside the Reactor Context |
| **SecurityWebFilterChain** | WebFilters protecting requests |
| **ServerHttpSecurity** | WebFlux Security configuration DSL |

Do not confuse with Servlet:

| Servlet | WebFlux |
|---|---|
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| OpaqueTokenAuthenticationProvider | OpaqueTokenReactiveAuthenticationManager |
| OpaqueTokenIntrospector | ReactiveOpaqueTokenIntrospector |
| Servlet Filter | WebFilter |
| HttpServletRequest | ServerWebExchange |
| Typical ThreadLocal SecurityContextHolder | ReactiveSecurityContextHolder via Reactor Context |

**OpaqueTokenReactiveAuthenticationManager** is a ReactiveAuthenticationManager. It uses the introspector and authentication converter to build an Authentication after successful introspection. In the default configuration, the typical result is **BearerTokenAuthentication**; a custom converter can change the result type.

## 4. RFC 7662 Returns JSON, Not a Java Authentication

An introspection request typically looks like:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_RS_CREDENTIALS

token=opaque-access-token&token_type_hint=access_token
~~~

The AS returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1794731400
}
~~~

RFC 7662 specifies the **active boolean and metadata**, not Java types such as OAuth2AuthenticatedPrincipal or BearerTokenAuthentication. Spring Security uses the trusted response to construct those objects.

Distinguish the outcomes:

- **HTTP 200 + active=true**: AS confirms the token is active; the introspector may build a principal.
- **HTTP 200 + active=false**: token is not accepted by the AS; do not build an authenticated principal.
- **HTTP 401/403 from the AS introspection endpoint**: likely an RS credential or introspection permission issue; does not automatically mean the caller's token is invalid.
- **Timeout, TLS, HTTP 429/5xx, malformed JSON**: dependency/protocol failure; unknown whether the token is active.

All failures where the token cannot be verified must **fail closed**: never let the protected request proceed.

### Two Types of Credentials

The **caller's Bearer token** is sent to the Resource Server. The **Resource Server's Client ID/client secret** is used to call the AS introspection endpoint. If the AS returns 401 invalid_client after a secret rotation, the Resource Server has not proven the user's token is inactive. Never "work around" failed introspection by creating a fake principal.

## 5. The ReactiveOpaqueTokenIntrospector Contract

The interface belongs to package:

~~~java
org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector
~~~

Conceptual signature:

~~~java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
~~~

**Do not redefine** this interface in your application; the snippet merely illustrates the Spring Security API.

Meaning:

~~~text
introspect(token)
   |
   +-- success -> Mono<OAuth2AuthenticatedPrincipal>
   |
   +-- inactive -> authentication/introspection error
   |
   +-- AS/network/protocol failure -> error signal
~~~

The introspector **does not return Mono<BearerTokenAuthentication>** by its API. The next layer's authentication manager/converter uses the principal to create an Authentication. When a token is inactive, it must emit an appropriate error rather than returning a principal with empty authorities and treating it as success.

### Never Turn Errors into a Default Principal

Anti-pattern:

~~~java
// Dangerous: an AS error turns into authentication success.
return delegate.introspect(token)
        .onErrorResume(ex -> Mono.just(defaultUserPrincipal));
~~~

Even if defaultUserPrincipal holds minimal permissions, it is still an authentication bypass. If a business endpoint only requires authenticated(), forged tokens can slip through.

**A custom ReactiveOpaqueTokenIntrospector must uphold the trust boundary of token acceptance.**

## 6. What APIs Does OAuth2AuthenticatedPrincipal Have?

Interface in package:

~~~java
org.springframework.security.oauth2.core
    .OAuth2AuthenticatedPrincipal
~~~

Key methods:

| API | Description |
|---|---|
| **getName()** | Principal name per implementation and token profile |
| **getAttributes()** | Map<String, Object> holding attributes |
| **getAttribute(String)** | Reads a single attribute by name |
| **getAuthorities()** | Collection<? extends GrantedAuthority> |

Example:

~~~java
import java.util.Map;
import java.util.Collection;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

OAuth2AuthenticatedPrincipal principal = ...;

String name = principal.getName();
Map<String, Object> attributes = principal.getAttributes();
String subject = principal.getAttribute("sub");

Collection<? extends GrantedAuthority> authorities =
        principal.getAuthorities();
~~~

**Never assume getName() is always an email, username, or internal database user ID.** In user tokens, name typically maps from sub when present; in client_credentials tokens, the principal may represent a machine client with no human subject.

## 7. DefaultOAuth2AuthenticatedPrincipal

Spring Security provides **DefaultOAuth2AuthenticatedPrincipal** to hold name, attributes, and authorities.

Example creating a principal **in unit tests**:

~~~java
import java.util.Map;
import java.util.List;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;

OAuth2AuthenticatedPrincipal principal =
        new DefaultOAuth2AuthenticatedPrincipal(
                "user-42",
                Map.of(
                        "sub", "user-42",
                        "client_id", "shop-web",
                        "tenant_id", "tenant-blue"),
                List.of(
                        new SimpleGrantedAuthority("SCOPE_orders.read"),
                        new SimpleGrantedAuthority("SCOPE_orders.write")));
~~~

**Instantiating this class directly does not perform introspection.** In production, attributes must only be used to build an Authentication after passing through a trusted verification mechanism. An object named OAuth2AuthenticatedPrincipal is not automatically trustworthy because of its class name.

Parameters:

- **name**: principal name.
- **attributes**: metadata whose source has been verified.
- **authorities**: privileges permitted into Spring Security authorization.

Having a roles attribute in the Map does not automatically turn it into ROLE_ADMIN unless you have a trusted mapping.

## 8. How Does BearerTokenAuthentication Hold the Principal?

Class in package:

~~~java
org.springframework.security.oauth2.server.resource.authentication
    .BearerTokenAuthentication
~~~

Typical public constructor:

~~~java
new BearerTokenAuthentication(
        OAuth2AuthenticatedPrincipal principal,
        OAuth2AccessToken credentials,
        Collection<? extends GrantedAuthority> authorities)
~~~

Key points:

| Member/API | Meaning |
|---|---|
| **getPrincipal()** | OAuth2AuthenticatedPrincipal |
| **getTokenAttributes()** | Attribute map from introspection |
| **getAuthorities()** | Final Authentication authorities |
| **getName()** | Authentication name, typically derived from principal name |
| **getToken()** | OAuth2AccessToken from superclass, when using the matching API |
| **isAuthenticated()** | Authentication status |
| **OAuth2AccessToken credentials** | Verified credential per flow, not JWT claims |

Usage example:

~~~java
BearerTokenAuthentication authentication = ...;

OAuth2AuthenticatedPrincipal principal =
        authentication.getPrincipal();

String name = authentication.getName();

Object subject =
        authentication.getTokenAttributes().get("sub");

boolean hasReadAuthority =
        authentication.getAuthorities().stream()
                .anyMatch(a ->
                        "SCOPE_orders.read".equals(a.getAuthority()));
~~~

**getTokenAttributes() does not require the opaque token to be a JWT.** Attributes come from AS introspection, not from decoding a payload out of the token string.

### Principal Authorities vs. Authentication Authorities

The principal carries authorities from the introspector. The final Authentication carries authorities selected by the authentication converter, which may match or transform the principal's authorities. When checking actual permissions, use **Authentication.getAuthorities()**, since that is what Spring Security authorization evaluates.

Some Spring Security versions may add factor-related granted authorities. Do not assert that an Authentication contains an exact count of scope authorities via strict list equality; instead assert that the required authorities are present.

## 9. BearerTokenAuthentication Differs from BearerTokenAuthenticationToken

Two easily confused names:

~~~text
BearerTokenAuthenticationToken
  - created by the converter from the HTTP credential
  - holds the raw token
  - not yet authenticated

BearerTokenAuthentication
  - created by the manager/converter after successful introspection
  - holds OAuth2AuthenticatedPrincipal and OAuth2AccessToken
  - authenticated result
~~~

An unauthenticated example:

~~~java
BearerTokenAuthenticationToken request =
        new BearerTokenAuthenticationToken("opaque-test-token");
~~~

Never construct a BearerTokenAuthentication from the request above and put it in the SecurityContext without introspecting. That turns an unverified credential into a trusted identity.

## 10. Comparison with a JWT Resource Server

JWT:

~~~text
Authorization: Bearer signed-JWT
   |
   v
ReactiveJwtDecoder verifies JWS signature, iss, aud, exp...
   |
   v
JwtAuthenticationToken with Jwt principal
   |
   v
Authorization
~~~

Opaque:

~~~text
Authorization: Bearer opaque-token
   |
   v
ReactiveOpaqueTokenIntrospector verifies active via AS
   |
   v
OAuth2AuthenticatedPrincipal
   |
   v
BearerTokenAuthentication
   |
   v
Authorization
~~~

| Aspect | JWT Resource Server | Opaque Resource Server |
|---|---|---|
| Verification | ReactiveJwtDecoder/JWKS | ReactiveOpaqueTokenIntrospector |
| Typical Principal | Jwt | OAuth2AuthenticatedPrincipal |
| Typical Authentication | JwtAuthenticationToken | BearerTokenAuthentication |
| Attributes | Verified JWT claims | Trusted introspection metadata |
| Authority mapping | JWT scope/claims | Introspection scope/attributes |
| Per-request AS network call | Not required if keys are cached | Typically yes, unless policy-bound cache |
| Revocation awareness | May need extra mechanisms | AS can reflect revocation via active=false |

Even when an access token has a JWT format, an application can still choose **opaque introspection** over JWT decoding. In that case, the Java Authentication follows the introspection flow rather than the shape of the token string.

**Never cast Authentication.getPrincipal() to Jwt** when the application uses an opaque Resource Server.

## 11. Common Introspection Attributes

RFC 7662 defines several attributes; the AS is not required to provide every attribute for every token type.

| Attribute | Common wire type | Meaning | Watch out |
|---|---|---|---|
| **active** | Boolean | Token status per AS | false must be rejected before creating a principal |
| **scope** | Space-delimited String | Permission scope | Spring Security may normalize to List<String> |
| **client_id** | String | OAuth client issued the token | Not necessarily a user |
| **sub** | String | Subject | Issuer-scoped, not globally unique |
| **username** | String | Display name per AS | Not a guaranteed stable user key |
| **token_type** | String | Token type | Must match bearer per contract |
| **exp** | NumericDate | Expiration | May be mapped to Instant |
| **iat** | NumericDate | Issued At | Does not replace auth_time |
| **nbf** | NumericDate | Not Before | Temporal validity |
| **aud** | String/Array | Intended recipients | Enforce resource binding |
| **iss** | String | Issuer identifier | Requires trust policy |
| **jti** | String | Token ID | Not a user ID |
| **tenant_id** | Provider-specific | Tenant metadata | No universal RFC 7662 semantics |
| **groups/roles** | Provider-specific | Group/role metadata | Does not automatically become GrantedAuthority |

### Do Not Cast Every Attribute to String

Suppose the AS returns:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write",
  "exp": 1794731400,
  "aud": ["orders-api"]
}
~~~

After introspection, the implementation may normalize:

~~~text
scope -> List<String>
exp   -> Instant
aud   -> List<String>
~~~

The following is not guaranteed to work:

~~~java
String scope = principal.getAttribute("scope");
~~~

because scope may be a List. If your goal is permission checking, use **principal.getAuthorities()** or **authentication.getAuthorities()**. If you need raw attributes, verify the Java type per your token contract and check types before casting.

## 12. Scope to SCOPE_ GrantedAuthority

AS returns:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Spring Security's default mapping typically generates:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

WebFlux policy:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

The **SCOPE_** prefix is a Spring Security convention, not something required on the RFC 7662 wire response.

### Scope Differs from Domain Permission

A token with orders.write cannot automatically modify every order. The domain may require:

~~~text
hasAuthority("SCOPE_orders.write")
AND actor belongs to order tenant
AND actor is allowed to modify this order
AND order state permits modification
~~~

**Token active** is the credential check. **Sufficient scope** is coarse authorization. **Ownership/tenant/workflow** is domain authorization.

### SCOPE_ Differs from ROLE_

- hasAuthority("SCOPE_orders.write") checks a scope-based authority.
- hasRole("ADMIN") checks ROLE_ADMIN by convention.
- Claim roles=["ADMIN"] is not mapped to ROLE_ADMIN by default.

Never grant an admin role from a group attribute lacking an explicit trust contract.

## 13. Spring Boot Configuration for WebFlux Opaque Tokens

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: REPLACE_WITH_SECRET_MANAGER
~~~

The Resource Server uses its client ID/secret to authenticate to the AS introspection endpoint; this is **not the caller's access token**.

In production, secrets must come from a secret manager or environment injection. Never commit real secrets to the repository or log credentials in error responses.

**The introspection URI above is an example, not a fixed path for every AS.** Obtain the endpoint from your trusted provider contract or metadata.

An AS may require mTLS or private_key_jwt instead of Basic. SpringReactiveOpaqueTokenIntrospector with the clientId/clientSecret builder is one option; when the AS uses another method, configure the HTTP client/introspector per contract. Never change the authentication method arbitrarily without basis.

## 14. SecurityWebFilterChain Enabling Opaque Introspection

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
~~~

Flow:

1. ServerBearerTokenAuthenticationConverter reads the raw credential.
2. OpaqueTokenReactiveAuthenticationManager invokes ReactiveOpaqueTokenIntrospector.
3. Active token -> OAuth2AuthenticatedPrincipal.
4. Manager/converter builds BearerTokenAuthentication.
5. Security context holds Authentication; authorization checks authorities.
6. Handler runs only after passing the security policy.

**Do not write custom WebFilters to replace OAuth2 Resource Server.** When you want to customize principal or authority mapping, use the introspector or authentication converter extension points.

### CSRF and CORS

A 403 caused by CSRF or CORS is not necessarily insufficient_scope. Pure stateless Bearer APIs may have a different CSRF policy than apps using browser session cookies; establish your trust model before disabling CSRF. CORS preflight requests typically carry no Bearer token and must be handled properly.

## 15. Retrieving OAuth2AuthenticatedPrincipal in a WebFlux Controller

With Spring Security principal injection:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Mono<MeView> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String subject = principal.getAttribute("sub");
        String issuer = principal.getAttribute("iss");

        return Mono.just(new MeView(
                principal.getName(), subject, issuer));
    }

    public record MeView(
            String name, String subject, String issuer) {}
}
~~~

This code assumes the token contract guarantees the attributes being read. If an endpoint requires sub or iss, validate required attributes **before constructing the Authentication or before business authorization** rather than letting a controller treat null as an identity.

**Never return principal.getAttributes() wholesale in an API response.** It can contain token details, client info, tenant info, or sensitive claims. Return a DTO with carefully chosen fields.

### Retrieving BearerTokenAuthentication Directly

Spring Security WebFlux lets a controller inject the Authentication directly:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class SubjectController {

    @GetMapping("/api/subject")
    public Mono<String> subject(BearerTokenAuthentication authentication) {
        Object subject =
                authentication.getTokenAttributes().get("sub");
        return Mono.just(String.valueOf(subject));
    }
}
~~~

This example is purely to show **getTokenAttributes()**. If an API supports service clients without sub, never return the string "null" as a real identity; enforce a principal classification policy. If a custom authentication converter replaces BearerTokenAuthentication, the controller must accept the corresponding type.

## 16. ReactiveSecurityContextHolder in Services

In WebFlux, the security context travels via the **Reactor Context**, so never rely on ThreadLocal as a sole guarantee.

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import reactor.core.publisher.Mono;

public final class CallerIdentityService {

    public Mono<String> currentSubject() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .filter(BearerTokenAuthentication.class::isInstance)
                .cast(BearerTokenAuthentication.class)
                .flatMap(auth -> Mono.justOrEmpty(
                        auth.getTokenAttributes().get("sub")))
                .ofType(String.class);
    }
}
~~~

If Authentication is not a BearerTokenAuthentication or sub is missing, the Mono may complete empty. The application needs an explicit policy for missing identity; never treat Mono.empty() as default authorization.

### Avoid `block()`

Never do:

~~~java
Authentication auth =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .block();
~~~

Blocking the event loop degrades throughput or causes runtime errors. Use map/flatMap/filter/switchIfEmpty and Reactor context propagation. Never stash raw tokens into a global ThreadLocal to "work around" missing context.

## 17. getName(), sub, and client_id Are Not Always Equivalent

A user-delegated token might look like:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "shop-web",
  "scope": "orders.read"
}
~~~

Here **sub** is the subject; **client_id** is the OAuth client issued the token. In the default opaque flow, Authentication.getName() typically derives from sub when present.

A client_credentials token might only contain:

~~~json
{
  "active": true,
  "client_id": "billing-worker",
  "scope": "orders.sync",
  "aud": ["orders-api"]
}
~~~

It represents a **machine client**, not a human user. Never assume:

~~~text
client_id == sub == internalUserId == human user
~~~

An API may need two identity models:

- **USER actor**: issuer + subject + client + tenant context, with user-delegated permissions.
- **CLIENT actor**: issuer + client ID, with machine-to-machine permissions.

Never substitute client_id for sub on human-user endpoints. Conversely, do not demand sub on every M2M flow if the issuer contract does not supply one.

### Multi-Issuer Subject Collision

~~~text
Issuer A, sub=123
Issuer B, sub=123
~~~

can represent two completely different actors. When mapping to local identities, use **(issuer, subject)** or a trusted identity-linking rule. getName alone is not a global identifier.

## 18. Normalizing the Principal into a Domain Identity

Suppose a principal carries:

~~~text
iss=https://auth.example.com/realms/shop
sub=user-42
client_id=shop-web
tenant_id=tenant-blue
scope=orders.read orders.write
~~~

The domain may want an application-defined DTO:

~~~text
CallerIdentity:
  issuer
  subject
  clientId
  tenantId
  actorKind = USER or CLIENT
~~~

Never treat a raw HTTP header like X-Tenant-ID as trusted identity without checking tenant membership. The caller might pass a requestedTenantId in the URL, while the authenticated principal/permission store must prove the caller has access to that tenant.

**Attributes are authorization inputs, not automatically immutable entitlements.** For high-freshness permissions, the domain can query current memberships/entitlements rather than relying solely on claim snapshots.

## 19. Customizing Authorities with a ReactiveOpaqueTokenIntrospector Decorator

When a clear contract states that scope orders.write maps to internal permission PERM_orders.create, you can decorate a trusted introspector:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Bean
ReactiveOpaqueTokenIntrospector introspector() {
    ReactiveOpaqueTokenIntrospector delegate =
            SpringReactiveOpaqueTokenIntrospector
                    .withIntrospectionUri(
                            "https://auth.example.com/oauth2/introspect")
                    .clientId("orders-api-introspector")
                    .clientSecret(
                            System.getenv("INTROSPECTION_CLIENT_SECRET"))
                    .build();

    return token -> delegate.introspect(token)
            .map(principal -> {
                List<GrantedAuthority> mapped =
                        new ArrayList<>(principal.getAuthorities());

                boolean hasWriteScope =
                        mapped.stream().anyMatch(a ->
                                "SCOPE_orders.write"
                                        .equals(a.getAuthority()));

                if (hasWriteScope) {
                    mapped.add(new SimpleGrantedAuthority(
                            "PERM_orders.create"));
                }

                return new DefaultOAuth2AuthenticatedPrincipal(
                        principal.getName(),
                        principal.getAttributes(),
                        mapped);
            });
}
~~~

This illustrates a Spring Security version with the **SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri** builder. Secrets must be provisioned via a secret manager and validated at startup; never hardcode real credentials.

Safety assumptions:

1. **Delegate** already introspected the token via a trusted AS.
2. **SCOPE_orders.write** is a scope with stable semantics per the issuer contract.
3. Mapping to **PERM_orders.create** is approved by domain security policy.
4. Existing authorities are preserved; only explicitly defined permissions are added.
5. The domain still checks tenant/ownership and live state.
6. Errors from the delegate are preserved—never converted into success.

### Never Automatically Map Arbitrary Role Attributes to ADMIN

If the AS returns roles=["ADMIN"], do not map it to ROLE_ADMIN merely because the names match. You must verify issuer, client/actor kind, claim ownership, and AS semantics. A client-controlled claim or one lacking a trust contract must never elevate internal privileges.

### Never Turn Network Errors into a Default Principal

Wrong:

~~~java
return delegate.introspect(token)
        .onErrorReturn(defaultAuthenticatedPrincipal);
~~~

On AS 401/timeout or an inactive token, identity is unconfirmed. Always fail closed.

## 20. ReactiveOpaqueTokenAuthenticationConverter Differs from the Inbound Bearer Converter

Spring Security has two easily confused converters:

| Converter | Input | Output | Timing |
|---|---|---|---|
| **ServerBearerTokenAuthenticationConverter** | ServerWebExchange | Unauthenticated BearerTokenAuthenticationToken | Before introspection |
| **ReactiveOpaqueTokenAuthenticationConverter** | Raw token + OAuth2AuthenticatedPrincipal | Authenticated Mono<Authentication> | After successful introspection |

ReactiveOpaqueTokenAuthenticationConverter has the conceptual signature:

~~~java
Mono<Authentication> convert(
        String introspectedToken,
        OAuth2AuthenticatedPrincipal authenticatedPrincipal);
~~~

It is invoked by OpaqueTokenReactiveAuthenticationManager. When an application wants to replace the default BearerTokenAuthentication or map authorities at the Authentication level, it can customize this extension point per framework version.

**However, most applications do not need a custom Authentication type.** An OpaqueTokenIntrospector decorator is cleaner when you only need to enrich authorities from a trusted introspection response.

When customizing the authentication converter, preserve the semantics of verified OAuth2AccessToken, authorities, and authentication state. Newer versions may add factor-related authorities; a custom converter must not accidentally drop framework security invariants.

## 21. Method Security After Introspection

A method-level rule:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

public class OrdersService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<Order> readOrder(String id) {
        return repository.findById(id);
    }
}
~~~

This is an illustrative fragment; **Order** and **repository** are application types/objects. Enable reactive method security properly and use reactive return types so the interceptor can enforce the policy.

**PreAuthorize does not trigger introspection itself.** It reads the Authentication already placed in the reactive context by the pipeline. If the token is inactive, no successful authentication is created.

### Scope Alone Is Insufficient for Object-Level Policy

A user holding SCOPE_orders.read may still be forbidden from viewing another tenant's order. Policy may look like:

~~~text
Authenticated
AND hasAuthority("SCOPE_orders.read")
AND order.tenantId == authorizedTenantForPrincipal
AND currentMembershipAllowsRead
~~~

These checks belong to authorization; do not cram everything into OpaqueTokenIntrospector, especially when checks depend on order state in the database.

## 22. Missing Claims and Wrong Data Types

If introspection returns:

~~~json
{
  "active": true,
  "client_id": "shop-web",
  "scope": "orders.read"
}
~~~

while the endpoint requires a user subject, establish an explicit policy: is missing sub a token-contract/actor-type error, or is the endpoint restricted to service clients?

Never do:

~~~text
Missing sub -> use "anonymous" as subject
Missing tenant -> allow access to a default tenant
Unknown role -> grant ROLE_USER with broad default privileges
~~~

That leads to identity confusion or unauthorized access.

### Avoiding ClassCastException

Never assume scope is always a String:

~~~java
Object scopeValue = principal.getAttributes().get("scope");

if (scopeValue instanceof List<?> scopes) {
    // Validate elements and schema per contract.
}
~~~

For permission checks, inspect authorities:

~~~java
boolean mayRead =
        authentication.getAuthorities().stream()
                .anyMatch(a ->
                        "SCOPE_orders.read".equals(a.getAuthority()));
~~~

Timestamp fields may be Instant after normalization, not necessarily Long. Audience fields may be collections. Know the actual Java types before casting.

## 23. When Is a Principal Trustworthy?

OAuth2AuthenticatedPrincipal is a Java interface that any code can construct manually. **Trust comes from the process that produced it**, not the interface name.

A principal used to build an Authentication should satisfy:

1. The token came from an authorized credential source.
2. The introspection URI/store belongs to the application's trust domain.
3. The RS holds valid client credentials and enforces TLS certificate validation.
4. A valid response reported active=true.
5. Token type and resource binding match API requirements.
6. Subject/client/issuer/tenant attributes are validated per contract.
7. Authorities are mapped strictly from trusted claims per policy.
8. Multi-issuer names never collide across namespaces.
9. AS unavailability never yields a default principal.
10. Caching does not defeat revocation or freshness policies.

A custom introspector can be valid if it verifies tokens against a local trusted token store instead of an HTTP AS, provided it enforces the equivalent security contract.

## 24. Secret Handling: BearerTokenAuthentication Is Not an API Response

A Bearer token is a replayable credential. BearerTokenAuthentication holds a verified OAuth2AccessToken, which **never means you may expose getToken().getTokenValue() to browsers or logs**.

Never log:

- Raw Authorization headers.
- Introspection form body tokens.
- Client ID/secret combined into a Basic header.
- Full principal attributes containing PII, tenant secrets, or domain metadata.
- Authentication.toString() unless you know sensitive fields are redacted.
- Raw tokens as correlation IDs or metric labels.

Instead, log/record:

~~~text
requestId
configuredIssuerId
principalKind USER/CLIENT
introspectionOutcome active/inactive/auth_error/network_error
authenticationType
grantedAuthorityCount
httpStatus
latency
~~~

Unverified inputs must never be treated as trusted facts or unbounded metric labels.

## 25. Principal Caching and Revocation Risk

A cache can store OAuth2AuthenticatedPrincipal to reduce HTTP introspection calls:

~~~text
T0 AS returns active=true, scope=orders.write.
T1 RS caches result for 60 seconds.
T2 AS revokes token.
T3 RS may continue seeing the cached principal until TTL expires.
~~~

Specify:

- TTL bounded by access token exp and revocation SLA.
- Cache keys partitioned by issuer, introspection endpoint, and resource context.
- Never cache timeouts or AS 401s as active=false.
- Never cache a principal by sub and reuse it for all of the user's tokens.
- Never serve expired cached principals during an AS outage unless trust policy explicitly permits stale positives within a bounded window.
- Bound cache size to resist token-flooding.

**Principal caching is not merely a performance optimization; it directly governs the effective lag of revocations and privilege changes.**

## 26. Reactive I/O and Safe Error Handling

In WebFlux, avoid:

~~~java
// Do not block inside the reactive event loop.
OAuth2AuthenticatedPrincipal principal =
        delegate.introspect(token).block();
~~~

Use reactive composition:

~~~java
return delegate.introspect(token)
        .map(principal -> adaptPrincipal(principal));
~~~

If querying live permissions from a database is required, use reactive data access or framework-supported blocking I/O offloading—never bury event-loop-blocking code inside `map`.

### Retrying on Introspection Failures

| AS Status | Should you retry? |
|---|---|
| 200 active=false | Never retry hoping the token becomes active |
| 401 invalid_client | Never retry indefinitely with the same secret |
| 403 missing introspection permission | Fix IAM/configuration |
| 400 invalid_request | Fix request/protocol |
| 429 rate limit | Bounded backoff, respect quota |
| 502/503/504 | Limited retries acceptable |
| DNS/connect/read timeout | Limited retries within deadline |
| TLS certificate validation failure | Fix truststore/cert; never disable TLS |

An error on the RS -> AS hop **must never turn into a successful OAuth2AuthenticatedPrincipal**. Fail closed is the baseline requirement.

## 27. Unit Testing BearerTokenAuthentication Structure

This test verifies Java structure only and performs no HTTP introspection:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

class BearerAuthenticationStructureTest {

    @Test
    void exposesPrincipalAttributesAndAuthorities() {
        OAuth2AuthenticatedPrincipal principal =
                new DefaultOAuth2AuthenticatedPrincipal(
                        "user-42",
                        Map.of("sub", "user-42",
                               "client_id", "shop-web"),
                        List.of(new SimpleGrantedAuthority(
                                "SCOPE_orders.read")));

        Instant now = Instant.now();

        OAuth2AccessToken credential =
                new OAuth2AccessToken(
                        OAuth2AccessToken.TokenType.BEARER,
                        "synthetic-test-token",
                        now,
                        now.plusSeconds(300),
                        Set.of("orders.read"));

        BearerTokenAuthentication auth =
                new BearerTokenAuthentication(
                        principal, credential, principal.getAuthorities());

        assertThat(auth.isAuthenticated()).isTrue();
        assertThat(auth.getPrincipal()).isSameAs(principal);
        assertThat(auth.getName()).isEqualTo("user-42");
        assertThat(auth.getTokenAttributes().get("sub"))
                .isEqualTo("user-42");
        assertThat(auth.getAuthorities())
                .extracting("authority")
                .contains("SCOPE_orders.read");
    }
}
~~~

**Never cite this test as proof that a raw token passed introspection.** It builds the principal and Authentication manually. Real integration tests must still verify active=false, AS credentials, network errors, scope mapping, and the WebFlux SecurityWebFilterChain.

## 28. Reactive Introspection Test Matrix

These are **design expectations**, not test execution results:

| AS Stub / Input | Resource Server Expectation |
|---|---|
| HTTP 200 active=true, scope=orders.read | Builds OAuth2AuthenticatedPrincipal/BearerTokenAuthentication |
| HTTP 200 active=true, missing orders.write | GET may pass; POST typically returns 403 |
| HTTP 200 active=false | Unauthenticated, typically 401 |
| HTTP 200 malformed JSON | Fail closed, protocol error |
| HTTP 401 invalid_client | Do not conclude user token invalid; dependency/config failure |
| HTTP 403 from AS | Do not conclude user lacks OAuth scope |
| HTTP 429/503 | Fail closed, bounded retry/circuit breaker |
| DNS/TLS/timeout | Fail closed, preserve network root cause |
| Missing sub on user endpoint requiring sub | Reject per token/actor contract |
| client_credentials without sub | Apply machine-actor policy; do not fake a user |
| scope normalized as List | Authority mapping works |
| Provider-specific roles | Do not auto-map ROLE_ADMIN |
| Principal has SCOPE_orders.read | Authentication carries authority for authorization |
| Active principal, wrong audience | Reject if audience/resource binding is required |
| Active principal, tenant mismatch | Domain authorization denies |
| Multi-issuer with identical sub | Never mix identities |
| Cached active result stale after revocation | Behavior matches TTL/invalidation policy |

Separate the tiers:

1. **Principal object/mapping unit tests**: DefaultOAuth2AuthenticatedPrincipal and BearerTokenAuthentication.
2. **Introspection contract tests**: HTTP stub for RFC 7662, active, attributes, credentials, and errors.
3. **WebFlux SecurityWebFilterChain tests**: Bearer filter, manager, 401/403, WWW-Authenticate, and authorities.
4. **Domain authorization tests**: tenant/ownership/actor kind and live permissions.

Spring Security Test **mockOpaqueToken()** is convenient for authorization tests, yet it creates a mock authentication without calling a real AS; never use it as proof that HTTP introspection works.

## 29. Common Debugging Issues

### Why Is the Principal Not a Jwt?

Because the application is configured as an **opaque-token Resource Server**. The default principal is OAuth2AuthenticatedPrincipal inside BearerTokenAuthentication. Casting it to Jwt in a controller throws a type error. Use the right abstraction or normalize to a domain identity after authentication.

### Why Does getName Not Equal Username?

The AS may define sub differently from username, or the token may be client_credentials. Never treat getName as an email or global user key without an explicit contract.

### Why Is the Scope Attribute Present Yet hasAuthority Returns False?

The scope may have been normalized to a List, a custom mapper mishandled types, a converter changed the SCOPE_ prefix, the policy checked ROLE_ instead of SCOPE_, or a different SecurityWebFilterChain matched. Inspect **Authentication.getAuthorities()**, not just the raw scope attribute.

### Why Is the Principal Missing sub?

The token may be client_credentials, or the AS omitted subject. User endpoints need a required-sub policy; M2M endpoints need their own actor contract.

### Why Does getTokenAttributes Differ from Verbatim JSON?

The introspection implementation may normalize scope, exp, iat, aud, and Java types. Custom decorators can also alter attributes. Never assume wire JSON types equal Java types.

### Why Do All Tokens Suddenly Return 401 After Deployment?

The RS introspection client secret or endpoint may be misconfigured. An AS HTTP 401 invalid_client **does not prove** all user tokens are inactive. Distinguish upstream status from client-facing status.

### Why Does an Active Token Still Get 403?

It may lack the required scope, tenant membership, ownership, or live permissions. active=true only establishes token validity, not domain authorization.

## 30. Common Anti-Patterns

| Mistake | Problem | Correct approach |
|---|---|---|
| Treating BearerTokenAuthenticationToken as verified Authentication | Token is unverified | Introspect before creating Authentication |
| Building OAuth2AuthenticatedPrincipal from untrusted HTTP headers | Identity spoofing | Use a trusted introspector |
| Creating a default principal when active=false | Fail open | Preserve authentication failure |
| Letting requests through on AS timeout | Token validation bypass | Fail closed |
| Casting opaque principal to Jwt | Wrong type | Use OAuth2AuthenticatedPrincipal |
| Using getName as a global user ID | Collisions across issuers and machine clients | Use issuer + subject/client contract |
| Arbitrarily mapping roles to ROLE_ADMIN | Privilege escalation | Map strictly per trusted issuer |
| Checking scope attribute while ignoring GrantedAuthority | Inconsistent authorization | Check Authentication.getAuthorities |
| Treating active=true as access to every endpoint | Bypasses domain policy | Enforce scope + tenant + ownership |
| Skipping audience/resource binding | Tokens for other APIs accepted | Validate token contract |
| Returning all principal attributes to the browser | Leaks metadata/PII | Project into a selective DTO |
| Logging access token from BearerTokenAuthentication | Credential exposure | Emit sanitized telemetry |
| Relying on ThreadLocal SecurityContext in WebFlux | Broken context propagation | Use ReactiveSecurityContextHolder |
| Calling block() in the request pipeline | Blocks event loop | Compose with Mono/Flux |
| Using a mock introspector in production | Skips AS verification | Keep fakes strictly in unit tests |
| Caching principal by sub, ignoring token/issuer | Mixes sessions/trust domains | Key cache by token and issuer |
| Custom converter drops factor authorities | Alters authentication semantics | Uphold version-specific contract |
| Using Servlet Provider/HttpSecurity in WebFlux | Broken integration | Use reactive manager/ServerHttpSecurity |

## 31. Summary

~~~text
Client Bearer opaque token
          |
          v
ReactiveOpaqueTokenIntrospector
  trusted active=true response
          |
          v
OAuth2AuthenticatedPrincipal
  - getName()
  - getAttributes()
  - getAuthorities()
          |
          v
OpaqueTokenReactiveAuthenticationManager
  + ReactiveOpaqueTokenAuthenticationConverter
          |
          v
BearerTokenAuthentication
  - OAuth2AuthenticatedPrincipal principal
  - verified OAuth2AccessToken
  - authorities
  - token attributes
          |
          v
ReactiveSecurityContextHolder
          |
          v
Scope / tenant / business authorization
~~~

Key principles:

1. **ReactiveOpaqueTokenIntrospector returns OAuth2AuthenticatedPrincipal after successful introspection**, not an Authentication result.
2. **OpaqueTokenReactiveAuthenticationManager** creates the Authentication—by default **BearerTokenAuthentication**—via the configured converter.
3. **BearerTokenAuthenticationToken is an unauthenticated request**, distinct from the authenticated BearerTokenAuthentication.
4. **Attributes differ from authorities**; scopes are typically mapped to SCOPE_ authorities.
5. **getName, sub, and client_id have distinct semantics**; distinguish user tokens from machine-client tokens.
6. **In WebFlux, use @AuthenticationPrincipal or ReactiveSecurityContextHolder** to read the trusted principal without blocking.
7. **Never turn active=false or an AS outage into a valid principal**; always fail closed.
8. **An active token is not enough to authorize an action**; check audience, scopes, tenant, and domain policy.
9. **Bearer tokens and introspection credentials are secrets**; never log or return them in responses.
10. **Separate principal unit tests, introspection contract tests, and SecurityWebFilterChain integration tests**.

**Conclusion:** In a WebFlux opaque-token Resource Server, OAuth2AuthenticatedPrincipal represents the verified identity and attributes from trusted introspection; BearerTokenAuthentication is the Authentication wrapping that principal alongside the verified access token and authorities. Understanding both types enables safe mapping extensions while maintaining a clear boundary between authentication and authorization.

## 32. References

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token:** introspection, principal, BearerTokenAuthentication, authority mapping, and custom introspectors. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security API — OAuth2AuthenticatedPrincipal:** name, attributes, and authorities. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html
- **Spring Security API — DefaultOAuth2AuthenticatedPrincipal:** implementation and constructors. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html
- **Spring Security API — BearerTokenAuthentication:** principal, OAuth2AccessToken, and getTokenAttributes. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html
- **Spring Security API — BearerTokenAuthenticationToken:** Bearer authentication request. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthenticationToken.html
- **Spring Security API — ReactiveOpaqueTokenIntrospector:** Mono<OAuth2AuthenticatedPrincipal>. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- **Spring Security API — SpringReactiveOpaqueTokenIntrospector:** AS introspection client. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html
- **Spring Security API — OpaqueTokenReactiveAuthenticationManager:** reactive opaque Authentication manager. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html
- **Spring Security API — ReactiveOpaqueTokenAuthenticationConverter:** converts a principal into Authentication. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenAuthenticationConverter.html
- **Spring Security Reference — WebFlux Security:** SecurityWebFilterChain/ServerHttpSecurity. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security Reference — Reactive Method Security:** @EnableReactiveMethodSecurity and @PreAuthorize. https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- **RFC 7662 — OAuth 2.0 Token Introspection:** active and metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer credentials and HTTP errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — OAuth 2.0 Framework:** OAuth clients, scopes, and access tokens. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7519 — JWT:** comparing JWT claims with opaque introspection attributes. https://www.rfc-editor.org/rfc/rfc7519
