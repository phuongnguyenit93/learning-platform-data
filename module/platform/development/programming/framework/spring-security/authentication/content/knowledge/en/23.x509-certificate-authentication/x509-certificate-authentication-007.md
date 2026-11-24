# Certificate Expiration, Revocation, and Trust Chain Testing

X.509 certificate authentication relies on multiple conditions **simultaneously**: the certificate is within its validity period, the certificate chain is validly signed and leads to a trusted **trust anchor**, the key/certificate matches its intended purpose, the revocation status complies with policy, and the identity maps accurately to an application account. A certificate with a valid signature can still be expired, revoked by the CA, issued by an unauthorized CA, or carry an unprovisioned identity.

In Spring Security applications using **mutual TLS (mTLS)**, client certificate verification belongs first to the **TLS stack** (for example, Tomcat + JSSE or an API gateway). Only when the TLS handshake is accepted does Spring Security get the chance to read the certificate, determine the principal, and load authorities. Therefore, clearly distinguish **TLS/PKIX-layer** errors from **HTTP authorization** errors: a certificate rejected at TLS typically produces no HTTP 401/403 response from the application.

This lesson focuses on **certificate expiration, revocation, and trust chain testing** in the context of X.509 authentication on Spring Security Servlet, with examples in Java 17+, Spring Boot 3.x, Spring Security 6.x, and OpenSSL 3.x. Domain names and `.pem`/`.p12` files are illustrative fixtures; never use a production CA to issue or revoke certificates solely to run test exercises.

## 1. Three Mandatory Questions When Verifying X.509

| Check Group | Core Question | Typical Checks |
| --- | --- | --- |
| **Validity period** | Is the certificate currently valid, or has it expired? | `notBefore`, `notAfter`, system clock, intermediate validity |
| **Trust chain and purpose** | Who signed the certificate? Is there a path to an allowed CA? Is it for the right TLS purpose? | Signature, path building, trust anchor, Basic Constraints, Key Usage, EKU, SAN/hostname |
| **Revocation** | Did the CA withdraw validity before expiration? | CRL, OCSP, response signature and freshness, fail policy |

Checking all three is **not enough to grant application permissions**: after a client certificate passes, the application still must identify the user and business permissions. For example, client `CN=client-linh` may pass mTLS yet receive HTTP 403 if the application account lacks the `API_READ` authority.

X.509 fields commonly inspected:

- `Subject` and `Issuer`: identify the subject and issuing CA; matching expected strings **does not replace** signature verification.
- `Serial Number`: identifies the certificate within the issuer's scope, crucial when checking CRL/OCSP. Serial alone is not globally unique across all CAs.
- `Not Before`/`Not After`: validity window of each certificate.
- `Subject Alternative Name (SAN)`: DNS/URI/email identities... For HTTPS server certificates, the hostname must match SAN per client policy.
- `Basic Constraints`: determines whether a certificate may act as a CA and limits chain depth.
- `Key Usage`: key permissions such as digitalSignature or keyCertSign.
- `Extended Key Usage (EKU)`: e.g., `clientAuth` (TLS Web Client Authentication) and `serverAuth` (TLS Web Server Authentication).
- `Authority Key Identifier`, `Subject Key Identifier`: assist in linking keys/issuers during path building.
- `CRL Distribution Points` and `Authority Information Access`: can point to CRL, OCSP, or intermediate CA sources. Having URIs inside a certificate **does not mean** every runtime automatically downloads them or enables revocation checks.

## 2. Trust Chains: Root, Intermediate, and Leaf

Example of an organization issuing mTLS certificates to employees:

~~~text
Server TRUSTSTORE
└── Corporate Root CA                   [Trust Anchor]
          │ signs
          ▼
    Employee Issuing CA                 [Intermediate CA]
          │ signs
          ▼
    client-linh                         [Leaf / End-Entity]
    EKU: TLS Web Client Authentication
          │ uses private key during TLS handshake
          ▼
    Client connects via HTTPS to server
~~~

A **trust anchor** is the root that the verifier **has explicitly chosen to trust** via configuration. The server truststore holds CAs allowed to issue client certificates; the server keystore holds the server's private key and certificate presented to the client. The client also has its own trusted CAs to verify the server certificate.

In the PKIX algorithm, the validator must build and verify a path from the leaf through issuers/intermediates to a trust anchor. An intermediate sent over TLS is merely data for building the path, and is **not automatically trusted**. Key conditions include:

1. Every certificate's signature under its issuer certificate must be valid.
2. Every intermediate acting as a CA must satisfy `basicConstraints CA=true`, key usage, and applicable `pathLenConstraint`.
3. Validity periods and algorithm/policy constraints must pass the validator.
4. The path ends at a trust anchor within the allowed CA set, not an arbitrary self-signed root.
5. For mTLS, the leaf certificate must suit client authentication; for HTTPS servers, the server certificate must also match the connection hostname.

**Missing intermediate:** the leaf may be signed by a valid CA, yet the server cannot locate the issuer to build the chain. **Wrong root:** the signature may verify under another CA, but that CA is absent from the application's truststore. **Wrong EKU:** the chain is valid, yet the certificate is only for `serverAuth`, unsuitable as a client certificate.

Never conclude a chain is valid just because `Subject` and `Issuer` names match; you must use signature/PKIX verification algorithms.

## 3. Expiration: Checking Not Before and Not After

Certificate validity is defined by two timestamps:

~~~text
                   Validity period
notBefore  |================================|  notAfter
           |                                |
 Before mark: not yet valid          After mark: expired
~~~

- **Not Before:** clients should not use the certificate before this timestamp. Failures usually indicate a certificate issued with a future start time or clock skew on the verifying host.
- **Not After:** a certificate expires past its validity end time; it cannot be “renewed” by changing the JVM clock or editing PEM metadata.
- **Intermediate expiry:** a valid leaf whose intermediate in the chain has expired can still cause path validation to fail.
- **Clocks:** validity checking uses the clock where validation runs. Synchronize NTP and understand UTC timestamps; UI displays in local time zones can cause confusion.

### 3.1. Reading Validity Dates and Extensions with OpenSSL

~~~bash
openssl x509 -in pki/client-valid.pem -noout -subject -issuer -serial -dates
openssl x509 -in pki/client-valid.pem -noout -text
~~~

Typical validity output contains `notBefore=...` and `notAfter=...`. `-text` helps locate `Basic Constraints`, `Key Usage`, `Extended Key Usage`, `Authority Information Access`, and `CRL Distribution Points`. This is only **reading certificate structure**, not checking truststores or revocation status.

If the certificate is inside a PKCS#12 file:

~~~bash
keytool -list -v -storetype PKCS12 -keystore pki/client-keystore.p12
~~~

`keytool` typically prompts interactively for a password. Never place keystore passwords in command history, source code, or CI logs. Inspect all certificates in the chain and relevant aliases, not just the leaf.

### 3.2. Testing at a Specific Point in Time

You can verify a path at a fixed UNIX timestamp (for example, 2026-11-06 00:00:00 UTC):

~~~bash
openssl verify \
  -CAfile pki/root-ca.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  -attime 1793923200 \
  pki/client-valid.pem
~~~

`-attime` tells OpenSSL to evaluate validity at the chosen timestamp, useful when testing not-yet-valid or soon-to-expire certificates. It **does not change Spring Boot/Tomcat's clock** and does not replace historical revocation tests. The timestamp used must match your test fixture's timeframe.

### 3.3. Checking Validity with Java 17

`X509Certificate.checkValidity()` checks validity dates on a single certificate. The standalone program below reads a `.pem` file and checks both the current time and a fixed timestamp.

File `CertificateTimeCheck.java`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Date;

public class CertificateTimeCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CertificateTimeCheck <cert.pem>");
            System.exit(2);
        }

        X509Certificate cert;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            cert = (X509Certificate)
                    CertificateFactory.getInstance("X.509")
                            .generateCertificate(in);
        }

        System.out.println("Subject: " + cert.getSubjectX500Principal());
        System.out.println("Issuer: " + cert.getIssuerX500Principal());
        System.out.println("NotBefore: " + cert.getNotBefore().toInstant());
        System.out.println("NotAfter: " + cert.getNotAfter().toInstant());

        try {
            cert.checkValidity();
            System.out.println("Current time: VALID");
        } catch (CertificateExpiredException e) {
            System.out.println("Current time: EXPIRED");
        } catch (CertificateNotYetValidException e) {
            System.out.println("Current time: NOT_YET_VALID");
        }

        Instant fixedTime = Instant.parse("2026-11-06T00:00:00Z");
        try {
            cert.checkValidity(Date.from(fixedTime));
            System.out.println("Fixed time: VALID");
        } catch (CertificateExpiredException e) {
            System.out.println("Fixed time: EXPIRED");
        } catch (CertificateNotYetValidException e) {
            System.out.println("Fixed time: NOT_YET_VALID");
        }
    }
}
~~~

