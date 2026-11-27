# `htm`, `htu`, and Binding Proofs to the Request Method and Target URI

**DPoP (Demonstrating Proof of Possession)** is an OAuth 2.0 mechanism that binds an access token to a client's public key. When calling an API, the client sends the access token together with a **DPoP proof JWT** signed with the corresponding private key. The Resource Server verifies the proof, checks that the access token is bound to that same public key, and matches the proof against the current HTTP request.

The two claims that bind a proof to a specific request are:

- **htm**: the HTTP method of the request, e.g., GET, POST, PATCH, or DELETE.
- **htu**: the HTTP target URI of the request, excluding the query string and fragment.

Because of these two claims, a proof signed for a GET request to one URI cannot be arbitrarily reused for a POST request or a different endpoint. However, DPoP does not sign the entire HTTP message: query strings, bodies, and most headers are not covered by `htm`/`htu`. Understanding that boundary accurately—especially when reverse proxies and URL rewriting are involved—is essential to implementing DPoP correctly.

This lesson focuses on **RFC 9449**, how servers match `htm`/`htu`, URI normalization rules, proxy scenarios, the limits of method/URI binding, and how to configure and test with Spring Security.

## 1. How Does a DPoP Proof Bind to a Request?

A standard Bearer access token can be used by any party holding the token. DPoP adds proof of private key possession: the token is bound by the Authorization Server to a public key, and the client must generate a fresh proof for the request.

Overall flow:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof and public JWK
    AS-->>C: Access token token_type=DPoP, key binding
    C->>RS: Authorization: DPoP access-token
    C->>RS: DPoP: proof JWT for current request
    RS->>RS: Verify proof signature and claims
    RS->>RS: Match htm against HTTP method
    RS->>RS: Match htu against request URI
    RS->>RS: Check ath, cnf.jkt, iat, jti, nonce
    RS->>RS: Validate access token and authorization
    RS-->>C: Allow or deny
~~~

The DPoP proof proves the client holds the private key corresponding to the public key in the proof. The Authorization Server binds the access token to that public key. When the Resource Server receives a request, it must confirm that both the proof and the access token reference the same key.

**DPoP does not replace access tokens or authorization.** Even a proof with a valid signature does not grant permission to read orders, delete accounts, or access a tenant. The Resource Server must still verify the access token, issuer, audience, scopes, and domain policies.

## 2. Structure of a DPoP Proof JWT

Per RFC 9449, the DPoP proof is sent in an HTTP header named **DPoP**. The header value is a JWT signed with the client's private key.

Minimal JOSE header:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "public-coordinate-x",
    "y": "public-coordinate-y"
  }
}
~~~

Key fields:

| Field | Meaning |
|---|---|
| typ | Must be dpop+jwt |
| alg | Supported and permitted asymmetric signing algorithm |
| jwk | Client's public JWK; must not contain private keys |

The proof payload for a protected resource request has the form:

~~~json
{
  "jti": "unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.com/v1/orders/42",
  "iat": 1893452400,
  "ath": "base64url-sha256-of-access-token"
}
~~~

| Claim | Meaning |
|---|---|
| **jti** | Unique ID of the proof, used to help detect replay |
| **htm** | HTTP method of the request |
| **htu** | HTTP target URI, omitting query and fragment |
| **iat** | Proof creation timestamp |
| **ath** | Base64url-encoded SHA-256 hash of the access token; required when the proof accompanies an access token to a protected resource |
| **nonce** | Nonce supplied by the Authorization Server or Resource Server, if required by the server |

A fresh proof must be generated for each HTTP request. Never reuse a proof JWT across multiple API calls, even when requests share the same method and URI.

### 2.1. The Access Token Must Also Be Bound to the Key

For JWT access tokens, key confirmation is typically represented via the `cnf.jkt` claim:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": ["orders-api"],
  "sub": "user-123",
  "scope": "orders.read",
  "cnf": {
    "jkt": "SHA-256-JWK-thumbprint"
  }
}
~~~

**jkt** is the JWK SHA-256 thumbprint of the public key used to sign the DPoP proof.

The Resource Server must verify:

