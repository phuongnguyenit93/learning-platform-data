# Authentication with Username, Password, and Token in Spring Framework Mail

When a Spring application sends email through an SMTP relay, the server may require the application to prove permission to access the sending account. Authentication credentials can be a **username/password**, **app password**, **provider-issued SMTP credential**, or **OAuth 2.0 access token**. Choosing the right credential type, SMTP AUTH mechanism, and TLS configuration determines whether mail sending is secure and reliable.

Spring Framework Mail provides `JavaMailSender` to work with SMTP via Jakarta Mail/Angus Mail. Spring Boot can auto-configure a sender from `spring.mail.*`, but it does not automatically fetch OAuth tokens, determine provider-specific permissions, or refresh tokens for every service. Those responsibilities belong to the application's infrastructure and security design.

This lesson explains SMTP AUTH mechanisms, configuring username/password, app passwords, and OAuth2/XOAUTH2, protecting secrets, handling token expiry, diagnosing authentication failures, and testing safely.

## 1. What is SMTP AUTH?

SMTP is the protocol for sending and relaying email. The application opens a connection to an SMTP submission server, may upgrade the connection with TLS, authenticates to the server, and then transmits the envelope and email content.

An SMTP server may allow certain relaying without AUTH inside an internal network with strict policies. However, for authenticated application submission, SMTP AUTH is commonly used to prevent unauthorized parties from sending through an account or relay.

~~~text
Spring application
      |
      v
SMTP connection
      |
      +--> TLS
      |
      +--> SMTP AUTH
      |       |
      |       +--> Username + password
      |       +--> Username + app password
      |       +--> Username + OAuth access token
      |
      +--> MAIL FROM / RCPT TO / DATA
      |
      v
SMTP server accepts or rejects the message
~~~

Authentication answers the question: **is the client authorized to use the SMTP service under the declared identity?**

It does not by itself prove:

- That any From address is permitted to send.
- That the domain has valid SPF/DKIM/DMARC.
- That the message was accepted after DATA.
- That the message reached the recipient's Inbox.
- That the content is encrypted end-to-end.

Distinguish between **authentication**, **transport encryption**, **sender authorization**, **submission**, and **delivery**.

## 2. Components to distinguish

| Component | Role | Illustrative example |
| --- | --- | --- |
| SMTP host | Server the application connects to | `smtp.example.com` |
| SMTP port | Port and connection mode | `587` / `465` |
| Username | Identity used with SMTP AUTH | `notifier@example.com` |
| Password | Secret for password-based AUTH | Stored in vault |
| App password | Application-specific secret if supported by provider | Stored in vault |
| SMTP API key | Some providers issue a secret used like a password | Per provider documentation |
| OAuth access token | Token with scope/audience and expiration | Passed via XOAUTH2 if supported |
| OAuth refresh token | Used to request a new access token from the token endpoint | Never sent in SMTP AUTH |
| AUTH mechanism | How the client proves its credential | PLAIN, LOGIN, XOAUTH2 |
| Envelope sender | `MAIL FROM` address in SMTP | `bounce@example.com` |
| MIME From | Address displayed in the email | `Notifier <notifier@example.com>` |

The username does not have to be an email address. Some providers use a service account or a separately generated username. Similarly, the term “API key” does not automatically mean an OAuth access token.

Do not pass `password` or `refresh token` into a use case DTO merely because an email needs to be sent. Credentials should be selected and retrieved at the infrastructure layer.

## 3. Where does SMTP AUTH fit in the flow?

An SMTP session using STARTTLS and AUTH might look like this:

~~~text
Client                                    SMTP server
  |                                            |
  |<------ 220 Service ready ------------------|
  |------- EHLO app.example.com -------------->|
  |<------ 250-STARTTLS -----------------------|
  |------- STARTTLS -------------------------->|
  |<------ 220 Ready for TLS ------------------|
  |======= TLS handshake ======================|
  |------- EHLO app.example.com -------------->|
  |<------ 250-AUTH PLAIN LOGIN XOAUTH2 -------|
  |------- AUTH [selected mechanism] --------->|
  |<------ 235 Authentication successful ------|
  |------- MAIL FROM:<sender@example.com> ---->|
  |<------ 250 OK -----------------------------|
  |------- RCPT TO:<user@example.net> -------->|
  |<------ 250 OK -----------------------------|
  |------- DATA ------------------------------>|
  |<------ 354 Continue -----------------------|
  |------- MIME message + DATA terminator ---->|
  |<------ 250 Accepted -----------------------|
~~~

This is an abbreviated transcript. Not every server supports all mechanisms shown in the example.

