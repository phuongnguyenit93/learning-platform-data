# 8.10. Requesting `acr_values` and Desired Authentication Level

## Lesson Objectives

In OpenID Connect (OIDC), a successful authentication does not necessarily satisfy the same assurance level for every business operation. An application might accept a regular SSO login to view a profile, yet require a **higher authentication level** before transferring funds, approving payments, or changing sensitive details.

The **`acr_values`** parameter in an OIDC Authentication Request lets the **Relying Party (RP)** express the **Authentication Context Class Reference (ACR)** values it wants the **OpenID Provider (OP)** to apply when authenticating the user. The actual outcome must be examined via the **`acr`** claim in the ID token, if provided by the OP.

After this lesson, you will be able to:

- Explain what **ACR** represents and why ACR values require shared semantic agreement between OP and RP.
- Build an OIDC Authorization Request containing `acr_values` and understand **priority order**, URL-encoding, and the parameter's limitations.
- Distinguish **`acr_values` (request)** from **`acr` (result in ID token)**.
- Distinguish `acr`, `amr`, `auth_time`, `max_age`, and `prompt=login`.
- Build a **step-up authentication** flow using Spring Security OAuth 2.0 Client.
- Add custom parameters via `OAuth2AuthorizationRequestResolver` while preserving `state`, `nonce`, redirect URI, and PKCE.
- Enforce application policy when the OP returns an undesired ACR level or omits the `acr` claim.

## 1. Problem: "Logged In" and "Sufficiently Authenticated" Are Two Different Questions

Suppose the **Finance Portal** application uses Spring Boot and logs users in through an enterprise OP. The Portal has three feature groups:

| Feature | Typical Authentication Need |
|---|---|
| View profile | Any valid OIDC login session |
| View sensitive reports | Valid login session, possibly requiring sufficiently recent authentication |
| Approve fund transfers | Valid login session and **authentication assurance level** meeting policy |

User Alice may have logged into the OP in the morning. When visiting Finance Portal, the browser reuses her SSO session and Portal receives a valid ID token. For the profile page, that result may be enough.

However, before approving a large payment, the application needs to know **in what context the OP authenticated Alice**: does that context meet the approval policy?

OIDC lets the RP:

1. **Request** desired authentication contexts via `acr_values` or an appropriate `acr` claim request.
2. **Receive and inspect** the `acr` value in the ID token if issued by the OP.
3. **Enforce its own policy** for the business action—for example, allowing it to proceed only when `acr` is in an accepted set and the authentication is recent enough.

The meaning of `acr` is defined by the identity ecosystem/provider. You cannot conclude a security level just because an ID token contains an ACR string that looks like "high."

## 2. What Is ACR?

### 2.1. Authentication Context Class Reference

**ACR** stands for **Authentication Context Class Reference**. In OIDC Core, an ACR value is an identifier string for **an authentication class/context** applied by the OP when authenticating the End-User.

It answers the question:

> "Which authentication assurance class does this authentication outcome belong to, per the OP/identity system's convention?"

Illustrative examples **invented by a hypothetical system**:

~~~text
urn:example:acr:basic
urn:example:acr:strong
urn:example:acr:regulated
~~~

Suppose the enterprise defines:

- `urn:example:acr:basic`: basic authentication conditions per internal policy.
- `urn:example:acr:strong`: enhanced authentication assurance level per internal policy.
- `urn:example:acr:regulated`: assurance level for workflows subject to specific compliance requirements.

**The URNs above are only examples in this lesson, not a standard list understood by all OPs.** When implementing, you must use **the exact ACR strings supported by your provider**, along with their definitions and authentication policies.

An ACR may be tied to an assurance framework recognized by an organization or industry. If the OP uses a formal catalog, read the documentation describing those levels rather than inventing your own meaning for the values.

### 2.2. ACR Is a Level/Context, Not a Login Method Name

Suppose a user logs in with a password and an OTP code. That indicates **methods** that may have been used, yet by itself is not enough to deduce that the OP reached a specific ACR class.

An ACR class can depend on multiple factors:

- How the account was enrolled and how identity was previously vetted.
- Credential types and current authentication mechanisms.
- Use of multiple factors, hardware devices, or phishing-resistant factors.
- Account recovery policies and credential lifecycle management.
- Other criteria defined by the OP's authentication assurance framework.

Do not invent a rule like "OTP means high ACR" unless the OP publishes that mapping and commits to enforcing it.

### 2.3. ACR Describes the Authentication Event, Not Directly a Business Permission

An ACR value describes **the user's authentication context**. It does not automatically authorize an application action.

For instance, Alice may hold a strong ACR yet **not belong to the group authorized to approve transactions**. Finance Portal must still verify:

- Which account is identified via issuer and subject?
- Does the user have the appropriate role/business permission?
- Is the user authorized to handle this specific transaction?
- Do the ACR level and authentication recency satisfy the requirements?

A valid OIDC outcome is only one input to an authorization decision.

