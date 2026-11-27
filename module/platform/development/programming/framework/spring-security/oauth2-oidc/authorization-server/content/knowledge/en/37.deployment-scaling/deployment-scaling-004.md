# HTTPS Termination, mTLS, and Certificate Configuration

The Authorization Server is the trust anchor of an OAuth 2.0 and OpenID Connect system. Clients and users rely on this server to authenticate endpoints and receive authorization codes, tokens, and public keys. Therefore, HTTPS must be designed end-to-end from the external entry point to the application; certificates and private keys must be managed as system security assets.

In this lesson, we examine three closely related parts:

- **HTTPS termination**: where the TLS connection ends, typically at a load balancer, ingress, or Spring Boot itself.
- **mTLS (mutual TLS)**: a mechanism where both sides authenticate certificates during the TLS handshake.
- **Certificate management**: how certificates are provisioned, stored, trusted, rotated, and revoked for each connection.

After completing this lesson, you will be able to select an appropriate TLS architecture, configure public URLs of the Authorization Server behind a reverse proxy, implement mTLS with the right scope, and verify certificate chains before putting the service into operation.

## 1. Why does the Authorization Server need accurate TLS configuration?

TLS provides three foundational properties:

1. **Confidentiality**: exchanged data such as authorization codes, access tokens, refresh tokens, and session cookies cannot be eavesdropped in transit.
2. **Integrity**: data cannot be silently altered while traversing the network.
3. **Server authentication**: clients verify the certificate to confirm they are connecting to the genuine domain of the Authorization Server.

When mTLS is used, the server also authenticates the client's identity at the connection layer using a client certificate. This mechanism is useful for service-to-service connections or certain OAuth profiles that require client certificates.

TLS does not replace OAuth authentication. A valid HTTPS connection only proves that both parties established a transport channel protected according to the TLS configuration; it does not grant API access on its own, replace an access token, or prove a user is logged in.

With OpenID Connect, the issuer address must be stable and match the issuer in metadata, ID Tokens, and client configuration exactly. If a reverse proxy terminates TLS while the application receives plain HTTP requests and builds URLs from internal requests, metadata may advertise `http` URLs or the wrong host. Then discovery, redirect URIs, issuer checks, and login flows can fail even though users visit the external page over HTTPS.

## 2. Choosing where to terminate TLS

TLS termination is the point where HTTPS traffic is decrypted. There are three common architectures:

| Architecture | Connection path | What the application sees | When to use |
|---|---|---|---|
| Direct TLS at Spring Boot | Client → HTTPS → Authorization Server | Request handled on the TLS connector; if mTLS is enabled, the connector receives the client certificate | Small services, fewer network hops, or when the application needs to inspect client certificates directly |
| TLS terminated at proxy | Client → HTTPS → proxy → HTTP → Authorization Server | Internal HTTP request | Suitable only when the internal network is protected, the backend accepts connections only from the proxy, and forwarded headers are controlled |
| TLS terminated and re-encrypted | Client → HTTPS → proxy → HTTPS → Authorization Server | TLS connection from proxy to application | Suitable when the internal hop across nodes, subnets, or shared networks also needs encryption |

### 2.1. Direct TLS at the application

Spring Boot's embedded server holds the server certificate and handles TLS. This model is straightforward because the application receives secure connection details directly. If client certificate requirements are enabled on the connector, the application can also obtain client certificate authentication results from the TLS handshake.

A consideration is that certificate management, renewal, and TLS configuration are tied to each application instance. When running multiple replicas, every instance must use appropriate certificates and be updated consistently.

### 2.2. TLS terminated at a load balancer or ingress

The proxy accepts HTTPS from the Internet, presents the server certificate, and forwards requests to the application. If the proxy-to-application hop uses HTTP, the request has already been decrypted on the proxy. Therefore:

- The backend must reside on a private network with no direct Internet access path.
- Firewalls or network policies must allow only the proxy to connect to the backend.
- The proxy must strip client-supplied forwarded headers and generate trusted values itself.
- Do not use plain HTTP for an internal hop that crosses untrusted or observable networks.

