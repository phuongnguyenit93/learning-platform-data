# STARTTLS and SMTPS

## 1. The role of TLS when sending email with Spring Framework Mail

In Java applications using **Spring Framework Mail**, **JavaMailSender** typically sends email to an SMTP server or email service provider (ESP). Before the server accepts the email, the application may need to exchange sensitive data: username, authentication credentials, sender/recipient addresses, subject, and MIME content. If the connection session is unprotected, data is at risk of being observed or tampered with in transit.

**TLS (Transport Layer Security)** protects the connection session between the **Spring application** and the **connected SMTP server** using encryption and server authentication via certificates. In SMTP, two common ways to establish TLS are:

- **STARTTLS (explicit TLS):** opens an initial SMTP connection, requests upgrading the current session to TLS, and then continues SMTP communication inside the encrypted connection.
- **SMTPS / implicit TLS:** establishes TLS as soon as the TCP connection is opened, before exchanging normal SMTP commands.

Both methods can protect mail delivery if configured properly. The main difference lies in **when TLS begins and the handshake sequence**, not that STARTTLS uses a weaker algorithm than SMTPS.

In Spring Mail, choosing the TLS mode is a configuration of the **Jakarta Mail SMTP transport** used by **JavaMailSenderImpl**. It does not change how subjects, HTML, or attachments are written.

## 2. Protection scope: TLS between the application and the SMTP relay

Distinguish between protecting the SMTP submission session and protecting the email across its entire journey:

~~~text
Spring application
        |
        |  STARTTLS or implicit TLS
        |  (connection controlled by the application)
        v
Submission SMTP server / ESP
        |
        |  One or more SMTP relays
        |  TLS depends on each hop and policy
        v
Receiving SMTP server
        |
        v
Recipient mailbox / mail client
~~~

STARTTLS or SMTPS at the application protects the **hop from Spring to the configured SMTP server**. They **do not automatically turn an email into an end-to-end encrypted message**. After receiving it, the SMTP provider may process the content and forward it through other servers according to email system mechanisms.

If content confidentiality from sender to recipient is required, consider a dedicated solution such as **S/MIME**, **OpenPGP**, or delivering sensitive content via an authenticated landing page. TLS for SMTP submission does not replace those measures.

## 3. How does STARTTLS work?

With **STARTTLS**, the application connects to an SMTP endpoint that supports TLS upgrades. Typical flow on port 587:

~~~text
Spring / Jakarta Mail                 SMTP server
       |                                   |
       | -------- TCP connect ----------> |
       | <-------- 220 greeting ---------- |
       | -------- EHLO ------------------> |
       | <----- 250-STARTTLS ... --------- |
       | -------- STARTTLS --------------> |
       | <-------- 220 Ready ------------ |
       | ======== TLS handshake ======== |
       | ======== Encrypted SMTP ======= |
       | -------- EHLO (again) ---------> |
       | <----- ESMTP capabilities ------ |
       | -------- AUTH (if required) ---> |
       | -------- MAIL FROM / RCPT TO --> |
       | -------- DATA -----------------> |
       | <-------- SMTP response -------- |
       |                                   |
~~~

Main steps:

1. **Open TCP:** the client connects to the SMTP host and port.
2. **Receive greeting:** the server typically sends SMTP code 220.
3. **EHLO:** the client discovers capabilities advertised by the server, including STARTTLS if supported.
4. **STARTTLS:** the client requests an upgrade; the server accepts with a 220 response.
5. **TLS handshake:** both sides negotiate TLS parameters, the server presents its certificate, and the client verifies it according to configuration.
6. **EHLO again:** after TLS is established, the client sends EHLO to receive capabilities applicable to the secured session.
7. **AUTH and content:** the client authenticates if required, then sends the SMTP envelope and MIME message.

**Important point:** before the STARTTLS command, the initial greeting and first EHLO are unencrypted. After a successful upgrade, AUTH and message content must be exchanged over the TLS channel if the application requires secure submission.

### Why must EHLO be sent again?

Once TLS is enabled, the server's capabilities may change. For example, an AUTH mechanism might only be advertised after the connection is encrypted. This is why SMTP clients typically re-issue EHLO rather than continuing to use capability info from before STARTTLS.

## 4. How does SMTPS (implicit TLS) work?

With **SMTPS**, port 465 is commonly used for mail submission over implicit TLS. The client and server establish TLS **before** exchanging the SMTP greeting and commands:

~~~text
Spring / Jakarta Mail                 SMTP server
       |                                   |
       | -------- TCP connect ----------> |
       | ======== TLS handshake ======== |
       | ======== Encrypted channel ===== |
       | <-------- 220 greeting ---------- |
       | -------- EHLO ------------------> |
       | <----- ESMTP capabilities ------ |
       | -------- AUTH (if required) ---> |
       | -------- MAIL FROM / RCPT TO --> |
       | -------- DATA -----------------> |
       | <-------- SMTP response -------- |
       |                                   |
~~~

There is no **STARTTLS** upgrade command because TLS is active from the beginning. The client requires the server to speak TLS immediately after TCP connect.

The name **SMTPS** is frequently used in operational communication. For modern SMTP submission, the accurate term is **implicit TLS**: SMTP runs inside a TLS connection established immediately.

### Common errors caused by using the wrong mode