## 3. Where Does `acr_values` Sit in the Authorization Request?

### 3.1. Standard OIDC Authentication Request Parameter

OIDC defines the optional parameter:

~~~text
acr_values
~~~

It lets the RP send **a string of one or more space-separated ACR values**, representing the requested Authentication Context Class References.

For example, if the RP wants the strong level and lists basic as a lower-priority option:

~~~text
acr_values=urn:example:acr:strong urn:example:acr:basic
~~~

When placed in a URL, spaces and special characters must be encoded. A query fragment can become:

~~~text
acr_values=urn%3Aexample%3Aacr%3Astrong%20urn%3Aexample%3Aacr%3Abasic
~~~

**The order of values expresses the RP's preference**: earlier values are preferred over later ones. Order does **not** mean the OP will try each level in a mandatory fallback algorithm.

### 3.2. Complete Authorization Request Example

Suppose client `finance-web` is registered at the OP and uses OIDC Authorization Code:

~~~http
GET /authorize?response_type=code&client_id=finance-web&redirect_uri=https%3A%2F%2Ffinance.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&scope=openid%20profile&state=RANDOM_STATE&nonce=RANDOM_NONCE&acr_values=urn%3Aexample%3Aacr%3Astrong&max_age=300&code_challenge=RANDOM_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: idp.example.com
~~~

The `RANDOM_*` values are placeholders; **never use fixed strings in real applications**.

| Parameter | Responsibility |
|---|---|
| `response_type=code` | Selects the Authorization Code flow |
| `client_id` | Identifies the registered OAuth 2.0 Client/RP |
| `redirect_uri` | Callback registered at the OP |
| `scope=openid ...` | Requests OIDC processing |
| `state` | Binds the authorization response to the initial request |
| `nonce` | Binds the ID token to the Authentication Request |
| `acr_values` | Lists authentication contexts preferred by the RP |
| `max_age` | Requests authentication recency, if used |
| `code_challenge` and `code_challenge_method` | PKCE components protecting the Authorization Code flow |

`acr_values` is a **request parameter sent to the OP**. It is not a verified claim, nor is it an access token.

### 3.3. Practical Meaning of "Requesting" an ACR

`acr_values` is a **preference request** in OIDC; merely putting this value in the URL **does not guarantee** the OP will authenticate at the desired level or return the exact requested value.

Depending on the provider and policy, the OP may:

- Perform an authentication mechanism matching a requested ACR.
- Reuse an existing login session if that session already satisfies the right level.
- Prompt the user to perform additional authentication.
- Not support the ACR value requested by the client.
- Return an authentication result with a different ACR or omit the `acr` claim from the ID token, depending on capabilities and protocol context.
- Return an error if it cannot satisfy the request per policy or the claim request mechanism used.

Therefore, when a business action has a **mandatory requirement** on authentication level, the RP must inspect **the result** and deny the action if unmet. Never treat "sent `acr_values`" as equivalent to "achieved ACR."

## 4. The `acr` Claim in the ID Token

### 4.1. `acr` Is the Result Published by the OP

An ID token after authentication may contain the claim:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "employee-1288",
  "aud": "finance-web",
  "iat": 1760000100,
  "exp": 1760003700,
  "auth_time": 1760000000,
  "acr": "urn:example:acr:strong"
}
~~~

This is an **illustrative payload**, not a real token. In OIDC, `acr` is an optional claim and does not necessarily appear in every ID token.

Interpretation:

- `iss`: issuer that issued the ID token.
- `sub`: End-User subject within the issuer's scope.
- `aud`: audience, which must match the client/RP receiving the token.
- `iat`, `exp`: token issuance and expiration timestamps.
- `auth_time`: timestamp when the OP authenticated the End-User, if provided.
- `acr`: authentication class/context reported by the OP for that authentication event.

The RP must validate the ID token according to standard OIDC rules **before trusting the `acr` claim**: signature, issuer, audience, expiration, and flow constraints such as nonce where applicable.

Never take an unverified JSON payload from the browser and check `acr`; an untrusted party could supply any value it wants.

### 4.2. The `acr` Claim May Be Absent

If `acr` is absent, that **does not automatically mean either low or high assurance**; it simply means the RP did not receive an ACR value usable for its policy.

If the application requires a minimum ACR level for a sensitive operation, the prudent handling is:

> No valid and accepted `acr` → business assurance condition not met.

The application can guide the user to restart an appropriate authentication flow or report that the OP does not support the required assurance level.

### 4.3. Compare Only Values with Trusted Definitions

Suppose the organization accepts:

~~~text
urn:example:acr:strong
urn:example:acr:regulated
~~~

Code can check against a preconfigured allowlist. Never assume that any `acr` string containing the word `strong` or `mfa` meets requirements. Nor should alphabetical ordering, trailing digits in a URN, or vendor naming conventions be treated as a universal hierarchy.

