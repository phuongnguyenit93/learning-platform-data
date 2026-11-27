# invalid_client: Secret, Authentication Method, Assertion, and Certificate

The `invalid_client` error occurs when the Authorization Server cannot authenticate the OAuth2 client at the endpoint processing the request. The cause may be a nonexistent client ID, an incorrect or expired client secret, an authentication method that does not match the registered configuration, an invalid JWT client assertion, or an untrusted TLS certificate. These causes have different inspection steps; repeatedly rotating secrets or switching every client to another authentication method often masks the root error.

With Spring Authorization Server, client authentication is tied to `RegisteredClient`, `ClientAuthenticationMethod`, and the `AuthenticationConverter`/`AuthenticationProvider` implementations handling the endpoint. This guide walks through identifying the method the client is using, checking the corresponding credentials and configuration, and then re-verifying with safe test requests.

## 1. Understanding invalid_client Correctly

OAuth2 client authentication verifies the application calling the Authorization Server. This is the identity of the client, separate from the identity of the end user. For example, a user may log in successfully while the token request is still rejected because the client sends an incorrect secret.

Distinguishing common errors:

| Error | Common Meaning | Investigation Direction |
|---|---|---|
| invalid_client | The client could not be authenticated using the submitted method | Client ID, secret, assertion, certificate, and RegisteredClient |
| unauthorized_client | The client authenticated, but is not permitted to use the grant or operation | Grant types and client policy |
| unsupported_grant_type | The token endpoint does not support the submitted grant type | Version, extensions, and provider configuration |
| invalid_grant | The authorization code, refresh token, or related grant is invalid | Authorization state and token state |
| invalid_scope | The requested scope is not permitted | Registered scopes and authorization policy |
| invalid_request | The request is missing or has malformed protocol parameters | Content-Type, parameters, and encoding |

At the token endpoint, if the client sends an HTTP authentication scheme such as Basic and authentication fails, the response is typically HTTP 401 with `WWW-Authenticate`. For other methods, the status and error representation depend on the endpoint and implementation. Always read both the HTTP status and the OAuth error body; do not draw conclusions from the status code alone.

Several signs help narrow down the issue quickly:

- Error occurs before the Authorization Server processes the grant: focus on client authentication.
- Client can log in, but cannot use the grant: check `unauthorized_client` and `RegisteredClient` grant types.
- Client authenticates, but the authorization code is invalid: check `invalid_grant` and authorization state.
- Only one node fails: check client configuration, secret version, cache, and key material across instances.
- Only occurs after secret or certificate rotation: check the transition timing and the state of old/new credentials.

## 2. Identifying the Registered Authentication Method

Spring Authorization Server represents the client authentication method using `ClientAuthenticationMethod` in `RegisteredClient`. Common values include:

| Method | Submitted Credential | Verification Mechanism |
|---|---|---|
| client_secret_basic | Client ID and secret in the HTTP Basic Authorization header | Compare the secret against the stored value |
| client_secret_post | Client ID and secret in the form body | Compare the secret against the stored value |
| client_secret_jwt | JWT assertion signed with a shared secret | Verify the HMAC signature and assertion claims |
| private_key_jwt | JWT assertion signed with the client's private key | Verify the signature using the registered public key |
| tls_client_auth | Client certificate in the TLS handshake | Verify the chain and registered certificate attributes |
| self_signed_tls_client_auth | Self-signed certificate in the TLS handshake | Match against the registered certificate/thumbprint |
| none | No client secret, typically for public clients | Apply PKCE and constraints for public clients |

Specific method names and support levels should be checked against the Spring Authorization Server version and application extensions. Do not assume every endpoint or every version enables all methods in the table.

Before checking credentials, determine which client ID is calling, which endpoint receives the request, and which method the client actually sends. A client registered with `client_secret_basic` that sends `client_secret_post` will not be authenticated merely because the secret value is right. Methods are not arbitrarily interchangeable.

