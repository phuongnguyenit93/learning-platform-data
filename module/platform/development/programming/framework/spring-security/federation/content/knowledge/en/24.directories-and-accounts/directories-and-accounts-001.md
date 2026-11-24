# Role of LDAP and Active Directory as an Identity Source Behind an IdP

In a federated login architecture, **LDAP/Active Directory** is typically the **source of profile and account state** used by the **Identity Provider (IdP)**. It is the **IdP** that orchestrates the SSO session, verifies credentials via the appropriate mechanism, enforces MFA, maps attributes, and issues an **OIDC ID Token, SAML Assertion, or CAS Service Ticket**. The **Spring Security** application trusts the IdP according to the configured federation protocol; it must not treat an LDAP search result as proof that a user has authenticated.

High-level example:

~~~text
Employee Browser
   -> Spring Portal (OIDC RP / SAML SP)
   -> Corporate IdP (Keycloak, AD FS, or IAM solution)
        -> LDAP/Active Directory: account, groups, attributes, status
        -> IdP: authentication policy, MFA, session, claims
   -> Spring: protocol validation, local user linking, role/tenant
   -> Reports API / business resource
~~~

**Key takeaway:** LDAP/AD answers "what does the directory know about this identity and which mechanism can verify its credential?", the IdP answers "how was the login session proven and which claims am I allowed to release?", and Spring Security answers "is this issuer trusted and is the user allowed to perform this action?". These three responsibilities are related, but **not identical**.

This lesson belongs to the **Directories and Accounts** group in the **Spring Security - Federation** module. The content covers the directory model, LDAP bind/search, AD specifics, Keycloak User Federation, stable IDs, group mapping, account lifecycle, LDAPS/StartTLS, OIDC configuration in Spring, standalone Java 17 code, and practical testing. The `.example` domain is used for illustration only.

## 1. Division of Responsibilities: Directory, IdP, and Application

| Component | Responsible for | Does not prove on its own |
| --- | --- | --- |
| **LDAP server** | Querying/binding/updating LDAP entries | A valid OIDC/SAML federation token |
| **Active Directory Domain Services** | Directory users/groups, domain/account policies, Kerberos | Spring application roles |
| **IdP** | Login, MFA, SSO session, token/assertion, claim release | Business permissions for every application |
| **Identity broker** | Authenticating upstream IdP, issuing identity under a new issuer | That every upstream claim is trustworthy |
| **Spring Security RP/SP** | Verifying issuer, audience, signature, and protocol state; creating Authentication | That an AD password was verified by the app itself |
| **Local application** | Tenant, entitlement, roles, object authorization | Admin privileges inferred from AD Domain Admins |
| **IAM/HR/data owner** | Source of truth, schema, and offboarding | Immediate automatic revocation of all tokens/sessions |

An organization with 30 applications reduces risk by **centralizing LDAP bind credentials and directory schema at the IdP**, rather than having all 30 apps connect directly to DCs. However, the IdP is a critical trust boundary that requires HA, certificate validation, secret protection, and careful operations.

## 2. Federated Login Backed by LDAP/AD

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring Portal
    participant IDP as Enterprise IdP
    participant AD as LDAP/Active Directory
    U->>SP: GET /reports
    SP-->>U: Redirect OIDC Authorization Request
    U->>IDP: Login or IdP SSO session
    IDP->>AD: LDAP search user/status/groups when needed
    AD-->>IDP: Directory identity/attributes
    opt Choose password validation via directory
        IDP->>AD: User bind or secure credential verification
        AD-->>IDP: Success or deny
    end
    IDP->>IDP: MFA + session + protocol claim policy
    IDP-->>U: Authorization code redirect
    U->>SP: OIDC callback
    SP->>IDP: Exchange code over HTTPS
    IDP-->>SP: Tokens
    SP->>SP: Verify ID Token, issuer, audience, nonce/state
    SP->>SP: Local user, role, and tenant
    SP-->>U: Application session
~~~

This is an **OIDC Authorization Code flow** example. In SAML, the IdP issues an Assertion to the ACS; in CAS, the IdP/CAS issues a Service Ticket and the application validates the ticket. **Not all IdPs send passwords over LDAP**: they may use Kerberos/SPNEGO, passkeys, client certificates, delegated upstream login, or an existing SSO session.

A technical explanation should pinpoint exactly which step **actually proves the credential** and which step **only reads the user profile**.

## 3. LDAP Is a Protocol; AD Is a Directory System

LDAP v3 allows clients to perform **Bind**, **Search**, **Compare**, **Modify**, and controls according to a directory schema. The system providing LDAP can be OpenLDAP, 389 Directory Server, or AD DS; schemas differ.

Active Directory Domain Services also includes:

- **Domain Controller (DC)**, domains/forests/OUs, and directory replication.
- **Global Catalog (GC)** for searching across multiple domains with a partial attribute set.
- **Kerberos KDC**, service principals, and Windows account/group policies.
- Attributes `sAMAccountName`, `userPrincipalName`, `objectGUID`, `objectSid`, `memberOf`, and `userAccountControl`.
- Password expiration, lockout, and disabled status defined by AD policies.

