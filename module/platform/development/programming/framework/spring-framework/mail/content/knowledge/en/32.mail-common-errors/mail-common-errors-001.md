# Configuring the Right Host but Forgetting the Port or Protocol

In **Spring Framework Mail**, setting `spring.mail.host` correctly is necessary but **not sufficient** to send email successfully. An SMTP endpoint is defined by **hostname, port, transport protocol, TLS initiation method, and authentication mechanism**. If you only enter the hostname and omit the remaining parts, the application may connect to a default port not supported by the provider, wait indefinitely for a response that never arrives, encounter TLS handshake errors, or have authentication rejected.

For example, a provider may publish the same hostname `smtp.example.net` with two different submission methods:

- `smtp.example.net:587`: starts a plain SMTP session, then uses **STARTTLS** to upgrade to TLS before authenticating.
- `smtp.example.net:465`: starts **TLS immediately upon TCP connection**, commonly called implicit TLS or submissions.

If the application connects to the right host but uses the default port 25, or connects to port 465 without enabling implicit TLS, DNS may still resolve normally, yet the sending session will fail. This is a common error because the error message appears at the **TCP, TLS, SMTP, or AUTH** layer, while the developer only checks the hostname.

This lesson explains how to distinguish ports and connection modes, configure Spring Boot and `JavaMailSenderImpl` properly, read error messages, test from the actual runtime environment, write tests to prevent regressions, and troubleshoot email-sending systems with queues/retries.

> **Scope:** This lesson focuses on **SMTP outbound submission** via Spring Mail. When mentioning IMAP/POP3 or HTTP email APIs, we will clarify that these are **different** protocols and cannot replace `smtp` simply because they share a similar hostname. The hostnames, accounts, and domains in the examples are all hypothetical.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why a correct hostname does not prove a valid SMTP connection.
2. Distinguish SMTP relay on port 25, SMTP submission with STARTTLS on port 587, and implicit TLS on port 465.
3. Distinguish `spring.mail.protocol=smtp` from TLS modes `mail.smtp.starttls.*` and `mail.smtp.ssl.*`.
4. Understand the default values of `JavaMailSenderImpl` when no port is specified.
5. Configure `application.yml` correctly for 587/STARTTLS and 465/implicit TLS.
6. Set TLS, hostname verification, SMTP AUTH, and timeout properties consistently.
7. Recognize when the `smtps` protocol is used and the requirement to change the JavaMail property prefix.
8. Avoid confusing `server.port`, `spring.mail.port`, `mail.smtp.port`, or HTTP API ports.
9. Distinguish DNS, TCP, TLS, EHLO/STARTTLS, AUTH, relay permission, and message delivery errors.
10. Diagnose connections using PowerShell, OpenSSL, and controlled logging.
11. Write unit/integration tests that verify the correct combination of host/port/protocol/TLS.
12. Design timeouts, retries, and safe operations when the SMTP provider is unavailable.

## 2. What Choices Make Up an SMTP Connection?

Think of an outbound configuration as a tuple:

```text
SMTP connection profile
|
+-- Hostname: smtp.example.net
|
+-- TCP port: 587
|
+-- Transport protocol: smtp
|
+-- TLS mode: STARTTLS_REQUIRED
|
+-- Authentication: username/password or OAuth2
|
+-- Certificate/hostname verification: enabled
|
+-- Connect/read/write timeouts
|
+-- Sender identity / envelope sender / provider policy
```

Any wrong layer can cause `JavaMailSender.send(...)` to fail. For example:

| Component | Possible Valid Value | Missing or Wrong Leads To |
|---|---|---|
| Host | `smtp.example.net` | DNS resolution failure, wrong endpoint |
| Port | `587` | May unexpectedly attempt port 25 |
| Transport protocol | `smtp` | Cannot find the right provider or uses the wrong property namespace |
| TLS mode | STARTTLS required | Encrypted connection is not established properly |
| Authentication | Authorized account | SMTP `535`, `530`, or relay rejection |
| Hostname verification | Enabled, SAN matches hostname | Untrusted TLS or MITM risk |
| Timeouts | Appropriate bounds | Worker waits too long, backlog grows |
| Sender/domain | Verified at provider | Sending rejected or fails SPF/DKIM/DMARC |

**Host, port, and protocol must be treated as an inseparable configuration group.** Never just swap the host and blindly reuse the old provider's port/TLS mode.

## 3. Common SMTP Ports and Their Purposes

| Port | Common Purpose | Session Start | Recommendation for Spring Mail |
|---|---|---|---|
| **25** | Server-to-server SMTP/relay, sometimes internal relay | Initial plaintext SMTP; may support STARTTLS | Use only when the provider/infrastructure **explicitly allows it** |
| **587** | **SMTP message submission** | SMTP greeting/EHLO then **STARTTLS** | `protocol=smtp`, `starttls.enable=true`, `starttls.required=true` |
| **465** | **Message submission over implicit TLS** | **TLS handshake immediately after TCP connect** | `protocol=smtp` + `mail.smtp.ssl.enable=true`, or `smtps` if configured consistently |
| **2525** | Alternative port on some services | Depends on provider | Use only according to the specific endpoint documentation |

There is no rule that every hostname listens on all ports. Nor should port 2525 be assumed to guarantee STARTTLS or implicit TLS; some providers use it due to network policies, so its semantics must be checked individually.

### 3.1. Port 25 Is Not the Default Choice for Every Application

Port 25 is typically associated with mail transfer between SMTP servers or internal relays. Many cloud/network environments restrict outbound port 25. Even if a provider's SMTP endpoint supports port 25, it may not accept AUTH or application submission in the way you expect.

Therefore, **do not rely on default port 25** for transactional email sent to a submission service unless documented as permitted.

### 3.2. Port 587: STARTTLS

The application opens a TCP connection, reads the SMTP greeting, exchanges EHLO, and requests a TLS upgrade using `STARTTLS`. After valid TLS is established, the client performs SMTP AUTH if required by the provider.

### 3.3. Port 465: Implicit TLS

Immediately after TCP connects, the client must initiate a TLS handshake. If the client waits for a plaintext SMTP greeting while the server waits for a TLS ClientHello, both sides may wait for each other until timeout.

### 3.4. The Port Alone Does Not Determine the Full Policy

Do not write code like:

```java
if (port == 465) {
    // Automatically guess all capabilities or credentials.
}
```

The port is an important parameter, but **the configuration profile published by the provider** remains the authoritative source for TLS mode, AUTH, hostname, and sending permissions.

## 4. Why Forgetting the Port Often Leads to Port 25

In common usage with Spring `JavaMailSenderImpl`, if no port is explicitly configured, the internal value may remain `-1` so that Jakarta Mail/the provider uses its default.

For the standard `smtp` transport, the default port is typically **25**. Therefore:

```yaml
spring:
  mail:
    host: smtp.example.net
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
```

**does not mean** Spring Boot will automatically pick port 587 just because username and password are declared. The library cannot know on its own whether the provider requires 587 or 465.

The flow may look like:

```text
spring.mail.host = smtp.example.net
spring.mail.port = not configured
spring.mail.protocol = smtp (typical default)
                 |
                 v
JavaMailSenderImpl: no explicit port
                 |
                 v
SMTP provider default port: often 25
                 |
                 v
Cloud/network blocks port 25
or provider rejects submission
                 |
                 v
MailSendException / connection timeout / refused
```

### 4.1. Why Is This Error Easily Overlooked?

- The host is right and DNS returns an IP, so the developer assumes the configuration is complete.
- A local machine might allow port 25 while cloud production blocks it.
- Some SMTP sandboxes default to dynamic ports or 1025, making test configuration differ from production.
- A new email service has a similar hostname to the old service but uses a different port/TLS mode.
- Having username/password configured leads the developer to assume the library automatically chooses the submission port.
- Logs say “Could not connect to SMTP host” without being read down to the `port: 25` part.

### 4.2. Reading the Port in the Exception

When seeing an error like:

```text
MailSendException: Mail server connection failed
...
Could not connect to SMTP host: smtp.example.net, port: 25
```

the key detail to notice is **port 25**, not just the hostname. Before changing the password, ask why the application is trying to connect on that port.

### 4.3. Defaults Are No Substitute for Intentional Configuration

There are multiple Spring/Jakarta Mail versions and multiple transport providers. If `smtps` is used, the default port may differ. Therefore, **set the port explicitly in production profiles** and verify it with integration tests rather than relying on library defaults.

## 5. Jakarta Mail Protocol and TLS Mode Are Not the Same Thing

In Spring Boot you have:

```yaml
spring:
  mail:
    protocol: smtp
```

