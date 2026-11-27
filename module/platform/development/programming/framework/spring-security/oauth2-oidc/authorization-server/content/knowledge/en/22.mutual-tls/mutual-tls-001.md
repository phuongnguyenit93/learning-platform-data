# Client Authentication with X.509 Certificates

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, a confidential client must prove its identity when calling the Token Endpoint. Common approaches use a client secret or a JWT assertion signed with a private key. With **mutual TLS (mTLS)**, the client proves possession of the private key corresponding to an **X.509** certificate directly during the TLS handshake. The Authorization Server verifies the certificate and binds it to a registered OAuth client.

Running example: the <code>orders-worker</code> service calls <code>https://auth.example.com/oauth2/token</code> to exchange a Client Credentials grant for an access token. Instead of sending a <code>client_secret</code>, the service establishes TLS using a client certificate issued by an internal CA. The Authorization Server validates the certificate chain, identifies the client from <code>client_id</code>, and then matches the registered subject DN or certificate attributes. When access token theft protection is needed, the Authorization Server can also bind the token to that same certificate; the Orders API requires the client to present the same certificate when calling the API.

After this lesson, you will be able to:

1. Explain how TLS client authentication differs from OAuth client authentication at the protocol layer.
2. Distinguish between the two RFC 8705 methods: PKI-based <code>tls_client_auth</code> and registered self-signed certificate-based <code>self_signed_tls_client_auth</code>.
3. Configure trust stores, client certificates, and TLS listeners to support mTLS in Spring Boot.
4. Register clients using <code>ClientAuthenticationMethod.TLS_CLIENT_AUTH</code> or <code>SELF_SIGNED_TLS_CLIENT_AUTH</code>.
5. Understand the roles of <code>X509ClientCertificateAuthenticationProvider</code>, the certificate verifier, and <code>RegisteredClient</code>.
6. Customize Subject Alternative Name (SAN) verification while preserving the certificate-to-client binding.
7. Enable certificate-bound access tokens and understand the <code>cnf.x5t#S256</code> claim.
8. Implement proof-of-possession verification on the Resource Server.
9. Design certificate rotation, revocation, TLS termination via reverse proxy, and operational testing.

**Version scope:** Examples use Spring Authorization Server 1.5.x, Spring Security 6.x, and the Servlet stack. <code>X509ClientCertificateAuthenticationProvider</code> is supported starting in Spring Authorization Server 1.3. Newer Spring Security releases that integrate Authorization Server may change packages or APIs; verify against your running version. Server/ingress TLS configurations are a separate part of infrastructure and are not created solely by the Authorization Server Java DSL.

## 2. What is mTLS?

### 2.1. One-way TLS and Mutual TLS

In standard HTTPS, the server presents a TLS certificate so the client can verify it is connecting to the right server. With mTLS, the server also requires the client to present an X.509 certificate and prove possession of the corresponding private key during the TLS handshake.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant S as Authorization Server
    C->>S: ClientHello
    S-->>C: ServerHello + server certificate
    C->>S: Verify server certificate
    S-->>C: CertificateRequest (request client certificate)
    C->>S: Client certificate chain
    C->>S: CertificateVerify (prove private key possession)
    C->>S: Finished
    S->>S: Validate TLS client certificate against trust policy
    S-->>C: TLS handshake completed
    C->>S: HTTP request over TLS
~~~

Simplified TLS 1.2/1.3 diagram. The exact message sequence depends on the TLS version and handshake mode. The key point is that the certificate is presented at the **TLS layer**, before the HTTP request to the Token Endpoint is processed. The server does not merely receive a certificate string self-submitted by the client in a form; the TLS stack verifies proof of private key possession through the handshake.

### 2.2. Why is mTLS suitable for OAuth clients?

- The client does not need to send a shared secret in every request.
- The private key can reside in a keystore, HSM, or key-protection device; the application only requests signing operations during the TLS handshake.
- Certificates have validity periods, issuers, subjects, SANs, key usage, and CA chains for identity management.
- The Authorization Server can map the certificate to the exact <code>client_id</code>.
- When combined with certificate-bound access tokens, the Resource Server can require the same certificate to prevent another party from using a stolen token.

mTLS is typically well suited for service-to-service communication, workloads in enterprise environments, partner APIs, or systems with PKI. For typical end-user browser applications, requiring certificates globally can cause the browser to display a certificate selection dialog and create an undesirable user experience.

### 2.3. Two verification layers to distinguish

| Layer | Question | Performing Component |
| --- | --- | --- |
| TLS client authentication | Did the client prove possession of the private key and present a certificate accepted by the TLS server? | TLS stack, trust store, certificate path validation. |
| OAuth client authentication | Is the received certificate registered for the exact <code>client_id</code> requesting the token? | Spring Authorization Server, <code>X509ClientCertificateAuthenticationProvider</code>, certificate verifier. |

A successful TLS handshake is **not enough** to conclude the caller is <code>orders-worker</code>. A certificate might be valid within the PKI yet belong to a different client. The Authorization Server must still bind the certificate to a registered client. RFC 8705 requires an mTLS request to include <code>client_id</code>; the server uses that ID to look up the client configuration and then matches the certificate.

## 3. Two mTLS Methods in RFC 8705

RFC 8705 defines two ways to use an X.509 certificate as an OAuth client credential:

