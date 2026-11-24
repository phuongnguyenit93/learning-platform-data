# TLS, Certificate, and Handshake Errors

When sending emails using **Spring Framework Mail**, a call to `JavaMailSender.send(...)` can fail even when the SMTP host, username, and password all look correct. Messages such as `SSLHandshakeException`, `PKIX path building failed`, `No subject alternative DNS name matching`, `Unsupported or unrecognized SSL message`, or `STARTTLS is required but host does not support STARTTLS` usually relate to **how the TLS channel is established**, **certificate verification**, **protocol versions**, or **the connection path to the SMTP relay**.

This is not a group of errors you should fix by disabling certificate validation. TLS helps the application verify the SMTP server's identity and encrypt traffic over that connection. If mishandled, the application may send credentials and email content to an untrusted endpoint, accept forged certificates, or silently downgrade to an unencrypted connection.

This lesson explains the difference between **STARTTLS** and **implicit TLS**, how Jakarta Mail interacts with Java JSSE/truststores, common causes of handshake failures, a repeatable diagnostic workflow, safe Spring Boot configurations, and common testing scenarios.

## 1. Placing the Error Accurately in the Mail Sending Flow

When a Spring Boot application sends mail via SMTP, there are several stages before a recipient sees the email:

```text
Spring service
     |
     v
JavaMailSender / MimeMessage
     |
     v
DNS / TCP connection
     |
     v
SMTP greeting / EHLO
     |
     +------------------------------+
     | STARTTLS mode                | Implicit TLS mode
     | EHLO -> STARTTLS -> TLS      | TLS immediately upon TCP connect
     +------------------------------+
     |
     v
TLS certificate validation / handshake
     |
     v
SMTP AUTH (if required)
     |
     v
MAIL FROM -> RCPT TO -> DATA
     |
     v
SMTP server accepts submission
     |
     v
Provider delivery toward recipient
```

**Where do handshake errors happen?** If the SSL/TLS handshake fails, the secure channel is not ready, so the sending session stops before completing SMTP AUTH or DATA. Errors like "wrong password" or "nonexistent recipient address" belong to other steps and should not be conflated with certificate errors.

A successful `send(...)` call usually only indicates the SMTP server accepted the submission; it **does not prove the recipient received the email in their Inbox or opened it**. This lesson focuses on **transport security for the connection from the application to the SMTP relay/provider**, not end-to-end content security inside a mailbox.

### 1.1. Distinguishing Three Layers to Isolate Issues

| Layer | Example errors | What to inspect |
|---|---|---|
| **Network / TCP** | Connection refused, DNS failure, timeout | Host, port, firewall, proxy, DNS, route. |
| **TLS / certificate** | `SSLHandshakeException`, PKIX, hostname mismatch | STARTTLS/implicit TLS, certificate chain, truststore, SNI, protocol/cipher. |
| **SMTP / authentication** | `535 Authentication failed`, `550` recipient rejected | Username, app password/OAuth2, AUTH mechanism, relay policy, recipient. |

A Spring `MailSendException` may wrap a deeper exception. Find the **root cause** before choosing a remediation.

## 2. STARTTLS vs. Implicit TLS: Do Not Confuse Them

Two common ways to protect an SMTP submission connection are:

1. **STARTTLS**: TCP initially opens an unencrypted SMTP connection; the client sends EHLO and the `STARTTLS` command to upgrade to TLS before AUTH/sending content.
2. **Implicit TLS** (often called SMTPS): the TLS handshake begins immediately after TCP connect, before the SMTP greeting inside the encrypted channel.

### 2.1. Comparing Common Ports

| Port | Common usage | Main config | What to remember |
|---|---|---|---|
| **587** | Message submission with STARTTLS | `mail.smtp.starttls.enable=true` and usually `required=true` | Do not enable implicit TLS simultaneously if the server expects STARTTLS. |
| **465** | Message submission via implicit TLS | `mail.smtp.ssl.enable=true` | The connection starts with TLS immediately. |
| **25** | MTA-to-MTA transfer or internal relay per policy | Infrastructure-dependent | Not assumed open for application submission; many networks block port 25. |

Ports 587/465 are common conventions, **not substitutes for official SMTP provider configuration**. An internal system may use a different port. Pick the exact host, port, and TLS mode published by your SMTP provider.

### 2.2. How Does STARTTLS Work?

Illustrative flow:

```text
Client                         SMTP server :587
  |-------- TCP connect ------------>|
  |<------- 220 greeting ------------|
  |-------- EHLO app.example -------->|
  |<------- 250-STARTTLS ------------|
  |-------- STARTTLS ---------------->|
  |<------- 220 Ready to start TLS --|
  |=========== TLS handshake ========|
  |    certificate validation        |
  |-------- EHLO app.example ------->|  (inside TLS)
  |<------- 250-AUTH ... ------------|
  |-------- AUTH ... ---------------->|
  |-------- MAIL FROM ... ----------->|
  |-------- RCPT TO ... ------------->|
  |-------- DATA ... ---------------->|
  |<------- 250 queued --------------|
```