1. The proof signature is valid against the public JWK in the proof.
2. The public key in the proof has a thumbprint matching `cnf.jkt` in the access token.
3. `ath` matches the hash of the access token sent in the request.

If using opaque access tokens, key-binding info can be supplied via the introspection response as agreed and supported by the Authorization Server/Resource Server.

### 2.2. HTTP Headers of a Protected Resource Request

A typical DPoP request:

~~~http
GET /v1/orders/42?expand=items HTTP/1.1
Host: api.example.com
Authorization: DPoP <dpop-bound-access-token>
DPoP: <signed-dpop-proof-jwt>
~~~

There are two headers with distinct roles:

- `Authorization` uses the **DPoP** scheme and carries the key-bound access token.
- `DPoP` carries the proof JWT created for the current request.

For a protected resource request, sending only a Bearer token and a DPoP proof without following the proper scheme/contract does not constitute a valid DPoP request.

## 3. The `htm` Claim: Binding the HTTP Method

**htm** is the HTTP method of the request to which the proof is attached. The Resource Server must match this claim against the current HTTP request's method.

Example proof:

~~~json
{
  "htm": "POST",
  "htu": "https://api.example.com/v1/orders",
  "iat": 1893452400,
  "jti": "proof-001"
}
~~~

The proof above was created for the request:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.com
~~~

If the same proof is sent for:

~~~http
DELETE /v1/orders HTTP/1.1
Host: api.example.com
~~~

then the method mismatches. The server must reject the proof.

### 3.1. Same URI with Different Methods Is Still a Different Request

| HTTP request | htm in proof | Match result |
|---|---|---|
| GET /v1/orders/42 | GET | Matches |
| POST /v1/orders/42 | GET | Mismatch |
| PATCH /v1/orders/42 | PATCH | Matches |
| DELETE /v1/orders/42 | PATCH | Mismatch |
| OPTIONS /v1/orders/42 | GET | Mismatch |

One URI can serve multiple operations by method. DPoP uses `htm` to distinguish those operations.

### 3.2. Matching Methods per HTTP Semantics

HTTP methods are case-sensitive tokens under HTTP semantics. Standard clients send standard methods like GET, POST, PUT, PATCH, and DELETE in uppercase and should set `htm` to match the actual method.

Do not arbitrarily transform one method into another to force a proof to "match." For custom HTTP methods, the client and server must agree on the exact method sent and match that exact value.

### 3.3. Method Overrides Can Break the `htm` Boundary

Some applications support mechanisms such as:

~~~http
POST /v1/orders/42 HTTP/1.1
X-HTTP-Method-Override: DELETE
~~~

or a form parameter:

~~~text
_method=DELETE
~~~

At the HTTP layer, the request is still **POST**. If middleware later rewrites the method to DELETE before the controller handles it, the DPoP proof only bound the POST method on the wire; it did not sign the effective method synthesized afterward by the application.

This matters because a proof JWT does not sign the full request body or headers. An override parameter can change the business meaning without changing `htm`.

For DPoP-protected APIs, the simplest and most controllable approach is **not to use method overrides**. If the system strictly requires such a mechanism, you must design an additional request binding understood by both client and server; never assume `htm` protects the post-middleware rewritten method.

## 4. The `htu` Claim: Binding the HTTP Target URI

**htu** is the HTTP target URI of the request, **excluding the query string and fragment**.

For example, the client calls:

~~~http
GET /v1/orders/42?expand=items&locale=vi HTTP/1.1
Host: api.example.com
~~~

The `htu` value in the proof is:

~~~text
https://api.example.com/v1/orders/42
~~~

Not:

~~~text
https://api.example.com/v1/orders/42?expand=items&locale=vi
~~~

Fragments such as `#details` are also omitted from `htu`. Fragments are client-side components and are normally not sent in HTTP requests.

### 4.1. Which Parts of the URI Are Bound?

An absolute URI can be viewed in terms of its components:

~~~text
scheme://host[:port]/path?query#fragment
~~~

For `htu`, the significant parts are:

- **scheme**: http or https.
- **host**: hostname or IP of the resource server.
- **port**: port if required in the URI representation.
- **path**: resource path.