| Method | <code>client_authentication_method</code> Code | Verification Mechanism |
| --- | --- | --- |
| PKI Mutual-TLS | <code>tls_client_auth</code> | The TLS server verifies the certificate chain up to a trusted CA; the Authorization Server matches the Subject DN or SAN against the registered client identity. |
| Self-Signed Certificate Mutual-TLS | <code>self_signed_tls_client_auth</code> | Does not rely on a public CA to verify the chain; the Authorization Server matches the certificate presented in the handshake against the certificate/JWK registered for the client, typically via JWKS containing <code>x5c</code>. |

### 3.1. PKI Mutual-TLS: <code>tls_client_auth</code>

This method is suitable when an organization has an internal CA or managed PKI:

1. A trusted CA issues a client certificate for <code>orders-worker</code>.
2. The client installs the certificate and private key into its keystore/HSM.
3. The Authorization Server's TLS listener requests a client certificate and trusts the issuing CA.
4. The TLS stack verifies the chain, validity period, signatures, key usage, and configured PKI constraints.
5. Spring Authorization Server receives the certificate chain after the handshake.
6. The provider identifies the client via <code>client_id</code> and by default compares the certificate's Subject Distinguished Name (DN) with <code>ClientSettings.x509CertificateSubjectDN</code>.

RFC 8705 allows binding by a single Subject DN value or a single SAN value. In Spring Authorization Server 1.5.x, the default verifier for <code>tls_client_auth</code> uses Subject DN. If you want to use SAN DNS/URI/IP/email, you must configure a custom certificate verifier.

### 3.2. Self-Signed Certificate Mutual-TLS: <code>self_signed_tls_client_auth</code>

This method is useful when you do not want to operate a CA for individual clients. The client registers its public certificate with the Authorization Server, directly or via a JWKS URI:

1. The client generates a key pair and a self-signed X.509 certificate.
2. The client registers the certificate in a JWK Set; the corresponding JWK contains the certificate in the <code>x5c</code> field.
3. RegisteredClient stores <code>jwkSetUrl</code> pointing to the client's JWKS (or configures the JWK Set according to the client management mechanism).
4. During the TLS handshake, the client presents the exact certificate and proves possession of the private key.
5. Spring Authorization Server fetches the registered JWK Set and looks for a certificate matching the presented certificate.

In this method, the server does not verify the certificate chain up to a public CA. Trust is established from the fact that **the certificate has been registered for a specific client** and the TLS handshake proves possession of the private key. Registering/accepting a JWKS URI must be strictly controlled; never allow clients to arbitrarily point to internal URLs or endpoints that could cause SSRF.

### 3.3. Which method to choose?

| Criterion | PKI | Self-signed |
| --- | --- | --- |
| CA Infrastructure | Requires a managed CA/trust anchors. | No shared CA needed for clients. |
| Chain verification | Yes. | Does not rely on a CA chain; verifies that the certificate matches registration. |
| Client binding | Registered Subject DN or SAN. | Registered certificate/JWK, typically via <code>x5c</code>. |
| Certificate renewal | Can issue a new certificate with the same subject from a trusted CA, per policy. | Update the certificate in the JWK Set/JWKS URI and synchronize caches. |
| Operations | Managing CA, trust store, CRL/OCSP, and certificate lifecycle. | Managing certificate registration, JWKS URI, rotation, and protecting the client private key. |

Do not choose self-signed simply to skip certificate checks. This method replaces the CA trust model with a per-client certificate registration/pinning model; you still must verify that the certificate belongs to the right client and has the corresponding private key.

## 4. X.509 Certificates and Attributes to Verify

### 4.1. Subject Distinguished Name

The Subject DN describes the subject of the certificate, for example:

~~~text
CN=orders-worker,OU=Platform,O=Example Corp,C=VN
~~~

In the default Spring Authorization Server PKI example, the expected DN value is stored in:

~~~java
ClientSettings.builder()
    .x509CertificateSubjectDN(
        "CN=orders-worker,OU=Platform,O=Example Corp,C=VN")
    .build();
~~~

A DN is an identifier represented according to X.500/X.509 distinguished name syntax. Do not compare DN strings using ad-hoc rules or assume all CAs serialize DNs in the exact same order. When multi-CA interoperability is required, standardize how DNs are normalized and compared according to appropriate rules.

### 4.2. Subject Alternative Name (SAN)

A SAN can contain one or more identifiers:

| SAN Type | Example | Use Case |
| --- | --- | --- |
| <code>dNSName</code> | <code>orders-worker.internal.example.com</code> | Identify a workload/service by DNS. |
| <code>uniformResourceIdentifier</code> | <code>spiffe://example.org/ns/prod/sa/orders-worker</code> | Identify a workload by URI/SPIFFE. |
| <code>iPAddress</code> | <code>10.20.4.15</code> | Identify by IP address in environments with stable managed IPs. |
| <code>rfc822Name</code> | <code>orders-worker@example.com</code> | Email-style identifier when required by policy. |

RFC 8705 requires binding a single chosen subject name value for a client. If using SAN, specify the exact SAN type and expected value; do not accept any SAN simply because the certificate has one valid SAN.

### 4.3. Certificate path and key usage

With PKI, the TLS stack should check at minimum:

- The certificate is not expired and is within its validity period.
- The certificate chain terminates at an approved trust anchor.
- Signatures across the certificate chain are valid.
- Basic Constraints and path length match the CA/leaf role.
- Extended Key Usage is suitable for client authentication (typically <code>clientAuth</code>).
- Key Usage is suitable for signing/proving key possession according to the algorithm.
- Certificate revocation status is checked per CRL/OCSP policy or the corresponding PKI management mechanism.

