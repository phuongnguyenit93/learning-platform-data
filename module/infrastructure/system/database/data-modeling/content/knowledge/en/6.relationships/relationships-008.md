# Directed, Ordered, and Bounded Relationships

Within the **DATABASE_DATA_MODELING** module, a data model must accurately describe not only which entities exist, but also how they relate to one another. A relationship can carry **direction**, **ordering**, or **quantity bounds** at one or both ends. These characteristics directly influence business semantics, key structures, integrity constraints, and how data is queried.

If direction is omitted, the system may confuse who depends on whom, or which object is the source and which is the destination. If ordering is omitted, workflow steps, route legs, or playback lists may appear in the wrong sequence. If quantity bounds are undocumented, data may violate rules such as "each order has one primary invoice," "an employee has at most two active emergency contacts," or "a course requires at least one prerequisite course when opened."

This lesson helps identify those three characteristics, represent them in conceptual models, and translate them into testable constraints.

## 1. Relationships have multiple semantic dimensions

A relationship describes how two or more entities participate together in a business event or link. When modeling, answer:

- Which entities or roles participate?
- What role does one side play, and what role does the other side play?
- Does the relationship distinguish source from target?
- Are the links ordered, or are they an unordered set?
- At minimum and maximum, how many times can each entity participate?
- Does the relationship have its own attributes such as timestamp, status, order position, creator, or effective period?
- Do the rules vary by status or over time?

All three characteristics can occur together. For example, an approval workflow has steps connected directionally from prior step to next step, each step has a position, and a request may be bounded to at most five approvers. Never treat "directed," "ordered," and "bounded" as mutually exclusive choices.

### Cardinality and participation counts

Multiplicity/cardinality describes the number of links allowed at each relationship end. Common notations:

| Notation | Meaning |
|---|---|
| 0..1 | Zero or at most one |
| 1..1 or 1 | Mandatory, exactly one |
| 0..N or 0..* | May have none or many |
| 1..N or 1..* | Must have at least one, possibly many |
| 2..5 | Between two and five elements |

Clarify which side the count applies to. In the Customer places Order relationship, a customer can place 0..N orders; each order belongs to exactly one customer. These are two distinct constraints.

Beyond cardinality, distinguish **mandatory participation** from **maximum bounds**. "An order must have at least one line item when confirmed" is a status-conditional minimum constraint. "An employee has at most two active emergency contacts" is a maximum bound across a set of links.

## 2. Directed relationships

A **directed relationship** distinguishes the roles of the two linked ends. One side is the source and the other is the destination, or each end holds a distinct business role. Reversing the direction produces a different meaning.

Examples:

- Course A is a prerequisite for Course B.
- Employee M manages Employee N.
- Account A transfers money to Account B.
- User A follows User B.
- Task X depends on Task Y.

In "A is a prerequisite for B," direction can be interpreted as A must be completed before B can be taken. Swapping the ends turns the meaning into B is a prerequisite for A.

~~~mermaid
flowchart LR
    A["Course A"] -->|"must be completed before"| B["Course B"]
    B -->|"must be completed before"| C["Course C"]
~~~

### Identifying source and target roles

Avoid generic names like `related_course` or `linked_employee`. Name attributes after their roles:

- `course_id`: the course requiring the prerequisite.
- `prerequisite_course_id`: the course that must be completed beforehand.
- `manager_id`: the manager.
- `subordinate_id`: the managed employee.
- `source_account_id`: the sending account.
- `destination_account_id`: the receiving account.

Role names allow readers to understand direction even without looking at a diagram. For recursive relationships, such as an employee managing an employee, both ends point to the same table yet hold different roles.

### A directed relationship does not imply a reverse relationship

If A follows B, that does not mean B follows A. If A manages B, that does not mean B manages A. Some relationships allow reciprocal pairs, yet that must be explicitly confirmed by the business.

Distinguish among:

- **Asymmetric:** A linking to B does not imply B links to A, such as following or dependency.
- **Symmetric:** if A is friends with B, then B is also friends with A by business definition.
- **Reflexive:** is an object allowed to link to itself?
- **Irreflexive:** an object cannot link to itself, e.g., a course cannot be a prerequisite for itself.
- **Transitive:** if A relates to B and B relates to C, does A relate to C? Do not infer transitivity unless explicitly defined by the business.

A symmetric relationship can be stored using one canonical pair to avoid storing both A–B and B–A, or stored bidirectionally if the system needs efficient directional queries. Either storage approach needs an explicit uniqueness rule.

### Representing directed relationships in the relational model

Example where a course can have multiple prerequisite courses:

