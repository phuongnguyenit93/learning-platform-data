# Preventing IdP Confusion, Tenant Confusion, and Cross-Tenant Data Access

## 1. Objective: Right User, Right Organization, Right Resource

A **Spring Security SAML2 Service Provider (SP)** application can accept logins from multiple **Identity Providers (IdPs)** and serve multiple tenants (companies, customers, organizations). **A validly signed `SAMLResponse` does not automatically allow a user to access every tenant's data.**

Three independent failure modes often appear together:

- **IdP confusion:** mapping an Assertion to the wrong `RelyingPartyRegistration`, confusing issuers, or verifying with another IdP's signing key.
- **Tenant confusion:** taking the tenant from a URL, header, email domain, or unauthoritative claim and treating it as permission to enter an organization.
- **Cross-tenant data access (BOLA/IDOR):** an authenticated user accesses records belonging to another organization because a service/repository/cache misses tenant scoping.

This lesson focuses on **Spring Security 6.x Servlet SAML 2.0 federation**, Java 17+, and a **Spring Boot 3.3.5** example. The goal is protecting **IdP trust → identity binding → tenant authorization → data-layer isolation**. Never write a custom XML Signature validator or disable SAML checks.

### Questions to Answer

1. How does the SP know which IdP a Response belongs to without blindly trusting a browser-sent issuer?
2. Once the IdP authenticates a user, how does the app verify the user holds membership in a **specific tenant**?
3. How do you avoid mix-ups when **one IdP serves multiple tenants** or multiple IdPs emit the same email/NameID?
4. How do you stop a tenant A user from altering a path, header, or document ID to read tenant B's data?
5. Must caches, search, exports, object storage, background jobs, and connection pools also obey the tenant boundary?
6. Which negative tests prove organizational isolation even after SAML login succeeds?

## 2. Identifiers That Must Be Kept Separate

| Identifier | Example | Meaning | Does It Prove Membership? |
| --- | --- | --- | --- |
| **`registrationId`** | `corp`, `partner` | Config key in `RelyingPartyRegistrationRepository`. | No. |
| **IdP `entityID` / `Issuer`** | `https://idp.corp.example.org/saml` | Logical identifier of the IdP issuing the Assertion. | No. |
| **SP `entityID`** | `https://sp.example.org/saml2/service-provider-metadata/corp` | SP identifier, typically appearing in `AudienceRestriction`. | No. |
| **ACS URL** | `https://sp.example.org/login/saml2/sso/corp` | Endpoint receiving `SAMLResponse`. | No; a URL is not a trust anchor. |
| **`NameID`** | `opaque-user-7` | Subject identifier inside the Assertion, with its own format and lifecycle. | No. |
| **stable subject** | `employeeId=EMP-041` | IdP-issued claim agreed upon for account linking. | Not automatically; must bind to the exact issuer and account. |
| **`tenantId`** | `corp`, `partner` | Namespace for permissions, data, and organization. | No; the client merely picks a target. |
| **resource ID** | `DOC-001` | Document/invoice identifier. | No; an unguessable ID does not replace authorization. |

**`registrationId` is neither IdP `entityID` nor `tenantId`.** A `registrationId` named `corp` might point to an IdP shared across multiple tenants, or two registrations might share an IdP issuer while differing in SP `entityID`/ACS. Never automatically equate issuer with tenant.

**NameID/email must never be the default global account key.** An IdP may use transient NameIDs, emails can change or be reassigned, and two IdPs may emit the same subject string. A safe account key typically requires **`(IdP issuer, stable subject)`** linked to an **internal account ID** via an admin-approved server-side table.

## 3. Threat Model: An Attacker with a Valid SAML Login

Suppose an attacker holds a valid account at **Partner IdP**; they log into the SP, receive an `HttpSession`, and call APIs:

~~~text
GET /orgs/partner/docs/DOC-001   -> legitimate Partner data
GET /orgs/corp/docs/DOC-001      -> swaps tenant in path
X-Tenant-ID: corp                -> spoofs header
GET /api/docs/DOC-CORP-SECRET    -> direct access using known ID
POST /api/docs {"tenantId":"corp", "title":"..."}
~~~

The attacker does not need Corp IdP's private signing key if the application fails at **tenant authorization** or **data access**.

Correct flow:

~~~text
SAMLResponse from browser
   |
   v
Spring Security/OpenSAML verifies:
   - matching registration, IdP issuer, public signing key
   - Response/Assertion signature
   - Audience, Destination, Recipient
   - Time, InResponseTo, subject confirmation, replay
   |
   v
Authenticated Saml2AuthenticatedPrincipal
   |
   v
Server-side identity binding:
   (verified IdP entityID, stable subject) -> localAccount
   |
   v
Tenant authorization:
   Is IdP allowed to represent this tenant?
   Does user have active tenant membership?
   Does user have permission for this operation on object?
   |
   v
