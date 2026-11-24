# Hostname and Server Certificate Verification

When an application sends email with **Spring Framework Mail**, simply enabling TLS is not enough to prove it is connecting to the **right SMTP server**. TLS can encrypt data, but the application must also verify that the certificate presented by the server is trustworthy and actually represents the SMTP hostname the application intends to connect to.

For example, the application is configured to send through `smtp.example.com`. If a proxy, altered DNS, or spoofed server returns a valid certificate for `mail.attacker.example`, the connection must not accept that certificate merely because it is signed by a trusted CA. An additional **hostname verification** step is needed. Conversely, a certificate bearing the name `smtp.example.com` signed by an untrusted CA is not secure enough either.

With Jakarta Mail used by Spring Mail, a critical property is `mail.smtp.ssl.checkserveridentity=true`. Combining this property with a proper truststore/PKI setup, accurate STARTTLS or implicit TLS configuration, and operational checks helps the application prevent endpoint spoofing, protect SMTP credentials, and avoid sending email content over an unverified channel.

This lesson covers the trust model, rules for matching hostnames against Subject Alternative Name (SAN), the difference between certificate chains and server identity, Spring Boot/`JavaMailSenderImpl` configuration, inspection using OpenSSL and `keytool`, common error causes, troubleshooting workflows, and hands-on exercises.

## 1. Two questions that must be answered on a TLS connection

A properly verified TLS connection must answer two independent questions:

1. **Is the certificate trustworthy?** Can a valid certificate chain be built to a trust anchor trusted by the application/JVM, while also satisfying requirements on validity period, algorithms, intended usage, and verification policy?
2. **Does the certificate belong to the right server being connected to?** Does the hostname the application intends to access match an identifier asserted by the certificate, typically a `dNSName` in the `Subject Alternative Name` extension?

This can be visualized as:

```text
Spring application
      |
      v
Connect to smtp.example.com:587
      |
      v
STARTTLS negotiation
      |
      v
Server sends certificate chain
      |
      +--> Certificate chain trusted?
      |        |
      |        +-- No  -> reject TLS connection
      |
      +--> SAN matches smtp.example.com?
      |        |
      |        +-- No  -> reject TLS connection
      |
      v
Authenticated TLS channel
      |
      v
SMTP AUTH -> MAIL FROM -> RCPT TO -> DATA
```

Both conditions are required. Checking only the chain without checking the name can lead the application to trust a server holding a valid certificate for **a different hostname**. Matching only the name while ignoring signatures/CA can lead the application to trust an attacker's self-signed certificate.

### 1.1. Illustrating the scenarios

| Certificate | Chain trusted? | SAN matches connected host? | Expected outcome |
|---|---|---|---|
| Issued by a valid CA for `smtp.example.com` | Yes | Yes | Acceptable if all other checks pass. |
| Issued by a valid CA for `mail.other.example` | Yes | No | **Reject** due to server identity mismatch. |
| Self-signed cert listing `smtp.example.com` but untrusted | No | Yes | **Reject** because there is no valid trust path. |
| Cert with matching name but expired | Fails validity | Yes | **Reject**. |
| Cert with valid name and CA, but server fails to prove possession of private key | Handshake does not complete | Matches by name | **Reject**. |

These checks occur before the application exchanges sensitive SMTP information over the authenticated channel.

## 2. Risks of skipping hostname and certificate verification

### 2.1. Server impersonation

An attacker or a misconfigured component can route the application to a different endpoint:

```text
Application
  |
  | smtp.example.com
  v
Redirected DNS / proxy / route
  |
  v
Wrong SMTP endpoint
  |
  +--> Presents certificate for another name
```

If the application only cares “is TLS present?” without verifying the exact hostname, it can establish an encrypted channel **with the wrong party**. Encrypting traffic to an impersonating server does not protect information from that server itself.

### 2.2. Exposing SMTP credentials

SMTP AUTH may use a password, app password, or token. If an untrusted endpoint is accepted, credentials may be handed over to an unauthorized party.

Therefore, **do not send credentials before mandatory TLS and server authentication succeed** for submission configurations requiring TLS.

### 2.3. Exposing email content and attachments

Messages may contain:
- verification codes;
- invoices;
- transaction details;
- customer data;
- file attachments;
- action links containing tokens.

If the receiving SMTP server is not the intended server, this information can be disclosed. “Encrypted with TLS” should not be considered sufficient assurance when you do not know who the server on the other end is.

### 2.4. STARTTLS downgrade

With STARTTLS, the client starts with an SMTP session before upgrading to TLS. If the network path or a proxy interferes so that the server does not advertise STARTTLS and the client continues sending in plaintext, data can be exposed.

Therefore, when the provider requires STARTTLS, configure:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

These two properties do not replace hostname verification; they ensure **TLS must be used**, while server identity authentication requires `mail.smtp.ssl.checkserveridentity=true` and a valid truststore.

## 3. Which hostname must be verified?

An application may encounter many names related to email:
- sender's domain such as `example.com`;
- recipient address such as `customer@recipient.example`;
- SMTP submission host such as `smtp.mail-provider.example`;
- internal DNS/CNAME server names;
- reverse DNS/PTR;
- MX record of the recipient's domain.

**When an application connects directly to an SMTP submission server, the hostname compared against the certificate is the hostname the client uses for the SMTP connection**, such as the value of `spring.mail.host`.

If the app configures:

```yaml
spring:
  mail:
    host: smtp.mail-provider.example
    port: 587
```

then the server certificate must prove an identity matching `smtp.mail-provider.example`, not the domain after the @ sign of the recipient, not the email Subject, and not necessarily the sender's domain.