If those conditions cannot be guaranteed, re-encrypt the proxy-to-application hop with HTTPS or use TLS passthrough depending on client authentication requirements.

### 2.3. TLS terminated and re-encrypted

The proxy maintains two independent TLS sessions: one with the client and one with the Authorization Server. The proxy verifies the server certificate on the backend hop; the application verifies the proxy's certificate if internal mTLS is enabled.

In this model, the client certificate seen by the application on the backend hop is usually the proxy's certificate. The user's or external OAuth client's certificate is not automatically carried across the second TLS session. If the application needs the original certificate identity, you must design an authenticated identity-forwarding mechanism and trust only the designated proxy, or choose an appropriate TLS passthrough model.

## 3. Configuring public URLs behind a reverse proxy

Suppose users access the Authorization Server at https://auth.example.com, while the application runs internally at http://authorization-server:8080. The proxy must pass accurate external URL details so Spring handles redirects, cookies, and endpoints properly.

Common headers:

| Header | Meaning |
|---|---|
| Forwarded | Standardized header carrying host, protocol, and proxy address information |
| X-Forwarded-Proto | External protocol, e.g. https |
| X-Forwarded-Host | External host, e.g. auth.example.com |
| X-Forwarded-Port | External port, typically 443 |
| X-Forwarded-For | Chain of client and proxy addresses per infrastructure conventions |
| X-Forwarded-Prefix | External prefix if the proxy publishes the application under a path prefix |

The application must trust these headers only when requests arrive from a trusted proxy. If a client can send X-Forwarded-Proto: https or X-Forwarded-Host itself and the proxy forwards it verbatim, the client can distort generated URLs, affecting redirects, cookies, and security checks.

A minimal Nginx example when Nginx acts directly as the edge proxy:

~~~nginx
server {
    listen 443 ssl;
    server_name auth.example.com;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://authorization-server:8080;

        proxy_set_header Host $host;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

The example above assumes Nginx is the edge proxy and $remote_addr already reflects the client address per network configuration. If another load balancer sits in front of Nginx, configure a trusted proxy list and normalize the client address before forwarding. Never treat raw header chains sent from the Internet as trusted data.

In Spring Boot, you can enable forwarded-header handling at the framework layer:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

framework uses Spring's forwarded-header mechanism. Some runtimes may use container-native processing; pick one strategy suitable for your environment and test on the actual container being run. Do not blindly enable forwarded-header processing if the application can be reached directly from untrusted networks.

### 3.1. Declaring the public issuer

Configure the issuer explicitly using the public HTTPS address:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

The issuer must match the exact value clients use to identify the Authorization Server, including scheme, hostname, port if applicable, and path if applicable. Do not let each replica derive the issuer from an internal hostname or container IP address.

After deployment, check the discovery metadata at the endpoint corresponding to the configured issuer. When the issuer is at the root domain, the URL is typically:

~~~bash
curl --fail --show-error https://auth.example.com/.well-known/openid-configuration
~~~

Compare the issuer, authorization_endpoint, token_endpoint, jwks_uri fields, and published endpoints. Public URLs must use the proper scheme, host, and path. If the system uses an issuer with a path prefix or custom endpoint paths, verify the discovery URL according to your actual configuration.

At the same time, client redirect URIs must match the registered callback URIs exactly. Use HTTPS for deployed environments; loopback exceptions for certain native apps must follow the corresponding OAuth rules. Also check logout URLs and URLs embedded in frontend applications.

## 4. Configuring server certificates in Spring Boot

A server certificate setup typically consists of:

- **Leaf/server certificate**: certificate issued for the public hostname or backend hostname.
- **Private key**: the private key matching the certificate; must be kept confidential.
- **Intermediate CA certificates**: intermediate certificates enabling clients to build the trust chain.
- **Root CA**: trust anchor usually pre-installed in the client's trust store.

The Subject Alternative Name (SAN) field must contain the hostname used by clients. Setting only the Common Name does not satisfy SAN validation in modern TLS clients. The server certificate must have the appropriate extended key usage, typically serverAuth.

### 4.1. Embedded server configuration

When Spring Boot terminates TLS directly, configure the keystore as follows:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/authorization-server.p12
    key-store-type: PKCS12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}
    key-alias: authorization-server
    enabled-protocols: TLSv1.2,TLSv1.3
