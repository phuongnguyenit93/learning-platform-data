# Setting Up Truststores, Certificate Chains, and Certificate Acceptance Policies

## 1. Objectives and Real-World Scenario

In the **mTLS** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson focuses on configuring truststores, validating X.509 certificate chains, and deciding which client certificates are permitted for OAuth 2.0 authentication. This is part of the goal to **design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application**.

Suppose a system has backend services such as Orders Worker, Billing Worker, and Reporting Service. Instead of sharing client secrets across multiple environments, each workload is issued a client certificate by an internal CA. When a workload calls the Token Endpoint, the TLS handshake requires the client to present its certificate and prove possession of the corresponding private key. The Authorization Server verifies the certificate chain up to a trusted CA, then matches the certificate's identity against the registered client.

A certificate signed by a trusted CA **does not mean** it is allowed to represent every OAuth client. All of the following must be verified simultaneously:

1. The certificate has a valid chain leading to a configured trust anchor.
2. The certificate is within its validity period, has the proper key usage, and satisfies PKI policies.
3. The identity in Subject DN or Subject Alternative Name matches the registered client_id.
4. The client is permitted to use the TLS client authentication method and the requested grant.
5. If certificate-bound Access Tokens are enabled, the Resource Server verifies the certificate when the client presents the token.

After this lesson, you will be able to:

- Distinguish keystores, truststores, root CAs, intermediate CAs, and leaf/client certificates.
- Configure TLS client authentication in Spring Boot and understand the none, want, and need modes.
- Verify certificate chains per PKIX and understand the role of trust anchors.
- Register clients with tls_client_auth or self_signed_tls_client_auth in Spring Authorization Server.
- Apply policies for Subject DN, SAN, EKU, validity, and certificate revocation.
- Handle TLS termination at a reverse proxy, certificate rotation, and troubleshooting authentication errors.

**Version scope:** Spring Authorization Server examples focus on the 1.5.x line and Spring Boot 3.x. The server.ssl.* properties illustrate an embedded Servlet server. If TLS terminates at an ingress, load balancer, or service mesh, the certificate and truststore configuration must be placed at the component performing the actual TLS handshake.

## 2. At Which Layer Does mTLS Occur?

Standard TLS authenticates the server to the client. With **mutual TLS (mTLS)**, the server also requires the client to present an X.509 certificate and prove possession of the corresponding private key during the TLS handshake. This occurs **before the HTTP request reaches the Spring Security filter chain**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant TLS as TLS Server / Servlet Container
    participant AS as Spring Authorization Server
    C->>TLS: TLS ClientHello
    TLS-->>C: Server Certificate + CertificateRequest
    C->>TLS: Client Certificate chain + CertificateVerify
    TLS->>TLS: Verify signature, chain, and trust anchor
    TLS-->>C: TLS handshake completed or rejected
    C->>AS: POST /oauth2/token + client_id
    AS->>AS: X509ClientCertificateAuthenticationProvider
    AS->>AS: Match certificate against RegisteredClient
    AS-->>C: Token response or invalid_client
~~~

There are two distinct verification layers:

- **TLS/PKIX validation:** verifies that the certificate is signed by a trusted CA, the certificate chain is valid, and the client actually holds the private key.
- **OAuth client identity validation:** Spring Authorization Server identifies the client_id and compares the received certificate against the certificate identity configured for the RegisteredClient.

If the TLS handshake fails, the application may never receive an HTTP request to return an OAuth2 JSON error. If the handshake succeeds but the certificate does not match the client_id, the OAuth layer can return a client authentication error, typically invalid_client.

## 3. How Do Keystores and Truststores Differ?

These two store types are often confused because both can be JKS or PKCS12 files.

| Component | What Does It Contain? | Who Uses It? | Purpose |
| --- | --- | --- | --- |
| **Server keystore** | Server certificate, private key, and optionally the certificate chain | Authorization Server | Proves the server's identity to the client |
| **Client CA truststore** | CA certificates trusted as trust anchors | TLS server/container | Verifies client certificate chains |
| **Client keystore** | Client certificate, private key, and chain | OAuth2 client | Proves client identity and private key possession |
| **Client truststore** | CAs/certificates used to trust the server certificate | OAuth2 client | Verifies the Authorization Server when the client connects |

In an Authorization Server accepting mTLS:

- The keystore holds the server's certificate and private key.
- The truststore holds the CAs the server accepts to verify client certificates.
- The client has its own keystore holding the client certificate and private key.
- The client may also have its own truststore to verify the server certificate.

