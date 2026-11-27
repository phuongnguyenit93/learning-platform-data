# Validating jwks, jwks_uri, and Client-Declared Algorithms

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect Authorization Server** system using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, Dynamic Client Registration (DCR) allows an application to register with an OpenID Provider (OP) via a request containing metadata instead of creating each client manually. Metadata may include redirect URIs, grant types, client authentication methods, a JWK Set address, and JOSE algorithms the client wishes to use.

Some metadata directly affects trust boundaries:

- `jwks_uri` points to a public JWK Set managed by the client.
- `jwks` embeds a JWK Set directly in the registration request.
- `token_endpoint_auth_signing_alg` declares the algorithm the client uses to sign authentication JWTs at the Token Endpoint.
- `request_object_signing_alg` declares the algorithm the client uses to sign Request Objects sent to the OP.
- `id_token_signed_response_alg` asks the OP to sign ID Tokens for the client with a specific algorithm.
- JWE fields declare how to encrypt ID Tokens or UserInfo responses for the client.

If the OP only checks that JSON is valid and stores the metadata, a client could register a URL pointing to an internal network, supply a public key incompatible with the algorithm, declare weak algorithms, or create an unworkable configuration. Specifically, when the OP fetches a client-provided `jwks_uri` to verify `private_key_jwt` or Request Objects, an untrusted URL can become an SSRF vector from the Authorization Server.

Running example: a partner registers client `partner-service` and wants to use `private_key_jwt`. The partner declares `jwks_uri=https://partner.example.com/.well-known/jwks.json`, `token_endpoint_auth_signing_alg=PS256`, and `request_object_signing_alg=ES256`. The OP must verify that the public endpoint is safe, the JWK Set contains only appropriate public keys, there are keys compatible with PS256 and ES256, and client-signing algorithms are not confused with the algorithm the OP uses to sign ID Tokens.

After this lesson, you will be able to:

1. Distinguish `jwks_uri` and `jwks` per OIDC Dynamic Client Registration.
2. Identify who uses each key and algorithm in a client's JWK Set.
3. Validate HTTPS, SSRF, DNS rebinding, redirects, and limits when fetching remote JWKS.
4. Validate public JWKs, key types, curves, key use, key operations, `alg`, `kid`, and certificate chains.
5. Distinguish JWS signing algorithms from JWE key-management/content-encryption algorithms.
6. Validate algorithms per `token_endpoint_auth_method`, Request Object, and ID Token response.
7. Configure Spring Authorization Server 1.5.x validators to preserve default checks while adding allow-lists.
8. Persist metadata into `RegisteredClient` and verify configuration read-back.
9. Test rotation, key mismatches, failing endpoints, and unsafe registration requests.

**Version scope:** Examples use Spring Authorization Server **1.5.8**, Spring Security **6.x**, and the Servlet stack. DCR APIs are illustrated with `OidcClientRegistrationAuthenticationProvider`, `OidcClientRegistrationAuthenticationValidator`, `OidcClientRegistration`, and `RegisteredClient.ClientSettings`. DCR is disabled by default; enable it only when the system has an appropriate registration authorization policy.

## 2. What Is a Client's JWK Set Used For?

### 2.1. A Client May Own Multiple Key Pairs

An OIDC client may hold private keys in an HSM, keystore, or KMS. The OP only needs public keys to verify client signatures or encrypt responses sent to the client. The client publishes public keys as a JSON Web Key Set (JWKS).

A JWKS has the structure:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "PS256",
      "kid": "partner-auth-2026-01",
      "n": "base64url-rsa-modulus",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "use": "enc",
      "alg": "ECDH-ES+A256KW",
      "kid": "partner-encryption-2026-01",
      "crv": "P-256",
      "x": "base64url-x-coordinate",
      "y": "base64url-y-coordinate"
    }
  ]
}
~~~

Key values in the example are placeholders, not usable key material. The first RSA key is used to verify client signatures; the second EC key is used for response encryption if the OP supports the corresponding algorithm.

### 2.2. Direction of Key Usage

| Requirement | Who signs/encrypts? | Which key does the OP use? |
| --- | --- | --- |
| `private_key_jwt` at Token Endpoint | Client signs JWT assertion with client's private key. | OP uses public key in client's JWKS to verify. |
| Signed Request Object | Client signs Request Object with client's private key. | OP uses client's public signing key to verify. |
| Encrypted ID Token | OP encrypts ID Token for the client. | OP uses public encryption key in client's JWKS. |
| Encrypted UserInfo response | OP encrypts UserInfo response for the client. | OP uses public encryption key in client's JWKS. |
| ID Token JWS signature | OP signs ID Token with OP's private key. | Client fetches public key from the **OP's JWKS**, not the client's JWKS. |

The last distinction in the table is especially important: `jwks_uri` in a registration request is the **client's** key location. It is not the Authorization Server's `jwks_uri` in OpenID Provider Discovery. Both parties may publish JWKS, yet each JWKS serves a different trust direction.

### 2.3. Not Every Client Needs JWKS

`jwks_uri` is usually needed when a client uses asymmetric signing mechanisms, such as `private_key_jwt` or signed Request Objects. A client using only `client_secret_basic` does not need a public signing key for client authentication. `client_secret_jwt` uses a shared secret for MAC signing and therefore does not read keys from JWKS.

If a client asks the OP to encrypt ID Tokens/UserInfo with the client's public key, the OP needs an appropriate encryption key regardless of which authentication method the client uses at the Token Endpoint.

Do not require every client to submit JWKS. Inspect the metadata and features chosen by the client to determine what key material is actually necessary.

## 3. How Do jwks_uri and jwks Differ?

### 3.1. jwks_uri — Referencing a Remote JWKS

Registration metadata example:

~~~json
{
  "client_name": "Partner Service",
  "redirect_uris": [
    "https://partner.example.com/oidc/callback"
  ],
  "token_endpoint_auth_method": "private_key_jwt",
  "token_endpoint_auth_signing_alg": "PS256",
  "jwks_uri": "https://partner.example.com/.well-known/jwks.json"
}
~~~

