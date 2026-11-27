# MFA, Password Policies, and Protecting Authentication Flows

> **Chapter:** Application Identity with Cognito  
> **Module:** CLOUD_PROVIDERS_AWS — explore AWS across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; practice selecting services, deploying secure applications, monitoring, recovery, and cost control.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Cognito User Pools**, **Identity Pools**, app clients, IAM, managed login, and external IdPs in an authentication architecture.
2. Design **OFF / OPTIONAL / ON** MFA configurations aligned with product requirements and onboarding flows.
3. Explain **TOTP, SMS MFA, and email MFA**, as well as the differences between MFA, passwordless OTP, and passkeys.
4. Build **password policies**, password reuse prevention, temporary password limits, and secure account recovery.
5. Understand Cognito challenge flows, OAuth/OIDC token/session lifecycles, and MFA management APIs.
6. Evaluate **threat protection, adaptive authentication, compromised credentials**, and **AWS WAF**.
7. Protect Java APIs by verifying JWTs, `token_use`, `client_id`, scopes, and business permissions.
8. Monitor sign-in errors, create operational runbooks, and estimate Cognito/SMS/SES/WAF costs.

## 1. Why Passwords Alone Are Not Enough to Protect Applications

Username/password sign-in is familiar to customers, yet carries major risks:

- Users **reuse passwords** leaked from other websites.
- Attackers test leaked email/password lists via **credential stuffing**.
- **Phishing** steals passwords and even OTP codes when users enter them on spoofed pages.
- Insecure **password resets** can become an account takeover vector.
- Users losing an MFA device, SIM, or email risk locking themselves out if recovery is poorly designed.
- Access/refresh tokens can be stolen **after** a valid MFA session.

**Multi-factor authentication (MFA)** adds authentication proof, but does not replace API authorization, token protection, bot mitigation, or secure password reset controls.

~~~mermaid
flowchart TB
    U["User"] --> APP["Web / Mobile App"]
    APP --> COG["Amazon Cognito User Pool"]
    COG --> A["First factor: password / compatible flow"]
    A --> Q{"MFA required?"}
    Q -->|"Yes"| M["TOTP / SMS / Email challenge"]
    Q -->|"No"| T["Issue tokens after authentication"]
    M -->|"Success"| T
    M -->|"Wrong/expired"| FAIL["Deny or rate-limited retry"]
    T --> API["Java Backend / API Gateway"]
    API --> V["Verify JWT, scope, object permissions"]
    V --> DATA[("RDS / DynamoDB / S3")]
~~~

This is the basic **local password + MFA** flow. With **passkeys/WebAuthn** or a **federated IdP**, authentication steps are structured differently.

## 2. User Pool, Identity Pool, App Client, and IAM

| Component | Responsibility | Example |
| --- | --- | --- |
| **Cognito User Pool** | Application user accounts, sign-up, sign-in, MFA, password policies, OIDC/OAuth tokens. | Customers of an e-commerce website. |
| **Cognito app client** | Auth flow config, callback URLs, OAuth scopes, token validity, client secret where appropriate. | An SPA, a mobile app, a server-side app. |
| **Cognito managed login** | Sign-in UI hosted and provided by Cognito. | AWS-managed login and MFA pages. |
| **Cognito Identity Pool** | Issues **temporary AWS credentials** via IAM roles when apps need to call AWS APIs directly. | Mobile app uploading directly to S3 under scoped permissions. |
| **AWS IAM** | Administrative permissions and workload permissions to call AWS APIs. | ECS task role accessing DynamoDB. |
| **External IdP** | Sign-in handled by Entra ID, Okta, social providers, SAML/OIDC. | Employees signing in with corporate identity. |

**A User Pool access token is not an AWS access key.** Cognito authenticates the user and issues JWTs, while the backend API must verify tokens and enforce business authorization. The backend's IAM role governs AWS resource permissions.

### 2.1. Special Considerations for Federated Users

MFA in Cognito User Pools primarily applies to **local users**. For federated SAML/OIDC users, password and MFA checks happen at the **upstream IdP**. Cognito does not automatically insert a local TOTP/SMS step after federated sign-in the way local User Pool MFA works.

Therefore, enabling required MFA in Cognito does not replace Conditional Access/MFA in Entra ID or Okta.

### 2.2. Public Clients and Confidential Clients

- **SPA/mobile** are public clients: never embed a **client secret** in JavaScript or mobile packages; prefer **Authorization Code + PKCE** with OAuth.
- **Server-side web/BFF** can keep a secret when genuinely needed and backed by secure server-side secret storage.
- **M2M client credentials** represent a workload, not a human user, and do not go through user MFA.

## 3. Cognito's Three MFA States

Cognito User Pool uses **MfaConfiguration**:

| API Value | Effect | Notes |
| --- | --- | --- |
| **OFF** | Does not require user-pool MFA. | Can pair with passwordless/passkeys per custom design. |
| **OPTIONAL** | Users may enroll/enable MFA; enrolled users can be challenged. | Managed login does not automatically prompt every user to enroll; the app needs UX. |
| **ON** | Users on local password-based flows must complete MFA per supported rules. | Must have onboarding and recovery ready before enabling. |

Required MFA strengthens security, yet can **lock out users lacking a factor** or unfinished onboarding. To roll it out safely:

1. Inventory active app clients and auth flows.
2. Configure supported TOTP/SMS/email factors.
3. Test new accounts, existing accounts, and users with unverified attributes.
4. Build enrollment screens and guidance for users without a device.
5. Prepare an independent recovery channel.
6. Track failure rates and maintain a rollback procedure.

### 3.1. Optional MFA and Adaptive Authentication

Per Cognito guidance, **risk-based adaptive MFA** uses **MFA = OPTIONAL** paired with **threat protection**. When risk rises, Cognito can prompt for MFA per configured actions; mandating MFA pool-wide and triggering MFA by risk are distinct goals.

### 3.2. User MFA Preference

A user may have multiple available methods with one **enabled/preferred method**. How Cognito challenges depends on pool settings, user attributes, auth flow, and user preference. Enabling TOTP, SMS, and email does not mean the user must enter three codes every time.

Custom apps can let users update MFA preferences via **SetUserMFAPreference** with a valid access token. Admins use **AdminSetUserMFAPreference** with IAM credentials and auditing.

## 4. TOTP, SMS MFA, and Email MFA

| Method | Concept | Pros | Risks |
| --- | --- | --- | --- |
| **TOTP** | Authenticator app generates time-based codes from a secret. | No need to send SMS/email each sign-in. | Device loss, clock skew, code phishing. |
| **SMS MFA** | Sends code via phone number. | Accessible to broad users. | SIM swap, SMS delays, roaming, messaging fees. |
| **Email MFA** | Sends code to mailbox. | Easy UX for users already using email. | Email compromise, deliverability, SES/plan dependency. |
| **Passkey with user verification** | WebAuthn key-based auth with on-authenticator user verification. | Stronger phishing resistance than OTPs when properly configured. | Browser/device support and recovery workflows. |

### 4.1. TOTP

General steps:

1. User signs in up to the enrollment point.
2. App calls **AssociateSoftwareToken** to obtain a setup secret.
3. Display a QR code or manual entry secret inside a secure UI.
4. User enters a code generated by their authenticator app.
5. App calls **VerifySoftwareToken**.
6. When needed, complete the `MFA_SETUP` challenge via **RespondToAuthChallenge** and set MFA preference.

**Never log TOTP secrets, OTP codes, or challenge sessions.** Never expose provisioning QR codes publicly or share them in support tickets.