**Do not equate AD DS with Microsoft Entra ID.** Entra ID is a cloud identity platform; if an enterprise syncs AD users to Entra, an application using Entra OIDC does not mean it is connecting directly to Entra via LDAP.

## 4. The LDAP Tree and Directory Entries

Example of a DN:

~~~ldif
dn: CN=Lan Nguyen,OU=Employees,DC=corp,DC=example
objectClass: person
objectClass: organizationalPerson
objectClass: user
cn: Lan Nguyen
displayName: Lan Nguyen
sAMAccountName: lnguyen
userPrincipalName: lan.nguyen@corp.example
mail: lan.nguyen@corp.example
department: Finance
memberOf: CN=ReportReaders,OU=Groups,DC=corp,DC=example
~~~

This is an **illustrative LDIF subset of fields**. AD `objectGUID`/`objectSid` typically have their own binary representation; the LDIF snippet does not list every mandatory attribute.

| Concept | Meaning | Example |
| --- | --- | --- |
| DN | Path locating an object in the tree | `CN=Lan Nguyen,OU=Employees,DC=corp,DC=example` |
| RDN | Name portion at the entry's position | `CN=Lan Nguyen` |
| Base DN | Root scope for an LDAP search | `OU=Employees,DC=corp,DC=example` |
| Scope | Base/one-level/subtree | Employees subtree only |
| LDAP filter | Criteria for finding entries | `(sAMAccountName=lnguyen)` |
| Entry UUID | Object ID from the directory | AD `objectGUID` |
| Attributes | Profile and metadata | `mail`, `displayName`, `memberOf` |

### Search is not authentication

An LDAP `search` only tells you that an entry exists and which attributes are readable. For example, finding a user with email `lan@corp.example` **does not mean the request came from Lan**. Authentication requires a user bind, Kerberos, an IdP-signed assertion, or the corresponding authentication mechanism.

Three search outcomes must be distinguished: **0 users** → deny; **1 user** → still requires credential validation/status check; **multiple users** → deny because it is not unique, never pick the first record to log in. Search filters must be scoped and protected against injection.

## 5. Service Bind vs. User Bind

An IdP LDAP connector typically performs:

~~~text
1. Service account bind with restricted READ permissions
2. Search user DN by username matching schema/OU
3. Check uniqueness, account enabled, and login restrictions
4. If password flow: bind/credential validation for the user
5. Apply MFA, risk-based authentication, IdP session
6. Issue identity to the registered application
~~~

**Service bind** uses a system account to **search**; it does not prove that the user has logged in. **User bind** uses the user's credential to authenticate against LDAP/AD according to policy.

Some IdPs use **Kerberos/SPNEGO** to verify the user and then use LDAP only to read profile/groups; there is no user password bind step. Therefore, the phrase "the IdP uses AD" must be clarified: **AD password authentication**, **Kerberos SSO**, or **directory lookup**.

The Spring Security LDAP reference explains that `LdapBindAuthenticationManagerFactory` uses the LDAP server to verify passwords, rather than using `UserDetailsService` to read a password hash and compare it itself. Never grant an app/IdP permission to read password hashes just to "authenticate on its own".

## 6. Keycloak User Federation: AD/LDAP as a Source Behind the IdP

Keycloak provides **User Federation → Add LDAP providers**. Common configuration fields:

| Property/Concept | Example or decision |
| --- | --- |
| Vendor | Active Directory or the corresponding LDAP vendor |
| Connection URL | `ldaps://dc01.corp.example:636` |
| Bind DN | `CN=svc-ldap-read,OU=Service Accounts,DC=corp,DC=example` |
| Bind Credential | Secret managed by a vault/secret manager |
| Users DN | `OU=Employees,DC=corp,DC=example` |
| Username LDAP attribute | `sAMAccountName` or `uid` per schema |
| RDN LDAP attribute | Field for the relative DN |
| UUID LDAP attribute | `objectGUID` for AD, `entryUUID` on many LDAP servers |
| User Object Classes | Select user entries, avoid out-of-scope computers/services |
| Search Scope/User LDAP Filter | Narrow down candidate entries |
| Import Users | Import/copy profile or read LDAP directly |
| Edit Mode | `READ_ONLY`, `WRITABLE`, `UNSYNCED` |
| Mappers | Attributes, groups, identity linking |
| Sync Settings | Full sync/changed users sync |

Field names and behavior may vary by **Keycloak version** and mapper configuration; verify against the documentation for your deployed version.

### Does Import Users copy AD passwords?

**No.** The Keycloak Server Administration Guide states that when Import Users is enabled, Keycloak can import/copy the **user profile** into the local DB and sync on-demand/periodically; **passwords are not imported**, and password verification is still performed by the LDAP/AD provider.

This does not mean every application can still log in offline. LDAP downtime, stale caches, and existing IdP sessions behave differently depending on the flow. **Never treat an LDAP cache as a password authority.**