The OP stores the URL and can fetch the JWKS when it needs to verify JWTs or encrypt responses. Advantages:

- The client can rotate keys without re-registering just to replace JWKS.
- The OP can retrieve new keys per cache/revalidation policy.
- Registration requests stay small without transmitting the entire public key set.

OIDC Dynamic Client Registration stipulates that the `jwks_uri` URL **MUST use the HTTPS scheme**. TLS must properly verify hostname and certificate chain; plain HTTP must not be accepted for public deployments.

### 3.2. jwks — Passing JWKS Directly in the Request

Example:

~~~json
{
  "client_name": "Native Partner",
  "redirect_uris": [
    "com.example.partner:/oauth2redirect"
  ],
  "token_endpoint_auth_method": "private_key_jwt",
  "token_endpoint_auth_signing_alg": "RS256",
  "jwks": {
    "keys": [
      {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "native-client-key-01",
        "n": "base64url-rsa-modulus",
        "e": "AQAB"
      }
    ]
  }
}
~~~

The JWKS is passed **by value** and stored as part of the client metadata. This can be useful for clients that have nowhere to host a JWKS URL. However:

- The OP does not automatically pick up new keys when the client rotates.
- Changing keys requires updating the registration via the Client Configuration Endpoint or an admin workflow.
- Payloads are larger and require request size limits.
- The OP must store and version key sets per client.

### 3.3. The Two Fields Are Mutually Exclusive

Under OIDC Dynamic Client Registration 1.0:

- `jwks_uri` and `jwks` **MUST NOT** appear together in the same request/registration.
- If a client can use `jwks_uri`, the client **MUST NOT** use `jwks`.
- A JWKS must not contain private keys or symmetric key values.

Do not arbitrarily pick one field when both are present. Reject the registration with an appropriate metadata error and require the client to submit exactly one mechanism.

### 3.4. Spring Authorization Server 1.5.8 Support

In the standard Spring Authorization Server 1.5.8 API:

- `OidcClientRegistration.Builder.jwkSetUrl(...)` represents the `jwks_uri` metadata.
- `OidcClientMetadataClaimAccessor.getJwkSetUrl()` provides the JWKS URL.
- `RegisteredClient.ClientSettings.Builder.jwkSetUrl(...)` stores the URL in client settings.
- The public builder does not have a dedicated `jwks(...)` method to store an inline JWK Set.

Therefore, when using default mapping, prefer `jwks_uri`. If the product strictly requires supporting inline `jwks`, you need custom request/metadata converters and structured storage for the JWK Set; updates, rotation, read responses, and key protection must be designed separately. Do not assume an unrecognized JSON field will automatically map to `ClientSettings.jwkSetUrl`.

## 4. Validating JWK Set Structure and Contents

### 4.1. Checking the JSON Envelope

A JWKS must be a JSON object with a `keys` property that is an array of JWKs. Verify:

- The body is non-empty and valid JSON.
- `keys` exists, is an array, and its length is within limits.
- Each element is a JSON object with a valid `kty`.
- No duplicate keys cause ambiguity during selection.
- Total response size, key count, and individual field sizes are bounded.
- Reject duplicate JSON members or payloads parsed inconsistently across parsers.

Invalid response example:

~~~json
{
  "keys": "not-an-array"
}
~~~

Or a JWK missing `kty`:

~~~json
{
  "keys": [
    {
      "kid": "key-01",
      "alg": "RS256"
    }
  ]
}
~~~

`kty` is a REQUIRED member of a JWK under RFC 7517. Do not infer key type solely from the algorithm name.

### 4.2. Reject Private or Symmetric Key Values

OIDC Dynamic Client Registration requires a client's JWK Set not to contain private or symmetric key values. Fields to detect:

| Key type | Private/sensitive fields to reject |
| --- | --- |
| RSA | `d`, `p`, `q`, `dp`, `dq`, `qi`, `oth` |
| EC | `d` |
| OKP | `d` |
| oct | `k` (symmetric key material) |

A public RSA JWK typically has `n` and `e`; a public EC JWK has `crv`, `x`, `y`; a public OKP JWK has `crv` and `x`. Never put private parameters into registration responses, database logs, exceptions, or audit events.

If private/symmetric key material is detected, reject the registration and treat it as a sensitive-data incident: do not log the raw request, restrict log access, and notify the client to replace its keys.

### 4.3. Checking use and key_ops

`use` describes the public key's intended use:

- `sig`: signature verification.
- `enc`: encryption or key agreement.

`key_ops` describes specific operations, such as `verify`, `encrypt`, or `wrapKey`. RFC 7517 recommends against using `use` and `key_ops` together; if both appear, they **MUST** be consistent.

OIDC Registration specifies that when a JWKS contains both signing and encryption keys, `use` must be declared on all keys to indicate their purpose. Using separate keys for signing and encryption is recommended; reusing the same key for both purposes is less safe than keeping them separate.

Do not strip out all `use=enc` keys before processing the rest of the metadata. Select keys according to the specific operation:

- Verifying client assertion: needs a key intended for signature/verify.
- Verifying a signed Request Object: needs a public signing key.
- Encrypting ID Token/UserInfo: needs an encryption key matching the JWE algorithm.

### 4.4. Checking alg and Key Type

`alg` in a JWK is optional metadata, but if present it must match the algorithm actually used with the key. Some rules:

| JWS/JWE algorithm | Key type and typical conditions |
| --- | --- |
| `RS256`, `RS384`, `RS512` | RSA; sufficiently strong modulus. |
| `PS256`, `PS384`, `PS512` | RSA; crypto provider supports RSA-PSS. |
| `ES256` | EC curve P-256. |
| `ES384` | EC curve P-384. |
| `ES512` | EC curve P-521. |
| `ECDH-ES`, `ECDH-ES+A256KW` | EC/OKP key agreement on a JWA-supported curve; do not use as a JWS signing key. |
| `RSA-OAEP`, `RSA-OAEP-256` | Suitable RSA public encryption key. |

Do not accept an EC P-384 JWK just because metadata declares ES256; do not accept an RSA JWK for ES256; do not use an encryption key to verify signatures.

