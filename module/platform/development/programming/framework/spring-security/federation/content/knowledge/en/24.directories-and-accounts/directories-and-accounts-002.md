# Distinguishing Directory Lookup, Direct Authentication, and Identity Linking

> **Topic:** Spring Security – federation. **Knowledge group:** Directories and Accounts. This Knowledge README distinguishes three operations often conflated into one: **directory lookup** (querying user/group data), **direct authentication** (verifying a credential directly against an identity store, e.g., LDAP bind), and **identity linking** (associating an identity already authenticated by an external system with a local application account). It focuses on Spring Security Servlet, Java 17+, LDAP/Active Directory, databases, OIDC, SAML, Kerberos, and the essential trust boundaries when deploying federation.

## 1. Three Different Questions

An SSO system may use the same Active Directory for multiple purposes, yet the following three operations **differ in inputs, outputs, security guarantees, and ownership**.

1. **Directory lookup:** "Which record in the directory matches this identifier? What are its attributes and groups?" It typically uses search/read over LDAP/AD or a directory API. **Finding a user does not mean the caller has proven they are that user.**
2. **Direct authentication:** "Does the person logging in actually control the required credential?" For example, Spring Security uses LDAP **bind as user** to verify username/password, or a local password encoder checks a hash. It returns authentication success or failure. **Successful authentication does not by itself prove the user holds any application permissions.**
3. **Identity linking:** "Which local account in app B corresponds to the identity verified by provider A?" For example, an OIDC `(issuer, subject)` pair is linked under controlled rules to `localUserId`. This is a **governed identity-mapping rule**, not looking up a user by email and auto-merging.

**One sentence to remember:** *Lookup finds a record; authentication proves control of a credential; linking decides which local account an external record corresponds to.*

A real flow may require all three, but **their order, trust requirements, and timing must be explicit**.

## 2. Head-to-Head Comparison

| Property | Directory lookup | Direct authentication | Identity linking |
|---|---|---|---|
| Question | Which record? Which attributes? | Is the credential valid? | Which local account does the external identity belong to? |
| Input | Search base, filter, DN/ID | Username/password or other credential | Verified external ID + proof of the account being linked |
| Typical systems | LDAP, AD, directory API, DB | LDAP bind, local password hash, KDC, IdP | Local identity-link DB/service |
| Output | 0/1/n records, attributes, groups | Authenticated principal or failure | Local user ID or conflict/unlinked |
| Proves caller owns identity? | **No** | **Yes, when properly verified** | Only if the identity proof is already valid |
| Reads user password? | Should not; usually cannot | May receive password in login form; must not log it | No password needed if other proof suffices |
| Produces app roles? | May return data as a mapping source | Does not grant business roles by itself | Does not grant roles; only connects identity→account |
| Typical failures | Not found, multiple matches, timeout | Bad credentials, locked, disabled | Not linked, duplicate key, account conflict |
| Requires unique identity key? | Yes, to avoid picking the wrong record | Yes, to select the right principal/realm | **Mandatory** for uniqueness |
| Can occur after SSO? | Yes | No need to re-authenticate with password if SSO already verified | Yes, after a verified login |
| Trust boundary | Trust directory data per read permissions | Trust verifier/credential protocol | Trust both external proof and local account ownership |
| Risk if misused | User enumeration, LDAP injection, wrong groups | Credential leak, auth bypass | Account takeover, cross-tenant identity collision |

**Do not call every LDAP query "LDAP authentication".** LDAP is a protocol with search/read/bind/compare/modify operations; using LDAP **to read groups** is not the same as **binding with the user's password**.

## 3. A Practical Scenario Clarifying the Difference

A company has:
- **AD Directory** managing employees and AD group memberships.
- **Spring Portal** with account `localUserId=1001`, tenant, and report-approval permissions.
- **OIDC Identity Provider** serving SSO logins.
- **External identities table** connecting IdP identifiers to `localUserId`.

When Alice logs in via OIDC:
1. Spring Security runs the OIDC Authorization Code flow and verifies the ID Token/issuer/audience/nonce/state as configured.
2. From the trusted OIDC principal, the app receives the `iss` and `sub` pair.
3. The identity-link table resolves that pair to `localUserId=1001`. **This is linking/resolution**, not checking an AD password.
4. The app may query AD via a stable mapping to fetch group IDs. **This is lookup**, not re-authentication.
5. The app queries local DB roles and checks whether the account is active and belongs to the tenant.
6. The app creates the Spring Authentication/authorities per policy and enforces per-resource authorization.

Conversely, if the app has its own **username/password form using LDAP bind**, the credential verification step is **direct LDAP authentication**. It does not automatically create an OIDC identity link unless a separate, explicitly authorized linking workflow runs.

## 4. A Directory Is a Data Store, Not an Answer to "Is Logged In?"

An LDAP directory can store entries identified by DN:

~~~text
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
mail: alice@example.org
employeeNumber: E1042
~~~

DNs/attributes are illustrative. Schemas vary by directory; AD commonly uses `userPrincipalName`, `sAMAccountName`, `objectGUID`, `objectSid`, and `memberOf`.

### 4.1. LDAP search

A conceptual lookup:

~~~text
base   = ou=people,dc=example,dc=org
scope  = subtree
filter = (&(objectClass=inetOrgPerson)(uid=alice))
attrs  = uid, cn, mail, entryUUID
~~~

Outcomes:
- **0 records:** no matching identity found in scope; does not mean wrong password.
- **1 record:** matching directory entry exists; has not authenticated the caller.
- **Multiple records:** search key/filter is not unique or directory is misconfigured; **never auto-pick the first record** for authentication/linking.

### 4.2. LDAP lookup can use service credentials

The application uses a **read-only service bind** or appropriate mTLS/SASL to ask the directory "does alice belong to group X?". This service account proves **the application's permission to read the directory**; it **does not prove that the person using the browser is Alice**.

**Dangerous anti-pattern:**

~~~java
// UNSAFE: finding a record and assuming the browser is the account owner.
if (directory.findByUid(request.getParameter("uid")) != null) {
    // Must not create an authenticated session here.
}
~~~

Any client can send `uid=alice`. Lookup is a data source, not credential proof.

### 4.3. Directory lookup serves many non-login tasks

- Finding a user to display name/email in an admin UI.
- Fetching group memberships after a Kerberos or OIDC login.
- Checking account active/disabled status before granting business access.
- Looking up an employee's manager/department.
- Syncing approved public profile information.
- Routing policy by organization, **not** replacing authentication.
- Checking an external identity link against a directory object.

Each use case requires checking read permissions and privacy: searching for people does not mean every attribute may be displayed.

## 5. Direct Authentication Is Credential Verification

### 5.1. LDAP bind authentication