`EHLO` reveals which extensions and AUTH mechanisms the server advertises. After STARTTLS completes, the client must re-check capabilities over the TLS channel. Providers may require TLS before advertising or accepting AUTH.

`235` confirms authentication; it **does not** prove the mail was accepted. A successful SMTP response after the DATA step is the evidence of submission at the current hop.

### Do not write AUTH data into logs

Safe log examples should redact credentials:

~~~text
C: AUTH PLAIN <redacted>
S: 235 Authentication successful
~~~

Do not copy Base64 AUTH values into tickets: Base64 is only encoding, not encryption.

## 4. AUTH PLAIN, AUTH LOGIN, and passwords

`AUTH PLAIN` and `AUTH LOGIN` are two username/password authentication methods commonly supported by SMTP servers. They differ in format/challenge-response, yet both rely on a password-equivalent secret.

During the exchange, data may be Base64-encoded. Base64 does not keep secrets confidential; anyone receiving the string can decode it back. Therefore:

1. Transmit passwords only over a trusted TLS connection.
2. Verify the server certificate and hostname.
3. Never fall back to plaintext if policy requires encryption.
4. Do not enable raw AUTH transcript debugging in production.
5. Do not store passwords in code, queue payloads, or telemetry.

Comparison table:

| Technology | Problem addressed |
| --- | --- |
| SMTP AUTH | Whether the client is permitted to use the SMTP relay |
| STARTTLS | Upgrades an SMTP connection to TLS |
| Implicit TLS | TLS from the moment the connection opens |
| Base64 | ASCII representation of data; not secure |
| OAuth2 | Issues tokens and authorization to use a service |
| SPF/DKIM/DMARC | Part of the domain authentication and anti-spoofing ecosystem |

Do not confuse AUTH with transport encryption.

## 5. Configuring username/password via Spring Boot

An application with the `spring-boot-starter-mail` dependency can configure `JavaMailSender` with YAML:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
~~~

Explanation:

| Property | Effect |
| --- | --- |
| `spring.mail.host` | SMTP server address |
| `spring.mail.port` | SMTP port |
| `spring.mail.username` | AUTH identity |
| `spring.mail.password` | AUTH secret |
| `mail.smtp.auth` | Enables SMTP authentication |
| `mail.smtp.starttls.enable` | Uses STARTTLS when supported |
| `mail.smtp.starttls.required` | Requires STARTTLS to succeed |
| `mail.smtp.ssl.checkserveridentity` | Verifies the server certificate's hostname |
| `mail.smtp.connectiontimeout` | Connection open timeout |
| `mail.smtp.timeout` | Read timeout |
| `mail.smtp.writetimeout` | Write timeout |

The syntax `"[mail.smtp.auth]"` preserves dots in the key when binding maps from YAML. In `application.properties`, dotted property names can be used directly.

The `SMTP_PASSWORD` value must be provided at runtime from a controlled environment or secret manager; never commit real secrets to the repository.

### Simple email sending example

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationService {

    private final JavaMailSender mailSender;

    public AccountNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(recipient);
        message.setSubject("Account notification");
        message.setText("Your account has been updated.");

        mailSender.send(message);
    }
}
~~~

The service does not accept a password as a parameter. `JavaMailSender` is already configured at the infrastructure layer; the application simply requests sending the message.

If HTML, attachments, or inline resources are needed, use `MimeMessage` and `MimeMessageHelper` without altering the credential storage principle.

## 6. TLS configuration: STARTTLS and implicit TLS

Two common submission modes:

| Mode | Common port | Sequence |
| --- | ---: | --- |
| STARTTLS | 587 | Connect SMTP then upgrade to TLS |
| Implicit TLS | 465 | TLS handshake immediately upon connect |
| SMTP relay between mail servers | 25 | Depends on relay policy; not intended by default for authenticated app submission |

Providers may use custom ports, so check the documentation of the service you are using.

### STARTTLS on port 587

~~~properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

`starttls.enable` permits STARTTLS; `starttls.required` mandates that the connection upgrade succeed rather than continuing in plaintext if the server does not support it.

### Implicit TLS on port 465

~~~properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

In this mode, TLS begins immediately upon connection. Normally, do not enable STARTTLS on the same implicit TLS connection.

### Do not bypass certificate verification

Never use `mail.smtp.ssl.trust=*` or disable hostname validation to fix TLS errors in production. That opens the risk of connecting to a spoofed endpoint.

When facing TLS handshake errors, check hostname/port, certificate chain, CA, trust store, certificate expiration, TLS version, and proxy/firewall. Fix trust configuration properly instead of skipping verification.

