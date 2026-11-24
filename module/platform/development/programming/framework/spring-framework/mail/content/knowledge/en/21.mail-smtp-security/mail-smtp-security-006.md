# OAuth2 or Modern Provider Authentication Mechanisms

When a **Spring Framework Mail** application connects to an SMTP server, authentication determines whether the application is permitted to send mail under a given identity. The traditional configuration supplies a username and password:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

This approach can still suit some SMTP servers, yet many email service providers are increasingly restricting or retiring **Basic Authentication with account passwords**. They may require **OAuth 2.0**, scoped app passwords, dedicated SMTP relay credentials, or an email-sending API protected by tokens, API keys, or workload identities.

In that context, a Java application must solve two distinct problems:

1. **Obtain a credential compliant with provider policy.** With OAuth 2.0, this is typically an access token issued for a mailbox or application with specific permission scopes.
2. **Pass the credential using the exact mechanism supported by the SMTP server.** For example, when the SMTP server supports `AUTH XOAUTH2`, JavaMail/Jakarta Mail can pass the access token into this authentication mechanism instead of sending an account password via `AUTH LOGIN` or `AUTH PLAIN`.

**Important point:** OAuth 2.0 is not an email content encryption method and does not replace TLS. It manages **authorization and access delegation**. The application still needs TLS certificate checks, token protection, permission scoping, and SMTP error handling.

## 1. Why is modern authentication needed for SMTP?

In many systems, SMTP credentials are configured as a static password:

~~~text
Application
    |
    | username + password
    v
SMTP server
    |
    v
Accept or reject mail submission
~~~

Using a long-lived password has several limitations:

- If the secret is exposed, an attacker can keep using it until it is changed or revoked.
- It is hard to restrict permissions to a single application or sending purpose.
- A password shared across multiple services makes it difficult to trace the source of an incident.
- Changing the password can impact multiple processes simultaneously.
- Providers may forbid SMTP login with account passwords under security policy.
- Some environments mandate MFA, conditional access, workload identity, or restricting authorized applications.

OAuth 2.0 separates the **long-lived credential used to request authorization** from the **short-lived access token used to access the service**. Access tokens typically have an expiration time, scopes, and a target audience/resource defined by the token issuer.

This does not mean OAuth is “automatically secure”. If an application leaks a refresh token, client secret, or access token, risks still remain. The difference is that granting, revoking, scoping, and monitoring access can be managed independently rather than relying on a shared mailbox password.

### 1.1. Distinguishing authentication, authorization, and encryption

| Concept | Question answered | Example |
| --- | --- | --- |
| **Authentication** | Which identity is the application/principal proving? | SMTP authentication via SASL XOAUTH2 |
| **Authorization** | What is that identity allowed to do? | Token has permission to send for the granted mailbox |
| **Transport encryption** | Is data on the wire protected? | TLS, STARTTLS |
| **Message encryption** | Is email content encrypted for the recipient? | S/MIME or OpenPGP, if used by the product |
| **Identity policy** | Is the application permitted to use this From address? | Send As/alias/sender domain permissions |

An SMTP session with a valid token but without TLS can expose the token in transit. A session with proper TLS whose token lacks sending permission will also be rejected by the provider. Both conditions must be verified separately.

## 2. OAuth 2.0 and SMTP AUTH XOAUTH2 are not the same thing

OAuth 2.0 is an **authorization framework**: the application receives an access token from an authorization server based on an approved grant flow.

SMTP is a mail-sending protocol. An SMTP server uses the `AUTH` extension to authenticate the SMTP client. Some servers support the SASL `XOAUTH2` mechanism or another suitable bearer-token mechanism.

In the common case:

~~~text
OAuth authorization server
        |
        | OAuth 2.0 grant/token response
        v
    Access token
        |
        | Token is used as credential
        v
Spring Mail / Jakarta Mail
        |
        | SMTP AUTH XOAUTH2 (over TLS)
        v
   SMTP submission server
~~~

The application must know:

- Which issuer issued the token.
- Which SMTP resource/server the token targets.
- Which mailbox or service principal the token is bound to.
- Which scopes/permissions the token holds.
- How long the token remains valid.
- Whether the SMTP server supports `AUTH XOAUTH2` or another mechanism.

You cannot take an arbitrary API access token, drop it into SMTP, and assume it will work. **Audience, scope, mailbox identity, and provider policy must match.**

### 2.1. How do AUTH PLAIN/LOGIN differ from AUTH XOAUTH2?

| Aspect | `AUTH LOGIN` / `AUTH PLAIN` | `AUTH XOAUTH2` |
| --- | --- | --- |
| Typical credential | Username + password or app password | Mailbox identity + OAuth access token |
| Credential lifecycle | May be long-lived | Access tokens are typically short-lived |
| Revoking access | Change password, lock account, or policy | Revoke grant/app, block principal, token expiry |
| MFA/conditional access | Depends on mechanism/provider; basic auth struggles | Token issuance flows can enforce modern policies |
| TLS | Still mandatory in secure design | Still mandatory |
| Jakarta Mail config | Select `LOGIN`/`PLAIN` per server | Explicitly select `XOAUTH2` |
| Operating condition | Provider permits passwords | Provider supports XOAUTH2 and token has sufficient permissions |

This does not mean every `AUTH PLAIN` implementation transmits readable passwords over the network: when valid TLS is used, AUTH data is protected inside the TLS channel. Still, TLS does not solve the storage risk and broad permissions of long-lived passwords.

### 2.2. The SMTP server must advertise the supported mechanism

After establishing TLS and re-issuing `EHLO`, the server may advertise:

~~~text
S: 250-smtp.example.com
S: 250-AUTH XOAUTH2 PLAIN LOGIN
S: 250 SIZE 35882577
~~~

This is an illustrative example, not a guaranteed response from every provider.

If the server does not support XOAUTH2 or the account is not allowed to use SMTP AUTH, merely adding:

~~~properties
mail.smtp.auth.mechanisms=XOAUTH2
~~~

will not make the server support the feature. In that case, consult provider documentation, tenant policies, and the option of using an email-sending API instead.

## 3. Structure of the XOAUTH2 authentication string

Some providers use a SASL payload formatted as:

~~~text
user=<mailbox-address>^Aauth=Bearer <access-token>^A^A
~~~

