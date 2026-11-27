# Managing Authorization and Permission Inheritance Paths in an Organization

## 1. The Problem: One Permission Can Come from Many Graph Paths

In an organization, access to a document is not necessarily assigned directly to each employee. A person may belong to a **project group**, the group is assigned a **role**, higher roles inherit lower roles, and permissions on a **folder** may apply to child documents. Thus, the question "Can user U01 edit DOC1?" is actually a query over multiple conditional relationship paths.

Example of a permission-granting chain:

~~~text
U01 --MEMBER_OF--> G_DEV --ASSIGNED_ROLE--> EDITOR
EDITOR --INHERITS--> VIEWER
VIEWER --GRANTS {action:READ}--> PRJ
DOC1 --PART_OF--> PRJ
~~~

The chain above explains why U01 can read DOC1 even without a direct `GRANTS` edge from U01 to DOC1. However, if U01 has a **DENY** applying to DOC1, the final decision can flip to **not allowed**, regardless of how many grant paths exist.

This lesson belongs to the **Graph Applications** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. It connects the **property graph** model, **Cypher** path queries, indexes/constraints, query optimization, and permission checks from the **Neo4j Java Driver** or **Spring Data Neo4j** to build an explainable and testable access-control system.

**After this lesson, you will be able to:**

1. Translate organizational authorization requirements into nodes, relationships, and explicit query rules.
2. Distinguish permissions granted **directly**, via **groups**, via **role inheritance**, and via **resource scope**.
3. Compute *effective permission* under **default deny** and **explicit deny overrides grant** policies.
4. Query the **explanation path** showing why a permission is proposed, then check whether a negative deny path overrides it.
5. Integrate checks and mutations inside Java/SDN transactions without trusting a client-supplied `userId`.
6. Identify risks such as inheritance cycles, privilege escalation, cross-tenant leakage, stale caches, and N+1 queries.
7. Verify correctness using a fixture with an independent expected-results matrix.

> **Scope and principles:** This is an **application-layer authorization model** built on a Neo4j graph, **not** how the Neo4j DBMS internally implements `GRANT`/`DENY` for database roles. The specific policy in this lesson is explicitly defined for verifiability; do not treat it as a universal security standard for every organization. Examples target Neo4j 5+ and Java 17+; verify APIs against your actual versions.

## 2. From Basic RBAC to Hierarchical and Scoped RBAC

**RBAC (Role-Based Access Control)** assigns permissions by role rather than assigning every permission per user. With inheritance (*hierarchical RBAC*), a higher role receives the permissions of lower roles.

Example:

~~~text
MANAGER --> EDITOR --> VIEWER
AUDITOR -------------> VIEWER
~~~

In this lesson, the edge direction is:

`(childRole)-[:QA004_INHERITS]->(parentRole)`

Meaning:

- MANAGER has the permissions of MANAGER, EDITOR, and VIEWER.
- EDITOR has the permissions of EDITOR and VIEWER.
- AUDITOR has the permissions of AUDITOR and VIEWER.
- VIEWER does **not** automatically inherit permissions of EDITOR/MANAGER/AUDITOR.

Beyond roles, we consider **resource scope**. A `READ` permission granted on folder PRJ applies to DOC1 and DOC2 if both belong to PRJ:

~~~text
DOC1 --PART_OF--> PRJ --PART_OF--> ROOT
DOC2 --PART_OF--> PRJ --PART_OF--> ROOT
FIN1 --PART_OF--> FIN --PART_OF--> ROOT
~~~

`PART_OF` paths are traversed from the child resource **up** to parent resources to find grants/denies applied on ancestors. Granting permission on DOC1 does **not** automatically grant permission on folder PRJ or DOC2.

### 2.1. This Model Is Not Automatically ABAC

**ABAC (Attribute-Based Access Control)** also evaluates attributes like department, classification level, owner, time, approval state, or access device. A real system may combine RBAC and ABAC, but this lesson's fixture **only evaluates RBAC + resource tree + direct deny**. Checks such as "active employees only", "internal documents only", or "cannot approve own request" must be added explicitly and never assumed to be present in the Cypher.

## 3. Defining the Policy Before Writing Queries

To prevent results from depending on implicit assumptions, we adopt the following rules:

| Rule | Exact Meaning |
|---|---|
| **P1 — Default deny** | Without a valid grant path, **deny** |
| **P2 — Direct role** | Users can be assigned roles directly |
| **P3 — Group role** | Users can belong to groups, and groups are assigned roles |
| **P4 — Role inheritance** | Assigned roles inherit permissions from ancestors via `INHERITS` |
| **P5 — Resource inheritance** | A grant on a resource applies to itself and all `PART_OF` descendants |
| **P6 — Explicit deny** | A user's direct deny on a resource or ancestor **overrides** all grants |
| **P7 — Deny ALL** | A deny edge with `action='ALL'` blocks every requested action in that scope |
| **P8 — Independent actions** | `WRITE` does not imply `READ`; `APPROVE` does not imply `WRITE` |
| **P9 — No nested groups** | The fixture only supports one hop user → group → role |
| **P10 — Bounded depth** | Example queries traverse at most 5 `INHERITS` hops and 5 `PART_OF` hops |

**The model only includes direct DENYs from users**; there are no group/role denies yet. If the system requires group/role denies or time-based validity, extend the Cypher and test suite accordingly. Never assume those rules are already enforced.

In production, depth limits must be **a data invariant** enforced on writes. If the graph contains a 6-hop inheritance path while the query traverses 5, permission results can be wrong; never silently apply an arbitrary bound and call it a complete security policy.

### 3.1. Effective Permission Formula

For user `u`, action `a`, and resource `x`:

\[
\operatorname{allowed}(u,a,x)
=
\operatorname{hasGrant}(u,a,x)
\;\land\;
\neg \operatorname{hasDeny}(u,a,x)
\]

Where:

- `hasGrant` is true if there exists at least one role assigned to the user (directly or via a group) and an inheritance path to a role holding a grant for action `a` on `x` or an ancestor of `x`.
- `hasDeny` is true if the user has a deny edge for action `a` or `ALL` on `x` or an ancestor of `x`.

**Deny beats grant**, even if the grant has a shorter path or comes from a higher role. Do not use "most recent rule wins" or "shortest path wins" unless the policy explicitly defines that.

## 4. Property Graph Diagram for the Organization

~~~mermaid
flowchart LR
    U["QA004User"] -->|"MEMBER_OF"| G["QA004Group"]
    U -->|"ASSIGNED_ROLE"| R["QA004Role"]
    G -->|"ASSIGNED_ROLE"| R
    R -->|"INHERITS (child → parent)"| B["Ancestor QA004Role"]
    R -->|"GRANTS {action}"| P["QA004Resource"]
    B -->|"GRANTS {action}"| P
    D["Child QA004Resource"] -->|"PART_OF"| P
    U -->|"DENIES {action / ALL}"| D
~~~

| Label | Identifying Property | Example | Role |
|---|---|---|---|
| `QA004User` | `userId` | U01, U02 | Authenticated application identity |
| `QA004Group` | `groupId` | G_DEV | Organizational/project group |
| `QA004Role` | `roleId` | VIEWER, EDITOR | Permission bundle and inheritance node |
| `QA004Resource` | `resourceId` | DOC1, PRJ | Protected object |

| Relationship | Direction | Properties | Meaning |
|---|---|---|---|
| `QA004_MEMBER_OF` | User → Group | *(none)* | User belongs to group |
| `QA004_ASSIGNED_ROLE` | User/Group → Role | *(none)* | Subject is assigned role |
| `QA004_INHERITS` | Child role → Parent role | *(none)* | Permission inheritance |
| `QA004_PART_OF` | Child resource → Parent resource | *(none)* | Resource scope hierarchy |
| `QA004_GRANTS` | Role → Resource | `action` | Allows action at scope |
| `QA004_DENIES` | User → Resource | `action` | Denies action at scope |

