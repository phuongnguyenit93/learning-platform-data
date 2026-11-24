# Customizing Authentication Results with the AuthenticationProvider Converter

In Spring Security SAML 2.0, the IdP (*Identity Provider*) authenticates the user and sends a SAML Response to the SP's (*Service Provider*) ACS (*Assertion Consumer Service*). Spring Security verifies the Response/Assertion using OpenSAML before creating an `Authentication` object for the application. The **`AuthenticationProvider` response authentication converter** is the extension point that lets enterprises transform a verified SAML principal into an **internal identity**, map **`GrantedAuthority`** instances, check locked accounts, and preserve SAML data needed after login.

In Spring Security 7.x / OpenSAML 5, the key API is **`OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter(...)`**, accepting a `Converter<ResponseToken, Saml2Authentication>`. Its job is **converting the authentication result**, not replacing XML signature, issuer, audience, recipient, timestamp, or replay checks. This lesson belongs to **Identity and authorities**; examples cleanly separate Spring code needing dependencies from standalone Java 17 programs.

## 1. Objectives and practical problem

After this lesson, you will be able to:

- Pinpoint how a **provider** converter differs from the HTTP converter in the SAML authentication filter.
- Understand `Saml2Authentication`, `Saml2AssertionAuthentication`, principal, credentials, and authorities.
- Map an IdP-verified subject to an internal account via a key namespaced by IdP/registration.
- Integrate `UserDetailsService` or an identity-link store, while avoiding auto-granting admin rights from external groups.
- Configure the `OpenSaml5AuthenticationProvider` actually used by `saml2Login`.
- Preserve `Saml2ResponseAssertionAccessor` and `registrationId` when SAML Single Logout is needed.
- Distinguish APIs across Spring Security 5, 6, and 7; test positive/negative cases, offboarding, and tenant isolation.

Example: Partner IdP B sends `NameID=employee-123` with attribute `groups=ExternalAdmins`. Application A only permits the corresponding user `localUserId=u-702` in tenant B to view reports. If the app blindly trusts the external group, it could grant `ROLE_ADMIN` unintentionally. If it omits issuer metadata when linking accounts, IdP C could have a user sharing `employee-123` merged into user B. **A proper converter must fail closed and enforce privileges controlled by application A.**

## 2. Two converters in the SAML pipeline

~~~mermaid
sequenceDiagram
    participant Browser as Browser
    participant Filter as Saml2WebSsoAuthenticationFilter
    participant Input as HTTP AuthenticationConverter
    participant Manager as AuthenticationManager
    participant Provider as OpenSaml5AuthenticationProvider
    participant Output as Response Authentication Converter
    participant App as SecurityContext / Application
    Browser->>Filter: POST ACS with SAMLResponse
    Filter->>Input: convert(HttpServletRequest)
    Input-->>Filter: Saml2AuthenticationToken
    Filter->>Manager: authenticate(token)
    Manager->>Provider: authenticate(token)
    Provider->>Provider: Select registration and verify SAML
    Provider->>Output: convert(ResponseToken)
    Output-->>Provider: Mapped Saml2Authentication
    Provider-->>Manager: Authentication succeeded
    Manager-->>Filter: Authentication
    Filter->>App: Store SecurityContext
    App->>App: Authorization by role, tenant, object
~~~

| Component | Input | Output | Responsibility |
| --- | --- | --- | --- |
| `Saml2AuthenticationTokenConverter` (or OpenSAML-version token converter) | HTTP request at ACS | Unauthenticated `Saml2AuthenticationToken` | Extract Response, select `RelyingPartyRegistration`, retrieve AuthnRequest state |
| `AuthenticationManager` / `ProviderManager` | Authentication request | Authentication result | Dispatch to appropriate provider |
| `OpenSaml5AuthenticationProvider` | SAML token + trusted registration | Resulting Authentication | Decrypt and validate protocol, coordinate validators and converter |
| **`setResponseAuthenticationConverter`** | Provider's `ResponseToken` | `Saml2Authentication` | Build internal principal/authorities post-SAML verification |
| `UserDetailsService` / identity-link service | Verified ID and IdP namespace | Local user, roles, account status | Map and enforce account policies |
| `SecurityContext` / AuthorizationManager | Resulting Authentication | Access decision | Protect endpoints, tenants, objects |