If the organization wants a **minimum level**, it needs a mapping and ordering rule **agreed upon with the OP**. Lexicographical string comparison has no security meaning.

## 5. Comparing `acr_values`, `acr`, `amr`, `auth_time`, and `max_age`

These fields are easily confused because all relate to authentication, yet they answer different questions.

| Component | Location | Main Question |
|---|---|---|
| `acr_values` | Authentication Request | Which authentication class does the RP want the OP to apply? |
| `acr` | ID token, when present | Which authentication class/context did the OP declare? |
| `amr` | ID token, when present | Which authentication methods participated? |
| `auth_time` | ID token, when present | When was the user authenticated by the OP? |
| `max_age` | Authentication Request | What is the maximum authentication age in seconds the RP accepts? |
| `prompt=login` | Authentication Request | Does the RP want the OP to ask for re-authentication? |

### 5.1. `amr` Indicates Methods; `acr` Indicates Class/Context

`amr` stands for **Authentication Methods References**. For example, an ID token might contain:

~~~json
{
  "acr": "urn:example:acr:strong",
  "amr": ["pwd", "otp"]
}
~~~

Here, the OP declares an ACR class and the participating authentication methods. `pwd` and `otp` are common method identifiers, though exact interpretation depends on the provider and definitions in use.

You cannot infer in reverse that any token with `amr=["pwd","otp"]` achieves `urn:example:acr:strong`. Assurance depends on more than just the count of methods.

Similarly, an OP may provide `acr` without including `amr` in the ID token. If business policy requires ACR, work with the OP to identify trustworthy `acr` values.

### 5.2. `max_age` Controls Recency, Not Assurance Level

Example:

~~~text
acr_values=urn:example:acr:strong
max_age=300
~~~

The RP has requested two things:

1. Desired authentication class is `urn:example:acr:strong`.
2. Authentication must be recent within a 300-second limit.

These two conditions are independent. Someone who entered a password 10 seconds ago may **still not meet** the strong level; someone who used a strong method yesterday may **fail** the 5-minute recency check.

When `max_age` is sent in an OIDC Authentication Request, the ID token must include `auth_time` so the RP can evaluate recency. `iat` is the token issuance time and does not replace `auth_time`.

### 5.3. `prompt=login` Requests Re-Authentication, Without Specifying ACR

If the app sends:

~~~text
prompt=login
~~~

the RP asks the OP to re-authenticate. However, that is **not a specific request for an ACR class**.

You can combine:

~~~text
prompt=login
acr_values=urn:example:acr:strong
~~~

to express both re-authentication intent and desired level simultaneously. For a "within 5 minutes" requirement, `max_age` together with `auth_time` expresses and verifies freshness more clearly than looking at `prompt=login` alone.

### 5.4. Valid ID Tokens with Insufficient `acr` Must Still Be Handled

Consider three responses:

| Verified ID Token | Decision for Action Requiring `strong` |
|---|---|
| `acr=urn:example:acr:strong` | Meets ACR condition; proceed to check permissions and freshness |
| `acr=urn:example:acr:basic` | Fails ACR requirement; do not perform action |
| Missing `acr` claim | No proof meeting policy; do not perform action |

An ID token can still be **protocol-valid** while failing **the application's assurance policy**. These are two separate verification layers.

## 6. `acr_values` Is a Preference Parameter; Mandatory Requests Use `claims`

### 6.1. Why Does `acr_values` Have Limits?

Under OIDC, `acr_values` requests ACRs in preference order. However, that parameter alone does not create a universal obligation for the OP to fail if it cannot meet a specific value.

When the RP needs to express an **essential ACR claim** per OIDC, it can use the **`claims`** parameter in the Authentication Request, with `acr` inside `id_token`.

Example JSON body for `claims`:

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:acr:strong",
        "urn:example:acr:regulated"
      ]
    }
  }
}
~~~

Semantically, the RP is requesting that the `acr` claim in the ID token hold one of the permitted values and marks this claim as **essential**. The JSON must be URL-encoded when sent in the Authorization Request.

OPs vary in **support for the `claims` parameter** and how they handle extended claim requests. Check actual provider documentation and capabilities.

### 6.2. `claims` and `acr_values` Are Not the Same Parameter

| Request Mechanism | What It Expresses |
|---|---|
| `acr_values=urn:example:acr:strong` | Prefers an authentication context |
| `claims` with `id_token.acr.essential=true` | Expresses an essential ACR claim request per OIDC claim request mechanics |
| `max_age=300` | Caps authentication age |
| `prompt=login` | Asks the OP to re-authenticate |

Using `claims` still **does not replace RP-side verification**. The application must validate the ID token and inspect the actual received ACR value. If the provider ignores the request or does not support that mechanism, the RP must never proceed with a sensitive action simply because the request sent `essential=true`.

Some providers offer different syntax or specialized assurance mapping. Rely on the specific provider's protocol and documentation rather than assuming they understand the illustrative URNs in this lesson.

### 6.3. Example Passing `claims` and `acr_values`

