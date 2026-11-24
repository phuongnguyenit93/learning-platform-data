# TLS in Connections to the Mail Server

When a Spring Framework Mail application sends an email, data typically travels over a connection from the **application** to the **SMTP server**. This connection may carry authentication credentials, the envelope sender/recipient, headers, HTML content, plain text, and attachments. Without an appropriate protection layer, the data can be observed or modified by an actor capable of intercepting traffic in transit.

**Transport Layer Security (TLS)** is a mechanism that protects network connections through encryption, server identity verification via certificates, and integrity checking of exchanged data. In SMTP, TLS is commonly used in two ways: **STARTTLS** (upgrading an initially plain SMTP connection to TLS) or **implicit TLS** (establishing TLS immediately upon connection).

Key points of this lesson:

- TLS protects **a single connection hop** between the mail client and the SMTP server; it does not automatically encrypt emails end-to-end.
- **STARTTLS** on the submission port (typically 587) differs from **implicit TLS** (typically port 465); do not arbitrarily configure both modes for the same connection.
- For applications requiring security, simply enabling STARTTLS as optional is not enough: you must **require the upgrade to succeed** and **verify the certificate/hostname**.
- **SMTP AUTH does not replace TLS**; account authentication and transport encryption serve different roles.
- TLS errors are usually caused by the wrong port, unsupported STARTTLS, untrusted certificates, hostname mismatches, or incompatible TLS versions/ciphers.
- Never fix TLS errors by disabling certificate verification or trusting every server.

This article uses Spring Boot and **JavaMailSenderImpl** examples, while clarifying the security boundaries for production configuration and troubleshooting.

## 1. Which part of the email flow does TLS protect?

An email may pass through multiple systems:

~~~text
Spring application
        |
        |  SMTP submission over TLS
        v
Outbound SMTP server / provider
        |
        |  SMTP relay: TLS may be used, depending on policy and configuration
        v
Receiving mail infrastructure
        |
        v
Mailbox and recipient email client
~~~

When Spring connects to an outbound SMTP server using TLS, TLS protects the **Spring application ↔ outbound SMTP server** hop. At the server, the message is typically decrypted for processing, scanning, routing, signing, storage, or forwarding.

If the server forwards the message to another mail server, that is a **separate connection** with its own protection mechanism. The fact that the first hop uses TLS does not prove that every subsequent hop uses TLS.

### 1.1. Security properties of TLS

| Property | Meaning on an SMTP connection |
| --- | --- |
| **Confidentiality** | Prevents third parties from reading connection contents |
| **Integrity** | Detects data modification during transmission |
| **Server authentication** | Verifies that the connected server has a valid certificate for the expected hostname |
| **Session security** | Establishes session keys to protect data transmitted within the TLS session |

In a typical SMTP client configuration, the application authenticates the **server** via its TLS certificate. The client can authenticate to SMTP using a username/password, app password, or OAuth2 after the connection is protected. This is the **SMTP AUTH** mechanism, not client certificate authentication.

### 1.2. TLS is not end-to-end encryption

Application-hop TLS is not equivalent to S/MIME or OpenPGP:

- **TLS:** protects data in transit over a specific connection.
- **S/MIME/OpenPGP:** can encrypt message content for specific recipients at the content layer, following a separate key management model.

If only authorized recipients must be able to read the content, evaluate an appropriate content protection solution. Do not describe SMTP STARTTLS as end-to-end security.

### 1.3. TLS does not guarantee inbox delivery

An SMTP server may accept a message, and the message may later be filtered as spam, bounce, or go unopened by the recipient. TLS does not replace domain authentication, spam controls, or delivery tracking.

## 2. How does STARTTLS work?

**STARTTLS** is an SMTP extension that allows a client to upgrade a connection initially using plain-text SMTP to a TLS-protected connection.

Conceptual flow:

~~~text
Spring / Jakarta Mail                     SMTP server
        |                                      |
        |------------- TCP connect ---------->|
        |<-------------- 220 ------------------|
        |------------- EHLO ------------------>|
        |<--------- 250-STARTTLS --------------|
        |------------- STARTTLS ------------->|
        |<-------------- 220 ------------------|
        |======= TLS handshake ===============|
        |     Verify certificate/hostname      |
        |------------- EHLO over TLS --------->|
        |<--------- Server capabilities -------|
        |------------- AUTH over TLS -------->|
        |------------- MAIL FROM ------------->|
        |------------- RCPT TO --------------->|
        |------------- DATA ------------------>|
        |        MIME message over TLS         |
        |<---------- SMTP response ------------|
~~~

Before the TLS handshake succeeds, the commands used to negotiate the upgrade still occur on the initial connection. After the upgrade, the client sends EHLO again to retrieve the server's capabilities in the secured state.

### 2.1. Why send EHLO again after STARTTLS?

The capabilities advertised by the server before and after TLS may differ. For example, the server might not advertise SMTP AUTH before the connection is encrypted.

Therefore, after the TLS handshake, the client must follow the proper SMTP flow and not assume that all extensions from the initial EHLO remain in effect identically.

### 2.2. STARTTLS is an upgrade, not TLS from the first byte