**Key distinction:** `Saml2LoginConfigurer.authenticationConverter(...)`, when used, deals with **HTTP request → authentication token**. `OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter(...)` deals with **SAML assertion → authenticated Authentication**. Choosing the wrong extension point can mean your code never runs or skips necessary verification.

## 3. What is verified in SAML before trusting the principal?

A response arriving at the ACS must pass checks appropriate to the version/provider and profile:

1. Matching `RelyingPartyRegistration` and trusted IdP issuer/entityID.
2. XML signature of the Response or Assertion verified on the right element with the verification certificate.
3. `AudienceRestriction` restricting the Assertion to the application's SP Entity ID.
4. `Destination` and bearer `Recipient` matching a valid ACS.
5. `InResponseTo`, `RelayState`, and AuthnRequest state bound to the right session when SP-initiated.
6. `NotBefore`, `NotOnOrAfter`, subject confirmation, clock skew, and replay adhering to policy.
7. SAML attributes, NameID, and encrypted elements handled per trust policy.

A converter **cannot turn unverified data into verified data**. Calling the converter manually on client-supplied Response XML leaves all downstream role mapping resting on untrusted input. Keep Spring/OpenSAML's default validators and use the converter **strictly for establishing identity/authorities**.

In some versions, Response/Assertion check ordering varies; never write a converter assuming the token passed every check without reading Javadoc/migration notes for your version. When customizing validators, chain onto defaults rather than replacing everything.

## 4. What does the Authentication result contain?

Spring Security's `Authentication` object provides:

| Property | Meaning |
| --- | --- |
| `getPrincipal()` | Identity used by the app; may be `Saml2AuthenticatedPrincipal` or local `UserDetails` |
| `getName()` | Identifying name supplied by principal/Authentication |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` checked during authorization |
| `isAuthenticated()` | Provider succeeded in authenticating |
| `getDetails()` | Additional details per filter/framework |
| `getCredentials()` | Proof/related object; exact type depends on class and version |
| `getSaml2Response()` | SAML Response XML retained per contract; may contain sensitive data |

**External assertion** data is not necessarily the **internal principal**. Example:

~~~text
IdP B authenticates:
  registrationId = partner-b
  issuer         = https://idp.partner-b.example/saml2
  NameID         = employee-123
  groups         = [PortalReaders, ExternalAdmins]

Application A links:
  externalKey    = (partner-b, employee-123)
  localUserId    = u-702
  status         = ACTIVE
  tenant         = tenant-b
  authorities    = [ROLE_REPORT_VIEWER]

Authentication after converter:
  principal      = local user u-702
  authorities    = [ROLE_REPORT_VIEWER]
  samlContext    = preserves assertion accessor/registration
~~~

Role `ROLE_REPORT_VIEWER` **does not** automatically permit viewing tenant C's resources; object ownership and tenant membership checks are still needed.

## 5. Trust boundaries between IdP, SP, and internal entitlement store

The **Identity Provider** is responsible for authenticating users and issuing signed assertions. The **Relying Party** may trust claims per approved contract, without being obligated to grant every right the IdP mentions. The **internal application** retains ownership of authorization policies and business data.

A sound identity-linking table should include:

| Field | Example | Why it is needed |
| --- | --- | --- |
| `registrationId` | `partner-b` | Identifies the approved SP–IdP pair |
| `assertingPartyEntityId` | `https://idp.partner-b.example/saml2` | Separates issuing authorities |
| `externalSubject` | `employee-123` | User key guaranteed stable by the IdP |
| `NameIDFormat/NameQualifier` if needed | persistent format | Prevents namespace ambiguity |
| `tenantId` | `tenant-b` | Data boundary |
| `localUserId` | `u-702` | SP-side user identifier |
| `enabled/locked` | ACTIVE | Offboarding policy |
| `authorities` | `ROLE_REPORT_VIEWER` | Approved privileges within the SP |

Conceptual key:

~~~text
ExternalIdentityKey(
  registrationId,
  trustedIssuer,
  stableSubject,
  qualifiersIfApplicable
)
  -> linkedLocalUser
  -> tenantMembership
  -> accountStatus
  -> permittedAuthorities
~~~

**Never auto-link based solely on email**: emails can change, be reused, or appear across multiple IdPs. Transient `NameID` values can change per session, so long-term links require an agreed immutable ID or a vetted account-linking workflow. Never lowercase/trim user IDs unless the IdP commits to that normalization.

## 6. Why is the default ROLE_USER usually not enough?

