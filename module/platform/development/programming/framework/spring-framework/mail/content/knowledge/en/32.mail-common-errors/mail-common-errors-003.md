# Disabling TLS Verification to Bypass Certificate Errors

When integrating email sending with **Spring Framework Mail**, applications typically connect to an SMTP relay over TLS. During configuration, many developers encounter errors such as `PKIX path building failed`, `SSLHandshakeException`, `No subject alternative DNS name matching`, or `Could not convert socket to TLS`. A commonly passed-around workaround is setting `mail.smtp.ssl.trust=*`, disabling hostname checks, or using an “accept-all” `TrustManager`.

That workaround may get email sending running again, yet **it does not prove the application connected to the real, trusted SMTP server**. If the connection goes to a spoofed server or through an unauthorized intermediary device, recipient data, email contents, and SMTP credentials can be exposed. In particular, emails often contain OTPs, password reset links, invoices, or sensitive business data.

**Key takeaway:** Never disable TLS certificate validation or hostname verification to “bypass” errors in production. Identify the real root cause: wrong hostname, wrong port/TLS mode, expired certificate, missing intermediate CA in the chain, missing CA in the JVM truststore, intercepting proxy, skewed system clock, or incompatible TLS protocol.

This lesson explains the security mechanisms that must be preserved, dangerous Spring Mail configurations, proper STARTTLS/implicit TLS setup, and a troubleshooting workflow applicable to Spring Boot, `JavaMailSenderImpl`, Jakarta Mail, and SMTP providers.

## 1. What Does TLS Protect When Spring Sends Email?

An email-sending connection passes through several layers:

~~~text
Business service / Mail worker
            |
            v
JavaMailSender / Jakarta Mail
            |
            | SMTP submission
            | TLS (STARTTLS or implicit TLS)
            v
SMTP relay / email provider
            |
            v
Downstream mail servers and recipient mailbox
~~~

TLS on the **Spring application → SMTP relay** hop addresses three concerns:

1. **Confidentiality:** reduces the chance of third parties eavesdropping on credentials, emails, and message contents in transit.
2. **Integrity:** reduces the chance of transmitted data being altered undetected.
3. **Server authentication:** allows the client to verify that the TLS peer matches the intended hostname and belongs to a trusted certificate chain.

### 1.1. Encryption Does Not Equal Server Authentication

Suppose the application connects to `smtp.provider.example` over an untrusted network:

~~~text
Spring application
       |
       | TLS where client trusts any certificate
       v
Impostor server
       |
       | Can capture credentials / messages
       v
Real SMTP provider (if attacker forwards)
~~~

If the application accepts **any certificate**, an attacker can establish an encrypted TLS connection **with themselves**. Data remains encrypted on the wire, yet it is no longer protected against the impersonating peer as intended.

| Mechanism | Purpose | If Bypassed |
| --- | --- | --- |
| TLS encryption | Protects data in transit | May send plaintext |
| Certificate chain verification | Certificate chains to a valid trust anchor | May accept certificates issued by anyone |
| Hostname verification | Certificate belongs to the host being connected to | Accepts another host's certificate |
| STARTTLS required | Refuses to continue without TLS upgrade | May downgrade to plaintext |
| SMTP AUTH | Authenticates the sending account | Cannot replace server authentication |

### 1.2. SMTP AUTH Does Not Replace TLS Identity

`mail.smtp.auth=true` only tells the client to use an appropriate SMTP authentication mechanism. It does not ensure the server's certificate is valid. If the application skips server verification, credentials or tokens may be presented to an untrusted endpoint, depending on protocol/auth mechanism.

Logically safe sequence:

~~~text
1. Connect to the right hostname / port.
2. Start or upgrade TLS per policy.
3. Verify the server's chain + hostname.
4. Perform SMTP authentication if required.
5. Send MAIL FROM, RCPT TO, DATA.
6. Record submission outcome.
~~~

Never treat a successful AUTH as proof that earlier steps were secure.

### 1.3. TLS on the First Hop Does Not Guarantee the Entire Email Path

Spring connecting to the SMTP relay with valid TLS only proves the transport layer on the **Spring → relay** hop is protected per policy. The message may continue across multiple SMTP hops; whether it reaches the Inbox, is DKIM-signed, or is read are separate matters.

Never treat `JavaMailSender.send(...)` returning successfully as proof that the message was delivered to the Inbox. It usually only indicates SMTP submission completed per the transport adapter's contract.

## 2. Three Commonly Conflated Layers

### 2.1. Certificate Chain Validation

The SMTP server presents a chain such as:

~~~text
Trusted Root CA
      |
      v
Intermediate CA
      |
      v
Leaf certificate: smtp.provider.example
~~~

The client must verify signatures, usage constraints, validity period, and find a trust path to a CA in the appropriate truststore. If a trust chain cannot be built, Java may report:

~~~text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed

Caused by:
    sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
~~~

**A PKIX error does not mean TLS should be disabled.** It typically calls for checking the certificate chain, CAs, and truststore.

### 2.2. Hostname Verification

A certificate signed by a trusted CA can still belong to **a different host**.

~~~text
App connects:
    smtp-b.provider.example

Certificate SAN:
    DNS:smtp-a.provider.example

Chain valid: YES
Hostname match: NO
=> Must reject connection.
~~~

Modern certificates use **Subject Alternative Name (SAN)** to list valid DNS names or IP addresses. Hostname matching must follow TLS identity checking rules. When connecting by IP address, you cannot assume a certificate with only a DNS SAN is sufficient.

### 2.3. TLS Mode and Downgrade Policy

For SMTP submission on port 587, STARTTLS usually begins with unencrypted SMTP and then upgrades. If the application permits continuing when STARTTLS is not advertised by the server, an attacker or broken proxy can keep the client from using TLS as policy requires.

Therefore, distinguish:

- `mail.smtp.starttls.enable=true`: enables upgrading via STARTTLS.
- `mail.smtp.starttls.required=true`: **requires** the upgrade; refuses to continue if TLS cannot be established.