While in JavaMail properties you have:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.enable=false
```

These are two different configuration layers:

- **`spring.mail.protocol=smtp`:** selects the Jakarta Mail transport provider that uses SMTP.
- **`mail.smtp.starttls.enable=true`:** enables the TLS upgrade mechanism inside an SMTP session.
- **`mail.smtp.ssl.enable=true`:** requests SSL/TLS initiation from the very beginning for the `smtp` transport.

### 5.1. Can the `smtp` Protocol Be Used for Both 587 and 465?

**Yes**, in common configurations:

- Port 587: `protocol=smtp` + STARTTLS.
- Port 465: `protocol=smtp` + implicit TLS enabled via `mail.smtp.ssl.enable=true`.

What matters is **choosing the right TLS mode**; you do not necessarily have to switch `spring.mail.protocol` from `smtp` to `smtps` to use port 465.

### 5.2. What Is the `smtps` Protocol?

Some Jakarta Mail implementations provide the `smtps` transport as SMTP with SSL/TLS immediately upon connection. When choosing:

```yaml
spring:
  mail:
    protocol: smtps
```

you must ensure the provider/implementation supports the `smtps` transport and **the mail properties use the `mail.smtps.*` prefix**, instead of mistakenly keeping everything under `mail.smtp.*`.

For example, `mail.smtp.auth=true` will not necessarily control the `smtps` transport because the provider may read `mail.smtps.auth`. A prefix mismatch can prevent AUTH/timeouts/TLS checks from being applied as intended.

For many Spring Boot applications, it is simpler to **keep `protocol=smtp`** and enable implicit TLS with `mail.smtp.ssl.enable=true` on port 465.

### 5.3. IMAP/POP3 Are Not SMTP Transports

- `imap`/`imaps`: reads mailboxes via Jakarta Mail `Store`.
- `pop3`/`pop3s`: reads mailboxes via Jakarta Mail `Store`.
- `smtp`/`smtps`: sends mail via Jakarta Mail `Transport`.

Do not set `spring.mail.protocol=imaps` in `JavaMailSenderImpl` hoping to send email through a mailbox server. Outbound Spring Mail requires an appropriate transport for sending.

## 6. Standard Configuration: SMTP 587 with Required STARTTLS

Spring Boot example:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
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
```

Explanation:

| Property | Meaning |
|---|---|
| `spring.mail.host` | Host of the SMTP submission endpoint |
| `spring.mail.port=587` | Explicit TCP port |
| `spring.mail.protocol=smtp` | SMTP transport provider |
| `spring.mail.username/password` | Credentials issued by the SMTP provider |
| `mail.smtp.auth=true` | Enables SMTP AUTH when required by the provider |
| `mail.smtp.starttls.enable=true` | Allows requesting STARTTLS |
| `mail.smtp.starttls.required=true` | Refuses to proceed if STARTTLS upgrade is unavailable |
| `mail.smtp.ssl.checkserveridentity=true` | Verifies hostname against the TLS certificate |
| `mail.smtp.connectiontimeout` | TCP connect timeout in milliseconds |
| `mail.smtp.timeout` | Socket read timeout in milliseconds |
| `mail.smtp.writetimeout` | Socket write timeout in milliseconds |

### 6.1. Why Are Both `enable` and `required` Needed?

If you only set:

```properties
mail.smtp.starttls.enable=true
```

some default behaviors may allow proceeding without STARTTLS when the server does not advertise it or the upgrade is unavailable. For endpoints whose policy requires TLS, set:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

to **fail closed** instead of silently falling back to plaintext.

### 6.2. Hostname Verification Remains Mandatory

TLS encrypting the session alone is not enough to guarantee you connected to the right server. The certificate trust chain and the hostname in the certificate's SAN must be verified.

Therefore:

```properties
mail.smtp.ssl.checkserveridentity=true
```

is an essential safeguard when transmitting credentials and message content over the network.

### 6.3. Do Not Enable `ssl.enable` on a Port Expecting STARTTLS

This is an error:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    properties:
      mail:
        smtp:
          ssl:
            enable: true
```

If the server on port 587 is waiting for an SMTP greeting/EHLO/STARTTLS while the client immediately initiates TLS, the handshake will not follow the expected protocol. The outcome may be an `SSLException`, timeout, or connection reset.

**587 + STARTTLS** and **465 + implicit TLS** are two distinct initialization models.

## 7. Standard Configuration: SMTP 465 with Implicit TLS

If the provider publishes an immediate-TLS endpoint upon connection:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 465
    protocol: smtp
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
```

Connection flow:

```text
JavaMailSenderImpl                     SMTP :465
         |                                  |
         +------- TCP connect ------------>|
         |                                  |
         +======= TLS handshake ===========|
         |         certificate verify      |
         |                                  |
         +------- SMTP EHLO -------------->|
         +------- AUTH ------------------->|
         +------- MAIL FROM/RCPT TO ------>|
         +------- DATA ------------------->|
         |<------ final acceptance --------|
```

Here, STARTTLS is not used as the primary initiation method; TLS already exists before the application exchanges SMTP commands.

### 7.1. Common Mistake When Only Changing the Port to 465

It is not enough to just change:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 465
```

while leaving `mail.smtp.ssl.enable` at its default false.

The client may wait for a plaintext SMTP greeting while the server on 465 waits for a TLS ClientHello. Both may wait until the timeout expires.

### 7.2. Should Both STARTTLS and Implicit TLS Be Enabled?

Do not enable both as a trick to “guarantee TLS”. Pick the right mode for the endpoint:

- `smtp + 587 + starttls.enable/required`.
- `smtp + 465 + ssl.enable`.

Combining flags indiscriminately makes operations hard to explain and easily causes unintended reliance on a specific provider version's behavior.

### 7.3. Only a Complete Configuration Constitutes a Valid Profile

A profile should store together:
- host;
- port;
- transport protocol;
- TLS mode;
- username/credential mechanism;
- sender identity;
- socket timeouts;
- hostname verification policy.

Do not change only the port or only the host in isolation when rotating providers.

## 8. The Port 25 Case: Internal Relay or Mail Server

If an organization has an internal relay exposed on port 25, it may have a dedicated configuration:

```yaml
spring:
  mail:
    host: relay.internal.example
    port: 25
    protocol: smtp
    properties:
      mail:
        smtp:
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
```

This example **assumes the internal relay supports STARTTLS and requires TLS**. SMTP AUTH may or may not be required by the relay; that is a specific network/account policy and cannot be inferred from port 25.

### 8.1. Do Not Disable TLS Simply Because the Relay Is Inside a VPC

An internal network does not automatically guarantee server identity or protection against eavesdropping. Follow security requirements and the relay's actual capabilities. If the relay does not support STARTTLS, an appropriate architecture/infrastructure decision is needed instead of quietly dropping `required=true` as a “quick fix”.

### 8.2. Cloud Environments May Restrict Port 25

An SMTP relay working on a developer laptop does not prove the application will connect successfully from a cloud provider, container cluster, corporate network, or CI environment. Environments can have different egress policies.

Test from **where the app actually runs** and work with the network/provider team through approved channels; do not arbitrarily change ports or route email to unapproved endpoints.

## 9. Handshake Diagrams: Identifying a Wrong Mode

### 9.1. Correct STARTTLS on Port 587

```text
Client                               Server :587
  |---- TCP connection ---------------->|
  |<--- 220 SMTP service ready ---------|
  |---- EHLO app.example -------------->|
  |<--- 250-STARTTLS -------------------|
  |---- STARTTLS ---------------------->|
  |<--- 220 Ready to start TLS ---------|
  |==== TLS handshake ==================|
  |---- EHLO again (inside TLS) ------->|
  |---- AUTH (inside TLS) ------------->|
  |---- MAIL FROM / RCPT TO / DATA ---->|
  |<--- final SMTP response -----------|
```

This is a conceptual diagram; actual replies and EHLO capabilities depend on the server. The key point is that **TLS begins after STARTTLS**.

### 9.2. Correct Implicit TLS on Port 465

```text
Client                               Server :465
  |---- TCP connection ---------------->|
  |==== TLS handshake ==================|
  |<--- SMTP greeting (inside TLS) -----|
  |---- EHLO (inside TLS) ------------->|
  |---- AUTH (inside TLS) ------------->|
  |---- MAIL FROM / RCPT TO / DATA ---->|
```

### 9.3. Wrong: Plaintext SMTP to Port 465

```text
Client                               Server :465
  |---- TCP connection ---------------->|
  |---- waits for SMTP greeting         |
  |                                     | waits for TLS ClientHello
  |............. timeout ...............|