With STARTTLS, the connection starts as plain SMTP and is then upgraded. This **does not mean** content and credentials are sent unencrypted: if the client enforces that STARTTLS succeeds before AUTH/DATA, those sensitive parts travel over TLS.

Conversely, if the application allows fallback when the server does not advertise STARTTLS, it may proceed over an unencrypted connection. This is a configuration point that must be controlled.

### 2.3. Which port does STARTTLS use?

Port **587** is commonly used for **message submission** with STARTTLS. This is the typical choice when an application logs in to a provider to send email.

The port alone does not dictate TLS: follow your SMTP provider's documentation and the connection mode that the endpoint provides.

## 3. How does implicit TLS differ from STARTTLS?

**Implicit TLS** means the client initiates the TLS handshake immediately after opening the TCP connection, **before** exchanging any SMTP commands.

~~~text
Spring / Jakarta Mail                     SMTP server
        |                                      |
        |------------- TCP connect ---------->|
        |======= TLS handshake ===============|
        |     Verify certificate/hostname      |
        |<--------- SMTP greeting over TLS ----|
        |------------- EHLO over TLS --------->|
        |------------- AUTH over TLS --------->|
        |------------- MAIL FROM ------------->|
        |------------- RCPT TO --------------->|
        |------------- DATA ------------------>|
        |          MIME over TLS               |
~~~

Port **465** is commonly used for SMTP submission over implicit TLS.

| Comparison point | STARTTLS | Implicit TLS |
| --- | --- | --- |
| Timing of TLS handshake | After greeting, EHLO, and STARTTLS command | Immediately after TCP connect |
| Common submission port | **587** | **465** |
| Typical Jakarta Mail property | **mail.smtp.starttls.enable** | **mail.smtp.ssl.enable** |
| Has STARTTLS command step | Yes | No |
| Certificate/hostname verification | Required | Required |
| Suitable for | Endpoints requiring STARTTLS | Endpoints using TLS from the start |

Both approaches can protect the connection effectively if configured properly. Do not claim that implicit TLS is always cryptographically stronger than STARTTLS: the level of security also depends on the TLS version, certificate verification, fail-closed policy, and server configuration.

### 3.1. Why can't the same configuration work for both?

If the client sends a TLS ClientHello immediately to an endpoint expecting an initial SMTP greeting, or sends a plaintext SMTP greeting to an endpoint expecting TLS first, the two sides will not understand each other.

Possible symptoms include:

- Connection hanging until timeout.
- Connection reset.
- SSLException.
- Errors like “Unrecognized SSL message” or “wrong version number”, depending on the provider.
- Server closing the connection immediately upon connect.

First, check **whether the port and mode match the SMTP server documentation**.

### 3.2. Should STARTTLS and SSL be enabled simultaneously?

For a single submission endpoint, normally choose **one** of the two modes:

- **587/STARTTLS:** enable STARTTLS, do not enable implicit TLS.
- **465/implicit TLS:** enable SSL/TLS from the start, no STARTTLS upgrade needed.

Do not configure both just to try to be “more secure”. If both modes are enabled at the same time, the behavior may be confusing or incompatible with the server; the right approach is to match the endpoint's mode.

## 4. What do ports 25, 465, and 587 mean?

| Port | Common role | Common TLS | Notes |
| --- | --- | --- | --- |
| **25** | SMTP relay between mail servers | STARTTLS if supported/required by policy | Many ISPs or cloud providers restrict outbound port 25 |
| **465** | Message submission | Implicit TLS | TLS handshake from the start |
| **587** | Message submission | STARTTLS | Usually uses SMTP AUTH after upgrade |

These are **common conventions**, not mandatory rules for every server. Internal providers may use different ports.

Spring applications typically act as a **mail submission client**, so follow the provider's guide for 465 or 587 instead of defaulting to SMTP relay port 25.

## 5. Configuring Spring Boot with STARTTLS on port 587

Illustrative YAML configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Key values to understand:

| Property | Purpose |
| --- | --- |
| **spring.mail.host** | SMTP host name |
| **spring.mail.port** | Port of the STARTTLS endpoint |
| **spring.mail.username/password** | SMTP credentials, provided via environment/secret manager |
| **spring.mail.default-encoding** | Default charset for email text; does not control TLS |
| **mail.smtp.auth** | Enables SMTP authentication |
| **mail.smtp.starttls.enable** | Allows Jakarta Mail to upgrade via STARTTLS if the server supports it |
| **mail.smtp.starttls.required** | Does not proceed if STARTTLS is unavailable or fails to complete |
| **mail.smtp.ssl.checkserveridentity** | Enables hostname identity verification of the TLS peer |
| **mail.smtp.connectiontimeout** | Connection timeout limit |
| **mail.smtp.timeout** | Read timeout limit |
| **mail.smtp.writetimeout** | Write timeout limit |

The example uses the placeholder host and account **example.org**. Environment variables should be supplied via a secrets management mechanism; never store real passwords in source control.

### 5.1. Difference between enable and required

Two properties that are often confused:

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
~~~