Example of registering a confidential client using `client_secret_basic`:

~~~java
PasswordEncoder passwordEncoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

String encodedSecret = passwordEncoder.encode(rawClientSecret);

RegisteredClient client = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientSecret(encodedSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.test/callback")
        .scope("openid")
        .scope("profile")
        .build();
~~~

The example above illustrates how to store an encoded secret using `PasswordEncoder`. In a real application, retrieve `rawClientSecret` from a secret manager when creating/issuing credentials; do not store raw secrets in source code, public configuration files, or logs. If using JDBC, verify that the `RegisteredClient` record is stored and read back with the exact encoded value.

A client can support multiple authentication methods if policy and implementation permit, but you should verify the method used on each request. Do not add methods indiscriminately just to make the error disappear; doing so can widen the authentication surface unexpectedly.

## 3. Diagnosing client_secret_basic

With `client_secret_basic`, the client sends the client ID and secret in the `Authorization` header using HTTP Basic. Common failures stem from encoding, headers altered by a proxy, mismatched secrets, or the server registering a different method.

### 3.1 Checking the Request

A token endpoint request typically looks like:

~~~http
POST /oauth2/token
Authorization: Basic <base64-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&scope=orders.read
~~~

In OAuth 2.0 Basic authentication, the client ID and client secret must be form-url-encoded individually before being joined as a username/password pair and Base64-encoded according to the protocol rules. OAuth client libraries usually handle this. If constructing the header manually, special characters such as colons, plus signs, percent signs, or Unicode characters can cause the server to decode a different value than intended.

Check:

- Is the client ID exact, including case sensitivity?
- Is the secret retrieved from the right environment and the right credential version?
- Does the client library generate the Basic header automatically, or does the application concatenate the string manually?
- Are the client ID and secret encoded according to the specification before Base64 encoding?
- Is the `Authorization` header stripped or replaced by a reverse proxy, API gateway, or filter?
- Does the request send both a Basic header and `client_id`/`client_secret` in the body, causing a conflict?
- Is the `Content-Type` of the token request `application/x-www-form-urlencoded`?

Do not decode and print the Basic header to logs for debugging. If comparison is needed, verify the secret fingerprint in the secret manager or use a controlled verification operation.

### 3.2 Checking the Stored Secret

With `PasswordEncoder`, `RegisteredClient` typically stores the encoded secret rather than plaintext. Verify:

- The stored value has the appropriate prefix for `DelegatingPasswordEncoder` if that encoder is in use.
- The encoder used when creating the client is compatible with the encoder used during authentication.
- The secret has not expired according to `clientSecretExpiresAt` or custom policy.
- The secret has not been overwritten by migrations, seed data, or deployment scripts.
- All instances read the same `RegisteredClient` record and the same encoder configuration.

If the secret was generated with BCrypt while the server compares using a different encoder, authentication will fail even when the operator uses the correct raw secret. Never compare the raw secret directly against the encoded string in the database, and do not switch to plaintext just to work around the error.

### 3.3 Errors Caused by Special Characters in the Secret

Secrets containing special characters often fail when the client manually builds the Basic header. Use a tested OAuth client library instead of manually concatenating `clientId + ":" + secret`. If a custom implementation is unavoidable, write unit tests for values containing colons, plus signs, percent signs, spaces, and Unicode characters, and compare the result against the server implementation.

Never send the secret in a URL query string. Query strings routinely appear in access logs, proxy logs, browser history, and tracing systems.

## 4. Diagnosing client_secret_post

With `client_secret_post`, the client sends `client_id` and `client_secret` in the form body of the token request. This is a separate method; the server must allow it in the client configuration. OAuth 2.0 recommends HTTP Basic when available, because credentials in the body are more easily logged by middleware or request logging.

Example request structure:

~~~http
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id=service-worker
&client_secret=<secret>
&scope=jobs.read
~~~

Check:

- Does `RegisteredClient` register `CLIENT_SECRET_POST`?
- Is the client sending the body as `form-urlencoded` rather than JSON?
- Do `client_id` and `client_secret` each appear exactly once?
- Does the HTTP client framework encode form values properly?
- Does a reverse proxy, WAF, or request wrapper strip the secret field?
- Does any filter read the request body before the token endpoint without allowing it to be re-read?
- Does the server unintentionally receive both a Basic header and body credentials?

If the application uses request logging, `client_secret` must be masked before logging the body. Do not enable global body logging on the token endpoint in production.

If the client uses Basic while `RegisteredClient` only allows POST, fix the method on one side according to the agreed policy. You should not allow both simply because one client sends a misconfigured request.

## 5. Diagnosing client_secret_jwt and private_key_jwt

These two methods use a JWT client assertion to authenticate the client at the token endpoint. The request typically contains two parameters:

- `client_assertion_type` with the value `urn:ietf:params:oauth:client-assertion-type:jwt-bearer`.
- `client_assertion` containing the JWT assertion signed by the client.

The client ID is usually sent along with the request to identify the client. Do not send `client_secret_basic` simultaneously with an assertion unless a specific profile and implementation dictate otherwise.

### 5.1 Checking the Assertion Structure

A JWT client assertion typically contains these claims:

| Claim | Meaning to Verify |
|---|---|
| iss | The client or issuer defined by the profile |
| sub | Usually the `client_id` of the authenticating client |
| aud | The Authorization Server or token endpoint per the server's audience policy |
| exp | Short expiration time in the future |
| iat | Issued-at time consistent with clock and policy |
| jti | Unique assertion ID if policy requires replay protection |
| kid | Key ID to select the right public key when using JWKS |

The header must have an allowed algorithm and appropriate key information. Never accept `alg=none`. With `private_key_jwt`, the assertion is signed with the client's private key and verified by the server with the corresponding public key. With `client_secret_jwt`, the assertion is signed with a shared secret and verified by the server using the configured HMAC signature.

A JWT that parses successfully does not mean the assertion is valid. You must check the signature, issuer/subject, audience, expiration, algorithm, key ID, and replay policy.

### 5.2 Diagnosing client_assertion_type and Assertion Parameters

If you receive `invalid_request`, check:

- Does `client_assertion_type` have the exact standard URI?
- Is `client_assertion` missing, empty, or sent multiple times?
- Does the JWT have all three parts (`header.payload.signature`)?
- Is the form body properly encoded?
- Did the request mistakenly send the assertion in the `client_secret` field?
- Are multiple client authentication methods being sent at the same time?

If you receive `invalid_client`, proceed to check the signature, key, and claims. Do not confuse an expired assertion with an expired grant; the assertion authenticates the client, whereas an authorization code/refresh token is a grant credential.

### 5.3 Diagnosing private_key_jwt

Check in order:

1. Does `RegisteredClient` allow `PRIVATE_KEY_JWT`?
2. Is the registered JWK Set URI or public key reachable from the Authorization Server?
3. Does the JWK Set contain the public key corresponding to the private key the client used to sign?
4. Does the JWT header have the right `kid` and an `alg` on the allowlist?
5. Was the signature created with the matching private key?
6. Do `iss` and `sub` match the client ID per the implemented profile?
7. Does `aud` match the audience expected by the Authorization Server?
8. Are `exp`/`iat` within the allowed time window?
9. Was `jti` replayed or was the assertion already used previously?

Common errors:

- The client rotates keys, but the JWKS URI still publishes the old key.
- The client sends a `kid` that does not exist or collides with another key's `kid`.
- The server cannot reach the JWKS due to DNS, TLS, firewall, or timeout.
- An instance's JWKS cache has not been refreshed.
- The client signs with RS256, but the server only allows a different algorithm.
- The audience uses the issuer URI when the implementation requires the token endpoint URI, or vice versa.
- Clock skew causes the assertion to be treated as not yet valid or already expired.
- The assertion is reused because the client retries the exact same old JWT.

The client assertion's audience must follow the exact profile and validator configured on the server. Do not change the audience arbitrarily based on guesswork. Check the expected value in the server configuration and sanitized diagnostic logs.

### 5.4 Diagnosing client_secret_jwt

With `client_secret_jwt`, the server needs to verify HMAC using the shared secret. Check:

- Does `RegisteredClient` allow `CLIENT_SECRET_JWT`?
- Do the client and server share the same raw shared secret and the same HMAC algorithm?
- Was the secret rotated on one side without updating the other?
- Does the secret have sufficient length and entropy for the chosen algorithm?
- Does the JWT header `alg` match the policy?
- Are the claims `iss`, `sub`, `aud`, `exp`, `iat`, and `jti` valid?

An important storage design point: HMAC requires the original key to verify the signature. A one-way hash of the client secret cannot be used directly as an HMAC key. If the system stores secrets as irreversible hashes, supporting `client_secret_jwt` requires an appropriate shared-key management mechanism, such as a controlled encrypted secret store or a different credential design. Do not store plaintext secrets in the database just to make assertions work.

Unless `client_secret_jwt` is strictly required, `private_key_jwt` generally avoids sharing an HMAC secret between two parties, though it still requires managing the client's private key, public key registration, and safe rotation.

## 6. Diagnosing TLS Client Authentication

TLS client authentication authenticates the client using a certificate during the TLS handshake. Two common methods are `tls_client_auth` and `self_signed_tls_client_auth`. Configurability and support depend on the Spring Authorization Server version, Spring Security, servlet container, and TLS/proxy infrastructure.

Distinguish the two layers:

- TLS server authentication: the client verifies the Authorization Server's certificate.
- TLS client authentication: the Authorization Server or TLS terminator verifies the client's certificate.

A client trusting the server's certificate does not mean the server has authenticated the client's certificate.

### 6.1 Checking the TLS Handshake

If the error occurs before the HTTP request reaches Spring, inspect the TLS terminator, ingress, load balancer, or servlet container:

- Does the listener request or accept client certificates?
- Does the client send a certificate during the handshake?
- Is the certificate still valid (not expired) and within a trusted chain?
- Does the certificate have the appropriate Extended Key Usage for client authentication?
- Does the certificate chain include all intermediate certificates?
- Does the truststore contain the necessary CA certificates?
- Are the TLS version and cipher suite compatible?
- Has the certificate been revoked or is it no longer accepted by policy?

If the TLS handshake fails, the application may not produce an OAuth error response because the request never reached the token endpoint. In that case, look at logs on the ingress/TLS terminator rather than only in Spring Authorization Server.

### 6.2 Checking Certificate-to-Client Mapping

With `tls_client_auth`, the server must match the client certificate against registered details per the profile, such as the subject DN or matching SAN DNS/URI/IP/email. With `self_signed_tls_client_auth`, the certificate/thumbprint must match the value registered for the client.

Check:

- Does the submitted certificate correspond to the client ID being used?
- Does the Subject DN or SAN match the registered metadata?
- Is the SHA-256 thumbprint computed over the exact DER certificate?
- Is the client using a new certificate while `RegisteredClient` still holds the old certificate information?
- Are multiple certificates mapped to one client according to policy?
- Is the certificate sent over the right TLS connection to the right endpoint?

Do not map certificates solely by Common Name if the policy requires SAN or a stronger identifier. Do not accept a certificate merely because it is signed by a trusted CA; that certificate must also be bound to the specific client.

### 6.3 TLS Termination at a Reverse Proxy

If TLS terminates at a load balancer, Spring Authorization Server may not see the client certificate in the TLS connection. Some architectures forward certificate details via internal headers. In that case:

- The proxy must verify the certificate before forwarding.
- The proxy must strip any certificate headers sent externally by the client.
- Internal headers must only travel over a protected proxy-to-application channel.
- The application must only trust headers from explicitly identified proxies.
- Clients must never be allowed to call the application endpoint directly and spoof certificate headers.
- Logs must distinguish certificates obtained from an actual TLS handshake from metadata forwarded by a proxy.

If the proxy cannot reliably forward certificate identity, use TLS passthrough or configure mTLS directly between the client and the component responsible for authentication.

### 6.4 Certificate Rotation

When a client replaces a certificate, there can be a transition period:

1. Register the new certificate and verify its certificate chain/thumbprint.
2. Configure the server to accept the new certificate according to approved policy.
3. Switch the client to use the new certificate.
4. Monitor successful authentication across all instances.
5. Remove the old certificate after the transition is complete and the compatibility window expires.

Do not remove the old certificate before the client has finished switching if an overlap window is needed. Conversely, never retain a compromised certificate just to avoid disruption; trigger the incident response process instead.

## 7. Checking RegisteredClient and Storage State

When client authentication fails only in one environment or on one instance, compare the `RegisteredClient` data that each node actually reads. Check:

- Does the client ID exist and is it unique?
- Does the client authentication method match the request?
- Is the client secret encoded properly with the same encoder configuration?
- Has `clientSecretExpiresAt` expired?
- Is the JWK Set URI correct and reachable?
- Does the certificate subject/SAN/thumbprint match?
- Are grant types and client settings deployed consistently?
- Is the `RegisteredClient` cache stale after rotating a secret or key?

With a JDBC repository, verify that the data is committed and the schema is on the right version. With a custom repository or cache, verify invalidation/update propagation to all nodes. Avoid editing the production database directly to "test" a secret; use an audited credential management workflow.

A common mistake is running a new client seed in only one environment while other instances use a different database or cache. Another is a node still running stale configuration after a rolling deployment. Record the instance ID and client ID in sanitized logs to identify which node handled the request.

## 8. Distinguishing Client Authentication Errors from Grant and Resource Errors

Do not rotate the client secret when the actual fault lies in the authorization grant or Resource Server.

| Symptom | Is It invalid_client? | Check |
|---|---|---|
| Wrong secret at token endpoint | Yes | Secret, encoder, method |
| Expired client assertion | Yes | `exp`, `iat`, clock |
| Untrusted client certificate | Possibly yes; or TLS handshake fails before HTTP | TLS trust, mapping, proxy |
| Client authenticates, but grant is not permitted | No, usually `unauthorized_client` | `RegisteredClient` grant types |
| Expired/reused authorization code | No, usually `invalid_grant` | Authorization state |
| Valid token, but API returns 403 | No | Scope/authority/audience at Resource Server |
| Disallowed scope | No, usually `invalid_scope` | Client scopes and authorization policy |
| Request missing assertion type | Usually `invalid_request` | Request parameters |

If the token endpoint returns `invalid_client`, verify client authentication before investigating the subject or authorization code. If client authentication succeeds but the grant fails, move on to checking authorization state.

## 9. Safe Logging and Observability

Log enough data to classify the cause without recording credentials. Suggested fields:

| Field | Recorded Value |
|---|---|
| event_type | `CLIENT_AUTHENTICATION_FAILED` |
| client_id | Client ID if identified |
| authentication_method | `client_secret_basic`, `private_key_jwt`, `tls_client_auth`... |
| endpoint | Token endpoint or endpoint processing the request |
| failure_category | `SECRET_MISMATCH`, `ASSERTION_INVALID`, `CERTIFICATE_UNTRUSTED`... |
| instance_id | Node handling the request |
| correlation_id | Request correlation ID |
| occurred_at | UTC timestamp |
| source | IP/proxy identity if policy permits |

Do not log:

- `client_secret` or the Basic `Authorization` header.
- Raw `client_assertion`, signatures, or the full JWT.
- Private keys, shared keys, or keystore passwords.
- The full certificate chain if logs are not tightly controlled; if matching is needed, log the thumbprint and non-sensitive metadata.
- Full request bodies at the token endpoint.

You can create metrics counting errors by authentication method, failure category, and normalized client group. Do not use raw client IDs as metric labels if client counts are large or the data is sensitive. Monitor the `invalid_client` rate per instance to catch configuration drift after deployments or rotations.

## 10. Test Matrix and Fix Verification

After identifying the cause, reproduce it with a dedicated test client. Each test should change only one factor and check both the response and that no token is issued.

| Test ID | Input | Expected Result |
|---|---|---|
| BASIC-01 | Nonexistent client ID | `invalid_client` |
| BASIC-02 | Wrong secret | `invalid_client` |
| BASIC-03 | Right secret, mismatched method | `invalid_client` |
| BASIC-04 | Secret expired per policy | Client authentication rejected |
| POST-01 | `client_secret_post` not registered | Rejected |
| POST-02 | Missing `client_secret` or wrong form encoding | Rejected |
| JWT-01 | Wrong `client_assertion_type` | `invalid_request` or corresponding assertion error |
| JWT-02 | Assertion with invalid signature | `invalid_client` |
| JWT-03 | Expired assertion or excessive `iat` skew | `invalid_client` |
| JWT-04 | Audience mismatch | `invalid_client` |
| JWT-05 | `kid` not present in JWKS | `invalid_client` |
| JWT-06 | Replayed assertion | Rejected per replay policy |
| MTLS-01 | No client certificate sent | TLS/client authentication failure |
| MTLS-02 | Untrusted certificate chain | Rejected |
| MTLS-03 | Valid certificate, does not match client | `invalid_client` or TLS mapping error |
| MTLS-04 | Old certificate after revocation | Rejected |
| NODE-01 | Same request to two instances after credential rotation | Consistent result |

After every fix, verify:

1. A client using the registered method can authenticate.
2. Invalid secrets/assertions/certificates are still rejected.
3. Disallowed grant types still return `unauthorized_client`.
4. Invalid authorization codes or refresh tokens are still rejected independently of client authentication.
5. No access token/refresh token is issued from a request where client authentication fails.
6. Every instance applies the same credential version, key set, and trust configuration.
7. Logs contain no raw secrets, assertions, tokens, or private keys.

For secret or certificate rotation, test both the transition period and the state after the old credential is removed. For `private_key_jwt`, check the JWKS cache and key ID across all instances. For mTLS, verify the handshake at the exact TLS termination point.

## 11. Production Incident Workflow

When an `invalid_client` incident occurs in production:

1. Record the timestamp, correlation ID, endpoint, client ID, and instance; do not store credentials.
2. Identify whether the client is using Basic, POST, JWT assertion, or mTLS.
3. Compare the submitted method with the method in `RegisteredClient`.
4. Inspect secret expiry/encoder, assertion claims/signature/JWKS, or certificate chain/mapping depending on the method.
5. Compare configuration and `RegisteredClient` data across instances.
6. Check proxy, TLS termination, clock, cache, and JWKS/KMS connectivity if applicable.
7. Reproduce with a test client and confirm the error before changing credentials.
8. Apply rotation or fix configuration through the credential management workflow; monitor authentication rates after the change.

If you suspect a secret, private key, or certificate has been exposed, treat it as a credential compromise incident: revoke or rotate the credential, audit access logs, identify affected clients and tokens, and notify according to internal procedures. Never put credentials in a ticket for someone else to retry.

A good incident report clearly states the authentication method, root cause, affected client/instance scope, credential/configuration changes, negative tests run, and evidence that no further tokens were issued improperly. This helps distinguish routine integration errors from incidents carrying credential exposure risk.

By accurately identifying the authentication method and checking credentials at the client authentication boundary, `invalid_client` errors can be isolated without weakening OAuth2 policy. `RegisteredClient`, secret encoders, JWT assertion validators, and TLS trust must remain synchronized across instances so client authentication behaves reliably throughout the deployment lifecycle.