### 3.1. Example with MX, SMTP relay, and sender domain

```text
From: billing@store.example
To: user@customer.example

Application sends via:
smtp.provider.example:587
```

On the hop from the application to the provider, TLS identity is verified against `smtp.provider.example`. The provider's forwarding of mail to the MX of `customer.example` is a separate hop managed by the MTA/provider under their transport policy.

Mechanisms such as MTA-STS or DANE/TLSA relate primarily to SMTP transport protection between MTAs. They **do not replace** the Spring Mail application verifying the hostname of its directly configured submission server.

### 3.2. Host aliases, CNAMEs, and load balancers

Suppose the application uses `smtp.internal.example`, a CNAME to `smtp.service.example`. If the actual hostname used to establish TLS and verify identity is `smtp.internal.example`, the certificate needs to match that name under hostname verification policy, even if both names resolve to the same IP address.

Do not assume a CNAME makes two hostnames equivalent for TLS verification. When needed, configure:
- the official hostname supported by the SMTP provider;
- a certificate SAN for the alias the organization actually uses;
- SNI/load balancer returning a certificate matching the name the client connects to;
- consistent DNS and TLS termination across nodes.

### 3.3. Connecting directly by IP

A certificate containing `DNS:smtp.example.com` is not automatically valid for connecting to `203.0.113.10`. If a client uses an IP as the identity, the certificate needs a matching IP identifier (typically an `iPAddress` SAN) per TLS stack rules.

In most applications, use an official hostname rather than hardcoding an IP. IPs can change after failover, causing incorrect SNI or breaking certificate hostname checks.

## 4. Subject Alternative Name (SAN) and name matching rules

Modern X.509 certificates typically contain the **Subject Alternative Name** extension. For a DNS hostname, the client checks the `dNSName` entries in the SAN.

Example:

```text
Subject: CN=mail.example.com
X509v3 Subject Alternative Name:
    DNS:smtp.example.com,
    DNS:mail.example.com
```

In this example, the certificate's name can match `smtp.example.com` or `mail.example.com` provided the chain, validity period, and other checks pass.

### 4.1. Common Name is not the preferred choice

Older certificates often placed the hostname in the `Subject CN` field. Modern systems prioritize SAN; fallback behavior to CN when SAN is absent can vary by library version, standards rules, and infrastructure policy.

To avoid incompatibility:
- issue certificates with proper DNS/IP SANs;
- do not rely solely on CN;
- test on the exact Java runtime/Jakarta Mail implementation the application uses.

### 4.2. Wildcards do not match every level

A certificate with:

```text
DNS:*.example.com
```

may match `smtp.example.com` within the wildcard rules enforced by the TLS stack. Do not assume it matches:
- `example.com` (no subdomain label);
- `a.b.example.com` (two subdomain labels);
- all internationalized or IDN variants;
- hosts in another domain such as `smtp.example.net`.

Verify precisely with Java's hostname verification and limit broad wildcards when unnecessary.

### 4.3. DNS is not proof of certificate ownership

An A/AAAA/CNAME record pointing to a server does not prove the server's certificate is valid. DNS can be misconfigured or altered, whereas certificate identity still needs to be checked independently against the hostname the client intends to access.

### 4.4. Server Name Indication (SNI)

With one IP serving multiple hostnames, the TLS server may use **SNI** from the ClientHello to select the right certificate.

If the client fails to send the appropriate SNI, or a proxy/load balancer serves a default certificate for another hostname, the application may hit a hostname mismatch even when the endpoint appears operational.

When diagnosing with OpenSSL, pass the hostname explicitly via `-servername`. With Java, inspect actual behavior in JSSE debug and endpoint configuration; never alter your truststore to work around a server returning the wrong certificate due to SNI.

## 5. Certificate chain: trust is a separate step from name matching

A certificate chain typically looks like:

```text
Trusted Root CA / trust anchor
           |
           v
Intermediate CA
           |
           v
Server certificate
  SAN: DNS:smtp.example.com
```

To trust a server certificate, the TLS client must verify:
- the chain leads to a trusted trust anchor;
- certificate signatures and constraints are valid;
- the certificate is within its validity period;
- key usage is appropriate for TLS server authentication;
- algorithms/key strengths satisfy JDK policies;
- additional extended conditions depending on verification configuration.

**A certificate with a matching SAN that cannot build a trusted chain must still be rejected.** Conversely, a valid certificate chain for a different hostname must also be rejected.

### 5.1. Root CA and intermediate CA

The Root CA is typically a trust anchor located in the JVM's truststore or an approved custom truststore. The server needs to send the leaf and appropriate intermediate certificates so the client can build the chain. Not every server sends the root certificate; that is not necessarily an error.

If the server omits an intermediate, Java may report:

```text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
Caused by:
  sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
```

Preferred resolution steps:
1. Verify what chain the server actually returns.
2. Fix server configuration to serve the required intermediate(s).
3. Inspect the JVM's actual truststore.
4. Confirm the CA/trust anchor aligns with organizational policy.

Do not import every certificate seen on the network into the truststore just to silence errors.

### 5.2. Certificate validity period

The `notBefore` and `notAfter` timestamps determine validity. Skewed container/VM clocks, an expired leaf certificate, or an intermediate issue can cause failures.

Check:
- the actual clock on the machine running the JVM;
- NTP synchronization;
- expiry of both leaf and intermediate certificates;
- renewal and chain deployment procedures.

Do not fake the system clock or skip expiration checks just to let the system connect.

### 5.3. Key usage and Extended Key Usage

