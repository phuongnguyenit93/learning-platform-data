# Integrating Two IdPs with Stable Identifiers and Tenant Data Isolation

> **Topic:** Spring Security – federation. **Knowledge track:** Comprehensive Practice. This lab guides integrating two OpenID Connect Identity Providers (IdP/OP) into a Spring Boot 3.x / Spring Security 6.x Servlet app using Java 17+, mapping identities via **`(issuer, subject)`**, and protecting multi-tenant data with **service-layer authorization** and **tenant-scoped SQL queries**. It includes sample IdP configuration, a Maven project, Java code, SQL schema, MockMvc tests, a standalone Java 17 program, a runbook, a negative test matrix, and extensions to SAML2/Resource Server.

## 1. Objectives and Model

The `portal` application serves two independent tenants:

- **North:** OIDC issuer `http://localhost:8180/realms/north`; Spring `registrationId=north`; client `portal-north`.
- **South:** OIDC issuer `http://localhost:8180/realms/south`; Spring `registrationId=south`; client `portal-south`.
- North and South have separate accounts/grants/notes. A North user has **no default permission** to read South documents.
- Two users across the two IdPs **may share the same email, username, or `sub` string**: they are still two distinct identities.
- `tenantId` in the URL is an **untrusted resource selector**; the app must verify it server-side from the authenticated principal and approved tenant membership.
- The lab picks **one IdP ↔ one tenant** to keep test cases clear. Production may let one IdP serve multiple tenants, or one tenant trust multiple IdPs, provided there is an issuer/tenant allowlist and independent business grants.

**PASS criteria:** An authenticated North user granted `NOTE_READ` on North reads `GET /api/tenants/north/notes/1` with 200; that same user calling `/api/tenants/south/notes/1` receives 403; South works symmetrically in reverse; unknown issuer/sub/tenant is denied; a disabled account is denied even if an app session remains. No output may leak another tenant's document content.

### 1.1. IdP Does Not Equal Tenant or Account

| Field | Origin | Example | Meaning |
| --- | --- | --- | --- |
| `iss` | Verified OIDC ID Token | `.../realms/north` | OP namespace / trust boundary |
| `sub` | Verified OP | `same-sub` | Unique user ID **within the issuer** |
| `registrationId` | Spring `ClientRegistration` | `north` | Internal config key; does not automatically equal `iss` |
| `client_id` | OP/client registry | `portal-north` | OAuth client ID, not an account ID |
| `account_id` | Application DB | `acct-n` | Stable local account identifier |
| `tenant_id` | Business data model | `north` | Scope of permissions and data |
| `permission` | Approved business policy | `NOTE_READ` | Explicit permission, not derived from email |
| `note_id` | Tenant data | `1` | Meaningful only when combined with tenant |
| `JSESSIONID`/`SESSION` | RP session | Opaque cookie | Local session, not the IdP SSO session |

OIDC Core `5.7` defines the **`iss + sub` pair** as the identifier an RP can trust for uniqueness/stability; **never** use `email`, `preferred_username`, or display name as the primary key. `sub` can collide across issuers. `email_verified=true` also does not authorize merging accounts across two IdPs. With **pairwise subjects**, the same user at one OP can get a different `sub` when the client/sector identifier changes; account migration requires proof/approval, not automatic linking by email.

### 1.2. Flow Diagram

```text
            Browser (two separate profiles)
                       |
             Spring Security RP
           oauth2Login north / south
                       |
            +----------+----------+
            |                     |
            v                     v
       OP North               OP South
   iss=.../north           iss=.../south
   client portal-north     client portal-south
            |                     |
            +----------+----------+
                       |
       Verified OidcUser ID Token (iss, sub)
                       |
            federated_identity
       PK (issuer, subject) -> account_id
                       |
          app_account.active AND
          tenant_membership.active AND
          permission = NOTE_READ
                       |
         @PreAuthorize tenant policy
                       |
         SELECT ... FROM tenant_note
         WHERE tenant_id=? AND note_id=?
                       |
                only authorized data
```

**Four security invariants:** (1) verified IdP authentication before reading claims; (2) unique `(iss,sub)` → local account; (3) active membership/permission for the **specific tenant**; (4) **tenant-bound SQL** on every data path. None of the four can replace the other three.

## 2. Threat Model: What Must Be Blocked?

1. **Account collision:** Attacker uses IdP South with an email or `sub` matching North; the app keys by email/sub alone and grants North access.
2. **Tenant ID tampering/IDOR:** A North user changes `/tenants/north/notes/1` to `/tenants/south/notes/1`, or guesses note IDs.
3. **Unsigned/untrusted token:** Backend reads Base64 JWT `iss`/`groups` before verifying the signature and grants privileges.
4. **Dynamic JWK SSRF:** Code constructs a `JwtDecoder` from an un-allowlisted `iss` URL, and the attacker points it to an OP they operate.
5. **Group mapping confusion:** North and South both emit `groups=["admin"]`, and the app maps any `admin` to global `ROLE_ADMIN`.
6. **Stale access:** User leaves the organization and the IdP account is disabled, yet an RP session/JWT, local grant, or stale permission cache remains active.
7. **Cache bleed:** Cache uses key `note:1`, potentially serving North data to South.
8. **Unscoped SQL:** Service checks permissions properly, yet the repository runs `SELECT body WHERE note_id=?`, leaking another tenant's data.
9. **Browser/session mix-up:** Two tabs in the same browser profile log into two IdPs and overwrite session state/cookies; if the app drops state/nonce checks to "fix" it, it introduces login CSRF.
10. **Issuer migration/auto-link:** OP changes issuer/client sector, a new `sub` appears, and the app auto-links the old account by email.
11. **SAML mixed federation:** An Assertion from IdP A is accepted under registration B, or a transient NameID is used as a stable key.
12. **API access token confusion:** The app uses an OIDC ID Token as an OAuth access token, or a Resource Server trusts the wrong JWT issuer/audience.

**Rule:** HTTP request headers `X-Tenant`, `X-User`, `?sub=...`, and raw JWT claims are **not authentication evidence**. The tenant path is an authorization input, not a grant. Never select an IdP/public key from an attacker-supplied hostname.

## 3. Setting Up Two Issuers in the Lab Environment

### 3.1. Start One Keycloak Instance with Two Realms