Here `^A` represents the control character `Control-A` (`0x01`), not the literal caret and letter A. The payload is typically base64-encoded when executing `AUTH XOAUTH2` over SMTP.

Illustrative pre-encoding content, for descriptive purposes only:

~~~text
user=notifications@example.com<0x01>auth=Bearer ACCESS_TOKEN<0x01><0x01>
~~~

**Do not manually assemble the AUTH string in your application when the SMTP library already supports XOAUTH2.** Spring Mail builds on Jakarta Mail; a compatible SMTP provider handles formatting and the authentication exchange. Manually handling base64, control characters, and raw socket SMTP dialogue easily causes protocol bugs and token leaks.

### 3.1. Why shouldn't tokens be placed in email headers?

An access token serves **authentication with the SMTP server**. It is not email content and must never be placed into:

~~~text
Authorization: Bearer <token>     # Not an email header to send
X-Access-Token: <token>           # Never add this
Subject: <token>                  # Never
~~~

Email headers can pass through many systems and be stored long-term. Tokens must only be transmitted during the SMTP authentication step over TLS or to the corresponding HTTP token/API endpoint.

## 4. OAuth 2.0 authentication flow when sending SMTP

Common architectural flow:

~~~mermaid
sequenceDiagram
    participant A as Spring application
    participant I as Identity provider
    participant M as SMTP server
    A->>I: Request access token
    I-->>A: Access token + expiry + scope
    A->>M: TLS / STARTTLS
    M-->>A: Secure SMTP session
    A->>M: EHLO, AUTH XOAUTH2
    M-->>A: Authentication success
    A->>M: MAIL FROM, RCPT TO, DATA
    M-->>A: Submission response
~~~

These are two separate exchanges:

1. **Token acquisition:** use an OAuth 2.0 grant to fetch a token from the identity provider.
2. **SMTP submission:** use the token as the credential in `AUTH XOAUTH2` to submit the email.

If token acquisition fails, the application does not even need to open an SMTP session. If a token is obtained but SMTP rejects authentication, the cause may be wrong audience, scope, mailbox identity, policy, or an expired token.

### 4.1. Common grant flows

| Flow | Context | Notes |
| --- | --- | --- |
| **Authorization Code** (possibly with PKCE) | User authorizes the application to act on their behalf | Token carries user permissions; needs proper consent and refresh |
| **Refresh Token** | Obtain a new access token after initial authorization | Refresh token is a secret to protect; providers enforce rotation/revocation policies |
| **Client Credentials** | Workload/service sends without an interactive user | Use only if the provider offers app-only permissions for SMTP |
| **Service account + delegated authority** | Enterprise environment where admins grant delegation | Provider-dependent; typically requires admin setup and scope limits |
| **Managed identity / workload identity federation** | Cloud workload obtains tokens without storing long-lived client secrets | Suitable only if the SMTP resource server or API supports that identity/token |

Do not assume **Client Credentials** always works for SMTP. An SMTP provider might allow only delegated user tokens, whereas its HTTP sending API supports application tokens.

### 4.2. Access tokens and refresh tokens are different

**Access token**:

- used to access a service under the granted audience/scopes;
- typically short-lived;
- passed into SMTP XOAUTH2;
- should not be stored as static config in a repository.

**Refresh token**:

- used to request a new access token when supported by the flow/provider;
- may live longer and be subject to rotation/revocation policies;
- must never be passed into SMTP `AUTH XOAUTH2` in place of an access token;
- must live in a secure store with least-privilege access.

If an application only holds a refresh token and puts it into `spring.mail.password`, SMTP authentication will typically fail because SMTP expects a valid access token, not a refresh token.

## 5. Preparation steps with the email provider

Before writing Spring Mail code, clarify the provider-side requirements:

1. Is SMTP AUTH enabled at the organization/tenant and mailbox levels?
2. What are the required SMTP server, port, and TLS mode?
3. Does SMTP support XOAUTH2 or another mechanism?
4. Where must the OAuth application/client be registered?
5. What is the specific API permission or scope for **SMTP sending**?
6. Which flows are supported: delegated, app-only, service account, or only certain flows?
7. Are admin consent, mailbox permissions, or Send As permissions required?
8. Is the `From` address restricted to the authorized mailbox/alias?
9. What are the token endpoint and required audience/resource?
10. How do rate limits, quotas, tenant restrictions, and auditing apply?

A token can be issued successfully yet SMTP AUTH still fail if SMTP submission is disabled on the mailbox or the service principal has not been granted the corresponding permission.

### 5.1. Do not confuse “able to sign in” with “permitted to send”

A user might log into webmail successfully or obtain a token for another API while not being permitted to use SMTP AUTH. Similarly, an app might have permission to read profiles or mailbox metadata without permission to send mail.

Diagnosis should verify all of:

- token issuer, audience, and scopes/roles;
- identity bound to the token;
- SMTP AUTH policy;
- sender/From permissions;
- whether the provider accepts the chosen flow.

### 5.2. Do not choose broader scopes just to make errors disappear

If a provider requires a broad mailbox scope for SMTP XOAUTH2, understand the risk and approval policy. Still, never default to granting **full mail read/write permissions** to an application if the provider offers a dedicated sending method with narrower permissions.

Consider using an HTTP email-sending API with finer-grained permissions if your sending needs do not strictly require SMTP.

## 6. Provider example: Google Workspace/Gmail

Gmail supports OAuth 2.0 for mail protocols, including SMTP using XOAUTH2 under the applicable configuration and policies.

Points to distinguish:

- The OAuth client must be registered and authorized per account/organization.
- The token must carry a scope supported by Gmail SMTP. A scope commonly cited for SMTP/IMAP/POP in Gmail OAuth documentation is `https://mail.google.com/`; this is a **broad** scope, requiring proper review and approval.
- When using the authorization code flow, obtaining a refresh token depends on consent, offline access, and active Google policies.
- In Google Workspace, a service account with **domain-wide delegation** may be an admin-permitted option; it does not automatically apply to personal Gmail accounts.
- App verification, restricted scope, tenant admin, and mailbox policies can affect usability.

Logical flow:

~~~text
Google OAuth authorization/token flow
  -> access token for authorized mailbox
  -> JavaMailSender SMTP AUTH XOAUTH2
  -> smtp.gmail.com (TLS per provider config)
