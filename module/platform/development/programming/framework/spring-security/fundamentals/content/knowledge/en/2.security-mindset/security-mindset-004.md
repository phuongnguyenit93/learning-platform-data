# Principle of Least Privilege and Deny by Default

> **Context:** Spring Security on Servlet/Spring MVC, Java 17+, and Spring Boot 3.x. This lesson answers two design questions: **which permissions does each identity truly need?** and **what must the application do with a request that lacks an explicit allow rule?**

## 1. Two Complementary Principles

**Principle of Least Privilege (PoLP):** every user, service account, process, and component receives only the permissions **necessary to perform its assigned task**, within the required data scope and duration. Granting extra privileges requires a concrete reason and control.

**Deny by Default / Default Deny:** an action is executed only when **an explicit allow rule applies**. If no matching rule exists, information to decide is missing, or conditions are unproven, the system **does not grant access**. This is an expression of **fail-closed** thinking.

The two principles are related but not identical:

| Scenario | What Least Privilege Asks | What Deny by Default Asks |
| --- | --- | --- |
| Customer support rep views orders | Do they need to view all orders across every tenant? | If there is no rule for a new order type, is the request blocked? |
| Invoice generation service calls API | Does the token need permission to delete users? | Is a new API without a declared policy open to every token? |
| Administrator accesses documents | Does admin permission truly include reading private documents? | Is the ADMIN role exempt from all checks, or only allowed via deliberate rules? |
| Adding an endpoint for a new feature | Which roles and actions should the endpoint serve? | If authorization is forgotten, is the endpoint denied? |

**Failing to authenticate an identity** and **being authenticated yet lacking permission** both disqualify access, though they may produce different HTTP responses. The following sections explain why.

## 2. Define Permissions by Action and Resource

A complete access decision typically requires:

- **Subject:** who is acting? E.g., **alice**, a service account, or an OAuth2 client.
- **Action:** what do they want to do? E.g., **READ**, **CREATE**, **UPDATE**, **DELETE**, **APPROVE**.
- **Resource:** on which object? E.g., **document:doc-2**, **order:42**.
- **Context:** tenant, owner, order status, time, environment, authentication strength, or relevant attributes.

Conceptualized as:

~~~text
ALLOW if and only if:
  subject meets authentication requirements
  AND has permission to perform action
  AND policy for the specific resource is satisfied
  AND all required context conditions are satisfied

Otherwise: do not grant permission.
~~~

For example, **alice** has the **document:read** permission. That permission only states alice can perform *the document-reading action type*; it does not prove alice can read **doc-2** belonging to **bob**. If the API only checks a broad role and takes an ID from the URL, users can swap IDs to access others' documents. This is **Broken Object Level Authorization (BOLA/IDOR)**.

A simple least-privilege matrix:

| Identity | GET /api/ping | GET /api/docs/doc-1 (alice's) | GET /api/docs/doc-2 (bob's) | GET /api/admin/audit |
| --- | --- | --- | --- | --- |
| Anonymous | Allow | No | No | No |
| alice, document:read | Allow | Allow | No | No |
| bob, document:read | Allow | No | Allow | No |
| admin, ROLE_ADMIN | Allow | No, unless granted document-read permission | No | Allow |

**ADMIN does not implicitly mean "everything."** If business needs require an administrator to view documents for support cases, design a **dedicated support permission**, proper scoping, and auditing; do not infer sensitive data access from the role name alone.

### 2.1. Role, Authority, and Object-Level Conditions

- **Role (RBAC):** a group of permissions tied to a function, such as **READER**, **EDITOR**, **AUDITOR**. In Spring Security, **hasRole("ADMIN")** looks by default for **ROLE_ADMIN**.
- **Authority:** a permission string Spring Security checks directly via **hasAuthority("document:read")**. Authority strings can be **ROLE_ADMIN**, **document:read**, **SCOPE_documents.read**; prefixes have meaning depending on configuration.
- **Object-level conditions (ABAC/ownership):** checking **resource.ownerId == principal.id**, **resource.tenantId == principal.tenantId**, business status, or other attribute rules.
- **Time and scope:** a permission is valid only within a specific project, tenant, time window, or session if required by business rules.

RBAC helps manage many users; object-level checks prevent an overly broad role from leaking data. Real applications usually need to combine both.

## 3. Default Deny Must Hold Across Multiple Layers