Do not rely solely on Subject DN to validate a certificate. A broadly trusted CA could issue another certificate with the same subject; RFC 8705 recommends restricting trust anchors to CAs whose issuance policies meet security requirements.

## 5. Configuring the TLS Listener in Spring Boot

Spring Authorization Server processes OAuth client authentication after the TLS handshake completes. TLS configuration is placed on the embedded server, load balancer, or ingress.

### 5.1. Requiring client certificates at the TLS layer

Example PKI configuration for Spring Boot:

~~~properties
# Server certificate: client must be able to verify the Authorization Server.
server.ssl.enabled=true
server.ssl.key-store=classpath:auth-server.p12
server.ssl.key-store-password=${AS_TLS_KEYSTORE_PASSWORD}
server.ssl.key-store-type=PKCS12

# Trust store containing CAs allowed to issue client certificates.
server.ssl.trust-store=classpath:oauth-client-ca.p12
server.ssl.trust-store-password=${CLIENT_CA_TRUSTSTORE_PASSWORD}
server.ssl.trust-store-type=PKCS12

# Request certificate but allow handshake to continue if client does not send one.
server.ssl.client-auth=want
~~~

Password values are configuration variables retrieved from a secret manager, not literal values committed to Git. The trust store must contain only the CAs appropriate for OAuth client authentication; do not include an unnecessarily broad set of CAs.

Common modes:

| <code>server.ssl.client-auth</code> | Behavior |
| --- | --- |
| <code>none</code> | Does not request a client certificate. |
| <code>want</code> | Requests a client certificate but allows the client not to send one and continues the handshake. |
| <code>need</code> | Requires a client certificate to complete the handshake. |

If the Authorization Server simultaneously serves browser login, the authorization endpoint, and regular clients, <code>want</code> is usually more appropriate than requiring a certificate on every request. For dedicated mTLS endpoints, a separate listener/hostname/port and a TLS policy requiring certificates can be used.

### 5.2. Avoiding prompting end-user browsers to select a certificate

If the TLS server requests a client certificate on the same hostname serving login, browsers may display a certificate selection dialog to users. RFC 8705 allows separating mTLS endpoints onto a dedicated hostname/port and publishing <code>mtls_endpoint_aliases</code> in metadata. Clients using mTLS select the appropriate token/introspection/revocation alias; the browser authorization endpoint continues to use the standard hostname.

Spring Authorization Server exposes endpoint paths via <code>AuthorizationServerSettings</code>, while separating hostnames, TLS connectors, routing, and publishing alias metadata are deployment configuration responsibilities. Do not assume that merely enabling <code>ClientAuthenticationMethod.TLS_CLIENT_AUTH</code> automatically creates a separate TLS listener.

### 5.3. TLS termination at a reverse proxy/load balancer

In Kubernetes/cloud environments, TLS may terminate at an ingress or load balancer before reaching Spring Boot. In that case:

- The proxy must request and verify the client certificate according to policy.
- The proxy must strip any certificate headers sent by clients from the Internet before writing verified metadata itself.
- The proxy → application channel must be protected, preferably with internal mTLS and network policies.
- The application must trust metadata only from an authenticated proxy; it must not accept direct requests from untrusted networks.
- The mechanism for forwarding the certificate chain must preserve the exact format and identity; test how the container/Spring receives the certificate.

Spring Authorization Server by default retrieves the client certificate from the Servlet TLS request context. If the proxy only adds a header such as <code>X-Forwarded-Client-Cert</code>, a trusted adapter is needed to translate the data into the appropriate request attribute/flow; never read arbitrary headers that callers can spoof. RFC 8705 does not standardize how certificate metadata is passed between a proxy and an application.

## 6. Registering a Client with tls_client_auth

### 6.1. RegisteredClient

Example of a confidential client using Client Credentials:

~~~java
RegisteredClient ordersWorker = RegisteredClient
    .withId("orders-worker-record-001")
    .clientId("orders-worker")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=orders-worker,OU=Platform,O=Example Corp,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

The example omits the repository and infrastructure beans. <code>RegisteredClient.id</code> is the internal record ID; <code>clientId</code> is the OAuth identifier sent by the client. The authentication method must match the registered certificate mapping. When using the default PKI verifier, <code>x509CertificateSubjectDN</code> is the expected DN value.

### 6.2. HTTP request at the Token Endpoint

The client uses its certificate and private key in the TLS handshake, then sends the OAuth request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=orders-worker&scope=orders.read
~~~

An mTLS request requires <code>client_id</code>. The client does not send <code>client_secret</code> to substitute for certificate authentication. The server identifies the client from the ID and then verifies whether the handshake's certificate belongs to that client.

Example call using curl:

~~~bash
curl --request POST \
  --url https://auth.example.com/oauth2/token \
  --cert ./orders-worker.crt \
  --key ./orders-worker.key \
  --cacert ./auth-server-ca.pem \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'client_id=orders-worker' \
  --data-urlencode 'scope=orders.read'
~~~

<code>--cert</code>/<code>--key</code> specify the client-side certificate and private key; <code>--cacert</code> specifies the CA so the client can verify the Authorization Server's certificate. Do not use <code>-k</code>/<code>--insecure</code> in security testing because it disables server certificate verification.

### 6.3. How does the default provider handle this?

