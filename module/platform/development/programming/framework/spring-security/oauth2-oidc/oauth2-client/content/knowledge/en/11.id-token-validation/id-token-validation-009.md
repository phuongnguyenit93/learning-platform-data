# 11.9. Claims auth_time, acr, and amr in Elevated Authentication Requirements

## 1. Why Might a Valid ID Token Still Not Suffice for Sensitive Operations?

In OpenID Connect (OIDC), a **Relying Party (RP)** or **OIDC Client** application can log users in via an OpenID Provider (OP), receive an ID Token, and build a login session in Spring Security. For most ordinary screens, verifying signature, issuer, audience, expiration, nonce (when present), and other OIDC conditions forms the foundation for trusting the user's identity.

However, when a user performs a sensitive operation, the questions often change:

- **When did the user last authenticate?** Was it hours ago, even if the token was just issued?
- Does that authentication's **assurance level** satisfy business requirements?
- **Which authentication methods** were actually used by the provider, such as password, OTP, or a security key?
- If insufficient, how should the application request **reauthentication** or **step-up authentication**?

OIDC provides three especially useful claims:

| Claim in ID Token | Data Type | Question Answered |
|---|---|---|
| **<code>auth_time</code>** | JSON number, Unix time in seconds | When was the user authenticated by the OP? |
| **<code>acr</code>** | JSON string | Which *Authentication Context Class* did the authentication session satisfy? |
| **<code>amr</code>** | JSON array of strings | Which *Authentication Methods* did the OP use? |

These three claims serve different purposes. <code>auth_time</code> states the **recency of authentication**, <code>acr</code> states the **assurance class/level per OP policy**, and <code>amr</code> describes **the methods used**. They supplement ID Token validation and authorization; they do not replace signature, issuer, audience, scope, or business access permissions.

For example: a user logs in via SSO at 08:00 with a password, then opens a funds-transfer page at 14:00. The OP may issue a fresh ID Token at 14:00 from the existing SSO session without prompting for authentication factors again. <code>iat=14:00</code> does not prove the user just authenticated at 14:00; you must inspect <code>auth_time</code> and the completed authentication policy.

## 2. Where the Claims Appear in an ID Token

An illustrative ID Token payload:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "sub": "248289761001",
  "aud": "finance-web",
  "iat": 1794808800,
  "exp": 1794812400,
  "auth_time": 1794808500,
  "acr": "urn:company:assurance:high",
  "amr": ["pwd", "otp"],
  "nonce": "random-nonce-from-client"
}
~~~

This example shows only the payload for learning purposes; a real ID Token is signed by the OP (or processed per the agreed algorithm), and all claims are trustworthy **only after the Client completes ID Token validation**.

In this example:

- <code>iat</code> is when the **ID Token was issued**.
- <code>auth_time</code> is when the **user authenticated at the OP**.
- <code>acr</code> is an assurance class identifier per the <code>company</code> OP's contract.
- <code>amr</code> shows that the OP reported <code>pwd</code> (password) and <code>otp</code> (one-time password) methods.

Values like <code>urn:company:assurance:high</code> illustrate an **organization-defined** policy, not a universal ACR code across all Identity Providers. The actual ACR set, meaning of each value, and MFA/step-up triggers must be agreed upon with the OP.

### 2.1. Claims That Must Be Distinguished

| Claim/Info | Purpose | Do Not Infer |
|---|---|---|
| <code>exp</code> | When the ID Token expires | An unexpired token does not mean authentication is recent |
| <code>iat</code> | When the token was issued | A newly issued token does not mean password/MFA was just entered |
| <code>auth_time</code> | When user authentication occurred | Does not state the method or assurance level |
| <code>acr</code> | Authentication context class asserted by the OP | Do not infer a specific method set without an explicit contract |
| <code>amr</code> | Authentication methods declared by the OP | Do not automatically infer ACR policy, recency, or phishing resistance |
| <code>nonce</code> | Binds ID Token to authorization request and resists replay per OIDC | Not the authentication time or MFA level |
| <code>state</code> | Correlates authorization response/callback with original request | Not an ID Token claim for evaluating assurance |
| Scope/role | Permissions or application scope requested/granted | Does not prove how recently or strongly the user authenticated |

## 3. auth_time: When the User Actually Authenticated

### 3.1. Meaning and Data Type

Per OpenID Connect Core 1.0, <code>auth_time</code> is the time when End-User authentication occurred. Its value is a **JSON number** representing the number of **seconds** since <code>1970-01-01T00:00:00Z</code> (Unix time).

Example:

~~~json
{
  "auth_time": 1794808500
}
~~~

When converting that number to an instant in Java, use <code>Instant.ofEpochSecond(...)</code>, **not milliseconds**. Accidentally calling <code>ofEpochMilli</code> produces a wildly wrong timestamp.

OIDC specifies:

- When the authorization request includes **<code>max_age</code>**, the ID Token **must contain <code>auth_time</code>**.
- When <code>auth_time</code> is requested as an **Essential Claim**, the ID Token **must contain <code>auth_time</code>**.
- In all other cases, <code>auth_time</code> is an **optional** claim that the OP may omit.

