# Normalizing Names, Emails, and Groups Across Different IdPs

> **Topic:** Spring Security – federation. **Knowledge group:** Identity and authorities. This lesson builds a unified model for transforming identity data from multiple OpenID Providers (OIDC), SAML Identity Providers (IdPs), and other federated sources into an **internal user profile** and **application permissions** without conflating names/emails/groups across independent systems.

## 1. The problem and the most important principle

An enterprise may connect a Spring application to multiple identity providers: an employee IdP, partner IdP, Azure/Entra ID, Keycloak, Okta, or a legacy SAML system. The same user might receive data like:

```text
OIDC IdP A:
  iss             = https://login-a.example.org/realms/staff
  sub             = user-8f9
  name            = "Nguyễn Thị Lan"
  email           = "Lan@Example.ORG"
  email_verified  = true
  groups          = ["finance-read", "project-x"]

OIDC IdP B:
  iss             = https://accounts-b.example.net
  sub             = "person-1007"
  preferred_username = "lan.nguyen"
  given_name      = "Lan"
  family_name     = "Nguyễn"
  email           = "lan@example.org"
  email_verified  = false
  roles           = ["Accounting.View"]

SAML IdP C:
  IdP entityID    = https://sso.partner.example.edu/issuer
  NameID          = "u-7481"
  NameID Format   = persistent
  Attributes:
    displayName   = ["Nguyễn Thị Lan"]
    mail          = ["lan@example.org"]
    memberOf      = ["CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu"]
```

These fields **do not allow concluding that the three logins belong to one person**, even though the names and emails look alike. Each IdP has its own rules for issuing identifiers, managing emails, updating groups, and handling account lifecycles. If an application merges accounts by email or trusts any group named `admin`, an attacker can take over an account or escalate privileges via an IdP with lower assurance.

**The normalization system must separate four concepts:**

1. **Verified identity source:** Issuer, tenant, protocol, trusted certificates/keys, and active registration.
2. **Immutable identifier key within the source's scope:** OIDC `iss + sub`; SAML NameID/contractually stable identifier; never use email as a primary key.
3. **Display/contact profile attributes:** Full name, given/family name, email, email verification status, locale. These may change over time.
4. **Internal application permissions:** Permissions/roles decided by the application after **controlled mapping** from external groups/roles and business authorization checks.

Desired outcome: a `CanonicalIdentity` record with a stable identifier, per-field provenance, a safe display profile, and the **least-privilege permission set required**. Out-of-contract data is ignored or rejected, never becoming authority automatically.

## 2. Why manage the "source" before normalizing data?

### 2.1. Every claim must have context

For **OIDC**, the Relying Party (RP) application validates the ID Token: OP signature, `iss`, `aud`, expiration, and necessary `nonce`/flow checks. Under OIDC Core, only the `iss + sub` pair carries a stable identifier guarantee within the issuer's scope; `name`, `preferred_username`, and `email` have no guarantee of uniqueness or non-reassignment.

For **SAML 2.0 Web SSO**, the Service Provider (SP) checks SAMLResponse/Assertion, IdP source, signature, `AudienceRestriction`, `Recipient`, `Destination`, timestamps, and replay. After verification, `Saml2AuthenticatedPrincipal` allows reading NameID and processed attributes. However, **NameID is not automatically a permanent key**: `transient` is temporary; `persistent` is designed to be stable per link yet depends on IdP policy; `emailAddress` is not an immutable identifier.

With CAS or an identity broker, principal names/attributes may likewise only be used after verifying the ticket or assertion from a **trusted server**. When a broker translates SAML into OIDC, distinguish the **actual downstream token issuer (the broker)** from the upstream identity the broker declares; never let a client-supplied `upstream_issuer` claim dictate trust.

**Authenticated input can still carry claims not trustworthy enough to grant permissions.** A valid signature proves the IdP issued a claim; it does not prove every claim has the same assurance level, freshness, and semantics across providers.

### 2.2. Source identity should be configured, not guessed from input

Each connection needs a configuration record:

| Field | Example | Rule |
| --- | --- | --- |
| `providerKey` | `staff-a`, `partner-b` | System-managed configuration key, not user-selected input |
| `protocol` | `OIDC` or `SAML2` | Selects the appropriate validation mechanism |
| `issuer` / IdP entityID | `https://login-a.example.org/realms/staff` | Exact match against registered source |
| `registrationId` | `staff-a` | Links Spring registration to IdP policy |
| `tenant` / realm | `staff` | Restricts which attributes the tenant may assert |
| `subjectSource` | `sub` or approved persistent NameID/employee ID | Never use arbitrary email/username |
| `displayNameClaim` | `name` or SAML OID `displayName` | Display purposes only |
| `emailClaim` and verification state | `email` + `email_verified` or external verification flow | Must not be used to auto-link accounts |
| `groupClaim` / attribute | `groups`, `roles`, SAML `memberOf` | Exact agreed schema and path |
| `groupMappingVersion` | `v3` | Audits permission policy changes |

Never accept tokens from arbitrary issuers simply because their JWT structure matches. With multiple IdPs, resolve the approved registration first and verify using the trusted keys **of that matching issuer**, rather than trusting `iss`/`kid`/`jku` declared by an unverified token and fetching keys from arbitrary URLs.

## 3. Designing the canonical profile: identity, contact, and permissions are three separate zones

A suitable internal schema:

```text
CanonicalIdentity
  localAccountId: UUID (issued by the application, not derived from email)
  externalIdentifiers[]:
    - providerKey: "staff-a"
      issuer: "https://login-a.example.org/realms/staff"
      subject: "user-8f9"
      protocol: "OIDC"
      tenant: "staff"
      verifiedAt: ...
      linkStatus: VERIFIED
  profile:
    displayName: "Nguyễn Thị Lan"
    givenName: "Lan"
    familyName: "Nguyễn"
    emailDisplay: "Lan@example.org"
    emailVerifiedBy: "staff-a"
    emailVerificationAt: ... (if provided by the system)
    locale: "vi-VN"
  entitlements:
    - REPORT_READ
    - PROJECT_X_VIEW
  audit:
    mappingVersion: "v3"
    lastIdentitySync: ...
    attributeSources: ...
```

**Only `localAccountId`** serves as the internal primary key for business data. `externalIdentifiers` has a unique constraint by source and identifier, such as `(provider_key, issuer, subject, tenant/qualifiers if part of the model)`. In OIDC, the protocol-standard pair is `iss + sub`; storing `providerKey`/`tenant` binds operational configuration without stripping meaning from that pair. In SAML, store NameID Format, NameQualifier, SPNameQualifier, or an agreed immutable attribute whenever they affect uniqueness/stability.

**One person can have multiple external identifiers**, yet binding them to a single `localAccountId` must be an **evidenced, properly authenticated account-linking workflow**, not a join on two rows sharing an email.

Separate data provenance by policy:

- `displayName` is for UI display; render safely with fallbacks.
- `emailDisplay` is for contact only when permitted; email is not an access permission.
- `roles/permissions` are decided by **application policy**; never turn any claim named `roles` into `ROLE_ADMIN` automatically.
- `accountStatus`/`disabled` may come from an authoritative HR/SCIM/directory source, never inferred from a missing claim during one login.
- An IdP's internal `userId` is not always identical to `sub`; distinguish management-API IDs from the identifier published to RPs.

## 4. Normalizing personal names: preserve cultural identity and never use names for identification

### 4.1. Common fields

OIDC provides standard claims such as `name`, `given_name`, `family_name`, `middle_name`, `nickname`, `preferred_username`, and `locale`. They may be absent. IdP A and IdP B need not supply the same completeness; if the app requires a display name, define a per-source priority order.

In SAML, commonly seen attribute names include:

| Meaning | Common SAML Attribute Name | Notes |
| --- | --- | --- |
| Display name | `urn:oid:2.16.840.1.113730.3.1.241` or `displayName` | Both are implementation conventions, **not emitted by every IdP** |
| Given name | `urn:oid:2.5.4.42` | Requires matching metadata/attribute contract |
| Surname | `urn:oid:2.5.4.4` | Do not assume display ordering works for all countries |
| Email | `urn:oid:0.9.2342.19200300.100.1.3` or `mail` | Does not prove email is verified by itself |
| Group membership | `memberOf`, OID/URI, or partner-declared name | May be DN, GUID, or a list |

An IdP may issue an Attribute `Name` as a URN and `FriendlyName` solely for human reading. SPs should map by the **agreed Attribute Name/NameFormat** rather than relying solely on FriendlyName, since FriendlyName may be non-unique or change.

### 4.2. Practical rules

1. Only read identity claims after SAML/OIDC validation succeeds.
2. Define priority order per IdP: e.g., `name` when trusted and present, otherwise assemble `given_name` and `family_name` per locale/product rules. For Vietnamese, many users prefer **family – middle – given** order; do not mechanically swap them based on English "first/last name".
3. Normalize Unicode to **NFC** for consistent display/search; preserve Vietnamese diacritics and valid spaces. Avoid blanket `NFKC` if it alters character semantics undesirably.
4. Trim leading/trailing whitespace and sanitize length/control characters in the UI. **Never strip diacritics** like turning `Nguyễn` into `Nguyen` for the canonical profile.
5. Never use `name`, `displayName`, `preferred_username`, or first/last name pairs to search/merge accounts. Names collide easily and change.
6. Avoid unnecessary logging of PII/attributes. In HTML UIs, always output-encode/prevent injection per framework; string normalization **does not replace** HTML escaping.
7. If name is missing, use a neutral label like "User" or a non-sensitive internal label; do not expose email or `sub` automatically if privacy policy forbids it.

**Distinction example:** `"Nguyễn"` can be encoded with different Unicode code points yet render identically. NFC helps unify comparisons for **search/display**; it still never turns a name string into an identity key.

### 4.3. Multilingual state and profile updates

The `locale` claim helps choose date/time/name formatting rules, not verify nationality or origin. When an IdP changes a name, the app may sync it to the profile depending on each source's authority, while recording timestamp/source and avoiding overwriting a user-chosen name if product rules forbid it. For names on legal documents, use a **separate authoritative source**; an SSO token name is not automatically a document-verified legal name.

## 5. Normalizing email: display differs from verification differs from identity

### 5.1. OIDC fields and semantic limits

OIDC defines `email` and `email_verified`. `email_verified = true` means the OP performed an email control check under its policy at the time of verification. It is **not a permanent guarantee** that the user still owns the mailbox or that the email is exclusively assigned to them; nor is it authorization to attach to an internal account sharing that email.

If `email_verified` is absent or `false`, treat the status as **unverified** in OIDC-based flows, never flipping it to true just because the user logged in. In SAML, a `mail` attribute has no standard verification flag across all IdPs; mark it verified only with an **explicit trust contract/proof** confirming the IdP verifies mailboxes.

**Three states to separate:**

