# Authorization: Bearer and the Structure of Token-Bearing HTTP Requests

In OAuth 2.0, a **Resource Server** provides a protected API and only processes requests that satisfy authentication and authorization policies. The most common way for a client to send an **access token** to a Resource Server is by placing the token in an HTTP request header:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

Here, `<ACCESS_TOKEN>` is a **placeholder notation for documentation**, and the `<` and `>` characters must not be sent in an actual request. The client replaces this entire placeholder with the access token string received from the Authorization Server. The value `Bearer` is the **authentication scheme**, and the string that follows is the **credential**.

This lesson explains the header syntax, its position in an HTTP request, how to read GET/POST/HTTP/2 cases, its relationship with JWTs and opaque tokens, 401/403 responses, and how Spring Security Resource Server uses this header in practice.

## 1. Why does a Resource Server need an access token?

In an OAuth 2.0 architecture, clients typically do not send user passwords to an API. After completing an appropriate authorization flow, the client receives an access token from the **Authorization Server** and presents the token when calling the **Resource Server**. The Resource Server validates the token before allowing operations on the resource.

~~~mermaid
sequenceDiagram
    participant U as User / Client
    participant AS as Authorization Server / OIDC Provider
    participant RS as Resource Server (API)
    U->>AS: OAuth 2.0 authorization flow
    AS-->>U: access_token
    U->>RS: GET /api/profile + Authorization: Bearer token
    RS->>RS: Extract token, authenticate, and authorize
    alt Valid and authorized
        RS-->>U: 200 OK + data
    else Missing / invalid token
        RS-->>U: 401 Unauthorized
    else Authenticated but insufficient permissions
        RS-->>U: 403 Forbidden
    end
~~~

An access token is a **credential granting access to resources**, not an account password and not necessarily a JWT. In OpenID Connect (OIDC), the response may also include an **ID token** so the client receives user identity information; an ID token **does not replace an access token** when calling an API. Spring Security OAuth 2.0 Resource Server is configured to validate access tokens appropriate for the API.

## 2. Dissecting the `Authorization: Bearer ...` line

HTTP uses the `Authorization` field for the client to send authentication credentials for the requested resource. With a Bearer token, the standard format is:

~~~text
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9....
└───────────┘  └────┘ └───────────────────────────────────────────┘
 Header name   Scheme                Access token
~~~

| Component | Role | Example |
|---|---|---|
| `Authorization` | Name of the HTTP header carrying the credential | `Authorization` |
| `:` | Separator between header name and value | `:` |
| `Bearer` | Authentication scheme type; tells the server this is a Bearer credential | `Bearer` |
| Space after `Bearer` | Separates the scheme from the token | `Bearer eyJ...` |
| `<ACCESS_TOKEN>` | The actual issued token string | Three-part JWT or opaque token |

The word **Bearer** means that the party **holding the token** can present it to exercise the permissions it carries. A Bearer-type token is not inherently bound to a client's private key or device. Therefore, **token exposure can lead to unauthorized access while the token remains valid**.

### HTTP syntax

Under the HTTP `Authorization` model and RFC 6750 Bearer token transport rules, the header value consists of `Bearer`, at least one space, followed by the token string.

~~~http
Authorization: Bearer abc.def.ghi
~~~

The string `abc.def.ghi` here only illustrates the shape of a JWT. Real tokens do not necessarily contain dots.

Key points to remember:

- HTTP field names are **case-insensitive**: `Authorization` and `authorization` represent the same header under HTTP rules.
- The `Bearer` authentication scheme is also recognized case-insensitively under HTTP authentication rules, though writing `Bearer` consistently is recommended for readability and compatibility.
- After the scheme comes the **raw token value**; do not wrap it in double quotes, do not prepend `Bearer` a second time, and do not include placeholder characters.
- Do not split a token across multiple lines or insert line breaks into the header value. Standard HTTP clients handle header encoding; input data must never allow CR/LF injection.
- Avoid sending multiple transport forms of the same Bearer token simultaneously in one request. For example, setting both `Authorization` and attaching `access_token` in the URL violates the spirit of RFC 6750.

Comparison examples:

~~~text
CORRECT: Authorization: Bearer abc.def.ghi

WRONG:   Authorization: abc.def.ghi
         # Missing the Bearer authentication scheme.

WRONG:   Authorization: Bearer Bearer abc.def.ghi
         # Repeated scheme inside the token value.

WRONG:   Authorization: Bearer "abc.def.ghi"
         # Double quotes are not part of the token.

WRONG:   Authorization: Bearer <ACCESS_TOKEN>
         # If sent literally, this is only a placeholder.
~~~

Note that the `WRONG` lines show errors **relative to the intended token value in the example**, not that all of them produce the same status code or identical parser failures on every server.

## 3. What does an HTTP request with a Bearer token contain?

Consider a GET request to an API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
User-Agent: orders-client/1.0

~~~

This format is an illustrative HTTP/1.1 request. In a real request, the client replaces the placeholder with the access token; the blank line ends the header section. For a GET without a request body, there is no need to add `Content-Type`.

| Line/component | Meaning |
|---|---|
| `GET /api/orders/42 HTTP/1.1` | **Request line**: method, resource path (request target), HTTP version |
| `Host: api.example.test` | Target host; required in HTTP/1.1 |
| `Authorization: Bearer ...` | Credential for the Resource Server to authenticate |
| `Accept: application/json` | Client prefers JSON response format |
| `User-Agent: orders-client/1.0` | HTTP client identification; not proof of authentication |
| Blank line | Boundary between headers and body (if present) |
| Body (depends on method) | Business payload such as JSON; the Bearer token stays in the header |

**The URL path does not contain the Bearer token.** The `?` in a URL query may carry filter or pagination parameters, but should not carry an access token. Putting tokens in query parameters easily exposes them via browser history, proxy/server logs, analytics tools, and URL observability systems.

### POST request with JSON body

The request still uses the `Authorization` header, while adding metadata describing the payload:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
Content-Type: application/json
Content-Length: 21

{"sku":"A42","qty":2}
~~~

Here:

- `Authorization` is used for **authentication**.
- `Content-Type` indicates the **format of the submitted data**.
- `Content-Length: 21` is the illustrative JSON payload size in UTF-8 bytes; HTTP clients usually populate this automatically.
- The body `{"sku":"A42","qty":2}` is **business content**, not a place for credentials.

Not every POST requires a body, and methods like PUT/PATCH can also use the same Authorization header. Bearer tokens are not restricted to `GET` or `POST`: which methods are permitted depends on the **API's authorization rules**, not on the mere presence of the header alone.

## 4. When using HTTPS, how are the URL and headers transmitted?

Example URL:

~~~text
https://api.example.test/api/orders/42
│       │                │
Scheme  Host             Path
~~~

The browser or HTTP client sends the request over a TLS connection to the appropriate server. With HTTPS, the **Authorization header, path, and body** are protected in transit by TLS between TLS termination points. DNS and certain connection metadata may still be observable depending on infrastructure; do not assume TLS hides all metadata.

When the application sits behind a reverse proxy/API gateway:

~~~mermaid
flowchart LR
    A["Client"] -->|"HTTPS + Authorization: Bearer"| B["API Gateway / Reverse Proxy"]
    B -->|"Forward request per config"| C["Spring Security Resource Server"]
    C --> D["Controller / Service"]
~~~

The system must configure the gateway to properly forward credentials to services **authorized to receive the token**. If the gateway strips the `Authorization` header, the Resource Server will see a request without a Bearer token and may return `401`. If the gateway pre-validates the token, it must clearly define which information downstream services trust rather than trusting arbitrary client-supplied headers as identity.

**`Authorization` is not `Proxy-Authorization`**: the latter relates to proxy authentication and does not replace the API's Bearer credential. Across multiple hops, protect inter-service connections and forward tokens only to the intended receiving service.

## 5. What is different in HTTP/2 and HTTP/3?

HTTP/1.1 examples are text-based and easy to read. HTTP/2 and HTTP/3 transmit headers using protocol framing and encoding rather than literal `GET /... HTTP/1.1` request lines. Equivalent information is represented using pseudo-headers:

~~~http
:method: GET
:scheme: https
:authority: api.example.test
:path: /api/orders/42
authorization: Bearer <ACCESS_TOKEN>
accept: application/json
~~~

In HTTP/2 and HTTP/3, header names are **lowercase**, so `authorization` typically appears instead of `Authorization`; the meaning is unchanged. Pseudo-headers `:method`, `:scheme`, `:authority`, `:path` are not arbitrary headers applications can freely add in the usual way. The HTTP library is responsible for constructing valid requests for the connection version.

For Spring developers, **there is no need to write separate token-parsing code per HTTP version**. Spring Security receives header information from the runtime's HTTP abstraction and then performs Bearer token authentication.

## 6. Both JWT and opaque tokens travel in the Bearer header

**The location of the access token in the request does not dictate the token format.** A Resource Server may be configured to validate JWTs or perform introspection on opaque tokens; the client still uses the same syntax:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

### 6.1. JWT access token

A typical signed compact JWT has the form:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

An example payload after decoding its claims might contain:

~~~json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

Sample claims illustrating their purpose:

| Claim | Purpose |
|---|---|
| `iss` | Issuer: the party that issued the token |
| `sub` | Subject: principal identifier |
| `aud` | Audience: the resource/service the token is intended for |
| `exp` | Expiration timestamp |
| `nbf` | Not-before timestamp when the token becomes valid, if present |
| `scope` or `scp` | Scopes/permissions granted by the token |

JWT claims **must not be trusted merely because Base64URL decoding succeeded**. The Resource Server must verify the signature, algorithm, and trusted keys, time validity, issuer, and required audience before using claims for authorization decisions.

### 6.2. Opaque access token

An opaque token can be a random string, for example:

~~~http
Authorization: Bearer tkn_f7a91c2b8e4d6a50
~~~

The Resource Server does not infer permissions or identity from the string's shape. It typically calls the Authorization Server's **OAuth 2.0 token introspection endpoint** and only accepts the token when it is active and satisfies API policy. The snippet `tkn_f7a91c2b8e4d6a50` is also just a dummy token for illustration.

You cannot determine that a token is “secure” merely because it has two dots like a JWT or a `tkn_` prefix. **The contract between the Authorization Server, client, and Resource Server** defines the token format and validation method.

### 6.3. Access token vs. ID token

When using OIDC, a client may receive both an `access_token` and an `id_token`. Their intended usage must stay clear:

| Token | Primary recipient | Purpose |
|---|---|---|
| OAuth 2.0 access token | Resource Server / API | Resource access authorization |
| OIDC ID token | OIDC client (relying party) | Information about the authentication event/identity |
| Refresh token (if issued) | OAuth 2.0 client sent to token endpoint | Requesting new access tokens per Authorization Server policy |

Do not send a refresh token directly to an API as `Authorization: Bearer ...`. Likewise, do not use an ID token as an access token merely because it is formatted as a JWT and contains a `sub` claim.

## 7. Constructing Bearer-token requests from HTTP clients

### 7.1. cURL in the terminal

Assume the `ACCESS_TOKEN` environment variable already holds a real access token; how the variable is populated depends on your shell and token issuance system.

**Bash/Zsh:**

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "https://api.example.test/api/orders/42"
~~~

For a JSON POST:

~~~bash
curl -i \
  -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  --data '{"sku":"A42","qty":2}' \
  "https://api.example.test/api/orders"
~~~

`-i` prints response headers so you can inspect the status and `WWW-Authenticate`. Avoid placing tokens directly in shell history; do not paste output containing real credentials into issue trackers, shared documents, or logs.

**Windows PowerShell:**

~~~powershell
$token = $env:ACCESS_TOKEN
curl.exe -i -H "Authorization: Bearer $token" -H "Accept: application/json" "https://api.example.test/api/orders/42"
~~~

Use `curl.exe` to invoke the cURL binary directly on Windows, avoiding differences from the `curl` alias in some PowerShell versions.

### 7.2. JavaScript `fetch`

