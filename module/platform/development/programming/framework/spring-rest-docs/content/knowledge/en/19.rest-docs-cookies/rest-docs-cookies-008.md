# Distinguishing cookies from the Authorization header

## Learning Objectives

After this lesson, you will be able to:

- Distinguish authentication cookies from credentials sent via the `Authorization` header.
- Explain how browsers automatically send cookies according to cookie policy versus how clients explicitly attach a Bearer token to requests.
- Analyze `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path`, CORS, and CSRF when choosing an authentication mechanism.
- Use Spring REST Docs to document cookies with `requestCookies`/`responseCookies` and `Authorization` with `requestHeaders`.
- Write HTTP tests for endpoints using session cookies and endpoints using Bearer tokens; verify missing or invalid credentials.
- Mask session IDs/tokens in snippets while keeping the structure needed for consumers to integrate properly.

## 1. Two ways to carry credentials in HTTP

Both cookies and the `Authorization` header can carry data that helps the server identify the caller. However, they differ in how they are created, stored, sent, and handled by browsers.

**Authentication with a session cookie:**

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Cookie: SESSION=<session-id>
Accept: application/json
```

The server typically issues the cookie after login via a `Set-Cookie` response header. The browser stores the cookie and automatically sends it back on requests matching `Domain`, `Path`, `Secure`, `SameSite`, and other cookie rules.

**Authentication with a Bearer token:**

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
```

The client obtains an access token through an authentication flow, then explicitly attaches the token to the `Authorization` header for requests requiring credentials. The browser does not automatically pull an arbitrary token from local storage into this header; client application code must do so.

Both examples use placeholders. Never include valid session IDs, access tokens, or refresh tokens in public documentation.

## 2. Comparing cookies and the Authorization header

| Aspect | Authentication cookie | Authorization: Bearer |
| --- | --- | --- |
| How it is sent | Browser automatically attaches cookies matching the URL and cookie policy | Client explicitly sets the header on the request |
| Typical storage | Browser cookie jar or HTTP client cookie store | Client memory/token manager; storage depends on the application |
| Credential | Typically an opaque session ID or token inside a cookie | Typically a Bearer access token |
| Readable by JavaScript? | Cookies with `HttpOnly` cannot be read by JavaScript via `document.cookie` | If the token is in memory, application code can access it; tokens stored elsewhere carry their own risks |
| CSRF | Vulnerable because browsers auto-send cookies under matching conditions | Less exposed to cookie auto-attach CSRF if the token is only attached explicitly by client code; XSS can still steal or abuse the token |
| CORS | Cross-origin credentialed requests require appropriate credentials and origin configuration | `Authorization` makes a request non-CORS-safelisted and may trigger a preflight |
| Revocation | Session can be invalidated server-side; client cookie cleanup must be handled | Token can be revoked, or short-lived access tokens/refresh flows can be used depending on design |
| REST Docs | Cookies have dedicated descriptors/snippets | Header is documented with `requestHeaders` |

Neither approach is universally better. The choice depends on client types, threat model, authentication infrastructure, browser requirements, and system security policies.

## 3. How do authentication cookies work?

A typical session cookie flow:

1. The client submits login credentials to the login endpoint.
2. The server verifies credentials and creates a server-side session.
3. The server returns `Set-Cookie` containing the session identifier and cookie attributes.
4. The browser stores the cookie in its cookie jar.
5. On subsequent requests, the browser automatically sends `Cookie` if the URL and cookie policy match.
6. The server reads the session identifier, looks up the session, and resolves the principal/permissions.
7. On logout or session expiration, the server invalidates the session and may return `Set-Cookie` to delete the cookie on the client.

Example login response:

```http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<REDACTED>; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"authenticated":true}
```

Subsequent request:

```http
GET /api/profile HTTP/1.1
Cookie: SESSION=<REDACTED>
Accept: application/json
```

A session cookie is usually an opaque identifier. Session state data can live server-side in a database, cache, or distributed session store. The cookie does not need to contain full user details.

### 3.1. Cookie attributes to understand

| Attribute | Meaning |
| --- | --- |
| `HttpOnly` | JavaScript cannot read the cookie via `document.cookie`; the browser can still send it according to rules |
| `Secure` | Browser sends the cookie only over secure connections according to cookie rules |
| `SameSite` | Controls whether the cookie is sent in certain same-site/cross-site contexts |
| `Domain` | Defines the host scope permitted to receive the cookie |
| `Path` | Restricts the request path scope to which the cookie applies |
| `Max-Age` | Lifetime in seconds; `0` or negative values can be used to delete a cookie |
| `Expires` | Expiration timestamp of the cookie |

`HttpOnly` does not prevent the cookie from being sent in HTTP requests and does not by itself protect an application from all XSS. `Secure` does not replace TLS across the entire system. `SameSite` is one CSRF control layer, not a sole defense across every threat model.