If a JWK omits `alg`, the OP must still verify that the key fits `kty`, curve, `use`/`key_ops`, and the allow-list of the algorithm being processed. Omitting `alg` does not mean every algorithm is allowed.

### 4.5. kid and Key Selection

`kid` is a key identifier that helps locate the right key in a JWKS. RFC 7517 does not mandate `kid` on every JWK, yet production policy should require a unique `kid` for each key used for signing or encryption, especially during rotation.

When verifying a JWT:

1. Read the protected header and extract `alg`, plus `kid` if present.
2. Apply the endpoint/client algorithm allow-list.
3. Filter keys by `kid`, `kty`, curve, `use`/`key_ops`, and `alg`.
4. If no key matches, reject.
5. If multiple keys match and no unique selection can be made, reject rather than trying keys without bound.
6. Verify the signature and JWT claims per protocol.

Never treat `alg` from the JWT header as the sole source of truth. The algorithm must be in the server-approved policy and compatible with the selected key.

### 4.6. x5c and X.509 Certificates

A JWK may contain `x5c` as a certificate chain. If used:

- The public key in the first certificate must match the JWK's public key parameters.
- `x5c` values must be parsed and checked against PKI policy.
- Do not treat the presence of a certificate as automatically trusting the client; dedicated trust anchors and certificate validation rules are required.
- Do not omit base key parameter fields just because `x5c` is present.

X.509 certificates in JWKs and mTLS client authentication are two mechanisms that can complement each other, but they are not identical. `jwks_uri` does not replace TLS client certificate verification.

A JWK may also declare `x5u`, a URL referencing a certificate chain. If the JOSE library fetches this URL automatically, it creates another outbound request controlled by client metadata. Apply the same SSRF, TLS, redirect, and response-size policies as when fetching `jwks_uri`; if there is no clear use case, prefer validated `x5c` or reject `x5u`.

## 5. Validating jwks_uri and Preventing SSRF

### 5.1. HTTPS Is Only the First Step

The `jwks_uri` URL must use HTTPS. However, HTTPS **does not by itself prevent SSRF**. An HTTPS URL can still point to:

- Loopback addresses such as `127.0.0.1` or `::1`.
- Private networks such as RFC 1918 or IPv6 unique-local.
- Cloud metadata services or management endpoints.
- Internal hosts resolvable only via the Authorization Server's DNS.
- Public domains whose DNS can change to point to internal IPs.
- Redirect chains leading from a public hostname to an internal address.

The OP makes the outbound request, so the OP's network privileges can be abused if it fetches JWKS from a URL controlled by an untrusted registrant.

### 5.2. URL Checks at Registration Time

URL policy should check:

- Scheme is `https`.
- No username/password in the authority.
- No fragment.
- Host is valid and can be safely canonicalized.
- Port is allowlisted or uses the policy's default port.
- Disallow `localhost`, literal IPs, private/link-local/multicast/reserved addresses unless required by the use case.
- If needed, hostname belongs to an approved domain list.
- Block IP-encoded URLs, IPv4 shorthand, IPv6 zone identifiers, and parser ambiguities.

Do not just call `URI.getHost()` and declare it safe. URL parsers, DNS resolvers, HTTP clients, and proxies can interpret URLs differently. Validate at both the URL parser layer and the network egress layer.

### 5.3. DNS Rebinding and Redirects

A domain might resolve to a public IP during registration yet return a private IP on a subsequent resolution. Therefore:

1. Validate hostnames and DNS as needed.
2. At connection time, verify the actual destination address against network policy.
3. Avoid letting the HTTP client follow redirects without restriction.
4. If redirects are allowed, re-validate scheme, host, DNS, and destination address at every hop.
5. Block transitions from public hostnames to private/internal destinations.
6. Ensure TLS hostname verification remains enabled across all redirects.

Network egress policies/firewalls are a critical defense layer; do not rely solely on Java validators.

### 5.4. HTTP Client Limits When Fetching JWKS

The HTTP client used to fetch JWKS should have:

- Short connect timeouts and response/read timeouts.
- Response byte-size caps.
- Limits on JWK count and individual key size.
- Explicit redirect policy, ideally disabling automatic redirects if unnecessary.
- TLS certificate/hostname verification.
- Concurrency and rate limits to resist DoS.
- Caching with appropriate TTL and revalidation.
- Never send OP cookies, bearer tokens, or client credentials to client-supplied hosts.
- Never log full URLs containing query secrets if URLs contain credentials or sensitive data.

Do not use a shared HTTP client with an interceptor that automatically attaches internal Authorization headers to every outbound request.

### 5.5. Checking the JWKS Response

After fetching:

1. Verify HTTP status indicates success.
2. Verify the response body is within size limits and parses as a valid JWK Set.
3. Verify no private/symmetric key material is present.
4. Check key count, duplicate `kid`, and algorithm/key compatibility.
5. Check `use`/`key_ops` if declared.
6. Never treat HTTP 200 or valid JSON parsing as proof that keys are trustworthy.

If fetching fails, do not fall back to unknown keys or switch to another algorithm. Return an appropriate authentication error and record metrics/safe logs.

## 6. Client-Declared Algorithms

Not every field containing `alg` controls the same signature. Distinguish signing direction, JWT type, and encryption mechanisms.

### 6.1. token_endpoint_auth_signing_alg

This field declares the JWS algorithm the client **MUST** use when signing authentication JWTs at the Token Endpoint with:

- `private_key_jwt`: client signs with an asymmetric private key; OP verifies with the client's public key in JWKS.
- `client_secret_jwt`: client signs a MAC with the shared client secret; keys are not fetched from JWKS.

If the client sends a JWT with an algorithm different from the registered metadata, the Token Request must be rejected. The value `none` MUST NOT be used. If the field is omitted, OIDC Registration allows any algorithm supported by both the OP and RP; servers SHOULD support RS256.

OP policy should use an explicit allow-list, e.g., RS256/PS256/ES256 depending on infrastructure, and bind algorithms to authentication methods:

| token_endpoint_auth_method | Client Key | Algorithm Policy |
| --- | --- | --- |
| `private_key_jwt` | Asymmetric private key at client, public key in JWKS | Allow only supported asymmetric JWS algorithms. |
| `client_secret_jwt` | Shared client secret | Allow only policy-permitted HMAC JWS algorithms. |
| `client_secret_basic` / `client_secret_post` | Client secret | `token_endpoint_auth_signing_alg` is not the active authentication mechanism. |
| `none` | No client secret | Disallow client assertions signed with shared secrets; use public-client policy/PKCE. |

### 6.2. request_object_signing_alg

This field declares the algorithm the client uses to sign Request Objects sent to the OP via `request` or `request_uri`. The OP verifies the signature using the public signing key in the client's JWKS.

OIDC Registration specifies:

- If this field has a value, all Request Objects from the client must be signed with that exact algorithm.
- The OP SHOULD support RS256.
- `none` MAY be used per the spec, though production policy may require signed Request Objects and reject `none`.
- If omitted, algorithms supported by both OP and RP may be used.

If the OP requires signed Request Objects, verify an appropriate key exists in the JWKS and never let a client use an encryption key to verify a JWS.

### 6.3. id_token_signed_response_alg

This field asks the **OP** to use a JWS algorithm to sign ID Tokens returned to the client. It is not an algorithm used by the client to sign.

- The default if omitted is RS256.
- `none` MUST NOT be used, unless the client only uses Response Types that do not return an ID Token from the Authorization Endpoint per OIDC Registration's exception.
- The public key for the client to verify the ID Token resides in the **OP's JWKS**.
- The client's `jwks_uri` is not where the OP gets a private key to sign ID Tokens.

If the client specifies an algorithm the OP does not support, registration must be rejected with an appropriate metadata error; never silently substitute another algorithm.

### 6.4. id_token_encrypted_response_alg and enc

If the client wants the OP to encrypt ID Tokens:

- `id_token_encrypted_response_alg` declares the JWE key-management algorithm.
- `id_token_encrypted_response_enc` declares the content-encryption algorithm.

When encryption is requested, the OP needs a matching public encryption key in the client's JWKS. If `id_token_encrypted_response_alg` is present without `enc`, OIDC Registration defines a default of `A128CBC-HS256`; if `enc` is sent without `alg`, the metadata is invalid.

When both signing and encryption are requested, the ID Token is signed first and then encrypted into a Nested JWT. Do not confuse JWE `alg` with JWS `alg`.

### 6.5. userinfo_signed_response_alg and UserInfo Encryption

`userinfo_signed_response_alg` asks the OP to sign UserInfo responses using JWS. `userinfo_encrypted_response_alg` and `userinfo_encrypted_response_enc` ask the OP to encrypt UserInfo responses using JWE.

These algorithms must also be checked against OP capabilities and the client's public keys. They do not alter the ID Token signing algorithm.

### 6.6. Summary Table

| Metadata | Action | Client/OP Key |
| --- | --- | --- |
| `token_endpoint_auth_signing_alg` | Client signs client assertion | Client private key or client secret; OP verifies. |
| `request_object_signing_alg` | Client signs Request Object | Client private key; OP verifies with client JWKS. |
| `id_token_signed_response_alg` | OP signs ID Token | OP private key; client verifies with OP JWKS. |
| `id_token_encrypted_response_alg` | OP encrypts ID Token | OP uses client's public encryption key. |
| `id_token_encrypted_response_enc` | Encrypts ID Token content | JWE content-encryption algorithm. |
| `userinfo_signed_response_alg` | OP signs UserInfo response | OP private key. |
| `userinfo_encrypted_response_alg` | OP encrypts UserInfo response | OP uses client's public encryption key. |
| `userinfo_encrypted_response_enc` | Encrypts UserInfo content | JWE content-encryption algorithm. |

## 7. Rules for Checking Algorithms and Keys

### 7.1. Use Purpose-Specific Allow-Lists

Do not create a single list of "every JOSE algorithm known by the library" and apply it to all metadata. Each purpose has its own allow-list:

- Client authentication JWS.
- Request Object JWS.
- OP's ID Token JWS.
- ID Token/UserInfo JWE key-management algorithms.
- ID Token/UserInfo JWE content-encryption algorithms.

An algorithm supported by a library is not necessarily permitted by the system's security policy. Allow-lists must consider:

1. Capabilities of the crypto provider/JWT library.
2. Available key types and strengths.
3. Actual client support.
4. Organizational security standards.
5. Published OP metadata.
6. Key rotation and operational manageability.

### 7.2. Reject the none Algorithm for Client Authentication

`token_endpoint_auth_signing_alg=none` must be rejected. If the server requires `private_key_jwt`, it must verify an asymmetric signature. If it requires `client_secret_jwt`, it must verify a MAC using the client secret and constrain allowed algorithms.

For Request Objects, the spec allows `none` in some cases, but if the server relies on Request Object signatures to protect request integrity, it must require a signed JWS.

For ID Tokens, apply the OIDC Registration Response Type exception accurately; production policy may be stricter than the spec, yet must never advertise an algorithm the OP does not actually enforce.

### 7.3. Checking Algorithm Metadata Against Keys

Examples:

| Declared Metadata | Actual JWKS | Result |
| --- | --- | --- |
| `private_key_jwt` + `PS256` | Has compatible RSA signing public key | Potentially acceptable after other checks. |
| `private_key_jwt` + `ES256` | Has only RSA keys | Reject or fail registration. |
| `private_key_jwt` + `RS256` | JWKS has only EC keys | Incompatible. |
| Signed Request Object `ES256` | Has EC P-256 key with matching `use` | Can be verified. |
| Signed Request Object `ES256` | Has only EC P-384 key | Incompatible. |
| `id_token_signed_response_alg=ES256` | OP has only RSA signing keys | OP cannot satisfy metadata; reject. |
| Encrypted ID Token `RSA-OAEP-256` | Client JWKS has only EC signing keys | No compatible encryption key. |
| `client_secret_jwt` + `HS256` | Client secret issued and policy allows HS256 | Potentially acceptable; no JWKS needed for assertion. |