```

### 9.4. Wrong: Immediate TLS to Port 587

```text
Client                               Server :587
  |---- TCP connection ---------------->|
  |==== sends TLS ClientHello ========>| expects SMTP exchange
  |<--- invalid response/reset ---------|
```

The error messages in the two wrong scenarios can vary by JVM, provider, proxy, and disconnect timing. **Do not rely on a single exception line alone; cross-check port and TLS mode first.**

## 10. Difference Between `server.port` and `spring.mail.port`

A mistake that looks simple at first glance:

```yaml
server:
  port: 587

spring:
  mail:
    host: smtp.example.net
```

`server.port` is **the HTTP/HTTPS port that the Spring Boot web server listens on**. It does not configure the destination SMTP port.

If `server.port=587` is set, the web application may attempt to bind port 587 on the host machine, while the mail sender still lacks a proper SMTP port configuration.

The configuration should be:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
```

Keep `server.port` for the HTTP API (for example 8080) if the application runs a web server.

### 10.1. Do Not Confuse Client-Side Ports with External Container Ports

The following are all different:
- the app's HTTP service port;
- the provider's SMTP port on the Internet;
- an internal relay port;
- a port published by Docker Compose;
- the port of an SMTP sandbox used in tests.

A container running an application that wants to send mail to `smtp.example.net:587` needs **outbound network access** to that endpoint; not just mapping `-p 587:587` on the container.

### 10.2. Do Not Confuse Spring Mail with an HTTP Email API

If the provider gives an endpoint like `https://api.provider.example/v1/send`, that is an **HTTP API**. Do not put the API hostname into `spring.mail.host` and expect `JavaMailSender` to connect over SMTP port 587 or 465.

Use the SMTP endpoint published by the provider, or use a dedicated HTTP client/SDK if choosing the API.

## 11. Difference Between `spring.mail.port` and `mail.smtp.port`

In Spring Boot, the clear and standard approach is:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
```

You may see Jakarta Mail properties such as `mail.smtp.port`. However, when using `JavaMailSenderImpl`, the explicitly configured port field on the sender can be passed directly to transport connect.

Therefore, do not configure two conflicting value sources:

```yaml
spring:
  mail:
    port: 587
    properties:
      mail:
        smtp:
          port: 465
```

Operators will struggle to tell which port is actually used. It is best to:
1. Use `spring.mail.port` to configure the Spring Boot mail sender.
2. Use `spring.mail.properties.mail.smtp.*` for TLS, AUTH, and appropriate timeouts.
3. Avoid declaring a second port unless there is a specific requirement and you understand the implementation's precedence.

### 11.1. The `transport.protocol` Property Can Also Cause Confusion

`spring.mail.protocol` is the Boot property for `JavaMailSenderImpl`. A Jakarta Mail property such as `mail.transport.protocol` belongs to the Session/Transport context. Configuring both in parallel can make it unclear which provider the runtime selected.

Use one place to configure the protocol, and verify via the bean and tests.

## 12. YAML Indentation Mistakes and Wrong Prefixes

Nested YAML properties are bound by Spring Boot into Jakarta Mail keys. For example:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          starttls:
            enable: true
            required: true
```

corresponds to the keys:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

### 12.1. Wrong: Properties Outside `spring.mail`

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587

mail:
  smtp:
    starttls:
      enable: true
```

Depending on application configuration, this top-level `mail.smtp.*` block is **not automatically** placed into the sender's `spring.mail.properties`. Result: host/port are right, but STARTTLS is not applied.

### 12.2. Wrong: Misspelling `starttls`

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          startTLS:
            enabled: true
```

Jakarta Mail expects property keys like `mail.smtp.starttls.enable`, not an arbitrary alias `startTLS.enabled`. Property names are library-defined; do not guess them from YAML structure and ignore the standard names.

### 12.3. Wrong: Port Unintentionally Under `properties`

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          port: 587
```

When using Spring Boot auto-configuration, it is usually best to place the port under `spring.mail.port` to avoid relying on provider precedence. The key is to **set the exact property that the sender instance actually uses**.

### 12.4. Wrong: `smtp` Properties with the `smtps` Protocol

```yaml
spring:
  mail:
    protocol: smtps
    port: 465
    properties:
      mail:
        smtp:
          auth: true
          timeout: 10000