| Status | Meaning | Permitted usage |
| --- | --- | --- |
| `emailPresent` | IdP provided an email-like string | Can display if valid and permitted by policy |
| `emailVerified` | Authoritative source verified control per contract | Can use for notifications/recovery per policy; never auto-link accounts |
| `emailPrimaryForContact` | User/org selected a primary contact address | A product choice, independent of the `iss + sub` identity key |

**Do not equate** email as a login claim, email as a notification address, email as a username, and email as a principal ID. A mailbox can be a shared alias; a user can change company domains; old emails can be reassigned to someone else.

### 5.2. Safe normalization practices

- `strip` leading/trailing whitespace from config artifacts; do not arbitrarily alter the interior of the address.
- You may **lowercase the domain part** after `@` using proper rules and handle IDN/Punycode domains where supported; the local-part can technically be case-sensitive under email standards. Do not force-lowercase the entire address as a universal identity rule.
- Do not strip dots or `+tag` suffixes in the local-part. Transformations like "Gmail dot/plus insensitivity" are provider-specific and can cause wrongful merges on other domains.
- Use a product-appropriate email parser/validator (accounting for Unicode/EAI and mail-sending policies), rather than a naive regex to decide which account gets linked.
- Check email syntax and length per policy, blocking control characters/header injection before sending mail; sanitize logs.
- Store both the source-provided value and normalized value for **search/contact purposes**, alongside source, timestamp, and verification state. Never use canonical email as a system-wide unique user key.
- Email data remains PII; avoid placing it in URLs, cookies, unnecessary access tokens, or logs.

**Example:**

```text
Received value:    "  Lan@Example.ORG  "
Display email:     "Lan@example.org"
Verified?          Only if the source has corresponding proof.

Other value:       "lan@example.org"
Do not conclude:   "Lan@..." and "lan@..." belong to the same account.
Do not conclude:   "lan+finance@example.org" is the same as "lan@example.org".
```

### 5.3. Account linking: conditions must be stricter than email matching

Suppose internal account `localAccountId=123` is already linked to OIDC A, and the user logs in via SAML B whose `mail` matches the current email. The application **must not auto-link** SAML B to account 123 based on email alone; require a workflow:

1. The user has a **strongly authenticated session** on the internal account or an already-linked external identifier.
2. The user explicitly initiates adding source B.
3. Complete federation login with B, verifying B's exact issuer/certificate/NameID or immutable identifier.
4. Assess risk/step-up, confirming the user controls both the current account and the new identity; for privileged accounts, require additional approval.
5. Block if external identifier B is already linked to another account; never "steal/transfer" links automatically.
6. Write link/unlink audit logs (source, hashed/redacted subject key, timestamp, actor, verification method) and notify the account owner per policy.
7. Enforce unique constraints and transactions to prevent concurrent requests from mis-linking.

This is a key NIST federation account-linking recommendation: binding identities must be protected by an authenticated session, not merely matching emails.

## 6. Normalizing groups/roles: matching names do not prove matching authority

### 6.1. Reality of group sources

| Source | Common claim/attribute | Shape | Warning |
| --- | --- | --- | --- |
| OIDC IdP A | `groups` | `["finance-read","operations"]` | `groups` is not a mandatory OIDC Core standard claim; may reside only in UserInfo |
| OIDC IdP B | `roles`, `realm_access.roles` | list of strings or nested objects | Vendor-specific schema; exact path must be declared |
| SAML IdP C | `memberOf`, `groups`, `Role`, or OID/URI | list of DNs, GUIDs, strings | Can have multiple AttributeValues with varying lengths/encodings |
| Broker | `upstream_groups` or `app_roles` | mapped claim issued by broker | Trust only within the scope delegated to the broker |
| SCIM/HR directory | out-of-band group membership | background-synced membership or entitlement | Evaluate freshness, authoritative source, and revocation |

A group named `Admins` from a partner IdP **does not mean** `ROLE_ADMIN` inside the internal app. Even within the same IdP, tenant A's `Admins` differs from tenant B's. Always evaluate **issuer + tenant + group identifier** and the policy mapping to internal permissions.

### 6.2. Source-scoped allowlist mapping policy

Example contract:

| Verified provider | Exact external group ID | Internal permission | Scope |
| --- | --- | --- | --- |
| `staff-a` (staff issuer) | `finance-read` | `REPORT_READ` | Staff reports only |
| `staff-a` | `approvers-v2` | `REPORT_APPROVE` | Must scope by record/unit |
| `partner-b` (partner issuer) | `CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu` | `REPORT_READ` | Only data shared with partner |
| `partner-b` | `CN=Admins,OU=Apps,...` | **Do not map** | Never auto-grant internal admin |
| Other issuer/unknown claim | `admin` or any other string | **Do not map** | Fail closed |

If the IdP provides GUIDs/immutable group IDs, prefer stable IDs over display names or distinguished names that change when groups move OUs. When an IdP only emits DNs/strings, document rename procedures and version the mapping; never use `toLowerCase`, `contains("admin")`, or arbitrary string splitting. Permission governance must be approved by the application owner, **not solely by a partner IdP administrator**.

### 6.3. Least privilege and defense in depth