Data boundary:
   query WHERE tenant_id = authorizedTenant
   cache/search/storage/job use verified tenant context
~~~

**Successful SAML authentication is a necessary condition, not a sufficient condition for data access.**

## 4. Preventing IdP Confusion During SAML Authentication

Example of two `RelyingPartyRegistration` entries:

~~~text
registrationId: corp
  IdP entityID: https://idp.corp.example.org/saml
  IdP verification certs: Corp IdP public signing keys
  SP entityID: https://sp.example.org/saml2/service-provider-metadata/corp
  ACS: https://sp.example.org/login/saml2/sso/corp

registrationId: partner
  IdP entityID: https://idp.partner.example.org/saml
  IdP verification certs: Partner IdP public signing keys
  SP entityID: https://sp.example.org/saml2/service-provider-metadata/partner
  ACS: https://sp.example.org/login/saml2/sso/partner
~~~

An attacker can POST a Partner `SAMLResponse` to **`/login/saml2/sso/corp`**. The string `corp` in the URL is only a routing hint; Spring Security must verify the Response using Corp's policy and verification keys, exact issuer, audience, and ACS. Partner's message must be **rejected** if it fails those constraints.

### 4.1. Saved AuthnRequest and Registration Selection

In **SP-initiated login**:

~~~text
GET /saml2/authenticate/corp
  -> Spring creates AuthnRequest ID=_r123
  -> HttpSession saves pending AuthnRequest and registration
  -> browser goes to Corp IdP
  -> browser POSTs SAMLResponse to ACS
  -> converter locates saved request / registrationId
  -> provider verifies Response.InResponseTo=_r123
  -> signature + Issuer + Audience + Recipient + Destination + time...
~~~

In Spring Security Servlet, **`HttpSessionSaml2AuthenticationRequestRepository`** is the standard default repository for pending AuthnRequests. Multi-node SP deployments need appropriate sticky sessions or a shared session store so callbacks locate the request; **never drop `InResponseTo`** when a session is lost.

### 4.2. Issuer Fallback Is Not Proof

When an ACS lacks `registrationId` or no saved AuthnRequest exists, Spring Security can look up a registration using **`Response.Issuer`**. However, **the Response's Issuer has not yet been signature-verified at lookup time**, so it is strictly a **hint to select a candidate trust configuration**.

If two registrations `corp-vn` and `corp-sg` share the **same IdP issuer** yet have different SP entityIDs/ACSs/tenants, issuer alone cannot resolve uniquely. You need pending request context, explicit ACS/`registrationId`, or a custom resolver with safe policy. **Never pick the first registration** and relax validation just to let login pass.

**IdP-initiated SSO** has no originating AuthnRequest, so it requires dedicated policy for unsolicited responses, login CSRF/replay defense, and resolving issuer/tenant ambiguity. If IdP-initiated SSO is unnecessary, restrict to SP-initiated flows only.

### 4.3. SAML Checks That Must Never Be Weakened

| Check | Failure Mode If Skipped |
| --- | --- |
| **Trusted IdP metadata and entityID** | Trusts certificates/SSO URLs of an unknown IdP. |
| **XML Signature on Response/Assertion** | Accepts self-signed or tampered payloads. |
| **Issuer matches registration** | Confuses Partner for Corp. |
| **`AudienceRestriction`** | Accepts Assertions issued for a different SP. |
| **`Response.Destination`** | Accepts Responses sent to the wrong endpoint. |
| **`SubjectConfirmationData.Recipient`** | Bearer Assertions meant for another ACS are accepted. |
| **`InResponseTo` when SP-initiated** | Login CSRF; binds Response to the wrong browser/request. |
| **`NotBefore`/`NotOnOrAfter`** | Accepts expired Assertions. |
| **Replay/one-time policy** | Reuses an already-consumed Response. |
| **SAML encryption, if used** | Fails to decrypt safely before consuming claims. |

Never trust `ds:KeyInfo` inside a message to self-authorize a new certificate. Verification keys must come from an **approved registration/metadata**, never from an unverified message.

## 5. Preventing Tenant Confusion with Server-Managed Policy

Design a registry:

| `registrationId` | Approved IdP Issuer | Tenants IdP May Represent | Stable Subject Claim |
| --- | --- | --- | --- |
| `corp` | `https://idp.corp.example.org/saml` | `corp` | `employeeId` |
| `partner` | `https://idp.partner.example.org/saml` | `partner` | `externalSubjectId` |
| `shared-broker` | `https://broker.example.org/saml` | `corp`, `partner` if approved | `immutableSubject` |

Even a **`shared-broker`** permitted to assert identities for two tenants does not make every broker user a member of both. You still need **active per-user tenant memberships** and per-tenant roles/actions.

### Suggested Internal Data Tables

~~~text
identity_binding:
  idp_entity_id
  stable_subject
  local_account_id
  status
  UNIQUE(idp_entity_id, stable_subject)