This means an ID Token completely valid for regular login can still omit <code>auth_time</code>. For sensitive APIs requiring recent authentication, **a missing <code>auth_time</code> must never default to "just authenticated."**

### 3.2. Checking Recency (Freshness)

Suppose business policy requires the user to have authenticated within **5 minutes**. Upon receiving a valid ID Token, the application computes:

~~~text
age = now - auth_time

Satisfies freshness requirement if:
    auth_time is present with valid type
    auth_time is not too far in the future
    age <= 5 minutes (+ small, controlled clock skew)
~~~

Examples:

| Check Time | <code>auth_time</code> | Authentication Age | Decision with 5-Minute Threshold |
|---|---|---|---|
| 10:04 | 10:00 | 4 minutes | Passes freshness |
| 10:06 | 10:00 | 6 minutes | Fails |
| 10:06 | Absent | Unknown | Fails for operations requiring freshness |
| 10:06 | 10:30 | Far in the future | Fails; inspect clock/OP |

These illustrative timestamps assume the same timezone; in code, convert to UTC <code>Instant</code> to avoid timezone bugs.

### 3.3. auth_time Is Not iat

This is the most critical confusion when building step-up authentication:

~~~text
08:00  User logs in at OP with password
14:00  Application initiates a new OIDC flow
14:00  OP sees SSO cookie, issues a new ID Token

New ID Token:
    iat       ≈ 14:00
    auth_time ≈ 08:00
~~~

If the application only checks <code>iat</code>, the user passes the "recently authenticated" check even though the OP did not prompt for any factor again. Policy must rely on <code>auth_time</code>.

### 3.4. max_age Requests Recent Authentication

An authorization request can pass:

~~~text
max_age=300
~~~

<code>max_age</code> is the **maximum allowable elapsed time in seconds since the OP actively authenticated the End-User**. If the last authentication is too old, the OP must attempt to re-authenticate the user per protocol requirements.

When a fresh authentication attempt is needed immediately:

~~~text
max_age=0
~~~

A value of <code>0</code> requests reauthentication instead of silently reusing existing SSO. Even so, the Client must still **read and verify <code>auth_time</code> in the final ID Token**; never assume that merely sending <code>max_age</code> guarantees the OP complied with policy.

The <code>prompt=login</code> parameter can ask the OP to re-display the login screen, yet <code>max_age</code> carries an explicit recency constraint and mandates the <code>auth_time</code> claim. Never replace <code>auth_time</code> checks with observing UI screens or solely sending <code>prompt=login</code>.

## 4. acr: Authentication Context Class Reference

### 4.1. What Assurance Class Does ACR Describe?

<code>acr</code> is a **string** identifying the Authentication Context Class that the OP asserts the authentication satisfied. Example:

~~~json
{
  "acr": "urn:company:assurance:high"
}
~~~

ACR typically represents an **authentication policy**: required factors, device enrollment rules, phishing resistance, session lifetime, identity-proofing criteria, and other constraints. ACR **is not simply "number of factors."**

Depending on provider and organization, values might look like:

~~~text
urn:company:assurance:basic
urn:company:assurance:high
urn:company:assurance:phishing-resistant
~~~

These are custom-defined examples; **OIDC defines no default ordering like "basic < high < phishing-resistant."** The application must maintain its own policy/allowlist and an explicit contract with the OP. Never compare <code>acr</code> lexicographically or parse the tail of the URI to guess assurance strength.

### 4.2. acr_values: Requesting Authentication Levels in Priority Order

OIDC supports the authorization request parameter:

~~~text
acr_values=urn:company:assurance:phishing-resistant urn:company:assurance:high
~~~

<code>acr_values</code> carries a **space-separated** list of ACR values ordered by Client preference. In real URLs, spaces and special characters must be percent-encoded by the HTTP library.

This lets the Client express **desired ACR values**, yet per OIDC Core using <code>acr_values</code> alone requests <code>acr</code> as a **Voluntary Claim**. The OP may fail to meet the requested value and return a different ACR or omit the claim, depending on capabilities and rules.

Therefore, after receiving the ID Token, the application must still:

1. Perform standard ID Token verification.
2. Read <code>acr</code>.
3. Match against the **set of allowed ACRs** for the operation.
4. Reject the operation or trigger another step-up if the result is insufficient.

### 4.3. Requesting acr as an Essential Claim via the claims Parameter

OIDC supports the <code>claims</code> parameter, passing a JSON object requesting claims in <code>id_token</code> or <code>userinfo</code>. When the OP supports <code>claims</code>, the Client can request a specific ACR as an **Essential Claim**:

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:company:assurance:phishing-resistant"
      ]
    },
    "auth_time": {
      "essential": true
    }
  }
}
~~~

This JSON value must be URL-encoded when placed in the authorization request's <code>claims</code> parameter. Never send raw unencoded JSON in the URL.

Per OIDC Core, when the OP **supports the claims parameter** and <code>acr</code> is requested as Essential with <code>value</code>/<code>values</code>, the OP must return an <code>acr</code> value from the requested set; if it cannot satisfy it, it must treat authentication as failed. The OP may prompt the user to re-authenticate or supply additional factors to meet the requirement.