~~~mermaid
erDiagram
    COURSE ||--o{ COURSE_PREREQUISITE : requires
    COURSE ||--o{ COURSE_PREREQUISITE : prerequisite_for
    COURSE {
        bigint course_id PK
        string course_name
    }
    COURSE_PREREQUISITE {
        bigint course_id PK, FK
        bigint prerequisite_course_id PK, FK
    }
~~~

Illustrative DDL:

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
    CONSTRAINT fk_cp_course
        FOREIGN KEY (course_id) REFERENCES course(course_id),
    CONSTRAINT fk_cp_prerequisite
        FOREIGN KEY (prerequisite_course_id) REFERENCES course(course_id),
    CONSTRAINT ck_course_not_own_prerequisite
        CHECK (course_id <> prerequisite_course_id)
);
~~~

In this table, `course_id` is the course requiring the condition; `prerequisite_course_id` is the course that must be completed first. The composite primary key prevents recording the exact same directed pair twice. It does not by itself forbid reverse pairs; if the business forbids two courses from being prerequisites for each other, check that separately.

The CHECK constraint only forbids a course from being its own prerequisite. It cannot detect multi-hop cycles like A depends on B, B depends on C, and C depends on A. If the relationship must form a directed acyclic graph (DAG), check for cycles using recursive queries or graph algorithms inside a concurrency-controlled transaction. Standard foreign keys cannot replace cycle detection.

## 3. Ordered relationships

An **ordered relationship** is one in which the position or sequence of elements carries business meaning. Examples:

- Steps in an approval workflow.
- Legs of a travel itinerary.
- Lessons within a course.
- Tracks in a playlist.
- Prioritized items in a processing queue.
- Versions or phases over time.

A standard many-to-many relationship is unordered by default. If order matters, model it explicitly via position, sequence number, timestamp, or sorting rules.

### Business order vs. display order

Distinguish two cases:

- **Business order:** changing position alters the meaning or workflow. For example, approval step 2 can run only after step 1.
- **Display order:** governs only how a list is presented and can change without altering business behavior, such as sorting a product catalog by name.

Do not store display order in the business model if it is only a temporary UI preference. Conversely, if position governs the process, protect it as core business data.

### Ways to represent ordering

| Representation | Suitable when | Considerations |
|---|---|---|
| Position number (`position`/`sequence_no`) | Explicitly ordered list | Must enforce uniqueness within parent scope and handle reordering |
| Timestamp (`occurred_at`/`effective_at`) | Order is determined by actual time | Must handle simultaneous events and timestamp precision |
| Precedence relation (before/after) | Only dependency order is needed, not absolute position | Can introduce cycles; querying total order is more complex |
| Sort key (`sort_key`) | Frequent insertions between existing elements | Needs rebalancing strategy and collision prevention |

Never rely on the physical storage order of rows in a database. Whenever order is required, queries must sort explicitly on a defined column, such as `ORDER BY position`.

### Example: ordered playlist

A playlist contains many tracks; each track has a distinct position in the list. Assume each track appears at most once in the same playlist:

~~~mermaid
erDiagram
    PLAYLIST ||--o{ PLAYLIST_ITEM : contains
    TRACK ||--o{ PLAYLIST_ITEM : selected_as
    PLAYLIST {
        bigint playlist_id PK
        string playlist_name
    }
    PLAYLIST_ITEM {
        bigint playlist_id PK, FK
        int position PK
        bigint track_id FK
        datetime added_at
    }
~~~

~~~sql
CREATE TABLE playlist (
    playlist_id BIGINT PRIMARY KEY,
    playlist_name VARCHAR(200) NOT NULL
);

CREATE TABLE track (
    track_id BIGINT PRIMARY KEY,
    track_title VARCHAR(200) NOT NULL
);

CREATE TABLE playlist_item (
    playlist_id BIGINT NOT NULL,
    position INTEGER NOT NULL,
    track_id BIGINT NOT NULL,
    added_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_playlist_item
        PRIMARY KEY (playlist_id, position),
    CONSTRAINT uq_playlist_track
        UNIQUE (playlist_id, track_id),
    CONSTRAINT fk_item_playlist
        FOREIGN KEY (playlist_id) REFERENCES playlist(playlist_id),
    CONSTRAINT fk_item_track
        FOREIGN KEY (track_id) REFERENCES track(track_id),
    CONSTRAINT ck_playlist_position_positive
        CHECK (position > 0)
);
~~~

The composite primary key ensures each position in a playlist holds only one track. UNIQUE ensures a track does not appear twice in the same playlist under the assumed business rule. If repeating the same track is allowed, drop this UNIQUE constraint; each appearance still has its own position.

The DDL above does not automatically enforce a 100-track maximum per playlist. Because that is a multi-row counting rule, check it inside a transaction with contention protection. One approach is locking the corresponding playlist row before counting and inserting:

~~~text
BEGIN TRANSACTION
  Lock the playlist row for this playlist_id
  Count playlist_item rows for this playlist_id
  If count >= 100, reject the insert
  Otherwise, insert the new playlist_item
COMMIT
~~~

This pseudocode outlines the operation sequence. In PostgreSQL, you can use `SELECT ... FOR UPDATE` to lock the playlist row; all write paths must follow the same protocol. Triggers or atomically updated counters can be used when appropriate, provided two concurrent transactions cannot both see one remaining slot and insert simultaneously.

Query to fetch the playlist in order:

~~~sql
SELECT
    pi.position,
    t.track_id,
    t.track_title
FROM playlist_item pi
JOIN track t ON t.track_id = pi.track_id
WHERE pi.playlist_id = :playlist_id
ORDER BY pi.position;
~~~

### Reordering and uniqueness

When swapping two items, updating row by row can temporarily violate `UNIQUE(playlist_id, position)`. You can use a temporary placeholder position, update in a safe order, or use deferred constraints if supported by the DBMS. When multiple users edit the same list, add conflict control so two transactions do not assign the same position.

If lists are very long with frequent mid-list insertions, sparse sort keys or fractional indexing can be used. However, those require strategies for key proximity, precision limits, and rebalancing. Sequential position integers are generally simpler when reordering happens infrequently.

## 4. Bounded relationships

A **bounded relationship** establishes a minimum or maximum participation count for an entity at one end of a relationship.

Examples:

- Every confirmed order must have at least one line item.
- Each employee can have at most two active emergency contacts.
- Each account has only one primary representative at a time.
- A group has between three and eight members.
- A workflow has at most five approval levels.

Write bounds in clear language and specify their scope:

- Minimum or maximum?
- Applies to all records or only a specific status?
- Counts current active items only or includes history?
- Measured per entity, per type, or system-wide?
- Effective at which point in time?

### Distinguishing bounds per side

Example of the Group–Member relationship:

- A group has 3 to 8 active members.
- A member can belong to 0 to 5 groups.

These two bounds apply to opposite sides. Saying only "a group has at most 8 members" does not imply each member can join at most 8 groups.

~~~mermaid
flowchart LR
    G["Group"] -->|"3..8 members"| M1["Member"]
    M2["Member"] -->|"0..5 groups"| G2["Group"]
~~~

A relationship diagram should place cardinalities on the right entity ends. When using ERD or UML notation, verify the tool's conventions to avoid misreading which side is bounded.

### Enforcing a maximum of one

A frequent case is "each customer has at most one active primary address." You can use an `is_primary` flag on the address table together with a conditional unique constraint if the DBMS supports partial/filtered unique indexes.

Example in PostgreSQL syntax:

~~~sql
CREATE UNIQUE INDEX uq_customer_one_active_primary_address
    ON customer_address (customer_id)
    WHERE is_active = TRUE AND is_primary = TRUE;
~~~

This constraint prevents a customer from having two addresses that are both active and marked primary. It does not require a customer to have at least one primary address; that is a separate minimum rule that must be enforced at the appropriate business checkpoint.

### Enforcing maximum bounds greater than one

Suppose each employee can have at most two active emergency contacts. When the cap is small and fixed, you can model a slot number within the allowed set:

~~~sql
CREATE TABLE employee_emergency_contact (
    employee_id BIGINT NOT NULL,
    slot_no SMALLINT NOT NULL,
    contact_name VARCHAR(160) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL,
    CONSTRAINT pk_employee_emergency_contact
        PRIMARY KEY (employee_id, slot_no),
    CONSTRAINT fk_emergency_contact_employee
        FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    CONSTRAINT ck_emergency_contact_slot
        CHECK (slot_no IN (1, 2))
);
~~~

The composite primary key plus CHECK limits each employee to at most two slots. This design works well when two slots represent a small, fixed limit with no complex ordering rules. If the maximum changes with policy or depends on contact type, fixed slots can make evolution harder.

For general bounds like at most N active records, a per-row CHECK constraint is insufficient because the condition spans multiple rows. Concurrency-safe enforcement is needed: a transaction locking the parent row, an appropriate trigger, or a counter updated atomically with inserts/deletes. Prevent two concurrent transactions from both counting an available slot and inserting simultaneously to exceed the cap.

### Enforcing minimum bounds

For example, "a confirmed order must have at least one order line" spans both the set of order lines and the order's status. A CHECK constraint on the order table only inspects columns of that row and cannot directly count rows in `order_line`.

You can enforce this when transitioning the order from DRAFT to CONFIRMED within the same transaction: lock or guard the order, verify at least one line exists, and only then update the status. If the DBMS supports deferred constraint triggers, you can check at commit time. Explicitly prevent a concurrent transaction from deleting the last line while another transaction confirms the order.

## 5. When direction, ordering, and bounds appear together

In practice, these characteristics often combine.

For instance, an approval workflow has at most five steps. Each step points to the next step; order determines who approves first; each step can have a primary approver and an alternate. The model must represent:

- Direction from earlier step to subsequent step.
- Position of each step in the workflow.
- Maximum bound of five steps.
- Only one step per position within the same workflow.
- No step pointing to itself.
- An acyclic rule preventing loops.
- Change history once the workflow has been activated.

An alternative is storing `sequence_no` on the step table and deriving previous/next steps from position. If the flow is strictly linear, storing both `next_step_id` and `sequence_no` is unnecessary because two ordering sources can drift out of sync. If the workflow branches, model transition edges explicitly and separate display ordering from execution flow.

### Avoid storing the same fact in multiple places

If `position = 3` defines the third step while `previous_step_id` and `next_step_id` are also stored, moving a step requires updating multiple links. Unless a field cannot be derived safely from the other, avoid redundancy. Each fact should have a single source of truth or a verified synchronization rule.

## 6. Translating relationship characteristics into data models

| Characteristic | Conceptual model | Relational model | Document | Graph |
|---|---|---|---|---|
| Directed | Clear source and target roles | Two role-named FKs | Two meaningful reference fields | Directed edge from source to target |
| Ordered | Position or sequencing rule | `position`/`sequence` column or timestamp | Ordered array or sort key field | Order property on edge/node or precedence relationship |
| Bounded | Min/max at each relationship end | UNIQUE, CHECK, trigger, or transaction | Validation and atomic updates on aggregate | Application checks or graph engine constraints |
| Has own attributes | Modeled as an association with attributes | Junction table | Nested object or link document | Properties on edge or relationship node |

In analytical models, many-to-many relationships typically require a bridge table. If the relationship is directed, the bridge must preserve source/target roles. If ordered, store sequence or effective time. If bounded, enforce bounds in the transactional source or ETL ingestion pipeline; analytical warehouses are rarely the sole place enforcing operational business rules.

## 7. Validating relationship constraints

A neat diagram is not enough. Verify each characteristic using valid and invalid test cases.

### Testing direction

- Create relationship A → B and confirm queries do not interpret it as B → A.
- Try creating the reverse link B → A to test whether business rules allow it.
- Test self-referencing link A → A.
- If a DAG is required, test creating short and multi-step cycles.

### Testing ordering

- Create three items at positions 1, 2, 3 and confirm queries return them in order.
- Try assigning duplicate positions under the same parent scope.
- Swap two items and verify updates leave no unexpected duplicates or gaps.
- Test two users reordering simultaneously.
- When using timestamps, test events with identical timestamps.

### Testing bounds

- Try creating fewer items than the minimum.
- Test exactly at the maximum bound.
- Try exceeding the maximum bound.
- Try deleting an item that drops the set below the minimum.
- Test two concurrent transactions adding the final allowed slot simultaneously.
- Test state transitions where cardinality rules begin taking effect.

### Query-based verification examples

Find courses with self-referencing prerequisites or duplicate data:

~~~sql
SELECT
    course_id,
    prerequisite_course_id
FROM course_prerequisite
WHERE course_id = prerequisite_course_id;
~~~

If the system already holds legacy data before constraints are applied, this query detects self-references. Find duplicate directed pairs using:

~~~sql
SELECT
    course_id,
    prerequisite_course_id,
    COUNT(*) AS duplicate_count
FROM course_prerequisite
GROUP BY course_id, prerequisite_course_id
HAVING COUNT(*) > 1;
~~~

Once the table has a composite primary key, duplicate rows cannot be newly inserted; this query remains useful when inspecting legacy or staging data before applying constraints.

## 8. Evolving relationships over time

Relationship bounds and semantics can change as the business evolves. For example, a group previously capped at eight members now permits twelve; an approval workflow gains branching; a playlist allows the same track multiple times; or a previously one-way relationship becomes bidirectional under new requirements.

When making changes, evaluate:

1. Does existing data violate the new or old bounds?
2. Do applications and integrations interpret direction, roles, and order correctly?
3. Do we need to backfill position, source/target, or effective status?
4. Can the new constraint be deployed before updating the application?
5. How must violating data be remediated, and who signs off?
6. Must historical relationship records be retained for auditing?

For maximum-bound changes, inspect existing data before creating new constraints. For ordering changes, decide the canonical source of order and how duplicate positions are resolved. For direction changes, never flip all historical edges automatically; define business rules per relationship type.

A safe migration sequence typically involves expanding the structure, backfilling and reconciling, switching applications, enabling new constraints, and only then dropping legacy fields. If a new rule could disrupt writes, prepare a transition plan and error-handling strategy.

## 9. Common modeling mistakes

- Using a generic relationship like `related_to` even when both ends have distinct roles.
- Assuming A → B automatically implies B → A.
- Failing to specify whether self-referencing is allowed.
- Relying on physical row order or unguaranteed element order.
- Storing both `position` and `next`/`previous` IDs with no single source of truth.
- Documenting only maximum bounds while forgetting minimums or status-based conditions.
- Assuming a single-row CHECK protects multi-row counts.
- Checking counts before inserting without concurrency control.
- Assuming foreign keys prevent cycles in graphs.
- Failing to specify whether bounds apply by time, status, or relationship type.
- Changing bounds or ordering without reconciling existing data.
- Overlooking relationship attributes such as timestamps, status, creator, and effective period.

## 10. Design and documentation process

For each relationship to be modeled:

1. Name it using a verb expressing its business meaning.
2. Identify each end and its source/target roles.
3. Determine whether the relationship is directed, symmetric, reflexive, or transitive.
4. Document min/max cardinality at each end along with applicability conditions.
5. Determine whether order matters; if so, choose position, time, or precedence links.
6. List attributes belonging to the relationship itself, if any.
7. Choose the logical representation and keys for the relationship.
8. Separate constraints enforceable by PK, FK, UNIQUE, CHECK from those requiring transactions or multi-row validation.
9. Define policies for deletion, archival, updates, and history.
10. Write verification queries and test cases for exceeding bounds, reversing direction, colliding positions, or forming cycles.

### Relationship specification template

| Field | What to record |
|---|---|
| Relationship name | Business verb or phrase |
| Entity/role A | First end and role |
| Entity/role B | Second end and role |
| Direction | Directed, symmetric, or not applicable |
| Cardinality A | Min..max on side A |
| Cardinality B | Min..max on side B |
| Ordering | None, by position, timestamp, or precedence relation |
| Bounds | Max/min, counting scope, and effective conditions |
| Relationship attributes | Status, timestamps, creator, order, effective period |
| Lifecycle rules | Deletion, archiving, updates, history |
| Enforcement mechanism | PK/FK/UNIQUE/CHECK/trigger/transaction |
| Verification | Queries and valid/invalid test cases |

## 11. Practice exercises and assessment rubric

### Exercise 1 — Course prerequisites

A course can require many prerequisite courses. The relationship is directed and must not form cycles. A course can have at most five prerequisites.

Identify the roles at both ends, design the junction table, keys, and constraints. Describe how to detect cycles and prevent two concurrent transactions from violating constraints when adding prerequisites.

### Exercise 2 — Playlist

A playlist has ordered tracks, cannot contain the same track twice, and holds at most 100 tracks. Users can reorder, add, and remove tracks.

Design the model, keys, UNIQUE constraints, and track cap. Explain how to swap positions without causing position collisions during updates.

### Exercise 3 — Group membership

A group must have three to eight active members; each member can join at most five groups.

Specify the bounds at each end and how to protect multi-row bounds under concurrent operations.

### Exercise 4 — Approval workflow

A workflow has up to five ordered steps. Each step has a primary approver and may have an alternate approver. Certain steps can be skipped based on business conditions.

Determine when to use sequence numbers, when transition links are needed, how to retain history, and how to avoid two conflicting ordering sources.

### Self-assessment rubric

| Criterion | Meets requirements when |
|---|---|
| Direction semantics | Correctly identifies source, target, and per-end roles |
| Symmetry | Knows whether reverse links are derived or stored explicitly |
| Ordering | Chooses an ordering representation with one source of truth and explicit query sorting |
| Cardinality | States min/max at each end and applicability conditions |
| Integrity | Distinguishes single-row constraints from multi-row constraints |
| Concurrency | Prevents exceeding bounds under competing transactions |
| Evolution | Plans changes to direction, ordering, bounds, and history |

A well-modeled relationship clearly answers who links to whom, in what direction, in what order, and how many links are allowed. When these rules are documented as semantics and testable constraints, the data model reduces ambiguity, protects integrity, and supports controlled business change.