The `QA004` prefix keeps practice statements from colliding with labels/relationships of other models. However, this **does not guarantee** safety if a real database happens to use the same names; therefore, run only on a test database.

### 4.1. Modeling Decisions You Cannot Skip

- **A role is not a user:** a user can hold multiple roles, and a role can belong to multiple users.
- **A group is not a role:** organizational restructuring can update memberships without changing permission definitions.
- **The resource tree is a directed graph:** child → parent, extensible to a DAG when business rules allow multiple scopes; if so, you must handle duplicate paths and inheritance semantics.
- **Action is a controlled value:** `READ`, `WRITE`, `APPROVE`, not arbitrary strings passed from the UI.
- **Do not use Neo4j internal node IDs as durable authorization keys:** use constrained business IDs to avoid depending on storage identifiers that may change on export/restore.

## 5. Fixture with Answer Key: Six Employees, Four Roles, Six Resources

### 5.1. Users and Initial Roles

| User | Name | Direct Assignment | Group | Expected Effective Roles |
|---|---|---|---|---|
| U01 | An | *(none)* | G_DEV → EDITOR | EDITOR, VIEWER |
| U02 | Binh | MANAGER | *(none)* | MANAGER, EDITOR, VIEWER |
| U03 | Chi | *(none)* | G_AUDIT → AUDITOR | AUDITOR, VIEWER |
| U04 | Dung | VIEWER | *(none)* | VIEWER |
| U05 | Em | EDITOR | *(none)* | EDITOR, VIEWER |
| U06 | Giang | *(none)* | *(none)* | *(empty)* |

### 5.2. Permission Scopes

Role grants:

| Grant-Holding Role | Action | Scope | Propagated Scope |
|---|---|---|---|
| VIEWER | READ | PRJ | PRJ, DOC1, DOC2 |
| EDITOR | WRITE | PRJ | PRJ, DOC1, DOC2 |
| MANAGER | APPROVE | PRJ | PRJ, DOC1, DOC2 |
| AUDITOR | READ | FIN | FIN, FIN1 |

Direct denies:

| User | Denied Action | Scope | Effect |
|---|---|---|---|
| U01 | ALL | DOC2 | Cannot READ/WRITE/APPROVE DOC2 despite having EDITOR |
| U05 | WRITE | DOC2 | Can still READ DOC2, but cannot WRITE DOC2 |

**DOC1** and **DOC2** live under PRJ; **FIN1** lives under FIN. Both PRJ and FIN belong to ROOT, yet **there is no grant on ROOT**. Consequently, VIEWER cannot read FIN1 merely because both sit in the same organization.

### 5.3. Expected Authorization Matrix

| User | DOC1 READ | DOC1 WRITE | DOC1 APPROVE | DOC2 READ | DOC2 WRITE | FIN1 READ |
|---|---|---|---|---|---|---|
| **U01** (EDITOR via group) | Yes | Yes | No | **No: DENY ALL** | **No: DENY ALL** | No |
| **U02** (MANAGER) | Yes | Yes | Yes | Yes | Yes | No |
| **U03** (AUDITOR via group) | Yes | No | No | Yes | No | **Yes** |
| **U04** (VIEWER) | Yes | No | No | Yes | No | No |
| **U05** (EDITOR) | Yes | Yes | No | Yes | **No: DENY WRITE** | No |
| **U06** (no role) | No | No | No | No | No | No |

This is an **independent answer key** to verify queries, not a table derived from trial runs. Columns represent **independent** actions: for example, a user allowed to WRITE is not automatically allowed to APPROVE.

## 6. Creating Practice Data: Constraints and Nodes

> **Safety:** Run the statements below only in a lab database without real data sharing the `QA004` prefix. Never run cleanup snippets before verifying the exact target database.

### 6.1. Reset Fixture When Re-Running in the Lab

~~~cypher
MATCH (n)
WHERE n:QA004User
   OR n:QA004Group
   OR n:QA004Role
   OR n:QA004Resource
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa004_user_id IF EXISTS;
DROP CONSTRAINT qa004_group_id IF EXISTS;
DROP CONSTRAINT qa004_role_id IF EXISTS;
DROP CONSTRAINT qa004_resource_id IF EXISTS;
~~~

Depending on your Cypher client, run each `DROP CONSTRAINT` individually if the tool does not accept multiple statements in one command. `DETACH DELETE` is destructive, so use it only on a verified fixture.

### 6.2. Create Business-Key Constraints

~~~cypher
CREATE CONSTRAINT qa004_user_id IF NOT EXISTS
FOR (u:QA004User)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa004_group_id IF NOT EXISTS
FOR (g:QA004Group)
REQUIRE g.groupId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa004_role_id IF NOT EXISTS
FOR (r:QA004Role)
REQUIRE r.roleId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa004_resource_id IF NOT EXISTS
FOR (r:QA004Resource)
REQUIRE r.resourceId IS UNIQUE;
~~~

`IS UNIQUE` prevents creating two nodes with the same business key when the property **exists**; it does not automatically require every node to possess an ID. In production authorization systems, enforce both key presence and data type using edition-supported constraints and validation workflows.

### 6.3. Create Six Users, Two Groups, Four Roles, Six Resources

~~~cypher
UNWIND [
  {id:'U01', name:'An'},
  {id:'U02', name:'Binh'},
  {id:'U03', name:'Chi'},
  {id:'U04', name:'Dung'},
  {id:'U05', name:'Em'},
  {id:'U06', name:'Giang'}
] AS row
MERGE (u:QA004User {userId:row.id})
SET u.fullName=row.name;
~~~

~~~cypher
UNWIND [
  {id:'G_DEV', title:'Development group'},
  {id:'G_AUDIT', title:'Audit group'}
] AS row
MERGE (g:QA004Group {groupId:row.id})
SET g.title=row.title;
~~~

~~~cypher
UNWIND ['VIEWER','EDITOR','MANAGER','AUDITOR'] AS id
MERGE (:QA004Role {roleId:id});
~~~

~~~cypher
UNWIND [
  {id:'ROOT', kind:'ORG', title:'Organization'},
  {id:'PRJ', kind:'FOLDER', title:'Project A'},
  {id:'DOC1', kind:'DOC', title:'Design'},
  {id:'DOC2', kind:'DOC', title:'Plan'},
  {id:'FIN', kind:'FOLDER', title:'Finance'},
  {id:'FIN1', kind:'DOC', title:'Payroll'}
] AS row
MERGE (r:QA004Resource {resourceId:row.id})
SET r.kind=row.kind, r.title=row.title;
~~~

**Answer check:** **18 nodes** total across the four fixture labels: 6 users + 2 groups + 4 roles + 6 resources.

## 7. Creating Inheritance and Grant/Deny Relationships

### 7.1. Role Inheritance: Child Inherits Parent

~~~cypher
UNWIND [
  {child:'EDITOR', parent:'VIEWER'},
  {child:'MANAGER', parent:'EDITOR'},
  {child:'AUDITOR', parent:'VIEWER'}
] AS link
MATCH (child:QA004Role {roleId:link.child})
MATCH (parent:QA004Role {roleId:link.parent})
MERGE (child)-[:QA004_INHERITS]->(parent);
~~~

### 7.2. Assign Roles Directly to Three Users