- Client enables implicit TLS on an endpoint that only accepts SMTP followed by STARTTLS: the TLS handshake may fail or time out.
- Client waits for a plaintext greeting on an endpoint requiring implicit TLS: both sides may wait for each other until timeout.
- Client enables STARTTLS, but the server does not advertise the feature and configuration does not mandate TLS: mail risks being sent over an unencrypted connection.

Do not fix these errors by disabling certificate verification or increasing timeouts indefinitely; configure the correct **host, port, and TLS mode**.

## 5. How do STARTTLS and SMTPS differ?

| Criterion | STARTTLS | SMTPS / implicit TLS |
|---|---|---|
| When TLS starts | After greeting, EHLO, and STARTTLS command | Immediately after TCP connect |
| Common submission port | **587** | **465** |
| STARTTLS command | Yes | Not needed |
| Initial SMTP greeting | Before TLS | After TLS |
| Primary Jakarta Mail setting | **mail.smtp.starttls.enable** | **mail.smtp.ssl.enable** |
| Mechanism enforcing security | Enable **starttls.required** | TLS must handshake before speaking SMTP |
| Certificate verification | Required | Required |
| Encrypts content/AUTH | Yes, after successful upgrade | Yes, from the start of the SMTP session |
| Common configuration issue | Opportunistic fallback if TLS is not required | Wrong port or wrong TLS mode |

Both approaches use TLS to protect the session if the handshake and server verification succeed. **There is no universal rule that SMTP over port 465 is always safer than port 587 or vice versa.** TLS policy, server authentication, allowed algorithms, and server configuration determine the actual level of protection.

## 6. Common SMTP ports

| Port | Common purpose | Notes |
|---|---|---|
| **587** | Message submission | Typically uses SMTP + STARTTLS |
| **465** | Message submission with implicit TLS | TLS immediately after TCP connect |
| **25** | Relaying between MTAs / SMTP relay | May support STARTTLS; outbound is often restricted in some clouds |
| **2525** | Alternative port used by some ESPs | TLS mode depends on the provider |

Only choose a port that the SMTP provider explicitly publishes. Do not assume that any given host opens both 465 and 587.

### When to choose 587 vs. 465?

If the provider supports both, you can choose based on organizational policy and deployment environment. When using 587, **require STARTTLS** if email submission must be encrypted; when using 465, enable **implicit TLS**. If a port is blocked, check firewall/egress policies or provider documentation instead of arbitrarily switching modes.

## 7. Configuring STARTTLS with Spring Boot

When using **spring-boot-starter-mail**, Spring Boot can configure **JavaMailSender** from **spring.mail** properties.

Illustrative Gradle dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Example **application.yml** for SMTP submission over STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
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
          timeout: 10000
          writetimeout: 10000
~~~

Key meanings:

- **host / port:** the provider's SMTP endpoint.
- **username / password:** authentication credentials; should come from environment variables or a secret manager.
- **auth: true:** requests SMTP authentication when the provider requires it.
- **starttls.enable: true:** lets Jakarta Mail attempt a TLS upgrade via STARTTLS.
- **starttls.required: true:** stops sending if STARTTLS is unsupported or cannot be established.
- **ssl.checkserveridentity: true:** requires checking the hostname against the TLS certificate.
- **connectiontimeout / timeout / writetimeout:** connection, read, and write time limits (milliseconds).

Host, username, and password are illustrative values; do not use **smtp.example.com** as a real endpoint. Credentials must never be committed to the repository.

### Why set both enable and required?

These are two distinct properties:

~~~properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
~~~

**enable** permits the upgrade process. **required** mandates that the upgrade succeed. If only enable is turned on, depending on the situation and server/client behavior, the application may continue without STARTTLS when the server does not support it. For applications needing to protect credentials and submission content, setting **required=true** is the safer principle.

## 8. Configuring SMTPS (implicit TLS) with Spring Boot

Example **application.yml** for port 465:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

The decisive setting is:

~~~properties
mail.smtp.ssl.enable=true
~~~

For **JavaMailSenderImpl** using the default SMTP transport, this property requests implicit TLS. Typically **you do not need to change the protocol to “smtps”** just to use TLS on port 465 once **mail.smtp.ssl.enable=true** is configured.

In this implicit TLS configuration, there is no need to enable STARTTLS because the session is already encrypted before the SMTP greeting. When using multiple profiles, ensure the 465 configuration does not accidentally retain STARTTLS properties that conflict with the intent.

### Properties to remember

| Property | STARTTLS, typically on 587 | Implicit TLS, typically on 465 |
|---|---|---|
| mail.smtp.auth | true if server requires it | true if server requires it |
| mail.smtp.starttls.enable | true | Not needed |
| mail.smtp.starttls.required | true when TLS is required | Not needed |
| mail.smtp.ssl.enable | Do not enable for normal STARTTLS | true |
| mail.smtp.ssl.checkserveridentity | true | true |
| mail.smtp.connectiontimeout | Should set a limit | Should set a limit |
| mail.smtp.timeout | Should set a limit | Should set a limit |
| mail.smtp.writetimeout | Should set a limit | Should set a limit |

## 9. Configuring JavaMailSenderImpl without auto-configuration

In a plain Spring Framework application or when creating multiple senders manually, you can configure **JavaMailSenderImpl** directly. It is the implementation class of **JavaMailSender**, using Jakarta Mail underneath.