Per Spring Security docs, the default provider maps `AttributeStatement` into the principal and grants a baseline `ROLE_USER` authority. It does not construct an entire enterprise authorization graph.

Systems often need:

- `ROLE_REPORT_VIEWER` to read reports.
- `ROLE_REPORT_EDITOR` for approved edits.
- `ROLE_BILLING_APPROVER` only when the account holds internal approval.
- Access to `tenant-b` without **any** access to tenant C.
- Rejecting disabled users even when the IdP just authenticated them.

Thus, the converter can invoke `UserDetailsService` or a dedicated service to resolve roles. **Never** turn every external group value into `new SimpleGrantedAuthority("ROLE_" + group)` without an allowlist.

## 7. Core Spring Security 7.x API

In Spring Security 7.1 / OpenSAML 5, the provider accepts a converter like:

~~~java
OpenSaml5AuthenticationProvider provider =
        new OpenSaml5AuthenticationProvider();

Converter<OpenSaml5AuthenticationProvider.ResponseToken, Saml2Authentication>
        converter = /* application-built converter per requirements */;

provider.setResponseAuthenticationConverter(converter);
~~~

**This is only an API fragment:** it requires a Spring project, proper type imports, and a real converter variable. Merely declaring a converter bean in IoC **is not enough** if the provider used by `saml2Login` is not wired with that bean.

Wiring the provider:

~~~java
http.saml2Login(saml ->
        saml.authenticationManager(new ProviderManager(provider)));
~~~

Spring Security docs include `OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter` to perform default mapping. You can instantiate that delegate and chain `Converter.andThen(...)` to swap principal/roles. This preserves default attribute extraction while reducing boilerplate.

**Do not confuse `ResponseToken` with `Saml2AuthenticationToken`.** `ResponseToken` is used by the provider when converting a verified result; the token from the HTTP filter is not yet an authenticated Authentication.

## 8. Spring Security 7: Saml2AssertionAuthentication and SAML Single Logout

Spring Security 7 introduces `Saml2AssertionAuthentication` and `Saml2ResponseAssertionAccessor`. The migration guide recommends not storing all assertion data inside `Saml2AuthenticatedPrincipal` as in many legacy patterns.

`Saml2AssertionAuthentication` extends `Saml2Authentication` with useful additions:

- `getCredentials()` returns `Saml2ResponseAssertionAccessor`.
- `getRelyingPartyRegistrationId()` returns the specific registration.
- `getPrincipal()` holds the application-used principal.
- `getAuthorities()` holds the final authorities.
- `getSaml2Response()` is inherited.

**Why preserve it?** SAML Single Logout needs assertion/NameID/SessionIndex and registration details to communicate with the right IdP. If a converter replaces Authentication with a username/password token, or a plain `Saml2Authentication` holding only the response string, SLO may lose details the framework expects.

Spring Security 7 Javadoc provides the constructor:

~~~java
new Saml2AssertionAuthentication(
    localPrincipal,
    existingAssertionAccessor,
    mappedAuthorities,
    relyingPartyRegistrationId
);
~~~

The variables are an **illustrative fragment**, not a complete program. Use the accessor returned by the standard converter/provider; never fabricate an "already verified assertion" object from unsigned XML.

## 9. Spring Security 7.1 example: swapping principal and roles via UserDetailsService

Suppose:

1. The application has a `RelyingPartyRegistrationRepository` for `corp` and `partner-b`.
2. A `UserDetailsService` looks up keys `registrationId + "|" + stableExternalSubject`, e.g., `partner-b|employee-123`.
3. The user store manages `UserDetails.isEnabled()`, account lock/expiry, and `getAuthorities()`.
4. `verified.getName()` is a **durable subject within the registration namespace** per IdP contract. Otherwise, design a dedicated subject resolver/identity link.
5. The application uses Spring Security 7.x / OpenSAML 5; `Saml2AssertionAuthentication` exists since 7.0.