Default deny must be enforced where **access is actually controlled**, not just via a single config line or hiding a UI button.

~~~text
                 HTTP request
                      |
        Which SecurityFilterChain protects it?
                      |
            HTTP-level authorization
        specific allowlist + trailing denyAll
                      |
              Controller / Service
                      |
          Method-level / domain policy
         role + action + resource + tenant
                      |
                 Data query
             verify exact scope
                      |
              Execute / return result
~~~

Each layer addresses a different risk:

1. **Filter chain:** the request must enter an appropriate **SecurityFilterChain**.
2. **HTTP policy:** only authorized URL + HTTP method combinations pass through.
3. **Method/domain policy:** a business operation must be checked even when invoked outside the controller.
4. **Data scope:** queries and updates operate only on resources within allowed scope.
5. **Accounts/infrastructure:** database connections, service credentials, and cloud roles also require least privilege.

**A request permitted past the URL does not mean every underlying resource may be read or modified.**

### 3.1. Default Deny in Spring Security HTTP Authorization

With a typical Servlet configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/docs/*")
            .hasAuthority("document:read")
        .requestMatchers(HttpMethod.GET, "/api/admin/audit")
            .hasRole("ADMIN")
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

This is an **excerpt inside a @Configuration class**; it requires full imports and beans as shown in the runnable example below.

- **Specific** rules come first.
- **anyRequest().denyAll()** blocks requests without a declared allow rule, including new endpoints accidentally added to a controller by a developer.
- **hasAuthority("document:read")** requires this exact authority; it does not yet check document ownership.
- **permitAll()** only waives the authorization requirement for the allowed path. The request still passes through **SecurityFilterChain** and other active protections.

**Spring Security evaluates request rules in order and uses the first match.** Placing a broad **anyRequest().permitAll()** or **requestMatchers("/api/**").permitAll()** before restrictive rules can allow more than intended; for protected APIs, design a deliberate allowlist.

### 3.2. Do Not Confuse Chain Scope with Policies Inside a Chain

There are two distinct concepts:

- **securityMatcher(...)**: decides whether a request belongs to this **SecurityFilterChain**.
- **requestMatchers(...)** inside **authorizeHttpRequests(...)**: decides access permissions for requests **that have entered that chain**.

When configuring multiple chains, **FilterChainProxy** picks the first matching chain in order. If you only create a **securityMatcher("/api/**")** chain without a catch-all chain for the rest, URLs outside **/api/** may be **unprotected by Spring Security**. An **anyRequest().denyAll()** in the API chain only blocks requests **that matched the API chain**, without protecting anything outside its scope.

When multiple chains are needed, design **a final chain without a restricting securityMatcher and with anyRequest().denyAll()** (or other explicit rules), check **@Order** precedence, and test unexpected URLs as well.

### 3.3. Business Methods Are Not Denied by Default Automatically

**@EnableMethodSecurity** enables **@PreAuthorize**, **@PostAuthorize**, etc., yet **does not automatically imply that all unannotated methods are denied**. To give the method/domain layer default-deny behavior, enforce **explicit access-boundary conventions**: sensitive business entry points must declare policies or be reachable only through a policy-enforcing service layer; test internal/batch/message call paths that bypass HTTP filters.

Avoid thinking that checking security only in controllers is safe: a service can be invoked by a scheduled job, a messaging listener, or a new controller.

## 4. Complete Example: Policy by URL, Permission, and Ownership

The example below uses three demo accounts:

- **alice** and **bob** have the **document:read** authority, each owning only one document.
- **admin** has **ROLE_ADMIN** to read audits, without implicitly receiving **document:read**.
- Only **GET /api/ping** is public; every unlisted URL/method is denied.

This demo runs on **Spring MVC + Spring Security + HTTP Basic**. All endpoints are **GET** to focus on authorization; when adding POST/PUT/DELETE, you must also design per-operation policies and CSRF according to client type.

### 4.1. Dependencies

Create a Spring Boot 3.x application with **Java 17+**, **Spring Web**, **Spring Security**, and **Spring Security Test**, then add to your existing **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The project requires the Spring Boot and Java plugins, Maven Central repository, and configured version/dependency management. The example below uses package **com.example.leastprivilege**; create files with exact names in **src/main/java/com/example/leastprivilege/**.

### 4.2. Entry Point: LeastPrivilegeApplication.java

~~~java
package com.example.leastprivilege;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LeastPrivilegeApplication {
    public static void main(String[] args) {
        SpringApplication.run(LeastPrivilegeApplication.class, args);
    }
}
~~~

### 4.3. SecurityConfig.java — allowlist + denyAll

~~~java
package com.example.leastprivilege;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/docs/*")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .authorities("document:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob123"))
            .authorities("document:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}
~~~

**Security meaning:**

1. No **securityMatcher(...)** is declared for this chain, so by default it matches every request.
2. **GET /api/ping** is an intentional public exception.
3. **GET /api/docs/* ** requires the document-reading capability at the HTTP layer.
4. **GET /api/admin/audit** requires **ROLE_ADMIN**.
5. **anyRequest().denyAll()** creates a final catch-all block. For example, adding controller **GET /api/new-feature** while forgetting to add an authorization rule results in the request being denied.
6. **@EnableMethodSecurity** enables additional checks inside services.

Hardcoded passwords are only for **localhost/demo**. HTTP Basic sends Base64-encoded username/password so **HTTPS** must be used on real networks; production environments should use an identity provider, secrets, and proper credential lifecycles. Do not assume this HTTP Basic model is equivalent to bearer tokens or session mechanisms of other applications.

### 4.4. DocumentPolicy.java — Grant Access Only to Owned Documents

~~~java
package com.example.leastprivilege;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    // Simulated data; production must query by tenant and real permissions.
    private static final Map<String, String> OWNER_BY_ID = Map.of(
        "doc-1", "alice",
        "doc-2", "bob"
    );

    public boolean ownedBy(Authentication authentication, String documentId) {
        if (authentication == null || documentId == null) {
            return false;
        }

        String owner = OWNER_BY_ID.get(documentId);
        return owner != null && owner.equals(authentication.getName());
    }
}
~~~

**Key point:** **Map.get(...)** returns null when the document does not exist; **owner != null && ...** returns **false**. Missing information to prove access results in **no access granted**. Never use dangerous conditions like "if owner == null then allow" or default tenant "all."

Production implementations must verify a **stable user ID**, tenant, and permissions against real data; never treat username as an immutable ID, and never trust client-supplied tenant or owner parameters.

### 4.5. DocumentService.java — Protecting the Business Entry Point

~~~java
package com.example.leastprivilege;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.ownedBy(authentication, #p0)"
    )
    public String readDocument(String id) {
        return "document:" + id;
    }
}
~~~

The **@PreAuthorize** expression must satisfy **both** conditions:

- **document:read**: holds permission for the action type;
- **documentPolicy.ownedBy(...)**: holds rights to the exact document passed into the method.

**#p0** references the first method parameter, avoiding reliance on compiler parameter-name retention. The policy is a Spring-managed bean, and the method is called through a Spring proxy so the annotation takes effect. If another method in the same bean calls this method directly via **this**, the Spring AOP proxy may not intercept that internal call; design enforcement points carefully and test real call paths.

This service layer also protects calls if another controller invokes **readDocument(...)**, because permissions are enforced at the Spring-managed business entry point rather than relying solely on old URL rules.

### 4.6. DemoController.java — Exposing Endpoints

~~~java
package com.example.leastprivilege;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final DocumentService documents;

    public DemoController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/docs/{id}")
    public String readDocument(@PathVariable String id) {
        return documents.readDocument(id);
    }

    @GetMapping("/api/admin/audit")
    public String audit() {
        return "audit";
    }

    // Controller exists but has no allow rule in SecurityConfig.
    @GetMapping("/api/forgotten")
    public String forgotten() {
        return "sensitive";
    }
}
~~~

The **/api/forgotten** endpoint is an intentional case to test **default deny**: the controller exists, yet the fallback rule blocks it before the method executes.