When protecting credentials and emails is mandatory, use both on a submission endpoint that supports STARTTLS.

## 3. Dangerous “Quick-Fix” Configurations

| Approach | Effect | Why Not Use It to Fix Incidents |
| --- | --- | --- |
| `mail.smtp.ssl.trust=*` | Configures the SMTP provider to trust all hosts per its SSL socket factory mechanism | Bypasses standard trust-chain verification guardrails |
| `mail.smtp.ssl.trust=smtp.example` | Trusts a specified host via a special mechanism | Can still bypass CA validation without proving a valid chain |
| `mail.smtp.ssl.checkserveridentity=false` | Disables certificate hostname checks via the JavaMail property | Hostname mismatches can be ignored |
| Trust-all `X509TrustManager` | Accepts any leaf/issuer | Forged, expired, or self-signed certs can be accepted |
| Hostname verifier always returning `true` | Disables identity verification | Cannot tell if the server is the intended host |
| `starttls.required=false` when policy requires TLS | Allows opportunistic STARTTLS | Risks continuing over an un-upgraded connection |
| Retrying plaintext after handshake error | Weakens security policy during an incident | A TLS error is no reason to transmit data less securely |

### 3.1. Anti-Pattern: Trusting Every SMTP Host

**Insecure configuration example — for recognition only, do not deploy:**

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.ssl.trust]": "*"
~~~

If the `PKIX` error disappears after this change, it only shows that part of verification was skipped. It **does not prove the certificate is genuine, the server name is right, or communication is secure**.

### 3.2. Anti-Pattern: Disabling Hostname Checks

**Example not to do:**

~~~properties
spring.mail.properties.mail.smtp.ssl.checkserveridentity=false
~~~

When the certificate SAN does not match, fix **`spring.mail.host`, DNS/alias, or the server-side certificate**. If the server only presents a certificate for the provider's official hostname, connect using that hostname instead of an arbitrary alias.

### 3.3. Anti-Pattern: Writing a Custom Trust-All Socket Factory

Some projects inject a custom `SSLSocketFactory`/`SSLContext` built from an `X509TrustManager` that accepts any chain. This hides configuration errors and makes TLS auditing difficult.

Prefer **default JSSE with a managed truststore**, or a reviewed dedicated TLS context that still validates both the chain **and** hostname. Never turn a test workaround into production behavior.

### 3.4. Is “Disabling Only on CI” Okay?

That depends on **the goal of the test**:

- Unit tests rendering MIME or sending to a loopback mock SMTP server without testing TLS can use a plaintext test server and an isolated test profile with no real credentials/emails.
- Integration tests **verifying TLS** must keep certificate chain and hostname verification enabled, using proper test CAs/test certificates.

You cannot claim TLS tests passed if they only pass after enabling `ssl.trust=*`.

## 4. Choosing the Right SMTP Port and TLS Mode

Two common mechanisms:

| Common Port | Mechanism | Sequence |
| --- | --- | --- |
| **587** | SMTP submission + STARTTLS | TCP → SMTP greeting/EHLO → STARTTLS → TLS handshake → AUTH |
| **465** | SMTP submission + implicit TLS | TCP → immediate TLS handshake → SMTP greeting/EHLO over TLS → AUTH |
| **25** | SMTP relay/server-to-server | Depends on server, routing, and policy; not a default submission port |

The actual port must follow SMTP provider documentation. Some enterprises use custom endpoints/ports.

### 4.1. STARTTLS on 587

~~~text
Client                          SMTP server
  |-------- TCP -------------------->|
  |<------- 220 greeting -----------|
  |-------- EHLO ------------------>|
  |<------- STARTTLS offered -------|
  |-------- STARTTLS -------------->|
  |<------- 220 Ready -------------|
  |========== TLS handshake ========|
  |-------- EHLO over TLS --------->|
  |-------- AUTH over TLS --------->|
  |-------- MAIL/RCPT/DATA -------->|
~~~

If `mail.smtp.ssl.enable=true` is used against an endpoint **expecting a plaintext SMTP greeting**, the client sends a TLS ClientHello at the wrong moment and hits handshake errors, timeouts, or `Unsupported or unrecognized SSL message`. Seeing “SSL” in an error does not always mean certificate trust is broken.

### 4.2. Implicit TLS on 465

~~~text
Client                          SMTP server
  |-------- TCP -------------------->|
  |========== TLS handshake ========|
  |<------- 220 greeting over TLS --|
  |-------- EHLO/AUTH/DATA -------->|
~~~

Trying to start plaintext/STARTTLS against an endpoint expecting TLS from the first byte also fails. Fix the protocol mode, **do not disable verification**.

### 4.3. Do Not Infer from the Port Alone That TLS Was Enforced

Even with the right port configured, verify negotiation, certificate chain, and hostname. Never permit falling back to plaintext against policy. When changing providers or relays, verify the new endpoint truly supports the desired mode.

## 5. Safe Spring Boot Configuration for STARTTLS 587

`application.yml` example:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    protocol: smtp
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

Explanation:

- `spring.mail.host` must match the SMTP service's valid hostname and certificate SAN.
- `port=587` must match the STARTTLS mechanism published by the provider.
- `mail.smtp.auth=true` enables SMTP AUTH when using credentials.
- `starttls.enable=true` allows protocol upgrade.
- `starttls.required=true` refuses to proceed if TLS cannot be upgraded.
- `ssl.checkserveridentity=true` enforces hostname identity checking in the Jakarta Mail SMTP provider.
- Timeouts prevent workers from waiting indefinitely on network I/O.
- `SMTP_USERNAME` and `SMTP_PASSWORD` are injected from a secure secret manager/environment, never committed to source control.

**There is no `mail.smtp.ssl.trust=*` and no custom trust-all manager.** The JVM must have valid trust anchors for the chain presented by the SMTP provider.

### 5.1. Why Use Bracket Syntax?

Jakarta Mail reads property keys like `mail.smtp.starttls.required`. In Spring Boot YAML, using:

~~~yaml
properties:
  "[mail.smtp.starttls.required]": "true"
~~~

preserves keys containing dots when binding into the `Map` properties. The equivalent in `application.properties`:

~~~properties
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

If the application creates multiple `JavaMailSender` beans manually, check which properties are actually bound to the **right** sender. Do not edit only the default YAML while code uses a custom sender that ignores those properties.

### 5.2. If STARTTLS Is Not Seen from the Server

When `required=true`, the application should fail rather than quietly sending plaintext. Investigate:

- whether hostname/port point to the right submission endpoint;
- whether the provider advertises STARTTLS;
- whether a proxy/firewall/TLS inspection alters the SMTP session;
- whether a load balancer routes to a misconfigured node;
- whether account/region/provider policy requires a different port.

Do not set `required=false` just to make the send job “succeed”.

## 6. Safe Spring Boot Configuration for Implicit TLS 465

If the provider publishes SMTP submission over TLS from the outset:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 465
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

`mail.smtp.ssl.enable=true` creates a TLS connection as soon as the socket opens. Do not use STARTTLS to upgrade a connection that already uses implicit TLS.

Some legacy JavaMail projects use the `smtps` protocol with the `mail.smtps.*` prefix. With `JavaMailSenderImpl` using protocol `smtp` and `mail.smtp.ssl.enable=true` as shown above, properties start with `mail.smtp.*`. **Do not mix prefixes arbitrarily**; verify the actual SMTP provider protocol/version.

## 7. Creating `JavaMailSenderImpl` Manually

When a dedicated sender profile is needed or Boot auto-configuration is not used:

~~~java
package com.example.mail.config;