- **Default deny:** missing, malformed, or non-allowlisted groups → grant no new business permissions. Successful authentication never implies `REPORT_READ` or `ROLE_ADMIN`.
- **Action-oriented permissions:** prefer granular permissions like `REPORT_READ`, `REPORT_APPROVE`, `USER_MANAGE` over mapping every string into an overly broad role.
- **Resource-level authorization:** having `REPORT_READ` still requires checking which **specific report** the user/tenant may read.
- **Authoritative source for high privilege:** sensitive roles may require internal decisions or dual-source/step-up verification, not a single external group.
- **Freshness:** membership inside an ID Token/SAML Assertion is a point-in-time snapshot; when a user is removed from a group at the IdP, an open Spring session may retain stale authorities. Use session timeouts, re-authentication, revocation, back-channel provisioning/deprovisioning, or per-request permission checks per policy.
- **MFA does not replace entitlements:** `amr`/`acr` claims reflect authentication context (if trusted), not business authorization.
- **Never trust browser claims:** never accept `X-Groups`, localStorage, or form fields as permission grounds without authoritative backend verification.

**Distinguish roles from scopes:** In OIDC login, `SCOPE_profile` or `SCOPE_email` are OAuth client-requested scopes, **not employee groups**. Application `ROLE_ADMIN` must come from approved mapping or local policy, never inferred from scopes.

## 7. Normalization pipeline to build in the application

```text
      OIDC ID Token/UserInfo        SAML Response/Assertion
         (OP A, OP B)                 (IdP C)
                |                        |
                v                        v
          OIDC Validation           SAML Validation
          iss/aud/signature         issuer/signature/
          exp/nonce/claims          audience/recipient/time
                |                        |
                +-----------+------------+
                            |
                            v
                  Trusted Source Context
                   issuer, registrationId,
                   tenant, protocol, subject
                            |
                            v
                    Attribute Extractor
                name/email/verification/groups
                            |
                            v
                    Normalization Layer
                  unicode/profile/email forms
                            |
                            v
                   Source-specific Mapper
                  exact group IDs => permissions
                            |
                            v
                     Account Resolver
              stable external key => localAccountId
                      (link only by policy)
                            |
                            v
                   Authorization Layer
              permission + tenant + object rights
                            |
                            v
                     Application Data
```

**Key architecture rule:** Authenticate **first**, normalize **after**. The mapper must never receive raw JWTs or unchecked XML from an HTTP request. It must receive data already verified by Spring Security, paired with trusted registration/issuer context. Also bound claim/attribute **length and count** to prevent DoS and preserve consistency.

### 7.1. Canonical model

In code/business logic, split cleanly:

```text
VerifiedExternalIdentity:
  sourceKey             // resolved from trusted configuration
  subject               // OIDC sub, or SAML persistent identifier
  claims                // verified subset
  authenticationTime
  assuranceContext      // when IdP and contract allow interpretation

CanonicalProfile:
  displayName
  emailForDisplay
  emailVerificationState
  locale

CanonicalEntitlements:
  applicationPermissions
  tenantScope
  policyVersion
  evaluatedAt
```

If an important attribute claim is missing, do not guess from username/NameID strings; display a fallback if needed, **without granting corresponding permissions**. When data comes from multiple sources linked to one local account, define a **per-field precedence policy**, e.g., work email from HR directory while displayName is user-chosen; never use "last login wins everything" where a lower-trust partner could overwrite sensitive attributes.

### 7.2. Active synchronization vs. login-time sync

- **Just-in-Time (JIT) provisioning:** creates profiles on first successful login; easy to adopt, but detects deprovisioning late. Unique constraints are mandatory.
- **SCIM/directory sync:** updates, locks, or revokes entitlements via an out-of-band management channel; verify source authority and handle out-of-order events.
- **Login-time refresh:** refreshes profile/groups from claims at each login; permissions can go stale inside the session until next login.
- **Just-in-time authorization:** for sensitive actions, check permissions against an authoritative store per request or periodically; add tenant/object checks.

Choose the model based on risk. Never call an external API on every request without timeouts/caching/error policy; when the group source is unreachable, fail closed appropriately. More importantly, **authorization decisions must carry expiration and policy versions**.

## 8. Standalone Java 17+ example: canonicalizing data and groups

The following example uses only Java 17 standard libraries, without Spring. It models the step **after the IdP has been verified**. `sourceKey` comes from an approved configuration table, not a self-declared user string.

File `FederatedNormalizationDemo.java`:

```java
import java.net.IDN;
import java.text.Normalizer;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class FederatedNormalizationDemo {

    record ExternalKey(String sourceKey, String subject) { }

    record VerifiedIdentity(
            String sourceKey,
            String subject,
            String displayName,
            String email,
            boolean emailVerified,
            List<String> groups) { }

    record CanonicalIdentity(
            ExternalKey key,
            String displayName,
            String emailDisplay,
            boolean emailVerified,
            Set<String> permissions) { }

    private static final Map<String, Map<String, String>> GROUP_MAPPING =
        Map.of(
            "staff-a",
            Map.of(
                "finance-read", "REPORT_READ",
                "approvers-v2", "REPORT_APPROVE"),
            "partner-b",
            Map.of(
                "CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu",
                "REPORT_READ"));

    private static String normalizeDisplayName(String value) {
        if (value == null || value.isBlank()) {
            return "User";
        }
        return Normalizer.normalize(value.strip(), Normalizer.Form.NFC);
    }

    // For lab display only; NOT an RFC email parser.
    private static String normalizeDisplayEmail(String value) {
        if (value == null || value.isBlank()) {
            return "";
        }
        String trimmed = value.strip();
        int at = trimmed.lastIndexOf('@');
        if (at < 1 || at >= trimmed.length() - 1) {
            return "";
        }
        String local = trimmed.substring(0, at);
        String domain = trimmed.substring(at + 1);
        try {
            return local + "@" +
                IDN.toASCII(domain).toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException invalidDomain) {
            return "";
        }
    }

    static CanonicalIdentity normalize(VerifiedIdentity identity) {
        if (identity == null
                || !GROUP_MAPPING.containsKey(identity.sourceKey())
                || identity.subject() == null
                || identity.subject().isBlank()) {
            throw new IllegalArgumentException(
                "Unknown source or missing immutable subject");
        }

        Map<String, String> allowed =
            GROUP_MAPPING.get(identity.sourceKey());
        Set<String> permissions = new TreeSet<>();

        // Do not trust groups outside the allowlist; do not grant default permissions.
        for (String rawGroup : identity.groups()) {
            String mapped = allowed.get(rawGroup);
            if (mapped != null) {
                permissions.add(mapped);
            }
        }

        return new CanonicalIdentity(
            new ExternalKey(identity.sourceKey(), identity.subject()),
            normalizeDisplayName(identity.displayName()),
            normalizeDisplayEmail(identity.email()),
            identity.emailVerified(),
            Set.copyOf(permissions));
    }

    public static void main(String[] args) {
        VerifiedIdentity a = new VerifiedIdentity(
            "staff-a", "user-8f9", "  Nguyễn Thị Lan  ",
            "Lan@Example.ORG", true,
            List.of("finance-read", "ops-admin"));

        VerifiedIdentity b = new VerifiedIdentity(
            "partner-b", "person-1007", "Nguyễn Thị Lan",
            "lan@example.org", false,
            List.of("CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu",
                    "CN=Admins,OU=Apps,DC=partner,DC=example,DC=edu"));

        CanonicalIdentity first = normalize(a);
        CanonicalIdentity second = normalize(b);

        System.out.println("firstKey=" +
            first.key().sourceKey() + ":" + first.key().subject());
        System.out.println("firstName=" + first.displayName());
        System.out.println("firstEmail=" + first.emailDisplay());
        System.out.println("firstVerified=" + first.emailVerified());
        System.out.println("firstCanRead=" +
            first.permissions().contains("REPORT_READ"));
        System.out.println("firstIsAdmin=" +
            first.permissions().contains("ADMIN"));
        System.out.println("samePersonByKey=" +
            first.key().equals(second.key()));
        System.out.println("secondCanRead=" +
            second.permissions().contains("REPORT_READ"));
        System.out.println("secondIsAdmin=" +
            second.permissions().contains("ADMIN"));
        System.out.println("secondEmailVerified=" +
            second.emailVerified());
    }
}
```

Compile and run from the file's directory:

```bash
javac --release 17 FederatedNormalizationDemo.java
java FederatedNormalizationDemo
```

Deterministic stdout:

```text
firstKey=staff-a:user-8f9
firstName=Nguyễn Thị Lan
firstEmail=Lan@example.org
firstVerified=true
firstCanRead=true
firstIsAdmin=false
samePersonByKey=false
secondCanRead=true
secondIsAdmin=false
secondEmailVerified=false
```

**Output explanation:** Both accounts have similar displayNames and emails, yet different `ExternalKey`s; no auto-linking occurs. IdP B has a group containing `Admins`, but no mapping exists, so it receives no ADMIN permission. B's `emailVerified` remains false despite matching A's email.

**Production limitations and prerequisites:**

- `sourceKey` in the example represents an issuer/registration already verified by the backend; production must store actual issuer + subject + tenant/qualifiers as designed in Section 3.
- `normalizeDisplayEmail` demonstrates domain casing and IDN, **not a full RFC 5322/EAI email parser**. Never use it to assert email validity, send mail, or link accounts without a real validator and verification policy.
- `Set.copyOf` only preserves deduplicated contents, **not iteration order**. The example avoids printing the set directly to prevent JVM-dependent stdout differences. Use `TreeSet` when sorted permissions are needed for reporting.
- Real systems must bound lengths, drop unknown claims, control invisible/control characters in display data, normalize separately for search, and HTML-escape output. Never use `Normalizer.Form.NFC` as an authentication mechanism.
- Not all SAML NameIDs are stable. `subject` in the example may only be supplied after the issuing source has been verified **and** stability is confirmed by contract.
- Each mapping version needs an owner/approval; updating a mapping must not leave old sessions holding elevated privileges indefinitely.
- If `groups` input is null or mismatches schema, production must validate shape and fail closed; the example assumes data was already extracted into a safe list.

## 9. Spring Security integration: OIDC authorities and SAML attributes

### 9.1. OIDC: `GrantedAuthoritiesMapper` for trusted sources

In Spring Security Servlet OAuth2/OIDC Login, `OidcUserAuthority` holds the ID Token and UserInfo processed by the framework; `GrantedAuthoritiesMapper` can translate group claims into internal authorities. Only emit authorities when the issuer is in the configured list and the claim has the expected structure.

Example in a Spring Boot 3+/Spring Security 6+ app, Java 17+; file `src/main/java/com/example/federation/OidcRoleConfig.java`:

```java
package com.example.federation;

import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Configuration
public class OidcRoleConfig {

    private static final String STAFF_ISSUER =
        "https://login-a.example.org/realms/staff";

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return input -> {
            Set<GrantedAuthority> result = new HashSet<>();

            for (GrantedAuthority authority : input) {
                if (!(authority instanceof OidcUserAuthority oidc)) {
                    continue;
                }
                String issuer = oidc.getIdToken().getIssuer().toString();

                if (!STAFF_ISSUER.equals(issuer)) {
                    continue;
                }

                // groups is an IdP-specific claim per agreement.
                Object raw = oidc.getIdToken().getClaims().get("groups");
                if (!(raw instanceof java.util.List<?> groups)) {
                    continue;
                }

                for (Object group : groups) {
                    if ("finance-read".equals(group)) {
                        result.add(new SimpleGrantedAuthority(
                            "APP_REPORT_READ"));
                    } else if ("approvers-v2".equals(group)) {
                        result.add(new SimpleGrantedAuthority(
                            "APP_REPORT_APPROVE"));
                    }
                }
            }
            return result;
        };
    }
}
```