## 4. How do the Authorization header and Bearer tokens work?

With Bearer authentication, the client attaches credentials to each authenticated request:

```http
GET /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
```

The server or resource server verifies the token and enforces authorization policies. For JWTs, checks may include signature, issuer, audience, validity window, and claims. For opaque tokens, the server may look them up via an authorization server or token introspection/cache.

Bearer means whoever possesses the token can exercise it within its granted scope. Therefore:

- Transmit tokens over TLS.
- Never write tokens to uncontrolled logs or snippets.
- Grant minimal scopes/permissions.
- Keep access tokens short-lived by design.
- Maintain proper refresh/revocation workflows.
- Avoid putting tokens in URL query strings because URLs easily leak into logs, browser history, and telemetry.

### 4.1. Access tokens and refresh tokens

Access tokens are typically sent in the `Authorization` header to resource servers. Refresh tokens are used at the token endpoint to obtain new access tokens; they should not be sent to every API resource.

Example:

```http
POST /oauth/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REDACTED>
```

The exact format depends on the authorization server and OAuth flow. The example above merely illustrates a refresh request; do not treat it as a complete OAuth configuration.

## 5. CSRF and XSS: different risks between the two approaches

### 5.1. Why do cookies usually require CSRF attention?

Browsers automatically send matching cookies whenever a request satisfies cookie rules. A malicious page may try to make a user's browser send a request to another site; if an authentication cookie is auto-attached, the request can carry the user's session.

That is the basis of Cross-Site Request Forgery (CSRF). Common layered defenses include:

- A `SameSite` cookie policy aligned with the flow.
- Server-verified CSRF tokens.
- `Origin`/`Referer` checks where appropriate.
- Never using `GET` for state-changing operations.
- Purpose-built CORS and cookie credentials configuration.

Do not assume `SameSite` is always enough. SSO flows, cross-site frontend/API deployments, or browser compatibility needs may call for explicit CSRF designs.

### 5.2. Bearer tokens do not eliminate XSS risks

If a browser application keeps an access token somewhere JavaScript can reach, XSS can read the token or execute requests under the user's authority. Even if a token cannot be read directly, malicious script running inside the origin can still drive the UI and dispatch requests from the user's context.

Therefore, a Bearer header is not automatically safer than a cookie. You still need XSS defenses, content controls, a suitable CSP, avoiding theft-prone token storage, and considering the Backend-for-Frontend pattern if your architecture needs to keep tokens server-side.

## 6. CORS and browser behavior

Cookies and the `Authorization` header affect CORS differently:

- Cross-origin requests using cookies require the browser to allow credentials; fetch clients typically need `credentials: "include"` in cross-origin scenarios.
- The server must return `Access-Control-Allow-Credentials: true`, and `Access-Control-Allow-Origin` must be a specific matching origin; wildcard `*` cannot be used for credentialed responses.
- `Authorization` is not a CORS-safelisted request header; browsers typically send an `OPTIONS` preflight so the server can confirm the header is allowed.
- For cross-site cookies, `SameSite` and `Secure` attributes also affect whether the browser sends the cookie.

Fetch example using cookies:

```javascript
fetch("https://api.example.test/api/profile", {
  method: "GET",
  credentials: "include"
});
```

Example where the client explicitly attaches a Bearer token:

```javascript
fetch("https://api.example.test/api/profile", {
  method: "GET",
  headers: {
    "Authorization": "Bearer " + accessToken
  }
});
```

These are browser-side illustrations. Non-browser HTTP clients may not enforce CORS or cookie policies the way browsers do; hence, MockMvc test results do not prove browser cross-origin behavior.

## 7. Documenting cookies and Authorization with Spring REST Docs

Spring REST Docs has distinct descriptor APIs for cookies and headers:

| HTTP component | REST Docs API |
| --- | --- |
| Request cookie | `requestCookies(cookieWithName(...))` |
| Response cookie | `responseCookies(cookieWithName(...))` |
| Request `Authorization` header | `requestHeaders(headerWithName("Authorization")...)` |
| Response header | `responseHeaders(headerWithName(...))` |

Cookies travel in HTTP headers on the wire, yet REST Docs can generate dedicated cookie snippets to document each cookie more legibly. Do not document the same cookie simultaneously as both a `Cookie` request header and a request cookie descriptor in the same table if that creates duplication; pick snippets reflecting the page's goal.

### 7.1. Documenting a request cookie

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;

document("profile-cookie",
    requestCookies(
        cookieWithName("SESSION")
            .description("Session identifier issued by the server after login")
    )
)
```

### 7.2. Documenting a response cookie

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

document("login-cookie",
    responseCookies(
        cookieWithName("SESSION")
            .description("Session cookie; client sends it back on authenticated requests")
    )
)
```