Before STARTTLS completes, never send username/password or sensitive content. To avoid sending plaintext when a relay lacks support or during downgrade attempts, set `mail.smtp.starttls.required=true` for providers required to support STARTTLS.

Setting only `starttls.enable=true` may allow continuing without TLS in some cases if the server does not advertise STARTTLS; `required=true` forces the connection to use STARTTLS or fail.

### 2.3. How Does Implicit TLS Work?

```text
Client                        SMTP server :465
  |-------- TCP connect ------------>|
  |=========== TLS handshake ========|
  |    certificate validation        |
  |<------- 220 greeting ------------|  (inside TLS)
  |-------- EHLO -------------------->|
  |-------- AUTH ... ---------------->|
  |-------- MAIL FROM ... ----------->|
  |-------- RCPT TO ... ------------->|
  |-------- DATA ... ---------------->|
```

If the client uses implicit TLS on a port expecting a plaintext SMTP greeting, or waits for a plaintext SMTP greeting on a port expecting TLS ClientHello, neither side understands the other. That can cause `Unsupported or unrecognized SSL message`, `wrong version number`, timeouts, or connection resets.

## 3. Proper Spring Boot Configuration for Each TLS Mode

Spring Boot can auto-configure `JavaMailSender` when the application includes the mail starter and appropriate SMTP properties. The examples below use SMTP with username/password authentication; some providers require OAuth2 or another AUTH mechanism.

### 3.1. Port 587: Required STARTTLS

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

Explanation:
- `auth=true`: uses SMTP AUTH if required by the provider.
- `starttls.enable=true`: requests upgrading the connection via STARTTLS when supported by the server.
- `starttls.required=true`: refuses to continue the session if STARTTLS is absent or fails.
- `ssl.checkserveridentity=true`: enforces hostname verification on the TLS certificate.
- Timeouts cap connect, read, and write wait times in milliseconds per Jakarta Mail properties.

Do not enable `mail.smtp.ssl.enable=true` in this port 587 example if the provider supports only STARTTLS on this port.

### 3.2. Port 465: Implicit TLS

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

`ssl.enable=true` makes Jakarta Mail's SMTP transport establish TLS immediately upon connect. There is no need to send a STARTTLS command on an implicit TLS port.

**Do not enable both modes simultaneously out of habit.** Confirm the mode supported by the provider, then configure that single TLS initiation mode properly.

### 3.3. Setting TLS Versions When Required by Infrastructure

In some systems, protocols must be restricted per policy:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          ssl:
            protocols: TLSv1.2 TLSv1.3
```

The `mail.smtp.ssl.protocols` property is a space-separated list of protocol names and depends on actual JDK/server support. Do not force `TLSv1.3` when the server/JVM lacks support, and do not downgrade to TLS 1.0/1.1 just to "make it work".

Modern JDKs disable many weak algorithms/ciphers by default. If compatibility with a legacy relay is needed, prioritize upgrading the relay or using an organization-controlled secure SMTP proxy rather than arbitrarily relaxing JVM-wide cryptographic policies.

### 3.4. Choosing the Right Host

`spring.mail.host` must be the exact name published by the provider, e.g., `smtp.example.com`. Avoid:
- connecting directly by IP if the certificate only contains DNS names;
- using an internal alias/CNAME not listed in the certificate's SAN;
- confusing the provider's web host with the SMTP host;
- confusing an internal relay host with a public host;
- using a hostname that DNS/routing directs to a TLS proxy presenting a different certificate.

The server name is used for certificate identity verification and usually SNI; misconfiguring the host can fail handshakes even when the IP and port are reachable.

## 4. What Does the TLS Handshake Verify?

A TLS handshake is not simply "turning on encryption". Client and server must:
1. Agree on a compatible protocol version and cipher suite.
2. Exchange data to establish session keys.
3. Server presents its certificate along with its certificate chain as needed.
4. Client confirms the certificate was issued by a trusted Certificate Authority.
5. Client verifies the certificate is within validity dates, suitable for server authentication, and matches the hostname.
6. Both sides complete authentication/cryptographic verification steps.

Some deployments also use **mTLS**, meaning the SMTP server requires the client to present a certificate. This is uncommon for public SMTP submission providers, though it can occur in enterprise relays.

### 4.1. Certificate Chain

Example:

```text
Root CA (trusted by client)
  |
  v
Intermediate CA
  |
  v
Server certificate
  Subject Alternative Name: DNS:smtp.example.com
  Extended Key Usage: TLS Web Server Authentication (if present)
```

Servers usually send the leaf certificate and required intermediates. The Java truststore holds trust anchors trusted by the JVM. If an intermediate is missing, a matching CA is missing, the chain is malformed, or a certificate is revoked under active checks, chain building/verification fails.

**Never blindly copy arbitrary certificates into the truststore until errors go away.** Verify the server's identity, issuing authority, certificate provenance, and organizational CA policy.

### 4.2. Hostname and Subject Alternative Name

Suppose the client connects to `smtp.example.com`, yet the certificate only contains:

```text
Subject Alternative Name:
  DNS:mail.other-example.net