```

The `smtps` provider may read `mail.smtps.*`; settings under `mail.smtp.*` are not applied as intended.

If choosing `smtps` intentionally, you must configure the matching property namespace and test it. Unless there is a specific reason, use `protocol=smtp` + `mail.smtp.ssl.enable=true` on port 465 to reduce confusion.

## 13. Example of Explicitly Configured `JavaMailSenderImpl`

Not using Spring Boot auto-configuration? You can declare a sender bean:

```java
package com.example.mail;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class OutboundSmtpConfiguration {

    @Bean
    public JavaMailSender javaMailSender(
            SmtpEndpointProperties config) {

        JavaMailSenderImpl sender =
            new JavaMailSenderImpl();

        sender.setHost(config.host());
        sender.setPort(config.port());
        sender.setProtocol("smtp");
        sender.setUsername(config.username());
        sender.setPassword(config.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();

        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        if (config.tlsMode() == TlsMode.IMPLICIT_TLS) {
            props.put("mail.smtp.ssl.enable", "true");
        } else if (config.tlsMode() == TlsMode.STARTTLS) {
            props.put("mail.smtp.starttls.enable", "true");
            props.put("mail.smtp.starttls.required", "true");
        } else {
            throw new IllegalArgumentException(
                "SMTP TLS mode is not approved"
            );
        }

        return sender;
    }
}
```

`SmtpEndpointProperties` and `TlsMode` in the example are **application-defined models**, not built-in Spring Framework classes.

### 13.1. Example Model with Validation

```java
package com.example.mail;

public enum TlsMode {
    STARTTLS,
    IMPLICIT_TLS
}

public record SmtpEndpointProperties(
    String host,
    int port,
    String username,
    String password,
    TlsMode tlsMode
) {
    public SmtpEndpointProperties {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("SMTP host required");
        }

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid SMTP port");
        }

        if (tlsMode == null) {
            throw new IllegalArgumentException("SMTP TLS mode required");
        }
    }
}
```

For providers requiring OAuth2 or an unauthenticated internal relay, the factory contract must be extended. Do not hardcode the assumption that every SMTP endpoint uses username/password.

### 13.2. Why Validate the Port Early?

If the port is left blank, an application may fall back to default 25 without warning. A custom model can **require a port to be provided** at startup and fail immediately, before it is time to send critical emails.

Do not rely on the first `MailSendException` in production to discover a missing configuration.

### 13.3. Immutable Configuration After Startup

A shared `JavaMailSender` bean should be treated as immutable in host, port, protocol, TLS, and credentials while multiple threads are sending. Never call `sender.setPort(...)` in one request while another request has already started submitting.

If multiple SMTP profiles exist, use separate configured sender instances/registries instead of mutating a singleton's settings per email.

## 14. Spring Boot Auto-Configuration and Custom Beans

When `spring-boot-starter-mail` is present, Spring Boot typically auto-configures `JavaMailSender` based on mail settings and auto-configuration conditions.

However, if the application already declares its own `JavaMailSender` or `JavaMailSenderImpl` bean, auto-configuration may **not create the default sender**, depending on the Boot version's conditions.

Consequence: updating `spring.mail.port=587` in `application.yml` while a custom bean still uses port 25 or a hardcoded host.

### 14.1. Finding the Configuration Actually Used

Check across the project:
- Is there a custom `@Bean JavaMailSender`?
- Are there multiple `JavaMailSender` beans / `@Qualifier`s?
- Is there a `MailSenderFactory` creating senders per tenant?
- Is a bean created via `new JavaMailSenderImpl()` directly inside a business method?
- Does code call `sender.setHost/setPort` after config binding?
- Does a profile/test configuration override the default bean?

Do not read YAML alone and conclude all workers use that sender.

### 14.2. Reading the Configured Endpoint Without Exposing Secrets

For a `JavaMailSenderImpl` bean, you can inspect host/port/protocol without logging credentials:

```java
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class MailConfigDiagnostics {

    public static String summary(
            JavaMailSenderImpl sender) {
        return "SMTP endpoint: host=" + sender.getHost()
            + ", port=" + sender.getPort()
            + ", protocol=" + sender.getProtocol();
    }
}
```

This pattern is meant to aid diagnostics, **not to authorize exposing config over a public HTTP endpoint**. Do not call `getPassword()` or print the entire `Properties` object because it may contain sensitive data.

### 14.3. Port -1 Is a Signal Worth Investigating

If logs or a snapshot show sender port `-1`, it means no explicit port was set at the sender level. The transport provider may use the protocol default.

This is not necessarily an error in every environment, but it is a sign to check when the submission service requires port 587/465.

## 15. Correct DNS Is Not Enough to Prove SMTP Works

Suppose:

```powershell
Resolve-DnsName smtp.example.net
```

returns valid IPv4/IPv6 addresses.

This only proves DNS resolution from the environment being tested. It **does not confirm**:
- port 587/465 is open;
- the firewall allows outbound traffic;
- the TLS mode is right;
- the certificate matches the hostname;
- SMTP AUTH is valid;
- the From domain is authorized;
- the provider is accepting messages.

### 15.1. An MX Record Is Not a Submission Host

An email domain `example.com` may have an MX record:

```text
example.com MX 10 inbound-mail.provider.example
```

That is where mail servers deliver mail **to this domain**, not necessarily the endpoint an application should use to **submit outgoing mail**.

Do not take an MX host and assign it to `spring.mail.host` when the provider has published a dedicated submission hostname.

### 15.2. CNAME, Proxies, and TLS Hostname

A hostname may point through a CNAME or load balancer. When verifying certificates, you usually must verify **the hostname the client connects to**, such as `smtp.example.net`, rather than substituting a backend hostname just because DNS returns a CNAME.

If the certificate lacks an appropriate SAN, fix the certificate/endpoint or follow the provider's configuration; do not disable hostname verification.

## 16. Checking Ports with PowerShell

On Windows (PowerShell), you can test:

```powershell
Test-NetConnection smtp.example.net -Port 587
```

When successful:

```text
ComputerName     : smtp.example.net
RemotePort       : 587
TcpTestSucceeded : True
```

That proves a TCP connection to the tested IP/port at the time of the test. **It does not prove STARTTLS, AUTH, or SMTP submission will succeed.**

Compare both the intended port and the port the application is actually trying:

```powershell
Test-NetConnection smtp.example.net -Port 25
Test-NetConnection smtp.example.net -Port 587
Test-NetConnection smtp.example.net -Port 465
```

Do not scan addresses outside your administrative authority; only test endpoints the organization is authorized to connect to.

### 16.1. Use the Actual Production/Test Workload Environment

A command succeeding on a laptop does not prove a Kubernetes pod can connect. Differing factors include:
- source IP/egress NAT;
- VPC/subnet/firewall;
- corporate proxy;
- DNS resolver;
- IPv4/IPv6 routing;
- provider allowlist;
- container security policy.

If permitted, diagnose from the same environment where the app runs or from a diagnostic container with equivalent network policies.

### 16.2. Interpret PowerShell Results Carefully

| Result | Possible Meaning |
|---|---|
| `TcpTestSucceeded=True` | TCP can open to the endpoint |
| `False` | Port is unreachable from the test environment or rejected |
| Timeout | Network/filter/route/server did not respond |
| Connection refused | Active refusal at the address/port, usually no service listening or policy rejection |

There is not enough data to conclude “firewall X is blocking” from a single timeout alone.

## 17. Testing STARTTLS with OpenSSL

For SMTP submission port 587:

```bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -verify_return_error
```

Components:
- `-starttls smtp`: performs the necessary plaintext SMTP exchange and then upgrades to TLS.
- `-connect`: actual hostname/port.
- `-servername`: SNI server name when supported.
- `-verify_hostname`: verifies the certificate is valid for the hostname.
- `-verify_return_error`: does not silently continue on certificate verification errors.

A successful result here proves TLS negotiation and certificate verification in the test environment; it does not by itself prove SMTP AUTH will succeed or that email can be sent with the chosen From domain.

### 17.1. Test the Exact Hostname

Use the exact hostname and port that `JavaMailSender` uses. Do not test `smtp-a.example.net` in the terminal while the app reads an override pointing to `smtp-b.example.net`.

### 17.2. Reading TLS Errors

Some indicators:
- `certificate verify failed`;
- hostname mismatch;
- `wrong version number`;
- handshake failure;
- unexpected EOF or reset.

Errors depend on TLS mode, certificate, proxy, and server; do not attribute all of them to a single cause.

### 17.3. Truststore Differences

OpenSSL and the JVM may use different trust anchors. OpenSSL succeeding **does not guarantee the Java runtime with its own truststore will succeed as well**. If Java reports `PKIX path building failed`, inspect the CA chain and the specific JDK truststore in use.

## 18. Testing Implicit TLS on Port 465

For implicit TLS, **do not add `-starttls smtp`**:

```bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -verify_return_error
```

OpenSSL starts TLS immediately, matching how a port 465 server expects clients to behave.

### 18.1. Comparing the Two Commands

**Correct for 587/STARTTLS:**

```bash
openssl s_client -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net
```

**Correct for 465/implicit TLS:**

```bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net
```

If the two commands are swapped, the errors closely resemble misconfiguration errors in Spring Mail. This helps identify what the server expects, though you must still cross-check the provider documentation.

### 18.2. Do Not Put Credentials in Diagnostic Logs

Never type SMTP passwords or app passwords into shared transcripts or screenshots. To test actual AUTH, use a secured test application or a dedicated tool with proper redaction and secrets management.

### 18.3. A TLS Test Does Not Mean Email Was Sent

`openssl s_client` at this step only checks network/protocol/TLS. It does not prove an email was accepted, delivered, or passed SPF/DKIM/DMARC.

## 19. Reading SMTP Reply Codes in Proper Context

Commonly seen replies:

| SMTP Code | Common Context | What to Do |
|---|---|---|
| `220` | Greeting or ready for STARTTLS | Check which phase the session is in |
| `250` | EHLO capability, command success, final DATA acceptance | Distinguish `250` from EHLO vs `250` after DATA |
| `334` | Continue an authentication challenge step | Follow the actual AUTH mechanism |
| `421` | Service unavailable or temporary shutdown | Backoff/health check; avoid retry storms |
| `450`/`451` | Temporary failures | Check phase and policy before retrying |
| `530` | Authentication or TLS required | Check AUTH/STARTTLS |
| `535` | Authentication rejected | Check credentials/scope/provider policy |
| `550`/`553`/`554` | Permanent rejection or policy error | Check full context; do not blindly retry |

An SMTP reply code alone may not be enough to pinpoint a wrong port. For instance, `535` can occur due to a wrong password, expired token, locked account, or incompatible AUTH mechanism. The first step is confirming the app reached **the right SMTP endpoint and TLS mode**.

### 19.1. `250` After EHLO Is Not an Accepted Message

If the server returns:

```text
250-AUTH PLAIN LOGIN
250-STARTTLS
250 SIZE 20000000
```

that is a list of advertised capabilities; it does not mean the email was queued. A message only achieves submission-accepted status when the server returns an appropriate response at **the completion of the DATA phase** or an equivalent submission step.

### 19.2. SMTP Provider Acceptance Does Not Equal Delivery

`JavaMailSender.send(message)` returning without throwing an exception typically indicates submission completed per the transport API; it **does not** prove the recipient received it in their Inbox. The provider may still defer, bounce, or filter it as spam afterward.

## 20. Symptom → Possible Cause Matrix

| Symptom/Log | What to Check First | Common Misconfiguration |
|---|---|---|
| `Could not connect ... port: 25` | Actual sender port | Missing `spring.mail.port` |
| `Connection refused` on 587 | Endpoint/port, firewall | Provider only uses 465 or wrong host |
| Timeout on 465 | TLS mode and network | Missing `mail.smtp.ssl.enable` |
| `SSLException: wrong version number` | STARTTLS vs implicit TLS | Implicit TLS enabled on port 587 |
| `Unrecognized SSL message` | Server returned plaintext when client expected TLS | Mismatched TLS mode |
| `Must issue a STARTTLS command first` | `starttls.enable/required` | Attempting AUTH before TLS |
| `STARTTLS is required but host does not support` | Correct endpoint/capability | Connected to wrong port/server/proxy |
| `PKIX path building failed` | CA chain/truststore | Server certificate not trusted by JDK |
| `No subject alternative names matching` | Hostname and certificate SAN | Host alias does not match certificate |
| `AuthenticationFailedException` | AUTH/TLS/account policy | Wrong credentials or auth mechanism |
| `Could not convert socket to TLS` | Server STARTTLS and TLS context | TLS version/cert/proxy mismatch |
| `SendFailedException` | MAIL FROM/RCPT TO/DATA | Recipient/sender/relay policy |
| Local OK, production fails | Outbound firewall, DNS, IPv6, secrets | Environment differences |
| Fails only after rotation | New secret/config version, active sessions | Workers using mixed sender profiles |
| Port not logged | Custom sender config or missing logging | No runtime diagnostics |
| SMTP accepted but not in Inbox | Delivery/bounce/suppression | Not necessarily a port issue |

**Do not treat the table as a strict 1-to-1 mapping.** One exception type can have multiple causes, especially when a proxy, firewall, or load balancer sits between the app and the relay.

## 21. Layered Diagnostic Procedure

To avoid guessing, check in order:

```text
1. Confirm the provider's documented endpoint
       |
       v
