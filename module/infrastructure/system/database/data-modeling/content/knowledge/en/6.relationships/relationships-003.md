# Roles at Both Ends of a Relationship and Meaningful Naming

In a data model, a relationship indicates how business concepts are connected. However, simply knowing that two entities are related is not enough. We must understand **what role each party plays in the relationship**, how many instances on the other side an instance on one side can link to, and how to phrase the relationship so readers do not misunderstand its direction or meaning.

For example, the statement "Customer and Order are related" does not tell us whether the customer is the one placing the order, paying for it, or receiving it. An order may be placed by one customer, paid for by another party, and delivered to a different recipient. If the model only uses a generic relationship label like "related to", the roles of the participants become obscured.

This lesson focuses on the roles at both ends of a relationship, naming relationships based on business semantics, representing recursive and multi-role relationships, and validating names alongside cardinalities so the model remains clear and consistent.

**After this lesson, you will be able to:**

- Explain the role of each entity participating in a relationship.
- Distinguish the relationship name from the role names at each end.
- Name relationships using clear, meaningful verbs or verb phrases.
- Read a relationship in both directions without reversing the subject and object.
- Identify recursive relationships, symmetric relationships, and cases where one entity type participates in multiple roles.
- Use roles to clarify foreign keys, associative relationships, and business rules.

## 1. Why identify roles at both ends of a relationship?

A relationship connects instances of entity types. Each relationship end expresses how an entity type participates in that business meaning. A role answers the question: **What part does this instance play in this specific relationship?**

Consider the statement:

> One employee approves the leave request of another employee.

Both ends are the EMPLOYEE entity, yet their roles differ:

- The employee at the first end is the **approver**.
- The employee at the second end is the **requester**.

If we only write `EMPLOYEE — relates to — EMPLOYEE`, the reader cannot tell who approves whom. Role names clarify semantics that the entity name alone cannot express.

Another example:

> An order has a billing address and a shipping address.

Both addresses may belong to the ADDRESS concept, but within the order they serve two distinct roles:

- Billing address;
- Shipping address.

Do not assume both roles always hold the same value. An order can be shipped to one location and invoiced to another.

### 1.1. Three components to distinguish

When describing a binary relationship, distinguish:

| Component | Answers the question | Example |
|---|---|---|
| Entity type | Which types of objects participate? | CUSTOMER and ORDER |
| Relationship name | Through what action or meaning are the objects connected? | PLACES |
| Role at each end | In what capacity does each object participate? | Order placer; placed order |

The relationship can be expressed in the active voice:

> A customer **places** an order.

And the corresponding passive voice:

> An order **is placed by** a customer.

Both sentences describe the same relationship from two perspectives. Good naming makes both sentences easy to read.

### 1.2. Roles belong to the relationship, not necessarily to separate entity types

"Buyer", "recipient", and "approver" can be roles of a person or organization within a relationship. Having a role name does not automatically mean you must create a new table or entity type.

For instance, an employee may act as a leave requester this month and as an approver for another employee's request in a different situation. Roles change depending on the relationship and context.

Create a separate entity type only when it has an independent definition, identifier, attributes, lifecycle, or business rules confirmed by the domain.

## 2. Meaningful relationship naming

A relationship name should express what happens or what the link between entities means. For binary relationships, verbs or verb phrases are usually easiest to read.

Examples:

- CUSTOMER **places** ORDER.
- EMPLOYEE **approves** REQUEST.
- ORDER **is delivered via** SHIPMENT.
- PRODUCT **is classified into** CATEGORY.
- EMPLOYEE **reports to** MANAGER.

### 2.1. Prefer names that express business actions or meaning

Relationship names such as "has", "relates to", "belongs to", or "connects with" are often too generic without context. They may be used when the true meaning is ownership or general association, but you should verify whether readers infer the right rule.

| Vague name | Clearer name | What is clarified |
|---|---|---|
| CUSTOMER relates to ORDER | CUSTOMER places ORDER | Customer is the party initiating the transaction |
| EMPLOYEE has REQUEST | EMPLOYEE submits REQUEST | Distinguishes requester from approver |
| ORDER has SHIPMENT | ORDER is fulfilled via SHIPMENT | Clarifies fulfillment/shipping semantics |
| PRODUCT belongs to CATEGORY | CATEGORY classifies PRODUCT | Clarifies phrasing direction and classification meaning |
| EMPLOYEE links to EMPLOYEE | EMPLOYEE manages EMPLOYEE | Clarifies recursive relationship |

A relationship name does not need to be long, but it must be distinguishable from other relationships between the same two entity types.

### 2.2. Use consistent phrasing across the entire model