~~~javascript
async function getOrder(accessToken, orderId) {
  const response = await fetch(
    "https://api.example.test/api/orders/" + encodeURIComponent(orderId),
    {
      method: "GET",
      headers: {
        "Authorization": "Bearer " + accessToken,
        "Accept": "application/json"
      }
    }
  );

  if (!response.ok) {
    throw new Error("API request failed: HTTP " + response.status);
  }

  return response.json();
}
~~~

This function takes an `accessToken` already obtained through an appropriate OAuth 2.0 flow. The example does **not** describe how to acquire or store tokens in the browser; a client must not turn an ID token into an access token.

### 7.3. Java `RestClient` and `WebClient`

Spring provides the `HttpHeaders.setBearerAuth(String)` helper to attach the token to the header. Pass the **raw token string**, without the `Bearer ` prefix:

~~~java
import org.springframework.web.client.RestClient;

public class OrderApiClient {
    private final RestClient client = RestClient.create("https://api.example.test");

    public String getOrder(String accessToken, String orderId) {
        return client.get()
            .uri("/api/orders/{id}", orderId)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

`RestClient` is well suited for synchronous calls in modern Spring Framework. For reactive applications, `WebClient` can be used in an equivalent manner:

~~~java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class ReactiveOrderApiClient {
    private final WebClient client =
        WebClient.create("https://api.example.test");

    public Mono<String> getOrder(String accessToken, String orderId) {
        return client.get()
            .uri("/api/orders/{id}", orderId)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

In Postman, Insomnia, or similar HTTP tools, select the **Bearer Token** auth type and typically enter only the raw token; the tool prepends the `Bearer` scheme automatically. If you enter `Bearer abc.def.ghi` into the Bearer Token field itself, the request may become `Authorization: Bearer Bearer abc.def.ghi`.

### 7.4. JSON body does not replace the Authorization header

~~~javascript
async function createOrder(accessToken, order) {
  const response = await fetch("https://api.example.test/api/orders", {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + accessToken,
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify(order)
  });

  if (!response.ok) {
    throw new Error("Cannot create order: HTTP " + response.status);
  }

  return response.json();
}
~~~

The token goes in `Authorization`; the body holds the `order` payload. Putting a token into a JSON field like `{"accessToken":"..."}` does not cause Spring Security to recognize a Bearer credential automatically and is not a standard default mechanism.

## 8. How does Spring Security read `Authorization: Bearer`?

For a **Servlet Resource Server** (typically using Spring MVC), the standard processing pipeline is:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring Security Filter Chain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["Extract token from Authorization header"]
    D --> E["AuthenticationManager"]
    E --> F["Validate JWT or introspect opaque token"]
    F --> G["Authentication + GrantedAuthority"]
    G --> H["Check endpoint authorization rules"]
    H --> I["Controller"]
~~~

`BearerTokenAuthenticationFilter` receives the credential and delegates to `AuthenticationManager`. For JWTs, the Resource Server uses `JwtDecoder` and validators; for opaque tokens, it uses `OpaqueTokenIntrospector`. After authentication, Spring Security builds an `Authentication` with authorities to enforce access rules.

Example Spring MVC configuration protecting `GET /api/orders/**` with the `orders.read` scope:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

`issuer-uri` here is an example URL. With a real issuer, Spring Security can validate the JWT's signature, issuer, and timestamps; if the application requires restricting `aud`, add audience validation. **Having an Authorization header does not mean the token will be accepted**: the token must be valid and carry sufficient permissions according to the rules.

On **WebFlux**, the corresponding entry points are `SecurityWebFilterChain`, `AuthenticationWebFilter`, `ServerHttpSecurity`, and reactive components. Whether using Spring MVC or WebFlux, the HTTP client sends the exact same syntax:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>

~~~

Spring Security JWT Resource Server typically converts `scope = "orders.read profile"` into authorities `SCOPE_orders.read` and `SCOPE_profile`. The rule `hasAuthority("SCOPE_orders.read")` checks the exact scope. After HTTP authorization, the service must still check permissions on the **specific order**, such as owner or tenant.

## 9. HTTP 401, 403, and `WWW-Authenticate`

**`Authorization`** is a request header sent by the client. **`WWW-Authenticate`** is a response header used to advertise the authentication scheme and, when appropriate, the reason for rejection.

### 9.1. Missing access token

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

For an endpoint requiring authentication, the typical response is:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"

~~~

`realm="orders-api"` illustrates a protection space defined by the API. When a request has no credentials, the server generally does not need to include a detailed Bearer error code in the challenge.

### 9.2. Expired or invalid token

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"

~~~

The server may also include:

~~~http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token expired"
~~~

`invalid_token` typically relates to an expired, revoked, malformed token, or one that fails validation. In practice, error headers may vary depending on configuration and policies to limit leaking internal details.

### 9.3. Valid token with insufficient scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.read"

~~~

`scope="orders.read"` describes the required permission and **does not grant permission** to the client. The client must obtain valid permissions from the Authorization Server according to policy.

### 9.4. Malformed Bearer request

If a request carries a token via multiple transport methods simultaneously, or Bearer parameters are malformed, RFC 6750 describes the `invalid_request` error typically paired with `400 Bad Request`. However, the actual status depends on the rejecting layer (HTTP parser, reverse proxy, bearer token resolver, security filter, custom policy). Do not assume every malformed header returns `400`.

| Situation | Typical status | Meaning |
|---|---|---|
| No credential on an endpoint requiring authentication | `401` | Valid Bearer token required |
| Wrong, revoked, or expired access token | `401` | `invalid_token` |
| Valid access token, insufficient permissions | `403` | `insufficient_scope` or authorization rule |
| Malformed Bearer request | `400` in `invalid_request` cases | Invalid request |
| Valid token with sufficient permissions | Determined by controller | Proceed with business logic |

A token properly signed by the issuer but targeting the wrong **API audience** should also be rejected during authentication if the Resource Server configures an audience validator. This is normally `401`, not `403` for missing scope.

## 10. Browsers and CORS preflight with Authorization

When JavaScript on `https://app.example.test` calls `https://api.example.test`, the request is **cross-origin**. The `Authorization` header is not a CORS-safelisted request header, so the browser typically performs an **OPTIONS preflight**:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization

~~~

A possible response is:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type
Vary: Origin

~~~

After a valid preflight, the browser sends the request containing the token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json

~~~

**Preflights generally do not carry Bearer credentials.** If the application requires authentication on all OPTIONS requests before CORS handling runs, the browser may report a CORS error even when the Bearer token used for the actual request is completely valid. Configure CORS properly for origins, methods, headers, and integrate it in the right order with Spring Security. CORS is a browser policy, **not a replacement** for Resource Server authentication/authorization. cURL does not enforce CORS restrictions like a browser.

## 11. Places you should not put a Bearer token

RFC 6750 describes the Authorization header and other methods such as form-encoded bodies and URI queries under specific conditions. For modern APIs, **putting the token in the header is the preferred option**:

| Location | Example | Assessment |
|---|---|---|
| `Authorization` header | `Authorization: Bearer token123` | **Recommended** over HTTPS |
| URL query | `/api/orders?access_token=token123` | **Avoid** because logs, history, and analytics easily capture URLs |
| Form body `application/x-www-form-urlencoded` | `access_token=token123` | Consider only if required for specific protocol compatibility |
| JSON body | `{"accessToken":"token123"}` | Not a default Spring Security Bearer credential |
| Custom header | `X-Access-Token: token123` | Not accepted unless the API has custom handling |
| Cookie | `Cookie: access_token=token123` | Belongs to a different model; requires evaluating CSRF, session, and origin |

Spring Security Resource Server defaults to extracting tokens from `Authorization`. To read tokens from elsewhere, you must configure `BearerTokenResolver` in Servlet or an appropriate converter in WebFlux. Do not enable multiple token extraction sources merely for testing convenience without clear control policies.

## 12. Protecting tokens in transit and inside the application

A Bearer token is a credential that can be used by others if captured; therefore:

1. **Require HTTPS** between clients and APIs; protect internal connections appropriately for the infrastructure model.
2. **Do not log real tokens** in application, proxy, APM, browser console, CI, or error-tracking logs.
3. **Do not embed tokens in URLs**, even while debugging; prevent tokens from appearing in browser history and access logs.
4. **Send tokens only to intended APIs**; be especially careful with redirects or calls to third-party hosts.
5. **Limit lifetime, scope, and audience** to what is needed, reducing damage if a token leaks.
6. **Validate signature/issuer/timestamps/audience** and apply business authorization at the Resource Server.
7. **Do not send refresh tokens or ID tokens to APIs** in place of access tokens.
8. **Choose token storage based on client type and risks**, especially XSS/storage/session risks in browsers.

TLS protects data in transit between TLS termination points, but proxies, gateways, and services can see headers after decryption. Access controls and redaction rules must be enforced at these components.

## 13. Common errors and how to diagnose them

| Symptom | Possible cause | How to check |
|---|---|---|
| `401` even though client set token | Header did not reach API, env variable empty, token expired | Check request construction, gateway, token timestamps |
| `401` with freshly issued token | Wrong issuer, JWK, audience, algorithm, or token type | Compare against the API's validation policy |
| `401` when using Bearer Token tool | Entered the scheme into a field that already prepends `Bearer` | Enter only the raw token |
| `401` with `Authorization: Basic ...` | Wrong HTTP authentication scheme | Use `Bearer` and a valid access token |
| `403` even though token is valid | Missing scope/authority or business permission | Check `SCOPE_*` mapping and policies |
| Browser reports CORS, cURL works | OPTIONS preflight blocked or CORS misconfigured | Inspect preflight request/response |
| Backend does not see `Authorization` | Proxy/gateway stripped or did not forward header | Check secure forwarding configuration |
| Token in query is ignored | Spring defaults to reading Bearer from header | Move token into `Authorization` |
| API A accepts token, API B rejects it | Token not intended for API B's audience/issuer/scope | Issue a token matching API B |

When debugging, separate three cases: **credential not sent properly**, **authentication failed**, and **authentication succeeded but authorization failed**. Never fix a 401 by disabling JWT validation or permitting all URLs.

## 14. Examples of recognizing requests and responses

**A. Public GET endpoint** does not necessarily require a token:

~~~http
GET /public/catalog HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

If `/public/catalog` is configured with `permitAll`, a missing `Authorization` header is normal.

**B. Protected GET endpoint** requires a Bearer token:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json

~~~

**C. JSON POST** includes both the authentication header and the body:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
Accept: application/json
Content-Length: 21

{"sku":"A42","qty":2}
~~~

**D. Valid token lacking `orders.write`**:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.write"

~~~

**E. Expired token**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"

~~~

The client must request a new access token via a valid OAuth 2.0 flow; resending the expired token repeatedly will not solve the issue.

## 15. Self-check questions

**1. A client has access token `abc.def.ghi`. Which header is correct?**

~~~http
Authorization: Bearer abc.def.ghi
~~~

The token follows the `Bearer` scheme, without extra double quotes.

**2. A POST already has `Content-Type: application/json`, so can the API authenticate it?** No. That header only declares the body format and does not replace the Bearer credential.

**3. Why is 401 different from 403?** `401` usually means credentials are missing or invalid; `403` usually means authentication succeeded, but permissions are insufficient under policy.

**4. If Base64URL decoding of a JWT succeeds, is it trustworthy?** Not yet. Signature, issuer, expiration, audience, and other system validations must pass before using its claims.

**5. Why does a browser send OPTIONS without a token?** That is typically a CORS preflight asking the server whether sending the `Authorization` header in the actual request is permitted.

## 16. Summary

A request protected by Bearer authentication carries **method, path, HTTP headers**, and the authentication line:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

For GET, the token is in the header even without a body. For POST/PUT/PATCH, the token **remains in the header**, while the body carries business data. Whether the Resource Server runs **Spring MVC/Servlet** or **Spring WebFlux**, the HTTP syntax sent by the client is identical. Spring Security extracts the token, verifies the JWT or introspects the opaque token, creates the principal, maps authorities, and enforces permissions.

Always use **HTTPS**, send the right **access token** to the right API, keep tokens out of URLs/queries/logs, check **issuer/audience/expiration/scope**, and distinguish **401** from **403** when handling responses.

## References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