### 4.2. SMS MFA

SMS messages route through Cognito-supported channels such as Amazon SNS or **AWS End User Messaging SMS**, depending on pool configuration. Verify:

- Sender/origination identity and per-country registration rules.
- SMS sandbox limits and allowlisted test numbers.
- Phone numbers formatted in international **E.164** format.
- Delivery latency, carriers, retries, and quotas.
- Per-destination SMS charges and anti-abuse controls to prevent cost spikes.

If SMS arrives slowly, never immediately disable MFA or skip the challenge. The app must allow bounded retries and display fallback/recovery instructions.

### 4.3. Email MFA

**Email MFA requires Cognito Essentials or Plus and customer-configured Amazon SES resources**. Verify SES sender identity, domain verification, quotas, Region, and email delivery logs. Lower tiers do not include this capability by default.

Do not confuse **email MFA** (email as a second factor after a password) with **passwordless email OTP** (email as the first factor).

### 4.4. MFA and Phishing

TOTP/SMS/email OTPs still carry the risk of users entering codes into spoofed sites. For high-risk scenarios, evaluate **WebAuthn/passkeys with user verification**, as origin binding improves phishing resistance. However, understand Cognito's WebAuthn constraint: passkeys are not used as a second factor after a password under current Cognito mechanisms.

## 5. TOTP Challenge Flow and APIs

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Application
    participant C as Cognito
    participant T as Authenticator
    U->>A: Username + password
    A->>C: InitiateAuth
    C-->>A: MFA_SETUP / corresponding challenge
    A->>C: AssociateSoftwareToken
    C-->>A: SecretCode
    A-->>U: Display secret / QR securely
    U->>T: Add account
    T-->>U: TOTP code
    U->>A: Enter code
    A->>C: VerifySoftwareToken
    C-->>A: SUCCESS / Session
    A->>C: RespondToAuthChallenge if required by flow
    C-->>A: AuthenticationResult upon completion
~~~

### 5.1. Distinguishing the APIs

| API | Role |
| --- | --- |
| **InitiateAuth / AdminInitiateAuth** | Starts authentication; returns tokens or ChallengeName + Session. |
| **RespondToAuthChallenge / AdminRespondToAuthChallenge** | Responds to SMS/TOTP/email/password challenges. |
| **AssociateSoftwareToken** | Registers a TOTP secret; does not complete setup by itself. |
| **VerifySoftwareToken** | Verifies the enrolled TOTP code. |
| **SetUserMFAPreference** | User manages preferred factor via access token. |
| **AdminSetUserMFAPreference** | Admin updates MFA preferences via IAM credentials. |
| **GetUser / AdminGetUser** | Reads user info under the appropriate permission model. |

Illustrative response:

~~~json
{
  "ChallengeName": "SOFTWARE_TOKEN_MFA",
  "Session": "EXAMPLE_TEMPORARY_SESSION",
  "ChallengeParameters": {
    "USER_ID_FOR_SRP": "example-user"
  }
}
~~~

This is **mock data**, containing no real credentials. The app must read the **ChallengeName** returned by Cognito—never assume it is always `SOFTWARE_TOKEN_MFA`.

Other challenge names you may encounter: **SMS_MFA**, **EMAIL_OTP**, **MFA_SETUP**, **SELECT_MFA_TYPE**, **NEW_PASSWORD_REQUIRED**. Depending on flow and feature, challenge names and response parameters vary; check SDK/Cognito documentation at implementation time.

### 5.2. Strictly Separate "Challenge Pending" from "Sign-In Succeeded"

If `InitiateAuth` returns `ChallengeName`/`Session` **without an `AuthenticationResult`**, never create an app session or treat the user as authenticated. Only after the challenge finishes and valid tokens are issued may the backend evaluate authorization.

### 5.3. Common Errors

- Expired TOTP code or phone clock drift.
- User enrolled a different device or lost the secret.
- Auth challenge `Session` expired.
- Too many wrong OTP attempts hitting Cognito rate limits.
- User lacks a verified attribute required for that factor.
- Pool requires MFA, yet app client lacks an `MFA_SETUP` screen.

Never build an "auto-bypass MFA after three failures" shortcut for support convenience. Use an admin-assisted recovery workflow with identity verification.

## 6. MFA vs. Passwordless OTP and Passkeys

| Sign-In Type | First Factor | Additional Factor | Key Difference |
| --- | --- | --- | --- |
| Password + TOTP | Password | TOTP app | Two independent factors. |
| Password + SMS/email MFA | Password | SMS/email OTP | Message-channel MFA. |
| Passwordless email OTP | Email OTP | Not necessarily another factor | OTP is the **first factor**. |
| Passwordless SMS OTP | SMS OTP | Not necessarily another factor | Does not become MFA merely by sending a code. |
| Passkey/WebAuthn | Authenticator + user verification per config | Not password + second passkey | Can satisfy MFA in a single step where supported. |

### 6.1. Compatibility with Required MFA

Per current AWS documentation, you cannot set **MFA required** in a pool that permits **EMAIL_OTP or SMS_OTP** as passwordless first auth factors. When MFA is required, choice-based sign-in is restricted to compatible password factors, **with the exception of WebAuthn configured for MFA via user verification**.

### 6.2. WebAuthn/Passkeys Can Satisfy MFA Under Newer Configurations

With **WebAuthnConfiguration.FactorConfiguration = MULTI_FACTOR_WITH_USER_VERIFICATION**, a passkey with user verification can satisfy multi-factor requirements at **first-factor** in supported scenarios. Passkeys are **not** used as a second challenge after password sign-in in Cognito.

Items to test: Essentials/Plus feature plans, app clients, browser/OS support, user verification, relying party domain, device-loss recovery, and required/optional states.

### 6.3. Never Configure One Factor as Both

If a user only has an email and the app uses passwordless email OTP, trying to also use email as a second MFA factor **does not provide two independent factors**. Cognito blocks incompatible MFA/first-factor combinations; design a clear model from the start.

## 7. User Pool Password Policies

Common properties of **Policies.PasswordPolicy**:

- **MinimumLength**.
- **RequireUppercase**, **RequireLowercase**.
- **RequireNumbers**, **RequireSymbols**.
- **TemporaryPasswordValidityDays**.
- **PasswordHistorySize** when supported by plan.

~~~json
{
  "Policies": {
    "PasswordPolicy": {
      "MinimumLength": 14,
      "RequireUppercase": true,
      "RequireLowercase": true,
      "RequireNumbers": true,
      "RequireSymbols": true,
      "TemporaryPasswordValidityDays": 7,
      "PasswordHistorySize": 10
    }
  }
}
~~~

This is an **illustrative configuration fragment**, not a complete API request payload.

### 7.1. Strong Password Policy Goes Beyond Special Characters

A long password reused across many services remains high-risk. Recommendations:

1. Encourage long, unique passphrases and password managers.
2. Allow paste and autofill in sign-in forms.
3. Pair with MFA proportional to risk.
4. Avoid messages revealing user existence during reset/login.
5. Never log passwords or transmit them over plaintext HTTP.
6. On the **Plus** plan, evaluate compromised-credentials detection where supported by auth flows.

### 7.2. Password History

**Essentials/Plus** supports password reuse prevention, currently capable of blocking reuse of the current password and up to 23 prior passwords (up to 24 total per docs). Never confuse reuse-prevention history with checking passwords leaked on the Internet; they are distinct controls.

### 7.3. Temporary Passwords