A certificate used for an SMTP TLS server must be suitable for TLS server authentication under the standards and policies Java enforces. A certificate designed solely for client authentication or another purpose may be rejected.

Do not infer a certificate is valid purely from its subject/issuer. Extensions such as `KeyUsage`, `ExtendedKeyUsage`, `BasicConstraints`, and trust manager policies are also part of verification.

### 5.4. Certificate revocation checking

OCSP/CRL verification and additional constraints **depend on policy, configuration, and TLS implementation**. Do not assume Jakarta Mail/JVM always checks revocation for every connection by default.

If your organization requires revocation checking, design and test the corresponding PKIX/JSSE configuration, including behavior when OCSP/CRL responders are unreachable. Define a clear policy; do not treat `checkserveridentity=true` as a revocation mechanism.

## 6. JavaMailSender, Jakarta Mail, and JSSE

In Spring Framework Mail, sending MIME messages typically goes through `JavaMailSender` or `JavaMailSenderImpl`. Underneath, Jakarta Mail implements the SMTP transport and uses Java/JSSE TLS mechanisms.

Distinguish between:

| Component | Role |
|---|---|
| `JavaMailSender` | Spring-level mail sending API. |
| `JavaMailSenderImpl` | Sender implementation accepting host/port/JavaMail properties. |
| Jakarta Mail SMTP Transport | SMTP connection, EHLO, STARTTLS, AUTH, DATA. |
| Java JSSE | TLS handshake, certificates, trust manager, protocol/cipher. |
| Truststore | Set of trust anchors accepted by the JVM/organization. |
| Hostname verification | Checks whether the server certificate represents the target hostname. |

### 6.1. Explicitly enabling hostname verification

Critical property:

```properties
mail.smtp.ssl.checkserveridentity=true
```

Jakarta Mail's SMTP transport supports server identity checks through this property; do not rely on defaults of a specific library version or socket creation path. Enable it explicitly and test when upgrading the JDK/Jakarta Mail.

Although the property name contains `ssl`, it applies to identity verification of the TLS connection established by the SMTP transport, including TLS after STARTTLS in the corresponding configuration.

### 6.2. Hostname verification is distinct from the truststore

`mail.smtp.ssl.checkserveridentity=true` does not add CAs to the truststore and does not make an untrusted chain valid.

Conversely, Java trusting a CA does not prove the certificate's SAN matches the hostname. Therefore, **both trust path validation and hostname validation** are needed.

### 6.3. Do not use trust-all

Configurations to avoid in production:

```properties
mail.smtp.ssl.trust=*
```

and custom `TrustManager` implementations that accept every certificate.

This “let everything pass” approach can mask spoofed servers, broken chains, or unapproved CAs. Even if hostname verification remains on, bypassing chain validation breaks half of the trust model.

Instead of trust-all:
- fix the server certificate/chain;
- use the correct hostname;
- use a verified internal CA distributed under control;
- configure an appropriate truststore;
- safely update the JDK/trust anchors.

## 7. STARTTLS and implicit TLS: when does verification happen?

Both modes require certificate validation and hostname verification. The difference is **when TLS begins**.

### 7.1. STARTTLS, typically on port 587

```text
Application                      SMTP server :587
    |---------- TCP ----------------->|
    |<--------- 220 greeting ---------|
    |---------- EHLO ---------------->|
    |<--------- 250-STARTTLS ---------|
    |---------- STARTTLS ----------->|
    |<--------- 220 Ready -----------|
    |=========== TLS handshake ======|
    |       chain + hostname check   |
    |---------- EHLO (TLS) --------->|
    |---------- AUTH --------------->|
    |---------- MAIL FROM ... ------>|
```

For SMTP submission requiring TLS, configure:
- `mail.smtp.starttls.enable=true`;
- `mail.smtp.starttls.required=true`;
- `mail.smtp.ssl.checkserveridentity=true`.

Enabling only `enable` without enforcing `required` can allow the session to proceed unencrypted when the server does not support STARTTLS, depending on SMTP transport behavior. That is inappropriate when sending credentials and sensitive data to a provider requiring TLS.

### 7.2. Implicit TLS, typically on port 465

```text
Application                      SMTP server :465
    |---------- TCP ----------------->|
    |=========== TLS handshake ======|
    |       chain + hostname check   |
    |<--------- 220 greeting (TLS) ---|
    |---------- EHLO (TLS) --------->|
    |---------- AUTH --------------->|
    |---------- MAIL FROM ... ------>|
```

For implicit TLS, typically use:
- `mail.smtp.ssl.enable=true`;
- `mail.smtp.ssl.checkserveridentity=true`.

There is no need for STARTTLS in this mode. If modes/ports are mismatched, the client may report a handshake failure, `wrong version number`, or `Unsupported or unrecognized SSL message`. That can be a transport configuration error rather than a certificate problem.

### 7.3. Port 25 is not the default for application submission

Port 25 commonly appears in MTA-to-MTA relaying or internal relays. Many ISPs/clouds block outbound port 25. Do not assume port 25 behaves like 587 or 465; use it only when confirmed by provider/infrastructure configuration with an appropriate TLS policy.

## 8. Spring Boot configuration: STARTTLS with server identity check

Example `application.yml` for SMTP submission over port 587:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Key points:
- `spring.mail.host` is the **expected hostname**, which must be verified against SAN.
- `starttls.enable` permits upgrading from SMTP to TLS.
- `starttls.required` mandates that TLS succeed.
- `ssl.checkserveridentity` enables server identity checking.
- Truststore/JSSE must still verify the certificate chain.
- Timeouts are in milliseconds per the SMTP transport; pick values suited to your infrastructure.