**Integration conditions:** This class is a Spring Bean in a project with `spring-boot-starter-security` and `spring-boot-starter-oauth2-client` (or equivalent dependencies). Register the mapper bean and enable `http.oauth2Login(...)` in the filter chain; Spring Security supports configuring the mapper via `oauth2Login().userInfoEndpoint().userAuthoritiesMapper(...)` or auto-discovered bean depending on version. This class **cannot run via `javac` without Spring dependencies**.

Explanation:

- `STAFF_ISSUER` is a configured test issuer; in production source it from a reviewed source registry, never from client input. Even though `iss` was verified by the framework, constraining issuer in **policy mapping** ensures only the staff issuer can assign staff permissions.
- Exact-string mapping accepts only two group IDs, `finance-read` and `approvers-v2`; unknown roles, `admin`, or groups from other IdPs are ignored.
- Authority `APP_REPORT_READ` is distinct from `ROLE_ADMIN` and `SCOPE_profile`; the app can enforce `hasAuthority("APP_REPORT_READ")` on routes or methods. Never derive permissions from OAuth scopes.
- An IdP may place `groups` in **UserInfo** instead of the ID Token, or omit `groups` under default scopes. Adjust the extractor per the source contract, verifying `sub` consistency and UserInfo policy; never fall back to arbitrary claims or client headers.
- The mapper above **returns only mapped business authorities**. If other parts of the app also need technical flow authorities, design an explicit whitelist and test your Spring version's filter/authorization behavior; never blindly copy all of `input` as it may carry non-role `SCOPE_*` entries.
- `email_verified` and `name` do not participate in granting permissions. Mapping high-privilege rights requires risk/freshness checks, not just a claim string.

Example route configuration using the new authority:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .requestMatchers("/reports/**")
                    .hasAuthority("APP_REPORT_READ")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

This is a separate Java file `WebSecurityConfig.java` in package `com.example.federation`, with its own package/import declarations. Do not paste this import snippet immediately below `OidcRoleConfig.java`'s class body, since Java forbids `import` after a class declaration. In a complete project, place `package com.example.federation;` at the top of `WebSecurityConfig.java`.

**Important:** `hasAuthority` only checks permission at the URL layer; the report service must still check tenant/owner/unit and individual records. `REPORT_READ` from a partner applies strictly to datasets that partner is permitted to read, never granting access across all company data.

### 9.2. SAML: reading verified attributes via `Saml2AuthenticatedPrincipal`

In Spring Security SAML2, once `SAMLResponse` is verified successfully, `Authentication#getPrincipal` is commonly `Saml2AuthenticatedPrincipal`, whose `getAttributes()` returns a map of attribute names → value lists. NameID serves as the default principal name, yet **is insufficient for account linking** if the IdP lacks a stable NameID.

Spring Boot Java example, **reading data without auto-granting permissions**:

```java
package com.example.federation;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlProfileController {

    @GetMapping("/saml-profile")
    public Map<String, Object> profile(Authentication authentication) {
        if (!(authentication.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return Map.of("authenticatedBySaml", false);
        }

        String registrationId =
            principal.getRelyingPartyRegistrationId();

        // Attribute name must come from the corresponding IdP's contract.
        List<Object> names = principal.getAttributes()
            .getOrDefault(
                "urn:oid:2.16.840.1.113730.3.1.241",
                List.of());

        return Map.of(
            "authenticatedBySaml", true,
            "registration", registrationId,
            "hasDisplayName", !names.isEmpty());
    }
}
```

**Example security:** This code does not return raw assertions/NameID/email or group lists in the response. `/saml-profile` must still be protected by `saml2Login`/`authenticated` in the security chain. Do not mistake this controller for SAML validation; signature/issuer/audience/recipient checks occur **earlier** inside Spring Security/OpenSAML. If multiple filter chains exist, ensure the route does not bypass validation.

To **grant authorities from SAML attributes**, integrate mapping into the `Saml2Authentication`/authentication-provider creation step for your Spring Security version (e.g., conversion extension points on `OpenSaml5AuthenticationProvider`), or enforce permissions in an authorization service post-authentication using verified data. Audit and scope mappings by `registrationId` + IdP entityID + tenant; **never check if `principal.getAttributes().get("memberOf")` contains Admins and mint `ROLE_ADMIN`**. In Spring Security 7, extension point APIs may differ from 6.x projects; always follow the matching version reference.

### 9.3. A shared model for both SAML and OIDC

Separate extractors into two adapters:

```text
OidcVerifiedClaimsAdapter
    input: OidcUser + verified ClientRegistration/Issuer
    output: VerifiedExternalIdentity

SamlVerifiedAttributesAdapter
    input: Saml2AuthenticatedPrincipal + verified registration
    output: VerifiedExternalIdentity

NormalizationService
    input: VerifiedExternalIdentity
    output: CanonicalProfile + ExternalKey

EntitlementMapper
    input: ExternalKey/source + allowlisted group IDs
    output: application permissions

AccountLinkService
    input: verified ExternalKey + proven local account session
    output: linked identifier (only after policy approval)
```