2. Identify runtime host + port + protocol + TLS
       |
       v
3. Check DNS resolution
       |
       v
4. Check TCP connectivity from the workload
       |
       v
5. Check SMTP greeting/STARTTLS or implicit TLS
       |
       v
6. Check CA + hostname verification
       |
       v
7. Check SMTP AUTH
       |
       v
8. Check MAIL FROM / RCPT TO policy
       |
       v
9. Check DATA submission acceptance
       |
       v
10. Track delivery/bounce if needed
```

### 21.1. Step 1: Read Provider Documentation

Record:
- submission hostname;
- port 587/465 or another choice;
- STARTTLS or implicit TLS;
- SMTP AUTH mechanism;
- credential format;
- verified sender;
- IP allowlist;
- quotas and size limits.

Do not take an MX record as the submission hostname.

### 21.2. Step 2: Cross-Check Runtime

Inspect the actual bean/settings, not just YAML source files. Look for:
- environment overrides;
- Spring profiles;
- custom `JavaMailSender` beans;
- outdated Secret/ConfigMap versions;
- Helm/Kubernetes values;
- deployments running a different image;
- workers with separate profiles.

### 21.3. Step 3: Verify TCP

`Test-NetConnection` or an approved tool in the environment tells you whether the port is reachable. Do not conclude the password is wrong when TCP cannot even connect.

### 21.4. Step 4: Verify TLS

Use OpenSSL in the endpoint's exact mode, then verify the Java truststore and hostname. Do not “fix” it with `ssl.trust=*`.

### 21.5. Step 5: Verify AUTH and Sender

If TLS succeeds but AUTH fails:
- determine if the provider requires an app password or OAuth2;
- check if the token has the right scope;
- check if the account is disabled;
- verify login is allowed from the source IP/region;
- check whether the From domain is permitted.

### 21.6. Step 6: Verify Submission

Send a test email only to an approved mailbox/sandbox. Record the SMTP accepted status, provider ID if available, and check bounce/delivery via the appropriate channel.

## 22. Connection Timeout, Read Timeout, and Write Timeout

If you forget the port or use the wrong TLS mode, the application may **hang until timeout** instead of failing immediately. Set appropriate bounds:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

The unit for these SMTP socket timeouts is **milliseconds**.

| Property | Controls | Does Not Control |
|---|---|---|
| `connectiontimeout` | TCP connection establishment | Total duration of the entire email job |
| `timeout` | Socket read | Processing steps outside the network |
| `writetimeout` | Socket write | Total retry deadline |

### 22.1. Do Not Set Timeout to 0 to Mean “Do Not Wait”

In many socket APIs, a timeout of 0 means **unlimited** rather than “fail immediately”. Check the library's semantics; set an intentional positive number if you want a bounded wait.

### 22.2. Too-Short Timeouts Can Cause Duplicate Sends

If the server has already received the complete DATA but the client times out before reading the response, the state may be `UNKNOWN`. Retrying immediately can create a second email.

Therefore:
- do not configure timeouts too low for the network/provider;
- classify errors by phase when data is available;
- do not assume timeout = definitely unsent;
- maintain a retry budget and reconciliation.

### 22.3. Total Deadline Is Separate

Multiple SMTP commands are sent sequentially, each with its own network I/O. Socket timeouts do not necessarily cap the combined time of MIME rendering + connect + AUTH + send + persisting the outcome.

For critical jobs with SLAs, set a deadline at the orchestration/worker layer, not just in socket properties.

## 23. AUTH Failure Is Not Always a Password Error

Suppose port/TLS are correct, yet you receive:

```text
535 5.7.8 Authentication credentials invalid
```

Possible causes:
- wrong username/password;
- using a standard login password when the provider requires an app password;
- SMTP AUTH disabled on the mailbox;
- OAuth2 token has wrong audience/scope or is expired;
- provider restricts source IPs;
- account is locked;
- sending to the wrong region endpoint;
- client picked an unsupported AUTH mechanism;
- policy requires STARTTLS before AUTH.

### 23.1. Do Not Drop TLS to Test Login

This is an anti-pattern:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          starttls:
            enable: false
```

If the provider requires encryption, disabling STARTTLS can cause AUTH to be rejected or expose credentials if the server accepts plaintext. Fix the endpoint/credentials/CA properly.

### 23.2. Do Not Confuse `username` with `From`

`spring.mail.username` is the account used for SMTP AUTH; `helper.setFrom(...)` sets the email's From header. They can differ if the provider permits verified aliases, but you cannot assume every From domain is authorized to send.

Some providers reject relaying if the From or envelope sender does not match the account/domain. That cannot be fixed merely by changing the port.

### 23.3. SMTP AUTH Does Not Guarantee DMARC

Even when a server accepts a message, receiving systems still check SPF, DKIM, and DMARC. Deliverability failures should be addressed through domain authentication and provider events, not lumped under host/port errors.

## 24. SSL Handshake and Certificate Errors

If the hostname is right and the port is reachable but TLS does not work, examine two error groups:

**Group A — Wrong TLS Mode:**
- 587 with implicit TLS enabled.
- 465 without implicit TLS enabled.
- STARTTLS not advertised by the server.
- A proxy emits plaintext or strips STARTTLS.

**Group B — TLS Validation:**
- Expired certificate.
- Missing intermediate CA.
- JDK truststore does not trust the appropriate CA.
- Hostname has no matching SAN.
- Incompatible TLS protocol/cipher.
- SSL inspection swaps in a certificate the application does not trust.

### 24.1. Hostname Must Match the Certificate

If the client connects to `smtp.example.net` while the certificate is only issued for `mail-backend.internal`, hostname verification will fail even if both point to the same machine.

Do not resolve the IP from DNS and set `spring.mail.host` to the IP if the certificate lacks a matching IP SAN.

### 24.2. Do Not Enable Trust-All

Avoid:

```properties
mail.smtp.ssl.trust=*
```

This setting can bypass trust checks as supported by the implementation and is not a certificate fix. It weakens security and masks endpoint errors.

### 24.3. Do Not Disable Hostname Verification

If you enabled:

```properties
mail.smtp.ssl.checkserveridentity=true
```

and hit a mismatch, the solution is to use the right hostname/certificate or update the server/CA side, not flip it to false in production just to “get it working”.

## 25. Spring Boot Profiles and Environment Overrides

Another source of errors is values declared properly in files but overridden at runtime.

For example:

```yaml
# application.yml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
```

Yet deployment sets:

```text
SPRING_MAIL_PORT=25
```

and the environment value takes effect according to Spring Boot's configuration precedence. As a result, the sender may use port 25 even though the developer sees 587 in the repository.

### 25.1. Places to Cross-Check

- `application.yml`.
- `application-prod.yml` and active profiles.
- Environment variables.
- Command-line arguments.
- Config Server/externalized configuration.
- Kubernetes ConfigMap/Secret.
- Helm chart values.
- Custom `@ConfigurationProperties`.
- Custom bean factories or sender registries.

### 25.2. Do Not Dump the Entire Environment

The environment contains secrets. When inspecting:
- record only non-sensitive fields such as host, port, protocol, and TLS mode;
- never log passwords/tokens;
- never print the full `Environment` or all `spring.mail.properties` indiscriminately;
- restrict operational endpoints to authorized access.

### 25.3. Development Sandboxes May Use Different Ports

Mailpit/GreenMail/mock SMTP servers often run on test ports chosen by the environment. Do not assign test ports to production or let a default value like 1025 leak into live configurations.

Always separate configs per environment and ensure tests never send to unintended Internet mailboxes.

## 26. Network Issues: Firewall, DNS, Proxy, and IPv6

When the port is configured correctly but connection still fails, do not immediately change TLS config.

Other causes can be:

1. Provider has not allowlisted the source IP.
2. Firewall/security group blocks outbound 587/465.
3. Cloud egress policy restricts SMTP traffic.
4. NetworkPolicy blocks the pod.
5. DNS returns IPv6, but IPv6 routing is broken.
6. Proxy/NAT alters the path.
7. Provider is under maintenance or rate-limiting connections.
8. Private endpoint is reachable only from a specific network.
9. Split-horizon DNS returns different IPs per environment.
10. Load balancer has backends with the wrong TLS mode.