```

When hostname verification is enabled, the server fails to prove its identity as `smtp.example.com` and the connection must fail.

Do not disable hostname verification. Instead:
- connect to the hostname supported by the certificate;
- configure a new certificate with the right SAN if you manage the relay;
- fix DNS/proxy configuration;
- avoid connecting directly to an IP unless the cert has an IP SAN and infrastructure supports it.

Two hostnames pointing to the same IP **do not automatically make one certificate valid for both hostnames**.

### 4.3. Time Affects Certificate Validity

Certificates carry `notBefore` and `notAfter` fields. If the server/client clock skews significantly or a certificate has expired, Java may report `CertificateExpiredException` or `CertificateNotYetValidException`.

Check NTP/clocks on hosts, VMs/containers, and certificate expiration dates. Fix system time or replace the certificate properly; never spoof clocks or disable expiration checks to bypass errors.

## 5. Java's Truststore vs. Browsers

Jakarta Mail connections typically use Java JSSE. Trust anchors come from **the truststore the JVM actually uses**, not necessarily the certificate store used by a browser or the OpenSSL CLI on the machine.

A common scenario:
- A browser accesses the provider's service without warnings.
- `openssl s_client` on a laptop verifies cleanly.
- The Java app inside a container still throws `PKIX path building failed`.

Possible reasons:
- Browser/OS uses a different truststore than the JDK.
- JDK inside the container has an outdated CA bundle.
- JVM has `javax.net.ssl.trustStore` pointing to a different file.
- Server sends a chain missing an intermediate that other tools fetch/fill automatically.
- Corporate proxy swaps certificates using an internal CA not yet trusted by the JVM.
- Container runs a different JDK than the development environment.

**Always inspect the truststore and JDK of the running application process**, not just the developer workstation.

### 5.1. Default Truststore

Java normally uses CAs bundled in truststores like `cacerts`, though details depend on the JDK distribution, security config, and system properties.

Common JSSE properties:

```text
javax.net.ssl.trustStore
javax.net.ssl.trustStoreType
javax.net.ssl.trustStorePassword
```

If a custom `trustStore` is configured, verify the file exists, the keystore type matches, and it contains the appropriate trust anchors. A nonexistent path or wrong password can cause connections to fail differently from the original symptom.

### 5.2. Creating a Dedicated Truststore for an Internal CA

If your organization runs an SMTP relay with a certificate signed by an **approved internal CA**, you can create a separate truststore:

```bash
keytool -importcert \
  -alias approved-mail-root-ca \
  -file /secure/certs/approved-mail-root-ca.pem \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

Then verify its contents:

```bash
keytool -list \
  -keystore /secure/mail-truststore.p12 \
  -storetype PKCS12
```

The command may prompt interactively for a password. **Only import CAs/certificates verified by infrastructure or PKI teams**; never import leaf certificates of unknown provenance just because the system is failing.

When launching the JVM, configure:

```text
-Djavax.net.ssl.trustStore=/secure/mail-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

The truststore password must be supplied via a controlled secret/launch mechanism. Avoid putting plaintext passwords in scripts or command lines visible to others. Note these JSSE properties can affect **multiple TLS connections in the same JVM**, not just Spring Mail. For complex apps, consider configuring an isolated `SSLContext`/transport per internal policy.

A custom truststore containing only an internal CA may also omit public CAs needed by other connections in the JVM. Audit trust anchors thoroughly rather than accidentally replacing `cacerts`.

### 5.3. Unsafe "Fixes"

Do not apply these in production:
- `mail.smtp.ssl.trust=*` to trust every server.
- Custom `TrustManager` accepting all certificates.
- Disabling `mail.smtp.ssl.checkserveridentity` to avoid hostname mismatch.
- Dropping `starttls.required` to fall back to plaintext on errors.
- Forcing TLS 1.0/1.1 or enabling weak ciphers without security review.
- Installing an unverified certificate into the truststore.
- Writing passwords, certificate private keys, or full SMTP debug logs to centralized logs.

Some of these may make tests appear to succeed while **removing the exact security guarantees TLS is meant to provide**.

## 6. Common TLS and Certificate Errors

Read the error chain from outer exception down to **root cause**. The same `MailSendException` can stem from many causes.

| Message / exception | Common cause | Investigation direction |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | JVM cannot build a trust chain from server to a trusted CA | Certificate chain, intermediates, JVM truststore, legitimate MITM proxy. |
| `SSLHandshakeException: No subject alternative DNS name matching ...` | Connected host does not match cert SAN | Hostname, IP/CNAME, certificate SAN, proxy endpoint. |
| `CertificateExpiredException` | Certificate expired | Leaf/intermediate expiration, renewal process. |
| `CertificateNotYetValidException` | Cert not yet valid or clock skew | System NTP/timezone and validity dates. |
| `Received fatal alert: handshake_failure` | Parties could not agree on cipher/protocol or cert policy | TLS versions/ciphers, mTLS, server logs, JDK. |
| `Received fatal alert: protocol_version` | One party does not support proposed protocol version | JVM/relay TLS configuration. |
| `no cipher suites in common` | No overlapping cipher suites | JDK disabled algorithms, server policy. |
| `Unsupported or unrecognized SSL message` | Client expects TLS while server speaks plaintext | Port and TLS mode, proxy/gateway. |
| `wrong version number` | Usually mixing up implicit TLS and plaintext endpoint | Port, STARTTLS vs. SSL enable, TLS terminator. |
| `Connection reset` / `EOFException` mid-handshake | Server/proxy closed connection, protocol mismatch, infra policy | Network path, server logs, SNI, timeouts. |
| `STARTTLS is required but host does not support STARTTLS` | Server does not advertise or execute STARTTLS | EHLO capabilities, host/port, proxy stripping. |
| `530 Must issue a STARTTLS command first` | Client tried AUTH/MAIL before upgrading to TLS as server requires | `starttls.enable`, `required`, port. |
| `handshake timed out` / `SocketTimeoutException` | Slow relay/network, hung proxy, or incomplete handshake | Network, timeouts, server load and logs. |
| `bad_certificate` / `certificate_required` | Server requires or rejects client cert in mTLS | Client key/cert, client CA trust, relay policy. |
| `MailAuthenticationException` after TLS succeeds | Wrong credentials or AUTH mechanism, not necessarily handshake error | Auth provider, app password/OAuth2, server response. |

These are **isolation hints**, not automatic rules. The same message can arise in multiple configurations. Inspect nested causes, timing, and logs from both sides.

### 6.1. `PKIX path building failed`

Illustrative stack trace:

```text
org.springframework.mail.MailSendException: Mail server connection failed
Caused by: jakarta.mail.MessagingException: Could not convert socket to TLS
Caused by: javax.net.ssl.SSLHandshakeException:
    PKIX path building failed