Spring Authorization Server configures <code>OAuth2ClientAuthenticationFilter</code> with an <code>AuthenticationManager</code> containing default providers, including <code>X509ClientCertificateAuthenticationProvider</code>. This provider receives the certificate chain from the TLS request, looks up the RegisteredClient by <code>client_id</code>, and verifies the certificate according to the registered method.

For <code>tls_client_auth</code>, the default verifier compares the certificate's Subject DN against <code>RegisteredClient.getClientSettings().getX509CertificateSubjectDN()</code>. If the certificate is missing or does not match the client, client authentication fails with the OAuth error <code>invalid_client</code>.

There is no need to write a custom filter that reads the certificate and manually marks the client as authenticated. Use the Authorization Server's client authentication mechanism to preserve the proper check ordering and OAuth error results.

## 7. Registering a Client with self_signed_tls_client_auth

### 7.1. ClientSettings with JWKS URI

Example:

~~~java
RegisteredClient partner = RegisteredClient
    .withId("partner-record-001")
    .clientId("partner-service")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.SELF_SIGNED_TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("partner.data.read")
    .clientSettings(ClientSettings.builder()
        .jwkSetUrl(
            "https://keys.partner.example.com/oauth-client.jwks")
        .build())
    .build();
~~~

The JWK Set at the registered URL must contain the client's public certificate in the <code>x5c</code> field of an appropriate JWK. The first certificate element in <code>x5c</code> must match the public key represented by the JWK parameters. Spring Authorization Server uses this JWK Set to match the certificate presented during the TLS handshake.

### 7.2. Protecting the client's JWKS URI

The JWKS URI is a data source that determines client identity, so it requires:

- HTTPS and a controlled hostname.
- Domain allow-lists or URI registration policies; prevent server-side request forgery (SSRF).
- Disallowing redirects to private network IPs or untrusted hosts.
- Caching and refreshing with clear rules, including error/timeout handling.
- Never including private keys in the JWK Set; publish only certificates/public keys.
- Auditing changes to certificates/JWKS URIs with an approval workflow.

Do not use an arbitrary <code>jwkSetUrl</code> sent by the client in the token request. This is a configuration pre-registered for the client in the Authorization Server.

### 7.3. Comparison with PKI

With the self-signed method, the server does not verify the certificate chain through a CA trust store like the PKI method; instead, the certificate must match the registered certificate. If you customize the certificate verifier, you must preserve the necessary certificate/JWK matching logic. Do not apply a custom SAN verifier and inadvertently discard the default certificate pinning check of the self-signed method.

## 8. Customizing the Certificate Verifier in Spring Authorization Server

### 8.1. When is a custom verifier needed?

The default PKI verifier compares Subject DN. If an organization uses SAN DNS or URI to identify workloads, you can configure <code>X509ClientCertificateAuthenticationProvider.setCertificateVerifier(...)</code>.

The provider can be customized via <code>clientAuthentication(...).authenticationProviders(...)</code>. This API grants access to the list of default providers; locate the <code>X509ClientCertificateAuthenticationProvider</code> and set the verifier.

### 8.2. DNS SAN verification example

Suppose the application has a trusted policy service to retrieve the expected DNS SAN by registered client record ID:

~~~java
public interface ClientCertificatePolicy {
    String expectedDnsSan(String registeredClientId);
}
~~~

This is an application-defined abstraction, not a Spring API. Configuring the verifier:

~~~java
private Consumer<List<AuthenticationProvider>>
        configureDnsSanCertificateVerifier(
            ClientCertificatePolicy certificatePolicy) {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                X509ClientCertificateAuthenticationProvider x509Provider) {

            x509Provider.setCertificateVerifier(context -> {
                OAuth2ClientAuthenticationToken authentication =
                    context.getAuthentication();
                RegisteredClient registeredClient =
                    context.getRegisteredClient();

                Object credentials = authentication.getCredentials();
                if (!(credentials instanceof X509Certificate[] chain)
                        || chain.length == 0) {
                    throw new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_CLIENT);
                }

                X509Certificate leafCertificate = chain[0];
                String expectedDns = certificatePolicy.expectedDnsSan(
                    registeredClient.getId());
                if (expectedDns == null || expectedDns.isBlank()) {
                    throw new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_CLIENT);
                }

                try {
                    Collection<List<?>> subjectAltNames =
                        leafCertificate.getSubjectAlternativeNames();

                    boolean matched = subjectAltNames != null
                        && subjectAltNames.stream().anyMatch(entry ->
                            entry.size() >= 2
                            && Integer.valueOf(2).equals(entry.get(0))
                            && expectedDns.equalsIgnoreCase(
                                String.valueOf(entry.get(1))));

                    if (!matched) {
                        throw new OAuth2AuthenticationException(
                            OAuth2ErrorCodes.INVALID_CLIENT);
                    }
                } catch (CertificateParsingException ex) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT), ex);
                }
            });
        }
    });
}
~~~

In Java's SAN structure, type <code>2</code> represents <code>dNSName</code>. The example above performs an exact match of the DNS SAN against the value retrieved from a trusted policy; do not use arbitrary wildcard or suffix matching. If URI SAN is needed, the SAN type is <code>6</code>; match the URI according to an agreed rule/namespace.

**Important point:** <code>setCertificateVerifier()</code> replaces the provider's verifier. When using a custom verifier for PKI, you are responsible for checking the certificate mapping (in this example, the SAN DNS); chain validation has already been performed by the TLS stack according to the trust store. If using a custom verifier for <code>SELF_SIGNED_TLS_CLIENT_AUTH</code>, you must preserve the logic that matches the certificate against the registered JWK Set; the example above only illustrates PKI SAN and must not be applied verbatim to self-signed.