Content before URL-encoding:

~~~text
scope=openid
acr_values=urn:example:acr:strong
claims={"id_token":{"acr":{"essential":true,"values":["urn:example:acr:strong"]}}}
~~~

In a real URL, quotation marks, braces, spaces, and colons must all be properly encoded using a URI builder library.

Never build URLs by concatenating arbitrary input strings. Invalid `claims` JSON or an unsupported provider request can cause the Authorization Request to be rejected.

## 7. Step-Up Authentication Flow

### 7.1. What Is Step-Up?

**Step-up authentication** means the application requires the user to perform or prove a **stronger authentication level** when preparing to execute an action requiring high assurance.

Example:

1. Alice opens Finance Portal via OIDC Login and is admitted to the overview page.
2. Alice selects "Approve transaction."
3. Portal checks policy and sees the current session lacks the required ACR level.
4. Portal initiates a new OIDC Authentication Request with appropriate `acr_values`, optionally adding `max_age` per freshness policy.
5. The OP authenticates Alice per policy and returns the OIDC callback.
6. Portal verifies the result and reads `acr` and `auth_time` from the ID token.
7. Only when assurance, freshness, identity, and business permissions all align does Portal permit approval to proceed.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant RP as Finance Portal / Spring Security
    participant OP as OpenID Provider
    U->>RP: Access dashboard
    RP->>OP: Standard OIDC Login if needed
    OP-->>RP: ID token, possibly with basic ACR
    RP-->>U: Dashboard
    U->>RP: Request transaction approval
    Note over RP: Check ACR / auth_time / permissions
    RP-->>U: Require step-up
    RP->>OP: Authorization Request with desired acr_values
    OP->>U: Additional authentication if required by policy
    OP-->>RP: OIDC callback and ID token
    Note over RP: Verify token, acr, auth_time, iss + sub
    alt Policy satisfied
        RP-->>U: Allow workflow to proceed
    else Not satisfied
        RP-->>U: Reject and explain authentication requirement
    end
~~~

**Step-up does not always mean re-entering a password.** The OP may recognize that the existing session already meets the requested level, or apply an additional mechanism such as a passkey or MFA per policy.

### 7.2. Verifying Identity Before and After Step-Up

An important scenario: a browser may hold multiple accounts at the OP. After redirecting to the OP for step-up, the user might pick a different account.

If the business operation was initiated for Alice, the RP must ensure the step-up callback belongs to **the exact same subject** required by the operation—usually matching the **`iss` + `sub`** pair of the user who initiated the action.

Do not compare only email or display name. Never let Bob's step-up result silently confirm a transaction prepared in Alice's context.

### 7.3. Protecting Business Flow State Before Returning

When step-up finishes, the application may want to return to the approval page. Protect the associated data:

- Which transaction was submitted for approval.
- Who initiated the step-up journey.
- Which ACR/freshness policy applies.
- When the request was created and its expiration time.
- The Authorization Code's `state`/nonce/PKCE state.

Manage pending approval steps with server-side state bound to the user and session, along with an unpredictable transaction ID when needed. **Never** accept a URL parameter like `?transactionId=...&approved=true` as proof of successful step-up.

Right before executing the actual approval, the backend must re-check permissions and policy for the current transaction. A single successful callback does not mean all subsequent actions are allowed indefinitely.

### 7.4. Avoiding Authentication Loops

If the OP does not support the ACR requested by the application, the browser can get stuck redirecting to login repeatedly if the RP does not check outcomes properly.

Right handling:

1. If `acr` is insufficient, do not proceed with the sensitive operation.
2. Clearly inform the user that the required assurance level could not be verified.
3. Offer a bounded retry path if appropriate.
4. Never loop the exact same Authorization Request infinitely.
5. Provide administrative handling or direct the user to support when the OP cannot issue the required assurance.

## 8. Configuring OIDC Client in Spring Boot

### 8.1. Dependency

With Maven and Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 8.2. Registration and Provider

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/company
~~~

In this configuration:

- `corporate` is the registration ID used in Spring Security.
- `client-id` and `client-secret` are issued by the OP when registering a confidential client.
- `issuer-uri` is the trusted issuer; Spring can use OIDC discovery to fetch endpoints and metadata.
- `scope=openid` causes the authorization request to be handled as an OIDC request.
- `authorization_code` is the login flow using the application's callback.

**`acr_values` is not a scope.** Never put `acr_values` into the `scope` list to request an ACR; it is an **additional parameter** of the OIDC Authorization Request.

## 9. Adding `acr_values` with `OAuth2AuthorizationRequestResolver`

### 9.1. Why Customize the Authorization Request?

Spring Security provides `DefaultOAuth2AuthorizationRequestResolver` to build requests from `ClientRegistration`, redirect URI, and callback-binding values.

When an OIDC parameter such as `acr_values` must be sent, we can **wrap the default resolver** and add `additionalParameters`. This continues using the framework's mechanisms to generate `state`, OIDC nonce, and PKCE when configured.

