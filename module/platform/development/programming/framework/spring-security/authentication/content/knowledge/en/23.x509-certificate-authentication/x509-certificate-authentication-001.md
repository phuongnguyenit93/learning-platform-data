# Client Certificate Authentication and Its Relationship to mTLS in Spring Security

## 1. Learning Objectives

X.509 client certificate authentication uses a **client-side X.509 digital certificate** as proof for a server to identify the caller. When the TLS protocol authenticates **both the server and the client**, that connection is called **mutual TLS (mTLS)**. Spring Security receives the client certificate provided by the TLS layer to map it to an application `Authentication`, and then applies authorization policies.

After this lesson, you should understand:

1. Why regular HTTPS only checks the server certificate, whereas mTLS adds the server requesting and verifying the client's certificate.
2. The roles of private key, public key, certificate chain, CA, truststore/keystore, SAN, Key Usage, Extended Key Usage, validity dates, and certificate revocation mechanisms.
3. The boundary between **TLS handshake**, **Spring Security X.509 authentication**, **user account mapping**, and **authorization**. A successful mTLS connection does not automatically turn every request into a user with full permissions.
4. How to enable client certificate requirements on the web server, configure `ServerHttpSecurity.x509(...)` for WebFlux, map the principal, and retrieve the identity from `ReactiveSecurityContextHolder`.
5. How to test with OpenSSL + `curl`, and interpret scenarios such as a missing cert, untrusted cert, valid cert with no account, and authenticated cert lacking permissions.
6. How to deploy in an environment with a reverse proxy/service mesh and avoid turning self-asserted HTTP headers into an authenticated identity.

Context: **Spring Boot WebFlux (reactive) + Spring Security**, Java 17+. PKI/mTLS principles apply to Servlet applications as well, but the main examples use WebFlux's `SecurityWebFilterChain`, not Servlet's `HttpSecurity` or `X509AuthenticationFilter`.

## 2. What Does an X.509 Client Certificate Contain and What Does It Prove?

An X.509 certificate is data signed by a CA or issuing authority that binds a **public key** to identifying attributes attested by the issuer. Common fields include:

| Component | Meaning | Things to Watch Out For |
| --- | --- | --- |
| Subject / Distinguished Name (DN) | Attributes such as `CN`, `O`, `OU` | `CN` can be used to map usernames in examples; it is not inherently a persistent or unique identifier |
| Subject Alternative Name (SAN) | Additional identities, such as DNS name, URI, email | Usually preferable to `CN` for workload identity if the organization has clear conventions |
| Issuer, certificate chain | Who issued it / chain to the trust anchor | Must be trusted by the verifier; a valid signature alone is not enough |
| Public key and signature algorithm | The public key and algorithm to verify the signature | The corresponding private key is not stored inside the certificate |
| `notBefore` / `notAfter` | Certificate validity period | Expired or not-yet-valid certificates must be rejected |
| Key Usage / Extended Key Usage | Permitted purposes for using the key | For TLS client certificates, EKU `clientAuth` is typically required depending on policy and implementation |
| Serial Number / CRL Distribution Points / OCSP | Supports managing and looking up certificate status | Certificate revocation must have a real checking strategy; do not assume every deployment automatically checks online |

**A certificate is public data; the private key is secret.** The client presents the certificate along with proof of possession of the private key during the TLS handshake (the mechanism depends on the TLS version/cipher suite). Simply copying a `.crt` file without the corresponding private key is not enough to pass mTLS.

Example filenames in a test environment:

- `client-ca.crt`: the CA certificate trusted by the server to verify clients.
- `alice.crt`: a certificate signed by the CA, containing an example identity `CN=alice`.
- `alice.key`: the private key held by Alice; do not share, do not commit.
- `server.p12`: PKCS#12 file containing the server's private key and certificate to serve HTTPS.
- `client-truststore.p12`: list of CAs/certs used by the web server to verify client certificates; it does **not** contain Alice's private key.

The name “client certificate” refers to the **role on a connection**. A service can be a server on connection A and become a client on connection B; trust and key material must be configured accordingly for each direction.

## 3. One-Way TLS, mTLS, and Application-Layer Authentication

### 3.1. Regular HTTPS

In standard HTTPS, the server sends its certificate chain; the client verifies the chain, domain name, and related TLS conditions. As a result, the client trusts that it is talking to the intended server and data in transit is protected. The server **does not thereby know the client's identity**. The application can authenticate the user via session cookie, OAuth2/OIDC, HTTP Basic, or other means.