~~~

**Never assume** a regular Google service account can send SMTP on behalf of any user without proper authorization by a Workspace administrator. Scopes and policies can change; during actual implementation, verify against official Google documentation at configuration time.

### 6.1. Is an app password OAuth2?

No. An **app password** (if permitted by the account and provider policy) is still a password-like credential, not an OAuth access token. Some systems use app passwords when multi-factor authentication is enabled, yet:

- it lacks OAuth's grant/refresh flows;
- permission scoping and revocation depend on the provider;
- it may be blocked by administrators or account types;
- it should not be treated as a long-term solution if policy already mandates OAuth.

Only use an app password if the provider currently supports it, the organization allows it, and the mechanism fits security requirements.

## 7. Provider example: Microsoft Exchange Online/Outlook

Exchange Online offers OAuth authentication capabilities for SMTP AUTH depending on account type, granted permissions, and tenant/mailbox settings.

Common concepts:

- **Delegated permissions:** the application acts on behalf of an authorized user. Microsoft documentation gives examples of delegated SMTP scopes such as `https://outlook.office.com/SMTP.Send`.
- **Application permissions:** the application sends under a workload/app identity in Exchange Online-supported configurations; this may involve the `SMTP.SendAsApp` permission and admin setup of service principal/mailbox permissions.
- **Token audience/resource:** the application must acquire a token targeting the corresponding Exchange/Outlook service. For certain app-only flows, Microsoft documentation uses a token request for resource `https://outlook.office365.com/.default`; do not substitute Microsoft Graph scopes when authenticating to SMTP.
- **SMTP AUTH policy:** even with a valid token, the organization or mailbox may still block SMTP AUTH.
- **Send As:** using a From address different from the authorized user/service principal requires appropriate policy permissions.

A common mistake is fetching a **Microsoft Graph token** and passing it straight into SMTP XOAUTH2. Tokens for Graph `Mail.Send` and tokens for Exchange SMTP can differ in audience and permissions. Do not treat them as interchangeable.

When the job only requires sending email, an HTTP API such as Microsoft Graph `sendMail` can be an alternative; compare limits, permission requirements, and response semantics before choosing.

### 7.1. Delegated and app-only models differ

~~~text
Delegated:
  User consent / organization policy
      -> delegated SMTP token
      -> authorized mailbox

App-only (when supported and authorized by provider):
  Service principal / application identity
      -> application token
      -> SMTP permission + mailbox policy
~~~

No JavaMail property grants app-only permissions automatically. Most of the setup resides in the identity provider, admin consent, and Exchange/tenant configuration. Only afterward is the token passed to SMTP XOAUTH2.

**Version/policy note:** Endpoints, permissions, SMTP AUTH availability, and Microsoft guidance evolve over time, tenant, and product. Scope examples here are for conceptual identification; verify against official documentation for your target deployment environment.

## 8. Spring Mail architecture when tokens change over time

A typical Spring Boot configuration creates a singleton `JavaMailSender` using properties from `spring.mail.*`. This is convenient when username/password are stable credentials.

However, OAuth access tokens expire. If you only start the application once and set:

~~~yaml
spring:
  mail:
    password: ${OAUTH_ACCESS_TOKEN}
~~~

the token will expire after the application runs for a while. Acquiring fresh tokens must be integrated into the lifecycle of **each SMTP authentication attempt**, or into a self-refreshing token cache layer.

Desired flow:

~~~text
MailService.send(mail)
     |
     v
AccessTokenProvider.getValidToken(mailbox)
     |
     +-- token still valid, return cached
     |
     +-- token nearing expiry, refresh/acquire
     |
     v
SMTP sender with current access token
     |
     v
AUTH XOAUTH2 + send message
~~~

### 8.1. Separating the token provider from the mail service

An application-level interface:

~~~java
public interface SmtpAccessTokenProvider {
    /**
     * Returns a valid access token for the mailbox's SMTP.
     * May retrieve from cache or perform an OAuth token exchange.
     *
     * Throws an application-contract exception if a token cannot be obtained.
     */
    String getValidAccessToken(String mailboxAddress);
}
~~~

The mail service only knows it needs an access token to authenticate to SMTP; it does not need to know whether the flow is authorization code, client credentials, or workload identity.

The provider implementation layer knows:

- which client registration applies to the mailbox;
- where access tokens are stored and when they expire;
- how refresh tokens/identity credentials are protected;
- which scopes and audience the provider requires;
- how to report errors when refresh fails.

## 9. Example sending email with JavaMailSenderImpl and XOAUTH2

A simple approach with a clear lifecycle is creating a **short-lived sender per send operation**, fetching a valid access token right before opening the connection. This avoids mutating `password` on a singleton `JavaMailSenderImpl` bean while multiple threads are sending.

### 9.1. Application configuration

Example `application.yml`:

~~~yaml
app:
  smtp:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    mailbox: ${SMTP_MAILBOX}
    from: ${SMTP_FROM:notifications@example.com}
~~~

These are application-defined properties, not mandatory built-in Spring Boot properties. The token is not in YAML; it is supplied via `SmtpAccessTokenProvider`.

### 9.2. Illustrative mail service

~~~java
package com.example.mail.infrastructure;

import java.util.Properties;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OAuth2SmtpMailService {
    private final SmtpAccessTokenProvider accessTokens;
    private final String smtpHost;
    private final int smtpPort;
    private final String mailbox;
    private final String from;

    public OAuth2SmtpMailService(
            SmtpAccessTokenProvider accessTokens,
            @Value("${app.smtp.host}") String smtpHost,
            @Value("${app.smtp.port:587}") int smtpPort,
            @Value("${app.smtp.mailbox}") String mailbox,
            @Value("${app.smtp.from}") String from) {
        this.accessTokens = accessTokens;
        this.smtpHost = smtpHost;
        this.smtpPort = smtpPort;
        this.mailbox = mailbox;
        this.from = from;
    }

    public void sendText(
            String recipient,
            String subject,
            String body) {

        // Token must be for the authorized SMTP resource/mailbox.
        String token = accessTokens.getValidAccessToken(mailbox);

        // Do not mutate password/token on a singleton shared across threads.
        JavaMailSenderImpl sender = createSender(token);
        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");
            helper.setFrom(from);
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(body);
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot prepare SMTP message", ex);
        }

        // MailException propagates to the orchestration layer for classification.
        // Returning without error only indicates SMTP submission, not Inbox delivery.
        sender.send(message);
    }

    private JavaMailSenderImpl createSender(String accessToken) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(smtpHost);
        sender.setPort(smtpPort);
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