The "OP supports" condition is critical. Not every provider implements <code>claims</code>, <code>acr</code>, or step-up the same way. Even when the OP claims compliance, **the RP must still verify the received <code>acr</code> value** and enforce internal policy.

> **Protocol note:** If you send both <code>acr_values</code> and an explicit <code>acr</code> request with <code>value</code>/<code>values</code> inside <code>claims</code>, OIDC Core states the combined behavior is **undefined**. Pick one clear mechanism per request and follow provider documentation.

### 4.4. ACR Does Not Automatically Equal Access Permission

An ID Token with a strong ACR only states that authentication met a context class. It does not prove the user holds an admin role, payment-approval rights, or membership in a readable data group.

For example, approving a large payment requires **all of the following simultaneously**:

~~~text
User has permission APPROVE_PAYMENT
AND valid ID Token
AND acr belongs to the allowed set for payments
AND auth_time is sufficiently recent
AND transaction request is bound to the exact user and session
~~~

Never use <code>acr</code> to replace business authorization.

## 5. amr: Authentication Methods References

### 5.1. Meaning and Examples

<code>amr</code> is an **array of strings** used by the OP to record the authentication methods used:

~~~json
{
  "amr": ["pwd", "otp"]
}
~~~

Common example values:

| AMR Value | General Meaning |
|---|---|
| <code>pwd</code> | Password |
| <code>otp</code> | One-time password |
| <code>mfa</code> | Multi-factor authentication, if published by the OP under corresponding conventions |
| <code>hwk</code> | Proof-of-possession of a hardware key |
| <code>swk</code> | Proof-of-possession of a software key |
| <code>fpt</code> | Fingerprint biometric |

These codes appear in the Authentication Method Reference ecosystem; standardized lists and meanings are governed by **RFC 8176 / IANA Authentication Method Reference Values Registry**. Providers may also use custom values, provided both sides agree on the meaning of unregistered values.

<code>amr</code> **is not a comma-separated string**, nor is it a count of methods. Per OIDC, the claim is a JSON **array of case-sensitive strings**, e.g., <code>["pwd","otp"]</code>.

### 5.2. What amr Does Not Prove

Seeing <code>["pwd", "otp"]</code> is not automatically enough to conclude authentication meets every "high-grade MFA" policy:

- OTP could be an authenticator app, SMS, or another mechanism with vastly different phishing resistance.
- Order or which factors applied to the current session may be unclear without an explicit OP contract.
- A provider might report MFA as <code>"mfa"</code> or list individual methods, depending on implementation.
- An OP might omit <code>amr</code> even after performing MFA.
- <code>amr</code> carries no timestamp of its own; recency still requires <code>auth_time</code>.
- A method labeled "hardware" does not automatically prove phishing resistance or device binding at the level business policy requires.

If policy requires "phishing-resistant authentication," the reliable indicator is **an ACR explicitly committed by the OP for that assurance level**, combined with time and other constraints; <code>amr</code> can serve as a supplementary signal when defined by the OP contract.

### 5.3. Can amr Be Used in Authorization Decisions?

Yes, **only when an explicit contract exists with the OP** specifying how AMR is emitted and what each value means. For instance, an internal system might require:

~~~text
acr = urn:company:assurance:high
AND auth_time within 5 minutes
AND amr contains "mfa" per OP contract
~~~

If the OP does not guarantee always emitting <code>amr</code>, such a policy could reject MFA-authenticated users. Conversely, if the OP emits <code>mfa</code> yet the underlying context lacks phishing resistance, checking <code>mfa</code> alone may be too permissive.

For sensitive operations, **a missing policy-required claim** should yield **insufficient assurance**, never implicit acceptance.

## 6. Comparing auth_time, acr, and amr in Practical Scenarios

| Scenario | <code>auth_time</code> | <code>acr</code> | <code>amr</code> | Conclusion |
|---|---|---|---|---|
| User logged in with password 4 hours ago; OP issues new ID Token via SSO | 4 hours ago | Basic | <code>["pwd"]</code> | Fine for regular app usage; fails "fresh within 5 minutes" |
| User just re-authenticated with password | Current | Basic | <code>["pwd"]</code> | Passes freshness, but may not meet high-assurance requirement |
| User just completed MFA per OP policy | Current | High | <code>["pwd","otp"]</code> | Can satisfy policy requiring High + freshness |
| OP just issued token without <code>auth_time</code> | Absent | High | <code>["mfa"]</code> | Insufficient proof of recency |
| OP returned lower ACR than required | Current | Basic | <code>["pwd","otp"]</code> | Fails ACR-based policy; check contract/OP |
| High ACR yet past allowed time window | 1 hour ago | High | <code>["mfa"]</code> | Fails recent-authentication requirement |

The table conclusions are not universal rules for all organizations: exact ACR values, time windows, and accepted methods must be determined by **business policy and OP integration contract**.

## 7. Step-Up Authentication: From Initial Request to Result Verification