**Do not confuse the client-side truststore with the server-side truststore.** The client's truststore helps the client trust the server; the server's truststore helps the server trust the CAs issuing client certificates.

### 3.1. What is a trust anchor?

In PKI, a certificate path typically looks like this:

~~~text
Client leaf certificate
        |
        v
Intermediate CA certificate
        |
        v
Root CA certificate  <--- trust anchor in truststore
~~~

The leaf certificate is issued to the workload. The Intermediate CA signs the leaf certificate. The Root CA is typically the trust point installed in the truststore. During the TLS handshake, the client usually sends the leaf certificate along with any necessary intermediates; the root certificate usually does not need to be sent because the server already has the trust anchor.

The truststore is not a list of all registered client certificates. It primarily defines **which CAs or certificates are trusted to build a certificate path**. Determining which client_id a leaf certificate belongs to still requires the identity verification step at the OAuth layer.

### 3.2. Trust the root CA or trust leaf certificates directly?

With PKI mTLS, the common model is trusting one or a few managed internal CAs. When a client is re-issued a new leaf certificate from the same CA while keeping the appropriate identity, the server can continue verifying the chain without importing each leaf certificate into the truststore.

Importing leaf certificates directly into the truststore can create a form of specific-certificate pinning, but makes certificate rotation and scaling clients more complex. Choose that model only with clear intent and an understanding of how the TLS provider builds trust paths.

## 4. X.509 Certificate Chains and PKIX Validation

A valid client certificate needs more than just a CA signature. The server must verify the certificate path and usage constraints.

| Check | Meaning | Error Example |
| --- | --- | --- |
| Chain signatures | Each certificate is validly signed by the next issuer | Leaf signed by a CA missing from the chain |
| Trust anchor | Chain terminates at a CA/certificate trusted by the truststore | Root CA not yet imported |
| Validity | Current time falls within Not Before/Not After | Expired or not-yet-valid certificate |
| Basic Constraints | CA certificates are allowed to act as CAs; leaf does not claim CA role | Intermediate has CA=false |
| Key Usage | Key is permitted for the required purpose | Missing digitalSignature when TLS requires signing |
| Extended Key Usage | Client authentication purpose is permitted when required by policy | Only serverAuth present, missing clientAuth |
| Name Constraints / Policy | Complies with CA naming constraints and policies | SAN falls outside the permitted namespace |
| Revocation | Checks CRL/OCSP if required by deployment | Certificate has been revoked |

For client certificates used in TLS client authentication, verify EKU matches **TLS Web Client Authentication** when the certificate/profile includes EKU. The TLS stack and PKIX provider are responsible for verifying the chain, signatures, validity, and extensions per configuration. The OAuth verifier adds client identity matching.

**Do not write your own X.509 verification algorithm.** Use a tested TLS stack and PKIX library. RFC 8705 also recommends using proven X.509 implementations rather than hand-rolling certificate chain processing, DN parsing, or revocation checks.

## 5. Creating a Truststore for an Internal CA

Suppose the PKI team provides:

- partner-root-ca.pem: root CA certificate verified over an administrative channel.
- partner-intermediate-ca.pem: intermediate CA (typically sent by the client in the chain).
- client-leaf.pem and client-key.pem: certificate and private key of an OAuth client.

Import a CA certificate only after verifying its fingerprint through a trusted channel. Never import a certificate simply because it was attached in an email or extracted from a TLS request.

### 5.1. Creating a PKCS12 truststore and importing a CA

Example using keytool:

~~~bash
keytool -importcert \
  -alias partner-root-ca \
  -file partner-root-ca.pem \
  -keystore oauth-client-ca-truststore.p12 \
  -storetype PKCS12
~~~

keytool prompts interactively for the truststore password. In CI/CD or production, supply secrets via a secret manager or platform secret mechanism; never commit passwords or truststores containing internal data to public repositories.

Inspecting contents:

~~~bash
keytool -list -v \
  -keystore oauth-client-ca-truststore.p12 \
  -storetype PKCS12
~~~

The output should confirm the alias, entry type, and CA subject/issuer. A truststore typically has entries of type trustedCertEntry for CA certificates; it does not need the CA's private key.

### 5.2. Verifying the chain before deploying to the server

You can use OpenSSL to verify a test chain:

~~~bash
openssl verify \
  -CAfile partner-root-ca.pem \
  -untrusted partner-intermediate-ca.pem \
  client-leaf.pem
~~~