Do not enable `mail.smtp.ssl.enable=true` for port 587 if the SMTP provider uses STARTTLS on that port.

### 8.1. Selecting SMTP hosts from trusted configuration

Never accept an arbitrary SMTP hostname from user input and pass it to `JavaMailSender` to send mail. A client-chosen host can turn mail sending into **SSRF or credential exfiltration**.

For multi-tenant applications supporting multiple SMTP providers:
- manage admin-validated connector profiles;
- restrict host/port by policy;
- verify and store configurations separately per tenant;
- control DNS/IP/egress if dynamic connections exist;
- never let one tenant read another tenant's secrets/truststore;
- always keep hostname verification enabled for every endpoint.

## 9. Spring Boot configuration: implicit TLS with hostname verification

Example for port 465:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Here TLS starts immediately when the socket connects to the server. Do not use `starttls.required` in place of `ssl.enable`.

### 9.1. Do not conflate TLS mode with hostname verification

Summary table:

| Setting | STARTTLS 587 | Implicit TLS 465 |
|---|---|---|
| `mail.smtp.starttls.enable` | `true` | Usually not needed |
| `mail.smtp.starttls.required` | `true` when TLS is required | Usually not needed |
| `mail.smtp.ssl.enable` | Do not enable for STARTTLS-only endpoints | `true` |
| `mail.smtp.ssl.checkserveridentity` | `true` | `true` |
| Chain/truststore check | Mandatory | Mandatory |
| Credentials after verified TLS | Mandatory per policy | Mandatory per policy |

Actual ports must follow the SMTP provider's documentation, not just common conventions.

## 10. Configuring JavaMailSenderImpl without Spring Boot auto-configuration

In a Spring Framework application configuring the sender manually:

```java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpMailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

The example uses STARTTLS on port 587. If the SMTP provider requires implicit TLS on port 465, adjust configuration per the provider, enable `mail.smtp.ssl.enable=true`, and keep `checkserveridentity=true`.

Never hardcode passwords. In real deployments, supply credentials from a secret manager or protected environment configuration with rotation. Never log environment variables, app passwords, or access tokens.

### 10.1. Example sending after TLS configuration

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(
            String recipient,
            String subject,
            String plainText,
            String htmlText) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, htmlText);

        // Connection, handshake, and hostname verification
        // are performed by the SMTP transport/JSSE when sending.
        mailSender.send(message);
    }
}
```

`MimeMessageHelper` is not responsible for checking certificate SANs itself. That is the responsibility of the SMTP transport and TLS stack configured in `JavaMailSenderImpl`. Never implement a custom string-based CN comparison to replace the TLS hostname verifier.

## 11. JVM truststore and certificates issued by an internal CA

### 11.1. The effective truststore can differ across environments

Java typically includes a set of trust anchors depending on the JDK distribution and JSSE configuration. Factors that change outcomes include:
- different JDK vendors/versions;
- different `cacerts` files;
- a container image older than your laptop;
- JVM startup flags pointing to a custom truststore;
- an internal proxy replacing certificates with ones signed by a corporate CA;
- a certificate chain missing an intermediate;
- staging using a custom CA while production uses a different CA.

Common JSSE system properties:

```text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
```

The fact that a browser or `openssl` on a laptop trusts a certificate does not prove a Java process inside a container trusts it too. Check the **actual runtime** of the application.

### 11.2. Using an approved internal CA

If the SMTP relay is an internal server with a certificate signed by an enterprise CA, you can create a dedicated truststore according to organizational policy:

```bash
keytool -importcert \
  -alias approved-internal-smtp-ca \
  -file /secure/certs/approved-smtp-ca.pem \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

Inspect the truststore:

```bash
keytool -list -v \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

The command may prompt interactively for a password. Before importing, verify the CA certificate through a trusted channel with your PKI/infrastructure team. Never download an arbitrary certificate from a failing endpoint and immediately trust it.

When specifying the truststore is necessary:

```text
-Djavax.net.ssl.trustStore=/secure/mail-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Supply the password via securely managed secret/launch configuration if needed. Never place plaintext passwords in source code or broadly visible command lines.

**Note:** these JSSE system properties can affect other TLS connections in the same JVM. A custom truststore containing only an internal CA can inadvertently exclude public CAs needed by other HTTP clients. Evaluate the entire runtime; if isolated trust is needed, design TLS/`SSLContext` configuration within the limits of your stack and test thoroughly.

### 11.3. Do not unconditionally import leaf certificates

Temporarily importing a leaf certificate creates a dependency on a cert that will be replaced upon renewal. When the provider rotates the leaf/CA, the system will fail again.

Prefer:
- using an updated public CA/JDK truststore for public providers;
- using an organization-approved internal root/intermediate CA for private relays;
- planning for CA rollovers;
- avoiding leaf pinning unless you have proper pinning and rollout policies.

## 12. Diagnosing certificates and hostnames with OpenSSL

OpenSSL lets you observe the certificate an endpoint returns along the actual network path. Run it from the **same server, container, or egress network** as the application if possible, since a personal laptop may traverse different DNS/proxies.

### 12.1. Checking STARTTLS on port 587

```bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.com:587 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error \
  -showcerts
```

Options:
- `-starttls smtp`: speaks SMTP and requests a STARTTLS upgrade before verifying TLS.
- `-connect`: target host/port.
- `-servername`: sends SNI so the server selects the certificate.
- `-verify_hostname`: checks the hostname using OpenSSL's verification logic.
- `-verify_return_error`: does not merely print verification errors, but causes a failure return when verification fails.
- `-showcerts`: displays certificates sent by the server.

### 12.2. Checking implicit TLS on port 465

```bash
openssl s_client \
  -connect smtp.example.com:465 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error \
  -showcerts
