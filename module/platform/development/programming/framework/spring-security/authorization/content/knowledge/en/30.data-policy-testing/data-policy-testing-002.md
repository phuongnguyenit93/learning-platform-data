# Testing IDOR by Substituting Resource Identifiers

## 1. Objective and Scope

**IDOR (Insecure Direct Object Reference)** is an object-level access control flaw: the application accepts a resource identifier from a request and retrieves or modifies the object without verifying that the caller is authorized for **that specific object**. In modern APIs, this flaw is commonly called **BOLA (Broken Object Level Authorization)**. What must be tested is the per-object authorization decision, not merely whether the user is logged in or holds a valid role.

After this lesson, you should know how to:
- Identify where the client supplies resource identifiers: paths, query parameters, JSON bodies, sub-resource parameters, and bulk update commands.
- Keep the caller's identity constant while substituting **only the object identifier** to attempt accessing data belonging to another account/group/tenant within an authorized test environment.
- Distinguish policy-compliant outcomes (200/204, 403, 404) from actual security flaws; verify both **response data contents and persistence effects**.
- Write automated tests for Spring Security confirming that horizontal, vertical, and cross-tenant access are blocked when the application is multi-tenant.

Only use test accounts and data that you manage or have permission from the system owner to test. Never probe IDs, extract content, or modify real users' data.

## 2. Failure Model: Authentication vs. Object Authorization

Suppose a document management API has:

- Alice owns document **101** in tenant T1.
- Bob owns document **202** in tenant T1.
- Carol owns document **303** in tenant T2.
- Alice is logged in, sends **GET /api/documents/101**, and receives her document.
- Alice changes the URL to **GET /api/documents/202**; if she receives Bob's document despite not being granted permission, IDOR/BOLA has occurred.

Protecting the **/api/documents/** route with **authenticated()** only guarantees the request carries a valid identity. Checking **hasRole("USER")** is also insufficient: Alice and Bob can both hold the USER role while having different read permissions per document. A correct decision usually needs to evaluate **subject** (caller), **action** (read/update/delete), **resource** (target object), and **context** (tenant, state, sharing relationships, timestamp) together.

There are three common testing angles:

| Testing Angle | Security Question | Example |
| --- | --- | --- |
| Horizontal authorization | Can two users with the same role view/edit each other's objects? | Alice uses Bob's document ID 202 |
| Vertical authorization | Can a lower-privileged user affect objects/functions reserved for a higher role? | A USER tries swapping the ID of a request only an ADMIN may approve |
| Tenant isolation | Can a user in tenant T1 access an object in T2? | Alice uses Carol's document ID 303 |

**Unpredictable IDs do not replace authorization.** UUIDs, ULIDs, random-looking tokens, or encoded IDs only make guessing harder; once an identifier is exposed via links, logs, responses, or sharing, access permissions must still be enforced server-side.

## 3. Designing Test Data and the Expected Matrix

Create fixtures with explicit owners and tenants. All IDs in the table are synthetic data for the test environment:

| Caller | Requested ID | Relationship | Expected under an owner-only read policy |
| --- | --- | --- | --- |
| Alice (T1) | 101 | Owner | 200 and exact content of document 101 |
| Alice (T1) | 202 | Same tenant, different owner | 403 **or** 404; no data from Bob |
| Alice (T1) | 303 | Different tenant | 403 **or** 404; no data from Carol |
| Bob (T1) | 202 | Owner | 200 and exact content of document 202 |
| Unauthenticated | 101 | No identity | 401 if the API uses HTTP authentication; may redirect for web login |
| Alice (T1) | 999 | Non-existent resource | 404 |
| Admin (authorized) | 202 | Permission per administrative policy | Succeeds only if the policy actually permits it |

**403** indicates the server knows the caller is unauthorized; **404** can be an intentional choice to avoid disclosing the object's existence. Do not conclude IDOR from the status code alone. Inspect the response body, error codes, logs, and data state after the request. Conversely, a request returning 403 that already updated data before checking permissions is still a critical flaw.

Before running tests, confirm all valid sharing cases, admin privileges, author rights, inheritance rules, document states, and tenant boundaries. Do not assume "different owner" is always forbidden if the business domain supports resource sharing.

## 4. Identifier Substitution Testing Workflow

1. **Select entry points.** Identify endpoints that read a single object, edit, delete, download files, read sub-resources, or perform bulk actions. Note where IDs live and where they originate (list responses, UI-generated paths, JSON fields).
2. **Establish a valid baseline.** Log in as Alice; call her legitimate document 101; record the method, path, request body, response status, JSON, and persistence state. This confirms the test setup works.
3. **Swap only the resource identifier.** Keep Alice's token/cookie, method, payload, and role unchanged; replace 101 with 202. Repeat with 303 if multi-tenant. Separate experiments that swap IDs in the path, query, and body to see which parameter actually selects the object.
4. **Inspect the response and side effects.** No unauthorized content may be returned. For PATCH/PUT/DELETE, check before/after data using the owning account or a test DB query; never rely solely on HTTP status.
5. **Test the reverse direction.** Log in as Bob and verify Bob can read 202 but is blocked from 101. This catches rules hardcoded to a single ID or single user.
6. **Repeat across actions and relationships.** For every action (read/update/delete/download/approve) and every relevant role/tenant, run a similar minimal matrix. Record "expected vs observed" results for regression testing.

HTTP example in a test environment with Bearer tokens; both requests use **Alice's same token**, differing only in ID:

~~~http
GET /api/documents/101 HTTP/1.1
Host: localhost:8080
Authorization: Bearer <alice-test-token>
Accept: application/json
~~~

~~~http
GET /api/documents/202 HTTP/1.1
Host: localhost:8080
Authorization: Bearer <alice-test-token>
Accept: application/json
~~~

If the policy allows only the owner to read, the second request must be denied (403 or 404) and must never return document 202's content. These requests illustrate the protocol; the runnable application example below uses HTTP Basic and MockMvc instead of Bearer tokens.

**ID locations frequently overlooked:**
- Path: **/api/orders/{orderId}**, **/api/orders/{orderId}/items/{itemId}**. Ensure the item actually belongs to the order and the caller is authorized for that relationship.
- Query: **GET /api/reports?accountId=202**. The server must not trust a client-supplied accountId as proof of ownership.
- Body: fields like **documentId**, **ownerId**, **tenantId**, **targetUserId** in PATCH/POST; especially when the request allows changing ownership relationships.
- Bulk operations: **POST /api/documents/bulk-delete** with an ID list spanning multiple users' resources. Check permission on **every ID** and define transaction policy when a subset is invalid.
- Downloads/exports, previews, attachments, version history, search/list, and internal endpoints called by the frontend. Access rules must stay consistent between listing and direct reads.
- GraphQL resolvers, gRPC services, or WebSocket access if present: object authorization boundaries apply just as in HTTP.

