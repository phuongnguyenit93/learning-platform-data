# Subject–Action–Resource Matrix for Expressing Permission Requests

> **Context:** Access control models in Spring Security applications. This lesson aims to clearly express **who** (subject) can perform **which action** (action) on **which resource** (resource), interpret allow/deny decisions, and translate that model into backend authorization checks.

## 1. What Components Make Up an Authorization Request?

To answer "can this user open that document?", knowing only that the user is logged in is not enough. An access decision needs at least a triple:

**`(subject, action, resource)`** — or in shorthand, **`(S, A, R)`**.

| Component | Meaning | Example |
| --- | --- | --- |
| **Subject — S** | Subject requesting access: user, service account, or system-identified role | `alice`, `bob`, report-export service account |
| **Action — A** | Business operation to perform on the resource | `READ`, `EDIT`, `DELETE`, `APPROVE` |
| **Resource — R** | Resource type or **a specific object** to protect | `document:101`, `invoice:987`, `tenant:acme` |
| **Context — C** (when needed) | Context affecting the decision: tenant, owner, status, limit, time, etc. | `tenant=acme`, `status=DRAFT` |

A policy decision can be described by:

`isAllowed(S, A, R, C) → true/false`.

In Java/Spring Security, the subject usually comes from a verified `Authentication`; the action comes from the business operation; the resource should be resolved **from trusted server data** (e.g., a record by ID), without trusting client-supplied `owner` or `tenant` fields.

**Key distinctions:**

- **Authentication** establishes subject identity. **Authorization** decides whether the `(S,A,R)` triple/rule is permitted.
- The `document:read` permission describes the **action category**, which is not necessarily enough to read **every document**. Target document, ownership, or tenant must still be evaluated.
- HTTP methods (`GET`, `POST`, `PATCH`, etc.) guide routing and request semantics, but business actions (`READ`, `EDIT`, `APPROVE`) must be mapped explicitly per API semantics. Never assume every `POST` requires the same permission.

## 2. Access Control Matrix: Rows Are Subjects, Columns Are Resources

An **access control matrix** represents permissions in two dimensions. Each **row** is a subject, each **column** is a resource; the **intersecting cell** holds the set of permitted actions on that resource.

Notation:

`M[S,R] = {A1, A2, ...}`

and:

`allow(S,A,R) ⇔ A ∈ M[S,R]`

If the cell set is empty, no matching permission exists. Under **default deny**, the request is rejected. To capture dynamic conditions such as tenant, ownership, and object state, think of the matrix as a **snapshot of effective permissions at a given point in time/context**.

### Example: Three Documents Across Two Tenants

The system has three documents:

- `doc-101`: belongs to tenant `acme`, owned by Alice; Alice shares **READ** with Bob.
- `doc-202`: belongs to tenant `acme`, owned by Bob; Bob shares **READ** with Alice.
- `doc-301`: belongs to tenant `orbit`, owned by Carol.
- Maya is `MANAGER` of **tenant acme**. The example policy allows a manager to read/edit documents in their own tenant, but **not across other tenants**.

The actions are `READ` (view content) and `EDIT` (edit content). Assume **owner** gets both READ/EDIT; sharing grants only the recorded action; manager privileges apply only within their own tenant.

| Subject | `doc-101` (acme) | `doc-202` (acme) | `doc-301` (orbit) |
| --- | --- | --- | --- |
| **Alice — acme** | READ, EDIT | READ | ∅ |
| **Bob — acme** | READ | READ, EDIT | ∅ |
| **Carol — orbit** | ∅ | ∅ | READ, EDIT |
| **Maya — acme/MANAGER** | READ, EDIT | READ, EDIT | ∅ |

Reading three representative cells:

1. `M[alice, doc-101] = {READ, EDIT}`: Alice is the owner, so `(alice, EDIT, doc-101)` is allowed.
2. `M[alice, doc-202] = {READ}`: Bob shared read access with Alice; `(alice, EDIT, doc-202)` must be denied.
3. `M[maya, doc-301] = ∅`: Maya holds a manager role **in acme**, but `doc-301` belongs to `orbit`; the request must be denied before evaluating manager privileges.

**Do not interpret ∅ as meaning the resource does not exist.** It only states that this subject **has no granted action** on that resource under the current policy. The resource may exist yet be inaccessible.

### Turning a Request into a Matrix Cell Lookup

~~~text
Request: Alice wants to EDIT doc-202
          |
          v