~~~

Secret values must be supplied by a secret manager or the deployment platform's secret mechanism. Do not commit passwords, private keys, or real keystores to Git. The file path in the example points to a file mounted into the container; ensure the application process has read permission while unrelated users and containers cannot access it.

If TLS already terminates at the ingress and the backend uses HTTP, server.ssl settings on the application do not replace the certificate on the ingress. If the backend uses HTTPS, configure server.ssl for the backend certificate and configure the proxy to validate that certificate. Clearly distinguish the public edge certificate from the certificate used on the internal hop.

### 4.2. Keystore and truststore

| Component | What it contains | Purpose |
|---|---|---|
| Keystore | The server's own certificate and matching private key | Proves server identity during the TLS handshake |
| Truststore | Trusted CAs or certificates | Verifies peer certificates, such as client certificates or proxy certificates |

Do not place client private keys into the server's truststore. A truststore normally holds CAs authorized to issue client certificates, rather than arbitrarily adding individual certificates. If adding only a root CA, review issuance policies to avoid accepting unintended certificates issued by that CA outside the desired scope.

## 5. Implementing mTLS

In one-way TLS, the client verifies the server's certificate. In mTLS, the server also requires the client to present a certificate during the handshake and verifies that certificate's trust chain.

Client certificate validation should check at minimum:

1. Signature and certificate chain leading to a trusted CA.
2. Validity period and revocation status per policy.
3. Permitted SAN or certificate identifier.
4. Extended Key Usage matching clientAuth.
5. Rules mapping the certificate to a specific client identity.

Merely validating the certificate does not mean the client is permitted to call every endpoint. After the TLS step, the application or gateway still needs to map the identity to a client registration, check permissions, and enforce access scope limits.

### 5.1. Requiring certificates on the embedded server

If every request arriving on a connector must present a client certificate, Spring Boot can use a truststore and client-auth: need:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/authorization-server.p12
    key-store-type: PKCS12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD}
    key-alias: authorization-server
    trust-store: file:/run/secrets/client-ca.p12
    trust-store-type: PKCS12
    trust-store-password: ${CLIENT_TRUSTSTORE_PASSWORD}
    client-auth: need
    enabled-protocols: TLSv1.2,TLSv1.3
~~~

client-auth: need requires clients to send a valid certificate on every request hitting this connector. want requests a client certificate but allows the handshake to proceed if none is provided; the application must decide how to handle requests missing an identity. This setting applies at the connector level, not automatically scoped to the token endpoint alone.

Because regular user browsers do not carry client certificates, enabling need on a connector that also serves the authorization endpoint, login page, and consent UI can break interactive flows. If only a subset of APIs or the token endpoint requires mTLS, consider a dedicated hostname, listener, or gateway with an appropriate mTLS policy. Thoroughly test endpoint scope and browser flows before applying.

If an ingress terminates external TLS, the configuration above only demands a peer certificate on the ingress-to-application hop. That peer is normally the ingress, not the external OAuth client's certificate. For the application to authenticate OAuth clients by their original certificate, ensure that identity is conveyed over a trusted channel or pass the client's TLS handshake through to the component performing authentication.

### 5.2. mTLS at the ingress

An ingress or API gateway can require client certificates right at the entry point. This approach centralizes CA management, certificate policies, and access restrictions at the network edge.

If the gateway passes authentication results to the application via headers, all of the following conditions must be satisfied:

- The gateway strips any headers with the same name sent by clients before creating the authentication header.
- The gateway writes the identity only after verifying the certificate and CA policy itself.
- The backend accepts connections only from the gateway, over a private network with explicit policies.
- The header has a standardized format, size limits, and is protected on the gateway-to-backend hop.
- The application trusts the header only from the authenticated gateway; never accept values supplied on direct requests.

Do not simply forward a raw PEM string or a header like X-Forwarded-Client-Cert and assume it is valid proof. The application needs to know which gateway verified the certificate, which checks the gateway performed, and that identity data could not be tampered with in transit.

