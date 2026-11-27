# Testing dynamic client registration, PAR, and client authentication

An Authorization Server must strictly control which clients are allowed to participate, how clients submit authorization requests, and how clients prove their identity at protected endpoints. When a system supports OpenID Connect Dynamic Client Registration, Pushed Authorization Requests (PAR), and multiple client authentication methods, functional testing must verify stored metadata, HTTP behavior, and security rules alike.

Three interrelated functional areas are covered:

- **Dynamic Client Registration (DCR):** a client registers dynamically and receives metadata such as `client_id`, redirect URIs, grant types, scopes, and authentication methods.
- **Pushed Authorization Requests (PAR):** a client submits authorization parameters directly to the server via an authenticated request, then uses a short-lived `request_uri` at the authorization endpoint.
- **Client authentication:** the Authorization Server verifies the client at endpoints requiring authentication, such as the token endpoint or PAR endpoint.

This lesson focuses on functional testing for Spring Authorization Server: verifying configuration, preparing clients, sending requests, checking responses, inspecting persisted data, and exercising rejection scenarios.

## 1. Testing scope and objectives

Functional testing must verify observable behavior from both the client's and Authorization Server's perspectives. A thorough test case checks not only HTTP status codes, but also metadata, persistence state, and security impact.

| Group | What to verify |
|---|---|
| Dynamic Client Registration | Endpoint is published and enabled; valid metadata creates a client; data is persisted; invalid metadata is rejected |
| Client registration policy | Redirect URIs, grant types, response types, scopes, and auth methods comply with allowlists/policies |
| PAR | Request is accepted; response contains `request_uri` and expiration; authorization request references the exact pushed request |
| PAR security | Client binding, expiration, request parameters, and replay policy are enforced |
| Client authentication | Registered method matches submitted credentials/assertions/certificates |
| Negative paths | Missing credentials, wrong credentials, expired assertions, wrong audience, invalid signatures, or unsupported methods are all rejected |
| Persistence | Client registrations and authorization requests are stored with required durability |
| Operational consistency | Discovery/metadata, issuer, JWKS, and endpoint URIs remain consistent across replicas |

Tests should run through the real HTTP filter chain with appropriate repositories and encoders. Separate unit tests for validators or services remain useful, but they do not replace integration tests through SecurityFilterChain, converters, and authentication providers.

## 2. Preparing configuration and test environment

### 2.1. Checking version and feature support

Spring Authorization Server evolves across versions; configurer API names, endpoints, and protocol support can change. Before writing tests, pin the Spring Authorization Server and Spring Security versions in use, then confirm which features those versions provide.

Specifically, verify:

- The OIDC Client Registration Endpoint exists in your version and is enabled.
- The Pushed Authorization Request Endpoint is supported and configured.
- The client authentication methods you need to test are supported.
- JWT, JWK, and mTLS configurations align with the corresponding Spring Security version.

Do not create mock endpoints in tests to compensate for features not supported by the framework. If DCR or PAR is implemented via a custom extension, tests must invoke that actual extension and verify its real behavior.

### 2.2. Enabling the endpoints to test

Configuration example using the modern configurer API, with the OIDC Client Registration and PAR endpoints explicitly enabled:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer
                .oidc(oidc -> oidc
                    .clientRegistrationEndpoint(Customizer.withDefaults())
                )
                .pushedAuthorizationRequestEndpoint(Customizer.withDefaults())
        );

    return http.build();
}
~~~

This is an illustrative structure. In a real application, keep existing authorization rules, Resource Server configuration, exception handling, consent, and any other active endpoints. Verify APIs against your project's dependency versions.

Endpoint paths can be configured in `AuthorizationServerSettings`. Common default paths in Spring Authorization Server are:

| Endpoint | Common default path |
|---|---|
| Token | `/oauth2/token` |
| Authorization | `/oauth2/authorize` |
| Pushed Authorization Request | `/oauth2/par` |
| OIDC Client Registration | `/connect/register` |
| JWK Set | `/oauth2/jwks` |

Use values from metadata/discovery or the application's configuration as the source of truth. Tests should not hardcode paths copied from an example if the application has customized its endpoints.

### 2.3. Using dedicated test repositories and credentials

Tests need a `RegisteredClientRepository` capable of reading back newly registered clients. In integration testing environments, use a JDBC repository with a test database, or an in-memory repository when persistence is outside the test goal.