### READ_ONLY, WRITABLE, and UNSYNCED

| Mode | Behavior | Caution |
| --- | --- | --- |
| `READ_ONLY` | Mapped user attributes are not written back to LDAP by the IdP | Worth considering when AD is authoritative |
| `WRITABLE` | Can update mapped fields/passwords per LDAP permissions | Requires ACLs, audit, ownership, write policy |
| `UNSYNCED` | Changes are kept in the IdP local store instead of LDAP | Can create two sources of truth for the same field |

**Changing Edit Mode or Import Users later does not necessarily update already-created mappers automatically.** Keycloak explicitly notes that some mapper configs are built from values at provider creation time; migrations must inspect each mapper, not just change a dropdown.

### User synchronization and caching

- **On-demand**: lookup/import when the user logs in or is queried for the first time.
- **Full sync**: iterate over users in scope; requires controlling DC/LDAP load and pagination.
- **Changed users sync**: processes only changed users per the provider's tracker, reducing load, but does not by default handle every deletion/role revocation immediately.
- **Mapper direct LDAP read**: some fields can be read directly instead of from the DB cache.
- **Group membership**: can use its own strategy/sync.

Keycloak recommends running an initial full sync and then scheduling periodic changed-users sync where appropriate. **Sync interval, replication lag, IdP sessions, token TTL, and Spring sessions are distinct layers**; never assume an AD group change takes effect immediately across every browser.

## 7. Stable Identifier Sources: Do Not Merge People by Email

| Identifier | Role | Stability/limitations |
| --- | --- | --- |
| AD `objectGUID` | Identity of an AD object | Preserved across rename/move within a forest; delete/recreate yields a new object |
| LDAP `entryUUID` | Entry ID where supported by server | Scoped to directory/provider and replication |
| DN | Locates the entry | Can change when OU/CN changes |
| `sAMAccountName` | Domain-scoped legacy login | Can change/be reused or collide across domains |
| `userPrincipalName` | UPN-formatted username | Suffix/name can change; not identical to email |
| `mail` | Contact attribute | Mutable, can be duplicated/shared/recycled |
| `objectSid` | Windows security principal | Distinct SIDHistory and migration semantics |
| OIDC `sub` | IdP subject identifier | Bound to `iss`; not implicitly equal to objectGUID |
| OIDC `iss` | Issuer trusted by the RP | Must be verified against token/metadata |
| `preferred_username` | Display username | Not guaranteed immutable |

**Microsoft confirms that an AD object's `objectGUID` does not change when renamed or moved**, whereas DN can change. Even so, GUID is not magic across delete/recreate, directory migrations, or different forests.

A safe two-tier link:

~~~text
Directory -> IdP:
  (LDAP provider ID, objectGUID) -> IdP internal user

IdP -> Spring:
  (verified issuer, OIDC sub) -> local user ID + tenant
~~~

**Do not replace `sub` with email** when linking accounts. If the issuer changes after an IdP migration, an approved identity-relinking procedure is required—do not auto-merge based on username/UPN.

### Binary objectGUID and Keycloak decoder

AD `objectGUID` is usually returned over LDAP as **16 binary bytes**, not a plain-text UUID string. The Keycloak Upgrading Guide 26.x includes changes regarding **Decode Binary Attribute As** and base64/uuid options for LDAP mappers.

Check during upgrades: raw ID values, decoded strings, linked users, group mappers, and SSO subjects before/after migration. Do not "fix" duplicate users by blindly deleting IdP records if a mapper changed representation.

### Multiple LDAP servers and failover

If a single LDAP provider lists multiple URLs, they must be **replicas of the same directory** with the same object UUID for a given user. Two independent directories—even with identical names/emails—can generate different `objectGUID`/`entryUUID` values. Keycloak docs warn that such a setup can cause duplicates or failures during failover. Each independent source needs its own provider or an explicit identity-linking architecture.

## 8. LDAP Attributes → IdP Profile → Protocol Claims

Example source data:

~~~text
LDAP AD:
  sAMAccountName = lnguyen
  mail = lan@corp.example
  displayName = Lan Nguyen
  givenName = Lan
  sn = Nguyen
  department = Finance
  memberOf = [ReportReaders, Employees, OtherGroups]
  userAccountControl = account status flags
  objectGUID = stable source object ID
~~~

IdP user model mapping might be:

~~~text
Keycloak user:
  username = lnguyen
  email = lan@corp.example
  firstName = Lan
  lastName = Nguyen
  internal federation link -> objectGUID + provider
~~~

And release only the necessary claims:

~~~json
{
  "iss": "https://login.corp.example/realms/staff",
  "sub": "a7f7b22b-cf08-42db-96b2-4ba671ca35a5",
  "aud": "reports-web",
  "name": "Lan Nguyen",
  "email": "lan@corp.example"
}
~~~

**This JSON is an illustrative claim subset**, not a complete/signed ID Token; in a real product, Spring verifies the signature, `iss`, `aud`, `exp`, nonce/state, and proper protocol flow.