### 9.2. Example Requesting a Preferred ACR for All OIDC Logins

The following example sets an illustrative ACR for registration `corporate`. It is a **configuration applied to every login of this registration**, suitable when the application wants the entire login session to carry high assurance.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcAcrSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver delegate =
                new DefaultOAuth2AuthorizationRequestResolver(
                        registrations,
                        "/oauth2/authorization");

        OAuth2AuthorizationRequestResolver resolver =
                new OAuth2AuthorizationRequestResolver() {

                    @Override
                    public OAuth2AuthorizationRequest resolve(
                            HttpServletRequest request) {
                        return addAcrValues(delegate.resolve(request));
                    }

                    @Override
                    public OAuth2AuthorizationRequest resolve(
                            HttpServletRequest request,
                            String registrationId) {
                        return addAcrValues(
                                delegate.resolve(request, registrationId));
                    }
                };

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .authorizationEndpoint(endpoint -> endpoint
                                .authorizationRequestResolver(resolver)))
                .build();
    }

    private static OAuth2AuthorizationRequest addAcrValues(
            OAuth2AuthorizationRequest original) {

        if (original == null
                || !original.getScopes().contains("openid")) {
            return original;
        }

        return OAuth2AuthorizationRequest.from(original)
                .additionalParameters(parameters ->
                        parameters.put(
                                "acr_values",
                                "urn:example:acr:strong"))
                .build();
    }
}
~~~

Explanation:

1. `delegate` creates the Authorization Request via Spring Security using the configured provider and registration.
2. `addAcrValues(...)` leaves the request intact except for adding the OIDC parameter.
3. `getScopes().contains("openid")` ensures ACR is added only when this is an OIDC request.
4. `OAuth2AuthorizationRequest.from(original)` preserves all fields built by the framework.
5. `additionalParameters(...)` adds `acr_values` to the request sent to the OP.
6. `oauth2Login(...)` uses the new resolver to initiate the Authorization Code flow.

**Distinction to keep clear:** This example only **requests** the ACR. Without evaluating the `acr` claim after callback, it **does not guarantee** the user met policy assurance.

Any other non-OIDC registration should be handled according to its own needs; if the system has multiple OIDC registrations with different levels, choose policy per trusted registration/business flow.

### 9.3. Adding Multiple ACRs in Preference Order

In the resolver, you can set:

~~~java
parameters.put(
        "acr_values",
        "urn:example:acr:strong urn:example:acr:basic");
~~~

Spring Security builds the query URI and performs URL encoding when creating the Authorization Request. **The value placed in the parameter map is the unencoded string**; do not manually replace spaces with `%20` before putting it into the map.

If the business operation **is not permitted** to use `basic`, **never put `basic` into the list as an acceptable fallback**. Define a clear policy and validate the returned ACR.

### 9.4. When Step-Up Is Needed for Only One Feature

Putting strong `acr_values` on **every login** can force users through enhanced authentication even when just opening a regular info page.

For applications with both routine and sensitive features:

- Perform initial login using a normal OIDC registration/flow.
- When the user accesses a feature requiring high assurance, evaluate policy on the backend.
- If unmet, the backend initiates **a new OIDC Authentication Request** with `acr_values` for step-up.
- When the callback succeeds, the backend checks `acr`, `auth_time` (when freshness policy applies), identity, and business permissions.
- Proceed with the feature only after all conditions are satisfied.

Technically, you can design a **dedicated step-up endpoint** wired to an `OAuth2AuthorizationRequestResolver` strategy, or use a separate registration/login flow configured for high assurance. When using a separate registration with the same client/provider, its callback/redirect URI must also be allowed by the OP.

**Never take `acr_values` directly from an uncontrolled query parameter** letting the client arbitrarily decide the required assurance level. The RP must define policy by business operation and control value selection.

## 10. Reading the `acr` Claim in Spring Security

### 10.1. OIDC Principal After Login

After OIDC Login on the Servlet stack, `Authentication` is typically an `OAuth2AuthenticationToken` whose principal is `OidcUser`. The ID token can be read from the principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AssuranceInfoController {

    @GetMapping("/me/assurance")
    AssuranceInfo assurance(
            @AuthenticationPrincipal OidcUser user) {

        String acr = user.getIdToken().getClaimAsString("acr");

        return new AssuranceInfo(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                acr,
                user.getIdToken().getAuthenticationTime()
        );
    }

    record AssuranceInfo(
            String issuer,
            String subject,
            String acr,
            java.time.Instant authenticationTime) {}
}
~~~

Here:

- `user.getIdToken()` is the ID token processed by OIDC Login.
- `getClaimAsString("acr")` returns the ACR value, or `null` if the claim is absent.
- `getAuthenticationTime()` returns the authentication timestamp if `auth_time` is present.
- `issuer` and `subject` identify the OP-scoped identity.

