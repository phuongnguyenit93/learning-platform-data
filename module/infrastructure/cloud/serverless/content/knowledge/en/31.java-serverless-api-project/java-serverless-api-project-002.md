# Designing Data Models and Per-User Access Control

A Java serverless API often serves many concurrent users who may belong to different organizations (tenants) and hold different roles on each resource. A project's creator can edit that project; another member may only view it; a tenant administrator can manage members; users in another tenant must never read data even if they guess a project ID.

These requirements must be reflected consistently across the data model, the API contract, and the authorization layer. Merely hiding UI buttons or checking a role at the API Gateway is not enough. Every read/write operation must verify the authenticated identity, tenant scope, membership, and permissions on the exact target object. The database should enforce constraints that prevent cross-tenant data from being linked accidentally; Java services must enforce policies before side effects; and tests must prove users cannot access others' objects.

This lesson uses a workspace, project, and task management API as an example. You will design schemas for users, tenants, memberships, and resource ownership; distinguish authentication from authorization; implement tenant-scoped repositories and object-level access checks in Java/Spring; and examine Row-Level Security (RLS), indexes, transactions, and serverless-specific risks.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish user identity, tenant membership, resource ownership, and workload identity.
- Design a data model that supports a single user belonging to multiple tenants.
- Choose between shared schema, schema-per-tenant, and database-per-tenant.
- Use foreign keys, unique constraints, and composite keys to protect tenant boundaries.
- Define RBAC, ABAC, and ownership relationships for each API operation.
- Validate JWT/OIDC tokens and map issuer + subject to an internal user.
- Implement object-level authorization and tenant-scoped queries in Java.
- Prevent IDOR, mass assignment, and cross-tenant access.
- Use transactions, optimistic locking, and database RLS as defense-in-depth layers.
- Propagate actor/tenant context safely across events and background functions.
- Test positive access, negative access, membership revocation, and race conditions.

## 1. The Problem: One User, Multiple Tenants, Multiple Object Permissions

Suppose the API provides the following capabilities:

- Users sign in via an identity provider.
- A user can belong to multiple workspaces/tenants.
- Each tenant has multiple projects.
- Projects have members with roles OWNER, EDITOR, or VIEWER.
- Projects contain tasks; tasks have a creator and an assignee.
- Certain operations are restricted to tenant admins or project owners.

For example:

| User | Tenant | Role | Project | Permissions |
|---|---|---|---|---|
| An | Acme | TENANT_ADMIN | Mobile App | Manage tenant and projects |
| Binh | Acme | MEMBER | Mobile App | EDITOR | Read/edit project and tasks |
| Chi | Acme | MEMBER | Mobile App | VIEWER | Read-only |
| Dung | Beta | TENANT_ADMIN | Billing | Manage Beta data |

Binh may be an editor in Mobile App while only a viewer in another project. Therefore, a global role attached to the user is usually insufficient to represent actual permissions.

A request:

~~~http
GET /tenants/{tenantId}/projects/{projectId}
Authorization: Bearer <access-token>
~~~

must answer several questions:

1. Is the token valid and issued for this API?
2. Which internal user does the token represent?
3. Does the user have an active membership in the requested tenant?
4. Is the user permitted to view that specific project?
5. Does the project actually belong to the tenant in the path?
6. Does the response contain any fields the user is not allowed to see?

None of these questions can be replaced by simply checking whether the user is signed in.

## 2. Authentication and Authorization Are Two Distinct Steps

**Authentication** answers "which principal sent this request?". **Authorization** answers "what actions is that principal allowed to perform on which resources?".

| Component | Responsibility | Example |
|---|---|---|
| Identity provider | Authenticate users and issue tokens | OIDC provider |
| API Gateway/ingress | Validate tokens or forward them to the API | JWT authorizer |
| Java API | Verify context, apply business policies | Can this user view/edit the project? |
| Database | Enforce integrity and tenant boundaries | Composite foreign keys, RLS |
| Workload identity | Grant the function permissions to call other services | Service account, execution role |

A request with a valid token may still be unauthorized to read a project. A user who is a tenant member may still not be allowed to edit tasks in a project where they only hold VIEWER permission.

### What Should a Token Contain?

An OIDC access token typically includes claims such as:

- iss: the issuer that minted the token.
- sub: a stable subject identifier within the issuer's scope.
- aud: audience, the API or resource server permitted to accept the token.
- exp: token expiration timestamp.
- nbf: not-before timestamp when the token becomes valid, if used.
- scope or role claims: coarse-grained permissions granted under the identity provider contract.