### 3.2. Mutual TLS (mTLS)

In mTLS, the server also sends a request for the client to present a certificate. If the TLS policy requires it, the handshake is only accepted when the client presents a valid certificate chain and proves possession of the corresponding key.

```text
Client                                               Web server
  |                                                       |
  |  TLS ClientHello                                      |
  |------------------------------------------------------>|
  |                           Server certificate,         |
  |               CertificateRequest (if mTLS required)   |
  |<------------------------------------------------------|
  |  Verify server identity + trust chain                 |
  |  Client certificate + proof of private key possession |
  |------------------------------------------------------>|
  |                      Verify client certificate        |
  |<============= TLS established if valid ==============>|
  |            HTTP request over TLS                      |
  |------------------------------------------------------>|
  |                     Spring Security maps certificate  |
  |                     to principal/account/authorities  |
  |                     then checks HTTP authorization    |
  |<---------------- HTTP response -----------------------|
```

The diagram omits TLS 1.2/1.3 message details. The key point is that TLS completes **before** the HTTP/Spring Security layer processes the request. With a policy requiring a client certificate, if the handshake fails, the application has no opportunity to return a normal HTTP status.

### 3.3. Two Identification Layers, Multiple Decision Steps

| Step | Deciding Component | What Does It Ask? | If It Fails |
| --- | --- | --- | --- |
| 1. Server authentication | Client TLS stack | Is it the right server by host/SAN and trust policy? | Client aborts TLS |
| 2. Client authentication | Server TLS stack / gateway | Does the client cert have a trusted chain, valid dates, policy compliance, and proven private key? | Usually TLS handshake is rejected when `client-auth: need` |
| 3. Identity extraction | Spring Security X.509 converter + principal extractor | From the cert handed over by TLS, which principal is determined? | No matching principal / application authentication error |
| 4. Account mapping | `ReactiveAuthenticationManager` / `ReactiveUserDetailsService` | Does the principal have an account allowed to log in, not disabled, and with which roles? | HTTP authentication failure if it has entered the HTTP layer |
| 5. Permission check | `authorizeExchange` and/or method security | Is the principal authorized to call this endpoint and access this resource? | Usually HTTP 403 when authenticated but lacking permissions |

**Do not equate “trusted CA” with “authorized account”.** A CA may issue certificates to hundreds of workloads; only identities covered by application policy are permitted to perform specific actions.

A certificate can verify a **machine/service** identity, not necessarily the **human** identity using that machine. For example, a gateway has the gateway's own certificate; after mTLS from the gateway to the backend, the backend only proves that the peer is the gateway, not the end user in the browser.

## 4. Where Does Spring Security X.509 Authentication Operate?

In WebFlux, a network layer such as Reactor Netty performs HTTPS/mTLS. For a request that carries TLS information, Spring Framework can provide `SslInfo` on `ServerHttpRequest`, which includes `getPeerCertificates()`. Spring Security's X.509 authentication component reads the certificate from this source, extracts the principal, and creates a **pre-authenticated** token for the authentication manager to map into a user/authorities.

Overview of the path:

```text
Server TLS (client cert chain already verified)
   |
   v
ServerHttpRequest.getSslInfo().getPeerCertificates()
   |
   v
Spring Security X.509 authentication converter
   |
   v
X509PrincipalExtractor: X509Certificate -> principal ("alice")
   |
   v
ReactivePreAuthenticatedAuthenticationManager
   |
   v
ReactiveUserDetailsService: "alice" -> account + authorities
   |
   v
Authentication in reactive SecurityContext
   |
   v
authorizeExchange / method security / business handler
```

**Pre-authenticated** means Spring Security trusts the credential verification result from properly configured infrastructure; it does not mean Spring skips all account policies. In standard configuration, `ReactivePreAuthenticatedAuthenticationManager` can look up the account and check statuses such as locked/disabled/expired. A principal extracted from a cert is not automatically granted every role.

In **WebFlux**:

```java
// Snippet inside an @Configuration class with appropriate imports.
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .x509(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .build();
}
```

This is a **reactive** configuration API supported by Spring Security; `x509` is not a Servlet-only feature. This configuration is **not enough** to require mTLS on the socket: the web server or TLS gateway still must configure key/cert, trusted CAs, and client authentication policy.