The endpoint above is only for **observation**. Publicly exposing assurance details may be unnecessary in production; consider securing the endpoint and minimizing exposed data.

**Never** merely display ACR on the UI and let the frontend decide whether transaction approval is allowed. Decisions must be enforced on the backend.

### 10.2. Example Checking the ACR Value in Business Logic

A simple policy helper:

~~~java
import java.util.Set;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class AssurancePolicy {

    private static final Set<String> APPROVED_ACR = Set.of(
            "urn:example:acr:strong",
            "urn:example:acr:regulated"
    );

    private AssurancePolicy() {
    }

    public static boolean hasAcceptedAcr(OidcUser principal) {
        if (principal == null || principal.getIdToken() == null) {
            return false;
        }

        String acr = principal.getIdToken().getClaimAsString("acr");
        return acr != null && APPROVED_ACR.contains(acr);
    }
}
~~~

The `APPROVED_ACR` policy must come from trusted configuration and reflect **values actually issued by the OP with semantics approved by the organization**.

This helper checks only the ACR condition—it does **not yet** verify:

- whether `auth_time` is recent enough;
- whether the user has business permissions;
- whether the transaction belongs to the user or valid operation scope;
- whether the post-step-up subject matches the subject who started the transaction.

The remaining conditions must be enforced inside the operation's protection workflow.

### 10.3. Ensuring the ID Token Was Verified Before Use

In the example, `OidcUser` comes from Spring Security's OIDC Login. The application must let the framework run all protocol steps and token validations, using trusted issuer/provider configuration.

Never write a controller accepting an arbitrary JWT from a request body:

~~~java
// Do not do this to decide assurance:
// String acr = decodeWithoutVerification(jwt).get("acr");
~~~

An `acr` value is meaningful only when issued by an **OP trusted by the RP** and validated per protocol rules. In multi-OP systems, ACR policies must also be separated by issuer, since the same ACR string does not necessarily share the same definition across two providers.

## 11. Blocking Login If ACR Does Not Meet Requirements

In an application **where every login must achieve high assurance**, you can use the OIDC user service extension point to evaluate ACR before accepting the principal.

Spring Security 6, Servlet stack example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Configuration
public class OidcAssuranceBeans {

    @Bean
    OidcUserService enforcingOidcUserService() {
        OidcUserService delegate = new OidcUserService();

        return new OidcUserService() {

            @Override
            public OidcUser loadUser(OidcUserRequest request)
                    throws OAuth2AuthenticationException {

                OidcUser user = delegate.loadUser(request);

                String acr =
                        request.getIdToken().getClaimAsString("acr");

                if (!"urn:example:acr:strong".equals(acr)) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(
                                    "insufficient_acr",
                                    "Requested authentication context was not met",
                                    null
                            )
                    );
                }

                return user;
            }
        };
    }
}
~~~

Configuration wiring this service into `oauth2Login()`:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OidcUserService enforcingOidcUserService) throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(login -> login
                    .userInfoEndpoint(userInfo -> userInfo
                            .oidcUserService(enforcingOidcUserService)))
            .build();
}
~~~

Both snippets illustrate **coordinating configurations**: in a real project, merge beans/filter chains per your architecture and also apply the resolver requesting `acr_values` from the earlier section.

Meaning:

1. Spring Security processes OIDC Login through the normal flow.
2. `OidcUserService` loads or builds principal information from validated login data.
3. The application inspects the `acr` claim of the **ID token in `OidcUserRequest`**.
4. If unmet, it throws `OAuth2AuthenticationException`; login is not considered successful per policy.
5. If met, the user service returns `OidcUser` so the flow continues.

**Scope note:** the code above **enforces strong ACR on every OIDC Login** using that service. For systems that step up only for specific features, design the policy along a backend-controlled journey so normal login is not unintentionally blocked. You can evaluate assurance at the approval step and design a step-up workflow binding principal, freshness, and transaction.

Never use a session flag like `strongLogin=true` controllable by the frontend in place of a trusted ACR result.

## 12. Step-Up and Managing Servlet Login Sessions

### 12.1. Nature of the Session After Login

Servlet applications usually store `SecurityContext` in `HttpSession` after OIDC Login. The principal may retain ID token details from the completed authentication.

If a user logged in with strong ACR several hours ago, the Portal session may still be active. **The ACR claim in the principal does not automatically expire just because time passes**, yet business policy may require combining it with freshness.

Example:

~~~text
Approval conditions:
  acr is in accepted set
  AND auth_time is within the last 5 minutes
  AND user has appropriate authority/role
  AND user has permission on the transaction
~~~

If `auth_time` is missing when `max_age` was requested, or is too old per policy, Portal must run an appropriate authentication flow again.

### 12.2. Do Not Treat Token Expiration as Authentication Time

These timestamps are distinct:

- `iat`: when the ID token was issued.
- `exp`: when the ID token expires.
- `auth_time`: when the user was authenticated by the OP.
- HttpSession timeout: how long an idle application session stays valid.
- Access token expiry: until when the API-calling token stays valid.