Compile/run with JDK 17+ once a certificate file is present:

~~~bash
javac --release 17 CertificateTimeCheck.java
java CertificateTimeCheck pki/client-valid.pem
~~~

Subject/Issuer/NotBefore/NotAfter values and the two result lines depend on **actual certificate contents**, so there is no fixed stdout for illustrative files. If `checkValidity()` succeeds without error, you can only conclude the certificate is valid **with respect to time**. This method does not verify signatures, trusted CAs, revocation, hostnames, purposes, or application permissions. To verify chains, use PKIX `CertPathValidator` or a properly configured TLS trust manager.

## 4. Certificate Revocation Before Expiration

**Revocation** occurs when a CA withdraws a certificate's validity before `notAfter` is reached—for instance due to private key compromise, lost device, disabled account, or mis-issuance. “Not expired” **does not mean** “not revoked”.

Statuses to distinguish:

| Result | What Can Be Inferred? |
| --- | --- |
| `expired` | Invalid by time, even if OCSP/CRL does not list the serial yet |
| `not yet valid` | Not yet within active timeframe, not a revocation state |
| `revoked` | Valid CA/responder reported that the certificate's validity was withdrawn |
| OCSP `good` | Responder states the certificate is not revoked per its source and timestamp; chain/purpose still must be verified |
| OCSP `unknown` | Status could not be determined; **do not convert to good** |
| CRL/OCSP unreachable | Status unproven; requires an explicit hard-fail/soft-fail policy |

### 4.1. CRL — Certificate Revocation List

A CRL is a list of revoked serial numbers **signed by the CA**. A usable CRL requires matching issuer/scope, valid signature, appropriate `thisUpdate`/`nextUpdate` timestamps, and sufficient freshness. If full-chain checking is enabled, valid CRLs are needed for the leaf and verified intermediates, not just the leaf CRL file.

Pros: downloadable/cacheable, supports offline checking while the CRL remains valid. Cons: lists can grow large, and periodic publishing creates latency between revocation and verifiers receiving the latest list.

**Do not assume CRLDPs are automatically downloaded.** A certificate containing a CRL URI is only a hint; whether the runtime fetches/caches/checks it depends on separate configuration.

### 4.2. OCSP — Online Certificate Status Protocol

OCSP queries a responder for the status of a certificate by issuer and serial. Responses must be verified for signature, OCSP signing certificate/authorization, freshness, and `good`/`revoked`/`unknown` status.

An HTTP 200 response from an OCSP server or the word `good` from an unverified source is **not sufficient** to grant access. OCSP can encounter network errors, expired `nextUpdate`, or return `unknown`; handling rules must be defined.

**Distinguish OCSP stapling:** many guides describe a server stapling an OCSP response for the **server** certificate during the HTTPS handshake. That does not prove the **server checked client certificate revocation** under mTLS. Check the policy of whichever party is authenticating the certificate.

### 4.3. Hard-Fail and Soft-Fail

| Scenario | Hard-fail | Soft-fail |
| --- | --- | --- |
| Certificate revoked per valid response | Reject | **Still reject** |
| Unable to fetch CRL/OCSP due to network error | Reject | May proceed if policy permits |
| Stale OCSP response / invalid signature | Do not accept as good evidence | Reject forged data; handle error per policy |
| OCSP status `unknown` | Do not treat as good | Do not default to good |

`PKIXRevocationChecker.Option.SOFT_FAIL` in Java only allows ignoring **specific defined errors** when revocation info cannot be obtained; it is not an option to “ignore revoked certificates”. For high-security systems, hard-fail prevents accepting certificates when revocation sources are unreliable, though it requires solid SLAs/timeouts/caching to avoid service-wide outages.

## 5. Chain Testing with OpenSSL

Suppose the test PKI has these files:

~~~text
pki/
├── root-ca.pem
├── intermediate-ca.pem
├── client-valid.pem
├── client-expired.pem
├── client-revoked.pem
├── client-untrusted.pem
├── client-server-only.pem
├── issuing-ca.crl.pem
├── client-valid.key
└── server-root.pem
~~~

Every certificate must be validly generated by a test CA for the simulated scenario. Simply renaming a file to `client-revoked.pem` does **not** make it revoked.

