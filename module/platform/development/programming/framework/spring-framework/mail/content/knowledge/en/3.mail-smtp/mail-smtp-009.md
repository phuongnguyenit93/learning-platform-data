# STARTTLS and Connection Upgrade in an SMTP Session

When a Spring application sends email over SMTP, data exchanged with the mail server may travel across an internal network or the Internet. Traditional SMTP connections begin with plaintext commands. If login credentials or message content are sent over an unprotected connection, anyone able to observe network traffic can read or tamper with the data.

**STARTTLS** is a mechanism allowing both ends of **an active SMTP connection** to switch from regular SMTP communication to communication protected by **TLS (Transport Layer Security)**. After upgrading successfully, subsequent SMTP commands and message data sent over that connection are encrypted under the TLS session.

In **Spring Framework Mail**, applications usually use `JavaMailSender` with the Jakarta Mail library to connect to an SMTP server or SMTP relay. Configuring STARTTLS determines how the application protects this connection hop. It is essential to understand how the upgrade occurs, when to refuse connections lacking TLS, and why STARTTLS does not mean the email is encrypted end-to-end.

## 1. What Problem Does STARTTLS Solve?

Imagine an application needing to send an account confirmation email:

~~~mermaid
flowchart LR
    A["Spring Application"] -->|"SMTP submission"| B["SMTP relay"]
    B -->|"Server-to-server SMTP"| C["Receiving server"]
    C --> D["Recipient mailbox"]
~~~

These are **different transmission hops**. The connection from Spring to the SMTP relay can be protected with STARTTLS; the connection from the relay to the receiving server is a separate SMTP session that may or may not use TLS depending on both servers' configurations and policies.

The three main goals of TLS on an SMTP hop are:

- **Confidentiality in transit:** prevents network observers from reading SMTP commands, email contents, and authentication credentials transmitted after the TLS session is established.
- **Integrity protection:** helps detect tampering with data in transit over the TLS connection.
- **Target server authentication when identity verification is configured:** valid TLS certificates and hostname checks reduce the risk of the application accidentally connecting to a spoofed server.

STARTTLS does not authenticate the email account itself; that is the role of **SMTP AUTH**. Nor does it guarantee the email will reach the Inbox, guarantee every subsequent relay hop is encrypted, or authenticate the sender identity per SPF/DKIM/DMARC.

## 2. How Does STARTTLS Differ from an Immediate TLS Connection?

There are two common ways to set up a TLS-protected SMTP connection:

| Connection method | When TLS begins | Common ports | Characteristics |
| --- | --- | --- | --- |
| **STARTTLS (Explicit TLS)** | Starts with regular SMTP, sends the `STARTTLS` command, and then performs the TLS handshake on the same TCP connection | **587** (submission), also seen on **25** when MTAs relay mail | Requires the server to advertise and support the `STARTTLS` command. |
| **Implicit TLS** | TLS handshake occurs **immediately after the TCP connection opens**, before any SMTP commands | **465** (submissions) | Does not need a `STARTTLS` command to switch state on this connection. |

The ports above reflect common conventions:

- **587:** **message submission** service. Applications or email clients submit mail to an SMTP relay, usually requiring authentication and potentially requiring STARTTLS.
- **465:** submission service over **implicit TLS**; both sides start TLS immediately upon connecting.
- **25:** primarily for **SMTP between sending and receiving servers**. STARTTLS on this port is usually negotiated per the transport infrastructure's policy.

Do not rely solely on port numbers to assume traffic is encrypted. Actual capabilities and policies reside in the SMTP server's configuration and the application's security requirements.

> **Rule of thumb:** STARTTLS means "start SMTP and upgrade to TLS on the same connection"; implicit TLS means "establish TLS from the very first byte".

## 3. How Does an SMTP Session Upgraded with STARTTLS Proceed?

To see the role of STARTTLS, follow an SMTP client connecting to `smtp.provider.example:587`. This is an **illustrative session**; specific hostnames, greetings, and advertised capabilities will differ.