A newly issued ID token with a very recent `iat` **does not prove** the user just performed strong authentication. When freshness is required, use `auth_time` and appropriate OIDC checks.

### 12.3. Avoid Losing Binding Between Step-Up and the Sensitive Task

Suppose Alice is awaiting approval of transaction `TX-4821`. After step-up, the backend must verify:

- Which exact transaction this step-up request served?
- Does the session/account that started step-up still match the callback?
- Did the user switch to another account at the OP?
- Was the transaction modified, deleted, or reassigned during authentication?
- Are ACR and freshness still satisfied at the moment of **executing the operation**?

Relying only on a post-login return URL and an ACR value without binding the transaction can create vulnerabilities in multi-step workflows.

## 13. Working with Providers: ACR Is Not a Universal String

### 13.1. What to Confirm with the OP

Before implementing an assurance policy, agree on:

1. Which **ACR values** the OP supports and what each value means?
2. Does the OP accept `acr_values` in the Authorization Request?
3. Does the OP return the `acr` claim in the ID token, and under what conditions?
4. Does the OP support the `claims` parameter and essential `acr` requests?
5. If it cannot satisfy the requested ACR, does the OP return a different ACR, omit the claim, or return an error?
6. Does the OP support step-up on an existing SSO session? Are special parameters/settings needed?
7. How are `auth_time`, `max_age`, `amr`, and additional authentication policies enforced?

In multi-tenant or multi-OP environments, confirm each issuer separately.

### 13.2. Read Metadata to Understand Capabilities, Without Over-Inferring

OIDC Discovery may publish information such as:

~~~json
{
  "issuer": "https://idp.example.com/realms/company",
  "claims_supported": ["sub", "iss", "aud", "auth_time", "acr"],
  "acr_values_supported": [
    "urn:example:acr:basic",
    "urn:example:acr:strong"
  ]
}
~~~

This is an illustrative example; real providers may omit some fields or publish different lists.

`acr_values_supported`, when published, lists the ACR values the OP advertises as supported. `claims_supported` describes claims the OP is capable of providing. **Presence in metadata does not guarantee your client is permitted to use every value**, nor does omitting an optional field always prove the provider lacks support.

Some products map ACR to proprietary provider authentication policies/flows. Rely on provider documentation and configuration, not metadata alone.

### 13.3. The Same ACR Value Across Two Issuers Does Not Necessarily Mean the Same Thing

Example:

~~~text
Issuer A: https://login-a.example.com
acr: urn:example:acr:strong

Issuer B: https://login-b.example.com
acr: urn:example:acr:strong
~~~

Even if the string is identical, the RP must never assume both OPs apply identical controls and assurance levels. When integrating multiple OPs, build an **issuer-scoped ACR mapping policy** and trust only pre-approved issuers.

## 14. Common Errors and Scenarios

| Symptom | Possible Cause | How to Address |
|---|---|---|
| Sent `acr_values` but no extra MFA appeared | OP accepted existing session, ignored request, or defines ACR differently | Inspect returned `acr` and OP policy; do not infer from UI |
| ID token lacks `acr` | OP does not emit the claim or support is unconfigured | Do not bypass assurance requirement; check provider capabilities |
| `acr` returns a value outside the accepted list | OP could not or did not pick desired ACR | Deny sensitive action; guide user to appropriate auth flow |
| OP returns an error for the ACR value | Unsupported ACR, client lacks permission, or invalid claim request | Cross-check values against provider docs |
| Has strong ACR yet approval still denied | Missing authority or lacking permission on the transaction | Check business authorization policies |
| `auth_time` is too old | SSO session reused an older authentication; freshness unmet | Initiate flow with `max_age`; check authentication timestamp |
| Page loops login redirects endlessly | Policy demands an ACR the provider never returns; callback auto-restarts | Break the loop and display an insufficient-assurance message |
| User after step-up is a different account | OP allowed picking another account in a multi-session browser | Compare `iss` + `sub` against the subject that started the workflow |
| `acr_values` appears inside `scope` | Misconfigured in registration `scope` | Move to `additionalParameters` on the Authorization Request |
| ACR value with spaces is split incorrectly | Manual URL concatenation or bad encoding | Let the URI builder/framework encode request values |
| Found `acr` in an unverified JWT | App decoded token manually and trusted contents | Use OIDC Login and validate tokens from a trusted OP |
| Normal login blocked by step-up policy | Enforced strong ACR on every callback instead of per transaction | Branch policy by backend journey |

### 14.1. Do Not Infer ACR from the User Interface

Seeing an OTP screen does not mean the RP can fill in `acr=strong` itself. Only the OP declares the applied context through the appropriate protocol result; the RP inspects the result and maps it per agreed policy.

Conversely, seeing no MFA prompt during the current login does not necessarily mean the OP failed to meet ACR. The OP's policy may account for existing session state or earlier authentication. If business logic requires a recent event, add a freshness policy.