**TemporaryPasswordValidityDays** applies to admin-set temporary passwords, typically tied to **AdminCreateUser** and the **NEW_PASSWORD_REQUIRED** challenge.

Temporary password expiration does not cause users' permanent passwords to expire periodically on the same schedule. Support may need to issue/reset a temporary password through authorized admin workflows.

### 7.4. Federated Users

Users authenticated at an upstream IdP do not have Cognito's password policy enforced against their IdP password. Manage their password/MFA policies at the IdP and configure federation trust properly.

## 8. Account Recovery: Never Reuse the MFA Channel

This is a critical security and UX rule. **Cognito does not send self-service password reset codes to the same email or phone number a user uses as their preferred MFA channel.**

| Preferred MFA | Recommended Recovery Channel | Risk Scenario |
| --- | --- | --- |
| **SMS** | Verified email. | User registered only a phone, no email. |
| **Email** | Verified phone/SMS. | User registered only an email or lost phone access. |
| **TOTP** | Verified email/phone per design. | User lost both TOTP device and contact channel. |
| **Passkey** | Alternate credentials / custom-designed recovery. | Device lost or re-enrollment abused. |

### 8.1. AccountRecoverySetting

~~~json
{
  "AccountRecoverySetting": {
    "RecoveryMechanisms": [
      {
        "Name": "verified_email",
        "Priority": 1
      },
      {
        "Name": "verified_phone_number",
        "Priority": 2
      }
    ]
  }
}
~~~

**Priority 1** is highest. Cognito still selects an eligible channel based on MFA preferences and verified attributes; email is not guaranteed to be used for an account if email is currently its preferred MFA.

To allow admin-only resets:

~~~json
{
  "AccountRecoverySetting": {
    "RecoveryMechanisms": [
      {
        "Name": "admin_only",
        "Priority": 1
      }
    ]
  }
}
~~~

Never mix **admin_only** with self-service recovery channels.

### 8.2. Self-Service Password Reset

~~~mermaid
sequenceDiagram
    participant U as User
    participant APP as Application
    participant C as Cognito
    U->>APP: Forgot password
    APP->>C: ForgotPassword
    C-->>U: Send code via eligible recovery channel
    U->>APP: Code + new password
    APP->>C: ConfirmForgotPassword
    C-->>APP: Success / error
    APP-->>U: Sign in again
~~~

Do not assume every user has an eligible channel for self-service reset. **InvalidParameterException** can occur when no valid recovery channel exists. Support workflows must require real identity proofing rather than blindly trusting an email typed into a form.

### 8.3. Lost Phone: Admin-Assisted Recovery

1. Verify the account owner's identity via an organization-approved secure channel.
2. Check for signs of account takeover before modifying MFA.
3. Least-privilege IAM admin updates only necessary user attributes/MFA settings.
4. Log an audit trail of who changed what, why, and when.
5. Guide the user to enroll a new factor.
6. Revoke sessions/tokens if compromise is suspected.

**Never build a public API that disables MFA using only an easily hijacked email or SMS code.**

## 9. OAuth/OIDC and Cognito Tokens

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant APP as Web/BFF
    participant C as Cognito managed login
    participant API as Java backend
    B->>APP: Sign in
    APP-->>B: Redirect authorize + state + nonce + PKCE
    B->>C: Password/MFA or passkey as configured
    C-->>B: Authorization code to callback
    B->>APP: Callback code and state
    APP->>C: Token endpoint with code_verifier / client auth
    C-->>APP: Access/ID/Refresh tokens
    APP->>API: Bearer access token / protected session
    API-->>APP: Response after JWT + authorization
~~~

### 9.1. The Tokens

| Token | Purpose | Never Do This |
| --- | --- | --- |
| **ID token** | Carries OIDC user info, consumed by the right client. | Substitute for an access token as API authorization proof. |
| **Access token** | Accesses resources/APIs with valid scopes/claims. | Treat as permanent authorization or AWS IAM credentials. |
| **Refresh token** | Obtains fresh tokens while the session remains valid. | Put in URLs, frontend logs, analytics, or routine business API calls. |

Backends must verify **signature/JWKS, issuer, expiry, `token_use`**, app client binding (**`client_id`** or audience per token type), scopes/groups, and data/tenant permissions.

### 9.2. Authentication Response and Challenges

~~~json
{
  "ChallengeName": "SMS_MFA",
  "Session": "EXAMPLE_SESSION_NOT_REAL",
  "ChallengeParameters": {
    "CODE_DELIVERY_DELIVERY_MEDIUM": "SMS"
  }
}
~~~

When receiving **ChallengeName**, the app must complete the challenge. Absence of `AuthenticationResult` means the user has not completed sign-in.

A successful response returns:

~~~json
{
  "AuthenticationResult": {
    "AccessToken": "EXAMPLE_ACCESS_JWT",
    "IdToken": "EXAMPLE_ID_JWT",
    "RefreshToken": "EXAMPLE_REFRESH",
    "TokenType": "Bearer",
    "ExpiresIn": 3600
  }
}
~~~

Tokens in these examples are placeholders. Never put real tokens in articles, tickets, or CloudWatch logs.

### 9.3. OAuth Protections

- Use HTTPS and exact callback URL allowlists.
- Use **state** against CSRF/login swapping and **nonce** for OIDC where needed.
- Use **PKCE** for public clients.
- Never place a client secret in SPA/mobile code.
- Prevent open redirects; never accept uncontrolled wildcard callbacks.
- In browsers, prefer XSS-resistant token/session storage; BFFs can use HttpOnly/Secure/SameSite cookies with CSRF protection.
- Access tokens must carry proper scopes, and backends must enforce object-level authorization—not just Cognito groups.

## 10. Refresh Token Rotation, Revocation, and Logout

### 10.1. Refresh Token Rotation

~~~json
{
  "RefreshTokenRotation": {
    "Feature": "ENABLED",
    "RetryGracePeriodSeconds": 10
  }
}
~~~

This is an app client configuration fragment. When refresh token rotation is enabled:

- Each successful refresh can return a new refresh token.
- **`REFRESH_TOKEN_AUTH` is not used** on app clients with rotation enabled; use **GetTokensFromRefreshToken** or the OAuth token endpoint per supported flows.
- The new token retains only the **remaining lifetime** of the original refresh window, never extending indefinitely.
- Handle multi-tab races and retries cleanly while protecting tokens.
- A small grace period allows legitimate retries, yet introduces a brief reuse window if a token leaks.

### 10.2. Token Revocation

Cognito provides mechanisms such as **RevokeToken**, **GlobalSignOut**, **AdminUserGlobalSignOut**, or session management features depending on feature plan.

**Critical warning:** self-contained JWTs can still pass **signature + `exp`** checks in a custom backend even after revocation. Cognito APIs receiving the token may reject revoked tokens, but a Java resource server needs its own session/revocation controls if logout must take effect immediately across all APIs.

Managed login maintains its own Cognito session cookie. Signing out of APIs and clearing the managed login session cookie are two separate steps to coordinate; never assume revoking a refresh token automatically clears browser cookies across every IdP/hosted login.

## 11. Separating Authentication from Authorization

A user can authenticate properly and pass MFA yet still have **no permission to view someone else's order**.

- **Authentication:** who is the user, and did they complete sign-in requirements?
- **Authorization:** which resources/tenants may the user operate on?
- **IAM authorization:** which AWS services may the AWS workload/role invoke?
- **Data authorization:** does the RDS/DynamoDB record or S3 object belong to that user/tenant?