tenant_membership:
  local_account_id
  tenant_id
  status(active/revoked)
  scoped_permissions
  membership_version

tenant_resource:
  tenant_id
  resource_id
  owner_id
  payload
~~~

After SAML authentication, perform these steps in order:

1. Confirm the registration and real IdP issuer were verified by the **trusted SAML provider**.
2. Read the stable subject from **`Saml2AuthenticatedPrincipal.getAttributes()`** using the agreed `Attribute.Name`; enforce **exactly one non-blank value** of the expected type.
3. Look up `localAccount` by **`(IdP issuer, stable subject)`**, not by email alone.
4. Check that this IdP is permitted to represent **`requestedTenant`**.
5. Check that `localAccount` is active, holds active membership in that tenant, and has permission for the operation/resource.
6. Only then construct **`authorizedTenant`** for services, repositories, and caches.
7. If any step disagrees, **deny by default**; never fall back to a broad default tenant or role.

### Is a Signed Tenant Claim Enough?

An IdP may emit:

~~~xml
<saml:Attribute xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                Name="tenantId">
  <saml:AttributeValue>corp</saml:AttributeValue>
</saml:Attribute>
~~~

The signature only proves the claim came from that IdP. If Partner IdP lacks authority to assert `corp` membership, the value `corp` must be blocked by policy. If the IdP is authorized for multiple tenants, you must still verify **this specific subject holds membership in that tenant**.

Never infer the tenant by default from **email domain**, **`NameID`**, **`group=admin`**, or a client-sent **`X-Tenant-ID`** header. Those inputs may act as selectors/hints when policy specifies, never replacing the server's authorization decision.

## 6. Tenant Selector and Session: Never Let Two Tabs Mix Organizations

An application may expose:

~~~text
/orgs/corp/docs/DOC-001
/orgs/partner/docs/DOC-001
~~~

`tenantId` in the URL is **the target requested by the caller**, and membership must be verified on every request. Risks include:

- Storing a global **`currentTenant`** in `HttpSession`, letting tab B silently switch tab A from Corp to Partner.
- Logging into a different IdP in the same session while retaining old roles/tenant.
- Membership revoked while cached permissions/session remain active.
- Using `tenantId` from a header/path to set a database RLS session variable before verifying the user.
- Letting a Partner **`ADMIN`** user become platform `ADMIN` across the whole app.

Separate **tenant selection**, **tenant authorization**, and **data operations**. Switching tenants must recheck membership and scoped roles; the session can hold a UI preference, never replacing server-side permission checks. If the identity genuinely switches IdPs, refresh `SecurityContext` and apply appropriate session-fixation and cookie policies.

### Account Linking / JIT Provisioning

When a user logs in for the first time, the application may create an account (JIT), provided:

- Both IdP and tenant are already onboarded/allowlisted.
- Two accounts are never auto-merged simply because emails match.
- An `ADMIN` membership is never auto-created from an unknown SAML group.
- Invitation/approval workflows, lifecycle, deprovisioning, and auditing exist.
- Stable subjects may be reissued or changed by an IdP; maintain a migration policy.
- Cross-IdP account linking goes strictly through an authorized, audited workflow—never auto-linked by `displayName`.

## 7. Data Access: Preventing BOLA/IDOR at the Service Layer

**Anti-pattern:**

~~~sql
SELECT id, title, body
FROM documents
WHERE id = :documentId;
~~~

The query may be safe from SQL injection yet still leak another tenant's document. **An unguessable resource ID, even a UUID, does not replace authorization.**

**Right approach:**

~~~sql
SELECT id, title, body
FROM documents
WHERE tenant_id = :authorizedTenant
  AND id = :documentId;
~~~

**`authorizedTenant`** must originate from the authenticated principal and server-side membership/permissions—never pass an unverified path segment or header straight into queries.

Write operations must also be scoped:

~~~sql
UPDATE documents
SET title = :title
WHERE tenant_id = :authorizedTenant AND id = :documentId;

DELETE FROM documents
WHERE tenant_id = :authorizedTenant AND id = :documentId;
~~~

On `INSERT`, set `tenant_id` from the **verified tenant context**; never let clients arbitrarily supply another organization's `tenantId`. Moving a resource between tenants requires a separate privileged operation with auditing.

**A single controller check is not enough:** batch jobs, exports, search, GraphQL, background workers, and internal services also call repositories. Place the service/data-access boundary across every entry point. Database row-level security can be added as defense in depth.

### 403 or 404?

- User lacks permission for the requested tenant: typically **403 Forbidden**.
- User has tenant access, yet `documentId` does not exist in that tenant: **404 Not Found**, never revealing "this document actually belongs to another tenant."
- Depending on policy, you may return 404 to hide existence; keep response bodies, counts, logs, and timing consistent to reduce side channels.

## 8. Pure Java 17: Simulating Trust, Tenant, and Document Isolation