If the same meaning is called "places", "creates order", and "initiates order" across different diagrams, standardize on one canonical name and document aliases if needed. Relationship names should not vary depending on who drew the diagram.

A canonical name should:

- Use terminology familiar to the business;
- Accurately convey the action or meaning;
- Distinguish itself from other relationships between the same entities;
- Remain stable across documentation, models, and team discussions;
- Read naturally as a sentence from both directions.

If business terminology is not yet consistent, log an open question for confirmation instead of picking an arbitrary technical term and treating it as the definition.

## 3. Naming roles at both ends

A role name describes an instance's position within a relationship. It can be named using a noun or noun phrase indicating the role, such as "order placer", "placed order", "manager", or "managed employee".

For the relationship `CUSTOMER — PLACES — ORDER`:

| Relationship end | Entity type | Role | Explanatory question |
|---|---|---|---|
| First end | CUSTOMER | Order placer | Which orders did this customer place? |
| Second end | ORDER | Placed order | Which customer placed this order? |

Role names are especially helpful when:

- One entity type participates in relationships multiple times;
- Both ends carry different semantics;
- The relationship is read from multiple directions;
- The model has multiple foreign keys referencing the same table;
- Responsibilities or authorities need to be distinguished.

### 3.1. Roles and reading direction

A relationship can be read in two directions. For example:

- A customer **places** an order.
- An order **is placed by** a customer.

The relationship name can be phrased in the active voice, while role names at both ends identify the subject and object. When using diagrams, ensure the relationship label and arrow direction do not contradict the business statement.

Do not assume that left-to-right drawing order always represents the business direction. Diagrams can be laid out arbitrarily in space; meaning must reside in the relationship name, roles, and cardinality notation.

### 3.2. A role is not a cardinality

A role answers "in what capacity does the instance participate?". Cardinality answers "how many instances at the other end can or must one instance link to?".

For example, in a management relationship:

- Roles: manager and managed employee.
- Cardinality: a manager can manage many employees; each employee has at most one direct manager.

These two pieces of information complement rather than replace each other. A clear role name cannot make up for missing or incorrect cardinality.

## 4. Combining role names with cardinality and participation

Every relationship must specify minimum and maximum counts at each end. Common notation includes:

| Notation | Interpretation |
|---|---|
| 0..1 | Zero or at most one |
| 1..1 | Mandatory, exactly one |
| 0..* | Zero or many |
| 1..* | At least one, possibly many |

For example, in the relationship `CUSTOMER places ORDER`:

- A customer can place 0 or many orders.
- A recorded order must belong to exactly one customer under the system's assumption.

This can be represented as:

~~~mermaid
flowchart LR
    C["CUSTOMER<br/>Role: order placer"] -->|"places<br/>0..* orders"| O["ORDER<br/>Role: placed order"]
    O -->|"placed by<br/>1 customer"| C
~~~

The diagram illustrates bidirectional reading; the numbers reflect the business assumptions of the example. If the system allows walk-in guest orders, the order-side rule may differ and require modeling the buyer party appropriately.

### 4.1. Separate maximum and minimum cardinality

Do not just write "one-to-many" if the business needs to distinguish the zero-link case.

Examples:

- A customer may not have placed any orders yet: minimum 0.
- A confirmed order must have at least one line item: minimum 1.
- A draft order may not have any line items yet: in draft status, the minimum can be 0.

Participation can depend on status or timing. If the model only states a generic cardinality without noting conditions, readers may misinterpret it.

### 4.2. Read cardinality from each end

When reading a relationship, ask separately:

- How many instances at end B does one instance at end A link to at minimum and maximum?
- How many instances at end A does one instance at end B link to at minimum and maximum?

Reading both sides prevents confusing "every order belongs to one customer" with "every customer has only one order".

## 5. Relationships between entities of the same type: recursive roles

A recursive relationship is one in which the same entity type participates at multiple ends. In this case, role names are especially critical because the entity name alone cannot distinguish the two sides.

### 5.1. Example: employee manages employee

An employee can manage many other employees. Each employee has at most one direct manager.

Two roles:

- **Manager:** the instance at the managing end.
- **Managed employee:** the instance at the reporting end.

~~~mermaid
flowchart TD
    M["EMPLOYEE<br/>Role: manager"] -->|"manages<br/>0..* employees"| E["EMPLOYEE<br/>Role: managed employee"]
    E -->|"reports to<br/>0..1 manager"| M
~~~

This structure can be mapped logically to a self-referencing EMPLOYEE relation, e.g., an attribute `manager_employee_id` referencing `employee_id`. The column name must state the role so readers understand it identifies the manager, not an arbitrary employee.