Minimum preparation:

- A confidential client using `client_secret_basic`.
- A public client using `none` and authorization code with PKCE.
- A client using `private_key_jwt`, if this method is enabled.
- A client using `client_secret_post`, if this method is allowed.
- A client with invalid redirect URIs, grant types, or auth methods to test rejection branches.
- A logged-in test user to complete the authorization flow after PAR.

Never use production secrets, real private keys, real certificates, or real user data in tests.

## 3. Testing Dynamic Client Registration

### 3.1. Confirming the endpoint is published

OIDC Discovery can publish the `registration_endpoint` field when the server supports Dynamic Client Registration.

Fetch the discovery document:

~~~bash
curl -i https://auth.example.com/.well-known/openid-configuration
~~~

Verify:

- `issuer` matches the public issuer.
- `registration_endpoint` is present when DCR is enabled.
- The registration URL points to the right host, scheme, and context path.
- The endpoint is reachable through ingress/reverse proxy per deployment configuration.

If the server does not publish `registration_endpoint`, verify that the OIDC Client Registration Endpoint is enabled in your version's configurer and metadata provider. If the endpoint is published but returns `404`, check endpoint settings and proxy routing.

### 3.2. Registering a confidential web client

An illustrative registration request:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Content-Type: application/json
Accept: application/json

{
  "application_type": "web",
  "client_name": "Billing Portal",
  "redirect_uris": [
    "https://billing.example.com/login/oauth2/code/portal"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "scope": "openid profile email",
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

If the registration endpoint is protected by an initial access token or a custom authorization mechanism, requests must send credentials per that exact policy. Never assume the endpoint is always open for anonymous registration.

When the request is valid, inspect the response per protocol and server configuration. Normally a successful registration returns `201 Created` with the provisioned client metadata, including `client_id` and related fields. For a confidential client using a client secret, the response may return the newly generated `client_secret`.

Assertions to check:

- Response contains a non-empty, unique `client_id`.
- `redirect_uris`, `grant_types`, `response_types`, `scope`, and `token_endpoint_auth_method` reflect accepted metadata.
- The client can be read back via `RegisteredClientRepository`.
- Redirect URIs are not arbitrarily broadened or normalized into dangerous URIs.
- The secret is returned per protocol and stored encoded using PasswordEncoder.
- The client can execute authorization/token flows with the newly registered configuration.

Never log or save plaintext `client_secret` values in test reports. If the response returns a secret, keep it solely in test memory and use it directly within the test case.

### 3.3. Example test using MockMvc

The example below assumes the endpoint is enabled and the registration policy permits the test request. If the endpoint requires an initial access token, add the authentication header matching your application's extension/policy.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ClientRegistrationFunctionalTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RegisteredClientRepository registeredClientRepository;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void shouldRegisterConfidentialWebClient() throws Exception {
        String request = """
            {
              "application_type": "web",
              "client_name": "Billing Portal",
              "redirect_uris": [
                "https://billing.example.com/login/oauth2/code/portal"
              ],
              "grant_types": ["authorization_code", "refresh_token"],
              "response_types": ["code"],
              "scope": "openid profile email",
              "token_endpoint_auth_method": "client_secret_basic"
            }
            """;

        MvcResult result = mockMvc.perform(post("/connect/register")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(request))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.client_id").isNotEmpty())
            .andExpect(jsonPath("$.redirect_uris[0]")
                    .value("https://billing.example.com/login/oauth2/code/portal"))
            .andExpect(jsonPath("$.token_endpoint_auth_method")
                    .value("client_secret_basic"))
            .andReturn();

        String responseBody = result.getResponse().getContentAsString();
        JsonNode response = objectMapper.readTree(responseBody);
        String clientId = response.path("client_id").asText();

        RegisteredClient registeredClient =
                registeredClientRepository.findByClientId(clientId);

        assertThat(registeredClient).isNotNull();
        assertThat(registeredClient.getAuthorizationGrantTypes())
                .contains(AuthorizationGrantType.AUTHORIZATION_CODE);
        assertThat(registeredClient.getClientAuthenticationMethods())
                .contains(ClientAuthenticationMethod.CLIENT_SECRET_BASIC);
    }
}
~~~