Never use email as the primary identity key. Email addresses can change, be recycled, or remain unverified. Map internal users by the (issuer, subject) pair; the same sub string from two different issuers does not necessarily refer to the same person.

Tokens should not carry full project memberships if memberships change frequently. Stale role claims can persist until the token expires. For permissions requiring rapid revocation, query current membership/policy from a trusted data store or use an appropriate token lifetime/revocation strategy.

## 3. Choosing a Data Isolation Strategy for Multi-Tenancy

There are three common models:

| Model | Organization | Advantages | Trade-offs |
|---|---|---|---|
| Shared database, shared schema | All tenants share tables; each row has tenant_id | Low cost, simpler operations, convenient aggregate queries | Every query must be tenant-scoped; bug blast radius can span tenants |
| Shared database, schema-per-tenant | Each tenant has its own schema | Separates namespaces and schema-level permissions | Multi-schema migrations are complex; connections/search paths require control |
| Database-per-tenant | Each tenant has its own database | Strong isolation, independent backup/restore and key policies | Higher cost, more connections/secrets, complex operations |

For a project API with many moderately sized tenants, a shared schema with tenant_id is usually a practical starting point. Large tenants or those with strict compliance/isolation needs can be moved to dedicated databases under a hybrid model.

No model protects data automatically if the application misidentifies the tenant. Database-per-tenant still requires authenticating tenant routing and selecting the right credentials; shared schema requires strict query scoping and constraints.

### General Principles

- Every tenant-owned data table must have a tenant key or an explicit traceable relationship to a tenant.
- Every unique constraint must include tenant scope when uniqueness applies only within a tenant.
- Every read/write query must filter by tenant.
- Never infer tenant from an email domain or a client-supplied field without verifying membership.
- Never treat a tenant ID as proof of authorization; it is only a selector for the requested scope.
- Maintain dedicated migrations and tests when migrating a tenant from shared to isolated databases.

## 4. Designing the Relational Schema

This example uses PostgreSQL and UUIDs. The model includes:

- app_user: internal user mapped from an identity provider.
- tenant: workspace/organization.
- tenant_membership: a user's membership and role in a tenant.
- project: a resource belonging to a tenant.
- project_member: a user's permissions on a project.
- task: child data belonging to a project and tenant.

### Users and Tenant Membership Tables

~~~sql
CREATE TABLE app_user (
    id              UUID PRIMARY KEY,
    issuer          TEXT NOT NULL,
    subject         TEXT NOT NULL,
    email           TEXT,
    display_name    TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (issuer, subject),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED'))
);

CREATE TABLE tenant (
    id              UUID PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED'))
);

CREATE TABLE tenant_membership (
    tenant_id       UUID NOT NULL REFERENCES tenant(id),
    user_id         UUID NOT NULL REFERENCES app_user(id),
    role            VARCHAR(30) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id),
    CHECK (role IN ('TENANT_ADMIN', 'MEMBER', 'BILLING_ADMIN')),
    CHECK (status IN ('INVITED', 'ACTIVE', 'SUSPENDED', 'REMOVED'))
);

CREATE INDEX idx_membership_user_active
    ON tenant_membership (user_id, tenant_id)
    WHERE status = 'ACTIVE';
~~~

Email is not a unique identity in this example because users may change emails or authenticate through multiple identity providers. If business rules require unique emails within a tenant, add an appropriate constraint and define normalization/case-folding; do not assume emails are globally unique.

### Projects and Project Membership

~~~sql
CREATE TABLE project (
    tenant_id       UUID NOT NULL,
    id              UUID NOT NULL,
    name            VARCHAR(200) NOT NULL,
    created_by      UUID NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    version         BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, created_by)
        REFERENCES tenant_membership (tenant_id, user_id),
    CHECK (status IN ('ACTIVE', 'ARCHIVED', 'DELETED'))
);

CREATE TABLE project_member (
    tenant_id       UUID NOT NULL,
    project_id      UUID NOT NULL,
    user_id         UUID NOT NULL,
    role            VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, user_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES project (tenant_id, id),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES tenant_membership (tenant_id, user_id),
    CHECK (role IN ('OWNER', 'EDITOR', 'VIEWER')),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REMOVED'))
);

CREATE INDEX idx_project_member_user
    ON project_member (tenant_id, user_id, project_id);
~~~

Composite foreign keys ensure a project member must also be a tenant member of the same tenant. Storing only project_id and user_id without including tenant in the constraint could allow an application bug to create cross-tenant links.

When creating a project, the transaction should:
1. Verify the user has an ACTIVE membership in the tenant.
2. Insert the project.
3. Insert a project_member row for the creator with role OWNER.
4. Commit both changes in the same transaction.