TLS protects data in transit to the SMTP hop the application connects to; it does not encrypt email end-to-end across all hops.

## 7. App passwords differ from regular login passwords

Some providers allow creating an **app password** dedicated to an application or device instead of putting the primary login password into the SMTP client.

Potential benefits:

- Can be revoked individually without changing the main password.
- Easier to track a single workload's credential.
- Supports clients without interactive MFA.
- Limits blast radius if a single application's secret is exposed.

However, not every provider supports app passwords. Organizational policy may forbid app passwords and require OAuth. An app password is still a sensitive secret and must be protected like a password.

| Criterion | App password | OAuth access token |
| --- | --- | --- |
| Form | Password-style secret | Authorization token |
| Common mechanism | PLAIN/LOGIN over TLS | XOAUTH2 if SMTP supports it |
| Lifetime | Per provider and policy | Typically short-lived |
| Scope | Per account/provider policy | Granted scopes/audience/permissions |
| Rotation | Replace/revoke credential | Request new token or revoke grant |
| Refresh | Not an OAuth refresh flow | Via token provider/OAuth grant |

Do not use an app password as an XOAUTH2 token. The authentication mechanism must match the credential type.

## 8. API keys or generated SMTP credentials

Some Email Service Providers issue an SMTP username and a secret named an API key, SMTP key, or generated password. The provider may require passing that secret as the password in `AUTH PLAIN/LOGIN`.

Example:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${PROVIDER_SMTP_USERNAME}
    password: ${PROVIDER_SMTP_SECRET}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

The name “API key” **does not automatically mean XOAUTH2**. An HTTP API key, an SMTP secret, and an OAuth access token are used differently. Specify the auth mechanism according to provider documentation.

Whenever possible, provision a secret with minimal SMTP/send permissions instead of an administrative credential for the entire account.

## 9. OAuth 2.0 and XOAUTH2

OAuth2 allows an application to obtain an **access token** from an authorization server. Some SMTP services support the `XOAUTH2` mechanism to use tokens instead of long-lived passwords.

~~~text
Application
     |
     +---> OAuth authorization/token service
     |          |
     |          +--> grant / permission check
     |          +--> access token
     |
     +---> SMTP submission server
                |
                +--> TLS
                +--> AUTH XOAUTH2
                        |
                        +--> mailbox identity
                        +--> OAuth access token
                |
                +--> MAIL FROM / RCPT TO / DATA
~~~

For this to work, all of the following must hold:

- Both the SMTP server and JavaMail implementation support XOAUTH2.
- The token is issued for the right resource/audience.
- The token carries the appropriate SMTP scope/permission.
- The mailbox identity matches the token's permissions.
- The provider/tenant allows SMTP AUTH and the chosen OAuth flow.
- TLS protects the token in transit.

Not all providers support the same OAuth grant. Some require delegated user consent, while others offer application permissions or service principals with admin configuration conditions. Having a client ID and client secret does not by itself prove that a client-credentials grant is allowed to send SMTP for that mailbox.

**A refresh token, if issued by the flow, is not a credential to pass to SMTP.** It is only used to request a new access token from the token endpoint.

## 10. Selecting the XOAUTH2 auth mechanism in Jakarta Mail

With Jakarta Mail/Angus Mail supporting XOAUTH2, you can use:

~~~properties
mail.smtp.auth=true
mail.smtp.auth.mechanisms=XOAUTH2
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

In the corresponding SMTP client API, the username is usually the mailbox identity; the access token is passed in the password parameter position when the mechanism is XOAUTH2.

Example factory building a sender configuration for a token:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class OAuthSmtpSenderFactory {

    public JavaMailSenderImpl create(
            String host,
            int port,
            String mailbox,
            String accessToken) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setUsername(mailbox);
        sender.setPassword(accessToken);
        sender.setDefaultEncoding("UTF-8");

        Properties props = new Properties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.auth.mechanisms", "XOAUTH2");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(props);
        return sender;
    }
}
~~~

The factory receives an **already issued valid access token** and does not perform the OAuth flow itself. It targets port 587/STARTTLS in this example; if the provider requires 465/implicit TLS, configure the transport accordingly.

If XOAUTH2 is selected while passing an app password to `setPassword`, the server may reject it. Conversely, placing an access token in password while the client only picks PLAIN/LOGIN does not guarantee server acceptance either. Token type, mechanism, and provider policy must align.

## 11. Separating the token provider from the SMTP transport

In real environments, OAuth access tokens can expire and require renewal. Do not fetch a token once at application startup and reuse it forever. Design separate components:

1. **Mail access token provider**: returns a valid token for the required account, audience, and permissions.
2. **SMTP adapter**: selects XOAUTH2, configures the TLS connection, and submits the message.
3. **Application use case**: specifies the request to send email without receiving raw tokens or SMTP secrets.

Contract:

~~~java
public interface MailAccessTokenProvider {

    /**
     * Implementation retrieves an appropriate token for the SMTP mailbox.
     * May cache and refresh according to the provider-allowed OAuth flow.
     */
    String getValidAccessToken(String mailbox);
}
~~~

An illustrative adapter:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OAuth2SmtpMailAdapter {

    private final MailAccessTokenProvider tokenProvider;
    private final OAuthSmtpSenderFactory senderFactory;
    private final String host;
    private final int port;
    private final String mailbox;

    public OAuth2SmtpMailAdapter(
            MailAccessTokenProvider tokenProvider,
            OAuthSmtpSenderFactory senderFactory,
            String host,
            int port,
            String mailbox) {

        this.tokenProvider = tokenProvider;
        this.senderFactory = senderFactory;
        this.host = host;
        this.port = port;
        this.mailbox = mailbox;
    }

    public void send(
            String recipient,
            String subject,
            String body) throws MessagingException {

        String accessToken =
            tokenProvider.getValidAccessToken(mailbox);

        JavaMailSenderImpl sender = senderFactory.create(
            host,
            port,
            mailbox,
            accessToken
        );

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(mailbox);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(body, false);

        sender.send(message);
    }
}
~~~

This example only illustrates collaboration between the token provider and transport. It does not implement the OAuth client, token endpoint, credential store, retries, or permission checks. Those parts must rely on your chosen provider and an appropriate OAuth library.

### Why not mutate the password on a shared sender?

Avoid doing this:

~~~java
sharedSender.setUsername(tenantA);
sharedSender.setPassword(tokenForTenantA);
sharedSender.send(messageA);

// Another thread may overwrite username/password
// before thread A finishes using the configuration.
~~~

In environments with multiple workers/tenants, mutating credentials on a shared instance creates race conditions, intermittent login errors, or sending under the wrong account.

The factory in the example creates a distinct sender configuration per attempt, avoiding shared mutable credentials. In large systems, transport pooling can be optimized, but session/account/token state must be managed in a thread-safe manner.

## 12. Token expiry, refresh, and clock skew

Access tokens usually carry expiration metadata such as `expires_in` or `expires_at`. When a token expires, the SMTP provider can reject AUTH even if the host, username, and TLS configuration are completely valid.

The token provider should be responsible for:

- Caching access tokens by exact account, audience, and permission.
- Recording the expiration timestamp from the OAuth response.
- Refreshing proactively before the token actually expires.
- Accounting for a reasonable clock skew buffer.
- Limiting concurrent token requests for the same account.
- Distinguishing transient token endpoint errors from denied permissions.
- Never logging raw access tokens.
- Handling revocation/rotation of the underlying credential.

Flow:

~~~text
Mail worker needs to send
       |
       v
Token provider
       |
       v
Token cache has a sufficiently valid token?
       |
    +--+--+
    |     |
   Yes    No
    |     |
    |     v
    |   Request a new token via the appropriate OAuth flow
    |     |
    +--+--+
       |
       v
SMTP AUTH XOAUTH2 over TLS
       |
       v
Send MIME message
~~~

If a token has only a few seconds left, the connection or AUTH might start after the token expires. Set a safety margin based on real latency and provider policy.

### Refresh tokens are not SMTP passwords

If the OAuth flow issues a refresh token, that token is only sent to the **OAuth token endpoint** when requesting a new access token. Never configure:

~~~properties
spring.mail.password=<refresh-token>
~~~

and expect XOAUTH2 to work. Some flows such as client credentials can request a new access token without using a refresh token; not every system has refresh tokens.

### Avoiding refresh stampedes

When 100 workers detect that a token is about to expire, if all 100 call the token endpoint simultaneously, the application may hit rate limits or elevated errors. The token provider can use locking/single-flight per account and token audience.

When multiple instances need tokens, consider an appropriate token caching/management mechanism. However, a shared cache must enforce access control and encryption; never store plaintext tokens where every service can read them.

## 13. Handling access tokens expiring mid-send

A token may expire or be revoked between retrieval and when SMTP executes AUTH. In that case, the adapter may receive an authentication failure.

Distinguish between:

- The token expired and a new token can be requested.
- The token lacks the right scope/audience.
- The OAuth grant is unsupported by the SMTP provider.
- SMTP AUTH is disabled for the account/tenant.
- The mailbox identity does not match the token's permissions.
- Permission/admin consent was revoked.
- The token endpoint or identity provider is experiencing an outage.

A cautious strategy:

1. Confirm the error happened at **AUTH**, before MAIL FROM/DATA.
2. Inspect the token cache, expiry, and error code.
3. If the token might be stale, invalidate the cache.
4. Request a fresh access token per policy.
5. Retry once within bounds if appropriate.
6. If it still fails, stop rapid retries and alert to resolve permissions/policy.

Do not catch every `MailAuthenticationException` and refresh tokens endlessly. If the failure is due to a missing scope or the provider forbidding SMTP, fetching another identical token will not help.

A clear AUTH error occurring before DATA normally has not created a submission in that attempt. However, do not apply a “safe retry” rule to timeouts after DATA, because the server may have already accepted the message.

## 14. Authentication and sender authorization are different

An account may authenticate successfully yet not be permitted to send from every address.

For example, SMTP username:

~~~text
notifications@example.com
~~~

while the message sets:

~~~java
helper.setFrom("finance@example.com");
~~~

The provider may require:

- The From header to match the authenticated mailbox.
- From to belong to a verified domain.
- A verified alias.
- Send-as / send-on-behalf permissions granted for another mailbox.
- The envelope sender to comply with relay policy.

When receiving an error like “sender not permitted”, distinguish AUTH errors from sender authorization errors.

### MAIL FROM and MIME From

- `MAIL FROM` is the SMTP envelope/return-path address during the protocol session.
- `From` in MIME headers is the address displayed to the recipient.

The two addresses may differ based on sending policy, bounce processing, and email provider. Successful authentication does not automatically authorize arbitrary values in either field.

Furthermore, SPF/DKIM/DMARC are separate domain authentication/evaluation layers and are not replaced by a successful SMTP login.

## 15. Managing passwords and tokens with a secret store

Never hard-code credentials:

~~~java
sender.setUsername("notifications@example.com");
sender.setPassword("hardcoded-secret");
~~~

If a secret is committed to Git, baked into a build artifact, or logged, revocation is difficult and can impact multiple environments.

Better management practices:

- A secret manager or vault.
- Environment variables injected by the runtime/orchestrator.
- Encrypted deployment secrets with restricted access.
- Workload identity when supported by the provider.
- A token provider managing OAuth grants, client secrets/certificates, and rotation.

Example `application.yml` holding only references:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

**Environment variables are not automatically completely safe.** They can be exposed via container config inspection permissions, process inspection, crash dumps, or pipeline logs if unprotected. Apply the principle of least privilege for users and workloads.

### Do not store tokens in the outbox

A mail outbox holds send requests and business metadata; it should never store SMTP passwords, app passwords, access tokens, or refresh tokens. Workers fetch credentials at the time of sending.

If a job waits for several hours in the outbox, an access token attached to the payload at enqueue time will almost certainly no longer be valid. A token provider solves precisely this problem.

### Do not log credentials

Avoid:

~~~java
log.info("SMTP password: {}", password);
log.debug("OAuth access token: {}", token);
~~~

If diagnosis is needed, log the credential **source identifier**, tenant ID, provider ID, expiry timestamp, or token status—never raw tokens/passwords and never AUTH Base64 strings.

## 16. Credential rotation and revocation

Credentials must have lifecycle management. An application may run for months, while passwords, app passwords, and client secrets may need periodic rotation or rotation upon suspected exposure.

### For passwords/app passwords

1. Create a new secret with appropriate permissions.
2. Store the new secret in the secret manager.
3. Update the application's deployment/secret reference.
4. Test a single email with a test account or controlled send path.
5. Watch auth failures and queue backlog.
6. Revoke the old secret once all instances have switched to the new secret.
7. Record audit logs without storing secrets in logs.

If the provider supports two valid secrets during a transition window, you can use an overlap period to minimize downtime. Otherwise, plan a cutover or safe sending pause.

### For OAuth client secrets or certificates

A client secret used to obtain an access token is a different credential from the access token used at SMTP. Rotating a client secret/certificate requires updating the token provider and may not immediately invalidate all active access tokens. Revocation behavior depends on the provider.

A revoked token or removed permission must make workers stop futile attempts and transition jobs to an attention-needed state, rather than continuing to send with the same failing token.

## 17. Choosing password, app password, generated key, or OAuth

| Need | Typically suitable mechanism | What to verify |
| --- | --- | --- |
| Internal SMTP relay issuing username/password | Password-based AUTH over TLS | Permissions, rotation |
| ESP issuing a dedicated SMTP key | Generated SMTP credential | Username and secret placement |
| Provider permitting app passwords | App password over TLS | Account/tenant policy |
| Provider requiring modern authentication | OAuth access token + XOAUTH2 | SMTP capability, audience, scope, grant |
| Provider offering only an HTTP send API | HTTP mail adapter | Do not force API secrets into SMTP |
| Multiple tenants/accounts | Per-tenant credential resolver | Isolation and concurrency |
| High sending volume | Dedicated credential/service account | Quota, rate limits, audit |

