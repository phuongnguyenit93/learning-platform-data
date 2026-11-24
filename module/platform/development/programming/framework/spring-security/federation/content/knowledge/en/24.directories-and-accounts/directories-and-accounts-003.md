# Loading Internal Groups or Attributes After Federated Authentication

## 1. The Problem: The IdP Identifies the User, the App Must Still Decide Permissions

A Spring Security application using **OIDC, SAML2, CAS, or Kerberos** typically delegates identity authentication to another system. Once the IdP/KDC/CAS authenticates successfully, the application only knows **who the external user is**; that is not enough to know which internal account they hold, which department/group/tenant they belong to, or which data they may read, approve, export, or delete.

Example:

~~~text
OIDC authenticated identity:
    issuer = https://idp.example.org/realms/corp
    sub = opaque-123

Internal identity binding:
    (OIDC, issuer, sub) -> account_id = 41

Local directory:
    account_id=41, status=ACTIVE
    tenant_id=corp, membership=ACTIVE
    groups=[FINANCE_READER, CASE_AGENT]

Approved policy:
    corp:FINANCE_READER -> APP_REPORT_READ
    corp:CASE_AGENT -> APP_CASE_WRITE

Spring authorization:
    /corp/reports requires APP_REPORT_READ
    data queries must still enforce tenant_id=corp
~~~

**Successful federated authentication does not automatically grant full application access.** You must separate:

1. **Federated authentication:** verify the OIDC ID Token/code, `SAMLResponse`, CAS service ticket, or Kerberos service ticket.
2. **Identity binding:** bind the verified identity to an **internal account ID**.
3. **Internal directory loading:** load account status, membership, groups, and attributes from an authoritative source.
4. **Authority mapping:** use an allowlist policy to convert groups/attributes into **`GrantedAuthority`** or business permissions.
5. **Resource authorization:** check role/tenant/owner/operation at the service/database layer, even after a session has been created.

This lesson belongs to the **Directories and Accounts** group of **Spring Security - Federation**. Java examples use **Java 17+**, Spring Boot **3.3.5**, and Spring Security **6.x**. All `example.org` issuers/tenants/subjects are dummy data, not a live IdP.

### Learning Outcomes

- Distinguish external claims from internal attributes and authorization authority.
- Know how to choose the account key **(protocol, trusted issuer, stable subject)**, avoiding auto-linking by email.
- Understand the roles of **LDAP/Active Directory, local DB, SCIM/IGA, and HR data**.
- Know how to load groups in an **OIDC user service**, in a SAML2 response converter, or via a local `UserDetailsService` for CAS/Kerberos.
- Create an accurate **group → permission** policy with tenant scoping, without auto-mapping to `ROLE_ADMIN`.
- Evaluate timing, caching, stale authorities, offboarding, nested groups, LDAP injection, and directory outages.
- Run a standalone Java 17 example, configure Spring OIDC + JDBC, and test denial scenarios as well.

## 2. Trust Boundary: Data Must Be Loaded After Authentication

~~~text
Browser
    |
    v
Spring Security protocol filter/provider
  OIDC: code exchange + ID Token validation
  SAML2: XML Signature + issuer + audience + subject confirmation
  CAS: validate service ticket with CAS server
  Kerberos: GSS context with SPN/keytab
    |
    v
Trusted external identity
  (protocol, issuer/realm, stable subject)
    |
    v
Server-side identity_links
  -> internal account_id
    |
    v
Directory / internal DB / IAM
  -> active account?
  -> tenant membership?
  -> groups, department, manager, cost center?
    |
    v
Explicit local authority policy
  -> allowed business permissions
    |
    v
Spring Authentication/GrantedAuthority
    |
    v
Service + resource + tenant authorization
    |
    v
Database WHERE tenant_id = authorizedTenant
~~~

**Never perform local authority mapping based on an email/header/issuer self-asserted by the browser before the framework verifies federation.** A valid SAML/JWT signature only proves that the token came from a trusted issuer and passed protocol validations; the signature **does not by itself decide** whether that issuer has authority to grant `ROLE_ADMIN`, tenant membership, or specific business permissions.

For example, if a user from a Partner IdP has a signed claim **department=Finance**, the application must not automatically let them read Corp's financial data. You must check which identities, groups, or tenant memberships the IdP is authorized to assert under your organization's **trust contract**.

## 3. Which Attributes Should Be Read from Internal Sources?

| Data | Common authoritative source | Used by application to | Risk if sourced incorrectly |
| --- | --- | --- | --- |
| Internal account ID | Local database/IGA | Stable user key, audit, foreign keys. | Email collisions merge wrong users. |
| Account enabled/locked | IAM/local DB/HR workflow | Decide whether login or access is allowed. | IdP login passes while app account is disabled. |
| Tenant membership | Membership DB/IGA | Permission to select a tenant. | Cross-tenant data access. |
| Groups/roles | AD/LDAP/local groups/SCIM | Input to permission policy. | Out-of-scope groups become admin. |
| Department/cost center | HR/IGA/directory | ABAC, routing, departmental reporting. | Fake/unapproved new department strings. |
| Manager/approval chain | HR/IGA | Approval workflows. | A manager gets treated as system-wide admin. |
| Display name/job title | Directory/HR | Profile UI. | Using display info as an account key. |
| Permission version | IAM/authorization store | Revalidation and session/cache invalidation. | Revoked permissions stay usable too long. |
| Tenant/account risk flags | Business authorization store | Block/step-up per policy. | Sensitive APIs skip fresh condition checks. |

**A group is not necessarily a simple string.** A directory may return multiple group DNs, `objectGUID`s, group IDs, or nested groups; you must distinguish direct vs. transitive membership, enforce size limits, and guard against cycles. Do not assume `memberOf` in Active Directory returns all nested groups or that every LDAP directory shares the same schema.

## 4. Linking an External Principal to a Local Account