~~~text
[1] TCP connection to smtp.provider.example:587

S: 220 smtp.provider.example ESMTP ready
C: EHLO app.example.org
S: 250-smtp.provider.example
S: 250-SIZE 26214400
S: 250-STARTTLS
S: 250 HELP

[2] Client requests upgrade

C: STARTTLS
S: 220 Ready to start TLS

[3] TLS handshake occurs on the same TCP connection
    (No longer plaintext SMTP command lines)
    - Client and server agree on TLS version/cipher
    - Server sends its certificate
    - Client verifies certificate and server identity per configuration
    - Both parties establish session keys

[4] TLS handshake succeeds; SMTP resumes inside TLS

C: EHLO app.example.org
S: 250-smtp.provider.example
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 26214400

[5] Client authenticates and sends mail inside TLS
    (Credentials omitted from this illustration)

C: AUTH ...
S: 235 2.7.0 Authentication successful
C: MAIL FROM:<notify@example.org>
S: 250 2.1.0 Sender OK
C: RCPT TO:<linh@example.net>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: notify@example.org
C: To: linh@example.net
C: Subject: Welcome
C:
C: Your account is ready.
C: .
S: 250 2.0.0 Message accepted
C: QUIT
S: 221 Bye
~~~

`C:` denotes the client and `S:` denotes the server. The transcript above uses text to explain the order. In reality, once TLS is established, packet captures outside the connection only see encrypted data; reading command contents requires traffic decryption capabilities in an appropriate test environment.

### Phase A — SMTP Connection and Discovering STARTTLS Capability

The server sends the `220` greeting. The client sends `EHLO` to use Extended SMTP (ESMTP) and receive the server's capability list. If the response includes `250-STARTTLS`, the server is signaling upgrade support.

**Advertising STARTTLS does not mean TLS is active yet.** At this moment, SMTP commands and responses are still pre-encryption data. Attributes such as server address, greeting text, and initially advertised capabilities can be observed.

### Phase B — Client Sends the STARTTLS Command

The client sends:

~~~text
STARTTLS
~~~

The server returns code `220` when ready to start TLS. From that point, both ends must transition to the **TLS handshake** over the **existing TCP connection**. No new port is opened, no HTTP command is issued, and no separate SMTP connection is created to perform the upgrade.

If the server does not advertise STARTTLS, the client must act according to its configured security policy. If the upgrade command is rejected, the connection must not be considered protected.

### Phase C — TLS Handshake

During the TLS handshake, client and server negotiate TLS session parameters, the server presents its certificate, and the client decides whether to trust that server. Under proper security configuration, the client checks:

1. The certificate chain is signed by a trusted Certificate Authority (CA), or by a configured private trust source.
2. The certificate has not expired and has valid usage attributes.
3. The identity in the certificate matches the SMTP server hostname the client intends to connect to.
4. The TLS version and cipher suite are supported by both sides and permitted by policy.

**Encryption without server identity verification is insufficient against server spoofing.** An attacker can attempt to place a device between client and server if the client accepts any certificate or skips hostname checks.

### Phase D — SMTP Resumes After TLS

Once the TLS handshake succeeds, both sides **discard any SMTP capabilities recorded prior to the upgrade**. The client sends `EHLO` **again** inside the TLS connection to retrieve the updated capability list.

This is necessary because the server may advertise `AUTH` mechanisms or sensitive capabilities **only after the connection is protected**. The client must never assume the ESMTP list before and after STARTTLS is identical.

After the second `EHLO`, the client can authenticate (if required by the service) and then send `MAIL FROM`, `RCPT TO`, and `DATA` per normal SMTP, except the bytes crossing the TCP connection now travel inside the TLS session.

### Overall State Flow