Example bean using STARTTLS:

~~~java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    public JavaMailSender mailSender(MailCredentials credentials) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(credentials.host());
        sender.setPort(587);
        sender.setUsername(credentials.username());
        sender.setPassword(credentials.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

**MailCredentials** is an application-defined configuration object, such as a record receiving data from a secret manager or **@ConfigurationProperties**. The snippet assumes this object is registered as a bean with valid data. Never hard-code real credentials.

To switch the example above to implicit TLS:

~~~java
sender.setPort(465);

Properties props = sender.getJavaMailProperties();
props.put("mail.smtp.auth", "true");
props.put("mail.smtp.ssl.enable", "true");
props.put("mail.smtp.ssl.checkserveridentity", "true");
props.put("mail.smtp.connectiontimeout", "5000");
props.put("mail.smtp.timeout", "10000");
props.put("mail.smtp.writetimeout", "10000");
~~~

Choose **one mode that matches the endpoint**. Do not copy all properties of both modes simultaneously and expect Jakarta Mail to decide the right mode on its own.

### Single configuration or multiple senders?

If an application has separate transactional and marketing senders, each bean can use a different hostname, port, and credentials:

~~~text
TransactionalMailService
           |
           v
 @Qualifier("transactionalSender")
           |
           +--> host: smtp.transactional.example, port: 587, STARTTLS

CampaignMailService
           |
           v
 @Qualifier("campaignSender")
           |
           +--> host: smtp.campaign.example, port: 465, implicit TLS
~~~

Verify the TLS mode **for each bean**, not only the default **spring.mail** configuration.

## 10. Sending a MimeMessage after setting up a secure sender

The application does not need to change content-building APIs when switching between STARTTLS and SMTPS. The difference belongs to the transport layer.

Example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class AccountNotificationService {

    private final JavaMailSender sender;

    public AccountNotificationService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendSecurityNotice(String recipient)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("security@example.com");
        helper.setTo(recipient);
        helper.setSubject("Account security notification");
        helper.setText(
                """
                There has been a security change related to your account.
                View details at https://example.com/account/security
                """,
                """
                <html lang="en">
                  <body>
                    <h1>Account security notification</h1>
                    <p>There has been a security change related to your account.</p>
                    <p><a href="https://example.com/account/security">
                       View details
                    </a></p>
                  </body>
                </html>
                """
        );

        sender.send(message);
    }
}
~~~

This code creates plain text and HTML in **multipart/alternative**. It uses the TLS-configured sender from the previous section. **MimeMessageHelper is not where STARTTLS or SMTPS is chosen**: it prepares addresses, headers, and MIME content.

Security emails should contain only the necessary amount of data. TLS on SMTP submission does not mean the entire delivery path and recipient mailbox are end-to-end encrypted.

## 11. Threat when STARTTLS is not mandatory

STARTTLS has a negotiation step in the initial SMTP session. If the client is only configured to upgrade when the server advertises STARTTLS without **requiring it**, an un-upgraded session may still continue.

Example risky path:

~~~text
Client                               Server
  | ---- EHLO ---------------------> |
  | <--- 250 capabilities --------- |
  |       no STARTTLS                |
  |                                  |
  | ---- continue plaintext SMTP --> |  <- risk
~~~

Reasons STARTTLS is not advertised could be an unsupported server, server misconfiguration, an intermediary device altering data, or connecting to the wrong endpoint. Do not assume this is normal.

For submission applications requiring security:

~~~properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
~~~

Setting **required=true** makes the application fail rather than silently proceeding unencrypted when STARTTLS cannot be established. This is the mechanism preventing **fallback to plaintext** on the submission hop.

### What is STARTTLS stripping?

An interceptor on the wire before TLS may try to prevent the client from seeing the STARTTLS capability. If the client is allowed to proceed without encryption, transmitted data can be exposed. When STARTTLS is required, a stripping attempt causes delivery to fail instead of silently downgrading security.

Requiring STARTTLS does not solve all attacks: the client must still **verify the certificate, hostname, and trustworthiness of the TLS channel**. If any certificate is accepted, an “encrypted” connection is not guaranteed to reach the intended SMTP server.

## 12. TLS certificates and server identity verification

TLS involves two goals that are easily confused:

1. **Transport encryption**, preventing outsiders from easily reading or modifying session content.
2. **Server verification**, letting the client trust that the endpoint it connects to matches the configured hostname.

A TLS session with encryption only and no server identity check can be redirected to a spoofed server.

Important checks:

- The certificate chain is signed by a trusted CA, or issued by an explicitly configured enterprise PKI.
- The certificate has not expired and is within its validity period.
- The SMTP hostname matches a valid name in the certificate, typically in **Subject Alternative Name (SAN)**.
- TLS protocol versions and cipher algorithms are supported by both client/server and permitted by policy.

With the Jakarta Mail SMTP provider, explicitly enable hostname verification:

~~~properties
mail.smtp.ssl.checkserveridentity=true
~~~

This property applies to both STARTTLS and implicit TLS connections when using the **mail.smtp** transport.

### Certificate mismatch scenario

For example, the application connects to:

~~~text
SMTP host: smtp.mail.example.com

Certificate SAN:
  DNS:mail.example.com
~~~