~~~cypher
UNWIND [
  {user:'U02', role:'MANAGER'},
  {user:'U04', role:'VIEWER'},
  {user:'U05', role:'EDITOR'}
] AS link
MATCH (u:QA004User {userId:link.user})
MATCH (r:QA004Role {roleId:link.role})
MERGE (u)-[:QA004_ASSIGNED_ROLE]->(r);
~~~

### 7.3. Assign Roles Through Groups

~~~cypher
UNWIND [
  {user:'U01', group:'G_DEV'},
  {user:'U03', group:'G_AUDIT'}
] AS link
MATCH (u:QA004User {userId:link.user})
MATCH (g:QA004Group {groupId:link.group})
MERGE (u)-[:QA004_MEMBER_OF]->(g);
~~~

~~~cypher
UNWIND [
  {group:'G_DEV', role:'EDITOR'},
  {group:'G_AUDIT', role:'AUDITOR'}
] AS link
MATCH (g:QA004Group {groupId:link.group})
MATCH (r:QA004Role {roleId:link.role})
MERGE (g)-[:QA004_ASSIGNED_ROLE]->(r);
~~~

### 7.4. Resource Tree: Child Points to Parent

~~~cypher
UNWIND [
  {child:'PRJ', parent:'ROOT'},
  {child:'DOC1', parent:'PRJ'},
  {child:'DOC2', parent:'PRJ'},
  {child:'FIN', parent:'ROOT'},
  {child:'FIN1', parent:'FIN'}
] AS link
MATCH (child:QA004Resource {resourceId:link.child})
MATCH (parent:QA004Resource {resourceId:link.parent})
MERGE (child)-[:QA004_PART_OF]->(parent);
~~~

### 7.5. Four Grants

~~~cypher
UNWIND [
  {role:'VIEWER', action:'READ', scope:'PRJ'},
  {role:'EDITOR', action:'WRITE', scope:'PRJ'},
  {role:'MANAGER', action:'APPROVE', scope:'PRJ'},
  {role:'AUDITOR', action:'READ', scope:'FIN'}
] AS row
MATCH (role:QA004Role {roleId:row.role})
MATCH (scope:QA004Resource {resourceId:row.scope})
MERGE (role)-[:QA004_GRANTS {action:row.action}]->(scope);
~~~

### 7.6. Two Direct Denies

~~~cypher
MATCH (u:QA004User {userId:'U01'})
MATCH (doc:QA004Resource {resourceId:'DOC2'})
MERGE (u)-[:QA004_DENIES {action:'ALL'}]->(doc);
~~~

~~~cypher
MATCH (u:QA004User {userId:'U05'})
MATCH (doc:QA004Resource {resourceId:'DOC2'})
MERGE (u)-[:QA004_DENIES {action:'WRITE'}]->(doc);
~~~

### 7.7. Reconcile the Graph Before Checking Permissions

~~~cypher
MATCH (n)
WHERE n:QA004User OR n:QA004Group
   OR n:QA004Role OR n:QA004Resource
RETURN count(n) AS fixtureNodes;
~~~

**Answer check:** `fixtureNodes=18`.

~~~cypher
MATCH ()-[r]->()
WHERE type(r) STARTS WITH 'QA004_'
RETURN type(r) AS relType, count(r) AS amount
ORDER BY relType;
~~~

| relType | amount |
|---|---:|
| QA004_ASSIGNED_ROLE | **5** |
| QA004_DENIES | **2** |
| QA004_GRANTS | **4** |
| QA004_INHERITS | **3** |
| QA004_MEMBER_OF | **2** |
| QA004_PART_OF | **5** |

Total **21 relationships**. If any count differs, inspect the fixture and relationships before interpreting security outputs. Here `ASSIGNED_ROLE=5` comprises three edges from users and two edges from groups.

## 8. Step 1: Retrieve Direct and Group-Assigned Roles

First distinguish **assigned roles** from **inherited roles**.

~~~cypher
MATCH (u:QA004User {userId:$userId})
OPTIONAL MATCH (u)-[:QA004_ASSIGNED_ROLE]->(direct:QA004Role)
WITH u, collect(DISTINCT direct) AS directRoles
OPTIONAL MATCH (u)-[:QA004_MEMBER_OF]->
               (:QA004Group)-[:QA004_ASSIGNED_ROLE]->
               (groupRole:QA004Role)
WITH directRoles + collect(DISTINCT groupRole) AS allRoles
UNWIND allRoles AS role
RETURN DISTINCT role.roleId AS assignedRole
ORDER BY assignedRole;
~~~

Running with `$userId='U01'`: **EDITOR**. With U02: **MANAGER**. With U03: **AUDITOR**. With U06: **0 rows**, because no roles are assigned.

**Note:** a role can arrive from multiple groups; `DISTINCT` avoids duplicate display rows. However, the **number of paths** still matters for auditing: a role granted via two groups represents two grant sources to account for during revocation.

### 8.1. Why Not Concatenate Role Names in a String?

Never store role names as a CSV string on a user property and use `CONTAINS` to infer permissions. That makes hierarchy maintenance, group revocation, and grant-path explanation brittle. Directed relationships let Cypher walk explicitly from subjects to permission sources.

## 9. Step 2: Compute Role Inheritance Closure

For role MANAGER, traverse **0 or more** `INHERITS` edges to retrieve itself and all ancestor roles:

~~~cypher
MATCH (u:QA004User {userId:'U02'})
      -[:QA004_ASSIGNED_ROLE]->(seed:QA004Role)
MATCH path=(seed)-[:QA004_INHERITS*0..5]->
           (effective:QA004Role)
RETURN DISTINCT effective.roleId AS effectiveRole
ORDER BY effectiveRole;
~~~

**Answer for U02:** EDITOR, MANAGER, VIEWER.

`*0..5` has two meanings:

- `0` edges: the role itself is effective. Omitting `0` would prevent MANAGER from **receiving grants assigned directly to MANAGER**.
- Up to `5` edges: sample test depth bound; production must enforce valid hierarchy depth rather than treating `5` as a silent assumption.

For U03 via group G_AUDIT:

~~~cypher
MATCH (u:QA004User {userId:'U03'})
      -[:QA004_MEMBER_OF]->(:QA004Group)
      -[:QA004_ASSIGNED_ROLE]->(seed:QA004Role)
MATCH (seed)-[:QA004_INHERITS*0..5]->
      (effective:QA004Role)
RETURN DISTINCT effective.roleId AS effectiveRole
ORDER BY effectiveRole;
~~~

**Answer for U03:** AUDITOR, VIEWER. U03 can read project documents via VIEWER and finance documents via AUDITOR, but cannot WRITE because U03 does not inherit EDITOR.

## 10. Step 3: Find Inherited Resource Scopes

A grant on PRJ applies to both DOC1 and DOC2 because both sit under PRJ. For DOC1:

~~~cypher
MATCH path=(doc:QA004Resource {resourceId:'DOC1'})
           -[:QA004_PART_OF*0..5]->
           (scope:QA004Resource)
RETURN scope.resourceId AS scopeId,
       length(path) AS stepsToScope
ORDER BY stepsToScope;
~~~

| scopeId | stepsToScope |
|---|---:|
| DOC1 | 0 |
| PRJ | 1 |
| ROOT | 2 |

For FIN1, the corresponding result is **FIN1, FIN, ROOT**. A WRITE grant on PRJ **cannot** apply to FIN1 because there is no `FIN1 → ... → PRJ` path.

### 10.1. Inheritance Direction Cannot Be Reversed Arbitrarily

Because the edge `(DOC1)-[:PART_OF]->(PRJ)` exists, a grant on **PRJ** flows down to **DOC1**. You cannot infer from a grant on DOC1 that the subject has permissions on PRJ or sibling documents in the same folder.