For example, **GET /orders/987** cannot check only **`cognito:groups = customer`**; it must confirm order 987 **belongs to the current user** or an authorized agent role.

~~~mermaid
flowchart LR
    TOK["Cognito access token"] --> JWT["Validate iss/exp/signature/token_use/client_id"]
    JWT --> SCOPE{"Sufficient scope?"}
    SCOPE -->|"No"| DENY["403 Forbidden"]
    SCOPE -->|"Yes"| OBJ{"Order belongs to tenant/user?"}
    OBJ -->|"No"| DENY
    OBJ -->|"Yes"| DB["Read data via backend IAM role"]
~~~

**Passing MFA does not let the backend skip authorization.** The IAM role on ECS/Lambda/EC2 lets code call DynamoDB, yet the application must still isolate every tenant's records.

## 12. Threat Protection, Adaptive Authentication, and Credential Risk

**Threat protection** (formerly known as advanced security features) is part of the **Cognito Plus feature plan**.

| Component | Goal | Scope |
| --- | --- | --- |
| **Compromised credentials** | Detects leaked/common passwords in Cognito-observed flows. | Depends on sign-in/reset flow; differs for SRP. |
| **Adaptive authentication** | Evaluates risk from IP, device, user agent, location, and other signals. | Local username/password/SRP/custom flows per support. |
| **User activity logs** | Investigates authentication events and risk assessments. | Must be enabled, exported, and governed appropriately. |
| **IP allow/block exceptions** | Controls selected traffic by IP/CIDR in full-function mode. | Has limitations around federated sign-in, refreshes, and risk logic. |

### 12.1. Compromised Credentials Does Not Work Identically Across Flows

- With **USER_PASSWORD_AUTH** and **ADMIN_USER_PASSWORD_AUTH**, Cognito receives the password and can evaluate compromised credentials per feature behavior.
- With **USER_SRP_AUTH**, Cognito does not receive the plaintext password directly, so compromised-credentials detection **cannot operate identically** to password auth at sign-in.
- With **federated sign-in**, the upstream IdP handles passwords/MFA.
- With **M2M client credentials**, there is no user password for this feature to evaluate.

Never enable the feature and claim all passwords across every auth flow are checked against breach lists.

### 12.2. Risk-Based Adaptive MFA

Cognito can apply **Allow/Audit, Require MFA, or Block** actions based on risk level and configuration. If an app uses **MFA OPTIONAL**, the system can require an additional factor as risk rises.

Reference flow:

~~~mermaid
flowchart LR
    SIGNIN["User sign-in"] --> SCORE["Threat protection risk scoring"]
    SCORE --> LOW["Low risk -> Allow/Audit"]
    SCORE --> MID["Medium risk -> MFA per policy"]
    SCORE --> HIGH["High risk -> Block/notification"]
    MID --> TOK["Tokens when challenge succeeds"]
    LOW --> TOK
~~~

This is an **illustrative policy**, not an AWS default. Actual risk responses and conditions depend on pool and app client settings.

### 12.3. Audit Before Enforcing

AWS recommends running in **Audit-only** mode first to gather metrics, observe false positives, and study real traffic; documentation suggests monitoring for roughly **two weeks** minimum before switching to full-function mode. Plan:

1. Enable Plus/threat protection in a test environment.
2. Turn on Audit mode and inspect sign-in risk logs.
3. Analyze shared IPs/NATs, VPNs, travel, and legitimate devices.
4. Design risk-response thresholds and notifications.
5. Test with consenting real accounts across varied network conditions.
6. Switch to Full-function with rollback, monitoring, and support readiness.

**Threat protection is not a DDoS rate limiter.** It scores individual requests; deploy AWS WAF/rate controls against bot floods.

## 13. AWS WAF, Bot Controls, and Anti-Enumeration

Cognito User Pools support integrating an **AWS WAF web ACL** for eligible endpoints/user pools. Rules can:

- Rate-limit requests per IP/IP range or WAF-supported key.
- Block known bad sources using IP sets or managed rules.
- Apply CAPTCHA/challenge/bot controls where features and flows support them.
- Log and analyze blocked requests.

| Attack Pattern | Appropriate Defense Layer |
| --- | --- |
| High-volume credential stuffing | WAF rate/bot rules, Cognito MFA, threat protection. |
| Leaked passwords | Plus compromised credentials, password reset, MFA. |
| Sign-ins from anomalous locations | Adaptive risk, MFA/challenge/alerts. |
| User enumeration | `PreventUserExistenceErrors` where supported and consistent UX messages. |
| Authenticated user reading wrong tenant | Java authorization and data access checks. |
| SMS/email OTP spamming | Throttling, WAF, messaging cost alerts, and OTP retry caps. |

Avoid overly aggressive rate limits on users sharing **carrier NATs or corporate proxies** to prevent false positives. Enabling WAF does not automatically stop every distributed attack; review metrics and tune rules continuously.

### 13.1. Never Disclose Account Existence

In login/reset flows, messages like "This email has never been registered" help attackers harvest valid usernames. Configure **`PreventUserExistenceErrors`** on the app client where supported and design generic messages (such as "If the details are valid, we will send instructions").

Still maintain legitimate customer support channels so generic errors do not leave real users stranded with typos.

## 14. Reference Architecture for Java/AWS Applications

~~~mermaid
flowchart TB
    U["Browser / Mobile App"] --> WAF["Cognito managed login + WAF"]
    WAF --> C["Cognito User Pool: password / MFA / risk"]
    C --> TOK["OIDC / OAuth tokens"]
    TOK --> API["API Gateway / ALB"]
    API --> JAVA["Spring Boot API or Java Lambda"]
    JAVA --> VALID["JWT signature + iss + token_use + client_id + scopes"]
    VALID --> AUTH["RBAC / ABAC / object-level authorization"]
    AUTH --> DB[("DynamoDB / RDS")]
    JAVA -.-> IAM["Task / Lambda execution IAM role"]
    C -.-> LOG["CloudTrail, risk logs, CloudWatch"]
~~~

**Separate three authorization layers:**

1. User Pool authenticates and issues tokens.
2. Backend verifies tokens and decides what the user may do.
3. Backend IAM role permits executing the underlying AWS actions.

### 14.1. Per-Environment App Clients

Separate **dev/staging/prod** with distinct callback URLs and domains, and never use real production users for OTP testing. If a process requires a shared user pool, strictly govern ownership, MFA rollouts, and IAM.

### 14.2. Protecting OTPs and Secrets

Never write to logs:

- Plaintext passwords, refresh tokens, or raw access/ID tokens.
- TOTP secrets or QR provisioning URIs.
- SMS/email OTP codes or authentication `Session` values.
- Client secrets or IAM access keys.
- Unnecessary user attribute values such as full phone numbers or emails.

Log **correlation ID, error type, redacted app client ID, auth flow, challenge type, duration, and status** per data classification so you can investigate without leaking credentials.

## 15. Risk-Tiered Policy Templates

| Account Tier | Password Policy | MFA | Threat / Risk | Recovery |
| --- | --- | --- | --- | --- |
| Everyday consumers | Strong password, encourage password managers. | OPTIONAL, support TOTP and accessible methods. | WAF + audit; Plus risk if budget/need justifies. | Verified email/phone distinct from MFA factor, or support. |
| Customer support staff | Corporate password and SSO policy. | Mandatory MFA at IdP or local User Pool per model. | Risk-based sign-in and auditing. | Helpdesk identity verification. |
| High-privilege admins | Strong policy and appropriately short session lifetimes. | Prefer phishing-resistant MFA/SSO where available. | Block risky sessions, high-sensitivity alerts. | Two-person admin verification when needed. |
| Machine-to-machine | No user passwords where unneeded. | No user MFA. | OAuth client credentials, secret rotation, scoped IAM/WAF. | Credential rotation/revocation. |