If the certificate does not cover **smtp.mail.example.com**, hostname verification must fail, even if the certificate is valid for **mail.example.com**. Use the hostname published by the SMTP provider that has a matching certificate; never disable the check to keep sending.

## 13. Java truststore and internal certificates

Java uses a set of trusted CA certificates via its truststore/runtime configuration. When an SMTP server uses a valid public certificate, the JDK usually already includes the necessary CA. For an internal SMTP relay using an enterprise CA, the application may need a truststore configured for that CA.

Typical error:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
  unable to find valid certification path to requested target
~~~

Possible causes:

- The server does not send the complete intermediate certificate chain.
- The certificate is signed by a CA that the JDK does not yet trust.
- The container/JDK truststore is missing the internal CA.
- The server/CA changed, but the truststore has not been updated.
- The hostname or certificate does not match the endpoint.

Remediation steps:

1. Inspect the certificate chain actually provided by the server.
2. Verify the CA and domain per documentation or your PKI administrator.
3. Update the server-side chain if an intermediate certificate is missing.
4. If it is an organization-approved internal CA, configure a truststore containing the appropriate CA.
5. Protect the truststore and update it via certificate management procedures.

Do not automatically download a certificate from a failing connection and add it to the trusted store without verifying its identity and fingerprint through a trusted source.

### Why shouldn't you use “trust all”?

A configuration often seen in experimental examples:

~~~properties
mail.smtp.ssl.trust=*
~~~

Accepting every host/certificate this way weakens endpoint authentication and can mask real truststore or certificate errors. **Never use wildcard trust as a production solution.** Likewise, do not disable hostname verification just to force mail through.

## 14. TLS protocol versions and cipher suites

TLS security also depends on which protocol versions and algorithms are permitted. In modern environments, policies generally prefer **TLS 1.2 and TLS 1.3**, depending on JDK compatibility, server support, and organizational requirements.

Jakarta Mail may allow restricting TLS versions using a property such as:

~~~properties
mail.smtp.ssl.protocols=TLSv1.3 TLSv1.2
~~~

This is a syntax example for the SMTP transport; it must be checked against your actual Jakarta Mail version and runtime. If you specify versions that either side does not support, the connection can fail even when the host and credentials are correct.

Do not arbitrarily enable outdated TLS versions just for compatibility with an old relay. Upgrade the relay or agree on an approach approved by your security team.

### Operational notes

- Different JDKs may enable/disable different default protocols and cipher suites.
- Changing JDKs or container images can cause an older endpoint to start failing TLS.
- System-wide configurations can affect multiple TLS clients, not just SMTP.
- Validate TLS policies by testing against the actual server and appropriate certificate chain.

Do not conclude “STARTTLS is broken” solely from an **SSLHandshakeException**; the issue may lie in the certificate, protocol version, truststore, or TLS endpoint.

## 15. SMTP AUTH must be protected by TLS

Many SMTP submission servers require **AUTH** to determine whether an application is authorized to send email. Some AUTH mechanisms can expose credentials if used over an unencrypted channel.

Therefore, for connections with a username/password:

- Choose mandatory STARTTLS on the appropriate endpoint or implicit TLS.
- Verify the server certificate and hostname.
- Use an authentication method supported by the provider and allowed by the organization.
- Never log credentials or AUTH conversations.
- Restrict credential permissions and rotate secrets following procedures.

### AUTH does not replace TLS

**SMTP AUTH** answers the question “Is this application allowed to use the sending service?”. **TLS** protects the transport channel and authenticates the server. Both are required when the provider mandates application authentication over a secure channel.

If AUTH fails after TLS has succeeded, the cause may be credentials, permissions, account policy, or authentication method. **Never switch to plaintext SMTP just to avoid AUTH errors.**

## 16. TLS protects transport, not replacing SPF/DKIM/DMARC

Email security technologies serve different roles:

| Mechanism | Primary objective | What does it protect? |
|---|---|---|
| **STARTTLS / implicit TLS** | Secure the SMTP connection | Transport channel between two SMTP peers in that session |
| **SMTP AUTH** | Authenticate the client using SMTP submission | Permission to use the sending service |
| **SPF** | Publish servers/IPs authorized to send for a domain under SPF | Helps verify the sending domain via the SMTP envelope |
| **DKIM** | Sign selected headers and message content | Verifies signature and integrity per the signing domain |
| **DMARC** | Policy and alignment linking SPF/DKIM with the From domain | Helps the domain owner control handling of spoofed mail |
| **S/MIME / OpenPGP** | Encrypt/sign content at the message layer | End-to-end security when implemented properly |

An email sent over TLS can still land in Spam or be rejected if domain identity, SPF, DKIM, DMARC, content, or reputation is improper. Conversely, SPF/DKIM/DMARC do not encrypt the SMTP connection.

## 17. Checking STARTTLS with OpenSSL

When diagnosing connectivity from the machine or container running the application, you can use **OpenSSL** if installed:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.com:587 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error
~~~

Components:

- **-starttls smtp:** performs the exchange needed to upgrade an SMTP connection via STARTTLS.
- **-connect:** specifies the endpoint and port.
- **-servername:** sends SNI so the server can select the appropriate certificate when supported.
- **-verify_hostname:** verifies that the certificate matches the target hostname.
- **-verify_return_error:** returns an error if certificate verification fails.