This command demonstrates checking the chain up to the specified CA. It does not replace checking EKU, SAN, client_id policies, or the application's actual TLS configuration.

### 5.3. Never put the CA private key into the truststore

A truststore needs only the public CA certificate as a trust anchor. Root CA/Intermediate CA private keys must remain inside an HSM or controlled PKI infrastructure. If a CA private key is leaked, attackers can issue forged certificates trusted by systems that installed that CA.

## 6. Configuring mTLS in Spring Boot

A Spring Boot embedded server needs:

1. A keystore containing the Authorization Server's certificate/private key.
2. A truststore containing CAs allowed to issue client certificates.
3. A client certificate request mode appropriate for the endpoints served.

Example YAML configuration for Spring Boot 3.x:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/auth-server.p12
    key-store-type: PKCS12
    key-store-password: __AUTH_SERVER_KEYSTORE_PASSWORD_FROM_SECRET_STORE__
    key-alias: auth-server
    trust-store: file:/run/secrets/oauth-client-ca-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: __OAUTH_CLIENT_TRUSTSTORE_PASSWORD_FROM_SECRET_STORE__
    client-auth: want
~~~

In this example:

- key-store is the **server's** identity.
- trust-store holds trust anchors for verifying **client certificate chains**.
- client-auth: want asks the client to present a certificate if available, while allowing the TLS handshake to continue if the client does not send one.
- Spring Authorization Server will then apply the client authentication method for each RegisteredClient.

Never put real passwords directly in an application.yml committed to Git. Use environment variables, Kubernetes Secrets, Vault, cloud secret managers, or appropriate secret injection.

### 6.1. none, want, and need

| Value | TLS Behavior | Use Case |
| --- | --- | --- |
| none | Does not request a client certificate | Endpoints not using mTLS |
| want | Requests a certificate but lets the handshake continue if the client sends none | Single host/port serving both browser/public clients and mTLS clients |
| need | Requires a client certificate in the TLS handshake | Endpoints/ports dedicated exclusively to mTLS connections |

If the Authorization Server serves browser login, the authorization endpoint, public clients, and confidential mTLS clients on the same listener, configuring need can prevent browsers or clients without certificates from connecting. RFC 8705 describes supporting mTLS alongside other client authentication methods by allowing the handshake to proceed when no certificate is present; want is a common choice for embedded servers.

For environments requiring mTLS on every request, a dedicated listener or hostname/port with need can be used. In that case, endpoint discovery, redirects, reverse proxies, and client routing must be clearly designed.

### 6.2. The truststore alone does not decide which OAuth clients can log in

When a client certificate is signed by a trusted CA, the TLS handshake can succeed. However, if client_id does not exist, is not registered for TLS_CLIENT_AUTH, or the certificate identity mismatches, OAuth client authentication must still fail.

This is why a truststore must not be treated as an authorization allow-list. The truststore defines the **trusted CA boundary**; RegisteredClient and the certificate verifier define the **accepted client identities**.

## 7. Registering a Client with tls_client_auth

RFC 8705 defines two mTLS OAuth client authentication methods:

- **tls_client_auth:** the PKI method; the server verifies the certificate chain up to a trust anchor, then matches a registered Subject DN or SAN.
- **self_signed_tls_client_auth:** the client uses a self-signed certificate; the server matches the received certificate against a certificate in the client's JWKS/JWK Set, without relying on a CA chain as in the PKI method.

For the PKI method, a Spring Authorization Server example:

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient mtlsClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-worker")
        .clientAuthenticationMethod(ClientAuthenticationMethod.TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .x509CertificateSubjectDN(
                        "CN=orders-worker,OU=Workloads,O=Example,C=VN")
                .build())
        .tokenSettings(TokenSettings.builder()
                .x509CertificateBoundAccessTokens(true)
                .build())
        .build();
~~~

This is an illustrative registration. In production, RegisteredClient must be stored in a persistent repository with a stable ID. Subject DN must match the PKI-issued certificate according to proper DN comparison rules; do not compare DN strings by splitting strings arbitrarily.

Key components:

- TLS_CLIENT_AUTH requires client authentication using PKI mTLS.
- x509CertificateSubjectDN configures the expected Subject DN of the client certificate.
- x509CertificateBoundAccessTokens(true) requires Access Tokens to be bound to the certificate per RFC 8705.
- CLIENT_CREDENTIALS is the illustrative grant for workloads; other grants must be permitted per separate policy.

### 7.1. client_id is still required in the Token Request