A reversed traversal direction can silently over-grant permissions; tests must include both **positive** and **negative** path cases.

## 11. Complete Cypher Authorization Decision Query

This is the core query combining direct/group roles, role inheritance, resource scope, and deny override. Pass `$userId`, `$resourceId`, and `$action` from a trusted server layer.

~~~cypher
MATCH (u:QA004User {userId:$userId})
MATCH (target:QA004Resource {resourceId:$resourceId})

OPTIONAL MATCH
  (u)-[:QA004_ASSIGNED_ROLE]->(direct:QA004Role)
WITH u, target, collect(DISTINCT direct) AS directRoles

OPTIONAL MATCH
  (u)-[:QA004_MEMBER_OF]->
  (:QA004Group)-[:QA004_ASSIGNED_ROLE]->
  (viaGroup:QA004Role)
WITH u, target,
     directRoles + collect(DISTINCT viaGroup) AS seeds

WITH u, target,
     any(seed IN seeds WHERE EXISTS {
       MATCH (seed)-[:QA004_INHERITS*0..5]->
             (effective:QA004Role)
       MATCH (effective)-[grant:QA004_GRANTS]->
             (scope:QA004Resource)
       MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
       WHERE grant.action = $action
     }) AS hasGrant,
     EXISTS {
       MATCH (u)-[deny:QA004_DENIES]->
             (scope:QA004Resource)
       MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
       WHERE deny.action IN [$action, 'ALL']
     } AS hasDeny

RETURN u.userId AS userId,
       target.resourceId AS resourceId,
       $action AS action,
       hasGrant,
       hasDeny,
       hasGrant AND NOT hasDeny AS allowed;
~~~

**Example parameters:**

~~~json
{"userId":"U01","resourceId":"DOC1","action":"READ"}
~~~

Expected logical result:

| userId | resourceId | action | hasGrant | hasDeny | allowed |
|---|---|---|---|---|---|
| U01 | DOC1 | READ | true | false | **true** |

For U01/DOC2/READ: `hasGrant=true`, `hasDeny=true`, `allowed=false`. For U06/DOC1/READ: `hasGrant=false`, `hasDeny=false`, `allowed=false`.

### 11.1. Why Does the Query Use EXISTS?

- `EXISTS { MATCH ... }` returns **true/false** without materializing every grant path.
- `any(seed IN seeds ...)` checks whether **at least one** assigned role produces a valid grant.
- `collect(DISTINCT ...)` limits role duplication when a user belongs to multiple groups.
- Denies are evaluated **independently** of grants, then precedence is applied in the final boolean expression.
- Users with no roles have an empty `seeds` list and `hasGrant=false`; missing roles must never be treated as a fallback error that grants access.

### 11.2. When User or Resource Does Not Exist

The first two `MATCH` clauses can return **0 records** if `userId` or `resourceId` does not exist. **The application must treat 0 records as DENY**, never defaulting to true or assigning ad-hoc "guest" access.

In external APIs, consider returning errors that do not reveal whether a resource exists (403/404 per threat model) to prevent **resource enumeration**. Internal audit logs can record detailed reasons, while public responses must adhere to information-disclosure policy.

### 11.3. Intentional Boundaries Set in This Lesson

- Role inheritance and resource ancestry are capped at 5 edges.
- Group membership is 1 level only; nested groups are not traversed.
- Denies are assigned directly to users; role/group denies are not handled.
- No conditional permissions by time, IP, device, or document classification.
- Cypher checks only the application policy model. Neo4j DBMS RBAC and API call paths may enforce independent checks.

These are boundaries **to document in design and tests**, not gaps to ignore.

## 12. Verifying Grant/Deny Scenarios Case by Case

| Request | Grant Reason | Any Deny? | Decision |
|---|---|---|---|
| U01 READ DOC1 | U01 → G_DEV → EDITOR → VIEWER → READ PRJ; DOC1 ∈ PRJ | No | **ALLOW** |
| U01 WRITE DOC1 | EDITOR → WRITE PRJ | No | **ALLOW** |
| U01 READ DOC2 | VIEWER → READ PRJ | **ALL on DOC2** | **DENY** |
| U01 WRITE DOC2 | EDITOR → WRITE PRJ | **ALL on DOC2** | **DENY** |
| U02 APPROVE DOC1 | MANAGER → APPROVE PRJ | No | **ALLOW** |
| U03 READ FIN1 | G_AUDIT → AUDITOR → READ FIN; FIN1 ∈ FIN | No | **ALLOW** |
| U03 WRITE DOC1 | No WRITE grant | No | **DENY** |
| U05 READ DOC2 | EDITOR → VIEWER → READ PRJ | Deny applies only to WRITE | **ALLOW** |
| U05 WRITE DOC2 | EDITOR → WRITE PRJ | **WRITE on DOC2** | **DENY** |
| U06 READ DOC1 | No roles | No | **DENY** |

To avoid confounding "resource exists" with "resource is accessible", every case in this table must use **existing users and resources**; add separate negative tests for non-existent IDs.

### 12.1. Testing a Deny on a Parent Scope

If a user has a deny `ALL` on PRJ, that deny also applies to DOC1/DOC2. Not because the `DENIES` relationship copies itself downward, but because the query checks whether **the target has a `PART_OF` path up to the denied scope**.

**Do not mutate denies in a fixture undergoing concurrent tests** if you want the Section `5.3` matrix to stay intact. To experiment, use a test transaction and roll back or restore the fixture before the next test case.

## 13. Tracing "Why Was Permission Granted?"

Audit systems often need **the granting path**, not just true/false. For U01 → DOC1 → READ:

~~~cypher
MATCH (u:QA004User {userId:'U01'})
      -[:QA004_MEMBER_OF]->(g:QA004Group)
      -[:QA004_ASSIGNED_ROLE]->(seed:QA004Role)
MATCH rolePath=(seed)-[:QA004_INHERITS*0..5]->
               (role:QA004Role)
MATCH (role)-[grant:QA004_GRANTS {action:'READ'}]->
      (scope:QA004Resource)
MATCH resourcePath=
      (target:QA004Resource {resourceId:'DOC1'})
      -[:QA004_PART_OF*0..5]->(scope)
RETURN g.groupId AS sourceGroup,
       [r IN nodes(rolePath) | r.roleId] AS rolePath,
       [r IN nodes(resourcePath) | r.resourceId] AS scopePath,
       grant.action AS action;
~~~

**Answer:**

| sourceGroup | rolePath | scopePath | action |
|---|---|---|---|
| G_DEV | [EDITOR, VIEWER] | [DOC1, PRJ] | READ |

This path is **grant evidence**, **not the final decision**. A user deny could override that grant; to explain a denial, query `QA004_DENIES` separately.

Example query finding a deny path:

~~~cypher
MATCH (u:QA004User {userId:'U01'})
      -[deny:QA004_DENIES]->
      (scope:QA004Resource)
MATCH path=(target:QA004Resource {resourceId:'DOC2'})
           -[:QA004_PART_OF*0..5]->(scope)
WHERE deny.action IN ['READ','ALL']
RETURN deny.action AS blockedAction,
       scope.resourceId AS denyScope,
       [r IN nodes(path) | r.resourceId] AS scopePath;
~~~

**Answer:** `blockedAction='ALL'`, `denyScope='DOC2'`, `scopePath=['DOC2']`.

In real systems, expose detailed path explanations only to authorized admins/auditors; never return internal group names, role names, graph structure, and organizational policies to a denied user.

## 14. Java Driver: Checking Permissions Before Editing a Document

The Neo4j Java Driver lets you run parameterized Cypher inside a transaction. An example service can keep the Section 11 query as constant `AuthQueries.POLICY_CYPHER`:

~~~java
public final class AuthQueries {
    private AuthQueries() {}

    // Verbatim policy Cypher from Section 11, no string interpolation.
    public static final String POLICY_CYPHER = """
        MATCH (u:QA004User {userId:$userId})
        MATCH (target:QA004Resource {resourceId:$resourceId})
        OPTIONAL MATCH
          (u)-[:QA004_ASSIGNED_ROLE]->(direct:QA004Role)
        WITH u, target, collect(DISTINCT direct) AS directRoles
        OPTIONAL MATCH
          (u)-[:QA004_MEMBER_OF]->
          (:QA004Group)-[:QA004_ASSIGNED_ROLE]->
          (viaGroup:QA004Role)
        WITH u, target,
             directRoles + collect(DISTINCT viaGroup) AS seeds
        WITH u, target,
             any(seed IN seeds WHERE EXISTS {
               MATCH (seed)-[:QA004_INHERITS*0..5]->
                     (role:QA004Role)
               MATCH (role)-[g:QA004_GRANTS]->
                     (scope:QA004Resource)
               MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
               WHERE g.action=$action
             }) AS granted,
             EXISTS {
               MATCH (u)-[d:QA004_DENIES]->
                     (scope:QA004Resource)
               MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
               WHERE d.action IN [$action,'ALL']
             } AS denied
        RETURN granted AND NOT denied AS allowed
        """;
}
~~~

**Note:** This constant returns only the `allowed` column; the `RETURN` in Section 11 also returned `hasGrant` and `hasDeny`. Both queries are **decision-equivalent**, not identical in column projection. If the policy changes, update a single canonical implementation in production code and protect against drift with tests.

### 14.1. Read-Only Permission Check Helper

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class GraphAuthorization {
    private GraphAuthorization() {}

    public static boolean can(
            Driver driver, String database,
            String authenticatedUserId,
            String resourceId, String action) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> {
                var result = tx.run(
                    AuthQueries.POLICY_CYPHER,
                    Values.parameters(
                        "userId", authenticatedUserId,
                        "resourceId", resourceId,
                        "action", action
                    )
                );

                // 0 records when user/resource does not exist => deny.
                return result.hasNext()
                    && result.single().get("allowed").asBoolean();
            });
        }
    }
}
~~~

Before calling, **validate `action` against an enum/allowlist** (`READ`, `WRITE`, `APPROVE`) and derive `authenticatedUserId` from a backend-verified token/session, **never** from a client-supplied JSON body such as `{"userId":"U02"}`.

### 14.2. Combining Check and Mutation in One Transaction

To avoid patterns like:

~~~text
HTTP A: canWrite(...) => true
HTTP B: revokePermission(...)
HTTP A: editDocument(...) in a separate transaction
~~~

place both the authorization check and the document update inside the **same write transaction** when business rules require it:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class DocumentWriter {
    public static void rename(
            Driver driver, String database,
            String authenticatedUserId,
            String resourceId, String newTitle) {

        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {

            session.executeWrite(tx -> {
                var decision = tx.run(
                    AuthQueries.POLICY_CYPHER,
                    Values.parameters(
                        "userId", authenticatedUserId,
                        "resourceId", resourceId,
                        "action", "WRITE"
                    )
                );
                if (!decision.hasNext() ||
                    !decision.single().get("allowed").asBoolean()) {
                    throw new SecurityException("Access denied");
                }

                long updated = tx.run("""
                    MATCH (doc:QA004Resource {
                      resourceId:$id, kind:'DOC'
                    })
                    SET doc.title=$title
                    RETURN count(doc) AS modified
                    """, Values.parameters(
                        "id", resourceId,
                        "title", newTitle
                    ))
                    .single().get("modified").asLong();

                if (updated != 1L) {
                    throw new IllegalArgumentException(
                        "Document not found"
                    );
                }
                return null;
            });
        }
    }
}
~~~

**What is right here:** check and write share the same transaction; if denied, no update commits. The `executeWrite` callback may retry on transient errors, so never send emails, debit accounts, or emit non-idempotent events inside the callback.

**Important limitation:** sharing one transaction **does not completely eliminate concurrent revocation races**. A transaction checking permissions before another transaction commits a policy change may still need policy versioning/locking or serialization rules depending on your threat model. For sensitive operations, define decision point-in-time, policy locking/versioning, and revocation consistency.

## 15. Spring Data Neo4j: Repositories Do Not Enforce Organizational Permissions Automatically

An SDN entity only maps nodes and relationships; it **does not automatically understand** rules `P1–P10`. Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("QA004Resource")
public class ProtectedResource {
    @Id
    private String resourceId;
    private String title;
    private String kind;

    protected ProtectedResource() {}

    public String getResourceId() { return resourceId; }
    public String getTitle() { return title; }
    public String getKind() { return kind; }
}
~~~

A `Neo4jRepository<ProtectedResource,String>` can still read objects by ID if the backend calls that method with sufficiently privileged database credentials. **Simply having `@Node`/`@Relationship` or `@PreAuthorize("isAuthenticated()")` does not mean per-document permissions were checked.**

### 15.1. Service Example Using Neo4jClient

You can execute the same policy Cypher via `Neo4jClient` and wrap both the decision and document update in a Spring transaction:

~~~java
import java.util.Map;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SdnDocumentService {
    private final Neo4jClient client;

    public SdnDocumentService(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public void rename(String authenticatedUserId,
                       String resourceId, String title) {

        boolean allowed = client.query(
                AuthQueries.POLICY_CYPHER)
            .bindAll(Map.of(
                "userId", authenticatedUserId,
                "resourceId", resourceId,
                "action", "WRITE"
            ))
            .fetchAs(Boolean.class)
            .mappedBy((ts, record) ->
                record.get("allowed").asBoolean())
            .one()
            .orElse(false);

        if (!allowed) {
            throw new SecurityException("Access denied");
        }

        long modified = client.query("""
                MATCH (d:QA004Resource {
                  resourceId:$resourceId, kind:'DOC'
                })
                SET d.title=$title
                RETURN count(d) AS modified
                """)
            .bind(resourceId).to("resourceId")
            .bind(title).to("title")
            .fetchAs(Long.class)
            .mappedBy((ts, record) ->
                record.get("modified").asLong())
            .one()
            .orElse(0L);

        if (modified != 1L) {
            throw new IllegalArgumentException(
                "Document not found"
            );
        }
    }
}
~~~

`@Transactional` must be managed by the proper `Neo4jTransactionManager`/SDN configuration. Avoid mixing a raw `driver.session().executeWrite(...)` inside a Spring transaction and assuming both roll back together. Likewise, never call `repository.save(...)` on an entity hydrated without its relationships unless you have verified its graph-saving behavior.

**Operational requirement:** read/export/download code paths, full-text search, background jobs, and admin endpoints must also pass through policy checks or equivalent controls. Protecting only `rename` while leaving `findAll()` returning the whole graph is an authorization vulnerability.

## 16. Neo4j DBMS Privileges vs. Application Permissions

There are **two distinct security layers**:

| Layer | What It Governs | Example |
|---|---|---|
| **Neo4j DBMS RBAC** | Which databases, labels, properties, or procedures a Bolt account can access | App service account can run `MATCH`/`WRITE` per granted DB roles |
| **Application graph authorization** | Whether employee U01 may view/edit DOC1 per organizational roles | U01 via G_DEV → EDITOR, denied on DOC2 |

If a backend uses **one Neo4j service account** for all users, Neo4j sees only that database principal; the database does not know who U01 or U02 is unless the application passes the authenticated identity and evaluates policy.

**Architecture requires defense in depth:**

- Give the Neo4j service account **least-privilege** permissions for its business queries.
- Never allow end users to connect to Bolt with backend credentials.
- Never expose an "execute arbitrary Cypher" endpoint under the same service account.
- Allow only authorized services/workflows to modify role/group/grant/deny graphs.
- Enforce resource access rules across **all relevant read/write paths**.
- Configure Neo4j database `GRANT`/`DENY` policies independently per version/edition; **do not confuse** them with `QA004_DENIES` edges.

Never claim "we have graph RBAC" is sufficient if any application query path bypasses `hasDeny` or trusts a caller-supplied ID.

## 17. Cyclic Inheritance Paths: Detecting and Preventing at the Source

Cycles in `INHERITS` are an administration bug. Example:

~~~text
MANAGER → EDITOR → VIEWER → MANAGER
~~~

Such a cycle allows VIEWER to gain MANAGER permissions backwards around the loop, causing **privilege escalation**. In a resource tree, a `PART_OF` cycle turns folders into mutual ancestors and propagates permissions incorrectly.

### 17.1. Query to Detect Cycles in the Fixture

~~~cypher
MATCH path=(r:QA004Role)
           -[:QA004_INHERITS*1..5]->(r)
RETURN r.roleId AS cycleStart,
       [n IN nodes(path) | n.roleId] AS roleCycle
LIMIT 20;
~~~

~~~cypher
MATCH path=(r:QA004Resource)
           -[:QA004_PART_OF*1..5]->(r)
RETURN r.resourceId AS cycleStart,
       [n IN nodes(path) | n.resourceId] AS scopeCycle
LIMIT 20;
~~~

**Fixture answer:** both queries return **0 records**. If a cycle is detected in production, fix the permission structure rather than raising `LIMIT` or capping traversal to hide the bug.

### 17.2. Preventing Cycles When Adding New Edges

Before creating `child-[:INHERITS]->parent`, verify **whether `parent` already has a path back to `child`**. If so, the new edge creates a cycle. The same applies to `PART_OF`.

When multiple admins make concurrent updates, checking paths in one transaction and writing in another creates a **race condition**. Use transactions with appropriate synchronization/locking, post-write invariant checks, and change auditing; never rely solely on a standalone `WHERE NOT EXISTS`.

**Other invariants to enforce:** resources must not span tenants outside policy, groups must not be granted over-privileged roles, every node must have a unique ID, and inheritance depths must not exceed documented query bounds.

## 18. Revoking Permissions: Fast to Grant, Must Be Certain to Revoke

Two mechanisms carry different semantics:

1. **Revoke membership:** deleting `(u)-[:MEMBER_OF]->(g)` removes all roles coming from that group unless the user receives the same permission via another path.
2. **Add DENY:** blocks an action/resource even when other grant paths remain; suited to urgent exceptions, though it requires auditing and exception hygiene.

Test on an **isolated transaction/fixture**:

~~~cypher
MATCH (u:QA004User {userId:'U01'})
      -[m:QA004_MEMBER_OF]->
      (g:QA004Group {groupId:'G_DEV'})
DELETE m;
~~~

After deleting membership, U01 has no role from G_DEV, so DOC1 READ and WRITE become **DENY by default deny**, even while the DOC2 deny edge remains.

**Note:** This statement mutates the fixture. If used in a test case, roll back or re-seed before verifying the Section `5.3` matrix.

### 18.1. Stale Caches and Revocation Effective Time

If the API caches `canRead(U01,DOC1)=true` for 10 minutes, revoking the group in Neo4j **does not automatically expire** that cache. For near-immediate revocation, track policy versions, use event-driven invalidation, keep TTLs very short, or query live on sensitive paths.

Points to account for:

- Cache keys should include **user, action, resource, and policy/tenant version**, not just resource ID.
- Updating membership, role inheritance, grants, denies, or resource parents can invalidate many prior decisions at once.
- In-flight requests and background jobs may hold older policy snapshots.
- In a cluster, manage read-after-write consistency when policy changes and auth checks occur back-to-back.
- Never skip a denial check simply because the cache misses or errors; **fail closed** per security requirements.

## 19. Multi-Tenant: Never Let Graph Paths Cross Customer Boundaries

The fixture has one ROOT organization and therefore no tenant isolation yet. In multi-tenant SaaS, nodes belong to different companies. If two tenants share role name `EDITOR` or resource `DOC1`, querying by ID without tenant scoping risks cross-tenant privilege leakage.

An extended model needs:

~~~text
User, Group, Role, and Resource all carry tenantId
Unique business key: (tenantId, localId)
MEMBER_OF / ASSIGNED_ROLE / INHERITS / PART_OF edges
only connect within the authorized tenant.
~~~

### 19.1. Example Tenant-Scoped Identity Lookup

~~~cypher
MATCH (u:User {
  tenantId:$tenantId,
  userId:$authenticatedUserId
})
MATCH (r:Resource {
  tenantId:$tenantId,
  resourceId:$resourceId
})
RETURN u.userId AS userId,
       r.resourceId AS resourceId;
~~~

This snippet illustrates only the **starting** condition; labels `User`/`Resource` differ from the `QA004` fixture and are **not enough** to enforce full policy. A real authorization query must ensure **every role, group, grant, deny, and ancestor** belongs to the right tenant, not just the starting two nodes.

**Write negative tests:** if a user in tenant A passes a `resourceId` from tenant B, the result must be DENY even when role names match and buggy data created a cross-tenant edge.

### 19.2. Context-Dependent Action Rules

A company may allow `APPROVE` only when the approver is not the author, the document status is `PENDING`, and the request occurs during shift hours. That is **ABAC and separation of duties**, which role MANAGER alone does not enforce.

Encode business predicates in both the decision check and the write transaction, and test every state transition. Never check `hasRole('MANAGER')` alone and permit all approvals.

## 20. Querying the List of Resources a User Can View

Checking one resource with `EXISTS` is straightforward; a "All documents I can view" screen is harder because you must determine candidates, filter denies, and paginate.

**Anti-pattern:** fetching all DOCs and calling `can(...)` from Java in a loop:

~~~java
// Anti-pattern example: easily causes N+1 round trips.
for (String resourceId : allDocumentIds) {
    if (GraphAuthorization.can(
            driver, db, userId, resourceId, "READ")) {
        visible.add(resourceId);
    }
}
~~~

With 10,000 documents, this can trigger 10,000 extra queries. Moreover, fetching all documents before filtering in the application increases **over-fetch** risk.

### 20.1. Batched Query Approach

A controllable workflow:

1. Retrieve candidate document IDs matching business filters/sorting/pagination.
2. For a small batch of IDs, run **one Cypher query** evaluating permissions per ID (e.g., `UNWIND $ids`, subqueries, and Section 11 policy).
3. Return only items where `allowed=true`, preserving page order and accurate total count semantics.
4. If you need a full `pageSize` of **authorized documents**, do not simply `LIMIT 20` documents **before** permission filtering and treat it as "20 visible items per page". You may need a query over the authorized set or controlled batched cursor fetching.
5. Cap maximum items evaluated per call and measure `Rows`, `DB Hits`, and response bytes.

Large systems may use **materialized access views**, policy-versioned bitmaps/caches, or ACL-synchronized search architectures, provided they maintain fast revocation and reconciliation so denied documents never leak.

### 20.2. Correctness Before Speed

Optimizing an authorization query down to 2 ms while returning a **false ALLOW** is a security flaw, not a performance win. Before caching or precomputing closures, build regression tests covering deny precedence, role/group changes, and tenant isolation.

## 21. Optimizing Cypher and Schema for Large Permission Graphs

### 21.1. Use IDs and Indexes Instead of Scanning Names

Constraints on `userId`, `groupId`, `roleId`, and `resourceId` enable indexed entry lookups. In production, identify entities by normalized business keys rather than display names, which can collide or change.

~~~cypher
EXPLAIN
MATCH (u:QA004User {userId:'U01'})
RETURN u.userId AS id;
~~~

Verify that the planner uses the corresponding index/constraint. Never conclude from "we have constraints" that every permission query is fast; most execution cost often lies in subsequent edge expansions.

### 21.2. Limit Fan-Out and Depth by Policy

A user in hundreds of groups, each with hundreds of deeply inheriting roles and multi-ancestor resources, can generate huge numbers of duplicate paths. To bound cost:

- Enforce role hierarchies as a **DAG** with an explicit maximum depth.
- Keep resource scopes as a tree or controlled DAG with zero cycles.
- Use `EXISTS` when only a boolean is required; enumerate full paths only for bounded audits.
- Use `DISTINCT` when path multiplicity adds no semantic meaning.
- Monitor group/role/resource nodes with abnormal degrees.
- Consider separating single-resource authorization checks from list-filtering queries, as they have different plan requirements.

### 21.3. Inspect Plans Without Equating DB Hits to Real I/O

~~~cypher
PROFILE
MATCH (u:QA004User {userId:'U01'})
OPTIONAL MATCH (u)-[:QA004_MEMBER_OF]->
               (g:QA004Group)
RETURN u.userId AS id, collect(g.groupId) AS groups;
~~~

Inspect `Rows`, `DB Hits`, and when available, `Page Cache Hits/Misses`. The 18-node fixture only verifies functional correctness; sizing indexes, memory, and caches at scale requires benchmarking on representative authorization data.

**Never** run unbounded `*0..` traversals on uncontrolled graphs; this risks path explosion and query-level DoS.

## 22. Security Testing: Authorization Suites Must Test Denials

### 22.1. Integration Test Matrix

| Case | Input | Assertion |
|---|---|---|
| Role via group | U01 READ DOC1 | ALLOW |
| Role inheritance | U02 APPROVE DOC1 | ALLOW |
| Scope inheritance | U05 WRITE DOC1 | ALLOW |
| Deny ALL beats grant | U01 READ DOC2 | DENY |
| Action-specific deny | U05 WRITE DOC2 | DENY |
| Deny does not block other actions | U05 READ DOC2 | ALLOW |
| Role lacks unrelated action | U03 WRITE DOC1 | DENY |
| Separate resource scope | U04 READ FIN1 | DENY |
| Auditor reads finance | U03 READ FIN1 | ALLOW |
| No roles | U06 READ DOC1 | DENY |
| Non-existent user | U99 READ DOC1 | DENY (0 records from query) |
| Non-existent resource | U01 READ DOC99 | DENY (0 records) |
| No reverse inheritance | U04 APPROVE DOC1 | DENY |
| Membership revocation | U01 after leaving G_DEV | Loses READ DOC1 from group |
| Role/resource cycle | Attempt adding cycle in test tx | Admin transaction must reject |
| Cross-tenant | Tenant A user requests tenant B resource | DENY |
| Write while denied | U01 WRITE DOC2 | Title unchanged, transaction fails/rolls back |
| Cache after revoke | Remove group grant then retry | Must not continue returning stale ALLOW |

A unit test mocking `AuthorizationRepository.can(...)` to return true/false is **insufficient** to verify that Cypher actually traverses the right paths. Run integration tests against a real Neo4j test instance with an independent fixture and check against the Section `5.3` matrix.

### 22.2. JUnit Example Checking the Expected Matrix

Assume the test seeds the Section 6–7 fixture in a Neo4j test instance, and `GraphAuthorization.can(...)` is the method from Section 14:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class AuthorizationContractTest {

    // driver and database are provided by the fixture/test container.

    @Test
    void inheritedGrantAndExplicitDeny() {
        assertTrue(GraphAuthorization.can(
            driver, database, "U01", "DOC1", "READ"
        ));
        assertFalse(GraphAuthorization.can(
            driver, database, "U01", "DOC2", "READ"
        ));
        assertFalse(GraphAuthorization.can(
            driver, database, "U05", "DOC2", "WRITE"
        ));
        assertTrue(GraphAuthorization.can(
            driver, database, "U05", "DOC2", "READ"
        ));
        assertTrue(GraphAuthorization.can(
            driver, database, "U02", "DOC1", "APPROVE"
        ));
        assertTrue(GraphAuthorization.can(
            driver, database, "U03", "FIN1", "READ"
        ));
        assertFalse(GraphAuthorization.can(
            driver, database, "U06", "DOC1", "READ"
        ));
    }
}
~~~

This is an **illustrative test snippet**; it does not declare `driver`, `database`, `@BeforeEach`, or test containers. In a real suite, add setup/teardown, Neo4j version config, and test isolation. Never run tests against a production database.

### 22.3. Testing "No Data Leakage on Reads"

Do not test only write endpoints. Also verify:

- Document lists and total counts do not expose info about denied resources.
- Title search, pagination, and downloads do not expose metadata/files of unauthorized documents.
- Queries traversing relationships from an authorized document to a denied document do not return the full target node unchecked.
- Traces/logs/error messages do not contain confidential group names, private roles, or sensitive document contents.
- API callers cannot swap `authenticatedUserId` to impersonate MANAGER.

Verify security policy enforcement **at the final output**, not only inside one helper method.

## 23. Auditing and Explaining Authorization Decisions

An internal audit record should capture at minimum:

| Field | Purpose |
|---|---|
| Timestamp, requestId, correlationId | Reconstruct event sequence |
| Authenticated principal | Who made the request, via which auth source |
| Action and resource ID | What was requested on which object |
| ALLOW/DENY outcome | Final decision, not just grant status |
| Policy version | Which policy version governed the decision |
| Internal reason | No grant, explicit deny, invalid user/resource, tenant mismatch |
| Execution duration | Monitor authorization latency |
| Role/group change TraceId | Who modified the edges leading to the decision |

**Never log** access tokens, secrets, document payloads, or unauthorized full graph paths into public logs. Restrict access and set retention periods for stored authorization evidence.

### 23.1. Why Explanations Must Be Tied to a Point in Time

Permissions can change seconds later. If audit logs record only "U01 was allowed to READ DOC1" without storing a policy version or change set, the graph may look different the next day and fail to explain the earlier decision.

You can use **policy versioning** or event sourcing for updates to grants, denies, memberships, and resource ancestry. If compliance mandates reconstructing exact permissions at a past timestamp, current graph state alone **is not enough**; you need tamper-protected change history.

## 24. Runbook for Rolling Out an Organizational Authorization Model

### Design Phase

1. Enumerate true actions: READ/WRITE/APPROVE; never use role names as actions.
2. Classify resources, owners, tenants, and data sensitivity.
3. Define who can create roles, assign users to groups, add denies, or alter the resource tree.
4. Document **deny precedence**, inherited scope, depth limits, and missing user/resource handling.
5. Confirm separation of duties, e.g., authors cannot self-approve sensitive documents.

### Implementation Phase

6. Create business IDs and unique constraints/indexes.
7. Seed roles/groups/resource tree with DAG validation, tenant boundaries, and grant checks.
8. Route all resource reads/writes through the authorization gateway; keep the DB service account least-privileged.
9. Add integration tests covering positive and negative expectations.
10. Monitor query plans, cache invalidation, latency, and DENY decisions.

### Operations Phase

11. Monitor roleless accounts, overly broad roles, and spiking deny exceptions.
12. Maintain **joiner/mover/leaver** workflows: onboarding, transfers, and offboarding must update memberships/permissions and revoke sessions/tokens/caches promptly.
13. Run periodic access reviews: who holds admin rights, which roles are unused, and what grants exist on sensitive resources.
14. Practice emergency revocation drills and verify permissions cease across APIs, batch jobs, and caches.
15. Back up and restore the policy graph alongside identity data, then test authorization post-restore; a restored graph missing users/roles can cause mass false denials or expose bypass gaps.

**Rollout principle:** if migrating from another policy engine, run **shadow evaluation** (compute decisions without blocking), compare against expected results/legacy engine, resolve discrepancies, then canary enforce. Never enable org-wide enforcement without a controlled break-glass procedure and rollback path.

## 25. Practice Exercises with Solutions

### Exercise 1 — Role Inheritance

MANAGER → EDITOR → VIEWER. What permissions does MANAGER have if VIEWER has READ on PRJ, EDITOR has WRITE on PRJ, and MANAGER has APPROVE on PRJ?

**Solution:** MANAGER has **READ, WRITE, and APPROVE** on PRJ and child resources within the inheritance scope. VIEWER does not gain WRITE/APPROVE.

### Exercise 2 — Resource Scope Inheritance

DOC1 → PRJ → ROOT and FIN1 → FIN → ROOT. VIEWER only has READ on PRJ. Can VIEWER READ FIN1?

**Solution:** **No.** There is no path from FIN1 up to PRJ; sharing ROOT is insufficient because ROOT has no grant.

### Exercise 3 — Roles via Groups

U01 belongs to G_DEV, G_DEV has EDITOR, and EDITOR inherits VIEWER. Can U01 WRITE DOC1?

**Solution:** **Yes**, because EDITOR has WRITE on PRJ, DOC1 sits under PRJ, and no deny applies to DOC1.

### Exercise 4 — Deny Beats Grant

U01 has READ/WRITE via G_DEV, plus `DENIES {action:'ALL'}` on DOC2. Can U01 READ or WRITE DOC2?

**Solution:** **Neither.** `hasGrant=true` and `hasDeny=true`, so `allowed=false`.

### Exercise 5 — Action-Specific Deny

U05 has EDITOR and DENY WRITE on DOC2. Can U05 read DOC2? Can U05 write DOC2?

**Solution:** **READ is allowed**, **WRITE is denied**. Rule P8 keeps actions independent, so denying WRITE does not block READ.

### Exercise 6 — Privilege Auditing

U02 holds MANAGER directly. If U02 requests APPROVE on DOC1, trace the explanation path.

**Solution:** U02 → ASSIGNED_ROLE → MANAGER → GRANTS {APPROVE} → PRJ; DOC1 → PART_OF → PRJ; no deny applies, so ALLOW.

### Exercise 7 — User Without Roles

U06 exists with no direct roles or groups. What is the result of checking READ on DOC1?

**Solution:** **DENY by default deny.** `seeds` is empty and `hasGrant=false`; lack of a deny never grants access.

### Exercise 8 — Non-Existent Node

A client requests U01 READ DOC99, where DOC99 does not exist. What does the Section 11 query return, and what should the API do?

**Solution:** The query returns **0 records**. The backend must **fail closed**; never treat 0 records as ALLOW, and avoid leaking whether an unauthorized resource exists.

### Exercise 9 — Dangerous Inheritance Cycle

If you add VIEWER → MANAGER while MANAGER → EDITOR → VIEWER already exists, what happens?

**Solution:** It forms a cycle allowing VIEWER to reach MANAGER permissions, causing privilege escalation. Reject cycle-forming updates and check new edges in a concurrency-controlled admin workflow.

### Exercise 10 — Group Permission Revocation

U01 has no direct roles and belongs only to G_DEV. If G_DEV membership is removed, can U01 still READ DOC1?

**Solution:** **No**, unless another grant path was added outside the fixture. Invalidate caches so stale API decisions do not linger.

### Exercise 11 — Checking and Writing in One Transaction

A Java service calls `canWrite` in transaction A, then updates the document in transaction B. Why is this unsafe under concurrent revocation?

**Solution:** Permissions can change between the two transactions. Perform the check and write inside the same transaction, and add policy versioning/locking if immediate pre-commit revocation is required.

### Exercise 12 — N+1 Queries

A list has 2,000 documents; the service loads all IDs and calls an individual permission query per document. What happens, and how should it be optimized?

**Solution:** It generates at least **2,000 extra checks**, adding round trips and over-fetch overhead. Use batched permission evaluation with `UNWIND` or policy-versioned index/materialized-view strategies, verifying correctness and p95 latency before rollout.

### Exercise 13 — Tenant Isolation

Tenants A and B both have `roleId` EDITOR and `resourceId` DOC1. If a query only runs `MATCH (r {resourceId:'DOC1'})` without tenant checks, what is the risk?

**Solution:** It can apply permissions or return data from the wrong tenant. Enforce composite IDs / tenant scoping **across every node and inheritance path**, not only on input user/resource nodes.

### Exercise 14 — Verifying Fixture Counts

There are 6 users, 2 groups, 4 roles, and 6 resources; 3 role inheritance edges, 5 PART_OF edges, 5 ASSIGNED_ROLE edges, 2 MEMBER_OF edges, 4 GRANTS, and 2 DENIES. What are the total nodes and relationships?

**Solution:** **18 nodes** and **21 relationships**. If totals differ, reset/verify the fixture before relying on the expected authorization matrix.

## 26. Fixture Cleanup and Final Verification

Run only on the **test database** holding this lesson's fixture; never execute these statements in production.

~~~cypher
MATCH (n)
WHERE n:QA004User
   OR n:QA004Group
   OR n:QA004Role
   OR n:QA004Resource
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa004_user_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa004_group_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa004_role_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa004_resource_id IF EXISTS;
~~~

Verify:

~~~cypher
MATCH (n)
WHERE n:QA004User
   OR n:QA004Group
   OR n:QA004Role
   OR n:QA004Resource
RETURN count(n) AS remaining;
~~~

**Answer:** `remaining=0`. If you tested group revocation or added denies, cleanup deletes those mutations too since they belong to fixture nodes. Do not run if these labels were reused for real data.

## 27. References and Takeaways

- [Neo4j Cypher Manual — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/): querying nodes/relationships and directed patterns.
- [Neo4j Cypher Manual — Variable-length patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/): variable-hop paths, bounds, and path modeling.
- [Neo4j Cypher Manual — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/): testing existence of valid authorization paths.
- [Neo4j Cypher Manual — Predicates](https://neo4j.com/docs/cypher-manual/current/functions/predicate/): `any`, `all`, and logical checks.
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/): uniqueness and protecting business keys.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`/`PROFILE` for tuning authorization queries.
- [Neo4j Operations Manual — Security and access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/access-control/): DBMS-level RBAC, distinct from application ACLs.
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/): checking and updating inside managed transactions.
- [Neo4j Java Driver Manual — Run queries](https://neo4j.com/docs/java-manual/current/query-simple/): parameterization, `Record`, and result consumption.
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/): entity mapping, `Neo4jClient`, and Spring transaction management.
- [NIST RBAC model and standard](https://csrc.nist.gov/projects/role-based-access-control): RBAC concepts, role hierarchies, and separation of duties.

**Takeaway:** A graph is a great tool for modeling **who belongs to which group, which roles they receive, how permissions inherit, and which resources they cover**. Still, a secure authorization system requires an **explicit policy**: default deny, deny precedence, bounded inheritance paths, tenant isolation, cycle prevention, verified identity, consistent transactions/revocation/caching, and negative tests. **Finding a `GRANTS` path is never enough to conclude ALLOW**; the final decision is only valid after checking all **`DENIES`** paths and remaining business predicates.
