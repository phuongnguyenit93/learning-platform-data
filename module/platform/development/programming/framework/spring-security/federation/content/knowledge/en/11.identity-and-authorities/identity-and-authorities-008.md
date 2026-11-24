# Combining IdP Permissions with Business Permissions in the Internal Database

**Module:** Spring Security – federation  
**Context:** Identity and authorities  
**Stack:** SAML 2.0 Web Browser SSO, Spring Security 6.x, Spring Boot 3.x, Java 17+.

## 1. Why does successful SSO login not automatically grant data access?

An **Identity Provider (IdP)** authenticates users and may issue organizational attributes such as groups, department, employee ID, or authentication method. The **Service Provider (SP)** is the business application. The SP knows who owns orders, records, and payments; who is allowed to approve within monetary limits; which contracts are active; and which tenant may view which data.

Example: The IdP has verified that an employee belongs to group **finance-readers**, yet the application DB grants **READ** on order **42** and denies access on order **43**. If the SP checks only the IdP group and allows access to all orders, it turns organizational metadata into an ungranted business privilege.

We need to combine three layers:

1. **Authentication:** Did the SAMLResponse genuinely come from a trusted IdP and target the right SP? Who is the user/subject?
2. **Eligibility:** Do verified IdP attributes satisfy functional participation criteria, e.g., group finance-readers?
3. **Business authorization:** Does the internal DB link the subject to an active account and permit the specific operation on the specific resource?

A typical decision:

~~~text
ALLOW read(order=42)
  = trustedSamlAuthentication
  AND idpGroupEligible
  AND localIdentityLinked
  AND localAccountEnabled
  AND businessPermission(order=42, action=READ)
  AND tenantBoundarySatisfied
  AND noExplicitDeny
~~~

This is a **deny by default** model: missing data or any unmet condition → **DENY**. Never use an OR between "IdP says admin" and "DB granted" to open access, unless a special business policy has been explicitly approved and verified.

**Key point:** The IdP answers "who is this user, and what organizational traits do they have?"; the application DB answers "what may this user do to which data?". Authenticate before checking permissions, and authorize per critical resource and action.

## 2. Data source boundaries and sources of truth

| Data | Trusted source | Role |
| --- | --- | --- |
| SAML signature, Issuer, Audience, Destination, Recipient, timing | IdP metadata + Spring Security SAML provider | Verifies assertion validity |
| NameID, subject, SAML AttributeStatement, groups | **Verified Assertion** | Provides external identity and organizational attributes |
| Link from IdP subject to internal user | **Account-linking DB** | Prevents identity mix-ups across IdPs/tenants |
| Account enabled/disabled state | **Application DB** | Enables or locks access within the SP scope |
| Business roles and permissions | **Role/grant/permission DB** | Governs business operations |
| Resource ownership, resource state, tenant | **Application DB/policy service** | Protects individual records |
| SecurityContext/HttpSession | Spring Security SP | Maintains login state; does not auto-sync all permission changes |

This explains why holding **ROLE_USER** in SecurityContext does not automatically grant **order:read:42**. **GrantedAuthority** describes permissions Spring Security knows at a point in time; many resource permissions can only be evaluated via the DB at action time.

### Selectable patterns

- **IdP group as necessary condition, DB as additional sufficient condition:** uses AND; well-suited for sensitive data governance.
- **IdP group mapped to functional role:** e.g., finance-readers ↦ ROLE_FINANCE_USER; user still requires a DB grant for the order.
- **DB-only permissions, IdP for authentication only:** sensible when IdP groups/departments are unstable or outside the organizational contract.
- **Permissions baked into Authentication at login:** suits rarely changing roles, but faces stale permission/revocation issues; design refresh or invalidation.
- **Centralized policy service:** suits multiple apps and complex policies; account for network/latency risks and fail-closed behavior.

There is no universal algorithm to "merge all IdP and DB roles and allow." Every permission needs pre-defined **semantics, authoritative source, negation conditions, and data scope**.

## 3. Receiving the SAML2 principal from Spring Security

