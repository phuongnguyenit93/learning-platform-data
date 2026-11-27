# Recursive Relationships and Multiple Roles Between the Same Entity Type

Within the **DATABASE_DATA_MODELING** module, a data model must accurately describe how entities participate in business relationships. One common source of confusion occurs when an entity links to another entity of the same type: an employee manages an employee, a course requires prerequisite courses, an account transfers funds to an account, or a user follows a user.

This is a **recursive relationship** (self-referencing relationship). When both ends of a relationship point to the same entity type, each end can still carry a distinct role. For instance, in a funds transfer, one account is the sender and the other is the recipient. If the model only states "account relates to account", the meaning of the data becomes ambiguous.

This lesson explains how to identify recursive relationships, name roles, determine cardinalities, choose representations in the relational model and other data model families, and control self-loops, cycles, and relationship history.

## 1. What is a recursive relationship?

A **recursive relationship** connects instances of the same entity type. In a diagram, both ends of the relationship point to the same entity, while each end may represent a different role.

Examples:

- An employee reports to another employee.
- A parent category contains child categories.
- A course has prerequisite courses.
- An account sends funds to another account.
- A user follows another user.
- A product replaces or is compatible with another product.

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE : manages
    COURSE ||--o{ COURSE : prerequisite_for
    ACCOUNT ||--o{ ACCOUNT : transfers_to
~~~

The overview diagram shows that one entity type can appear at both ends. During implementation and documentation, role names must be explicitly stated so readers do not confuse which end is the source and which is the target.

### Recursive relationships vs. relationships between two entity types

Comparison:

- **Standard relationship:** Customer places Order. The two ends are different entity types.
- **Recursive relationship:** Employee manages Employee. Both ends are the Employee entity type, while the roles are manager and managed employee.

Having both ends share the same entity type does not eliminate role differences. Roles are part of the relationship's semantics and must be explicitly documented in the model.

## 2. Naming roles for each relationship end

Whenever the same entity type appears multiple times in a relationship, name each role. A role name should describe the entity's business function in that relationship.

| Entity type | First role | Second role | Relationship meaning |
|---|---|---|---|
| Employee | Manager | Subordinate/Report | One employee manages another employee |
| Course | Course | Prerequisite | One course requires completing another course |
| Account | Source account | Destination account | One account transfers money to another account |
| User | Follower | Followed user | One user follows another user |
| Product | Original product | Replacement product | One product is replaced by another product |

Avoid generic names such as `entity_a`, `entity_b`, `related_id`, or `other_id` whenever role-based names are possible. Clear names make diagrams easier to read, queries easier to write, APIs easier to design, and rules easier to verify.

### Directed roles

In the relationship "A manages B", the roles Manager and Subordinate cannot be swapped arbitrarily. Likewise, Source account and Destination account carry distinct meanings in a transfer transaction.

Phrase sentences in both directions:

- "Employee A manages Employee B."
- "Employee B reports to Employee A."

Both sentences express the same link from two different roles. This helps verify directionality and avoid misnaming columns.

### Roles are not necessarily entity attributes

A person can be the sender in one transaction and the recipient in another. Do not add permanent `is_sender` or `is_receiver` columns to the Person table to represent roles across all relationships. A role typically belongs to **a specific participation in a relationship**, not an inherent, permanent trait of the person.

## 3. Determining cardinality and mandatory participation

Recursive relationships still require determining cardinality at each end. Never infer cardinality merely because both ends have the same entity type.

### Example: employee management hierarchy

An employee may have no manager if they are the top executive; each employee has at most one direct manager. A manager can manage many employees.

| Role | Participation count | Interpretation |
|---|---:|---|
| Manager of a Subordinate | 0..1 | An employee may have no direct manager or have exactly one |
| Subordinate of a Manager | 0..N | A manager may have zero or many direct reports |

This model is a recursive one-to-many relationship. If each employee could have multiple direct managers, the structure shifts to many-to-many and requires a junction table.

### Example: course prerequisites

A course can require completing multiple prerequisite courses, and a course can serve as a prerequisite for many other courses.

| Role | Participation count |
|---|---:|
| Course requiring prerequisites | 0..N Prerequisites |
| Prerequisite required by | 0..N Courses |

This is a recursive many-to-many relationship. Each directed pair must be clearly defined: which course has the requirement, and which course must be completed beforehand.

### Example: transfers between accounts

Every transfer transaction has exactly one source account and one destination account. An account can be the source in many transfers and the destination in many transfers.

- Source role: exactly one account per transfer.
- Destination role: exactly one account per transfer.
- An account can participate in 0..N transfers in each role.

This is a relationship with two fixed roles referencing the Account table. It is not a simple one-to-many hierarchy like an employee management tree.

## 4. Recursive one-to-many relationships in the relational model

For a one-to-many relationship, the common representation places a self-referencing foreign key on the many side. For example, each employee has a `manager_id` pointing to `employee.employee_id`.

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE : manages
    EMPLOYEE {
        bigint employee_id PK
        string employee_name
        bigint manager_id FK
    }
~~~

Illustrative DDL:

~~~sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    employee_name VARCHAR(160) NOT NULL,
    manager_id BIGINT,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id) REFERENCES employee(employee_id),
    CONSTRAINT ck_employee_not_own_manager
        CHECK (manager_id IS NULL OR manager_id <> employee_id)
);
~~~