### 8.3. Attaching the verifier to SecurityFilterChain

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        ClientCertificatePolicy certificatePolicy) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .clientAuthentication(clientAuthentication ->
                clientAuthentication.authenticationProviders(
                    configureDnsSanCertificateVerifier(
                        certificatePolicy))));

    return http.build();
}
~~~

This is a configuration skeleton for the Authorization Server chain; the application also needs RegisteredClientRepository, AuthorizationServerSettings, authorization service, token generator, user authentication, and other appropriate beans. In production, if a client has both DN and SAN policies, clearly define the acceptance criteria; do not inadvertently allow a certificate to match one of overly broad identifiers.

## 9. mTLS Client Authentication and Certificate-Bound Access Tokens

These two mechanisms often go together but serve different purposes:

| Mechanism | What does it prove? | Where does it take place? |
| --- | --- | --- |
| mTLS client authentication | The client calling the Authorization Server possesses the private key of the certificate registered for the client. | TLS connection to the Token Endpoint (and other endpoints requiring client authentication). |
| Certificate-bound access token | The caller to the Resource Server possesses the private key of the exact certificate bound to the access token. | TLS connection to the API/Resource Server. |

A client can authenticate with mTLS at the Token Endpoint and still receive a **bearer access token** if token binding is not enabled. If the token is stolen, another party can use it while it remains valid. Certificate-bound tokens add proof-of-possession: the same certificate/private key must be presented when calling the API.

### 9.1. Enabling binding in RegisteredClient

~~~java
RegisteredClient mtlsClient = RegisteredClient
    .withId("mtls-client-record-001")
    .clientId("mtls-client")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.TLS_CLIENT_AUTH)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .x509CertificateSubjectDN(
            "CN=mtls-client,OU=Platform,O=Example Corp,C=VN")
        .build())
    .tokenSettings(TokenSettings.builder()
        .x509CertificateBoundAccessTokens(true)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

<code>TokenSettings.x509CertificateBoundAccessTokens(true)</code> enables binding the access token to the client certificate in supported mTLS flows. For JWT access tokens, Spring Authorization Server places the thumbprint in the <code>cnf</code> claim:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": ["https://orders-api.example.com"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint-of-certificate"
  }
}
~~~

The thumbprint value is the SHA-256 hash of the certificate's **DER encoding**, Base64URL-encoded without padding <code>=</code>. It is not a hash of the PEM text or the private key.

### 9.2. With reference/opaque access tokens

If the access token is an opaque/reference token, the thumbprint can be provided in the Token Introspection response under the <code>cnf</code> claim:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "mtls-client",
  "cnf": {
    "x5t#S256": "base64url-sha256-thumbprint-of-certificate"
  }
}
~~~

The Resource Server compares the thumbprint in the introspection response with the certificate received from the TLS connection to the API. If they do not match, it must reject the request with <code>401 invalid_token</code>.

### 9.3. The client must use the same certificate at the Resource Server

Flow:

1. The client presents certificate C1 when calling the Token Endpoint and receives a certificate-bound access token.
2. The access token contains <code>cnf.x5t#S256</code>, which is the thumbprint of C1.
3. The client calls the Orders API over mTLS and presents C1.
4. The Resource Server obtains the certificate from the TLS layer, computes its thumbprint, and compares it against the <code>cnf</code> claim.
5. If they match, it proceeds to check issuer, audience, expiry, scope, and API policy.
6. If they do not match or no certificate is present, it returns <code>401 invalid_token</code>.

If the client rotates its certificate, an access token bound to the old certificate does not automatically transfer to the new certificate. The client needs to obtain a new token per policy and use the new certificate. For confidential clients, refresh requests must also authenticate the client using the current certificate.

## 10. Resource Server Verification of Certificate-Bound Tokens

### 10.1. Thumbprint formula

RFC 8705 defines:

~~~text
x5t#S256 = BASE64URL_NOPAD(SHA-256(DER(certificate)))
~~~

Java helper:

~~~java
static String certificateThumbprint(X509Certificate certificate) {
    try {
        byte[] der = certificate.getEncoded();
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(der);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    } catch (CertificateEncodingException
            | NoSuchAlgorithmException ex) {
        throw new IllegalStateException(
            "Cannot calculate certificate thumbprint", ex);
    }
}
~~~

### 10.2. Verification logic at the API

The Resource Server must obtain the certificate **from the TLS layer** of the current request, not from a self-declared header sent by the caller. With a Servlet container, the certificate chain can usually be read via the request attribute <code>jakarta.servlet.request.X509Certificate</code> when TLS terminates at the container.

Core verification logic:

~~~java
boolean certificateMatches(
        Jwt jwt, X509Certificate[] clientCertificateChain) {

    if (clientCertificateChain == null
            || clientCertificateChain.length == 0) {
        return false;
    }

    Map<String, Object> confirmation = jwt.getClaim("cnf");
    if (confirmation == null) {
        return false;
    }

    Object expectedValue = confirmation.get("x5t#S256");
    if (!(expectedValue instanceof String expectedThumbprint)) {
        return false;
    }

    String actualThumbprint =
        certificateThumbprint(clientCertificateChain[0]);

    return MessageDigest.isEqual(
        expectedThumbprint.getBytes(StandardCharsets.US_ASCII),
        actualThumbprint.getBytes(StandardCharsets.US_ASCII));
}
~~~