### 14.2. Never Let the Frontend Choose the Required Assurance Level

Dangerous example:

~~~text
POST /approve-payment?acr=basic
~~~

where the backend treats the `acr` value in the browser query as the policy to enforce.

Policy must be determined by the backend based on operation type and risk. Browser-supplied input may request navigation or initiate a flow, but must never **lower mandatory business assurance levels**.

### 14.3. Avoid Using ACR as a Substitute for Transaction Confirmation

Even with a high ACR, a user can still be tricked into approving the wrong transaction if the application fails to verify **approval context** and resource permissions.

ACR is one part of access policy—it does not prove the user reviewed or consented to the specific contents of a transaction. If business rules require per-transaction confirmation, use a proper transaction confirmation/binding mechanism.

## 15. Example Feature-Based Assurance Policy Design

A hypothetical policy for Finance Portal:

| Action | Required ACR | Freshness | Other Conditions |
|---|---|---|---|
| View profile page | Valid OIDC Login | Per application session | Right account |
| View financial reports | Organization-approved ACR | Within 30 minutes if required | Has report-view permission |
| Create payment order | `urn:example:acr:strong` | Within 10 minutes | Has create permission |
| Approve large transaction | `urn:example:acr:regulated` | Within 5 minutes | Has approve permission and cannot self-approve own order |

The values, timeframes, and permissions in this table are **illustrative policy only**, not universal OIDC requirements or legal regulations.

An implementation strategy:

1. Use standard OIDC Login for basic features.
2. Before each sensitive action, the backend evaluates identity, permissions, ACR, and freshness.
3. If assurance is insufficient, start a new OIDC Authorization Request with the needed ACR and `max_age`.
4. After callback, verify the ID token and confirm the right user account.
5. Proceed with the task only if the policy holds at decision time.
6. Log required security events with a correlation ID, never logging tokens or secrets.

In real systems, centralize policy definitions so endpoints do not accidentally apply inconsistent assurance rules.

## 16. Self-Check Questions

**Q1.** Does `acr_values` force the OP to always return an `acr` value identical to the one in the request?

**Answer:** No. `acr_values` expresses preferred ACRs. The RP must validate the ID token and the actual returned `acr`; if it fails policy, do not allow the high-assurance action.

**Q2.** How do `acr` and `amr` differ?

**Answer:** `acr` represents the authentication class/context declared by the OP; `amr` describes the authentication methods that participated. Never assume a list of methods automatically equals a particular ACR class.

**Q3.** A newly issued ID token has a recent `iat` but `auth_time` from yesterday. Can we treat the user as just authenticated?

**Answer:** No. `iat` is only when the token was issued. To check authentication recency, inspect `auth_time` per policy, typically paired with requesting `max_age` in the flow.

**Q4.** We sent `acr_values=urn:example:acr:strong`, yet the ID token returned `acr=urn:example:acr:basic`. Should we allow approving a transaction requiring `strong`?

**Answer:** No. What was requested does not substitute for what was actually returned; the backend must reject it or initiate a suitable authentication flow if supported.

**Q5.** To request an ACR, should we write `scope: [openid, acr_values]` in `application.yml`?

**Answer:** No. `acr_values` is an OIDC Authorization Request parameter, not a scope. In Spring Security it can be added via `OAuth2AuthorizationRequestResolver`.

**Q6.** If the OP authenticated the user at a strong level long ago, how do we also require freshness?

**Answer:** Use `max_age` per the required threshold and verify `auth_time` in the ID token after the flow. Never treat HttpSession timeout or `iat` as the authentication timestamp.

**Q7.** Two OPs both return the ACR string `strong`. Can the application trust both results as equivalent?

**Answer:** Only if the organization has verified and agreed on the meaning and trustworthiness of that value per issuer. ACR must be interpreted in the context of each OP and its authentication policy.

**Q8.** Step-up succeeded for Bob, but Alice initiated the fund transfer order. Can Bob's callback continue Alice's order?

**Answer:** Never automatically. The backend must bind step-up to the initiating subject and transaction, checking issuer + subject and business permissions. If mismatched, abort or restart properly.

## Key Takeaways

- **`acr_values` is an OIDC Authentication Request parameter** used to request Authentication Context Class References in **priority order**.
- **`acr` in the ID token** is the result declared by the OP, if present. The RP must verify the ID token, check ACR against policy, and **never assume the OP met the requirement simply because the request contained `acr_values`**.
- **`amr`** describes authentication methods; **`acr`** describes authentication context/class; **`auth_time`** and **`max_age`** address authentication recency.
- For sensitive operations, implement **step-up authentication** alongside identity, ACR, freshness, and business permission checks. Policy must be enforced by the backend.
- In **Spring Security OAuth 2.0 Client**, you can add `acr_values` with `OAuth2AuthorizationRequestResolver` and read the result from `OidcUser.getIdToken()`; rely on trusted OP data and framework extension points to manage login state.