Caused by: sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
```

Interpretation: Java received a certificate during the handshake yet could not construct a valid trust path.

Check:
1. Did the server send all intermediate certificates?
2. Are the root/intermediate CAs trusted by the JVM running the app?
3. Does the container Java have a different truststore than dev?
4. Is a TLS inspection proxy swapping the certificate?
5. Was the certificate misissued or expired?
6. Is the app connecting to the right SMTP host?

Do not jump to "Java is missing a certificate" and import unconditionally. If hitting a spoofed endpoint, trusting the wrong cert is worse than the initial error.

### 6.2. Hostname Mismatch

Example:

```text
No subject alternative DNS name matching smtp.example.com found
```

The issue is not CA trust, but that **the server name is not among the identities proven by the certificate**.

Valid fixes:
- use a hostname supported by the certificate;
- ask the provider to update the certificate;
- fix the endpoint, SNI, or DNS;
- reissue the org relay cert with the right SAN.

Do not disable hostname checking. Importing a CA into the truststore also **will not fix** a SAN mismatch.

### 6.3. Handshake Failure Due to Protocol/Cipher

If the server supports only legacy TLS versions disabled by the JDK, the client may report `handshake_failure` or `protocol_version`.

Check:
- JDK version and `jdk.tls.disabledAlgorithms` policy.
- TLS versions supported by the server.
- Whether the server is actually the right SMTP endpoint.
- Custom `mail.smtp.ssl.protocols` or cipher suites configuration.
- Whether mTLS is enabled on the relay without a client cert configured.

Prioritize upgrading the relay/server or using a modern port/provider. Never "fix" by disabling JDK protections without a formal security review.

## 7. Ordered Diagnostic Workflow

An approach that minimizes wasted effort:

```text
1. Confirm host + port + TLS mode
                 |
                 v
2. Do DNS / TCP connect?
                 |
                 v
3. SMTP banner / EHLO / STARTTLS capability
                 |
                 v
4. TLS handshake and certificate chain
                 |
                 v
5. SAN hostname + validity + Java truststore
                 |
                 v
6. SMTP AUTH
                 |
                 v
7. MAIL FROM / RCPT TO / DATA
                 |
                 v
8. SMTP accepted / provider delivery status
```

### Step 1 — Lock Down Provider Details

Record:
- Official hostname.
- Port.
- STARTTLS or implicit TLS.
- Whether authentication is required.
- Minimum TLS version or custom CA requirements.
- Any intermediate proxy/gateway/VPN/egress relay.
- Which machine/runtime runs Java/JDK.

Do not guess from a hostname or from an old configuration.

### Step 2 — Check DNS and TCP

Use tools suited to the environment:

```powershell
Resolve-DnsName smtp.example.com
Test-NetConnection smtp.example.com -Port 587
```

On Linux, use equivalents like `getent hosts`, `nc`, or check TCP network policies. Successful TCP connect only proves host/port reachability; **it does not prove TLS or certificates are valid**.

If TCP itself times out or refuses connections, inspect firewalls, security groups, proxies, Kubernetes NetworkPolicies, NAT egress, ISP port blocking, and provider status before investigating truststores.

### Step 3 — Check STARTTLS Support and Certificates from the Right Environment

For port 587:

```bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.com:587 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -showcerts
```

For implicit TLS on port 465:

```bash
openssl s_client \
  -connect smtp.example.com:465 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -showcerts