```

Do not pass `-starttls smtp` when connecting to an implicit TLS endpoint expecting ClientHello from the start.

### 12.3. Reading key fields

Observe:
- Subject and Subject Alternative Name.
- Issuer.
- Certificate chain presented by the server.
- `notBefore` and `notAfter`.
- Negotiated TLS protocol/cipher.
- Verification result.
- Handshake errors before or after the certificate step.

If the tool returns `Verify return code: 0 (ok)`, that only confirms verification under **OpenSSL's** current truststore/policy. Java may still use a different set of trust anchors.

Never enter SMTP passwords or tokens into a debug session as a “quick test”. If AUTH testing is needed, use an organization-approved tool/process and protect the output.

### 12.4. Avoid testing the wrong name

If the app uses `smtp.internal.example` but an operator runs:

```bash
openssl s_client \
  -connect smtp.internal.example:587 \
  -starttls smtp \
  -servername public-mail.example \
  -verify_hostname public-mail.example
```

then the output may only prove the endpoint returns a valid cert for `public-mail.example`; it **does not prove the app configuration using `smtp.internal.example` is correct**. Ensure `-verify_hostname` and SNI reflect the actual hostname the app intends to verify, unless intentionally investigating a mismatch on a specific endpoint.

## 13. Verifying certificate chains with keytool and the Java runtime

### 13.1. Viewing the list of trust anchors

For example, if you have a dedicated truststore:

```bash
keytool -list -v \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

For the default JVM truststore, you can use `keytool` to list `cacerts` per the running JDK's documentation. Do not conclude a CA is “trusted” just because it appears in a `cacerts` file on a different machine.

Cross-check:
- the actual truststore file;
- the JDK running the application;
- the organization-approved CA/root fingerprint;
- the endpoint's issuer/chain;
- file read permissions.

### 13.2. Enabling JSSE debug when necessary

You can temporarily enable JVM flags:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
```

These flags let you observe:
- handshake and TLS version;
- certificate chain being evaluated;
- whether the trust manager accepts the issuer/trust anchor;
- where path validation fails;
- certificate identity or protocol/cipher mismatch scenarios.

JSSE logs can be very verbose and contain hostname/certificate metadata and connection details. Enable only in controlled environments, restrict log access, and disable after troubleshooting.

### 13.3. Distinguishing OpenSSL and Java debugging

| Tool | What can it verify? | Limitations |
|---|---|---|
| `openssl s_client` | Endpoint cert, SNI, protocol/cipher, verification per OpenSSL | Does not use Java's exact default truststore/policy. |
| `keytool` | Keystore/truststore/certificate contents | Does not prove the app's network path by itself. |
| `javax.net.debug` | Handshake and JSSE decisions in the Java runtime | Logs can be verbose; must be protected. |
| `JavaMailSenderImpl.testConnection()` | Real sender connection with network/TLS/AUTH per config | Does not send a message or prove delivery. |
| Provider SMTP logs | Which endpoint handled the request and what it replied | Depends on access permissions and retention. |

Combining multiple sources helps distinguish a Java truststore issue from a server presenting the wrong chain or SAN.

## 14. Common errors and how to classify them

When Spring `send(...)` fails, the outer exception may be `MailSendException`; inspect deeply nested causes such as `MessagingException`, `SSLHandshakeException`, or `CertificateException`.

| Error / symptom | Common likelihood | Remediation direction |
|---|---|---|
| `PKIX path building failed` | Cannot build trust chain to a JVM-trusted CA | Check intermediates, CA, truststore, proxy. |
| `unable to find valid certification path` | Missing or untrusted trust anchor | Verify chain and actual JVM truststore. |
| `No subject alternative DNS name matching ...` | SAN does not match hostname | Use right hostname or reissue cert with matching SAN. |
| `No name matching ... found` | Hostname verification failed | Check host, alias, CN/SAN per implementation. |
| `CertificateExpiredException` | Certificate expired | Renew and deploy proper chain, verify clock. |
| `CertificateNotYetValidException` | Certificate not valid yet or clock skewed | Check NTP and validity dates. |
| `Unsupported or unrecognized SSL message` | Confusing implicit TLS with plaintext SMTP | Check port and TLS mode. |
| `wrong version number` | Sending TLS to an endpoint not speaking TLS at that point | Check STARTTLS/implicit/proxy. |
| `handshake_failure` | No agreed protocol/cipher or cert policy | Check JSSE/server logs, mTLS, TLS versions. |
| `protocol_version` | One side does not support the TLS version | Update relay/JDK and policy. |
| `no cipher suites in common` | No overlapping cipher suites | Check JDK disabled algorithms and relay. |
| `Connection reset` or `EOFException` | Proxy/server closed connection; wrong mode; network issue | Check egress, SNI, server logs. |
| `STARTTLS is required but host does not support STARTTLS` | Server does not advertise STARTTLS | Verify right host/port, relay/gateway. |
| `530 Must issue STARTTLS first` | Client hasn't upgraded to TLS while server requires it | Enable the right STARTTLS mode. |
| `535 Authentication failed` | TLS likely succeeded, but AUTH failed | Check credentials, OAuth2/app password, account policy. |

This is a triage table, not an absolute classification ruleset. `handshake_failure` can have multiple causes and requires reading protocol context, logs, and exact failure timing.

### 14.1. Case: valid chain but wrong hostname

```text
Connected hostname: smtp.example.com