Authenticate request -> principal = alice
          |
          v
Normalize action = EDIT
          |
          v
Load doc-202 from trusted data store: tenant=acme, owner=bob
          |
          v
Check Alice's tenant == document's tenant? Yes
          |
          v
Look up effective permissions M[alice, doc-202] = {READ}
          |
          v
Is EDIT in {READ}? No
          |
          v
DENY (blocked on backend)
~~~

An allowed cell does not automatically mean every other condition passes. For example, the document may be locked or Alice may be suspended. In that case `allow(S,A,R,C)` also depends on context `C`. **Evaluation order** and deny/allow precedence must be explicit design decisions.

## 3. Three Views of the Same Policy

The **full matrix form** is convenient for learning, reviewing, and testing. In real databases, a `users × resources` matrix is usually huge and mostly empty; systems typically store permissions as **sparse relationship lists** or derived policies.

### 3.1. Row–Column Matrix

The table format in section 2 is easy for humans to read. It supports both "Who can EDIT document X?" and "What can Alice do with document Y?".

### 3.2. Permission Grant List: `(subject, action, resource)` Triples

The **explicit** subset of permissions can be stored as:

| subject | action | resource |
| --- | --- | --- |
| `bob` | `READ` | `doc-101` |
| `alice` | `READ` | `doc-202` |

These are **shared** permissions. Owner and manager permissions in the example are **derived by rules**, so there is no need to pre-populate every triple for every document. A similar database table might have columns `subject_id, action, resource_type, resource_id`, along with tenant, grantor, and expiration timestamp if required by the business.

### 3.3. Resource-Attached ACL

An **Access Control List (ACL)** attaches a list of subjects/permissions to each resource:

~~~text
doc-101:
  owner: alice
  tenant: acme
  acl:
    - subject: bob
      actions: [READ]

doc-202:
  owner: bob
  tenant: acme
  acl:
    - subject: alice
      actions: [READ]
~~~

ACLs conveniently answer "Who can access this document?". Subject-centric permission lists conveniently answer "Which documents can this account access?". Both can represent equivalent policies; **do not confuse storage format with security rules**.

> The term *capability* has a stricter meaning than a per-user permission list: it is typically an unforgeable reference/token granting the ability to operate on a resource. Simply having a `user → resource → action` list is not enough to call it a capability-based security system.

## 4. Extending the Triple to Model Real Policies

For many business domains, name permissions after **resource type + action**, then add conditions for the resource instance:

| Request | Business Action | Resource | Additional Conditions |
| --- | --- | --- | --- |
| `GET /api/docs/101` | READ | Document 101 | Owner, shared user, or same-tenant manager |
| `PATCH /api/docs/101` | EDIT | Document 101 | EDIT permission, document unlocked |
| `POST /api/invoices/987/approve` | APPROVE | Invoice 987 | Approval permission, right unit, did not create invoice |
| `DELETE /api/users/58` | DELETE | User 58 | Scoped admin, no account constraint violations |
| `GET /api/projects/74/members` | LIST_MEMBERS | Project 74 | Project membership or project management permission |

A decision can be written as a *policy predicate*:

`allow(s, a, r, c) = authenticated(s) ∧ sameTenant(s,r) ∧ hasEffectiveAction(s,a,r) ∧ contextSatisfied(a,r,c)`.

The symbol `∧` means **simultaneously satisfied**; a single failing condition must return deny. In real applications, functions may vary by action and resource type. For example, a public `READ_PUBLIC` permission might not require login, but must be specified explicitly rather than accidentally left unguarded.

### Comparison with RBAC and ABAC

- **Access matrix** is a way to **describe/map permissions**: for this subject and this resource, which actions are allowed?
- **RBAC** is a way to **grant permissions through roles**: user → role → permission. You can compute each user's effective permissions and populate the matrix.
- **ABAC** incorporates attributes into conditions: user department, resource tenant, data classification, timestamp, status, etc. The matrix can represent a **snapshot of results** after evaluating attributes at a point in time.
- **Owner/ACL** are mechanisms granting permissions per resource instance; they can be combined with RBAC and ABAC.

For example, the `DOC_EDITOR` role having `document:edit` is a **necessary** condition, while which tenant the document belongs to or which instances the user is granted access to are **additional** conditions. **Do not** conclude that `hasAuthority("document:edit")` means permission to edit every document in the system.

## 5. Pure Java 17: Computing the Effective Permission Matrix from Policy