### 5.1. Verifying Chain/Trust Anchor and Client Purpose

~~~bash
openssl verify \
  -show_chain \
  -CAfile pki/root-ca.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  pki/client-valid.pem
~~~

- `-CAfile`: CA that the command **explicitly trusts**, usually the root in the fixture.
- `-untrusted`: supplies intermediates to build the chain; does **not** add intermediates as trust anchors.
- `-purpose sslclient`: requires verifying TLS client usage, including corresponding constraints in OpenSSL.
- `-show_chain`: prints the constructed chain to cross-check against expected issuers.

With a genuinely valid fixture, output includes:

~~~text
pki/client-valid.pem: OK
~~~

This command does **not** prove revocation was checked unless revocation options are passed; nor does it test client possession of the private key in a TLS handshake.

### 5.2. Testing Missing Intermediate and Wrong Root

When intermediates are omitted (and unavailable elsewhere), the command can fail:

~~~bash
openssl verify -CAfile pki/root-ca.pem \
  -purpose sslclient pki/client-valid.pem
~~~

When using a root that is not the valid issuer:

~~~bash
openssl verify \
  -CAfile pki/unrelated-root.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  pki/client-valid.pem
~~~

Results may report `unable to get local issuer certificate`, `unable to verify the first certificate`, or an error matching the fixture. Do not assume identical error codes/stdout strings across OpenSSL versions.

### 5.3. Checking CRLs and Revoked Certificates

~~~bash
openssl crl \
  -in pki/issuing-ca.crl.pem \
  -noout -issuer -lastupdate -nextupdate
~~~

The command above inspects CRL metadata; to view revoked serial numbers:

~~~bash
openssl crl -in pki/issuing-ca.crl.pem -noout -text
~~~

After ensuring the CRL is properly signed by the test CA and still within validity:

~~~bash
openssl verify \
  -CAfile pki/root-ca.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  -CRLfile pki/issuing-ca.crl.pem \
  -crl_check \
  pki/client-revoked.pem
~~~

`-crl_check` requires a CRL for the end-entity. `-crl_check_all` additionally checks certificates up the chain, requiring valid CRLs for those issuers. When the leaf serial is genuinely listed in a valid CRL, the command must **fail** with `certificate revoked`. If the CRL is missing or expired, that is a missing-evidence failure, not confirmation that the certificate is good.

### 5.4. Querying OCSP from a Test Responder

~~~bash
openssl ocsp \
  -issuer pki/intermediate-ca.pem \
  -cert pki/client-valid.pem \
  -url http://ocsp.pki.example.test \
  -CAfile pki/root-ca.pem \
  -resp_text
~~~

Requires a running OCSP endpoint and valid CA/responder info; output depends on actual status. This command illustrates querying and reading responses, and does **not** replace configuring server-side revocation checking. Verify issuer, responder signature, `thisUpdate`, `nextUpdate`, and result per policy.

### 5.5. Testing Key, mTLS, and Hostname over Real HTTPS

~~~bash
curl --cacert pki/server-root.pem \
  --resolve api.example.test:8443:127.0.0.1 \
  --cert pki/client-valid.pem \
  --key pki/client-valid.key \
  https://api.example.test:8443/api/private/ping
~~~

- `--cacert` lets curl verify the **server** certificate using the selected CA.
- `--resolve` preserves hostname `api.example.test` for TLS hostname verification while connecting to the lab IP.
- `--cert` and `--key` enable the client to participate in mTLS; the private key is not sent to the server.
- The **server certificate SAN must contain `api.example.test`** and the client chain must be valid. If needed, the `--cert` file can bundle leaf plus intermediate.

Never use `curl -k` in trust tests because that flag bypasses server certificate verification. If the Spring program is not running or certificates do not exist, the command cannot yield the expected HTTP result.

## 6. PKIX Testing in Java: Scope and Limitations

Key APIs:

- `CertificateFactory` reads X.509 from files and creates a `CertPath` in leaf → intermediate order.
- `TrustAnchor` represents a trusted root/CA.
- `PKIXParameters` holds trust anchors, cert stores, policies, validation timestamp, and revocation toggle.
- `CertPathValidator.getInstance("PKIX")` validates the constructed path.
- `PKIXRevocationChecker` adds OCSP/CRL rules when configured and supported.

**Illustrative code snippet placed inside a method**, assuming variables `leaf`, `intermediate`, `root` of type `X509Certificate`:

~~~java
CertificateFactory factory = CertificateFactory.getInstance("X.509");