In **Servlet**, the configuration is different, using `HttpSecurity.x509(...)` and running on the Servlet filter chain. Do not copy `HttpSecurity` into a WebFlux application. A Servlet `X509AuthenticationFilter` is not a reactive `WebFilter`.

## 5. Setting Up HTTPS/mTLS in Spring Boot WebFlux

Suppose a WebFlux application directly terminates TLS on port `8443` (with no reverse proxy terminating TLS). In a Spring Boot 3.x project with dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

The application uses the default Reactor Netty provided by the WebFlux starter. File `src/main/resources/application.yml`:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:./certs/server.p12"
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: tls-server
    trust-store: "file:./certs/client-truststore.p12"
    trust-store-type: PKCS12
    trust-store-password: changeit
    client-auth: need
```

Exact meanings:

- **`key-store`**: the **server's** private key + certificate. It allows the server to prove its identity to the client.
- **`trust-store`**: CAs trusted by the server when verifying **client certificates**. Do not confuse this with the truststore that the client uses to verify the server.
- **`client-auth: need`**: a client certificate is mandatory for the TLS connection. Without a valid cert, the HTTP handler is normally not invoked.
- **`client-auth: want`**: the server requests a cert but allows the handshake to proceed if the client does not provide one; the application still needs to decide which endpoints require authentication. `want` does not mean forcing mTLS on every request.
- **`client-auth: none`**: does not request a client certificate. Enabling `.x509()` in Spring Security alone does not replace this policy.

`changeit` and unencrypted private keys in the commands below are **only for the local lab**. Production should supply secrets via a secret manager/restricted-permission mount, apply rotation, and never commit `.key`, `.p12`, or passwords to the repository. If configuring SSL bundles (`server.ssl.bundle`), follow the bundle rules for your Spring Boot version; do not mix bundles with standalone `server.ssl.key-store`/`trust-store` properties.

If port `8443` is not listening or TLS is not working properly, **fix the TLS configuration before debugging `ServerHttpSecurity`**. The security filter cannot receive certificates that the server does not request or forward.

## 6. Complete Java Example: Mapping Certificate CN to an Account

This is a demo running in a **Spring Boot 3.x/WebFlux Java 17+ project with the dependencies listed above**. Extracting the principal from the certificate's `CN` is for demonstration only; in practice, prefer stable SAN/URI identifiers controlled by the CA and mapped via organizational policy.

The demo intentionally accepts **exactly one non-blank CN**, parsing the DN with `LdapName` instead of a naive regex. This avoids confusion caused by escaped commas in DNs; system design still needs to control which CAs are allowed to issue CNs and keep Spring Security updated to patched versions. The code below is **a single compilable Java file** when the project has valid dependencies.

Place at `src/main/java/example/mtls/MtlsApplication.java`:

```java
package example.mtls;