### 7.4. Do Not Infer Key Compatibility Solely from Algorithm Names

`RS256` implies RSA, yet modulus, public exponent, and JWK metadata must still be checked. `ES256` requires P-256, not just any EC curve. `PS256` requires RSA-PSS support from the crypto provider. For JWE, distinguish the key-management algorithm (e.g., `RSA-OAEP-256` or `ECDH-ES`) from the content-encryption algorithm (e.g., `A256GCM`).

Do not accept weak keys, disallowed curves, deprecated algorithms, or inconsistent JWK/algorithm combinations just because a library can parse them.

## 8. Configuring DCR Validators in Spring Authorization Server

### 8.1. DCR Is Disabled by Default

Spring Authorization Server 1.5.8 disables the OpenID Connect Dynamic Client Registration Endpoint by default. This endpoint is an OAuth2 protected resource:

- Client Registration requests require a Bearer access token with the `client.create` scope.
- Client Read requests require the `client.read` scope.
- A `JwtDecoder` bean must be configured for the endpoint.

Do not open the registration endpoint to anonymous callers just to test metadata. Initial Access Tokens/registration access tokens, rate limits, tenant policies, and approval workflows must be designed upfront.

### 8.2. Default Validators Since 1.5.7

`OidcClientRegistrationAuthenticationValidator` was added in Spring Authorization Server 1.5.7. In 1.5.8, the default validators check:

- `redirect_uris`.
- `post_logout_redirect_uris`.
- `jwks_uri`.
- `scope`.

The fields have two groups of validators:

| Validator | Meaning |
| --- | --- |
| `DEFAULT_JWK_SET_URI_VALIDATOR` | Rejects `jwks_uri` not using HTTPS. |
| `SIMPLE_JWK_SET_URI_VALIDATOR` | Preserves legacy behavior with no URL checks. May permit values leading to SSRF. |
| `DEFAULT_REDIRECT_URI_VALIDATOR` | Rejects URIs missing a scheme, having a fragment, or using dangerous schemes. |
| `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` | Applies similar safety rules to post-logout URIs. |
| `DEFAULT_SCOPE_VALIDATOR` | Rejects requests with non-empty scopes. |
| `SIMPLE_SCOPE_VALIDATOR` | Accepts scopes per legacy behavior; requires a separate scope policy. |

Crucial point: `DEFAULT_JWK_SET_URI_VALIDATOR` checks only the **HTTPS scheme**. It does not prove the hostname is safe, block DNS rebinding, inspect redirect chains, or verify that the JWK Set has valid public keys. It is the first validation layer, not the complete SSRF defense.

### 8.3. Preserving Default Validators and Adding Custom Algorithm Checks

Spring Authorization Server allows customizing validators via `OidcClientRegistrationAuthenticationProvider.setAuthenticationValidator(...)`. Example:

~~~java
private static Consumer<List<AuthenticationProvider>>
        registrationValidatorCustomizer() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
            registrationProvider.setAuthenticationValidator(
                OidcClientRegistrationAuthenticationValidator
                    .DEFAULT_REDIRECT_URI_VALIDATOR
                    .andThen(
                        OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                    .andThen(
                        OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_JWK_SET_URI_VALIDATOR)
                    .andThen(customAlgorithmValidator())
                    .andThen(customScopeValidator()));
        }
    });
}
~~~

This code shows validator ordering. When replacing the validator, explicitly chain back the checks you need to keep. Never replace `DEFAULT_JWK_SET_URI_VALIDATOR` with `SIMPLE_JWK_SET_URI_VALIDATOR` just to make registration easier.

### 8.4. Reading Metadata from the Authentication Context

The validator receives `OidcClientRegistrationAuthenticationContext`. Request metadata can be read from it:

~~~java
private static Consumer<OidcClientRegistrationAuthenticationContext>
        customAlgorithmValidator() {

    return context -> {
        OidcClientRegistrationAuthenticationToken authentication =
            context.getAuthentication();
        OidcClientRegistration registration =
            authentication.getClientRegistration();

        String jwksUri = registration.getJwkSetUrl();
        String authMethod =
            registration.getTokenEndpointAuthenticationMethod();
        String authSigningAlg =
            registration.getTokenEndpointAuthenticationSigningAlgorithm();
        String idTokenAlg =
            registration.getIdTokenSignedResponseAlgorithm();
        String requestObjectAlg =
            registration.getClaimAsString("request_object_signing_alg");

        validateJwksUriPolicy(jwksUri);
        validateClientAuthenticationAlgorithm(
            authMethod, authSigningAlg, jwksUri);
        validateIdTokenResponseAlgorithm(idTokenAlg);
        validateRequestObjectAlgorithm(requestObjectAlg, jwksUri);
    };
}
~~~

The `validate...` methods represent application policy. They must throw `OAuth2AuthenticationException` with an appropriate `OAuth2Error` when metadata is invalid. Do not perform unbounded network fetches synchronously inside the validator; if checking JWKS at registration time, use a hardened fetcher with timeouts, egress policies, and response-size limits.

### 8.5. Checking Algorithms by Auth Method

Simple policy example:

~~~java
private static void validateClientAuthenticationAlgorithm(
        String authMethod, String alg, String jwksUri) {

    if ("private_key_jwt".equals(authMethod)) {
        if (jwksUri == null || jwksUri.isBlank()) {
            throw invalidClientMetadata(
                "private_key_jwt requires a client public key source");
        }
        if (alg != null && !Set.of("RS256", "PS256", "ES256").contains(alg)) {
            throw invalidClientMetadata(
                "Unsupported private_key_jwt signing algorithm");
        }
    }

    if ("client_secret_jwt".equals(authMethod)) {
        if (alg != null && !Set.of("HS256").contains(alg)) {
            throw invalidClientMetadata(
                "Unsupported client_secret_jwt signing algorithm");
        }
    }

    if ("none".equals(alg)) {
        throw invalidClientMetadata(
            "Unsigned client authentication assertion is not allowed");
    }
}