- **starttls.enable=true** allows using STARTTLS when the server supports it. If the server does not advertise STARTTLS, the default behavior may proceed unencrypted.
- **starttls.required=true** requires STARTTLS; if the server does not offer STARTTLS or the upgrade fails, the operation must not continue normally.

For submission using accounts and sensitive data, **configure both enable and required to true** once the endpoint is confirmed to be STARTTLS.

### 5.2. Why is required necessary?

If only enable is turned on:

~~~text
SMTP server does not advertise STARTTLS
        |
        v
Client can still continue with an unencrypted session
        |
        v
Risk of transmitting AUTH/MIME in plaintext
~~~

When required is enabled:

~~~text
SMTP server does not advertise STARTTLS
        |
        v
Client reports an error and does not send the message
~~~

This is the **fail-closed** principle: prefer halting delivery when mandatory security conditions are not met.

### 5.3. Why doesn't default-encoding protect the connection?

**UTF-8** is a text content charset. It does not encrypt data to prevent eavesdropping. **Base64** in MIME is also not security encryption.

TLS operates at the transport layer; charsets and Content-Transfer-Encoding operate at the content representation layer.

## 6. Configuring Spring Boot with implicit TLS on port 465

When the provider requires TLS from the start:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Here **mail.smtp.ssl.enable=true** makes the SMTP connection use TLS from the beginning. There is no need to enable STARTTLS required for a true implicit TLS endpoint.

### 6.1. Property names still start with mail.smtp

In common usage with **JavaMailSenderImpl** and the **smtp** protocol, implicit TLS configuration can use **mail.smtp.ssl.enable=true**. You do not necessarily need to change the protocol to **smtps**.

If your application uses the separate **smtps** transport protocol, property names and transport initialization may differ; check the Jakarta Mail provider documentation for that mode. Do not randomly mix **mail.smtp** and **mail.smtps** prefixes.

### 6.2. When to choose port 465?

Choose it if the SMTP provider offers an explicit submission endpoint for implicit TLS, or if deployment policy mandates it. Do not simply change the port from 587 to 465 while keeping all the STARTTLS settings.

## 7. Equivalent configuration using application.properties

Properties format with STARTTLS:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true

spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

Properties format with implicit TLS:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.ssl.enable]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Square brackets accurately represent keys in the JavaMail properties map. In YAML, keys containing dots should be enclosed in quotes as shown in the examples above.

## 8. Configuring JavaMailSenderImpl directly without Boot

In a plain Spring Framework application, you can instantiate **JavaMailSenderImpl**:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public class MailSenderFactory {

    public JavaMailSenderImpl create(
            String host,
            int port,
            String username,
            String password
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(properties);
        return sender;
    }
}
~~~

The method receives the host/account/secret from external configuration. Do not hard-code passwords in source code.

### 8.1. For implicit TLS

Change the mode configuration:

~~~java
sender.setPort(465);

Properties properties = new Properties();
properties.put("mail.smtp.auth", "true");
properties.put("mail.smtp.ssl.enable", "true");
properties.put("mail.smtp.ssl.checkserveridentity", "true");

sender.setJavaMailProperties(properties);
~~~

Do not keep the STARTTLS properties from the previous factory at the same time if the endpoint actually requires implicit TLS.

### 8.2. Do not create a new JavaMailSender for every message

Normally, Spring Boot auto-configures **JavaMailSender** when the dependencies and configuration conditions are met. Inject that bean into your service.

If you have multiple SMTP accounts/tenants, design a controlled sender selection and resource management mechanism, avoiding creating connection configurations arbitrarily from user input.

## 9. Example service sending mail over a TLS connection

TLS is configured on the **transport**, not per MimeMessage. A mail-sending service uses JavaMailSender as usual:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SecureNotificationMailService {

    private final JavaMailSender mailSender;

    public SecureNotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotification(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                "UTF-8"
        );

        helper.setFrom("notifications@example.org");
        helper.setTo(recipient);
        helper.setSubject("Account notification");
        helper.setText(
                "A change in your account has been recorded.",
                false
        );

        mailSender.send(message);
    }
}
~~~

The business layer does not need to invoke STARTTLS directly. The Jakarta Mail transport handles the handshake according to the **mail.smtp.\*** properties.

### 9.1. What the service does not automatically guarantee

Merely observing **mailSender.send(message)** succeed does not prove:

- All subsequent relays use TLS.
- The message is encrypted end-to-end.
- The message reached the inbox.
- The recipient has read the email.
- Email content is safe if the mailbox is compromised.

Those are separate requirements with different monitoring and protection mechanisms.

## 10. SMTP AUTH should occur after TLS is established

A dangerous design flaw is allowing username/password to be sent over an unencrypted connection.

For servers supporting STARTTLS, the proper sequence is:

~~~text
TCP connect
    |
    v
EHLO
    |
    v
STARTTLS
    |
    v
TLS handshake + server certificate verification
    |
    v
EHLO again
    |
    v
SMTP AUTH
    |
    v
MAIL FROM / RCPT TO / DATA
~~~

When using implicit TLS, the handshake is already complete before the server greeting and AUTH.

### 10.1. SMTP AUTH is not encryption