RFC 8705 requires requests using TLS client authentication to include client_id. Example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=orders-worker&
scope=orders.read
~~~

The certificate does not replace client_id. The server uses client_id to look up the RegisteredClient, then checks whether the certificate presented in the TLS handshake matches that client.

## 8. Subject DN and SAN Acceptance Policies

After the TLS handshake completes, Spring Authorization Server uses X509ClientCertificateAuthenticationProvider for both methods:

- ClientAuthenticationMethod.TLS_CLIENT_AUTH.
- ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH.

With PKI mTLS, Spring Authorization Server's default certificate verifier checks the certificate's Subject Distinguished Name against RegisteredClient.getClientSettings().getX509CertificateSubjectDN().

### 8.1. Subject DN

Example DN:

~~~text
CN=orders-worker,OU=Workloads,O=Example,C=VN
~~~

A DN can have multiple structurally equivalent representations. Do not compare manually by splitting on commas or comparing ad-hoc normalized strings. Use an X.500/DN comparison mechanism with clear rules consistent with how certificate subjects are registered.

A DN is not a secret either. If a DN is too generic such as CN=service or OU=backend, multiple clients could collide on identity. The PKI must issue sufficiently distinct subjects/SANs and enforce a process preventing two different clients from sharing an identity.

### 8.2. Subject Alternative Name

SANs are often better suited for workload identities:

| SAN Type | Example | Purpose |
| --- | --- | --- |
| dNSName | orders-worker.prod.example.internal | Identify a workload by DNS name |
| uniformResourceIdentifier | spiffe://example.internal/ns/orders/sa/worker | Identify a workload by URI |
| iPAddress | 10.20.4.15 | Identify by IP address if required by architecture |
| rfc822Name | workload@example.internal | Email-style identifier if used by profile |

RFC 8705 specifies that the PKI method registers a single subject name value for a client, which can be a Subject DN or a supported SAN type. Spring Authorization Server defaults to Subject DN; if you want to verify SANs, you must configure a custom Certificate Verifier.

### 8.3. Customizing Certificate Verifier to verify SANs

Spring Authorization Server allows replacing the Certificate Verifier of X509ClientCertificateAuthenticationProvider. The example below illustrates checking a URI SAN against a server-side registry:

~~~java
import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.authentication.X509ClientCertificateAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

Consumer<List<AuthenticationProvider>> configureSanVerifier(
        Map<String, String> expectedUriSanByClientId) {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof X509ClientCertificateAuthenticationProvider x509Provider) {
            Consumer<OAuth2ClientAuthenticationContext> verifier = context -> {
                OAuth2ClientAuthenticationToken authentication =
                        context.getAuthentication();
                RegisteredClient registeredClient = context.getRegisteredClient();
                X509Certificate[] chain =
                        (X509Certificate[]) authentication.getCredentials();

                if (chain == null || chain.length == 0) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
                }

                String expectedUriSan =
                        expectedUriSanByClientId.get(registeredClient.getClientId());
                if (expectedUriSan == null) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
                }

                try {
                    X509Certificate leaf = chain[0];
                    Collection<List<?>> sans = leaf.getSubjectAlternativeNames();
                    boolean matched = sans != null && sans.stream().anyMatch(san ->
                            san.size() >= 2
                            && Integer.valueOf(6).equals(san.get(0))
                            && expectedUriSan.equals(san.get(1)));

                    if (!matched) {
                        throw new OAuth2AuthenticationException(
                                new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
                    }
                } catch (CertificateParsingException ex) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT), ex);
                }
            };

            x509Provider.setCertificateVerifier(verifier);
        }
    });
}
~~~

Register this helper in the Authorization Server's client authentication configuration, inside SecurityFilterChain:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.clientAuthentication(clientAuthentication ->
            clientAuthentication.authenticationProviders(
                    configureSanVerifier(expectedUriSanByClientId))));
~~~

This snippet attaches to an existing SecurityFilterChain configuration; the application still needs to call http.build() and configure the necessary beans/repositories.

This illustrates URI SAN (GeneralName type 6), not a complete configuration class. In a real application:

- expectedUriSanByClientId must come from trusted administrative configuration, not from the HTTP request.
- The chain has already been verified by the TLS stack before the Certificate Verifier performs identity matching.
- Test duplicate SANs, missing SANs, wrong SAN types, empty certificate chains, and certificates belonging to the wrong client.
- If using DNS SAN, GeneralName type is 2; IP SAN is 7. Compare using the proper type and rules for each kind.
- Never replace PKIX chain validation with a SAN comparison alone.