## 5. Demonstrating the Bug and Controls in Spring Security

### 5.1. Vulnerable Snippet (Illustrative Only, Not for Production)

~~~java
@GetMapping("/{id}")
public DocumentView read(@PathVariable long id) {
    return repository.findById(id)
            .map(DocumentView::from)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
}
~~~

The snippet above only checks whether **the object exists**, without checking whether **the caller is authorized to read it**. Even if the endpoint is configured with **authenticated()**, any logged-in user can try other IDs unless a check exists at the service/repository layer. This is a pseudo-snippet: repository/DocumentView types must be defined by the real application.

### 5.2. Minimal Runnable Spring Boot Example for Testing

The example uses Java 21, Spring Boot 3.3, Spring Security 6, and two in-memory documents to isolate access control flaws. In-memory data is solely for learning and testing; real applications should query the DB scoped by principal/tenant and handle transactions appropriately.

Create the following files in a Gradle project:

**settings.gradle**

~~~groovy
rootProject.name = 'idor-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/idor/IdorDemoApplication.java**

~~~java
package demo.idor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdorDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/idor/SecurityConfig.java**

~~~java
package demo.idor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**src/main/java/demo/idor/DocumentView.java**

~~~java
package demo.idor;

public record DocumentView(long id, String owner, String title) {
}
~~~

**src/main/java/demo/idor/DocumentStore.java**

~~~java
package demo.idor;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
class DocumentStore {
    private final Map<Long, DocumentView> documents = Map.of(
            101L, new DocumentView(101L, "alice", "Alice's Document"),
            202L, new DocumentView(202L, "bob", "Bob's Document")
    );

    Optional<DocumentView> findOwnedBy(long id, String username) {
        return Optional.ofNullable(documents.get(id))
                .filter(document -> document.owner().equals(username));
    }
}
~~~

**src/main/java/demo/idor/DocumentController.java**

~~~java
package demo.idor;

import java.security.Principal;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/documents")
class DocumentController {
    private final DocumentStore store;