Do not choose OAuth solely because it is newer if the provider does not support SMTP XOAUTH2 for that account type. Conversely, do not continue using legacy username/password when the provider/tenant has disallowed it.

## 18. Common authentication error codes

| Signal | Possible cause | Investigation direction |
| --- | --- | --- |
| `530 Authentication required` | Not authenticated yet or security flow unmet | Check SMTP AUTH and TLS |
| `535 Authentication credentials invalid` | Credential rejected or disallowed by policy | Secret, mechanism, account status, permissions |
| `534` related to authentication policy | Current mechanism not accepted | Provider guidance/enhanced code |
| `454 Temporary authentication failure` | AUTH service temporarily failing | Bounded backoff/retry |
| `503 Bad sequence of commands` | Wrong order of SMTP commands | Transcript and transport config |
| `AuthenticationFailedException` | Jakarta Mail reporting AUTH failure | Nested exception and response |
| `MailAuthenticationException` | Spring wrapper for authentication errors | SMTP response, cause |
| TLS handshake failure | Valid TLS not established yet | Port, certificate, trust store |
| AUTH timeout | Slow network/server | Phase, timeouts, provider outage |
| Sender not authorized after AUTH | Not allowed to use From address | Send-as, verified domain, envelope |

A code like `535` is not always a simple typo in a password. It can be caused by a locked account, disabled SMTP AUTH, an expired/revoked app password, an OAuth token missing permissions, or a new provider policy.

### Reading errors by SMTP phase

~~~text
S: 235 Authentication successful
C: MAIL FROM:<different@example.com>
S: 550 Sender not permitted
~~~

Here AUTH has already succeeded. Changing the password will not fix a sender policy rejection.

If an error occurs before DATA, there is no evidence the server accepted the message. If the client times out after sending DATA, the submission outcome may be ambiguous; do not attribute every timeout to an AUTH error.

## 19. Retries for authentication errors must be bounded

| Scenario | Retry? | Reason |
| --- | --- | --- |
| Definitely wrong password | Do not retry continuously | Can trigger account lockout |
| SMTP AUTH disabled by policy | No | Must fix configuration/permissions |
| Token expired and refreshable | Can refresh then retry once | Fix credential before sending |
| Token missing scope/audience | Do not retry as-is | Obtain proper permissions |
| SMTP AUTH service returns temporary error | Can use exponential backoff | Provider may recover |
| Wrong TLS certificate | Do not bypass certificate | Must fix trust/endpoint |
| Connection timeout before AUTH | Can retry if transient | Not submitted in that attempt |
| Timeout after DATA | Do not treat as auth failure | Duplicate risk |

Repeated authentication failures can trigger security alerts, lock accounts, or cause provider throttling. Therefore, if 100 emails are queued, do not let 100 workers repeatedly hammer the server with the same wrong credentials.

A per-account/provider cooldown or circuit breaker mechanism helps reduce cascading failures. Once credentials are fixed, workers can resume processing the outbox according to rate and deadline policies.

## 20. Multi-tenant and concurrency

An application may send from multiple mailboxes or multiple tenants. If threads concurrently mutate a singleton `JavaMailSenderImpl`:

~~~text
Thread A: setUsername(tenant A)
Thread B: setUsername(tenant B)
Thread A: send(message A)   -> may use the wrong account
~~~

This is a state-sharing bug. Do not use a global mutable sender and swap username/password before each email.

The design should include:

1. Use case supplies tenant ID or sender account ID.
2. Credential resolver returns the valid configuration for that account.
3. OAuth token provider uses the right mailbox/audience/permissions.
4. SMTP adapter creates or selects a concurrency-safe transport configuration.
5. Rate limiter applies per account/provider.
6. Audit records account ID, never secrets.

If tenants are allowed to specify custom SMTP hosts, validate endpoints and control network access to prevent SSRF or unauthorized access to internal services. Never take a raw SMTP URL from an HTTP request and connect arbitrarily.

## 21. Authentication in mail workers and outboxes

An important transactional email can be sent after the business transaction commits, via an outbox worker:

~~~text
Business use case
       |
       v
Save outbox job
       |
       v
Worker claim job
       |
       +--> Resolve account
       +--> Fetch secret/access token
       +--> TLS + SMTP AUTH
       +--> Submit message
       |
       +--> SUBMITTED / RETRY_WAIT / FAILED