| LDAP/AD field | IdP mapping | Should it be released to applications? |
| --- | --- | --- |
| `mail` | email | When genuinely needed, per privacy contract |
| `givenName`/`sn` | firstName/lastName | When needed for display |
| `displayName` | name | Display data, not an ID key |
| `objectGUID` | Stable internal user link | Usually no need to release raw GUID |
| `department` | Custom profile attribute | Only if the client needs it and is approved |
| `memberOf` | Group/role mapper | Restrict to app-specific role claims |
| `userAccountControl` | Account status input | Do not release raw internal flags to every RP |

**Email verified:** Having `mail` in LDAP does not by itself prove that the current owner verified the email address. Only set `email_verified=true` when the IdP has an appropriate source/trust contract and verification process. Never auto-link high-privilege accounts based on an untrusted email.

## 9. Active Directory Groups, Nested Membership, and App Roles

Example:

~~~text
User Lan
  direct group: FinanceAnalysts
FinanceAnalysts
  is member of ReportReaders
Domain Admins
  is unrelated to Reports Portal app role
~~~

A user's `memberOf` typically lists **direct groups**; in some cases nested/primary groups do not appear in a simple attribute read. AD provides `LDAP_MATCHING_RULE_IN_CHAIN` (OID `1.2.840.113556.1.4.1941`) for querying DN ancestry on supported attributes:

~~~ldap
(&(objectCategory=person)(objectClass=user)(memberOf:1.2.840.113556.1.4.1941:=CN=ReportReaders,OU=Groups,DC=corp,DC=example))
~~~

This is a **Microsoft AD extension**, not a portable filter across all LDAP servers. In trees with deep OU/group nesting, the query can be expensive; evaluate search scope, paging, caching, group retrieval strategy, Global Catalog partial attributes, and tests.

AD also has `tokenGroups` (SID-based), group types, `primaryGroupID`, cross-domain groups, and distribution groups. **Do not turn every membership into a `GrantedAuthority`.**

A good mapping:

~~~text
AD group approved for Reports:
  CN=ReportReaders,OU=Groups,DC=corp,DC=example

IdP claim for reports-web:
  roles = ["report_viewer"]

Spring local authorities:
  ROLE_REPORT_VIEWER only after issuer/token validation and local policy

AD Domain Admins:
  does NOT imply ROLE_ADMIN in Reports Portal
~~~

**Domain Admins is an infrastructure privilege, not blanket business authorization.** Define a group/role allowlist per application/tenant with a data owner and periodic review; never use a regex matching group names containing "admin".

## 10. Disabled, Locked, and Expired Accounts

An LDAP Search can still return a disabled user; therefore, **finding a user does not prove the account is active**.

In AD:
- `userAccountControl` contains the bit **ACCOUNTDISABLE = 0x0002**.
- Lockout, password expiration, `accountExpires`, and logon restrictions may depend on other attributes/computed values such as `msDS-User-Account-Control-Computed`.
- An LDAP user bind may reject credentials per directory policy, yet a previously issued IdP session may remain active.
- A Spring local HTTP session or JWT has its own lifetime.

Example AD-specific filter excluding disabled accounts:

~~~ldap
(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))
~~~

`1.2.840.113556.1.4.803` is the AD bitwise AND matching rule. **This is only a search condition**; it does not replace a full account status/MFA/revocation policy.

Hypothetical lifecycle:

~~~text
09:00 HR decides offboarding
09:01 AD disables account
09:02 IdP LDAP cache may still hold stale data
09:05 Existing OIDC token may not have expired yet
09:10 Changed-users sync may only run now
09:15 Spring web session may still be alive
~~~

These timestamps are **not defaults**. You must measure the **deprovisioning SLA**: the maximum time from directory disable/group revocation until Spring endpoints reject access. Architecture-dependent solutions include token TTL, revocation/introspection, IdP session termination, back-channel logout, policy checks at the resource server, event-driven SCIM/provisioning, or local active-account lookup.

## 11. LDAPS/STARTTLS and LDAP Signing/Channel Binding

The IdP connects to AD on commonly used ports:

| Endpoint | Port | Notes |
| --- | --- | --- |
| LDAP | TCP 389 | Can use STARTTLS or SASL; **never plaintext simple bind** |
| LDAPS | TCP 636 | TLS starts before LDAP operations |
| Global Catalog LDAP | TCP 3268 | Forest search, partial attribute set, no TLS by default |
| Global Catalog LDAPS | TCP 3269 | GC over TLS |
| Kerberos | UDP/TCP 88 | When flow uses Kerberos/Windows SSO |
| DNS | TCP/UDP 53 | DC/KDC/hostname discovery |

**LDAPS differs from HTTPS**: both use TLS, but LDAP inside is not HTTP.

The IdP must verify:
1. Domain Controller CA/PKIX certificate chain.
2. **Hostname SAN/FQDN** matching the DC the connector calls.
3. Certificate validity and security algorithms.
4. Bind credentials never appear on a plaintext connection.
5. Server failover and DNS routing to trusted endpoints.