    DocumentController(DocumentStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    DocumentView read(@PathVariable long id, Principal principal) {
        return store.findOwnedBy(id, principal.getName())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

The decision point lies in **findOwnedBy(id, principal.getName())**. The principal is provided by Spring Security from the authenticated session; clients cannot gain access simply by altering **ownerId** in the request. The store only returns the document when **the ID matches and the caller is the owner**. Both non-existent documents and documents belonging to another user return 404 under this example's existence-hiding policy.

In an application with a DB and tenants, query design typically needs to constrain **id + tenantId + ownerId/share permissions** directly at data access. Illustrative JPA repository signature (not a standalone compilable class):

~~~java
Optional<Document> findByIdAndTenantIdAndOwnerId(
        Long documentId, Long tenantId, Long ownerId);
~~~

The **tenantId** and **ownerId** used for authorization must be derived from the authenticated principal/context or a trusted server mapping, never taken directly from client input. If the policy includes sharing permissions, check the corresponding ACL or policy service; if there is an ADMIN bypass, explicitly specify which admins, which tenants, and which actions are allowed. For write operations, enforce permissions within the same service/transaction flow to avoid checking one object while updating another, or checking and then having data change before writing.

Spring Security supports **@EnableMethodSecurity** with **@PreAuthorize** for service-layer policies. For example, **@PreAuthorize("@documentPolicy.canRead(#p0, authentication)")** can check permission for the first ID parameter, but the **documentPolicy** bean must be defined and perform ownership/tenant checks on trusted data. Annotations do not automatically know who owns an object. If checks are placed on the controller, still ensure every other entry point into the service enforces the same policy.

### 5.3. Automated Testing with MockMvc

**src/test/java/demo/idor/DocumentAuthorizationTest.java**

~~~java
package demo.idor;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    @WithMockUser(username = "alice")
    void changingOnlyIdCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "bob")
    void bobCanReadHisOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    @WithMockUser(username = "bob")
    void accessDeniedInReverseDirectionToo() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "alice")
    void missingDocumentIsNotFound() throws Exception {
        mvc.perform(get("/api/documents/999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void anonymousUserMustAuthenticate() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Run from the project directory with JDK 21 and Gradle 8.5 (or a compatible Gradle wrapper):

~~~bash
gradle test
~~~

Expected result: **all 6 tests PASS** on the example above; no database, production accounts, or real tokens are needed. If **findOwnedBy(...)** were replaced with a plain ID lookup, the two ID-swapping tests would catch the data leak because they would receive 200 instead of 404. **@WithMockUser** only simulates a principal for security tests; real integration tests also need to verify tokens/sessions, tenant resolvers, and the repository/DB the system uses.

## 6. For Edit/Delete Operations, Verify Consequences

GET helps uncover data leaks; IDOR on **PATCH/PUT/DELETE/POST actions** can be more dangerous because it mutates resources. Example supplemental matrix for Alice:

| Operation | Identifier | Outcome to Verify |
| --- | --- | --- |
| PATCH /api/documents/101 | Alice's document | Succeeds if Alice has edit permission; changes are persisted |
| PATCH /api/documents/202 | Bob's document | Denied; **Bob's content remains unchanged** |
| DELETE /api/documents/202 | Bob's document | Denied; **the document still exists** |
| POST /api/documents/202/approve | Bob's document | Succeeds only if the policy permits that role/action |
| GET /api/documents/202/download | Bob's document | Does not return the file, signed download URL, or sensitive metadata |

For state-changing requests in session/cookie-based applications, supply a valid CSRF token when required; a **403 caused by a missing CSRF token** does not prove object authorization works. For stateless Bearer APIs, CSRF configuration must match the actual authentication model—never disable it blindly just to make tests pass. Verify the response, post-request state, events/audits, and related objects.

If an API returns a list containing only permitted documents while the **GET /{id}** endpoint returns any ID, list filtering does not protect direct access. Conversely, if the detail endpoint enforces permissions properly while search/export/bulk actions skip the policy, a vulnerability still exists.

## 7. Common Pitfalls When Analyzing Results

- **401 vs 403/404:** 401 means unauthenticated; 403/404 for an authenticated request usually relates to authorization or existence. Do not use a tokenless request to conclude that ID substitution is blocked.
- **Confusing ownership with role:** Holding the USER role does not mean permission to read every other USER's documents. Conversely, valid sharing grants can allow non-owners to access a resource.
- **Checking only status codes:** An API may return 200 with sensitive data in JSON, error details, or caches; a write API may cause side effects before returning an error. Always compare actual data.
- **Trusting client-supplied tenantId/ownerId:** If the service reads tenantId from JSON/query, an attacker can alter both ID and tenantId. Tenant context must come from a trusted identity and be verified against the resource.
- **Relying solely on UUIDs:** Unpredictability does not create authorization. A document whose link is leaked still needs ownership/sharing checks.
- **Protecting only the controller:** Another path such as a batch job, GraphQL resolver, or service method might call the repository while bypassing the check; move policies to the appropriate service/data-access layer.
- **Caches and file storage:** Cache keys must distinguish objects and permissions/tenants where appropriate; download URLs, object storage, and response caches must not inadvertently share data across users.
- **Checking one record then updating by another ID:** For mutations, avoid checking permissions on one record and then updating using an unconstrained client-supplied ID; account for transaction consistency and race conditions.
- **Testing only sequential IDs:** Use fixture IDs across different owners/tenants/roles instead of only 101, 102; the goal is testing policy, not guessing IDs.

## 8. Bug Reporting and Completion Criteria

An IDOR reproduction report should include: endpoint/method, tested actor/role/tenant, valid object ID, unauthorized object ID, expected policy, both requests with tokens redacted, observed status/body, evidence of side effects (if any), security impact, and regression tests. Never include access tokens, sensitive secrets, or real personal data in reports.

**PASS criteria for testing:** legitimate operations continue working; switching to unauthorized IDs is consistently denied across every entry point; no data leaks via body/file/cache; no unauthorized side effects occur; tenant boundaries are preserved; behaviors are guarded by automated tests and re-run after policy changes.

**Key takeaway:** Spring Security authenticates the caller and provides authorization mechanisms; the application itself must define and enforce permissions per **specific resource**. Substituting identifiers within the same session is the most direct way to prove whether the policy is enforced on each individual object.