Key points:

1. `mailbox` is passed as the SMTP username.
2. `accessToken` is passed into the credential position JavaMail uses for authentication; with `auth.mechanisms=XOAUTH2`, it is an OAuth bearer token, **not an account password**.
3. `mail.smtp.auth.mechanisms=XOAUTH2` allows only the requested mechanism under this configuration, preventing accidental fallback to LOGIN/PLAIN.
4. `mail.smtp.starttls.required=true` enforces upgrading to a secure channel via STARTTLS on the appropriate SMTP submission port.
5. `mail.smtp.ssl.checkserveridentity=true` enforces hostname verification on the TLS certificate where supported by the provider.
6. A new sender is created per send operation, avoiding race conditions from calling `setPassword(...)` on a shared singleton.
7. The token must have enough remaining lifetime to complete connection and SMTP authentication.

**Scope of the example:** it does not include token-fetching implementation, retries, queues, template rendering, full validation, or multi-tenant logic. In production deployments, those pieces require clear policies and testing against the real provider. Specifically, `mail.smtp.auth.mechanisms` is an SMTP provider property; your Jakarta Mail/Angus Mail version must support `XOAUTH2`.

### 9.3. Why not use a singleton and call setPassword for each email?

Error-prone pattern:

~~~java
@Autowired
JavaMailSenderImpl sharedSender;

void sendWithToken(String token, MimeMessage mime) {
    sharedSender.setPassword(token);
    sharedSender.send(mime);
}
~~~

If two threads run concurrently:

~~~text
Thread A: setPassword(token-for-A)
Thread B: setPassword(token-for-B)
Thread A: sender.send(message-for-A)
~~~

Thread A may use B's credential. This is especially dangerous in multi-account/multi-tenant systems. If a high-performance singleton sender is needed, design an adapter performing per-connection token resolution, isolating account identities, and testing concurrency thoroughly—never simply mutate password before each `send`.

### 9.4. Does creating a new sender lose connection pooling benefits?

The new-sender example prioritizes clarity and concurrency safety. Object creation cost is usually tiny compared to opening an SMTP/TLS connection. However, at high throughput, opening many connections can increase latency or hit provider limits.

In production, consider:

- bounding concurrent SMTP workers;
- connection lifecycle and token expiry;
- per-mailbox/tenant quotas;
- connection reuse if supported by the provider and strictly isolated by identity;
- retry/backoff and monitoring;
- choosing an HTTP sending API when high scale is required.

Never share an authenticated transport across different mailboxes or tenants without explicit isolation design.

## 10. Token provider using Spring Security OAuth2 Client

Spring Security OAuth2 Client can help acquire and refresh access tokens via `OAuth2AuthorizedClientManager`, depending on the grant flow and configuration. However, this library **does not automatically turn `JavaMailSender` into an SMTP XOAUTH2 sender**. It solves the token acquisition part; your mail sender code must still pass the token to the appropriate SMTP mechanism.

### 10.1. Example token provider for app-only workloads

In cases where the provider **genuinely permits client credentials for the SMTP resource**, a service can fetch a token via the manager:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.stereotype.Component;

@Component
public class ClientCredentialsSmtpTokenProvider
        implements SmtpAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public ClientCredentialsSmtpTokenProvider(
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Override
    public String getValidAccessToken(String mailboxAddress) {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("smtp-workload")
                        .principal("mail-sender-service")
                        .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException(
                    "Cannot authorize SMTP OAuth client");
        }

        OAuth2AccessToken token = client.getAccessToken();
        return token.getTokenValue();
    }
}
~~~

Explanation:

- `smtp-workload` is an application-defined registration ID.
- Principal `mail-sender-service` is the identity used to associate the authorized client in this workload example.
- The manager must be configured with an `OAuth2AuthorizedClientProvider` supporting client credentials and an appropriate authorized client store.
- The manager may reuse or acquire a new token according to expiry policy; do not mint a fresh token for every email while the current token is still valid.
- The `mailboxAddress` parameter is accepted by the interface, yet **does not automatically grant permission on behalf of that mailbox**. The actual provider must ensure the app principal is authorized to send for the specified mailbox.

This is an example for a **conditional app-only flow**. If the provider only supports delegated SMTP OAuth, you must use the user's authorized client and protect the refresh token; it cannot be replaced with this client-credentials snippet.

### 10.2. Client registration configuration