In SAML Web Browser SSO, the browser posts SAMLResponse to the Assertion Consumer Service (ACS). Spring Security's **Saml2WebSsoAuthenticationFilter** passes it to the AuthenticationManager/OpenSAML provider. Only after verifying signature, Issuer, AudienceRestriction, Recipient/Destination, timestamps, SubjectConfirmation, and required request correlation does Spring create an authenticated Authentication.

In Spring Security 6.x, the usual result is **Saml2Authentication** with a **Saml2AuthenticatedPrincipal** principal:

~~~java
@GetMapping("/identity")
public Map<String, Object> identity(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
    List<?> groups = principal.getAttribute("groups");

    return Map.of(
        "registrationId", principal.getRelyingPartyRegistrationId(),
        "subject", principal.getName(),
        "groups", groups == null ? List.of() : groups);
}
~~~

The snippet above is a **fragment** needing Java/Spring MVC/SAML imports; it is strictly for learning and **should not be exposed publicly in production** because subject and groups can be identifying data. In a full controller, inject Authentication or `@AuthenticationPrincipal` only after authentication.

- **getName()** typically represents **NameID**, not necessarily an email.
- **getRelyingPartyRegistrationId()** returns the local registration ID such as company, which must bind to the right trusted issuer/metadata.
- **getAttribute("groups")** retrieves the group list if the IdP uses that exact attribute name. SAML allows **multiple values** for an attribute.
- **getFirstAttribute** is handy when the contract guarantees one value; never use it to truncate multi-valued permission lists.
- Claim names may be OIDs/URIs or IdP-specific formats, not `groups` by default. Require a **contract for name, NameFormat, data type, casing/normalization, and issuing authority**.

**Never use `groups` values from HTTP queries/headers or unverified SAMLResponse XML** to grant ROLE_ADMIN. Even with the same name "admins", a partner IdP's group may not carry admin rights in the company's app.

## 4. Identity linking: issuer + subject, not email

Linking data should rely on **(IdP issuer/entityID, stable subject)**. If the project uses a **registrationId** like company, it must be a fixed identifier for the trust relationship to that exact IdP. Two IdPs can emit the exact same NameID for completely different people.

| Trust/registration | Subject | Local user |
| --- | --- | --- |
| company | employee-847 | 1001 |
| partner | employee-847 | 9007 |
| company | employee-911 | 1002 |

**Do not auto-merge the first two people because of matching subject text.** Changing IdP/tenant or NameID format requires an audited link-migration workflow.

### Persistent NameID vs. transient NameID

- **Persistent NameID** is designed to be stable within a specific scope; it can serve as a linking key **if IdP/SP agreed on the contract**.
- **Transient NameID** can change across logins and is unsuitable as a long-term DB key.
- **Email** can change, be reassigned, or lack uniqueness across tenants; never use email as automatic proof to attach to an existing privileged account.
- If using an `employeeId` attribute instead of NameID, verify stability/uniqueness and read it only after SAML verification.

### Provisioning on first login

When no local account link is found, safe options are **deny until approved**, create a **privilege-free pending** account, or JIT-provision baseline permissions per an approved policy. Never auto-create a local ADMIN just because the IdP sent a group string resembling an admin role name.

## 5. Mapping IdP groups to application permissions

An allowlist reduces role-injection risk:

| Authoritative IdP | Exact attribute/value | Mappable meaning | What is NOT granted automatically |
| --- | --- | --- | --- |
| company | groups = finance-readers | Access to finance reading views | Cannot READ every invoice/order |
| company | groups = purchasing | Can use purchasing workflow | Cannot automatically APPROVE or DELETE |
| partner | groups = external-vendor | Restricted vendor functions | Cannot access employee data |
| company | groups = unknown-group | Do not map a role | Never auto-create ROLE_UNKNOWN/ADMIN |

Mapping must check **issuer + attribute name + value**, not value alone. If the application uses **hasRole("FINANCE")**, Spring Security normally checks authority **ROLE_FINANCE**. **hasAuthority("order:read")** matches the exact string, yet permission **on a specific orderId** still requires a DB lookup.

Do not do this:

~~~java
// Unsafe if group has not been allowlisted/mapped to a permission:
new SimpleGrantedAuthority("ROLE_" + rawGroupFromClient);
~~~

This snippet illustrates what to avoid, **not a recommended implementation**. Even with verified groups, the application must control which groups map to which permissions and audit mapping changes.