### 8.4. Client certificates with multiple SANs

A certificate can contain multiple SANs. Policy must specify **which single SAN represents the client_id** and verify the exact SAN type. Do not accept a certificate merely because one of its many SANs matches a generic string such as example.internal.

## 9. Self-Signed TLS Client Authentication

Not every system has an internal PKI. RFC 8705 provides the self_signed_tls_client_auth method for clients that self-sign certificates.

In this method:

1. The client registers its public certificate or JWK Set URL with the Authorization Server.
2. The certificate is represented in the JWK Set via the x5c attribute.
3. The client presents the certificate in the TLS handshake and proves possession of the private key.
4. Spring Authorization Server compares the received certificate against the certificate registered in the JWK Set.
5. No CA chain validation is performed as in the PKI method; identity is verified via the certificate registered for the client.

Client configuration example:

~~~java
RegisteredClient selfSignedClient = RegisteredClient.withId("self-signed-client-id")
        .clientId("edge-agent-01")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("telemetry.write")
        .clientSettings(ClientSettings.builder()
                .jwkSetUrl("https://registry.example.com/clients/edge-agent-01/jwks")
                .build())
        .build();
~~~

This is a configuration example; the JWKS endpoint must be protected and governed. The self-signed method does not mean accepting any arbitrary self-signed certificate. The server accepts only certificates matching the certificate registered for that exact client.

With this method, the TLS stack must be configured not to require a certificate chain leading to a trusted CA as in the PKI method; certificate verification is performed by matching against the certificate registered in the JWKS. Therefore, you cannot simply reuse the same PKI truststore configuration from section 6 and expect a self-signed certificate not signed by a CA to pass the TLS handshake. If a system requires both PKI and self-signed client authentication simultaneously, design separate listeners/endpoints or TLS policies for each trust model and thoroughly test the authentication paths. Never open a listener that accepts any certificate if the OAuth provider is not enforcing mandatory certificate/JWKS matching.

**Do not mix the two models:**

| PKI TLS client auth | Self-signed TLS client auth |
| --- | --- |
| Trust CA chain via truststore | Match certificate against registered JWK Set/x5c |
| TLS_CLIENT_AUTH | SELF_SIGNED_TLS_CLIENT_AUTH |
| Subject DN/SAN per client registration | Certificate fingerprint/key material per JWKS |
| Fits centralized PKI, internal CA | Fits clients with individual certificates without a shared PKI |

## 10. Certificate-Bound Access Tokens

mTLS client authentication and certificate-bound Access Tokens are **different mechanisms that can be combined**:

- Client authentication verifies the client at the Authorization Server.
- Certificate-bound tokens bind the Access Token to a certificate so the Resource Server requires that exact certificate when using the token.

For JWT Access Tokens, RFC 8705 defines the confirmation claim:

~~~json
{
  "cnf": {
    "x5t#S256": "bwcK0esc3ACC3DB2Y5_lESsXE8o9ltc05O89jdN-dg2"
  }
}
~~~

x5t#S256 is the unpadded Base64URL encoding of the SHA-256 hash over the **DER encoding of the X.509 certificate**. It is not DPoP's JWK thumbprint cnf.jkt.

Spring Authorization Server supports enabling certificate-bound Access Tokens via:

~~~java
TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .build();
~~~

When a client uses TLS client authentication at the Token Endpoint, the Authorization Server can extract the verified certificate, compute its thumbprint, and attach it to the token. For JWTs, the cnf claim contains x5t#S256. For opaque tokens, the binding can be provided via the Token Introspection Response.

### 10.1. Which certificate must the Resource Server check?

When the client calls a protected resource, it must use the **exact same certificate** bound to the Access Token. The Resource Server obtains the client certificate from the TLS layer, computes the SHA-256 thumbprint of the DER certificate, and compares it against cnf.x5t#S256 in the token or introspection response.

If the thumbprints differ, the Resource Server rejects the request with HTTP 401 and invalid_token per RFC 8705. Checking only the JWT signature and exp is insufficient for certificate-bound tokens.

### 10.2. Trust chain at the Resource Server

In RFC 8705's certificate-bound token model, the Resource Server needs to verify that the certificate presented on the TLS connection is the certificate bound to the Access Token. The RFC does not mandate that the Resource Server re-verify the PKI CA trust chain in the same way the Authorization Server authenticated the client; the goal here is proof-of-possession using the certificate specified by the token binding.