**Step-up authentication** means asking the user to perform additional authentication or elevate their assurance level **when a specific action requires higher assurance than the current login**.

Admin application example:

1. User logs in via OIDC to view a report list.
2. Upon clicking "Export sensitive data," the application evaluates the current ID Token.
3. <code>auth_time</code> is stale or <code>acr</code> is insufficient, so the application initiates a **new authorization request** to the OP with freshness and assurance parameters.
4. The OP performs reauthentication/MFA per policy.
5. The OP returns an authorization code; the Client exchanges it and verifies the new ID Token.
6. **Only after verifying <code>auth_time</code> and <code>acr</code> on the new ID Token** does the application allow the next step per business permissions.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant B as Browser
    participant RP as Spring Security OIDC Client
    participant OP as OpenID Provider
    U->>B: Request sensitive operation
    B->>RP: GET /payments/approve
    RP->>RP: Check permissions + current ID Token auth_time/acr
    alt Insufficient assurance/freshness
        RP-->>B: Trigger OIDC step-up
        B->>RP: GET /oauth2/authorization/company?stepup=true
        RP->>RP: Generate state, nonce, max_age, and required claims
        RP-->>B: 302 to authorization endpoint
        B->>OP: Authorization request with step-up requirements
        OP->>U: Reauthentication / extra auth factor
        OP-->>B: Callback with code and state
        B->>RP: GET /login/oauth2/code/company?code=...&state=...
        RP->>OP: Token request
        OP-->>RP: Token response with ID Token
        RP->>RP: Verify token, auth_time, acr, identity
    end
    RP-->>B: Allow proceeding if policy and business rights pass
~~~

This is a conceptual model. Post-step-up redirects and resuming the operation must be designed explicitly: never automatically execute a state-changing action merely because the user returned from a callback. For payments or security-setting changes, require explicit transaction confirmation in the business flow with proper CSRF protection.

### 7.1. Passing max_age, prompt, and acr_values

An authorization request might specify:

~~~text
response_type=code
client_id=finance-web
scope=openid profile
redirect_uri=https://app.example.org/login/oauth2/code/company
state=RANDOM_STATE
nonce=RANDOM_NONCE
max_age=300
acr_values=urn:company:assurance:high
~~~

This shows the **pre-URL-encoded** representation, one parameter per line for readability. Real requests travel over HTTPS with properly URL-encoded values.

For mandatory assurance requirements, use Essential <code>claims</code> instead of <code>acr_values</code>. **Do not send both ways of requesting specific ACR values in the same request** if you want deterministic behavior per OIDC Core.

If immediate reauthentication at action time is needed:

~~~text
max_age=0
~~~

If you only want the OP to re-display the login prompt:

~~~text
prompt=login
~~~

In both cases, the RP must verify the final result rather than inferring compliance from the fact that the browser displayed some screen.

### 7.2. Essential Claims Request Template

JSON example for <code>claims</code>:

~~~json
{
  "id_token": {
    "auth_time": {
      "essential": true
    },
    "acr": {
      "essential": true,
      "values": [
        "urn:company:assurance:high"
      ]
    }
  }
}
~~~

Combine <code>max_age=0</code> to force immediate reauthentication with <code>claims</code> so supporting OPs require <code>auth_time</code> and the desired ACR. Verify in provider documentation/metadata that the OP supports the `claims` parameter and ACR semantics before relying on this feature.

## 8. Basic Spring Security OAuth 2.0/OIDC Client Configuration

Example Spring Boot 3 / Spring Security 6 Servlet OAuth2 Login application with a preconfigured issuer:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: finance-web
            client-secret: replace-with-secret-from-secure-storage
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

The client secret is a placeholder; real deployments must supply it from a secret manager or environment variable, never committing secrets to a repository. The issuer is also an example and must be replaced with the OP's official issuer.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

When the user logs in:

~~~text
GET /oauth2/authorization/company
~~~

Spring Security uses `ClientRegistration` to create the authorization request, store `state`, receive the callback at <code>/login/oauth2/code/company</code>, and construct `OidcUser` from the OIDC-verified ID Token.

**Important point:** Default configuration verifies the ID Token per protocol, yet the application **must not assume a specific ACR or 5-minute freshness was automatically checked by Spring Security for business requirements**. Policy must be enforced by the application.

## 9. Reading auth_time, acr, and amr from OidcUser

In Spring Security, <code>OidcUser.getIdToken()</code> returns <code>OidcIdToken</code>, which exposes standard accessors via <code>IdTokenClaimAccessor</code>:

- <code>getAuthenticatedAt()</code>: reads <code>auth_time</code> as an <code>Instant</code>.
- <code>getAuthenticationContextClass()</code>: reads <code>acr</code> as a string.
- <code>getAuthenticationMethods()</code>: reads <code>amr</code> as a list of strings.

Illustrative controller returning status only:

~~~java
package example.web;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthenticationInfoController {

    @GetMapping("/me/assurance")
    public Map<String, Object> assurance(
            @AuthenticationPrincipal OidcUser user) {
        Instant authTime = user.getIdToken().getAuthenticatedAt();
        String acr = user.getIdToken().getAuthenticationContextClass();
        List<String> amr = user.getIdToken().getAuthenticationMethods();

        return Map.of(
            "hasAuthTime", authTime != null,
            "hasAcr", acr != null,
            "reportedAmrCount", amr == null ? 0 : amr.size()
        );
    }
}
~~~

This snippet avoids returning the raw ID Token or sensitive values. In applications with multiple authentication mechanisms (not every principal is an <code>OidcUser</code>), ensure the endpoint applies only to OIDC users or handles other principal types cleanly.

Accessors depend on the specific Spring Security version; these names appear in <code>IdTokenClaimAccessor</code> in Spring Security 5.8/6.x. Note the method name is **<code>getAuthenticatedAt()</code>**, not <code>getAuthenticationTime()</code>.

## 10. Writing an Elevated Authentication Policy in Java

Suppose a sensitive operation endpoint requires all of the following simultaneously:

1. Principal is an OIDC-logged-in user.
2. <code>auth_time</code> is present and no older than **5 minutes**.
3. <code>acr</code> equals a high-assurance value committed by the OP.
4. <code>amr</code> may be checked additionally **only if required by the OP contract**.

Create a standalone server-side policy component:

~~~java
package example.security;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component("assurancePolicy")
public final class AssurancePolicy {
    private static final Duration MAX_AUTH_AGE = Duration.ofMinutes(5);
    private static final Duration CLOCK_SKEW = Duration.ofSeconds(30);
    private static final String REQUIRED_ACR =
        "urn:company:assurance:high";

    private final Clock clock;

    public AssurancePolicy() {
        this.clock = Clock.systemUTC();
    }

    public boolean isSatisfied(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }
        if (!(authentication.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        OidcIdToken idToken = user.getIdToken();
        if (idToken == null) {
            return false;
        }

        Instant authenticatedAt = idToken.getAuthenticatedAt();
        String acr = idToken.getAuthenticationContextClass();
        if (authenticatedAt == null || !REQUIRED_ACR.equals(acr)) {
            return false;
        }

        Instant now = clock.instant();
        if (authenticatedAt.isAfter(now.plus(CLOCK_SKEW))) {
            return false; // anomalous auth_time in the future
        }

        // Reject authentication timestamps older than the allowed threshold.
        return !now.isAfter(
            authenticatedAt.plus(MAX_AUTH_AGE).plus(CLOCK_SKEW));
    }
}
~~~

This is an **illustrative policy**. For ultra-sensitive actions, an organization may choose not to add clock skew to the maximum age or require a tighter threshold. Inject <code>Clock</code> via a bean if time conditions need unit testing; this example uses <code>Clock.systemUTC()</code> for brevity.

The policy can also require <code>amr</code>, but only when the OP commits to its semantics and emission. Example:

~~~java
var methods = idToken.getAuthenticationMethods();
boolean hasOtp =
    methods != null && methods.contains("otp");
~~~

Do not replace <code>REQUIRED_ACR.equals(acr)</code> with <code>methods.contains("otp")</code> when policy mandates a specific assurance level. An OTP over an insecure channel and a phishing-resistant method carry very different risk profiles.

### 10.1. Protecting the Endpoint with Method Security

Enable method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Then:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SensitiveOperationController {

    @PostMapping("/payments/approve")
    @PreAuthorize(
        "hasAuthority('PAYMENT_APPROVER') and " +
        "@assurancePolicy.isSatisfied(authentication)")
    public String approve() {
        // In practice: verify transaction and invoke secure business service.
        return "Approved";
    }
}
~~~

This example omits persistence and real transfer logic; it demonstrates **two independent conditions**: the user holds business permission and the current ID Token satisfies assurance/freshness. The <code>PAYMENT_APPROVER</code> authority must be granted from a trusted source per application policy; the annotation alone does not create it.

If the user is logged in yet fails the policy, Spring Security can return 403. In a real application, the UI/handler can route the user into a **controlled step-up flow** and then require them to re-confirm the action. Avoid turning every 403 into an infinite login loop.

### 10.2. Do Not Rely on UI-Only Checks

Never rely solely on JavaScript to hide an "Approve" button. A modified client or direct HTTP request can still invoke the endpoint. Policy must live on the backend holding the Spring Security-verified `Authentication` and ID Token.

For large transactions, also bind reauthentication to the **exact transaction** or operation session; meeting ACR and `auth_time` alone does not prove the user approved arbitrary parameter changes injected by an attacker.

## 11. Adding Elevated Authentication Requirements to Authorization Requests

Spring Security allows customizing authorization requests via <code>DefaultOAuth2AuthorizationRequestResolver</code>. The example below illustrates requiring every login routed through the resolver to include:

- <code>max_age=300</code> to request freshness of at most 5 minutes.
- <code>acr</code> as an Essential Claim matching the high-assurance value agreed with the OP.
- <code>auth_time</code> as an Essential Claim in the ID Token.

### 11.1. Java Configuration

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcAssuranceRequestConfig {

    private static final String ESSENTIAL_CLAIMS = """
        {
          "id_token": {
            "auth_time": {"essential": true},
            "acr": {
              "essential": true,
              "values": ["urn:company:assurance:high"]
            }
          }
        }
        """;

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations)
            throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            clientRegistrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
            builder.additionalParameters(parameters -> {
                parameters.put("max_age", "300");
                parameters.put("claims", ESSENTIAL_CLAIMS);
            }));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