The **`TenantBoundaryDemo.java`** example runs without Spring, an IdP, or a DB. **`VerifiedLogin`** assumes SAML signature/issuer/audience validation already succeeded before creation. **Never construct `VerifiedLogin` from headers or unverified XML in production.**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;

public class TenantBoundaryDemo {
    record VerifiedLogin(String registration, String issuer, String subject) {}
    record Registration(String issuer, Set<String> tenants) {}
    record Identity(String issuer, String subject) {}
    record Document(String tenant, String id, String title) {}

    static final Map<String, Registration> REG = Map.of(
        "corp", new Registration("https://idp.corp.example.org/saml", Set.of("corp")),
        "partner", new Registration("https://idp.partner.example.org/saml", Set.of("partner"))
    );

    static final Map<Identity, Set<String>> MEMBERS = Map.of(
        new Identity("https://idp.corp.example.org/saml", "EMP-041"), Set.of("corp"),
        new Identity("https://idp.partner.example.org/saml", "P-007"), Set.of("partner")
    );

    static final List<Document> DOCUMENTS = List.of(
        new Document("corp", "DOC-001", "Corp report"),
        new Document("partner", "DOC-001", "Partner report"),
        new Document("partner", "DOC-002", "Partner confidential")
    );

    static String read(VerifiedLogin login, String tenant, String id) {
        Registration policy = REG.get(login.registration());
        if (policy == null || !policy.issuer().equals(login.issuer())) {
            throw new SecurityException("IDP_MISMATCH");
        }
        if (!policy.tenants().contains(tenant)) {
            throw new SecurityException("TENANT_DENIED");
        }
        Identity key = new Identity(login.issuer(), login.subject());
        if (!MEMBERS.getOrDefault(key, Set.of()).contains(tenant)) {
            throw new SecurityException("NO_MEMBERSHIP");
        }
        return DOCUMENTS.stream()
            .filter(d -> d.tenant().equals(tenant))
            .filter(d -> d.id().equals(id))
            .findFirst()
            .orElseThrow(() -> new SecurityException("DOCUMENT_NOT_FOUND"))
            .title();
    }