```

These are diagnostic commands; they do not send email. Run them from **the same network/container/host** used by the application if possible; a personal laptop may take a different network path.

How to read:
- `Certificate chain`: certs sent by the server.
- `subject`, `issuer`: identity and issuing CA.
- `notBefore`, `notAfter`: cert validity window.
- `Verify return code`: verification result against OpenSSL's truststore.
- `Protocol` and `Cipher`: negotiated TLS version/cipher.
- Handshake errors before seeing a certificate may point to TLS mode, protocol, or network policy.

Notes:
- `-servername` supplies SNI; `-verify_hostname` checks hostname if supported by your OpenSSL version.
- OpenSSL has its own truststore, so passing there **does not guarantee Java trusts the chain**.
- Never enter SMTP credentials into diagnostic tools or capture logs containing secrets.
- If OpenSSL is unavailable on the OS, use an organization-approved diagnostic environment; do not install tools from untrusted sources.

### Step 4 — Compare the Certificate Against the Actual Hostname

Compare the certificate SAN with the exact `spring.mail.host` value, even when connecting through an alias/proxy. If connecting to an IP when the certificate only has DNS names, switch to a valid hostname. If DNS returns multiple endpoints, verify certificate consistency across nodes/load balancers.

### Step 5 — Inspect the Java Process's Truststore

Check:
- JDK vendor/version inside the runtime container/VM.
- JVM startup properties.
- Whether the mounted truststore file exists in the container.
- File read permissions for the app's runtime user.
- Whether password/type are valid.
- Whether trust anchors match approved CAs.
- Whether the server sends the complete certificate chain.

Do not inspect only your laptop's truststore if the app runs in a separate pod.

### Step 6 — Check SMTP AUTH and Sending Only After TLS

If TLS succeeds yet errors occur at AUTH, inspect:
- Username/secret.
- App password or OAuth2 requirement.
- Whether the provider permits Basic Auth.
- Whether the account is permitted SMTP submission.
- From/recipient policies or IP allowlists.

Do not confuse `535 Authentication failed` with certificate errors. Adding a CA to the JVM will not fix a wrong password.

## 8. TLS Diagnostic Logging and Spring Mail

### 8.1. Enabling JavaMail Debug Under Control

In an isolated diagnostic environment, you can enable:

```yaml
spring:
  mail:
    properties:
      mail:
        debug: true
```

Jakarta Mail debugging can reveal connection progress, EHLO/STARTTLS/AUTH capabilities, and SMTP replies. However, **never enable it by default in production**, because logs can expose system metadata, email addresses, authentication mechanisms, and potentially sensitive data depending on configuration.

Never paste raw debug logs into public tickets; redact internal hosts, emails, tokens, secrets, or sensitive content.

### 8.2. Enabling JSSE Debug in the JVM When Needed

Example diagnostic flags:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
```

These flags show negotiated TLS versions, certificate validation steps, and trust decisions. They generate very verbose logs, so enable only temporarily in restricted-access environments and turn off once isolated.

What to observe:
- Is the client sending the handshake to the right host/port?
- Which server certificates are received?
- Which chain is trusted or rejected?
- Which protocol/cipher is selected?
- Are there fatal alerts from client or server?
- Does the handshake fail before or after certificate verification?

### 8.3. Extracting the Root Cause from Spring Exceptions

An example logging classification **without printing potentially sensitive messages**:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;

public class MailErrorLogger {

    private static final Logger log =
        LoggerFactory.getLogger(MailErrorLogger.class);

    public void logFailure(String messageKey, MailException ex) {
        Throwable root = ex;
        while (root.getCause() != null && root.getCause() != root) {
            root = root.getCause();
        }

        log.warn(
            "smtp_submission_failed messageKey={} exceptionType={} rootType={}",
            messageKey,
            ex.getClass().getSimpleName(),
            root.getClass().getSimpleName()
        );
    }
}
```

This is a minimal logging example. In restricted diagnostic environments, stack traces may be needed with proper access controls; never log credentials, MIME content, or uncontrolled full exception details.

For `MailSendException`, failed messages or nested exceptions can be useful when sending multiple messages. Analyze per message/recipient and avoid concluding all failed if the provider accepted a subset.

## 9. Example `JavaMailSenderImpl` Configuration Without Boot Auto-Config

If a Spring Framework application does not use Spring Boot auto-configuration, configure the sender explicitly:

```java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

This is an example for STARTTLS on port 587. When using port 465 implicit TLS, adjust per provider and use `mail.smtp.ssl.enable=true` instead of STARTTLS mode.

**Never hardcode passwords.** In real deployments, inject from a secret manager/environment configuration with a rotation process. Protect environment/secret values and never dump environment variables to logs.