### Tasks and Ownership

~~~sql
CREATE TABLE task (
    tenant_id       UUID NOT NULL,
    id              UUID NOT NULL,
    project_id      UUID NOT NULL,
    title           VARCHAR(300) NOT NULL,
    description     TEXT,
    owner_user_id   UUID,
    created_by      UUID NOT NULL,
    status          VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    version         BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES project (tenant_id, id),
    FOREIGN KEY (tenant_id, owner_user_id)
        REFERENCES tenant_membership (tenant_id, user_id),
    FOREIGN KEY (tenant_id, created_by)
        REFERENCES tenant_membership (tenant_id, user_id),
    CHECK (status IN ('OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED'))
);

CREATE INDEX idx_task_project_created
    ON task (tenant_id, project_id, created_at DESC, id);

CREATE INDEX idx_task_owner_status
    ON task (tenant_id, owner_user_id, status)
    WHERE owner_user_id IS NOT NULL;
~~~

Foreign keys guarantee the task and project share the same tenant, and that the owner and creator belong to that tenant. They do not guarantee the membership is still ACTIVE when the task is created or that the user still holds EDITOR rights; that belongs to authorization/transaction logic and can be reinforced with policies or triggers if needed.

### Why Are Composite Keys Useful?

Using only project_id as a foreign key prevents the database from catching a task whose tenant_id = A references a project belonging to tenant B. A composite foreign key enforces that the (tenant_id, project_id) pair must exist together.

This turns the database into the final integrity safeguard, even if a code path forgets to check the tenant.

## 5. Standardizing Permissions: RBAC, ABAC, and Ownership

**RBAC (Role-Based Access Control)** grants permissions by role. **ABAC (Attribute-Based Access Control)** evaluates attributes of the principal, resource, and context. Ownership is a specific relationship between a user and a resource.

Sample policy:

| Action | Tenant Admin | Project Owner | Editor | Viewer |
|---|---:|---:|---:|---:|
| View project | Yes | Yes | Yes | Yes |
| Edit project metadata | Yes | Yes | By policy | No |
| Manage project members | Yes | Yes | No | No |
| Create task | Yes | Yes | Yes | No |
| Edit any task | Yes | Yes | Yes | No |
| Edit task assigned to self | Yes | Yes | Yes | By policy |
| Delete project | Yes | Yes | No | No |

This table is illustrative. Define roles based on real business needs; avoid proliferating too many roles or relying on a single ADMIN role for everything.

### RBAC Alone Is Not Enough for Every Decision

A policy may need to check:
- Which tenant does the user belong to?
- Is the membership still ACTIVE?
- Does the project belong to that tenant?
- Does the user have a project membership?
- Is the user the owner of the task?
- Is the project/task ARCHIVED?
- Is the action permitted in the current state?

For instance, a user with the EDITOR role whose membership is no longer active must still be denied. A task may allow its owner to update personal fields like estimates while requiring editor rights to transition to DONE. That is a resource/action policy, not merely a role check.

### Default Deny

If no rule explicitly allows an action, deny it. Never assume a signed-in user has read access by default. When adding a new action, add the corresponding policy and tests; never let new actions inherit broad permissions automatically.

## 6. Separating Tenant Roles, Project Roles, and Object Ownership

Authorization decisions can be layered into three tiers:

1. **Tenant membership:** is the user allowed to participate in the tenant?
2. **Project membership:** is the user allowed to access the project and in what role?
3. **Object-level policy:** is the user allowed to perform the action on the specific task/project?

A tenant admin may be granted override access across project memberships per policy. However, do not allow every tenant MEMBER to read all projects by default if private projects exist.

A policy service can take:
- Actor: internally mapped user ID.
- Requested tenant ID.
- Resource: project/task and its current state.
- Action: READ, UPDATE, DELETE, ASSIGN.
- Context: membership, role, owner, workflow state.

Return an allow/deny decision with an internal reason code for auditing. Do not expose full policy details to the client if doing so would reveal the existence of resources in another tenant.

## 7. Validating JWT/OIDC in a Java API

The Java API should act as an OAuth2 Resource Server. The framework verifies signatures against the issuer/JWK, expiration, and required claims. Configuration must verify that the audience matches this API; not every valid JWT was issued for the current service.

Spring Security configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Configure the issuer in application configuration and add an audience validator per the API contract. Spring Resource Server with an issuer decoder validates the issuer and token expiration; add a dedicated audience validator if one is not already configured. Never write a custom JWT parser or merely base64-decode the payload and trust claims.