**mail.smtp.auth=true** only requests SMTP authentication according to server capabilities. It **does not automatically enable TLS**.

A configuration containing username/password and AUTH without policy-enforced TLS may cause credentials to be transmitted in an unprotected session, depending on the server and mechanism. To avoid mistakes, require TLS on the client and use a submission server that supports security.

### 10.2. Does the AUTH mechanism matter?

SMTP has several authentication mechanisms, which may include PLAIN, LOGIN, or OAuth-based mechanisms. Some mechanisms transmit authentication data in a representational encoding rather than strong encryption; therefore, TLS is still required for the connection.

**Do not treat Base64 in AUTH PLAIN/LOGIN as a security encryption layer.**

### 10.3. TLS and OAuth2 are two different layers

An OAuth2 access token restricts how the client proves access authorization, while TLS protects the token in transit. Expired tokens or wrong scopes must be handled at the authentication layer; disabling TLS will not fix those errors.

## 11. Certificates and trust chains: is the server trustworthy?

During the TLS handshake, the server sends its certificate chain for the client to verify. The JVM typically uses the Java TLS stack and trust material appropriate to the deployment environment.

Checks typically include:

- The certificate is not expired.
- The chain leads to a trusted certificate authority.
- Signatures and the chain are valid.
- The hostname the application connects to matches the identity in the certificate.
- The TLS protocol/cipher is supported by both sides.
- Additional checks according to runtime configuration or deployment policy.

### 11.1. A valid trust chain does not mean the hostname is right

Suppose a certificate is issued by a valid CA, but its hostname is:

~~~text
mail-other.example.org
~~~

while the application connects to:

~~~text
smtp.example.org
~~~

Without hostname verification, the application might accept a connection to an endpoint presenting a certificate belonging to a different name. Therefore, server identity verification must be enabled.

### 11.2. Enabling hostname verification in Jakarta Mail

Property:

~~~properties
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

In Java:

~~~java
properties.put(
        "mail.smtp.ssl.checkserveridentity",
        "true"
);
~~~

Do not rely on an unverified default across your deployed mail provider/JDK version. Enabling it explicitly makes the hostname verification requirement clear.

### 11.3. Certificate SAN and hostnames

Modern certificates usually specify valid DNS names in the **Subject Alternative Name (SAN)**. The SMTP endpoint the application connects to must have a name matching the certificate.

If the application uses a private alias or load balancer, ensure that the alias is covered by the certificate. Never fix a mismatch error by disabling hostname verification.

### 11.4. Private CAs in enterprise environments

An internal SMTP server may use a certificate issued by an internal CA. If the JVM does not yet trust that CA, the handshake may fail with a PKIX or certificate path validation error.

Proper resolution steps:

1. Verify that the certificate and hostname are managed by your organization.
2. Add the internal CA to an appropriate truststore according to policy.
3. Configure the JVM or a trusted SSL context.
4. Keep hostname verification enabled.
5. Re-test against the actual endpoint.

Avoid updating the JVM-wide truststore uncontrollably if the application also connects to many other systems; limit the trust scope where architecture permits.

## 12. Dangerous TLS configurations to avoid

### 12.1. Trusting every server

An insecure configuration:

~~~properties
spring.mail.properties[mail.smtp.ssl.trust]=*
~~~

This provider-specific property can cause the client to broadly trust hosts instead of verifying the trust chain normally. This weakens protection against server spoofing.

Do not use **trust=*** as a quick fix for PKIX errors in production.

### 12.2. Disabling hostname verification

An unsuitable configuration for environments requiring security:

~~~properties
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=false
~~~

Even if the certificate chain is accepted, the server identity may not be checked against the expected hostname.

### 12.3. Disabling STARTTLS required just to “make sending work”

~~~properties
spring.mail.properties[mail.smtp.starttls.required]=false
~~~

If the business requirement is to send only over TLS, disabling required may cause the system to fall back to an unencrypted connection when the server does not support STARTTLS.

When the server has a TLS issue, investigate the endpoint, certificate, configuration, and network rather than silently dropping the security requirement.

### 12.4. Disabling certificate checks in a custom SSLSocketFactory

A custom TrustManager that accepts every certificate can result in an encrypted TLS connection that does not prove the server's identity. An attacker could present an arbitrary certificate to spoof the endpoint.

If a custom truststore or TLS policy is required, configure the trust layer properly—never write an “always true” TrustManager.

### 12.5. Enabling debug logs that expose secrets

Protocol debugging may expose metadata or authentication credentials, depending on implementation and configuration. Do not leave detailed debugging enabled uncontrollably in production.

## 13. STARTTLS downgrade attacks and fail-closed behavior

Because STARTTLS is advertised via EHLO before TLS begins, an actor capable of modifying the connection can intentionally interfere with the negotiation.

Conceptual example:

~~~text
Client                    Attacker                 Server
  |                         |                       |
  |------ EHLO ------------>|------ EHLO ---------->|
  |                         |<--- 250-STARTTLS -----|
  |<--- 250 (TLS stripped) -|                       |
  |                         |                       |
  | Client assumes server does not support STARTTLS |
~~~