The following is a **complete, standalone program**, compilable/runnable on JDK 17+ with no external libraries. Sample data is declared in memory. Rather than storing every matrix cell, it computes them from **tenant + MANAGER role + owner + shared ACL**.

Create a file named **`AccessMatrixDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AccessMatrixDemo {

    enum Action {
        READ, EDIT
    }

    record Subject(String username, String tenant, Set<String> roles) {}

    record Document(
        String id,
        String tenant,
        String owner,
        Map<String, Set<Action>> grants
    ) {}

    static boolean allowed(Subject subject, Action action, Document document) {
        if (subject == null || action == null || document == null) {
            return false;
        }

        // Tenant boundary is mandatory, even for MANAGER.
        if (!subject.tenant().equals(document.tenant())) {
            return false;
        }

        // Example business rule: MANAGER has READ/EDIT within tenant.
        if (subject.roles().contains("MANAGER")) {
            return true;
        }

        // Owner has READ/EDIT on their own document.
        if (subject.username().equals(document.owner())) {
            return true;
        }

        // Other subjects only have actions recorded in the ACL.
        return document.grants()
            .getOrDefault(subject.username(), Set.of())
            .contains(action);
    }

    static String rights(Subject subject, Document document) {
        List<String> result = new ArrayList<>();
        for (Action action : Action.values()) {
            if (allowed(subject, action, document)) {
                result.add(action.name());
            }
        }
        return result.isEmpty() ? "-" : String.join(",", result);
    }

    public static void main(String[] args) {
        Subject alice = new Subject("alice", "acme", Set.of("MEMBER"));
        Subject bob = new Subject("bob", "acme", Set.of("MEMBER"));
        Subject carol = new Subject("carol", "orbit", Set.of("MEMBER"));
        Subject maya = new Subject("maya", "acme", Set.of("MANAGER"));

        Document doc101 = new Document(
            "doc-101", "acme", "alice",
            Map.of("bob", Set.of(Action.READ))
        );
        Document doc202 = new Document(
            "doc-202", "acme", "bob",
            Map.of("alice", Set.of(Action.READ))
        );
        Document doc301 = new Document(
            "doc-301", "orbit", "carol", Map.of()
        );

        List<Subject> subjects = List.of(alice, bob, carol, maya);
        List<Document> documents = List.of(doc101, doc202, doc301);

        System.out.println("subject | doc-101 | doc-202 | doc-301");
        for (Subject subject : subjects) {
            List<String> cells = new ArrayList<>();
            for (Document document : documents) {
                cells.add(rights(subject, document));
            }
            System.out.println(
                subject.username() + " | " + String.join(" | ", cells)
            );
        }

        System.out.println(
            "alice EDIT doc-202: " + allowed(alice, Action.EDIT, doc202)
        );
        System.out.println(
            "maya READ doc-301: " + allowed(maya, Action.READ, doc301)
        );
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac AccessMatrixDemo.java
java AccessMatrixDemo
~~~

**Exact stdout:**

~~~text
subject | doc-101 | doc-202 | doc-301
alice | READ,EDIT | READ | -
bob | READ | READ,EDIT | -
carol | - | - | READ,EDIT
maya | READ,EDIT | READ,EDIT | -
alice EDIT doc-202: false
maya READ doc-301: false
~~~

### Reading the Program by Policy Layer

1. **`Subject`** holds username, tenant, and roles. The sample program supplies known data itself; in real applications, these attributes must be verified/loaded from trusted sources.
2. **`Document`** holds ID, tenant, owner, and `grants` for shared users.
3. **`allowed(...)`** rejects null inputs and cross-tenant accesses **before** checking manager or owner privileges, preventing a tenant A manager from opening tenant B documents.
4. After the tenant boundary, the program checks manager role, owner, and then ACL. This is an **illustrative policy explicitly defined for the example**, not a built-in Spring Security rule.
5. **`rights(...)`** tests `READ` and `EDIT` in turn; the set of permitted actions forms each matrix cell.
6. The last two lines confirm **deny** cases: Alice can read Bob's document but cannot edit it; Maya cannot read another tenant's document.

**Security note:** the branch order here suits a simple policy: "mandatory tenant boundary; then manager/owner/ACL as ALLOW sources". If the product has **explicit deny**, locked documents, suspended users, or policy conflicts, define precedence and add those checks before returning `true`. Never assume "allow always wins over deny" or vice versa without an explicit contract.

## 6. Bringing the Matrix into Spring Security: From Principal to Method Security

The Java code above explains the policy without framework dependencies. In Spring Security, a typical implementation is:

1. Authentication verifies credentials/tokens and creates `Authentication`.
2. HTTP security guards public routes and requires login for the API zone.
3. **Method security** receives `Authentication` and the resource ID, calling a **policy service** to compute `allowed(subject,action,resource)`.
4. Controllers return data only when method-level authorization allows it.
5. Any other path invoking the business logic must go through the **same service/policy**, avoiding duplicated policies or trusting frontend checks.

### Complete Java 17+ Spring Boot Example

Create a Maven project via Spring Initializr with **Java 17+**, **Spring Web**, and **Spring Security** dependencies. Create **`src/main/java/com/example/matrix/MatrixApplication.java`** with the following content. The code uses fixed demo accounts/data for illustration; **never use hardcoded credentials as production configuration**.

~~~java
package com.example.matrix;

import java.util.Map;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class MatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatrixApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .requestMatchers("/api/docs/**").authenticated()
            .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            user("alice", "demo123", "MEMBER", encoder),
            user("bob", "demo456", "MEMBER", encoder),
            user("carol", "demo789", "MEMBER", encoder),
            user("maya", "demo999", "MANAGER", encoder)
        );
    }

    private static UserDetails user(
        String name, String rawPassword, String role, PasswordEncoder encoder
    ) {
        return User.withUsername(name)
            .password(encoder.encode(rawPassword))
            .roles(role)
            .build();
    }

    @RestController
    public static class DocumentController {
        private final DocumentService service;

        public DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        public String ping() {
            return "pong";
        }

        @GetMapping("/api/docs/{id}")
        public String read(@PathVariable("id") long id) {
            return service.read(id);
        }

        // Only previews EDIT access; this GET does not mutate data.
        @GetMapping("/api/docs/{id}/edit-preview")
        public String editPreview(@PathVariable("id") long id) {
            return service.editPreview(id);
        }
    }

    @Service
    public static class DocumentService {

        @PreAuthorize("@documentPolicy.allowed(authentication, #p0, 'READ')")
        public String read(long id) {
            return "document " + id;
        }

        @PreAuthorize("@documentPolicy.allowed(authentication, #p0, 'EDIT')")
        public String editPreview(long id) {
            return "edit preview " + id;
        }
    }

    @Component("documentPolicy")
    public static class DocumentPolicy {

        private record Doc(
            long id, String tenant, String owner, Set<String> readers
        ) {}

        private final Map<Long, Doc> documents = Map.of(
            101L, new Doc(101L, "acme", "alice", Set.of("bob")),
            202L, new Doc(202L, "acme", "bob", Set.of("alice")),
            301L, new Doc(301L, "orbit", "carol", Set.of())
        );

        // Demo: tenant is mapped on the server, never accepted from the client.
        private final Map<String, String> userTenants = Map.of(
            "alice", "acme",
            "bob", "acme",
            "carol", "orbit",
            "maya", "acme"
        );

        public boolean allowed(
            Authentication authentication, long id, String action
        ) {
            if (authentication == null || !authentication.isAuthenticated()) {
                return false;
            }

            Doc doc = documents.get(id);
            if (doc == null) {
                return false;
            }

            String username = authentication.getName();
            String tenant = userTenants.get(username);
            if (!doc.tenant().equals(tenant)) {
                return false;
            }

            if (!"READ".equals(action) && !"EDIT".equals(action)) {
                return false;
            }

            boolean manager = authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_MANAGER".equals(a.getAuthority()));

            if (manager || username.equals(doc.owner())) {
                return true;
            }

            return "READ".equals(action) && doc.readers().contains(username);
        }
    }
}
~~~

**Explanation of Spring Security mechanics:**

- `@EnableMethodSecurity` enables `@PreAuthorize`; the Spring Security starter **does not automatically enable** method security merely by being declared as a dependency.
- `authentication` in the expression retrieves the current principal from the security context; `#p0` is the method's first parameter (document ID). The policy runs **before** the method body executes.
- `@documentPolicy` references the Spring bean named `documentPolicy`. Putting the policy in a standalone component enables reuse and centralized testing.
- `DocumentController` calls `DocumentService` through a **Spring-managed bean**, so the method security proxy applies. Avoid calling `@PreAuthorize` methods via `this` inside the same bean under standard proxy mechanics.
- The `/api/docs/**` route only requires `authenticated()`. The decision of **which specific document can be read/edited** belongs to `DocumentPolicy`; `authenticated()` alone is insufficient.
- For user Maya, `ROLE_MANAGER` is evaluated **only after** checking the tenant; an `acme` manager cannot cross into `orbit`.
- The example uses `GET /edit-preview` because it **does not change state**. When implementing real EDIT operations, use an appropriate HTTP method (`PATCH`/`PUT`/`POST`) and handle CSRF according to the authentication mechanism; never use GET to modify data.