### 9.1. Example Sending a MIME Message and Handling Errors

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SecureNoticeMailService {

    private final JavaMailSender mailSender;

    public SecureNoticeMailService(JavaMailSender mailSender) {
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

        // MailException is a runtime exception when submission fails.
        // Do not retry every MailException directly inside an HTTP request.
        mailSender.send(message);
    }
}
```

When TLS errors occur, exceptions may be wrapped in Spring's `MailException` or `MessagingException`/`SSLHandshakeException` underneath. Let a dedicated service/worker record state and apply retry policies based on cause, rather than catching exceptions and looping indefinitely.

## 10. Real-World Scenarios and How to Handle Them

### 10.1. Port 587 with Implicit TLS Enabled

Misconfiguration:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail:
        smtp:
          ssl:
            enable: true
```

While the server on this port expects plaintext SMTP before `STARTTLS`, the client immediately sends TLS ClientHello. The result can be a timeout or protocol error.

Fix: use `starttls.enable=true` and `starttls.required=true`; do not set `ssl.enable=true` on endpoints supporting only STARTTLS.

### 10.2. Port 465 with Only STARTTLS Enabled

If the server requires TLS from the very first byte, the client waits for an SMTP greeting before sending `STARTTLS`. Both sides wait on each other or close the connection.

Fix: switch to `mail.smtp.ssl.enable=true` per the provider's implicit TLS configuration.

### 10.3. Certificate Valid on Laptop Yet Fails in Docker/Kubernetes

Possible causes:
- JDK image includes a different truststore/CA bundle.
- Truststore mounted at the wrong path or lacks read permissions.
- Container clock out of sync.
- Pod egress routes through a TLS inspection proxy.
- Truststore override omitted public CAs.
- Nodes/load balancers serve inconsistent certificates.

Remediation:
1. Check the JDK image and JVM options of the running container.
2. Check network/DNS to the SMTP host from the exact pod/host.
3. Compare server cert/chain from that egress path.
4. Confirm the Java process's truststore configuration.
5. Fix the CA, intermediate, or proxy at the source; never replace with trust-all.

### 10.4. New Certificate After Rotation Causes Failures

Some relays change CAs/intermediates during renewal. If an internal truststore pins a leaf cert or is too old, rotation can break handshakes.

Best practices:
- monitor relay expiry and chains;
- plan CA rollovers;
- trust approved CAs rather than arbitrarily pinning leaf certs;
- deploy/test before switching production certificates;
- avoid letting dev/staging use different CAs unnoticed.

### 10.5. Proxy or TLS Inspection Appliance

An enterprise may place a proxy/SMTP gateway that re-signs certificates. The JVM sees a cert signed by an internal CA rather than the provider's public cert.

Do not rush to import a cert seen over an unverified connection. Ask infrastructure:
- What are the official SMTP endpoint and egress path?
- Does the proxy legitimately perform TLS inspection on this connection?
- Which internal CA is approved?
- Are SNI and STARTTLS passthrough supported?

Then configure trust anchors per security policy.

### 10.6. `STARTTLS` Disappears from `EHLO`

If provider docs state STARTTLS is supported yet the server does not advertise the capability:
- Wrong port/host may be configured.
- An intermediate relay may strip or alter the EHLO response.
- STARTTLS was disabled on a node/backend.
- A network appliance is malfunctioning or interfering.
- Traffic was routed to a different endpoint.

If `starttls.required=true`, the connection should refuse rather than send credentials in plaintext. Preserve this protective behavior.

### 10.7. Handshake Succeeds Yet Authentication Fails

After fixing TLS, the app may proceed and receive `535 Authentication failed`. This is a new stage; it does not mean the TLS fix was wrong.

Check provider policies on app passwords/OAuth2, SMTP AUTH account status, username, send permissions, and login limits. Never turn off TLS to fix AUTH.

### 10.8. Multiple DNS Addresses, Only One Node Has a Bad Cert

With an SMTP host resolving to multiple IPs or a load balancer, one node may lack an intermediate or serve an expired cert. This manifests as intermittent failures affecting only some requests/pods.

Record timestamps, resolved addresses, and network paths as infrastructure permits, then have the provider/operations fix configuration consistently across nodes. Do not switch to trust-all just because errors are intermittent.

## 11. Retrying TLS Errors: When Does It Help?

Not every send error should be retried. Retrying does not fix a certificate with the wrong identity or a truststore missing a CA.

| Error group | Retry immediately? | Appropriate action |
|---|---|---|
| Expired cert | No | Replace/renew certificate or fix path to right endpoint. |
| Hostname mismatch | No | Fix hostname/certificate SAN. |
| PKIX due to missing CA/intermediate | Do not retry blindly | Fix chain/truststore after verifying source. |
| Incompatible protocol/cipher | No | Fix TLS/relay/JDK policy under control. |
| STARTTLS vs. implicit TLS mismatch | No | Fix host/port/mode config. |
| Transient TCP reset or timeout | Maybe | Retry with backoff/jitter, attempt cap; still investigate if persistent. |
| Relay overloaded/unresponsive | Maybe | Retry per provider policy, rate limits/circuit breaker. |
| Wrong SMTP AUTH | Usually no | Fix credentials/auth mechanism. |
| Unknown error after sending DATA | Do not retry immediately | Record `UNKNOWN` and reconcile to reduce duplicates. |