private static OAuth2AuthenticationException invalidClientMetadata(
        String description) {
    return new OAuth2AuthenticationException(
        new OAuth2Error(
            "invalid_client_metadata",
            description,
            null));
}
~~~

This is a sample policy, not a mandatory algorithm list from the spec. If supporting `client_secret_jwt` with HS384/HS512, intentionally expand the allow-list. If clients use `private_key_jwt` while the server supports inline `jwks`, replace the `jwks_uri` check with a check for a persisted and verified public key source. The example above assumes the deployment accepts only remote JWKS.

Do not require `jwks_uri` for `client_secret_basic`. Do not use `id_token_signed_response_alg` to infer that a client needs a public key; that is the algorithm the OP uses to sign ID Tokens.

### 8.6. Checking Scopes by Policy

In Spring Authorization Server 1.5.8, the default scope validator rejects any non-empty scope. If your product needs to accept client-declared scopes, replace it with an explicit allow-list validator, for example:

~~~java
private static Consumer<OidcClientRegistrationAuthenticationContext>
        customScopeValidator() {

    Set<String> allowedScopes = Set.of(
        "openid",
        "profile",
        "orders.read");

    return context -> {
        List<String> requestedScopes =
            context.getAuthentication()
                .getClientRegistration()
                .getScopes();

        if (!allowedScopes.containsAll(requestedScopes)) {
            throw invalidClientMetadata("Unsupported client scope");
        }
    };
}
~~~

If scopes are metadata that the organization does not allow clients to self-select, keep `DEFAULT_SCOPE_VALIDATOR` instead of a custom validator. Never use `SIMPLE_SCOPE_VALIDATOR` as a general way to disable validation.

### 8.7. Enabling the Endpoint with Validators