Rules to clarify:

- Can top-level executives leave the manager blank?
- Is an employee allowed to manage themselves?
- Are cycles allowed, such as A manages B, B manages C, C manages A?
- Can an employee have multiple direct managers or only one?
- Is the management relationship time-bound (effective over a period)?

A self-referencing foreign key ensures the manager exists, but does not automatically prevent cycles or guarantee a valid organizational tree.

### 5.2. Example: referrer and referee

A customer can refer many other customers to join the system. Both ends are CUSTOMER, yet their roles differ:

- Referrer;
- Referee (referred customer).

If you need to store the timestamp, referral program, or reward status, the relationship may have its own attributes or be represented as an associative entity. Clarify whether one person can be referred by multiple people and which rule determines the valid referral credit.

## 6. One entity type participating in multiple roles within the same relationship context

Recursive relationships are not the only case requiring role names. A relationship context can have multiple ends referencing the same entity type.

### 6.1. Billing address and shipping address

An order can reference two addresses:

- Billing address;
- Shipping address.

Both ends are ADDRESS, but their roles differ. In the logical model, two foreign keys such as `billing_address_id` and `shipping_address_id` may appear referencing the same ADDRESS relation.

Foreign key names must reflect their roles. Naming both `address_id` in the same structure makes it hard for readers and maintainers to tell which value serves which purpose.

Additional checks to confirm:

- Can both roles point to the same address?
- Are both addresses mandatory?
- Must the order's address remain immutable as of placement time?
- Can one address be used by multiple orders?

### 6.2. Departure airport and arrival airport

A flight connects to two airports:

- Departure airport;
- Arrival airport.

Both ends are AIRPORT. Role names clarify the sequence and direction of the leg. You cannot merely say "flight links to airport" because it would be unclear which airport is the origin and which is the destination.

### 6.3. Source account and destination account

A funds transfer links two accounts:

- Source account;
- Destination account.

Both are ACCOUNT, yet each role has different rules. For example, the source account must be eligible for debit; the destination account must be eligible to receive funds. A validation rule stating that the two accounts cannot be identical may apply across both roles.

## 7. Symmetric and asymmetric relationships

Some relationships carry the same meaning when swapping the two ends; others have a clear direction.

### 7.1. Symmetric relationships

Example: the "is friends with" relationship between two people. If A is friends with B, then B is also friends with A by symmetric definition.

Both ends share the same entity type and nearly identical semantic roles. Even so, the system needs a storage rule to avoid storing the same pair twice as A–B and B–A if the relationship is undirected.

Determine:

- Is the relationship truly symmetric?
- Can a person be friends with themselves?
- Does the relationship need an accepted or pending-confirmation status?
- Do we need to record who initiated the invitation?

A friend request is directed with sender and recipient roles; the resulting friendship after acceptance can be symmetric. These are two distinct concepts even though both involve two people.

### 7.2. Asymmetric relationships

Relationships like "manages", "refers", "transfers money from", and "ships to" are directed. Swapping the two ends changes the meaning.

For instance, A transferring money to B is not equivalent to B transferring money to A. Role names must distinguish source and destination.

Do not use an undirected relationship structure for a directed business process without recording information that distinguishes the two ends.

### 7.3. Reflexive, symmetric, and transitive properties

When business rules involve complex relationship semantics, you may need to check these properties:

- **Reflexive:** whether an object relates to itself.
- **Symmetric:** if A relates to B, does B relate to A?
- **Transitive:** if A relates to B and B relates to C, does it follow that A relates to C?

For example, "equals" is reflexive, symmetric, and transitive; "directly manages" typically lacks those properties. Do not infer transitive relationships if the business only validates direct relationships.

## 8. Roles in n-ary relationships

An n-ary relationship links three or more entity types. Each end needs its own role, because merely listing entity type names may fail to convey the full meaning.

Example:

> A supplier supplies a product to a warehouse under a specific agreement.

Roles:

- Supplier: supplying party;
- Product: supplied item;
- Warehouse: receiving location.

~~~mermaid
flowchart TD
    R["SUPPLIER<br/>Role: supplying party"]
    P["PRODUCT<br/>Role: supplied item"]
    W["WAREHOUSE<br/>Role: receiving location"]
    X(("SUPPLY"))
    R --> X
    P --> X
    W --> X
~~~

Simply splitting this into three binary relationships—"supplier supplies product", "supplier delivers to warehouse", and "warehouse stores product"—may fail to preserve the meaning of a specific supply agreement. For example, supply pricing may depend simultaneously on supplier, product, warehouse, and contract term.