This is an illustrative helper; it must be called after the JWT signature and standard claims have been verified by the decoder. In a Servlet application, you can place a filter after <code>BearerTokenAuthenticationFilter</code> to retrieve <code>JwtAuthenticationToken</code>, read the peer certificate, and reject if the helper returns <code>false</code>. If using opaque tokens, read <code>cnf</code> from the introspection result instead of a JWT.

**Do not check the certificate only at the Token Endpoint.** The Resource Server must independently verify proof-of-possession on the API connection. Also do not assume <code>oauth2ResourceServer().jwt()</code> automatically compares the <code>cnf.x5t#S256</code> claim against the TLS certificate; configure/implement the corresponding verification for your version and architecture.

### 10.3. Do not use untrusted certificate headers

If TLS terminates at an ingress/proxy, the Servlet container may not see the peer certificate directly. In that case, a protected mechanism for forwarding certificate metadata is required:

- Accept only from proxies/ingresses with an authenticated identity.
- The proxy strips certificate headers sent by Internet clients before writing verified values.
- Proxy → Resource Server uses a protected internal channel, preferably with mTLS.
- The Resource Server must not be directly reachable from external networks if it trusts headers added by the proxy.
- Test that clients cannot spoof headers such as <code>X-Forwarded-Client-Cert</code> or <code>X-SSL-CERT</code>.

## 11. Certificate Rotation and Revocation

### 11.1. PKI Rotation

With <code>tls_client_auth</code>, if the Authorization Server binds by Subject DN, the CA can issue a new certificate with the same DN for the client. Even so, you must:

1. Issue the new certificate and install the private key on the workload.
2. Verify the chain, SAN/DN, EKU, and key usage.
3. Deploy the new certificate to the client.
4. Shift traffic to the new certificate.
5. Revoke the old certificate via CRL/OCSP or PKI procedures.
6. Monitor requests still using the old certificate and close the overlap window.

If matching solely on Subject DN, both the old and new certificates with the same DN may be accepted during the overlap window. This is helpful for rotation, but the old certificate must be revoked if the old private key is compromised.

### 11.2. Self-signed Rotation

With <code>self_signed_tls_client_auth</code>, the new certificate must be registered in the client's JWK Set/JWKS URI. When rotating certificates:

- Publish a JWK containing the new certificate's <code>x5c</code>.
- Wait for caches/replicas to pick up the new data according to policy.
- Deploy the new certificate to the client.
- Verify the handshake and mapping with the new certificate.
- Remove the old certificate after the transition window or immediately upon compromise.

Do not reuse a <code>kid</code> for a different certificate/public key. Protect the JWKS URI because it is the source of truth for client identity.

### 11.3. Certificate revocation

Certificates may be revoked before expiration due to a compromised private key, lost device, compromised workload, or personnel/partner access termination. With PKI, CRL or OCSP can be used depending on the TLS stack and deployment policy. Do not assume every embedded server automatically enables revocation checking just because a trust store is configured.

With self-signed, you must remove the certificate from the registered list/JWKS and ensure caches are updated. If the certificate was already used to issue certificate-bound access tokens, the Resource Server must also handle tokens bound to that certificate; revoking a certificate at the Authorization Server does not necessarily invalidate already-issued offline JWTs immediately.

### 11.4. Certificate-bound access tokens and token lifecycle

A certificate-bound access token can no longer be used with a new certificate if the thumbprint differs. This limits the risk of stolen tokens, though it can impact clients during rotation:

- Choose an appropriate access token TTL to reduce the impact window.
- Perform certificate rotation with a controlled overlap.
- Issue new tokens using the new certificate.
- With refresh tokens, a confidential client must re-authenticate using the client certificate per the registered method.
- If the old certificate is compromised, prioritize revoking it immediately and accept forcing the client to acquire a new token.

## 12. TLS and mTLS Security Controls

### 12.1. Choose narrow trust anchors

With the PKI method, trust only CAs whose certificate issuance procedures meet requirements. If you trust all public CAs or an overly broad enterprise root, an attacker could obtain another certificate with the same Subject DN/SAN. Restrict trust anchors and bind certificate identities according to client-specific policies.

### 12.2. TLS versions and cipher configurations

Prefer TLS 1.2 or TLS 1.3 according to current security baselines, disable weak versions/ciphers, verify the server certificate on the client, and protect private keys on both sides. Do not use self-signed client certificates as an excuse to skip server certificate verification on the client.

### 12.3. Do not arbitrarily share one certificate across multiple clients

If multiple services share the same certificate/private key, revocation or investigation becomes difficult and compromising one workload impacts the entire group. Issue certificates per workload/client or per group with clear privilege boundaries; SAN/DN identifiers must tie to the corresponding client registration.

### 12.4. Prevent authentication method downgrades

A client registered with <code>tls_client_auth</code> must perform proper mTLS. Do not allow the client to send a <code>client_secret</code> or switch to <code>client_secret_basic</code> to bypass a certificate mismatch. The authentication method is dictated by RegisteredClient and server policy, not chosen per request by the client.

### 12.5. Protect the client private key

The client certificate is only a public credential; the **private key** proves possession. Protect the private key using a keystore/HSM/TPM or secret manager, restrict access permissions, avoid exporting unencrypted PEM files, never log keys, and maintain rotation/incident procedures when a workload is compromised.