This snippet is **an alternative configuration option** to the <code>SecurityFilterChain</code> in section 8; do not declare two beans with overlapping scope simultaneously without intentionally designing multiple filter chains. Java text blocks require Java 15+; this fits Java 17 in Spring Boot 3.

<code>DefaultOAuth2AuthorizationRequestResolver</code> still constructs baseline parameters such as <code>state</code>, `ClientRegistration`, redirect URI, and required internal data. The customizer only adds assurance parameters to <code>additionalParameters</code>; never generate static state or leak `code_verifier` onto the front channel.

**Deployment note:** The configuration above enforces high assurance on **every authorization request passing through this resolver**. For step-up triggered only on sensitive actions, apply parameters selectively per flow/registration or use a custom resolver distinguishing requests; do not force every user through MFA on every login unless business policy demands it.

### 11.2. Do Not Accidentally Drop state, nonce, or PKCE

If you write an <code>OAuth2AuthorizationRequestResolver</code> from scratch to build new authorization requests, it is easy to forget:

- Random <code>state</code> and authorization request repository handling.
- <code>nonce</code> and OIDC correlation.
- PKCE <code>code_challenge</code>/<code>code_verifier</code> when applicable.
- Redirect URI, registration ID, scopes, and attributes the framework needs during token exchange.

Prefer **delegating to the default resolver** and adding parameters in a controlled way. When building from an existing request, use <code>OAuth2AuthorizationRequest.from(existing)</code> to retain required data and append only permitted parameters. Verify that customizers and extension points do not accidentally wipe PKCE/nonce attributes needed by Spring Security.

### 11.3. Designing Dedicated Step-Up for Sensitive Actions

An application can distinguish:

~~~text
Normal login:
    /oauth2/authorization/company
    → Standard OIDC Authorization Code Flow

Step-up request:
    /oauth2/authorization/company?stepup=true
    → Authorization request with max_age and Essential Claims
~~~

<code>stepup=true</code> here is an **illustrative signal for the resolver to attach stronger requirements**, not a token granting permissions. Users may initiate step-up themselves, yet **cannot self-assert step-up completion via query parameters**; the backend must rely on the verified ID Token and policy.

If supporting multiple sensitive operations such as changing passwords, updating payment methods, or exporting data, each can have its own policy. Never automatically read an ACR from a browser-supplied URL parameter and treat it as the required threshold: requested values and accepted ACR sets must originate from backend configuration.

## 12. Validation: Requesting Is One Thing, Outcome Is Another

Safe handling has two independent phases:

1. **Request:** RP asks the OP to re-authenticate or return appropriate context via <code>max_age</code>, <code>acr_values</code>, or <code>claims</code>.
2. **Response:** RP verifies the ID Token and independently checks <code>auth_time</code>, <code>acr</code> (and <code>amr</code> if policy genuinely relies on it).

Even when an OP supports Essential ACR requests, the RP still needs to verify the returned value. Non-compliant implementations, buggy proxies, or tenant misconfigurations can still yield an outcome failing policy.

### 12.1. Baseline Validation Must Happen First

To trust any assurance claim, you must first trust the ID Token:

| Condition | Reason |
|---|---|
| Valid signature with trusted issuer key/algorithm | Reject tampered tokens |
| <code>iss</code> matches configured OP issuer | Never accept assurance claims from another issuer |
| <code>aud</code> contains matching Client ID and check <code>azp</code> when applicable | Token was issued for the right Client |
| <code>exp</code>/<code>iat</code> valid per time policy | Reject expired tokens or anomalous timestamps |
| <code>nonce</code> matches request when nonce was sent | Binds ID Token to the authentication request |
| Valid callback <code>state</code> | Binds authorization response to original request |

In Spring Security OAuth2 Login/OIDC, the framework handles most protocol validation. The application must maintain proper issuer configuration, `ClientRegistration`, token processing, and extensions. **Never bypass baseline validation just to read `acr`/`amr` more easily.**

### 12.2. Evaluating Each Claim Against Policy

Typical policy flow:

~~~text
if principal is not OidcUser:
    deny

if ID Token not verified per OIDC:
    deny

if action requires recent authentication:
    require auth_time present and within threshold

if action requires ACR:
    require acr in allowed set per OP contract

if business logic depends on AMR:
    require amr contains OP-committed matching values

if business permissions fail:
    deny

allow
~~~

A "fail" status can trigger a step-up redirect rather than a permanent error, yet the sensitive action must never execute before policy is re-evaluated.

### 12.3. A Missing Claim Does Not Default to Unauthenticated — Nor to Satisfied

Suppose an ID Token is valid yet omits <code>amr</code>. The user may have completed MFA while the OP omits method claims. The right decision is:

- If the operation **does not depend on AMR**, do not require AMR.
- If policy **mandates AMR per OP contract**, treat the requirement as unmet and investigate configuration.
- Never conclude "the user logged in with password only" solely because AMR is absent; missing data proves neither that a method happened nor that it didn't.

Similarly, when <code>auth_time</code> is absent for an operation requiring freshness, trigger a flow to obtain the claim or reject — never substitute <code>iat</code>.

## 13. Security Considerations for Step-Up

### 13.1. Protecting Identity During Reauthentication

Suppose User A is logged in and redirected to the OP for step-up. If during step-up the user switches to Account B at the OP, the application must not automatically treat B as confirming A's pending action.

The application must define an account-change policy:

- If step-up aims to re-verify **the exact current user**, require the post-flow <code>(iss, sub)</code> pair to match the pre-flow identity.
- If account switching is supported, handle it as an explicit account-switch flow that clears/re-evaluates pending business context.
- Never use email as a guaranteed key to compare OIDC identities across providers.

<code>login_hint</code> can help the OP suggest an account, yet **never replaces** RP identity checks after the callback.

### 13.2. Binding Step-Up to the Session and Protected Action

A single successful step-up should not become an "unlimited pass" for every action. Consider:

- Short-lived freshness windows evaluated at **every sensitive endpoint**.
- Explicit transaction re-confirmation for high-impact actions.
- Correlation between the step-up request, HTTP session, `state`, and pending work.
- CSRF protection for state-changing requests.
- Avoiding automatic execution of a funds-transfer `POST` immediately upon a callback `GET`.
- Invalidating elevated privileges on logout or account switch.

If *transaction signing* or payload-bound authentication is required, ACR + `auth_time` alone may be insufficient; adopt mechanisms suited to business requirements and threat models.

### 13.3. Time, Clock Skew, and Refresh Tokens

The Client server needs an accurate clock, usually via system time synchronization. A small clock skew may be permitted to avoid false rejections from minor drift, yet never configure skew large enough to nullify freshness policies.

Using a **refresh token** to obtain a new access token / ID Token does not prove the End-User just re-authenticated. Policy must rely on OP-asserted <code>auth_time</code> and genuine authentication flows, never treating refresh time as MFA completion time.

### 13.4. Never Log Sensitive Data

When debugging OIDC Login, avoid logging:

- Raw ID Tokens, access tokens, or refresh tokens.
- Authorization codes, PKCE verifiers, real nonces, and real states.
- Callback URLs with query parameters containing `code`/`state`.
- Session cookies or Client secrets.

You may log sanitized details such as registration ID, validation result code, boolean <code>auth_time_present</code>, allowlisted ACR, check timestamp, and internal correlation ID. Because AMR reveals authentication methods, review privacy policies before writing it to logs or telemetry.

## 14. Common Issues

| Symptom | Causes to Inspect | Resolution |
|---|---|---|
| ID Token lacks <code>auth_time</code> | Did not request <code>max_age</code> / Essential `auth_time`, or OP didn't honor it | Add compliant request parameters and verify provider support; never substitute `iat` |
| Sent <code>max_age=0</code> yet no re-login appeared | Non-compliant provider, request routed to wrong OP, customizer not applied, or unexpected session behavior | Inspect outbound authorization request, OP metadata/policy, and post-callback `auth_time` |
| <code>acr</code> differs from desired value | <code>acr_values</code> is voluntary, OP lacks that context, or policy not met | Use Essential ACR if OP supports it; always validate received ACR |
| Provider ignores <code>claims</code> | Provider doesn't support `claims` parameter or client lacks permission | Check provider docs/metadata and pick an OP-supported step-up mechanism |
| Sent both <code>acr_values</code> and Essential <code>acr</code> with values | Behavior undefined per OIDC Core | Pick one explicit ACR request mechanism |
| <code>amr</code> absent | Optional claim, provider omits it, or incompatible declaration | Require only when backed by contract; do not infer user skipped MFA |
| <code>amr</code> has <code>mfa</code> yet ACR fails | AMR and ACR carry different semantics | Check against policy and OP contract; never replace `acr` with `amr` |
| Still denied after step-up | Stale <code>auth_time</code>, low ACR, app session kept old ID Token, or different account used | Check new ID Token, active principal, session, and policy |
| Callback state/nonce error | Lost session/correlation, multiple tabs, wrong repository/PKCE config | Diagnose authorization request repository and callback chain |
| User caught in endless login redirects | Step-up redirect lacks stop condition when OP cannot meet assurance | Bound retries, show actionable error, log operational error code |
| <code>auth_time</code> parses as 1970 | Confused Unix seconds vs. milliseconds | Use <code>Instant.ofEpochSecond</code> or Spring Security accessor |
| Policy permits based on ACR alone despite missing permissions | Mixed assurance with business authorization | Combine separate role/permission policies |

## 15. Practice Scenarios and Exercises

### Exercise 1 — Distinguishing iat and auth_time

A freshly issued ID Token contains:

~~~json
{
  "iat": 1794808800,
  "auth_time": 1794787200,
  "acr": "urn:company:assurance:high"
}
~~~