import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Map;
import javax.naming.InvalidNameException;
import javax.naming.ldap.LdapName;
import javax.security.auth.x500.X500Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ReactivePreAuthenticatedAuthenticationManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class MtlsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MtlsApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService clientAccounts() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}not-used-for-client-cert-auth")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            MapReactiveUserDetailsService clientAccounts) {

        var preAuth = new ReactivePreAuthenticatedAuthenticationManager(
                clientAccounts);

        return http
                .x509(x509 -> x509
                        .principalExtractor(MtlsApplication::singleSubjectCn)
                        .authenticationManager(preAuth))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/whoami").hasRole("USER")
                        .anyExchange().denyAll())
                .build();
    }

    // Demo: from a TLS-verified certificate, extract exactly one CN.
    private static String singleSubjectCn(X509Certificate certificate) {
        try {
            String subject = certificate.getSubjectX500Principal()
                    .getName(X500Principal.RFC2253);
            List<String> commonNames = new LdapName(subject).getRdns()
                    .stream()
                    .filter(rdn -> "CN".equalsIgnoreCase(rdn.getType()))
                    .map(rdn -> String.valueOf(rdn.getValue()))
                    .toList();

            if (commonNames.size() != 1 || commonNames.get(0).isBlank()) {
                throw new BadCredentialsException(
                        "Certificate must have exactly one nonblank CN");
            }

            return commonNames.get(0);
        } catch (InvalidNameException ex) {
            throw new BadCredentialsException(
                    "Invalid certificate subject DN", ex);
        }
    }

    @RestController
    static class WhoAmIController {

        @GetMapping("/whoami")
        Mono<Map<String, String>> whoAmI() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(context -> context.getAuthentication())
                    .map(MtlsApplication.WhoAmIController::response);
        }

        private static Map<String, String> response(
                Authentication authentication) {
            return Map.of(
                    "user", authentication.getName(),
                    "authenticated", Boolean.toString(
                            authentication.isAuthenticated()));
        }
    }
}
```

Explanation of key points:

1. `server.ssl.*` performs certificate verification at the **TLS layer**. `.x509(...)` performs principal extraction and authentication **at the Spring Security layer**. Both configurations work together and do not replace each other.
2. `ReactivePreAuthenticatedAuthenticationManager` uses the identity extracted from the cert to look up the account via `MapReactiveUserDetailsService`. In production, replace it with an appropriate reactive account lookup, restricting CA sources, disabled/expired accounts, and assigned permissions.
3. `.hasRole("USER")` means that in addition to being authenticated, the user must have the `ROLE_USER` authority. `anyExchange().denyAll()` makes the demo deny undeclared endpoints by default.
4. The handler returns a `Mono` and retrieves the identity through `ReactiveSecurityContextHolder`. Do not use Servlet-style thread-local `SecurityContextHolder` in WebFlux; do not call `block()` to get the principal.
5. The user has a dummy password in the fixture because `UserDetails` requires a password field; **mTLS does not check that password**. Do not accidentally enable HTTP Basic or form login just to “use” the password field.
6. `singleSubjectCn` is only a lab mapping mechanism. Do not treat an arbitrary CN as a safe identifier when the CA is allowed to issue duplicate CNs or when there are multiple trust domains. If you have a workload identity namespace based on a SAN URI, check the specific SAN type, expected trust domain, and issuance rules before mapping.

Regarding versions: newer Spring Security releases include `SubjectX500PrincipalExtractor` to replace `SubjectDnX509PrincipalExtractor`, which used legacy DN parsing. On 2026-06-09, Spring published [CVE-2026-47838](https://spring.io/security/cve-2026-47838/) about the risk of incorrect CN extraction in specially crafted certificates on older versions. Upgrading to an appropriate patched release is a separate requirement; a demo code snippet does not substitute for updating dependencies. Check the Spring Security versions published as patched by Spring, for example the 6.5 line from **6.5.11**; for older 6.3 and 6.4 lines, check their corresponding support/patch policies. Do not copy legacy configurations using `SubjectDnX509PrincipalExtractor` or regex on DNs without assessing the risk.

## 7. Generating Certificates for the Local Lab with OpenSSL and keytool

Commands in this section run in a **Bash/POSIX shell** at the project root directory (with `openssl`, `keytool` from the JDK, and `curl`). On Windows, you can use Git Bash or adapt to the corresponding shell. Only test locally: CA/keys generated here **must not be used for production**.

### 7.1. Create a CA Solely to Sign Client Certificates

```bash
mkdir -p certs

openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 30 \
  -keyout certs/client-ca.key \
  -out certs/client-ca.crt \
  -subj "/CN=Demo Client CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
```

`client-ca.key` is a highly sensitive signing key. When the server trusts `client-ca.crt`, it can accept client certificates issued by this CA if additional policy checks pass. Therefore, **the CA's scope of trust** is just as important as checking usernames.

### 7.2. Create the Server HTTPS Certificate with SAN `localhost`

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 7 \
  -keyout certs/server.key \
  -out certs/server.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
  -addext "extendedKeyUsage=serverAuth"

openssl pkcs12 -export \
  -inkey certs/server.key \
  -in certs/server.crt \
  -name tls-server \
  -out certs/server.p12 \
  -passout pass:changeit
```

The server certificate here is self-signed for the lab; therefore `curl` is passed `--cacert certs/server.crt`. Production requires a server certificate issued by an appropriate CA, and the client must verify the hostname/SAN according to TLS rules. **Do not use `curl -k` to “fix” trust errors.**

### 7.3. Create a Client Certificate with `CN=alice`, EKU `clientAuth`

```bash
openssl req -newkey rsa:2048 -nodes -sha256 \
  -keyout certs/alice.key \
  -out certs/alice.csr \
  -subj "/CN=alice"

printf '%s\n' \
  'basicConstraints=CA:FALSE' \
  'keyUsage=critical,digitalSignature' \
  'extendedKeyUsage=clientAuth' \
  > certs/client.ext

openssl x509 -req \
  -in certs/alice.csr \
  -CA certs/client-ca.crt \
  -CAkey certs/client-ca.key \
  -CAcreateserial \
  -out certs/alice.crt \
  -days 7 -sha256 \
  -extfile certs/client.ext
```