**No single configuration fits every system.** Balance security, accessibility, user constraints, cost, and support capacity.

## 16. Java Spring Boot: Verifying Access Tokens Properly

A Java API must never trust a JWT merely because it looks like three dot-separated segments. The API must verify the token came from the **expected Cognito User Pool**, check expiration, token type, app client, and permissions.

### 16.1. Why ID Tokens Must Not Substitute for Access Tokens

Cognito User Pools issue ID tokens and access tokens for distinct purposes:

- **ID token:** confirms user identity to the client app; typically carries **`aud`** pointing to the app client.
- **Access token:** authorizes access to resources/APIs; in common Cognito flows carries **`token_use = access`**, **`client_id`**, and scopes.
- **Refresh token:** requests new tokens; never send to protected APIs as a bearer access token.

Common bug: a Java backend checks only the JWT signature without checking `token_use`, inadvertently accepting both ID tokens and access tokens. A cryptographically valid token **is not automatically valid to invoke every API**.

### 16.2. Required Dependencies

With Spring Boot 3.x and Spring Security 6.x, the backend can use these starters:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
</dependencies>
~~~

This is a Maven snippet from a Spring Boot project, not a complete POM. Verify exact dependency versions and project compatibility.

### 16.3. Illustrative Security Configuration

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CognitoSecurityConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = System.getenv("COGNITO_ISSUER");
        String clientId = System.getenv("COGNITO_CLIENT_ID");

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> appTokenValidator = jwt -> {
            boolean expectedToken = "access".equals(
                jwt.getClaimAsString("token_use"));
            boolean expectedClient = clientId.equals(
                jwt.getClaimAsString("client_id"));

            if (expectedToken && expectedClient) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected token use or app client",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                appTokenValidator
            )
        );
        return decoder;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders/read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**This is a learning example**, not complete production code. It demonstrates:

1. Loading **issuer** and **app client ID** from trusted environment/config.
2. Using the issuer's JWKS to verify signatures.
3. Using standard validators to verify expiry, not-before, and issuer per Spring Security version.
4. **Explicitly validating `token_use` and `client_id`** for Cognito access tokens.
5. Checking **scopes** on API endpoints.
6. Enforcing **object-level authorization** in the service/data layer.

Example environment:

~~~text
COGNITO_ISSUER=https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE
COGNITO_CLIENT_ID=examplepublicclientid
~~~

Values are placeholders; no real credentials. When accepting tokens from multiple app clients, replace the single `clientId` comparison with a **managed allowlist** matching your trust model. If the API uses **`client_credentials`** from confidential clients, verify scopes/audience/client binding per actual token claims.

### 16.4. Scope Authorization Is Not Business Authorization

For example, **`SCOPE_orders/read`** only states the token can call that API group—not read every order. Endpoint **`GET /api/orders/123`** must still:

- Extract the user identity from the valid access token, typically **`sub`**.
- Load order 123 from the database.
- Verify owner/tenant or authorized role.
- Return the record only if business permissions match.

**MFA does not grant permission to "view all orders"; the Java backend's IAM role does not grant end-user data permissions either.**

### 16.5. JWT Key Rotation and JWKS Caching

Cognito can rotate JWT signing keys. Resource server JWT libraries should fetch and cache **JWKS** reliably, supporting new key IDs rather than hardcoding a public key forever. Handle network/JWKS endpoint outages, caching, and timeouts safely; never disable signature verification because key lookup failed.

**Never use unverified JWT decoding** in production. Base64-decoding lets you view the payload, not prove the token was issued by Cognito.

## 17. Read-Only AWS CLI Commands to Inspect Cognito

The following commands **do not create, modify, or delete user pools, reset passwords, send OTPs, or invoke auth**. They require AWS CLI with IAM read permissions and the right Region/account. Never access someone else's production account without authorization.

### 17.1. Verify AWS Identity

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Do not confuse the CLI's **AWS caller identity** with a **Cognito user** signing into a website; they are two separate identity systems.

### 17.2. List User Pools

~~~bash
aws cognito-idp list-user-pools \
  --max-results 20 \
  --region ap-southeast-1 \
  --query "UserPools[].{Id:Id,Name:Name,Created:CreationDate}"
~~~

In environments with many pools, handle pagination. A User Pool is identified by Region + UserPoolId; if the CLI targets the wrong Region, it will not find the pool even though it exists.

### 17.3. Inspect MFA, Password Policy, Recovery, and Feature Plan

~~~bash
aws cognito-idp describe-user-pool \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --region ap-southeast-1 \
  --query "UserPool.{Id:Id,Name:Name,MFA:MfaConfiguration,Policies:Policies,Recovery:AccountRecoverySetting,Tier:UserPoolTier,AddOns:UserPoolAddOns,Status:Status}"

aws cognito-idp get-user-pool-mfa-config \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --region ap-southeast-1
~~~

Fields to inspect:

| Field | Meaning |
| --- | --- |
| **MfaConfiguration** | OFF, OPTIONAL, ON. |
| **SoftwareTokenMfaConfiguration** | Pool TOTP status. |
| **SmsMfaConfiguration** | SMS MFA config per pool type. |
| **EmailMfaConfiguration** | Email MFA config when supported by feature plan. |
| **WebAuthnConfiguration** | Passkey/user verification options if present. |
| **PasswordPolicy** | Length, character rules, temporary password expiry, history. |
| **AccountRecoverySetting** | Recovery priority channels/conditions. |
| **UserPoolTier** | Feature plan such as Lite/Essentials/Plus per returned data. |

Note that **`describe-user-pool`** may also return email/SMS configs, Lambda trigger ARNs, and resource details. Strip unnecessary internal details before pasting output into tickets.

### 17.4. Inspect App Clients and Auth Flows

~~~bash
aws cognito-idp list-user-pool-clients \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --max-results 20 \
  --region ap-southeast-1

aws cognito-idp describe-user-pool-client \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --client-id EXAMPLECLIENTID \
  --region ap-southeast-1 \
  --query "UserPoolClient.{Name:ClientName,Id:ClientId,Flows:ExplicitAuthFlows,OAuthFlows:AllowedOAuthFlows,CallbackURLs:CallbackURLs,PreventExistence:PreventUserExistenceErrors,RefreshRotation:RefreshTokenRotation,AccessTTL:AccessTokenValidity,IdTTL:IdTokenValidity}"
~~~

**Never print full app client details in public spaces**, because confidential app clients can include sensitive fields such as client secrets. Filtering with `--query` is a strong security habit.

### 17.5. Inspect Threat Protection / Risk Configuration

~~~bash
aws cognito-idp describe-risk-configuration \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --region ap-southeast-1
~~~

This command may require Cognito Plus/threat protection or specific permissions to view full settings. **`AccessDenied`** does not automatically mean the feature is off; check IAM, plan, Region, and the exact error code.

### 17.6. Inspect WAF Association on a User Pool

~~~bash
aws wafv2 get-web-acl-for-resource \
  --resource-arn arn:aws:cognito-idp:ap-southeast-1:111122223333:userpool/ap-southeast-1_EXAMPLE \
  --region ap-southeast-1
~~~