~~~

Key points to remember:

- Outbox jobs do not contain credentials.
- Workers fetch a new token if the old token has expired.
- Secret rotation does not force updating old payloads.
- Workers do not hold database transactions open while waiting on OAuth token endpoints or SMTP servers.
- An authentication failure can affect many jobs for the same account; apply cooldown/alerting instead of hot retries.
- SMTP AUTH success does not mean the server accepted the email after DATA.
- If a connection error occurs after DATA, the submission outcome may be AMBIGUOUS; account for duplicates.

A `SUBMITTED` status only reflects transport acceptance per API/provider evidence. `DELIVERED` is a later step requiring separate delivery events if supported by the provider.

## 22. Testing without production passwords

### Unit tests

You can mock `MailAccessTokenProvider` and delivery adapters to verify:

- Tokens are fetched for the right mailbox/tenant.
- Sending does not proceed if the token provider errors.
- Expired tokens are not reused.
- Auth failures are classified properly.
- Concurrent requests do not mix up credentials.
- Passwords or access tokens are never logged.

### SMTP integration tests

Use an appropriate SMTP test server to verify:

- AUTH PLAIN/LOGIN with dummy credentials.
- STARTTLS/implicit TLS with test certificates.
- Authentication failure responses.
- Messages are submitted after AUTH succeeds.
- Client refuses to send if STARTTLS is required but unsupported by the server.

Not every SMTP test server supports XOAUTH2. Testing XOAUTH2 may require a stub supporting the exact mechanism or a provider sandbox.

### Provider sandbox

Against a real provider, verify:

- Advertised SMTP AUTH capabilities.
- TLS mode/hostname verification.
- OAuth token scopes/audience/grant.
- Send-as permissions and verified domains.
- Expired/revoked token behavior.
- Quotas and throttling.
- Provider message acceptance after DATA.

Use test accounts and test recipients; never inject production data into tests.

## 23. SMTP debug logging and security

Jakarta Mail includes a protocol debugging mechanism. In controlled test environments, you can enable:

~~~properties
spring.mail.properties.mail.debug=true
~~~

Do not leave it enabled long-term in production without strict controls on sensitive data: depending on version and configuration, transcripts may contain envelopes, recipient addresses, headers, AUTH metadata, or secrets.

Investigation order:

1. Check host, port, DNS, and network.
2. Confirm STARTTLS or implicit TLS is right.
3. Check the server certificate and hostname.
4. Inspect EHLO capabilities and AUTH mechanisms.
5. Verify the client selects the right PLAIN/LOGIN/XOAUTH2.
6. Read the AUTH response without exposing credentials.
7. After `235`, check sender permissions if rejected.
8. Then check RCPT TO, DATA, and the final submission response.
9. Turn debugging off and handle retention/redaction.

If the server does not advertise `XOAUTH2`, putting a token into password will not make it work. If the server advertises XOAUTH2 but the token has the wrong audience/permissions, AUTH will also fail.

## 24. Runbook for resolving SMTP authentication failures

**Step 1 — Isolate scope**

- Are all tenants failing or only one account?
- Was a secret recently rotated or a new version deployed?
- Was there a provider policy change or account lockout?
- Did failure start at TLS, AUTH, or MAIL FROM?

**Step 2 — Check credentials**

- Does the secret reference exist?
- Does the workload have permission to read the secret?
- Is the username/mailbox right?
- Was the password/app password revoked?
- Has the access token expired?
- Does the token have the right audience/scope/permissions?
- Is SMTP AUTH disabled by tenant policy?

**Step 3 — Check transport**

- Host/port and TLS mode match documentation.
- Certificate chain/hostname are valid.
- AUTH mechanism matches the credential type.
- Plaintext fallback is not enabled.

**Step 4 — Recover**

- Rotate/update secrets if wrong or exposed.
- Refresh tokens under a valid grant.
- Request missing permissions/admin consent.
- Throttle down/apply cooldown if the provider is temporarily failing.
- Consider switching to a provider-approved auth flow or HTTP mail API if current SMTP AUTH is unsupported.

**Step 5 — Verify**

- Send a test message with a correlation ID.
- Confirm SMTP AUTH succeeds.
- Confirm the server accepts DATA per the final response.
- Watch outbox backlog.
- Monitor delivery events/bounces if offered by the provider.

Do not delete failed jobs just to clear the queue; preserve state and handle properly per retry/dead-letter policy.

## 25. Common anti-patterns