`alice.crt` is the public certificate; `alice.key` is the private key. TLS verifies the chain to `client-ca.crt`; the Spring Security demo extracts `CN=alice` and then looks up user `alice` in `MapReactiveUserDetailsService`. If the account does not exist, **a certificate valid at TLS is still not enough to be allowed into the endpoint**.

### 7.4. Create a Truststore for the Server to Verify the Client CA

```bash
keytool -importcert -noprompt \
  -alias demo-client-ca \
  -file certs/client-ca.crt \
  -keystore certs/client-truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit
```

`client-truststore.p12` must match `server.ssl.trust-store` in YAML. Do **not** put `alice.key` into the server's truststore. `client-ca.key` also does not belong in the truststore; the CA private key is only for issuing certificates in a controlled environment.

Verify the certificate was signed as expected:

```bash
openssl verify -CAfile certs/client-ca.crt certs/alice.crt
openssl x509 -in certs/alice.crt -noout -subject -issuer -dates
openssl x509 -in certs/alice.crt -noout -text
```

The first `openssl verify` command is expected to return `certs/alice.crt: OK`. The remaining commands inspect the Subject, Issuer, validity dates, and EKU in the cert. Output may vary depending on OpenSSL version; for production, add your organization's PKI procedures.

### 7.5. Run the Application

Ensure the file structure:

```text
project-root/
  certs/
    server.p12
    server.crt
    client-truststore.p12
    alice.crt
    alice.key
    client-ca.crt
  src/main/java/example/mtls/MtlsApplication.java
  src/main/resources/application.yml
  build.gradle
```

Run from project root with the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell or Command Prompt, use `gradlew.bat bootRun`. The example assumes the project has the Spring Boot Gradle plugin, the proper Java version configured, and port `8443` is not used by another process.

### 7.6. Call HTTPS with the Client Certificate

```bash
curl --show-error --silent \
  --cacert certs/server.crt \
  --cert certs/alice.crt \
  --key certs/alice.key \
  https://localhost:8443/whoami
```

Expect JSON containing the fields `"user":"alice"` and `"authenticated":"true"` (JSON property order may vary). The verification path is: **client trusts server -> server trusts client CA -> proof of private key -> CN alice -> account alice -> ROLE_USER -> response**.

## 8. Four Test Scenarios and How to Interpret the Results

### 8.1. Sending No Client Certificate When `client-auth: need`

```bash
curl -v \
  --cacert certs/server.crt \
  https://localhost:8443/whoami
```

Expect the TLS handshake or TLS session to be terminated because the server requires a client certificate. **Do not expect HTTP 401**: the request may not have reached WebFlux. Specific error names such as `certificate required`, `alert bad certificate`, `handshake failure`, or connection reset depend on TLS 1.2/1.3, implementation, and when the error is detected.

If you want public paths to still use HTTPS without requiring a client certificate, design a separate listener/gateway, or use `client-auth: want` combined with an appropriate HTTP policy. TLS `need` on the same socket applies to the entire handshake, not just a single path like `/admin`.

### 8.2. Certificate Issued by an Untrusted CA

Even if a certificate has `CN=alice`, if it does not belong to a trust chain allowed by the server, TLS must reject it. This step cannot be bypassed simply by editing the Subject to “alice”. Similarly, having `alice.crt` without the corresponding private key is insufficient to prove key possession.

### 8.3. Certificate Valid at TLS but Without a Matching Account

Create another client `CN=bob` signed by the **same CA**:

```bash
openssl req -newkey rsa:2048 -nodes -sha256 \
  -keyout certs/bob.key -out certs/bob.csr \
  -subj "/CN=bob"

openssl x509 -req \
  -in certs/bob.csr \
  -CA certs/client-ca.crt \
  -CAkey certs/client-ca.key \
  -CAcreateserial \
  -out certs/bob.crt \
  -days 7 -sha256 \
  -extfile certs/client.ext

curl -i \
  --cacert certs/server.crt \
  --cert certs/bob.crt \
  --key certs/bob.key \
  https://localhost:8443/whoami
```