Query and fragment are omitted per RFC 9449.

| Request URL | `htu` Value |
|---|---|
| https://api.example.com/v1/orders/42 | https://api.example.com/v1/orders/42 |
| https://api.example.com/v1/orders/42?expand=items | https://api.example.com/v1/orders/42 |
| https://api.example.com/v1/orders/42?locale=vi | https://api.example.com/v1/orders/42 |
| https://api.example.com/v1/orders/42#details | https://api.example.com/v1/orders/42 |

Because queries are stripped, the first three requests share the same `htu`. This is by DPoP's design, not a parser bug.

### 4.2. Differing Scheme, Host, Port, or Path Means a Different URI

The following cases normally mismatch a proof whose `htu` is `https://api.example.com/v1/orders/42`:

| Request URI | Difference |
|---|---|
| http://api.example.com/v1/orders/42 | Scheme |
| https://other.example.com/v1/orders/42 | Host |
| https://api.example.com:8443/v1/orders/42 | Port |
| https://api.example.com/v2/orders/42 | Path |
| https://api.example.com/v1/orders/43 | Resource path |

The server must compare `htu` against the actual request URI after applying the required normalization rules.

### 4.3. Queries Are Not Signed

Because the query string is excluded from `htu`, a proof does not distinguish:

~~~text
/v1/orders/42?view=summary
/v1/orders/42?view=full
/v1/orders/42?operation=export
~~~

If the query only controls presentation or filtering on data whose access permissions are checked separately, this may be an acceptable limit. However, if a query parameter triggers a sensitive action, **never treat DPoP `htu` as a signature protecting that parameter**.

Similarly, basic DPoP does not sign the request body or all HTTP headers. If an operation depends on body data, DPoP does not prove that body was signed by the client.

For broader integrity requirements, a separate request-signing protocol or contract-defined extension between client and server is required. Do not invent arbitrary custom claims and assume other DPoP implementations will interpret them the same way.

## 5. Normalizing URIs Before Comparing `htu`

RFC 9449 recommends that Resource Servers apply:

- **Syntax-based normalization** per RFC 3986, Section 6.2.2.
- **Scheme-based normalization** per RFC 3986, Section 6.2.3.

The goal is to avoid falsely rejecting syntactically or scheme-equivalent URIs.

Examples of differences that can occur:

~~~text
HTTPS://API.EXAMPLE.COM:443/v1/orders/42
https://api.example.com/v1/orders/42
~~~

Scheme/host can be lowercased; default ports and equivalent URI forms are handled according to proper normalization rules.

### 5.1. Never Write an Ad-Hoc String Comparison

A strict byte-for-byte string comparison can reject equivalent URIs. Conversely, overly broad normalization can collapse two distinct resources into one.

Common mistakes:

- Lowercasing the entire path, even though paths can be case-sensitive.
- Stripping all trailing slashes without considering route semantics.
- Arbitrarily decoding all percent-encoded characters.
- Sorting or filtering query parameters and including them in `htu`.
- Treating two different host aliases as the same resource without a policy.
- Replacing `https` with `http` simply because the backend receives internal traffic over HTTP.
- Dropping different ports even when they represent two distinct public endpoints.

Use standard-compliant URI parsing/normalization, preserving meaningful differences while omitting query/fragment per the DPoP specification. Never use a "lowercase the whole URL" function as a canonicalizer.

### 5.2. Percent-Encoding and Path Segments

URIs may represent certain characters using percent-encoding. RFC 3986 specifies how to normalize equivalent forms, including encoding of unreserved characters and dot-segment resolution during normalization.

Never decode reserved characters such as path separators just because they are percent-encoded. Apply proper syntax-based normalization rules and test with the exact URIs handled by your reverse proxy, servlet container, and router.

For example, the server must not assume every decoded path carries the same meaning as the original path. Differences involving encoded slashes, path traversal, duplicate slashes, and route normalization must be handled consistently across the ingress and application.

## 6. Reverse Proxies: Client-Seen URI vs. Backend-Seen URI

This is one of the most common causes of DPoP `htu` mismatches.

Suppose the client calls the public endpoint:

~~~text
https://api.example.com/v1/orders/42
~~~

The gateway forwards to the backend:

~~~text
http://orders-service.internal:8080/orders/42
~~~

The client creates the proof with:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/v1/orders/42"
}
~~~

Yet the Servlet backend may observe:

~~~text
http://orders-service.internal:8080/orders/42
~~~

If the Resource Server compares this internal URI directly against `htu`, a valid proof from the client's perspective will be rejected.

### 6.1. You Must Determine the Trusted Public Request URI

The Resource Server must compare `htu` against the URI of the request the client actually sent to the protected resource. In deployments behind a reverse proxy, the application must have a reliable way to reconstruct the public scheme, host, port, and path.

Typically relevant headers/metadata:

- `Forwarded` header per RFC 7239.
- `X-Forwarded-Proto`.
- `X-Forwarded-Host`.
- `X-Forwarded-Port`.
- `X-Forwarded-Prefix` or gateway-managed path rewrites.

Not all proxies use the same headers or rewriting behavior. Clearly define the public URL and backend URL in your architecture.

### 6.2. Trust Forwarded Headers Only from Managed Proxies

`Forwarded`/`X-Forwarded-*` headers can be forged by clients if the edge proxy does not strip them. If the application blindly trusts an attacker-supplied value, the attacker can manipulate the scheme/host/port/path used to verify `htu`.

Deployment rules:

1. The edge proxy must strip or overwrite forwarded headers coming from external clients.
2. Only trusted proxies/gateways may supply URI forwarding metadata.
3. The backend must trust forwarded headers only from configured proxy sources.
4. Never let clients dictate the `Host` or public prefix used in DPoP comparisons.
5. Test traffic through the real proxy path, not only by calling the backend directly.

### 6.3. Spring Support for Handling Forwarded Requests

In the Servlet stack, Spring provides **ForwardedHeaderFilter**. In WebFlux, it provides **ForwardedHeaderTransformer**. These adjust how the application sees the scheme, host, and request URI from forwarded headers.

However, enabling the filter/transformer **does not make forwarded headers trustworthy on its own**. The proxy trust boundary must be established first. If the backend is directly reachable from the Internet, never assume every forwarded header originated from the gateway.

### 6.4. Path Rewriting Requires a Clear Contract

If the public route is:

~~~text
/v1/orders/42
~~~

but the proxy rewrites it to:

~~~text
/orders/42
~~~

then the Resource Server must know the corresponding public path in order to match `htu`. You cannot simply compare the backend path against the client's proof.

Three common architectural approaches:

- The proxy preserves the public path when forwarding.
- The backend receives the forwarded prefix/path from a trusted proxy and the framework reconstructs the public URI.
- The application maintains an explicit, managed public mapping to translate backend requests back to public URIs.

Whichever option is chosen, client and server must arrive at the same URI representation after normalization. Never infer the public path from an arbitrary header.

## 7. What Does DPoP Check and What Does It Not Check?

When a Resource Server receives a DPoP proof, RFC 9449 requires checking multiple conditions. `htm` and `htu` are only two of them.

| Check | Purpose |
|---|---|
| Only one DPoP header | Avoid ambiguous multiple proofs |
| Proof is a valid JWT | Ensure proper structure and signature |
| `typ` = `dpop+jwt` | Identify proof type |
| Permitted asymmetric `alg` | Prevent `none` / unsuitable symmetric algorithms |
| JWK contains only public key | Never accept private keys from clients |
| Valid signature | Prove private-key possession |
| `htm` matches method | Bind method |
| `htu` matches request URI | Bind endpoint |
| `iat` within allowed time window | Bound proof age |
| `jti` has not been used | Mitigate replay |
| `nonce` matches if required by server | Strengthen replay resistance |
| `ath` matches access token | Tie proof to the token being sent |
| `cnf.jkt` matches proof key | Tie access token to the same public key |

### 7.1. `ath` Does Not Replace `htm`/`htu`

`ath` is the hash of the access token. It ties the proof to the specific token being presented.

However, checking only `ath` without checking `htm`/`htu` leaves the proof unbound to the exact request method and URI. The RFC requires all of these checks together.