Keycloak can use **two realms** to create **two logical OIDC issuer namespaces** on the same server. These are not two physically independent deployments; testing independent outages/HA requires two separate Keycloak instances.

```bash
docker run --rm --name keycloak-two-idp \
  -p 127.0.0.1:8180:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=change-me-local-only \
  quay.io/keycloak/keycloak:26.8.2 start-dev
```

**Run HTTP/dev credentials on localhost only**—never expose to production. The image tag follows Keycloak docs at the time of lab authoring; you may use an organization-approved version and check release notes. On Windows PowerShell, run the command on one line or use the shell's proper line-continuation syntax.

Open `http://localhost:8180/admin/` and create two realms `north` and `south`; do not use the `master` realm for applications.

In **north**:

- Create OIDC confidential client `portal-north` with Standard Flow / Authorization Code; enable client authentication.
- Exact Valid Redirect URI: `http://localhost:8080/login/oauth2/code/north`.
- Create a test user, set a password, and enable it. Store the client secret in environment variable `NORTH_CLIENT_SECRET`.

In **south**:

- Create client `portal-south`, exact Valid Redirect URI `http://localhost:8080/login/oauth2/code/south`.
- Create a separate test user; you may use the same email as North to test collisions. Store the secret in `SOUTH_CLIENT_SECRET`.

Verify both discovery URLs:

```text
http://localhost:8180/realms/north/.well-known/openid-configuration
http://localhost:8180/realms/south/.well-known/openid-configuration
```

Each JSON `issuer` must match the configured URI exactly, including scheme, host, port, and path. Never guess an issuer from an email domain or arbitrarily strip/add trailing slashes. Use `http://localhost` only in the lab; production requires HTTPS, trusted OP discovery, TLS/PKIX, and client secrets in a secret manager.

### 3.2. Keep Two Separate Browser Profiles

Use **Profile N** to log into North and **Profile S** to log into South. A normal Spring web session holds a single current `Authentication`; logging into a second provider in the same browser profile can overwrite the principal/session, so two tabs are not an independent two-user test. Only after verifying the happy path should you add concurrent-tab/state tests.

## 4. Java 17 / Spring Boot Project

File layout:

```text
federation-two-idp-lab/
  pom.xml
  src/main/resources/
    application.yml
    schema.sql
    data.sql
  src/main/java/com/example/federationlab/
    FederationLabApplication.java
    WebSecurityConfiguration.java
    TenantGuard.java
    TenantNoteService.java
    TenantNoteController.java
  src/test/java/com/example/federationlab/
    TenantIsolationMvcTest.java
```

**Maven `pom.xml`** (Java 17, Spring Boot 3.5.x; version pin is illustrative, not a recommendation for "latest"):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>federation-two-idp-lab</artifactId>
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
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

### 4.1. `application.yml`

```yaml
server:
  port: 8080
  # Only local direct HTTP lab. Use TLS/Secure cookies in prod.
  forward-headers-strategy: none
  servlet:
    session:
      cookie:
        secure: false
        http-only: true
        same-site: lax

spring:
  application:
    name: federation-two-idp-lab
  datasource:
    url: jdbc:h2:mem:federation;DB_CLOSE_DELAY=-1
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
          north:
            provider: north-op
            client-id: portal-north
            client-secret: "${NORTH_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          south:
            provider: south-op
            client-id: portal-south
            client-secret: "${SOUTH_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          north-op:
            issuer-uri: http://localhost:8180/realms/north
          south-op:
            issuer-uri: http://localhost:8180/realms/south
```

- `spring.security.oauth2.client.registration.north`/`south` are internal keys. `provider.<id>.issuer-uri` is the OP's exact issuer.
- Spring Security handles `ClientRegistration`, OAuth2 Authorization Code flow, `state`/nonce/PKCE per config, token exchange, and OIDC ID Token/JWKS/issuer/audience validation. Never Base64-decode a JWT yourself and trust its claims.
- `client-secret` uses environment placeholders; never hardcode secrets or put them into Git/Google Sheets. `profile`/`email` scopes are meaningful only if the app needs them; minimize per least-data principles.
- `secure: false` and HTTP are for localhost only. Production needs HTTPS, `Secure=true`, trusted reverse-proxy forwarding, and a shared session store across multiple pods.
- Boot may perform OIDC discovery immediately when building `ClientRegistration`; **start Keycloak before running the app/tests** or configure an appropriate test-only `ClientRegistrationRepository` stub.
- H2 in-memory data disappears on restart; production uses PostgreSQL, a migration tool, and approved provisioning.

### 4.2. `schema.sql` — Stable Identity, Membership, and Tenant Data

```sql
CREATE TABLE app_account (
    account_id VARCHAR(64) PRIMARY KEY,
    active BOOLEAN NOT NULL
);

CREATE TABLE federated_identity (
    issuer VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (issuer, subject),
    FOREIGN KEY (account_id) REFERENCES app_account(account_id)
);

CREATE INDEX idx_identity_account
    ON federated_identity(account_id);

CREATE TABLE tenant_membership (
    account_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    permission VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (account_id, tenant_id, permission),
    FOREIGN KEY (account_id) REFERENCES app_account(account_id)
);

CREATE TABLE tenant_note (
    tenant_id VARCHAR(64) NOT NULL,
    note_id BIGINT NOT NULL,
    body VARCHAR(4000) NOT NULL,
    PRIMARY KEY (tenant_id, note_id)
);
```

**Why two composite primary keys?**

- `PRIMARY KEY (issuer, subject)`: the same `sub` under different issuers will never merge, while the same `(iss,sub)` cannot point to two local accounts during concurrent imports.
- `PRIMARY KEY (tenant_id, note_id)`: North and South can both have `note_id=1` without colliding; every resource query must include tenant.
- `account_id` is decoupled from email, `sub`, and display name, enabling controlled contact email updates or subject migrations.
- `tenant_membership` represents locally approved permissions. Successful identity login does **not** automatically grant membership. Production adds owner, expiry, grant source, audit, SoD, indexes/constraints, and tenant lifecycle.

### 4.3. `data.sql` — Intentional Collision Setup