The role at each end must be explicitly documented. If the relationship has its own attributes or needs an identifier, it can be converted into an associative entity such as SUPPLY AGREEMENT.

## 9. Roles when relationships are mapped to a logical model

When translating to a relational logical model, role names directly influence foreign key names, attribute names, and associative table names.

### 9.1. Two foreign keys referencing the same table

For example, the ORDER table may reference CUSTOMER in two roles:

| Logical attribute | Role | Reference |
|---|---|---|
| placed_by_customer_id | Customer placing the order | CUSTOMER.customer_id |
| billed_to_customer_id | Customer responsible for payment | CUSTOMER.customer_id |

If both roles can be the same customer, both foreign keys can hold the same value. If business rules require them to differ in certain cases, document that constraint explicitly.

Column names like `customer_id_1` and `customer_id_2` convey no meaning. Use role-based names to avoid depending on declaration order.

### 9.2. Recursive relationships

The EMPLOYEE table may have `manager_employee_id` referencing `employee_id` in the same table. The `manager` prefix clarifies the role at the referenced end. If the model must store multiple management layers or transfer history, a separate management-relationship table may be more suitable.

### 9.3. Associative relationships

For a many-to-many relationship with clear roles, the associative table should be named to reflect the action or meaning, such as ENROLLMENT for a student enrolling in a course.

Attributes might include:

- `student_id`: role of the enrolling student;
- `course_id`: role of the enrolled course;
- `enrolled_at`: enrollment timestamp;
- `enrollment_status`: enrollment status.

If a student can enroll in the same course multiple times across different terms, the unique key cannot simply be `(student_id, course_id)`. You must include the academic term or an enrollment instance identifier to preserve the business rule.

## 10. Consistent naming rules across the model

A solid naming convention enables readers to understand the model without opening external documentation for every connecting line.

### 10.1. Rules for relationship names

- Use a verb or verb phrase describing the action or meaning.
- Prefer terminology confirmed by the business.
- Avoid generic names whenever a more specific word applies.
- Use one canonical name for the same meaning.
- If multiple relationships exist between the same two entities, give each a distinct name.

### 10.2. Rules for role names

- Use nouns or noun phrases indicating the participation position.
- Names must distinguish ends, especially when the same entity type appears multiple times.
- Avoid "side 1", "side 2", "entity A", "entity B" in finalized models.
- Do not treat a role name as if it were always an independent entity type.
- If a role is conditional or time-bound, document its scope and effective period.

### 10.3. Rules for foreign key names

Foreign key names should reflect the role of the referenced entity. Examples:

| Unclear | Clearer |
|---|---|
| customer_id_1 | placed_by_customer_id |
| customer_id_2 | billed_to_customer_id |
| employee_id_1 | manager_employee_id |
| employee_id_2 | approved_by_employee_id |
| address_id_1 | billing_address_id |
| address_id_2 | shipping_address_id |

Physical names can follow the project's `snake_case` or `camelCase` convention, while preserving the role semantics.

### 10.4. Using canonical names and aliases

If sales calls them "buyer" while customer support calls them "account holder", determine whether they refer to the same concept and role. If they are aliases, record them for traceability. If they represent different roles, keep separate names.

## 11. Comprehensive example: order model with multiple roles

A sales system has the following requirements:

- A customer can place many orders.
- Every order is placed by one customer.
- An order may be paid for by a customer or organization different from the one who placed it.
- An order has a billing address and a shipping address.
- An employee may approve an order in certain cases.
- Each order can be fulfilled in multiple shipments.

We can describe the roles as follows:

| Relationship | First end and role | Second end and role | Meaning |
|---|---|---|---|
| PLACES ORDER | CUSTOMER — order placer | ORDER — placed order | Who creates the order? |
| PAYS FOR | CUSTOMER/ORGANIZATION — paying party | ORDER — paid order | Who is responsible for payment? |
| USES BILLING ADDRESS | ORDER — order to be invoiced | ADDRESS — billing address | Which address appears on the invoice? |
| USES SHIPPING ADDRESS | ORDER — order to be delivered | ADDRESS — shipping address | Where are the goods delivered? |
| APPROVES | EMPLOYEE — approver | ORDER — approved order | Who has approval authority? |
| FULFILLED AS | ORDER — order to fulfill | SHIPMENT — shipment belonging to order | Into which shipments is the order packed? |

Illustrative diagram:

~~~mermaid
flowchart LR
    C["CUSTOMER<br/>order placer"] -->|"places"| O["ORDER"]
    P["CUSTOMER / ORGANIZATION<br/>paying party"] -->|"pays for"| O
    E["EMPLOYEE<br/>approver"] -->|"approves"| O
    O -->|"uses billing address"| BA["ADDRESS<br/>billing"]
    O -->|"uses shipping address"| SA["ADDRESS<br/>shipping"]
    O -->|"fulfilled as"| S["SHIPMENT"]
~~~

Key points to note:

- The order placer and the paying party can be the same entity or different entities.
- The billing address and shipping address can match or differ.
- The approver is an employee role within the approval relationship, not necessarily a new employee subtype.
- An order can be shipped in multiple shipments; each shipment needs its own identifier and status if tracking is required by the business.

Role names allow the model to represent these cases without ambiguous foreign key references.

## 12. Common mistakes

1. **Listing only the two entity names:** readers know a link exists but cannot tell each party's role.
2. **Using overly generic relationship names:** "has", "relates to", and "connects" fail to clarify the action or rule.
3. **Failing to distinguish two ends of the same entity type:** an EMPLOYEE manages EMPLOYEE relationship requires manager and managed employee roles.
4. **Confusing a role with an entity type:** "approver" may simply be a role of an employee, not always a separate table.
5. **Confusing a role name with cardinality:** the role "order placer" does not tell you how many orders a customer may place.
6. **Reading a relationship in only one direction:** diagrams easily end up reversing subject and object.
7. **Numbering foreign key names:** `customer_id_1` and `customer_id_2` fail to communicate intent.
8. **Assuming symmetry:** "friends with" may be symmetric, but "manages" or "transfers money to" is not.
9. **Splitting an n-ary relationship into non-equivalent pairs:** loses the meaning of the combined roles.
10. **Ignoring time-bound roles:** a manager or active address can change over time.
11. **Using multiple names for the same meaning:** makes traceability and cross-team communication difficult.
12. **Skipping exception checks:** the model may work for the happy path yet break when the placer differs from the payer or an order splits into multiple shipments.

## 13. Checklist for reviewing relationship names and roles

- [ ] Every relationship has a name that clearly expresses the business action or meaning.
- [ ] Every relationship end has an identified entity type and role.
- [ ] The relationship reads as a meaningful sentence from both sides.
- [ ] When the same entity type appears at multiple ends, role names distinguish them.
- [ ] Minimum and maximum cardinalities are determined independently of role names.
- [ ] Mandatory or optional participation is confirmed.
- [ ] Recursive relationships have clear role names and cycle-prevention rules where needed.
- [ ] Symmetric and asymmetric relationships are clearly distinguished.
- [ ] N-ary relationships have names and roles for each component.
- [ ] Foreign key names reflect roles rather than confusing ordinal suffixes.
- [ ] Roles are not confused with entity types or attributes.
- [ ] Canonical names are used consistently across diagrams, data dictionaries, and documentation.

## 14. Practice exercise

An HR system has the following requirements:

- An employee can manage many employees.
- Each employee has at most one direct manager.
- An employee can submit leave requests.
- Another employee has the authority to approve requests.
- Each leave request belongs to exactly one submitting employee.
- A request may be unapproved, pending, or decided.

Perform the following tasks:

1. Identify the participating entity types.
2. Name the relationship between the managing employee and the managed employee.
3. Name the roles at both ends of the request-submission relationship.
4. Name the roles at both ends of the approval relationship.
5. State the minimum and maximum cardinalities based on the requirements.
6. Propose foreign key names when mapping to a relational logical model.
7. Point out which rules require handling beyond standard foreign keys.

**Suggested answers:**

| Relationship | First end role | Second end role | Reference cardinality |
|---|---|---|---|
| MANAGES | Managing employee (manager) | Managed employee | A manager has 0..* employees; an employee has 0..1 direct manager |
| SUBMITS REQUEST | Requester | Submitted leave request | An employee submits 0..* requests; each request belongs to exactly 1 employee |
| APPROVES | Approver | Approved leave request | An employee can approve 0..* requests; a request may have no approver yet or at most 1 approver under the assumed workflow |

Reference logical attribute names:

- `EMPLOYEE.manager_employee_id`: direct manager.
- `LEAVE_REQUEST.requested_by_employee_id`: submitting employee.
- `LEAVE_REQUEST.approved_by_employee_id`: approving employee, nullable while unprocessed.

Foreign keys can ensure that the manager, requester, and approver exist. Rules such as preventing self-approval, requiring the approver to hold authority at approval time, ensuring leave dates do not conflict with blackout periods, and preventing management cycles require appropriate business validation mechanisms.

This exercise is complete when a reader can unambiguously tell who manages whom, who submits the request, who approves it, and what state a request is in without guessing from column names or diagram endpoint positions.
