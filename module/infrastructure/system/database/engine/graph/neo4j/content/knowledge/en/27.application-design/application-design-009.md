# Considering GraphQL for Graph APIs and Controlling Query Costs

Neo4j is well suited for modeling highly connected data. A project management page might need project metadata, a task list, members, and completion status; a recommendation app might need to traverse multiple relationship hops. **GraphQL** lets clients declare the exact shape of data they want in a single request. However, allowing clients to request multiple branches of data also means the server must strictly govern **the number of nodes, relationships, intermediate rows, and actual queries executed**.

This lesson belongs to the **Application Design** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses Neo4j to organize a **property graph**, query nodes, relationships, and paths with Cypher, design indexes/constraints, and integrate via the Java Driver or Spring Data Neo4j. In this context, GraphQL is **an API-layer option**, not a replacement for Cypher or an automatic way to make graph queries faster.

After this lesson, you will be able to:

- Decide when GraphQL offers advantages over REST or specialized APIs.
- Design a GraphQL schema reflecting nodes, relationships, and relationship properties without exposing the full Neo4j structure.
- Identify **N+1** queries, fan-out, deeply nested queries, repeated aliases, and expensive aggregations.
- Apply depth limits, complexity budgets, pagination, row caps, timeouts, and tenant-scoped access control.
- Connect each GraphQL operation to Cypher/`EXPLAIN`/`PROFILE` and operational metrics.
- Implement a read resolver using Spring for GraphQL and `Neo4jClient`, then test correctness, authorization, and performance.

## 1. What Problem Does GraphQL Solve for Graph APIs?

Suppose a project detail screen needs:

~~~text
(:AppDemoUser {tenantId, userId})
       |
       | [:APP_MEMBER_OF {role, joinedAt}]
       v
(:AppDemoProject {tenantId, projectId, name})
       |
       | [:APP_HAS_TASK]
       v
(:AppDemoTask {tenantId, taskId, title, status, createdAt})
~~~

In this model:

- **Nodes** `AppDemoUser`, `AppDemoProject`, and `AppDemoTask` are identifiable entities.
- **Relationship** `APP_MEMBER_OF` links users to projects and carries properties `role` and `joinedAt`.
- **Relationship** `APP_HAS_TASK` links projects to tasks.
- `tenantId` defines organizational scope, not a property clients can arbitrarily pick to bypass authorization checks.

With REST, an application might call multiple endpoints, such as project details followed by tasks and members. With GraphQL, the client can request the required fields in one operation:

~~~graphql
query ProjectOverview($projectId: ID!, $taskLimit: Int!) {
  project(id: $projectId) {
    id
    name
    tasks(first: $taskLimit) {
      nodes {
        id
        title
        status
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
  }
}
~~~

The operation above works only if the server defines a matching schema and resolvers. GraphQL **does not inherently understand** the `AppDemoProject` label or `APP_HAS_TASK` relationship just from query syntax. The API layer must map them to data and enforce authorization, filtering, and pagination.

### 1.1. Benefits and Associated Costs

| Common Benefits | Costs to Accept |
| --- | --- |
| Clients select exact fields needed per screen. | Server must control which fields are accessible and each branch's cost. |
| One endpoint can return multiple linked entities. | Nested queries can explode query counts or scanned record counts. |
| Strongly typed schema supporting introspection and client tooling. | Requires managing versioning/deprecation, nullability, errors, and pagination contracts. |
| UI can evolve without creating a REST endpoint per data combination. | Added complexity for resolvers, caching, tracing, and complexity control. |
| Helpful when diverse clients need different data shapes. | Arbitrary operations are harder to cost-predict than fixed endpoints if left unbounded. |

**GraphQL is an API choice, not a mandatory goal.** If you only need a handful of fixed-shape operations, REST backed by tuned Cypher can be simpler, safer, and easier to cache.

## 2. When Should You Consider GraphQL?

GraphQL adds value when **clients have widely varying field-selection and relationship-composition needs**, such as web, mobile, and internal consoles sharing one domain. It also helps when a typed schema lets frontend teams discover and consume a clear API contract.

Conversely, a large-file export report API, sequential ingestion stream, heavy path-computing job, or fixed-sort search endpoint may fit REST, async jobs, or specialized APIs better.

| Requirement | Preferred Direction | Reason |
| --- | --- | --- |
| Multiple screens need different subsets of fields over the same connected data. | GraphQL with bounded resolvers. | Reduces proliferation of endpoint variants differing only in response shape. |
| Key lookups, simple CRUD, fixed responses. | Either REST or GraphQL; pick the simpler option. | GraphQL offers little advantage if clients don't need field selection. |
| Computing top-K paths, GDS algorithms, or exporting millions of rows. | Async job API / specialized endpoint. | Hard to guarantee interactive read latency and resource bounds. |
| Public API with many untrusted clients. | GraphQL **only with** strict bounds and fine-grained authz. | Clients can craft expensive queries that are still schema-valid. |
| Full-text/vector search, complex business filtering and pagination. | Dedicated resolver using suitable Cypher/indexes. | Never let clients compose arbitrary unbounded traversals. |

Never decide solely on "it's a graph, so we must use GraphQL." The real question is: **do clients need a flexible query contract, and can we govern the cost of that flexibility?**

## 3. From Property Graph to GraphQL Schema

GraphQL provides object types, fields, arguments, lists, inputs, and scalars. A hand-crafted schema can expose an **API model** without revealing every property stored in Neo4j.

~~~graphql
type Query {
  project(id: ID!): Project
  projects(first: Int!, after: String): ProjectConnection!
}

type Project {
  id: ID!
  name: String!
  openTaskCount: Int!
  tasks(first: Int!, after: String): TaskConnection!
  members(first: Int!, after: String): MembershipConnection!
}

type Task {
  id: ID!
  title: String!
  status: String!
}

type Member {
  id: ID!
  displayName: String!
}

type Membership {
  member: Member!
  role: String!
  joinedAt: String
}

type PageInfo {
  endCursor: String
  hasNextPage: Boolean!
}

type ProjectConnection {
  nodes: [Project!]!
  pageInfo: PageInfo!
}

type TaskConnection {
  nodes: [Task!]!
  pageInfo: PageInfo!
}

type MembershipConnection {
  nodes: [Membership!]!
  pageInfo: PageInfo!
}
~~~

This is **pure GraphQL SDL**, without resolver implementations. In production, add date/time scalars and status/role enums per your chosen library. `joinedAt: String` simplifies the example; UTC formatting, timezones, and nullability still require a clear contract.

### 3.1. Mapping Data Across Layers

| Neo4j Property Graph | GraphQL API | Principle |
| --- | --- | --- |
| `AppDemoProject.projectId` | `Project.id` | API IDs can differ from physical property names. |
| `AppDemoProject.name` | `Project.name` | Fields can come directly from node properties. |
| `(Project)-[:APP_HAS_TASK]->(Task)` | `Project.tasks` | Lists require authorization filtering, pagination, and deterministic ordering. |
| `(User)-[r:APP_MEMBER_OF]->(Project)` | `Project.members.nodes[].member` | Returns the associated user. |
| `r.role` and `r.joinedAt` | `Membership.role`, `Membership.joinedAt` | Relationship properties are represented as an API object. |
| `tenantId` | Usually **not open to arbitrary client input** | Tenant scope comes from authentication and authorization context. |

`Membership` in the GraphQL schema is an **API output type**. It does not require Neo4j to have a `:Membership` node. The resolver can construct this object from the `APP_MEMBER_OF` relationship and the `AppDemoUser` node. When a membership becomes an entity with an independent lifecycle, another model may be considered; that is a modeling decision, not a GraphQL requirement.

### 3.2. Do Not Force the API to Mirror the Entire Graph 1:1

If Neo4j stores `User → Group → Project → Task → Comment → Author`, you do not have to expose every hop as chained fields for arbitrary clients. Instead, you can create:

- `ProjectSummary` for list screens.
- `Project.tasks(first, after)` for a bounded single-level expansion.
- `searchTasks(query, first)` as a dedicated resolver backed by a full-text index.
- `relatedProjects(projectId, first)` as a controlled ranking/top-K operation.

GraphQL lets you model the API **around use cases**, rather than letting clients walk every relationship stored in Neo4j.

## 4. Two Common Implementation Approaches with Neo4j

### 4.1. Hand-Written Resolvers

A GraphQL server (such as **Spring for GraphQL** in a Java application) can invoke:

1. `Neo4jClient` or Neo4j Java Driver to run parameterized Cypher.
2. Spring Data Neo4j repositories for suitable aggregate operations.
3. Business services to enforce authorization, validate arguments, and manage transactions.

The advantage is exact control over Cypher, row counts, pagination, and security logic. The trade-off is designing resolvers, batching, mapping, and observability yourself.

### 4.2. Generating GraphQL Operations from a Neo4j Model

The Neo4j ecosystem includes libraries like **Neo4j GraphQL** (popular in JavaScript/TypeScript) that build APIs from type definitions and relationship mappings. Such libraries can generate queries, filters, or mutations for the declared model. However:

- **Directive syntax, authorization features, pagination, and query mechanics vary across library versions.**
- Auto-generated resolvers can still be expensive if the schema exposes high-degree relationship traversals.
- Never assume the library automatically understands tenant boundaries, authorization rules, or per-operation business costs.
- Auto-generated CRUD features are no excuse to expose every database label/property.

When choosing an auto-generating library, inspect the **actual generated Cypher**, resource usage, and exposed fields/operations for your deployed version. Whenever a business flow needs special write logic, replace it with an explicit resolver/service.

## 5. Why Can GraphQL Over a Graph Be Very Expensive?

GraphQL query cost does not depend solely on query text length. You must evaluate **each branch's width**, node degrees, and Neo4j aggregations/sorts.

Suppose an operation requests:

~~~graphql
query Dashboard {
  projects(first: 100) {
    nodes {
      id
      tasks(first: 50) {
        nodes {
          id
          comments(first: 10) {
            nodes {
              id
              text
            }
          }
        }
      }
    }
  }
}
~~~

If data is dense enough and every field hits its limit, the operation can traverse:

~~~text
100 projects
  x 50 tasks / project = 5,000 tasks
  x 10 comments / task = 50,000 comments
~~~

Just three list levels create the potential to return tens of thousands of objects. Even when each individual field cap "looks small," **their product** is large. Adding `members`, `attachments`, and aggregate fields increases cost further.

Never confuse **returned object count** with **actual relationships traversed**. A resolver may return 10 items after scanning hundreds of thousands of relationships to pick the top 10.

### 5.1. N+1 Queries

A naive resolver implementation:

~~~text
1 query: fetch 100 projects
100 queries: fetch tasks for each project
5,000 queries: fetch comments for each task
~~~

This is the **N+1** problem at the resolver layer. Total round-trips to Neo4j grow with the number of parent objects, even when each individual Cypher query is fast.

Ways to mitigate N+1:

- **Batch loading:** combine multiple `projectId` values into one task read using DataLoader or an equivalent mechanism.
- **Screen-oriented projections:** one controlled Cypher query returning summaries instead of nested resolvers.
- **Selective fetching:** read only client-requested fields, avoiding loading full SDN aggregates with unneeded relationships.
- **Per-request caching:** avoid re-reading the same node across branches; cross-request caching requires invalidation and tenant isolation policies.

However, batching **only reduces round-trips**, not total nodes/relationships processed. If a batched query expands millions of edges, it can still be very slow.

### 5.2. Fan-Out and Supernodes

Suppose a project has 200,000 tasks. A GraphQL query asks for only the 20 newest tasks. If Neo4j cannot leverage an appropriate entry point or data structure, it may still have to scan huge numbers of edges before sorting and limiting.

Similarly, a popular task with 1 million comments makes any expansion across `HAS_COMMENT` expensive. These characteristics are **data-distribution limits** that cannot be fixed by SDL alone.

### 5.3. Sorting and Aggregation

Fields like `totalComments`, `memberCount`, or `topContributors` can trigger counts/aggregations over large sets. For instance, `COUNT` across multiple joined branches can produce massive intermediate row counts if aggregations are not separated.

Field costs must be measured against **real workloads**: top-K can be cheap with precomputed data, yet costly if scanning and sorting every event before picking K.

### 5.4. GraphQL Aliases, Fragments, and Batched Operations

A client can use aliases:

~~~graphql
query RepeatedFields {
  a: projects(first: 50) { nodes { id name } }
  b: projects(first: 50) { nodes { id name } }
  c: projects(first: 50) { nodes { id name } }
}
~~~

This query is shallow yet requests three root branches. Fragments reuse fields in the query document without **reducing data retrieval cost**. Some servers allow multiple operations or batched HTTP requests depending on configuration; the gateway must govern **whole-request and per-user costs**, not just check single-branch depth.

## 6. Designing Enforceable Complexity Limits

There is no single "max depth" number suitable for all GraphQL APIs. Combine multiple protection layers:

| Defense Layer | How It Works | Limitation |
| --- | --- | --- |
| Depth limit | Reject operations nested deeper than allowed. | Does not block a shallow level with huge list sizes or aliases. |
| Complexity budget | Assign weights per field and multiply by max items. | Only an estimate; does not replace Neo4j performance metrics. |
| `first`/`pageSize` caps | Require positive integers and cap per collection. | Multiple collection levels still multiply cost. |
| Alias and field caps | Block excessive repeated fields/combinations per request. | Must resolve fragments, operations, and input variables. |
| Timeouts | Policy timeouts at gateway, resolver/driver, and transaction layers. | HTTP cancel does not guarantee immediate DB query termination unless wired properly. |
| Resource limits | Rate limits, concurrency caps, per-tenant request limits, result caps. | Needs fairness and monitoring for multi-connection abuse. |
| Operation allowlist | Clients may run only pre-approved operations, especially for internal apps. | Still requires authz checks, variable validation, and data-driven cost measurement. |

### 6.1. Illustrative Complexity Calculation Model

Suppose scalar fields have weight 1; `projects` has overhead 5 per call, `tasks` has overhead 3 with max items capped at `first`, and `comments` has overhead 4. A simple estimation formula is:

\[
C(\text{field}) =
w_{\text{field}} +
\text{maxItems(field)}\times
\sum C(\text{child fields}).
\]

For scalar fields, treat `maxItems = 1`. For lists, `maxItems` is the **server-accepted** limit, not a client-declared number if it exceeds the maximum.

Manual estimate example:

~~~text
projects(first: 20)
  tasks(first: 30)
    comments(first: 10)

Maximum comment items across the tree:
20 x 30 x 10 = 6,000
~~~

If the API enforces a budget equivalent to at most 1,000 items for interactive operations, the query above must be rejected or narrowed by the client. The number 1,000 is merely a **policy design example**, not a Neo4j or GraphQL default.

**Do not just sum field points:** a field named `shortestPath` or `allConnections` can perform massive work even when returning few rows. It needs dedicated weighting, path-length caps, algorithm rules, and specific permissions.

### 6.2. Clamp Inputs Right at the API Boundary

Suppose `tasks(first: Int!)` allows at most 50:

- Reject `0` or negative values instead of running meaningless queries.
- Reject values above 50, or apply a documented clamp policy consistently across validator and resolver.
- Cap text filter lengths, `ids` list sizes, and nested `where` input sizes.
- Never let users choose unbounded Cypher path lengths like `*1..` when the API should traverse only 2–3 hops.
- Protect queries over WebSocket/subscriptions too if enabled.

Compute complexity **after GraphQL binds variables**, because `first: $pageSize` could be 5 or 50. Inspecting raw query text while ignoring variables is insufficient.

## 7. Pagination from GraphQL to Neo4j

A list can mutate over time, so pagination requires **deterministic ordering**. Never return results relying on default relationship traversal order.

### 7.1. Offset: Simple but Limited

~~~cypher
MATCH (p:AppDemoProject {tenantId: $tenantId})
RETURN p.projectId AS id, p.name AS name
ORDER BY id ASC
SKIP $offset
LIMIT $pageSize;
~~~

`$offset` is a non-negative integer and `$pageSize` must be capped. At large offsets, Neo4j may still process/skip many preceding rows. If records are added/removed between requests, items can reappear or get skipped.

### 7.2. Keyset/Cursor: Better for Stable Lists

If `projectId` is unique **within a tenant** and sorted ascending:

~~~cypher
MATCH (p:AppDemoProject {tenantId: $tenantId})
WHERE p.projectId > $afterProjectId
RETURN p.projectId AS id, p.name AS name
ORDER BY id ASC
LIMIT $pageSize;
~~~

For the first page, the resolver can use a query without `p.projectId > $afterProjectId`; subsequent pages decode the cursor and validate inputs. Cursors should be **opaque tokens** bound to ordering and filters; never trust client-edited token contents for authorization decisions.

When sorting by `createdAt DESC`, add a unique tie-breaker such as `projectId` and construct the corresponding keyset predicate. If sort values mutate during pagination, cursors still do not create a consistent snapshot; define semantics acceptable to the product.

### 7.3. Fetching One Extra Row for `hasNextPage`

A common pattern: client asks for 20 records, resolver fetches up to **21** ordered rows, returns 20, and sets `hasNextPage = true` if the 21st row exists. There is no need to run `count(*)` over the entire dataset just to know if a next page exists.

For nested connections, pagination must be enforced **per parent**. A single `LIMIT 20` placed after expanding tasks for 10 projects does not mean each project gets up to 20 tasks; it caps the overall query rows and lets one project consume the entire budget.

## 8. Proper Batching Without Losing Per-Parent Bounds

Suppose `Project.tasks(first: 10)` runs across 30 projects. Instead of 30 Cypher round-trips, batch by the authorized list of `projectId` values.

Illustrative Cypher bounding items per project:

~~~cypher
UNWIND $projectIds AS projectId
MATCH (p:AppDemoProject {
  tenantId: $tenantId,
  projectId: projectId
})
CALL {
  WITH p
  MATCH (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
  WHERE t.tenantId = $tenantId
  RETURN t
  ORDER BY t.createdAt DESC, t.taskId ASC
  LIMIT $perParent
}
RETURN p.projectId AS projectId,
       collect({
         id: t.taskId,
         title: t.title,
         status: t.status
       }) AS tasks
ORDER BY projectId;
~~~

Here, the correlated subquery runs per parent `p`, placing `LIMIT $perParent` **inside**, rather than one global `LIMIT` after `UNWIND`. Correlated subquery syntax and behavior vary slightly across Neo4j/Cypher versions; verify on your running version.

**Points to handle in the resolver/DataLoader:**

1. If a project has no tasks, the subquery `MATCH` yields zero rows and that project drops from results. The DataLoader must return an **empty list** for valid keys with no tasks instead of misaligning result order.
2. `projectIds` must be size-capped, deduplicated, and authorized; never turn batching into an unbounded read.
3. When parents specify **different** `first`, cursor, or filter arguments, never merge them and ignore differences. Batch by equivalent parameter groups or choose a dedicated strategy.
4. Map results by **`projectId` key**, never relying on Neo4j return row order unless explicitly re-aligned to the DataLoader's input keys.
5. You may still need a total subquery-execution and total-row cap per request, even with per-parent limits.

Batching optimizes **round-trip counts**; controlling fan-out, sorting, and authorization inside each query remains mandatory.

## 9. Optimizing Cypher Behind Resolvers

A GraphQL schema might simply declare `projects(first: 20) { nodes { id name openTaskCount } }`, yet the real cost lies in the Cypher executed by the resolver.

### 9.1. Filter and Limit Parents Before Expanding

A query tailored for a list screen:

~~~cypher
MATCH (p:AppDemoProject {tenantId: $tenantId})
WITH p
ORDER BY p.projectId ASC
LIMIT $first
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
  WHERE t.tenantId = $tenantId AND t.status = 'OPEN'
  RETURN count(t) AS openTaskCount
}
RETURN p.projectId AS id,
       p.name AS name,
       openTaskCount
ORDER BY id ASC;
~~~

This query picks at most `$first` projects before counting tasks. It avoids counting tasks for **every project in the tenant** just to return the first few projects. Even so, if one project has hundreds of thousands of tasks, `count(t)` still scans many relationships; in that case, consider a controlled summary property.

`WHERE t.tenantId = $tenantId` enforces data scoping and reinforces the cross-tenant invariant. However, because it sits inside the expansion, never treat it as a substitute for authorization checks or proof that the engine avoided traversing cross-tenant edges.

### 9.2. Inspecting the Execution Plan

~~~cypher
EXPLAIN
MATCH (p:AppDemoProject {tenantId: $tenantId})
WITH p
ORDER BY p.projectId ASC
LIMIT $first
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
  WHERE t.tenantId = $tenantId AND t.status = 'OPEN'
  RETURN count(t) AS openTaskCount
}
RETURN p.projectId AS id, openTaskCount
ORDER BY id ASC;
~~~

Run `PROFILE` **on read queries** with representative test data to inspect rows, DB Hits, and resources per operator. Check:

- How many projects does Neo4j start from? Index/range seek or label scan?
- Are projects limited before expanding `APP_HAS_TASK`?
- How many tasks are traversed and discarded by `status`/`tenantId` filters?
- Do `count`, `Sort`, or `Top` dominate time/memory?
- How much worse is p95/p99 than the median for large tenants or high-degree projects?

`EXPLAIN` does not execute the query, whereas `PROFILE` **does execute the query**; never run `PROFILE` carelessly on production mutations. Operator names and stat columns vary across Neo4j versions and runtimes.

### 9.3. Indexes and Constraints Supporting Entry Points

In a learning environment:

~~~cypher
CREATE CONSTRAINT app_demo_project_key IF NOT EXISTS
FOR (p:AppDemoProject)
REQUIRE (p.tenantId, p.projectId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT app_demo_task_key IF NOT EXISTS
FOR (t:AppDemoTask)
REQUIRE (t.tenantId, t.taskId) IS UNIQUE;
~~~

Composite uniqueness constraints protect project and task keys within a tenant while backing lookups with indexes. Standard uniqueness constraints **do not** enforce property existence; validate payloads or evaluate node key/existence constraints per edition/version.

Do not add random indexes when `PROFILE` already locates parents via an index and slowness comes from relationship expansion. When the bottleneck is a supernode or huge task aggregation, consider precomputed summaries, time bounds, or model changes.

### 9.4. Materialized Counts and Aggregated Data

If a screen queries `openTaskCount` thousands of times per minute, consider storing `AppDemoProject.openTaskCount` and updating it when task status changes. In exchange:

- Count updates and task mutations must run in the same transaction when both live in Neo4j.
- Handle concurrent updates, retries, deletes, and backfills.
- Run reconciliation queries comparing summaries with source tasks and have a repair mechanism.

A GraphQL field that looks cheap because it reads a single property has simply shifted cost to the write path. Evaluate **total system cost**, not just one resolver's latency.

## 10. Spring for GraphQL + Neo4jClient: A Safer Resolver Example

In Java, **Spring for GraphQL** provides the GraphQL controller and data-fetching layer, while Spring Data Neo4j provides `Neo4jClient` to run Cypher. These two components serve distinct responsibilities.

Define a schema tailored for a list screen, intentionally **avoiding unbounded nested objects**:

~~~graphql
type Query {
  projects(first: Int!): [ProjectSummary!]!
}

type ProjectSummary {
  id: ID!
  name: String!
  openTaskCount: Int!
}
~~~

Java 17+ example:

~~~java
import java.security.Principal;
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

record ProjectSummary(String id, String name, int openTaskCount) {}

interface TenantScope {
    // Implementations must resolve verified tenant access from the authenticated principal.
    String requireTenant(Principal principal);
}

@Controller
public class ProjectGraphQlController {
    private final Neo4jClient neo4jClient;
    private final TenantScope tenantScope;

    public ProjectGraphQlController(
            Neo4jClient neo4jClient, TenantScope tenantScope) {
        this.neo4jClient = neo4jClient;
        this.tenantScope = tenantScope;
    }

    @QueryMapping
    public List<ProjectSummary> projects(
            @Argument int first, Principal principal) {
        if (first < 1 || first > 50) {
            throw new IllegalArgumentException(
                "first must be between 1 and 50");
        }

        // NEVER accept a client-supplied tenantId as an authorization boundary.
        String tenantId = tenantScope.requireTenant(principal);

        return neo4jClient.query("""
                MATCH (p:AppDemoProject {tenantId: $tenantId})
                WITH p
                ORDER BY p.projectId ASC
                LIMIT $first
                CALL {
                  WITH p
                  OPTIONAL MATCH
                    (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
                  WHERE t.tenantId = $tenantId
                    AND t.status = 'OPEN'
                  RETURN count(t) AS openTaskCount
                }
                RETURN p.projectId AS id,
                       p.name AS name,
                       openTaskCount
                ORDER BY id ASC
                """)
            .bind(tenantId).to("tenantId")
            .bind(first).to("first")
            .fetch()
            .all()
            .stream()
            .map(row -> new ProjectSummary(
                (String) row.get("id"),
                (String) row.get("name"),
                Math.toIntExact(
                    ((Number) row.get("openTaskCount")).longValue()
                )))
            .toList();
    }
}
~~~

**Assumptions and limits of the example:**

1. `TenantScope` is an illustrative contract only. **The application must implement it** from verified principals and permissions; never fall back to a default tenant for unauthenticated callers.
2. The database contains `AppDemoProject`, `AppDemoTask`, and `APP_HAS_TASK` per the lesson model. If empty, the query returns an empty list.
3. The server configures Spring for GraphQL, `Neo4jClient`, security, and transactions/drivers properly. This snippet is not a complete standalone Spring Boot application.
4. GraphQL `Int` is a 32-bit integer. `Math.toIntExact(...)` intentionally catches overflow if counts exceed that range; production schemas can use custom scalars/types if counts exceed 32 bits.
5. The resolver clamps `first` yet **does not replace** whole-operation complexity limits, cursor pagination, or timeouts.
6. The query counts tasks per selected project; if projects hold huge task counts, measure and consider summary materialization.
7. Test that cross-tenant data cannot be reached through corrupt links even when the starting node belongs to a valid tenant.

In production, invalid variables can be rejected at the GraphQL validation layer before reaching resolvers. Never return raw Neo4j errors or stack traces to clients; normalize errors with business codes and keep sensitive diagnostics in server logs.

### 10.1. Client GraphQL Query

~~~graphql
query Projects($first: Int!) {
  projects(first: $first) {
    id
    name
    openTaskCount
  }
}
~~~

Example variables:

~~~json
{"first": 20}
~~~

Unlike section 1's example, this list API **returns only summaries**, without opening arbitrary fields to drill into every task. That is an intentional design choice when performance and access control outweigh query flexibility.

## 11. Authorization: A Valid GraphQL Field Is Not Necessarily Readable

A GraphQL schema answers "does this field exist and what is its type?"—it **does not automatically answer** "is the current user allowed to see this field?"

### 11.1. Three Control Levels

| Level | Example Check | Where Enforced |
| --- | --- | --- |
| Operation | May the user view projects or run an admin mutation? | Gateway / controller / service. |
| Object / tenant | Do project, task, and member fall within authorized scope? | Inside data queries and/or authorization service. |
| Field / relationship | May the user see `member.email` or `membership.role`? | In field resolvers/projections; may require filtering or masking fields. |

A client could request a valid project and traverse into another tenant's tasks/relationships if the graph contains bad edges or resolvers omit checks. Every expansion step must preserve the **data-scope invariant**.

### 11.2. Never Rely on Input `tenantId` as Proof of Permission

Unsafe:

~~~graphql
query Unsafe($tenantId: ID!) {
  projectsForTenant(tenantId: $tenantId) {
    id
    name
  }
}
~~~

The operation above **illustrates a risky design if the server trusts the argument directly**. You can still accept `tenantId` as a selector when a user holds access to multiple tenants, provided the server verifies that tenant belongs to the user's authorized set. For single-tenant users, derive scope from identity/session rather than client input.

Likewise, a GraphQL mutation must never allow clients to alter roles, owners, or authorization properties on relationships simply because the schema exposes those fields.

### 11.3. Introspection and Error Messages

Introspection powers schema discovery tools; it can be restricted or adjusted on public APIs per policy. Still, **disabling introspection does not replace authorization**: attackers can still know or guess field names, so resolvers must always enforce permissions.

Never return internal Cypher, database names, PII, secrets, or stack-trace details in GraphQL error responses. Internal logs should include a correlation ID linking GraphQL failures down to Neo4j without logging sensitive payloads verbatim.

## 12. Mutations and Transaction Boundaries

GraphQL supports `mutation` operations. A mutation creating a project and its tasks must obey **business invariants and Neo4j transactions**, not just GraphQL syntax.

Illustrative SDL:

~~~graphql
input CreateTaskInput {
  id: ID!
  title: String!
}

input CreateProjectInput {
  id: ID!
  name: String!
  tasks: [CreateTaskInput!]!
}

type Mutation {
  createProject(input: CreateProjectInput!): ProjectSummary!
}
~~~

Sound service flow:

~~~text
Authenticate and authorize
         |
Validate task count, IDs, title lengths
         |
BEGIN Neo4j TRANSACTION
         |
Create Project (business key)
         |
Create Tasks + APP_HAS_TASK relationships
         |
Verify invariants and COMMIT
         |
Return written result
~~~

In Java/Spring, use `@Transactional` on the service backed by the Neo4j transaction manager. When a step fails, changes inside that transaction roll back. If sending emails, charging payments, or publishing to a broker, Neo4j transactions **do not cover external systems**; use outbox/idempotency or suitable integration mechanisms.

**GraphQL note:** one HTTP request does not automatically equal one Neo4j transaction spanning all resolvers. A GraphQL mutation can trigger multiple operations depending on server and library setup; define transaction boundaries in the service layer instead of inferring atomicity merely from sending one GraphQL operation.

For mutations that may be retried after disconnects around commit, use a stable **idempotency key**. Never assume rollback when the client loses the response; verify committed state before re-writing.

## 13. Controlling Authorization and Cost on Dynamic Queries

Auto-generated GraphQL filters can support comparisons/negations, nested OR/AND, and relationship filtering. While convenient, they let a short query string translate into a very complex Cypher query.

Multi-branch filter example:

~~~graphql
query FilteredProjects($first: Int!) {
  projects(first: $first) {
    id
    name
    openTaskCount
  }
}
~~~

This example intentionally keeps filtering simple to quantity only. If the API later adds inputs like:

~~~graphql
input ProjectFilter {
  nameContains: String
  taskStatus: String
  memberRole: String
  or: [ProjectFilter!]
  and: [ProjectFilter!]
}
~~~

then you must:

- Bound **condition counts** and **AND/OR nesting depth**.
- Cap list sizes and expensive string/wildcard operators.
- Combine server-enforced tenant/permission filters alongside client-requested filters.
- Maintain an allowlist of filterable/sortable properties and supporting indexes; never accept raw Cypher from clients.
- Profile the **final generated query**, not just inspect the GraphQL AST.

With code-generating GraphQL libraries, test policies for every filter/aggregation feature enabled. Features, directives, and syntax can change across library versions; never assume generated query shapes remain identical across releases.

## 14. End-to-End Observability from GraphQL to Cypher and Operational Budgets

When an API slows down, a metric saying "GraphQL response = 2 seconds" is not enough. Link operations to actual queries and workloads:

| Metric | Meaning |
| --- | --- |
| GraphQL operation name and type | Shows which screen or use case drives load. |
| Computed complexity/depth and executed field count | Detects overly wide/deep queries or branch growth. |
| Resolver invocation count and Neo4j call count | Reveals N+1 issues or ineffective batching. |
| Neo4j p50/p95/p99 latency | Separates DB slowness from resolver/network overhead. |
| Rows/DB Hits and expanded relationships on sample queries | Highlights fan-out, Sort/Aggregation, and missing/wrong indexes. |
| Returned bytes and object counts per level | Tracks over-fetching and serialization cost. |
| Rate-limit rejections, timeouts, canceled queries | Tracks effectiveness of resource guards and UX impact. |
| Controlled tenant/role metadata | Diagnoses load per scope without leaking cross-tenant data. |

Use a **correlation ID** to connect an HTTP GraphQL request to resolver logs and Neo4j queries. Never log raw query variables containing passwords, tokens, emails, private documents, or unnecessary user data. Store operation hashes/allowlisted names and sanitized parameters for observability.

### 14.1. Distinguish Timeouts at Each Layer

- **Gateway/HTTP timeout**: prevents holding client connections open too long.
- **Resolver/Java Driver timeout**: bounds query or transaction duration via your API stack.
- **Database and resource limits**: protects Neo4j against excessive concurrency, runaway transactions, or memory pressure.

An HTTP timeout only means the client stopped waiting; **it does not automatically stop database work** unless cancellation propagates cleanly. Monitor active Neo4j transactions and completion/termination rates as well.

### 14.2. When to Use Caching?

| Cache Level | Useful When | Risk |
| --- | --- | --- |
| Per-request DataLoader cache | The same node is read by multiple fields in one operation. | Scoped to a single request only; must respect permissions. |
| Response cache by operation + variables | Repeated read queries over rarely changing data. | Must include identity/tenant/permissions in the cache key or prove data is public. |
| Entity/field cache | Multiple screens read nearly static properties. | Invalidation when entities/relationships change; risk of stale data. |
| Materialized projection in Neo4j | Expensive aggregates/top-K where sync lag is acceptable. | Adds write overhead and requires consistency reconciliation. |

Never share cached responses containing private data across users or tenants merely because they executed the same GraphQL operation.

## 15. Test Plan for GraphQL APIs on Neo4j

An effective test suite validates **correct data, correct authorization, and rejection of overly expensive queries**. Never stop at unit-testing one resolver with three nodes.

| Test | Input / Scenario | Expected Result |
| --- | --- | --- |
| G01 | Query one valid project. | Returns exact nodes and fields; hides unpublished properties. |
| G02 | Non-existent or unauthorized project. | Returns policy-compliant result/error; never leaks another tenant's data. |
| G03 | Project with 0 tasks vs. thousands of tasks. | Pagination and `hasNextPage` behave accurately without exceeding limits. |
| G04 | Three-level nested list query with large `first`. | Complexity validator rejects or enforces published budget. |
| G05 | Multiple aliases invoking the same heavy field. | Total operation cost is summed and capped within budget. |
| G06 | 100 projects fetching tasks. | DataLoader/batching cuts round-trips without scrambling order/relationships. |
| G07 | Two parents using different cursors/filters. | Never shares mismatched results; each parent gets its exact page. |
| G08 | Query with deeply nested AND/OR filters. | Validation rejects excess depth; avoids running expensive Cypher. |
| G09 | Task linked to wrong tenant in test fixture. | Never returns cross-tenant task; alerts on data anomaly if applicable. |
| G10 | Mutation fails midway on bad data. | Transaction rolls back; no partial nodes/relationships committed. |
| G11 | Two mutations with same business ID. | Constraints/idempotency block duplicates; errors classified cleanly. |
| G12 | Client disconnects right at commit. | State reconciliation supported; never blindly assumes rollback and duplicates writes. |
| G13 | Project with very high relationship degree. | p95/p99 and resources stay within bounds, or request is properly rejected. |
| G14 | Account lacks permission for sensitive field. | Field hidden/blocked across every query path per policy. |
| G15 | Server encounters Cypher error. | Normalized GraphQL error returned; no internal query or PII exposed. |

### 15.1. Measure on Representative Data

Build at minimum these datasets:

1. Small tenant with a few projects and tasks.
2. Large tenant with many projects, tasks, and members.
3. Very crowded project (*supernode*) with task/comment counts far above median.
4. Data mutating concurrently while clients paginate.
5. Duplicate or cross-tenant relationships in test fixtures to verify resolver invariant checks.

Record **baselines** before and after adding batching, indexes, or limits: Neo4j query count, Rows/DB Hits, p95, p99, response bytes, CPU/memory, and business outputs. Fixing an N+1 bug might cut 101 queries down to 2, yet if the new query processes huge relationship counts, latency still will not improve proportionally.

### 15.2. Load-Test Real Operations

Do not benchmark only `projects(first: 1) { nodes { id } }`; sample weighted real client operations:

- Frequently accessed project lists.
- Project details with tasks and members.
- Filtered search and pagination.
- Permitted but expensive admin operations.
- Mutations updating tasks and relationships.

Compare peak throughput, timeout errors, impact on other queries sharing the database, and recovery after load spikes.

## 16. Common Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| "GraphQL returns only requested fields so it's automatically fast." | Neo4j may still expand, sort, and aggregate huge sets before returning a few fields. | Measure actual Cypher, Rows/DB Hits, and latency. |
| Bounding depth only. | Shallow queries with large `first` or many aliases are still expensive. | Combine complexity, breadth, pagination, and rate limits. |
| Putting `LIMIT` only at the end of a Cypher query. | Limits may apply after massive expansions/aggregations. | Select parents first, bound each collection, and profile plans. |
| Each field resolver calls the DB directly. | Causes N+1 / 1+N+M round-trips. | Use DataLoader, batched queries, and projections. |
| Batching then applying one `LIMIT` across all parents. | One parent hogs the page while others get starved. | Bound per parent via subqueries or equivalent. |
| Exposing every Neo4j relationship as a field. | Clients can traverse deeply, overload DB, or infer sensitive topology. | Design schemas per use case; block unneeded traversals. |
| Trusting client-supplied `tenantId`. | Risks cross-tenant reads/writes. | Enforce tenant authorization from identity at every expansion step. |
| Enabling generated CRUD without authz review. | Auto-generated ops may allow unauthorized field/edge mutations. | Configure permissions, bounds, and test every exposed op. |
| Caching by query text alone. | Identical queries return different data per identity/tenant/variables. | Include security context in cache keys and enforce invalidation. |
| Treating GraphQL mutations as distributed transactions. | External APIs/brokers do not roll back with Neo4j. | Design service transactions and idempotency/outbox. |
| Disabling introspection and calling it security. | Resolvers still run if callers know operation/field names. | Enforce authn/authz per operation, object, and field. |
| Using GraphQL for heavy synchronous graph analytics. | Multi-minute algorithms exhaust request resources. | Use async jobs with status polling and bounded results. |

## 17. Practice Exercises

**Exercise 1 — Choosing an API Architecture.** One app has just two fixed-response endpoints: look up a project by ID and create a task. Another app serves web, mobile, and admin clients needing different combinations of connected fields. Compare REST and GraphQL on flexibility, security, caching, cost observability, and development effort; recommend a choice for each case.

**Exercise 2 — Schema Design.** From the graph `User-[APP_MEMBER_OF {role, joinedAt}]->Project-[APP_HAS_TASK]->Task`, write SDL for `Project`, `TaskConnection`, and `MembershipConnection`. Explain why `Membership` in GraphQL does not have to be a Neo4j node.

**Exercise 3 — Estimating Fan-Out.** A query fetches 40 projects × 20 tasks/project × 12 comments/task. Compute the maximum comment objects. If the server budgets at most 3,000 comments/request, propose how to adjust the operation or enforce limits.

**Exercise 4 — Fixing N+1.** A resolver currently runs one query for 100 projects, then one task query per project. Describe how to use DataLoader and a batched query. Why does placing `LIMIT 10` at the end of the batch query not mean "10 tasks per project"?

**Exercise 5 — Multi-Tenant Authorization.** Project A belongs to tenant T1, yet due to corrupt data a task with `tenantId = T2` is linked via `APP_HAS_TASK`. Specify what checks the server must enforce when expanding from project to task, and write integration test cases ensuring no T2 data leaks.

**Exercise 6 — When to Use Summaries?** The GraphQL field `openTaskCount` is slow because one project has 300,000 tasks. Compare live counting against storing a pre-aggregated property on `Project`. Propose update, retry, and reconciliation strategies if storing the summary.

**Exercise 7 — Complexity Budget.** Assign weights to `projects`, `tasks`, `comments`, and scalars; write the estimation formula when `first` is a variable alongside aliases and fragments. Identify fields that cannot be accurately costed by depth alone.

**Exercise 8 — Pagination.** Write a Cypher query fetching the next page of Projects in a tenant ordered by `projectId ASC`, using `afterProjectId`. Analyze what happens if projects are added/deleted between pages and why cursors do not automatically create a data snapshot.

**Exercise 9 — From GraphQL to `PROFILE`.** An operation `project.tasks.comments` takes 4 seconds. List diagnostic steps across the gateway, resolver, driver, and Neo4j. Explain how to distinguish N+1 overhead from fan-out inside a single batched query.

**Exercise 10 — Mutations and Commit Failures.** A mutation creates one project with three tasks; Neo4j commits, but the client disconnects before receiving the response. Design an idempotency key and saved-state lookup strategy to prevent duplicates when the client retries.

## 18. Checklist for Taking a GraphQL API on Neo4j to Production

1. **Genuine need:** do multiple clients need flexible data shapes, or are REST/dedicated queries enough?
2. **Intentional schema:** expose only use-case fields and paths; map relationship properties to fitting API types.
3. **Authz before data:** authenticate identity, check tenant/object/field permissions, and never trust client params as authorization proof.
4. **Bounded costs:** depth, breadth/aliases, complexity, page size, filters, query timeouts, and concurrency all have explicit policies.
5. **Well-designed resolvers:** avoid N+1, batch by exact keys and params, and bound results **per parent** when needed.
6. **Measured Cypher:** appropriate indexes/constraints, `EXPLAIN`/`PROFILE` on representative data, mindful of fan-out and aggregations.
7. **Deterministic pagination:** stable ordering, validated cursors, and documented behavior under concurrent mutations.
8. **Safe mutations:** clear transactions, input validation, business keys, and idempotency on retries.
9. **Cross-layer observability:** operation name/hash, resolver counts, DB round-trips, Rows/DB Hits, p95/p99 latency, response bytes, and resource-guard rejections.
10. **Multi-dimensional testing:** data accuracy, multi-tenancy, corrupt node/edge fixtures, deep nesting, aliases, heavy load, and disconnect failures.
11. **Version alignment:** GraphQL server, Spring Data Neo4j/Java Driver, or Neo4j GraphQL library capabilities and syntax verified for deployed versions.

**Conclusion:** GraphQL lets clients request connected data in the exact shape they need, yet **being able to express a query does not mean it is cheap or permitted to run**. On Neo4j, design schemas around use cases, bound graph traversals and row counts, use proper resolvers and batching, enforce permissions at every hop, and measure the Cypher actually executed. Choose GraphQL only when its API flexibility outweighs the added cost of governing complexity, security, and operations.