### 7.2. `jti` and Replay Detection

A proof has a unique `jti` and an `iat` within a short time window. The server can store used `jti` values to prevent a proof from being submitted multiple times.

A proof created for `GET /orders/42` could still be replayed to the exact same endpoint and method if an attacker steals the entire proof while it is still valid. `htm`/`htu` prevent moving the proof to another endpoint/method; **the `jti` replay cache and time window** help prevent reusing the proof at the same endpoint.

With multiple Resource Server instances, a per-node local replay cache does not guarantee detecting a proof sent first to node A and second to node B. If cluster-wide replay prevention is required, a shared cache/state or proper synchronization mechanism is needed.

Spring Security provides **DPoPProofReplayValidator** with a cache to check used `jti` values and `iat` timestamps. Configure the cache/lifecycle to fit your architecture. An in-memory cache on one instance does not automatically protect other replicas.

### 7.3. Nonce

The Authorization Server or Resource Server can return a **DPoP-Nonce** header. The client must include that recent nonce in the `nonce` claim of its next proof.

Nonces allow the server to require proofs bound to a recent challenge, improving replay defense in appropriate scenarios. Clients do not invent security-meaningful nonces in place of the server.

## 8. Example of Matching `htm` and `htu`

Suppose the client calls:

~~~http
PATCH /v1/orders/42?notify=true HTTP/1.1
Host: api.example.com
Authorization: DPoP <access-token>
DPoP: <proof>
~~~

Signed proof payload:

~~~json
{
  "jti": "a7f2f4c9-0d20-4d3f-a8e3-4f5e6d7c8b9a",
  "htm": "PATCH",
  "htu": "https://api.example.com/v1/orders/42",
  "iat": 1893452400,
  "ath": "base64url-sha256-of-access-token"
}
~~~

The server performs:

1. Actual method is PATCH, `htm` is PATCH: match.
2. Public URI after normalization is `https://api.example.com/v1/orders/42`: match.
3. Query `notify=true` is ignored in the `htu` comparison per RFC.
4. Proof signature, key binding, `ath`, `iat`, `jti`, and `nonce` are checked per policy.
5. The access token is verified.
6. Authorization checks scopes and permission to modify the order.

If the request changes to:

~~~http
DELETE /v1/orders/42?notify=true HTTP/1.1
Host: api.example.com
~~~

then `htm` mismatches. If the request changes to:

~~~http
PATCH /v1/orders/43?notify=true HTTP/1.1
Host: api.example.com
~~~

then `htu` mismatches.

If the query changes to `notify=false` while method/path remain the same, `htm`/`htu` still match. This is an intentional design limit of DPoP; if a query controls a sensitive action, protect those semantics at another layer.

## 9. How Does Spring Security Support DPoP?

Spring Security provides DPoP components in modern release lines:

- **DPoPAuthenticationToken**: holds the access token, proof, method, and resource URI.
- **DPoPAuthenticationProvider**: authenticates DPoP-bound access tokens.
- **DPoPProofJwtDecoderFactory**: creates decoders for DPoP proofs.
- **DPoPAuthenticationConverter**: extracts the DPoP access token/proof from a Servlet request.
- **DPoPAuthenticationEntryPoint**: generates challenges/errors for DPoP.
- **DPoPProofReplayValidator**: checks `jti`/`iat` using a cache.

Key version differences to remember:

- Several DPoP components such as `DPoPAuthenticationProvider` and `DPoPAuthenticationToken` exist from Spring Security 6.5.
- **DPoPConfigurer** in the OAuth2 Resource Server DSL was added in Spring Security 7.1.
- `DPoPProofReplayValidator` exists from Spring Security 6.5.12.

Do not copy Spring Security 7.1 DSL configuration into a 6.5 project without verifying the API/version.

### 9.1. Configuring Servlet Resource Server with DPoP