Requires AWS WAF/Cognito IAM permissions and depends on Region and actual web ACL associations. If WAF is absent, distinguish "not associated" from "caller lacks permission to inspect".

### 17.7. Restrictions on Reading User MFA Preferences

Authorized administrators can use **AdminGetUser** to inspect user status and MFA settings. However, responses can contain **email, phone, attributes/PII**. Never run bulk exports or paste raw user data into logs or tickets. Every admin query must have a documented business reason and access control.

### 17.8. Commands Intentionally Excluded from This Inspection Exercise

The following operations **alter security or data** and are out of scope for read-only inspection:

~~~text
aws cognito-idp set-user-pool-mfa-config
aws cognito-idp update-user-pool
aws cognito-idp admin-set-user-mfa-preference
aws cognito-idp admin-reset-user-password
aws cognito-idp admin-disable-user
aws cognito-idp update-user-pool-client
~~~

These command names are shown to help recognize mutating actions; **do not run them** during an audit task. For production, use reviewed IaC, migration plans, rollback testing, and auditing.

## 18. Monitoring and Auditing Authentication

### 18.1. Observe at the Right Layer

| Layer | Key Signal | Meaning |
| --- | --- | --- |
| Cognito sign-in | Successes/failures/challenge outcomes in supported event logs. | Can users sign in? |
| Threat protection (Plus) | Risk level, compromised credentials, blocked/required MFA, event feedback. | Are attacks/account takeovers occurring? |
| SES/SMS delivery | Sent/delayed/rejected messages, bounces, sandbox, quotas. | Are users receiving codes? |
| WAF | Allowed/blocked/challenged requests, rate patterns. | Bot/credential stuffing or false positives? |
| CloudTrail | Pool/app client config changes, IAM/admin actions within logging scope. | Who altered policies, MFA, or users? |
| Java API | JWT validation failures, 401/403s, object-level authorization outcomes. | Are tokens valid and API permissions enforced? |
| Cost Explorer/Budgets | MAU/tier, SMS/email/WAF/CloudWatch/Lambda trigger usage. | Is cost driven by real users or abuse? |

**CloudTrail is not a complete default log of every OTP entry or password attempt.** Never log passwords, OTPs, or tokens to compensate for missing audits. Enable user activity/threat protection logs where supported, with appropriate retention and IAM restrictions.

### 18.2. Suggested KPIs/SLOs

- **Sign-in success rate** over valid authentication attempts.
- **MFA completion rate** by challenge type, separating user errors from delivery failures.
- **Password recovery success rate**: users completing resets without support escalation.
- **Time to sign in**: p50/p95 from initiation to established session.
- **Suspicious sign-in rate** by risk level and channel without logging unnecessary PII.
- **OTP delivery time**, undelivered/bounced codes.
- **Lockout/helpdesk tickets** after enabling required MFA.
- **Cost per successfully authenticated monthly user** or per active user cohort.

If tighter security causes account recovery failures to spike, there may be a **recovery channel design flaw**, not necessarily user error.

### 18.3. Alerts and Runbooks

| Signal | First Action |
| --- | --- |
| SMS OTP delivery failures spike | Check sandbox, sender/registration, Region, quotas, delivery routes. |
| Email MFA codes not arriving | Check SES identities/quotas, bounce/deliverability, pool plan, and message settings. |
| Risk blocks spike after policy update | Check Audit vs. Full-function mode, false positives, WAF/NAT/VPN traffic. |
| `ForgotPassword` `InvalidParameterException` spikes | Check verified recovery attributes and MFA channel conflicts. |
| 401s spike after frontend release | Check `token_use`, issuer/`client_id`, callbacks/PKCE, and JWKS. |
| 403s from Java API spike | Separate missing scopes from object-level permissions; never hastily disable authz. |
| Unexpected SMS spend spike | Inspect OTP spam, rate controls, WAF, send volume, and billing by destination. |

Avoid overly sensitive alerts on individual mistyped OTPs; users make typos. Monitor ratios and trends, correlated with IP/device anomalies and business impact.

## 19. Costs of Cognito and Related Services

No single unit price fits every Cognito deployment. Account for both the feature plan and supporting services:

| Cost Line | Cost Driver | Optimization |
| --- | --- | --- |
| **Cognito User Pools** | Lite/Essentials/Plus plan and **Monthly Active Users (MAU)** per pricing terms. | Pick tier by actual needs; do not enable Plus solely for TOTP MFA. |
| **SMS / End User Messaging** | Message volume and destination country, sender identity/registration per policy. | Use TOTP/passkeys where suitable, WAF anti-spam, monitor retries. |
| **Amazon SES** | Email OTP/MFA/recovery sends, bounces, and data transfer per pricing. | Maintain deliverability, send only in valid flows, detect abuse. |
| **AWS WAF** | Web ACLs, rules, requests, managed/bot control features. | Scope rules to workload; avoid paying for unneeded rules. |
| **CloudWatch / Logs** | Log ingestion/storage/queries, metrics, alarms. | Structured logs, tuned retention, never log sensitive payloads. |
| **Lambda triggers** | Runtime execution, invocations, logs, network, retries. | Trim unneeded logic and optimize cold starts/calls. |
| **API Gateway / ALB / backend** | HTTP requests, compute, data transfer. | Cache where appropriate; scale and rate-limit properly. |
| **Data residency / Regions** | Pool location, SES/SMS integration, data, and networking. | Design Regions/DR intentionally. |

### 19.1. When Is the Plus Plan Needed?

**Threat protection** (compromised credentials, adaptive auth/risk) requires **Plus** per current documentation. **Email MFA, password reuse prevention, and passwordless/passkeys** are supported starting at **Essentials** under plan terms.

Do not upgrade to Plus just for **TOTP MFA** if other requirements do not need Plus—always check current official pricing/tier capabilities for your Region and date.

### 19.2. Credential Stuffing Can Drive Up Your Bill

A bot sending tens of thousands of sign-in/OTP requests can:

- Trigger rate-limit errors.
- Generate email/SMS messages and delivery charges.
- Increase WAF/CloudWatch request and log volume.
- Create support incidents when users get locked out.
- Distort adoption and business metrics.

Deploy budget alerts, WAF, challenge/rate rules, abuse monitoring, and message caps. **Budget alerts are not hard cost caps** that automatically stop spending.

## 20. Troubleshooting MFA and Password Recovery