### 4.1. OIDC: use verified issuer + subject

An OIDC ID Token contains **`iss`** and **`sub`**. Once Spring Security OIDC authentication succeeds, the pair:

~~~text
iss = https://idp.example.org/realms/corp
sub = opaque-123
~~~

is used to look up the identity link. **`sub` is stable within the scope of an issuer**, though it may be pairwise per client; `issuer`/`sub` can change during an IdP migration. There must be a formal process for changing or linking verified accounts.

**Never use `email`/`preferred_username` as a globally unique key**: emails change, get reassigned, or collide across IdPs; `email_verified` confirms a property asserted by the provider, not permission to merge every account sharing an email.

### 4.2. SAML2: IdP issuer + stable subject per trust contract

~~~text
protocol = SAML2
issuer = https://saml.corp.example.org/idp
stableSubject = immutableEmployeeId
              or persistent NameID per contract
~~~

**NameID has multiple formats**: transient, persistent, email. A transient NameID is unsuitable as a long-term account ID; an email-format NameID is not inherently immutable. Only after Spring/OpenSAML validates signature, issuer, audience, time, recipient, and correlation should you read `AttributeStatement` and map the identity.

**`registrationId` is not a tenant ID**: one `RelyingPartyRegistration` can authenticate users for multiple tenants, or one IdP can use multiple registrations. Do not grant membership just because the ACS URL contains a tenant name.

### 4.3. CAS and Kerberos

- **Native CAS:** username is trusted after the service ticket is verified by the CAS validator against the right service. If there are multiple CAS realms/servers, namespace the identity by CAS trust domain; username `alice` from CAS A may differ from `alice` from CAS B.
- **Kerberos:** a verified principal includes a realm, e.g., **`alice@EXAMPLE.ORG`**; never strip `@REALM` and merge with `alice@OTHER.ORG`.
- **LDAP username** and federated subject are not implicitly identical. Link via an internal identity registry with an owner, status, and audit trail.

### 4.4. The `identity_links` table