~~~mermaid
stateDiagram-v2
    [*] --> TCP
    TCP --> PlainSMTP: Receive 220 banner
    PlainSMTP --> Capabilities: EHLO
    Capabilities --> TLSRequested: STARTTLS present, client requests
    TLSRequested --> Handshake: Server returns 220
    Handshake --> SecureSMTP: TLS succeeds
    SecureSMTP --> SecureCapabilities: EHLO again
    SecureCapabilities --> Submission: AUTH (if needed), MAIL/RCPT/DATA
    Submission --> [*]: QUIT
    Capabilities --> Reject: TLS required but server lacks support
    TLSRequested --> Reject: Server rejects
    Handshake --> Reject: TLS handshake fails
    Reject --> [*]
~~~

On a connection requiring TLS, until `SecureSMTP` is reached, **do not proceed to send credentials or message data over a plaintext connection**.

## 4. How Do Opportunistic TLS and Required TLS Differ?

This is the most important distinction when configuring an application.

### 4.1. Opportunistic TLS — Use TLS If the Server Supports It

The client may request STARTTLS upon seeing the `STARTTLS` capability, yet **still proceed with unencrypted SMTP if the server lacks support**. This is the opportunistic TLS strategy, commonly used in server-to-server MTA transport to maintain broad compatibility.

Its advantage is delivering mail to older servers without TLS support; its drawback is that traffic can travel unencrypted. If an attacker can tamper with the connection before TLS starts, they may try stripping `STARTTLS` from the `EHLO` response (a form of **downgrade attack**).

Never assume opportunistic TLS is sufficient for the **Spring app → authenticated SMTP submission relay** hop.

### 4.2. Required TLS — Mandatory Successful Upgrade

With a required TLS policy, the client refuses to proceed if:

- the SMTP server does not advertise `STARTTLS`;
- the server rejects the `STARTTLS` command;
- the TLS handshake fails;
- the server certificate or identity fails configured verification requirements.

This prevents the application from silently falling back to plaintext SMTP. With a trusted provider's SMTP relay, requiring TLS is the right choice when sending authenticated transactional emails.

Distinguish **"requiring TLS"** from **"verifying server identity"**. Both requirements must be configured properly to avoid encrypting a connection while still trusting an invalid certificate or wrong hostname.

| Policy | When server supports valid TLS | When server lacks STARTTLS | When handshake fails |
| --- | --- | --- | --- |
| Opportunistic STARTTLS | Upgrades and sends | May continue in plaintext | Usually reports connection/upgrade failure; do not assume a safe fallback |
| Required STARTTLS | Upgrades and sends | Stops with error | Stops with error |
| Implicit TLS | Handshakes TLS on connect | STARTTLS command not applicable | Stops with error |

**Never interpret "opportunistic" as allowing all TLS failures to be ignored.** Exact behavior depends on the SMTP client and error type; inspect actual configuration. A safe policy for authenticated applications is making the TLS requirement explicit.

## 5. Configuring STARTTLS in Spring Boot and JavaMailSender

Spring Framework Mail provides `JavaMailSender` to send mail. With Spring Boot and `spring-boot-starter-mail`, Jakarta Mail handles SMTP connections and the STARTTLS command according to configured properties.

### 5.1. Gradle Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

If a Spring project does not use Spring Boot, you can create a `JavaMailSenderImpl` bean yourself and declare Jakarta Mail along with the equivalent SMTP properties.

### 5.2. Example Application Using STARTTLS on Port 587

~~~properties
# Actual SMTP submission relay provided by the vendor
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.protocol=smtp

# Load secrets from runtime environment; never store passwords in Git
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

# Authentication and STARTTLS
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

# Verify server hostname identity in the TLS certificate
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

# Connect / read / write timeouts (milliseconds)
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

`smtp.provider.example` is illustrative only. Replace it with the SMTP provider's official host and port, and verify whether the service supports STARTTLS and which authentication mechanisms it uses.

Meaning of properties directly tied to STARTTLS:

| Jakarta Mail property | Effect |
| --- | --- |
| `mail.smtp.starttls.enable=true` | Allows the client to use the STARTTLS command when advertised by the server. On its own, this property **does not force every connection to be encrypted**. |
| `mail.smtp.starttls.required=true` | Requires STARTTLS to be available and the upgrade to succeed; otherwise sending must fail. |
| `mail.smtp.ssl.checkserveridentity=true` | Enables checking the server's hostname identity against TLS; avoids relying solely on trust-chain validity. |
| `mail.smtp.auth=true` | Requires using SMTP AUTH. It does not replace STARTTLS. |
| `mail.smtp.connectiontimeout` | Time limit for establishing the TCP connection. |
| `mail.smtp.timeout` | Time limit waiting to read from the socket. |
| `mail.smtp.writetimeout` | Time limit for writing data to the socket. |

Spring Boot passes keys under `spring.mail.properties.` into Jakarta Mail's configuration. Therefore, property names starting with `mail.smtp.` must be spelled accurately per the Jakarta Mail version used by the project.

Normally, the application should use the JVM's trusted certificate store or a properly managed truststore. **Avoid configuring `mail.smtp.ssl.trust=*` in real environments**, as that can cause the client to accept servers without proper trust-chain verification.

### 5.3. Email-Sending Example

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String from, String to) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject("System notification");
        message.setText("Your request has been received.");
        mailSender.send(message);
    }
}
~~~

`NotificationMailService` does not manually emit `EHLO`, `STARTTLS`, or run the TLS handshake. **Jakarta Mail handles the protocol based on configuration**, while business code calls `JavaMailSender.send(...)`.

If STARTTLS is required and the upgrade fails, the send call may throw an exception in Spring's `MailException` family (the root cause may be a Jakarta Mail or SSL/TLS error). The application must log the error appropriately and decide whether to retry or alert, rather than treating it as a successful send.

## 6. When the Provider Requires Implicit TLS on Port 465

If the SMTP relay requires TLS right upon connect, the configuration typically differs:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

For implicit TLS, `mail.smtp.ssl.enable=true` asks to create an SSL/TLS-protected SMTP connection **from the start**. You do not need STARTTLS to "upgrade" a connection that is already inside TLS.

A common configuration mistake is:

- Connecting to port **587** while setting `mail.smtp.ssl.enable=true` as if it were an implicit TLS port.
- Connecting to port **465** while only setting `mail.smtp.starttls.enable=true` as if the server expected an initial plaintext SMTP session.

Both mismatches can leave the two sides waiting for different protocol bytes, leading to timeouts or handshake failures. Use the configuration matching the SMTP provider's documentation. Custom ports can still work if both ends are configured consistently.

## 7. EHLO and Capability Changes After STARTTLS

Extended SMTP uses `EHLO` for the server to advertise currently supported capabilities. The capability list **can change after TLS**.

Example:

~~~text
# Before STARTTLS
250-smtp.provider.example
250-STARTTLS
250 SIZE 26214400

# After TLS and second EHLO
250-smtp.provider.example
250-AUTH PLAIN LOGIN
250 SIZE 26214400
~~~

Here, `AUTH` appears only after the client completes the handshake. Servers do this to avoid encouraging clients to send credentials over an unencrypted channel.

Key points to understand:

1. The first `EHLO` determines whether STARTTLS can be requested.
2. A `220` reply to `STARTTLS` begins the **TLS handshake**.
3. Once TLS succeeds, **do not reuse the old ESMTP capability list**.
4. The second `EHLO` supplies current capabilities for the protected SMTP session.
5. Only then do `AUTH` and mail submission commands follow per server policy.

Some servers may advertise `AUTH` even before TLS yet refuse to execute it until TLS is active. Clients must still uphold the policy of never sending login credentials over plaintext.

## 8. Common Errors During STARTTLS Upgrade

Observed errors can appear at several steps. Determining the cause should rely on **when the failure happened in the SMTP session**, not merely on a "mail send failed" message at the business layer.