A conceptual configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          smtp-workload:
            provider: smtp-idp
            client-id: ${OAUTH_CLIENT_ID}
            client-secret: ${OAUTH_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - ${SMTP_OAUTH_SCOPE}
        provider:
          smtp-idp:
            token-uri: ${OAUTH_TOKEN_URI}
~~~

`SMTP_OAUTH_SCOPE`, `OAUTH_TOKEN_URI`, and client registration values must come from provider documentation. Do not copy one provider's example verbatim to another provider.

This also does not mean every application must use a client secret. Certificate-based credentials, workload identity federation, or managed identity can be used depending on the platform and libraries, if supported by the provider.

### 10.3. Using AuthorizedClientManager in the right context

Spring Security offers several ways to organize OAuth authorized clients. For background services not tied to an HTTP request or an authenticated end user, a manager implementation backed by `OAuth2AuthorizedClientService` is typically more suitable than the servlet-request-based variant.

For delegated flows, the application must manage:

- the authorizing user;
- storage of the authorized client and refresh token;
- refresh/revocation logic;
- scenarios where the user is disabled or consent is revoked;
- mailbox identities permitted for sending;
- errors requiring user or admin re-authorization.

Do not use one administrator's authorized client and assume it can send on behalf of all mailboxes.

## 11. Caching tokens and refreshing before expiration

Access tokens usually have a lifetime, requiring a clear lifecycle:

~~~mermaid
flowchart TD
    A["Mail job ready to send"] --> B{"Token exists for resource/identity?"}
    B -->|No| C["Acquire token"]
    B -->|Yes| D{"Token sufficiently valid?"}
    D -->|Yes| E["Use token"]
    D -->|Expiring soon| C
    C --> F{"Acquire succeeded?"}
    F -->|Yes| E
    F -->|No| G["Fail before SMTP / schedule appropriate retry"]
    E --> H["SMTP AUTH XOAUTH2"]
~~~

A cache key may need to include:

~~~text
provider / tenant / client registration / mailbox identity / scopes
~~~

Do not cache solely by username if the same username can be used across different tenants, scopes, or OAuth clients.

### 11.1. Safety margin

Suppose a token expires at 14:00:00. The application should not check at 13:59:59 that the token is “not yet expired” and start a send operation that may take several seconds.

An illustrative policy:

~~~java
boolean shouldRefresh(
        Instant expiresAt,
        Instant now,
        Duration safetyWindow) {
    return expiresAt == null
            || !expiresAt.isAfter(now.plus(safetyWindow));
}
~~~

The safety window can be based on SMTP timeouts, clock skew, and provider policy. There is no single magic number for every application.

### 11.2. Avoiding refresh stampedes

If hundreds of workers notice a token is nearly expired at the same time and all request a new token, the identity provider can become overloaded or rate-limit requests.

A token provider can use:

- caching by identity/resource/scope;
- locking or single-flight refresh per cache key;
- limiting concurrent token requests;
- backoff when the token endpoint experiences transient errors;
- handling refresh-token rotation per provider contract;
- never storing raw access tokens in logs/metrics.

When refresh fails, do not keep using an expired token hoping SMTP will accept it.

### 11.3. Distinguishing rejected tokens from slow SMTP

**Token acquisition errors** occur before sending the message; retrying token acquisition per policy normally carries no risk that the email was already sent.

**SMTP errors after sending data** can occur even though the provider already received the email. If the application blindly “refreshes the token and resends the entire message” on every `MailException`, it may send duplicates.

Determine which stage failed before retrying.

## 12. TLS remains a prerequisite

OAuth bearer tokens must be protected in transit. SMTP typically has two ways to establish TLS:

| Mode | Common port | How it works |
| --- | --- | --- |
| **SMTP submission + STARTTLS** | 587 | Connect SMTP, require STARTTLS, then authenticate/send over TLS channel |
| **Implicit TLS / SMTPS** | 465 | Establish TLS immediately upon opening connection, then run SMTP |

Specific ports and modes are specified by the provider; do not infer them solely from port numbers.

### 12.1. Mandatory STARTTLS

~~~properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.checkserveridentity=true
~~~

`starttls.enable=true` requests STARTTLS when supported; `starttls.required=true` prevents silently continuing an un-upgraded connection if the server does not support STARTTLS. Server identity checking helps prevent connecting to a host with the wrong certificate.

Never set `starttls.enable=false` or drop `starttls.required` just to “fix a connection error” if your application's policy requires protecting credentials over TLS.

### 12.2. Implicit TLS on port 465

If the provider requires TLS immediately upon connection:

~~~properties
mail.smtp.ssl.enable=true
mail.smtp.ssl.checkserveridentity=true
mail.smtp.auth=true
mail.smtp.auth.mechanisms=XOAUTH2
~~~

Pair with the right host and port, such as port 465 **if** provider documentation uses that port. Do not configure both implicit TLS and STARTTLS in a way that conflicts with the selected endpoint.

### 12.3. Do not disable certificate verification

To “fix” certificate errors, some projects use a trust-all socket factory. This can cause access tokens to be sent to a spoofed server.

Instead:

- verify the host;
- configure a valid truststore;
- update CA/certificate chains;
- check proxies or TLS inspection policies;
- cross-check the provider endpoint.

Never send bearer tokens over an untrusted TLS channel.

## 13. Sender identity and From policies

A token issued for an account or application identity does not mean you can send under any arbitrary `From` address.

Example:

~~~text
SMTP authentication identity:
  notifications@example.com

From header:
  billing@example.com
~~~

If the provider has not granted Send As/alias permission for `billing@example.com`, the server may reject the message or rewrite the sender per policy.

Applications should:

- manage `From` via configuration or a sender profile allowlist;
- never let callers supply arbitrary addresses;
- verify that the mailbox/alias/domain is authorized by the provider;
- distinguish SMTP envelope sender, From, and Reply-To;
- evaluate SPF, DKIM, and DMARC to strengthen domain authentication on receipt;
- not expect OAuth to replace anti-spoofing email policies.

### 13.1. A token for one mailbox does not grant access to another

In multi-tenant systems:

~~~text
Tenant A -> mailbox A -> OAuth identity A
Tenant B -> mailbox B -> OAuth identity B
~~~

Isolate token stores, client configurations, recipient data, logs, and rate limits per tenant. Never mistakenly use token A to authenticate mailbox B, even on the same SMTP host.

## 14. Common errors and how to diagnose them

An SMTP server may return authentication errors such as:

~~~text
535 5.7.x Authentication unsuccessful
530 5.7.x Authentication required
454 4.7.x Temporary authentication failure
~~~

These are examples, not identical detailed code sets across all providers.

### 14.1. Diagnostic table

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `535 Authentication unsuccessful` | Wrong token audience, expired, missing scope, wrong mailbox or policy | Issuer, scope, token expiry, identity, SMTP AUTH policy |
| Server does not advertise XOAUTH2 | Endpoint or provider does not support it | `EHLO` after TLS, provider documentation |
| `530 Must issue STARTTLS first` | TLS not established yet | Port, STARTTLS required, truststore |
| Token endpoint returns unauthorized/invalid client | Wrong client credential or registration | Client ID/secret/cert, token endpoint |
| `invalid_grant` on refresh | Expired refresh token, revoked consent, clock policy | Authorization flow, token store, re-authorization needed |
| Authentication succeeds, but `MAIL FROM` / `DATA` rejected | Sender permissions, domain policy, quota | From/Send As/alias, SMTP policy |
| Works initially, then fails later | Access token expired | Refresh/cache/expiry safety window |
| One tenant sends, another tenant fails | Different tenant/mailbox policy or permissions | Scope, tenant ID, SMTP AUTH state |
| SMTP timeout | Network, firewall, provider latency | DNS, port, timeouts, TLS handshake |
| Mail accepted, but does not reach Inbox | Delivery/spam/bounce is a later stage | Provider events, SPF/DKIM/DMARC |

Do not catch every `MailException` and return an “OAuth token expired” message. An SMTP send failure may involve recipients, message size, quotas, network, or provider policies unrelated to the access token.

### 14.2. Spring Mail exceptions

In Spring Mail, exceptions commonly distinguished include:

- `MailAuthenticationException`: authentication issues represented by Spring Mail.
- `MailSendException`: message submission/transport failures, potentially with per-message errors.
- `MailPreparationException`: message preparation errors at the Spring layer.
- `MailException`: base class.

At the Jakarta Mail/provider layer, exceptions may be wrapped in `getCause()` or the `MessagingException.getNextException()` chain. When diagnosing, inspect both the failing stage and provider code rather than relying solely on message text.

### 14.3. Token expiring mid-send

A token might be valid when retrieved yet no longer valid when SMTP authentication starts. An appropriate approach is:

1. Use a cache with a safety margin.
2. Identify authentication failures that definitely occurred **before the message was accepted**.
3. If confirmed as an authentication failure, you may invalidate the token and re-acquire one per policy.
4. Avoid blindly retrying the entire email if the error happened **after `DATA`** and the outcome is uncertain.

This is where SMTP security, idempotency, and retries intersect. **Token refreshes can be repeated**, whereas **SMTP submission is not inherently idempotent**.

## 15. Do not enable debugging that leaks bearer tokens

SMTP debugging is helpful when investigating connectivity, yet it can expose:

- AUTH commands and base64 credentials;
- access tokens;
- email addresses and headers;
- message data depending on debug level;
- server responses containing tenant/account info.

Do not use:

~~~properties
mail.debug=true
~~~

in production without controlled redaction, access restrictions, and retention. When needed, enable minimal logging in a test environment or a controlled diagnostic session, and verify whether the provider/library actually masks AUTH contents.

Safe application-level log example:

~~~text
event=smtp_auth_attempt
provider=exchange-online
mailboxProfile=billing
tokenSource=oauth2
tokenExpiresSoon=false
result=FAILED
errorClass=MailAuthenticationException
correlationId=mail-job-752
~~~

Never log:

~~~text
accessToken=eyJ...
refreshToken=...
clientSecret=...
Authorization: Bearer ...
AUTH XOAUTH2 <base64-payload>
~~~

**Base64 is not security encryption.** Base64-encoded AUTH strings can still be decoded to recover the bearer token.

## 16. Secret management and access control

An OAuth SMTP system may need to protect:

- client secrets or private keys used to request tokens;
- user refresh tokens;
- active access tokens;
- service account credentials or federation configuration;
- lists of mailbox/application permissions.

Useful practices:

1. Use a secret manager or workload identity mechanism instead of hard-coding credentials in the repository.
2. Grant only necessary permissions per app/tenant/mailbox.
3. Restrict read access to token stores and runtime environments.
4. Never emit tokens in API responses, error messages, or logs.
5. Establish rotation, revocation, and incident response procedures for leaked tokens.
6. Monitor app consent, Send As permissions, and SMTP policy changes.
7. Separate production sending accounts from test accounts.
8. Enforce mandatory TLS and certificate verification.
9. Purge/limit expired token data per appropriate retention policies.
10. Rate-limit email sending to curb damage if an application or sending identity is abused.

If an access token leaks, short lifetimes help limit the abuse window. However, a leaked refresh token or private key can allow minting new tokens; those credentials require even stricter protection.

## 17. When should you use an email-sending API instead of SMTP?

Not every provider offers the same SMTP OAuth capabilities. Some transactional email services prioritize **HTTP APIs**:

~~~text
Spring application
   |
   | HTTPS request
   | OAuth bearer / API key / request signing
   v
Email provider API
   |
   +--> Tracking / provider ID
   +--> Webhook delivery / bounce
   +--> Rate limiting / templates
~~~

### 17.1. Comparing SMTP and HTTP APIs

| Criterion | SMTP + OAuth XOAUTH2 | HTTP email API |
| --- | --- | --- |
| Protocol | SMTP submission | HTTPS/REST or provider protocol |
| Credential | OAuth access token in SMTP AUTH | OAuth token, API key, IAM signing, or custom mechanism |
| Spring integration | `JavaMailSender` / Jakarta Mail | HTTP client or provider SDK |
| Format | MIME message | JSON payload or raw MIME depending on API |
| Tracking | Often needs provider-specific integration | Many providers return message ID, status/webhooks |
| Idempotency | Plain SMTP lacks a universal guarantee | May support idempotency keys depending on provider |
| Port/network | SMTP ports such as 587/465 | Usually HTTPS 443 |
| Sending permission | SMTP AUTH policy/mailbox permissions | API permissions/provider-specific policies |
| Provider portability | MIME/SMTP is highly standardized | Custom APIs may require new adapters |

HTTP APIs do not always use OAuth. For example:

- Some transactional email services use dedicated API keys.
- Some cloud services use request signing with IAM/workload credentials.
- Some APIs use OAuth delegated/application permissions.

**Do not label every API key as an OAuth token.** These mechanisms differ in authorization, rotation, and security properties.

### 17.2. Architecture for swapping transports

If you want to switch between SMTP and HTTP APIs:

~~~text
Business service
     |
     v
MailService interface
     |
     +-- SmtpOAuthMailAdapter
     |
     +-- ProviderHttpMailAdapter
     |
     +-- FakeMailAdapter for tests
~~~

The contract might look like:

~~~java
public interface MailService {
    MailSubmissionResult submit(OutgoingMail request);
}

public record MailSubmissionResult(
        String localJobId,
        String providerMessageId,
        SubmissionStatus status) {
}

public enum SubmissionStatus {
    SUBMITTED,
    ACCEPTED_FOR_PROCESSING
}
~~~

Statuses must be defined according to the actual provider. An HTTP API returning `202 Accepted` may only confirm that the job was queued, **not** that the message reached the Inbox. Similarly, SMTP `250` after `DATA` is submission acceptance, not final delivery.

### 17.3. Why can managed identity fit an API better?

A cloud sending API may support workload identity or direct request signing. That avoids storing refresh tokens/user passwords inside the application. Still, do not assume the exact same managed identity can authenticate SMTP XOAUTH2: the SMTP server must accept tokens for the proper resource and flow.

Choose the channel based on business needs, provider support, permission models, and operational capabilities rather than trying to force an API token into SMTP.

## 18. Plan for migrating from password to OAuth2

When a system currently uses `spring.mail.username/password` and the provider mandates modern authentication, migrate step-by-step:

1. **Inventory:** identify all services, batch workers, schedulers, and active SMTP accounts.
2. **Check provider policies:** SMTP AUTH, XOAUTH2, grant flows, scopes, sender permissions.
3. **Register applications:** OAuth clients/service principals or identity methods required by the provider.
4. **Grant least privilege:** only the necessary mailboxes/tenants/domains.
5. **Implement the token provider:** acquisition, caching, refresh, and token endpoint error handling.
6. **Switch SMTP mechanism:** select `XOAUTH2`, configure TLS and hostname verification.
7. **Controlled testing:** use test mailboxes, never production recipients.
8. **Observe:** separate error rates for token acquisition, SMTP authentication, and email submission.
9. **Phased rollout:** canary or per-mailbox/tenant rollout with a rollback plan.
10. **Revoke legacy credentials:** once the new sending path is verified and no legacy consumers remain.

### 18.1. Avoid a “replace password with static token” rollout

Avoid doing this:

~~~yaml
spring:
  mail:
    password: eyJ... # Manually copied access token
~~~

This is not a complete migration. The token can expire and end up in source/config backups. Automated token lifecycle management and secure storage are required.

### 18.2. Ensure rollback does not downgrade security

When a migration fails, unsuitable rollback actions include:

- disabling TLS;
- enabling trust-all certificates;
- re-enabling Basic Authentication across the entire tenant;
- logging tokens;
- using a broadly privileged admin account across all applications.

Rollback must return to an organization-approved, controlled alternative; if the provider has already disabled basic auth, fix the token/provider configuration or safely pause sending rather than bypassing policy.

## 19. Testing OAuth2 SMTP

Test **token acquisition**, **SMTP mechanism selection**, and **email submission** separately.

### 19.1. Unit tests for the token provider

Scenarios:

- valid token: uses cache;
- expiring token: fetches a new token;
- token endpoint times out: does not return an expired token;
- client revoked: fails per contract;
- two threads request a token simultaneously: no refresh storm;
- two mailboxes in different tenants: do not share wrong-scope tokens;
- refresh token rotation: persists updated credential per provider mechanism.

With Spring Security's manager, you can mock `OAuth2AuthorizedClientManager` to return a fake authorized client. No real identity provider calls are needed in unit tests.

### 19.2. Unit tests for the mail adapter

With `OAuth2SmtpMailService`, separate the sender factory or SMTP adapter to test:

- `auth.mechanisms` includes only `XOAUTH2` when required;
- host, port, and TLS mode are right;
- token is retrieved close to connection time;
- sender does not swap passwords across mailboxes;
- token acquisition failures are not recorded as delivery failures;
- adapter constructs messages with valid From/To/Subject;
- access tokens are never logged.

These tests verify configuration and contracts, **not that the provider actually accepts the token**.

### 19.3. Integration tests

An SMTP test server can verify MIME, TLS, and AUTH invocation. However, not every SMTP mock supports XOAUTH2 or validates real tokens.

Separate your tests into:

1. Mock SMTP tests verifying message formatting, retries, and exception mapping.
2. Mock identity/token tests verifying grants/refreshes.
3. Controlled integration tests against a provider sandbox/test tenant verifying OAuth + SMTP end-to-end.

### 19.4. Diagnostic cases to cover

| Case | Expectation |
| --- | --- |
| Valid token, right permissions | SMTP AUTH succeeds, can submit |
| Expired token | Provider rejects auth; token source refreshes |
| Valid signature, wrong audience | Do not use this token for SMTP AUTH |
| Missing SMTP send permission | Report permission error; do not retry endlessly like a network error |
| SMTP AUTH disabled on mailbox | Diagnose policy, do not tweak TLS |
| Invalid host certificate | Reject connection |
| Server lacks STARTTLS while client requires it | Reject connection safely |
| Server lacks XOAUTH2 | Do not silently fall back to password |
| Client credentials unsupported by provider | Report flow error, choose delegated or suitable API |
| Token endpoint 429/5xx | Retry token acquisition within limits |
| SMTP timeout after DATA | Keep UNKNOWN status if submission outcome is unclear |
| High multi-thread/multi-mailbox load | No mixed tokens, rate limits enforced |

Never run tests that intentionally leak credentials or send real emails to out-of-scope recipients.

## 20. Common mistakes

| Mistake | Consequence | Remediation |
| --- | --- | --- |
| Placing static access token in `spring.mail.password` | Expires, sending fails after a while | Token provider with refresh/cache |
| Using refresh token as SMTP password | Authentication fails | Exchange refresh token for an access token for the right resource |
| Using Graph/API token for SMTP sending | Wrong audience/scope | Request a token for the SMTP resource |
| Selecting `LOGIN`/`PLAIN` while passing an OAuth token | Server interprets token as plain password | Enable `XOAUTH2` per provider |
| Enabling XOAUTH2 when SMTP server lacks support | Authentication does not work | Check EHLO/docs/provider |
| Assuming client credentials always supports SMTP | Cannot obtain right-permission token | Confirm provider-supported grant flows |
| Using mailbox A with a token issued for B | Wrong identity/permissions | Bind mailbox, token, and From |
| Using a singleton sender and `setPassword` per thread | Race/mixed tokens across accounts | Sender per call or adapter isolating tokens per connection |
| Disabling STARTTLS or hostname verification to “fix” errors | Can expose bearer tokens | Mandatory TLS, fix truststore/certs properly |
| Logging AUTH XOAUTH2 base64 | Token exposed | Redact and restrict protocol debug |
| Storing refresh tokens in repositories | Long-lived credential risk | Secret manager/secure authorized client store |
| Retrying email immediately after any auth/transport exception | Can send duplicates after DATA timeout | Classify stage, use idempotency |
| Allowing arbitrary From from API | Can spoof senders | Allowlist sender profiles/Send As |
| Treating OAuth as replacing SPF/DKIM/DMARC | Delivery/reputation not guaranteed | Configure domain authentication separately |
| Treating SMTP accepted as Delivered | Misreports Inbox delivery | Provider events/DSN/webhooks |
| Treating every HTTP sending API as OAuth | Wrong secret/permission design | Distinguish API keys, IAM, OAuth |

## 21. End-to-end example: invoice sending service

Suppose an application sends PDF invoices from mailbox `billing@example.com`. Because the provider mandates OAuth2 SMTP, the system consists of:

~~~text
OrderApplicationService
  |
  +-- commit invoice
  |
  +-- store mail outbox job
            |
            v
      MailWorker
            |
            v
  OAuth2SmtpMailService
            |
            +-- SmtpAccessTokenProvider
            |       |
            |       +-- token cache / expiry check
            |       +-- identity provider
            |
            +-- JavaMailSenderImpl
                    |
                    +-- TLS
                    +-- AUTH XOAUTH2
                    +-- MAIL FROM / RCPT TO / DATA
                    |
                    v
                 SMTP server
~~~

Sequence:

1. Business logic creates the invoice and an outbox job with a stable message key.
2. The worker claims the job and prepares the MIME message (plain text/HTML, PDF).
3. The token provider obtains a valid access token for the identity permitted to send from the billing mailbox.
4. The mail adapter opens TLS, verifies the certificate, and authenticates using XOAUTH2.
5. The SMTP server accepts the message or returns an error.
6. If submission succeeds without error, the worker marks `SUBMITTED`; it does not mark `DELIVERED`.
7. If token acquisition or auth is rejected, the worker classifies the error before deciding on retries.
8. If SMTP times out with an unclear outcome, the worker applies idempotency policy and `UNKNOWN` status.
9. When the provider delivers bounce/delivery events, the system updates delivery state separately.

The key takeaway is that **OAuth authentication** and **email delivery flow reliability** are two independent yet related concerns. OAuth ensures the application uses valid credentials/permissions; the outbox, retries, and tracking ensure send requests are managed durably.

### 21.1. When SMTP is not needed

If the provider offers an HTTPS invoice-sending API with suitable sending permissions, the workflow can swap `OAuth2SmtpMailService` for `ProviderHttpMailAdapter`. Outbox job creation, message keys, rendering, and business states can stay unchanged. Separating the contract from the transport lets the application switch without altering invoice business logic.

## 22. Production deployment checklist

1. **Provider support:** are SMTP AUTH and XOAUTH2 supported for this account/tenant type?
2. **Grant flow:** is delegated, app-only, or service account permitted?
3. **Scope/audience:** which SMTP resource is the access token actually targeting?
4. **Mailbox authorization:** does the identity/token have permission to send from the mailbox/alias?
5. **TLS:** required STARTTLS or implicit TLS on the right endpoint, with certificate verification.
6. **Client config:** `mail.smtp.auth.mechanisms=XOAUTH2` and no silent fallback to passwords.
7. **Token lifecycle:** caching, refresh, safety window, revocation, and handling refresh failures.
8. **Concurrency:** never mutate credentials on a sender shared across threads/tenants.
9. **Secret storage:** never hard-code tokens, client secrets, or refresh tokens.
10. **Logging:** never log access tokens, AUTH payloads, or raw SMTP authentication traces.
11. **Error mapping:** distinguish token endpoint, SMTP AUTH, sender policy, and submission failures.
12. **Retries:** never automatically resend the whole email after timeouts with indeterminate outcomes.
13. **Observability:** monitor auth failures, token refreshes, SMTP latency, and submission status.
14. **Tests:** test token lifecycle and SMTP XOAUTH2 on a controlled tenant/sandbox.
15. **Provider lifecycle:** monitor policy/API changes and prepare a migration path to HTTP APIs.

## 23. Key points to remember

- **OAuth 2.0** issues access tokens bound to identities and permissions; **SMTP XOAUTH2** is how SMTP uses tokens to authenticate.
- An access token used in `AUTH XOAUTH2` is neither a mailbox password nor a refresh token.
- The SMTP provider must support XOAUTH2, and the token must carry the right audience, scope, and mailbox permissions.
- In Spring Mail, you can set `mail.smtp.auth.mechanisms=XOAUTH2` and pass the access token in the credential position of `JavaMailSenderImpl`.
- Access tokens expire, so a token provider must refresh them according to real lifecycle needs; never place static tokens in configuration.
- Never mutate passwords/tokens on a singleton sender shared across threads or tenants.
- TLS and certificate verification remain essential to protect bearer tokens.
- Providers have different flows and permissions; never copy tokens or scopes across Gmail, Exchange Online, and other APIs.
- HTTP APIs using OAuth, API keys, or IAM signing may be a better choice than SMTP depending on requirements.
- Successful sending via SMTP only confirms submission acceptance; it does not guarantee Inbox delivery.

In Spring Framework Mail, properly implementing “OAuth2 SMTP” is more than replacing a password string with a token. The application must **acquire tokens with the right permissions, refresh tokens safely, choose the appropriate SMTP AUTH mechanism, protect the connection with TLS, and handle send outcomes independently of authentication errors**. Separating these responsibilities clearly lets the system adapt to modern provider security policies while keeping the email-sending pipeline operable and controllable.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `JavaMailSenderImpl`, and `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** `spring.mail.*` and custom mail configuration.
- **Jakarta Mail / Angus Mail SMTP provider documentation:** `mail.smtp.auth.mechanisms`, `XOAUTH2`, TLS, STARTTLS, and SMTP properties.
- **Spring Security Reference — OAuth 2.0 Client:** `OAuth2AuthorizedClientManager`, client registration, and authorized client lifecycle.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** authorization grants and access tokens.
- **RFC 6750 — Bearer Token Usage:** bearer tokens and credential protection requirements.
- **RFC 7628 — A Set of Simple Authentication and Security Layer (SASL) Mechanisms for OAuth:** OAuth SASL mechanisms and client protocol relationship.
- **RFC 3207 — SMTP Service Extension for Secure SMTP over TLS:** STARTTLS.
- **RFC 4954 — SMTP Service Extension for Authentication:** SMTP AUTH.
- **Google Workspace/Gmail official documentation — OAuth 2.0 for mail protocols:** XOAUTH2, scopes, and authorization policies.
- **Microsoft Learn — Authenticate an IMAP, POP or SMTP connection using OAuth:** permissions, SMTP AUTH policies, and delegated/app-only scenarios.