~~~sql
CREATE TABLE app_accounts (
    account_id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE identity_links (
    protocol VARCHAR(16) NOT NULL,
    issuer VARCHAR(255) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    account_id BIGINT NOT NULL REFERENCES app_accounts(account_id),
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (protocol, issuer, subject_id)
);
~~~

This is a **server-controlled link**, not user-POSTed data. The same subject across two issuers represents two different identities. Multiple external identities may link to one internal account, but only through an approved **verified account linking** workflow, never based on email/`displayName`.

If the identity link is missing, inactive, or conflicting, the system should **deny by default** or route the user to an onboarding flow with no sensitive privileges—never auto-grant `ROLE_ADMIN` because the issuer is "trusted".

## 5. Sources of Internal Groups and Attributes

### Local DB

Suitable when groups/permissions are business concepts like **`FINANCE_READER`, `CASE_AGENT`, `REPORT_APPROVER`**, or tenant memberships. The database provides constraints, auditing, transactions, permissions, and versioning for revocation. Lifecycle must still be synced with IdP/HR/IGA.

### LDAP / Active Directory

Suitable when the company manages groups in a directory. You can use:

- **`objectGUID`/`entryUUID`** or an immutable directory object ID to bind to the account.
- **`memberOf`**, group member queries, or directory-specific mechanisms for nested groups.
- **`employeeID`, department, manager, cost center, account flags** per schema.
- Mapping **directory group DN/object ID** to a local permission policy.

Connect to LDAP over **LDAPS/StartTLS with TLS certificate/hostname validation**, a **read-only least-privilege** account, restricted search base, timeouts, paging, and size limits. Avoid string-concatenated LDAP filters from user input; use **`LdapTemplate`** / a query builder with schema-appropriate escaping.

**LDAP lookup after federated authentication does not force the user to LDAP-bind again with a password.** The app already authenticated via the IdP; the directory client uses its own service credential/read access. LDAP group query and LDAP password-based authentication are two distinct steps.

### SCIM, IGA, HR

**SCIM** can sync users/groups, disabled statuses, and provisioning events into the local database; **IGA/HR** is the source for organization/department/manager. This makes login faster than querying multiple systems synchronously on every request, but requires idempotency, event integrity, reconciliation, lag monitoring, and a revocation SLA.

Do not treat a signed **`groups`** claim from an IdP as an automatic grant unless the organization's **authority delegation contract** authorizes the IdP to assert that group, and mapping still enforces a tenant/role allowlist.

## 6. Group Is Neither GrantedAuthority Nor OAuth2 SCOPE

Example server-side policy:

| Tenant | Internal group | GrantedAuthority |
| --- | --- | --- |
| corp | FINANCE_READER | APP_REPORT_READ |
| corp | CASE_AGENT | APP_CASE_WRITE |
| corp | SUPPORT_VIEWER | APP_TICKET_READ |
| partner | FINANCE_READER | APP_PARTNER_REPORT_READ |

**`GrantedAuthority`** in Spring Security is the authority string carried by `Authentication`; **`@PreAuthorize("hasAuthority('APP_REPORT_READ')")`** checks that exact string. **`hasRole("ADMIN")`** checks **`ROLE_ADMIN`** by default. **`SCOPE_read`** typically represents an OAuth2 access token scope and is not inherently equivalent to a business permission to read reports.

Dangerous pattern:

~~~java
// DO NOT use: user-controlled/unapproved external group
new SimpleGrantedAuthority("ROLE_" + externalGroup);
~~~

The right pattern is to **take only local permissions on the allowlist** after checking issuer/sub/account/membership:

~~~java
// Illustrative snippet; roleCode comes from an approved internal policy.
if (APPROVED_PERMISSIONS.contains(roleCode)) {
    new SimpleGrantedAuthority(roleCode);
}
~~~

In a multi-tenant application, there is no global report permission just because a user holds permission in tenant Corp. You must check membership for **the requested tenant**, the operation, and the resource tenant. **A URL/header/body `tenantId` is only a selector**, never a grant of permission.

## 7. Choosing When to Load Groups: Login, Request, or Provisioning

| Timing | Benefits | Limitations |
| --- | --- | --- |
| **Right after federated login** | Authorities are ready as soon as `Authentication` is built. | Slower login; session may go stale after revocation. |
| **At request/service authorization** | Reflects changes near real time. | DB/LDAP overhead; needs caching/timeouts. |
| **SCIM/IGA background sync** | Fast login, governed data. | Asynchronous sync may lag. |
| **Preload at login + recheck for sensitive operations** | Balances UX and freshness. | Needs permission version/session revocation policy. |

For payroll, administration, exports, or cross-tenant data, **recheck local account/role/tenant** at resource access, or use permission versions with session/cache invalidation. **Never assume authorities loaded at login stay up to date when directory groups change.**

## 8. Pure Java 17: Simulating Federated Auth and Group Loading

**FederatedDirectoryDemo.java** runs on JDK 17 **without OIDC/SAML2/LDAP/KDC**. The `VerifiedIdentity` object below represents a **model already verified by the framework**, and must never be constructed from browser-supplied JSON/headers in a real system.

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

public class FederatedDirectoryDemo {
    static final String CORP =
            "https://idp.example.org/realms/corp";
    static final String OTHER =
            "https://idp.other.example.org/realms/other";

    record VerifiedIdentity(String issuer, String sub,
                            boolean verified) {}
    record Account(long id, boolean enabled) {}
    record Membership(long id, String tenant,
                      boolean active, List<String> groups) {}
    record IdentityKey(String issuer, String sub) {}

    static final Map<IdentityKey, Account> LINKS = Map.of(
        new IdentityKey(CORP, "opaque-123"), new Account(41, true),
        new IdentityKey(CORP, "disabled-9"), new Account(99, false),
        new IdentityKey(CORP, "revoked-2"), new Account(42, true),
        new IdentityKey(CORP, "unknown-group"), new Account(43, true),
        new IdentityKey(CORP, "no-groups"), new Account(44, true)
    );
    static final List<Membership> MEMBERS = List.of(
        new Membership(41, "corp", true,
            List.of("FINANCE_READER", "CASE_AGENT")),
        new Membership(42, "corp", false, List.of("FINANCE_READER")),
        new Membership(43, "corp", true, List.of("UNKNOWN_GROUP")),
        new Membership(44, "corp", true, List.of())
    );
    static final Map<String, String> APPROVED = Map.of(
        "FINANCE_READER", "APP_REPORT_READ",
        "CASE_AGENT", "APP_CASE_WRITE"
    );

    static String decide(VerifiedIdentity id, String tenant) {
        if (id == null || !id.verified()) {
            return "DENY UNVERIFIED_IDENTITY";
        }
        Account account = LINKS.get(new IdentityKey(id.issuer(), id.sub()));
        if (account == null) {
            return "DENY NO_LINK";
        }
        if (!account.enabled()) {
            return "DENY ACCOUNT_DISABLED";
        }

        Membership membership = MEMBERS.stream()
            .filter(m -> m.id() == account.id())
            .filter(m -> m.tenant().equals(tenant))
            .findFirst().orElse(null);
        if (membership == null) {
            return "DENY NO_MEMBERSHIP";
        }
        if (!membership.active()) {
            return "DENY INACTIVE_MEMBERSHIP";
        }

        TreeSet<String> permissions = new TreeSet<>();
        for (String group : membership.groups()) {
            String code = APPROVED.get(group);
            if (code == null) {
                return "DENY UNMAPPED_GROUP";
            }
            permissions.add(code);
        }
        return "ALLOW account=" + account.id()
             + " permissions=" + permissions;
    }

    static void show(String label, VerifiedIdentity id, String tenant) {
        System.out.println(label + ": " + decide(id, tenant));
    }

    public static void main(String[] args) {
        show("valid", new VerifiedIdentity(
            CORP, "opaque-123", true), "corp");
        show("wrong tenant", new VerifiedIdentity(
            CORP, "opaque-123", true), "partner");
        show("same sub other issuer", new VerifiedIdentity(
            OTHER, "opaque-123", true), "corp");
        show("unverified", new VerifiedIdentity(
            CORP, "opaque-123", false), "corp");
        show("disabled", new VerifiedIdentity(
            CORP, "disabled-9", true), "corp");
        show("revoked", new VerifiedIdentity(
            CORP, "revoked-2", true), "corp");
        show("unmapped", new VerifiedIdentity(
            CORP, "unknown-group", true), "corp");
        show("empty groups", new VerifiedIdentity(
            CORP, "no-groups", true), "corp");
        show("missing", null, "corp");
    }
}
~~~

Compile and run:

~~~bash
javac FederatedDirectoryDemo.java
java FederatedDirectoryDemo
~~~

**Exact stdout:**

~~~text
valid: ALLOW account=41 permissions=[APP_CASE_WRITE, APP_REPORT_READ]
wrong tenant: DENY NO_MEMBERSHIP
same sub other issuer: DENY NO_LINK
unverified: DENY UNVERIFIED_IDENTITY
disabled: DENY ACCOUNT_DISABLED
revoked: DENY INACTIVE_MEMBERSHIP
unmapped: DENY UNMAPPED_GROUP
empty groups: ALLOW account=44 permissions=[]
missing: DENY UNVERIFIED_IDENTITY
~~~

- **valid:** both local groups are mapped and `TreeSet` sorts **`APP_CASE_WRITE`** before **`APP_REPORT_READ`**.
- **wrong tenant:** user has no Partner membership even though the account belongs to Corp.
- **same sub other issuer:** matching `sub` from a different IdP is not auto-linked.
- **unverified:** never use an identity not verified by a protocol provider.
- **disabled/revoked:** identity link still exists, but the local account/membership is invalid.
- **unmapped:** internal group has no permission contract; fail-closed.
- **empty groups:** may enter the application, but receives no business permissions; an API requiring `APP_REPORT_READ` must return 403.

**This program does not verify OIDC ID Token/SAML signatures, does not connect to LDAP/SQL, and does not create HTTP sessions.** It is solely for studying the **local authorization after trusted authentication** step.

## 9. Spring Boot 3.3.5 Example: OIDC UserService Loading JDBC Groups

The Spring MVC Servlet sample below demonstrates **OIDC federation + local JDBC directory**. H2 is for learning only. Real login testing requires a valid OIDC Provider sandbox and client registration, with a real verified issuer/sub approved and linked to the local account.

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>federated-directory-example</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build><plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins></build>
</project>
~~~

**Do not use an OIDC library to verify `SAMLResponse` yourself, or trust a `groups` claim from a bearer token with the wrong issuer.** Spring `oauth2Login()` runs the OIDC authorization code flow; business mapping runs after the framework verifies the ID Token.

### 9.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

spring:
  datasource:
    url: "jdbc:h2:mem:directorydb;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
  security:
    oauth2:
      client:
        registration:
          intranet:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: "${OIDC_ISSUER_URI}"
~~~

The issuer environment variable must point to a **real OIDC Provider** exposing discovery metadata. The client must register its redirect URI, e.g. **http://localhost:8080/login/oauth2/code/intranet** in a controlled sandbox or a real public HTTPS callback. Never place secrets in source code or logs.

### 9.3. schema.sql

**src/main/resources/schema.sql**

~~~sql
CREATE TABLE app_accounts (
    account_id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE identity_links (
    protocol VARCHAR(16) NOT NULL,
    issuer VARCHAR(255) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    account_id BIGINT NOT NULL REFERENCES app_accounts(account_id),
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (protocol, issuer, subject_id)
);

CREATE TABLE tenant_memberships (
    account_id BIGINT NOT NULL REFERENCES app_accounts(account_id),
    tenant_id VARCHAR(32) NOT NULL,
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (account_id, tenant_id)
);

CREATE TABLE directory_groups (
    tenant_id VARCHAR(32) NOT NULL,
    group_code VARCHAR(64) NOT NULL,
    authority_code VARCHAR(64) NOT NULL,
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (tenant_id, group_code)
);

CREATE TABLE assigned_groups (
    account_id BIGINT NOT NULL,
    tenant_id VARCHAR(32) NOT NULL,
    group_code VARCHAR(64) NOT NULL,
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (account_id, tenant_id, group_code),
    FOREIGN KEY (account_id, tenant_id)
        REFERENCES tenant_memberships(account_id, tenant_id),
    FOREIGN KEY (tenant_id, group_code)
        REFERENCES directory_groups(tenant_id, group_code)
);
~~~

PK/FK constraints prevent mixing identity links and assigning groups to a tenant without membership; a production database also needs indexes, migrations, transactions/revocation, and auditing.

### 9.4. data.sql

**src/main/resources/data.sql**

~~~sql
INSERT INTO app_accounts VALUES (41, 'Alice', TRUE);

-- PLACEHOLDER: issuer/sub must be replaced with a verified IdP identity.
INSERT INTO identity_links
(protocol, issuer, subject_id, account_id, enabled)
VALUES
('OIDC', 'https://idp.example.org/realms/corp',
 'opaque-123', 41, TRUE);

INSERT INTO tenant_memberships VALUES (41, 'corp', TRUE);

INSERT INTO directory_groups VALUES
('corp', 'FINANCE_READER', 'APP_REPORT_READ', TRUE),
('corp', 'CASE_AGENT', 'APP_CASE_WRITE', TRUE);

INSERT INTO assigned_groups VALUES
(41, 'corp', 'FINANCE_READER', TRUE),
(41, 'corp', 'CASE_AGENT', TRUE);
~~~

In production, never auto-run demo SQL. Provisioning/identity linking must be performed by an authorized IAM/DB workflow; never auto-insert accounts from unverified emails.

### 9.5. Main

**src/main/java/com/example/directory/FederatedDirectoryApplication.java**

~~~java
package com.example.directory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederatedDirectoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederatedDirectoryApplication.class, args);
    }
}
~~~