**Do not use a trust-all `X509TrustManager`, hostname verification bypass, or `TLS_REQCERT never`** to work around PKIX errors. Fix the CA chain/certificate SAN/truststore via the PKI team.

Microsoft distinguishes these layers:
- **LDAP signing:** integrity/authenticity of a SASL LDAP session when configured, especially without TLS.
- **SASL sealing:** confidentiality/integrity for applicable SASL mechanisms.
- **TLS LDAPS/STARTTLS:** confidentiality/integrity and server identity for LDAP.
- **Channel Binding Token (CBT):** binds SASL authentication to the TLS session, helping mitigate relay attacks in relevant mechanisms.

**Simple bind over TLS does not automatically use SASL channel binding the way Kerberos SASL bind does.** Under newer AD signing/CBT policies, verify compatibility of the IdP LDAP connector/bind mechanism—do not weaken security policy just to "make login work".

## 12. Service Bind Account, Secrets, and Permission Scope

Example of an IdP search account:

~~~text
DN:
  CN=svc-ldap-reader,OU=Service Accounts,DC=corp,DC=example

Allowed:
  read specific user profiles/groups under approved OUs

Forbidden:
  Domain Admin
  create/delete users
  modify security groups
  read password material
  blanket write rights
~~~

Requirements:
- Store the bind password in a secret manager/IdP credential store; never commit to Git or log it.
- Rotate credentials with coordinated rollout, auditing, and an owner.
- Restrict OUs, attributes, group search rights, timeouts, and result size.
- Monitor bind failures/expiry/lockout.
- Never use an AD administrator account to "fix" `LDAP error 50 insufficientAccessRights`; grant the exact read ACL if genuinely needed.
- Separate the service bind credential from user login credentials.
- Do not expose username enumeration or raw directory entries in client-visible errors.

**Permission to read the directory does not automatically grant permission to release data to applications**: the IdP must enforce a claim/attribute release policy per client.

## 13. Spring Security as an OIDC RP, Not Binding Directly to LDAP

Spring Boot OIDC client example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-oidc:
            provider: corp-idp
            client-id: reports-web
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp-idp:
            issuer-uri: "https://login.corp.example/realms/staff"
~~~

`issuer-uri` specifies the **OIDC issuer**, not `ldaps://dc01...`. Spring validates metadata/discovery, the Authorization Code callback, state/nonce, and the ID Token's signature/issuer/audience per the supported flow. The LDAP connector/Bind DN belongs inside the IdP's scope.