Thus, names, emails, and groups across both protocols normalize into a **common data structure**, while **never forcing identical evidence or trust levels**. For instance, OIDC `email_verified` has standardized semantics; SAML `mail` needs a separate contract. OIDC `sub` is issuer-stable; SAML `NameID` has multiple formats with varying stability.

## 10. Conflict policy when one account has multiple IdPs

Suppose after an evidenced account-linking workflow, an internal account has two sources:

| Field | Source A | Source B | Approved rule |
| --- | --- | --- | --- |
| Display name | `Nguyễn Thị Lan` | `Lan Nguyễn` | Keep user-chosen name or HR source per contract |
| Email | `lan@corp.example` verified | `lan@partner.example` unverified | Only an email satisfying contact/verification policy becomes primary |
| Group | `finance-read` | `CN=Admins,...` | A may grant REPORT_READ; B never grants ADMIN |
| Office/Department | HR directory | self-configured OIDC claim | HR source is authoritative for org data if policy states |
| Account disabled | HR/SCIM | active SSO session remains | Never allow an older login to re-enable a disabled account |
| Tenant access | Internal ABAC | Partner IdP tenant claim | Enforce tenant on resources; never grant tenant access via email |

**Field-level precedence design:** the "most recent" claim must not blindly overwrite everything; freshness/trust/authority per source must be defined per field. Changes affecting authorization require auditing and separate policy-edit privileges. Never expose a `PATCH /profile` API accepting `groups` and writing directly into entitlements.

When a user loses their link to IdP A, whether to lock the whole local account or only remove external identifier A depends on security policy and data obligations. Notify and revoke/clear sessions per risk; never automatically reassign to another account sharing the same email.

## 11. Tricky edge cases and how to handle them

### 11.1. Email changed or reassigned

IdP A changes email from `lan@corp.example` to `lan.nguyen@corp.example` while `iss + sub` stays the same. **This is still the same external identity**. Update display/contact email per policy, without creating a new user or transferring permissions by email.

If an employee leaves and the old email is reassigned to someone else, the new user has a different `sub`. If the system linked by email, the new user could inherit the former employee's data/workflows. A unique constraint on external identifiers is an essential safeguard.

### 11.2. Group renamed or moved between OUs

SAML IdP emits `CN=Readers,OU=Finance,...` and later moves it to `CN=Readers,OU=Apps,...`. If mapping depends on the literal DN, permissions break; never work around it with `contains("Readers")`. Prefer stable group object IDs or a versioned mapping update workflow tested before cutover.

### 11.3. Same group name across two different tenants

Staff tenant has `admin`; partner tenant also has `admin`. If code checks `group.equalsIgnoreCase("admin")`, it can elevate a partner user. Always scope by `sourceKey/issuer + tenant + exactGroupId` and an allowlist. Even within a trusted tenant, an `admin` role must map to **specific permissions** allowed by the application.

### 11.4. Multi-valued and mismatched-type claims

SAML `AttributeValue` can be a list; OIDC custom `groups` can be an array or string depending on the IdP; nested `realm_access.roles` is a vendor-specific JSON object. Never coerce everything to CSV via `toString()` and split on commas, because DN values legitimately contain commas. Validate type, count, length, nulls, duplicates, and reject off-contract formats. When groups are absent, the new permission set is empty; never retain the previous session's roles as a permanent fallback.

### 11.5. Too many groups or oversized tokens

Some IdPs omit full groups from the ID Token and emit `groups overage`/a pointer to another API; brokers may truncate groups; large SAML assertions can exceed HTTP POST size limits. **Never treat a "missing claim" as preserving old permissions.** When querying Graph/Directory APIs, use least-privilege service credentials, request timeouts, source validation, and bounded caches/TTLs; never take group names from a client-supplied URL.

### 11.6. Unicode and email homographs

Accented names, combining characters, direction markers, and Unicode lookalikes can cause UI confusion. NFC unifies encoding, **but does not stop all homograph attacks**. When displaying account-search results, show additional low-sensitivity permitted info for user confirmation rather than linking by name. Internationalized emails require EAI-capable libraries/SMTP; never strip Unicode characters and treat addresses as identical.

### 11.7. SAML transient NameID and OIDC pairwise `sub`

SAML `transient` can change every session, making it unsuitable as a long-term external ID. If an IdP only provides transient NameID, require an agreed **immutable identifier attribute** and verify it comes from a trusted source before creating a local account. In OIDC, `sub` can be **pairwise** per sector identifier/RP, differing from the same person's `sub` at another app. Never aggregate accounts across RPs by email or compare `sub` values across two issuers.

## 12. Normalization and authorization test matrix

Every fixture should represent data **after valid OIDC/SAML authentication**, except cases explicitly testing source validation. Do not mutate signed raw ID Tokens/SAMLAssertions and treat signature errors as proof that mapping logic works.