If the application only enables **starttls.enable**, the client may proceed in plaintext when it does not see the extension.

If the application enables **starttls.required=true**, it must abort instead of falling back to an unencrypted connection.

### 13.1. When is fail-closed mandatory?

For applications sending via an SMTP submission account, especially with authentication credentials or sensitive content, policy should typically require:

- STARTTLS or implicit TLS according to the endpoint.
- Certificate validation.
- Hostname verification.
- No AUTH/DATA sent if mandatory security has not been established.

### 13.2. What is the trade-off of fail-closed?

Yes, there is one. When the server's TLS fails, email sending may temporarily halt. This is an intentional trade-off between **availability** and **minimum security requirements**.

The application should move the task to retry/backoff or an attention-needed state, rather than secretly downgrading the connection.

## 14. TLS versions and cipher suites

TLS has multiple versions. In modern systems, **TLS 1.2 and TLS 1.3** are generally the appropriate deployment targets, depending on the JVM, SMTP server, and organizational policy.

Older versions such as TLS 1.0/1.1 should not be actively enabled for new connections unless there is a specific legacy requirement that has undergone risk assessment.

### 14.1. How do the JVM and Jakarta Mail share responsibility?

- **JDK/JSSE:** implements the TLS protocol, cryptography, certificate processing, and truststore.
- **Jakarta Mail provider:** creates the SMTP connection, uses the TLS stack, and reads properties.
- **Spring Mail:** provides JavaMailSender/JavaMailSenderImpl and configuration.
- **SMTP server:** advertises and supports the actual protocols/ciphers.

You cannot force a server to support TLS 1.3 solely via a client-side property.

### 14.2. Specifying protocols only when truly needed

Some providers support the property:

~~~properties
spring.mail.properties[mail.smtp.ssl.protocols]=TLSv1.3 TLSv1.2
~~~

This property typically takes a space-separated list of protocols. Use it only when a specific policy is needed and support has been verified across the JDK, provider, and server. An improper configuration can cause the handshake to fail even when the server has another secure TLS configuration available.

If your organization has a TLS security baseline, prefer applying it consistently across the JVM/runtime and testing compatibility per environment.

### 14.3. Cipher suites

Supported ciphers depend on the JDK and server. If you need to restrict cipher suites, use configurations supported by the provider/JDK and approved by your security team.

Do not copy a cipher list from another system without checking the Java version, disabled algorithms, and SMTP server capabilities.

## 15. Difference between TLS handshake failure and SMTP AUTH failure

These two types of errors are often confused with each other.

### 15.1. TLS handshake failure

Example cause chain:

~~~text
MailSendException
    |
    v
MessagingException / SSLException
    |
    v
SSLHandshakeException
    |
    +-- PKIX path building failed
    +-- Certificate expired
    +-- Hostname verification failed
    +-- No appropriate protocol
~~~

This is an error during the secure connection setup step. Do not immediately try changing the password just because SMTP send failed.

### 15.2. SMTP AUTH failure

Example:

~~~text
MailAuthenticationException
    |
    v
AuthenticationFailedException
    |
    v
535 5.7.8 Authentication credentials invalid
~~~

TLS may have succeeded, yet the credentials are wrong or the account lacks permission.

### 15.3. Quick comparison table

| Symptom | Primary suspect | What to check |
| --- | --- | --- |
| PKIX path building failed | Trust chain/CA | Certificate chain, truststore |
| No subject alternative name matching | Hostname mismatch | SAN, connected host |
| Handshake failure | TLS protocol/cipher/certificate | JDK, server capability, TLS baseline |
| 535 authentication failed | Credentials/AUTH permission | Username, token, SMTP AUTH policy |
| STARTTLS is required but host does not support it | Mode/endpoint/advertisement | Port, EHLO capabilities, provider |
| Connection reset on port 465 | Possibly wrong mode/port or network | Implicit TLS endpoint, firewall |
| Timeout on connect | Network/route/firewall/provider | Host, port, DNS, timeout |
| Timeout after DATA | Uncertain send outcome | SMTP phase, retry/idempotency |

## 16. Common mistakes when configuring ports and TLS modes

### 16.1. Port 587 with implicit TLS enabled

Example mismatch with a typical STARTTLS endpoint:

~~~properties
spring.mail.port=587
spring.mail.properties[mail.smtp.ssl.enable]=true
~~~

The client attempts TLS from the very beginning while the server is preparing to return a plaintext SMTP greeting. The result may be a timeout or SSLException.

Fix this by using STARTTLS on that endpoint, if confirmed by the provider.

### 16.2. Port 465 with only STARTTLS enabled

If the server expects TLS from the start while the client waits for a plaintext SMTP greeting, the connection may hang or be closed.

Configure implicit TLS instead of STARTTLS for a 465 endpoint.

### 16.3. Only enabling mail.smtp.auth

~~~properties
spring.mail.properties[mail.smtp.auth]=true
~~~

This line does not require TLS. With providers that mandate STARTTLS, missing starttls properties may cause AUTH failures or lead to a connection that violates policy.

### 16.4. Only enabling starttls.enable

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
~~~