Suppose the system requires authentication within the last 5 minutes. Can we use <code>iat</code> as the timestamp?

**Answer:** No. <code>iat</code> is merely token issuance time, whereas <code>auth_time</code> reflects End-User authentication at the OP. If `auth_time` is older than 5 minutes, step-up/reauthentication is required despite the fresh ID Token.

### Exercise 2 — Voluntary vs. Essential ACR

Client sends:

~~~text
acr_values=urn:company:assurance:high
~~~

OP returns:

~~~json
{"acr": "urn:company:assurance:basic"}
~~~

Should the Client allow an action restricted to High?

**Answer:** No. <code>acr_values</code> is a voluntary request. The RP must check the actual outcome; Basic ACR does not satisfy High policy. If the OP supports Essential ACR via <code>claims</code>, use that mechanism for mandatory requirements.

### Exercise 3 — Is AMR Enough to Confirm MFA?

OP returns:

~~~json
{"amr": ["pwd", "otp"]}
~~~

Can we immediately conclude the user satisfied a specific phishing-resistant authentication standard?

**Answer:** No. AMR only lists methods, and OTP characteristics vary widely. You need an ACR and OP contract defining the exact policy; if business requirements demand phishing resistance, require evidence matching that exact criterion.

### Exercise 4 — Writing a Policy

Suppose business requirements state:

~~~text
Role: PAYMENT_APPROVER
Authentication age: <= 300 seconds
Required ACR: urn:company:assurance:high
~~~

Write server-side checks ensuring:

1. The user is authenticated and holds business permission.
2. The ID Token was verified by Spring Security.
3. <code>auth_time</code> is present, valid, and sufficiently recent.
4. <code>acr</code> matches the allowed high value.

You can use <code>AssurancePolicy</code> from section 10 together with method security; if unmet, respond via the step-up flow without executing the payment yet.

### Exercise 5 — Sending Essential Claims

Write the <code>claims</code> JSON requesting:

- <code>auth_time</code> as Essential.
- <code>acr</code> as Essential, matching either of two enterprise-approved authentication classes.

Example:

~~~json
{
  "id_token": {
    "auth_time": {"essential": true},
    "acr": {
      "essential": true,
      "values": [
        "urn:company:assurance:high",
        "urn:company:assurance:phishing-resistant"
      ]
    }
  }
}
~~~

Remember to URL-encode this JSON when sending the authorization request, and do not simultaneously send <code>acr_values</code> alongside the requested values above.

### Exercise 6 — Account-Switching Risk During Step-Up

User A opens a payment form and is prompted for step-up. At the OP, the browser switches to Account B and completes MFA. The application receives a new ID Token with High ACR.

**Question:** Can we complete A's transaction using B's authentication?

**Answer:** Not automatically. If step-up aims to re-verify A, the RP must verify that the post-flow principal's <code>(iss, sub)</code> matches pre-flow Account A and recheck business permissions. Account switching must be an explicit separate flow, never used to resume a transaction bound to an old identity.

## 16. Key Takeaways

- <code>auth_time</code> is when End-User authentication occurred in **Unix seconds**, distinct from <code>iat</code> (when the ID Token was issued).
- <code>auth_time</code> is **mandatory in the ID Token** when the Client sends <code>max_age</code> or requests it as an Essential Claim; otherwise it may be absent.
- <code>acr</code> is a string identifying the **authentication context class** asserted by the OP. Its meaning is governed by provider policy/contract, with no universal ordering.
- <code>acr_values</code> requests ACR as **voluntary**; <code>claims</code> can request Essential ACR with a value list if the OP supports it. Avoid sending both explicit ACR request mechanisms simultaneously.
- <code>amr</code> is an **array of authentication methods** declared by the OP; it is not synonymous with assurance level or authentication timestamp.
- Spring Security provides <code>OidcIdToken.getAuthenticatedAt()</code>, <code>getAuthenticationContextClass()</code>, and <code>getAuthenticationMethods()</code> to read these claims after OIDC Login.
- **Safe step-up** requires requesting stronger/fresher authentication, verifying the new ID Token, enforcing assurance policy and business permissions, and binding identity/session to the sensitive action.

### References

- **[OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)**: ID Token, <code>auth_time</code>, <code>acr</code>, <code>amr</code>, <code>max_age</code>, <code>acr_values</code>, <code>prompt</code>, and `claims` parameter.
- **[RFC 8176 — Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176)**: AMR registration mechanism and reference authentication method values.
- **[IANA Authentication Method Reference Values Registry](https://www.iana.org/assignments/authentication-method-reference-values/authentication-method-reference-values.xhtml)**: registered AMR values and definitions.
- **[Spring Security — IdTokenClaimAccessor API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html)**: <code>getAuthenticatedAt</code>, <code>getAuthenticationContextClass</code>, <code>getAuthenticationMethods</code>.
- **Spring Security Reference — OAuth2 Login (Servlet)**: `ClientRegistration`, OIDC Login, customizing authorization requests, and ID Token validation.
- **Spring Security Reference — Method Security**: protecting endpoints and service methods with annotations and custom policies.