TLS handshakes normally occur **before SMTP DATA**, so if you are certain the handshake failed before submission, retrying after a transient network error carries lower duplicate risk. However, a generic exception wrapped by `send(...)` does not prove which step finished. Track logs and state per attempt.

In queue/outbox systems, store `messageKey`, `attemptId`, root cause category, and next retry timestamp. Avoid annotating everything with unbounded `@Retryable` without outcome tracking.

## 12. Testing and Preventing TLS Errors

### 12.1. Environments to Test

- **Local**: connect to an SMTP sandbox with valid TLS.
- **CI/integration tests**: use a controlled SMTP test server and test certificates.
- **Staging**: test exact hostname/port/TLS mode and production-like network paths.
- **Production smoke check**: verify connection/handshake per runbook and permissions without blasting real emails just to test connectivity.

You can use `JavaMailSenderImpl.testConnection()` to verify sender connectivity in appropriate environments:

```java
JavaMailSenderImpl sender = ...;
sender.testConnection();
```

This method helps detect some network/TLS/AUTH errors during connection setup, **but does not replace real send integration tests**, nor does it verify body/attachments or destination delivery.

Spring Boot may also support startup connection checks like `spring.mail.test-connection=true` depending on version and config; enabling it can prevent startup if SMTP is temporarily interrupted. Use only when fail-fast startup is desired, not blindly for every system.

### 12.2. Recommended Test Cases

| Test case | Expectation |
|---|---|
| STARTTLS port 587 configured properly | TLS connection succeeds and test message sends to sandbox. |
| Implicit TLS port 465 configured properly | TLS connection succeeds immediately after TCP. |
| Mode swapped between 587 and 465 | Fails; records config/TLS category, no plaintext fallback. |
| Untrusted CA certificate | Handshake fails; credentials/body not sent. |
| Hostname absent from SAN | Handshake rejected when hostname check enabled. |
| Expired certificate | Connection rejected and alerted. |
| Server missing intermediate | Verifies corresponding chain/PKIX failure. |
| No common TLS version/cipher | Handshake fails with isolatable logs. |
| STARTTLS not advertised | `required=true` rejects connection. |
| Wrong SMTP AUTH after valid TLS | Reports separate authentication error, not PKIX. |
| Network timeout | Bounded retry per policy and attempt recorded. |
| Provider cert rotation | System trusts planned new CA without trust-all. |

Tests must run against authorized test servers or sandboxes. Never place real credentials in test source or send test emails to real unintended recipients.

### 12.3. Do Not Simulate Success by Disabling Validation

A unit test using a mock sender can verify the service calls `send(...)`, **but cannot prove TLS configuration is right**. Integration tests require real SSL validation against a controlled truststore and a hostname matching SAN.

Do not configure `trustAll` in tests and assume production will be safe. If a test CA is needed, create a dedicated test CA and import it into a test-only truststore.

## 13. Operations, Monitoring, and Preventing Recurrence

Monitor:
- TLS handshake failure rate by SMTP host/port.
- Counts of PKIX/hostname/expired certificate errors.
- Connection timeout and AUTH failure rates.
- Latency from connection start to SMTP accepted.
- SMTP provider status and quotas/rate limits.
- Certificate expiry dates and renewal schedules.
- JDK/truststore differences across environments.
- Pending outbox item counts and retry counts.
- Incidents affecting only a single node/egress route.

Never log:
- SMTP username/password.
- OAuth2 access tokens or app passwords.
- Full MIME bodies, attachments, Base64 payloads.
- Full raw SMTP AUTH exchanges.
- Private keys, keystore passwords.
- Token-bearing URLs.

For each error, store **message key/correlation ID**, allowed host alias, TLS mode, error category, and timestamp. This enables traceability without storing recipient email content.

### 13.1. Incident Runbook

When mail error rates spike suddenly:

1. Separate network/TCP, TLS/certificate, and SMTP AUTH errors.
2. Check recent changes to provider, certificates, DNS, networking, or JDK images.
3. Confirm deployed host, port, and TLS mode.
4. Run TLS diagnostics from an equivalent egress environment.
5. Inspect leaf/intermediate/SAN/validity and the JVM's truststore.
6. If a CA error occurs, verify the CA/cert with PKI before importing.
7. Restore proper configuration; never disable TLS verification.
8. Re-test connection/test email per approved procedure.
9. Drain worker backlog with rate limits/backoff to avoid bursts and duplicates.
10. Document root cause and update monitoring/rotation to prevent recurrence.

### 13.2. After Remediation

If workers held jobs in `RETRY_WAIT` during handshake failures, processing can resume after fixing config. If errors occurred as `UNKNOWN` during submission, reconcile before resubmitting to avoid duplicates.

Never purge the outbox or reset attempt counts blindly to "resend everything". Know which messages were never SMTP-accepted, which the provider already holds, and which hard-bounced.

## 14. Common Misconceptions