Run the application in the project directory:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
~~~

Test with `curl` while the server is running on the default port 8080:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/docs/101
curl -i -u alice:demo123 http://localhost:8080/api/docs/101
curl -i -u alice:demo123 http://localhost:8080/api/docs/202
curl -i -u alice:demo123 http://localhost:8080/api/docs/202/edit-preview
curl -i -u bob:demo456 http://localhost:8080/api/docs/202/edit-preview
curl -i -u maya:demo999 http://localhost:8080/api/docs/101/edit-preview
curl -i -u maya:demo999 http://localhost:8080/api/docs/301
~~~

| Request | Expected HTTP | Reason |
| --- | --- | --- |
| `GET /public/ping` (anonymous) | `200`, body `pong` | Public route |
| `GET /api/docs/101` (anonymous) | `401` | Unauthenticated; HTTP Basic requires credentials |
| `GET /api/docs/101` (Alice) | `200`, body `document 101` | Owned by Alice |
| `GET /api/docs/202` (Alice) | `200`, body `document 202` | Bob shared READ |
| `GET /api/docs/202/edit-preview` (Alice) | `403` | Alice lacks EDIT |
| `GET /api/docs/202/edit-preview` (Bob) | `200`, body `edit preview 202` | Owned by Bob |
| `GET /api/docs/101/edit-preview` (Maya) | `200`, body `edit preview 101` | Manager in same tenant |
| `GET /api/docs/301` (Maya) | `403` | Different tenant; manager privilege does not cross boundaries |