Spring receives username/password in an **HTTPS login form**, determines the user DN, and attempts an LDAP bind with the user's own credentials. The directory server verifies the password and account policy; Spring receives success/failure.

~~~text
Browser                 Spring Application                LDAP/AD
   |                            |                            |
   | POST /login                |                            |
   | username, password         |                            |
   +--------------------------->|                            |
   |                            | Search DN or DN pattern    |
   |                            +--------------------------->|
   |                            |<------ user DN ------------+
   |                            | Bind as user with password |
   |                            +--------------------------->|
   |                            |<------ success/failure ----+
   |                            | If success, load group/role|
   |                            | and create Authentication  |
   |<----------- result --------+                            |
~~~

**Key point:** In bind authentication, the application does not need to read the password or password hash from LDAP and compare it itself. The LDAP server checks credentials; Spring Security LDAP uses `LdapAuthenticator` instead of the default DB-backed form authentication's `UserDetailsService`. <escape><</escape>This does not mean the login form does not receive a password: Spring **may receive the password on the inbound request** to pass to bind, so TLS, request logging, and secret handling must be protected.</escape>

### 5.2. Password comparison is a different mechanism from bind

Spring LDAP also supports **password comparison**:
- The application uses the LDAP compare operation or retrieves the password/hash attribute when directory policy permits.
- Compares the supplied credential against the stored value using an appropriate algorithm/`PasswordEncoder`.
- LDAP compare has limitations with salted hashes, as noted in the Spring documentation.
- Never use `NoOpPasswordEncoder` in production, and never unilaterally change the directory's password hashing format without an authentication contract.

Do not lump "LDAP bind", "LDAP compare", and "running SELECT user WHERE username=..." into one operation.

### 5.3. Local database password authentication

An application using password hashes in a DB can:
1. Load `UserDetails` via `UserDetailsService`.
2. Use `DaoAuthenticationProvider` and a `PasswordEncoder` (e.g., bcrypt/Argon2 per policy) to verify the password.
3. Return an `Authentication` with mapped `GrantedAuthorities`.

**Difference from LDAP bind:** the application owns the password hash/encoder logic; with LDAP bind, the directory verifies the credential. Both are **direct authentication**, but their trust boundaries and secret lifecycles differ.

### 5.4. Direct authentication is not synonymous with group lookup

Possible outcomes:
- Bind succeeds, but the user has no app role → authenticated, yet receives 403.
- User/AD group lookup succeeds, but password bind fails → no authenticated session created.
- AD account is disabled despite having an entry → must be denied per auth/account lifecycle policy.
- User already logged in via an OIDC IdP → app looks up AD groups without binding the password again.

Keeping these distinct helps diagnose "user not found", "wrong password", and "insufficient permissions" accurately.

## 6. Spring Security LDAP: Standard Bind Configuration

Spring Security documentation for Servlet uses `LdapBindAuthenticationManagerFactory` with `BaseLdapPathContextSource`.