This test needs standard test imports and beans such as `post`, `status`, `jsonPath`, `objectMapper`, and AssertJ. The endpoint path in the example is a common default; pull it from test configuration if the project customizes it.

Do not assert the stored secret by comparing it with the plaintext secret. Verify that the repository stores a value encoded by PasswordEncoder or verify that the client can authenticate using the secret returned in the response.

### 3.4. Testing metadata policies

Dynamic registration is an input that directly affects the attack surface. The server should never accept arbitrary metadata sent by a client.

Key test cases:

| Submitted data | Expected result |
|---|---|
| Missing `redirect_uris` when required by protocol | Reject registration |
| Invalid or out-of-policy redirect URI | Reject registration |
| Grant type unsupported by server | Reject or strip per published protocol policy |
| Response type incompatible with grant type | Reject registration |
| Disallowed scope | Reject or restrict per policy |
| Unsupported `token_endpoint_auth_method` | Reject registration |
| Invalid or untrusted `jwks_uri` | Reject when the registration method requires a JWKS URI |
| Oversized metadata or malformed JSON | Reject request |
| Client name containing invalid content | Handle safely without impacting logs/UI |
| Repeated registration with identical metadata | Issue new client ID or handle per policy; never overwrite an existing client unintentionally |

For redirect URIs, apply strict matching rules. Never allow wildcards or arbitrary URL prefixes for web clients. For native applications, allow only redirect URI forms accepted by standards and application policy.

### 3.5. Testing public clients and PKCE

A public client cannot store a client secret securely inside an app installed on a user's device. Registration metadata typically declares:

~~~json
{
  "application_type": "native",
  "client_name": "Mobile App",
  "redirect_uris": [
    "com.example.mobile:/oauth2redirect"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "scope": "openid profile",
  "token_endpoint_auth_method": "none"
}
~~~

After registration, verify:

- The client is stored as a public client per policy.
- No secret is issued for the client to embed in a native app.
- Grant types are restricted to what was requested.
- PKCE is enforced via `ClientSettings.requireProofKey(true)` or an equivalent mechanism.
- Authorization requests missing `code_challenge` or using `plain` when policy requires S256 are rejected.
- Token requests with a wrong `code_verifier` are rejected.

Do not trust client-supplied metadata to decide whether a client can skip PKCE. The server must enforce policy based on client type and the server's own trusted configuration.

### 3.6. Testing registration access and client administration

If the server issues registration access tokens or uses initial access tokens, test the token lifecycle:

- Tokens are sent in the header per the implemented bearer mechanism.
- Wrong, expired, or unprivileged registration tokens are rejected.
- A token permits operations only on the client/resource it represents.
- Client registration tokens are never confused with access tokens meant for UserInfo or business APIs.
- Updating/deleting clients is allowed only when the corresponding endpoint and policy are enabled.
- Revoking registration management permissions invalidates old tokens per policy.

If the application does not implement registration management tokens, do not write tests assuming that feature exists. Test the exact endpoint protection mechanism actually in use.

## 4. Testing Pushed Authorization Requests (PAR)

### 4.1. Purpose of PAR

PAR lets a client send authorization parameters to the Authorization Server over a back-channel request. The server stores the request and returns a short-lived `request_uri`. The client uses this URI when redirecting the user to the authorization endpoint.

PAR flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as PAR Endpoint
    participant A as Authorization Endpoint
    participant U as End User

    C->>P: POST authorization parameters + client authentication
    P->>P: Authenticate client and validate parameters
    P-->>C: 201 Created, request_uri, expires_in
    C->>U: Redirect browser to authorization endpoint
    U->>A: GET /oauth2/authorize?client_id=...&request_uri=...
    A->>A: Look up request_uri, check client and expiration
    A-->>U: Proceed to authentication/consent
~~~

PAR avoids passing all authorization parameters through the front channel and lets the server validate the request before redirecting the user to the authorization endpoint.

### 4.2. Sending a valid pushed authorization request

An illustrative request using client secret basic:

~~~http
POST /oauth2/par HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=portal-client&
response_type=code&
redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&
scope=openid%20profile%20email&
state=st-123&
nonce=no-456&
code_challenge=<S256-CHALLENGE>&
code_challenge_method=S256
~~~

Actual parameters must match the registered client. The example above illustrates Authorization Code Flow with PKCE; do not send the code verifier to the PAR endpoint because the verifier stays on the client and is sent in the token request.

A successful response typically looks like:

~~~json
{
  "request_uri": "urn:ietf:params:oauth:request_uri:opaque-value",
  "expires_in": 90
}
~~~

The URI and expiration values here are illustrative. Actual response checks must ensure:

- HTTP status is `201 Created` per PAR.
- `request_uri` is non-empty and uses a URI format supported by the server.
- `expires_in` is a positive number of seconds.
- The request URI does not leak authorization parameters or user data.
- The server stores the request bound to the exact client and expiration.
- The client can use the request URI to initiate the authorization flow.

### 4.3. Example PAR endpoint test

Example with `client_secret_basic`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PushedAuthorizationRequestFunctionalTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void shouldAcceptValidPushedAuthorizationRequest() throws Exception {
        MvcResult result = mockMvc.perform(post("/oauth2/par")
                .with(httpBasic("portal-client", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("client_id", "portal-client")
                .param("response_type", "code")
                .param("redirect_uri",
                        "https://portal.example.com/callback")
                .param("scope", "openid profile")
                .param("state", "state-123")
                .param("nonce", "nonce-456")
                .param("code_challenge", "S256_CHALLENGE_VALUE")
                .param("code_challenge_method", "S256")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.request_uri").isNotEmpty())
            .andExpect(jsonPath("$.expires_in").isNumber())
            .andReturn();

        JsonNode response = objectMapper.readTree(
                result.getResponse().getContentAsString());

        assertThat(response.path("expires_in").asLong()).isPositive();
    }
}
~~~

In real tests, compute a valid `code_challenge` from a random `code_verifier` using S256; do not use an arbitrary string if the application's validator checks challenge formatting. Credentials and clients must be seeded into the test repository before sending the request.

### 4.4. Using request_uri at the authorization endpoint

After receiving `request_uri`, the client redirects the browser to the authorization endpoint with `client_id` and `request_uri`:

~~~http
GET /oauth2/authorize?client_id=portal-client&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3Aopaque-value HTTP/1.1
Host: auth.example.com
~~~

Tests should verify:

- The Authorization Server finds the pushed request.
- The request is bound to the exact client.
- Redirect URI, response type, scopes, state, nonce, and PKCE parameters come from the stored request.
- The client cannot alter authorization parameters already accepted by the server by appending conflicting front-channel values.
- The user proceeds to authentication/consent just like a standard authorization flow.
- If the request URI is expired or nonexistent, the server returns an appropriate protocol error, typically `invalid_request_uri`.

Do not treat the authorization endpoint returning the login page as a test failure. When the user is not logged in, redirecting to the login page can be the exact expected behavior. Tests must distinguish valid redirects from `invalid_request_uri`, `invalid_request`, or `unauthorized_client` errors.

### 4.5. Negative PAR and security cases

| Scenario | Expected result |
|---|---|
| Missing client authentication for confidential client | Rejected per registered auth method |
| Wrong client secret | `invalid_client` |
| `client_id` in body differs from authenticated client | Request rejected |
| Unregistered redirect URI | `invalid_request` or matching protocol error |
| Disallowed response type/grant type | Request rejected |
| Missing required parameter | `invalid_request` |
| Malformed PKCE challenge or disallowed method | Rejected per PKCE policy |
| Nonexistent request URI | `invalid_request_uri` |
| Expired request URI | `invalid_request_uri` |
| Client A uses a request URI belonging to Client B | Rejected; never leaks B's request data |
| Request alters parameters at the authorization endpoint | Server continues using pushed data or rejects per PAR rules |
| Sending excessive PAR requests | Rate limiting or protective policy enforced |

Test `request_uri` reuse behavior according to the policy and specification enforced by your implementation. If the system requires single-use request URIs, include a replay test verifying the second use is rejected. Even if policy permits reuse within a window, `request_uri` must remain unpredictable, time-bounded, and bound to the client.

### 4.6. Testing expiration and stored data

Do not use long `Thread.sleep` calls in functional tests to wait for PAR expiration. Configure a short TTL in the test profile, use a controllable Clock if supported by the implementation, or test via integration tests with simulated time.

Verify:

- `expires_in` matches the TTL advertised by the server.
- Expired requests cannot proceed with authorization.
- One client's request URI cannot be used by another client.
- Server restarts do not lose requests if the architecture requires durable PAR state; if state is transient only, post-restart behavior must be clearly defined.
- Replicas share access to PAR state if a load balancer can route subsequent requests to another instance.

## 5. Testing client authentication

Client authentication verifies the application calling an endpoint. It differs from End-User authentication: client authentication does not prove a user is logged in.

### 5.1. Common methods matrix

| Method | Submitted credential | Key checks |
|---|---|---|
| `client_secret_basic` | Client ID and secret in HTTP Basic Authorization | Right secret, right encoding, no conflicting duplicate credentials |
| `client_secret_post` | Client ID and secret in form body | Enable only when needed; reject wrong secrets and invalid body credentials |
| `client_secret_jwt` | JWT client assertion signed with shared secret | Signature, algorithm, iss/sub, aud, exp, and jti |
| `private_key_jwt` | JWT client assertion signed with client's private key | Signature against registered public key/JWKS, iss/sub, aud, exp, and jti |
| `tls_client_auth` | Client certificate issued by a trusted CA | Chain, validity, subject/SAN mapping, and client registration |
| `self_signed_tls_client_auth` | Registered/trusted self-signed certificate | Certificate fingerprint/key binding and client mapping |
| `none` | No client secret; public client identified by client_id | Allowed only on appropriate endpoints/flows; PKCE required for authorization code |

Enable only methods the server genuinely supports and has credential management processes for. Never accept a method merely because the client declared it in registration metadata.

### 5.2. Testing client_secret_basic

Illustrative request to the token endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=api.read
~~~

Test example:

~~~java
@Test
void shouldAuthenticateConfidentialClientWithBasic() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("service-client", "test-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "api.read"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

Ensure the test client is registered with:

- `ClientAuthenticationMethod.CLIENT_SECRET_BASIC`.
- `AuthorizationGrantType.CLIENT_CREDENTIALS`.
- Scope `api.read` permitted.
- Secret encoded with the matching PasswordEncoder.

Negative cases include wrong secret, nonexistent client ID, disabled client, disallowed grant type, and malformed credentials. For client authentication failures, verify the response contains `invalid_client` and does not reveal which client IDs exist.

### 5.3. Testing client_secret_post

With this method, the client sends credentials in the form body:

~~~bash
curl -i -X POST https://auth.example.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=legacy-client" \
  -d "client_secret=$CLIENT_SECRET"
~~~

Accept body credentials only if the client registered `client_secret_post`. Also test the case where a client registered `client_secret_basic` but sends its secret in the body; the server must enforce the configured auth method rather than silently downgrading or trying every method.

### 5.4. Testing private_key_jwt

With `private_key_jwt`, the client builds a JWT assertion and signs it with its private key. The Authorization Server uses the registered public key to verify it.

Claims typically checked:

- `iss` and `sub` identify the client per client authentication requirements.
- `aud` matches the audience the Authorization Server accepts for the target endpoint.
- `exp` is within the allowed time window.
- `jti` is unique to support replay detection.
- Header `alg` belongs to algorithms permitted by the server; `kid` points to the registered public key.

Illustrative request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=jwt-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=<SIGNED-CLIENT-ASSERTION>
~~~

Tests must create assertions using a test private key whose corresponding public JWKS is registered for the client. Never use the Authorization Server's private key to sign client assertions.

Negative test matrix:

| Assertion | Expected result |
|---|---|
| Valid signature, right audience, unexpired | Client authentication succeeds |
| Wrong signature or mismatched public key | `invalid_client` |
| `iss` or `sub` does not match client | `invalid_client` |
| Audience not accepted by server | `invalid_client` |
| Expired assertion | `invalid_client` |
| `jti` replayed within replay-prevention window | Duplicate assertion rejected |
| Algorithm not on allowlist | Assertion rejected |
| `kid` not found | Assertion rejected |

### 5.5. Testing client_secret_jwt

This method uses the client's shared secret to sign the JWT assertion. Tests must verify allowed MAC algorithms, valid signatures, and valid assertion claims.

Never accept `alg=none`. Do not use symmetric algorithms outside the allowlist or low-entropy secrets. If the server does not enable `client_secret_jwt`, requests must be rejected rather than falling back to `client_secret_basic`.

### 5.6. Testing mTLS client authentication

mTLS requires a real TLS connection so the server receives the client certificate. Pure MockMvc does not fully simulate the TLS handshake and certificate mapping at the connector/proxy.

For mTLS tests, use an embedded server or an integration environment with HTTPS, separate test keystores/truststores, and trustworthy certificate-forwarding configuration if TLS terminates at a proxy.

Cases to check:

- Certificate issued by a trusted CA and matching client registration.
- Expired or not-yet-valid certificate.
- Certificate not in the trust chain.
- Subject DN or SAN mismatching client metadata.
- Client A's certificate used with Client B's client ID.
- Revoked certificate if the system performs CRL/OCSP checks.
- Proxy prevents clients from spoofing certificate headers.

If TLS terminates at ingress, trust forwarded certificate headers only when the proxy strips client-supplied headers and sets its own after verifying the certificate. Never accept raw certificate headers straight from the Internet.

### 5.7. Testing public clients

A public client using `token_endpoint_auth_method=none` has no client secret. With Authorization Code Flow, verify:

- Valid client ID.
- Redirect URI matches registration.
- PKCE is enforced per policy.
- Token request carries a `code_verifier` matching the challenge.
- Client cannot send a fake client secret to be promoted to a confidential client.
- Public clients cannot use grant types or scopes beyond policy.

Never use the client credentials grant for a public client in place of user authentication.

## 6. Testing consistency across registration, PAR, and the token endpoint

Features must work together properly. A client that registers successfully yet cannot authenticate using its registered method is still a functional bug.

An integrated flow should:

1. Register a confidential client with redirect URI, authorization code grant, scopes, and `private_key_jwt` or `client_secret_basic`.
2. Read the client back via `RegisteredClientRepository` to verify metadata was persisted.
3. Send PAR using the exact client authentication method.
4. Receive `request_uri` and redirect the browser to the authorization endpoint.
5. Complete user authentication and consent.
6. Exchange the authorization code at the token endpoint using the matching client authentication and PKCE verifier if applicable.
7. Verify the token response and granted scopes.
8. Retry with wrong credentials or another client to confirm the server rejects properly.

Public client flows need their own dedicated test: registration with `none`, PAR per public client policy, authorization code with PKCE, and token requests without a secret.

## 7. Suggested functional test suite

### 7.1. Registration test matrix

| ID | Scenario | Outcome |
|---|---|---|
| REG-01 | Register valid web client | Client created, client ID returned |
| REG-02 | Register native public client | Client created without secret, PKCE applied |
| REG-03 | Invalid redirect URI | Registration rejected |
| REG-04 | Disallowed grant/response type | Registration rejected |
| REG-05 | Unsupported auth method | Registration rejected |
| REG-06 | Registration missing permission/initial access token | Rejected if endpoint is protected |
| REG-07 | Read client back from repository | Metadata persisted accurately |
| REG-08 | Confidential client secret | Response secret usable; repository keeps encoded value |
| REG-09 | Oversized/malformed registration request JSON | Safely rejected |

### 7.2. PAR test matrix

| ID | Scenario | Outcome |
|---|---|---|
| PAR-01 | Valid PAR with right client authentication | Returns request URI and expires_in |
| PAR-02 | Wrong client authentication | Rejected |
| PAR-03 | Unregistered redirect URI | Rejected |
| PAR-04 | Request missing response_type or client_id | Rejected |
| PAR-05 | Authorization endpoint uses valid request_uri | Continues authorization flow |
| PAR-06 | Nonexistent request URI | invalid_request_uri |
| PAR-07 | Expired request URI | invalid_request_uri |
| PAR-08 | Another client uses request_uri | Rejected |
| PAR-09 | Front-channel parameter altered | Does not alter pushed request |
| PAR-10 | Replay request_uri | Behavior matches chosen replay policy |

### 7.3. Client authentication test matrix

| ID | Scenario | Outcome |
|---|---|---|
| AUTH-01 | Valid Basic credentials | Authentication succeeds |
| AUTH-02 | Wrong Basic secret | invalid_client |
| AUTH-03 | Valid secret post for client registered with that method | Authentication succeeds |
| AUTH-04 | Wrong auth method used | invalid_client |
| AUTH-05 | Valid private key JWT | Authentication succeeds |
| AUTH-06 | JWT assertion with wrong signature/audience/expiry | invalid_client |
| AUTH-07 | Replayed assertion jti | Rejected per replay protection |
| AUTH-08 | Valid mTLS certificate | Authentication succeeds |
| AUTH-09 | Invalid/expired mTLS certificate | TLS or client authentication fails |
| AUTH-10 | Public client with valid PKCE | Authorization code exchange succeeds |

## 8. Observing errors and protecting test data

During testing, logs need enough detail for diagnostics without containing credentials.

Safe to log:

- Test case ID and correlation ID.
- Endpoint and HTTP status.
- Synthetic client ID in the test environment.
- Authentication method name.
- OAuth error type, such as `invalid_client`, `invalid_request`, or `invalid_request_uri`.
- Processing latency and handling replica.

Never log:

- Plaintext client secrets.
- Access tokens, refresh tokens, or registration access tokens.
- Full client assertion JWTs.
- Private keys or keystore contents.
- Session cookies, authorization codes, or personal data.

If you need to debug a JWT assertion, log only non-sensitive claims after stripping replayable material, such as algorithm, key ID, expiration timestamp, and verification result.

## 9. Common issues during testing

| Symptom | Possible cause | Resolution |
|---|---|---|
| Registration endpoint returns 404 | OIDC registration endpoint not enabled or wrong path | Check configurer, metadata, and AuthorizationServerSettings |
| Registration returns 401/403 | Missing initial access token or registration protection policy | Use test credentials matching the policy |
| Registration returns client ID but repository lacks client | Test repository differs from endpoint's repository or transaction rolled back | Inject the right repository and inspect transactions |
| Secret in response cannot be used | Inconsistent PasswordEncoder or mishandled secret | Check encoder during client creation and verification |
| PAR returns 401 | Wrong auth method, secret, or client not allowed to use PAR | Check registration metadata and request authentication |
| PAR returns invalid_request | Missing parameter, wrong redirect URI, or invalid PKCE | Compare request parameters against client registration |
| Authorization endpoint reports invalid_request_uri | Wrong/expired request URI or not persisted/shared across replicas | Check TTL, PAR storage, and client binding |
| Basic auth test passes but post auth test fails | Client registered only basic or server has not enabled post | Register the exact method and check allowlist |
| private_key_jwt fails | Wrong assertion audience, signature, kid, or expiration | Compare assertion against policy and client JWKS |
| mTLS test passes in MockMvc but fails in production | MockMvc does not perform real TLS handshakes | Run HTTPS tests in an embedded server or integration environment |
| PAR works on one replica but fails on another | PAR state resides only in per-instance memory | Use a shared state store or clearly defined sticky policy |

## 10. Pre-release checklist

- [ ] The Spring Authorization Server version supports all enabled endpoints and auth methods.
- [ ] Discovery/metadata accurately publishes the registration endpoint and PAR endpoint if supported.
- [ ] Dynamic Client Registration is protected by an explicit policy.
- [ ] Redirect URIs, grant types, response types, scopes, and auth methods are validated.
- [ ] Confidential client secrets are generated securely and stored encoded.
- [ ] Public clients receive no secret and must use PKCE per policy.
- [ ] PAR authenticates clients against registered metadata.
- [ ] PAR returns an unpredictable request URI and valid expires_in.
- [ ] Request URIs are bound to the client and expire on schedule.
- [ ] The authorization endpoint uses the pushed parameters.
- [ ] Client authentication methods at token/PAR endpoints match registration.
- [ ] `private_key_jwt` validates signature, iss, sub, aud, exp, jti, and kid.
- [ ] mTLS is tested over real HTTPS, certificate mapping, and proxy trust.
- [ ] Negative tests verify wrong credentials, assertion replay, client mismatch, and expired request URIs.
- [ ] Replicas share client registrations and PAR state per architectural requirements.
- [ ] Logs never record secrets, tokens, full assertions, or private keys.
- [ ] Integration tests cover registration through PAR to the token endpoint.

Testing DCR confirms the server creates clients only with permitted metadata. Testing PAR confirms authorization requests are accepted, bound to clients, and used within their lifetime. Testing client authentication confirms each endpoint accepts only the exact registered method. Combining all three test groups in one integrated flow catches configuration errors, persistence bugs, and authorization gaps early before deploying the Authorization Server.