```sql
INSERT INTO app_account(account_id, active)
VALUES ('acct-n', TRUE), ('acct-s', TRUE);

-- Test fixtures; do not pretend Keycloak emits same-sub.
INSERT INTO federated_identity
  (issuer, subject, account_id, active)
VALUES
  ('http://localhost:8180/realms/north', 'same-sub', 'acct-n', TRUE),
  ('http://localhost:8180/realms/south', 'same-sub', 'acct-s', TRUE);

INSERT INTO tenant_membership
  (account_id, tenant_id, permission, active)
VALUES
  ('acct-n', 'north', 'NOTE_READ', TRUE),
  ('acct-s', 'south', 'NOTE_READ', TRUE);

INSERT INTO tenant_note(tenant_id, note_id, body)
VALUES
  ('north', 1, 'NORTH_ONLY'),
  ('south', 1, 'SOUTH_ONLY');
```

**Note:** `same-sub` is strictly a **synthetic subject fixture** for MockMvc/Java account-collision tests. Real Keycloak users usually receive distinct UUID-style `sub` values. During real browser login, the app returns 403 on notes until an administrator/owner verifies the identity and binds it to a local account with membership. This is **deny by default**, not a bug to bypass.

## 5. Java Spring Security Authentication and Tenant Policy

### 5.1. `FederationLabApplication.java`

```java
package com.example.federationlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationLabApplication.class, args);
    }
}
```

### 5.2. `WebSecurityConfiguration.java`

```java
package com.example.federationlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

`authenticated()` only checks authentication; it **does not automatically enforce tenant isolation**. `@EnableMethodSecurity` lets `@PreAuthorize` guard business methods before queries execute. Having two client registrations exposes two start URLs at `/oauth2/authorization/north` and `/oauth2/authorization/south`, with default callbacks at `/login/oauth2/code/north` and `/login/oauth2/code/south`.

### 5.3. `TenantGuard.java` — Checking Verified Issuer, Subject, and Grant

```java
package com.example.federationlab;

import java.util.Map;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component("tenantGuard")
public class TenantGuard {

    private static final Map<String, String> TENANT_ISSUERS =
        Map.of(
            "north", "http://localhost:8180/realms/north",
            "south", "http://localhost:8180/realms/south"
        );

    private final JdbcTemplate jdbc;