Configuration example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

issuer-uri must point to your real identity provider issuer. The illustrative URL is not a production endpoint.

### Mapping External Subject to Internal User

Use the iss + sub pair to look up the user:

~~~java
import java.util.UUID;

public record ExternalIdentity(String issuer, String subject) {
}

public record Actor(UUID userId) {
}
~~~

Resolver service:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public class ActorResolver {
    private final UserRepository users;

    public ActorResolver(UserRepository users) {
        this.users = users;
    }

    public Actor resolve(Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        AppUser user = users.findByIssuerAndSubject(issuer, subject)
                .orElseThrow(() -> new UnknownUserException());

        if (!user.isActive()) {
            throw new AccountDisabledException();
        }
        return new Actor(user.id());
    }
}
~~~

Never create a user merely because a request passes a userId in JSON. If auto-provisioning from an identity provider is supported, implement it through a verified issuer flow, invitation workflow, and explicit account-creation policy.

## 8. A Client-Supplied Tenant ID Does Not Mean the Client Has Access

APIs often receive the tenant ID in the path:

~~~http
GET /tenants/tenant-123/projects/project-456
~~~

The path parameter only states which tenant the client wants to access. The server must verify the actor is an active member of that tenant. Never take the tenant from:
- A client-supplied JSON body.
- Arbitrary headers like X-Tenant-Id without validation.
- Email domains.
- Unvalidated query parameters.

If a gateway injects tenant/user headers, the API may trust them only when the gateway validates the token, strips any client-supplied headers, and secures the gateway-to-service connection. In many systems, preserving and validating the access token directly in the API is easier to control.

### Never Trust Roles or Owner IDs from Request Bodies

A task creation payload might look like:

~~~json
{
  "title": "Review deployment",
  "ownerUserId": "user-123",
  "status": "DONE",
  "tenantId": "tenant-999"
}
~~~

If the API binds this payload directly to a database entity, a client can assign the task to another user, switch tenants, or mark the task DONE. This is mass assignment.

Use a request DTO containing only the fields clients are allowed to send:

~~~java
public record CreateTaskRequest(
        String title,
        String description,
        java.util.UUID assigneeUserId) {
}
~~~

The server assigns the tenant, creator, and initial status, and verifies the assignee has project access. Never bind request JSON directly to JPA entities.

## 9. Object-Level Authorization and IDOR

IDOR (Insecure Direct Object Reference) occurs when an API accepts an object ID and returns data without checking whether the caller has permission on that object.

Dangerous example:

~~~java
@GetMapping("/projects/{projectId}")
public Project getProject(@PathVariable UUID projectId) {
    return projectRepository.findById(projectId).orElseThrow();
}
~~~

UUIDs are harder to guess than sequential integers, but they are not authorization. Attackers can obtain IDs from logs, links, events, browser history, or another user sharing a URL.

The safe approach is querying scoped by tenant and actor policy:

~~~sql
SELECT p.tenant_id, p.id, p.name, p.status, p.version
FROM project p
JOIN tenant_membership tm
  ON tm.tenant_id = p.tenant_id
 AND tm.user_id = :actor_user_id
 AND tm.status = 'ACTIVE'
LEFT JOIN project_member pm
  ON pm.tenant_id = p.tenant_id
 AND pm.project_id = p.id
 AND pm.user_id = :actor_user_id
 AND pm.status = 'ACTIVE'
WHERE p.tenant_id = :tenant_id
  AND p.id = :project_id
  AND p.status <> 'DELETED'
  AND (
      tm.role = 'TENANT_ADMIN'
      OR pm.role IN ('OWNER', 'EDITOR', 'VIEWER')
  );
~~~

This query returns the project only when the actor is a tenant admin or a valid project member. If policy allows any tenant member to read PUBLIC projects, add that condition explicitly.

Apply the same principle to:
- GET by ID.
- PATCH/PUT/DELETE.
- Attachment downloads.
- Exports/reports.
- Search and list endpoints.
- Bulk operations.
- Nested resources such as tasks within a project.

Do not secure the detail endpoint while leaving list or export endpoints unprotected.

## 10. Java Service: Checking Membership and Resource Permissions

Centralize authorization in an application service or testable policy component. Controllers handle HTTP; services coordinate policies and business logic.