Deployments may have their own PKI policies and continue checking trust chains at the Resource Server. The critical requirement is never skipping the step of **comparing the certificate thumbprint against the token binding**. The TLS server still must request a certificate during the handshake if the endpoint requires mTLS.

### 10.3. What happens to old tokens when a certificate changes?

An Access Token bound to certificate A will not match certificate B after the client rotates keys/certificates. The client must request a new token via an authorized flow using certificate B. Never modify the cnf claim inside an old token and never accept a new certificate merely because client_id is the same.

## 11. TLS Termination at a Reverse Proxy or Load Balancer

In production, TLS may terminate at an ingress, load balancer, API gateway, or service mesh rather than the Spring Boot JVM. In that case:

~~~mermaid
flowchart LR
    C["OAuth Client + client certificate"] -->|"mTLS"| P["Ingress / Reverse Proxy"]
    P -->|"Internal TLS + protected certificate metadata"| AS["Spring Authorization Server"]
    AS --> F["Spring Security client authentication"]
~~~

The proxy is the component performing the TLS handshake and must verify the certificate chain if using the PKI method. It can pass certificate metadata to the application via internal headers or request attributes.

### 11.1. Certificate header spoofing risk

If the application trusts headers such as X-Client-Cert or X-SSL-CERT from any request, clients can send forged headers to spoof certificates. A secure reverse proxy must:

1. Strip external client-sent certificate headers.
2. Extract the certificate directly from the verified TLS handshake.
3. Overwrite the header with a proxy-generated value.
4. Allow the backend to accept connections only from trusted proxies.
5. Protect the proxy → backend connection and block direct access bypassing the proxy.
6. Have a clear contract for certificate format/encoding; avoid inconsistent parsers.

RFC 8705 leaves secure passing of certificate metadata between the TLS terminator and the application server outside the scope of the standard. Thus, this is an architectural deployment responsibility; you cannot assume the framework automatically protects headers.

### 11.2. Maintaining proper trust boundaries

If TLS terminates at a proxy while the application needs the certificate chain to authenticate OAuth clients, you must use a controlled integration mechanism to populate the verified certificate into servlet request/TLS metadata. Never simply turn on forwarded headers or trust headers from the Internet.

## 12. Revocation, Expiry, and Certificate Rotation

### 12.1. Certificate expiry

The TLS stack checks certificate validity during path validation. An expired certificate generally cannot complete a PKI mTLS handshake. With certificate-bound Access Tokens, the token is also tied to the exact certificate; rotating the certificate causes thumbprints to mismatch.

### 12.2. Certificate revocation

PKI mTLS can check revocation status via CRL or OCSP. However, **never assume that merely importing a CA into a truststore automatically enables all forms of revocation checking**. You must configure and test revocation policies at the TLS provider/container or TLS termination point.

RFC 8705 leaves the decision of whether to check certificate revocation to the deployment. For critical workloads, define:

- CRL/OCSP sources and update mechanisms.
- Behavior when the responder is unreachable: fail-open or fail-closed.
- Cache lifetimes and revocation latency.
- Operational procedures during CA/OCSP/CRL outages.
- Procedures to revoke compromised certificates and invalidate associated tokens.

### 12.3. Zero-downtime certificate rotation

A PKI rotation plan can include:

1. Issue a new certificate from a trusted CA.
2. Ensure the new Subject DN or SAN matches registration, or update registration through a controlled process.
3. Have the client deploy the new certificate and corresponding private key.
4. Test the TLS handshake and OAuth client authentication using the new certificate.
5. Issue new tokens; if certificate-bound tokens are enabled, new tokens bind to the new thumbprint.
6. Revoke or stop accepting the old certificate after the transition window.
7. Remove the old CA/certificate from the truststore once no valid clients depend on it.

If overlap is needed, the truststore can temporarily trust both the old and new CAs, while client identity policies must still clearly distinguish which certificates are allowed for each client_id. Never let overlap turn into permission to accept any workload's certificate.

### 12.4. Separating CAs by environment

Avoid sharing the same CA/client certificates across dev, staging, and production whenever possible. Separating trust anchors limits the blast radius if a test environment is compromised. A staging certificate should never be accepted at a production Authorization Server.

## 13. Testing mTLS

Testing must cover the TLS handshake, OAuth client authentication, and certificate-bound tokens at the Resource Server.

### 13.1. Using curl with a client certificate

PEM example:

~~~bash
curl --verbose \
  --cacert auth-server-ca.pem \
  --cert orders-worker.pem \
  --key orders-worker.key \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=orders-worker" \
  --data-urlencode "scope=orders.read" \
  https://auth.example.com:8443/oauth2/token