Certificate chain:
  Root CA: trusted
  Intermediate CA: trusted
  Leaf SAN: DNS:mail.other.example

Result: hostname mismatch
```

There is no need to import another CA. The chain is already trusted; the error is in **server identity**. Fix the app's hostname or the certificate SAN on the right relay.

### 14.2. Case: matching SAN but untrusted CA

```text
Connected hostname: smtp.example.com

Certificate:
  SAN: DNS:smtp.example.com
  Issuer: Internal Test CA

Java truststore:
  Internal Test CA not trusted

Result: PKIX path validation failed
```

Do not change the hostname because the hostname is already right. Verify whether Internal Test CA is approved, then configure the trust anchor or replace the server certificate with a trusted chain.

### 14.3. Case: both chain and SAN match, yet still fails

Other causes may include:
- expired/not-yet-valid certificate;
- weak algorithm rejected by the JDK;
- unsuitable KeyUsage/ExtendedKeyUsage;
- mTLS client certificate required;
- incompatible protocol/cipher;
- proxy/network reset;
- revoked certificate under configured policy;
- SNI/server farm where a node returns a different cert during actual tests.

**Do not assume SAN checking is the sole cause of every handshake failure.**

## 15. Security pitfalls from misconfiguration and how to prevent them

### 15.1. Disabling hostname verification just to “make it run”

If `mail.smtp.ssl.checkserveridentity=false` is configured, the application may accept a certificate that is valid but belongs to **another hostname**, depending on SMTP transport behavior. This weakens guarantees against server impersonation.

Never resolve an incident by disabling this property. Fix DNS/aliases/certificate SANs properly.

### 15.2. Trusting every certificate

Using `mail.smtp.ssl.trust=*` or a trust manager that accepts all certificates allows untrusted chains to pass verification. This is not a safe option for production.

Do not use trust-all to fix `PKIX path building failed`. Certificate sources must be verified through a trusted channel.

### 15.3. Omitting STARTTLS required

If the relay requires TLS and the client only sets `starttls.enable=true`, in some cases it may proceed with non-TLS SMTP when the capability is absent. This is a downgrade risk.

Set `required=true` to fail closed and never send credentials in plaintext.

### 15.4. Downgrading TLS protocols to bypass errors

Some legacy relays only support TLS 1.0/1.1 or weak ciphers. Do not relax `jdk.tls.disabledAlgorithms` or force weak protocols just to send email.

Prefer upgrading the relay/provider or using an organization-approved gateway configured with modern TLS and a replacement plan.

### 15.5. Certificate pinning without a rotation plan

Pinning a leaf certificate can tighten control in specialized environments, but easily causes outages when certs rotate, multiple nodes exist, or providers change CAs. If an organization applies pinning, it must have:
- backup pin/rollover mechanisms;
- distribution/revocation procedures;
- integration tests;
- incident response plans for certificate changes.

For typical SMTP submission, rely on a trusted CA truststore plus hostname verification rather than arbitrarily pinning a leaf certificate.

## 16. Certificates from reverse proxies and TLS interception

Some organizations use an SMTP gateway or proxy to control egress. The path may be:

```text
Spring application
       |
       v
SMTP proxy / TLS inspection gateway
       |
       v
Provider SMTP server
```

The TLS identity the app sees depends on whether the proxy terminates TLS or passes it through:
- If passthrough, the app expects the provider's cert and verifies the provider's hostname.
- If the proxy terminates TLS, the app may see the proxy's certificate, which must be issued and managed under internal policy with a SAN matching the name the app uses.
- If the proxy substitutes a cert signed by an internal CA not yet trusted by the JVM, PKIX errors can occur.
- If the proxy serves a default certificate not matching SNI, hostname mismatches can occur.

Do not import a cert “seen on the wire” without verifying with the infrastructure team. You need to know who manages TLS termination, which CA is authorized, and which hostname the app is supposed to trust.

### 16.1. When only some pods or nodes fail

One hostname may resolve to multiple IPs or backend relays. If one node serves an old cert or broken chain, errors will occur intermittently depending on the connection path.

Collect:
- timestamp and pod/node;
- SMTP host name, port, TLS mode;
- resolved DNS/IP (in logs with appropriate access control);
- certificate subject/SAN/issuer/fingerprint if useful for diagnosis;
- JSSE failure category.

Coordinate with the provider team to align certificates and chains uniformly across all nodes. Never disable verification just because failures are intermittent.

## 17. Practical verification with Spring Mail

### 17.1. testConnection()

`JavaMailSenderImpl` can test connectivity:

```java
JavaMailSenderImpl sender = ...;
sender.testConnection();
```

This method can detect TCP, TLS, or AUTH errors during the connect stage according to sender configuration. However, it **does not send a full email**, does not test MIME attachments, and does not guarantee delivery.

If using Spring Boot, a startup connection test property may be available in certain versions:

```yaml
spring:
  mail:
    test-connection: true