In this example:

- `employee_id` identifies an employee.
- `manager_id` is a foreign key pointing to another employee acting as the manager.
- NULL indicates the employee has no direct manager within the scope of the model.
- CHECK prevents an employee from managing themselves.
- The foreign key ensures the referenced manager exists.

A foreign key and a CHECK constraint are not enough to prevent multi-hop cycles in the management structure. For example, A manages B, B manages C, and C manages A would not violate either constraint above. If the business requires an acyclic tree or forest, cycle detection must run whenever the relationship changes.

### Self-join queries

To display employees alongside their managers' names, the same table is used twice with different aliases:

~~~sql
SELECT
    subordinate.employee_id,
    subordinate.employee_name,
    manager.employee_id AS manager_id,
    manager.employee_name AS manager_name
FROM employee AS subordinate
LEFT JOIN employee AS manager
    ON manager.employee_id = subordinate.manager_id
ORDER BY subordinate.employee_id;
~~~

The aliases `subordinate` and `manager` express the two roles. LEFT JOIN retains employees who have no manager. Using INNER JOIN would omit employees without a `manager_id`.

### Multi-level tree queries

A recursive query can traverse from an employee down through reporting levels below them. The syntax below illustrates PostgreSQL:

~~~sql
WITH RECURSIVE reporting_tree AS (
    SELECT
        employee_id,
        employee_name,
        manager_id,
        0 AS depth
    FROM employee
    WHERE employee_id = :root_employee_id

    UNION ALL

    SELECT
        child.employee_id,
        child.employee_name,
        child.manager_id,
        parent.depth + 1
    FROM employee AS child
    JOIN reporting_tree AS parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, employee_name, manager_id, depth
FROM reporting_tree
ORDER BY depth, employee_id;
~~~

This query assumes the data contains no cycles. If a cycle exists, the recursive query can loop indefinitely or run until hitting a DBMS limit. When querying untrusted data, apply visited-path tracking or an appropriate depth limit, and repair the source data.

## 5. Recursive many-to-many relationships

A many-to-many relationship between instances of the same type is typically stored using a junction table. For example, a course has many prerequisites and can simultaneously be a prerequisite for many other courses.

~~~mermaid
erDiagram
    COURSE ||--o{ COURSE_PREREQUISITE : requires
    COURSE ||--o{ COURSE_PREREQUISITE : prerequisite
    COURSE {
        bigint course_id PK
        string course_name
    }
    COURSE_PREREQUISITE {
        bigint course_id PK, FK
        bigint prerequisite_course_id PK, FK
    }
~~~

~~~sql
CREATE TABLE course (
    course_id BIGINT PRIMARY KEY,
    course_name VARCHAR(200) NOT NULL
);

CREATE TABLE course_prerequisite (
    course_id BIGINT NOT NULL,
    prerequisite_course_id BIGINT NOT NULL,
    CONSTRAINT pk_course_prerequisite
        PRIMARY KEY (course_id, prerequisite_course_id),
    CONSTRAINT fk_prerequisite_course
        FOREIGN KEY (course_id) REFERENCES course(course_id),
    CONSTRAINT fk_required_course
        FOREIGN KEY (prerequisite_course_id) REFERENCES course(course_id),
    CONSTRAINT ck_no_self_prerequisite
        CHECK (course_id <> prerequisite_course_id)
);
~~~

Conventions in this example:

- `course_id` is the course requiring the prerequisite.
- `prerequisite_course_id` is the course that must be completed beforehand.
- The composite primary key prevents storing the same directed pair twice.
- CHECK prevents a course from being its own prerequisite.
- Foreign keys ensure both courses exist.

If the business permits independent reverse relationships, the pairs A → B and B → A are two distinct entries under the primary key. If the business requires an acyclic graph, multi-step cycle detection is needed, not just checking for a direct reverse pair.

### Cycle checking

For prerequisites, a cycle such as A requires B, B requires C, and C requires A makes it impossible to complete any course before the others. One way to check is, before adding edge A → B, searching whether a path already exists from B to A. If so, adding the new edge would create a cycle.

The following PostgreSQL query illustrates checking whether a path exists from the prerequisite course to the target course:

~~~sql
WITH RECURSIVE reachable(course_id) AS (
    SELECT prerequisite_course_id
    FROM course_prerequisite
    WHERE course_id = :new_prerequisite_course_id

    UNION

    SELECT cp.prerequisite_course_id
    FROM course_prerequisite AS cp
    JOIN reachable AS r
      ON cp.course_id = r.course_id
)
SELECT EXISTS (
    SELECT 1
    FROM reachable
    WHERE course_id = :new_course_id
) AS would_create_cycle;
~~~

If the result is TRUE, an existing path means the new edge would create a cycle under this example's direction convention. Checking and inserting must be protected inside a concurrency-controlled transaction. If two transactions both check before inserting, both could see a cycle-free state and insert edges that together form a cycle. Use an appropriate isolation level, graph-scoped locking, or serialized relationship updates.

## 6. Multiple fixed roles between the same entity type

A relationship can have multiple fixed roles referencing the same table. For example, a transfer transaction has one source account and one destination account.

~~~mermaid
erDiagram
    ACCOUNT ||--o{ TRANSFER : source_account
    ACCOUNT ||--o{ TRANSFER : destination_account
    ACCOUNT {
        bigint account_id PK
        string account_number
    }
    TRANSFER {
        bigint transfer_id PK
        bigint source_account_id FK
        bigint destination_account_id FK
        decimal amount
        datetime created_at
    }
~~~

~~~sql
CREATE TABLE account (
    account_id BIGINT PRIMARY KEY,
    account_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE account_transfer (
    transfer_id BIGINT PRIMARY KEY,
    source_account_id BIGINT NOT NULL,
    destination_account_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_transfer_source
        FOREIGN KEY (source_account_id) REFERENCES account(account_id),
    CONSTRAINT fk_transfer_destination
        FOREIGN KEY (destination_account_id) REFERENCES account(account_id),
    CONSTRAINT ck_transfer_different_accounts
        CHECK (source_account_id <> destination_account_id),
    CONSTRAINT ck_transfer_amount_positive
        CHECK (amount > 0)
);
~~~

Two foreign key columns reference the same Account table under different names and roles. Two independent FK constraints let the DBMS validate both source and destination. The CHECK constraint expresses the assumption that a transaction cannot transfer funds to the same source account. If the domain includes internal transaction types permitting the same account, the condition must be scoped by transaction type.

Querying both source and destination account numbers also requires two aliases:

~~~sql
SELECT
    tr.transfer_id,
    source.account_number AS source_account,
    destination.account_number AS destination_account,
    tr.amount,
    tr.created_at
FROM account_transfer AS tr
JOIN account AS source
  ON source.account_id = tr.source_account_id
JOIN account AS destination
  ON destination.account_id = tr.destination_account_id;
~~~

Do not use a single `account_id` column paired with a `role` column when a relationship always has exactly two fixed roles with distinct rules for each role. Two role-named FKs make mandatory constraints and queries much clearer.

## 7. Variable roles: using a participation table

Sometimes instances of the same entity type participate in an event in variable numbers and roles. For example, a meeting has an organizer, presenters, a note-taker, and attendees; one person can hold multiple roles if rules allow it.

When the set of roles is extensible, use a participation table with one row per person and role:

~~~sql
CREATE TABLE meeting (
    meeting_id BIGINT PRIMARY KEY,
    meeting_title VARCHAR(200) NOT NULL
);

CREATE TABLE person (
    person_id BIGINT PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE meeting_participant (
    meeting_id BIGINT NOT NULL,
    person_id BIGINT NOT NULL,
    role_code VARCHAR(30) NOT NULL,
    joined_at TIMESTAMP,
    CONSTRAINT pk_meeting_participant
        PRIMARY KEY (meeting_id, person_id, role_code),
    CONSTRAINT fk_participant_meeting
        FOREIGN KEY (meeting_id) REFERENCES meeting(meeting_id),
    CONSTRAINT fk_participant_person
        FOREIGN KEY (person_id) REFERENCES person(person_id)
);
~~~

The composite primary key allows the same person to hold multiple roles in a meeting, while preventing the same role from being recorded twice for that person. If business rules dictate that each meeting has only one organizer, add a conditional unique constraint filtered by `role_code`, or model the organizer role as a dedicated FK column. If each person may hold only one role, the primary key can be `(meeting_id, person_id)`.

### Choosing between fixed role FKs and a role table

| Situation | Appropriate representation |
|---|---|
| Always one sender and one receiver | Two role-named FKs on the transaction/relationship table |
| Always a manager and reporting employee | Self-referencing `manager_id` FK on Employee |
| Multiple participants with variable roles | Participation table containing `entity_id` and `role_code` |
| One person can hold multiple roles in the same event | Key consisting of `event_id`, `person_id`, `role_code` or equivalent |
| Each role allows at most one person | `UNIQUE` constraint on `event_id` and `role_code` |
| Roles carry their own attributes | Role/participation table containing the corresponding attributes |

Do not create a separate column for every conceivable role if roles change frequently. Conversely, do not force an overly generic role table when the domain strictly has two fixed roles with distinct constraints.

## 8. Distinguishing trees, forests, and directed acyclic graphs

Not every recursive relationship forms a tree. Define the permitted graph structure:

- **Tree:** one root, every non-root node has exactly one parent; no cycles and all nodes belong to the same tree.
- **Forest:** multiple independent trees; each node has at most one parent.
- **DAG:** directed acyclic graph; a node can have multiple parents and multiple children.
- **General graph:** may contain cycles, multiple paths, and diverse link types.

| Domain | Common structure | Notes |
|---|---|---|
| Employee reporting structure | Tree or forest | Each employee typically has at most one direct manager |
| Single-parent category hierarchy | Tree or forest | A child node has one parent category |
| Course prerequisites | DAG | A course can have multiple prerequisites |
| Users following each other | General directed graph | Mutual follow loops can exist |
| Symmetric friendships | Undirected graph semantically | Needs a rule for storing once vs. bidirectionally |

Never force a tree model if the domain allows multiple parents. Likewise, do not impose an acyclic rule on relationships where cycles are valid, such as users following each other.

### Ways to store hierarchical structures

For tree relationships, several storage patterns are common:

| Model | How it stores data | Advantages | Limitations |
|---|---|---|---|
| Adjacency list | Each node stores `parent_id` | Simple, easy to move nodes | Full-tree queries require recursion |
| Closure table | Stores every ancestor–descendant pair and depth | Fast, clear ancestor/descendant queries | Extra rows and update overhead |
| Materialized path | Stores path from root to node | Convenient prefix-based subtree queries | Moving a node requires updating descendant paths |
| Nested sets | Stores left/right bounds | Efficient subtree reads for certain workloads | Inserting/moving nodes may update many rows |

An adjacency list is usually an intuitive starting point. When ancestor/descendant queries become a bottleneck, consider a closure table or materialized path based on your workload.

Closure table example:

Assume the `employee` table has already been created as in the adjacency list example above. The table below provides the companion closure-table structure; it can be used instead of repeatedly running recursive queries on `manager_id`.

~~~sql
CREATE TABLE employee_hierarchy (
    ancestor_id BIGINT NOT NULL,
    descendant_id BIGINT NOT NULL,
    depth INTEGER NOT NULL,
    CONSTRAINT pk_employee_hierarchy
        PRIMARY KEY (ancestor_id, descendant_id),
    CONSTRAINT fk_hierarchy_ancestor
        FOREIGN KEY (ancestor_id) REFERENCES employee(employee_id),
    CONSTRAINT fk_hierarchy_descendant
        FOREIGN KEY (descendant_id) REFERENCES employee(employee_id),
    CONSTRAINT ck_hierarchy_depth CHECK (depth >= 0)
);
~~~

A closure table typically includes a self-row with `depth = 0` for each employee in addition to ancestor–descendant rows. When moving an employee to another branch, update old and new path sets within the same transaction. Because this is a derived model from the parent–child relationship, establish a source of truth and synchronization rules so closure data never drifts out of sync.

## 9. Representing recursive relationships across model families

Role semantics must remain consistent even as storage structures change.

| Model family | Representation | When appropriate |
|---|---|---|
| Relational | Self-referencing FK, multiple role FKs, or junction table | Needs referential integrity, transactions, and explicit constraints |
| Document | `parentId` field, role reference fields, or edge/participant arrays | Data is read as aggregates; updates and cycles are guarded in application logic |
| Graph | Nodes of the same label linked by directed edges with role labels | Multi-hop traversal, path finding, and neighborhood queries are central |
| Analytical | Self-referencing dimension, bridge table, or relationship fact | Needs hierarchy analysis, source/target roles, or relationship history |

### Document: parent reference and embedded children

A category document can store `parentId` to reference its parent document, mirroring an adjacency list. Children can be embedded if the tree is small, rarely changes, and is usually read with its parent; however, embedding all descendants can bloat documents and complicate moving nodes.

For two fixed roles, store `sourceAccountId` and `destinationAccountId`. For variable roles, an array of participants containing `personId` and `roleCode` is more suitable. Validate that referenced IDs exist and enforce cardinality rules in the write path.

### Graph: same node label, multiple relationship labels

In a graph database, both ends of an edge can be nodes with the same label while the edge indicates direction and role:

~~~mermaid
flowchart LR
    A["(:Employee {id: A})"] -->|"MANAGES"| B["(:Employee {id: B})"]
    C["(:Employee {id: C})"] -->|"MENTORS"| B
~~~

Employee B can be managed by A and mentored by C. Two distinct relationship types share the same target yet carry different meanings. Storing only a single `relatedEmployeeId` field would lose that role information.

### Analytical: role-playing dimensions

In a data warehouse, a fact table may reference the same employee dimension in multiple roles—such as transaction creator, approver, and handler. Create role-playing dimensions or multiple role-named foreign keys. Reports must alias the dimension properly for each role so creator and approver are never confused.

## 10. Lifecycle, time, and deleting relationships

Recursive relationships can change over time. An employee transfers to a new manager; a course updates its prerequisites; a user unfollows another; an account is closed.

Distinguish among:

- **Current relationship:** retains only active links currently in effect.
- **Relationship history:** retains link occurrences with start/end timestamps.
- **Snapshot:** captures roles or details as of the moment an event occurred.
- **Derived relationship:** computed from base relationships, such as tree paths or a closure table.

If history is required, add `valid_from`, `valid_to`, `created_at`, `ended_at`, or a status column. Uniqueness rules must then account for effective intervals. For instance, an employee can have many managers over time yet at most one active direct manager at any single point in time.

Deletion policies must also be explicit:

- `ON DELETE RESTRICT`: forbids deleting an entity still referenced by others.
- `ON DELETE SET NULL`: keeps child entities while clearing the parent link; suitable when the relationship is optional and separate history is not needed.
- `ON DELETE CASCADE`: deletes dependent relationship rows; use only when business lifecycle allows it.
- Deactivation/soft delete: retains data and history, commonly suitable for personnel, accounts, and auditable records.

Do not choose CASCADE merely to avoid foreign key errors. Deleting an employee can break the reporting tree or erase management history if no handover rule is executed first.

## 11. Validating recursive and multi-role relationships

After designing, build concrete test cases:

1. Create a valid link between two distinct instances of the same entity type.
2. Attempt a self-reference A → A if forbidden by business rules.
3. Attempt reverse pairs A → B and B → A to test symmetry or cycle rules.
4. For trees, attempt assigning two parents to one node.
5. For DAGs, attempt creating a three-node cycle.
6. For fixed multi-role relationships, try leaving a mandatory role blank or reusing the same entity in both roles if forbidden.
7. For role tables, test repeating the same role and giving one person multiple roles.
8. Attempt deleting a parent node or a referenced node.
9. Test concurrent relationship changes from two transactions.
10. Reconcile history and derived data after moving nodes or changing roles.

### Query to find self-managing employees

~~~sql
SELECT employee_id, manager_id
FROM employee
WHERE employee_id = manager_id;
~~~

### Query to find employees with more than one active manager

Assume management history is stored in `employee_manager_history`:

~~~sql
SELECT
    employee_id,
    COUNT(*) AS active_manager_count
FROM employee_manager_history
WHERE valid_to IS NULL
GROUP BY employee_id
HAVING COUNT(*) > 1;
~~~

The result must be empty if business rules require at most one active direct manager. Diagnostic queries against existing data do not replace constraints protecting write operations.

### Query validating source and destination roles

For account transfers, verify that both FKs exist and do not violate the distinct-accounts rule. CHECK and FK constraints protect basic conditions; rules such as both accounts being active, matching currencies, or sufficient balance must be checked inside a concurrency-controlled business transaction.

## 12. Design and documentation process

For each recursive or multi-role relationship on the same entity type:

1. Identify the participating entity type and why both ends share the same type.
2. Name distinct roles for each end; write business statements from each role's perspective.
3. Determine direction, symmetry, self-referencing eligibility, and transitivity.
4. Specify min/max for each role independently without inferring from the opposite end.
5. Determine whether the structure is one-to-many, many-to-many, tree, forest, DAG, or general graph.
6. Identify relationship attributes and history requirements.
7. Choose self-referencing FKs, multiple fixed FKs, a junction table, or node/edge structures.
8. Define key, uniqueness, anti-self-reference, anti-cycle, and role rules.
9. Define deletion, retention, and relationship transition policies.
10. Verify using self-joins, recursive queries, cycle test cases, and concurrent operations.

### Specification template

| Field | Content |
|---|---|
| Entity type | e.g., Employee |
| Relationship name | MANAGES, PREREQUISITE_OF, TRANSFERS_TO |
| End A role | Manager, Course, Source account |
| End B role | Subordinate, Prerequisite, Destination account |
| Direction | Directed, symmetric, or independent bidirectional |
| Cardinality | Min..max for each role |
| Self-reference | Allowed/disallowed; permitted conditions |
| Cycles | Allowed, forbidden, or specific cycle types forbidden |
| Relationship attributes | Timestamps, status, amount, effective period |
| History | Current state only or versioned history |
| Representation | Self-referencing FK, multiple FKs, junction table, node/edge |
| Integrity | PK, FK, UNIQUE, CHECK, transaction, or algorithm |
| Verification | Valid cases, self-references, cycles, concurrency, and deletes |

## 13. Practice exercises and assessment rubric

### Exercise 1 — Employee reporting structure

An employee has at most one direct manager, yet can supervise many other employees. The system must store manager transfer history over time.

Identify the Manager and Subordinate roles, cardinalities, tree/forest structure, and design both current-state and history tables. State how you ensure an employee cannot have two simultaneously active direct managers.

### Exercise 2 — Course prerequisites

A course can require many other courses, and a course can serve as a prerequisite for many others. Cycles are forbidden.

Design the junction table, keys, self-reference CHECK, and cycle-detection algorithm. Explain how to protect the check when two users update the course catalog concurrently.

### Exercise 3 — Funds transfer

A transaction has a source account and a destination account. Both roles are mandatory and must be distinct; each account can participate in many transactions.

Design two role-named FKs, write a two-alias self-join query, and list the rules that must be checked inside the transfer transaction.

### Exercise 4 — Multi-role meeting

A meeting has an organizer, presenters, a note-taker, and attendees. One person can hold multiple roles, yet each meeting has only one organizer.

Choose between fixed FKs and a participant table, and define the keys and uniqueness constraint for the organizer role.

### Self-assessment rubric

| Criterion | Meets requirements when |
|---|---|
| Identification | Correctly identifies relationships between instances of the same entity type |
| Roles | Clearly names each end without confusing source and target |
| Cardinality | Determines min/max separately for each role |
| Graph structure | Distinguishes trees, forests, DAGs, and general graphs |
| Representation | Chooses the right self-FK, multiple FKs, or junction table |
| Integrity | Controls self-references, duplicates, cycles, and mandatory roles |
| Lifecycle | Handles deletions, updates, and relationship history |
| Verification | Provides queries and test cases for boundary scenarios |

A recursive relationship is more than a foreign key pointing back to its own table. What matters is accurately defining each end's role, cardinality, direction, and permitted graph structure. When these decisions are captured explicitly, a data model can represent management trees, prerequisites, account transfers, and multi-role events consistently, queryably, and evolvably.