~~~

--cacert helps curl verify the **server certificate**. --cert and --key provide the **client certificate/private key** for mTLS. Do not confuse these two trust directions.

If using PKCS12, curl supports configuring the corresponding certificate type, though you must check your curl/OpenSSL version and pass passwords securely. Never log private key passwords or client private keys.

### 13.2. Inspecting the TLS handshake

~~~bash
openssl s_client \
  -connect auth.example.com:8443 \
  -servername auth.example.com \
  -cert orders-worker.pem \
  -key orders-worker.key \
  -CAfile auth-server-ca.pem \
  -showcerts
~~~

This command lets you observe the handshake and certificate chain. It does not prove Spring Authorization Server mapped the right client_id or scopes; you must call the Token Endpoint afterward.

### 13.3. Test matrix

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | Valid client certificate, chain to root CA in truststore, DN/SAN matches client_id | TLS succeeds; OAuth client authentication succeeds |
| 2 | No client certificate sent for client using tls_client_auth | TLS may proceed if client-auth=want; Token Endpoint rejects client |
| 3 | Certificate signed by untrusted CA | PKIX handshake fails or request rejected before OAuth |
| 4 | Certificate chain missing intermediate and server cannot build path | Handshake fails |
| 5 | Certificate expired or before Not Before | Handshake fails |
| 6 | Certificate has wrong EKU/key usage per policy | Rejected |
| 7 | Valid chain, but Subject DN does not match RegisteredClient | OAuth authentication returns invalid_client |
| 8 | DN matches, but client_id does not exist | OAuth authentication returns invalid_client |
| 9 | Certificate has valid SAN, but verifier only checks DN | Rejected; configure SAN verifier if policy requires SAN |
| 10 | Revoked certificate with revocation checking enabled | Rejected per CRL/OCSP policy |
| 11 | Client uses self-signed certificate absent from JWKS | OAuth client authentication fails |
| 12 | Certificate-bound token presented with a different certificate | Resource Server returns 401 invalid_token |
| 13 | Token has right certificate, but wrong audience/scope | Resource Server rejects per authorization policy |
| 14 | Proxy receives client-sent certificate header | Proxy must strip and overwrite header; backend distrusts fake values |
| 15 | Client rotates certificate but keeps using old token | Token fails new thumbprint check |
| 16 | Backend accessed directly, bypassing proxy | Connection blocked by network policy |

### 13.4. Testing the truststore

In addition to inspecting the truststore with keytool, test that:

- Expected root CAs are present.
- Unrelated CAs were not added unintentionally.
- New certificates issued by trusted CAs can build a chain.
- Certificates from removed CAs are rejected after truststore reload/restart per deployment design.
- Nodes in a cluster use the same truststore version and policies.

## 14. Troubleshooting Common Errors

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| TLS handshake reports unknown_ca | Root/intermediate CA not in trust path | Check truststore and chain sent by client |
| unable to find valid certification path | Missing CA, broken chain, or truststore not loaded | keytool -list, check server.ssl configuration |
| handshake_failure when client sends no cert | server.ssl.client-auth=need | Check whether endpoint needs to allow clients without certificates |
| TLS succeeds, yet invalid_client | Wrong client_id, DN/SAN mismatch, or RegisteredClient not enabled for TLS auth | Check client registration and certificate verifier |
| Certificate expired | NotAfter has passed | Issue and deploy a new certificate |
| Certificate has right DN yet rejected | EKU, SAN, key usage, revocation, or other policy invalid | Check extensions and server TLS logs |
| Self-signed client rejected | Certificate does not match registered JWKS/x5c | Check jwkSetUrl, x5c, and public key |
| Token response lacks cnf.x5t#S256 | Certificate-bound tokens not enabled or no mTLS cert on token request | Check TLS client auth and TokenSettings |
| Resource Server rejects new token | Certificate presented to API differs from certificate used at token issuance | Check client cert and thumbprint |
| One node accepts, another rejects | Truststore/registration/CA versions out of sync | Check rollout and cluster configuration |
| Proxy mTLS succeeds, yet app sees no certificate | Certificate metadata not safely forwarded | Check integration between proxy and servlet container |

Do not leave TLS debug logging enabled long-term in production if logs can expose certificate details, handshake data, or internal metadata. Use short windows, restrict access, and turn it off after investigation.

## 15. Certificate Acceptance Policy Checklist