### 4.7. Running and Predicting Results

If the project already has the Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

If there is no wrapper yet, run **gradle bootRun** with a Gradle version compatible with the project's Spring Boot version, or generate the wrapper per Spring Boot documentation.

From another terminal, try:

~~~bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/api/docs/doc-1
curl -i -u alice:alice123 http://localhost:8080/api/docs/doc-1
curl -i -u alice:alice123 http://localhost:8080/api/docs/doc-2
curl -i -u bob:bob123 http://localhost:8080/api/docs/doc-2
curl -i -u admin:admin123 http://localhost:8080/api/admin/audit
curl -i -u admin:admin123 http://localhost:8080/api/docs/doc-1
curl -i -u admin:admin123 http://localhost:8080/api/forgotten
curl -i -u alice:wrong http://localhost:8080/api/docs/doc-1
~~~

These are the **expectations** for this exact demo app, without reverse proxies or custom exception handlers:

| Request | HTTP | Body Content on Success | Reason |
| --- | --- | --- | --- |
| Anonymous → /api/ping | **200** | **pong** | Only this endpoint is public. |
| Anonymous → /api/docs/doc-1 | **401** | — | Missing identity when endpoint requires authorization. HTTP Basic challenges. |
| alice → /api/docs/doc-1 | **200** | **document:doc-1** | Has document:read and is the owner. |
| alice → /api/docs/doc-2 | **403** | — | Has action-type permission but does not own doc-2. |
| bob → /api/docs/doc-2 | **200** | **document:doc-2** | Correct permission and correct owner. |
| admin → /api/admin/audit | **200** | **audit** | Has ROLE_ADMIN. |
| admin → /api/docs/doc-1 | **403** | — | ROLE_ADMIN does not implicitly include document:read. |
| admin → /api/forgotten | **403** | — | Trailing anyRequest().denyAll() blocks undeclared endpoint. |
| alice with wrong password → /api/docs/doc-1 | **401** | — | HTTP Basic authentication failed. |