```

Consider carefully: during a temporary SMTP provider outage, mandatory startup checks can prevent the application from starting. Enable it only if that is the desired system behavior.

### 17.2. Integration tests with valid and invalid certificates

A useful test suite should cover three cases:
1. Certificate issued by a trusted test CA and SAN matches hostname: connect succeeds.
2. Certificate issued by a trusted test CA but SAN **does not match**: connect fails.
3. Certificate has matching SAN but signed by an **untrusted** CA: connect fails.

Notes:
- use a managed SMTP TLS test server in CI/staging;
- issue test certificates with appropriate SANs;
- keep the test truststore separate; never overwrite the production truststore;
- run with the right TLS mode (STARTTLS/implicit);
- do not merely mock `JavaMailSender`, because mocks do not execute the JSSE handshake.

Also test:
- expired certificates;
- missing intermediates;
- STARTTLS not advertised when `required=true`;
- wrong TLS mode;
- SNI returning a different certificate;
- multiple load-balanced endpoints;
- CA rollover.

### 17.3. Failure tests must not send credentials/body

With an untrusted cert or hostname mismatch, expect the connection not to proceed to AUTH/MAIL FROM/DATA. This is a security property that should be verified in integration tests.

Do not use an SMTP test server that accepts every certificate and assume production will be safe. In tests, you may use a self-created CA **that is intentionally trusted**; never use trust-all.

## 18. Hostname/certificate troubleshooting runbook

When encountering TLS/certificate errors in a Spring Mail application:

1. **Confirm the endpoint**: verify exact `spring.mail.host`, port, and TLS mode per provider docs.
2. **Confirm DNS/TCP**: check that the app actually reaches the right network path. TCP success does not imply TLS success.
3. **Inspect the certificate on the path**: use OpenSSL `s_client` with the right STARTTLS/implicit mode, `-servername`, and `-verify_hostname`.
4. **Match SAN against the host**: do not mistakenly check the sender domain, recipient domain, or another proxy hostname.
5. **Check the chain and validity**: leaf, intermediate, trust anchor, EKU, validity dates.
6. **Check the JVM truststore**: right JDK/container, trustStore path/type/permissions, approved CA.
7. **Enable limited JSSE debug** if the root cause remains unclear: obtain protocol/cipher/certificate validation details.
8. **Check proxy/SNI/load balancer**: see if any node serves a different cert or performs legitimate TLS interception.
9. **Fix at the source**: host/certificate/CA/chain/proxy/TLS mode; strictly never use trust-all or plaintext fallback.
10. **Run testConnection and integration tests** in permitted environments.
11. **Recover workers/backlog** with controlled retries; distinguish pre-send handshake failures from indeterminate SMTP outcomes after DATA.
12. **Update monitoring**: expiry, handshake errors, hostname mismatches, and truststore drift.

### 18.1. Useful logging without exposing data

Record:
- message key and attempt ID;
- SMTP host alias/port/TLS mode;
- exception class and root cause category;
- timestamp, service instance, JDK version;
- TLS handshake failure count metric.

Do not record:
- SMTP passwords, app passwords, OAuth tokens;
- AUTH exchanges;
- body content, attachments/Base64;
- reset/verification tokens in URLs;
- private keys or truststore passwords.

If enabling `mail.debug=true` or Java `javax.net.debug`, restrict access because debug logs can contain extensive metadata or sensitive details. Disable after investigation.

## 19. Special operational scenarios

### 19.1. Certificate rotation

Providers may rotate leaf or intermediate certificates. If the system uses an appropriate CA/truststore and the hostname stays the same, rotation can usually happen with minimal disruption.

Prepare by:
- monitoring expiry ahead of time;
- knowing the current CA and upcoming CA;
- testing the new chain from staging;
- distributing trust anchors on schedule if rollover is needed;
- verifying SAN still covers the host the app uses;
- having a safe rollback plan if a wrong cert is deployed.

Do not wait until a certificate expires and then disable verification to restore service.

### 19.2. JDK upgrades

New JDKs may update trust anchors or disable weak TLS algorithms. An older relay that previously connected may start failing after a JDK upgrade.

Before upgrading:
- check the SMTP provider's protocols/ciphers and certificate chain;
- run integration tests with the new image/JDK;
- verify custom truststores/CAs;
- upgrade the relay if it uses algorithms that are no longer secure.

Do not fix this by disabling JDK security defaults system-wide without proper assessment and approval.

### 19.3. Mail relay mTLS

In enterprise relays requiring **mutual TLS**, the server not only presents a certificate to the client, but also requires a client certificate.

Two distinct checks:
- **Application checks server**: chain + hostname of the SMTP relay.
- **Relay checks client**: the application's certificate and private key per relay policy.

Missing client certificate errors may show as `certificate_required` or `bad_certificate`, which does not mean the server's SAN is wrong. Configure the client keystore/key material per SMTP admin guidelines; never disable server verification to get past an mTLS error.

### 19.4. Revoking or replacing an internal CA

If an internal CA is revoked or no longer approved:
- update truststores following PKI procedures;
- replace certificates on affected relays;
- coordinate rollout timing;
- confirm fail-closed behavior;
- never leave old CAs active indefinitely just to avoid an outage.

### 19.5. Multiple SMTP profiles

In applications with distinct transactional and marketing senders, each profile must have:
- a confirmed hostname;
- an appropriate TLS mode;
- `checkserveridentity=true`;
- corresponding trust policy;
- separate secrets if needed;
- separate connection logging/metrics.

Do not treat the secure configuration of the first sender as proof that the second sender is also secure. If using per-tenant relays, validate and authorize configuration per tenant.

## 20. Design mistakes to avoid

| Bad practice | Why it is wrong | Replace with |
|---|---|---|
| Enabling TLS without checking hostname | May trust a server holding a cert for another host | `mail.smtp.ssl.checkserveridentity=true`. |
| Using `mail.smtp.ssl.trust=*` | Skips trust chain, increases MITM risk | Verified CA/truststore. |
| Disabling hostname check on SAN mismatch | Hides wrong endpoint/certificate | Fix host, DNS/SNI, or SAN. |
| Importing unverified certs from failing endpoints | May trust an attacker's certificate | Confirm fingerprint/CA via a trusted channel. |
| Connecting by IP when cert only has DNS SAN | IP does not necessarily match DNS SAN | Use official hostname or matching IP SAN. |
| Guessing certificate from sender/recipient domain | That is not the submission hostname | Check `spring.mail.host`. |
| Using 465 with STARTTLS-only config | Wrong timing for TLS start | Use implicit TLS on the right port. |
| Using 587 with implicit TLS on a STARTTLS endpoint | Protocol mismatch | Use STARTTLS + required. |
| Dropping `starttls.required` to fall back to plaintext | Downgrade and data exposure risk | Fail closed when TLS is required. |
| Treating OpenSSL verify OK as sufficient for Java | OpenSSL and JSSE have different truststores | Verify against actual JDK/truststore. |
| Pinning leaf certificates without rollover | Outage during rotation | Trust appropriate CA or plan pinning carefully. |
| Letting users enter arbitrary SMTP hosts | SSRF/credential exfiltration risk | Admin-managed profiles, allowlists, egress policies. |
| Using a mock mail sender to claim TLS security | Mocks perform no TLS handshake | Integration tests with real certs and hostnames. |
| Dumping full SMTP debug into public logs | Easily leaks hosts, recipients, tokens, secrets | Restricted debug, data filtering, disable after triage. |

## 21. Practice exercises

### Exercise 1 — Checking two independent conditions

Given three certificates:
- Cert A: trusted CA, SAN matches `smtp.example.com`.
- Cert B: trusted CA, SAN is only `mail.other.example`.
- Cert C: SAN matches `smtp.example.com`, but CA is untrusted.

Analyze which cert can be accepted once all other TLS conditions are also valid.

### Exercise 2 — Enabling hostname verification

Configure Spring Boot using STARTTLS on port 587 with `starttls.required=true` and `mail.smtp.ssl.checkserveridentity=true`. Explain the difference between the two properties.

### Exercise 3 — Implicit TLS

Migrate the port 587 configuration to port 465 implicit TLS per the provider. Identify which properties must be enabled, which are no longer needed, and why hostname verification stays unchanged.

### Exercise 4 — SAN and wildcards

A certificate has `DNS:*.example.com`. Identify names to test: `smtp.example.com`, `a.b.example.com`, `example.com`, and `smtp.example.net`. Do not assume wildcards match infinitely.

### Exercise 5 — Host aliases

The app uses `smtp.internal.example`, a CNAME to `relay.vendor.example`. The certificate only has SAN `relay.vendor.example`. Explain why a DNS alias is insufficient, then propose changing the hostname or issuing an appropriate SAN.

### Exercise 6 — OpenSSL and SNI

Run `openssl s_client` with the right `-servername` and `-verify_hostname` against an SMTP sandbox. Observe the result when changing to a hostname not in the SAN. Never enter SMTP credentials into the diagnostic session.

### Exercise 7 — Java truststore differs from OpenSSL

OpenSSL on your laptop verifies successfully, but Java in a container reports PKIX. List the factors to cross-check: JDK image, truststore flags, CA bundle, proxy, and certificate chain.

### Exercise 8 — Internal CA

Use an organization-approved test CA and import it into a test-only PKCS12 truststore. Demonstrate that a cert with matching SAN and trusted CA connects successfully, while a cert with the wrong SAN is still rejected.

### Exercise 9 — Testing hostname mismatch

Stand up an SMTP test server with a valid certificate for `smtp.test.local`, but have the client connect to `wrong.test.local`. Verify `JavaMailSenderImpl.testConnection()` fails when hostname verification is enabled.

### Exercise 10 — Certificate rotation

Write a runbook for rotating a leaf certificate, then rotating an intermediate/CA. State steps for preparing trust anchors, testing SANs, checking nodes, and rolling back without weakening TLS.

### Exercise 11 — TLS inspection proxy

An internal relay intercepts TLS and issues certificates using an Enterprise CA. State the steps to verify with the infrastructure team before trusting that CA; explain why importing arbitrary certs is unsafe.

### Exercise 12 — Incident recovery

After a hostname verification outage, many email jobs remain queued. Distinguish jobs that never passed the TLS handshake from jobs with indeterminate submission outcomes after DATA, then design bounded retries without uncontrolled duplicate sending.

## 22. Summary

**Hostname and server certificate verification** are foundational when securing SMTP submission with TLS in Spring Framework Mail. A connection is trustworthy only when **the certificate chain is valid per the JVM's truststore/policy** and **the server certificate genuinely represents the SMTP hostname the application intends to connect to**.

For safe deployment:
1. Use the official SMTP hostname and verify against `Subject Alternative Name`, not the sender or recipient domain.
2. Explicitly enable `mail.smtp.ssl.checkserveridentity=true`.
3. For STARTTLS, enable `starttls.enable=true` and `starttls.required=true` when the provider requires TLS; for implicit TLS, use `ssl.enable=true` on the right endpoint.
4. Keep PKIX path validation and truststores accurate; never use `ssl.trust=*` or a trust manager that accepts all certificates.
5. Inspect SNI, aliases, IPs, proxies, and certificate chains when mismatches happen.
6. Diagnose from the actual Java runtime and network path using OpenSSL, keytool, JSSE debug, and `testConnection()`.
7. Manage certificate expiry, CA rollovers, and JDK updates via integration tests and runbooks.

TLS encrypts the connection, while **hostname and certificate validation ensure that encrypted channel is established with the right trusted SMTP server**. Never trade away these two verification layers just to make mail sending temporarily succeed.