File `src/main/java/com/example/security/LdapBindConfiguration.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Configuration
public class LdapBindConfiguration {

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {

        LdapBindAuthenticationManagerFactory factory =
                new LdapBindAuthenticationManagerFactory(contextSource);

        factory.setUserSearchBase("ou=people");
        factory.setUserSearchFilter("(uid={0})");

        return factory.createAuthenticationManager();
    }
}
~~~

Explanation:
- `contextSource` holds the LDAP connection/base DN and TLS/trust configuration.
- `setUserSearchBase` restricts the scope, avoiding searching the whole directory unnecessarily.
- `setUserSearchFilter` is a pattern processed by Spring with the login username; never concatenate arbitrary HTTP input.
- `createAuthenticationManager()` returns a manager for **username/password LDAP login**, not a plain directory lookup service.
- User DN patterns can also be used if the directory has a fixed layout, such as `uid={0},ou=people`.
- This example is a **Spring configuration class**, not runnable with plain `javac`; it requires a context source, Spring dependencies, login filter/HTTP Security, an LDAP server, and real TLS.
- For Active Directory, there is a dedicated `ActiveDirectoryLdapAuthenticationProvider` following UPN conventions; use the version and configuration appropriate for domain/URL/account status—do not assume generic LDAP bind handles every AD feature the same way as the AD provider.

**Never create a login session by calling `directory.search()` and returning success.** The manager must prove the password or corresponding credential.

### 6.1. Configuring permissions via LDAP authorities populator

Spring Security provides `LdapAuthoritiesPopulator` to load authorities after LDAP authentication. Example fragment:

~~~java
@Bean
LdapAuthoritiesPopulator ldapAuthorities(
        BaseLdapPathContextSource contextSource) {

    DefaultLdapAuthoritiesPopulator populator =
            new DefaultLdapAuthoritiesPopulator(
                    contextSource, "ou=groups");

    populator.setGroupSearchFilter("(member={0})");
    return populator;
}
~~~

Required imports:
- `org.springframework.security.ldap.userdetails.LdapAuthoritiesPopulator` (verify actual API for your version).
- `org.springframework.security.ldap.userdetails.DefaultLdapAuthoritiesPopulator` per the actual package in your Spring Security LDAP release.

Depending on the Spring Security version's source layout, `DefaultLdapAuthoritiesPopulator` typically lives under `org.springframework.security.ldap.userdetails`. This snippet is a **bean fragment**, not a standalone buildable module; it must be wired via `factory.setLdapAuthoritiesPopulator(populator)` and checked against group mapping policy.

**Operations:** Group search returns directory groups; it does **not** automatically turn every LDAP group into `ROLE_ADMIN`. Grant authorities only according to a business allowlist policy.

## 7. Spring LDAP: Querying the Directory Without Authenticating the User

A fragment using `LdapTemplate` and `LdapQueryBuilder` is completely different from bind authentication:

~~~java
package com.example.directory;

import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class DirectoryReader {

    private final LdapTemplate ldap;

    public DirectoryReader(LdapTemplate ldap) {
        this.ldap = ldap;
    }

    public List<String> lookupUids(String uid) {
        LdapQuery q = query()
                .base("ou=people")
                .where("uid").is(uid)
                .and("objectClass").is("inetOrgPerson");

        return ldap.search(q, (AttributesMapper<String>)
                attrs -> (String) attrs.get("uid").get());
    }
}
~~~

**This is a Java class with a Spring LDAP dependency**, not a standalone program. It only performs a search using the account authorized for `LdapTemplate`. After receiving the list, you must handle 0/1/n entries per policy; if used for identity resolution, require **exactly one** result.

**Why the builder matters:** Spring LDAP `LdapQueryBuilder` escapes dangerous characters in filter values, preventing LDAP injection. Never write:

~~~java
// UNSAFE: filter injection.
String filter = "(uid=" + request.getParameter("uid") + ")";
~~~

Even input from a trusted directory/API should be escaped for LDAP filters or parameterized in SQL; "Kerberos authenticated" does not make a principal string safe to concatenate into a query.

### 7.1. Lookup contains no password

`lookupUids("alice")` does not accept a user password, does not verify who is using the browser, and does not create a Spring Authentication. It is appropriate for looking up profiles/groups **after another authentication flow has already succeeded**.

### 7.2. LDAP search should return a stable identifier

If the goal is identity linking, read an immutable/stable directory ID:
- Generic LDAP may provide `entryUUID` if supported by server/schema.
- Active Directory typically uses `objectGUID` for user objects and `objectSid` for security identities.
- `uid`, `cn`, `mail`, or `displayName` can be changed, duplicated, or recycled.

The code example only returns `uid` to illustrate lookup; **it does not recommend using `uid` as a global immutable external key across all directories**.

## 8. Active Directory: AD Auth and AD Lookup Are Different

AD provides these concepts:
- `userPrincipalName` (UPN) and `sAMAccountName` (login-name conventions).
- `objectGUID` (directory object identity).
- `objectSid` (security identifier).
- `memberOf`/nested group membership.
- Account disabled/locked/expired policies.
- SPNs and Kerberos tickets on AD domain controllers.
- Directory queries over LDAP/LDAPS.

### 8.1. AD password login

Spring `ActiveDirectoryLdapAuthenticationProvider` is a specialized provider:
- Typically authenticates with a UPN in the form `username@domain`.
- Can use a custom search filter.
- Handles AD-specific errors/sub-codes per configuration.
- After auth, can retrieve group memberships/authorities.

This is still **direct authentication** when the application receives username/password. If browser SSO runs via Kerberos, the application receives a SPNEGO ticket and **does not need to force the user to re-enter their AD password just to look up groups**.

### 8.2. AD query after Kerberos/OIDC

The application can use a read-only service credential to look up `objectGUID` and approved groups for a verified principal. When doing so, do not call that lookup "AD login". The Kerberos/OIDC provider already performed authentication elsewhere; the directory is only a source of attributes/entitlements.

### 8.3. Identifying a user through AD

You may need mappings such as:
- Verified Kerberos `user@REALM` → AD user object.
- Verified OIDC `iss+sub` → approved link → `localUserId` → AD `objectGUID`.
- Local account → AD `objectGUID` to fetch groups.
- Nested AD groups → application-role allowlist.

Do not infer that an OIDC user belongs to an AD record simply because both share the same email.

## 9. Federation Authentication Differs from Direct LDAP Bind

Spring Security federation typically involves:
- **OIDC/OAuth2 Login:** Browser redirects to IdP, Spring receives Authorization Code, performs token exchange and verifies the ID Token per configuration, then receives `OidcUser`/claims.
- **SAML 2.0 Login:** Spring SP verifies Response/Assertion signatures, issuer, conditions, audience/recipient, and response correlation per profile, then receives `Saml2AuthenticatedPrincipal`/attributes.
- **Kerberos/SPNEGO:** GSS acceptor uses a service keytab to verify AP-REQ and obtains a verified Kerberos client principal.
- **CAS native protocol:** Client receives a Service Ticket and validates it via the CAS Server validation endpoint.

**None of these is inherently an LDAP password bind inside the web application.** The federation service may rely on a directory at the IdP, or the application may look up a directory after login, but the active verifier is the corresponding IdP/KDC/CAS protocol.

### 9.1. Scenario classification table

| Scenario | Authentication mechanism | Lookup | Linking |
|---|---|---|---|
| Username/password login form, LDAP bind | Direct LDAP bind | DN/group lookup may accompany | Not required |
| Local DB password login form | DaoAuthenticationProvider/PasswordEncoder | UserDetailsService DB | Not required |
| Browser Kerberos SPNEGO | Kerberos GSS ticket verification | AD/LDAP groups after ticket | Possible, if local account |
| Spring OIDC Login | IdP-verified ID Token/code flow | UserInfo, local DB, or AD | Usually needs local mapping |
| Spring SAML Login | Signed Response/Assertion protocol verification | SAML attributes, local DB/AD | Usually needs local mapping |
| CAS Ticket login | CAS ticket validation | Local directory/DB | Possible |
| Admin searches employee by email | **No end-user auth from lookup** | Directory search | Does not auto-create link |
| Logged-in user clicks "Link account" | Must have current session and external proof | Lookup may assist | Explicit identity linking |
| SCIM user provisioning | Not end-user login | Creates/updates directory records | May prepare identity links, must be approved |

**Never build an authentication provider from a search/read API:** finding a directory entry does not prove credential ownership.

## 10. Identity Linking: Connecting an External Identity to a Local Account

An application has local accounts:
~~~text
local_users
  id         uuid
  status     ACTIVE / DISABLED
  tenant_id  tenant-a
  created_at timestamp
~~~

External identities can be attached as:
~~~text
external_identity_links
  provider_type  OIDC | SAML | KERBEROS | LDAP | CAS
  issuer_or_realm
  external_subject
  local_user_id
  tenant_scope
  link_state     ACTIVE | REVOKED
  linked_at
  linked_by
~~~

This is a **schema concept**, not a default Spring schema. One local account may have multiple approved external identities, and an external identity should point to **only one** local account within a defined scope.

### 10.1. Identity linking is a long-lived trust decision

Once a link is created, subsequent logins with the same external identity typically resolve straight to the local user. A wrong link can grant access to someone else's account even when IdP authentication is completely valid.

**Therefore, linking is a security-sensitive operation**, not an "INSERT if email matches" action. It requires authentication proof, explicit intent, session freshness, CSRF protection, uniqueness, and auditing.

### 10.2. OIDC external key

OpenID Connect Core defines the **`iss` + `sub`** pair as the stable identifier within the IdP's scope:
- `iss` = verified issuer (URL/issuer identifier).
- `sub` = subject identifier within the issuer.
- Never use `email`, `preferred_username`, or `name` as a trusted unique key across users/issuers.

Example:
~~~text
OIDC
issuer  = https://login.example.org/realms/employees
subject = 248d2bf1-...
localUserId = 1001
~~~

OIDC emails can be changed, reused, or omitted; `email_verified` only reflects the provider's assertion per policy and **is not sufficient to auto-link to a sensitive local account**. Also validate the ID Token, and when using UserInfo, confirm `UserInfo.sub` matches the ID Token `sub`.

### 10.3. SAML external key

SAML does not have a single fixed pair like OIDC `iss+sub` across all deployments. The identity key must rely on:
- Trusted IdP entityID/issuer.
- NameID and `Format`/`NameQualifier`/`SPNameQualifier` where appropriate for the profile.
- Or a stable attribute defined by the IdP–SP contract, with clear uniqueness, reassignment, and lifecycle policies.

**Do not assume NameID is always stable:** a transient NameID can change on every login; an email-format NameID is not inherently immutable. When changing IdPs/certificates/name mappings, perform a formal link migration and guard against account takeover.

### 10.4. Kerberos/AD external key

With Kerberos, use the verified **full principal + realm** per the trust contract. If AD changes UPNs, an approved mapping to `objectGUID`/`objectSid` can preserve the local identity. Do not strip `@REALM` or blindly lowercase all names and merge accounts across realms.

### 10.5. Direct LDAP auth external key

If direct LDAP bind has authenticated the user, the result can be mapped to a stable directory ID:
- Directory `entryUUID` per server schema.
- AD `objectGUID`/`objectSid`.
- DN/uid can change on rename/move, so a migration policy is needed.

Do not turn finding an LDAP entry by email into proof that the browser owns that account.

### 10.6. Identity keys must have a namespace/provider

An external subject string like `alice` is not globally unique. The identity key should include:
- Mechanism/provider type.
- Trusted issuer/realm/directory instance.
- Exact subject ID.
- If multi-tenant: the scope actually required by the provider/local identity model contract.

**Never alter the issuer string from an unverified redirect URL**; derive the issuer from trusted provider/metadata after protocol validation. Never auto-merge subjects from two different issuers.

## 11. Safe Account Linking Requires Two-Sided Proof

Suppose Alice is already logged into a local account and wants to link her company SSO:

1. Alice has an **authenticated local session**, still valid and sufficiently fresh.
2. Alice explicitly chooses "Link corporate account" via a CSRF-protected POST.
3. The app creates a one-time link intent with nonce/state/TTL bound to the session/`localUserId` and expected provider.
4. The browser initiates the OIDC/SAML/other trusted authentication flow.
5. Spring verifies the protocol response, ensuring the external identity actually authenticated and belongs to the expected provider/tenant.
6. The app canonicalizes the external key per the protocol contract.
7. The app checks that the external key is not yet linked to another `localUser`, and that the local account is still active.
8. A transaction/unique constraint creates the link atomically; concurrent attempts cannot hijack an account.
9. Audit the user, provider, link key hash, timestamp, authentication context, and outcome.
10. Redirect to a success page and clear the pending intent; **do not** trigger money transfers or other side effects solely because the auth callback succeeded.

**If the user has no local session yet**, the account recovery/linking workflow must provide equivalent proof of local account ownership. Finding a local user whose email matches the IdP's is not enough.

### 11.1. Verifying control of the local account

Options depend on risk:
- Re-authenticate with local credentials per security policy.
- Verify MFA bound to the local account.
- For IAM-managed corporate accounts, use an approval workflow/gateway authenticated on both sides.
- An account recovery flow with rate limiting, anti-enumeration, proof of possession, and auditing.

Never use "email from IdP equals local email" as sole proof for high-privilege accounts.

### 11.2. When the external identity is already linked

If a link for the external key already exists:
- **Same `localUserId`:** can be treated as idempotent (already linked), creating no duplicate.
- **Different `localUserId`:** **conflict**—reject, never silently reassign.
- **Revoked link:** policy may require manual re-approval; do not auto-revive on login.
- **Disabled local account:** disallow new linking or login per policy.
- **Different tenant:** do not bypass tenant isolation, do not merge by default.

### 11.3. Unlinking is also a security operation

Protect against:
- Require recent reauth/step-up from the user.
- Do not unlink the last login method if it leaves the account unrecoverable, unless an explicit recovery policy exists.
- Do not allow unlinking another `localUser`'s link.
- Audit and invalidate sessions/tokens as needed.
- Do not automatically transfer a `localUser`'s permissions when a provider changes `sub` or NameID.

## 12. JIT Provisioning Is Different from Auto-Linking Old Accounts

**Just-In-Time provisioning** means creating a new local account when a valid external identity is encountered for the first time, according to onboarding policy. It does not mean attaching an external identity to an existing account because the email matches.

### 12.1. Scenario with no existing external link

After successful OIDC/SAML login, when link lookup finds nothing:
1. If the provider/tenant is not on the allowlist → deny.
2. If there is no onboarding entitlement → deny/request approval.
3. If policy permits JIT → atomically create a **new local account** and external link with minimal permissions.
4. If a local account has a matching email → do not auto-merge; require explicit linking or approved enterprise account resolution.
5. If the directory has a user with the same username who is a different person → do not merge.
6. If a race condition occurs → database uniqueness handles it, with safe transaction retry/handoff.

### 12.2. Default permissions must be minimal

JIT-created accounts should not be granted by default:
- `ROLE_ADMIN`.
- Payment/disbursement approval rights.
- Access to all tenants.
- Permissions from user-self-asserted groups.
- Access to resources belonging to another local account.

Permission sources must be approved group/entitlement mappings with tenant scope and a revocation lifecycle.

## 13. Unique Keys, Transactions, and Preventing Account Takeover

A reference SQL schema (dialect may vary by DB):

~~~sql
CREATE TABLE local_user (
    id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    tenant_id VARCHAR(64) NOT NULL
);

CREATE TABLE external_identity_link (
    provider_type VARCHAR(24) NOT NULL,
    trusted_issuer VARCHAR(512) NOT NULL,
    subject_key VARCHAR(512) NOT NULL,
    local_user_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    linked_at TIMESTAMP NOT NULL,
    PRIMARY KEY (provider_type, trusted_issuer, subject_key),
    FOREIGN KEY (local_user_id) REFERENCES local_user(id)
);
~~~

**Significance:**
- The composite unique key ensures the same external identity cannot point to two local users.
- The foreign key ensures the target account exists.
- Create the link inside a transaction; never rely on "SELECT not found, then INSERT" without a database uniqueness guarantee.
- Model subject/issuer lengths and indexes according to your DB and provider contract; a keyed digest with a collision policy can be used if fields exceed index limits.
- If the architecture uses tenant-specific identity keys, clearly define whether tenant belongs in the PK or on the local user; **never add tenant from a browser request to let the same identity claim multiple accounts outside policy**.
- Define re-link/unlink/audit state rules rather than treating rows as immutable.
- Credential secrets, passwords, tokens, and SAML assertions must not be stored in the linking table.

**Concurrency scenario:** Two sessions simultaneously try to link one external key to two different local accounts. Only one transaction commits; the other hits a conflict and must not overwrite. This is a critical safeguard against takeover in multi-pod environments.

## 14. Standalone Java 17: Simulating Three Separate Operations

The following code **runs on JDK 17+** with no LDAP, Spring, or IdP required. It separates directory lookup, already-obtained credential verification from a trusted provider, and identity linking. Results are **simulations** and must not be used as production authentication.

File `DirectoryAuthLinkDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class DirectoryAuthLinkDemo {

    record ExternalKey(String provider, String issuer, String subject) {
        ExternalKey {
            Objects.requireNonNull(provider);
            Objects.requireNonNull(issuer);
            Objects.requireNonNull(subject);
            if (provider.isBlank() || issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException("Empty identity key");
            }
        }
    }

    record LocalAccount(String id, boolean enabled) {
    }

    enum LinkOutcome {
        LINKED, ALREADY_LINKED, CONFLICT, REJECTED
    }

    private static final Map<String, String> DIRECTORY = Map.of(
            "alice", "alice@example.org");

    private static final Map<String, LocalAccount> ACCOUNTS = Map.of(
            "U1001", new LocalAccount("U1001", true),
            "U2002", new LocalAccount("U2002", true),
            "U3003", new LocalAccount("U3003", false));

    private static final Map<ExternalKey, String> LINKS = new HashMap<>();

    static boolean directoryContains(String uid) {
        return DIRECTORY.containsKey(uid);
    }

    static LinkOutcome link(
            ExternalKey key,
            String localId,
            boolean localSessionVerified,
            boolean externalCredentialVerified) {

        LocalAccount account = ACCOUNTS.get(localId);
        if (!localSessionVerified
                || !externalCredentialVerified
                || account == null
                || !account.enabled()) {
            return LinkOutcome.REJECTED;
        }

        String existing = LINKS.get(key);
        if (existing != null) {
            return existing.equals(localId)
                    ? LinkOutcome.ALREADY_LINKED
                    : LinkOutcome.CONFLICT;
        }

        LINKS.put(key, localId);
        return LinkOutcome.LINKED;
    }

    public static void main(String[] args) {
        ExternalKey alice = new ExternalKey(
                "OIDC", "https://idp.example.org", "sub-123");
        ExternalKey other = new ExternalKey(
                "OIDC", "https://other-idp.example.org", "sub-123");

        System.out.println("directory-found=" +
                directoryContains("alice"));
        System.out.println("lookup-authenticates=false");
        System.out.println("unverified=" +
                link(alice, "U1001", true, false));
        System.out.println("link=" +
                link(alice, "U1001", true, true));
        System.out.println("repeat=" +
                link(alice, "U1001", true, true));
        System.out.println("conflict=" +
                link(alice, "U2002", true, true));
        System.out.println("other-issuer=" +
                link(other, "U2002", true, true));
        System.out.println("disabled=" +
                link(new ExternalKey(
                     "OIDC", "https://idp.example.org", "sub-999"),
                     "U3003", true, true));
    }
}
~~~