Cookie descriptors document the cookie name and meaning. Attributes such as `Path`, `HttpOnly`, `Secure`, and `SameSite` still need to be shown via response headers/snippets or supplemental prose depending on your documentation layout.

### 7.3. Documenting the Authorization header

```java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;

document("orders-bearer",
    requestHeaders(
        headerWithName(HttpHeaders.AUTHORIZATION)
            .description("Bearer access token; required to call the endpoint")
    )
)
```

This is a request header, not a cookie descriptor. `requestHeaders(...)` documents the `Authorization` header; it does not validate tokens or configure Spring Security on its own.

## 8. MockMvc practice: authenticating with a session cookie

Suppose `/api/profile` uses a session cookie named `SESSION`. Test example:

```java
@Test
void returnsProfileForValidSession() throws Exception {
    mockMvc.perform(get("/api/profile")
                    .cookie(new Cookie("SESSION", "documentation-session"))
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("user-42"))
            .andDo(document("profile-cookie",
                    preprocessRequest(
                            modifyHeaders(headers ->
                                    headers.set("Cookie", "SESSION=<REDACTED>"))
                    ),
                    requestCookies(
                            cookieWithName("SESSION")
                                    .description("Session identifier issued by the server")
                    ),
                    responseFields(
                            fieldWithPath("id").description("User ID")
                    )
            ));
}
```

The test uses a dummy cookie and masks it in snippets. With real Spring Security, make sure MockMvc is configured with the appropriate security filter chain and session repository. If you run a standalone controller test without a real security context, the test does not prove session-based authentication.

Test for missing cookie:

```java
@Test
void rejectsMissingSessionCookie() throws Exception {
    mockMvc.perform(get("/api/profile")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
}
```

The status code in this example represents a hypothetical contract. An application may redirect to a login page or return a different error depending on client type and security configuration. Assert actual behavior.

## 9. MockMvc practice: authenticating with a Bearer token

For endpoints using Resource Server/JWT or a custom Bearer mechanism, the client sends the `Authorization` header:

```java
@Test
void returnsOrdersForValidBearerToken() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer documentation-token")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("orders-bearer",
                    preprocessRequest(
                            replacePattern(
                                    Pattern.compile("Bearer [^\\\\s]+"),
                                    "Bearer <REDACTED>")
                    ),
                    requestHeaders(
                            headerWithName(HttpHeaders.AUTHORIZATION)
                                    .description("Bearer access token; required")
                    ),
                    responseFields(
                            fieldWithPath("content").description("List of orders")
                    )
            ));
}
```

For meaningful security testing, the dummy token must be accepted by your test security setup or use appropriate test support. This example does not synthesize a valid JWT by itself; if your application verifies real JWT signatures, supply a valid test token or configure a dedicated test decoder/converter intentionally.

Test for missing token:

```java
@Test
void rejectsMissingBearerToken() throws Exception {
    mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
}
```

And you can add a test for a token lacking required scopes:

```java
@Test
void rejectsTokenWithoutRequiredScope() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer token-without-report-scope"))
            .andExpect(status().isForbidden());
}
```

`401` and `403` in these examples illustrate authentication versus authorization scenarios. Actual mappings must follow your security configuration and API error contract.

## 10. Comparing documentation for both endpoints

Suppose an API exposes two endpoint groups:

| Endpoint | Mechanism | What to document |
| --- | --- | --- |
| `GET /browser/profile` | Session cookie | `SESSION` cookie, login flow, `Set-Cookie` attributes, logout/expiry, CSRF if applicable |
| `GET /service/orders` | Bearer token | `Authorization` scheme, how to obtain access tokens, scopes, expiry, refresh flow at token endpoint |

Do not lump both mechanisms into a single vague phrase like “send a token to authenticate.” Clients need to know where credentials go and who is responsible for sending them:

- Browsers automatically send cookies per cookie policy.
- Bearer clients explicitly attach the `Authorization` header.
- Cookies require explaining `SameSite`/CSRF in browser flows.
- Bearer tokens require explaining scopes, expiry, refresh, and secure storage.

If an application supports both mechanisms on the same API, documentation must explain precedence and behavior when a request carries both a cookie and `Authorization`. Never let the server silently pick a credential in an undocumented order.

## 11. Preprocessing and protecting snippets

Cookies and `Authorization` typically carry authentication data. Use dummy data and preprocessors so real credential values are never stored in artifacts.

For `Authorization`:

```java
preprocessRequest(
    replacePattern(
        Pattern.compile("Bearer [^\\\\s]+"),
        "Bearer <REDACTED>"
    )
)
```

For `Cookie`, if snippets need to show the session mechanism:

```text
Cookie: SESSION=<REDACTED>
```

For `Set-Cookie`, preserve security attributes:

```text
Set-Cookie: SESSION=<REDACTED>; Path=/; HttpOnly; Secure; SameSite=Lax
```

If you completely remove `Cookie` or `Authorization` from the preprocessed exchange, the corresponding descriptor may no longer find the header/cookie in the snippet. When readers need to see how authentication works, replace the value instead of deleting the credential name.

Inspect all artifacts, not just cookie/header tables: credentials can appear in `http-request`, `http-response`, `curl-request`, logs, or debug files.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Browser sends cookie but MockMvc fails auth | Test context lacks security/session config or cookie name is wrong | Check filter chain, session repository, and actual cookie |
| Browser does not send cross-site cookie | `SameSite`, `Secure`, `Domain`, `Path`, or credentials/CORS misconfigured | Check cookie attributes and CORS policy in browser |
| `Authorization` present in code yet server returns 401 | Expired token, wrong issuer/audience/signature, or malformed header | Verify token and resource server configuration |
| REST Docs cannot find `Cookie` descriptor | Preprocessor removed `Cookie` before snippet generation | Replace value or drop descriptor if not publishing the cookie |
| Header snippet leaks Bearer token | Missing request preprocessor or regex mismatch | Use dummy tokens, check pattern, and scan artifacts |
| Both mechanisms sent with unclear behavior | API has not defined credential precedence | Define and test requests carrying both cookie and `Authorization` |
| JavaScript fails to read `HttpOnly` cookie | This is expected behavior by design | Let browser requests send the cookie; do not read via `document.cookie` |
| Documentation omits CSRF | Only documented cookies without explaining browser auto-send | Add CSRF flow documentation and matching tests |

## 13. Checklist for choosing and documenting an authentication mechanism

- [ ] Identify whether the endpoint uses a session cookie, Bearer token, or both.
- [ ] Describe how credentials are created/issued and where clients send them.
- [ ] For cookies, state the cookie name and `Path`, `Domain`, `Secure`, `HttpOnly`, `SameSite`, and expiry as needed.
- [ ] For Bearer, state the scheme, token acquisition, scopes, expiry, and refresh flow.
- [ ] Analyze CSRF for cookies and XSS/token theft for clients holding Bearer tokens.
- [ ] Specify CORS/credentials if browsers make cross-origin calls.
- [ ] Use `requestCookies`/`responseCookies` for cookies; `requestHeaders` for `Authorization`.
- [ ] Write tests for valid, missing, invalid, and insufficient-permission credentials.
- [ ] Mask sessions/tokens in snippets while keeping details consumers need.
- [ ] If the same endpoint supports both mechanisms, define precedence explicitly.
- [ ] Inspect raw snippets and rendered docs before publishing.

## 14. Practice exercise

A system has:

- A web app using a `SESSION` cookie with `HttpOnly`, `Secure`, and `SameSite=Lax`.
- A service-to-service API using `Authorization: Bearer` access tokens.
- Endpoint `/api/profile` using only the session cookie.
- Endpoint `/api/jobs` using only a Bearer token with scope `JOBS_READ`.

Complete the following:

1. Write login documentation explaining the `Set-Cookie` response and cookie attributes.
2. Use `requestCookies(...)` to document `SESSION` in the `/api/profile` test.
3. Write tests for missing `SESSION` and invalid session; document actual behavior.
4. Use `requestHeaders(...)` to document `Authorization` in the `/api/jobs` test.
5. Write tests for missing token, invalid token, and insufficient scope; distinguish `401` and `403` per the contract.
6. Mask `SESSION` and Bearer token values in snippets while preserving published cookie/header names and security attributes.
7. Write CSRF explanations for the browser cookie flow and scope/expiry notes for the Bearer flow.
8. If the web app calls the API cross-origin, verify credentials, `SameSite`, and CORS with an appropriate browser integration test.

**Self-check question:** Can session cookies and Bearer tokens be treated as identical since both represent a user? No. They may both authenticate a principal, yet they are transmitted and protected differently. Browsers automatically attach cookies based on policy, whereas Bearer headers are typically added explicitly by clients; consequently, CSRF, CORS, credential storage, and documentation differ.

## Conclusion

Both cookies and the `Authorization` header can carry credentials, but they cannot be documented as the same mechanism. Cookies are typically sent automatically by browsers based on `Domain`, `Path`, `Secure`, and `SameSite`; hence documentation must cover session lifecycle, cookie attributes, and CSRF protection. Bearer tokens are explicitly placed in the `Authorization` header by clients; documentation must explain the scheme, token acquisition, scopes, expiry, and refresh while noting token-exposure/XSS risks. In Spring REST Docs, use `requestCookies`/`responseCookies` for cookies and `requestHeaders` for `Authorization`. HTTP tests must prove valid, missing, and invalid credentials; snippets must mask real values while retaining enough detail for consumers to integrate accurately.