| Anti-pattern | Consequence | Alternative |
| --- | --- | --- |
| Hard-code passwords | Secrets exposed via Git/artifacts | Vault/environment injection |
| Use personal account passwords for services | Overly broad access, hard to rotate | Service account or dedicated credential |
| AUTH over plaintext | Credentials exposed in transit | Require TLS |
| STARTTLS enable allowing plaintext fallback | Traffic may go unencrypted | STARTTLS required |
| Disable hostname verification | Easy to connect to wrong SMTP server | Validate certificate/hostname |
| Use `ssl.trust=*` to bypass TLS errors | Breaks trust boundary | Fix CA/trust store |
| Use XOAUTH2 with an app password | Wrong credential type | Choose matching mechanism |
| Put refresh token into SMTP password | Wrong flow, exposes long-lived secret | Use access tokens only |
| Cache tokens indefinitely | Auth fails upon expiry | Refresh and clock skew handling |
| Mutate credentials on a shared sender | Race condition across workers | Per-account/thread-safe adapter |
| Retry wrong password endlessly | Account lockout and overload | Fail fast/cooldown/alert |
| Store tokens in the outbox | Secret exposure, stale tokens | Fetch at send time |
| Print SMTP AUTH transcripts | Exposes secrets and PII | Redaction/scoped debug |
| Confuse AUTH success with delivered | Misleading mail status | Track DATA/delivery separately |
| Confuse HTTP API key with OAuth token | Wrong mechanism config | Follow exact provider contract |
| Ignore send-as permissions | AUTH succeeds but sending is blocked | Verify sender identity |

## 26. Implementation workflow

A clear implementation flow:

1. **Identify SMTP provider/account policy** and supported auth mechanisms.
2. **Choose credential type**: SMTP password, app password, generated secret, or OAuth access token.
3. **Configure mandatory TLS** with hostname/certificate validation.
4. **Store secrets safely** in a vault or runtime secret injection.
5. **For password-based AUTH**, configure `spring.mail.username/password`.
6. **For OAuth**, implement a token provider, XOAUTH2, and appropriate SMTP permissions.
7. **Separate the mail adapter from use cases**; never pass credentials through business logic.
8. **Manage rotation/expiry** and prevent token refresh stampedes.
9. **Classify AUTH/TLS/sender-policy failures** instead of retrying every error.
10. **For critical emails**, persist in an outbox and fetch credentials in the worker at execution time.
11. **Test** with fake/test SMTP and provider sandboxes.
12. **Monitor** auth failures, token refresh errors, queue backlogs, and credential expiry.

~~~text
Use case needs to send mail
       |
       v
MailDeliveryPort
       |
       v
SMTP adapter
       |
       +--> Resolve provider / sender account
       |
       +--> Resolve credential
       |       |
       |       +--> SMTP password/app key from vault
       |       +--> Access token from token provider
       |
       +--> TLS connection
       |
       +--> AUTH PLAIN/LOGIN/XOAUTH2
       |       |
       |       +--> 235 success
       |       +--> 4xx/5xx failure
       |
       +--> MAIL FROM / RCPT TO / DATA
       |
       v
Submission outcome
       |
       +--> SUBMITTED
       +--> RETRY_WAIT / FAILED / AMBIGUOUS
~~~

## 27. Takeaways

- SMTP AUTH proves permission to use the relay, not that an email was delivered.
- Username may be a mailbox or service account, depending on the provider.
- Passwords, app passwords, SMTP-generated secrets, and OAuth tokens are distinct credential types.
- AUTH PLAIN/LOGIN rely on password-like credentials; Base64 is not encryption.
- XOAUTH2 uses an appropriate **access token**, never a refresh token.
- Protect credentials with required STARTTLS or implicit TLS alongside certificate/hostname validation.
- Spring Boot provides `spring.mail.username/password` and JavaMail properties; it does not automatically fetch/refresh every OAuth token.
- Tokens must carry the right scope/audience/permission and be permitted by the provider for SMTP.
- Token providers need caching/refresh/clock skew/cooldowns and must never log raw tokens.
- Avoid mutating username/password on a shared `JavaMailSenderImpl` across concurrent requests.
- Successful AUTH does not automatically permit sending from any From address.
- Secrets do not belong in business entities or mail outbox payloads.
- Rotation and least privilege must be designed from the start.
- Auth errors must be classified; never infinitely retry rejected credentials.
- Test TLS, authentication, sender permissions, and token expiry in appropriate environments.

**Core principle:** choose the right authentication mechanism per SMTP provider, protect credentials in a secret store and over a TLS channel, use valid access tokens when choosing OAuth/XOAUTH2, and separate the authentication layer from mail-sending use cases. Organizing things this way lets Spring Framework Mail applications operate and rotate credentials safely while handling errors clearly without leaking secrets.