Illustrative Spring JavaConfig (requires Spring dependencies; not standalone Java):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CorporateOidcSecurity {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/reports/**").authenticated()
                        .anyRequest().denyAll())
                .oauth2Login(login -> {})
                .build();
    }
}
~~~

This sample only establishes an authenticated user; **business roles and tenant/object authorization must still be added by design**. Map verified group/role claims to `GrantedAuthority` using an allowlist—never take raw `memberOf` directly from the browser. For API resource servers using bearer tokens, `oauth2ResourceServer().jwt()`/`JwtAuthenticationConverter` serves a different role than OIDC browser login.

### Direct LDAP login is a different path

Spring Security provides the `spring-security-ldap` module with `LdapBindAuthenticationManagerFactory` for when **Spring itself receives the username/password**, for example:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;

AuthenticationManager directLdapManager(
        BaseLdapPathContextSource source) {
    LdapBindAuthenticationManagerFactory factory =
            new LdapBindAuthenticationManagerFactory(source);
    factory.setUserSearchBase("ou=people");
    factory.setUserSearchFilter("(uid={0})");
    return factory.createAuthenticationManager();
}
~~~

This snippet is a **fragment inside a Spring project**, not an OIDC federation pattern. With AD, `sAMAccountName`/UPN and `ActiveDirectoryLdapAuthenticationProvider` may be used depending on version. Do not blindly copy `uid` without checking the schema. If an IdP is already in use, do not add an LDAP password check inside the OIDC callback to "increase security"; it can break federation and demand unnecessary credentials.

## 14. Java JNDI LDAP Searches Must Prevent Injection

Concatenating raw user input directly into an LDAP filter is a risk:

~~~text
WRONG:
  "(&(objectClass=user)(sAMAccountName=" + userInput + "))"
~~~

Input containing `*`, `(`, `)`, `\`, or NUL can alter the filter's meaning. Use **JNDI parameterized filters** or proper RFC 4515 escaping. This is a Java/JNDI fragment that runs when variables/environment and a real LDAP server are provided; it has no fixed stdout:

~~~java
import java.util.Hashtable;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.directory.*;

Hashtable<String, Object> env = new Hashtable<>();
env.put(Context.INITIAL_CONTEXT_FACTORY,
        "com.sun.jndi.ldap.LdapCtxFactory");
env.put(Context.PROVIDER_URL, "ldaps://dc01.corp.example:636");
env.put(Context.SECURITY_AUTHENTICATION, "simple");
env.put(Context.SECURITY_PRINCIPAL, bindDn);
env.put(Context.SECURITY_CREDENTIALS, bindSecret);
env.put("com.sun.jndi.ldap.connect.timeout", "5000");
env.put("com.sun.jndi.ldap.read.timeout", "5000");

DirContext directory = new InitialDirContext(env);
try {
    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setCountLimit(2);
    controls.setReturningAttributes(
            new String[]{"mail", "displayName", "objectGUID"});
    String filter =
            "(&(objectCategory=person)(objectClass=user)(sAMAccountName={0}))";
    NamingEnumeration<SearchResult> results = directory.search(
            "OU=Employees,DC=corp,DC=example",
            filter,
            new Object[]{userInput},
            controls);
    try {
        while (results.hasMore()) {
            SearchResult entry = results.next();
            // Only fields within the data contract may be used.
        }
    } finally {
        results.close();
    }
} finally {
    directory.close();
}
~~~

`bindDn`, `bindSecret`, and `userInput` are variables that a real project must supply, not hardcoded secrets. `{0}` is handled by the JNDI substitutor instead of raw text interpolation. A search result still **does not prove the user has authenticated**, and `objectGUID` may be binary and require proper decoding. TLS validation/connection pooling/failover/timeouts/ACLs must be implemented in production.

## 15. Standalone Java 17: Stable Identity Link and App Role

This pure Java program simulates **directory identity**, email/login rename, IdP issuer, and local role mapping. It has **no** LDAP server, OIDC signature, AD group mapper, TLS, or actual user authentication; the boolean `fresh` represents the assumption that a directory status check mechanism exists, and **must never be hardcoded to `true` in production**.

Create file **`DirectoryBehindIdpDemo.java`**:

~~~java
import java.util.Set;
import java.util.TreeSet;

public class DirectoryBehindIdpDemo {

    record DirectoryUser(
            String objectGuid, String login, String email,
            boolean active, Set<String> groups) {}

    static final String TRUSTED_ISSUER =
            "https://login.corp.example/realms/staff";

    static String identityKey(String issuer, DirectoryUser user) {
        return issuer + "|" + user.objectGuid();
    }

    static Set<String> roles(DirectoryUser user) {
        Set<String> result = new TreeSet<>();
        if (user.groups().contains("APP_REPORT_READERS")) {
            result.add("ROLE_REPORT_VIEWER");
        }
        return result;
    }

    static String authorize(
            String issuer, DirectoryUser user, boolean fresh) {
        if (!TRUSTED_ISSUER.equals(issuer)) {
            return "DENY: untrusted issuer";
        }
        if (!fresh) {
            return "DENY: stale directory state";
        }
        if (!user.active()) {
            return "DENY: disabled directory account";
        }
        if (!roles(user).contains("ROLE_REPORT_VIEWER")) {
            return "DENY: missing application grant";
        }
        return "ALLOW: ROLE_REPORT_VIEWER";
    }

    public static void main(String[] args) {
        String guid = "75b43cc2-21d9-4ce5-a9c5-d6d3bf08fa20";

        DirectoryUser user = new DirectoryUser(
                guid, "lnguyen", "lan@corp.example", true,
                Set.of("APP_REPORT_READERS", "Domain Admins"));

        DirectoryUser renamed = new DirectoryUser(
                guid, "lan2", "lan.new@corp.example", true,
                user.groups());

        DirectoryUser disabled = new DirectoryUser(
                guid, "lan2", "lan.new@corp.example", false,
                user.groups());

        DirectoryUser noGrant = new DirectoryUser(
                guid, "lnguyen", "lan@corp.example", true,
                Set.of("Domain Admins"));

        System.out.println("Stable link: "
                + identityKey(TRUSTED_ISSUER, user).equals(
                    identityKey(TRUSTED_ISSUER, renamed)));

        System.out.println("Email changed: "
                + !user.email().equals(renamed.email()));

        System.out.println("App roles: " + roles(user));

        System.out.println("Domain admin became app admin: "
                + roles(user).contains("ROLE_ADMIN"));

        System.out.println("Valid: "
                + authorize(TRUSTED_ISSUER, user, true));

        System.out.println("Disabled: "
                + authorize(TRUSTED_ISSUER, disabled, true));

        System.out.println("Stale: "
                + authorize(TRUSTED_ISSUER, user, false));

        System.out.println("Wrong issuer: "
                + authorize("https://untrusted.example", user, true));

        System.out.println("Missing app group: "
                + authorize(TRUSTED_ISSUER, noGrant, true));
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac DirectoryBehindIdpDemo.java
java DirectoryBehindIdpDemo
~~~

**Exact stdout:**

~~~text
Stable link: true
Email changed: true
App roles: [ROLE_REPORT_VIEWER]
Domain admin became app admin: false
Valid: ALLOW: ROLE_REPORT_VIEWER
Disabled: DENY: disabled directory account
Stale: DENY: stale directory state
Wrong issuer: DENY: untrusted issuer
Missing app group: DENY: missing application grant
~~~

**Interpretation:** The ID of the same AD object does not change on rename in the model; email is not a stable primary key; "Domain Admins" is not granted Spring admin privileges; disabled, stale state, another issuer, or missing approved group are all denied per the **simulated policy**. In real Spring, checking the issuer is not just a string comparison: you must use the framework's OIDC/SAML/CAS validator to verify signature/audience/expiry and state/nonce per protocol. The app may need a separate user status/revocation check to know whether directory data is still fresh.

## 16. Account Lifecycle and Token/Session Cache

A user may be disabled in AD at time T while the following still persist:
- AD replication lag between DCs.
- IdP LDAP cache or imported user record.
- IdP SSO session from a previous login.
- Unexpired OIDC ID/Access Token.
- Spring Security local HTTP session.
- API permission cache.

~~~text
09:00 HR triggers offboarding
09:01 AD account disabled
09:03 IdP profile cache may be stale
09:05 Existing JWT may still be within exp
09:10 LDAP changed-users sync may run
09:15 Spring session may still be valid
~~~

These timestamps are **hypothetical**. Define and measure a **deprovisioning SLA**, using appropriate mechanisms: short token TTL, revocation/introspection, session termination, event-driven provisioning, or policy checks when accessing sensitive resources. Do not assume an LDAP directory outage must fail every existing login, but **never fail-open** new authentications when credentials/sessions have not been verified.

## 17. Multi-Domain AD, GC, and Directory Failover

Global Catalog enables searching across multiple AD domains, but it usually holds only a **partial attribute set**, not every directory attribute. The IdP may need to query the specific domain DC to retrieve additional fields. Do not simply switch the URL from LDAP 636 to GC 3269 and assume all attribute/group mappers behave identically.

With forest trusts, LDAP/GC lookups are also subject to DNS, firewalls, AD ACLs, referrals, and name suffix routing. A trust between Kerberos realms does not automatically grant permission to read all directory entries. An alternative for many organizations is **SCIM** synchronization or OIDC/SAML federation through an identity broker, avoiding exposing direct network access to Domain Controllers outside the enterprise.

## 18. Mandatory Tests by Layer

| Case | Expected outcome |
| --- | --- |
| Valid LDAPS CA/SAN | IdP connects successfully and verifies server identity |
| Untrusted CA / wrong hostname cert | TLS fails, no trust-all |
| Plain LDAP simple bind | Blocked by policy; password is not sent in cleartext |
| Wrong service bind credential | Authn/search failure and alert |
| Wrong search base DN | User not found, appropriate directory error reported |
| Duplicate usernames | Does not auto-link wrong provider identities |
| Filter injection | Parameterization/escaping blocks broad search |
| AD account disabled/expired | New login denied per IdP policy |
| Rename/move AD user | Same objectGUID preserves identity link |
| Delete/recreate with same email | Does not inherit old local account/roles |
| Import Users ON | Mapped profile imported, LDAP password not imported |
| READ_ONLY mode | Does not write directory fields outside policy |
| Changed-users sync | Group/department updated within SLA |
| Nested group | Only app-approved roles are mapped |
| Domain Admins group | Does not auto-grant ROLE_ADMIN |
| GC query | Does not assume every attribute exists in GC |
| LDAP failover | Replicas share UUID, avoid independent directories |
| objectGUID decoder upgrade | No duplicate/mismatched user links |
| OIDC issuer/signature/audience | Spring rejects invalid tokens |
| SAML assertion signature/audience | Spring rejects invalid assertions |
| User disabled after login | Access ends within revocation SLA |
| PII minimization | Tokens contain no extra fields/excess group memberships |
| Directory down | IdP has a fail policy; does not turn anonymous login into authenticated |
| Cross-tenant access | Spring local authorization denies |
| Java demo | Compiles/runs with exact stdout shown in section 15 |

A unit test mocking `OidcUser` only helps test roles/controllers; it **does not prove** LDAPS trust, user bind, group mappers, token issuance, or deprovisioning. You must test IdP↔AD, IdP↔Spring, and business authorization.

### Diagnostic tools

In an authorized lab:

~~~bash
ldapsearch -x \
  -H ldaps://dc01.corp.example:636 \
  -D "CN=svc-ldap-reader,OU=Service Accounts,DC=corp,DC=example" \
  -W \
  -b "OU=Employees,DC=corp,DC=example" \
  "(&(objectCategory=person)(objectClass=user)(sAMAccountName=lnguyen))" \
  dn mail displayName
~~~

`-W` prompts for the password interactively; `-x` specifies simple bind only when already using **LDAPS with certificate verification**. Do not use `-ZZ` with `ldaps://` because one is STARTTLS and the other is TLS from the start; choose based on the endpoint and tool. This is a search request, not verification of an OIDC login. There is no fixed stdout because the host and DN are illustrative.

## 19. Common Errors and Fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| LDAP error 49 | Invalid user or service bind credential | Identify which account was rejected; do not log secrets |
| LDAP error 32 | Wrong Base DN/OU | Verify directory namespace |
| LDAP error 50 | Insufficient access rights | Grant minimal read ACL, not Domain Admin |
| `PKIX path building failed` | Wrong CA chain/truststore | Fix trusted CA/hostname |
| User not found | Search filter/scope or replication lag | Check unique identity, base DN |
| User logs into IdP, Spring misses email | Attribute mapper/scopes/sync | Check IdP claim release; do not query AD password directly |
| Roles lost after OU change | Group mapping relied on old DN | Use a stable identity/group contract |
| Duplicate identities | Email/username collision or UUID format change | Check provider+object ID and migration |
| Spring returns 403 | Insufficient local RBAC/tenant | Check application, do not widen LDAP bind rights |
| Disabled user still has session | Token/session TTL or stale cache | Revocation/deprovision SLA |
| App receives unintended admin role | Mapped AD groups too broad | App-specific allowlist and review |
| Slow recursive group search | Group nesting and LDAP query scope | Tune matcher, indexes, cache |
| GC missing field | Partial attribute set | Query the specific domain DC or adjust data contract |
| IdP outage | Directory connection/credentials/MFA component | Classify network/TLS/bind/IdP protocol |

**Runbook in order:** (1) directory entry/account state; (2) LDAP connector and bind/search; (3) IdP authentication/session/claims; (4) Spring protocol validation; (5) local business authorization. Never fix a Spring 403 by granting Domain Admin to the IdP service bind.

## 20. Implementation and Operations Checklist

- [ ] Distinguish directory from IdP and Spring RP/SP.
- [ ] Have an owner for schema, authoritative attributes, and account lifecycle.
- [ ] Search is not used in place of authentication.
- [ ] Service bind credentials are protected and have minimal read permissions.
- [ ] Appropriate LDAPS/STARTTLS/SASL, with certificate chain/hostname verified.
- [ ] Do not disable LDAP signing/CBT policy just to support legacy clients.
- [ ] LDAP filters use escaping/parameterization, with restricted search scope.
- [ ] Keycloak Import Users/Edit Mode/sync are verified for the exact version.
- [ ] LDAP passwords are not copied into the IdP DB in this federation model.
- [ ] Use `objectGUID`/`entryUUID` with source namespace; never DN/email as an immutable key.
- [ ] OIDC user linking uses verified `(iss, sub)`.
- [ ] Group mapper handles nested groups/role allowlist without auto-granting admin.
- [ ] Disabled, locked, and expired accounts have clear policies.
- [ ] Token/session/cache/revocation SLAs are monitored.
- [ ] Claims per application are minimized for PII and group count.
- [ ] GC partial attributes and multi-domain failover are tested.
- [ ] Spring `oauth2Login`/`saml2Login` validate issuer, audience, and signature properly.
- [ ] App local roles, tenant, and object authorization continue operating independently.
- [ ] Have a runbook and rollback plan for LDAP provider, Keycloak upgrade, and issuer migration.

## 21. Official Documentation

1. [RFC 4511 — LDAP v3](https://www.rfc-editor.org/rfc/rfc4511): bind/search and protocol.
2. [RFC 4513 — LDAP Authentication and Security](https://www.rfc-editor.org/rfc/rfc4513): credential validation and transport.
3. [RFC 4515 — LDAP Filter Syntax](https://www.rfc-editor.org/rfc/rfc4515): escaping/filter injection.
4. [Spring Security — LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): direct bind, LDAP provider, and Active Directory.
5. [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): Spring RP authentication flow.
6. [Spring Security — SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html): Spring SP Assertion validation.
7. [Keycloak — Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/): LDAP/AD User Federation, sync, and mappers.
8. [Keycloak — Upgrading Guide](https://www.keycloak.org/docs/latest/upgrading/): binary LDAP attribute decoder behavior.
9. [Microsoft — Object Names and Identities](https://learn.microsoft.com/en-us/windows/win32/ad/object-names-and-identities): objectGUID and DN stability.
10. [Microsoft — UserAccountControl](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/useraccountcontrol-manipulate-account-properties): disabled flag.
11. [Microsoft — Search Filter Syntax](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/search-filter-syntax): nested group matching rules.
12. [Microsoft — LDAP Channel Binding](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding): TLS, signing, SASL, and CBT.
13. [Microsoft — Configure LDAPS Certificates](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/configure-ldap-signing-certificates): AD DC cert and TLS.
14. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer/subject/ID Token validation.

**Summary:** LDAP/AD acts as the **identity source behind the IdP**; the IdP authenticates sessions by policy and issues tokens/assertions; Spring Security verifies the issuer/protocol and then applies local RBAC/tenant rules. Having an LDAP record does not mean the user is logged in, an AD group does not automatically become an app admin, and disabling an AD account does not automatically revoke all live tokens/sessions. Prioritize stable IDs, TLS, least privilege, claim minimization, and E2E revocation tests.