### 9.6. LocalAuthorityService.java

**src/main/java/com/example/directory/LocalAuthorityService.java**

~~~java
package com.example.directory;

import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LocalAuthorityService {
    // Demo is for tenant corp only. Multi-tenant requires scoping per request.
    private static final String TENANT = "corp";
    private static final Set<String> ALLOWED = Set.of(
        "APP_REPORT_READ", "APP_CASE_WRITE"
    );
    private final JdbcTemplate jdbc;

    public LocalAuthorityService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record LocalProfile(long accountId, String displayName,
                               Set<String> permissions) {}

    @Transactional(readOnly = true)
    public LocalProfile load(String issuer, String subject) {
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw denied("missing_verified_identity");
        }

        List<LocalProfile> accounts = jdbc.query(
            """
            SELECT a.account_id, a.display_name
              FROM app_accounts a
              JOIN identity_links l ON l.account_id = a.account_id
              JOIN tenant_memberships m ON m.account_id = a.account_id
             WHERE l.protocol = 'OIDC'
               AND l.issuer = ? AND l.subject_id = ?
               AND a.enabled = TRUE AND l.enabled = TRUE
               AND m.tenant_id = ? AND m.enabled = TRUE
            """,
            (rs, index) -> new LocalProfile(
                rs.getLong("account_id"),
                rs.getString("display_name"),
                Set.of()),
            issuer, subject, TENANT
        );
        if (accounts.size() != 1) {
            throw denied("no_active_local_identity");
        }

        LocalProfile account = accounts.get(0);
        List<String> codes = jdbc.queryForList(
            """
            SELECT DISTINCT g.authority_code
              FROM assigned_groups ag
              JOIN directory_groups g
                ON ag.tenant_id = g.tenant_id
               AND ag.group_code = g.group_code
             WHERE ag.account_id = ?
               AND ag.tenant_id = ?
               AND ag.enabled = TRUE
               AND g.enabled = TRUE
            """,
            String.class, account.accountId(), TENANT
        );

        TreeSet<String> verified = new TreeSet<>();
        for (String code : codes) {
            if (!ALLOWED.contains(code)) {
                throw denied("unapproved_permission_code");
            }
            verified.add(code);
        }
        return new LocalProfile(account.accountId(),
            account.displayName(), Set.copyOf(verified));
    }

    private OAuth2AuthenticationException denied(String code) {
        return new OAuth2AuthenticationException(new OAuth2Error(code));
    }
}
~~~