Compile and run:

~~~bash
javac DirectoryAuthLinkDemo.java
java DirectoryAuthLinkDemo
~~~

**Exact stdout:**

~~~text
directory-found=true
lookup-authenticates=false
unverified=REJECTED
link=LINKED
repeat=ALREADY_LINKED
conflict=CONFLICT
other-issuer=LINKED
disabled=REJECTED
~~~

**Interpretation:**
1. Directory finds Alice, yet the lookup result **is not a login**.
2. Unverified external proof cannot create a link even with a valid local session.
3. Re-linking to the same account is idempotent.
4. An external key already bound to U1001 cannot be silently hijacked by U2002.
5. Same subject text under a **different issuer** is a different identity.
6. A disabled local account cannot be used as a link target.

**Security limitation:** The two booleans `localSessionVerified` and `externalCredentialVerified` are purely illustrative. In production, **never let an HTTP client pass two booleans and trust them**; rely on a trusted server-side session, a fully validated OIDC/SAML/Kerberos result, CSRF/state/nonce/freshness, and a transactional repository. `HashMap` is only for single-threaded demos; multi-node systems must use database unique constraints and transactions.

## 15. Standalone Java 17: Demonstrating Which Operation Counts as Authentication

This example requires no real passwords; it classifies API intent, showing that merely finding a directory entry does not produce an authenticated principal.