    static void show(String label, Supplier<String> operation) {
        try {
            System.out.println(label + ": " + operation.get());
        }
        catch (SecurityException ex) {
            System.out.println(label + ": DENY " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        VerifiedLogin corp = new VerifiedLogin(
            "corp", "https://idp.corp.example.org/saml", "EMP-041");
        VerifiedLogin partner = new VerifiedLogin(
            "partner", "https://idp.partner.example.org/saml", "P-007");
        VerifiedLogin wrong = new VerifiedLogin(
            "corp", "https://idp.partner.example.org/saml", "EMP-041");

        show("corp/corp", () -> read(corp, "corp", "DOC-001"));
        show("corp/partner", () -> read(corp, "partner", "DOC-001"));
        show("partner/partner", () -> read(partner, "partner", "DOC-001"));
        show("wrong issuer", () -> read(wrong, "corp", "DOC-001"));
        show("corp probes partner id", () -> read(corp, "corp", "DOC-002"));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac TenantBoundaryDemo.java
java TenantBoundaryDemo
~~~

**Exact stdout:**

~~~text
corp/corp: Corp report
corp/partner: DENY TENANT_DENIED
partner/partner: Partner report
wrong issuer: DENY IDP_MISMATCH
corp probes partner id: DENY DOCUMENT_NOT_FOUND
~~~

Points to note:

1. Corp and Partner both have **DOC-001**, yet lookups by **tenant+id** return each organization's own document.
2. A Corp user switching to `tenant=partner` is blocked even though authenticated.
3. Registration `corp` cannot be paired with Partner's issuer.
4. Corp knowing Partner's specific document ID cannot query it under tenant Corp.
5. Membership is server-side; a signed IdP assertion does not self-grant membership.
6. This is an authorization demo, **not a substitute for Spring Security/OpenSAML**, and does not process SAML Responses.

## 9. Spring Boot 3.3.5: Two-IdP SP and Tenant-Scoped API

This sample models two registrations (**corp/partner**) using **real IdP metadata**, with in-memory membership/document maps for learning purposes only. In real deployments, replace those maps with a protected identity/membership store and repository where every document belongs to a specific tenant.

### 9.1. Maven — `pom.xml`

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
    <artifactId>saml-tenant-isolation</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
        </repository>
    </repositories>
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
~~~

The Maven XML has a single `xmlns:xsi` and valid namespace/XSD pair in `xsi:schemaLocation`. Dependencies belong to Boot 3.3/Security 6.x on JDK 17; real sandbox IdPs are required to complete SSO.

### 9.2. `application.yml`

**`src/main/resources/application.yml`**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "${CORP_IDP_METADATA_URI}"
          partner:
            assertingparty:
              metadata-uri: "${PARTNER_IDP_METADATA_URI}"

server:
  port: 8080
~~~

Both `metadata-uri` values are **organization-approved** IdP URLs. Corp IdP is expected to have entityID **`https://idp.corp.example.org/saml`** and Partner IdP **`https://idp.partner.example.org/saml`**. If actual issuers differ, update the registry policy through onboarding rather than inferring issuers from hostnames or emails. Register SP entityID/ACS at both IdPs.

### 9.3. Main Class

**`src/main/java/com/example/samltenant/SamlTenantApplication.java`**

~~~java
package com.example.samltenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlTenantApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlTenantApplication.class, args);
    }
}
~~~

### 9.4. `SecurityFilterChain`

**`src/main/java/com/example/samltenant/SecurityConfig.java`**

~~~java
package com.example.samltenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**`anyRequest().authenticated()`** only enforces login; downstream APIs still require **tenant authorization**. If your design uses `@PreAuthorize` on services, enable **`@EnableMethodSecurity`**; Spring Security does not activate method security automatically just by adding the starter.

### 9.5. `TenantAccessService`

**`src/main/java/com/example/samltenant/TenantAccessService.java`**

~~~java
package com.example.samltenant;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class TenantAccessService {
    record Policy(String expectedIssuer, String subjectClaim,
                  Set<String> allowedTenants) {}
    record Identity(String issuer, String stableSubject) {}

    private final RelyingPartyRegistrationRepository registrations;

    // Organization-approved IdP -> tenant contract.
    private final Map<String, Policy> policies = Map.of(
        "corp", new Policy(
            "https://idp.corp.example.org/saml", "employeeId", Set.of("corp")),
        "partner", new Policy(
            "https://idp.partner.example.org/saml",
            "externalSubjectId", Set.of("partner"))
    );

    // Simulated membership table; production needs a DB with status/roles/expiry.
    private final Map<Identity, Set<String>> memberships = Map.of(
        new Identity("https://idp.corp.example.org/saml", "EMP-041"),
        Set.of("corp"),
        new Identity("https://idp.partner.example.org/saml", "P-007"),
        Set.of("partner")
    );

    public TenantAccessService(RelyingPartyRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String authorize(Authentication auth, String tenantId) {
        if (auth == null || !auth.isAuthenticated()
                || !(auth.getPrincipal() instanceof Saml2AuthenticatedPrincipal p)) {
            throw new AccessDeniedException("SAML login required");
        }

        String registrationId = p.getRelyingPartyRegistrationId();
        Policy policy = policies.get(registrationId);
        if (policy == null || !policy.allowedTenants().contains(tenantId)) {
            throw new AccessDeniedException("Tenant not allowed");
        }

        RelyingPartyRegistration registration =
                registrations.findByRegistrationId(registrationId);

        if (registration == null || !policy.expectedIssuer().equals(
                registration.getAssertingPartyDetails().getEntityId())) {
            throw new AccessDeniedException("Unapproved IdP");
        }

        List<Object> values = p.getAttributes().get(policy.subjectClaim());
        if (values == null || values.size() != 1
                || !(values.get(0) instanceof String stableSubject)
                || stableSubject.isBlank()) {
            throw new AccessDeniedException("Invalid stable subject");
        }

        Identity identity = new Identity(policy.expectedIssuer(), stableSubject);
        if (!memberships.getOrDefault(identity, Set.of()).contains(tenantId)) {
            throw new AccessDeniedException("No tenant membership");
        }

        return tenantId;
    }
}
~~~

**Security evaluation:**

- **`getRelyingPartyRegistrationId()`** on the principal was verified by the Spring SAML provider, not taken from a user-supplied query parameter.
- **`getAssertingPartyDetails().getEntityId()`** confirms the registration is configured with the server policy's exact IdP entityID; the OpenSAML provider itself still verifies `Response.Issuer` and the actual signature.
- The stable subject claim must be exactly one non-blank `String`. Never fall back to email/NameID when the claim is missing, and never take the first element if multi-valued.
- Tenant access is decided by **registration allowlist + internal membership**, not a signed claim alone.
- Production must also verify account active status, tenant status, role/action, and permission version; the demo does not imply every Corp IdP user gets corp access.
- When one IdP is permitted to represent multiple tenants, expand `Set allowedTenants` per contract while still checking **each user's individual membership**.

### 9.6. `DocumentService` with Tenant-Scoped Lookup

**`src/main/java/com/example/samltenant/DocumentService.java`**

~~~java
package com.example.samltenant;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    public record DocumentView(String id, String title) {}
    record Key(String tenantId, String documentId) {}

    private final TenantAccessService access;

    private final Map<Key, DocumentView> documents = Map.of(
        new Key("corp", "DOC-001"),
        new DocumentView("DOC-001", "Corp report"),
        new Key("partner", "DOC-001"),
        new DocumentView("DOC-001", "Partner report"),
        new Key("partner", "DOC-002"),
        new DocumentView("DOC-002", "Partner confidential")
    );

    public DocumentService(TenantAccessService access) {
        this.access = access;
    }

    public DocumentView read(Authentication auth,
                             String tenantId, String documentId) {
        String authorizedTenant = access.authorize(auth, tenantId);
        DocumentView document = documents.get(
                new Key(authorizedTenant, documentId));
        if (document == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
        }
        return document;
    }
}
~~~

Lookup uses **`tenantId+documentId`** rather than fetching the whole dataset and filtering afterward. When replacing the `Map` with a database, repositories must enforce **`WHERE tenant_id=:authorizedTenant AND document_id=:id`**, and list/search/export/write paths must pass through the same boundary.

### 9.7. `TenantController`

**`src/main/java/com/example/samltenant/TenantController.java`**

~~~java
package com.example.samltenant;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TenantController {
    private final DocumentService documents;

    public TenantController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/")
    public String home() {
        return "SAML tenant isolation ready";
    }

    @GetMapping("/orgs/{tenantId}/docs/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable String tenantId,
            @PathVariable String documentId,
            Authentication authentication) {
        return documents.read(authentication, tenantId, documentId);
    }
}
~~~

The controller accepts `tenantId` from the path **only to know which tenant the caller is requesting**. The service authorizes before looking up data. Other APIs must enforce the same boundary, not just one GET controller.

### 9.8. Running and Verifying

Configure real IdP metadata and SP entityID/ACS, have the IdPs release `employeeId`/`externalSubjectId`, and run:

~~~bash
mvn spring-boot:run
~~~

- **`GET http://localhost:8080/`** returns **`SAML tenant isolation ready`**.
- **`GET /saml2/authenticate/corp`** starts SSO with Corp; **`/saml2/authenticate/partner`** with Partner.
- **`GET /saml2/metadata/corp`** and **`/saml2/metadata/partner`** output per-registration `SPSSODescriptor`s.
- With a valid Corp login `employeeId=EMP-041`, **`GET /orgs/corp/docs/DOC-001`** returns JSON for **`Corp report`**.
- Corp login calling **`/orgs/partner/docs/DOC-001`** gets **403**.
- Partner login `externalSubjectId=P-007` calling **`/orgs/partner/docs/DOC-001`** sees **`Partner report`**.
- Corp calling **`/orgs/corp/docs/DOC-002`** gets **404** because that document exists only in Partner.
- Invalid SAML signatures/issuers/audiences are blocked **before** `DocumentService` executes; missing membership/stable subject is blocked in **`TenantAccessService`**.

**End-to-end SSO cannot be proven with a fake IdP.** You need real sandbox IdPs, trusted certificates, matching public HTTPS ACS URLs, and validly signed `SAMLResponse`s. The in-memory records are sample fixtures only and must not serve as a production authorization store.

## 10. PostgreSQL RLS as Defense in Depth

A shared database might use this schema:

~~~sql
CREATE TABLE documents (
    tenant_id VARCHAR(100) NOT NULL,
    document_id VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);
~~~

With PostgreSQL, you can add RLS:

~~~sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy ON documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
~~~

**Do not treat this as a complete migration:** check DB roles, grants, transaction boundaries, and connection pooling. Rules:

1. Set **`app.tenant_id`** solely from a server-verified tenant.
2. Use **`SET LOCAL`** inside a transaction rather than session-level `SET`, which can leak tenants across pooled connections.
3. The app DB role must not be superuser/`BYPASSRLS`; table owners bypass RLS unless `FORCE ROW LEVEL SECURITY` is enabled—test in practice.
4. Test select/insert/update/delete/list/count across all tenant-owned tables.
5. DB RLS does not cover Redis, object storage, search, or queues.
6. Cross-tenant jobs need a dedicated service principal/scope rather than normal user roles.

Even without RLS, ensure every query is tenant-scoped behind a centralized authorization boundary. Choose database-per-tenant, schema-per-tenant, or shared-table per SLA, compliance, and operations; every option still requires tenant-level authorization.

## 11. Caches, Files, Search, and Background Processing

### Cache

**Wrong:** cache key **`document:DOC-001`** can return Corp's report to Partner when IDs collide.

**Right approach:**

~~~text
tenant:corp:document:DOC-001
tenant:partner:document:DOC-001
~~~

If results also depend on user/permissions, cache keys or policy caches must incorporate those dimensions. **Check authorization before reading sensitive cached entries.** Membership revocation needs proper invalidation/TTL.

### Object Storage

~~~text
tenants/corp/docs/DOC-001.pdf
tenants/partner/docs/DOC-001.pdf
~~~

A tenant prefix does not replace permissions. Before issuing a signed download URL or reading/writing a file, verify the user holds permission for **the exact object and operation**. Guard against path/key tampering, cap TTLs, and restrict HTTP methods and bucket/IAM policies. Tenant admins must never run with broad platform storage credentials.

### Search / Analytics

Search indexes, vector DBs, reports, and warehouses must **filter by tenant inside the query itself**. Never fetch all results and filter in the UI, because snippets, rankings, facets, total counts, or cached searches can leak data before filtering.

### Background Jobs and Queues

Jobs must carry a **producer-verified tenant scope** or reference an authorized job record. Consumers verify provenance, re-authorize if memberships/roles changed, and scope queries and outputs. Deduplication, retries, dead-letter queues, and file exports must all be tenant-aware. Never trust a `tenantId` field stuffed into a message by an untrusted caller.

### Admin / Support / Audit

Tenant admins hold permissions solely inside their approved tenant; platform admin is a separate audited role. Log verified tenant, internal actor ID, action, and denial reason; never log raw `SAMLResponse`, cookies, signing keys, or sensitive `NameID`/emails.

## 12. Positive and Negative Test Matrix

**Important:** to test tenant isolation, use **real, valid, signed `SAMLResponse`s from a sandbox IdP**, then attempt to change the URL/tenant/resource. If you edit signed XML afterward, signature checks fail early and the test never exercises application authorization.

| # | Scenario | Expected Outcome |
| --- | --- | --- |
| 1 | Valid Corp login reads Corp document | 200 if account/membership/ACL pass. |
| 2 | Valid Partner login reads Partner document | 200 per policy. |
| 3 | Validly signed Partner Response POSTed to Corp ACS | Rejected on registration/issuer/trust mismatch. |
| 4 | Self-signed Assertion with attacker cert in `ds:KeyInfo` | Rejected due to unknown verification key. |
| 5 | `AudienceRestriction` targets another SP | Rejected. |
| 6 | `Destination`/`Recipient` differs from ACS | Rejected. |
| 7 | Wrong or missing `InResponseTo` in SP-initiated flow | Rejected on correlation check. |
| 8 | Replayed already-used Response | Rejected per replay/one-time policy. |
| 9 | Shared IdP issuer maps to two registrations without request context | Never picks arbitrarily; fails closed. |
| 10 | Unsolicited response from unregistered IdP | Rejected. |
| 11 | Partner login succeeds, changes `/orgs/partner` to `/orgs/corp` | 403; no data leaked. |
| 12 | Partner adds `X-Tenant-ID: corp` | Does not change tenant authorization. |
| 13 | POST JSON carrying another organization's `tenantId` | Rejected or server assigns verified tenant per contract. |
| 14 | Corp knows document ID existing only in Partner | 404 in Corp scope. |
| 15 | Corp and Partner both have `DOC-001` | Each receives its own tenant's content. |
| 16 | IdP emits signed `tenantId=corp`, yet registry forbids it | Denied; never trusts out-of-contract tenant claims. |
| 17 | Stable subject claim missing, multi-valued, or wrong type | Does not fall back to link account. |
| 18 | Two IdPs emit the same email/`NameID` | Never merges accounts automatically. |
| 19 | User holds valid SAML login yet membership was revoked | Denied per current membership/revalidation. |
| 20 | Partner tenant-admin calls platform API or Corp admin endpoint | 403; roles are scoped. |
| 21 | List API is scoped yet `totalCount` query is global | Test catches leakage. |
| 22 | Cache uses `documentId` without tenant prefix | Test catches cross-tenant collision. |
| 23 | Signed URL targeting another tenant's file | URL not issued and download blocked. |
| 24 | Search index returns facets/snippets from another tenant | Test fails; needs tenant filter at search engine. |
| 25 | Export job carries forged `tenantId` | Consumer rejects without verified authorization. |
| 26 | Two browser tabs rapidly switch tenants | Each request re-authorizes; no stale `currentTenant`. |
| 27 | Re-login with a different IdP in the same browser | Old roles/tenant identity not retained. |
| 28 | DB connection reused after another tenant's request | RLS/`SET LOCAL` does not leak. |
| 29 | Internal service accesses document bypassing controller | Still passes through tenant-aware authorization boundary. |
| 30 | Multi-tenant platform admin permitted | Separate privilege, least privilege, and explicit audit. |

**A negative test passes** when the system denies unauthorized operations without weakening SAML validation or granting default permissions.

## 13. Common Bugs

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| **`RelyingPartyRegistration` not found** | `registrationId` or ACS path missing from repository. | Verify onboarding, routes, metadata; never auto-add unknown IdPs. |
| **Issuer mismatch** | Response came from an IdP other than the registration's. | Verify issuer/keys; never weaken policy. |
| **Invalid signature** | Stale metadata/key rotation or tampered Response. | Update trust via proper process; never skip verification. |
| **SAML login works yet tenant API returns 403** | Local membership/claim/tenant policy not met. | Distinguish SAML auth success from business authorization. |
| **Users from two IdPs merged into one local account** | Key binding used email/`NameID` only. | Namespace by IdP + stable subject. |
| **Changing `tenantId` in URL still reads documents** | Service only checks `authenticated`. | Enforce membership and `WHERE tenant_id` queries. |
| **Export/Search leaks cross-tenant results** | Data path bypasses common enforcement. | Fix service/DB/search scoping. |
| **Cache mixes Corp and Partner `DOC-001`** | Key lacks tenant or authorization check. | Namespace keys and authorize before read. |
| **RLS leaks tenant after connection reuse** | Session-level `SET` was not reset. | Use `SET LOCAL` in transactions and test pooled connections. |
| **IdP-initiated lands in wrong tenant** | Shared issuer lacks disambiguating context. | Explicit policy, extra routing, or deny unsolicited. |
| **Tenant admin becomes platform admin** | Unscoped role mapping. | Separate tenant roles from platform roles and audit. |

## 14. Production Checklist

**Federation:**

- [ ] Accept only approved IdP `entityID`s and metadata/certificates.
- [ ] Every Response/Assertion checks signature, issuer, audience, destination, recipient, timestamps, `InResponseTo`, and replay.
- [ ] Ambiguous issuer lookups never pick arbitrarily; IdP-initiated SSO has an explicit policy.
- [ ] Public HTTPS SP `entityID`/ACS matches each registration.
- [ ] Stable subject claim has explicit name, type, cardinality, and lifecycle.

**Authorization and data isolation:**

- [ ] Server manages the allowlist of registration/IdP → tenants.
- [ ] Account linking uses issuer + stable subject, active membership, and scoped roles.
- [ ] Tenant path/header/body is a selector only, never self-granting permissions.
- [ ] Services/repositories enforce `authorizedTenant` across `SELECT`/`INSERT`/`UPDATE`/`DELETE`/list/search/export.
- [ ] DB RLS or other defense-in-depth controls are evaluated.
- [ ] Caches, blobs, queues, search, support tools, and audits are tenant-scoped.
- [ ] Tenant admins never inherit automatic platform roles.
- [ ] Membership/session/permission caches have bounded TTLs and revocation policies.

**Testing and operations:**

- [ ] Test two IdPs, two tenants, and colliding document IDs.
- [ ] Test switching tenants after valid SAML login, not just invalidly signed XML.
- [ ] Test account collisions, multi-tab usage, session switching, node failover, Redis/caches, and IdP key rotation.
- [ ] Maintain procedures for tenant onboarding/offboarding, revocation, migration, and access reviews.
- [ ] Monitor cross-tenant denials without exposing raw Assertions, PII, or secrets.

## 15. Self-Check

**1. If Partner validly signs a `SAMLResponse`, why can't that user read Corp documents?**  
Because the signature proves Partner IdP as the source; it does not prove that IdP may grant Corp membership, that the user holds Corp permissions, or that the document belongs to an allowed tenant.

**2. Is `registrationId=corp` in the ACS URL enough to prove the Response came from Corp IdP?**  
No. The URL is routing only; the provider must still verify issuer, keys, audience, and profile rules.

**3. Two registrations share an IdP Issuer with no pending AuthnRequest. Can you pick the first registration?**  
No. Require controlled routing context or fail closed.

**4. Two IdPs emit identical `employeeId` values. Can `employeeId` act as a global account key?**  
No; namespace by issuer + stable subject with an explicit linking policy.

**5. If the UI already filters by tenant, is an unscoped `repository.findById` safe?**  
No. Every read/write path must enforce tenancy at the service/data layer.

**6. With RLS and a connection pool, why is `SET LOCAL` needed?**  
So tenant context never outlives the transaction or leaks into another request on a reused connection.

**7. Why is a tenant-prefixed cache key alone not enough protection?**  
You must verify permissions before reading cached data; results can also depend on user permissions and current session membership.

**8. A stable subject is missing despite valid IdP login. Should you create a shared guest account?**  
No if a stable subject is required for account linking; fail closed and fix IdP attribute release.

## 16. References

1. [Spring Security 6.5 — SAML Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, ACS, Responses, and issuer resolution.
2. [Spring Security 6.3 Javadoc — `Saml2AuthenticatedPrincipal`](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): `getRelyingPartyRegistrationId` and attribute APIs.
3. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): principal mapping and response validation.
4. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize` for service-level enforcement.
5. [Spring Boot 3.3 — Security/SAML](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): multiple relying party registrations.
6. [OWASP — Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): tenant identity, membership, data isolation, cache/search/storage/queues.
7. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and per-request authorization.
8. [OWASP — Insecure Direct Object Reference](https://community.owasp.org/attacks/insecure_direct_object_reference): server-side resource ownership checks.
9. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Issuer, `AudienceRestriction`, Conditions, and signatures.
10. [OASIS — SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO and request correlation.

**Conclusion:** To prevent IdP confusion, tenant confusion, and cross-tenant data leakage, **verify SAML with the exact IdP trust configuration**, **bind identities and verify memberships/roles per tenant**, and **scope every resource to the verified tenant at the service/data layer**. A valid `SAMLResponse` never replaces authorization.