Notes:

1. **`JdbcTemplate`** uses placeholders/bound parameters for `issuer` and `subject`; never concatenate SQL strings with user input.
2. Local account, identity link, and membership must all be active; never take groups from email/remote claims.
3. **`tenant=corp` is fixed by server configuration** in this example; in a multi-tenant system, check the requested tenant and membership on every operation.
4. Group authorities are fetched from local tables and checked against an allowlist; if an unexpected code appears, such as **`ROLE_SUPER_ADMIN`**, **`denied()`** fails closed.
5. The group set may be empty: login remains valid, but the user cannot perform operations requiring **`APP_REPORT_READ`**.
6. On a DB outage, never fall back to admin; define an explicit failure/limited-mode policy.
7. Once a session holds authorities and groups change, permissions in `Authentication` may become stale; use session revocation, permission versioning, or live checks.

### 9.7. SecurityConfig.java

**src/main/java/com/example/directory/SecurityConfig.java**

~~~java
package com.example.directory;

import java.util.LinkedHashSet;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, LocalAuthorityService local)
            throws Exception {

        OidcUserService delegate = new OidcUserService();

        OAuth2UserService<OidcUserRequest, OidcUser> enriched =
                request -> {
            // At this point Spring OAuth2/OIDC login has already verified the ID Token.
            OidcUser principal = delegate.loadUser(request);
            String issuer =
                    principal.getIdToken().getClaimAsString("iss");
            String subject = principal.getSubject();

            LocalAuthorityService.LocalProfile profile =
                    local.load(issuer, subject);

            LinkedHashSet<GrantedAuthority> authorities =
                    new LinkedHashSet<>();

            // Preserve authenticated OIDC marker; do not take remote
            // group claims to auto-grant ROLE_ADMIN.
            for (GrantedAuthority authority :
                    principal.getAuthorities()) {
                if (authority instanceof OidcUserAuthority) {
                    authorities.add(authority);
                }
            }

            for (String code : profile.permissions()) {
                authorities.add(new SimpleGrantedAuthority(code));
            }

            return new DefaultOidcUser(authorities,
                principal.getIdToken(), principal.getUserInfo(), "sub");
        };

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(enriched)));

        return http.build();
    }
}
~~~

**`OidcUserRequest`** is a type in **`org.springframework.security.oauth2.client.oidc.userinfo`**; **`OidcUserAuthority`** and **`DefaultOidcUser`** live in **`org.springframework.security.oauth2.core.oidc.user`**. **`OAuth2Error`** and **`OAuth2AuthenticationException`** belong to **`org.springframework.security.oauth2.core`**, not the `org.springframework.oauth2` namespace.

**Security points:**

- OIDC code exchange and ID Token signature/issuer/audience/nonce are handled by Spring before calling `OidcUserService`.
- **`delegate.loadUser`** preserves framework behavior for UserInfo/ID Token; `enriched` only performs the local group lookup.
- Never use **`email`** or **`preferred_username`** as the local account key.
- Keep only the verified user's **`OidcUserAuthority`**, avoiding confusing **`SCOPE_`** with business authorities. If the app needs scopes to call a Resource API, design a policy-governed way to keep them separate.
- **`DefaultOidcUser`** retains the ID Token/UserInfo and adds permissions from the local DB, rather than fabricating an authenticated token from browser input.
- **`@EnableMethodSecurity`** is mandatory for `@PreAuthorize` to work. The Spring Boot security starter does not enable method security automatically.
- Local authorities loaded at login can go stale; revalidation/session revocation is needed for sensitive data.

### 9.8. ReportsController.java

**src/main/java/com/example/directory/ReportsController.java**

~~~java
package com.example.directory;

import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {
    private final LocalAuthorityService directory;

    public ReportsController(LocalAuthorityService directory) {
        this.directory = directory;
    }

    @GetMapping("/")
    public String home() {
        return "Federated directory ready";
    }

    @GetMapping("/corp/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser user) {
        var profile = directory.load(
            user.getIdToken().getClaimAsString("iss"),
            user.getSubject());
        return Map.of(
            "accountId", profile.accountId(),
            "displayName", profile.displayName(),
            "permissions", profile.permissions());
    }

    @PreAuthorize("hasAuthority('APP_REPORT_READ')")
    @GetMapping("/corp/reports")
    public String reports() {
        return "Corp report allowed";
    }
}
~~~

Because **`/corp/me`** calls the local directory again, it can reflect current account/membership state, whereas **`/corp/reports`** uses the authorities captured in `Authentication` at login time. If near-instant revocation is required for reports, you must **recheck permission version/active membership at the service layer**, not rely solely on `@PreAuthorize` over a long-lived session. For real data, the repository must still filter by **`tenant_id=corp`** and resource owner per policy.

### 9.9. Running and Expected Behavior

~~~bash
mvn spring-boot:run
~~~