**Do not assume 401/403 are fixed across all configurations.** With form login, unauthenticated requests may be redirected **302**; how security exceptions map to status codes depends on **AuthenticationEntryPoint** and **AccessDeniedHandler**. In this example, authenticated requests that are denied receive **403**. An error produced by the application itself or a reverse proxy may also return a different status.

## 5. Testing Policy: Include Negative Cases

Testing only what is **allowed** misses many critical authorization bugs. Valuable tests must prove that **missing permission**, **wrong resource**, and **undeclared endpoints** are all blocked.

Add **src/test/java/com/example/leastprivilege/AuthorizationPolicyTest.java**:

~~~java
package com.example.leastprivilege;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationPolicyTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingIsExplicitlyAllowed() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousRequestCannotReadDocuments() throws Exception {
        mvc.perform(get("/api/docs/doc-1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/docs/doc-1")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:doc-1"));
    }

    @Test
    void readerCannotReadAnotherUsersDocument() throws Exception {
        mvc.perform(get("/api/docs/doc-2")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanViewAuditButCannotReadUnrelatedDocuments() throws Exception {
        mvc.perform(get("/api/admin/audit")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit"));

        mvc.perform(get("/api/docs/doc-1")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void newRouteWithoutAllowRuleIsDenied() throws Exception {
        mvc.perform(get("/api/forgotten")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownDocumentIdDoesNotGrantAccess() throws Exception {
        mvc.perform(get("/api/docs/doc-404")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**How to read the test results:**

- **newRouteWithoutAllowRuleIsDenied** proves that an existing controller does not automatically open access.
- **readerCannotReadAnotherUsersDocument** proves that the action-type permission **document:read** is insufficient to read every document.
- **adminCanViewAuditButCannotReadUnrelatedDocuments** prevents accidentally treating **ADMIN** as a superuser for every resource.
- **unknownDocumentIdDoesNotGrantAccess** proves the policy returns **false** when ownership info is missing.

The example returns **403** for unauthorized or nonexistent IDs per the demo policy. In production systems, **404** can be used to reduce resource-existence probing, provided policy is consistent and nothing leaks through error payloads, timing, or another endpoint.

## 6. When Adding a New Feature, In What Order Should Permissions Be Evaluated?

Suppose the team adds **POST /api/docs/{id}/approve**. Before enabling the endpoint:

1. **Identify the business action**: **document:approve**, do not reuse **document:read** merely because the URL is similar.
2. **Identify allowed identities**: users holding approval permission in the tenant, possibly required to differ from the creator.
3. **Identify resource conditions**: which tenant the document belongs to, whether its state allows approval, and whether the approver has a conflict of interest.
4. **Add an explicit HTTP rule** for the exact **POST + path** and protect the handling method/service.
5. **Verify data at execution time**: avoid checking permission early and using mutated data later (**TOCTOU**); sensitive actions should validate and update consistently inside a transaction with concurrency control when needed.
6. **Test positive and negative cases**: anonymous, expired token, account lacking permission, right permission in wrong tenant, already-approved document, other undeclared endpoints.
7. **Evaluate CSRF** if using browser/cookie/session; CSRF policy differs by client and credential transport. Never disable CSRF just to make a POST test pass.

An illustrative service-layer policy (not a complete Java class) might look like:

~~~java
@PreAuthorize(
    "hasAuthority('document:approve') and " +
    "@approvalPolicy.canApprove(authentication, #p0)"
)
public void approveDocument(String documentId) {
    // Execute within a transaction and check state consistently.
}
~~~

**Distinction:** the annotation is the authorization gate; transactions, state handling, and data checks still need to be implemented in the service/repository. This rule alone does not guarantee consistency under concurrent requests.

## 7. Situations Where Principles Frequently Break Down

### 7.1. "Anyone Logged In Is Allowed"

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
)
~~~

This configuration only requires **having an identity**, making no distinction among read, edit, approve, or tenant scope. For an API holding multi-user data, **authenticated()** is usually necessary but **insufficient**. Redesign per action and enforce resource checks.

### 7.2. "One Role Covers Every Permission"

~~~java
.requestMatchers("/api/**").hasRole("ADMIN")
~~~

This rule can make sense for genuinely administrative APIs, yet does not mean every business function belongs to ADMIN. It easily creates overly broad privileges or forces ops teams to share ADMIN accounts. Split by capability such as **invoice:approve**, **user:disable**, **audit:read** and grant only what is needed.

### 7.3. "Taking tenantId from a Query Parameter Is Enough"

A client calls **GET /api/orders?tenantId=other-company**. If the service uses the request's tenantId to scope the query without **checking that it belongs to the tenants the principal is permitted to access**, simply changing the parameter can leak data. Tenant must be verified via identity/policy and bound in the query; also check per-resource permissions when required.

### 7.4. "If There Is No Owner, Anyone Can Read"

Dangerous example:

~~~java
// Wrong: missing ownership data opens up access.
return owner == null || owner.equals(username);
~~~

Safer approach for the lesson:

~~~java
// Missing ownership data: insufficient evidence to grant access.
return owner != null && owner.equals(username);
~~~

On database or identity-service errors, the system must also **not allow by default** merely because the policy failed to return a result. The response may be **5xx** if a dependency breaks; the principle is **never execute the action without verifying sufficient permission**, not forcing every infrastructure error into a 403.

### 7.5. "Hiding the Edit Button in the Frontend Is Authorization"

The frontend is only user experience. Attackers or ordinary users can craft HTTP requests directly. The backend must control every endpoint and every data manipulation flow.

### 7.6. "This Endpoint Is Internal-Only, So It Needs No Protection"

Internal endpoints can still be exposed through ingress misconfigurations, service meshes, SSRF, or network errors. Use service identity, appropriate authentication, scoped permissions, and network controls instead of implicitly trusting all internal traffic.

### 7.7. "Method Security Is Enabled, So Every Method Is Safe"

**@EnableMethodSecurity** activates supported annotations when calls pass through a proxy. Unannotated methods are not blocked automatically. Self-invocation and non-proxied call paths must also be examined. Domain authorization requires clear conventions and testing real call paths.

### 7.8. "anyRequest().denyAll() in One Chain Is Enough"

If that chain only matches **/api/**, other requests can fall outside it. Always inspect the full set of **SecurityFilterChain** beans, their order, and the catch-all chain so there are no coverage gaps.

## 8. Least Privilege Applies Beyond HTTP Requests Too

A sound design restricts the privileges of **executing components**:

| Component | Should Be Granted | Should Be Avoided |
| --- | --- | --- |
| Report-reading user | Permission to view reports within approved scope | Permission to delete reports, read all tenants |
| Email-sending worker | Permission to read outbound queue and send via designated provider | System admin privileges, access to all tables |
| Data-reading API | DB connection with SELECT on required tables/views | Using a database superuser account |
| Deployment CI | Deploy rights for the exact target environment and resources | Broad org-wide or non-expiring tokens |
| On-call support | Time-bounded support privileges, audited actions | Sharing permanent admin passwords |
| OAuth2 client | Only the scopes genuinely needed for the task | Broad wildcard scopes on every token |

Good practices: **separate accounts by duty**, limit token/credential lifetimes, remove privileges on role changes, revoke access on offboarding, manage secrets securely, and log key access decisions. Authorization is an ongoing change-tracking process, not a one-time setup.

### 8.1. With JWT/OAuth2, Pay Special Attention

In a **Resource Server**, a valid token **does not prove** every API may be called. Validate **issuer**, **audience**, expiration, and signature per configuration, then apply scopes/authorities together with tenant, resource, and owner checks. **SCOPE_documents.read** usually represents only an action-type permission and does not solve who may read which document.

Overly broad scopes or long-lived tokens increase blast radius if a token leaks. Design token lifetimes and scopes based on risk.

## 9. Auditing and Verifying Policy Before Release

For each endpoint or business action, build a **subject × action × resource × context** table and answer:

1. **Who is allowed?** This permission must have a business justification.
2. **Who must be denied?** Including anonymous, wrong role, wrong tenant, non-owner, locked account, or stale role.
3. **What happens if there is no new rule?** Undeclared endpoints must be denied or unreachable.
4. **What if policy data is missing or the authz service fails?** Never execute an action assuming "it's probably fine."
5. **Are URL, method, service, and data layers consistent?** Including request matchers, chain matchers, dispatches, and non-HTTP jobs.
6. **Are there audit logs for traceability?** Log subject ID, action, resource ID, decision, correlation ID within allowed bounds; **never log passwords, tokens, or sensitive data**.
7. **Are there negative tests and bypass-path tests?** Try undeclared URLs, other HTTP methods, other roles, other tenants, other IDs, direct service calls, and all request types the app actually supports.

You can enable development logging to read filter decisions:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Enable only the appropriate level per environment and never log secrets. When encountering unexpected **401/403**, identify the chain, Authentication, authorities, first matching request matcher, method rule, and resource policy. A **403** alone does not tell you which layer failed without checking logs.

### 9.1. Caution Regarding denyAll in Real Environments

**anyRequest().denyAll()** is a strong choice for an allowlist; therefore when building out an application, explicitly evaluate legitimate endpoints such as health checks, assets, authentication callbacks, CORS preflights, error/forward dispatches, and framework-provided endpoints. Add exceptions only when clearly needed and with narrow scope.

Spring Security can also evaluate authorization across **dispatcher types** such as **REQUEST**, **ERROR**, and **FORWARD** depending on configuration. If error/forward pages must work, design intentional dispatcher-type rules; never add a broad app-wide **permitAll** exception just to fix error rendering.

## 10. Self-Assessment Exercises

**Exercise 1 — New Endpoint.** You add **GET /api/export** to a controller without adding an authorization rule. With **anyRequest().denyAll()** at the end of a chain covering all URLs, what happens?

**Answer:** The request is denied before the controller runs. If a chain does not cover that URL or a broad allow rule sits earlier, the outcome can differ; check the overall chain configuration.

**Exercise 2 — Is Role Enough?** **alice** has **document:read** yet calls **GET /api/docs/doc-2** (bob's document).

**Answer:** It must be denied if the ownership policy does not allow it. Authority expresses the **action category**, not rights to a **specific document**.

**Exercise 3 — Missing Ownership Data.** The service reading the owner returns null or times out. Should access default to allow to keep the system running?

**Answer:** No. Never execute an action when proof of permission is missing. Return an infrastructure error response and retry safely; never treat a policy failure as an ALLOW decision.

**Exercise 4 — Only an /api/** Chain.** Configure one SecurityFilterChain with **securityMatcher("/api/**")** and **anyRequest().denyAll()**; is **GET /internal/debug** guaranteed to be blocked by Spring Security?

**Answer:** No. If no other chain matches **/internal/debug**, that endpoint may fall outside Spring Security's protection layer.

**Exercise 5 — Admin Privileges.** Should someone with **ROLE_ADMIN** automatically read every personal document?

**Answer:** Not by default. Define dedicated support capabilities, business purpose, scope, approval, and audit if special access is needed.

**Exercise 6 — Authentication vs. Authorization.** Why can both **401** and **403** appear when a request is unauthorized?

**Answer:** **401** typically challenges for authentication (e.g., HTTP Basic challenge) when a valid identity is absent; **403** typically applies to an authenticated identity lacking sufficient privileges. Entry point/handler policies and client types can alter the exact response.

## Official Resources for Further Learning

- Spring Security — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Java Configuration / Multiple HttpSecurity**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html

**Takeaway:** always **grant the right action, on the right resource, in the right context**. Every time functionality is added, allow policies must be explicitly decided; **every case lacking proof of permission must be denied**.