### 26.1. Check TCP Before Changing Certificates

If you get connection refused or unreachable, there is no TLS handshake to inspect yet. Fix the route/port/firewall based on evidence first.

### 26.2. Test from the Exact Source Environment

A laptop may succeed while production Kubernetes fails due to egress rules. This is not because Spring Boot interprets the same YAML two ways, but because the network path differs.

### 26.3. When IPv4 Works but IPv6 Does Not

Do not immediately toggle a random Java system property flag. Check:
- DNS A/AAAA records;
- IPv6 routing;
- network policies;
- provider IPv6 support;
- Java runtime options.

If preferring IPv4 is needed, that is a network/runtime change with system-wide impact; evaluate it first.

## 27. Using `JavaMailSenderImpl.testConnection` Appropriately

Spring provides:

```java
JavaMailSenderImpl sender = ...;

sender.testConnection();
```

This method can test connectivity to the mail server per the sender's configuration and throw an exception if it cannot connect.

It is useful for catching:
- wrong host/port;
- TCP errors;
- TLS errors on connect;
- some AUTH errors during the connect step.

However, it **does not prove a specific email will be accepted**, because it does not necessarily execute MAIL FROM/RCPT TO/DATA with a real sender/recipient. Nor does it prove the email is delivered.

### 27.1. Testing Connection at Startup

Spring Boot has the setting:

```yaml
spring:
  mail:
    test-connection: true
```

When supported by the version and auto-configuration conditions, this option helps verify connectivity when the application starts up.

Considerations:
- During an SMTP outage, startup may fail.
- For an app whose API must stay up even when SMTP is unavailable, failing startup may be inappropriate.
- For a dedicated mail worker whose sole job is sending, failing fast can be helpful.
- When using multiple custom senders, each profile must be checked via dedicated health logic.
- Do not send real emails just to test a connection.

### 27.2. Do Not Blindly Couple Health to Readiness

If readiness depends on SMTP availability, the entire HTTP service may be pulled from the load balancer during a mail provider incident, even though other APIs remain healthy. Design health indicators around critical dependencies and operational goals; do not assume the mail provider is a mandatory dependency for every request.

## 28. Smoke Testing with `SimpleMailMessage`

Once host/port/protocol/TLS are verified, use a test email with an approved recipient:

```java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailSmokeTestService {

    private final JavaMailSender sender;

    public MailSmokeTestService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendToApprovedMailbox(String approvedRecipient) {
        SimpleMailMessage message =
            new SimpleMailMessage();

        message.setFrom("no-reply@example.com");
        message.setTo(approvedRecipient);
        message.setSubject("SMTP connection smoke test");
        message.setText("This is a controlled test message.");

        sender.send(message);
    }
}
```

A real application must verify that `approvedRecipient` belongs to an allowed test mailbox list; do not expose this method as an HTTP endpoint where arbitrary recipients can be entered.

### 28.1. Distinguishing Smoke Test Outcomes

- `testConnection()` succeeds: sender connectivity/auth was checked.
- `sender.send(message)` succeeds: transport reported submission succeeded.
- Provider dashboard reports delivered: provides additional delivery-layer data.
- Recipient opens the message: a separate event, not inferred from the SMTP API result.

### 28.2. Do Not Send a Smoke Test Before Verifying the Route

If a provider or sandbox/production config is mixed up, a smoke test could send out to the Internet unintentionally. Verify host, port, profile, and recipient allowlist before sending.

## 29. Testing: Validating the Configuration Profile

You can model the endpoint and TLS mode as a configuration requiring validation.

```java
package com.example.mail;

public enum SmtpTlsMode {
    STARTTLS_REQUIRED,
    IMPLICIT_TLS
}

public record MailServerProfile(
    String host,
    int port,
    SmtpTlsMode tlsMode
) {
    public MailServerProfile {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("Host required");
        }
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("Invalid port");
        }
        if (tlsMode == null) {
            throw new IllegalArgumentException("TLS mode required");
        }
    }
}
```

If the system only supports 587/465, you can add an allowlist and pairing rules. However, **do not hardcode that 587 is always STARTTLS and 465 is always implicit TLS across every provider in every environment** if a contract specifies a different endpoint. Validate against **provider profile policy**, not just numbers.

### 29.1. Unit Tests Catching Missing Ports

```java
import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.Test;

class MailServerProfileTest {

    @Test
    void rejectsMissingPort() {
        assertThatThrownBy(() ->
            new MailServerProfile(
                "smtp.example.net",
                0,
                SmtpTlsMode.STARTTLS_REQUIRED
            )
        ).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void acceptsExplicitSubmissionPort() {
        MailServerProfile profile =
            new MailServerProfile(
                "smtp.example.net",
                587,
                SmtpTlsMode.STARTTLS_REQUIRED
            );

        assertThat(profile.port()).isEqualTo(587);
    }
}
```

This unit test makes no network connection; it solely guards the configuration model against “forgetting the port”.

### 29.2. Testing That the Factory Attaches Correct JavaMail Properties

If you have a `JavaMailSenderImpl` factory, assert:
- `getHost()` is right;
- `getPort()` is right;
- `getProtocol()` is right;
- `mail.smtp.starttls.enable/required` are right on 587;
- `mail.smtp.ssl.enable` is right on 465;
- `mail.smtp.ssl.checkserveridentity` is enabled;
- timeouts are positive;
- there are no conflicting properties.

No SMTP server is needed to test this configuration mapping.

## 30. Integration Tests: Verifying Real Connectivity

Unit tests are not enough to prove an SMTP handshake.

An integration test plan can use:
- GreenMail or an SMTP sandbox supporting the desired protocol;
- an SMTP test server with proper TLS;
- a fault-injecting SMTP proxy/server for specific errors;
- `JavaMailSenderImpl` configured to point at the test host/port;
- assertions verifying the count of accepted messages.

### 30.1. Happy-Path STARTTLS

1. Start an SMTP test server with STARTTLS on an allowed dynamic or fixed port.
2. Generate or inject a trusted test CA certificate with a SAN matching the test hostname.
3. Configure `protocol=smtp`, test port, `starttls.enable/required=true`.
4. Call `testConnection()` or send a controlled test message.
5. Verify the test server received the message.
6. Close resources cleanly.

### 30.2. Happy-Path Implicit TLS

1. Start an SMTP TLS-from-connect test server.
2. Configure `mail.smtp.ssl.enable=true` on the test port.
3. Verify the handshake/TLS certificate.
4. Send a test email and inspect the MIME message.
5. Do not use `starttls smtp` when testing implicit TLS.

### 30.3. Negative Test: Wrong TLS Mode

Examples:
- Client sends TLS-from-connect to a server supporting only STARTTLS.
- Client sends plaintext SMTP to a server expecting implicit TLS.
- Client omits an explicit port, and fallback configuration is rejected by policy.

Assertions should verify the exception/connection failure belongs to the appropriate **category** and that no message was accepted. Do not assert a single exact error string because JDK/provider versions may vary.

### 30.4. Negative Test: Invalid Hostname or CA

Include tests for certificate mismatch and untrusted CA. Do not prove “TLS works” by disabling hostname validation or enabling trust-all.

### 30.5. Tests Must Not Depend on Production Internet

For stable CI:
- use an isolated SMTP sandbox;
- never use real credentials;
- never send to recipients outside an allowlist;
- choose non-conflicting ports;
- stop servers and clean up;
- enforce bounded waits/timeouts;
- prevent tests from sending to real providers when CI variables are missing.

## 31. Environment Testing with Testcontainers

In projects using Testcontainers, you can run an SMTP sandbox/container to test mail submission. Most importantly, **the port the application connects to must be the actual mapped host port**, not the fixed port inside the container if the test runs from the host process.

Example diagram:

```text
JUnit process                  Docker container
     |
     | localhost:mappedPort
     +--------------------------> SMTP sandbox :1025
                                  (container port)
```

If the sandbox listens on 1025 inside the container, Testcontainers may map it to a different host port. The app must use the mapped port value provided by the test container.

### 31.1. Do Not Use 587 by Default for Every Integration Test

In a test environment, the endpoint may use 1025, 3025, or a random port. Testing with a port different from production is fine when testing the general flow; however, have dedicated tests for **TLS mode and profile mapping** if that is the bug you want to prevent.

### 31.2. Property Overrides in `@SpringBootTest`

A test can override:

```text
spring.mail.host=127.0.0.1
spring.mail.port=<mapped-smtp-test-port>
spring.mail.protocol=smtp
```

Use dynamic properties/test configuration accordingly; do not hardcode a port if the runtime maps one randomly.

### 31.3. Do Not Confuse `testConnection` with an Acceptance Test

An SMTP sandbox may let `testConnection` pass while still rejecting a recipient or MAIL FROM during an actual send. Test both if the use case requires verifying submission.

## 32. Reading Logs Without Exposing Credentials

Jakarta Mail has debug options, yet enabling full debug logging in production can expose protocol metadata, email addresses, or sensitive payloads.

Information usually sufficient to diagnose host/port/protocol issues:
- environment/service name;
- SMTP provider profile key;
- display-safe hostname;
- port;
- transport protocol;
- TLS mode;
- exception class;
- short safe error category;
- attempt ID/message key;
- duration;
- retry decision.

Example:

```json
{
  "event": "mail.smtp_connect_failed",
  "messageKey": "msg-2187",
  "attemptId": "attempt-3",
  "profile": "transactional",
  "host": "smtp.example.net",
  "port": 25,
  "protocol": "smtp",
  "tlsMode": "STARTTLS_REQUIRED",
  "errorCategory": "CONNECT_TIMEOUT",
  "durationMs": 5000
}
```

This log snippet clearly shows the application is trying **port 25** even though the profile expects 587. That is far more useful than dumping an entire raw SMTP transcript.

### 32.1. Avoid Logging the Following

- SMTP passwords or app passwords.
- OAuth2 access/refresh tokens.
- AUTH challenges/responses containing secrets.
- Full MIME bodies.
- Attachment data/Base64.
- Reset/verification token links.
- Unnecessary recipient addresses.

### 32.2. Enable Debug in a Controlled Manner

When an issue is hard to reproduce, debug logging can be enabled in a test environment or during a brief diagnostic window with redaction and restricted log access. Never leave protocol-level debug logging on long-term in production by default.

### 32.3. Metrics Are Different from Logs

Use metrics such as:
- `mail_smtp_connect_failures_total{profile,category}`;
- `mail_smtp_send_duration_seconds{profile}`;
- `mail_smtp_auth_failures_total{profile}`;
- `mail_smtp_tls_failures_total{profile}`;
- `mail_outbox_retry_wait_count`;
- `mail_outbox_unknown_count`.

Do not use message ID or recipient as high-cardinality Prometheus labels.

## 33. Retries and Outbox: Do Not Turn Config Errors into a Send Storm

If the port is wrong, every retry keeps connecting to the wrong endpoint, wasting resources and building up a backlog.

Example:

```text
Mail job due
    |
    v
JavaMailSender tries smtp.example.net:25
    |
    v
Connect timeout
    |
    v
Retry immediately
    |
    +--> timeout again
    +--> timeout again
    +--> timeout again
```

Proper orchestration:
- When a profile misconfiguration is detected, open a circuit breaker/pause the route if policy requires.
- Emit an alert for wrong host/port/protocol/TLS mode.
- Do not retry continuously with the exact same configuration.
- Use exponential backoff with jitter for transient errors.
- For definite configuration errors, require fixing the profile or manual intervention.
- Keep outbox jobs durable and maintain a retry budget.
- Once config is fixed, resume/dispatch in a controlled manner to avoid flooding the backlog all at once.

### 33.1. Wrong Port Before Connecting Usually Produces No SMTP Submission

If TCP connect never succeeded, it is clearer that DATA was not sent compared to a timeout after DATA. However, **the classifier must rely on real phase evidence**; do not assume every `MailSendException` is pre-submission.

### 33.2. `UNKNOWN` Must Not Be Blindly Retried

If an error occurs after the client may have finished sending SMTP DATA without receiving the final reply, the provider may have already accepted it. Blind retries risk duplicate sends. Record `UNKNOWN` and reconcile via provider logs/API/webhooks if available.

### 33.3. Do Not Change `sendAt` When Fixing the Port

A scheduled email was due at 09:00, but the port was wrong until 09:30. After fixing the configuration:
- preserve `send_at=09:00` for auditing;
- record the actual submission time when sent;
- check `expires_at`, consent, and quota before resending;
- do not overwrite every `send_at` with the current time to hide the delay.

## 34. Multiple SMTP Profiles and Failover

An application may use:
- a transactional provider on port 587;
- a marketing provider on port 465;
- an internal relay on port 25.

If there is only a single global `spring.mail.host/port` set and it is mutated dynamically per tenant, the system can send via the wrong route.

Proper design:
- dedicated sender beans or immutable profiles per provider;
- routing by validated category/tenant;
- validating host/port/TLS/auth per profile;
- never mutating a shared singleton across threads;
- per-provider metrics;
- separate quotas/rate limits.

### 34.1. Failover Must Be Safe

If provider A fails to connect before SMTP submission, failing over to provider B may be considered when policy permits. However, B must be prepared with:
- a verified From domain;
- SPF/DKIM/DMARC alignment;
- suppression/consent checks;
- credentials/TLS;
- quota;
- data residency/tenant permissions.

Do not fail over to B just because A timed out with an **unknown outcome**. A may have already accepted the email, and B would send a duplicate.

### 34.2. Configure Both Host and Port per Route

Avoid:

```java
sender.setHost(provider.host());
sender.send(message);
```

while forgetting to update port/TLS. When switching providers, switch the **entire endpoint profile**, not just a single property.

## 35. Common Errors When Receiving Mail: IMAP and POP3 Ports/Protocols

Although this lesson focuses on outbound SMTP, a Spring Mail system may also read email via Jakarta Mail `Store`.

Common ports:

| Receive Protocol | Common Port | TLS |
|---|---|---|
| IMAP | 143 | STARTTLS if supported by server |
| IMAPS | 993 | Implicit TLS |
| POP3 | 110 | STLS/STARTTLS if supported by server |
| POP3S | 995 | Implicit TLS |

### 35.1. Do Not Use the SMTP Host to Read INBOX

A provider may publish:
- `smtp.example.net` for sending;
- `imap.example.net` for reading.

Do not default `Store.getFolder("INBOX")` to `spring.mail.host`. Spring Boot `spring.mail.*` auto-configuration is primarily intended for the outbound sender.

### 35.2. `Session`, `Store`, and `Transport` Are Different

`jakarta.mail.Session` is the configuration context. `Transport` is used to send over SMTP, while `Store` is used to read mailboxes over IMAP/POP3.

If using `Session.getStore("imaps")`, you must use `mail.imaps.*` properties; meanwhile `JavaMailSenderImpl` uses the `smtp` or `smtps` protocol/transport and its corresponding properties.

### 35.3. The Same Problem: Right Hostname but Wrong Port

If an IMAP server expects immediate TLS on 993 while the client uses plaintext `imap`, it can likewise time out or fail the handshake. The general rule remains choosing the right **protocol + port + TLS mode**.

## 36. Incident Runbook: When Sending Mail Suddenly Fails

### Step 1 — Confirm Scope of Impact

- All emails or only a single tenant/provider?
- All environments or only production?
- Did errors start after a deployment or config rotation?
- Are SMTP requests timing out, failing AUTH, or being rejected?
- How large is the backlog/retry queue growing?

### Step 2 — Protect the System Temporarily

- Limit concurrency/rate.
- If a definite misconfiguration is found, pause the route.
- Keep jobs in a durable outbox; do not drop them.
- Do not automatically move `UNKNOWN` back to pending.
- Do not use trust-all/plaintext fallbacks to “recover quickly”.

### Step 3 — Confirm Runtime Profile

Record non-secret values:
- host;
- port;
- protocol;
- TLS mode;
- authentication mechanism;
- profile/environment;
- active application version.

Compare against provider documentation, not just YAML in git.

### Step 4 — Verify DNS/TCP

From the actual deployment environment:
- resolve the hostname;
- test the published port;
- check firewall/network rules;
- verify source IP allowlists if the provider uses them.

### Step 5 — Verify TLS

Use OpenSSL in the right mode, verify hostname and certificate chain, then inspect the JDK truststore if the JVM still fails.

### Step 6 — Verify AUTH and Sender Policy

Once connectivity/TLS are valid:
- confirm credentials/scopes;
- check provider logs;
- verify From/envelope sender;
- do not print secrets.

### Step 7 — Controlled Smoke Test

Send one email to an approved test mailbox and observe the submission result.

### Step 8 — Resume Backlog with Limits

- Handle expired jobs first.
- Reconcile `UNKNOWN`.
- Prevent retry storms.
- Enforce quotas/concurrency.
- Monitor acceptance, bounces, and delivery if available.