This may not satisfy the requirement of “do not send when TLS is unavailable”. When fail-closed is needed, enable required.

### 16.5. Using an internal SMTP host that does not match the certificate

For example, connecting by IP or a short alias when the certificate only contains the full DNS name can cause hostname verification errors.

The solution is to use a hostname covered by the certificate or issue a proper certificate—do not disable checkserveridentity.

## 17. Timeouts, retry limits, and reliability

A TLS/SMTP connection can become slow or hang at different stages. Setting finite timeouts is critical in production:

~~~properties
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

These numbers are just examples. Tune them based on provider response times, MIME size, network quality, and SLAs.

### 17.1. Why are there three timeouts?

- **connectiontimeout:** waiting to establish a connection to the server.
- **timeout:** waiting to read data/responses from the server.
- **writetimeout:** waiting to write bytes to the connection.

A read timeout after DATA can occur after the SMTP server has already accepted the message. Therefore, you cannot assume every timeout is a guaranteed unsent failure.

### 17.2. Retries should not downgrade TLS

If an error occurs due to an invalid certificate or unsupported STARTTLS, retrying by disabling TLS can violate security requirements.

Classify errors accordingly:

| Error | Appropriate action |
| --- | --- |
| Temporary network timeout before DATA | Retry with backoff and limit |
| Server temporarily overloaded | Wait and retry according to policy |
| Certificate expired or hostname mismatch | Stop, fix configuration/certificate |
| STARTTLS unavailable when required | Stop and inspect endpoint/policy |
| AUTH credentials invalid | Stop blind retries, fix credentials |
| Unknown outcome after DATA | Reconcile or retry cautiously due to duplicate risk |

### 17.3. Do not send SMTP inside long-running database transactions

SMTP I/O can take several seconds. If you call mailSender.send() inside a `@Transactional` method, database connections/locks may be held while negotiating TLS or waiting on SMTP.

For post-commit notifications, use a service invoked after the transaction, `TransactionalEventListener(AFTER_COMMIT)`, or a transactional outbox when high resilience is required. This reduces coupling between SMTP/TLS latency and business transactions.

## 18. Safe TLS debugging

When investigating errors, different logging layers provide different information:

1. **Application logs:** event ID, account reference, host/port/mode, exception type.
2. **Jakarta Mail protocol debug:** SMTP commands and responses, when enabled in a controlled manner.
3. **JVM SSL debug:** TLS handshake, certificate, and protocol details, which should be restricted to diagnostic environments.

### 18.1. Jakarta Mail debug

Development environment example:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": "true"
~~~

Use debug for a limited time; review logging policies because the transcript can expose metadata such as sender, recipient, server capabilities, or other information.

### 18.2. JSSE debug

The JVM can support the system property:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

Depending on the JDK, it helps inspect handshake details, certificates, and protocol negotiation.

**Do not enable verbose handshake and protocol logs by default in production.** Logs must have restricted access and an appropriate retention period.

### 18.3. Do not log passwords or AUTH payloads

Do not log:

- SMTP passwords.
- OAuth access/refresh tokens.
- Raw SMTP AUTH data.
- Email bodies or attachments just to prove TLS.
- Full recipient addresses when unnecessary.

In many cases, the error code, hostname, port, TLS mode, and correlation ID are enough to guide the investigation.

## 19. Example of diagnosing STARTTLS with network tools

When authorized to test the endpoint, you can use TLS tools to verify whether the server advertises STARTTLS and which certificate it presents.

Illustrative example with OpenSSL:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.org:587 \
  -servername smtp.example.org \
  -verify_hostname smtp.example.org
~~~

For implicit TLS:

~~~bash
openssl s_client \
  -connect smtp.example.org:465 \
  -servername smtp.example.org \
  -verify_hostname smtp.example.org
~~~

Read the full verification and chain output rather than just checking whether the TLS handshake succeeded. Supported options may depend on the OpenSSL version.

These commands are for **diagnosing the TLS endpoint**; they do not mean JavaMailSender uses OpenSSL. Java applications use the Java runtime's TLS stack and truststore.

### 19.1. What should you observe?

- Did it connect to the right host/port?
- Was STARTTLS advertised on the 587 endpoint?
- Did the TLS handshake complete?
- Is the certificate chain valid?
- Does the SAN contain the expected hostname?
- Are the negotiated TLS version/cipher compliant with policy?
- Does the endpoint require authentication after TLS?

### 19.2. Why does OpenSSL succeed while Java still reports PKIX?

OpenSSL and the JVM can use different trust stores. A CA trusted by OpenSSL is not necessarily present in the application's Java truststore.

Verify the JDK, container image, runtime options, and actual truststore used by the application.

## 20. Testing TLS configuration in a Spring environment

Do not rely solely on the application starting up successfully. Some mail configurations are only checked when a connection is actually opened.

### 20.1. Testing with a dedicated test SMTP server

You can use a TLS-capable SMTP test server with clear certificates and policies to verify:

- STARTTLS required and server has STARTTLS → connection succeeds.
- STARTTLS required but server does not support it → sending fails.
- Untrusted certificate → handshake must fail.
- Hostname mismatch → connection must fail when checkserveridentity is enabled.
- Implicit TLS endpoint on 465 → connects in the right mode.
- Wrong port/mode → reports an appropriate error without falling back to plaintext.
- Wrong credentials → AUTH fails even though TLS succeeds.

Do not intentionally configure fake certificates or perform repeated failed logins against production SMTP.

### 20.2. Testing fail-closed

An important test is having the server not advertise STARTTLS and verifying that a client configured with **required=true** does not send content over plaintext.

This check reflects security requirements better than a test that only verifies “mail can be sent”.

### 20.3. Testing hostname verification

Test a certificate with a valid chain whose SAN does not match the hostname. The client must reject it if policy requires hostname verification.

Do not treat that connection as successful simply because the certificate was issued by a valid CA.

### 20.4. Testing timeouts and retries

If a test makes the server stop responding, verify that workers do not hold resources indefinitely, task state is recorded, and retries are bounded. If the error occurs after DATA, the outcome may be indeterminate and carries duplicate-sending risk.

## 21. Additional security measures beyond the TLS client

TLS is the foundation for protecting connections, but email-sending systems also need other layers of defense.

### 21.1. SPF, DKIM, and DMARC

These mechanisms relate to sender authentication and domain anti-spoofing, not SMTP session encryption.

| Mechanism | Primary role |
| --- | --- |
| **SPF** | Specifies which hosts are authorized to send on behalf of a domain in the SMTP context |
| **DKIM** | Attaches a signature to the message to verify the signing domain and integrity of signed parts |
| **DMARC** | Policy/evaluation of SPF/DKIM alignment with the From domain |
| **TLS** | Protects a single transport connection |

An email with valid DKIM does not prove the sending hop used TLS. Likewise, a TLS-protected SMTP session does not prove the From domain has valid DKIM/SPF/DMARC.

### 21.2. MTA-STS and DANE

In email exchange between mail transfer agents, **MTA-STS** and **DANE** are mechanisms that can support TLS protection/verification policies for eligible delivery hops.

They do not replace the application's JavaMailSender configuration when sending to a submission server over 587 or 465. Their scope and deployment requirements lie in the mail transport/receiving server infrastructure, not simply in Spring Mail code.

### 21.3. Protecting credentials

You should use:

- A secrets manager or controlled environment variables.
- Least-privilege permissions for SMTP accounts.
- Credential rotation according to policy.
- Restrictions on allowed domains/From identities.
- Monitoring for abnormal AUTH errors.
- Never placing secrets in repositories, tickets, or logs.

### 21.4. Protecting sensitive content

TLS does not prevent recipients from forwarding emails, mailbox compromises, or providers storing content. For highly sensitive documents, you may need to send authenticated, time-limited download links or use a dedicated content encryption solution.

## 22. Configuration errors and remediation guide

| Symptom | Common cause | Remediation |
| --- | --- | --- |
| Cannot connect to smtp.example.org:587 | Wrong DNS, firewall, host, or port | Check endpoint and network route |
| SSLException when using 587 | Implicit TLS enabled on a STARTTLS port | Choose STARTTLS mode |
| Timeout when using 465 | Client waits for plaintext greeting while server expects TLS | Enable implicit TLS |
| STARTTLS required but server does not support it | Wrong endpoint or server lacks STARTTLS | Choose the right endpoint, keep fail-closed |
| PKIX path building failed | Untrusted CA/chain | Fix chain/truststore |
| Hostname verification failed | Host does not match SAN | Use matching DNS/certificate |
| Certificate expired | Server certificate expired | Renew/replace certificate |
| No appropriate TLS protocol | No overlapping version/cipher | Check JDK and server policy |
| AUTH 535 after TLS | Wrong credentials or SMTP AUTH policy | Fix account, do not disable TLS |
| AUTH not available before STARTTLS | Connection not upgraded to TLS yet | Enable STARTTLS required |
| Mail sends in dev, fails in container | Different truststore/JDK/network | Check actual runtime environment |
| SMTP send timeout | Slow server/network or phase error | Classify timeout and retry with control |
| Email bounces after successful send | Downstream delivery failed | Track bounces separately, do not blame TLS |
| Sends successfully, but compliance mandates TLS | Only starttls.enable was set | Enable required and hostname verification |

## 23. Frequently asked questions

**1. What is TLS used for in SMTP?**

It encrypts and protects the integrity of data on the connection between the SMTP client and server, while supporting server identity verification via certificates.

**2. How does STARTTLS differ from SSL/TLS on port 465?**

STARTTLS upgrades an initial SMTP session to TLS. Implicit TLS starts the TLS handshake immediately after the TCP connection. The two endpoints follow different flows.

**3. Is port 587 always STARTTLS?**

Port 587 is commonly used for submission with STARTTLS, but you must follow the provider's configuration. The port does not replace verifying the actual mode.

**4. When using 465, must mail.smtp.ssl.enable=true always be configured?**

If JavaMailSender uses the smtp protocol and the endpoint requires implicit TLS, this is the typical configuration to start TLS from the beginning. Check the provider/version and endpoint documentation.