- **GET /** returns **Federated directory ready** once the app and OIDC client configuration initialize.
- Anonymous **GET /corp/me** redirects to OIDC login.
- The OIDC issuer and subject must **match `identity_links` exactly**; since the sample issuer/sub are dummy data, an admin must link to a real sandbox IdP.
- With an active link, active local account, active `corp` membership, and valid groups, **GET /corp/me** returns JSON with **accountId=41, displayName=Alice** and both `APP_` permissions.
- **GET /corp/reports** is permitted when `Authentication` holds **`APP_REPORT_READ`**, returning **Corp report allowed**.
- Mismatched issuer/sub, disabled account, revoked membership, or an unapproved authority code in the DB → login is rejected per policy, never auto-granted.
- A user with a valid account/membership but without the `FINANCE_READER` group → can log in, yet **GET /corp/reports returns 403**.

**Without a real OIDC Provider, verified issuer/sub, redirect URI, and valid secrets, you cannot run an end-to-end login test.** Compiling the standalone Java 17 demo does not prove real token verification.

## 10. SAML2: Loading Local Groups After a Validated Response

In **Spring Security 6.3.x**, **`OpenSaml4AuthenticationProvider`** can configure **`setResponseAuthenticationConverter`** to enrich the result already processed by the SAML2 provider. Do not confuse it with **`OpenSaml5AuthenticationProvider`** in other versions.

~~~text
Saml2WebSsoAuthenticationFilter
 -> Saml2AuthenticationTokenConverter (RelyingPartyRegistration)
 -> OpenSaml4AuthenticationProvider (SAML signature/conditions)
 -> validated Saml2Authentication and Saml2AuthenticatedPrincipal
 -> local issuer/stable subject -> account/tenant/groups
 -> mapped authorities -> service authorization
~~~

**API illustration snippet—NOT standalone runnable due to missing provider bean/imports and business helper:**

~~~java
OpenSaml4AuthenticationProvider provider =
        new OpenSaml4AuthenticationProvider();

var delegate = OpenSaml4AuthenticationProvider
        .createDefaultResponseAuthenticationConverter();

provider.setResponseAuthenticationConverter(responseToken -> {
    Saml2Authentication saml = delegate.convert(responseToken);
    Saml2AuthenticatedPrincipal p =
            (Saml2AuthenticatedPrincipal) saml.getPrincipal();

    // resolve trusted RelyingPartyRegistration from p,
    // derive the configured IdP entityID and stable subject
    // released by the IdP and approved by the application.
    Collection<GrantedAuthority> mapped =
            loadLocalAuthoritiesAfterValidatedSaml(p);

    return new Saml2Authentication(p,
            saml.getSaml2Response(), mapped);
});
~~~

**`loadLocalAuthoritiesAfterValidatedSaml`** is a hypothetical business helper that must be defined in the application. This extension point must never be used to bypass signature/time/audience/recipient validation. **`NameID`** may be transient/email and is not inherently stable; use a persistent NameID/immutable attribute per the trust contract and namespace by IdP `entityID`.

When one IdP serves multiple tenants, a verified IdP issuer **does not replace membership**. A SAML-authenticated user must still be checked against local account, group/tenant, and resource policies.

## 11. CAS and Kerberos: Different Protocols, Same Local Directory Layer

**Native CAS flow:**

~~~text
CAS login -> CAS service ticket
 -> CasAuthenticationFilter -> CasAuthenticationProvider
 -> TicketValidator verifies ST with CAS server
 -> local UserDetailsService / Directory
 -> groups/attributes/authorities + business authorization
~~~

**Kerberos/SPNEGO flow:**

~~~text
Browser Authorization: Negotiate
 -> SpnegoAuthenticationProcessingFilter
 -> KerberosServiceAuthenticationProvider
 -> SunJaasKerberosTicketValidator / GSS keytab
 -> verified principal user@REALM
 -> local UserDetailsService / Directory
 -> groups/attributes/authorities + business authorization
~~~

Never trust a username, email, or `X-User` header sent by the request itself; only use the principal **after** CAS ticket or Kerberos GSS verification. With multiple CAS servers/realms, namespace local identities by trust domain. Querying groups via LDAP does not mean the application must re-run password-based LDAP authentication.

## 12. LDAP/AD Lookup: Filter Injection, Nested Membership, and Scale

A directory may use:

~~~text
AD service user identity: objectGUID=...
LDAP entry DN: uid=alice,ou=people,dc=corp,dc=example,dc=org
Group DN: cn=FinanceReader,ou=groups,dc=corp,dc=example,dc=org
Group references: member / memberOf depending on schema
~~~

Principles:

1. **Look up from a verified local account/immutable directory ID**, not from a browser-chosen email/username.
2. Use Spring LDAP **`LdapTemplate`** or an LDAP client with filter escaping/parameter binding; never manually concatenate `(uid= + input + )`.
3. **LDAPS/StartTLS** with truststore/hostname validation; never disable TLS verification.
4. Directory service accounts may only read required OUs/attributes, never hold Domain Admin privileges.
5. Enforce paging, size limits, query timeouts, connect/read deadlines, and circuit breakers to prevent hung logins.
6. Nested groups require checking direct vs. transitive semantics, limiting depth/cycles, and avoiding unbounded queries.
7. Group DN/`objectGUID` is generally more trustworthy than matching common name alone; identical CNs across different domains do not carry the same authority.
8. Referrals/forest trusts must be allowlisted; never auto-follow referrals to an attacker-controlled directory.
9. Never stuff the entire group list into cookies/JWTs/sessions unnecessarily; map to minimal permissions.
10. Group lists and HR attributes can be sensitive data requiring access control, retention rules, and auditing.

**A failing directory source is not a signal to grant default permissions.** For financial reports or admin functions, fail closed; if the business needs a limited offline mode, policy must explicitly define permitted data/actions, TTL, and risk.

## 13. Sessions/Caching and Permission Revocation

A user logs in at 09:00, and the OIDC user service loads groups and attaches **`APP_REPORT_READ`** to `Authentication`. At 09:05, an admin revokes `FINANCE_READER`. If the application only checks session authorities, the user can keep reading reports until the session expires.

To control the **revocation window**, consider:

- **Permission version** in the directory/IGA, checked on every request or sensitive operation.
- **`SessionRegistry` / Spring Session** to invalidate sessions across all nodes after account disable/group revocation.
- **Short-lived caches** with risk-appropriate TTLs; never cache roles indefinitely.
- **Event-driven invalidation** from SCIM/IGA/HR/AD connectors with auditing and retries.
- **Live permission/membership checks** in services/`AuthorizationManager` for payroll/admin/cross-tenant actions.
- **Revalidating the resource tenant**, not just login-time authorities.
- **Cache keys** namespaced by account ID, tenant, and policy version—never by email.
- **Explicit outage policy**: never turn an unavailable directory into admin access.

Example cache key:

~~~text
authz:v5:account:41:tenant:corp:policy:27
~~~

**Never promise immediate revocation merely because a JWT or SAML Assertion is short-lived.** Local sessions/authorization caches have their own lifecycles and can outlive the login token.

## 14. Multi-Tenancy and Data-Layer Boundaries

**Anti-pattern:**

~~~sql
SELECT document_id, body FROM documents
WHERE document_id = :requestedDocument;
~~~

If a document ID from another tenant is guessed or known, an authenticated user can view the wrong tenant's data.

**Correct direction:**

~~~sql
SELECT document_id, body FROM documents
WHERE tenant_id = :authorizedTenant
  AND document_id = :requestedDocument;
~~~

**`authorizedTenant`** must be a tenant verified server-side from an active membership—never accepted straight from path/query/header without validation. `INSERT`/`UPDATE`/`DELETE` statements must likewise include a tenant predicate or assign tenant from the verified context. Database RLS can provide defense-in-depth, but does not replace membership logic and does not cover caches/search/blob storage/queues.

A **`FINANCE_READER`** group in tenant Partner does not grant **`FINANCE_READER`** permissions in Corp. If users are allowed to switch tenants, check membership and per-tenant permissions on every request; the Spring sample in section 9 uses a **fixed tenant `corp`** to avoid implying that a global `APP_REPORT_READ` is safe across multi-tenant systems.

## 15. Common Errors Table

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| OIDC login succeeds but local directory returns no link | `issuer`/`sub` not properly provisioned/linked. | Check verified identity and onboarding; no email fallback. |
| After SAML login the account changes every session | Transient NameID used as stable key. | Choose persistent NameID/immutable attribute per IdP contract. |
| Matching emails caused accounts to merge | Identity link lacked issuer namespace. | Use PK(`protocol`,`issuer`,`subject`) and verified linking flow. |
| IdP group Admin becomes `ROLE_ADMIN` | Automatic mapping without allowlist. | Server-controlled policy per tenant/role. |
| User from tenant A reads tenant B data | Checked only `authenticated()` or global role. | Local membership + data-layer tenant predicate. |
| Added LDAP group but permissions didn't change | Session/authz cache not refreshed. | Permission version/revocation/reauthorization. |
| LDAP query slow/times out | Nested groups, referrals, overly broad search base. | Timeouts, paging, bounded depth, indexes. |
| LDAP group lookup leaks permissions | Filter injection from user input. | Escaping/parameterized queries, server-side account lookup. |
| Disabled user still has access | Old session/permissions cache still active. | Recheck status and revoke sessions. |
| OIDC `SCOPE_read` can read reports | OAuth2 scope confused with business role. | `APP_REPORT_READ` only from internal permission policy. |
| DB contains unapproved authority | Mapping drift or modified group policy. | Reject unknown codes, audit/require approval. |
| Protected GET returns 403 after login | Insufficient local roles. | Distinguish federated auth success from business authz. |
| Directory down, user becomes admin | Fail-open fallback. | Fail closed or approved limited mode. |
| Spring `@PreAuthorize` does not enforce | `@EnableMethodSecurity` not enabled. | Enable method security and add regression tests. |
| All orgs share identically named groups | Missing tenant namespace. | Scope groups and permissions by tenant ID. |

## 16. Integration Testing Matrix

Test **federated validation**, **identity linking**, **directory membership**, **authority mapping**, and **resource authorization** separately.

| # | Scenario | Expected |
| --- | --- | --- |
| 1 | Valid OIDC issuer/sub, active account + membership | Loads local groups/permissions. |
| 2 | Invalid ID Token signature/issuer/audience/nonce | Spring OIDC rejects before local lookup. |
| 3 | Same `sub` but different IdP issuer | `NO_LINK`; do not merge accounts. |
| 4 | Two IdPs emit the same email | Do not auto-link. |
| 5 | Identity link disabled | Deny login. |
| 6 | Local account disabled | Deny. |
| 7 | Tenant membership revoked | Deny tenant. |
| 8 | Corp user calls Partner tenant | Deny without Partner membership. |
| 9 | `FINANCE_READER` Corp group | `APP_REPORT_READ` Corp per policy. |
| 10 | `FINANCE_READER` Partner group | Does not grant Corp permission. |
| 11 | Remote IdP claims unauthorized `ROLE_ADMIN` | Do not grant `ROLE_ADMIN`. |
| 12 | Unknown local group | Deny or ignore per contract; never auto-elevate. |
| 13 | Empty group list | Login may pass, privileged endpoint returns 403. |
| 14 | Group revoked mid-session | Revalidation/session version blocks within SLA. |
| 15 | Directory DB outage | No default-admin. |
| 16 | LDAP filter contains special characters | No LDAP injection. |
| 17 | AD nested group has cycle/excessive depth | Bounded, no DoS. |
| 18 | LDAP referral points outside trust | Never auto-follow and grant groups. |
| 19 | IdP changes issuer/sub on migration | Verified account relinking. |
| 20 | Transient SAML NameID changes per session | Not used as permanent identity key. |
| 21 | Different CAS servers with same username | Do not merge identities. |
| 22 | Different Kerberos realms with same username | Do not merge identities. |
| 23 | Multi-valued local group | Deduplicate/normalize per policy, don't just take first. |
| 24 | User knows a Partner document ID | Data-layer tenant filter blocks. |
| 25 | Unapproved JIT provisioning | Does not create admin membership. |
| 26 | HR department changes | ABAC updates per revalidation policy. |
| 27 | `email_verified=true` but different subject | Do not link based on email. |
| 28 | Session exists on another node after revocation | Shared session invalidation works. |
| 29 | `authority_code` in DB not on allowlist | Fail-closed. |
| 30 | UserInfo has oversized/wrong-type attributes | Schema/size validation, no bypass. |
| 31 | User lacks `APP_REPORT_READ` | `@PreAuthorize` returns 403. |
| 32 | `@EnableMethodSecurity` removed | Regression test detects missing enforcement. |
| 33 | OAuth2 `SCOPE_read` without `APP_REPORT_READ` | Report returns 403. |
| 34 | IdP session remains after local logout | Re-login still checks fresh account/permissions. |
| 35 | Audit account linking and role changes | Captures policy/actor/tenant, never exposes tokens. |

**Do not only test an ID Token with a bad signature**: a signature error blocks before group mapping, proving nothing about local directory ACLs. Use a valid sandbox SSO login, then test wrong tenant, wrong group, disabled account, and stale session.

## 17. Production Checklist

**Identity and accounts**

- [ ] External identity is verified by the framework before group lookup.
- [ ] Identity key includes protocol+issuer/realm+stable subject; no email auto-matching.
- [ ] Account linking/JIT provisioning has approval and auditing.
- [ ] Active status and tenant membership are checked server-side.
- [ ] SAML persistent NameID/immutable attribute and OIDC `sub` lifecycle have a contract.

**Directories and roles**

- [ ] Authoritative directory source is clear for each attribute/group.
- [ ] LDAP/AD uses TLS, read-only credentials, escaping, and paging/timeouts/depth limits.
- [ ] SCIM/IGA synchronization has SLAs, retries, and reconciliation.
- [ ] Group→permission mapping uses an allowlist, tenant scoping, and least privilege.
- [ ] Never map all remote groups to Spring `ROLE_ADMIN`.
- [ ] Never confuse OAuth2 scopes with business permissions.

**Spring and authorization**

- [ ] OIDC `oidcUserService` delegates before loading local groups.
- [ ] SAML2 response converter matches version without bypassing provider validation.
- [ ] CAS/Kerberos only reads local accounts after ticket/GSS validation.
- [ ] `@EnableMethodSecurity` and `@PreAuthorize` are covered by tests.
- [ ] Sensitive permissions are revalidated within SLA; session revocation/cache invalidation works.
- [ ] Data-layer tenant predicates, cross-tenant tests, and auditing are in place.
- [ ] Directory outage fails closed or follows an explicitly approved limited policy.

## 18. Review Questions

**1. Does successful IdP authentication give the user all app permissions?**  
No. The IdP confirms identity; local account, groups, tenant membership, and resource policy decide permissions.

**2. Why use OIDC `issuer+sub` instead of email?**  
Because emails can change, be recycled, or collide across IdPs; `sub` is scoped to the issuer.

**3. Is a SAML2 NameID always stable?**  
No. Transient NameIDs are unsuitable for long-term linking; use a persistent NameID or immutable attribute per contract.

**4. Does an LDAP group `Admin` automatically become `ROLE_ADMIN`?**  
No. You need an explicit mapping policy, least privilege, and tenant scoping.

**5. When does the OIDC user service load local groups?**  
After Spring OIDC validation produces a verified principal; never load from self-asserted data before authentication.

**6. A user had a role at login and it was later revoked—why does the session still have it?**  
Authorities are stored in `Authentication`. You need permission versioning, session revocation, or live authorization.

**7. Does an OIDC access token's `SCOPE_read` grant permission to read `APP_REPORT_READ` reports?**  
Not without an explicit mapping policy; they are two different kinds of permissions.

**8. Does an LDAP group lookup after SSO require the user's password to bind again?**  
No. The app uses a read-only directory service client; authentication already happened with the IdP.

**9. If `APP_REPORT_READ` is already checked, why is `tenant_id` still needed in the query?**  
An authority does not verify resource ownership or tenant by itself. Queries must scope to the right tenant's resources.

**10. If the directory fails, should `ROLE_USER` or `ADMIN` be assigned by default?**  
No. Fail closed or use an approved limited mode; never auto-elevate during a dependency outage.

## 19. Official References

1. [Spring Security 6.x — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): mapping user authorities, delegation-based OIDC user service.
2. [Spring Security 6.3 — OidcUserService Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): OIDC user loading customization.
3. [Spring Security 6.3 — DefaultOidcUser Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html): ID Token/UserInfo and authorities.
4. [Spring Security 6.3 — OpenSaml4AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): SAML response converter.
5. [Spring Security — SAML2 Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): validated Response/principal mapping (note version 7.x).
6. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
7. [Spring LDAP — Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, search, and directory integration.
8. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer, subject, UserInfo, and ID Token verification.
9. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID, issuer, and `AttributeStatement`.
10. [RFC 7643 — SCIM Schema](https://www.rfc-editor.org/rfc/rfc7643), [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): user/group provisioning.
11. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, per-request authorization.
12. [OWASP — Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): tenant scoping and data isolation.

**Conclusion:** After federated authentication, an application must **map the verified identity (`issuer` + stable `subject`) to a local account**, load groups/attributes from an **authoritative source**, apply a **local allowlist** to convert them into business permissions, and then enforce **tenant/resource** checks during API execution. Never auto-link by email, never auto-grant roles from IdP groups, and never keep revoked permissions alive indefinitely in a session.