## 13. End-to-End mTLS Testing

### 13.1. OAuth client authentication test matrix

| Scenario | Expected Result |
| --- | --- |
| Valid certificate, trusted chain, matching client DN | Client authentication succeeds. |
| No certificate sent for a client using <code>tls_client_auth</code> | <code>invalid_client</code>; no token issued. |
| Valid certificate but DN/SAN does not match client | <code>invalid_client</code>. |
| Client A's certificate used with Client B's <code>client_id</code> | Rejected; no cross-certificate usage. |
| Expired certificate | TLS handshake/client authentication fails. |
| Certificate chain does not reach a trust anchor | TLS handshake fails. |
| Revoked certificate with revocation checking configured | Rejected per CRL/OCSP policy. |
| Client omits <code>client_id</code> in mTLS request | Rejected per RFC 8705. |
| Client sends an invalid secret alongside TLS method | Must not allow secret to downgrade/bypass certificate. |
| SAN has matching DNS but wrong URI | Accepted only for the registered SAN type; do not accept arbitrary SANs. |
| Self-signed certificate present in registered JWKS | Succeeds when certificate matches and proof-of-possession is valid. |
| Self-signed certificate missing from JWKS | Rejected. |
| JWKS URI timeout/untrusted | Must not authenticate client using unauthorized cache/data outside policy. |

### 13.2. Certificate-bound access token matrix

| Scenario | Expected Result |
| --- | --- |
| Access token issued via mTLS with binding enabled | JWT contains <code>cnf.x5t#S256</code> or introspection returns the corresponding claim. |
| Client calls API with the same certificate used at the token endpoint | Passes certificate binding if signature/claims/scopes are valid. |
| Stolen token used from a client without the corresponding private key | Rejected. |
| Token used with a different certificate | HTTP 401 <code>invalid_token</code>. |
| Token missing <code>cnf</code> on an mTLS-bound required endpoint | Rejected per endpoint policy. |
| Certificate rotated after token issuance | Old token does not match new certificate; must obtain a new token. |
| Opaque token introspection contains <code>cnf</code> | Resource Server compares thumbprint from response against peer certificate. |
| JWT has valid signature but wrong audience | Resource Server still rejects. |
| Proxy adds untrusted certificate header | Stripped/rejected; spoofed header is not used for authentication. |

### 13.3. Integration tests with MockMvc and real TLS

MockMvc is useful for testing controller/provider logic, but it does not simulate an actual mTLS TLS handshake by itself. To prove the entire flow:

1. Create a test CA and issue a certificate for <code>orders-worker</code>.
2. Configure an embedded server or test proxy to require a client certificate.
3. Send a real HTTP request to the token endpoint using the certificate/private key.
4. Verify that requests missing a certificate or presenting the wrong client's certificate are rejected.
5. Verify that the token response has the correct scopes and binding claim when enabled.
6. Call the Resource Server over mTLS with the matching certificate, then with a different certificate.
7. Verify HTTP 401 when the thumbprint does not match.
8. Perform certificate rotation and verify behavior during the transition window.

For a custom SAN verifier, create test certificates with valid/invalid SANs, multiple SANs, wrong SAN types, and invalid certificate chains. For self-signed, test both matching and non-matching JWKS <code>x5c</code> entries.

### 13.4. Testing the reverse proxy

If TLS terminates at an ingress:

- Send a spoofed <code>X-Forwarded-Client-Cert</code> header from outside and verify the proxy strips it.
- Verify the proxy writes verified certificate metadata.
- Send a direct request to the backend and verify it is blocked.
- Replace the proxy→backend certificate and verify the backend rejects it.
- Verify the leaf certificate is forwarded properly without confusing CA/intermediate certificates for the client leaf.
- Verify the thumbprint on the Resource Server is computed from the exact certificate presented in the handshake.

## 14. Common Errors and Troubleshooting

### Error 1: RegisteredClient is configured but the handshake does not request a certificate

**Symptom:** The provider receives no certificate or the request fails with <code>invalid_client</code>.

**Cause:** The TLS listener has not enabled client authentication, the trust store is misconfigured, or the ingress does not request a certificate.

**Resolution:** Check the TLS handshake, client-auth mode, trust anchors, and the request certificate attribute in the Servlet container.

### Error 2: Handshake succeeds but the OAuth client is still rejected

**Symptom:** The TLS connection is established, yet the token endpoint returns <code>invalid_client</code>.

**Cause:** <code>client_id</code> does not exist, the certificate does not match Subject DN/SAN, or the registered method differs from the certificate method being used.

**Resolution:** Check RegisteredClient, authentication method, subject DN, and the actual certificate chain.

### Error 3: Subject DNs look identical yet still mismatch

**Symptom:** The DN in the logs looks identical to the configuration, but the verifier rejects it.

**Cause:** Differences in DN serialization/normalization, RDN ordering, escaping, or Unicode characters.

**Resolution:** Normalize and compare DNs according to an agreed DN rule; if using SAN, implement an explicit verifier for the exact SAN type.

### Error 4: Custom verifier breaks self-signed clients

**Symptom:** A client using a previously valid self-signed certificate is rejected after configuring a custom verifier.

**Cause:** <code>setCertificateVerifier()</code> replaced the default verifier that matches the certificate against the JWK Set.

**Resolution:** Apply the custom verifier only to the appropriate method, or implement complete certificate/JWKS matching logic for self-signed as well.

### Error 5: Browser login prompts with a certificate selection dialog