These statuses apply to the example's **HTTP Basic and method security**. With form login, unauthenticated requests may redirect to the login page. For nonexistent IDs, the current policy returns `false` so authenticated requests get denied; a real application may deliberately return 404 to avoid disclosing resource existence. Returning 403 or 404 must be consistent and avoid leaking information in error details.

## 7. From Manual Matrix to Data Schema and Enforcement

When resource counts are large, do not store a full `users × documents` table. You can store **explicit grants** as rows:

~~~sql
-- PostgreSQL, illustrating per-resource permission structure:
CREATE TABLE document_grants (
    tenant_id VARCHAR(100) NOT NULL,
    document_id BIGINT NOT NULL,
    subject_id BIGINT NOT NULL,
    action VARCHAR(30) NOT NULL,
    granted_by BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, document_id, subject_id, action)
);
~~~

This table is an **illustrative schema**, omitting the documents/accounts tables and corresponding foreign keys. In production, add appropriate foreign keys, query indexes, valid-action constraints, and a revocation/expiration model. Owner/manager permissions can be **derived by policy** rather than duplicated into `document_grants`.

Reading a subject's grants for a specific document (using bind parameters in code):

~~~sql
SELECT action
FROM document_grants
WHERE tenant_id = :tenant_id
  AND document_id = :document_id
  AND subject_id = :subject_id;
~~~

`:tenant_id`, `:document_id`, and `:subject_id` are data-access-layer placeholders, not standalone PostgreSQL syntax to paste verbatim into `psql`.

**Crucial point:** the ACL query is only **one grant source**. The final allow/deny outcome can still depend on tenant, owner, role, and document state. Evaluate it inside a **shared policy service**, rather than writing three diverging logic variants across controllers, repositories, and frontend.

### Authorize Before Returning Data

At the service layer, follow this sequence:

1. Identify the principal from the verified `Authentication`.
2. Resolve the action from the operation being performed (never accept an arbitrary action string from the client and let the client choose).
3. Load the resource and tenant/owner/state from the database with properly constrained queries.
4. Evaluate the permission policy against **verified** attributes.
5. Return data or execute changes only when ALLOW.

For **LIST/SEARCH** endpoints like `GET /api/docs`, checking a single document ID is not applicable. **Filter directly inside the query** by tenant, owner/share/role, and access rules; fetching all documents and filtering in Java can leak data via pagination, total counts, or performance side channels.

### Avoid Checking Early and Using Stale Data Later