Example project read service:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProjectQueryService {
    private final TenantAccessService tenantAccess;
    private final ProjectRepository projects;
    private final ProjectPolicy policy;

    public ProjectQueryService(
            TenantAccessService tenantAccess,
            ProjectRepository projects,
            ProjectPolicy policy) {
        this.tenantAccess = tenantAccess;
        this.projects = projects;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    public ProjectView getProject(
            Actor actor,
            UUID tenantId,
            UUID projectId) {

        TenantMembership membership =
                tenantAccess.requireActiveMember(actor.userId(), tenantId);

        Project project = projects.findByTenantIdAndId(tenantId, projectId)
                .orElseThrow(ProjectNotFoundException::new);

        ProjectMembership projectMembership =
                projects.findMembership(tenantId, projectId, actor.userId())
                        .orElse(null);

        if (!policy.canRead(membership, project, projectMembership)) {
            throw new AccessDeniedException("Not allowed to read project");
        }

        return ProjectView.from(project);
    }
}
~~~

In production applications, combine queries scoped by tenant and actor where appropriate to reduce round trips and narrow the window between the authorization check and the read. If a policy depends on resource state, read the state and check permissions within the same transaction or directly in a query with the matching predicates.

Never return JPA entities directly. Response DTOs control which fields are exposed and prevent serializing internal relationships.

### Pure Java Policy

~~~java
public final class ProjectPolicy {
    public boolean canRead(
            TenantMembership tenant,
            Project project,
            ProjectMembership projectMember) {

        if (!tenant.isActive() || !project.isActive()) {
            return false;
        }
        if (tenant.role() == TenantRole.TENANT_ADMIN) {
            return true;
        }
        return projectMember != null
                && projectMember.isActive()
                && projectMember.role().canRead();
    }

    public boolean canEdit(
            TenantMembership tenant,
            Project project,
            ProjectMembership projectMember) {

        if (!tenant.isActive() || !project.isActive()) {
            return false;
        }
        if (tenant.role() == TenantRole.TENANT_ADMIN) {
            return true;
        }
        return projectMember != null
                && projectMember.isActive()
                && projectMember.role().canEdit();
    }
}
~~~

This policy is illustrative; enums and methods must match your domain. Never pass arbitrary client-supplied role strings into policies. Roles must be read from the database or verified claims under a trust model with clear lifetimes.

## 11. Safe Writes: Tenant Scope, Authorization, and Optimistic Locking

For updates, never:
1. Load an entity by ID alone.
2. Trust a new owner or tenant from the client.
3. Overwrite the entire object.

Instead:
- Obtain the actor from the verified security context.
- Verify tenant membership and project role.
- Allow updates only to allowlisted fields.
- Include the tenant ID in the UPDATE predicate.
- Use optimistic locking/versioning to prevent overwriting concurrent updates.
- Record an audit entry for sensitive actions.

Example SQL task update:

~~~sql
UPDATE task t
SET title = :title,
    description = :description,
    version = version + 1,
    updated_at = now()
WHERE t.tenant_id = :tenant_id
  AND t.id = :task_id
  AND t.version = :expected_version
  AND EXISTS (
      SELECT 1
      FROM project p
      WHERE p.tenant_id = t.tenant_id
        AND p.id = t.project_id
        AND p.status = 'ACTIVE'
  )
  AND EXISTS (
      SELECT 1
      FROM tenant_membership tm
      WHERE tm.tenant_id = t.tenant_id
        AND tm.user_id = :actor_user_id
        AND tm.status = 'ACTIVE'
        AND (
            tm.role = 'TENANT_ADMIN'
            OR EXISTS (
                SELECT 1
                FROM project_member pm
                WHERE pm.tenant_id = t.tenant_id
                  AND pm.project_id = t.project_id
                  AND pm.user_id = tm.user_id
                  AND pm.status = 'ACTIVE'
                  AND pm.role IN ('OWNER', 'EDITOR')
            )
        )
  );
~~~

If the update count is 0, the object may not exist in that tenant, the actor may lack permission, or the version may have changed. The API should decide whether to distinguish 404/403/409 or return 404 uniformly to avoid leaking object existence. Do not blindly treat an update count of 0 as a database error.

For assignments, verify the assignee is an active tenant/project member before updating. Composite FKs protect tenant consistency, but they do not enforce project membership if the assignee belongs to the tenant without participating in the project.

## 12. Authorization for List, Search, and Pagination

A common mistake is authorizing the detail endpoint while letting list endpoints leak data.

Every list/search query must scope by tenant and membership before paginating:

~~~sql
SELECT p.id, p.name, p.status, p.created_at
FROM project p
JOIN tenant_membership tm
  ON tm.tenant_id = p.tenant_id
 AND tm.user_id = :actor_user_id
 AND tm.status = 'ACTIVE'
LEFT JOIN project_member pm
  ON pm.tenant_id = p.tenant_id
 AND pm.project_id = p.id
 AND pm.user_id = :actor_user_id
 AND pm.status = 'ACTIVE'
WHERE p.tenant_id = :tenant_id
  AND (
      tm.role = 'TENANT_ADMIN'
      OR pm.role IN ('OWNER', 'EDITOR', 'VIEWER')
  )
  AND (p.created_at, p.id) < (:cursor_created_at, :cursor_id)
ORDER BY p.created_at DESC, p.id DESC
LIMIT :page_size;
~~~

Cursors should be bound to the filter/sort/tenant so another tenant's cursor cannot be replayed to leak data. You can sign cursors or store them server-side. Cap page size to prevent oversized queries.

With offset pagination, concurrent data changes can cause rows to duplicate or be skipped across pages. Keyset pagination is typically more stable for large datasets. Regardless of style, authorization predicates must apply to every request and page.

## 13. Indexing by Access Pattern and Tenant Key

In a shared schema, many queries lead with tenant_id. Indexes should reflect real access patterns:

| Access Pattern | Suggested Index |
|---|---|
| Look up project by tenant and ID | PK (tenant_id, id) |
| List project members by user | (tenant_id, user_id, project_id) |
| List newest tasks in a project | (tenant_id, project_id, created_at DESC, id) |
| List owner's tasks by status | (tenant_id, owner_user_id, status) |
| Find user's active memberships | Partial index (user_id, tenant_id) WHERE status='ACTIVE' |

Do not index every column. Indexes add write overhead, storage, and migration cost. Use query plans and production metrics to verify an index helps.

When tenant sizes vary widely, a very large tenant can create hot partitions or slow queries. You may need partitioning, dedicated databases, or per-tier workload isolation.

## 14. Row-Level Security as Defense in Depth

PostgreSQL Row-Level Security (RLS) restricts rows based on the tenant context in the database session/transaction. RLS reduces the blast radius if a query forgets a tenant filter, though it does not replace business authorization.

Example policy:

~~~sql
ALTER TABLE project ENABLE ROW LEVEL SECURITY;
ALTER TABLE project FORCE ROW LEVEL SECURITY;

CREATE POLICY project_tenant_isolation
ON project
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

If app.tenant_id has not been set, the expression evaluates to NULL and no rows match. The application database role must not be a superuser and must not have BYPASSRLS; FORCE RLS subjects table owners to the policy as well within PostgreSQL's rules. Always test using the actual runtime DB role.

### Setting Tenant Context per Transaction

With a connection pool, never use session-level settings that linger for the next request. Use SET LOCAL or set_config(..., true) inside a transaction:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

public final class TenantDatabaseContext {
    public void setTenant(Connection connection, UUID tenantId)
            throws SQLException {
        try (PreparedStatement statement =
                     connection.prepareStatement(
                             "select set_config('app.tenant_id', ?, true)")) {
            statement.setString(1, tenantId.toString());
            statement.execute();
        }
    }
}
~~~

The third argument true scopes the setting locally to the current transaction. The connection must be inside an active transaction; after commit/rollback, the local setting resets per PostgreSQL semantics. Never execute this on an autocommit connection expecting the context to persist for the next query.

The example RLS policy covers only the project table. Apply corresponding policies to every tenant-owned table such as project_member and task, each using a consistent tenant context. Project membership, ownership, and action permissions must still be checked by the application or additional DB policies.

## 15. Serverless: Preventing Tenant Context Leaks Across Invocations

Functions/containers can be reused across invocations. Dangerous mistakes include:
- Storing currentTenantId in a static mutable field.
- Using ThreadLocal without clearing it in a finally block.
- Reusing an entity manager or connection carrying a stale session setting.
- Caching permission decisions without tenant/user/resource in the key or without expiration.
- Dispatching async tasks to an executor without propagating security context safely.

Every invocation must build its context from the verified token/event. Never use environment variables to hold a request's tenant. Environment variables are for deployment configuration, never per-user state.

If using ThreadLocal for framework integration, set and clear the context in a filter/interceptor inside try/finally. Better yet, pass Actor/TenantContext explicitly into application services so dependencies remain visible and unit-testable.

### Warm Reuse and Authorization Caching

Caching memberships reduces queries but risks stale permissions after a user is removed or downgraded. If caching:
- Set short TTLs aligned with sensitivity.
- Invalidate on membership changes if rapid revocation is required.
- Include issuer/user, tenant, and scope/resource in the cache key.
- Never cache ALLOW decisions longer than policy changes are allowed to take effect.
- For financial or admin actions, consider reading current permissions directly from the store.

## 16. Event-Driven Workers and Actor Context

When an HTTP API emits events for workers, the end-user JWT usually should not be forwarded verbatim through a queue. Tokens may expire, leak in logs/messages, or create unwanted coupling.

An event can carry server-generated metadata:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "project.task.created",
  "tenantId": "tenant-123",
  "actor": {
    "userId": "user-456",
    "issuer": "https://identity.example.com/issuer",
    "subject": "subject-789"
  },
  "data": {
    "projectId": "project-1",
    "taskId": "task-9"
  }
}
~~~