import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpSenderFactory {
    private SmtpSenderFactory() {}

    public static JavaMailSenderImpl createStartTlsSender(
            String hostname,
            String username,
            String password) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setProtocol("smtp");
        sender.setHost(hostname);
        sender.setPort(587);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties p = sender.getJavaMailProperties();
        p.put("mail.smtp.auth", "true");
        p.put("mail.smtp.starttls.enable", "true");
        p.put("mail.smtp.starttls.required", "true");
        p.put("mail.smtp.ssl.checkserveridentity", "true");
        p.put("mail.smtp.connectiontimeout", "5000");
        p.put("mail.smtp.timeout", "10000");
        p.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

Usage example:

~~~java
JavaMailSenderImpl sender =
        SmtpSenderFactory.createStartTlsSender(
                "smtp.provider.example",
                smtpUsername,
                smtpPassword);
~~~

This is a configuration template; it does not yet include multi-sender routing, secret rotation, proxies, monitoring, or provider-specific OAuth2. Credentials must come from an appropriate secure source and never be logged.

### 7.1. Notes on Hostname and Socket Factory

If connecting to a proxy using `smtp.internal` while the certificate only has SAN `smtp.provider.example`, hostname verification will fail. Use the **infrastructure-published endpoint identity with a valid certificate**, or configure the proxy/certificate accordingly.

Never attach a trust-all custom `SSLSocketFactory` to the sender to bypass this mismatch.

## 8. Classifying Errors Before Fixing

“Cannot send email” is not enough to identify a TLS error. Read the nested exceptions from Spring Mail and Jakarta Mail.

| Common Message | Likely Cause | What to Check |
| --- | --- | --- |
| `PKIX path building failed` | Missing trust path, CA/intermediate, truststore | Server chain and JVM truststore |
| `unable to find valid certification path` | Trust anchor not found | CA, truststore, proxy |
| `No name matching ... found` | Hostname mismatch | Configured host and SAN |
| `No subject alternative DNS name matching` | Inappropriate SAN | DNS/IP endpoint and certificate |
| `CertificateExpiredException` | Expired certificate | Chain, rotation, and clock |
| `CertificateNotYetValidException` | Not yet within validity period | Validity/clock |
| `handshake_failure` | Protocol, cipher, certificate, mTLS, or policy | TLS capabilities on both sides |
| `protocol_version` | Incompatible TLS protocol version | JDK/server/TLS policy |
| `Unsupported or unrecognized SSL message` | Wrong implicit TLS vs STARTTLS, endpoint, or proxy | Host, port, mode |
| `Could not convert socket to TLS` | STARTTLS handshake error | Nested cause, server EHLO, and chain |
| `STARTTLS is required but host does not support STARTTLS` | STARTTLS not advertised | Server/port/proxy |
| `MailAuthenticationException` / `535` | Username/password/OAuth/account policy | SMTP AUTH, not just cert |
| `Connection refused` | TCP endpoint not accepting connections | Firewall, host, port |
| `Connect timed out` | Network/routing or unresponsive service | Pre-TLS connectivity |
| `Read timed out` | Server unresponsive in time or wrong mode | Network/protocol phase |

### 8.1. `PKIX path building failed` Example

~~~text
org.springframework.mail.MailSendException:
  Mail server connection failed
Caused by: javax.net.ssl.SSLHandshakeException:
  PKIX path building failed
Caused by:
  SunCertPathBuilderException:
  unable to find valid certification path to requested target
~~~

This signals a failure to build a trust chain. Investigate whether the server is missing an intermediate, the JVM is missing a CA, a custom truststore is wrong, or TLS inspection is presenting a different certificate.

### 8.2. Hostname Mismatch Example

~~~text
Connected host: mail.company.internal
Presented SAN:
  DNS:smtp.provider.example
~~~

The chain may be valid while the hostname mismatches. The fix is to use the right endpoint or issue a valid certificate for the internal hostname, not drop `checkserveridentity`.

### 8.3. AUTH Error Example

~~~text
535 5.7.8 Authentication credentials invalid
~~~

Check credentials, account, OAuth scopes, SMTP AUTH policy, and sending permissions. Do not alter CA trust or weaken TLS verification when the problem is the SMTP account.

### 8.4. Wrong TLS Mode Example

~~~text
App: port 587 + implicit TLS ClientHello
SMTP relay: waiting for plaintext SMTP greeting
=> handshake timeout / unrecognized SSL message
~~~

Fix the mode to port 587 STARTTLS or endpoint 465 implicit TLS per provider documentation.

## 9. Diagnostic Runbook When SMTP TLS Fails

~~~mermaid
flowchart TD
    A["SMTP send error"] --> B{"TCP connect to host/port?"}
    B -->|No| C["DNS, firewall, routing, port"]
    B -->|Yes| D{"TLS mode right?"}
    D -->|No| E["STARTTLS vs implicit TLS"]
    D -->|Yes| F{"Handshake + certificate verification"}
    F -->|PKIX| G["CA / chain / truststore / proxy"]
    F -->|Hostname| H["SAN / DNS / SNI / alias"]
    F -->|TLS protocol| I["JVM / TLS versions / ciphers"]
    F -->|Success| J{"SMTP AUTH?"}
    J -->|Failure| K["Credentials, token, account policy"]
    J -->|Success| L["SMTP response / job outcome"]
~~~

### Step 1: Collect Event Details

Record:

- timestamp of the error and affected sender profile;
- intended hostname/port/TLS mode;
- JDK and JavaMail/Jakarta Mail provider versions;
- execution environment: laptop, CI, VM, or Kubernetes;
- exception class and nested causes scrubbed of secrets;
- provider endpoint/region if multiple exist;
- recent changes: certificate rotation, truststore, deploy, proxy;
- number of jobs queued due to the error.

Never dump full email MIME/OTPs/passwords into tickets just to debug certificates.

### Step 2: Verify the Endpoint

Check SMTP provider documentation and compare:

- published hostname;
- required submission port;
- STARTTLS vs implicit TLS;
- certificate SAN presented by the server;
- whether IP allowlist, mTLS, or internal proxy is required.

Check DNS/CNAME and network routing. An internal alias pointing to the same IP does not automatically make another hostname's certificate valid.

### Step 3: Verify TCP

On Windows you can run:

~~~powershell
Test-NetConnection smtp.provider.example -Port 587
~~~

A successful TCP check **is not** a successful TLS handshake and does not validate SMTP authentication. If TCP fails to connect, investigate DNS, firewall, network policies, proxy, or port first.

### Step 4: Inspect Certificate and Hostname Independently

Use OpenSSL with the exact host, port, and TLS mode as in section 10. Compare the results with what the Java application sees; do not assume OpenSSL and the JVM share the same trust anchors.

### Step 5: Check the Actual Truststore of the Java Process

A Docker image may carry a different `cacerts` than the host OS or workstation. A custom `javax.net.ssl.trustStore` can replace the default CA set. Confirm the **exact process** and **exact path** in use before importing any certificate.

### Step 6: Fix Root Cause, Stay Fail-Closed

| Root Cause | Primary Fix |
| --- | --- |
| Hostname does not match SAN | Fix host/endpoint or server certificate |
| Missing intermediate | Fix full chain served by the server |
| Trusted internal CA missing from Java | Add verified CA to the proper truststore |
| Expired certificate | Rotate certificate on the server |
| Skewed clock | Synchronize system time |
| Wrong port/TLS mode | Use proper STARTTLS or implicit TLS |
| STARTTLS blocked by proxy | Fix proxy/network route or use approved endpoint |
| TLS cipher/protocol mismatch | Upgrade or align per security policy |
| AUTH failed after TLS | Fix account/credential/permission/token |

### Step 7: Verify Recovery

~~~text
TCP connectivity          OK
Expected TLS mode         OK
Certificate chain         TRUSTED
Hostname                  MATCHES
Required TLS              NEGOTIATED
SMTP authentication       OK
SMTP submission           ACCEPTED
~~~

Then monitor outbox backlog, retries, and delivery events. Successful SMTP submission still does not prove the message reached the Inbox.

## 10. Using OpenSSL to Test STARTTLS/SMTPS

Commands require an OpenSSL version supporting the flags. They only check the endpoint from the machine running the command; production JVMs may use a different truststore.

### 10.1. Port 587 — STARTTLS

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.provider.example:587 \
  -servername smtp.provider.example \
  -verify_hostname smtp.provider.example \
  -verify_return_error \
  -showcerts
~~~

- `-starttls smtp` performs the SMTP upgrade step.
- `-connect` specifies host/port.
- `-servername` sends SNI when appropriate.
- `-verify_hostname` checks the certificate against the host.
- `-verify_return_error` exits with error if certificate validation fails.
- `-showcerts` prints certificates presented by the server.

Do not look solely at `Verify return code: 0` if hostname verification wasn't enabled. OpenSSL's hostname must match the application's `spring.mail.host`.

### 10.2. Port 465 — Implicit TLS

~~~bash
openssl s_client \
  -connect smtp.provider.example:465 \
  -servername smtp.provider.example \
  -verify_hostname smtp.provider.example \
  -verify_return_error \
  -showcerts
~~~

Do not add `-starttls smtp` for a 465 implicit TLS endpoint unless the provider documents a different mode.

### 10.3. SMTP Relay Signed by a Private CA

If the organization uses a verified private CA:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.internal.example:587 \
  -servername smtp.internal.example \
  -verify_hostname smtp.internal.example \
  -verify_return_error \
  -CAfile approved-internal-ca.pem \
  -showcerts
~~~

**`approved-internal-ca.pem` must come from a trusted PKI channel**, not be downloaded directly from the suspect endpoint and automatically trusted.

### 10.4. OpenSSL OK Yet Spring Still Throws PKIX

Possible reasons:

- OpenSSL uses the OS CA store, whereas Java uses its own `cacerts`;
- older JDK/container versions lack newer root CAs;
- the Java process has a custom `javax.net.ssl.trustStore`;
- a custom truststore lacks required public CAs;
- the app and CLI tool connect via different hosts/ports/routes/proxies;
- the server returns different certificates depending on SNI/load balancer backend.

To verify, run from the closest matching environment/container possible and read controlled JSSE debug output.

## 11. JVM Truststore and Keystore

| Component | Typically Holds | Role |
| --- | --- | --- |
| **Truststore** | Trusted CA certificates/trust anchors | Verifies server certificates |
| **Keystore** | Client certificate/private key | Used when client certificates/mTLS are required |

For standard SMTP AUTH, the Spring application does not need to present a client certificate; it needs to **trust the right SMTP server** and provide the AUTH mechanism required by the provider.

### 11.1. Default Truststores Can Differ by Environment

Many JDKs/JREs load trust anchors from `cacerts` relative to `java.home`, though packaging depends on vendor, distribution, and Java system properties. Never assume a containerized JVM uses the host machine's CA certificates.

An example path:

~~~text
<java.home>/lib/security/cacerts
~~~

Inspect the **actual** runtime/truststore of the application instead of editing a file on a workstation.

### 11.2. Inspecting with `keytool`

~~~bash
keytool -list -v \
  -keystore /secure/path/mail-truststore.p12 \
  -storetype PKCS12
~~~

Verify alias, Subject, Issuer, SHA-256 fingerprint, validity dates, and trust policy. Protect truststore passwords; avoid putting passwords in command lines, logs, or tickets.

### 11.3. Importing a Verified Internal CA

~~~bash
keytool -importcert \
  -alias approved-internal-smtp-ca \
  -file approved-internal-ca.pem \
  -keystore /secure/path/mail-truststore.p12 \
  -storetype PKCS12
~~~

The workflow should include:

1. Obtaining the CA certificate from an authoritative PKI source.
2. Verifying fingerprint and usage policy via an independent channel.
3. Confirming the exact CA/chain that needs to be trusted.
4. Importing into an operations-controlled truststore.
5. Configuring the JVM to use the truststore if needed.
6. Confirming hostname verification remains enabled.
7. Regression-testing related TLS connections.
8. Recording the change and certificate rotation process.

**Never import an unknown leaf certificate** just to silence errors. Trusting a leaf grabbed off a suspect network path does not prove it is the real server, and it causes outages when the provider rotates certificates.

### 11.4. Pointing the JVM to a Truststore

Example Java system properties:

~~~text
-Djavax.net.ssl.trustStore=/secure/path/mail-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

When the truststore requires a password, the runtime may need `javax.net.ssl.trustStorePassword`, supplied via an appropriate secret-injection mechanism. Never write plaintext passwords in source code or logs.

**Warning:** a custom truststore can replace the default CA roots for the entire JVM. If the new file only contains one private CA, other HTTPS or public SMTP connections may start failing. Actively manage **all required trusted roots** or use a reviewed per-sender TLS context.

### 11.5. Why Not Use a Trust-All Factory Instead?

Because it removes the certificate verification boundary, making CA rotations, hostname mismatches, network attacks, and misconfigurations all look like “connection succeeded”. Those errors need to be surfaced and fixed, not hidden.

## 12. Server Missing Intermediate Certificate

A fairly common error is a server sending only its leaf certificate:

~~~text
Server sends:
    Leaf: smtp.provider.example

Expected chain:
    Leaf -> Intermediate CA -> Trusted Root CA

Missing:
    Intermediate CA
~~~

Some desktop clients can locate intermediates via cache or AIA; Java containers may fail to do so and throw `PKIX`. The preferred fix is usually **fixing the full chain on the SMTP server/load balancer**, not importing leaf certificates onto every client.

### 12.1. Multiple SMTP Backends with Different Certificates

~~~text
smtp.provider.example
       |
       +-- backend A: chain valid
       +-- backend B: intermediate missing
       +-- backend C: certificate expired
~~~

Errors may appear intermittent due to load balancing. Inspect certificates across the relevant routes/nodes and coordinate with the provider. Do not hastily call Spring Mail “flaky” and turn off verification.

### 12.2. A Chain Sent by the Server Is Not Automatically Trusted

`-showcerts` only displays the certificates the server presents; it does not prove they are all valid. Validation against independent trust anchors and hostname verification are still required.

## 13. Hostname, SAN, DNS CNAME, IP, and SNI

### 13.1. Provider's Official Hostname

~~~text
Provider submission host: smtp.provider.example
Presented SAN:            DNS:smtp.provider.example
~~~

In this case `spring.mail.host=smtp.provider.example` is usually the right choice. Do not switch to the server's IP or an internal alias just to avoid DNS and then turn off `checkserveridentity`.

### 13.2. A CNAME Does Not Make a Certificate Valid for the Alias

~~~text
mail.company.example CNAME smtp.provider.example
~~~

A certificate containing only `DNS:smtp.provider.example` is not automatically valid when the client connects to **`mail.company.example`**. DNS mapping and certificate identity are two separate concerns.

Right options:

- use the provider's official hostname;
- or obtain a valid certificate for the custom alias as supported by the service;
- never disable hostname verification.

### 13.3. Using an IP Address

If the application connects to `10.20.30.40`, the certificate needs a matching IP identity per verifier rules. A certificate with only a DNS SAN will not be accepted for an IP. If the provider publishes a hostname, use that hostname.

### 13.4. SNI and Another Server's Certificate

A multi-tenant SMTP service may pick a certificate based on Server Name Indication. If the app and diagnostic tool send different SNIs, results can differ. Cross-check hostname, endpoint, SNI, and the actual presented certificate; never use `ssl.trust=*` to ignore a “wrong-tenant” certificate.

### 13.5. Wildcard Certificates

A `*.example.com` certificate may match `smtp.example.com` but does not by default match `smtp.eu.example.com`. Do not assume “same base domain” means valid; check the SAN and wildcard matching rules.

## 14. Expired, Not-Yet-Valid Certificates, and Clock Skew

Certificates have a `Not Before` and `Not After` window. If the certificate or an intermediate expires, validation fails. If the system clock is skewed, a genuinely valid certificate may appear not yet valid.

~~~text
Certificate:
  Not Before: 2026-11-01
  Not After:  2026-12-01

Application clock:
  2026-10-01

=> May report certificate not yet valid.
~~~

Remediation steps:

- check NTP/time synchronization;
- check actual time on the host/VM/container;
- verify leaf and intermediate validity;
- verify whether the provider rotated its certificate;
- perform rotations before expiration.

Never use trust-all to “ignore an expired certificate”, as subsequent cert changes may leave the app talking to the wrong endpoint.

### 14.1. Planned Rotation

For a private CA:

1. Add the newly approved CA to the truststore during an overlap window.
2. Deploy the updated app/JVM image and confirm clients trust the new chain.
3. Rotate the certificate on the SMTP server.
4. Monitor handshake success across all regions/replicas.
5. Revoke/remove the old CA per policy after the transition period.

Track certificate expiration dates so you never resort to emergency workarounds.

## 15. Corporate Proxies and TLS Inspection

Some networks run TLS interception appliances:

~~~text
Spring application
      |
      v
Corporate inspection proxy
      |
      v
SMTP provider
~~~

The client may see a certificate signed by a corporate CA instead of the SMTP provider's direct chain. If this is an **approved** architecture, work with the security team to:

- verify the proxy and CA truly belong to the organization;
- verify certificate SANs still match the hostname;
- install the right corporate CA into the truststore if policy permits;
- confirm whether inspecting SMTP AUTH/email content is permitted.

If interception is not permitted for mail submission traffic, fix the route/proxy policy or design an approved bypass. **Never blindly trust a new CA simply because a proxy presented it to the client.**

### 15.1. Laptop OK, Container Fails

~~~text
Developer laptop: SMTP TLS OK
CI container:     PKIX path building failed
Production pod:   SMTP TLS OK
~~~

CI may use an older image/JVM, lack the corporate CA, have a mis-mounted truststore, or traverse a different route/proxy. Verify the exact failing environment and certificate policy; never make `ssl.trust=*` a default environment variable in CI or production.

## 16. TLS Protocol/Cipher Mismatch

`SSLHandshakeException` is not always a CA error. The server and JVM may lack a common protocol/cipher or have conflicting security policies.

~~~text
Client: TLS 1.2, TLS 1.3
Server: TLS 1.0 only
=> No mutually secure version.
~~~

Remediation steps:

- upgrade the SMTP relay/provider;
- use a supported JDK/Jakarta Mail/provider version;
- verify TLS 1.2/1.3 per policy;
- check Java security disabled algorithms/cipher suites;
- check whether the endpoint requires a client certificate (mTLS);
- review load balancer/proxy TLS termination.

A related property:

~~~properties
mail.smtp.ssl.protocols=TLSv1.2 TLSv1.3
~~~

This is an example of protocol selection where **the JVM/provider actually supports it and policy permits**. Never force TLS 1.0/1.1 just to talk to a legacy server; prioritize upgrading the server.

### 16.1. Disabling Verification Does Not Fix Cipher Mismatches

Dropping chain/hostname validation does not give the two sides a shared cipher suite or fix TLS handshake mechanics. If `handshake_failure` occurs before certificate validation, trust-all can even obscure the real investigation path.

## 17. SMTP AUTH Mechanisms and OAuth2

Providers may require:

- dedicated SMTP username/password;
- OAuth2/XOAUTH2 tokens;
- SMTP AUTH permissions on the mailbox/tenant;
- network allowlists;
- sender identity/Send As policies.

These failures must be classified separately from TLS. `535 5.7.x` typically relates to authentication and cannot be fixed by importing an arbitrary CA.

If the app uses OAuth tokens, they must carry valid scopes/audiences/permissions and be refreshed properly. Never log access tokens in debug traces or public telemetry.

## 18. TLS Debugging in Java

When you need to observe the handshake, Java offers debug system properties:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

And to inspect certificate path building:

~~~text
-Djava.security.debug=certpath
~~~

These are **temporary, controlled** diagnostic options, not long-term production defaults.

### 18.1. What to Read in the Debug Output?

- certificate chain presented by the server;
- issuer, signature, validity, and trust path;
- hostname/SNI;
- negotiated TLS protocol and cipher;
- exact point where the handshake failed;
- whether STARTTLS occurred prior to the handshake;
- discrepancies between the actual and expected truststore.

Avoid printing raw SMTP AUTH exchanges, tokens, bodies/attachments, OTPs, or recipient lists. If protocol debugging is necessary, use an isolated environment/case, a short window, and restricted log access.

### 18.2. Root Cause Usually Sits Beneath Spring's Wrapper Exception

~~~text
MailSendException
  -> MailConnectException
      -> MessagingException
          -> SSLHandshakeException
              -> CertPathBuilderException
~~~

The exact exception path depends on provider/version. Looking only at the outermost exception name easily confuses TCP connection failures with certificate validation failures. Locate the deepest meaningful nested cause to classify the error.

## 19. Distinguishing SMTP TLS from SPF, DKIM, and DMARC

| Mechanism | Meaning |
| --- | --- |
| TLS Spring → SMTP provider | Secures and authenticates the sending connection |
| SMTP AUTH | Authenticates the authorized sending account |
| SPF | Verifies authorized sending servers per domain policy |
| DKIM | Cryptographic signature on email headers/content tied to a domain |
| DMARC | Policy combining SPF/DKIM alignment |

Valid SPF/DKIM/DMARC does not prove the SMTP endpoint's certificate was verified; valid TLS does not guarantee Inbox delivery or DKIM signing. When investigating `PKIX`, focus on transport TLS first rather than making unrelated DNS email authentication changes.

## 20. Testing TLS in Spring Mail

### 20.1. Unencrypted Local SMTP Tests

Unit/integration tests checking MIME rendering or basic submission can use loopback servers like GreenMail/Mailpit running plaintext **in an isolated test environment** without real credentials/recipients. Such tests do not prove production TLS.

~~~text
JUnit -> local SMTP test server (127.0.0.1)
      -> Assert subject, recipients, MIME parts
~~~

Never conclude “TLS was tested” just because mail appeared in a test mailbox.

### 20.2. Real TLS Testing

A proper TLS test should:

1. Create a controlled test CA/PKI fixture.
2. Issue a server certificate with a SAN matching the test hostname.
3. Configure the SMTP test server to support STARTTLS or implicit TLS.
4. Configure the test JVM truststore to trust the **test CA**, not every certificate.
5. Connect using the SAN-matching hostname.
6. Verify a valid certificate is accepted.
7. Verify a mismatched hostname or untrusted CA is rejected.
8. Verify `STARTTLS required` prevents plaintext continuation.

### 20.3. Scenarios Worth Testing

| Scenario | Expectation |
| --- | --- |
| Valid server cert, trusted CA, matching SAN | Handshake succeeds |
| Untrusted self-signed cert | Handshake fails |
| Certificate from unknown CA | Rejected |
| SAN lists only host A, client connects to host B | Rejected |
| Expired / not-yet-valid certificate | Rejected |
| Server lacks STARTTLS when required | Fail closed |
| Port 587 mistakenly runs implicit TLS | Fails with appropriate mode/protocol error |
| Port 465 implicit TLS configured right | Handshake can succeed |
| Wrong SMTP AUTH while TLS is valid | Auth failure without changing TLS policy |
| Provider rotates to a new trusted CA | Connection remains valid |

Spring Mail typically wraps transport errors in `MailException` subclasses. Tests can verify the error category and nested cause without hardcoding one fixed TLS exception class across all providers.

### 20.4. Testing Certificates on `localhost`

If a certificate has only `DNS:smtp.test.internal` while the app connects to `127.0.0.1`, hostname verification failing is expected behavior. Issue a certificate with IP SAN `127.0.0.1`, or configure an appropriate test hostname/network alias; no need to disable verification.

### 20.5. Cleanup

After tests:

- stop test servers/containers via the proper owner;
- close test-managed resources;
- clean up fixture mailboxes, jobs/outbox entries, and attachments;
- remove temporary test truststore/cert files per lifecycle;
- avoid parallel tests sharing a single mutable port/truststore;
- avoid purging an entire shared SMTP server while other tests run.

## 21. Operating When SMTP TLS Fails in Production

A certificate error can leave thousands of mail jobs stuck in an outbox. The right response is to **preserve data and fix transport trust**, not disable verification.

~~~text
09:00 Certificate expired or truststore misconfigured.
09:01 SMTP worker hits SSLHandshakeException.
09:05 Retry backlog starts growing.
09:10 On-call receives alert.

What to do:
  - Pause aggressive retries on the failing sender.
  - Keep durable jobs intact.
  - Verify chain/hostname/TLS mode.
  - Fix certificate/truststore/proxy.
  - Resume sender with backoff and watch backlog.
~~~

### 21.1. Suggested Metrics

| Application-Instrumented Metric | Purpose |
| --- | --- |
| `mail_submission_attempts_total` | Volume of transport attempts |
| `mail_tls_handshake_failures_total` | Handshake failures by error class |
| `mail_sender_healthy` | Health per sender profile |
| `mail_outbox_pending` | Incomplete jobs |
| `mail_outbox_oldest_pending_age_seconds` | Age of backlog |
| `mail_retry_scheduled_total` | Retries and backoff |
| `mail_jobs_expired_total` | Jobs expired during incident |

These names are implementation suggestions, **not default metrics on every Spring Mail application**. Labels should be bounded enums like `sender_profile`, `error_class=pkix|hostname|protocol|auth`, and `mail_type`; never raw exception messages, recipients, OTPs, or passwords.

### 21.2. Conditional Failover

If a backup sender is configured and tested:

~~~text
primary SMTP -> certificate problem
backup SMTP  -> valid TLS certificate + approved account
~~~

Part of the traffic can shift to backup per runbook, provided you verify **From/Send As permissions, quotas, deliverability, and idempotency**. Prior attempts with an `UNKNOWN` outcome must not be blindly re-sent through backup because the primary provider may have accepted them.

### 21.3. Due Mail and Expired Tokens

An OTP meant to arrive within 30 seconds may be useless if a TLS outage lasts 20 minutes. During recovery:

- evaluate `expires_at`;
- do not send expired OTPs/tokens;
- record expired/suppressed states per policy;
- send a fresh notification only when the business workflow actually requires it, with a new intent;
- never delete pending jobs silently without auditing.

### 21.4. Do Not Use a Circuit Breaker to Mask Errors

A circuit breaker reduces retry storms when a sender continuously fails TLS, yet it does not solve certificate validation. After fixing infrastructure, **verify the handshake with full verification enabled** before gradually reopening traffic.

## 22. Certificate Rotation Process

To prevent routine expirations from turning into emergencies, manage the TLS lifecycle:

1. Inventory SMTP hosts/ports/providers/sender profiles.
2. Track `Not After` dates and server/CA rotation schedules.
3. Validate the chain and SANs of upcoming certificates.
4. When changing CAs, deploy new trust anchors before server rotation if needed.
5. Maintain a CA overlap window per policy.
6. Rotate the server certificate/full chain.
7. Verify from representative containers/JVMs in every region.
8. Monitor TLS failure rates and submission backlogs.
9. Remove old trust anchors once complete per policy.
10. Audit the change, owner, rollback plan, and verification results.

A well-managed CA rotation never requires enabling trust-all on clients.

## 23. Typical Scenarios

### Scenario A: Laptop Sends Fine, Docker Throws PKIX

~~~text
Laptop:
  Up-to-date OS/JDK CA store -> SMTP OK.

Docker:
  Older JRE image missing CA -> PKIX error.
~~~

Fix: inspect the JRE and truststore inside the image, update trusted CAs or use an up-to-date base image, compare host/port/proxy, redeploy, and verify hostname. Do not fix with `ssl.trust=*`.

### Scenario B: Switching Hostname to IP

~~~text
Before:
  smtp.provider.example
  Certificate SAN = DNS:smtp.provider.example

After:
  10.10.10.8
  Certificate lacks matching IP SAN
  => Hostname verification failed
~~~

Revert to the published hostname and valid DNS/network route. Do not drop `checkserveridentity`.

### Scenario C: Server Missing Intermediate

~~~text
Leaf cert signed by Intermediate CA.
SMTP server sends leaf only.
JVM container cannot build chain.
~~~

Have the operator/provider serve the full chain and verify against trusted anchors. Never trust an unverified leaf certificate just because the error disappears.

### Scenario D: Wrong Mode on Port 587

~~~text
spring.mail.port=587
mail.smtp.ssl.enable=true
Server expects SMTP greeting + STARTTLS
=> Handshake failure/timeout
~~~

Switch to `starttls.enable=true` and `starttls.required=true` per policy. Do not disable certificate validation.

### Scenario E: Corporate TLS Inspection

The presented certificate is signed by a corporate CA. Work with PKI/security teams to verify the endpoint, interception authorization, and CA. If policy allows, add the verified CA to the proper truststore. Otherwise, fix routing or use an approved inspection bypass.

### Scenario F: SMTP AUTH 535 After Successful TLS

This is no longer a trust-chain issue. Check the account, password/OAuth scopes, SMTP AUTH settings, and sender permissions. Do not alter TLS settings to fix an authentication error.

## 24. Checklist for Handling Certificate Errors

### Host and Protocol

- [ ] Hostname in `spring.mail.host` matches the provider endpoint.
- [ ] DNS/CNAME/IP/SNI and actual network route checked.
- [ ] Port 587 uses STARTTLS if specified by provider.
- [ ] Port 465 uses implicit TLS if specified by provider.
- [ ] Mandatory STARTTLS sets `mail.smtp.starttls.required=true`.
- [ ] No unauthorized fallback to plaintext.

### Certificate Validation

- [ ] `mail.smtp.ssl.checkserveridentity=true` is enabled.
- [ ] `mail.smtp.ssl.trust=*` is not set.
- [ ] No custom trust-all manager or hostname verifier exists.
- [ ] Leaf certificate SAN matches the host.
- [ ] Chain includes valid intermediates and trust anchor.
- [ ] Certificate is within validity dates; system clock is accurate.
- [ ] Internal CAs were verified independently before importing.
- [ ] Actual JVM/container truststore has been identified.

### Diagnostics

- [ ] Read root cause beneath `MailException`.
- [ ] Verified TCP before assuming TLS issues.
- [ ] Used OpenSSL in the right STARTTLS/implicit TLS mode.
- [ ] Verified hostname in OpenSSL, not just chain.
- [ ] Distinguished PKIX, hostname, protocol, auth, and network errors.
- [ ] Debug logs do not leak credentials/OTPs/bodies.

### Operations

- [ ] Owner assigned for certificate/CA rotation.
- [ ] Monitoring exists for certificate expiry and TLS handshake failures.
- [ ] Outbox preserves jobs during TLS failures.
- [ ] Retries use backoff to avoid storms.
- [ ] Expired/suppressed jobs are handled properly.
- [ ] Failover only targets senders with valid TLS and authorization.
- [ ] Security tests prove invalid certificates **are rejected**.

## 25. Key Takeaways

- **Disabling TLS verification to bypass certificate errors is a dangerous anti-pattern in Spring Framework Mail.**
- TLS encryption alone is insufficient if the client does not verify the certificate chain and hostname.
- `mail.smtp.ssl.trust=*` and trust-all managers hide errors while removing server authentication safeguards.
- `mail.smtp.ssl.checkserveridentity=true` enforces server identity verification; on hostname mismatch, fix host/SAN.
- On port **587**, typically use STARTTLS and set `starttls.required=true` when policy requires TLS.
- On port **465**, typically use implicit TLS with `mail.smtp.ssl.enable=true`.
- `PKIX path building failed` calls for inspecting the CA chain, intermediates, truststore, and proxy — not importing arbitrary certificates.
- JVMs/containers can use a different truststore than a local machine or OpenSSL.
- Expired certificates, wrong SNI/hostname, TLS protocol mismatches, and SMTP AUTH failures are distinct error classes.
- Internal CAs must be verified via trusted channels before import; plan rotations and expiry alerts.
- A proper TLS integration test must reject untrusted or hostname-mismatched certificates.
- When failures happen in production, preserve durable mail jobs, back off retries, and fix the root cause; never weaken security just to boost send volume.

**Conclusion:** a certificate error is a signal to **restore trust with the SMTP server**, not an invitation to disable verification. In Spring Mail, the sustainable solution is the right host, right port/TLS mode, a verified CA chain, a truststore aligned with the actual JVM, enabled hostname verification, and a clear certificate rotation workflow. Fixing the right layer restores mail delivery while protecting credentials and message contents as security expects.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `JavaMailSenderImpl`, and mail exceptions.
- **Spring Boot Reference — Sending Email:** `spring.mail.*`, JavaMail properties, and timeouts.
- **Jakarta Mail / Eclipse Angus Mail SSL Notes:** `mail.smtp.ssl.trust`, `mail.smtp.ssl.checkserveridentity`, `mail.smtp.starttls.enable`, and `mail.smtp.starttls.required`.
- **Java JSSE Reference Guide:** TLS handshake, trust anchors, truststores, `javax.net.ssl.*`, and debugging.
- **Java keytool Documentation:** `-importcert`, `-list`, `-keystore`, and CA management.
- **RFC 3207 — SMTP Service Extension for Secure SMTP over Transport Layer Security:** STARTTLS.
- **RFC 8314 — Cleartext Considered Obsolete:** using TLS for email submission/access.
- **RFC 9525 — Service Identity Verification:** verifying service identity in certificates.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP transport and submission responses.
- **OpenSSL s_client Documentation:** `-starttls smtp`, `-servername`, `-verify_hostname`, and `-verify_return_error`.
- **SMTP provider and internal PKI documentation:** endpoints, ports, TLS policies, certificate rotation, and authentication.