| Symptom | Possible Cause | Checks |
| --- | --- | --- |
| MFA required enabled, yet users cannot log in. | Factor not enrolled, app misses `MFA_SETUP`, missing MFA channel. | Pool MFA config, user preferences, challenge responses, onboarding. |
| TOTP codes always rejected. | Phone clock drift, unverified secret, wrong account entry. | `Associate`/`VerifySoftwareToken` state, clock, Session validity. |
| SMS not received. | Sandbox, origination registration, quota, non-E.164 number, delivery lag. | Cognito SMS settings, SNS/End User Messaging delivery logs. |
| Email MFA not received. | Lite plan, SES unconfigured, unverified sender, quota/bounce/spam. | `UserPoolTier`, `EmailMfaConfiguration`, SES status. |
| User has email MFA yet `ForgotPassword` fails. | Email is preferred MFA with no eligible recovery phone. | `AccountRecoverySetting`, `phone_number_verified`, support flow. |
| User has SMS MFA yet SMS password reset fails. | Cognito bars using the same phone for MFA and recovery. | Add verified email fallback or admin recovery. |
| Optional MFA yet managed login never prompts setup. | Optional does not auto-render MFA enrollment UX. | Build settings/enrollment UI using Cognito APIs. |
| User gets email OTP while app expects `SMS_MFA`. | Hardcoded `ChallengeName` parser or wrong auth mode. | Read `ChallengeName` dynamically; verify client flow. |
| Passwordless OTP fails under Required MFA. | Cognito first-factor/MFA compatibility rules. | `AllowedFirstAuthFactors` and WebAuthn exceptions. |
| Federated user receives no local TOTP MFA. | Federated MFA is delegated to the external IdP. | SAML/OIDC IdP policy and sign-in path. |
| Cognito returns 403 after enabling WAF. | Web ACL rule blocks legitimate traffic. | WAF sampled requests/logs, rate rules, IP/NAT. |
| Threat protection blocks VPN staff. | Risk engine flags unusual location/device (false positive). | Audit logs, enforcement settings, allow/block exceptions. |
| API returns 401 despite valid-looking token. | Wrong issuer/`exp`/`token_use`/`client_id`/signature/JWKS. | JWT validator and app client mapping. |
| API returns 403 after successful login. | Missing scope/group or lacking object-level permission. | Authorization rules and business data ACLs. |
| Logout fails to block old JWTs at custom API. | Offline signature+exp check ignores revocation. | Token/session design, TTLs, revocation-aware checks. |
| Repeated wrong MFA codes lock account. | Cognito backoff/lockout after repeated failures. | Retry policy, user support; never bypass security. |

### 20.1. Layered Diagnostic Tree

~~~mermaid
flowchart TD
    A["User cannot complete sign-in"] --> B{"Received ChallengeName?"}
    B -->|"No"| C["Check app client, password/auth flow, WAF, risk block"]
    B -->|"Yes"| D{"App handles challenge properly?"}
    D -->|"No"| E["Update parser/UI for TOTP/SMS/Email/MFA_SETUP"]
    D -->|"Yes"| F{"User receives/verifies factor?"}
    F -->|"No"| G["Check SES/SMS/TOTP, clock/session, user attrs"]
    F -->|"Yes"| H{"Cognito returns AuthenticationResult?"}
    H -->|"No"| I["Check lockout, risk response, challenge error"]
    H -->|"Yes"| J["Check JWT validation / API scopes / tenant permissions"]
~~~

### 20.2. Operational Traps

- Never disable MFA pool-wide to help a single user.
- Never turn user password resets into unauthenticated automated actions.
- Never log passwords, OTPs, or tokens to troubleshoot.
- Never drop JWT validation because the frontend reports errors.
- Never leave broad WAF allowlists open indefinitely when tuning false positives.
- Never treat **Cognito sign-in success** as proof every API is properly authorized.

## 21. Real-World Scenarios and Solutions

### Scenario A — Rolling Out TOTP for Employees

**Requirement:** Internal staff manage customer orders; the company wants every local password sign-in to require a second factor.

**Design:** Evaluate MFA = **ON**, enable TOTP, onboard via `AssociateSoftwareToken`/`VerifySoftwareToken`, guide authenticator setup, provide identity-verified recovery, and retain admin change logs. If the enterprise already uses Entra ID/Okta, enforcing phishing-resistant MFA directly at the IdP may be a better fit.

**Testing:** New users, existing users, lost phones, wrong TOTP, expired `Session`, admin resets, and apps abandoning challenges midway.

### Scenario B — Email-Only Customers

**Requirement:** Users register with email, the app enables email MFA, and recovery policy allows only email.

**Problem:** Email used as preferred MFA cannot be used for self-service password reset over the same channel in Cognito. Users risk getting locked out.

**Design:** Collect and verify a **phone number** as an alternate recovery channel, or provide an admin-assisted workflow. If collecting phone numbers is infeasible, consider **TOTP MFA** instead of email MFA and use email for recovery per policy; test the full sign-in/recovery flow before rollout.

### Scenario C — Stopping Credential Stuffing

**Requirement:** Login failures surge across many IPs, with some valid password pairs succeeding.

**Design:** Enable WAF rate/bot protections, MFA, Plus threat protection if warranted, ensure password flows trigger compromised-credentials checks, enable risk alerts, and restrict user-existence messaging.

**Avoid:** Blocking an entire country's IP space or enabling Block across all risk levels without auditing, which disrupts legitimate users.

### Scenario D — Java API Accepts ID Tokens as Bearer Tokens

**Requirement:** Frontend signs in successfully but sends the ID token instead of the access token to the Java API. The backend checks only the signature.

**Problem:** The ID token is meant for the identity client; the backend is accepting the wrong token type.

**Design:** Java API validates **`token_use=access`**, issuer, client binding, `exp`, scopes, and business ownership. Frontend sends the proper access token or uses a BFF session—never using ID tokens for resource authorization.

### Scenario E — Risk-Based MFA in Plus

**Requirement:** Product wants fewer MFA prompts for routine customer logins, yet requires MFA on unfamiliar devices/locations.

**Design:** **MFA OPTIONAL**, Plus threat protection, run Audit-only first, gather sufficient telemetry, and configure risk actions (MFA/block/notifications) with support fallback. Test false positives with VPNs and carrier NATs.

### Scenario F — User Loses Device After Phishing

**Requirement:** A user suspects their password was stolen and lost their TOTP phone.

**Design:** Support verifies identity via an approved secure process, reviews suspicious activity, revokes active refresh/session tokens, resets the password/re-enrolls MFA, re-verifies recovery channels, and notifies the user per policy. Never use unverified email/SMS as an arbitrary MFA bypass.

## 22. Hands-On Exercises with Suggested Answers

**Exercise 1 — Building a security policy for a transactional system.** A system has local users, an SPA, and a Spring Boot API. Design the app client, MFA, recovery, and token validation.

**Hint:** Public app client + Authorization Code/PKCE, risk-aligned MFA policy, TOTP, alternate recovery channel, JWT access-token validation at the API, and object/tenant authorization. Never embed a client secret in the SPA.

**Exercise 2 — Password history.** A team wants to block reusing the last 10 passwords and detect leaked passwords at sign-in.

**Hint:** Essentials/Plus provides reuse prevention, but **compromised-credentials detection requires Plus** and works only on supported authentication flows.

**Exercise 3 — ForgotPassword fails for SMS MFA users.** A user has a verified phone but no verified email.

**Hint:** Cognito cannot use the same phone for both SMS MFA and password reset; require an alternate verified email or admin recovery.

**Exercise 4 — Email MFA login sends no code.** Pool is on Lite and email uses the default path.

**Hint:** Email MFA requires Essentials/Plus and customer-configured SES; upgrade the plan, configure SES sender/quotas carefully, and verify deliverability and cost.

**Exercise 5 — Federated user bypasses local MFA.** User signs in through a corporate SAML IdP.

**Hint:** Enforce MFA at the IdP; never assume Cognito's local pool adds a second factor after federation—audit SAML/OIDC integration and IdP policies.

**Exercise 6 — Over-blocking WAF.** After enabling a rate rule, many users behind one office public IP receive 403.

**Hint:** Inspect WAF sampled requests/logs, tune keys/rates/exceptions based on risk, and monitor effectiveness without disabling WAF completely.

**Exercise 7 — Passkeys in an MFA-required pool.** Product wants passwordless passkeys while still satisfying multi-factor rules.

**Hint:** Check **`WebAuthnConfiguration.FactorConfiguration=MULTI_FACTOR_WITH_USER_VERIFICATION`**, feature plan, and browser support; do not treat passkeys as a second factor after a password.