During write operations, document state or permissions can change between check and update (**time-of-check/time-of-use**). For sensitive operations, ensure the check and update share an appropriate snapshot/transaction, or embed permission/state conditions into the write query and check the updated row count. Do not assume a single `@PreAuthorize` is always sufficient when resources can change owner/status concurrently.

## 8. Testing the Matrix and Negative Cases

A solid test suite must treat the matrix as a **behavioral specification**, not just test "valid-permission" requests.

With 4 subjects × 3 resources × 2 actions in the example, there are **24 triples** to consider. You do not need 24 identical test methods: use **parameterized tests** or loops generating `(subject, action, resource, expectedAllow)`, and assert against the policy result. At minimum verify:

| Case | Expected |
| --- | --- |
| Owner reads/edits document in same tenant | ALLOW |
| User with shared READ reads document | ALLOW |
| Read-only user attempts EDIT | DENY |
| Unshared user attempts READ | DENY |
| MANAGER accesses document in managed tenant | ALLOW per example policy |
| MANAGER accesses document in another tenant | DENY |
| Nonexistent document ID | DENY or 404 per API contract |
| Action unsupported by the model | DENY |
| Request missing Authentication for protected API | 401/redirect per login mechanism |
| Client tampers with `tenantId` or `ownerId` to spoof access | DENY because server ignores those fields |

When adding permissions or changing roles, update the **expected matrix** and run tests. For multi-state resources, add cases for locked documents, disabled accounts, expired shares, tokens carrying stale permissions, tenant changes, and concurrent requests.

## 9. Common Misconceptions

1. **"User has EDITOR role, so they can edit any document."** Not necessarily: the role may grant `document:edit` capability, while each resource instance still requires tenant/ownership/ACL scope.
2. **"Username and action alone are enough to decide permission."** Missing the resource instance; Alice can edit `doc-101` but cannot edit `doc-202`.
3. **"The URI is the only resource to consider."** `/api/docs/{id}` can point to many distinct objects with different owners, tenants, and states.
4. **"If there is no DENY row, just ALLOW."** Wrong under **default deny**: lacking a valid grant must be denied.
5. **"Blocking in the frontend makes it safe."** Hiding buttons in the frontend does not stop direct API calls; the backend must enforce policy.
6. **"A MANAGER in tenant A is a MANAGER system-wide."** Wrong when roles are scoped; check tenant at decision time.
7. **"The action list sent by the client is trustworthy."** Clients can send `EDIT`; the server must know which business action an endpoint performs and check permissions itself.
8. **"Every matrix cell must exist as a stored record."** Unnecessary: many effective permissions are derived from roles, owners, groups, ACLs, or attributes.
9. **"Protecting a single-ID endpoint suffices for list APIs."** For LIST/SEARCH, the query itself must enforce data scope; pagination/totals can leak forbidden records.
10. **"A permission check once remains valid forever."** Roles, owners, tenants, states, and shares can change; sessions/tokens/caches and transactions must have proper refresh and revocation policies.

## 10. Self-Check Exercise

Using the matrix in section 2:

1. `(alice, READ, doc-202)` → **ALLOW** because Bob shared read access.
2. `(alice, EDIT, doc-202)` → **DENY** because Alice is not the owner and only has READ.
3. `(bob, EDIT, doc-202)` → **ALLOW** because Bob is the owner.
4. `(carol, READ, doc-101)` → **DENY** because of different tenant.
5. `(maya, EDIT, doc-101)` → **ALLOW** per MANAGER policy in tenant acme.
6. `(maya, READ, doc-301)` → **DENY** because tenant orbit differs from acme.
7. If Bob additionally shares EDIT on `doc-101`, wait—if Bob is not owner, or if Bob receives EDIT on `doc-101`, which cell changes? **`M[bob, doc-101]`** changes from `{READ}` to `{READ,EDIT}`; other cells do not change automatically.
8. If `doc-202` transitions to a locked state, can the EDIT result change? **Yes**, if the policy adds `status != LOCKED`; the earlier matrix was a snapshot of effective permissions before state changes.

**Remember:** an authorization request is **"which subject – wants to do what – on which resource – in which context"**. An access control matrix helps express and test permission sets as `(S,A,R)` triples; Spring Security enforces them via authentication, request authorization, and method/domain policies. Policies must **deny by default**, rely on trusted server data, and check the exact resource instance.

## Official Documentation

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Expression-Based Access Control: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html#use-authorization-custom-bean