Consumers must:
- Verify the event came from an authorized producer/service.
- Validate the schema and event type.
- Use a dedicated workload identity to access databases/queues.
- Treat the event's tenant ID as context to verify, not self-validating proof.
- Apply the appropriate business policy.
- Record the original actor in audit entries if acting on a user's behalf.
- Use event ID/idempotency keys to avoid duplicate processing.

If a worker performs an authorized system task, policy may rely on the service principal rather than re-checking the user's JWT. If the work must respect user permissions at execution time, define clearly whether authorization is checked at request acceptance or worker execution, since membership may have been revoked in between.

Never store raw access tokens inside events. If delegation is needed, use token exchange or short-lived credentials supported by the platform and identity provider.

## 17. Separating User Authorization from Workload IAM

A Java function may hold IAM permissions to read a database or publish to a queue, but those permissions do not dictate which user may view which rows.

Two distinct layers:

- **Workload IAM:** which cloud services and resources the function is allowed to call.
- **Application authorization:** what a user/tenant is allowed to do with specific business objects.

Examples:
- A Lambda execution role can read the Orders table.
- Application code must still scope queries by tenant/user.
- A Cloud Run service account can read Secret Manager.
- End users must not read secrets just because the service can read them.

Never pass an end user's cloud role or long-lived credentials through requests. The function uses its execution role/service account; the app uses the verified actor context to govern data access.