Some OpenSSL builds or environments may have different options; use capabilities supported by your installed version.

### Reading the output

The output can show:

- Whether the TCP connection opened successfully.
- Whether the SMTP server supports and accepts STARTTLS.
- Whether the TLS handshake completed.
- Whether the certificate and CA chain verify cleanly.
- Whether the hostname matches the certificate.
- Which protocol/cipher was selected.

This command **does not prove AUTH succeeds or that mail sending permissions are valid**. It only tests connectivity and the TLS upgrade within the scope of the tool.

**Do not enter real SMTP credentials into an uncontrolled manual test session.** Use a test environment and dedicated account when testing authentication.

## 18. Checking implicit TLS on port 465

For SMTPS, omit **-starttls smtp** because TLS must be established immediately:

~~~bash
openssl s_client \
  -connect smtp.example.com:465 \
  -servername smtp.example.com \
  -verify_hostname smtp.example.com \
  -verify_return_error
~~~

If the STARTTLS command on port 587 works well while the implicit TLS command on port 465 fails, the provider does not necessarily have an outage. The provider may only support one of the two endpoints, or port 465 may be blocked by a firewall.

Conversely, running an implicit TLS command on 587 is normally not the right way to test STARTTLS. The client may report a handshake error or timeout because the server is expecting an SMTP greeting/command in a different order.

### Check TCP before concluding a TLS failure

On Windows PowerShell:

~~~powershell
Test-NetConnection smtp.example.com -Port 587
Test-NetConnection smtp.example.com -Port 465
~~~

On Linux with netcat:

~~~bash
nc -vz -w 5 smtp.example.com 587
nc -vz -w 5 smtp.example.com 465
~~~

A successful TCP connect only proves initial layer connectivity; it does not confirm TLS, AUTH, or sending permission.

## 19. Common errors when using STARTTLS

| Symptom | Possible cause | What to check |
|---|---|---|
| **STARTTLS is required but host does not support STARTTLS** | Endpoint does not advertise STARTTLS; wrong host/port or server misconfigured | Check EHLO capabilities and endpoint |
| **Could not convert socket to TLS** | Handshake, certificate, protocol, or intermediary device | Inspect SSLHandshakeException cause and certificate |
| **PKIX path building failed** | Untrusted CA or incomplete chain | Inspect chain and truststore |
| **No subject alternative DNS name matching** | Certificate does not match hostname | Fix host or certificate |
| **Authentication failed** | Wrong credentials, permissions, or AUTH mechanism | Check auth configuration after TLS |
| **SocketTimeoutException** | Slow server/network response; wrong mode may cause waiting | Identify phase, TCP, TLS, and read timeout |
| **Connection refused** | No listener on target port or rejected | Check host/port and network policy |
| **UnknownHostException** | SMTP hostname cannot be resolved | Check DNS and effective configuration |

These error names are common examples, not a guarantee of identical exception strings across every Jakarta Mail/JDK version. In a Spring application, the root cause may be wrapped inside **MailSendException**, **MessagingException**, or related exceptions.

### Example: server does not advertise STARTTLS

~~~text
Client: EHLO application.example
Server: 250-smtp.example.com
Server: 250-SIZE 52428800
Server: 250 AUTH ...

Missing 250-STARTTLS / 250 STARTTLS
~~~

If using port 587 and requiring STARTTLS, the application should **fail rather than send plaintext**. Verify that this is the right SMTP endpoint, check whether an intermediary device is interfering, and confirm whether STARTTLS is enabled on the server.

### Example: untrusted certificate chain

~~~text
javax.net.ssl.SSLHandshakeException
  PKIX path building failed
~~~

The solution is not **ssl.trust=***. Inspect the endpoint, CA chain, JDK truststore, and the provider's certificate issuance process.

## 20. Common errors when using implicit TLS

| Symptom | Possible cause | Remediation |
|---|---|---|
| TLS handshake fails immediately upon connect | Wrong port, protocol, or certificate | Run s_client in implicit TLS mode and inspect error |
| Timeout waiting for SMTP greeting | Client has not enabled implicit TLS while server expects TLS | Enable mail.smtp.ssl.enable=true on port 465 |
| Server closes connection immediately | Client speaks plaintext on a TLS endpoint or rejected by policy | Check TLS mode and network |
| SMTP greeting arrives but AUTH fails | TLS is working; credential/AUTH mechanism issue | Check permissions and credentials |
| Hostname mismatch | Certificate does not cover host | Use official host or fix certificate |
| Only production container fails | Different truststore/JDK/runtime or outbound network | Compare image, CA, and egress |

If the certificate verifies successfully but authentication fails, do not conclude “TLS is broken”. Separate the two steps in logs and runbooks.

## 21. DNS, TCP, TLS, and SMTP AUTH are four distinct layers

When the application only surfaces a generic error, you can diagnose in order:

~~~text
Is SMTP hostname right?
       |
       +-- No --> Fix host/profile configuration
       |
       v
Does DNS lookup succeed?
       |
       +-- No --> Check DNS/resolver/container
       |
       v
Does TCP host:port connect?
       |
       +-- No --> Check firewall, route, listener, egress
       |
       v
Do TLS handshake and cert verification succeed?
       |
       +-- No --> Check 587/465 mode, CA, hostname, TLS policy
       |
       v