File `IdentityOperationDemo.java`:

~~~java
public class IdentityOperationDemo {

    enum Operation {
        DIRECTORY_LOOKUP,
        PASSWORD_AUTHENTICATION,
        FEDERATION_AUTHENTICATION,
        IDENTITY_LINKING
    }

    static String result(Operation op) {
        return switch (op) {
            case DIRECTORY_LOOKUP -> "ATTRIBUTES_NOT_IDENTITY_PROOF";
            case PASSWORD_AUTHENTICATION ->
                    "CREDENTIAL_VERIFICATION_REQUIRED";
            case FEDERATION_AUTHENTICATION ->
                    "PROTOCOL_PROOF_VERIFICATION_REQUIRED";
            case IDENTITY_LINKING ->
                    "TWO_SIDED_PROOF_AND_UNIQUE_BINDING";
        };
    }

    public static void main(String[] args) {
        for (Operation op : Operation.values()) {
            System.out.println(op + "=" + result(op));
        }
    }
}
~~~

Run:

~~~bash
javac IdentityOperationDemo.java
java IdentityOperationDemo
~~~

**Exact stdout:**

~~~text
DIRECTORY_LOOKUP=ATTRIBUTES_NOT_IDENTITY_PROOF
PASSWORD_AUTHENTICATION=CREDENTIAL_VERIFICATION_REQUIRED
FEDERATION_AUTHENTICATION=PROTOCOL_PROOF_VERIFICATION_REQUIRED
IDENTITY_LINKING=TWO_SIDED_PROOF_AND_UNIQUE_BINDING
~~~

This model only clarifies the responsibility of a Java layer. It cannot replace LDAP bind authentication or token signature verification.

## 16. Spring Security OIDC: Authority Mapping Is Not Account Linking

Spring `oauth2Login()` can configure an OIDC `OidcUserService` or `GrantedAuthoritiesMapper`:
- The IdP supplies verified claims/identity after protocol authentication.
- UserInfo can supplement attributes after Spring verifies the source and subject.
- `OidcUser.getAuthorities()` may include authorities from OAuth scopes and `OidcUserAuthority`.
- The app can map these to `GrantedAuthority` business roles.
- A **separate identity-link service** resolves `localUserId` from `iss+sub`.

Warnings:
- `SCOPE_profile` or `OIDC_USER` does not automatically equal `ROLE_ADMIN`.
- `email_verified=true` does not automatically authorize linking to a local account sharing that email.
- `UserInfo.sub` must match `ID Token.sub`; OpenID Connect Core explicitly mandates this.
- Never derive the issuer from an arbitrary browser URL; take it from configured provider metadata and response validation.
- If an identity is unlinked, deny or trigger onboarding/JIT per policy; never auto-grant high privileges.