1. **Trust anchor:** only approved CAs reside in the truststore.
2. **Certificate path:** verify chain, signatures, validity, and extensions using the TLS/PKIX implementation.
3. **Client identity:** match client_id strictly against Subject DN or a chosen SAN.
4. **Key usage/EKU:** certificate is permitted for TLS client authentication.
5. **Revocation:** clearly define CRL/OCSP, caching, timeouts, and behavior when responders fail.
6. **Client registration:** only RegisteredClients permitted to use TLS_CLIENT_AUTH or SELF_SIGNED_TLS_CLIENT_AUTH.
7. **Client certificate:** private keys are protected; certificates have lifecycles, rotation, and incident procedures.
8. **TLS policy:** use appropriate TLS version/cipher policies; never keep legacy TLS settings solely for unsupported clients.
9. **Endpoint topology:** choose want/need and hosts/ports carefully; never accidentally block browsers/public clients.
10. **Reverse proxy:** strip fake headers, verify certificates at the proxy, and protect the proxy-to-app channel.
11. **Certificate-bound tokens:** if enabled, Resource Server verifies x5t#S256 against the certificate on the TLS connection.
12. **Cluster consistency:** truststores, client registry, revocation data, and certificate verifiers are synchronized.
13. **Audit:** log client_id, certificate fingerprint, issuer/subject, validation outcome, and correlation ID; never log private keys.
14. **Negative tests:** unknown CA, wrong DN/SAN, expired, revoked, missing certificate, and certificate-bound mismatches are all rejected.

## 16. Exercises and Self-Assessment Questions

**Exercise A — Distinguishing key stores.** The server has certificate auth-server.p12 and truststore oauth-client-ca.p12. Explain which file proves the server's identity and which file determines which CAs are allowed to sign client certificates.

**Exercise B — Certificate chains.** The client sends a leaf and intermediate certificate; the truststore holds the root CA. Describe how the TLS server builds the path and why the client does not need to send the root certificate.

**Exercise C — want and need.** The Authorization Server serves browser login and mTLS workloads on the same hostname. Choose the client-auth mode and explain when to separate listeners/hostnames.

**Exercise D — DN/SAN.** Two clients share the same CA but have different URI SANs. Design the client_id → SAN mapping and test that Client A's certificate cannot authenticate under Client B's client_id.

**Exercise E — Self-signed.** A workload uses a self-signed certificate. Explain why PKI TLS_CLIENT_AUTH and SELF_SIGNED_TLS_CLIENT_AUTH have different trust workflows.

**Exercise F — Certificate-bound tokens.** A token has cnf.x5t#S256 for certificate A. The client rotates to certificate B yet reuses the old token. Explain the outcome at the Resource Server.

**Review questions:**

1. How do keystores and truststores differ?
2. What is a trust anchor? Why does a truststore usually hold CA certificates instead of private keys?
3. At which layer is the leaf → intermediate → root chain verified?
4. Does a valid truststore automatically authorize every certificate from that CA as an OAuth client?
5. How does TLS_CLIENT_AUTH differ from SELF_SIGNED_TLS_CLIENT_AUTH?
6. Why does RFC 8705 require client_id in requests using mTLS client authentication?
7. Which attribute does Spring Authorization Server match by default for PKI mTLS?
8. When is a custom Certificate Verifier needed to check SANs?
9. How does server.ssl.client-auth=want differ from need?
10. Why can't external request certificate headers be trusted when TLS terminates at a proxy?
11. What data is cnf.x5t#S256 computed from?
12. How do Certificate-bound Access Tokens differ from DPoP-bound Access Tokens?
13. Why is an explicit CRL/OCSP policy needed instead of merely importing a CA into a truststore?
14. When a client rotates certificates, how must old tokens and registrations be handled?

## 17. References

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514)
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [Spring Authorization Server — Configuration Model: Mutual-TLS Client Authentication](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot — SSL Configuration](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Java keytool Documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)

**Key takeaway:** The truststore decides **which CA/certificate paths are trusted at the TLS layer**. Afterward, Spring Authorization Server must still verify **which client_id the certificate belongs to and whether it is permitted by RegisteredClient**. PKI mTLS uses chain trust and Subject DN/SAN; self-signed mTLS uses certificates registered via JWKS/x5c. If certificate-bound Access Tokens are enabled, the Resource Server must compare cnf.x5t#S256 against the actual certificate on the TLS connection. Only when these layers are configured and tested together does mTLS form a trust boundary that can be operated safely.