## 6. Distinguishing transport-layer mTLS from OAuth 2.0 mTLS

OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens are specified in RFC 8705. There are two distinct capabilities:

- **mTLS client authentication**: the Authorization Server uses the TLS certificate to authenticate the OAuth client at the token endpoint.
- **Certificate-bound access token**: the access token is bound to the client certificate; the Resource Server verifies that the client presenting the token also possesses the corresponding certificate.

These two capabilities can be deployed together or independently depending on system profiles and policies. A TLS setting like server.ssl.client-auth: need only requires a certificate at the transport connection layer. It does not automatically:

- map the certificate to an OAuth client registration;
- validate the tls_client_auth or self_signed_tls_client_auth client authentication method;
- add the certificate thumbprint to the access token's confirmation claim;
- cause the Resource Server to verify the certificate when receiving an access token.

When implementing RFC 8705, confirm which parts are supported by your Spring Authorization Server version and integration components. If extensions are needed, clearly design the authentication provider/converter, lookup of registered certificates, client mapping rules, issuance of certificate-bound tokens, and verification step at the Resource Server. Do not treat enabling mTLS at the ingress as completing all of RFC 8705.

## 7. Certificate lifecycle and protection

### 7.1. Provisioning and validation

Before placing a certificate into a deployment environment, verify:

- SAN contains the exact DNS names clients access.
- Not Before and Not After dates fit the issuance window.
- Issuer and intermediate chain match the expected CA.
- Key Usage and Extended Key Usage match the server or client role.
- Signature algorithm and key size satisfy current security policies.
- The private key actually matches the public key in the leaf certificate.

Do not reuse the same certificate and private key across every role just to reduce operational effort. Separating public edge certificates, backend service certificates, and client certificates allows revoking or rotating each scope without disrupting the entire system.

### 7.2. Storing private keys

Place private keys and keystores in a secret manager, HSM/KMS, or platform-managed secret store. With Kubernetes, you can mount secrets as read-only files and restrict access per service account. Ensure backups, logs, build artifacts, and crash dumps do not inadvertently include private keys or keystore passwords.

Passwords in environment variables are merely a way to pass configuration; they do not replace a secret manager. Restrict process environment read permissions, avoid logging secret values, and do not include secret contents in exceptions or diagnostic reports.

### 7.3. Rotation and revocation

Rotation procedures should include an overlap window:

1. Issue the new certificate and verify its trust chain, SAN, EKU, and validity dates.
2. Update truststores or CA bundles on parties that need to verify the new certificate.
3. Deploy the new certificate to proxies or applications; verify every replica has received the updated configuration.
4. Test handshakes, discovery, the token endpoint, and actual mTLS connections.
5. Once no clients still use the old certificate, remove the old certificate or CA per policy.

Some runtimes do not automatically reload keystores when files are replaced. Verify reload capabilities of your container/proxy; if unsupported, perform a controlled rolling restart. Avoid replacing certificates across all replicas simultaneously without a rollback plan.

When a private key is compromised or a client certificate is no longer authorized, revoke the certificate and update CRL/OCSP or trust policies according to infrastructure capabilities. Also evaluate already-issued tokens: revoking a certificate does not automatically revoke all valid access tokens, unless the Resource Server enforces certificate binding checks or a corresponding revocation mechanism.

## 8. Post-deployment verification

### 8.1. Checking the server certificate

Inspect the certificate presented by the public endpoint:

~~~bash
openssl s_client \
  -connect auth.example.com:443 \
  -servername auth.example.com \
  -verify 5 \
  -verify_hostname auth.example.com \
  -showcerts \
  -verify_return_error
~~~

Inspect certificate details from a file:

~~~bash
openssl x509 -in fullchain.pem -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

The output should show the right hostname in SAN, valid dates, and a verifiable certificate chain. Test from a network or trust store similar to real client environments; an admin workstation with internal CAs installed may produce different results than an external client.

### 8.2. Checking metadata and endpoints

~~~bash
curl --fail --show-error \
  https://auth.example.com/.well-known/openid-configuration
~~~