Does SMTP AUTH succeed?
       |
       +-- No --> Check credentials, permissions, and auth mechanism
       |
       v
Do SMTP MAIL FROM / RCPT TO / DATA succeed?
       |
       +-- No --> Check SMTP reply, sender identity, recipient, size
       |
       v
Submission accepted
~~~

This order does not mean performing every step if the fault is already clear. It prevents misattributing causes:

- **UnknownHostException** is not fixed by changing the password.
- **Connection refused** is not fixed by changing HTML content.
- **SSLHandshakeException** is not fixed by removing SMTP authentication.
- **SMTP 535 authentication failed** is usually not fixed by increasing timeouts.
- **SMTP 550 recipient rejected** is usually not a TLS error.

## 22. Timeouts when using STARTTLS and SMTPS

TLS requires extra network steps such as the handshake and certificate verification; SMTP submission also involves greeting, AUTH, and DATA. To keep workers from waiting indefinitely, configure all three timeout limits on the Jakarta Mail SMTP transport:

~~~properties
mail.smtp.connectiontimeout=5000
mail.smtp.timeout=10000
mail.smtp.writetimeout=10000
~~~

| Property | Role |
|---|---|
| **connectiontimeout** | Limit for opening the socket connection |
| **timeout** | Limit for socket read/response waiting |
| **writetimeout** | Limit for socket writes |

The values above are in milliseconds and are only examples; measure actual latency before choosing yours.

### Timeout caused by wrong TLS mode

If the client waits for a plaintext SMTP greeting from an implicit TLS endpoint while the server waits for a TLS ClientHello, both sides may wait until one of the timeouts triggers. Increasing timeouts will not fix a wrong mode.

### Timeout after submitting SMTP data

If the final response is lost when the server may have already received DATA, the application may **not know whether the email was accepted**. This is a different state from a connect timeout before opening a connection.

~~~text
Connect timeout before SMTP
   -> no submission yet
   -> safe to retry if cause is transient

Read timeout after sending DATA
   -> acceptance may have occurred
   -> UNKNOWN / reconcile before retrying
~~~

Do not assume every **SocketTimeoutException** can be safely resent.

## 23. Why is “SSL enabled” not enough to conclude security?

A configuration like this may appear:

~~~properties
mail.smtp.ssl.enable=true
mail.smtp.ssl.trust=*
~~~

The connection may be encrypted, yet trusting all certificates/hosts prevents the application from properly verifying the real server. An actor controlling an intermediate link could attempt to stand up a spoofed endpoint.

For proper protection, pay attention to:

1. **Right endpoint:** host/port published by the provider.
2. **Right TLS mode:** explicit STARTTLS or implicit TLS.
3. **No plaintext fallback:** with STARTTLS, require the upgrade.
4. **Trusted CA chain:** use an appropriate truststore.
5. **Hostname verification:** the server certificate must match the host.
6. **Permitted protocols/ciphers:** do not use weak protocols to “fix errors”.
7. **Credential protection:** use a secret manager, never log AUTH.

**Encryption and peer authentication are two inseparable parts of secure connection design.**

## 24. Environment-specific configuration and secrets handling

In practice, development, staging, and production often have different SMTP endpoints or accounts.

~~~text
Development
  -> Internal SMTP sandbox, no outbound delivery to the Internet

Staging
  -> SMTP test account, restricted recipients

Production
  -> SMTP submission provider, mandatory STARTTLS/implicit TLS
~~~

Configuration can use environment variables:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
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
~~~

The example above **assumes** the endpoint configured via environment variables uses STARTTLS. If production switches to port 465, you must also change the TLS mode settings rather than only changing **SMTP_PORT**.

Never put secrets in documentation, sample YAML committed to a repository, or error logs. For SMTP providers supporting app passwords, OAuth2, or tokens, use the provider-approved method and apply least privilege.

### Risks of dynamic configuration

If host/port/TLS mode are taken from user requests or untrusted data, the application risks sending to unfamiliar servers or accessing internal endpoints. SMTP hosts and transport modes should be determined by controlled administrative configuration, never arbitrary input.

## 25. Monitoring TLS connections in operations

An email-sending system should not only count how often **JavaMailSender.send(...)** returns successfully. You need to understand where errors happen and how frequently.

Metrics you can record:

| Metric | Meaning |
|---|---|
| **mail_connection_failure_total** | Number of failures connecting to the SMTP server |
| **mail_tls_handshake_failure_total** | Number of failed TLS handshakes |
| **mail_tls_certificate_failure_total** | Number of invalid certificate/hostname failures |
| **mail_authentication_failure_total** | Number of rejected SMTP authentications |
| **mail_submission_success_total** | Number of confirmed SMTP submissions |
| **mail_send_duration** | Duration to create/send over transport |
| **mail_timeout_total** | Number of timeouts, ideally split by phase if known |
| **mail_retry_pending_count** | Number of notifications awaiting retry |
| **mail_unknown_outcome_total** | Number of indeterminate send outcomes |

Event logs should include enough information to correlate:

~~~text
notificationId=...
sender=transactional
smtpHost=smtp.example.com
smtpPort=587
tlsMode=STARTTLS_REQUIRED
errorCategory=TLS_CERTIFICATE_INVALID
attempt=1
~~~