    public TenantGuard(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean canRead(Authentication authentication,
                           String tenantId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        String allowedIssuer = TENANT_ISSUERS.get(tenantId);
        if (allowedIssuer == null) {
            return false; // unknown tenant
        }

        String issuer = user.getIdToken().getClaimAsString("iss");
        String subject = user.getIdToken().getSubject();

        if (!Objects.equals(allowedIssuer, issuer)
                || subject == null || subject.isBlank()) {
            return false;
        }

        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*)
              FROM federated_identity fi
              JOIN app_account a
                ON a.account_id = fi.account_id
              JOIN tenant_membership tm
                ON tm.account_id = a.account_id
             WHERE fi.issuer = ?
               AND fi.subject = ?
               AND fi.active = TRUE
               AND a.active = TRUE
               AND tm.tenant_id = ?
               AND tm.permission = 'NOTE_READ'
               AND tm.active = TRUE
            """,
            Integer.class, issuer, subject, tenantId
        );

        return count != null && count > 0;
    }
}
```

**Reading the code along trust boundaries:**

1. `OidcUser` is created by Spring OAuth2 Login after verifying the ID Token and OIDC flow; never treat raw HTTP headers/queries as a principal.
2. The `issuer+subject` pair resolves the exact identity. `getClaimAsString("iss")`/`getSubject()` read from `OidcIdToken`, not from `/tenants/south`.
3. `TENANT_ISSUERS` is a **lab allowlist**, not a rule for all architectures. When one tenant trusts multiple IdPs, use an approved issuer-set mapping and independent memberships.
4. `fi.active`, `a.active`, and `tm.active` must all be TRUE. DB membership changes take effect on the next request, even without logging out the local session (unless production adds an un-invalidated authorization cache).
5. `permission='NOTE_READ'` does not grant `NOTE_WRITE` or `ADMIN`. Never map raw `groups=["admin"]` from all IdPs to global admin.
6. `JdbcTemplate` uses bound parameters; never concatenate `subject`/`tenantId` into SQL.
7. On API routes, a logged-in user can still receive `403`; that is a **business authorization denial**, distinct from an OIDC authentication failure.
8. `oidcLogin()` tests inject a synthetic principal into MockMvc; that is policy testing, not cryptographic token validation.
9. Services annotated with `@PreAuthorize` must be invoked through a Spring-managed bean/AOP proxy; avoid self-invocation that bypasses enforcement.
10. Production apps typically check permissions at action time from an authoritative DB/cache version rather than relying solely on login-time cached `GrantedAuthorities`.

### 5.4. `TenantNoteService.java` — Tenant-Scoped Queries

```java
package com.example.federationlab;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TenantNoteService {

    private final JdbcTemplate jdbc;

    public TenantNoteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @PreAuthorize("@tenantGuard.canRead(authentication, #p0)")
    public String readNote(String tenantId, long noteId) {

        List<String> rows = jdbc.query(
            """
            SELECT body
              FROM tenant_note
             WHERE tenant_id = ?
               AND note_id = ?
            """,
            (rs, rowNum) -> rs.getString("body"),
            tenantId, noteId
        );

        if (rows.isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Note not found");
        }
        return rows.get(0);
    }
}
```

**Defense in depth:** `@PreAuthorize` checks permission **before** the method body runs; SQL `WHERE tenant_id=? AND note_id=?` ensures the query itself is tenant-scoped. **Wrong:** `SELECT body FROM tenant_note WHERE note_id=?`, because IDs can collide across tenants and another code path could bypass a controller guard.

### 5.5. `TenantNoteController.java`

```java
package com.example.federationlab;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TenantNoteController {

    private final TenantNoteService service;

    public TenantNoteController(TenantNoteService service) {
        this.service = service;
    }

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "northLogin", "/oauth2/authorization/north",
            "southLogin", "/oauth2/authorization/south"
        );
    }

    // Lab-only authenticated endpoint for manual onboarding.
    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getIdToken().getSubject()
        );
    }

    @GetMapping("/api/tenants/{tenantId}/notes/{noteId}")
    public Map<String, Object> read(
            @PathVariable String tenantId,
            @PathVariable long noteId) {
        return Map.of(
            "tenant", tenantId,
            "id", noteId,
            "body", service.readNote(tenantId, noteId)
        );
    }
}
```

`/me` lets an authenticated user inspect **their own identity** so an admin can approve onboarding in the lab. `iss`/`sub` are privacy-sensitive identifiers; remove or restrict this endpoint in production, and never log full user identities. `service.readNote` is invoked via a Spring bean so method-security AOP executes properly.

## 6. Running the Lab and Onboarding Real Identities

Before running Maven, start Keycloak, verify `/.well-known/openid-configuration` for both realms, and supply each secret via environment variables. With Java 17 + Maven:

```bash
mvn -version
mvn test
mvn spring-boot:run
```

Browser sequence:

1. Profile N: `http://localhost:8080/oauth2/authorization/north` → Keycloak North login → Spring callback.
2. Profile S: `http://localhost:8080/oauth2/authorization/south` → Keycloak South login → Spring callback.
3. Open `http://localhost:8080/me` in each profile; confirm two distinct `issuer` values and read the test users' `sub` values locally in the lab (do not paste into shared logs).
4. Because `data.sql` only seeds `same-sub`, real Keycloak users initially succeed at OIDC login yet still get `403` on `/api/tenants/north/notes/1`. That is **deny by default**.
5. Only after business-owner approval, an admin updates the two seeded `subject` values (preserving `issuer`/`accountId`) to the real subjects and restarts the H2 app. Example:

```sql
-- Lab-only: values must come from verified login and approval.
UPDATE federated_identity
   SET subject = 'VERIFIED_NORTH_SUB'
 WHERE issuer = 'http://localhost:8180/realms/north'
   AND account_id = 'acct-n';

UPDATE federated_identity
   SET subject = 'VERIFIED_SOUTH_SUB'
 WHERE issuer = 'http://localhost:8180/realms/south'
   AND account_id = 'acct-s';
```

With in-memory H2, the simplest way is editing `data.sql` accordingly and restarting; if running `UPDATE` directly via a DB admin tool in the lab, secure that tool since no public H2 console is enabled above. **Never build a self-service endpoint `POST /grant?tenant=south`**: browsers must never grant themselves membership. Production uses approved provisioning/SCIM/invite flows with transactions/uniqueness/auditing and authoritative HR/partner identity sources.

Expected results after provisioning:

| Browser | Request | Result |
| --- | --- | --- |
| Profile N | `GET /api/tenants/north/notes/1` | 200, `NORTH_ONLY` |
| Profile N | `GET /api/tenants/south/notes/1` | **403**, no `SOUTH_ONLY` |
| Profile S | `GET /api/tenants/south/notes/1` | 200, `SOUTH_ONLY` |
| Profile S | `GET /api/tenants/north/notes/1` | **403**, no `NORTH_ONLY` |
| Unauthenticated | GET protected resource | Login redirect (web flow) or error per entry point |
| Logged in with unmapped account | GET tenant note | **403** (correct) |

**Distinction required:** "OIDC login success" only guarantees Spring received an identity, not that the user holds a business grant. An un-onboarded user getting 403 is **not** a reason to disable the tenant guard.

## 7. MockMvc Testing Cross-Tenant Access

`oidcLogin()` in `spring-security-test` injects a synthetic OIDC principal into a MockMvc request, testing **post-authentication authorization**. It performs no authorization code exchange, real JWT signature verification, or PKCE/nonce/HTTPS checks. To test the handshake, use Keycloak and signed-token E2E tests.

File `src/test/java/com/example/federationlab/TenantIsolationMvcTest.java`:

```java
package com.example.federationlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantIsolationMvcTest {

    @Autowired
    MockMvc mvc;

    static RequestPostProcessor id(String issuer, String subject) {
        return oidcLogin().idToken(token -> token
            .claim("iss", issuer)
            .claim("sub", subject));
    }

    @Test
    void northAllowedButSouthForbidden() throws Exception {
        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "same-sub")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.body").value("NORTH_ONLY"));

        mvc.perform(get("/api/tenants/south/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "same-sub")))
            .andExpect(status().isForbidden());
    }

    @Test
    void southAllowedButNorthForbidden() throws Exception {
        mvc.perform(get("/api/tenants/south/notes/1")
                .with(id("http://localhost:8180/realms/south",
                         "same-sub")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.body").value("SOUTH_ONLY"));

        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/south",
                         "same-sub")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownIssuerSubjectTenantAreDenied() throws Exception {
        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/attacker",
                         "same-sub")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/tenants/north/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "not-linked")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/tenants/east/notes/1")
                .with(id("http://localhost:8180/realms/north",
                         "same-sub")))
            .andExpect(status().isForbidden());
    }
}
```

**Accurately verifies:** Identical `sub=same-sub` does not merge accounts; North cannot read South; South cannot read North; unknown issuer/sub/tenant is denied; API body matches. If Spring OIDC discovery at startup requires a live OP, **start Keycloak before `mvn test`** or configure a test-only `ClientRegistrationRepository` stub so unit tests do not depend on an OP; never treat MockMvc as proof of cryptographic validation.

**Caveat:** To test revocation in the app, add a test toggling `app_account.active=false` / `tenant_membership.active=false` within a test transaction, repeat the MockMvc request, and roll back the fixture. Do not assert only on a `role` claim inside OIDC; effective access must come from the DB.

## 8. Standalone Java 17 — Simulating Tenant Decisions

Runs without Spring/Keycloak/DB; the model assumes **issuer/subject were already verified by the provider before calling**. Never accept them directly from HTTP query parameters in production.

File `TwoIssuerTenantIsolationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class TwoIssuerTenantIsolationDemo {

    static final String NORTH = "https://idp.example.org/north";
    static final String SOUTH = "https://idp.example.org/south";

    record Key(String issuer, String subject) { }
    record Account(String id, String email, boolean active) { }

    enum Verdict {
        ALLOW, DENY_TENANT, DENY_ISSUER, DENY_IDENTITY,
        DENY_INACTIVE, DENY_MEMBERSHIP, DENY_PERMISSION
    }

    final Map<Key, Account> identities = new HashMap<>();
    final Map<String, Set<String>> grants = new HashMap<>();
    final Map<String, String> tenantIssuer =
        Map.of("north", NORTH, "south", SOUTH);

    void bind(String issuer, String sub, Account account) {
        identities.put(new Key(issuer, sub), account);
    }

    void grant(String account, String tenant, String permission) {
        grants.put(account, Set.of(tenant, permission));
    }

    Verdict read(String issuer, String sub,
                 String tenant, String permission) {

        String expected = tenantIssuer.get(tenant);
        if (expected == null) return Verdict.DENY_TENANT;
        if (!expected.equals(issuer)) return Verdict.DENY_ISSUER;

        Account account = identities.get(new Key(issuer, sub));
        if (account == null) return Verdict.DENY_IDENTITY;
        if (!account.active()) return Verdict.DENY_INACTIVE;

        Set<String> grant = grants.get(account.id());
        if (grant == null || !grant.contains(tenant)) {
            return Verdict.DENY_MEMBERSHIP;
        }
        if (!grant.contains(permission)) {
            return Verdict.DENY_PERMISSION;
        }
        return Verdict.ALLOW;
    }

    public static void main(String[] args) {
        var app = new TwoIssuerTenantIsolationDemo();

        app.bind(NORTH, "same-sub",
            new Account("acct-n", "same@example.org", true));
        app.bind(SOUTH, "same-sub",
            new Account("acct-s", "same@example.org", true));

        app.grant("acct-n", "north", "NOTE_READ");
        app.grant("acct-s", "south", "NOTE_READ");

        System.out.println("northOwn=" +
            app.read(NORTH, "same-sub", "north", "NOTE_READ"));

        System.out.println("southOwn=" +
            app.read(SOUTH, "same-sub", "south", "NOTE_READ"));

        System.out.println("northToSouth=" +
            app.read(NORTH, "same-sub", "south", "NOTE_READ"));

        System.out.println("southToNorth=" +
            app.read(SOUTH, "same-sub", "north", "NOTE_READ"));

        System.out.println("unknownTenant=" +
            app.read(NORTH, "same-sub", "east", "NOTE_READ"));

        System.out.println("unlinked=" +
            app.read(NORTH, "other-sub", "north", "NOTE_READ"));

        System.out.println("wrongPermission=" +
            app.read(NORTH, "same-sub", "north", "NOTE_WRITE"));

        Account n = app.identities.get(new Key(NORTH, "same-sub"));
        Account s = app.identities.get(new Key(SOUTH, "same-sub"));
        System.out.println("differentAccounts=" +
            !n.id().equals(s.id()));
        System.out.println("sameEmail=" +
            n.email().equals(s.email()));

        app.bind(NORTH, "same-sub",
            new Account("acct-n", "same@example.org", false));

        System.out.println("disabledNorth=" +
            app.read(NORTH, "same-sub", "north", "NOTE_READ"));

        System.out.println("southUnaffected=" +
            app.read(SOUTH, "same-sub", "south", "NOTE_READ"));
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 TwoIssuerTenantIsolationDemo.java
java TwoIssuerTenantIsolationDemo
```

**Exact stdout:**

```text
northOwn=ALLOW
southOwn=ALLOW
northToSouth=DENY_ISSUER
southToNorth=DENY_ISSUER
unknownTenant=DENY_TENANT
unlinked=DENY_IDENTITY
wrongPermission=DENY_PERMISSION
differentAccounts=true
sameEmail=true
disabledNorth=DENY_INACTIVE
southUnaffected=ALLOW
```

The program only checks composite keys and simulated grants; it does not verify JWTs, signatures, SAML, browser sessions, TLS, role databases, or concurrency. It never uses `email` as an identity key even though both accounts have identical emails; `differentAccounts=true` demonstrates this. Never pass unauthenticated client `issuer`/`sub` inputs to `read` and treat `ALLOW` as proof of login.

## 9. End-to-End Browser Test Flow

| Step | Profile N | Profile S | Expected Observation |
| --- | --- | --- | --- |
| 1 | `GET /oauth2/authorization/north` | — | Redirects to North issuer |
| 2 | — | `GET /oauth2/authorization/south` | Redirects to South issuer |
| 3 | Login/MFA on North | Login/MFA on South | OPs authenticate independently |
| 4 | `/login/oauth2/code/north` | `/login/oauth2/code/south` | Spring verifies state/nonce/token |
| 5 | `GET /me` | `GET /me` | Two distinct issuers; no email auto-linking |
| 6 | After approved onboarding, GET North note | GET South note | 200, matching body |
| 7 | GET South note | GET North note | **403** in both directions |
| 8 | Change email at OP, keep `sub` | Same | Internal account unchanged |
| 9 | Revoke membership, keep session | Login unchanged | North denied, South unaffected |

One browser session typically holds only one current `Authentication`; **use separate profiles/containers to test two users concurrently**. If you intentionally log into North then South in the same profile, verify proper session replacement and `state` correlation rather than assuming "tenant isolation failed" just because the active account switched.

## 10. Data Layer and IDOR: Query Conditions That Must Never Be Omitted

**Wrong:**

```java
jdbc.queryForObject(
    "SELECT body FROM tenant_note WHERE note_id = ?",
    String.class, noteId);
```

**Right:**

```java
jdbc.query(
    "SELECT body FROM tenant_note WHERE tenant_id = ? AND note_id = ?",
    (rs, n) -> rs.getString("body"),
    verifiedAuthorizedTenantId, noteId);
```

`verifiedAuthorizedTenantId` is not a raw path/query value; in `TenantNoteService`, the method argument was verified by `TenantGuard` via Spring Method Security. For lists, search, exports, batch jobs, async tasks, WebSockets, caches, and files:

- Every SQL query, full-text search, aggregate, count, pagination, and export must carry tenant scope.
- Cache keys must include tenant identity, e.g., `tenant:north:note:1`; `note:1` alone risks cross-tenant cache bleed.
- Background jobs need a verified tenant context; never accept tenant from an untrusted message queue.
- Resource ownership/permissions must be enforced at the **service layer**; hiding UI buttons is not authorization.
- Short-lived CDN/object-storage links may be issued only after tenant/permission checks.
- Database backups, logs, APM, and error responses must never leak another tenant's body, record counts, or group memberships.

**PostgreSQL RLS (optional defense-in-depth):**

```sql
ALTER TABLE tenant_note ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_note FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope
    ON tenant_note
    FOR SELECT
    USING (tenant_id = current_setting('app.current_tenant', true));
```

This is a **SQL fragment** for production design, not an H2 script. With pooled connections, `app.current_tenant` must be set from the **authorized tenant** using `SET LOCAL` or transaction-local `set_config(..., true)`, preventing a prior request's session variable from leaking into the next request. Superuser/`BYPASSRLS` DB roles can still bypass RLS; never run the app with such a role. RLS does not replace OIDC issuer validation, local grants, or service authorization. Test RLS against real database roles and connection pools before deploying.

## 11. Extending to Two IdPs Across Different Protocols: OIDC and SAML2

The lab chose two OIDC issuers, yet the same identity/tenant model applies when **North uses OIDC and South uses SAML2**.

After a verified OIDC flow:

```text
protocol=OIDC
providerId=validated ID Token iss
subjectId=validated ID Token sub
identityKey=(OIDC, iss, sub)
```

After SAML `saml2Login()` verifies signatures and conditions:

```text
protocol=SAML2
providerId=trusted IdP EntityID / Issuer
subjectId=approved stable NameID or asserted stable attribute
qualifierScope=NameID Format + NameQualifier/SPNameQualifier as needed
identityKey=(SAML2, issuer, qualifierScope, stableSubject)
```

**SAML caveats:**

- `transient NameID` is not stable across logins; `emailAddress NameID` can change or be reassigned. Use a persistent NameID or stable attribute guaranteed by the IdP and verified by the RP.
- `RelyingPartyRegistration.registrationId` is neither the IdP EntityID nor automatically the tenant.
- Verify the SAML XML Signature with trusted IdP verification credentials; check `AudienceRestriction`, `Destination`, `Recipient`, `InResponseTo`, `NotBefore`/`NotOnOrAfter`, and replay before mapping the user.
- Two SAML IdPs both emitting `groups=Admins` do not authorize auto-mapping to global admin.
- Never pull a signing certificate out of an untrusted SAMLResponse `KeyInfo` and trust it.
- SP signing/decryption credentials differ from IdP signing certs, and metadata signer/TLS certs have separate trust boundaries.
- If an RP has multiple SAML registrations and unsolicited IdP-initiated SSO lacks `InResponseTo`, design unambiguous route/issuer/audience resolution or reject that flow.

When storing multiple protocols in the same identity table, include `protocol`/provider namespace in the `UNIQUE` key as needed. **Account linking between OIDC and SAML must occur only via verified re-authentication/approval**—never by matching email. Linking identities must not automatically union all tenant permissions.

## 12. Multi-Issuer API Resource Server Is a Different Case

The web lab uses `oauth2Login()` and Spring HttpSession. When an API accepts Bearer access tokens from two Authorization Servers, configure **`oauth2ResourceServer`** with issuer-specific JWT validation—never substitute the RP's OIDC ID Token for an access token.

Spring Security Servlet supports a resolver over trusted issuers (a fragment for a separate API `SecurityFilterChain`, adding the Resource Server dependency):

```java
var resolver =
    org.springframework.security.oauth2.server.resource.authentication
        .JwtIssuerAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://op-north.example.org/issuer",
            "https://op-south.example.org/issuer"
        );

http.authorizeHttpRequests(auth ->
        auth.anyRequest().authenticated())
    .oauth2ResourceServer(resource ->
        resource.authenticationManagerResolver(resolver));
```

- Never construct a decoder from an arbitrary `iss` inside an unverified token, avoiding SSRF and attacker-selected keys.
- Beyond issuer/signature/expiry, check **API audience**, permitted algorithms/scopes, and business tenant membership. A trusted issuer **does not automatically grant access to every tenant**.
- Separate `SecurityFilterChain`s for browser OAuth2 Login and API bearer tokens when used side-by-side so login callbacks are not intercepted by the API chain.
- Spring's `jwt()` MockMvc post-processor tests policy with a mock principal; it verifies no real signature. Use signed JWT fixtures or real authorization servers for crypto/issuer/audience tests.

## 13. Sessions and Account Lifecycle

- **Joiner:** IdP authenticates identity; business owner/HR confirms user and grant; add `(issuer,sub)` → `accountId` binding with approval/audit, granting only minimum membership.
- **Mover:** revoke old tenant grants and assign the new tenant after review; never retain old access via cached groups/roles.
- **Leaver:** disable authoritative account/membership, revoke Spring sessions/refresh tokens per policy, and enforce action-time API denials. Issued JWTs have their own `exp`; disabling the IdP account alone does not revoke all active JWTs.
- **Local logout:** clears the RP session; OP North/South SSO cookies have independent lifecycles. OIDC RP-initiated/back-channel logout works only when supported and properly implemented by provider and protocol.
- **Issuer/client migration:** a pairwise `sub`/issuer change is an identity migration, not an "email change"; perform a verified linkage ceremony with audit and uniqueness locks.
- **Multi-pod sessions:** OAuth2 authorization requests/state require session continuity (Spring Session / shared state / appropriate sticky routing). Callbacks hitting another pod must not lose `state` or skip `state` checks.
- **Role caching:** snapshotting `GrantedAuthority` at login lets stale business grants survive for the session's lifetime. The lab queries active membership on every request; production caches need invalidation/versioning and an SLA.
- **Cookies:** production needs `Secure; HttpOnly`, appropriate `SameSite`, and restricted Domain/Path. OIDC top-level GET callbacks usually work with `Lax`; cross-site POST modes require dedicated review.
- **Forwarded headers:** reverse proxies must strip/overwrite `Forwarded`/`X-Forwarded-*` so Spring constructs the exact public redirect URI without trusting browser-supplied `Host` headers.

## 14. Security Test Matrix

| Test | Fixture / Action | Result |
| --- | --- | --- |
| North own resource | North issuer/sub + NOTE_READ North | **200 NORTH_ONLY** |
| South own resource | South issuer/sub + NOTE_READ South | **200 SOUTH_ONLY** |
| North to South path | Login North, swap tenant path | **403** |
| South to North path | Login South, swap tenant path | **403** |
| Same `sub` different issuer | `same-sub` in North & South | Two separate accounts |
| Same email | Duplicate email across OPs | No automatic account linking |
| Unknown issuer | Third realm ID Token / mock | Rejected by OP validation / tenant guard |
| Unknown subject | Approved issuer, unmapped sub | 403 |
| Unknown tenant | `/tenants/east` | 403/404 per policy |
| Disable local account | `active=false`, session still exists | Next request denied |
| Revoke membership | `tm.active=false` | Next request denied |
| Note ID collision | Both tenants have note `1` | No data mixing |
| SQL without tenant | `WHERE note_id=?` | Caught by security regression |
| Cache key without tenant | `note:1` only | Rejected / cache design fixed |
| Raw group `admin` | Claim present, no approved grant | No admin |
| Duplicate email with verified flag | Both OPs emit `email_verified` | No merge |
| Forged `X-User`/`X-Tenant` | Attacker headers | No effect |
| Altered `state` | OAuth callback tampering | Auth failure |
| Bad PKCE verifier | Authorization/token mismatch | Token endpoint rejects |
| Unknown JWK `kid` | Untrusted signing key | Token rejected |
| Wrong `iss` | Signed token from third realm | Reject |
| Wrong `aud` | Token for another client/API | Reject |
| Expired ID Token | Past `exp` | Reject |
| OIDC issuer migration | New issuer/sub | Approved migration only |
| Pairwise subject rotated | Sector/client changes | No silent email linking |
| Concurrent two tabs | North and South callbacks overlap | Valid state or safe failure |
| OIDC OP outage | North token endpoint down | No fallback to South identity |
| Session cookie missing | Callback session lost | Safe correlation failure |
| SAML wrong issuer | Valid signature, wrong IdP registration | Reject |
| SAML wrong audience | Signed assertion for another SP | Reject |
| SAML transient NameID | Subject changes each login | No accidental account merge |
| API unknown issuer | JWT `iss` attacker URL | Reject, no arbitrary JWKS fetch |
| API wrong audience | Valid signature for different API | Reject |
| Multi-pod stale grants | One pod retains old cache | Fails regression until converged |
| RLS pooled connection leak | Prior tenant context remains | Reject / fix transaction scope |
| Cross-tenant export/search | Unscoped bulk data endpoint | No leaked records |
| Sensitive logs | Raw token/cookie/SAMLResponse in TRACE | QA fails, redact |

**Test fixture note:** MockMvc `oidcLogin()` fakes claims without cryptographic signatures. Signed-token E2E negative tests must use OP/JWK test keys; editing a SAML assertion after signing only invalidates the signature and does not prove the audience validator works. Keep **policy tests** distinct from **protocol/trust tests**.

## 15. Troubleshooting Runbook for Common Failures

### 15.1. North Login Succeeds Yet Note Returns 403

1. Check `/me` to confirm exact North `iss` and real `sub` from the OP.
2. Check `federated_identity` for an active exact `(issuer,sub)` mapping; `data.sql`'s synthetic `same-sub` may not have been replaced yet.
3. Check `app_account.active` and `tenant_membership` grant `NOTE_READ` on North.
4. Check `@EnableMethodSecurity`, `TenantGuard`, transaction state, and read-replica lag.
5. Never "fix" this by removing the guard or auto-granting tenant access by email.

### 15.2. South User Sees North Data

This is a **security incident**. Isolate the endpoint per incident procedure, assess impact, and verify whether identity keys dropped `issuer`, SQL omitted the tenant predicate, caches/search/exports lacked tenant scoping, or method security was bypassed via self-invocation. Add negative regression tests and evaluate privacy/disclosure obligations per policy.

### 15.3. OIDC Callback Reports `invalid_state` or Redirect Loop

Inspect cookie Domain/Path/SameSite/Secure, session store (especially multi-pod), browser tabs, reverse-proxy public HTTPS host/port, and the authorization request repository. Never disable `state`/nonce/PKCE. Token exchange is **server-to-server back-channel**, absent from the browser Network panel; inspect sanitized Spring/OP logs instead.

### 15.4. Two Users Sharing an Email Merged into One Account

Audit `findByEmail` queries, unique constraints, JIT provisioning, and group role mappers. Migrate to `(iss,sub)` with approved, audited migration; never auto-link on `email_verified`. If data exposure occurred, trigger security/privacy incident handling.

### 15.5. Changing Issuer or Signing Key

Verify OP discovery `issuer`, JWKS `kid`, client registration, allowlist, and key-rotation timeline. Never import JWKs from attacker-supplied URLs. For client/issuer migration, use approved identity mapping and planned rollover; never reassign `account_id` by email.

### 15.6. Leaver Still Has Access in Existing Session

Disable account/membership in the authoritative layer, invalidate sessions/refresh tokens per SLA, inspect DB status/authorization caches, and verify API bearer JWT expiry. Confirm requests using the old session are denied across all pods; blocking new IdP logins alone is insufficient.

## 16. Anti-Patterns to Avoid

| Wrong | Risk | Right |
| --- | --- | --- |
| `users.email PRIMARY KEY` | Email changes/collides/reused | Local account ID + federated `(iss,sub)` |
| `Map<sub,account>` | Cross-OP collisions | Composite key |
| Trust `X-Tenant` from browser | Tenant impersonation | Validated principal + approved membership |
| Decode JWT then accept `groups` | Claim forgery | Verify ID Token / access token first |
| JWK URL from arbitrary JWT `iss` | SSRF / trust bypass | Trusted issuer allowlist |
| Auto-map `admin` across all issuers | Cross-tenant privilege escalation | Issuer-specific mapping + local policy |
| `authenticated()` is enough | IDOR | Service/resource authorization |
| `SELECT WHERE note_id=?` | Data leak | `WHERE tenant_id=? AND note_id=?` |
| Cache key `note:1` | Tenant data bleed | Tenant-scoped cache key |
| Auto-link on matching email | Account takeover | Verified linking ceremony |
| Disable `state` on session errors | Login CSRF | Fix session/cookies |
| Use ID Token for APIs | Wrong audience/semantics | OAuth access token + Resource Server |
| Disable CSRF app-wide | Browser CSRF | Protocol-specific handling |
| Self-invocation bypasses `@PreAuthorize` | Skipped authorization | Spring proxy service calls |
| Log raw tokens/HAR | Credential/PII leak | Sanitized audit events |
| Trust arbitrary SAML `KeyInfo` | Untrusted signer | Approved IdP metadata/cert |
| Reuse one browser profile for two users | Session overwriting | Separate profiles |
| Wait for token expiry on high-risk leavers | Stale privilege window | Active revocation / action-time checks |

## 17. Observability and QA Evidence

Audit event example (values are illustrative only):

```json
{
  "event": "TENANT_AUTHZ_DECISION",
  "utc": "2030-02-03T10:15:30Z",
  "trustedIssuerId": "north-op",
  "accountRef": "pseudonymous-account",
  "requestedTenant": "south",
  "permission": "NOTE_READ",
  "decision": "DENY",
  "reason": "ISSUER_NOT_ALLOWED_FOR_TENANT",
  "requestId": "server-generated-id"
}
```

Never log raw `sub`/email unnecessarily, access/ID tokens, authorization codes, `state`/nonces, cookies, secrets, SAMLResponses, private signing keys, or full SQL parameters. Metric labels should use only known registration/tenant values, never attacker-controlled identifiers. QA sign-off requires both **positive tests** (right tenant 200) and **negative tests** (wrong tenant 403/no data), config/runtime readback, IdP signed-token E2E, and data-scoping checks—not just observing a successful login screen.

## 18. Self-Check Questions and Answers

**1.** North and South both have `sub=123`; can `sub` be used as a global unique key?

**Answer:** No. `sub` is unique only within an issuer; you must use `(iss,sub)`.

**2.** Two OPs share the same email with `email_verified=true`; can accounts auto-merge?

**Answer:** No. Linking requires dedicated proof/approval, not email.

**3.** Does a successful OIDC login automatically grant `NOTE_READ` on North?

**Answer:** No. Business grants in local membership/authoritative stores must be approved.

**4.** Could a North user change the URL to South if the controller only requires `authenticated()`?

**Answer:** Yes, that is a risk if relying solely on `authenticated()`; the lab uses `@PreAuthorize` and tenant-scoped SQL to deny it.

**5.** Why does the note PK include `tenant_id,note_id`?

**Answer:** The same note ID can exist across multiple tenants; keys and queries must include tenant.

**6.** Does MockMvc `oidcLogin()` prove signature/PKCE/JWKS validation?

**Answer:** No, because it mocks the principal; real OP / signed-token E2E tests are required.

**7.** If a user's email changes while `iss/sub` stays the same, should the local account ID change?

**Answer:** No. Update display/contact attributes per policy while keeping the mapping stable.

**8.** An IdP pairwise `sub` changes when the client sector changes; use email to "recover" the mapping?

**Answer:** No. Use verified/approved migration linking.

**9.** A JWT access token carries `iss` from a third tenant; can you fetch JWKS from that URL to test?

**Answer:** No. Use only a trusted issuer allowlist to prevent SSRF and untrusted signing keys.

**10.** Does disabling a user at the OP automatically invalidate Spring `HttpSession` and all JWTs?

**Answer:** No. You need session/token revocation policies and authoritative access-time checks.

**11.** Is a cache keyed solely by note ID dangerous?

**Answer:** Yes. North and South `note_id=1` data can bleed across tenants. Caches must include tenant and authorization context.

**12.** When adding SAML2, what stable subject can be used?

**Answer:** Only a persistent NameID or approved stable attribute from a verified assertion, scoped by IdP EntityID and qualifiers; never arbitrary transient NameIDs or emails.

## 19. Acceptance Checklist

- [ ] Two OPs/realms have **distinct issuers**, with independently governed client IDs/secrets/redirect URIs/JWKS.
- [ ] Browser logins target `/oauth2/authorization/north` or `/south`, with callbacks to `/login/oauth2/code/{registrationId}`.
- [ ] ID Token signature/issuer/audience/expiry/nonce and authorization transaction `state`/PKCE are verified.
- [ ] Identity table has `PRIMARY KEY (issuer, subject)` and accounts use immutable local IDs.
- [ ] Email, display name, raw groups, URL tenant, and HTTP headers are never used as security principals/grants.
- [ ] Unknown identity/tenant/issuer is denied by default; JIT provisioning never creates privileged memberships.
- [ ] Membership/permission/active status is bound to tenant, with owner approval and offboarding.
- [ ] `@EnableMethodSecurity` works and service `@PreAuthorize` is actually invoked through the proxy.
- [ ] Note/list/export/search SQL queries are tenant-bound, never `note_id` alone.
- [ ] Synthetic tests cover identical `sub`/email and identical note IDs across North and South.
- [ ] North own 200, North→South 403; South own 200, South→North 403.
- [ ] Unknown issuer/subject/tenant, disabled account/grant, and guessed resource IDs are denied.
- [ ] Independent browser profiles are used; session fixation/state/cookie behavior is tested.
- [ ] Token/refresh-token/session lifecycles and IdP logout vs. local RP logout are clearly understood.
- [ ] Production enforces HTTPS, Secure/HttpOnly/SameSite, trusted forwarded headers, secret manager, and network controls.
- [ ] Multi-pod apps use shared session/correlation storage and cache invalidation.
- [ ] API Resource Server (if present) validates trusted issuers, JWK signatures, audience, scopes, and local tenant permissions.
- [ ] SAML adapter (if present) verifies signature/issuer/audience/recipient/time and stable NameID contracts.
- [ ] Account linking and issuer migration require approval/audit, never auto-linking by email.
- [ ] Logs/HAR/metrics contain no bearer artifacts, secrets, raw SAMLResponses, or unnecessary PII.
- [ ] Negative tests run after every IdP config change, key rotation, Spring Security upgrade, and schema migration.
- [ ] PASS verdict rests on **right-IdP authentication + right account mapping + authorized tenant + scoped data query**, not merely a 200 login page.

**Conclusion:** Integrating two IdPs does not stop at two `ClientRegistration` entries. A secure foundation consists of **trusted issuer verification**, **composite `(iss,sub)` identity**, **locally approved tenant grants**, and **tenant-scoped data access**. The lab intentionally seeds `same-sub` and `note_id=1` on both sides to surface account collisions and IDOR. The exercise is successful only when cross-tenant negative cases are **rejected**, even when the browser already holds a valid SSO login.

## 20. Official References

1. [OpenID Connect Core – Claim Stability and Uniqueness](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability): `iss/sub` pair, pairwise subject.
2. [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, endpoints, and JWKS.
3. [Spring Security – OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): multiple ClientRegistrations and provider mapping.
4. [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): Authorization Code login and callbacks.
5. [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
6. [Spring Security – OAuth2 Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oidcLogin()` test double.
7. [Spring Security – Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuer resolver.
8. [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature and claims.
9. [Keycloak – Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): `start-dev` and realms.
10. [Spring Boot – SQL Database Initialization](https://docs.spring.io/spring-boot/reference/data/sql.html): `schema.sql`/`data.sql`.
11. [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).
12. [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
13. [RFC 7636 – PKCE](https://www.rfc-editor.org/rfc/rfc7636).
14. [OASIS SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf).
15. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
16. [OWASP – Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html).
17. [OWASP – Multi Tenant Security](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html).
18. [PostgreSQL – Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