### 16.1. Spring OIDC configuration fragment

~~~java
@Bean
SecurityFilterChain oidcSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(approvedOidcUserService())));
    return http.build();
}
~~~

This is a **method fragment**: `approvedOidcUserService()` must perform protocol-validated `OidcUser` delegation, identity linking, and authority policy, returning an `OAuth2UserService<OidcUserRequest, OidcUser>` compatible with the framework version. The code does not run standalone; do not treat this fragment alone as a complete secure OIDC integration.

**Important:** Never replace Spring's OIDC protocol verifier with a user lookup by email. Identity linking must only run after trusted token validation.

## 17. Spring SAML and Kerberos: Different Principal Connections

### 17.1. SAML

After `saml2Login()` and SAML Response verification, Spring has an authenticated principal and attributes. Identity linking needs to know:
- Trusted IdP issuer.
- Stable subject contract (NameID Format/qualifiers or a stable identifying attribute).
- Signature, audience, recipient, replay, and response correlation conditions.
- Tenant/IdP registration/metadata trust.

A SAML email attribute is not sufficient for auto-linking; a transient NameID is not stable for long-lived accounts. The identity key rule must be agreed upon with the IdP.

### 17.2. Kerberos

After `SpnegoAuthenticationProcessingFilter` and `KerberosServiceAuthenticationProvider` verify the ticket:
- Verified full principal includes the realm.
- The app can use directory lookup to fetch AD groups/user objects.
- The app can link the principal/`objectGUID` to `localUserId`.
- There is no need to collect the user's password or re-bind LDAP just to look up groups.

**Do not strip the realm:** `alice@REALM-A` is different from `alice@REALM-B`. If short names collide, resolve them via stable directory linking and realm trust policy.

### 17.3. Native CAS

CAS Service Ticket validation verifies a CAS principal over a back-channel; it can map to `localUserId` using trusted CAS issuer/service configuration and a stable principal contract. A CAS ticket **is not a Kerberos ticket**, and a CAS server using an LDAP backend does not mean the client is running an LDAP bind.

## 18. Application Permissions Must Be Loaded Separately

After direct authentication or federation authentication:
1. You have a proven identity.
2. Identity resolver/link service provides `localUserId`.
3. Directory/DB/IAM lookup retrieves account status/roles/memberships.
4. Only allowlisted groups/entitlements produce `GrantedAuthority`.
5. Resource/tenant authorization decides the action.

Example:
- AD group "GG-Report-Readers" may map to `ROLE_REPORT_VIEW`.
- Group "Domain Admins" **does not automatically become** portal `ROLE_ADMIN`.
- `hasAuthority("ROLE_REPORT_VIEW")` checks the exact string.
- `hasRole("REPORT_VIEW")` uses the default role prefix, typically checking `ROLE_REPORT_VIEW`.
- If the app authorizes per tenant, a global role is not enough.

### 18.1. Identity lifecycle differs from role lifecycle

An account may still hold a valid identity link while:
- The local account is disabled.
- A group/role has been revoked.
- Tenant membership has expired.
- The directory has offboarded the user.
- Spring `HttpSession` still holds a stale authorities snapshot.

**A link does not mean lifetime authorization.** You need TTL/cache invalidation, account state rechecks, and a session revocation policy.

### 18.2. Do not mechanically mint ROLE_ADMIN from external claims

Token claims such as `groups=["Admin"]` or `email_domain=example.org` are only **data from the IdP**; you must trust the right issuer/audience and apply a mapping policy using stable IDs and tenant scope, never turning every claim into application authorities. Authorization must enforce least privilege.

## 19. Account Linking and Multi-Tenancy

An enterprise with multiple tenants/organizations may have per tenant:
- A different AD domain.
- A different OIDC issuer.
- A different SAML IdP.
- Users with the same email/username who are different real identities.
- Different local roles/permissions.

An identity from tenant A **must not automatically link to a local account in tenant B**. Required:
- Trusted issuer/realm/provider registration.
- Approved `localUserId` and tenant membership.
- Unique identity key and uniqueness policy.
- Cross-tenant linking approval/recovery when genuinely needed.
- Explicit conflict handling and auditing.

**Be careful with per-tenant uniqueness:** If the unique key is only `(tenant, issuer, sub)`, the same identity could be linked to two accounts in two tenants; this may be intended or may violate your security model. Choose global vs. provider-scoped uniqueness based on the contract, never from a user-supplied tenant in a query parameter.

## 20. Caches, Offboarding, and Account Status

A production environment has several caches:
- LDAP/AD user attributes/group memberships.
- Local identity-link resolution.
- OIDC/SAML/Kerberos authenticated principal/session.
- Spring `SecurityContext`/`HttpSession` holding an authorities snapshot.
- Per-resource authorization decisions.

These caches have **different lifecycles**. When an admin disables a user or removes a group:
- Directory search may return the new status.
- The identity link still exists.
- Spring `HttpSession` may still be authenticated.
- Group cache TTL may not have expired yet.
- IdP ticket/token may not have expired yet.

Solutions:
1. Define a revocation SLA for each role category.
2. When an account is disabled, deny login and invalidate/revoke sessions based on risk.
3. When roles change, refresh authorities/invalidate caches.
4. Sensitive actions check entitlements close to time of use.
5. Logs/audit capture provider, `localUserId`, policy version, and outcome without raw tokens.
6. When directory/IAM is unavailable, **fail closed** for new authentication/role elevation; stale-cache policies apply only if explicitly approved.
7. Never assume a fresh LDAP search automatically updates the `SecurityContext` of every browser session.

## 21. LDAP Security Rules and Credential Handling

### 21.1. LDAP injection

Data passed to a search filter must be escaped per RFC 4515 or built with Spring `LdapQueryBuilder`:
- Characters `*`, `(`, `)`, backslash, and NUL have special meaning in LDAP filters.
- DN escaping differs from filter escaping.
- Never concatenate `"(uid=" + input + ")"`.
- Restrict base DN/search scope/size/time limits.
- Never let a directory search return all users/attributes unnecessarily.

### 21.2. Bind passwords and LDAP TLS

When using direct LDAP bind:
- Form login/browser→app must run over HTTPS.
- App→LDAP should use LDAPS or StartTLS/secured SASL per policy.
- Verify the CA chain/hostname; never bypass TLS validation.
- Never log passwords, bind DN/passwords, request bodies, or credentials.
- Rate-limit logins, prevent enumeration/brute force, and return appropriate generic errors.
- Never use a Domain Admin service bind just to look up groups.
- Avoid forwarding user passwords through a chain of microservices.

### 21.3. Returning appropriate errors