Configuration example:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .clientRegistrationEndpoint(registration ->
                    registration.authenticationProviders(
                        registrationValidatorCustomizer())))
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is the endpoint configuration portion. The application still requires `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, `JwtDecoder`, key management, `client.create`/`client.read` scope protection, and persistence. Do not enable DCR in production without policies governing who can register clients and what metadata requires approval.

## 9. Persisting Metadata into RegisteredClient

### 9.1. jwks_uri Is Stored in ClientSettings

Spring Authorization Server 1.5.8 maps the client's JWKS URL into `ClientSettings`:

~~~java
ClientSettings clientSettings = ClientSettings.builder()
    .jwkSetUrl("https://partner.example.com/.well-known/jwks.json")
    .tokenEndpointAuthenticationSigningAlgorithm(
        SignatureAlgorithm.PS256)
    .build();

RegisteredClient registeredClient = RegisteredClient
    .withId("partner-service-record-001")
    .clientId("partner-service")
    .clientName("Partner Service")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.PRIVATE_KEY_JWT)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .clientSettings(clientSettings)
    .build();
~~~

The example uses `SignatureAlgorithm.PS256` to illustrate an asymmetric JWS algorithm; verify classes/enums and crypto providers in your application's dependency version. `tokenEndpointAuthenticationSigningAlgorithm` takes a `JwsAlgorithm`, while `jwkSetUrl` stores the JWKS URL. The framework's default DCR converter handles mapping registration metadata to `RegisteredClient`; if adding custom policies, preserve all fields handled by the default converter.

### 9.2. Reading Back the Client Registration

After saving, the Client Configuration Endpoint returns the registered metadata. Verify:

- `jwks_uri` reflects the approved URL.
- `token_endpoint_auth_method` matches the granted method.
- `token_endpoint_auth_signing_alg` matches the stored algorithm.
- Private keys or raw secrets are not exposed improperly.
- Custom metadata is handled consistently by bidirectional converters.

If a custom converter handles only the request direction and not the response direction, Client Read responses may omit or return incorrect metadata. Spring Authorization Server provides `setRegisteredClientConverter(...)` and `setClientRegistrationConverter(...)` for bidirectional customization.

### 9.3. Storing Inline jwks If Truly Needed

Because `RegisteredClient.ClientSettings` has a URL field by default without a dedicated field for an inline JWK Set, supporting `jwks` requires a dedicated design:

1. Parse and validate the JWKS right inside the registration request.
2. Keep only validated public keys; strip/reject private/symmetric material.
3. Serialize in a standard format or store key records in a separate table linked to the `RegisteredClient` ID.
4. Enforce size limits, key count limits, schema versioning, and read permissions.
5. When verifying JWTs, construct a JWK source from the persisted snapshot.
6. When updating the registration, swap the key set atomically and audit the version.
7. When returning a Client Read Response, return the right metadata per policy.

Do not serialize an arbitrary Java object into `ClientSettings` and assume every JDBC mapper/upgrade will remain compatible. For frequent key rotation, `jwks_uri` is easier to operate.

## 10. Algorithms and JWKs in Live Flows

### 10.1. private_key_jwt

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Partner Client
    participant JWKS as Client JWKS URI
    participant AS as Authorization Server
    C->>C: Build client_assertion JWT
    C->>C: Sign with PS256 private key
    C->>AS: POST /oauth2/token + client_assertion
    AS->>JWKS: Fetch public JWK on cache miss/refresh
    JWKS-->>AS: Client's JWK Set
    AS->>AS: Select RSA public key by kid/alg
    AS->>AS: Verify signature and assertion claims
    AS-->>C: Access Token or invalid_client error
~~~

The OP must validate `iss`, `sub`, `aud`, `exp`, `jti`, client ID, and replay protection per the JWT client authentication profile. A valid signature with the wrong `aud` or a replayed assertion must still be rejected.

### 10.2. Signed Request Object

The client signs the Request Object with its private key; the OP fetches the public key from JWKS to verify before using claims in the request. Signature and claim checks must follow OIDC Core, including issuer/client, audience, timestamps, and replay policy. Never treat a validly signed request JWT with the wrong `aud` as a valid authorization request.

### 10.3. OP Encrypting ID Tokens for the Client

When a client declares `id_token_encrypted_response_alg`, the OP selects the client's public encryption key from its JWKS. The key must match the JWE algorithm; a signing key with `use=sig` must not be used as an encryption key simply because it lives in the same JWKS.

If the client requests both signing and encryption, the OP can sign the ID Token with the OP's private key and then encrypt it with the client's public key. The client decrypts with its private key and verifies the signature with the OP's public key.

## 11. Caching, Rotation, and JWKS Availability

### 11.1. jwks_uri Supports Rotation

A client can publish both its current and next public keys simultaneously:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "partner-rsa-old",
      "n": "old-public-modulus",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "partner-rsa-new",
      "n": "new-public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Rotation workflow:

1. Client publishes the new public key before using the new private key.
2. Wait so the OP can retrieve the new key per cache/revalidation policy.
3. Client switches to signing with the new key and using the new `kid`.
4. Keep the old public key long enough for in-flight assertions/requests and valid retries.
5. Remove the old key when it is no longer needed for verification.

### 11.2. Caching Must Have Bounds

Caching JWKS reduces outbound requests and latency, yet if a key is compromised or revoked, caching too long can keep trusting the old public key. You need:

- A maximum TTL per security policy.
- Respecting HTTP cache headers if supported by the library.
- Refreshing when a `kid` is not found, with rate limits to prevent forced-refresh DoS.
- Single-flight/concurrent refresh deduplication to avoid thundering-herd requests.
- Retry caps so failed refreshes do not loop indefinitely.
- Cache invalidation when registration/key versions change via a trusted channel.

Do not accept stale JWKS indefinitely when an endpoint times out. If cache freshness expires and keys cannot be fetched, verification decisions must fail closed.

### 11.3. Registration Updates and Cache Invalidation

The Client Configuration Endpoint allows updating metadata using a Registration Access Token. When `jwks_uri` changes:

- Authenticate the Registration Access Token and client edit permissions.
- Re-run URL validation and algorithm/key policies.
- Write the new metadata atomically.
- Invalidate the JWKS cache for that client.
- Audit old/new URLs using sanitized fingerprints without logging keys/private material.
- Test old/new assertions during transition windows per policy.

Never let a client change `jwks_uri` right before a Token Request to redirect the OP to a new host without re-running validators.

## 12. Common Pitfalls and How to Fix Them

### Pitfall 1: Confusing the Client's JWKS with the OP's JWKS

**Symptom:** OP tries to use the client's public key to verify ID Tokens signed by the OP itself.

**Cause:** Failing to distinguish the two trust directions.

**Fix:** Use client JWKS to verify client signatures/encrypt responses for the client; use OP JWKS for clients to verify OP-signed tokens.

### Pitfall 2: Allowing jwks_uri to Use HTTP

**Symptom:** Client keys are tampered with in transit or an attacker controls JWKS contents.

**Cause:** Skipping OIDC Registration's HTTPS requirement.

**Fix:** Keep `DEFAULT_JWK_SET_URI_VALIDATOR` and enforce TLS hostname/certificate verification.

### Pitfall 3: Assuming HTTPS Prevents SSRF

**Symptom:** OP accesses cloud metadata or internal HTTPS services via `jwks_uri`.

**Cause:** Validator checks only the scheme.

**Fix:** Enforce DNS/IP egress policies, block private/reserved destinations, control redirects, and use a hardened HTTP client.

### Pitfall 4: Using SIMPLE_JWK_SET_URI_VALIDATOR in Production

**Symptom:** Unsafe URLs are accepted.

**Cause:** Using the backward-compatible validator that performs no URL checks.

**Fix:** Use the strict validator plus SSRF policy. Only use SIMPLE when an evaluated compatibility need exists alongside an equivalent validation layer.

### Pitfall 5: Client Sends Both jwks_uri and jwks Simultaneously

**Symptom:** Ambiguous which key source is authoritative.

**Cause:** Failing to enforce mutual exclusion.

**Fix:** Reject the registration; require the client to choose exactly one mechanism.

### Pitfall 6: JWKS Contains Private Keys

**Symptom:** Client's private key appears in requests, logs, or database.

**Cause:** Client uploaded an entire keystore instead of public keys.

**Fix:** Reject JWKs with private/symmetric parameters; purge raw requests from logs and require rotating the exposed key.

### Pitfall 7: Using One Key for Both Signing and Encryption

**Symptom:** Ambiguous key selection and key compromise affects multiple purposes.

**Cause:** Reusing keys or omitting `use`.

**Fix:** Separate keys by purpose; if a JWKS contains both signing and encryption keys, require `use` on every key.

### Pitfall 8: Not Checking alg Against kty/curve

**Symptom:** Client declares ES256 but only has an RSA key.

**Cause:** Checking only whether the algorithm string is on an allowed list.

**Fix:** Validate the tuple of algorithm/key type/curve/use and run an actual test verification in tests.

### Pitfall 9: Confusing token_endpoint_auth_signing_alg with id_token_signed_response_alg

**Symptom:** Client assertions use the wrong algorithm or the OP signs ID Tokens under an unintended policy.

**Cause:** Conflating client-signing algorithms with OP-signing algorithms.

**Fix:** Persist and validate each metadata field separately according to its signing direction.

### Pitfall 10: Allowing none for Client Authentication

**Symptom:** Unsigned JWT assertions are accepted.

**Cause:** Failing to enforce the normative rule for `token_endpoint_auth_signing_alg`.

**Fix:** Reject `none`; require a valid JWS algorithm and matching key/secret.

### Pitfall 11: Removing Old Keys Immediately After Rotation

**Symptom:** Valid in-flight assertions are rejected because `kid` is no longer in JWKS.

**Cause:** Rotating without an overlap window.

**Fix:** Pre-publish the new key, maintain overlap, monitor cache behavior, and retire the old key only after a safe window.

### Pitfall 12: Validating Only at Registration Time, Not on Update

**Symptom:** Client switches JWKS URL to an unsafe address through the Client Configuration Endpoint.

**Cause:** Attaching validators only to the registration provider, overlooking the configuration/update path.

**Fix:** Apply the same policies to both registration and client configuration updates, and test both endpoints.

## 13. Test Matrix

| Case | Expected Result |
| --- | --- |
| Valid HTTPS `jwks_uri` | Passes strict scheme validator; proceeds to host policy and JWKS checks. |
| HTTP `jwks_uri` | Rejected. |
| `jwks_uri` using localhost/private IP | Rejected by SSRF policy. |
| `jwks_uri` redirecting to private IP | Not followed or redirect blocked by policy. |
| DNS rebinding | Connection to private/reserved address blocked. |
| TLS certificate hostname mismatch/expired | JWKS not fetched. |
| JWKS response exceeds size limit | Download aborted and rejected. |
| JWKS missing `keys` array | Rejected. |
| JWK missing `kty` | Rejected. |
| JWKS containing RSA private `d` | Rejected; raw key never logged. |
| JWKS containing symmetric `oct` key | Rejected per OIDC Registration. |
| Both `jwks_uri` and `jwks` present | Metadata rejected. |
| Both signing and encryption keys present without `use` | Rejected per OIDC policy. |
| Conflicting `use` and `key_ops` | Rejected. |
| Duplicate `kid` across two different keys | Rejected or unable to uniquely select key. |
| ES256 declared with non-P-256 key | Rejected. |
| RS256 declared with EC JWK | Rejected. |
| `private_key_jwt` without public key source | Registration rejected per policy. |
| `client_secret_jwt` using permitted HMAC | Accepted if secret and policy match. |
| `token_endpoint_auth_signing_alg` is `none` | Rejected. |
| `request_object_signing_alg` outside allow-list | Rejected. |
| `id_token_signed_response_alg` unsupported by OP | Metadata rejected. |
| `id_token_encrypted_response_alg` with no encryption key | Rejected. |
| Registration scope outside allow-list | Rejected. |
| JWKS rotation with new and old keys | Both keys verify during overlap window. |
| JWKS endpoint times out after cache expiry | Verification fails closed. |
| Client update changes `jwks_uri` | Re-runs validators and invalidates cache. |
| Client Read after registration | Returns accurate metadata without exposing private keys. |
| Registration endpoint call without `client.create` | Rejected. |

## 14. Production Checklist

| Item | Question to Confirm |
| --- | --- |
| DCR access | Is the endpoint protected by access tokens and the `client.create` scope? |
| Registration read | Is `client.read` required for Client Read? |
| jwks_uri | Are only HTTPS and safe hostnames/destination addresses accepted? |
| SSRF | Are egress firewalls, DNS/IP validation, and redirect policies in place? |
| HTTP client | Are timeouts, response-size caps, concurrency limits, and TLS verification configured? |
| JWKS schema | Are `keys`, `kty`, key counts, and duplicate keys validated? |
| Private material | Are private/symmetric JWK values rejected? |
| Key use | Are `use`/`key_ops` purpose-appropriate and consistent? |
| Algorithms | Are separate allow-lists enforced for JWS/JWE and compatible with keys? |
| Client auth | Does `token_endpoint_auth_method` match signing algorithms and key sources? |
| Request Object | Are signed Request Objects verified against client key policies? |
| ID Token | Are client JWKS and OP JWKS kept strictly distinct? |
| JWE | Does a matching encryption key exist for ID Token/UserInfo responses? |
| Registration update | Are validators applied when modifying metadata as well? |
| Persistence | Is `RegisteredClient` metadata durably persisted and read back accurately? |
| Rotation | Are pre-publishing, overlap, cache refresh, and key retirement supported? |
| Auditing | Are raw private JWKs, client assertions, and secrets excluded from logs? |
| Tests | Are SSRF, algorithm mismatch, malformed JWKS, rotation, and negative tests covered? |

## 15. Hands-On Exercise

A partner wants to register three capabilities:

- `private_key_jwt` at the Token Endpoint using PS256.
- Signed Request Objects using ES256.
- Receiving ID Tokens encrypted with RSA-OAEP-256 and A256GCM.

The partner submits `jwks_uri=https://partner.example.com/.well-known/jwks.json`. The JWKS contains one RSA signing key, one EC P-256 signing key, and one RSA encryption key. The endpoint sits behind a CDN with a 5-minute cache.