// CertPath from leaf to intermediate; trust anchor sits outside the path.
CertPath path = factory.generateCertPath(List.of(leaf, intermediate));

TrustAnchor rootAnchor = new TrustAnchor(root, null);
PKIXParameters params = new PKIXParameters(Set.of(rootAnchor));

params.setRevocationEnabled(false); // Chain demo only, CRL/OCSP NOT checked yet.
CertPathValidator.getInstance("PKIX").validate(path, params);
~~~

Imports belong to `java.security.cert` and `java.util`; this is a snippet requiring certificates/variables passed from another program, **not** a standalone runnable file. `setRevocationEnabled(false)` is only for isolating path validation in tests; never treat it as a suitable production configuration.

When enabling revocation checking in a fully configured validator:

~~~java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

// Do not enable SOFT_FAIL in this example.
checker.setOptions(Set.of(PKIXRevocationChecker.Option.NO_FALLBACK));

PKIXParameters params = new PKIXParameters(trustAnchors);
params.setRevocationEnabled(true);
params.addCertPathChecker(checker);

// certPath and trustAnchors must be prepared from trusted sources.
// Configure responder / CRL / CertStore additionally per actual PKI.
validator.validate(certPath, params);
~~~

`NO_FALLBACK` controls the checker's OCSP/CRL fallback behavior; it does not fabricate valid revocation data. If tests require offline CRLs, supply a `CertStore` containing properly signed, unexpired CRLs; if using OCSP, verify the responder is configured and reachable. Running a `CertPathValidator` manually inside application code **does not automatically enable** that configuration in the active TLS trust manager.

## 7. Spring Boot + Spring Security: Boundaries of Responsibility

### 7.1. Two Verification Layers of mTLS

~~~text
Client certificate + private key
              │ TLS handshake
              ▼
Embedded Tomcat / Java JSSE (or gateway)
   ├── verifies chain, validity, trust anchor, purpose
   ├── revocation if configured and supported
   └── failure → TLS error, no HTTP request yet
              │ success
              ▼
Spring Security X509AuthenticationFilter
   ├── reads client certificate supplied by container
   ├── extracts principal
   ├── loads UserDetails and GrantedAuthority
   └── authorization → HTTP allow or deny
~~~

`http.x509(...)` does **not** replace the trust manager at the TLS layer. If a certificate is expired or its CA is untrusted and TLS blocks it, Spring cannot “rescue” authentication with a `UserDetailsService`. If TLS succeeds yet the user lacks permissions, the error happens **after TLS**, typically HTTP 403.

### 7.2. Dependencies and SSL Configuration in Spring Boot 3.x

In `build.gradle` of a servlet application with the Spring Boot plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

In `src/main/resources/application.properties`:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=${TLS_SERVER_KEYSTORE}
server.ssl.key-store-password=${TLS_SERVER_KEYSTORE_PASSWORD}
server.ssl.key-store-type=PKCS12

server.ssl.trust-store=${TLS_CLIENT_CA_TRUSTSTORE}
server.ssl.trust-store-password=${TLS_CLIENT_CA_TRUSTSTORE_PASSWORD}
server.ssl.trust-store-type=PKCS12

server.ssl.client-auth=need
~~~

- **Server keystore** holds the server private key and server certificate chain.
- **Client CA truststore** holds the CAs that the server permits to issue client certificates. Never put all public CAs into the truststore just to make tests pass.
- `server.ssl.client-auth=need` requires a client certificate right at the TLS handshake; `want` only requests one if the client has a certificate.
- Environment variable/secret values must point to valid keystore/truststore resources with read permissions and valid passwords. The example cannot start until PKI assets are prepared.
- This configuration requests client certs and sets CA trust; it **does not prove CRL/OCSP is enabled**.

### 7.3. Example Mapping X.509 to Application Permissions

File `src/main/java/example/mtls/MtlsApplication.java`:

~~~java
package example.mtls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MtlsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MtlsApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class MtlsSecurityConfig {

    @Bean
    UserDetailsService certificateUsers() {
        // Demo data; production must use a repository and stable identifiers.
        return username -> {
            if (!"client-linh".equals(username)) {
                throw new UsernameNotFoundException("Unknown application client");
            }
            return User.withUsername(username)
                    .password("{noop}not-used")
                    .authorities("API_READ")
                    .build();
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService certificateUsers)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/private/**").hasAuthority("API_READ")
                .anyRequest().authenticated());

        http.x509(x509 -> x509
                .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
                .userDetailsService(certificateUsers));

        http.formLogin(AbstractHttpConfigurer::disable);
        http.httpBasic(AbstractHttpConfigurer::disable);
        return http.build();
    }
}

@RestController
class PrivateController {
    @GetMapping("/api/private/ping")
    String ping() {
        return "ok";
    }
}
~~~

Here:

1. Tomcat/JSSE accepts or rejects the client certificate first according to TLS config.
2. Spring Security extracts the principal from Subject DN, e.g., `CN=client-linh` becomes `client-linh`.
3. `UserDetailsService` loads the `API_READ` authority. `password("{noop}not-used")` is only a structural value in `UserDetails`; this password is not used to authenticate the certificate.
4. The endpoint requires `API_READ`, so a client with a valid certificate whose internal account lacks permission is still denied.
5. CN regex is only suitable for **illustration**: CN may be non-unique or change easily. In production, map issuer + durable identifier (such as policy-governed Subject Alternative Name), avoiding duplicate CNs or unmanaged self-declared names.

In a project with valid TLS and fixtures, run:

~~~bash
./gradlew bootRun
~~~

Then use `curl` from Section 5.5. If server certificate, client certificate, private key, chain, and user mapping are all valid, the expected output from the endpoint is:

~~~text
ok
~~~

If TLS fails, there may be **no HTTP response**; do not claim all mTLS errors return HTTP 401/403.

### 7.4. When mTLS Terminates at a Reverse Proxy/Gateway

If a gateway validates the certificate and forwards an HTTP request to Spring Boot, the backend usually **does not directly see** the client certificate on the servlet request. A header like `X-Client-Cert`/`X-Verified-User` can only be trusted if the gateway guarantees:

- The backend does not receive direct traffic from the internet/bypassing the gateway.
- The gateway strips client-sent identity headers and recreates them from the verified session/certificate.
- The gateway → backend connection is protected per threat model (mTLS or restricted-access network).
- Mapping of identity, issuer, tenant, and permissions prevents privilege escalation via header strings.

In this model, the **gateway** is where expiry, trust chain, and revocation policies for client certificates must live. `http.x509(...)` on the backend cannot check revocation of a certificate that the gateway already terminated.

## 8. Actually Enabling Revocation Checking in Java/TLS

A Java PKIX snippet or Spring Security property **does not prove** the Java TLS stack has CRL/OCSP checking enabled. You must know where TLS termination happens and which runtime/provider/trust manager is in use.

For some SunJSSE/SunPKIX systems, system properties exist:

~~~text
-Dcom.sun.net.ssl.checkRevocation=true
-Dcom.sun.security.enableCRLDP=true
~~~

And the Java security property enabling OCSP:

~~~java
java.security.Security.setProperty("ocsp.enable", "true");
~~~

Security properties must be set before the SSL context/trust manager is initialized (or inside the JVM's `java.security` file). **Do not confuse** the `ocsp.enable` Java security property with an arbitrary `-D` Java system property. The effectiveness of each setting must be verified against your actual Java version, PKIX provider, Tomcat, or gateway.

A system can use `PKIXRevocationChecker`/`PKIXParameters.setRevocationEnabled(true)`, or a proper custom JSSE trust manager. However, a `CertPathValidator` snippet run inside a unit test **does not automatically apply** to Tomcat's TLS trust manager. Production configuration is only verified when tests show an **unexpired revoked certificate** is properly rejected at the TLS layer and timeouts/outages follow the chosen policy.

In addition:

- If using CRLs, you must have the issuer's valid CRL with a valid signature and freshness meeting policy.
- If using OCSP, verify responder identity, response timestamp, signature, and `good/revoked/unknown`.
- If enabling hard-fail, configure sensible timeouts/HA for responders to avoid halting all logins during PKI outages.
- If permitting soft-fail, conduct risk assessment and monitor failed checks; a valid `revoked` status must still be rejected.
- A certificate may be revoked **after a TLS connection is already established**. Existing open connections/sessions do not immediately close upon a CRL update; establish connection, session, and application account revocation lifecycle policies.

## 9. Complete Testing Matrix

Create a fixture set **with a test CA** and test each condition independently. When testing revocation, the certificate must be **unexpired, with a valid chain and proper EKU**; otherwise, an expiration error can mask the revocation error and lead to false conclusions.

| Case | Setup | Expected Result |
| --- | --- | --- |
| 1. All conditions valid | Trusted root, complete chain, unexpired leaf, valid EKU, status good, user has `API_READ` | TLS succeeds, endpoint returns HTTP 200 |
| 2. No client certificate sent | `server.ssl.client-auth=need`, request without `--cert` | TLS handshake rejected |
| 3. Expired leaf | `notAfter` in the past | Rejected at TLS/path; `checkValidity` reports expired |
| 4. Not-yet-valid leaf | `notBefore` in the future | Rejected at TLS/path |
| 5. Expired intermediate | Valid leaf, expired intermediate | PKIX path validation fails |
| 6. Untrusted root | Use cert from a CA absent from truststore | Handshake fails due to missing trust path |
| 7. Missing intermediate | Incomplete chain sent and validator lacks issuer | Path building fails |
| 8. Intermediate lacks signing authority | Invalid Basic Constraints/Key Usage/pathLen | Path validation fails |
| 9. Wrong EKU | Leaf only has serverAuth instead of clientAuth | Must be rejected by purpose-enforcing TLS validator |
| 10. Wrong client private key | `--cert` and `--key` do not form a pair | Handshake/credential setup fails |
| 11. Revoked leaf | Valid CRL/OCSP marks serial revoked | TLS/path rejects when revocation checking is enabled |
| 12. CRL/OCSP unreachable | Block access to test responder | Reject or continue strictly per hard/soft-fail policy |
| 13. Stale revocation response | `nextUpdate` has passed | Do not treat as good evidence |
| 14. Wrong server hostname | Client calls host not in server SAN | Client rejects TLS server certificate |
| 15. Unmapped user | Valid client cert, but no user in app | TLS succeeds, Spring Security rejects |
| 16. User lacks authority | Valid client cert, but lacks `API_READ` | TLS succeeds, HTTP 403 |
| 17. Bypassing gateway | Client sends auth headers directly to backend | Must be blocked by trust boundary |
| 18. CA rotation | New CA distributed, old CA removed on schedule | Neither trust out-of-scope CAs accidentally nor break connections from unsynced truststores |

### Inspecting Errors at the Right Layer

| Symptom | Check First |
| --- | --- |
| `certificate has expired`, `not yet valid` | `notBefore/notAfter` of leaf and intermediate, UTC, and NTP |
| `unable to get local issuer certificate` | Intermediate, trust anchor, chain sent over TLS |
| `self-signed certificate in certificate chain` | Whether the root is trusted by the **right party's** truststore |
| `unsuitable certificate purpose` | EKU, Key Usage, Basic Constraints |
| `certificate revoked` | Valid CRL/OCSP, issuer/serial, whether revocation is enabled |
| `unable to get certificate CRL` | Valid unexpired CRL matching issuer, download path/CRL file |
| `PKIX path building failed` | Truststore and chain, issuer signatures, path constraints |
| TLS handshake fails with no HTTP | Certificate, private key, TLS/ciphers, truststore, revocation |
| HTTP 403 after successful TLS | Principal mapping, user repository, and `GrantedAuthority` |
| OpenSSL verify OK but JVM mTLS fails | Different trust anchors, algorithms/trust managers, provider versions, and policies |

Diagnostic JVM flags in test environments:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
~~~

Enable only when needed; logs can be large and contain details about certificates/principals. These flags **do not enable revocation checking**; they only help observe the validation process.

## 10. Real-World Pitfalls to Avoid

1. **Equating validity period with trust.** `checkValidity()` can succeed even when the CA is untrusted or the cert is revoked.
2. **Trusting Subject/Issuer as text.** Matching names do not prove signatures; PKIX path validation is required.
3. **Putting arbitrary roots into the truststore.** This expands the set of allowed issuers and shifts the trust boundary.
4. **Mistaking `-untrusted` for “bad CA”.** In OpenSSL, this option supplies intermediates to build chains, not where trust anchors are decided.
5. **Assuming CRL/OCSP runs automatically just because AIA/CRLDP URIs exist.** Must enable/configure and run end-to-end revoked tests.
6. **Treating OCSP `unknown` as `good`.** Undetermined status is a distinct case requiring its own policy.
7. **Using `curl -k` to test HTTPS.** Skipping server certificate verification hides hostname/trust errors.
8. **Verifying files without testing mTLS.** File verification does not prove the client uses the right private key, Spring maps the right principal, or permissions are enforced.
9. **Confusing server-side OCSP stapling with client certificate revocation checking.** The right party must perform validation.
10. **Concluding 403 means an expired certificate.** With `client-auth=need`, expiration errors are normally blocked before HTTP.
11. **Ignoring existing TLS connections during revocation.** New revocations do not automatically close every old session connection.
12. **Trusting client-sent certificate headers.** Behind a proxy, trust identity only across a protected and verified boundary.

## 11. Operating the Certificate Lifecycle

A stable mTLS operations program should include:

- **Expiration monitoring and alerting** for leaves, intermediates, and critical CAs; set alerts ahead of thresholds (e.g., 30/14/7 days) aligned with SLAs.
- **Pre-expiration renewal and key rotation**; after replacing, verify SAN, EKU, private key, chain, and the live authentication flow.
- **Monitoring revocation infrastructure:** OCSP/CRL availability, CRL freshness, response errors, hard-fail rates, secure logs.
- **Private key compromise playbook:** revoke, reissue, refresh trust/policies, block accounts or sessions when needed; do not wait for `notAfter`.
- **CA rotation plan:** controlled truststore overlap period, rollout across nodes, verifying clients/servers before removing the old CA.
- **Cache/connection/session policy:** when app permissions or certs are revoked, define TTLs, enforcement timelines, and invalidation methods.
- **Periodic testing:** run good, expired, revoked, unknown-issuer, and responder-outage fixtures in production-like environments.

## 12. Self-Check Questions

1. Why can an unexpired certificate with a valid signature still be rejected?
2. How does a `TrustAnchor` differ from an `intermediate CA`? Why shouldn't every CA sent over TLS be trusted automatically?
3. Why does `checkValidity()` not prove a certificate is authorized to authenticate?
4. When a CRL contains the serial of an unexpired certificate, what must the validator do?
5. Is OCSP `unknown` equivalent to `good`? How does a hard-fail policy behave when a responder times out?
6. What is the difference between `-CAfile` and `-untrusted` in `openssl verify`?
7. Distinguish an mTLS handshake error due to expiry from HTTP 403 due to missing `API_READ`.
8. Which two authentication layers do `server.ssl.client-auth=need` and `http.x509(...)` belong to?
9. Why must revocation tests use an unexpired certificate and a valid chain?
10. If a gateway terminates TLS client certificates, which component is responsible for checking CRL/OCSP?

**Suggested answers:** (1) untrusted root, wrong purpose/identity, revoked, or broken chain; (2) trust anchors are configured by the verifier while intermediates are only signing links; (3) the method checks timestamps only; (4) reject if revocation policy applies; (5) no, hard-fail rejects when evidence is insufficient; (6) trusted CA vs. intermediates provided for chain building; (7) pre-HTTP vs. HTTP request reached app lacking permissions; (8) TLS validation vs. principal/authority mapping; (9) to avoid masking the revocation failure reason; (10) the gateway, while the application enforces identity/authorization behind the gateway.

## 13. Acceptance Checklist

- [ ] Tested valid, expired, not-yet-valid, revoked, unknown issuer, missing intermediate, and wrong EKU.
- [ ] Verified the entire chain up to the intended root in the truststore without indiscriminately broadening CAs.
- [ ] Verified UTC/NTP time and expiry for both leaf and intermediate.
- [ ] Verified revocation checking is **genuinely enabled** at TLS termination via end-to-end revoked tests.
- [ ] Defined hard/soft-fail policy and tested responder outages, stale/unknown responses, and CRL/OCSP signatures.
- [ ] Client checks server CA + hostname; server checks client CA + purpose + principal.
- [ ] Application permissions are loaded after mTLS, and HTTP 403 is distinguished from TLS errors.
- [ ] Truststores/keystores, private keys, and secrets are managed under least-privilege principles.
- [ ] Renewal schedules, expiry alerts, CA rotation plans, and emergency revocation procedures are in place.
- [ ] Any reverse proxy protects verified identity and never accepts forged headers from clients.

## 14. References

- [Spring Security 6.5 — X.509 Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html)
- [Spring Security — X509Configurer API](https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/config/annotation/web/configurers/X509Configurer.html)
- [Spring Boot 3.3 — SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Oracle Java 21 — PKIXRevocationChecker.Option](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXRevocationChecker.Option.html)
- [Oracle — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [OpenSSL — verification options](https://docs.openssl.org/3.0/man1/openssl-verification-options/)
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 6960 — Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960)