### Permissions in Authentication can go stale

Spring Security can store GrantedAuthority post-login in **SecurityContext/HttpSession**. If the DB or IdP revokes a permission while the user still holds a session, authorities snapshotted at login may remain unchanged. Therefore:

- Roles controlling low-sensitivity menu display can use short-lived snapshots.
- **Object-level permissions** should query the DB right before the action or use a cache with bounded TTL/invalidation.
- Group changes at the IdP are **unlikely** to appear in an established SAML session automatically; design re-authentication/forced session invalidation or refresh policies per protocol and business requirements.
- When a local account is disabled, block new requests via DB policy even if SecurityContext still holds a valid Authentication.

## 6. Storing business permissions in the DB

Example using **PostgreSQL**, single-tenant to focus on the core principle. Multi-tenant projects must include `tenant_id` in linking tables, permission tables, and record queries.

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE federated_identities (
    registration_id VARCHAR(80) NOT NULL,
    subject_id VARCHAR(300) NOT NULL,
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    PRIMARY KEY (registration_id, subject_id)
);

CREATE TABLE order_permissions (
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    order_id BIGINT NOT NULL,
    permission VARCHAR(32) NOT NULL,
    permitted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (app_user_id, order_id, permission)
);
~~~

Sample data:

~~~sql
INSERT INTO app_users (id, enabled)
VALUES (1001, TRUE);

INSERT INTO federated_identities
    (registration_id, subject_id, app_user_id)
VALUES ('company', 'employee-847', 1001);

INSERT INTO order_permissions
    (app_user_id, order_id, permission, permitted)
VALUES
    (1001, 42, 'READ', TRUE),
    (1001, 43, 'READ', FALSE);
~~~

If subject **employee-847** from company IdP has group finance-readers and `app_users.enabled=true`, permission to read order 42 can be granted; order 43 is denied. If `app_users.enabled=false`, both must be denied.

The linking table has primary key **(registration_id, subject_id)**. Never use `LIKE(email)` or arbitrary "same name so link" queries. Adding/editing account links and grants must go through an approved administrative workflow with auditing and stricter checks if needed.

**Multi-tenant note:** `orderId=42` can exist in multiple tenants. When adding `tenant_id`, bind it to both the local user's tenant and the resource's tenant; queries need tenant filters and appropriate FK/unique constraints. Never accept `tenantId` from a client header on trust.

## 7. Spring Boot 3, Java 17+ example: checking IdP group AND DB permission

The sample application uses **SAML2 browser login** and **method security**. When accessing **GET /orders/42**, Spring Security creates Saml2Authentication after SSO, and **OrderPolicy** checks the IdP group, account link, enabled flag, and grant on orderId.

**Prerequisites for real integration:** Maven Spring Boot 3.x project on Java 17+, approved IdP metadata, SP with matching entityID/ACS, PostgreSQL with created tables/data, datasource config, and environment variables. Domain example.org is illustrative only and provides no live SSO service.

### 7.1. Maven dependencies

Inside `pom.xml` dependencies using an appropriate Spring Boot parent/BOM:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

Do not force an OpenSAML version incompatible with the Spring Security release. JDBC keeps this lesson concise; real systems may use JPA/PermissionEvaluator/AuthorizationManager.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    metadata-location: classpath:metadata/company-idp.xml

spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

server:
  servlet:
    session:
      timeout: 30m
~~~

Place real IdP metadata XML at **src/main/resources/metadata/company-idp.xml**; configure least-privilege DB credentials, parameterized SQL, and TLS/secret manager per environment. Schema is installed by migrations/DBAs; do not rely on Boot auto-creating these tables.

### 7.3. Main class

**src/main/java/com/example/federation/FederationApplication.java**

~~~java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }
}
~~~

### 7.4. Configuring SAML2 and method security

**src/main/java/com/example/federation/SecurityConfig.java**