## 18. User Deletion, Membership Revocation, and Auditing

Deleting an account alters both data and access control, not just a single row.

Decisions to settle:
- When a user is suspended, are existing tokens still accepted until expiry?
- Does removing a membership revoke permissions immediately?
- Are tasks created by the user preserved for audit purposes?
- Are tasks assigned to the user reassigned?
- Can the user be re-invited to the tenant later?
- Which personal data must be deleted or anonymized under retention policies?
- Must audit records retain the actor ID or a pseudonymous reference?

Do not cascade-delete every project/task simply because a user leaves a tenant. Business data typically belongs to the tenant, not the creating user. Usually, keep created_by as a historical reference, delete or anonymize profile fields per policy, and revoke membership.

Audit logs should record actor, tenant, action, resource type/ID, outcome, timestamp, and correlation ID. Never log access tokens, passwords, or sensitive payloads.

## 19. API Design and Response Behavior

Key API rules:

- Return HTTP 401 when the token is missing or invalid.
- Return HTTP 403 when the actor is authenticated but lacks permission, provided distinguishing 403 vs. 404 does not leak resource existence.
- Return HTTP 404 for non-existent or invisible resources when policy requires preventing IDOR enumeration.
- Return HTTP 409 for business conflicts or optimistic lock conflicts.
- Never return stack traces, SQL, or policy internals to clients.
- Never expose internal fields such as tenant routing, secret references, or unauthorized audit metadata.

Returning 404 for out-of-scope objects reduces ID enumeration risk. Apply this consistently across GET, PATCH, DELETE, and nested resources.

### Preventing the API from Becoming a Confused Deputy

The service has access across multiple tenants. If a client supplies an unvalidated tenantId/resourceId, the service could inadvertently use its own broad privileges to access someone else's data. Always bind object queries to the authorized actor and tenant; never accept a resource identifier and read it arbitrarily with the service account.

## 20. Testing Authorization

Authorization tests must prove both allow and deny cases. A happy-path test where a user reads their own project will not catch IDOR bugs.

| Scenario | Expected Outcome |
|---|---|
| User A is an active member and project editor | Read/edit permitted per policy |
| User A is a viewer | Read succeeds, update denied |
| User B belongs to a different tenant | Cannot read or write project |
| User is suspended | Request denied |
| Membership was removed | Permissions revoked per policy |
| Path tenant ID differs from project's tenant | Not found / access denied |
| Client sends spoofed ownerUserId/tenantId | Server ignores or rejects |
| Wrong JWT audience | 401 |
| Untrusted/expired JWT issuer | 401 |
| Task owner no longer has tenant membership | Assignment rejected per policy |
| Cursor from another tenant | Cannot access the other tenant's data |
| Event with forged tenantId | Consumer rejects or quarantines |