Bob can pass **TLS** because the CA is trusted, but there is no user `bob` in `MapReactiveUserDetailsService`, so Spring Security rejects authentication. The specific HTTP response depends on the security entry point/error handling; the key distinction is that **this is not a TLS certificate verification error**.

### 8.4. Account Exists but Lacks Permission

If you map another valid user with `ROLE_VIEWER`, while the endpoint requires `hasRole("USER")`, Spring Security must deny authorization after authentication has succeeded, typically with HTTP **403 Forbidden**. Therefore:

```text
TLS ACCEPTED ≠ SPRING AUTHENTICATED ≠ AUTHORIZED
```

Do not conclude that mTLS is “broken” solely from a 403 status. Identify which layer blocked the request.

| Test Case | TLS | Spring Authentication | Authorization |
| --- | --- | --- | --- |
| Alice valid cert/key, account enabled, ROLE_USER | Pass | Pass | Pass |
| No client cert, server `need` | Fail | Not run | Not run |
| Self-signed cert / untrusted CA | Fail | Not run | Not run |
| Bob valid cert, account does not exist | Pass | Rejected | Not reached |
| Account exists but lacks ROLE_USER | Pass | Pass | Rejected |
| Alice expired cert | Rejected by TLS validation policy | Not run | Not run |

## 9. Principal Mapping: CN, SAN, Service Identity, and Permissions

Spring Security provides `X509PrincipalExtractor` to convert an `X509Certificate` into a principal. Depending on the version, the default implementation may extract the CN; newer versions provide `SubjectX500PrincipalExtractor`. However, **choosing which field to use and how the CA organization issues names** determines whether the identity is safe and stable.

### 9.1. Why Should CN Only Be Used in a Lab or Under Controlled Policy?

A `CN=payment-service` in a certificate is an **identifier string** set by the CA/issuer. If multiple trusted CAs can issue that same string, or a single CA issues duplicate CNs to multiple subjects, mapping solely by CN can lead to unintended permissions.

For machines/services, define an identification namespace, for example placing the identity in a **URI SAN** with a designated trust domain. The mapping process should check the exact SAN type, URI scheme, tenant/trust domain, issuing CA, environment, and workload status according to policy. Do not take an arbitrary SAN and grant a default role.

### 9.2. Custom Mapping Must Be Separated from Certificate Verification

In the example, `singleSubjectCn` does **not** verify the signature/certificate itself; that task belongs to the TLS stack. The function only extracts a name from a certificate already verified by the TLS layer. If you read an `X-Client-Cert` header or Base64 string sent by the client and parse it into an `X509Certificate` without a trust boundary, you have bypassed the TLS authentication layer.

When replacing `ReactivePreAuthenticatedAuthenticationManager` with a custom `ReactiveAuthenticationManager`, you must still:

- Verify that the account or workload is approved, check disabled/locked/expiry status, and enforce permission revocation policy.
- Assign authorities from trusted data; do not take `“ROLE_ADMIN”` directly from `OU` or fields from an insufficiently controlled issuer.
- Reject when the principal does not match; do not return `Mono.just(authentication)` with `authenticated=true` for every certificate.
- Maintain fail-closed behavior: parse errors, non-unique identities, or identifiers outside the tenant/trust domain must be rejected.

### 9.3. Distinguishing User Identity from Workload Identity

For example, a gateway has a certificate `CN=edge-gateway` and calls the backend via mTLS. The backend authenticates **edge-gateway**, without automatically knowing about the user “alice” logged into the browser at the previous hop. If the backend needs end-user authorization, it must receive and verify an appropriate delegation/end-user token mechanism, independent of the mTLS connection's workload authentication.

In microservices architectures, mTLS typically authenticates **service-to-service**, while OAuth2 access tokens/JWTs carry user or client identity/authorization scopes under a separate model. Both mechanisms can be used together; mTLS can assist with authentication/channel security, but it does not automatically create scopes, roles, or replace resource-level permission checks.

## 10. mTLS with WebClient: The Caller Must Also Present a Certificate

If a Spring WebFlux application acts as a **client** calling an API that requires mTLS, configuring `server.ssl.*` on that application itself is not enough. The outbound `WebClient` needs **client key material** (certificate + private key) and **trust material** to verify the target server's certificate.

The following Java snippet illustrates configuring a dedicated `WebClient` with Reactor Netty; place it in a configuration class with the required types imported, and handle `SSLException` according to application startup policy:

```java
import java.io.File;
import javax.net.ssl.SSLException;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

// Configuration method snippet, not a standalone application.
WebClient mtlsWebClient() throws SSLException {
    SslContext context = SslContextBuilder.forClient()
            .keyManager(
                    new File("certs/alice.crt"),
                    new File("certs/alice.key"))
            .trustManager(new File("certs/server.crt"))
            .build();

    HttpClient httpClient = HttpClient.create()
            .secure(spec -> spec.sslContext(context));

    return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .baseUrl("https://localhost:8443")
            .build();
}
```

`WebClient` continues to be used in the reactive model:

```java
Mono<String> response = mtlsWebClient()
        .get()
        .uri("/whoami")
        .retrieve()
        .bodyToMono(String.class);
```

The second snippet belongs inside a method allowed to throw/handle `SSLException`; the code does not call `block()` or `subscribe()` manually. Production configurations should use appropriate SSL bundles/secrets and manage lifecycle/key rotation instead of creating a new context/client per request. `trustManager` specifies the server trust anchor; **do not replace it with trust-all**. Hostname/SAN verification and target URL restrictions are also needed, because a client certificate should not be sent to hosts outside the defined trust domain.

## 11. What If TLS Terminates at a Reverse Proxy, Ingress, or Service Mesh?

This is the scenario most prone to misconfiguration.

### Case A: mTLS Terminates Directly at WebFlux/Netty

```text
Caller -- mTLS (client cert) --> Reactor Netty --> Spring Security .x509()
```

The Spring layer can see `SslInfo.getPeerCertificates()`. This is the model used in the demo.

### Case B: mTLS Terminates at Ingress/Proxy

```text
Caller -- mTLS --> trusted ingress -- HTTP/other TLS --> WebFlux app
                     |
                     +-- already authenticated caller cert at ingress
```

The backend receives the connection from the ingress. If the ingress does not forward the certificate or authentication result over a protected protocol, `getSslInfo().getPeerCertificates()` on the backend may be empty or only see the **ingress's certificate** on the second hop. The backend's `.x509()` **does not automatically rediscover the original certificate**.

If authentication results must be passed from the ingress, there must be an engineered and audited trust model: the ingress strips any incoming internet headers matching the identity header names, constructs an assertion/metadata from the verified TLS result, signs or transmits it over an authenticated channel between ingress and backend, and the backend only accepts it from a trusted peer and performs appropriate mapping/authorization. Do not enable “read `X-Client-Cert`, `X-Forwarded-Client-Cert`, or `X-SSL-Client-Cert` and treat as the user” when external clients can set headers themselves.

If a service mesh issues workload identities, the mesh and application must agree on **who the proven peer is**, **which hops use TLS**, how identity is propagated, and what authorization checks use. A secure TLS link to a gateway only proves the peer of that link.

### Responsibility Split Table

| Architecture | Who Verifies the Original Client's Certificate? | Does the App See the Original Cert? | What Does the App Need? |
| --- | --- | --- | --- |
| Direct TLS at WebFlux | Netty TLS stack | Yes if SSL info is properly provided | `.x509`, account mapping, authorization |
| Ingress terminates mTLS, backend HTTP | Ingress | Usually no | Verified assertion across trust boundary, separate policy |
| Ingress terminates and re-establishes mTLS to backend | Ingress on outer hop; backend verifies ingress on inner hop | Backend may see ingress cert, not original user's | Verify ingress workload and end-user identity separately |
| Service mesh mTLS between workloads | Sidecar/mesh proxy | Depends on integration; usually mesh holds channel identity | Workload policy + optional application authentication |

## 12. Testing and Observing Errors by Layer

### 12.1. Testing Certificates at the TLS Level

Test variants: valid cert; no cert; cert from untrusted CA; expired/not-yet-valid cert; wrong EKU; mismatched private key; wrong server hostname. Test with real `curl`/OpenSSL over the HTTPS port to verify the **TLS handshake**; unit tests mocking a principal do not substitute for this step.

### 12.2. Testing Account Mapping and Authorization

With a certificate accepted by TLS, create existing/non-existing identities, enabled/disabled accounts, valid/invalid roles, unusual CN/SAN values, and duplicate namespaces. Verify the application fails closed when account lookup/authorization fails. `@WithMockUser` or reactive security test fixtures are useful for business authorization tests, but **do not prove that mTLS is configured properly**.

### 12.3. Testing Asynchrony and Context Boundaries