### "Port 587 Always Uses SSL Immediately on Connect"

No. Port 587 usually uses STARTTLS: SMTP greeting and EHLO happen before TLS. Implicit TLS usually uses port 465.

### "Setting `starttls.enable=true` Is Enough to Enforce Encryption"

Not necessarily. For providers requiring STARTTLS, also set `starttls.required=true` so it does not fall back if the server does not offer STARTTLS.

### "`PKIX path building failed` Means the Certificate Is Definitely Fake"

No. It may be a missing intermediate or a Java truststore missing the CA. Still, verify chain/provenance before adding trust.

### "Importing the Leaf Certificate Solves It Long-Term"

Unlikely. Leaf rotation will break it again, and trusting unverified certificates is risky. Prefer proper chains/CAs and approved PKI procedures.

### "Setting `ssl.trust=*` Is a Standard Fix"

No. Trusting every host bypasses part of server identity verification. This is unsuitable for production.

### "If OpenSSL Verifies OK, Java Will Definitely Verify OK"

No. OpenSSL and Java can use different truststores, protocols, and certificate policies.

### "An SMTP AUTH Error Means a TLS Error"

No. AUTH usually occurs after TLS is already established. Classify by response and root cause.

### "TLS Protects Emails End-to-End"

No. TLS between the app and SMTP relay protects only that hop. Emails can traverse multiple relays and are stored/processed by providers and recipients. End-to-end protection requires dedicated mechanisms like S/MIME or OpenPGP as needed.

### "Reading Just the `MailSendException` Line Is Enough"

No. Inspect nested `MessagingException`, `SSLHandshakeException`, trust validation causes, and server logs if available.

## 15. Practice Exercises

### Exercise 1 — Distinguishing TLS Modes

Write two `application.yml` configurations for the same provider: port 587 mandatory STARTTLS and port 465 implicit TLS. Explain why you cannot swap the two configs merely by changing the port.

### Exercise 2 — Classifying Errors

Given logs showing `PKIX path building failed`, `No subject alternative DNS name matching`, `handshake_failure`, and `535 Authentication failed`, identify the error layer and first diagnostic step for each.

### Exercise 3 — Checking Certificates with OpenSSL

In an authorized sandbox environment, run `openssl s_client` with STARTTLS and implicit TLS. Record the certificate chain, SAN, validity, protocol, and cipher; compare with the app's SMTP host.

### Exercise 4 — Internal CA Truststore

With an authorized test CA, create a PKCS12 truststore using `keytool` and configure the JVM to use it. Explain the difference between trusting the right CA vs. trusting all certificates.

### Exercise 5 — Checking Hostname Verification

Use a test SMTP server with a certificate whose SAN differs from the connected hostname. Verify the handshake is rejected when `mail.smtp.ssl.checkserveridentity=true` and propose how to fix the endpoint/certificate.

### Exercise 6 — Disabled STARTTLS

Test against a server that does not advertise STARTTLS. Compare `starttls.enable=true` alone vs. adding `starttls.required=true`. Explain fail-closed behavior.

### Exercise 7 — Container vs. Laptop

An app sends from a laptop yet hits PKIX errors inside a container. List differences in JDK, truststore, proxy, DNS, and CA chain to inspect. Do not propose disabling certificate validation.

### Exercise 8 — Exception Wrapping

Write a class classifying `MailException` by root cause type to emit TLS/network/auth metrics. Do not log passwords, MIME data, or tokens.

### Exercise 9 — Cert Rotation

Simulate a provider rotating a leaf certificate under the same CA, then rotating an organization-approved intermediate/CA. Design testing and truststore rollout steps ahead of rotation time.

### Exercise 10 — Post-Incident Retry

During a TLS incident, 500 outbox items remain unsent and 5 items are in `UNKNOWN` state. Design rate-limited backlog recovery without blindly retrying items whose submission outcome is uncertain.

## 16. Summary

TLS, certificate, and handshake errors in Spring Framework Mail usually stem from **confusing STARTTLS with implicit TLS, wrong host/port selection, incomplete or untrusted certificate chains, SAN hostname mismatches, expired certificates, incompatible protocols/ciphers, or network/proxy interference**.

The safe remediation approach is:
1. Confirm exact **SMTP host, port, and TLS mode**.
2. For port 587 STARTTLS, use `mail.smtp.starttls.enable=true` and `required=true` when the provider requires TLS.
3. For port 465 implicit TLS, use `mail.smtp.ssl.enable=true`.
4. Enable `mail.smtp.ssl.checkserveridentity=true` and keep certificate validation active.
5. Verify certificate chain/SAN/validity and **the JVM's actual truststore**.
6. Diagnose from the right network/runtime using OpenSSL, `keytool`, and controlled JSSE logs.
7. Separate TLS errors from network, AUTH, and SMTP submission outcomes.
8. Never use trust-all or downgrade encryption to bypass errors; fix the root cause and retry within bounds.

Proper TLS configuration not only keeps `JavaMailSender` connections reliable; it ensures the application exchanges credentials and email content with **the SMTP server it actually intends to trust**.