**Never log passwords, SMTP AUTH payloads, full MIME messages, OTPs, or tokens.** If protocol debugging must be enabled, do so in a controlled environment, limit how long it stays on, and identify clearly what information may be recorded.

## 26. Debugging Jakarta Mail when connections fail

Jakarta Mail has a debug mode to observe protocol exchanges and connection events. In a test environment, you can configure:

~~~yaml
spring:
  mail:
    properties:
      mail:
        debug: true
~~~

However, SMTP debugging must be used cautiously:

- It can generate high log volume under heavy traffic.
- Logs may expose servers, addresses, and email metadata.
- Do not assume all authentication values are always masked in every version/configuration.
- Debugging can increase production log cost and noise.

Prefer using exception classes, cause chains, SMTP reply codes, and metrics first. If you must enable debug, use an SMTP sandbox and test secrets.

### Reading the exception chain properly

In a Spring application, TLS errors may appear underneath **MailSendException** or **MessagingException**:

~~~text
org.springframework.mail.MailSendException
  -> jakarta.mail.MessagingException
      -> javax.net.ssl.SSLHandshakeException
          -> sun.security.validator.ValidatorException
~~~

This is only an illustrative diagram; actual classes and order vary by JDK/Jakarta Mail version. When diagnosing, inspect both **Throwable.getCause()** and, when needed, **MessagingException.getNextException()**.

An outer exception named **MailSendException** does not tell you whether the cause is a certificate, wrong port, DNS, or AUTH. Do not classify every MailSendException as retryable.

## 27. When can you retry after a TLS error?

Retrying depends on the cause:

| Case | Usually appropriate action |
|---|---|
| SMTP server temporarily unavailable, not connected yet | Retry with backoff |
| Transient DNS resolver failure | Retry with a limit |
| TLS handshake fails due to certificate mismatch | Stop, fix endpoint/certificate |
| CA is untrusted | Stop, inspect chain/truststore |
| Server only offers disallowed TLS versions | Fix/upgrade server or approved policy |
| STARTTLS configured on an implicit TLS port | Fix TLS mode |
| Implicit TLS configured on a STARTTLS port | Fix TLS mode |
| Incorrect SMTP authentication | Check credentials/permissions; do not retry endlessly with the same secret |
| Timeout after DATA, no final response | UNKNOWN, reconcile before resending |

**TLS handshake errors occur before transmitting email content in a properly established SMTP session**, so duplicate-sending risk from the failed handshake itself is normally low. However, to retry safely you must still check which sending phase actually occurred and transport details, especially if the code performs multiple sends or complex fallbacks.

### Backoff and limits

If the error is transient, a policy may use:

~~~text
retryDelay = min(maxDelay, initialDelay * 2^(attempt - 1)) + jitter
~~~

For example:

- Wait 30 seconds before the first retry.
- Double the wait interval for subsequent attempts.
- Cap the maximum delay.
- Set max attempts and alert if errors persist.
- Persist retry state durably in an outbox for important notifications.

Exact timings should be based on SLAs and actual SMTP load. **Do not retry indefinitely on request threads** or open thousands of connections while the provider is failing.

## 28. TLS when sending mail via transaction/outbox

Spring Mail is often called from a business service. A common mistake is holding a database transaction open during SMTP connections, especially when a TLS handshake times out.

Avoid doing this:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    mailSender.send(...); // Waits for DNS, TCP, TLS, AUTH, DATA inside the DB transaction
}
~~~

If SMTP is slow, database locks or transactions can be held for a long time. If sending succeeds and then the transaction rolls back, the submitted email cannot be “recalled” by a database rollback.

For important emails, write a **notification outbox record** inside the business transaction, then let a worker send it after commit:

~~~text
Business transaction
   |
   +-- UPDATE order
   +-- INSERT notification_outbox
   |
 COMMIT
   |
   v
Worker claims outbox record
   |
 COMMIT claim
   |
   v
JavaMailSender: TCP -> TLS -> AUTH -> DATA
   |
   v
Worker updates result in a separate transaction
~~~

This prevents TLS handshakes or network failures from keeping the business transaction open. Meanwhile, the outbox lets you store PENDING/RETRY/FAILED states and reconcile UNKNOWN send outcomes.

However, an outbox **does not automatically guarantee exactly-once delivery**. If SMTP already received DATA and the connection drops before the worker records the result, retrying may produce duplicate emails. You need notification IDs, attempt tracking, an UNKNOWN policy, and reconciliation when supported by the provider.

## 29. Testing STARTTLS and SMTPS

Different test layers serve different purposes:

### Unit testing the mail-sending service

You can mock **JavaMailSender** to verify the service builds a **MimeMessage** and calls **send(...)** with the right recipient, subject, and content.

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
);

when(sender.createMimeMessage()).thenReturn(message);

AccountNotificationService service =
        new AccountNotificationService(sender);

service.sendSecurityNotice("test@example.net");

verify(sender).send(message);
~~~

This is an illustrative sketch using Mockito and Jakarta Mail **Session**. **Mock-based unit tests do not prove TLS is established** because mocks never open a TCP connection.

### Integration testing with an SMTP test server

To test transport behavior, you need a suitable test SMTP server or sandbox:

- An endpoint advertising STARTTLS on the test port.
- An endpoint requiring implicit TLS if testing port 465.
- A test certificate with a trusted hostname and CA.
- Dedicated test accounts, never production credentials.
- Ability to simulate not advertising STARTTLS or presenting an invalid certificate.