File `SamlUserMappingSecurityConfig.java`:

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider.ResponseToken;
import org.springframework.security.saml2.provider.service.authentication.Saml2AssertionAuthentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlUserMappingSecurityConfig {

    private static final Set<String> ALLOWED_IDPS =
            Set.of("corp", "partner-b");

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService localUsers) throws Exception {

        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        ResponseAuthenticationConverter defaults =
                new ResponseAuthenticationConverter();

        Converter<ResponseToken, Saml2Authentication> mapped =
                defaults.andThen(authentication -> {
                    if (!(authentication instanceof
                            Saml2AssertionAuthentication verified)) {
                        throw new BadCredentialsException(
                                "Missing SAML assertion context");
                    }
                    String registrationId =
                            verified.getRelyingPartyRegistrationId();
                    if (!ALLOWED_IDPS.contains(registrationId)) {
                        throw new BadCredentialsException(
                                "Unknown SAML registration");
                    }
                    String externalSubject = verified.getName();
                    if (externalSubject == null
                            || externalSubject.isBlank()) {
                        throw new BadCredentialsException(
                                "Missing stable external identity");
                    }

                    // Demo: UserDetailsService uses the "id|subject" namespace.
                    // Production: use a composite identity-link repository.
                    String lookupKey =
                            registrationId + "|" + externalSubject;
                    UserDetails user =
                            localUsers.loadUserByUsername(lookupKey);

                    if (!user.isEnabled() || !user.isAccountNonLocked()
                            || !user.isAccountNonExpired()) {
                        throw new DisabledException(
                                "Local account is inactive");
                    }

                    Saml2AssertionAuthentication result =
                            new Saml2AssertionAuthentication(
                                    user,
                                    verified.getCredentials(),
                                    user.getAuthorities(),
                                    registrationId);
                    result.setDetails(verified.getDetails());
                    return result;
                });

        provider.setResponseAuthenticationConverter(mapped);

        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health").permitAll()
                    .requestMatchers("/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .saml2Login(saml -> saml
                    .authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
~~~

**Step-by-step explanation:**

- `ResponseAuthenticationConverter defaults` handles default mapping, retaining provider-verified SAML data.
- `defaults.andThen(...)` appends user/role conversion **after** default mapping, never parsing unverified XML itself.
- `Saml2AssertionAuthentication` preserves the assertion accessor and `registrationId` in version 7.
- `ALLOWED_IDPS` is an illustrative allowlist; in production govern it via contractual IdP configuration.
- `UserDetailsService` supplies the local user and local authorities. It never turns `groups=ExternalAdmins` into `ROLE_ADMIN`.
- `DisabledException` blocks inactive accounts even when the IdP authenticated the user.
- `new ProviderManager(provider)` is crucial to ensure the filter uses the provider wired with your converter.
- `hasRole("ADMIN")` requires `ROLE_ADMIN` under the default prefix config; never bypassed automatically.
- `setDetails` preserves extra details if used by the framework/app, without altering `SecurityContext` or session policy.

**Runtime prerequisites:** this class requires a Spring Boot/Spring Security project with `spring-security-saml2-service-provider`, valid IdP metadata/credentials, and a valid `UserDetailsService` bean. It is **not a plain Java program** runnable with `javac`. Never register arbitrary Identity Providers from HTTP queries. On Spring Security 6.x only, change the API because `Saml2AssertionAuthentication` does not exist there yet.

**Security note on lookupKey:** concatenating `registrationId + "|" + externalSubject` is strictly illustrative. If identifiers can contain delimiters or complex qualifiers, ambiguity risks arise. In production, use a DB unique composite key holding registration/issuer/subject/qualifiers, and ensure the chosen SAML identifier is durable.

## 10. Changing the principal name from a SAML attribute

Scenario: the IdP sends a transient `NameID`, while the SP needs an immutable `employeeId` from `AttributeStatement`. Spring Security 7 provides:

~~~java
ResponseAuthenticationConverter converter =
        new ResponseAuthenticationConverter();

converter.setPrincipalNameConverter(assertion -> {
    // Extract employeeId per the IdP's contract.
    // Must verify exact Name/NameFormat and single-valued/non-blank constraints.
    return extractContractedEmployeeId(assertion);
});
~~~

This is a **design fragment**: `extractContractedEmployeeId` is a function the app must implement using OpenSAML Assertion APIs and the IdP contract. Do not copy this fragment as a complete program. If NameID is already a stable key guaranteed by the IdP, do not customize merely for cosmetic renaming.

When extracting an attribute as a principal key:

- Extract only from a validated assertion belonging to the chosen IdP.
- Know the exact attribute `Name`, `NameFormat`, and XML value type.
- If the attribute is missing, null, or has conflicting values: **fail closed**.
- Never auto-lowercase emails, or trim/truncate strings without an identity convention.
- Never assume two IdPs sharing an `employeeId` represent the same person.
- Include issuer + subject/qualifiers in the identity-link policy and audits.
- Test logic when the IdP changes formats/rotates issuers/updates employeeIds per workflow.

`setPrincipalNameConverter` customizes the **identity name**, whereas `setResponseAuthenticationConverter` lets you customize the **entire Authentication**, including principal, credentials context, and authorities.

## 11. Safe rules for mapping SAML groups to GrantedAuthority

Suppose IdP B sends `groups = [PortalReaders, ExternalAdmins]` inside a signature-verified AttributeStatement. SP A enforces this policy:

| Issuer / registration | External group | Internal authority |
| --- | --- | --- |
| `corp` | `REPORTS_VIEW` | `ROLE_REPORT_VIEWER` |
| `corp` | `REPORTS_EDIT` | `ROLE_REPORT_EDITOR` |
| `partner-b` | `PortalReaders` | `ROLE_REPORT_VIEWER` |
| `partner-b` | `ExternalAdmins` | Do not map |
| `partner-c` | `PortalReaders` | Map only if contract C allows |

**Principles:**

1. **Trust the right source:** use attributes only after SAML Response/Assertion verification against trusted IdP certificates.
2. **Scope by issuer:** two IdPs with matching group names do not automatically share roles.
3. **Allowlist:** unmapped external groups **grant no authorities**.
4. **Least privilege:** admin rights, creating/approving transactions, and data exports typically need local approval.
5. **Account status:** locked/disabled local users cannot log in even with valid IdP groups.
6. **Multi-tenant:** authenticated roles are only one input; check specific tenant membership and data permissions.
7. **Data types:** handle empty/multi-valued attributes and exact attribute namespaces; never guess with substring matches.
8. **Observability:** audit applied rules and local user IDs without logging entire Assertions.

Example of what not to write:

~~~java
// Do not auto-grant roles from a group without a policy.
new SimpleGrantedAuthority("ROLE_" + groupFromIdP);
~~~

A group named `ADMIN` managed by a partner for their own purposes **is not** `ROLE_ADMIN` in the SP application. If supporting group mapping, design policy `(issuer, attributeName, exactGroup) -> allowedLocalAuthority` and apply it only after issuer/signature verification.

## 12. Combining UserDetailsService with an identity-link service

`UserDetailsService#loadUserByUsername(String)` is convenient when a local username is already resolved; it does not take issuer/tenant as separate parameters. A clearer domain service could look like:

~~~java
public interface FederatedIdentityLinkService {
    LocalUser lookup(
            String verifiedRegistrationId,
            String verifiedIssuer,
            String verifiedStableSubject);
}
~~~

**This is an illustrative interface**, not a Spring API, and `LocalUser` must be defined by the application. A possible schema:

~~~text
federated_identity_link(
  registration_id,
  asserting_party_entity_id,
  external_subject,
  qualifier,
  local_user_id,
  tenant_id,
  status,
  PRIMARY/UNIQUE KEY(...)
)

local_user(
  user_id,
  enabled,
  locked,
  roles,
  membership
)
~~~

If the user is not found:

- **Fail closed**: reject with a neutral message, suitable for B2B systems requiring onboarding.
- **JIT provisioning**: create accounts only when permitted for that IdP/tenant, with anti-abuse controls, uniqueness constraints, minimal roles, auditing, and approvals as needed.

Never auto-link by email alone, never import external groups as admin, and never invoke a password verifier to "re-authenticate SAML" inside the converter. Identity verification belongs to the provider; the local service owns accounts and authorities.

## 13. Do Spring Security 5/6/7 differ at this step?

| Version | Commonly used provider/API | Notes when writing code |
| --- | --- | --- |
| Early Spring Security 5.x SAML2 | `OpenSamlAuthenticationProvider` and older OpenSAML APIs | Different converter/default signatures; do not copy 7.x code |
| Spring Security 6.0–6.4 | `OpenSaml4AuthenticationProvider` depending on release | Has `setResponseAuthenticationConverter`, yet verify token/constructor types |
| Spring Security 6.5 | Supports `OpenSaml5AuthenticationProvider` per OpenSAML config | `createDefaultResponseAuthenticationConverter()` deprecated; prefer nested `ResponseAuthenticationConverter` |
| Spring Security 7.x | `OpenSaml5AuthenticationProvider` and `ResponseAuthenticationConverter` | `Saml2AssertionAuthentication` and assertion accessor preferred |
| Preview/snapshot releases | May vary | Check Javadoc for the **exact version**; do not guess from tutorials |

In Spring Security 7, `Saml2AuthenticatedPrincipal` is deprecated in many API contexts; `Saml2ResponseAssertionAccessor` and `Saml2AssertionAuthentication` retain data needed for the SAML lifecycle. Therefore the legacy pattern:

~~~java
return new Saml2Authentication(
    myPrincipal,
    authentication.getSaml2Response(),
    myAuthorities
);
~~~

may no longer be ideal when using SLO because it drops the specialized authentication/accessor types. If forced to keep the legacy form for compatibility, test version behavior, SLO, and security context carefully.

Check actual dependency versions rather than guessing:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
~~~

Or Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Spring Security 5.x uses `javax.servlet`, whereas 6.x/7.x use `jakarta.servlet`. Check Spring Boot BOM, Spring Framework, and OpenSAML transitive dependencies to avoid class/method linkage errors.

## 14. Standalone Java 17: testing issuer/subject mapping and local roles

The pure Java snippet below **does not parse SAML XML or verify signatures**. It assumes fields in `VerifiedIdentity` were already checked by a trusted provider. The exercise solely proves **account/role linking policy** behaves properly and does not merge subjects across two IdPs.

Create `FederatedRoleMappingDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class FederatedRoleMappingDemo {
    record ExternalKey(String registrationId, String subject) {}
    record LocalAccount(String userId, boolean active, Set<String> roles) {}
    record VerifiedIdentity(
            String registrationId, String subject, Set<String> groups) {}

    static String map(
            VerifiedIdentity verified,
            Map<ExternalKey, LocalAccount> links) {

        LocalAccount local = links.get(new ExternalKey(
                verified.registrationId(), verified.subject()));

        if (local == null) {
            return "DENY: unlinked";
        }
        if (!local.active()) {
            return "DENY: inactive";
        }

        String roles = local.roles().stream()
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
        return "ALLOW " + local.userId() + " " + roles;
    }

    public static void main(String[] args) {
        Map<ExternalKey, LocalAccount> links = Map.of(
                new ExternalKey("corp", "employee-123"),
                new LocalAccount("u-001", true,
                        Set.of("ROLE_USER", "ROLE_EDITOR")),
                new ExternalKey("partner-b", "employee-123"),
                new LocalAccount("u-702", true,
                        Set.of("ROLE_REPORT_VIEWER")),
                new ExternalKey("partner-b", "disabled-7"),
                new LocalAccount("u-703", false,
                        Set.of("ROLE_USER")));

        System.out.println("Corp: " + map(
                new VerifiedIdentity("corp", "employee-123", Set.of()),
                links));

        System.out.println("Partner B: " + map(
                new VerifiedIdentity("partner-b", "employee-123", Set.of()),
                links));

        System.out.println("Unknown issuer: " + map(
                new VerifiedIdentity("partner-c", "employee-123", Set.of()),
                links));

        System.out.println("Disabled: " + map(
                new VerifiedIdentity("partner-b", "disabled-7", Set.of()),
                links));

        System.out.println("External admin ignored: " + map(
                new VerifiedIdentity("partner-b", "employee-123",
                        Set.of("ExternalAdmins")),
                links));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac FederatedRoleMappingDemo.java
java FederatedRoleMappingDemo
~~~

**Exact stdout:**

~~~text
Corp: ALLOW u-001 [ROLE_EDITOR, ROLE_USER]
Partner B: ALLOW u-702 [ROLE_REPORT_VIEWER]
Unknown issuer: DENY: unlinked
Disabled: DENY: inactive
External admin ignored: ALLOW u-702 [ROLE_REPORT_VIEWER]
~~~

**Explanation:**

- `employee-123` from `corp` and `partner-b` maps to **two separate accounts**.
- `partner-c` has no link, so **DENY**.
- User `disabled-7` is denied even though an external identity exists.
- Group `ExternalAdmins` cannot inject `ROLE_ADMIN`; roles come from the local account.
- Sorting the `Set` keeps stdout deterministic across all compatible JDKs.

**Limitations:** this program omits issuer certificate checks, SAML signatures, audience, recipient, NotBefore/NotOnOrAfter, InResponseTo, request state, replay, and sessions. In a real app, `VerifiedIdentity` is constructed only from **verified** provider output; never use this record as proof from an HTTP client.

## 15. Common security mistakes

### Mistake A — Expanding privileges from external groups

A partner IdP emits `groups=ADMIN`. If the converter grants `ROLE_ADMIN` from the group string, users gain privileges unapproved by the SP. Fix: per-registration/issuer allowlist, local approvals, least privilege, resource permission checks.

### Mistake B — Using email as a global key

The same email may appear in IdP B and C or be reassigned. Fix: composite key combining trusted issuer, immutable subject, and appropriate qualifiers; reviewed account linking.

### Mistake C — Converter never actually used by AuthenticationManager

The app registers a converter bean without wiring it into the provider inside the chain; output remains `ROLE_USER`. Fix: check `setResponseAuthenticationConverter`, `ProviderManager`, `saml2Login.authenticationManager`, and `SecurityFilterChain` request matchers.

### Mistake D — Replacing validation with mapping

A developer disables `ResponseValidator` or `AssertionValidator` to make login "pass" after switching IdPs. Fix: correct metadata, issuer, ACS, certificates, or clock skew; never strip security checks.

### Mistake E — Losing SAML Single Logout context

A custom converter replaces `Saml2AssertionAuthentication` with `UsernamePasswordAuthenticationToken` or plain `Saml2Authentication`. Fix: preserve the assertion accessor and registration ID in Security 7; test SLO/NameID/SessionIndex.

### Mistake F — Not checking disabled users

The IdP still authenticates someone whose access was revoked by the SP organization. Fix: verify internal status during mapping and enforce session revocation/TTL after login.

### Mistake G — Stale roles in session

Roles are cached in `SecurityContext` at login while the user's rights are later revoked. Fix: TTL/refresh and service-layer permission checks on sensitive operations.

### Mistake H — Logging sensitive assertions

`getSaml2Response()` can contain XML with NameID, employee data, and session info. Fix: log only registration ID, local user ID, correlation ID, and concise error codes; never log raw Responses, credentials, or private keys.

## 16. Testing the converter properly

Testing should cover three layers:

**Layer 1 — Unit mapping:** test identity and permission linking functions assuming trusted inputs. This is the layer `FederatedRoleMappingDemo` illustrates.

**Layer 2 — Provider integration:** use a lab IdP or real signed SAML fixtures to verify XML signature/issuer/audience/recipient/timestamp checks, then verify the converter produces the expected principal and authorities.

**Layer 3 — End-to-end authorization:** browser logs in via the IdP, session is established, requests to URLs and tenant resources are allowed/denied per policy; test logout, caching, and key rotation as needed.

| Test | Input | Expected |
| --- | --- | --- |
| Valid local identity | partner-b + employee-123 | Correct localUserId and `ROLE_REPORT_VIEWER` |
| Same subject, different IdP | corp + employee-123 | Never mixed with partner-b |
| Unknown registration | undeclared partner-c | Fail closed |
| Missing immutable subject | required NameID/attribute missing | Fail closed |
| Disabled/locked | Linked user is inactive | Login does not succeed |
| External admin group | `ExternalAdmins` | Does not grant `ROLE_ADMIN` |
| Approved group mapping | `PortalReaders` from B per allowlist | Correct approved role |
| Invalid signature | Tampered Assertion | Provider rejects |
| Wrong issuer | Response from IdP C at registration B | Reject |
| Wrong audience | Assertion for another SP | Reject |
| Wrong recipient | Response aimed at another ACS | Reject |
| Expired assertion | Past `NotOnOrAfter` | Reject |
| Incorrect `InResponseTo` | Mismatched AuthnRequest | Reject per SP-initiated policy |
| Replay | Resubmit already-used Response | Do not create unauthorized session |
| Tenant authorization | User B views C's data | HTTP 403 |
| Single Logout | Logout after custom mapping | Preserves assertion accessor and issuer |
| Role revoked | Local authority revoked | Session/refresh policy takes effect |

**A unit test manually instantiating `Saml2Authentication` does not prove SAML login is secure.** It only tests post-authentication app logic. Confirming federation correctness requires end-to-end signed SAML tests with a registered IdP.

## 17. Customizing users by IdP and tenant

In multi-organization federation, the same `NameID` can appear across multiple issuers. The converter must know which registration the user came from to resolve the right local account; roles are then further bounded by tenant.

A sound policy:

~~~text
Trusted IdP:
  partner-b -> issuer B -> tenant-b
  partner-c -> issuer C -> tenant-c

Verified Identity:
  registration = partner-b
  subject = employee-123

Local link:
  (partner-b, employee-123) -> user u-702
  u-702 is ACTIVE
  u-702 tenantMembership = tenant-b

Authorities:
  [ROLE_REPORT_VIEWER]

Request:
  GET /tenants/tenant-c/orders/991

Decision:
  authenticated = true
  role valid = true
  tenant/resource ownership = false
  -> 403 Forbidden
~~~

Clearly separate **authentication success** from **authorization success**. The converter must not open all resources based on IdP group attributes. In Spring Security, combine `authorizeHttpRequests`, `@PreAuthorize`, service-level checks, and data access filters.

When IdPs change NameID format/issuer or use JIT provisioning, establish an identity-link migration workflow and duplicate-prevention tests; never swap principal converters expecting old records to match automatically.

## 18. Error model and operations

When users cannot log in after adding a converter, isolate the failing layer:

1. **Before converter:** bad signature, wrong IdP issuer, missing registration, wrong ACS/recipient, mismatched audience, expired assertion, missing request state. Fix federation config, not local roles.
2. **Inside converter:** local user not found, account disabled, unmapped group, unstable identity key, identity-link repository failure. Fix policy/data mapping.
3. **After converter:** authenticated user has roles yet gets 403 on resources, session cookie lost, stale roles, broken SLO. Fix authorization/session management.

Emit balanced telemetry: verified registrationId, error code, localUserId, ruleId, correlation ID, UTC timestamp, and outcome. Never emit raw SAMLResponses or certificate private keys into production logs.

Particularly with `UserDetailsService`, handle `UsernameNotFoundException` with a neutral message without revealing whether specific accounts exist. When the local user store is unreachable, never default to letting users log in role-less or auto-creating admin accounts. Fail closed and monitor.

## 19. Production deployment checklist

- [ ] Exact Spring Boot/Security/OpenSAML versions confirmed.
- [ ] Difference between request converter and response authentication converter understood.
- [ ] Converter is wired onto the actual `OpenSaml5AuthenticationProvider` used by `saml2Login`.
- [ ] Default converter is delegated to when custom SAML parsing is unnecessary.
- [ ] Signature, issuer, audience, recipient, timing, correlation, and replay validations remain intact.
- [ ] External identity key includes IdP/registration namespace and an appropriate immutable subject.
- [ ] Local account is linked, active, unlocked, and belongs to a valid tenant.
- [ ] Authorities come from approved sources/allowlists, never copied from IdP admin groups.
- [ ] `Saml2AssertionAuthentication`/assertion accessor preserved on Security 7 if using SLO.
- [ ] SAMLResponse, assertions, and credentials are never logged.
- [ ] Unit tests cover mapping collisions for same subject across different IdPs.
- [ ] Integration tests cover signature/issuer/audience/recipient/expiration/replay.
- [ ] Authorization tests verify 403 on mismatched roles or tenants.
- [ ] Offboarding/session revocation/role refresh take effect per policy.
- [ ] Auditing, metrics, and rollback plans exist for converter changes or major upgrades.

## 20. Official documentation

1. [Spring Security 7.1 — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): section **Converting an Assertion into an Authentication**, `setResponseAuthenticationConverter`, local users, and authority mapping.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): filter → token converter → provider → Authentication chain.
3. [Spring Security 7 — SAML Migration Guide](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/saml2.html): preferring `Saml2AssertionAuthentication` and `Saml2ResponseAssertionAccessor`.
4. [Javadoc — Saml2AssertionAuthentication](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html): constructor for principal, accessor, authorities, and registrationId.
5. [Spring Security 6.5 Deprecated API](https://javadoc.io/static/org.springframework.security/spring-security-saml2-service-provider/6.5.0/deprecated-list.html): `createDefaultResponseAuthenticationConverter` deprecated in favor of `ResponseAuthenticationConverter`.
6. [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): meaning of `GrantedAuthority`, `ROLE_` prefix, and policies.
7. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): checking permissions at services/methods after SAML login.

**Key takeaway:** the `AuthenticationProvider` response converter bridges **verified SAML identity** and **application principal/authorities**. Use it to grant exact privileges per local policy, never replacing or weakening validation. On Spring Security 7, preserve `Saml2AssertionAuthentication` with its assertion accessor to keep SAML context intact; always separate the IdP's authentication role from the SP's responsibility to authorize resource access.