Example for Spring Security 7.1 and later:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DPoPSecurityConfiguration {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

This example assumes the application already configures `JwtDecoder`/issuer/audience validators and that the Authorization Server issues **DPoP-bound access tokens**. For opaque tokens, use the corresponding introspection configuration to supply public-key binding info.

The Servlet DPoP configurer can customize the request matcher, authentication converter, success handler, and failure handler. By default, the converter creates a `DPoPAuthenticationToken` from the request; the provider verifies the proof and access token.

### 9.2. Spring Security 6.5

Spring Security 6.5 includes several DPoP building blocks, while the `.dPoP(...)` DSL on `OAuth2ResourceServerConfigurer` is introduced in 7.1. When using 6.5, check the exact API/Javadoc of your minor release and how to wire the provider/converter/entry point. Do not mix 6.5 classes with a configurer that only exists in 7.1.

### 9.3. WebFlux

The `.dPoP(...)` configuration documented here belongs to **Servlet `HttpSecurity`**. WebFlux uses `ServerHttpSecurity` and reactive authentication managers; never copy Servlet DSL directly into `SecurityWebFilterChain`.

If a WebFlux Resource Server needs DPoP, verify official support in your exact release or design an appropriate reactive authentication integration. Never run a blocking Servlet `DPoPAuthenticationProvider` inside the Reactor event loop, and never skip `htm`/`htu` because of the reactive stack.

## 10. URIs and Reverse Proxies in Spring: Configuration Checklist

With Spring MVC behind a reverse proxy, verify:

- The application observes `https` as the public scheme when clients call HTTPS.
- Host/port match the public host/port set by the proxy.
- The path seen by the DPoP converter is the corresponding public path.
- `ForwardedHeaderFilter` processes forwarded headers only from trusted proxies.
- The edge proxy strips client-supplied forwarded headers.
- The `Host` header is never taken from an untrusted source.
- There are no unmapped path rewrites.
- URI normalization follows RFC 3986 properly.

With WebFlux, forwarded-header components have a different API; check the proper WebFlux configuration rather than using a Servlet filter.

### 10.1. Example Public vs. Backend URI

| Attribute | Client Sees | Backend May See |
|---|---|---|
| Scheme | https | http |
| Host | api.example.com | orders-service.internal |
| Port | 443 | 8080 |
| Path | /v1/orders/42 | /orders/42 |
| Query | ?expand=items | May be forwarded or rewritten |

The proof is created using the public URI. The Resource Server needs a trusted request view matching that public URI to compare `htu`.

If the proxy changes the path, preserve the public prefix or maintain an explicit mapping. If the backend cannot reliably reconstruct the URI the client called, adjust your gateway/routing architecture before enabling DPoP.

## 11. Scenarios Likely to Cause Mismatches

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Every proof reports `htu` mismatch behind ingress | Backend sees `http`/internal host | Configure trusted forwarded URI |
| Fails only through gateway | Proxy rewrites path or prefix | Synchronize public path mapping |
| Fails only on HTTPS termination | Backend sees `http` scheme | Trust forwarded proto from managed proxy |
| Some hostname aliases succeed | Client and server pick different hosts | Standardize public hostname |
| Default port causes mismatch | URI represented differently | Apply RFC 3986 scheme normalization |
| Paths with percent-encoding rejected | Client/server normalize differently | Use compatible URI parser and normalization rules |
| POST requests rejected after middleware | Method override alters method | Disable override on DPoP routes or add extra binding |
| Proof works with multiple queries | Query is excluded from `htu` | Do not treat query as DPoP-signed |
| Proof rejected at another node | Replay cache is local-only or clocks differ | Share replay state and synchronize clocks |
| Valid proof, yet token rejected | `ath` or `cnf.jkt` mismatch | Check access token / key binding |

## 12. Testing `htm`/`htu` in the Resource Server

Do not test only one happy-path request. Include positive and negative tests for every binding component.

### 12.1. `htm` Matrix

| Request method | `htm` in proof | Expected Result |
|---|---|---|
| GET | GET | Match |
| POST | POST | Match |
| GET | POST | Reject |
| DELETE | PATCH | Reject |
| OPTIONS | GET | Reject |

Also test custom methods if used by the application.

### 12.2. `htu` Matrix

| Request URI | `htu` in proof | Expected Result |
|---|---|---|
| https://api.example.com/v1/orders/42 | Same URI | Match |
| https://api.example.com/v1/orders/43 | Different path URI | Reject |
| https://other.example.com/v1/orders/42 | Different host | Reject |
| http://api.example.com/v1/orders/42 | Different scheme | Reject |
| https://api.example.com:8443/v1/orders/42 | Different port | Reject |
| Same URI, different query | Same `htu` after stripping query | `htu` still matches |
| Equivalent URI per RFC 3986 normalization | Equivalent URI | Matches per normalization rules |

URI equivalence tests must follow RFC 3986 rather than inventing normalization rules beyond the specification.

### 12.3. Testing Through a Proxy

Use a test environment with a reverse proxy/gateway:

1. The client generates a proof for the public URI.
2. The proxy terminates TLS and forwards to the backend.
3. The backend receives forwarded metadata from the trusted proxy.
4. The Resource Server constructs the appropriate URI.
5. Valid proofs are accepted.
6. Resend the same request with spoofed client-supplied forwarded host/proto headers; the edge must strip/overwrite them so attackers cannot control the `htu` comparison.
7. Test path rewrites and public prefixes.

Tests calling controllers/backends directly are insufficient to prove URI reconstruction works in production.

### 12.4. Testing Query and Body Boundaries

Send two requests with the same method/path but different queries. DPoP `htm`/`htu` will still match because queries are omitted.

This does not mean both requests are permitted to perform the same business action. Tests must prove that the authorization/domain layer still enforces constraints on sensitive query/body parameters.

### 12.5. Testing Replay

- Send a proof with a fresh `jti`: may be accepted.
- Resend the same proof within the valid window: must be caught per replay policy.
- Send the same proof to another node: verify the shared replay cache if running multiple instances.
- Send a proof with an `iat` too old or too far in the future outside clock policy: reject.
- Send a proof missing a nonce when the server requires a nonce: reject and handle the challenge appropriately.

### 12.6. Testing Access Token Binding

Beyond `htm`/`htu`, test:

- `ath` computed over the exact presented access token.
- `cnf.jkt` matching the thumbprint of the proof's public key.
- Tokens cannot be used with the Bearer scheme if issued as DPoP-bound.
- Proofs signed with a different private key are rejected.
- Proof headers containing private JWK material are rejected.
- Non-compliant `typ` or `alg` values are rejected.

Use real test key pairs and test access tokens with genuine bindings; never inject a fake `Authentication` and conclude DPoP has been verified.

## 13. Anti-Patterns to Avoid

**Checking only the proof signature.** A valid signature is not enough; you must check `htm`, `htu`, `iat`, `jti`, `ath`, key binding, and nonces when required.

**Comparing `htu` against the internal backend URL.** The client signs the public URL while the backend compares against the post-proxy hostname/port/path.

**Trusting all `X-Forwarded-*` headers.** Clients can spoof them if the edge does not strip them and the backend does not restrict proxy trust.

**Lowercasing the entire URI.** Paths can be case-sensitive; never apply arbitrary normalization.

**Including the query in `htu`.** RFC 9449 excludes query and fragment from `htu`.

**Assuming DPoP signs the request body.** Basic DPoP does not sign the body or all headers.

**Using method overrides on protected routes.** `htm` binds the HTTP method on the wire, not a method rewritten afterward.

**Reusing proofs.** Each HTTP request needs its own proof and unique `jti`.

**Local-only replay cache in multi-node systems.** A proof can be replayed to another node without shared state.

**Treating DPoP as authorization.** Scopes, audience, tenants, roles, and resource permissions must still be checked.

**Using a DPoP proof as a standalone access token.** The proof proves key possession; the access token still determines OAuth permissions.

## 14. Practical Implementation Workflow

**Step 1 — Confirm the Authorization Server supports DPoP.** Token responses must return `token_type` `DPoP` and bind access tokens to public keys.

**Step 2 — Define public URIs.** Document the exact scheme, host, port, and path seen by clients for each route.

**Step 3 — Audit the reverse proxy.** Identify TLS termination, host forwarding, prefix/path rewrites, and proxy trust boundaries.

**Step 4 — Configure the Resource Server.** Use the DPoP-aware converter/provider/configurer for your exact Spring Security version; verify both access tokens and proofs.

**Step 5 — Verify `htm`.** Ensure method matching checks the real HTTP method, without method overrides altering semantics after DPoP validation.

**Step 6 — Verify `htu`.** Strip query/fragment, apply RFC 3986 syntax-based and scheme-based normalization, and compare against the trusted public request URI.

**Step 7 — Verify key/token binding.** Verify the proof signature, public JWK, `ath`, and `cnf.jkt`.

**Step 8 — Design replay/nonce controls.** Bound proof age, enforce `jti` uniqueness, use a shared cache where needed, and define nonce policy.

**Step 9 — Keep authorization independent.** Check issuer, audience, scopes, tenants, ownership, and domain policies.

**Step 10 — Test end-to-end through ingress.** Test method mismatches, path/host/scheme mismatches, forwarded-header spoofing, query/body boundaries, and multi-instance replay.

## 15. Self-Check Questions

**1. What is `htm`?**

It is the HTTP method of the request to which the DPoP proof is bound. The Resource Server must match it against the current method.

**2. Does `htu` contain the query string?**

No. RFC 9449 requires omitting the query and fragment when creating/comparing `htu`.

**3. Can a proof for `GET /orders/42` be used for `DELETE /orders/42`?**

No. `htm` differs.

**4. Can a proof for `/orders/42` be used when the path changes to `/orders/43`?**

No. `htu` differs.

**5. If the query changes while the method/path stay the same, does `htu` change?**

No. Queries are excluded from `htu`. Important parameters must still be validated in authorization/domain logic.

**6. Does DPoP sign the request body?**

Not in the base mechanism. It binds the method and URI together with the access token/key binding, not the entire HTTP message.

**7. Why can a reverse proxy cause an `htu` mismatch?**

Because the client uses the public scheme/host/path, while the backend may observe an internal scheme/host/path after TLS termination or rewriting.

**8. Should an `X-Forwarded-Host` header sent by a request be trusted?**

Not by default. Trust only forwarded metadata set by managed proxies after the edge strips any client-supplied values.

**9. Starting from which version does Spring Security have the DPoP DSL?**

`DPoPAuthenticationProvider` exists from 6.5; `DPoPConfigurer` on the OAuth2 Resource Server DSL exists from 7.1. Always verify against your exact release line.

**10. Does DPoP replace scope/role authorization?**

No. It proves key possession and binds the proof to the request/token; access permissions are still governed by the access token and authorization policy.

## Conclusion

**`htm` and `htu` are the two claims that bind a DPoP proof to a specific HTTP request.** `htm` must match the actual method; `htu` must match the target URI after stripping query/fragment and applying RFC 3986 URI normalization.

The difference between the client-observed URL and the backend-observed URL behind a reverse proxy is a critical deployment boundary. The Resource Server must reconstruct the public URI strictly from forwarded metadata trusted from managed proxies. If methods are overridden or queries/bodies carry sensitive business meaning, never assume `htm`/`htu` signed the entire request.

In Spring Security, use the right DPoP components and APIs for your version, while also verifying proof signatures, `jti`/`iat`, `ath`, `cnf.jkt`, and nonces when required. **DPoP helps prevent stolen access tokens from being used by parties lacking the private key, but it does not replace authorization, replay protection, or request integrity for bodies and queries.**

### References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP), Section 4.2–4.3](https://www.rfc-editor.org/rfc/rfc9449.html)
- [RFC 9449 — Public Key Confirmation and DPoP-Protected Resource Requests](https://www.rfc-editor.org/rfc/rfc9449.html#section-6)
- [RFC 9449 — DPoP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc9449.html#section-7.1)
- [RFC 9449 — DPoP Proof Replay](https://www.rfc-editor.org/rfc/rfc9449.html#section-11.1)
- [RFC 3986 — URI Generic Syntax, Section 6.2](https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html)
- [Spring Security 7.1 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html)
- [Spring Security API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html)
- [Spring Security API — DPoPProofJwtDecoderFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofJwtDecoderFactory.html)
- [Spring Security API — DPoPProofReplayValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.html)
- [Spring Framework — ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)