**5. Is starttls.enable=true enough for production?**

Not if policy mandates TLS. Use **starttls.required=true** and **ssl.checkserveridentity=true** when connecting to a STARTTLS endpoint.

**6. Why is checkserveridentity needed?**

To verify that the TLS server has a certificate matching the hostname the application intends to connect to. Trusting only the CA chain without checking the name may be insufficient against endpoint spoofing.

**7. Can mail.smtp.ssl.trust=* be used to fix PKIX?**

No, not in production. Verify the chain and configure the appropriate CA/truststore rather than trusting every server.

**8. Does TLS make email end-to-end encrypted?**

No. TLS protects a single connection. Intermediate mail servers can decrypt and process the message. End-to-end encryption is a separate requirement.

**9. Does TLS replace SMTP AUTH?**

No. TLS protects the connection; AUTH authenticates the sending account. Both are needed when the provider requires authenticated submission.

**10. Does BASE64 protect SMTP passwords or body content?**

No. Base64 is encoding, not encryption. STARTTLS/implicit TLS protects the connection when properly configured and verified.

**11. Why does the server return 535 even though TLS succeeded?**

535 usually relates to credentials/AUTH permissions. The TLS handshake and SMTP AUTH are two independent steps.

**12. Why does OpenSSL verify succeed while Java reports an error?**

The two environments may use different truststores and TLS policies. Check the JDK, container, CA, and hostname that Java actually uses.

**13. Can only TLS 1.3 be enforced?**

Yes, if the provider/JDK supports that configuration, though the server must support it as well. Do not enforce it arbitrarily and cause sending disruptions; apply a baseline and test it.

**14. Should retries be performed when a handshake fails?**

It depends on the cause. Transient network errors can be retried. Expired certificates, hostname mismatches, or wrong modes must be fixed rather than retried blindly.

**15. Does a timeout when sending SMTP guarantee the email was not sent?**

No. If a timeout occurs after DATA, the server may have already accepted the message. Retries must account for the risk of duplicate emails.

**16. Does Spring Mail have a separate sendTls() API?**

Normally there is no need. TLS configuration resides in the transport's JavaMail properties. The service still calls JavaMailSender.send(...).

**17. Are SSL and TLS always two separate security options in configuration?**

The **ssl** property name is historical library naming. In modern deployments, it normally configures TLS via the Java SSL/TLS stack; older SSL protocols are not recommended.

**18. Do DKIM/SPF/DMARC prove an email was sent over TLS?**

No. They address sender authentication and domain alignment, not encryption across the entire delivery path.

## 24. TLS implementation workflow for Spring Mail

A practical workflow:

1. **Choose the SMTP provider and endpoint**: determine the host, port, and TLS mode from provider documentation.
2. **Decide between STARTTLS or implicit TLS**: typically 587/STARTTLS or 465/implicit TLS.
3. **Require a secure connection**: STARTTLS should use enable + required if policy mandates TLS; implicit TLS uses ssl.enable.
4. **Enable hostname verification**: configure ssl.checkserveridentity=true.
5. **Ensure valid certificates**: check SAN, trust chain, expiration date, and JVM truststore.
6. **Configure AUTH securely**: retrieve secrets from a secrets management channel; do not send credentials over connections that fail policy.
7. **Set finite timeouts**: connection/read/write timeouts.
8. **Test fail-closed**: a server missing STARTTLS or presenting an invalid certificate must be rejected.
9. **Test AUTH errors separately**: authentication failures must not be worked around by disabling TLS.
10. **Monitor operations**: structured logs, alerts, conditional retries, and handling indeterminate outcomes.
11. **Protect layers outside TLS**: SPF/DKIM/DMARC, secret rotation, data controls, and authorization.
12. **Test in real runtime**: production JDK, container, host, port, and truststore may differ from development environments.

## 25. Key takeaways on TLS in mail server connections

**TLS is the foundation for protecting SMTP connections, not end-to-end email security.** In Spring Framework Mail, applications typically use **STARTTLS on port 587** or **implicit TLS on port 465** per provider documentation. STARTTLS upgrades the connection after EHLO; implicit TLS negotiates security from the start. Both require proper certificate and hostname verification to prevent server spoofing.

With STARTTLS, **mail.smtp.starttls.enable=true** only permits the upgrade. If policy mandates encryption, add **mail.smtp.starttls.required=true** to prevent plaintext fallback, and enable **mail.smtp.ssl.checkserveridentity=true**. With implicit TLS, use **mail.smtp.ssl.enable=true** and hostname verification on the corresponding endpoint. Do not stack both modes for one server just to increase security.

Never use **mail.smtp.ssl.trust=***, disable hostname verification, or drop TLS to mask certificate or AUTH errors. Distinguish connection, handshake, and credential failures; set timeouts, persist send state, retry conditionally, and treat timeouts after DATA cautiously because the SMTP outcome may be indeterminate.

Finally, distinguish between **a TLS-protected SMTP connection**, **the provider accepting the message**, **the email being delivered**, and **the recipient reading the message**. These are independent milestones. Proper TLS configuration protects the transport path without conflating it with every security and reliability requirement of an email system.