**Symptom:** Users open the login page and the browser asks them to pick a client certificate.

**Cause:** The TLS listener requires a certificate on the same hostname/port as the authorization endpoint.

**Resolution:** Use optional client-auth or separate the mTLS endpoint alias/hostname/port per RFC 8705.

### Error 6: Resource Server accepts JWTs, yet stolen tokens still work

**Symptom:** Another client successfully uses a bearer token even though it was issued via mTLS.

**Cause:** Client authentication was enabled only at the Token Endpoint without enabling certificate-bound access tokens, or the Resource Server does not verify <code>cnf.x5t#S256</code>.

**Resolution:** Enable token binding, require mTLS at the API, and compare the peer certificate thumbprint.

### Error 7: New certificate works at Token Endpoint, but old tokens fail

**Symptom:** After rotation, the API returns <code>invalid_token</code>.

**Cause:** The access token is bound to the thumbprint of the old certificate.

**Resolution:** Obtain a new access token using the new certificate; do not alter the thumbprint inside a signed token.

### Error 8: Proxy forwards certificate via header, but it can be spoofed

**Symptom:** A caller sends a self-crafted certificate header and the backend accepts it.

**Cause:** The backend trusts headers from any source, or the proxy fails to strip client-sent headers.

**Resolution:** Trust only an authenticated proxy, strip inbound headers, protect proxy→backend traffic, and block direct access paths.

## 15. Production Checklist

| Item | Question to Verify |
| --- | --- |
| Client registration | Correct client ID, auth method, Subject DN/SAN, or JWKS URI? |
| TLS listener | Requests client cert on the right endpoint with the right want/need mode? |
| Trust anchors | Trusts only necessary CAs? Verifies chain, EKU, key usage, and validity? |
| Revocation | Has CRL/OCSP or an appropriate certificate revocation mechanism? |
| Certificate mapping | DN/SAN/JWK certificate matches exactly one client with no cross-usage? |
| Self-signed JWKS | Trusted URI, HTTPS, SSRF protection, controlled caching and rotation? |
| Private key | Stored in keystore/HSM/TPM, not logged or exported unauthorizedly? |
| Token binding | Should <code>x509CertificateBoundAccessTokens</code> be enabled? |
| Resource Server | Requires the same certificate and compares <code>cnf.x5t#S256</code>? |
| TLS termination | Proxy metadata is authenticated and header spoofing is prevented? |
| Endpoint alias | Separated mTLS endpoints from browser authorization endpoints where needed? |
| Rotation | Has overlap window, revokes old certificates, and issues new tokens? |
| Audit | Logs client ID, certificate serial/thumbprint, issuer, timestamp, and outcome without exposing private keys? |
| Testing | Has TLS integration tests, negative cases, rotation tests, and proxy tests? |

## 16. Hands-on Exercise

An enterprise system has an Authorization Server at <code>https://auth.example.com</code> and two services: <code>orders-worker</code> and <code>billing-worker</code>. Both use Client Credentials, but only Orders is permitted to access the Orders API. The company operates an internal CA, an ingress terminates TLS, and the Resource Server requires certificate-bound access tokens.

1. Design certificate profiles for both workloads, including Subject DN or SAN, EKU, Key Usage, and TTL.
2. Register two <code>RegisteredClient</code> entries with <code>ClientAuthenticationMethod.TLS_CLIENT_AUTH</code> and distinct DNs.
3. Configure the trust store/ingress to require a client certificate; explain when to use <code>want</code> versus <code>need</code>.
4. Send a token request with <code>client_id</code> and a certificate without sending a client secret; verify that Client A cannot use Client B's certificate.
5. Write a custom certificate verifier for DNS SAN and explain why a custom verifier must perform the mapping itself.
6. Enable <code>TokenSettings.x509CertificateBoundAccessTokens(true)</code> and verify the JWT contains <code>cnf.x5t#S256</code>.
7. Write a Resource Server filter/helper comparing the actual certificate thumbprint against the <code>cnf</code> claim.
8. Demonstrate that a stolen token cannot be used from a client lacking the corresponding private key.
9. Perform certificate rotation, revoke the old certificate, and define how old access tokens must be handled.
10. Test that the ingress strips spoofed headers, forwards only verified certificate metadata, and secures the channel to the backend.

**Pass Criteria:** Demonstrate that **the TLS handshake proves possession of the private key**, **the Authorization Server binds the certificate to the correct RegisteredClient**, and when certificate-bound tokens are enabled, **the Resource Server verifies the same certificate before granting API access**.

## 17. References

- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): PKI/self-signed methods, client certificate binding, <code>cnf.x5t#S256</code>, endpoint aliases, TLS termination, and security considerations.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate path validation, extensions, CRL, and PKI.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): Subject DN representation.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): DN comparison rules.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set and the <code>x5c</code> field.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): providing metadata and status of opaque access tokens.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): client authentication, mTLS verifier, self-signed certificates, and certificate-bound access tokens.
- [Spring Authorization Server — X509ClientCertificateAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/X509ClientCertificateAuthenticationProvider.html): certificate authentication provider and <code>setCertificateVerifier</code>.
- [Spring Authorization Server — ClientSettings.Builder API](https://docs.spring.io/spring-authorization-server/docs/1.5.0/api/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): <code>x509CertificateSubjectDN</code> and client settings.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): <code>server.ssl.client-auth</code>, key store, and trust store.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification in a Resource Server.