~~~java
package com.example.federation;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties(
            @Value("${app.saml.metadata-location}") String location) {
        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(location)
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp/company")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(company);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**@EnableMethodSecurity** enables **@PreAuthorize** evaluation; adding annotations on methods without enabling method security is insufficient. **saml2Login()** preserves the standard SAML verification flow and SP session, avoiding manual SAMLResponse parsing to read groups.

SP entityID and ACS are examples and must match the real IdP. Testing on `http://localhost:8080` when the registered ACS is `https://portal.example.org` will prevent callbacks from returning locally; align environments and metadata on both sides rather than disabling Recipient/Audience validation.

### 7.5. OrderPolicy.java: combining IdP group and SQL grant

**src/main/java/com/example/federation/OrderPolicy.java**

~~~java
package com.example.federation;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component("orderPolicy")
public class OrderPolicy {

    private final JdbcTemplate jdbc;

    public OrderPolicy(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public boolean canRead(Authentication authentication, long orderId) {
        if (!(authentication instanceof Saml2Authentication saml)) {
            return false;
        }
        if (!authentication.isAuthenticated()) {
            return false;
        }
        if (!(saml.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }
        if (!"company".equals(principal.getRelyingPartyRegistrationId())) {
            return false;
        }

        List<?> groups = principal.getAttribute("groups");
        if (groups == null || !groups.contains("finance-readers")) {
            return false;
        }

        String subject = principal.getName();
        if (subject == null || subject.isBlank()) {
            return false;
        }

        String sql = """
            SELECT COUNT(*)
              FROM app_users u
              JOIN federated_identities fi
                ON fi.app_user_id = u.id
              JOIN order_permissions op
                ON op.app_user_id = u.id
             WHERE fi.registration_id = ?
               AND fi.subject_id = ?
               AND u.enabled = TRUE
               AND op.order_id = ?
               AND op.permission = 'READ'
               AND op.permitted = TRUE
            """;

        Long count = jdbc.queryForObject(
            sql,
            Long.class,
            principal.getRelyingPartyRegistrationId(),
            subject,
            orderId);

        return count != null && count > 0;
    }
}
~~~

**Explanation:**

1. Accepts only Saml2Authentication established by Spring Security; anonymous/other auth types → **DENY**.
2. Checks registrationId `company`, which must be statically configured to the trusted IdP.
3. Accepts only the `groups` attribute containing **finance-readers** per contract. If the group is missing → DENY; never fall back to allowing.
4. Uses the verified subject to query **federated_identities**, never matching on email.
5. Combines local account **enabled** and a grant record with **permission=READ**, **permitted=TRUE** for the specific orderId.
6. Uses **bind parameters** to prevent SQL injection. `COUNT(*)` returns 0 if the grant/link does not exist.
7. When the DB is unavailable, JdbcTemplate throws an exception; never turn it into **ALLOW**. The app can return a handled 503/5xx without leaking SQL or sensitive info.

**TOCTOU protection:** If permissions are checked initially yet the resource/tenant/grant changes before reading/writing data, a race can occur. For sensitive writes, apply **authorization filters directly inside the read/update statement** or use appropriate transactions/locking rather than assuming a controller check suffices.

### 7.6. OrderController.java: @PreAuthorize protecting the resource

**src/main/java/com/example/federation/OrderController.java**

~~~java
package com.example.federation;

import java.util.Map;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/")
    public String home() {
        return "Federated authorization demo";
    }

    @GetMapping("/orders/{orderId}")
    @PreAuthorize("@orderPolicy.canRead(authentication, #orderId)")
    public Map<String, Object> getOrder(
            @P("orderId") @PathVariable("orderId") long orderId) {

        return Map.of(
            "orderId", orderId,
            "authorization", "passed");
    }
}
~~~

**@P("orderId")** tells Spring Security the parameter name in SpEL **#orderId** regardless of compiler parameter-name retention. **authentication** is the current user's Authentication exposed to method-security expressions.

**The controller returns an illustrative payload only**, not real order records. Production must fetch orders under trusted tenant/permission conditions (in the service layer/DB query). Method security should protect **business services** if multiple REST routes, schedulers, or message handlers can invoke the same logic, rather than relying solely on controllers.

### 7.7. Running and expected behavior

After configuring IdP metadata, SP registration, PostgreSQL, and environment variables, run from the Maven project directory:

~~~bash
mvn spring-boot:run
~~~

Public endpoint:

~~~bash
curl -i http://localhost:8080/
~~~

Response body:

~~~text
Federated authorization demo
~~~

Once a browser completes real SAML login:

| Condition | GET /orders/42 | GET /orders/43 |
| --- | --- | --- |
| IdP group finance-readers; user 1001 enabled; DB grants per sample SQL | **200** | **403** |
| IdP group lacks finance-readers | **403** | **403** |
| app_users.enabled = FALSE | **403** | **403** |
| No account link | **403** | **403** |
| No valid SAML Authentication | Starts login flow | Starts login flow |
| Temporary DB disconnect | **Must not return 200** | **Must not return 200** |

These are logical outcomes of the configuration/SQL, not a claim of live end-to-end execution against a real IdP. If the IdP omits `groups` or sends another value, policy denies access; that is fail-closed behavior, not a reason to drop group checks.

## 8. Standalone Java 17 example with verifiable stdout

The program below simulates only the **logical decision**. It does not verify SAML itself, does not query a DB, and an in-memory Set must not replace real database authorization.

**File: CombinedAccessPolicy.java**

~~~java
import java.util.Set;

public final class CombinedAccessPolicy {

    record Evidence(
        boolean verified,
        String registration,
        String subject,
        Set<String> groups) { }

    record LocalAccount(
        String linkedSubject,
        boolean enabled,
        Set<Long> allowedOrderIds) { }

    static boolean canRead(Evidence evidence,
                           LocalAccount local,
                           long orderId) {
        return evidence != null
            && evidence.verified()
            && "company".equals(evidence.registration())
            && evidence.groups().contains("finance-readers")
            && local != null
            && local.enabled()
            && evidence.subject().equals(local.linkedSubject())
            && local.allowedOrderIds().contains(orderId);
    }

    public static void main(String[] args) {
        Evidence valid = new Evidence(
            true, "company", "employee-847",
            Set.of("finance-readers"));
        LocalAccount account = new LocalAccount(
            "employee-847", true, Set.of(42L));
        Evidence noGroup = new Evidence(
            true, "company", "employee-847", Set.of("staff"));

        System.out.println(
            "allow=" + canRead(valid, account, 42L));
        System.out.println(
            "missingGroup=" + canRead(noGroup, account, 42L));
        System.out.println(
            "noLocalGrant=" + canRead(valid, account, 43L));
        System.out.println(
            "disabledLocalUser=" + canRead(valid,
                new LocalAccount("employee-847", false, Set.of(42L)),
                42L));
        System.out.println(
            "wrongLink=" + canRead(valid,
                new LocalAccount("another-subject", true, Set.of(42L)),
                42L));
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac CombinedAccessPolicy.java
java CombinedAccessPolicy
~~~

**Exact stdout:**

~~~text
allow=true
missingGroup=false
noLocalGrant=false
disabledLocalUser=false
wrongLink=false
~~~

Names and data are hypothetical. **Evidence.verified** in the demo is only a fixed boolean for illustration; production must use Authentication produced after the SAML provider verifies signature/issuer/audience/recipient/timing, never accepting a client-supplied verified flag.

## 9. Permission synchronization and the "stale permissions" problem

After SAML2 login, the SP usually stores Authentication in SecurityContext/HttpSession. Groups from the IdP are a snapshot from when the assertion was received. Local roles loaded into authorities at login can also go stale.

| Strategy | Permission freshness | Trade-off |
| --- | --- | --- |
| Load all roles at SAML login | Snapshot | Fewer DB queries, yet revocations do not take immediate effect |
| Check DB on every sensitive action | Near real-time | Adds latency/queries; needs indexes and availability |
| Cache permissions with short TTL | Bounded by TTL | Small stale window; needs proper invalidation |
| Centralized policy service | Follows source of truth and cache | Needs HA, timeouts, fail-closed, monitoring |

**DB revocation:** When a grant is deleted or `app_users.enabled=false`, per-request DB policy blocks subsequent requests. **IdP revocation:** When a group is removed at the IdP, the principal cached in the SP session may still carry the old group. Per-request DB checks **do not automatically refresh IdP attributes**; you need dedicated re-authentication, session invalidation, IdP logout/invalidation, or safe refresh policies.

For systems guarding monetary operations or sensitive data, enforce **fresh authentication/step-up** before the action, combining internal policy with the authentication assurance reported by the IdP.

## 10. Role mapping via response authentication converter

In Spring Security 6.x, you can customize how verified SAML assertions convert into Authentication/GrantedAuthority via the matching **OpenSamlXAuthenticationProvider** extension; in releases supporting OpenSAML 5, that is **OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter**.

Architectural extension flow:

~~~text
SAML Response from browser
   |
OpenSAML AuthenticationProvider checks trust + signature + conditions
   |
Response authentication converter on verified data
   |
Lookup (IdP issuer, subject) -> local account
   |
Map IdP groups via allowlist, read DB roles if needed
   |
Create Saml2Authentication with approved authorities
   |
SecurityContext / HttpSession
~~~

**You do not need a converter solely to check orderId.** The OrderPolicy example in Section 7 keeps the standard SAML provider and evaluates permissions at access time. When customizing a converter, preserve standard validations, handle DB errors fail-closed, and clarify how stale authorities are refreshed. **DaoAuthenticationProvider is not a role-loading tool for SAML2**; that provider is for username/password authentication.

If you want to render a button based on role without heavy querying, you can compute a **display entitlement** at login, while the backend still checks the real grant before returning or modifying resources. Hiding UI buttons is not authorization.

## 11. Object-level, tenant, and data-state permissions

Real systems often add:

- **Resource ownership:** Which user/team/unit owns the order?
- **Tenant scope:** Does the user belong to the order's tenant?
- **Workflow state:** Allow editing DRAFT only, never APPROVED/CLOSED.
- **Amount limits:** Approvers may approve only below a threshold.
- **Separation of duties:** The creator cannot approve the same transaction.
- **Grant expiration:** Project permissions end on a set date.
- **Explicit deny:** Suspended account or resource under legal hold.

Example:

~~~text
approveInvoice(user, invoice)
 = validSaml(user)
 AND userInApprovedIdpGroup
 AND localUserEnabled(user)
 AND invoice.tenantId == user.tenantId
 AND hasLocalPermission(user, invoice, APPROVE)
 AND invoice.status == PENDING
 AND invoice.amount <= user.approvalLimit
 AND invoice.createdBy != user.id
 AND noHold(invoice)
~~~

Conditions involving DB data must be evaluated inside the proper transaction, especially when **mutating state**. Do not check roles only on URLs; place policy close to business execution.

## 12. Error handling and fail-closed policy

- **Invalid SAMLResponse:** never build a trusted Authentication; never query DB grants to "salvage" failed authentication.
- **No local account:** deny or create a privilege-free pending record per onboarding policy.
- **Unknown IdP group:** never map high roles; deny if the group is mandatory.
- **Account disabled:** deny regardless of an active IdP session.
- **DB unreachable:** never fall back to allowing via last-known roles; return a safe error with monitoring without exposing SQL/PII.
- **Resource not found:** avoid leaking whether resources exist in other tenants; pick 404/403 consistently per policy.
- **Unstable IdP config:** never auto-switch trust to another issuer because a request carries plausible-looking data.
- **Transaction race:** grants or states can change between check and UPDATE; use conditional SQL/appropriate transactions.

**Never store the entire SAMLResponse or a detailed list of all permitted resources in cookies/clients.** Session cookies are only session identifiers; business grants remain verified by the authoritative data store.

## 13. Combined testing and exercises

### Negative test matrix

1. **Wrong issuer:** SAMLResponse signed by partner IdP yet account grant belongs to company → deny.
2. **Invalid signature/recipient/audience:** must not even reach local grant evaluation.
3. **Valid group but missing DB grant:** orderId denied.
4. **Valid DB grant but missing mandatory group:** denied.
5. **Local user disabled:** denied even though IdP authenticates.
6. **Subject changes or transient NameID:** never auto-join to a privileged account.
7. **Email matches another person:** never auto-merge account links.
8. **IdP group named ROLE_ADMIN not in mapping:** never grant admin.
9. **DB grant revoked mid-session:** next request denied via per-request lookup.
10. **IdP group revoked mid-session:** test refresh/session-invalidation policy; never assume automatic updates.
11. **DB outage:** zero requests granted access via fallback allow.
12. **Cross-tenant resource ID:** only matching tenant scope succeeds.
13. **Tampered orderId parameter:** enforce object-level checks on every request to prevent IDOR/BOLA.
14. **Calling business service from scheduler/message consumer:** policy is not bypassed by alternate entry points.
15. **Grant changes mid-write transaction:** conditions/locking prevent TOCTOU.
16. **Unknown/missing groups:** deny instead of falling back to overly broad default roles.
17. **Local role changes between two browser tabs/sessions:** policy reflects revocation within SLA.
18. **Audit:** log actor/action/resource/decision safely without logging SAMLResponse or cookies.

### Self-check questions

**Q1:** The IdP says the user belongs to finance-readers, yet the DB has no grant for order 99. Should viewing be allowed?  
**Answer:** No. The IdP group is only a functional prerequisite; without a local DB grant, deny by default.

**Q2:** The DB has a READ grant on order 42 for subject employee-847 under company, yet the sender is employee-847 from partner. Should viewing be allowed?  
**Answer:** No. Linking keys must evaluate the approved IdP/issuer or registration **alongside the subject**.

**Q3:** The DB revokes a permission while the SP session is still active. How do you ensure the next request is blocked?  
**Answer:** Check the DB on each request/action, or use a cache with explicit invalidation and defined staleness limits; never store permissions solely at login.

**Q4:** The IdP removes a group while the SP still holds a principal with the old group; does querying the DB per request detect the removed group?  
**Answer:** No. IdP attributes inside the principal can be stale; you need appropriate re-authentication or invalidation policies.

**Q5:** Can every SAML group be converted into `ROLE_*` via string concatenation?  
**Answer:** No. Map only approved groups/issuers via an allowlist, and verify resource permissions separately.

**Q6:** Is a single `@PreAuthorize` on a controller enough to protect business logic across all channels?  
**Answer:** Not if the service is also invoked through other paths. Policy should be enforced at the service layer/DB boundary.

## 14. Production checklist

- [ ] SAMLResponse is fully verified by the Spring SAML provider: signature, Issuer, AudienceRestriction, Recipient, timing, and correlation.
- [ ] Contracts exist for IdP group attributes, NameFormat, issuer, and stable subjects.
- [ ] Account linking binds **approved issuer/registration + subject**, never email by default.
- [ ] Local account enabled/disabled status, roles, and resource grants reside in an audited source of truth.
- [ ] IdP groups are mapped via allowlist; unknown/missing groups grant no privileges.
- [ ] **Deny by default, least privilege**, and AND across necessary conditions are enforced.
- [ ] Object-level permissions are evaluated by **action + resource + tenant**, not roles alone.
- [ ] **@EnableMethodSecurity** is enabled when using `@PreAuthorize`; business services are protected across all entry channels.
- [ ] JDBC queries use bind parameters, appropriate indexes/constraints, and timeouts; no SQL errors leaked.
- [ ] DB outages never fall back to allow.
- [ ] Policies handle revocation, group changes, and stale sessions across both IdP and DB.
- [ ] In multi-tenant setups, all link/grant/resource queries enforce tenant scope.
- [ ] Writes/approvals prevent TOCTOU via transactions or conditional updates.
- [ ] Tests cover missing groups, missing grants, wrong issuers, wrong subjects, disabled accounts, revocation, DB outages, cross-tenant access, and role injection.
- [ ] Audits capture enough context to trace grant provenance without logging SAMLResponses/cookies/sensitive PII.

**Conclusion:** In SAML2 federation, the IdP is the source of truth for **verified identity and organizational attributes**; the internal application is the source of truth for **business privileges on individual resources**. Spring Security provides Saml2AuthenticatedPrincipal and method security to combine both sources under a clear policy. A successfully logged-in user is only the **starting point** of authorization.

## 15. References

- [Spring Security 6.5 – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): SAML2 Authentication, Saml2AuthenticatedPrincipal, and attribute data.
- [Spring Security 6.5 – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): response converters, coordinating UserDetailsService, and custom authorities.
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@P` parameter annotations, and policy beans.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): GrantedAuthority and AuthorizationManager.
- [Spring Framework – JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcTemplate and bind parameters.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, check permissions on every request.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID, AttributeStatement, and assertion conditions.