| Test case | Input/condition | Expected result |
| --- | --- | --- |
| Composed vs. decomposed Unicode name | Two strings with different code points for the same name | Consistent NFC display; external key unchanged |
| Missing name | `name` absent, with or without `given_name`/`family_name` | Safe fallback; never create/merge users by name |
| Uppercase email domain | `Lan@Example.ORG` | Domain may normalize for display; local-part preserved |
| Differing local-part casing | `Lan@example.org` vs `lan@example.org` | Never use case folding to auto-link identities |
| Email `+tag` or dots | `lan+test@example.org` | Never auto-strip tags/dots |
| False/missing email verified | OIDC `email_verified` absent or false | Do not mark verified, do not auto-link |
| Identical email from two issuers | OIDC A `sub=u1`; OIDC B `sub=u2` | Two distinct ExternalKeys; no auto-linking |
| Email changed while `iss+sub` unchanged | `sub=u1`, new email | Same external key; update profile per policy |
| Unknown IdP or issuer mismatch | Token/response not from trusted source | Reject at authentication, skip mapping |
| SAML transient NameID | NameID changes every session | Never use as persistent local key without another stable source |
| Missing group claim | No `groups` | Grant no new business permissions |
| Wrong group claim type | `groups` is an unexpected string instead of array | Fail closed or controlled mapping error |
| Same group name across two issuers | `admin` in internal and partner | Map only where an approved policy exists |
| Unknown/typo group | `finance-read-2027` not in allowlist | Do not grant `REPORT_READ`, warn if needed |
| Group rename | DN/ID diverges from contract | Lose permissions (fail closed), require reviewed mapping update |
| High privilege | Partner IdP sends `Admins` | Never becomes `ROLE_ADMIN` without approval |
| Granted token scopes | `SCOPE_email` / `SCOPE_profile` | Do not infer reporting/admin entitlements |
| User removed from group post-login | Old session still holds authority | Revocation/session re-evaluation policy limits exposure |
| Multiple group values | List has duplicates and mixed casing | Intentional dedup, exact match per policy; never loosen |
| Multi-tenant | User A has `REPORT_READ` in tenant A | Cannot read tenant B unless ownership/ABAC permits |
| Concurrent account linking | Two requests bind same external ID to two local accounts | Unique constraint/transaction blocks double-linking |
| UserInfo `sub` differs from ID Token | Returns data for a different subject | Reject per OIDC; never use mismatched-subject data |
| Unsigned/unauthorized SAML attribute | Tampered XML or untrusted source | Authentication fails; grant no permissions |

**Authorization tests must cover both routes and object-level checks.** For example, a user holding `APP_REPORT_READ` still receives `403` or denial for another tenant's report; an authenticated user with no permissions cannot access admin routes.

### 12.1. Auditing data provenance

For each login in an authorization-enforcing system, log at minimum:

```text
authEventId
protocol: OIDC | SAML2
providerKey / verified issuer / registrationId
subject: pseudonymized identifier or internal reference
accountId: local ID
mappingVersion
acceptedPermissionCodes
rejectedGroupCount
emailVerificationState
timestamp UTC
decision: GRANTED / DENIED
```

Never log raw ID Tokens/Access Tokens, SAMLResponses, full NameIDs unnecessarily, cookies, real emails, or sensitive group lists. `rejectedGroupCount` helps detect mapping drift without exposing raw details. Logs must support investigations under retention and access policies.

## 13. Practical implementation checklist

- [ ] Every IdP has a clear `providerKey`, issuer/entityID, tenant, registration, certificates/keys, claim schema, and owner.
- [ ] OIDC ID Token `iss/aud/sub`/signature/expiration are verified; SAML assertion signature/issuer/audience/recipient/time/replay are verified.
- [ ] External identity keys never use name/email; use `iss + sub` for OIDC and contractually stable identifiers for SAML.
- [ ] Display names preserve Unicode/locale properly, are never used as linking keys, and are escaped in HTML output.
- [ ] Emails track source/verification state; domain canonicalization is strictly for display/search; never apply global Gmail dot/plus rules.
- [ ] Never auto-link accounts by matching email; account linking requires an authenticated session, subject consent/risk-based step-up, and auditing.
- [ ] Group/role claims are parsed per exact schema and type, with size bounds; sources outside the allowlist cannot grant permissions.
- [ ] Mappings separate issuer/tenant/group ID and policy versions; elevated privileges require internal governance approval.
- [ ] Never treat OAuth scopes, `name`, `email`, or `preferred_username` as authorities.
- [ ] Application permissions and multi-tenant data are enforced at route/method and service/object layers.
- [ ] Update and revocation mechanisms handle group membership changes; never retain old privileges indefinitely in sessions.
- [ ] Tests cover Unicode, email changes/reassignment, multiple issuers with matching emails, group renames, unknown groups, stale sessions, and cross-tenant isolation.
- [ ] Logs provide sufficient auditability without leaking tokens, private attributes, session secrets, or raw assertions.

**Conclusion:** Normalization does not mean "merging all IdPs into one namespace." The right approach is **scoping identifiers by source**, normalizing mutable profile data separately, tracking email **provenance**, and mapping only **issuer/tenant-approved groups** into application permissions. Spring Security verifies OIDC/SAML and supplies authorities/principals, while the application remains responsible for **account linking, permission mapping, and final resource authorization**.

## 14. References

- [OpenID Connect Core 1.0 — Standard Claims and Claim Stability](https://openid.net/specs/openid-connect-core-1_0.html): `iss/sub`, `name`, `email`, `email_verified`, `preferred_username`, and uniqueness.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `GrantedAuthoritiesMapper`, `OidcUserAuthority`, `OidcUserService`, and UserInfo handling.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `Saml2AuthenticatedPrincipal`, attributes, assertion verification, and `Saml2Authentication`.
- [Spring Security — SAML2 Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): configuring response authentication and granting `GrantedAuthority` by version.
- [NIST SP 800-63C-4 — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): federated identifiers, account linking, and identity handling at relying parties.
- [OASIS SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID formats, Attributes, and assertion conditions.
- [Java 17 `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization NFC/NFKC.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/): canonical/compatibility normalization and usage limits.