Specifically verify that the application **does not send plaintext emails when STARTTLS is configured as required but the server does not support STARTTLS**.

### Test scenario table

| Client configuration | Server | Expected outcome |
|---|---|---|
| STARTTLS enable + required | Has STARTTLS, valid certificate | Sends over TLS |
| STARTTLS enable + required | Does not advertise STARTTLS | Fails, no plaintext fallback |
| STARTTLS required | Certificate has wrong hostname | Fails server identity verification |
| Implicit TLS on 465 | Server supports valid implicit TLS | Connects and exchanges SMTP over TLS |
| Implicit TLS on 587 | Server only supports STARTTLS | Handshake/connection fails; fix mode |
| STARTTLS on 465 | Server requires TLS from the start | May timeout/handshake fail; fix mode |
| Valid TLS, wrong credentials | Server rejects AUTH | Authentication error, do not label as TLS |
| Valid TLS, temporary 4xx from provider | SMTP explicitly rejects command | Retry per SMTP reply/policy |
| Timeout after DATA | Unclear if server accepted | UNKNOWN state/reconciliation |

Do not intentionally test repeated wrong credentials against production SMTP, as this may lock the account or trigger anomaly flags.

## 30. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| “STARTTLS is a weaker encryption protocol than SMTPS” | Both are ways of adding TLS to an SMTP session; they differ in when TLS starts |
| “Port 465 is deprecated and cannot be used” | Port 465 is used for implicit TLS submission in modern deployments |
| “Port 587 is always encrypted” | The server must support STARTTLS and the client must actually upgrade |
| “Enabling starttls.enable is enough” | For strict security requirements, also set starttls.required |
| “A successful TLS handshake is all you need” | You must verify the certificate chain and hostname |
| “ssl.trust=* is how you fix certificate errors” | That weakens endpoint verification |
| “SMTP AUTH protects passwords even without TLS” | AUTH does not replace transport encryption |
| “TLS on port 465 secures email all the way to the Inbox” | That TLS only protects the current connection hop |
| “If TLS is on, you don't need SPF/DKIM/DMARC” | They serve different purposes |
| “SSLHandshakeException can always be retried” | Wrong mode or certificate issues are persistent configuration errors |
| “Spring Boot infers TLS mode from the port” | You must explicitly declare the right properties |
| “Successful SMTP send means delivered” | Accepted submission does not mean it reached the mailbox |

## 31. Production deployment checklist

1. **Identify the official SMTP endpoint**, host, and port published by the provider.
2. **Choose the right TLS mode**: STARTTLS on an endpoint supporting upgrades, or implicit TLS on an endpoint requiring encryption from the start.
3. **No STARTTLS fallback:** set both enable and required when data needs protection.
4. **Verify hostname:** enable mail.smtp.ssl.checkserveridentity=true.
5. **Proper CA/truststore:** verify the server certificate and trust chain, never wildcard trust.
6. **Appropriate TLS protocols:** avoid forcing disallowed legacy versions.
7. **SMTP AUTH:** only transmit credentials over a verified TLS channel; protect secrets.
8. **Finite timeouts:** set connectiontimeout, timeout, and writetimeout matching SLAs.
9. **Environment-specific configuration:** staging and production have separate secrets/endpoints; do not let profiles accidentally alter modes.
10. **Test from where the app actually runs:** check DNS, TCP, OpenSSL, and certificates when errors occur.
11. **Test no-fallback behavior:** ensure failure when STARTTLS is required but unsupported by the server.
12. **Safe logging:** record category/phase/correlation ID, never credentials or sensitive MIME content.
13. **Classified retries:** do not retry blindly on certificate mismatches, auth failures, or unknown outcomes.
14. **Use an outbox when needed:** persist send intent durably and send outside business transactions.
15. **Monitor:** track TLS handshake failures, auth errors, submission status, and queue age.

This list is an implementation guide and does not replace your organization's security policies and operational procedures.

## 32. Takeaways

**STARTTLS** and **SMTPS (implicit TLS)** both use TLS to protect communication between a Spring application and an SMTP server. STARTTLS starts with an SMTP session and upgrades to TLS after the STARTTLS command, commonly on **port 587**. Implicit TLS establishes TLS from the very start, commonly on **port 465**. The two differ in handshake ordering, not fixed encryption strength.

In Spring Framework Mail with **JavaMailSenderImpl**:

- STARTTLS: set **mail.smtp.starttls.enable=true** and **mail.smtp.starttls.required=true**.
- Implicit TLS: set **mail.smtp.ssl.enable=true**.
- Both: enable **mail.smtp.ssl.checkserveridentity=true**, use a trusted CA/truststore, protect credentials, and configure finite timeouts.

If a connection fails, diagnose **DNS, TCP, TLS handshake, certificate/hostname, SMTP AUTH, and SMTP response** in sequence instead of disabling TLS or arbitrarily raising timeouts. Network errors after DATA can leave submission status unknown; do not retry unconditionally and create duplicate emails.

**Secure TLS requires the right endpoint, the right mode, server verification, and no downgrade to plaintext.** Combining these principles with proper sender, outbox, and send-error management helps Spring applications send email over SMTP more reliably.