In reactive controllers/services, retrieve the identity via `ReactiveSecurityContextHolder` or Spring-injected principal; do not rely on `ThreadLocal`. Avoid calling `block()` and manual `subscribe()`. Test concurrent requests from two certificates (e.g., Alice and a second user) to ensure principals are not mixed up. If a request triggers an outbound call, configure the client certificate and end-user identity propagation **independently** per connection.

### 12.4. Isolating Errors

| Symptom | Most Likely Cause | Check Step |
| --- | --- | --- |
| `SSLHandshakeException`, `certificate_required`, TLS alert | Missing cert, cert/key mismatch, CA/truststore, expiry, EKU, or handshake policy | Check `server.ssl.client-auth`, chain, clock/dates, key, and truststore |
| `curl` reports self-signed/untrusted server | Client does not trust server certificate or SAN mismatch | Use proper `--cacert` and correct hostname, do not disable verification |
| TLS passes, HTTP rejected | Principal did not map to an account or lacks role | Check extracted username, account status, `authorizeExchange` |
| `ReactiveSecurityContextHolder` has no user | Request not authenticated, certificate absent from `SslInfo`, or security chain did not run as expected | Verify the WebFlux filter chain and TLS topology |
| Works locally, fails behind ingress | TLS terminated before the app, or backend only sees proxy's cert | Identify peers per hop and design trust propagation |
| Revoked certificate still succeeds | CRL/OCSP not configured/verified or cached/connection still alive | Review revocation policy, connection TTL, and rotation |

Do not log full private keys, raw certificate chains, or bearer tokens. Log minimally per policy: request correlation, authentication/authorization result, error codes, and normalized workload identifier; consider privacy regarding Subject DN, SAN, and serial number.

## 13. Production Checklist

1. **PKI:** trust only necessary CAs; define trust domains, issuance procedures, SAN/EKU restrictions, and protect CA keys.
2. **Private keys:** store securely in a secret store/HSM or equivalent mechanism; restrict file permissions, manage lifecycle and rotation. Do not use lab passwords.
3. **TLS:** enable securely supported protocol versions, client-side hostname verification, `client-auth: need` on ports that truly require mTLS for all connections; clearly distinguish `want`/`need`.
4. **Identity mapping:** prefer organization-managed identifiers with verifiable uniqueness; reject ambiguity; do not use arbitrary DN regexes or rely on self-asserted headers.
5. **Spring Security:** use `ServerHttpSecurity.x509(...)` when WebFlux receives peer certificates, check account status, and grant minimal authorities; stay on patched Spring Security versions, especially for X.509 subject extraction code.
6. **Authorization:** authorize endpoints, methods, and data; a CA-signed certificate does not mean `ROLE_ADMIN`. Distinguish client workloads from end users.
7. **Topology:** identify exactly where TLS terminates; if behind a proxy/mesh, clearly design and verify hops and trusted identity assertions.
8. **Revocation/rotation:** have CRL/OCSP processes or suitable revocation/short-lived cert mechanisms; monitor cert replacement, connection reuse, expiry errors, and clock skew.
9. **Testing:** include real TLS smoke tests, wrong CA, missing certificate, non-existent account, missing permission, two concurrent identities, and proxy boundary tests.
10. **Observability:** monitor TLS handshake failures, authentication failures, 403s, certificate expiry, and rotation success without leaking keys or credentials in logs.

A trustworthy mTLS system requires **two independent decisions**: the transport layer verifies the party holding the right key; the application determines what that identity is allowed to do. Spring Security X.509 is the bridge from the TLS-provided certificate to the application's `Authentication` and authorization model.

## 14. Official and Security References

- [Spring Security — Reactive X.509 Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/x509.html): configuring `ServerHttpSecurity.x509`, principal extractor, and reactive pre-authentication manager.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): WebFlux DSL.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange` and policies.
- [Spring Boot 3.3 — Embedded Web Servers / SSL](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): keystore, SSL bundles, and Reactor Netty.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.ssl.client-auth` and truststore.
- [Spring Security — CVE-2026-47838](https://spring.io/security/cve-2026-47838/): CN extraction risk in `SubjectDnX509PrincipalExtractor` and patches.
- [Spring Security — CVE-2026-22747](https://spring.io/security/cve-2026-22747/): CN extraction risk in certain versions of `SubjectX500PrincipalExtractor`.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate structure and chain verification.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshake and certificate authentication.