| Symptom | Possible causes | Investigation path |
| --- | --- | --- |
| `STARTTLS is required but host does not support STARTTLS` or similar message | Server does not advertise STARTTLS; app connects to wrong port, wrong service, or server is misconfigured | Confirm hostname/port, inspect `EHLO` capabilities, check provider docs |
| `454 TLS not available due to temporary reason` | Server temporarily unable to provide TLS; server config or resource issue | Check SMTP server health, certificates, and server logs |
| `SSLHandshakeException` | Could not negotiate TLS session, untrusted cert, or handshake failure | Inspect root cause in stack trace, TLS version/cipher, truststore |
| Certificate does not match server hostname | Connected via a hostname different from the cert's Subject Alternative Name (SAN); intermediary device swapped cert | Use the exact SMTP hostname; inspect cert chain and hostname verification settings |
| Connection to 465/587 times out | Wrong TLS mode for the port, blocked by firewall, or server unresponsive | Check implicit TLS vs. STARTTLS, test network and port |
| TLS handshake succeeded but `AUTH` rejected | Wrong account, wrong auth mechanism, or provider policy | Check credentials, AUTH method, and sending permissions |
| `530 Must issue a STARTTLS command first` or similar message | Server requires upgrading before authenticating or sending mail | Configure STARTTLS properly and make TLS required |

SMTP codes are illustrative: exact replies and error messages vary across servers. After a network or TLS error, **never default to retrying over a plaintext connection** just to "make it work", especially when contents or credentials are sensitive.

### When Should You Retry?

- On temporary infrastructure errors, the sending queue can retry later with reasonable time and attempt limits.
- On wrong hostname, untrusted certificate, or wrong port config, repeated retries usually will not fix it; fix the configuration or infrastructure.
- If an error occurs after the receiving server already accepted `DATA` but the final reply did not reach the application, the client may **not know whether the message was received**. Retry logic must account for potential duplicates.

Distinguishing temporary failures from configuration errors is the responsibility of the sending/queuing system, not a feature STARTTLS provides on its own.

## 9. Using Tools to Observe the Upgrade Process

When troubleshooting a failed STARTTLS connection, you can use `openssl s_client` on a machine with OpenSSL. Example syntax:

~~~bash
openssl s_client -starttls smtp \
  -connect smtp.provider.example:587 \
  -servername smtp.provider.example \
  -verify_hostname smtp.provider.example
~~~

The command requests upgrading SMTP via STARTTLS and displays TLS/certificate details after connecting. Replace the illustrative hostname with the real SMTP hostname. Depending on the OpenSSL version, chain validation options and error reporting may vary; check **certificate verification outcome and exit status**, not just whether the socket connected.

You can use `swaks` (if installed in a test environment) to test SMTP at the protocol level:

~~~bash
swaks --server smtp.provider.example --port 587 \
  --tls --to test-recipient@example.net \
  --from test-sender@example.org
~~~

This command illustrates requesting STARTTLS; actually sending mail may require specifying SMTP auth and matching sending policies. Never pass passwords on the command line if they risk being saved in shell history or exposed via process listings.

### Observing Debug Information from Jakarta Mail

In a controlled development environment, Jakarta Mail supports SMTP session debugging via:

~~~properties
spring.mail.properties.mail.debug=true
~~~

Debug output can help observe `EHLO`, `STARTTLS` support, connection progress, and protocol errors. **Do not enable debug logging indiscriminately in Production**, because SMTP session logs can contain email addresses, metadata, or sensitive information. When troubleshooting an incident, enforce a time-bounded window for enabling logs and redact sensitive data properly. Never copy real credentials or real message contents into debug reports.

## 10. TLS on One Hop Is Not End-to-End Email Encryption

Suppose the Spring application uses STARTTLS with an SMTP relay and the TLS handshake succeeds:

~~~mermaid
flowchart LR
    A["Spring Application"] -->|"TLS #1"| B["SMTP relay"]
    B -->|"TLS #2 if negotiated"| C["Receiving server"]
    C -->|"Internal storage/forwarding"| D["Mailbox"]
~~~

What can be asserted is that **hop A → B** was protected by TLS during that SMTP session, with confidence depending on certificate/hostname verification. From this result you cannot deduce that:

- Hop B → C definitely uses TLS; that is a separate session and connection policy.
- The email is encrypted while sitting in queues, databases, or providers' mailboxes.
- Intermediaries with access to mail server systems cannot read email content.
- The email cannot be spoofed, rejected by spam filters, or placed in the Junk folder.

If you need **content encryption from sender to recipient so intermediate servers cannot read it**, look at other mechanisms such as S/MIME or OpenPGP along with corresponding key management workflows. STARTTLS protects the **transport channel between two SMTP endpoints**, not end-to-end content confidentiality.

### MTA STARTTLS and Downgrade Prevention

For the **MTA → MTA hop on port 25**, relying solely on the `STARTTLS` line advertised on initial connect can face downgrade risks without additional protective policies. Mechanisms such as **MTA-STS** or **DANE for SMTP** (paired with DNSSEC) can strengthen the reliability of requiring TLS and authenticating transfer servers, depending on domain adoption.

That belongs to email infrastructure administration rather than configuring Spring to send to a fixed relay. A Spring application should start with a clear policy for its own **SMTP submission**: require STARTTLS or implicit TLS properly, verify server identity, and manage credentials securely.

## 11. Practical Scenarios to Reason Through

**Scenario 1:** The app enabled `mail.smtp.starttls.enable=true`. The SMTP server does not advertise STARTTLS. Is the client guaranteed to refuse sending in plaintext?

**No.** Only setting `enable=true` permits using STARTTLS when the server supports it. If the application must guarantee TLS, configure `mail.smtp.starttls.required=true` and appropriate server verification.

**Scenario 2:** The SMTP client sends `EHLO`, then `STARTTLS`, and the TLS handshake succeeds. Can it reuse the pre-TLS capability list to send `AUTH`?

**No.** After upgrading, it must send `EHLO` again and use the new capability list.

**Scenario 3:** The provider requires port 465 implicit TLS. Should you use `spring.mail.port=465` with `mail.smtp.starttls.enable=true` without `mail.smtp.ssl.enable=true`?

**No.** Use the immediate TLS mode matching a port 465 server; STARTTLS is an upgrade mechanism over an initially plaintext SMTP connection.

**Scenario 4:** Spring sends successfully through a relay using TLS. Can you conclude the recipient's server received the message over TLS?

**No.** The outcome only covers the application-to-relay submission step. Each subsequent relay hop has its own TLS policy, connection, and state.

**Scenario 5:** The TLS handshake succeeds, yet the certificate does not match the SMTP hostname. Can you skip hostname checking to send mail faster?

**You should not.** Use the correct hostname, verify the certificate, or fix the truststore/server config. Skipping identity verification weakens protection against spoofed servers.

## 12. Mental Model to Remember

In Spring's mail-sending workflow, separate three things:

1. **Spring Framework Mail and Jakarta Mail:** build the message, connect to SMTP per configuration, require STARTTLS, and handle connection errors.
2. **SMTP and STARTTLS:** server advertises capabilities via `EHLO`, client sends `STARTTLS`, both sides run the TLS handshake, and SMTP continues after a fresh `EHLO`.
3. **Email policy and infrastructure:** decide whether TLS is mandatory, verify certificates, authenticate accounts, relay across multiple hops, handle bounced mail, and track delivery status.

The essence of STARTTLS is **upgrading security on an existing SMTP connection**. For a Spring application sending mail via SMTP submission, explicitly decide **whether TLS is required or optional**, configure the provider's exact connection mode, and verify server identity. Once you understand the states before and after `STARTTLS`, it becomes clear why an email succeeds, fails during handshake, or gets rejected at authentication even after TCP connects.