**Exercise 8 — JWT still works after logout.** A custom Java API validates signatures and expiration offline.

**Hint:** Cognito revocations are not checked by JWT libraries verifying only signatures/`exp`; implement session/revocation-aware authorization or appropriately short access token lifetimes.

**Exercise 9 — Evaluating OTP costs.** SMS volume jumps 5× while successful logins rise only 10%.

**Hint:** Investigate bots/retries/OTP abuse, WAF, SMS sends by destination, delivery failures, and login success rates; optimize **cost per successful user sign-in**.

**Exercise 10 — Required MFA causes post-release lockouts.** Over 20% of existing users lack TOTP or verified phones.

**Hint:** Roll back the policy change safely, add onboarding/enrollment UI, provide recovery guidance, and test thoroughly before re-enabling required MFA. Never skip MFA per request.

## 23. Self-Check Questions

**Q1.** How does a Cognito User Pool differ from an Identity Pool?  
**Answer:** User Pool authenticates app users and issues tokens; Identity Pool issues temporary AWS credentials based on an identity.

**Q2.** What are the main values of `MfaConfiguration`?  
**Answer:** **OFF, OPTIONAL, ON**.

**Q3.** Does `MFA OPTIONAL` cause managed login to automatically prompt every user to set up MFA?  
**Answer:** No. The application must provide enrollment UX if users are to enable MFA themselves.

**Q4.** What are three common message/software MFA methods?  
**Answer:** **TOTP, SMS MFA, email MFA**.

**Q5.** Does email MFA require Essentials/Plus and SES?  
**Answer:** Yes, per current Cognito requirements.

**Q6.** Is an email OTP used as the sole sign-in factor automatically MFA?  
**Answer:** No. It is a passwordless **first-factor**.

**Q7.** Can a passkey serve as a second factor after password sign-in in Cognito?  
**Answer:** Not under the current model; a passkey with user verification can satisfy MFA requirements as the first factor when the matching WebAuthn setting is enabled.

**Q8.** Why is `VerifySoftwareToken` needed after `AssociateSoftwareToken`?  
**Answer:** Associate generates the secret; Verify confirms the user actually controls the authenticator and produces valid codes.

**Q9.** Can a user with SMS MFA use that same phone number for `ForgotPassword`?  
**Answer:** No. An alternate recovery channel or admin recovery is required.

**Q10.** Does `TemporaryPasswordValidityDays` cause regular passwords to expire periodically?  
**Answer:** No. It applies to temporary passwords created/set by admin flows.

**Q11.** Which feature plans include password reuse prevention?  
**Answer:** **Essentials/Plus** per current capabilities.

**Q12.** Which feature plan includes compromised-credentials detection?  
**Answer:** **Plus threat protection**, on supported flows.

**Q13.** Why doesn't SRP get the same compromised-credentials sign-in check as `USER_PASSWORD_AUTH`?  
**Answer:** SRP does not transmit the plaintext password to Cognito in that flow.

**Q14.** Should adaptive MFA configure MFA as `ON` or `OPTIONAL`?  
**Answer:** **OPTIONAL**, per Cognito threat protection risk-based MFA guidance.

**Q15.** Does enabling local Cognito MFA automatically require MFA for SAML users?  
**Answer:** No; the federated IdP handles authentication and MFA.

**Q16.** Do WAF and threat protection perform the same job?  
**Answer:** No. WAF handles request/bot/rate protections; threat protection evaluates sign-in risk and password compromise among other capabilities.

**Q17.** Can an access token replace an AWS access key?  
**Answer:** No. User Pool tokens are not IAM credentials.

**Q18.** What must a Java backend verify on a Cognito access JWT?  
**Answer:** Signature/JWKS, issuer, expiration, `token_use`, client binding, scopes, and business permissions.

**Q19.** Why can a token revoked by Cognito still be accepted by a custom JWT library?  
**Answer:** Libraries checking only signature and expiry do not check live revocation state.

**Q20.** Which APIs can update a user's MFA preference?  
**Answer:** **SetUserMFAPreference** with a user access token, or **AdminSetUserMFAPreference** with admin IAM permissions.

**Q21.** When MFA is required, why must onboarding include an enrollment step?  
**Answer:** Users without an enrolled valid factor may be unable to complete MFA-required sign-ins.

**Q22.** What are key cost drivers of sign-in and MFA?  
**Answer:** Cognito tier/MAUs, SMS, SES emails, WAF, CloudWatch, Lambda triggers, and backend/networking.

## 24. Summary and Operations Checklist

**MFA, password policies, and authentication flow protection** form an interconnected system; designing any piece in isolation creates security gaps or locks out users.

Pre-production checklist:

1. **Classify identities:** local, federated, human users, machine-to-machine; never apply one MFA rule blindly to all.
2. **MFA policy:** OFF/OPTIONAL/ON aligned with risk and UX; required MFA must include onboarding.
3. **Methods:** TOTP, SMS/email where delivery/plan conditions hold; passkey user verification per supported feature/flow.
4. **Passwords:** length, complexity, password manager compatibility, reuse prevention where available.
5. **Recovery:** maintain a verified channel **distinct from preferred MFA** or an identity-verified admin process.
6. **Tokens:** Authorization Code + PKCE, secrets kept in the right place, full JWT validation, scopes, and object-level authorization.
7. **Sessions:** refresh token rotation, revocation, sign-out, and protected browser/session cookies.
8. **Threat protection:** Plus plan, understand SRP/federation limits, audit before enforcing.
9. **WAF:** tested rate/bot rules avoiding false positives and OTP spam.
10. **Observability:** MFA completion, recovery success, risk events, OTP delivery, and logs with strict access and retention controls.
11. **Cost:** manage MAUs/tier, SMS/email/WAF/CloudWatch, and monitor traffic anomalies.
12. **Testing:** sign-up, enrollment, lost factor, password reset, policy updates, app client mismatch, token revocation, federated sign-in, and rollbacks.
13. **Operational security:** least-privilege IAM, CloudTrail audits, zero credential logging, and reviewed policy changes.
14. **Reliability:** user support workflows and incident response without bypassing MFA when related systems fail.

Good security is not just forcing users to type more codes. It means making **legitimate sign-in reliable**, **anomalous sign-in hard to succeed**, **account recovery trustworthy**, and **data access continuously verified** across your entire AWS architecture.

### Official AWS Documentation References

- [Amazon Cognito User Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-identity-pools.html) — application identity management foundation.
- [Adding MFA to a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa.html) — MFA modes, preferences, passwordless, and passkeys.
- [TOTP software token MFA](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa-totp.html) — enrolling and verifying authenticators.
- [SMS and email message MFA](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa-sms-email-message.html) — OTP delivery and prerequisites.
- [User pool feature plans](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-sign-in-feature-plans.html) — Lite, Essentials, Plus.
- [Passwords, account recovery, and policies](https://docs.aws.amazon.com/cognito/latest/developerguide/managing-users-passwords.html) — passwords, recovery, and password history.
- [Threat protection](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-settings-threat-protection.html) — adaptive auth and compromised credentials.
- [Working with adaptive authentication](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-settings-adaptive-authentication.html) — risk signals and responses.
- [Associate AWS WAF with a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-waf.html) — request-level protection.
- [Refresh tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html) — refresh rotation and session lifetimes.
- [Token revocation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html) — sign-out and revocation.
- [Cognito pricing](https://aws.amazon.com/cognito/pricing/) — feature plan and MAU pricing.