1. Design registration metadata with the appropriate algorithm fields.
2. Identify which public key is used for PS256, ES256, and RSA-OAEP-256.
3. Determine how `use` must be declared when the JWKS contains both signing and encryption keys.
4. Write a validator checking HTTPS, auth method, algorithm allow-list, and key source.
5. Design SSRF defenses for `jwks_uri`, including DNS rebinding and redirects.
6. Determine when the OP fetches the JWKS, cache TTL, and how to refresh when a new `kid` appears.
7. Test a registration containing both `jwks_uri` and `jwks`; specify the error to return.
8. Test a JWKS containing private RSA `d` and symmetric `k`; specify behavior and safe logging.
9. Rotate the RSA signing key while keeping the EC key; demonstrate that both old and new assertions verify during overlap.
10. Verify that `id_token_signed_response_alg` is the algorithm the OP uses to sign ID Tokens, not one of the client-signing algorithms.

**Acceptance criteria:** Each algorithm is bound to the right purpose and matching key; the OP never fetches internal resources via `jwks_uri`; the JWKS contains only public keys; both registration and updates are validated; key rotation creates no verification gap.

## 16. Reference Documentation

- [OpenID Connect Dynamic Client Registration 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-registration-1_0.html): `jwks_uri`, `jwks`, client metadata, algorithms, and validation.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591): client metadata `jwks_uri`/`jwks` and registration errors.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): `kty`, `use`, `key_ops`, `alg`, `kid`, and JWK Set.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS protected headers and signature verification.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE serialization, key management, and content encryption.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): JWS/JWE algorithms and key requirements.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): `private_key_jwt`/JWT client assertions.
- [Spring Authorization Server — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enabling DCR, validators, and converters.
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationValidator Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): strict/simple validators and `jwks_uri` validation.
- [Spring Authorization Server 1.5.8 — OidcClientRegistration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcClientRegistration.Builder.html): `jwkSetUrl` and client metadata.
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationProvider Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html): authentication validators and converters.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Client Registration Endpoint, bearer access tokens, and scope requirements.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient` and `ClientSettings.jwkSetUrl`.