### Step 9 — Document Root Cause

Example:
> In the new deployment, `SPRING_MAIL_PORT` was not provided, so the sender fell back to `smtp`'s default port. Infrastructure blocks outbound port 25. Restored port 587/STARTTLS configuration and added startup validation + integration tests.

A runbook should help fix the **root cause**, not just tweak timeouts or retry counts.

## 37. Pre-Deployment Configuration Checklist

### 37.1. Endpoint

- [ ] SMTP submission host matches provider documentation.
- [ ] `spring.mail.port` is declared explicitly.
- [ ] `spring.mail.protocol` matches the transport.
- [ ] MX/IMAP/API endpoints are not confused with SMTP submission.
- [ ] `server.port` is not confused with `spring.mail.port`.
- [ ] No conflicting `mail.smtp.port` exists.
- [ ] Env/profile/ConfigMap overrides have been verified.

### 37.2. TLS and AUTH

- [ ] Port 587 uses STARTTLS if documented by the provider.
- [ ] Port 465 uses implicit TLS if documented by the provider.
- [ ] `starttls.required=true` when the endpoint requires STARTTLS.
- [ ] Hostname verification and CA chain are valid.
- [ ] `ssl.trust=*` is not used in production.
- [ ] SMTP AUTH mechanism/credentials are correct.
- [ ] Credentials are pulled from a protected secret manager/env.
- [ ] From domain/identity is verified.

### 37.3. Runtime

- [ ] Connect/read/write timeouts are reasonable.
- [ ] Workload has outbound access to the port.
- [ ] Provider quotas/rate limits are known.
- [ ] Startup/`testConnection` policy has been considered.
- [ ] Non-secret metrics/logs exist for host, port, protocol, and TLS.
- [ ] Appropriate retry/backoff/circuit breaker or route pause is in place.
- [ ] Outbox does not lose jobs during provider outages.
- [ ] `UNKNOWN` attempts are never blindly resent.

### 37.4. Tests

- [ ] Unit test for endpoint profile validation.
- [ ] Unit test mapping config onto `JavaMailSenderImpl`.
- [ ] Test 587/STARTTLS against an appropriate server.
- [ ] Test 465/implicit TLS against an appropriate server.
- [ ] Test wrong-port/wrong-mode failures.
- [ ] Test that certificate mismatch is rejected.
- [ ] Test AUTH failure and sender policy.
- [ ] Test production-like network path if the environment allows.
- [ ] Test that no real email is sent unintentionally.

## 38. Practice Exercises

### Exercise 1 — Missing Port

Given the configuration:

```yaml
spring:
  mail:
    host: smtp.example.net
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
```

The provider requires 587/STARTTLS. Add the missing properties and explain why omitting the port can cause the client to use port 25.

### Exercise 2 — Confusing `server.port`

An application sets `server.port=587`, yet email still connects to port 25. Fix it and explain the difference between the HTTP listen port and the SMTP destination port.

### Exercise 3 — STARTTLS vs Implicit TLS

Draw the handshakes for 587 and 465. Indicate where the `STARTTLS` command appears and why 465 does not need an upgrade from a plaintext SMTP session.

### Exercise 4 — Analyzing the “wrong version number” Error

A client enables `mail.smtp.ssl.enable=true` on port 587. Analyze the protocol mismatch hypothesis and write the correct configuration.

### Exercise 5 — Port 465 Timeout

A client only changes `spring.mail.port` from 587 to 465 while keeping the STARTTLS config. Explain why it waits for a greeting and provide the correct implicit TLS configuration.

### Exercise 6 — `smtps` Property Prefix

An application uses `spring.mail.protocol=smtps` but sets timeout under `mail.smtp.timeout`. Identify the risk of the prefix not being applied and propose a consistent configuration.

### Exercise 7 — YAML Indentation

Given an `application.yml` that places `mail.smtp.starttls.enable` outside `spring.mail.properties`, fix the nesting so the sender receives the property properly.

### Exercise 8 — Runtime Override

The repository uses port 587, but production logs show port 25. List the override sources to inspect and how to log the non-secret runtime profile.

### Exercise 9 — DNS vs TCP

`Resolve-DnsName` succeeds, yet `Test-NetConnection -Port 587` fails. State what has been proven and what causes still need investigation.

### Exercise 10 — OpenSSL STARTTLS

Write the `openssl s_client -starttls smtp` command for 587 with SNI and hostname verification. Explain why that command differs from implicit TLS on 465.

### Exercise 11 — Certificate Mismatch

The SMTP certificate only matches `smtp-a.example.net`, whereas the application uses `mail.example.net`. Design a safe fix without disabling hostname verification.

### Exercise 12 — `TestConnection`

Call `JavaMailSenderImpl.testConnection()`. Distinguish what that test can prove from what it cannot prove about recipients and delivery.

### Exercise 13 — Unit Testing Profile Factory

Write a unit test verifying that the factory configures `smtp`, port 587, STARTTLS required, or port 465, implicit TLS. The test must also reject port 0.

### Exercise 14 — SMTP Sandbox Integration

Create two test endpoints: one STARTTLS, one implicit TLS. Send test mail and verify the server receives mail in the right mode.

### Exercise 15 — Cloud Network Blocks Port 25

Local sends work over port 25, while cloud times out. Design a procedure to verify egress, select the provider-published submission endpoint, and avoid switching to a random port.

### Exercise 16 — AUTH After TLS

Port and TLS are right, yet the server returns 535. List possibilities related to credentials, OAuth2/app password, account policy, and the difference between SMTP AUTH and From verification.

### Exercise 17 — Timeout in a Queue Worker

A mail worker has a 60-second connect timeout and 100 jobs become due simultaneously. Analyze the thread-exhaustion risk and propose bounded concurrency/backoff.

### Exercise 18 — Avoiding Duplicates After `UNKNOWN`

Simulate SMTP DATA finishing while the client loses the final reply. Design the `UNKNOWN` outbox state and reconciliation instead of immediate retries.

### Exercise 19 — Provider Rotation

An application switches from provider A (587/STARTTLS) to B (465/implicit TLS). Write a checklist of the profile parts that must change together, including verified From and quotas.

### Exercise 20 — Comprehensive Incident Diagnosis

Log:

```json
{
  "event": "mail.smtp_connect_failed",
  "host": "smtp.example.net",
  "port": 25,
  "protocol": "smtp",
  "durationMs": 5000,
  "errorCategory": "CONNECT_TIMEOUT"
}
```

The provider publishes port 587/STARTTLS. Create a plan to fix it, test on a sandbox, roll out, and avoid a retry storm for the existing backlog.

## 39. Summary

**Configuring the right host while forgetting the port or protocol** is a common Spring Framework Mail error because the hostname only resolves **the server address**, whereas SMTP submission requires **the right port, transport provider, and TLS mode**.

Remember these principles:

1. **Declare the port explicitly** in `spring.mail.port`; do not expect Jakarta Mail to infer 587 from username/password.
2. **Port 587** commonly uses `smtp + STARTTLS`; enable both `starttls.enable` and `starttls.required` when the provider requires encryption.
3. **Port 465** commonly uses implicit TLS; with `protocol=smtp`, enable `mail.smtp.ssl.enable=true` before connecting.
4. **Port 25** typically serves relay/server-to-server traffic; do not use it by default for SMTP submission, and it may be blocked by networks/clouds.
5. **`spring.mail.protocol` differs from TLS mode**. `smtp` works with both 587/STARTTLS and 465/implicit TLS; if using `smtps`, check the `mail.smtps.*` property prefix.
6. **`server.port` is not `spring.mail.port`**. Do not configure the HTTP port instead of the SMTP port.
7. **YAML nesting and runtime overrides** matter; inspect the actual sender bean, not just source files.
8. Diagnose layer by layer: **DNS → TCP → SMTP greeting/TLS → certificate → AUTH → MAIL FROM/RCPT TO/DATA → delivery**.
9. **Never fix errors by disabling TLS/hostname verification** or enabling trust-all; fix the endpoint, certificate, or credentials per policy.
10. **Bound timeouts and retries**, keep a durable outbox, and never blindly resend attempts with an `UNKNOWN` outcome.
11. **Test both configuration mapping and real SMTP handshakes** using unit tests, sandboxes, and environment-appropriate network checks.
12. **SMTP submission accepted does not equal delivered**: delivery depends on the provider and receiving systems.

When configuring **host + port + protocol + TLS mode** as a unified profile, you catch errors early, diagnose faster, and operate Spring Framework Mail reliably without trading off security or creating duplicate-email risks.