For end users:
- Wrong credentials → generic message, avoiding account existence disclosure.
- Unlinked identity → guide to link/contact support, do not auto-merge.
- Account disabled → report access denied per policy.
- Directory timeout → temporary service error, do not claim wrong password.
- Duplicate link → advise contacting admin/security support, do not reveal another user's account ID.

Internal logs should distinguish `DIRECTORY_NOT_FOUND`, `AUTH_BAD_CREDENTIALS`, `LINK_CONFLICT`, `ACCOUNT_DISABLED`, `DIRECTORY_TIMEOUT`, and `AUTHZ_DENIED` without containing secrets.

## 22. Three-Layer Testing

### 22.1. Directory lookup tests

| Test | Input | Expected |
|---|---|---|
| L1 | User has entry | Returns allowlisted attrs only, **no** Authentication created |
| L2 | User has no entry | Not found, does not conclude wrong password |
| L3 | Filter matches multiple entries | Reject ambiguous if used for identity resolution |
| L4 | UID contains special LDAP filter chars | Builder escapes properly, no injection |
| L5 | AD nested membership | Effective groups match policy |
| L6 | Directory account disabled | Status returned, app enforces account policy |
| L7 | Directory unreachable | Clear timeout, no default admin granted |
| L8 | Read-only bind credentials | Only granted directory permissions |
| L9 | Query outside search base | Does not leak out-of-scope data |

### 22.2. Direct authentication tests

| Test | Scenario | Expected |
|---|---|---|
| A1 | Valid username/password, LDAP bind succeeds | Authentication succeeds per account policy |
| A2 | Wrong password | Bad credentials |
| A3 | Entry exists but password is wrong | **No login** |
| A4 | User disabled/locked | Login rejected |
| A5 | No LDAP TLS or untrusted cert | Does not disable TLS to bypass |
| A6 | Group loader times out after bind | Does not auto-grant admin role |
| A7 | AD UPN vs uid difference | Lookup/auth match scope and convention |
| A8 | LDAP compare salted-hash config | Check compatibility, no NoOp in production |
| A9 | Form login rate limit | Blocks brute force and enumeration |
| A10 | User found but lacks app permission | May authenticate, yet 403 per policy |

### 22.3. Identity linking tests

| Test | Scenario | Expected |
|---|---|---|
| I1 | Valid OIDC iss+sub, authenticated local session, explicit intent | Link succeeds |
| I2 | Unvalidated external proof | No link |
| I3 | Local session unauthenticated/not recent enough | No link |
| I4 | External key already linked to same local ID | Idempotent/already linked |
| I5 | External key already linked to different local ID | CONFLICT, no overwrite |
| I6 | Same sub but different issuer | Two distinct identity keys |
| I7 | Matching email, different sub | No auto-merge |
| I8 | Email verified but local account unproven | No sensitive auto-link |
| I9 | Disabled account | No link/login |
| I10 | User from another tenant | Deny if outside policy |
| I11 | Concurrent link requests | Unique constraint allows only one winner |
| I12 | Callback state/nonce/CSRF mismatch | Reject |
| I13 | OIDC UserInfo.sub differs from ID Token.sub | Reject UserInfo data |
| I14 | SAML transient NameID | Not used as lifetime stable key |
| I15 | Unknown issuer/realm | Deny |
| I16 | Unlink last method | Follows account recovery policy, no lockout |
| I17 | JIT user first login | New account created with least privilege, audited |
| I18 | Duplicate AD object mapping | Reject ambiguous |
| I19 | Revoked link, login again | Does not auto-re-enable if policy forbids |
| I20 | Provider changes issuer/sub | Requires approved migration, no email auto-link |

**Integration tests:** require an LDAP/AD or test directory with real data, a protocol-compliant OIDC/SAML IdP or Kerberos KDC, the Spring Security filter chain, HTTP sessions, and database unique constraints. A plain mock principal does not prove authentication or linking security.

## 23. Troubleshooting by Pinpointing the Failing Layer

| Symptom | Suspected layer | Action |
|---|---|---|
| LDAP finds user but form login reports wrong password | Direct authentication | Check bind DN, password, LDAP TLS, account flags |
| User logs in via OIDC but app cannot find user | Identity linking/lookup | Check iss+sub, approved link, and onboarding |
| User logs in successfully but lacks permissions | Authority lookup | Check group-to-role mapping and tenant membership |
| LDAP search returns 2 entries | Directory resolution | Fix unique key/search scope, reject ambiguity |
| SSO user links to someone else's account | Identity linking | Check conflict/issuer/subject uniqueness, audit |
| User changes email and loses local account | Linking misused email | Use stable provider subject |
| SAML transient NameID changes every time | Subject contract | Choose stable attribute/persistent NameID per IdP |
| OIDC token valid but local email collides | Link policy | Do not auto-merge; require ownership proof |
| Kerberos principal valid but AD groups missing | Directory/authority lookup | Check realm/AD SID, nested groups, stale cache |
| Directory lookup has no password yet user hits password prompt | Authentication design | Distinguish service read bind vs user bind |
| User password valid yet app returns 403 | Authorization | Do not fix by bypassing roles |
| Group revoked yet session retains access | Cache/session | Invalidate, policy-version TTL, entitlement check |
| Directory outage breaks login | Availability | Retry/backoff/circuit breaker, fail closed |
| Different tenant with identical email | Identity namespace | Issuer/realm/tenant mapping and unique links |
| LDAP injection causes multi-user search | Query construction | Use escaped builder/parameters |
| OAuth/OIDC login unexpectedly asks for local password | Provider selection | Check Spring filters/chains; do not misconfigure DaoAuthenticationProvider |
| CAS/Kerberos/SAML login succeeds but unlinked | Account mapping | Explicit onboarding/JIT/linking, no email auto-merge |

**Standard debugging order:** *is credential/protocol verified?* → *does directory identity resolution return a single unique result?* → *does the external identity link have an approved target?* → *is the local account active?* → *is the group/role/tenant policy correct?* → *is any session/cache stale?*

## 24. Anti-Patterns to Avoid