### Unit Testing Policies

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ProjectPolicyTest {
    private final ProjectPolicy policy = new ProjectPolicy();

    @Test
    void viewerCanReadButCannotEdit() {
        TenantMembership member =
                TenantMembership.activeMember(TenantRole.MEMBER);
        Project project = Project.active();
        ProjectMembership viewer =
                ProjectMembership.active(ProjectRole.VIEWER);

        assertTrue(policy.canRead(member, project, viewer));
        assertFalse(policy.canEdit(member, project, viewer));
    }

    @Test
    void inactiveTenantMembershipDeniesAccess() {
        TenantMembership removed =
                TenantMembership.removed(TenantRole.MEMBER);

        assertFalse(policy.canRead(
                removed,
                Project.active(),
                ProjectMembership.active(ProjectRole.OWNER)));
    }
}
~~~

Factories here are domain-model test factories. Policy tests require no JWT, database, or cloud runtime.

### Integration Tests Against Cross-Tenant Access

Use a real test database or container:
1. Create tenant A and tenant B.
2. Create user A in tenant A and a project in tenant A.
3. Create user B in tenant B.
4. Invoke repositories/services as user B targeting project A.
5. Verify zero rows are returned and no mutations occur.
6. Test GET, list, update, delete, and export.
7. Run tests under the actual runtime database role if RLS is enabled.

Testing RLS as a database owner/superuser can yield false positives because those roles may bypass policies. Tests must run with the actual least-privilege application role.

### Property/Fuzz Tests

Generate random tenant/user/resource IDs and verify the invariant: no actor can read a row belonging to another tenant without explicit authorization. For bulk APIs, test lists mixing valid IDs with out-of-tenant IDs; the server must neither return unauthorized partial data nor perform side effects on denied items.

## 21. Data Model and Access Control Checklist

- [ ] Internal users are mapped by issuer + subject, not email as ID.
- [ ] Users can belong to multiple tenants via explicit membership records.
- [ ] Tenant memberships and project memberships track status and role clearly.
- [ ] Every tenant-owned resource has a tenant key or explicit tenant relationship.
- [ ] Composite foreign keys prevent cross-tenant associations.
- [ ] Unique constraints and indexes match access patterns and tenant scope.
- [ ] RBAC/ABAC/ownership rules are defined per action and resource.
- [ ] Default deny applies when no allow policy matches.
- [ ] JWT validation checks issuer, signature, expiry, and audience.
- [ ] Client-chosen tenant IDs always have membership verified.
- [ ] Object-level authorization applies to detail, list, update, delete, and export endpoints.
- [ ] Request DTOs prevent clients from mass-assigning tenant, role, creator, or internal status.
- [ ] Update queries include tenant predicates and optimistic locking where required.
- [ ] RLS is treated as defense in depth and tested with the runtime DB role.
- [ ] Connection pools never retain tenant context from prior invocations.
- [ ] Static mutable fields or uncleaned ThreadLocals are never used for actor/tenant state.
- [ ] Events never carry raw user access tokens; consumers verify producers and tenant context.
- [ ] Workload IAM is kept separate from user authorization.
- [ ] Membership revocation and account deletion follow clear policies.
- [ ] Audit logs exclude credentials and unnecessary PII.
- [ ] Positive, negative, cross-tenant, revocation, and RLS integration tests exist.

## Self-Check

1. What distinct questions do authentication and authorization answer?
2. Why is issuer + subject more stable than email for mapping users?
3. How should membership be modeled when one user belongs to multiple tenants?
4. How do composite foreign keys protect tenant boundaries?
5. How does RBAC differ from ABAC and ownership?
6. Why does a tenant ID in the URL not prove the caller has access to that tenant?
7. Why can IDOR still occur even when resource IDs are UUIDs?
8. Why must list/search queries also be scoped by tenant and actor?
9. What additional protection does RLS provide, and what does it not replace?
10. How can connection pools and warm instances leak tenant context?
11. Why should raw JWTs not be passed through queues to workers?
12. How does workload IAM differ from application authorization?
13. When a membership is revoked, how do stale caches or tokens affect permission decisions?
14. What integration tests are needed to prove cross-tenant access is prevented?

A secure serverless API requires a data model that explicitly represents users, tenants, memberships, and resource ownership; every request must be authenticated with a trusted identity and then authorized by tenant, action, and specific object. Composite constraints, tenant-scoped queries, RLS, workload IAM, and cross-tenant tests reinforce one another. When Java functions are reused across invocations, actor/tenant context must be constructed per request and never leak into the next.