Read the metadata and confirm that the issuer, authorization endpoint, token endpoint, JWKS URI, and other endpoints use the proper public URLs. Continue testing the authorization code flow with PKCE, callback URI, consent, and exchanging the code for tokens. Verify that session cookies are set with appropriate attributes such as Secure, HttpOnly, and SameSite according to the application flow.

### 8.3. Checking mTLS

For endpoints requiring mTLS, test both with and without a client certificate:

~~~bash
# Connection with client certificate
openssl s_client \
  -connect mtls.auth.example.com:443 \
  -servername mtls.auth.example.com \
  -verify 5 \
  -verify_hostname mtls.auth.example.com \
  -cert client.crt \
  -key client.key \
  -CAfile server-ca.pem \
  -verify_return_error
~~~

Also test expired certificates, certificates issued by untrusted CAs, certificates with the wrong key usage, and certificates not mapped to an authorized client. Each case must fail per policy. If a gateway handles mTLS, also test direct access paths to the backend to ensure identity headers cannot be spoofed.

## 9. Common issues

| Symptom | Possible cause | What to check |
|---|---|---|
| Metadata publishes http URLs | Application does not receive or trust forwarded headers | Check whether proxy sets X-Forwarded-Proto: https, forwarded-header strategy, and issuer |
| Redirects point back to internal hostname | Proxy does not forward Host/X-Forwarded-Host properly or issuer is not fixed | Compare request headers, issuer, and registered redirect URIs |
| Client reports hostname mismatch | SAN lacks the accessed hostname or proxy presents the wrong certificate | Inspect SAN and SNI with openssl s_client |
| TLS handshake fails | Missing intermediate, untrusted CA, incompatible protocol/cipher, or expired certificate | Check certificate chain, expiration, and handshake logs on both ends |
| mTLS rejects valid client | Truststore lacks CA, client omits intermediate, or EKU/identifier is wrong | Check chain, EKU, SAN, and actual truststore on connector/gateway |
| Login page fails to open when mTLS is enabled | Connector demands a client certificate even for user browsers | Check listener scope and separate endpoints requiring mTLS |
| Application sees proxy identity instead of OAuth client | TLS terminates at ingress and a new TLS session is opened to backend | Identify where client certificates are verified and design secure identity forwarding |
| Only some replicas work after rotation | Keystore/truststore out of sync or runtime did not reload | Check secret version and certificates on each replica |

## 10. Deployment checklist

- [ ] All public endpoints of the Authorization Server use HTTPS and certificates have accurate SANs.
- [ ] Only TLS 1.2/1.3 are enabled per system compatibility policy.
- [ ] It is clearly defined whether TLS terminates at the edge, at the application, or is re-encrypted on the backend hop.
- [ ] HTTP backend is reachable only from trusted proxies; if crossing untrusted networks, TLS is used.
- [ ] Proxy strips forwarded headers from clients and writes headers from verified data.
- [ ] Spring handles forwarded headers properly for the running proxy/container type.
- [ ] Issuer and metadata publish stable public HTTPS URLs.
- [ ] Registered redirect URIs, logout URIs, and callbacks match exactly.
- [ ] Keystores and truststores are separated, granted least-privilege access, and sourced from a secret store.
- [ ] mTLS is enabled only on intentional listeners/endpoints; impact on browsers and consent flows has been tested.
- [ ] If using RFC 8705, OAuth client authentication and certificate-bound access tokens at the Resource Server have been tested separately.
- [ ] Rotation, revocation, rollback, and per-replica verification procedures exist.
- [ ] Handshake, discovery, authorization code with PKCE, token endpoint, and invalid certificate cases have been tested.

## Conclusion

Designing HTTPS for an Authorization Server starts with choosing the right TLS termination point and protecting every connection hop. When placed behind a reverse proxy, forwarded headers must come from a trusted proxy and the issuer must reflect the HTTPS URL clients actually use. mTLS adds certificate-layer authentication, though its scope and how certificates map to OAuth clients must be designed explicitly. Good certificate management requires storing private keys securely, verifying trust chains, and having rotation and revocation procedures tested before operations begin.