1. **Lookup = login:** finding an email via LDAP search and creating an `Authentication`.
2. **Email = unique identity:** auto-linking OIDC/SAML to a local account by `mail` or `displayName`.
3. **Stripped realm:** confusing Kerberos `alice@REALM-A` with `alice@REALM-B`.
4. **Browser-supplied issuer:** taking the IdP issuer from a query header to construct an identity key.
5. **Fake external proof:** trusting self-parsed claims without verifying token/signature.
6. **UserInfo mix-up:** failing to check `UserInfo.sub` matches `ID Token.sub`.
7. **Direct bind over plain LDAP:** sending passwords without transport/trust protection.
8. **Directory admin bind:** using a Domain Admin account just to read memberships.
9. **LDAP filter string concatenation:** enabling LDAP injection.
10. **Group text = app admin:** turning all directory groups into authorities.
11. **Auto-JIT with `ROLE_ADMIN`:** making every valid external identity an admin.
12. **Link without local proof:** using an IdP account with someone else's email to hijack a local account.
13. **Missing unique constraint:** two link records with the same external key pointing to two users.
14. **Link race overwrite:** an UPDATE transferring ownership when already linked to someone else.
15. **No account lifecycle:** a disabled local user can still log in because an external token is valid.
16. **Trust all realms:** users from a partner realm automatically get internal roles.
17. **Session stale forever:** AD revokes a role, but the Spring session never refreshes.
18. **Ambiguous directory match:** picking the first entry from a multi-record search.
19. **Identity link = authorization:** having a link grants access to every tenant.
20. **Unlink without recovery:** removing the last credential locks out the account.

## 25. Design and Go-Live Checklist

- [ ] Clearly separate services: `DirectoryLookup`, `CredentialAuthenticator`, and `IdentityLinkService`.
- [ ] Directory lookup never creates a Spring `Authentication` on its own.
- [ ] Direct LDAP bind/password comparison is properly configured with TLS and rate limits.
- [ ] Federation protocols (OIDC/SAML/Kerberos/CAS) are verified by the framework before local mapping.
- [ ] Use OIDC `iss+sub`, never email, as the unique key.
- [ ] SAML stable subject is agreed upon in the IdP contract.
- [ ] Kerberos principal/realm and AD object ID are preserved.
- [ ] Local accounts always have a stable internal ID independent of email.
- [ ] Existing account linking requires local account proof + external proof.
- [ ] Link intent has state/nonce/CSRF, a TTL, and single-use enforcement.
- [ ] Links have atomic database uniqueness and never silently overwrite conflicts.
- [ ] Cross-tenant identity mapping has an approval policy.
- [ ] JIT is separated from linking and never auto-creates admins.
- [ ] User/group lookups use LDAP query builders/escaping with restricted search scope.
- [ ] Directory bind credentials use least privilege and a secret manager.
- [ ] Disabled/locked/revoked accounts and group changes are enforced in authorization.
- [ ] Authorities are mapped from an allowlist/policy and checked at the resource level.
- [ ] Caching/session revocation SLAs are defined.
- [ ] Never log passwords, raw tokens, keytabs, LDAP secrets, or sensitive profile data.
- [ ] Tests cover 0/1/n lookups, wrong passwords, invalid SSO proofs, link conflicts, races, and cross-realm/tenant cases.
- [ ] Audit traces capture link/unlink/migration operations with IDs that do not leak secrets.
- [ ] Distinct UX exists for not found, bad credentials, unlinked identity, access denied, and directory outage.

## 26. Review Questions

1. **Does directory lookup prove the browser is Alice?** No, it only finds/reads records.
2. **What does LDAP bind do?** The directory verifies credentials during bind authentication.
3. **How do LDAP search and LDAP bind differ?** Search reads data; bind authenticates access/credentials, and user-bind can be used for login.
4. **Does Spring LDAP bind need to read the user's password hash from the directory?** No.
5. **Does Spring LDAP bind use `UserDetailsService` like DAO form login?** Not in the same way; it uses `LdapAuthenticator` and an authorities populator.
6. **Is LDAP password compare the same as bind?** No, it is a different authentication mechanism.
7. **Why still query AD after OIDC login?** To fetch attributes/groups/account status per business policy.
8. **Which OIDC key is stable for identity linking?** The trusted `iss+sub` pair.
9. **Is a verified email enough to auto-link a local account?** Not by default.
10. **Is a SAML NameID always stable?** No; transient or other formats require an explicit contract.
11. **What should a Kerberos principal preserve?** Full principal and realm; optionally mapped to an AD stable ID.
12. **What happens if a directory entry exists but the password is wrong?** Direct auth fails.
13. **What if there is a verified IdP identity with no link yet?** Onboarding/JIT per policy or deny; never auto-merge by email.
14. **Can one external identity link to two local users?** Not if the uniqueness policy is one-to-one; conflicts must be rejected.
15. **Why does linking require two-sided proof?** To prevent the owner of an external account from taking over someone else's local account.
16. **Is JIT linking into an existing account?** No, it usually creates a new account under an explicit policy.
17. **How do you prevent LDAP injection?** Use parameterized searches/LDAP query builders and restrict scope.
18. **Why must a lookup returning multiple matches be rejected?** Because it is ambiguous which user object is right, risking account confusion.
19. **Does group membership automatically become `ROLE_ADMIN`?** No; an application permission allowlist is required.
20. **Does revoking a role immediately drop it from active sessions?** Not by default; TTL, invalidation, or live entitlement checks are required.
21. **Does direct password auth require HTTPS?** Yes, both client→app and app→directory must be protected.
22. **Does a service account used to read LDAP prove the browser user?** No.
23. **Does an `OAuth2Login` verified token replace LDAP password bind?** It can replace the user login mechanism, while subsequent directory lookup remains separate.
24. **What is the purpose of the `external_identity_links` table?** Connecting a stable external identity to a local user under controlled rules.
25. **What is the overarching principle?** Clearly separate lookup, authentication, and linking, then enforce authorization on the verified account/tenant/resource.

## 27. Official References

- Spring Security – LDAP Authentication, bind/password comparison, and authorities populator: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Spring Security – ActiveDirectoryLdapAuthenticationProvider JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring LDAP – Reference, LdapTemplate, and LdapQueryBuilder: https://docs.spring.io/spring-ldap/reference/
- Spring Security – OAuth2 Login Advanced Configuration, OidcUserService/authority mapping: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security – UserDetailsService and DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security – OIDC/OAuth2 client: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Kerberos/SPNEGO: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- OpenID Connect Core – §5.7 `iss+sub`, §5.3.2 UserInfo sub matching: https://openid.net/specs/openid-connect-core-1_0.html
- LDAP Filter escaping – RFC 4515: https://www.rfc-editor.org/rfc/rfc4515
- OWASP – LDAP Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

**Summary:** Directory lookup returns information about an identity and **does not prove the caller owns that identity**. Direct authentication verifies credentials via LDAP bind, password comparison, a local password encoder, or an equivalent verifier. Identity linking is the decision to bind an already-authenticated external identity to a local account, and must rely on a stable provider-scoped identifier, two-sided ownership proof, uniqueness/transactions, and auditing. In a Spring Security federation system, enforce a clean separation: **protocol verification → trusted principal → directory lookup if needed → approved identity link/local account → role/tenant/resource authorization**. That separation prevents critical mistakes like LDAP lookup-as-login, email auto-linking leading to account takeover, and granting application permissions merely because IdP authentication succeeded.
